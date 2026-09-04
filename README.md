# Murdoku Solver

Un puzzle de logica tipo sudoku, pero las pistas son de un caso de
asesinato en vez de numeros: cada sospechoso (y la victima) ocupa una
celda de un tablero, cada fila y columna tiene como maximo una persona,
y una pista en texto ("Estaba 2 filas al norte de Elena.") acota donde
puede estar cada uno. Colocando a todo el mundo se puede deducir quien
comparte sala con la victima -- y por tanto quien es el asesino.

El repo tiene dos partes: un generador/verificador de puzzles en Python
(`murdoku/`) y una webapp local (FastAPI) para generar, listar y jugar
esos puzzles en el navegador.

## Instalacion

Requiere Python 3.12+ y [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Copia `.env.example` a `.env` y rellena `OPENAI_API_KEY` -- solo hace
falta si vas a generar puzzles con tematica (el generador y el
verificador en si no usan ningun LLM).

## Usar la webapp

```bash
uv run python scripts/run_webapp.py
```

Abre `http://127.0.0.1:8420`. Desde ahi puedes generar un caso nuevo
(eligiendo dificultad y, opcionalmente, una tematica libre como
"piratas" o "la corte medieval"), verlo en el listado, y jugarlo
colocando a cada sospechoso y a la victima en el tablero.

Los niveles generados se guardan como JSON en `puzzles/generated/`
(no se suben al repo, ver `.gitignore`).

## Como se genera un puzzle

1. **`murdoku/generator.py`** coloca a las personas y los objetos en el
   tablero y genera pistas en texto para cada sospechoso, comprobando
   por construccion que la solucion sea unica (nunca se guarda un
   puzzle con mas de una solucion valida).
2. Si se pide una tematica, **`murdoku/reskin.py`** le pide a un LLM
   barato que traduzca los nombres genericos de objetos, salas y
   personajes a algo acorde al tema (p.ej. "silla" -> "banqueta" en un
   tema medieval). El resultado se vuelve a pasar por el mismo
   verificador que usa el resto del proyecto antes de aceptarlo: si el
   LLM repite un nombre para dos cosas distintas (lo que rompe la
   unicidad de la solucion), ese intento se descarta y se reintenta, o
   se cae de vuelta al puzzle generico si no hay forma de tematizarlo
   bien.
3. **`murdoku/render_html.py`** convierte el puzzle en una pagina HTML
   autocontenida y jugable (sin dependencias externas, todo el CSS/JS
   va embebido).

`murdoku/verifier.py` contiene las reglas del juego (filas/columnas
unicas, celdas bloqueadas, pistas satisfechas, quien es el asesino) y
es el unico sitio que decide si una solucion es valida -- tanto el
generador como el reskin como la propia webapp lo reusan en vez de
duplicar logica.

## Resolver con un LLM (evaluacion, no parte de la webapp)

`murdoku/solver.py`, `murdoku/pipeline.py` y `murdoku/orchestrator.py`
son la parte experimental del proyecto: le piden a un LLM que resuelva
un puzzle ya generado, con reintento automatico si la respuesta no es
valida, y (en el orchestrator) deciden entre un modelo barato o uno de
razonamiento segun la dificultad de las pistas. Se usan desde
`scripts/solve_with_llm.py`, `scripts/run_eval.py` y
`scripts/run_router_eval.py` para medir que tan bien resuelve un LLM
estos puzzles y a que coste -- son scripts de investigacion, no hace
falta ejecutarlos para usar la webapp.

`scripts/validate_puzzle.py` valida a mano un puzzle (y, opcionalmente,
una solucion propuesta en un JSON aparte) contra el verificador, util
para puzzles transcritos manualmente en `puzzles/local/`.

## Tests

```bash
uv run pytest
```
