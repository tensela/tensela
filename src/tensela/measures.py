"""Area, volume and centroid of each element.

    area(rectangle(10, 5))          → 50 (m²)
    volume(box(2, 3, 4))            → 24 (m³)
    centroid(l_shaped_curve)        → the balance point of the plan, not the average of its vertices

The *centroid* is the centre of gravity: in a plan, that of the area; in a closed volume, that of the volume; in an
open curve, that of its length. The «Centre» node gives something else: the average of the vertices, which in an
irregular shape (an L, a plan with many points on one side) shifts towards where there are more vertices.
"""

from __future__ import annotations

import numpy as np

from .data import Data, ShapeError
from .geometry import POINT, TOLERANCE_VERTEX, real_faces
from .language import tr


def _elements(geometry: Data):
    """(index, vertices) of each element that exists (without the holes of the variable levels)."""
    v = geometry.values
    shape = v.shape[:-2] if geometry.kind is not POINT else v.shape[:-1]
    mask = geometry.mask if geometry.levels else np.ones((), dtype=bool)
    for index in np.ndindex(shape):
        if np.broadcast_to(mask, shape)[index]:
            yield index, v[index]


def _repeated_without(p: np.ndarray, closed: bool) -> np.ndarray:
    """The vertices of a curve without the repeated ones in a row (the padding repeats the last one)."""
    follow = np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > TOLERANCE_VERTEX]
    p = p[follow]
    if closed and len(p) > 1 and np.linalg.norm(p[0] - p[-1]) <= TOLERANCE_VERTEX:
        p = p[:-1]
    return p


def _triangles_indices(faces) -> np.ndarray:
    """The faces of a kind, as a fan, as indices (n, 3): computed once per kind."""
    key = id(faces)
    if _CACHE_TRIANGLES.get(key, (None,))[0] is not faces:
        indices = [(face[0], face[j], face[j + 1]) for face in faces for j in range(1, len(face) - 1)]
        _remember(_CACHE_TRIANGLES, key, (faces, np.array(indices, dtype=np.int64).reshape(-1, 3)))
    return _CACHE_TRIANGLES[key][1]


#: How many kinds each cache keeps: the latest ones (each entry holds its faces, which may be a big mesh; without a
#: limit, every mesh measured in the session stayed in memory).
CACHED_KINDS = 32


def _remember(cache: dict, key, value) -> None:
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > CACHED_KINDS:
        cache.pop(next(iter(cache)))


_CACHE_TRIANGLES: dict = {}


def _kind_triangles(kind, p: np.ndarray) -> np.ndarray:
    if kind.polygon:                               # the polygons clean their repeated vertices, one by one
        triangles = [p[[face[0], face[j], face[j + 1]]]
                      for face in real_faces(kind, p) for j in range(1, len(face) - 1)]
        return np.array(triangles, dtype=float).reshape(-1, 3, 3)
    return p[_triangles_indices(kind.faces)]


def _triangles(kind, p: np.ndarray) -> np.ndarray:
    """The faces of an element in triangles (n, 3, 3), as a fan, with their orientation."""
    if kind.curve:                                  # a closed curve: its outline, as a fan
        p = _repeated_without(p, True)
        return np.stack([np.repeat(p[:1], len(p) - 2, axis=0), p[1:-1], p[2:]], axis=1) if len(p) >= 3 \
            else np.zeros((0, 3, 3))
    t = _kind_triangles(kind, p)
    # Out with those that repeat a point (the padding ones): they measure nothing and confuse the count of edges when
    # checking whether the body is closed. The flat ones with three different points (in a line) stay: they sew edges.
    size_ = float(np.ptp(p.reshape(-1, 3), axis=0).max()) if p.size else 0.0
    tol = size_ * 1e-9
    different = ((np.linalg.norm(t[:, 0] - t[:, 1], axis=1) > tol) & (np.linalg.norm(t[:, 1] - t[:, 2], axis=1) > tol)
                 & (np.linalg.norm(t[:, 2] - t[:, 0], axis=1) > tol))
    return t[different]


def _area_y_centre(kind, p: np.ndarray) -> tuple[float, np.ndarray]:
    t = _triangles(kind, p)
    vectors = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]) / 2     # the area of each triangle, with its normal
    centres = t.mean(axis=1)
    if kind.curve:
        # A plan: with a sign according to its normal, so a concave shape (an L, a U) gives its right area.
        total = vectors.sum(axis=0)
        normal = total / max(np.linalg.norm(total), 1e-300)
        weights = vectors @ normal
    else:
        weights = np.linalg.norm(vectors, axis=1)
    area = float(weights.sum())
    if abs(area) < 1e-15:
        return 0.0, centres.mean(axis=0) if len(centres) else p.mean(axis=0)
    return abs(area), (weights[:, None] * centres).sum(axis=0) / area


_CLOSED_CACHE: dict = {}


def _closed_by_indices(faces) -> bool:
    """Whether the faces of a kind enclose a volume by how they touch (without looking at coordinates): once per
    kind. If it does not look so (repeated points of a seam), the coordinates are checked."""
    key = id(faces)
    if _CLOSED_CACHE.get(key, (None,))[0] is not faces:
        t = _triangles_indices(faces)
        edges = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
        _, how_many = np.unique(edges, axis=0, return_counts=True)
        _remember(_CLOSED_CACHE, key, (faces, bool(len(how_many)) and bool(np.all(how_many == 2))))
    return _CLOSED_CACHE[key][1]


def _closed(t: np.ndarray, size_: float) -> bool:
    """Whether the triangles enclose a volume: each edge, shared by exactly two faces."""
    if not len(t):
        return False
    keys = np.round(t.reshape(-1, 3) / max(size_ * 1e-7, 1e-12)).astype(np.int64)
    _, ids = np.unique(keys, axis=0, return_inverse=True)
    ids = ids.reshape(-1, 3)
    edges = np.concatenate([ids[:, [0, 1]], ids[:, [1, 2]], ids[:, [2, 0]]])
    edges = edges[edges[:, 0] != edges[:, 1]]
    if not len(edges):
        return False
    edges.sort(axis=1)
    _, how_many = np.unique(edges, axis=0, return_counts=True)
    return bool(np.all(how_many == 2))


def _volume_y_centre(kind, p: np.ndarray, name: str) -> tuple[float, np.ndarray]:
    t = _triangles(kind, p)
    size_ = float(np.ptp(p.reshape(-1, 3), axis=0).max()) if len(p) else 0.0
    closed = (not kind.curve and not kind.polygon and kind.faces and _closed_by_indices(kind.faces)) \
        or (not kind.curve and len(t) and _closed(t, size_))
    if kind.curve or not len(t) or not closed:
        raise ShapeError(tr('“{name}” is not a closed volume: volume is only measured on bodies without gaps '
                              '(a box, a prism, some pipes). An open surface has area, not volume.').format(name=name))
    origin = p.reshape(-1, 3).mean(axis=0)          # closer to the shape: less rounding error
    a, b, c = t[:, 0] - origin, t[:, 1] - origin, t[:, 2] - origin
    volumes = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6     # each tetrahedron with the origin, with a sign
    total = float(volumes.sum())
    centre = (volumes[:, None] * (a + b + c) / 4).sum(axis=0) / total + origin
    return abs(total), centre


def _require_geometry(geometry: Data, what: str) -> None:
    if not isinstance(geometry, Data) or geometry.kind is None or geometry.kind is POINT:
        raise ShapeError(tr('“{name}” should be a geometry to measure its {what}.').format(
                               name=getattr(geometry, "_name", lambda: "?")(), what=tr(what)))


def area(geometry: Data, name: str | None = None) -> Data:
    """The area of each element (m²): a plan (closed curve), a surface or the skin of a volume."""
    _require_geometry(geometry, 'area')
    kind = geometry.kind
    if kind.curve and not kind.closed:
        raise ShapeError(tr('“{name}” is an open curve: it encloses no area. Close it (for example, “closed: '
                              'yes”) or use a surface.').format(name=geometry._name()))
    output = np.zeros(geometry.values.shape[:-2])
    for index, p in _elements(geometry):
        output[index] = _area_y_centre(kind, p)[0]
    return geometry.derived(output, name, None)


def length(geometry: Data, name: str | None = None) -> Data:
    """The length of each curve (m), closing the loop of a closed one; of a surface or a mesh, the sum of its edges is
    not a length anyone asks for, so it is refused."""
    _require_geometry(geometry, 'length')
    kind = geometry.kind
    # A rectangle, a polygon: one flat face, whose outline is a closed curve too (its perimeter).
    outline = kind.faces is not None and kind.grid is None and (kind.polygon or len(kind.faces) == 1)
    if not kind.curve and not outline:
        raise ShapeError(tr('“{name}” is not a curve: Length measures curves (for a surface, its Area).').format(
            name=geometry._name()))
    output = np.zeros(geometry.values.shape[:-2])
    for index, p in _elements(geometry):
        p = np.asarray(p, dtype=float)
        if not kind.curve:
            faces = real_faces(kind, p)
            if len(faces) != 1:
                raise ShapeError(tr('“{name}” is not a curve: Length measures curves (for a surface, its Area).')
                                 .format(name=geometry._name()))
            p = p[list(faces[0])]
        closed = kind.closed or not kind.curve
        p = _repeated_without(p, closed)
        if closed and len(p) > 2:
            p = np.vstack([p, p[:1]])
        output[index] = float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
    return geometry.derived(output, name, None)


def volume(geometry: Data, name: str | None = None) -> Data:
    """The volume of each closed body (m³): a box, a prism, some tubes."""
    _require_geometry(geometry, "volumen")
    output = np.zeros(geometry.values.shape[:-2])
    for index, p in _elements(geometry):
        output[index] = _volume_y_centre(geometry.kind, p, geometry._name())[0]
    return geometry.derived(output, name, None)


def centroid(geometry: Data, name: str | None = None) -> Data:
    """The centre of gravity of each element: of the volume if it is a closed body; of the area if it is a plan or a
    surface; of the length if it is an open curve."""
    _require_geometry(geometry, "centroide")
    kind = geometry.kind
    output = np.zeros(geometry.values.shape[:-2] + (3,))
    for index, p in _elements(geometry):
        if kind.curve and not kind.closed:          # an open curve: the centre of its length
            q = _repeated_without(p, False)
            lengths = np.linalg.norm(np.diff(q, axis=0), axis=1)
            midpoints = (q[1:] + q[:-1]) / 2
            output[index] = (lengths[:, None] * midpoints).sum(axis=0) / lengths.sum() if lengths.sum() > 0 else q[0]
            continue
        if not kind.curve:
            t = _triangles(kind, p)
            size_ = float(np.ptp(p.reshape(-1, 3), axis=0).max())
            if len(t) and ((not kind.polygon and _closed_by_indices(kind.faces)) or _closed(t, size_)):
                output[index] = _volume_y_centre(kind, p, geometry._name())[1]
                continue
        output[index] = _area_y_centre(kind, p)[1]
    return geometry.derived(output, name, POINT)


# --- Inside (an architect's «contains») ---------------------------------------------------------

def _plan_inside(p: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Whether each point p (…, 3) falls inside the outline c (…, n, 3), seen perpendicular to its plane (in plan, if
    the outline is horizontal). The crossings of a ray with the sides are counted (even: outside; odd: inside)."""
    c = np.concatenate([c, c[..., :1, :]], axis=-2)              # the closing side
    next_ = np.roll(c, -1, axis=-2)
    normal = np.cross(c, next_).sum(axis=-2)                 # Newell: the normal of the outline
    normal = normal / np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-300)
    help = np.where(np.abs(normal[..., :1]) < 0.9, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
    u = np.cross(normal, help)
    u = u / np.maximum(np.linalg.norm(u, axis=-1, keepdims=True), 1e-300)
    v = np.cross(normal, u)
    origin = c[..., :1, :]
    cu = ((c - origin) * u[..., None, :]).sum(-1)
    cv = ((c - origin) * v[..., None, :]).sum(-1)
    pu = ((p[..., None, :] - origin) * u[..., None, :]).sum(-1)  # (…, 1)
    pv = ((p[..., None, :] - origin) * v[..., None, :]).sum(-1)
    x0, y0, x1, y1 = cu[..., :-1], cv[..., :-1], cu[..., 1:], cv[..., 1:]
    crosses = (y0 > pv) != (y1 > pv)
    with np.errstate(divide="ignore", invalid="ignore"):
        cut_x = x0 + (pv - y0) * (x1 - x0) / (y1 - y0)
    return (np.sum(crosses & (pu < cut_x), axis=-1) % 2) == 1


def _volume_inside(p: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Whether each point p (m, 3) is inside the closed body of triangles t (k, 3, 3): the winding number (the sum of
    the solid angles of the faces, seen from the point) is 1 inside and 0 outside."""
    a, b, c = (t[None, :, i, :] - p[:, None, :] for i in range(3))
    la, lb, lc = (np.linalg.norm(x, axis=-1) for x in (a, b, c))
    above = np.einsum("mki,mki->mk", a, np.cross(b, c))
    below = (la * lb * lc + np.einsum("mki,mki->mk", a, b) * lc + np.einsum("mki,mki->mk", a, c) * lb
             + np.einsum("mki,mki->mk", b, c) * la)
    turns = (2 * np.arctan2(above, below)).sum(axis=-1) / (4 * np.pi)
    return np.abs(turns) > 0.5


def inside(points, region: Data, name: str | None = None) -> Data:
    """Yes or no for each point: whether it falls inside a plan (a closed curve, a rectangle; it is checked in plan,
    perpendicular to it) or a closed volume (a box, a prism). A geometry is tested by its centre: the columns that fall
    inside the courtyard, the trees inside the building."""
    if points is None:
        raise ShapeError(tr('The “points” to test are missing (or a geometry: each element is tested by its centre).'))
    if not isinstance(region, Data) or region.kind is None or region.kind is POINT:
        raise ShapeError(tr('“inside” should be a plan (a closed curve, a rectangle) or a closed volume (a box, '
                              'a prism).'))
    from .geometry import _centres
    p = _centres(points, "points")
    kind = region.kind
    plane = kind.curve or (not kind.curve and kind.faces and len(kind.faces) == 1)
    if kind.curve and not kind.closed:
        raise ShapeError(tr('“{name}” is an open curve: it has no inside or outside. Close it (“closed: yes”) '
                              'or use a rectangle, a circle, a closed plan.').format(name=region._name()))
    if plane:
        return _apply_without_holes(_plan_inside, p, region, name)
    if not region.levels:                                    # a single body (the usual): all the points at once
        t = _closed_triangles(kind, region.values, region)

        def against_body(q, _):
            planes = q.reshape(-1, 3)
            parts = [_volume_inside(planes[i:i + 2000], t) for i in range(0, len(planes), 2000)]
            return (np.concatenate(parts) if parts else np.zeros(0, bool)).reshape(q.shape[:-1])
        return _apply_without_holes(against_body, p, Data.value(np.zeros(())), name)
    # Several bodies: each one, with its triangles, against the points that belong to it.
    from .data import align
    a = align(p, region)
    points_to, bodies = a.values
    shape = np.broadcast_shapes(points_to.shape[:-1], bodies.shape[:len(a.levels)])
    output = np.zeros(shape, dtype=bool)
    size_ = float(np.ptp(region.values.reshape(-1, 3), axis=0).max()) if region.values.size else 0.0
    seen: dict = {}
    for index in np.ndindex(shape):
        body = np.broadcast_to(bodies, shape + bodies.shape[len(a.levels):])[index]
        key = body.__array_interface__["data"][0]          # the same body, without triangulating it again
        if key not in seen:
            seen[key] = _closed_triangles(kind, body, region, size_)
        output[index] = _volume_inside(np.broadcast_to(points_to, shape + (3,))[index][None], seen[key])[0]
    return Data(output, a.levels, name, a.variables, a.starts, None, a.holes)


def _closed_triangles(kind, body: np.ndarray, region: Data, size_: float | None = None) -> np.ndarray:
    """The triangles of a body, or a clear error if it is not closed (a surface has no inside)."""
    triangles = _triangles(kind, body)
    if size_ is None:
        size_ = float(np.ptp(body.reshape(-1, 3), axis=0).max()) if body.size else 0.0
    closed = (not kind.polygon and kind.faces and _closed_by_indices(kind.faces)) or \
        (len(triangles) and _closed(triangles, size_))
    if not closed:
        raise ShapeError(tr('“{name}” is not a closed volume: an open surface has no inside. Use a box, a '
                              'prism, an extrusion with caps.').format(name=region._name()))
    return triangles


def _apply_without_holes(function, p: Data, region: Data, name):
    from .data import apply
    return apply(function, p, region, name=name)
