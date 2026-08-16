import random
from unittest.mock import Mock

import pytest

from murdoku.generator import (
    ATTRIBUTE_CATALOG,
    MULTI_CELL_OBJECTS,
    NON_BLOCKING_OBJECTS,
    _extremal_position_candidates,
    _place_multi_cell_object,
    assign_attributes,
    assign_clues_and_objects,
    find_all_solutions,
    generate_placement,
    generate_puzzle,
    generate_rooms,
    has_unique_solution,
    render_clue_template,
    reword_with_llm,
)
from murdoku.schema import Cell, Clue, Grid, Person, Puzzle
from murdoku.verifier import (
    check_clues_satisfied,
    check_no_blocked_cells,
    check_unique_rows_and_cols,
    identify_murderer,
    parse_cell_id,
)


def _cells_by_area(cells: dict) -> dict:
    by_area: dict = {}
    for cell_id, cell in cells.items():
        by_area.setdefault(cell.area, set()).add(cell_id)
    return by_area


def _is_connected(cell_ids: set) -> bool:
    """BFS: desde una celda cualquiera, ¿se llega a todas las demas
    moviendose solo arriba/abajo/izquierda/derecha?"""
    remaining = set(cell_ids)
    start = next(iter(remaining))
    visited = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        row, col = parse_cell_id(current)
        for r, c in [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]:
            neighbor = f"r{r}c{c}"
            if neighbor in remaining and neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    return visited == remaining


def test_placement_has_one_cell_per_person():
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=random.Random(0))
    assert set(placement.keys()) == set(people)


def test_placement_respects_unique_rows_and_cols():
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=random.Random(1))
    assert check_unique_rows_and_cols(placement) == []


def test_placement_uses_every_row_and_column_exactly_once():
    people = [f"P{i}" for i in range(9)]
    placement = generate_placement(9, 9, people, rng=random.Random(2))
    rows = {parse_cell_id(cell_id)[0] for cell_id in placement.values()}
    cols = {parse_cell_id(cell_id)[1] for cell_id in placement.values()}
    assert rows == set(range(9))
    assert cols == set(range(9))


def test_placement_is_reproducible_with_the_same_seed():
    people = ["Ada", "Bruno", "Carmen"]
    placement_a = generate_placement(3, 3, people, rng=random.Random(42))
    placement_b = generate_placement(3, 3, people, rng=random.Random(42))
    assert placement_a == placement_b


def test_rejects_non_square_grid():
    with pytest.raises(ValueError):
        generate_placement(3, 4, ["Ada", "Bruno", "Carmen"])


def test_rejects_wrong_number_of_people():
    with pytest.raises(ValueError):
        generate_placement(3, 3, ["Ada", "Bruno"])


def test_rooms_cover_every_cell_exactly_once():
    cells = generate_rooms(6, 6, ["A", "B", "C"], rng=random.Random(0))
    assert set(cells.keys()) == {f"r{r}c{c}" for r in range(6) for c in range(6)}


def test_rooms_use_exactly_the_given_area_names():
    cells = generate_rooms(6, 6, ["A", "B", "C"], rng=random.Random(0))
    assert {cell.area for cell in cells.values()} == {"A", "B", "C"}


def test_each_room_is_a_single_connected_piece():
    cells = generate_rooms(9, 9, ["A", "B", "C", "D"], rng=random.Random(7))
    for area, cell_ids in _cells_by_area(cells).items():
        assert _is_connected(cell_ids), f"area {area} is split into disconnected pieces"


def test_rooms_are_reproducible_with_the_same_seed():
    cells_a = generate_rooms(6, 6, ["A", "B"], rng=random.Random(99))
    cells_b = generate_rooms(6, 6, ["A", "B"], rng=random.Random(99))
    assert {k: v.area for k, v in cells_a.items()} == {k: v.area for k, v in cells_b.items()}


def test_rooms_rejects_more_areas_than_cells():
    with pytest.raises(ValueError):
        generate_rooms(2, 2, ["A", "B", "C", "D", "E"])


@pytest.mark.parametrize("seed", range(20))
def test_connectivity_holds_across_many_random_seeds(seed):
    # el flood fill depende del orden aleatorio de expansion; probamos
    # muchas semillas distintas para tener confianza de que no es casualidad.
    cells = generate_rooms(7, 7, ["A", "B", "C", "D", "E"], rng=random.Random(seed))
    for area, cell_ids in _cells_by_area(cells).items():
        assert _is_connected(cell_ids), f"seed={seed}: area {area} disconnected"


def _has_isolated_cell(cells: dict) -> bool:
    for cell_id, cell in cells.items():
        row, col = int(cell_id[1:cell_id.index("c")]), int(cell_id[cell_id.index("c") + 1 :])
        neighbor_ids = [
            f"r{row - 1}c{col}", f"r{row + 1}c{col}", f"r{row}c{col - 1}", f"r{row}c{col + 1}",
        ]
        neighbor_areas = {cells[n].area for n in neighbor_ids if n in cells}
        if cell.area not in neighbor_areas:
            return True
    return False


def test_no_room_has_a_single_cell_island():
    # una celda sin NINGUN vecino de su misma sala se ve como un error de
    # transcripcion en el plano jugable (lo encontramos a mano en un
    # puzzle real: una celda "aislada" en medio de otra sala).
    cells = generate_rooms(9, 9, ["A", "B", "C", "D", "E"], rng=random.Random(7))
    assert not _has_isolated_cell(cells)


@pytest.mark.parametrize("seed", range(40))
def test_no_isolated_cells_across_many_random_seeds(seed):
    cells = generate_rooms(7, 7, ["A", "B", "C", "D", "E"], rng=random.Random(seed))
    assert not _has_isolated_cell(cells), f"seed={seed}: found an isolated cell"


def _build_puzzle(
    rows: int,
    cols: int,
    cells: dict,
    placement: dict,
    clues: dict,
    person_attributes: dict | None = None,
) -> Puzzle:
    areas: dict = {}
    for cell_id, cell in cells.items():
        areas.setdefault(cell.area, []).append(cell_id)

    person_attributes = person_attributes or {}
    return Puzzle(
        id="generated_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=rows, cols=cols),
        areas=areas,
        cells=cells,
        people=[
            Person(
                id=pid,
                role="suspect",
                clue=Clue(text="...", structured=clues[pid]),
                attributes=person_attributes.get(pid, {}),
            )
            for pid in placement
        ],
    )


def test_every_person_gets_a_clue():
    rng = random.Random(5)
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=rng)
    rooms = generate_rooms(4, 4, ["A", "B"], rng=rng)
    _, clues = assign_clues_and_objects(placement, rooms, 4, 4, rng=rng)
    assert set(clues.keys()) == set(people)


def test_nobody_ends_up_placed_on_a_blocked_cell():
    rng = random.Random(6)
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena"]
    placement = generate_placement(5, 5, people, rng=rng)
    rooms = generate_rooms(5, 5, ["A", "B", "C"], rng=rng)
    cells, clues = assign_clues_and_objects(placement, rooms, 5, 5, rng=rng)
    puzzle = _build_puzzle(5, 5, cells, placement, clues)
    assert check_no_blocked_cells(puzzle, placement) == []


@pytest.mark.parametrize("seed", range(20))
def test_derived_clues_are_actually_true_according_to_our_own_verifier(seed):
    rng = random.Random(seed)
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    cells, clues = assign_clues_and_objects(placement, rooms, 6, 6, rng=rng)
    puzzle = _build_puzzle(6, 6, cells, placement, clues)

    assert check_no_blocked_cells(puzzle, placement) == []
    assert check_clues_satisfied(puzzle, placement) == []


@pytest.mark.parametrize("seed", range(30))
def test_derived_clues_hold_at_maximum_clue_density(seed):
    # con num_clues y num_relational_people altos, TODOS los tipos nuevos
    # (unique_object_on, absolute_position, any_area, negacion) entran en
    # juego a la vez -- justo donde encontramos bugs reales de
    # contaminacion entre pistas de distintas personas.
    rng = random.Random(seed)
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    person_attributes = assign_attributes(people, rng)
    cells, clues = assign_clues_and_objects(
        placement, rooms, 6, 6, rng=rng, num_clues=3, num_relational_people=6,
        person_attributes=person_attributes,
    )
    puzzle = _build_puzzle(6, 6, cells, placement, clues, person_attributes)

    assert check_no_blocked_cells(puzzle, placement) == []
    assert check_clues_satisfied(puzzle, placement) == []


def test_assign_attributes_gives_everyone_a_value_for_every_catalog_attribute():
    people = ["Ada", "Bruno", "Carmen"]
    attributes = assign_attributes(people, random.Random(0))
    assert set(attributes.keys()) == set(people)
    for person_attrs in attributes.values():
        assert set(person_attrs.keys()) == set(ATTRIBUTE_CATALOG.keys())
        for attribute, value in person_attrs.items():
            assert value in ATTRIBUTE_CATALOG[attribute]


def test_assign_attributes_is_reproducible_with_the_same_seed():
    people = ["Ada", "Bruno", "Carmen"]
    a = assign_attributes(people, random.Random(3))
    b = assign_attributes(people, random.Random(3))
    assert a == b


@pytest.mark.parametrize("seed", range(30))
def test_relational_attribute_clue_actually_gets_produced_and_holds(seed):
    # con num_relational_people = todo el mundo, relational_attribute
    # deberia aparecer tarde o temprano -- si nunca se produce, algo en
    # _available_global_types o en el dispatch esta roto en silencio.
    rng = random.Random(f"relational-attribute-{seed}")
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    person_attributes = assign_attributes(people, rng)
    cells, clues = assign_clues_and_objects(
        placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
        person_attributes=person_attributes,
    )
    puzzle = _build_puzzle(6, 6, cells, placement, clues, person_attributes)

    assert check_clues_satisfied(puzzle, placement) == [], f"seed={seed}"


def test_relational_attribute_appears_across_many_seeds():
    seen_types = set()
    for seed in range(30):
        rng = random.Random(f"relational-attribute-coverage-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        person_attributes = assign_attributes(people, rng)
        _, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
            person_attributes=person_attributes,
        )
        for structured in clues.values():
            clauses = structured.get("clauses", [structured])
            seen_types.update(c["type"] for c in clauses)
    assert "relational_attribute" in seen_types


@pytest.mark.parametrize("seed", range(30))
def test_relative_to_person_and_object_clues_hold(seed):
    rng = random.Random(f"relative-distance-{seed}")
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    person_attributes = assign_attributes(people, rng)
    cells, clues = assign_clues_and_objects(
        placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
        person_attributes=person_attributes,
    )
    puzzle = _build_puzzle(6, 6, cells, placement, clues, person_attributes)

    assert check_clues_satisfied(puzzle, placement) == [], f"seed={seed}"


def test_relative_to_person_and_relative_to_object_both_appear_across_many_seeds():
    seen_types = set()
    for seed in range(30):
        rng = random.Random(f"relative-distance-coverage-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        person_attributes = assign_attributes(people, rng)
        _, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
            person_attributes=person_attributes,
        )
        for structured in clues.values():
            clauses = structured.get("clauses", [structured])
            seen_types.update(c["type"] for c in clauses)
    assert "relative_to_person" in seen_types
    assert "relative_to_object" in seen_types


def test_relative_to_person_clue_always_carries_an_exact_distance():
    # el generador siempre debe fijar distance (el modo sin distancia es
    # solo para compatibilidad con puzzles reales transcritos a mano).
    for seed in range(20):
        rng = random.Random(f"relative-to-person-distance-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        _, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6
        )
        for structured in clues.values():
            clauses = structured.get("clauses", [structured])
            for clause in clauses:
                if clause["type"] == "relative_to_person":
                    assert isinstance(clause["distance"], int) and clause["distance"] > 0


def test_relative_to_object_never_anchors_to_a_duplicated_object():
    # si un objeto ancla una distancia y otra pista lo vuelve a colocar en
    # otra celda, la distancia dejaria de ser inequivoca.
    for seed in range(30):
        rng = random.Random(f"relative-to-object-uniqueness-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        cells, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6
        )
        anchored_objects = {
            clause["object"]
            for structured in clues.values()
            for clause in structured.get("clauses", [structured])
            if clause["type"] == "relative_to_object"
        }
        for obj in anchored_objects:
            cells_with_obj = [c for c in cells.values() if obj in c.objects]
            assert len(cells_with_obj) == 1, f"seed={seed}: {obj} appears in {len(cells_with_obj)} cells"


@pytest.mark.parametrize("seed", range(30))
def test_room_count_and_parity_clues_hold(seed):
    rng = random.Random(f"room-count-{seed}")
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    person_attributes = assign_attributes(people, rng)
    cells, clues = assign_clues_and_objects(
        placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
        person_attributes=person_attributes,
    )
    puzzle = _build_puzzle(6, 6, cells, placement, clues, person_attributes)

    assert check_clues_satisfied(puzzle, placement) == [], f"seed={seed}"


def test_room_count_and_room_parity_both_appear_across_many_seeds():
    seen_types = set()
    for seed in range(30):
        rng = random.Random(f"room-count-coverage-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        person_attributes = assign_attributes(people, rng)
        _, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
            person_attributes=person_attributes,
        )
        for structured in clues.values():
            clauses = structured.get("clauses", [structured])
            seen_types.update(c["type"] for c in clauses)
    assert "room_count" in seen_types
    assert "room_parity" in seen_types


@pytest.mark.parametrize("seed", range(30))
def test_same_axis_clue_holds(seed):
    rng = random.Random(f"same-axis-{seed}")
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    person_attributes = assign_attributes(people, rng)
    cells, clues = assign_clues_and_objects(
        placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
        person_attributes=person_attributes,
    )
    puzzle = _build_puzzle(6, 6, cells, placement, clues, person_attributes)

    assert check_clues_satisfied(puzzle, placement) == [], f"seed={seed}"


def test_same_axis_appears_across_many_seeds():
    seen_types = set()
    for seed in range(30):
        rng = random.Random(f"same-axis-coverage-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        _, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6
        )
        for structured in clues.values():
            clauses = structured.get("clauses", [structured])
            seen_types.update(c["type"] for c in clauses)
    assert "same_axis" in seen_types


def test_same_axis_never_anchors_to_a_duplicated_object():
    for seed in range(30):
        rng = random.Random(f"same-axis-uniqueness-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        cells, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6
        )
        anchored_objects = {
            clause["object"]
            for structured in clues.values()
            for clause in structured.get("clauses", [structured])
            if clause["type"] in ("relative_to_object", "same_axis")
        }
        for obj in anchored_objects:
            cells_with_obj = [c for c in cells.values() if obj in c.objects]
            assert len(cells_with_obj) == 1, f"seed={seed}: {obj} appears in {len(cells_with_obj)} cells"


@pytest.mark.parametrize("seed", range(30))
def test_extremal_position_clue_holds(seed):
    rng = random.Random(f"extremal-position-{seed}")
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    placement = generate_placement(6, 6, people, rng=rng)
    rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    person_attributes = assign_attributes(people, rng)
    cells, clues = assign_clues_and_objects(
        placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
        person_attributes=person_attributes,
    )
    puzzle = _build_puzzle(6, 6, cells, placement, clues, person_attributes)

    assert check_clues_satisfied(puzzle, placement) == [], f"seed={seed}"


def test_extremal_position_appears_across_many_seeds():
    seen_types = set()
    for seed in range(30):
        rng = random.Random(f"extremal-position-coverage-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        rooms = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        person_attributes = assign_attributes(people, rng)
        _, clues = assign_clues_and_objects(
            placement, rooms, 6, 6, rng=rng, num_clues=4, num_relational_people=6,
            person_attributes=person_attributes,
        )
        for structured in clues.values():
            clauses = structured.get("clauses", [structured])
            seen_types.update(c["type"] for c in clauses)
    assert "extremal_position" in seen_types


def test_extremal_position_never_offered_to_more_than_four_people():
    # es unica por direccion (nadie comparte fila ni columna), asi que
    # como mucho 4 personas por puzzle pueden llegar a tenerla disponible
    # (min fila, max fila, min columna, max columna).
    for seed in range(20):
        rng = random.Random(f"extremal-position-rarity-{seed}")
        people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
        placement = generate_placement(6, 6, people, rng=rng)
        eligible = [
            person_id
            for person_id, cell_id in placement.items()
            if _extremal_position_candidates(cell_id, placement)
        ]
        assert len(eligible) <= 4, f"seed={seed}: {eligible}"


def test_render_clue_template_for_relational_attribute_none_with():
    text = render_clue_template(
        {"type": "relational_attribute", "attribute": "color_pelo", "value": "moreno", "relation": "none_with"}
    )
    assert text == "Nadie mas en su sala tenia el pelo moreno."


def test_render_clue_template_for_relational_attribute_with_another():
    text = render_clue_template(
        {"type": "relational_attribute", "attribute": "gafas", "value": "con_gafas", "relation": "with_another"}
    )
    assert text == "Alguien mas en su sala llevaba gafas."


def test_render_clue_template_for_relative_to_person_without_distance():
    # compatibilidad con puzzles reales transcritos que no llevan "distance".
    text = render_clue_template({"type": "relative_to_person", "reference": "Cameron", "direction": "south"})
    assert text == "Estaba al sur de Cameron."


def test_render_clue_template_for_relative_to_person_with_exact_distance():
    text = render_clue_template(
        {"type": "relative_to_person", "reference": "Cameron", "direction": "north", "distance": 1}
    )
    assert text == "Estaba 1 fila al norte de Cameron."


def test_render_clue_template_pluralizes_distance_correctly():
    text = render_clue_template(
        {"type": "relative_to_person", "reference": "Cameron", "direction": "east", "distance": 3}
    )
    assert text == "Estaba 3 columnas al este de Cameron."


def test_render_clue_template_for_relative_to_object():
    text = render_clue_template(
        {"type": "relative_to_object", "object": "alfombra", "direction": "west", "distance": 2}
    )
    assert text == "Estaba 2 columnas al oeste de la alfombra."


def test_render_clue_template_for_room_count_exact_singular():
    text = render_clue_template({"type": "room_count", "relation": "exact", "count": 1})
    assert text == "Habia exactamente 1 persona en su sala."


def test_render_clue_template_for_room_count_exact_plural():
    text = render_clue_template({"type": "room_count", "relation": "exact", "count": 3})
    assert text == "Habia exactamente 3 personas en su sala."


def test_render_clue_template_for_room_count_at_least():
    text = render_clue_template({"type": "room_count", "relation": "at_least", "count": 2})
    assert text == "Habia al menos 2 personas en su sala."


def test_render_clue_template_for_room_parity_even():
    text = render_clue_template({"type": "room_parity", "parity": "even"})
    assert text == "El numero de personas en su sala era par."


def test_render_clue_template_for_room_parity_odd():
    text = render_clue_template({"type": "room_parity", "parity": "odd"})
    assert text == "El numero de personas en su sala era impar."


def test_render_clue_template_for_same_axis_row():
    text = render_clue_template({"type": "same_axis", "object": "alfombra", "axis": "row"})
    assert text == "Estaba en la misma fila que la alfombra."


def test_render_clue_template_for_same_axis_col():
    text = render_clue_template({"type": "same_axis", "object": "mesa", "axis": "col"})
    assert text == "Estaba en la misma columna que la mesa."


def test_render_clue_template_for_extremal_position():
    text = render_clue_template({"type": "extremal_position", "direction": "north"})
    assert text == "Era la persona mas al norte de todos."


def test_object_on_clues_use_only_non_blocking_objects():
    rng = random.Random(6)
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena"]
    placement = generate_placement(5, 5, people, rng=rng)
    rooms = generate_rooms(5, 5, ["A", "B", "C"], rng=rng)
    _, clues = assign_clues_and_objects(placement, rooms, 5, 5, rng=rng)
    for structured in clues.values():
        if structured["type"] == "object_on":
            assert structured["object"] in NON_BLOCKING_OBJECTS


def test_assign_clues_is_reproducible_with_the_same_seed():
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=random.Random(8))
    rooms = generate_rooms(4, 4, ["A", "B"], rng=random.Random(8))

    _, clues_a = assign_clues_and_objects(placement, rooms, 4, 4, rng=random.Random(1))
    _, clues_b = assign_clues_and_objects(placement, rooms, 4, 4, rng=random.Random(1))
    assert clues_a == clues_b


def test_render_clue_template_for_area():
    text = render_clue_template({"type": "area", "area": "JARDIN"})
    assert text == "Estaba en la sala JARDIN."


def test_render_clue_template_for_object_on():
    text = render_clue_template({"type": "object_on", "object": "silla"})
    assert text == "Estaba sobre una silla."


def test_render_clue_template_for_object_adjacent():
    text = render_clue_template({"type": "object_adjacent", "object": "mesa"})
    assert text == "Estaba junto a una mesa."


def test_render_clue_template_rejects_unsupported_type():
    # placeholder del backlog: "a N filas/columnas al norte/sur/este/oeste
    # de X" -- todavia no tiene plantilla ni implementacion.
    with pytest.raises(ValueError):
        render_clue_template({"type": "distance_direction", "direction": "north"})


def test_render_clue_template_joins_all_clauses_into_one_text():
    text = render_clue_template(
        {
            "type": "all",
            "clauses": [
                {"type": "area", "area": "JARDIN"},
                {"type": "object_on", "object": "silla"},
            ],
        }
    )
    assert text == "Estaba en la sala JARDIN. Estaba sobre una silla."


def test_reword_with_llm_returns_the_models_text_and_calls_the_right_model():
    # "doble" (mock) del cliente de OpenAI: no llamamos a la API de verdad,
    # solo comprobamos que nuestra funcion la usa correctamente.
    fake_content = Mock(type="output_text", text="  Descansaba junto a una mesa.  ")
    fake_message = Mock(type="message", content=[fake_content])
    fake_response = Mock(output=[fake_message])
    fake_client = Mock()
    fake_client.responses.create.return_value = fake_response

    result = reword_with_llm("Estaba junto a una mesa.", fake_client, model="gpt-5.4-nano")

    assert result == "Descansaba junto a una mesa."
    _, kwargs = fake_client.responses.create.call_args
    assert kwargs["model"] == "gpt-5.4-nano"
    assert kwargs["input"][1]["content"] == "Estaba junto a una mesa."


def _puzzle_with_four_single_cell_areas() -> Puzzle:
    # 2x2, cada celda es su propia sala: el clue "area X" solo puede
    # cumplirse en una celda concreta.
    cells = {
        "r0c0": Cell(area="A"),
        "r0c1": Cell(area="B"),
        "r1c0": Cell(area="C"),
        "r1c1": Cell(area="D"),
    }
    return Puzzle(
        id="unique_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"A": ["r0c0"], "B": ["r0c1"], "C": ["r1c0"], "D": ["r1c1"]},
        cells=cells,
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(text="...", structured={"type": "area", "area": "A"}),
            ),
            Person(
                id="Bruno",
                role="suspect",
                clue=Clue(text="...", structured={"type": "area", "area": "D"}),
            ),
        ],
    )


def test_finds_the_unique_solution_when_clues_force_it():
    puzzle = _puzzle_with_four_single_cell_areas()
    solutions = find_all_solutions(puzzle, max_solutions=5)
    assert solutions == [{"Ada": "r0c0", "Bruno": "r1c1"}]
    assert has_unique_solution(puzzle)


def _puzzle_with_an_ambiguous_solution() -> Puzzle:
    # 2x2, una sola sala que cubre todo: la pista de Ada no distingue
    # ninguna celda, y Bruno no tiene pista -- cualquiera de las 2
    # colocaciones validas sirve.
    cells = {cell_id: Cell(area="ROOM") for cell_id in ["r0c0", "r0c1", "r1c0", "r1c1"]}
    return Puzzle(
        id="ambiguous_test",
        scenario="test",
        difficulty="easy",
        grid=Grid(rows=2, cols=2),
        areas={"ROOM": list(cells.keys())},
        cells=cells,
        people=[
            Person(
                id="Ada",
                role="suspect",
                clue=Clue(text="...", structured={"type": "area", "area": "ROOM"}),
            ),
            Person(id="Bruno", role="victim"),
        ],
    )


def test_does_not_have_a_unique_solution_when_clues_are_too_loose():
    puzzle = _puzzle_with_an_ambiguous_solution()
    assert not has_unique_solution(puzzle)
    assert len(find_all_solutions(puzzle, max_solutions=5)) > 1


def test_backtracking_search_finds_the_generators_own_solution():
    # aqui las pistas son solo de celda propia (num_clues=1 con el set
    # original), asi que suelen fijar una solucion unica y la propia
    # colocacion debe aparecer entre pocas soluciones encontradas.
    rng = random.Random(0)
    people = ["Ada", "Bruno", "Carmen", "Diana"]
    placement = generate_placement(4, 4, people, rng=rng)
    rooms = generate_rooms(4, 4, ["A", "B"], rng=rng)
    cells, clues = assign_clues_and_objects(placement, rooms, 4, 4, rng=rng)
    puzzle = _build_puzzle(4, 4, cells, placement, clues)

    solutions = find_all_solutions(puzzle, max_solutions=10)
    assert placement in solutions


def test_generators_own_solution_always_satisfies_its_own_clues():
    # con pistas relacionales (with_person, alone...) un puzzle puede
    # salir ambiguo con num_clues=1, asi que la propia colocacion podria
    # no aparecer entre las primeras N que encuentra la busqueda -- pero
    # SIEMPRE tiene que superar la verificacion, sea o no unica.
    for seed in range(20):
        rng = random.Random(seed)
        people = ["Ada", "Bruno", "Carmen", "Diana"]
        placement = generate_placement(4, 4, people, rng=rng)
        rooms = generate_rooms(4, 4, ["A", "B"], rng=rng)
        cells, clues = assign_clues_and_objects(placement, rooms, 4, 4, rng=rng)
        puzzle = _build_puzzle(4, 4, cells, placement, clues)

        assert check_clues_satisfied(puzzle, placement) == [], f"seed={seed}"


def _generate(seed: int, rows: int = 5, cols: int = 5) -> Puzzle:
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena"][:rows]
    return generate_puzzle(
        rows,
        cols,
        people,
        victim_id=people[-1],
        area_names=["A", "B", "C", "D", "E"],
        scenario="Test",
        difficulty="easy",
        rng=random.Random(seed),
        num_clues=2,
        num_relational_people=2,
    )


@pytest.mark.parametrize("seed", range(10))
def test_generated_puzzle_is_fully_valid(seed):
    puzzle = _generate(seed)
    solution = puzzle.solution

    assert check_unique_rows_and_cols(solution) == []
    assert check_no_blocked_cells(puzzle, solution) == []
    assert check_clues_satisfied(puzzle, solution) == []
    assert identify_murderer(puzzle, solution) is not None
    assert has_unique_solution(puzzle)


def test_victim_has_no_clue_and_suspects_all_do():
    puzzle = _generate(seed=3)
    for person in puzzle.people:
        if person.role == "victim":
            assert person.clue is None
        else:
            assert person.clue is not None


def test_generate_puzzle_is_reproducible_with_the_same_seed():
    puzzle_a = _generate(seed=17)
    puzzle_b = _generate(seed=17)
    assert puzzle_a.solution == puzzle_b.solution
    assert puzzle_a.cells == puzzle_b.cells


def test_generate_puzzle_rejects_victim_not_in_person_ids():
    with pytest.raises(ValueError):
        generate_puzzle(
            3,
            3,
            ["Ada", "Bruno", "Carmen"],
            victim_id="Nobody",
            area_names=["A"],
            scenario="Test",
            difficulty="easy",
        )


def test_place_multi_cell_object_produces_correct_footprint_size():
    rng = random.Random(0)
    cells = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    obj = _place_multi_cell_object(cells, occupied_cells=set(), rows=6, cols=6, rng=rng)
    assert obj in MULTI_CELL_OBJECTS
    footprint = [cid for cid, c in cells.items() if obj in c.objects]
    assert len(footprint) == MULTI_CELL_OBJECTS[obj]


def test_place_multi_cell_object_stays_within_a_single_room():
    rng = random.Random(1)
    cells = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    obj = _place_multi_cell_object(cells, occupied_cells=set(), rows=6, cols=6, rng=rng)
    footprint = [cid for cid, c in cells.items() if obj in c.objects]
    areas = {cells[cid].area for cid in footprint}
    assert len(areas) == 1


def test_place_multi_cell_object_footprint_is_contiguous():
    rng = random.Random(2)
    cells = generate_rooms(7, 7, ["A", "B", "C", "D"], rng=rng)
    obj = _place_multi_cell_object(cells, occupied_cells=set(), rows=7, cols=7, rng=rng)
    footprint = {cid for cid, c in cells.items() if obj in c.objects}
    assert _is_connected(footprint)


def test_place_multi_cell_object_marks_footprint_as_blocked():
    rng = random.Random(3)
    cells = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
    obj = _place_multi_cell_object(cells, occupied_cells=set(), rows=6, cols=6, rng=rng)
    footprint = [cid for cid, c in cells.items() if obj in c.objects]
    assert all(cells[cid].blocked for cid in footprint)


def test_place_multi_cell_object_never_overlaps_occupied_cells():
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    for seed in range(20):
        rng = random.Random(f"multicell-occupied-{seed}")
        cells = generate_rooms(6, 6, ["A", "B", "C"], rng=rng)
        placement = generate_placement(6, 6, people, rng=rng)
        occupied = set(placement.values())
        obj = _place_multi_cell_object(cells, occupied, 6, 6, rng)
        if obj is None:
            continue
        footprint = {cid for cid, c in cells.items() if obj in c.objects}
        assert footprint.isdisjoint(occupied), f"seed={seed}"


def test_place_multi_cell_object_returns_none_when_nothing_fits():
    # tablero de una sola celda: no cabe ningun objeto de tamaño >= 2.
    cells = {"r0c0": Cell(area="A")}
    obj = _place_multi_cell_object(cells, occupied_cells=set(), rows=1, cols=1, rng=random.Random(0))
    assert obj is None
    assert cells["r0c0"].objects == []


@pytest.mark.parametrize("seed", range(15))
def test_generated_puzzle_with_multi_cell_object_is_fully_valid(seed):
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    puzzle = generate_puzzle(
        6, 6, people, victim_id="Francisco", area_names=["A", "B", "C"],
        scenario="Test", difficulty="medium", rng=random.Random(f"multicell-puzzle-{seed}"),
        num_clues=2, num_relational_people=2, num_multi_cell_objects=1,
    )
    solution = puzzle.solution

    assert check_unique_rows_and_cols(solution) == []
    assert check_no_blocked_cells(puzzle, solution) == []
    assert check_clues_satisfied(puzzle, solution) == []
    assert identify_murderer(puzzle, solution) is not None
    assert has_unique_solution(puzzle)


def test_multi_cell_object_actually_appears_across_many_seeds():
    people = ["Ada", "Bruno", "Carmen", "Diana", "Elena", "Francisco"]
    seen = False
    for seed in range(15):
        puzzle = generate_puzzle(
            6, 6, people, victim_id="Francisco", area_names=["A", "B", "C"],
            scenario="Test", difficulty="medium", rng=random.Random(f"multicell-coverage-{seed}"),
            num_clues=2, num_relational_people=2, num_multi_cell_objects=1,
        )
        for cell in puzzle.cells.values():
            if any(obj in MULTI_CELL_OBJECTS for obj in cell.objects):
                seen = True
                break
    assert seen
