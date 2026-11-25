"""The annotations of the node canvas: texts, arrows and frames (Victor's notes, package 2).

They are outside the computation: they serve to explain the process to whoever opens the file («here the plan is
made», an arrow to the slider that matters, a frame with a title around the nodes of the facade). They are saved in
the file, in «notes», as dictionaries (the settings that are not the factory ones go there too):

    {"type": "text", "x": 0, "y": 0, "width": 220, "text": "…", "color": "yellow", "size": 11,
     "background": false, "border": false, "typeface": "serif"}
    {"type": "arrow", "x": 0, "y": 0, "x2": 120, "y2": 40, "color": "red", "start": "dot", "end": "swiss"}
    {"type": "frame", "x": 0, "y": 0, "width": 400, "height": 250, "text": "Facade", "color": "blue",
     "line": "dashed", "title": "text"}

The notes saved before the move to English (Spanish keys and values) are read with `in_english`.
"""
from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTextCursor
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyle

from ..language import tr

#: The colours of the annotations (tones readable on the light canvas and on the dark one).
COLOURS = {"yellow": "#e8c547", "orange": "#e8873a", "red": "#d9534f", "green": "#5fae6a",
           "blue": "#4a7fd4", "violet": "#8a7dff", "grey": "#9aa0a8", "black": "#1d2027", "white": "#f4f5f7"}

#: Font sizes of a text (and of the title of a frame).
SIZES = {"small": 9, "medium": 11, "large": 16, "title": 24}

#: The typefaces: the three families every system has (fontconfig picks the best installed).
LETTERS = {"sans serif": "sans-serif", "serif": "serif", "monospace": "monospace"}

#: The stroke of an arrow or of the border of a frame.
LINES = {"solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine,
          "dotted": Qt.PenStyle.DotLine}

#: What an arrow carries at each end. The «swiss» one: that of Swiss design signage (two thick
#: strokes at 45°, cut square, that meet at a sharp angle).
TIPS = ("none", "classic", "open", "swiss", "dot")

#: The weight of an arrow.
WEIGHTS = {"thin": 1.5, "medium": 2.5, "thick": 5.0}

#: What tells the canvas that an annotation changed (to save it and be able to undo it). The Editor sets it.
ON_CHANGE: dict[str, Callable[[], None] | None] = {"function": None}


def _warn() -> None:
    if ON_CHANGE["function"] is not None:
        ON_CHANGE["function"]()


def _selection() -> QColor:
    from . import editor  # the «chosen» colour of the theme set
    return editor.SELECTION


def _text_canvas() -> QColor:
    from . import editor  # the text of the theme set: it reads on the canvas, without paper
    return editor.TEXT


def _color(name: str) -> QColor:
    return QColor(COLOURS.get(name, COLOURS["yellow"]))


def _source(base: QFont, font: str, points: int, bold: bool, italic: bool = False) -> QFont:
    f = QFont(base)
    f.setFamilies([LETTERS.get(font, "sans-serif")])
    f.setPointSize(points)
    f.setBold(bold)
    f.setItalic(italic)
    return f


class Annotation:
    """The common part: moving, being chosen, its colour, its settings and its dictionary.

    `SETTINGS` are the factory settings of each class; the file keeps only those that were changed."""

    kind = ""
    color = "yellow"
    SETTINGS: dict = {}

    def _prepare(self) -> None:
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.settings = dict(self.SETTINGS)

    def read_settings(self, d: dict) -> None:
        for key, default in self.SETTINGS.items():
            value = d.get(key, default)
            if type(value) is type(default) or default is None:
                self.settings[key] = value
        self._on_adjust()

    def a_dict(self) -> dict:
        d = {"type": self.kind, "x": round(self.pos().x()), "y": round(self.pos().y()), "color": self.color}
        d.update({k: v for k, v in self.settings.items() if v != self.SETTINGS[k]})
        return d

    def put_color(self, color: str) -> None:
        self.color = color
        self.update()
        _warn()

    def put(self, key: str, value) -> None:
        """Changes a setting (from the menu) and draws itself again."""
        self.prepareGeometryChange()
        self.settings[key] = value
        self._on_adjust()
        self.update()
        _warn()

    def _on_adjust(self) -> None:
        """What changes inside on changing a setting (the typeface of a text, for example)."""

    def menu(self) -> list:
        """The settings for the canvas menu: (title, key, [(label, value, colour or None)…]); for a yes/no, (title, key,
        None); (None, None, None) is a separating line."""
        return []


def _options_color(with_none: bool = False, same_with: bool = False) -> list:
    options = []
    if same_with:
        options.append(("same as the note", "same", None))
    if with_none:
        options.append(("no colour", "none", None))
    return options + [(n, n, h) for n, h in COLOURS.items()]


class NoteText(QGraphicsTextItem, Annotation):
    """A loose text: on a slip of paper (background and border of the chosen colour) or just the text. Double-click
    to write; click outside, done."""

    kind = "text"
    SETTINGS = {"background": True, "border": True, "typeface": "sans serif", "bold": None, "italic": False,
               "text_colour": "auto"}

    def __init__(self, text: str = "", width: float = 220, color: str = "yellow", size_: int = 11):
        super().__init__(text)
        self._prepare()
        self.color, self.size_ = color, size_
        self.setTextWidth(width)
        self.setZValue(5)
        self._on_adjust()

    def _on_adjust(self) -> None:
        bold = self.settings["bold"]
        if bold is None:                       # factory: the big sizes, in bold
            bold = self.size_ >= SIZES["large"]
        self.setFont(_source(self.font(), self.settings["typeface"], self.size_, bold, self.settings["italic"]))
        self.setDefaultTextColor(self.color_text())

    def color_text(self) -> QColor:
        chosen = self.settings["text_colour"]
        if chosen != "auto":
            return _color(chosen)
        return QColor("#1d2027") if self.settings["background"] else _text_canvas()

    def put_size_(self, size_: int) -> None:
        self.size_ = size_
        self._on_adjust()
        _warn()

    def only_text(self, yes: bool) -> None:
        """The style of a click: just the text (without background or border) or the slip of paper."""
        self.settings["background"] = self.settings["border"] = not yes
        self._on_adjust()
        self.update()
        _warn()

    def a_dict(self) -> dict:
        return {**super().a_dict(), "width": round(self.textWidth()), "text": self.toPlainText(),
                "size": self.size_}

    def menu(self) -> list:
        return [
            ('Typeface', "typeface", [(n, n, None) for n in LETTERS]),
            ('Bold', "bold", None),
            ('Italic', "italic", None),
            (None, None, None),
            ('Text colour', "text_colour", [("automatic", "auto", None)] + _options_color()),
            ('Background', "background", None),
            ('Border', "border", None),
        ]

    def editing(self) -> bool:
        return bool(self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction)

    def write(self) -> None:
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def mouseDoubleClickEvent(self, event) -> None:
        if not self.editing():
            self.write()
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if self.editing():
            self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            cursor = self.textCursor()
            cursor.clearSelection()
            self.setTextCursor(cursor)
            _warn()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        super().keyPressEvent(event)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDefaultTextColor(self.color_text())     # «automatic» follows the canvas theme
        rect = self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isSelected():
            painter.setPen(QPen(_selection(), 2))
        elif self.settings["border"]:
            painter.setPen(QPen(_color(self.color), 1))
        elif self.editing() or not self.toPlainText():      # without a border: when writing, it shows where
            guide = QColor(_text_canvas())
            guide.setAlpha(90)
            painter.setPen(QPen(guide, 1, Qt.PenStyle.DashLine))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        if self.settings["background"]:
            paper = _color(self.color).lighter(150)
            paper.setAlpha(235)
            painter.setBrush(paper)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 5, 5)
        if not self.toPlainText() and not self.editing():
            grey = QColor("#6b6f76") if self.settings["background"] else QColor(_text_canvas())
            grey.setAlpha(255 if self.settings["background"] else 150)
            painter.setPen(grey)
            painter.drawText(self.boundingRect().adjusted(6, 4, -6, -4), Qt.AlignmentFlag.AlignLeft,
                             tr('Double-click to write'))
        option.state &= ~QStyle.StateFlag.State_Selected      # without Qt's dotted box: the border is already there
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, widget)


class Arrow(QGraphicsItem, Annotation):
    """An arrow from one point to another, to point at a card. It is dragged whole, or by either of its ends (the
    points that appear on choosing it). Each end carries its tip (or a dot, or nothing)."""

    kind = "arrow"
    TAKES = 9
    SETTINGS = {"start": "none", "end": "classic", "weight": "medium", "line": "solid"}

    def __init__(self, to: QPointF = QPointF(140, 0), color: str = "red"):
        super().__init__()
        self._prepare()
        self.color = color
        self.to = QPointF(to)          # relative to its position (the start)
        self._end = None                 # which end is dragged: 0 the start, 1 the tip
        self.setZValue(6)

    def a_dict(self) -> dict:
        d = super().a_dict()
        return {**d, "x2": d["x"] + round(self.to.x()), "y2": d["y"] + round(self.to.y())}

    def menu(self) -> list:
        tips = [({"dot": "a dot", "none": "nothing"}.get(p, p), p, None) for p in TIPS]
        return [
            ('At the end', "end", tips),
            ('At the start', "start", tips),
            (None, None, None),
            ('Line weight', "weight", [(n, n, None) for n in WEIGHTS]),
            ('Line', "line", [(n, n, None) for n in LINES]),
        ]

    def _width(self) -> float:
        return WEIGHTS.get(self.settings["weight"], 2.5)

    def _length_tip(self) -> float:
        return 7 + 3 * self._width()

    def boundingRect(self) -> QRectF:
        m = 14 + self._length_tip()
        return QRectF(QPointF(0, 0), self.to).normalized().adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        line = QLineF(QPointF(0, 0), self.to)
        n = line.normalVector()
        if n.length() > 0:
            n.setLength(8 + self._width())
        d = QPointF(n.dx(), n.dy())
        path.addPolygon(QPolygonF([d, self.to + d, self.to - d, -d]))
        for p in (QPointF(0, 0), self.to):
            path.addEllipse(p, self.TAKES, self.TAKES)
        return path

    def _offcut(self, style_name: str) -> float:
        """How much the line is shortened before the tip (so it does not show in front)."""
        if style_name == "classic":
            return self._length_tip() * 0.8
        if style_name == "swiss":
            return self._width() * 0.75
        return 0.0

    def _tip(self, painter: QPainter, tip: QPointF, direction: QPointF, style_name: str, color: QColor) -> None:
        """Draws an end: `direction` is a unit vector and points out of the arrow."""
        w, length = self._width(), self._length_tip()
        normal = QPointF(-direction.y(), direction.x())
        if style_name == "classic":
            base = tip - direction * length
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([tip, base + normal * length * 0.45, base - normal * length * 0.45]))
        elif style_name in ("open", "swiss"):
            swiss = style_name == "swiss"
            wing = length * (0.8 if swiss else 1.0)
            opens = 1.0 if swiss else 0.5                       # the swiss one, at 45°; the open one, more closed
            pen = QPen(color, w, Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.FlatCap if swiss else Qt.PenCapStyle.RoundCap,
                         Qt.PenJoinStyle.MiterJoin if swiss else Qt.PenJoinStyle.RoundJoin)
            pen.setMiterLimit(4)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            back = tip - direction * wing
            path = QPainterPath(back + normal * wing * opens)
            path.lineTo(tip)
            path.lineTo(back - normal * wing * opens)
            painter.drawPath(path)
        elif style_name == "dot":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(tip, max(3.5, w * 1.6), max(3.5, w * 1.6))

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = _color(self.color)
        line = QLineF(QPointF(0, 0), self.to)
        length = line.length()
        if length < 1:
            return
        u = QPointF(line.dx() / length, line.dy() / length)          # from the start to the tip
        start, end = self.settings["start"], self.settings["end"]
        from_ = QPointF(0, 0) + u * min(self._offcut(start), length / 2)
        to = self.to - u * min(self._offcut(end), length / 2)
        style_name = LINES.get(self.settings["line"], Qt.PenStyle.SolidLine)
        straight = "swiss" in (start, end) and style_name == Qt.PenStyle.SolidLine
        painter.setPen(QPen(color, self._width(), style_name,
                            Qt.PenCapStyle.FlatCap if straight else Qt.PenCapStyle.RoundCap))
        painter.drawLine(QLineF(from_, to))
        self._tip(painter, self.to, u, end, color)
        self._tip(painter, QPointF(0, 0), -u, start, color)
        if self.isSelected():
            painter.setPen(QPen(_selection(), 1.5))
            painter.setBrush(QBrush(_selection().lighter(130)))
            for p in (QPointF(0, 0), self.to):
                painter.drawEllipse(p, 4.5, 4.5)

    def mousePressEvent(self, event) -> None:
        p = event.pos()
        self._end = None
        if self.isSelected():
            if QLineF(p, self.to).length() <= self.TAKES:
                self._end = 1
            elif QLineF(p, QPointF(0, 0)).length() <= self.TAKES:
                self._end = 0
        if self._end is None:
            super().mousePressEvent(event)
        else:
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._end is None:
            super().mouseMoveEvent(event)
            return
        self.prepareGeometryChange()
        if self._end == 1:
            self.to = event.pos()
        else:                               # moving the start: the tip stays where it was
            tip = self.mapToScene(self.to)
            self.setPos(event.scenePos())
            self.to = self.mapFromScene(tip)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._end is not None:
            self._end = None
            _warn()
            return
        super().mouseReleaseEvent(event)


class Frame(QGraphicsItem, Annotation):
    """A frame with a title behind some cards, to group them visually (it is not a group of nodes: it does not
    change the computation). It is enlarged from the right edge, the bottom one or the corner; double-click on the title,
    another one. Background and border, each of its colour (or none); the border, solid, dashed or dotted; the title, in
    a band, just the text, or no title."""

    kind = "frame"
    CORNER = 16
    EDGE = 8
    HEIGHT_TITLE = 26
    SETTINGS = {"background": "same", "border": "same", "line": "solid", "title": "band",
               "typeface": "sans serif", "title_size": 11}

    def __init__(self, width: float = 420, height: float = 260, text: str = "", color: str = "blue"):
        super().__init__()
        self._prepare()
        self.color, self.text = color, text
        self.width, self.height = width, height
        self._enlarging = None             # what is dragged to enlarge: "right", "bottom" or "corner"
        self.setZValue(-10)                 # behind the cards and the wires

    def a_dict(self) -> dict:
        return {**super().a_dict(), "width": round(self.width), "height": round(self.height), "text": self.text}

    def menu(self) -> list:
        return [
            ('Background', "background", _options_color(with_none=True, same_with=True)),
            ('Border', "border", _options_color(with_none=True, same_with=True)),
            ('Border line', "line", [(n, n, None) for n in LINES]),
            (None, None, None),
            ('Title', "title", [("in a band", "band", None), ("just the text", "text", None),
                                  ("hide it", "hidden", None)]),
            ('Title typeface', "typeface", [(n, n, None) for n in LETTERS]),
            ('Title size', "title_size", [(n, p, None) for n, p in SIZES.items()]),
        ]

    def _height_title(self) -> float:
        return max(self.HEIGHT_TITLE, self.settings["title_size"] * 1.9 + 6)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height).adjusted(-3, -3, 3, 3)

    def shape(self) -> QPainterPath:
        # Only the title band and the border are grabbed with the mouse: inside, the cards are chosen (or
        # a selection box is dragged), as on a canvas without a frame.
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.width, self._height_title()))
        b = self.EDGE
        for r in (QRectF(0, 0, b, self.height), QRectF(self.width - b, 0, b, self.height),
                  QRectF(0, self.height - b, self.width, b),
                  QRectF(self.width - self.CORNER, self.height - self.CORNER, self.CORNER, self.CORNER)):
            path.addRect(r)
        return path

    def _tone(self, chosen: str) -> QColor | None:
        if chosen == "none":
            return None
        return _color(self.color) if chosen == "same" else _color(chosen)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = _color(self.color)
        rect = QRectF(0, 0, self.width, self.height)
        background, edge = self._tone(self.settings["background"]), self._tone(self.settings["border"])
        if background is not None:
            background.setAlpha(28 if self.settings["background"] == "same" else 60)
        painter.setBrush(background if background is not None else Qt.BrushStyle.NoBrush)
        style_name = LINES.get(self.settings["line"], Qt.PenStyle.SolidLine)
        if self.isSelected():
            painter.setPen(QPen(_selection(), 2, style_name))
        elif edge is not None:
            painter.setPen(QPen(edge, 1.5, style_name))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 8, 8)
        if edge is None and background is None and not self.isSelected():   # with nothing: a faint guide, to find it
            guide = QColor(color)
            guide.setAlpha(70)
            painter.setPen(QPen(guide, 1, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 8, 8)
        self._paint_title(painter, color, rect)
        grip = QColor(edge if edge is not None else color)        # the corner to enlarge
        painter.setPen(QPen(grip, 1.5))
        x, y = self.width - 4, self.height - 4
        for d in (5, 9, 13):
            painter.drawLine(QPointF(x - d, y), QPointF(x, y - d))

    def _paint_title(self, painter: QPainter, color: QColor, rect: QRectF) -> None:
        as_ = self.settings["title"]
        if as_ == "hidden":
            return
        height = self._height_title()
        if as_ == "band":
            edge = QPainterPath()
            edge.addRoundedRect(rect, 8, 8)
            strip = QColor(color)
            strip.setAlpha(200)
            painter.save()
            painter.setClipPath(edge)             # the title band, with the corners of the frame
            painter.fillRect(QRectF(0, 0, self.width, height), strip)
            painter.restore()
        painter.setFont(_source(painter.font(), self.settings["typeface"], self.settings["title_size"], True))
        if self.text:
            painter.setPen(QColor("#ffffff") if as_ == "band" else color)
        else:
            grey = QColor("#ffffff" if as_ == "band" else color)
            grey.setAlpha(170)
            painter.setPen(grey)
        painter.drawText(QRectF(12, 0, self.width - 24, height),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.text or tr('Double-click to add a title'))

    def _zone(self, p: QPointF) -> str | None:
        """Where it is enlarged from: the corner, the right edge or the bottom one."""
        right, below = p.x() > self.width - self.EDGE, p.y() > self.height - self.EDGE
        if p.x() > self.width - self.CORNER and p.y() > self.height - self.CORNER:
            return "corner"
        if right and p.y() > self._height_title():
            return "right"
        if below:
            return "bottom"
        return None

    CURSORS = {"corner": Qt.CursorShape.SizeFDiagCursor, "right": Qt.CursorShape.SizeHorCursor,
                "bottom": Qt.CursorShape.SizeVerCursor}

    def hoverMoveEvent(self, event) -> None:
        self.setCursor(self.CURSORS.get(self._zone(event.pos()), Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, event) -> None:
        self._enlarging = self._zone(event.pos())
        if self._enlarging:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._enlarging:
            self.prepareGeometryChange()
            if self._enlarging in ("corner", "right"):
                self.width = max(120.0, event.pos().x())
            if self._enlarging in ("corner", "bottom"):
                self.height = max(80.0, event.pos().y())
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._enlarging:
            self._enlarging = None
            _warn()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.change_title()

    def change_title(self) -> None:
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        from .widgets import ask_text
        text, ok = ask_text(view, tr('Frame title'), tr('Title:'), text=self.text, limit=80)
        if ok:
            self.text = text.strip()
            self.update()
            _warn()


#: Notes saved before the move to English: their Spanish keys and values, to the ones of now.
_OLD_KEYS = {"tipo": "type", "texto": "text", "ancho": "width", "alto": "height", "tamaño": "size",
             "fondo": "background", "borde": "border", "letra": "typeface", "negrita": "bold", "cursiva": "italic",
             "color_texto": "text_colour", "inicio": "start", "fin": "end", "grosor": "weight", "linea": "line",
             "titulo": "title", "tamaño_titulo": "title_size"}
_OLD_VALUES = {
    "type": {"texto": "text", "flecha": "arrow", "marco": "frame"},
    "color": {"amarillo": "yellow", "naranjo": "orange", "naranja": "orange", "rojo": "red", "verde": "green",
              "azul": "blue", "violeta": "violet", "gris": "grey", "negro": "black", "blanco": "white"},
    "typeface": {"sin serifa": "sans serif", "con serifa": "serif", "monoespaciada": "monospace"},
    "line": {"continua": "solid", "discontinua": "dashed", "punteada": "dotted"},
    "start": {"nada": "none", "clásica": "classic", "abierta": "open", "suiza": "swiss", "punto": "dot"},
    "weight": {"fino": "thin", "medio": "medium", "grueso": "thick"},
    "title": {"franja": "band", "texto": "text", "oculto": "hidden"},
}
_OLD_VALUES["end"] = _OLD_VALUES["start"]
_OLD_VALUES["text_colour"] = _OLD_VALUES["background"] = _OLD_VALUES["border"] = {
    **_OLD_VALUES["color"], "mismo": "same", "ninguno": "none"}


def in_english(d: dict) -> dict:
    """A note as it is saved now (an old one comes with Spanish keys and values)."""
    if "tipo" not in d:
        return d
    output = {}
    for k, v in d.items():
        k = _OLD_KEYS.get(k, k)
        if isinstance(v, str):
            v = _OLD_VALUES.get(k, {}).get(v, v)
        output[k] = v
    return output


def from__dict(d: dict):
    """An annotation from what is saved in the file (None if it is not recognised)."""
    d = in_english(d)
    kind, color = d.get("type"), d.get("color")
    if kind == "text":
        item = NoteText(str(d.get("text", "")), float(d.get("width", 220)), color or "yellow",
                         int(d.get("size", SIZES["medium"])))
    elif kind == "arrow":
        item = Arrow(QPointF(float(d.get("x2", 140)) - float(d.get("x", 0)),
                              float(d.get("y2", 0)) - float(d.get("y", 0))), color or "red")
    elif kind == "frame":
        item = Frame(float(d.get("width", 420)), float(d.get("height", 260)), str(d.get("text", "")), color or "blue")
    else:
        return None
    item.read_settings(d)
    item.setPos(float(d.get("x", 0)), float(d.get("y", 0)))
    if isinstance(item, Frame):
        item.setAcceptHoverEvents(True)
    return item
