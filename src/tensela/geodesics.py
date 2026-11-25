"""Geodesics: the shortest path between two points over a surface (for instance, a gridshell whose bars are
geodesics between points of its edge ring).

A geodesic is what a stretched string does on the surface: it never bends sideways, only with the surface. Laths
of timber or tubes laid along geodesics stay straight in their own plane, so they can be bent onto the shape without
twisting: that is why gridshells use them.

How it is found, in two steps, both on the flat map of the surface (its u and v, from 0 to 1):

1. **The way round.** A coarse net of the surface (about `detail` points along its longer side) and the shortest
   path over that net, through its sixteen neighbours (the eight around and the eight a knight's move away), with
   the real length of each step in space. This picks which side of a hill the path goes by.
2. **Pulling it tight.** That path, as a chain of points on the surface, is pulled straight: each point moves
   towards the middle of its two neighbours and back onto the surface, again and again, with more points each round,
   until it no longer gets shorter. Like a string pulled at both ends.

Where the geodesics cross each other (on the map, so it is exact on the surface) are the knots of the gridshell; the
pieces of each geodesic between its knots are its bars.
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError, align
from .geometry import CURVE, POINT, _point
from .language import tr
from .surfaces import _bilinear, _closed_in, _grid_of, closest_uv

SHOW = ('curves', 'lengths', 'crossings', 'bars')

#: The sixteen steps of the coarse net: the eight neighbours and the eight knight's moves.
_STEPS = [(di, dj) for di in (-2, -1, 0, 1, 2) for dj in (-2, -1, 0, 1, 2)
          if (di, dj) != (0, 0) and (abs(di) < 2 or abs(dj) < 2) and not (abs(di) == 2 and dj == 0)
          and not (abs(dj) == 2 and di == 0)]
#: How many points the chain has in each round of pulling it tight, and in the end.
_ROUNDS = (17, 33, 65)


def _evaluate(r: np.ndarray, uv: np.ndarray, cu: bool, cv: bool) -> np.ndarray:
    """Points of the surface at u v (… , 2), the closed directions wrapped around."""
    u = np.mod(uv[..., 0], 1.0) if cu else np.clip(uv[..., 0], 0.0, 1.0)
    v = np.mod(uv[..., 1], 1.0) if cv else np.clip(uv[..., 1], 0.0, 1.0)
    return _bilinear(r, u, v)


def _net(r: np.ndarray, detail: int, cu: bool, cv: bool):
    """The coarse net: its u v, its points, and the length of each of the sixteen steps from each node (inf where it
    leaves the surface)."""
    rows_length = float(np.linalg.norm(np.diff(r, axis=0), axis=-1).sum(0).max())
    cols_length = float(np.linalg.norm(np.diff(r, axis=1), axis=-1).sum(1).max())
    longest = max(rows_length, cols_length, 1e-12)
    # Each side at least half the detail: a dome measured round its edge is long, but its way up to the top counts too.
    n = max(4, detail // 2, int(round(detail * rows_length / longest)))
    m = max(4, detail // 2, int(round(detail * cols_length / longest)))
    us = np.arange(n) / n if cu else np.linspace(0.0, 1.0, n)
    vs = np.arange(m) / m if cv else np.linspace(0.0, 1.0, m)
    uv = np.stack(np.meshgrid(us, vs, indexing="ij"), -1)
    p = _evaluate(r, uv, cu, cv)
    weights = []
    for di, dj in _STEPS:
        q = _shifted(p, di, dj, cu, cv, np.nan, axes=(0, 1))
        w = np.linalg.norm(q - p, axis=-1)
        weights.append(np.where(np.isnan(w), np.inf, w))
    return uv, p, np.array(weights)


def _shifted(a: np.ndarray, di: int, dj: int, cu: bool, cv: bool, fill, axes=(-2, -1)) -> np.ndarray:
    """a[..., i + di, j + dj, ...] at each node i, j of the net (on the two `axes`): wrapped in a closed direction,
    `fill` past the edge of an open one."""
    out = a
    for axis, step, closed in ((axes[0], di, cu), (axes[1], dj, cv)):
        if step == 0:
            continue
        out = np.roll(out, -step, axis=axis)
        if not closed:
            index = [slice(None)] * out.ndim
            index[axis] = slice(-step, None) if step > 0 else slice(None, -step)
            out[tuple(index)] = fill
    return out


def _distances(weights: np.ndarray, sources: np.ndarray, cu: bool, cv: bool) -> np.ndarray:
    """The shortest distance over the net from each source node to every node (S, n, m): all the sources at once,
    relaxing every step until nothing gets shorter."""
    n, m = weights.shape[1:]
    d = np.full((len(sources), n, m), np.inf)
    d[np.arange(len(sources)), sources[:, 0], sources[:, 1]] = 0.0
    for _ in range(4 * (n + m)):
        best = d
        for (di, dj), w in zip(_STEPS, weights):
            best = np.minimum(best, _shifted(d, di, dj, cu, cv, np.inf) + w)
        if np.array_equal(best, d):
            break
        d = best
    return d


def _way_back(d: np.ndarray, weights: np.ndarray, end: tuple, cu: bool, cv: bool) -> list:
    """The nodes of the shortest path, walking back from the end to the source (where the distance is 0): each time
    to the neighbour it came from. Never to a node already passed: round the top of a dome all the nodes are one
    point, steps of no length, and the walk would go round it for ever. Between equals, the one nearer the source."""
    n, m = d.shape
    path = [end]
    passed = {end}
    i, j = end
    for _ in range(n * m):
        if d[i, j] <= 0.0:
            break
        best, step = (np.inf, np.inf), None
        for k, (di, dj) in enumerate(_STEPS):
            # The step from (i, j) to its neighbour has the same length as the one back.
            ii, jj = i + di, j + dj
            if cu:
                ii %= n
            if cv:
                jj %= m
            if not (0 <= ii < n and 0 <= jj < m) or not np.isfinite(weights[k, i, j]) or (ii, jj) in passed:
                continue
            value = (round(float(d[ii, jj] + weights[k, i, j]), 12), float(d[ii, jj]))
            if value < best:
                best, step = value, (ii, jj)
        if step is None:
            break
        i, j = step
        path.append(step)
        passed.add(step)
    return path[::-1]


def _unwrapped(uv: np.ndarray, cu: bool, cv: bool) -> np.ndarray:
    """Chains on the map (…, K, 2) without jumps across the seam of a closed direction: each step the short way."""
    out = uv.copy()
    for axis, closed in ((0, cu), (1, cv)):
        if closed:
            step = np.diff(out[..., axis], axis=-1)
            out[..., 1:, axis] = out[..., :1, axis] + np.cumsum(step - np.round(step), axis=-1)
    return out


def _resampled(uv: np.ndarray, r: np.ndarray, count: int, cu: bool, cv: bool) -> np.ndarray:
    """`count` points along a chain on the map, evenly spaced along its length in space."""
    p = _evaluate(r, uv, cu, cv)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=-1))])
    if s[-1] <= 1e-15:
        return np.linspace(uv[0], uv[-1], count)
    t = np.linspace(0.0, s[-1], count)
    return np.stack([np.interp(t, s, uv[:, 0]), np.interp(t, s, uv[:, 1])], -1)


def _block_tridiagonal(own: np.ndarray, after: np.ndarray, g: np.ndarray) -> np.ndarray:
    """Solves, for each chain at once, the system of 2 × 2 blocks Bᵢ δᵢ + Cᵢ δᵢ₊₁ + Cᵢ₋₁ᵀ δᵢ₋₁ = gᵢ, with Bᵢ = `own`
    (P, n, 2, 2) and Cᵢ = `after` (P, n − 1, 2, 2): forward elimination and back substitution (Thomas)."""
    count, n = g.shape[:2]
    upper = np.zeros((count, n, 2, 2))
    right = np.zeros((count, n, 2))
    for i in range(n):
        m = own[:, i].copy()
        rhs = g[:, i].copy()
        if i:
            below = np.swapaxes(after[:, i - 1], 1, 2)
            m -= below @ upper[:, i - 1]
            rhs -= (below @ right[:, i - 1, :, None])[..., 0]
        inverse = np.linalg.inv(m)
        if i < n - 1:
            upper[:, i] = inverse @ after[:, i]
        right[:, i] = (inverse @ rhs[..., None])[..., 0]
    out = np.zeros_like(right)
    out[:, -1] = right[:, -1]
    for i in range(n - 2, -1, -1):
        out[:, i] = right[:, i] - (upper[:, i] @ out[:, i + 1, :, None])[..., 0]
    return out


def _energy(r: np.ndarray, uv: np.ndarray, cu: bool, cv: bool) -> np.ndarray:
    """The sum of the squared steps in space of each chain (P,): the least, the tightest."""
    return (np.diff(_evaluate(r, uv, cu, cv), axis=1) ** 2).sum((-1, -2))


def _inside(uv: np.ndarray, cu: bool, cv: bool) -> np.ndarray:
    """The u v kept on the map in an open direction (a closed one goes round)."""
    if not cu:
        uv[..., 0] = np.clip(uv[..., 0], 0.0, 1.0)
    if not cv:
        uv[..., 1] = np.clip(uv[..., 1], 0.0, 1.0)
    return uv


def _poles(r: np.ndarray, cu: bool, cv: bool) -> list:
    """Where the surface gathers into a point (the top of a dome, the tip of a cone): (radial axis, at 0 or at 1).
    Only round a closed direction: a whole row (or column) at one point."""
    tolerance = 1e-9 * (float(np.ptp(r)) or 1.0)
    found = []
    for axis, closed in ((0, cv), (1, cu)):
        if not closed:
            continue
        for end in (0, 1):
            edge = r[-end] if axis == 0 else r[:, -end]
            if float(np.ptp(edge, axis=0).max()) < tolerance:
                found.append((axis, end))
    return found


def _charts(middle: np.ndarray, poles: list):
    """How each inner point moves: in u v, or, near a pole, in a little flat map around it (ρ cos φ, ρ sin φ, with
    ρ the distance to the pole on the map and φ the turn round it), where a short step is a short move. Gives T,
    the change of u v per change of that map (…, 2, 2), and a function that moves the points by a step in it."""
    shape = middle.shape[:-1]
    t = np.broadcast_to(np.eye(2), shape + (2, 2)).copy()
    zones = []
    for axis, end in poles:
        other = 1 - axis
        rho = middle[..., axis] if end == 0 else 1.0 - middle[..., axis]
        zone = rho < 0.5
        phi = 2 * np.pi * middle[..., other]
        sign = 1.0 if end == 0 else -1.0
        safe = np.maximum(rho, 1e-9)
        cos, sin = np.cos(phi), np.sin(phi)
        t[zone, axis, 0], t[zone, axis, 1] = sign * cos[zone], sign * sin[zone]
        t[zone, other, 0] = -sin[zone] / (2 * np.pi * safe[zone])
        t[zone, other, 1] = cos[zone] / (2 * np.pi * safe[zone])
        zones.append((axis, end, zone, rho, phi))

    def advance(delta: np.ndarray) -> np.ndarray:
        out = middle + delta
        for axis, end, zone, rho, phi in zones:
            other = 1 - axis
            q = np.stack([rho * np.cos(phi), rho * np.sin(phi)], -1) + delta
            new_rho = np.linalg.norm(q, axis=-1)
            turn = np.arctan2(q[..., 1], q[..., 0]) / (2 * np.pi)
            v = middle[..., other] + (np.mod(turn - middle[..., other] + 0.5, 1.0) - 0.5)
            out[..., axis] = np.where(zone, new_rho if end == 0 else 1.0 - new_rho, out[..., axis])
            out[..., other] = np.where(zone, v, out[..., other])
        return out
    return t, advance


def _tight(uv: np.ndarray, r: np.ndarray, cu: bool, cv: bool, f: int, c: int) -> np.ndarray:
    """Pulls chains on the map (P, K, 2) tight on the surface. Each round moves every inner point at once
    (Gauss-Newton), so that the sum of the squared steps in space is the least it can be: with the ends held, that is
    the shortest chain, its points evenly spaced. A chain that a whole step would not shorten takes half, or a
    quarter… A few rounds are enough."""
    h = 1e-6
    limit = 1.0 / max(min(f, c) - 1, 1)
    count, k = uv.shape[:2]
    if k <= 2:
        return uv
    poles = _poles(r, cu, cv)
    energy = _energy(r, uv, cu, cv)
    for _ in range(80):
        p = _evaluate(r, uv, cu, cv)
        middle = uv[:, 1:-1]
        su = (_evaluate(r, middle + [h, 0.0], cu, cv) - _evaluate(r, middle - [h, 0.0], cu, cv)) / (2 * h)
        sv = (_evaluate(r, middle + [0.0, h], cu, cv) - _evaluate(r, middle - [0.0, h], cu, cv)) / (2 * h)
        t, advance = _charts(middle, poles)
        jac = np.stack([su, sv], -1) @ t                              # (P, inner, 3, 2)
        d = np.diff(p, axis=1)                                        # (P, K - 1, 3)
        # The normal equations: 2 JᵢᵀJᵢ δᵢ − JᵢᵀJᵢ₋₁ δᵢ₋₁ − JᵢᵀJᵢ₊₁ δᵢ₊₁ = Jᵢᵀ (dᵢ − dᵢ₋₁), with a little damping
        # where a direction goes nowhere.
        g = np.einsum('pikc,pik->pic', jac, d[:, 1:] - d[:, :-1])
        own = 2 * np.einsum('pika,pikb->piab', jac, jac)
        own += (1e-6 * np.trace(own, axis1=2, axis2=3).mean(1) + 1e-300)[:, None, None, None] * np.eye(2)
        after = -np.einsum('pika,pikb->piab', jac[:, :-1], jac[:, 1:])
        step = np.clip(_block_tridiagonal(own, after, g), -limit, limit)
        size = np.ones(count)
        best, best_energy = uv.copy(), energy.copy()
        pending = np.ones(count, bool)
        for _ in range(12):
            trial = uv.copy()
            trial[:, 1:-1] = _inside(advance(size[:, None, None] * step), cu, cv)
            trial_energy = _energy(r, trial, cu, cv)
            better = pending & (trial_energy < best_energy)
            best[better], best_energy[better] = trial[better], trial_energy[better]
            pending &= ~better
            if not pending.any():
                break
            size[pending] *= 0.5
        gain = (energy - best_energy) / np.maximum(energy, 1e-300)
        uv, energy = best, best_energy
        if gain.max() < 1e-12:
            break
    return uv


#: The last geodesics found, by surface, points and detail: the curves and their crossings (two nodes on the same
#: geodesics, or a slider that does not touch them) do not find them again.
_LAST: dict = {}


def _paths(r: np.ndarray, starts: np.ndarray, ends: np.ndarray, detail: int):
    """The geodesics on one surface between pairs of points: their u v (P, K, 2) and points (P, K, 3)."""
    key = (r.shape, r.tobytes(), starts.tobytes(), ends.tobytes(), detail)
    if key in _LAST:
        uv, p, closed = _LAST[key]
        return uv.copy(), p.copy(), closed
    found = _find_paths(r, starts, ends, detail)
    if len(_LAST) >= 8:
        _LAST.pop(next(iter(_LAST)))
    _LAST[key] = found
    uv, p, closed = found
    return uv.copy(), p.copy(), closed


def _find_paths(r: np.ndarray, starts: np.ndarray, ends: np.ndarray, detail: int):
    f, c = r.shape[:2]
    cu, cv = _closed_in(r, 0), _closed_in(r, 1)
    uv0 = closest_uv(starts, r)
    uv1 = closest_uv(ends, r)
    net_uv, _, weights = _net(r, detail, cu, cv)
    n, m = net_uv.shape[:2]

    def node(uv):
        i = np.round(uv[:, 0] * (n if cu else n - 1)).astype(int) % n
        j = np.round(uv[:, 1] * (m if cv else m - 1)).astype(int) % m
        return np.stack([i, j], -1)
    a, b = node(uv0), node(uv1)
    sources, which = np.unique(a, axis=0, return_inverse=True)
    d = _distances(weights, sources, cu, cv)
    chains = []
    for p in range(len(starts)):
        nodes = _way_back(d[which.ravel()[p]], weights, tuple(b[p]), cu, cv)
        middle = np.array([net_uv[i, j] for i, j in nodes[1:-1]]).reshape(-1, 2)
        chain = _unwrapped(np.vstack([uv0[p], middle, uv1[p]]), cu, cv)
        chains.append(chain)
    uv = np.array([_resampled(ch, r, _ROUNDS[0], cu, cv) for ch in chains])
    for round_ in range(len(_ROUNDS)):
        if round_:
            middle = 0.5 * (uv[:, :-1] + uv[:, 1:])
            finer = np.empty((len(uv), 2 * uv.shape[1] - 1, 2))
            finer[:, 0::2], finer[:, 1::2] = uv, middle
            uv = finer
        uv = _unwrapped(_tight(uv, r, cu, cv, f, c), cu, cv)
    return uv, _evaluate(r, uv, cu, cv), (cu, cv)


def _knots(uvs: np.ndarray, points: np.ndarray, r: np.ndarray, closed: tuple):
    """The crossings of the geodesics of one surface (points) and the bars between them: found on the map, where two
    chains cross exactly, each geodesic against all the later ones at once."""
    cu, cv = closed
    count, k = uvs.shape[:2]
    shifts = [(du, dv) for du in ((-1, 0, 1) if cu else (0,)) for dv in ((-1, 0, 1) if cv else (0,))]
    hits = []                                                # (g, position along g, h, position along h, u v)
    start, run = uvs[:, :-1], np.diff(uvs, axis=1)           # (P, K − 1, 2)
    for g in range(count - 1):
        p, r_ = start[g][:, None, None, :], run[g][:, None, None, :]
        for du, dv in shifts:
            q, s_ = start[g + 1:][None] + np.array([du, dv], float), run[g + 1:][None]
            cross = r_[..., 0] * s_[..., 1] - r_[..., 1] * s_[..., 0]
            qp = q - p
            with np.errstate(divide="ignore", invalid="ignore"):
                t = (qp[..., 0] * s_[..., 1] - qp[..., 1] * s_[..., 0]) / cross
                w = (qp[..., 0] * r_[..., 1] - qp[..., 1] * r_[..., 0]) / cross
            hit = (np.abs(cross) > 1e-15) & (t >= 0) & (t < 1) & (w >= 0) & (w < 1)
            i, h, j = np.nonzero(hit)
            at_g, at_h = i + t[i, h, j], j + w[i, h, j]
            # Not at the ends two bars share (a point of the ring).
            inside = (np.minimum(at_g, k - 1 - at_g) > 1e-6) & (np.minimum(at_h, k - 1 - at_h) > 1e-6)
            i, h, at_g, at_h = i[inside], h[inside], at_g[inside], at_h[inside]
            uv = uvs[g, i] + (at_g - i)[:, None] * run[g, i]
            hits += [(g, a, g + 1 + b, c, x) for a, b, c, x in zip(at_g, h, at_h, uv)]
    crossings = _merged(_evaluate(r, np.array([x[4] for x in hits]).reshape(-1, 2), cu, cv),
                        _MERGE * (float(np.ptp(r.reshape(-1, 3), axis=0).max()) or 1.0))
    where = [[] for _ in range(count)]                       # (position along the chain, point)
    for (g, at_g, h, at_h, _), point in zip(hits, crossings):
        where[g].append((at_g, point))
        where[h].append((at_h, point))
    bars = []
    for g, chain in enumerate(points):
        knots = [(0.0, chain[0])] + sorted(where[g], key=lambda x: x[0]) + [(k - 1.0, chain[-1])]
        for (_, p0), (_, p1) in zip(knots[:-1], knots[1:]):
            if np.linalg.norm(p1 - p0) > 1e-9:
                bars.append(np.stack([p0, p1]))
    return list(np.unique(crossings, axis=0)) if len(crossings) else [], bars


#: Crossings closer than this part of the size of the surface are one knot.
_MERGE = 0.005


def _merged(points: np.ndarray, near: float) -> np.ndarray:
    """The points, those closer than `near` to each other (in chains) moved to the middle of their group: three
    geodesics that almost meet make one knot, not three a hand apart."""
    count = len(points)
    if count < 2:
        return points
    group = np.arange(count)

    def root(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i
    for start in range(0, count, 1000):                       # (in pieces: bounded memory)
        d = np.linalg.norm(points[start:start + 1000, None] - points[None], axis=-1)
        for i, j in zip(*np.nonzero(d < near)):
            a, b = root(start + i), root(j)
            if a != b:
                group[max(a, b)] = min(a, b)
    roots = np.array([root(i) for i in range(count)])
    out = points.copy()
    for g in np.unique(roots):
        members = roots == g
        if members.sum() > 1:
            out[members] = points[members].mean(0)
    return out


def geodesic(surface, start, end, show: str = 'curves', detail=32, name: str | None = None) -> Data:
    """The node Geodesic (see the module)."""
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    detail = int(detail)
    if not 4 <= detail <= 200:
        raise ShapeError(tr('The detail goes from 4 to 200 (points of the net along the surface).'))
    _, f, c = _grid_of(surface)
    al = align(_point(start, "from"), _point(end, "to"), surface)
    a, b, s = (np.asarray(x, float) for x in al.values)
    lead = np.broadcast_shapes(a.shape[:-1], b.shape[:-1], s.shape[:-2])
    a = np.broadcast_to(a, lead + (3,)).reshape(-1, 3)
    b = np.broadcast_to(b, lead + (3,)).reshape(-1, 3)
    grids = np.broadcast_to(s.reshape(s.shape[:-2] + (f, c, 3)), lead + (f, c, 3)).reshape(-1, f, c, 3)
    groups: dict = {}                                        # the pairs on the same surface, solved together
    for k in range(len(a)):
        groups.setdefault(grids[k].tobytes(), []).append(k)
    count = _ROUNDS[-1]
    uvs, curves = np.zeros((len(a), count, 2)), np.zeros((len(a), count, 3))
    crossings, bars = [], []
    for group in groups.values():
        group = np.array(group)
        r = grids[group[0]]
        uv, p, closed = _paths(r, a[group], b[group], detail)
        uvs[group], curves[group] = uv, p
        if show in ('crossings', 'bars'):
            more, pieces = _knots(uv, p, r, closed)
            crossings += more
            bars += pieces
    if show == 'crossings':
        values = np.array(crossings).reshape(-1, 3)
        if not len(values):
            raise ShapeError(tr('The geodesics do not cross each other.'))
        return Data(values, ("crossing",), name, kind=POINT)
    if show == 'bars':
        return Data(np.array(bars).reshape(-1, 2, 3), ("bar",), name, kind=CURVE)
    if show == 'lengths':
        lengths = np.linalg.norm(np.diff(curves, axis=1), axis=-1).sum(-1)
        return Data(lengths.reshape(lead), al.levels, name, al.variables, al.starts, None, al.holes)
    return Data(curves.reshape(lead + (count, 3)), al.levels, name, al.variables, al.starts, CURVE, al.holes)
