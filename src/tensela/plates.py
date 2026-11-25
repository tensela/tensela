"""Plates: a faceted shape built of boards, each face a plate trimmed back from its edges so that two plates meeting
at any angle keep the same gap between them.

Two plates of thickness t that meet along an edge at an angle α (between the two faces, on the side where they would
touch) collide unless each one stops short of the edge. The plate is trimmed back from the edge by

    s = (g / 2 + (t / 2) cos(α / 2)) / sin(α / 2)

so that the nearest corners of the two plates are g apart, whatever the angle: in a flat joint (α = 180°) just g / 2;
in an acute one, much more. The same rule places the holes of the hinges: the gap stays the same all over the
structure.

The faces are found in a mesh (or a box, or any faces); the vertices that coincide are welded, so the edge two faces
share is known even if each face brings its own copy of its corners (as the Code node gives them). An edge of the
border (one face only) is not trimmed.
"""
from __future__ import annotations

import math

import numpy as np

from .data import Data, ShapeError
from .geometry import CLOSED_CURVE
from .language import tr

SHOW = ('plates', 'outlines', 'angles', 'setbacks')


def _faces_of(shape) -> list[np.ndarray]:
    """The faces of a geometry as polygons (k, 3), each with its own corners."""
    from .simulation import _items
    if not isinstance(shape, Data) or shape.kind is None or shape.kind.faces is None or shape.kind.curve:
        raise ShapeError(tr('Connect something with faces: a mesh, a box, a surface.'))
    polygons = []
    for _, v in _items(shape, CLOSED_CURVE):
        for face in shape.kind.faces:
            polygons.append(np.asarray(v, float)[list(face)])
    if not polygons:
        raise ShapeError(tr('There are no faces to make plates of.'))
    return polygons


def _normal(p: np.ndarray) -> np.ndarray:
    n = np.cross(p, np.roll(p, -1, axis=0)).sum(0)                # Newell: the sum of the cross of each side
    length = np.linalg.norm(n)
    if length < 1e-12:
        raise ShapeError(tr('A face has no area: plates need flat faces with some size.'))
    return n / length


def setback(angle: float, thickness: float, gap: float) -> float:
    """How far a plate stops short of an edge where two plates meet at `angle` (radians, between the faces)."""
    half = 0.5 * angle
    return (0.5 * gap + 0.5 * thickness * math.cos(half)) / max(math.sin(half), 1e-6)


def _trimmed(p: np.ndarray, n: np.ndarray, back: np.ndarray) -> np.ndarray:
    """The polygon `p` with each edge moved inwards by its own `back` (in the plane of the face)."""
    k = len(p)
    centre = p.mean(0)
    e1 = p[1] - p[0]
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    q = np.stack([(p - centre) @ e1, (p - centre) @ e2], 1)
    if 0.5 * np.sum(q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]) < 0:
        e2 = -e2                                                  # seen from the other side: counterclockwise
        q[:, 1] = -q[:, 1]
    lines = []
    for i in range(k):
        a, b = q[i], q[(i + 1) % k]
        d = (b - a) / np.linalg.norm(b - a)
        inward = np.array([-d[1], d[0]])
        lines.append((a + inward * back[i], d))
    out = []
    for i in range(k):
        (a0, d0), (a1, d1) = lines[i - 1], lines[i]
        m = np.array([d0, -d1]).T
        if abs(np.linalg.det(m)) < 1e-12:
            out.append(a1)
            continue
        t = np.linalg.solve(m, a1 - a0)
        out.append(a0 + d0 * t[0])
    out = np.array(out)
    # Each edge of the trimmed plate must still run the way it did: trimmed too much, the plate turns inside out.
    still = [(out[(i + 1) % k] - out[i]) @ lines[i][1] > 1e-9 for i in range(k)]
    if not all(still) or 0.5 * np.sum(out[:, 0] * np.roll(out[:, 1], -1) - np.roll(out[:, 0], -1) * out[:, 1]) <= 0:
        raise ShapeError(tr('A face is too small for that gap and thickness: its plate would disappear.'))
    return centre + out[:, :1] * e1 + out[:, 1:] * e2


def plates(shape, thickness=0.012, gap=0.01, show='plates', name: str | None = None) -> Data:
    """The node Plates (see the module)."""
    from .fabrication import _padded
    from .meshes import kind_mesh
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    t, g = float(thickness), float(gap)
    if t <= 0 or g < 0:
        raise ShapeError(tr('The thickness must be more than 0, and the gap not negative.'))
    polygons = _faces_of(shape)
    size = max(float(np.ptp(np.vstack(polygons), axis=0).max()), 1e-9)
    weld = 1e-6 * size

    def key(point):
        return tuple(np.round(point / weld).astype(np.int64))
    normals = [_normal(p) for p in polygons]
    sharing: dict = {}
    for f, p in enumerate(polygons):
        for i in range(len(p)):
            a, b = key(p[i]), key(p[(i + 1) % len(p)])
            sharing.setdefault(frozenset((a, b)), []).append((f, i))
    backs = [np.zeros(len(p)) for p in polygons]
    angles, setbacks = [], []
    for pair in sharing.values():
        if len(pair) != 2:
            continue                                              # the border: nothing meets it
        (f, i), (h, j) = pair
        # The angle between the two half-planes: from the edge towards the middle of each face (so it does not matter
        # which way a face looks).
        a, b = polygons[f][i], polygons[f][(i + 1) % len(polygons[f])]
        along = (b - a) / np.linalg.norm(b - a)
        towards = []
        for face in (f, h):
            v = polygons[face].mean(0) - a
            v = v - (v @ along) * along
            towards.append(v / max(np.linalg.norm(v), 1e-12))
        between = math.acos(float(np.clip(towards[0] @ towards[1], -1.0, 1.0)))
        s = setback(between, t, g)
        backs[f][i] = backs[h][j] = s
        angles.append(math.degrees(between))
        setbacks.append(s)
    if show == 'angles':
        return Data(np.array(angles or [180.0]), ("edge",), name)
    if show == 'setbacks':
        return Data(np.array(setbacks or [0.0]), ("edge",), name)
    outlines = [_trimmed(p, n, b) for p, n, b in zip(polygons, normals, backs)]
    if show == 'outlines':
        return Data(_padded(outlines), ("plate",), name, kind=CLOSED_CURVE)
    points, faces = [], []
    for q, n in zip(outlines, normals):                           # each plate, a prism of its thickness
        k, start = len(q), sum(len(x) for x in points)
        points.append(np.vstack([q + n * t / 2, q - n * t / 2]))
        faces.append(tuple(start + i for i in range(k)))
        faces.append(tuple(start + k + i for i in reversed(range(k))))
        faces.extend((start + i, start + k + i, start + k + (i + 1) % k, start + (i + 1) % k) for i in range(k))
    return Data(np.vstack(points), (), name, kind=kind_mesh(faces))
