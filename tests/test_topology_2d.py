"""Topology optimization in 2D."""
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import topology as T
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _points(*p):
    return Data(np.array(p, float), ("p",), None, kind=geo.POINT)


def _beam(width=6.0, height=2.0, plane="elevation"):
    g = Graph()
    g.node("Rectangle", "r", width=width, height=height, plane=plane)
    return g.value("r")


def test_the_stiffness_of_a_cell_and_the_grid_solve_a_plate():
    k = T._cell_stiffness()
    assert np.allclose(k, k.T) and np.allclose(k @ np.tile([1.0, 0.0], 4), 0)        # a move of the whole: no force
    assert np.allclose(np.linalg.eigvalsh(k)[:3], 0, atol=1e-12)                     # three free moves of a body
    # A plate of 10 × 1 cells, held at its left edge, pulled at its right edge: stretches as E A / L says.
    grid = T._Grid(10, 1)
    held = np.zeros((11, 4), dtype=bool)
    held[0] = True
    force = np.zeros((11, 4))
    force[10, 0] = force[10, 2] = 0.5
    u = grid.solve(np.repeat(k[None], 10, axis=0), force, held)
    assert u[10, 0] == pytest.approx(10.0, rel=0.01)                                 # F L / (E A), E = 1


def test_the_mbb_beam_keeps_its_material_and_finds_a_truss():
    r = T.optimize_2d(_beam(), supports=_points((0, 0, 0)), rollers=_points((6, 0, 0)), loads=_points((3, 0, 2)),
                      load=10000.0, density=0.4, resolution=60)
    d = r["density"].reshape(r["nx"], r["ny"])
    assert (r["nx"], r["ny"]) == (60, 20)
    assert d[r["active"].reshape(60, 20)].mean() == pytest.approx(0.4, abs=0.01)    # the material asked for
    assert d[:, 0].mean() > 0.8 and d[25:35, -1].mean() > 0.8                       # the tie below, the top in the middle
    assert d[25:35, 8:12].mean() < 0.2                                               # and empty in between
    assert np.allclose(d, d[::-1], atol=0.05)                                        # symmetric, as the beam
    shape = T.topology_2d(_beam(), supports=_points((0, 0, 0)), rollers=_points((6, 0, 0)),
                          loads=_points((3, 0, 2)), load=10000.0)
    assert shape.kind.closed and shape.levels == ("outline",) and len(shape.values) >= 4   # the outer one and holes
    assert np.allclose(np.asarray(shape.values)[..., 1], 0)                          # in its plane (elevation)
    # «plate»: the same shape filled in, with its holes: about the material asked for (40 % of 6 × 2 m).
    plate = T.topology_2d(_beam(), supports=_points((0, 0, 0)), rollers=_points((6, 0, 0)),
                          loads=_points((3, 0, 2)), load=10000.0, show='plate')
    p, faces = np.asarray(plate.values), np.asarray(plate.kind.faces)
    area = 0.5 * np.linalg.norm(np.cross(p[faces[:, 1]] - p[faces[:, 0]], p[faces[:, 2]] - p[faces[:, 0]]), axis=1)
    assert plate.kind.name == "mesh" and np.allclose(p[:, 1], 0)
    assert area.sum() == pytest.approx(0.4 * 12, rel=0.15)


def test_its_own_weight_makes_an_arch_and_the_outputs():
    g = Graph()
    g.node("Rectangle", "b", width=12.0, height=3.0, plane="elevation")
    g.node("Rectangle", "s1", width=1.0, height=0.5, plane="elevation")
    g.node("Rectangle", "s2", width=1.0, height=0.5, origin=(11.0, 0, 0), plane="elevation")
    g.node("Merge lists", "s", a=g.nodes["s1"], b=g.nodes["s2"])
    r = T.optimize_2d(g.value("b"), supports=g.value("s"), self_weight=True, resolution=48)
    d = r["density"].reshape(r["nx"], r["ny"])
    assert d[20:28, -1].mean() > 0.8 and d[20:28, :4].mean() < 0.2                  # the crown of an arch, empty below
    common = dict(supports=g.value("s"), self_weight=True, resolution=24)
    assert T.topology_2d(g.value("b"), show='cells', **common).kind is geo.RECTANGLE
    grid = T.topology_2d(g.value("b"), show='grid', **common)
    density = T.topology_2d(g.value("b"), show='density', **common)
    stress = T.topology_2d(g.value("b"), show='stress', **common)
    assert len(grid.values) == len(density.values) == len(stress.values) == 24 * 6
    assert float(T.topology_2d(g.value("b"), show='largest displacement', **common).values) > 0


def test_voids_solid_parts_and_what_is_missing():
    g = Graph()
    g.node("Rectangle", "door", width=1.0, height=1.0, origin=(2.5, 0, 0.5), plane="elevation")
    r = T.optimize_2d(_beam(), voids=g.value("door"), supports=_points((0, 0, 0)), rollers=_points((6, 0, 0)),
                      loads=_points((3, 0, 2)), resolution=30)
    d = r["density"].reshape(r["nx"], r["ny"])
    assert d[13:17, 3:7].max() == 0                                                   # the door stays empty
    with pytest.raises(ShapeError, match="holds"):
        T.optimize_2d(_beam(), loads=_points((3, 0, 2)))
    with pytest.raises(ShapeError, match="carry"):
        T.optimize_2d(_beam(), supports=_points((0, 0, 0)))
    with pytest.raises(ShapeError, match="density"):
        T.optimize_2d(_beam(), supports=_points((0, 0, 0)), loads=_points((3, 0, 2)), density=1.5)
    # The region drawn in plan and the load up in the elevation: said, not pressed flat onto the plate.
    with pytest.raises(ShapeError, match="2 m off the plane"):
        T.optimize_2d(_beam(plane="plan"), supports=_points((0, 0, 0)), loads=_points((3, 0, 2)))
    # Held by rollers alone it slides sideways; on one point alone it turns: said, not a shape that means nothing.
    with pytest.raises(ShapeError, match="Only rollers"):
        T.optimize_2d(_beam(), rollers=_points((6, 0, 0)), loads=_points((3, 0, 2)))
    with pytest.raises(ShapeError, match="single point"):
        T.optimize_2d(_beam(), supports=_points((0, 0, 0)), loads=_points((3, 0, 2)))


def test_the_way_to_the_shape_and_its_moment():
    import time
    g = Graph()
    g.node("Rectangle", "r", width=6.0, height=2.0, plane="elevation")
    g.node("Point", "a", x=0.0)
    g.node("Point", "b", x=6.0)
    g.node("Point", "c", x=3.0, z=2.0)
    g.node("Topology optimization", "t", region=g.nodes["r"], supports=g.nodes["a"], rollers=g.nodes["b"],
           loads=g.nodes["c"], resolution=30)
    final = g.value("t")
    g.change("t", "moment", 0.0)
    begin = time.monotonic()
    start = g.value("t")
    assert time.monotonic() - begin < 0.5                                     # remembered: only a frame
    assert start.levels == () and np.ptp(np.asarray(start.values)[:, 0]) > 5.5  # the whole region, one outline
    assert final.levels == ("outline",)                                       # the shape, with its holes
    g.change("t", "show", "largest displacement")
    soft = float(g.value("t").values)
    g.change("t", "moment", 1.0)
    assert float(g.value("t").values) < soft                                  # the shape is stiffer than the start
    with pytest.raises(Exception, match="moment"):
        g.change("t", "moment", 2.0)
        g.value("t")


SCRIPT = r'''
import os, sys, time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
from tensela.ui.widgets import ActionTile
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()
w.PLAY_SECONDS = 0.6

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    w.editor.select("0 MBB"); app.processEvents()
    tiles = [t for t in w.panel_node.findChildren(ActionTile) if t.isVisible()]
    assert len(tiles) == 1 and tiles[0].isEnabled(), tiles
    seen = []
    original = w.project.graph.change
    def change(node, input_, value):
        if input_ == "moment":
            seen.append(value)
        return original(node, input_, value)
    w.project.graph.change = change
    tiles[0].clicked.emit()
    for _ in range(600):
        app.processEvents(); w.wait_computation()
        if w._playing is None:
            break
        time.sleep(0.01)
    assert w._playing is None and seen and seen[0] == 0.0 and seen[-1] == 1.0 and len(seen) > 3, seen
    print("ok", flush=True)
    os._exit(0)

def safely():
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(4)

QTimer.singleShot(500, safely)
QTimer.singleShot(120000, lambda: os._exit(3))
app.exec()
'''


