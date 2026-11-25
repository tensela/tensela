# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Which parts of the model's edges the view shows, fast, on a depth buffer.

An exact hidden-line pass takes minutes on a model of a few tens of
thousands of triangles. A sketch needs the
lines a hand would draw, not exact ones, so here the triangles are drawn
into a depth buffer at the drawing's resolution and every edge is walked
pixel by pixel: where nothing stands in front of it, it shows.

The same buffer tells the outlines: a line with the background, or a
surface well behind it, on one side is where a shape ends, and is drawn
heavier. A crease between two faces has the model at its own depth on both
sides.

All NumPy over the projection of the host's camera (its own
``projection_matrix() * view_matrix()``), so the lines land where the
viewport draws them, in perspective, two-point or parallel.
"""
from __future__ import annotations

import math

import numpy as np

#: The near plane, as a row a with the kept side a · clip ≥ 0 (OpenGL).
_NEAR = np.array([0.0, 0.0, 1.0, 1.0])
#: Something stands in front of an edge when it is nearer by more than this
#: share of the edge's own depth (an edge lies on its faces: equal depth).
_IN_FRONT = 0.004
#: A side is "well behind" (an outline) past this share of the depth.
_BEHIND = 0.03


def clip_matrix(camera) -> np.ndarray:
    m = camera.projection_matrix() * camera.view_matrix()
    return np.array(m.data(), dtype=np.float64).reshape(4, 4, order="F")


def to_clip(points: np.ndarray, M: np.ndarray) -> np.ndarray:
    return points @ M[:, :3].T + M[:, 3]


def _screen(c: np.ndarray, width: int, height: int, persp: bool):
    """Clip coordinates → (x, y) pixels and nearness q (bigger = nearer;
    affine across the screen, so it interpolates linearly in pixels)."""
    w = c[..., 3]
    x = (c[..., 0] / w * 0.5 + 0.5) * width
    y = (0.5 - c[..., 1] / w * 0.5) * height
    q = 1.0 / w if persp else -c[..., 2] / w
    return x, y, q


def _clip_triangles(C: np.ndarray):
    """Cut (T, 3, 4) clip-space triangles at the near plane: those wholly in
    front pass, those wholly behind go, and a crossing one becomes one or
    two triangles. Returns them and, for each, the triangle it came from."""
    d = C @ _NEAR
    inside = d >= 0
    keep = inside.all(axis=1)
    out = [C[keep]]
    src = [np.nonzero(keep)[0]]
    crossing = np.nonzero(~keep & inside.any(axis=1))[0]
    for tid, tri, dd, ins in zip(crossing, C[crossing], d[crossing], inside[crossing]):
        poly = []
        for i in range(3):
            j = (i + 1) % 3
            if ins[i]:
                poly.append(tri[i])
            if ins[i] != ins[j]:
                t = dd[i] / (dd[i] - dd[j])
                poly.append(tri[i] + t * (tri[j] - tri[i]))
        for k in range(1, len(poly) - 1):
            out.append(np.array([[poly[0], poly[k], poly[k + 1]]]))
            # The triangle it came from (``t`` above is the cut's share).
            src.append(np.array([tid]))
    return np.concatenate(out), np.concatenate(src).astype(np.int64)


def depth_buffer(tris: np.ndarray, M: np.ndarray, width: int, height: int,
                 persp: bool):
    """``(zbuf, index)``: the nearness q of the nearest surface at every
    pixel, (H, W), -inf where there is none (the background); and which of
    ``tris`` it is, -1 for the background."""
    zbuf = np.full((height, width), -np.inf, dtype=np.float64)
    index = np.full((height, width), -1, dtype=np.int64)
    if not len(tris):
        return zbuf, index
    C, src = _clip_triangles(to_clip(tris.reshape(-1, 3), M).reshape(-1, 3, 4))
    if not len(C):
        return zbuf, index
    X, Y, Q = _screen(C, width, height, persp)
    x0 = np.clip(np.floor(X.min(axis=1)).astype(np.int64), 0, width)
    x1 = np.clip(np.ceil(X.max(axis=1)).astype(np.int64) + 1, 0, width)
    y0 = np.clip(np.floor(Y.min(axis=1)).astype(np.int64), 0, height)
    y1 = np.clip(np.ceil(Y.max(axis=1)).astype(np.int64) + 1, 0, height)
    area = ((X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0])
            - (X[:, 2] - X[:, 0]) * (Y[:, 1] - Y[:, 0]))
    live = (x1 > x0) & (y1 > y0) & (np.abs(area) > 1e-12)
    # Small triangles, the most of a detailed model, all at once: every one
    # tested on the pixels of a square that holds its box.
    side = np.maximum(x1 - x0, y1 - y0)
    zf, xf = zbuf.reshape(-1), index.reshape(-1)
    done = ~live
    for S in (2, 4, 8, 16, 32):
        group = np.nonzero(live & ~done & (side <= S))[0]
        done[group] = True
        oy, ox = np.divmod(np.arange(S * S), S)
        step = max(1, 4_000_000 // (S * S))
        for k in range(0, len(group), step):
            g = group[k:k + step]
            px = x0[g, None] + ox[None, :]
            py = y0[g, None] + oy[None, :]
            cx, cy = px + 0.5, py + 0.5
            X0, X1, X2 = X[g, 0, None], X[g, 1, None], X[g, 2, None]
            Y0, Y1, Y2 = Y[g, 0, None], Y[g, 1, None], Y[g, 2, None]
            a = area[g, None]
            w0 = ((X1 - cx) * (Y2 - cy) - (X2 - cx) * (Y1 - cy)) / a
            w1 = ((X2 - cx) * (Y0 - cy) - (X0 - cx) * (Y2 - cy)) / a
            w2 = 1.0 - w0 - w1
            ok = ((w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
                  & (px < x1[g, None]) & (py < y1[g, None]))
            if not ok.any():
                continue
            q = (w0 * Q[g, 0, None] + w1 * Q[g, 1, None] + w2 * Q[g, 2, None])[ok]
            pix = (py * width + px)[ok]
            tri = np.broadcast_to(src[g, None], ok.shape)[ok]
            np.maximum.at(zf, pix, q)
            win = q >= zf[pix]
            xf[pix[win]] = tri[win]
    big = np.nonzero(~done)[0]
    if len(big):
        _fill_big(big, X, Y, Q, area, (x0, x1, y0, y1), src, zf, xf, width)
    return zbuf, index


#: The side of the tiles that remember the farthest depth already drawn in
#: them (to skip the rows of big triangles that are behind, see _fill_big).
_TILE = 16


def _fill_big(big: np.ndarray, X, Y, Q, area, box, src, zf, xf, width: int,
              budget: int = 4_000_000, rows_at_once: int = 100_000) -> None:
    """The big triangles into the buffer, row by row: in each row only the
    pixels the triangle covers (found from its three edges), not the whole
    square around it. A slab seen from above is a few triangles as big as
    the drawing, one over the other.

    They go from the nearest, about `rows_at_once` rows at a time (and
    `budget` pixels); before each batch, a coarse map of tiles keeps the
    farthest depth drawn in each, and a row whose nearest point is behind
    all the tiles it crosses is not drawn."""
    x0, x1, y0, y1 = box
    height = len(zf) // width
    big = big[np.argsort(-Q[big].max(axis=1), kind="stable")]
    heights = y1[big] - y0[big]
    ends = np.cumsum(heights)
    tiles_x = -(-width // _TILE)
    first = 0
    while first < len(big):
        last = max(first + 1, int(np.searchsorted(
            ends, (ends[first - 1] if first else 0) + rows_at_once, side="right")))
        tris, rows = big[first:last], heights[first:last]
        first = last
        t = np.repeat(tris, rows)
        py = y0[t] + (np.arange(len(t)) - np.repeat(np.cumsum(rows) - rows, rows))
        cy = py + 0.5
        X0, X1, X2 = X[t, 0], X[t, 1], X[t, 2]
        Y0, Y1, Y2 = Y[t, 0], Y[t, 1], Y[t, 2]
        a = area[t]
        # Along a row each weight is p + s·x: where all three are >= 0, and
        # the depth, which is p + s·x too.
        s0, s1 = (Y1 - Y2) / a, (Y2 - Y0) / a
        p0 = (X1 * (Y2 - cy) - X2 * (Y1 - cy)) / a
        p1 = (X2 * (Y0 - cy) - X0 * (Y2 - cy)) / a
        s2, p2 = -(s0 + s1), 1.0 - p0 - p1
        lo = np.full(len(t), -np.inf)
        hi = np.full(len(t), np.inf)
        with np.errstate(divide="ignore", invalid="ignore"):
            for s_, p_ in ((s0, p0), (s1, p1), (s2, p2)):
                edge = (-1e-6 - p_) / s_
                lo = np.where(s_ > 0, np.maximum(lo, edge), lo)
                hi = np.where(s_ < 0, np.minimum(hi, edge), hi)
                hi = np.where((s_ == 0) & (p_ < -1e-6), -np.inf, hi)
        qp = p0 * Q[t, 0] + p1 * Q[t, 1] + p2 * Q[t, 2]
        qs = s0 * Q[t, 0] + s1 * Q[t, 1] + s2 * Q[t, 2]
        lo = np.clip(np.nan_to_num(lo, nan=1e18), -1e18, 1e18)
        hi = np.clip(np.nan_to_num(hi, nan=-1e18), -1e18, 1e18)
        first_px = np.maximum(x0[t], np.ceil(lo - 0.5)).astype(np.int64)
        last_px = np.minimum(x1[t] - 1, np.floor(hi - 0.5)).astype(np.int64)
        keep = last_px >= first_px
        # Behind what is drawn: the nearest point of the row (an end, the
        # depth is straight along it) against the farthest of its tiles.
        if keep.any() and np.isfinite(zf).any():
            farthest = _farthest_by_tiles(zf, width, height, tiles_x)
            ty = (py // _TILE).astype(np.int64)
            nearest = np.maximum(qp + qs * (first_px + 0.5), qp + qs * (last_px + 0.5))
            k = np.nonzero(keep)[0]
            behind = nearest[k] < _range_min(farthest, ty[k], first_px[k] // _TILE,
                                             last_px[k] // _TILE)
            keep[k[behind]] = False
        k = np.nonzero(keep)[0]
        count = (last_px[k] - first_px[k] + 1)
        total = np.cumsum(count)
        start = 0
        while start < len(k):
            stop = max(start + 1, int(np.searchsorted(
                total, (total[start - 1] if start else 0) + budget, side="right")))
            n = count[start:stop]
            r = np.repeat(k[start:stop], n)
            px = first_px[r] + (np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n))
            q = qp[r] + qs[r] * (px + 0.5)
            pix = py[r] * width + px
            tri = src[t[r]]
            np.maximum.at(zf, pix, q)
            win = q >= zf[pix]
            xf[pix[win]] = tri[win]
            start = stop


def _farthest_by_tiles(zf: np.ndarray, width: int, height: int, tiles_x: int):
    """For each row of tiles, a table to ask the farthest depth drawn
    (the smallest q; -inf where something is still empty) in any run of
    tiles: level j holds the minimum of 2**j tiles from each one."""
    whole_y, whole_x = height // _TILE, width // _TILE
    tiles = np.full((-(-height // _TILE), tiles_x), -np.inf)  # the edges, cut: as if empty
    if whole_y and whole_x:
        z = zf.reshape(height, width)[:whole_y * _TILE, :whole_x * _TILE]
        tiles[:whole_y, :whole_x] = (z.reshape(whole_y, _TILE, whole_x * _TILE).min(axis=1)
                                     .reshape(whole_y, whole_x, _TILE).min(axis=2))
    levels = [tiles]
    while (1 << len(levels)) <= tiles_x:
        last, half = levels[-1], 1 << (len(levels) - 1)
        levels.append(np.minimum(last[:, :-half], last[:, half:]))
    return levels


def _range_min(levels, row: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The smallest value of the tiles a..b (both included) of each row."""
    n = b - a + 1
    j = np.floor(np.log2(np.maximum(n, 1))).astype(np.int64)
    out = np.empty(len(row))
    for level in np.unique(j):
        m = j == level
        table = levels[level]
        out[m] = np.minimum(table[row[m], a[m]], table[row[m], b[m] - (1 << level) + 1])
    return out


def _clip_segments(A: np.ndarray, B: np.ndarray):
    """Cut clip-space segments at the near plane."""
    gives, db = A @ _NEAR, B @ _NEAR
    keep = (gives >= 0) | (db >= 0)
    A, B, gives, db = A[keep], B[keep], gives[keep], db[keep]
    t = np.where(gives != db, gives / np.where(gives != db, gives - db, 1.0), 0.0)
    cut = A + t[:, None] * (B - A)
    A = np.where((gives < 0)[:, None], cut, A)
    B = np.where((db < 0)[:, None], cut, B)
    return A, B


def edges_of_view(geom, camera) -> np.ndarray:
    """World segments (E, 2, 3) to draw: every hard edge, and the soft ones
    where the surface turns away from the eye (its silhouette) or ends."""
    tris, hard, soft, soft_n = geom
    hard = np.asarray(hard, dtype=np.float64).reshape(-1, 2, 3)
    soft = np.asarray(soft, dtype=np.float64).reshape(-1, 2, 3)
    soft_n = np.asarray(soft_n, dtype=np.float64).reshape(-1, 2, 3)
    if not len(soft):
        return hard
    if camera.perspective:
        eye = camera.eye()
        v = soft.mean(axis=1) - np.array([eye.x(), eye.y(), eye.z()])
    else:
        f = camera.forward()
        v = np.broadcast_to(np.array([f.x(), f.y(), f.z()]), (len(soft), 3))
    fa = np.einsum("ij,ij->i", soft_n[:, 0], v)
    fb = np.einsum("ij,ij->i", soft_n[:, 1], v)
    turn = np.isnan(fb) | ((fa < 0.0) != (fb < 0.0))
    return np.concatenate([hard, soft[turn]])


def _runs(flags: np.ndarray, ids: np.ndarray):
    """Start and end indices (inclusive) of the True runs of ``flags``,
    never across a change of ``ids``."""
    f = flags.astype(np.int8)
    brk = np.r_[True, ids[1:] != ids[:-1]]
    starts = np.nonzero(flags & (brk | np.r_[True, f[:-1] == 0]))[0]
    endb = np.r_[ids[1:] != ids[:-1], True]
    ends = np.nonzero(flags & (endb | np.r_[f[1:] == 0, True]))[0]
    return starts, ends


#: Samples walked at once by :func:`visible_lines` (about 0.5 GB of arrays).
_BATCH = 4_000_000


def _clip_to_frame(ax, ay, bx, by, width: int, height: int, margin: float = 1.0):
    """Liang-Barsky against the frame (a pixel of margin): ``(t0, t1, keep)``,
    the part of each screen segment inside it and whether it has one."""
    t0 = np.zeros(len(ax))
    t1 = np.ones(len(ax))
    keep = np.ones(len(ax), dtype=bool)
    dx, dy = bx - ax, by - ay
    for p, q in ((-dx, ax + margin), (dx, width + margin - ax),
                 (-dy, ay + margin), (dy, height + margin - ay)):
        flat = p == 0
        keep &= ~(flat & (q < 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(flat, 0.0, q / np.where(flat, 1.0, p))
        t0 = np.where(p < 0, np.maximum(t0, r), t0)
        t1 = np.where(p > 0, np.minimum(t1, r), t1)
    return t0, t1, keep & (t0 <= t1)


def _visible_pieces(ax, ay, aq, bx, by, bq, n, far3, width, height, persp):
    """The visible pieces of a batch of screen segments sampled ``n`` times
    each: ``(segs (k, 4), mid (k, 3))``, the middle sample's x, y, q."""
    ids = np.repeat(np.arange(len(n)), n)
    first = np.repeat(np.cumsum(n) - n, n)
    t = (np.arange(len(ids)) - first) / np.repeat(n - 1, n)
    sx = ax[ids] + t * (bx - ax)[ids]
    sy = ay[ids] + t * (by - ay)[ids]
    sq = aq[ids] + t * (bq - aq)[ids]
    del first, t
    ix = np.floor(sx).astype(np.int64)
    iy = np.floor(sy).astype(np.int64)
    on = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
    if persp:
        on &= sq > 0
    np.clip(ix, 0, width - 1, out=ix)
    np.clip(iy, 0, height - 1, out=iy)
    behind = far3[iy, ix]
    del ix, iy
    visible = on & (sq + (_IN_FRONT * np.abs(sq) + 1e-12) >= behind)
    del behind
    # Close one- and two-sample gaps (a pixel the rasteriser gave to a
    # neighbour), then the runs are the visible pieces.
    s0, e0 = _runs(~visible & on, ids)
    N = len(ids)
    ok = (e0 - s0 < 2) & (s0 > 0) & (e0 + 1 < N)
    s0, e0 = s0[ok], e0[ok]
    ok = ((ids[s0 - 1] == ids[s0]) & (ids[e0 + 1] == ids[e0])
          & visible[s0 - 1] & visible[e0 + 1])
    visible[s0[ok]] = True
    visible[e0[ok]] = True
    starts, ends = _runs(visible, ids)
    keep = ends > starts
    starts, ends = starts[keep], ends[keep]
    segs = np.stack([sx[starts], sy[starts], sx[ends], sy[ends]], axis=1)
    mid = (starts + ends) // 2
    return segs, np.stack([sx[mid], sy[mid], sq[mid]], axis=1)


def visible_lines(geom, camera, width: int, height: int, step: float = 1.0,
                  zbuf=None):
    """The visible parts of the view's edges, as ``(segs, outline)``: segs
    (N, 4) in pixels (x0, y0, x1, y1), outline (N,) True where the model
    ends on one side of the line. ``zbuf``: :func:`depth_buffer`'s, when
    the caller has it already."""
    persp = bool(camera.perspective)
    M = clip_matrix(camera)
    if zbuf is None:
        tris = np.asarray(geom[0], dtype=np.float64).reshape(-1, 3, 3)
        zbuf, _index = depth_buffer(tris, M, width, height, persp)
    # The farthest surface in each pixel's 3×3: an occluder must cover the
    # whole neighbourhood to hide an edge (an edge's own pixels straddle
    # its faces).
    pad = np.pad(zbuf, 1, mode="constant", constant_values=-np.inf)
    far3 = np.full_like(zbuf, np.inf)
    for dy in range(3):
        for dx in range(3):
            np.minimum(far3, pad[dy:dy + height, dx:dx + width], out=far3)

    E = edges_of_view(geom, camera)
    if not len(E):
        return np.empty((0, 4)), np.zeros(0, dtype=bool)
    A, B = _clip_segments(to_clip(E[:, 0], M), to_clip(E[:, 1], M))
    ax, ay, aq = _screen(A, width, height, persp)
    bx, by, bq = _screen(B, width, height, persp)
    length = np.hypot(bx - ax, by - ay)
    # An end at infinity (on the eye's own plane) has no place: skip.
    sane = np.isfinite(length)
    ax, ay, aq, bx, by, bq = (v[sane] for v in (ax, ay, aq, bx, by, bq))
    # Only what falls in the frame is walked: an edge running off toward
    # the horizon, or cut at the near plane, can be thousands of times the
    # drawing's width (141 million samples on a 734 000-face model).
    t0, t1, inside = _clip_to_frame(ax, ay, bx, by, width, height)
    ax, ay, aq, bx, by, bq, t0, t1 = (v[inside] for v in (ax, ay, aq, bx, by, bq, t0, t1))
    dx, dy, dq = bx - ax, by - ay, bq - aq
    ax, ay, aq, bx, by, bq = (ax + t0 * dx, ay + t0 * dy, aq + t0 * dq,
                              ax + t1 * dx, ay + t1 * dy, aq + t1 * dq)
    length = np.hypot(bx - ax, by - ay)
    n = np.maximum(2, np.ceil(length / step).astype(np.int64) + 1)
    # In batches of whole edges, so the samples in memory stay bounded
    # whatever the model.
    ends_at = np.cumsum(n)
    parts = []
    lo = 0
    while lo < len(n):
        hi = int(np.searchsorted(ends_at, ends_at[lo] - n[lo] + _BATCH, side="right"))
        hi = max(hi, lo + 1)
        sl = slice(lo, hi)
        parts.append(_visible_pieces(ax[sl], ay[sl], aq[sl], bx[sl], by[sl], bq[sl],
                                     n[sl], far3, width, height, persp))
        lo = hi
    if not parts:
        return np.empty((0, 4)), np.zeros(0, dtype=bool)
    segs = np.concatenate([p[0] for p in parts])
    mx, my, mq = (np.concatenate([p[1][:, k] for p in parts]) for k in range(3))
    # Outline: test both sides a few pixels off the middle of each piece.
    dx, dy = segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]
    ln = np.hypot(dx, dy)
    ln[ln < 1e-9] = 1.0
    off = max(2.0, 3.0 * height / 1000.0)
    nx, ny = -dy / ln * off, dx / ln * off

    def side(sgn):
        x = np.clip((mx + sgn * nx).astype(np.int64), 0, width - 1)
        y = np.clip((my + sgn * ny).astype(np.int64), 0, height - 1)
        q = zbuf[y, x]
        return ~np.isfinite(q) | (q < mq - _BEHIND * np.abs(mq))

    outline = side(1.0) | side(-1.0)
    return segs, outline


def merge_collinear(segs: np.ndarray, outline: np.ndarray, tol: float,
                    max_angle_deg: float = 1.5):
    """Join pieces that continue each other in a straight line (a wall's
    edge split at every vertex along it) into one, so the hand draws it in
    one stroke. Only where exactly two pieces meet: where three meet, it is
    a corner. A joined line is an outline if most of its length was."""
    n = len(segs)
    if n < 2:
        return segs, outline
    P = segs.reshape(n * 2, 2)
    length = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    cos_max = math.cos(math.radians(max_angle_deg))
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Two grids, the second shifted half a cell, so two ends that fall on
    # either side of a cell border still meet in one of them.
    for shift in (0.0, 0.5):
        cells = np.floor(P / tol + shift).astype(np.int64)
        _u, node, count = np.unique(cells, axis=0, return_inverse=True,
                                    return_counts=True)
        node = node.reshape(-1)
        pairs = np.nonzero(count[node] == 2)[0]
        order = pairs[np.argsort(node[pairs], kind="stable")]
        e1, e2 = order[0::2], order[1::2]
        i, j = e1 // 2, e2 // 2
        di = P[e1] - P[e1 ^ 1]              # toward the meeting point
        dj = P[e2 ^ 1] - P[e2]              # and on, away from it
        li, lj = length[i], length[j]
        good = (i != j) & (li > 1e-9) & (lj > 1e-9)
        cos = np.einsum("ij,ij->i", di, dj) / np.where(good, li * lj, 1.0)
        good &= cos >= cos_max
        for a, b in zip(i[good].tolist(), j[good].tolist()):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
    roots = parent.copy()
    while True:                             # every piece straight to its root
        up = roots[roots]
        if np.array_equal(up, roots):
            break
        roots = up
    # Each joined line from its members, all at once (sorted by root), not
    # line by line over the whole list: that was quadratic, hours on a model
    # of hundreds of thousands of pieces.
    order = np.argsort(roots, kind="stable")
    r = roots[order]
    first = np.r_[0, np.nonzero(r[1:] != r[:-1])[0] + 1]
    group = np.repeat(np.arange(len(first)), np.diff(np.r_[first, n]))
    w = length[order]
    # The direction of each line is its longest member's.
    best = np.full(len(first), -1.0)
    np.maximum.at(best, group, w)
    is_best = w >= best[group]
    k = np.full(len(first), -1, dtype=np.int64)
    k[group[is_best][::-1]] = order[is_best][::-1]
    d = segs[k, 2:] - segs[k, :2]
    d = d / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-12)[:, None]
    pts = segs[order].reshape(-1, 2, 2)                 # (m, 2 ends, xy)
    t = np.einsum("mex,mx->me", pts, d[group])
    lo_t = np.full(len(first), np.inf)
    hi_t = np.full(len(first), -np.inf)
    np.minimum.at(lo_t, group, t.min(axis=1))
    np.maximum.at(hi_t, group, t.max(axis=1))
    # The end points that reach those extremes.
    flat_pts = pts.reshape(-1, 2)
    flat_t = t.reshape(-1)
    flat_g = np.repeat(group, 2)
    at_lo = np.zeros((len(first), 2))
    at_hi = np.zeros((len(first), 2))
    m_lo = flat_t <= lo_t[flat_g]
    m_hi = flat_t >= hi_t[flat_g]
    at_lo[flat_g[m_lo][::-1]] = flat_pts[m_lo][::-1]
    at_hi[flat_g[m_hi][::-1]] = flat_pts[m_hi][::-1]
    out_segs = np.concatenate([at_lo, at_hi], axis=1)
    lit = np.zeros(len(first))
    tot = np.zeros(len(first))
    np.add.at(lit, group, w * outline[order])
    np.add.at(tot, group, w)
    out_line = lit > 0.5 * tot
    # A line of one piece stays that piece, exactly.
    single = np.diff(np.r_[first, n]) == 1
    out_segs[single] = segs[order[first[single]]]
    out_line[single] = outline[order[first[single]]].astype(bool)
    return out_segs.reshape(-1, 4), out_line.astype(bool)
