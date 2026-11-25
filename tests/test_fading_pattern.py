"""The trims of the diamonds and the fading pattern."""

from pathlib import Path

import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.images import folder
from tensela.mesh_tools import mesh_edges, mesh_faces
from tensela.polygons import _clean
from tensela.project_file import open_

EXAMPLES = Path(__file__).parent / "data"


def _area(cells) -> float:
    v = np.asarray(cells.values).reshape((-1,) + cells.values.shape[-2:])
    return sum(np.linalg.norm(np.cross(c := _clean(x), np.roll(c, -1, axis=0)).sum(axis=0)) / 2 for x in v)


def _grid(shape, columns, rows, base="rectangle"):
    g = Graph()
    if base == "rectangle":
        g.node("Rectangle", "base", width=16.0, height=7.0)
    else:                                                  # a cylinder: a skin that goes round
        g.node("Circle", "plan", radius=3.0)
        g.node("Extrude", "base", curve=g.nodes["plan"], vector=(0.0, 0.0, 6.0))
    g.node("Grid", "g", rectangle=g.nodes["base"], columns=columns, rows=rows, shape=shape)
    return g.value("g")


@pytest.mark.parametrize("columns, rows", [(23, 11), (8, 5), (3, 4), (1, 1), (1, 2)])
def test_the_diamonds_and_their_trims_cover_the_rectangle_without_overlapping(columns, rows):
    diamonds, trims = _grid("diamonds", columns, rows), _grid("diamond trims", columns, rows)
    assert _area(diamonds) + _area(trims) == pytest.approx(16 * 7)
    assert trims.levels == ("trim",) and trims.values.shape[-2] == 3


def test_the_trims_face_the_same_way_as_the_diamonds():
    g = Graph()
    g.node("Rectangle", "r", width=16.0, height=7.0)
    g.node("Grid", "t", rectangle=g.nodes["r"], columns=6, rows=3, shape="diamond trims")
    g.node("Normal", "n", rectangle=g.nodes["t"])
    assert np.allclose(g.value("n").values[:, 2], 1)


def test_on_a_skin_that_goes_round_only_the_bottom_and_the_top_are_trimmed():
    trims = _grid("diamond trims", 8, 4, base="cylinder")
    z = trims.values[..., 2]
    assert np.all((z.min(axis=-1) < 1e-9) | (z.max(axis=-1) > 6 - 1e-9))
    assert len(trims.values) == 8 + 1 + 8                    # bottom: n − 1 between and 2 corners; top: n


def test_the_trims_are_flat_panels_and_even():
    with pytest.raises(ShapeError):
        g = Graph()
        g.node("Circle", "plan", radius=3.0)
        g.node("Extrude", "base", curve=g.nodes["plan"], vector=(0.0, 0.0, 6.0))
        g.node("Grid", "g", rectangle=g.nodes["base"], columns=4, rows=2, shape="diamond trims", panels="curved")
        g.value("g")
    with pytest.raises(ShapeError):
        _grid("diamond trims", "0; 0.3; 1", 3)


