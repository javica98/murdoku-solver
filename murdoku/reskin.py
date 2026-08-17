import json

from murdoku.generator import render_clue_template
from murdoku.schema import Clue, Puzzle

REWORD_THEME_SYSTEM_PROMPT = """Dado un tema, traduce cada nombre de la \
lista de objetos y salas genericos de un juego de misterio a un \
equivalente tematico breve (1-3 palabras).

Devuelve UNICAMENTE un objeto JSON PLANO donde cada CLAVE es EXACTAMENTE \
uno de los nombres originales que recibes (la clave NO se traduce) y \
cada VALOR es un objeto con dos campos: "nombre" (la traduccion \
tematica) y "genero" ("m" o "f", el genero gramatical en español de esa \
traduccion). Nunca devuelvas listas ni valores sueltos -- una entrada \
por cada objeto Y por cada sala recibidos, ni una mas ni una menos.

Ejemplo -- si recibes:
{"tema": "piratas", "objetos": ["silla", "cama"], "salas": ["AREA_0"]}

Debes devolver EXACTAMENTE esta forma:
{"silla": {"nombre": "barril", "genero": "m"}, "cama": {"nombre": "hamaca", "genero": "f"}, "AREA_0": {"nombre": "Cubierta del barco", "genero": "f"}}"""


def get_theme_vocabulary(
    objects: list[str], areas: list[str], theme: str, client, model: str = "gpt-5.4-nano"
) -> dict[str, dict[str, str]]:
    """Le pide al modelo barato un mapeo objeto/sala generico -> {nombre,
    genero} tematico, p.ej. tema "piratas": {"silla": {"nombre": "barril",
    "genero": "m"}}. Si el modelo no devuelve JSON valido, se deja alguna
    clave fuera, o el genero no es "m"/"f", esa clave concreta
    simplemente no se retema (se queda con su nombre generico) en vez de
    fallar todo el puzzle.
    """
    payload = json.dumps({"tema": theme, "objetos": objects, "salas": areas}, ensure_ascii=False)
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

    valid_keys = set(objects) | set(areas)
    vocabulary: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if key not in valid_keys or not isinstance(value, dict):
            continue
        nombre = value.get("nombre")
        genero = value.get("genero")
        if not isinstance(nombre, str) or not nombre:
            continue
        vocabulary[key] = {"nombre": nombre, "genero": genero if genero in ("m", "f") else "f"}
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
    if "clauses" in new_structured:
        new_structured["clauses"] = [
            _rethemed_structured(c, name_map, gender_map) for c in new_structured["clauses"]
        ]
    return new_structured


def apply_theme(puzzle: Puzzle, vocabulary: dict[str, dict[str, str]]) -> Puzzle:
    """Sustituye nombres genericos de objeto/sala por su equivalente
    tematico en todo el puzzle (celdas, areas, y las pistas -- vuelve a
    renderizar el texto de cada una a partir de su version ya retemada,
    en vez de pedirle al LLM que reescriba frase a frase). El genero
    tematico de cada objeto viaja con la pista para que las plantillas
    ("un"/"una", "el"/"la") concuerden aunque el retema cambie el genero
    gramatical original.
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

    new_people = []
    for person in puzzle.people:
        if person.clue is None or person.clue.structured is None:
            new_people.append(person)
            continue
        new_structured = _rethemed_structured(person.clue.structured, name_map, gender_map)
        new_people.append(
            person.model_copy(
                update={"clue": Clue(text=render_clue_template(new_structured), structured=new_structured)}
            )
        )

    return puzzle.model_copy(update={"cells": new_cells, "areas": new_areas, "people": new_people})


def reskin_puzzle(puzzle: Puzzle, theme: str, client, model: str = "gpt-5.4-nano") -> Puzzle:
    objects = sorted({obj for cell in puzzle.cells.values() for obj in cell.objects})
    areas = sorted(puzzle.areas.keys())
    vocabulary = get_theme_vocabulary(objects, areas, theme, client, model=model)
    if not vocabulary:
        return puzzle
    return apply_theme(puzzle, vocabulary)
