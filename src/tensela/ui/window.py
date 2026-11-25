"""The application window (Delivery 1: see and move).

    tensela-app examples/case_01.json

In the centre, the 3D view of the exported nodes. Around it, in dockable panels (they move, group, go to another
screen; where they were left is remembered): the node canvas, the sliders of the *Values*, the chosen *Node* and the
*Data* (the shape of what each node produces). Moving a slider recomputes only what depends on that value and updates
the view at once.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import math
import sys
import threading
import time
from pathlib import Path

import numpy as np

from PySide6.QtCore import (QEventLoop, QLibraryInfo, QLocale, QSettings, QSignalBlocker, QSize, Qt, QTimer,
                            QTranslator, Signal)
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPainter, QValidator
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressDialog, QPushButton,
    QScrollArea, QSlider, QTabBar, QToolButton, QVBoxLayout, QWidget,
)

from ..memory import _from_proc, memory_cap, return_memory  # noqa: F401  (the memory while computing)
from ..project_file import (EXTENSION, EXTENSIONS, COLOURS, Control, Project, to_text, open_, control_for, automatic_controls, slidable,
                       from__text, save, numbers_items, LEVEL_INPUTS)
from ..graph import Graph
from ..connectors.blender import open_in_blender, export_blend
from ..connectors.dxf import export_dxf
from ..connectors.ingetrazo import open_in_ingetrazo, export_igz
from ..connectors.obj import export_obj
from ..data import ShapeError
from ..graph import Cancelled, NodeError, Node, drawable
from ..optimize import put_value
from .search_dialog import numbers_of
from .. import values as values
from ..values import label_input, read_value, text_value
from . import icons as icons, theme as theme
from .. import language as language
from ..language import tr
from .widgets import NAME_LIMIT, Panel, DockablePanel, TableDataItems, ask_text, button_icon, set_icon
from .menus import MenusPainter, text_shortcut
from .tooltips import TipWrapper
from .dialogs import DialogDxf, DialogImage, DialogPreferences
from .editor import SETTING, Editor, editable
from .node_panel import PanelNode
from . import navigation as navigation
from .. import sun as sun_module
from .viewer import HELP_TEXTS_STYLE_NAME, STYLE_NAMES, Viewer, amount, heaviness

# Scroll bars with the «handle» well visible, in light and dark themes.



def _code_nodes(graph) -> int:
    """How many Code nodes a project has, also inside its groups."""
    loose = sum(1 for n in graph.nodes.values() if n.kind.name == 'Code')
    inside = sum(1 for d in graph.definitions.values() for n in d.nodes.values() if n.get("type") == 'Code')
    return loose + inside


class _Divider(QWidget):
    """A thin upright line between groups of buttons, in the colour of the theme's borders."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(1, 20)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.color("border", "#3a3d48")))
        painter.end()


class Slider(QWidget):
    """A value of the project: slider + box to write it exactly, and ▶ to play it from its minimum to its maximum."""

    change = Signal(float)
    play = Signal()
    stop_play = Signal()

    def __init__(self, control: Control, value: float, parent: QWidget | None = None, label: str | None = None):
        super().__init__(parent)
        self.control = control
        steps = max(1, round((control.maximum - control.minimum) / control.step))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, steps)
        self.cell = CellNumber(length=control.unit == "m")
        self.cell.setRange(-1e9, 1e9)  # any value can be written; the slider adapts
        self.cell.setSingleStep(control.step)
        # The decimals of Preferences (if they were chosen); if not, those of the slider's step.
        self.cell.setDecimals(values.DECIMALS if values.DECIMALS is not None else _decimals(control.step))
        if control.unit and control.unit != "m":      # the lengths carry their unit in the text
            self.cell.setSuffix(f" {control.unit}")
        self.cell.setKeyboardTracking(False)

        # The name above; below, the slider and the box: a long name does not squash the slider. A name of its own
        # («angle near») also says, quieter, the input it moves («to min»): so it is found from the node's panel.
        text = label or control.label or label_input(control.input_)
        if control.label and label is None and control.label != label_input(control.input_):
            label = QLabel(f"{html.escape(control.label)} <span style='color: palette(placeholder-text)'>· "
                           f"{html.escape(label_input(control.input_))}</span>")
        else:
            label = QLabel(text)
        label.setWordWrap(True)
        self.cell.setFixedWidth(104)
        layer = QVBoxLayout(self)
        layer.setContentsMargins(0, 2, 0, 2)
        layer.setSpacing(4)
        layer.addWidget(label)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.slider, stretch=1)
        row.addWidget(self.cell)
        self.button_play = button_icon("play", 'Play it: from its minimum to its maximum, in a few seconds (to see '
                                               'it move)')
        self.button_play.clicked.connect(self.play.emit)
        row.addWidget(self.button_play)
        self.button_stop = button_icon("stop", 'Stop: back to the value it had before playing')
        self.button_stop.clicked.connect(self.stop_play.emit)
        self.button_stop.hide()
        row.addWidget(self.button_stop)
        layer.addLayout(row)

        self.put(value)
        self.slider.valueChanged.connect(self._from__slider)
        self.cell.setToolTip(tr('From {from_} to {to} with the slider; type any other value here and the slider widens.').format(from_=text_value(control.minimum),
                                                                    to=text_value(control.maximum)))
        self.cell.valueChanged.connect(self._from__cell)

    def show_play(self, state: str | None) -> None:
        """How its playing goes: "playing" (⏸ and ■), "paused" (▶ and ■) or None (only ▶)."""
        set_icon(self.button_play, "pause" if state == "playing" else "play", active=state is not None)
        self.button_play.setToolTip(tr('Pause' if state == "playing" else 'Go on from here' if state == "paused" else
                                       'Play it: from its minimum to its maximum, in a few seconds (to see it move)'))
        self.button_stop.setVisible(state is not None)

    def put(self, value: float) -> None:
        with QSignalBlocker(self.slider), QSignalBlocker(self.cell):
            self.cell.setValue(value)
            self.slider.setValue(round((value - self.control.minimum) / self.control.step))

    def _from__slider(self, i: int) -> None:
        value = round(self.control.minimum + i * self.control.step, 10)
        with QSignalBlocker(self.cell):
            self.cell.setValue(value)
        self.change.emit(value)

    def _from__cell(self, value: float) -> None:
        if value < self.control.minimum or value > self.control.maximum:  # out of the range: it widens
            self.control.minimum = min(self.control.minimum, value)
            self.control.maximum = max(self.control.maximum, value)
            with QSignalBlocker(self.slider):
                self.slider.setRange(0, max(1, round((self.control.maximum - self.control.minimum) / self.control.step)))
        with QSignalBlocker(self.slider):
            self.slider.setValue(round((value - self.control.minimum) / self.control.step))
        self.change.emit(value)


#: More points than these (in a node just put) are not shown by themselves in 3D: the eye is turned on by hand.
AUTOMATIC_MAX_POINTS = 500

VERSION_LAYOUT = 1   # raise it if the panels change: an old layout is not applied


class CellNumber(QDoubleSpinBox):
    """A number box shown with a decimal comma (0,35), as in the rest of Tensela, which also accepts the point as
    decimal (0.35), never as a thousands separator.

    A length (`length=True`) with the imperial system is shown in feet and inches (12'-6 1/2"); it is typed in any unit
    (120 cm, 4', 6 1/2").
    """

    def __init__(self, parent=None, length: bool = False):
        super().__init__(parent)
        self.length = length          # before anything: setLocale already writes the value
        local = QLocale(QLocale.Language.Spanish if language.LANGUAGE == "es" else QLocale.Language.English)
        local.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator | QLocale.NumberOption.RejectGroupSeparator)
        self.setLocale(local)

    def textFromValue(self, value: float) -> str:
        return values.text_length(value) if self.length else super().textFromValue(value)

    def validate(self, text: str, position: int):
        if self.length:
            try:
                ok = isinstance(values.read_length(text), (int, float))
            except ShapeError:
                ok = False
            return (QValidator.State.Acceptable if ok else QValidator.State.Intermediate), text, position
        return super().validate(self._to_decimal(text), position)

    def valueFromText(self, text: str) -> float:
        if self.length:
            try:
                v = values.read_length(text)
                if isinstance(v, (int, float)):
                    return float(v)
            except ShapeError:
                pass
        return super().valueFromText(self._to_decimal(text))

    def _to_decimal(self, text: str) -> str:
        """It is written with a point or with a comma: the box takes it to its decimal (comma in Spanish, point in English)."""
        return text.replace(".", ",") if self.locale().decimalPoint() == "," else text.replace(",", ".")


class DialogControl(QDialog):
    """The range and the step of a slider, and its name: the step is also how fine Find the best… searches."""

    #: More positions than these on one slider: it could not be moved one by one.
    MOST_STEPS = 100_000

    def __init__(self, control: Control, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Range and step'))
        length = control.unit == "m"
        form = QFormLayout()
        self.name = QLineEdit(control.label)
        self.name.setMaxLength(NAME_LIMIT)
        self.name.setPlaceholderText(label_input(control.input_))
        form.addRow(tr('Name'), self.name)
        self.cells = {}
        decimals = max(_decimals(control.step), _decimals(control.minimum), _decimals(control.maximum), 2)
        for key, text, value in (("minimum", 'Minimum', control.minimum), ("maximum", 'Maximum', control.maximum),
                                 ("step", 'Step', control.step)):
            cell = CellNumber(length=length)
            cell.setRange(-1e9, 1e9)
            cell.setDecimals(min(decimals + 2, 8))
            if control.unit and not length:
                cell.setSuffix(f" {control.unit}")
            cell.setValue(value)
            cell.valueChanged.connect(self._check)
            self.cells[key] = cell
            form.addRow(tr(text), cell)
        layer = QVBoxLayout(self)
        layer.addLayout(form)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setProperty("role", "secondary")
        layer.addWidget(self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layer.addWidget(self.buttons)
        self._check()

    def choice(self) -> tuple[str, float, float, float]:
        """The name (empty: that of the input), the minimum, the maximum and the step."""
        c = self.cells
        return self.name.text().strip(), c["minimum"].value(), c["maximum"].value(), c["step"].value()

    def _check(self, *_) -> None:
        """Says how many positions the slider will have, or what is wrong (and then it cannot be accepted)."""
        _, low, high, step = self.choice()
        wrong = (tr('The maximum must be greater than the minimum.') if high <= low else
                 tr('The step must be greater than zero.') if step <= 0 else
                 tr('The step is larger than the whole range.') if step > high - low + 1e-12 else
                 tr('Too many positions ({n}): use a larger step.').format(n=f"{round((high - low) / step):,}".replace(
                     ",", " ")) if (high - low) / step > self.MOST_STEPS else "")
        self.note.setText(wrong or tr('{n} positions on the slider. The step is also how fine Find the best… '
                                      'searches.').format(n=round((high - low) / step) + 1))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not wrong)


def _cut_thread(thread: threading.Thread) -> None:
    """Raises Cancelled inside the computation thread: it stops at its next Python instruction (it does not wait for
    the current node to end)."""
    import ctypes
    if thread.ident is not None and thread.is_alive():
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread.ident), ctypes.py_object(Cancelled))


def _feeding(graph, names) -> set[str]:
    """`names` and every node that feeds them."""
    found, pending = set(), [n for n in names if n in graph.nodes]
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        for value in graph.nodes[name].inputs.values():
            for item in (value if isinstance(value, (list, tuple)) else [value]):
                if isinstance(item, Node) and item.name not in found:
                    pending.append(item.name)
    return found


class _FailureApart(Exception):
    """A failure of the program in the process that computes: its text, and where it happened."""

    def __init__(self, text: str, trace: str):
        super().__init__(text)
        self.trace = trace


class _ProjectTabs(QTabBar):
    """The tabs of the projects, only as wide as they are: Qt keeps room for its scroll arrows, and the «+» beside
    them was left far away."""

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self.sizeHint().width(), 120), hint.height())


class Window(QMainWindow):
    _computation_finished = Signal(int)      # from the computation thread: its turn
    _computing_node = Signal(int, str)       # from the process that computes: the node it starts, in which turn

    def __init__(self):
        super().__init__()
        self.project: Project | None = None
        self.filepath: Path | None = None
        self.resize(1500, 950)

        app = QApplication.instance()
        if app is not None and app.property("menu_painter") is None:
            # The shortcuts of all the menus, in short and smaller than the command (ui/menus.py).
            app.setProperty("menu_painter", True)
            app._menus_painter = MenusPainter(app)
            app.installEventFilter(app._menus_painter)
            # Each tooltip in short lines, not one across the screen (ui/tooltips.py).
            app._tip_wrapper = TipWrapper(app)
            app.installEventFilter(app._tip_wrapper)
        self.viewer = Viewer()
        if theme.current():
            self.viewer.put_background(theme.color_view())
        self.editor = Editor()
        self.editor.plane_of_view = self.viewer.plane_of_view   # new rectangles and circles stand where you look
        self.editor.changed.connect(self._after_edit)
        self.editor.warning.connect(self._warn)
        self.editor.selected.connect(self._display_node)
        self.editor.value_changed.connect(self._change_text)   # what was written on the card itself
        self.editor.values_changed.connect(self._change_texts)  # one value for several (Alt + drag on the card)
        self.editor.enter.connect(self.enter_group)
        self.editor.toggle_see.connect(self._toggle_see)       # the eye of the card
        self.editor.isolate.connect(self.isolate)                     # Alt + click on the eye
        self._levels: list[dict] = []           # the groups entered, one inside the other (see `_inside`)
        self._eyes_inside: dict[str, list] = {}  # inside each group, the nodes seen in 3D (for this session)
        self.panel_node = PanelNode()
        self.panel_node.rename.connect(self._rename)
        self.panel_node.change.connect(lambda node, input_, text: self._change_together(node, [input_], text))
        self.panel_node.change_several.connect(self._change_together)
        self.panel_node.toggle_slider.connect(self._toggle_slider)
        self.panel_node.toggle_see.connect(self._toggle_see)
        self.panel_node.change_color.connect(self._change_color)
        self.panel_node.colour_by.connect(self._colour_by)
        self.panel_node.rest.connect(self.calculate_rest)
        self.panel_node.change_opacity.connect(self._change_opacity)
        self.panel_node.toggle_number.connect(self._toggle_number)
        self.panel_node.toggle_curvature.connect(self._toggle_curvature)
        self.panel_node.analyse.connect(self._change_analysis)
        self.panel_node.change_value.connect(self._change_value_together)
        self._together: list[str] = []           # several nodes of one kind chosen: the panel changes all of them
        self._say_after = ""                     # what a change says, shown when its computation ends (not covered)
        self.panel_node.draw.connect(self.draw)
        self.panel_node.code.connect(self.edit_code)
        self.panel_node.play.connect(self.play_input)
        self.panel_node.stop_play.connect(lambda node, input_: self.stop_playing_back(("input", node, input_)))
        self.editor.code.connect(self.edit_code)
        self.editor.edit.connect(self._edit_node)
        bar = self.viewer.bar_drawing
        bar.grid_changed.connect(self._change_grid_drawing)
        bar.closed.connect(self._dismiss_drawing)
        bar.finish.connect(self.finish_drawing)
        bar.knots.connect(lambda *_: self._put_strip_nodes())
        bar.rest.connect(lambda *_: self.recompute())
        strip = self.viewer.strip_nodes
        strip.moved.connect(self._moved_nodes)
        strip.insert.connect(self._insert_node)
        strip.remove.connect(self._remove_node)
        strip.over.connect(self._node_over)
        self.viewer.drawing.tool_changed.connect(
            lambda *_: self.statusBar().showMessage(self._instructions_drawing()) if self._drawing else None)
        self._selection: str | None = None
        self.modified = False
        self.editor.moved.connect(lambda: (self._register("mover cajas"), self._look_again()))   # (a preview opened)
        self.editor.notes_changed.connect(lambda: self._register())
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._state = ""
        self._last_change = ("", 0.0)

        self.panel_values = QWidget()
        self.items_values = QVBoxLayout(self.panel_values)
        self.items_values.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)   # if it does not fit, it scrolls
        self.items_values.addStretch(1)
        scrollable = self._scrollable_values = QScrollArea()
        scrollable.setWidgetResizable(True)
        scrollable.setWidget(self.panel_values)
        box_values = Panel(tr('Values'))
        box_values.body.addWidget(scrollable)
        find_best = button_icon("target", 'Find the best…: moves these sliders until a number reaches its minimum, '
                                          'its maximum or a value')
        find_best.clicked.connect(lambda: self.open_search())
        box_values.action(find_best)

        self.table = TableDataItems()
        self.table.setToolTip(tr('In green, what was recalculated by the last change. A click selects the node.'))
        self.table.chosen.connect(lambda name: self.editor.select(name))
        box_data_items = Panel(tr('Data'))
        box_data_items.body.addWidget(self.table)
        export_data_items = button_icon("export", 'Export the table (CSV) or copy it as text')
        export_data_items.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_data_items = QMenu(export_data_items)
        menu_data_items.addAction(tr('Save as CSV…')).triggered.connect(lambda: self._export_data_items("csv"))
        menu_data_items.addAction(tr('Copy as text')).triggered.connect(lambda: self._export_data_items("copy"))
        export_data_items.setMenu(menu_data_items)
        export_data_items.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        box_data_items.action(export_data_items)

        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setObjectName("warning")
        self.warning.hide()
        # While a long computation goes on in another thread: the window responds, and it can be stopped.
        self.strip_computation = QFrame()
        self.strip_computation.setObjectName("computing_strip")
        row_computation = QHBoxLayout(self.strip_computation)
        row_computation.setContentsMargins(10, 4, 6, 4)
        self._computing_text = QLabel(tr('Calculating… Meanwhile the view shows the last result.'))
        row_computation.addWidget(self._computing_text, 1)
        stop = QPushButton(tr('Stop'))
        stop.setToolTip(tr('Abandon this calculation (for example, if a count has an extra digit)'))
        stop.clicked.connect(self.stop_computation)
        row_computation.addWidget(stop)
        self.strip_computation.hide()
        self._computation_finished.connect(self._on_finish_computation)
        self._computing_node.connect(self._say_computing_node)
        # An isolated node: only it in the 3D view, framed (to look at it closely); leaving leaves everything as it was.
        self.isolated_strip = QFrame()
        self.isolated_strip.setObjectName("computing_strip")
        isolated_row = QHBoxLayout(self.isolated_strip)
        isolated_row.setContentsMargins(10, 4, 6, 4)
        self._isolated_text = QLabel()
        isolated_row.addWidget(self._isolated_text, 1)
        quit_ = QPushButton(tr('Exit'))
        quit_.setToolTip(tr('See everything again, with the view as it was (/)'))
        quit_.clicked.connect(lambda: self.isolate(None))
        isolated_row.addWidget(quit_)
        self.isolated_strip.hide()
        self._isolated: str | None = None

        # A node too heavy to draw without asking (a digit too many in a count): its eye stays on, the view waits.
        self.held_strip = QFrame()
        self.held_strip.setObjectName("computing_strip")
        held_row = QHBoxLayout(self.held_strip)
        held_row.setContentsMargins(10, 4, 6, 4)
        self._held_text = QLabel()
        self._held_text.setWordWrap(True)
        held_row.addWidget(self._held_text, 1)
        draw_them = QPushButton(tr('Show them'))
        draw_them.setToolTip(tr('Draw them anyway. It is remembered with the project: it is not asked again unless '
                                'they become many more.'))
        draw_them.clicked.connect(self._draw_held)
        held_row.addWidget(draw_them)
        eye_off = QPushButton(tr('Turn off its eye'))
        eye_off.setToolTip(tr('Do not see it in 3D; the nodes that use it go on computing with it.'))
        eye_off.clicked.connect(self._held_off)
        held_row.addWidget(eye_off)
        self.held_strip.hide()
        self._held: list[str] = []

        # From the AppImage, the first time: Tensela offers to go into the applications menu (ui/desktop.py).
        self.desktop_strip = QFrame()
        self.desktop_strip.setObjectName("computing_strip")
        desktop_row = QHBoxLayout(self.desktop_strip)
        desktop_row.setContentsMargins(10, 4, 6, 4)
        desktop_text = QLabel(tr('Tensela is not in your applications menu yet. Add it, so that it opens from there '
                                 'and .tela files open with a double click.'))
        desktop_text.setWordWrap(True)
        desktop_row.addWidget(desktop_text, 1)
        add_menu = QPushButton(tr('Add to the menu'))
        add_menu.setToolTip(tr('Only in your folders (~/.local/share). Preferences ▸ General can take it out again.'))
        add_menu.clicked.connect(lambda: self.put_in_menu(True))
        desktop_row.addWidget(add_menu)
        no_menu = QPushButton(tr('No, thanks'))
        no_menu.setToolTip(tr('It is not asked again. Preferences ▸ General can still do it.'))
        no_menu.clicked.connect(self._decline_menu)
        desktop_row.addWidget(no_menu)
        self.desktop_strip.hide()

        # The nodes not seen are not calculated (Window._wanted): «Calculate the rest» does it once, to see their
        # results and whether any has an error; with the next change they wait again.
        self.button_rest = QPushButton()
        self.button_rest.setObjectName("button_rest")
        self.button_rest.setToolTip(tr('Calculate once also the nodes that are not seen: to see their results and '
                                       'whether any has an error. With the next change they wait again.'))
        self.button_rest.clicked.connect(self.calculate_rest)
        self.statusBar().addPermanentWidget(self.button_rest)
        self.button_rest.hide()

        # In the centre, the 3D view (with the notice on top). The rest, in dockable panels:
        # they move, group, go to another screen and where they were left is remembered.
        self.card_view = Panel(tr('3D view'))
        self.card_view.body.addWidget(self.viewer)
        centre = QWidget()
        margin = QVBoxLayout(centre)
        margin.setContentsMargins(8, 8, 0, 0)
        # One tab per open project.
        self.tabs = _ProjectTabs()
        self.tabs.setObjectName("project_tabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setExpanding(False)
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._to_tab)
        self.tabs.tabCloseRequested.connect(self.dismiss_tab)
        self.tabs.tabMoved.connect(self._moved_tab)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self._menu_tab)
        self.documents: list[dict] = []
        self._tabs_row = QWidget()
        tabs_row = QHBoxLayout(self._tabs_row)
        tabs_row.setContentsMargins(0, 0, 0, 0)
        tabs_row.setSpacing(4)
        tabs_row.addWidget(self.tabs)
        self.button_new_tab = button_icon("plus", 'New project (Ctrl+N). To start from a recipe: File ▸ Start screen')
        self.button_new_tab.setObjectName("new_tab")
        self.button_new_tab.clicked.connect(self.new_)
        tabs_row.addWidget(self.button_new_tab)
        tabs_row.addStretch(1)
        self._tabs_row.hide()
        margin.addWidget(self._tabs_row)
        margin.addWidget(self.warning)
        margin.addWidget(self.strip_computation)
        margin.addWidget(self.isolated_strip)
        margin.addWidget(self.held_strip)
        margin.addWidget(self.desktop_strip)
        margin.addWidget(self.card_view, 1)
        self.setCentralWidget(centre)
        self.card_nodes = Panel(tr('Nodes'))
        self.card_nodes.body.addWidget(self.editor)
        # Inside a group: «Leave group», set apart from the canvas tools by a thin line (it is only for now).
        self._button_quit = QWidget()
        leaving = QHBoxLayout(self._button_quit)
        leaving.setContentsMargins(0, 0, 0, 0)
        leaving.setSpacing(0)
        leave = QPushButton(tr('Leave group'))
        leave.setToolTip(tr('Back to the project (what you edited inside is already applied)'))
        leave.clicked.connect(lambda: self.quit_group())
        leaving.addWidget(leave)
        leaving.addSpacing(10)
        leaving.addWidget(_Divider())
        leaving.addSpacing(6)
        self._button_quit.hide()
        self.card_nodes.action_items.insertWidget(0, self._button_quit)

        from .sketch_dialog import SketchPanel
        self.croquis = SketchPanel()
        card_sketch = Panel(tr("Croquis"))
        card_sketch.body.addWidget(self.croquis)
        from .library_panel import LibraryPanel
        self.library = LibraryPanel()
        card_library = Panel(tr("Library"))
        card_library.body.addWidget(self.library)
        self.library.put.connect(self._put_group)
        self.library.save.connect(self._save_kind_in_library)
        self.library.rename.connect(self._rename_in_library)
        self.library.delete.connect(self._delete_from_library)
        self.library.open_folder.connect(self.open_library)
        self._library_groups: dict = {}              # {name: (description, summary)} of the library, read when it changes
        self.panels = {key: DockablePanel(panel, key, self) for key, panel in (
            ("nodes", self.card_nodes), ("values", box_values), ("node", self.panel_node), ("data", box_data_items),
            ("sketch", card_sketch), ("library", card_library))}
        self.panels["library"].toggleViewAction().setShortcut(QKeySequence("Ctrl+Alt+L"))
        # Croquis follows the view: on turning it or changing the model, it is passed the scene (if it is seen).
        self._version_graph_scene = 0
        self._graph_scene_sketch = None
        self._watcher_sketch = QTimer(self)
        self._watcher_sketch.setInterval(400)
        self._watcher_sketch.timeout.connect(self._follow_sketch)
        self._watcher_sketch.start()
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowNestedDocks
                            | QMainWindow.DockOption.AllowTabbedDocks)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self._factory_place()
        self.setContentsMargins(4, 0, 8, 6)   # room around the cards

        self._start_extensions()                     # before the menus (they bring entries) and the calculator
        self._menus()
        self._tools()
        self._register_shortcuts()
        self.editor.on_ask_menu = self._menu_canvas_and_extensions
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu_data_items)
        self.viewer.requested_menu.connect(self._menu_view)
        self._apply_preferences()
        self._recover_layout()
        self._title()
        QTimer.singleShot(0, self._calculator)          # the process that computes, ready before the first change
        self.statusBar().showMessage(tr('File → New or File → Open… to start.'))
        QTimer.singleShot(0, lambda: self._tell_extensions("window"))   # the window is ready (Api.on)

    # --- Menus ---------------------------------------------------------------

    def _menus(self) -> None:
        file = self.menuBar().addMenu(tr('&File'))

        def action(menu, text, shortcut, function, help=None):
            a = QAction(text, self)
            a.setShortcut(shortcut)
            a.triggered.connect(function)
            if help:
                a.setStatusTip(tr(help))
            menu.addAction(a)
            self.addAction(a)  # the shortcut also works inside a submenu

        action(file, tr('&New'), QKeySequence.StandardKey.New, self.new_)
        action(file, tr('Start &screen…'), QKeySequence("Ctrl+Shift+N"), self.show_start,
               'New project, the recent ones and the recipes to start from')
        action(file, tr('&Open…'), QKeySequence.StandardKey.Open, self._open_ask)
        self.menu_recent = file.addMenu(tr('Open &recent'))
        self.menu_recent.aboutToShow.connect(self._fill_recent)
        action(file, tr('&Save'), QKeySequence.StandardKey.Save, self.save)
        action(file, tr('Save &as…'), QKeySequence("Ctrl+Shift+S"), self.save_as)
        action(file, tr('C&lose project'), QKeySequence("Ctrl+W"), lambda: self.dismiss_tab(),
               'Closes this tab (asks if there are changes)')
        for shortcut, step in (("Ctrl+Tab", 1), ("Ctrl+Shift+Tab", -1)):     # from tab to tab
            go = QAction(self)
            go.setShortcut(QKeySequence(shortcut))
            go.triggered.connect(lambda _=False, p=step: self._to_tab_next(p))
            self.addAction(go)
        file.addSeparator()
        # What is taken outside: files that are saved (Export) and programs that are opened (Open in).
        export = file.addMenu(tr('&Export'))
        action(export, tr('&Image (PNG)…'), QKeySequence("Ctrl+Shift+E"), self._ask_image,
               'The 3D view as an image, larger than on screen')
        action(export, tr('Freehand &sketch (PNG, SVG, PDF)…'), QKeySequence("Ctrl+K"), self._sketch,
               'The 3D view drawn by hand, with Croquis')
        export.addSeparator()
        action(export, tr('&DXF (3D or 2D)…'), QKeySequence("Ctrl+Shift+D"), self._ask_dxf,
               'For AutoCAD, BricsCAD, Rhino, ArchiCAD…: the model, or a plan or an elevation')
        action(export, tr("&OBJ…"), QKeySequence("Ctrl+E"), self._ask_export, 'For any 3D program')
        export.addSeparator()
        action(export, tr("3D print (&STL)…"), QKeySequence(), lambda: self._ask_print("stl"),
               'For any slicer: the visible pieces, in millimetres, checked before saving')
        action(export, tr("3D print (3&MF)…"), QKeySequence(), lambda: self._ask_print("3mf"),
               'The modern one: it keeps the unit, and each visible node is an object with its name and colour')
        action(export, tr("C&utting file (DXF or SVG)…"), QKeySequence(), self._ask_cutting,
               'For a laser, a router, a plasma: the flat pieces in millimetres, cut in red and engraved in blue; one '
               'file per sheet')
        export.addSeparator()
        action(export, tr("&Blender (.blend)…"), QKeySequence("Ctrl+Shift+B"), self._ask_export_blend)
        action(export, tr("Inge&Trazo (.igz)…"), QKeySequence("Ctrl+Shift+I"), self._ask_export_igz)
        self._menu_export = export                     # (the extensions add theirs at the end)
        open_in = file.addMenu(tr('Open i&n'))
        action(open_in, tr("&Blender"), QKeySequence("Ctrl+B"), self._open_in_blender,
               'Opens Blender with the scene set up')
        action(open_in, tr("Inge&Trazo"), QKeySequence("Ctrl+I"), self._open_in_ingetrazo,
               'Opens IngeTrazo with the scene (save it from there)')
        file.addSeparator()
        action(file, tr('&Quit'), QKeySequence.StandardKey.Quit, self.close)
        edit = self.menuBar().addMenu(tr('&Edit'))
        for text, shortcuts, action in (
            (tr('&Undo'), [QKeySequence.StandardKey.Undo], self.undo),
            (tr('&Redo'), [QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")], self.redo),
        ):
            a = QAction(text, self)
            a.setShortcuts(shortcuts)
            a.triggered.connect(action)
            edit.addAction(a)
        edit.addSeparator()
        # Adding a node: Tab on the canvas (the canvas handles it, so Tab still works in the fields).
        # This action only shows it in the menu and lets it be changed in Preferences → Interaction.
        add = QAction(tr('&Add a node…'), self)
        add.setShortcut(QKeySequence("Tab"))
        add.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)   # the shortcut does not act by itself
        add.triggered.connect(lambda: self.editor.graph and self.editor.open_finder(
            self.editor.viewport().rect().center()))
        add.changed.connect(lambda: setattr(self.editor, "key_finder", add.shortcut()))
        edit.addAction(add)
        repeat = QAction(tr('&Repeat last node'), self)
        repeat.setShortcut(QKeySequence("Shift+R"))
        repeat.setStatusTip(tr('Places the last node type you used again, where the mouse is'))
        repeat.triggered.connect(lambda: self.editor.last_repeat()
                                  or self.statusBar().showMessage(tr('You have not placed any node yet.')))
        edit.addAction(repeat)
        find = QAction(tr('&Find a node…'), self)
        find.setShortcut(QKeySequence.StandardKey.Find)
        find.triggered.connect(lambda: self.editor.graph and self.editor.find_node())
        self._action_items_edit = {"search": find}
        best = QAction(tr('Find the &best…'), self)
        best.setStatusTip(tr('Moves the sliders of Values until a number reaches its minimum, its maximum or a value'))
        best.triggered.connect(lambda: self.open_search())
        self._action_items_edit["find_best"] = best
        # Copy, cut, paste…: only with the focus on the canvas (in a field, Ctrl+C copies the text).
        for key, text, shortcut, function in (
                ("copy", '&Copy', QKeySequence.StandardKey.Copy, lambda: self.editor.copy()),
                ("cut", 'Cu&t', QKeySequence.StandardKey.Cut, lambda: self.editor.cut()),
                ("paste", '&Paste', QKeySequence.StandardKey.Paste, lambda: self.editor.paste()),
                ("duplicate", 'D&uplicate', QKeySequence("Ctrl+D"), lambda: self.editor.duplicate()),
                ("all", 'Select &all', QKeySequence.StandardKey.SelectAll, lambda: self.editor.select_all())):
            a = QAction(tr(text), self)
            a.setShortcut(shortcut)
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            a.triggered.connect(lambda _=False, f=function: self.editor.graph is not None and f())
            self.editor.addAction(a)
            edit.addAction(a)
            self._action_items_edit[key] = a
        edit.addSeparator()
        edit.addAction(best)
        edit.addSeparator()
        for key, text, shortcut, function in (("group", '&Group…', "Ctrl+G", lambda: self.group()),
                                             ("ungroup", '&Ungroup', "Ctrl+Shift+G", lambda: self.ungroup())):
            a = QAction(tr(text), self)
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            a.triggered.connect(lambda _=False, f=function: self.project is not None and f())
            self.editor.addAction(a)
            edit.addAction(a)
            self._action_items_edit[key] = a
        folder = QAction(tr('Open the library folder'), self)
        folder.triggered.connect(self.open_library)
        edit.addAction(folder)
        edit.addSeparator()
        edit.addAction(find)
        edit.addSeparator()
        preferences = QAction(tr('&Preferences…'), self)
        preferences.setShortcut(QKeySequence("Ctrl+,"))
        preferences.triggered.connect(self.open_preferences)
        edit.addAction(preferences)
        see = self.menuBar().addMenu(tr('&View'))
        frame = QAction(tr('&Frame all'), self)
        frame.setShortcut(QKeySequence("F"))
        frame.triggered.connect(lambda: self.viewer.frame())
        see.addAction(frame)
        self._action_items = {"frame_all": frame}
        frame_nodes = QAction(tr('Frame the &nodes'), self)
        frame_nodes.setShortcut(QKeySequence("Shift+F"))
        frame_nodes.triggered.connect(lambda: self.editor.frame())
        see.addAction(frame_nodes)
        self._action_items["frame_nodes"] = frame_nodes
        isolate = QAction(tr('&Isolate the selected node'), self)
        isolate.setShortcut(QKeySequence("/"))
        isolate.setStatusTip(tr('Only that node in the 3D view, framed; again (or «Exit») goes back to everything. '
                               'Also: Alt + click on its card’s eye.'))
        isolate.triggered.connect(lambda: self.isolate(None if self._isolated else self._selection))
        see.addAction(isolate)
        self._action_items["isolate"] = isolate
        # Turning eyes on and off several at a time (they stay so: it is what is seen and exported).
        for key, text, shortcut, tip, function in (
                ("see_only", 'Show &only the selected', "Shift+H",
                 'Turns off the eye of every other node: only the selected stay in the 3D view.',
                 lambda: self.see_only(self._selected_names())),
                ("hide_selected", '&Hide the selected', "H", 'Turns off the eye of the selected nodes.',
                 lambda: self.hide(self._selected_names())),
                ("see_all", 'Show &all', "Alt+H", 'Turns on the eye of every node that gives a geometry.',
                 lambda: self.see_all()),
                ("hide_all", 'Hid&e all', "Alt+Shift+H", 'Turns off every eye: an empty 3D view.',
                 lambda: self.hide_all())):
            action = QAction(tr(text), self)
            action.setShortcut(QKeySequence(shortcut))
            action.setStatusTip(tr(tip))
            action.triggered.connect(function)
            see.addAction(action)
            self._action_items[key] = action
        see.addSeparator()
        arrange_nodes = QAction(tr('&Arrange the nodes'), self)
        arrange_nodes.setShortcut(QKeySequence("Ctrl+L"))
        arrange_nodes.triggered.connect(lambda: self.editor.graph and self.editor.arrange_all())
        see.addAction(arrange_nodes)
        self._action_items["arrange"] = arrange_nodes
        organise = see.addMenu(tr('Or&ganize nodes'))
        for text, as_, shortcut in Editor.ALIGN:
            if text is None:
                organise.addSeparator()
                continue
            a = QAction(tr(text), self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(lambda _=False, c=as_: self.editor.graph and self.editor.align(c))
            organise.addAction(a)
            self._action_items.setdefault("align", []).append(a)
        organise.addSeparator()
        for text, direction, shortcut in Editor.DISTRIBUTE:
            a = QAction(tr(text), self)
            a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(lambda _=False, s=direction: self.editor.graph and self.editor.distribute(s))
            organise.addAction(a)
            self._action_items.setdefault("distribute", []).append(a)
        self.editor.graph_scene.selectionChanged.connect(self._action_items_by_selection)
        self._action_items_by_selection()
        grid = QAction(tr('Snap to &grid'), self)
        grid.setCheckable(True)
        grid.setChecked(QSettings().value("canvas/grid", True, type=bool))
        SETTING["grid"] = grid.isChecked()
        grid.toggled.connect(lambda yes: (SETTING.__setitem__("grid", yes), QSettings().setValue("canvas/grid", yes)))
        see.addAction(grid)
        self._action_items["grid"] = grid
        guides = QAction(tr('Smart &guides'), self)
        guides.setCheckable(True)
        guides.setChecked(QSettings().value("canvas/guides", True, type=bool))
        SETTING["guides"] = guides.isChecked()
        guides.toggled.connect(lambda yes: (SETTING.__setitem__("guides", yes), QSettings().setValue("canvas/guides", yes)))
        see.addAction(guides)
        self._action_items["guides"] = guides
        menu_legends = see.addMenu(tr('Color &legends'))   # those of «by a value»: for the capture
        group_legends = QActionGroup(self)
        side = QSettings().value("view/legends", "right")
        for key, text in (("right", 'On the right'), ("left", 'On the left')):
            a = QAction(tr(text), self)
            a.setCheckable(True)
            a.setChecked(key == side)
            a.triggered.connect(lambda _=False, c=key: (self.viewer.legends_side(c),
                                                          QSettings().setValue("view/legends", c)))
            group_legends.addAction(a)
            menu_legends.addAction(a)
        self.viewer.legends_side(side if side in ("right", "left") else "right")
        see.addSeparator()
        menu_panels = see.addMenu(tr('&Panels'))
        for panel in self.panels.values():
            menu_panels.addAction(panel.toggleViewAction())
        menu_panels.addSeparator()
        factory = QAction(tr('&Factory layout'), self)
        factory.triggered.connect(self.factory_layout)
        menu_panels.addAction(factory)
        self._menu_spaces = see.addMenu(tr('&Workspaces'))
        self._menu_spaces.aboutToShow.connect(self._fill_spaces)
        menu_mode = see.addMenu(tr('&Mode'))          # light or dark; the node cards, in Preferences
        saved_mode = QSettings().value("theme/mode", "system")
        group_mode = QActionGroup(self)
        for key, text in (("system", 'Like the system'), ("light", 'Light'), ("dark", 'Dark')):
            a = QAction(tr(text), self, checkable=True, checked=(key == saved_mode))
            a.triggered.connect(lambda _=False, k=key: self.apply_preference("theme/mode", k))
            group_mode.addAction(a)
            menu_mode.addAction(a)
        self._menu_extensions = self.menuBar().addMenu(tr('E&xtensions'))
        self._fill_extension_menus()
        self._menu_help()

    # --- Extensions (extensions.py) ---------------------------------------------------------------------------

    def extensions_on(self) -> list[str]:
        """The ids of the extensions turned on (remembered in the preferences)."""
        value = QSettings().value("extensions/on", []) or []
        return [value] if isinstance(value, str) else list(value)

    def _start_extensions(self) -> None:
        """At opening: the extensions turned on are loaded (one that fails is said and stays off)."""
        from .. import extensions as E
        failed = []
        on = E.load_these(self.extensions_on(), failed.append)
        os.environ[E.ENVIRONMENT] = E.for_the_calculator()
        if failed:
            QTimer.singleShot(1000, lambda: QMessageBox.warning(self, tr('Extensions'), "\n\n".join(failed)))
        if len(on) != len(self.extensions_on()):
            QSettings().setValue("extensions/on", on)

    def turn_extension(self, ext_id: str, yes: bool) -> str:
        """Turns an extension on or off, at once: its nodes, its ways of exporting and its actions; the process that
        computes starts again with it; the open project is read again (its nodes of that extension are real now, or
        marked). What failed, or ""."""
        from .. import extensions as E
        said = ""
        if yes:
            failed = []
            E.load_these([ext_id], failed.append)
            said = "\n".join(failed)
        else:
            E.unload(ext_id)
        on = [i for i in self.extensions_on() if i != ext_id] + ([ext_id] if ext_id in E.LOADED else [])
        QSettings().setValue("extensions/on", on)
        os.environ[E.ENVIRONMENT] = E.for_the_calculator()
        if self._calculator_ is not None:
            self._calculator_.renew()
        self._fill_extension_menus()
        icons._drawing.cache_clear()                     # its icons come (or go) with it
        if yes and not said:                             # turned on with the window ready: it hears so
            self._tell_extensions("window", only=ext_id)
        icons.pixmap.cache_clear()
        if self.project is not None and not said:
            if any(n.kind.extension == ext_id for n in self.project.graph.nodes.values()):
                self._restore(self._snapshot())
            else:
                self.editor.viewport().update()
        return said

    def _fill_extension_menus(self) -> None:
        """The Extensions menu (Manage… and the actions of those on) and their ways of exporting, in File →
        Export."""
        from .. import extensions as E
        menu = self._menu_extensions
        menu.clear()
        manage = menu.addAction(tr('&Manage extensions…'))
        manage.setStatusTip(tr('Those installed, turned on or off; install one from a file'))
        manage.triggered.connect(self.manage_extensions)
        # One submenu per extension on: its actions (they do something once) and, apart, its panels (with their check,
        # open or closed): so it is clear what is whose, and what stays on.
        self._sync_extension_panels()
        names = {e.id: e.said("name") for e in E.available()}
        whose = list(dict.fromkeys([e.extension for e in E.actions()] +
                                   [ext_id for ext_id, _ in self._extension_panels]))
        if whose:
            menu.addSeparator()
        for ext_id in sorted(whose, key=lambda i: names.get(i, i).casefold()):
            sub = menu.addMenu(names.get(ext_id, ext_id))
            sub.setObjectName(f"extension_menu_{ext_id}")
            for entry in [e for e in E.actions() if e.extension == ext_id]:
                a = sub.addAction(tr(entry.label))
                a.setStatusTip(tr(entry.help))
                self._entry_icon(a, entry)
                a.triggered.connect(lambda _=False, e=entry: self._run_extension_action(e))
            docks = [d for (i, _), d in self._extension_panels.items() if i == ext_id]
            if docks and sub.actions():
                sub.addSeparator()
            for dock in docks:
                a = dock.toggleViewAction()
                a.setText(tr('Panel: {name}').format(name=tr(dock.entry.label)))
                a.setStatusTip(tr(dock.entry.help))      # (no icon: on a panel it hides the check, open or closed)
                sub.addAction(a)
        for a in self.__dict__.get("_extension_exports", []):
            self._menu_export.removeAction(a)
        self._extension_exports = []
        exports = E.exports()
        if exports:
            self._extension_exports.append(self._menu_export.addSeparator())
        for entry in exports:
            a = self._menu_export.addAction(tr(entry.label))
            a.setStatusTip(tr(entry.help))
            a.triggered.connect(lambda _=False, e=entry: self._run_extension_export(e))
            self._extension_exports.append(a)

    _extensions_dialog = None

    def manage_extensions(self) -> None:
        """Extensions → Manage extensions…"""
        from .extensions_dialog import ExtensionsDialog
        if self._extensions_dialog is None:
            self._extensions_dialog = ExtensionsDialog(self)
        self._extensions_dialog.fill()
        self._extensions_dialog.show()
        self._extensions_dialog.raise_()
        self._extensions_dialog.activateWindow()

    def _run_extension_action(self, entry, *args) -> None:
        try:
            entry.function(self, *args)
        except Exception as error:                     # noqa: BLE001 (an extension that fails does not close Tensela)
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, tr('Extensions'), tr('«{label}» failed: {error}').format(
                label=tr(entry.label), error=f"{type(error).__name__}: {error}"))

    def _entry_icon(self, action: QAction, entry) -> None:
        if entry.icon:
            action.setIcon(icons.icon(entry.icon, theme.color("text_2", "#9ca1b0"), 16))

    def _extension_entries(self, menu: QMenu, where: str, name: str | None = None) -> None:
        """The entries the extensions on put in a right-click menu (of a node, the canvas or the 3D view)."""
        from .. import extensions as E
        entries = E.menus(where)
        if entries:
            menu.addSeparator()
        for entry in entries:
            a = menu.addAction(tr(entry.label))
            a.setStatusTip(tr(entry.help))
            a.setToolTip(tr(entry.help))
            self._entry_icon(a, entry)
            args = (name,) if where == "node" else ()
            a.triggered.connect(lambda _=False, e=entry, x=args: self._run_extension_action(e, *x))

    _extension_panels: dict = {}

    def _sync_extension_panels(self) -> None:
        """A panel for each one the extensions on bring (closed, beside Values, until it is opened); those of an
        extension turned off go away."""
        from .. import extensions as E
        if "_extension_panels" not in self.__dict__:
            self._extension_panels = {}
        wanted = {(e.extension, e.label): e for e in E.panels()}
        for key in [k for k in self._extension_panels if k not in wanted]:
            dock = self._extension_panels.pop(key)
            dock.return_()
            self.removeDockWidget(dock)
            dock.deleteLater()
        for key, entry in wanted.items():
            if key in self._extension_panels:
                continue
            card = Panel(tr(entry.label))
            slug = re.sub(r"[^a-z0-9]+", "_", entry.label.lower()).strip("_")
            dock = DockablePanel(card, f"extension_{entry.extension}_{slug}", self)
            dock.entry, dock.built, dock.content = entry, False, None
            dock.visibilityChanged.connect(lambda seen, d=dock: seen and self._build_extension_panel(d))
            # Opened from the menu: in front of its tab group, and built at once.
            dock.toggleViewAction().triggered.connect(
                lambda yes, d=dock: yes and (d.raise_(), self._build_extension_panel(d)))
            if not self.restoreDockWidget(dock):          # where it was left last time, or beside Values
                self.tabifyDockWidget(self.panels["values"], dock)
                dock.hide()
            self._extension_panels[key] = dock

    def _build_extension_panel(self, dock) -> None:
        """Its content, made by the extension the first time it is seen."""
        if dock.built:
            return
        dock.built = True
        try:
            content = dock.entry.function(self)
        except Exception as error:                     # noqa: BLE001 (an extension that fails does not close Tensela)
            import traceback
            traceback.print_exc()
            content = QLabel(tr('«{label}» failed: {error}').format(label=tr(dock.entry.label),
                                                                   error=f"{type(error).__name__}: {error}"))
            content.setWordWrap(True)
            content.setAlignment(Qt.AlignmentFlag.AlignTop)
        dock.content = content
        dock.panel.body.addWidget(content)

    def show_extension_panel(self, title: str, extension: str | None = None):
        """Opens (and brings to the front) the panel `title` of an extension; its content, or None."""
        self._sync_extension_panels()
        dock = next((d for (ext_id, label), d in self._extension_panels.items()
                     if label == title and extension in (None, ext_id)), None)
        if dock is None:
            return None
        dock.show()
        dock.raise_()
        self._build_extension_panel(dock)
        return dock.content

    def _tell_extensions(self, event: str, *args, only: str | None = None) -> None:
        """What happened, to the extensions that hear it (one that fails is said in the status bar, once)."""
        from .. import extensions as E
        for ext_id, function in E.listeners(event):
            if only is not None and ext_id != only:
                continue
            try:
                function(self, *args)
            except Exception as error:                 # noqa: BLE001 (an extension that fails does not close Tensela)
                import traceback
                traceback.print_exc()
                self.statusBar().showMessage(tr('The extension «{name}» failed: {error}').format(
                    name=ext_id, error=f"{type(error).__name__}: {error}"), 10000)

    def _run_extension_export(self, entry) -> None:
        """A way of exporting of an extension: what the view shows, to the file chosen."""
        p = self.project
        if not p or not p.export:
            self.statusBar().showMessage(tr('Nothing to export: turn on “Show in 3D” on a node.'))
            return
        if not self._wait_for_calculation():
            return
        objects = p.visible_objects(computed_only=True)
        suffix = entry.suffix if entry.suffix.startswith(".") else "." + entry.suffix
        suggested = str(self.filepath.with_suffix(suffix)) if self.filepath else "project" + suffix
        filepath, _ = QFileDialog.getSaveFileName(self, tr(entry.label).replace("&", "").rstrip("…"), suggested,
                                                  f"*{suffix}")
        if not filepath:
            return
        if not filepath.lower().endswith(suffix.lower()):
            filepath += suffix
        try:
            self._aside(tr('Exporting…'), lambda: entry.function(filepath, objects))
        except Exception as error:                     # noqa: BLE001 (said, not lost)
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, tr('Could not export'), f"{type(error).__name__}: {error}")
            return
        self.statusBar().showMessage(tr('Exported: {path}').format(path=filepath))

    def _menu_help(self) -> None:
        """Help: the manual (the one that comes with Tensela, without internet), the part about the chosen node (F1),
        the shortcuts, and the links of the project, which open the browser only when chosen."""
        from . import help as module_help
        menu = self.menuBar().addMenu(tr('&Help'))

        def item(text, function, shortcut=None, tip=None):
            a = QAction(tr(text), self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setStatusTip(tr(tip))
            a.triggered.connect(function)
            menu.addAction(a)
            self.addAction(a)
            return a

        item('&Manual (offline)', lambda: module_help.open_url(module_help.manual_url()),
             tip='The manual that comes with Tensela: it opens in your browser, without internet')
        item('Manual at &tensela.com', lambda: module_help.open_url(module_help.online_manual()),
             tip='The manual online: always up to date, with the interactive map of the nodes')
        item('Help for the chosen &node', self.help_node, "F1",
             'The part of the manual about the chosen node (with none chosen, the list of all the nodes)')
        item('&Keyboard shortcuts', lambda: self.open_preferences("Interaction"))
        menu.addSeparator()
        item('Download the manual (&PDF)', lambda: module_help.open_url(module_help.LINKS["pdf"]()))
        item('&Community', lambda: module_help.open_url(module_help.LINKS["community"]()),
             tip='Questions, ideas and what others make with Tensela')
        item('&Report a problem or send a comment', lambda: module_help.open_url(module_help.LINKS["report"]()),
             tip='Opens the page to write it; nothing is sent by itself')
        menu.addSeparator()
        item('&Support Tensela', lambda: module_help.open_url(module_help.LINKS["donate"]()))
        item('&About Tensela', self.about)

    def help_node(self) -> None:
        """The part of the manual about the chosen node; with none chosen, the page of all the nodes."""
        from . import help as module_help
        names = self._selected_names() if self.project is not None else []
        kind = None
        if names and self.project is not None and names[0] in self.project.graph.nodes:
            kind = self.project.graph.nodes[names[0]].kind
        elif self._selection and self.project is not None and self._selection in self.project.graph.nodes:
            kind = self.project.graph.nodes[self._selection].kind
        if kind is None:
            module_help.open_url(module_help.manual_url("nodes"))
            return
        page, heading = module_help.node_place(kind)
        module_help.open_url(module_help.manual_url(page, heading))

    def about(self) -> None:
        from . import help as module_help
        self._display_dialog(module_help.DialogAbout(self, app_icon()))

    def _apply_preferences(self) -> None:
        """The saved preferences that are not the theme (the view's navigation, the canvas background)."""
        from . import editor as module_editor
        settings = QSettings()
        self.viewer.put_navigation(settings.value("preferences/navigation", "tensela"))
        self.viewer._browser.towards_pointer = settings.value("preferences/zoom", "pointer") != "centre"
        module_editor.DEPTH_CANVAS = settings.value("preferences/canvas_background", "dots")
        tones = (settings.value("preferences/canvas_tone", "theme"), settings.value("preferences/view_tone", "theme"))
        if tones != (theme.TONE["canvas"], theme.TONE["view"]):
            theme.put_tones(*tones)
            self.viewer.put_background(theme.color_view())
        old = {"imperial": "ft-in"}.get(settings.value("preferences/units", "metric"), "m")
        unit = settings.value("preferences/length_unit", old)
        decimals = settings.value("preferences/decimals", "auto")
        decimals = None if decimals in (None, "auto") else int(decimals)
        fraction = int(settings.value("preferences/fraction", 16))
        if (unit, decimals, fraction) != (values.UNIT, values.DECIMALS, values.FRACTION):
            # The lengths are written again in the other unit.
            values.UNIT, values.DECIMALS, values.FRACTION = unit, decimals, fraction
            for box in self.editor.boxes.values():
                box.refresh()
            if self.project is not None:
                self._create_controls()
                self._display_node(self._selection)
        self.editor.apply_theme()

    def open_preferences(self, section: str | None = None) -> None:
        """Preferences by sections (open at `section`, if given); each change is applied at once
        (`apply_preference`)."""
        a = QSettings()
        from . import desktop
        old = {"imperial": "ft-in"}.get(a.value("preferences/units", "metric"), "m")
        values = {
            "preferences/language": a.value("preferences/language", language.system_language()),
            "_current_language": language.LANGUAGE,
            "theme/mode": a.value("theme/mode", "system"), "theme/name": a.value("theme/name", theme.DEFAULT_BY),
            "view/style": a.value("view/style", "solid"), "view/axes": self._button_axes.isChecked(),
            "preferences/canvas_background": a.value("preferences/canvas_background", "dots"),
            "preferences/canvas_tone": a.value("preferences/canvas_tone", "theme"),
            "preferences/view_tone": a.value("preferences/view_tone", "theme"),
            "canvas/guides": self._action_items["guides"].isChecked(), "canvas/grid": self._action_items["grid"].isChecked(),
            "preferences/length_unit": a.value("preferences/length_unit", old),
            "preferences/decimals": str(a.value("preferences/decimals", "auto")),
            "preferences/fraction": int(a.value("preferences/fraction", 16)),
            "preferences/navigation": a.value("preferences/navigation", "tensela"),
            "preferences/zoom": a.value("preferences/zoom", "pointer"),
            "preferences/location": a.value("preferences/location", "Madrid"),
            "_locations": list(sun_module.CITIES) + [sun_module.OTHER],
            "preferences/latitude": a.value("preferences/latitude", 40.42),
            "preferences/longitude": a.value("preferences/longitude", -3.70),
            "preferences/time_zone": a.value("preferences/time_zone", 1.0),
            "_styles": list(STYLE_NAMES.items()), "_schemes": list(navigation.NAMES.items()),
            "_scheme_help": navigation.HELP_TEXTS,
            "_section": section,
            "start/show": a.value("start/show", True, type=bool),
            "compute/what": a.value("compute/what", "seen"),
            "_desktop_image": str(desktop.appimage()) if desktop.appimage() else None,
            "_desktop_installed": desktop.installed_for() is not None,
            "_desktop_for": desktop.installed_for(),
            "_desktop_put": self.put_in_menu,
        }
        from .code_editor import settings as code_settings
        values.update({f"code/{k}": v for k, v in code_settings().items()})
        themes = [(k, theme.load(k, "light")["name"]) for k in theme.themes()]
        shortcuts = [(key, action.text(), action.shortcut().toString(), self._factory_shortcuts[key])
                  for key, action in self._action_items_with_shortcut().items()]
        self._display_dialog(DialogPreferences(self, values, self.apply_preference, themes, shortcuts))

    def apply_preference(self, key: str, value) -> None:
        """Saves a preference and puts it in action."""
        QSettings().setValue(key, value)
        QSettings().sync()
        if key == "preferences/language":
            if value != language.LANGUAGE:
                QTimer.singleShot(0, self._offer_restart)
        elif key == "theme/mode":
            self.put_theme(mode=value)
        elif key == "theme/name":
            self.put_theme(name=value)
        elif key == "view/style":
            self.put_style_name_view(value)
        elif key == "view/axes":
            self._button_axes.setChecked(bool(value))
        elif key in ("canvas/guides", "canvas/grid"):
            self._action_items[key.split("/")[1]].setChecked(bool(value))
        elif key == "compute/what":
            self._look_again()
        elif key.startswith("code/"):           # the editor of the Code node, if it is open
            if self._code_dialog is not None and self._code_dialog.isVisible():
                self._code_dialog.restyle()
        elif key.startswith("shortcuts/"):
            action = self._action_items_with_shortcut().get(key.split("/", 1)[1])
            if action is not None:
                action.setShortcut(QKeySequence(value))
        else:                                   # canvas background, units, mouse
            self._apply_preferences()

    def _action_items_with_shortcut(self) -> dict:
        """The actions with a keyboard shortcut, by a key that does not change: their factory shortcut."""
        return dict(self._record_shortcuts)

    def _register_shortcuts(self) -> None:
        """Takes note of the factory shortcuts and sets those the user changed (Preferences → Interaction)."""
        self._record_shortcuts, self._factory_shortcuts = {}, {}
        for action in self.findChildren(QAction):
            shortcut = action.shortcut().toString()
            if shortcut and action.text() and shortcut not in self._record_shortcuts:
                self._record_shortcuts[shortcut] = action
                self._factory_shortcuts[shortcut] = shortcut
        settings = QSettings()
        for key, action in self._record_shortcuts.items():
            own = settings.value(f"shortcuts/{key}")
            if own is not None:
                action.setShortcut(QKeySequence(own))

    def _menu_matcap(self, menu: QMenu) -> None:
        """Below the styles: the material of the Matcap, each with its picture (on choosing it, the view goes to
        Matcap): Tensela's and the user's own, read again each time the menu opens (a new one in the folder
        appears without reopening)."""
        sub = menu.addMenu(tr('Matcap material'))
        sub.setObjectName("matcaps")
        sub.aboutToShow.connect(lambda: self._fill_matcaps(sub))
        self._fill_matcaps(sub)

    _thumbnails: dict = {}

    def _fill_matcaps(self, sub: QMenu) -> None:
        from .matcaps import MATCAPS, image_of, own
        sub.clear()
        group = QActionGroup(sub)
        current = QSettings().value("view/matcap", "plaster")

        def add(key: str, text: str, stamp: float = 0.0) -> None:
            try:
                picture = self._thumbnails.get((key, stamp))
                if picture is None:
                    picture = self._thumbnails[(key, stamp)] = _thumbnail(image_of(key))
            except (ShapeError, OSError) as error:            # a file that is not an image: said, not chosen
                a = sub.addAction(tr('{name} (cannot be read)').format(name=text))
                a.setEnabled(False)
                a.setToolTip(str(error))
                return
            a = QAction(picture, text, sub, checkable=True, checked=(key == current))
            a.triggered.connect(lambda _=False, k=key: self.put_matcap(k))
            group.addAction(a)
            sub.addAction(a)
        for key, text in MATCAPS.items():
            add(key, tr(text))
        mine = own()
        if mine:
            sub.addSection(tr('Your own'))
            for key, path in mine.items():
                add(key, path.stem, path.stat().st_mtime)
        sub.addSeparator()
        sub.addAction(tr('Open the matcaps folder'), self.open_matcaps)
        sub.setToolTipsVisible(True)

    def open_matcaps(self) -> None:
        """The folder of the own matcaps (made, if it was not there): put a picture of a sphere in it (PNG, JPG,
        EXR…) and it appears in the menu."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from .matcaps import folder
        where = folder()
        try:
            where.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._warn(str(error))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(where)))
        self.statusBar().showMessage(tr('Put pictures of a sphere here (PNG, JPG, EXR…): they appear in the Matcap '
                                        'menu by their name.'), 10000)

    def put_matcap(self, key: str) -> None:
        QSettings().setValue("view/matcap", key)
        self.viewer.put_matcap(key)
        if self.viewer.style_name != "matcap":
            self.put_style_name_view("matcap")
        else:
            self._show_style("matcap")            # the button says the new material

    @staticmethod
    def _matcap_name(key: str) -> str:
        """The name of a matcap's material as the menu writes it: Plaster, Clay… or the file's name (own ones)."""
        from .matcaps import MATCAPS, OWN
        key = str(key)
        if key.startswith(OWN):
            return Path(key[len(OWN):]).stem
        return tr(MATCAPS.get(key, 'Plaster'))

    def put_style_name_view(self, key: str) -> None:
        """Studio, model, matcap, wireframe, hidden lines, x-ray or occlusion: for this project (saved with it), and
        the one a new project starts with."""
        key = key if key in STYLE_NAMES else "solid"
        QSettings().setValue("view/style", key)
        if self.project is not None and self.project.look.get("style") != key:
            self.project.look["style"] = key
            self._modified_look()
        self._show_style(key)

    def _modified_look(self) -> None:
        """The look of the view changed: the project has changes to save (it is not undone)."""
        if not self.modified:
            self.modified = True
            self._title()

    def _show_style(self, key: str) -> None:
        """Paints the view in that style and marks it in the menus (without remembering anything)."""
        key = key if key in STYLE_NAMES else "solid"
        if self.viewer.style_name != key:
            self.viewer.put_style_name(key)
        if getattr(self, "_button_style_name", None) is not None:
            text = tr(STYLE_NAMES[key])
            if key == "matcap":                  # with its material: a coloured one tints every model
                text += " · " + self._matcap_name(QSettings().value("view/matcap", "plaster"))
            self._button_style_name.setText(f"{text}  ▾")
        if key in getattr(self, "_action_items_style_name", {}):
            self._action_items_style_name[key].setChecked(True)

    def put_outlines(self, yes: bool) -> None:
        """The thin lines at the edges in Studio and Model: for this project (saved with it), and for the new ones."""
        QSettings().setValue("view/outlines", bool(yes))
        if self.project is not None and self.project.look.get("outlines") != bool(yes):
            self.project.look["outlines"] = bool(yes)
            self._modified_look()
        self._show_outlines(yes)

    def _show_outlines(self, yes: bool) -> None:
        if self.viewer.outlines != bool(yes):
            self.viewer.put_outlines(yes)
        if getattr(self, "_action_outlines", None) is not None:
            self._action_outlines.setChecked(bool(yes))

    def _add_outlines_action(self, menu) -> QAction:
        """The switch of the outlines, under the styles."""
        menu.addSeparator()
        action = QAction(tr('Outlines'), menu, checkable=True, checked=self.viewer.outlines)
        action.setStatusTip(tr('Thin lines at the edges of each object and of each panel (Studio and Model)'))
        action.setToolTip(action.statusTip())
        action.triggered.connect(self.put_outlines)
        menu.addAction(action)
        return action

    def _recover_layout(self) -> None:
        """The panels where they were left last time (if the layout is of this version)."""
        settings = QSettings()
        # Only the size and whether it was maximised: on Wayland, restoring the whole geometry added the
        # desktop's frame each time, and the window grew on opening and closing.
        size_ = settings.value("window/size")
        if isinstance(size_, (list, tuple)) and len(size_) == 2:
            self.resize(int(size_[0]), int(size_[1]))
        if settings.value("window/maximized", False, type=bool):
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        state = settings.value("window/layout")
        if state is not None:
            self.restoreState(state, VERSION_LAYOUT)

    def _factory_measures(self) -> None:
        """The panels on the right, 430 px wide; the canvas, 400 high and all across."""
        self.resizeDocks([self.panels["values"]], [430], Qt.Orientation.Horizontal)
        self.resizeDocks([self.panels["nodes"]], [max(600, self.width() - 450)], Qt.Orientation.Horizontal)
        self.resizeDocks([self.panels["nodes"]], [400], Qt.Orientation.Vertical)
        self.resizeDocks([self.panels[c] for c in ("values", "node", "data")], [330, 330, 260],
                         Qt.Orientation.Vertical)

    def _factory_place(self) -> None:
        """The canvas at the bottom; Values, Node and Data on the right, one above the other."""
        for panel in self.panels.values():
            panel.return_()
            panel.setFloating(False)
            self.removeDockWidget(panel)        # loose from their groups and sides: if not, Qt leaves them where they were
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.panels["nodes"])
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.panels["values"])
        self.splitDockWidget(self.panels["values"], self.panels["node"], Qt.Orientation.Vertical)
        self.splitDockWidget(self.panels["node"], self.panels["data"], Qt.Orientation.Vertical)
        self.tabifyDockWidget(self.panels["values"], self.panels["sketch"])   # Croquis, junto a Valores
        self.tabifyDockWidget(self.panels["values"], self.panels["library"])  # the Library, too
        for key, panel in self.panels.items():
            # Croquis and the Library, closed until they are asked for (Ctrl+K, Ctrl+Alt+L or View → Panels).
            panel.setVisible(key not in ("sketch", "library"))
        self.panels["values"].raise_()
        self._factory_measures()

    def factory_layout(self) -> None:
        self._factory_place()

    # --- Workspaces: named layouts of the panels --------------------

    def spaces(self) -> list[str]:
        settings = QSettings()
        settings.beginGroup("workspaces")
        names = sorted(settings.childKeys(), key=str.casefold)
        settings.endGroup()
        return names

    def save_space(self, name: str) -> None:
        """Where each panel is now, with a name (those taken out to another window, in their place)."""
        for panel in self.panels.values():
            panel.return_()
        QSettings().setValue(f"workspaces/{name}", self.saveState(VERSION_LAYOUT))

    def put_space(self, name: str) -> bool:
        state = QSettings().value(f"workspaces/{name}")
        if state is None:
            return False
        for panel in self.panels.values():
            panel.return_()
        return self.restoreState(state, VERSION_LAYOUT)

    def delete_space(self, name: str) -> None:
        QSettings().remove(f"workspaces/{name}")

    def _fill_spaces(self) -> None:
        menu = self._menu_spaces
        menu.clear()
        names = self.spaces()
        for name in names:
            menu.addAction(name, lambda n=name: self.put_space(n))
        if names:
            menu.addSeparator()
        menu.addAction(tr('Save current as…'), self._space_ask_name)
        if names:
            delete = menu.addMenu(tr('Delete'))
            for name in names:
                delete.addAction(name, lambda n=name: self.delete_space(n))
        menu.addSeparator()
        menu.addAction(tr('&Factory layout'), self.factory_layout)

    def _space_ask_name(self) -> None:
        name, ok = ask_text(self, tr('Save workspace'), tr('Name (for example: Model, Present):'))
        name = name.strip().replace("/", "-")
        if not ok or not name:
            return
        if name in self.spaces() and QMessageBox.question(
                self, tr('Save workspace'),
                tr('There is already one called “{name}”. Replace it?').format(name=name)) != QMessageBox.StandardButton.Yes:
            return
        self.save_space(name)
        self.statusBar().showMessage(tr('Workspace “{name}” saved: it is in View → Workspaces.')
                                     .format(name=name), 5000)

    def _tools(self) -> None:
        """The icon-only buttons of the headers of the 3D view and of the canvas: the usual, at hand."""
        a = {**self._action_items, **self._action_items_edit}

        def button(card, icon, help, action=None, function=None):
            shortcut = text_shortcut(action.shortcut()) if action is not None else ""
            b = card.action(button_icon(icon, f"{tr(help)} ({shortcut})" if shortcut else help,
                                           checkable=bool(action and action.isCheckable())))
            if action is not None and action.isCheckable():
                b.setChecked(action.isChecked())
                b.toggled.connect(action.setChecked)
                action.toggled.connect(b.setChecked)
            else:
                b.clicked.connect(action.trigger if action is not None else function)
            return b

        # The style of the view: a button with its name and a menu (without an icon: it is a choice, not a command).
        style_name = QToolButton()
        style_name.setObjectName("menu_button")
        style_name.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        style_name.setToolTip(tr('How the 3D view is drawn'))
        menu = QMenu(style_name)
        group = QActionGroup(menu)
        self._action_items_style_name: dict[str, QAction] = {}
        saved = QSettings().value("view/style", "solid")
        for key, text in STYLE_NAMES.items():
            action = QAction(tr(text), menu, checkable=True, checked=(key == saved))
            action.setStatusTip(tr(HELP_TEXTS_STYLE_NAME[key]))
            action.setToolTip(tr(HELP_TEXTS_STYLE_NAME[key]))
            action.triggered.connect(lambda _=False, k=key: self.put_style_name_view(k))
            group.addAction(action)
            menu.addAction(action)
            self._action_items_style_name[key] = action
        self._menu_matcap(menu)
        self._action_outlines = self._add_outlines_action(menu)
        saved_outlines = QSettings().value("view/outlines", True, type=bool)
        self._show_outlines(self.project.look.get("outlines", saved_outlines) if self.project is not None
                            else saved_outlines)
        menu.setToolTipsVisible(True)
        style_name.setMenu(menu)
        self._button_style_name = style_name
        self.card_view.action(style_name)
        self.viewer.put_matcap(QSettings().value("view/matcap", "plaster"))
        self._show_style(self.project.look.get("style", saved) if self.project is not None else saved)
        # Perspective or parallel (orthographic), in view: a button with its name, like the style. Key 5, as
        # on a numeric keypad. Remembered.
        projection = QToolButton()
        projection.setObjectName("menu_button")
        projection.setCheckable(True)
        projection.setToolTip(tr('Perspective or parallel (orthographic), as in a drawing (key 5)'))
        projection.setShortcut(QKeySequence("5"))

        def put_projection(parallel: bool) -> None:
            self.viewer.parallel_put(parallel)
            projection.setText(tr('Parallel') if parallel else tr('Perspective'))
            QSettings().setValue("view/parallel", parallel)

        projection.toggled.connect(put_projection)

        def projection_from__view(parallel: bool) -> None:   # key 5 of the numeric keypad, in the view
            if projection.isChecked() != parallel:
                projection.setChecked(parallel)
        self.viewer.projection_changed.connect(projection_from__view)
        parallel_saved = QSettings().value("view/parallel", False, type=bool)
        projection.setChecked(parallel_saved)
        put_projection(parallel_saved)
        self._button_projection = projection
        self.card_view.action(projection)
        # The views: a menu with its icon (front, back, sides, plan, bottom, isometric).
        views = QToolButton()
        views.setObjectName("menu_button")
        views.setText(tr('Views') + "  ▾")
        views.setToolTip(tr('Look from the front, a side, above, below, or isometric'))
        views.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_views = QMenu(views)
        for text, icon, view, opposite, shortcut in (
                ('Front (south)', "from_south", "front", False, "1"), ('Back (north)', "from_north", "front", True, ""),
                ('Right (east)', "from_east", "right", False, "3"), ('Left (west)', "from_west", "right", True, ""),
                ('Plan (top)', "from_above", "plan", False, "7"), ('Bottom', "from_below", "plan", True, "")):
            action = menu_views.addAction(icons.icon(icon, theme.color("text", "#e6e7ec")), tr(text))
            if shortcut:
                action.setToolTip(tr('Numpad key {key_name}').format(key_name=shortcut))
            action.triggered.connect(lambda _=False, v=view, o=opposite: self.viewer.look(v, o))
        menu_views.addSeparator()
        iso = menu_views.addAction(icons.icon("isometric", theme.color("text", "#e6e7ec")), tr('Isometric'))
        iso.triggered.connect(self.viewer.isometric)
        menu_views.setToolTipsVisible(True)
        views.setMenu(menu_views)
        self.card_view.action(views)
        # The button says which view one is in («Front ▾»); turning by hand, «Views» again.
        self.viewer.view_changed.connect(lambda name: views.setText(
            (tr('Views') if name == 'Free' else tr(name)) + "  ▾"))
        button(self.card_view, "frame_all", 'Frame all', a["frame_all"])
        axes = button(self.card_view, "axes", 'Show or hide the axes', function=lambda: None)
        axes.setCheckable(True)
        axes.setChecked(QSettings().value("view/axes", True, type=bool))
        self.viewer.display_axes(axes.isChecked())
        axes.toggled.connect(lambda yes: (QSettings().setValue("view/axes", yes), self.viewer.display_axes(yes)))
        self._button_axes = axes
        button(self.card_view, "image", 'Export image (Ctrl+Shift+E)', function=self._ask_image)
        button(self.card_view, "croquis", 'Freehand sketch (Ctrl+K)', function=self._sketch)
        button(self.card_nodes, "search", 'Find a node', a["search"])
        # The eyes of several nodes at once: a button with its menu.
        eyes = button_icon("eye", 'Show and hide nodes in the 3D view')
        eyes.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_eyes = QMenu(eyes)
        for key in ("see_only", "hide_selected", None, "see_all", "hide_all"):
            if key is None:
                menu_eyes.addSeparator()
            else:
                menu_eyes.addAction(a[key])
        eyes.setMenu(menu_eyes)
        eyes.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.card_nodes.action(eyes)
        button(self.card_nodes, "arrange", 'Arrange the nodes', a["arrange"])
        button(self.card_nodes, "frame_all", 'Frame the nodes', a["frame_nodes"])
        button(self.card_nodes, "guides", 'Smart guides: align with the other boxes while moving them', a["guides"])
        button(self.card_nodes, "grid", 'Snap to grid', a["grid"])
        button(self.card_nodes, "export", 'Export the nodes as an image (PNG or SVG)',
              function=self._export_nodes)

    def put_theme(self, name: str | None = None, mode: str | None = None) -> None:
        """The theme (Sober, Vivid…) and the mode (light, dark or like the system); remembered."""
        settings = QSettings()
        name = name or settings.value("theme/name", theme.DEFAULT_BY)
        mode = mode or settings.value("theme/mode", "system")
        settings.setValue("theme/name", name)
        settings.setValue("theme/mode", mode)
        tk = theme.apply(QApplication.instance(), name, None if mode == "system" else mode)
        self.editor.apply_theme()
        self.viewer.put_background(theme.color_view(tk))

    def _title(self) -> None:
        name = self.filepath.name if self.filepath else (tr('untitled') if self.project else tr('no project'))
        self.setWindowTitle(f"{'* ' if self.modified else ''}{name} — Tensela")
        i = self.tabs.currentIndex()
        if 0 <= i < len(self.documents):
            self.tabs.setTabText(i, (self.filepath.stem if self.filepath else tr('untitled')) + ("  •" if self.modified else ""))
            self.tabs.setTabToolTip(i, str(self.filepath) if self.filepath else tr('Not saved yet'))

    # --- Tabs: several open projects -----------------------------------------

    def _document(self) -> dict:
        """What is needed to come back to this project as it is."""
        if self.project is not None:
            self._collect_canvas()
        return {"project": self.project, "path": self.filepath, "modified": self.modified,
                "undo": self._undo, "redo": self._redo, "state": self._state,
                "selection": self._selection, "camera": self.viewer.view.camera_position,
                "canvas": (self.editor.transform(), self.editor.mapToScene(self.editor.viewport().rect().center()))}

    def _save_tab(self) -> None:
        i = getattr(self, "_current_tab", -1)
        if 0 <= i < len(self.documents) and self.documents[i] is not None:
            self.documents[i] = self._document()

    def _to_tab(self, i: int) -> None:
        """It goes to tab `i`: how the previous one was left is saved and this one is set."""
        if getattr(self, "_changing_tabs", False) or not 0 <= i < len(self.documents):
            return
        self.finish_drawing()
        self._save_tab()
        self._isolated = None                    # the isolated one was of the other project
        self.isolated_strip.hide()
        self._inside = None                     # the other project is reached from outside the groups
        self._mark_inside()
        self._current_tab = i
        d = self.documents[i]
        self.project, self.filepath, self.modified = d["project"], d["path"], d["modified"]
        self._undo, self._redo, self._state = d["undo"], d["redo"], d["state"]
        self._last_change = ("", 0.0)
        self._selection = None
        self.panel_node.display(None)
        self.viewer.clean()
        self.editor.display(self.project.graph, self.project.positions, frame=False,
                            thumbnails=self.project.thumbnails, notes=self.project.notes)
        self._create_controls()
        # Its own look: the one saved with it; if it has none, the last one chosen, fixed now for this project (a
        # change in another tab does not reach it). Before computing and drawing.
        look = self.project.look
        look.setdefault("style", QSettings().value("view/style", "solid"))
        look.setdefault("outlines", QSettings().value("view/outlines", True, type=bool))
        self._show_style(look["style"])
        self._show_outlines(look["outlines"])
        self.recompute()
        if d.get("camera") is not None:
            self.viewer.view.camera_position = d["camera"]
            self.viewer.view.render()
        else:
            self.viewer.frame(fresh=True)
            self.editor.frame()
        if d.get("canvas") is not None:              # the node canvas, where it was in this tab
            transformation, centre = d["canvas"]
            self.editor.setTransform(transformation)
            self.editor.centerOn(centre)
        self._title()
        self._show_library()
        self._tell_extensions("project")

    def _moved_tab(self, from_: int, to: int) -> None:
        self.documents.insert(to, self.documents.pop(from_))
        self._current_tab = self.tabs.currentIndex()

    def _new_tab(self, project: Project, filepath: Path | None, reuse_empty: bool = True) -> None:
        """A project in a new tab (or in the current one, if it is empty and without changes, and `reuse_empty`)."""
        i = self.tabs.currentIndex()
        empty = (reuse_empty and 0 <= i < len(self.documents) and not self.modified and self.filepath is None
                 and self.project is not None and not self.project.graph.nodes)
        self._save_tab()
        doc = {"project": project, "path": filepath, "modified": False, "undo": [], "redo": [],
               "state": to_text(project), "selection": None, "camera": None}
        self._changing_tabs = True
        if empty:
            self.documents[i] = doc
        else:
            self.documents.append(doc)
            i = self.tabs.addTab("")
            dismiss = self.tabs.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if dismiss is not None:           # Qt's is 16 px and the X was tiny
                dismiss.setFixedSize(28, 20)            # 20 of button and 8 of margin
        self._changing_tabs = False
        self._tabs_row.setVisible(True)
        self._current_tab = -1          # do not save on top: the new one is already set
        self.tabs.setCurrentIndex(i)
        self._to_tab(i)

    def dismiss_tab(self, i: int | None = None) -> bool:
        """Closes a project (it asks if it has changes). If it was the last, a new empty one remains."""
        i = self.tabs.currentIndex() if i is None else i
        if not 0 <= i < len(self.documents):
            return False
        if i != self.tabs.currentIndex():
            self.tabs.setCurrentIndex(i)
        if not self._follow_without_save():
            return False
        self._changing_tabs = True
        self.documents.pop(i)
        self.tabs.removeTab(i)
        self._changing_tabs = False
        self._current_tab = -1
        if not self.documents:
            self._new_tab(Project(Graph()), None)
        else:
            self._to_tab(self.tabs.currentIndex())
        return_memory()
        return True

    def _menu_tab(self, point) -> None:
        """Right click on a tab: close it (or the others), save, rename, duplicate, find it in its folder."""
        i = self.tabs.tabAt(point)
        if not 0 <= i < len(self.documents):
            return
        if i != self.tabs.currentIndex():
            self.tabs.setCurrentIndex(i)
        path = self.filepath
        menu = QMenu(self)
        menu.addAction(tr('Close')).triggered.connect(lambda: self.dismiss_tab(i))
        others = menu.addAction(tr('Close the others'))
        others.setEnabled(self.tabs.count() > 1)
        others.triggered.connect(lambda: self._close_tabs(keep=i))
        right = menu.addAction(tr('Close those to the right'))
        right.setEnabled(i < self.tabs.count() - 1)
        right.triggered.connect(lambda: self._close_tabs(keep=i, only_right=True))
        menu.addAction(tr('Close all')).triggered.connect(lambda: self._close_tabs())
        menu.addSeparator()
        menu.addAction(tr('Save')).triggered.connect(self.save)
        menu.addAction(tr('Save as…')).triggered.connect(self.save_as)
        rename = menu.addAction(tr('Rename file…'))
        rename.setEnabled(path is not None)
        rename.triggered.connect(self._rename_file)
        menu.addAction(tr('Duplicate')).triggered.connect(self._duplicate_tab)
        menu.addSeparator()
        folder = menu.addAction(tr('Show in its folder'))
        folder.setEnabled(path is not None)
        folder.triggered.connect(self._show_in_folder)
        copy = menu.addAction(tr('Copy its path'))
        copy.setEnabled(path is not None)
        copy.triggered.connect(lambda: QApplication.clipboard().setText(str(path)))
        menu.exec(self.tabs.mapToGlobal(point))

    def _close_tabs(self, keep: int | None = None, only_right: bool = False) -> None:
        """Closes several tabs (each one asks if it has changes; «Cancel» stops there)."""
        kept = self.documents[keep] if keep is not None else None
        for doc in list(reversed(self.documents)):
            if doc is kept:
                if only_right:
                    break
                continue
            if doc not in self.documents:
                continue
            if not self.dismiss_tab(self.documents.index(doc)):
                return
        if kept is not None and kept in self.documents:
            self.tabs.setCurrentIndex(self.documents.index(kept))

    def _rename_file(self) -> None:
        """Renames the file of this project on disk (in its same folder)."""
        if self.filepath is None:
            return
        old = Path(self.filepath)
        name, ok = ask_text(self, tr('Rename file'), tr('New name:'), text=old.stem)
        name = name.strip()
        if not ok or not name or name == old.stem:
            return
        if "/" in name or "\\" in name or name in (".", ".."):
            QMessageBox.warning(self, tr('Rename file'), tr('The name of a file cannot have “/” nor “\\”.'))
            return
        new = old.with_name(name if name.endswith(EXTENSIONS) else name + (old.suffix or EXTENSION))
        if new.exists():
            QMessageBox.warning(self, tr('Rename file'), tr('There is already a file called “{name}” there.').format(
                name=new.name))
            return
        try:
            old.rename(new)
        except OSError as error:
            QMessageBox.warning(self, tr('Rename file'), str(error))
            return
        self.filepath = new
        self.documents[self.tabs.currentIndex()]["path"] = new
        self._remember(new)
        self._title()
        self.statusBar().showMessage(tr('Renamed: {path}').format(path=new))

    def _duplicate_tab(self) -> None:
        """A copy of this project, as it is now, in a new tab (not saved yet)."""
        self._collect_canvas()
        copy = from__text(self._snapshot())
        copy.look = dict(self.project.look)
        self._new_tab(copy, None)
        self.modified = True
        self._title()

    def _show_in_folder(self) -> None:
        if self.filepath is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.filepath).parent)))

    def _to_tab_next(self, step: int = 1) -> None:
        if self.tabs.count() > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    # --- Undo and redo --------------------------------------------------------

    def _snapshot(self) -> str:
        """The whole project as text, with the boxes where they are now."""
        self._collect_canvas()
        return to_text(self.project)

    def _register(self, key: str = "") -> None:
        """After a change: the previous snapshot goes to the undo list.

        Several changes in a row of the same slider (or of moving boxes) count as one, so one does not have to undo each
        millimetre.
        """
        snapshot = self._snapshot()
        if snapshot == self._state:
            return
        now = time.monotonic()
        followed = key and self._last_change[0] == key and now - self._last_change[1] < 1.5
        if not followed:
            self._undo.append(self._state)
            del self._undo[:-100]
        self._redo.clear()
        self._state = snapshot
        self._last_change = (key, now)
        self._mark_modified()

    def edit_project(self, change, what: str = "") -> bool:
        """For the extensions: `change(project)` changes a copy of the open project; if it does not fail, the copy
        takes its place as one step that Ctrl+Z undoes, and it is computed (`what`, if given, is said in the status
        bar). If it fails, nothing changed and its error goes on. Whether something changed."""
        if self.project is None:
            return False
        before = self._snapshot()
        copy = from__text(before)
        change(copy)
        after = to_text(copy)
        if after == before:
            return False
        self._undo.append(before)
        del self._undo[:-100]
        self._redo.clear()
        if what:                                     # said when it has been computed (not covered by «Recalculated»)
            self._say_after = tr('{what}. Ctrl+Z undoes it.').format(what=what)
        self._restore(after)
        return True

    def undo(self) -> None:
        if not self._undo:
            self.statusBar().showMessage(tr('Nothing to undo.'))
            return
        self._redo.append(self._state)
        self._restore(self._undo.pop())
        self.statusBar().showMessage(tr('Undone.'))

    def redo(self) -> None:
        if not self._redo:
            self.statusBar().showMessage(tr('Nothing to redo.'))
            return
        self._undo.append(self._state)
        self._restore(self._redo.pop())
        self.statusBar().showMessage(tr('Redone.'))

    def _restore(self, snapshot: str) -> None:
        drawing = self._drawing                     # undoing a point while drawing: drawing goes on
        self.finish_drawing()
        inside = [dict(d) for d in self._levels]
        self._inside = None
        look = dict(self.project.look) if self.project is not None else {}
        self.project = from__text(snapshot)
        self.project.look = look                     # the look of the view is not undone: it stays as it is
        self._state = snapshot
        self._last_change = ("", 0.0)
        self.editor.display(self.project.graph, self.project.positions, frame=False,
                            thumbnails=self.project.thumbnails, notes=self.project.notes)
        self._create_controls()
        self._mark_inside()
        self.recompute()
        self._display_node(self._selection)
        self._mark_modified()
        if inside:                                  # something inside was undone: back in, level by level
            for d in inside:
                g = self._canvas
                if d["node"] not in g.nodes or g.nodes[d["node"]].kind.name != d["type"]:
                    break
                self.enter_group(d["node"], view=d["view"], frame=False)
        elif drawing is not None and drawing in self.project.graph.nodes \
                and (drawable(self.project.graph.nodes[drawing])
                     or self.project.graph.nodes[drawing].kind.name in ('Edit mesh', 'Equilibrium')):
            self.draw(drawing)

    def _mark_modified(self) -> None:
        if not self.modified:
            self.modified = True
            self._title()
        self._show_library()

    def _show_library(self, reread: bool = False) -> None:
        """The Library panel, up to date: the project's groups (they change with the project) and those of the
        library (read again when it changes: `reread`)."""
        from .. import library as library
        from ..nodes import CATALOG
        from .library_panel import summary
        if reread or not self._library_groups:
            try:
                self._library_groups = {name: (tr(g.kinds[name].help),
                                               summary(g.definitions[name], {**CATALOG, **g.kinds}))
                                        for name, g in library.graphs().items()}
            except OSError:
                self._library_groups = {}
        p = self.project
        own = {}
        if p is not None:
            known = {**CATALOG, **p.graph.kinds}
            own = {name: (tr(p.graph.kinds[name].help), summary(p.graph.definitions[name], known))
                   for name in p.graph.definitions if name in p.graph.kinds}
        if (own, self._library_groups) != getattr(self, "_library_shown", None):   # (a slider moved: nothing new)
            self._library_shown = (dict(own), dict(self._library_groups))
            self.library.show_groups(own, self._library_groups)

    def _put_group(self, where: str, name: str) -> None:
        if self.project is not None:
            self.editor.put_group(where, name)

    def _rename_in_library(self, where: str, name: str) -> None:
        from .. import library as library
        new_, ok = ask_text(self, tr('Rename in the library'), tr('New name for “{group}” in the library (the '
                                                                    'projects that use it keep theirs):').format(
            group=name), text=name)
        if not ok or not new_.strip() or new_.strip() == name:
            return
        try:
            library.rename(name, new_.strip())
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Could not rename'), str(error))
            return
        self._show_library(reread=True)

    def _delete_from_library(self, name: str) -> None:
        """A group out of the library, to the trash (it can be taken back from there). The projects that use it keep
        their own copy."""
        from PySide6.QtCore import QFile
        from .. import library as library
        try:
            filepath = library.file_of(name)
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not delete'), str(error))
            return
        if QMessageBox.question(
                self, tr('Delete from the library'),
                tr('Delete “{group}” from the library? Its file goes to the trash (it can be taken back from there); '
                   'the projects that use it keep their own copy.').format(group=name)) \
                != QMessageBox.StandardButton.Yes:
            return
        moved = QFile.moveToTrash(str(filepath))
        if not (moved[0] if isinstance(moved, tuple) else moved):     # (a bool, or (bool, path), by version)
            if QMessageBox.question(
                    self, tr('Delete from the library'),
                    tr('“{file}” could not be moved to the trash. Delete it for good? This cannot be undone.').format(
                        file=filepath)) != QMessageBox.StandardButton.Yes:
                return
            try:
                filepath.unlink()
            except OSError as error:
                QMessageBox.warning(self, tr('Could not delete'), str(error))
                return
        self._show_library(reread=True)

    # --- Nuevo, guardar --------------------------------------------------------------

    def _follow_without_save(self) -> bool:
        """If there are unsaved changes, it asks. True: one can go on."""
        if not self.modified:
            return True
        r = QMessageBox.question(
            self, tr('Unsaved changes'), tr('The project has unsaved changes. Save them?'),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def new_(self, reuse_empty: bool = False) -> None:
        """A new empty project, in a tab of its own (the «+» and Ctrl+N always add one). `reuse_empty`: if this tab is
        already an empty project without a name, it stays (New project on the start screen)."""
        self._new_tab(Project(Graph()), None, reuse_empty=reuse_empty)
        self.statusBar().showMessage(tr('New project: double-click in the editor (or Tab) to add the first node.'))

    def save(self) -> bool:
        if self.project is None:
            return False
        if self.filepath is None:
            return self.save_as()
        self._collect_canvas()
        try:
            save(self.project, self.filepath)
            self._remember(self.filepath)
            self._keep_preview()
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Could not save'), str(error))
            return False
        self.modified = False
        self._title()
        self.statusBar().showMessage(tr('Saved: {path}').format(path=self.filepath))
        return True

    def save_as(self) -> bool:
        if self.project is None:
            return False
        # A project of before (.json) is offered as .tela: saving it again as it was is Save, not Save as.
        here = (self.filepath.with_suffix(EXTENSION) if self.filepath
                else Path(self._folder()) / (tr('untitled') + EXTENSION))
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Save project'), str(here),
                                                  tr('Tensela projects (*.tela)'))
        if not filepath:
            return False
        self.filepath = Path(filepath) if filepath.endswith(EXTENSIONS) else Path(filepath + EXTENSION)
        return self.save()

    def _all_saved_o_discarded(self) -> bool:
        """On quitting: for each project with changes, it asks (in its tab)."""
        for i in range(len(self.documents)):
            self._save_tab()
            if self.documents[i] is not None and self.documents[i]["modified"]:
                self.tabs.setCurrentIndex(i)
                if not self._follow_without_save():
                    return False
        return True                             # each one was already asked once (before it came out twice)

    def contextMenuEvent(self, event) -> None:
        """Right click on the tabs of panels grouped together: the list of the panels, as on the header of a loose
        panel (Qt offers it there, not on the tabs of a group)."""
        under = self.childAt(event.pos())
        if isinstance(under, QTabBar) and under is not self.tabs:
            menu = self.createPopupMenu()
            if menu is not None:
                menu.exec(event.globalPos())
                return
        super().contextMenuEvent(event)

    def closeEvent(self, event) -> None:
        if self._all_saved_o_discarded():
            for panel in self.panels.values():
                panel.return_()                  # those taken out come back: the layout remembers them in their place
            settings = QSettings()
            settings.setValue("window/layout", self.saveState(VERSION_LAYOUT))
            settings.setValue("window/maximized", self.isMaximized())
            if not self.isMaximized():
                settings.setValue("window/size", [self.width(), self.height()])
            self.viewer.dismiss()
            self.croquis.dismiss()
            if self._calculator_ is not None:
                self._calculator_.close()
            event.accept()
        else:
            event.ignore()

    # --- Open and export -----------------------------------------------------

    def _open_ask(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(self, tr('Open project'), self._folder(),
                                              tr('Tensela projects (*.tela *.json)'))
        if filepath:
            self.open_(filepath)

    def open_(self, filepath, as_new: bool = False) -> bool:
        """Opens a project in its own tab. `as_new`: as a new project without a name (a recipe of the start screen:
        saving it asks where, and the recipe stays as it is)."""
        try:
            project = open_(filepath)
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not open'), str(error))
            return False
        if not project.controls:  # without controls in the file: a slider per number
            project.controls = automatic_controls(project.graph)
        n = _code_nodes(project.graph)
        self._notice_code = (tr('This project has 1 Code node: code written by whoever made the project. It runs '
                                'closed in: it cannot touch your files or connect anywhere. You can read it with '
                                '«Edit code…».') if n == 1 else
                             tr('This project has {n} Code nodes: code written by whoever made the project. They run '
                                'closed in: they cannot touch your files or connect anywhere. You can read them with '
                                '«Edit code…».').format(n=n)) if n else None
        if as_new:
            self._load(project, None)
            return True
        self._load(project, Path(filepath))           # (it computes: the notice above is said when it finishes)
        self._remember(Path(filepath))
        return True

    def show_start(self) -> None:
        """The start screen (ui/start.py): a new project, open one, the recent ones and the recipes."""
        from .start import StartScreen
        if getattr(self, "_start_screen", None) is not None:      # already open: to the front
            self._start_screen.raise_()
            self._start_screen.activateWindow()
            return
        screen = StartScreen(self._recent(), app_icon(), self)
        screen.destroyed.connect(lambda *_: setattr(self, "_start_screen", None))
        screen.new.connect(lambda: self.new_(reuse_empty=True))
        screen.open_ask.connect(self._open_ask)
        screen.open_file.connect(self.open_)
        screen.open_template.connect(lambda path: self.open_(path, as_new=True))
        screen.forget_recent.connect(lambda: QSettings().setValue("recent", []))
        self._start_screen = screen
        self._display_dialog(screen)

    # --- One window for all, and the applications menu ------------------------------------------------------------

    def listen_for_others(self) -> bool:
        """Another start of Tensela hands its projects to this window (ui/launch.py): they open here as new tabs."""
        from PySide6.QtNetwork import QLocalServer
        from .launch import address
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(address()):
            QLocalServer.removeServer(address())          # left by a Tensela that did not end well
            if not server.listen(address()):
                return False
        server.newConnection.connect(self._from_other_start)
        self._server, self._arriving = server, {}
        return True

    def _from_other_start(self) -> None:
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            self._arriving[id(connection)] = b""
            connection.readyRead.connect(lambda c=connection: self._read_other_start(c))
            connection.disconnected.connect(lambda c=connection: (self._arriving.pop(id(c), None), c.deleteLater()))

    def _read_other_start(self, connection) -> None:
        data = self._arriving.get(id(connection), b"") + bytes(connection.readAll())
        self._arriving[id(connection)] = data
        if b"\n" not in data:
            return
        connection.write(b"ok\n")
        connection.flush()
        connection.disconnectFromServer()
        try:
            message = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
            files = [str(f) for f in message.get("files", [])]
        except (ValueError, AttributeError):
            message, files = {}, []
        for file in files:
            self.open_(file)
        self.come_forward({k: str(v) for k, v in message.items() if k != "files"})

    def come_forward(self, tokens: dict | None = None) -> None:
        """This window in front (another start of Tensela asked for it, with the permission the desktop gave it)."""
        from .activate import bring_forward
        bring_forward(self, tokens or {})

    def offer_menu(self) -> None:
        """At the start: from an AppImage moved or newer, the launcher of the menu follows it; from one not in the
        menu yet, the strip that offers to put it there (unless it was declined)."""
        from . import desktop
        if desktop.appimage() is None:
            return
        desktop.follow_move()
        if desktop.installed_for() is None and not QSettings().value("desktop/declined", False, type=bool):
            self.desktop_strip.show()

    def put_in_menu(self, yes: bool) -> bool:
        """Tensela into the applications menu (from its AppImage), or out of it. Returns whether it is there."""
        from . import desktop
        self.desktop_strip.hide()
        try:
            if yes and desktop.appimage() is not None:
                desktop.install(desktop.appimage())
                self.statusBar().showMessage(tr('Tensela is in the applications menu: .tela files open with a '
                                                'double click.'))
            elif not yes:
                desktop.uninstall()
                self.statusBar().showMessage(tr('Tensela is out of the applications menu.'))
        except OSError as error:
            QMessageBox.warning(self, tr('Could not change the applications menu'), str(error))
        return desktop.installed_for() is not None

    def _decline_menu(self) -> None:
        QSettings().setValue("desktop/declined", True)
        self.desktop_strip.hide()

    def _keep_preview(self) -> None:
        """The picture of the project as it looks now, for the start screen (it is kept in the cache)."""
        if self.filepath is None:
            return
        try:
            from .start import save_preview
            pixels = np.ascontiguousarray(self.viewer.view.screenshot(return_img=True)[..., :3])
            h, w = pixels.shape[:2]
            from PySide6.QtGui import QImage
            save_preview(QImage(pixels.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy(), self.filepath)
        except Exception:                            # a picture is not worth a failure on saving
            pass

    # --- Archivos recientes -------------------------------------------------------

    def _recent(self) -> list[str]:
        list_ = QSettings().value("recent", [])
        return [r for r in (list_ if isinstance(list_, list) else [list_]) if r]

    def _remember(self, filepath: Path) -> None:
        r = str(Path(filepath).resolve())
        QSettings().setValue("recent", ([r] + [x for x in self._recent() if x != r])[:10])
        QSettings().setValue("files/folder", str(Path(r).parent))      # Open… and Save as… start there

    def _folder(self) -> str:
        """Where Open… and Save as… start: the folder of the last project opened or saved, or the home folder."""
        folder = QSettings().value("files/folder", "")
        return folder if folder and Path(folder).is_dir() else str(Path.home())

    def _fill_recent(self) -> None:
        self.menu_recent.clear()
        recent = [r for r in self._recent() if Path(r).exists()]
        if not recent:
            self.menu_recent.addAction(tr('(none yet)')).setEnabled(False)
            return
        for i, r in enumerate(recent, start=1):
            a = self.menu_recent.addAction(f"&{i % 10}  {Path(r).name}   —   {Path(r).parent}")
            a.triggered.connect(lambda _=False, r=r: self.open_(r))
        self.menu_recent.addSeparator()
        self.menu_recent.addAction(tr('Forget the list')).triggered.connect(lambda: QSettings().setValue("recent", []))

    def _load(self, project: Project, filepath: Path | None) -> None:
        """Opens `project` in its own tab (if that file is already open, it only goes to it)."""
        if filepath is not None:
            for i, d in enumerate(self.documents):
                if d is not None and d["path"] is not None and Path(d["path"]).resolve() == Path(filepath).resolve():
                    self.tabs.setCurrentIndex(i)
                    return
        self._new_tab(project, filepath)

    # --- Exporting: with the results the view shows (none computed here), the slow part aside -------------------

    def _wait_for_calculation(self) -> bool:
        """Before exporting: the calculation in progress, waited for (the export takes what the view will show).
        False if it was not waited for to the end."""
        if self._in_progress is None:
            return True
        dialog = QProgressDialog(tr('Waiting for the calculation to end, to export what the view will show…'),
                                 tr('Cancel'), 0, 0, self)
        dialog.setWindowTitle(tr('Export'))
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(300)
        try:
            while self._in_progress is not None and not dialog.wasCanceled():
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
                time.sleep(0.01)
        finally:
            dialog.close()
        return self._in_progress is None

    def _export_values(self, names: list[str]) -> list | None:
        """The results of `names`, to export them. None (said) if one has none: an error, or the calculation was
        stopped."""
        if not self._wait_for_calculation():
            return None
        g = self.project.graph
        missing = [n for n in names if g.nodes[n]._value is None]
        if missing:
            QMessageBox.warning(self, tr('Could not export'), tr(
                '«{node}» has no result: it has an error, or its calculation was stopped. Fix it or turn off its '
                'eye, and export again.').format(node=missing[0]))
            return None
        return [g.nodes[n]._value for n in names]

    def _aside(self, text: str, function):
        """Runs `function` (an export, which may take long) in a thread of its own: meanwhile the window repaints and
        says `text`, without taking clicks. Its result, or its error."""
        box = {}

        def work() -> None:
            try:
                box["result"] = function()
            except BaseException as error:              # noqa: BLE001 (raised again here, in the window's thread)
                box["error"] = error

        thread = threading.Thread(target=work, daemon=True, name="export")
        thread.start()
        thread.join(0.1)
        if thread.is_alive():
            self.statusBar().showMessage(text)
            self.setCursor(Qt.CursorShape.BusyCursor)
            try:
                while thread.is_alive():
                    QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 50)
                    thread.join(0.02)
            finally:
                self.unsetCursor()
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def _ask_export(self) -> None:
        if not self.project or not self.project.export:
            self.statusBar().showMessage(tr('Nothing to export.'))
            return
        values = self._export_values(self.project.export)
        if values is None:
            return
        suggested = str(self.filepath.with_suffix(".obj")) if self.filepath else "proyecto.obj"
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Export to OBJ'), suggested, tr("Wavefront OBJ (*.obj)"))
        if not filepath:
            return
        try:
            self._aside(tr('Saving the OBJ…'), lambda: export_obj(filepath, *values))
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not export'), str(error))
            return
        self.statusBar().showMessage(tr('Exported: {path}').format(path=filepath))

    def _ask_print(self, kind: str) -> None:
        """STL or 3MF of the visible nodes with faces, in millimetres; checked first (Print check), and if a piece
        cannot be printed, it is said before saving."""
        from ..connectors.print3d import export_3mf, export_stl
        from ..printing import check, pieces
        p = self.project
        if not p or not p.export:
            self.statusBar().showMessage(tr('Nothing to export: turn on “Show in 3D” on a node.'))
            return
        g = p.graph
        # (What a Print check shows, the printer's volume or the red lines, helps to look: it is not printed.)
        values = self._export_values([n for n in p.export if g.nodes[n].kind.name != 'Print check'])
        if values is None:
            return
        with_faces = [v for v in values if v.kind is not None and v.kind.faces is not None and not v.kind.curve]
        if not with_faces:
            QMessageBox.warning(self, tr('Could not export'), tr('No visible node has faces (a body, a mesh, a '
                                                                  'surface): there is nothing to print.'))
            return
        try:
            reports = self._aside(tr('Checking the pieces…'),
                                  lambda: [r for v in with_faces for r in check(pieces(v), printer=None)])
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not export'), str(error))
            return
        failing = [r for r in reports if not r.ready]
        if failing:
            first = failing[0].problems[0]
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(tr('Not ready to print'))
            box.setText(tr('{n} of {total} pieces would not print well.').format(n=len(failing), total=len(reports)))
            box.setInformativeText(first[:1].upper() + first[1:] + "\n\n" +
                                   tr('A Print check node shows where, in red, and what to do.'))
            keep = box.addButton(tr('Export anyway'), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(tr('Cancel'), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is not keep:
                return
        suffix = "." + kind
        suggested = str(self.filepath.with_suffix(suffix)) if self.filepath else "proyecto" + suffix
        filter_ = tr("STL for 3D printing (*.stl)") if kind == "stl" else tr("3MF for 3D printing (*.3mf)")
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Export for 3D printing'), suggested, filter_)
        if not filepath:
            return
        if not filepath.lower().endswith(suffix):
            filepath += suffix
        colours = {n: (p.view.get(n) or {}).get("color") for n in p.export}
        try:
            self._aside(tr('Saving for 3D printing…'), lambda: export_stl(filepath, *with_faces) if kind == "stl" else
                        export_3mf(filepath, *with_faces, colours=colours))
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not export'), str(error))
            return
        self.statusBar().showMessage((tr('Exported: {path} (1 piece, in millimetres)') if len(reports) == 1 else
                                      tr('Exported: {path} ({n} pieces, in millimetres)')).format(
            path=filepath, n=len(reports)))

    def _ask_cutting(self) -> None:
        """The visible flat pieces (Lay flat) as a cutting file, DXF or SVG, in millimetres; one per sheet."""
        from ..connectors.cutting import export_cutting, lying_flat
        p = self.project
        if not p or not p.export:
            self.statusBar().showMessage(tr('Nothing to export: turn on “Show in 3D” on a node.'))
            return
        g = p.graph
        names = [n for n in p.export if g.nodes[n].kind.name != 'Print check']
        values = self._export_values(names)
        if values is None:
            return
        items, left_out = lying_flat(list(zip(names, values)))
        if not items:
            QMessageBox.warning(self, tr('Could not export'), tr(
                'Nothing visible is lying flat on the ground, ready to cut: lay the pieces flat with Lay flat and '
                'turn on its eye.'))
            return
        # The format of the last time, both in the name and in the list below, so they agree.
        filters = {".svg": tr("SVG for a laser (*.svg)"), ".dxf": tr("DXF for a laser or a router (*.dxf)")}
        last = QSettings().value("export/cutting_format", ".svg")
        last = last if last in filters else ".svg"
        suggested = str(self.filepath.with_suffix(last)) if self.filepath else "pieces" + last
        filepath, chosen = QFileDialog.getSaveFileName(
            self, tr('Export a cutting file'), suggested, ";;".join(filters.values()), filters[last])
        if not filepath:
            return
        picked = ".dxf" if "dxf" in chosen.lower() else ".svg"
        if not filepath.lower().endswith((".svg", ".dxf")):
            filepath += picked
        elif filepath.lower().endswith(last) and picked != last:
            filepath = filepath[:-4] + picked             # the list changed and the name, as suggested: the list wins
        QSettings().setValue("export/cutting_format", filepath[-4:].lower())
        try:
            written = self._aside(tr('Saving the cutting file…'), lambda: export_cutting(filepath, items))
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not export'), str(error))
            return
        said = (tr('Exported: {path} (in millimetres: red, cut; blue, engrave)').format(path=written[0])
                if len(written) == 1 else
                tr('Exported {n} files, one per sheet: {first} …, and {all} with all of them side by side, to check '
                   'them.').format(n=len(written) - 1, first=written[0].name, all=written[-1].name))
        if left_out:
            said += "  ·  " + tr('Left out (not lying flat, the model in 3D): {nodes}.').format(nodes=", ".join(left_out))
        self.statusBar().showMessage(said)

    def _offer_restart(self) -> None:
        """The new language asks for reopening: it is said clearly, in both languages, and doing it now is offered."""
        box = QMessageBox(QApplication.activeWindow() or self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Idioma · Language")
        box.setText("El idioma cambia al volver a abrir Tensela.\n"
                     "The language changes when Tensela is reopened.")
        box.setInformativeText("Si hay algo sin guardar, se pregunta antes de cerrar.\n"
                                "If anything is unsaved, you will be asked before closing.")
        now = box.addButton("Reiniciar ahora · Restart now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Más tarde · Later", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(now)
        box.exec()
        if box.clickedButton() is now:
            self.restart()

    def restart(self) -> None:
        """Closes Tensela (asking about what is not saved) and opens it again with the same projects."""
        self._save_tab()
        filepaths = [str(Path(d["path"]).resolve()) for d in self.documents if d is not None and d.get("path")]
        for dialog in list(getattr(self, "_open_dialogs", [])):
            dialog.close()
        if not self.close():
            return
        order = [a for a in sys.orig_argv[1:] if not a.endswith(EXTENSIONS)]
        subprocess.Popen([sys.executable, *order, *filepaths], start_new_session=True)
        QApplication.instance().quit()

    def _display_dialog(self, dialog, on_accept=None) -> None:
        """Opens a dialog without blocking the window (non-modal): GNOME «sticks» the modal ones to the main window and,
        on dragging them, the whole application moved."""
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if on_accept is not None:
            dialog.accepted.connect(lambda: on_accept(dialog))
        # A reference is kept while it is open; on closing, Qt deletes it and it leaves the list.
        self._open_dialogs = getattr(self, "_open_dialogs", []) + [dialog]
        dialog.destroyed.connect(lambda *_: self._open_dialogs.remove(dialog)
                                  if dialog in self._open_dialogs else None)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _ask_image(self) -> None:
        if not self.project:
            return
        self._display_dialog(DialogImage(self, self.viewer.size_()), self._export_image)

    def _export_image(self, dialog) -> None:
        # What was chosen, before asking where to save: meanwhile, Qt deletes the already closed dialog.
        scale, background, axes = dialog.choice()
        suggested = str(self.filepath.with_suffix(".png")) if self.filepath else "view.png"
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Export image'), suggested, tr('PNG image (*.png)'))
        if not filepath:
            return
        if not filepath.lower().endswith(".png"):
            filepath += ".png"
        try:
            width, height = self.viewer.save_image(filepath, scale=scale, background=background, axes=axes)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr('Export image'), str(error))
            return
        self.statusBar().showMessage(tr('Image saved: {path} ({width} × {height} px)').format(path=filepath, width=width, height=height))

    def _ask_dxf(self) -> None:
        if not self.project or not self._wait_for_calculation():
            return
        objects = self.project.visible_objects(computed_only=True)
        if not objects:
            self.statusBar().showMessage(tr('Nothing to export: turn on “Show in 3D” on a node.'))
            return
        settings = QSettings()
        dialog = DialogDxf(self, settings.value("dxf/unit", "millimetres"),
                             settings.value("dxf/compatible", False, type=bool),
                             settings.value("dxf/mode", 0, type=int), settings.value("dxf/view", "plan"),
                             settings.value("dxf/visible", True, type=bool))
        self._display_dialog(dialog, lambda d: self._export_dxf(d, objects))

    def _export_dxf(self, dialog, objects) -> None:
        settings = QSettings()
        unit, compatible, view, visible_only = dialog.choice()
        base = self.filepath.stem if self.filepath else "project"
        folder = self.filepath.parent if self.filepath else Path.cwd()
        suggested = str(folder / (f"{base} {view}.dxf" if view else f"{base}.dxf"))
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Export DXF'), suggested, tr('DXF drawing (*.dxf)'))
        if not filepath:
            return
        if not filepath.lower().endswith(".dxf"):
            filepath += ".dxf"
        try:
            self._aside(tr('Removing hidden lines and saving the DXF…') if view and visible_only
                        else tr('Saving the DXF…'),
                        lambda: export_dxf(filepath, objects, unit=DialogDxf.UNITS[unit], compatible=compatible,
                                           view=view, visible_only=visible_only))
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Export DXF'), str(error))
            return
        settings.setValue("dxf/unit", unit)
        settings.setValue("dxf/compatible", compatible)
        settings.setValue("dxf/mode", 1 if view else 0)
        if view:
            settings.setValue("dxf/view", view)
            settings.setValue("dxf/visible", visible_only)
        what = tr('in 2D, {view}').format(view=tr(view)) if view else tr('in 3D')
        self.statusBar().showMessage(tr('Exported: {path} ({what}, one layer per node, in {unit})').format(
            path=filepath, what=what, unit=tr(unit)))

    def _sketch(self) -> None:
        """Opens the Croquis panel (in front, if it is in tabs) with the view of now."""
        panel = self.panels["sketch"]
        panel.show()
        panel.raise_()
        if not panel.isFloating() and panel.height() < 560:      # so the preview and the styles fit
            self.resizeDocks([panel], [min(640, max(560, self.height() - 260))], Qt.Orientation.Vertical)
        self._graph_scene_sketch = None
        self._follow_sketch()

    def _follow_sketch(self) -> None:
        """If the Croquis panel is seen and the camera or the model changed, it passes it the scene."""
        if not self.croquis.isVisible() or self.project is None:
            return
        camera = self.viewer.view.camera_position
        key = (id(self.project), self._version_graph_scene, tuple(map(tuple, camera)), self.viewer.size_())
        if key == self._graph_scene_sketch:
            return
        self._graph_scene_sketch = key
        objects = self.project.visible_objects(computed_only=True) if self.project.export else []
        folder = str(self.filepath.parent) if self.filepath else ""
        self.croquis.put_graph_scene(objects, self.viewer.camera_sketch() if objects else None,
                                  self._name_project(), folder)

    # --- IngeTrazo ------------------------------------------------------------------

    def _open_in_ingetrazo(self) -> None:
        objects = self._objects_a_carry()
        if objects is None:
            return
        try:
            self._aside(tr('Preparing the scene…'), lambda: open_in_ingetrazo(objects, self._name_project()))
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Open in IngeTrazo'), str(error))
            return
        self.statusBar().showMessage(tr('Opening IngeTrazo with the scene. To keep it, save it from IngeTrazo (Save as…).'))

    def _ask_export_igz(self) -> None:
        objects = self._objects_a_carry()
        if objects is None:
            return
        suggested = str(self.filepath.with_suffix(".igz")) if self.filepath else "proyecto.igz"
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Export to IngeTrazo'), suggested, tr("IngeTrazo (*.igz)"))
        if not filepath:
            return
        if not filepath.lower().endswith(".igz"):
            filepath += ".igz"
        try:
            self._aside(tr('Saving the scene…'), lambda: export_igz(filepath, objects, self._name_project()))
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Export to IngeTrazo'), str(error))
            return
        self.statusBar().showMessage(tr('Exported: {path}').format(path=filepath))

    # --- Blender directo ----------------------------------------------------------

    def _objects_a_carry(self) -> list | None:
        p = self.project
        if not p or not p.export:
            self.statusBar().showMessage(tr('Nothing to send: turn on “Show in 3D” on a node.'))
            return None
        if not self._wait_for_calculation():
            return None
        return p.visible_objects(computed_only=True)

    def _name_project(self) -> str:
        return self.filepath.stem if self.filepath else "Tensela"

    def _open_in_blender(self) -> None:
        objects = self._objects_a_carry()
        if objects is None:
            return
        try:
            self._aside(tr('Preparing the scene…'), lambda: open_in_blender(objects, self._name_project()))
        except ShapeError as error:
            QMessageBox.warning(self, tr('Open in Blender'), str(error))
            return
        self.statusBar().showMessage(tr('Opening Blender with the scene (one object per node, in metres)…'))

    def _ask_export_blend(self) -> None:
        objects = self._objects_a_carry()
        if objects is None:
            return
        suggested = str(self.filepath.with_suffix(".blend")) if self.filepath else "proyecto.blend"
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Export to Blender'), suggested, tr("Blender (*.blend)"))
        if not filepath:
            return
        try:
            self._aside(tr('Blender is saving the scene…'),
                        lambda: export_blend(filepath, objects, self._name_project()))
        except (ShapeError, OSError, subprocess.TimeoutExpired) as error:
            QMessageBox.warning(self, tr('Export to Blender'), str(error))
            return
        self.statusBar().showMessage(tr('Exported: {path}').format(path=filepath))

    # --- Valores ------------------------------------------------------------

    def _create_controls(self) -> None:
        while self.items_values.count() > 1:  # everything but the final space
            w = self.items_values.takeAt(0).widget()
            if w:
                w.hide()              # out now: if not, it is seen on top of the new ones until Qt deletes it
                w.deleteLater()
        g = self.project.graph
        controls = self.project.controls
        self.sliders: dict[str, Slider] = {}
        groups: dict[str, QVBoxLayout] = {}
        self._boxes_values: dict = {}           # the box of sliders of each node (to go to it)
        by_node = {n: sum(1 for c in controls if c.node == n) for n in {c.node for c in controls}}
        for c in controls:
            v = g.nodes[c.node].inputs[c.input_]
            list_ = numbers_items(v)
            # A single value whose name is already the node's (a Number): without a title above repeating it.
            only = list_ is None and by_node[c.node] == 1 and (c.input_ == "value" or c.label == c.node)
            if c.node not in groups:
                box = QGroupBox("" if only else c.node)
                box.setObjectName("value_alone" if only else "value_group")
                groups[c.node] = QVBoxLayout(box)
                self._boxes_values[c.node] = box
                self.items_values.insertWidget(self.items_values.count() - 1, box)
            if list_ is None:
                pieces = [(c.key, None, float(v), (c.label or c.node) if only else None)]
            else:
                # A list: a slider per value, with the name of its level («ring 0», «ring 1»…).
                level = g.nodes[c.node].inputs.get("level") if c.input_ == "value" else None
                level = level if isinstance(level, str) and level else "value"
                pieces = [(f"{c.key}[{i}]", i, float(x), f"{tr(level)} {i}") for i, x in enumerate(list_)]
            for key, i, value, label in pieces:
                d = Slider(c, value, label=label)
                d.change.connect(lambda value, c=c, i=i: self.change(c, value, i))
                d.play.connect(lambda c=c, i=i, d=d: self._play_control(c, i, d))
                d.stop_play.connect(lambda c=c, i=i: self.stop_playing_back(("control", c.key, i)))
                p = self.__dict__.get("_playing")
                if p is not None and p["what"] == ("control", c.key, i):     # rebuilt while it plays
                    d.show_play("paused" if p["paused"] else "playing")
                d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                d.customContextMenuRequested.connect(lambda point, c=c, d=d: self._menu_slider(c, d.mapToGlobal(point)))
                groups[c.node].addWidget(d)
                self.sliders[key] = d
        self._tell_extensions("sliders")

    # --- Playing a value: to see it move ------------------------------------------------

    #: How long a ▶ takes to go from the start to the end.
    PLAY_SECONDS = 4.0

    def _play_control(self, control: Control, index: int | None, slider: Slider) -> None:
        """The ▶ of a slider: its value from the minimum to the maximum (or pauses, or goes on, if it was playing)."""
        def apply(value: float) -> None:
            if control.step:
                value = control.minimum + round((value - control.minimum) / control.step) * control.step
            slider.put(value)
            self.change(control, round(value, 10), index)

        key = control.key if index is None else f"{control.key}[{index}]"

        def show(state: str | None) -> None:
            shown = self.sliders.get(key)
            if shown is not None:
                try:
                    shown.show_play(state)
                except RuntimeError:                     # the slider was rebuilt meanwhile
                    pass

        self._play(("control", control.key, index), control.minimum, control.maximum, apply, show,
                   float(slider.cell.value()))

    def play_input(self, node: str, input_: str, start: float, end: float) -> None:
        """Plays an input of a node from `start` to `end` (the ▶ of the Equilibrium's panel: its moment)."""
        def apply(value: float) -> None:
            if node not in self.project.graph.nodes:
                self._stop_playing()
                return
            self.project.graph.change(node, input_, round(value, 6))
            if node in self.editor.boxes:
                self.editor.boxes[node].refresh()
            self.recompute()
            self._register(f"play {node} {input_}")

        before = self.project.graph.nodes[node].inputs.get(input_) if node in self.project.graph.nodes else None
        self._play(("input", node, input_), start, end, apply, None,
                   float(before) if isinstance(before, (int, float)) else end)

    def _play(self, what: tuple, start: float, end: float, apply, show, before: float) -> None:
        """Plays a value from `start` to `end`; the same ▶ again pauses it, and once more it goes on from there.
        `show(state)` says it to its button; `before` is the value it goes back to with ■."""
        playing = self.__dict__.get("_playing")
        if playing is not None and playing["what"] == what:
            self._pause_playing(not playing["paused"])
            return
        self._stop_playing()
        if playing is not None and playing["project"] is self.project:
            playing["apply"](playing["before"])           # another ▶: the one playing goes back, as with ■
        self._playing = {"what": what, "start": start, "end": end, "apply": apply, "show": show, "before": before,
                         "since": time.monotonic(), "project": self.project, "last": None, "paused": False,
                         "elapsed": 0.0}
        if self.__dict__.get("_clock_play") is None:
            self._clock_play = QTimer(self)
            self._clock_play.setInterval(30)
            self._clock_play.timeout.connect(self._play_step)
        self._show_playing()
        self._playing["last"] = start
        apply(start)                                       # it starts from the start, right away
        self._clock_play.start()

    def _pause_playing(self, pause: bool = True) -> None:
        """⏸: it stays where it is; ▶ again: it goes on from there."""
        p = self.__dict__.get("_playing")
        if p is None or p["paused"] == pause:
            return
        p["paused"] = pause
        if pause:
            p["elapsed"] = time.monotonic() - p["since"]
            self._clock_play.stop()
        else:
            p["since"] = time.monotonic() - p["elapsed"]
            self._clock_play.start()
        self._show_playing()

    def stop_playing_back(self, what: tuple) -> None:
        """■: it stops, and the value goes back to the one it had before playing."""
        p = self.__dict__.get("_playing")
        if p is None or p["what"] != what:
            return
        self._stop_playing()
        if p["project"] is self.project:
            p["apply"](p["before"])
        self.statusBar().showMessage(tr('Stopped: the value is back to the one it had before playing.'))

    def _show_playing(self) -> None:
        """The play buttons say how it goes: playing (⏸ and ■), paused (▶ and ■) or nothing."""
        p = self.__dict__.get("_playing")
        state = None if p is None else "paused" if p["paused"] else "playing"
        if p is not None and p["show"] is not None:
            p["show"](state)
        self.panel_node.playing = None if p is None else (p["what"], state)
        self._display_node(self._selection)

    def _play_step(self) -> None:
        """One frame: the value where the time says (if the last frame is still being computed, it waits)."""
        p = self.__dict__.get("_playing")
        if p is None or p["paused"]:
            return
        if p["project"] is not self.project:
            self._stop_playing()
            return
        if self._in_progress is not None:
            return
        fraction = min(1.0, (time.monotonic() - p["since"]) / self.PLAY_SECONDS)
        value = p["start"] + (p["end"] - p["start"]) * fraction
        if value != p["last"]:
            p["last"] = value
            p["apply"](value)
        if fraction >= 1.0:
            self._stop_playing()

    def _stop_playing(self) -> None:
        p = self.__dict__.get("_playing")
        self._playing = None
        clock = self.__dict__.get("_clock_play")
        if clock is not None:
            clock.stop()
        if p is not None:
            if p["show"] is not None:
                p["show"](None)
            self.panel_node.playing = None
            self._display_node(self._selection)

    def change(self, control: Control, value: float, index: int | None = None) -> None:
        """A slider moved: it changes the value (or, in a list, the value `index`)."""
        put_value(self.project.graph, control.node, control.input_, value, index, float(control.step).is_integer())
        self.editor.boxes[control.node].refresh()
        self.recompute()
        self._register(control.key)

    # --- After editing the graph on the canvas ---------------------------------------

    def _after_edit(self) -> None:
        """The graph changed in the editor: the project forgets what was deleted and recomputes."""
        if self._inside is not None:
            self._apply_inside()
            self._display_node(self._selection)
            self._register()
            return
        p = self.project
        exist = set(p.graph.nodes)
        p.export = [n for n in p.export if n in exist]
        p.view = {n: v for n, v in p.view.items() if n in exist}
        if self._drawing is not None and self._drawing not in exist:   # what was being drawn was deleted
            self.finish_drawing()                    # (after forgetting it: finishing computes and shows the rest)
        before = len(p.controls)
        # A slider only for a fixed number (not if it now comes from another node, or is a list).
        p.controls = [c for c in p.controls
                       if c.node in exist and _is_number(p.graph.nodes[c.node].inputs[c.input_])]
        if len(p.controls) != before:
            self._create_controls()
        self.recompute()
        self._display_node(self._selection)
        self._register()

    # --- The panel of the selected node -------------------------------------------

    def _display_node(self, name: str | None) -> None:
        before, self._selection = self._selection, name
        if name != before:
            self._tell_extensions("selected", name)
        if (name != before and name is not None and self.project is not None and self._inside is None
                and name in self.project.graph.nodes and self._drawing is None):
            n = self.project.graph.nodes[name]
            # A Drawn curve just put: to draw, without looking for the button (the NURBS waits: its points may
            # come from another node).
            if n.kind.name == 'Drawn curve' and not n.inputs["points"]:
                QTimer.singleShot(0, lambda: self.draw(name))
        self._together = self._chosen_together() if name is None else []
        if self._together:                     # several of one kind: the panel shows the first, and changes them all
            name = self._together[0]
        if name is None or self.project is None or name not in self._canvas.nodes:
            self.panel_node.display(None)
            return
        if self._inside is not None:            # inside a group: its eye (for now), without slider or colour
            self.panel_node.display(self._canvas.nodes[name], name in self._seen_inside(), set(), None)
            return
        p = self.project
        self.panel_node.display(p.graph.nodes[name], name in p.export,
                                {c.input_ for c in p.controls if c.node == name},
                                p.view.get(name, {}).get("color"),
                                float(p.view.get(name, {}).get("opacity", 1.0)),
                                bool(p.view.get(name, {}).get("numbers", False)),
                                p.view.get(name, {}).get("by"), p.view.get(name, {}).get("gradient", ""),
                                p.for_colour_by(name) if name in p.export else [],
                                bool(p.view.get(name, {}).get("curvature_comb", False)),
                                p.view.get(name, {}).get("analyze", "no"), together=max(1, len(self._together)),
                                differing=self._differing(self._together))
        QTimer.singleShot(0, lambda: self._go_a_values(name))   # its sliders, in view in Values
        self._look_again()                      # not calculated yet (not seen until now): it is calculated

    def _differing(self, names: list[str]) -> dict[str, list[str]]:
        """Of several nodes of one kind, the inputs whose value is not the same in all: {input: ["box A: 1 m", …]}."""
        if len(names) < 2:
            return {}
        from ..values import is_length, text_of
        nodes = [self.project.graph.nodes[n] for n in names]
        found = {}
        for input_ in nodes[0].kind.inputs:
            texts = []
            for n in nodes:
                v = n.inputs.get(input_.name)
                texts.append(f"← {v.name}" if isinstance(v, Node) else
                             text_of(input_.name, v, is_length(n, input_.name)) if v is not None else tr('empty'))
            if len(set(texts)) > 1:
                found[input_.name] = [f"{n.name}: {t}" for n, t in zip(nodes, texts)]
        return found

    def _chosen_together(self) -> list[str]:
        """The chosen nodes, if they are two or more and all of the same kind (outside a group), in the project's
        order; otherwise none."""
        if self.project is None or self._inside is not None:
            return []
        chosen = {box.node.name for box in self.editor.chosen()}
        graph = self.project.graph
        if len(chosen) < 2 or not chosen <= graph.nodes.keys() or \
                len({graph.nodes[n].kind.name for n in chosen}) > 1:
            return []
        return [n for n in graph.nodes if n in chosen]

    def _change_together(self, node: str, inputs: list, text: str) -> None:
        """What was written in the panel: in its node, or, with several of its kind chosen, in all of them (computed
        once and undone in one step)."""
        nodes = self._together if node in self._together else [node]
        if len(nodes) == 1 and len(inputs) == 1:
            self._change_text(node, inputs[0], text)
            return
        if len(nodes) == 1:
            self._change_texts(node, inputs, text)
            return
        for n in nodes:
            for input_ in inputs:
                if not self._change_text(n, input_, text, last=False):
                    break
        self.recompute()
        self._display_node(self._selection)
        self._register()

    def _change_value_together(self, node: str, input_: str, value, final: bool) -> None:
        """A value that is not written (the points of a Graph), in its node or in all those chosen with it."""
        nodes = self._together if node in self._together else [node]
        for k, n in enumerate(nodes):
            if k < len(nodes) - 1:                # the others without computing: the last one computes for all
                self._canvas.change(n, input_, value)
                if n in self.editor.boxes:
                    self.editor.boxes[n].refresh()
            else:
                self._change_value(n, input_, value, final)

    def _go_a_values(self, name: str) -> None:
        box = getattr(self, "_boxes_values", {}).get(name)
        if box is not None:
            try:
                self._scrollable_values.ensureWidgetVisible(box, 0, 12)
            except RuntimeError:                # the sliders were recreated meanwhile
                pass

    def _rename(self, old: str, new_: str) -> None:
        if self._inside is not None:
            from ..groups import INPUT, rename_input
            is_input = old in self._canvas.nodes and self._canvas.nodes[old].kind is INPUT
            try:
                self._canvas.rename(old, new_)
            except ShapeError as error:
                self._warn(str(error))
                return
            if is_input:                      # a group input: outside it keeps its wire and its slider
                kind = self._inside["type"]
                around = self._graphs_around()
                rename_input(around[-1], kind, old, new_.strip(), tuple(around[:-1]))
                for c in self.project.controls:
                    if c.input_ == old and c.node in self.project.graph.nodes \
                            and self.project.graph.nodes[c.node].kind.name == kind:
                        c.input_ = new_.strip()
            self.editor.rename_box(old, new_.strip())
            self._after_edit()
            return
        p = self.project
        try:
            p.graph.rename(old, new_)
        except ShapeError as error:
            self._warn(str(error))
            self._display_node(old)
            return
        new_ = new_.strip()
        p.export = [new_ if n == old else n for n in p.export]
        p.view = {(new_ if n == old else n): v for n, v in p.view.items()}
        for style_name in p.view.values():          # those painted by its value stay with it
            if style_name.get("by") == old:
                style_name["by"] = new_
        for c in p.controls:
            if c.node == old:
                c.node = new_
        self.editor.rename_box(old, new_)
        self._create_controls()
        self.recompute()
        self._display_node(new_)
        self._register()

    # --- Groups of nodes (Delivery 6) ---------------------------------------------------

    def group(self) -> None:
        """The chosen nodes, in a group: the name of the new kind is asked for («sun fin»)."""
        from ..groups import group_in_project
        p = self.project
        names = [c.node.name for c in self.editor.chosen()]
        if len(names) < 2:
            self._warn(tr('To group, select two or more nodes.'))
            return
        i = 1
        while f"{tr('group')} {i}" in p.graph.kinds or f"{tr('group')} {i}" in p.graph.definitions:
            i += 1
        name, ok = ask_text(
            self, tr('Group'), tr('Group name: the new node type (for example, “sunshade”).'),
            text=f"{tr('group')} {i}")
        if not ok:
            return
        if self._inside is not None:
            self._group_inside(names, name)
            return
        p.positions, p.thumbnails = self.editor.positions(), self.editor.thumbnails()
        try:
            node = group_in_project(p, names, name)
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not group'), str(error))
            return
        except Exception as error:                   # noqa: BLE001 (never a project left half grouped)
            self._restore(self._state)
            QMessageBox.warning(self, tr('Could not group'), str(error))
            return
        self._after_restructure(node.name)
        self.statusBar().showMessage(tr('{n} nodes grouped into “{group}” (Ctrl+Shift+G to ungroup).').format(
            n=len(names), group=node.name))

    def ungroup(self) -> None:
        from ..groups import ungroup_in_project
        p = self.project
        groups = [c.node.name for c in self.editor.chosen() if c.node.kind.name in p.graph.definitions]
        if not groups:
            self._warn(tr('To ungroup, select a group.'))
            return
        if self._inside is not None:
            self._ungroup_inside(groups)
            return
        p.positions, p.thumbnails = self.editor.positions(), self.editor.thumbnails()
        loose = []
        try:
            for name in groups:
                loose.extend(ungroup_in_project(p, name).values())
        except Exception as error:                   # noqa: BLE001 (never a project left half ungrouped)
            self._restore(self._state)
            QMessageBox.warning(self, tr('Could not ungroup'), str(error))
            return
        self._after_restructure(*loose)
        self.statusBar().showMessage(tr('Ungrouped: the nodes are loose again.'))

    def _group_inside(self, names: list[str], kind: str) -> None:
        """Grouping inside a group: the new group goes into the project's groups, and the one around holds it."""
        from ..groups import boxes_grouped, group
        g = self._canvas
        positions = self.editor.positions()
        try:
            definition, node = group(g, names, kind, [], positions)
        except ShapeError as error:
            QMessageBox.warning(self, tr('Could not group'), str(error))
            return
        except Exception as error:                   # noqa: BLE001 (never a project left half grouped)
            self._restore(self._state)
            QMessageBox.warning(self, tr('Could not group'), str(error))
            return
        self.editor.display(g, boxes_grouped(positions, names, definition, node.name), frame=False)
        self._apply_inside()
        self.editor.select(node.name)
        self._register()
        self.statusBar().showMessage(tr('{n} nodes grouped into “{group}” (Ctrl+Shift+G to ungroup).').format(
            n=len(names), group=node.name))

    def _ungroup_inside(self, groups: list[str]) -> None:
        from ..groups import boxes_ungrouped, ungroup
        g, p = self._canvas, self.project
        positions, loose, kinds = self.editor.positions(), [], set()
        try:
            for name in groups:
                definition = p.graph.definitions[g.nodes[name].kind.name]
                kinds.add(definition.name)
                taken = {}
                new = ungroup(g, name, None, taken)
                positions = boxes_ungrouped(positions, name, definition, new, taken)
                loose.extend(new.values())
        except Exception as error:                   # noqa: BLE001 (never a project left half ungrouped)
            self._restore(self._state)
            QMessageBox.warning(self, tr('Could not ungroup'), str(error))
            return
        self.editor.display(g, positions, frame=False)
        self._apply_inside(forget=tuple(kinds))
        self.editor.graph_scene.clearSelection()
        for n in loose:
            if n in self.editor.boxes:
                self.editor.boxes[n].setSelected(True)
        self._register()
        self.statusBar().showMessage(tr('Ungrouped: the nodes are loose again.'))

    @property
    def _canvas(self):
        """The graph the canvas shows: the project's, or the one inside a group."""
        return self._inside["graph"] if self._inside is not None else self.project.graph

    def _collect_canvas(self) -> None:
        """Where the boxes are: in the project, or (inside a group) in the group's definition."""
        p = self.project
        if p is None:
            return
        if self._inside is not None:
            definition = p.graph.definitions.get(self._inside["type"])
            if definition is not None:
                definition.positions = self.editor.positions()
        else:
            p.positions, p.thumbnails = self.editor.positions(), self.editor.thumbnails()
            p.notes = self.editor.notes()

    @property
    def _inside(self) -> dict | None:
        """Inside a group: the innermost one entered ({"node", "type", "graph", "view"}); None outside them."""
        levels = self.__dict__.get("_levels")
        return levels[-1] if levels else None

    @_inside.setter
    def _inside(self, value) -> None:
        self._levels = [] if value is None else [value]

    def _graphs_around(self) -> list:
        """The project's graph and those of the groups entered, except the innermost one (the canvas)."""
        return [self.project.graph] + [d["graph"] for d in self._levels[:-1]]

    def enter_group(self, name: str, view=None, frame: bool = True) -> None:
        """The canvas shows the group inside, computed with what reaches this node (also from inside another
        group: one level deeper)."""
        from ..groups import inner
        p = self.project
        if p is None:
            return
        g_out = self._canvas
        if name not in g_out.nodes or g_out.nodes[name].kind.name not in p.graph.definitions:
            return
        self._collect_canvas()
        kind = g_out.nodes[name].kind.name
        try:
            g, positions = inner(g_out, name, [d["type"] for d in self._levels])
        except ShapeError as error:
            self._warn(str(error))
            return
        outside = view or (self.editor.transform(), self.editor.mapToScene(self.editor.viewport().rect().center()))
        g.folder = p.graph.folder
        self._levels.append({"node": name, "type": kind, "graph": g, "view": outside})
        self.editor.display(g, positions, frame=frame)
        if not positions:
            self.editor.arrange_all()
        self._mark_inside()
        self.panel_node.display(None)
        self.recompute()
        self.statusBar().showMessage(tr('Inside “{group}”: what you change applies to every “{kind}”. “Leave group” to go back.').format(group=name, kind=kind))

    def quit_group(self) -> None:
        """One level out: to the group around (or to the project)."""
        if self._inside is None:
            return
        self._collect_canvas()
        p = self.project
        d = self._levels.pop()
        if self._inside is not None:
            around = self._inside
            self.editor.display(around["graph"], p.graph.definitions[around["type"]].positions, frame=False)
        else:
            self.editor.display(p.graph, p.positions, frame=False, thumbnails=p.thumbnails, notes=p.notes)
        transformed, centre = d["view"]
        self.editor.setTransform(transformed)
        self.editor.centerOn(centre)
        self._mark_inside()
        self._create_controls()
        self.recompute()
        if d["node"] in self.editor.boxes:
            self.editor.select(d["node"])
        self._register("mover cajas")

    def _mark_inside(self) -> None:
        """The canvas title says where one is; the button to leave, only inside a group."""
        d = self._inside
        self.card_nodes.title.setText(tr('Nodes') if d is None else tr('Nodes  ›  {group}').format(
            group="  ›  ".join(level["node"] for level in self._levels)))
        self.panels["nodes"].setWindowTitle(self.card_nodes.title.text())
        self._button_quit.setVisible(d is not None)

    def _apply_inside(self, forget: tuple = ()) -> None:
        """What was edited inside, to the group's definition and to all its nodes; with groups inside groups, up
        through each one around, to the project. Then, to compute. `forget`: groups that may have been left unused
        (ungrouped inside): they leave the project's groups."""
        from ..groups import _forget_if_unused, inner_apply, refresh_kinds
        p, levels = self.project, self._levels
        try:
            for i in range(len(levels) - 1, -1, -1):
                d = levels[i]
                around = levels[i - 1]["graph"] if i else p.graph
                others = tuple(x for x in [p.graph] + [level["graph"] for level in levels[:i]] if x is not around)
                inner_apply(around, d["type"], d["graph"], self.editor.positions() if i == len(levels) - 1 else None,
                            d["node"], others)
        except ShapeError as error:
            self._warn(str(error))
            self._compute_inside()
            return
        for kind in forget:
            _forget_if_unused(p.graph, kind)
        refresh_kinds(p.graph, [(d["graph"], [x["type"] for x in levels[:k + 1]]) for k, d in enumerate(levels)])
        # The sliders of inputs that no longer exist, out.
        before = len(p.controls)
        definitions = p.graph.definitions
        p.controls = [c for c in p.controls if c.node not in p.graph.nodes
                       or p.graph.nodes[c.node].kind.name not in definitions
                       or c.input_ in definitions[p.graph.nodes[c.node].kind.name].inputs]
        if len(p.controls) != before:
            self._create_controls()
        self.recompute()

    def _compute_inside(self) -> None:
        """Inside a group: its nodes computed (shapes and errors). The process that computes sends them computed
        (`_take_results`); without it, here: its inputs up to date with what reaches the group node, and each node."""
        from ..groups import refresh_inputs
        d = self._inside
        taken = self.__dict__.pop("_inside_taken", None)
        if taken is not None and taken[0] is d["graph"]:
            self.editor.sync(set(taken[1]))
            return
        around = self._levels[-2]["graph"] if len(self._levels) > 1 else self.project.graph
        refresh_inputs(around, d["node"], d["graph"])
        failures = set()
        for n in d["graph"].nodes:
            try:
                d["graph"].value(n)
            except NodeError as error:
                failures.add(error.node.name)
        self.editor.sync(failures)

    def save_in_library(self, name: str) -> None:
        """The group of that node, to the library: it can be added in any project (Tab)."""
        self._save_kind_in_library(self._canvas.nodes[name].kind.name)

    def _save_kind_in_library(self, kind: str) -> None:
        """A group of the project, to the library (from a node of it, or from the Library panel)."""
        from .. import library as library
        p = self.project
        help, ok = ask_text(
            self, tr('Save to library'),
            tr('What “{group}” does (shown when the pointer rests on it, in Tab and in the library). Optional: left '
               'empty, it is written by itself: what it takes, what it gives and its nodes.').format(group=kind),
            text=p.graph.definitions[kind].help, limit=200)
        if not ok:
            return
        try:
            filepath = library.save(p.graph, kind, help)
        except FileExistsError:
            if QMessageBox.question(self, tr('Save to library'),
                                    tr('There is already a “{group}” in the library. Replace it?').format(group=kind)) \
                    != QMessageBox.StandardButton.Yes:
                return
            filepath = library.save(p.graph, kind, help, replace=True)
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Could not save'), str(error))
            return
        self._register()                         # the description also stays in the project
        self._show_library(reread=True)
        self.statusBar().showMessage(tr('“{group}” is in the library: Tab in any project ({path}).').format(
            group=kind, path=filepath), 8000)

    def open_library(self) -> None:
        """The library folder in the file manager (to delete, rename or share groups)."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from .. import library as library
        folder = library.folder()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _after_restructure(self, *pick: str) -> None:
        """After grouping or ungrouping: the canvas, the sliders and the computation, again."""
        p = self.project
        p.notes = self.editor.notes()                # the annotations stay where they were
        self.editor.display(p.graph, p.positions, frame=False, thumbnails=p.thumbnails, notes=p.notes)
        self._create_controls()
        self.recompute()
        self.editor.graph_scene.clearSelection()
        for n in pick:
            if n in self.editor.boxes:
                self.editor.boxes[n].setSelected(True)
        self._register()

    def _change_texts(self, node: str, inputs: list, text: str) -> None:
        """The same value typed for several inputs at once (dragging over them in the panel): one change."""
        for k, input_ in enumerate(inputs):
            if not self._change_text(node, input_, text, last=k == len(inputs) - 1):
                return

    def _change_text(self, node: str, input_: str, text: str, last: bool = True) -> bool:
        if input_ == "mode" and self._drawing == node:   # from control points to pen (or the other way round)
            self.finish_drawing()
        g = self._canvas
        kind_input = g.nodes[node].kind.input_(input_)
        options = kind_input.options
        if kind_input.levels_of:     # a level («along»): written in the language set («fila»), as it is called («row»)
            origin = g.nodes[node].inputs.get(kind_input.levels_of)
            levels = getattr(getattr(origin, "_value", None), "levels", ())
            text = language.on_original(text.strip(), levels)
        text = language.on_original(text.strip(), options)
        before = getattr(g.nodes[node], "_value", None)
        if options and self._inside is None and node not in self.project.export and \
                (before is None or getattr(before, "kind", None) is None):
            # A node that gave a number (or nothing) and now, with another option («show» deformed), may give
            # geometry: like a new one, it is seen in 3D as soon as it does.
            self.editor.new.add(node)
        if input_ == "level" or input_.startswith("level_"):   # «tramo» written in Spanish: the usual «segment»
            current = g.nodes[node].inputs.get(input_)
            text = language.on_original(text, [current] if isinstance(current, str) else [])
        try:
            # A length: a plain number, in the chosen unit (40 with centimetres is 0.4 m).
            # An option of the list stays as it is (the «not» operation is not a yes/no).
            value = (text if options and text in options
                     else values.read_lengths(text) if values.is_length(g.nodes[node], input_)
                     else read_value(text))
            if value is None:
                value = g.nodes[node].kind.input_(input_).default
            previous = g.nodes[node].inputs.get(input_)
            g.change(node, input_, value)
            followers = []
            if input_ in LEVEL_INPUTS and not kind_input.levels_of and isinstance(previous, str) \
                    and isinstance(value, str) and previous.strip() and value.strip() and previous != value:
                # The name of a level changed: the nodes after it that pick that level by its name, too.
                followers = g.rename_level(node, previous.strip(), value.strip())
        except ShapeError as error:
            self._warn(str(error))
            return False
        for other in followers:
            if other in self.editor.boxes:
                self.editor.boxes[other].refresh()
        if followers:
            self._say_after = tr('The level is “{level}” now, also in: {nodes}.').format(
                level=tr(value.strip()), nodes=", ".join(followers))
        self.editor.boxes[node].refresh()
        if self._inside is not None:
            if last:
                self._after_edit()
            return True
        if any(c.node == node and c.input_ == input_ for c in self.project.controls):
            if not _is_number(self.project.graph.nodes[node].inputs[input_]):   # it became a list
                self.project.controls = [c for c in self.project.controls
                                           if not (c.node == node and c.input_ == input_)]
            self._adjust_control(node, input_)
            self._create_controls()
        if not last:                                 # several at once: computed and registered with the last one
            return True
        self.recompute()
        self._display_node(node)
        self._register()
        return True

    def _adjust_control(self, node: str, input_: str) -> None:
        """If a value outside its slider's range was written, the range widens."""
        v = self.project.graph.nodes[node].inputs[input_]
        fixed_values = numbers_items(v) or ([v] if isinstance(v, (int, float)) else [])
        for c in self.project.controls:
            if c.node == node and c.input_ == input_ and fixed_values:
                c.minimum, c.maximum = min(c.minimum, *fixed_values), max(c.maximum, *fixed_values)

    # --- Drawing in the view (Drawn curve) ------------------------------------------

    _drawing: str | None = None

    def _instructions_drawing(self) -> str:
        d = self.viewer.drawing
        grid = (tr('only on the {step} m grid crossings (Ctrl: free)') if d.adjust
                   else tr('free (Ctrl: only on the {step} m grid crossings)')).format(step=f"{d.step:g}")
        help_ = self.viewer.bar_drawing.help_text
        if self.project is not None and self._drawing in self.project.graph.nodes \
                and self.project.graph.nodes[self._drawing].kind.name == 'Equilibrium':
            help_ = tr('drag a particle: it is held where you let it go, and the shape settles again (Alt: up or '
                       'down) · squares: the supports · right-click a particle: hold it here, or let it go') + \
                " · " + tr('double click a point: its exact coordinates')
        return tr('Editing «{node}»: {help} · {grid} · Enter or Esc finishes').format(
            node=self._drawing, help=help_, grid=grid)

    def _change_grid_drawing(self, step: float, adjust: bool) -> None:
        self.viewer.drawing.change_grid(step, adjust)
        self.viewer.bar_drawing.put_grid(step, adjust)
        if self._drawing is not None:
            self.statusBar().showMessage(self._instructions_drawing())

    def draw(self, node: str) -> None:
        """Starts drawing the points of a Drawn curve in the 3D view (or finishes, if it was already drawing)."""
        if self._drawing == node:
            self.finish_drawing()
            return
        self.finish_drawing()
        p = self.project
        if p is None or self._inside is not None or node not in p.graph.nodes:
            return
        if node not in p.export:                   # what is drawn, in view
            p.export.append(node)
        if p.graph.nodes[node].kind.name == 'Edit mesh':
            self._edit_mesh(node)
            return
        if p.graph.nodes[node].kind.name == 'Equilibrium':
            self._edit_supports(node)
            return
        self._drawing = node
        self.panel_node.drawing = node
        es_nurbs = p.graph.nodes[node].kind.name == 'NURBS Curve'
        with_pen = es_nurbs and p.graph.nodes[node].inputs.get('mode') == 'pen'
        input_ = "stroke" if with_pen else "points"
        points = p.graph.nodes[node].inputs[input_] or []
        self.viewer.drawing.start(points, lambda list_, final, n=node, e=input_: self._drawn_points(n, list_, final, e),
                                  self._drawing_finished, with_weights=es_nurbs and not with_pen,
                                  curve=(lambda n=node: self._curve_what_draws(n)) if es_nurbs else None,
                                  pen=with_pen, on_dismiss=lambda: self.viewer.bar_drawing.closing.setChecked(True),
                                  samples=lambda n=node: self._samples_of(n))
        n = p.graph.nodes[node]
        closed = n.inputs.get("closed") if "closed" in n.inputs and not isinstance(n.inputs["closed"], Node) \
            else None
        self.viewer.bar_drawing.display(node, None if closed is None else bool(closed), es_nurbs, with_pen)
        self.viewer.bar_drawing.put_tool(self.viewer.drawing.tool)
        self.recompute()                              # the curve alone in the view (or with the rest, faint)
        self._put_strip_nodes()
        self._display_node(node)
        self.statusBar().showMessage(self._instructions_drawing())

    def _edit_mesh(self, node: str) -> None:
        """Edit mesh: the 3D view becomes the editor of the vertices of the mesh that comes in (with the moves
        already kept), joined by its edges. Each drag keeps only how much each vertex moved."""
        from ..mesh_tools import editable_mesh
        g = self.project.graph
        source = g.nodes[node].inputs.get("mesh")
        try:
            base = editable_mesh(g.value(source.name) if isinstance(source, Node) else None)
        except (ShapeError, NodeError) as error:
            self.statusBar().showMessage(tr('To edit «{node}», connect a mesh to its input «mesh» ({error}).').format(
                node=node, error=str(error)))
            return
        start = np.array(base.values, dtype=float)
        for row in g.nodes[node].inputs.get("moves") or ():
            if 0 <= int(row[0]) < len(start):
                start[int(row[0])] += np.asarray(row[1:4], dtype=float)
        pairs = {(min(a, b), max(a, b)) for f in base.kind.faces for a, b in zip(f, f[1:] + f[:1])}
        self._drawing = node
        self.panel_node.drawing = node
        base_points = np.array(base.values, dtype=float)
        self.viewer.drawing.start([list(map(float, q)) for q in start],
                                  lambda list_, final, n=node: self._moved_vertices(n, base_points, list_, final),
                                  self._drawing_finished, edges=sorted(pairs))
        self.viewer.bar_drawing.display(node, None, False, mesh=True)
        self.viewer.bar_drawing.put_grid(self.viewer.drawing.step, self.viewer.drawing.adjust)
        self.viewer.bar_drawing.put_tool(self.viewer.drawing.tool)
        self.recompute()
        self._display_node(node)
        self.statusBar().showMessage(self._instructions_drawing())

    def _edit_supports(self, node: str) -> None:
        """Move supports: the 3D view shows the particles of an Equilibrium at rest, joined by its springs, the
        supports as squares. Dragging a particle holds it where it is let go (a support by hand), and the shape settles
        again; the right-click menu holds one where it is, or lets a support by hand go."""
        g = self.project.graph
        try:
            value = g.value(node)
        except (ShapeError, NodeError) as error:
            self.statusBar().showMessage(tr('To move the supports of «{node}», it must hang first ({error}).').format(
                node=node, error=str(error)))
            return
        net = value.network
        self._drawing = node
        self.panel_node.drawing = node
        self._supports_base = np.array(net["rest"], dtype=float)
        self.viewer.drawing.start([list(map(float, q)) for q in net["rest"]],
                                  lambda list_, final, n=node: self._moved_supports(n, list_, final),
                                  self._drawing_finished, edges=[tuple(map(int, e)) for e in net["springs"]],
                                  marked=net["fixed"], on_mark=lambda i, yes, n=node: self._mark_support(n, i, yes))
        self.viewer.bar_drawing.display(node, None, False, mesh=True)
        self.viewer.bar_drawing.put_grid(self.viewer.drawing.step, self.viewer.drawing.adjust)
        self.viewer.bar_drawing.put_tool(self.viewer.drawing.tool)
        self.recompute()
        self._display_node(node)
        self.statusBar().showMessage(self._instructions_drawing())

    def _hand_rows(self, node: str) -> list:
        return [list(map(float, r[:6])) for r in (self.project.graph.nodes[node].inputs.get("hand_supports") or ())
                if len(r) >= 6]

    def _put_hand_support(self, node: str, i: int, where, rows: list) -> list:
        """The support by hand of particle i, at `where` (it replaces the one it had)."""
        start = np.asarray(self.project.graph.value(node).network["start"][i], dtype=float)
        rows = [r for r in rows if np.linalg.norm(np.asarray(r[:3]) - start) > 1e-9]
        return rows + [[*map(float, np.round(start, 6)), *map(float, np.round(np.asarray(where, dtype=float), 6))]]

    def _moved_supports(self, node: str, list_: list, final: bool) -> None:
        """Particles dragged in the view: each one, a support by hand where it is now."""
        if self.project is None or node not in self.project.graph.nodes:
            self.finish_drawing()
            return
        now = np.asarray(list_, dtype=float)[:, :3]
        base = self.__dict__.get("_supports_base")
        if base is None or len(base) != len(now):
            return
        moved = np.flatnonzero(np.abs(now - base).max(axis=1) > 1e-9)
        if not len(moved):
            return
        rows = self._hand_rows(node)
        for i in moved:
            rows = self._put_hand_support(node, int(i), now[i], rows)
        self._supports_base = now.copy()
        self.project.graph.change(node, "hand_supports", rows)
        self.editor.boxes[node].refresh()
        # While dragging, only if the last one is done (a big membrane takes a while: they would pile up); on
        # letting go, always.
        if final or self._in_progress is None:
            self.recompute()
        if final:
            self._register()
            self._display_node(node)

    def _mark_support(self, node: str, i: int, hold: bool) -> None:
        """The menu of a particle: hold it where it is now, or let its support by hand go."""
        if self.project is None or node not in self.project.graph.nodes:
            return
        rows = self._hand_rows(node)
        if hold:
            rows = self._put_hand_support(node, i, self._supports_base[i], rows)
        else:
            start = np.asarray(self.project.graph.value(node).network["start"][i], dtype=float)
            before = len(rows)
            rows = [r for r in rows if np.linalg.norm(np.asarray(r[:3]) - start) > 1e-9]
            if len(rows) == before:
                self.statusBar().showMessage(tr('That support is not by hand: it comes from «supports» or «more '
                                                'supports».'))
                return
        self.project.graph.change(node, "hand_supports", rows)
        self.editor.boxes[node].refresh()
        self.recompute()
        self._register()
        self._display_node(node)

    def _moved_vertices(self, node: str, base: np.ndarray, list_: list, final: bool) -> None:
        """The vertices dragged in the view, kept as moves: [vertex, dx, dy, dz] for those that are not where the
        mesh puts them."""
        if self.project is None or node not in self.project.graph.nodes:
            self.finish_drawing()
            return
        delta = np.round(np.asarray(list_, dtype=float)[:, :3] - base, 4)
        moves = [[int(i), *map(float, delta[i])] for i in np.flatnonzero(np.abs(delta).max(axis=1) > 1e-9)]
        self.project.graph.change(node, "moves", moves)
        self.editor.boxes[node].refresh()
        self.recompute()
        if final:
            self._register()
            self._display_node(node)

    # --- The knots of the curve being edited (the strip under the editor's bar) ---------------------

    def _nodes_of(self, node: str):
        """(points, weights of each point, degree, complete knots) of the open NURBS being edited with control points;
        None if it cannot be (closed, pen, connected values, a list of knots that is not valid)."""
        from .. import geometry as geo
        n = self.project.graph.nodes.get(node) if self.project is not None else None
        d = self.viewer.drawing
        if n is None or n.kind.name != 'NURBS Curve' or d.pen or not d.active or len(d.points) < 2:
            return None
        e = n.inputs
        if any(isinstance(e.get(k), Node) for k in ("degree", "weights", "knots", "list", "closed")) or e.get("closed"):
            return None
        try:
            k = max(1, min(int(e["degree"]), geo.MAX_DEGREE_NURBS, len(d.points) - 1))
            weights = geo._values_items(e["weights"], "weights")
            weights = (np.repeat(weights, len(d.points)) if len(weights) == 1 else weights) * d.weights
            to_hand = geo._values_items(e["list"], "list") if e['knots'] == 'by hand' else np.zeros(0)
            return d.points, weights, k, geo._open_nodes(d.points, k, e["knots"], to_hand)
        except (ShapeError, ValueError, TypeError, KeyError):
            return None

    def _put_strip_nodes(self, highlighted=None) -> None:
        """The strip of knots and its marks on the curve, up to date (or out, if they do not go)."""
        from .. import geometry as geo
        strip, d = self.viewer.strip_nodes, self.viewer.drawing
        data_items = self._nodes_of(self._drawing) if self._drawing else None
        if data_items is None or not self.viewer.bar_drawing.see_nodes.isChecked():
            strip.hide()
            d.mark_nodes(None)
            return
        points, weights, k, knots = data_items
        inner = list(knots[k + 1:len(points)])
        strip.put(inner, k)
        strip.show()
        marks = geo.points_in_nurbs(points, weights, k, knots, inner) if inner else None
        point = geo.points_in_nurbs(points, weights, k, knots, [highlighted])[0] if highlighted is not None else None
        d.mark_nodes(marks, point)

    def _node_over(self, u) -> None:
        self._put_strip_nodes(u)

    def _moved_nodes(self, inner: list, final: bool) -> None:
        """A knot was dragged on the strip: the curve goes to «by hand» knots, with the new list."""
        node = self._drawing
        if node is None or self.project is None:
            return
        g = self.project.graph
        g.change(node, "knots", "by hand")
        g.change(node, "list", "; ".join(text_value(round(u, 4)) for u in inner))
        self.editor.boxes[node].refresh()
        self.recompute()
        if final:
            self._register()
            self._display_node(node)
            self.statusBar().showMessage(tr('Knots «by hand»: the list is in the node’s «More settings».'))

    def _insert_node(self, u: float) -> None:
        """Double-click on the strip (or repeat a knot): one more knot and a control point, without changing the shape."""
        from .. import geometry as geo
        node = self._drawing
        data_items = self._nodes_of(node) if node else None
        if data_items is None:
            return
        points, weights, k, knots = data_items
        new, new_weights = geo.insert_node(points, weights, k, knots, u)
        g = self.project.graph
        inner = sorted(list(knots[k + 1:len(points)]) + [u])
        g.change(node, "knots", "by hand")
        g.change(node, "list", "; ".join(text_value(round(x, 4)) for x in inner))
        g.change(node, "weights", 1.0)                 # the weights, all in the drawn points
        d = self.viewer.drawing
        d.points, d.weights, d.chosen = np.round(new, 4), np.round(new_weights, 6), set()
        d._paint()
        d._warn(True)                               # it saves the points, recomputes and stays to be undone

    def _remove_node(self, i: int) -> None:
        """Right-click → remove on the strip: one knot and one control point fewer (the curve, as alike as possible)."""
        from .. import geometry as geo
        node = self._drawing
        data_items = self._nodes_of(node) if node else None
        if data_items is None:
            return
        points, weights, k, knots = data_items
        try:
            new, new_weights = geo.remove_node(points, weights, k, knots, i)
        except ShapeError as error:
            self.statusBar().showMessage(str(error))
            return
        inner = list(knots[k + 1:len(points)])
        del inner[i]
        g = self.project.graph
        if inner:
            g.change(node, "knots", "by hand")
            g.change(node, "list", "; ".join(text_value(round(x, 4)) for x in inner))
        else:                                         # without inner knots: uniform is the same
            g.change(node, "knots", "uniform")
            g.change(node, "list", "")
        g.change(node, "weights", 1.0)
        d = self.viewer.drawing
        d.points, d.weights, d.chosen = np.round(new, 4), np.round(new_weights, 6), set()
        d._paint()
        d._warn(True)

    def _samples_of(self, node: str):
        """The points of the already computed curve of a node (a single curve), or None."""
        n = self.project.graph.nodes.get(node) if self.project is not None else None
        value = getattr(n, "_value", None)
        if value is None or value.kind is None or not value.kind.curve or value.levels:
            return None
        return value.values.reshape(-1, 3)

    def _curve_what_draws(self, node: str):
        """(degree, knot mode, closed) of the NURBS being edited, if they are fixed values (not connected)."""
        if self.project is None or node not in self.project.graph.nodes:
            return None
        e = self.project.graph.nodes[node].inputs
        values = (e.get("degree"), e.get("knots"), e.get("closed"))
        if any(isinstance(v, Node) for v in values):
            return None
        try:
            return int(values[0]), values[1], bool(values[2])
        except (TypeError, ValueError):
            return None

    def _dismiss_drawing(self, yes: bool) -> None:
        """«Closed» on the curve editor's bar: the curve being edited goes round (or not)."""
        if self._drawing is not None:
            self._change_value(self._drawing, "closed", bool(yes), True)
            self._display_node(self._selection)

    def _drawn_points(self, node: str, list_: list, final: bool, input_: str = "points") -> None:
        if self.project is None or node not in self.project.graph.nodes:
            self.finish_drawing()
            return
        self.project.graph.change(node, input_, list_)
        self.editor.boxes[node].refresh()
        self.recompute()
        if final:
            self._register()
            self._display_node(node)

    def _drawing_finished(self) -> None:
        """The view stopped drawing (Enter, Esc or the button)."""
        node, self._drawing = self._drawing, None
        self.panel_node.drawing = None
        self.viewer.bar_drawing.hide()
        self.viewer.strip_nodes.hide()
        if self.project is not None:
            self.recompute()                          # everything in view again
        if node is not None and self.project is not None and node in self.project.graph.nodes:
            self._display_node(self._selection)
        self.statusBar().showMessage(tr('Drawing finished.'))

    def finish_drawing(self) -> None:
        if self._drawing is not None:
            self.viewer.drawing.finish()

    def _toggle_slider(self, node: str, input_: str, yes: bool) -> None:
        if self._inside is not None:              # inside a group it is not seen in 3D per node
            return
        p = self.project
        p.controls = [c for c in p.controls if not (c.node == node and c.input_ == input_)]
        if yes:
            p.controls.append(control_for(p.graph, node, input_))
        self._create_controls()
        self._register()
        QTimer.singleShot(0, lambda: self._display_node(self._selection))

    def _change_color(self, node: str, color: str) -> None:
        if self._inside is not None:              # inside a group it is not seen in 3D per node
            return
        self.project.view.setdefault(node, {})["color"] = color
        self.recompute()
        self._register()
        QTimer.singleShot(0, lambda: self._display_node(self._selection))

    def _colour_by(self, node: str, by: str, gradient: str) -> None:
        """Painting it by the value of another node (or back to a single colour, with an empty `by`)."""
        if self._inside is not None or self.project is None:
            return
        style_name = self.project.view.setdefault(node, {})
        if by:
            style_name["by"], style_name["gradient"] = by, gradient
        else:
            style_name.pop("by", None)
            style_name.pop("gradient", None)
        self.recompute()
        self._register()
        QTimer.singleShot(0, lambda: self._display_node(self._selection))

    def _new_see(self, g) -> None:
        """A node just put is seen in 3D (the eye on) the first time it gives geometry. If it gives a number or a text,
        no; and afterwards, the eye belongs to whoever uses it."""
        # Those that turned on by themselves and then grew (a Point to which a grid was connected): they are turned
        # off once. Those the user turned on or off by hand are no longer in this list.
        if "_lone_switches" not in self.__dict__:
            self._on_alone = set()
        self._warning_points = ""
        for name in list(self._on_alone):
            node = g.nodes.get(name)
            value = getattr(node, "_value", None) if node is not None else None
            if node is None or name not in self.project.export:
                self._on_alone.discard(name)
                continue
            if value is not None and value.kind is not None and value.kind.name == "point" and value.levels:
                how_many = math.prod(value.sizes[n] for n in value.levels)
                if how_many > AUTOMATIC_MAX_POINTS:
                    self.project.export.remove(name)
                    self._on_alone.discard(name)
                    self._warning_points = "  ·  " + tr('“{node}” has {n} points: it is not shown in 3D on its own '
                                                      '(it is an intermediate step); turn on its eye if you want '
                                                      'to see it.').format(
                                                          node=name, n=f"{how_many:,}".replace(",", " "))
        for name in list(self.editor.new):
            node = g.nodes.get(name)
            value = getattr(node, "_value", None) if node is not None else None
            if node is not None and value is None:
                continue                              # still without a result (something is missing): it waits
            self.editor.new.discard(name)
            if value is not None and getattr(value, "kind", None) is not None and name not in self.project.export \
                    and node.kind.name != 'Info':
                # A cloud of many points (an intermediate step: the grid of a wall) does not turn on by itself:
                # it would make the view slow. The eye stays to be turned on by hand.
                how_many = math.prod(value.sizes[n] for n in value.levels) if value.levels else 1
                if value.kind.name == "point" and how_many > AUTOMATIC_MAX_POINTS:
                    self._warning_points = "  ·  " + tr('“{node}” has {n} points: it is not shown in 3D on its own '
                                                      '(it is an intermediate step); turn on its eye if you want '
                                                      'to see it.').format(
                                                          node=name, n=f"{how_many:,}".replace(",", " "))
                    continue
                self.project.export.append(name)
                self._on_alone.add(name)

    def _change_value(self, node: str, input_: str, value, final: bool) -> None:
        """A value that is not written (the points of a Graph): while dragging, it recomputes; on releasing, it stays to be
        undone."""
        g = self._canvas
        if node not in g.nodes:
            return
        g.change(node, input_, value)
        if node in self.editor.boxes:
            self.editor.boxes[node].refresh()
        if self._inside is not None:
            self._after_edit()
            return
        self.recompute()
        if final:
            self._register()

    def _toggle_number(self, node: str, yes: bool) -> None:
        """The numbers of a node in the view: they are saved with the project (and undone)."""
        if self._inside is not None or self.project is None:
            return
        style_name = self.project.view.setdefault(node, {})
        if yes:
            style_name["numbers"] = True
        else:
            style_name.pop("numbers", None)
        self.viewer.put_numbers(node, yes)
        self._register()

    def _action_items_by_selection(self) -> None:
        """What in the menu asks for something chosen, off if there is nothing: isolate (a node, or leave the isolated),
        align (two or more) and distribute (three or more)."""
        how_many = len(self.editor.chosen())
        self._action_items["isolate"].setEnabled(how_many == 1 or self._isolated is not None)
        for a in self._action_items.get("align", []):
            a.setEnabled(how_many >= 2)
        for a in self._action_items.get("distribute", []):
            a.setEnabled(how_many >= 3)

    def isolate(self, node: str | None) -> None:
        """Only `node` in the 3D view, framed (None, or the same one again: it leaves and everything goes back as it was,
        camera included). It does not change which nodes are seen: it is only for looking."""
        p = self.project
        if node is not None and node == self._isolated:        # the same one again: leave
            node = None
        if node is not None and (p is None or self._inside is not None or node not in p.graph.nodes):
            return
        if node is not None:
            value = p.graph.nodes[node]._value
            if value is None or value.kind is None:
                self.statusBar().showMessage(tr('«{node}» is not geometry: there is nothing to isolate in the view.').format(
                    node=node))
                return
            if self._isolated is None:                 # on entering: the camera of before, to go back to it
                self._isolate_camera_before = self.viewer.view.camera_position
            self._isolated = node
            self._action_items_by_selection()
            self._isolated_text.setText(tr('Isolated: «{node}». Only it in the view; everything else is unchanged.').format(
                node=node))
            self.isolated_strip.show()
            self.recompute()
            self.viewer.frame()
        elif self._isolated is not None:
            self._isolated = None
            self._action_items_by_selection()
            self.isolated_strip.hide()
            self.recompute()
            camera = getattr(self, "_isolate_camera_before", None)
            if camera is not None:
                self.viewer.view.camera_position = camera
                self.viewer.view.render()

    def _change_analysis(self, node: str, mode: str) -> None:
        """Analysing a surface in the view (its curvature or the zebra): it is saved with the project (and undone)."""
        if self._inside is not None or self.project is None:
            return
        style_name = self.project.view.setdefault(node, {})
        if mode in ("gaussian", "mean", "zebra"):
            style_name["analyze"] = mode
        else:
            style_name.pop("analyze", None)
        self.recompute()
        self._register()

    def _toggle_curvature(self, node: str, yes: bool) -> None:
        """The curvature comb of a curve in the view: it is saved with the project (and undone)."""
        if self._inside is not None or self.project is None:
            return
        style_name = self.project.view.setdefault(node, {})
        if yes:
            style_name["curvature_comb"] = True
        else:
            style_name.pop("curvature_comb", None)
        self.viewer.put_curvature(node, yes)
        self._register()

    def _change_opacity(self, node: str, opacity: float, final: bool) -> None:
        """While dragging, only the view changes; on releasing, it stays in the project (and can be undone)."""
        if self._inside is not None or self.project is None:
            return
        self.viewer.put_opacity(node, opacity)
        if final:
            style_name = self.project.view.setdefault(node, {})
            if opacity >= 1.0:
                style_name.pop("opacity", None)          # opaque: the usual, no need to save it
            else:
                style_name["opacity"] = round(opacity, 2)
            self._register()

    def _selected_names(self) -> list[str]:
        return [box.node.name for box in self.editor.chosen()]

    #: The key of a node seen from inside a group, in the 3D view (its name may be that of one outside).
    INSIDE_KEY = "\u2039inside\u203a "

    def _seen_inside(self) -> list[str]:
        """The nodes of the group one is in that are seen in 3D (those that still exist)."""
        if self._inside is None:
            return []
        g = self._canvas
        return [n for n in self._eyes_inside.get(self._inside["type"], []) if n in g.nodes]

    def _gives_geometry(self, name: str) -> bool:
        return getattr(self.project.graph.nodes[name]._value, "kind", None) is not None

    def _put_seen(self, names: list[str], said: str) -> None:
        """The nodes seen in 3D, all at once (in the order they had; the new ones after), as one change to undo."""
        p = self.project
        if p is None or self._inside is not None:     # inside a group it is not seen in 3D per node
            return
        new_ = [n for n in p.export if n in names] + [n for n in names if n not in p.export]
        if new_ == p.export:
            self.statusBar().showMessage(said, 4000)
            return
        self.__dict__.setdefault("_lone_switches", set()).difference_update(set(p.export) | set(names))
        p.export = new_
        self.recompute()
        self._register()
        self.statusBar().showMessage(said, 4000)
        QTimer.singleShot(0, lambda: self._display_node(self._selection))

    def see_only(self, names: list[str]) -> None:
        """Only these nodes seen in 3D: every other eye off."""
        if self.project is None:
            return
        names = [n for n in names if n in self.project.export or self._gives_geometry(n)]
        if not names:
            self.statusBar().showMessage(tr('Select one or more nodes that give a geometry.'), 4000)
            return
        self._put_seen(names, tr('Only {nodes} in the 3D view.').format(nodes=", ".join(f"«{n}»" for n in names)))

    def hide(self, names: list[str]) -> None:
        if self.project is None:
            return
        self._put_seen([n for n in self.project.export if n not in names],
                       tr('{n} node(s) turned off.').format(n=len([n for n in names if n in self.project.export])))

    def see_all(self) -> None:
        """Every node that gives a geometry, seen."""
        if self.project is None:
            return
        every = [n for n in self.project.graph.nodes if self._gives_geometry(n)]
        self._put_seen(self.project.export + [n for n in every if n not in self.project.export],
                       tr('Every node with a geometry, in the 3D view ({n}).').format(n=len(set(every) | set(self.project.export))))

    def hide_all(self) -> None:
        if self.project is not None:
            self._put_seen([], tr('Every eye off: Show all (Alt+H) turns them on again; Ctrl+Z undoes it.'))

    def _toggle_see(self, node: str, yes: bool) -> None:
        if self._inside is not None:              # inside a group: seen while one is inside (not saved, not undone)
            eyes = self._eyes_inside.setdefault(self._inside["type"], [])
            eyes[:] = [n for n in eyes if n != node] + ([node] if yes else [])
            self.recompute()
            QTimer.singleShot(0, lambda: self._display_node(self._selection))
            return
        self.__dict__.setdefault("_lone_switches", set()).discard(node)   # the user decided: it does not turn off by itself
        p = self.project
        p.export = [n for n in p.export if n != node] + ([node] if yes else [])
        self.recompute()
        self._register()
        QTimer.singleShot(0, lambda: self._display_node(self._selection))

    def _too_heavy(self, node: str, data) -> bool:
        """Whether a node seen in 3D has too many pieces to draw them without asking. Once drawn on purpose, it is not
        asked again unless they double."""
        weight = heaviness(data) if data is not None and getattr(data, "kind", None) is not None else 0.0
        return weight > 1 and weight > 2 * float(self.project.view.get(node, {}).get("many", 0))

    def _show_held(self, held: list[str], g) -> None:
        """The strip that says which nodes were not drawn, and how many pieces they have."""
        self._held = held
        if not held:
            self.held_strip.hide()
            return
        pieces, points = amount(g.nodes[held[0]]._value)
        if pieces > 1:
            text = tr('“{node}” has {n} pieces: drawing them would make the view slow, so it waits. Is there a digit '
                      'too many in a count?')
        else:
            text = tr('“{node}” has {n} points: drawing it would make the view slow, so it waits.')
        more = " " + tr('(And {n} more node(s).)').format(n=len(held) - 1) if len(held) > 1 else ""
        self._held_text.setText(text.format(node=held[0], n=f"{pieces if pieces > 1 else points:,}".replace(",", " "))
                                + more)
        self.held_strip.show()

    def _draw_held(self) -> None:
        """«Show them»: the held nodes are drawn, and it is remembered with the project (undone with Ctrl+Z)."""
        g = self.project.graph
        for name in self._held:
            if name in g.nodes and g.nodes[name]._value is not None:
                self.project.view.setdefault(name, {})["many"] = round(heaviness(g.nodes[name]._value), 3)
        self.recompute()
        self._register()

    def _held_off(self) -> None:
        """«Turn off its eye»: the held nodes are no longer seen in 3D."""
        held, self._held = self._held, []
        self.project.export = [n for n in self.project.export if n not in held]
        self.recompute()
        self._register()

    def _warn(self, text: str) -> None:
        self.warning.setText(f"✖ {tr(text)}")
        self.warning.show()

    # --- Compute and show ---------------------------------------------------

    # If a computation takes longer than this, it goes on in another thread and the window does not freeze: the 3D view keeps
    # the last result and «Computing… Stop» appears. If it takes less, everything happens as if at once.
    WAIT_COMPUTATION = 0.12
    # The notice appears only if the computation goes on after this (a notice seen for an instant and gone distracts).
    WARNING_COMPUTATION = 0.6
    depth_computation = True
    # The computations go to a process of their own (calculator.py): the window does not freeze, and the memory of a
    # huge one is that process's. False (or TENSELA_CALCULATE_HERE=1): in a thread of the window, as before.
    use_calculator = os.environ.get("TENSELA_CALCULATE_HERE") != "1"
    _turn = 0
    _in_progress = None
    _calculator_ = None

    def _calculator(self):
        """The process that computes, started the first time (and again if it ended); None if it cannot start."""
        if not self.use_calculator:
            return None
        if self._calculator_ is not None:              # (if its process ends, the one ready takes its place)
            return self._calculator_
        from ..calculator import Calculator
        try:
            self._calculator_ = Calculator(self._calculator_reply)
        except OSError:
            self.use_calculator = False
            return None
        return self._calculator_

    def _calculator_reply(self, reply) -> None:
        """(In the thread that reads the replies.) The reply goes with its turn; the window shows it in its thread."""
        waiting = self.__dict__.setdefault("_waiting_turns", {})
        if reply.get("op") == "at":                  # the node it starts: said in the strip «Calculating…»
            self._computing_node.emit(reply["turn"], reply["node"])
            return
        if reply.get("op") == "ended":               # the process ended by itself: the turn will not come
            reply = {"turn": reply.get("turn"), "ended": True, "node": reply.get("node")}
        turn = reply.get("turn")
        entry = self.__dict__.get("_results", {}).get(turn)
        if entry is None:
            return
        entry[2].update(reply)
        event = waiting.pop(turn, None)
        if event is not None:
            event.set()
        self._computation_finished.emit(turn)

    #: A new request while the process has been longer than this in a node of what no longer serves: it is closed and
    #: the one ready takes its place (it does not wait for that node to end).
    STUCK_SECONDS = 0.5

    def _compute_apart(self, calculator, g, before: dict, wanted: list | None = None) -> bool:
        """Hands the computation to the process; it waits a moment for it (most are quick). False if it could not."""
        self._turn += 1
        turn, result = self._turn, {"version": g.version}
        self._results = getattr(self, "_results", {})
        self._results[turn] = (g, before, result)
        levels = [(d["node"], d["graph"]) for d in self.__dict__.get("_levels") or []]   # the groups entered
        result["levels"] = [graph for _, graph in levels]
        closure = g.nodes if wanted is None else _feeding(g, wanted)
        missing = [name for name, node in g.nodes.items() if node._value is None and name in closure]
        if not missing and all(x._value is not None for _, graph in levels for x in graph.nodes.values()):
            # everything has its result (another tab, a view change…)
            result.update({"values": {}, "computed": [], "errors": [], "ms": 0.0})
            if levels:                               # (a node that fails has no result: none fails inside)
                self._inside_taken = (levels[-1][1], [])
            self._on_finish_computation(turn)
            return True
        if calculator.stuck_for() > self.STUCK_SECONDS:
            calculator.restart()
        event = threading.Event()
        self.__dict__.setdefault("_waiting_turns", {})[turn] = event
        from ..calculator import request
        message = request(g, turn, id(self.project), g.folder, language.LANGUAGE, levels, wanted)
        if not calculator.knows(id(self.project)):   # a process that does not know it: what feeds what is missing
            message["seed"] = self._seed(g, missing + [n for n, _ in levels[:1] if n in g.nodes])
        if not calculator.send(message):
            self._results.pop(turn, None)
            self._waiting_turns.pop(turn, None)
            return False
        if event.wait(self.WAIT_COMPUTATION):
            self._on_finish_computation(turn)
        else:
            self._in_progress = turn
            QTimer.singleShot(int((self.WARNING_COMPUTATION - self.WAIT_COMPUTATION) * 1000),
                              lambda: self._warn_what_computes(turn))
        return True

    def _seed(self, g, missing: list[str]) -> dict:
        """The results the window has of the nodes that feed those without one (a new process starts from them, it
        does not compute the whole project again)."""
        seed = {}
        for name in missing:
            for value in g.nodes[name].inputs.values():
                if isinstance(value, Node) and value._value is not None:
                    seed[value.name] = value._value
        return seed

    def _say_computing_node(self, turn: int, node: str) -> None:
        if turn == self._turn and (node in self.project.graph.nodes or node in self._canvas.nodes):
            self._computing_text.setText(tr('Calculating «{node}»… Meanwhile the view shows the last result.')
                                         .format(node=node))

    def _take_results(self, g, result: dict) -> dict:
        """The results the process sent, into the nodes of the window; its errors, as the window's."""
        with g._lock:
            for name, value in result.get("values", {}).items():
                node = g.nodes.get(name)
                if node is not None:
                    node._value = value
            for name in result.get("computed", []):
                if name in g.nodes:
                    g.nodes[name].evaluations += 1
        errors = {}
        for name, expected, text, trace in result.get("errors", []):
            if name not in g.nodes:
                continue
            if expected:
                error = NodeError.__new__(NodeError)
                ShapeError.__init__(error, text)
                error.node = g.nodes[name]
            else:
                error = _FailureApart(text, trace)
            errors[name] = error
        # Inside the groups entered (if one is still inside the same ones): their results, and the errors of the
        # innermost one, for its canvas.
        entered = [d["graph"] for d in self.__dict__.get("_levels") or []]
        sent = result.get("levels") or []
        for k, level in enumerate(result.get("inside") or []):
            if k >= len(entered) or k >= len(sent) or sent[k] is not entered[k]:
                break
            inner = entered[k]
            with inner._lock:
                for name, value in level["values"].items():
                    if name in inner.nodes:
                        inner.nodes[name]._value = value
            if k == len(entered) - 1:
                self._inside_taken = (inner, [e[0] for e in level["errors"]])
        return errors

    def recompute(self) -> None:
        """Computes all the nodes, shows in 3D those that are seen and marks those that fail."""
        g = self.project.graph
        g.folder = self.filepath.parent if self.filepath else None   # where the images it reads are
        before = {n.name: n.evaluations for n in g.nodes.values()}
        wanted = self._wanted(g)
        self._closure = None if wanted is None else _feeding(g, wanted)
        calculator = self._calculator() if self.depth_computation else None
        if calculator is not None and self._compute_apart(calculator, g, before, wanted):
            return
        if not self.depth_computation or self._inside is not None:
            start = time.perf_counter()
            errors = self._errors(g.compute_all(wanted))
            self._apply_computation(g, errors, (time.perf_counter() - start) * 1000, before)
            return
        self._turn += 1
        turn, result = self._turn, {}

        def compute():
            start = time.perf_counter()
            try:
                with self._lock_threads:
                    self._threads[turn] = threading.current_thread()
                    memory_cap(True)            # (with the free memory of now)
                result["errors"] = g.compute_all(wanted)
                result["version"] = g.version
            except Cancelled:
                result["cancelled"] = True
            except Exception as e:                  # it should not happen: «Computing…» must not stay forever
                result["failure"] = e
            finally:
                with self._lock_threads:
                    self._threads.pop(turn, None)
                    if not self._threads:
                        memory_cap(False)
            result["ms"] = (time.perf_counter() - start) * 1000
            self._computation_finished.emit(turn)

        if "_threads" not in self.__dict__:
            self._threads, self._lock_threads = {}, threading.Lock()
        self._results = getattr(self, "_results", {})
        self._results[turn] = (g, before, result)
        thread = threading.Thread(target=compute, daemon=True, name=f"computation {turn}")
        thread.start()
        thread.join(self.WAIT_COMPUTATION)
        if thread.is_alive():
            self._in_progress = turn
            QTimer.singleShot(int((self.WARNING_COMPUTATION - self.WAIT_COMPUTATION) * 1000),
                              lambda: self._warn_what_computes(turn))
        else:
            self._on_finish_computation(turn)

    #: Nodes an extension wants calculated too, though they are not seen (it empties it after).
    also_calculate: set = set()

    def _wanted(self, g) -> list[str] | None:
        """What is calculated (with what feeds it): what is seen and what is looked at. The nodes with their eye on,
        the chosen ones, the open previews, the Info nodes, the isolated one, the one being drawn, what paints them
        by a value and the group entered. The rest waits until it is looked at. None: everything (the preference
        «Calculate: everything», or while «Find the best…» is open: it lists every number of the project)."""
        if QSettings().value("compute/what", "seen") == "all" or self.__dict__.get("_everything_once"):
            return None
        dialog = self._search_dialog
        if dialog is not None and dialog.isVisible():
            return None
        p = self.project
        seen = set(p.export) | set(self.__dict__.get("_out_for_numbers", ()))
        seen |= {n for n, x in g.nodes.items() if x.kind.name == 'Info'}
        if self._inside is None:
            seen |= set(self.editor.thumbnails()) | set(self._together) | {self._selection, self._isolated,
                                                                           self._drawing}
            levels = []
        else:
            seen |= set(p.thumbnails)
            levels = [self._levels[0]["node"]]
        seen |= {p.view.get(n, {}).get("by") for n in list(seen) if n in g.nodes}
        seen |= set(levels) | set(self.also_calculate)
        return [n for n in g.nodes if n in seen]

    def calculate_rest(self) -> None:
        """«Calculate the rest»: once, every node (also those not seen); with the next change, only what is seen."""
        if self.project is None:
            return
        self._everything_once = True
        try:
            self.recompute()
        finally:
            self._everything_once = False
        if self._in_progress is None:
            self._display_node(self._selection)

    def _look_again(self) -> None:
        """If something not calculated is now seen or looked at (a node chosen, a preview opened, «Find the
        best…»), it is calculated."""
        if self.project is None or "_closure" not in self.__dict__ or self._in_progress is not None:
            return
        closure, g = self._closure, self.project.graph
        if closure is None:
            return
        wanted = self._wanted(g)
        if wanted is None or any(n not in closure for n in wanted):
            self.recompute()
            if self._in_progress is None:            # (quick: the panel of the chosen node, with its result)
                self._display_node(self._selection)

    def _warn_what_computes(self, turn: int) -> None:
        if self._in_progress == turn == self._turn:
            self.strip_computation.show()

    def wait_computation(self, seconds: float = 600) -> None:
        """Waits for the current computation to end (for the tests and the tools)."""
        from PySide6.QtWidgets import QApplication
        limit = time.perf_counter() + seconds
        while self._in_progress is not None and time.perf_counter() < limit:
            QApplication.processEvents()
            time.sleep(0.005)

    # --- Find the best… ---------------------------------------------------------------

    _search_dialog = None

    def open_search(self, objective: str | None = None) -> None:
        """«Find the best…»: the dialog beside the window (or to the front, with this number chosen)."""
        from .search_dialog import SearchDialog
        if self.project is None or self._inside is not None:
            return
        dialog = self._search_dialog
        if dialog is not None and dialog.isVisible():
            dialog.fill(objective)
            dialog.raise_()
            dialog.activateWindow()
            return
        self._search_dialog = SearchDialog(self, objective)
        self._search_dialog.show()
        self._look_again()                       # it lists every number: everything is calculated meanwhile

    def put_found(self, pieces: list[tuple], final: bool) -> None:
        """Values found by «Find the best…» into their sliders: (control, index or None, value). While it searches
        (`final` False) only the view follows; at the end it is registered once, so one Ctrl + Z undoes the whole
        search."""
        g = self.project.graph
        for control, index, value in pieces:
            if control.node not in g.nodes:
                continue
            put_value(g, control.node, control.input_, value, index, float(control.step).is_integer())
            if control.node in self.editor.boxes:
                self.editor.boxes[control.node].refresh()
            key = control.key if index is None else f"{control.key}[{index}]"
            if key in self.sliders:
                try:
                    self.sliders[key].put(value)
                except RuntimeError:                     # the slider was rebuilt meanwhile
                    pass
        self.recompute()
        if final:
            self._register()                         # (without a key: each search or click, its own step)
            self._display_node(self._selection)

    def _thread_started(self, key) -> None:
        """A thread of its own computes (the search): with the memory cap, as the computations of the window."""
        if "_threads" not in self.__dict__:
            self._threads, self._lock_threads = {}, threading.Lock()
        with self._lock_threads:
            self._threads[key] = threading.current_thread()
            memory_cap(True)

    def _thread_ended(self, key) -> None:
        with self._lock_threads:
            self._threads.pop(key, None)
            if not self._threads:
                memory_cap(False)

    def stop_computation(self) -> None:
        """«Stop»: the current computation is no longer used; the view keeps the last result."""
        self.project.graph.stop()
        if self._calculator_ is not None:
            self._calculator_.stop()
        self._turn += 1
        with self.__dict__.get("_lock_threads") or threading.Lock():
            for thread in list(self.__dict__.get("_threads", {}).values()):
                _cut_thread(thread)
        self._in_progress = None
        self.strip_computation.hide()
        self._stop_playing()
        shown = self.__dict__.get("_shown_state")
        if shown is not None and shown != self._snapshot():
            # The values go back to those of the result in view: the change that did not get to be computed is
            # undone (and leaves no trace in the undo list).
            if self._undo and self._undo[-1] == shown:
                self._undo.pop()
            else:
                self._undo.append(self._state)
            self._restore(shown)
            self.statusBar().showMessage(tr('Calculation stopped: the values are back to those of the result in '
                                            'view.'))
            return
        self.statusBar().showMessage(tr('Calculation stopped: the view shows the last result. Change a value to calculate again.'))

    def _on_finish_computation(self, turn: int) -> None:
        """(In the window's thread.) If it is the last computation asked for and it is still valid, it is shown."""
        g, before, result = self._results.pop(turn, (None, None, None))
        if g is None or turn != self._turn:
            return                                   # an old one (another was already asked for), or already shown
        self._in_progress = None
        self.strip_computation.hide()
        self._computing_text.setText(tr('Calculating… Meanwhile the view shows the last result.'))
        if result.get("ended"):                      # the process that computes ended by itself in the middle
            if g is not self.project.graph or g.version != result["version"]:
                return                               # something changed: the new computation is coming
            node = result.get("node")
            errors = {}
            if self._inside is not None:             # inside a group: not computed here (it might close the window)
                self._inside_taken = (self._inside["graph"], [node] if node in self._inside["graph"].nodes else [])
            if node in g.nodes:                      # it is shown as an error of that node
                errors[node] = NodeError(g.nodes[node], tr(
                    'the calculation closed here: it may have needed more memory than there is, or a library failed '
                    'with these inputs. The rest of Tensela goes on; change a value to calculate again.'))
            self._apply_computation(g, self._errors(errors), 0.0, before)
            self.statusBar().showMessage(tr('The calculation closed unexpectedly in «{node}»: the window goes on.')
                                         .format(node=node) if node else
                                         tr('The calculation closed unexpectedly: the view keeps the last result. '
                                            'Change a value to calculate again.'))
            return
        if "failure" in result:
            if isinstance(result["failure"], str):   # from the process that computes
                raise RuntimeError(result["failure"] + "\n" + result.get("trace", ""))
            raise result["failure"]
        if "cancelled" in result or g is not self.project.graph or g.version != result["version"]:
            return                                   # something changed: the new computation is coming
        if "values" in result:                       # from the process that computes
            result["errors"] = self._take_results(g, result)
        slow = result["ms"] > self.WAIT_COMPUTATION * 1000
        self._apply_computation(g, self._errors(result["errors"]), result["ms"], before)
        if slow:                                    # it arrived late: the node's panel, with what was computed
            self._display_node(self._selection)
            return_memory()

    def _errors(self, errors: dict) -> dict[str, str]:
        """The errors of a computation as notices: the expected ones, as they are; the program's failures, explained."""
        warnings = {}
        for name, e in errors.items():
            if isinstance(e, NodeError):
                warnings[name] = str(e)
            elif isinstance(e, _FailureApart):
                print(e.trace, file=sys.stderr)      # where it failed, in the process that computes
                warnings[name] = tr('In “{node}”: something failed while calculating ({error}). If it happens '
                                    'again, report it in Help → Report a problem or send a comment, with what you '
                                    'were doing.').format(node=name, error=e)
            else:
                import traceback
                traceback.print_exception(e)
                warnings[name] = tr('In “{node}”: something failed while calculating ({error}). If it happens '
                                    'again, report it in Help → Report a problem or send a comment, with what you '
                                    'were doing.').format(node=name, error=e)
        return warnings

    #: The errors of the last computation shown: node → what failed (for the extensions).
    last_errors: dict = {}

    def _apply_computation(self, g, errors: dict[str, str], ms: float, before: dict) -> None:
        """With everything computed: the 3D view, the notices, the table and the canvas."""
        self.last_errors = dict(errors)
        self._shown_state = self._snapshot()        # what the view shows: «Stop» goes back to it
        dialog = self._search_dialog
        if dialog is not None and dialog.isVisible() and dialog._thread is None and self._inside is None:
            dialog.fill()                             # «Find the best…» with the numbers and sliders of now
        if self._inside is None:
            self._new_see(g)

        # What only computes (Area, a Formula…) or only shows values (Info) is not seen in 3D: out of the list. A
        # node that was geometry and now gives numbers (Mesh faces from outlines to flatness) is remembered: when it
        # gives geometry again, it is seen again, as it was.
        def numbers(n):
            return g.nodes[n]._value is not None and g.nodes[n]._value.kind is None
        out_for_numbers = getattr(self, "_out_for_numbers", set())
        out_for_numbers &= set(g.nodes)
        back = [n for n in out_for_numbers if g.nodes[n]._value is not None and not numbers(n)]
        out_for_numbers.update(n for n in self.project.export if g.nodes[n].kind.name != 'Info' and numbers(n))
        out_for_numbers.difference_update(back)
        self._out_for_numbers = out_for_numbers
        self.project.export = [n for n in self.project.export
                                  if g.nodes[n].kind.name != 'Info' and not numbers(n)] + \
            [n for n in back if n not in self.project.export]
        if self._isolated is not None and self._isolated not in g.nodes:    # the isolated one was deleted (or renamed)
            self._isolated = None
            self.isolated_strip.hide()
        drawing = self._drawing if self._drawing in g.nodes and self._inside is None else None
        focus = drawing or (self._isolated if self._inside is None else None)
        if self.editor.focused != focus:            # on the canvas, the other nodes in grey
            self.editor.focus(focus)
        if drawing is not None and g.nodes[drawing].kind.name == 'Edit mesh':
            # Editing a cage by hand: what comes after it (the smoothed shape is what is being designed), and the cage
            # itself as the editor's edges and vertices (its faces would hide the smooth shape, which is inside it).
            after, pending = [], g._next(g.nodes[drawing])
            while pending:
                n = pending.pop()
                if n.name not in after:
                    after.append(n.name)
                    pending.extend(g._next(n))
            rest = self.viewer.bar_drawing.see_rest.isChecked()
            see = [n for n in self.project.export if n != drawing and (rest or n in after)]
            see = [n for n in (see or [drawing]) if g.nodes[n]._value is not None]
        elif drawing is not None:                    # editing a curve: it alone (or the rest, faint)
            rest = self.viewer.bar_drawing.see_rest.isChecked()
            see = [n for n in ([drawing] + ([x for x in self.project.export if x != drawing] if rest else []))
                      if g.nodes[n]._value is not None]
        elif self._isolated is not None and self._inside is None:
            see = [self._isolated] if g.nodes[self._isolated]._value is not None else []
        else:
            see = [n for n in self.project.export if g.nodes[n]._value is not None]
        # Too many pieces to draw them without asking: not drawn until the user says so (a digit too many in a count).
        held = [n for n in see if self._too_heavy(n, g.nodes[n]._value)]
        see = [n for n in see if n not in held]
        self._show_held(held, g)
        no_geometry = []
        inside = []                                  # inside a group: its nodes seen, computed with what reaches it
        if self._inside is not None:
            self._compute_inside()
            canvas = self._canvas
            inside = [n for n in self._seen_inside() if getattr(canvas.nodes[n]._value, "kind", None) is not None
                      and heaviness(canvas.nodes[n]._value) <= 1]
        self.viewer.remove_except(set(see) | {self.INSIDE_KEY + n for n in inside}, paint=False)
        for i, name in enumerate(see):
            data, style_name = g.nodes[name]._value, self.project.view.get(name, {})
            if data.kind is None:
                no_geometry.append(name)
                continue
            if "color" not in style_name:
                # Its automatic colour stays saved in the node: the panel shows the one seen, and it does not change
                # when others are removed from the view. The first of the palette nobody uses yet.
                used = {v.get("color") for v in self.project.view.values()}
                free = [c for c in COLOURS if c not in used]
                style_name = self.project.view.setdefault(name, {})
                style_name["color"] = free[0] if free else COLOURS[i % len(COLOURS)]
                own = getattr(data, "colour", None)    # one that means something (the problems in red, the
                if own is not None:                    # lines to cut…), and its opacity
                    style_name["color"] = own
                    if getattr(data, "opacity", None) is not None:
                        style_name.setdefault("opacity", data.opacity)
            opacity = float(style_name.get("opacity", 1.0))
            if drawing is not None and name != drawing or inside:
                opacity = min(opacity, 0.3)          # the rest, as a reference while a curve is edited (or while
                                                     # something inside a group is seen)
            self.viewer.display(name, data,
                               color=style_name["color"],
                               opacity=opacity,
                               edges=style_name.get("edges"), number=bool(style_name.get("numbers", False)),
                               curvature=bool(style_name.get("curvature_comb", False)),
                               analyse=style_name.get("analyze"),
                               colour_by=self.project.colour_by(name, data), paint=False)
        for i, name in enumerate(inside):
            self.viewer.display(self.INSIDE_KEY + name, self._canvas.nodes[name]._value,
                                color=COLOURS[(i + 3) % len(COLOURS)], opacity=1.0, paint=False)
        self.viewer.frame_si_appears()
        if self._drawing is not None:                # the curvature comb and the knots, with the new curve
            self.viewer.drawing.paint_comb()
            self._put_strip_nodes()
        self.viewer.view.render()                      # only once, with everything set
        self._version_graph_scene += 1                      # Croquis redraws (if it is seen)

        recomputed = [n for n in g.nodes.values() if n.evaluations != before[n.name]]
        self._fill_table(set(errors), recomputed)
        if self._inside is not None:
            self.editor.visible_mark(set(self._seen_inside()))
        else:
            closure = self.__dict__.get("_closure")
            self.editor.sync(set(errors), set() if closure is None else set(g.nodes) - set(closure))
            self.editor.visible_mark(set(self.project.export))
        if errors:
            more = "\n" + tr('(And {n} more node(s) with errors, in red.)').format(n=len(errors) - 1) if len(errors) > 1 else ""
            self.warning.setText(f"✖ {next(iter(errors.values()))}{more}\n" + tr('(The view shows the last valid result.)'))
            self.warning.show()
        else:
            self.warning.hide()
        note = ("  ·  " + tr('Not shown in 3D (not geometry): {nodes}.').format(nodes=", ".join(no_geometry))
                if no_geometry else "")
        closure = self.__dict__.get("_closure")
        waiting = sum(1 for n in g.nodes.values() if closure is not None and n.name not in closure
                      and n._value is None)
        if waiting:
            note += "  ·  " + tr('{n} not calculated, because they are not seen: a click on one calculates '
                                 'it.').format(n=waiting)
        self.panel_node.waiting = waiting if self._inside is None else 0
        self.button_rest.setText(tr('Calculate the rest ({n})').format(n=waiting))
        self.button_rest.setVisible(bool(waiting) and self._inside is None)
        self.statusBar().showMessage(tr('Recalculated {n} of {total} nodes in {ms} ms.').format(
            n=len(recomputed), total=len(g.nodes), ms=f"{ms:.0f}") + note + getattr(self, "_warning_points", ""))
        if self._say_after:                           # what the change that started this computation had to say
            self.statusBar().showMessage(self._say_after, 10000)
            self._say_after = ""
        if self._drawing is not None:                 # while drawing, what can be done, in view
            self.statusBar().showMessage(self._instructions_drawing())
        self._report_to_code_editor(g, errors)
        if self._drawing in g.nodes and g.nodes[self._drawing].kind.name == 'Equilibrium' and self._inside is None:
            value = g.nodes[self._drawing]._value       # moving supports: the particles where they settled now
            if value is not None and hasattr(value, "network"):
                self._supports_base = np.array(value.network["rest"], dtype=float)
                self.viewer.drawing.put_points(self._supports_base, value.network["fixed"])
                if self.viewer.drawing._dragging is not None:      # the one under the pointer stays there
                    self._supports_base = np.array(self.viewer.drawing.points, dtype=float)
        notice, self._notice_code = getattr(self, "_notice_code", None), None
        if notice:                                     # a project with code just opened: said once, without stopping
            self.statusBar().showMessage(notice, 20000)
        self._tell_extensions("computed")

    # --- The code of a Code node, in its editor ------------------------------------------------------

    _notice_code: str | None = None

    def _edit_node(self, node: str) -> None:
        """Double-click on a card with an editor of its own: the code editor, or editing in the 3D view."""
        g = self._canvas
        if node not in g.nodes:
            return
        if g.nodes[node].kind.name == 'Code':
            self.edit_code(node)
        elif self._drawing != node:              # (already editing it: the double click does not finish it)
            self.draw(node)

    _code_dialog = None

    def edit_code(self, node: str) -> None:
        """Opens the editor of the code of a node (or brings it to the front, if it is the one already open)."""
        from .code_editor import CodeDialog
        g = self._canvas
        if node not in g.nodes or g.nodes[node].kind.name != 'Code' or isinstance(g.nodes[node].inputs["code"], Node):
            return
        if self._code_dialog is not None and self._code_dialog.node == node and self._code_dialog.isVisible():
            self._code_dialog.raise_()
            self._code_dialog.activateWindow()
            return
        if self._code_dialog is not None:
            self._code_dialog.close()
        self._code_dialog = CodeDialog(node, g.nodes[node].inputs["code"], self)
        self._code_dialog.applied.connect(lambda name, code: self._change_value(name, "code", code, True))
        self._code_dialog.preferences.connect(lambda: self.open_preferences('Code editor'))
        self._code_dialog.show()

    def _report_to_code_editor(self, g, errors: dict[str, str]) -> None:
        """With the node computed: its error (or that it went well) in the editor of its code, if it is open."""
        dialog = self._code_dialog
        if dialog is None or not dialog.isVisible():
            return
        if dialog.node not in g.nodes:               # the node was deleted or renamed: its editor closes
            dialog.close()
            return
        dialog.report(errors.get(dialog.node))

    def _fill_table(self, failures: set[str], recomputed: list) -> None:
        """One row per node: name, node kind, what it produces and its shape (what it measures); «not calculated»
        if it is not seen (a click on it calculates it)."""
        g = self.project.graph
        closure = self.__dict__.get("_closure")
        rows = []
        for node in g.nodes.values():
            if node._value is not None:
                data = node._value
                what = tr(data.kind.name if data.kind is not None else (
                    'yes/no' if data.values.dtype == bool else 'number'))
                if not data.levels:     # a single one: its value if it is a number; «1» if it is a geometry
                    shape = text_value(data.values.item()) if data.kind is None and data.values.size == 1 else "1"
                else:
                    shape = data.shape
                    if data.kind is None and data.values.dtype != bool and data.values.dtype.kind in "fiu":
                        # A list of numbers: its first values too, so they can be read without opening the card.
                        numbers = [float(v) for v in np.asarray(data.values)[data.mask].ravel()[:6]]
                        more = " …" if int(np.count_nonzero(data.mask)) > 5 else ""
                        shape += ":  " + " · ".join(text_value(round(v, 2)) for v in numbers[:5]) + more
                state = "recomputed" if node in recomputed else ""
            elif node.name in failures:
                what, shape, state = "—", tr("error"), "error"
            elif closure is not None and node.name not in closure:
                what, shape, state = "—", tr("not calculated"), "waiting"
            else:
                what, shape, state = "—", "—", ""
            kind = tr(node.kind.name)
            input_what = next((e for e in node.kind.inputs if e.name == "what" and e.options), None)
            mode = node.inputs.get("what", input_what.default) if input_what is not None else None
            if isinstance(mode, str):
                kind += f" · {tr(mode)}"         # the chosen mode: «Surface curvature · developable»
            rows.append((node.name, kind, node.kind.category, what, shape, state))
        self.table.icons = {n.name: icons.of_kind(n.kind.name, n.kind.category) for n in g.nodes.values()}
        self.table.put(rows)

    # --- Right-click menus -------------------------------------------------------

    def _menu_canvas_and_extensions(self, menu: QMenu, name: str | None) -> None:
        self._menu_canvas(menu, name)
        if self._inside is None and self.project is not None:
            self._extension_entries(menu, "canvas" if name is None else "node", name)

    def _menu_canvas(self, menu: QMenu, name: str | None) -> None:
        """What belongs to the project in the canvas menu: on a box, or on the background."""
        if self._inside is not None:            # inside a group: rename, and leave
            if name is not None:
                menu.addAction(tr('Rename…')).triggered.connect(lambda: self._ask_rename(name))
            else:
                menu.addAction(tr('Leave group'), self.quit_group)
                menu.addSeparator()
            if name is not None:
                return
        if name is not None:
            p = self.project
            if p.graph.nodes[name].kind.name in p.graph.definitions:
                menu.addAction(tr('Enter group'), lambda: self.enter_group(name))
                menu.addAction(tr('Save to library…'), lambda: self.save_in_library(name))
                menu.addSeparator()
            node = p.graph.nodes[name]
            if editable(node):                       # what double-clicking the card opens, also here
                text = ('Edit code…' if node.kind.name == 'Code' else
                        'Edit vertices' if node.kind.name == 'Edit mesh' else
                        'Move supports' if node.kind.name == 'Equilibrium' else 'Edit curve')
                menu.addAction(tr(text), lambda: self._edit_node(name))
                menu.addSeparator()
            value = getattr(node, "_value", None)
            if value is not None and value.kind is None and name in numbers_of(p.graph):
                menu.addAction(tr('Find its best value…'), lambda: self.open_search(name))
                menu.addSeparator()
            see = menu.addAction(tr('Show in 3D'))
            see.setCheckable(True)
            see.setChecked(name in p.export)
            see.toggled.connect(lambda yes: self._toggle_see(name, yes))
            chosen = self._selected_names()
            only = menu.addAction(tr('Show only this one') if len(chosen) <= 1 else
                                  tr('Show only the selected ({n})').format(n=len(chosen)))
            only.setShortcut(self._action_items["see_only"].shortcut())
            only.triggered.connect(lambda: self.see_only(chosen or [name]))
            menu.addAction(self._action_items["see_all"])
            menu.addAction(self._action_items["hide_all"])
            menu.addAction(tr('Rename…')).triggered.connect(lambda: self._ask_rename(name))
            menu.addAction(tr('Replace with…')).triggered.connect(lambda: self._ask_replace(name))
            if len(self.editor.chosen()) > 1:
                menu.addAction(self._action_items_edit["group"])
            if p.graph.nodes[name].kind.name in p.graph.definitions:
                menu.addAction(self._action_items_edit["ungroup"])
            if name in p.export:
                menu.addAction(tr('Colour…')).triggered.connect(lambda: self._ask_color(name))
            return
        for key in ("search",):
            menu.addAction(self._action_items_edit[key])
        menu.addAction(self._action_items["see_all"])
        menu.addAction(self._action_items["hide_all"])
        menu.addAction(self._action_items["arrange"])
        menu.addAction(self._action_items["frame_nodes"])
        menu.addAction(tr('Export the nodes (PNG or SVG)…')).triggered.connect(self._export_nodes)
        menu.addSeparator()
        menu.addAction(self._action_items["guides"])
        menu.addAction(self._action_items["grid"])
        background = menu.addMenu(tr('Canvas background'))
        current = QSettings().value("preferences/canvas_background", "dots")
        for key, text in (("dots", 'Dots'), ("squares", 'Square grid'), ("plain", 'Plain')):
            a = background.addAction(tr(text))
            a.setCheckable(True)
            a.setChecked(key == current)
            a.triggered.connect(lambda _=False, k=key: (QSettings().setValue("preferences/canvas_background", k),
                                                           self._apply_preferences()))
        background.addSeparator()
        self._menu_tone(background, "preferences/canvas_tone")

    def _menu_tone(self, menu: QMenu, key: str) -> None:
        """Like the theme, light, mid or dark: the canvas background or that of the view."""
        current = QSettings().value(key, "theme")
        group = QActionGroup(menu)
        for tone, text in theme.NAMES_TONE.items():
            a = menu.addAction(tr(text))
            a.setCheckable(True)
            a.setChecked(tone == current)
            group.addAction(a)
            a.triggered.connect(lambda _=False, t=tone: self.apply_preference(key, t))

    def _ask_rename(self, name: str) -> None:
        new_, ok = ask_text(self, tr('Rename'), tr('New name for “{node}”:').format(node=name), text=name)
        if ok and new_.strip() and new_.strip() != name:
            self._rename(name, new_.strip())

    def _ask_replace(self, name: str) -> None:
        """Change the node for another kind, in its place and with its wires: the finder, by its card."""
        box = self.editor.boxes.get(name)
        if box is None:
            return
        point = self.editor.mapFromScene(box.sceneBoundingRect().topRight())
        self.editor.choose_kind(point, lambda kind: self._replace(name, kind))

    def _replace(self, name: str, kind: str) -> None:
        p = self.project
        if p is None or name not in p.graph.nodes or p.graph.nodes[name].kind.name == kind:
            return
        p.positions, p.thumbnails = self.editor.positions(), self.editor.thumbnails()
        try:
            new, lost = p.graph.replace(name, kind)       # («merge 1» → «merge lists 1»: an automatic name follows)
        except ShapeError as error:
            self._warn(str(error))
            return
        inputs = {e.name for e in new.kind.inputs}
        p.controls = [c for c in p.controls if c.node != name or c.input_ in inputs]
        old, name = name, new.name
        if name != old:                                  # what was kept by its name goes with it
            p.positions = {(name if n == old else n): v for n, v in p.positions.items()}
            p.thumbnails = [name if n == old else n for n in p.thumbnails]
            p.export = [name if n == old else n for n in p.export]
            p.view = {(name if n == old else n): v for n, v in p.view.items()}
            for style_name in p.view.values():
                if style_name.get("by") == old:
                    style_name["by"] = name
            for c in p.controls:
                if c.node == old:
                    c.node = name
        message = tr('“{node}” is now a “{kind}”, with its wires.').format(node=name, kind=tr(kind))
        if lost:
            message += " " + tr('Without a place in it: {inputs}.').format(
                inputs=", ".join(label_input(i) for i in lost))
        self._say_after = message                 # said when it has been computed
        self._after_restructure(name)

    def _ask_color(self, name: str) -> None:
        color = QColorDialog.getColor(QColor(self.project.view.get(name, {}).get("color", "#7d8a96")), self,
                                      tr('Colour of “{node}”').format(node=name))
        if color.isValid():
            self._change_color(name, color.name())

    def _menu_view(self, point) -> None:
        """The 3D view menu: style, views, axes and what is taken outside."""
        menu = QMenu(self)
        style_names = menu.addMenu(tr('Style'))
        current = self.viewer.style_name
        for key, text in STYLE_NAMES.items():
            a = style_names.addAction(tr(text))
            a.setCheckable(True)
            a.setChecked(key == current)
            a.triggered.connect(lambda _=False, k=key: self.put_style_name_view(k))
        self._menu_matcap(style_names)
        self._add_outlines_action(style_names)
        views = menu.addMenu(tr('Look from'))
        for text, view, opposite in (('Front (south)', "front", False), ('Back (north)', "front", True),
                                      ('Right (east)', "right", False), ('Left (west)', "right", True),
                                      ('Plan (top)', "plan", False), ('Bottom', "plan", True)):
            views.addAction(tr(text)).triggered.connect(lambda _=False, v=view, o=opposite: self.viewer.look(v, o))
        views.addSeparator()
        parallel = views.addAction(tr('Parallel projection'))
        parallel.setCheckable(True)
        parallel.setChecked(bool(self.viewer.view.camera.parallel_projection))
        parallel.triggered.connect(lambda yes: self._button_projection.setChecked(yes))
        menu.addAction(self._action_items["frame_all"])
        axes = menu.addAction(tr('Show the axes'))
        axes.setCheckable(True)
        axes.setChecked(self._button_axes.isChecked())
        axes.toggled.connect(self._button_axes.setChecked)
        self._menu_tone(menu.addMenu(tr('Background')), "preferences/view_tone")
        menu.addSeparator()
        menu.addAction(tr('Export image…')).triggered.connect(self._ask_image)
        menu.addAction(tr('Freehand sketch…')).triggered.connect(self._sketch)
        open_in = menu.addMenu(tr('Open in'))
        open_in.addAction("Blender").triggered.connect(self._open_in_blender)
        open_in.addAction("IngeTrazo").triggered.connect(self._open_in_ingetrazo)
        self._extension_entries(menu, "view")
        menu.exec(point)

    def _menu_data_items(self, point) -> None:
        item = self.table.itemAt(point)
        menu = QMenu(self)
        if item is not None:
            name = item.data(0, Qt.ItemDataRole.UserRole)
            menu.addAction(tr('Select “{node}” on the canvas').format(node=name)).triggered.connect(
                lambda: self.editor.select(name))
            menu.addSeparator()
        menu.addAction(tr('Copy as text')).triggered.connect(lambda: self._export_data_items("copy"))
        menu.addAction(tr('Save as CSV…')).triggered.connect(lambda: self._export_data_items("csv"))
        menu.exec(self.table.viewport().mapToGlobal(point))

    def _menu_slider(self, control: Control, point) -> None:
        menu = QMenu(self)
        menu.addAction(tr('Select “{node}” on the canvas').format(node=control.node)).triggered.connect(
            lambda: self.editor.select(control.node))
        menu.addAction(tr('Range and step…')).triggered.connect(lambda: self._ask_range(control))
        menu.addAction(tr('Remove this slider')).triggered.connect(
            lambda: self._toggle_slider(control.node, control.input_, False))
        menu.exec(point)

    def _ask_range(self, control: Control) -> None:
        self._display_dialog(DialogControl(control, self), lambda d: self._change_range(control.key, *d.choice()))

    def _change_range(self, key: str, name: str, minimum: float, maximum: float, step: float) -> None:
        """Another range, step or name for a slider (it is saved with the project, and undone)."""
        control = next((c for c in self.project.controls if c.key == key), None) if self.project else None
        if control is None or not (maximum > minimum and step > 0):
            return
        control.minimum, control.maximum, control.step = float(minimum), float(maximum), float(step)
        control.label = "" if name == label_input(control.input_) else name
        self._create_controls()
        self._register()
        self.statusBar().showMessage(tr('“{name}”: from {low} to {high}, every {step}.').format(
            name=control.label or label_input(control.input_), low=text_value(control.minimum),
            high=text_value(control.maximum), step=text_value(control.step)), 8000)

    def _export_nodes(self) -> None:
        """The whole canvas: high-resolution PNG or vector SVG (for a board or a presentation)."""
        if not self.editor.boxes:
            self.statusBar().showMessage(tr('There are no nodes to export.'))
            return
        base = self.filepath.with_suffix("") if self.filepath else Path.cwd() / tr('nodes')
        filepath, filter_ = QFileDialog.getSaveFileName(self, tr('Export the nodes'), f"{base} {tr('nodes')}.png",
                                                   tr('PNG image, high resolution (*.png);;Vector SVG (*.svg)'))
        if not filepath:
            return
        if not filepath.lower().endswith((".png", ".svg")):
            filepath += ".svg" if "svg" in filter_.lower() else ".png"
        try:
            width, height = self.editor.export(filepath)
        except OSError as error:
            QMessageBox.warning(self, tr('Could not export'), str(error))
            return
        self.statusBar().showMessage(tr('Exported: {path}').format(path=f"{filepath} ({width} × {height})"))

    def _export_data_items(self, as_: str) -> None:
        """The Data table: to a CSV file, or copied as text (to paste it in a spreadsheet)."""
        if as_ == "copy":
            QApplication.clipboard().setText(self.table.as_text())
            self.statusBar().showMessage(tr('Table copied: paste it into a spreadsheet or a text.'))
            return
        base = self.filepath.with_suffix("") if self.filepath else Path.cwd() / tr('data items')
        filepath, _ = QFileDialog.getSaveFileName(self, tr('Export the data'), f"{base} {tr('data items')}.csv",
                                              tr('CSV table (*.csv)'))
        if not filepath:
            return
        try:
            Path(filepath).write_text(self.table.as_text(","), encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, tr('Could not export'), str(error))
            return
        self.statusBar().showMessage(tr('Exported: {path}').format(path=filepath))


def pick_platform() -> str | None:
    """On GNOME with Wayland, Tensela goes through XWayland (X11) if it has what it needs.

    On Wayland an application cannot place its windows: Qt's panels do not drag or come out well (comments of batches 6
    to 8). On X11 they do, and the desktop puts the frame of the windows taken out (title, minimise, maximise). Three
    small XCB libraries are needed; without them it stays on Wayland, with the «⋯» menu of the panels. It can be forced
    with QT_QPA_PLATFORM.
    """
    if os.environ.get("QT_QPA_PLATFORM") or os.environ.get("XDG_SESSION_TYPE") != "wayland" \
            or not os.environ.get("DISPLAY"):
        return None
    from ctypes.util import find_library
    if all(find_library(n) or _beside_qt(n) for n in ("xcb-cursor", "xcb-icccm", "xcb-keysyms")):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        return "xcb"
    return None


def _beside_qt(name: str) -> bool:
    """Whether the library `name` comes beside those of Qt (the AppImage brings those of X11: libxcb-cursor…)."""
    import importlib.util
    spec = importlib.util.find_spec("PySide6")
    folders = list(spec.submodule_search_locations or []) if spec else []
    return any(any((Path(f) / "Qt" / "lib").glob(f"lib{name}.so.*")) for f in folders)



# --- Preferences saved before the move to English -----------------------------------------------------------

#: Old key → (new key, {old value: new value}).
OLD_PREFERENCES = {
    'croquis/ajustes': ('sketch/settings', {}),
    'croquis/ancho': ('sketch/width', {}),
    'dibujo/ajustar': ('drawing/snap', {}),
    'dibujo/curvatura': ('drawing/curvature', {}),
    'dibujo/nudos': ('drawing/knots', {}),
    'dibujo/paso': ('drawing/step', {}),
    'dibujo/resto': ('drawing/rest', {}),
    'dxf/modo': ('dxf/mode', {}),
    'dxf/unidad': ('dxf/unit',
                    {'metros': 'metres',
                     'centímetros': 'centimetres',
                     'milímetros': 'millimetres',
                     'pulgadas': 'inches',
                     'pies': 'feet'}),
    'dxf/vista': ('dxf/view',
                   {'planta': 'plan',
                    'alzado sur': 'south elevation',
                    'alzado norte': 'north elevation',
                    'alzado este': 'east elevation',
                    'alzado oeste': 'west elevation'}),
    'lienzo/guias': ('canvas/guides', {}),
    'lienzo/rejilla': ('canvas/grid', {}),
    'preferencias/decimales': ('preferences/decimals', {}),
    'preferencias/fondo_lienzo': ('preferences/canvas_background',
                                   {'punteado': 'dots', 'cuadricula': 'squares', 'liso': 'plain'}),
    'preferencias/fraccion': ('preferences/fraction', {}),
    'preferencias/idioma': ('preferences/language', {}),
    'preferencias/navegacion': ('preferences/navigation', {}),
    'preferencias/tono_lienzo': ('preferences/canvas_tone',
                                  {'tema': 'theme', 'claro': 'light', 'medio': 'mid', 'oscuro': 'dark'}),
    'preferencias/tono_vista': ('preferences/view_tone',
                                 {'tema': 'theme', 'claro': 'light', 'medio': 'mid', 'oscuro': 'dark'}),
    'preferencias/unidad_longitud': ('preferences/length_unit', {}),
    'preferencias/unidades': ('preferences/units', {'metrico': 'metric'}),
    'recientes': ('recent', {}),
    'tema/modo': ('theme/mode', {'claro': 'light', 'oscuro': 'dark', 'sistema': 'system'}),
    'tema/nombre': ('theme/name', {'sobrio': 'sober', 'vivo': 'vivid'}),
    'ventana/maximizada': ('window/maximized', {}),
    'ventana/tamaño': ('window/size', {}),
    'vista/ejes': ('view/axes', {}),
    'vista/estilo': ('view/style',
                      {'solido': 'solid', 'alambre': 'wireframe', 'lineas': 'hidden lines', 'rayos': 'x-ray'}),
    'vista/leyendas': ('view/legends', {'izquierda': 'left', 'derecha': 'right'}),
    'vista/matcap': ('view/matcap',
                      {'arcilla': 'clay', 'cerámica': 'ceramic', 'grafito': 'graphite', 'yeso': 'plaster'}),
    'vista/paralela': ('view/parallel', {})}
OLD_PREFIXES = {"atajos/": "shortcuts/", "espacios/": "workspaces/"}


def move_from_parametrico(settings: QSettings | None = None, old: Path | None = None,
                          data: Path | None = None) -> bool:
    """The first time Tensela opens, it takes what Parametrico (its name of before) kept: the preferences and the own
    files (the library of groups, the matcaps). It copies them: Parametrico's are left as they were. Returns whether
    it moved anything."""
    settings = settings or QSettings()
    if settings.allKeys():                       # Tensela already has its own preferences
        return False
    config = Path(os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config"))
    old = old or config / "Parametrico" / "Parametrico.conf"
    moved = False
    if old.is_file():
        before = QSettings(str(old), QSettings.Format.IniFormat)
        for key in before.allKeys():
            value = before.value(key)
            if key == "preferences/navigation" and value == "parametrico":
                value = "tensela"
            settings.setValue(key, value)
        settings.sync()
        moved = True
    share = data or Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))
    if (share / "parametrico").is_dir() and not (share / "tensela").exists():
        import shutil
        shutil.copytree(share / "parametrico", share / "tensela")
        moved = True
    return moved


def desktop_entry_installed(name: str = "tensela.desktop") -> bool:
    """Whether the launcher of Tensela is where the desktop looks for applications (XDG_DATA_HOME and XDG_DATA_DIRS)."""
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    dirs = [home] + (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    return any((Path(d) / "applications" / name).is_file() for d in dirs if d)


def app_icon():
    """The icon of Tensela (the hypar mesh), in the sizes the desktop asks for."""
    from PySide6.QtGui import QIcon
    brand = Path(__file__).resolve().parent / "brand"
    icon = QIcon(str(brand / "tensela.svg"))
    for side in (16, 24, 32, 48, 64, 128, 256, 512):
        icon.addFile(str(brand / f"tensela-{side}.png"))
    return icon


def migrate_preferences(settings: QSettings | None = None) -> None:
    """The preferences saved with the Spanish keys of before, to the ones of now (once; the old ones are removed).
    The window layout of before is forgotten: it named the panels in Spanish (the default one comes back)."""
    settings = settings or QSettings()
    if not any(settings.contains(k) for k in (*OLD_PREFERENCES, "ventana/disposicion")) \
            and not any(k.startswith(tuple(OLD_PREFIXES)) for k in settings.allKeys()):
        return
    for old, (new, values) in OLD_PREFERENCES.items():
        if settings.contains(old):
            if not settings.contains(new):
                v = settings.value(old)
                settings.setValue(new, values.get(v, v) if isinstance(v, str) else v)
            settings.remove(old)
    for key in settings.allKeys():
        for old, new in OLD_PREFIXES.items():
            if key.startswith(old):
                if not settings.contains(new + key[len(old):]):
                    settings.setValue(new + key[len(old):], settings.value(key))
                settings.remove(key)
    settings.remove("ventana/disposicion")
    settings.remove("ventana/geometria")              # (no longer used)
    settings.sync()


#: Where the errors of the program are written down (a few hundred kilobytes at most), to send them when reporting.
ERRORS_LOG = "errors.log"


def errors_log() -> Path:
    """The file of the errors of the program, in the user's data folder."""
    from PySide6.QtCore import QStandardPaths
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    return folder / ERRORS_LOG


def _catch_errors(window: "Window") -> None:
    """An error of the program inside a click or a shortcut (a bug, not a mistake in the project) is not left only in
    the terminal: the window says so on its status bar, and it is written down in `errors_log()` with the date."""
    import traceback
    previous = sys.excepthook

    def hook(kind, error, trace) -> None:
        previous(kind, error, trace)                  # in the terminal too, as before
        text = "".join(traceback.format_exception(kind, error, trace))
        try:
            log = errors_log()
            log.parent.mkdir(parents=True, exist_ok=True)
            old = log.read_text(encoding="utf-8")[-200_000:] if log.exists() else ""
            log.write_text(old + f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')}\n{text}", encoding="utf-8")
        except OSError:
            pass
        try:
            window.statusBar().showMessage(
                tr('Something failed in Tensela (a bug, not in your project): {error}. It is written down in '
                   '{log}.').format(error=f"{kind.__name__}: {error}", log=errors_log()), 15000)
        except RuntimeError:                          # the window is being closed
            pass
    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tensela-app", description=tr("The Tensela window."))
    parser.add_argument("files", nargs="*", metavar=tr("FILE"),
                        help=tr("the projects (.tela or .json) opened at the start"))
    # To check the window hands-free (development); the Spanish names of before still work:
    parser.add_argument("--move", "--mover", dest="move", action="append", default=[], metavar="NODE.INPUT=VALUE",
                        help=argparse.SUPPRESS)
    parser.add_argument("--capture", "--captura", dest="capture", help=argparse.SUPPRESS)
    parser.add_argument("--mode", "--tema", dest="mode", choices=["light", "dark", "claro", "oscuro"], help=argparse.SUPPRESS)
    parser.add_argument("--style", "--estilo", dest="style_name", help=argparse.SUPPRESS)
    parser.add_argument("--seconds", "--segundos", dest="seconds", type=float, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.textinput=false")
    pick_platform()
    # The name of Tensela for the desktop, before the application exists, so Qt introduces it to the desktop portal
    # once. Only when its launcher (tensela.desktop) is installed: without it the portal refuses the name, with a
    # notice in the terminal (the AppImage installs the launcher).
    if desktop_entry_installed():
        QApplication.setDesktopFileName("tensela")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Tensela")
    app.setOrganizationName("Tensela")
    app.setWindowIcon(app_icon())
    move_from_parametrico()
    migrate_preferences()
    # The language, before creating anything (the texts are written when creating each part of the window).
    language.LANGUAGE = QSettings().value("preferences/language", language.system_language())
    mode = {"claro": "light", "oscuro": "dark"}.get(args.mode, args.mode) or QSettings().value("theme/mode", "system")
    theme.apply(app, args.style_name or QSettings().value("theme/name", theme.DEFAULT_BY),
                 None if mode == "system" else mode)
    # Qt's standard buttons (Save, Discard, Cancel…) in Spanish.
    translation = QTranslator(app)
    if language.LANGUAGE == "es" and translation.load("qtbase_es", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translation)
    window = Window()
    _catch_errors(window)
    window.show()
    window.listen_for_others()
    window.offer_menu()
    for file in args.files:
        window.open_(file)
    if not args.files:
        window.new_()                    # under the start screen, or alone: closing the start screen leaves it
        from .start import show_at_start
        if not args.seconds and show_at_start():
            QTimer.singleShot(300, window.show_start)      # once the window has its place: it goes over its centre

    if args.seconds:
        def script():
            for mov in args.move:
                key, value = mov.split("=", 1)
                window.sliders[key].cell.setValue(float(value))
            if args.capture:
                window.viewer.capture(args.capture)
                window.grab().save(str(Path(args.capture).with_suffix(".window.png")))
            window.viewer.dismiss()
            app.quit()

        QTimer.singleShot(int(args.seconds * 1000), script)
    return app.exec()


def _is_number(v) -> bool:
    """Whether a fixed value can have a slider: a number or a list of numbers."""
    return slidable(v)


def _thumbnail(picture: np.ndarray, side: int = 32):
    """A matcap's picture, small, for its menu."""
    from PySide6.QtGui import QIcon, QImage, QPixmap
    rgb = np.ascontiguousarray(picture[..., :3], dtype=np.uint8)
    h, w = rgb.shape[:2]
    image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    return QIcon(QPixmap.fromImage(image.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)))


def _decimals(step: float) -> int:
    text = f"{step:.10f}".rstrip("0")
    return max(0, len(text.split(".")[1])) if "." in text else 0


if __name__ == "__main__":
    sys.exit(main())
