"""A group that repeats itself: what comes out goes back in."""

from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import Data, ShapeError, stack
from tensela.graph import Graph, NodeError
from tensela.groups import group, rename_input
from tensela.project_file import from__text, open_, to_text


def _doubling():
    """x → 2x + more, as a group «double» with the inputs «x» and «more»."""
    g = Graph()
    g.node("Number", "x", value=1.0)
    g.node("Number", "more", value=0.0)
    g.node("Formula", "twice", formula="a * 2", a=g.nodes["x"])
    g.node("Formula", "plus", formula="a + b", a=g.nodes["twice"], b=g.nodes["more"])
    _, node = group(g, ["twice", "plus"], "double")
    return g, node


def test_once_it_is_the_group_as_always():
    g, node = _doubling()
    assert float(g.value(node).values) == 2.0 and g.value(node).levels == ()


def test_repeated_the_result_goes_back_in():
    g, node = _doubling()
    g.change(node, "repeat", 5)
    assert float(g.value(node).values) == 32.0
    g.change(node, "repeat", 0)                              # no times: what came in
    assert float(g.value(node).values) == 1.0


def test_every_step_with_the_start_first():
    g, node = _doubling()
    g.change(node, "repeat", 4)
    g.change(node, "keep", "every step")
    v = g.value(node)
    assert v.levels == ("step",) and v.values.tolist() == [1, 2, 4, 8, 16]
    g.change(node, "step_level", "round")
    assert g.value(node).levels == ("round",)


def test_the_other_inputs_stay_as_they_are_and_the_input_can_be_chosen():
    g, node = _doubling()
    g.change("more", "value", 1.0)
    g.change(node, "repeat", 3)
    assert float(g.value(node).values) == 15.0               # x: 1 → 3 → 7 → 15
    g.change(node, "back_into", "more")                      # now «more» is what goes round: 1 → 3 → 5 → 7
    assert float(g.value(node).values) == 7.0
    g.change(node, "back_into", "nothing")
    with pytest.raises(NodeError):
        g.value(node)


def test_an_input_called_step_gets_the_number_of_each_step():
    g = Graph()
    g.node("Number", "total", value=0.0)
    g.node("Number", "step", value=99.0)
    g.node("Formula", "with the step", formula="a + b", a=g.nodes["total"], b=g.nodes["step"])
    g.node("Formula", "same", formula="a", a=g.nodes["with the step"])
    _, node = group(g, ["with the step", "same"], "add the step")
    assert float(g.value(node).values) == 99.0               # once: what is connected
    g.change(node, "repeat", 4)
    g.change(node, "back_into", "total")
    assert float(g.value(node).values) == 0 + 1 + 2 + 3


def test_too_many_times_and_a_step_that_cannot_go_back_in_are_said():
    g, node = _doubling()
    g.change(node, "repeat", 5000)
    with pytest.raises(NodeError, match="1000"):
        g.value(node)
    g2 = Graph()
    g2.node("Rectangle", "r", width=4.0, height=2.0)
    g2.node("Grid", "cells", rectangle=g2.nodes["r"], columns=2, rows=2)
    g2.node("Centre", "centres", geometry=g2.nodes["cells"])
    _, node2 = group(g2, ["cells", "centres"], "centres of the cells")
    g2.change(node2, "repeat", 2)                            # points do not go back in where a rectangle goes
    with pytest.raises(NodeError, match="2"):
        g2.value(node2)


def test_steps_of_different_sizes_stack_with_a_variable_level():
    a = Data(np.zeros((1, 2, 3)), ("segment",), kind=G.CURVE)
    b = Data(np.ones((4, 2, 3)), ("segment",), kind=G.CURVE)
    s = stack([a, b], "step")
    assert s.levels == ("step", "segment") and s.count == 5
    assert s.variables["segment"].values.tolist() == [1, 4]
    short = Data(np.zeros((2, 3)), (), kind=G.CURVE)
    long = Data(np.ones((5, 3)), (), kind=G.CURVE)
    s = stack([short, long], "step")                          # a curve with fewer points: its last one, repeated
    assert s.values.shape == (2, 5, 3) and np.allclose(s.values[0, 2:], 0)
    with pytest.raises(ShapeError):
        stack([a, Data(1.0)], "step")
    with pytest.raises(ShapeError):
        stack([a, a], "segment")


def test_it_is_saved_and_opened_and_follows_a_renamed_input():
    g, node = _doubling()
    g.change(node, "repeat", 3)
    g.change(node, "back_into", "x")
    g.change(node, "keep", "every step")
    from tensela.project_file import Project
    q = from__text(to_text(Project(g, [])))
    n = q.graph.nodes[node.name]
    assert n.inputs["repeat"] == 3 and q.graph.value(n).values.tolist() == [1, 2, 4, 8]
    rename_input(q.graph, "double", "x", "amount")
    assert n.inputs["back_into"] == "amount"


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    g = w.project.graph
    w.editor.select("1 lines"); app.processEvents()
    w.enter_group("1 lines"); app.processEvents()
    assert "middle third" in w._canvas.nodes                   # inside: the canvas is the group's graph
    w._canvas.change("middle third", "to", 0.5)
    w._apply_inside(); app.processEvents()
    w.quit_group(); app.processEvents(); w.wait_computation(); app.processEvents()
    n = g.nodes["1 lines"]
    assert n.inputs["back_into"] == "line 0" and n.inputs["keep"] == "every step"   # it still repeats
    v = g.value("1 lines")
    assert len(v.values) == 4 and abs(float(v.values[1, -1, 0]) - 13.5) < 1e-6      # with what was edited inside
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


def test_two_nodes_seen_one_after_the_other_group_into_the_last_one():
    """Prueba 70: new nodes turn their eye on by themselves; Scale and Rotate, both seen, still make a group (the
    step in between is not a second result), and it repeats into a spiral."""
    g = Graph()
    g.node("Rectangle", "rect", width=10.0, height=10.0)
    g.node("Scale", "scale", geometry=g.nodes["rect"], factor=0.8)
    g.node("Rotate", "turn", geometry=g.nodes["scale"], degrees=10.0)
    export = ["rect", "scale", "turn"]
    definition, node = group(g, ["scale", "turn"], "shrink and turn", export=export)
    assert definition.output == "turn" and export == ["rect", node.name]
    g.change(node, "repeat", 12)
    g.change(node, "keep", "every step")
    spiral = g.value(node)
    assert spiral.levels == ("step",) and spiral.sizes["step"] == 13


def test_two_results_used_outside_give_a_group_with_two_results():
    g = Graph()
    g.node("Number", "x", value=1.0)
    g.node("Formula", "twice", formula="a * 2", a=g.nodes["x"])
    g.node("Formula", "plus", formula="a + 1", a=g.nodes["twice"])
    g.node("Formula", "uses twice", formula="a", a=g.nodes["twice"])
    g.node("Formula", "uses plus", formula="a", a=g.nodes["plus"])
    group(g, ["twice", "plus"], "both")
    assert float(g.value("uses twice").values) == 2.0 and float(g.value("uses plus").values) == 3.0
    assert g.nodes["plus"].kind.name == "Group result"
