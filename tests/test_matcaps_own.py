"""The user's own matcaps (plan of the pending work, 2.13): a folder of pictures (PNG, JPG, EXR…) that appear in the
menu of the Matcap with their picture. The EXR files of tests/data/exr were made with Blender: 32 × 24 pixels, red
growing to the right, green growing upwards, blue 0.25, 0.35 or 0.45 in turn."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tensela import language
from tensela.data import ShapeError

EXR = Path(__file__).parent / "data" / "exr"


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _expected(w=32, h=24):
    out = np.zeros((h, w, 3))
    for up in range(h):
        for x in range(w):
            out[h - 1 - up, x] = [x / (w - 1), up / (h - 1), 0.25 + 0.1 * ((x + up) % 3)]
    return out


@pytest.mark.parametrize("name, tolerance", [("m_ZIP_16.exr", 3e-4), ("m_RLE_32.exr", 1e-6)])
def test_an_exr_is_read_as_it_was_written(name, tolerance):
    from tensela.ui.matcaps import _exr
    assert np.abs(_exr(EXR / name) - _expected()).max() < tolerance


def test_an_exr_it_cannot_read_says_what_to_do():
    from tensela.ui.matcaps import _exr
    with pytest.raises(ShapeError, match="ZIP compression"):
        _exr(EXR / "m_PIZ_16.exr")


def test_the_own_matcaps_are_the_pictures_of_the_folder(tmp_path, monkeypatch):
    from tensela.ui import matcaps
    monkeypatch.setenv("TENSELA_MATCAPS", str(tmp_path))
    assert matcaps.own() == {}
    (tmp_path / "bronze.exr").write_bytes((EXR / "m_ZIP_16.exr").read_bytes())
    (tmp_path / "notes.txt").write_text("not a picture")
    assert list(matcaps.own()) == ["file:bronze.exr"] and matcaps.known("file:bronze.exr")
    picture = matcaps.image_of("file:bronze.exr")
    assert picture.shape == (24, 32, 3) and picture.dtype == np.uint8
    assert picture[0, -1, 0] == 255 and picture[-1, 0, 0] == 0          # red to the right; screen gamma
    assert not matcaps.known("file:missing.png") and matcaps.image_of("plaster").shape == (256, 256, 3)


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QMenu
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window, viewer
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1200, 800); w.show()

def run():
    folder = os.environ["TENSELA_MATCAPS"]
    image = QImage(64, 64, QImage.Format.Format_RGB888)
    image.fill(QColor("#b87333")); image.save(folder + "/copper.png")
    open(folder + "/broken.png", "w").write("no")
    menu = QMenu(); w._menu_matcap(menu)
    sub = menu.findChild(QMenu, "matcaps")
    texts = [a.text() for a in sub.actions() if not a.isSeparator()]
    assert texts[:4] == ["Plaster", "Clay", "Graphite", "Ceramic"], texts
    assert "copper" in texts and "broken (cannot be read)" in texts and texts[-1] == "Open the matcaps folder", texts
    copper = next(a for a in sub.actions() if a.text() == "copper")
    assert not copper.icon().isNull()
    styles = []
    w.put_style_name_view = styles.append            # (drawing in Matcap needs a real screen)
    copper.trigger(); app.processEvents()
    assert viewer.MATCAP["name"] == "file:copper.png" and styles == ["matcap"], styles
    texture = viewer._texture_matcap("file:copper.png")
    assert texture is not None
    print("ok", flush=True)
    os._exit(0)

def safely():
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(4)

QTimer.singleShot(400, safely)
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_the_menu_shows_them_with_their_picture(tmp_path):
    pytest.importorskip("PySide6")
    (tmp_path / "matcaps").mkdir()
    script = tmp_path / "menu.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "TENSELA_MATCAPS": str(tmp_path / "matcaps"), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=90)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
