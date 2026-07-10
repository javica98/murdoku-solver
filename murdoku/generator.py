import random

from murdoku.schema import Cell
from murdoku.verifier import parse_cell_id


def _orthogonal_neighbor_ids(cell_id: str, rows: int, cols: int) -> list[str]:
    row, col = parse_cell_id(cell_id)
    candidates = [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]
    return [f"r{r}c{c}" for r, c in candidates if 0 <= r < rows and 0 <= c < cols]


def generate_rooms(
    rows: int, cols: int, area_names: list[str], rng: random.Random | None = None
) -> dict[str, Cell]:
    """Reparte todas las celdas de la rejilla entre las salas dadas.

    Usa un crecimiento por inundacion aleatorio: cada sala parte de una
    celda semilla y, en cada ronda, reclama una celda vecina libre al azar.
    Esto garantiza que cada sala quede como una unica pieza conectada.
    """
    if rng is None:
        rng = random.Random()

    all_cell_ids = [f"r{r}c{c}" for r in range(rows) for c in range(cols)]
    if len(area_names) > len(all_cell_ids):
        raise ValueError("more areas than cells")

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

    return {
        cell_id: Cell(area=area, objects=[], blocked=False)
        for cell_id, area in cell_area.items()
    }


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


def assign_clues_and_objects(
    placement: dict[str, str],
    cells: dict[str, Cell],
    rows: int,
    cols: int,
    rng: random.Random | None = None,
) -> tuple[dict[str, Cell], dict[str, dict]]:
    """Para cada persona, elige un tipo de pista cierta segun su colocacion
    y coloca los objetos que hagan falta para que lo sea.

    Solo cubre los 3 tipos mas simples de la taxonomia (area, object_on,
    object_adjacent); los relacionales (que dependen de donde esta el
    resto de gente) se añaden en un paso posterior.

    Devuelve una copia de `cells` con los objetos añadidos, y un dict
    persona -> clue.structured.
    """
    if rng is None:
        rng = random.Random()

    cells = {cell_id: cell.model_copy(deep=True) for cell_id, cell in cells.items()}
    occupied_cells = set(placement.values())
    clues: dict[str, dict] = {}

    for person_id, cell_id in placement.items():
        cell = cells[cell_id]
        clue_type = rng.choice(["area", "object_on", "object_adjacent"])

        if clue_type == "area":
            clues[person_id] = {"type": "area", "area": cell.area}
            continue

        if clue_type == "object_on":
            obj = rng.choice(NON_BLOCKING_OBJECTS)
            cell.objects.append(obj)
            clues[person_id] = {"type": "object_on", "object": obj}
            continue

        # object_adjacent: solo en celdas vecinas libres, para no colocar
        # un objeto bloqueante encima de otra persona.
        free_neighbors = [
            n
            for n in _orthogonal_neighbor_ids(cell_id, rows, cols)
            if n not in occupied_cells
        ]
        if not free_neighbors:
            clues[person_id] = {"type": "area", "area": cell.area}
            continue

        neighbor_id = rng.choice(sorted(free_neighbors))
        obj = rng.choice(ALL_OBJECTS)
        neighbor = cells[neighbor_id]
        neighbor.objects.append(obj)
        if obj in BLOCKING_OBJECTS:
            neighbor.blocked = True
        clues[person_id] = {"type": "object_adjacent", "object": obj}

    return cells, clues


def render_clue_template(structured: dict) -> str:
    """Redaccion fija en español a partir de una pista estructurada.

    No pretende sonar natural por si sola -- es la base determinista
    que luego reformula `reword_with_llm`.
    """
    clue_type = structured.get("type")

    if clue_type == "area":
        return f"Estaba en la sala {structured['area']}."

    if clue_type == "object_on":
        return f"Estaba sobre una {structured['object']}."

    if clue_type == "object_adjacent":
        return f"Estaba junto a una {structured['object']}."

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
