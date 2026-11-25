"""Edit mesh: a cage shaped by hand, keeping only how much each vertex moved."""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.mesh_tools import edit_mesh, editable_mesh
from tensela.project_file import open_

EXAMPLES = Path(__file__).resolve().parent / "data"


def _box():
    g = Graph()
    g.node("Box", "b", width=2.0, depth=2.0, height=2.0)
    return g.value("b")


def test_only_the_moved_vertices_move():
    box = _box()
    base = np.asarray(editable_mesh(box).values)
    edited = edit_mesh(box, [[0, 0.0, 0.0, 1.0], [5, 0.5, 0.0, 0.0]])
    p = np.asarray(edited.values)
    assert np.allclose(p[0], base[0] + [0, 0, 1]) and np.allclose(p[5], base[5] + [0.5, 0, 0])
    assert np.allclose(np.delete(p, [0, 5], axis=0), np.delete(base, [0, 5], axis=0))
    assert edited.kind.faces == editable_mesh(box).kind.faces          # the same faces: only the geometry changes


def test_the_numbers_are_the_same_for_the_same_mesh():
    assert np.allclose(editable_mesh(_box()).values, editable_mesh(_box()).values)


def test_a_vertex_the_mesh_does_not_have_is_left_aside():
    assert np.allclose(edit_mesh(_box(), [[99, 1.0, 1.0, 1.0]]).values, editable_mesh(_box()).values)


def test_the_edits_follow_the_mesh_when_it_changes():
    g = Graph()
    g.node("Number", "size", value=2.0)
    g.node("Box", "b", width=g.nodes["size"], depth=2.0, height=2.0)
    g.node("Edit mesh", "e", mesh=g.nodes["b"], moves=[[0, 0.0, 0.0, 1.0]])
    first = np.asarray(g.value("e").values)[0]
    g.change("size", "value", 4.0)
    base = np.asarray(editable_mesh(g.value("b")).values)[0]
    assert np.allclose(np.asarray(g.value("e").values)[0], base + [0, 0, 1]) and not np.allclose(first, base + [0, 0, 1])


def test_mistakes_say_what_happened():
    with pytest.raises(ShapeError):
        edit_mesh(None, [])
    with pytest.raises(ShapeError):
        edit_mesh(_box(), [["a", "b"]])


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
import numpy as np
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    w.editor.select("cage by hand"); app.processEvents()
    w.draw("cage by hand"); app.processEvents()
    d = w.viewer.drawing
    assert d.active and d.edges is not None and d.tool == "select"
    d.put_tool("add"); d.put_tool("delete")
    assert d.tool == "select"                                        # a mesh: only choose and move
    n = len(d.points)
    node = w.project.graph.nodes["cage by hand"]
    before = len(node.inputs["moves"])
    top = int(np.argmax(d.points[:, 2] - d.points[:, 0]))
    d.points[top] = d.points[top] + [0, 0, 0.2]
    d._warn(True); w.wait_computation(); app.processEvents()
    assert len(node.inputs["moves"]) == before + 1
    assert any(m[0] == top and abs(m[3] - 0.2) < 1e-9 for m in node.inputs["moves"])
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    d.eventFilter(None, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier))
    assert len(d.points) == n                                        # Del does not remove a vertex
    w.finish_drawing(); app.processEvents()
    assert not d.active and w._drawing is None
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


