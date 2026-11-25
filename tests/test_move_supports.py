"""Moving the supports of an Equilibrium in the 3D view."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tensela import language
from tensela.graph import Graph


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def test_supports_by_hand_follow_their_particle():
    g = Graph()
    g.node("Line", "cable", **{"from": (0.0, 0.0, 0.0)}, to=(10.0, 0.0, 0.0))
    g.node("Equilibrium", "hung", shape=g.nodes["cable"])
    g.change("hung", "hand_supports", [[5.0, 0, 0, 5.0, 0, 2.0], [9.9, 0, 0.1, 9.0, 1.0, 0.0]])
    v = g.value("hung")
    shape = np.asarray(v.values)
    assert np.allclose(shape[5], [5, 0, 2]) and np.allclose(shape[10], [9, 1, 0])  # each to the nearest particle
    assert set(v.network["by_hand"]) == {5, 10} and v.network["fixed"].sum() == 3   # (the end, moved by hand)
    assert v.network["rest"].shape == (11, 3) and v.network["springs"].shape == (10, 2)
    g.change("hung", "spans", 20)                       # finer: the supports find their particles again
    assert np.allclose(np.asarray(g.value("hung").values)[10], [5, 0, 2])


SCRIPT = r'''
import os, sys
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    g = w.project.graph
    w.editor.select("0 spans"); app.processEvents()
    w.draw("0 spans"); app.processEvents(); w.wait_computation(); app.processEvents()
    d = w.viewer.drawing
    assert d.active and len(d.points) == 11 and d.marked.sum() == 2, (len(d.points), d.marked)
    low_before = float(d.points[:, 2].min())
    d.move(5, [5.0, 0.0, 10.0]); w.wait_computation(); app.processEvents()
    rows = g.nodes["0 spans"].inputs["hand_supports"]
    assert len(rows) == 1 and np.allclose(rows[0][3:], [5, 0, 10]), rows
    assert d.marked.sum() == 3 and np.allclose(d.points[5], [5, 0, 10])
    assert d.points[3, 2] > low_before + 0.5, d.points[:, 2]      # the others followed: the cable went up
    w._mark_support("0 spans", 5, False); w.wait_computation(); app.processEvents()
    assert not g.nodes["0 spans"].inputs["hand_supports"] and d.marked.sum() == 2
    w._mark_support("0 spans", 3, True); w.wait_computation(); app.processEvents()
    assert len(g.nodes["0 spans"].inputs["hand_supports"]) == 1 and d.marked[3]
    w.undo(); w.wait_computation(); app.processEvents()
    assert not w.project.graph.nodes["0 spans"].inputs["hand_supports"]
    w.finish_drawing(); app.processEvents()
    assert not w.viewer.drawing.active
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
QTimer.singleShot(90000, lambda: os._exit(3))
app.exec()
'''


