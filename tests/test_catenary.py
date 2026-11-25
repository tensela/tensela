"""Catenary: the exact shape of a cable hanging from two points."""
import math

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela.graph import Graph
from tensela.values import ShapeError


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _lengths(points):
    return np.linalg.norm(np.diff(np.asarray(points), axis=0), axis=1)


def test_it_is_the_exact_catenary():
    c = np.asarray(geo.catenary((0, 0, 0), (10, 0, 0), 20).values)     # fig. 9.16: 10 units apart, 20 long
    assert np.allclose(c[[0, -1]], [[0, 0, 0], [10, 0, 0]])
    a = 1.0                                                           # 20 = 2a·sinh(5/a)
    for _ in range(100):
        a -= (2 * a * math.sinh(5 / a) - 20) / (2 * math.sinh(5 / a) - 10 / a * math.cosh(5 / a))
    exact = a * np.cosh((c[:, 0] - 5) / a) - a * math.cosh(5 / a)
    assert np.abs(c[:, 2] - exact).max() < 1e-9
    assert _lengths(c).sum() == pytest.approx(20, rel=1e-3)           # its polyline, a hair shorter than the curve
    assert _lengths(c).std() < 1e-3 * _lengths(c).mean()              # points evenly spaced along it


def test_ends_at_different_heights_and_any_gravity():
    c = np.asarray(geo.catenary((0, 0, 0), (6, 2, 3), 9).values)
    assert np.allclose(c[-1], [6, 2, 3]) and _lengths(c).sum() == pytest.approx(9, rel=1e-3)
    assert c[:, 2].min() < -1                                          # it hangs below both ends
    sideways = np.asarray(geo.catenary((0, 0, 0), (0, 0, 4), 6, gravity=(1, 0, 0)).values)
    assert sideways[:, 0].max() > 1 and abs(sideways[:, 0].min()) < 1e-9   # it falls towards +x
    arch = np.asarray(geo.catenary((0, 0, 0), (4, 0, 0), 1.5, gravity=(0, 0, 1), length_in='times the distance')
                      .values)
    assert arch[:, 2].max() > 1 and _lengths(arch).sum() == pytest.approx(6, rel=1e-3)   # upside down: the arch


def test_taut_folded_and_very_slack():
    taut = np.asarray(geo.catenary((0, 0, 0), (4, 0, 0), 3).values)
    assert np.allclose(taut[:, 1:], 0) and np.allclose(taut[[0, -1], 0], [0, 4])     # shorter: a straight line
    folded = np.asarray(geo.catenary((0, 0, 2), (0, 0, 0), 6).values)                  # one end over the other
    assert folded[:, 2].min() == pytest.approx(-2) and _lengths(folded).sum() == pytest.approx(6)
    slack = np.asarray(geo.catenary((0, 0, 0), (1, 0, 0), 1e4).values)
    assert np.isfinite(slack).all() and slack[:, 2].min() == pytest.approx(-5000, rel=1e-3)


def test_many_cables_between_two_rows_of_points():
    g = Graph()
    g.node("Series", "k", count=5, level="cable")
    g.node("Formula", "far", formula="10 + a", a=g.nodes["k"])
    g.node("Point", "a", x=0.0, y=g.nodes["k"], z=0.0)
    g.node("Point", "b", x=g.nodes["far"], y=g.nodes["k"], z=0.0)
    g.node("Catenary", "cables", start=g.nodes["a"], end=g.nodes["b"], length=1.3, length_in="times the distance")
    cables = np.asarray(g.value("cables").values)
    assert cables.shape == (5, geo.SAMPLES + 1, 3)
    for k, cable in enumerate(cables):
        assert _lengths(cable).sum() == pytest.approx(1.3 * (10 + k), rel=1e-3)


def test_what_cannot_be_done_is_said():
    with pytest.raises(ShapeError, match="gravity"):
        geo.catenary((0, 0, 0), (1, 0, 0), 2, gravity=(0, 0, 0))
    with pytest.raises(ShapeError, match="greater than 0"):
        geo.catenary((0, 0, 0), (1, 0, 0), 0)


def test_the_length_of_curves():
    g = Graph()
    g.node("Catenary", "cable", end=(10.0, 0.0, 0.0), length=20.0)
    g.node("Length", "long", curve=g.nodes["cable"])
    assert float(g.value("long").values) == pytest.approx(20, rel=1e-3)
    g.node("Rectangle", "plan", width=4.0, height=3.0)
    g.node("Length", "perimeter", curve=g.nodes["plan"])
    assert float(g.value("perimeter").values) == pytest.approx(14)       # a closed one: its whole loop
    g.node("Circle", "ring", radius=1.0)
    g.node("Length", "round", curve=g.nodes["ring"])
    assert float(g.value("round").values) == pytest.approx(2 * math.pi, rel=1e-2)
    g.node("Box", "box")
    g.node("Length", "wrong", curve=g.nodes["box"])
    with pytest.raises(Exception, match="not a curve"):
        g.value("wrong")
