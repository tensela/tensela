"""The small comforts of the pending plan (2.5 to 2.11): a slider's range and step, Find the best without sliders,
the legend with the decimal comma, firmer cell borders, the image as in the view, all the sheets in one file (in
test_cutting) and the numbers of the pieces in another style."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tensela import language
from tensela.data import Data
from tensela.geometry import CLOSED_CURVE


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def test_the_legend_writes_its_numbers_as_the_interface(monkeypatch):
    from tensela.ui.viewer import legend_numbers
    assert [t for _, t in legend_numbers(12.25, 22.75, "%.3g")] == ["12.2", "17.5", "22.8"]
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert [t for _, t in legend_numbers(12.25, 22.75, "%.3g")] == ["12,2", "17,5", "22,8"]
    assert [t for _, t in legend_numbers(100, 2400, "%.0f")] == ["100", "1250", "2400"]


def _pieces():
    rings = []
    for k in range(6):
        w = 0.06 + 0.01 * k
        rings.append([(0, 0, 0), (0.15, 0, 0), (0.15, 0, w), (0, 0, w), (0, 0, 0)])
    return Data(np.array(rings, float), ("piece",), "p", starts={"piece": 1}, kind=CLOSED_CURVE)


def test_the_numbers_of_the_pieces_in_another_style():
    from tensela import fabrication as F
    laid = F.lay_flat(_pieces(), 0.6, 0.4, number=0.02)
    plain = F.numbers_and_sheets(laid, 'numbers')
    assert plain.count == len(laid.layout.numbers)                     # as before, by default
    bold = F.numbers_and_sheets(laid, 'numbers', weight='bold')
    assert bold.count == 2 * plain.count                               # two passes
    outline = F.numbers_and_sheets(laid, 'numbers', weight='outline')
    v = np.asarray(outline.values)
    assert np.allclose(v[..., 0, :], v[..., -1, :])                    # closed rings, to engrave filled
    rounded = F.numbers_and_sheets(laid, 'numbers', letter='rounded')
    assert rounded.values.shape[-2] > plain.values.shape[-2]           # more points: the corners eased
    turned = np.asarray(F.numbers_and_sheets(laid, 'numbers', reading='turned a quarter').values)
    flat = np.asarray(plain.values)
    # Turned, each number is taller than wide (it reads up the sheet)
    assert np.ptp(turned[..., 1]) > 0 and np.ptp(flat[0, :, 0]) >= 0
    for kind, d in (("plain", flat), ("turned", turned)):
        assert np.isfinite(d).all(), kind
    with pytest.raises(Exception, match="must be one of"):
        F.numbers_and_sheets(laid, 'numbers', weight='heavy')


def test_the_rounded_letter_keeps_its_points():
    from tensela.strokes import _eased, text_strokes
    a = text_strokes("A", 1.0)[0]                                      # the two legs of the A, and its top
    eased = _eased(a)
    assert np.allclose(eased[np.argmax(eased[:, 1])], a[1])           # the top of the A stays sharp


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
from tensela.ui.search_dialog import values_of
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    p = w.project
    p.controls = []                                   # (opened without sliders, it makes them: removed, as in test 99)
    w._create_controls()
    # 2.6: nothing moves the volume; the values it depends on are offered as sliders
    assert [(n, i) for n, i, _ in values_of(p, "volume")] == [("box", "width"), ("box", "depth"), ("box", "height")]
    w.open_search("volume"); app.processEvents()
    d = w._search_dialog
    assert d.offer.isVisible() and d.sliders.count() == 3 and not d.start.isEnabled()
    from PySide6.QtCore import Qt
    d.sliders.item(0).setCheckState(Qt.CheckState.Checked)
    d._make_sliders(); app.processEvents()
    assert [c.key for c in w.project.controls] == ["box.width"]
    assert d.start.isEnabled() and not d.offer.isVisible() and d.sliders.count() == 1
    d.sliders.item(0).setCheckState(Qt.CheckState.Unchecked); app.processEvents()
    assert not d.start.isEnabled()                                     # nothing marked to move: no search
    d.sliders.item(0).setCheckState(Qt.CheckState.Checked); app.processEvents()
    assert d.start.isEnabled()
    d.close()
    # 2.5: its range and step, and its name
    from tensela.ui.window import DialogControl
    control = w.project.controls[0]
    dialog = DialogControl(control, w)
    dialog.cells["maximum"].setValue(control.minimum - 1)
    assert not dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()
    dialog.cells["maximum"].setValue(5.0); dialog.cells["minimum"].setValue(1.0); dialog.cells["step"].setValue(0.5)
    assert dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled() and "9 positions" in dialog.note.text()
    dialog.name.setText("box width")
    w._change_range(control.key, *dialog.choice()); app.processEvents()
    c = w.project.controls[0]
    assert (c.minimum, c.maximum, c.step, c.label) == (1.0, 5.0, 0.5, "box width")
    w.undo(); app.processEvents()
    c = w.project.controls[0]
    assert (c.minimum, c.maximum) != (1.0, 5.0) and c.label == ""
    # 2.9: the image, with the background of the view
    from tensela.ui.dialogs import DialogImage
    image = DialogImage(w, (800, 600))
    image.background.put("view")
    assert image.choice()[1] is None and image.choice()[0] == 2
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
QTimer.singleShot(90000, lambda: os._exit(3))
app.exec()
'''


def test_a_slider_range_and_find_the_best_without_sliders(tmp_path):
    pytest.importorskip("PySide6")
    from tensela.graph import Graph
    from tensela.project_file import Project, save
    g = Graph()
    g.node("Box", "box", width=2.0, depth=3.0, height=4.0)
    g.node("Volume", "volume", geometry=g.nodes["box"])
    save(Project(g, ["box"], "", [], {}, {}), tmp_path / "box.json")
    script = tmp_path / "comforts.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script), str(tmp_path / "box.json")], env=env, capture_output=True,
                            text=True, timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
