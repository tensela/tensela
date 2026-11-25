"""Curves (Delivery 3, E3.3): line, circle, curve through points, points on curve."""

import numpy as np
import pytest

from tensela.connectors.obj import export_obj
from tensela.data import Data, ShapeError, series
from tensela.geometry import (
    CURVE, CLOSED_CURVE, centre, circle, curve_by_points, distance, rotate, line, move, point, curve_points,
)


def test_line():
    l = line((0, 0, 0), (10, 0, 0))
    assert l.kind == CURVE and l.values.shape == (2, 3)


def test_many_lines_by_the_single_rule():
    floors = series(4, level="piso")
    l = line(point(0, 0, floors), point(10, 0, floors))
    assert l.shape == "piso 4"


def test_circle_and_ellipse():
    c = circle(radius=3)
    assert c.kind == CLOSED_CURVE
    assert np.linalg.norm(c.values, axis=-1) == pytest.approx(np.full(64, 3.0))
    e = circle(radius=3, radius_2=1, plane='elevation')
    assert e.values[:, 0].max() == pytest.approx(3) and e.values[:, 2].max() == pytest.approx(1, abs=0.01)


def test_a_ring_per_floor_with_its_radius():
    floors = series(3, level="piso")
    rings = circle(point(0, 0, floors), radius=Data(np.array([1.0, 2.0, 3.0]), ("piso",)))
    assert rings.shape == "piso 3"
    assert np.linalg.norm(rings.values[2, :, :2], axis=-1).max() == pytest.approx(3)


def test_points_of_an_open_and_a_closed_curve():
    assert curve_points(line((0, 0, 0), (10, 0, 0)), 5).list_() == [
        [0, 0, 0], [2.5, 0, 0], [5, 0, 0], [7.5, 0, 0], [10, 0, 0]]
    p = curve_points(circle(radius=1), 4)
    assert p.shape == "punto 4"
    assert p.values[1] == pytest.approx([0, 1, 0], abs=1e-9)


def test_curve_through_points_removes_the_level():
    vertices = point(Data(np.array([0.0, 1, 1, 0]), ("vértice",)), Data(np.array([0.0, 0, 1, 1]), ("vértice",)),
                     series(3, level="piso"))
    outlines = curve_by_points(vertices, along="vértice", smooth=False, closed=True)
    assert outlines.shape == "piso 3" and outlines.kind == CLOSED_CURVE
    assert outlines.values.shape == (3, 4, 3)
    smooth = curve_by_points(vertices, along="vértice")
    assert smooth.values.shape[-2] > 4
    # The smooth curve passes through the points.
    assert any(np.allclose(q, [1, 1, 0]) for q in smooth.values[0])


def test_joining_along_the_other_level_gives_the_verticals():
    """The same points, joined by floor instead of by vertex: mullions."""
    vertices = point(Data(np.array([0.0, 1, 1, 0]), ("vértice",)), Data(np.array([0.0, 0, 1, 1]), ("vértice",)),
                     series(3, level="piso"))
    mullions = curve_by_points(vertices, along="piso", smooth=False)
    assert mullions.shape == "vértice 4"
    assert mullions.values[0][:, 2].tolist() == [0, 1, 2]


def test_distance_to_a_curve():
    c = circle(radius=3)
    assert distance(point(0, 0, 5), c).values == pytest.approx(np.hypot(3, 5), abs=0.01)
    assert distance(point(5, 0, 0), line((0, 0, 0), (10, 0, 0))).values == pytest.approx(0)


def test_curves_move_rotate_and_have_a_centre():
    c = move(circle(radius=1), (0, 0, 2))
    assert c.kind == CLOSED_CURVE and centre(c).values == pytest.approx([0, 0, 2])
    assert rotate(line((1, 0, 0), (2, 0, 0)), 90).values[1] == pytest.approx([0, 2, 0])


def test_clear_errors():
    with pytest.raises(ShapeError, match="debería ser una curva"):
        curve_points(point(1, 2, 3, name="p"), 4)
    with pytest.raises(ShapeError, match="hacen falta varios para una curva"):
        curve_by_points(point(1, 2, 3, name="p"))


def test_curves_go_to_the_obj_as_lines(tmp_path):
    text = export_obj(tmp_path / "c.obj", circle(radius=1, name="anillo")).read_text()
    lines = [l for l in text.splitlines() if l.startswith("l ")]
    assert len(lines) == 1 and lines[0].split()[1] == lines[0].split()[-1]  # closed: it goes back to the first


def test_lattice_tower_example():
    from pathlib import Path
    from tensela.project_file import open_
    g = open_(Path(__file__).parent / "data" / "torre_de_celosia.json").graph
    assert g.value('nodes').shape == "anillo 13 × barra 16 = 208"
    assert g.value('members').shape == "barra 16"
    radii = g.value('radii').values
    assert radii.argmin() == 6  # the waist, in ring 6
    g.change('nodes', "count", 24)
    assert g.value('counter members').shape == "barra 24"


def test_points_on_curve_in_its_four_modes():
    straight = line((0, 0, 0), (10, 0, 0))
    half = curve_points(straight, mode='fraction', positions=0.5)
    assert half.levels == () and np.allclose(half.values, [5, 0, 0])            # a single point: without level
    thirds = curve_points(straight, mode='fraction', positions="0,25; 0,75")
    assert np.allclose(thirds.values[:, 0], [2.5, 7.5]) and thirds.levels == ("point",)
    to_metres = curve_points(straight, mode='distance', positions=[2, -2])            # -2: 2 m from the end
    assert np.allclose(to_metres.values[:, 0], [2, 8])
    every = curve_points(straight, mode='every', distance=3)
    assert np.allclose(every.values[:, 0], [0, 3, 6, 9])
    assert curve_points(straight, 5).shape == "punto 5"                              # parts, as always
    c = circle(radius=1)                                                              # closed: it goes round
    assert np.allclose(curve_points(c, mode='fraction', positions=1.25).values,
                       curve_points(c, mode='fraction', positions=0.25).values)
    with pytest.raises(ShapeError, match="mayor que 0"):
        curve_points(straight, mode='every', distance=0)


def test_half_of_a_line_is_the_start_of_another():
    from tensela.graph import Graph
    g = Graph()
    g.node("Line", "viga", from_=(0, 0, 0), to=(8, 0, 0))
    g.node("Points on curve", "centro de la viga", curve=g.nodes["viga"], mode='fraction', positions=0.5)
    g.node("Point", "arriba", x=4, z=3)
    g.node("Line", "pie derecho", from_=g.nodes["centro de la viga"], to=g.nodes["arriba"])
    assert np.allclose(g.value("pie derecho").values, [[4, 0, 0], [4, 0, 3]])


def test_a_point_is_written_however_it_comes():
    from tensela.geometry import _point
    from tensela.values import read_value
    for text in ("0,0,0", "8, 0, 0", "8 0 0", "(8; 0; 0)"):
        assert read_value(text) == [int(text.strip("()").replace(";", ",").replace(" ", ",").split(",")[0] or 0), 0, 0]
    assert read_value("0,5") == 0.5 and read_value("10; 10; 14") == "10; 10; 14"   # a number and a list, the same
    assert np.allclose(_point("8; 0; 2,5", "p").values, [8, 0, 2.5])               # with decimal comma, with «;»
    assert np.allclose(_point("0,0,0", "p").values, [0, 0, 0])                     # a file saved like this
    with pytest.raises(ShapeError, match="tres coordenadas"):
        _point("hola", "desde")


def test_arc_by_three_points_and_by_angles():
    from tensela.geometry import arc
    a = arc('three points', (0, 0, 0), (2, 1, 0), (4, 0, 0)).values
    assert np.allclose(a[0], [0, 0, 0]) and np.allclose(a[-1], [4, 0, 0])
    assert np.linalg.norm(a - [2, 1, 0], axis=1).min() < 1e-9                       # it passes through the middle
    assert np.ptp(np.linalg.norm(a - [2, -1.5, 0], axis=1)) < 1e-9                  # a single radius
    assert arc('three points', (0, 0, 0), (2, 0, 2), (4, 0, 0)).values[:, 2].max() == pytest.approx(2)
    c = arc('centre and angles', radius=2, from_=0, to=90).values
    assert np.allclose(c[0], [2, 0, 0]) and np.allclose(c[-1], [0, 2, 0])
    with pytest.raises(ShapeError, match="línea recta"):
        arc('three points', (0, 0, 0), (3, 0, 0), (2, 0, 0))                    # the middle beyond the end


def test_a_flattened_arc_is_the_straight_line():
    from tensela.geometry import arc
    flat = arc('three points', (0, 0, 0), (1, 0, 0), (2, 0, 0)).values             # a depth of 0
    assert np.allclose(flat[:, 1:], 0) and np.allclose(flat[[0, -1]], [[0, 0, 0], [2, 0, 0]])
    from tensela.graph import Graph
    g = Graph()
    g.node("Series", "s", count=2, level="k")
    g.node("Formula", "z", formula="a * 0.5", a=g.nodes["s"])
    g.node("Point", "m", x=1.0, z=g.nodes["z"])
    g.node("Arc", "arc", start=(0, 0, 0), middle=g.nodes["m"], end=(2, 0, 0))
    some = np.asarray(g.value("arc").values)
    assert np.ptp(some[0][:, 2]) == 0 and some[1][:, 2].max() == pytest.approx(0.5)   # one flat, one curved
    ahead = arc('start, direction and end', (0, 0, 0), direction=(1, 0, 0), end=(3, 0, 0)).values
    assert np.allclose(ahead[:, 1:], 0) and np.allclose(ahead[-1], [3, 0, 0])
    with pytest.raises(ShapeError, match="detrás"):
        arc('start, direction and end', (0, 0, 0), direction=(-1, 0, 0), end=(3, 0, 0))


def test_graph_passes_the_values_through_a_drawn_curve():
    from tensela.geometry import CHARTS, evaluate_chart, chart
    x = np.linspace(0, 1, 11)
    assert np.allclose(evaluate_chart(CHARTS["linear"], x), x)
    bell = evaluate_chart(CHARTS["bell"], x)
    assert bell[5] == pytest.approx(1) and bell[0] == pytest.approx(0) and bell.max() <= 1 + 1e-9
    rise = evaluate_chart(CHARTS["smooth rise"], np.linspace(0, 1, 200))
    assert np.all(np.diff(rise) >= -1e-12)                                        # smooth, without bounces
    assert np.allclose(chart(series(5, 0, 10, "p"), CHARTS["reversed"], 0, 2).values, [2, 1.5, 1, 0.5, 0])
    with pytest.raises(ShapeError, match="2 puntos"):
        chart(series(3, 0, 1, "p"), [[0, 0]])


def test_vectors_and_random_by_count():
    from tensela.geometry import measure_vector, move, vector
    from tensela.data import on_random
    v = vector('point to point', from_=(1, 0, 0), to=(4, 4, 0))
    assert np.allclose(v.values, [3, 4, 0]) and v.kind.name == "vector"
    assert np.allclose(vector('unit', base=v).values, [0.6, 0.8, 0])
    assert np.allclose(vector('to a length', base=v, length=10).values, [6, 8, 0])
    assert np.allclose(vector('invert', base=v).values, [-3, -4, 0])
    assert np.allclose(vector("perpendicular", base=vector(x=1, y=0, z=0), other=(0, 0, 1)).values, [0, -1, 0])
    assert measure_vector('length', v).values == pytest.approx(5)
    assert measure_vector('angle', vector(x=1, y=0, z=0), (0, 0, 1)).values == pytest.approx(90)
    assert np.allclose(move(point(0, 0, 0), v).values, [3, 4, 0])                # a vector serves where a point goes
    r = on_random(mode='count', count=20, level="punto", minimum=1, maximum=5, integers=True, seed=2)
    assert r.sizes == {"punto": 20} and set(np.unique(r.values)) <= {1, 2, 3, 4, 5}
    with pytest.raises(ShapeError, match="nulo"):
        vector('unit', base=vector(x=0, y=0, z=0))


