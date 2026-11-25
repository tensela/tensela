"""The node editor (Delivery 2), on Qt's canvas (D9).

Each node of the graph is a box: at the top its name and its kind, on the left its inputs (with their fixed value, if
they have one), on the right its output. Each connection is a wire that carries written the shape of the data it
transports (`row 12 × column 20 = 240`): the data can be seen.

Navigation: wheel to zoom; middle button (or Shift + left on the background) to pan; drag a box to move it.
"""

from __future__ import annotations

import time
import unicodedata

import numpy as np

import shiboken6
from PySide6.QtCore import QEvent, QLineF, QObject, QPoint, QPointF, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QFontMetricsF, QIcon, QKeySequence, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (
    QGraphicsColorizeEffect, QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QCompleter, QFrame, QGraphicsProxyWidget, QGraphicsView, QLineEdit, QListWidget, QListWidgetItem, QMenu, QVBoxLayout,
)

from ..data import Data, ShapeError
from ..graph import Graph, Node, drawable
from ..nodes import (OLD, CATALOG, ESSENTIALS, PROGRAM_NAMES, NodeType, suggestions, visible_input,
                     automatic_level)
from ..values import MAGNITUDE_NODE, is_length, label_input, lines_of, text_of, text_value
from . import annotations as annotations, icons as icons, theme as theme
from .widgets import complete_inline, offered_first
from ..language import in_spanish, tr

DEPTH = QColor("#2f3237")
GRID = QColor("#3a3e44")
BODY = QColor("#474b52")
EDGE = QColor("#1f2125")
TEXT = QColor("#eceff1")
SMOOTH_TEXT = QColor("#aeb4bb")
WIRE = QColor("#9aa3ad")
RED = QColor("#e0605a")
SELECTION = QColor("#f0b84a")
TEXT_HEADER = QColor("#ffffff")
HEADER = "filled"   # the header of the card: «filled» with its colour, or a «band» at the top
ICON = 14           # the category icon, next to the title
RADIUS = 6
DEPTH_CANVAS = "dots"   # dots, squares or plain (Preferences)
# (These colours are the factory ones: the theme, ui/theme.py, changes them at start-up.)
COLOURS_CATEGORY = {
    'Values': QColor("#5b8a45"),
    'Shapes': QColor("#3f7396"),
    'Curves': QColor("#3a8a80"),
    'Surfaces': QColor("#2f6f8a"),
    'Meshes': QColor("#9a5a2e"),
    'Divide': QColor("#8c6a33"),
    'Measure': QColor("#7a5a8c"),
    'Transform': QColor("#94505a"),
    'Fabrication': QColor("#7a7d10"),
    'Simulation': QColor("#9c2f63"),
    'Environment': QColor("#946500"),
}


class _Escape(QObject):
    """Esc cancels what is being written on the card."""

    def __init__(self, parent, cancel):
        super().__init__(parent)
        self._cancel = cancel

    def eventFilter(self, object_, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return True
        return False


class _Offered(QObject):
    """The names offered under a field of a card (the installed fonts): a list inside the canvas, right below the field,
    that keeps those holding what is typed (those that start with it first) and proposes the first one in the field
    itself. ↑ ↓ go through it, a click or Enter takes one. Inside the canvas and not a window of its own: it stays
    under its card, wherever the window is."""

    ROWS = 10

    def __init__(self, box, field: QLineEdit, names: list[str], where: QPointF, width: float, take):
        super().__init__(field)
        self.names, self.field, self._take = names, field, take
        self.list = QListWidget()
        self.list.setObjectName("card_list")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)      # the field keeps the keys: it goes on being typed
        self.list.setUniformItemSizes(True)
        self.list.setFixedSize(int(width), HEIGHT_ROW * self.ROWS)
        self.list.itemClicked.connect(lambda item: self._pick(item.text()))
        self.proxy = QGraphicsProxyWidget(box)
        self.proxy.setWidget(self.list)
        self.proxy.setZValue(11)
        self.proxy.setPos(where)
        self._z = box.zValue()
        box.setZValue(5)                          # above the cards below it, while it is open
        self._box = box
        self.show(field.text() if field.text() in names else "")
        complete_inline(field, names)
        field.textEdited.connect(self.show)
        field.installEventFilter(self)

    def show(self, typed: str) -> None:
        """Those that hold `typed`, the one in the field marked."""
        self.list.clear()
        self.list.addItems(offered_first(self.names, typed) if typed else self.names)
        QTimer.singleShot(0, self._mark)          # once the field has its proposal

    def _mark(self) -> None:
        if not shiboken6.isValid(self.list) or not shiboken6.isValid(self.field):
            return
        found = self.list.findItems(self.field.text(), Qt.MatchFlag.MatchExactly)
        self.list.setCurrentItem(found[0] if found else None)
        if found:
            self.list.scrollToItem(found[0], QListWidget.ScrollHint.PositionAtTop)

    def _pick(self, name: str) -> None:
        self.field.setText(name)
        self.field.setModified(True)
        self._take()

    def eventFilter(self, object_, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up,
                                                                    Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            step = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1, Qt.Key.Key_PageDown: self.ROWS,
                    Qt.Key.Key_PageUp: -self.ROWS}[event.key()]
            count = self.list.count()
            if count:
                row = min(max(self.list.currentRow() + step, 0), count - 1) if self.list.currentRow() >= 0 else 0
                self.list.setCurrentRow(row)
                self.field.setText(self.list.item(row).text())
                self.field.setModified(True)
            return True
        return False

    def close(self) -> None:
        if shiboken6.isValid(self._box):
            self._box.setZValue(self._z)
        if shiboken6.isValid(self.proxy):
            self.proxy.setParentItem(None)
            if self.proxy.scene() is not None:
                self.proxy.scene().removeItem(self.proxy)
            self.proxy.deleteLater()


def _icon_category(category: str, kind: str = ""):
    name = icons.of_kind(kind, category)
    return icons.icon(name, COLOURS_CATEGORY.get(category, TEXT).name(), 16) if name else QIcon()


def _with_alpha(color: QColor, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c

STEP_GRID = 25
SETTING = {"grid": True, "guides": True}  # it is changed from the View menu or the Nodes header
GUIDE_PIXELS = 8   # at how many screen pixels a card snaps to the guide
MINIMUM_WIDTH = 150
HEIGHT_HEADER = 40
HEIGHT_ROW = 20
HEIGHT_THUMBNAIL = 130        # the preview inside the card
HEIGHT_LINE_PANEL = 17       # each line of what a Panel node shows
HEIGHT_CHART = 58           # the curve of a Graph node, on its card
MAX_PANEL_WIDTH = 340
COLOR_THUMBNAIL = "#9aa4b0"
WIDTH_WITH_THUMBNAIL = 200
MARGIN = 10
SPACING_X = 190
SPACING_Y = 30


def text_shape(data) -> str:
    """The shape of a data, short, to write it on a wire."""
    return "·" if not data.levels else data.shape


class Port(QGraphicsEllipseItem):
    RADIUS = 5.0

    def __init__(self, box: BoxNode, input_: str | None, y: float):
        r = self.RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, box)
        self.box = box
        self.input_ = input_  # None: it is the output
        self.cables: list[Wire] = []
        x = 0.0 if input_ is not None else box.width
        self.setPos(x, y)
        self.setBrush(QBrush(WIRE))
        self.setPen(QPen(EDGE, 1.2))
        self.setZValue(2)

    @property
    def is_output(self) -> bool:
        return self.input_ is None

    def centre(self) -> QPointF:
        return self.scenePos()

    def highlight(self, yes: bool) -> None:
        """The port the dragged wire would snap to: bigger and in the accent colour."""
        r = self.RADIUS * (1.7 if yes else 1.0)
        self.setRect(-r, -r, 2 * r, 2 * r)
        self.setBrush(QBrush(SELECTION if yes else WIRE))


#: The categories whose nodes give a geometry: their eye is there even while they fail.
GEOMETRIC_CATEGORIES = ('Shapes', 'Curves', 'Surfaces', 'Meshes', 'Transform', 'Fabrication', 'Simulation',
                        'Environment')


def choose_file(parent, kind: str, base, current=None) -> str | None:
    """The file browser for an input file (an image, a weather file): the path chosen, relative to the project's
    folder when it is inside it (so the project and its files travel together), or None."""
    from pathlib import Path
    from PySide6.QtWidgets import QFileDialog
    from ..images import EXTENSIONS, folder, resolve
    start = Path(base) if base else Path.cwd()
    if current:
        with folder(base):
            start = resolve(str(current))
    if kind == "image":
        patterns = " ".join(f"*.{e}" for e in EXTENSIONS)
        chosen, _ = QFileDialog.getOpenFileName(parent, tr('Choose an image'), str(start),
                                                tr('Images ({patterns})').format(patterns=patterns))
    else:
        chosen, _ = QFileDialog.getOpenFileName(parent, tr('Choose a weather file'), str(start),
                                                tr('Weather files (*.epw *.zip)'))
    if not chosen:
        return None
    path = Path(chosen)
    if base is not None and path.resolve().is_relative_to(Path(base).resolve()):
        path = path.resolve().relative_to(Path(base).resolve())
    return path.as_posix()


class BoxNode(QGraphicsItem):
    """A node of the graph, drawn as a box."""

    #: The eye of the header can be pressed (show or hide in 3D); inside a group, no.
    eyes = True

    def __init__(self, node: Node):
        super().__init__()
        self.node = node
        self.with_error = False
        self.sees = False  # it is shown in 3D
        self.thumbnail = False  # the preview of what comes out, inside the card
        self.several: set[str] = set()  # the numbers marked with Alt + drag, to type one value for all of them
        self._lines: list[str] = []  # what a Panel node shows
        self._drawing = None     # its image (ui/thumbnail.py), until the node is recomputed
        self.source = QFont()
        self.source.setPointSizeF(9)
        self.source_title = QFont(self.source)
        self.source_title.setBold(True)
        self.source_title.setPointSizeF(10)
        self._measure()

        self.ports: dict[str | None, Port] = {}
        for input_ in node.kind.inputs:
            self.ports[input_.name] = Port(self, input_.name, 0)
        self.ports[None] = Port(self, None, HEIGHT_HEADER * 0.7)
        self._place_ports()
        self.ports[None].setToolTip(tr('Output: {output}. Drag from here to connect it to another box.').format(
            output=tr(node.kind.output)))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(1)
        self.setToolTip(tr('{name}: a “{kind}” node. {help}\n“{output}” comes out of the port on the right.').format(
            name=node.name, kind=tr(node.kind.name), help=tr(node.kind.help), output=tr(node.kind.output)))

    def visible(self) -> list:
        """The inputs that are seen (the variables e … h of a formula, only if they are used)."""
        return [e for e in self.node.kind.inputs if visible_input(self.node, e)]

    def _place_ports(self) -> None:
        visible = [e.name for e in self.visible()]
        for name, port in self.ports.items():
            if name is None:
                continue
            port.setVisible(name in visible)
            if name in visible:
                port.setPos(0, HEIGHT_HEADER + (visible.index(name) + 0.5) * HEIGHT_ROW)

    def _measure(self) -> None:
        m, mt = QFontMetricsF(self.source), QFontMetricsF(self.source_title)
        widths = [mt.horizontalAdvance(self.node.name) + 2 * MARGIN + 26 + ICON + 4,
                  m.horizontalAdvance(f"{tr(self.node.kind.name)}      {tr(self.node.kind.output)}") + 2 * MARGIN + 12
                  + ICON + 4]
        for e in self.visible():
            widths.append(m.horizontalAdvance(f"{label_input(e.name)}   {self._fixed_value(e.name)}") + 2 * MARGIN + 16)
        widths[0] += 20                               # the preview button, on the header
        if self.is_group():
            widths.append(m.horizontalAdvance(self._foot_text()) + 2 * MARGIN + 12)
        self._lines = self._lines_panel()
        for line in self._lines:
            widths.append(min(m.horizontalAdvance(line) + 2 * MARGIN + 12, MAX_PANEL_WIDTH))
        self.width = max(WIDTH_WITH_THUMBNAIL if self.with_thumbnail_3d() else MINIMUM_WIDTH, *widths)
        self.height = HEIGHT_HEADER + len(self.visible()) * HEIGHT_ROW + 6
        if self.is_group():
            self.height += HEIGHT_ROW                 # the foot: «3 nodes inside»
        self.height += self.height_panel() + self.height_chart()
        if self.with_thumbnail_3d():
            self.height += HEIGHT_THUMBNAIL + 4

    def _foot_text(self) -> str:
        """The foot of a group: how many nodes it has inside; with «↻» first if it repeats itself (a loop)."""
        n = len(self.node.graph.definitions[self.node.kind.name].nodes)
        text = tr('{n} nodes inside · double-click to enter').format(n=n)
        e = self.node.inputs
        loops = e.get("repeat", 1) != 1 or e.get("keep") == 'every step'
        return f"↻ {text}" if loops else text

    def es_panel(self) -> bool:
        """An Info node: it always shows its values on the card, and it is never seen in 3D."""
        return self.node.kind.name == 'Info'

    def gives_values(self) -> bool:
        """Whether what comes out is numbers, yes/no or texts (not a geometry): it is not seen in 3D, it is read."""
        value = getattr(self.node, "_value", None)
        return value is not None and getattr(value, "kind", None) is None

    def with_thumbnail_3d(self) -> bool:
        """The preview open and of a geometry (a drawing); that of some values is their text."""
        return self.thumbnail and not self.es_panel() and not self.gives_values()

    def shows_button_preview(self) -> bool:
        """The preview button on the card: the cube (a geometry) or the «i» (some values)."""
        return not self.es_panel() and (self.thumbnail or self.gives_geometry() or self.gives_values())

    def _lines_panel(self) -> list[str]:
        """The values read on the card: always in an Info node; in the others that give values (Area, Volume, Formula…),
        on opening their «i»."""
        if not (self.es_panel() or (self.thumbnail and self.gives_values())):
            return []
        value = getattr(self.node, "_value", None)
        if value is None:
            return [tr('(no value: connect something)')]
        origin = self.node.inputs.get("value") if self.es_panel() else self.node   # what it measures (its unit)
        while isinstance(origin, Node) and origin.kind.name == 'Info':
            origin = origin.inputs.get("value")
        magnitude = MAGNITUDE_NODE.get(origin.kind.name) if isinstance(origin, Node) else None
        return lines_of(value, magnitude=magnitude)

    def height_chart(self) -> float:
        return HEIGHT_CHART if self._card_curve() is not None else 0.0

    def _card_curve(self):
        """The curve drawn small on the card: that of a Graph, or the shape of a one-variable Function (normalised to
        0–1), or None."""
        xs = np.linspace(0, 1, 60)
        try:
            if self.node.kind.name == 'Graph':
                from ..geometry import evaluate_chart
                return xs, evaluate_chart(self.node.inputs.get("points"), xs, bool(self.node.inputs.get("smooth", True)))
            if self.node.kind.name == 'Function':
                from ..functions import FUNCTIONS
                variables, _, tally = FUNCTIONS.get(self.node.inputs.get("shape", "wave"), (2, "", None))
                if variables != 1:
                    return None
                centred = self.node.inputs.get("shape") in ("bell", "stair step")
                ys = np.asarray(tally((xs * 2 - 1) if centred else xs * 2, None, 1.0, 1.0), dtype=float)
                range_ = np.ptp(ys)
                return xs, (ys - ys.min()) / range_ if range_ > 0 else ys * 0 + 0.5
        except Exception:
            return None
        return None

    def height_panel(self) -> float:
        return len(self._lines) * HEIGHT_LINE_PANEL + 8 if self._lines else 0.0

    def is_group(self) -> bool:
        return self.node.kind.name in getattr(self.node.graph, "definitions", {})

    def gives_geometry(self) -> bool:
        """Whether what comes out is a geometry (the preview only makes sense then)."""
        value = getattr(self.node, "_value", None)
        return value is not None and getattr(value, "kind", None) is not None

    def shows_eye(self) -> bool:
        """The eye: open if it is seen in 3D; faint and closed if it is a geometry not seen (a click shows it)."""
        if self.es_panel() or self.gives_values():     # Info, or some numbers: there is nothing to see in 3D
            return False
        if getattr(self.node, "_value", None) is None:  # not computed (an error): by what it usually gives
            return self.sees or (BoxNode.eyes and self.node.kind.category in GEOMETRIC_CATEGORIES)
        return self.sees or (BoxNode.eyes and self.gives_geometry())

    def input_in_value(self, where: QPointF):
        """The input whose value is under `where` (the right part of its row), or None."""
        row = int((where.y() - HEIGHT_HEADER) // HEIGHT_ROW)
        visible = self.visible()
        if where.y() < HEIGHT_HEADER or not 0 <= row < len(visible) or not self.width * 0.4 <= where.x() <= self.width:
            return None
        return visible[row]

    def zone_button_eye(self) -> QRectF:
        return QRectF(self.width - MARGIN - 15, 4, 15, 15)

    def zone_button_thumbnail(self) -> QRectF:
        x = self.width - MARGIN - 15 - (20 if self.shows_eye() else 0)
        return QRectF(x, 4, 15, 15)

    def zone_thumbnail(self) -> QRectF:
        y = (HEIGHT_HEADER + (len(self.visible()) + (1 if self.is_group() else 0)) * HEIGHT_ROW + 2 + self.height_panel()
             + self.height_chart())
        return QRectF(MARGIN - 4, y, self.width - 2 * MARGIN + 8, HEIGHT_THUMBNAIL)

    def put_drawing(self, image) -> None:
        self._drawing = image
        self.update()

    def _fixed_value(self, input_: str) -> str:
        v = self.node.inputs[input_]
        if isinstance(v, Node):
            return ""
        if v is None:                            # an empty level: it says which it will use
            auto = automatic_level(self.node, input_)
            if auto:
                return tr("auto: {level}").format(level=tr(auto))
        if isinstance(v, Data):                  # what reaches a group input: its shape, short
            return text_shape(v)
        if isinstance(v, str) and v in self.node.kind.input_(input_).options:
            return tr(v)                         # a fixed option, in the language of the interface
        return text_of(input_, v, is_length(self.node, input_))

    def _drops_down(self, input_) -> bool:
        """It is chosen from a list (options, the levels of another input, names offered), not connected."""
        if isinstance(self.node.inputs.get(input_.name), Node):
            return False
        return bool(input_.options or input_.levels_of or input_.suggest is not None)

    def boundingRect(self) -> QRectF:
        extra = 12 if self.is_group() else 6          # the halo of the chosen one; in a group, the cards behind
        return QRectF(-6, -6, self.width + 6 + extra, self.height + 6 + extra)

    def _paint_switch(self, painter: QPainter, row: QRectF, on: bool) -> None:
        """A small switch on the right of the row, with «yes» or «no» to its left (as in the panel)."""
        width, height = 24.0, 13.0
        hint = QRectF(row.right() - width, row.center().y() - height / 2, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.color("accent", "#8a7dff")) if on else EDGE.lighter(160))
        painter.drawRoundedRect(hint, height / 2, height / 2)
        r = height - 4
        x = hint.right() - r - 2 if on else hint.left() + 2
        painter.setBrush(QColor("#ffffff") if on else SMOOTH_TEXT)
        painter.drawEllipse(QRectF(x, hint.top() + 2, r, r))
        painter.setPen(TEXT if on else SMOOTH_TEXT)
        painter.drawText(QRectF(row.left(), row.top(), row.width() - width - 5, row.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, tr('yes') if on else tr("no"))

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width, self.height)
        color = COLOURS_CATEGORY.get(self.node.kind.category, BODY)
        edge = RED if self.with_error else (SELECTION if self.isSelected() else EDGE)

        if self.is_group():                     # a group: a deck of cards (several nodes in one)
            # They peek out below only: on the right they would cover where the output wire leaves the card, and it
            # would seem to come from the cards behind.
            for d in (10, 5):
                painter.setPen(QPen(_with_alpha(color, 150), 1))
                painter.setBrush(BODY.darker(115 if d == 5 else 125))
                painter.drawRoundedRect(rect.adjusted(3 * d / 5, d, -3 * d / 5, d), RADIUS, RADIUS)
        if self.isSelected():                   # chosen: a halo of the accent, even if the border is the red of an error
            painter.setPen(QPen(_with_alpha(SELECTION, 110), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), RADIUS + 3, RADIUS + 3)
        painter.setPen(QPen(edge, 2 if (self.with_error or self.isSelected()) else 1))
        painter.setBrush(BODY)
        painter.drawRoundedRect(rect, RADIUS, RADIUS)

        # The header: the top part of the rounded card, cut straight at the bottom
        # (whole in its colour, or only a band).
        card = QPainterPath()
        card.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        painter.save()
        painter.setClipRect(QRectF(0, 0, self.width, HEIGHT_HEADER if HEADER == "filled" else 4))
        painter.fillPath(card, color)
        painter.restore()
        if HEADER != "filled":
            painter.setPen(QPen(_with_alpha(EDGE, 255), 1))
            painter.drawLine(QPointF(1, HEIGHT_HEADER), QPointF(self.width - 1, HEIGHT_HEADER))

        if self.shows_eye():  # the eye: seen in 3D (open) or not (closed and faint); a click changes it
            painter.save()
            painter.setOpacity(1.0 if self.sees else 0.45)
            icons.paint(painter, "eye" if self.sees else "eye_closed", TEXT_HEADER.name(),
                          self.zone_button_eye())
            painter.restore()
        if self.shows_button_preview():  # the preview: the cube (or the «i» of some values), brighter if it is open
            painter.save()
            painter.setOpacity(1.0 if self.thumbnail else 0.45)
            icons.paint(painter, "info" if self.gives_values() else "view3d", TEXT_HEADER.name(),
                          self.zone_button_thumbnail())
            painter.restore()

        # The category icon: white on the filled header, in its colour on the band.
        ink = TEXT_HEADER if HEADER == "filled" else color
        # (Code, written by whoever made the project, has its own: seen at a glance; an extension may bring one.)
        category = icons.of_kind(self.node.kind.name, self.node.kind.category)
        if category:
            icons.paint(painter, category, ink.name(), QRectF(MARGIN - 1, 5, ICON, ICON))
        x = MARGIN + ICON + 4
        painter.setPen(TEXT_HEADER)
        painter.setFont(self.source_title)
        painter.drawText(QRectF(x, 3, self.width - x - MARGIN - 36, 19), Qt.AlignmentFlag.AlignVCenter, self.node.name)
        painter.setFont(self.source)
        painter.setPen(_with_alpha(TEXT_HEADER, 190))
        second = QRectF(x, 20, self.width - x - MARGIN, 17)
        painter.drawText(second, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, tr(self.node.kind.name))
        painter.setPen(_with_alpha(TEXT_HEADER, 150))  # what comes out, next to its port
        painter.drawText(second, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, tr(self.node.kind.output))

        for i, e in enumerate(self.visible()):
            y = HEIGHT_HEADER + i * HEIGHT_ROW
            row = QRectF(MARGIN + 4, y, self.width - 2 * MARGIN - 4, HEIGHT_ROW)
            painter.setPen(TEXT)
            painter.drawText(row, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label_input(e.name))
            value = self._fixed_value(e.name)
            if e.name in self.several:              # marked with Alt + drag: one value for all of them
                painter.setPen(QPen(SELECTION, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(QRectF(self.width * 0.42, y + 2, self.width * 0.58 - MARGIN, HEIGHT_ROW - 4),
                                        4, 4)
            if isinstance(self.node.inputs.get(e.name), bool):   # a yes/no: a switch, with a click
                self._paint_switch(painter, row, self.node.inputs[e.name])
            elif e.file and not isinstance(self.node.inputs.get(e.name), Node):
                # A file: its name (without the folders) and the folder icon; a click chooses it.
                folder = QRectF(row.right() - ICON, y + (HEIGHT_ROW - ICON) / 2, ICON, ICON)
                icons.paint(painter, "open", SMOOTH_TEXT.name(), folder)
                from pathlib import PurePath
                name = PurePath(str(self.node.inputs.get(e.name) or "")).name or tr('choose…')
                text_zone = QRectF(row.left() + row.width() * 0.4, y, row.width() * 0.6 - ICON - 4, HEIGHT_ROW)
                name = QFontMetricsF(self.source).elidedText(name, Qt.TextElideMode.ElideLeft, text_zone.width())
                painter.setPen(SMOOTH_TEXT)
                painter.drawText(text_zone, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, name)
            elif self._drops_down(e):
                # A list to choose from: a small chevron on the right says so (a click opens it).
                chevron = QRectF(row.right() - 9, y + (HEIGHT_ROW - 9) / 2, 9, 9)
                icons.paint(painter, "chevron_down", SMOOTH_TEXT.name(), chevron)
                if value:
                    painter.setPen(RED if value == tr("missing") else SMOOTH_TEXT)
                    painter.drawText(row.adjusted(0, 0, -13, 0), Qt.AlignmentFlag.AlignVCenter |
                                     Qt.AlignmentFlag.AlignRight, value)
            elif value:
                painter.setPen(RED if value == tr("missing") else SMOOTH_TEXT)
                painter.drawText(row, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, value)

        if self.is_group():                     # the foot: how many nodes it has inside
            foot = QRectF(MARGIN + 4, HEIGHT_HEADER + len(self.visible()) * HEIGHT_ROW, self.width - 2 * MARGIN - 4,
                         HEIGHT_ROW)
            painter.setPen(_with_alpha(color, 230))
            painter.drawText(foot, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._foot_text())

        if self.height_chart():                  # the curve of the Graph (or the shape of the Function), small
            y0 = HEIGHT_HEADER + (len(self.visible()) + (1 if self.is_group() else 0)) * HEIGHT_ROW + 2
            zone = QRectF(MARGIN - 4, y0, self.width - 2 * MARGIN + 8, HEIGHT_CHART - 6)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_with_alpha(DEPTH, 160))
            painter.drawRoundedRect(zone, RADIUS * 0.6, RADIUS * 0.6)
            inside = zone.adjusted(6, 6, -6, -6)
            try:
                xs, ys = self._card_curve()
                path = QPainterPath(QPointF(inside.left(), inside.bottom() - ys[0] * inside.height()))
                for x, y in zip(xs[1:], ys[1:]):
                    path.lineTo(QPointF(inside.left() + x * inside.width(), inside.bottom() - y * inside.height()))
                painter.setPen(QPen(SELECTION, 1.8))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
            except Exception:                    # some points that do not serve yet: the card, without a curve
                pass
        if self._lines:                         # the Panel: what it is worth, on a darker background
            y0 = HEIGHT_HEADER + (len(self.visible()) + (1 if self.is_group() else 0)) * HEIGHT_ROW + 2 + self.height_chart()
            zone = QRectF(MARGIN - 4, y0, self.width - 2 * MARGIN + 8, self.height_panel() - 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_with_alpha(DEPTH, 160))
            painter.drawRoundedRect(zone, RADIUS * 0.6, RADIUS * 0.6)
            painter.setPen(TEXT)
            measures = QFontMetricsF(self.source)
            for i, line in enumerate(self._lines):
                row = QRectF(MARGIN + 2, y0 + 2 + i * HEIGHT_LINE_PANEL, self.width - 2 * MARGIN - 4, HEIGHT_LINE_PANEL)
                text = measures.elidedText(line, Qt.TextElideMode.ElideRight, row.width())
                painter.drawText(row, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        if self.with_thumbnail_3d():
            zone = self.zone_thumbnail()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_with_alpha(DEPTH, 140))
            painter.drawRoundedRect(zone, RADIUS * 0.6, RADIUS * 0.6)
            if self._drawing is not None:
                size_ = self._drawing.size() / self._drawing.devicePixelRatio()
                painter.drawImage(QPointF(zone.center().x() - size_.width() / 2,
                                          zone.center().y() - size_.height() / 2), self._drawing)
            else:
                painter.setPen(SMOOTH_TEXT)
                painter.drawText(zone, Qt.AlignmentFlag.AlignCenter,
                                 tr('with error') if self.with_error else tr('no geometry'))

    def refresh(self) -> None:
        """Measures and draws the box again (its name or a fixed value changed)."""
        self.prepareGeometryChange()
        self._measure()
        self._place_ports()
        self.ports[None].setPos(self.width, HEIGHT_HEADER * 0.7)
        for p in self.ports.values():
            for c in p.cables:
                c.sync()
        self.update()

    def put_error(self, yes: bool) -> None:
        if yes != self.with_error:
            self.with_error = yes
            self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and (SETTING["grid"] or SETTING["guides"]):
            x, y = value.x(), value.y()
            guided_x = guided_y = False
            # Smart guides: the edges and the centre of the box snap to those of the others.
            if SETTING["guides"] and self.isSelected() and len(self.scene().selectedItems()) == 1:
                (x, guided_x), (y, guided_y) = self._guides(x, y)
            # Snapping to the grid, on the axis a guide did not take.
            if SETTING["grid"]:
                if not guided_x:
                    x = round(x / STEP_GRID) * STEP_GRID
                if not guided_y:
                    y = round(y / STEP_GRID) * STEP_GRID
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for p in self.ports.values():
                for c in p.cables:
                    c.sync()
        return super().itemChange(change, value)


    def _guides(self, x: float, y: float):
        """Where to snap the box (in x and in y) to the others, and the guide lines seen while moving it."""
        views = self.scene().views()
        scale = views[0].transform().m11() if views else 1.0
        tolerance = GUIDE_PIXELS / max(scale, 0.05)
        others = [c for c in self.scene().items() if isinstance(c, BoxNode) and c is not self]
        lines = []

        def paste(mine: list[float], other_from):
            best = None                                   # (distance, correction, value, other)
            for o in others:
                for m in mine:
                    for v in other_from(o):
                        d = abs(m - v)
                        if d <= tolerance and (best is None or d < best[0]):
                            best = (d, v - m, v, o)
            return best

        bx = paste([x, x + self.width / 2, x + self.width], lambda o: (o.x(), o.x() + o.width / 2, o.x() + o.width))
        by = paste([y, y + self.height / 2, y + self.height], lambda o: (o.y(), o.y() + o.height / 2, o.y() + o.height))
        if bx:
            x += bx[1]
            o = bx[3]
            lines.append(QLineF(bx[2], min(y, o.y()) - 12, bx[2], max(y + self.height, o.y() + o.height) + 12))
        if by:
            y += by[1]
            o = by[3]
            lines.append(QLineF(min(x, o.x()) - 12, by[2], max(x + self.width, o.x() + o.width) + 12, by[2]))
        for view in views:
            if isinstance(view, Editor):
                view.display_guides(lines)
        return (x, bx is not None), (y, by is not None)


class Wire(QGraphicsPathItem):
    """A connection: from the output of a node to an input of another, with the shape of the data written."""

    def __init__(self, output: Port, input_: Port):
        super().__init__()
        self.output, self.input_ = output, input_
        output.cables.append(self)
        input_.cables.append(self)
        self.setZValue(0)
        self._lit = False
        self.label = QGraphicsSimpleTextItem(self)
        source = QFont()
        source.setPointSizeF(8)
        self.label.setFont(source)
        self.put_shape("")

    def put_shape(self, text: str, error: bool = False, waiting: bool = False) -> None:
        self.label.setText(text)
        self._error, self._waiting = error, waiting
        self.colour_by()
        self.sync()

    def colour_by(self) -> None:
        """The colours of the wire and of its label, those of the canvas background (they change with it); in the
        accent, if a card it joins is chosen; faint, if what it carries is not calculated."""
        text = self.label.text()
        colour = RED if self._error else (SELECTION if self._lit else WIRE)
        waiting = getattr(self, "_waiting", False)
        width = 2.0 if text and text != "·" and not waiting else 1.5
        self.setPen(QPen(colour, width + (0.8 if self._lit else 0.0)))
        if waiting and not self._lit:
            colour = QColor(colour)
            colour.setAlpha(130)
        self.label.setBrush(colour)

    def light(self, yes: bool) -> None:
        """A wire of a chosen card: in the accent and above the cards, so it is seen where it comes from even where
        it passes behind another card (a wire is drawn below the cards)."""
        if yes != self._lit:
            self._lit = yes
            self.setZValue(1.5 if yes else 0)
            self.colour_by()

    def sync(self) -> None:
        a, b = self.output.centre(), self.input_.centre()
        dx = max(40.0, abs(b.x() - a.x()) * 0.5)
        path = QPainterPath(a)
        path.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
        self.setPath(path)
        middle = path.pointAtPercent(0.5)
        r = self.label.boundingRect()
        self.label.setPos(middle.x() - r.width() / 2, middle.y() - r.height() - 2)


def _without_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def editable(node: Node) -> bool:
    """A node with an editor of its own: a curve drawn by hand, a mesh whose vertices are moved, a Code node."""
    if node.kind.name == 'Code':
        return not isinstance(node.inputs.get("code"), Node)
    return node.kind.name in ('Edit mesh', 'Equilibrium') or drawable(node)


def find_kinds(text: str, own=None, library=None) -> list[NodeType]:
    """The node kinds that match what was written: by name, synonym or category, without accents.

    First those that start with what was written; then those that contain it. `own`: the project's kinds (its groups),
    which go first; `library`: the groups of the library, after.
    """
    t = _without_accents(text.strip())
    own = list((own or {}).values())
    names_own = {p.name for p in own}
    from_library = [b for b in (library or {}).values() if b.name not in names_own]

    def first_essentials(kinds):
        return sorted(kinds, key=lambda kind: (0 if kind in own else 1 if kind in from_library else 2,
                                               kind.name not in ESSENTIALS))

    all_ = [*own, *from_library, *CATALOG.values()]
    if not t:
        return first_essentials(all_)
    start, contain = [], []
    for kind in all_:
        # In both languages: «caja» finds Box even if the interface is in English, and the other way round.
        words = [_without_accents(p) for p in (kind.name, *in_spanish(kind.name), *kind.synonyms)]
        if any(p.startswith(t) for p in words):
            start.append(kind)
        elif any(t in p for p in words) or t in _without_accents(kind.category) or t in _without_accents(in_spanish(kind.category)[0]):
            contain.append(kind)
    return first_essentials(start) + first_essentials(contain)


def synonym_shown(kind: NodeType, by: str | None, text: str = "") -> str | None:
    """The synonym printed next to a node found with it, or None: not the name of another program, and not when the
    name shown already has what was written (`text`, without accents)."""
    if not by or by in PROGRAM_NAMES:
        return None
    if text and text in _without_accents(tr(kind.name)):
        return None
    return by


class Finder(QFrame):
    """A small window to choose a node kind by writing part of its name."""

    chosen = Signal(object, object)  # NodeType and the synonym it was found with (or None)

    def __init__(self, parent=None, own=None, library=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.own = own or {}                     # the project's groups
        self.library = {n: t for n, t in (library or {}).items() if n not in self.own}
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.field = QLineEdit()
        self.field.setPlaceholderText(tr('Find a node: box, grid, fin, attractor…'))
        self.list_ = QListWidget()
        self.list_.setMinimumSize(340, 300)
        layer = QVBoxLayout(self)
        layer.setContentsMargins(6, 6, 6, 6)
        layer.addWidget(self.field)
        layer.addWidget(self.list_)
        self.field.textChanged.connect(self._filter)
        self.field.returnPressed.connect(self._accept)
        self.list_.itemActivated.connect(lambda _: self._accept())
        self.list_.itemClicked.connect(lambda item: self._accept(item))      # one click is enough
        self.field.installEventFilter(self)
        self._filter("")

    def _section(self, title: str) -> None:
        """A heading in the list (it is not chosen): «Project groups», «Nodes»."""
        item = QListWidgetItem(tr(title).upper())
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        source = QFont(self.list_.font())
        source.setPointSizeF(max(7.0, source.pointSizeF() * 0.8))
        source.setBold(True)
        item.setFont(source)
        item.setForeground(SMOOTH_TEXT)
        self.list_.addItem(item)

    def _filter(self, text: str) -> None:
        self.list_.clear()
        t = _without_accents(text.strip())
        kinds = find_kinds(text, self.own, self.library)
        there_is_groups = any(x.name in self.own or x.name in self.library for x in kinds)
        section = None
        for kind in kinds:
            # The project's groups, those of the library and the usual nodes, each one with its heading.
            current = ('Project groups' if kind.name in self.own
                      else 'Library' if kind.name in self.library else 'Nodes')
            if there_is_groups and current != section:
                self._section(current)
                section = current
            # If it was found by a synonym, say which: «Box, louvre».
            by = next((p for p in kind.synonyms if t and t in _without_accents(p)), None)
            if t and t in _without_accents(kind.name):
                by = None
            # The category is said by the icon (and its colour); the synonym it was found with, in text.
            shown = synonym_shown(kind, by, t)
            item = QListWidgetItem(tr(kind.name) + (f"   — «{shown}»" if shown else ""))
            item.setToolTip(f"{tr(kind.category)}. {tr(kind.help)}")
            item.setIcon(_icon_category(kind.category, kind.name))
            item.setData(Qt.ItemDataRole.UserRole, (kind, by))
            self.list_.addItem(item)
        self._move(0, 1)

    def eventFilter(self, object_, event) -> bool:
        # The arrows move the list's selection without leaving the text field.
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            self._move(self.list_.currentRow() + step, step)
            return True
        # (QFrame, not super(): the project's node finder uses this same filter and is not a Finder)
        return QFrame.eventFilter(self, object_, event)

    def _move(self, row: int, step: int) -> None:
        """To the row `row`, skipping the headings (in the direction `step`)."""
        n = self.list_.count()
        while 0 <= row < n and not self.list_.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
            row += step
        if 0 <= row < n:
            self.list_.setCurrentRow(row)

    def _accept(self, item=None) -> None:
        item = item or self.list_.currentItem()
        if item is not None and not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return                              # a heading: it is neither chosen nor closed
        if item is not None:
            self.chosen.emit(*item.data(Qt.ItemDataRole.UserRole))
        self.close()

    def open_in(self, global_point) -> None:
        self.field.clear()
        self._filter("")
        self.move(global_point)
        self.show()
        self.field.setFocus()


class NodesFinder(QFrame):
    """A small window to find a node of the project by writing part of its name or its kind."""

    chosen = Signal(str)

    def __init__(self, graph: Graph, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.graph = graph
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.field = QLineEdit()
        self.field.setPlaceholderText(tr('Search the project: a name (panels) or a type (Formula)…'))
        self.list_ = QListWidget()
        self.list_.setMinimumSize(340, 300)
        layer = QVBoxLayout(self)
        layer.setContentsMargins(6, 6, 6, 6)
        layer.addWidget(self.field)
        layer.addWidget(self.list_)
        self.field.textChanged.connect(self._filter)
        self.field.returnPressed.connect(self._accept)
        self.list_.itemActivated.connect(lambda _: self._accept())
        self.list_.itemClicked.connect(lambda item: self._accept(item))      # one click is enough
        self.field.installEventFilter(self)
        self._filter("")

    def _filter(self, text: str) -> None:
        t = _without_accents(text.strip())
        self.list_.clear()
        for name, node in self.graph.nodes.items():
            if not t or t in _without_accents(name) or t in _without_accents(node.kind.name) or \
                    t in _without_accents(tr(node.kind.name)):
                item = QListWidgetItem(f"{name}   ·   {tr(node.kind.name)}")
                item.setIcon(_icon_category(node.kind.category, node.kind.name))
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.list_.addItem(item)
        self._move(0, 1)

    eventFilter = Finder.eventFilter

    def _move(self, row: int, step: int) -> None:
        """To the row `row`, skipping the headings (in the direction `step`)."""
        n = self.list_.count()
        while 0 <= row < n and not self.list_.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
            row += step
        if 0 <= row < n:
            self.list_.setCurrentRow(row)

    def _accept(self, item=None) -> None:
        item = item or self.list_.currentItem()
        if item is not None and not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return                              # a heading: it is neither chosen nor closed
        if item is not None:
            self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))
        self.close()

    def open_in(self, global_point) -> None:
        self.move(global_point)
        self.show()
        self.field.setFocus()


class Editor(QGraphicsView):
    """The canvas with the project's graph.

    Editing: dragging from an output to an input (or the other way round) connects; dragging the end of a wire from its
    input disconnects it (and it can be dropped on another input); right-click on a wire, Disconnect; Del deletes the
    selected nodes.

    Each change is applied to the graph and reported with `changed`; a change that cannot be made (a cycle) is explained
    with `warning`.
    """

    changed = Signal()
    moved = Signal()  # some box moved (it changes the project, not the computation)
    notes_changed = Signal()  # an annotation (text, arrow, frame) was added, moved, written or deleted
    warning = Signal(str)
    selected = Signal(object)  # the name of the selected node, or None
    value_changed = Signal(str, str, str)  # node, input, text written on the card itself
    values_changed = Signal(str, list, str)  # node, inputs, one text for all of them (Alt + drag on the card)
    enter = Signal(str)                    # double-click on a group: see it inside
    code = Signal(str)                     # double-click on the code of a Code node: its editor
    edit = Signal(str)                     # double-click on a node with an editor (a curve, a mesh, code): it opens
    toggle_see = Signal(str, bool)        # click on the eye of a card: see it in 3D or not
    isolate = Signal(str)                    # Alt + click on the eye: only that node in the 3D view
    #: What the window adds to the right-click menu: f(menu, node name or None if it is the background).
    on_ask_menu = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.graph_scene = QGraphicsScene(self)
        self._annotations: list = []        # the annotations of the canvas (texts, arrows, frames)
        self.setScene(self.graph_scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(DEPTH)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.graph: Graph | None = None
        self.new: set[str] = set()              # nodes just put that have not given a result yet
        self.boxes: dict[str, BoxNode] = {}
        self.cables: list[Wire] = []
        self._panning: QPointF | None = None
        self._pulling: Port | None = None        # the port a new wire is dragged from
        self._provisional_wire: QGraphicsPathItem | None = None
        self._failures: set[str] = set()
        self.graph_scene.selectionChanged.connect(self._warn_selection)
        self.graph_scene.changed.connect(lambda _=None: self._widen_canvas())
        annotations.ON_CHANGE["funcion"] = self.notes_changed.emit

    def apply_theme(self) -> None:
        """Paints the canvas again with the theme's colours (ui/theme.py changes them)."""
        self.setBackgroundBrush(DEPTH)
        for box in self.boxes.values():
            box.update()
        for item in self.graph_scene.items():
            if isinstance(item, Wire):
                item.colour_by()
        self.graph_scene.update()

    def _warn_selection(self) -> None:
        try:
            boxes = [i for i in self.graph_scene.selectedItems() if isinstance(i, BoxNode)]
        except RuntimeError:  # the scene is being deleted
            return
        self.selected.emit(boxes[0].node.name if len(boxes) == 1 else None)
        self._light_wires(boxes)

    def _light_wires(self, boxes=None) -> None:
        """The wires of the chosen cards, in the accent and above the cards."""
        if boxes is None:
            try:
                boxes = [i for i in self.graph_scene.selectedItems() if isinstance(i, BoxNode)]
            except RuntimeError:
                return
        chosen = set(boxes)
        for wire in self.cables:
            wire.light(wire.output.box in chosen or wire.input_.box in chosen)

    def rename_box(self, old: str, new_: str) -> None:
        """The node `old` is now called `new_` (the graph already knows)."""
        box = self.boxes.pop(old)
        self.boxes[new_] = box
        box.refresh()

    def arrange_all(self) -> None:
        """Rearranges all the boxes from left to right by the flow (exact: without snapping to the grid)."""
        positions = arrange(self.graph)

        def move():
            for name, (x, y) in positions.items():
                self.boxes[name].setPos(x, y)

        self._without_setting(move)
        self.frame()

    def _without_setting(self, move) -> None:
        """Moves without snapping to the grid or the guides: align and distribute give exact positions."""
        before = dict(SETTING)
        SETTING.update(grid=False, guides=False)
        try:
            move()
        finally:
            SETTING.update(before)
        self.moved.emit()

    def chosen(self) -> list["CajaNodo"]:
        return [i for i in self.graph_scene.selectedItems() if isinstance(i, BoxNode)]

    def align(self, as_: str) -> None:
        """Aligns the chosen boxes: «left», «centre» or «right» (in x); «up», «mid» or «down» (in y)."""
        boxes = self.chosen()
        if len(boxes) < 2:
            self.warning.emit(tr('To align, select two or more boxes (drag a rectangle, or Ctrl + click).'))
            return

        def move():
            if as_ in ("left", "centre", "right"):
                if as_ == "left":
                    x = min(c.pos().x() for c in boxes)
                    for c in boxes:
                        c.setPos(x, c.pos().y())
                elif as_ == "right":
                    x = max(c.pos().x() + c.width for c in boxes)
                    for c in boxes:
                        c.setPos(x - c.width, c.pos().y())
                else:
                    x = sum(c.pos().x() + c.width / 2 for c in boxes) / len(boxes)
                    for c in boxes:
                        c.setPos(x - c.width / 2, c.pos().y())
            else:
                if as_ == "up":
                    y = min(c.pos().y() for c in boxes)
                    for c in boxes:
                        c.setPos(c.pos().x(), y)
                elif as_ == "down":
                    y = max(c.pos().y() + c.height for c in boxes)
                    for c in boxes:
                        c.setPos(c.pos().x(), y - c.height)
                else:
                    y = sum(c.pos().y() + c.height / 2 for c in boxes) / len(boxes)
                    for c in boxes:
                        c.setPos(c.pos().x(), y - c.height / 2)

        self._without_setting(move)

    def distribute(self, direction: str) -> None:
        """Spreads the chosen boxes with the same space between one and the next: «horizontal» or «vertical».

        The ones at the ends do not move; those in the middle do.
        """
        boxes = self.chosen()
        if len(boxes) < 3:
            self.warning.emit(tr('To distribute, select three or more boxes.'))
            return
        horizontal = direction == "horizontal"
        key = (lambda c: c.pos().x()) if horizontal else (lambda c: c.pos().y())
        size = (lambda c: c.width) if horizontal else (lambda c: c.height)
        boxes.sort(key=key)
        total = key(boxes[-1]) + size(boxes[-1]) - key(boxes[0])
        hole = (total - sum(size(c) for c in boxes)) / (len(boxes) - 1)

        def move():
            place = key(boxes[0])
            for c in boxes:
                if horizontal:
                    c.setPos(place, c.pos().y())
                else:
                    c.setPos(c.pos().x(), place)
                place += size(c) + hole

        self._without_setting(move)

    # --- Preview on the card ----------------------------------------------------

    def toggle_thumbnail(self, names, yes: bool | None = None) -> None:
        """Opens or closes the preview of those cards (`yes`: force it; if not, that of the first one toggles)."""
        boxes = [self.boxes[n] for n in names if n in self.boxes]
        if not boxes:
            return
        yes = (not boxes[0].thumbnail) if yes is None else yes
        for box in boxes:
            if box.thumbnail != yes:
                box.thumbnail = yes
                box.refresh()
        self._draw_thumbnails([c for c in boxes if yes])
        self.moved.emit()                             # it is remembered with the project (and undone)

    def thumbnails(self) -> list[str]:
        return [n for n, c in self.boxes.items() if c.thumbnail]

    def _schedule_thumbnails(self) -> None:
        """After recomputing: the open previews are redone a moment later (dragging a slider they are not redone at each
        step, only when it stops)."""
        if not any(c.thumbnail for c in self.boxes.values()):
            return
        if not hasattr(self, "_clock_thumbnails"):
            from PySide6.QtCore import QTimer
            self._clock_thumbnails = QTimer(self)
            self._clock_thumbnails.setSingleShot(True)
            self._clock_thumbnails.setInterval(150)
            self._clock_thumbnails.timeout.connect(lambda: self._draw_thumbnails())
        self._clock_thumbnails.start()

    def _draw_thumbnails(self, boxes=None) -> None:
        from .thumbnail import draw
        for box in boxes if boxes is not None else [c for c in self.boxes.values() if c.thumbnail]:
            if not box.with_thumbnail_3d():           # some values: their text is already on the card
                box.refresh()
                continue
            zone = box.zone_thumbnail()
            value = getattr(box.node, "_value", None)
            try:
                image = draw(value, int(zone.width()) - 8, int(zone.height()) - 8, COLOR_THUMBNAIL,
                                 BODY.name()) if value is not None else None
            except (ValueError, IndexError, TypeError):
                image = None
            box.put_drawing(image)

    # --- Copiar, cortar, pegar, duplicar ------------------------------------------------

    KIND_CLIPBOARD = "application/x-tensela-nodos"

    def select_all(self) -> None:
        for box in self.boxes.values():
            box.setSelected(True)

    def _chosen_fragment(self) -> dict | None:
        from ..project_file import fragment
        names = [c.node.name for c in self.chosen()]
        if not names:
            return None
        return fragment(self.graph, names, self.positions())

    def copy(self) -> bool:
        """The chosen boxes, to the clipboard (they are pasted here or in another project)."""
        import json

        from PySide6.QtCore import QMimeData
        from PySide6.QtWidgets import QApplication
        frag = self._chosen_fragment()
        if frag is None:
            return False
        text = json.dumps(frag, ensure_ascii=False)
        data_items = QMimeData()
        data_items.setData(self.KIND_CLIPBOARD, text.encode("utf-8"))
        data_items.setText(text)
        QApplication.clipboard().setMimeData(data_items)
        return True

    def cut(self) -> None:
        if self.copy():
            self.delete([c.node.name for c in self.chosen()])

    def paste(self, at=None) -> None:
        """Pastes what was copied; `at`: point of the scene (if not, next to the mouse or at the centre of the view)."""
        import json

        from PySide6.QtWidgets import QApplication
        data_items = QApplication.clipboard().mimeData()
        if data_items is None or self.graph is None:
            return
        raw = bytes(data_items.data(self.KIND_CLIPBOARD)).decode("utf-8") or data_items.text()
        try:
            frag = json.loads(raw)
        except ValueError:
            return
        if not isinstance(frag, dict) or not ("nodes" in frag or "nodes" in frag):      # (copied by an older version: "nodos")
            return
        from ..project_file import in_english
        frag = in_english(frag)
        if at is None:
            mouse = self.mapFromGlobal(QCursor.pos())
            at = self.mapToScene(mouse if self.viewport().rect().contains(mouse) else self.viewport().rect().center())
        self._put_fragment(frag, at, with_inputs=False)

    def duplicate(self) -> None:
        """A copy of the chosen boxes, next to them, that keeps using the same inputs from outside."""
        frag = self._chosen_fragment()
        if frag is None:
            return
        positions = frag["positions"].values()
        x0 = min((p[0] for p in positions), default=0.0)
        y0 = min((p[1] for p in positions), default=0.0)
        self._put_fragment(frag, QPointF(x0 + 2 * STEP_GRID, y0 + 2 * STEP_GRID), with_inputs=True)

    def _put_fragment(self, frag: dict, at: QPointF, with_inputs: bool) -> None:
        from ..project_file import paste_fragment
        try:
            new = paste_fragment(self.graph, frag, with_inputs)
        except (ShapeError, KeyError, TypeError, ValueError) as error:
            self.warning.emit(tr('Could not paste: {error}').format(error=error))
            return
        self.new.update(new.values())       # pasted or duplicated: they are also seen in 3D if they give geometry
        positions = frag.get("positions", {})
        x0 = min((p[0] for p in positions.values()), default=0.0)
        y0 = min((p[1] for p in positions.values()), default=0.0)
        self.graph_scene.clearSelection()
        for i, (old, new_) in enumerate(new.items()):
            x, y = positions.get(old, (x0 + 30 * i, y0 + 30 * i))
            box = self._put_box(self.graph.nodes[new_], (at.x() + x - x0, at.y() + y - y0))
            box.setSelected(True)
        self._redo_cables()
        self.changed.emit()

    def visible_mark(self, names) -> None:
        """Puts the eye on the boxes of the nodes seen in 3D."""
        for name, box in self.boxes.items():
            if box.sees != (name in names):
                box.sees = name in names
                box.update()

    def select(self, name: str) -> None:
        self.graph_scene.clearSelection()
        if name in self.boxes:
            self.boxes[name].setSelected(True)
            self.centerOn(self.boxes[name])

    # --- Construir ------------------------------------------------------------

    def display(self, graph: Graph, positions: dict[str, list[float]] | None = None,
                frame: bool = True, thumbnails=(), notes=()) -> None:
        """Draws the graph. The boxes without a saved position arrange themselves; `thumbnails`: those that have the
        preview open; `notes`: the annotations (texts, arrows, frames)."""
        if graph is not self.graph:              # another project (or another group): its new nodes are not these
            self.new.clear()
        self.graph = graph
        self.graph_scene.clear()
        self.boxes.clear()
        self.cables.clear()
        self._annotations.clear()
        positions = dict(positions or {})
        automatic = arrange(graph)
        for name, node in graph.nodes.items():
            box = self._put_box(node, positions.get(name, automatic[name]))
            box.thumbnail = name in thumbnails
        self._redo_cables()
        for d in notes:
            item = annotations.from__dict(d)
            if item is not None:
                self._put_note(item)
        if frame:
            self.frame()

    # --- Annotations (outside the computation) -------------------------------------------

    def notes(self) -> list[dict]:
        """The annotations of the canvas, as they are saved: from back to front (the frames first)."""
        items = [i for i in self.graph_scene.items() if isinstance(i, annotations.Annotation)]
        items.sort(key=lambda i: (i.zValue(), i.pos().y(), i.pos().x()))
        return [i.a_dict() for i in items]

    def annotate(self, kind: str, where: QPointF) -> None:
        """A new annotation where it was asked for: a text (to write at once), an arrow or a frame."""
        item = annotations.from__dict({"type": kind, "x": where.x(), "y": where.y(),
                                       "x2": where.x() + 140, "y2": where.y()})
        self._put_note(item)
        self.graph_scene.clearSelection()
        item.setSelected(True)
        self.notes_changed.emit()
        if isinstance(item, annotations.NoteText):
            item.write()
        elif isinstance(item, annotations.Frame):
            item.change_title()

    def _put_note(self, item) -> None:
        # The canvas keeps each annotation (as it keeps the boxes in `boxes`): if only the scene had it,
        # Python could free it at any moment and it would disappear from the canvas a second after putting it.
        self._annotations.append(item)
        self.graph_scene.addItem(item)

    def _delete_notes(self, items) -> None:
        for item in items:
            self.graph_scene.removeItem(item)
            if item in self._annotations:
                self._annotations.remove(item)
        if items:
            self.notes_changed.emit()

    @staticmethod
    def _shows(hexa: str | None) -> QIcon:
        """A small square of the colour, for the colour menus."""
        if hexa is None:
            return QIcon()
        shows = QPixmap(14, 14)
        shows.fill(QColor(hexa))
        return QIcon(shows)

    def _menu_note(self, menu: QMenu, item) -> None:
        if isinstance(item, annotations.NoteText):
            menu.addAction(tr('Write'), item.write)
            style_name = menu.addMenu(tr('Style'))
            only = not item.settings["background"] and not item.settings["border"]
            for text, yes in (('Text only', True), ('With background and border', False)):
                a = style_name.addAction(tr(text), lambda s=yes: item.only_text(s))
                a.setCheckable(True)
                a.setChecked(only == yes)
            sizes = menu.addMenu(tr('Text size'))
            for name, points in annotations.SIZES.items():
                a = sizes.addAction(tr(name), lambda p=points: item.put_size_(p))
                a.setCheckable(True)
                a.setChecked(item.size_ == points)
        elif isinstance(item, annotations.Frame):
            menu.addAction(tr('Change the title…'), item.change_title)
        menu.addSeparator()
        text = isinstance(item, annotations.NoteText)
        colours = menu.addMenu(tr('Paper colour') if text else tr('Colour'))
        for name, hexa in annotations.COLOURS.items():
            a = colours.addAction(self._shows(hexa), tr(name), lambda c=name: item.put_color(c))
            a.setCheckable(True)
            a.setChecked(item.color == name)
        for title, key, options in item.menu():
            if title is None:
                menu.addSeparator()
                continue
            current = item.settings[key]
            if options is None:                         # a yes or no
                if key == "bold" and current is None:
                    current = item.font().bold()
                a = menu.addAction(tr(title))
                a.setCheckable(True)
                a.setChecked(bool(current))
                a.toggled.connect(lambda yes, k=key: item.put(k, yes))
                continue
            sub = menu.addMenu(tr(title))
            for label, value, hexa in options:
                a = sub.addAction(self._shows(hexa), tr(label), lambda k=key, v=value: item.put(k, v))
                a.setCheckable(True)
                a.setChecked(current == value)
        menu.addSeparator()
        chosen = [i for i in self.graph_scene.selectedItems() if isinstance(i, annotations.Annotation)] or [item]
        delete = menu.addAction(tr('Delete'))
        delete.setShortcut("Del")
        delete.triggered.connect(lambda: self._delete_notes(chosen))

    def _put_box(self, node: Node, position) -> BoxNode:
        box = BoxNode(node)
        self.graph_scene.addItem(box)
        box.setPos(*position)
        self.boxes[node.name] = box
        self._turn_off(box, self.focused is not None and node.name != self.focused)
        return box

    # --- A node in focus (isolated, or its curve being edited): the others, in grey -----------------

    focused: str | None = None

    def focus(self, name: str | None) -> None:
        """`name` in focus: the other cards in black and white and faint, and their wires too (those that reach it or
        leave it, not). None: all as usual."""
        self.focused = name
        for n, box in self.boxes.items():
            self._turn_off(box, name is not None and n != name)
        self._turn_off_cables()

    def _turn_off(self, box, turn_off: bool) -> None:
        if turn_off and box.graphicsEffect() is None:
            grey = QGraphicsColorizeEffect()
            grey.setColor(QColor(128, 128, 128))
            grey.setStrength(1.0)                  # without colour: black and white
            box.setGraphicsEffect(grey)
        elif not turn_off and box.graphicsEffect() is not None:
            box.setGraphicsEffect(None)
        box.setOpacity(0.45 if turn_off else 1.0)

    def _turn_off_cables(self) -> None:
        for wire in self.cables:
            its = self.focused in (wire.output.box.node.name, wire.input_.box.node.name)
            wire.setOpacity(1.0 if self.focused is None or its else 0.25)

    def _redo_cables(self) -> None:
        """Draws all the wires again by the graph's connections."""
        for wire in self.cables:
            wire.output.cables.remove(wire)
            wire.input_.cables.remove(wire)
            self.graph_scene.removeItem(wire)
        self.cables.clear()
        for name, node in self.graph.nodes.items():
            for input_, origin in node.connections.items():
                if origin.name not in self.boxes or name not in self.boxes:
                    continue                             # (a node without its card: nothing to join)
                wire = Wire(self.boxes[origin.name].ports[None], self.boxes[name].ports[input_])
                self.graph_scene.addItem(wire)
                self.cables.append(wire)
        self._light_wires()
        for box in self.boxes.values():
            box.refresh()  # the fixed values seen in the box may have changed
        self._turn_off_cables()
        self.sync(self._failures)

    def positions(self) -> dict[str, list[float]]:
        return {n: [round(c.pos().x()), round(c.pos().y())] for n, c in self.boxes.items()}

    #: How much free canvas always remains around the cards (to keep putting nodes, or to zoom out).
    MARGIN_CANVAS = 20000

    def _widen_canvas(self) -> None:
        """The canvas grows with the cards: a lot of free space always remains around (it never shrinks)."""
        frame = self.graph_scene.itemsBoundingRect()
        m = self.MARGIN_CANVAS
        wants = frame.adjusted(-m, -m, m, m)
        current = self.sceneRect()
        if not current.contains(frame.adjusted(-m / 2, -m / 2, m / 2, m / 2)):
            self.setSceneRect(current.united(wants))

    def frame(self) -> None:
        frame = self.graph_scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._widen_canvas()
        self.fitInView(frame, Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.2:  # do not zoom in too much on a small graph
            self.resetTransform()
            self.centerOn(frame.center())

    def export(self, filepath, scale: float = 3.0) -> tuple[int, int]:
        """The whole graph as an image: high-resolution PNG (`scale` × the screen) or vector SVG.

        The background is the canvas's (without grid); the cards, the wires and the icons, as they are seen. Returns the
        size (in pixels or in points).
        """
        from PySide6.QtCore import QRect, QSize
        from PySide6.QtGui import QImage
        from PySide6.QtSvg import QSvgGenerator
        frame = self.graph_scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        selection = self.graph_scene.selectedItems()
        for item in selection:                       # without the «chosen» border
            item.setSelected(False)
        try:
            if str(filepath).lower().endswith(".svg"):
                width, height = int(frame.width()), int(frame.height())
                generator = QSvgGenerator()
                generator.setFileName(str(filepath))
                generator.setSize(QSize(width, height))
                generator.setViewBox(QRect(0, 0, width, height))
                generator.setTitle("Tensela")
                painter = QPainter(generator)
            else:
                width, height = int(frame.width() * scale), int(frame.height() * scale)
                image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
                painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.fillRect(QRectF(0, 0, width, height), DEPTH)
            self.graph_scene.render(painter, QRectF(0, 0, width, height), frame)
            painter.end()
            if not str(filepath).lower().endswith(".svg"):
                image.save(str(filepath))
        finally:
            for item in selection:
                item.setSelected(True)
        return width, height

    # --- Editing (each action, a method: it can be tested without a mouse) --------------

    def link(self, origin: str, target: str, input_: str) -> bool:
        """Connects the output of `origin` to the input `input_` of `target`."""
        try:
            self.graph.change(target, input_, self.graph.nodes[origin])
        except ShapeError as error:
            self.warning.emit(str(error))
            return False
        self._redo_cables()
        self.changed.emit()
        return True

    def put_group(self, where: str, name: str, position=None) -> Node | None:
        """A group of the Library panel, on the canvas (`where`: project or library; from the library it is brought
        to the project first). `position`: in the scene; none, the middle of the view."""
        from .. import library as library
        if where == "library" and name not in self.graph.kinds:
            try:
                library.bring(self.graph, name)
            except ShapeError as error:
                self.warning.emit(str(error))
                return None
        if name not in self.graph.kinds:
            self.warning.emit(tr('“{name}” is not a group of this project any more.').format(name=name))
            return None
        if position is None:
            position = self.mapToScene(self.viewport().rect().center())
        return self.add(name, (position.x(), position.y()))

    # Dragged from the Library panel: dropped on the canvas, it is put there.
    def dragEnterEvent(self, event) -> None:
        from .library_panel import MIME_GROUP
        if event.mimeData().hasFormat(MIME_GROUP):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        from .library_panel import MIME_GROUP
        if event.mimeData().hasFormat(MIME_GROUP):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        from .library_panel import MIME_GROUP
        if not event.mimeData().hasFormat(MIME_GROUP):
            super().dropEvent(event)
            return
        where, _, name = bytes(event.mimeData().data(MIME_GROUP)).decode("utf-8").partition(":")
        event.acceptProposedAction()
        self.put_group(where, name, self.mapToScene(event.position().toPoint()))

    def add(self, kind: str, position=(0.0, 0.0), name: str | None = None) -> Node:
        """Adds a new node (with its automatic name, «box 1») at `position`."""
        if name is None and kind in OLD:  # «Máximo» → a Summarise called «maximum 1»
            name = self.graph._free_name(kind.lower())
        node = self.graph.node(kind, name)
        self._in_the_plane_of_view(node)
        self._in_the_preferred_place(node)
        self.last_kind = kind                  # for «Repeat the last node» (Shift+R)
        self.new.add(node.name)             # it will be seen in 3D as soon as it gives geometry (the window decides)
        box = self._put_box(node, (position[0], position[1]))
        self.graph_scene.clearSelection()
        box.setSelected(True)
        self.changed.emit()
        return node

    last_kind: str | None = None
    #: Which plane the 3D view looks at ('plan', 'elevation' or 'side elevation'); the window gives it.
    plane_of_view = None

    def _in_the_preferred_place(self, node: Node) -> None:
        """A new Sun (or anything with a place) starts in the city of the Preferences."""
        e = next((e for e in node.kind.inputs if e.name == 'location'), None)
        if e is None or not e.options:
            return
        settings = QSettings()
        place = settings.value("preferences/location", e.default)
        if place != e.default and place in e.options:
            self.graph.change(node, 'location', place)
        from ..sun import OTHER
        if place == OTHER:                                # with its latitude, longitude and time zone
            for name in ('latitude', 'longitude', 'time_zone'):
                value = settings.value(f"preferences/{name}")
                if value is not None and any(i.name == name for i in node.kind.inputs):
                    try:
                        self.graph.change(node, name, float(value))
                    except (TypeError, ValueError):
                        pass

    def _in_the_plane_of_view(self, node: Node) -> None:
        """A new shape with a plane (Rectangle, Circle, Arc) is born in the plane the view looks at: from the front,
        standing in elevation, where it is seen."""
        if self.plane_of_view is None:
            return
        e = next((e for e in node.kind.inputs if e.name == 'plane'), None)
        if e is None or e.default != 'plan' or not e.options or 'elevation' not in e.options:
            return
        plane = self.plane_of_view()
        if plane != e.default and plane in e.options:
            self.graph.change(node, 'plane', plane)

    def last_repeat(self) -> bool:
        """Puts again the last node kind that was put, where the mouse is (Shift+R)."""
        if self.graph is None or not self.last_kind:
            return False
        point = self.mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(point):
            point = self.viewport().rect().center()
        at = self.mapToScene(point)
        self.add(self.last_kind, (at.x(), at.y()))
        return True

    def find_node(self) -> None:
        """Finds a node of the project by its name or its kind and centres it (Ctrl+F)."""
        finder = NodesFinder(self.graph, self)
        finder.chosen.connect(self.go_a)
        finder.open_in(self.mapToGlobal(self.viewport().rect().center()) - QPoint(170, 150))
        self._finder = finder

    def go_a(self, name: str) -> None:
        """Chooses the node, centres it and zooms in enough to read it."""
        if name not in self.boxes:
            return
        self.select(name)
        if self.transform().m11() < 0.8:
            self.resetTransform()
        self.centerOn(self.boxes[name])

    def choose_kind(self, point_view, then) -> None:
        """The finder, to choose a kind for something else than a new node (to change a node for another): `then`
        receives its name (one of the library is brought to the project first)."""
        if self.graph is None:
            return
        from .. import library as library
        from_library = library.kinds()
        finder = Finder(self, self.graph.kinds, from_library)

        def chosen(kind, by):
            if kind.name in from_library and kind.name not in self.graph.kinds:
                try:
                    library.bring(self.graph, kind.name)
                except ShapeError as error:
                    self.warning.emit(str(error))
                    return
            then(by if by in OLD else kind.name)

        finder.chosen.connect(chosen)
        finder.open_in(self.mapToGlobal(point_view))
        self._finder = finder

    def open_finder(self, point_view) -> None:
        """Opens the finder; the chosen node appears where the mouse was."""
        if self.graph is None:
            return
        in_graph_scene = self.mapToScene(point_view)
        from .. import library as library
        from_library = library.kinds()
        finder = Finder(self, self.graph.kinds, from_library)

        def chosen(kind, by):
            if kind.name in from_library and kind.name not in self.graph.kinds:
                try:
                    library.bring(self.graph, kind.name)       # from the library to the project
                except ShapeError as error:
                    self.warning.emit(str(error))
                    return
            self.add(by if by in OLD else kind.name, (in_graph_scene.x(), in_graph_scene.y()))

        finder.chosen.connect(chosen)
        finder.open_in(self.mapToGlobal(point_view))
        self._finder = finder  # so that garbage collection does not take it while it is open

    def unlink(self, target: str, input_: str) -> None:
        """Removes the connection of an input: it goes back to its default value."""
        node = self.graph.nodes[target]
        self.graph.change(target, input_, node.kind.input_(input_).default)
        self._redo_cables()
        self.changed.emit()

    def delete(self, names: list[str]) -> None:
        """Deletes nodes; the inputs that used them stay unconnected."""
        for other in list(self.graph.nodes.values()):
            for input_, origin in list(other.connections.items()):
                if origin.name in names:
                    self.graph.change(other, input_, other.kind.input_(input_).default)
        for name in names:
            self.graph.remove(name)
            self.graph_scene.removeItem(self.boxes.pop(name))
        self._redo_cables()
        self.changed.emit()

    # --- Data on the wires ---------------------------------------------------

    def sync(self, failures=frozenset(), waiting=None) -> None:
        """Writes on each wire the shape of what it carries («not calculated», faint, if it comes from a node of
        `waiting`: not seen, so not calculated yet); marks the nodes with an error."""
        if isinstance(failures, str):
            failures = {failures}
        self._failures = set(failures or ())
        if waiting is not None:
            self._waiting = set(waiting)
        waiting = self.__dict__.get("_waiting", set())
        for name, box in self.boxes.items():
            box.put_error(name in self._failures)
            if box.es_panel() or box.thumbnail:    # their values (or their preview) change with each computation
                box.refresh()
        for wire in self.cables:
            node = wire.output.box.node
            if node._value is not None:
                wire.put_shape(text_shape(node._value))
            elif node.name in waiting and node.name not in self._failures:
                wire.put_shape(tr('not calculated'), waiting=True)
            else:
                wire.put_shape("", error=node.name in self._failures)
        self._schedule_thumbnails()

    # --- Mouse and keyboard -----------------------------------------------------------

    #: At how many pixels a port attracts the dragged wire (the magnet).
    RADIUS_MAGNET = 28

    def _port_magnet(self, point_view) -> Port | None:
        """The closest port the dragged wire can connect to (of the other class: an output with an input, and of another
        card), if it is closer than MAGNET_RADIUS pixels."""
        start = self._pulling
        if start is None:
            return None
        centre = self.mapToScene(point_view)
        margin = self.RADIUS_MAGNET / max(self.transform().m11(), 0.1)
        best, distance = None, margin
        for item in self.graph_scene.items(QRectF(centre.x() - margin, centre.y() - margin, 2 * margin, 2 * margin)):
            if isinstance(item, Port) and item.isVisible() and item.is_output != start.is_output \
                    and item.box is not start.box:
                d = QLineF(item.centre(), centre).length()
                if d < distance:
                    best, distance = item, d
        return best

    def _put_magnet(self, port: Port | None) -> None:
        previous = getattr(self, "_magnet", None)
        if previous is not port:
            if previous is not None and previous.scene() is self.graph_scene:
                previous.highlight(False)
            if port is not None:
                port.highlight(True)
            self._magnet = port

    def _port_in(self, point_view) -> Port | None:
        """The port under the mouse, with a little margin so as not to have to hit the pixel."""
        centre = self.mapToScene(point_view)
        margin = 8 / max(self.transform().m11(), 0.1)
        for item in self.graph_scene.items(QRectF(centre.x() - margin, centre.y() - margin, 2 * margin, 2 * margin)):
            if isinstance(item, Port):
                return item
        return None

    def wheelEvent(self, event) -> None:
        if self._in_field(event):                       # over the fonts offered under a field: the list scrolls
            QGraphicsView.wheelEvent(self, event)
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        now = self.transform().m11()
        scale = now * factor
        # Within the range, or coming back to it: a big project framed whole can start below the minimum, and the
        # wheel must not stay stuck there.
        if self.ZOOM_MIN < scale < self.ZOOM_MAX or (now <= self.ZOOM_MIN and factor > 1) or \
                (now >= self.ZOOM_MAX and factor < 1):
            self.scale(factor, factor)
        if self._pulling is not None:            # dragging a wire: it stays stuck to the pointer
            self._follow_wire(event.position().toPoint())

    #: How far the canvas zooms out and in with the wheel.
    ZOOM_MIN, ZOOM_MAX = 0.15, 3.0

    #: Near the edge of the canvas (in pixels), dragging a wire, the canvas scrolls by itself.
    EDGE_AUTOSCROLL = 48

    def _follow_wire(self, point_view) -> None:
        """The dragged wire, up to the pointer (or up to the port that attracts it)."""
        magnet = self._port_magnet(point_view)
        self._put_magnet(magnet)
        self._provisional_draw(magnet.centre() if magnet is not None else self.mapToScene(point_view))

    def _autoscroll(self) -> None:
        """Dragging a wire near the edge of the canvas, the canvas scrolls to that side: faster the closer to the edge.
        So a node that is out of view can be reached."""
        if self._pulling is None:
            self._clock_edge.stop()
            return
        point = self.viewport().mapFromGlobal(QCursor.pos())
        width, height, edge = self.viewport().width(), self.viewport().height(), self.EDGE_AUTOSCROLL

        def speed(p: int, length: int) -> int:
            if p < edge:
                return -int(4 + 22 * (edge - max(p, -edge)) / edge)
            if p > length - edge:
                return int(4 + 22 * (min(p, length + edge) - (length - edge)) / edge)
            return 0

        dx, dy = speed(point.x(), width), speed(point.y(), height)
        if dx or dy:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)
            self._follow_wire(point)

    def _in_field(self, event) -> bool:
        """Whether the click falls on the open field of a card: it is its own (put the cursor, choose a word)."""
        opened = getattr(self, "_field_opened", None)
        return opened is not None and self.itemAt(event.position().toPoint()) in (
            opened[0], getattr(self, "_field_list", None))

    def mousePressEvent(self, event) -> None:
        if self._in_field(event):
            QGraphicsView.mousePressEvent(self, event)
            return
        opened = getattr(self, "_field_opened", None)
        if opened is not None:
            self.dismiss_field()                         # a click outside the field of a card: it saves and closes
        pos = event.position().toPoint()
        over_depth = self.itemAt(pos) is None
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier and over_depth
        ):
            self._panning = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.graph is not None:
            item = self.itemAt(pos)
            box = item if isinstance(item, BoxNode) else (item.parentItem() if item is not None else None)
            if isinstance(box, BoxNode) and box.shows_eye() and BoxNode.eyes and \
                    box.zone_button_eye().adjusted(-3, -3, 3, 3).contains(box.mapFromScene(self.mapToScene(pos))):
                if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                    self.isolate.emit(box.node.name)
                else:
                    self.toggle_see.emit(box.node.name, not box.sees)
                return
            if isinstance(box, BoxNode) and box.shows_button_preview() and \
                    box.zone_button_thumbnail().adjusted(-3, -3, 3, 3).contains(box.mapFromScene(self.mapToScene(pos))):
                self.toggle_thumbnail([box.node.name])
                return
            port = self._port_in(pos)
            if port is not None:
                if not port.is_output and port.cables:
                    # Grabbing a wire by its input: it is released from there and dragged from its output.
                    origin = port.cables[0].output
                    self.unlink(port.box.node.name, port.input_)
                    port = origin
                self._pulling = port
                if not hasattr(self, "_clock_edge"):
                    self._clock_edge = QTimer(self)
                    self._clock_edge.setInterval(30)
                    self._clock_edge.timeout.connect(self._autoscroll)
                self._clock_edge.start()
                self._provisional_wire = QGraphicsPathItem()
                self._provisional_wire.setPen(QPen(SELECTION, 2, Qt.PenStyle.DashLine))
                self._provisional_wire.setZValue(3)
                self.graph_scene.addItem(self._provisional_wire)
                self._provisional_draw(self.mapToScene(pos))
                return
            if isinstance(box, BoxNode) and event.modifiers() & Qt.KeyboardModifier.AltModifier:
                name = self._number_row(box, box.mapFromScene(self.mapToScene(pos)))
                if name is not None:              # Alt + drag over numbers: marked, to type one value for all
                    self._several = (box, name)
                    box.several = {name}
                    box.update()
                    return
            if isinstance(box, BoxNode):          # a click on a value: it is edited on releasing (if it was not dragged)
                where = box.mapFromScene(self.mapToScene(pos))
                if box.input_in_value(where) is not None:
                    self._click_value = (box, where, event.position())
        self._positions_before = self.positions()
        self._notes_before = self.notes()
        super().mousePressEvent(event)

    def _provisional_draw(self, to: QPointF) -> None:
        a = self._pulling.centre()
        a, b = (a, to) if self._pulling.is_output else (to, a)
        dx = max(40.0, abs(b.x() - a.x()) * 0.5)
        path = QPainterPath(a)
        path.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
        self._provisional_wire.setPath(path)

    def _number_row(self, box: "BoxNode", where: QPointF) -> str | None:
        """The input of the row under `where` if it holds a number typed on the card (not a wire, not a yes/no)."""
        row = int((where.y() - HEIGHT_HEADER) // HEIGHT_ROW)
        visible = box.visible()
        if where.y() < HEIGHT_HEADER or not 0 <= row < len(visible):
            return None
        v = box.node.inputs.get(visible[row].name)
        return visible[row].name if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def mouseMoveEvent(self, event) -> None:
        several = getattr(self, "_several", None)
        if several is not None:                   # Alt + drag: the numbers from the first to the one under the pointer
            box, first = several
            here = box.mapFromScene(self.mapToScene(event.position().toPoint()))
            row = int((here.y() - HEIGHT_HEADER) // HEIGHT_ROW)
            names = [e.name for e in box.visible()]
            row = max(0, min(row, len(names) - 1))
            a, b = sorted((names.index(first), row))
            box.several = {n for n in names[a:b + 1] if self._number_row(
                box, QPointF(0, HEIGHT_HEADER + (names.index(n) + 0.5) * HEIGHT_ROW)) is not None}
            box.update()
            return
        if self._panning is not None:
            d = event.position() - self._panning
            self._panning = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            if self._pulling is not None:        # panning with the middle one without releasing the wire
                self._follow_wire(event.position().toPoint())
            return
        if self._pulling is not None:
            # The magnet: near a port it can connect to, the wire jumps to it and the port gets bigger.
            self._follow_wire(event.position().toPoint())
            return
        if not event.buttons() and self.graph is not None:   # over a value that can be edited: a hand
            item = self.itemAt(event.position().toPoint())
            box = item if isinstance(item, BoxNode) else (item.parentItem() if item is not None else None)
            input_ = box.input_in_value(box.mapFromScene(self.mapToScene(event.position().toPoint()))) \
                if isinstance(box, BoxNode) else None
            editable = input_ is not None and not isinstance(box.node.inputs[input_.name], Node)
            if editable:
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def dismiss_field(self, save: bool = True) -> None:
        """Closes the open field on a card (saving what was written, if `save`)."""
        opened = getattr(self, "_field_opened", None)
        if opened is not None:
            opened[1](save)

    def display_guides(self, lines) -> None:
        self._lines_guide = lines
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """The smart guides while a box moves: thin lines in the accent colour."""
        lines = getattr(self, "_lines_guide", None)
        if lines:
            pencil = QPen(SELECTION, 0, Qt.PenStyle.DashLine)
            painter.setPen(pencil)
            for line in lines:
                painter.drawLine(line)

    def mouseReleaseEvent(self, event) -> None:
        several = getattr(self, "_several", None)
        if several is not None:                   # the marked numbers: the field opens on the first one
            self._several = None
            box, first = several
            names = [e.name for e in box.visible() if e.name in box.several]
            if len(names) > 1:
                row = [e.name for e in box.visible()].index(first)
                self._edit_in_card(box, QPointF(box.width * 0.8, HEIGHT_HEADER + (row + 0.5) * HEIGHT_ROW),
                                   several=names)
            else:
                box.several = set()
                box.update()
            return
        if getattr(self, "_lines_guide", None):
            self.display_guides([])
        if self._panning is not None and (self._pulling is None or event.button() != Qt.MouseButton.LeftButton):
            self._panning = None
            self.unsetCursor()
            return
        if self._pulling is not None:
            self._panning = None
            start = self._pulling
            end = self._port_magnet(event.position().toPoint()) or self._port_in(event.position().toPoint())
            self._put_magnet(None)
            self.graph_scene.removeItem(self._provisional_wire)
            self._pulling = self._provisional_wire = None
            if end is not None and end.is_output != start.is_output and end.box is not start.box:
                output, input_ = (start, end) if start.is_output else (end, start)
                self.link(output.box.node.name, input_.box.node.name, input_.input_)
            return
        super().mouseReleaseEvent(event)
        before, self._positions_before = getattr(self, "_positions_before", None), None
        moved = self.graph is not None and before is not None and self.positions() != before
        if moved:
            self.moved.emit()
        notes_before, self._notes_before = getattr(self, "_notes_before", None), None
        if notes_before is not None and self.notes() != notes_before:     # an annotation moved
            self.notes_changed.emit()
        click, self._click_value = getattr(self, "_click_value", None), None
        if click is not None and not moved and event.button() == Qt.MouseButton.LeftButton \
                and (event.position() - click[2]).manhattanLength() < 5 and click[0].scene() is self.graph_scene:
            from PySide6.QtWidgets import QApplication
            input_ = click[0].input_in_value(click[1])
            key, now = (click[0].node.name, input_.name), time.monotonic()
            last = getattr(self, "_last_value", (None, 0.0))
            # The second click of a double click on the same value does not change it again (a yes/no would stay the same).
            if last[0] != key or now - last[1] > QApplication.doubleClickInterval() / 1000:
                self._last_value = (key, now)
                self._edit_in_card(click[0], click[1], a_click=True)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._in_field(event):
            QGraphicsView.mouseDoubleClickEvent(self, event)
            return
        if event.button() != Qt.MouseButton.LeftButton:  # a double right click is two menus, not an entry
            event.accept()
            return
        point = event.position().toPoint()
        item = self.itemAt(point)
        if item is None:
            self.open_finder(point)
            return
        box = item if isinstance(item, BoxNode) else item.parentItem()
        if isinstance(box, BoxNode) and box.input_in_value(box.mapFromScene(self.mapToScene(point))) is not None:
            return                                       # the first click already opened it (or changed it)
        if isinstance(box, BoxNode) and self._edit_in_card(box, box.mapFromScene(self.mapToScene(point))):
            return
        if isinstance(box, BoxNode) and box.node.kind.name in self.graph.definitions:
            self.enter.emit(box.node.name)          # double-click on a group (outside its values): enter
            return
        if isinstance(box, BoxNode) and editable(box.node):
            self.edit.emit(box.node.name)           # on a node with an editor of its own (outside its values): it opens
            return
        super().mouseDoubleClickEvent(event)

    def _options(self, box: "CajaNodo", input_) -> list[str]:
        """The options of an input: the fixed ones, or the levels of the input they depend on («along»)."""
        if input_.options:
            from ..nodes import options_of
            return options_of(box.node, input_)
        if input_.levels_of:
            origin = box.node.inputs.get(input_.levels_of)
            value = getattr(origin, "_value", None) if isinstance(origin, Node) else origin
            return list(getattr(value, "levels", ()) or ())
        return []

    def _edit_in_card(self, box: "CajaNodo", where: QPointF, a_click: bool = False,
                      several: list[str] | None = None) -> bool:
        """A click on a value of the card: it is written right there; a yes/no toggles; some options drop down. False if it
        was not a value."""
        row = int((where.y() - HEIGHT_HEADER) // HEIGHT_ROW)
        visible = box.visible()
        if where.y() < HEIGHT_HEADER or not 0 <= row < len(visible):
            return False
        input_ = visible[row]
        current = box.node.inputs[input_.name]
        if box.node.kind.name == 'Code' and input_.name == "code" and not isinstance(current, Node):
            if not a_click:                              # the code is not written on the card: its editor opens
                self.code.emit(box.node.name)
            return not a_click
        if isinstance(current, Node):
            if a_click:                                  # a click on a connected value: it only chooses the card
                return False
            self.warning.emit(tr('“{input}” comes from another node: disconnect the wire to type it.').format(
                input=label_input(input_.name)))
            return True
        if isinstance(input_.default, bool) or isinstance(current, bool):
            self.value_changed.emit(box.node.name, input_.name, "no" if current else "yes")
            return True
        if input_.file:                                  # a file: the browser opens, as from the panel
            chosen = choose_file(self, input_.file, box.node.graph.folder, current)
            if chosen is not None:
                self.value_changed.emit(box.node.name, input_.name, chosen)
            return True
        options = self._options(box, input_)
        if options:                                     # a drop-down list with the options, right there
            self.dismiss_field()
            menu = QMenu(self)
            for option in options:
                action = menu.addAction(tr(option))
                action.setCheckable(True)
                action.setChecked(option == current)
                action.triggered.connect(lambda _=False, o=option: o != current and self.value_changed.emit(
                    box.node.name, input_.name, o))
            corner = box.mapToScene(QPointF(box.width * 0.45, HEIGHT_HEADER + (row + 1) * HEIGHT_ROW))
            menu.exec(self.viewport().mapToGlobal(self.mapFromScene(corner)))
            return True
        length = is_length(box.node, input_.name)
        field = QLineEdit(text_of(input_.name, current, length) if current is not None else "")
        from ..project_file import LEVEL_INPUTS
        if input_.name in LEVEL_INPUTS:                 # the name of a level: a name, not a text
            from .widgets import NAME_LIMIT
            field.setMaxLength(max(NAME_LIMIT, len(field.text())))
        field.setObjectName("card_field")
        field.setPlaceholderText(tr(input_.help) or tr('empty'))
        if input_.options:
            complete = QCompleter(list(input_.options), field)
            complete.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            field.setCompleter(complete)
        names = None
        if input_.suggest is not None and not input_.options:  # names offered (the installed fonts): typed, or chosen
            try:
                names = suggestions(box.node, input_)
            except Exception:                           # noqa: BLE001 (without the list, it is written by hand)
                names = []
            field.addAction(icons.icon("chevron_down", SMOOTH_TEXT.name(), 12),
                            QLineEdit.ActionPosition.TrailingPosition).setToolTip(tr('Pick from the list or type.'))
        self.dismiss_field()                              # a single open field at a time
        # Inside the card: if the card moves (the double click drags it a little), the field goes with it.
        intermediary = QGraphicsProxyWidget(box)
        intermediary.setWidget(field)
        intermediary.setZValue(10)
        width = box.width * 0.55
        field.setFixedSize(int(width), HEIGHT_ROW)
        intermediary.setPos(box.width - MARGIN - width, HEIGHT_HEADER + row * HEIGHT_ROW)
        done = [False]
        offered = None
        if names:                                       # the list opens with the field, inside the canvas, below it
            offered = _Offered(box, field, names, QPointF(box.width - MARGIN - max(width, 220),
                                                           HEIGHT_HEADER + (row + 1) * HEIGHT_ROW + 2),
                               max(width, 220), lambda: QTimer.singleShot(0, lambda: finish(True)))
            self.graph_scene.setStickyFocus(True)      # a click on the list leaves the field open, to take the name
        self._field_list = offered.proxy if offered is not None else None

        def finish(save: bool) -> None:
            if done[0]:
                return
            done[0] = True
            self._field_opened = None
            self._field_list = None
            if offered is not None:
                offered.close()
                if shiboken6.isValid(self.graph_scene):
                    self.graph_scene.setStickyFocus(False)
            if not shiboken6.isValid(field) or not shiboken6.isValid(intermediary):
                return                                   # its card was deleted meanwhile (the node, or a rebuild)
            text = field.text()
            on_scene = intermediary.scene() is self.graph_scene
            intermediary.setParentItem(None)
            if on_scene or intermediary.scene() is self.graph_scene:
                self.graph_scene.removeItem(intermediary)
            intermediary.deleteLater()
            if self.boxes.get(box.node.name) is not box:
                return                                   # its card is gone: there is no node to save it in
            if several:                                  # the marked numbers: the same value for all of them
                box.several = set()
                box.update()
                if save and field.isModified():
                    self.values_changed.emit(box.node.name, several, text)
                return
            if save and text != text_of(input_.name, current, length):
                self.value_changed.emit(box.node.name, input_.name, text)

        field.returnPressed.connect(lambda: finish(True))
        field.editingFinished.connect(lambda: finish(True))
        field.installEventFilter(_Escape(field, lambda: finish(False)))
        self._field_opened = (intermediary, finish, box.node.name, input_.name)
        intermediary.setFocus()
        field.setFocus()
        field.selectAll()
        return True

    #: The key that opens the node finder (Preferences → Interaction can change it).
    key_finder = QKeySequence("Tab")

    def event(self, event) -> bool:
        # Writing on a card, the window's shortcuts (Del, Ctrl+Z, Ctrl+A, Ctrl+V…) do not fire:
        # those keys belong to the field, as in any text box.
        if event.type() == QEvent.Type.ShortcutOverride and getattr(self, "_field_opened", None) is not None:
            event.accept()
            return True
        if event.type() == QEvent.Type.KeyPress:
            # With a field open on a card, Tab goes to the next value (Shift+Tab, to the previous one),
            # as in a form.
            if getattr(self, "_field_opened", None) is not None and event.key() in (Qt.Key.Key_Tab,
                                                                                    Qt.Key.Key_Backtab):
                self.skip_field(event.key() == Qt.Key.Key_Tab
                                  and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                return True
            # The finder's key (Tab by default; Qt would use it to pass the focus to another control).
            if getattr(self, "_field_opened", None) is None and not self.key_finder.isEmpty() and \
                    QKeySequence(event.keyCombination()).matches(self.key_finder) == \
                    QKeySequence.SequenceMatch.ExactMatch:
                self.open_finder(self.mapFromGlobal(QCursor.pos()))
                return True
        return super().event(event)

    def _writable(self, box: "CajaNodo") -> list[str]:
        """The inputs of a card that are written in a field (neither wire, nor yes/no, nor options)."""
        return [e.name for e in box.visible()
                if not isinstance(box.node.inputs[e.name], Node)
                and not (isinstance(e.default, bool) or isinstance(box.node.inputs[e.name], bool))
                and not self._options(box, e)]

    def skip_field(self, ahead: bool = True) -> None:
        """Saves the open field and opens that of the next (or previous) value of the same card."""
        opened = getattr(self, "_field_opened", None)
        if opened is None:
            return
        node, input_ = opened[2], opened[3]
        box = self.boxes.get(node)
        list_ = self._writable(box) if box is not None else []
        if input_ not in list_ or len(list_) < 2:
            self.dismiss_field()
            return
        next_ = list_[(list_.index(input_) + (1 if ahead else -1)) % len(list_)]
        self.dismiss_field()                       # it saves (it may redo the cards): the other one is opened afterwards
        QTimer.singleShot(0, lambda: self.open_field(node, next_))

    def open_field(self, node: str, input_: str) -> None:
        """Opens the field of a value of a card, like a click on it."""
        box = self.boxes.get(node)
        if box is None:
            return
        names = [e.name for e in box.visible()]
        if input_ in names:
            row = names.index(input_)
            self._edit_in_card(box, QPointF(box.width * 0.8, HEIGHT_HEADER + (row + 0.5) * HEIGHT_ROW))

    def _writing_note(self) -> bool:
        focus = self.graph_scene.focusItem()
        return isinstance(focus, annotations.NoteText) and focus.editing()

    def keyPressEvent(self, event) -> None:
        if getattr(self, "_field_opened", None) is not None or self._writing_note():
            super().keyPressEvent(event)               # writing on a card or on a note: it is its own
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.graph is not None:
            notes = [i for i in self.graph_scene.selectedItems() if isinstance(i, annotations.Annotation)]
            self._delete_notes(notes)
            names = [i.node.name for i in self.graph_scene.selectedItems() if isinstance(i, BoxNode)]
            if names:
                self.delete(names)
                return
            if notes:
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if isinstance(item, QGraphicsSimpleTextItem):
            item = item.parentItem()
        if isinstance(item, Wire):
            menu = QMenu(self)
            action = menu.addAction(tr('Disconnect “{input}” from “{node}”').format(
                input=label_input(item.input_.input_), node=item.input_.box.node.name))
            if menu.exec(event.globalPos()) is action:
                self.unlink(item.input_.box.node.name, item.input_.input_)
            return
        if self.graph is None:
            return
        if isinstance(item, annotations.Annotation):
            if not item.isSelected():
                self.graph_scene.clearSelection()
                item.setSelected(True)
            menu = QMenu(self)
            self._menu_note(menu, item)
            menu.exec(event.globalPos())
            return
        box = item if isinstance(item, BoxNode) else (item.parentItem() if item is not None else None)
        if isinstance(box, BoxNode) and box.node.name not in self.graph.nodes:
            # A card whose node is no longer in the project (it should never happen; a failed ungroup left one): it
            # goes, instead of a menu that fails on every click.
            self.graph_scene.removeItem(self.boxes.pop(box.node.name, box))
            self._redo_cables()
            return
        menu = QMenu(self)
        if isinstance(box, BoxNode):
            if not box.isSelected():
                self.graph_scene.clearSelection()
                box.setSelected(True)
            name = box.node.name
            if self.on_ask_menu:
                self.on_ask_menu(menu, name)
            menu.addSeparator()
            chosen = [c.node.name for c in self.chosen()]
            for text, shortcut, function in ((tr('Copy'), "Ctrl+C", self.copy), (tr('Cut'), "Ctrl+X", self.cut),
                                          (tr('Duplicate'), "Ctrl+D", self.duplicate)):
                menu.addAction(text, function).setShortcut(shortcut)
            if len(chosen) > 1:
                self._menu_organise(menu.addMenu(tr('Align and distribute')), len(chosen))
            if box.shows_button_preview():
                preview = menu.addAction(tr('Show its values on the card') if box.gives_values()
                                        else tr('Preview in the card'))
                preview.setCheckable(True)
                preview.setChecked(box.thumbnail)
                preview.toggled.connect(lambda yes: self.toggle_thumbnail(chosen, yes))
            menu.addSeparator()
            delete = menu.addAction(tr('Delete') + (f" ({len(chosen)})" if len(chosen) > 1 else ""))
            delete.setShortcut("Del")
            delete.triggered.connect(lambda: self.delete(chosen))
        else:
            point = event.pos()
            menu.addAction(tr('Add a node here…')).triggered.connect(lambda: self.open_finder(point))
            from PySide6.QtWidgets import QApplication
            data_items = QApplication.clipboard().mimeData()
            paste = menu.addAction(tr('Paste here'), lambda: self.paste(self.mapToScene(point)))
            paste.setShortcut("Ctrl+V")
            paste.setEnabled(data_items is not None and data_items.hasFormat(self.KIND_CLIPBOARD))
            menu.addAction(tr('Select all'), self.select_all).setShortcut("Ctrl+A")
            annotate = menu.addMenu(tr('Annotate here'))
            where = self.mapToScene(point)
            for kind, text in (("text", 'A text'), ("arrow", 'An arrow'), ("frame", 'A frame with a title')):
                annotate.addAction(tr(text), lambda t=kind: self.annotate(t, where))
            menu.addSeparator()
            if self.on_ask_menu:
                self.on_ask_menu(menu, None)
        menu.exec(event.globalPos())

    #: Align and distribute: (text, how, shortcut). The window puts the same in View → Arrange.
    ALIGN = (('Align left', "left", "Ctrl+Shift+L"), ('Center horizontally', "centre", ""),
               ('Align right', "right", "Ctrl+Shift+R"), (None, None, None),
               ('Align top', "up", "Ctrl+Shift+T"), ('Center vertically', "mid", ""),
               ('Align bottom', "down", ""))
    DISTRIBUTE = (('Distribute horizontally', "horizontal", "Ctrl+Shift+H"),
                  ('Distribute vertically', "vertical", "Ctrl+Shift+V"))

    def _menu_organise(self, menu: QMenu, how_many: int) -> None:
        for text, as_, shortcut in self.ALIGN:
            if text is None:
                menu.addSeparator()
                continue
            a = menu.addAction(tr(text), lambda c=as_: self.align(c))
            if shortcut:
                a.setShortcut(shortcut)
        menu.addSeparator()
        for text, direction, shortcut in self.DISTRIBUTE:
            a = menu.addAction(tr(text), lambda s=direction: self.distribute(s))
            a.setShortcut(shortcut)
            a.setEnabled(how_many >= 3)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """The canvas background: dots, squares or plain (Preferences)."""
        super().drawBackground(painter, rect)
        if DEPTH_CANVAS == "plain":
            return
        step = STEP_GRID
        x0, y0 = int(rect.left()) - int(rect.left()) % step, int(rect.top()) - int(rect.top()) % step
        if DEPTH_CANVAS == "squares":
            line = QPen(_with_alpha(WIRE, 45), 0)     # thin stroke (cosmetic), in the tone of the wires
            painter.setPen(line)
            xs, ys = range(x0, int(rect.right()) + 1, step), range(y0, int(rect.bottom()) + 1, step)
            if len(xs) + len(ys) < 4000:
                for x in xs:
                    painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                for y in ys:
                    painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            return
        painter.setPen(QPen(GRID, 1.5))
        points = [QPointF(x, y) for x in range(x0, int(rect.right()), step) for y in range(y0, int(rect.bottom()), step)]
        if len(points) < 20000:
            painter.drawPoints(points)


def arrange(graph: Graph) -> dict[str, tuple[float, float]]:
    """Automatic positions: each node to the right of those it uses (by layers)."""
    layers: dict[str, int] = {}

    def layer(node: Node) -> int:
        if node.name not in layers:
            layers[node.name] = 0  # it protects from cycles (there should be none)
            layers[node.name] = 1 + max((layer(o) for o in node.connections.values()), default=-1)
        return layers[node.name]

    for node in graph.nodes.values():
        layer(node)

    widths: dict[int, float] = {}
    for name, node in graph.nodes.items():
        widths[layers[name]] = max(widths.get(layers[name], 0), BoxNode(node).width)
    xs, x = {}, 0.0
    for c in sorted(widths):
        xs[c] = x
        x += widths[c] + SPACING_X

    # Layer by layer: each node, as close as possible to the average height of the
    # nodes it uses (fewer crossed wires than the plain order of the file).
    positions: dict[str, tuple[float, float]] = {}
    for c in sorted(widths):
        in_layer = [n for n in graph.nodes.values() if layers[n.name] == c]

        def desired(node: Node) -> float:
            ys = [positions[o.name][1] for o in node.connections.values() if o.name in positions]
            return sum(ys) / len(ys) if ys else float(list(graph.nodes).index(node.name)) * 1e-6

        free_y = 0.0
        for node in sorted(in_layer, key=desired):
            y = max(free_y, desired(node) if node.connections else free_y)
            y = round(y / STEP_GRID) * STEP_GRID
            positions[node.name] = (round(xs[c] / STEP_GRID) * STEP_GRID, y)
            free_y = y + HEIGHT_HEADER + sum(visible_input(node, e) for e in node.kind.inputs) * HEIGHT_ROW \
                + 6 + SPACING_Y
    return positions
