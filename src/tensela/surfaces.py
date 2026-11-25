"""Surfaces (challenge «Curves and surfaces»): NURBS by control points (S1), revolution and sweep (S2), by edges
(S3).

All give a surface like the others of the program: a grid of rows × columns of points (`geometry.kind_surface`), so
they are divided with Grid, thickened, cut into ribs and exported the same way. The closed ones repeat the seam (the
last row is the first).
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError, _number, _require_size_, apply, integer
from .geometry import (BLOCK, MAX_DEGREE_NURBS, POINT, _data, _base_bspline, _require_curve, _values_items, _point,
                        _without_padding, kind_surface)
from .language import tr

#: Samples per span between knots, in each direction (fewer on big surfaces: no more than about 160 rows).
SAMPLES_BY_RUN = 16
MAXIMUM_ROWS = 160


# --- S1 · Superficie NURBS ------------------------------------------------------------------

def _samples(knots: np.ndarray, from_: float, to: float, by_run: int, closed: bool) -> np.ndarray:
    cuts = np.unique(knots[(knots >= from_) & (knots <= to)])
    t = np.concatenate([np.linspace(a, b, by_run, endpoint=False) for a, b in zip(cuts[:-1], cuts[1:])])
    return np.append(t, to)                        # the last row (in a closed one, the seam: the first)


def base_in_a_direction(n: int, k: int, closed: bool) -> np.ndarray:
    """The basis functions of one direction of the surface (uniform knots; closed: periodic): a matrix (samples, n)
    that, by the control points of that direction, gives the points of the surface."""
    runs = n if closed else n - k
    by_run = max(4, min(SAMPLES_BY_RUN, MAXIMUM_ROWS // max(runs, 1)))
    if closed:                                       # periodic: the knots go on and the first k points repeat
        u = np.arange(n + 1, dtype=float)
        knots = np.concatenate([u[n - k:n] - n, u, u[1:k + 1] + n])
        indices = np.arange(n + k) % n
        t = _samples(knots, knots[k], knots[n + k], by_run, True)
    else:
        knots = np.concatenate([np.zeros(k + 1), np.linspace(0, 1, n - k + 1)[1:-1], np.ones(k + 1)])
        indices = np.arange(n)
        t = _samples(knots, 0.0, 1.0, by_run, False)
    base = _base_bspline(knots, k, t)
    if closed:                                       # the last parameter of a periodic one: outside its span
        base[-1] = base[0]
    full = np.zeros((len(t), n))
    for column, i in enumerate(indices):
        full[:, i] += base[:, column]
    return full


def surface_nurbs(points: Data, level_u: str | None = None, level_v: str | None = None, degree_u=3, degree_v=3,
                     weights=1.0, closed_u: bool = False, closed_v: bool = False, name: str | None = None) -> Data:
    """A NURBS surface (*Surface from control points*): a grid of control points (two levels: u and v) that attract
    it like magnets, with its degree in each direction (1: facets; 3: smooth), its weights (one for all, or one per
    point, row by row) and closed in u or in v (a tube; in both, a torus). With more levels, one for each."""
    if not isinstance(points, Data) or points.kind is not POINT:
        raise ShapeError(tr('«{name}» should be points (the control points, in rows × columns).').format(
            name=points._name() if isinstance(points, Data) else tr('points')))
    if len(points.levels) < 2:
        raise ShapeError(tr('For a NURBS surface, the control points need rows × columns: two levels (for '
                              'example, two Series with different names).'))
    level_u = level_u or points.levels[-2]
    level_v = level_v or points.levels[-1]
    for level in (level_u, level_v):
        if level not in points.levels:
            raise ShapeError(tr('«{level}» is not a level of «{name}» (its levels: {options}).').format(
                level=tr(level), name=points._name(), options=", ".join((tr(n) for n in points.levels))))
    if level_u == level_v:
        raise ShapeError(tr('u and v must be two different levels.'))
    if any(x in points.variables for x in (level_u, level_v)):
        raise ShapeError(tr('The rows of control points must all have the same length.'))
    v = np.moveaxis(np.asarray(points.values, dtype=float),
                    [points.levels.index(level_u), points.levels.index(level_v)], [-3, -2])
    nu, nv = v.shape[-3], v.shape[-2]
    for n, closed, what in ((nu, closed_u, "u"), (nv, closed_v, "v")):
        if n < (3 if closed else 2):
            raise ShapeError(tr('In {what} at least {m} control points are needed.').format(
                what=what, m=3 if closed else 2))
    ku = max(1, min(integer(degree_u), MAX_DEGREE_NURBS, nu - 1))
    kv = max(1, min(integer(degree_v), MAX_DEGREE_NURBS, nv - 1))
    w = _values_items(weights, "weights")
    if len(w) == 1:
        w = np.full((nu, nv), float(w[0]))
    elif len(w) == nu * nv:
        w = w.reshape(nu, nv)
    else:
        raise ShapeError(tr('There are {n} control points ({nu} × {nv}) and {m} weights: give one for all or '
                              'one per point.').format(n=nu * nv, nu=nu, nv=nv, m=len(w)))
    if np.any(w <= 0):
        raise ShapeError(tr('Weights must be greater than 0 (1 is normal).'))
    bu, bv = base_in_a_direction(nu, ku, bool(closed_u)), base_in_a_direction(nv, kv, bool(closed_v))
    _require_size_({**{x: t for x, t in points.sizes.items() if x not in (level_u, level_v)},
                    "surface point": len(bu) * len(bv)}, tr('The surface'))
    numerator = np.einsum("ai,...ijc,bj->...abc", bu, v * w[..., None], bv)
    denominator = np.einsum("ai,ij,bj->ab", bu, w, bv)
    s = numerator / denominator[..., None]
    remain = tuple(x for x in points.levels if x not in (level_u, level_v))
    return Data(s.reshape(s.shape[:-3] + (len(bu) * len(bv), 3)), remain, name,
                {x: c for x, c in points.variables.items() if x in remain},
                {x: i for x, i in points.starts.items() if x in remain}, kind_surface(len(bu), len(bv)))


# --- S2 · Revolution and sweep ---------------------------------------------------------------

def _profiles(profile: Data) -> tuple[np.ndarray, bool]:
    """The curves of a profile as (…, n, 3), closed with their first point at the end (the seam)."""
    _require_curve(profile, "profile")
    v = np.asarray(profile.values, dtype=float)
    if profile.kind.closed and not np.allclose(v[..., 0, :], v[..., -1, :]):   # (some already repeat the first one)
        v = np.concatenate([v, v[..., :1, :]], axis=-2)
    return v, profile.kind.closed


def _rotate(points: np.ndarray, origin: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """The points turned by `angle` (radians) about the line origin + t·axis (Rodrigues)."""
    k = axis / np.linalg.norm(axis)
    p = points - origin
    c, s = np.cos(angle), np.sin(angle)
    return origin + p * c + np.cross(k, p) * s + k * (p @ k)[..., None] * (1 - c)


def revolve(profile: Data, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), degrees=360.0,
               name: str | None = None) -> Data:
    """The surface a profile leaves when turning about an axis (*Revolve*): a column, a dome, a vase. `origin` and
    `axis`: the line of the axis (a point and a direction); `degrees`: how much it turns (360: a whole turn, closed)."""
    v, _ = _profiles(profile)
    o = np.asarray(_point(origin, "origin").values, dtype=float).reshape(3)
    e = np.asarray(_point(axis, "axis").values, dtype=float).reshape(3)
    if np.linalg.norm(e) < 1e-12:
        raise ShapeError(tr('The axis cannot be zero (0, 0, 0).'))
    a = float(_values_items(degrees, "degrees")[0])
    if abs(a) < 1e-9:
        raise ShapeError(tr('The rotation angle cannot be 0.'))
    whole = abs(abs(a) - 360) < 1e-9 or abs(a) > 360
    a = np.clip(a, -360, 360)
    rows = max(9, int(round(64 * abs(a) / 360)) + 1)
    angles = np.radians(np.linspace(0, a, rows))
    s = np.stack([_rotate(v, o, e, t) for t in angles], axis=-3)           # (…, filas, n, 3)
    if whole:
        s[..., -1, :, :] = s[..., 0, :, :]                                 # the seam, exact
    f, c = s.shape[-3], s.shape[-2]
    return profile.derived(s.reshape(s.shape[:-3] + (f * c, 3)), name, kind_surface(f, c))


#: Where the profile goes in a sweep: as it is (drawn at the start of the path), or centred on it.
PLACE_PROFILE = ('where it is', 'centred on the path')


def _frames(path: np.ndarray, closed: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Frames that do not twist along a path (rotation minimizing frames, double reflection): (tangents, normals,
    binormals). If it is closed, the offset at the end is spread so the seam closes."""
    m = len(path)
    t = np.gradient(path, axis=0)
    if closed:                                           # without a seam: the tangents go round
        ring = path[:-1]
        t[:-1] = np.roll(ring, -1, axis=0) - np.roll(ring, 1, axis=0)
        t[-1] = t[0]
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    above = np.array([0.0, 0.0, 1.0]) if abs(t[0, 2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    r = above - t[0] * (above @ t[0])
    r /= np.linalg.norm(r)
    normals = [r]
    for i in range(m - 1):
        v1 = path[i + 1] - path[i]
        c1 = v1 @ v1
        if c1 < 1e-24:
            normals.append(normals[-1])
            continue
        r_l = normals[-1] - (2 / c1) * (v1 @ normals[-1]) * v1
        t_l = t[i] - (2 / c1) * (v1 @ t[i]) * v1
        v2 = t[i + 1] - t_l
        c2 = v2 @ v2
        normals.append(r_l - (2 / c2) * (v2 @ r_l) * v2 if c2 > 1e-24 else r_l)
    n = np.array(normals)
    n -= t * np.einsum("ij,ij->i", n, t)[:, None]
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    if closed:                                           # what turned too much, spread over the whole path
        offset = np.arctan2(np.cross(n[-1], n[0]) @ t[0], n[-1] @ n[0])
        lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
        for i in range(m):
            n[i] = _rotate(n[i], np.zeros(3), t[i], offset * lengths[i] / lengths[-1])
    return t, n, np.cross(t, n)


def sweep(profile: Data, path: Data, place: str = 'where it is', rotate=0.0, name: str | None = None,
            path_2: Data | None = None) -> Data:
    """The surface a profile leaves when travelling along a path (*Sweep*): a handrail, a moulding, a curved beam.
    The profile does not twist along the path (except `rotate`: degrees of turn over the whole run). `place`: «as it
    is» (the profile, drawn at the start of the path) or «centred on the path» (the profile, drawn anywhere: its centre
    goes to the path). With `path_2` (*Sweep 2*): the profile goes from one path to the other and stretches across to
    touch both (its height does not change)."""
    from .geometry import _curve_plane
    if path_2 is not None:
        return _sweep_with_two_rails(profile, path, path_2, place, name)
    v, _ = _profiles(profile)
    _require_curve(path, "path")
    if place not in PLACE_PROFILE:
        raise ShapeError(tr('«place» can be: {options}.').format(options=", ".join(tr(x) for x in PLACE_PROFILE)))
    if path.levels:
        raise ShapeError(tr('The path must be a single curve (each profile runs along all of it).'))
    filepath = _without_padding(np.asarray(path.values, dtype=float))
    closed = path.kind.closed
    if closed:
        if len(filepath) > 2 and np.allclose(filepath[0], filepath[-1]):   # a closed NURBS already repeats the first one at the end
            filepath = filepath[:-1]
        filepath = np.vstack([filepath, filepath[:1]])
    if len(filepath) < 2:
        raise ShapeError(tr('The path needs at least two points.'))
    t, n, b = _frames(filepath, closed)
    rotation = np.radians(float(_values_items(rotate, "girar")[0]))
    lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(filepath, axis=0), axis=1))])
    planes = v.reshape(-1, v.shape[-2], 3)
    output = []
    for p in planes:
        if place == 'where it is':                     # the profile, in the axes of the starting frame
            d = p - filepath[0]
            local = np.stack([d @ n[0], d @ b[0], d @ t[0]], axis=-1)
        else:                                           # its centre to the path; its plane, to the frame's plane
            real = _without_padding(p)
            normal = _curve_plane(real)
            e1 = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            e1 = e1 - normal * (e1 @ normal)
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(normal, e1)
            d = p - real.mean(axis=0)
            local = np.stack([d @ e1, d @ e2, np.zeros(len(d))], axis=-1)
        rows = []
        for i in range(len(filepath)):
            a = rotation * lengths[i] / (lengths[-1] or 1.0)
            nor = n[i] * np.cos(a) + b[i] * np.sin(a)
            bi = np.cross(t[i], nor)
            rows.append(filepath[i] + local[:, :1] * nor + local[:, 1:2] * bi + local[:, 2:3] * t[i])
        output.append(np.stack(rows))
    s = np.stack(output).reshape(v.shape[:-2] + (len(filepath), v.shape[-2], 3))
    f, c = s.shape[-3], s.shape[-2]
    return profile.derived(s.reshape(s.shape[:-3] + (f * c, 3)), name, kind_surface(f, c))


def _sweep_with_two_rails(profile: Data, path: Data, path_2: Data, place: str, name: str | None) -> Data:
    from .geometry import _curve_plane
    v, _ = _profiles(profile)
    filepaths = []
    for c, role in ((path, "path"), (path_2, "path 2")):
        _require_curve(c, role)
        if c.levels:
            raise ShapeError(tr('«{role}» must be a single curve.').format(role=tr(role)))
        filepaths.append(_without_padding(np.asarray(c.values, dtype=float)))
    m = max(POINTS_BY_EDGE, len(filepaths[0]), len(filepaths[1]))
    r1, r2 = (_resample(r, m) for r in filepaths)
    if np.linalg.norm(r1[0] - r2[-1]) + np.linalg.norm(r1[-1] - r2[0]) < \
            np.linalg.norm(r1[0] - r2[0]) + np.linalg.norm(r1[-1] - r2[-1]):
        r2 = r2[::-1]                                     # the two paths, in the same direction
    middle = (r1 + r2) / 2
    advance = np.gradient(middle, axis=0)

    def frame(i):
        x = r2[i] - r1[i]
        width = float(np.linalg.norm(x))
        if width < 1e-12:
            raise ShapeError(tr('The two paths touch: the profile has no width there.'))
        x = x / width
        z = advance[i] - x * (advance[i] @ x)
        z = z / (np.linalg.norm(z) or 1.0)
        return x, np.cross(z, x), z, width
    x0, y0, z0, width0 = frame(0)
    planes = v.reshape(-1, v.shape[-2], 3)
    output = []
    for p in planes:
        if place == 'where it is':                     # the profile, drawn between the starts of the two paths
            d = p - r1[0]
            local = np.stack([(d @ x0) / width0, d @ y0, d @ z0], axis=-1)
        else:                                           # its centre halfway; its width, from one path to the other
            real = _without_padding(p)
            normal = _curve_plane(real)
            e1 = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            e1 = e1 - normal * (e1 @ normal)
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(normal, e1)
            d = p - real.mean(axis=0)
            width_profile = float(np.ptp(d @ e1)) or 1.0
            local = np.stack([0.5 + (d @ e1) / width_profile, d @ e2, np.zeros(len(d))], axis=-1)
        rows = []
        for i in range(m):
            x, y, z, width = frame(i)
            rows.append(r1[i] + local[:, :1] * (x * width) + local[:, 1:2] * y + local[:, 2:3] * z)
        output.append(np.stack(rows))
    s = np.stack(output).reshape(v.shape[:-2] + (m, v.shape[-2], 3))
    f, c = s.shape[-3], s.shape[-2]
    return profile.derived(s.reshape(s.shape[:-3] + (f * c, 3)), name, kind_surface(f, c))


# --- Isocurvas ------------------------------------------------------------------------------

DIRECTIONS = ("u", "v")


def isocurves(surface: Data, direction: str = "u", mode: str = 'parts', count=10, positions=0.5,
              level: str = "isocurve", name: str | None = None) -> Data:
    """The surface's own lines (*Isocurve*): those that follow its grid, in u (along the rows) or in v (along the
    columns); in `count` equal parts or at some `positions` (fractions from 0 to 1). Ribs, mullions, a breakdown that
    follows the shape."""
    grid = getattr(surface.kind, "grid", None) if isinstance(surface, Data) else None
    if grid is None:
        raise ShapeError(tr('Isocurves belong to a surface (NURBS, loft, revolve…): «{name}» is not one.').format(name=surface._name() if isinstance(surface, Data) else ""))
    if direction not in DIRECTIONS:
        raise ShapeError(tr('The direction can be u or v.'))
    if mode not in ('parts', 'fraction'):
        raise ShapeError(tr('The mode can be: parts or fraction.'))
    f, c = grid
    r = np.asarray(surface.values, dtype=float).reshape(surface.values.shape[:-2] + (f, c, 3))
    if mode == 'parts':
        n = integer(count)
        if n < 1:
            raise ShapeError(tr('At least 1 isocurve is needed.'))
        t = np.linspace(0, 1, n) if n > 1 else np.array([0.5])
    else:
        t = np.clip(_values_items(positions, "positions"), 0, 1)
    if direction == "v":                                  # in v: along the columns, at some rows
        r = np.swapaxes(r, -3, -2)
    side = r.shape[-2]                                    # how many columns (u: the curves are the columns)
    x = t * (side - 1)
    j0 = np.clip(np.floor(x).astype(int), 0, side - 2)
    a = (x - j0)[:, None, None]
    curves = r[..., :, j0, :] * (1 - a.swapaxes(0, 1)) + r[..., :, j0 + 1, :] * a.swapaxes(0, 1)   # (…, puntos, m, 3)
    curves = np.moveaxis(curves, -2, -3)                  # (…, m, puntos, 3)
    from .geometry import CURVE
    if len(t) == 1:
        return surface.derived(curves[..., 0, :, :], name, CURVE)
    _require_size_({**surface.sizes, level: len(t)}, tr('The isocurves'))
    return surface.derived(curves, name, CURVE, (level,))


# --- Surface by a network of curves ---------------------------------------------------------

def _spline(xk: np.ndarray, yk: np.ndarray, x: np.ndarray) -> np.ndarray:
    """The natural cubic curve through (xk, yk) evaluated at x: yk (k, …) → (len(x), …). With two, a straight line."""
    k = len(xk)
    shape = yk.shape[1:]
    y = yk.reshape(k, -1)
    if k == 2:
        a = ((x - xk[0]) / (xk[1] - xk[0]))[:, None]
        return (y[0] * (1 - a) + y[1] * a).reshape((len(x),) + shape)
    h = np.diff(xk)
    matrix = np.zeros((k, k))
    side = np.zeros((k, y.shape[1]))
    matrix[0, 0] = matrix[-1, -1] = 1.0                   # natural: no curvature at the ends
    for i in range(1, k - 1):
        matrix[i, i - 1], matrix[i, i], matrix[i, i + 1] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
        side[i] = 6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
    m = np.linalg.solve(matrix, side)
    i = np.clip(np.searchsorted(xk, x, side="right") - 1, 0, k - 2)
    hi = h[i][:, None]
    a = (xk[i + 1][:, None] - x[:, None]) / hi
    b = (x[:, None] - xk[i][:, None]) / hi
    value = a * y[i] + b * y[i + 1] + ((a ** 3 - a) * m[i] + (b ** 3 - b) * m[i + 1]) * hi ** 2 / 6
    return value.reshape((len(x),) + shape)


def _loose_curves(data, role: str) -> list[np.ndarray]:
    _require_curve(data, role)
    list_ = [_without_padding(c) for c in np.asarray(data.values, dtype=float).reshape(-1, data.values.shape[-2], 3)]
    if len(list_) < 2:
        raise ShapeError(tr('«{role}» needs at least 2 curves (one family of the network).').format(role=tr(role)))
    return list_


def _crossing(a: np.ndarray, b: np.ndarray) -> tuple[float, float, np.ndarray, float]:
    """Where two sampled curves cross (or pass closest): (fraction on a, fraction on b, point, distance)."""
    d = np.linalg.norm(a[:, None] - b[None], axis=2)
    i, j = np.unravel_index(np.argmin(d), d.shape)
    return i / (len(a) - 1), j / (len(b) - 1), (a[i] + b[j]) / 2, float(d[i, j])


#: The most pairs of curves a Network surface crosses (each one, 97 × 97 distances).
MAXIMUM_CROSSINGS = 10_000


def surface_by_net(curves_u: Data, curves_v: Data, name: str | None = None) -> Data:
    """The surface through a network of curves in two crossing directions (*Network Surface*, a Gordon surface): the
    ribs of a hull, of a free roof. The curves can come in any order and direction; each one of one family has to cross
    (or pass very close to) each one of the other."""
    n = 97                                               # samples of each curve (by its length)
    loose_u, loose_v = _loose_curves(curves_u, "curves u"), _loose_curves(curves_v, "curves v")
    if len(loose_u) * len(loose_v) > MAXIMUM_CROSSINGS:  # each pair is crossed by hand: hundreds of thousands hang
        raise ShapeError(tr('The network has {u} × {v} curves: too many to cross one by one (at most {maximum} '
                            'crossings). Does one family come with a level too many?').format(
            u=_number(len(loose_u)), v=_number(len(loose_v)), maximum=_number(MAXIMUM_CROSSINGS)))
    family_u = [_resample(c, n) for c in loose_u]
    family_v = [_resample(c, n) for c in loose_v]
    size_ = float(np.ptp(np.vstack(family_u + family_v), axis=0).max()) or 1.0
    crossings = [[_crossing(a, b) for b in family_v] for a in family_u]
    worst = max(c[3] for row in crossings for c in row)
    if worst > 0.02 * size_:
        raise ShapeError(tr('The network curves do not all cross (two are {d} m apart): each u curve must cross '
                              'each v curve.').format(d=f"{worst:.3g}"))
    s = np.array([[c[0] for c in row] for row in crossings])         # (u, v): where each crossing falls on its u curve
    t = np.array([[c[1] for c in row] for row in crossings])         # and on its v curve
    p = np.array([[c[2] for c in row] for row in crossings])         # (u, v, 3)
    # All in the same direction and in order: the v ones by where they cut the u ones, and the other way round.
    order_v = np.argsort(s[0])
    for i in range(len(family_u)):
        if np.corrcoef(np.arange(len(order_v)), s[i, order_v])[0, 1] < 0 if len(order_v) > 1 else False:
            family_u[i], s[i] = family_u[i][::-1], 1 - s[i]
    order_u = np.argsort(t[:, 0])
    for j in range(len(family_v)):
        if np.corrcoef(np.arange(len(order_u)), t[order_u, j])[0, 1] < 0 if len(order_u) > 1 else False:
            family_v[j], t[:, j] = family_v[j][::-1], 1 - t[:, j]
    order_v, order_u = np.argsort(s.mean(axis=0)), np.argsort(t.mean(axis=1))
    family_u = [family_u[i] for i in order_u]
    family_v = [family_v[j] for j in order_v]
    s, t, p = s[order_u][:, order_v], t[order_u][:, order_v], p[order_u][:, order_v]
    ss, tt = s.mean(axis=0), t.mean(axis=1)                         # the crossings, common to the whole family
    if np.any(np.diff(ss) <= 1e-6) or np.any(np.diff(tt) <= 1e-6):
        raise ShapeError(tr('Two curves of the network cross the others at the same place: they cannot be ordered.'))
    mesh_s, mesh_t = np.linspace(0, 1, 49), np.linspace(0, 1, 49)

    def traverse(curve, own, common, a):           # the curve, with its crossings at the common places
        x = np.interp(a, np.concatenate([[0.0], common, [1.0]]), np.concatenate([[0.0], own, [1.0]]))
        k = np.linspace(0, 1, len(curve))
        return np.stack([np.interp(x, k, curve[:, e]) for e in range(3)], axis=-1)
    u_in_s = np.stack([traverse(c, s[i], ss, mesh_s) for i, c in enumerate(family_u)])     # (U, S, 3)
    v_in_t = np.stack([traverse(c, t[:, j], tt, mesh_t) for j, c in enumerate(family_v)])  # (V, T, 3)
    first = _spline(tt, u_in_s, mesh_t)                           # (T, S, 3): between the u curves
    second = np.swapaxes(_spline(ss, v_in_t, mesh_s), 0, 1)        # (T, S, 3): between the v curves
    crossed = _spline(tt, np.swapaxes(_spline(ss, np.swapaxes(p, 0, 1), mesh_s), 0, 1), mesh_t)  # the crossings
    surface = first + second - crossed
    rows, columns = surface.shape[:2]
    return Data(surface.reshape(-1, 3), (), name, kind=kind_surface(rows, columns))


# --- S3 · Surface by edges -------------------------------------------------------------

#: Points of each edge in the surface's grid.
POINTS_BY_EDGE = 33


def _resample(c: np.ndarray, n: int) -> np.ndarray:
    """A curve (points in order) at `n` points spread evenly along it."""
    lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    t = np.linspace(0.0, lengths[-1], n)
    return np.stack([np.interp(t, lengths, c[:, e]) for e in range(3)], axis=-1)


def _a_edge(curve, role: str) -> np.ndarray:
    _require_curve(curve, role)
    if curve.levels:
        raise ShapeError(tr('«{role}» must be a single curve (an edge).').format(role=tr(role)))
    c = _without_padding(np.asarray(curve.values, dtype=float))
    if curve.kind.closed:
        raise ShapeError(tr('«{role}» is a closed curve: an edge goes from one corner to another (to cap a '
                              'closed curve, use Cap).').format(role=tr(role)))
    return c


def surface_by_edges(a: Data, b: Data, c: Data | None = None, d: Data | None = None,
                          name: str | None = None) -> Data:
    """The surface stretched between its edges (*Edge Surface*, a Coons surface): four curves that touch at the corners
    (a slab, a roof with curved edges); with three, one of the sides closes into a point; with two, a ruled surface
    between them. The edges can come in any order and direction."""
    edges = [_a_edge(x, r) for x, r in ((a, "a"), (b, "b"), (c, "c"), (d, "d")) if x is not None]
    names = [r for x, r in ((a, "a"), (b, "b"), (c, "c"), (d, "d")) if x is not None]
    size_ = float(np.ptp(np.vstack(edges), axis=0).max()) or 1.0
    tolerance = 0.01 * size_
    n = POINTS_BY_EDGE
    if len(edges) == 2:                                  # ruled: the second one, in the direction of the first
        p, q = edges
        if np.linalg.norm(p[0] - q[-1]) + np.linalg.norm(p[-1] - q[0]) < \
                np.linalg.norm(p[0] - q[0]) + np.linalg.norm(p[-1] - q[-1]):
            q = q[::-1]
        p, q = _resample(p, n), _resample(q, n)
        t = np.linspace(0, 1, n)[:, None, None]
        s = p[None] * (1 - t) + q[None] * t
        return Data(s.reshape(-1, 3), (), name, kind=kind_surface(n, n))
    # Three or four: they chain, each one starting where the previous one ends.
    chain, order, remain = [edges[0]], [names[0]], list(range(1, len(edges)))
    while remain:
        end = chain[-1][-1]
        near = [(np.linalg.norm(edges[i][0] - end), i, False) for i in remain] + \
                [(np.linalg.norm(edges[i][-1] - end), i, True) for i in remain]
        distance, i, on_reverse = min(near)
        if distance > tolerance:
            raise ShapeError(tr('The edges do not touch: no other one starts after «{a}» (the closest is {d} m '
                                  'away). The curves must meet at the corners.').format(
                a=order[-1], d=f"{distance:.3g}"))
        chain.append(edges[i][::-1] if on_reverse else edges[i])
        order.append(names[i])
        remain.remove(i)
    if np.linalg.norm(chain[-1][-1] - chain[0][0]) > tolerance:
        raise ShapeError(tr('The edges do not close: «{a}» ends far from where «{b}» starts.').format(
            a=order[-1], b=order[0]))
    c0, c1, c2 = (_resample(x, n) for x in chain[:3])
    c3 = _resample(chain[3], n) if len(chain) == 4 else np.repeat(c0[:1], n, axis=0)   # three: one side is a point
    below, right, above, left = c0, c1, c2[::-1], c3[::-1]       # bottom and top in u; the sides in v
    u = np.linspace(0, 1, n)[None, :, None]
    v = np.linspace(0, 1, n)[:, None, None]
    p00, p10, p01, p11 = below[0], below[-1], above[0], above[-1]
    s = ((1 - v) * below[None] + v * above[None] + (1 - u) * left[:, None] + u * right[:, None]
         - ((1 - u) * (1 - v) * p00 + u * (1 - v) * p10 + (1 - u) * v * p01 + u * v * p11))
    return Data(s.reshape(-1, 3), (), name, kind=kind_surface(n, n))


# --- Points of a surface, flipping it, a part of it -------------------------------------

def _grid_of(surface, role: str = "surface") -> tuple[np.ndarray, int, int]:
    grid = getattr(surface.kind, "grid", None) if isinstance(surface, Data) else None
    if grid is None:
        raise ShapeError(tr('«{name}» should be a surface (NURBS, loft, revolve, edges…).').format(name=surface._name() if isinstance(surface, Data) else tr(role)))
    f, c = grid
    return np.asarray(surface.values, dtype=float).reshape(surface.values.shape[:-2] + (f, c, 3)), f, c


def _grid_normals(r: np.ndarray) -> np.ndarray:
    """The normal at each point of a grid (…, r, c, 3): that of its face (u × v); where the points coincide (the seam
    of a closed one, the pole of a dome), the average, so it does not jump."""
    su, sv = np.gradient(r, axis=-3), np.gradient(r, axis=-2)
    n = np.cross(su, sv)
    planes, normals = r.reshape(-1, r.shape[-3] * r.shape[-2], 3), n.reshape(-1, r.shape[-3] * r.shape[-2], 3)
    for p, q in zip(planes, normals):
        size_ = float(np.ptp(p, axis=0).max()) or 1.0
        _, group = np.unique(np.round(p / (size_ * 1e-7)).astype(np.int64), axis=0, return_inverse=True)
        group = group.ravel()
        total = np.zeros((group.max() + 1, 3))
        np.add.at(total, group, q)
        q[:] = total[group]
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    return np.divide(n, length, out=np.zeros_like(n), where=length > 1e-12)


def _bilinear(r: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """The values of a grid (…, r, c, k) at the fractions u (along the rows) and v (along the columns):
    (…, *shape of u, k)."""
    f, c = r.shape[-3], r.shape[-2]
    x, y = np.asarray(u, float) * (f - 1), np.asarray(v, float) * (c - 1)
    i0 = np.clip(np.floor(x).astype(int), 0, max(f - 2, 0))
    j0 = np.clip(np.floor(y).astype(int), 0, max(c - 2, 0))
    a, b = (x - i0)[..., None], (y - j0)[..., None]
    i1, j1 = np.minimum(i0 + 1, f - 1), np.minimum(j0 + 1, c - 1)
    return ((1 - a) * (1 - b) * r[..., i0, j0, :] + a * (1 - b) * r[..., i1, j0, :]
            + (1 - a) * b * r[..., i0, j1, :] + a * b * r[..., i1, j1, :])


def _closed_in(r: np.ndarray, axis: int) -> bool:
    """Whether the grid closes in that direction (the last row or column is the first)."""
    first, final = (r[..., 0, :, :], r[..., -1, :, :]) if axis == 0 else (r[..., :, 0, :], r[..., :, -1, :])
    return bool(np.allclose(first, final, atol=1e-9 * (float(np.ptp(r)) or 1.0)))


WHAT_POINTS_SURFACE = ('points', 'normals')
MODES_POINTS_SURFACE = ('lattice', 'centres', 'fractions')


def surface_points(surface: Data, what: str = 'points', mode: str = 'lattice', count_u=5, count_v=5,
                         u=0.5, v=0.5, name: str | None = None, level_u: str = "u", level_v: str = "v") -> Data:
    """Points on a surface (*Evaluate Surface*, *Divide Surface*), or its normal there (where it faces, length 1): in a
    **lattice** of count_u × count_v, or at some **fractions** of u and v (from 0 to 1; several with «;»: all the
    combinations). u goes along the rows and v along the columns, as in Isocurves. `level_u` and `level_v`: the names
    of their levels (the same name as another list, and they pair one by one)."""
    level_u, level_v = (str(level_u or "u").strip() or "u"), (str(level_v or "v").strip() or "v")
    if level_u == level_v:
        raise ShapeError(tr('The levels along u and along v need different names.'))
    r, f, c = _grid_of(surface)
    if what not in WHAT_POINTS_SURFACE:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_POINTS_SURFACE)))
    if mode not in MODES_POINTS_SURFACE:
        raise ShapeError(tr('The mode can be: {options}.').format(options=", ".join(tr(m) for m in MODES_POINTS_SURFACE)))
    if mode == 'lattice':
        nu, nv = integer(count_u), integer(count_v)
        if nu < 1 or nv < 1:
            raise ShapeError(tr('At least 1 point is needed in each direction.'))
        us = np.linspace(0, 1, nu, endpoint=not _closed_in(r, 0)) if nu > 1 else np.array([0.5])
        vs = np.linspace(0, 1, nv, endpoint=not _closed_in(r, 1)) if nv > 1 else np.array([0.5])
    elif mode == 'centres':                           # the centre of each panel of a division into count u × v
        nu, nv = integer(count_u), integer(count_v)
        if nu < 1 or nv < 1:
            raise ShapeError(tr('At least 1 panel is needed in each direction.'))
        us, vs = (np.arange(nu) + 0.5) / nu, (np.arange(nv) + 0.5) / nv
    else:
        us = np.clip(_values_items(u, "u"), 0, 1)
        vs = np.clip(_values_items(v, "v"), 0, 1)
    uu, vv = np.meshgrid(us, vs, indexing="ij")
    _require_size_({**surface.sizes, level_u: len(us), level_v: len(vs)}, tr('The surface points'))
    if what == 'points':
        values, kind = _bilinear(r, uu, vv), POINT
    else:
        from .geometry import VECTOR
        n = _bilinear(_grid_normals(r), uu, vv)
        length = np.linalg.norm(n, axis=-1, keepdims=True)
        values, kind = np.divide(n, length, out=np.zeros_like(n), where=length > 1e-12), VECTOR
    levels = tuple(x for x, k in ((level_u, len(us)), (level_v, len(vs))) if k > 1)
    if len(us) == 1:
        values = values[..., 0, :, :]
    if len(vs) == 1:
        values = values[..., 0, :]
    return surface.derived(values, name, kind, levels)


# --- The closest point on a surface, and a curve on a surface ----------------------------------------------------

#: What Closest point on surface gives: the point, its u and v (as a point (u, v, 0), to use in Curve on surface),
#: the distance, or the normal there.
GIVES_SURFACE = ('point', 'u v', 'distance', 'normal')


def _on_triangles(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The closest point of each triangle abc to each point p (all broadcast to (…, 3)): its weights on a, b and c
    (…, 3), and the squared distance. Inside, the projection on the plane; outside, the nearest of the three edges."""
    ab, ac, ap = b - a, c - a, p - a
    d00, d01, d11 = (ab * ab).sum(-1), (ab * ac).sum(-1), (ac * ac).sum(-1)
    d20, d21 = (ap * ab).sum(-1), (ap * ac).sum(-1)
    denominator = d00 * d11 - d01 * d01
    ok = denominator > 1e-24 * np.maximum(d00 * d11, 1e-300)
    safe = np.where(ok, denominator, 1.0)
    v = (d11 * d20 - d01 * d21) / safe
    w = (d00 * d21 - d01 * d20) / safe
    u = 1.0 - v - w
    weights = np.stack([u, v, w], -1)
    inside = ok & (u >= 0) & (v >= 0) & (w >= 0)

    def edge(start, direction, from_p, i, j):
        t = np.clip((from_p * direction).sum(-1) / np.maximum((direction * direction).sum(-1), 1e-300), 0.0, 1.0)
        out = np.zeros(t.shape + (3,))
        out[..., i], out[..., j] = 1.0 - t, t
        q = start + t[..., None] * direction
        return out, ((p - q) ** 2).sum(-1)

    candidates = [edge(a, ab, ap, 0, 1), edge(a, ac, ap, 0, 2), edge(b, c - b, p - b, 1, 2)]
    best_w, best_d = candidates[0]
    for wk, dk in candidates[1:]:
        closer = dk < best_d
        best_w, best_d = np.where(closer[..., None], wk, best_w), np.where(closer, dk, best_d)
    q = weights[..., 0:1] * a + weights[..., 1:2] * b + weights[..., 2:3] * c
    d_inside = ((p - q) ** 2).sum(-1)
    return np.where(inside[..., None], weights, best_w), np.where(inside, d_inside, best_d)


def closest_uv(points: np.ndarray, r: np.ndarray) -> np.ndarray:
    """The u and v (from 0 to 1) of the point of a grid surface r (f, c, 3) closest to each point (N, 3): each cell
    as two triangles, and the nearest of all."""
    f, c = r.shape[0], r.shape[1]
    us, vs = np.meshgrid(np.linspace(0, 1, f), np.linspace(0, 1, c), indexing="ij")
    uv = np.stack([us, vs], -1)
    corners = [(r[:-1, :-1], r[1:, :-1], r[1:, 1:]), (r[:-1, :-1], r[1:, 1:], r[:-1, 1:])]
    corners_uv = [(uv[:-1, :-1], uv[1:, :-1], uv[1:, 1:]), (uv[:-1, :-1], uv[1:, 1:], uv[:-1, 1:])]
    a = np.concatenate([x[0].reshape(-1, 3) for x in corners])
    b = np.concatenate([x[1].reshape(-1, 3) for x in corners])
    cc = np.concatenate([x[2].reshape(-1, 3) for x in corners])
    ua = np.concatenate([x[0].reshape(-1, 2) for x in corners_uv])
    ub = np.concatenate([x[1].reshape(-1, 2) for x in corners_uv])
    uc = np.concatenate([x[2].reshape(-1, 2) for x in corners_uv])
    points = np.asarray(points, float).reshape(-1, 3)
    out = np.zeros((len(points), 2))
    chunk = max(1, int(2_000_000 // max(len(a), 1)))            # (points × triangles in pieces: bounded memory)
    for k in range(0, len(points), chunk):
        p = points[k:k + chunk, None, :]
        weights, d2 = _on_triangles(p, a[None], b[None], cc[None])
        best = np.argmin(d2, axis=1)
        w = weights[np.arange(len(p)), best]
        out[k:k + chunk] = w[:, 0:1] * ua[best] + w[:, 1:2] * ub[best] + w[:, 2:3] * uc[best]
    out = np.clip(out, 0.0, 1.0)
    # Then a few steps on the surface itself (Gauss-Newton on its u and v), so the point lies exactly on it.
    h = 1e-6
    for _ in range(6):
        u, v = out[:, 0], out[:, 1]
        s0 = _bilinear(r, u, v)
        su = (_bilinear(r, np.clip(u + h, 0, 1), v) - _bilinear(r, np.clip(u - h, 0, 1), v)) / (2 * h)
        sv = (_bilinear(r, u, np.clip(v + h, 0, 1)) - _bilinear(r, u, np.clip(v - h, 0, 1))) / (2 * h)
        e = points - s0
        a11, a12, a22 = (su * su).sum(-1), (su * sv).sum(-1), (sv * sv).sum(-1)
        b1, b2 = (su * e).sum(-1), (sv * e).sum(-1)
        det = a11 * a22 - a12 * a12
        ok = det > 1e-18 * np.maximum(a11 * a22, 1e-300)
        du = np.where(ok, (a22 * b1 - a12 * b2) / np.where(ok, det, 1.0), 0.0)
        dv = np.where(ok, (a11 * b2 - a12 * b1) / np.where(ok, det, 1.0), 0.0)
        step = np.clip(np.stack([du, dv], -1), -1.0 / max(f - 1, 1), 1.0 / max(c - 1, 1))
        trial = np.clip(out + step, 0.0, 1.0)
        better = ((points - _bilinear(r, trial[:, 0], trial[:, 1])) ** 2).sum(-1) < (e ** 2).sum(-1)
        out = np.where(better[:, None], trial, out)
    return out


def _each(q: np.ndarray, s: np.ndarray, f: int, c: int, element: int):
    """Pairs each element of q (…, *element axes) with its surface grid from s (…, f·c, 3), broadcasting their
    levels: yields (index, element, grid) and gives the shape of the levels."""
    lead = np.broadcast_shapes(q.shape[:q.ndim - element], s.shape[:-2])
    q = np.broadcast_to(q, lead + q.shape[q.ndim - element:])
    g = np.broadcast_to(s.reshape(s.shape[:-2] + (f, c, 3)), lead + (f, c, 3))
    return lead, [(index, q[index], g[index]) for index in np.ndindex(*lead)]


def _closest_all(q: np.ndarray, s: np.ndarray, f: int, c: int) -> tuple[np.ndarray, np.ndarray, list]:
    """For each point of q (…, 3), its u and v on its surface (…, 2), and the grids, by level index."""
    lead, items = _each(q, s, f, c, 1)
    uv = np.zeros(lead + (2,))
    if s.reshape(-1, f * c, 3).shape[0] == 1:                # a single surface for all the points: at once
        grid = s.reshape(f, c, 3)
        uv[...] = closest_uv(np.broadcast_to(q, lead + (3,)).reshape(-1, 3), grid).reshape(lead + (2,))
    else:
        for index, point, grid in items:
            uv[index] = closest_uv(point[None], grid)[0]
    return uv, lead, items


def closest_on_surface(points, surface: Data, gives: str = 'point', name: str | None = None) -> Data:
    """The point of a surface closest to each point (*Surface Closest Point*): to bring something onto the surface, to
    know where it falls on it (its u and v, from 0 to 1, as a point (u, v, 0) for Curve on surface), how far it is,
    or where the surface faces there (its normal)."""
    from .geometry import VECTOR
    if gives not in GIVES_SURFACE:
        raise ShapeError(tr('“gives” must be one of: {options}.').format(
            options=", ".join(tr(d) for d in GIVES_SURFACE)))
    _, f, c = _grid_of(surface)

    def find(q, s):
        uv, lead, items = _closest_all(np.asarray(q, float), np.asarray(s, float), f, c)
        if gives == 'u v':
            return np.concatenate([uv, np.zeros(lead + (1,))], -1)
        out = np.zeros(lead + (3,))
        for index, point, grid in items:
            u, v = uv[index]
            if gives == 'normal':
                n = _bilinear(_grid_normals(grid), u, v)
                out[index] = n / (np.linalg.norm(n) or 1.0)
            else:
                out[index] = _bilinear(grid, u, v)
        if gives == 'distance':
            return np.linalg.norm(np.broadcast_to(q, lead + (3,)) - out, axis=-1)
        return out

    kind = {'point': POINT, 'u v': POINT, 'distance': None}.get(gives, VECTOR)
    return apply(find, _point(points, "points"), surface, name=name, kind=kind)


#: How many points the curve on the surface takes along each straight piece of its map: enough to follow the surface.
SAMPLES_ON_SURFACE = 24


def curve_on_surface(surface: Data, points, along: str | None = None, smooth: bool = True, closed: bool = False,
                     name: str | None = None) -> Data:
    """A curve that lies on a surface (*Curve On Surface*), through some points given by their u and v (from 0 to 1,
    as points (u, v, 0): from Closest point on surface, or a Point with x = u and y = v). The curve is drawn on the
    flat map of the surface (u, v), smooth or straight, and then laid on it, so it follows every bump."""
    from .geometry import CLOSED_CURVE, CURVE, curve_by_points
    r, f, c = _grid_of(surface)
    cu, cv = _closed_in(r, 0), _closed_in(r, 1)
    flat = curve_by_points(_point(points, "points"), along, smooth, closed)     # on the map of the surface
    v = np.asarray(flat.values, float)
    if not smooth:                                          # a straight piece of the map is a curve on the surface
        t = np.linspace(0, 1, SAMPLES_ON_SURFACE, endpoint=False)[:, None]
        ends = np.concatenate([v[..., 1:, :], v[..., :1, :]], -2) if closed else v[..., 1:, :]
        starts = v if closed else v[..., :-1, :]
        dense = (starts[..., :, None, :] * (1 - t) + ends[..., :, None, :] * t)
        dense = dense.reshape(dense.shape[:-3] + (-1, 3))
        v = dense if closed else np.concatenate([dense, v[..., -1:, :]], -2)
    on_map = Data(v, flat.levels, None, flat.variables, flat.starts, flat.kind, flat.holes)

    def lay(q, s):
        lead, items = _each(np.asarray(q, float), np.asarray(s, float), f, c, 2)
        out = np.zeros(lead + q.shape[-2:])
        for index, samples, grid in items:
            u = np.mod(samples[:, 0], 1.0) if cu else np.clip(samples[:, 0], 0, 1)
            w = np.mod(samples[:, 1], 1.0) if cv else np.clip(samples[:, 1], 0, 1)
            out[index] = _bilinear(grid, u, w)
        return out

    return apply(lay, on_map, surface, name=name, kind=CLOSED_CURVE if closed else CURVE)


def surface_cells(surface: Data, count_u=6, count_v=6, height=1.0, name: str | None = None) -> Data:
    """The surface divided into count_u × count_v cells that rise `height` along its normal: blocks that follow the
    curve and share their corners, so a module fitted into them covers the surface without gaps."""
    r, _, _ = _grid_of(surface)
    nu, nv = integer(count_u), integer(count_v)
    if nu < 1 or nv < 1:
        raise ShapeError(tr('At least 1 panel is needed in each direction.'))
    _require_size_({**surface.sizes, "u": nu, "v": nv}, tr('The cells of the surface'))
    uu, vv = np.meshgrid(np.linspace(0, 1, nu + 1), np.linspace(0, 1, nv + 1), indexing="ij")
    points, normals = _bilinear(r, uu, vv), _bilinear(_grid_normals(r), uu, vv)
    length = np.linalg.norm(normals, axis=-1, keepdims=True)
    normals = np.divide(normals, length, out=np.zeros_like(normals), where=length > 1e-12)

    def corners(x):                                   # the four corners of each cell, in the order of a box
        return np.stack([x[..., :-1, :-1, :], x[..., 1:, :-1, :], x[..., 1:, 1:, :], x[..., :-1, 1:, :]], axis=-2)

    base = surface.derived(np.concatenate([corners(points), corners(normals)], axis=-2), None, BLOCK, ("u", "v"))

    def rise(c, h):
        below, n = c[..., :4, :], c[..., 4:, :]
        return np.concatenate([below, below + n * np.asarray(h, dtype=float)[..., None, None]], axis=-2)

    return apply(rise, base, _data(height), name=name, kind=BLOCK)


def surface_morph(geometry, surface: Data, count_u=6, count_v=6, height=1.0, reference=None,
                  name: str | None = None) -> Data:
    """A module in each cell of a surface (*Surface Morph*, paneling): it follows the curve and its normal, the
    bottom of the module on the surface and its top `height` above. Without a module, the cells themselves."""
    from .geometry import morph
    blocks = surface_cells(surface, count_u, count_v, height, None if geometry is not None else name)
    if geometry is None:
        return blocks
    return morph(geometry, blocks, reference=reference, name=name)


def grid_curvatures(values, rows: int, columns: int) -> tuple[np.ndarray, np.ndarray]:
    """The Gaussian (K) and mean (H) curvature at each point of some grid surfaces ((…, rows, columns, 3) or
    (…, rows·columns, 3)): (…, rows, columns) each, with the two fundamental forms: K = (LN − M²) / (EG − F²),
    H = (EN − 2FM + GL) / (2 (EG − F²)). They do not depend on how the points are spread. The sign of H depends on where
    the face looks (u × v). Where the grid closes into a point (the pole of a dome, the tip of a cone), that of its
    surroundings."""
    v = np.asarray(values, dtype=float).reshape(-1, rows, columns, 3)
    cu, cv = _closed_in(v, 0) if rows > 2 else False, _closed_in(v, 1) if columns > 2 else False

    def derivative(x, axis, closed):                     # in a closed direction, it goes round through the seam
        if not closed:
            return np.gradient(x, axis=axis)
        without = np.take(x, range(x.shape[axis] - 1), axis=axis)          # without repeating the seam
        d = (np.roll(without, -1, axis=axis) - np.roll(without, 1, axis=axis)) / 2
        return np.concatenate([d, np.take(d, [0], axis=axis)], axis=axis)
    su, sv = derivative(v, 1, cu), derivative(v, 2, cv)
    suu, svv, suv = derivative(su, 1, cu), derivative(sv, 2, cv), derivative(su, 2, cv)
    normal = np.cross(su, sv)
    length = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal = np.divide(normal, length, out=np.zeros_like(normal), where=length > 1e-12)
    e, f, g = (su * su).sum(-1), (su * sv).sum(-1), (sv * sv).sum(-1)
    l, m, n = (suu * normal).sum(-1), (suv * normal).sum(-1), (svv * normal).sum(-1)
    below = e * g - f * f
    well = below > 1e-12 * max(float(below.max()), 1e-24)
    k = np.divide(l * n - m * m, below, out=np.full_like(below, np.nan), where=well)
    h = np.divide(e * n - 2 * f * m + g * l, 2 * below, out=np.full_like(below, np.nan), where=well)
    for x in (k, h):
        for i in range(len(x)):                        # the points without surface around: that of their surroundings
            bad = ~np.isfinite(x[i])
            if bad.any():
                x[i][bad] = np.nanmedian(x[i]) if np.isfinite(x[i]).any() else 0.0
    shape = np.asarray(values).shape[:-1]
    if shape[-1:] == (rows * columns,):              # (…, rows·columns, 3), as a Data keeps the points
        shape = shape[:-1] + (rows, columns)
    return k.reshape(shape), h.reshape(shape)


WHAT_CURVATURE = ('Gaussian', 'mean', 'developable')
#: A surface is developable if its normals sweep less than this on the sphere (in steradians; a
#: hemisphere sweeps 2π ≈ 6.28): in practice, it is made from a flat sheet.
DEVELOPABLE_TOLERANCE = 0.01


def _gauss_image(r: np.ndarray) -> np.ndarray:
    """What the normals of the panels of some grids (…, r, c, 3) sweep on the unit sphere (their «Gauss image», in
    steradians), without the two panels of each border: there a tangent developable has its edge of regression, where the
    surface is not smooth. In a developable one it is zero: its normals do not change along each ruling. It uses only the
    normals of the panels (no second derivatives)."""
    d1 = r[..., 1:, 1:, :] - r[..., :-1, :-1, :]
    d2 = r[..., :-1, 1:, :] - r[..., 1:, :-1, :]
    n = np.cross(d1, d2)
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    well = length[..., 0] > 1e-12 * max(float(length.max()), 1e-30)
    n = np.divide(n, length, out=np.zeros_like(n), where=length > 0)

    def triangle(a, b, c):                            # the area of a spherical triangle (Van Oosterom and Strackee)
        above = np.einsum("...i,...i->...", a, np.cross(b, c))
        below = 1 + (a * b).sum(-1) + (b * c).sum(-1) + (c * a).sum(-1)
        return 2 * np.arctan2(np.abs(above), below)
    a, b, c, d = n[..., :-1, :-1, :], n[..., 1:, :-1, :], n[..., 1:, 1:, :], n[..., :-1, 1:, :]
    well = well[..., :-1, :-1] & well[..., 1:, :-1] & well[..., 1:, 1:] & well[..., :-1, 1:]
    area = np.where(well, triangle(a, b, c) + triangle(a, c, d), 0.0)
    area = area[..., 2:-2, :, ] if area.shape[-2] > 6 else area
    area = area[..., :, 2:-2] if area.shape[-1] > 6 else area
    return area.reshape(area.shape[:-2] + (-1,)).sum(-1)


def surface_curvature(surface: Data, what: str = 'Gaussian', mode: str = 'lattice', count_u=5,
                            count_v=5, u=0.5, v=0.5, name: str | None = None) -> Data:
    """The curvature of a surface at some points (the same ones Surface points gives with the same mode):
    **Gaussian** (zero: it is made from a flat sheet; positive: dome-like; negative: saddle-like), **mean** (the average
    of how it bends in the two directions; its sign depends on where the face looks) or **developable**: yes or no, for
    each surface (the Gaussian is zero all over it)."""
    r, f, c = _grid_of(surface)
    if what not in WHAT_CURVATURE:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_CURVATURE)))
    if f == 2 or c == 2:                               # a straight direction (a cone, a cylinder by extrusion):
        fu = np.linspace(0, 1, 17 if f == 2 else f)     # more points in it, so the curvature carries on in between
        fv = np.linspace(0, 1, 17 if c == 2 else c)
        r = _bilinear(r, *np.meshgrid(fu, fv, indexing="ij"))
        f, c = len(fu), len(fv)
    k, h = grid_curvatures(r, f, c)
    if what == 'developable':
        yes = _gauss_image(r) <= DEVELOPABLE_TOLERANCE
        return surface.derived(np.asarray(yes), name, None, ())
    if mode not in MODES_POINTS_SURFACE:
        raise ShapeError(tr('The mode can be: {options}.').format(options=", ".join(tr(m) for m in MODES_POINTS_SURFACE)))
    if mode == 'lattice':
        nu, nv = integer(count_u), integer(count_v)
        if nu < 1 or nv < 1:
            raise ShapeError(tr('At least 1 point is needed in each direction.'))
        us = np.linspace(0, 1, nu, endpoint=not _closed_in(r, 0)) if nu > 1 else np.array([0.5])
        vs = np.linspace(0, 1, nv, endpoint=not _closed_in(r, 1)) if nv > 1 else np.array([0.5])
    elif mode == 'centres':                           # the centre of each panel of a division into count u × v
        nu, nv = integer(count_u), integer(count_v)
        if nu < 1 or nv < 1:
            raise ShapeError(tr('At least 1 panel is needed in each direction.'))
        us, vs = (np.arange(nu) + 0.5) / nu, (np.arange(nv) + 0.5) / nv
    else:
        us = np.clip(_values_items(u, "u"), 0, 1)
        vs = np.clip(_values_items(v, "v"), 0, 1)
    uu, vv = np.meshgrid(us, vs, indexing="ij")
    _require_size_({**surface.sizes, "u": len(us), "v": len(vs)}, tr('The surface curvature'))
    values = _bilinear((k if what == 'Gaussian' else h)[..., None], uu, vv)[..., 0]
    levels = tuple(x for x, n_ in (("u", len(us)), ("v", len(vs))) if n_ > 1)
    if len(us) == 1:
        values = values[..., 0, :]
    if len(vs) == 1:
        values = values[..., 0]
    return surface.derived(values, name, None, levels)


WHAT_REVERSE = ('face', "u", "v", 'swap u and v')


def reverse_surface(surface: Data, what: str = 'face', name: str | None = None) -> Data:
    """The surface flipped (*Flip*, *Swap UV*): «face», it looks the other way (its normal, reversed: so that Thicken
    grows to the other side); «u» or «v», that direction reversed (it also flips the face); «swap u and v», the rows
    become the columns."""
    r, f, c = _grid_of(surface)
    if what not in WHAT_REVERSE:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_REVERSE)))
    if what in ('face', "v"):
        r = r[..., :, ::-1, :]
    elif what == "u":
        r = r[..., ::-1, :, :]
    else:
        r = np.swapaxes(r, -3, -2)
        f, c = c, f
    return surface.derived(r.reshape(r.shape[:-3] + (f * c, 3)), name, kind_surface(f, c))


def surface_part(surface: Data, u_from=0.0, u_to=1.0, v_from=0.0, v_to=1.0,
                        name: str | None = None) -> Data:
    """The piece of a surface between two fractions of u and two of v (*Isotrim*, *Sub Surface*): a panel of a roof, a
    gore of a dome. In a closed direction, «to» before «from» goes round. With several values (separated by «;», or
    from a Series), several pieces (the «part» level): the gores of a dome."""
    r, f, c = _grid_of(surface)
    lists = [np.asarray(_values_items(x, role), float).ravel()
              for x, role in ((u_from, "from"), (u_to, "to"), (v_from, "from"), (v_to, "to"))]
    n = max(len(x) for x in lists)
    if any(len(x) not in (1, n) for x in lists):
        raise ShapeError(tr('«from» and «to» must have the same number of values (or a single one).'))
    lists = [np.resize(x, n) for x in lists]

    def run(a, b, closed):
        if closed and b < a:
            b += 1.0
        elif not closed:
            a, b = sorted((float(np.clip(a, 0, 1)), float(np.clip(b, 0, 1))))
        if abs(b - a) < 1e-9:
            raise ShapeError(tr('«from» and «to» are the same: the piece has no width.'))
        return a, b

    cu, cv = _closed_in(r, 0), _closed_in(r, 1)
    runs_u = [run(a, b, cu) for a, b in zip(lists[0], lists[1])]
    runs_v = [run(a, b, cv) for a, b in zip(lists[2], lists[3])]
    # All the pieces with the same grid (that of the widest), so they go together in a list.
    rows = max(max(2, int(np.ceil(abs(b - a) * (f - 1))) + 1) for a, b in runs_u)
    columns = max(max(2, int(np.ceil(abs(b - a) * (c - 1))) + 1) for a, b in runs_v)
    pieces = []
    for (ua, ub), (goes, vb) in zip(runs_u, runs_v):
        us, vs = np.linspace(ua, ub, rows), np.linspace(goes, vb, columns)
        us = np.mod(us, 1.0 + 1e-12) if cu else us
        vs = np.mod(vs, 1.0 + 1e-12) if cv else vs
        s = _bilinear(r, *np.meshgrid(us, vs, indexing="ij"))
        pieces.append(s.reshape(s.shape[:-3] + (rows * columns, 3)))
    kind = kind_surface(rows, columns)
    if n == 1:
        return surface.derived(pieces[0], name, kind)
    return surface.derived(np.stack(pieces, axis=-3), name, kind, ("part",))


# --- Intersections and splitting with curves -------------------------------------------------------

def _triangles(data: Data, role: str) -> tuple[np.ndarray, np.ndarray]:
    """All the elements of a geometry with faces (surface, mesh, box, rectangles), as (vertices, triangles) of a
    single mesh."""
    from .geometry import real_faces
    if not isinstance(data, Data) or data.kind is None or data.kind.faces is None or data.kind.curve:
        raise ShapeError(tr('«{role}» should be a surface or a body (something with faces).').format(role=tr(role)))
    v = np.asarray(data.values, dtype=float)
    by_element = v.shape[-2]
    elements = v.reshape(-1, by_element, 3)
    tris = []
    for i, e in enumerate(elements):
        faces = real_faces(data.kind, e) if data.kind.polygon else data.kind.faces
        for face in faces:
            for k in range(1, len(face) - 1):                  # as a fan
                tris.append((i * by_element + face[0], i * by_element + face[k], i * by_element + face[k + 1]))
    return elements.reshape(-1, 3), np.array(tris, dtype=np.int64).reshape(-1, 3)


def _vtk(vertices: np.ndarray, triangles: np.ndarray):
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(vertices, dtype=float), deep=True))
    cells = vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0, 3 * len(triangles) + 1, 3, dtype=np.int64), deep=True),
                   numpy_to_vtkIdTypeArray(np.ascontiguousarray(triangles.ravel(), dtype=np.int64), deep=True))
    mesh = vtk.vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(cells)
    return mesh


def _polylines(output) -> list[np.ndarray]:
    """The lines of a VTK output, chained into polylines (each one, its points in order)."""
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import vtk_to_numpy
    clean = vtk.vtkCleanPolyData()
    clean.SetInputData(output)
    chain = vtk.vtkStripper()
    chain.SetInputConnection(clean.GetOutputPort())
    chain.JoinContiguousSegmentsOn()
    chain.Update()
    lines = chain.GetOutput()
    if lines.GetNumberOfLines() == 0:
        return []
    points = vtk_to_numpy(lines.GetPoints().GetData()).astype(float)
    cells = lines.GetLines()
    offsets = vtk_to_numpy(cells.GetOffsetsArray())
    connectivity = vtk_to_numpy(cells.GetConnectivityArray())
    output_ = []
    for start, end in zip(offsets[:-1], offsets[1:]):
        if end - start >= 2:
            output_.append(points[connectivity[start:end]])
    return output_


def _curves_pairs(polylines: list[np.ndarray], name: str | None, level: str) -> Data:
    """Some polylines of different lengths as curves of a data: all with the same number of points (by their length)."""
    from .geometry import CURVE
    n = max(33, max(len(p) for p in polylines))
    curves = np.stack([_resample(p, n) for p in polylines])
    if len(curves) == 1:
        return Data(curves[0], (), name, kind=CURVE)
    return Data(curves, (level,), name, kind=CURVE)


def intersection(a: Data, b: Data, name: str | None = None) -> Data:
    """Where two geometries cross (*Brep | Brep*, *Curve | Brep*): two surfaces (or bodies), the **curves** of their
    crossing (a roof with a wall, two skins); a curve with a surface, the **points** where it goes through. Then they can
    be divided (Points on curve) or cut (Cut curve)."""
    from . import vtk_light as vtk
    to_curve = isinstance(a, Data) and a.kind is not None and a.kind.curve
    b_curve = isinstance(b, Data) and b.kind is not None and b.kind.curve
    if to_curve and b_curve:
        raise ShapeError(tr('Two curves almost never meet in space: for that, one of them must be a surface.'))
    if to_curve or b_curve:                                # curve with surface: points
        curve, other = (a, b) if to_curve else (b, a)
        vertices, triangles = _triangles(other, "surface")
        a0, a1, a2 = (vertices[triangles[:, k]] for k in range(3))
        e1, e2 = a1 - a0, a2 - a0
        found = []
        for c in np.asarray(curve.values, dtype=float).reshape(-1, curve.values.shape[-2], 3):
            c = _without_padding(c)
            if curve.kind.closed:
                c = np.vstack([c, c[:1]])
            for p0, p1 in zip(c[:-1], c[1:]):             # each segment with each triangle (Möller–Trumbore)
                d = p1 - p0
                h = np.cross(d, e2)
                det = np.einsum("ij,ij->i", e1, h)
                valid = np.abs(det) > 1e-14
                inv = np.divide(1.0, det, out=np.zeros_like(det), where=valid)
                s_ = p0 - a0
                u = np.einsum("ij,ij->i", s_, h) * inv
                q = np.cross(s_, e1)
                v = (q @ d) * inv
                t = np.einsum("ij,ij->i", e2, q) * inv
                hit = valid & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t >= -1e-9) & (t <= 1 + 1e-9)
                found += list(p0 + np.outer(t[hit], d))
        if not found:
            raise ShapeError(tr('The curve does not go through the surface: there are no crossing points.'))
        p = np.array(found)
        size_ = float(np.ptp(vertices, axis=0).max()) or 1.0
        _, unique = np.unique(np.round(p / (size_ * 1e-6)).astype(np.int64), axis=0, return_index=True)
        p = p[np.sort(unique)]
        return Data(p[0], (), name, kind=POINT) if len(p) == 1 else Data(p, ("crossing",), name, kind=POINT)
    goes, ta = _triangles(a, "a")
    vb, tb = _triangles(b, "b")
    filter_ = vtk.vtkIntersectionPolyDataFilter()
    filter_.SetInputData(0, _vtk(goes, ta))
    filter_.SetInputData(1, _vtk(vb, tb))
    filter_.SplitFirstOutputOff()
    filter_.SplitSecondOutputOff()
    filter_.GlobalWarningDisplayOff()
    filter_.Update()
    lines = _polylines(filter_.GetOutput(0))
    if not lines:
        raise ShapeError(tr('The two geometries do not cross.'))
    return _curves_pairs(lines, name, "crossing")


def _loose_triangles(pieces: list[tuple[np.ndarray, np.ndarray]], name: str | None, level: str) -> Data:
    """Some mesh pieces (each one, its vertices and triangles) in a data: each triangle with its three points, and the
    pieces with fewer triangles, padded with triangles without area (they are not seen). So they go in a list."""
    from .meshes import kind_mesh
    more = max(len(t) for _, t in pieces)
    elements = []
    for v, t in pieces:
        loose = v[t].reshape(-1, 3)
        padding = np.repeat(loose[-1:], 3 * (more - len(t)), axis=0)
        elements.append(np.vstack([loose, padding]))
    faces = tuple((3 * k, 3 * k + 1, 3 * k + 2) for k in range(more))
    values = np.stack(elements)
    if len(pieces) == 1:
        return Data(values[0], (), name, kind=kind_mesh(faces))
    return Data(values, (level,), name, kind=kind_mesh(faces))


def _curves_what_there_is(curves: Data) -> np.ndarray:
    """The curves of a data, one after the other, without those a Filter left empty: (n, points, 3)."""
    v = np.asarray(curves.values, dtype=float)
    if curves.levels:
        v = v[curves.mask]
    return v.reshape(-1, v.shape[-2], 3)


def _touch(a: np.ndarray, b: np.ndarray) -> bool:
    """Whether two 2D polygons touch: one has a point inside the other, or their sides cross."""
    from .geometry import _inside
    if _inside(a[:1], b)[0] or _inside(b[:1], a)[0]:
        return True
    p, r = a, np.roll(a, -1, 0) - a
    q, s_ = b, np.roll(b, -1, 0) - b
    cross = r[:, None, 0] * s_[None, :, 1] - r[:, None, 1] * s_[None, :, 0]
    qp = q[None, :, :] - p[:, None, :]
    parallel = np.abs(cross) < 1e-15
    cross = np.where(parallel, 1.0, cross)
    t = (qp[..., 0] * s_[None, :, 1] - qp[..., 1] * s_[None, :, 0]) / cross
    u = (qp[..., 0] * r[:, None, 1] - qp[..., 1] * r[:, None, 0]) / cross
    return bool(((t >= 0) & (t <= 1) & (u >= 0) & (u <= 1) & ~parallel).any())


def _is_convex(q: np.ndarray) -> bool:
    """Whether a 2D polygon (anticlockwise) is convex: all its turns, to the same side."""
    a, b = np.roll(q, -1, 0) - q, np.roll(q, -2, 0) - np.roll(q, -1, 0)
    rotation = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    return bool((rotation >= -1e-12 * float(np.abs(rotation).max() or 1)).all())


def _delaunay_2d(edge, cutouts: list, loose: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Triangles (constrained Delaunay) of a 2D polygon (anticlockwise) with holes (clockwise) and some loose points
    inside. `edge` can be a list of separate polygons (all triangulated at once). The points come out in the order
    they go in."""
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    edges = (list(edge) if isinstance(edge, list) else [edge]) + list(cutouts)
    p2 = np.vstack(edges + [loose.reshape(-1, 2)])
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(np.column_stack([p2, np.zeros(len(p2))])), deep=True))
    input_ = vtk.vtkPolyData()
    input_.SetPoints(points)
    from vtkmodules.util.numpy_support import numpy_to_vtkIdTypeArray
    lengths = np.array([len(b) for b in edges], dtype=np.int64)
    from_ = np.concatenate([[0], np.cumsum(lengths)])          # the edges, at once (not point by point)
    polygons = vtk.vtkCellArray()
    polygons.SetData(numpy_to_vtkIdTypeArray(from_.astype(np.int64), deep=True),
                      numpy_to_vtkIdTypeArray(np.arange(from_[-1], dtype=np.int64), deep=True))
    source = vtk.vtkPolyData()
    source.SetPoints(points)
    source.SetPolys(polygons)
    delaunay = vtk.vtkDelaunay2D()
    delaunay.SetInputData(input_)
    delaunay.SetSourceData(source)
    delaunay.Update()
    output = delaunay.GetOutput()
    if output.GetNumberOfPolys() == 0:
        return np.zeros((0, 2)), np.zeros((0, 3), dtype=np.int64)
    faces = vtk_to_numpy(output.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    return vtk_to_numpy(output.GetPoints().GetData())[:, :2].copy(), faces


_REASONS_WITHOUT_HOLES = {
    0: 'the curves are not closed (or the surface is not a grid)',
    1: 'the surface closes on itself',
    2: 'some curve goes off the surface',
    3: 'there are no curves that make holes',
    4: 'some curve touches the edge of the surface',
    5: 'some curves touch each other',
    6: 'it could not be triangulated',
}


def _pattern(k: int) -> str:
    return _REASONS_WITHOUT_HOLES.get(k, "")


def _uv_looking(vert: np.ndarray, tri: np.ndarray, uv: np.ndarray, points: np.ndarray, d: np.ndarray):
    """Where each point falls on a mesh of triangles looking along d (the first one it meets coming from behind), in
    the uv coordinates of its vertices: (n, 2), or None if any does not fall. All at once: the triangles, spread into
    cells of the plane perpendicular to d, and each point tested only with those of its cell."""
    e1 = np.cross(d, [1.0, 0, 0] if abs(d[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(d, e1)
    v2 = np.stack([vert @ e1, vert @ e2], -1)
    p2 = np.stack([points @ e1, points @ e2], -1)
    t2 = v2[tri]                                           # (m, 3, 2)
    lo, hi = t2.min(1), t2.max(1)
    h = float(np.median((hi - lo).max(1))) or 1.0          # the side of a cell: that of a triangle
    origin = np.minimum(lo.min(0), p2.min(0))
    width = int(np.ceil((max(hi.max(0)[0], p2.max(0)[0]) - origin[0]) / h)) + 1
    c_lo = np.floor((lo - origin) / h).astype(np.int64)
    c_hi = np.floor((hi - origin) / h).astype(np.int64)
    # Each triangle in the cells its box touches (almost always 1 to 4).
    nx, ny = c_hi[:, 0] - c_lo[:, 0] + 1, c_hi[:, 1] - c_lo[:, 1] + 1
    how_many = nx * ny
    which = np.repeat(np.arange(len(tri)), how_many)
    k = np.arange(how_many.sum()) - np.repeat(np.cumsum(how_many) - how_many, how_many)
    cx = c_lo[which, 0] + k % nx[which]
    cy = c_lo[which, 1] + k // nx[which]
    cell = cy * width + cx
    order = np.argsort(cell, kind="stable")
    cell, which = cell[order], which[order]
    # Each point with the triangles of its cell.
    cp = np.floor((p2 - origin) / h).astype(np.int64)
    cell_p = cp[:, 1] * width + cp[:, 0]
    start, end = np.searchsorted(cell, cell_p, "left"), np.searchsorted(cell, cell_p, "right")
    n_cand = end - start
    point = np.repeat(np.arange(len(points)), n_cand)
    candidate = which[np.repeat(start, n_cand) + np.arange(n_cand.sum()) - np.repeat(np.cumsum(n_cand) - n_cand, n_cand)]
    a, b, c = t2[candidate, 0], t2[candidate, 1], t2[candidate, 2]
    q = p2[point]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
    det = np.where(np.abs(det) > 1e-30, det, 1e-30)
    s1 = ((q[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (q[:, 1] - a[:, 1])) / det
    s2 = ((b[:, 0] - a[:, 0]) * (q[:, 1] - a[:, 1]) - (q[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])) / det
    eps = 1e-9
    inside = (s1 >= -eps) & (s2 >= -eps) & (s1 + s2 <= 1 + eps)
    if not inside.any():
        return None
    point, candidate, s1, s2 = point[inside], candidate[inside], s1[inside], s2[inside]
    ia, ib, ic = tri[candidate].T
    deep = ((1 - s1 - s2)[:, None] * vert[ia] + s1[:, None] * vert[ib] + s2[:, None] * vert[ic]) @ d
    order = np.lexsort((deep, point))                     # per point, the first one along d
    point, candidate, s1, s2 = point[order], candidate[order], s1[order], s2[order]
    first = np.r_[True, point[1:] != point[:-1]]
    if first.sum() != len(points):
        return None
    ia, ib, ic = tri[candidate[first]].T
    s1, s2 = s1[first][:, None], s2[first][:, None]
    return (1 - s1 - s2) * uv[ia] + s1 * uv[ib] + s2 * uv[ic]


_PREPARED: dict = {}


def _prepare_holes(surface: Data, curves: Data, d: np.ndarray):
    """What «the biggest» and «the others» of Split surface share (two nodes with the same inputs): the curves taken
    to the (u, v) plane and checked. The last one is kept, so the second node does not repeat it."""
    import hashlib
    key = hashlib.blake2b(np.ascontiguousarray(surface.values, dtype=float).tobytes()
                            + np.ascontiguousarray(_curves_what_there_is(curves)).tobytes()
                            + np.asarray(d, float).tobytes() + repr(surface.kind.grid).encode(),
                            digest_size=16).digest()
    if key in _PREPARED:
        return _PREPARED[key]
    result = _prepare_holes_without_save(surface, curves, d)
    _PREPARED.clear()
    _PREPARED[key] = result
    return result


def _prepare_holes_without_save(surface: Data, curves: Data, d: np.ndarray):
    from . import vtk_light as vtk
    from .geometry import _inside
    grid = getattr(surface.kind, "grid", None)
    if grid is None or not curves.kind.closed or surface.levels:
        return _pattern(0)
    r, f, c = _grid_of(surface)
    if _closed_in(r, 0) or _closed_in(r, 1):
        return _pattern(1)
    # The surface in triangles, with their (u, v), to know where each point of the curves falls.
    uu, vv = np.meshgrid(np.linspace(0, 1, f), np.linspace(0, 1, c), indexing="ij")
    uv = np.stack([uu, vv], -1).reshape(-1, 2)
    vert = r.reshape(-1, 3)
    i, j = np.meshgrid(np.arange(f - 1), np.arange(c - 1), indexing="ij")
    a0, a1, b0, b1 = i * c + j, i * c + j + 1, (i + 1) * c + j, (i + 1) * c + j + 1
    tri = np.concatenate([np.stack([a0, b0, b1], -1).reshape(-1, 3), np.stack([a0, b1, a1], -1).reshape(-1, 3)])
    # The sizes of the surface along u and v: the (u, v) plane without stretching much.
    lu = float(np.linalg.norm(np.diff(r, axis=0), axis=-1).sum(axis=0).mean()) or 1.0
    lv = float(np.linalg.norm(np.diff(r, axis=1), axis=-1).sum(axis=1).mean()) or 1.0
    scale = np.array([lu, lv])
    # All the curves at once: where each point falls on the surface (looking along d), in (u, v).
    curves_ = []
    for curve in _curves_what_there_is(curves):
        curve = _without_padding(curve)
        if len(curve) > 1 and np.linalg.norm(curve[0] - curve[-1]) < 1e-9:
            curve = curve[:-1]
        if len(curve) >= 3 and np.ptp(curve, axis=0).max() >= 1e-9:   # (a circle of radius 0: nothing to make a hole with)
            curves_.append(curve)
    if not curves_:
        return _pattern(3)
    all_uv = _uv_looking(vert, tri, uv, np.vstack(curves_), d)
    if all_uv is None:
        return _pattern(2)                                   # some point does not fall on the surface
    holes = []
    cuts = np.cumsum([0] + [len(x) for x in curves_])
    for n_ in range(len(curves_)):
        q = all_uv[cuts[n_]:cuts[n_ + 1]]
        q = q * scale
        area = (q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]).sum() / 2
        if abs(area) < 1e-12:
            continue
        holes.append(q if area < 0 else q[::-1])           # the holes, clockwise
    if not holes:
        return _pattern(3)
    # That they touch neither the edge nor each other (if not, the general way).
    boxes = np.array([[h.min(0), h.max(0)] for h in holes])
    margin = 1e-6 * scale.max()
    if (boxes[:, 0] <= margin).any() or (boxes[:, 1, 0] >= lu - margin).any() or (boxes[:, 1, 1] >= lv - margin).any():
        return _pattern(4)
    order = np.argsort(boxes[:, 0, 0])
    for n_, a in enumerate(order):
        for b in order[n_ + 1:]:
            if boxes[b, 0, 0] > boxes[a, 1, 0]:
                break
            if boxes[b, 0, 1] <= boxes[a, 1, 1] and boxes[a, 0, 1] <= boxes[b, 1, 1] and \
                    _touch(holes[a], holes[b]):
                return _pattern(5)                                 # two holes that touch
    # The edge of the surface, in segments like those of its grid; the grid points inside (so that
    # the surface follows its shape), away from the holes.
    side = min(lu / (f - 1), lv / (c - 1))
    def runs(a, b):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / (side * 0.7))))
        return a + (b - a) * (np.arange(n) / n)[:, None]
    corners = np.array([[0, 0], [lu, 0], [lu, lv], [0, lv]], float)
    edge = np.vstack([runs(corners[k], corners[(k + 1) % 4]) for k in range(4)])
    def densify(h):
        next_ = np.roll(h, -1, 0)
        n = np.maximum(1, np.ceil(np.linalg.norm(next_ - h, axis=1) / (side * 0.7)).astype(int))
        if (n == 1).all():
            return h
        which = np.repeat(np.arange(len(h)), n)
        f_ = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
        return h[which] + (next_[which] - h[which]) * f_[:, None]
    holes = [densify(h) for h in holes]
    inside = (uv * scale)[(uv[:, 0] > 0) & (uv[:, 0] < 1) & (uv[:, 1] > 0) & (uv[:, 1] < 1)]
    outside = np.zeros(len(inside), bool)
    near = np.zeros(len(inside), bool)
    for h in holes:
        box = (inside[:, 0] > h[:, 0].min() - side) & (inside[:, 0] < h[:, 0].max() + side) & \
               (inside[:, 1] > h[:, 1].min() - side) & (inside[:, 1] < h[:, 1].max() + side)
        if box.any():
            idx = np.flatnonzero(box)
            outside[idx] |= _inside(inside[idx], h)
            near[idx] |= np.min(np.linalg.norm(inside[idx][:, None] - h[None], axis=2), axis=1) < side * 0.4
    return r, lu, lv, edge, holes, inside, outside, near


def _split_by_holes(surface: Data, curves: Data, d: np.ndarray, length: float, name,
                       what: str = 'all pieces') -> Data | str:
    """The fast way of Split surface, for closed curves that fall inside the surface without touching (some holes, a
    perforation): each curve is taken to the (u, v) plane of the surface, there the surface is triangulated with its
    holes and each hole apart, and it goes back to the surface. If it is not the case, why not (a text: the general way
    goes)."""
    prepared = _prepare_holes(surface, curves, d) if getattr(surface.kind, "grid", None) is not None \
        else _pattern(0)
    if isinstance(prepared, str):
        return prepared
    r, lu, lv, edge, holes, inside, outside, near = prepared
    from .geometry import _inside
    def to_surface(q):
        return _bilinear(r, np.clip(q[:, 0] / lu, 0, 1), np.clip(q[:, 1] / lv, 0, 1))
    pieces = []
    if what != 'the others':                              # the surface with its holes
        q2, faces = _delaunay_2d(edge, holes, inside[~outside & ~near])
        if not len(faces):
            return _pattern(6)
        pieces = [(to_surface(q2), faces)]
        if what == 'the largest':
            return _pick_pieces(pieces, what, name)
    # The cut-outs: each hole, with the grid points that fall inside. (One by one: all at once, with
    # holes very close, the triangulation loses some of their edges.)
    candidates = inside[outside & ~near]
    discs = []
    for h in holes:
        box = (candidates[:, 0] > h[:, 0].min()) & (candidates[:, 0] < h[:, 0].max()) & \
               (candidates[:, 1] > h[:, 1].min()) & (candidates[:, 1] < h[:, 1].max())
        there = candidates[box][_inside(candidates[box], h)] if box.any() else np.zeros((0, 2))
        counterclockwise = h[::-1]
        if not len(there) and _is_convex(counterclockwise):    # a small circle: as a fan, nothing more
            n_ = len(counterclockwise)
            cd = np.stack([np.zeros(n_ - 2, dtype=np.int64), np.arange(1, n_ - 1), np.arange(2, n_)], -1)
            discs.append((to_surface(counterclockwise), cd))
            continue
        qd, cd = _delaunay_2d(counterclockwise, [], there)
        if len(cd):
            discs.append((to_surface(qd), cd))
    def area(v, t):
        return float(np.linalg.norm(np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]), axis=1).sum() / 2)
    discs.sort(key=lambda x: -area(*x))
    return _pick_pieces([None] + discs if what == 'the others' else pieces + discs, what, name)


SPLIT_WHAT = ('all pieces', 'the largest', 'the others')
#: What the list of pieces can take up, at most (each one is padded up to the size of the biggest).
MEMORY_PIECES = 300 * 1024 ** 2


def _pick_pieces(pieces: list, what: str, name) -> Data:
    """The pieces (the first, the biggest) by `what`: all, the biggest (a single mesh) or the others."""
    from .meshes import kind_mesh
    if what == 'the largest':
        v, t = pieces[0]
        return Data(v, (), name, kind=kind_mesh(t))
    if what == 'the others':
        pieces = pieces[1:]
        if not pieces:
            raise ShapeError(tr('The surface stayed whole, in a single piece (no curve cuts it): there are no «others».'))
    elif len(pieces) > 1:
        more = max(len(t) for _, t in pieces)
        if len(pieces) * more * 9 * 8 > MEMORY_PIECES:
            raise ShapeError(tr('These are {n} pieces of very different sizes and together they would take too '
                                  'much memory: in «what», choose «the largest» or «the others» (in two nodes, if '
                                  'you want both).').format(n=len(pieces)))
    return _loose_triangles(pieces, name, "piece")


#: With more curves than this, the general way of Split surface (strip by strip) would take too long.
SPLIT_CURVES_FOR = 40


def split_surface(surface: Data, curves: Data, direction=(0.0, 0.0, 1.0), name: str | None = None,
                      what: str = 'all pieces') -> Data:
    """A surface split by some curves (*Split*), into pieces (the «piece» level), from the biggest to the smallest:
    each curve is projected onto the surface along `direction` (by default, from above) and cuts it. A curve that does
    not cross it from side to side does not split it. The pieces are picked with Pick; `what`: all, only the biggest (a
    perforated sheet) or the others (the cut-outs)."""
    if what not in SPLIT_WHAT:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in SPLIT_WHAT)))
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import vtk_to_numpy
    _require_curve(curves, "curves")
    vertices, triangles = _triangles(surface, "surface")
    d = np.asarray(_point(direction, "direction").values, dtype=float).reshape(3)
    if np.linalg.norm(d) < 1e-12:
        raise ShapeError(tr('The direction cannot be zero (0, 0, 0).'))
    d = d / np.linalg.norm(d)
    length = 2.0 * (float(np.linalg.norm(np.ptp(np.vstack([vertices, np.asarray(curves.values).reshape(-1, 3)]),
                                                axis=0))) or 1.0)
    if not len(_curves_what_there_is(curves)):                # no curve (a Filter that left nothing): whole
        return _pick_pieces([(vertices, np.asarray(triangles))], what, name)
    fast = _split_by_holes(surface, curves, d, length, name, what)
    if isinstance(fast, Data):
        return fast
    if len(_curves_what_there_is(curves)) > SPLIT_CURVES_FOR:
        raise ShapeError(tr('With more than {n} curves, Split surface can only work if they are closed, fall '
                              'inside the surface and do not touch (perforations); here {reason}. Reduce the '
                              'radii, or use fewer curves.').format(n=SPLIT_CURVES_FOR, reason=tr(fast)))
    ribbons_v, ribbons_t = [], []                           # each curve, a strip that goes through it along d
    u = np.cross(d, [1.0, 0.0, 0.0] if abs(d[0]) < 0.9 else [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    for number, c in enumerate(_curves_what_there_is(curves), 1):
        c = _without_padding(c)
        if curves.kind.closed:
            flat = np.column_stack([c @ u, c @ v])           # seen along d: edge-on, its strip folds onto itself
            area = 0.5 * abs(np.sum(flat[:, 0] * np.roll(flat[:, 1], -1) - np.roll(flat[:, 0], -1) * flat[:, 1]))
            if area < 1e-9 * length ** 2:                   # (and VTK's intersection hung with it)
                raise ShapeError(tr('Seen along the direction, curve {n} is only a line (it stands edge-on): it '
                                    'cannot split the surface. Change the direction or the plane of the curve.')
                                 .format(n=number))
            c = np.vstack([c, c[:1]])
        base = sum(len(x) for x in ribbons_v)
        ribbons_v.append(np.vstack([c - d * length, c + d * length]))
        n = len(c)
        for k in range(n - 1):
            a0, a1, b0, b1 = base + k, base + k + 1, base + n + k, base + n + k + 1
            ribbons_t += [(a0, a1, b1), (a0, b1, b0)]
    ribbon = _vtk(np.vstack(ribbons_v), np.array(ribbons_t, dtype=np.int64))
    filter_ = vtk.vtkIntersectionPolyDataFilter()
    filter_.SetInputData(0, _vtk(vertices, triangles))
    filter_.SetInputData(1, ribbon)
    filter_.SplitFirstOutputOn()
    filter_.SplitSecondOutputOff()
    filter_.GlobalWarningDisplayOff()
    filter_.Update()
    start = filter_.GetOutput(1)
    if start.GetNumberOfPolys() == 0:
        raise ShapeError(tr('The curves do not touch the surface (looking along the direction): there is nothing to split.'))
    p = vtk_to_numpy(start.GetPoints().GetData()).astype(float)
    t = vtk_to_numpy(start.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    # The points on the cut (on the strip): two triangles that only share points of the cut, in different pieces.
    distance = vtk.vtkImplicitPolyDataDistance()
    distance.SetInput(ribbon)
    size_ = float(np.ptp(p, axis=0).max()) or 1.0
    in_cut = np.array([abs(distance.EvaluateFunction(q.tolist())) < size_ * 1e-6 for q in p])
    parent = np.arange(len(t))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    sides: dict[tuple[int, int], int] = {}
    for k, (i0, i1, i2) in enumerate(t):
        for a_, b_ in ((i0, i1), (i1, i2), (i2, i0)):
            if in_cut[a_] and in_cut[b_]:
                continue                                  # a side on the cut: it does not join
            key = (min(a_, b_), max(a_, b_))
            if key in sides:
                parent[root(k)] = root(sides[key])
            else:
                sides[key] = k
    groups: dict[int, list[int]] = {}
    for k in range(len(t)):
        groups.setdefault(root(k), []).append(k)
    a_, b_, c_ = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b_ - a_, c_ - a_), axis=1)
    pieces = []
    for faces in sorted(groups.values(), key=lambda g: -area[g].sum()):
        if area[faces].sum() < 1e-6 * area.sum() or in_cut[t[faces]].all():
            continue                                      # a splinter of the cut (all on it, or without area): out
        sub = t[faces]
        used, new = np.unique(sub, return_inverse=True)
        pieces.append((p[used], new.reshape(-1, 3)))
    return _pick_pieces(pieces, what, name)
