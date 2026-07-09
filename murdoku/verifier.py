import re
from typing import Any

from murdoku.schema import Person, Puzzle

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


def _area_bounding_box(puzzle: Puzzle, area: str) -> tuple[int, int, int, int]:
    """Fila/columna minima y maxima de las celdas que pertenecen a `area`.

    Asume que la sala es mas o menos rectangular. Si tiene forma de L,
    esto puede marcar como "esquina" alguna celda que visualmente no lo es.
    """
    rows = []
    cols = []
    for cell_id, area_cell in puzzle.cells.items():
        if area_cell.area == area:
            r, c = parse_cell_id(cell_id)
            rows.append(r)
            cols.append(c)
    return min(rows), max(rows), min(cols), max(cols)


def _orthogonal_neighbors(row: int, col: int) -> list[tuple[int, int]]:
    return [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]


def _clue_holds(
    structured: dict[str, Any],
    person_id: str,
    cell_id: str,
    puzzle: Puzzle,
    solution: dict[str, str],
) -> bool:
    cell = puzzle.cells[cell_id]
    row, col = parse_cell_id(cell_id)
    clue_type = structured.get("type")

    if clue_type == "all":
        for clause in structured.get("clauses", []):
            result = _clue_holds(clause, person_id, cell_id, puzzle, solution)
            if clause.get("negate"):
                result = not result
            if not result:
                return False
        return True

    if clue_type == "area":
        return cell.area == structured.get("area")

    if clue_type == "object_on":
        return structured.get("object") in cell.objects

    if clue_type == "absolute_position":
        position = structured.get("position")

        if cell.area is None:
            return False

        min_row, max_row, min_col, max_col = _area_bounding_box(puzzle, cell.area)

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

        reference_cell_id = solution.get(reference_id)
        if reference_cell_id is None:
            return False
        reference_row, _ = parse_cell_id(reference_cell_id)

        if direction == "south":
            return row > reference_row

        raise ValueError(f"unsupported relative_to_person direction: {direction!r}")

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

        if not _clue_holds(person.clue.structured, person.id, cell_id, puzzle, solution):
            violations.append(f"{person.id}'s clue is not satisfied at {cell_id}")

    return violations
