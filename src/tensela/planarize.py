"""Planarize: panels made flat while they keep touching (a free surface built of flat panels, quadrilaterals or
hexagons, so they can be cut from boards or glass).

A panel of a curved surface is usually warped: its corners are not on one plane. Making each one flat on its own
opens gaps between them, because each corner is shared by several panels. So it is done together, a few hundred
times over:

1. each panel finds the plane that fits its corners best, and asks each corner to go onto it;
2. each corner goes to the average of what its panels ask (and a little further, the way it was going).

When nothing moves any more, every panel is flat (to a hundredth of a millimetre, or as near as the shape allows)
and the panels still meet corner to corner. On a surface curved in one direction (a vault, a scroll) it is easy; on
one curved two ways like a saddle, flat hexagons have to bend inwards, and some may not get fully flat: «flatness»
tells how far each one is.
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError, integer
from .language import tr

SHOW = ('panels', 'flatness', 'flatness before')
#: How much of its last move each corner keeps in the next round (0: none; near 1, quicker but restless).
MOMENTUM = 0.8
#: The last panels made flat, by their points: the panels and their flatness (two nodes) are found once.
_LAST: dict = {}
#: Flat enough: no corner farther from the plane of its panel than this part of the size of the whole.
FLAT = 1e-6


def _faces(values: np.ndarray, mask: np.ndarray, tolerance: float, shapes: list):
    """The corners welded (where panels share them) and each panel as a list of corner numbers, from the points of
    the elements (…, n, 3) and the panels of each element (`shapes`: lists of point numbers; a closed curve is one
    panel, a mesh one per face): the ids of every point (…, n), the corners (m, 3), the faces (lists of ids) and
    where each face is (element, its number among the panels of the element)."""
    points = values.reshape(-1, 3)
    keys = np.round(points / tolerance).astype(np.int64)
    _, first, ids = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    ids = ids.ravel()
    corners = points[first]
    per_panel = ids.reshape(values.shape[:-1])
    faces, where = [], []
    for index in np.ndindex(*values.shape[:-2]):
        if not mask[index]:
            continue
        for k, shape in enumerate(shapes):
            face = list(dict.fromkeys(per_panel[index][list(shape)].tolist()))   # without the padding repeats
            if len(face) >= 3:
                faces.append(face)
                where.append(index + (k,))
    return per_panel, corners, faces, where


def _flatness(corners: np.ndarray, faces: list) -> np.ndarray:
    """The largest distance from a corner of each panel to the plane that fits them best, in metres."""
    out = np.zeros(len(faces))
    for k, face in enumerate(faces):
        if len(face) > 3:
            p = corners[face]
            centred = p - p.mean(0)
            normal = np.linalg.svd(centred, full_matrices=False)[2][-1]
            out[k] = float(np.abs(centred @ normal).max())
    return out


def _flattened(corners: np.ndarray, faces: list, iterations: int, size: float) -> np.ndarray:
    """The corners moved until every panel is flat (see the module). Each round a corner goes to the average of what
    its panels ask, plus part of the move it made the round before (so it does not crawl towards the end)."""
    which = np.concatenate([np.full(len(f), k) for k, f in enumerate(faces)])     # panel of each (panel, corner)
    corner = np.concatenate([np.array(f) for f in faces])                         # corner of each
    count = np.bincount(which, minlength=len(faces)).astype(float)
    shared = np.bincount(corner, minlength=len(corners)).astype(float)
    p = corners.copy()
    before = p.copy()
    for _ in range(iterations):
        q = p[corner]
        centre = np.zeros((len(faces), 3))
        np.add.at(centre, which, q)
        centre /= count[:, None]
        d = q - centre[which]
        cov = np.zeros((len(faces), 3, 3))
        np.add.at(cov, which, d[:, :, None] * d[:, None, :])
        n = np.linalg.eigh(cov)[1][:, :, 0][which]                               # the least spread: the normal
        off = (d * n).sum(1, keepdims=True)
        if float(np.abs(off).max()) < FLAT * size:
            break                                                                 # every panel flat
        total = np.zeros_like(p)
        np.add.at(total, corner, q - off * n)
        p, before = total / shared[:, None] + MOMENTUM * (p - before), p
    return p


def planarize(panels, iterations=2000, show='panels', name: str | None = None) -> Data:
    """The node Planarize (see the module)."""
    from .geometry import POINT
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    kind = getattr(panels, "kind", None)
    if not isinstance(panels, Data) or kind is None or kind is POINT or not (kind.curve or kind.faces):
        raise ShapeError(tr('Connect panels: closed curves, like the cells of a Grid on a surface.'))
    iterations = integer(iterations)
    if not 1 <= iterations <= 5000:
        raise ShapeError(tr('The iterations go from 1 to 5000.'))
    values = np.asarray(panels.values, float)
    lead = values.shape[:-2]
    mask = np.broadcast_to(panels.mask if panels.levels else np.ones((), bool), lead)
    size = float(np.ptp(values.reshape(-1, 3), axis=0).max()) or 1.0
    # A closed curve (a cell of a Grid) is one panel; a mesh or a surface, one panel per face.
    shapes = [range(values.shape[-2])] if kind.curve or not kind.faces else [list(f) for f in kind.faces]
    per_panel, corners, faces, where = _faces(values, mask, 1e-6 * size, shapes)
    if not faces:
        raise ShapeError(tr('There are no panels with three corners or more.'))
    if show == 'flatness before':
        return _per_panel(_flatness(corners, faces), where, lead, len(shapes), panels, name)
    key = (values.tobytes(), values.shape, np.asarray(mask).tobytes(), iterations)
    if key not in _LAST:
        if len(_LAST) >= 8:
            _LAST.pop(next(iter(_LAST)))
        _LAST[key] = _flattened(corners, faces, iterations, size)
    flat = _LAST[key]
    if show == 'flatness':
        return _per_panel(_flatness(flat, faces), where, lead, len(shapes), panels, name)
    return panels.derived(flat[per_panel], name, panels.kind)


def _per_panel(numbers: np.ndarray, where: list, lead: tuple, faces: int, panels: Data, name) -> Data:
    """One number per panel, with the levels of the panels (0 where there is none); with several panels per element
    (the faces of a mesh), a level «face» more."""
    out = np.zeros(lead + (faces,))
    for index, number in zip(where, numbers):
        out[index] = number
    out[out < 1e-7] = 0.0                                # below a ten-thousandth of a millimetre: flat
    if faces == 1:
        return Data(out[..., 0], panels.levels, name, panels.variables, panels.starts, None, panels.holes)
    return panels.derived(out, name, None, ("face",))
