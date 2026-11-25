"""The process that computes (calculator.py): it gives back the results of the graph the window sends, computes again
only what changed, drops a computation when a newer request arrives, and the window shows its results as before."""
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tensela import calculator as C
from tensela.graph import Graph
from tensela.project_file import open_

SRC = Path(__file__).resolve().parent.parent / "src"
TOWER = SRC / "tensela" / "templates" / "twisting-tower.tela"


def test_a_fingerprint_changes_with_the_node_and_with_what_feeds_it():
    graph = open_(str(TOWER)).graph
    before = C.fingerprints(graph, C.graph_message(graph))
    graph.change("floor", "count", 30)
    after = C.fingerprints(graph, C.graph_message(graph))
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"floor", "height", "turn", "raised", "turned", "slabs"}       # not «plan»


def test_a_fingerprint_changes_when_the_file_it_reads_changes(tmp_path):
    image = tmp_path / "picture.png"
    image.write_bytes(b"one")
    graph = Graph()
    graph.node("Image sampler", "sampler", file=str(image))
    first = C.fingerprints(graph, C.graph_message(graph))["sampler"]
    os.utime(image, ns=(1, 10 ** 18))
    assert C.fingerprints(graph, C.graph_message(graph))["sampler"] != first


class _Replies:
    """The replies of the process, without the messages that say which node it starts."""

    def __init__(self):
        self.queue, self.nodes = queue.Queue(), []

    def put(self, reply):
        if reply.get("op") == "at":
            self.nodes.append(reply["node"])
        else:
            self.queue.put(reply)

    def get(self, timeout):
        return self.queue.get(timeout=timeout)


@pytest.fixture
def calculator():
    replies = _Replies()
    calc = C.Calculator(replies.put)
    yield calc, replies
    calc.close()


def test_it_computes_and_remembers(calculator):
    calc, replies = calculator
    graph = open_(str(TOWER)).graph
    assert calc.send(C.request(graph, 1, 1, None, "en"))
    reply = replies.get(timeout=60)
    assert reply["turn"] == 1 and sorted(reply["computed"]) == sorted(graph.nodes) and not reply["errors"]
    for name, value in reply["values"].items():
        graph.nodes[name]._value = value
    graph.change("floor", "count", 30)
    calc.send(C.request(graph, 2, 1, None, "en"))
    reply = replies.get(timeout=60)
    assert "plan" not in reply["computed"] and "slabs" in reply["computed"]
    assert reply["values"]["slabs"].values.shape[0] == 30
    # A window without the results (another tab, a project opened again): it gets them without computing again.
    fresh = open_(str(TOWER)).graph
    fresh.change("floor", "count", 30)
    calc.send(C.request(fresh, 3, 2, None, "en"))
    reply = replies.get(timeout=60)
    assert reply["computed"] == [] and sorted(reply["values"]) == sorted(fresh.nodes)


def test_its_errors_come_back_with_their_node(calculator):
    calc, replies = calculator
    graph = Graph()
    graph.node("Formula", "f", formula="a +* 2")
    calc.send(C.request(graph, 1, 1, None, "es"))
    reply = replies.get(timeout=60)
    (name, expected, text, _), = reply["errors"]
    assert name == "f" and expected and text.startswith("En «f» (Fórmula)")       # in the language of the window


def test_a_newer_request_drops_the_computation_at_the_next_node():
    """Two requests waiting: the first is dropped as soon as its first node is about to be computed."""
    to_process, from_window = os.pipe()
    to_window, from_process = os.pipe()
    graph = open_(str(TOWER)).graph
    C._write(from_window, C.request(graph, 1, 1, None, "en"))
    C._write(from_window, C.request(graph, 2, 1, None, "en"))
    from tensela import language
    before = language.LANGUAGE
    worker = threading.Thread(target=C._Process(to_process, from_process).run)
    worker.start()
    first = C._read(to_window)
    second = C._read(to_window)
    while second.get("op") == "at":                         # (the nodes it starts, one by one)
        second = C._read(to_window)
    C._write(from_window, {"op": "quit"})
    worker.join(30)
    language.LANGUAGE = before                              # (it computed in this process: the language it set)
    assert first == {"turn": 1, "cancelled": True}
    assert second["turn"] == 2 and sorted(second["computed"]) == sorted(graph.nodes)


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()

def settle():
    for _ in range(4):
        w.wait_computation(); app.processEvents()

def run():
    w.open_(sys.argv[1]); settle()
    calc = w._calculator_
    assert calc is not None and calc.alive() and calc.current.process.pid != os.getpid()      # it computed apart
    g = w.project.graph
    assert all(node._value is not None for node in g.nodes.values())
    assert "Recalculated 7 of 7" in w.statusBar().currentMessage(), w.statusBar().currentMessage()
    w._change_text("floor", "count", "30"); settle()
    assert g.nodes["slabs"]._value.values.shape[0] == 30
    assert "Recalculated 6 of 7" in w.statusBar().currentMessage(), w.statusBar().currentMessage()
    # An error: on its card, as before.
    w._change_text("height", "formula", "a +* 2"); settle()
    assert w.editor.boxes["height"].with_error, "the error is not on the card"
    w._change_text("height", "formula", "a * 3.5"); settle()
    assert not w.editor.boxes["height"].with_error
    # If the process ends, the next change starts another one.
    before = calc.current.process.pid
    calc.current.process.kill(); calc.current.process.wait()
    for _ in range(50):
        app.processEvents()
    w._change_text("floor", "count", "12"); settle()
    assert calc.alive() and calc.current.process.pid != before
    assert g.nodes["slabs"]._value.values.shape[0] == 12
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


def test_the_window_computes_apart(tmp_path):
    pytest.importorskip("PySide6")
    script = tmp_path / "window.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"), "XDG_RUNTIME_DIR": str(tmp_path),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(SRC)}
    env.pop("TENSELA_CALCULATE_HERE", None)
    result = subprocess.run([sys.executable, str(script), str(TOWER)], env=env, capture_output=True, text=True,
                            timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]


# --- Package 2: «Stop» at once, failures that do not close the window, a node stuck in what no longer serves ---------

SLOW_NODES = r'''
"""A node that takes the time it is told (only for the tests)."""
import time
from tensela.nodes import Input, NodeType, _register, number


CALLS = []                                  # each time it computes in this process


def _wait(seconds, name):
    CALLS.append(float(seconds))
    time.sleep(float(seconds))
    return number(float(seconds), "value", name)


_register(NodeType("Wait", "Values", (Input("seconds", 1.0, single=True),), "value", _wait, "Waits."))
'''

SLOW_SCRIPT = r'''
import os, sys, time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
import slow_nodes  # noqa: F401
from tensela.graph import Graph
from tensela.project_file import Project
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()
w.WAIT_COMPUTATION = 0.0

def settle(seconds=30):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        w.wait_computation(0.05); app.processEvents()
        if w._in_progress is None:
            return

def until(condition, seconds=20):
    limit = time.monotonic() + seconds
    while not condition() and time.monotonic() < limit:
        app.processEvents(); time.sleep(0.01)
    assert condition()

def in_slow(calc):
    """The process is in «slow» of the turn it computes now (not of the one before, which may still be ending)."""
    at = calc.at
    return at is not None and at[0] == calc.busy and at[1] == "slow"

def run():
    g = Graph()
    g.node("Number", "n", value=1.0)
    g.node("Wait", "slow", seconds=0.2)
    g.node("Formula", "after", formula="a + b", a=g.nodes["n"], b=g.nodes["slow"])
    w._load(Project(g, ["after"]), None); settle()
    calc = w._calculator_
    assert w.project.graph.nodes["after"]._value is not None
    until(lambda: calc.spare is not None)

    # «Stop» in the middle of a long node: at once; the process ready takes the place of the one that was stuck.
    w._change_text("slow", "seconds", "30")
    until(lambda: in_slow(calc))
    stuck = calc.current.process.pid
    start = time.monotonic(); w.stop_computation()
    assert time.monotonic() - start < 1.0 and calc.current.process.pid != stuck
    until(lambda: not os.path.exists(f"/proc/{stuck}") or open(f"/proc/{stuck}/stat").read().split()[2] == "Z")
    assert "stopped" in w.statusBar().currentMessage()

    # A new change while it is stuck in what no longer serves: it does not wait for that node to end.
    w._change_text("slow", "seconds", "30")
    until(lambda: in_slow(calc))
    time.sleep(w.STUCK_SECONDS + 0.1)
    start = time.monotonic()
    w._change_text("slow", "seconds", "0.1"); settle()
    assert time.monotonic() - start < 5 and w.project.graph.nodes["after"]._value.values.ravel()[0] == 1.1, "it waited"
    # The new process did not compute «n» again: the window gave it its result.
    w._change_text("n", "value", "2"); settle()
    assert w.project.graph.nodes["after"]._value.values.ravel()[0] == 2.1

    # The process ends by itself in the middle of a node (a library that fails, the memory of the computer): the window
    # goes on, and the node is marked.
    w._change_text("slow", "seconds", "30")
    until(lambda: in_slow(calc))
    calc.current.process.kill()
    until(lambda: w._in_progress is None)
    app.processEvents()
    assert w.editor.boxes["slow"].with_error
    assert "closed unexpectedly in «slow»" in w.statusBar().currentMessage(), w.statusBar().currentMessage()
    w._change_text("slow", "seconds", "0.1"); settle()
    assert not w.editor.boxes["slow"].with_error and w.project.graph.nodes["after"]._value.values.ravel()[0] == 2.1
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
QTimer.singleShot(120000, lambda: os._exit(3))
app.exec()
'''


def test_stop_at_once_and_failures_that_do_not_close_the_window(tmp_path):
    pytest.importorskip("PySide6")
    (tmp_path / "slow_nodes.py").write_text(SLOW_NODES, encoding="utf-8")
    script = tmp_path / "window.py"
    script.write_text(SLOW_SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"), "XDG_RUNTIME_DIR": str(tmp_path),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": os.pathsep.join([str(SRC), str(tmp_path)]),
           "TENSELA_EXTRA_NODES": "slow_nodes"}
    env.pop("TENSELA_CALCULATE_HERE", None)
    result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=150)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]


def test_sending_a_big_project_does_not_make_the_window_wait(calculator):
    """The request goes through a thread of its own: a project much bigger than what the channel holds at once is
    sent without waiting for the process to read it."""
    import time
    calc, replies = calculator
    graph = Graph()
    graph.node("Number", "many", value=";".join(str(i) for i in range(200_000)))      # about 1.3 MB of inputs
    start = time.monotonic()
    calc.send(C.request(graph, 1, 1, None, "en"))
    assert time.monotonic() - start < 0.2
    assert replies.get(timeout=60)["turn"] == 1


# --- Package 3: inside the groups, «Find the best…» and exporting, through the same way --------------------------

CASE = Path(__file__).parent / "data" / "caso_01.json"


def _nested_groups():
    """The case with a group inside another, as the window would have it: the project and the two insides."""
    from tensela.groups import group_in_project, inner
    from tensela.project_file import from__text, to_text
    p = open_(CASE)
    small = group_in_project(p, ['maximum distance', 'angles'], "scale angles")
    big = group_in_project(p, ['distances', small.name], "rotation")
    return from__text(to_text(p)), big.name, inner


def test_inside_the_groups_entered_is_computed_apart(calculator):
    import numpy as np
    calc, replies = calculator
    here, big, inner = _nested_groups()
    outer, _ = inner(here.graph, big)                       # computed here, to compare
    small = next(n for n, x in outer.nodes.items() if x.kind.name == "scale angles")
    deeper, _ = inner(outer, small, ["rotation"])
    expected = {n: np.array(deeper.value(n).values) for n in deeper.nodes}
    window, _, _ = _nested_groups()                         # the window: nothing computed yet
    one, _ = inner(window.graph, big)
    two, _ = inner(one, small, ["rotation"])
    for g in (window.graph, one, two):
        for node in g.nodes.values():
            node._value = None
    from tensela import language                          # (the language of the window: the names inside)
    calc.send(C.request(window.graph, 1, 1, None, language.LANGUAGE, [(big, one), (small, two)]))
    reply = replies.get(timeout=60)
    first, second = reply["inside"]
    assert first["node"] == big and second["node"] == small and not first["errors"] and not second["errors"]
    assert sorted(second["values"]) == sorted(two.nodes)
    for name, value in second["values"].items():
        assert np.allclose(np.array(value.values), expected[name]), name
    # Again, with the results in the window: nothing computed again inside either.
    for level, g in ((first, one), (second, two)):
        for name, value in level["values"].items():
            g.nodes[name]._value = value
    for name, value in reply["values"].items():
        window.graph.nodes[name]._value = value
    calc.send(C.request(window.graph, 2, 1, None, language.LANGUAGE, [(big, one), (small, two)]))
    reply = replies.get(timeout=60)
    assert reply["computed"] == [] and [level["computed"] for level in reply["inside"]] == [[], []]


SAME_WAY_SCRIPT = r'''
import os, sys, time
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
import slow_nodes  # noqa: F401
from tensela.graph import Graph
from tensela.project_file import Control, Project
from tensela.ui import window
from tensela.calculator import _Worker
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()

def settle(seconds=60):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        w.wait_computation(0.05); app.processEvents()
        if w._in_progress is None:
            return

def until(condition, seconds=30):
    limit = time.monotonic() + seconds
    while not condition() and time.monotonic() < limit:
        app.processEvents(); time.sleep(0.01)
    assert condition()

def fins():
    return np.array(w.project.graph.nodes["sun fins"]._value.values)

def run():
    # Inside the groups: computed apart (the window computes none of their nodes), also one group inside another.
    w.open_(sys.argv[1]); settle()
    before = fins()
    big = next(n for n, x in w.project.graph.nodes.items() if x.kind.name == "rotation")
    w.enter_group(big); settle()
    assert all(x._value is not None and x.evaluations == 0 for x in w._canvas.nodes.values())
    small = next(n for n, x in w._canvas.nodes.items() if x.kind.name == "scale angles")
    w.enter_group(small); settle()
    inside = w._canvas
    assert all(x._value is not None and x.evaluations == 0 for x in inside.nodes.values())
    remap = next(n for n, x in inside.nodes.items() if x.kind.name == "Remap")
    inside.change(remap, "to_max", 45.0); w._after_edit(); settle()
    assert inside.nodes[remap]._value is not None and inside.nodes[remap].evaluations == 0
    assert not np.allclose(fins(), before)
    assert not any(w.editor.boxes[n].with_error for n in inside.nodes if n in w.editor.boxes)
    w.quit_group(); settle(); w.quit_group(); settle()

    # «Find the best…»: in a process of its own.
    g = Graph()
    g.node("Number", "n", value=1.0)
    g.node("Wait", "slow", seconds=0.0)
    g.node("Formula", "f", formula="(a - 3) * (a - 3) + b * 0", a=g.nodes["n"], b=g.nodes["slow"])
    w._load(Project(g, ["f"], controls=[Control("n", "value", 0, 10, 1), Control("slow", "seconds", 0, 30, 30)]),
            None)                                           # («f», seen: it is what is exported)
    settle()
    w.open_search("f"); app.processEvents()
    d = w._search_dialog
    for k, (c, i, name, value) in enumerate(d._pieces):
        d.sliders.item(k).setCheckState(Qt.CheckState.Checked if c.node == "n" else Qt.CheckState.Unchecked)
    d.start.click()
    assert isinstance(d._thread, _Worker) and d._thread.process.pid != os.getpid()
    until(lambda: d._thread is None)
    settle()
    assert w.project.graph.nodes["n"].inputs["value"] == 3 and "Found" in d.status.text(), d.status.text()
    # «Stop» in the middle of a long node: at once, with the best found.
    for k in range(d.sliders.count()):
        d.sliders.item(k).setCheckState(Qt.CheckState.Checked)
    d.start.click()
    searcher = d._thread
    time.sleep(2.0); app.processEvents()
    assert d._thread is searcher, d.status.text()            # (stuck in «slow»: 30 seconds)
    start = time.monotonic(); d.start.click()
    until(lambda: d._thread is None, 5)
    assert time.monotonic() - start < 2.5 and "Stopped" in d.status.text(), d.status.text()
    until(lambda: searcher.process.poll() is not None, 5)
    settle()
    assert w.project.graph.nodes["n"].inputs["value"] == 3
    d.close()

    # Exporting while it computes: it waits for the calculation (none of it here), and the slow part goes aside.
    w._change_text("slow", "seconds", "1.5")
    assert w._in_progress is not None
    values = w._export_values(["f"])
    assert values is not None and values[0].values.ravel()[0] == 0
    assert slow_nodes.CALLS == []                          # the window computed none of it
    assert w._aside("…", lambda: time.sleep(0.3) or 7) == 7
    try:
        w._aside("…", lambda: 1 / 0)
        raise AssertionError("the error is lost")
    except ZeroDivisionError:
        pass
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
QTimer.singleShot(150000, lambda: os._exit(3))
app.exec()
'''


def test_groups_the_search_and_exports_go_through_the_process(tmp_path):
    pytest.importorskip("PySide6")
    from tensela.project_file import to_text
    project, _, _ = _nested_groups()
    case = tmp_path / "nested.tela"
    case.write_text(to_text(project), encoding="utf-8")
    (tmp_path / "slow_nodes.py").write_text(SLOW_NODES, encoding="utf-8")
    script = tmp_path / "window.py"
    script.write_text(SAME_WAY_SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"), "XDG_RUNTIME_DIR": str(tmp_path),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": os.pathsep.join([str(SRC), str(tmp_path)]),
           "TENSELA_EXTRA_NODES": "slow_nodes"}
    env.pop("TENSELA_CALCULATE_HERE", None)
    result = subprocess.run([sys.executable, str(script), str(case)], env=env, capture_output=True, text=True,
                            timeout=180)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]


# --- Package 4: only what is seen ----------------------------------------------------------------------------------

SUN = SRC / "tensela" / "templates" / "sun-study.tela"


def test_only_the_nodes_asked_for_and_what_feeds_them():
    graph = open_(str(SUN)).graph
    assert graph.compute_all(["shadows"]) == {}
    computed = {name for name, node in graph.nodes.items() if node._value is not None}
    assert computed == {"building", "sun", "shadows"}


SEEN_SCRIPT = r'''
import os, sys, time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()
HIDDEN = {"faces", "panels", "sun hours"}

def settle():
    for _ in range(6):
        w.wait_computation(); app.processEvents(); time.sleep(0.02)

def computed():
    return {n for n, x in w.project.graph.nodes.items() if x._value is not None}

def rows():
    return {name: (shape, state) for name, kind, category, what, shape, state in w.table._rows}

def wire_from(name):
    return next(c for c in w.editor.cables if c.output.box.node.name == name)

def run():
    w.open_(sys.argv[1]); settle()
    assert computed() == {"building", "sun", "shadows"}, computed()
    assert "3 not calculated" in w.statusBar().currentMessage(), w.statusBar().currentMessage()
    assert all(rows()[n] == ("not calculated", "waiting") for n in HIDDEN), rows()
    assert wire_from("faces").label.text() == "not calculated" and wire_from("faces")._waiting
    # Looked at (a click on its row in Data): calculated, with what feeds it.
    w.table.chosen.emit("sun hours"); settle()
    assert HIDDEN <= computed() and w.panel_node._shown == "sun hours"
    assert wire_from("faces").label.text() != "not calculated" and rows()["sun hours"][1] != "waiting"
    # Another chosen and a change: it waits again.
    w.editor.select("building"); settle()
    w._change_text("building", "height", "40"); settle()
    assert not (HIDDEN & computed()), computed()
    # An open preview counts as seen.
    w.editor.toggle_thumbnail(["sun hours"], True); settle()
    assert HIDDEN <= computed()
    w._change_text("building", "height", "35"); settle()
    assert HIDDEN <= computed()
    w.editor.toggle_thumbnail(["sun hours"], False); settle()
    w._change_text("building", "height", "30"); settle()
    assert not (HIDDEN & computed())
    # Package 5: «Calculate the rest», once; an error in what is not seen shows then, and the next change, it waits.
    assert w.button_rest.isVisible() and w.button_rest.text() == "Calculate the rest (3)", w.button_rest.text()
    assert w.panel_node.waiting == 3
    w._change_text("panels", "rows", "abc"); settle()
    assert w.editor.boxes["panels"].with_error               # (the node edited is the one looked at: calculated)
    w.editor.select("building"); w._change_text("building", "height", "31"); settle()
    assert not w.editor.boxes["panels"].with_error           # not seen now: not calculated, nothing known
    w.button_rest.click(); settle()
    assert w.editor.boxes["panels"].with_error and w.warning.isVisible() and not w.button_rest.isVisible()
    w._change_text("panels", "rows", "15"); settle()
    # What the change did not touch stays calculated («faces»); «panels» is the one looked at; after it, it waits.
    assert {"faces", "panels"} <= computed() and "sun hours" not in computed()
    w.editor.select("building"); w._change_text("building", "height", "33"); settle()
    assert not (HIDDEN & computed()) and w.button_rest.isVisible() and not w.editor.boxes["panels"].with_error
    # «Calculate: everything», as before.
    w.apply_preference("compute/what", "all"); settle()
    assert computed() == set(w.project.graph.nodes)
    w.apply_preference("compute/what", "seen")
    w._change_text("building", "height", "32"); settle()
    assert not (HIDDEN & computed())
    # «Find the best…» open: everything (it lists every number).
    w.open_search(); settle()
    assert computed() == set(w.project.graph.nodes)
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
QTimer.singleShot(120000, lambda: os._exit(3))
app.exec()
'''


@pytest.mark.parametrize("apart", [True, False], ids=["apart", "here"])
def test_only_what_is_seen_is_calculated(tmp_path, apart):
    pytest.importorskip("PySide6")
    script = tmp_path / "window.py"
    script.write_text(SEEN_SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"), "XDG_RUNTIME_DIR": str(tmp_path),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(SRC)}
    env.pop("TENSELA_CALCULATE_HERE", None)
    if not apart:
        env["TENSELA_CALCULATE_HERE"] = "1"
    result = subprocess.run([sys.executable, str(script), str(SUN)], env=env, capture_output=True, text=True,
                            timeout=150)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
