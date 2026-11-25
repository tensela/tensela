"""Polygon meshes by their topology: build, read and turn faces."""

from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import Data, ShapeError
from tensela.mesh_tools import flip_faces, mesh, mesh_faces, orientation, read_faces
from tensela.project_file import open_


def _points(*coords):
    return Data(np.array(coords, float), ("vertex",), kind=G.POINT)


SQUARE = _points((0, 0, 0), (2, 0, 0), (1, 1.7, 0), (3, 1.7, 0))


def test_the_faces_can_be_written_in_several_ways():
    assert read_faces("0 1 2; 2 1 3") == [(0, 1, 2), (2, 1, 3)]
    assert read_faces("0,1,2;2,1,3") == [(0, 1, 2), (2, 1, 3)]
    assert read_faces([0, 1, 2]) == [(0, 1, 2)]                          # a single face, as the window reads «0 1 2»
    assert read_faces([[0, 1, 2, 3], [1, 4, 5, 2]]) == [(0, 1, 2, 3), (1, 4, 5, 2)]


def test_compatible_faces_look_the_same_way():
    m = mesh(SQUARE, "0 1 2; 2 1 3")
    assert m.kind.faces == ((0, 1, 2), (2, 1, 3))
    assert np.allclose(mesh_faces(m, "normals").values, [[0, 0, 1], [0, 0, 1]])
    assert np.allclose(mesh_faces(m, "orientation").values, [1, 1])


def test_a_face_in_the_other_order_is_turned_over_and_flip_fixes_it():
    bad = mesh(SQUARE, "0 1 2; 1 2 3")
    assert np.allclose(mesh_faces(bad, "normals").values[1], [0, 0, -1])
    assert np.allclose(mesh_faces(bad, "orientation").values, [1, -1])  # not orientable
    fixed = flip_faces(bad, "1")
    assert np.allclose(mesh_faces(fixed, "orientation").values, [1, 1])
    assert np.allclose(mesh_faces(flip_faces(bad), "orientation").values, [1, -1])   # all of them: still one apart


def test_quadrilaterals_and_their_outlines():
    v = _points((0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (4, 0, 0), (4, 2, 0))
    m = mesh(v, "0 1 2 3; 1 4 5 2")
    out = mesh_faces(m, "outlines")
    assert out.sizes == {"face": 2} and out.values.shape[-2] == 4
    assert np.allclose(mesh_faces(m, "centres").values, [[1, 1, 0], [3, 1, 0]])
    assert np.allclose(mesh_faces(m, "sides").values, [4, 4])


def test_a_mixed_mesh_pads_the_outlines():
    v = _points((0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (3, 1, 0))
    m = mesh(v, "0 1 2 3; 1 4 2")
    assert np.allclose(mesh_faces(m, "sides").values, [4, 3])
    assert np.allclose(mesh_faces(m, "centres").values[1], [7 / 3, 1, 0])   # without the repeated vertex


def test_a_box_is_orientable_and_its_normals_look_out():
    b = G.box(2, 2, 2)
    n = mesh_faces(b, "normals").values
    c = mesh_faces(b, "centres").values
    assert np.all(np.sum(n * c, axis=-1) > 0)
    assert np.allclose(orientation(b.kind.faces), 1)


def test_more_levels_give_one_mesh_each():
    pts = Data(np.stack([SQUARE.values, SQUARE.values + [0, 0, 5]]), ("copy", "vertex"), kind=G.POINT)
    m = mesh(pts, "0 1 2; 2 1 3")
    assert m.sizes == {"copy": 2} and m.kind.name == "mesh"


@pytest.mark.parametrize("faces", ["0 1", "0 1 1", "0 1 7", ""])
def test_wrong_faces_say_so(faces):
    with pytest.raises(ShapeError):
        mesh(SQUARE, faces)


