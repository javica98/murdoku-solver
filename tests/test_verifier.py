import pytest

from murdoku.schema import Cell, Clue, Grid, Person, Puzzle
from murdoku.verifier import (
    check_clues_satisfied,
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


def _puzzle_with_bastian_clue(structured: dict | None) -> Puzzle:
    return Puzzle(
        id="prison_mini_04",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=2),
        areas={"CELL_A": ["r0c0"], "CAFETERIA": ["r0c1"]},
        cells={
            "r0c0": Cell(area="CELL_A", objects=["bed"]),
            "r0c1": Cell(area="CAFETERIA"),
        },
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(text="He was in a Cell.", structured=structured),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Vlad": "r0c1"},
    )


def test_no_violation_when_area_clue_matches_placement():
    puzzle = _puzzle_with_bastian_clue({"type": "area", "area": "CELL_A"})
    solution = {"Bastian": "r0c0", "Vlad": "r0c1"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_area_clue_does_not_match_placement():
    puzzle = _puzzle_with_bastian_clue({"type": "area", "area": "CELL_A"})
    solution = {"Bastian": "r0c1", "Vlad": "r0c0"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def test_clue_without_structured_data_is_skipped():
    puzzle = _puzzle_with_bastian_clue(None)
    # Bastian esta en la Cafeteria, contradiciendo el texto de su pista,
    # pero sin "structured" no hay nada que el codigo pueda comprobar.
    solution = {"Bastian": "r0c1", "Vlad": "r0c0"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_unsupported_clue_type_raises():
    puzzle = _puzzle_with_bastian_clue({"type": "not_a_real_type"})
    solution = {"Bastian": "r0c0", "Vlad": "r0c1"}
    with pytest.raises(ValueError):
        check_clues_satisfied(puzzle, solution)


def test_no_violation_when_object_on_clue_matches_placement():
    puzzle = _puzzle_with_bastian_clue({"type": "object_on", "object": "bed"})
    solution = {"Bastian": "r0c0", "Vlad": "r0c1"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_object_on_clue_does_not_match_placement():
    puzzle = _puzzle_with_bastian_clue({"type": "object_on", "object": "bed"})
    solution = {"Bastian": "r0c1", "Vlad": "r0c0"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def _puzzle_3x3_with_bastian_clue(structured: dict | None) -> Puzzle:
    # ROOM cubre las 9 celdas: aqui la esquina/columna "de la sala"
    # coincide con la esquina/columna del tablero completo.
    all_ids = [f"r{row}c{col}" for row in range(3) for col in range(3)]
    cells = {cell_id: Cell(area="ROOM") for cell_id in all_ids}
    return Puzzle(
        id="prison_mini_06",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=3, cols=3),
        areas={"ROOM": all_ids},
        cells=cells,
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(text="...", structured=structured),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Vlad": "r2c2"},
    )


def test_no_violation_when_corner_clue_matches_a_corner_cell():
    puzzle = _puzzle_3x3_with_bastian_clue({"type": "absolute_position", "position": "corner"})
    solution = {"Bastian": "r0c0", "Vlad": "r2c2"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_corner_clue_is_placed_in_the_center():
    puzzle = _puzzle_3x3_with_bastian_clue({"type": "absolute_position", "position": "corner"})
    solution = {"Bastian": "r1c1", "Vlad": "r2c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def test_no_violation_when_last_column_clue_matches():
    puzzle = _puzzle_3x3_with_bastian_clue(
        {"type": "absolute_position", "position": "last_column"}
    )
    solution = {"Bastian": "r1c2", "Vlad": "r2c2"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_last_column_clue_does_not_match():
    puzzle = _puzzle_3x3_with_bastian_clue(
        {"type": "absolute_position", "position": "last_column"}
    )
    solution = {"Bastian": "r1c0", "Vlad": "r2c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def test_unsupported_absolute_position_value_raises():
    puzzle = _puzzle_3x3_with_bastian_clue(
        {"type": "absolute_position", "position": "middle"}
    )
    solution = {"Bastian": "r1c1", "Vlad": "r2c2"}
    with pytest.raises(ValueError):
        check_clues_satisfied(puzzle, solution)


def _puzzle_with_a_middle_row_room() -> Puzzle:
    # MIDDLE_ROOM es una franja de 1x3 en la fila del medio (r1c0..r1c2).
    # Ninguna de sus celdas es esquina del tablero (fila 1 no es ni la
    # primera ni la ultima), pero r1c0 y r1c2 SI son esquinas de esa sala.
    cells = {
        "r0c0": Cell(area=None),
        "r0c1": Cell(area=None),
        "r0c2": Cell(area=None),
        "r1c0": Cell(area="MIDDLE_ROOM"),
        "r1c1": Cell(area="MIDDLE_ROOM"),
        "r1c2": Cell(area="MIDDLE_ROOM"),
        "r2c0": Cell(area=None),
        "r2c1": Cell(area=None),
        "r2c2": Cell(area=None),
    }
    return Puzzle(
        id="prison_mini_07",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=3, cols=3),
        areas={"MIDDLE_ROOM": ["r1c0", "r1c1", "r1c2"]},
        cells=cells,
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(
                    text="...",
                    structured={"type": "absolute_position", "position": "corner"},
                ),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r1c0", "Vlad": "r0c0"},
    )


def test_corner_is_relative_to_the_room_not_the_whole_board():
    puzzle = _puzzle_with_a_middle_row_room()
    # r1c0 no es esquina del tablero (fila 1 no es la primera ni la
    # ultima), pero SI es esquina de MIDDLE_ROOM.
    solution = {"Bastian": "r1c0", "Vlad": "r0c0"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_middle_of_the_room_is_not_a_corner_even_if_not_center_of_board():
    puzzle = _puzzle_with_a_middle_row_room()
    solution = {"Bastian": "r1c1", "Vlad": "r0c0"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]
