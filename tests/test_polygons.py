"""Polygons, random points and 3D Voronoi (exercise bank: EX 4 and EX 5)."""

from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.connectors.obj import export_obj
from tensela.data import ShapeError, on_random
from tensela.geometry import real_faces, centre, frame, prism
from tensela.polygons import points_random, voronoi_3d

EXAMPLES = Path(__file__).parent / "data"


def _volume(cells) -> float:
    """The volume enclosed by all the faces (divergence theorem)."""
    total = 0.0
    for pos in np.argwhere(cells.mask):
        v = cells.values[tuple(pos)]
        for face in real_faces(cells.kind, v):
            p = v[face]
            total += sum(np.dot(p[0], np.cross(p[a], p[a + 1])) for a in range(1, len(p) - 1)) / 6
    return total


def test_the_voronoi_fills_the_box_without_gaps_or_overlaps():
    box = prism(20, 20, 20)
    cells = voronoi_3d(points_random(box, 11, 1), box)
    assert cells.shape.startswith("celda 11 × cara ") and cells.kind.polygon
    assert _volume(cells) == pytest.approx(8000)


def test_the_same_seed_gives_the_same_and_another_not():
    box = prism(10, 6, 4)
    a, b, c = points_random(box, 5, 3), points_random(box, 5, 3), points_random(box, 5, 4)
    assert np.array_equal(a.values, b.values) and not np.array_equal(a.values, c.values)
    assert (a.values >= 0).all() and (a.values[:, 0] <= 10).all() and (a.values[:, 2] <= 4).all()
    n = on_random(a, "point", 0, 1, 7)
    assert n.shape == "punto 5" and np.array_equal(n.values, on_random(a, "point", 0, 1, 7).values)


def test_the_centre_of_a_polygon_does_not_count_the_padding():
    box = prism(20, 20, 20)
    cells = voronoi_3d(points_random(box, 6, 2), box)
    c = centre(cells)
    for pos in np.argwhere(cells.mask):
        v = cells.values[tuple(pos)]
        real = v[real_faces(cells.kind, v)[0]]
        assert np.allclose(c.values[tuple(pos)], real.mean(axis=0))


def test_the_voronoi_warns():
    box = prism(1, 1, 1)
    with pytest.raises(ShapeError, match="deberían ser puntos"):
        voronoi_3d(box, box)
    with pytest.raises(ShapeError, match="1 o más"):
        points_random(box, 0)
    with pytest.raises(ShapeError, match="«abertura»"):
        frame(voronoi_3d(points_random(box, 3), box), width=0.1)


def test_part_of_curve_and_twist():
    from tensela.data import Data
    from tensela.geometry import circle, curve_part, twist
    arcs = curve_part(circle(radius=20.0), Data([0.1, 0.6], ("mitad",)), Data([0.5, 1.0], ("mitad",)))
    assert arcs.shape == "mitad 2" and not arcs.kind.closed
    # (the circle is a 64-sided polygon: the point falls on a chord, less than 5 cm from the circle)
    assert np.allclose(arcs.values[0, 0], [20 * np.cos(0.2 * np.pi), 20 * np.sin(0.2 * np.pi), 0], atol=0.05)
    assert np.allclose(arcs.values[0, -1], [-20, 0, 0], atol=1e-6) and np.allclose(arcs.values[1, -1], [20, 0, 0], atol=1e-6)
    # Twist: at the bottom it does not turn; at the top, what was asked; the height does not change.
    post = Data(np.array([[[1.0, 0, 0], [1.0, 0, 10]]]), ("poste",), kind=arcs.kind)
    t = twist(post, 90)
    assert np.allclose(t.values[0, 0], [1, 0, 0]) and np.allclose(t.values[0, 1], [0, 1, 10])


def test_twist_from_a_height_and_with_several_twists():
    from tensela.data import Data
    from tensela.geometry import CURVE, twist
    post = Data(np.array([[[1.0, 0, 0], [1.0, 0, 5], [1.0, 0, 10]]]), ("poste",), kind=CURVE)
    t = twist(post, Data([90.0, 180.0], ("cinta",)), from_=0.5)
    assert t.shape == "poste 1 × cinta 2 = 2"
    assert np.allclose(t.values[0, 0, 1], [1, 0, 5])                   # below «from», it does not turn
    assert np.allclose(t.values[0, 0, 2], [0, 1, 10]) and np.allclose(t.values[0, 1, 2], [-1, 0, 10])


def test_scale_by_axes():
    from tensela.geometry import scale_by_axes, rectangle
    e = scale_by_axes(rectangle(4, 2), 2.0, 0.5)
    assert np.allclose(e.values, [[-2, 0.5, 0], [6, 0.5, 0], [6, 1.5, 0], [-2, 1.5, 0]])


def test_rounded_rectangle_and_cap():
    from tensela.geometry import rounded_rectangle, cap
    c = rounded_rectangle(25, 15, 3.7, (-12.5, -7.5, 0))
    assert c.kind.closed and np.allclose(c.values.min(axis=0), [-12.5, -7.5, 0])
    assert np.allclose(c.values.max(axis=0), [12.5, 7.5, 0])
    t = cap(c)
    assert t.kind.grid is not None and np.allclose(t.values[0], 0, atol=1e-9)   # it starts at the centre


def test_coordinate_project_and_merge():
    from tensela.geometry import coordinate, join, line, project, surface_by_sections
    high_line = line((0, 0, 5), (10, 0, 7))
    tread = project(high_line)
    assert np.allclose(tread.values[..., 2], 0) and np.allclose(tread.values[..., :2], high_line.values[..., :2])
    together = join(high_line, tread, "altura")
    assert together.shape == "altura 2" and surface_by_sections(together, "altura").kind.grid is not None
    from tensela.data import Data
    from tensela.geometry import POINT
    p = Data(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]), ("punto",), kind=POINT)
    assert coordinate(p, "y").values.tolist() == [2.0, 5.0]
    with pytest.raises(ShapeError, match="de lo mismo"):
        join(high_line, p, "x")


def _distance_a_curve(point, curve):
    return float(np.linalg.norm(curve - np.asarray(point, float), axis=1).min())


def test_drawn_curve_modes_and_degree():
    from tensela.geometry import SAMPLES_BY_RUN, drawn_curve
    p = [[-12, -3, 0], [-6, 1, 0], [-5.5, 1.2, 0], [6, -1, 0], [12, 4, 2]]   # uneven, as by hand
    for k in (2, 3, 4, 5):
        c = drawn_curve(p, 'through points', k).values
        assert max(_distance_a_curve(q, c) for q in p) < 1e-6           # it passes through all
        closed = drawn_curve(p, 'through points', k, closed=True)
        assert closed.kind.closed and max(_distance_a_curve(q, closed.values) for q in p) < 1e-6
    assert drawn_curve(p, 'by control points', 3).levels == ()                # a single curve, without levels
    c = drawn_curve(p, 'by control points', 3).values
    assert np.allclose(c[0], p[0]) and np.allclose(c[-1], p[-1])         # control: it touches the ends…
    assert _distance_a_curve(p[2], c) > 0.05                             # …and not those in the middle
    assert drawn_curve(p, 'by control points', 3, closed=True).kind.closed
    assert np.allclose(drawn_curve(p, 'through points', 1).values[::SAMPLES_BY_RUN], p)  # degree 1: polyline
    # Really smooth: between two consecutive samples the direction turns little (no straight spans with breaks).
    c = drawn_curve(p, 'through points', 3).values
    d = np.diff(c, axis=0)
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    assert np.degrees(np.arccos(np.clip((d[1:] * d[:-1]).sum(axis=1), -1, 1))).max() < 12
    assert len(drawn_curve(p[:2], 'through points', 3).values) > 2   # two points: a straight span, without error
    with pytest.raises(Exception, match="3 o más"):
        drawn_curve(p[:2], closed=True)


def test_drawn_curve_from_an_old_file(tmp_path):
    import json
    filepath = tmp_path / "vieja.json"
    filepath.write_text(json.dumps({"parametrico": 1, "nodos": {"c": {"tipo": "Curva dibujada", "suave": False,
                                "puntos": [[0, 0, 0], [1, 1, 0], [2, 0, 0]]}}, "exportar": ["c"]}))
    g = open_(filepath).graph
    assert g.nodes["c"].inputs["degree"] == 1 and g.value("c").kind.curve


