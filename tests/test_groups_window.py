"""Group 3.3 of the pending plan, in the window: grouping, entering and ungrouping inside a group, the eyes inside a
group, and a group with two results."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

CASE = Path(__file__).parent / "data" / "caso_01.json"

SCRIPT = r'''
import os, sys
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
answers = []
window.ask_text = lambda *a, **k: (answers.pop(0), True)
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()

def settle():
    w.wait_computation(); app.processEvents()

def choose(*names):
    w.editor.graph_scene.clearSelection()
    for n in names:
        w.editor.boxes[n].setSelected(True)
    app.processEvents()

def fins():
    return np.array(w.project.graph.value("sun fins").values)

def run():
    w.open_(sys.argv[1]); settle()
    before = fins()
    choose("distances", "maximum distance", "angles"); answers.append("rotation"); w.group(); settle()
    assert "rotation 1" in w.project.graph.nodes
    # inside it, a group of two of its nodes
    w.enter_group("rotation 1"); settle()
    choose("maximum distance", "angles"); answers.append("scale angles"); w.group(); settle()
    small = next(n for n, x in w._canvas.nodes.items() if x.kind.name == "scale angles")
    assert "scale angles" in w.project.graph.definitions
    assert any(s["type"] == "scale angles" for s in w.project.graph.definitions["rotation"].nodes.values())
    assert np.allclose(fins(), before)
    # one level deeper: edited there, it reaches the project
    w.enter_group(small); settle()
    assert len(w._levels) == 2 and "rotation 1" in w.card_nodes.title.text() and small in w.card_nodes.title.text()
    remap = next(n for n, x in w._canvas.nodes.items() if x.kind.name == "Remap")
    w._canvas.change(remap, "to_max", 45.0); w._after_edit(); settle()
    edited = fins()
    assert not np.allclose(edited, before)
    # undo, inside: still two levels in, and the value back
    w.undo(); settle()
    assert len(w._levels) == 2 and np.allclose(fins(), before), (len(w._levels), fins()[:2], before[:2])
    w.redo(); settle()
    assert np.allclose(fins(), edited)
    w.quit_group(); settle()
    assert len(w._levels) == 1 and small in w._canvas.nodes
    # an eye inside: drawn in 3D while one is inside (the centres that reach the group)
    w._toggle_see("centres", True); settle()
    assert w.INSIDE_KEY + "centres" in w.viewer.view.actors, list(w.viewer.view.actors)
    assert w.editor.boxes["centres"].sees
    # ungrouped inside: back loose, and the group leaves the project's groups
    choose(small); w.ungroup(); settle()
    assert "scale angles" not in w.project.graph.definitions and "angles" in w._canvas.nodes
    assert np.allclose(fins(), edited)
    w.quit_group(); settle()
    assert w._inside is None and np.allclose(fins(), edited)
    assert not any(k.startswith(w.INSIDE_KEY) for k in w.viewer.view.actors)
    # two results: the group node and a Group result, with the name of the inside node
    w.open_(sys.argv[2]); settle()
    choose("centres", "distances", "maximum distance", "angles"); answers.append("two"); w.group(); settle()
    g = w.project.graph
    assert g.nodes["angles"].kind.name == "Group result" and np.allclose(fins(), before)
    assert "angles" in w.editor.boxes
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


def test_groups_inside_groups_in_the_window(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("pyvista")
    script = tmp_path / "groups.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    again = tmp_path / "again.json"
    again.write_text(CASE.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run([sys.executable, str(script), str(CASE), str(again)], env=env, capture_output=True,
                            text=True, timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
