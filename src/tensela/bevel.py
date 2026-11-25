"""Bevel: the edges of flat boards eased, with a chamfer, rounded, a cove, a few facets or a profile of one's own.

A board is built in layers: at each point of the profile, the outline of the piece inset by so much (with the 2D
library, so holes, slots and narrow parts behave), at its height. Between two layers, the band between their outlines
is triangulated in plan and lifted, each point to the height of its layer: seen from above it never folds over
itself, so the board is always closed, whatever the shape of the piece. Where a narrow part has no room for the whole
bevel, it is simply flat at the height where it ends."""
import numpy as np

from .data import Data, ShapeError
from .language import tr
from .geometry import _data

#: The shape of the bevel, seen on the corner of the board from its side.
PROFILES = ('rounded', 'chamfer', 'cove', 'custom')
#: Which faces of the board get it.
FACES = ('both faces', 'top face', 'bottom face')

_MM = 1000.0


def profile_points(profile: str, segments: int = 4, curve=None) -> np.ndarray:
    """The profile as points (u, v), from the face to the side: u, how far in from the side (1 → 0); v, how far down
    from the face (0 → 1), both as fractions of the bevel."""
    if profile == 'chamfer':
        return np.array([[1.0, 0.0], [0.0, 1.0]])
    if profile in ('rounded', 'cove'):
        a = np.linspace(0, np.pi / 2, max(1, int(segments)) + 1)
        if profile == 'rounded':                     # convex: a quarter circle around the inner corner
            return np.column_stack([1 - np.sin(a), 1 - np.cos(a)])
        return np.column_stack([np.cos(a), np.sin(a)])  # concave: around the outer corner
    if profile == 'custom':
        return _from_curve(curve)
    raise ShapeError(tr('“profile” must be one of: {options}.').format(options=", ".join(tr(p) for p in PROFILES)))


def _from_curve(curve) -> np.ndarray:
    """A drawn profile: like the corner of the board seen from its side, from the top face (left, high) down to the
    edge (right, low). Its bounding box becomes the bevel; it is made to go always in and down."""
    from .geometry import POINT
    from .polygons import _plane_frame
    kind = getattr(curve, "kind", None)
    if not isinstance(curve, Data) or kind is None or kind is POINT or not kind.curve:
        raise ShapeError(tr('With the profile «custom», “curve” must be a curve: the corner of the board seen from '
                            'its side, from the top face (left) down to the edge (right).'))
    p = np.asarray(curve.values, float).reshape(-1, 3)
    p = p[np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12]]
    if len(p) < 2:
        raise ShapeError(tr('The profile curve needs at least two different points.'))
    if np.ptp(p[:, 2]) < 1e-9 * max(np.ptp(p, axis=0).max(), 1e-12):
        xy = p[:, :2]                                # drawn in plan: as it is
    else:
        origin, axes = _plane_frame(p)
        xy = (p - origin) @ axes.T
    span = np.ptp(xy, axis=0)
    if span.min() <= 1e-12:
        raise ShapeError(tr('The profile curve must have a width and a height (it is the bevel seen from its side).'))
    x, y = ((xy - xy.min(axis=0)) / span).T
    if (x[0] - y[0]) > (x[-1] - y[-1]):              # it starts at the edge: turned round
        x, y = x[::-1], y[::-1]
    u = np.minimum.accumulate(1 - x)                 # always in (towards the side) and down
    v = np.maximum.accumulate(1 - y)
    out = np.column_stack([u, v])
    out = np.vstack([[1.0, 0.0], out, [0.0, 1.0]])
    keep = np.r_[True, np.linalg.norm(np.diff(out, axis=0), axis=1) > 1e-9]
    return out[keep]


def _top(n: np.ndarray) -> np.ndarray:
    """The normal turned to the «top» face: looking up; an upright board, towards +x (or +y)."""
    for axis in (2, 0, 1):
        if abs(n[axis]) > 1e-6:
            return n if n[axis] > 0 else -n
    return n


def _layers(profile: np.ndarray, t: float, b: float, faces: str) -> list[tuple[float, float]]:
    """(height from the middle, inset) of each layer, from the top face down to the bottom one."""
    top = [(t / 2 - v * b, u * b) for u, v in profile] if faces in ('both faces', 'top face') else [(t / 2, 0.0)]
    bottom = [(-t / 2 + v * b, u * b) for u, v in profile][::-1] if faces in ('both faces', 'bottom face') \
        else [(-t / 2, 0.0)]
    return top + bottom


def _inset(region, d: float) -> list[np.ndarray]:
    from manifold3d import JoinType
    if d > 1e-12:                                    # a rounding of 0 (cos 90°) is not an inset
        region = region.offset(-d * _MM, JoinType.Miter, 8.0)
    return [np.asarray(p, float) / _MM for p in region.to_polygons() if len(p) >= 3]


def _simplified(ring: np.ndarray, tolerance: float) -> np.ndarray:
    """The ring without points that add nothing (repeated, or less than `tolerance` off the line of their neighbours),
    so its corners can be inset one by one."""
    r = ring
    for _ in range(20):
        if len(r) <= 3:
            return r
        a, b = np.roll(r, 1, axis=0), np.roll(r, -1, axis=0)
        ab = b - a
        length = np.linalg.norm(ab, axis=1)
        off = np.abs(ab[:, 0] * (r - a)[:, 1] - ab[:, 1] * (r - a)[:, 0]) / np.maximum(length, 1e-300)
        idle = (off < tolerance) | (np.linalg.norm(r - a, axis=1) < tolerance)
        idle &= ~np.roll(idle, 1)                    # never two neighbours at once
        if not idle.any():
            return r
        r = r[~idle]
    return r


def _miters(flat: list[np.ndarray], deepest: float, tolerance: float):
    """Each corner moved along its bisector (the miter): (rings, their miter vectors) so that ring + d · miter is the
    piece inset by d, corner by corner, every edge parallel to its own. None where that does not hold up to `deepest`
    (a corner too sharp, an edge that would vanish, a narrow part that would cross itself)."""
    from manifold3d import CrossSection, FillRule
    from .fabrication import _area
    rings, miters = [], []
    for k, r in enumerate(flat):
        r = _simplified(r, tolerance)
        if len(r) < 3:
            return None
        if (_area(r) < 0) == (k == 0):               # the outline anticlockwise, the holes clockwise
            r = r[::-1]
        e = np.roll(r, -1, axis=0) - r
        length = np.linalg.norm(e, axis=1)
        if (length < 1e-12).any():
            return None
        t = e / length[:, None]
        left = np.column_stack([-t[:, 1], t[:, 0]])  # into the solid, for the outline and for the holes alike
        before = np.roll(left, 1, axis=0)
        cosine = np.sum(before * left, axis=1)
        if (cosine < -0.9).any():                    # a corner sharper than about 25°
            return None
        m = (before + left) / (1 + cosine)[:, None]
        rings.append(r)
        miters.append(m)
    deep = [r + deepest * m for r, m in zip(rings, miters)]
    for r, q in zip(rings, deep):
        if (np.sum((np.roll(q, -1, axis=0) - q) * (np.roll(r, -1, axis=0) - r), axis=1) <= 0).any():
            return None                              # an edge turned round: it vanished on the way
    signed = sum(_area(q) for q in deep)
    real = CrossSection([q * _MM for q in deep], FillRule.Positive).area() / _MM ** 2
    if signed <= 0 or abs(real - signed) > 1e-4 * abs(signed):
        return None                                  # it crosses itself
    return rings, miters


def _sewn(above: list[np.ndarray], ids_above: list, below: list[np.ndarray], ids_below: list):
    """The band between two layers sewn ring to ring (each ring of one inside or around its own of the other),
    always by the shortest diagonal: faces that follow the edges, and a fan where a tip shortens. None if the
    rings do not pair one to one (a part that vanished, two holes that met)."""
    from .fabrication import _inside
    if len(above) != len(below):
        return None
    pairs, used = [], set()
    for k, a in enumerate(above):
        mates = [m for m, b in enumerate(below) if m not in used and
                 (_inside(a[:1], b)[0] or _inside(b[:1], a)[0])]
        if len(mates) != 1:
            return None
        used.add(mates[0])
        pairs.append((k, mates[0]))
    from .fabrication import _area
    polygons = []
    for k, m in pairs:
        a, b, ia, ib = above[k], below[m], ids_above[k], ids_below[m]
        na, nb = len(a), len(b)
        plan = []
        j = int(np.argmin(np.linalg.norm(a - b[0], axis=1)))
        i, done_a, done_b = 0, 0, 0
        while done_a < na or done_b < nb:
            step_b = done_a >= na or (done_b < nb and np.linalg.norm(b[(i + 1) % nb] - a[j % na]) <=
                                      np.linalg.norm(b[i % nb] - a[(j + 1) % na]))
            if step_b:
                polygons.append((ib[i % nb], ib[(i + 1) % nb], ia[j % na]))
                plan.append((b[i % nb], b[(i + 1) % nb], a[j % na]))
                i, done_b = i + 1, done_b + 1
            else:
                polygons.append((ib[i % nb], ia[(j + 1) % na], ia[j % na]))
                plan.append((b[i % nb], a[(j + 1) % na], a[j % na]))
                j, done_a = j + 1, done_a + 1
        # Seen from above, the triangles must cover the band once: all turning the same way, adding up to it.
        t = np.asarray(plan)
        signed = 0.5 * ((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1]) -
                        (t[:, 1, 1] - t[:, 0, 1]) * (t[:, 2, 0] - t[:, 0, 0]))
        band = abs(abs(_area(b)) - abs(_area(a)))
        one_way = (signed > -1e-12 * band).all() or (signed < 1e-12 * band).all()
        if band <= 0 or not one_way or abs(np.abs(signed).sum() - band) > 1e-6 * band:
            return None
    return polygons


def bevel(pieces, thickness=0.003, size=0.001, profile: str = 'rounded', segments=4, curve=None,
          faces: str = 'both faces', name: str | None = None) -> Data:
    """Each flat piece as a board of `thickness` (centred on its plane, as Sections draws them) with its edges eased
    by `size`: `profile` rounded, chamfer, cove (concave) or custom (`curve`), with `segments` facets for the rounded
    and the cove (1: a chamfer; 2: octagonal); on `faces` both, the top or the bottom one. The outline in the middle
    of the board stays the piece's own, so it still lays flat and cuts the same."""
    from manifold3d import CrossSection, FillRule, triangulate
    from .fabrication import _area, _frame, _groups, _number, _rings_of
    from .meshes import kind_mesh
    t, b = float(_data(thickness).values), float(_data(size).values)
    n_segments = int(round(float(_data(segments).values)))
    if not t > 0:
        raise ShapeError(tr('The thickness must be greater than zero.'))
    if b < 0:
        raise ShapeError(tr('The bevel cannot be negative.'))
    if faces not in FACES:
        raise ShapeError(tr('“faces” must be one of: {options}.').format(options=", ".join(tr(f) for f in FACES)))
    if not 1 <= n_segments <= 32:
        raise ShapeError(tr('“segments” goes from 1 to 32.'))
    room = t / 2 if faces == 'both faces' else t
    if b >= room:
        raise ShapeError(tr('A bevel of {b} does not fit in a board of {t}: on both faces it must be less than half '
                            'the thickness; on one, less than the thickness.').format(
            b=_text(b), t=_text(t)))
    shape = profile_points(profile, n_segments, curve)
    layers = _layers(shape, t, b, faces) if b > 0 else [(t / 2, 0.0), (-t / 2, 0.0)]
    source = getattr(pieces, "outlines", pieces)
    vertices, polygons = [], []
    count = 0
    for index, rings, normal in _rings_of(source, 'pieces'):
        n = _top(normal / np.linalg.norm(normal))
        axes = _frame(n)
        level = float(rings[0][0] @ n)
        flat = []
        for k, r in enumerate(rings):
            r = r[:-1] if len(r) > 3 and np.allclose(r[0], r[-1]) else r
            flat.append(r @ axes.T)
        region = CrossSection([r * _MM for r in flat], FillRule.EvenOdd)
        if region.is_empty():
            continue
        # Corner by corner if it holds (clean flat facets, edge by edge); if not, with the 2D library.
        corners = _miters(flat, max(d for _, d in layers), min(b * 0.02, 5e-5) if b > 0 else 1e-7)
        per_layer = []
        for z, d in layers:
            rings_2d = [r + d * m for r, m in zip(*corners)] if corners is not None else _inset(region, d)
            if not rings_2d:
                raise ShapeError(tr('Piece {n} is too narrow for a bevel of {b}: make it smaller.').format(
                    n=_number(source, index) if hasattr(source, "levels") else index, b=_text(b)))
            ids = []
            for ring in rings_2d:
                points = ring @ axes + n * (level + z)
                ids.append(np.arange(count, count + len(ring)))
                vertices.append(points)
                count += len(ring)
            per_layer.append((rings_2d, ids, d))
        # The faces: the top one looking along the normal, the bottom one the other way.
        top_rings, top_ids, _ = per_layer[0]
        every = np.concatenate(top_ids)
        polygons += [tuple(every[i]) for i in np.asarray(triangulate([r * _MM for r in top_rings]), dtype=np.int64)]
        low_rings, low_ids, _ = per_layer[-1]
        every = np.concatenate(low_ids)
        polygons += [tuple(every[i[::-1]]) for i in
                     np.asarray(triangulate([r * _MM for r in low_rings]), dtype=np.int64)]
        # Between two layers: an upright wall if they are the same outline; if not, the band between them, lifted.
        for (rings_a, ids_a, d_a), (rings_b, ids_b, d_b) in zip(per_layer, per_layer[1:]):
            if corners is not None or (abs(d_a - d_b) < 1e-12
                                       and [len(r) for r in rings_a] == [len(r) for r in rings_b]):
                for ia, ib in zip(ids_a, ids_b):     # a is above b: an upright wall, or a facet of the bevel
                    m = len(ia)
                    polygons += [(ib[i], ib[(i + 1) % m], ia[(i + 1) % m], ia[i]) for i in range(m)]
                continue
            sewn = _sewn(rings_a, ids_a, rings_b, ids_b)
            if sewn is not None:
                polygons += sewn
                continue
            going_out = d_b < d_a                    # the upper bevel: the lower layer is the bigger one
            big_rings, big_ids, small_rings, small_ids = (rings_b, ids_b, rings_a, ids_a) if going_out else \
                (rings_a, ids_a, rings_b, ids_b)
            band = [r * _MM for r in big_rings] + [r[::-1] * _MM for r in small_rings]
            every = np.concatenate(list(big_ids) + [i[::-1] for i in small_ids])
            tris = np.asarray(triangulate(band), dtype=np.int64)
            # Seen from above, a band of the upper bevel faces up (as triangulated); one of the lower bevel, down.
            polygons += [tuple(every[i]) if going_out else tuple(every[i[::-1]]) for i in tris]
    if not vertices:
        raise ShapeError(tr('There are no pieces to bevel.'))
    result = Data(np.vstack(vertices), (), name, kind=kind_mesh(polygons))
    result.outlines = source if isinstance(source, Data) else None
    result.topology = False                          # the view draws its outlines, not its triangles
    return result


def _text(metres: float) -> str:
    from .values import text_length
    return text_length(metres)
