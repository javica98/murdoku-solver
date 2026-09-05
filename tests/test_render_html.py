import pytest

from murdoku.render_html import _humanize_area, _room_borders, render_puzzle_html
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
        object_emoji={"copa": "🍷"},
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


def _two_room_puzzle() -> Puzzle:
    # columna izquierda = area A, columna derecha = area B.
    return Puzzle(
        id="borders_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"A": ["r0c0", "r1c0"], "B": ["r0c1", "r1c1"]},
        cells={
            "r0c0": Cell(area="A"),
            "r0c1": Cell(area="B"),
            "r1c0": Cell(area="A"),
            "r1c1": Cell(area="B"),
        },
        people=[
            Person(id="Ada", role="suspect", clue=Clue(text="...", structured={"type": "area", "area": "B"})),
            Person(id="Bruno", role="victim"),
        ],
        # Ada y Bruno comparten area B, para que haya asesino identificable.
        solution={"Ada": "r0c1", "Bruno": "r1c1"},
    )


def test_room_borders_marks_board_edges():
    borders = _room_borders(_two_room_puzzle())
    assert borders["r0c0"]["top"] is True
    assert borders["r0c0"]["left"] is True


def test_room_borders_marks_area_boundary_but_not_same_area_seam():
    borders = _room_borders(_two_room_puzzle())
    # r0c0 (A) y r0c1 (B) son vecinos de distinta area -> pared entre ellas.
    assert borders["r0c0"]["right"] is True
    assert borders["r0c1"]["left"] is True
    # r0c0 (A) y r1c0 (A) son la misma area -> sin pared.
    assert borders["r0c0"]["bottom"] is False
    assert borders["r1c0"]["top"] is False


def test_render_includes_wall_border_data():
    html = render_puzzle_html(_two_room_puzzle())
    assert '"borders"' in html


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


def test_render_embeds_the_object_emoji_map():
    html = render_puzzle_html(_playable_puzzle())
    assert '"objectEmoji"' in html
    assert '"copa": "🍷"' in html


def test_render_handles_a_puzzle_with_no_object_emoji():
    # los puzzles reales transcritos a mano no traen object_emoji -- debe
    # renderizar igual, solo sin iconos.
    puzzle = _playable_puzzle()
    puzzle.object_emoji = {}
    html = render_puzzle_html(puzzle)
    assert '"objectEmoji": {}' in html


def test_render_embeds_the_theme_vocabulary():
    puzzle = _playable_puzzle()
    puzzle.theme_vocabulary = {"copa": "cáliz", "Ada": "Nova"}
    html = render_puzzle_html(puzzle)
    assert '"themeVocabulary"' in html
    assert '"copa": "cáliz"' in html
    assert '"Ada": "Nova"' in html
    assert 'id="theme-vocab"' in html


def test_render_handles_a_puzzle_with_no_theme_vocabulary():
    html = render_puzzle_html(_playable_puzzle())
    assert '"themeVocabulary": {}' in html


def test_render_shows_a_warning_when_theme_failed():
    html = render_puzzle_html(_playable_puzzle(), theme_failed=True)
    assert "No se pudo aplicar la tematica" in html


def test_render_shows_no_warning_by_default():
    html = render_puzzle_html(_playable_puzzle())
    assert "No se pudo aplicar la tematica" not in html
    assert '<p class="theme-warning">' not in html


def test_render_builds_witness_cards_via_textcontent_not_innerhtml():
    # antes, el id y la pista de cada testigo se montaban concatenando un
    # string y asignandolo con innerHTML -- un id tematizado por LLM que
    # contuviera markup se ejecutaria en el navegador del jugador. Ahora
    # se construyen con textContent, que nunca interpreta el valor como
    # HTML.
    html = render_puzzle_html(_playable_puzzle())
    assert "nameSpan.textContent = person.id;" in html
    assert "statement.textContent" in html
    assert "card.innerHTML =" not in html


def test_render_includes_note_mode_controls():
    html = render_puzzle_html(_playable_puzzle())
    assert 'id="mode-place-btn"' in html
    assert 'id="mode-note-btn"' in html
    assert "toggleNote" in html
    assert "clearNotesFor" in html


def test_render_includes_forbid_mode_controls():
    html = render_puzzle_html(_playable_puzzle())
    assert 'id="mode-forbid-btn"' in html
    assert "toggleForbidden" in html
    assert "forbidden-mark" in html


def test_render_makes_the_victim_placeable_like_a_witness():
    html = render_puzzle_html(_playable_puzzle())
    assert 'id="victim-card"' in html
    assert "armPerson(victim.id)" in html
    # el total a colocar (para "Faltan N personas" y el veredicto) debe
    # incluir a la victima, no solo a los sospechosos.
    assert "const placeable = PUZZLE.people;" in html
