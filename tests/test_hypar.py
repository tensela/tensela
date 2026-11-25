"""Hypar."""
from pathlib import Path

import numpy as np
import pytest

from tensela import hypar as H
from tensela import language
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _panels(columns=2, rows=2):
    g = Graph()
    g.node("Rectangle", "r", width=2.0, height=2.0)
    g.node("Grid", "p", rectangle=g.nodes["r"], columns=columns, rows=rows)
    return g.value("p")


def test_a_square_folds_into_a_saddle_and_opens_flat():
    panels = _panels()
    edges = np.asarray(H.hypar(panels, 0.3, show='longest edge').values)
    assert np.allclose(edges, np.hypot(1.0, 0.3))                             # the lifted corner lengthens its edges
    piece = np.asarray(H.hypar(panels, 0.3).values)[0, 0]
    assert piece[:, 2].min() == pytest.approx(0) and piece[:, 2].max() == pytest.approx(0.3)
    centre = piece[len(piece) // 2]
    assert centre[2] == pytest.approx(0.15)                                   # a saddle: half way at the middle
    flat = np.asarray(H.hypar(panels, 0.3, show='flat piece').values)[0, 0]
    folded = np.asarray(H.hypar(panels, 0.3, show='flat piece').values)       # (the same for every panel)
    assert np.allclose(flat[:, 2], 0) and np.allclose(folded, folded[0, 0])
    assert np.allclose(np.linalg.norm(np.roll(flat, -1, 0) - flat, axis=1), np.hypot(1.0, 0.3))   # edges kept
    assert np.allclose(flat[0], 0) and flat[1, 1] == pytest.approx(0)          # its longest edge along x
    fold = np.asarray(H.hypar(panels, 0.3, show='fold').values)[0, 0]
    assert np.allclose(fold[:, 2], 0)                                         # the fold joins the corners that stay
    flat_open = np.asarray(H.hypar(panels, 0.0, show='flat piece').values)[0, 0]
    assert np.allclose(np.ptp(flat_open, axis=0)[:2], [1.0, 1.0])             # without lift: the panel itself


def test_one_lift_per_panel_and_the_other_corners():
    panels = _panels()
    lifts = Data(np.array([[0.0, 0.1], [0.2, 0.3]]), ("row", "column"), None)
    edges = np.asarray(H.hypar(panels, lifts, show='longest edge').values)
    assert np.allclose(edges, np.hypot(1.0, [[0.0, 0.1], [0.2, 0.3]]))
    other = np.asarray(H.hypar(panels, 0.3, corners='second and fourth').values)[0, 0]
    first = np.asarray(H.hypar(panels, 0.3).values)[0, 0]
    assert not np.allclose(other, first)
    g = Graph()
    g.node("Box", "b")
    with pytest.raises(ShapeError, match="four corners"):
        H.hypar(g.value("b"), 0.1)


