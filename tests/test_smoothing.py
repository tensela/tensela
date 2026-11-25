"""Smoothing meshes by subdivision: Catmull-Clark and Loop."""

from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import Data, ShapeError
from tensela.mesh_tools import join_meshes, mesh, mesh_edges, mesh_faces, mesh_surface, smooth_mesh, triangulate
from tensela.project_file import open_

EXAMPLES = Path(__file__).parent / "data"


def test_catmull_clark_rounds_a_cube_towards_a_sphere():
    cube = G.box(2, 2, 2)
    spreads = []
    for level in (1, 2, 3):
        m = smooth_mesh(cube, "Catmull-Clark", level)
        assert len(m.kind.faces) == 6 * 4 ** level and all(len(f) == 4 for f in m.kind.faces)
        r = np.linalg.norm(m.values, axis=-1)
        spreads.append(r.max() / r.min())
        assert np.allclose(mesh_faces(m, "orientation").values, 1)     # it keeps the faces looking out
    assert spreads[0] > spreads[1] > spreads[2] and spreads[2] < 1.04


def test_catmull_clark_turns_any_face_into_quadrilaterals():
    v = Data(np.array([[0, 0, 0], [2, 0, 0], [3, 1.5, 0], [1, 3, 0], [-1, 1.5, 0]], float), ("vertex",), kind=G.POINT)
    pentagon = mesh(v, "0 1 2 3 4")
    m = smooth_mesh(pentagon, "Catmull-Clark", 1)
    assert len(m.kind.faces) == 5 and all(len(f) == 4 for f in m.kind.faces)


def test_loop_splits_each_triangle_in_four():
    tri = triangulate(G.box(2, 2, 2))
    m = smooth_mesh(tri, "Loop", 2)
    assert len(m.kind.faces) == 12 * 16 and all(len(f) == 3 for f in m.kind.faces)
    with pytest.raises(ShapeError):
        smooth_mesh(G.box(2, 2, 2), "Loop", 1)                          # quadrilaterals: Loop does not take them


def test_the_border_smooth_fixed_or_with_its_corners_fixed():
    plate = triangulate(mesh_surface(G.rectangle(4, 4), 2, 2))
    corners = np.array([[0, 0, 0], [4, 0, 0], [4, 4, 0], [0, 4, 0]], float)

    def kept(m):
        return sum(np.min(np.linalg.norm(m.values - c, axis=-1)) < 1e-9 for c in corners)
    assert kept(smooth_mesh(plate, "Loop", 2, "fixed")) == 4
    assert kept(smooth_mesh(plate, "Loop", 2, "corners fixed")) == 4
    assert kept(smooth_mesh(plate, "Loop", 2, "smooth")) == 0             # the corners are rounded off
    fixed = smooth_mesh(plate, "Loop", 2, "fixed")
    edge = mesh_edges(fixed, "naked").values.reshape(-1, 3)
    assert np.allclose(np.minimum.reduce([edge[:, 0], 4 - edge[:, 0], edge[:, 1], 4 - edge[:, 1]]), 0)  # on the square


def test_a_flat_mesh_stays_flat_and_level_zero_changes_nothing():
    plate = mesh_surface(G.rectangle(4, 4), 3, 3)
    assert np.allclose(smooth_mesh(plate, levels=3).values[:, 2], 0)
    same = smooth_mesh(plate, levels=0)
    assert same.kind.faces == plate.kind.faces and np.allclose(same.values, plate.values)


def test_each_element_is_smoothed_with_the_same_steps():
    two = G.move(G.box(1, 1, 1), G.point(Data(np.array([0.0, 5.0]), ("copy",)), 0, 0))
    m = smooth_mesh(two, levels=2)
    assert m.sizes == {"copy": 2}
    assert np.allclose(m.values[1] - m.values[0], [5, 0, 0])


def test_too_many_faces_say_so():
    with pytest.raises(ShapeError):
        smooth_mesh(mesh_surface(G.rectangle(10, 10), 100, 100), levels=5)


