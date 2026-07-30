import json

from murdoku.schema import Puzzle
from murdoku.solver import SYSTEM_PROMPT, build_solver_view
from murdoku.verifier import (
    check_clues_satisfied,
    check_no_blocked_cells,
    check_unique_rows_and_cols,
)

RETRY_MESSAGE_TEMPLATE = """Tu respuesta no es valida. Estos son los problemas encontrados:
{violations}

Corrige tu respuesta y devuelve UNICAMENTE el JSON corregido, con el mismo formato de antes."""


def _structural_violations(puzzle: Puzzle, solution: dict) -> list[str]:
    """Guardrails de dominio: antes de aplicar las reglas del juego,
    comprueba que la respuesta del modelo se refiera a datos que
    realmente existen en el puzzle (no personas ni celdas inventadas).
    """
    violations = []
    valid_person_ids = {person.id for person in puzzle.people}
    valid_cell_ids = set(puzzle.cells.keys())

    missing = valid_person_ids - set(solution.keys())
    extra = set(solution.keys()) - valid_person_ids
    if missing:
        violations.append(f"faltan personas en la respuesta: {sorted(missing)}")
    if extra:
        violations.append(f"personas que no existen en el puzzle: {sorted(extra)}")

    for person_id, cell_id in solution.items():
        if cell_id not in valid_cell_ids:
            violations.append(f"{person_id} esta colocado en una celda que no existe: {cell_id!r}")

    return violations


def _all_violations(puzzle: Puzzle, solution: dict) -> list[str]:
    structural = _structural_violations(puzzle, solution)
    if structural:
        # si hay ids inventados, no tiene sentido aplicar las reglas del
        # juego sobre datos que ni siquiera existen en el puzzle.
        return structural

    return (
        check_unique_rows_and_cols(solution)
        + check_no_blocked_cells(puzzle, solution)
        + check_clues_satisfied(puzzle, solution)
    )


def run_pipeline(
    puzzle: Puzzle, client, model: str, max_retries: int = 2, reasoning_effort: str = "high"
) -> dict:
    """Resuelve un puzzle con reintento: si la respuesta del modelo falla
    la verificacion (o los guardrails de dominio), se le explica
    exactamente que violo y se le pide que lo corrija, hasta
    `max_retries` veces mas.

    Devuelve un dict con la solucion final, si es valida, cuantos
    intentos hicieron falta, y el uso de tokens acumulado en toda la
    conversacion (incluidos los reintentos).
    """
    solver_view = build_solver_view(puzzle)
    conversation = [
        {"type": "message", "role": "developer", "content": SYSTEM_PROMPT},
        {
            "type": "message",
            "role": "user",
            "content": json.dumps(solver_view, ensure_ascii=False),
        },
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    solution: dict | None = None
    violations: list[str] = []

    for attempt in range(max_retries + 1):
        response = client.responses.create(
            model=model,
            reasoning={"effort": reasoning_effort},
            input=conversation,
        )

        answer_text = ""
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        answer_text += content.text

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        try:
            solution = json.loads(answer_text)
        except json.JSONDecodeError:
            solution = None
            violations = ["la respuesta no es un JSON valido"]
        else:
            violations = _all_violations(puzzle, solution)

        if not violations:
            return {
                "solution": solution,
                "valid": True,
                "attempts": attempt + 1,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            }

        conversation.append({"type": "message", "role": "assistant", "content": answer_text})
        conversation.append(
            {
                "type": "message",
                "role": "user",
                "content": RETRY_MESSAGE_TEMPLATE.format(
                    violations="\n".join(f"- {v}" for v in violations)
                ),
            }
        )

    return {
        "solution": solution,
        "valid": False,
        "attempts": max_retries + 1,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "violations": violations,
    }
