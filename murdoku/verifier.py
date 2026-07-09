import re

from murdoku.schema import Puzzle

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
