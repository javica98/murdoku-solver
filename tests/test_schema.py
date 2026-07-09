import pytest
from pydantic import ValidationError

from murdoku.schema import Cell, Clue, Grid, Person, Puzzle


def test_cell_with_area_and_object():
    cell = Cell(area="CELL_A", objects=["bed"], blocked=False)
    assert cell.area == "CELL_A"
    assert cell.objects == ["bed"]
    assert cell.blocked is False


def test_cell_without_area_is_blocked():
    cell = Cell(area=None, objects=["water"], blocked=True)
    assert cell.area is None
    assert cell.blocked is True


def test_cell_objects_defaults_to_empty_list():
    cell = Cell(area="CELL_A")
    assert cell.objects == []
    assert cell.blocked is False


def test_cell_rejects_non_boolean_blocked():
    with pytest.raises(ValidationError):
        Cell(area="CELL_A", objects=["bed"], blocked="si")


def test_suspect_with_clue_is_valid():
    person = Person(
        id="Bastian",
        role="suspect",
        clue=Clue(text="He was in a Cell, on a bed."),
    )
    assert person.clue.text == "He was in a Cell, on a bed."


def test_victim_without_clue_is_valid():
    person = Person(id="Vlad", role="victim")
    assert person.clue is None


def test_suspect_without_clue_is_rejected():
    with pytest.raises(ValidationError):
        Person(id="Bastian", role="suspect")


def test_role_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Person(id="Bastian", role="detective", clue=Clue(text="..."))


def _minimal_puzzle_kwargs() -> dict:
    return dict(
        id="prison_mini_01",
        scenario="Solitary Confinement",
        difficulty="easy",
        grid=Grid(rows=1, cols=2),
        areas={"CELL_A": ["r0c0", "r0c1"]},
        cells={
            "r0c0": Cell(area="CELL_A", objects=["bed"]),
            "r0c1": Cell(area="CELL_A", objects=[]),
        },
        people=[
            Person(id="Bastian", role="suspect", clue=Clue(text="He was on a bed.")),
            Person(id="Vlad", role="victim"),
        ],
        solution={"Bastian": "r0c0", "Vlad": "r0c1"},
    )


def test_puzzle_with_valid_cell_ids_is_accepted():
    puzzle = Puzzle(**_minimal_puzzle_kwargs())
    assert puzzle.grid.rows == 1
    assert puzzle.cells["r0c0"].objects == ["bed"]
    assert puzzle.solution["Bastian"] == "r0c0"


def test_puzzle_rejects_malformed_cell_id_in_cells():
    kwargs = _minimal_puzzle_kwargs()
    kwargs["cells"] = {"A1": Cell(area="CELL_A")}
    with pytest.raises(ValidationError):
        Puzzle(**kwargs)


def test_puzzle_rejects_malformed_cell_id_in_areas():
    kwargs = _minimal_puzzle_kwargs()
    kwargs["areas"] = {"CELL_A": ["not-a-cell-id"]}
    with pytest.raises(ValidationError):
        Puzzle(**kwargs)


def test_puzzle_rejects_malformed_cell_id_in_solution():
    kwargs = _minimal_puzzle_kwargs()
    kwargs["solution"] = {"Bastian": "nope", "Vlad": "r0c1"}
    with pytest.raises(ValidationError):
        Puzzle(**kwargs)
