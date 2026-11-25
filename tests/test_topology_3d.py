"""Topology optimization in 3D."""
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import topology as T
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _bridge(resolution=30):
    g = Graph()

    def box(name, w, d, h, centre):
        g.node("Box", name + " b", width=w, depth=d, height=h)
        g.node("Move", name, geometry=g.nodes[name + " b"], vector=centre)
    box("body", 20.0, 2.0, 4.0, (10.0, 0.0, 2.0))
    box("deck", 20.0, 2.0, 0.4, (10.0, 0.0, 3.8))
    box("left", 1.5, 2.0, 1.0, (0.75, 0.0, 0.5))
    box("right", 1.5, 2.0, 1.0, (19.25, 0.0, 0.5))
    g.node("Merge lists", "supports", a=g.nodes["left"], b=g.nodes["right"])
    g.node("Topology optimization", "bridge", region=g.nodes["body"], solid_parts=g.nodes["deck"],
           supports=g.nodes["supports"], loads=g.nodes["deck"], load=200000.0, self_weight=True,
           resolution=resolution, density=0.3)
    return g


def test_the_stiffness_of_a_cube():
    k = T._cell_stiffness(dim=3)
    assert k.shape == (24, 24) and np.allclose(k, k.T)
    assert np.allclose(np.linalg.eigvalsh(k)[:6], 0, atol=1e-12)                     # six free moves of a body
    assert np.linalg.eigvalsh(k)[6] > 1e-3
    # A bar of 8 cubes, held at one end and pulled at the other: F L / (E A) with A = 1, L = 8 (E = 1).
    grid = T._Grid(8, 1, 1)
    held = np.zeros((9, grid.m), dtype=bool)
    held[0] = True
    force = np.zeros((9, grid.m))
    force[8, 0::3] = 0.25
    u = grid.solve(np.repeat(k[None], 8, axis=0), force, held)
    assert u[8, 0::3].mean() == pytest.approx(8.0, rel=0.05)


def test_the_bridge_grows_legs_from_its_supports():
    g = _bridge()
    r = g.value("bridge").optimization
    assert r["dim"] == 3 and r["shape"][0] == 30 and list(r["order"][:1]) == [0]       # along the 20 m
    d = r["density"].reshape(r["shape"])
    elevation = d.mean(axis=2)                                                         # x × z (order 0, 2, 1)
    nx, nz = elevation.shape
    assert elevation[:, -1].min() > 0.9                                                # the deck stays full
    assert elevation[:3, 1:nz // 2].mean() > 0.5 and elevation[-3:, 1:nz // 2].mean() > 0.5   # legs at the ends
    assert elevation[nx // 2 - 2:nx // 2 + 2, :nz // 2].mean() < 0.15                  # empty below the middle
    shape = g.value("bridge")
    assert shape.kind.faces is not None and len(shape.kind.faces) > 100                 # the surface of the body
    p = np.asarray(shape.values)
    assert p[:, 0].min() > -0.5 and p[:, 0].max() < 20.5 and p[:, 2].max() < 4.3


def test_the_other_outputs_and_what_is_missing():
    g = _bridge(resolution=16)
    for show, kind in (('cells', geo.BOX), ('grid', geo.BOX), ('density', None), ('stress', None)):
        g.change("bridge", "show", show)
        v = g.value("bridge")
        assert v.kind is kind
    g.change("bridge", "show", 'largest displacement')
    assert float(g.value("bridge").values) > 0
    g.change("bridge", "resolution", 240)
    with pytest.raises(Exception, match="cubes"):
        g.value("bridge")
    with pytest.raises(ShapeError, match="bodies"):
        T.optimize_3d(g.value("body"), solid=geo.line((0, 0, 0), (1, 0, 0)), supports=g.value("supports"),
                      self_weight=True)


