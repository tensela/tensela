"""The preview of a node inside its card (Delivery 5, batch 8).

A small drawing of what comes out of the node, in axonometric (from the front, the left and above, like «Frame all»
in the 3D view): the faces shaded, from back to front; the curves as lines; the points as dots. It is drawn with
QPainter, without VTK: it is light and looks like the rest of the card. With many faces a sample is drawn (it is a
thumbnail, not a render).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

MAX_FACES = 6000           # more faces: a spread sample
MAX_LINES = 4000

_FROM_ = np.array([-0.55, -1.0, 0.45])            # towards where the viewer is (like frame all)
_AHEAD = -_FROM_ / np.linalg.norm(_FROM_)
_RIGHT = np.cross(_AHEAD, [0.0, 0.0, 1.0])
_RIGHT /= np.linalg.norm(_RIGHT)
_ABOVE = np.cross(_RIGHT, _AHEAD)
_SPAN = -0.45 * _RIGHT + 0.75 * _ABOVE - 0.5 * _AHEAD
_SPAN /= np.linalg.norm(_SPAN)


def _vertices(data) -> np.ndarray:
    """(elements, points per element, 3): only those that exist."""
    v = data.values[data.mask] if data.levels else data.values[None]
    return np.asarray(v, float)


def drawable(data) -> bool:
    return data is not None and getattr(data, "kind", None) is not None


def draw(data, width: int, height: int, color: str, ink: str, scale: float = 2.0) -> QImage | None:
    """The drawing of `data` in an image of `width` × `height` (at `scale` for dense screens); None if it is not geometry."""
    if not drawable(data):
        return None
    vertices = _vertices(data)
    if vertices.size == 0:
        return None
    kind = data.kind
    screen = np.stack([vertices @ _RIGHT, vertices @ _ABOVE], axis=-1)    # x, y (y up)
    z_depth = vertices @ _AHEAD

    image = QImage(int(width * scale), int(height * scale), QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(scale)
    image.fill(Qt.GlobalColor.transparent)
    planes = screen.reshape(-1, 2)
    minimum, maximum = planes.min(axis=0), planes.max(axis=0)
    size_ = np.maximum(maximum - minimum, 1e-9)
    margin = 6.0
    k = min((width - 2 * margin) / size_[0], (height - 2 * margin) / size_[1])
    if not np.isfinite(k) or k <= 0:
        return None
    centre = (minimum + maximum) / 2

    def to_image(p: np.ndarray) -> np.ndarray:            # (…, 2) of the drawing → pixels of the image
        x = (p[..., 0] - centre[0]) * k + width / 2
        y = height / 2 - (p[..., 1] - centre[1]) * k
        return np.stack([x, y], axis=-1)

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base, edge = QColor(color), QColor(ink)
    if kind.faces is None and not kind.curve:            # puntos
        points = to_image(planes)
        if len(points) > MAX_FACES:
            points = points[:: len(points) // MAX_FACES + 1]
        p.setPen(QPen(base, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPoints([QPointF(x, y) for x, y in points])
    elif kind.curve:                                       # curves: polylines
        lines = to_image(screen)
        if len(lines) > MAX_LINES:
            lines = lines[:: len(lines) // MAX_LINES + 1]
        p.setPen(QPen(base, 1.4))
        for line in lines:
            polygon = QPolygonF([QPointF(x, y) for x, y in line])
            if kind.closed:
                p.drawPolygon(polygon)
            else:
                p.drawPolyline(polygon)
    else:                                                  # faces, shaded, from back to front
        polygons, backgrounds, spans = [], [], []
        for face in kind.faces:
            corners = vertices[:, list(face), :]          # (elementos, lados, 3)
            normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, -1] - corners[:, 0])
            length = np.linalg.norm(normal, axis=1)
            normal = normal / np.where(length > 0, length, 1.0)[:, None]
            spans.append(0.55 + 0.45 * np.abs(normal @ _SPAN))
            backgrounds.append(z_depth[:, list(face)].mean(axis=1))
            polygons.append(to_image(screen[:, list(face), :]))
        order = []
        for i, f in enumerate(backgrounds):
            order.extend((float(depth), i, j) for j, depth in enumerate(f))
        if len(order) > MAX_FACES:
            order = order[:: len(order) // MAX_FACES + 1]
        order.sort(key=lambda t: -t[0])                    # the farthest first
        with_edges = len(order) <= 1500
        pencil = QPen(QColor(edge.red(), edge.green(), edge.blue(), 110), 0.6) if with_edges else Qt.PenStyle.NoPen
        p.setPen(pencil)
        for _depth, i, j in order:
            span = float(spans[i][j])
            p.setBrush(QColor(int(base.red() * span), int(base.green() * span), int(base.blue() * span)))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in polygons[i][j]]))
    p.end()
    return image
