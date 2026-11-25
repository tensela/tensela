"""Changing a node for another, keeping its wires (plan of the pending work, 2.1; Victor, test 53)."""
import numpy as np
import pytest

from tensela import language
from tensela.graph import Graph


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _graph():
    g = Graph()
    g.node("Series", "a", count=3)
    g.node("Series", "b", count=4, level="other")
    g.node("Merge", "merge 1", a=g.nodes["a"], b=g.nodes["b"])
    g.node("Summarise", "total", data=g.nodes["merge 1"], operation="sum")
    return g


def test_a_merge_becomes_a_merge_lists_with_its_wires():
    g = _graph()
    new, lost = g.replace("merge 1", "Merge lists")
    assert new.kind.name == "Merge lists" and new.name == "merge lists 1"    # an automatic name: the new one
    assert g.nodes["merge lists 1"].inputs["a"] is g.nodes["a"] and new.inputs["b"] is g.nodes["b"]
    assert g.nodes["total"].inputs["data"] is new                          # whoever used it, uses the new one
    assert "merge 1" not in g.nodes and lost == []
    assert float(g.value("total").values) == pytest.approx(0 + 1 + 2 + 0 + 1 + 2 + 3)
    assert list(g.nodes)[:3] == ["a", "b", "merge lists 1"]                 # in its place in the order


def test_a_name_of_its_own_stays_and_what_has_no_place_is_said():
    g = _graph()
    g.rename("merge 1", "both lists")
    g.change("both lists", "level", "pair")
    new, lost = g.replace("both lists", "Formula")
    assert new.name == "both lists" and new.kind.name == "Formula"
    assert new.inputs["a"] is g.nodes["a"] and new.inputs["b"] is g.nodes["b"]   # a and b: the Formula has them too
    assert lost == ["level"]                                               # a value of its own, without a place
    new, lost = g.replace("both lists", "Line")
    assert set(lost) >= {"a", "b"}                                         # a Line has no «a» nor «b»
    assert g.nodes["total"].inputs["data"] is new


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"                          # («merge 1» is the automatic name of a Merge in English)
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()
failures = []
original = sys.excepthook
sys.excepthook = lambda *a: (failures.append(a[1]), original(*a))

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    p = w.project
    where = list(w.editor.positions()["merge 1"])
    seen = "merge 1" in w.project.export
    w._replace("merge 1", "Merge lists"); w.wait_computation(); app.processEvents()
    assert "merge lists 1" in p.graph.nodes and "merge 1" not in p.graph.nodes
    assert w.editor.positions()["merge lists 1"] == where                 # in its place
    assert ("merge lists 1" in w.project.export) == seen                 # seen in 3D as it was
    assert w.project.graph.nodes["total"].inputs["data"] is w.project.graph.nodes["merge lists 1"]
    w.undo(); w.wait_computation(); app.processEvents()                   # a single step back
    assert "merge 1" in w.project.graph.nodes and "merge lists 1" not in w.project.graph.nodes
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


def test_the_window_changes_a_node_in_its_place_and_undoes_it_in_one_step(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from tensela.project_file import Project, save
    pytest.importorskip("PySide6")
    g = _graph()
    g.node("Line", "a line", **{"from": (0.0, 0.0, 0.0)}, to=(1.0, 0.0, 0.0))
    save(Project(g, ["a line", "merge 1"], "", [], {}, {"merge 1": [300, 100]}), tmp_path / "merge.json")
    script = tmp_path / "replace.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script), str(tmp_path / "merge.json")], env=env,
                            capture_output=True, text=True, timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]


def test_renaming_a_level_takes_the_nodes_that_pick_it_along():
    """Plan of the pending work, 2.2 (Victor, test 52): «vertex» → «point», and the nodes after it that picked
    «vertex» by its name pick «point»."""
    g = Graph()
    g.node("Series", "s", count=4, level="vertex")
    g.node("Point", "points", x=g.nodes["s"])
    g.node("Curve through points", "curve", points=g.nodes["points"], along="vertex")
    g.node("Pick", "second", data=g.nodes["points"], level="vertex", position=1)
    g.node("Series", "other", count=2, level="vertex")                     # not after «s»: it stays
    g.node("Pick", "apart", data=g.nodes["other"], level="vertex", position=0)
    g.change("s", "level", "point")
    changed = g.rename_level("s", "vertex", "point")
    assert set(changed) == {"curve", "second"}
    assert g.nodes["curve"].inputs["along"] == "point" and g.nodes["second"].inputs["level"] == "point"
    assert g.nodes["apart"].inputs["level"] == "vertex"
    assert np.asarray(g.value("second").values).tolist() == [1.0, 0.0, 0.0]
