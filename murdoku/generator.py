import random

from murdoku.schema import Cell, Clue, Grid, Person, Puzzle
from murdoku.verifier import (
    area_bounding_box,
    clue_holds,
    evaluate_clue_positive,
    identify_murderer,
    parse_cell_id,
)


def _orthogonal_neighbor_ids(cell_id: str, rows: int, cols: int) -> list[str]:
    row, col = parse_cell_id(cell_id)
    candidates = [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]
    return [f"r{r}c{c}" for r, c in candidates if 0 <= r < rows and 0 <= c < cols]


def _has_isolated_cell(cell_area: dict[str, str], rows: int, cols: int) -> bool:
    """True si alguna celda no tiene NINGUN vecino ortogonal de su misma
    sala -- una isla de una sola celda, que no tiene sentido como plano
    de una habitacion real (encontramos justo este caso a mano en un
    puzzle transcrito: una celda "aislada" en medio de otra sala).
    """
    for cell_id, area in cell_area.items():
        neighbor_areas = {cell_area[n] for n in _orthogonal_neighbor_ids(cell_id, rows, cols)}
        if area not in neighbor_areas:
            return True
    return False


def generate_rooms(
    rows: int,
    cols: int,
    area_names: list[str],
    rng: random.Random | None = None,
    max_attempts: int = 200,
) -> dict[str, Cell]:
    """Reparte todas las celdas de la rejilla entre las salas dadas.

    Usa un crecimiento por inundacion aleatorio: cada sala parte de una
    celda semilla y, en cada ronda, reclama una celda vecina libre al azar.
    Esto garantiza que cada sala quede como una unica pieza conectada --
    pero la semilla de una sala puede quedar aislada si sus vecinos los
    reclaman otras salas antes de que le toque turno, asi que se reintenta
    con semillas nuevas hasta que ninguna celda quede sin vecino propio.
    """
    if rng is None:
        rng = random.Random()

    all_cell_ids = [f"r{r}c{c}" for r in range(rows) for c in range(cols)]
    if len(area_names) > len(all_cell_ids):
        raise ValueError("more areas than cells")

    for _ in range(max_attempts):
        seeds = rng.sample(all_cell_ids, len(area_names))
        cell_area: dict[str, str] = dict(zip(seeds, area_names))
        unclaimed = set(all_cell_ids) - set(cell_area)

        frontiers = {
            area: set(_orthogonal_neighbor_ids(seed, rows, cols)) & unclaimed
            for area, seed in zip(area_names, seeds)
        }

        while unclaimed:
            areas_order = area_names.copy()
            rng.shuffle(areas_order)
            for area in areas_order:
                candidates = frontiers[area] & unclaimed
                if not candidates:
                    continue
                chosen = rng.choice(sorted(candidates))
                cell_area[chosen] = area
                unclaimed.discard(chosen)
                frontiers[area].discard(chosen)
                frontiers[area].update(set(_orthogonal_neighbor_ids(chosen, rows, cols)) & unclaimed)

        if _has_isolated_cell(cell_area, rows, cols):
            continue

        return {
            cell_id: Cell(area=area, objects=[], blocked=False)
            for cell_id, area in cell_area.items()
        }

    raise RuntimeError(f"no se logro un reparto de salas sin celdas aisladas en {max_attempts} intentos")


def generate_placement(
    rows: int, cols: int, person_ids: list[str], rng: random.Random | None = None
) -> dict[str, str]:
    """Coloca cada persona en una celda distinta, sin repetir fila ni columna.

    Requiere una rejilla cuadrada con tantas personas como filas/columnas
    (la regla base del juego: una persona por fila y por columna).
    """
    if rows != cols:
        raise ValueError(f"grid must be square, got {rows} rows and {cols} cols")
    if len(person_ids) != rows:
        raise ValueError(
            f"expected {rows} people for a {rows}x{cols} grid, got {len(person_ids)}"
        )

    if rng is None:
        rng = random.Random()

    shuffled_people = person_ids.copy()
    rng.shuffle(shuffled_people)

    columns = list(range(cols))
    rng.shuffle(columns)

    return {
        person_id: f"r{row}c{col}"
        for row, (person_id, col) in enumerate(zip(shuffled_people, columns))
    }


BLOCKING_OBJECTS = ["estanteria", "mesa", "planta"]
NON_BLOCKING_OBJECTS = ["silla", "alfombra", "cama"]
ALL_OBJECTS = BLOCKING_OBJECTS + NON_BLOCKING_OBJECTS

# Rasgos fisicos para pistas de tipo relational_attribute. Cada atributo
# es solo un dict valor -> frase descriptiva -- la parte tecnica (elegir
# atributo, comparar valores, redactar la frase) funciona identica para
# cualquiera de ellos, asi que anadir un atributo nuevo es solo anadir
# una entrada aqui. Las frases del valor "negativo" de un atributo
# binario se escriben como "iba sin X" (nunca "no tenia X"), para que la
# plantilla "Nadie mas ... {descriptor}" no acabe en doble negacion.
ATTRIBUTE_CATALOG: dict[str, dict[str, str]] = {
    "genero": {
        "hombre": "era un hombre",
        "mujer": "era una mujer",
    },
    "color_pelo": {
        "rubio": "tenia el pelo rubio",
        "moreno": "tenia el pelo moreno",
        "pelirrojo": "tenia el pelo pelirrojo",
        "canoso": "tenia el pelo canoso",
    },
    "gafas": {
        "con_gafas": "llevaba gafas",
        "sin_gafas": "iba sin gafas",
    },
    "barba": {
        "con_barba": "tenia barba",
        "sin_barba": "iba sin barba",
    },
}


def assign_attributes(person_ids: list[str], rng: random.Random) -> dict[str, dict[str, str]]:
    """Asigna a cada persona un valor de CADA atributo del catalogo, al azar.

    Todo el mundo (sospechosos y victima) recibe los mismos atributos --
    no hay ninguna razon tecnica para excluir a la victima, y si un
    sospechoso acaba compartiendo sala con ella, tambien puede comparar
    su rasgo contra el de ella.
    """
    return {
        person_id: {
            attribute: rng.choice(list(values.keys()))
            for attribute, values in ATTRIBUTE_CATALOG.items()
        }
        for person_id in person_ids
    }


def _make_area_clause(cell: Cell) -> dict:
    return {"type": "area", "area": cell.area}


def _make_object_on_clause(
    cell: Cell, rng: random.Random, forbidden: frozenset[str] = frozenset()
) -> dict | None:
    candidates = [obj for obj in NON_BLOCKING_OBJECTS if obj not in forbidden]
    if not candidates:
        return None
    obj = rng.choice(candidates)
    cell.objects.append(obj)
    return {"type": "object_on", "object": obj}


def _make_object_adjacent_clause(
    cell_id: str,
    cells: dict[str, Cell],
    occupied_cells: set[str],
    rows: int,
    cols: int,
    rng: random.Random,
    forbidden: frozenset[str] = frozenset(),
) -> dict | None:
    # solo en celdas vecinas libres, para no colocar un objeto bloqueante
    # encima de otra persona. `forbidden` son objetos que alguna pista
    # negada en otra parte del tablero necesita que NO aparezcan en
    # ningun sitio (ver _make_negated_object_adjacent_clause).
    free_neighbors = [
        n for n in _orthogonal_neighbor_ids(cell_id, rows, cols) if n not in occupied_cells
    ]
    candidates = [obj for obj in ALL_OBJECTS if obj not in forbidden]
    if not free_neighbors or not candidates:
        return None

    neighbor_id = rng.choice(sorted(free_neighbors))
    obj = rng.choice(candidates)
    neighbor = cells[neighbor_id]
    neighbor.objects.append(obj)
    if obj in BLOCKING_OBJECTS:
        neighbor.blocked = True
    return {"type": "object_adjacent", "object": obj}


def _make_absolute_position_clause(
    cell_id: str, cell: Cell, cells: dict[str, Cell], rng: random.Random
) -> dict | None:
    if cell.area is None:
        return None

    row, col = parse_cell_id(cell_id)
    min_row, max_row, min_col, max_col = area_bounding_box(cells, cell.area)

    options = []
    if row in (min_row, max_row) and col in (min_col, max_col):
        options.append("corner")
    if col == max_col:
        options.append("last_column")
    if not options:
        return None

    return {"type": "absolute_position", "position": rng.choice(options)}


def _make_any_area_clause(cell: Cell, area_names: list[str], rng: random.Random) -> dict | None:
    # el "o": una clausula cierta (su area de verdad) mas una senuelo (otra
    # area cualquiera) -- el "any" solo necesita que UNA sea cierta.
    decoys = [name for name in area_names if name != cell.area]
    if not decoys:
        return None
    return {
        "type": "any",
        "clauses": [
            {"type": "area", "area": cell.area},
            {"type": "area", "area": rng.choice(decoys)},
        ],
    }


def _make_negated_object_adjacent_clause(
    cell_id: str, cells: dict[str, Cell], rows: int, cols: int, rng: random.Random
) -> dict | None:
    # la negacion: un objeto que NO esta en ninguna celda vecina.
    adjacent_objects = set()
    for neighbor_id in _orthogonal_neighbor_ids(cell_id, rows, cols):
        adjacent_objects.update(cells[neighbor_id].objects)

    false_candidates = [obj for obj in ALL_OBJECTS if obj not in adjacent_objects]
    if not false_candidates:
        return None

    return {
        "type": "object_adjacent",
        "object": rng.choice(false_candidates),
        "negate": True,
    }


def _make_unique_object_on_clause(
    cell: Cell,
    used_on_own_cell: set[str],
    rng: random.Random,
    forbidden: frozenset[str] = frozenset(),
) -> dict | None:
    candidates = [
        obj for obj in NON_BLOCKING_OBJECTS if obj not in used_on_own_cell and obj not in forbidden
    ]
    if not candidates:
        return None

    obj = rng.choice(candidates)
    cell.objects.append(obj)
    return {"type": "unique_object_on", "object": obj}


def _make_relational_attribute_clause(
    person_id: str,
    area: str | None,
    cells: dict[str, Cell],
    placement: dict[str, str],
    person_attributes: dict[str, dict[str, str]],
    rng: random.Random,
) -> dict | None:
    roommates = _people_sharing_area(person_id, area, cells, placement)
    if not roommates:
        return None

    attribute = rng.choice(list(ATTRIBUTE_CATALOG.keys()))
    value = person_attributes[person_id][attribute]
    shared = any(person_attributes[pid][attribute] == value for pid in roommates)

    return {
        "type": "relational_attribute",
        "attribute": attribute,
        "value": value,
        "relation": "with_another" if shared else "none_with",
    }


def _people_sharing_area(
    person_id: str, area: str, cells: dict[str, Cell], placement: dict[str, str]
) -> list[str]:
    return sorted(
        pid
        for pid, other_cell_id in placement.items()
        if pid != person_id and cells[other_cell_id].area == area
    )


def _direction_and_distance(row: int, col: int, anchor_row: int, anchor_col: int, axis: str) -> tuple[str, int]:
    """Direccion + distancia EXACTA de (row, col) respecto a (anchor_row,
    anchor_col) en un solo eje -- fila (norte/sur) o columna (este/oeste).
    """
    if axis == "row":
        return ("south", row - anchor_row) if row > anchor_row else ("north", anchor_row - row)
    return ("east", col - anchor_col) if col > anchor_col else ("west", anchor_col - col)


def _make_relative_to_person_clause(
    person_id: str, cell_id: str, placement: dict[str, str], rng: random.Random
) -> dict | None:
    others = [pid for pid in placement if pid != person_id]
    if not others:
        return None

    row, col = parse_cell_id(cell_id)
    reference = rng.choice(others)
    reference_row, reference_col = parse_cell_id(placement[reference])

    # fila y columna nunca coinciden entre dos personas distintas (una
    # persona por fila/columna), asi que los dos ejes son siempre validos.
    axis = rng.choice(["row", "col"])
    direction, distance = _direction_and_distance(row, col, reference_row, reference_col, axis)

    return {
        "type": "relative_to_person",
        "reference": reference,
        "direction": direction,
        "distance": distance,
    }


def _relative_to_object_candidates(cell_id: str, cells: dict[str, Cell]) -> list[tuple[str, str, int]]:
    """(objeto, direccion, distancia) candidatos validos para anclar una
    pista de distancia a un objeto -- solo objetos que aparecen en una
    UNICA celda de todo el tablero (si no, la distancia seria ambigua), y
    solo ejes donde la distancia no sea cero (mismo eje que el objeto no
    dice nada sobre "norte" o "sur").
    """
    row, col = parse_cell_id(cell_id)

    cells_by_object: dict[str, list[str]] = {}
    for other_cell_id, cell in cells.items():
        for obj in cell.objects:
            cells_by_object.setdefault(obj, []).append(other_cell_id)

    candidates = []
    for obj, cell_ids in cells_by_object.items():
        if len(cell_ids) != 1:
            continue
        anchor_row, anchor_col = parse_cell_id(cell_ids[0])
        if row != anchor_row:
            direction, distance = _direction_and_distance(row, col, anchor_row, anchor_col, "row")
            candidates.append((obj, direction, distance))
        if col != anchor_col:
            direction, distance = _direction_and_distance(row, col, anchor_row, anchor_col, "col")
            candidates.append((obj, direction, distance))
    return candidates


def _make_relative_to_object_clause(
    cell_id: str, cells: dict[str, Cell], rng: random.Random
) -> dict | None:
    candidates = _relative_to_object_candidates(cell_id, cells)
    if not candidates:
        return None

    obj, direction, distance = rng.choice(candidates)
    return {"type": "relative_to_object", "object": obj, "direction": direction, "distance": distance}


def _available_global_types(
    person_id: str,
    cell_id: str,
    cell: Cell,
    cells: dict[str, Cell],
    placement: dict[str, str],
    occupied_cells: set[str],
    rows: int,
    cols: int,
    used_on_own_cell: set[str],
) -> list[str]:
    """Que tipos "globales" son ciertos AHORA MISMO para esta persona, dada
    la colocacion ya completa de todo el mundo (relacionales, que dependen
    de otras personas) o el estado de los objetos ya colocados hasta ahora
    (unique_object_on).

    A diferencia de area/object_on/object_adjacent (siempre se pueden
    forzar colocando un objeto), estos dependen de si la geometria y la
    colocacion ya dan la casualidad de que son ciertos -- por eso hace
    falta comprobar disponibilidad antes de elegir uno. Tambien son los
    que no se pueden podar temprano al comprobar unicidad, por eso se
    limitan con `num_relational_people` en vez de ofrecerse a todo el
    mundo.
    """
    types = []

    has_free_neighbor = any(
        n not in occupied_cells for n in _orthogonal_neighbor_ids(cell_id, rows, cols)
    )
    others_in_area = _people_sharing_area(person_id, cell.area, cells, placement)

    if has_free_neighbor:
        types.append("empty_neighbor")
    if not others_in_area:
        types.append("relational_person_alone")
    if others_in_area:
        types.append("with_person")
        types.append("relational_attribute")
    if len(placement) > 1:
        # cualquier otra persona sirve de referencia (norte/sur/este/oeste,
        # no solo "al sur de alguien mas arriba" como antes).
        types.append("relative_to_person")
    if any(obj not in used_on_own_cell for obj in NON_BLOCKING_OBJECTS):
        types.append("unique_object_on")

    return types


def assign_clues_and_objects(
    placement: dict[str, str],
    cells: dict[str, Cell],
    rows: int,
    cols: int,
    rng: random.Random | None = None,
    num_clues: int = 1,
    num_relational_people: int = 0,
    person_attributes: dict[str, dict[str, str]] | None = None,
) -> tuple[dict[str, Cell], dict[str, dict]]:
    """Para cada persona, elige `num_clues` tipos de pista ciertos segun su
    colocacion (combinados con "all" si son mas de uno) y coloca los
    objetos que hagan falta para que lo sean.

    Cubre los 4 tipos "de celda propia" (area, object_on, object_adjacent,
    relative_to_object -- siempre se pueden forzar o ya estan fijados por
    la geometria) y 5 relacionales (empty_neighbor, relational_person/alone,
    with_person, relative_to_person, relational_attribute -- solo
    disponibles si la colocacion ya los hace ciertos por si sola, ver
    `_available_global_types`).

    Las relacionales no se pueden podar temprano al comprobar unicidad
    (dependen de donde esta el resto de gente, no solo de la celda
    propia) -- si demasiada gente las tiene a la vez en un tablero
    grande, la busqueda de unicidad se vuelve casi exhaustiva y puede
    tardar una eternidad. `num_relational_people` limita a cuantas
    personas (elegidas al azar) se les ofrece la opcion de tener una
    pista relacional; el resto se queda solo con las 3 de celda propia,
    que sabemos que podan bien sea cual sea el tamaño del tablero.

    Devuelve una copia de `cells` con los objetos añadidos, y un dict
    persona -> clue.structured.
    """
    if rng is None:
        rng = random.Random()

    cells = {cell_id: cell.model_copy(deep=True) for cell_id, cell in cells.items()}
    occupied_cells = set(placement.values())
    clues: dict[str, dict] = {}
    area_names = sorted({cell.area for cell in cells.values() if cell.area is not None})
    if person_attributes is None:
        person_attributes = assign_attributes(list(placement.keys()), rng)
    # objetos ya colocados en la celda PROPIA de alguien (object_on o
    # unique_object_on) -- unique_object_on necesita saber esto para no
    # elegir un objeto que ya deje de ser unico.
    used_on_own_cell: set[str] = set()
    # objetos que una pista negada en OTRA persona necesita que no
    # aparezcan en ningun sitio del tablero a partir de ahora (si no, una
    # colocacion posterior podria colarse justo donde esa pista dice que
    # NO deberia haber nada). Ver _make_negated_object_adjacent_clause.
    globally_banned_objects: set[str] = set()
    # objetos que YA anclan una pista relative_to_object en curso -- si se
    # colocara una segunda copia en otra celda, esa distancia dejaria de
    # ser inequivoca. Ver _relative_to_object_candidates.
    distance_anchor_objects: set[str] = set()

    person_ids = list(placement.keys())
    relational_eligible = set(
        rng.sample(person_ids, min(num_relational_people, len(person_ids)))
    )

    for person_id, cell_id in placement.items():
        cell = cells[cell_id]

        available_types = [
            "area", "object_on", "object_adjacent", "absolute_position",
            "any_area", "negated_object_adjacent",
        ]
        # row-local igual que absolute_position (el objeto ancla es
        # geometria fija, no depende de donde acabe nadie) -- no hace
        # falta limitarla con num_relational_people.
        if _relative_to_object_candidates(cell_id, cells):
            available_types.append("relative_to_object")
        if person_id in relational_eligible:
            available_types += _available_global_types(
                person_id, cell_id, cell, cells, placement, occupied_cells,
                rows, cols, used_on_own_cell,
            )
        chosen_types = rng.sample(available_types, min(num_clues, len(available_types)))

        clauses = []
        for clue_type in chosen_types:
            if clue_type == "area":
                clauses.append(_make_area_clause(cell))
            elif clue_type == "object_on":
                clause = _make_object_on_clause(
                    cell, rng,
                    forbidden=used_on_own_cell | globally_banned_objects | distance_anchor_objects,
                )
                if clause is not None:
                    used_on_own_cell.add(clause["object"])
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "object_adjacent":
                clause = _make_object_adjacent_clause(
                    cell_id, cells, occupied_cells, rows, cols, rng,
                    forbidden=globally_banned_objects | distance_anchor_objects,
                )
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "absolute_position":
                clause = _make_absolute_position_clause(cell_id, cell, cells, rng)
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "any_area":
                clause = _make_any_area_clause(cell, area_names, rng)
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "negated_object_adjacent":
                clause = _make_negated_object_adjacent_clause(cell_id, cells, rows, cols, rng)
                if clause is not None:
                    globally_banned_objects.add(clause["object"])
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "empty_neighbor":
                clauses.append({"type": "empty_neighbor"})
            elif clue_type == "relational_person_alone":
                clauses.append({"type": "relational_person", "relation": "alone"})
            elif clue_type == "with_person":
                reference = rng.choice(_people_sharing_area(person_id, cell.area, cells, placement))
                clauses.append({"type": "with_person", "reference": reference})
            elif clue_type == "relative_to_person":
                clause = _make_relative_to_person_clause(person_id, cell_id, placement, rng)
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "relative_to_object":
                clause = _make_relative_to_object_clause(cell_id, cells, rng)
                if clause is not None:
                    distance_anchor_objects.add(clause["object"])
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "unique_object_on":
                clause = _make_unique_object_on_clause(
                    cell, used_on_own_cell, rng,
                    forbidden=globally_banned_objects | distance_anchor_objects,
                )
                if clause is not None:
                    used_on_own_cell.add(clause["object"])
                clauses.append(clause if clause is not None else _make_area_clause(cell))
            elif clue_type == "relational_attribute":
                clause = _make_relational_attribute_clause(
                    person_id, cell.area, cells, placement, person_attributes, rng
                )
                clauses.append(clause if clause is not None else _make_area_clause(cell))

        clues[person_id] = clauses[0] if len(clauses) == 1 else {"type": "all", "clauses": clauses}

    return cells, clues


def _negate_sentence(text: str) -> str:
    """"Estaba junto a una mesa." -> "No estaba junto a una mesa." """
    if text.startswith("Estaba "):
        return "No estaba " + text[len("Estaba ") :]
    return "No " + text[0].lower() + text[1:]


_DIRECTION_LABELS = {"north": "norte", "south": "sur", "east": "este", "west": "oeste"}
_DIRECTION_AXIS_WORD = {"north": "fila", "south": "fila", "east": "columna", "west": "columna"}


def _distance_phrase(direction: str, distance: int) -> str:
    axis_word = _DIRECTION_AXIS_WORD[direction]
    unit = axis_word if distance == 1 else axis_word + "s"
    return f"{distance} {unit} al {_DIRECTION_LABELS[direction]}"


def render_clue_template(structured: dict) -> str:
    """Redaccion fija en español a partir de una pista estructurada.

    No pretende sonar natural por si sola -- es la base determinista
    que luego reformula `reword_with_llm`.
    """
    clue_type = structured.get("type")

    if clue_type == "all":
        parts = []
        for clause in structured.get("clauses", []):
            text = render_clue_template(clause)
            parts.append(_negate_sentence(text) if clause.get("negate") else text)
        return " ".join(parts)

    if clue_type == "any":
        clauses = structured.get("clauses", [])
        if len(clauses) == 2 and all(c.get("type") == "area" and not c.get("negate") for c in clauses):
            return f"Estaba en la sala {clauses[0]['area']} o en la sala {clauses[1]['area']}."
        parts = []
        for clause in clauses:
            text = render_clue_template(clause)
            parts.append(_negate_sentence(text) if clause.get("negate") else text)
        return " O bien: ".join(parts)

    if clue_type == "area":
        return f"Estaba en la sala {structured['area']}."

    if clue_type == "object_on":
        return f"Estaba sobre una {structured['object']}."

    if clue_type == "unique_object_on":
        return f"Era la unica persona sobre una {structured['object']}."

    if clue_type == "object_adjacent":
        return f"Estaba junto a una {structured['object']}."

    if clue_type == "absolute_position":
        position = structured.get("position")
        if position == "corner":
            return "Estaba en una esquina de su sala."
        if position == "last_column":
            return "Estaba en la ultima columna de su sala."
        raise ValueError(f"no hay plantilla para absolute_position: {position!r}")

    if clue_type == "empty_neighbor":
        return "Habia una celda vacia justo a su lado."

    if clue_type == "relational_person" and structured.get("relation") == "alone":
        return "Estaba a solas."

    if clue_type == "with_person":
        return f"Estaba con {structured['reference']}."

    if clue_type == "relative_to_person":
        reference = structured["reference"]
        direction = structured["direction"]
        distance = structured.get("distance")
        if distance is None:
            return f"Estaba al {_DIRECTION_LABELS[direction]} de {reference}."
        return f"Estaba {_distance_phrase(direction, distance)} de {reference}."

    if clue_type == "relative_to_object":
        obj = structured["object"]
        direction = structured["direction"]
        distance = structured["distance"]
        return f"Estaba {_distance_phrase(direction, distance)} de la {obj}."

    if clue_type == "relational_attribute":
        attribute = structured["attribute"]
        value = structured["value"]
        descriptor = ATTRIBUTE_CATALOG[attribute][value]
        subject = "Nadie mas" if structured["relation"] == "none_with" else "Alguien mas"
        return f"{subject} en su sala {descriptor}."

    raise ValueError(f"no hay plantilla para el tipo de pista: {clue_type!r}")


REWORD_SYSTEM_PROMPT = """Reescribe la siguiente pista de un puzzle de misterio
en español, manteniendo EXACTAMENTE el mismo significado (no añadas ni quites
informacion). Solo dale una redaccion mas natural y variada. Devuelve
unicamente la frase reescrita, sin comillas ni explicacion adicional."""


def reword_with_llm(text: str, client, model: str = "gpt-5.4-nano") -> str:
    response = client.responses.create(
        model=model,
        input=[
            {"type": "message", "role": "developer", "content": REWORD_SYSTEM_PROMPT},
            {"type": "message", "role": "user", "content": text},
        ],
    )
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    return content.text.strip()
    return text


# Tipos que solo dependen de la celda propia de la persona (y de la
# geometria estatica del tablero) -- nunca de donde esta colocada otra
# persona. Siempre se pueden evaluar del todo en cuanto se coloca a esa
# persona. relative_to_object entra aqui porque el objeto ancla es parte
# de la geometria fija (ya colocado antes de resolver), no de la solucion.
ROW_LOCAL_CLUE_TYPES = {"area", "object_on", "object_adjacent", "absolute_position", "relative_to_object"}

# Tipos que dependen de una persona concreta, nombrada por id. Se pueden
# evaluar en cuanto ESA persona (no falta que este todo el mundo) ya
# tiene celda asignada.
_SINGLE_REFERENCE_TYPES = {"with_person", "relative_to_person"}


def _partial_eval(
    structured: dict,
    person_id: str,
    cell_id: str,
    puzzle: Puzzle,
    assignment: dict[str, str],
) -> bool | None:
    """Evalua una pista con la informacion que haya AHORA MISMO.

    Devuelve True/False si ya se puede saber con certeza (aunque falte
    gente por colocar, para clausulas de "all"/"any" a veces ya se sabe
    el resultado final igual), o None si todavia no hay suficiente
    informacion para decidir (p.ej. una referencia a alguien que aun no
    tiene celda). Esto es lo que permite podar una pista relacional en
    cuanto se puede, en vez de esperar siempre a que este todo colocado.

    Envoltorio fino sobre `_partial_eval_positive`, igual que
    `clue_holds`/`evaluate_clue_positive` en el verificador: calcula el
    resultado en positivo y lo invierte una sola vez si `structured`
    lleva "negate" (sea pista suelta o clausula dentro de un "all"/"any").
    """
    result = _partial_eval_positive(structured, person_id, cell_id, puzzle, assignment)
    if structured.get("negate") and result is not None:
        return not result
    return result


def _partial_eval_positive(
    structured: dict,
    person_id: str,
    cell_id: str,
    puzzle: Puzzle,
    assignment: dict[str, str],
) -> bool | None:
    clue_type = structured.get("type")

    if clue_type in ("all", "any"):
        results = [
            _partial_eval(clause, person_id, cell_id, puzzle, assignment)
            for clause in structured.get("clauses", [])
        ]

        if clue_type == "all":
            if any(r is False for r in results):
                return False
            return True if all(r is True for r in results) else None

        # "any"
        if any(r is True for r in results):
            return True
        return False if all(r is False for r in results) else None

    if clue_type in _SINGLE_REFERENCE_TYPES:
        if structured.get("reference") not in assignment:
            return None
        return evaluate_clue_positive(structured, person_id, cell_id, puzzle, assignment)

    if clue_type in ROW_LOCAL_CLUE_TYPES:
        return evaluate_clue_positive(structured, person_id, cell_id, puzzle, assignment)

    # Tipos "globales" (relational_person/alone, relational_attribute,
    # unique_object_on, empty_neighbor...): dependen de quien mas pueda
    # llegar a colocarse en cualquier sitio, no de una persona concreta
    # ya conocida -- no se pueden confirmar ni descartar de forma
    # fiable hasta tener la colocacion completa.
    return None


class SearchBudgetExceeded(Exception):
    """La busqueda de find_all_solutions supero max_nodes sin terminar.

    Con muchas pistas relacionales (no podables temprano) en un tablero
    grande, la busqueda puede acercarse a explorar casi todo el espacio.
    Este tope evita que se quede colgada indefinidamente; quien la llama
    decide que hacer (has_unique_solution la trata como "no confirmado").
    """


def find_all_solutions(
    puzzle: Puzzle, max_solutions: int = 2, max_nodes: int = 300_000
) -> list[dict[str, str]]:
    """Busca por fuerza bruta colocaciones validas que cumplan todas las
    pistas, parando en cuanto encuentra `max_solutions`.

    Usa backtracking (fila por fila, probando cada persona/columna libre)
    en vez de generar todas las permutaciones y filtrar: para las pistas
    "de celda propia" (area, object_on, object_adjacent,
    absolute_position), en cuanto fallan se descarta la rama sin seguir
    explorando. Las pistas relacionales (dependen de otras personas) no
    se pueden comprobar de forma fiable a medias, asi que se verifican
    todas juntas al completar cada colocacion candidata -- si hay muchas
    a la vez en un tablero grande, la busqueda apenas poda y `max_nodes`
    puede saltar (ver SearchBudgetExceeded).
    """
    rows = puzzle.grid.rows
    cols = puzzle.grid.cols
    person_ids = [person.id for person in puzzle.people]
    clue_by_person = {
        person.id: person.clue.structured
        for person in puzzle.people
        if person.clue is not None and person.clue.structured is not None
    }

    solutions: list[dict[str, str]] = []
    nodes_visited = 0

    def backtrack(row: int, used_cols: set[int], assignment: dict[str, str], remaining: list[str]) -> None:
        nonlocal nodes_visited

        if len(solutions) >= max_solutions:
            return
        if row == rows:
            if all(
                clue_holds(structured, person_id, assignment[person_id], puzzle, assignment)
                for person_id, structured in clue_by_person.items()
            ):
                solutions.append(dict(assignment))
            return

        for person_id in remaining:
            for col in range(cols):
                if col in used_cols:
                    continue
                cell_id = f"r{row}c{col}"
                cell = puzzle.cells.get(cell_id)
                if cell is None or cell.blocked:
                    continue

                nodes_visited += 1
                if nodes_visited > max_nodes:
                    raise SearchBudgetExceeded(f"exceeded {max_nodes} nodes")

                structured = clue_by_person.get(person_id)
                assignment[person_id] = cell_id
                if structured is not None and _partial_eval(
                    structured, person_id, cell_id, puzzle, assignment
                ) is False:
                    del assignment[person_id]
                    continue

                new_remaining = [p for p in remaining if p != person_id]
                backtrack(row + 1, used_cols | {col}, assignment, new_remaining)
                del assignment[person_id]

                if len(solutions) >= max_solutions:
                    return

    backtrack(0, set(), {}, person_ids)
    return solutions


def has_unique_solution(puzzle: Puzzle, max_nodes: int = 100_000) -> bool:
    try:
        return len(find_all_solutions(puzzle, max_solutions=2, max_nodes=max_nodes)) == 1
    except SearchBudgetExceeded:
        # no pudimos confirmar unicidad dentro del presupuesto -- lo mas
        # seguro es tratarlo como "no unico" y dejar que generate_puzzle
        # lo descarte y reintente, en vez de arriesgarnos a dar por bueno
        # un puzzle que no llegamos a verificar del todo.
        return False


def generate_puzzle(
    rows: int,
    cols: int,
    person_ids: list[str],
    victim_id: str,
    area_names: list[str],
    scenario: str,
    difficulty: str,
    rng: random.Random | None = None,
    max_attempts: int = 500,
    num_clues: int = 1,
    num_relational_people: int = 0,
) -> Puzzle:
    """Genera un puzzle completo con solucion unica y asesino identificable.

    Junta los 4 pasos anteriores (colocar personas, geometria+objetos+
    pistas, texto de plantilla, comprobar unicidad). Si un intento sale
    ambiguo o sin asesino determinable, se reintenta desde cero (nueva
    colocacion, nuevas salas, nuevas pistas) hasta `max_attempts` veces.

    Con una sola pista simple por persona (`num_clues=1`), la
    probabilidad de que un intento salga unico + con asesino
    identificable cae en picado segun crece el tablero (medido: ~0% en
    9x9). Subir `num_clues` a 2 o 3 (combinadas con "all") es lo que de
    verdad arregla esto, no subir `max_attempts` -- ver DIFFICULTY_TIERS.
    """
    if victim_id not in person_ids:
        raise ValueError(f"victim_id {victim_id!r} not in person_ids")

    if rng is None:
        rng = random.Random()

    for attempt in range(max_attempts):
        placement = generate_placement(rows, cols, person_ids, rng=rng)
        rooms = generate_rooms(rows, cols, area_names, rng=rng)
        person_attributes = assign_attributes(person_ids, rng)
        cells, clues = assign_clues_and_objects(
            placement,
            rooms,
            rows,
            cols,
            rng=rng,
            num_clues=num_clues,
            num_relational_people=num_relational_people,
            person_attributes=person_attributes,
        )

        areas: dict[str, list[str]] = {}
        for cell_id, cell in cells.items():
            areas.setdefault(cell.area, []).append(cell_id)

        people = [
            Person(
                id=person_id,
                role="victim" if person_id == victim_id else "suspect",
                clue=(
                    None
                    if person_id == victim_id
                    else Clue(
                        text=render_clue_template(clues[person_id]),
                        structured=clues[person_id],
                    )
                ),
                attributes=person_attributes[person_id],
            )
            for person_id in person_ids
        ]

        puzzle = Puzzle(
            id=f"generated_{attempt}",
            scenario=scenario,
            difficulty=difficulty,
            grid=Grid(rows=rows, cols=cols),
            areas=areas,
            cells=cells,
            people=people,
            solution=placement,
        )

        if identify_murderer(puzzle, placement) is None:
            continue
        if not has_unique_solution(puzzle):
            continue

        return puzzle

    raise RuntimeError(f"no se logro un puzzle valido en {max_attempts} intentos")


# Tramos de dificultad: tamaño del tablero + numero de salas + cuantas
# pistas se combinan por persona + cuanta gente puede tener una pista
# relacional a la vez. Los twists (objetos multi-celda, paridad) de la
# Fase 2 siguen sin implementarse en el generador, aunque el verificador
# ya los entiende. Valores medidos empiricamente: dan solucion unica +
# asesino identificable en un tiempo razonable (sub-segundo por intento)
# en los 4 tramos, incluido 9x9 con pistas relacionales de verdad.
DIFFICULTY_TIERS = {
    "easy": {"rows": 4, "cols": 4, "num_areas": 2, "num_clues": 2, "num_relational_people": 2},
    "medium": {"rows": 6, "cols": 6, "num_areas": 3, "num_clues": 2, "num_relational_people": 2},
    "hard": {"rows": 8, "cols": 8, "num_areas": 4, "num_clues": 4, "num_relational_people": 3},
    "expert": {"rows": 9, "cols": 9, "num_areas": 5, "num_clues": 4, "num_relational_people": 3},
}


def generate_puzzle_for_difficulty(
    difficulty: str,
    person_ids: list[str],
    victim_id: str,
    scenario: str,
    rng: random.Random | None = None,
    max_attempts: int = 500,
) -> Puzzle:
    if difficulty not in DIFFICULTY_TIERS:
        raise ValueError(f"unsupported difficulty: {difficulty!r}")

    tier = DIFFICULTY_TIERS[difficulty]
    rows = tier["rows"]
    cols = tier["cols"]
    if len(person_ids) != rows:
        raise ValueError(
            f"difficulty {difficulty!r} needs a {rows}x{cols} grid "
            f"({rows} people), got {len(person_ids)}"
        )

    area_names = [f"AREA_{i}" for i in range(tier["num_areas"])]
    return generate_puzzle(
        rows,
        cols,
        person_ids,
        victim_id,
        area_names,
        scenario,
        difficulty,
        rng=rng,
        max_attempts=max_attempts,
        num_clues=tier["num_clues"],
        num_relational_people=tier["num_relational_people"],
    )
