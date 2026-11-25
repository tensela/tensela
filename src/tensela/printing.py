"""Can it be printed? What a 3D printer needs from a piece, checked piece by piece.

The geometry (G1 to G4): **closed** (watertight: no edge with a single face), **manifold** (no edge shared
by more than two faces), **its faces turned the same way and outwards**, and **not crossing itself**. The machine
(C1, C2): it **fits** in the printer, and its walls are **not thinner** than what the printer can make.

    report = check(pieces, printer=(0.2, 0.2, 0.2), thickness=0.0008)

Each piece is welded first (the vertices that fall on one another become one), as a slicer does when it reads an
STL: so two faces that touch along an edge share it, whatever node made them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .data import Data, ShapeError
from .geometry import BOX, CURVE, POINT
from .language import tr
from .measures import _elements, _triangles

#: Looking for crossings compares faces that are close together: in blocks of this many pairs (the memory stays
#: low), and not at all beyond MAX_PAIRS (a piece with so many faces crowded together is said, not checked).
PAIRS_PER_BLOCK = 2_000_000
MAX_PAIRS = 60_000_000
MAX_ENTRIES = 20_000_000


class TooCrowded(Exception):
    """Too many faces close together to look for crossings in a reasonable time and memory."""


#: How many faces at most are tested for the wall thickness (spread over the piece): enough to find a thin wall
#: without making a fine mesh slow.
THICKNESS_SAMPLES = 1500


@dataclass
class Piece:
    """A piece ready to be checked or written to a file: its welded vertices and its triangles."""

    vertices: np.ndarray                   # (n, 3)
    triangles: np.ndarray                  # (m, 3) indices
    label: str = ""                        # where it is in the levels («piece 3»), for the report
    index: tuple = ()                      # its place in the levels of the data it comes from


@dataclass
class Report:
    """What the check found in one piece: each problem with its lines in the view (segments, (k, 2, 3))."""

    label: str
    index: tuple = ()
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)          # what could not be checked (not a problem)
    marks: list[np.ndarray] = field(default_factory=list)
    size: tuple[float, float, float] = (0.0, 0.0, 0.0)
    thinnest: float | None = None

    @property
    def ready(self) -> bool:
        return not self.problems


def pieces(data: Data, what: str = 'print') -> list[Piece]:
    """The elements of a geometry with faces (meshes, surfaces, bodies), each as a welded piece of triangles."""
    kind = data.kind
    if kind is None or kind is POINT or kind.curve:
        what_it_is = tr('“{kind}”').format(kind=tr(kind.name)) if kind is not None else tr('a number')
        raise ShapeError(tr('“{name}” cannot be printed: it is {what}, not a geometry with faces (a body, a mesh, '
                            'a surface).').format(name=data._name(), what=what_it_is))
    result = []
    for index, p in _elements(data):
        t = _triangles(kind, p)
        if not len(t):
            continue
        vertices, triangles = weld(t)
        label = ", ".join(f"{tr(n)} {i + data.starts.get(n, 0)}" for n, i in zip(data.levels, index))
        result.append(Piece(vertices, triangles, label, index))
    return result


def weld(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Triangles (m, 3, 3) as shared vertices and indices; those left without area (two corners welded) go out."""
    flat = t.reshape(-1, 3)
    size = float(np.ptp(flat, axis=0).max()) if len(flat) else 0.0
    keys = np.round(flat / max(size * 1e-7, 1e-12)).astype(np.int64)
    _, first, ids = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    vertices = flat[first]
    triangles = ids.reshape(-1, 3)
    keep = (triangles[:, 0] != triangles[:, 1]) & (triangles[:, 1] != triangles[:, 2]) & \
        (triangles[:, 2] != triangles[:, 0])
    return vertices, triangles[keep]


def check(items: list[Piece], printer=(0.2, 0.2, 0.2), thickness: float = 0.0008) -> list[Report]:
    """The report of each piece: what keeps it from being printed (nothing, if it is ready)."""
    return [_check_one(piece, printer, thickness) for piece in items]


def _check_one(piece: Piece, printer, thickness: float) -> Report:
    from .values import text_length
    v, t = piece.vertices, piece.triangles
    size = tuple(float(x) for x in np.ptp(v, axis=0)) if len(v) else (0.0, 0.0, 0.0)
    report = Report(piece.label, piece.index, size=size)
    edges = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    unique, counts = _unique_pairs(edges, len(v))

    open_ = unique[counts == 1]
    if len(open_):
        report.problems.append(tr('it is not closed: {n} edges have a face on one side only (it lets the inside '
                                  'out). Close it with a cap, or give a surface its thickness.').format(n=len(open_)))
        report.marks.append(v[open_])
    many = unique[counts > 2]
    if len(many):
        report.problems.append(tr('{n} edges are shared by more than two faces (it is not manifold): two bodies '
                                  'that only touch at an edge, or faces left over. Join them with a Boolean '
                                  'union.').format(n=len(many)))
        report.marks.append(v[many])

    # The faces, all turned the same way: each edge is gone along once in each direction.
    directed = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    _, directed_counts = _unique_pairs(directed, len(v))
    closed = not len(open_) and not len(many)
    if (directed_counts > 1).any():
        closed = False                              # (the thickness is measured inwards: not knowing where in is)
        report.problems.append(tr('its faces are not all turned the same way: some look inwards. Flip faces '
                                  'can turn them.'))
    elif closed and _signed_volume(v, t) < 0:
        closed = False
        report.problems.append(tr('its faces look inwards (it is turned inside out): Flip faces turns them '
                                  'outwards.'))

    try:
        crossings = self_crossings(v, t)
    except TooCrowded:
        crossings = np.zeros((0, 2, 3))
        report.notes.append(tr('Crossings were not looked for: it has too many faces close together (long thin '
                               'faces, or a very fine mesh). The other checks were made.'))
    if len(crossings):
        report.problems.append(tr('it crosses itself (along the red lines): parts that go through others without '
                                  'being joined. Join them with a Boolean union, or separate them.'))
        report.marks.append(crossings)

    if printer is not None:
        fits = all(s <= p + 1e-9 for s, p in zip(size, printer))
        turned = all(s <= p + 1e-9 for s, p in zip(sorted(size), sorted(printer)))
        if not fits:
            measures = " × ".join(text_length(s) for s in size)
            room = " × ".join(text_length(float(p)) for p in printer)
            report.problems.append(
                tr('it measures {size} and the printer takes {room}: it fits if it is laid down another way.')
                .format(size=measures, room=room) if turned else
                tr('it measures {size} and the printer takes {room}: it does not fit. Scale it down, or divide it '
                   'into parts that are put together afterwards.').format(size=measures, room=room))

    if closed and thickness and thickness > 0:
        thinnest, thin = wall_thickness(v, t, thickness)
        report.thinnest = thinnest
        if len(thin):
            report.problems.append(tr('in {n} places its wall is thinner than {minimum} (the thinnest, {thinnest}): '
                                      'the printer cannot make it. Thicken it there.').format(
                n=len(thin), minimum=text_length(thickness), thinnest=text_length(thinnest)))
            report.marks.append(thin)
    return report


def _unique_pairs(pairs: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """np.unique of rows of two indices below `n`, much faster: each row as one number."""
    keys, counts = np.unique(pairs[:, 0].astype(np.int64) * n + pairs[:, 1], return_counts=True)
    return np.stack([keys // n, keys % n], axis=1), counts


def _signed_volume(v: np.ndarray, t: np.ndarray) -> float:
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


def self_crossings(v: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Where the piece goes through itself: for each pair of faces that cross (and share no corner), the segment of
    their crossing, (k, 2, 3)."""
    if len(t) < 4:
        return np.zeros((0, 2, 3))
    corners = v[t]                                                   # (m, 3, 3)
    low, high = corners.min(axis=1), corners.max(axis=1)
    span = float(np.ptp(v, axis=0).max()) or 1.0
    # Faces sorted into cells of a grid the size of a typical face: only faces in the same cell are compared.
    cell = max(float(np.median(np.max(high - low, axis=1))) * 2, span * 1e-6)
    origin = v.min(axis=0)
    a = np.floor((low - origin) / cell).astype(np.int64)
    b = np.floor((high - origin) / cell).astype(np.int64)
    entries_face, entries_key = [], []
    reach = np.maximum(b - a + 1, 1)
    if int(np.prod(reach, axis=1).max()) > 64:                          # a huge face among small ones: coarser grid
        cell *= float(np.prod(reach, axis=1).max()) ** (1 / 3)
        a = np.floor((low - origin) / cell).astype(np.int64)
        b = np.floor((high - origin) / cell).astype(np.int64)
    if int(np.prod(np.maximum(b - a + 1, 1), axis=1, dtype=np.int64).sum()) > MAX_ENTRIES:
        raise TooCrowded(0)
    for dx in range(int((b - a)[:, 0].max()) + 1):
        for dy in range(int((b - a)[:, 1].max()) + 1):
            for dz in range(int((b - a)[:, 2].max()) + 1):
                d = np.array([dx, dy, dz])
                ok = np.all(a + d <= b, axis=1)
                idx = np.nonzero(ok)[0]
                c = a[idx] + d
                entries_face.append(idx)
                entries_key.append(c)
    faces = np.concatenate(entries_face)
    keys = np.concatenate(entries_key)
    order = np.lexsort((faces, keys[:, 2], keys[:, 1], keys[:, 0]))
    faces, keys = faces[order], keys[order]
    new_cell = np.r_[True, np.any(keys[1:] != keys[:-1], axis=1)]
    starts = np.nonzero(new_cell)[0]
    ends = np.r_[starts[1:], len(faces)]
    # Every pair inside each cell: each entry with those after it in its cell. In blocks of entries, so the memory
    # stays bounded however many faces crowd together.
    end_of = np.repeat(ends, ends - starts)
    partners = end_of - np.arange(len(faces)) - 1
    total = int(partners.sum())
    if total == 0:
        return np.zeros((0, 2, 3))
    if total > MAX_PAIRS:
        raise TooCrowded(total)
    segments = []
    cumulative = np.cumsum(partners)
    begin = 0
    while begin < len(faces):
        limit = (cumulative[begin - 1] if begin else 0) + PAIRS_PER_BLOCK
        end = max(int(np.searchsorted(cumulative, limit, side="right")), begin + 1)
        block = np.arange(begin, end)
        m = partners[block]
        count = int(m.sum())
        begin = end
        if count == 0:
            continue
        first = np.repeat(block, m)
        second = first + 1 + (np.arange(count) - np.repeat(np.cumsum(m) - m, m))
        p, q = faces[first], faces[second]
        # Each pair once: in the first cell both share (and not again in the others). Out: pairs whose boxes do
        # not touch, and neighbours (a shared corner is not a crossing).
        keep = np.all(keys[first] == np.maximum(a[p], a[q]), axis=1)
        keep &= np.all((low[p] <= high[q]) & (low[q] <= high[p]), axis=1)
        p, q = p[keep], q[keep]
        shared = (t[p][:, :, None] == t[q][:, None, :]).any(axis=(1, 2))
        p, q = p[~shared], q[~shared]
        if len(p):
            segments.append(_crossing_segments(corners[p], corners[q], span))
    return np.concatenate(segments) if segments else np.zeros((0, 2, 3))


def _crossing_segments(A: np.ndarray, B: np.ndarray, span: float) -> np.ndarray:
    """For pairs of triangles (k, 3, 3) and (k, 3, 3): the segment where each pair crosses (only those that do)."""
    hits = []                                       # for each pair, up to 6 points: edges of one through the other
    for X, Y in ((A, B), (B, A)):
        for i in range(3):
            o, d = X[:, i], X[:, (i + 1) % 3] - X[:, i]
            point, ok = _edge_through(o, d, Y, span)
            hits.append((point, ok))
    points = np.stack([h[0] for h in hits], axis=1)          # (k, 6, 3)
    ok = np.stack([h[1] for h in hits], axis=1)              # (k, 6)
    crossing = ok.sum(axis=1) >= 2
    points, ok = points[crossing], ok[crossing]
    if not len(points):
        return np.zeros((0, 2, 3))
    first = np.argmax(ok, axis=1)
    last = ok.shape[1] - 1 - np.argmax(ok[:, ::-1], axis=1)
    rows = np.arange(len(points))
    return np.stack([points[rows, first], points[rows, last]], axis=1)


def _edge_through(o: np.ndarray, d: np.ndarray, T: np.ndarray, span: float):
    """Möller–Trumbore, for many edges at once: where the edge o → o + d goes through the triangle T (strictly inside
    the edge, so edges that only touch do not count)."""
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    h = np.cross(d, e2)
    a = np.einsum("ij,ij->i", e1, h)
    tiny = (span ** 2) * 1e-12
    parallel = np.abs(a) < tiny
    f = np.where(parallel, 0.0, 1.0 / np.where(parallel, 1.0, a))
    s = o - T[:, 0]
    u = f * np.einsum("ij,ij->i", s, h)
    q = np.cross(s, e1)
    w = f * np.einsum("ij,ij->i", d, q)
    k = f * np.einsum("ij,ij->i", e2, q)
    eps = 1e-9
    ok = ~parallel & (u >= -eps) & (w >= -eps) & (u + w <= 1 + eps) & (k > eps) & (k < 1 - eps)
    return o + d * k[:, None], ok


def wall_thickness(v: np.ndarray, t: np.ndarray, minimum: float) -> tuple[float, np.ndarray]:
    """How thick the wall is behind each face (a ray from its centre, inwards, to the other side): the thinnest, and
    the segments where it is thinner than `minimum`."""
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(v, dtype=float), deep=True))
    cells = vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0, 3 * len(t) + 1, 3, dtype=np.int64), deep=True),
                  numpy_to_vtkIdTypeArray(np.ascontiguousarray(t.ravel(), dtype=np.int64), deep=True))
    mesh = vtk.vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(cells)
    locator = vtk.vtkStaticCellLocator()
    locator.SetDataSet(mesh)
    locator.BuildLocator()

    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    normals = np.cross(b - a, c - a)
    length = np.linalg.norm(normals, axis=1)
    usable = np.nonzero(length > 0)[0]
    if len(usable) > THICKNESS_SAMPLES:
        usable = usable[np.linspace(0, len(usable) - 1, THICKNESS_SAMPLES).astype(int)]
    span = float(np.ptp(v, axis=0).max())
    thinnest, thin = np.inf, []
    found, cells_hit = vtk.vtkPoints(), vtk.vtkIdList()
    for i in usable:
        n = normals[i] / length[i]
        centre = (a[i] + b[i] + c[i]) / 3
        start = centre - n * span * 1e-6
        if not locator.IntersectWithLine(start, centre - n * span * 2, span * 1e-9, found, cells_hit):
            continue
        hits = np.array([found.GetPoint(k) for k in range(found.GetNumberOfPoints())])
        distances = np.linalg.norm(hits - centre, axis=1)
        distances = distances[distances > span * 1e-5]
        if not len(distances):
            continue
        d = float(distances.min())
        thinnest = min(thinnest, d)
        if d < minimum:
            thin.append([centre, centre - n * d])
    return (thinnest if np.isfinite(thinnest) else 0.0), np.array(thin, dtype=float).reshape(-1, 2, 3)


def problems_of(reports: list[Report], name: str | None = None) -> Data:
    """The problems of all the pieces as lines in the view (the open edges, the crossings, the thin walls)."""
    marks = [m for r in reports for m in r.marks if len(m)]
    segments = np.concatenate(marks) if marks else np.zeros((0, 2, 3))
    return Data(segments, ("problem",), name, kind=CURVE)


def printer_box(geometry: Data, printer, name: str | None = None) -> Data:
    """The printer's volume around the geometry, standing on its lowest point and centred on it: to see whether it
    fits."""
    from .geometry import box
    v = geometry.values.reshape(-1, 3)
    low, high = v.min(axis=0), v.max(axis=0)
    w, d, h = (float(x) for x in printer)
    centre = (low + high) / 2
    room = box(w, d, h)
    corner = np.array([centre[0] - w / 2, centre[1] - d / 2, low[2]])
    values = np.asarray(room.values, dtype=float) - np.asarray(room.values, dtype=float).reshape(-1, 3).min(axis=0) \
        + corner
    return Data(values, (), name, kind=BOX)


SHOW = ('problems', 'ready', 'printer')


def print_check(geometry: Data, show: str = 'problems', width: float = 0.2, depth: float = 0.2, height: float = 0.2,
                thickness: float = 0.0008, name: str | None = None) -> Data:
    """The node Print check: the problems as lines in the view (or yes/no for each piece, or the printer's volume),
    with the report of each piece kept in `.report` for the panel."""
    if not isinstance(geometry, Data):
        raise ShapeError(tr('Connect the geometry to check (a body, a mesh, a surface).'))
    if show not in SHOW:
        raise ShapeError(tr('“show” must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    for value, what in ((width, 'width'), (depth, 'depth'), (height, 'height')):
        if not float(value) > 0:
            raise ShapeError(tr('The printer’s {what} must be greater than zero.').format(what=tr(what)))
    printer = (float(width), float(depth), float(height))
    if show == 'printer':                          # only the printer's volume: nothing to check for that
        result = printer_box(geometry, printer, name)
        result.report = None
        result.colour, result.opacity = "#3fa34d", 0.25        # unless the node is given another
        return result
    reports = check(pieces(geometry), printer, float(thickness or 0))
    if show == 'ready':
        shape = geometry.values.shape[:len(geometry.levels)]
        ready = np.zeros(shape, dtype=bool)
        for r in reports:
            ready[r.index] = r.ready
        result = geometry.derived(ready, name, None)
    else:
        result = problems_of(reports, name)
        result.colour = "#e0302a"
    result.report = reports
    return result
