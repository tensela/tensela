"""The Koch curve with a group that repeats itself."""

import time
from pathlib import Path

import numpy as np
import pytest

from tensela.graph import Graph
from tensela.project_file import open_


def _lengths(lines) -> np.ndarray:
    return np.linalg.norm(lines[..., 1, :] - lines[..., 0, :], axis=-1)


def test_a_part_of_a_straight_line_is_a_straight_line():
    g = Graph()
    g.node("Line", "line", from_=(0.0, 0.0, 0.0), to=(9.0, 0.0, 0.0))
    g.node("Part of curve", "third", curve=g.nodes["line"], from_=1 / 3, to=2 / 3)
    assert np.allclose(g.value("third").values, [[3, 0, 0], [6, 0, 0]])
    g.node("Circle", "circle", radius=2.0)
    g.node("Part of curve", "arc", curve=g.nodes["circle"], from_=0.0, to=0.25)
    assert len(g.value("arc").values) > 2                      # a curve keeps its points


def test_the_edges_of_a_rectangle_all_turn_the_same_way():
    """Prueba 71: each edge goes the way its face goes round, so a Koch step puts every peak on the same side."""
    from tensela import geometry as G
    from tensela.meshes import edges
    sides = np.asarray(edges(G.rectangle(10, 6)).values, float)[..., :2]
    assert sides.tolist() == [[[0, 0], [10, 0]], [[10, 0], [10, 6]], [[10, 6], [0, 6]], [[0, 6], [0, 0]]]
    box = edges(G.box(2, 3, 4))
    assert box.sizes["edge"] == 12
