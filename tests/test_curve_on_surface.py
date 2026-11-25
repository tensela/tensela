"""Closest point on surface and Curve on surface, and the names of the levels
of Surface points."""
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import surfaces as sup
from tensela.data import Data
from tensela import optimize as O
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _sheet(formula="0"):
    """A sheet of 10 × 6 m (u along x, v along y) with heights by a formula of x and y."""
    g = Graph()
    g.node("Series", "x", count=11, start=0.0, step=1.0, level="column")
    g.node("Series", "y", count=7, start=0.0, step=1.0, level="row")
    g.node("Formula", "z", formula=formula, a=g.nodes["x"], b=g.nodes["y"])
    g.node("Point", "grid", x=g.nodes["x"], y=g.nodes["y"], z=g.nodes["z"])
    g.node("Surface from points", "sheet", points=g.nodes["grid"])
    return g


def test_the_closest_point_of_a_flat_sheet_is_straight_below():
    g = _sheet()
    g.node("Number", "xs", value=[2.5, 7.0, 12.0])
    g.node("Point", "q", x=g.nodes["xs"], y=3.0, z=2.0)
    for gives in ('point', 'u v', 'distance', 'normal'):
        g.node("Closest point on surface", gives, points=g.nodes["q"], surface=g.nodes["sheet"], gives=gives)
    assert np.allclose(g.value("point").values, [[2.5, 3, 0], [7, 3, 0], [10, 3, 0]], atol=1e-6)  # (the last: edge)
    assert np.allclose(g.value("u v").values, [[0.25, 0.5, 0], [0.7, 0.5, 0], [1, 0.5, 0]], atol=1e-6)
    assert np.allclose(g.value("distance").values, [2, 2, np.hypot(2, 2)], atol=1e-6)
    assert np.allclose(np.abs(np.asarray(g.value("normal").values)[:, 2]), 1)
    with pytest.raises(Exception, match="gives"):
        g.change("point", "gives", "colour")
        g.value("point")


def test_the_closest_point_of_a_sphere():
    g = Graph()
    g.node("Sphere", "ball", radius=3.0)
    g.node("Point", "q", x=1.0, y=2.0, z=5.0)
    g.node("Closest point on surface", "on", points=g.nodes["q"], surface=g.nodes["ball"], gives="distance")
    assert float(np.asarray(g.value("on").values)) == pytest.approx(np.sqrt(30) - 3, abs=0.01)


def test_a_curve_on_a_surface_follows_it():
    g = _sheet("sin(a * 30) + b / 4")
    g.node("Number", "us", value=[0.0, 0.5, 1.0])
    g.node("Number", "vs", value=[0.0, 0.7, 1.0])
    g.node("Point", "uv", x=g.nodes["us"], y=g.nodes["vs"])
    g.node("Curve on surface", "c", surface=g.nodes["sheet"], points=g.nodes["uv"])
    curve = np.asarray(g.value("c").values)
    on = Data(curve, ("sample",), None, kind=geo.POINT)
    back = sup.closest_on_surface(on, g.value("sheet"), 'distance')
    assert np.allclose(curve[0], [0, 0, 0], atol=1e-6) and np.allclose(curve[-1, :2], [10, 6], atol=1e-6)
    assert np.abs(np.asarray(back.values)).max() < 1e-3                            # every point of it on the sheet
    g.change("c", "smooth", False)
    straight = np.asarray(g.value("c").values)
    assert len(straight) > len(curve) // 2 and np.allclose(straight[[0, -1], :2], [[0, 0], [10, 6]], atol=1e-6)


def test_on_a_flat_sheet_the_straight_curve_measures_the_distance():
    g = _sheet()
    g.node("Number", "us", value=[0.1, 0.9])
    g.node("Number", "vs", value=[0.2, 0.8])
    g.node("Point", "uv", x=g.nodes["us"], y=g.nodes["vs"])
    g.node("Curve on surface", "c", surface=g.nodes["sheet"], points=g.nodes["uv"], smooth=False)
    g.node("Length", "L", curve=g.nodes["c"])
    assert float(np.asarray(g.value("L").values)) == pytest.approx(np.hypot(8, 3.6))


def test_surface_points_name_their_levels():
    g = Graph()
    g.node("Sphere", "ball")
    g.node("Surface points", "p", surface=g.nodes["ball"], count_u=3, count_v=4, level_u="arch")
    assert g.value("p").levels == ("arch", "v")
    g.change("p", "level_v", "arch")
    with pytest.raises(Exception, match="different names"):
        g.value("p")


