"""Polygon meshes: built by their topology, their faces read and turned.

A mesh is a set of **vertices** (its geometry) and the **faces** that join them (its topology): each face, the list
of its vertices in order, three for a triangle and four for a quadrilateral. The order says which side is the front:
going round counterclockwise seen from the front. Two neighbouring faces are **compatible** when they go round the
shared edge in opposite directions (so both look the same way), and a mesh whose faces are all compatible is
**orientable**.

    mesh(points [vertex 4], "0 1 2; 2 1 3")     → a mesh of two triangles
    flip_faces(m, "1")                            → the same, with face 1 turned over
    mesh_faces(m, "normals")                      → [face 2] the normal of each face
    mesh_surface(dome, 16, 8)                     → the dome as one mesh of 16 × 8 quadrilaterals
    triangulate(m)                                → each quadrilateral split by its shorter diagonal
"""

from __future__ import annotations

import re
from collections import deque
from itertools import combinations

import numpy as np

from .data import Data, ShapeError
from .geometry import POINT, VECTOR, _require_geometry
from .language import tr
from .meshes import kind_mesh

#: What can be read from each face of a mesh.
FACE_READINGS = ('outlines', 'centres', 'normals', 'sides', 'orientation', 'flatness')


def read_faces(faces) -> list[tuple[int, ...]]:
    """The faces as written: «0 1 2; 2 1 3» (each face, its vertices; «;» between faces), a list of lists, or a data
    of numbers with a level of corners (face × corner)."""
    if isinstance(faces, Data):
        v = np.asarray(faces.values)
        if v.ndim == 1:
            v = v[None]
        rows = v.reshape(-1, v.shape[-1])
        return [tuple(int(round(x)) for x in row if np.isfinite(x)) for row in rows]
    if isinstance(faces, (list, tuple)):
        if faces and all(isinstance(x, (int, float, np.integer, np.floating)) for x in faces):
            return [tuple(int(round(x)) for x in faces)]                 # a single face: «0 1 2»
        return [tuple(int(round(x)) for x in face) for face in faces]
    text = str(faces or "").strip()
    if not text:
        raise ShapeError(tr('“faces” is missing: the vertices of each face, in order («0 1 2; 2 1 3»).'))
    out = []
    for part in text.split(";"):
        numbers = re.findall(r"-?\d+", part)
        if numbers:
            out.append(tuple(int(n) for n in numbers))
    return out


def _check_faces(faces: list[tuple[int, ...]], count: int) -> None:
    if not faces:
        raise ShapeError(tr('“faces” is missing: the vertices of each face, in order («0 1 2; 2 1 3»).'))
    for i, face in enumerate(faces):
        if len(face) < 3:
            raise ShapeError(tr('Face {face} has {n} vertices: a face needs at least 3.').format(face=i, n=len(face)))
        if len(set(face)) != len(face):
            raise ShapeError(tr('Face {face} repeats a vertex ({vertices}).').format(
                face=i, vertices=" ".join(map(str, face))))
        bad = [v for v in face if v < 0 or v >= count]
        if bad:
            raise ShapeError(tr('Face {face} uses vertex {vertex}, but there are only {count} (from 0 to {last}).').format(
                face=i, vertex=bad[0], count=count, last=count - 1))


def mesh(points: Data, faces, along: str | None = None, name: str | None = None) -> Data:
    """A mesh from its vertices and its faces (*Construct Mesh*). The vertices are the points of a level (the last
    one, unless another is said); with other levels, one mesh for each, all with the same faces."""
    if not isinstance(points, Data) or points.kind is not POINT or not points.levels:
        raise ShapeError(tr('“points” must be several points: the vertices of the mesh, in order.'))
    along = along or points.levels[-1]
    if along not in points.levels:
        raise ShapeError(tr('“{along}” is not a level of “{name}” (its levels: {options}).').format(
            along=tr(along), name=points._name(), options=", ".join(tr(n) for n in points.levels)))
    if along in points.variables or any(along in c.levels for c in points.variables.values()):
        raise ShapeError(tr('The number of vertices changes in “{name}”: not possible yet.').format(name=points._name()))
    axis = points.levels.index(along)
    values = np.moveaxis(np.asarray(points.values, dtype=float), axis, -2)       # (…, vertex, 3)
    face_list = read_faces(faces)
    _check_faces(face_list, values.shape[-2])
    levels = tuple(n for n in points.levels if n != along)
    starts = {k: v for k, v in points.starts.items() if k != along}
    holes = None if points.holes is None else np.moveaxis(points.holes, axis, -1).any(axis=-1)
    return Data(values, levels, name, {k: c for k, c in points.variables.items() if k != along}, starts,
                kind_mesh(face_list), holes)


def _faces_of(geometry: Data) -> tuple[tuple[int, ...], ...]:
    _require_geometry(geometry)
    faces = geometry.kind.faces
    if not faces or geometry.kind.curve:
        raise ShapeError(tr('“{name}” has no faces (it is {kind}): a mesh, a box or a surface is needed.').format(
            name=geometry._name(), kind=tr(geometry.kind.name)))
    return faces


def flip_faces(geometry: Data, which=None, name: str | None = None) -> Data:
    """The same mesh with its faces turned over (*Mesh Flip*): all of them, or only those listed («1» · «0 3»)."""
    faces = _faces_of(geometry)
    chosen = set(range(len(faces))) if which in (None, "") else {
        i for face in read_faces(which) for i in face} if not isinstance(which, (int, float)) else {int(which)}
    bad = [i for i in chosen if i < 0 or i >= len(faces)]
    if bad:
        raise ShapeError(tr('There is no face {face}: the mesh has {count} (from 0 to {last}).').format(
            face=bad[0], count=len(faces), last=len(faces) - 1))
    new = [tuple(reversed(f)) if i in chosen else tuple(f) for i, f in enumerate(faces)]
    return Data(geometry.values, geometry.levels, name, geometry.variables, geometry.starts, kind_mesh(new),
                geometry.holes)


def orientation(faces) -> np.ndarray:
    """+1 or −1 for each face: whether it looks the same way as the first face of its piece, going from face to face
    across the shared edges. A piece where every neighbour is compatible gives all +1 (orientable)."""
    n = len(faces)
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for i, f in enumerate(faces):
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            edges.setdefault((min(a, b), max(a, b)), []).append((i, 1 if a < b else -1))
    neighbours: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for users in edges.values():
        for x in range(len(users)):
            for y in range(x + 1, len(users)):
                (i, si), (j, sj) = users[x], users[y]
                same = si != sj                           # opposite directions on the edge: compatible
                neighbours[i].append((j, 1 if same else -1))
                neighbours[j].append((i, 1 if same else -1))
    sign = np.zeros(n)
    for start in range(n):
        if sign[start]:
            continue
        sign[start] = 1
        queue = deque([start])
        while queue:
            i = queue.popleft()
            for j, relation in neighbours[i]:
                if not sign[j]:
                    sign[j] = sign[i] * relation
                    queue.append(j)
    return sign


def mesh_faces(geometry: Data, what: str = 'normals', level: str = "face", name: str | None = None) -> Data:
    """Something of each face (a new level, «face»): its **outline** (a closed polygon), its **centre**, its
    **normal** (where it looks: length 1), its number of **sides**, its **orientation** (+1 if it looks like the
    first face of its piece, −1 if it is turned over: a mesh with any −1 is not orientable), or its **flatness**
    (how far its corners are from the plane that fits them best, in metres: 0 in a flat face, always in a
    triangle)."""
    faces = _faces_of(geometry)
    if what not in FACE_READINGS:
        raise ShapeError(tr('What can be read from the faces: {options}.').format(
            options=", ".join(tr(w) for w in FACE_READINGS)))
    if level in geometry.levels:
        raise ShapeError(tr('The new level needs a name that “{name}” does not use (it has: {options}).').format(
            name=geometry._name(), options=", ".join(tr(n) for n in geometry.levels)))
    v = np.asarray(geometry.values, dtype=float)                          # (…, vertex, 3)
    sides = max(len(f) for f in faces)
    index = np.array([list(f) + [f[-1]] * (sides - len(f)) for f in faces])  # padded with the last vertex
    corners = v[..., index, :]                                             # (…, face, sides, 3)
    if what == 'sides':
        out = np.broadcast_to(np.array([len(f) for f in faces], float), v.shape[:-2] + (len(faces),)).copy()
        return geometry.derived(out, name, None, (level,))
    if what == 'orientation':
        out = np.broadcast_to(orientation(faces), v.shape[:-2] + (len(faces),)).copy()
        return geometry.derived(out, name, None, (level,))
    if what == 'flatness':
        out = _flatness(corners, faces)
        return geometry.derived(out, name, None, (level,))
    if what == 'outlines':
        from .polygons import kind_polygon
        return geometry.derived(corners, name, kind_polygon(sides), (level,))
    real = np.array([[1.0] * len(f) + [0.0] * (sides - len(f)) for f in faces])[..., None]
    centres = (corners * real).sum(-2) / real.sum(-2)
    if what == 'centres':
        return geometry.derived(centres, name, POINT, (level,))
    n = np.cross(corners, np.roll(corners, -1, axis=-2)).sum(-2)          # Newell: also for a quad that is not flat
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    return geometry.derived(np.divide(n, length, out=np.zeros_like(n), where=length > 1e-12), name, VECTOR, (level,))


def _flatness(corners: np.ndarray, faces) -> np.ndarray:
    """For each face, the largest distance from one of its corners to the plane that fits them best (metres)."""
    sizes = np.array([len(f) for f in faces])
    out = np.zeros(corners.shape[:-2])
    for k in np.unique(sizes):
        if k <= 3:
            continue                                     # three points are always on a plane
        which = np.nonzero(sizes == k)[0]
        c = corners[..., which, :k, :]                   # (…, faces of k sides, k, 3)
        centred = c - c.mean(axis=-2, keepdims=True)
        _, _, vt = np.linalg.svd(centred, full_matrices=False)   # the normal: the direction of least spread
        normal = vt[..., -1, :]
        out[..., which] = np.abs(np.einsum("...kd,...d->...k", centred, normal)).max(axis=-1)
    out[out < 1e-6] = 0.0                                # below a thousandth of a millimetre: flat (not number noise)
    return out


def mesh_surface(surface: Data, count_u=10, count_v=10, name: str | None = None) -> Data:
    """A surface (or a rectangle) as one mesh of count_u × count_v quadrilaterals (*Mesh Surface*, *Mesh UV*): the
    vertices are shared by the neighbouring faces; on a surface that goes round (a revolution, a tube) the seam is
    closed too. The faces follow the surface: u across, v up."""
    from .data import integer
    from .geometry import RECTANGLE, _evaluator
    if not isinstance(surface, Data) or surface.kind is None or (surface.kind.grid is None
                                                                 and surface.kind is not RECTANGLE):
        raise ShapeError(tr('“surface” must be a surface or a rectangle.'))
    nu, nv = integer(count_u), integer(count_v)
    if nu < 1 or nv < 1:
        raise ShapeError(tr('At least 1 face is needed in each direction.'))
    closed_u = closed_v = False
    if surface.kind.grid is not None:
        from .geometry import _grid
        from .surfaces import _closed_in
        r = _grid(surface)
        closed_v, closed_u = _closed_in(r, 0), _closed_in(r, 1)
    su = np.linspace(0, 1, nu + 1)[:nu] if closed_u else np.linspace(0, 1, nu + 1)
    sv = np.linspace(0, 1, nv + 1)[:nv] if closed_v else np.linspace(0, 1, nv + 1)
    cu, cv = len(su), len(sv)
    tt, ss = np.meshgrid(sv, su, indexing="ij")          # rows (v) × columns (u)
    points = _evaluator(surface)(ss.ravel(), tt.ravel())  # (…, cv·cu, 3)
    # A first or last row that closes into a point (the bottom of a vase, the top of a dome): one vertex, with
    # triangles around it, so the mesh is closed there too.
    grid_points = points.reshape(points.shape[:-2] + (cv, cu, 3))
    size = float(np.nanmax(np.ptp(points.reshape(-1, 3), axis=0))) or 1.0
    poles = set()
    if not closed_v:
        for row in (0, cv - 1):
            spread = np.nanmax(np.linalg.norm(grid_points[..., row, :, :] - grid_points[..., row, :1, :], axis=-1))
            if cu > 1 and spread <= size * 1e-7:
                poles.add(row)
    ids = np.arange(cv * cu).reshape(cv, cu)
    for row in poles:
        ids[row, :] = ids[row, 0]
    keep = np.unique(ids)
    renumber = np.zeros(cv * cu, dtype=np.int64)
    renumber[keep] = np.arange(len(keep))
    i, j = np.meshgrid(np.arange(nv), np.arange(nu), indexing="ij")
    quads = np.stack([ids[i, j], ids[i, (j + 1) % cu], ids[(i + 1) % cv, (j + 1) % cu], ids[(i + 1) % cv, j]],
                     axis=-1).reshape(-1, 4)
    quads = renumber[quads]
    whole = (quads != np.roll(quads, 1, axis=1)).all(axis=1)
    faces = [tuple(q) for q in quads[whole].tolist()] if whole.all() else []
    if not whole.all():                              # by a pole: the quadrilateral, a triangle (in order)
        for q, ok in zip(quads.tolist(), whole):
            face = q if ok else [v for k, v in enumerate(q) if v != q[k - 1]]
            if len(face) >= 3:
                faces.append(tuple(face))
    points = points[..., keep, :]
    return Data(points, surface.levels, name, surface.variables, surface.starts, kind_mesh(faces), surface.holes)


#: How a quadrilateral is split into two triangles.
DIAGONALS = ('shorter', 'first', 'second')


def triangulate(geometry: Data, diagonal: str = 'shorter', name: str | None = None) -> Data:
    """Every face as triangles: a quadrilateral by one of its diagonals (the shorter one, or always the first, 0-2,
    or the second, 1-3); a face of more sides, from its first vertex. Triangles are always flat."""
    faces = _faces_of(geometry)
    if diagonal not in DIAGONALS:
        raise ShapeError(tr('The diagonal can be: {options}.').format(options=", ".join(tr(d) for d in DIAGONALS)))
    v = np.asarray(geometry.values, dtype=float).reshape(-1, geometry.values.shape[-2], 3).mean(axis=0)
    out = []
    for f in faces:
        if len(f) == 4:
            a, b, c, d = f
            first = np.linalg.norm(v[a] - v[c]) <= np.linalg.norm(v[b] - v[d])
            if diagonal == 'first' or (diagonal == 'shorter' and first):
                out += [(a, b, c), (a, c, d)]
            else:
                out += [(a, b, d), (b, c, d)]
        else:
            out += [(f[0], f[k], f[k + 1]) for k in range(1, len(f) - 1)]
    return Data(geometry.values, geometry.levels, name, geometry.variables, geometry.starts, kind_mesh(out),
                geometry.holes)


def _polygons(data: Data) -> tuple[np.ndarray, list[tuple[int, ...]]]:
    """All the faces of every element of a geometry, as one list: (vertices (n, 3), faces with those indices)."""
    faces = _faces_of(data)
    v = np.asarray(data.values, dtype=float)
    per = v.shape[-2]
    elements = v[data.mask] if data.levels else v[None]
    out_faces = []
    for k in range(len(elements)):
        out_faces += [tuple(i + k * per for i in f) for f in faces]
    return elements.reshape(-1, 3), out_faces


def _clean_face(face) -> tuple[int, ...]:
    """Without a vertex repeated next to itself (welded, or the padding of a polygon: the same index)."""
    out = [i for k, i in enumerate(face) if k == 0 or i != face[k - 1]]
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return tuple(out)


#: What Join meshes does with the faces that lie on top of another one (two boxes side by side share a wall).
DOUBLED_FACES = ('leave', 'remove')


def join_meshes(parts, weld: bool = True, tolerance: float = 0.001, name: str | None = None,
                doubled: str = 'leave') -> Data:
    """Everything with faces (meshes, boxes, panels, surfaces…), with all its elements, as **one mesh** (*Mesh Join*).
    With `weld`, the vertices closer than `tolerance` (metres) become one (*Weld*): the neighbouring faces share them,
    and the mesh is a single piece (what a subdivision needs to smooth it as a whole).

    `doubled` «remove»: a face with the same corners as another one (the wall between two boxes side by side, one from
    each box) goes, both of them: of a group of boxes only the outer skin is left, closed, as one volume."""
    if doubled not in DOUBLED_FACES:
        raise ShapeError(tr('Doubled faces can be: {options}.').format(
            options=", ".join(tr(d) for d in DOUBLED_FACES)))
    points, faces = [], []
    offset = 0
    for part in parts:
        if part is None:
            continue
        p, f = _polygons(part)
        points.append(p)
        faces += [tuple(i + offset for i in face) for face in f]
        offset += len(p)
    if not points:
        raise ShapeError(tr('Nothing to join: connect meshes or geometry with faces.'))
    p = np.vstack(points)
    tol = float(tolerance)
    if (weld or doubled == 'remove') and tol <= 0:
        raise ShapeError(tr('The welding tolerance must be more than 0.'))
    if doubled == 'remove':
        # Two faces lie on top of each other when their corners are the same points (within the tolerance).
        keys = np.round(p / tol).astype(np.int64)
        _, place = np.unique(keys, axis=0, return_inverse=True)
        place = place.ravel()
        corners = [frozenset(int(place[i]) for i in f) for f in faces]
        times: dict = {}
        for c in corners:
            times[c] = times.get(c, 0) + 1
        faces = [f for f, c in zip(faces, corners) if times[c] == 1]
        if not faces:
            raise ShapeError(tr('Every face lies on top of another one: nothing is left after removing the doubled '
                                'faces.'))
    if weld:
        keys = np.round(p / tol).astype(np.int64)
        _, first, remap = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        remap = remap.ravel()
        p = p[first]
        faces = [tuple(int(remap[i]) for i in f) for f in faces]
    cleaned = [c for c in (_clean_face(f) for f in faces) if len(c) >= 3]
    if not cleaned:
        raise ShapeError(tr('After welding no face is left: is the tolerance larger than the faces?'))
    used = sorted({i for f in cleaned for i in f})                     # without vertices that no face uses
    renumber = {old: new for new, old in enumerate(used)}
    return Data(p[used], (), name, kind=kind_mesh([tuple(renumber[i] for i in f) for f in cleaned]))


#: Which edges of a mesh are drawn.
EDGE_KINDS = ('naked', 'inner', 'all')


def mesh_edges(geometry: Data, which: str = 'naked', level: str = "edge", name: str | None = None) -> Data:
    """The edges of a mesh as lines: the **naked** ones (used by a single face: the border, or a seam that did not
    weld, as next to a T-node), the **inner** ones (shared by two faces or more), or **all**."""
    from .geometry import CURVE
    faces = _faces_of(geometry)
    if which not in EDGE_KINDS:
        raise ShapeError(tr('The edges can be: {options}.').format(options=", ".join(tr(w) for w in EDGE_KINDS)))
    use: dict[tuple[int, int], int] = {}
    order: list[tuple[int, int]] = []
    for f in faces:
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            if a == b:
                continue
            key = (min(a, b), max(a, b))
            if key not in use:
                order.append(key)
            use[key] = use.get(key, 0) + 1
    chosen = [e for e in order if which == 'all' or (use[e] == 1) == (which == 'naked')]
    if not chosen:
        raise ShapeError(tr('“{name}” has no {which} edges.').format(name=geometry._name(), which=tr(which)))
    index = np.array(chosen)
    v = np.asarray(geometry.values, dtype=float)
    return geometry.derived(v[..., index, :], name, CURVE, (level,))


# --- Smoothing by subdivision (Catmull and Clark, 1978; Loop, 1987) ---------------------------------------------------

#: The ways to smooth a mesh, and what is done with its border.
SMOOTHING = ('Catmull-Clark', 'Loop')
BORDERS = ('smooth', 'fixed', 'corners fixed')
#: More faces than these are not made (the view and the memory would suffer): the levels stop before.
MAX_SMOOTH_FACES = 400_000


class _Halfedges:
    """The topology of a mesh read once: every corner of every face as a half edge «from → to», its face, its edge
    (shared by the two faces that use it) and how many faces use each edge."""

    def __init__(self, faces: list[tuple[int, ...]], count: int):
        sizes = np.array([len(f) for f in faces])
        self.face = np.repeat(np.arange(len(faces)), sizes)
        self.start = np.concatenate([[0], np.cumsum(sizes)[:-1]])
        self.v_from = np.concatenate([np.asarray(f) for f in faces])
        position = np.arange(len(self.v_from)) - self.start[self.face]
        nxt = self.start[self.face] + (position + 1) % sizes[self.face]
        prv = self.start[self.face] + (position - 1) % sizes[self.face]
        self.next, self.prev = nxt, prv
        self.v_to = self.v_from[nxt]
        pairs = np.sort(np.stack([self.v_from, self.v_to], axis=1), axis=1)
        self.edges, self.edge = np.unique(pairs, axis=0, return_inverse=True)
        self.edge = self.edge.ravel()
        self.uses = np.bincount(self.edge, minlength=len(self.edges))
        self.sizes, self.faces_count, self.count = sizes, len(faces), count
        self.border_edge = self.uses != 2                      # a border (or an edge of more than two faces)
        self.border_vertex = np.zeros(count, bool)
        self.border_vertex[self.edges[self.border_edge].ravel()] = True
        # how many faces meet at each vertex (a corner of the border has a single one)
        self.faces_at = np.bincount(self.v_from, minlength=count)


def _accumulate(n: int, index: np.ndarray, values: np.ndarray) -> np.ndarray:
    out = np.zeros((n,) + values.shape[1:])
    np.add.at(out, index, values)
    return out


def _border_vertices(h: _Halfedges, P: np.ndarray, new: np.ndarray, border: str) -> None:
    """The vertices on the border: «smooth», like a curve (3/4 of itself and 1/8 of each neighbour on the border);
    «fixed», where they were; «corners fixed», smooth but the corners (a single face) stay."""
    b = np.nonzero(h.border_vertex)[0]
    if not len(b):
        return
    if border == 'fixed':
        new[b] = P[b]
        return
    be = h.edges[h.border_edge]
    neighbours = _accumulate(h.count, be[:, 0], P[be[:, 1]]) + _accumulate(h.count, be[:, 1], P[be[:, 0]])
    degree = np.bincount(be.ravel(), minlength=h.count)
    smooth = b[degree[b] == 2]                                 # an ordinary border vertex: two neighbours on it
    new[smooth] = 0.75 * P[smooth] + 0.125 * neighbours[smooth]
    odd = b[degree[b] != 2]                                    # where several borders meet: it stays
    new[odd] = P[odd]
    if border == 'corners fixed':
        # a corner: where the border turns (more than 30° between its two border edges), or a single face
        first = P.reshape(P.shape[0], -1, 3)[:, 0, :]          # (the same topology for every element: the first)
        ends = {}
        for a, c in be:
            ends.setdefault(a, []).append(c)
            ends.setdefault(c, []).append(a)
        corners = [int(v) for v in smooth
                   if _turn(first[ends[v][0]], first[v], first[ends[v][1]]) > np.radians(30)]
        corners += [int(v) for v in b[h.faces_at[b] == 1]]
        if corners:
            new[corners] = P[corners]


def _turn(a: np.ndarray, p: np.ndarray, b: np.ndarray) -> float:
    """How much a path a → p → b turns at p (radians: 0, straight on)."""
    u, w = p - a, b - p
    nu, nw = np.linalg.norm(u), np.linalg.norm(w)
    if nu < 1e-12 or nw < 1e-12:
        return 0.0
    return float(np.arccos(np.clip(np.dot(u, w) / (nu * nw), -1.0, 1.0)))


def _catmull_clark(faces, P: np.ndarray, border: str):
    """One level: each face becomes as many quadrilaterals as it has sides."""
    nv = P.shape[0]
    h = _Halfedges(faces, nv)
    face_pts = _accumulate(h.faces_count, h.face, P[h.v_from]) / h.sizes.reshape((-1,) + (1,) * (P.ndim - 1))
    ne = len(h.edges)
    mid = (P[h.edges[:, 0]] + P[h.edges[:, 1]]) / 2
    around = _accumulate(ne, h.edge, face_pts[h.face])        # the faces on each side of each edge
    edge_pts = mid.copy()
    inner = ~h.border_edge
    edge_pts[inner] = (P[h.edges[inner, 0]] + P[h.edges[inner, 1]] + around[inner]) / 4
    # vertices: (Q + 2R + (n − 3) P) / n, Q the average of the faces around, R that of the edge midpoints
    n = np.bincount(h.v_from, minlength=nv).astype(float)    # faces around each vertex (= edges, inside)
    Q = _accumulate(nv, h.v_from, face_pts[h.face])
    edges_at = np.bincount(h.edges.ravel(), minlength=nv).astype(float)
    R = _accumulate(nv, h.edges[:, 0], mid) + _accumulate(nv, h.edges[:, 1], mid)
    shape = (-1,) + (1,) * (P.ndim - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        Qm = Q / np.maximum(n, 1).reshape(shape)
        Rm = R / np.maximum(edges_at, 1).reshape(shape)
        nn = np.maximum(n, 1).reshape(shape)
        vert = (Qm + 2 * Rm + (nn - 3) * P) / nn
    _border_vertices(h, P, vert, border)
    new_P = np.concatenate([vert, edge_pts, face_pts], axis=0)
    quads = np.stack([h.v_from, nv + h.edge, nv + ne + h.face, nv + h.edge[h.prev]], axis=1)
    return [tuple(q) for q in quads.tolist()], new_P


def _loop(faces, P: np.ndarray, border: str):
    """One level: each triangle becomes four."""
    nv = P.shape[0]
    h = _Halfedges(faces, nv)
    if np.any(h.sizes != 3):
        raise ShapeError(tr('Loop smooths triangles only: use Triangulate first, or Catmull-Clark.'))
    ne = len(h.edges)
    opposite = P[h.v_from[h.prev]]                             # the third vertex of the triangle of each half edge
    edge_pts = (P[h.edges[:, 0]] + P[h.edges[:, 1]]) / 2
    inner = ~h.border_edge
    opp = _accumulate(ne, h.edge, opposite)
    edge_pts[inner] = 0.375 * (P[h.edges[inner, 0]] + P[h.edges[inner, 1]]) + 0.125 * opp[inner]
    neighbours = _accumulate(nv, h.edges[:, 0], P[h.edges[:, 1]]) + _accumulate(nv, h.edges[:, 1], P[h.edges[:, 0]])
    k = np.bincount(h.edges.ravel(), minlength=nv).astype(float)
    kk = np.maximum(k, 1)
    beta = (0.625 - (0.375 + 0.25 * np.cos(2 * np.pi / kk)) ** 2) / kk
    shape = (-1,) + (1,) * (P.ndim - 1)
    vert = (1 - kk * beta).reshape(shape) * P + beta.reshape(shape) * neighbours
    _border_vertices(h, P, vert, border)
    new_P = np.concatenate([vert, edge_pts], axis=0)
    a, b, c = h.v_from[h.start], h.v_from[h.start + 1], h.v_from[h.start + 2]
    e_ab, e_bc, e_ca = nv + h.edge[h.start], nv + h.edge[h.start + 1], nv + h.edge[h.start + 2]
    tris = np.concatenate([np.stack([a, e_ab, e_ca], 1), np.stack([e_ab, b, e_bc], 1),
                           np.stack([e_ca, e_bc, c], 1), np.stack([e_ab, e_bc, e_ca], 1)])
    return [tuple(t) for t in tris.tolist()], new_P


def editable_mesh(geometry) -> Data:
    """The mesh that Edit mesh works on: anything with faces as one welded mesh, its vertices numbered from 0 (always
    the same numbers for the same input)."""
    if not isinstance(geometry, Data) or geometry.kind is None or geometry.kind is POINT:
        raise ShapeError(tr('“mesh” must be a mesh or something with faces (boxes, panels, a joined skin).'))
    return join_meshes([geometry])


def edit_mesh(geometry: Data, moves=(), name: str | None = None) -> Data:
    """The mesh with some of its vertices moved by hand (*the cage of a subdivision*): `moves` is a list of
    [vertex, dx, dy, dz], how much each moved vertex goes in metres. Only the moves are kept, so the edits follow
    the mesh that comes in when it changes (as long as its vertices keep their numbers). A vertex number the mesh
    does not have is left aside."""
    mesh = editable_mesh(geometry)
    p = np.array(mesh.values, dtype=float)
    for row in moves or ():
        try:
            i, delta = int(row[0]), np.asarray(row[1:4], dtype=float)
        except (TypeError, ValueError, IndexError):
            raise ShapeError(tr('Each move is a vertex and how much it goes: [vertex, dx, dy, dz].')) from None
        if delta.shape == (3,) and 0 <= i < len(p):
            p[i] += delta
    return Data(p, (), name, kind=mesh.kind)


def smooth_mesh(geometry: Data, method: str = 'Catmull-Clark', levels=2, border: str = 'smooth',
                name: str | None = None) -> Data:
    """A smoother mesh by subdivision: each level splits every face and moves the vertices towards the smooth
    surface the mesh stands for (the limit surface). **Catmull-Clark** works on any faces (each face becomes
    quadrilaterals); **Loop**, on triangles (each one becomes four). The **border**: smooth (it tends to a curve),
    fixed (it stays where it is) or with its corners fixed. For a shape made of several parts, join and weld them
    first (Join meshes): if not, each part is smoothed on its own."""
    from .data import integer
    faces = list(_faces_of(geometry))
    if method not in SMOOTHING:
        raise ShapeError(tr('The method can be: {options}.').format(options=", ".join(SMOOTHING)))
    if border not in BORDERS:
        raise ShapeError(tr('The border can be: {options}.').format(options=", ".join(tr(b) for b in BORDERS)))
    n = integer(levels)
    if n < 0 or n > 5:
        raise ShapeError(tr('The levels go from 0 to 5 (each one multiplies the faces by about 4).'))
    v = np.asarray(geometry.values, dtype=float)
    P = np.moveaxis(v, -2, 0)                                  # (vertex, …, 3): the same steps for every element
    step = _catmull_clark if method == 'Catmull-Clark' else _loop
    for _ in range(n):
        growth = sum(len(f) for f in faces) if method == 'Catmull-Clark' else 4 * len(faces)
        if growth > MAX_SMOOTH_FACES:
            raise ShapeError(tr('So many levels would make {n} faces: fewer levels, or a lighter mesh.').format(
                n=f"{growth:,}".replace(",", " ")))
        faces, P = step(faces, P, border)
    return Data(np.moveaxis(P, 0, -2), geometry.levels, name, geometry.variables, geometry.starts, kind_mesh(faces),
                geometry.holes)


# --- Delaunay triangulation ------------------------------------------------------------------------------------------

#: On which plane a group of points is triangulated.
DELAUNAY_PLANES = ('best fit', 'plan')


def _delaunay_few(xy: np.ndarray) -> list[tuple[int, int, int]]:
    """The Delaunay triangles of three or four points (the pyramid on a triangle: its three corners and its centre),
    without the general method: with many small groups it is much faster."""
    def twice_area(a, b, c):
        return (xy[b, 0] - xy[a, 0]) * (xy[c, 1] - xy[a, 1]) - (xy[b, 1] - xy[a, 1]) * (xy[c, 0] - xy[a, 0])

    size = float(np.ptp(xy, axis=0).max()) if len(xy) else 0.0
    tiny = 1e-12 * (size * size or 1.0)
    if len(xy) < 3:
        return []
    if len(xy) == 3:
        return [(0, 1, 2)] if abs(twice_area(0, 1, 2)) > tiny else []
    for inner in range(4):                             # one point inside the triangle of the others: a fan around it
        a, b, c = (i for i in range(4) if i != inner)
        sides = [twice_area(a, b, inner), twice_area(b, c, inner), twice_area(c, a, inner)]
        if all(x > tiny for x in sides) or all(x < -tiny for x in sides):
            return [t for t in ((a, b, inner), (b, c, inner), (c, a, inner)) if abs(twice_area(*t)) > tiny]
    centre = xy.mean(axis=0)                           # four corners of a convex quadrilateral, in order
    order = sorted(range(4), key=lambda i: np.arctan2(xy[i, 1] - centre[1], xy[i, 0] - centre[0]))
    p, q, r, t = order
    m = np.array([[*(xy[i] - xy[t]), float((xy[i] - xy[t]) @ (xy[i] - xy[t]))] for i in (p, q, r)])
    split = (p, r) if np.linalg.det(m) <= 0 else (q, t)  # t outside the circle through p, q, r: the diagonal p–r
    if split == (p, r):
        found = [(p, q, r), (p, r, t)]
    else:
        found = [(q, r, t), (q, t, p)]
    return [x for x in found if abs(twice_area(*x)) > tiny]


def _delaunay_2d(xy: np.ndarray) -> np.ndarray | list[tuple[int, int, int]]:
    """The Delaunay triangles of some points on a plane (x, y): no point falls inside the circle through the three
    corners of a triangle, so they come out as even as possible (few thin triangles)."""
    if len(xy) <= 4:                                   # a triangle, or a pyramid on one: directly
        return _delaunay_few(np.asarray(xy, dtype=float))
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    xy = np.asarray(xy, dtype=float)
    order = vtk.nearby_order(xy)
    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(np.column_stack([xy[order], np.zeros(len(xy))]), deep=True))
    poly = vtk.vtkPolyData()
    poly.SetPoints(pts)
    d = vtk.vtkDelaunay2D()
    d.SetInputData(poly)
    d.SetOffset(1000.0)          # a larger enclosing triangle: with a smaller one, thin triangles on the outline
                                 # were lost (30 of 100 000 with 25 times its size, 3 with 1000)
    d.Update()
    cells = d.GetOutput().GetPolys()
    if cells.GetNumberOfCells() == 0:
        return []
    raw = order[vtk_to_numpy(cells.GetConnectivityArray()).reshape(-1, 3)]       # back to the points' own order
    a, b, c = xy[raw[:, 0]], xy[raw[:, 1]], xy[raw[:, 2]]
    area = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    size = float(np.ptp(xy, axis=0).max()) or 1.0
    return raw[area > 1e-12 * size * size].astype(np.int64)                         # without flat ones


#: Groups of up to this many points (a pyramid on a panel: its corners and its centre) are triangulated all at once,
#: with numpy, instead of one call to VTK each: 253 pyramids went from 0.2 s to a few milliseconds.
SMALL_GROUP = 8


def _delaunay_small(q: np.ndarray):
    """The Delaunay triangles of many small groups of points on their planes, all at once: q (G, n, 2), each group
    centred and of size 1. A triangle is kept when no other point of its group falls inside (or on) the circle through
    its corners. Returns the triples tried (m, 3), which of them are kept (G, m), their turn on the plane (G, m) and
    whether each group came out whole (G,): the kept triangles cover its outline. Four points on one circle, or three
    in a line on the outline, leave a gap: that group goes the usual way."""
    count = q.shape[1]
    triples = np.array(list(combinations(range(count), 3)), dtype=np.int64).reshape(-1, 3)
    a, b, c = (q[:, triples[:, k]] for k in range(3))                            # (G, m, 2)
    turn = (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0])
    d = q[:, None]                                                               # every point against every triple
    ad, bd, cd = a[:, :, None] - d, b[:, :, None] - d, c[:, :, None] - d          # (G, m, n, 2)

    def cross(u, w):
        return u[..., 0] * w[..., 1] - u[..., 1] * w[..., 0]
    inside = ((ad * ad).sum(-1) * cross(bd, cd) - (bd * bd).sum(-1) * cross(ad, cd)
              + (cd * cd).sum(-1) * cross(ad, bd)) * np.sign(turn)[..., None]   # > 0: inside the circle
    own = np.zeros((len(triples), count), dtype=bool)
    own[np.arange(len(triples))[:, None], triples] = True
    kept = (np.abs(turn) > 1e-9) & ((inside < -1e-9) | own).all(axis=-1)
    # the outline: the sides (i, j) with every other point on their left; its area against that of the triangles
    i, j = np.array([(i, j) for i in range(count) for j in range(count) if i != j]).T
    side = cross((q[:, j] - q[:, i])[:, :, None], q[:, None] - q[:, i][:, :, None])   # (G, pairs, n)
    other = np.ones((len(i), count), dtype=bool)
    other[np.arange(len(i)), i] = other[np.arange(len(i)), j] = False
    outline = ((side > 1e-9) | ~other).all(axis=-1)
    area_outline = np.where(outline, cross(q[:, i], q[:, j]), 0.0).sum(-1) / 2
    area_kept = np.where(kept, np.abs(turn), 0.0).sum(-1) / 2
    return triples, kept, turn, np.abs(area_outline - area_kept) <= 1e-9


def _small_groups(flat: np.ndarray, own_count: int, plane: str, more: bool) -> list:
    """The triangles of each group (as `delaunay` does them one by one), for many small groups at once: a list with
    the triangles of each group, or None for a group that has to go the usual way."""
    out = []
    step = max(1, 2_000_000 // (len(flat[0]) ** 4))                  # a few megabytes at a time
    for start in range(0, len(flat), step):
        group = flat[start:start + step]
        if plane == 'plan':
            xy, normal = group[..., :2], np.array([0.0, 0.0, 1.0])
        else:
            base = group[:, :own_count] if own_count >= 3 else group
            centre = base.mean(axis=1, keepdims=True)
            _, _, vt = np.linalg.svd(base - centre, full_matrices=False)
            normal = np.where((vt[:, 2, 2] >= 0)[:, None], vt[:, 2], -vt[:, 2])
            xy = np.einsum("gnd,gkd->gnk", group - centre, vt[:, :2])
        size = np.ptp(xy, axis=1).max(axis=-1)
        q = (xy - xy.mean(axis=1, keepdims=True)) / np.where(size > 0, size, 1.0)[:, None, None]
        triples, kept, turn, whole = _delaunay_small(q)
        tris = np.where((turn < 0)[..., None], triples[:, [0, 2, 1]], triples)      # (G, m, 3), all turning one way
        corner = np.take_along_axis(group[:, None], tris[..., None], axis=2)       # (G, m, 3, 3)
        n = np.cross(corner[:, :, 1] - corner[:, :, 0], corner[:, :, 2] - corner[:, :, 0]) * kept[..., None]
        base = group[:, :own_count]
        panel = np.cross(base, np.roll(base, -1, axis=1)).sum(axis=1)                # Newell: where each panel faces
        towards = corner.mean(axis=2) - group.mean(axis=1)[:, None]
        vote = np.einsum("gmd,gmd->g", n, towards)
        tie = np.abs(vote) <= 1e-9 * (np.abs(n).sum(axis=(1, 2)) + 1e-30)
        vote = np.where(tie, np.einsum("gmd,gd->g", n, np.broadcast_to(normal, panel.shape)), vote)
        if more and own_count >= 3:
            use = np.linalg.norm(panel, axis=-1) > 1e-12
            vote = np.where(use, np.einsum("gmd,gd->g", n, panel), vote)
        tris = np.where((vote < 0)[:, None, None], tris[..., [0, 2, 1]], tris)
        out.extend(t[k] if w else None for t, k, w in zip(tris, kept, whole))
    return out


def delaunay(points: Data, more=None, along: str | None = None, plane: str = 'best fit',
             name: str | None = None) -> Data:
    """The Delaunay triangulation of a group of points (*Delaunay Mesh*): triangles as even as possible, without
    thin ones. With other levels, one group for each (a pyramid on each panel, for example), all in one mesh.

    `more`: a point (or several) added to each group: the raised centre of each triangle, to make a pyramid. The
    group is triangulated on the plane that fits it best (or in plan). All the faces of a group turn the same way:
    with «more», towards the side the panel faces (its corners in order, anticlockwise seen from that side), so a
    raised pyramid is seen from outside and a sunk one from where it opens; without it, away from the group's
    middle."""
    if not isinstance(points, Data) or points.kind is not POINT or not points.levels:
        raise ShapeError(tr('“points” must be several points: those of each group, along a level.'))
    if plane not in DELAUNAY_PLANES:
        raise ShapeError(tr('The plane can be: {options}.').format(options=", ".join(tr(p) for p in DELAUNAY_PLANES)))
    along = along or points.levels[-1]
    if along not in points.levels:
        raise ShapeError(tr('“{along}” is not a level of “{name}” (its levels: {options}).').format(
            along=tr(along), name=points._name(), options=", ".join(tr(n) for n in points.levels)))
    groups = tuple(n for n in points.levels if n != along)
    v = np.moveaxis(np.asarray(points.values, dtype=float), points.levels.index(along), -2)   # (…groups, n, 3)
    shape = v.shape[:-2]
    own_count = v.shape[-2]                                    # the points of the group itself (they set its plane)
    if more is not None:
        if not isinstance(more, Data) or more.kind is not POINT:
            from .geometry import _what_is
            raise ShapeError(tr('“more” must be points (one or several added to each group, such as the raised centres '
                                'of the triangles), and it is {what_is}.').format(what_is=_what_is(more)))
        extra_levels = tuple(n for n in more.levels if n not in groups)
        if len(extra_levels) > 1 or any(n in more.levels and more.sizes[n] != points.sizes[n] for n in groups):
            raise ShapeError(tr('“more” must have the levels of the groups (and, at most, one of its own).'))
        from .data import _extend
        m = np.asarray(more.values, dtype=float)
        if extra_levels:
            m = np.moveaxis(m, more.levels.index(extra_levels[0]), -2)
            own = tuple(n for n in more.levels if n != extra_levels[0])
        else:
            m, own = m[..., None, :], more.levels
        m = _extend(m, own, groups, points.sizes) if own != groups else m
        m = np.broadcast_to(m, shape + m.shape[-2:])
        v = np.concatenate([v, m], axis=-2)
    flat = v.reshape(-1, v.shape[-2], 3)
    all_points, all_faces, offset = [], [], 0
    batch = _small_groups(flat, own_count, plane, more is not None) if 3 <= flat.shape[1] <= SMALL_GROUP else None
    for k, group in enumerate(flat):
        if batch is not None and batch[k] is not None:
            if len(batch[k]):
                all_faces.append(batch[k] + offset)
            all_points.append(group)
            offset += len(group)
            continue
        if plane == 'plan':
            xy, normal = group[:, :2], np.array([0.0, 0.0, 1.0])
        else:
            # the plane of the group's own points (a raised centre added with «more» does not tilt it)
            base = group[:own_count] if own_count >= 3 else group
            centre = base.mean(axis=0)
            _, _, vt = np.linalg.svd(base - centre, full_matrices=False)
            normal = vt[2] if vt[2] @ np.array([0.0, 0.0, 1.0]) >= 0 else -vt[2]
            xy = (group - centre) @ vt[:2].T
        tris = np.asarray(_delaunay_2d(xy), dtype=int).reshape(-1, 3)
        if len(tris):
            # All the triangles of a group turn the same way on its plane (they are neighbours: a skin with no face
            # turned over, also where a triangle joins three corners without the centre). Then the group as a whole
            # looks outwards, away from its middle (or along its plane's normal, when it is flat).
            e1, e2 = xy[tris[:, 1]] - xy[tris[:, 0]], xy[tris[:, 2]] - xy[tris[:, 0]]
            turn = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
            tris = np.where((turn < 0)[:, None], tris[:, [0, 2, 1]], tris)
            n = np.cross(group[tris[:, 1]] - group[tris[:, 0]], group[tris[:, 2]] - group[tris[:, 0]])
            base = group[:own_count]
            turn_of_panel = np.cross(base, np.roll(base, -1, axis=0)).sum(axis=0)   # Newell: where the panel faces
            if more is not None and own_count >= 3 and np.linalg.norm(turn_of_panel) > 1e-12:
                vote = float((n @ turn_of_panel).sum())      # the panel's corners in order: its side (a dent is seen
            else:                                            # from where it opens, a pyramid from outside)
                towards = group[tris].mean(axis=1) - group.mean(axis=0)
                vote = float(np.einsum("ij,ij->", n, towards))
                if abs(vote) <= 1e-9 * (float(np.abs(n).sum()) + 1e-30):
                    vote = float((n @ normal).sum())
            if vote < 0:
                tris = tris[:, [0, 2, 1]]
            all_faces.append(tris + offset)
        all_points.append(group)
        offset += len(group)
    if not all_faces:
        raise ShapeError(tr('No triangle could be made: the points are in a line, or too few.'))
    return Data(np.vstack(all_points), (), name, kind=kind_mesh(np.vstack(all_faces)))


def thicken_mesh(geometry: Data, thickness, name: str | None = None) -> Data:
    """A mesh with thickness, closed (*Mesh Thicken*): each vertex goes along its normal (positive, towards where the
    faces look; negative, the other way), the faces stay on one side and turned over on the other, and the open
    borders are sewn with a strip of quadrilaterals. A skin becomes a piece that can be printed or cut."""
    from .data import apply
    from .geometry import _data
    faces = [tuple(f) for f in _faces_of(geometry)]
    n = geometry.values.shape[-2]
    # The open borders: edges that only one face goes along (a→b, in the direction that face goes round).
    use = {}
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1]):
            use[(a, b)] = use.get((a, b), 0) + 1
    border = [(a, b) for (a, b) in use if (b, a) not in use]
    triangles = np.array([(f[0], f[j], f[j + 1]) for f in faces for j in range(1, len(f) - 1)], dtype=np.int64)
    new_faces = (faces + [tuple(n + i for i in reversed(f)) for f in faces]
                 + [(b, a, n + a, n + b) for a, b in border])

    def solid(v, e):
        a, b, c = (v[..., triangles[:, k], :] for k in range(3))
        area_normal = np.cross(b - a, c - a)                                  # (…, triangles, 3), as long as twice the area
        normals = np.zeros(v.shape)
        for k in range(3):
            _add_at(normals, triangles[:, k], area_normal)
        length = np.linalg.norm(normals, axis=-1, keepdims=True)
        normals = np.divide(normals, length, out=np.zeros_like(normals), where=length > 1e-15)
        # Where the faces around a vertex fold (the edge of a bottom), going along the averaged normal would leave
        # the wall thinner: the vertex goes further, so each face stays at the thickness asked (up to three times).
        face_length = np.linalg.norm(area_normal, axis=-1, keepdims=True)
        face_unit = np.divide(area_normal, face_length, out=np.zeros_like(area_normal), where=face_length > 1e-15)
        lowest = np.ones(v.shape[:-1])
        for k in range(3):
            cosine = np.einsum("...i,...i->...", normals[..., triangles[:, k], :], face_unit)
            _min_at(lowest, triangles[:, k], cosine)
        stretch = 1.0 / np.clip(lowest, 1 / 3, 1.0)
        e = np.asarray(e, dtype=float)[..., None, None]
        along = normals * stretch[..., None]
        return np.concatenate([v + along * np.maximum(e, 0), v + along * np.minimum(e, 0)], axis=-2)

    return apply(solid, geometry, _data(thickness), name=name, kind=kind_mesh(new_faces))


def _add_at(target: np.ndarray, index: np.ndarray, values: np.ndarray) -> None:
    """np.add.at along the vertex axis (the one before the last) of arrays with levels in front."""
    flat_t = target.reshape(-1, target.shape[-2], 3)
    flat_v = values.reshape(-1, values.shape[-2], 3)
    for k in range(len(flat_t)):
        np.add.at(flat_t[k], index, flat_v[k])


def _min_at(target: np.ndarray, index: np.ndarray, values: np.ndarray) -> None:
    """np.minimum.at along the vertex axis (the last one of `target`), with levels in front."""
    flat_t = target.reshape(-1, target.shape[-1])
    flat_v = values.reshape(-1, values.shape[-1])
    for k in range(len(flat_t)):
        np.minimum.at(flat_t[k], index, flat_v[k])
