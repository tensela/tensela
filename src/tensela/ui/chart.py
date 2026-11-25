"""The editor of a Graph in the node's panel: a curve in a square drawn by moving its points.

- **Drag a point**: it moves (the end ones, only up and down).
- **Click** on an empty place: a new point there.
- **Double-click** on a point: its exact values. **Right-click**: its exact values, or remove it (at least 2 remain).

While dragging, the curve is recomputed and reported with `change(points, False)`; on releasing, with `True` (it
can be undone).
"""
from __future__ import annotations

import numpy as np
import json

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QMenu, QWidget

from ..geometry import evaluate_chart, chart_points
from ..language import tr
from . import theme as theme

#: Where the user's own curves are kept: in the preferences, so they are there in every project.
_OWN_KEY = "charts/own"


def own_charts() -> dict[str, list]:
    """The curves the user saved, by name (in the order they were saved)."""
    try:
        saved = json.loads(QSettings().value(_OWN_KEY, "{}") or "{}")
    except (TypeError, ValueError):
        return {}
    return {str(k): v for k, v in saved.items() if isinstance(v, list) and len(v) >= 2} if isinstance(saved, dict) else {}


def save_own_chart(name: str, points) -> None:
    """Keeps a curve with that name (it replaces one with the same name)."""
    charts = own_charts()
    charts[name] = [[round(float(x), 4), round(float(y), 4)] for x, y in chart_points(points).tolist()]
    QSettings().setValue(_OWN_KEY, json.dumps(charts))


def delete_own_chart(name: str) -> None:
    charts = own_charts()
    charts.pop(name, None)
    QSettings().setValue(_OWN_KEY, json.dumps(charts))


#: At how many pixels a point is «grabbed».
RADIUS_TAKE = 9
#: The room between the edge of the box and the curve: the corner points stay inside.
PADDING = 12
#: The height of the bottom row («the smallest · the largest»).
HEIGHT_LABELS = 18


class EditorChart(QWidget):
    change = Signal(object, bool)          # the points ([[x, y], …], from 0 to 1) and whether it is the final change

    def __init__(self, points, smooth: bool = True, parent=None):
        super().__init__(parent)
        self.points = [list(map(float, p)) for p in chart_points(points).tolist()]
        self.smooth = smooth
        self._dragging: int | None = None
        self._over: int | None = None
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.setToolTip(tr('Drag the points · click on an empty spot: a new point · double-click a point: its exact '
                           'values · right click: remove it'))

    # --- From the square (0 to 1) to the screen, and back -------------------------------------------

    def _frame(self) -> QRectF:
        """The box: the whole width (aligned with what is above), minus the row of labels."""
        return QRectF(0.5, 0.5, self.width() - 1, self.height() - HEIGHT_LABELS - 1)

    def _box(self) -> QRectF:
        """Where the curve goes: the box, with room around."""
        return self._frame().adjusted(PADDING, PADDING, -PADDING, -PADDING)

    def _to_screen(self, x: float, y: float) -> QPointF:
        c = self._box()
        return QPointF(c.left() + x * c.width(), c.bottom() - y * c.height())

    def _to_chart(self, pos: QPointF) -> tuple[float, float]:
        c = self._box()
        x = (pos.x() - c.left()) / max(c.width(), 1)
        y = (c.bottom() - pos.y()) / max(c.height(), 1)
        return float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1))

    def _point_in(self, pos: QPointF) -> int | None:
        best, distance = None, RADIUS_TAKE
        for i, (x, y) in enumerate(self.points):
            p = self._to_screen(x, y)
            d = ((p.x() - pos.x()) ** 2 + (p.y() - pos.y()) ** 2) ** 0.5
            if d < distance:
                best, distance = i, d
        return best

    # --- Dibujar ----------------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QColor(theme.color("field", "#22252c"))
        edge = QColor(theme.color("border", "#3a3f4a"))
        text = QColor(theme.color("text_2", "#9aa0aa"))
        accent = QColor(theme.color("accent", "#8a7dff"))
        c = self._box()
        frame = self._frame()
        painter.setPen(QPen(edge, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(frame, 6, 6)
        grid = QColor(edge)
        grid.setAlpha(120)
        painter.setPen(QPen(grid, 1, Qt.PenStyle.DotLine))
        for k in (0.25, 0.5, 0.75):
            painter.drawLine(self._to_screen(k, 0), self._to_screen(k, 1))
            painter.drawLine(self._to_screen(0, k), self._to_screen(1, k))
        # The curve.
        xs = np.linspace(0, 1, 120)
        ys = evaluate_chart(self.points, xs, self.smooth)
        path = QPainterPath(self._to_screen(xs[0], ys[0]))
        for x, y in zip(xs[1:], ys[1:]):
            path.lineTo(self._to_screen(x, y))
        painter.setPen(QPen(accent, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        # The points.
        for i, (x, y) in enumerate(self.points):
            chosen = i in (self._dragging, self._over)
            painter.setPen(QPen(accent, 2))
            painter.setBrush(accent if chosen else background)
            r = 6 if chosen else 5
            painter.drawEllipse(self._to_screen(x, y), r, r)
        # What each axis is, small.
        painter.setPen(text)
        font = painter.font()
        font.setPointSizeF(max(font.pointSizeF() - 1, 8))
        painter.setFont(font)
        row = QRectF(frame.left() + 2, frame.bottom() + 2, frame.width() - 4, HEIGHT_LABELS)
        painter.drawText(row, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tr('smallest'))
        painter.drawText(row, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tr('largest'))

    # --- Mouse ------------------------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        i = self._point_in(pos)
        if event.button() == Qt.MouseButton.RightButton:
            if i is not None:
                menu = QMenu(self)
                menu.addAction(tr('Exact values…'), lambda: self.ask_values(i))
                remove = menu.addAction(tr('Remove this point'), lambda: self._remove(i))
                remove.setEnabled(len(self.points) > 2 and i not in (0, len(self.points) - 1))
                menu.exec(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if i is None:                                   # a new point, and one can keep dragging
            x, y = self._to_chart(pos)
            self.points.append([x, y])
            self.points.sort(key=lambda p: p[0])
            i = self.points.index([x, y])
        self._dragging = i
        self.update()
        self.change.emit(self._copy(), False)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if self._dragging is None:
            over = self._point_in(pos)
            if over != self._over:
                self._over = over
                self.setCursor(Qt.CursorShape.OpenHandCursor if over is not None else Qt.CursorShape.CrossCursor)
                self.update()
            return
        x, y = self._to_chart(pos)
        i = self._dragging
        if i == 0:                                      # the ends stay at their edge: they only go up and down
            x = 0.0
        elif i == len(self.points) - 1:
            x = 1.0
        else:                                           # and those in the middle do not go past their neighbours
            x = float(np.clip(x, self.points[i - 1][0] + 0.005, self.points[i + 1][0] - 0.005))
        self.points[i] = [x, y]
        self.update()
        self.change.emit(self._copy(), False)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging is not None:
            self._dragging = None
            self.update()
            self.change.emit(self._copy(), True)

    def mouseDoubleClickEvent(self, event) -> None:
        i = self._point_in(event.position())
        if i is not None:
            self._dragging = None
            self.ask_values(i)

    def ask_values(self, i: int) -> None:
        """The exact values of a point, from 0 to 1 (the ends stay at their edge: only their height)."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Point {n}').format(n=i + 1))
        shape = QFormLayout(dialog)
        fields = []
        for axis, value in zip("xy", self.points[i]):
            field = QDoubleSpinBox()
            field.setRange(0.0, 1.0)
            field.setDecimals(3)
            field.setSingleStep(0.01)
            field.setValue(float(value))
            shape.addRow(axis, field)
            fields.append(field)
        fields[0].setEnabled(i not in (0, len(self.points) - 1))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        shape.addRow(buttons)
        (fields[0] if fields[0].isEnabled() else fields[1]).selectAll()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        x, y = fields[0].value(), fields[1].value()
        if 0 < i < len(self.points) - 1:              # those in the middle do not go past their neighbours
            x = float(np.clip(x, self.points[i - 1][0] + 0.005, self.points[i + 1][0] - 0.005))
        self.points[i] = [x, y]
        self.update()
        self.change.emit(self._copy(), True)

    def _remove(self, i: int) -> None:
        if len(self.points) <= 2 or i in (0, len(self.points) - 1):
            return                                      # the ends and the last 2 stay
        del self.points[i]
        self._over = self._dragging = None
        self.update()
        self.change.emit(self._copy(), True)

    def put(self, points) -> None:
        """Another shape (of the starting ones): it replaces the points."""
        self.points = [list(map(float, p)) for p in chart_points(points).tolist()]
        self.update()
        self.change.emit(self._copy(), True)

    def _copy(self) -> list:
        return [[round(x, 4), round(y, 4)] for x, y in self.points]
