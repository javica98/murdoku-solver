import json
import sys

from murdoku.schema import Puzzle
from murdoku.verifier import (
    check_clues_satisfied,
    check_no_blocked_cells,
    check_unique_rows_and_cols,
    identify_murderer,
)


def main(path: str, solution_path: str | None = None) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    puzzle = Puzzle.model_validate(data)

    if solution_path is None:
        solution = puzzle.solution
    else:
        with open(solution_path, encoding="utf-8") as f:
            solution = json.load(f)

    violations = (
        check_unique_rows_and_cols(solution)
        + check_no_blocked_cells(puzzle, solution)
        + check_clues_satisfied(puzzle, solution)
    )

    if violations:
        print("Solucion INVALIDA:")
        for violation in violations:
            print(f"  - {violation}")
    else:
        print("Solucion valida: todas las reglas se cumplen.")

    murderer = identify_murderer(puzzle, solution)
    print(f"Asesino identificado: {murderer}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
