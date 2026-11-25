"""Victor's notes on tests 78 to 86: what failed or confused while trying the fabrication chapter."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tensela import fabrication as F  # noqa: E402
from tensela import language  # noqa: E402
from tensela.graph import Graph  # noqa: E402
from tensela.nodes import visible_input  # noqa: E402
from tensela.values import ShapeError  # noqa: E402

app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def test_a_connected_choice_does_not_hide_the_inputs_nor_cut_their_wires():
    g = Graph()
    g.node("Box", "box")
    g.node("Vertices", "corners", geometry=g.nodes["box"])
    g.node("Number", "up", value=0.05)
    g.node("Vector", "v", z=g.nodes["up"])
    g.change("v", "mode", g.nodes["corners"])        # wired by mistake into «mode» (test 79)
    shown = [e.name for e in g.nodes["v"].kind.inputs if visible_input(g.nodes["v"], e)]
    assert shown[:4] == ["mode", "x", "y", "z"]       # as if «mode» were its default; «z», wired, still there
    g.change("v", "mode", "axis")
    shown = [e.name for e in g.nodes["v"].kind.inputs if visible_input(g.nodes["v"], e)]
    assert "z" in shown and "x" not in shown        # another mode: only the wired one stays


def test_slots_and_lay_flat_take_the_boards_of_sections():
    g = Graph()
    g.node("Sphere", "ball", radius=0.1)
    g.node("Sections", "across", shape=g.nodes["ball"], gap=0.02, show="boards")
    g.node("Sections", "along", shape=g.nodes["ball"], gap=0.02, cuts="y", show="boards")
    g.node("Slots", "slotted", first=g.nodes["across"], second=g.nodes["along"], show="boards")
    assert g.value("slotted").kind is not None       # test 82: the boards shown, connected as they are
    g.node("Lay flat", "laid", pieces=g.nodes["across"])
    assert g.value("laid").layout.count == len(F._groups(g.value("across").outlines))


def test_numbers_and_sheets_follow_the_lay_flat():
    g = Graph()
    g.node("Rectangle", "strip", width=0.2, height=0.03)
    g.node("Series", "k", count=12, level="strip")
    g.node("Formula", "y", formula="a * 0.04", a=g.nodes["k"])
    g.node("Vector", "step", y=g.nodes["y"], z=0.0)
    g.node("Move", "strips", geometry=g.nodes["strip"], vector=g.nodes["step"])
    g.node("Lay flat", "pieces", pieces=g.nodes["strips"])
    g.node("Numbers and sheets", "numbers", laid=g.nodes["pieces"])
    g.node("Numbers and sheets", "sheets", laid=g.nodes["pieces"], show="sheets")
    assert len(g.value("sheets").values) == 1
    g.change("pieces", "width", 0.25)                 # only on the Lay flat (tests 81 and 86)
    g.change("pieces", "height", 0.12)
    sheets = g.value("sheets")
    assert len(sheets.values) == len(g.value("pieces").layout.boxes) > 1
    pieces = [(o[:, :2].min(axis=0), o[:, :2].max(axis=0)) for _, (o, *_) in F._groups(g.value("pieces"))]
    for stroke in g.value("numbers").values:         # every number inside a piece where it is now
        p = stroke[0, :2]
        assert any((low <= p).all() and (p <= high).all() for low, high in pieces)
    assert g.value("numbers").colour and g.value("pieces").colour and g.value("sheets").opacity
    with pytest.raises(ShapeError, match="Lay flat"):
        F.numbers_and_sheets(g.value("strips"))


def test_an_unrolled_net_lays_flat_as_its_outline():
    g = Graph()
    g.node("Box", "box", width=0.1, depth=0.1, height=0.1)
    g.node("Unroll", "net", geometry=g.nodes["box"])     # «unrolled», as it comes: a flat mesh (test 81)
    g.node("Lay flat", "laid", pieces=g.nodes["net"])
    laid = g.value("laid")
    assert laid.layout.count == 1
    (_, (outline,)), = F._groups(laid)
    assert abs(F._area(outline[:, :2])) == pytest.approx(6 * 0.01, rel=1e-6)   # the six faces in one piece
    g.node("Lay flat", "faces", pieces=g.nodes["box"])
    assert g.value("faces").layout.count == 6            # a box: its six faces
    g.node("Sphere", "ball")
    g.node("Lay flat", "round", pieces=g.nodes["ball"])
    with pytest.raises(Exception, match="Unroll"):
        g.value("round")


def test_the_problems_come_red_and_the_printer_faint():
    g = Graph()
    g.node("Rectangle", "plate", width=0.05, height=0.05)
    g.node("Print check", "check", geometry=g.nodes["plate"])
    assert g.value("check").colour == "#e0302a" and len(g.value("check").values) == 4    # its four open edges
    g.change("check", "show", "printer")
    assert g.value("check").opacity < 0.5


def test_a_failing_geometry_node_keeps_its_eye():
    from tensela.ui.editor import BoxNode
    g = Graph()
    g.node("Slots", "slotted")                       # nothing connected: it fails
    with pytest.raises(Exception):
        g.value("slotted")
    assert BoxNode(g.nodes["slotted"]).shows_eye()
    g.node("Number", "n", value=1.0)
    g.value("n")
    assert not BoxNode(g.nodes["n"]).shows_eye()


EYES = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    p = w.project
    before = list(p.export)
    assert len(before) > 2
    w.editor.select(before[1]); app.processEvents()
    w._action_items["see_only"].trigger(); w.wait_computation(); app.processEvents()
    assert p.export == [before[1]], p.export                 # only that one
    w._action_items["hide_all"].trigger(); w.wait_computation(); app.processEvents()
    assert p.export == []
    w.undo(); w.wait_computation(); app.processEvents()      # one change, undone at once
    p = w.project
    assert p.export == [before[1]], p.export
    w._action_items["see_all"].trigger(); w.wait_computation(); app.processEvents()
    assert set(before) <= set(p.export) and "board" not in p.export   # every geometry, not the numbers
    w.editor.select(before[0]); app.processEvents()
    w._action_items["hide_selected"].trigger(); w.wait_computation(); app.processEvents()
    assert before[0] not in p.export
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    w._menu_canvas(menu, before[1])                          # right-click on a node
    texts = [a.text() for a in menu.actions()]
    from tensela.language import tr
    assert tr("Show only this one") in texts and w._action_items["see_all"] in menu.actions(), texts
    menu = QMenu()
    w._menu_canvas(menu, None)                               # and on the background
    assert w._action_items["hide_all"] in menu.actions()
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


