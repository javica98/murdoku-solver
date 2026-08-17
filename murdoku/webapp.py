import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI

from murdoku.generator import DIFFICULTY_TIERS, generate_puzzle_for_difficulty
from murdoku.render_html import render_puzzle_html
from murdoku.reskin import reskin_puzzle
from murdoku.schema import Puzzle

load_dotenv()

PUZZLES_DIR = Path("puzzles/generated")
PEOPLE_NAMES = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco", "Gonzalo", "Hector", "Irene"]
_DIFFICULTY_LABELS = {"easy": "Facil", "medium": "Medio", "hard": "Dificil", "expert": "Experto"}

app = FastAPI(title="Murdoku Solver")


def _client() -> OpenAI:
    return OpenAI()


# ---------- almacenamiento de niveles generados ----------


def _save_puzzle_record(puzzle: Puzzle, theme: str) -> str:
    puzzle_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    PUZZLES_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "id": puzzle_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "theme": theme,
        "puzzle": puzzle.model_dump(),
    }
    (PUZZLES_DIR / f"{puzzle_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return puzzle_id


def _load_puzzle_record(puzzle_id: str) -> dict | None:
    path = PUZZLES_DIR / f"{puzzle_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _list_puzzle_records() -> list[dict]:
    if not PUZZLES_DIR.exists():
        return []
    records = []
    for path in sorted(PUZZLES_DIR.glob("*.json"), reverse=True):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return records


def _delete_puzzle_record(puzzle_id: str) -> bool:
    path = PUZZLES_DIR / f"{puzzle_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def _rename_puzzle_record(puzzle_id: str, new_name: str) -> bool:
    record = _load_puzzle_record(puzzle_id)
    if record is None:
        return False
    record["puzzle"]["scenario"] = new_name
    (PUZZLES_DIR / f"{puzzle_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


# ---------- estilo compartido entre Inicio / Listado / Generador ----------
# (la vista de Jugar usa su propio HTML autocontenido via render_puzzle_html)

_BASE_CSS = """
  :root {
    --paper: #EDE3CB; --paper-2: #E2D5B4; --ink: #2B2419; --ink-dim: #6B5F49;
    --accent: #8A2E22; --accent-ink: #FBF3E4; --line: #B9A97E;
    --shadow: 0 1px 2px rgba(43,36,25,0.15), 0 10px 26px -14px rgba(43,36,25,0.45);
    --font-mono: ui-monospace, "Cascadia Mono", Consolas, "Courier New", monospace;
    --font-serif: "Palatino Linotype", "Book Antiqua", Palatino, "Iowan Old Style", serif;
  }
  :root[data-theme="dark"] {
    --paper: #17140F; --paper-2: #201B14; --ink: #E9DFC7; --ink-dim: #A69A80;
    --accent: #E2694F; --accent-ink: #1B120D; --line: #4B4230;
    --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 12px 30px -14px rgba(0,0,0,0.7);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #17140F; --paper-2: #201B14; --ink: #E9DFC7; --ink-dim: #A69A80;
      --accent: #E2694F; --accent-ink: #1B120D; --line: #4B4230;
      --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 12px 30px -14px rgba(0,0,0,0.7);
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: var(--font-serif); padding: 2.5rem 1.25rem 4rem;
  }
  .page { max-width: 640px; margin: 0 auto; }
  .masthead {
    padding-bottom: 1.2rem; margin-bottom: 2rem; border-bottom: 3px double var(--line);
  }
  .eyebrow {
    font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.16em;
    text-transform: uppercase; color: var(--ink-dim); margin: 0 0 0.5rem;
  }
  h1 {
    font-family: var(--font-mono); font-weight: 700; font-size: clamp(1.5rem, 4vw, 2rem);
    margin: 0; letter-spacing: -0.01em;
  }
  .big-actions { display: flex; flex-direction: column; gap: 1rem; }
  .big-btn {
    display: block; text-decoration: none; font-family: var(--font-mono); font-weight: 700;
    font-size: 1rem; letter-spacing: 0.03em; text-transform: uppercase;
    padding: 1.3rem 1.5rem; border-radius: 8px; border: 2px solid var(--ink);
    color: var(--ink); background: var(--paper-2); box-shadow: var(--shadow);
    transition: transform 0.08s ease, background 0.12s ease, color 0.12s ease;
  }
  .big-btn:hover { background: var(--ink); color: var(--paper); transform: translateY(-1px); }
  .big-btn .sub {
    display: block; font-family: var(--font-serif); font-weight: 400; font-style: italic;
    font-size: 0.8rem; text-transform: none; letter-spacing: 0; margin-top: 0.3rem; opacity: 0.75;
  }
  .card-list { display: flex; flex-direction: column; gap: 0.7rem; }
  .card {
    background: var(--paper-2); border-radius: 6px; padding: 0.9rem 1.1rem 0.7rem;
    box-shadow: var(--shadow); border: 2px solid transparent;
    transition: border-color 0.12s ease;
  }
  .card:hover { border-color: var(--accent); }
  .card-link {
    display: block; text-decoration: none; color: var(--ink);
    transition: transform 0.08s ease;
  }
  .card-link:hover { transform: translateX(2px); }
  .card .title { font-family: var(--font-mono); font-weight: 700; font-size: 0.95rem; margin: 0 0 0.2rem; }
  .card .meta { font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-dim); letter-spacing: 0.03em; }
  .card-actions {
    display: flex; gap: 0.6rem; margin-top: 0.7rem; padding-top: 0.6rem;
    border-top: 1px solid var(--line);
  }
  .card-actions form { display: contents; }
  .card-btn {
    font-family: var(--font-mono); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.04em;
    text-transform: uppercase; text-decoration: none; background: none; border: none;
    color: var(--ink-dim); cursor: pointer; padding: 0.2rem 0;
  }
  .card-btn:hover { color: var(--ink); text-decoration: underline; }
  .card-btn.danger:hover { color: var(--accent); }
  .empty {
    font-family: var(--font-mono); font-size: 0.85rem; color: var(--ink-dim);
    padding: 2rem 1rem; text-align: center; border: 2px dashed var(--line); border-radius: 6px;
  }
  form { display: flex; flex-direction: column; gap: 1.3rem; }
  label {
    font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--ink-dim); display: block; margin-bottom: 0.5rem;
  }
  select, input[type="text"] {
    width: 100%; font-family: var(--font-serif); font-size: 1rem; padding: 0.7rem 0.85rem;
    border-radius: 6px; border: 2px solid var(--line); background: var(--paper-2); color: var(--ink);
  }
  .hint { font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-dim); margin-top: 0.4rem; }
  button.submit {
    font-family: var(--font-mono); font-weight: 700; font-size: 0.9rem; letter-spacing: 0.05em;
    text-transform: uppercase; padding: 1rem; border-radius: 8px; border: 2px solid var(--accent);
    background: var(--accent); color: var(--accent-ink); cursor: pointer;
  }
  button.submit:hover { filter: brightness(1.08); }
  .back-link {
    display: inline-block; margin-top: 1.5rem; font-family: var(--font-mono); font-size: 0.75rem;
    color: var(--ink-dim); text-decoration: none;
  }
  .back-link:hover { color: var(--ink); }
"""


def _shell(title: str, eyebrow: str, body: str) -> str:
    return f"""<title>{title}</title>
<style>{_BASE_CSS}</style>
<div class="page">
  <header class="masthead">
    <p class="eyebrow">{eyebrow}</p>
    <h1>{title}</h1>
  </header>
  {body}
</div>
"""


# ---------- rutas ----------


@app.get("/", response_class=HTMLResponse)
def inicio() -> str:
    body = """
    <div class="big-actions">
      <a class="big-btn" href="/niveles">Ver niveles
        <span class="sub">Repasa los casos que ya has generado</span>
      </a>
      <a class="big-btn" href="/generar">Generar nivel
        <span class="sub">Elige tamano y tematica para un caso nuevo</span>
      </a>
    </div>
    """
    return _shell("Murdoku Solver", "Expediente central", body)


@app.get("/niveles", response_class=HTMLResponse)
def listado_niveles() -> str:
    records = _list_puzzle_records()
    if not records:
        body = '<p class="empty">Todavia no has generado ningun nivel.</p>'
    else:
        cards = []
        for record in records:
            puzzle = record["puzzle"]
            theme = record.get("theme") or "clasico"
            difficulty_label = _DIFFICULTY_LABELS.get(puzzle["difficulty"], puzzle["difficulty"])
            cards.append(f"""
            <div class="card">
              <a class="card-link" href="/jugar/{record['id']}">
                <p class="title">{puzzle['scenario']}</p>
                <p class="meta">{difficulty_label} &middot; tema: {theme} &middot; {record['created_at']}</p>
              </a>
              <div class="card-actions">
                <a class="card-btn" href="/niveles/{record['id']}/editar">Editar nombre</a>
                <form method="post" action="/niveles/{record['id']}/borrar"
                      onsubmit="return confirm('¿Borrar este nivel? No se puede deshacer.');">
                  <button class="card-btn danger" type="submit">Borrar</button>
                </form>
              </div>
            </div>
            """)
        body = f'<div class="card-list">{"".join(cards)}</div>'
    body += '<a class="back-link" href="/">&larr; Inicio</a>'
    return _shell("Niveles generados", "Listado", body)


@app.get("/niveles/{puzzle_id}/editar", response_class=HTMLResponse)
def editar_nombre_form(puzzle_id: str) -> HTMLResponse:
    record = _load_puzzle_record(puzzle_id)
    if record is None:
        return HTMLResponse(_shell("No encontrado", "Error", "<p>Ese nivel no existe.</p>"), status_code=404)

    current_name = record["puzzle"]["scenario"]
    body = f"""
    <form method="post" action="/niveles/{puzzle_id}/editar">
      <div>
        <label for="name">Nombre del caso</label>
        <input type="text" name="name" id="name" value="{current_name}" required>
      </div>
      <button class="submit" type="submit">Guardar</button>
    </form>
    <a class="back-link" href="/niveles">&larr; Cancelar</a>
    """
    return HTMLResponse(_shell("Editar nombre", "Nivel " + puzzle_id, body))


@app.post("/niveles/{puzzle_id}/editar")
def editar_nombre_submit(puzzle_id: str, name: str = Form(...)) -> RedirectResponse:
    new_name = name.strip() or "Caso generado"
    _rename_puzzle_record(puzzle_id, new_name)
    return RedirectResponse(url="/niveles", status_code=303)


@app.post("/niveles/{puzzle_id}/borrar")
def borrar_nivel(puzzle_id: str) -> RedirectResponse:
    _delete_puzzle_record(puzzle_id)
    return RedirectResponse(url="/niveles", status_code=303)


@app.get("/generar", response_class=HTMLResponse)
def generar_form() -> str:
    options = "".join(
        f'<option value="{key}">{_DIFFICULTY_LABELS[key]}</option>' for key in DIFFICULTY_TIERS
    )
    body = f"""
    <form method="post" action="/generar">
      <div>
        <label for="name">Nombre del caso (opcional)</label>
        <input type="text" name="name" id="name" placeholder="p.ej. El misterio del vestuario">
        <p class="hint">Si se deja en blanco, se llama "Caso generado".</p>
      </div>
      <div>
        <label for="difficulty">Dificultad</label>
        <select name="difficulty" id="difficulty">{options}</select>
      </div>
      <div>
        <label for="theme">Tematica (opcional)</label>
        <input type="text" name="theme" id="theme" placeholder="p.ej. pokemon, piratas, la corte medieval">
        <p class="hint">Si se deja en blanco, se genera con los nombres genericos de siempre.</p>
      </div>
      <button class="submit" type="submit">Generar caso</button>
    </form>
    <a class="back-link" href="/">&larr; Inicio</a>
    """
    return _shell("Generar nivel", "Nuevo expediente", body)


@app.post("/generar")
def generar_submit(
    difficulty: str = Form(...), theme: str = Form(""), name: str = Form("")
) -> RedirectResponse:
    if difficulty not in DIFFICULTY_TIERS:
        difficulty = "easy"

    scenario = name.strip() or "Caso generado"
    rows = DIFFICULTY_TIERS[difficulty]["rows"]
    people = PEOPLE_NAMES[:rows]
    puzzle = generate_puzzle_for_difficulty(
        difficulty, people, victim_id=people[-1], scenario=scenario
    )

    theme = theme.strip()
    if theme:
        puzzle = reskin_puzzle(puzzle, theme, _client())

    puzzle_id = _save_puzzle_record(puzzle, theme)
    return RedirectResponse(url=f"/jugar/{puzzle_id}", status_code=303)


@app.get("/jugar/{puzzle_id}", response_class=HTMLResponse)
def jugar(puzzle_id: str) -> HTMLResponse:
    record = _load_puzzle_record(puzzle_id)
    if record is None:
        return HTMLResponse(_shell("No encontrado", "Error", "<p>Ese nivel no existe.</p>"), status_code=404)

    puzzle = Puzzle.model_validate(record["puzzle"])
    html = render_puzzle_html(puzzle)
    return HTMLResponse(html)
