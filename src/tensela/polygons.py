"""Polygons, random points and 3D Voronoi (exercise bank: EX 4 and EX 5).

A **polygon** has a variable number of vertices. In a data, all its elements keep the same number (that of the one
with most vertices); the others repeat the last one to fill up, and `geometry.real_faces` removes them when drawing
or exporting. A Voronoi **cell** is a polyhedron: its faces are polygons, with a «face» level of variable size (each
cell has its own).

All with numpy: each cell is the region cut by the planes that separate it from the other seeds (halfway between
the two).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from .data import Data, ShapeError, _require_size_, integer
from .geometry import POINT, TOLERANCE_VERTEX, Kind
from .language import tr

MAX_CELLS = 2000


@lru_cache(maxsize=None)
def kind_polygon(sides: int) -> Kind:
    """A polygon (padded) of up to `sides` vertices."""
    return Kind("polygon", (tuple(range(sides)),), polygon=True)


@lru_cache(maxsize=None)
def polygon_kind_frame(sides: int) -> Kind:
    """A flat polygon frame: outer vertices (0…n-1) and inner ones (n…2n-1); one quadrilateral per side."""
    faces = tuple((i, (i + 1) % sides, sides + (i + 1) % sides, sides + i) for i in range(sides))
    return Kind("frame", faces, polygon=True)


@lru_cache(maxsize=None)
def polygon_kind_prism(sides: int) -> Kind:
    """A thickened polygon: base (0…n-1), cap (n…2n-1) and one quadrilateral per side."""
    base = tuple(reversed(range(sides)))
    cap = tuple(range(sides, 2 * sides))
    sides_ = tuple((i, (i + 1) % sides, sides + (i + 1) % sides, sides + i) for i in range(sides))
    return Kind("block", (base, cap, *sides_), polygon=True)


@lru_cache(maxsize=None)
def coarse_polygon_kind_frame(sides: int) -> Kind:
    """A polygon frame with thickness: front outside (0…), front inside (n…), back outside (2n…), back inside (3n…);
    four quadrilaterals per side (front, back, outer edge, inner edge)."""
    n = sides
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces += [(i, j, n + j, n + i),                       # frente
                  (2 * n + i, 3 * n + i, 3 * n + j, 2 * n + j),   # dorso
                  (j, i, 2 * n + i, 2 * n + j),               # outer edge
                  (n + i, n + j, 3 * n + j, 3 * n + i)]       # inner edge
    return Kind("frame", tuple(faces), polygon=True)


def normal_de(g: np.ndarray) -> np.ndarray:
    """The (unit) normal of each polygon, by Newell's method (the repeated vertices do not count)."""
    next_ = np.roll(g, -1, axis=-2)
    n = np.cross(g, next_).sum(axis=-2)
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    return np.divide(n, length, out=np.zeros_like(n), where=length > 1e-12)


def frame(panel: Data, opening, thickness: float, output: str, name: str | None) -> Data:
    """`geometry.frame` for polygons: the opening is the polygon shrunk towards its centre (`opening`)."""
    from .geometry import _data, _average
    from .data import apply
    sides = panel.values.shape[-2]
    thickness = float(thickness)

    def build(g, x):
        c = _average(g, True, keepdims=True)
        hole = c + (g - c) * np.clip(np.asarray(x, dtype=float), 0, 0.98)[..., None, None]
        if output == 'hole':
            return hole
        plane = np.concatenate([np.broadcast_to(g, hole.shape), hole], axis=-2)
        if not thickness:
            return plane
        return np.concatenate([plane, plane + normal_de(g)[..., None, :] * thickness], axis=-2)

    kind = (kind_polygon(sides) if output == 'hole'
            else coarse_polygon_kind_frame(sides) if thickness else polygon_kind_frame(sides))
    return apply(build, panel, _data(opening), name=name, kind=kind)


def thicken(polygon: Data, thickness, name: str | None) -> Data:
    """Each polygon, a block of `thickness` towards where it faces (negative: inwards)."""
    from .geometry import _data
    from .data import apply
    sides = polygon.values.shape[-2]

    def block(g, e):
        n = normal_de(g)[..., None, :]
        e = np.asarray(e, dtype=float)[..., None, None]
        return np.concatenate([g + n * np.minimum(e, 0), g + n * np.maximum(e, 0)], axis=-2)

    return apply(block, polygon, _data(thickness), name=name, kind=polygon_kind_prism(sides))


def _vertices(data: Data) -> np.ndarray:
    """The vertices of all the elements that exist, together (n × 3)."""
    v = data.values[data.mask] if data.levels else data.values[None]
    return np.asarray(v, float).reshape(-1, 3)


def box_of(region: Data, flat: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """The box that wraps a geometry (minimum and maximum in x, y, z). `flat`: it also holds without height (a
    rectangle in plan), or without width or depth (one in elevation)."""
    if region.kind is None:
        raise ShapeError(tr('“{name}” should be a geometry (a box, a prism…), and it is a number.').format(
                               name=region._name()))
    v = _vertices(region)
    minimum, maximum = v.min(axis=0), v.max(axis=0)
    if (np.sum(maximum - minimum > 1e-9) < 2) if flat else np.any(maximum - minimum <= 1e-9):
        raise ShapeError(tr('“{name}” has no volume: a box or a prism is needed.').format(
                               name=region._name()))
    return minimum, maximum


def points_random(region: Data, count: int, seed: int = 1, level: str = "point",
                   name: str | None = None) -> Data:
    """`count` random points inside the box that wraps `region` (or in a rectangle, if it is flat); the same seed,
    the same points."""
    count = integer(count)
    if count < 1:
        raise ShapeError(tr('The number of points must be 1 or more (it is {count}).').format(count=count))
    _require_size_({level: count}, tr('The random points'))
    minimum, maximum = box_of(region, flat=True)
    random = np.random.default_rng(abs(integer(seed)))
    return Data(minimum + random.random((count, 3)) * (maximum - minimum), (level,), name, kind=POINT)


# --- Voronoi 3D ------------------------------------------------------------------------

# The faces of a box, each one anticlockwise seen from outside (indices of its 8 vertices).
_FACES_BOX = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def _box(minimum, maximum) -> tuple[np.ndarray, list[list[int]]]:
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], dtype=float)
    return v, [list(c) for c in _FACES_BOX]


def _trim(vertices: np.ndarray, faces: list[list[int]], normal: np.ndarray,
              limit: float) -> tuple[np.ndarray, list[list[int]]]:
    """A convex polyhedron (its vertices, and its faces as indices anticlockwise seen from outside) cut by the
    plane x·normal = limit: what has x·normal ≤ limit stays, with its cap.

    Each cut edge gives a single new point, shared by its two faces; the cap is built by chaining the cut segments of
    each face (each face runs its own from the exit to the entry; the cap, the other way round)."""
    d = (vertices @ normal - limit).tolist()
    margin = 1e-9 * float(np.sqrt(normal @ normal))      # a millimetre of a millimetre, at the scale of the normal
    outside = [x > margin for x in d]
    if not any(outside):
        return vertices, faces
    if all(outside):
        return vertices[:0], []
    new, in_edge, n0, v = [], {}, len(vertices), vertices.tolist()   # with plain numbers: faster

    def cut(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        i = in_edge.get(key)
        if i is None:
            t = min(1.0, max(0.0, d[a] / (d[a] - d[b])))
            (xa, already, za), (xb, yb, zb) = v[a], v[b]
            new.append((xa + (xb - xa) * t, already + (yb - already) * t, za + (zb - za) * t))
            i = in_edge[key] = n0 + len(new) - 1
        return i

    remain, cap = [], {}
    for face in faces:
        if not any(outside[i] for i in face):
            remain.append(face)
            continue
        if all(outside[i] for i in face):
            continue
        output, comes_out, enters, m = [], None, None, len(face)
        for k in range(m):                        # Sutherland–Hodgman
            a, b = face[k], face[(k + 1) % m]
            if not outside[a]:
                output.append(a)
            if outside[a] != outside[b]:
                c = cut(a, b)
                output.append(c)
                if outside[b]:
                    comes_out = c
                else:
                    enters = c
        if enters is not None and comes_out is not None:
            cap[enters] = comes_out
        remain.append(output)
    all_ = np.array(v + new)
    if len(cap) >= 3:
        start = next(iter(cap))
        cycle, x = [start], cap[start]
        while x != start and x in cap and len(cycle) <= len(cap):
            cycle.append(x)
            x = cap[x]
        if x != start or len(cycle) != len(cap):           # a rare case (points on the plane): by angles
            cycle = _arrange_cap(all_, sorted(set(cap) | set(cap.values())), normal)
        remain.append(cycle)
    used = sorted({i for face in remain for i in face})     # without the vertices that were left outside
    new_index = {v: k for k, v in enumerate(used)}
    return all_[used], [[new_index[i] for i in face] for face in remain]


def _arrange_cap(vertices: np.ndarray, indices: list[int], normal: np.ndarray) -> list[int]:
    """The points of the cap anticlockwise seen from the normal (from outside)."""
    p = vertices[indices]
    centre = p.mean(axis=0)
    u = p[0] - centre
    u /= np.linalg.norm(u) or 1.0
    w = np.cross(normal / np.linalg.norm(normal), u)
    angles = np.arctan2((p - centre) @ w, (p - centre) @ u)
    return [indices[k] for k in np.argsort(angles)]


def _clean(face: np.ndarray) -> np.ndarray:
    """The face without repeated vertices in a row (also the last equal to the first)."""
    if len(face) < 2:
        return face
    next_ = np.empty_like(face)
    next_[:-1], next_[-1] = face[1:], face[0]
    diff = face - next_
    remains = np.einsum("ij,ij->i", diff, diff) > TOLERANCE_VERTEX ** 2
    return face if remains.all() else face[remains]


def voronoi_3d(points: Data, region: Data, level: str = "cell", faces_level: str = "face",
               name: str | None = None) -> Data:
    """The Voronoi cells of `points` inside the box of `region`: to each seed, the space closer to it than to the
    others. Each cell is a polyhedron: its faces, polygons, in `[cell × face]`."""
    if points.kind != POINT:
        raise ShapeError(tr('“{name}” should be points (the seeds) for the Voronoi.').format(
                               name=points._name()))
    seeds = _vertices(points)
    if len(seeds) < 1:
        raise ShapeError(tr('The Voronoi needs at least one seed.'))
    if len(seeds) > MAX_CELLS:
        raise ShapeError(tr('Too many seeds for the Voronoi ({n}; the maximum is {maximum}).').format(
                               n=len(seeds), maximum=MAX_CELLS))
    minimum, maximum = box_of(region)
    cells = []
    for i, p in enumerate(seeds):
        vertices, faces = _box(minimum, maximum)
        others = np.delete(seeds, i, axis=0)
        far = np.linalg.norm(others - p, axis=1)
        order = np.argsort(far)
        others = others[order][far[order] > 1e-12]                     # two seeds in the same place: it does not cut
        normals, midpoints = others - p, (others + p) / 2                   # from the nearest to the farthest
        limits = np.einsum("ij,ij->i", midpoints, normals)               # the plane: x·normal = limit
        margins = 1e-9 * np.linalg.norm(normals, axis=1)
        radius = float(np.sqrt(((vertices - p) ** 2).sum(axis=1).max()))
        distances = far[order][far[order] > 1e-12]
        for k in range(len(normals)):
            # The plane is halfway between the two seeds: if it is beyond the farthest point of the
            # cell, neither it nor the following ones (farther still) touch it.
            if distances[k] / 2 > radius + 1e-9:
                break
            if (vertices @ normals[k]).max() - limits[k] <= margins[k]:
                continue                                               # it does not touch it
            vertices, faces = _trim(vertices, faces, normals[k], limits[k])
            if not faces:
                break
            radius = float(np.sqrt(((vertices - p) ** 2).sum(axis=1).max()))
        cells.append([f for f in (_clean(vertices[c]) for c in faces) if len(f) >= 3])

    n_faces = max(1, max(len(c) for c in cells))
    n_vertices = max(3, max((len(f) for c in cells for f in c), default=3))
    values = np.zeros((len(cells), n_faces, n_vertices, 3))
    counts = np.zeros(len(cells), dtype=int)
    for i, faces in enumerate(cells):
        counts[i] = len(faces)
        for k, face in enumerate(faces):
            values[i, k, : len(face)] = face
            values[i, k, len(face):] = face[-1]           # the padding: the last vertex, repeated
    variables = {faces_level: Data(counts, (level,))}
    return Data(values, (level, faces_level), name, variables, kind=kind_polygon(n_vertices))


# --- Voronoi on a plane ------------------------------------------------------------------

#: The sides of the circle that limits each cell when the Voronoi has a radius.
CIRCLE_SIDES = 48


def _plane_frame(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The origin and the two axes (x, y) of the plane that fits some points best. A plane that is nearly level keeps
    the axes of the plan (the cells are then drawn as in plan); with too few points or in a line, the plan."""
    centre = v.mean(axis=0)
    plan = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    if len(v) < 3:
        return centre, plan
    _, s, vt = np.linalg.svd(v - centre, full_matrices=False)
    if s[1] <= 1e-9 * max(s[0], 1e-30) or abs(vt[2][2]) > 1 - 1e-6:
        return centre, plan
    normal = vt[2] if vt[2][2] >= 0 else -vt[2]
    x = vt[0] - normal * (vt[0] @ normal)
    x /= np.linalg.norm(x)
    return centre, np.stack([x, np.cross(normal, x)])


def _clip_half(poly: np.ndarray, normal: np.ndarray, limit: float) -> np.ndarray:
    """The part of a convex polygon (n × 2) where x·normal <= limit."""
    if len(poly) == 0:
        return poly
    d = poly @ normal - limit
    out = []
    for i in range(len(poly)):
        a, b, da, db = poly[i - 1], poly[i], d[i - 1], d[i]
        if db <= 0:
            if da > 0:
                out.append(a + (b - a) * (da / (da - db)))
            out.append(b)
        elif da <= 0:
            out.append(a + (b - a) * (da / (da - db)))
    return np.array(out) if out else np.zeros((0, 2))


def _signed_area(p: np.ndarray) -> float:
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def voronoi(points: Data, boundary=None, radius=None, level: str = "cell", name: str | None = None) -> Data:
    """The Voronoi diagram of some points on a plane: to each seed, the part of the plane closer to it than to the
    others, as a polygon. The cells stay inside `boundary` (a closed curve or a polygon, also with corners going in);
    without it, inside a rectangle a little larger than the seeds. With `radius`, no cell goes farther than that from
    its seed (the cells round off and leave gaps). The plane is that of the boundary (or of the seeds); a seed outside
    the boundary has no cell."""
    if not isinstance(points, Data) or points.kind != POINT:
        raise ShapeError(tr('“{name}” should be points (the seeds) for the Voronoi.').format(
            name=points._name() if isinstance(points, Data) else "points"))
    seeds = _vertices(points)
    if len(seeds) < 1:
        raise ShapeError(tr('The Voronoi needs at least one seed.'))
    if len(seeds) > MAX_CELLS:
        raise ShapeError(tr('Too many seeds for the Voronoi ({n}; the maximum is {maximum}).').format(
            n=len(seeds), maximum=MAX_CELLS))
    outline = None
    if boundary is not None:
        if not isinstance(boundary, Data) or boundary.kind is None or boundary.kind is POINT or (
                boundary.levels and int(np.count_nonzero(boundary.mask)) != 1):
            raise ShapeError(tr('The boundary of the Voronoi must be a single closed curve or polygon (a rectangle, a '
                                'circle, a drawn outline).'))
        outline = _clean(_vertices(boundary))
        if len(outline) < 3:
            raise ShapeError(tr('The boundary of the Voronoi must be a single closed curve or polygon (a rectangle, a '
                                'circle, a drawn outline).'))
    if radius is not None:
        radius = float(np.asarray(radius.values if isinstance(radius, Data) else radius, float).reshape(-1)[0])
        if radius <= 0:
            raise ShapeError(tr('The radius of the Voronoi must be more than 0 (it is {radius}).').format(radius=radius))
    origin, axes = _plane_frame(outline if outline is not None else seeds)
    flat = (seeds - origin) @ axes.T
    from manifold3d import CrossSection
    if outline is not None:
        ring = (outline - origin) @ axes.T
        if _signed_area(ring) < 0:
            ring = ring[::-1]
        region = CrossSection([ring])
    else:
        low, high = flat.min(axis=0), flat.max(axis=0)
        pad = np.maximum((high - low) * 0.1, max(float((high - low).max()) * 0.1, 1.0))
        low, high = low - pad, high + pad
        region = CrossSection([np.array([low, [high[0], low[1]], high, [low[0], high[1]]])])
    lo, hi = (np.array(b, float) for b in (region.bounds()[:2], region.bounds()[2:]))
    span = float(np.linalg.norm(hi - lo)) + float(np.ptp(flat, axis=0).max(initial=0.0)) + 1.0
    centre = (lo + hi) / 2
    big = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], float) * span * 2 + centre
    t = np.linspace(0, 2 * np.pi, CIRCLE_SIDES, endpoint=False)
    circle = np.stack([np.cos(t), np.sin(t)], axis=1) * (radius or 0)    # its corners on the circle: none farther
    cells = []
    for i, p in enumerate(flat):
        others = np.delete(flat, i, axis=0)
        far = np.linalg.norm(others - p, axis=1)
        keep = far > 1e-12                                     # two seeds in the same place: it does not cut
        others, far = others[keep], far[keep]
        order = np.argsort(far)
        poly = big if radius is None else circle + p
        reach = float(np.linalg.norm(poly - p, axis=1).max())
        for k in order:
            if far[k] / 2 > reach + 1e-9:                      # the halfway line is beyond the cell: so are the rest
                break
            normal = others[k] - p
            poly = _clip_half(poly, normal, float(normal @ (others[k] + p) / 2))
            if len(poly) < 3:
                break
            reach = float(np.linalg.norm(poly - p, axis=1).max())
        if len(poly) < 3:
            continue
        piece = CrossSection([poly if _signed_area(poly) > 0 else poly[::-1]]) ^ region
        parts = [q for q in piece.to_polygons() if len(q) >= 3]
        if not parts:
            continue
        best = max(parts, key=lambda q: abs(_signed_area(np.asarray(q))))   # a cell cut in two by the boundary: the
        best = np.asarray(best, float)                                      # larger piece
        if abs(_signed_area(best)) <= 1e-12:
            continue
        if _signed_area(best) < 0:
            best = best[::-1]
        cells.append(origin + best @ axes)
    if not cells:
        raise ShapeError(tr('No Voronoi cell falls inside the boundary: the seeds are outside it.'))
    _require_size_({level: len(cells)}, tr('The Voronoi'))
    sides = max(3, max(len(c) for c in cells))
    values = np.zeros((len(cells), sides, 3))
    for i, c in enumerate(cells):
        values[i, :len(c)] = c
        values[i, len(c):] = c[-1]                             # the padding: the last vertex, repeated
    return Data(values, (level,), name, kind=kind_polygon(sides))
