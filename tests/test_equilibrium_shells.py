"""Bending, the floor and the imperfection in the Equilibrium node."""
import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import simulation as S
from tensela.graph import Graph
from tensela.values import ShapeError


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _sphere(count_u=12, count_v=6):
    g = Graph()
    g.node("Sphere", "ball", radius=1.0, centre=(0.0, 0.0, 1.5))
    g.node("Mesh surface", "mesh", surface=g.nodes["ball"], count_u=count_u, count_v=count_v)
    return g.value("mesh")


def test_the_force_of_bending_is_its_energy_going_down():
    mesh = _sphere(8, 4)
    net = S.network(mesh, 0)
    bending = S._bending(net["elements"], False, net["particles"]).scaled(3.0)
    x = net["particles"] + np.random.default_rng(0).normal(0, 0.05, net["particles"].shape)
    force, h = bending.force(x), 1e-6
    for i, axis in ((0, 0), (5, 2), (17, 1)):
        moved = x.copy()
        moved[i, axis] += h
        less = x.copy()
        less[i, axis] -= h
        assert -(bending.energy(moved) - bending.energy(less)) / (2 * h) == pytest.approx(force[i, axis], rel=1e-5)
    assert bending.energy(net["particles"]) == pytest.approx(0)                   # it starts at rest


def test_a_shell_rests_round_and_a_net_crumples():
    mesh = _sphere()
    shell = np.asarray(S.equilibrium(mesh, supports='none', floor=0.0, bending=0.01, imperfection=0.01).values)
    assert shell[:, 2].min() == pytest.approx(0, abs=1e-3) and np.ptp(shell[:, 2]) > 1.9     # on the floor, round
    net = np.asarray(S.equilibrium(mesh, supports='none', floor=0.0, imperfection=0.01).values)
    assert net[:, 2].min() > -1e-2 and np.ptp(net[:, 2]) < 1.0                    # without bending, it crumples


def test_an_imperfection_changes_nothing_of_a_stable_shape():
    line = geo.line((0, 0, 0), (10, 0, 0))
    perfect = np.asarray(S.equilibrium(line).values)
    shaken = np.asarray(S.equilibrium(line, imperfection=0.05).values)
    assert np.allclose(perfect, shaken, atol=1e-6)
    with pytest.raises(ShapeError, match="imperfection"):
        S.equilibrium(line, imperfection=-1)


def test_a_chain_on_the_floor_and_a_bent_bar():
    chain = np.asarray(S.equilibrium(geo.line((0, 0, 3), (10, 0, 3)), 40, stiffness=1e5, rest_length=1.6,
                                     floor=0.0).values)
    assert chain[:, 2].min() > -1e-3 and (chain[:, 2] < 1e-3).sum() > 10           # a part of it lies there
    bar = np.asarray(S.equilibrium(geo.line((0, 0, 0), (10, 0, 0)), 40, self_weight=1.0, stiffness=1e5,
                                   rest_length=1.2, bending=0.1, gravity=(0, 0, 1)).values)
    assert np.allclose(bar[[0, -1]], [[0, 0, 0], [10, 0, 0]]) and bar[:, 2].max() > 2   # an arch
    rise = bar[:, 2]
    assert np.argmax(rise) in (19, 20, 21)                                          # round, the top in the middle


def test_bending_makes_a_plate_sag_less():
    g = Graph()
    g.node("Rectangle", "plan", width=4.0, height=4.0)
    g.node("Mesh surface", "mesh", surface=g.nodes["plan"], count_u=8, count_v=8)
    mesh = g.value("mesh")
    cloth = np.asarray(S.equilibrium(mesh, supports='border').values)[:, 2].min()
    plate = np.asarray(S.equilibrium(mesh, supports='border', bending=0.01).values)[:, 2].min()
    assert cloth < plate < 0
    with pytest.raises(ShapeError, match="bending"):
        S.equilibrium(mesh, bending=-0.1)


def test_with_a_floor_it_needs_no_supports():
    line = geo.line((0, 0, 1), (10, 0, 1))
    lying = np.asarray(S.equilibrium(line, supports='none', floor=0.0).values)
    assert np.allclose(lying[:, 2], 0, atol=1e-3)                                  # it falls and lies down
    with pytest.raises(ShapeError, match="Nothing holds it"):
        S.equilibrium(line, supports='none')
