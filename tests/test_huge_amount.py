"""Group 3.4 of the pending plan: the view asks before drawing a huge amount of pieces (a digit too many in a count:
12 bars × 8760 hours gave 105 000 boxes in the test 111)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tensela.data import Data
from tensela.geometry import BOX, POINT, box


def test_how_much_a_geometry_weighs():
    pytest.importorskip("pyvista")
    from tensela.ui.viewer import MANY_PIECES, amount, heaviness
    one = np.asarray(box(1, 1, 1).values)
    boxes = Data(np.zeros((1000, 8, 3)) + one, ("box",), "b", kind=BOX)
    assert amount(boxes) == (1000, 8000)
    assert amount(box(1, 1, 1)) == (1, 8)
    points = Data(np.zeros((300, 200, 3)), ("row", "point"), "p", kind=POINT)
    assert amount(points) == (60_000, 60_000)
    assert heaviness(points) == pytest.approx(60_000 / MANY_PIECES)
    assert heaviness(boxes) < 1


PROJECT = {"nodes": {"count": {"type": "Series", "count": 60000, "start": 1},
                     "boxes": {"type": "Box", "width": {"node": "count"}, "depth": 0.5, "height": 0.5}},
           "export": ["boxes"]}

SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()

def drawn():
    return "boxes" in w.viewer.view.actors

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    # 60 000 boxes: not drawn, the strip says why, the eye stays on
    assert w.held_strip.isVisible() and "60 000 pieces" in w._held_text.text(), w._held_text.text()
    assert not drawn() and "boxes" in w.project.export
    w._draw_held(); w.wait_computation(); app.processEvents()
    assert drawn() and not w.held_strip.isVisible()
    assert w.project.view["boxes"]["many"] == 1.2                     # remembered with the project
    # a few more: still drawn; many more (more than double): asked again
    w._change_text("count", "count", "70000"); w.wait_computation(); app.processEvents()
    assert drawn() and not w.held_strip.isVisible()
    w._change_text("count", "count", "300000"); w.wait_computation(); app.processEvents()
    assert not drawn() and w.held_strip.isVisible() and "300 000" in w._held_text.text()
    w._held_off(); w.wait_computation(); app.processEvents()
    assert "boxes" not in w.project.export and not w.held_strip.isVisible()
    w.undo(); w.wait_computation(); app.processEvents()                # Ctrl+Z: its eye on again, and waiting
    assert "boxes" in w.project.export and w.held_strip.isVisible()
    # few pieces: drawn without asking
    w._change_text("count", "count", "10"); w.wait_computation(); app.processEvents()
    assert drawn() and not w.held_strip.isVisible()
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


def test_the_view_asks_before_drawing_a_huge_amount(tmp_path):
    pytest.importorskip("PySide6")
    from tensela.project_file import VERSION
    project = tmp_path / "many.json"
    project.write_text(json.dumps({"parametrico": VERSION, **PROJECT}), encoding="utf-8")
    script = tmp_path / "many.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script), str(project)], env=env, capture_output=True, text=True,
                            timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
