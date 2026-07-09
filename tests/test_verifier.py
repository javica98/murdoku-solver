import pytest

from murdoku.schema import Cell, Clue, Grid, Person, Puzzle
from murdoku.verifier import (
    check_no_blocked_cells,
    check_unique_rows_and_cols,
    identify_murderer,
    parse_cell_id,
)


def test_parse_cell_id_extracts_row_and_col():
    assert parse_cell_id("r0c0") == (0, 0)
    assert parse_cell_id("r3c4") == (3, 4)


def test_parse_cell_id_rejects_malformed_id():
    with pytest.raises(ValueError):
        parse_cell_id("A1")


def test_no_violations_when_rows_and_cols_are_all_different():
    solution = {"Bastian": "r0c0", "Vlad": "r1c1"}
    assert check_unique_rows_and_cols(solution) == []


def test_violation_when_two_people_share_a_row():
    # este es literalmente nuestro ejemplo prison_mini_01: valido segun
    # el esquema, pero invalido segun las reglas del juego.
    solution = {"Bastian": "r0c0", "Vlad": "r0c1"}
    violations = check_unique_rows_and_cols(solution)
    assert len(violations) == 1
    assert "row 0" in violations[0]


def test_violation_when_two_people_share_a_column():
    solution = {"Bastian": "r0c0", "Vlad": "r1c0"}
    violations = check_unique_rows_and_cols(solution)
    assert len(violations) == 1
    assert "column 0" in violations[0]


def _puzzle_with_blocked_cell() -> Puzzle:
    return Puzzle(
        id="prison_mini_02",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=3),
        areas={"CELL_A": ["r0c0", "r0c1"]},
        cells={
            "r0c0": Cell(area="CELL_A", objects=["bed"]),
            "r0c1": Cell(area="CELL_A", objects=[]),
            "r0c2": Cell(area=None, objects=["water"], blocked=True),
        },
        people=[
            Person(id="Bastian", role="suspect", clue=Clue(text="He was on a bed.")),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Vlad": "r0c1"},
    )


def test_no_violations_when_nobody_is_on_a_blocked_cell():
    puzzle = _puzzle_with_blocked_cell()
    solution = {"Bastian": "r0c0", "Vlad": "r0c1"}
    assert check_no_blocked_cells(puzzle, solution) == []


def test_violation_when_someone_is_placed_on_a_blocked_cell():
    puzzle = _puzzle_with_blocked_cell()
    solution = {"Bastian": "r0c0", "Vlad": "r0c2"}
    violations = check_no_blocked_cells(puzzle, solution)
    assert len(violations) == 1
    assert "blocked cell r0c2" in violations[0]


def test_violation_when_solution_points_to_an_unknown_cell():
    puzzle = _puzzle_with_blocked_cell()
    solution = {"Bastian": "r0c0", "Vlad": "r9c9"}
    violations = check_no_blocked_cells(puzzle, solution)
    assert len(violations) == 1
    assert "unknown cell r9c9" in violations[0]


def _puzzle_for_murderer_tests() -> Puzzle:
    # ROOM tiene 3 celdas (cabe la victima + 2 sospechosos a la vez).
    # HALL tiene 2 celdas, separadas de ROOM. r0c5 no tiene area.
    return Puzzle(
        id="prison_mini_03",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=6),
        areas={"ROOM": ["r0c0", "r0c1", "r0c2"], "HALL": ["r0c3", "r0c4"]},
        cells={
            "r0c0": Cell(area="ROOM"),
            "r0c1": Cell(area="ROOM"),
            "r0c2": Cell(area="ROOM"),
            "r0c3": Cell(area="HALL"),
            "r0c4": Cell(area="HALL"),
            "r0c5": Cell(area=None),
        },
        people=[
            Person(id="Bastian", role="suspect", clue=Clue(text="...")),
            Person(id="Elena", role="suspect", clue=Clue(text="...")),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c1", "Elena": "r0c3", "Vlad": "r0c0"},
    )


def test_murderer_is_the_only_suspect_in_the_victims_area():
    puzzle = _puzzle_for_murderer_tests()
    solution = {"Bastian": "r0c1", "Elena": "r0c3", "Vlad": "r0c0"}
    assert identify_murderer(puzzle, solution) == "Bastian"


def test_no_murderer_when_two_suspects_share_the_victims_area():
    puzzle = _puzzle_for_murderer_tests()
    solution = {"Bastian": "r0c1", "Elena": "r0c2", "Vlad": "r0c0"}
    assert identify_murderer(puzzle, solution) is None


def test_no_murderer_when_victim_is_alone_in_her_area():
    puzzle = _puzzle_for_murderer_tests()
    solution = {"Bastian": "r0c3", "Elena": "r0c4", "Vlad": "r0c0"}
    assert identify_murderer(puzzle, solution) is None


def test_no_murderer_when_victims_cell_has_no_area():
    puzzle = _puzzle_for_murderer_tests()
    solution = {"Bastian": "r0c0", "Elena": "r0c1", "Vlad": "r0c5"}
    assert identify_murderer(puzzle, solution) is None
