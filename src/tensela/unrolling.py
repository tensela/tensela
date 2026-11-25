"""Unroll: flattening surfaces to cut them from a sheet (metal, board, cloth).

A developable surface flattens without stretching: each triangle rests on one already placed keeping its three sides
(as a paper model unfolds). One that is not (a dome, a saddle) is flattened all the same, approximately: the points
settle so that each side comes close to its true length, and how much what does not fit stretches is measured. The
pieces lie on the XY plane, side by side, ready to cut.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from .data import Data, ShapeError, _require_size_
from .geometry import CURVE, CLOSED_CURVE
from .language import tr
from .meshes import _elements, kind_mesh
from .surfaces import DEVELOPABLE_TOLERANCE, _gauss_image

WHAT_UNROLL = ('unrolled', 'outlines', 'folds', 'stretch')
#: A closed body with more flat faces than this is curved (a sphere in triangles): its net is not made.
FACES_A_NET = 80
#: How many faces to start the net from, at most, looking for one where it does not land on itself.
NET_TRIES = 12
PLACE = ('in a row', 'in place')
#: Rounds, at most, to settle a surface that is not developable, and how much of the previous step is added
#: to the next (with inertia it oscillates: without it, slower but safe).
TURNS_RELAX = 800
INERTIA = 0.0


def _faces_y_welding(data: Data, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The triangles of an element and, for each point, the point it is welded to (those that are the same): on a grid
    surface, only a row or column that closes into a point (the pole of a dome, the tip of a cone), not the seam of a
    closed one (it opens there); on a mesh, all those that coincide."""
    grid = getattr(data.kind, "grid", None)
    faces = []
    for face in data.kind.faces:
        for j in range(1, len(face) - 1):
            faces.append((face[0], face[j], face[j + 1]))
    faces = np.array(faces, dtype=np.int64)
    weld = np.arange(len(v))
    size_ = float(np.ptp(v, axis=0).max()) or 1.0
    if grid is not None:
        f, c = grid
        r = v.reshape(f, c, 3)
        idx = np.arange(f * c).reshape(f, c)
        for i in range(f):
            if np.ptp(r[i], axis=0).max() < 1e-9 * size_:      # a row that is a point
                weld[idx[i]] = idx[i, 0]
        for j in range(c):
            if np.ptp(r[:, j], axis=0).max() < 1e-9 * size_:
                weld[idx[:, j]] = weld[idx[0, j]]
    else:
        keys = np.round(v / (size_ * 1e-9)).astype(np.int64)
        _, first, group = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        weld = first[group.ravel()]
    return faces, weld


def _unfold(p3: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """The 2D positions of the (welded) points of some triangles, unfolding them one by one from the biggest: each one
    rests on a side already placed and keeps its three sides. By components (each one, apart)."""
    n = len(p3)
    pos = np.full((n, 2), np.nan)
    sides = {}
    for t, (a, b, c) in enumerate(tri):
        for x, y in ((a, b), (b, c), (c, a)):
            sides.setdefault((min(x, y), max(x, y)), []).append(t)
    area = np.linalg.norm(np.cross(p3[tri[:, 1]] - p3[tri[:, 0]], p3[tri[:, 2]] - p3[tri[:, 0]]), axis=1)
    done = np.zeros(len(tri), bool)
    shift = 0.0
    for start in np.argsort(-area):
        if done[start]:
            continue
        a, b, c = tri[start]
        if not np.isnan(pos[a, 0]):
            continue
        # The first: a at the origin, b on x, c above (the triangle, in its direction).
        ab = np.linalg.norm(p3[b] - p3[a])
        pos[a] = (shift, 0.0)
        pos[b] = (shift + ab, 0.0)
        pos[c] = _third(pos[a], pos[b], np.linalg.norm(p3[c] - p3[a]), np.linalg.norm(p3[c] - p3[b]))
        done[start] = True
        queue = deque([start])
        while queue:
            t = queue.popleft()
            for x, y in ((tri[t][0], tri[t][1]), (tri[t][1], tri[t][2]), (tri[t][2], tri[t][0])):
                o = [q for q in tri[t] if q != x and q != y][0]       # the third of t, already placed
                for s in sides[(min(x, y), max(x, y))]:
                    if done[s]:
                        continue
                    done[s] = True
                    queue.append(s)
                    z = [q for q in tri[s] if q != x and q != y]
                    if not z or not np.isnan(pos[z[0], 0]) or np.isnan(pos[x, 0]) or np.isnan(pos[y, 0]):
                        continue
                    z = z[0]
                    # On the other side of the shared side from the third of t (it unfolds, like paper; it does not
                    # depend on which way each triangle turns).
                    candidate = _third(pos[x], pos[y], np.linalg.norm(p3[z] - p3[x]), np.linalg.norm(p3[z] - p3[y]))
                    side_o = _from_what_side(pos[x], pos[y], pos[o])
                    if side_o != 0 and _from_what_side(pos[x], pos[y], candidate) == side_o:
                        candidate = _third(pos[y], pos[x], np.linalg.norm(p3[z] - p3[y]),
                                             np.linalg.norm(p3[z] - p3[x]))
                    pos[z] = candidate
        placed = ~np.isnan(pos[:, 0])
        shift = float(np.nanmax(pos[placed, 0])) + 1.0
    return pos


def _triangles_cross(a: np.ndarray, b: np.ndarray, gap: float) -> bool:
    """Whether some 2D triangles of `a` (k, 3, 2) overlap some of `b` (m, 3, 2): more than touching by a side or a
    corner (separating axes, with a margin of `gap`)."""
    if not len(a) or not len(b):
        return False
    # First by the box around each whole group: most are far away.
    b = b[(b.min(1) < a.max((0, 1)) - gap).all(1) & (b.max(1) > a.min((0, 1)) + gap).all(1)]
    if not len(b):
        return False
    a = a[(a.min(1) < b.max((0, 1)) - gap).all(1) & (a.max(1) > b.min((0, 1)) + gap).all(1)]
    if not len(a):
        return False
    near = (a.min(1)[:, None] < b.max(1)[None] - gap).all(-1) & (b.min(1)[None] < a.max(1)[:, None] - gap).all(-1)
    i, j = np.nonzero(near)
    if not len(i):
        return False
    A, B = a[i], b[j]
    apart = np.zeros(len(i), bool)
    for T in (A, B):
        for k in range(3):
            e = T[:, (k + 1) % 3] - T[:, k]
            n = np.stack([-e[:, 1], e[:, 0]], -1)
            n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)
            pa, pb = np.einsum('pvd,pd->pv', A, n), np.einsum('pvd,pd->pv', B, n)
            apart |= (pa.max(1) <= pb.min(1) + gap) | (pb.max(1) <= pa.min(1) + gap)
    return not apart.all()


def _sides_touch(a: np.ndarray, b: np.ndarray, gap: float) -> bool:
    """Whether some 2D segments of `a` (k, 2, 2) lie along some of `b` (m, 2, 2) for more than a point: two faces of
    a net stuck by a side that is not a fold would come out of the cut welded."""
    if not len(a) or not len(b):
        return False
    b = b[(b.min(1) <= a.max((0, 1)) + gap).all(1) & (b.max(1) >= a.min((0, 1)) - gap).all(1)]
    if not len(b):
        return False
    d = a[:, 1] - a[:, 0]
    length = np.linalg.norm(d, axis=1)
    keep = length > gap
    a, d, length = a[keep], d[keep] / np.maximum(length[keep, None], 1e-300), length[keep]
    rel = b[None] - a[:, None, None, 0]                                   # (k, m, 2, 2)
    off = rel[..., 0] * d[:, None, None, 1] - rel[..., 1] * d[:, None, None, 0]
    along = rel[..., 0] * d[:, None, None, 0] + rel[..., 1] * d[:, None, None, 1]
    on_line = (np.abs(off) <= gap).all(-1)
    low = np.maximum(along.min(-1), 0.0)
    high = np.minimum(along.max(-1), length[:, None])
    return bool((on_line & (high - low > gap)).any())


def _from_what_side(pa, pb, q) -> int:
    """On which side of the line pa → pb q is: 1 to the left, −1 to the right, 0 on it."""
    cross = (pb[0] - pa[0]) * (q[1] - pa[1]) - (pb[1] - pa[1]) * (q[0] - pa[0])
    return int(np.sign(cross))


def _third(pa, pb, gives: float, db: float) -> np.ndarray:
    """The point at `da` from pa and at `db` from pb, to the left of pa → pb."""
    d = pb - pa
    length = float(np.linalg.norm(d)) or 1e-12
    x = (gives * gives - db * db + length * length) / (2 * length)
    y = np.sqrt(max(gives * gives - x * x, 0.0))
    e = d / length
    return pa + e * x + np.array([-e[1], e[0]]) * y


def _relax(pos: np.ndarray, p3: np.ndarray, edges: np.ndarray, turns: int | None = None) -> np.ndarray:
    """Settles the points so that each edge comes close to its true length (a surface that is not developable cannot
    have them all: what is left over is spread)."""
    length = np.linalg.norm(p3[edges[:, 1]] - p3[edges[:, 0]], axis=1)
    n = len(pos)
    how_many = np.bincount(edges.ravel(), minlength=n).astype(float)
    how_many[how_many == 0] = 1
    a, b = edges[:, 0], edges[:, 1]
    still = 1e-7 * (float(length.mean()) or 1.0)          # it no longer moves: done
    momentum = np.zeros_like(pos)                         # with inertia: it converges several times faster
    for _ in range(TURNS_RELAX if turns is None else turns):
        d = pos[b] - pos[a]
        now = np.maximum(np.linalg.norm(d, axis=1), 1e-12)
        error = (now - length) / now
        if np.abs(error).max() < 1e-7:
            break
        move = 0.5 * error[:, None] * d
        change = np.column_stack([np.bincount(a, move[:, k], n) - np.bincount(b, move[:, k], n) for k in (0, 1)])
        change /= how_many[:, None]
        momentum = INERTIA * momentum + change
        pos = pos + momentum
        if np.abs(change).max() < still:
            break
    return pos


#: In the fine grid, after the coarse one, fewer rounds are enough.
FINE_TURNS = 200


def _fine_grid(v: np.ndarray, f: int, c: int) -> np.ndarray:
    """The grid of a piece, with more points in a straight direction (of 2), for the Gauss image test."""
    from .surfaces import _bilinear
    r = v.reshape(f, c, 3)
    if f == 2 or c == 2:
        fu, fv = np.linspace(0, 1, 17 if f == 2 else f), np.linspace(0, 1, 17 if c == 2 else c)
        r = _bilinear(r, *np.meshgrid(fu, fv, indexing="ij"))
    return r


def _coarse_fit_in(pieces: list, f: int, c: int) -> None:
    """Settles the pieces (of grid r × c) first in a coarse grid, of about 17 × 17 points, and carries that settling to
    the fine one: there the adjustment travels from one end to the other in few rounds."""
    from .geometry import kind_surface
    iu = np.unique(np.r_[np.arange(0, f, max(1, (f - 1) // 16)), f - 1])
    iv = np.unique(np.r_[np.arange(0, c, max(1, (c - 1) // 16)), c - 1])
    if len(iu) == f and len(iv) == c:
        return                                           # it is already coarse
    kind = kind_surface(len(iu), len(iv))
    faces = np.array([(q[0], q[1], q[2]) for q in kind.faces] + [(q[0], q[2], q[3]) for q in kind.faces])
    edges = _edges(faces)
    n = len(iu) * len(iv)
    base = [x["pos"].reshape(f, c, 2)[np.ix_(iu, iv)].reshape(-1, 2) for x in pieces]
    p3 = [x["v"].reshape(f, c, 3)[np.ix_(iu, iv)].reshape(-1, 3) for x in pieces]
    together = _relax(np.vstack(base), np.vstack(p3), np.vstack([edges + k * n for k in range(len(pieces))]))
    for k, x in enumerate(pieces):
        move = (together[k * n:(k + 1) * n] - base[k]).reshape(len(iu), len(iv), 2)
        # To the fine grid: first along v, then along u (interpolating between the coarse points).
        a_lo_v = np.stack([np.stack([np.interp(np.arange(c), iv, move[i, :, d]) for d in (0, 1)], -1)
                           for i in range(len(iu))])
        fine = np.stack([np.stack([np.interp(np.arange(f), iu, a_lo_v[:, j, d]) for d in (0, 1)], -1)
                         for j in range(c)], axis=1)
        x["pos"] = x["pos"] + fine.reshape(-1, 2)


def _from__grid(v: np.ndarray, f: int, c: int) -> np.ndarray:
    """A flat starting point for a grid surface that is not developable: its (u, v) grid stretched to its sizes
    (without flipped triangles, which then would not let themselves settle)."""
    r = v.reshape(f, c, 3)
    du = np.linalg.norm(np.diff(r, axis=0), axis=-1).mean(axis=1)          # the length of each step in u
    dv = np.linalg.norm(np.diff(r, axis=1), axis=-1).mean(axis=0)
    x = np.concatenate([[0.0], np.cumsum(du)])
    y = np.concatenate([[0.0], np.cumsum(dv)])
    xx, yy = np.meshgrid(x, y, indexing="ij")
    return np.column_stack([xx.ravel(), yy.ravel()])


def _net(v: np.ndarray, tri: np.ndarray, flat: np.ndarray | None = None):
    """The net of a closed body with flat faces (a prism, a pyramid, a box): its faces unfolded one by one, each one
    turning about the edge it shares with the previous one (the coplanar faces, together: one true face). Returns the
    points of each corner of each triangle (n·3, 2) and the fold edges (2D segments), or None if the body is curved
    (too many faces). `flat`: the triangles without area of the body (points in a straight line along a side): they
    take no part in the shape, but each one goes with its face to draw its edge (without them, a side split at
    different points on its two faces would leave a cut inside the face)."""
    n_t = len(tri)
    normal = np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]])
    area = np.linalg.norm(normal, axis=1)
    normal = normal / np.maximum(area[:, None], 1e-300)
    sides: dict = {}
    for t, (a, b, c) in enumerate(tri):
        for x, y in ((a, b), (b, c), (c, a)):
            sides.setdefault((min(x, y), max(x, y)), []).append(t)
    # The true faces: neighbouring triangles on the same plane.
    parent = list(range(n_t))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for ts in sides.values():
        for t1 in ts:
            for t2 in ts:
                if t1 < t2 and abs(float(normal[t1] @ normal[t2])) > 1 - 1e-6:
                    parent[root(t1)] = root(t2)
    # Also those on the same plane that only touch by a corner: the parts of a cap cut by ears along a sampled curve
    # (the triangles without area that joined them are left out).
    size_ = float(np.ptp(v, axis=0).max()) or 1.0
    flip = np.where((normal[np.arange(n_t), np.argmax(np.abs(normal), axis=1)] < 0)[:, None], -1.0, 1.0)
    plane = np.round(np.column_stack([normal * flip, (normal * flip * v[tri[:, 0]]).sum(1, keepdims=True) / size_]),
                     5)
    around: dict = {}
    for t, corners in enumerate(tri):
        for q in corners:
            around.setdefault((int(q), *plane[t]), []).append(t)
    for ts in around.values():
        for t in ts[1:]:
            parent[root(t)] = root(ts[0])
    # And those on the same plane whose edges run along each other for a stretch (a side split at different points
    # on its two parts, without a triangle between them).
    by_plane: dict = {}
    for t in range(n_t):
        by_plane.setdefault(tuple(plane[t]), set()).add(root(t))
    for key, roots in by_plane.items():
        if len(roots) < 2:
            continue
        n = np.array(key[:3])
        e1 = np.cross(n, [1.0, 0, 0] if abs(n[0]) < 0.9 else [0, 1.0, 0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1)
        rim = {}
        for r_ in roots:
            mine = tri[[t for t in range(n_t) if root(t) == r_]]
            seg = np.array([[v[a], v[b]] for loop in _outlines(mine) for a, b in zip(loop, loop[1:] + loop[:1])])
            rim[r_] = np.stack([seg @ e1, seg @ e2], -1) if len(seg) else np.zeros((0, 2, 2))
        roots = sorted(roots)
        for i, r1 in enumerate(roots):
            for r2 in roots[i + 1:]:
                if root(r1) != root(r2) and _sides_touch(rim[r1], rim[r2], 1e-7 * size_):
                    parent[root(r1)] = root(r2)
    group = np.array([root(t) for t in range(n_t)])
    faces = {g: np.flatnonzero(group == g) for g in np.unique(group)}
    if len(faces) > FACES_A_NET:
        return None
    # Each face on its plane: its points in 2D.
    # Each flat triangle, with the face it continues: one on whose plane its three points lie and that runs one of
    # its sides the other way round (as two neighbours in a closed mesh). One along the foot of a pyramid lies on the
    # plane of the base and on that of the side, but only continues the base.
    whole = {g: tri[ts] for g, ts in faces.items()}
    if flat is not None and len(flat):
        runs: dict = {}
        for t, (a, b, c) in enumerate(tri):
            for x, y in ((a, b), (b, c), (c, a)):
                runs.setdefault((int(x), int(y)), set()).add(int(group[t]))
        pending = [tuple(int(q) for q in f) for f in flat]
        moved = True
        while pending and moved:
            moved = False
            for f in list(pending):
                mine = [(f[0], f[1]), (f[1], f[2]), (f[2], f[0])]
                for g in sorted({g for x, y in mine for g in runs.get((y, x), ())}):
                    n, o = normal[faces[g][0]], v[tri[faces[g][0], 0]]
                    if all(abs(float(n @ (v[q] - o))) < 1e-7 * size_ for q in f):
                        whole[g] = np.vstack([whole[g], [f]])
                        for e in mine:
                            runs.setdefault(e, set()).add(g)
                        pending.remove(f)
                        moved = True
                        break
    local = {}
    for g, ts in faces.items():
        points = np.unique(whole[g])
        n = normal[ts[np.argmax(area[ts])]]
        e1 = v[tri[ts[0], 1]] - v[tri[ts[0], 0]]
        e1 = e1 / np.linalg.norm(e1)
        e2 = np.cross(n, e1)
        o = v[points[0]]
        local[g] = {int(q): np.array([(v[q] - o) @ e1, (v[q] - o) @ e2]) for q in points}
    # The hinges: the edges between two faces.
    neighbours: dict = {}
    for (x, y), ts in sides.items():
        gs = {int(group[t]) for t in ts}
        if len(gs) == 2:
            g1, g2 = sorted(gs)
            neighbours.setdefault(g1, {}).setdefault(g2, []).append((x, y))
            neighbours.setdefault(g2, {}).setdefault(g1, []).append((x, y))
    area_face = {g: float(area[ts].sum()) for g, ts in faces.items()}
    size_ = float(np.ptp(v, axis=0).max()) or 1.0

    def unfold(g, h, edges, set_g):
        """Face `h` laid beside face `g` (already placed), turned about the hinge they share: its points, or None."""
        qs = sorted({q for a in edges for q in a})
        on = np.array([set_g[q] for q in qs])           # its points are on a line: its two ends
        qa = qs[int(np.argmax(((on - on[0]) ** 2).sum(1)))]
        qb = qs[int(np.argmax(((on - set_g[qa]) ** 2).sum(1)))]
        pa_, pb_ = set_g[qa], set_g[qb]
        if np.linalg.norm(pb_ - pa_) < 1e-12:
            return None
        # Which side each face lies on: the triangle of each one that touches the hinge (the centre of a whole
        # concave face can fall on the wrong side of it).
        x, y = edges[0]
        touching = sides[(min(x, y), max(x, y))]
        t_g = next(t for t in touching if group[t] == g)
        t_h = next(t for t in touching if group[t] == h)
        centre_g = np.mean([set_g[int(q)] for q in tri[t_g]], axis=0)
        for mirror in (False, True):
            lh = {q: (p * [1.0, -1.0] if mirror else p) for q, p in local[h].items()}
            ca, cb = lh[qa], lh[qb]
            ang = np.arctan2(*(pb_ - pa_)[::-1]) - np.arctan2(*(cb - ca)[::-1])
            R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
            placed = {q: pa_ + R @ (p - ca) for q, p in lh.items()}
            centre_h = np.mean([placed[int(q)] for q in tri[t_h]], axis=0)
            if _from_what_side(pa_, pb_, centre_h) != _from_what_side(pa_, pb_, centre_g):
                break                                     # on the other side of the hinge: unfolded
        return placed, np.array([pa_, pb_])

    # To test whether a face lands on another, only its true corners count: a side split in many short pieces (a
    # sampled curve) would make hundreds of thin triangles for the same face.
    from .geometry import _triangulate_plan
    simple, rims = {}, {}
    for g, ts in faces.items():
        loops = []
        for loop in _outlines(whole[g]):
            q2 = np.array([local[g][int(i)] for i in loop])
            a_, b_ = q2 - np.roll(q2, 1, 0), np.roll(q2, -1, 0) - q2
            turns = np.abs(a_[:, 0] * b_[:, 1] - a_[:, 1] * b_[:, 0]) > \
                1e-9 * np.linalg.norm(a_, axis=1) * np.linalg.norm(b_, axis=1)
            loops.append([int(i) for i, t in zip(loop, turns) if t])
        rims[g] = [(a, b) for loop in loops for a, b in zip(loop, loop[1:] + loop[:1])]
        simple[g] = tri[ts]
        if len(loops) == 1 and len(loops[0]) >= 3:          # without holes: its corners, by ears
            corners = loops[0]
            flat = np.array([[*local[g][i], 0.0] for i in corners])
            ears = np.array([[corners[i] for i in t] for t in _triangulate_plan(flat)], dtype=int).reshape(-1, 3)
            if len(ears):
                p_ = np.array([[local[g][int(i)] for i in t] for t in ears])
                e1, e2 = p_[:, 1] - p_[:, 0], p_[:, 2] - p_[:, 0]
                if abs(np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() - area_face[g]) < 1e-6 * area_face[g]:
                    simple[g] = ears

    def triangles_of(g, points):
        return np.array([[points[int(q)] for q in t] for t in simple[g]])

    def rim_of(g, points, fold=None):
        """The edge of a face as 2D segments (without those along `fold`, the hinge it hangs from)."""
        out = np.array([[points[a], points[b]] for a, b in rims[g]]).reshape(-1, 2, 2)
        if fold is not None and len(out):
            d = fold[1] - fold[0]
            n = float(np.linalg.norm(d))
            d = d / max(n, 1e-300)
            rel = out - fold[0]
            off = np.abs(rel[..., 0] * d[1] - rel[..., 1] * d[0]).max(-1)
            along = rel[..., 0] * d[0] + rel[..., 1] * d[1]
            out = out[~((off <= 1e-6 * size_) & (along.min(-1) >= -1e-6 * size_)
                        & (along.max(-1) <= n + 1e-6 * size_))]
        return out

    hinge = {g: {h: sum(float(np.linalg.norm(v[x] - v[y])) for x, y in edges) for h, edges in hs.items()}
             for g, hs in neighbours.items()}

    def direction(edges):
        d = v[edges[0][1]] - v[edges[0][0]]
        return d / max(float(np.linalg.norm(d)), 1e-300)

    def straight(came, edges) -> float:
        """How parallel a hinge is to the one a face was hung from: 1, going straight on."""
        return 0.0 if came is None else round(abs(float(direction(edges) @ came)), 6)

    def lay_out(start, how):
        """The faces unfolded from `start`: each one hung from a face already laid where it does not land on the
        others; if it lands on them from every side, it waits for another to hang from, and the last that fit nowhere
        start another piece. `how`: 'breadth' (around the first face, the faces it touches, the largest first),
        'hinge' (on from the last one laid, by its longest hinge) or 'strip' (on from the last one laid, straight on:
        across the hinge parallel to the one it was hung from, so the walls of a prism make a straight strip and
        each cap hangs from a wall of its outer edge, where it cannot land on the strip). Returns the pieces, each
        one [points, folds]."""
        chain = how != 'breadth'
        pieces, left = [], set(faces)
        while left:
            first = start if start in left else max(left, key=lambda g: area_face[g])
            left.discard(first)
            set_ = {first: dict(local[first])}
            laid = triangles_of(first, set_[first])
            edge = rim_of(first, set_[first])
            folds, failed = [], set()                 # what landed on the others still does (they only grow)
            entry = {first: None}                     # the hinge each face was hung from (its direction)
            grew = True
            while grew:
                grew = False
                for g in (list(set_)[::-1] if chain else list(set_)):
                    by = {'breadth': lambda x: -area_face[x[0]], 'hinge': lambda x: -hinge[g][x[0]],
                          'strip': lambda x: (-straight(entry[g], x[1]), area_face[x[0]])}[how]
                    for h, edges in sorted(neighbours.get(g, {}).items(), key=by):
                        if h not in left or (g, h) in failed:
                            continue
                        found = unfold(g, h, edges, set_[g])
                        if found is None:
                            failed.add((g, h))
                            continue
                        placed, fold = found
                        mine, rim = triangles_of(h, placed), rim_of(h, placed, fold)
                        if _triangles_cross(mine, laid, 1e-7 * size_) or _sides_touch(rim, edge, 1e-6 * size_):
                            failed.add((g, h))            # it would land on another face: from somewhere else
                            continue
                        set_[h] = placed
                        entry[h] = direction(edges)
                        laid = np.concatenate([laid, mine])
                        edge = np.concatenate([edge, rim_of(h, placed)])
                        folds.append(fold)
                        left.discard(h)
                        grew = True
                        if chain:
                            break
                    if grew and chain:
                        break                             # on from the one just laid
            pieces.append([set_, folds])
        return pieces

    # From the largest face, breadth first; if the net lands on itself, other orders and other first faces, and the
    # one that needs fewest pieces.
    order, sizes = [], set()
    for g in sorted(faces, key=lambda g: -area_face[g]):     # one of each size (the walls of a prism, alike)
        if round(area_face[g] / size_ ** 2, 6) not in sizes:
            sizes.add(round(area_face[g] / size_ ** 2, 6))
            order.append(g)
    def holes(pieces) -> int:
        """How many gaps a net encloses (they can be cut, but a net without them is cleaner to cut and fold)."""
        count = 0
        for points, _ in pieces:
            rings = [_only_corners(np.array([points[g][int(i)] for i in loop]))
                     for g in points for loop in _outlines(whole[g])]
            count += max(len(_polygons_outline(rings, size_)) - 1, 0)
        return count

    best, score = None, None
    for start in order[:NET_TRIES]:
        for how in ('breadth', 'hinge', 'strip'):
            pieces = lay_out(start, how)
            mine = (len(pieces), holes(pieces) if len(pieces) == 1 else 0)
            if best is None or mine < score:
                best, score = pieces, mine
            if score == (1, 0):
                break
        if score == (1, 0):
            break
    # The pieces side by side, a little apart (each one ready to cut on its own).
    set_, folds = {}, []
    right = None
    for points, piece_folds in best:
        everything = np.array([p for face in points.values() for p in face.values()])
        shift = np.zeros(2)
        if right is not None:
            shift = np.array([right + 0.15 * size_ - everything[:, 0].min(), 0.0])
        right = float(everything[:, 0].max() + shift[0])
        for g, face in points.items():
            set_[g] = {q: p + shift for q, p in face.items()}
        folds += [f + shift for f in piece_folds]
    if len(set_) != len(faces):
        return None
    corners = np.array([[set_[int(group[t])][int(q)] for q in tri[t]] for t in range(n_t)]).reshape(-1, 2)
    # The edge of each face, only with its true corners (without the intermediate points of a straight side): so
    # a hinge is a single segment on both faces and the outline of the net comes out clean.
    polygons = []
    for g, ts in faces.items():
        for loop in _outlines(whole[g]):
            q = np.array([set_[g][int(i)] for i in loop])
            polygons.append(_only_corners(q))
    return corners, folds, polygons


def _only_corners(q: np.ndarray) -> np.ndarray:
    """A 2D polygon without the points that do not turn."""
    a, b = q - np.roll(q, 1, 0), np.roll(q, -1, 0) - q
    rotation = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    length = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
    return q[np.abs(rotation) > 1e-9 * np.maximum(length, 1e-300)]


def _polygons_outline(polygons: list, size_: float) -> list[np.ndarray]:
    """The outline of some polygons stuck by their sides (a net): the sides nobody shares, chained."""
    keys = {}

    def key(p):
        k = tuple(np.round(p / (size_ * 1e-7)).astype(np.int64))
        keys.setdefault(k, p)
        return k
    sides = {}
    for q in polygons:
        x, y = q[:, 0], q[:, 1]
        if (x * np.roll(y, -1) - np.roll(x, -1) * y).sum() < 0:   # all in the same direction (anticlockwise)
            q = q[::-1]
        ks = [key(p) for p in q]
        for a, b in zip(ks, ks[1:] + ks[:1]):
            if a != b:
                sides[(a, b)] = sides.get((a, b), 0) + 1
    # The sides nobody shares, from each point. Where the net touches itself at a corner (two faces meeting only
    # there), two leave from the same point: each loop takes the one that turns most to the right, so no side is
    # lost and each lobe closes on its own.
    leaving: dict = {}
    for (a, b) in sides:
        if (b, a) not in sides:
            leaving.setdefault(a, []).append(b)
    loops = []
    while leaving:
        a = next(iter(leaving))
        loop, came, x = [a], None, a
        while True:
            options = leaving.get(x)
            if not options:
                break
            if len(options) > 1 and came is not None:
                back = keys[came] - keys[x]

                def turn(b):                          # the angle from the way back, anticlockwise: smallest, rightmost
                    ahead = keys[b] - keys[x]
                    return np.arctan2(back[0] * ahead[1] - back[1] * ahead[0], back @ ahead) % (2 * np.pi)
                options.sort(key=turn)
            b = options.pop(0)
            if not options:
                del leaving[x]
            came, x = x, b
            if x == a:
                break
            loop.append(x)
        if len(loop) >= 3:
            loops.append(np.array([keys[k] for k in loop]))
    return loops


def _is_closed(tri: np.ndarray) -> bool:
    """Whether some triangles close a body: each edge shared by two (without looking at which way each one turns)."""
    edges = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    _, how_many = np.unique(edges, axis=0, return_counts=True)
    return bool(len(how_many)) and bool((how_many >= 2).all())


def _outlines(tri: np.ndarray) -> list[list[int]]:
    """The edges of some triangles (the edges only one uses), chained in closed loops."""
    tally: dict = {}
    for a, b, c in tri:
        for x, y in ((a, b), (b, c), (c, a)):
            tally[(x, y)] = tally.get((x, y), 0) + 1
    next_ = {}
    for (x, y) in tally:
        if (y, x) not in tally:                       # an edge: nobody shares the side
            next_[x] = y
    loops, seen = [], set()
    for x in list(next_):
        if x in seen:
            continue
        loop, y = [], x
        while y not in seen and y in next_:
            seen.add(y)
            loop.append(y)
            y = next_[y]
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def _edges(tri: np.ndarray) -> np.ndarray:
    """The sides of some triangles, each one once."""
    return np.unique(np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1), axis=0)


def _length_change(pos: np.ndarray, p3: np.ndarray, edges: np.ndarray, size_: float, as_: str) -> float:
    """How much the sides change length on flattening: the one that most (without those of length 0) or, on average, all."""
    length = np.linalg.norm(p3[edges[:, 1]] - p3[edges[:, 0]], axis=1)
    d = np.linalg.norm(pos[edges[:, 1]] - pos[edges[:, 0]], axis=1)
    if as_ == "average":
        return float(np.abs(d - length).sum() / max(float(length.sum()), 1e-300))
    measurable = (length > 1e-6 * size_) & np.isfinite(d)
    return float(np.max(np.abs(d - length)[measurable] / length[measurable])) if measurable.any() else 0.0


_FLATTENED: dict = {}


def _pieces_flattened(geometry: Data, elements: np.ndarray) -> list:
    """The flattened pieces (before placing them): the last one is kept, because «unrolled», «outlines» and «stretch»
    are usually three nodes on the same thing."""
    import copy
    import hashlib
    key = hashlib.blake2b(np.ascontiguousarray(elements, dtype=float).tobytes()
                            + repr(geometry.kind.faces[:4]).encode() + repr(geometry.kind.grid).encode()
                            + str(len(geometry.kind.faces)).encode(), digest_size=16).digest()
    if key not in _FLATTENED:
        _FLATTENED.clear()
        _FLATTENED[key] = _flatten(geometry, elements)
    return copy.copy(_FLATTENED[key])


def _flatten(geometry: Data, elements: np.ndarray) -> list:
    # 1) Each piece, unfolded triangle by triangle (exact if it is developable).
    pieces = []
    for v in np.asarray(elements, dtype=float):
        faces, weld = _faces_y_welding(geometry, v)
        tri = weld[faces]
        area = np.linalg.norm(np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]]), axis=1)
        size_ = float(np.ptp(v, axis=0).max()) or 1.0
        different = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
        good = different & (area > 1e-12 * size_ ** 2)
        # Closed? With all the triangles (the zero-area ones seal the T joints of an Extrude body).
        closed = _is_closed(tri[different])
        flat = tri[different & ~good]
        tri = tri[good]
        if not len(tri):
            raise ShapeError(tr('A piece has no area: there is nothing to unroll.'))
        loops = [] if closed else _outlines(tri)
        if closed:                                       # a closed body: its net, if it has flat faces
            net = _net(v, tri, flat)
            if net is None:
                raise ShapeError(tr('A piece is a closed, curved body: it cannot be flattened without cutting '
                                      'it (split it first, with Split surface or Sub surface). A body with flat '
                                      'faces (a box, a prism, a pyramid) gives its net.'))
            corners, folds, polygons = net
            # The triangles of the net: those of each triangle of the body (also the zero-area ones, which are not seen:
            # so the mesh has the same faces as the body).
            pieces.append(dict(v=v, net=True, pos=corners, folds=folds, polygons=polygons, size=size_,
                               n_tri=len(tri)))
            continue
        grid = getattr(geometry.kind, "grid", None)
        to_view = grid is not None and _gauss_image(_fine_grid(v, *grid))[()] > \
            DEVELOPABLE_TOLERANCE                      # a grid that is not developable: no need to test
        pos = None if to_view else _unfold(v, tri)
        edges = _edges(tri)
        piece = dict(v=v, faces=faces, good=good, weld=weld, tri=tri, loops=loops, pos=pos,
                     edges=edges, size=size_)
        if to_view or _length_change(pos, v, edges, size_, "maximum") > 1e-6:   # it settles afterwards
            if grid is not None:                       # from the grid, without welding the poles (they open)
                piece.update(pos=_from__grid(v, *grid), edges=_edges(faces[good]),
                             weld=np.arange(len(v)))
            else:
                piece["pos"] = np.nan_to_num(pos)
            piece["relajar"] = True
        pieces.append(piece)
    # 2) Those that are not developable, settled all at once (a single computation: much faster).
    relax = [x for x in pieces if x.get("relajar")]
    grid = getattr(geometry.kind, "grid", None)
    if relax and grid is not None:                  # first in a coarse grid (it converges right away)
        _coarse_fit_in(relax, *grid)
    if relax:
        from_ = np.cumsum([0] + [len(x["pos"]) for x in relax])
        together = _relax(np.vstack([x["pos"] for x in relax]), np.vstack([x["v"] for x in relax]),
                          np.vstack([x["edges"] + d for x, d in zip(relax, from_[:-1])]),
                          FINE_TURNS if grid is not None else TURNS_RELAX)
        for x, a, b in zip(relax, from_[:-1], from_[1:]):
            x["pos"] = together[a:b]
    return pieces


def unroll(geometry: Data, what: str = 'unrolled', place: str = 'in a row', spacing=1.0,
                name: str | None = None) -> Data:
    """Flattens each surface (or mesh) on the XY plane, to cut it from a sheet: **unrolled** (the flat pieces),
    **outlines** (their edges, closed: for cutting or the DXF), **folds** (in the net of a closed body with flat faces:
    the edges where it folds) or **stretch** (how much its sides change length on flattening, on average, in %: 0 in a
    developable one). `place`: **in a row** (side by side, separated by `spacing`, each one standing: the long way, along
    y) or **in place** (each one flattened where it falls, without moving it)."""
    if geometry.kind is None or geometry.kind.faces is None or geometry.kind.curve:
        raise ShapeError(tr('«{name}» should be a surface or a mesh (something with faces).').format(
            name=geometry._name()))
    if what not in WHAT_UNROLL:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_UNROLL)))
    if place not in PLACE:
        raise ShapeError(tr('They can be placed: {options}.').format(options=", ".join(tr(c) for c in PLACE)))
    spacing = float(np.asarray(getattr(spacing, "values", spacing), float).ravel()[0])
    elements = _elements(geometry)
    _require_size_({"point": int(np.prod(elements.shape[:-1]))}, tr('The unrolling'))
    pieces = _pieces_flattened(geometry, elements)
    # 3) Each piece: how much it stretched and where it goes.
    flats, stretched, loops_of = [], [], []
    free_x = 0.0
    folds_of = []
    for x in pieces:
        v = x["v"]
        if not (sum(len(q) for q in x["polygons"]) if x.get("net") else len(x["tri"])):   # size 0, or too thin
            raise ShapeError(tr('«{name}» has nothing to unroll: a body or a surface of size 0, or far too long '
                                'and thin (a measure in 0, or an extra digit?).').format(name=geometry._name()))
        if x.get("net"):                                  # the net of a body: one face, one polygon (its corners)
            outline = _polygons_outline(x["polygons"], x["size"])
            n_pos = sum(len(q) for q in x["polygons"])
            pos = np.vstack(list(x["polygons"]) + outline)  # the outline, at the end (to move it with the piece)
            stretched.append(0.0)
            used = np.arange(n_pos)
            folds = [p.copy() for p in x["folds"]]
        else:
            pos, weld = x["pos"], x["weld"]
            stretched.append(100.0 * _length_change(pos, v, x["edges"], x["size"], "average"))
            used = np.unique(x["tri"])
            folds = []
            # The points that touch no good triangle (repeated ones of a pole), where their welded one is.
            pos = pos[weld]
            missing = np.isnan(pos[:, 0])
            if missing.any():
                pos[missing] = np.nanmean(pos[np.unique(weld[x["faces"]][x["good"]])], axis=0)
        before = pos.copy()
        if place == 'in place':                     # flattened where it falls: its centre, that of the piece in plan
            centre = v.mean(axis=0) if x.get("net") else v[used].mean(axis=0)   # a net: «used» counts its polygons
            pos = pos - pos[used].mean(axis=0) + centre[:2]
        else:                                            # standing (the long way, along y), and in a row
            q = pos[used] - pos[used].mean(axis=0)
            _, _, axes = np.linalg.svd(q, full_matrices=False)
            rotation = axes.T if np.linalg.det(axes) > 0 else axes.T @ np.diag([1.0, -1.0])
            pos = (pos - pos[used].mean(axis=0)) @ rotation @ np.array([[0.0, 1.0], [-1.0, 0.0]])
            minimum, maximum = pos[used].min(axis=0), pos[used].max(axis=0)
            pos = pos - minimum + np.array([free_x, 0.0])
            free_x += float(maximum[0] - minimum[0]) + spacing
        if x.get("net"):
            from_ = np.cumsum([n_pos] + [len(c) for c in outline])
            loops_of.append([list(range(a_, b_)) for a_, b_ in zip(from_[:-1], from_[1:])])
            flats.append(np.column_stack([pos, np.zeros(len(pos))]))
        else:
            loops_of.append([[int(i) for i in loop] for loop in x["loops"]])
            flats.append(np.column_stack([pos, np.zeros(len(pos))]))
        if folds:                                      # the folds, moved like the piece
            A = np.column_stack([before[used], np.ones(len(used))])
            M = np.linalg.lstsq(A, pos[used], rcond=None)[0]
            folds = [np.column_stack([p, np.ones(2)]) @ M for p in folds]
        folds_of.append(folds)
    if what == 'stretch':
        values = np.array(stretched) if geometry.levels else np.asarray(stretched[0])
        return geometry.derived(values.reshape(geometry.values.shape[:-2]) if geometry.levels else values,
                                  name, None)
    is_net = any(x.get("net") for x in pieces)
    if what == 'folds':
        lines = [np.column_stack([p, np.zeros(2)]) for ps in folds_of for p in ps]
        if not lines:
            raise ShapeError(tr('There are no folds: they come from the net of a closed body (a box, a prism, a pyramid).'))
        return Data(np.stack(lines), ("fold",), name, kind=CURVE)
    if what == 'unrolled' and is_net:                  # the net: each face, a polygon with its corners
        lengths = [tuple(len(q) for q in x["polygons"]) for x in pieces]
        if len(set(lengths)) > 1:
            raise ShapeError(tr('The nets in a list must have the same faces (unroll them separately).'))
        from_ = np.cumsum((0,) + lengths[0])
        faces = tuple(tuple(range(a_, b_)) for a_, b_ in zip(from_[:-1], from_[1:]))
        values = np.stack([pl[:from_[-1]] for pl in flats])
        if not geometry.levels:
            return Data(values[0], (), name, kind=kind_mesh(faces))
        return geometry.derived(values.reshape(geometry.values.shape[:-2] + values.shape[-2:]), name,
                                  kind_mesh(faces))
    if what == 'unrolled':
        values = np.stack(flats).reshape(geometry.values.shape)
        faces = geometry.kind.faces
        if geometry.kind.grid is not None:           # the flattened grid is still a grid
            return geometry.derived(values, name, geometry.kind)
        return geometry.derived(values, name, kind_mesh(faces))
    # Outlines: each loop of each piece, a closed curve (the outer edge and those of the holes).
    curves = [flat[loop] for flat, loops in zip(flats, loops_of) for loop in loops]
    more = max(len(x) for x in curves)
    curves = [np.vstack([x, np.repeat(x[-1:], more - len(x), axis=0)]) for x in curves]
    return Data(np.stack(curves), ("border",), name, kind=CLOSED_CURVE)
