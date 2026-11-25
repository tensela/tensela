"""Bar analysis: checked against the formulas of the structures books."""
from pathlib import Path

import numpy as np
import pytest

from tensela import frames as F
from tensela import geometry as geo
from tensela import language
from tensela import optimize as O
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.project_file import open_
from tensela.sections import CATALOGUE, section

E = 210e9


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _points(*p):
    return Data(np.array(p, float), ("p",), None, kind=geo.POINT)


def test_the_sections_measure_as_the_tables():
    ipe, heb = section("IPE 300"), section("heb300")
    assert ipe.area * 1e4 == pytest.approx(53.8, abs=0.1) and ipe.strong * 1e8 == pytest.approx(8356, rel=2e-3)
    assert heb.area * 1e4 == pytest.approx(149.1, abs=0.2) and heb.strong * 1e8 == pytest.approx(25170, rel=2e-3)
    assert section(10).name == "IPE 300" and len(CATALOGUE) == 56 and section(55).name == "HEB 600"
    assert section("rect 200x400").strong == pytest.approx(0.2 * 0.4 ** 3 / 12)
    assert section("tubo 200x100x8").area == pytest.approx(0.2 * 0.1 - 0.184 * 0.084)
    assert section("pipe 168x8").strong == pytest.approx(np.pi / 64 * (0.168 ** 4 - 0.152 ** 4))
    assert section("tubo redondo 168x8").area == section("caño 168x8").area == section("pipe 168x8").area
    for wrong in ("IPE 310", "beam 3", 56):
        with pytest.raises(ShapeError):
            section(wrong)


def test_a_cantilever_with_a_load_at_its_end():
    line, s, L, P = geo.line((0, 0, 0), (4, 0, 0)), section("IPE 300"), 4.0, 10000.0
    common = dict(supports=_points((0, 0, 0)), loads=_points((4, 0, 0)), load=P, self_weight=False)
    assert float(F.bar_analysis(line, **common, show='largest displacement').values) == pytest.approx(
        P * L ** 3 / (3 * E * s.strong), rel=1e-6)
    assert F.bar_analysis(line, **common, show='moments').values[0] == pytest.approx(P * L, rel=1e-6)
    assert float(F.bar_analysis(line, **common, show='largest utilization').values) == pytest.approx(
        100 * P * L / s.modulus_strong / 275e6, rel=1e-6)
    assert np.allclose(F.bar_analysis(line, **common, show='reactions').values, [[0, 0, P]], atol=1e-3)
    bent = np.asarray(F.bar_analysis(line, **common, scale=1.0).values)[0]
    assert bent[-1, 2] == pytest.approx(-P * L ** 3 / (3 * E * s.strong), rel=1e-6) and bent[0, 2] == 0


def test_a_simply_supported_beam_under_a_spread_load():
    line, s, L, q = geo.line((0, 0, 0), (6, 0, 0)), section("IPE 300"), 6.0, 5000.0
    common = dict(supports=_points((0, 0, 0), (6, 0, 0)), support='pinned', load_per_metre=q, self_weight=False)
    middle = np.asarray(F.bar_analysis(line, **common, scale=1.0).values)[0][F.SAMPLES // 2]
    assert -middle[2] == pytest.approx(5 * q * L ** 4 / (384 * E * s.strong), rel=1e-6)
    assert F.bar_analysis(line, **common, show='moments').values[0] == pytest.approx(q * L ** 2 / 8, rel=1e-6)
    assert np.allclose(F.bar_analysis(line, **common, show='reactions').values[:, 2], q * L / 2)
    # Its two ends are held: the largest move is in the middle, and the automatic scale draws it a twentieth of 6 m.
    sag = 5 * q * L ** 4 / (384 * E * s.strong)
    assert float(F.bar_analysis(line, **common, show='largest displacement').values) == pytest.approx(sag, rel=1e-6)
    drawn = np.asarray(F.bar_analysis(line, **common).values)[0][F.SAMPLES // 2]
    assert -drawn[2] == pytest.approx(0.05 * L, rel=1e-6)


def test_a_bar_far_too_weak_bends_a_lot_but_is_not_loose():
    common = dict(supports=_points((0, 0, 0)), support='clamped', loads=_points((4, 0, 0)), load=40000.0,
                  section_='IPE 80', self_weight=False)
    tip = float(F.bar_analysis(geo.line((0, 0, 0), (4, 0, 0)), **common, show='largest displacement').values)
    assert tip == pytest.approx(40000.0 * 4 ** 3 / (3 * E * section("IPE 80").strong), rel=1e-3)
    assert tip > 4                                             # more than the beam is long: still bending


def test_a_pulled_bar_its_weight_and_its_own_weight():
    line, s = geo.line((0, 0, 0), (4, 0, 0)), section("IPE 300")
    pull = Data(np.array([[10000.0, 0, 0]]), ("p",), None, kind=geo.VECTOR)
    common = dict(supports=_points((0, 0, 0)), loads=_points((4, 0, 0)), load=pull, self_weight=False)
    assert F.bar_analysis(line, **common, show='axial forces').values[0] == pytest.approx(10000)   # tension +
    assert float(F.bar_analysis(line, **common, show='largest displacement').values) == pytest.approx(
        10000 * 4 / (E * s.area))
    alone = dict(supports=_points((0, 0, 0)))
    assert float(F.bar_analysis(line, **alone, show='total weight').values) == pytest.approx(7850 * s.area * 4)
    q = 7850 * 9.81 * s.area
    assert float(F.bar_analysis(line, **alone, show='largest displacement').values) == pytest.approx(
        q * 4 ** 4 / (8 * E * s.strong), rel=1e-6)


def test_a_grid_of_bars_and_what_is_loose():
    g = Graph()
    g.node("Rectangle", "r", width=10.0, height=10.0)
    g.node("Mesh surface", "m", surface=g.nodes["r"], count_u=10, count_v=10)
    corners = _points((0, 0, 0), (10, 0, 0), (0, 10, 0), (10, 10, 0))
    used = F.bar_analysis(g.value("m"), supports=corners, support='pinned', section_='tube 200x100x8',
                          show='utilization')
    assert used.levels == ("bar",) and len(used.values) == 220 and used.values.max() > 0
    two = _points((0, 0, 0), (10, 0, 0))
    sideways = Data(np.array([[100.0, 0, -1000]]), ("p",), None, kind=geo.VECTOR)
    with pytest.raises(ShapeError, match="moves freely"):
        F.bar_analysis(geo.line((0, 0, 0), (10, 0, 0)), supports=two, support='roller', loads=_points((5, 0, 0)),
                       load=sideways)
    with pytest.raises(ShapeError, match="Nothing holds"):
        F.bar_analysis(geo.line((0, 0, 0), (10, 0, 0)))


SCRIPT = '''
import json, os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([])
app.setOrganizationName("Tensela")
app.setApplicationName("Tensela")
from tensela.ui import window
w = window.Window()
w._continue_without_saving = lambda: True
w.show()


def check():
    try:
        w.open_(sys.argv[1])
        w.wait_computation()
        app.processEvents()
        assert "bars" not in w.project.export                  # it gives a number: nothing to see
        w._change_text("bars", "show", "deformed")
        w.wait_computation()
        app.processEvents()
        assert "bars" in w.project.export, w.project.export     # now a bent beam: seen at once
        print("ok", flush=True)
    except BaseException:
        import traceback
        traceback.print_exc()
    os._exit(0)


QTimer.singleShot(800, check)
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_from_a_number_to_the_deformed_shape_it_is_seen_in_the_window(tmp_path):
    import json
    import os
    import subprocess
    import sys
    pytest.importorskip("PySide6")
    pytest.importorskip("pyvista")
    project = {"parametrico": 1, "export": ["axis"], "nodes": {
        "axis": {"type": "Line", "from": [0, 0, 3], "to": [6, 0, 3]},
        "ends": {"type": "Point", "x": [0.0, 6.0], "z": 3.0},
        "bars": {"type": "Bar analysis", "shape": {"node": "axis"}, "supports": {"node": "ends"},
                 "support": "pinned", "load_per_metre": 5000, "show": "moments"}}}
    (tmp_path / "beam.json").write_text(json.dumps(project))
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}
    script = tmp_path / "beam.py"
    script.write_text(SCRIPT)
    done = subprocess.run([sys.executable, str(script), str(tmp_path / "beam.json")], env=env, capture_output=True,
                          text=True, timeout=120)
    assert "ok" in done.stdout, done.stderr[-3000:]
