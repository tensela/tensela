"""Vertices, edges, joined lists, neighbours, fused tubes and spheres (exercise bank: EX 17).

    edges(box(20, 20, 20))                          → [edge 12] (lines)
    join_nearby(points [point 11], 4)               → [point 11 × neighbour 4] (lines)
    tubes(join_lists(edges, members), radius=1.5)   → a mesh: the tubes fused into a single skin

`tubes` is Grasshopper's *MultiPipe*: each line, a tube; where they meet, they fuse with a smooth fillet. It is
computed as a level surface (the distance to the lines, blended smoothly) and closed with *marching cubes* (VTK,
which the 3D view already uses).
"""

from __future__ import annotations

import math

import numpy as np

from .data import Data, ShapeError, _require_size_, apply, integer
from .geometry import CURVE, POINT, Kind, _data, _point, kind_surface
from .language import tr

#: Mesh points per tube radius (more, finer and slower).
DETAIL = 4
#: How many rows and columns a sphere has.
ROWS_SPHERE, COLUMNS_SPHERE = 33, 65


def kind_mesh(faces) -> Kind:
    """A free mesh: its vertices and its triangles (each mesh, its own)."""
    if isinstance(faces, np.ndarray):                  # (faster than number by number)
        return Kind("mesh", tuple(map(tuple, faces.astype(np.int64).tolist())))
    return Kind("mesh", tuple(tuple(int(i) for i in c) for c in faces))


def _elements(data: Data) -> np.ndarray:
    """The elements that exist, one after the other: (n, …)."""
    return data.values[data.mask] if data.levels else data.values[None]


def vertices(geometry: Data, level: str = "vertex", name: str | None = None) -> Data:
    """The vertices of each element, as points: the corners of a box, the points of a curve."""
    if geometry.kind is None or geometry.kind is POINT:
        raise ShapeError(tr('“{name}” should be a geometry with vertices (a box, a curve…).').format(
                               name=geometry._name()))
    return geometry.derived(geometry.values, name, POINT, (level,))


def edges(geometry: Data, level: str = "edge", name: str | None = None) -> Data:
    """The edges of each element (each one once), as lines: the 12 of a box."""
    kind = geometry.kind
    if kind is None or kind.faces is None or kind.polygon:
        raise ShapeError(tr('“{name}” should be a geometry with faces (a box, a rectangle…).').format(
                               name=geometry._name()))
    # Each edge goes the way the first face that has it goes round: the four sides of a rectangle all turn the same
    # way (what a Koch step or an offset to one side needs).
    pairs, seen = [], set()
    for face in kind.faces:
        for a, b in zip(face, face[1:] + face[:1]):
            if (min(a, b), max(a, b)) not in seen:
                seen.add((min(a, b), max(a, b)))
                pairs.append((a, b))
    values = geometry.values[..., np.array(pairs), :]          # (…, arista, 2, 3)
    return geometry.derived(values, name, CURVE, (level,))


def join_lists(a: Data, b: Data, level: str = "element", name: str | None = None, *more: Data | None) -> Data:
    """The elements of `a` and then those of `b` (and those of `more`, up to eight), in a single list (*Merge*).

    If `level` is a level of both, they join **along that level** and the others are kept: the points of the front of
    each rib and then those of its back, rib by rib.
    """
    for font, x in zip("abcdefgh", (a, b, *more)):
        if x is not None and not isinstance(x, Data):
            raise ShapeError(tr('«{font}» must be a list connected from another node (it gets «{value}»).').format(
                                   font=font, value=x))
    joined = _join_two(a, b, level, name)
    for other in more:
        if other is not None:
            joined = _join_two(joined, other, level, name)
    return joined


def _join_two(a: Data, b: Data, level: str, name: str | None) -> Data:
    if a.kind != b.kind or a.values.shape[len(a.levels):] != b.values.shape[len(b.levels):]:
        raise ShapeError(tr('To merge “{a}” and “{b}” they must be the same kind (both lines, both points…).').format(
                               a=a._name(), b=b._name()))
    if level in a.levels and level in b.levels:
        return _join_a_length(a, b, level, name)
    values = np.concatenate([_elements(a), _elements(b)])
    _require_size_({level: len(values)}, tr('The merged list'))
    return Data(values, (level,), name, kind=a.kind)


def _join_a_length(a: Data, b: Data, level: str, name: str | None) -> Data:
    """`a` and then `b` along `level`; the other levels, paired by their name (R1)."""
    from .data import align
    others_a = [n for n in a.levels if n != level]
    others_b = [n for n in b.levels if n != level]
    # Everything is aligned except the level being joined: it is put at the end and hidden in the values.
    def without_level(d: Data) -> Data:
        axis = d.levels.index(level)
        v = np.moveaxis(d.values, axis, len(d.levels) - 1)
        others = tuple(n for n in d.levels if n != level)
        return Data(v, others, d._name(), {k: c for k, c in d.variables.items() if k != level},
                    {k: i for k, i in d.starts.items() if k != level}, d.kind)
    al = align(without_level(a), without_level(b))
    goes, vb = al.values
    k = len(al.levels)
    shape = np.broadcast_shapes(goes.shape[:k], vb.shape[:k])
    goes = np.broadcast_to(goes, shape + goes.shape[k:])
    vb = np.broadcast_to(vb, shape + vb.shape[k:])
    together = np.concatenate([goes, vb], axis=k)
    _require_size_({**dict(zip(al.levels, shape)), level: together.shape[k]}, tr('The merged list'))
    del others_a, others_b
    return Data(together, (*al.levels, level), name, al.variables, al.starts, a.kind)


def join_nearest(points: Data, count: int = 3, level: str = "neighbour", name: str | None = None) -> Data:
    """Joins each point with its `count` nearest neighbours (*Closest Points* + *Line*)."""
    if points.kind is not POINT:
        raise ShapeError(tr('“{name}” should be points.').format(name=points._name()))
    p = _elements(points)
    k = min(integer(count), len(p) - 1)
    if k < 1:
        raise ShapeError(tr('Joining neighbours needs 2 or more points and a count of 1 or more.'))
    distances = np.linalg.norm(p[:, None] - p[None], axis=-1)
    np.fill_diagonal(distances, np.inf)
    neighbours = np.argsort(distances, axis=1, kind="stable")[:, :k]
    lines = np.stack([np.broadcast_to(p[:, None], (len(p), k, 3)), p[neighbours]], axis=2)   # (punto, vecino, 2, 3)
    level_points = points.levels[0] if len(points.levels) == 1 else "point"
    return Data(lines, (level_points, level), name, kind=CURVE)


def _runs(curves: Data) -> np.ndarray:
    """The straight segments of all the curves, without repeats (in any direction): (n, 2, 3)."""
    c = _elements(curves)
    runs = np.stack([c[:, :-1], c[:, 1:]], axis=2).reshape(-1, 2, 3)
    if curves.kind.closed:
        runs = np.concatenate([runs, np.stack([c[:, -1], c[:, 0]], axis=1)])
    runs = runs[np.linalg.norm(runs[:, 1] - runs[:, 0], axis=-1) > 1e-9]
    # A repeated segment (a→b and b→a) would fatten the tube: one is left.
    difference = np.round(runs[:, 1] - runs[:, 0], 6)
    first = np.argmax(difference != 0, axis=1)                  # the first axis in which they differ
    on_reverse = difference[np.arange(len(runs)), first] < 0
    sorted_ = np.where(on_reverse[:, None, None], runs[:, ::-1], runs)
    keys = np.round(sorted_.reshape(len(sorted_), 6), 6)
    _, unique = np.unique(keys, axis=0, return_index=True)
    return runs[np.sort(unique)]


def _minimum_smooth(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """The smaller of two, with a curve of radius ~k where they are alike: the fillet between two tubes."""
    h = np.clip(k - np.abs(a - b), 0.0, None) / k
    return np.minimum(a, b) - h * h * k / 4


def _field(p: np.ndarray, a: np.ndarray, ab: np.ndarray, largo2: np.ndarray, fillet: float) -> np.ndarray:
    """The distance to the segments; among the three nearest, blended smoothly (the fillets)."""
    ap = p[:, None, :] - a[None]
    t = np.clip(np.einsum("mso,so->ms", ap, ab) / largo2, 0.0, 1.0)
    d = np.linalg.norm(ap - t[..., None] * ab[None], axis=-1)
    if fillet <= 0 or d.shape[1] == 1:
        return d.min(axis=1)
    nearest = np.sort(np.partition(d, min(2, d.shape[1] - 1), axis=1)[:, :3], axis=1)
    field = _minimum_smooth(nearest[:, 0], nearest[:, 1], fillet)
    if nearest.shape[1] > 2:
        field = _minimum_smooth(field, nearest[:, 2], fillet)
    return field


def pipes(curves: Data, radius=1.0, fillet=None, detail=DETAIL, name: str | None = None) -> Data:
    """A tube around each curve, all fused into a single skin (*MultiPipe*).

    `fillet`: how much the joints are filled (0: tubes that simply cross); empty, half the radius.
    """
    if curves.kind is None or not curves.kind.curve:
        raise ShapeError(tr('“{name}” should be lines or curves.').format(name=curves._name()))
    radius = float(radius)
    if radius <= 0:
        raise ShapeError(tr('The pipe radius must be greater than 0 (it is {radius}).').format(radius=radius))
    fillet = radius / 2 if fillet is None else max(float(fillet), 0.0)
    runs = _runs(curves)
    if not len(runs):
        raise ShapeError(tr('“{name}” has no segment with length.').format(name=curves._name()))
    a, ab = runs[:, 0], runs[:, 1] - runs[:, 0]
    largo2 = np.einsum("so,so->s", ab, ab)
    step = radius / max(float(detail), 1.0)
    margin = radius + fillet / 2 + 2 * step          # the fillet fattens the joints a little
    minimum, maximum = runs.reshape(-1, 3).min(axis=0) - margin, runs.reshape(-1, 3).max(axis=0) + margin
    tally = np.ceil((maximum - minimum) / step).astype(int) + 1
    if np.prod(tally) > 6_000_000:
        raise ShapeError(tr('The pipes would be too fine for their size: lower the detail or raise the radius.'))
    xs, ys, zs = (minimum[i] + step * np.arange(tally[i]) for i in range(3))
    # VTK wants x the fastest: z, y, x from outside in.
    grid = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).transpose(2, 1, 0, 3).reshape(-1, 3)
    field = np.empty(len(grid))
    piece = max(1, 2_000_000 // len(runs))
    for i in range(0, len(grid), piece):
        field[i:i + piece] = _field(grid[i:i + piece], a, ab, largo2, fillet) - radius
    # The edge of the computation, always outside: the skin stays closed.
    block = field.reshape(tally[2], tally[1], tally[0])
    for edge in (block[0], block[-1], block[:, 0], block[:, -1], block[:, :, 0], block[:, :, -1]):
        np.maximum(edge, step, out=edge)

    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    image = vtk.vtkImageData()
    image.SetDimensions(*(int(c) for c in tally))
    image.SetSpacing(step, step, step)
    image.SetOrigin(*minimum)
    image.GetPointData().SetScalars(numpy_to_vtk(field, deep=True))
    skin = vtk.vtkFlyingEdges3D()
    skin.SetInputData(image)
    skin.SetValue(0, 0.0)
    skin.ComputeNormalsOff()
    skin.Update()
    mesh = skin.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData()).astype(float)
    triangles = vtk_to_numpy(mesh.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    # Outside, anticlockwise: the field grows outwards.
    triangles = triangles[:, ::-1]
    return Data(points, (), name, kind=kind_mesh(triangles))


#: How many points, at most, among all the spheres of a node (with more, each one gets coarser).
POINTS_SPHERES = 150_000


def sphere(centre=(0.0, 0.0, 0.0), radius=1.0, name: str | None = None) -> Data:
    """A sphere, as a surface. With many at once (the joints of a structure) each one carries fewer points: they are
    small and so the view does not get slow."""
    c, r = _point(centre, "centre"), _data(radius)
    how_many = max(int(np.prod(c.values.shape[:-1])), int(np.size(r.values)), 1)
    rows, columns = ROWS_SPHERE, COLUMNS_SPHERE
    while how_many * rows * columns > POINTS_SPHERES and rows > 7:
        rows, columns = (rows + 1) // 2, (columns + 1) // 2
    lat = np.linspace(-np.pi / 2, np.pi / 2, rows)[:, None]
    lon = np.linspace(0, 2 * np.pi, columns)[None, :]
    unit = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat) + 0 * lon], axis=-1).reshape(-1, 3)

    def points(c, r):
        return c[..., None, :] + np.asarray(r)[..., None, None] * unit

    return apply(points, c, r, name=name, kind=kind_surface(rows, columns))


def _triangles(geometry: Data) -> np.ndarray:
    """All the faces of a geometry (surface, box, mesh…), in triangles: (n, 3, 3)."""
    from .geometry import real_faces
    kind = geometry.kind
    if kind is None or kind.faces is None:
        raise ShapeError(tr('“{name}” should be a surface, a volume or a mesh (something with faces).').format(
                               name=geometry._name()))
    if not kind.polygon:                                     # the same faces for all: all at once
        fan = np.array([(face[0], face[j], face[j + 1]) for face in kind.faces for j in range(1, len(face) - 1)],
                       dtype=np.int64).reshape(-1, 3)
        elements = np.asarray(_elements(geometry), dtype=float)
        return elements[:, fan].reshape(-1, 3, 3)
    triangles = []
    for vertices in _elements(geometry):
        for face in real_faces(kind, vertices):
            for j in range(1, len(face) - 1):                # as a fan from the first vertex
                triangles.append(vertices[[face[0], face[j], face[j + 1]]])
    return np.array(triangles, dtype=float).reshape(-1, 3, 3)


def _cut(triangles: np.ndarray, d: np.ndarray, amplitude: float) -> np.ndarray:
    """The segments where the plane (distance `height` in direction d) cuts the triangles: (m, 2, 3)."""
    s = triangles @ d - amplitude                                 # (n, 3): on which side each vertex is
    s = np.where(s == 0, 1e-12, s)
    sides = s > 0
    cut = sides.any(axis=1) & ~sides.all(axis=1)
    t, s = triangles[cut], s[cut]
    runs = []
    for a, b in ((0, 1), (1, 2), (2, 0)):                       # in each triangle, two of its edges cross
        crosses = (s[:, a] > 0) != (s[:, b] > 0)
        f = s[:, a] / np.where(crosses, s[:, a] - s[:, b], 1.0)
        runs.append((np.where(crosses[:, None], t[:, a] + f[:, None] * (t[:, b] - t[:, a]), np.nan)))
    points = np.stack(runs, axis=1)                           # (m, 3 aristas, 3)
    valid = ~np.isnan(points[..., 0])
    if (valid.sum(axis=1) == 2).all():                         # (always, but for a vertex right on the plane)
        return points[valid].reshape(-1, 2, 3)
    return np.array([p[v][:2] for p, v in zip(points, valid)]).reshape(-1, 2, 3)


def _chain(runs: np.ndarray, tolerance: float) -> list[np.ndarray]:
    """Joins the loose segments into polylines (the closed ones repeat their first point at the end)."""
    rounded = np.round(runs.reshape(-1, 3) / tolerance).astype(np.int64)           # all at once
    keys = np.unique(rounded, axis=0, return_inverse=True)[1].reshape(-1).tolist()  # each end, a number
    neighbours: dict = {}
    for k, key in enumerate(keys):
        neighbours.setdefault(key, []).append((k // 2, k % 2))
    used = np.zeros(len(runs), dtype=bool)

    def follow(i: int, side: int) -> list[np.ndarray]:
        """From the end `side` of segment i, forwards while there is a segment that continues."""
        path = []
        while True:
            next_ = [(j, l) for j, l in neighbours[keys[2 * i + side]] if not used[j]]
            if not next_:
                return path
            j, l = next_[0]
            used[j] = True
            path.append(runs[j, 1 - l])
            i, side = j, 1 - l

    polylines = []
    for i in range(len(runs)):
        if used[i]:
            continue
        used[i] = True
        front = follow(i, 1)
        behind = follow(i, 0)
        points = [*reversed(behind), runs[i, 0], runs[i, 1], *front]
        polylines.append(np.array(points))
    return polylines


def level_curves(geometry: Data, distance=1.0, direction=(0.0, 0.0, 1.0), start=None,
                    level: str = "cut", name: str | None = None) -> Data:
    """Cuts a surface, a volume or a mesh with parallel planes, every `distance` (*Contour*).

        level_curves(cylinder, 2)  → [cut 11]: the rings at 0, 2, 4… 20 m

    The planes are perpendicular to `direction` (upwards: horizontal cuts, like the contour lines of a terrain).
    `start`: the height of the first cut; empty, the lowest point. Each cut piece is a curve of the new level, ordered
    from bottom to top.
    """
    d = np.asarray(_point(direction, "direction").values, dtype=float).reshape(-1, 3)[0]
    if np.linalg.norm(d) < 1e-12:
        raise ShapeError(tr('The direction of the cuts cannot be zero.'))
    d = d / np.linalg.norm(d)
    step = float(_data(distance).values)
    if not step > 0:
        raise ShapeError(tr('The distance between cuts must be greater than 0.'))
    triangles = _triangles(geometry)
    heights = triangles.reshape(-1, 3) @ d
    under, height = float(heights.min()), float(heights.max())
    size_ = max(float(np.ptp(triangles.reshape(-1, 3), axis=0).max()), 1e-9)
    from_ = under if start is None else float(_data(start).values)
    count = int(np.floor((height - from_) / step + 1e-9)) + 1
    if count > 10000:
        raise ShapeError(tr('That would give {n} cuts: increase the distance.').format(n=count))
    margin = size_ * 1e-6                                    # the first and the last, just inside the edge
    curves = []
    for k in range(max(count, 0)):
        amplitude = from_ + k * step
        if amplitude < under - margin or amplitude > height + margin:
            continue
        runs = _cut(triangles, d, min(max(amplitude, under + margin), height - margin))
        if len(runs):
            for c in _chain(runs, size_ * 1e-7):
                # Out with the almost repeated points (a cut right on an edge leaves them): tubes without streaks.
                far = np.r_[True, np.linalg.norm(np.diff(c, axis=0), axis=1) > size_ * 1e-4]
                c = c[far]
                if len(c) > 2 and np.linalg.norm(c[0] - c[-1]) <= size_ * 1e-4:
                    c[-1] = c[0]                             # closed: it ends right at its first point
                if len(c) >= 2:
                    curves.append(c)
    if not curves:
        raise ShapeError(tr('The cuts do not touch “{name}”.').format(name=geometry._name()))
    length = max(len(c) for c in curves)                      # the padding repeats the last point
    values = np.array([np.vstack([c, np.repeat(c[-1:], length - len(c), axis=0)]) for c in curves])
    return Data(values, (level,), name, kind=CURVE)


#: How many sides the section of a simple tube has.
SIDES_PIPE = 16


#: The sections of Tube: round (radius, sides), rectangular (width × height) or that of a drawn curve.
SECTIONS_PIPE = ('round', "rectangular", 'profile')


def _section_profile(profile) -> np.ndarray:
    """The (x, y) points of a curve drawn as a section: x goes towards the width and y towards the height of the
    piece; the origin (0, 0) is the axis of the piece."""
    if not isinstance(profile, Data) or profile.kind is None or not profile.kind.curve:
        raise ShapeError(tr('For the «profile» section, connect a curve (drawn around the origin, in plan).'))
    v = np.asarray(profile.values, float)
    if v.ndim != 2:
        raise ShapeError(tr('The section takes a single curve.'))
    q = v[:, :2]
    closed = bool(profile.kind.closed) or np.linalg.norm(q[0] - q[-1]) < 1e-9
    q = q[np.r_[True, np.linalg.norm(np.diff(q, axis=0), axis=1) > 1e-9]]            # without repeated points
    if closed and len(q) > 1 and np.linalg.norm(q[0] - q[-1]) < 1e-9:
        q = q[:-1]
    if len(q) < 2:
        raise ShapeError(tr('The section curve has no length.'))
    # Without the points that do not turn (a sampled straight line), and the corners twice: sharp edges.
    prev = np.roll(q, 1, axis=0) if closed else np.vstack([q[:1], q[:-1]])
    next_ = np.roll(q, -1, axis=0) if closed else np.vstack([q[1:], q[-1:]])
    a, b = q - prev, next_ - q
    na, nb = np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1)
    cosine = np.where((na > 0) & (nb > 0), (a * b).sum(1) / np.maximum(na * nb, 1e-300), -1.0)
    if not closed:
        cosine[[0, -1]] = -1.0                                  # the ends of an open one stay
    remains = cosine < 1 - 1e-6
    corner = cosine < np.cos(np.radians(30))
    points = []
    for point, k, e in zip(q, remains, corner):
        if k:
            points += [point, point] if e and (closed or len(points)) else [point]
    q = np.array(points)
    if closed:
        q = np.vstack([q, q[:1]])
    return q


def _triangulate_polygon(xy: np.ndarray) -> list[tuple[int, int, int]]:
    """The triangles of a simple polygon (its points anticlockwise, without repeating the first), by cutting ears:
    it also works for a concave one (an I, an L)."""
    remain = list(range(len(xy)))
    triangles = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    turns = 0
    while len(remain) > 3 and turns < 10 * len(xy):
        turns += 1
        for m in range(len(remain)):
            i, j, k = remain[m - 1], remain[m], remain[(m + 1) % len(remain)]
            a, b, c = xy[i], xy[j], xy[k]
            if cross(a, b, c) <= 1e-14:                          # it is not an ear (concave or aligned)
                continue
            if any(cross(a, b, xy[q]) >= 0 and cross(b, c, xy[q]) >= 0 and cross(c, a, xy[q]) >= 0
                   for q in remain if q not in (i, j, k) and not np.allclose(xy[q], (a, b, c)[0])):
                continue
            triangles.append((i, j, k))
            remain.pop(m)
            break
        else:
            break
    if len(remain) == 3:
        triangles.append(tuple(remain))
    return triangles


def pipe(curves: Data, radius=0.5, sides=SIDES_PIPE, name: str | None = None, section: str = 'round',
         width=0.3, height=0.5, profile=None, rotation=0.0, caps: bool = False) -> Data:
    """A tube along each curve (Grasshopper's *Pipe*), with a round, rectangular (`width` × `height`) section or that
    of a drawn curve (`profile`, around the origin, in plan: x towards the width, y towards the height). In a beam the
    width stays horizontal and the height vertical; in a column, the height goes towards the vertical axis of the origin
    (the centre of a tower). `rotation` turns the section (in degrees). With `caps`, each piece closes at its two ends and
    a closed mesh comes out (a body) instead of a surface (except on a closed curve: a hoop).

        tube(rings [cut 11], 0.3)  → [cut 11]: eleven hoops

    Unlike «Tubes», it fuses nothing: each curve gives its tube, fast and as fine as wanted. The section moves on
    without twisting (*parallel transport frame*).
    """
    if curves.kind is None or not curves.kind.curve:
        raise ShapeError(tr('“{name}” should be one or more curves.').format(name=curves._name()))
    if section not in SECTIONS_PIPE:
        raise ShapeError(tr('The section can be: {options}.').format(options=", ".join(tr(x) for x in SECTIONS_PIPE)))
    if section == 'round':
        r = float(_data(radius).values)
        if not r > 0:
            raise ShapeError(tr('The pipe radius must be greater than 0.'))
        n_sides = max(3, integer(sides))
        ang = np.linspace(0, 2 * np.pi, n_sides + 1)            # the last one repeats the first: it closes the seam
        xy = r * np.stack([np.cos(ang), np.sin(ang)], 1)
    elif section == "rectangular":
        a, h = float(_data(width).values) / 2, float(_data(height).values) / 2
        if not (a > 0 and h > 0):
            raise ShapeError(tr('The width and height of the section must be greater than 0.'))
        corners = np.array([(a, -h), (a, h), (-a, h), (-a, -h)])
        xy = np.vstack([np.repeat(corners, 2, axis=0)[1:], corners[:1]])   # each corner twice: sharp edges
    else:
        xy = _section_profile(profile)
    g = np.radians(float(_data(rotation).values))
    if g:
        xy = xy @ np.array([[np.cos(g), np.sin(g)], [-np.sin(g), np.cos(g)]])
    closed_section = len(xy) > 3 and np.linalg.norm(xy[0] - xy[-1]) < 1e-9
    if closed_section:                                         # anticlockwise: the skin faces outwards
        x, y = xy[:, 0], xy[:, 1]
        if (x[:-1] * y[1:] - x[1:] * y[:-1]).sum() < 0:
            xy = xy[::-1].copy()
    p = curves.values
    if curves.kind.closed:                                     # the closed one goes back to its first point
        p = np.concatenate([p, p[..., :1, :]], axis=-2)
    n = p.shape[-2]
    closed = np.linalg.norm(p[..., 0, :] - p[..., -1, :], axis=-1) < 1e-9
    # The direction of each segment; one of length 0 (the padding) follows the previous one (or the next, at the start).
    run = np.diff(p, axis=-2)
    length_t = np.linalg.norm(run, axis=-1, keepdims=True)
    run = run / np.maximum(length_t, 1e-300)
    empty = length_t[..., 0] <= 1e-12
    for i in range(1, n - 1):
        run[..., i, :] = np.where(empty[..., i, None], run[..., i - 1, :], run[..., i, :])
        empty[..., i] &= empty[..., i - 1]
    for i in range(n - 3, -1, -1):
        run[..., i, :] = np.where(empty[..., i, None], run[..., i + 1, :], run[..., i, :])
    # At each point, what arrives and what leaves; the tangent goes along the bisector (the mitre).
    enters = np.concatenate([run[..., :1, :], run], axis=-2)
    comes_out = np.concatenate([run, run[..., -1:, :]], axis=-2)
    enters[..., 0, :] = np.where(closed[..., None], run[..., -1, :], enters[..., 0, :])
    comes_out[..., -1, :] = np.where(closed[..., None], run[..., 0, :], comes_out[..., -1, :])
    tangents = enters + comes_out
    length = np.linalg.norm(tangents, axis=-1, keepdims=True)
    tangents = np.where(length > 1e-9, tangents / np.maximum(length, 1e-300), comes_out)
    # The first normal: any perpendicular to the first tangent; then, it is transported.
    t0 = tangents[..., 0, :]
    # Reference: the vertical; in an almost vertical piece, the direction towards the vertical axis of the origin (in a
    # centred tower, the section faces the centre), or x if it is on that axis.
    radial = np.concatenate([p[..., 0, :2], np.zeros_like(p[..., 0, :1])], axis=-1)
    length_r = np.linalg.norm(radial, axis=-1, keepdims=True)
    radial = np.where(length_r > 1e-9, radial / np.maximum(length_r, 1e-12), [1.0, 0.0, 0.0])
    axis = np.where(np.abs(t0[..., 2:3]) < 0.9, [0.0, 0.0, 1.0], radial)
    normals = np.empty_like(tangents)
    normal = np.cross(t0, axis)
    for i in range(n):
        t = tangents[..., i, :]
        normal = normal - (normal * t).sum(axis=-1, keepdims=True) * t
        normal = normal / np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-12)
        normals[..., i, :] = normal
    # On a closed curve, the normal does not come back exactly to the starting one (the transport turns a little):
    # that turn is spread along the curve, so the last section is the first and there is no seam.
    if closed.any():
        first, final, t_end = normals[..., 0, :], normals[..., -1, :], tangents[..., -1, :]
        rotation = np.arctan2((np.cross(final, first) * t_end).sum(axis=-1), (final * first).sum(axis=-1))
        rotation = np.where(closed, rotation, 0.0)[..., None] * np.linspace(0, 1, n)          # (…, n)
        b = np.cross(tangents, normals)
        normals = np.cos(rotation)[..., None] * normals + np.sin(rotation)[..., None] * b
    binormals = np.cross(tangents, normals)
    cut = (xy[:, 0, None] * normals[..., :, None, :] + xy[:, 1, None] * binormals[..., :, None, :])
    # Mitre: where the curve breaks, the section stretches towards the break (1 / cos of half the angle), so the
    # piece is not pinched at the joint of two segments.
    kink = comes_out - enters
    length_q = np.linalg.norm(kink, axis=-1, keepdims=True)
    direction_q = kink / np.maximum(length_q, 1e-300)
    middle = np.sqrt(np.clip((1 + (enters * comes_out).sum(axis=-1, keepdims=True)) / 2, 0, 1))
    stretch = np.where(length_q > 1e-9, 1 / np.maximum(middle, 0.3) - 1, 0.0)          # (…, n, 1)
    cut = cut + (stretch[..., None] * (cut * direction_q[..., None, :]).sum(-1, keepdims=True)
                     * direction_q[..., None, :])
    values = p[..., :, None, :] + cut                      # (…, n, points of the section, 3)
    values[..., -1, :, :] = np.where(closed[..., None, None], values[..., 0, :, :], values[..., -1, :, :])
    k = len(xy)
    values = values.reshape(values.shape[:-3] + (n * k, 3))
    if not (caps and closed_section and not curves.kind.closed):
        return curves.derived(values, name, kind_surface(n, k))
    # With caps: a closed mesh (the skin in triangles and the two ends, triangulating the section once).
    unique = [j for j in range(k - 1) if j == 0 or np.linalg.norm(xy[j] - xy[j - 1]) > 1e-12]
    if np.linalg.norm(xy[unique[-1]] - xy[0]) < 1e-12:
        unique = unique[:-1]
    cap = [(unique[a], unique[b], unique[c]) for a, b, c in _triangulate_polygon(xy[unique])]
    # A single index per point of the section (the repeated corners and the seam, to the first): so the mesh is
    # watertight by indices too (for exporting and for the booleans); the zero-length triangles, out.
    canon, last = [], 0
    for j in range(k):
        if j and np.linalg.norm(xy[j] - xy[j - 1]) > 1e-12:
            last = j
        canon.append(last)
    canon = [0 if np.linalg.norm(xy[j] - xy[0]) < 1e-12 else canon[j] for j in range(k)]
    faces = []
    for i in range(n - 1):
        for j in range(k - 1):
            a, b = i * k + canon[j], i * k + canon[j + 1]
            c, d = (i + 1) * k + canon[j + 1], (i + 1) * k + canon[j]
            faces += [t for t in ((a, b, c), (a, c, d)) if len(set(t)) == 3]
    final = (n - 1) * k
    faces += [(a, c, b) for a, b, c in cap]                    # the starting one faces backwards
    faces += [(final + a, final + b, final + c) for a, b, c in cap]
    return curves.derived(values, name, kind_mesh(faces))


# --- Booleanas: unir, restar, intersecar cuerpos cerrados ------------------------------------------

#: The boolean operations between closed bodies.
OPERATIONS_BOOLEANS = ('union', 'difference', 'intersection')


def _folded(kind, p: np.ndarray) -> bool:
    """Whether a face of the element folds over itself: its triangles (a fan from its first corner) face opposite
    ways, as in a «bow tie». The boolean library takes such a body without complaint and then never ends, or breaks
    and takes the calculation with it (a wall of cells with its block at 0: the cores, morphed into corners in the
    wrong order, pinched through themselves)."""
    from .measures import real_faces
    faces = real_faces(kind, p) if kind.polygon else kind.faces
    by_length: dict[int, list] = {}
    for face in faces:
        if len(face) >= 4:
            by_length.setdefault(len(face), []).append(face)
    size_ = float(np.ptp(p.reshape(-1, 3), axis=0).max()) if p.size else 0.0
    smallest = (size_ * 1e-6) ** 2
    for length, group in by_length.items():
        corners = p.reshape(-1, 3)[np.array(group, dtype=np.int64)]          # (faces, length, 3)
        normals = np.cross(corners[:, 1:-1] - corners[:, :1], corners[:, 2:] - corners[:, :1])
        sizes = np.linalg.norm(normals, axis=2)
        largest = normals[np.arange(len(group)), sizes.argmax(axis=1)]
        cosine = np.einsum("ftk,fk->ft", normals, largest) / np.maximum(sizes * sizes.max(axis=1)[:, None], 1e-300)
        if ((sizes > smallest) & (cosine < -0.5)).any():
            return True
    return False


def _body(geometry: Data, role: str):
    """All the elements of a data (boxes, prisms, extrusions with caps, tubes…) as a single manifold3d body (joined)."""
    from manifold3d import Manifold, Mesh64

    from .measures import _closed, _triangles
    kind = geometry.kind if isinstance(geometry, Data) else None
    if kind is None or kind.faces is None:
        raise ShapeError(tr('“{role}” should be a closed body (a box, a prism, an extrusion with caps, some pipes).').format(role=tr(role)))
    pieces = []
    for p in _elements(geometry):
        t = _triangles(kind, p)
        size_ = float(np.ptp(p.reshape(-1, 3), axis=0).max()) if p.size else 0.0
        if not len(t) or not _closed(t, size_):
            raise ShapeError(tr('“{name}” is not a closed body: booleans only work with bodies without gaps '
                                  '(a box, a prism, an extrusion with caps: yes).').format(
                                      name=geometry._name()))
        keys = np.round(t.reshape(-1, 3) / max(size_ * 1e-9, 1e-12)).astype(np.int64)
        _, first, indices = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        vertices = t.reshape(-1, 3)[first]
        triangles = indices.reshape(-1, 3)
        if _folded(kind, p):
            raise ShapeError(tr('“{name}” folds over itself: some of its faces turn inside out (corners in the wrong '
                                'order, a negative size), and a boolean cannot tell its inside from its outside.'
                                ).format(name=geometry._name()))
        # Outwards (manifold requires it): if the volume comes out negative, they are flipped.
        a, b, c = (vertices[triangles[:, k]] for k in range(3))
        if np.einsum("ij,ij->i", a, np.cross(b, c)).sum() < 0:
            triangles = triangles[:, ::-1]
        body = Manifold(Mesh64(vert_properties=np.ascontiguousarray(vertices, dtype=np.float64),
                                 tri_verts=np.ascontiguousarray(triangles, dtype=np.uint64)))
        if body.status().name != "NoError":
            raise ShapeError(tr('“{name}” could not be used as a closed body ({state}).').format(
                                   name=geometry._name(), state=body.status().name))
        pieces.append(body)
    return Manifold.batch_boolean(pieces, __import__("manifold3d").OpType.Add) if len(pieces) > 1 else pieces[0]


def boolean(a: Data, b: Data, operation: str = 'difference', name: str | None = None) -> Data:
    """Joins, subtracts or intersects closed bodies (*Solid Union / Difference / Intersection*):

    - «union»: all together, in a single skin (two volumes that cross);
    - «difference»: `a` minus `b` (a wall minus its openings);
    - «intersection»: only what they have in common.

    All the elements of `a` (and of `b`) count together; the result is a single body.
    """
    if operation not in OPERATIONS_BOOLEANS:
        raise ShapeError(tr('The operation must be one of: {options}.').format(
                               options=", ".join(tr(o) for o in OPERATIONS_BOOLEANS)))
    try:
        import manifold3d  # noqa: F401
    except ImportError:
        raise ShapeError(tr('Booleans need the manifold3d library (pip install manifold3d).')) from None
    ca, cb = _body(a, "a"), _body(b, "b")
    result = ca + cb if operation == 'union' else (ca - cb if operation == 'difference' else ca ^ cb)
    if result.is_empty():
        raise ShapeError(tr('Nothing is left after the {operation}: do “{a}” and “{b}” touch?').format(
                               operation=tr(operation), a=a._name(), b=b._name()))
    mesh = result.to_mesh64()
    vertices = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
    triangles = np.asarray(mesh.tri_verts, dtype=np.int64)
    result = Data(vertices, (), name, kind=kind_mesh(triangles))
    # Its triangles say nothing of the form (the diagonals of each flat face): the view draws its outlines only,
    # whatever its size (before, a small result showed every diagonal and a big one did not).
    result.topology = False
    return result


# --- Ribs: a shape, cut into parallel boards -----------------------------------------------

#: The axes of the cuts. «x»: vertical ribs along X (a wall that faces south); «y»: along
#: Y; «z»: horizontal slices (slabs, a bench in layers).
AXES_RIBS = ("x", "y", "z")
#: How many points the front of each rib has (all the same number, so they are a single data).
POINTS_BY_RIB = 80


def _resample(p: np.ndarray, count: int) -> np.ndarray:
    """A polyline with `count` points spread along its length."""
    lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    if lengths[-1] <= 0:
        return np.repeat(p[:1], count, axis=0)
    t = np.linspace(0, lengths[-1], count)
    return np.stack([np.interp(t, lengths, p[:, k]) for k in range(3)], axis=1)


def ribs(shape: Data, count=30, weight=0.02, cuts: str = "x", back=0.0,
              name: str | None = None) -> Data:
    """Cuts a shape (a surface, a mesh, a volume) into parallel boards (*contour ribs*, louvres):

    - `count` ribs spread along the axis `cuts` (from end to end of the shape);
    - each one, the cut of the shape closed against the plane of the **back** (the wall: y = `back` if cut in x or in z;
      x = `back` if cut in y), extruded to the `thickness` of the board.

    A rib wall: three wavy curves, a Loft surface and Ribs.
    """
    if cuts not in AXES_RIBS:
        raise ShapeError(tr('Cuts go along x, y or z (got “{cuts}”).').format(cuts=cuts))
    n = integer(count)
    if n < 1:
        raise ShapeError(tr('At least 1 rib is needed.'))
    g = float(_data(weight).values)
    if not g > 0:
        raise ShapeError(tr('The rib thickness must be greater than 0.'))
    depth_in = float(_data(back).values)
    axis = "xyz".index(cuts)
    deep = 0 if cuts == "y" else 1                       # where they stick out: y (or x, if cut in y)
    height = 2 if cuts != "z" else 0                           # along what each profile is ordered
    triangles = _triangles(shape)
    p = triangles.reshape(-1, 3)
    under, above = float(p[:, axis].min()), float(p[:, axis].max())
    if above - under < 1e-9:
        raise ShapeError(tr('“{name}” has no length in {axis}: there is nowhere to cut.').format(
                               name=shape._name(), axis=cuts))
    size_ = float(np.ptp(p, axis=0).max())
    half = min(g / 2, (above - under) / 2)
    positions = np.linspace(under + half, above - half, n) if n > 1 else np.array([(under + above) / 2])
    normal = np.zeros(3)
    normal[axis] = 1.0
    # Each rib is closed against the back wall: the shape has to stay on one side of it, or the rib folds over itself.
    side = p[:, deep] - depth_in
    if side.min() < -size_ * 1e-6 and side.max() > size_ * 1e-6:
        # The wall suggested just outside the shape, on the side it crosses the least, with a small margin and rounded
        # outwards: written as it is, the ribs come out.
        margin = max(0.01, 0.01 * size_)
        if abs(side.max()) < abs(side.min()):
            behind = math.ceil((p[:, deep].max() + margin) * 100) / 100
        else:
            behind = math.floor((p[:, deep].min() - margin) * 100) / 100
        raise ShapeError(tr('“{name}” crosses the back wall ({wall} = {back}): each rib is closed against that wall, so '
                            'the shape has to stay on one side of it. Move “back” out of the shape, for example to '
                            '{suggest}.').format(name=shape._name(), wall="xyz"[deep], back=round(depth_in, 3),
                                                 suggest=f"{behind:.2f}"))
    profiles = []
    for x in positions:
        runs = _cut(triangles, normal, x)
        pieces = _chain(runs, size_ * 1e-7) if len(runs) else []
        if not pieces:
            raise ShapeError(tr('A cut does not touch “{name}” (at {axis} = {x}).').format(
                                   name=shape._name(), axis=cuts, x=round(float(x), 3)))
        front = max(pieces, key=lambda c: np.linalg.norm(np.diff(c, axis=0), axis=1).sum())   # the longest piece
        if front[0, height] > front[-1, height]:                   # from bottom to top
            front = front[::-1]
        front = _resample(front, POINTS_BY_RIB)
        back_ = front[::-1].copy()                           # the back: the same profile, against the wall
        back_[:, deep] = depth_in
        outline = np.concatenate([front, back_])
        outline[:, axis] = x - g / 2                             # each board, from its face
        profiles.append(outline)
    from .geometry import CLOSED_CURVE, extrude
    curves = Data(np.array(profiles), ("rib",), None, kind=CLOSED_CURVE)
    vector = [0.0, 0.0, 0.0]
    vector[axis] = g
    return extrude(curves, tuple(vector), name, caps=True)


# --- Surface by points (SrfGrid, and a point cloud of a terrain) --------------------------------

#: How the points join: an ordered grid (rows × columns) or a loose cloud (a survey).
MODES_SURFACE_POINTS = ('grid', 'cloud')


def surface_by_points(points: Data, mode: str = 'grid', smooth: bool = False,
                          name: str | None = None) -> Data:
    """A surface through some points (*Surface from Points*, *SrfGrid*; and *Delaunay* for a cloud):

    - «grid»: the points come ordered in **rows × columns** (their two last levels: two Series with different names).
      With `smooth`, the surface curves between them instead of going by facets.
    - «cloud»: loose points, in any order (those of a topographic survey): they join into triangles seen from above. It
      gives a mesh: a terrain, from which its contour lines can be taken. With `smooth`, each triangle curves (it still
      passes through the points), instead of staying as flat facets.
    """
    from .geometry import _catmull_rom, smooth_count
    if points.kind is not POINT:
        raise ShapeError(tr('“{name}” should be some points.').format(name=points._name()))
    if mode not in MODES_SURFACE_POINTS:
        raise ShapeError(tr('The mode must be “grid” or “cloud”.'))
    if mode == 'grid':
        if len(points.levels) < 2:
            raise ShapeError(tr('For a grid surface, the points need rows × columns: two levels (for example, '
                                  'two Series with different names, one in x and one in y). If they are loose, '
                                  'use the “cloud” mode.'))
        rows, columns = points.sizes[points.levels[-2]], points.sizes[points.levels[-1]]
        if rows < 2 or columns < 2:
            raise ShapeError(tr('At least 2 rows and 2 columns of points are needed.'))
        v = np.asarray(points.values, dtype=float)                               # (…, f, c, 3)
        if smooth:                                 # how big it becomes, before making it (it ran out of memory)
            kind_surface(smooth_count(rows, False), smooth_count(columns, False))
            v = _catmull_rom(v, False)                                             # along the columns
            v = np.swapaxes(_catmull_rom(np.swapaxes(v, -2, -3), False), -2, -3)   # and the rows
            rows, columns = v.shape[-3], v.shape[-2]
        remain = points.levels[:-2]
        values = v.reshape(v.shape[:-3] + (rows * columns, 3))
        holes = None
        if points.holes is not None:
            h = np.broadcast_to(points.holes, points.values.shape[:len(points.levels)])
            holes = h.reshape(h.shape[:-2] + (-1,)).any(axis=-1) if remain else None
        return Data(values, remain, name, {k: c for k, c in points.variables.items() if k in remain},
                    {k: i for k, i in points.starts.items() if k in remain}, kind_surface(rows, columns), holes)
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    p = np.asarray(_elements(points) if points.levels else points.values[None], dtype=float).reshape(-1, 3)
    if len(p) < 3:
        raise ShapeError(tr('A surface needs at least 3 points.'))
    cloud = vtk.vtkPolyData()
    vtk_points = vtk.vtkPoints()
    order = vtk.nearby_order(p[:, :2])                       # each point near the one before: much faster
    vtk_points.SetData(numpy_to_vtk(np.ascontiguousarray(p[order]), deep=True))
    cloud.SetPoints(vtk_points)
    delaunay = vtk.vtkDelaunay2D()                                                 # in plan (x, y)
    delaunay.SetInputData(cloud)
    delaunay.SetOffset(1000.0)   # a larger enclosing triangle: with a smaller one, thin triangles on the outline were lost
    delaunay.Update()
    output = delaunay.GetOutput()
    if output.GetNumberOfPolys() == 0:
        raise ShapeError(tr('The points are in a line (seen from above): they do not form a surface.'))
    cells = order[vtk_to_numpy(output.GetPolys().GetConnectivityArray()).reshape(-1, 3)]   # in the points' own order
    vertices = p.copy()
    if smooth:
        vertices, cells = _smooth_terrain(vertices, cells)
    return Data(vertices, (), name, kind=kind_mesh(cells))


def _smooth_terrain(p: np.ndarray, tri: np.ndarray, parts: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Each triangle of a terrain in parts² triangles, curved (a cubic Bézier triangle in height, with the slope of
    each vertex): it still passes through the measured points, and in plan nothing changes (the edge stays where it
    was). Two neighbouring triangles share their curved edge: no cracks are left."""
    # The slope at each vertex: the average of the normals of its triangles (weighted by their area).
    a, b, c = p[tri[:, 0]], p[tri[:, 1]], p[tri[:, 2]]
    normal = np.cross(b - a, c - a)
    normal[normal[:, 2] < 0] *= -1
    total = np.zeros_like(p)
    for k in range(3):
        np.add.at(total, tri[:, k], normal)
    nz = np.where(np.abs(total[:, 2]) > 1e-12, total[:, 2], 1e-12)
    pending = -total[:, :2] / nz[:, None]                                   # (dz/dx, dz/dy) at each vertex

    def control(i, j):   # the control point of the edge i→j, a third from i
        return p[i, 2] + (pending[i] * (p[j, :2] - p[i, :2])).sum(-1) / 3

    i0, i1, i2 = tri[:, 0], tri[:, 1], tri[:, 2]
    z0, z1, z2 = p[i0, 2], p[i1, 2], p[i2, 2]
    b210, b120 = control(i0, i1), control(i1, i0)
    b021, b012 = control(i1, i2), control(i2, i1)
    b102, b201 = control(i2, i0), control(i0, i2)
    e = (b210 + b120 + b021 + b012 + b102 + b201) / 6
    b111 = e + (e - (z0 + z1 + z2) / 3) / 2

    # The subdivision of a triangle, in barycentric coordinates.
    n = parts
    ijk = np.array([(n - i - j, i, j) for i in range(n + 1) for j in range(n + 1 - i)], dtype=float) / n
    index = {(i, j): k for k, (i, j) in enumerate((i, j) for i in range(n + 1) for j in range(n + 1 - i))}
    small = []
    for i in range(n):
        for j in range(n - i):
            small.append((index[i, j], index[i + 1, j], index[i, j + 1]))
            if i + j < n - 1:
                small.append((index[i + 1, j], index[i + 1, j + 1], index[i, j + 1]))
    small = np.array(small)
    u, v, w = ijk[:, 0][None], ijk[:, 1][None], ijk[:, 2][None]          # u: vertex 0, v: 1, w: 2
    xy = u[..., None] * a[:, None, :2] + v[..., None] * b[:, None, :2] + w[..., None] * c[:, None, :2]
    col = lambda x: x[:, None]
    z = (col(z0) * u ** 3 + col(z1) * v ** 3 + col(z2) * w ** 3
         + 3 * (col(b210) * u * u * v + col(b120) * u * v * v + col(b021) * v * v * w
                + col(b012) * v * w * w + col(b102) * w * w * u + col(b201) * u * u * w)
         + 6 * col(b111) * u * v * w)
    points = np.concatenate([xy, z[..., None]], axis=-1).reshape(-1, 3)
    cells = (small[None] + (np.arange(len(tri)) * len(ijk))[:, None, None]).reshape(-1, 3)
    # Weld the repeated vertices on the shared edges.
    key = np.round(points, 7)
    unique, which = np.unique(key, axis=0, return_inverse=True)
    return unique, which.reshape(-1)[cells]
