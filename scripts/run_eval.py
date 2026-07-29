import csv
import os
import random
import time

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv
from openai import OpenAI

from murdoku.generator import DIFFICULTY_TIERS, generate_puzzle_for_difficulty
from murdoku.solver import solve_with_llm
from murdoku.verifier import (
    check_clues_satisfied,
    check_no_blocked_cells,
    check_unique_rows_and_cols,
)

MODELS = ["o4-mini", "gpt-5.4"]
PUZZLES_PER_TIER = 5

# $ por 1M tokens (input, output). El output ya incluye los tokens de
# razonamiento, la API los factura juntos.
PRICING = {
    "o4-mini": {"input": 1.10, "output": 4.40},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
}

PEOPLE_NAMES = [
    "Ada", "Bruno", "Carmen", "Diana", "Elena",
    "Francisco", "Gonzalo", "Hector", "Irene",
]


def is_correct(puzzle, solution) -> bool:
    violations = (
        check_unique_rows_and_cols(solution)
        + check_no_blocked_cells(puzzle, solution)
        + check_clues_satisfied(puzzle, solution)
    )
    return len(violations) == 0


def cost_of(model: str, usage) -> float:
    price = PRICING[model]
    return (usage.input_tokens / 1_000_000) * price["input"] + (
        usage.output_tokens / 1_000_000
    ) * price["output"]


def main() -> None:
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY no encontrada (revisa el .env)")

    client = OpenAI()
    results = []

    for tier, spec in DIFFICULTY_TIERS.items():
        rows = spec["rows"]
        people = PEOPLE_NAMES[:rows]
        victim_id = people[-1]

        for i in range(PUZZLES_PER_TIER):
            rng = random.Random(f"{tier}-{i}")
            puzzle = generate_puzzle_for_difficulty(
                tier, people, victim_id=victim_id, scenario="Eval", rng=rng
            )

            for model in MODELS:
                start = time.time()
                try:
                    solution, usage = solve_with_llm(puzzle, client, model)
                    correct = is_correct(puzzle, solution)
                    cost = cost_of(model, usage)
                    input_tokens = usage.input_tokens
                    output_tokens = usage.output_tokens
                except Exception as exc:
                    correct, cost, input_tokens, output_tokens = False, 0.0, 0, 0
                    print(f"  ERROR {tier} #{i} {model}: {exc}")

                elapsed = time.time() - start
                results.append(
                    {
                        "tier": tier,
                        "puzzle": i,
                        "model": model,
                        "correct": correct,
                        "cost_usd": round(cost, 5),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "seconds": round(elapsed, 1),
                    }
                )
                status = "OK  " if correct else "FAIL"
                print(
                    f"{tier:8s} #{i} {model:10s} {status}  "
                    f"${cost:.4f}  {elapsed:.1f}s"
                )

    out_path = "puzzles/local/eval_results.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResultados guardados en {out_path}")
    print("\n=== RESUMEN ===")
    print(f"Coste total: ${sum(r['cost_usd'] for r in results):.2f}")
    for tier in DIFFICULTY_TIERS:
        for model in MODELS:
            subset = [r for r in results if r["tier"] == tier and r["model"] == model]
            n_correct = sum(r["correct"] for r in subset)
            print(f"  {tier:8s} {model:10s}: {n_correct}/{len(subset)} correctas")


if __name__ == "__main__":
    main()
