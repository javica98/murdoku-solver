from typing import Annotated, Any, Literal

from pydantic import BaseModel, StringConstraints, model_validator

# Un id de celda tiene forma "r0c0" (fila 0, columna 0). Se usa como tipo
# reusable en vez de "str" a secas, para que un id mal escrito falle al
# cargar el puzzle en vez de colar un dato corrupto.
CellId = Annotated[str, StringConstraints(pattern=r"^r\d+c\d+$")]


class Cell(BaseModel):
    area: str | None
    objects: list[str] = []
    blocked: bool = False


class Clue(BaseModel):
    text: str
    structured: dict[str, Any] | None = None


class Person(BaseModel):
    id: str
    role: Literal["suspect", "victim"]
    clue: Clue | None = None
    attributes: dict[str, Any] = {}

    @model_validator(mode="after")
    def suspect_requires_clue(self) -> "Person":
        if self.role == "suspect" and self.clue is None:
            raise ValueError("a suspect must have a clue")
        return self


class Grid(BaseModel):
    rows: int
    cols: int


class Puzzle(BaseModel):
    id: str
    scenario: str
    difficulty: Literal["easy", "medium", "hard", "expert"]
    grid: Grid
    areas: dict[str, list[CellId]]
    cells: dict[CellId, Cell]
    people: list[Person]
    # None cuando el puzzle se transcribe sin resolver todavia (p.ej. para
    # que lo resuelva un LLM); el verificador compara una solucion
    # propuesta aparte, no depende de este campo.
    solution: dict[str, CellId] | None = None
    # nombre de objeto (el que este vigente ahora mismo -- generico o ya
    # retemado) -> emoji para la vista jugable. Vacio por defecto: los
    # puzzles reales transcritos a mano y los mas antiguos simplemente no
    # muestran emoji, no es un campo obligatorio.
    object_emoji: dict[str, str] = {}
