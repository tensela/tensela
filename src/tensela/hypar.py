"""Hypar: each panel folded into a hyperbolic paraboloid, as a piece of paper folded along its diagonal.

A hypar (hyperbolic paraboloid) is the saddle a flat square makes when two opposite corners rise and the other two
stay: a ruled surface, made of straight lines from one edge to the opposite one. A sheet of paper folded along a
diagonal takes this shape; many of them make a folded skin.

For each panel of four corners (a Grid, on any surface) the node lifts two opposite corners along the panel's normal
by the «lift» (one for all, or one per panel). It gives:

- the **folded piece**: the curved surface between the four corners (bilinear: S(u, v) between the corners), smooth;
- the **flat piece**: what is cut out of the sheet, the folded piece opened along its fold (the diagonal between
  the corners that stay): two triangles that keep the length of every edge, laid flat on the ground at the origin
  with the longest edge along x (as it goes on the sheet), ready for Lay flat;
- the **fold**: the diagonal, the line to score or fold;
- the **longest edge** of each piece, the one that has to fit on the sheet.
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError, align
from .geometry import CLOSED_CURVE, CURVE, RECTANGLE, kind_surface
from .language import tr

SHOW = ('folded piece', 'flat piece', 'fold', 'longest edge')
CORNERS = ('first and third', 'second and fourth')
SAMPLES = 9


def _numbers(x) -> Data:
    if isinstance(x, Data):
        return x
    return Data(np.asarray(x if x is not None else 0.0, dtype=float), (), None)


def _flat(p: np.ndarray, fold: tuple[int, int]) -> np.ndarray:
    """The four corners (…, 4, 3) opened flat along the diagonal `fold`: two triangles on the ground, the fold on the
    x axis from the origin; each corner keeps its distances to the two ends of the fold (so every edge keeps its
    length)."""
    a, b = fold
    others = [i for i in range(4) if i not in fold]
    pa, pb = p[..., a, :], p[..., b, :]
    length = np.linalg.norm(pb - pa, axis=-1)
    out = np.zeros(p.shape[:-2] + (4, 3))
    out[..., b, 0] = length
    for side, k in zip((1.0, -1.0), others):               # one triangle on each side of the fold
        da = np.linalg.norm(p[..., k, :] - pa, axis=-1)
        db = np.linalg.norm(p[..., k, :] - pb, axis=-1)
        x = (da ** 2 - db ** 2 + length ** 2) / (2 * np.maximum(length, 1e-12))
        y = np.sqrt(np.maximum(da ** 2 - x ** 2, 0.0))
        out[..., k, 0], out[..., k, 1] = x, side * y
    # Laid as it goes on the sheet: its longest edge along x, from the origin.
    edges = np.roll(out, -1, axis=-2) - out
    longest = np.argmax(np.linalg.norm(edges, axis=-1), axis=-1)
    direction = np.take_along_axis(edges, longest[..., None, None], axis=-2)[..., 0, :]
    angle = np.arctan2(direction[..., 1], direction[..., 0])
    c, s_ = np.cos(-angle)[..., None], np.sin(-angle)[..., None]
    x, y = out[..., 0], out[..., 1]
    out[..., 0], out[..., 1] = c * x - s_ * y, s_ * x + c * y
    out[..., :2] -= out[..., :2].min(axis=-2, keepdims=True)
    return out


def hypar(panels, lift=0.1, corners='first and third', show='folded piece', name: str | None = None) -> Data:
    """The node Hypar (see the module)."""
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    if corners not in CORNERS:
        raise ShapeError(tr('The corners must be one of: {options}.').format(options=", ".join(tr(o) for o in CORNERS)))
    if not isinstance(panels, Data) or panels.kind is None or panels.kind.name != RECTANGLE.name:
        raise ShapeError(tr('Connect panels of four corners: a Grid on a surface, rectangles.'))
    aligned = align(panels, _numbers(lift))
    p, h = (np.asarray(v, float) for v in aligned.values)
    levels = aligned.levels

    def out(values, kind=None):
        return Data(values, levels, name, aligned.variables, aligned.starts, kind, aligned.holes)

    # The normal of each panel (the cross of its diagonals) and the two corners that rise.
    n = np.cross(p[..., 2, :] - p[..., 0, :], p[..., 3, :] - p[..., 1, :])
    n = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
    up, stay = ((0, 2), (1, 3)) if corners == 'first and third' else ((1, 3), (0, 2))
    q = p.copy()
    for i in up:
        q[..., i, :] = p[..., i, :] + n * h[..., None]
    if show == 'longest edge':
        edges = np.linalg.norm(q - np.roll(q, -1, axis=-2), axis=-1)
        return out(edges.max(-1))
    if show == 'fold':
        return out(np.stack([q[..., stay[0], :], q[..., stay[1], :]], -2), CURVE)
    if show == 'flat piece':
        return out(_flat(q, stay), CLOSED_CURVE)
    t = np.linspace(0.0, 1.0, SAMPLES)
    u, v = np.meshgrid(t, t, indexing="ij")                 # rows along v, columns along u
    w = np.stack([(1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v], -1).reshape(-1, 4)
    surface = np.einsum("km,...mc->...kc", w, q)
    return out(surface, kind_surface(SAMPLES, SAMPLES))
