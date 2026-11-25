"""Joined boxes without the faces they share."""

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.mesh_tools import join_meshes, mesh_edges, mesh_faces
from tensela.project_file import open_


def _boxes(columns=3, rows=2, floors=2, size=2.0):
    g = Graph()
    g.node("Series", "xs", count=columns, step=size, level="column")
    g.node("Series", "ys", count=rows, step=size, level="row")
    g.node("Series", "zs", count=floors, step=size, level="floor")
    g.node("Point", "o", x=g.nodes["xs"], y=g.nodes["ys"], z=g.nodes["zs"])
    g.node("Prism", "b", width=size, depth=size, height=size, origin=g.nodes["o"])
    return g.value("b")


def _edge_uses(mesh):
    uses = Counter()
    for f in mesh.kind.faces:
        for a, b in zip(f, f[1:] + f[:1]):
            uses[(min(a, b), max(a, b))] += 1
    return Counter(uses.values())


def test_two_boxes_lose_the_wall_they_share():
    boxes = _boxes(2, 1, 1)
    assert len(join_meshes([boxes]).kind.faces) == 12
    skin = join_meshes([boxes], doubled="remove")
    assert len(skin.kind.faces) == 10
    with pytest.raises(ShapeError):                          # closed: no naked edge
        mesh_edges(skin, "naked")


def test_a_block_of_boxes_becomes_its_outer_skin_closed_and_outwards():
    skin = join_meshes([_boxes()], doubled="remove")
    assert len(skin.kind.faces) == 2 * (3 * 2) + 2 * (3 * 2) + 2 * (2 * 2)
    assert set(_edge_uses(skin)) == {2}                       # every edge between two faces: closed, one volume
    centres = np.asarray(mesh_faces(skin, "centres").values)
    normals = np.asarray(mesh_faces(skin, "normals").values)
    assert np.all(np.einsum("ij,ij->i", normals, centres - centres.mean(axis=0)) > 0)


def test_faces_that_only_partly_overlap_stay():
    g = Graph()
    g.node("Prism", "big", width=4.0, depth=4.0, height=2.0)
    g.node("Prism", "small", width=2.0, depth=2.0, height=2.0, origin=(4.0, 0.0, 0.0))
    skin = join_meshes([g.value("big"), g.value("small")], doubled="remove")
    assert len(skin.kind.faces) == 12                         # the walls are not the same face: nothing goes


def test_without_welding_the_doubled_faces_also_go():
    skin = join_meshes([_boxes(2, 1, 1)], weld=False, doubled="remove")
    assert len(skin.kind.faces) == 10


def test_mistakes_say_what_happened():
    boxes = _boxes(2, 1, 1)
    with pytest.raises(ShapeError):
        join_meshes([boxes], doubled="sometimes")
    with pytest.raises(ShapeError):
        join_meshes([boxes, boxes], doubled="remove")          # every face is doubled


