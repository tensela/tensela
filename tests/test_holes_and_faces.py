"""R6 (filtering leaves holes), compare, pick; prism, faces, normal, thicken (for E03)."""

from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.data import Data, ShapeError, apply, compare, pick, filter_, pairs, reduce
from tensela.geometry import (
    BLOCK, BOX, RECTANGLE, faces, centre, thicken, move, normal, prism, point, rectangle, remap,
    grid,
)

EXAMPLES = Path(__file__).parent / "data"


def table():
    return Data(np.arange(12.0).reshape(3, 4), ("fila", "columna"), "tabla")


def extension(vertices):
    v = np.asarray(vertices)
    return v.max(axis=0) - v.min(axis=0)


# --- R6: filtrar deja huecos ---------------------------------------------------

def test_filtering_moves_nothing():
    t = table()
    f = filter_(t, compare(t, 5, 'less'))
    assert f.shape == "fila 3 × columna 4 = 5 (7 vacíos)"
    assert f.list_() == [[0.0, 1.0, 2.0, 3.0], [4.0, None, None, None], [None, None, None, None]]


def test_reversed_filter_is_the_complement():
    t = table()
    near = compare(t, 5, 'less')
    a, b = filter_(t, near), filter_(t, near, reverse=True)
    assert a.count + b.count == 12
    assert not np.any(a.mask & b.mask)


def test_holes_pass_through_the_computations():
    f = filter_(table(), compare(table(), 5, 'less'))
    double = apply(lambda x: x * 2, f)
    assert double.empty == 7
    assert double.list_()[1] == [8.0, None, None, None]


def test_reduce_ignores_the_empty():
    f = filter_(table(), compare(table(), 5, 'less'))
    assert reduce(f, 'sum', along="columna").list_() == [6.0, 4.0, None]
    assert reduce(f, 'tally').values == 5
    assert reduce(f, 'maximum').values == 4.0


def test_a_condition_per_facade_holds_for_its_panels():
    panels = Data(np.zeros((2, 3)), ("fachada", "panel"), "paneles")
    yes_no = Data(np.array([True, False]), ("fachada",), "trabajar")
    assert filter_(panels, yes_no).list_() == [[0.0, 0.0, 0.0], [None, None, None]]


def test_pairs_with_an_empty_stay_empty():
    d = filter_(Data(np.arange(4.0), ("eje",)), Data(np.array([True, True, False, True]), ("eje",)))
    assert pairs(d, "eje").list_() == [[0.0, 1.0], None, None]


# --- Compare and pick -----------------------------------------------------------

def test_compare_gives_yes_or_no():
    c = compare(table(), 5, 'greater or equal')
    assert c.values.dtype == bool
    assert int(c.values.sum()) == 7
    with pytest.raises(ShapeError, match="No conozco la comparación «casi»"):
        compare(table(), 5, "casi")


def test_pick_by_number_and_by_word():
    t = table()
    assert pick(t, "fila", 1).list_() == [4.0, 5.0, 6.0, 7.0]
    assert pick(t, "columna", "último").list_() == [3.0, 7.0, 11.0]
    assert pick(t, "fila", "primero").shape == "columna 4"


def test_pick_uses_the_user_numbering():
    floors = Data(np.arange(5.0), ("piso",), "pisos", starts={"piso": -2})
    assert pick(floors, "piso", 0).values == 2.0  # the ground floor
    with pytest.raises(ShapeError) as error:
        pick(floors, "piso", 3)
    assert str(error.value) == "«piso» 3 no existe en «pisos»: va de -2 a 2."


# --- Prisma, caras, normal, engrosar ---------------------------------------------

def test_prism_with_its_corner_at_the_origin():
    p = prism(15, 20, 30, origin=(1, 2, 0))
    assert p.kind == BOX
    v = p.values
    assert v.min(axis=0) == pytest.approx([1, 2, 0])
    assert v.max(axis=0) == pytest.approx([16, 22, 30])


def test_faces_by_name_face_outwards():
    p = prism(15, 20, 30, name="volumen")
    f = faces(p, 'façades', level="fachada")
    assert f.kind == RECTANGLE and f.shape == "fachada 4"
    n = normal(f).values
    assert n == pytest.approx(np.array([[0, -1, 0], [1, 0, 0], [0, 1, 0], [-1, 0, 0]]))
    assert normal(faces(p, 'roof')).values[0] == pytest.approx([0, 0, 1])


def test_the_grid_of_a_face_starts_bottom_left_seen_from_outside():
    east = faces(prism(15, 20, 30), 'east')
    c = centre(grid(east, columns=10, rows=10)).values[0]
    assert c[0, 0] == pytest.approx([15, 1, 1.5])    # bottom, on the south side
    assert c[0, 9] == pytest.approx([15, 19, 1.5])   # bottom, on the north side


def test_faces_clear_errors():
    with pytest.raises(ShapeError, match="No conozco la cara «arriba»"):
        faces(prism(1, 1, 1), "techo, arriba")
    with pytest.raises(ShapeError, match="debería ser una caja o un prisma"):
        faces(rectangle(1, 1, name="plano"), 'south')


def test_thicken_outwards_and_inwards():
    south = faces(prism(10, 10, 10), 'south')
    outside, inside = thicken(south, 2), thicken(south, -2)
    assert outside.kind == BLOCK
    assert outside.values[0][:, 1].min() == pytest.approx(-2) and outside.values[0][:, 1].max() == pytest.approx(0)
    assert inside.values[0][:, 1].min() == pytest.approx(0) and inside.values[0][:, 1].max() == pytest.approx(2)


def test_move_a_distance_in_a_direction():
    p = move(point(1, 1, 1), vector=(0, 10, 0), distance=-3)
    assert p.values == pytest.approx([1, -2, 1])


def test_remap_with_automatic_range_ignores_the_empty():
    d = filter_(Data(np.array([1.0, 2.0, 3.0, 50.0]), ("panel",)), Data(np.array([True, True, True, False]), ("panel",)))
    r = remap(d, (None, None), (0, 10))
    assert r.list_() == [0.0, 5.0, 10.0, None]


# --- A third case -----------------------------------------------------


