"""The Library panel (plan of the pending work, 2.14): the groups of the project and of the library, to put them."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tensela import library
from tensela.data import ShapeError
from tensela.groups import group
from tensela.project_file import open_

CASE = Path(__file__).parent / "data" / "caso_01.json"
ROTATION = ['distances', 'maximum distance', 'angles']


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def test_the_library_renames_a_group_and_finds_its_file(tmp_path):
    p = open_(CASE)
    group(p.graph, ROTATION, "turn", p.export)
    library.save(p.graph, "turn", where=tmp_path)
    assert library.file_of("turn", tmp_path).name == "turn.json"
    library.rename("turn", "fin turn", tmp_path)
    assert library.names(tmp_path) == ["fin turn"] and library.file_of("fin turn", tmp_path).name == "fin turn.json"
    assert not (tmp_path / "turn.json").exists()
    assert "fin turn" in library.kinds(tmp_path)                         # it still opens, with its new name
    library.save(p.graph, "turn", where=tmp_path)
    with pytest.raises(ShapeError, match="already"):
        library.rename("turn", "fin turn", tmp_path)
    with pytest.raises(ShapeError, match="not in the library"):
        library.file_of("nothing", tmp_path)


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import library
from tensela.groups import group_in_project
from tensela.ui import window, editor
from PySide6.QtCore import QSettings
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2] if len(a) > 2 else a)))
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()
failures = []
original = sys.excepthook
sys.excepthook = lambda *a: (failures.append(a[1]), original(*a))

def names(where):
    return w.library.names(where)

def run():
    assert w.panels["library"].toggleViewAction().shortcut().toString() == "Ctrl+Alt+L"
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    p = w.project
    node = group_in_project(p, ["distances", "maximum distance", "angles"], "turn")
    w._after_restructure(node.name); w.wait_computation(); app.processEvents()
    assert names("project") == ["turn"] and names("library") == [], (names("project"), names("library"))
    library.save(p.graph, "turn"); w._show_library(reread=True); app.processEvents()
    assert names("library") == ["turn"]
    item = w.library.items("library")[0]
    assert "Remap" in item.toolTip() or "Remapear" in item.toolTip(), item.toolTip()   # what it does
    info = item.data(258)                                                  # its swatch and its second line
    assert info["nodes"] == 3 and info["category"] in editor.COLOURS_CATEGORY, info
    assert info["gives"] and info["takes"], info
    for view in ("tiles", "list"):                                         # two ways of seeing it, remembered
        w.library.buttons[view].click(); app.processEvents()
        assert w.library.view == view and QSettings().value("library/view") == view
        assert w.library.groups.visualItemRect(item).isValid()
        drawn = w.library.groups.viewport().grab()                         # (it paints without failing)
    w.library.put_view("tiles")
    mime = w.library.groups.mimeData([item])                               # it is dragged as before
    assert bytes(mime.data("application/x-tensela-group")) == b"library:turn"
    w.library.search.setText("nothing like it"); app.processEvents()
    assert names("project") == [] and names("library") == []
    w.library.search.setText("tur"); app.processEvents()
    assert names("library") == ["turn"]
    before = sum(n.kind.name == "turn" for n in p.graph.nodes.values())
    w.library.put.emit("library", "turn"); app.processEvents()             # a double click
    w.editor.put_group("project", "turn", QPointF(2500, 800)); app.processEvents()   # a drop on the canvas
    assert sum(n.kind.name == "turn" for n in p.graph.nodes.values()) == before + 2
    library.rename("turn", "fin turn"); w._show_library(reread=True); app.processEvents()
    assert names("library") == ["fin turn"] and names("project") == ["turn"]
    w._delete_from_library("fin turn"); app.processEvents()
    assert library.names() == [] and names("library") == []
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


def test_the_panel_shows_filters_puts_renames_and_deletes(tmp_path):
    pytest.importorskip("PySide6")
    (tmp_path / "data").mkdir()                                            # (where the trash goes)
    script = tmp_path / "panel.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "TENSELA_LIBRARY": str(tmp_path / "library"), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script), str(CASE)], env=env, capture_output=True, text=True,
                            timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
