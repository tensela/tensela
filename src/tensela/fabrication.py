"""Pieces to be cut from a sheet: curves offset in their plane, and a shape cut into sections.

    offset_curve(curve, 0.002)                     # each curve 2 mm aside, in its own plane
    sections(surface, thickness=0.003)             # the surface cut into boards of 3 mm, each one a closed outline

A section of a surface is an open curve: to be a piece it is closed, as a **band** that follows the surface with a
depth (the curve and its offset downwards, joined at the ends), or **down to a base** (the curve and the plane under
the whole shape, like the slices of a terrain model). A section of a closed body is closed already.

The outlines are cleaned with the 2D library (manifold3d's CrossSection, Clipper inside): where an offset folds over
itself in a tight bend, or a rib under an overhang crosses its own curve, what is left is one clean outline.
"""
from __future__ import annotations

import math

import numpy as np

from .data import Data, ShapeError
from .geometry import CLOSED_CURVE, CURVE, POINT, _data
from .language import tr

#: Which way the sections are cut: planes across x, across y, or level (across z).
CUTS = ('x', 'y', 'z', 'radial', 'along a curve')
#: How an open section becomes a piece.
PIECES = ('band', 'to base')
#: What Sections shows: the outlines to cut, or the boards with their thickness.
SHOW_SECTIONS = ('outlines', 'boards')
#: The corners of an offset closed curve.
CORNERS = ('round', 'sharp')

#: Inside the 2D library, lengths go in millimetres (it works with fixed precision).
_MM = 1000.0


def _clean(contours: list[np.ndarray]) -> list[np.ndarray]:
    """Closed 2D outlines without crossings (the union of what they enclose), the largest first; each one turning
    anticlockwise."""
    from manifold3d import CrossSection, FillRule
    rings = []
    for c in contours:
        c = np.asarray(c, float)
        if len(c) >= 3:
            rings.append(c if _area(c) >= 0 else c[::-1])
    if not rings:
        return []
    from manifold3d import JoinType
    region = CrossSection([r * _MM for r in rings], FillRule.Positive)
    if len(rings) > 1:
        # Pieces side by side leave hairline slits between them (rounding): out and back in by a thousandth of a
        # millimetre closes them, and the outline does not touch itself.
        region = region.offset(1e-3, JoinType.Miter, 4.0).offset(-1e-3, JoinType.Miter, 4.0)
    out = [_ring_without_repeats(np.asarray(p, float) / _MM) for p in region.to_polygons()]
    out = sorted((p for p in out if _area(p) > 0), key=_area, reverse=True)   # (holes turn the other way: out)
    return [p for p in out if _area(p) > 1e-4 * _area(out[0])]                # (and slivers)


def _ring_without_repeats(p: np.ndarray, tolerance: float = 1e-7) -> np.ndarray:
    """A closed 2D outline without points closer than `tolerance` to the one before (a tenth of a micron)."""
    keep = np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > tolerance]
    p = p[keep]
    while len(p) > 3 and np.linalg.norm(p[0] - p[-1]) <= tolerance:
        p = p[:-1]
    return p


def _area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2


def _side_offset(p: np.ndarray, d: float) -> np.ndarray:
    """An open 2D polyline moved `d` to its left (negative: to its right), each vertex along the mean of its two
    segments' normals, lengthened at the bends so the segments stay at `d` (up to three times)."""
    seg = np.diff(p, axis=0)
    length = np.linalg.norm(seg, axis=1, keepdims=True)
    seg = np.divide(seg, length, out=np.zeros_like(seg), where=length > 0)
    normal = np.stack([-seg[:, 1], seg[:, 0]], axis=1)           # left of each segment
    before = np.vstack([normal[:1], normal])
    after = np.vstack([normal, normal[-1:]])
    mean = before + after
    size = np.linalg.norm(mean, axis=1, keepdims=True)
    mean = np.divide(mean, size, out=after.copy(), where=size > 1e-12)
    cosine = np.clip(np.einsum("ij,ij->i", mean, after), 1 / 3, 1.0)[:, None]
    return p + mean * d / cosine


def _band(p: np.ndarray, d: float, downwards: bool = True) -> list[np.ndarray]:
    """A strip of depth `d` along an open 2D polyline, on one side (under it, if `downwards`; else, to its left), as
    pieces to be joined: a quadrilateral under each segment, and a wedge at each bend. Joined, they give the strip
    without folds, however tight the bends."""
    seg = np.diff(p, axis=0)
    length = np.linalg.norm(seg, axis=1, keepdims=True)
    keep = length[:, 0] > 0
    seg = np.divide(seg, length, out=np.zeros_like(seg), where=length > 0)
    normal = np.stack([-seg[:, 1], seg[:, 0]], axis=1)          # left of each segment
    if downwards and normal[keep, 1].mean() > 0:
        normal = -normal
    pieces = []
    for i in np.nonzero(keep)[0]:
        a, b = p[i], p[i + 1]
        pieces.append(np.array([a, b, b + normal[i] * d, a + normal[i] * d]))
    idx = np.nonzero(keep)[0]
    for i, j in zip(idx[:-1], idx[1:]):                         # the wedge between two segments, at their joint
        q = p[j]
        pieces.append(np.array([q, q + normal[i] * d, q + normal[j] * d]))
    return pieces


def _down_to_base(p: np.ndarray, base: float) -> list[np.ndarray]:
    """The region between an open 2D polyline and the level `base` under it, as trapezoids to be joined (an
    overhang does not fold it: under it, it is all solid)."""
    return [np.array([p[i], p[i + 1], [p[i + 1, 0], base], [p[i, 0], base]]) for i in range(len(p) - 1)
            if abs(p[i + 1, 0] - p[i, 0]) > 0 or abs(p[i + 1, 1] - p[i, 1]) > 0]


def _band_rings(p: np.ndarray, d: float, downwards: bool = True) -> list[np.ndarray]:
    """The band as one outline (the curve and its offset, joined at the ends) when the offset does not fold; if it
    folds (a bend tighter than the depth), as the pieces of _band, which join without folding."""
    from manifold3d import CrossSection, FillRule
    seg = np.diff(p, axis=0)
    normal = np.stack([-seg[:, 1], seg[:, 0]], axis=1)
    side = -1.0 if downwards and normal[:, 1].mean() > 0 else 1.0
    ring = np.vstack([p, _side_offset(p, side * d)[::-1]])
    ring = ring if _area(ring) >= 0 else ring[::-1]
    positive = CrossSection([ring * _MM], FillRule.Positive)
    # A fold is a loop that turns the other way: filled «non zero» it counts, filled «positive» it does not.
    folds = abs(CrossSection([ring * _MM], FillRule.NonZero).area() - positive.area()) > 1e-4 * positive.area()
    clean = [_ring_without_repeats(np.asarray(c, float) / _MM) for c in positive.to_polygons()]
    clean = [c for c in clean if abs(_area(c)) > 1e-4 * _area(ring)]          # (out: slivers left at the ends)
    if not folds and len(clean) == 1:
        return clean
    return _band(p, d, downwards)


def _to_base_rings(p: np.ndarray, base: float) -> list[np.ndarray]:
    """Down to the base as one outline when the curve does not turn back over itself; with an overhang, as
    trapezoids to be joined."""
    du = np.diff(p[:, 0])
    if (du > 0).all() or (du < 0).all():
        return [np.vstack([p, [[p[-1, 0], base], [p[0, 0], base]]])]
    return _down_to_base(p, base)


def _without_reversals(p: np.ndarray) -> np.ndarray:
    """An open 2D polyline without spikes: a point where the path turns right back (more than about 170°) goes."""
    while len(p) > 2:
        seg = np.diff(p, axis=0)
        unit = seg / np.maximum(np.linalg.norm(seg, axis=1, keepdims=True), 1e-300)
        back = np.nonzero(np.einsum("ij,ij->i", unit[:-1], unit[1:]) < -0.985)[0]
        if not len(back):
            break
        p = np.delete(p, back[0] + 1, axis=0)
    return p


def _without_repeats(c: np.ndarray, tolerance: float) -> np.ndarray:
    keep = np.r_[True, np.linalg.norm(np.diff(c, axis=0), axis=1) > tolerance]
    return c[keep]


def _padded(curves: list[np.ndarray]) -> np.ndarray:
    """Curves of different lengths in one table: each one repeats its last point up to the longest."""
    n = max(len(c) for c in curves)
    return np.array([np.vstack([c, np.repeat(c[-1:], n - len(c), axis=0)]) for c in curves])


def _closed_ring(c: np.ndarray, tolerance: float) -> np.ndarray:
    """A closed 3D curve as its ring of points (without the padding, without repeating the first at the end)."""
    c = _without_repeats(c, tolerance)
    if len(c) > 1 and np.linalg.norm(c[0] - c[-1]) <= tolerance:
        c = c[:-1]
    return c


# --- Offset curve ---------------------------------------------------------------------------------------------------

def offset_curve(curve: Data, distance=0.01, corners: str = 'round', name: str | None = None) -> Data:
    """Each curve moved `distance` aside, in its own plane (*Offset*). A closed curve grows outwards (negative:
    inwards), with its corners rounded or sharp; an open curve goes to its left, looking along it from above its
    plane (negative: to its right). Several distances give several offsets, combined with the curves by the names of
    their levels (a Series of 4 distances and one curve: four outlines)."""
    from .data import align, require_numbers
    from .polygons import _plane_frame
    if not isinstance(curve, Data) or curve.kind is None or not curve.kind.curve:
        raise ShapeError(tr('“curve” must be a curve (or several).'))
    if corners not in CORNERS:
        raise ShapeError(tr('“corners” must be one of: {options}.').format(options=", ".join(tr(c) for c in CORNERS)))
    distances = _data(distance)
    require_numbers(distances, 'distance')
    if distances.values.ndim > len(distances.levels):
        raise ShapeError(tr('“distance” must be one number for each offset (a number, or a list of numbers).'))
    closed = curve.kind.closed
    values = np.asarray(curve.values, float)
    flat = values.reshape((-1,) + values.shape[-2:])
    if distances.levels:
        # The curves and the distances, lined up by the names of their levels: each curve with its distance (the same
        # level) or with every distance (other levels).
        shape = values.shape[:len(curve.levels)]
        index = Data(np.arange(len(flat)).reshape(shape), curve.levels, curve.name, curve.variables, curve.starts)
        lined = align(index, distances)
        which = np.asarray(lined.values[0]).ravel()
        each = np.asarray(lined.values[1], float).ravel()
    else:
        lined = None
        which = np.arange(len(flat))
        each = np.full(len(flat), float(distances.values))
    size = float(np.nanmax(np.ptp(flat.reshape(-1, 3), axis=0))) or 1.0
    tol = size * 1e-9
    out = []
    for c, d in zip(flat[which], each):
        ring = _closed_ring(c, tol) if closed else _without_repeats(c, tol)
        if len(ring) < 2:
            out.append(c[:1].repeat(2, axis=0))
            continue
        origin, axes = _plane_frame(ring)
        uv = (ring - origin) @ axes.T
        if closed:
            from manifold3d import CrossSection, JoinType
            if _area(uv) < 0:
                uv = uv[::-1]
            join = JoinType.Round if corners == 'round' else JoinType.Miter
            moved = CrossSection([uv * _MM]).offset(d * _MM, join, 4.0)
            rings = sorted((np.asarray(p, float) / _MM for p in moved.to_polygons()), key=_area, reverse=True)
            if not rings or _area(rings[0]) <= 0:
                raise ShapeError(tr('Offset {distance} inwards, the curve “{name}” disappears: it is narrower than '
                                    'that.').format(distance=_text(abs(d)), name=curve._name()))
            uv = rings[0]
            uv = np.vstack([uv, uv[:1]])                          # closed: it ends at its first point
        else:
            uv = _side_offset(uv, d)
        out.append(origin + uv @ axes)
    lengths = {len(c) for c in out}
    table = _padded(out) if len(lengths) > 1 else np.array(out)
    kind = CLOSED_CURVE if closed else CURVE
    if lined is not None:
        table = table.reshape(np.asarray(lined.values[0]).shape + table.shape[-2:])
        return Data(table, lined.levels, name, lined.variables, lined.starts, kind)
    table = table.reshape(values.shape[:-2] + table.shape[-2:])
    return curve.derived(table, name, kind)


def _text(metres: float) -> str:
    from .values import text_length
    return text_length(metres)


# --- Sections -------------------------------------------------------------------------------------------------------

#: A smooth surface is cut on a mesh of about this many faces along its longer side: the sections follow its curves.
SECTION_SAMPLES = 150


def _fine(shape: Data) -> Data:
    """A smooth surface as a fine mesh (its grid of points may be coarse); a mesh or a body, as it is."""
    if shape.kind.grid is None:
        return shape
    from .mesh_tools import mesh_surface
    rows, columns = shape.kind.grid
    g = np.asarray(shape.values, float).reshape((-1, rows, columns, 3))[0]
    along_u = float(np.linalg.norm(np.diff(g, axis=1), axis=-1).sum(axis=1).max())
    along_v = float(np.linalg.norm(np.diff(g, axis=0), axis=-1).sum(axis=0).max())
    longer = max(along_u, along_v, 1e-12)
    nu = max(int(np.ceil(SECTION_SAMPLES * along_u / longer)), 2)
    nv = max(int(np.ceil(SECTION_SAMPLES * along_v / longer)), 2)
    # Its own grid, if it is fine enough; but no more than 400 faces a side (a surface of revolution may bring
    # thousands along its profile, and the cut does not need them).
    nu, nv = max(nu, min(columns - 1, 400)), max(nv, min(rows - 1, 400))
    if (nu, nv) == (columns - 1, rows - 1):
        return shape
    return mesh_surface(shape, nu, nv)

def _planes(cuts: str, points: np.ndarray, t: float, between: float, count, shape: Data, guide=None):
    """The cutting planes: (normal, a point on it, its two axes u and v), v as near the vertical as the plane allows."""
    e = np.eye(3)
    if cuts == 'along a curve':
        return _planes_along(guide, t, between)
    if cuts == 'radial':
        n = int(_data(count).values)
        if n < 1:
            raise ShapeError(tr('At least 1 radial board is needed.'))
        if n > 360:
            raise ShapeError(tr('That would give {n} boards: make them thicker, or leave a gap between them.').format(
                n=n))
        low, high = points.min(axis=0), points.max(axis=0)
        centre = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, 0.0])
        out = []
        for k in range(n):                                # planes through the vertical axis, half a turn shared out
            a = np.pi * k / n
            u = np.array([np.cos(a), np.sin(a), 0.0])
            out.append((np.cross(u, e[2]) * -1, centre, u, e[2]))
        return out
    axis = "xyz".index(cuts)
    u_axis, v_axis = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[axis]
    low, high = float(points[:, axis].min()), float(points[:, axis].max())
    if high - low < t:
        raise ShapeError(tr('“{name}” measures less than one board across {axis}: there is nothing to cut.').format(
            name=shape._name(), axis=cuts))
    step = t + between
    n = int(np.floor((high - low - t) / step + 1e-9)) + 1
    if n > 2000:
        raise ShapeError(tr('That would give {n} boards: make them thicker, or leave a gap between them.').format(n=n))
    used = (n - 1) * step + t
    positions = low + (high - low - used) / 2 + t / 2 + np.arange(n) * step     # centred on the shape
    return [(e[axis], e[axis] * x, e[u_axis], e[v_axis]) for x in positions]


def _planes_along(guide, t: float, between: float):
    """Planes across a guide curve, one every board and gap along its length (centred on it), each one square to the
    curve where it crosses it: the boards follow the shape (a spine, the axis of a leaning tower)."""
    if not isinstance(guide, Data) or guide.kind is None or not guide.kind.curve:
        raise ShapeError(tr('Cuts «along a curve» need the guide curve: connect it to «guide».'))
    c = _without_repeats(np.asarray(guide.values, float).reshape(-1, guide.values.shape[-2], 3)[0], 1e-12)
    if guide.kind.closed:
        c = np.vstack([c, c[:1]])
    lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))]
    total = float(lengths[-1])
    step = t + between
    if total < t:
        raise ShapeError(tr('The guide is shorter than one board.'))
    n = int(np.floor((total - t) / step + 1e-9)) + 1
    if n > 2000:
        raise ShapeError(tr('That would give {n} boards: make them thicker, or leave a gap between them.').format(n=n))
    used = (n - 1) * step + t
    at = (total - used) / 2 + t / 2 + np.arange(n) * step

    def point(s):
        return np.stack([np.interp(s, lengths, c[:, k]) for k in range(3)], axis=-1)

    half = max(step / 2, total * 1e-3)
    out = []
    for s in at:
        tangent = point(min(s + half, total)) - point(max(s - half, 0.0))
        normal = tangent / np.linalg.norm(tangent)
        u, v = _frame(normal)
        out.append((normal, point(s), u, v))
    return out


def sections(shape: Data, thickness=0.003, gap=0.0, cuts: str = 'x', piece: str = 'band', depth=0.01,
             show: str = 'outlines', count=8, guide=None, name: str | None = None) -> Data:
    """The shape cut into boards of `thickness`, one beside the other with `gap` between them, across `cuts` (or, with
    «radial», `count` boards through the vertical axis of the shape, half a turn shared out). Each section is the
    outline of a board, in its place: a closed curve (level «section», numbered from 1); a board with holes (a ring
    of a hollow body) adds a level «contour»: the outline first, then its holes. An open cut (a surface) is closed as
    a band of `depth` under it, or down to a base `depth` under the lowest point of the shape. `show`: the outlines
    (to cut) or the boards (with their thickness, to see them)."""
    from .meshes import _chain, _cut, _triangles
    if cuts not in CUTS:
        raise ShapeError(tr('“cuts” must be one of: {options}.').format(options=", ".join(tr(c) for c in CUTS)))
    if piece not in PIECES:
        raise ShapeError(tr('“piece” must be one of: {options}.').format(options=", ".join(tr(p) for p in PIECES)))
    if show not in SHOW_SECTIONS:
        raise ShapeError(tr('“show” must be one of: {options}.').format(
            options=", ".join(tr(s) for s in SHOW_SECTIONS)))
    t = float(_data(thickness).values)
    between = float(_data(gap).values or 0.0)
    deep = float(_data(depth).values)
    if not t > 0:
        raise ShapeError(tr('The thickness of the boards must be greater than zero.'))
    if between < 0:
        raise ShapeError(tr('The gap between boards cannot be negative.'))
    if not deep > 0:
        raise ShapeError(tr('The depth of the pieces must be greater than zero.'))
    if not isinstance(shape, Data) or shape.kind is None or shape.kind is POINT or shape.kind.curve:
        raise ShapeError(tr('“shape” must be a surface, a mesh or a body: what is cut into sections.'))

    triangles = _triangles(_fine(shape))
    points = triangles.reshape(-1, 3)
    planes = _planes(cuts, points, t, between, count, shape, guide)
    # Along a curve, each plane may also cut other parts of the shape, far from the guide: only what is near it stays.
    reach = 0.3 * float(np.ptp(points, axis=0).max()) if cuts == 'along a curve' else None
    size = float(np.ptp(points, axis=0).max())
    joint = size * 1e-7                            # segments of a cut join when their ends are this close
    tol = size * 1e-5                              # points closer than this are one (a hundredth of a mm in 1 m)
    lowest = float(points[:, 2].min()) - deep                        # (for «to base»: under the lowest point)
    vertical = cuts != 'z'                         # the planes stand up: «under» is down along v

    # A plane right through a row of vertices gives repeated segments (a spike in the outline): each cut goes a
    # negligible amount aside (a millionth of the size), so it never falls exactly on the vertices.
    nudge = size * 1e-6 * 0.6180339887
    pieces, normals = [], []
    for normal, origin, u, v in planes:
        runs = _cut(triangles, normal, float(normal @ origin) + nudge)
        loops = _chain(runs, joint) if len(runs) else []
        if not loops:
            continue
        closed, open_ = [], []
        base = lowest - origin @ v
        for c in loops:
            uv = np.stack([(c - origin) @ u, (c - origin) @ v], axis=1)
            if len(c) > 2 and np.linalg.norm(c[0] - c[-1]) <= size * 1e-4:
                closed.append(_without_repeats(uv, tol))
                continue
            uv = _without_reversals(_without_repeats(uv, tol))
            if len(uv) < 2:
                continue
            open_ += _to_base_rings(uv, base) if piece == 'to base' and vertical else \
                _band_rings(uv, deep, downwards=vertical)
        for outer, holes in _clean_pieces(closed, open_):
            if reach is not None and not _inside(np.zeros((1, 2)), outer)[0] and \
                    _distance_to(np.zeros((1, 2)), outer)[0] > reach:
                continue
            pieces.append([origin + np.outer(r[:, 0], u) + np.outer(r[:, 1], v) for r in [outer] + holes])
            normals.append(normal)
    if not pieces:
        raise ShapeError(tr('No section touches “{name}”.').format(name=shape._name()))
    if show == 'outlines':
        return _pieces_table(pieces, "section", name)
    boards = _boards(pieces, normals, t, name)
    boards.outlines = _pieces_table(pieces, "section", name)     # for Slots and Lay flat, if the boards go to them
    return boards


def _clean_pieces(closed: list[np.ndarray], open_: list[np.ndarray]) -> list[tuple[np.ndarray, list[np.ndarray]]]:
    """The pieces of one section: the loops a closed body leaves (nested: holes, filled by turns) and the pieces of
    the bands or bases of an open one (joined), cleaned; each piece as (its outline, its holes), the largest first."""
    from manifold3d import CrossSection, FillRule, JoinType
    region = CrossSection()
    rings = [np.asarray(c, float) for c in closed if len(c) >= 3]
    if rings:
        region = region + CrossSection([r * _MM for r in rings], FillRule.EvenOdd)
    parts = [np.asarray(c, float) for c in open_ if len(c) >= 3]
    if parts:
        joined = CrossSection([(r if _area(r) >= 0 else r[::-1]) * _MM for r in parts], FillRule.Positive)
        if len(parts) > 1:
            # Pieces side by side leave hairline slits between them (rounding): out and back in by a thousandth of a
            # millimetre closes them, and the outline does not touch itself.
            joined = joined.offset(1e-3, JoinType.Miter, 4.0).offset(-1e-3, JoinType.Miter, 4.0)
        region = region + joined
    out = []
    for part in region.decompose():
        polygons = [_ring_without_repeats(np.asarray(q, float) / _MM) for q in part.to_polygons()]
        outers = [q for q in polygons if _area(q) > 0]
        if not outers:
            continue
        outer = max(outers, key=_area)
        holes = [q[::-1] for q in polygons if _area(q) < 0 and abs(_area(q)) > 1e-4 * _area(outer)]
        out.append((outer, holes))
    out.sort(key=lambda piece: _area(piece[0]), reverse=True)
    return [p for p in out if _area(p[0]) > 1e-4 * _area(out[0][0])] if out else []


def _pieces_table(pieces: list[list[np.ndarray]], level: str, name: str | None, starts: dict | None = None) -> Data:
    """Pieces (each a list of closed rings in 3D: its outline, then its holes) as a table of closed curves: one level
    (`level`) if none has holes; with holes, a second level «contour» that changes from one piece to the next."""
    closed = [[np.vstack([r, r[:1]]) if not np.allclose(r[0], r[-1]) else r for r in piece] for piece in pieces]
    starts = {level: 1} if starts is None else starts
    if all(len(piece) == 1 for piece in closed):
        return Data(_padded([piece[0] for piece in closed]), (level,), name, starts=starts, kind=CLOSED_CURVE)
    contours = max(len(piece) for piece in closed)
    points = max(len(r) for piece in closed for r in piece)
    table = np.zeros((len(closed), contours, points, 3))
    for i, piece in enumerate(closed):
        for k in range(contours):
            r = piece[min(k, len(piece) - 1)]
            table[i, k] = np.vstack([r, np.repeat(r[-1:], points - len(r), axis=0)])
    counts = Data(np.array([len(piece) for piece in closed]), (level,))
    return Data(table, (level, "contour"), name, {"contour": counts}, starts, kind=CLOSED_CURVE)


def _groups(data: Data) -> list[tuple[tuple, list[np.ndarray]]]:
    """The pieces of a table of closed curves: (its place in the levels, its rings: the outline, then its holes). A
    last level «contour» gathers the outline and holes of one piece."""
    values = np.asarray(data.values, float)
    shape = values.shape[:len(data.levels)]
    mask = np.broadcast_to(data.mask, shape) if data.levels else np.ones((), bool)
    holes_level = bool(data.levels) and data.levels[-1] == "contour"
    out: dict = {}
    for index in np.ndindex(shape):
        if not mask[index]:
            continue
        ring = _closed_ring(values[index], 1e-12)
        if len(ring) < 3:
            continue
        key = index[:-1] if holes_level else index
        out.setdefault(key, []).append(ring)
    return list(out.items())


def _frame(normal: np.ndarray) -> np.ndarray:
    """Two axes (u, v) of a plane with u × v = its normal: the second one as near the vertical as possible."""
    n = normal / np.linalg.norm(normal)
    up = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    v = up - n * (up @ n)
    v /= np.linalg.norm(v)
    return np.stack([np.cross(v, n), v])


def _boards(pieces: list, normals: list[np.ndarray], t: float, name: str | None) -> Data:
    """The boards with their thickness, to see them: each piece (its outline, or a list: the outline and its holes)
    triangulated in its plane, its two faces and its edges, all in one mesh (each board has its own shape, so they
    cannot share a table of faces)."""
    from manifold3d import triangulate
    from .meshes import kind_mesh
    vertices, faces = [], []
    for piece, normal in zip(pieces, normals):
        rings = [piece] if isinstance(piece, np.ndarray) else list(piece)
        n_ = normal / np.linalg.norm(normal)
        axes = _frame(n_)
        centre = rings[0].mean(axis=0) @ axes.T
        flat, solid = [], []
        for k, r in enumerate(rings):
            r = r[:-1] if len(r) > 3 and np.allclose(r[0], r[-1]) else r
            uv = r @ axes.T
            if (_area(uv) < 0) == (k == 0):                    # the outline anticlockwise, the holes clockwise
                r, uv = r[::-1], uv[::-1]
            flat.append(uv - centre)
            solid.append(r)
        base = sum(len(v) for v in vertices)
        ring_all = np.vstack(solid)
        m = len(ring_all)
        vertices += [ring_all - n_ * t / 2, ring_all + n_ * t / 2]
        tris = np.asarray(triangulate([q * _MM for q in flat]), dtype=np.int64)
        faces += [tuple(base + m + i for i in tri) for tri in tris]               # the face towards the normal
        faces += [tuple(base + i for i in tri[::-1]) for tri in tris]             # the other one
        offset = 0
        for r in solid:                                                            # the edges, round each contour
            n = len(r)
            faces += [(base + offset + i, base + offset + (i + 1) % n, base + m + offset + (i + 1) % n,
                       base + m + offset + i) for i in range(n)]
            offset += n
    result = Data(np.vstack(vertices), (), name, kind=kind_mesh(faces))
    result.topology = False                          # the view draws its outlines, not its triangles
    return result


# --- Lay flat on sheets ---------------------------------------------------------------------------------------------

#: What Lay flat shows: the pieces to cut, their numbers to engrave, or the sheets.
SHOW_SHEETS = ('pieces', 'numbers', 'sheets')

#: How Lay flat places them: fitted into one another (in the holes and hollows of the others), or in rows.
NESTING = ('fit together', 'in rows')


class Layout:
    """How the pieces went onto the sheets (for the panel and the cutting file)."""

    def __init__(self, sheet: tuple[float, float], boxes: list[tuple[float, float, float, float]], used: float,
                 count: int, unnumbered: list[str]):
        self.sheet = sheet                  # width × height of a sheet
        self.boxes = boxes                  # each sheet: x0, y0, x1, y1, where it lies in the drawing
        self.used = used                    # how much of the sheets the pieces take (0 to 1)
        self.count = count                  # how many pieces
        self.unnumbered = unnumbered        # pieces too small for their number


def _flat_outlines(data: Data) -> Data:
    """A flat surface or mesh (an unrolled net, some plates) as the outlines of its pieces: the faces of each plane
    joined, each separate region a piece (outline, then holes). Faces in too many planes are not flat pieces."""
    from manifold3d import CrossSection, FillRule, JoinType
    from .meshes import _triangles
    tris = _triangles(data)
    normal = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    size = np.linalg.norm(normal, axis=1)
    keep = size > 1e-14 * max(float(size.max(initial=0.0)), 1e-300)
    tris, normal = tris[keep], normal[keep] / size[keep][:, None]
    flip = np.where(np.abs(normal[:, 2]) > 1e-6, normal[:, 2] < 0,
                    np.where(np.abs(normal[:, 0]) > 1e-6, normal[:, 0] < 0, normal[:, 1] < 0))
    normal[flip] *= -1
    level = np.einsum("ij,ij->i", normal, tris[:, 0])
    extent = float(np.ptp(tris.reshape(-1, 3), axis=0).max()) or 1.0
    keys = np.column_stack([np.round(normal * 1e4), np.round(level / extent * 1e5)])
    planes, which = np.unique(keys, axis=0, return_inverse=True)
    if len(planes) > 100:
        raise ShapeError(tr('“{name}” is not made of flat pieces (its faces lie in {n} planes): unroll it first, '
                            'with Unroll (a Hypar gives its pieces open with show «flat piece»).').format(
                                name=data._name(), n=len(planes)))
    pieces = []
    for k in range(len(planes)):
        mine = tris[which.ravel() == k]
        n = normal[which.ravel() == k].mean(axis=0)
        n /= np.linalg.norm(n)
        axes = _frame(n)
        d = float(np.mean(mine.reshape(-1, 3) @ n))
        uv = mine @ axes.T
        turn = ((uv[:, 1, 0] - uv[:, 0, 0]) * (uv[:, 2, 1] - uv[:, 0, 1]) -
                (uv[:, 1, 1] - uv[:, 0, 1]) * (uv[:, 2, 0] - uv[:, 0, 0])) < 0
        uv[turn] = uv[turn][:, ::-1]
        region = CrossSection([t * _MM for t in uv], FillRule.NonZero)
        region = region.offset(1e-3, JoinType.Miter, 4.0).offset(-1e-3, JoinType.Miter, 4.0)   # no hairline seams
        for part in region.decompose():
            rings = sorted((np.asarray(r, float) / _MM for r in part.to_polygons() if len(r) >= 3),
                           key=lambda r: -abs(_area(r)))
            if rings:
                pieces.append([r @ axes + n * d for r in rings])
    if not pieces:
        raise ShapeError(tr('There are no pieces to lay flat.'))
    return _pieces_table(pieces, "piece", data.name)


def _faces_as_outlines(data):
    """A surface or a mesh with flat pieces: their outlines; anything else, as it is."""
    kind = getattr(data, "kind", None)
    if isinstance(data, Data) and kind is not None and kind.faces is not None and not kind.curve and \
            not (len(kind.faces) == 1 and not kind.polygon):
        return _flat_outlines(data)
    return data


def _pieces_2d(pieces: Data) -> list[tuple[str, tuple, list[np.ndarray]]]:
    """Each flat piece as (its number, its place in the levels, its rings in its own plane: outline, then holes)."""
    from .polygons import _plane_frame
    pieces = _faces_as_outlines(getattr(pieces, "outlines", pieces))   # boards of Sections, an unrolled net
    kind = getattr(pieces, "kind", None)
    if not isinstance(pieces, Data) or kind is None or kind is POINT:
        raise ShapeError(tr('“pieces” must be flat closed curves (the outlines of Sections, for example).'))
    if kind.faces is not None and len(kind.faces) == 1 and not kind.curve:     # a rectangle, a polygon: its outline
        values = np.asarray(pieces.values, float)[..., list(kind.faces[0]), :]
        pieces = Data(values, pieces.levels, pieces.name, pieces.variables, pieces.starts, CLOSED_CURVE, pieces.holes)
    elif not (kind.curve and kind.closed):
        raise ShapeError(tr('“pieces” must be flat closed curves (the outlines of Sections, for example).'))
    out = []
    for index, rings in _groups(pieces):
        size = float(np.ptp(rings[0], axis=0).max()) or 1.0
        origin, axes = _plane_frame(rings[0])
        normal = np.cross(axes[0], axes[1])
        if max(np.abs((r - origin) @ normal).max() for r in rings) > size * 1e-4:
            raise ShapeError(tr('Piece {n} is not flat: it cannot be laid on a sheet.').format(
                n=_number(pieces, index)))
        out.append((_number(pieces, index), index, [(r - origin) @ axes.T for r in rings]))
    if not out:
        raise ShapeError(tr('There are no pieces to lay flat.'))
    return out


def _number(data: Data, index: tuple) -> str:
    return "-".join(str(i + data.starts.get(n, 0)) for n, i in zip(data.levels, index)) or "1"


def _upright(rings: list[np.ndarray]) -> list[np.ndarray]:
    """A 2D piece (outline, holes) turned so the bounding rectangle of its outline is the smallest, lying (longer side
    along x), from (0, 0)."""
    from manifold3d import CrossSection
    p = rings[0]
    ring = p if _area(p) >= 0 else p[::-1]
    hull = np.asarray(CrossSection([ring * _MM]).hull().to_polygons()[0], float) / _MM
    best, angle = np.inf, 0.0
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):
        e = b - a
        if np.linalg.norm(e) == 0:
            continue
        t = -np.arctan2(e[1], e[0])
        c, s = np.cos(t), np.sin(t)
        r = hull @ np.array([[c, s], [-s, c]])
        area = np.ptp(r[:, 0]) * np.ptp(r[:, 1])
        if area < best:
            best, angle = area, t
    c, s = np.cos(angle), np.sin(angle)
    turn = np.array([[c, s], [-s, c]])
    q = ring @ turn
    if np.ptp(q[:, 1]) > np.ptp(q[:, 0]):
        turn = turn @ np.array([[0.0, 1.0], [-1.0, 0.0]])
    out = [r @ turn for r in [ring] + list(rings[1:])]
    low = out[0].min(axis=0)
    return [r - low for r in out]


def _inside(points: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Which points fall inside a closed 2D outline (even-odd)."""
    x, y = points[:, 0][:, None], points[:, 1][:, None]
    a, b = ring, np.roll(ring, -1, axis=0)
    crosses = ((a[:, 1] > y) != (b[:, 1] > y)) & \
        (x < (b[:, 0] - a[:, 0]) * (y - a[:, 1]) / np.where(b[:, 1] == a[:, 1], 1e-300, b[:, 1] - a[:, 1]) + a[:, 0])
    return crosses.sum(axis=1) % 2 == 1


def _distance_to(points: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """How far each point is from the outline."""
    a, b = ring, np.roll(ring, -1, axis=0)
    ab = b - a
    t = np.clip(np.einsum("pkj,kj->pk", points[:, None, :] - a[None], ab) / np.maximum((ab ** 2).sum(1), 1e-300),
                0, 1)
    nearest = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(points[:, None, :] - nearest, axis=2).min(axis=1)


def _label_place(rings: list[np.ndarray], text: str, height: float):
    """Where a number fits inside a piece (in its outline, not in its holes): (bottom-left corner, height), along x;
    or None if it does not fit even small."""
    from .strokes import text_width
    rings = [r[np.linspace(0, len(r) - 1, 160).astype(int)] if len(r) > 160 else r for r in rings]
    ring, holes = rings[0], rings[1:]

    def solid(points: np.ndarray) -> np.ndarray:
        inside = _inside(points, ring)
        for h in holes:
            inside &= ~_inside(points, h)
        return inside

    def room_at(points: np.ndarray) -> np.ndarray:
        return np.min([_distance_to(points, r) for r in rings], axis=0)

    low, high = ring.min(axis=0), ring.max(axis=0)
    span = high - low
    nx, ny = (40, max(6, int(40 * span[1] / max(span[0], 1e-12)))) if span[0] >= span[1] else \
        (max(6, int(40 * span[0] / max(span[1], 1e-12))), 40)
    gx, gy = np.meshgrid(np.linspace(low[0], high[0], nx + 2)[1:-1], np.linspace(low[1], high[1], ny + 2)[1:-1])
    candidates = np.stack([gx.ravel(), gy.ravel()], axis=1)
    candidates = candidates[solid(candidates)]
    if not len(candidates):
        return None
    room = room_at(candidates)
    order = np.argsort(-room)[:40]
    for h in (height, height * 0.75, height * 0.5, height * 0.35):
        w = text_width(text, h)
        for k in order:
            centre = candidates[k]
            corner = centre - [w / 2, h / 2]
            probe = corner + np.array([[0, 0], [w, 0], [w, h], [0, h], [w / 2, 0], [w / 2, h], [0, h / 2], [w, h / 2]])
            if solid(probe).all() and room_at(probe).min() > h * 0.15:
                return corner, h
    return None


def lay_flat(pieces: Data, width=0.6, height=0.4, spacing=0.004, margin=0.01, turn: bool = True, number=0.005,
             show: str = 'pieces', origin=(0.0, 0.0, 0.0), more=None, nesting: str = 'fit together',
             name: str | None = None) -> Data:
    """The flat pieces laid on sheets of `width` × `height`, to be cut (*nesting*), `spacing` from one another and
    `margin` from the edge of the sheet; the sheets side by side. `nesting`: «fit together» puts each piece, the
    biggest first, as far to the left as it fits (and then as low), turned a quarter at a time if `turn`, also inside
    the holes and hollows of the others; «in rows» turns each piece so it takes the least room, lying, and lays them
    in rows. Each piece carries its number (its place in the levels, as the 3D view numbers it), engraved inside it.
    `show`: the pieces (to cut), their numbers (to engrave) or the sheets. `origin`: where the corner of the first
    sheet goes (on the ground). `more`: a second family of pieces on the same sheets; then the numbers carry a letter
    (A3 for the first family, B3 for the second) and the pieces come out as one list."""
    from .geometry import _point
    pieces = _faces_as_outlines(getattr(pieces, "outlines", pieces))   # boards of Sections, an unrolled net
    more = _faces_as_outlines(getattr(more, "outlines", more)) if more is not None else None
    corner = np.asarray(_point(origin, "origin").values, float).reshape(-1, 3)[0][:2]
    from .geometry import RECTANGLE
    from .strokes import text_strokes
    if show not in SHOW_SHEETS:
        raise ShapeError(tr('“show” must be one of: {options}.').format(
            options=", ".join(tr(s) for s in SHOW_SHEETS)))
    if nesting not in NESTING:
        raise ShapeError(tr('“nesting” must be one of: {options}.').format(
            options=", ".join(tr(s) for s in NESTING)))
    W, H = float(_data(width).values), float(_data(height).values)
    gap, edge, text = float(_data(spacing).values), float(_data(margin).values), float(_data(number).values or 0)
    if not (W > 0 and H > 0):
        raise ShapeError(tr('The sheet must have a width and a height greater than zero.'))
    if gap < 0 or edge < 0:
        raise ShapeError(tr('The spacing and the margin cannot be negative.'))
    usable = (W - 2 * edge, H - 2 * edge)
    if usable[0] <= 0 or usable[1] <= 0:
        raise ShapeError(tr('The margin leaves no room on the sheet.'))
    import hashlib
    families = [("", pieces)] if more is None else [("A", pieces), ("B", more)]
    if more is not None and not isinstance(more, Data):
        raise ShapeError(tr('“pieces” must be flat closed curves (the outlines of Sections, for example).'))
    key = tuple((hashlib.sha1(np.ascontiguousarray(d.values, float).tobytes()).hexdigest(), d.levels,
                 tuple(sorted(d.starts.items()))) for _, d in families) + (W, H, gap, edge, bool(turn), text,
                                                                           tuple(corner), nesting)
    cached = _LAYOUTS.get(key)
    if cached is None:
        cached = _layout(families, W, H, gap, edge, turn, text, usable, corner, nesting)
        _LAYOUTS.clear()                              # (the last one is enough: the three views of one layout)
        _LAYOUTS[key] = cached
    outlines, numbers, layout = cached
    return _layout_view(pieces if more is None else None, outlines, numbers, layout, show, name)


_LAYOUTS: dict = {}


def _layout(families: list[tuple[str, Data]], W: float, H: float, gap: float, edge: float, turn: bool, text: float,
            usable, corner: np.ndarray, nesting: str = 'fit together'):
    """Where each piece goes, its number's strokes, and the summary (computed once for the three views)."""
    from .strokes import text_strokes
    from .values import text_length
    items = []
    every = [(prefix + label, (k, index), flat) for k, (prefix, data) in enumerate(families)
             for label, index, flat in _pieces_2d(data)]
    for label, index, flat in every:
        q = _upright(flat)
        w, h = np.ptp(q[0], axis=0)
        if w > usable[0] + 1e-12 or h > usable[1] + 1e-12:
            if turn and h <= usable[0] + 1e-12 and w <= usable[1] + 1e-12:
                q = [r @ np.array([[0.0, 1.0], [-1.0, 0.0]]) for r in q]
                low = q[0].min(axis=0)
                q = [r - low for r in q]
                w, h = h, w
            else:
                raise ShapeError(tr('Piece {n} measures {w} × {h} and does not fit on a sheet of {W} × {H} (with its '
                                    'margin): use larger sheets, or divide the piece.').format(
                    n=label, w=text_length(float(w)), h=text_length(float(h)), W=text_length(W),
                    H=text_length(H)))
        items.append([label, index, q, float(w), float(h)])
    if nesting == 'fit together':
        from .nesting import nest
        count, placed = nest(items, usable, gap, turn)
        for label, index, q, sheet, x, y in placed:
            if sheet is None:                        # it fits by its rectangle, not by its cells: a hair too tight
                w, h = np.ptp(q[0], axis=0)
                raise ShapeError(tr('Piece {n} measures {w} × {h} and does not fit on a sheet of {W} × {H} (with its '
                                    'margin): use larger sheets, or divide the piece.').format(
                    n=label, w=text_length(float(w)), h=text_length(float(h)), W=text_length(W),
                    H=text_length(H)))
        sheets_top = [0.0] * count
    else:
        placed, sheets_top = _in_rows(items, usable, gap)
    between = max(0.02, 0.1 * W)
    # Side by side; many of them (more than ten), in rows like a square, so they do not run off a hundred metres.
    per_row = len(sheets_top) if len(sheets_top) <= 10 else int(math.ceil(math.sqrt(len(sheets_top))))
    origins = [corner + [(k % per_row) * (W + between), (k // per_row) * (H + between)]
               for k in range(len(sheets_top))]
    boxes = [(o[0], o[1], o[0] + W, o[1] + H) for o in origins]
    outlines, numbers, unnumbered, labels = {}, [], [], []
    area = 0.0
    for label, index, q, sheet, x, y in placed:
        rings = [r + origins[sheet] + [edge + x, edge + y] for r in q]
        outlines[index] = rings
        area += abs(_area(rings[0])) - sum(abs(_area(r)) for r in rings[1:])
        if text > 0:
            spot = _label_place(rings, label, text)
            if spot is None:
                unnumbered.append(label)
            else:
                corner, h = spot
                numbers += [s + corner for s in text_strokes(label, h)]
                labels.append((label, corner, h, rings))
    layout = Layout((W, H), boxes, area / (len(boxes) * W * H), len(placed), unnumbered)
    layout.numbers = numbers                         # for Numbers and sheets
    layout.labels, layout.text = labels, text        # (where each number went: to write it in another style)
    return outlines, numbers, layout


def _in_rows(items: list, usable, gap: float):
    """By rows: the tallest first; each piece in the first row (of any sheet) where it fits, or a new row."""
    rows = []                                        # [sheet, y, row height, x used]
    sheets_top = []                                  # how far up each sheet is taken by its rows
    placed = []
    for label, index, q, w, h in sorted(items, key=lambda it: (-it[4], -it[3])):
        for row in rows:
            if h <= row[2] + 1e-12 and row[3] + w <= usable[0] + 1e-12:
                x, row[3] = row[3], row[3] + w + gap
                placed.append((label, index, q, row[0], x, row[1]))
                break
        else:
            sheet = next((k for k, top in enumerate(sheets_top) if top + h <= usable[1] + 1e-12), None)
            if sheet is None:
                sheets_top.append(0.0)
                sheet = len(sheets_top) - 1
            y = sheets_top[sheet]
            sheets_top[sheet] = y + h + gap
            rows.append([sheet, y, h, w + gap])
            placed.append((label, index, q, sheet, 0.0, y))
    return placed, sheets_top


#: What Numbers and sheets shows of a Lay flat.
SHOW_MARKS = ('numbers', 'sheets')


#: Which way the numbers of the pieces are read: along the sheet (its long side), or turned a quarter.
READINGS = ('along the sheet', 'turned a quarter')


#: The letters of the numbers of the pieces: the single-stroke one (plain, rounded) or an installed font.
NUMBER_LETTERS = ('plain', 'rounded', 'font')


def numbers_and_sheets(laid: Data, show: str = 'numbers', letter: str = 'plain', weight: str = 'single',
                       reading: str = 'along the sheet', font: str = "", name: str | None = None) -> Data:
    """Of the pieces laid by a Lay flat, their numbers (to engrave) or the outlines of the sheets: they always follow
    the pieces, whatever the Lay flat is set to. The numbers, in a letter (plain, rounded, or an installed `font`: its
    outlines, to engrave them filled), a weight (single: one pass; bold: two; outline: to engrave them filled) and a
    way of reading them."""
    from .strokes import WEIGHTS
    layout = getattr(laid, "layout", None)
    if layout is None or not hasattr(layout, "numbers"):
        raise ShapeError(tr('“laid” must come from a Lay flat.'))
    for value, options, what in ((show, SHOW_MARKS, 'show'), (letter, NUMBER_LETTERS, 'lettering'),
                                 (weight, WEIGHTS, 'weight'), (reading, READINGS, 'reading')):
        if value not in options:
            raise ShapeError(tr('“{input}” must be one of: {options}.').format(
                input=tr(what), options=", ".join(tr(o) for o in options)))
    numbers = layout.numbers
    if show == 'numbers' and (letter, weight, reading) != ('plain', 'single', 'along the sheet'):
        numbers = _styled_numbers(layout, letter, weight, reading, str(font or ""))
    return _layout_view(None, {}, numbers, layout, show, name)


def _number_shapes(label: str, h: float, letter: str, weight: str, font: str) -> list[np.ndarray]:
    """The lines of one number from (0, 0), `h` tall. In a font, its outlines fit the room of the single-stroke
    number (narrower if the font is wider, centred in it): it keeps fitting in its piece."""
    from .strokes import styled, text_strokes, text_width
    if letter != 'font':
        return styled(text_strokes(label, h), h, letter, weight)
    from .fonts import outlines
    rings, wide = outlines(label, font, h)
    room = text_width(label, h)
    k = min(1.0, room / wide) if wide > 0 else 1.0
    shift = np.array([(room - wide * k) / 2, (h - h * k) / 2])
    return [r * k + shift for r in rings]


def _styled_numbers(layout, letter: str, weight: str, reading: str, font: str = "") -> list[np.ndarray]:
    """The numbers of the pieces again, in another letter, weight or way of reading (turned: where it fits, the
    other way round inside the piece; if it does not fit so, as before)."""
    # Turned, it is read from the right of the sheet (as a drawing's vertical texts): the piece is turned a quarter
    # clockwise, the number placed in it as usual, and both turned back.
    quarter = np.array([[0.0, -1.0], [1.0, 0.0]])        # (row vectors: p @ quarter turns it clockwise)
    out = []
    for label, corner, h, rings in getattr(layout, "labels", []):
        turned = None
        if reading == 'turned a quarter':
            spot = _label_place([r @ quarter for r in rings], label, layout.text)
            if spot is not None:
                turned = spot
        if turned is None:
            out += [s + corner for s in _number_shapes(label, h, letter, weight, font)]
        else:
            at, size = turned
            out += [(s + at) @ quarter.T for s in _number_shapes(label, size, letter, weight, font)]
    return out


def _layout_view(pieces: Data, outlines: dict, numbers: list, layout: Layout, show: str, name: str | None) -> Data:
    from .geometry import RECTANGLE
    boxes = layout.boxes
    if show == 'sheets':
        corners = np.array([[[b[0], b[1], 0], [b[2], b[1], 0], [b[2], b[3], 0], [b[0], b[3], 0]] for b in boxes])
        result = Data(corners, ("sheet",), name, starts={"sheet": 1}, kind=RECTANGLE)
        result.operation = 'sheet'
        result.colour, result.opacity = "#d8c3a5", 0.35
    elif show == 'numbers':
        strokes = [np.column_stack([s, np.zeros(len(s))]) for s in numbers] or [np.zeros((2, 3))]
        result = Data(_padded(strokes), ("stroke",), name, kind=CURVE)
        result.operation = 'engrave'
        result.colour = "#2f5fd0"
    else:
        ordered = sorted(outlines.items(), key=lambda kv: kv[0])
        flat3d = [[np.column_stack([r, np.zeros(len(r))]) for r in rings] for _, rings in ordered]
        leading = [lv for lv in pieces.levels if lv != "contour"] if pieces is not None else []
        if pieces is not None and len(leading) == 1:
            result = _pieces_table(flat3d, leading[0], name,
                                   {k: v for k, v in pieces.starts.items() if k == leading[0]})
        else:                                        # two families, or no levels: one list, in order
            result = _pieces_table(flat3d, "piece", name)
        result.operation = 'cut'
        result.colour = "#e0302a"
    result.layout = layout
    return result


# --- Slots: two families of boards that cross ---------------------------------------------------------------------

#: Which family is slotted from above (the other, from below).
SLOTTED_FROM = ('first from above', 'first from below')
#: What Slots shows: each family with its slots, or all the boards with their thickness.
SHOW_SLOTS = ('first', 'second', 'boards')


def _rings_of(data: Data, what: str) -> list[tuple[tuple, list[np.ndarray], np.ndarray]]:
    """Each flat piece as (its place in the levels, its rings in 3D: outline then holes, the normal of its plane)."""
    from .polygons import _plane_frame
    data = _faces_as_outlines(getattr(data, "outlines", data))   # boards of Sections, an unrolled net
    kind = getattr(data, "kind", None)
    if isinstance(data, Data) and kind is not None and kind.faces is not None and len(kind.faces) == 1 \
            and not kind.curve:                           # a rectangle, a polygon: its outline
        values = np.asarray(data.values, float)[..., list(kind.faces[0]), :]
        data = Data(values, data.levels, data.name, data.variables, data.starts, CLOSED_CURVE, data.holes)
    elif not isinstance(data, Data) or kind is None or not (kind.curve and kind.closed):
        raise ShapeError(tr('“{what}” must be flat closed outlines (the outlines of Sections, for example).').format(
            what=tr(what)))
    out = []
    for index, rings in _groups(data):
        origin, axes = _plane_frame(rings[0])
        out.append((index, rings, np.cross(axes[0], axes[1])))
    return out


def _line_inside(rings: list[np.ndarray], normal: np.ndarray, p0: np.ndarray, d: np.ndarray) -> list[tuple[float, float]]:
    """Where the line p0 + t·d (lying in the plane of the piece) is inside the piece (its outline, minus its holes):
    intervals of t."""
    axes = _frame(normal)
    dd = axes @ d                                        # the line in the plane: through (0, 0), along dd
    hits = []
    for ring in rings:
        uv = (ring - p0) @ axes.T
        side = uv[:, 0] * dd[1] - uv[:, 1] * dd[0]       # which side of the line each vertex is
        a, b = side, np.roll(side, -1)
        crossing = (a > 0) != (b > 0)
        f = a[crossing] / (a[crossing] - b[crossing])
        pa, pb = uv[crossing], np.roll(uv, -1, axis=0)[crossing]
        hits.append(((pa + (pb - pa) * f[:, None]) @ dd) / (dd @ dd))
    t = np.sort(np.concatenate(hits)) if hits else np.zeros(0)
    return [(t[k], t[k + 1]) for k in range(0, len(t) - 1, 2)]


def _overlaps(first: list, second: list) -> list[tuple[float, float]]:
    out = []
    for a0, a1 in first:
        for b0, b1 in second:
            lo, hi = max(a0, b0), min(a1, b1)
            if hi > lo:
                out.append((lo, hi))
    return out


def slots(first: Data, second: Data, thickness=0.003, clearance=0.0002, slotted: str = 'first from above',
          show: str = 'first', towards=None, name: str | None = None) -> Data:
    """Two families of flat boards that cross (*waffle*), with a slot where each pair meets: halfway along their
    crossing, one board slotted from one end and the other from the other, as wide as the board that goes in (its
    `thickness`, wider if they do not cross square) plus a `clearance`. The first family is slotted from above (or from
    below), the second from the other side; when their crossing is level (the rings and ribs of a lamp), «above» is
    away from the centre of the shape: the first family is slotted from its outer edge. `towards` (a vector) says
    which way is «above» instead: a wall's front, so that «first from below» slots the first family from the back."""
    if slotted not in SLOTTED_FROM:
        raise ShapeError(tr('“slotted” must be one of: {options}.').format(
            options=", ".join(tr(o) for o in SLOTTED_FROM)))
    if show not in SHOW_SLOTS:
        raise ShapeError(tr('“show” must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW_SLOTS)))
    t = float(_data(thickness).values)
    gap = float(_data(clearance).values or 0.0)
    if not t > 0:
        raise ShapeError(tr('The thickness of the boards must be greater than zero.'))
    if gap < 0:
        raise ShapeError(tr('The clearance cannot be negative.'))
    A, B = _rings_of(first, 'first'), _rings_of(second, 'second')
    if not A or not B:
        raise ShapeError(tr('Slots need two families of boards that cross.'))
    boxes_a = np.array([np.r_[r[0].min(axis=0) - t, r[0].max(axis=0) + t] for _, r, _ in A])
    boxes_b = np.array([np.r_[r[0].min(axis=0) - t, r[0].max(axis=0) + t] for _, r, _ in B])
    touch = np.all((boxes_a[:, None, :3] <= boxes_b[None, :, 3:]) & (boxes_b[None, :, :3] <= boxes_a[:, None, 3:]),
                   axis=2)
    centre = np.vstack([r[0] for _, r, _ in A + B]).mean(axis=0)     # (for level crossings: «above» is outwards)
    cut_a = {k: [] for k in range(len(A))}
    cut_b = {k: [] for k in range(len(B))}
    from_above = slotted == 'first from above'
    crossings = []                                         # (i, j, a point on both planes, direction, sine)
    for i, j in zip(*np.nonzero(touch)):
        _, ra, na = A[i]
        _, rb, nb = B[j]
        d = np.cross(na, nb)
        sine = np.linalg.norm(d)
        if sine < 1e-6:                                    # parallel: they do not cross
            continue
        d /= sine
        # A point on both planes: the nearest to the centre of the first board.
        ca, cb = ra[0].mean(axis=0), rb[0].mean(axis=0)
        p0 = np.linalg.solve(np.array([na, nb, d]), [na @ ca, nb @ cb, d @ ca])
        crossings.append((i, j, p0, d, sine))
    # Which way is «above», the same for every crossing, so each board has its slots on one edge only (if not, it
    # could not be put in): if the crossings all run about the same way (a waffle, a leaning column), that common
    # way, upwards; if they spread out (the rings and ribs of a lamp), away from the centre of the shape.
    common = None
    if towards is not None:
        from .geometry import _point
        common = np.asarray(_point(towards, "towards").values, float).reshape(-1, 3)[0]
        if np.linalg.norm(common) < 1e-12:
            raise ShapeError(tr('«towards» cannot be zero.'))
        common = common / np.linalg.norm(common)
    elif crossings:
        directions = np.array([c[3] for c in crossings])
        values, vectors = np.linalg.eigh(directions.T @ directions)
        if values[-1] >= 0.75 * values.sum():
            common = vectors[:, -1]
            z = common @ np.array([0.0, 0.0, 1.0])
            if z < -1e-6 or (abs(z) <= 1e-6 and (np.mean([c[2] for c in crossings], axis=0) - centre) @ common < 0):
                common = -common
    for i, j, p0, d, sine in crossings:
        _, ra, na = A[i]
        _, rb, nb = B[j]
        if common is not None and d @ common < 0:
            d = -d
        for t0, t1 in _overlaps(_line_inside(ra, na, p0, d), _line_inside(rb, nb, p0, d)):
            middle = (t0 + t1) / 2
            along = d
            if common is None and (p0 + d * middle - centre) @ d < 0:     # «above» is away from the centre
                along, t0, t1, middle = -d, -t1, -t0, -middle
            beyond = (t1 - t0) + 2 * t                       # past the edge, so the slot opens cleanly
            # Each slot a little past the middle (half the clearance): the boards seat flush, without touching there.
            upper, lower = (middle - gap / 2, t1 + beyond), (t0 - beyond, middle + gap / 2)
            a_part, b_part = (upper, lower) if from_above else (lower, upper)
            width = t / sine + gap
            cut_a[i].append((p0, along, a_part, width, na))
            cut_b[j].append((p0, along, b_part, width, nb))
    if show == 'boards':
        pieces = [_slotted(r, n, cut_a[k]) for k, (_, r, n) in enumerate(A)] + \
            [_slotted(r, n, cut_b[k]) for k, (_, r, n) in enumerate(B)]
        normals = [n for _, _, n in A] + [n for _, _, n in B]
        return _boards(pieces, normals, t, name)
    family, cuts, data = (A, cut_a, first) if show == 'first' else (B, cut_b, second)
    pieces = [_slotted(r, n, cuts[k]) for k, (_, r, n) in enumerate(family)]
    leading = [lv for lv in data.levels if lv != "contour"]
    if len(leading) == 1:
        return _pieces_table(pieces, leading[0], name, {k: v for k, v in data.starts.items() if k == leading[0]})
    return _pieces_table(pieces, "board", name)


def _slotted(rings: list[np.ndarray], normal: np.ndarray, cuts: list) -> list[np.ndarray]:
    """A board's rings (outline, holes) with its slots taken out (in its own plane, with the 2D library)."""
    if not cuts:
        return rings
    from manifold3d import CrossSection, FillRule
    axes = _frame(normal)
    origin = rings[0].mean(axis=0)
    flat = [(r - origin) @ axes.T for r in rings]
    piece = CrossSection([f * _MM for f in flat], FillRule.EvenOdd)
    rects = []
    for p0, d, (s0, s1), width, n in cuts:
        across = np.cross(n, d)
        across /= np.linalg.norm(across)
        corners = [p0 + d * s0 - across * width / 2, p0 + d * s1 - across * width / 2,
                   p0 + d * s1 + across * width / 2, p0 + d * s0 + across * width / 2]
        q = (np.array(corners) - origin) @ axes.T
        rects.append(q if _area(q) > 0 else q[::-1])
    piece = piece - CrossSection([r * _MM for r in rects])
    parts = sorted(piece.decompose(), key=lambda c: c.area(), reverse=True)
    if not parts:
        return rings
    polygons = [_ring_without_repeats(np.asarray(q, float) / _MM) for q in parts[0].to_polygons()]
    outers = [q for q in polygons if _area(q) > 0]
    if not outers:
        return rings
    outer = max(outers, key=_area)
    holes = [q[::-1] for q in polygons if _area(q) < 0]
    return [origin + q @ axes for q in [outer] + holes]
