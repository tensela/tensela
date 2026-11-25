"""Watching it move: the moment of an Equilibrium, and the ▶ of the panel and of the sliders."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import simulation as S
from tensela.values import ShapeError


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def test_the_moment_goes_from_the_start_to_the_rest():
    line = geo.line((0, 0, 0), (10, 0, 0))
    lows = [float(np.asarray(S.equilibrium(line, moment=m).values)[:, 2].min()) for m in np.linspace(0, 1, 11)]
    assert lows[0] == 0 and lows[-1] == pytest.approx(float(np.asarray(S.equilibrium(line).values)[:, 2].min()))
    assert all(1.1 * lows[-1] <= low <= 0 for low in lows)          # on its way (it may bounce a little)
    supports = S.equilibrium(line, 10, 'start', S.Data(np.array([12.0, 0, 3]), (), None, kind=geo.POINT),
                             moment=0.0)
    assert np.allclose(np.asarray(supports.values)[-1], [12, 0, 3])  # the supports are where they go from the start
    with pytest.raises(ShapeError, match="moment"):
        S.equilibrium(line, moment=1.5)


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()
w.PLAY_SECONDS = 0.6

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    g = w.project.graph
    seen = []
    original = g.change
    def change(node, input_, value):
        if input_ in ("moment", "z"):
            seen.append(value)
        return original(node, input_, value)
    g.change = change
    w.editor.select("1 hung"); app.processEvents()
    w.play_input("1 hung", "moment", 0.0, 1.0)
    for _ in range(400):
        app.processEvents(); w.wait_computation()
        if w._playing is None:
            break
        import time; time.sleep(0.01)
    assert w._playing is None, "still playing"
    assert seen and seen[0] < 0.5 and seen[-1] == 1.0 and len(seen) > 3, seen
    assert g.nodes["1 hung"].inputs["moment"] == 1.0
    seen.clear()
    slider = w.sliders["4 B.z"] if "4 B.z" in w.sliders else next(s for k, s in w.sliders.items() if k.startswith("4 B"))
    slider.button_play.click()
    for _ in range(400):
        app.processEvents(); w.wait_computation()
        if w._playing is None:
            break
        import time; time.sleep(0.01)
    assert seen and seen[-1] == 12.0 and min(seen) == 4.0, seen
    assert not slider.button_stop.isVisible()
    w.undo(); w.wait_computation()                       # the whole play, undone at once
    assert w.project.graph.nodes["4 B"].inputs["z"] == 10.0, w.project.graph.nodes["4 B"].inputs["z"]

    # Pause, go on and stop: ■ puts back the value it had before playing.
    import time
    w.PLAY_SECONDS = 3.0
    slider = next(s for k, s in w.sliders.items() if k.startswith("4 B"))
    slider.button_play.click(); app.processEvents()
    assert slider.button_stop.isVisible() and w._playing is not None
    time.sleep(0.3); app.processEvents(); w.wait_computation(); app.processEvents()
    slider.button_play.click(); app.processEvents()          # pause
    paused = w.project.graph.nodes["4 B"].inputs["z"]
    assert w._playing["paused"] and 4.0 <= paused < 12.0, paused
    time.sleep(0.3); app.processEvents()
    assert w.project.graph.nodes["4 B"].inputs["z"] == paused          # it does not move while paused
    slider.button_play.click(); app.processEvents()          # it goes on
    assert not w._playing["paused"]
    slider.button_stop.click(); app.processEvents(); w.wait_computation()
    assert w._playing is None and not slider.button_stop.isVisible()
    assert w.project.graph.nodes["4 B"].inputs["z"] == 10.0

    # The tile of the Equilibrium: ▶, ⏸ and ■; another ▶ puts the moment back as ■ does.
    w.editor.select("1 hung"); app.processEvents()
    w.play_input("1 hung", "moment", 0.0, 1.0); app.processEvents()
    assert w.panel_node.playing == (("input", "1 hung", "moment"), "playing")
    w.play_input("1 hung", "moment", 0.0, 1.0); app.processEvents()
    assert w.panel_node.playing == (("input", "1 hung", "moment"), "paused")
    slider.button_play.click(); app.processEvents(); w.wait_computation()
    assert w.project.graph.nodes["1 hung"].inputs["moment"] == 1.0     # back where it was
    slider.button_stop.click(); app.processEvents(); w.wait_computation()
    assert w.project.graph.nodes["4 B"].inputs["z"] == 10.0

    # Stopping a computation: the values go back to those of the result in view.
    w.WAIT_COMPUTATION = 0.0
    slider = next(s for k, s in w.sliders.items() if k.startswith("4 B"))
    slider.cell.setValue(7.0); app.processEvents()
    assert w._in_progress is not None
    w.stop_computation(); w.wait_computation(); app.processEvents()
    assert w.project.graph.nodes["4 B"].inputs["z"] == 10.0, w.project.graph.nodes["4 B"].inputs["z"]
    slider = next(s for k, s in w.sliders.items() if k.startswith("4 B"))
    assert slider.cell.value() == 10.0

    # «Frame all» (F) from the front: it frames everything and stays in the front.
    import numpy as np
    w.viewer.look("front", False)
    before = np.subtract(w.viewer.view.camera.focal_point, w.viewer.view.camera.position)
    w._action_items["frame_all"].trigger(); app.processEvents()
    after = np.subtract(w.viewer.view.camera.focal_point, w.viewer.view.camera.position)
    assert w.viewer.name_view == 'Front', w.viewer.name_view
    assert np.allclose(before / np.linalg.norm(before), after / np.linalg.norm(after))
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


