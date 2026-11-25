"""The Delaunay triangulation and the pattern of pyramids; the triangles of the Grid."""

from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.mesh_tools import _delaunay_2d, delaunay, join_meshes, mesh_edges, mesh_faces
from tensela.project_file import open_


def test_no_point_falls_inside_the_circle_of_a_triangle():
    rng = np.random.default_rng(4)
    xy = rng.uniform(0, 10, (40, 2))
    tris = _delaunay_2d(xy)
    for a, b, c in tris:
        p, q, r = xy[a], xy[b], xy[c]
        d = 2 * (p[0] * (q[1] - r[1]) + q[0] * (r[1] - p[1]) + r[0] * (p[1] - q[1]))
        ux = ((p @ p) * (q[1] - r[1]) + (q @ q) * (r[1] - p[1]) + (r @ r) * (p[1] - q[1])) / d
        uy = ((p @ p) * (r[0] - q[0]) + (q @ q) * (p[0] - r[0]) + (r @ r) * (q[0] - p[0])) / d
        centre, radius = np.array([ux, uy]), np.linalg.norm(p - [ux, uy])
        others = np.delete(xy, [a, b, c], axis=0)
        assert np.all(np.linalg.norm(others - centre, axis=1) >= radius - 1e-9)


def test_a_triangle_and_its_centre_give_three_faces():
    xy = np.array([[0, 0], [1, 2], [0, 2], [1 / 3, 4 / 3]], float)      # the case that lost a face before
    assert len(_delaunay_2d(xy)) == 3


def test_a_cloud_in_plan_looks_up():
    rng = np.random.default_rng(1)
    pts = Data(np.column_stack([rng.uniform(0, 5, 20), rng.uniform(0, 5, 20), np.zeros(20)]), ("point",), kind=G.POINT)
    m = delaunay(pts, plane="plan")
    assert np.allclose(mesh_faces(m, "normals").values[:, 2], 1)


def test_the_triangles_of_the_grid_cover_the_rectangle():
    g = Graph()
    g.node("Rectangle", "r", width=6.0, height=4.0)
    g.node("Grid", "t", rectangle=g.nodes["r"], columns=3, rows=2, shape="triangles")
    t = g.value("t")
    assert t.kind.name == "polygon" and t.sizes == {"row": 2, "column": 7} and t.values.shape[-2] == 3
    area = sum(0.5 * np.cross(x[1] - x[0], x[2] - x[0])[2] for x in t.values.reshape(-1, 3, 3))
    assert np.isclose(area, 24)                                         # whole, and every triangle looks up
    welded = join_meshes([t])
    assert mesh_edges(welded, "naked").sizes == {"edge": 10}            # no gap, no overlap


def test_a_pyramid_on_each_triangle_looks_out():
    g = Graph()
    g.node("Rectangle", "r", width=8.0, height=4.0)
    g.node("Grid", "t", rectangle=g.nodes["r"], columns=4, rows=2, shape="triangles")
    g.node("Vertices", "corners", geometry=g.nodes["t"])
    g.node("Centre", "centres", geometry=g.nodes["t"])
    g.node("Move", "apex", geometry=g.nodes["centres"], vector=(0.0, 0.0, 0.5))
    m = delaunay(g.value("corners"), g.value("apex"))
    assert len(m.kind.faces) == 18 * 3
    assert np.all(mesh_faces(m, "normals").values[:, 2] > 0)


def test_wrong_inputs_say_so():
    with pytest.raises(ShapeError):
        delaunay(Data(np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], float), ("point",), kind=G.POINT))   # in a line
    with pytest.raises(ShapeError):
        delaunay(G.point(1, 2, 3))


