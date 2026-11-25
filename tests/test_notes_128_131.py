"""Victor's notes on the tests 128 to 131: tooltips in short lines, the panels' «Move to» in one language, the rounded
letter that keeps its shape, the labels in an installed font, and what can be written in the text of a label."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tensela import language
from tensela.data import Data
from tensela.geometry import POINT


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def test_a_long_tooltip_comes_in_short_lines():
    pytest.importorskip("PySide6")
    from tensela.ui.tooltips import TIP_WIDTH, needs_wrapping, wrapped
    help_ = ("codes on the panels: a “Text” node. Writes a label on each element: the number of a panel, the letter "
             "of a brick type, an area.\n“text” comes out of the port on the right.")
    lines = wrapped(help_).split("\n")
    assert all(len(line) <= TIP_WIDTH for line in lines) and len(lines) >= 4
    assert lines[-1] == "“text” comes out of the port on the right."      # its own line breaks, kept
    assert " ".join(wrapped(help_).split()) == " ".join(help_.split())     # not a word lost
    assert not needs_wrapping("Close") and needs_wrapping(help_)
    assert not needs_wrapping("<b>rich</b> " + "x " * 60)                   # rich text: Qt wraps it
    path = "/home/someone/projects/a/very/long/folder/without/spaces/in/it/project.json"
    assert wrapped(path) == path                                            # a long word stays whole


def test_the_panel_sides_are_written_in_the_language_of_the_interface():
    pytest.importorskip("PySide6")
    from tensela.translations import es
    from tensela.ui.widgets import DockablePanel
    for name, _ in DockablePanel.SIDES:
        assert name in es.TEXTS, name                                       # «Below», not «Abajo» in English


def test_the_rounded_letter_keeps_its_straight_parts():
    from tensela.strokes import styled, text_strokes
    for letter in "ELZ257":
        plain = text_strokes(letter, 1.0)
        rounded = styled(plain, 1.0, 'rounded')
        for p, r in zip(plain, rounded):
            assert np.allclose(p[0], r[0]) and np.allclose(p[-1], r[-1]), letter    # its ends, where they were
            # every point of the rounded one stays close to the plain stroke (only the corners move, a little)
            seg_a, seg_b = p[:-1], p[1:]
            d = seg_b - seg_a
            t = np.clip(((r[:, None] - seg_a) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-12), 0, 1)
            gap = np.linalg.norm(r[:, None] - (seg_a + t[..., None] * d), axis=-1).min(axis=1)
            assert gap.max() < 0.06, (letter, gap.max())


def _points():
    return Data(np.array([[0.0, 0, 0], [1.0, 0, 0]]), ("p",), "p", kind=POINT)


def test_the_labels_in_an_installed_font():
    pytest.importorskip("fontTools")
    from tensela import fonts, labels
    if not fonts.families():
        pytest.skip("no fonts on this computer")
    single = labels.text(_points(), "Año", height=0.2)
    font = labels.text(_points(), "Año", height=0.2, letter='font')
    v = np.asarray(font.values)
    assert font.levels == single.levels == ("p", "stroke")
    assert np.allclose(v[..., 0, :], v[..., -1, :])                      # closed outlines
    assert v.shape[-3] > np.asarray(single.values).shape[-3]                # «ñ» and «o» bring their holes
    # The capitals as tall as asked, as the single-stroke letter: the «A» from the baseline to 0,2
    a_only = np.asarray(labels.text(_points(), "A", height=0.2, letter='font').values)
    assert np.ptp(a_only[0, ..., 1]) == pytest.approx(0.2, rel=0.08)
    with pytest.raises(Exception, match="no font called"):
        labels.text(_points(), "A", letter='font', font="A font nobody has")
    with pytest.raises(Exception, match="must be one of"):
        labels.text(_points(), "A", letter='gothic')


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QToolButton
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()

def chips():
    return {b.text(): b for b in w.panels["node"].findChildren(QToolButton) if b.objectName() == "menu_button"}

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    node = w.project.graph.nodes["codes on the panels"]
    w.editor.select(node.name); app.processEvents()
    assert "{n}" not in chips(), sorted(chips())          # notes of the test 133: the help says it, not buttons
    w._change_text(node.name, "lettering", "font"); w.wait_computation(); app.processEvents()
    w.editor.select("areas written"); app.processEvents(); w.editor.select(node.name); app.processEvents()
    lists = [c for c in w.panels["node"].findChildren(QComboBox) if c.count() > 20]
    assert lists, "the list of fonts"
    from PySide6.QtTest import QTest
    from tensela.fonts import families
    from tensela.ui.widgets import offered_first
    names = families()
    prefix = names[len(names) // 2][:2]
    proposal = offered_first(names, prefix)[0]
    line = lists[0].lineEdit()
    line.setFocus(); line.clear(); QTest.keyClicks(line, prefix); app.processEvents(); app.processEvents()
    assert line.text() == proposal and line.selectedText() == proposal[2:], (prefix, line.text(), proposal)
    lists[0].completer().popup().hide()                  # (the panel's own list, a window of its own: fine there)
    # On the card, a chevron where a value is chosen from a list, and the fonts offered inside the canvas
    from PySide6.QtCore import QPointF, Qt
    from tensela.ui.editor import HEIGHT_HEADER, HEIGHT_ROW
    box = w.editor.boxes[node.name]
    drops = {e.name for e in box.visible() if box._drops_down(e)}
    assert {"plane", "lettering", "font"} <= drops and "height" not in drops and "at" not in drops, drops
    row = [e.name for e in box.visible()].index("font")
    assert w.editor._edit_in_card(box, QPointF(box.width - 20, HEIGHT_HEADER + (row + 0.5) * HEIGHT_ROW))
    app.processEvents()
    field = w.editor._field_opened[0].widget()
    offered = w.editor._field_list
    list_ = offered.widget()
    assert list_.count() == len(names) and field.actions()
    assert offered.scene() is w.editor.graph_scene and offered.parentItem() is box     # in the canvas, under its card
    assert offered.pos().y() > w.editor._field_opened[0].pos().y()
    assert not [t for t in app.topLevelWidgets() if t.isVisible() and t.windowType() == Qt.WindowType.Popup]
    field.clear(); QTest.keyClicks(field, prefix); app.processEvents(); app.processEvents()
    assert field.text() == proposal and list_.item(0).text().lower().startswith(prefix.lower()), field.text()
    assert all(prefix.lower() in list_.item(i).text().lower() for i in range(list_.count()))
    QTest.keyClick(field, Qt.Key.Key_Down); app.processEvents()
    assert list_.count() < 2 or field.text() == list_.item(list_.currentRow()).text()
    # a click on a name of the list: the field stays open until it takes it, and it is saved
    item = list_.item(min(1, list_.count() - 1))
    some = item.text()
    centre = offered.mapToScene(QPointF(list_.visualItemRect(item).center()))
    where = w.editor.mapFromScene(centre)
    QTest.mouseClick(w.editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, where)
    app.processEvents(); app.processEvents(); w.wait_computation(); app.processEvents()
    assert node.inputs["font"] == some, (node.inputs["font"], some)            # chosen from the list: saved
    assert w.editor._field_opened is None and not w.editor.graph_scene.stickyFocus()
    # A long tooltip, once and in short lines, where Qt puts it (the request answered, not shown twice)
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView, QPushButton, QToolTip
    from tensela.ui.tooltips import wrapped
    long_ = "a help long enough to be written in several short lines instead of one across the screen " * 2
    button = QPushButton("tip"); button.setToolTip(long_); button.show(); app.processEvents()
    ask = QHelpEvent(QHelpEvent.Type.ToolTip, QPoint(5, 5), button.mapToGlobal(QPoint(5, 5)))
    app.sendEvent(button, ask); app.processEvents()
    assert QToolTip.isVisible() and QToolTip.text() == wrapped(long_), QToolTip.text()
    scene = QGraphicsScene(); rect = QGraphicsRectItem(0, 0, 100, 100); rect.setToolTip(long_); scene.addItem(rect)
    view = QGraphicsView(scene); view.resize(300, 300); view.show(); app.processEvents()
    inside = view.mapFromScene(QPointF(50, 50))
    app.sendEvent(view.viewport(), QHelpEvent(QHelpEvent.Type.ToolTip, inside, view.viewport().mapToGlobal(inside)))
    app.processEvents()
    assert QToolTip.text() == wrapped(long_), QToolTip.text()
    # The style button names the matcap's material (a coloured one tints every model)
    # (offscreen, painting in Matcap breaks VTK: the style change is recorded, not drawn)
    w.viewer.put_style_name = lambda key: setattr(w.viewer, "style_name", key)
    w.viewer.put_matcap = lambda key: None
    w.put_matcap("clay"); app.processEvents()
    assert "Clay" in w._button_style_name.text(), w._button_style_name.text()
    # A number box starts its text where a text field does
    from PySide6.QtWidgets import QDoubleSpinBox
    from tensela.ui import theme
    theme.apply(app)
    spin = QDoubleSpinBox(); spin.show(); app.processEvents()
    assert spin.lineEdit().textMargins().left() == theme.NUMBER_MARGIN
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


def test_a_label_in_several_lines_lined_up():
    from tensela.labels import _block, text
    for align, (low, high) in (("centre", (-0.75, 0.75)), ("left", (-1.58, -0.08)), ("right", (0.08, 1.58))):
        top = [s for s in _block("AB | ABCD", 1.0, 'plain', "", align) if s[:, 1].min() > 0]   # the first line
        xs = np.concatenate([s[:, 0] for s in top])
        assert (xs.min(), xs.max()) == pytest.approx((low, high), abs=0.01), align
    one = np.asarray(text(_points(), "AB", height=1.0).values)
    two = np.asarray(text(_points(), "AB | CD", height=1.0).values)
    assert np.ptp(two[0, ..., 1]) == pytest.approx(np.ptp(one[0, ..., 1]) + 1.6, abs=0.01)   # one line below
    assert np.mean(two[0, ..., 1]) == pytest.approx(0.0, abs=0.35)                          # the block, centred
    with pytest.raises(Exception, match="must be one of"):
        text(_points(), "A", align="justified")


def test_the_numbers_of_the_pieces_in_an_installed_font():
    pytest.importorskip("fontTools")
    from tensela import fabrication as F
    from tensela import fonts
    from tensela.geometry import CLOSED_CURVE
    if not fonts.families():
        pytest.skip("no fonts on this computer")
    rings = [[(0, 0, 0), (0.15, 0, 0), (0.15, 0, 0.06 + 0.01 * k), (0, 0, 0.06 + 0.01 * k), (0, 0, 0)]
             for k in range(6)]
    pieces = Data(np.array(rings, float), ("piece",), "p", starts={"piece": 1}, kind=CLOSED_CURVE)
    laid = F.lay_flat(pieces, 0.6, 0.4, number=0.02)
    plain = np.asarray(F.numbers_and_sheets(laid, 'numbers').values)
    font = np.asarray(F.numbers_and_sheets(laid, 'numbers', letter='font').values)
    assert np.allclose(font[:, 0], font[:, -1])                                    # closed outlines
    # in the room of the single-stroke numbers: they still fit in their pieces
    assert font[..., 0].min() >= plain[..., 0].min() - 1e-3 and font[..., 0].max() <= plain[..., 0].max() + 1e-3
    turned = np.asarray(F.numbers_and_sheets(laid, 'numbers', letter='font', reading='turned a quarter').values)
    assert np.isfinite(turned).all()


def test_a_project_saved_with_letter_opens_with_lettering():
    from tensela import project_file
    content = {"parametrico": project_file.VERSION, "nodes": {
        "p": {"type": "Point"},
        "t": {"type": "Text", "at": {"node": "p"}, "letter": "rounded"},
        "s": {"type": "Numbers and sheets", "letter": "font"}}}
    graph = project_file.from__dict(content).graph
    assert graph.nodes["t"].inputs["lettering"] == "rounded"
    assert graph.nodes["s"].inputs["lettering"] == "font"
