"""«Find the best…»: the sliders move until a number reaches its minimum,
its maximum or a value, near (from where they are) or over the whole range (a population that evolves)."""
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tensela import language
from tensela import optimize as O
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def test_several_sliders_never_leave_their_ranges():
    seen = []

    def bowl(x):
        seen.append(list(x))
        return (x[0] - 3.3) ** 2 + (x[1] + 2.1) ** 2 + 1
    found = O.search_near(bowl, [O.Variable(0, -10, 10, 0.1), O.Variable(0, -10, 10, 0.1)])
    assert found.values == pytest.approx([3.3, -2.1]) and found.number == pytest.approx(1)
    edge = O.search_near(bowl, [O.Variable(0, -1, 1, 0.1), O.Variable(0, 0, 5, 0.5)])
    assert edge.values == pytest.approx([1, 0])                              # the best inside the ranges
    assert all(-10 <= a <= 10 and -10 <= b <= 10 for a, b in seen)


def test_what_fails_counts_as_the_worst_and_it_can_be_stopped():
    def fussy(x):
        if x[0] > 5:
            raise ShapeError("no")
        return (x[0] - 7) ** 2
    found = O.search_near(fussy, [O.Variable(0, 0, 10, 0.5)])
    assert found.values == [5.0] and found.failed > 0                        # as near to 7 as it can go
    calls = []
    stopped = O.search_near(lambda x: calls.append(x) or x[0] ** 2, [O.Variable(5, -10, 10, 0.001)],
                            stop=lambda: len(calls) >= 3)
    assert stopped.end == 'stopped' and stopped.attempts == 3 and math.isfinite(stopped.number)
    with pytest.raises(ShapeError, match="slider"):
        O.search_near(lambda x: 0, [])


def test_a_single_number_or_how_to_get_one():
    g = Graph()
    g.node("Series", "s", count=3)
    g.node("Rectangle", "r")
    g.node("Number", "n", value=2.5)
    assert O.single_number(g.value("n")) == 2.5
    with pytest.raises(ShapeError, match="Summarise"):
        O.single_number(g.value("s"))
    with pytest.raises(ShapeError, match="geometry"):
        O.single_number(g.value("r"))


def test_a_slider_of_a_list():
    g = Graph()
    g.node("Number", "list", value="1; 2; 3")
    O.put_value(g, "list", "value", 7.0, 1, whole=True)
    assert g.nodes["list"].inputs["value"] == "1; 7; 3"


def test_wide_with_whole_steps_and_a_list_of_sliders():
    # Six heights of a polyline (a list of sliders, like a Gene Pool): the flattest one, whole centimetres.
    def bumps(x):
        return sum(abs(a - b) for a, b in zip(x, x[1:])) + abs(x[0] - 3) + abs(x[-1] - 3)
    found = O.search(bumps, [O.Variable(0, 0, 10, 1) for _ in range(6)], method='both', seconds=20)
    assert found.values == [3.0] * 6 and found.number == 0
    stopped = O.search(bumps, [O.Variable(0, 0, 10, 1) for _ in range(6)], method='wide', stop=lambda: True)
    assert stopped.end == 'stopped'


SCRIPT = r'''
import os, sys, time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
from tensela.optimize import single_number
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    g = w.project.graph
    w.open_search("d"); app.processEvents()
    d = w._search_dialog
    assert d.objective.currentData() == "d" and d.sliders.count() == 1
    d.start.click()
    for _ in range(1000):
        app.processEvents(); time.sleep(0.01)
        if d._thread is None:
            break
    w.wait_computation(); app.processEvents()
    t = w.project.graph.nodes["t"].inputs["value"]
    exact = single_number(w.project.graph.value("exact distance"))
    assert abs(single_number(w.project.graph.value("d")) - exact) < 1e-3, (t, exact)
    assert abs(w.sliders["t.value"].cell.value() - t) < 1e-9                # the slider shows it
    assert d.found.count() > 1 and ("Found" in d.status.text() or "Encontrado" in d.status.text())
    d._put_back(d.found.item(1)); w.wait_computation(); app.processEvents()
    assert w.project.graph.nodes["t"].inputs["value"] != t
    w.undo(); w.wait_computation(); app.processEvents()
    assert w.project.graph.nodes["t"].inputs["value"] == t                  # one Ctrl + Z: the best again
    w.undo(); w.wait_computation(); app.processEvents()
    assert w.project.graph.nodes["t"].inputs["value"] == 0.15               # and one more: before searching
    w.sliders["t.value"].cell.setValue(0.9); w.wait_computation(); app.processEvents()
    d.fill("d"); d.method.put("wide"); d._show_how("wide")
    assert d.evolution.isVisibleTo(d)
    d.start.click()
    for _ in range(3000):
        app.processEvents(); time.sleep(0.01)
        if d._thread is None:
            break
    w.wait_computation(); app.processEvents()
    assert abs(single_number(w.project.graph.value("d")) - exact) < 1e-3             # from 0.9: the lowest anyway
    assert d.progress.averages, "the chart has the averages of the generations"
    w.open_search("exact distance"); app.processEvents()
    assert not d._pieces and ("No slider" in d.status.text() or "Ningún control" in d.status.text())
    # (what it depends on, offered as sliders: plan of the pending work, 2.6)
    assert d.sliders.count() == len(d._offered) and d.offer.isVisible() == bool(d._offered)
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


