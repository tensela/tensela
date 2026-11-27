"""The helper that runs the code of the Code nodes apart from Tensela: watched and with limits (the second
layer; the first one is the check, test_code_node.py)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.code_worker import Helper, helper, pack, unpack
from tensela.data import Data, ShapeError
from tensela.graph import Graph, NodeError
from tensela.meshes import kind_mesh

SOURCE = Path(__file__).resolve().parent.parent / "src"
HOSTILE = Path(__file__).resolve().parent / "helpers" / "enclosed_hostile.py"


# --- Data goes and comes back as numbers, never as code ---------------------------------------------------------

def _same(a: Data, b: Data) -> bool:
    return (a.levels == b.levels and a.kind == b.kind and np.array_equal(a.values, b.values)
            and a.values.dtype == b.values.dtype and set(a.variables) == set(b.variables)
            and all(np.array_equal(a.variables[n].values, b.variables[n].values) for n in a.variables)
            and (a.holes is None) == (b.holes is None) and (a.holes is None or np.array_equal(a.holes, b.holes)))


def test_data_survives_the_trip():
    uneven = Data.from_lists([[1.0, 2.0, 3.0], [4.0]], ("row", "column"))
    with_holes = Data(np.arange(4.0), ("n",), holes=[False, True, False, False])
    for data in (Data(3.5), Data(np.arange(6).reshape(2, 3), ("a", "b")), uneven, with_holes,
                 Data(np.zeros((4, 3)), ("p",), kind=G.POINT), Data(np.ones((5, 3)), (), kind=G.CLOSED_CURVE),
                 Data(np.zeros((3, 3)), (), kind=kind_mesh([(0, 1, 2)])), Data(np.zeros((2, 8, 3)), ("b",), kind=G.BOX)):
        back = unpack(*pack(data))
        assert _same(data, back), data.kind
    assert unpack(*pack(Data(2.0))).values.shape == ()          # a single number stays a single number
    assert unpack(*pack(Data(np.zeros(3), (), kind=G.POINT))).kind is G.POINT   # Tensela's own kinds, themselves
    assert pack(None) == (None, b"") and unpack(None, b"") is None


@pytest.mark.parametrize("head", [
    {"levels": [], "shape": [10 ** 9], "dtype": "<f8"},                       # more numbers than came
    {"levels": [], "shape": [2], "dtype": "O"},                               # objects are not numbers
    {"levels": [], "shape": [-1], "dtype": "<f8"},
    {"levels": ["a", "b"], "shape": [2], "dtype": "<f8"},                     # more levels than dimensions
    {"levels": [], "shape": [3], "dtype": "<f8", "kind": {"name": "x"}},      # a kind made up by halves
    {"levels": [], "shape": "nonsense", "dtype": "<f8"},
    {"shape": [2], "dtype": "<f8"},
])
def test_a_made_up_answer_is_an_error_never_data(head):
    with pytest.raises((ValueError, TypeError, KeyError, ShapeError)):
        unpack(head, np.zeros(2).tobytes())


# --- The helper ----------------------------------------------------------------------------------------------

def test_the_node_runs_in_the_helper_closed_in():
    g = Graph()
    g.node("Number", "n", value=5.0)
    g.node("Code", "c", code="result = [point(i, i * a) for i in range(int(a))]", a=g.nodes["n"])
    assert g.value("c").values.shape == (5, 3) and g.value("c").kind is G.POINT
    h = helper()
    assert h.enclosed["watcher"]                                # the watcher of Python, always
    if sys.platform.startswith("linux"):
        assert h.enclosed["memory"]                             # the limits, where the system has them
    t = time.time()
    for k in range(20):                                          # and it stays for the next ones: quick
        g.change("n", "value", float(k + 1))
        g.value("c")
    assert time.time() - t < 2


def test_too_much_memory_is_said_and_the_helper_goes_on():
    if not sys.platform.startswith("linux"):
        pytest.skip("the memory limit is the system's")
    h = helper()
    with pytest.raises(ShapeError):
        h.run("result = [0] * 10 ** 10", {})
    with pytest.raises(ShapeError):
        h.run("x = 'a' * 10 ** 10\nresult = 1", {})
    assert float(h.run("result = 1 + 1", {}).values) == 2


def test_something_python_cannot_interrupt_is_closed_and_another_helper_starts():
    h = Helper()
    try:
        assert float(h.run("result = 2", {}).values) == 2
        first = h._process.pid
        t = time.time()
        with pytest.raises(ShapeError, match="0.5"):
            h.run("result = 2 ** (10 ** 9) % 7", {}, seconds=0.5)      # one single operation, for minutes
        assert time.time() - t < 8
        assert float(h.run("result = 3", {}).values) == 3                # a new helper, without asking
        assert h._process.pid != first
    finally:
        h.close()


def test_a_helper_that_dies_is_said_kindly_and_starts_again():
    h = Helper()
    try:
        h.run("result = 1", {})
        h._process.kill()
        h._process.wait(5)
        assert float(h.run("result = 4", {}).values) == 4                # it was gone: another one, and the answer
    finally:
        h.close()


def test_the_check_still_goes_first_and_the_messages_are_the_same():
    g = Graph()
    g.node("Code", "c", code="import socket\nresult = 1")
    with pytest.raises(NodeError, match="socket"):
        g.value("c")
    g.change("c", "code", "x = [1]\nresult = x[3]")
    with pytest.raises(NodeError, match="2"):
        g.value("c")


def test_closed_in_nothing_leaves_even_with_all_of_python_at_hand(tmp_path):
    """As if some code had got past the check: inside the helper, with every module of Python reachable, each
    attempt to read, write, connect, start a program or reach the interpreter is stopped."""
    victim = tmp_path / "victim.txt"
    victim.write_text("still here")
    env = {"PATH": os.environ.get("PATH", ""), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    done = subprocess.run([sys.executable, "-I", str(HOSTILE), str(SOURCE), str(victim)], env=env,
                          capture_output=True, text=True, timeout=120)
    report = json.loads(done.stdout)
    assert report["put"]["watcher"] and report["still"] == []
    results = report["results"]
    assert results.pop("plain computing") == "RAN"                   # computing is all that is left
    assert len(results) >= 25
    for what, happened in results.items():
        if sys.platform == "win32" and happened.startswith(("AttributeError: module 'os' has no attribute",
                                                            "ModuleNotFoundError: No module named 'resource'")):
            continue                                                 # (os.fork, resource and the like: not on Windows)
        assert happened != "RAN" and ("_Outside" in happened or "MemoryError" in happened), (what, happened)
    assert victim.read_text() == "still here" and sorted(p.name for p in tmp_path.iterdir()) == ["victim.txt"]
