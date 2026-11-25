"""Plates."""
import math
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import mesh_tools
from tensela import plates as P
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _hinge(degrees: float, flip: bool = False):
    """Two squares of 1 m hinged along the x axis, the angle between them `degrees`."""
    a = math.radians(degrees)
    points = Data(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                            [1, math.cos(a), math.sin(a)], [0, math.cos(a), math.sin(a)]], float), ("v",), None,
                  kind=geo.POINT)
    second = [0, 5, 4, 1] if not flip else [0, 1, 4, 5]                        # one face turned the other way
    return mesh_tools.mesh(points, [[0, 1, 2, 3], second])


@pytest.mark.parametrize("degrees", [45.0, 90.0, 135.0, 170.0])
def test_the_gap_is_the_same_at_any_angle(degrees):
    t, g = 0.018, 0.012
    plates = P.plates(_hinge(degrees), t, g)
    v = np.asarray(plates.values)
    first, second = v[:8], v[8:]                                              # the two prisms, 8 corners each
    nearest = np.linalg.norm(first[:, None] - second[None], axis=-1).min()
    assert nearest == pytest.approx(g, abs=1e-9)
    assert float(P.plates(_hinge(degrees), t, g, show='angles').values[0]) == pytest.approx(degrees)
    assert float(P.plates(_hinge(degrees), t, g, show='setbacks').values[0]) == pytest.approx(P.setback(
        math.radians(degrees), t, g))


def test_the_way_a_face_looks_does_not_matter_and_the_box():
    assert np.allclose(P.plates(_hinge(60.0, flip=True), show='angles').values, 60.0)
    g = Graph()
    g.node("Box", "b", width=1.0, depth=1.0, height=1.0)
    outlines = np.asarray(P.plates(g.value("b"), 0.012, 0.01, show='outlines').values)
    s = P.setback(math.pi / 2, 0.012, 0.01)
    assert outlines.shape == (6, 4, 3) and np.allclose(np.ptp(outlines[0], axis=0).max(), 1 - 2 * s)
    with pytest.raises(ShapeError, match="faces"):
        P.plates(geo.line((0, 0, 0), (1, 0, 0)))
    with pytest.raises(ShapeError, match="too small"):
        P.plates(g.value("b"), 0.5, 0.6)


