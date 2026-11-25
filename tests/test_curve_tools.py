"""Curve tools (before the surfaces): Flip curve, Cut curve, Tangent, Tangent circle and Arc leaving tangent to a
direction."""

import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.geometry import (arc, circle, circle_tangent, cut_curve, reverse_curve,
                                   line_by_direction, curve_points, tangent)
from tensela.graph import Graph


def edge():
    return line_by_direction((0, 0, 0), (1, 0, 0), 1.0)            # an edge of 1 m


def test_points_at_a_distance_from_each_end():
    """Victor's example: on an edge of 1 m, a point 10 cm from the origin and another 20 cm from the end."""
    p = curve_points(edge(), mode='distance', positions="0,1; -0,2").values
    assert np.allclose(p[:, 0], [0.1, 0.8])


def test_flip_one_and_several_curves():
    a = edge()
    assert np.allclose(reverse_curve(a).values[[0, -1]], [[1, 0, 0], [0, 0, 0]])
    assert np.allclose(reverse_curve(a, (1, 0, 0)).values, a.values)            # it already goes towards +x: it does not change
    g = Graph()
    g.node("Series", "s", count=3, level="aro")
    g.node("Circle", "aros", radius=g.nodes["s"])
    inv = reverse_curve(g.value("aros"))
    assert inv.shape == g.value("aros").shape
    assert np.allclose(inv.values[..., 0, :], g.value("aros").values[..., 0, :])   # closed: the same start
    centre = inv.values[2] - inv.values[2].mean(axis=0)
    assert np.cross(centre[0], centre[1])[2] < 0                                       # ahora gira horario


def test_flipping_by_a_direction_leaves_all_the_same_way():
    from tensela.data import Data
    from tensela.geometry import CURVE
    lines = Data(np.array([[[0, 0, 0], [2, 0, 0]], [[2, 1, 0], [0, 1, 0]]], float), ("línea",), kind=CURVE)
    going = reverse_curve(lines, (1, 0, 0)).values
    assert np.all(going[:, -1, 0] > going[:, 0, 0])                                      # both, towards +x


def test_cut_curve_in_its_modes():
    a = edge()
    assert cut_curve(a, 'parts', 4).shape == "tramo 4"
    pieces = cut_curve(a, 'every', distance=0.3).values
    assert np.allclose([t[-1, 0] - t[0, 0] for t in pieces], [0.3, 0.3, 0.3, 0.1])
    pieces = cut_curve(a, 'distance', positions="0,1; -0,2").values
    assert np.allclose([[t[0, 0], t[-1, 0]] for t in pieces], [[0, 0.1], [0.1, 0.8], [0.8, 1.0]])
    from tensela.geometry import point
    pieces = cut_curve(a, 'at points', points=point(0.5, 0.3, 0)).values          # the closest point: 0.5
    assert np.allclose([t[-1, 0] for t in pieces], [0.5, 1.0])
    with pytest.raises(ShapeError, match="trozos"):
        cut_curve(a, 'parts', 0)


def test_cutting_a_closed_curve_goes_round():
    pieces = cut_curve(circle((0, 0, 0), 1), 'fraction', positions="0,25; 0,75").values
    assert len(pieces) == 2 and np.allclose(pieces[0][0], pieces[1][-1], atol=1e-9)


def test_tangent_and_normal_of_a_circle():
    c = circle((0, 0, 0), 2)
    for f in (0.0, 0.25, 0.5):
        p = curve_points(c, mode='fraction', positions=f).values
        t = tangent(c, 'tangent', positions=f).values
        n = tangent(c, "normal", positions=f).values
        assert abs(np.dot(t, p)) < 1e-3 and np.allclose(n, -p / 2, atol=1e-3)        # normal: towards the centre
    assert tangent(edge(), mode='parts', count=5).shape == "punto 5"


def test_circle_tangent_to_a_curve():
    c = circle_tangent(edge(), radius=0.2, at=0.5).values
    assert np.allclose(c[0], [0.5, 0, 0]) and np.allclose(c.mean(axis=0), [0.5, 0.2, 0], atol=1e-9)
    assert c[:, 1].min() > -1e-9                                                     # it does not cross the edge
    d = circle_tangent(edge(), radius=0.2, at=-0.2, size='distance', side='right').values
    assert np.allclose(d.mean(axis=0), [0.8, -0.2, 0], atol=1e-9)


def test_arc_leaving_tangent():
    a = arc('start, direction and end', start=(0, 0, 0), direction=(1, 0, 0), end=(2, 2, 0)).values
    assert np.allclose(a[[0, -1]], [[0, 0, 0], [2, 2, 0]])
    assert np.allclose(np.linalg.norm(a - [0, 2, 0], axis=1), 2)                      # a quarter of a circle
    with pytest.raises(ShapeError, match="detrás"):                                   # straight ahead: a line
        arc('start, direction and end', start=(0, 0, 0), direction=(1, 0, 0), end=(-3, 0, 0))


def test_the_nodes_in_the_graph():
    g = Graph()
    g.node("Line by direction", "borde", from_=(0, 0, 0), direction=(1, 0, 0), length=4)
    g.node("Tangent", "dir", curve=g.nodes["borde"], positions=1.0)
    g.node("Arc", "sigue", mode='start, direction and end', start=(4, 0, 0), direction=g.nodes["dir"], end=(6, 2, 0))
    g.node("Circle", "toca", mode='tangent to a curve', curve=g.nodes["borde"], radius=0.5)
    g.node("Cut curve", "trozos", curve=g.nodes["borde"], count=2)
    g.node("Flip curve", "al revés", curve=g.nodes["borde"])
    for n in g.nodes:
        g.value(n)
    assert np.allclose(g.value("dir").values, [1, 0, 0])
    g.change("toca", "curve", None)
    with pytest.raises(ShapeError, match="conecta una curva"):
        g.value("toca")


def test_the_left_does_not_depend_on_the_shape_of_the_curve():
    """A wave open towards +x: its left is always +y (looking from above), whatever its shape."""
    from tensela.data import Data
    from tensela.geometry import CURVE
    for y in ([0, 4, -1, 3, 0], [0, -4, 1, -3, 0]):
        wave = Data(np.column_stack([np.arange(5.0) * 3, y, np.zeros(5)]), (), kind=CURVE)
        assert tangent(wave, "normal", positions=0.0).values[1] > 0


def test_pick_a_cut_piece_without_saying_the_level():
    """Victor: of the pieces of Cut curve, a single one to work it apart (Pick; with a single level, without writing
    it)."""
    g = Graph()
    g.node("Line by direction", "arista", from_=(0, 0, 0), direction=(1, 0, 0), length=1)
    g.node("Cut curve", "tramos", curve=g.nodes["arista"], mode='distance', positions="0,1; -0,2")
    g.node("Pick", "el del medio", data=g.nodes["tramos"], position=1)
    run = g.value("el del medio")
    assert run.kind.name == "curve" and not run.levels
    assert np.allclose(run.values[[0, -1], 0], [0.1, 0.8])
