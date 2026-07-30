import json
from unittest.mock import Mock

import pytest

from murdoku.pipeline import _structural_violations, run_pipeline
from murdoku.schema import Cell, Clue, Grid, Person, Puzzle


def _fake_response(answer: dict | str, input_tokens: int = 100, output_tokens: int = 50) -> Mock:
    text = answer if isinstance(answer, str) else json.dumps(answer)
    content = Mock(type="output_text", text=text)
    message = Mock(type="message", content=[content])
    response = Mock(output=[message])
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def _simple_puzzle() -> Puzzle:
    return Puzzle(
        id="pipeline_test",
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
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(text="...", structured={"type": "area", "area": "ROOM"}),
            ),
            Person(id="Bruno", role="victim"),
        ],
    )


def test_returns_valid_immediately_when_first_answer_is_correct():
    puzzle = _simple_puzzle()
    client = Mock()
    client.responses.create.return_value = _fake_response({"Ada": "r0c0", "Bruno": "r1c1"})

    result = run_pipeline(puzzle, client, model="gpt-5.4")

    assert result["valid"] is True
    assert result["attempts"] == 1
    assert result["solution"] == {"Ada": "r0c0", "Bruno": "r1c1"}
    assert client.responses.create.call_count == 1


def test_retries_and_succeeds_after_an_invalid_first_answer():
    puzzle = _simple_puzzle()
    client = Mock()
    # primer intento: Ada y Bruno comparten fila -> invalido.
    # segundo intento: correcto.
    client.responses.create.side_effect = [
        _fake_response({"Ada": "r0c0", "Bruno": "r0c1"}),
        _fake_response({"Ada": "r0c0", "Bruno": "r1c1"}),
    ]

    result = run_pipeline(puzzle, client, model="gpt-5.4", max_retries=2)

    assert result["valid"] is True
    assert result["attempts"] == 2
    assert client.responses.create.call_count == 2


def test_retries_and_succeeds_after_malformed_json():
    puzzle = _simple_puzzle()
    client = Mock()
    client.responses.create.side_effect = [
        _fake_response("esto no es json"),
        _fake_response({"Ada": "r0c0", "Bruno": "r1c1"}),
    ]

    result = run_pipeline(puzzle, client, model="gpt-5.4", max_retries=2)

    assert result["valid"] is True
    assert result["attempts"] == 2


def test_gives_up_after_exhausting_retries():
    puzzle = _simple_puzzle()
    client = Mock()
    # siempre invalido (comparten fila).
    client.responses.create.return_value = _fake_response({"Ada": "r0c0", "Bruno": "r0c1"})

    result = run_pipeline(puzzle, client, model="gpt-5.4", max_retries=1)

    assert result["valid"] is False
    assert result["attempts"] == 2
    assert client.responses.create.call_count == 2
    assert result["violations"]


def test_retry_message_includes_the_specific_violation():
    puzzle = _simple_puzzle()
    client = Mock()
    client.responses.create.side_effect = [
        _fake_response({"Ada": "r0c0", "Bruno": "r0c1"}),
        _fake_response({"Ada": "r0c0", "Bruno": "r1c1"}),
    ]

    run_pipeline(puzzle, client, model="gpt-5.4", max_retries=2)

    _, kwargs = client.responses.create.call_args
    retry_prompt = kwargs["input"][-1]["content"]
    assert "shares row" in retry_prompt or "shares column" in retry_prompt or "row" in retry_prompt


def test_accumulates_token_usage_across_retries():
    puzzle = _simple_puzzle()
    client = Mock()
    client.responses.create.side_effect = [
        _fake_response({"Ada": "r0c0", "Bruno": "r0c1"}, input_tokens=100, output_tokens=50),
        _fake_response({"Ada": "r0c0", "Bruno": "r1c1"}, input_tokens=120, output_tokens=60),
    ]

    result = run_pipeline(puzzle, client, model="gpt-5.4", max_retries=2)

    assert result["input_tokens"] == 220
    assert result["output_tokens"] == 110


def test_structural_violations_flags_missing_and_invented_people():
    puzzle = _simple_puzzle()
    violations = _structural_violations(puzzle, {"Ada": "r0c0", "Carmen": "r1c1"})
    assert any("faltan personas" in v for v in violations)
    assert any("no existen" in v for v in violations)


def test_structural_violations_flags_nonexistent_cell():
    puzzle = _simple_puzzle()
    violations = _structural_violations(puzzle, {"Ada": "r5c5", "Bruno": "r1c1"})
    assert any("r5c5" in v for v in violations)


def test_structural_violations_empty_when_all_ids_are_real():
    puzzle = _simple_puzzle()
    violations = _structural_violations(puzzle, {"Ada": "r0c0", "Bruno": "r1c1"})
    assert violations == []
