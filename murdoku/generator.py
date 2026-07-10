import random

from murdoku.schema import Cell
from murdoku.verifier import parse_cell_id


def _orthogonal_neighbor_ids(cell_id: str, rows: int, cols: int) -> list[str]:
    row, col = parse_cell_id(cell_id)
    candidates = [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]
    return [f"r{r}c{c}" for r, c in candidates if 0 <= r < rows and 0 <= c < cols]


def generate_rooms(
    rows: int, cols: int, area_names: list[str], rng: random.Random | None = None
) -> dict[str, Cell]:
    """Reparte todas las celdas de la rejilla entre las salas dadas.

    Usa un crecimiento por inundacion aleatorio: cada sala parte de una
    celda semilla y, en cada ronda, reclama una celda vecina libre al azar.
    Esto garantiza que cada sala quede como una unica pieza conectada.
    """
    if rng is None:
        rng = random.Random()

    all_cell_ids = [f"r{r}c{c}" for r in range(rows) for c in range(cols)]
    if len(area_names) > len(all_cell_ids):
        raise ValueError("more areas than cells")

    seeds = rng.sample(all_cell_ids, len(area_names))
    cell_area: dict[str, str] = dict(zip(seeds, area_names))
    unclaimed = set(all_cell_ids) - set(cell_area)

    frontiers = {
        area: set(_orthogonal_neighbor_ids(seed, rows, cols)) & unclaimed
        for area, seed in zip(area_names, seeds)
    }

    while unclaimed:
        areas_order = area_names.copy()
        rng.shuffle(areas_order)
        for area in areas_order:
            candidates = frontiers[area] & unclaimed
            if not candidates:
                continue
            chosen = rng.choice(sorted(candidates))
            cell_area[chosen] = area
            unclaimed.discard(chosen)
            frontiers[area].discard(chosen)
            frontiers[area].update(set(_orthogonal_neighbor_ids(chosen, rows, cols)) & unclaimed)

    return {
        cell_id: Cell(area=area, objects=[], blocked=False)
        for cell_id, area in cell_area.items()
    }


def generate_placement(
    rows: int, cols: int, person_ids: list[str], rng: random.Random | None = None
) -> dict[str, str]:
    """Coloca cada persona en una celda distinta, sin repetir fila ni columna.

    Requiere una rejilla cuadrada con tantas personas como filas/columnas
    (la regla base del juego: una persona por fila y por columna).
    """
    if rows != cols:
        raise ValueError(f"grid must be square, got {rows} rows and {cols} cols")
    if len(person_ids) != rows:
        raise ValueError(
            f"expected {rows} people for a {rows}x{cols} grid, got {len(person_ids)}"
        )

    if rng is None:
        rng = random.Random()

    shuffled_people = person_ids.copy()
    rng.shuffle(shuffled_people)

    columns = list(range(cols))
    rng.shuffle(columns)

    return {
        person_id: f"r{row}c{col}"
        for row, (person_id, col) in enumerate(zip(shuffled_people, columns))
    }
