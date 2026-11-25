"""Victor's morning notes: the axes left behind after drawing, Model on any background, one value for several
numbers, and corners and Shift alignment while drawing a curve."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from tensela import geometry as geo


def test_a_drawn_curve_breaks_at_its_corners_and_is_smooth_elsewhere():
    points = [[0, 0, 0], [1, 0.5, 0], [2, 0, 0, 1, 1], [3, 0.5, 0], [4, 0, 0]]
    assert list(geo.drawn_corners(points)) == [False, False, True, False, False]
    for mode in geo.MODES_CURVE:
        for closed in (False, True):
            v = np.asarray(geo.drawn_curve(points, mode, 3, closed).values)
            k = int(np.argmin(np.linalg.norm(v - [2, 0, 0], axis=1)))
            assert np.linalg.norm(v[k] - [2, 0, 0]) < 1e-9                 # it passes through the corner
            before, after = v[k] - v[k - 1], v[k + 1] - v[k]
            turn = np.degrees(np.arccos(before @ after / np.linalg.norm(before) / np.linalg.norm(after)))
            assert turn > 20, (mode, closed)                              # and breaks there
    smooth = np.asarray(geo.drawn_curve([p[:3] for p in points]).values)
    k = int(np.argmin(np.linalg.norm(smooth - [2, 0, 0], axis=1)))
    before, after = smooth[k] - smooth[k - 1], smooth[k + 1] - smooth[k]
    turn = np.degrees(np.arccos(before @ after / np.linalg.norm(before) / np.linalg.norm(after)))
    assert turn < 10                                                       # without the corner, it goes round
    assert geo.drawn_row((1, 2, 3)) == [1, 2, 3] and geo.drawn_row((1, 2, 3), corner=True) == [1, 2, 3, 1, 1]
    assert geo.drawn_row((1, 2, 3), 2.0) == [1, 2, 3, 2.0]


def test_one_value_typed_for_several_numbers_of_the_panel():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from tensela.graph import Graph
    from tensela.ui.node_panel import PanelNode
    app = QApplication.instance() or QApplication([])  # noqa: F841
    g = Graph()
    g.node("Box", "box")
    panel = PanelNode()
    panel.display(g.nodes["box"])
    fields = dict((n, f) for f, n in panel.several.fields)
    assert {"width", "depth", "height"} <= set(fields)
    sent, several = [], []
    panel.change.connect(lambda *a: sent.append(a))
    panel.change_several.connect(lambda *a: several.append(a))
    panel.several._mark(["width", "depth", "height"])                     # as dragging over the three
    fields["width"].setText("0,5")
    fields["width"].setModified(True)
    fields["width"].editingFinished.emit()
    assert several == [("box", ["width", "depth", "height"], "0,5")] and not sent
    assert not panel.several.group                                         # and it lets go
    panel.several._mark(["width", "depth"])
    fields["depth"].setModified(False)
    fields["depth"].editingFinished.emit()                                 # left without typing: nothing
    assert len(several) == 1


def test_model_follows_the_background_chosen_for_the_view():
    pytest.importorskip("PySide6")
    from tensela.ui import studio, theme
    from tensela.ui.viewer import Viewer

    class View:                                     # what the view is painted with, without painting it
        def set_background(self, colour, top=None):
            self.background = (colour, top)

    class Stand:
        style_name, view, _theme_background = "model", View(), "#16181d"

    stand = Stand()
    try:
        theme.put_tones(view="theme")
        Viewer._apply_background(stand)
        assert stand.view.background == studio.MODEL_BACKGROUND             # its own light paper
        theme.put_tones(view="dark")
        Viewer._apply_background(stand)
        assert stand.view.background[0] == "#16181d"                        # the background chosen
    finally:
        theme.put_tones(view="theme")


SCRIPT = r'''
import json, os, sys
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window, theme
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def actors():
    return [n for n in w.viewer.view.renderer.actors if n.startswith("_drawing")]

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    w.editor.select("trace"); app.processEvents()
    w.draw("trace"); app.processEvents()
    d = w.viewer.drawing
    assert d.active and any("axis" in n for n in actors()), actors()
    d.toggle_corner([1]); w.wait_computation(); app.processEvents()
    points = w.project.graph.nodes["trace"].inputs["points"]
    assert len(points[1]) == 5 and points[1][4] == 1 and len(points[0]) == 3, points
    assert "_drawing_corners" in actors()
    d.insert(1); d.delete(1)                                       # the corner stays with its point
    assert list(d.corners) == [False, True, False]
    q, guides = d._aligned(np.array([2.03, 1.0, 0.0]), None, 2)    # in line with (2, 0): straight up
    assert np.allclose(q, [2.0, 1.0, 0.0]) and len(guides) >= 1
    q, guides = d._aligned(np.array([1.4, 0.004, 0.0]), None, None)   # near the line y = 0 of the others
    assert abs(q[1]) < 1e-12 and guides
    w.finish_drawing(); app.processEvents()
    assert not actors(), actors()                                  # nothing left in the view, the axes neither
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
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_drawing_leaves_nothing_behind_and_corners_and_shift_work(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("pyvista")
    project = {"parametrico": 1, "nodes": {"trace": {"type": "Drawn curve",
                                                     "points": [[0, 0, 0], [1, 1, 0], [2, 0, 0]]}},
               "export": ["trace"]}
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(project))
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}
    script = tmp_path / "draw.py"
    script.write_text(SCRIPT)
    done = subprocess.run([sys.executable, str(script), str(path)], env=env, capture_output=True, text=True,
                          timeout=120)
    assert "ok" in done.stdout, done.stderr[-3000:]


def test_alt_and_drag_over_the_numbers_of_a_card():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QLineEdit
    from tensela.graph import Graph
    from tensela.ui.editor import HEIGHT_HEADER, HEIGHT_ROW, Editor
    app = QApplication.instance() or QApplication([])
    g = Graph()
    g.node("Box", "box")
    e = Editor()
    e.resize(900, 600)
    e.show()
    e.display(g)
    app.processEvents()
    box = e.boxes["box"]

    def at(row):                                     # the value of a row of the card, on the screen
        return QPointF(e.mapFromScene(box.mapToScene(QPointF(box.width - 20, HEIGHT_HEADER + (row + 0.5) *
                                                              HEIGHT_ROW))))

    def send(kind, row, buttons):
        button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
        event = QMouseEvent(kind, at(row), e.viewport().mapToGlobal(at(row)), button, buttons,
                            Qt.KeyboardModifier.AltModifier)
        {QEvent.Type.MouseButtonPress: e.mousePressEvent, QEvent.Type.MouseMove: e.mouseMoveEvent,
         QEvent.Type.MouseButtonRelease: e.mouseReleaseEvent}[kind](event)

    names = [i.name for i in box.visible()]
    first, last = names.index("width"), names.index("height")
    before = dict(e.positions())
    send(QEvent.Type.MouseButtonPress, first, Qt.MouseButton.LeftButton)
    send(QEvent.Type.MouseMove, last, Qt.MouseButton.LeftButton)
    assert box.several == {"width", "depth", "height"}
    send(QEvent.Type.MouseButtonRelease, last, Qt.MouseButton.NoButton)
    assert dict(e.positions()) == before                                  # the card did not move
    field = next(w.widget() for w in e.graph_scene.items() if hasattr(w, "widget") and isinstance(w.widget(), QLineEdit))
    written = []
    e.values_changed.connect(lambda *a: written.append(a))
    field.setText("0,5")
    field.setModified(True)
    field.returnPressed.emit()
    assert written == [("box", ["width", "depth", "height"], "0,5")] and not box.several
