"""Joining and welding meshes, naked edges and T-nodes."""

from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.mesh_tools import flip_faces, join_meshes, mesh_edges, mesh_faces, mesh_surface
from tensela.project_file import open_


def _grid_panels(columns=3, rows=2):
    g = Graph()
    g.node("Rectangle", "r", width=float(columns), height=float(rows))
    g.node("Grid", "p", rectangle=g.nodes["r"], columns=columns, rows=rows)
    return g.value("p")


def test_joining_puts_every_element_in_one_mesh():
    panels = _grid_panels()                                            # 6 rectangles of 4 corners
    loose = join_meshes([panels], weld=False)
    assert loose.levels == () and len(loose.kind.faces) == 6 and loose.values.shape[0] == 24
    welded = join_meshes([panels])
    assert len(welded.kind.faces) == 6 and welded.values.shape[0] == 12   # (3 + 1) × (2 + 1) shared vertices


def test_welded_panels_have_only_their_border_naked():
    welded = join_meshes([_grid_panels()])
    assert mesh_edges(welded, "naked").sizes == {"edge": 10}             # 3 + 3 + 2 + 2
    assert mesh_edges(welded, "inner").sizes == {"edge": 7}
    assert mesh_edges(welded, "all").sizes == {"edge": 17}
    loose = join_meshes([_grid_panels()], weld=False)
    assert mesh_edges(loose, "naked").sizes == {"edge": 24}             # every panel, its own border


def test_a_tolerance_too_small_leaves_a_gap_unwelded():
    a = G.rectangle(1, 1)
    b = G.move(G.rectangle(1, 1), G.point(1.0005, 0, 0))                # half a millimetre apart
    assert mesh_edges(join_meshes([a, b], tolerance=0.001), "naked").sizes == {"edge": 6}
    assert mesh_edges(join_meshes([a, b], tolerance=0.0001), "naked").sizes == {"edge": 8}


def test_different_kinds_join_and_polygons_lose_their_padding():
    g = Graph()
    g.node("Rectangle", "r", width=6.0, height=4.0)
    g.node("Grid", "hex", rectangle=g.nodes["r"], columns=3, rows=2, shape="hexagons")
    m = join_meshes([g.value("hex"), G.box(1, 1, 1)])
    assert m.kind.name == "mesh"
    assert {len(f) for f in m.kind.faces} == {6, 4}                       # the hexagons and the faces of the box


def test_a_face_turned_over_in_a_box_is_found():
    box = join_meshes([G.box(2, 2, 2)])
    assert np.allclose(mesh_faces(box, "orientation").values, 1)
    bad = flip_faces(box, "2")
    o = mesh_faces(bad, "orientation").values
    assert sorted(o.tolist()).count(-1.0) in (1, 5)                       # one face apart from the others


def test_a_t_node_does_not_weld():
    a = mesh_surface(G.rectangle(4, 3), 4, 3)
    b = mesh_surface(G.move(G.rectangle(4, 3), G.point(4, 0, 0)), 4, 2)  # 2 faces up against 3: T-nodes
    # the shared side does not weld: 3 edges on one panel against 2 on the other, all naked (22 + 3 + 2 - 1)
    assert mesh_edges(join_meshes([a, b]), "naked").sizes == {"edge": 26}
    c = mesh_surface(G.move(G.rectangle(4, 3), G.point(4, 0, 0)), 4, 3)
    assert mesh_edges(join_meshes([a, c]), "naked").sizes == {"edge": 22}   # matching: only the outer border


def test_nothing_to_join_says_so():
    with pytest.raises(ShapeError):
        join_meshes([None, None])


