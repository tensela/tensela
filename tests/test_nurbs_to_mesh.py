"""From a NURBS surface to a mesh: one mesh of quadrilaterals, triangles, and flat faces."""

from pathlib import Path

import numpy as np

from tensela import geometry as G
from tensela.data import Data
from tensela.graph import Graph
from tensela.mesh_tools import mesh, mesh_faces, mesh_surface, triangulate
from tensela.project_file import open_


def test_a_rectangle_as_one_mesh_shares_its_vertices():
    m = mesh_surface(G.rectangle(4, 2), 4, 2)
    assert m.kind.name == "mesh" and len(m.kind.faces) == 8
    assert m.values.shape[-2] == 5 * 3                                   # (4 + 1) × (2 + 1) vertices, not 8 × 4
    assert np.allclose(mesh_faces(m, "normals").values, [0, 0, 1])       # it looks like the rectangle
    assert np.allclose(mesh_faces(m, "orientation").values, 1)


def test_a_surface_that_goes_round_closes_its_seam():
    g = Graph()
    g.node("Arc", "profile", mode="centre and angles", centre=(0, 0, 0), radius=5.0, from_=0.0, to=80.0,
           plane="elevation")
    g.node("Revolve", "dome", profile=g.nodes["profile"])
    m = mesh_surface(g.value("dome"), 12, 12)
    faces = len(m.kind.faces)
    assert faces == 144 and m.values.shape[-2] < 13 * 13                 # the seam is not doubled
    assert np.allclose(mesh_faces(m, "orientation").values, 1)
    assert np.allclose(mesh_faces(m, "flatness").values, 0)              # a surface of revolution: flat quads


def test_triangulating_takes_the_shorter_diagonal():
    v = Data(np.array([[0, 0, 0], [4, 0, 0], [5, 1, 0], [0, 1, 0]], float), ("vertex",), kind=G.POINT)
    m = mesh(v, "0 1 2 3")
    t = triangulate(m)
    assert len(t.kind.faces) == 2
    assert {1, 3} <= set(t.kind.faces[0]) | set(t.kind.faces[1]) and (0, 2) not in [f[::2] for f in t.kind.faces]
    assert set(triangulate(m, "first").kind.faces[0]) == {0, 1, 2}


def test_flatness_of_a_twisted_quadrilateral():
    v = Data(np.array([[0, 0, 0.1], [2, 0, -0.1], [2, 2, 0.1], [0, 2, -0.1]], float), ("vertex",), kind=G.POINT)
    m = mesh(v, "0 1 2 3")
    assert np.isclose(mesh_faces(m, "flatness").values[0], 0.1)          # each corner 0.1 m off the best plane
    assert np.allclose(mesh_faces(triangulate(m), "flatness").values, 0)  # triangles: always flat


