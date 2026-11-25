"""Moving around the 3D view: the button schemes and the turn without tipping over."""

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from tensela.ui.navigation import RIGHT, SCHEMES, LEFT, MIDDLE, _rotate  # noqa: E402


def test_each_scheme_orbits_with_its_button():
    assert SCHEMES["blender"][(MIDDLE, "")] == "orbit" and (LEFT, "") not in SCHEMES["blender"]
    assert SCHEMES["rhino"][(RIGHT, "")] == "orbit"
    assert SCHEMES["tensela"][(LEFT, "")] == "orbit"
    assert all(set(e.values()) <= {"orbit", "pan", "zoom"} for e in SCHEMES.values())


def test_rotate_about_an_axis():
    v = _rotate(np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), np.pi / 2)
    assert np.allclose(v, [0, 1, 0])
    assert Qt.MouseButton.LeftButton == LEFT


SCRIPT = '''
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([])
app.setOrganizationName("Tensela")
app.setApplicationName("Tensela")
from tensela.ui import window
w = window.Window()
w._continue_without_saving = lambda: True
w.resize(1200, 800)
w.show()


def where(b, point):
    ren = b.plotter.renderer
    ren.SetWorldPoint(*point, 1.0)
    ren.WorldToDisplay()
    return ren.GetDisplayPoint()[:2]


def check():
    w.new_()
    app.processEvents()
    v, b = w.viewer, w.viewer._browser
    # From the front a new rectangle stands in elevation, where it is seen; in 3D it lies in plan.
    v.look("front")
    app.processEvents()
    assert w.editor.add("Rectangle").inputs.get("plane") == "elevation"
    v.isometric()
    app.processEvents()
    assert w.editor.add("Rectangle").inputs["plane"] == "plan"
    # A new Sun starts in the city of the Preferences.
    assert w.editor.add("Sun").inputs["location"] == "Madrid"
    w.apply_preference("preferences/location", "Montevideo")
    assert w.editor.add("Sun").inputs["location"] == "Montevideo"
    # «Other place», with its latitude, longitude and time zone: a new Sun takes them; a new Daylight, its latitude.
    for key, value in (("preferences/latitude", -12.5), ("preferences/longitude", -70.0),
                       ("preferences/time_zone", -5.0), ("preferences/location", "other place")):
        w.apply_preference(key, value)
    sun = w.editor.add("Sun").inputs
    assert (sun["location"], sun["latitude"], sun["longitude"], sun["time_zone"]) == \
        ("other place", -12.5, -70.0, -5.0)
    assert w.editor.add("Daylight").inputs["latitude"] == -12.5
    # Datos: a short list of numbers shows its first values beside its shape.
    w.editor.add("Number", name="heights")
    w._change_text("heights", "value", "3; 4,5; 6")
    w.wait_computation()
    app.processEvents()
    rows = {w.table.topLevelItem(i).text(0): w.table.topLevelItem(i).text(3) for i in range(w.table.topLevelItemCount())}
    assert "3 · 4,5 · 6" in rows["heights"], rows
    # Over the empty background, in parallel and in perspective: what is under the pointer stays under it.
    v.look("front")
    for parallel in (True, False):
        v.view.camera.parallel_projection = parallel
        app.processEvents()
        pointer = QPointF(150, 120)
        anchor = b._zoom_anchor(pointer)
        before = where(b, anchor)
        b.approach(0.5, anchor)
        after = where(b, anchor)
        assert abs(before[0] - after[0]) < 1.0 and abs(before[1] - after[1]) < 1.0, (parallel, before, after)
    # Towards the centre (Preferences): the centre of the view does not move.
    w.apply_preference("preferences/zoom", "centre")
    assert b._zoom_anchor(QPointF(150, 120)) is None
    focus = v.view.camera.focal_point
    b.approach(0.5, b._zoom_anchor(QPointF(150, 120)))
    assert max(abs(a - c) for a, c in zip(focus, v.view.camera.focal_point)) < 1e-9
    print("ok", flush=True)
    os._exit(0)


def run():
    try:
        check()
    except BaseException:
        import traceback
        traceback.print_exc()
        os._exit(2)


QTimer.singleShot(800, run)
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_zoom_towards_the_pointer_and_shapes_in_the_plane_of_the_view(tmp_path):
    import os
    import subprocess
    import sys
    pytest.importorskip("pyvista")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}
    script = tmp_path / "zoom.py"
    script.write_text(SCRIPT)
    done = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=120)
    assert "ok" in done.stdout, done.stderr[-3000:]
