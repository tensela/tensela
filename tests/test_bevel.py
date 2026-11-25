"""Bevel: boards with their edges eased (notes on test 80)."""
import numpy as np
import pytest

from tensela import bevel as B
from tensela import fabrication as F
from tensela import language
from tensela import measures
from tensela import printing as P
from tensela.graph import Graph
from tensela.values import ShapeError


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _plate(g, width=0.1, height=0.05):
    g.node("Rectangle", "plate", width=width, height=height)
    return g.value("plate")


def test_a_chamfer_takes_off_exactly_its_wedges():
    g = Graph()
    plate = _plate(g)
    W, H, t, b = 0.1, 0.05, 0.006, 0.002
    board = B.bevel(plate, t, b, 'chamfer')
    # Each half: the area of the plate inset by w, from w = b at the face to 0, over a height b.
    wedge = W * H * b - (W + H) * b ** 2 + 4 * b ** 3 / 3
    assert float(measures.volume(board).values) == pytest.approx(W * H * (t - 2 * b) + 2 * wedge, rel=1e-9)
    assert P.check(P.pieces(board), printer=None, thickness=0)[0].ready


def test_one_face_only():
    g = Graph()
    plate = _plate(g)
    board = np.asarray(B.bevel(plate, 0.006, 0.002, 'rounded', faces='top face').values)
    top, bottom = board[np.isclose(board[:, 2], 0.003)], board[np.isclose(board[:, 2], -0.003)]
    assert np.allclose(bottom[:, :2].min(axis=0), [0, 0]) and np.allclose(bottom[:, :2].max(axis=0), [0.1, 0.05])
    assert np.allclose(top[:, :2].min(axis=0), [0.002, 0.002])          # the top face, inset by the bevel


def test_every_profile_on_slotted_boards_is_a_closed_board_that_lays_flat_the_same():
    g = Graph()
    g.node("Sphere", "ball", radius=0.1)
    g.node("Sections", "across", shape=g.nodes["ball"], gap=0.02)
    g.node("Sections", "along", shape=g.nodes["ball"], gap=0.02, cuts="y")
    g.node("Slots", "first", first=g.nodes["across"], second=g.nodes["along"])
    g.node("Drawn curve", "ogee", points=[(0, 1, 0), (0.5, 0.8, 0), (0.5, 0.2, 0), (1, 0, 0)])
    for profile in B.PROFILES:
        g.node("Bevel", f"b {profile}", pieces=g.nodes["first"], profile=profile, curve=g.nodes["ogee"])
        board = g.value(f"b {profile}")
        assert all(r.ready for r in P.check(P.pieces(board), printer=None, thickness=0)), profile
    laid = F.lay_flat(g.value("b rounded"), 0.6, 0.4)                   # its outlines are the slotted pieces'
    assert laid.layout.count == F.lay_flat(g.value("first"), 0.6, 0.4).layout.count


def test_the_profiles():
    chamfer = B.profile_points('chamfer')
    assert np.allclose(chamfer, [[1, 0], [0, 1]])
    octagon = B.profile_points('rounded', 2)
    assert len(octagon) == 3 and np.allclose(octagon[[0, -1]], [[1, 0], [0, 1]])
    assert (octagon[1] < 0.5).all()                                     # round bulges out (towards the corner)
    assert (B.profile_points('cove', 2)[1] > 0.5).all()                 # the cove hollows in
    g = Graph()
    g.node("Drawn curve", "drawn", points=[(0, 2, 0), (1, 1.5, 0), (2, 0, 0)])
    g.node("Drawn curve", "backwards", points=[(2, 0, 0), (1, 1.5, 0), (0, 2, 0)])
    one, other = B.profile_points('custom', curve=g.value("drawn")), B.profile_points('custom', curve=g.value("backwards"))
    assert np.allclose(one, other) and np.allclose(one[[0, -1]], [[1, 0], [0, 1]])
    assert (np.diff(one[:, 0]) <= 0).all() and (np.diff(one[:, 1]) >= 0).all()     # always in and down


def test_what_cannot_be_done_is_said():
    g = Graph()
    plate = _plate(g)
    with pytest.raises(ShapeError, match="does not fit"):
        B.bevel(plate, 0.006, 0.003)                                   # half the thickness, on both faces
    assert B.bevel(plate, 0.006, 0.004, faces='bottom face') is not None   # on one face, up to the thickness
    with pytest.raises(ShapeError, match="curve"):
        B.bevel(plate, 0.006, 0.002, 'custom')
    with pytest.raises(ShapeError, match="narrow"):
        B.bevel(_plate(Graph(), 0.1, 0.002), 0.006, 0.0015, 'chamfer', faces='top face')
