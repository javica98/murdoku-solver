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


def _puzzle_with_shelf_at_r0c1(bastian_cell_id: str) -> Puzzle:
    # tablero 1x3, una sola sala. La estanteria esta en r0c1: r0c0 y r0c2
    # son "beside" ella; r0c1 (la propia celda del estante) no lo es.
    return Puzzle(
        id="prison_mini_08",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=3),
        areas={"ROOM": ["r0c0", "r0c1", "r0c2"]},
        cells={
            "r0c0": Cell(area="ROOM"),
            "r0c1": Cell(area="ROOM", objects=["shelf"]),
            "r0c2": Cell(area="ROOM"),
        },
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(
                    text="He was beside a shelf.",
                    structured={"type": "object_adjacent", "object": "shelf"},
                ),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": bastian_cell_id, "Vlad": "r0c2"},
    )


def test_no_violation_when_beside_the_shelf():
    puzzle = _puzzle_with_shelf_at_r0c1("r0c0")
    solution = {"Bastian": "r0c0", "Vlad": "r0c2"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_on_the_shelfs_own_cell_not_beside_it():
    puzzle = _puzzle_with_shelf_at_r0c1("r0c1")
    solution = {"Bastian": "r0c1", "Vlad": "r0c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def test_no_violation_when_adjacent_object_is_in_a_different_area():
    # "beside" es solo geometria: no importa si el objeto vecino esta
    # en otra sala.
    puzzle = Puzzle(
        id="prison_mini_09",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=2),
        areas={"ROOM_A": ["r0c0"], "ROOM_B": ["r0c1"]},
        cells={
            "r0c0": Cell(area="ROOM_A"),
            "r0c1": Cell(area="ROOM_B", objects=["shelf"]),
        },
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(
                    text="He was beside a shelf.",
                    structured={"type": "object_adjacent", "object": "shelf"},
                ),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Vlad": "r0c1"},
    )
    solution = {"Bastian": "r0c0", "Vlad": "r0c1"}
    assert check_clues_satisfied(puzzle, solution) == []


def _puzzle_for_empty_neighbor_tests() -> Puzzle:
    # 1x3: r0c0 solo tiene un vecino ortogonal posible, r0c1.
    return Puzzle(
        id="prison_mini_10",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=3),
        areas={"ROOM": ["r0c0", "r0c1", "r0c2"]},
        cells={
            "r0c0": Cell(area="ROOM"),
            "r0c1": Cell(area="ROOM"),
            "r0c2": Cell(area="ROOM"),
        },
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(
                    text="There was an empty cell beside his.",
                    structured={"type": "empty_neighbor"},
                ),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Vlad": "r0c2"},
    )


def test_no_violation_when_a_neighbor_cell_is_empty():
    puzzle = _puzzle_for_empty_neighbor_tests()
    # r0c1 (el unico vecino de r0c0) esta vacio.
    solution = {"Bastian": "r0c0", "Vlad": "r0c2"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_the_only_neighbor_is_occupied():
    puzzle = _puzzle_for_empty_neighbor_tests()
    # ahora Vlad ocupa el unico vecino de Bastian.
    solution = {"Bastian": "r0c0", "Vlad": "r0c1"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def _puzzle_for_alone_tests() -> Puzzle:
    # ROOM = r0c0,r0c1 (2 celdas). HALL = r0c2,r0c3 (2 celdas).
    return Puzzle(
        id="prison_mini_11",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=4),
        areas={"ROOM": ["r0c0", "r0c1"], "HALL": ["r0c2", "r0c3"]},
        cells={
            "r0c0": Cell(area="ROOM"),
            "r0c1": Cell(area="ROOM"),
            "r0c2": Cell(area="HALL"),
            "r0c3": Cell(area="HALL"),
        },
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(
                    text="He was alone in his cell.",
                    structured={"type": "relational_person", "relation": "alone"},
                ),
            ),
            Person(id="Elena", role="suspect", clue=Clue(text="...")),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Elena": "r0c2", "Vlad": "r0c3"},
    )


def test_no_violation_when_alone_in_own_area():
    puzzle = _puzzle_for_alone_tests()
    solution = {"Bastian": "r0c0", "Elena": "r0c2", "Vlad": "r0c3"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_not_alone_in_own_area():
    puzzle = _puzzle_for_alone_tests()
    # Elena se muda a ROOM, con Bastian.
    solution = {"Bastian": "r0c0", "Elena": "r0c1", "Vlad": "r0c3"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def test_unsupported_relational_person_relation_raises():
    puzzle = _puzzle_for_alone_tests()
    puzzle.people[0].clue.structured = {"type": "relational_person", "relation": "married"}
    solution = {"Bastian": "r0c0", "Elena": "r0c2", "Vlad": "r0c3"}
    with pytest.raises(ValueError):
        check_clues_satisfied(puzzle, solution)


def _puzzle_for_attribute_tests(structured: dict, roommate_attributes: dict) -> Puzzle:
    # ROOM = r0c0 (Bastian), r0c1 (Roommate). HALL = r0c2 (Vlad).
    return Puzzle(
        id="prison_mini_12",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=3),
        areas={"ROOM": ["r0c0", "r0c1"], "HALL": ["r0c2"]},
        cells={
            "r0c0": Cell(area="ROOM"),
            "r0c1": Cell(area="ROOM"),
            "r0c2": Cell(area="HALL"),
        },
        people=[
            Person(
                id="Bastian",
                role="suspect",
                clue=Clue(text="...", structured=structured),
            ),
            Person(
                id="Roommate",
                role="suspect",
                clue=Clue(text="..."),
                attributes=roommate_attributes,
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Roommate": "r0c1", "Vlad": "r0c2"},
    )


def test_no_violation_when_no_one_with_beard_in_room():
    structured = {
        "type": "relational_attribute",
        "relation": "none_with",
        "attribute": "beard",
        "value": True,
    }
    puzzle = _puzzle_for_attribute_tests(structured, roommate_attributes={"beard": False})
    solution = {"Bastian": "r0c0", "Roommate": "r0c1", "Vlad": "r0c2"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_someone_with_beard_in_room():
    structured = {
        "type": "relational_attribute",
        "relation": "none_with",
        "attribute": "beard",
        "value": True,
    }
    puzzle = _puzzle_for_attribute_tests(structured, roommate_attributes={"beard": True})
    solution = {"Bastian": "r0c0", "Roommate": "r0c1", "Vlad": "r0c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def test_no_violation_when_with_another_woman():
    structured = {
        "type": "relational_attribute",
        "relation": "with_another",
        "attribute": "gender",
        "value": "female",
    }
    puzzle = _puzzle_for_attribute_tests(structured, roommate_attributes={"gender": "female"})
    solution = {"Bastian": "r0c0", "Roommate": "r0c1", "Vlad": "r0c2"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_not_with_another_woman():
    structured = {
        "type": "relational_attribute",
        "relation": "with_another",
        "attribute": "gender",
        "value": "female",
    }
    puzzle = _puzzle_for_attribute_tests(structured, roommate_attributes={"gender": "male"})
    solution = {"Bastian": "r0c0", "Roommate": "r0c1", "Vlad": "r0c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Bastian's clue is not satisfied" in violations[0]


def test_unsupported_relational_attribute_relation_raises():
    structured = {
        "type": "relational_attribute",
        "relation": "same_zodiac_sign",
        "attribute": "gender",
        "value": "female",
    }
    puzzle = _puzzle_for_attribute_tests(structured, roommate_attributes={"gender": "female"})
    solution = {"Bastian": "r0c0", "Roommate": "r0c1", "Vlad": "r0c2"}
    with pytest.raises(ValueError):
        check_clues_satisfied(puzzle, solution)


def _puzzle_for_relative_position_tests(brigitte_structured: dict) -> Puzzle:
    # grid 3x2, sin salas (no hacen falta para este tipo). Cameron fija en r0c0.
    cells = {
        f"r{row}c{col}": Cell(area=None) for row in range(3) for col in range(2)
    }
    return Puzzle(
        id="book_club_relative_01",
        scenario="El club de lectura",
        difficulty="easy",
        grid=Grid(rows=3, cols=2),
        areas={},
        cells=cells,
        people=[
            Person(id="Cameron", role="suspect", clue=Clue(text="...")),
            Person(
                id="Brigitte",
                role="suspect",
                clue=Clue(text="...", structured=brigitte_structured),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Cameron": "r0c0", "Brigitte": "r1c1", "Vlad": "r2c0"},
    )


def test_no_violation_when_south_of_reference_in_a_different_column():
    structured = {"type": "relative_to_person", "reference": "Cameron", "direction": "south"}
    puzzle = _puzzle_for_relative_position_tests(structured)
    # Brigitte en r1c1: fila mayor que Cameron (r0), columna distinta.
    solution = {"Cameron": "r0c0", "Brigitte": "r1c1", "Vlad": "r2c0"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_same_row_as_reference():
    structured = {"type": "relative_to_person", "reference": "Cameron", "direction": "south"}
    puzzle = _puzzle_for_relative_position_tests(structured)
    solution = {"Cameron": "r0c0", "Brigitte": "r0c1", "Vlad": "r2c0"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Brigitte's clue is not satisfied" in violations[0]


def test_north_of_reference_holds_with_no_exact_distance():
    structured = {"type": "relative_to_person", "reference": "Vlad", "direction": "north"}
    puzzle = _puzzle_for_relative_position_tests(structured)
    # Brigitte en r1c1: fila menor que Vlad (r2) -> al norte, sin exigir distancia exacta.
    solution = {"Cameron": "r0c0", "Brigitte": "r1c1", "Vlad": "r2c0"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_exact_distance_holds_only_at_the_right_offset():
    structured = {
        "type": "relative_to_person", "reference": "Cameron", "direction": "south", "distance": 1,
    }
    puzzle = _puzzle_for_relative_position_tests(structured)
    # Brigitte en r1c1: exactamente 1 fila al sur de Cameron (r0) -> cumple.
    solution = {"Cameron": "r0c0", "Brigitte": "r1c1", "Vlad": "r2c0"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_exact_distance_fails_at_the_wrong_offset():
    structured = {
        "type": "relative_to_person", "reference": "Cameron", "direction": "south", "distance": 2,
    }
    puzzle = _puzzle_for_relative_position_tests(structured)
    # Brigitte en r1c1: solo 1 fila al sur de Cameron, no 2 -> no cumple.
    solution = {"Cameron": "r0c0", "Brigitte": "r1c1", "Vlad": "r2c0"}
    assert len(check_clues_satisfied(puzzle, solution)) == 1


def test_unsupported_relative_to_person_direction_raises():
    structured = {"type": "relative_to_person", "reference": "Cameron", "direction": "diagonal"}
    puzzle = _puzzle_for_relative_position_tests(structured)
    solution = {"Cameron": "r0c0", "Brigitte": "r1c1", "Vlad": "r2c0"}
    with pytest.raises(ValueError):
        check_clues_satisfied(puzzle, solution)


def test_relative_to_object_holds_when_object_is_unique_on_board():
    cells = {f"r{row}c{col}": Cell(area=None) for row in range(3) for col in range(2)}
    cells["r0c0"].objects = ["planta"]
    puzzle = Puzzle(
        id="relative_to_object_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=3, cols=2),
        areas={},
        cells=cells,
        people=[
            Person(
                id="Brigitte",
                role="suspect",
                clue=Clue(
                    text="...",
                    structured={
                        "type": "relative_to_object", "object": "planta", "direction": "south", "distance": 1,
                    },
                ),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Brigitte": "r1c1", "Vlad": "r2c0"},
    )
    assert check_clues_satisfied(puzzle, {"Brigitte": "r1c1", "Vlad": "r2c0"}) == []


def test_relative_to_object_fails_when_object_is_not_unique_on_board():
    cells = {f"r{row}c{col}": Cell(area=None) for row in range(3) for col in range(2)}
    cells["r0c0"].objects = ["planta"]
    cells["r0c1"].objects = ["planta"]
    puzzle = Puzzle(
        id="relative_to_object_ambiguous_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=3, cols=2),
        areas={},
        cells=cells,
        people=[
            Person(
                id="Brigitte",
                role="suspect",
                clue=Clue(
                    text="...",
                    structured={
                        "type": "relative_to_object", "object": "planta", "direction": "south", "distance": 1,
                    },
                ),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Brigitte": "r1c1", "Vlad": "r2c0"},
    )
    assert len(check_clues_satisfied(puzzle, {"Brigitte": "r1c1", "Vlad": "r2c0"})) == 1


def _puzzle_for_unique_object_tests() -> Puzzle:
    # r0c0 y r0c1 tienen "silla"; r0c2 no tiene nada.
    # r0c0 y r0c1 tienen "silla"; r0c2 y r0c3 no tienen nada. 3 personas,
    # 4 celdas: asi "solo Darlene en una silla" es posible de verdad.
    return Puzzle(
        id="book_club_unique_01",
        scenario="El club de lectura",
        difficulty="easy",
        grid=Grid(rows=1, cols=4),
        areas={},
        cells={
            "r0c0": Cell(area=None, objects=["silla"]),
            "r0c1": Cell(area=None, objects=["silla"]),
            "r0c2": Cell(area=None, objects=[]),
            "r0c3": Cell(area=None, objects=[]),
        },
        people=[
            Person(
                id="Darlene",
                role="suspect",
                clue=Clue(
                    text="Era la unica persona sentada en una silla.",
                    structured={"type": "unique_object_on", "object": "silla"},
                ),
            ),
            Person(id="Other", role="suspect", clue=Clue(text="...")),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Darlene": "r0c0", "Other": "r0c2", "Vlad": "r0c3"},
    )


def test_no_violation_when_only_darlene_is_on_a_chair():
    puzzle = _puzzle_for_unique_object_tests()
    solution = {"Darlene": "r0c0", "Other": "r0c2", "Vlad": "r0c3"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_someone_else_is_also_on_a_chair():
    puzzle = _puzzle_for_unique_object_tests()
    solution = {"Darlene": "r0c0", "Other": "r0c1", "Vlad": "r0c3"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Darlene's clue is not satisfied" in violations[0]


def test_violation_when_darlene_herself_is_not_on_a_chair():
    puzzle = _puzzle_for_unique_object_tests()
    solution = {"Darlene": "r0c2", "Other": "r0c3", "Vlad": "r0c0"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Darlene's clue is not satisfied" in violations[0]


def _puzzle_for_compound_clue_tests() -> Puzzle:
    # BIBLIOTECA: r0c0(sin obj), r0c1(estanteria), r0c2(sin obj, junto al
    # estante), r0c3(sin obj, NO junto al estante). OTHER: r0c4.
    edison_structured = {
        "type": "all",
        "clauses": [
            {"type": "area", "area": "BIBLIOTECA"},
            {"type": "object_adjacent", "object": "estanteria", "negate": True},
        ],
    }
    return Puzzle(
        id="book_club_compound_01",
        scenario="El club de lectura",
        difficulty="easy",
        grid=Grid(rows=1, cols=5),
        areas={
            "BIBLIOTECA": ["r0c0", "r0c1", "r0c2", "r0c3"],
            "OTHER": ["r0c4"],
        },
        cells={
            "r0c0": Cell(area="BIBLIOTECA"),
            "r0c1": Cell(area="BIBLIOTECA", objects=["estanteria"]),
            "r0c2": Cell(area="BIBLIOTECA"),
            "r0c3": Cell(area="BIBLIOTECA"),
            "r0c4": Cell(area="OTHER"),
        },
        people=[
            Person(
                id="Edison",
                role="suspect",
                clue=Clue(text="...", structured=edison_structured),
            ),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Edison": "r0c3", "Vlad": "r0c4"},
    )


def test_no_violation_when_in_library_and_not_beside_the_shelf():
    puzzle = _puzzle_for_compound_clue_tests()
    solution = {"Edison": "r0c3", "Vlad": "r0c4"}
    assert check_clues_satisfied(puzzle, solution) == []


def test_violation_when_in_library_but_beside_the_shelf():
    puzzle = _puzzle_for_compound_clue_tests()
    solution = {"Edison": "r0c2", "Vlad": "r0c4"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Edison's clue is not satisfied" in violations[0]


def test_violation_when_not_even_in_the_library():
    puzzle = _puzzle_for_compound_clue_tests()
    solution = {"Edison": "r0c4", "Vlad": "r0c3"}
    violations = check_clues_satisfied(puzzle, solution)
    assert len(violations) == 1
    assert "Edison's clue is not satisfied" in violations[0]


def _puzzle_for_any_and_with_person_tests(diana_structured: dict, aaron_structured: dict) -> Puzzle:
    # 1x4: r0c0/r0c1 = DORMITORIO, r0c2 = PORCHE, r0c3 = COCINA.
    return Puzzle(
        id="backyard_any_01",
        scenario="El jardin trasero",
        difficulty="medium",
        grid=Grid(rows=1, cols=4),
        areas={
            "DORMITORIO": ["r0c0", "r0c1"],
            "PORCHE": ["r0c2"],
            "COCINA": ["r0c3"],
        },
        cells={
            "r0c0": Cell(area="DORMITORIO"),
            "r0c1": Cell(area="DORMITORIO"),
            "r0c2": Cell(area="PORCHE"),
            "r0c3": Cell(area="COCINA"),
        },
        people=[
            Person(id="Diana", role="suspect", clue=Clue(text="...", structured=diana_structured)),
            Person(id="Aaron", role="suspect", clue=Clue(text="...", structured=aaron_structured)),
            Person(id="Elena", role="suspect", clue=Clue(text="...")),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Diana": "r0c0", "Aaron": "r0c1", "Elena": "r0c2", "Vlad": "r0c3"},
    )


_ANY_CLAUSES = {
    "type": "any",
    "clauses": [
        {"type": "area", "area": "DORMITORIO"},
        {"type": "area", "area": "PORCHE"},
    ],
}
_WITH_PERSON_CLAUSE = {"type": "with_person", "reference": "Elena"}


def test_any_is_satisfied_by_the_first_clause():
    puzzle = _puzzle_for_any_and_with_person_tests(_ANY_CLAUSES, _WITH_PERSON_CLAUSE)
    # Diana en DORMITORIO (r0c0): cumple la primera clausula del "any".
    solution = {"Diana": "r0c0", "Aaron": "r0c1", "Elena": "r0c2", "Vlad": "r0c3"}
    violations = check_clues_satisfied(puzzle, solution)
    assert not any("Diana's clue is not satisfied" in v for v in violations)


def test_any_is_satisfied_by_the_second_clause():
    puzzle = _puzzle_for_any_and_with_person_tests(_ANY_CLAUSES, _WITH_PERSON_CLAUSE)
    # Diana en PORCHE (r0c2): cumple la segunda clausula del "any".
    solution = {"Diana": "r0c2", "Aaron": "r0c0", "Elena": "r0c1", "Vlad": "r0c3"}
    violations = check_clues_satisfied(puzzle, solution)
    assert not any("Diana's clue is not satisfied" in v for v in violations)


def test_any_fails_when_neither_clause_holds():
    puzzle = _puzzle_for_any_and_with_person_tests(_ANY_CLAUSES, _WITH_PERSON_CLAUSE)
    solution = {"Diana": "r0c3", "Aaron": "r0c0", "Elena": "r0c1", "Vlad": "r0c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert any("Diana's clue is not satisfied" in v for v in violations)


def test_with_person_holds_when_same_area_as_reference():
    puzzle = _puzzle_for_any_and_with_person_tests(_ANY_CLAUSES, _WITH_PERSON_CLAUSE)
    solution = {"Diana": "r0c3", "Aaron": "r0c0", "Elena": "r0c1", "Vlad": "r0c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert not any("Aaron's clue is not satisfied" in v for v in violations)


def test_with_person_fails_when_different_area_from_reference():
    puzzle = _puzzle_for_any_and_with_person_tests(_ANY_CLAUSES, _WITH_PERSON_CLAUSE)
    solution = {"Diana": "r0c0", "Aaron": "r0c3", "Elena": "r0c1", "Vlad": "r0c2"}
    violations = check_clues_satisfied(puzzle, solution)
    assert any("Aaron's clue is not satisfied" in v for v in violations)
