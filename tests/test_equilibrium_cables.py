"""Equilibrium of cables: particles and springs hanging from their supports."""
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


def _point(*p):
    return Data(np.array(p, dtype=float), (), None, kind=geo.POINT)


def _lengths(points):
    return np.linalg.norm(np.diff(np.asarray(points), axis=0), axis=1)


def test_hookes_law():
    # 80 cm hanging from its top, k = 2 N/cm (a stiffness of 160 N for the whole cable), 100 N at its end: 50 cm more.
    cable = geo.line((0, 0, 1.0), (0, 0, 0.2))
    hung = np.asarray(S.equilibrium(cable, 1, 'start', None, 0.0, _point(0, 0, 0.2), 100.0, 160.0).values)
    assert np.allclose(hung, [[0, 0, 1.0], [0, 0, -0.3]], atol=1e-9)
    force = S.equilibrium(cable, 1, 'start', None, 0.0, _point(0, 0, 0.2), 100.0, 160.0, show='forces')
    assert float(np.asarray(force.values).ravel()[0]) == pytest.approx(100)          # in tension: positive


def test_the_spans_next_to_the_supports_stretch_more():
    line = geo.line((0, 0, 0), (10, 0, 0))
    stretch = np.asarray(S.equilibrium(line, show='elongation').values)
    assert stretch.shape == (10,) and np.allclose(stretch, stretch[::-1])           # symmetric
    assert (np.diff(stretch[:5]) < 0).all()                                         # more at the ends (fig. 9.11)
    shape = np.asarray(S.equilibrium(line).values)
    assert _lengths(shape).sum() == pytest.approx(10 * (1 + stretch.mean() / 100), rel=1e-9)
    assert np.allclose(shape[[0, -1]], [[0, 0, 0], [10, 0, 0]]) and shape[:, 2].min() < -0.1
    stiffer = np.asarray(S.equilibrium(line, stiffness=1e5).values)
    assert stiffer[:, 2].min() > shape[:, 2].min()                                   # stiffer, it sags less


def test_more_supports_and_moving_one():
    line = geo.line((0, 0, 0), (10, 0, 0))
    three = np.asarray(S.equilibrium(line, 10, 'ends', _point(7.1, 0, 0.3)).values)
    assert np.allclose(three[7], [7.1, 0, 0.3])                    # the nearest particle, pinned where the point is
    assert three[3, 2] < three[8, 2] < 0                            # the longer part sags more
    supports = Data(np.array([[0, 0, 0], [11, 0, 4]], dtype=float), ("support",), None, kind=geo.POINT)
    moved = np.asarray(S.equilibrium(line, 10, 'none', supports).values)
    assert np.allclose(moved[-1], [11, 0, 4])                       # the end went with the point (fig. 9.8)


def test_an_arc_hangs_as_the_catenary():
    # Fig. 9.18 and 9.19: an arc of the right length, in 50 spans, very stiff: the catenary of that length.
    arc = geo.arc('three points', (0, 0, 0), (5, 0, -6.43), (10, 0, 0))
    hung = np.asarray(S.equilibrium(arc, 50, self_weight=10.0, stiffness=1e6).values)
    length = _lengths(hung).sum()
    exact = np.asarray(geo.catenary((0, 0, 0), (10, 0, 0), length).values)
    assert hung[:, 2].min() == pytest.approx(exact[:, 2].min(), rel=1e-3)
    arch = geo.arc('three points', (0, 0, 0), (5, 0, 6.43), (10, 0, 0))     # the same, drawn upwards
    upside_down = np.asarray(S.equilibrium(arch, 50, self_weight=10.0, stiffness=1e6, gravity=(0, 0, 1)).values)
    assert upside_down[:, 2].max() == pytest.approx(-exact[:, 2].min(), rel=1e-3)   # the arch


def test_lines_as_they_come_and_many_cables():
    shattered = Data(np.stack([np.linspace([0, 0, 0], [9, 0, 0], 10), np.linspace([1, 0, 0], [10, 0, 0], 10)], axis=1),
                     ("line",), None, kind=geo.CURVE)
    as_lines = S.equilibrium(shattered, 0, 'none', Data(np.array([[0, 0, 0], [10, 0, 0.0]]), ("p",), None,
                                                          kind=geo.POINT), show='spans')
    divided = np.asarray(S.equilibrium(geo.line((0, 0, 0), (10, 0, 0)), show='spans').values)
    assert np.allclose(np.asarray(as_lines.values).reshape(-1, 2, 3), divided, atol=1e-7)   # welded where they touch
    g = Graph()
    g.node("Series", "k", count=4, level="cable")
    g.node("Point", "a", x=0.0, y=g.nodes["k"], z=0.0)
    g.node("Point", "b", x=10.0, y=g.nodes["k"], z=g.nodes["k"])
    g.node("Line", "cables", **{"from": g.nodes["a"]}, to=g.nodes["b"])
    g.node("Equilibrium", "hung", shape=g.nodes["cables"])
    assert np.asarray(g.value("hung").values).shape == (4, 11, 3)


def test_big_networks_with_conjugate_gradients(monkeypatch):
    line = geo.line((0, 0, 0), (10, 0, 0))
    direct = np.asarray(S.equilibrium(line, 40, self_weight=10.0, stiffness=1e4).values)
    S._CACHE.clear()
    monkeypatch.setattr(S, "MAXIMUM_NEWTON", 30)
    iterative = np.asarray(S.equilibrium(line, 40, self_weight=10.0, stiffness=1e4).values)
    assert np.allclose(direct, iterative, atol=1e-6)


def test_what_cannot_be_done_is_said():
    line = geo.line((0, 0, 0), (10, 0, 0))
    with pytest.raises(ShapeError, match="Nothing holds it"):
        S.equilibrium(line, supports='none')
    two = Data(np.array([[[0, 0, 0], [10, 0, 0]], [[0, 5, 0], [10, 5, 0]]], dtype=float), ("cable",), None,
               kind=geo.CURVE)
    with pytest.raises(ShapeError, match="hangs from nothing"):
        S.equilibrium(two, supports='none', more_supports=_point(0, 0, 0))
    with pytest.raises(ShapeError, match="stiffness"):
        S.equilibrium(line, stiffness=0)
    with pytest.raises(ShapeError, match="curves, lines or a mesh"):
        S.equilibrium(_point(0, 0, 0))


def test_a_cable_as_long_as_its_supports_rests_without_any_force():
    # Without weight and exactly as long as the distance between its supports: straight, and no force at all (the
    # tolerance cannot be measured against a force that is 0).
    line = geo.line((46, 0, 8), (56, 0, 8))
    shape = np.asarray(S.equilibrium(line, supports='start', more_supports=_point(57.0, 0.0, 8.0), self_weight=0.0,
                                     stiffness=1e5, rest_length=1.1).values)
    assert np.allclose(shape[:, 2], 8) and np.allclose(shape[-1], [57, 0, 8])
    forces = np.asarray(S.equilibrium(line, supports='start', more_supports=_point(57.0, 0.0, 8.0), self_weight=0.0,
                                      stiffness=1e5, rest_length=1.1, show='forces').values)
    assert np.abs(forces).max() < 1e-3
