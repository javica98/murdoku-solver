import json
from unittest.mock import Mock

from murdoku.reskin import (
    _rethemed_structured,
    _themed_puzzle_is_valid,
    apply_theme,
    get_theme_vocabulary,
    reskin_puzzle,
)
from murdoku.schema import Cell, Clue, Grid, Person, Puzzle


def _fake_client(*response_texts: str) -> Mock:
    responses = []
    for text in response_texts:
        fake_content = Mock(type="output_text", text=text)
        fake_message = Mock(type="message", content=[fake_content])
        responses.append(Mock(output=[fake_message]))
    fake_client = Mock()
    if len(responses) == 1:
        fake_client.responses.create.return_value = responses[0]
    else:
        fake_client.responses.create.side_effect = responses
    return fake_client


def test_get_theme_vocabulary_parses_a_valid_json_response():
    client = _fake_client(
        json.dumps(
            {
                "planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"},
                "AREA_0": {"nombre": "Gimnasio", "genero": "m", "emoji": ""},
                "Ada": {"nombre": "Nova", "genero": "f", "emoji": ""},
            }
        )
    )
    vocabulary = get_theme_vocabulary(["planta"], ["AREA_0"], ["Ada"], "pokemon", client)
    assert vocabulary == {
        "planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"},
        "AREA_0": {"nombre": "Gimnasio", "genero": "m", "emoji": ""},
        "Ada": {"nombre": "Nova", "genero": "f", "emoji": ""},
    }


def test_get_theme_vocabulary_calls_the_cheap_model_by_default():
    client = _fake_client(json.dumps({"planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"}}))
    get_theme_vocabulary(["planta"], [], [], "pokemon", client)
    _, kwargs = client.responses.create.call_args
    assert kwargs["model"] == "gpt-5.4-nano"


def test_get_theme_vocabulary_returns_empty_on_malformed_json():
    client = _fake_client("esto no es json")
    vocabulary = get_theme_vocabulary(["planta"], ["AREA_0"], [], "pokemon", client)
    assert vocabulary == {}


def test_get_theme_vocabulary_drops_keys_the_puzzle_never_asked_for():
    # el modelo se inventa una clave que no estaba en la lista original.
    client = _fake_client(
        json.dumps(
            {
                "planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"},
                "objeto_inventado": {"nombre": "algo", "genero": "m", "emoji": ""},
            }
        )
    )
    vocabulary = get_theme_vocabulary(["planta"], ["AREA_0"], [], "pokemon", client)
    assert vocabulary == {"planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"}}


def test_get_theme_vocabulary_defaults_to_feminine_on_invalid_gender():
    client = _fake_client(json.dumps({"planta": {"nombre": "pokebola", "genero": "neutro", "emoji": "🔴"}}))
    vocabulary = get_theme_vocabulary(["planta"], [], [], "pokemon", client)
    assert vocabulary == {"planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"}}


def test_get_theme_vocabulary_defaults_to_empty_emoji_when_missing_or_invalid():
    client = _fake_client(
        json.dumps({"planta": {"nombre": "pokebola", "genero": "f"}, "AREA_0": {"nombre": "Gimnasio", "genero": "m", "emoji": 7}})
    )
    vocabulary = get_theme_vocabulary(["planta"], ["AREA_0"], [], "pokemon", client)
    assert vocabulary["planta"]["emoji"] == ""
    assert vocabulary["AREA_0"]["emoji"] == ""


def test_get_theme_vocabulary_skips_entries_with_no_usable_name():
    client = _fake_client(json.dumps({"planta": {"genero": "f", "emoji": "🔴"}}))
    vocabulary = get_theme_vocabulary(["planta"], [], [], "pokemon", client)
    assert vocabulary == {}


def test_get_theme_vocabulary_includes_character_names():
    client = _fake_client(json.dumps({"Ada": {"nombre": "Nova", "genero": "f", "emoji": ""}}))
    vocabulary = get_theme_vocabulary([], [], ["Ada"], "pokemon", client)
    assert vocabulary == {"Ada": {"nombre": "Nova", "genero": "f", "emoji": ""}}


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


def test_rethemed_structured_replaces_person_reference():
    structured = {"type": "with_person", "reference": "Ada"}
    result = _rethemed_structured(structured, {"Ada": "Nova"}, {})
    assert result == {"type": "with_person", "reference": "Nova"}


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
    # 4x4: Ada/Carmen comparten AREA_0 (para el with_person de Carmen),
    # Diana/Bruno comparten AREA_1 (Diana es la unica sospechosa con la
    # victima -> asesina identificable). Fila y columna unicas por persona.
    area_0_cells = [f"r{r}c{c}" for r in (0, 1) for c in range(4)]
    area_1_cells = [f"r{r}c{c}" for r in (2, 3) for c in range(4)]
    cells = {cid: Cell(area="AREA_0") for cid in area_0_cells}
    cells.update({cid: Cell(area="AREA_1") for cid in area_1_cells})
    cells["r0c1"].objects = ["planta"]

    return Puzzle(
        id="reskin_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=4, cols=4),
        areas={"AREA_0": area_0_cells, "AREA_1": area_1_cells},
        cells=cells,
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(
                    text="Estaba junto a una planta.",
                    structured={"type": "object_adjacent", "object": "planta", "gender": "f"},
                ),
            ),
            Person(
                id="Carmen",
                role="suspect",
                clue=Clue(text="Estaba con Ada.", structured={"type": "with_person", "reference": "Ada"}),
            ),
            Person(
                id="Diana",
                role="suspect",
                clue=Clue(text="Estaba con Bruno.", structured={"type": "with_person", "reference": "Bruno"}),
            ),
            Person(id="Bruno", role="victim"),
        ],
        solution={"Ada": "r0c0", "Carmen": "r1c1", "Diana": "r2c2", "Bruno": "r3c3"},
        object_emoji={"planta": "🪴"},
    )


def test_apply_theme_renames_objects_in_cells():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"}})
    assert themed.cells["r0c1"].objects == ["pokebola"]


def test_apply_theme_renames_area_keys():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"AREA_0": {"nombre": "Gimnasio", "genero": "m", "emoji": ""}})
    assert "Gimnasio" in themed.areas
    assert "AREA_0" not in themed.areas
    assert themed.cells["r0c0"].area == "Gimnasio"


def test_apply_theme_re_renders_clue_text_with_the_new_name():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"}})
    ada = next(p for p in themed.people if p.id == "Ada")
    assert ada.clue.text == "Estaba junto a una pokebola."
    assert ada.clue.structured["object"] == "pokebola"


def test_apply_theme_uses_the_themed_gender_for_the_article():
    # "planta" es femenina, pero su version tematica ("baul", tesoro
    # pirata) es masculina -- la plantilla debe decir "un baul", no
    # "una baul".
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "baul", "genero": "m", "emoji": "🪙"}})
    ada = next(p for p in themed.people if p.id == "Ada")
    assert ada.clue.text == "Estaba junto a un baul."
    assert ada.clue.structured["gender"] == "m"


def test_apply_theme_does_not_touch_the_victim_clue():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "pokebola", "genero": "f", "emoji": "🔴"}})
    bruno = next(p for p in themed.people if p.id == "Bruno")
    assert bruno.clue is None


def test_apply_theme_moves_the_emoji_to_the_new_object_name():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "baul", "genero": "m", "emoji": "🪙"}})
    assert themed.object_emoji == {"baul": "🪙"}


def test_apply_theme_keeps_the_original_emoji_when_the_model_gives_none():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"planta": {"nombre": "baul", "genero": "m", "emoji": ""}})
    assert themed.object_emoji == {"baul": "🪴"}


def test_apply_theme_keeps_untouched_objects_under_their_original_emoji():
    # el vocabulario solo trae "AREA_0" -- "planta" nunca se retema.
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"AREA_0": {"nombre": "Gimnasio", "genero": "m", "emoji": ""}})
    assert themed.object_emoji == {"planta": "🪴"}


def test_apply_theme_renames_person_id_and_solution_key():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"Ada": {"nombre": "Nova", "genero": "f", "emoji": ""}})
    ada = next(p for p in themed.people if p.id == "Nova")
    assert ada is not None
    assert themed.solution == {"Nova": "r0c0", "Carmen": "r1c1", "Diana": "r2c2", "Bruno": "r3c3"}


def test_apply_theme_updates_the_reference_inside_another_persons_clue():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"Ada": {"nombre": "Nova", "genero": "f", "emoji": ""}})
    carmen = next(p for p in themed.people if p.id == "Carmen")
    assert carmen.clue.structured["reference"] == "Nova"
    assert carmen.clue.text == "Estaba con Nova."


def test_apply_theme_populates_theme_vocabulary():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(
        puzzle,
        {
            "planta": {"nombre": "baul", "genero": "m", "emoji": "🪙"},
            "Ada": {"nombre": "Nova", "genero": "f", "emoji": ""},
        },
    )
    assert themed.theme_vocabulary == {"planta": "baul", "Ada": "Nova"}


def test_themed_puzzle_is_valid_accepts_a_clean_rename():
    puzzle = _themed_test_puzzle()
    themed = apply_theme(puzzle, {"Ada": {"nombre": "Nova", "genero": "f", "emoji": ""}})
    assert _themed_puzzle_is_valid(puzzle, themed) is True


def test_themed_puzzle_is_valid_rejects_a_person_name_collision():
    # "Ada" y "Carmen" acaban con el mismo nombre -- una de las dos
    # entradas de `solution` se pisa (los dicts no admiten claves
    # repetidas), asi que deja de haber una persona por fila/columna.
    puzzle = _themed_test_puzzle()
    vocabulary = {
        "Ada": {"nombre": "Nova", "genero": "f", "emoji": ""},
        "Carmen": {"nombre": "Nova", "genero": "f", "emoji": ""},
    }
    themed = apply_theme(puzzle, vocabulary)
    assert _themed_puzzle_is_valid(puzzle, themed) is False


def test_themed_puzzle_is_valid_rejects_an_object_name_collision_breaking_a_clue():
    # un puzzle donde la pista de Ada depende de que "planta" sea el
    # UNICO objeto de su tipo en el tablero (relative_to_object) -- si el
    # retema hace que otro objeto tambien se llame igual, la pista deja
    # de cumplirse para la propia solucion canonica.
    puzzle = Puzzle(
        id="collision_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"AREA_0": ["r0c0", "r0c1", "r1c0", "r1c1"]},
        cells={
            "r0c0": Cell(area="AREA_0", objects=["planta"]),
            "r0c1": Cell(area="AREA_0", objects=["silla"]),
            "r1c0": Cell(area="AREA_0"),
            "r1c1": Cell(area="AREA_0"),
        },
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(
                    text="Estaba 1 fila al sur de la planta.",
                    structured={
                        "type": "relative_to_object", "object": "planta",
                        "direction": "south", "distance": 1, "gender": "f",
                    },
                ),
            ),
            Person(id="Bruno", role="victim"),
        ],
        solution={"Ada": "r1c0", "Bruno": "r0c1"},
    )
    # "planta" y "silla" acaban ambas llamandose "reliquia" -> ya no es
    # unica en el tablero, relative_to_object deja de poder anclarse.
    vocabulary = {
        "planta": {"nombre": "reliquia", "genero": "f", "emoji": ""},
        "silla": {"nombre": "reliquia", "genero": "f", "emoji": ""},
    }
    themed = apply_theme(puzzle, vocabulary)
    assert _themed_puzzle_is_valid(puzzle, themed) is False


def test_reskin_puzzle_end_to_end_with_a_mocked_client():
    puzzle = _themed_test_puzzle()
    client = _fake_client(
        json.dumps(
            {
                "planta": {"nombre": "baul", "genero": "m", "emoji": "🪙"},
                "AREA_0": {"nombre": "Cubierta", "genero": "f", "emoji": ""},
                "AREA_1": {"nombre": "Camarote", "genero": "m", "emoji": ""},
                "Ada": {"nombre": "Anamaria", "genero": "f", "emoji": ""},
                "Carmen": {"nombre": "Calico", "genero": "f", "emoji": ""},
                "Diana": {"nombre": "Dalila", "genero": "f", "emoji": ""},
                "Bruno": {"nombre": "Barbanegra", "genero": "m", "emoji": ""},
            }
        )
    )

    themed = reskin_puzzle(puzzle, "piratas", client)

    assert themed.cells["r0c1"].objects == ["baul"]
    assert "Cubierta" in themed.areas
    assert themed.object_emoji == {"baul": "🪙"}
    assert {p.id for p in themed.people} == {"Anamaria", "Calico", "Dalila", "Barbanegra"}
    ada = next(p for p in themed.people if p.id == "Anamaria")
    assert ada.clue.text == "Estaba junto a un baul."


def test_reskin_puzzle_returns_the_original_puzzle_when_the_model_fails():
    puzzle = _themed_test_puzzle()
    client = _fake_client("no es json")
    themed = reskin_puzzle(puzzle, "pokemon", client)
    assert themed == puzzle


def test_reskin_puzzle_retries_after_a_colliding_vocabulary():
    puzzle = _themed_test_puzzle()
    colliding_response = json.dumps(
        {
            "Ada": {"nombre": "Nova", "genero": "f", "emoji": ""},
            "Carmen": {"nombre": "Nova", "genero": "f", "emoji": ""},
            "Bruno": {"nombre": "Rocket", "genero": "m", "emoji": ""},
        }
    )
    clean_response = json.dumps(
        {
            "Ada": {"nombre": "Nova", "genero": "f", "emoji": ""},
            "Carmen": {"nombre": "Estrella", "genero": "f", "emoji": ""},
            "Bruno": {"nombre": "Rocket", "genero": "m", "emoji": ""},
        }
    )
    client = _fake_client(colliding_response, clean_response)

    themed = reskin_puzzle(puzzle, "pokemon", client, max_attempts=3)

    assert client.responses.create.call_count == 2
    # Diana no aparece en ninguna respuesta -- se queda con su nombre
    # generico, y aun asi el resto del retema se considera valido.
    assert {p.id for p in themed.people} == {"Nova", "Estrella", "Rocket", "Diana"}


def test_reskin_puzzle_gives_up_and_stays_generic_after_max_attempts():
    puzzle = _themed_test_puzzle()
    always_colliding = json.dumps(
        {
            "Ada": {"nombre": "Nova", "genero": "f", "emoji": ""},
            "Carmen": {"nombre": "Nova", "genero": "f", "emoji": ""},
        }
    )
    client = _fake_client(always_colliding, always_colliding, always_colliding)

    themed = reskin_puzzle(puzzle, "pokemon", client, max_attempts=3)

    assert client.responses.create.call_count == 3
    assert themed == puzzle
