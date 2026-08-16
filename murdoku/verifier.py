import re
from typing import Any

from murdoku.schema import Cell, Person, Puzzle

_CELL_ID_RE = re.compile(r"^r(\d+)c(\d+)$")


def parse_cell_id(cell_id: str) -> tuple[int, int]:
    match = _CELL_ID_RE.match(cell_id)
    if match is None:
        raise ValueError(f"not a valid cell id: {cell_id!r}")
    return int(match.group(1)), int(match.group(2))


def check_unique_rows_and_cols(solution: dict[str, str]) -> list[str]:
    violations: list[str] = []
    person_in_row: dict[int, str] = {}
    person_in_col: dict[int, str] = {}

    for person_id, cell_id in solution.items():
        row, col = parse_cell_id(cell_id)

        if row in person_in_row:
            violations.append(
                f"{person_id} shares row {row} with {person_in_row[row]}"
            )
        else:
            person_in_row[row] = person_id

        if col in person_in_col:
            violations.append(
                f"{person_id} shares column {col} with {person_in_col[col]}"
            )
        else:
            person_in_col[col] = person_id

    return violations


def check_no_blocked_cells(puzzle: Puzzle, solution: dict[str, str]) -> list[str]:
    violations: list[str] = []

    for person_id, cell_id in solution.items():
        cell = puzzle.cells.get(cell_id)
        if cell is None:
            violations.append(f"{person_id} is placed on unknown cell {cell_id}")
        elif cell.blocked:
            violations.append(f"{person_id} is placed on blocked cell {cell_id}")

    return violations


def find_victim_id(puzzle: Puzzle) -> str:
    for person in puzzle.people:
        if person.role == "victim":
            return person.id
    raise ValueError("puzzle has no victim")


def find_person(puzzle: Puzzle, person_id: str) -> Person:
    for person in puzzle.people:
        if person.id == person_id:
            return person
    raise ValueError(f"puzzle has no person with id {person_id!r}")


def people_in_area(puzzle: Puzzle, solution: dict[str, str], area: str) -> list[str]:
    people_here = []
    for person_id, cell_id in solution.items():
        cell = puzzle.cells.get(cell_id)
        if cell is not None and cell.area == area:
            people_here.append(person_id)
    return people_here


def identify_murderer(puzzle: Puzzle, solution: dict[str, str]) -> str | None:
    victim_id = find_victim_id(puzzle)
    victim_cell_id = solution.get(victim_id)
    if victim_cell_id is None:
        return None

    victim_cell = puzzle.cells.get(victim_cell_id)
    if victim_cell is None or victim_cell.area is None:
        return None

    suspects_with_victim = [
        person_id
        for person_id in people_in_area(puzzle, solution, victim_cell.area)
        if person_id != victim_id
    ]

    if len(suspects_with_victim) == 1:
        return suspects_with_victim[0]
    return None


def area_bounding_box(cells: dict[str, Cell], area: str) -> tuple[int, int, int, int]:
    """Fila/columna minima y maxima de las celdas que pertenecen a `area`.

    Toma el dict de celdas directamente (no un Puzzle completo) para que
    el generador tambien pueda reusarla mientras todavia esta construyendo
    el puzzle, antes de tener un Puzzle valido.

    Asume que la sala es mas o menos rectangular. Si tiene forma de L,
    esto puede marcar como "esquina" alguna celda que visualmente no lo es.
    """
    rows = []
    cols = []
    for cell_id, area_cell in cells.items():
        if area_cell.area == area:
            r, c = parse_cell_id(cell_id)
            rows.append(r)
            cols.append(c)
    return min(rows), max(rows), min(cols), max(cols)


def _orthogonal_neighbors(row: int, col: int) -> list[tuple[int, int]]:
    return [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]


def _matches_direction_distance(
    row: int, col: int, anchor_row: int, anchor_col: int, direction: str, distance: int | None
) -> bool:
    """Si `distance` es None, es la semantica antigua/mas debil ("en algun
    punto en esa direccion", sin fijar el eje contrario) -- se mantiene
    por los puzzles reales transcritos que usan esta pista sin distancia
    exacta. Si `distance` es un numero, exige esa distancia EXACTA en el
    eje correspondiente (el otro eje queda libre).
    """
    if direction == "north":
        return row < anchor_row if distance is None else row == anchor_row - distance
    if direction == "south":
        return row > anchor_row if distance is None else row == anchor_row + distance
    if direction == "west":
        return col < anchor_col if distance is None else col == anchor_col - distance
    if direction == "east":
        return col > anchor_col if distance is None else col == anchor_col + distance
    raise ValueError(f"unsupported direction: {direction!r}")


def _find_unique_object_cell(cells: dict[str, Cell], obj: str) -> str | None:
    """La celda donde esta `obj`, solo si aparece en una UNICA celda de
    todo el tablero -- si no, anclar una distancia a el seria ambiguo.
    """
    matches = [cell_id for cell_id, cell in cells.items() if obj in cell.objects]
    return matches[0] if len(matches) == 1 else None


def clue_holds(
    structured: dict[str, Any],
    person_id: str,
    cell_id: str,
    puzzle: Puzzle,
    solution: dict[str, str],
) -> bool:
    """Si una pista se cumple, incluyendo su propio "negate" si lo lleva.

    Es un envoltorio fino sobre `evaluate_clue_positive`: calcula el hecho
    "en positivo" y lo invierte una sola vez si `structured` lleva
    `"negate": true` -- sea esta la pista de nivel superior de una
    persona, o una clausula dentro de un "all"/"any". Antes `negate` solo
    se comprobaba dentro de esos combinadores, asi que una pista negada
    SUELTA (sin combinador alrededor) nunca se invertia.
    """
    result = evaluate_clue_positive(structured, person_id, cell_id, puzzle, solution)
    return not result if structured.get("negate") else result


def evaluate_clue_positive(
    structured: dict[str, Any],
    person_id: str,
    cell_id: str,
    puzzle: Puzzle,
    solution: dict[str, str],
) -> bool:
    """El hecho "en positivo" de una pista, sin mirar su propio "negate"
    (eso es responsabilidad exclusiva de `clue_holds`). Las clausulas de
    "all"/"any" SI pasan por `clue_holds` de forma recursiva, para que la
    negacion de cada una se aplique exactamente una vez.
    """
    cell = puzzle.cells[cell_id]
    row, col = parse_cell_id(cell_id)
    clue_type = structured.get("type")

    if clue_type == "all":
        return all(
            clue_holds(clause, person_id, cell_id, puzzle, solution)
            for clause in structured.get("clauses", [])
        )

    if clue_type == "any":
        return any(
            clue_holds(clause, person_id, cell_id, puzzle, solution)
            for clause in structured.get("clauses", [])
        )

    if clue_type == "area":
        return cell.area == structured.get("area")

    if clue_type == "object_on":
        return structured.get("object") in cell.objects

    if clue_type == "with_person":
        reference_id = structured.get("reference")
        reference_cell_id = solution.get(reference_id)
        if reference_cell_id is None:
            return False
        reference_cell = puzzle.cells.get(reference_cell_id)
        if reference_cell is None or reference_cell.area is None:
            return False
        return cell.area == reference_cell.area

    if clue_type == "absolute_position":
        position = structured.get("position")

        if cell.area is None:
            return False

        min_row, max_row, min_col, max_col = area_bounding_box(puzzle.cells, cell.area)

        if position == "corner":
            is_edge_row = row in (min_row, max_row)
            is_edge_col = col in (min_col, max_col)
            return is_edge_row and is_edge_col

        if position == "last_column":
            return col == max_col

        raise ValueError(f"unsupported absolute_position value: {position!r}")

    if clue_type == "object_adjacent":
        # "beside" = arriba, abajo, izquierda o derecha. No importa si la
        # celda vecina pertenece a otra area (ver nota en el roadmap).
        target_object = structured.get("object")
        for n_row, n_col in _orthogonal_neighbors(row, col):
            neighbor = puzzle.cells.get(f"r{n_row}c{n_col}")
            if neighbor is None:
                continue
            if target_object in neighbor.objects:
                return True
        return False

    if clue_type == "empty_neighbor":
        occupied_cells = set(solution.values())
        for n_row, n_col in _orthogonal_neighbors(row, col):
            neighbor_id = f"r{n_row}c{n_col}"
            if neighbor_id in puzzle.cells and neighbor_id not in occupied_cells:
                return True
        return False

    if clue_type == "relational_person":
        relation = structured.get("relation")

        if relation == "alone":
            if cell.area is None:
                return False
            others = [
                pid
                for pid in people_in_area(puzzle, solution, cell.area)
                if pid != person_id
            ]
            return len(others) == 0

        raise ValueError(f"unsupported relational_person relation: {relation!r}")

    if clue_type == "relational_attribute":
        relation = structured.get("relation")
        attribute = structured.get("attribute")
        value = structured.get("value")

        if cell.area is None:
            return False

        other_ids = [
            pid
            for pid in people_in_area(puzzle, solution, cell.area)
            if pid != person_id
        ]
        others_have_it = any(
            find_person(puzzle, pid).attributes.get(attribute) == value
            for pid in other_ids
        )

        if relation == "none_with":
            return not others_have_it

        if relation == "with_another":
            return others_have_it

        raise ValueError(f"unsupported relational_attribute relation: {relation!r}")

    if clue_type == "relative_to_person":
        reference_id = structured.get("reference")
        direction = structured.get("direction")
        distance = structured.get("distance")

        reference_cell_id = solution.get(reference_id)
        if reference_cell_id is None:
            return False
        reference_row, reference_col = parse_cell_id(reference_cell_id)

        return _matches_direction_distance(row, col, reference_row, reference_col, direction, distance)

    if clue_type == "relative_to_object":
        target_object = structured.get("object")
        direction = structured.get("direction")
        distance = structured.get("distance")

        anchor_cell_id = _find_unique_object_cell(puzzle.cells, target_object)
        if anchor_cell_id is None:
            return False
        anchor_row, anchor_col = parse_cell_id(anchor_cell_id)

        return _matches_direction_distance(row, col, anchor_row, anchor_col, direction, distance)

    if clue_type == "unique_object_on":
        target_object = structured.get("object")
        if target_object not in cell.objects:
            return False

        for other_id, other_cell_id in solution.items():
            if other_id == person_id:
                continue
            other_cell = puzzle.cells.get(other_cell_id)
            if other_cell is not None and target_object in other_cell.objects:
                return False

        return True

    raise ValueError(f"unsupported clue type: {clue_type!r}")


def check_clues_satisfied(puzzle: Puzzle, solution: dict[str, str]) -> list[str]:
    violations: list[str] = []

    for person in puzzle.people:
        if person.clue is None or person.clue.structured is None:
            continue

        cell_id = solution.get(person.id)
        if cell_id is None or cell_id not in puzzle.cells:
            violations.append(f"{person.id} has no valid placement to check their clue")
            continue

        if not clue_holds(person.clue.structured, person.id, cell_id, puzzle, solution):
            violations.append(f"{person.id}'s clue is not satisfied at {cell_id}")

    return violations
