import random

from murdoku.schema import Cell, Clue, Grid, Person, Puzzle
from murdoku.verifier import clue_holds, identify_murderer, parse_cell_id


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


# Tipos que solo dependen de la celda propia de la persona (y de la
# geometria estatica del tablero) -- nunca de donde esta colocada otra
# persona. Son seguros para descartar una rama antes de tiempo durante
# la busqueda. Todo lo demas (with_person, relational_person,
# empty_neighbor, unique_object_on...) depende de gente que puede que
# aun no este colocada, asi que no se puede comprobar de forma fiable
# hasta tener la colocacion completa.
_ROW_LOCAL_TYPES = {"area", "object_on", "object_adjacent", "absolute_position"}


def _is_row_local_clue(structured: dict) -> bool:
    clue_type = structured.get("type")
    if clue_type in ("all", "any"):
        return all(_is_row_local_clue(clause) for clause in structured.get("clauses", []))
    return clue_type in _ROW_LOCAL_TYPES


def find_all_solutions(puzzle: Puzzle, max_solutions: int = 2) -> list[dict[str, str]]:
    """Busca por fuerza bruta colocaciones validas que cumplan todas las
    pistas, parando en cuanto encuentra `max_solutions`.

    Usa backtracking (fila por fila, probando cada persona/columna libre)
    en vez de generar todas las permutaciones y filtrar: para las pistas
    "de celda propia" (area, object_on, object_adjacent,
    absolute_position), en cuanto fallan se descarta la rama sin seguir
    explorando. Las pistas relacionales (dependen de otras personas) no
    se pueden comprobar de forma fiable a medias, asi que se verifican
    todas juntas al completar cada colocacion candidata.
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

    def backtrack(row: int, used_cols: set[int], assignment: dict[str, str], remaining: list[str]) -> None:
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

                structured = clue_by_person.get(person_id)
                assignment[person_id] = cell_id
                if (
                    structured is not None
                    and _is_row_local_clue(structured)
                    and not clue_holds(structured, person_id, cell_id, puzzle, assignment)
                ):
                    del assignment[person_id]
                    continue

                new_remaining = [p for p in remaining if p != person_id]
                backtrack(row + 1, used_cols | {col}, assignment, new_remaining)
                del assignment[person_id]

                if len(solutions) >= max_solutions:
                    return

    backtrack(0, set(), {}, person_ids)
    return solutions


def has_unique_solution(puzzle: Puzzle) -> bool:
    return len(find_all_solutions(puzzle, max_solutions=2)) == 1


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
) -> Puzzle:
    """Genera un puzzle completo con solucion unica y asesino identificable.

    Junta los 4 pasos anteriores (colocar personas, geometria+objetos+
    pistas, texto de plantilla, comprobar unicidad). Si un intento sale
    ambiguo o sin asesino determinable, se reintenta desde cero (nueva
    colocacion, nuevas salas, nuevas pistas) hasta `max_attempts` veces.

    Con una sola pista simple por persona (elegida al azar), la
    probabilidad de que un intento salga unico + con asesino
    identificable es baja (puede rondar el 1-5%) -- el cuello de botella
    es la unicidad, no el asesino. Cada intento es muy rapido (sub-
    milisegundo), asi que un limite generoso compensa la baja tasa de
    acierto sin coste real. Si en el futuro esto sigue fallando a
    menudo, la mejora pasa por dar pistas mas restrictivas, no por subir
    aun mas este numero.
    """
    if victim_id not in person_ids:
        raise ValueError(f"victim_id {victim_id!r} not in person_ids")

    if rng is None:
        rng = random.Random()

    for attempt in range(max_attempts):
        placement = generate_placement(rows, cols, person_ids, rng=rng)
        rooms = generate_rooms(rows, cols, area_names, rng=rng)
        cells, clues = assign_clues_and_objects(placement, rooms, rows, cols, rng=rng)

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
