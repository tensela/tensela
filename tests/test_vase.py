"""Fabrication, package 2: a printable vase, and what it needed: a mesh that closes at a point, a mesh
with thickness, the bounding box and a Morph into eight corners."""
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela import printing as P
from tensela.graph import Graph
from tensela.mesh_tools import mesh_surface, thicken_mesh
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def in_english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _cup(g: Graph) -> str:
    """A cup as a loft: a circle shrunk to a point at the bottom, then two circles up."""
    g.node("Circle", "ring", radius=0.04)
    g.node("Series", "storey", count=3, level="storey")
    g.node("Formula", "z", formula="if(a == 0, 0, (a - 1) * 0.06)", a=g.nodes["storey"])
    g.node("Formula", "size", formula="if(a == 0, 0, 1)", a=g.nodes["storey"])
    g.node("Vector", "up", z=g.nodes["z"])
    g.node("Move", "raised", geometry=g.nodes["ring"], vector=g.nodes["up"])
    g.node("Scale", "rings", geometry=g.nodes["raised"], factor=g.nodes["size"], centre=(0.0, 0.0, 0.0))
    g.node("Loft", "skin", curves=g.nodes["rings"], along="storey", smooth=False)
    return "skin"


def test_a_surface_that_closes_at_a_point_meshes_closed_there():
    g = Graph()
    mesh = mesh_surface(g.value(_cup(g)), 16, 4)
    sizes = {len(f) for f in mesh.kind.faces}
    assert sizes == {3, 4}                                       # triangles round the pole
    r = P.check(P.pieces(mesh), printer=None)[0]
    assert r.problems and "16 edges" in r.problems[0]            # only the mouth is open


def test_a_mesh_thickened_is_closed_and_as_thick_as_asked():
    g = Graph()
    skin = mesh_surface(g.value(_cup(g)), 32, 6)
    wall = thicken_mesh(skin, 0.002)
    r = P.check(P.pieces(wall))[0]
    assert r.ready and r.thinnest == pytest.approx(0.002, rel=0.15)
    assert len(wall.kind.faces) == 2 * len(skin.kind.faces) + 32         # both sides and the rim
    g.node("Mesh surface", "m", surface=g.nodes["skin"], count_u=32, count_v=6)
    g.node("Thicken", "t", rectangle=g.nodes["m"], thickness=-0.001)     # the node Thicken takes meshes too
    assert P.check(P.pieces(g.value("t")))[0].ready


def test_bounding_box_of_all_and_of_each():
    g = Graph()
    g.node("Box", "b", width=1.0, depth=2.0, height=3.0)
    g.node("Series", "i", count=2)
    g.node("Formula", "x", formula="a * 5", a=g.nodes["i"])
    g.node("Vector", "v", x=g.nodes["x"], y=0.0, z=0.0)
    g.node("Move", "two", geometry=g.nodes["b"], vector=g.nodes["v"])
    every = np.asarray(G.bounding_box(g.value("two")).values)
    assert np.allclose(every.min(axis=0), (-0.5, -1, -1.5)) and np.allclose(every.max(axis=0), (5.5, 1, 1.5))
    each = G.bounding_box(g.value("two"), 'each')
    assert each.levels == ("element",) and np.allclose(np.ptp(np.asarray(each.values)[1], axis=0), (1, 2, 3))


def test_morph_into_eight_corners_moved_one_by_one():
    g = Graph()
    g.node("Box", "b", width=1.0, depth=1.0, height=1.0)
    g.node("Vertices", "corners", geometry=g.nodes["b"], level="corner")
    g.node("Series", "k", count=8, level="corner")
    g.node("Formula", "drop", formula="if(a == 4 or a == 7, -0.5, 0)", a=g.nodes["k"])
    g.node("Vector", "v", z=g.nodes["drop"])
    g.node("Move", "moved", geometry=g.nodes["corners"], vector=g.nodes["v"])
    g.node("Box", "small", width=0.2, depth=0.2, height=0.2)
    g.node("Morph", "fitted", geometry=g.nodes["small"], into=g.nodes["moved"])
    fitted = np.asarray(g.value("fitted").values)              # its corners go to the moved corners
    assert np.allclose(fitted, np.asarray(g.value("moved").values))


