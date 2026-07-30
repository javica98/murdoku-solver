from murdoku.orchestrator import _is_simple_clue, choose_model_for_puzzle
from murdoku.schema import Cell, Clue, Grid, Person, Puzzle


def _puzzle_with_clues(*structured_clues: dict) -> Puzzle:
    people = [
        Person(id=f"P{i}", role="suspect", clue=Clue(text="...", structured=structured))
        for i, structured in enumerate(structured_clues)
    ]
    people.append(Person(id="Victima", role="victim"))
    return Puzzle(
        id="orchestrator_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"ROOM": ["r0c0", "r0c1", "r1c0", "r1c1"]},
        cells={
            "r0c0": Cell(area="ROOM"),
            "r0c1": Cell(area="ROOM"),
            "r1c0": Cell(area="ROOM"),
            "r1c1": Cell(area="ROOM"),
        },
        people=people,
    )


def test_row_local_clue_is_simple():
    assert _is_simple_clue({"type": "area", "area": "ROOM"}) is True


def test_relational_clue_is_not_simple():
    assert _is_simple_clue({"type": "relative_to_person", "reference": "P0", "relation": "same_row"}) is False


def test_negated_clue_is_not_simple_even_if_row_local():
    assert _is_simple_clue({"type": "area", "area": "ROOM", "negate": True}) is False


def test_any_clue_is_not_simple():
    assert (
        _is_simple_clue(
            {
                "type": "any",
                "clauses": [{"type": "area", "area": "ROOM"}, {"type": "area", "area": "OTHER"}],
            }
        )
        is False
    )


def test_all_clue_is_simple_only_if_every_clause_is_simple():
    all_simple = {
        "type": "all",
        "clauses": [{"type": "area", "area": "ROOM"}, {"type": "object_on", "object": "libro"}],
    }
    assert _is_simple_clue(all_simple) is True

    one_complex = {
        "type": "all",
        "clauses": [{"type": "area", "area": "ROOM"}, {"type": "with_person", "reference": "P0"}],
    }
    assert _is_simple_clue(one_complex) is False


def test_unrecognized_future_clue_type_defaults_to_not_simple():
    assert _is_simple_clue({"type": "distance_direction", "steps": 2, "direction": "north"}) is False


def test_puzzle_with_only_row_local_clues_routes_to_cheap_model():
    puzzle = _puzzle_with_clues(
        {"type": "area", "area": "ROOM"},
        {"type": "object_on", "object": "libro"},
    )
    assert choose_model_for_puzzle(puzzle, cheap_model="cheap", reasoning_model="smart") == "cheap"


def test_puzzle_with_one_relational_clue_routes_to_reasoning_model():
    puzzle = _puzzle_with_clues(
        {"type": "area", "area": "ROOM"},
        {"type": "relative_to_person", "reference": "P0", "relation": "same_row"},
    )
    assert choose_model_for_puzzle(puzzle, cheap_model="cheap", reasoning_model="smart") == "smart"


def test_puzzle_with_negated_clue_routes_to_reasoning_model():
    puzzle = _puzzle_with_clues({"type": "object_on", "object": "libro", "negate": True})
    assert choose_model_for_puzzle(puzzle, cheap_model="cheap", reasoning_model="smart") == "smart"


def test_puzzle_with_any_clue_routes_to_reasoning_model():
    puzzle = _puzzle_with_clues(
        {
            "type": "any",
            "clauses": [{"type": "area", "area": "ROOM"}, {"type": "area", "area": "OTHER"}],
        }
    )
    assert choose_model_for_puzzle(puzzle, cheap_model="cheap", reasoning_model="smart") == "smart"


def test_victim_without_clue_does_not_affect_routing():
    puzzle = _puzzle_with_clues({"type": "area", "area": "ROOM"})
    assert choose_model_for_puzzle(puzzle, cheap_model="cheap", reasoning_model="smart") == "cheap"


def test_unrecognized_clue_type_routes_to_reasoning_model_by_default():
    puzzle = _puzzle_with_clues({"type": "distance_direction", "steps": 2, "direction": "north"})
    assert choose_model_for_puzzle(puzzle, cheap_model="cheap", reasoning_model="smart") == "smart"
