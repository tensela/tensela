"""Fabrication, package 3a: curves offset in their plane, and a shape cut into boards to be cut out."""
from pathlib import Path

import numpy as np
import pytest

from tensela import fabrication as F
from tensela import printing as P
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def in_english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _ring(curve: np.ndarray) -> np.ndarray:
    return F._closed_ring(curve, 1e-12)


def _hill() -> Graph:
    g = Graph()
    g.node("Series", "i", count=11, level="column")
    g.node("Series", "j", count=8, level="row")
    g.node("Formula", "x", formula="a * 0.02", a=g.nodes["i"])
    g.node("Formula", "y", formula="a * 0.134 / 7", a=g.nodes["j"])
    g.node("Formula", "z", formula="0.03 * exp(-((a - 0.12)^2 / 0.002 + (b - 0.07)^2 / 0.0012))",
           a=g.nodes["x"], b=g.nodes["y"])
    g.node("Point", "p", x=g.nodes["x"], y=g.nodes["y"], z=g.nodes["z"])
    g.node("Surface from points", "surface", points=g.nodes["p"])
    return g


def test_a_closed_curve_grows_and_shrinks_in_its_plane():
    g = Graph()
    g.node("Circle", "c", radius=0.05)
    g.node("Offset curve", "out", curve=g.nodes["c"], distance=0.01)
    r = np.linalg.norm(np.asarray(g.value("out").values)[:, :2], axis=1)
    assert r.min() == pytest.approx(0.06, rel=1e-3) and r.max() == pytest.approx(0.06, rel=1e-3)
    g.change("out", "distance", -0.06)
    with pytest.raises(Exception, match="disappears"):
        g.value("out")


def test_an_open_curve_goes_to_its_left_and_a_square_keeps_its_corners():
    g = Graph()
    g.node("Line", "l", **{"from": (0.0, 0.0, 0.0), "to": (1.0, 0.0, 0.0)})
    g.node("Offset curve", "o", curve=g.nodes["l"], distance=0.1)
    assert np.allclose(np.asarray(g.value("o").values)[:, 1], 0.1)
    g.node("Rectangle", "r", width=1.0, height=1.0)
    g.node("Edges", "e", geometry=g.nodes["r"])
    from tensela.geometry import CLOSED_CURVE
    from tensela.data import Data
    square = Data(np.asarray(g.value("r").values, float), (), "square", kind=CLOSED_CURVE)
    sharp = np.asarray(F.offset_curve(square, 0.1, 'sharp').values)
    assert np.ptp(sharp[:, 0]) == pytest.approx(1.2) and len(_ring(sharp)) == 4


def test_sections_of_a_surface_are_closed_bands_numbered_from_one():
    g = _hill()
    s = F.sections(g.value("surface"), 0.003, 0.0, 'x', 'band', 0.01)
    assert s.levels == ("section",) and s.starts == {"section": 1} and s.kind.closed
    v = np.asarray(s.values)
    assert s.sizes["section"] == 66                                   # 200 mm / 3 mm
    assert np.allclose(np.diff(v[:, 0, 0]), 0.003)                    # one beside the other
    for curve in v:
        ring = _ring(curve)
        assert np.ptp(ring[:, 0]) < 1e-9                                 # flat, in its plane
        assert 0.134 * 0.01 * 0.99 < F._area(ring[:, 1:]) < 0.134 * 0.01 * 1.2   # the field (and its hill) × depth


def test_down_to_base_all_share_the_same_base():
    g = _hill()
    s = F.sections(g.value("surface"), 0.005, 0.002, 'x', 'to base', 0.01)
    v = np.asarray(s.values)
    assert np.allclose(v[..., 2].min(axis=1), v[..., 2].min())          # the same level under all of them
    assert v[..., 2].min() == pytest.approx(-0.01, abs=1e-6)            # 10 mm under the lowest point (0)
    assert np.allclose(np.diff(v[:, 0, 0]), 0.007)                      # board and gap


def test_sections_of_a_closed_body_and_boards_with_thickness():
    g = Graph()
    g.node("Sphere", "ball", radius=0.05)
    s = F.sections(g.value("ball"), 0.01, 0.0, 'z')
    r = [np.linalg.norm(_ring(c)[:, :2], axis=1).max() for c in np.asarray(s.values)]
    assert s.sizes["section"] == 10 and max(r) == pytest.approx(0.05, rel=0.02)
    boards = F.sections(g.value("ball"), 0.01, 0.002, 'z', show='boards')
    report = P.check(P.pieces(boards), printer=None, thickness=0)[0]
    assert report.ready                                                  # each board closed, faces outwards


def test_boards_too_thin_or_too_many_are_said():
    g = _hill()
    with pytest.raises(ShapeError, match="thickness"):
        F.sections(g.value("surface"), 0.0)
    with pytest.raises(ShapeError, match="boards"):
        F.sections(g.value("surface"), 0.00005)


