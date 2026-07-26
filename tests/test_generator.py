import random
from unittest.mock import Mock

import pytest

from murdoku.generator import (
    NON_BLOCKING_OBJECTS,
    assign_clues_and_objects,
    find_all_solutions,
    generate_placement,
    generate_puzzle,
    generate_rooms,
    has_unique_solution,
    render_clue_template,
    reword_with_llm,
)
from murdoku.schema import Cell, Clue, Grid, Person, Puzzle
from murdoku.verifier import (
    check_clues_satisfied,
    check_no_blocked_cells,
    check_unique_rows_and_cols,
    identify_murderer,
    parse_cell_id,
)


def _cells_by_area(cells: dict) -> dict:
    by_area: dict = {}
    for cell_id, cell in cells.items():
        by_area.setdefault(cell.area, set()).add(cell_id)
    return by_area


def _is_connected(cell_ids: set) -> bool:
    """BFS: desde una celda cualquiera, ¿se llega a todas las demas
    moviendose solo arriba/abajo/izquierda/derecha?"""
    remaining = set(cell_ids)
    start = next(iter(remaining))
    visited = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        row, col = parse_cell_id(current)
        for r, c in [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]:
            neighbor = f"r{r}c{c}"
            if neighbor in remaining and neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    return visited == remaining


def test_placement_has_one_cell_per_person():
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=random.Random(0))
    assert set(placement.keys()) == set(people)


def test_placement_respects_unique_rows_and_cols():
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=random.Random(1))
    assert check_unique_rows_and_cols(placement) == []


def test_placement_uses_every_row_and_column_exactly_once():
    people = [f"P{i}" for i in range(9)]
    placement = generate_placement(9, 9, people, rng=random.Random(2))
    rows = {parse_cell_id(cell_id)[0] for cell_id in placement.values()}
    cols = {parse_cell_id(cell_id)[1] for cell_id in placement.values()}
    assert rows == set(range(9))
    assert cols == set(range(9))


def test_placement_is_reproducible_with_the_same_seed():
    people = ["Ada", "Bruno", "Carmen"]
    placement_a = generate_placement(3, 3, people, rng=random.Random(42))
    placement_b = generate_placement(3, 3, people, rng=random.Random(42))
    assert placement_a == placement_b


def test_rejects_non_square_grid():
    with pytest.raises(ValueError):
        generate_placement(3, 4, ["Ada", "Bruno", "Carmen"])


def test_rejects_wrong_number_of_people():
    with pytest.raises(ValueError):
        generate_placement(3, 3, ["Ada", "Bruno"])


def test_rooms_cover_every_cell_exactly_once():
    cells = generate_rooms(6, 6, ["A", "B", "C"], rng=random.Random(0))
    assert set(cells.keys()) == {f"r{r}c{c}" for r in range(6) for c in range(6)}


def test_rooms_use_exactly_the_given_area_names():
    cells = generate_rooms(6, 6, ["A", "B", "C"], rng=random.Random(0))
    assert {cell.area for cell in cells.values()} == {"A", "B", "C"}


def test_each_room_is_a_single_connected_piece():
    cells = generate_rooms(9, 9, ["A", "B", "C", "D"], rng=random.Random(7))
    for area, cell_ids in _cells_by_area(cells).items():
        assert _is_connected(cell_ids), f"area {area} is split into disconnected pieces"


def test_rooms_are_reproducible_with_the_same_seed():
    cells_a = generate_rooms(6, 6, ["A", "B"], rng=random.Random(99))
    cells_b = generate_rooms(6, 6, ["A", "B"], rng=random.Random(99))
    assert {k: v.area for k, v in cells_a.items()} == {k: v.area for k, v in cells_b.items()}


def test_rooms_rejects_more_areas_than_cells():
    with pytest.raises(ValueError):
        generate_rooms(2, 2, ["A", "B", "C", "D", "E"])


@pytest.mark.parametrize("seed", range(20))
def test_connectivity_holds_across_many_random_seeds(seed):
    # el flood fill depende del orden aleatorio de expansion; probamos
    # muchas semillas distintas para tener confianza de que no es casualidad.
    cells = generate_rooms(7, 7, ["A", "B", "C", "D", "E"], rng=random.Random(seed))
    for area, cell_ids in _cells_by_area(cells).items():
        assert _is_connected(cell_ids), f"seed={seed}: area {area} disconnected"


def _build_puzzle(rows: int, cols: int, cells: dict, placement: dict, clues: dict) -> Puzzle:
    areas: dict = {}
    for cell_id, cell in cells.items():
        areas.setdefault(cell.area, []).append(cell_id)

    return Puzzle(
        id="generated_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=rows, cols=cols),
        areas=areas,
        cells=cells,
        people=[
            Person(id=pid, role="suspect", clue=Clue(text="...", structured=clues[pid]))
            for pid in placement
        ],
    )


def test_every_person_gets_a_clue():
    rng = random.Random(5)
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=rng)
    rooms = generate_rooms(4, 4, ["A", "B"], rng=rng)
    _, clues = assign_clues_and_objects(placement, rooms, 4, 4, rng=rng)
    assert set(clues.keys()) == set(people)


def test_nobody_ends_up_placed_on_a_blocked_cell():
    rng = random.Random(6)
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena"]
    placement = generate_placement(5, 5, people, rng=rng)
    rooms = generate_rooms(5, 5, ["A", "B", "C"], rng=rng)
    cells, clues = assign_clues_and_objects(placement, rooms, 5, 5, rng=rng)
    puzzle = _build_puzzle(5, 5, cells, placement, clues)
    assert check_no_blocked_cells(puzzle, placement) == []


@pytest.mark.parametrize("seed", range(20))
def test_derived_clues_are_actually_true_according_to_our_own_verifier(seed):
    rng = random.Random(seed)
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    cells, clues = assign_clues_and_objects(placement, rooms, 6, 6, rng=rng)
    puzzle = _build_puzzle(6, 6, cells, placement, clues)

    assert check_no_blocked_cells(puzzle, placement) == []
    assert check_clues_satisfied(puzzle, placement) == []


def test_object_on_clues_use_only_non_blocking_objects():
    rng = random.Random(6)
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena"]
    placement = generate_placement(5, 5, people, rng=rng)
    rooms = generate_rooms(5, 5, ["A", "B", "C"], rng=rng)
    _, clues = assign_clues_and_objects(placement, rooms, 5, 5, rng=rng)
    for structured in clues.values():
        if structured["type"] == "object_on":
            assert structured["object"] in NON_BLOCKING_OBJECTS


def test_assign_clues_is_reproducible_with_the_same_seed():
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=random.Random(8))
    rooms = generate_rooms(4, 4, ["A", "B"], rng=random.Random(8))

    _, clues_a = assign_clues_and_objects(placement, rooms, 4, 4, rng=random.Random(1))
    _, clues_b = assign_clues_and_objects(placement, rooms, 4, 4, rng=random.Random(1))
    assert clues_a == clues_b


def test_render_clue_template_for_area():
    text = render_clue_template({"type": "area", "area": "JARDIN"})
    assert text == "Estaba en la sala JARDIN."


def test_render_clue_template_for_object_on():
    text = render_clue_template({"type": "object_on", "object": "silla"})
    assert text == "Estaba sobre una silla."


def test_render_clue_template_for_object_adjacent():
    text = render_clue_template({"type": "object_adjacent", "object": "mesa"})
    assert text == "Estaba junto a una mesa."


def test_render_clue_template_rejects_unsupported_type():
    with pytest.raises(ValueError):
        render_clue_template({"type": "relational_person", "relation": "alone"})


def test_reword_with_llm_returns_the_models_text_and_calls_the_right_model():
    # "doble" (mock) del cliente de OpenAI: no llamamos a la API de verdad,
    # solo comprobamos que nuestra funcion la usa correctamente.
    fake_content = Mock(type="output_text", text="  Descansaba junto a una mesa.  ")
    fake_message = Mock(type="message", content=[fake_content])
    fake_response = Mock(output=[fake_message])
    fake_client = Mock()
    fake_client.responses.create.return_value = fake_response

    result = reword_with_llm("Estaba junto a una mesa.", fake_client, model="gpt-5.4-nano")

    assert result == "Descansaba junto a una mesa."
    _, kwargs = fake_client.responses.create.call_args
    assert kwargs["model"] == "gpt-5.4-nano"
    assert kwargs["input"][1]["content"] == "Estaba junto a una mesa."


def _puzzle_with_four_single_cell_areas() -> Puzzle:
    # 2x2, cada celda es su propia sala: el clue "area X" solo puede
    # cumplirse en una celda concreta.
    cells = {
        "r0c0": Cell(area="A"),
        "r0c1": Cell(area="B"),
        "r1c0": Cell(area="C"),
        "r1c1": Cell(area="D"),
    }
    return Puzzle(
        id="unique_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"A": ["r0c0"], "B": ["r0c1"], "C": ["r1c0"], "D": ["r1c1"]},
        cells=cells,
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(text="...", structured={"type": "area", "area": "A"}),
            ),
            Person(
                id="Bruno",
                role="suspect",
                clue=Clue(text="...", structured={"type": "area", "area": "D"}),
            ),
        ],
    )


def test_finds_the_unique_solution_when_clues_force_it():
    puzzle = _puzzle_with_four_single_cell_areas()
    solutions = find_all_solutions(puzzle, max_solutions=5)
    assert solutions == [{"Ada": "r0c0", "Bruno": "r1c1"}]
    assert has_unique_solution(puzzle)


def _puzzle_with_an_ambiguous_solution() -> Puzzle:
    # 2x2, una sola sala que cubre todo: la pista de Ada no distingue
    # ninguna celda, y Bruno no tiene pista -- cualquiera de las 2
    # colocaciones validas sirve.
    cells = {cell_id: Cell(area="ROOM") for cell_id in ["r0c0", "r0c1", "r1c0", "r1c1"]}
    return Puzzle(
        id="ambiguous_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"ROOM": list(cells.keys())},
        cells=cells,
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(text="...", structured={"type": "area", "area": "ROOM"}),
            ),
            Person(id="Bruno", role="victim"),
        ],
    )


def test_does_not_have_a_unique_solution_when_clues_are_too_loose():
    puzzle = _puzzle_with_an_ambiguous_solution()
    assert not has_unique_solution(puzzle)
    assert len(find_all_solutions(puzzle, max_solutions=5)) > 1


def test_backtracking_search_finds_the_generators_own_solution():
    rng = random.Random(11)
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=rng)
    rooms = generate_rooms(4, 4, ["A", "B"], rng=rng)
    cells, clues = assign_clues_and_objects(placement, rooms, 4, 4, rng=rng)
    puzzle = _build_puzzle(4, 4, cells, placement, clues)

    solutions = find_all_solutions(puzzle, max_solutions=10)
    assert placement in solutions


def _generate(seed: int, rows: int = 5, cols: int = 5) -> Puzzle:
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena"][:rows]
    return generate_puzzle(
        rows,
        cols,
        people,
        victim_id=people[-1],
        area_names=["A", "B", "C", "D", "E"],
        scenario="Test",
        difficulty="easy",
        rng=random.Random(seed),
    )


@pytest.mark.parametrize("seed", range(10))
def test_generated_puzzle_is_fully_valid(seed):
    puzzle = _generate(seed)
    solution = puzzle.solution

    assert check_unique_rows_and_cols(solution) == []
    assert check_no_blocked_cells(puzzle, solution) == []
    assert check_clues_satisfied(puzzle, solution) == []
    assert identify_murderer(puzzle, solution) is not None
    assert has_unique_solution(puzzle)


def test_victim_has_no_clue_and_suspects_all_do():
    puzzle = _generate(seed=3)
    for person in puzzle.people:
        if person.role == "victim":
            assert person.clue is None
        else:
            assert person.clue is not None


def test_generate_puzzle_is_reproducible_with_the_same_seed():
    puzzle_a = _generate(seed=17)
    puzzle_b = _generate(seed=17)
    assert puzzle_a.solution == puzzle_b.solution
    assert puzzle_a.cells == puzzle_b.cells


def test_generate_puzzle_rejects_victim_not_in_person_ids():
    with pytest.raises(ValueError):
        generate_puzzle(
            3,
            3,
            ["Ada", "Bruno", "Carmen"],
            victim_id="Nobody",
            area_names=["A"],
            scenario="Test",
            difficulty="easy",
        )
