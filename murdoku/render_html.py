import json

from murdoku.schema import Puzzle

_STOPWORDS = {"de", "del", "la", "el", "los", "las", "y", "en"}

_DIFFICULTY_LABELS = {
    "easy": "fácil",
    "medium": "medio",
    "hard": "difícil",
    "expert": "experto",
}

# Paleta de "expediente de caso" -- una tonalidad por area, ciclica si hay
# mas areas que colores. Cada tono trae su pareja clara/oscura para que
# el tablero se lea bien en ambos temas.
_ROOM_PALETTE_LIGHT = [
    {"bg": "#C9B896", "ink": "#4A3F27"},
    {"bg": "#6E8B7C", "ink": "#F4F3EA"},
    {"bg": "#C97B54", "ink": "#3A2416"},
    {"bg": "#6C7FA6", "ink": "#EDEFF6"},
    {"bg": "#B79A3B", "ink": "#2E2510"},
    {"bg": "#7C5A78", "ink": "#F3E9F2"},
]
_ROOM_PALETTE_DARK = [
    {"bg": "#4A4128", "ink": "#E4D8B0"},
    {"bg": "#3C5148", "ink": "#E5EFE9"},
    {"bg": "#7A4426", "ink": "#F3DEC9"},
    {"bg": "#384A66", "ink": "#DCE3F0"},
    {"bg": "#6B551C", "ink": "#F0E4B8"},
    {"bg": "#4E3A4C", "ink": "#EFE0EC"},
]


def _humanize_area(name: str) -> str:
    """'CIRCULO_DE_DEBATE' -> 'Circulo de debate'. Los nombres de area son
    ids internos sin acentos, asi que el resultado tampoco los lleva --
    es una limitacion cosmetica conocida, no un bug.
    """
    words = name.replace("_", " ").strip().lower().split(" ")
    out = [words[0].capitalize()] if words else []
    for word in words[1:]:
        out.append(word if word in _STOPWORDS else word.capitalize())
    return " ".join(out)


def _room_css_vars(palette: list[dict], indent: str) -> str:
    return "\n".join(
        f"{indent}--room-{i}-bg: {pair['bg']};\n{indent}--room-{i}-ink: {pair['ink']};"
        for i, pair in enumerate(palette)
    )


def _room_css_classes() -> str:
    return "\n".join(
        f"  .room-idx-{i} {{ background: var(--room-{i}-bg); color: var(--room-{i}-ink); }}"
        for i in range(len(_ROOM_PALETTE_LIGHT))
    )


def render_puzzle_html(puzzle: Puzzle) -> str:
    """Genera una pagina HTML autocontenida y jugable: un plano de la sala
    con las areas coloreadas y los objetos marcados, mas una lista de
    testigos con su pista en lenguaje natural. Un humano coloca a cada
    sospechoso en su casilla y comprueba el resultado.

    Requiere que el puzzle ya tenga solucion (el generador siempre la
    produce; un puzzle transcrito sin resolver no se puede jugar asi).
    """
    if puzzle.solution is None:
        raise ValueError("render_puzzle_html necesita un puzzle con solucion conocida")

    victim = next((p for p in puzzle.people if p.role == "victim"), None)
    if victim is None:
        raise ValueError("el puzzle no tiene victima")

    area_keys = sorted(puzzle.areas.keys())
    room_index = {area: i % len(_ROOM_PALETTE_LIGHT) for i, area in enumerate(area_keys)}

    data = {
        "scenario": puzzle.scenario,
        "caseId": puzzle.id,
        "difficulty": _DIFFICULTY_LABELS.get(puzzle.difficulty, puzzle.difficulty),
        "grid": {"rows": puzzle.grid.rows, "cols": puzzle.grid.cols},
        "areas": {name: _humanize_area(name) for name in area_keys},
        "roomIndex": room_index,
        "cells": {
            cell_id: {"area": cell.area, "objects": cell.objects, "blocked": cell.blocked}
            for cell_id, cell in puzzle.cells.items()
        },
        "people": [
            {
                "id": person.id,
                "role": person.role,
                "clue": person.clue.text if person.clue else None,
            }
            for person in puzzle.people
        ],
        "solution": puzzle.solution,
    }
    puzzle_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    html = _HTML_TEMPLATE
    html = html.replace("__PAGE_TITLE__", f"{puzzle.scenario} — {puzzle.id}")
    html = html.replace("__PUZZLE_JSON__", puzzle_json)
    html = html.replace("__ROOM_LIGHT_VARS__", _room_css_vars(_ROOM_PALETTE_LIGHT, "    "))
    html = html.replace("__ROOM_DARK_VARS__", _room_css_vars(_ROOM_PALETTE_DARK, "      "))
    html = html.replace("__ROOM_CLASSES__", _room_css_classes())
    return html


_HTML_TEMPLATE = """<title>__PAGE_TITLE__</title>
<style>
  :root {
    --paper: #EDE3CB;
    --paper-2: #E2D5B4;
    --ink: #2B2419;
    --ink-dim: #6B5F49;
    --accent: #8A2E22;
    --accent-ink: #FBF3E4;
    --line: #B9A97E;
    --blocked-hatch: rgba(43,36,25,0.16);
    --good: #4B6E45;
    --bad: #A6392F;
    --shadow: 0 1px 2px rgba(43,36,25,0.15), 0 10px 26px -14px rgba(43,36,25,0.45);
    --font-mono: ui-monospace, "Cascadia Mono", Consolas, "Courier New", monospace;
    --font-serif: "Palatino Linotype", "Book Antiqua", Palatino, "Iowan Old Style", serif;
__ROOM_LIGHT_VARS__
  }

  :root[data-theme="dark"] {
    --paper: #17140F;
    --paper-2: #201B14;
    --ink: #E9DFC7;
    --ink-dim: #A69A80;
    --accent: #E2694F;
    --accent-ink: #1B120D;
    --line: #4B4230;
    --blocked-hatch: rgba(233,223,199,0.10);
    --good: #83A579;
    --bad: #D6786D;
    --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 12px 30px -14px rgba(0,0,0,0.7);
__ROOM_DARK_VARS__
  }

  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #17140F;
      --paper-2: #201B14;
      --ink: #E9DFC7;
      --ink-dim: #A69A80;
      --accent: #E2694F;
      --accent-ink: #1B120D;
      --line: #4B4230;
      --blocked-hatch: rgba(233,223,199,0.10);
      --good: #83A579;
      --bad: #D6786D;
      --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 12px 30px -14px rgba(0,0,0,0.7);
__ROOM_DARK_VARS__
    }
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--font-serif);
    padding: 2rem 1.25rem 4rem;
    transition: background 0.2s ease, color 0.2s ease;
  }

  .case { max-width: 1080px; margin: 0 auto; }

  .masthead {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 1.5rem;
    flex-wrap: wrap;
    padding-bottom: 1.1rem;
    margin-bottom: 1.6rem;
    border-bottom: 3px double var(--line);
  }

  .case-num {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ink-dim);
    margin: 0 0 0.4rem;
  }

  h1 {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: clamp(1.5rem, 3.6vw, 2.15rem);
    letter-spacing: -0.01em;
    margin: 0;
    text-wrap: balance;
  }

  .stamp {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--accent);
    border: 2px solid var(--accent);
    padding: 0.4rem 0.8rem;
    border-radius: 2px;
    transform: rotate(-3deg);
    white-space: nowrap;
  }

  .board-wrap {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr);
    gap: 1.75rem;
    align-items: start;
  }

  @media (max-width: 800px) {
    .board-wrap { grid-template-columns: 1fr; }
  }

  .plan-panel {
    background: var(--paper-2);
    border-radius: 6px;
    box-shadow: var(--shadow);
    padding: 1.25rem;
  }

  .plan-panel h2 {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink-dim);
    margin: 0 0 0.9rem;
  }

  .grid {
    display: grid;
    gap: 3px;
    background: var(--line);
    padding: 3px;
    border-radius: 4px;
    aspect-ratio: 1;
  }

  .cell {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-mono);
    font-size: clamp(0.6rem, 1.6vw, 0.82rem);
    font-weight: 700;
    border-radius: 2px;
    cursor: pointer;
    user-select: none;
    transition: filter 0.12s ease, transform 0.08s ease;
    overflow: hidden;
  }

  .cell:hover { filter: brightness(1.08); }
  .cell:active { transform: scale(0.96); }
  .cell.blocked { cursor: not-allowed; }

  .cell.blocked::after {
    content: "";
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(45deg, var(--blocked-hatch) 0 6px, transparent 6px 12px);
  }

  .cell .obj-label {
    position: absolute;
    bottom: 2px;
    left: 3px;
    font-size: 0.52rem;
    font-weight: 400;
    letter-spacing: 0.02em;
    opacity: 0.75;
    text-transform: lowercase;
  }

  .cell .occupant {
    position: relative;
    z-index: 1;
    padding: 0.15rem 0.35rem;
    border-radius: 3px;
    background: var(--paper);
    color: var(--ink);
    box-shadow: 0 1px 3px rgba(0,0,0,0.35);
  }

  .cell.correct .occupant { outline: 2px solid var(--good); }
  .cell.incorrect .occupant { outline: 2px solid var(--bad); }

__ROOM_CLASSES__

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1.1rem;
    margin-top: 0.9rem;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    letter-spacing: 0.04em;
    color: var(--ink-dim);
  }

  .legend span { display: inline-flex; align-items: center; gap: 0.4rem; }
  .swatch { width: 0.7rem; height: 0.7rem; border-radius: 2px; display: inline-block; }

  .file-panel { display: flex; flex-direction: column; gap: 1rem; }

  .victim-card {
    background: var(--accent);
    color: var(--accent-ink);
    border-radius: 6px;
    padding: 0.85rem 1.05rem;
    box-shadow: var(--shadow);
  }

  .victim-card .role {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    opacity: 0.85;
    margin: 0 0 0.2rem;
  }

  .victim-card .name {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: 1.05rem;
    margin: 0;
  }

  .witnesses { display: flex; flex-direction: column; gap: 0.55rem; }

  .witness {
    background: var(--paper-2);
    border: 2px solid transparent;
    border-radius: 6px;
    padding: 0.7rem 0.9rem;
    cursor: pointer;
    box-shadow: var(--shadow);
    transition: border-color 0.12s ease, transform 0.08s ease;
  }

  .witness:hover { transform: translateX(2px); }
  .witness.armed { border-color: var(--accent); }
  .witness.placed { opacity: 0.6; }

  .witness-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.6rem;
    margin-bottom: 0.25rem;
  }

  .witness-name { font-family: var(--font-mono); font-weight: 700; font-size: 0.86rem; }
  .witness-loc { font-family: var(--font-mono); font-size: 0.66rem; color: var(--ink-dim); }

  .witness-statement {
    font-size: 0.86rem;
    font-style: italic;
    color: var(--ink);
    line-height: 1.4;
  }

  .hint {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--ink-dim);
    letter-spacing: 0.02em;
  }

  .controls { display: flex; gap: 0.6rem; flex-wrap: wrap; }

  button {
    font-family: var(--font-mono);
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 0.6rem 1rem;
    border-radius: 4px;
    border: 2px solid var(--ink);
    background: transparent;
    color: var(--ink);
    cursor: pointer;
    transition: background 0.12s ease, color 0.12s ease;
  }

  button:hover { background: var(--ink); color: var(--paper); }

  button.primary { border-color: var(--accent); color: var(--accent-ink); background: var(--accent); }
  button.primary:hover { filter: brightness(1.1); background: var(--accent); color: var(--accent-ink); }

  button:focus-visible, .cell:focus-visible, .witness:focus-visible {
    outline: 3px solid var(--accent);
    outline-offset: 2px;
  }

  #verdict {
    font-family: var(--font-mono);
    font-size: 0.82rem;
    padding: 0.7rem 0.9rem;
    border-radius: 4px;
    min-height: 1.2rem;
  }

  #verdict.good { background: color-mix(in srgb, var(--good) 18%, transparent); color: var(--good); }
  #verdict.bad { background: color-mix(in srgb, var(--bad) 18%, transparent); color: var(--bad); }
</style>

<div class="case">
  <header class="masthead">
    <div>
      <p class="case-num" id="case-num"></p>
      <h1 id="case-title"></h1>
    </div>
    <div class="stamp" id="case-stamp">Sin resolver</div>
  </header>

  <div class="board-wrap">
    <section class="plan-panel">
      <h2>Plano de la sala &mdash; toca una casilla para colocar (o quitar) al testigo armado</h2>
      <div class="grid" id="grid"></div>
      <div class="legend" id="legend"></div>
    </section>

    <section class="file-panel">
      <div class="victim-card">
        <p class="role">Victima</p>
        <p class="name" id="victim-name"></p>
      </div>

      <div class="witnesses" id="witnesses"></div>

      <p class="hint">Toca el nombre de un testigo para "armarlo", luego toca una casilla libre del plano para colocarlo ahi.</p>

      <div class="controls">
        <button id="verify-btn">Verificar</button>
        <button id="reset-btn">Reiniciar</button>
        <button id="reveal-btn" class="primary">Revelar solucion</button>
      </div>

      <div id="verdict"></div>
    </section>
  </div>
</div>

<script>
(function () {
  const PUZZLE = __PUZZLE_JSON__;

  const gridEl = document.getElementById("grid");
  const legendEl = document.getElementById("legend");
  const witnessesEl = document.getElementById("witnesses");
  const victimNameEl = document.getElementById("victim-name");
  const verdictEl = document.getElementById("verdict");
  const stampEl = document.getElementById("case-stamp");

  document.getElementById("case-num").textContent =
    "Expediente " + PUZZLE.caseId + " · dificultad: " + PUZZLE.difficulty;
  document.getElementById("case-title").textContent = PUZZLE.scenario;

  gridEl.style.gridTemplateColumns = "repeat(" + PUZZLE.grid.cols + ", 1fr)";
  gridEl.style.gridTemplateRows = "repeat(" + PUZZLE.grid.rows + ", 1fr)";

  const placements = {};
  let armed = null;

  const victim = PUZZLE.people.find((p) => p.role === "victim");
  const suspects = PUZZLE.people.filter((p) => p.role === "suspect");
  victimNameEl.textContent = victim.id;

  const roomClass = (area) => "room-idx-" + PUZZLE.roomIndex[area];

  Object.entries(PUZZLE.areas).forEach(([key, label]) => {
    const item = document.createElement("span");
    item.innerHTML = '<span class="swatch ' + roomClass(key) + '"></span>' + label;
    legendEl.appendChild(item);
  });

  function cellEl(cellId) {
    return gridEl.querySelector('[data-cell="' + cellId + '"]');
  }

  function renderGrid() {
    gridEl.innerHTML = "";
    for (let r = 0; r < PUZZLE.grid.rows; r++) {
      for (let c = 0; c < PUZZLE.grid.cols; c++) {
        const cellId = "r" + r + "c" + c;
        const cell = PUZZLE.cells[cellId];
        const div = document.createElement("div");
        div.className = "cell " + roomClass(cell.area) + (cell.blocked ? " blocked" : "");
        div.dataset.cell = cellId;
        div.tabIndex = cell.blocked ? -1 : 0;

        if (cell.objects.length) {
          const label = document.createElement("span");
          label.className = "obj-label";
          label.textContent = cell.objects.join(", ");
          div.appendChild(label);
        }

        if (!cell.blocked) {
          div.addEventListener("click", () => onCellClick(cellId));
          div.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onCellClick(cellId); }
          });
        }

        gridEl.appendChild(div);
      }
    }
    syncOccupants();
  }

  function syncOccupants() {
    document.querySelectorAll(".cell .occupant").forEach((el) => el.remove());
    document.querySelectorAll(".cell").forEach((el) => el.classList.remove("correct", "incorrect"));
    Object.entries(placements).forEach(([personId, cellId]) => {
      const div = cellEl(cellId);
      if (!div) return;
      const occ = document.createElement("span");
      occ.className = "occupant";
      occ.textContent = personId.slice(0, 3);
      div.appendChild(occ);
    });
  }

  function renderWitnesses() {
    witnessesEl.innerHTML = "";
    suspects.forEach((person) => {
      const card = document.createElement("div");
      card.className = "witness";
      card.tabIndex = 0;
      card.dataset.person = person.id;
      card.innerHTML =
        '<div class="witness-head">' +
          '<span class="witness-name">' + person.id + "</span>" +
          '<span class="witness-loc"></span>' +
        "</div>" +
        '<div class="witness-statement">"' + person.clue + '"</div>';
      card.addEventListener("click", () => armWitness(person.id));
      witnessesEl.appendChild(card);
    });
    syncWitnessCards();
  }

  function syncWitnessCards() {
    witnessesEl.querySelectorAll(".witness").forEach((card) => {
      const id = card.dataset.person;
      card.classList.toggle("armed", armed === id);
      const placedAt = placements[id];
      card.classList.toggle("placed", Boolean(placedAt));
      card.querySelector(".witness-loc").textContent = placedAt ? placedAt : "";
    });
  }

  function armWitness(personId) {
    armed = armed === personId ? null : personId;
    syncWitnessCards();
  }

  function onCellClick(cellId) {
    const occupantId = Object.keys(placements).find((p) => placements[p] === cellId);

    if (occupantId && !armed) {
      delete placements[occupantId];
      syncOccupants();
      syncWitnessCards();
      return;
    }

    if (!armed) return;

    Object.keys(placements).forEach((p) => {
      if (placements[p] === cellId) delete placements[p];
    });
    placements[armed] = cellId;
    armed = null;
    syncOccupants();
    syncWitnessCards();
    verdictEl.textContent = "";
    verdictEl.className = "";
  }

  function verify() {
    const total = suspects.length;
    let correct = 0;
    suspects.forEach((p) => {
      if (!placements[p.id]) return;
      const div = cellEl(placements[p.id]);
      if (placements[p.id] === PUZZLE.solution[p.id]) {
        correct++;
        if (div) div.classList.add("correct");
      } else {
        if (div) div.classList.add("incorrect");
      }
    });

    if (Object.keys(placements).length < total) {
      verdictEl.textContent = "Faltan " + (total - Object.keys(placements).length) + " testigos por colocar.";
      verdictEl.className = "";
    } else if (correct === total) {
      verdictEl.textContent = "Caso resuelto — los " + total + " testigos están en su sitio.";
      verdictEl.className = "good";
      stampEl.textContent = "Caso resuelto";
    } else {
      verdictEl.textContent = correct + " de " + total + " en el lugar correcto. Sigue investigando.";
      verdictEl.className = "bad";
    }
  }

  function reset() {
    Object.keys(placements).forEach((k) => delete placements[k]);
    armed = null;
    verdictEl.textContent = "";
    verdictEl.className = "";
    stampEl.textContent = "Sin resolver";
    syncOccupants();
    syncWitnessCards();
  }

  function reveal() {
    Object.keys(placements).forEach((k) => delete placements[k]);
    Object.entries(PUZZLE.solution).forEach(([id, cell]) => {
      if (id !== victim.id) placements[id] = cell;
    });
    syncOccupants();
    syncWitnessCards();
    verify();
  }

  document.getElementById("verify-btn").addEventListener("click", verify);
  document.getElementById("reset-btn").addEventListener("click", reset);
  document.getElementById("reveal-btn").addEventListener("click", reveal);

  renderGrid();
  renderWitnesses();
})();
</script>
"""
