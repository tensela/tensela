"""Fabrication, package 1: what a 3D printer needs from a piece, and the STL and 3MF files."""
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela import printing as P
from tensela.connectors.print3d import export_3mf, export_stl
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


@pytest.fixture(autouse=True)
def in_english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _report(data, **k):
    reports = P.check(P.pieces(data), **k)
    assert len(reports) == 1
    return reports[0]


def test_a_closed_box_is_ready_and_its_wall_is_measured():
    r = _report(G.box(0.1, 0.1, 0.1))
    assert r.ready and r.thinnest == pytest.approx(0.1, rel=1e-4)


def test_what_keeps_a_piece_from_printing():
    assert "not closed" in _report(G.rectangle(0.1, 0.1)).problems[0]
    assert "does not fit" in _report(G.box(0.3, 0.1, 0.1)).problems[0]
    assert "laid down another way" in _report(G.box(0.1, 0.25, 0.1), printer=(0.3, 0.2, 0.2)).problems[0]
    assert "thinner" in _report(G.box(0.1, 0.1, 0.0005)).problems[0]
    g = Graph()
    g.node("Box", "a", width=0.1, depth=0.1, height=0.1)
    g.node("Flip faces", "inside out", mesh=g.nodes["a"])
    assert "inside out" in _report(g.value("inside out")).problems[0]
    g.node("Move", "b", geometry=g.nodes["a"], vector=(0.05, 0.05, 0.05))
    g.node("Join meshes", "two", a=g.nodes["a"], b=g.nodes["b"])
    r = _report(g.value("two"))
    assert any("crosses itself" in p for p in r.problems) and r.marks
    g.node("Boolean", "one", a=g.nodes["a"], b=g.nodes["b"], operation="union")
    assert _report(g.value("one")).ready


def test_two_boxes_touching_at_an_edge_are_not_manifold():
    a = np.asarray(G.box(1, 1, 1).values, float)
    b = a + np.array([1.0, 1.0, 0.0])                   # they share the vertical edge x = y = 0.5
    from tensela.measures import _triangles
    t = np.concatenate([_triangles(G.BOX, a), _triangles(G.BOX, b)])
    v, tri = P.weld(t)
    r = P.check([P.Piece(v, tri)], printer=None)[0]
    assert any("more than two faces" in p for p in r.problems)


def test_the_node_shows_problems_ready_or_the_printer():
    g = Graph()
    g.node("Box", "bar", width=0.25, depth=0.03, height=0.03)
    node = g.node("Print check", "check", geometry=g.nodes["bar"])
    assert not g.value("check").report[0].ready
    g.change(node, "show", "ready")
    assert not bool(g.value("check").values)
    g.change(node, "show", "printer")
    room = np.asarray(g.value("check").values).reshape(-1, 3)
    assert np.allclose(np.ptp(room, axis=0), (0.2, 0.2, 0.2)) and room[:, 2].min() == pytest.approx(-0.015)
    g.node("Rectangle", "flat", width=1, height=1)
    g.change(node, "geometry", g.nodes["flat"])
    g.change(node, "show", "problems")
    assert g.value("check").sizes["problem"] == 4                  # its four open edges


def test_curves_cannot_be_printed():
    with pytest.raises(ShapeError):
        P.pieces(G.circle(1.0))


def test_stl_is_binary_in_millimetres(tmp_path):
    path = export_stl(tmp_path / "box.stl", G.box(0.1, 0.1, 0.1))
    raw = path.read_bytes()
    count = struct.unpack("<I", raw[80:84])[0]
    assert count == 12 and len(raw) == 84 + 50 * count
    corners = np.frombuffer(raw[84:], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))["v"]
    assert np.allclose(np.abs(corners), 50.0)


def test_3mf_keeps_the_unit_names_and_colours(tmp_path):
    g = Graph()
    g.node("Box", "block", width=0.1, depth=0.1, height=0.1)
    g.node("Sphere", "ball", radius=0.05)
    path = export_3mf(tmp_path / "two.3mf", g.value("block"), g.value("ball"), colours={"ball": "#d9534f"})
    with zipfile.ZipFile(path) as z:
        assert {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} <= set(z.namelist())
        model = ET.fromstring(z.read("3D/3dmodel.model"))
    assert model.get("unit") == "millimeter"
    objects = model.findall("m:resources/m:object", NS)
    assert [o.get("name") for o in objects] == ["block", "ball"]
    assert model.findall("m:resources/m:basematerials/m:base", NS)[1].get("displaycolor") == "#D9534F"
    box = objects[0].find("m:mesh", NS)
    assert len(box.find("m:vertices", NS)) == 8 and len(box.find("m:triangles", NS)) == 12
    assert len(model.findall("m:build/m:item", NS)) == 2


