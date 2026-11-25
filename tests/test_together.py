"""One option for several nodes (plan of the pending work, 2.3): with several nodes of one kind chosen, what is changed
in the node panel changes in all of them, computed once and undone in one step."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

CASE = Path(__file__).parent / "data" / "caso_01.json"

SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
QMessageBox.warning = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2] if len(a) > 2 else a)))
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()
failures = []
original = sys.excepthook
sys.excepthook = lambda *a: (failures.append(a[1]), original(*a))

def choose(*names):
    w.editor.graph_scene.clearSelection()
    for n in names:
        w.editor.boxes[n].setSelected(True)
    app.processEvents()

def note():
    found = w.panel_node.findChildren(QLabel, "together_note")
    return found[0].text() if found else ""

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    g = w.project.graph
    choose("sun fin", "marker")
    assert w._together == ["sun fin", "marker"], w._together
    assert note().startswith("2 “Box” chosen"), note()
    varies = {l.text(): l.toolTip() for l in w.panel_node.findChildren(QLabel, "varies")}
    assert "width · varies" in varies and "sun fin: 0.4" in varies["width · varies"], varies   # not the same in both
    w.panel_node.change.emit("sun fin", "width", "0.25"); w.wait_computation(); app.processEvents()
    assert g.nodes["sun fin"].inputs["width"] == 0.25 and g.nodes["marker"].inputs["width"] == 0.25
    varies = [l.text() for l in w.panel_node.findChildren(QLabel, "varies")]
    assert "width · varies" not in varies, varies                          # now the same: no mark
    assert note(), "the panel still shows both"
    w.panel_node.change_several.emit("marker", ["depth", "height"], "0.5"); w.wait_computation(); app.processEvents()
    assert all(g.nodes[n].inputs[i] == 0.5 for n in ("sun fin", "marker") for i in ("depth", "height"))
    w.undo(); w.wait_computation(); app.processEvents()
    g = w.project.graph
    assert g.nodes["sun fin"].inputs["depth"] == 0.05 and g.nodes["marker"].inputs["depth"] == 0.3
    assert g.nodes["sun fin"].inputs["width"] == 0.25 and g.nodes["marker"].inputs["width"] == 0.25
    w.undo(); w.wait_computation(); app.processEvents()
    g = w.project.graph
    assert g.nodes["sun fin"].inputs["width"] == 0.4 and g.nodes["marker"].inputs["width"] == 0.3
    choose("sun fin", "facade")                      # of different kinds: nothing together
    assert w._together == [] and note() == ""
    choose("marker")
    assert w._together == [] and note() == ""
    w.panel_node.change.emit("marker", "width", "0.6"); w.wait_computation(); app.processEvents()
    g = w.project.graph
    assert g.nodes["marker"].inputs["width"] == 0.6 and g.nodes["sun fin"].inputs["width"] == 0.4
    assert not failures, failures
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


def test_the_panel_changes_all_the_chosen_nodes_of_one_kind(tmp_path):
    pytest.importorskip("PySide6")
    script = tmp_path / "together.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "TENSELA_LIBRARY": str(tmp_path / "library"), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script), str(CASE)], env=env, capture_output=True, text=True,
                            timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
