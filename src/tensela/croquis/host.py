# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""What Tensela lends to Croquis: Qt and the colours of its scene.

The drawing core (compose, drawing, hatch, ink, marker, palette, paper, presets, shadow, strokes, texts, vector,
visibility, watercolour) works only with NumPy and is the own copy of Croquis (D11). Here it is lent, through its
hooks, the language, Qt's painting and smooth scaling, its own image as paper and the colours of the geometries. The
sun of a shadows panel does not exist yet: the light is always the sketch's «classic» one (from the top left).

:func:`install` runs when the package is imported (croquis/__init__.py).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPolygonF

from . import drawing, marker, palette, paper, texts
from .drawing import INK


def install() -> None:
    drawing.RESIZE = qt_resize
    drawing.PAINT = layers_image
    paper.IMAGE_COVER = image_cover
    from .. import language as language
    texts.LANGUAGE = lambda: language.LANGUAGE
    marker.SUN = None
    palette.SOURCES = (de_tensela,)
    palette.LOGGER = "tensela.croquis"


# ---- Tensela ------------------------------------------------------------------

def de_tensela(view, colour_of):
    """``(tris, marker, tone)`` of Tensela's scene (:class:`~.view.SketchView`): each triangle with the colour of
    its node."""
    if not len(view.tris):
        return None
    pairs = [colour_of({"color": rgb}) for rgb in view.colours]
    marker = np.array([m for m, _ in pairs], dtype=np.int64)[view.from_object]
    tone = np.array([t for _, t in pairs], dtype=np.float64)[view.from_object]
    return view.tris, marker, tone


# ---- Qt (as in the IngeTrazo edition) -----------------------------------

def to_qimage(rgb: np.ndarray) -> QImage:
    h, w = rgb.shape[:2]
    a = np.ascontiguousarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8),
                                        np.full((h, w), 255, dtype=np.uint8)]))
    img = QImage(a.tobytes(), w, h, w * 4, QImage.Format_RGBA8888)
    return img.convertToFormat(QImage.Format_ARGB32_Premultiplied)


def qt_resize(rgb: np.ndarray, width: int, height: int) -> np.ndarray:
    """Smoothly scale an (h, w, 3) float image with Qt."""
    img = to_qimage(rgb).scaled(width, height, Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_RGBA8888)
    a = np.frombuffer(img.constBits(), dtype=np.uint8,
                      count=img.bytesPerLine() * height)
    return a.reshape(height, img.bytesPerLine())[:, :width * 4].reshape(
        height, width, 4)[:, :, :3].astype(np.float64)


def draw_strokes(img: QImage, strokes: list, ink=INK) -> None:
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    for s in strokes:
        alpha = int(255 * max(0.0, min(1.0, s.opacity)))
        p.setBrush(QColor(ink[0], ink[1], ink[2], alpha))
        p.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in s.outline]))
    p.end()


def layers_image(layers) -> QImage:
    """A drawing's :class:`~croquis.drawing.Layers` as one QImage."""
    img = to_qimage(layers.coloured_sheet())
    draw_strokes(img, layers.strokes)
    return img


def image_cover(path: str, width: int, height: int):
    """An image of your own as the sheet, laid by Qt: repeated when small,
    else stretched to cover it (cropped to keep its proportions)."""
    src = QImage(path)
    if src.isNull():
        return None
    out = QImage(width, height, QImage.Format_RGB32)
    p = QPainter(out)
    if src.width() < paper.TILE_BELOW:
        p.fillRect(0, 0, width, height, QBrush(src))
    else:
        scaled = src.scaled(width, height, Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation)
        p.drawImage((width - scaled.width()) // 2, (height - scaled.height()) // 2, scaled)
    p.end()
    out = out.convertToFormat(QImage.Format_RGB888)
    a = np.frombuffer(out.constBits(), dtype=np.uint8,
                      count=out.bytesPerLine() * height)
    return a.reshape(height, out.bytesPerLine())[:, :width * 3].reshape(
        height, width, 3).astype(np.float32)
