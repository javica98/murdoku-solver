import json

from murdoku.generator import render_clue_template
from murdoku.schema import Clue, Puzzle
from murdoku.verifier import (
    check_clues_satisfied,
    check_no_blocked_cells,
    check_unique_rows_and_cols,
    identify_murderer,
)

REWORD_THEME_SYSTEM_PROMPT = """Dado un tema, traduce cada nombre de la \
lista de objetos, salas y personajes genericos de un juego de misterio a \
un equivalente tematico breve (1-3 palabras). Los personajes son \
sospechosos/victima de un asesinato: dales nombres propios que encajen \
con el tema, no descripciones.

Devuelve UNICAMENTE un objeto JSON PLANO donde cada CLAVE es EXACTAMENTE \
uno de los nombres originales que recibes (la clave NO se traduce) y \
cada VALOR es un objeto con TRES campos: "nombre" (la traduccion \
tematica), "genero" ("m" o "f" -- el genero gramatical en español; en \
personajes, el genero de ESE personaje) y "emoji" (UN SOLO emoji que lo \
represente visualmente -- usa "" si de verdad no hay ninguno que \
encaje, y siempre "" para personajes). Nunca devuelvas listas ni \
valores sueltos -- una entrada por cada nombre recibido, ni una mas ni \
una menos.

IMPORTANTE: cada traduccion debe ser UNICA -- nunca repitas el mismo \
"nombre" para dos claves distintas, ni siquiera entre categorias \
distintas (un objeto y un personaje no pueden acabar llamandose igual).

Cada "nombre" debe tener una relacion clara y reconocible con el tema \
recibido -- alguien familiarizado con el tema debe poder explicar por \
que ese objeto/sala/personaje encaja. Si no se te ocurre una traduccion \
que encaje de verdad, usa una version generica del tema (p.ej. "trofeo" \
para futbol) antes que una palabra rara sin relacion aparente.

Ejemplo -- si recibes:
{"tema": "piratas", "objetos": ["silla", "cama"], "salas": ["AREA_0"], "personajes": ["Ada", "Bruno"]}

Debes devolver EXACTAMENTE esta forma:
{"silla": {"nombre": "barril", "genero": "m", "emoji": "🛢️"}, "cama": {"nombre": "hamaca", "genero": "f", "emoji": "🏕️"}, "AREA_0": {"nombre": "Cubierta del barco", "genero": "f", "emoji": ""}, "Ada": {"nombre": "Anamaria", "genero": "f", "emoji": ""}, "Bruno": {"nombre": "Barbanegra", "genero": "m", "emoji": ""}}"""


def get_theme_vocabulary(
    objects: list[str],
    areas: list[str],
    people: list[str],
    theme: str,
    client,
    model: str = "gpt-5.4-nano",
) -> dict[str, dict[str, str]]:
    """Le pide al modelo barato un mapeo objeto/sala/personaje generico ->
    {nombre, genero, emoji} tematico. Si el modelo no devuelve JSON
    valido, se deja alguna clave fuera, repite un nombre, o el genero no
    es "m"/"f", esa clave concreta (o el lote entero, si el JSON es
    ilegible) simplemente no se retema -- `reskin_puzzle` es quien decide
    que hacer con un resultado incompleto o repetido.
    """
    payload = json.dumps(
        {"tema": theme, "objetos": objects, "salas": areas, "personajes": people}, ensure_ascii=False
    )
    response = client.responses.create(
        model=model,
        input=[
            {"type": "message", "role": "developer", "content": REWORD_THEME_SYSTEM_PROMPT},
            {"type": "message", "role": "user", "content": payload},
        ],
    )

    text = ""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text += content.text

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return {}

    valid_keys = set(objects) | set(areas) | set(people)
    vocabulary: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if key not in valid_keys or not isinstance(value, dict):
            continue
        nombre = value.get("nombre")
        genero = value.get("genero")
        emoji = value.get("emoji")
        if not isinstance(nombre, str) or not nombre:
            continue
        vocabulary[key] = {
            "nombre": nombre,
            "genero": genero if genero in ("m", "f") else "f",
            "emoji": emoji if isinstance(emoji, str) else "",
        }
    return vocabulary


def _rethemed_structured(
    structured: dict, name_map: dict[str, str], gender_map: dict[str, str]
) -> dict:
    new_structured = dict(structured)
    if "object" in new_structured:
        original = new_structured["object"]
        themed = name_map.get(original, original)
        new_structured["object"] = themed
        new_structured["gender"] = gender_map.get(themed, structured.get("gender", "f"))
    if "area" in new_structured:
        new_structured["area"] = name_map.get(new_structured["area"], new_structured["area"])
    if "reference" in new_structured:
        new_structured["reference"] = name_map.get(new_structured["reference"], new_structured["reference"])
    if "clauses" in new_structured:
        new_structured["clauses"] = [
            _rethemed_structured(c, name_map, gender_map) for c in new_structured["clauses"]
        ]
    return new_structured


def apply_theme(puzzle: Puzzle, vocabulary: dict[str, dict[str, str]]) -> Puzzle:
    """Sustituye nombres genericos de objeto/sala/personaje por su
    equivalente tematico en todo el puzzle -- celdas, areas, ids de
    persona, la solucion, y las pistas (vuelve a renderizar el texto de
    cada una a partir de su version ya retemada, en vez de pedirle al
    LLM que reescriba frase a frase). El genero tematico de cada objeto
    viaja con la pista para que las plantillas ("un"/"una", "el"/"la")
    concuerden aunque el retema cambie el genero gramatical original.

    Puede producir un puzzle INVALIDO si el vocabulario tiene nombres
    repetidos (dos claves distintas con el mismo "nombre" chocarian al
    convertirse en, p.ej., dos claves identicas en `solution`) -- por
    eso `reskin_puzzle` siempre revisa el resultado con
    `_themed_puzzle_is_valid` antes de darlo por bueno.
    """
    name_map = {key: value["nombre"] for key, value in vocabulary.items()}
    gender_map = {value["nombre"]: value["genero"] for value in vocabulary.values()}

    new_cells = {
        cell_id: cell.model_copy(
            update={
                "objects": [name_map.get(obj, obj) for obj in cell.objects],
                "area": name_map.get(cell.area, cell.area) if cell.area is not None else None,
            }
        )
        for cell_id, cell in puzzle.cells.items()
    }

    new_areas = {name_map.get(area, area): cell_ids for area, cell_ids in puzzle.areas.items()}

    # solo las claves de object_emoji son objetos (las de area/personaje
    # no viven ahi) -- asi distinguimos "silla" de "AREA_0"/"Ada" sin
    # necesitar que el LLM etiquete cada entrada por categoria.
    new_object_emoji = {}
    for key, old_emoji in puzzle.object_emoji.items():
        themed = vocabulary.get(key)
        if themed is not None:
            new_object_emoji[themed["nombre"]] = themed.get("emoji") or old_emoji
        else:
            new_object_emoji[key] = old_emoji

    new_solution = None
    if puzzle.solution is not None:
        new_solution = {name_map.get(pid, pid): cell_id for pid, cell_id in puzzle.solution.items()}

    new_people = []
    for person in puzzle.people:
        new_id = name_map.get(person.id, person.id)
        if person.clue is None or person.clue.structured is None:
            new_people.append(person.model_copy(update={"id": new_id}))
            continue
        new_structured = _rethemed_structured(person.clue.structured, name_map, gender_map)
        new_people.append(
            person.model_copy(
                update={
                    "id": new_id,
                    "clue": Clue(text=render_clue_template(new_structured), structured=new_structured),
                }
            )
        )

    theme_vocabulary = {key: value["nombre"] for key, value in vocabulary.items()}

    return puzzle.model_copy(
        update={
            "cells": new_cells,
            "areas": new_areas,
            "people": new_people,
            "solution": new_solution,
            "object_emoji": new_object_emoji,
            "theme_vocabulary": {**puzzle.theme_vocabulary, **theme_vocabulary},
        }
    )


def _themed_puzzle_is_valid(original: Puzzle, themed: Puzzle) -> bool:
    """Vuelve a pasar el puzzle retemado por el MISMO verificador que usa
    todo el proyecto, en vez de confiar en que el LLM no se haya
    equivocado. Esto es lo que de verdad detecta un nombre repetido: si
    dos objetos distintos acaban llamandose igual, una pista
    relative_to_object/same_axis que dependia de que ese objeto fuera
    unico en el tablero deja de cumplirse; si dos personajes acaban con
    el mismo nombre, uno de los dos desaparece de `solution` (las claves
    de un dict no se pueden repetir) y el recuento de personas no cuadra.
    """
    if themed.solution is None or original.solution is None:
        return False
    if len(themed.solution) != len(original.solution):
        return False
    if len({person.id for person in themed.people}) != len(themed.people):
        return False

    violations = (
        check_unique_rows_and_cols(themed.solution)
        + check_no_blocked_cells(themed, themed.solution)
        + check_clues_satisfied(themed, themed.solution)
    )
    if violations:
        return False

    return identify_murderer(themed, themed.solution) is not None


def reskin_puzzle(
    puzzle: Puzzle, theme: str, client, model: str = "gpt-5.4-nano", max_attempts: int = 3
) -> Puzzle:
    """Aplica un tema con reintento: si el vocabulario que devuelve el
    LLM produce un puzzle que ya no supera nuestro propio verificador
    (nombres repetidos, sobre todo), se descarta ese intento y se le
    vuelve a pedir. Si ningun intento sale valido, el puzzle se queda tal
    cual (generico) en vez de entregar algo roto.
    """
    objects = sorted({obj for cell in puzzle.cells.values() for obj in cell.objects})
    areas = sorted(puzzle.areas.keys())
    people = sorted(person.id for person in puzzle.people)

    for _ in range(max_attempts):
        vocabulary = get_theme_vocabulary(objects, areas, people, theme, client, model=model)
        if not vocabulary:
            continue
        themed = apply_theme(puzzle, vocabulary)
        if _themed_puzzle_is_valid(puzzle, themed):
            return themed

    return puzzle
