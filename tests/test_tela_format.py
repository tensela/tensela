"""The project file of Tensela: `.tela` with the key "tensela". The projects of before (`.json`, key "parametrico")
open as they are, and saved again as `.json` they keep their key, so the program of before still opens them."""
import json
import os
import subprocess
import sys
from pathlib import Path

from tensela.project_file import KEY, OLD_KEY, format_key, format_version, open_, save
from tensela import library
from tensela.groups import group

from test_graph import case_01


def test_a_tela_file_says_tensela_and_opens_again(tmp_path):
    filepath = save(case_01(), tmp_path / "facade.tela")
    content = json.loads(filepath.read_text(encoding="utf-8"))
    assert content[KEY] == 1 and OLD_KEY not in content
    assert list(open_(filepath).graph.nodes) == list(case_01().nodes)


def test_a_project_of_before_keeps_its_key_while_it_is_json(tmp_path):
    filepath = save(case_01(), tmp_path / "facade.json")
    content = json.loads(filepath.read_text(encoding="utf-8"))
    assert content[OLD_KEY] == 1 and KEY not in content
    assert list(open_(filepath).graph.nodes) == list(case_01().nodes)


def test_either_key_is_read():
    assert format_version({"tensela": 1}) == 1
    assert format_version({"parametrico": 1}) == 1
    assert format_version({}) is None
    assert format_key("a/b.json") == OLD_KEY and format_key("a/b.tela") == KEY and format_key("b") == KEY


def test_a_group_of_the_library_says_tensela(tmp_path):
    g = case_01()
    group(g, ["distancias", "distancia máxima", "ángulos"], "rotation")
    filepath = library.save(g, "rotation", where=tmp_path)
    assert json.loads(filepath.read_text(encoding="utf-8"))[KEY] == 1


SCRIPT = r'''
import os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True

def run():
    try:
        w.open_(sys.argv[1]); w.wait_computation()
        seen = {}
        def ask(parent, title, suggested, filters):
            seen["suggested"], seen["filters"] = suggested, filters
            return sys.argv[2], filters
        QFileDialog.getSaveFileName = staticmethod(ask)
        assert w.save_as()
        print(seen["suggested"]); print(seen["filters"]); print(w.filepath, flush=True)
        os._exit(0)
    except Exception:
        import traceback; traceback.print_exc(); sys.stderr.flush(); os._exit(4)

QTimer.singleShot(300, run)
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_save_as_offers_tela_for_a_project_of_before(tmp_path):
    before = save(case_01(), tmp_path / "facade.json")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "XDG_CONFIG_HOME": str(tmp_path / "c"),
           "XDG_DATA_HOME": str(tmp_path / "d")}
    out = subprocess.run([sys.executable, "-c", SCRIPT, str(before), str(tmp_path / "new")], capture_output=True,
                         text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    suggested, filters, saved = out.stdout.strip().splitlines()[-3:]
    assert suggested.endswith("facade.tela")
    assert "*.tela" in filters
    assert saved.endswith("new.tela")
    assert json.loads(Path(saved).read_text(encoding="utf-8"))[KEY] == 1
