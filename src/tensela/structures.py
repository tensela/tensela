"""Structures on surfaces (challenges): diagrid, space frame and Chebyshev net.

They work on the program's surfaces (their u × v grid) and give the usual geometry: members as lines (which Tube
turns into pieces), joints as points, rings as curves (which Cap turns into slabs).
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError, _require_size_, integer
from .geometry import CURVE, CLOSED_CURVE, POINT
from .language import tr
from .surfaces import _bilinear, _closed_in, _grid_normals, _grid_of

WHAT_DIAGRID = ('diagonals', 'crossings', 'rings')
BARS = ('straight', 'curves')
#: Points of each curved member (it follows the surface between its two joints).
POINTS_BAR_CURVE = 9


def _net(r: np.ndarray, nu: int, nv: int) -> tuple[np.ndarray, np.ndarray, bool, bool]:
    """The (u, v) fractions of the staggered net: 2·nu × 2·nv half steps (in a closed direction, without repeating the
    seam)."""
    cu, cv = _closed_in(r, 0), _closed_in(r, 1)
    us = np.arange(2 * nu + (0 if cu else 1)) / (2 * nu)
    vs = np.arange(2 * nv + (0 if cv else 1)) / (2 * nv)
    return us, vs, cu, cv


def diagrid(surface: Data, divisions_u=8, divisions_v=6, what: str = 'diagonals', members: str = 'straight',
            rings_along: str = "u", name: str | None = None, continuous: bool = False) -> Data:
    """A diagrid on a surface (a tower, a dome, a roof): diamonds of diagonal members, with `divisions_u` ×
    `divisions_v` diamonds. `what`: the **diagonals** (each member once; straight or curved following the surface), the
    **joints** or the **rings** (the belts that pass through the joints, along u or v: the slabs of a tower, with Cap)."""
    r, f, c = _grid_of(surface)
    if r.ndim > 3:
        raise ShapeError(tr('The diagrid goes on a single surface.'))
    nu, nv = integer(divisions_u), integer(divisions_v)
    if nu < 1 or nv < 1:
        raise ShapeError(tr('At least 1 diamond is needed in each direction.'))
    if what not in WHAT_DIAGRID:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_DIAGRID)))
    if members not in BARS:
        raise ShapeError(tr('The members can be: straight or curved.'))
    if rings_along not in ("u", "v"):
        raise ShapeError(tr('The rings run along u or along v.'))
    us, vs, cu, cv = _net(r, nu, nv)
    _require_size_({"joint": len(us) * len(vs)}, tr('The diagrid'))
    knots = [(i, j) for i in range(len(us)) for j in range(len(vs)) if (i + j) % 2 == 0]
    if what == 'crossings':
        p = _bilinear(r, us[[i for i, _ in knots]], vs[[j for _, j in knots]])
        return Data(p, ("joint",), name, kind=POINT)
    curves = members == 'curves'
    if what == 'diagonals' and continuous:
        return _diagonals_continuous(r, us, vs, cu, cv, curves, name)
    if what == 'diagonals':
        runs = []
        for i, j in knots:
            for dj in (1, -1):                              # upwards to the right and to the left
                i2, j2 = i + 1, j + dj
                if cu:
                    i2 %= len(us)
                elif i2 >= len(us):
                    continue
                if cv:
                    j2 %= len(vs)
                elif not 0 <= j2 < len(vs):
                    continue
                a = (us[i], vs[j])
                b = (us[i2] + (1.0 if cu and i2 < i else 0.0), vs[j2] + (1.0 if cv and dj > 0 and j2 < j else 0.0)
                     - (1.0 if cv and dj < 0 and j2 > j else 0.0))
                runs.append(_a_run(r, a, b, curves))
        return Data(np.stack(runs), ("member",), name, kind=CURVE)
    # Rings: through the joints of each row (along u, with v fixed) or of each column.
    lines = []
    if rings_along == "u":
        for j in range(len(vs)):
            ii = [i for i in range(len(us)) if (i + j) % 2 == 0]
            lines.append(_ring(r, us[ii], np.full(len(ii), vs[j]), cu, curves, axis=0))
        closed = cu
    else:
        for i in range(len(us)):
            jj = [j for j in range(len(vs)) if (i + j) % 2 == 0]
            lines.append(_ring(r, np.full(len(jj), us[i]), vs[jj], cv, curves, axis=1))
        closed = cv
    length = max(len(x) for x in lines)
    lines = [np.vstack([x, np.repeat(x[-1:], length - len(x), axis=0)]) for x in lines]
    return Data(np.stack(lines), ("ring",), name, kind=CLOSED_CURVE if closed else CURVE)


def _diagonals_continuous(r, us, vs, cu, cv, curves: bool, name) -> Data:
    """Each diagonal from end to end, as a single piece (in a tower, a helix): so the two families cross cleanly at
    the joints, without the cut of each member."""
    nu_, nv_ = len(us), len(vs)

    def inside(i, j):
        return (cu or 0 <= i < nu_) and (cv or 0 <= j < nv_)

    lines = []
    for dj in (1, -1):
        seen = set()
        for i0 in range(nu_):
            for j0 in range(nv_):
                if (i0 + j0) % 2 or (i0, j0) in seen or inside(i0 - 1, j0 - dj) and not (cu and cv):
                    continue                                    # it starts where there is no joint before
                steps, i, j = 0, i0, j0
                while True:
                    seen.add((i % nu_, j % nv_))
                    if not inside(i + 1, j + dj) or ((i + 1) % nu_, (j + dj) % nv_) == (i0, j0) and steps:
                        break
                    i, j, steps = i + 1, j + dj, steps + 1
                if steps == 0:
                    continue
                k = (POINTS_BAR_CURVE - 1 if curves else 1) * steps + 1
                m = np.linspace(0, steps, k)
                u = us[i0] + m * (us[1] - us[0])
                v = vs[j0] + m * dj * (vs[1] - vs[0])
                u = u % 1.0 if cu else np.clip(u, 0, 1)
                v = v % 1.0 if cv else np.clip(v, 0, 1)
                line = _bilinear(r, u, v)
                lines.append(line if dj > 0 else line[::-1])      # all in the direction of v
    if not lines:
        raise ShapeError(tr('With so few diamonds there are no diagonals.'))
    length = max(len(x) for x in lines)
    lines = [np.vstack([x, np.repeat(x[-1:], length - len(x), axis=0)]) for x in lines]
    return Data(np.stack(lines), ("diagonal",), name, kind=CURVE)


def _a_run(r, a, b, curves: bool) -> np.ndarray:
    """A member from fraction a to b (b may go past 1: it goes round through the seam)."""
    k = POINTS_BAR_CURVE if curves else 2
    t = np.linspace(0, 1, k)
    u = a[0] + (b[0] - a[0]) * t
    v = a[1] + (b[1] - a[1]) * t
    u = np.where(u > 1 + 1e-12, u - 1, u)
    v = np.where(v > 1 + 1e-12, v - 1, np.where(v < -1e-12, v + 1, v))
    return _bilinear(r, np.clip(u, 0, 1), np.clip(v, 0, 1))


def _ring(r, u, v, closed: bool, curves: bool, axis: int) -> np.ndarray:
    """A ring through some joints (in order): straight between them, or following the surface."""
    if not curves:
        return _bilinear(r, u, v)
    k = POINTS_BAR_CURVE
    runs = []
    pairs = list(zip(range(len(u) - 1), range(1, len(u))))
    if closed:
        pairs.append((len(u) - 1, 0))
    for a, b in pairs:
        ua, ub, goes, vb = u[a], u[b], v[a], v[b]
        if closed and axis == 0 and ub < ua:
            ub += 1.0
        if closed and axis == 1 and vb < goes:
            vb += 1.0
        runs.append(_a_run(r, (ua, goes), (ub, vb), True)[:-1])
    if not closed:
        runs.append(_bilinear(r, u[-1:], v[-1:]))
    return np.vstack(runs)


WHAT_MESH_SPACE = ('all members', 'top chord', 'bottom chord', 'diagonals', 'top crossings',
                      'bottom crossings')


def mesh_space(surface: Data, divisions_u=8, divisions_v=6, truss_depth=1.0, what: str = 'all members',
                   name: str | None = None) -> Data:
    """A space frame on a surface: the **top chord** is a grid of `divisions_u` × `divisions_v` modules on the
    surface; the **bottom** one, another grid shifted half a module (through the centres) and lowered by `truss_depth`
    along the normal (towards the back of the face; with a negative depth, to the other side); the **diagonals** join
    each bottom joint with the four corners of its module: square-based pyramids."""
    r, f, c = _grid_of(surface)
    if r.ndim > 3:
        raise ShapeError(tr('The space frame goes on a single surface.'))
    nu, nv = integer(divisions_u), integer(divisions_v)
    if nu < 1 or nv < 1:
        raise ShapeError(tr('At least 1 module is needed in each direction.'))
    if what not in WHAT_MESH_SPACE:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_MESH_SPACE)))
    truss_depth = float(np.asarray(getattr(truss_depth, "values", truss_depth), float).ravel()[0])
    cu, cv = _closed_in(r, 0), _closed_in(r, 1)
    _require_size_({"joint": (nu + 1) * (nv + 1) * 2}, tr('The space frame'))
    # Top: (nu + 1) × (nv + 1) joints (without repeating the seam in a closed one). Bottom: nu × nv, at the centres.
    ia, ja = nu if cu else nu + 1, nv if cv else nv + 1
    ua, goes = np.meshgrid(np.arange(ia) / nu, np.arange(ja) / nv, indexing="ij")
    above = _bilinear(r, ua, goes)
    ub, vb = np.meshgrid((np.arange(nu) + 0.5) / nu, (np.arange(nv) + 0.5) / nv, indexing="ij")
    n = _bilinear(_grid_normals(r), ub, vb)
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
    below = _bilinear(r, ub, vb) - truss_depth * n
    if what == 'top crossings':
        return Data(above.reshape(-1, 3), ("joint",), name, kind=POINT)
    if what == 'bottom crossings':
        return Data(below.reshape(-1, 3), ("joint",), name, kind=POINT)

    def above_in(i, j):
        return above[i % ia if cu else i, j % ja if cv else j]

    upper, lower, diagonals = [], [], []
    for i in range(ia):
        for j in range(ja):
            if i + 1 < ia or cu:
                upper.append((above[i, j], above_in(i + 1, j)))
            if j + 1 < ja or cv:
                upper.append((above[i, j], above_in(i, j + 1)))
    for i in range(nu):
        for j in range(nv):
            if i + 1 < nu or cu:
                lower.append((below[i, j], below[(i + 1) % nu, j]))
            if j + 1 < nv or cv:
                lower.append((below[i, j], below[i, (j + 1) % nv]))
            for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1)):
                diagonals.append((below[i, j], above_in(i + di, j + dj)))
    if cu and nu < 3 or cv and nv < 3:          # with 1 or 2 modules around, the members repeat
        def unique(members):
            views, remain = set(), []
            for a, b in members:
                k = frozenset((tuple(np.round(a, 6)), tuple(np.round(b, 6))))
                if k not in views and len(k) == 2:
                    views.add(k)
                    remain.append((a, b))
            return remain
        upper, lower = unique(upper), unique(lower)
    members = {'top chord': upper, 'bottom chord': lower, 'diagonals': diagonals,
              'all members': upper + lower + diagonals}[what]
    if not members:
        raise ShapeError(tr('With a single module there is no bottom chord: raise the divisions.'))
    return Data(np.array(members, float), ("member",), name, kind=CURVE)


WHAT_CHEBYSHEV = ('all laths', 'laths along u', 'laths along v', 'knots')


def chebyshev_net(surface: Data, u=0.5, v=0.5, step=1.0, count=10, angle=90.0, rotation=0.0,
                     what: str = 'all laths', name: str | None = None) -> Data:
    """A Chebyshev net on a surface: quadrilaterals with their four sides of the same length (`step`), as a net of
    battens that bends (gridshell) or a falling cloth settles. It is built with a compass: from the point (u, v) two
    threads leave following the surface (with `angle` between them; `rotation` turns both), and each new joint is one
    step from its two neighbours and on the surface. It grows `count` joints to each side, as far as the surface reaches."""
    r, f, c = _grid_of(surface)
    if r.ndim > 3:
        raise ShapeError(tr('The Chebyshev net goes on a single surface.'))
    if what not in WHAT_CHEBYSHEV:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_CHEBYSHEV)))
    one = lambda x: float(np.asarray(getattr(x, "values", x), float).ravel()[0])
    u0, v0, length, ang, turn = one(u), one(v), one(step), np.radians(one(angle)), np.radians(one(rotation))
    n = integer(count)
    if length <= 0:
        raise ShapeError(tr('The step must be greater than 0.'))
    if n < 1:
        raise ShapeError(tr('At least 1 node is needed on each side.'))
    if not 1 <= abs(np.degrees(ang)) % 180 <= 179:
        raise ShapeError(tr('With an angle of 0° or 180° the two laths run together: there is no net.'))
    _require_size_({"joint": (2 * n + 1) ** 2}, tr('The Chebyshev net'))
    cu, cv = _closed_in(r, 0), _closed_in(r, 1)
    sup = _Evaluator(r, cu, cv)
    # The two threads from the origin, in the tangent plane.
    st0 = np.array([[u0, v0]])
    p0, su, sv = sup.point(st0)[0], *[d[0] for d in sup.derivatives(st0)]
    normal = np.cross(su, sv)
    if np.linalg.norm(normal) < 1e-12 or not sup.inside(st0)[0]:
        raise ShapeError(tr('The starting point (u, v) must be on the surface, from 0 to 1.'))
    normal /= np.linalg.norm(normal)
    e = su / np.linalg.norm(su)

    def rotate(x, a):
        return x * np.cos(a) + np.cross(normal, x) * np.sin(a)

    d1, d2 = rotate(e, turn), rotate(e, turn + ang)
    P = np.full((2 * n + 1, 2 * n + 1, 3), np.nan)
    ST = np.full((2 * n + 1, 2 * n + 1, 2), np.nan)
    P[n, n], ST[n, n] = p0, st0[0]
    # Threads: the four at once (+d1, −d1, +d2, −d2).
    dirs = np.array([d1, -d1, d2, -d2])
    places = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    p, st, vivid = np.repeat(p0[None], 4, 0), np.repeat(st0, 4, 0), np.ones(4, bool)
    for k in range(1, n + 1):
        st_n = sup.straight_step(p, dirs, st, length)
        q = sup.point(st_n)
        vivid &= sup.inside(st_n) & np.isclose(np.linalg.norm(q - p, axis=1), length, rtol=1e-3)
        new_ = q - p
        dirs = new_ / np.maximum(np.linalg.norm(new_, axis=1, keepdims=True), 1e-12)
        for m, (a, b) in enumerate(places):
            if vivid[m]:
                P[n + a * k, n + b * k], ST[n + a * k, n + b * k] = q[m], st_n[m]
        p, st = q, st_n
    # The rest, by fronts (|i| + |j| = k): each joint one step from its two neighbours towards the origin.
    for k in range(2, 2 * n + 1):
        cases = [(i, j) for i in range(-n, n + 1) for j in range(-n, n + 1)
                 if i and j and abs(i) + abs(j) == k]
        if not cases:
            continue
        idx = np.array(cases)
        yes, sj = np.sign(idx[:, 0]), np.sign(idx[:, 1])
        a = P[n + idx[:, 0] - yes, n + idx[:, 1]]
        b = P[n + idx[:, 0], n + idx[:, 1] - sj]
        cdiag = P[n + idx[:, 0] - yes, n + idx[:, 1] - sj]
        sa = ST[n + idx[:, 0] - yes, n + idx[:, 1]]
        sb = ST[n + idx[:, 0], n + idx[:, 1] - sj]
        sc = ST[n + idx[:, 0] - yes, n + idx[:, 1] - sj]
        ok = ~(np.isnan(a).any(1) | np.isnan(b).any(1) | np.isnan(cdiag).any(1))
        if not ok.any():
            continue
        guide = sa[ok] + sb[ok] - sc[ok]                       # the parallelogram at (u, v), to start
        guide = sup.more_near(a[ok] + b[ok] - cdiag[ok], guide)
        st_n = sup.compass(a[ok], b[ok], length, guide)
        q = sup.point(st_n)
        well = (sup.inside(st_n) & np.isclose(np.linalg.norm(q - a[ok], axis=1), length, rtol=1e-4)
                & np.isclose(np.linalg.norm(q - b[ok], axis=1), length, rtol=1e-4)
                & (np.linalg.norm(q - cdiag[ok], axis=1) > 0.1 * length))
        for (i, j), point, s_, b_ in zip(idx[ok], q, st_n, well):
            if b_:
                P[n + i, n + j], ST[n + i, n + j] = point, s_
    if what == 'knots':
        knots = P[~np.isnan(P).any(-1)]
        return Data(knots, ("joint",), name, kind=POINT)
    lines = []
    if what in ('all laths', 'laths along u'):
        lines += [P[:, j] for j in range(2 * n + 1)]
    if what in ('all laths', 'laths along v'):
        lines += [P[i, :] for i in range(2 * n + 1)]
    runs = []
    for x in lines:
        well = ~np.isnan(x).any(-1)
        if well.sum() >= 2:
            runs.append(x[well])                          # the valid ones of a row come in a row
    if not runs:
        raise ShapeError(tr('The net does not fit on the surface: reduce the step or move the starting point.'))
    length_max = max(len(t) for t in runs)
    runs = [np.vstack([t, np.repeat(t[-1:], length_max - len(t), axis=0)]) for t in runs]
    return Data(np.stack(runs), ("batten",), name, kind=CURVE)


class _Evaluator:
    """The surface as a function of (s, t) in 0–1 (bilinear over its grid), with its derivatives and the computations
    of the net: the closest point, a step that follows the surface and the compass (at a length from two points)."""
    H = 1e-5

    def __init__(self, r, cu, cv):
        self.r, self.cu, self.cv = r, cu, cv

    def _adjust(self, st):
        s = st[:, 0] % 1.0 if self.cu else np.clip(st[:, 0], 0, 1)
        t = st[:, 1] % 1.0 if self.cv else np.clip(st[:, 1], 0, 1)
        return s, t

    def point(self, st):
        return _bilinear(self.r, *self._adjust(np.asarray(st, float)))

    def derivatives(self, st):
        h = self.H
        du, dv = np.array([h, 0.0]), np.array([0.0, h])
        return ((self.point(st + du) - self.point(st - du)) / (2 * h),
                (self.point(st + dv) - self.point(st - dv)) / (2 * h))

    def inside(self, st):
        ok = np.ones(len(st), bool)
        if not self.cu:
            ok &= (st[:, 0] >= -1e-9) & (st[:, 0] <= 1 + 1e-9)
        if not self.cv:
            ok &= (st[:, 1] >= -1e-9) & (st[:, 1] <= 1 + 1e-9)
        return ok

    def _clamp(self, st):
        """Without going far off the surface while searching (outside, the bilinear stays at the edge)."""
        st = st.copy()
        if not self.cu:
            st[:, 0] = np.clip(st[:, 0], -0.05, 1.05)
        if not self.cv:
            st[:, 1] = np.clip(st[:, 1], -0.05, 1.05)
        return st

    def more_near(self, g, st):
        """The (s, t) of the point of the surface closest to g, starting at st (Gauss-Newton)."""
        st = np.array(st, float)
        for _ in range(12):
            su, sv = self.derivatives(st)
            res = self.point(st) - g
            J = np.stack([su, sv], -1)                          # (N, 3, 2)
            JtJ = np.einsum("nki,nkj->nij", J, J) + 1e-12 * np.eye(2)
            step = -np.linalg.solve(JtJ, np.einsum("nki,nk->ni", J, res)[..., None])[..., 0]
            st = self._clamp(st + step)
            if np.abs(step).max() < 1e-10:
                break
        return st

    def straight_step(self, p, d, st, length):
        """A step of length `length` from p towards d, on the surface (the thread follows the surface)."""
        st = self.more_near(p + d * length, st)
        for _ in range(4):
            q = self.point(st)
            dq = q - p
            dq /= np.maximum(np.linalg.norm(dq, axis=1, keepdims=True), 1e-12)
            st = self.more_near(p + dq * length, st)
        return st

    def compass(self, a, b, length, st):
        """The (s, t) of the point of the surface at `length` from a and from b, starting at st (Newton)."""
        st = np.array(st, float)
        for _ in range(25):
            q = self.point(st)
            su, sv = self.derivatives(st)
            F = np.stack([((q - a) ** 2).sum(1) - length ** 2, ((q - b) ** 2).sum(1) - length ** 2], 1)
            J = 2 * np.stack([np.stack([((q - a) * su).sum(1), ((q - a) * sv).sum(1)], 1),
                              np.stack([((q - b) * su).sum(1), ((q - b) * sv).sum(1)], 1)], 1)
            det = np.linalg.det(J)
            J = J + (np.abs(det) < 1e-14)[:, None, None] * 1e-9 * np.eye(2)
            step = -np.linalg.solve(J, F[..., None])[..., 0]
            cap = np.maximum(np.abs(step).max(1, keepdims=True) / 0.05, 1.0)   # short steps: do not jump far
            st = self._clamp(st + step / cap)
            if np.abs(F).max() < 1e-12 * length ** 2:
                break
        return st
