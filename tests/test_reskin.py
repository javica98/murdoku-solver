import json
from unittest.mock import Mock

from murdoku.reskin import _rethemed_structured, apply_theme, get_theme_vocabulary, reskin_puzzle
from murdoku.schema import Cell, Clue, Grid, Person, Puzzle


def _fake_client(response_text: str) -> Mock:
    fake_content = Mock(type="output_text", text=response_text)
    fake_message = Mock(type="message", content=[fake_content])
    fake_response = Mock(output=[fake_message])
    fake_client = Mock()
    fake_client.responses.create.return_value = fake_response
    return fake_client


def test_get_theme_vocabulary_parses_a_valid_json_response():
    client = _fake_client(
        json.dumps({"planta": {"nombre": "pokebola", "genero": "f"}, "AREA_0": {"nombre": "Gimnasio", "genero": "m"}})
    )
    vocabulary = get_theme_vocabulary(["planta"], ["AREA_0"], "pokemon", client)
    assert vocabulary == {
        "planta": {"nombre": "pokebola", "genero": "f"},
        "AREA_0": {"nombre": "Gimnasio", "genero": "m"},
    }


def test_get_theme_vocabulary_calls_the_cheap_model_by_default():
    client = _fake_client(json.dumps({"planta": {"nombre": "pokebola", "genero": "f"}}))
    get_theme_vocabulary(["planta"], [], "pokemon", client)
    _, kwargs = client.responses.create.call_args
    assert kwargs["model"] == "gpt-5.4-nano"


def test_get_theme_vocabulary_returns_empty_on_malformed_json():
    client = _fake_client("esto no es json")
    vocabulary = get_theme_vocabulary(["planta"], ["AREA_0"], "pokemon", client)
    assert vocabulary == {}


def test_get_theme_vocabulary_drops_keys_the_puzzle_never_asked_for():
    # el modelo se inventa una clave que no estaba en la lista original.
    client = _fake_client(
        json.dumps(
            {
                "planta": {"nombre": "pokebola", "genero": "f"},
                "objeto_inventado": {"nombre": "algo", "genero": "m"},
            }
        )
    )
    vocabulary = get_theme_vocabulary(["planta"], ["AREA_0"], "pokemon", client)
    assert vocabulary == {"planta": {"nombre": "pokebola", "genero": "f"}}


def test_get_theme_vocabulary_defaults_to_feminine_on_invalid_gender():
    client = _fake_client(json.dumps({"planta": {"nombre": "pokebola", "genero": "neutro"}}))
    vocabulary = get_theme_vocabulary(["planta"], [], "pokemon", client)
    assert vocabulary == {"planta": {"nombre": "pokebola", "genero": "f"}}


def test_get_theme_vocabulary_skips_entries_with_no_usable_name():
    client = _fake_client(json.dumps({"planta": {"genero": "f"}}))
    vocabulary = get_theme_vocabulary(["planta"], [], "pokemon", client)
    assert vocabulary == {}


def test_rethemed_structured_replaces_object_and_carries_its_new_gender():
    structured = {"type": "object_on", "object": "silla", "gender": "f"}
    name_map = {"silla": "barril"}
    gender_map = {"barril": "m"}
    result = _rethemed_structured(structured, name_map, gender_map)
    assert result == {"type": "object_on", "object": "barril", "gender": "m"}


def test_rethemed_structured_replaces_area():
    structured = {"type": "area", "area": "AREA_0"}
    result = _rethemed_structured(structured, {"AREA_0": "Gimnasio"}, {})
    assert result == {"type": "area", "area": "Gimnasio"}


def test_rethemed_structured_recurses_into_clauses():
    structured = {
        "type": "all",
        "clauses": [
            {"type": "area", "area": "AREA_0"},
            {"type": "object_adjacent", "object": "planta", "gender": "f"},
        ],
    }
    name_map = {"AREA_0": "Gimnasio", "planta": "pokebola"}
    gender_map = {"pokebola": "f"}
    result = _rethemed_structured(structured, name_map, gender_map)
    assert result == {
        "type": "all",
        "clauses": [
            {"type": "area", "area": "Gimnasio"},
            {"type": "object_adjacent", "object": "pokebola", "gender": "f"},
        ],
    }


def test_rethemed_structured_leaves_unmapped_names_unchanged():
    structured = {"type": "object_on", "object": "silla", "gender": "f"}
    result = _rethemed_structured(structured, {}, {})
    assert result == structured


def _themed_test_puzzle() -> Puzzle:
    return Puzzle(
        id="reskin_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"AREA_0": ["r0c0", "r0c1"], "AREA_1": ["r1c0", "r1c1"]},
        cells={
            "r0c0": Cell(area="AREA_0", objects=["planta"]),
            "r0c1": Cell(area="AREA_0"),
            "r1c0": Cell(area="AREA_1"),
            "r1c1": Cell(area="AREA_1"),
        },
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(
                    text="Estaba junto a una planta.",
                    structured={"type": "object_adjacent", "object": "planta", "gender": "f"},
                ),
            ),
            Person(id="Bruno", role="victim"),
        ],
        solution={"Ada": "r0c1", "Bruno": "r1c0"},
    )


def test_apply_theme_renames_objects_in_cells():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "pokebola", "genero": "f"}})
    assert themed.cells["r0c0"].objects == ["pokebola"]


def test_apply_theme_renames_area_keys():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"AREA_0": {"nombre": "Gimnasio", "genero": "m"}})
    assert "Gimnasio" in themed.areas
    assert "AREA_0" not in themed.areas
    assert themed.cells["r0c0"].area == "Gimnasio"


def test_apply_theme_re_renders_clue_text_with_the_new_name():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "pokebola", "genero": "f"}})
    ada = next(p for p in themed.people if p.id == "Ada")
    assert ada.clue.text == "Estaba junto a una pokebola."
    assert ada.clue.structured["object"] == "pokebola"


def test_apply_theme_uses_the_themed_gender_for_the_article():
    # "planta" es femenina, pero su version tematica ("baul", tesoro
    # pirata) es masculina -- la plantilla debe decir "un baul", no
    # "una baul".
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "baul", "genero": "m"}})
    ada = next(p for p in themed.people if p.id == "Ada")
    assert ada.clue.text == "Estaba junto a un baul."
    assert ada.clue.structured["gender"] == "m"


def test_apply_theme_does_not_touch_the_victim():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "pokebola", "genero": "f"}})
    bruno = next(p for p in themed.people if p.id == "Bruno")
    assert bruno.clue is None


def test_reskin_puzzle_end_to_end_with_a_mocked_client():
    puzzle = _themed_test_puzzle()
    client = _fake_client(
        json.dumps(
            {
                "planta": {"nombre": "baul", "genero": "m"},
                "AREA_0": {"nombre": "Cubierta", "genero": "f"},
                "AREA_1": {"nombre": "Camarote", "genero": "m"},
            }
        )
    )

    themed = reskin_puzzle(puzzle, "piratas", client)

    assert themed.cells["r0c0"].objects == ["baul"]
    assert "Cubierta" in themed.areas
    ada = next(p for p in themed.people if p.id == "Ada")
    assert ada.clue.text == "Estaba junto a un baul."


def test_reskin_puzzle_returns_the_original_puzzle_when_the_model_fails():
    puzzle = _themed_test_puzzle()
    client = _fake_client("no es json")
    themed = reskin_puzzle(puzzle, "pokemon", client)
    assert themed == puzzle
