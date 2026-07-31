import pytest

from murdoku.render_html import _humanize_area, render_puzzle_html
from murdoku.schema import Cell, Clue, Grid, Person, Puzzle


def _playable_puzzle() -> Puzzle:
    return Puzzle(
        id="render_test",
        scenario="La cena de gala",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"SALON": ["r0c0", "r0c1", "r1c0", "r1c1"]},
        cells={
            "r0c0": Cell(area="SALON", objects=["copa"], blocked=False),
            "r0c1": Cell(area="SALON", objects=[], blocked=True),
            "r1c0": Cell(area="SALON", objects=[], blocked=False),
            "r1c1": Cell(area="SALON", objects=[], blocked=False),
        },
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(text="Estaba junto a una copa.", structured={"type": "object_adjacent", "object": "copa"}),
            ),
            Person(id="Bruno", role="victim"),
        ],
        solution={"Ada": "r1c0", "Bruno": "r1c1"},
    )


def test_humanize_area_replaces_underscores_and_titlecases():
    assert _humanize_area("CIRCULO_DE_DEBATE") == "Circulo de Debate"


def test_humanize_area_single_word():
    assert _humanize_area("BIBLIOTECA") == "Biblioteca"


def test_render_raises_without_solution():
    puzzle = _playable_puzzle()
    puzzle.solution = None
    with pytest.raises(ValueError, match="solucion"):
        render_puzzle_html(puzzle)


def test_render_raises_without_victim():
    puzzle = _playable_puzzle()
    puzzle.people = [p for p in puzzle.people if p.role != "victim"]
    with pytest.raises(ValueError, match="victima"):
        render_puzzle_html(puzzle)


def test_render_raises_without_identifiable_murderer():
    # los dos sospechosos comparten sala con la victima -> no hay un
    # unico asesino posible.
    puzzle = Puzzle(
        id="ambiguous_test",
        scenario="Fiesta",
        difficulty="easy",
        grid=Grid(rows=3, cols=3),
        areas={"SALON": [f"r{r}c{c}" for r in range(3) for c in range(3)]},
        cells={f"r{r}c{c}": Cell(area="SALON") for r in range(3) for c in range(3)},
        people=[
            Person(id="Ada", role="suspect", clue=Clue(text="...", structured={"type": "area", "area": "SALON"})),
            Person(id="Carmen", role="suspect", clue=Clue(text="...", structured={"type": "area", "area": "SALON"})),
            Person(id="Bruno", role="victim"),
        ],
        solution={"Ada": "r0c0", "Carmen": "r1c1", "Bruno": "r2c2"},
    )
    with pytest.raises(ValueError, match="asesino"):
        render_puzzle_html(puzzle)


def test_render_includes_murderer_and_murder_room():
    html = render_puzzle_html(_playable_puzzle())
    assert '"murderer": "Ada"' in html
    assert '"murderRoom": "Salon"' in html


def test_render_includes_scenario_and_case_id():
    html = render_puzzle_html(_playable_puzzle())
    assert "La cena de gala" in html
    assert "render_test" in html


def test_render_includes_clue_text_not_structured_type():
    html = render_puzzle_html(_playable_puzzle())
    assert "Estaba junto a una copa." in html
    assert "object_adjacent" not in html


def test_render_includes_person_ids_and_solution():
    html = render_puzzle_html(_playable_puzzle())
    assert '"Ada"' in html
    assert '"Bruno"' in html
    assert '"r1c0"' in html

def test_render_includes_humanized_area_label():
    html = render_puzzle_html(_playable_puzzle())
    assert "Salon" in html


def test_render_is_self_contained_html_fragment():
    html = render_puzzle_html(_playable_puzzle())
    assert "<style>" in html
    assert "<script>" in html
    assert "__PUZZLE_JSON__" not in html
    assert "__ROOM_LIGHT_VARS__" not in html
    assert "__ROOM_CLASSES__" not in html
