import random

import pytest

from murdoku.generator import (
    NON_BLOCKING_OBJECTS,
    assign_clues_and_objects,
    generate_placement,
    generate_rooms,
)
from murdoku.schema import Clue, Grid, Person, Puzzle
from murdoku.verifier import (
    check_clues_satisfied,
    check_no_blocked_cells,
    check_unique_rows_and_cols,
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
