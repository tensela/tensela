"""Equilibrium of membranes: meshes hanging from their corners, their border or some points."""
import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import simulation as S
from tensela.data import Data
from tensela.graph import Graph
from tensela.values import ShapeError


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _mesh(count=10, size=10.0):
    g = Graph()
    g.node("Rectangle", "plan", width=size, height=size)
    g.node("Mesh surface", "mesh", surface=g.nodes["plan"], count_u=count, count_v=count)
    return g.value("mesh")


def test_corners_border_and_diagonals():
    mesh = _mesh()
    net = S.network(mesh, 0)
    assert len(net["particles"]) == 121 and len(net["springs"]) == 220
    corners = net["elements"][0]["corners"]
    assert len(corners) == 4 and len(net["elements"][0]["border"]) == 40
    assert len(S.network(mesh, 0, 'one per square')["springs"]) == 320
    assert len(S.network(mesh, 0, 'both')["springs"]) == 420

    hung = np.asarray(S.equilibrium(mesh).values)
    assert hung.shape == (121, 3)
    assert np.allclose(hung[corners, 2], 0) and hung[:, 2].min() < -1          # held by its corners (fig. 9.24)
    middle = int(np.argmin(np.linalg.norm(np.asarray(mesh.values) - [5, 5, 0], axis=1)))
    assert hung[middle, 2] < 0 and np.allclose(hung[middle, :2], [5, 5], atol=1e-6)   # symmetric
    border = np.asarray(S.equilibrium(mesh, supports='border').values)
    assert border[:, 2].min() > hung[:, 2].min()                                  # all round: it sags less (9.27)
    sheet = np.asarray(S.equilibrium(mesh, diagonals='both').values)
    assert sheet[:, 2].min() > hung[:, 2].min()                                   # a sheet, not a cable net (9.29)
    soft = np.asarray(S.equilibrium(mesh, weft=0.2).values)
    assert soft[:, 2].min() < hung[:, 2].min()                                    # a weft that gives more


def test_a_soap_film():
    mesh = _mesh()
    film = np.asarray(S.equilibrium(mesh, self_weight=0.0, rest_length=0.0).values)
    assert np.allclose(film[:, 2], 0)                                             # flat, without weight
    side = int(np.argmin(np.linalg.norm(np.asarray(mesh.values) - [5, 0, 0], axis=1)))
    assert film[side, 1] > 1                                                      # its edges pulled in (fig. 9.28)


def test_a_tent_on_a_mast():
    mesh = _mesh()
    mast = Data(np.array([5.0, 5.0, 3.0]), (), None, kind=geo.POINT)
    tent = np.asarray(S.equilibrium(mesh, supports='border', more_supports=mast, self_weight=0.0,
                                    rest_length=0.5).values)
    assert tent[:, 2].max() == pytest.approx(3) and tent[:, 2].min() == pytest.approx(0)


def test_what_it_shows_of_a_mesh():
    mesh = _mesh(4)
    spans = S.equilibrium(mesh, diagonals='one per square', show='spans')
    assert np.asarray(spans.values).shape == (40 + 16, 2, 3)
    stretch = np.asarray(S.equilibrium(mesh, diagonals='one per square', show='elongation').values)
    forces = np.asarray(S.equilibrium(mesh, diagonals='one per square', show='forces').values)
    assert stretch.shape == forces.shape == (56,) and (np.sign(stretch) == np.sign(forces)).all()
    soft = np.asarray(S.equilibrium(mesh, weft=0.5, show='forces').values)
    assert np.isfinite(soft).all()


def test_several_meshes_each_held_by_its_border():
    # Two panels side by side (a ribbon between two arches): welded where they touch.
    g = Graph()
    g.node("Series", "k", count=2, level="panel")
    g.node("Formula", "x", formula="a * 4", a=g.nodes["k"])
    g.node("Rectangle", "plan", width=4.0, height=4.0)
    g.node("Vector", "step", x=g.nodes["x"], y=0.0, z=0.0)
    g.node("Move", "plans", geometry=g.nodes["plan"], vector=g.nodes["step"])
    g.node("Mesh surface", "panels", surface=g.nodes["plans"], count_u=6, count_v=6)
    g.node("Equilibrium", "hung", shape=g.nodes["panels"], supports="border")
    hung = np.asarray(g.value("hung").values)
    assert hung.shape == (2, 49, 3)
    assert hung[0, :, 2].min() == pytest.approx(hung[1, :, 2].min(), rel=1e-6)   # each panel sags between borders
    assert len(S.network(g.value("panels"), 0)["particles"]) == 2 * 49 - 7         # the shared edge, once


def test_what_cannot_be_done_with_a_mesh():
    mesh = _mesh(4)
    with pytest.raises(ShapeError, match="no start"):
        S.equilibrium(mesh, supports='start')
    g = Graph()
    g.node("Box", "box")
    with pytest.raises(ShapeError, match="no border"):
        S.equilibrium(g.value("box"), supports='border')
    with pytest.raises(ShapeError, match="weft"):
        S.equilibrium(mesh, weft=0)
