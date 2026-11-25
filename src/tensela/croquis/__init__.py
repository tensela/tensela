"""Croquis inside Tensela (D11): the 3D view as a freehand sketch.

It is an **own copy** of Victor Crespo's Croquis (GPL-3), taken from the IngeTrazo edition (0.14.0, commit 85d9089,
24-10-2026), which uses Qt like Tensela. The IngeTrazo and Blender editions stay apart, untouched: an
improvement of the drawing is passed by hand from one to the other.

- The **drawing core** (compose, drawing, hatch, ink, marker, palette, paper, presets, shadow, strokes, texts,
  vector, visibility, watercolour) is Croquis's, unchanged except for the comments («the host» instead of
  IngeTrazo); it only uses NumPy.
- **export** saves in PNG, layered SVG and PDF (with Qt), as in Croquis.
- Tensela's own: **host** (what is lent to the core, with Qt) and **view** (Tensela's camera and geometry
  in the form the core asks for, only with NumPy).

    from tensela.croquis import draw
    layers = draw(objects, camera, width=2400, style_name="colour_marker")
    export.save(layers, "sketch.pdf")
"""
from __future__ import annotations

from . import drawing, presets, texts
from .view import Camera, SketchView, pyvista_camera  # noqa: F401

# The language, from the start: the lists of the dialog (styles, papers)
# are written before the first drawing.
def _language() -> str:
    from .. import language as language
    return language.LANGUAGE


texts.LANGUAGE = _language

# Qt (the painting, the scaling) is lent when drawing, not when importing: so the
# hidden-line computation (visibility, view) works without an interface.
_borrowed = False


def _borrow() -> None:
    global _borrowed
    if not _borrowed:
        from . import host
        host.install()
        _borrowed = True

SKETCH_VERSION = "0.14.0"


def settings(style_name: str = "colour_marker", **changes) -> dict:
    """The Croquis settings of a style (ink, grey_marker, colour_marker, watercolour, hatched, contrast), with the
    `changes` asked for."""
    s = presets.apply_preset(presets.DEFAULTS, style_name) if style_name in presets.PRESETS else dict(presets.DEFAULTS)
    s.update(changes)
    return presets.clean(s)


def draw(objects, camera: Camera, width: int = 2400, style_name: str = "colour_marker",
            s: dict | None = None) -> drawing.Layers:
    """The sketch of the view, as its layers (paper, colour, ink)."""
    _borrow()
    s = s if s is not None else settings(style_name)
    view = SketchView(objects, camera)
    return drawing.render(view, presets.line_style(s), width, marker=presets.marker_style(s),
                          composition=presets.composition(s), paper_kind=s["paper"],
                          paper_image=s["paper_image"])
