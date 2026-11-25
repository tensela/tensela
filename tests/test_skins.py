"""Skins: patterns on a surface built by managing data with named levels."""

from pathlib import Path

import numpy as np

from tensela.graph import Graph
from tensela.project_file import open_

EXAMPLES = Path(__file__).parent / "data"


def test_a_surface_between_two_rectangles_gives_the_sides_of_a_frustum():
    g = Graph()
    g.node("Rectangle", "top", width=4.0, height=4.0, origin=(-2.0, -2.0, 0.0))
    g.node("Scale", "small", geometry=g.nodes["top"], factor=0.5)
    g.node("Move", "bottom", geometry=g.nodes["small"], vector=(0.0, 0.0, -1.0))
    g.node("Merge", "both", a=g.nodes["top"], b=g.nodes["bottom"], level="section")
    g.node("Loft", "sides", curves=g.nodes["both"], along="section", smooth=False)
    s = g.value("sides")
    assert s.kind.grid is not None and s.levels == ()
    v = s.values.reshape(-1, 3)
    assert np.isclose(v[:, 2].min(), -1) and np.isclose(v[:, 2].max(), 0)
    assert np.isclose(np.abs(v[:, 0]).max(), 2)                       # it closes all round: four sides


# --- Hexagonal skin -------------------------------------------------------------------------------------

def _honeycomb(columns=8, rows=5):
    g = Graph()
    g.node("Rectangle", "r", width=10.0, height=6.0)
    g.node("Grid", "hex", rectangle=g.nodes["r"], columns=columns, rows=rows, shape="hexagons")
    return g, g.value("hex")


def test_a_honeycomb_fills_the_rectangle_with_whole_hexagons():
    _, h = _honeycomb()
    assert h.kind.name == "polygon" and h.sizes == {"row": 5, "column": 8} and h.values.shape[-2] == 6
    v = h.values.reshape(-1, 3)
    assert np.allclose(v.min(axis=0), [0, 0, 0]) and np.allclose(v.max(axis=0), [10, 6, 0])


def test_neighbouring_hexagons_share_an_edge():
    _, h = _honeycomb()
    v = h.values

    def shared(a, b):
        return sum(np.min(np.linalg.norm(b - p, axis=-1)) < 1e-9 for p in a)
    assert shared(v[0, 0], v[1, 0]) == 2                        # the one above
    assert shared(v[0, 0], v[0, 1]) == 2                        # the next column (half a hexagon higher)
    assert shared(v[1, 1], v[1, 2]) == 2


def test_a_hexagon_faces_like_the_surface_and_has_a_normal():
    g, _ = _honeycomb()
    g.node("Normal", "n", rectangle=g.nodes["hex"])
    assert np.allclose(g.value("n").values, [0, 0, 1])


def test_on_a_skin_that_goes_round_the_columns_close_without_a_seam():
    g = Graph()
    g.node("Circle", "c", radius=5.0)
    g.node("Extrude", "tower", curve=g.nodes["c"], vector=(0.0, 0.0, 10.0))
    g.node("Grid", "hex", rectangle=g.nodes["tower"], columns=12, rows=6, shape="hexagons")
    v = g.value("hex").values
    first, last = v[0, 0], v[0, -1]
    assert sum(np.min(np.linalg.norm(last - p, axis=-1)) < 1e-6 for p in first) == 2


def test_hexagons_are_even_and_flat():
    import pytest
    from tensela.data import ShapeError
    g = Graph()
    g.node("Rectangle", "r", width=10.0, height=6.0)
    g.node("Grid", "a", rectangle=g.nodes["r"], columns="0; 0,2; 1", rows=3, shape="hexagons")
    with pytest.raises(ShapeError):
        g.value("a")


# --- Responsive facade ----------------------------------------------------------------------------


# --- Weaving --------------------------------------------------------------------------------------------

