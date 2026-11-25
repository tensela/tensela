"""The start screen (ui/start.py): the recipes travel inside Tensela and open, each one as a new project without a
name; the recent projects show the picture kept when they were saved; the «+» beside the tabs opens a new project;
Open… starts in the folder of the last project."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tensela.project_file import open_

TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "tensela" / "templates"


def test_every_recipe_is_there_with_its_picture_and_opens():
    from tensela.ui.start import RECIPES
    assert len(RECIPES) == 9
    for stem, _title, _line in RECIPES:
        assert (TEMPLATES / f"{stem}.png").is_file(), stem
        project = open_(str(TEMPLATES / f"{stem}.tela"))
        assert project.graph.nodes, stem


def test_every_text_of_the_start_screen_is_in_spanish():
    from tensela.translations import es
    from tensela.ui.start import RECIPES
    for _stem, title, line in RECIPES:
        assert title in es.TEXTS and line in es.TEXTS


def test_when_it_was_saved_in_words(monkeypatch):
    from tensela import language
    from tensela.ui.start import ago
    monkeypatch.setattr(language, "LANGUAGE", "en")
    now = time.mktime((2026, 11, 22, 18, 0, 0, 0, 0, -1))
    assert ago(now - 3600, now) == "today"
    assert ago(now - 86400, now) == "yesterday"
    assert ago(now - 3 * 86400, now) == "3 days ago"
    assert ago(now - 30 * 86400, now) == "23/10/2026"
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert ago(now - 3 * 86400, now) == "hace 3 días"


SCRIPT = r'''
import os, sys
from pathlib import Path
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import start, window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()
folder = Path(sys.argv[1])

def settle():
    for _ in range(6):
        w.wait_computation(); app.processEvents()

def run():
    saved = folder / "projects" / "roof.tela"
    saved.parent.mkdir()
    saved.write_bytes((start.TEMPLATES / "hypar-roof.tela").read_bytes())
    w.open_(str(saved)); settle()
    assert w._folder() == str(saved.parent)                       # Open… starts here now
    # The picture kept on saving (the view draws nothing without a screen: the one of the recipe stands in).
    assert start.save_preview(QImage(str(start.TEMPLATES / "hypar-roof.png")), saved)
    picture = QImage(str(start.preview_path(saved)))
    assert (picture.width(), picture.height()) == start.PREVIEW
    w.show_start(); app.processEvents()
    screen = w._start_screen
    assert [c.title for c in screen.recent_cards] == ["roof"]
    assert len(screen.recipe_cards) == 9
    # A recipe: a new tab, without a name, not among the recent ones.
    screen.recipe_cards[3].click(); settle()
    assert w.tabs.count() == 2 and w.filepath is None and w.project.graph.nodes
    app.processEvents(); assert w._start_screen is None          # it closed
    assert QSettings().value("recent") == [str(saved.resolve())]
    # The «+»: one more tab, empty, every time; right after the last tab.
    w.button_new_tab.click(); settle()
    assert w.tabs.count() == 3 and not w.project.graph.nodes
    w.button_new_tab.click(); settle()
    assert w.tabs.count() == 4
    app.processEvents()
    assert w.button_new_tab.x() - w.tabs.tabRect(w.tabs.count() - 1).right() < 16
    # New project on the start screen, over an empty tab without a name: that tab stays.
    w.show_start(); app.processEvents()
    centre, middle = w._start_screen.frameGeometry().center(), w.frameGeometry().center()
    assert abs(centre.x() - middle.x()) < 40 and abs(centre.y() - middle.y()) < 40     # over the window
    w._start_screen.new.emit(); settle()
    assert w.tabs.count() == 4
    w._start_screen.close(); app.processEvents()
    # Not shown at start any more: remembered.
    w.show_start(); app.processEvents()
    w._start_screen.show_switch.click()
    assert start.show_at_start() is False
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


def test_the_start_screen_in_the_window(tmp_path):
    pytest.importorskip("PySide6")
    script = tmp_path / "start.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script), str(tmp_path)], env=env, capture_output=True, text=True,
                            timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
