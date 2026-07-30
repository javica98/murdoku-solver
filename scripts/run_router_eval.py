import csv
import os
import random
import time

import truststore

truststore.inject_into_ssl()

import openai
from dotenv import load_dotenv
from openai import OpenAI

from murdoku.generator import DIFFICULTY_TIERS, generate_puzzle, generate_puzzle_for_difficulty
from murdoku.orchestrator import CHEAP_MODEL, REASONING_MODEL, choose_model_for_puzzle
from murdoku.pipeline import run_pipeline

PUZZLES_PER_TIER = 3

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


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICING[model]
    return (input_tokens / 1_000_000) * price["input"] + (output_tokens / 1_000_000) * price["output"]


def _run_pipeline_with_infra_retry(puzzle, client, model: str, max_infra_retries: int = 3) -> dict:
    """La API de OpenAI ha dado errores 520 de Cloudflare (infra, no
    codigo) de forma intermitente en evals largos anteriores. Reintenta
    la llamada entera unas pocas veces antes de rendirse.
    """
    for attempt in range(max_infra_retries):
        try:
            return run_pipeline(puzzle, client, model=model, max_retries=2)
        except (openai.InternalServerError, openai.APIConnectionError, openai.APITimeoutError) as exc:
            if attempt == max_infra_retries - 1:
                raise
            wait = 30
            print(f"    error de infraestructura ({exc.__class__.__name__}), reintentando en {wait}s...")
            time.sleep(wait)


def solve_and_record(puzzle, client, model: str) -> dict:
    start = time.time()
    result = _run_pipeline_with_infra_retry(puzzle, client, model)
    elapsed = time.time() - start
    return {
        "model": model,
        "valid": result["valid"],
        "attempts": result["attempts"],
        "cost_usd": round(cost_of(model, result["input_tokens"], result["output_tokens"]), 5),
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "seconds": round(elapsed, 1),
    }


OUT_PATH = "puzzles/local/router_eval_results.csv"
CSV_FIELDS = [
    "puzzle_set", "tier", "puzzle", "approach", "model", "valid",
    "cost_usd", "input_tokens", "output_tokens", "seconds", "attempts",
]


def _load_existing_results() -> list[dict]:
    if not os.path.exists(OUT_PATH):
        return []
    with open(OUT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["puzzle"] = int(row["puzzle"])
        row["valid"] = row["valid"] == "True"
        row["cost_usd"] = float(row["cost_usd"])
        row["input_tokens"] = int(row["input_tokens"])
        row["output_tokens"] = int(row["output_tokens"])
        row["seconds"] = float(row["seconds"])
        row["attempts"] = int(row["attempts"])
    return rows


def _save_results(results: list[dict]) -> None:
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(results)


def run_case(label: str, tier: str, index: int, puzzle, client, results: list[dict]) -> None:
    already_done = {(r["puzzle_set"], r["tier"], r["puzzle"]) for r in results}
    if (label, tier, index) in already_done:
        print(f"{label:8s} {tier:8s} #{index}  (ya hecho, se salta)")
        return

    routed_model = choose_model_for_puzzle(puzzle, cheap_model=CHEAP_MODEL, reasoning_model=REASONING_MODEL)
    routed = solve_and_record(puzzle, client, routed_model)

    if routed_model == REASONING_MODEL:
        # el router ya eligio el razonador -- es el mismo baseline, no
        # hace falta pagar una segunda llamada identica.
        baseline = dict(routed)
    else:
        baseline = solve_and_record(puzzle, client, REASONING_MODEL)

    for approach, row in (("routed", routed), ("baseline_gpt-5.4", baseline)):
        results.append(
            {
                "puzzle_set": label,
                "tier": tier,
                "puzzle": index,
                "approach": approach,
                **row,
            }
        )
        status = "OK  " if row["valid"] else "FAIL"
        print(
            f"{label:8s} {tier:8s} #{index} {approach:17s} {row['model']:10s} {status}  "
            f"${row['cost_usd']:.4f}  {row['seconds']:.1f}s  (attempts={row['attempts']})"
        )

    _save_results(results)


def main() -> None:
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY no encontrada (revisa el .env)")

    client = OpenAI()
    results: list[dict] = _load_existing_results()
    if results:
        print(f"Reanudando: {len(results)} filas ya en {OUT_PATH}")

    for tier, spec in DIFFICULTY_TIERS.items():
        rows = spec["rows"]
        people = PEOPLE_NAMES[:rows]
        victim_id = people[-1]
        area_names = [f"AREA_{i}" for i in range(spec["num_areas"])]

        for i in range(PUZZLES_PER_TIER):
            # tal y como esta afinado el tier (siempre con personas
            # relacionales) -- deberia enrutar siempre al razonador.
            rng = random.Random(f"router-eval-tiered-{tier}-{i}")
            tiered_puzzle = generate_puzzle_for_difficulty(
                tier, people, victim_id=victim_id, scenario="Eval router", rng=rng
            )
            run_case("tiered", tier, i, tiered_puzzle, client, results)

            # mismo tamano de tablero pero sin personas relacionales --
            # deberia enrutar al modelo barato, para poder medir el
            # ahorro real cuando las pistas son simples.
            rng2 = random.Random(f"router-eval-simple-{tier}-{i}")
            simple_puzzle = generate_puzzle(
                rows,
                spec["cols"],
                people,
                victim_id,
                area_names,
                "Eval router simple",
                tier,
                rng=rng2,
                num_clues=spec["num_clues"],
                num_relational_people=0,
            )
            run_case("simple", tier, i, simple_puzzle, client, results)

    print(f"\nResultados guardados en {OUT_PATH}")
    print("\n=== RESUMEN ===")
    print(f"Coste total del experimento: ${sum(r['cost_usd'] for r in results):.2f}")
    for label in ("tiered", "simple"):
        for approach in ("routed", "baseline_gpt-5.4"):
            subset = [r for r in results if r["puzzle_set"] == label and r["approach"] == approach]
            n_correct = sum(r["valid"] for r in subset)
            cost = sum(r["cost_usd"] for r in subset)
            print(
                f"  {label:8s} {approach:17s}: {n_correct}/{len(subset)} correctas, "
                f"${cost:.4f} total"
            )


if __name__ == "__main__":
    main()
