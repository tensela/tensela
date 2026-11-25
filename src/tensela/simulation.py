"""Equilibrium: the shape a flexible thing takes under its loads (a particle-spring system).

A cable is replaced by particles (points with a share of the weight) joined by springs (Hooke's law: each one pulls
or pushes in proportion to how much it is stretched from its rest length). Some particles are supports and do not
move. The particles move until every force balances: the shape found that way carries its loads only along the
springs, in tension or compression, as the hanging models of Gaudí and the tensile structures of Frei Otto.

The node always gives the shape at rest: nothing to start, stop or reset. Inside it is a dynamic relaxation with
kinetic damping (the usual method for tensile structures): each particle gets a fictitious mass that keeps the steps
stable, they move with the out-of-balance forces, and every time their kinetic energy peaks they stop and start again
from there. Each kind of force (springs, loads, supports) is a separate piece, so others can be added later.

    equilibrium(line((0, 0, 0), (10, 0, 0)))       -> a cable of 10 m in 10 spans, hanging from its ends
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np

from .data import Data, ShapeError, integer
from .geometry import CLOSED_CURVE, CURVE, POINT, VECTOR, _in_lengths, _lengths, gravity_direction
from .language import tr

#: Which particles hold the shape: the ends of each curve or the corners of each mesh, the whole border of each mesh
#: (of a curve, its ends), only the start of each curve (a hanging weight), or none (then the «more supports» points
#: must hold it).
SUPPORTS = ('ends or corners', 'border', 'start', 'none')
#: The diagonals of each quadrilateral of a mesh, as springs too: no diagonals (a cable net: the squares turn into
#: diamonds), one per square (from its first corner to the third), or both (a sheet that keeps its shape).
DIAGONALS = ('no diagonals', 'one per square', 'both')
#: A border turns at a corner by at least so many degrees.
CORNER_DEGREES = 30.0
#: What the node gives: the shape at rest, its spans as lines, how much each span stretched (%), or the force in
#: each one (N: tension positive, compression negative).
SHOW = ('shape', 'spans', 'elongation', 'forces')

#: At most so many particles (each step goes over all of them).
MAXIMUM_PARTICLES = 8000
#: At most so many steps; the usual cases settle in a few hundred or a few thousand.
MAXIMUM_STEPS = 200000
#: At most so many positions are kept of the way to the rest of each group (to see it move).
FRAMES = 80

_CACHE: OrderedDict = OrderedDict()
_CACHE_SIZE = 8


def _items(data: Data, kind_wanted) -> list[tuple[tuple, np.ndarray]]:
    """(index, element) of each element of a data that exists (the holes of variable levels left out)."""
    v = np.asarray(data.values, dtype=float)
    shape = v.shape[:-1] if kind_wanted is POINT else v.shape[:-2]
    mask = np.broadcast_to(data.mask if data.levels else np.ones((), dtype=bool), shape)
    return [(index, v[index]) for index in np.ndindex(shape) if mask[index]]


def _points(data, role: str) -> np.ndarray:
    """The points of an input as (n, 3); none if it is empty."""
    if data is None:
        return np.zeros((0, 3))
    if not isinstance(data, Data) or data.kind not in (POINT, VECTOR):
        raise ShapeError(tr('“{role}” should be points: connect a node that gives them.').format(role=tr(role)))
    found = [p for _, p in _items(data, POINT)]
    return np.array(found, dtype=float).reshape(-1, 3)


def _clean(p: np.ndarray, closed: bool) -> np.ndarray:
    """A curve without the repeated points in a row (the padding of variable levels repeats the last one)."""
    keep = np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12]
    p = p[keep]
    if closed and len(p) > 2 and np.linalg.norm(p[0] - p[-1]) <= 1e-12:
        p = p[:-1]
    return p


def _curve_element(p: np.ndarray, closed: bool, spans: int) -> dict:
    """The particles and springs of one curve: divided into `spans` equal spans (0: its own vertices)."""
    p = _clean(p, closed)
    if len(p) < 2:
        return None
    if spans:
        one = Data(p, (), None, kind=CLOSED_CURVE if closed else CURVE)
        c, accumulated = _lengths(one)
        p = _in_lengths(c, accumulated, accumulated[-1] * np.linspace(0, 1, spans + 1))
        if closed:
            p = p[:-1]
    i = np.arange(len(p))
    pairs = np.stack([i[:-1], i[1:]], axis=1)
    if closed:
        pairs = np.vstack([pairs, [[i[-1], 0]]])
    ends = [] if closed else [0, len(p) - 1]
    return {"p": p, "pairs": pairs, "weft": np.zeros(len(pairs), dtype=bool), "corners": ends, "border": ends,
            "start": ends[:1], "faces": None}


def _mesh_element(p: np.ndarray, faces: list, diagonals: str) -> dict:
    """The particles and springs of one mesh: its edges (in a quadrilateral, the first and third go across, warp; the
    second and fourth up, weft), its diagonals if asked, its border and the corners of its border."""
    pairs, weft = [], []
    for face in faces:
        k = len(face)
        for j in range(k):
            pairs.append((face[j], face[(j + 1) % k]))
            weft.append(k == 4 and j % 2 == 1)
    pairs, weft = np.array(pairs, dtype=np.int64).reshape(-1, 2), np.array(weft, dtype=bool)
    # Each edge once (the first time it appears); an edge in only one face is on the border.
    key = np.sort(pairs, axis=1)
    _, first, inverse, count = np.unique(key, axis=0, return_index=True, return_inverse=True, return_counts=True)
    border_edges = key[first][count == 1]
    order = np.sort(first)
    pairs, weft = pairs[order], weft[order]
    if diagonals != 'no diagonals':
        quads = [f for f in faces if len(f) == 4]
        extra = [(f[0], f[2]) for f in quads] + ([(f[1], f[3]) for f in quads] if diagonals == 'both' else [])
        if extra:
            pairs = np.vstack([pairs, np.array(extra, dtype=np.int64)])
            weft = np.r_[weft, np.zeros(len(extra), dtype=bool)]
    border = sorted(set(border_edges.ravel().tolist()))
    corners = []
    neighbours = {}
    for a, b in border_edges:
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    for v, around in neighbours.items():
        if len(around) != 2:
            corners.append(v)                       # where borders meet or end
            continue
        u, w = p[around[0]] - p[v], p[around[1]] - p[v]
        lu, lw = np.linalg.norm(u), np.linalg.norm(w)
        if lu < 1e-15 or lw < 1e-15:
            continue
        turn = 180.0 - np.degrees(np.arccos(np.clip(u @ w / (lu * lw), -1.0, 1.0)))
        if turn >= CORNER_DEGREES:
            corners.append(v)
    return {"p": p, "pairs": pairs, "weft": weft, "corners": sorted(corners), "border": border, "start": None,
            "faces": faces}


def network(shape: Data, spans, diagonals: str = 'no diagonals', most: int | None = MAXIMUM_PARTICLES) -> dict:
    """The particles and springs of some curves (each one divided into `spans` equal spans, 0: the vertices it
    already has) or meshes (their edges, and their diagonals if asked), their points welded where they touch. At most
    `most` particles once welded (None: the caller sets its own limit)."""
    from .geometry import real_faces
    kind = getattr(shape, "kind", None)
    if not isinstance(shape, Data) or kind is None or not (kind.curve or kind.faces is not None):
        raise ShapeError(tr('“{name}” should be curves, lines or a mesh (what hangs).').format(
            name=shape._name() if isinstance(shape, Data) else tr('shape')))
    spans = integer(spans)
    if spans < 0:
        raise ShapeError(tr('The spans cannot be negative.'))
    if diagonals not in DIAGONALS:
        raise ShapeError(tr('The diagonals must be one of: {options}.').format(
            options=", ".join(tr(o) for o in DIAGONALS)))
    elements = []
    for index, p in _items(shape, CURVE):
        if kind.curve:
            element = _curve_element(p, kind.closed, spans)
        else:
            element = _mesh_element(p, real_faces(kind, p), diagonals)
        if element is not None:
            element["index"] = index
            elements.append(element)
    if not elements:
        raise ShapeError(tr('“{name}” has nothing with length to hang.').format(name=shape._name()))
    counts = {len(e["p"]) for e in elements}
    if len(counts) > 1:
        raise ShapeError(tr('The curves have different numbers of points ({counts}): give the spans, so each one is '
                            'divided the same.').format(counts=", ".join(str(c) for c in sorted(counts))))
    allp = np.vstack([e["p"] for e in elements])
    if len(allp) > 40 * MAXIMUM_PARTICLES:          # before welding (the 8 corners of each cube), only for memory
        raise ShapeError(tr('Too many particles ({n}; at most {maximum}): use fewer spans.').format(
            n=len(allp), maximum=40 * MAXIMUM_PARTICLES))
    size = float(np.ptp(allp, axis=0).max()) or 1.0
    keys = np.round(allp / (size * 1e-7)).astype(np.int64)
    _, first, which = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    which = which.ravel()
    if most is not None and len(first) > most:
        raise ShapeError(tr('Too many particles ({n}; at most {maximum}): use fewer spans.').format(
            n=len(first), maximum=most))
    k = 0
    for e in elements:
        e["ids"] = which[k:k + len(e["p"])]
        k += len(e["p"])
    springs = np.vstack([e["ids"][e["pairs"]] for e in elements])
    weft = np.concatenate([e["weft"] for e in elements])
    keep = springs[:, 0] != springs[:, 1]
    springs, weft = springs[keep], weft[keep]
    unique = np.sort(np.unique(np.sort(springs, axis=1), axis=0, return_index=True)[1])
    return {"particles": allp[first], "springs": springs[unique], "weft": weft[unique], "elements": elements,
            "mesh": not kind.curve}


class Bending:
    """The resistance to bending, as an energy of curvature: at each inner particle, the step from it to the mean of
    its neighbours (a discrete measure of curvature, its Laplacian) wants to stay as it started. Weighted by the area
    (or the length) around the particle over its spacing to the fourth, its sum is the curvature squared over the
    surface (or the curve): it does not depend on how fine the mesh is. The energy is quadratic, so its stiffness is
    the same at every step."""

    def __init__(self, rows: np.ndarray, cols: np.ndarray, coeffs: np.ndarray, weights: np.ndarray,
                 particles: np.ndarray):
        self.rows, self.cols, self.coeffs, self.weights = rows, cols, coeffs, weights
        self.count = int(rows.max()) + 1 if len(rows) else 0
        self.target = self.apply(particles)

    def apply(self, x: np.ndarray) -> np.ndarray:
        """The Laplacian of each row (count, 3)."""
        out = np.zeros((self.count, 3))
        np.add.at(out, self.rows, self.coeffs[:, None] * x[self.cols])
        return out

    def scaled(self, factor: float) -> "Bending":
        other = object.__new__(Bending)
        other.__dict__.update(self.__dict__)
        other.weights = self.weights * factor
        return other

    def energy(self, x: np.ndarray) -> float:
        return 0.5 * float((self.weights[:, None] * (self.apply(x) - self.target) ** 2).sum())

    def force(self, x: np.ndarray) -> np.ndarray:
        """Minus the gradient of the energy, on each particle (n, 3)."""
        excess = self.weights[:, None] * (self.apply(x) - self.target)
        out = np.zeros_like(x)
        np.add.at(out, self.cols, -self.coeffs[:, None] * excess[self.rows])
        return out

    def stiffness(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Its (constant) stiffness as entries (i, j, value): value times the identity, between particles i and j."""
        order = np.argsort(self.rows, kind="stable")
        rows, cols, coeffs = self.rows[order], self.cols[order], self.coeffs[order]
        starts = np.r_[0, np.flatnonzero(np.diff(rows)) + 1, len(rows)]
        ii, jj, vv = [], [], []
        for s0, s1 in zip(starts[:-1], starts[1:]):
            c, k = cols[s0:s1], coeffs[s0:s1]
            w = self.weights[rows[s0]]
            ii.append(np.repeat(c, len(c)))
            jj.append(np.tile(c, len(c)))
            vv.append(w * np.outer(k, k).ravel())
        if not ii:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64), np.zeros(0)
        return np.concatenate(ii), np.concatenate(jj), np.concatenate(vv)

    def part(self, members: np.ndarray, n: int) -> "Bending":
        """The rows of some particles only (a group), renumbered."""
        local = -np.ones(n, dtype=np.int64)
        local[members] = np.arange(len(members))
        mine = local[self.cols] >= 0
        rows_kept = np.unique(self.rows[mine])
        row_map = -np.ones(max(self.count, 1), dtype=np.int64)
        row_map[rows_kept] = np.arange(len(rows_kept))
        keep = (row_map[self.rows] >= 0) & mine
        other = object.__new__(Bending)
        other.rows, other.cols, other.coeffs = row_map[self.rows[keep]], local[self.cols[keep]], self.coeffs[keep]
        other.weights, other.target = self.weights[rows_kept], self.target[rows_kept]
        other.count = len(rows_kept)
        return other


def _bending(elements: list, curves: bool, particles: np.ndarray) -> Bending | None:
    """The curvature operator of some curves or meshes (welded): at each inner particle, the mean of its neighbours
    minus itself. On a mesh, its neighbours along the edges of its faces (a particle on the border is left free)."""
    neighbours, area = {}, {}
    for e in elements:
        ids = e["ids"]
        if curves:
            for j in range(1, len(ids) - 1):
                v = int(ids[j])
                neighbours.setdefault(v, set()).update((int(ids[j - 1]), int(ids[j + 1])))
                area[v] = area.get(v, 0.0) + 0.5 * (np.linalg.norm(particles[ids[j + 1]] - particles[v])
                                                    + np.linalg.norm(particles[ids[j - 1]] - particles[v]))
            continue
        border = set(int(ids[v]) for v in e["border"])
        for face in e["faces"]:
            f = [int(ids[v]) for v in face]
            q = particles[f]
            share = 0.5 * np.linalg.norm(np.cross(q[1:-1] - q[0], q[2:] - q[0]).sum(axis=0)) / len(f) if len(f) > 2 \
                else 0.0
            for j, v in enumerate(f):
                if v in border:
                    continue
                neighbours.setdefault(v, set()).update(w for w in (f[j - 1], f[(j + 1) % len(f)]) if w != v)
                area[v] = area.get(v, 0.0) + share
    rows, cols, coeffs, weights = [], [], [], []
    for r, (v, around) in enumerate(sorted((v, sorted(a)) for v, a in neighbours.items() if len(a) >= 2)):
        h = float(np.mean(np.linalg.norm(particles[around] - particles[v], axis=1)))
        if h <= 1e-12:
            continue
        r = len(weights)
        rows += [r] * (len(around) + 1)
        cols += [v] + list(around)
        coeffs += [-1.0] + [1.0 / len(around)] * len(around)
        weights.append(area[v] / h ** 4)
    if not weights:
        return None
    return Bending(np.array(rows), np.array(cols), np.array(coeffs), np.array(weights), particles)


def _nearest(particles: np.ndarray, points: np.ndarray) -> np.ndarray:
    """The particle nearest each point (in the starting shape)."""
    if not len(points):
        return np.zeros(0, dtype=np.int64)
    d = ((points[:, None, :] - particles[None, :, :]) ** 2).sum(-1)
    return np.argmin(d, axis=1)


def _loads_at(points: np.ndarray, load, down: np.ndarray) -> np.ndarray:
    """The force at each load point (n, 3): a number is newtons towards gravity; a vector, as it is."""
    n = len(points)
    if load is None:
        load = 0.0
    if isinstance(load, Data) and load.kind in (POINT, VECTOR):
        v = np.array([p for _, p in _items(load, POINT)], dtype=float).reshape(-1, 3)
    else:
        values = np.asarray(load.values if isinstance(load, Data) else load, dtype=float).reshape(-1)
        v = values[:, None] * down[None, :]
    if len(v) == 1 or len(v) == n:
        return np.broadcast_to(v, (n, 3)).astype(float)
    raise ShapeError(tr('There are {n} load points and {m} loads: give one load for all, or one per point.').format(
        n=n, m=len(v)))


def solve(x0: np.ndarray, springs: np.ndarray, stiffness: np.ndarray, rest: np.ndarray, forces: np.ndarray,
          fixed: np.ndarray, tolerance: float, steps: int = MAXIMUM_STEPS, path: list | None = None,
          floor=None, bending=None) -> tuple[np.ndarray, int, bool]:
    """Dynamic relaxation with kinetic damping: the positions where the springs balance the forces (fixed particles
    stay where they are). Returns the positions, the steps taken and whether it settled. `path`, if given, gets the
    positions every few steps (to see it move)."""
    x = x0.copy()
    n = len(x)
    a, b = springs[:, 0], springs[:, 1]
    free = ~fixed
    v = np.zeros_like(x)
    energy_before = 0.0
    mass = None
    for step in range(steps):
        d = x[b] - x[a]
        length = np.linalg.norm(d, axis=1)
        length = np.maximum(length, 1e-15)
        tension = stiffness * (length - rest)
        pull = d * (tension / length)[:, None]
        residual = forces.copy()
        for axis in range(3):
            residual[:, axis] += np.bincount(a, pull[:, axis], n) - np.bincount(b, pull[:, axis], n)
        if floor is not None:
            residual += _floor_push(x, floor)[0]
        if bending is not None:
            residual += bending.force(x)
        residual[fixed] = 0.0
        if step % 25 == 0:
            # The fictitious mass that keeps a step of 1 stable: the stiffness that meets at each particle (axial and,
            # if pulled, geometric), with some room.
            local = stiffness + np.maximum(tension, 0.0) / length
            ground = floor[2] if floor is not None else 0.0
            if bending is not None:
                bi, _, bv = bending.stiffness()
                ground = ground + np.bincount(bi, np.abs(bv), n)
            mass = 1.2 * (np.bincount(a, local, n) + np.bincount(b, local, n) + ground) + 1e-30
            if path is not None:
                path.append(x.copy())
            if np.abs(residual[free]).max(initial=0.0) <= max(tolerance, 1e-9 * float(np.abs(tension).max())):
                return x, step, True
        v += residual / mass[:, None]
        energy = float((mass[:, None] * v * v).sum())
        if energy < energy_before:
            # Past a peak of kinetic energy: stop every particle there and start again.
            v[:] = 0.0
            energy = 0.0
        energy_before = energy
        x += v
    return x, steps, False


#: Up to so many free coordinates (three per free particle) each step of Newton's method is solved directly; beyond,
#: in blocks along the band of the system (it never builds the whole matrix).
MAXIMUM_NEWTON = 1200
#: The damping of Newton's steps: where it starts (times the mean stiffness), how much it grows when a step would
#: climb, and how much it shrinks after a good one.
DAMPING_START, DAMPING_UP, DAMPING_DOWN = 1e-3, 4.0, 3.0


def _energy(x, a, b, stiffness, rest, forces, floor=None, bending=None) -> float:
    length = np.linalg.norm(x[b] - x[a], axis=1)
    energy = float(0.5 * (stiffness * (length - rest) ** 2).sum() - (forces * x).sum())
    if bending is not None:
        energy += bending.energy(x)
    if floor is not None:
        up, height, hardness = floor
        below = np.maximum(height - x @ up, 0.0)
        energy += 0.5 * hardness * float((below ** 2).sum())
    return energy


def _floor_push(x, floor) -> tuple[np.ndarray, np.ndarray]:
    """The push of the floor on each particle below it (n, 3), and which ones are below."""
    up, height, hardness = floor
    below = np.maximum(height - x @ up, 0.0)
    return hardness * below[:, None] * up[None, :], below > 0


def _ordering(n: int, springs: np.ndarray) -> np.ndarray:
    """A numbering of the particles in which those joined by a spring are numbered close to one another (reverse
    Cuthill-McKee): the springs then stay near the diagonal of the system, in a narrow band."""
    neighbours = [set() for _ in range(n)]
    for i, j in springs:
        if i != j:
            neighbours[i].add(j)
            neighbours[j].add(i)
    degree = np.array([len(x) for x in neighbours])
    seen = np.zeros(n, dtype=bool)
    order = []
    for first in np.argsort(degree, kind="stable"):
        if seen[first]:
            continue
        seen[first] = True
        queue = [int(first)]
        head = 0
        while head < len(queue):
            v = queue[head]
            head += 1
            for w in sorted((w for w in neighbours[v] if not seen[w]), key=lambda w: degree[w]):
                seen[w] = True
                queue.append(w)
        order.extend(queue)
    number = np.empty(n, dtype=np.int64)
    number[np.array(order[::-1], dtype=np.int64)] = np.arange(n)
    return number


class _Banded:
    """The system of a big network, numbered in a narrow band and cut into blocks as wide as the band: the matrix is
    then block tridiagonal, and solving it takes a few dense steps per block instead of one huge one."""

    def __init__(self, springs: np.ndarray, where: np.ndarray, size: int, extra=None):
        a, b = springs[:, 0], springs[:, 1]
        joined = springs if extra is None else np.vstack([springs, np.stack(extra[:2], axis=1)])
        free_pairs = joined[(where[joined[:, 0]] >= 0) & (where[joined[:, 1]] >= 0)]
        self.number = _ordering(size // 3, where[free_pairs])
        band = int(np.abs(self.number[where[free_pairs[:, 0]]] - self.number[where[free_pairs[:, 1]]]).max(initial=0))
        w = self.width = 3 * band + 3
        self.size = size
        nb = self.blocks = -(-size // w)
        # Where each entry of each span block goes (the same every step: only the values change).
        self.oks, targets, keeps = [], [], []
        for i, j in ((a, a), (b, b), (a, b), (b, a)):
            ok = (where[i] >= 0) & (where[j] >= 0)
            self.oks.append(ok)
            rows = np.repeat(self._dof(where[i][ok])[:, :, None], 3, axis=2).ravel()
            cols = np.repeat(self._dof(where[j][ok])[:, None, :], 3, axis=1).ravel()
            br, bc = rows // w, cols // w
            same, lower = br == bc, br == bc + 1
            flat = np.where(same, (br * w + rows % w) * w + cols % w,
                            nb * w * w + (bc * w + rows % w) * w + cols % w)
            keeps.append(same | lower)
            targets.append(flat[same | lower])
        # The extra entries (the stiffness of bending): value times the identity between particles i and j.
        self.extra_keep, self.extra_values = None, None
        if extra is not None:
            ei, ej, ev = extra
            ok = (where[ei] >= 0) & (where[ej] >= 0)
            rows = (self._dof(where[ei][ok])).ravel()
            cols = (self._dof(where[ej][ok])).ravel()
            br, bc = rows // w, cols // w
            same, lower = br == bc, br == bc + 1
            flat = np.where(same, (br * w + rows % w) * w + cols % w,
                            nb * w * w + (bc * w + rows % w) * w + cols % w)
            keeps.append(same | lower)
            targets.append(flat[same | lower])
            self.extra_values = np.repeat(ev[ok], 3)
        self.keep = np.concatenate(keeps)
        self.targets = np.concatenate(targets)
        self.order = self._dof(np.arange(size // 3)).ravel()
        self.total = nb * w * w + max(nb - 1, 0) * w * w

    def _dof(self, particles_free: np.ndarray) -> np.ndarray:
        return 3 * self.number[particles_free][:, None] + np.arange(3)[None, :]

    def solve(self, block: np.ndarray, damping: float, r: np.ndarray) -> np.ndarray:
        """Solves (K + damping) x = r, with K the sum of the 3 × 3 `block` of each span between its particles."""
        w, nb = self.width, self.blocks
        values = [(sign * block[ok]).ravel() for ok, sign in zip(self.oks, (1.0, 1.0, -1.0, -1.0))]
        if self.extra_values is not None:
            values.append(self.extra_values)
        values = np.concatenate(values)
        summed = np.bincount(self.targets, values[self.keep], self.total)
        diagonal = summed[:nb * w * w].reshape(nb, w, w)
        below = summed[nb * w * w:].reshape(-1, w, w)
        index = np.arange(w)
        diagonal[:, index, index] += damping
        full = nb * w
        if full > self.size:                          # the padding of the last block: harmless ones on the diagonal
            pad = np.arange(self.size, full)
            diagonal[pad // w, pad % w, pad % w] = 1.0
        rhs = np.zeros(full)
        rhs[self.order] = r
        rhs = rhs.reshape(nb, w)
        inverses, links = [], []
        previous = None
        for k in range(nb):
            d = diagonal[k] if previous is None else diagonal[k] - previous @ previous.T
            inverse = np.linalg.inv(np.linalg.cholesky(d))   # raises if it is not positive: more damping
            inverses.append(inverse)
            if k < nb - 1:
                previous = below[k] @ inverse.T
                links.append(previous)
        y = np.zeros_like(rhs)
        for k in range(nb):
            y[k] = inverses[k] @ (rhs[k] - links[k - 1] @ y[k - 1] if k else rhs[k])
        x = np.zeros_like(rhs)
        for k in range(nb - 1, -1, -1):
            x[k] = inverses[k].T @ (y[k] - links[k].T @ x[k + 1] if k < nb - 1 else y[k])
        return x.ravel()[self.order]


def _first_guess(x0, a, b, free, stiffness, rest, forces, system, floor=None, bending=None) -> np.ndarray:
    """A start near the answer: the net in which each span pulls with c times its stiffness times its length (the
    force density method, linear: two solutions give it for every c), with the c of least energy. A membrane that
    starts flat and hangs from its corners then needs a few steps of Newton instead of dozens."""
    d = x0[b] - x0[a]
    pull = d * stiffness[:, None]
    toward = np.zeros_like(x0)
    np.add.at(toward, a, pull)
    np.add.at(toward, b, -pull)
    block = stiffness[:, None, None] * np.eye(3)[None]
    tiny = 1e-12 * float(stiffness.max())
    try:
        sag = system(block, tiny, forces[free].ravel()).reshape(-1, 3)
        shrink = system(block, tiny, toward[free].ravel()).reshape(-1, 3)
    except np.linalg.LinAlgError:
        return x0
    best, energy_best = x0, _energy(x0, a, b, stiffness, rest, forces, floor, bending)
    for pulled in (shrink, 0.0 * shrink):           # with the pull of the spans, and with only the loads

        def at(log_c):
            x = x0.copy()
            x[free] += sag / 10.0 ** log_c + pulled
            return x, _energy(x, a, b, stiffness, rest, forces, floor, bending)

        low, high = -8.0, 2.0                  # golden section over log10(c)
        ratio = (5 ** 0.5 - 1) / 2
        p, q = high - ratio * (high - low), low + ratio * (high - low)
        (xp, ep), (xq, eq) = at(p), at(q)
        for _ in range(30):
            if ep < eq:
                high, q, xq, eq = q, p, xp, ep
                p = high - ratio * (high - low)
                xp, ep = at(p)
            else:
                low, p, xp, ep = p, q, xq, eq
                q = low + ratio * (high - low)
                xq, eq = at(q)
        x, e = (xp, ep) if ep < eq else (xq, eq)
        if np.isfinite(e) and e < energy_best:
            best, energy_best = x, e
    return best


def newton(x0: np.ndarray, springs: np.ndarray, stiffness: np.ndarray, rest: np.ndarray, forces: np.ndarray,
           fixed: np.ndarray, tolerance: float, steps: int | None = None, path: list | None = None,
           floor=None, bending=None) -> tuple[np.ndarray, int, bool]:
    """Newton's method on the energy of the springs and the loads, damped (Levenberg-Marquardt) so it never climbs:
    a step that would raise the energy is tried again with more damping, shorter and more downhill. A small system is
    solved directly; a big one, in blocks along its band. Returns the positions, the steps and whether it settled.
    `path`, if given, gets the positions after each step (to see it move). `floor`: (up, height, hardness), a floor
    that pushes back the particles that go through it."""
    x = x0.copy()
    n = len(x)
    a, b = springs[:, 0], springs[:, 1]
    # The floor, as one more spring from each particle to a fixed ghost below it, stiff only up and down (and only
    # while the particle is under the floor): the system keeps its shape, only the values change.
    where = -np.ones(n + 1, dtype=np.int64)
    free = np.flatnonzero(~fixed)
    where[free] = np.arange(len(free))
    size = 3 * len(free)
    if size == 0:
        return x, 0, True
    a_all, b_all = a, b
    if floor is not None:
        a_all, b_all = np.r_[a, np.arange(n)], np.r_[b, np.full(n, n)]
    extra = None if bending is None else bending.stiffness()
    direct = size <= MAXIMUM_NEWTON
    banded = None if direct else _Banded(np.stack([a_all, b_all], axis=1), where, size, extra)
    anchored = bool(fixed.any())
    if steps is None:                    # a direct step is cheap: room for the slow cases (a cable turning over)
        steps = 4000 if direct else 400
    eye = np.eye(3)

    def system(block, damping, r, ground=None):
        """Solves (K + damping) x = r, K the sum of the 3 × 3 block of each span (and of the floor, `ground`)."""
        if floor is not None:
            block = np.concatenate([block, ground if ground is not None else np.zeros((n, 3, 3))])
        if not direct:
            return banded.solve(block, damping, r)
        matrix = np.zeros((size, size))
        for i, j, sign in ((a_all, a_all, 1.0), (b_all, b_all, 1.0), (a_all, b_all, -1.0), (b_all, a_all, -1.0)):
            ok = (where[i] >= 0) & (where[j] >= 0)
            rows = (3 * where[i][ok])[:, None, None] + np.arange(3)[None, :, None]
            cols = (3 * where[j][ok])[:, None, None] + np.arange(3)[None, None, :]
            np.add.at(matrix, (rows, cols), sign * block[ok])
        if extra is not None:
            ei, ej, ev = extra
            ok = (where[ei] >= 0) & (where[ej] >= 0)
            for axis in range(3):
                np.add.at(matrix, (3 * where[ei][ok] + axis, 3 * where[ej][ok] + axis), ev[ok])
        matrix[np.arange(size), np.arange(size)] += damping
        return np.linalg.solve(matrix, r)

    if path is not None:
        path.append(x.copy())
    if anchored:                         # (resting only on the floor, a linear guess has nothing to hang from)
        x = _first_guess(x, a, b, free, stiffness, rest, forces, system, floor, bending)
    if path is not None:
        path.append(x.copy())
    damping = DAMPING_START * float(stiffness.mean())
    # Resting only on the floor it could slide sideways freely: a little damping always keeps it in place.
    least = (1e-12 if anchored else 1e-6) * float(stiffness.max())
    energy = _energy(x, a, b, stiffness, rest, forces, floor, bending)
    up_up = None if floor is None else floor[2] * np.outer(floor[0], floor[0])
    for step in range(steps):
        d = x[b] - x[a]
        length = np.maximum(np.linalg.norm(d, axis=1), 1e-15)
        u = d / length[:, None]
        tension = stiffness * (length - rest)
        residual = forces.copy()
        pull = u * tension[:, None]
        np.add.at(residual, a, pull)
        np.add.at(residual, b, -pull)
        ground = None
        if floor is not None:
            push, below = _floor_push(x, floor)
            residual += push
            ground = np.where(below[:, None, None], up_up[None], 0.0)
        if bending is not None:
            residual += bending.force(x)
        r = residual[free].ravel()
        if np.abs(r).max() <= max(tolerance, 1e-9 * float(np.abs(tension).max(initial=0.0))):
            return x, step, True
        outer = u[:, :, None] * u[:, None, :]
        geometric = 1.0 - rest / length
        block = stiffness[:, None, None] * (geometric[:, None, None] * (eye - outer) + outer)
        while True:
            try:
                move = system(block, damping, r, ground)
            except np.linalg.LinAlgError:
                damping *= 10
                continue
            moved = x.copy()
            moved[free] += move.reshape(-1, 3)
            energy_moved = _energy(moved, a, b, stiffness, rest, forces, floor, bending)
            if energy_moved <= energy + 1e-13 * abs(energy) or damping > 1e12 * float(stiffness.max()):
                break
            damping *= DAMPING_UP
        x, energy = moved, energy_moved
        if path is not None:
            path.append(x.copy())
        damping = max(damping / DAMPING_DOWN, least)
    return x, steps, False


def _groups(n: int, springs: np.ndarray) -> np.ndarray:
    """The group of each particle: those joined by springs, directly or through others (cables that do not touch
    are separate groups, and each one settles on its own)."""
    parent = np.arange(n)

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in springs:
        ri, rj = root(i), root(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    return np.array([root(i) for i in range(n)])


def _settle(x0, springs, stiffness, rest, forces, fixed, tolerance, floor=None, bending=None
            ) -> tuple[np.ndarray, bool, list]:
    """Each group of particles to its rest, with Newton's method (and, if it did not get there, dynamic
    relaxation). Returns the positions, whether every group settled, and the way each group went: (its particles,
    its positions along the way, how far along each one is, from 0 to 1)."""
    x = x0.copy()
    group = _groups(len(x0), springs)
    span_group = group[springs[:, 0]]
    ways = []
    for g in np.unique(group):
        members = np.flatnonzero(group == g)
        mine = span_group == g
        if not mine.any():
            continue                                     # a particle alone: nothing pulls it
        local = -np.ones(len(x0), dtype=np.int64)
        local[members] = np.arange(len(members))
        pairs = local[springs[mine]]
        args = (pairs, stiffness[mine], rest[mine], forces[members], fixed[members], tolerance)
        if not fixed[members].any() and floor is None:
            if np.abs(forces[members]).max(initial=0.0) > 0:
                raise ShapeError(tr('A part of it hangs from nothing: every piece needs a support (or a floor).'))
            continue
        path = []
        mine_bending = None if bending is None else bending.part(members, len(x0))
        if mine_bending is not None and mine_bending.count == 0:
            mine_bending = None
        start = x0[members]
        if floor is not None and not fixed[members].any():
            # Resting only on the floor: first it falls whole until it touches it (a fall changes nothing of its
            # shape, and Newton would cover it in many short steps).
            path.append(start.copy())
            up, height, _ = floor
            start = start + (height - float((start @ up).min())) * up
        start, _, settled = newton(start, *args, path=path, floor=floor, bending=mine_bending)
        if not settled:
            start, _, settled = solve(start, *args, path=path, floor=floor, bending=mine_bending)
        if not settled:
            return x, False, []
        x[members] = start
        path.append(start.copy())
        ways.append((members,) + _way(path))
    return x, True, ways


def _way(path: list) -> tuple[np.ndarray, np.ndarray]:
    """The positions along the way (at most FRAMES of them) and how far along each one is, by how much the
    particles moved: so the way is seen at an even pace, though the steps were long at first and short at the end."""
    frames = np.array(path)
    moved = np.sqrt(((np.diff(frames, axis=0)) ** 2).sum(axis=2).mean(axis=1))
    along = np.r_[0.0, np.cumsum(moved)]
    total = along[-1]
    along = along / total if total > 0 else np.linspace(0.0, 1.0, len(frames))
    if len(frames) > FRAMES:
        keep = np.unique(np.searchsorted(along, np.linspace(0.0, 1.0, FRAMES)).clip(0, len(frames) - 1))
        frames, along = frames[keep], along[keep]
    return frames, along


def _at(x0: np.ndarray, ways: list, moment: float) -> np.ndarray:
    """The positions at a moment of the way: 0 the start, 1 at rest."""
    x = x0.copy()
    for members, frames, along in ways:
        if len(frames) < 2:
            x[members] = frames[-1]
            continue
        k = int(np.clip(np.searchsorted(along, moment, side="right") - 1, 0, len(frames) - 2))
        width = along[k + 1] - along[k]
        t = 0.0 if width <= 0 else (moment - along[k]) / width
        x[members] = frames[k] + (frames[k + 1] - frames[k]) * float(np.clip(t, 0.0, 1.0))
    return x


def _tie_pairs(ties, particles: np.ndarray) -> np.ndarray:
    """The particles each tie joins (k, 2): those nearest the two ends of each line (or curve) of `ties`."""
    from .geometry import CURVE
    if ties is None:
        return np.zeros((0, 2), dtype=np.int64)
    if not isinstance(ties, Data) or ties.kind is None or not ties.kind.curve:
        raise ShapeError(tr('The ties must be lines (or curves): their two ends are pulled together.'))
    ends = [(p[0], p[-1]) for _, p in _items(ties, CURVE)]
    if not ends:
        return np.zeros((0, 2), dtype=np.int64)
    a = _nearest(particles, np.array([e[0] for e in ends], float))
    b = _nearest(particles, np.array([e[1] for e in ends], float))
    keep = a != b                                             # both ends on the same particle: nothing to pull
    return np.stack([a[keep], b[keep]], 1)


def _share_by_area(particles: np.ndarray, elements: list) -> np.ndarray:
    """How much of a membrane each particle carries: the area of each face, a part to each of its corners."""
    share = np.zeros(len(particles))
    for e in elements:
        for face in e["faces"]:
            q = e["p"][list(face)]
            area = 0.5 * np.linalg.norm(np.cross(q[1:-1] - q[0], q[2:] - q[0]).sum(axis=0)) if len(q) > 2 else 0.0
            np.add.at(share, e["ids"][list(face)], area / len(face))
    return share


def _number(x, what: str = 'value') -> float:
    return float(np.asarray(x.values if isinstance(x, Data) else x, dtype=float).ravel()[0])


def equilibrium(shape: Data, spans=10, supports: str = 'ends or corners', more_supports=None, self_weight=100.0,
                loads=None, load=10.0, stiffness=10000.0, rest_length=1.0, gravity=(0.0, 0.0, -1.0),
                show: str = 'shape', name: str | None = None, diagonals: str = 'no diagonals', weft=1.0,
                moment=1.0, bending=0.0, floor=None, imperfection=0.0, hand_supports=None, ties=None,
                tie_strength=1.0) -> Data:
    """The shape at rest of some cables (curves or lines) or membranes (meshes) hanging from their supports, with
    their `self_weight` (N, shared out along the cables or over the membrane), more `load` at the `loads` points, a
    `stiffness` (N: the force that would stretch a span to twice its starting length; `weft` times that in the other
    direction of a mesh) and a rest length (`rest_length` times the starting one: 1 elastic, less pre-tensioned, 0 a
    soap film, more relaxed). `show`: the shape, its spans as lines, how much each stretched (%) or the force in each
    (N). `moment`: 1 at rest; less, on its way there from the start (0). `bending`: how much it resists bending,
    times the stiffness (0: it folds like a cloth). `floor`: the height of a floor it rests on (None: no floor).
    `imperfection`: how far (m) the particles are shaken at random before starting, to see whether the shape is
    stable (a stable one comes back; one that is not, buckles); the shape of reference is still the perfect one.
    `hand_supports`: the supports moved by hand in the 3D view, as rows [x0, y0, z0, x, y, z]: the particle that starts
    nearest (x0, y0, z0) is held at (x, y, z). The answer carries `.network` (the particles at the start and at rest,
    the springs, which are held and which by hand), for the editor of the view."""
    supports = 'ends or corners' if supports == 'ends' else supports       # the name of before
    if supports not in SUPPORTS:
        raise ShapeError(tr('The supports must be one of: {options}.').format(
            options=", ".join(tr(o) for o in SUPPORTS)))
    if show not in SHOW:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    net = network(shape, spans, diagonals)
    particles, springs, elements = net["particles"], net["springs"], net["elements"]
    n = len(particles)
    down = gravity_direction(gravity)
    ea = _number(stiffness)
    if not ea > 0:
        raise ShapeError(tr('The stiffness must be greater than 0.'))
    across = _number(weft)
    if not across > 0:
        raise ShapeError(tr('The weft must be greater than 0 (it multiplies the stiffness).'))
    factor = _number(rest_length)
    if factor < 0:
        raise ShapeError(tr('The rest length cannot be negative.'))
    weight = _number(self_weight)
    stiff_bending = _number(bending)
    if stiff_bending < 0:
        raise ShapeError(tr('The bending cannot be negative.'))
    shake = _number(imperfection)
    if shake < 0:
        raise ShapeError(tr('The imperfection cannot be negative.'))
    when = _number(moment)
    if not 0.0 <= when <= 1.0:
        raise ShapeError(tr('The moment goes from 0 (the start) to 1 (at rest).'))

    # Where it is held: the chosen ends, corners or border, and the particles nearest the other supports (moved to
    # those points).
    position = particles.copy()
    fixed = np.zeros(n, dtype=bool)
    if supports != 'none':
        if supports == 'start' and net["mesh"]:
            raise ShapeError(tr('A mesh has no start: hold it by its corners, its border or some points.'))
        which = {'ends or corners': "corners", 'border': "border", 'start': "start"}[supports]
        for e in elements:
            fixed[e["ids"][e[which]]] = True
        if not fixed.any() and supports != 'start':
            raise ShapeError(tr('“{name}” has no {what}: hold it by some points («more supports»).').format(
                name=shape._name(), what=tr('corners' if which == "corners" else 'border')))
    extra = _points(more_supports, 'more supports')
    held = _nearest(particles, extra)
    fixed[held] = True
    position[held] = extra
    by_hand = np.zeros(0, dtype=np.int64)
    if hand_supports:
        rows = np.array([[float(c) for c in r[:6]] for r in hand_supports if len(r) >= 6], dtype=float).reshape(-1, 6)
        by_hand = _nearest(particles, rows[:, :3])
        fixed[by_hand] = True
        position[by_hand] = rows[:, 3:]
    height = None if floor is None or (isinstance(floor, str) and not floor.strip()) else _number(floor)
    if not fixed.any() and height is None:
        raise ShapeError(tr('Nothing holds it: choose some supports, connect points to «more supports», or give it a '
                            'floor.'))

    if not len(springs):                                   # a sphere of radius 0, a box of size 0: a single point
        raise ShapeError(tr('«{name}» has no spans to hang: it is a single point (a size in 0?).').format(
            name=shape._name()))
    # The loads: the self weight shared out by the length (cables) or the area (membranes) each particle carries,
    # and the loads at their points.
    start = np.linalg.norm(particles[springs[:, 1]] - particles[springs[:, 0]], axis=1)
    start = np.maximum(start, 1e-12)
    forces = np.zeros((n, 3))
    if weight:
        share = _share_by_area(particles, elements) if net["mesh"] else None
        if share is None or not share.sum() > 0:
            share = np.bincount(springs[:, 0], start, n) + np.bincount(springs[:, 1], start, n)
        forces += (weight * share / share.sum())[:, None] * down
    where = _points(loads, 'loads')
    if len(where):
        np.add.at(forces, _nearest(particles, where), _loads_at(where, load, down))

    # Each span: the force over the stretch, from its starting length (the weft, `across` times that).
    k = ea / start * np.where(net["weft"], across, 1.0)
    rest = factor * start
    # The resistance to bending: it keeps the curvature it starts with, whatever the rest length.
    all_springs, all_k, all_rest = springs, k, rest
    # The ties: the two ends of each line pulled together (springs of no length, as stitches: a smocking), as stiff
    # as a typical span, times `tie_strength`.
    pairs = _tie_pairs(ties, particles)
    if len(pairs):
        strength = _number(tie_strength)
        if not strength > 0:
            raise ShapeError(tr('The strength of the ties must be greater than 0.'))
        all_springs = np.concatenate([springs, pairs])
        all_k = np.concatenate([k, np.full(len(pairs), strength * float(np.median(k)))])
        all_rest = np.concatenate([rest, np.zeros(len(pairs))])
    curving = None
    if stiff_bending > 0:
        curving = _bending(elements, not net["mesh"], particles)
        if curving is not None:
            curving = curving.scaled(stiff_bending * ea)
    ground = None
    if height is not None:
        ground = (-down, float(height), 100.0 * float(all_k.max()))      # up, how high, how hard it pushes back
    scale = max(float(np.abs(forces).max(initial=0.0)), 1e-9 * ea)
    if shake > 0:
        # Always the same shake (the same seed), so the same imperfect shape gives the same answer.
        noise = np.random.default_rng(7).normal(0.0, shake, position.shape)
        position = position + np.where(fixed[:, None], 0.0, noise)
    key = (position.tobytes(), all_springs.tobytes(), all_k.tobytes(), all_rest.tobytes(), forces.tobytes(),
           fixed.tobytes(), repr(ground), stiff_bending)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        x, ways = _CACHE[key]
    else:
        # Without loads, a shape can come to rest with no force at all (a cable exactly as long as the distance
        # between its supports): then the tolerance cannot go below the rounding of the numbers.
        rounding = 1e-12 * float(all_k.max(initial=0.0)) * max(1.0, float(np.abs(position).max(initial=0.0)))
        x, settled, ways = _settle(position, all_springs, all_k, all_rest, forces, fixed, max(1e-7 * scale, rounding),
                                   ground, curving)
        if not settled:
            raise ShapeError(tr('It did not settle: the stiffness is too high or too low for its loads. Try another '
                                'stiffness, or fewer spans.'))
        _CACHE[key] = (x, ways)
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)

    network_ = {"start": particles, "rest": x, "springs": springs, "fixed": fixed, "by_hand": by_hand}
    if when < 1.0:
        x = _at(position, ways, when)
    result = _shown(shape, net, elements, x, particles, ea, across, factor, show, name)
    result.network = network_
    return result


def _shown(shape, net, elements, x, particles, ea, across, factor, show, name) -> Data:
    """What the node gives, from the positions `x`: the shape, its spans, their elongation or their forces."""
    lead = shape.values.shape[:-2]
    if show == 'shape':
        out = np.zeros(lead + (len(elements[0]["ids"]), 3))
        for e in elements:
            out[e["index"]] = x[e["ids"]]
        return shape.derived(out, name, shape.kind)
    sizes = {len(e["pairs"]) for e in elements}
    if len(sizes) > 1:
        raise ShapeError(tr('Its pieces have different numbers of spans: show their shape, or one piece at a time.'))
    m = sizes.pop()
    if show == 'spans':
        out = np.zeros(lead + (m, 2, 3))
        for e in elements:
            out[e["index"]] = x[e["ids"][e["pairs"]]]
        return shape.derived(out, name, CURVE, ("span",))
    out = np.zeros(lead + (m,))
    for e in elements:
        pairs = e["ids"][e["pairs"]]
        now = np.linalg.norm(x[pairs[:, 1]] - x[pairs[:, 0]], axis=1)
        before = np.maximum(np.linalg.norm(particles[pairs[:, 1]] - particles[pairs[:, 0]], axis=1), 1e-12)
        if show == 'elongation':
            out[e["index"]] = 100.0 * (now - before) / before
        else:
            out[e["index"]] = ea * np.where(e["weft"], across, 1.0) / before * (now - factor * before)
    return shape.derived(out, name, None, ("span",))
