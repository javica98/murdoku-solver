from murdoku.generator import ROW_LOCAL_CLUE_TYPES
from murdoku.pipeline import run_pipeline
from murdoku.schema import Puzzle

CHEAP_MODEL = "o4-mini"
REASONING_MODEL = "gpt-5.4"


def _is_simple_clue(structured: dict) -> bool:
    """Si esta pista (y todas sus clausulas, si es un combinador) es de
    las que dependen solo de la celda propia -- reusa exactamente la
    misma clasificacion que usa el generador para podar la busqueda de
    unicidad (`ROW_LOCAL_CLUE_TYPES`), en vez de mantener una lista
    aparte: cuando se añada un tipo de pista nuevo, clasificarlo ahi ya
    actualiza el router automaticamente.

    Cualquier tipo que no reconozcamos se trata como NO simple. Es la
    opcion segura: si alguien añade un tipo nuevo y se olvida de
    clasificarlo, el router falla hacia el razonador (mas caro pero
    fiable), no hacia el barato sobre un tipo que no sabemos si aguanta.
    """
    clue_type = structured.get("type")

    if structured.get("negate"):
        return False

    if clue_type == "any":
        return False

    if clue_type == "all":
        return all(_is_simple_clue(clause) for clause in structured.get("clauses", []))

    return clue_type in ROW_LOCAL_CLUE_TYPES


def choose_model_for_puzzle(
    puzzle: Puzzle, cheap_model: str = CHEAP_MODEL, reasoning_model: str = REASONING_MODEL
) -> str:
    """Elige un modelo para TODO el puzzle, no pista a pista.

    Resolver un Murdoku es un problema conjunto (todo el mundo comparte
    fila/columna con todo el mundo), asi que no se puede repartir la
    mitad de las personas a un modelo y la otra mitad a otro y luego
    fusionar resultados. En cuanto UNA persona tiene una pista que no es
    simple, el puzzle entero se manda al razonador.
    """
    for person in puzzle.people:
        if person.clue is None or person.clue.structured is None:
            continue
        if not _is_simple_clue(person.clue.structured):
            return reasoning_model
    return cheap_model


def solve_with_router(
    puzzle: Puzzle,
    client,
    cheap_model: str = CHEAP_MODEL,
    reasoning_model: str = REASONING_MODEL,
    max_retries: int = 2,
) -> dict:
    """Encadena el router con el pipeline de la Fase 3: elige el modelo
    segun la dificultad real de las pistas, y lo resuelve con reintento.

    Devuelve lo mismo que `run_pipeline`, mas que modelo se eligio.
    """
    model = choose_model_for_puzzle(puzzle, cheap_model, reasoning_model)
    result = run_pipeline(puzzle, client, model=model, max_retries=max_retries)
    result["model_used"] = model
    return result
