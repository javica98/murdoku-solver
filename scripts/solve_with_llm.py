import json
import os
import sys

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv
from openai import OpenAI

from murdoku.schema import Puzzle

SYSTEM_PROMPT = """Eres un detective resolviendo un puzzle de logica tipo sudoku.

Reglas del juego:
- Cada persona (sospechosos + victima) ocupa una celda distinta del tablero.
- Ninguna fila ni columna puede tener mas de una persona.
- Las celdas bloqueadas no pueden ocuparse.
- Cada sospechoso tiene una pista en texto que describe donde estaba.
- Debes cumplir TODAS las pistas a la vez.

Devuelve UNICAMENTE un JSON con este formato, sin explicacion adicional:
{"Nombre1": "rXcY", "Nombre2": "rXcY", ...}
"""


def build_solver_view(puzzle: Puzzle) -> dict:
    view = puzzle.model_dump(exclude={"solution"})
    for person in view["people"]:
        clue = person.get("clue")
        if clue:
            clue.pop("structured", None)
    return view


def main(path: str, model: str) -> None:
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY no encontrada (revisa el .env)")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    puzzle = Puzzle.model_validate(data)
    solver_view = build_solver_view(puzzle)

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=[
            {"type": "message", "role": "developer", "content": SYSTEM_PROMPT},
            {
                "type": "message",
                "role": "user",
                "content": json.dumps(solver_view, ensure_ascii=False),
            },
        ],
    )

    answer_text = ""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    answer_text += content.text

    print("--- Respuesta cruda del modelo ---")
    print(answer_text)

    usage = response.usage
    print("\n--- Uso de tokens ---")
    print(f"input_tokens: {usage.input_tokens}")
    print(f"output_tokens: {usage.output_tokens}")
    if usage.output_tokens_details:
        print(f"reasoning_tokens: {usage.output_tokens_details.reasoning_tokens}")
    print(f"total_tokens: {usage.total_tokens}")

    proposed_solution = json.loads(answer_text)
    out_path = path.replace(".json", ".llm_answer.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(proposed_solution, f, indent=2, ensure_ascii=False)
    print(f"\nSolucion propuesta guardada en: {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
