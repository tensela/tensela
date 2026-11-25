"""The Voronoi on a plane and the Voronoi skin."""

from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.mesh_tools import delaunay, mesh_edges, mesh_faces
from tensela.polygons import _clean, kind_polygon, voronoi
from tensela.project_file import open_


def _area(cells: Data) -> float:
    total = 0.0
    for c in np.asarray(cells.values).reshape((-1,) + cells.values.shape[-2:]):
        c = _clean(c)
        total += np.linalg.norm(np.cross(c, np.roll(c, -1, axis=0)).sum(axis=0)) / 2
    return total


def _seeds(n=30, seed=2, w=10.0, h=6.0, z=0.0):
    rng = np.random.default_rng(seed)
    return Data(np.column_stack([rng.uniform(0, w, n), rng.uniform(0, h, n), np.full(n, z)]), ("point",),
                kind=G.POINT)


def _rectangle(w=10.0, h=6.0):
    g = Graph()
    g.node("Rectangle", "r", width=w, height=h)
    return g.value("r")


def test_the_cells_fill_the_rectangle_without_overlapping():
    cells = voronoi(_seeds(), _rectangle())
    assert cells.levels == ("cell",) and len(cells.values) == 30
    assert _area(cells) == pytest.approx(60.0)


def test_each_point_of_a_cell_is_closer_to_its_seed():
    seeds = _seeds(12, 5)
    cells = voronoi(seeds, _rectangle())
    s = seeds.values
    for i, c in enumerate(cells.values):
        inside = _clean(c).mean(axis=0)
        assert np.argmin(np.linalg.norm(s - inside, axis=1)) == i


def test_with_a_radius_no_cell_goes_farther_than_it():
    seeds = _seeds()
    cells = voronoi(seeds, _rectangle(), radius=0.8)
    for s, c in zip(seeds.values, cells.values):
        assert np.linalg.norm(c - s, axis=1).max() <= 0.8 + 1e-6
    assert _area(cells) < 60.0


def test_without_a_boundary_a_rectangle_a_little_larger():
    cells = voronoi(_seeds())
    v = cells.values.reshape(-1, 3)
    assert v[:, 0].min() < 0 and v[:, 0].max() > 10 and len(cells.values) == 30


def test_a_boundary_with_a_corner_going_in():
    ell = np.array([[0, 0, 0], [10, 0, 0], [10, 3, 0], [4, 3, 0], [4, 6, 0], [0, 6, 0]], float)
    boundary = Data(ell, (), kind=kind_polygon(6))
    seeds = _seeds(40, 7)
    cells = voronoi(seeds, boundary)
    assert _area(cells) == pytest.approx(10 * 3 + 4 * 3)
    assert len(cells.values) < 40                       # the seeds in the missing corner have no cell


def test_the_cells_lie_on_the_plane_of_a_tilted_boundary():
    g = Graph()
    g.node("Rectangle", "r", width=8.0, height=5.0)
    g.node("Rotate", "tilted", geometry=g.nodes["r"], degrees=30.0, axis="x")
    boundary = g.value("tilted")
    rng = np.random.default_rng(3)
    corners = boundary.values
    u, v = rng.uniform(0.05, 0.95, (2, 15))
    seeds = Data(corners[0] + np.outer(u, corners[1] - corners[0]) + np.outer(v, corners[3] - corners[0]),
                 ("point",), kind=G.POINT)
    cells = voronoi(seeds, boundary)
    normal = np.cross(corners[1] - corners[0], corners[3] - corners[0])
    assert np.allclose((cells.values.reshape(-1, 3) - corners[0]) @ normal, 0, atol=1e-9)
    assert _area(cells) == pytest.approx(40.0)


def test_mistakes_say_what_happened():
    with pytest.raises(ShapeError):
        voronoi(_rectangle(), None)
    with pytest.raises(ShapeError):
        voronoi(_seeds(), _rectangle(), radius=-1.0)
    with pytest.raises(ShapeError):
        voronoi(_seeds(), _seeds())                         # points are not a boundary
    g = Graph()
    g.node("Circle", "c", radius=1.0)
    far = Data(np.array([[50.0, 50.0, 0.0], [52.0, 50.0, 0.0]]), ("point",), kind=G.POINT)
    with pytest.raises(ShapeError):
        voronoi(far, g.value("c"), radius=1.0)              # the seeds are far from the boundary


def test_the_pyramids_of_the_cells_turn_all_the_same_way():
    # A cell where Delaunay joins three corners without the centre: that triangle turns like the others.
    cells = voronoi(_seeds(40, 4, 12.0, 9.0), _rectangle(12.0, 9.0))
    g = Graph()
    pts = Data(cells.values, ("cell", "vertex"), kind=G.POINT)
    centres = Data(np.array([_clean(c).mean(axis=0) for c in cells.values]) - [0, 0, 0.9], ("cell",), kind=G.POINT)
    m = delaunay(pts, more=centres)
    assert np.all(mesh_faces(m, "normals").values[:, 2] > 0)      # a dent, seen from where it opens


