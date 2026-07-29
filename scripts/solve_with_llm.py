import json
import os
import sys

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv
from openai import OpenAI

from murdoku.schema import Puzzle
from murdoku.solver import solve_with_llm


def main(path: str, model: str) -> None:
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY no encontrada (revisa el .env)")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    puzzle = Puzzle.model_validate(data)

    client = OpenAI()
    proposed_solution, usage = solve_with_llm(puzzle, client, model)

    print("--- Respuesta cruda del modelo ---")
    print(json.dumps(proposed_solution, ensure_ascii=False))

    print("\n--- Uso de tokens ---")
    print(f"input_tokens: {usage.input_tokens}")
    print(f"output_tokens: {usage.output_tokens}")
    if usage.output_tokens_details:
        print(f"reasoning_tokens: {usage.output_tokens_details.reasoning_tokens}")
    print(f"total_tokens: {usage.total_tokens}")

    out_path = path.replace(".json", ".llm_answer.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(proposed_solution, f, indent=2, ensure_ascii=False)
    print(f"\nSolucion propuesta guardada en: {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
