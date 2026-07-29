import json

from murdoku.schema import Puzzle

SYSTEM_PROMPT = """Eres un detective resolviendo un puzzle de logica tipo sudoku.

Reglas del juego:
- Cada persona (sospechosos + victima) ocupa una celda distinta del tablero.
- Cada fila y columna puede tener como maximo una persona (sospechoso o
  victima).
- Cada celda tiene un campo "blocked". Las celdas con "blocked": true NO se
  pueden ocupar bajo ninguna circunstancia, aunque parezcan encajar con una
  pista. Objetos como estanterias, mesas o plantas normalmente bloquean la
  celda (nadie puede estar de pie sobre ellos); alfombras y sillas no.
- Cada sospechoso tiene una pista en texto que describe donde estaba.
- Debes cumplir TODAS las pistas a la vez.
- Antes de dar tu respuesta final, revisa DOS VECES tu propia respuesta: (1)
  que ninguna fila ni columna se repita entre las personas elegidas, y (2)
  que ninguna celda elegida tenga "blocked": true.

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


def solve_with_llm(puzzle: Puzzle, client, model: str, reasoning_effort: str = "high"):
    """Le pasa el puzzle (solo lo que veria el solver) al modelo y devuelve
    la solucion propuesta como dict persona->celda, junto con el uso de
    tokens reportado por la API.
    """
    solver_view = build_solver_view(puzzle)

    response = client.responses.create(
        model=model,
        reasoning={"effort": reasoning_effort},
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

    proposed_solution = json.loads(answer_text)
    return proposed_solution, response.usage
