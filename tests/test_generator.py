import random

import pytest

from murdoku.generator import generate_placement
from murdoku.verifier import check_unique_rows_and_cols, parse_cell_id


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
