"""Minimal geometry (step 1.2).

Lengths in metres and angles in degrees (D2). Every node accepts loose numbers or `Data` with levels, and combines
its inputs with the single rule (R1):

    centres = centre(grid(rectangle(20, 12, plane="elevation"), cell_width=1, cell_height=1))
    sun_fins = place(box(0.40, 0.05, 1.00), at=centres, rotation=angles)

Each element is a point (3 coordinates) or a mesh: its vertices (n × 3) plus some faces common to all the elements,
kept in the `Kind`.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .data import Data, ShapeError, _require_size_, apply, integer, require_numbers, reduce
from .language import comma, tr


@dataclass(frozen=True)
class Kind:
    """What each element of a geometric data is."""

    name: str
    # If it is a mesh: each face is a list of vertex indices, anticlockwise
    # seen from outside.
    faces: tuple[tuple[int, ...], ...] | None = None
    # If it is a curve: its points, in order (n × 3); closed if the last joins the first.
    curve: bool = False
    closed: bool = False
    # If it is a surface: its points form a grid of rows × columns
    # (kept row after row), and `faces` are its quadrilaterals.
    grid: tuple[int, int] | None = None
    # Polygons of a variable number of vertices (polygons.py): each element repeats its last
    # vertex to fill up to the others; `real_faces` removes the repeats when drawing or exporting.
    polygon: bool = False


POINT = Kind("point")
CURVE = Kind("curve", curve=True)
CLOSED_CURVE = Kind("closed curve", curve=True, closed=True)
#: A vector: a direction and a length (x, y, z). It serves where a point goes (Move, Line by direction…); in the
#: view, an arrow from the origin.
VECTOR = Kind("vector")
#: An arrow: a vector placed at a point (from, to). It is a line, with its tip in the view.
ARROW = Kind("arrow", curve=True)
SAMPLES = 64  # points with which a circle or a smooth curve is drawn
RECTANGLE = Kind("rectangle", ((0, 1, 2, 3),))
BOX = Kind("box", (
    (0, 3, 2, 1),  # abajo
    (4, 5, 6, 7),  # arriba
    (0, 1, 5, 4),  # front (-y)
    (1, 2, 6, 5),  # derecha (+x)
    (2, 3, 7, 6),  # back (+y)
    (3, 0, 4, 7),  # izquierda (-x)
))

# A block is a box that comes from thickening a panel: same faces, but its
# sides are not called south, east… (Faces by name cannot be asked of it).
BLOCK = Kind("block", BOX.faces)

# The faces of a box by their name (Y is north). Each one with its
# corners in the order of a rectangle seen from outside: bottom-left,
# abajo-derecha, arriba-derecha, arriba-izquierda.
FACES_BOX = {
    "south": (0, 1, 5, 4),
    "east": (1, 2, 6, 5),
    "north": (2, 3, 7, 6),
    "west": (3, 0, 4, 7),
    "roof": (4, 5, 6, 7),
    "base": (0, 3, 2, 1),
}
GROUPS_FACES = {
    'façades': ("south", "east", "north", "west"),
    'all faces': tuple(FACES_BOX),
}

PLANES = {
    'plan': ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),   # horizontal: X across, Y up
    'elevation': ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),   # vertical, looking at -Y: X across, Z up
    'side elevation': ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),  # vertical, looking at +X
}

AXES = {"vertical": 2, "z": 2, "x": 0, "y": 1}


# --- Crear -------------------------------------------------------------------

def point(x=0.0, y=0.0, z=0.0, name: str | None = None) -> Data:
    """A point, or many if some coordinate is a data with levels."""
    return apply(lambda x, y, z: np.stack(np.broadcast_arrays(x, y, z), axis=-1),
                   _data(x), _data(y), _data(z), name=name, kind=POINT)


def rectangle(width, height, origin=(0.0, 0.0, 0.0), plane: str = 'plan',
               name: str | None = None) -> Data:
    """A rectangle with its bottom left corner at `origin`.

    `plane`: plan (horizontal), elevation (vertical, like a facade) or side elevation.
    """
    if plane not in PLANES:
        raise ShapeError(tr("I don't know the plane “{plane}”. Options: {options}.").format(
                               plane=plane, options=', '.join(tr(o) for o in PLANES)))
    u, v = (np.array(e) for e in PLANES[plane])

    def corners(a, h, o):
        a, h = a[..., None], h[..., None]
        return np.stack([o, o + a * u, o + a * u + h * v, o + h * v], axis=-2)

    return apply(corners, _data(width), _data(height), _point(origin, "origin"),
                   name=name, kind=RECTANGLE)


def box(width, depth, height, name: str | None = None) -> Data:
    """A box centred on the origin: `width` in X, `depth` in Y, `height` in Z."""
    signs = np.array([
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
    ]) / 2

    def vertices(a, f, h):
        measures = np.stack(np.broadcast_arrays(a, f, h), axis=-1)
        return signs * measures[..., None, :]

    return apply(vertices, _data(width), _data(depth), _data(height), name=name, kind=BOX)


#: Bounding box: around everything, or around each element.
BOUNDING = ('all', 'each')


def bounding_box(geometry: Data, of: str = 'all', name: str | None = None) -> Data:
    """The box that wraps the geometry, aligned with the axes (*Bounding Box*): one around everything, or one around
    each element. Its eight corners in the order of a box: the four below, then the four above."""
    _require_geometry(geometry)
    if of not in BOUNDING:
        raise ShapeError(tr('“of” must be one of: {options}.').format(options=", ".join(tr(o) for o in BOUNDING)))
    signs = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
    if of == 'all':
        v = np.asarray(geometry.values[geometry.mask] if geometry.levels else geometry.values, float).reshape(-1, 3)
        low, high = np.nanmin(v, axis=0), np.nanmax(v, axis=0)
        return Data(low + signs * (high - low), (), name, kind=BOX)
    v = np.asarray(geometry.values, float)
    if geometry.kind is POINT:
        raise ShapeError(tr('A point has no box of its own: choose «all» for the box around all the points.'))
    low, high = np.nanmin(v, axis=-2), np.nanmax(v, axis=-2)
    corners = low[..., None, :] + signs * (high - low)[..., None, :]
    return geometry.derived(corners, name, BOX)


def prism(width, depth, height, origin=(0.0, 0.0, 0.0), name: str | None = None) -> Data:
    """A volume: `width` in X (east-west), `depth` in Y (north-south), `height` in Z.

    Its bottom south-west corner is at `origin`. Its faces are asked for by name with `faces`.
    """
    signs = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=float)

    def vertices(a, f, h, o):
        measures = np.stack(np.broadcast_arrays(a, f, h), axis=-1)
        return signs * measures[..., None, :] + o[..., None, :]

    return apply(vertices, _data(width), _data(depth), _data(height), _point(origin, "origin"),
                   name=name, kind=BOX)


def faces(volume: Data, which='façades', level: str = "face", name: str | None = None) -> Data:
    """The faces of a box or a prism, by their name, as rectangles.

    `which`: a list of names (south, east, north, west, roof, base), a text with names separated by commas, or a group:
    «façades» (the four vertical ones) or «all faces». It adds the level `level` in that order. Each face is a rectangle
    seen from outside, so its grid goes from bottom-left to top-right and its normal faces outwards.
    """
    if volume.kind != BOX:
        raise ShapeError(
            tr('“{name}” should be a box or a prism to ask for faces by name, and it is {what_is}.').format(
                name=volume._name(), what_is=_what_is(volume))
        )
    if isinstance(which, str):
        which = list(GROUPS_FACES.get(which, [c.strip() for c in which.split(",") if c.strip()]))
    from .legacy_names import OPTIONS
    old = OPTIONS["Faces"]["which"]                 # files written with the Spanish names
    which = [old.get(c, c) for c in which]
    for c in which:
        if c not in FACES_BOX:
            raise ShapeError(tr("I don't know the face “{c}”. There are: {options} (or “façades”, “all”).").format(
                                   c=c, options=', '.join(tr(o) for o in FACES_BOX)))
    if not which:
        raise ShapeError(tr('Say which faces: for example “south, east” or “façades”.'))
    indices = np.array([FACES_BOX[c] for c in which])
    return volume.derived(volume.values[..., indices, :], name, RECTANGLE, (level,))


def normal(rect: Data, name: str | None = None) -> Data:
    """Where each rectangle (or polygon: a hexagon of a Grid) faces: a vector of length 1, perpendicular to it."""
    if rect.kind is not None and rect.kind.polygon and rect.kind.name == "polygon":
        p = rect.values                      # Newell: the sum of the cross products of each side (padding adds 0)
        n = np.cross(p, np.roll(p, -1, axis=-2)).sum(axis=-2)
        length = np.linalg.norm(n, axis=-1, keepdims=True)
        return rect.derived(np.divide(n, length, out=np.zeros_like(n), where=length != 0), name, POINT)
    _require_kind(rect, RECTANGLE, "rectangle")
    u, v = _sides(rect)
    n = np.cross(u, v)
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    return rect.derived(np.divide(n, length, out=np.zeros_like(n), where=length != 0), name, POINT)


def thicken(rect: Data, thickness, name: str | None = None) -> Data:
    """Turns each rectangle into a block of `thickness`.

    Positive grows outwards (towards where the rectangle faces); negative, inwards. The thickness can be different for
    each element.
    """
    if rect.kind is not None and rect.kind.grid is not None:
        return _thicken_surface(rect, thickness, name)
    if rect.kind is not None and rect.kind.name == "mesh" and rect.kind.faces:     # a free mesh: closed, sewn
        from .mesh_tools import thicken_mesh
        return thicken_mesh(rect, thickness, name)
    if rect.kind is not None and rect.kind.polygon and rect.kind.name == "polygon":
        from .polygons import thicken as thicken_polygon
        return thicken_polygon(rect, thickness, name)
    _require_kind(rect, RECTANGLE, "rectangle")

    def block(corners, e):
        u = corners[..., 1, :] - corners[..., 0, :]
        v = corners[..., 3, :] - corners[..., 0, :]
        n = np.cross(u, v)
        length = np.linalg.norm(n, axis=-1, keepdims=True)
        n = np.divide(n, length, out=np.zeros_like(n), where=length != 0)
        e = np.asarray(e, dtype=float)[..., None, None]
        below = corners + n[..., None, :] * np.minimum(e, 0)
        above = corners + n[..., None, :] * np.maximum(e, 0)
        return np.concatenate([below, above], axis=-2)

    return apply(block, rect, _data(thickness), name=name, kind=BLOCK)


def _frame_faces(with_thickness: bool) -> tuple[tuple[int, ...], ...]:
    o, i = range(0, 4), range(4, 8)
    next_ = lambda k: (k + 1) % 4  # noqa: E731
    faces = [(o[k], o[next_(k)], i[next_(k)], i[k]) for k in range(4)]                 # the ring, outwards
    if with_thickness:
        ot, it = range(8, 12), range(12, 16)
        faces = [(ot[k], ot[next_(k)], it[next_(k)], it[k]) for k in range(4)]          # arriba
        faces += [(i[k], i[next_(k)], o[next_(k)], o[k]) for k in range(4)]             # abajo
        faces += [(o[k], o[next_(k)], ot[next_(k)], ot[k]) for k in range(4)]           # canto exterior
        faces += [(i[next_(k)], i[k], it[k], it[next_(k)]) for k in range(4)]           # edge of the opening
    return tuple(faces)


FRAME = Kind("frame", _frame_faces(False))
COARSE_FRAME = Kind("frame", _frame_faces(True))


def _normal_de(corners: np.ndarray) -> np.ndarray:
    u = corners[..., 1, :] - corners[..., 0, :]
    v = corners[..., 3, :] - corners[..., 0, :]
    n = np.cross(u, v)
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    return np.divide(n, length, out=np.zeros_like(n), where=length != 0)


def _shrink(corners: np.ndarray, d: np.ndarray) -> np.ndarray:
    """The corners of a convex quadrilateral with each side moved `d` inwards (mitred)."""
    n = _normal_de(corners)[..., None, :]
    side = np.roll(corners, -1, axis=-2) - corners                 # the side that leaves each corner
    side = side / np.maximum(np.linalg.norm(side, axis=-1, keepdims=True), 1e-12)
    towards_inside = np.cross(n, side)                                  # perpendicular to the side, towards the centre
    before = np.roll(towards_inside, 1, axis=-2)                         # that of the side that arrives
    mitre = (before + towards_inside) / np.maximum(1 + (before * towards_inside).sum(-1, keepdims=True), 1e-6)
    return corners + mitre * np.asarray(d, dtype=float)[..., None, None]


def frame(panel: Data, opening=0.5, thickness: float = 0.0, width=None, output: str = 'frame',
          name: str | None = None) -> Data:
    """A frame with an opening in each panel (*Panel Frame*), or the opening alone.

    The opening is given as `opening` (its size relative to the panel, from 0 to 1; it can be different in each panel)
    or as the frame's `width` in metres (the same all round: the frame of a window). `thickness`: towards where the panel
    faces (0: a flat frame). `output`: «frame», or «hole» to get the rectangle of the opening (the glass, the inner
    leaf).
    """
    if output not in ('frame', 'hole'):
        raise ShapeError(tr("I don't know the output “{output}”. Options: frame, opening.").format(output=output))
    if panel.kind is not None and panel.kind.polygon and panel.kind.name == "polygon":
        if width is not None:
            raise ShapeError(tr('On a polygon, the frame is given by “opening” (not yet by “width”).'))
        from .polygons import frame as polygon_frame
        return polygon_frame(panel, opening, thickness, output, name)
    _require_kind(panel, RECTANGLE, 'rectangle (a panel)')
    thickness = float(thickness)
    by_width = width is not None

    def hole_of(corners, x):
        if by_width:
            return _shrink(corners, x)
        c = corners.mean(axis=-2, keepdims=True)
        f = np.clip(np.asarray(x, dtype=float), 0, 0.98)[..., None, None]
        return c + (corners - c) * f

    def build(corners, x):
        hole = hole_of(corners, x)
        if output == 'hole':
            return hole
        plane = np.concatenate([np.broadcast_to(corners, hole.shape), hole], axis=-2)
        if not thickness:
            return plane
        return np.concatenate([plane, plane + _normal_de(corners)[..., None, :] * thickness], axis=-2)

    kind = RECTANGLE if output == 'hole' else (COARSE_FRAME if thickness else FRAME)
    return apply(build, panel, _data(width if by_width else opening), name=name, kind=kind)


# --- Curvas ------------------------------------------------------------------

def line(from_, to, name: str | None = None) -> Data:
    """A straight line between two points (or many, if the points have levels)."""
    return apply(lambda a, b: np.stack([a, b], axis=-2), _point(from_, "from"), _point(to, "to"),
                   name=name, kind=CURVE)


def line_by_direction(from_, direction=(0.0, 0.0, 1.0), length=1.0, name: str | None = None) -> Data:
    """A line that leaves a point towards a direction, with a length (*Line SDL*): a 3 m mast upwards from a centroid,
    without writing coordinates. A negative length goes the other way."""
    def trace(a, d, l):
        length_d = np.linalg.norm(d, axis=-1, keepdims=True)
        if np.any(length_d < 1e-12):
            raise ShapeError(tr('The direction of the line cannot be zero (0, 0, 0).'))
        return np.stack(np.broadcast_arrays(a, a + d / length_d * np.asarray(l)[..., None]), axis=-2)

    return apply(trace, _point(from_, "from"), _point(direction, "direction"), _data(length),
                   name=name, kind=CURVE)


def circle(centre=(0.0, 0.0, 0.0), radius=1.0, radius_2=None, plane: str = 'plan',
            name: str | None = None, normal=None) -> Data:
    """A circle; with `radius_2`, an ellipse (radius across the plane, radius_2 up it). With `normal` (a vector, or one
    per circle: the normals of a surface), the circle stays perpendicular to it, resting on what faces there, instead of
    on the plane."""
    if plane not in PLANES:
        raise ShapeError(tr("I don't know the plane “{plane}”. Options: {options}.").format(
                               plane=plane, options=', '.join(tr(o) for o in PLANES)))
    angles = np.linspace(0, 2 * np.pi, SAMPLES, endpoint=False)
    cosine, sine = np.cos(angles)[:, None], np.sin(angles)[:, None]
    r2 = _data(radius if radius_2 is None else radius_2)
    if normal is None:
        u, v = (np.array(e) for e in PLANES[plane])

        def points(c, r1, r2):
            r1, r2 = np.asarray(r1)[..., None, None], np.asarray(r2)[..., None, None]
            return c[..., None, :] + r1 * cosine * u + r2 * sine * v

        return apply(points, _point(centre, "centre"), _data(radius), r2, name=name, kind=CLOSED_CURVE)

    def points_with_normal(c, r1, r2, n):
        n = np.asarray(n, float)
        n = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
        ref = np.where(np.abs(n[..., 2:3]) < 0.9, [0.0, 0.0, 1.0], [1.0, 0.0, 0.0])
        u = np.cross(ref, n)
        u = u / np.maximum(np.linalg.norm(u, axis=-1, keepdims=True), 1e-12)
        v = np.cross(n, u)
        r1, r2 = np.asarray(r1)[..., None, None], np.asarray(r2)[..., None, None]
        return c[..., None, :] + r1 * cosine * u[..., None, :] + r2 * sine * v[..., None, :]

    return apply(points_with_normal, _point(centre, "centre"), _data(radius), r2, _point(normal, "normal"),
                   name=name, kind=CLOSED_CURVE)


#: How a circle is given: with its centre, or touching a curve (tangent to it at a point).
MODES_CIRCLE = ('centre and radius', 'tangent to a curve')
SIDES = ('left', 'right')


def circle_tangent(curve: Data, radius=1.0, at=0.5, size: str = 'fraction', side: str = 'left',
                     name: str | None = None) -> Data:
    """A circle that touches a curve at a point, without cutting it (tangent): at `at` (a fraction from 0 to 1, or a
    distance if `size` is «distance»; several with «;»), of `radius`, to the left or to the right of the curve's
    direction, in the curve's plane. It starts at the point where it touches and goes on towards where the curve goes."""
    if side not in SIDES:
        raise ShapeError(tr('The side can be: {options}.').format(options=", ".join(tr(x) for x in SIDES)))
    if size not in ('fraction', 'distance'):
        raise ShapeError(tr('The measure can be: fraction or distance.'))
    r = float(_data(radius).values.ravel()[0]) if isinstance(radius, Data) else float(radius)
    if not r > 0:
        raise ShapeError(tr('The radius must be greater than 0.'))
    c, accumulated, wanted, a_only = _where_on_curve(curve, size, 2, 1.0, at, "point")
    points = _in_lengths(c, accumulated, wanted)                          # (…, m, 3)
    ahead = _directions(c, accumulated, wanted, curve.kind.closed)
    planes = c.reshape(-1, c.shape[-2], 3)
    normals = np.stack([_curve_plane(_without_padding(x)) for x in planes]).reshape(c.shape[:-2] + (1, 3))
    towards = np.cross(normals, ahead) * (1.0 if side == 'left' else -1.0)   # from the point to the centre
    centres = points + towards * r
    u = np.linspace(0, 2 * np.pi, SAMPLES, endpoint=False)[:, None]
    circles = (centres[..., None, :] + r * (np.cos(u) * -towards[..., None, :] + np.sin(u) * ahead[..., None, :]))
    if a_only:
        return curve.derived(circles[..., 0, :, :], name, CLOSED_CURVE)
    return curve.derived(circles, name, CLOSED_CURVE, ("circle",))


#: How an arc is given: by three points (start, one it passes through, end), with its centre, radius and angles, or
#: leaving a point towards a direction (tangent to it) up to another.
MODES_ARC = ('three points', 'centre and angles', 'start, direction and end')


def arc(mode: str = 'three points', start=(0.0, 0.0, 0.0), middle=(1.0, 1.0, 0.0), end=(2.0, 0.0, 0.0),
         centre=(0.0, 0.0, 0.0), radius=1.0, from_=0.0, to=90.0, plane: str = 'plan',
         name: str | None = None, direction=(1.0, 0.0, 0.0)) -> Data:
    """An arc of a circle (*Arc*, *Arc 3Pt*):

    - «three points»: it starts at `start`, passes through `middle` and ends at `end` (in any plane);
    - «centre and angles»: around `centre`, with `radius`, from `from_` to `to` degrees (0° towards +X in plan; measured
      as on a drawing: anticlockwise);
    - «start, direction and end» (*Arc SED*): it leaves `start` towards `direction` (tangent to it: it follows a curve
      without a break) and ends at `end`.
    """
    if mode not in MODES_ARC:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MODES_ARC)))
    if mode == 'centre and angles':
        if plane not in PLANES:
            raise ShapeError(tr("I don't know the plane “{plane}”. Options: {options}.").format(
                                   plane=plane, options=', '.join(tr(o) for o in PLANES)))
        u, v = (np.array(e) for e in PLANES[plane])

        def trace(c, r, a, b):
            r, a, b = (np.asarray(x, float)[..., None, None] for x in (r, a, b))
            t = np.radians(a + (b - a) * np.linspace(0, 1, SAMPLES + 1)[:, None])
            return c[..., None, :] + r * (np.cos(t) * u + np.sin(t) * v)

        return apply(trace, _point(centre, "centre"), _data(radius), _data(from_), _data(to),
                       name=name, kind=CURVE)

    def _straight(a, c):
        """The arc flattened out: the straight line from `a` to `c`, with as many points as an arc."""
        t = np.linspace(0, 1, SAMPLES + 1)[:, None]
        return a[..., None, :] + t * (c - a)[..., None, :]

    def _across(v):
        """A vector square to each `v` (never zero)."""
        axis = np.where((np.abs(v[..., 0:1]) < 0.9 * np.linalg.norm(v, axis=-1, keepdims=True)), [1.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0])
        return np.cross(v, axis) + (np.linalg.norm(v, axis=-1, keepdims=True) < 1e-300) * [0.0, 0.0, 1.0]

    if mode == 'start, direction and end':
        def with_direction(a, d, c):
            a, d, c = np.broadcast_arrays(a, d, c)
            chord = c - a
            normal = np.cross(d, chord)
            n = np.linalg.norm(normal, axis=-1, keepdims=True)
            if np.any(np.linalg.norm(d, axis=-1) < 1e-12):
                raise ShapeError(tr('The arc direction cannot be zero (0, 0, 0).'))
            if np.any((n[..., 0] < 1e-12) & ((d * chord).sum(-1) <= 0)):
                raise ShapeError(tr('The end lies exactly behind the starting direction: there is no arc.'))
            flat = n[..., 0] < 1e-12
            if np.any(flat):
                # The end straight ahead: the arc has flattened out into the straight line (the flat ones are worked
                # out with any other direction, and then replaced).
                if np.all(flat):
                    return _straight(a, c)
                curved = with_direction(a, np.where(flat[..., None], _across(chord), d), c)
                return np.where(flat[..., None, None], _straight(a, c), curved)
            normal = normal / n
            t = d / np.linalg.norm(d, axis=-1, keepdims=True)
            towards = np.cross(normal, t)                          # from the start towards the centre (on the side of the end)
            r = (chord * chord).sum(-1, keepdims=True) / (2 * (chord * towards).sum(-1, keepdims=True))
            o = a + towards * r
            e1, e2 = (a - o) / r, t
            ang = np.mod(np.arctan2(((c - o) * e2).sum(-1), ((c - o) * e1).sum(-1)), 2 * np.pi)
            theta = ang[..., None] * np.linspace(0, 1, SAMPLES + 1)
            return o[..., None, :] + r[..., None, :] * (np.cos(theta)[..., None] * e1[..., None, :]
                                                        + np.sin(theta)[..., None] * e2[..., None, :])

        return apply(with_direction, _point(start, "start"), _point(direction, "direction"), _point(end, "end"),
                       name=name, kind=CURVE)

    def by_three(a, b, c):
        a, b, c = np.broadcast_arrays(a, b, c)
        ab, ac = b - a, c - a
        normal = np.cross(ab, ac)
        n2 = (normal * normal).sum(axis=-1, keepdims=True)
        flat = n2[..., 0] < 1e-18
        if np.any(flat):
            # In a straight line: with the middle between the ends, the arc has flattened out (a depth of 0) and is
            # the straight line; otherwise there is no arc.
            along = (ab * ac).sum(-1) / np.maximum((ac * ac).sum(-1), 1e-300)
            if np.any(flat & ~((along > 1e-9) & (along < 1 - 1e-9))):
                raise ShapeError(tr('The three points of the arc are in a straight line (or two are the same): '
                                    'there is no arc.'))
            if np.all(flat):
                return _straight(a, c)
            curved = by_three(a, np.where(flat[..., None], a + _across(ac), b),
                              np.where(flat[..., None], a + ac + _across(_across(ac)), c))
            return np.where(flat[..., None, None], _straight(a, c), curved)
        # The centre of the circle through the three (circumcentre).
        o = a + (np.cross(normal, ab) * (ac * ac).sum(-1, keepdims=True)
                 + np.cross(ac, normal) * (ab * ab).sum(-1, keepdims=True)) / (2 * n2)
        e1 = a - o
        r = np.linalg.norm(e1, axis=-1, keepdims=True)
        e1 = e1 / r
        e2 = np.cross(normal / np.sqrt(n2), e1)
        angle = lambda p: np.mod(np.arctan2(((p - o) * e2).sum(-1), ((p - o) * e1).sum(-1)), 2 * np.pi)
        angle_c = angle(c)                                    # from a towards c, in the direction that passes through b
        t = np.linspace(0, 1, SAMPLES + 1)
        theta = angle_c[..., None] * t
        return o[..., None, :] + r[..., None, :] * (np.cos(theta)[..., None] * e1[..., None, :]
                                                    + np.sin(theta)[..., None] * e2[..., None, :])

    return apply(by_three, _point(start, "start"), _point(middle, "middle"), _point(end, "end"),
                   name=name, kind=CURVE)


#: How the length of a catenary is given: in metres, or as so many times the distance between its ends.
LENGTHS_CATENARY = ('metres', 'times the distance')


def catenary(start=(0.0, 0.0, 0.0), end=(4.0, 0.0, 0.0), length=5.0, gravity=(0.0, 0.0, -1.0),
             length_in: str = 'metres', name: str | None = None) -> Data:
    """The exact shape of a chain or a cable hanging from two points (*Catenary*): y = a·cosh(x/a), with `length`
    (in metres, or as times the distance between the ends) and hanging towards `gravity`. Upside down (gravity up) it
    is the arch that works only in compression. A length shorter than the distance leaves the cable taut: a straight
    line. Its points are evenly spaced along it, so Divide and Points on curve share it out evenly."""
    if length_in not in LENGTHS_CATENARY:
        raise ShapeError(tr('The mode must be one of: {options}.').format(
            options=", ".join(tr(m) for m in LENGTHS_CATENARY)))

    def trace(a, b, l, g):
        a, b, g = np.broadcast_arrays(a, b, g)
        shape = a.shape[:-1]
        a, b, g = a.reshape(-1, 3), b.reshape(-1, 3), g.reshape(-1, 3)
        l = np.broadcast_to(np.asarray(l, dtype=float), shape).reshape(-1)
        weight = np.linalg.norm(g, axis=-1)
        if np.any(weight < 1e-12):
            raise ShapeError(tr('The gravity of the catenary cannot be zero (0, 0, 0).'))
        up = -g / weight[:, None]
        d = b - a
        chord = np.linalg.norm(d, axis=-1)
        total = l * chord if length_in == 'times the distance' else l
        if np.any(total <= 0):
            raise ShapeError(tr('The length of the catenary must be greater than 0.'))
        rise = (d * up).sum(-1)                              # how much higher the end is than the start
        across = d - rise[:, None] * up                     # the span, square to gravity
        span = np.linalg.norm(across, axis=-1)
        t = np.linspace(0.0, 1.0, SAMPLES + 1)
        out = a[:, None, :] + t[None, :, None] * d[:, None, :]          # taut: a straight line
        slack = total > chord * (1 + 1e-9)
        vertical = slack & (span <= 1e-9 * np.maximum(total, 1e-12))
        hanging = slack & ~vertical
        if np.any(hanging):
            i = np.flatnonzero(hanging)
            s, v, L = span[i], rise[i], total[i]
            # sinh(k)/k = sqrt(L² − v²)/s, with k = s/(2a): Newton from above the root (the function is convex there).
            r = np.sqrt(L ** 2 - v ** 2) / s
            k = np.minimum(np.sqrt(6 * (r - 1)), 2 * np.log(2 * r) + 1)
            for _ in range(200):
                step = (np.sinh(k) - r * k) / (np.cosh(k) - r)
                k = np.maximum(k - step, k / 2)
                if np.all(np.abs(step) <= 1e-14 * np.maximum(k, 1)):
                    break
            c = s / (2 * k)                                 # the parameter a of the catenary
            low = s / 2 - c * np.arctanh(v / L)              # where the lowest point is, along the span
            sinh0 = np.sinh(-low / c)
            arc_ = t[None, :] * L[:, None]                  # even steps along the cable
            x = low[:, None] + c[:, None] * np.arcsinh(arc_ / c[:, None] + sinh0[:, None])
            y = c[:, None] * (np.cosh((x - low[:, None]) / c[:, None]) - np.cosh(low / c)[:, None])
            along = across[i] / s[:, None]
            out[i] = a[i, None, :] + x[..., None] * along[:, None, :] + y[..., None] * up[i, None, :]
            out[i, -1] = b[i]
        if np.any(vertical):
            # One end above the other: the cable falls from both and folds at its lowest point.
            for j in np.flatnonzero(vertical):
                bottom = min(0.0, rise[j]) - (total[j] - abs(rise[j])) / 2
                knots = np.array([0.0, -bottom, -bottom + rise[j] - bottom])
                heights = np.interp(t * knots[-1], knots, [0.0, bottom, rise[j]])
                heights[np.argmin(np.abs(t * knots[-1] - knots[1]))] = bottom
                out[j] = a[j] + heights[:, None] * up[j]
        return out.reshape(shape + (SAMPLES + 1, 3))

    return apply(trace, _point(start, "start"), _point(end, "end"), _data(length), _point(gravity, "gravity"),
                 name=name, kind=CURVE)


# --- Vectores -------------------------------------------------------------------

#: How a vector is made: writing its x, y, z; from one point to another; or from another vector.
MODES_VECTOR = ("x, y, z", 'axis', 'point to point', 'unit', 'to a length', 'multiply', 'add', 'invert',
               "perpendicular")
#: The axes a vector of the «axis» mode goes along (*Unit X*, *Unit Y*, *Unit Z*).
VECTOR_AXES = ('x', 'y', 'z')


def _length(v: np.ndarray) -> np.ndarray:
    return np.linalg.norm(v, axis=-1, keepdims=True)


def vector(mode: str = "x, y, z", x=0.0, y=0.0, z=1.0, from_=None, to=None, base=None, other=None, length=1.0,
           name: str | None = None, axis: str = 'z', factor=1.0) -> Data:
    """A vector (*Vector XYZ*, *Unit X/Y/Z*, *Vector 2Pt*, *Unit Vector*, *Amplitude*, *Multiply*, *Addition*,
    *Reverse*, *Cross Product*):

    - «x, y, z»: written with its three components;
    - «axis»: along x, y or z, `factor` long (1: the unit vector of that axis; several factors, several vectors);
    - «point to point»: from `from_` to `to`;
    - «unit»: the same, of length 1 (only the direction);
    - «to a length»: the same direction, with `length`;
    - «multiply»: the same, times `factor` (twice as long, half, reversed if negative);
    - «add»: `base` plus `other`, one after the other;
    - «invert»: the same, reversed;
    - «perpendicular»: perpendicular to `base` and to `other` (the *cross product*): from a radial direction and the
      vertical comes the tangent.
    """
    if mode not in MODES_VECTOR:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MODES_VECTOR)))
    if mode == "x, y, z":
        return apply(lambda a, b, c: np.stack(np.broadcast_arrays(a, b, c), axis=-1).astype(float),
                       _data(x), _data(y), _data(z), name=name, kind=VECTOR)
    if mode == 'axis':
        if axis not in VECTOR_AXES:
            raise ShapeError(tr('The axis must be x, y or z (it is “{axis}”).').format(axis=axis))
        direction = np.eye(3)[VECTOR_AXES.index(axis)]
        return apply(lambda f: np.asarray(f, dtype=float)[..., None] * direction, _data(factor), name=name,
                     kind=VECTOR)
    if mode == 'point to point':
        if from_ is None or to is None:
            raise ShapeError(tr('A point-to-point vector needs both: “from” and “to”.'))
        return apply(lambda a, b: b - a, _point(from_, "from"), _point(to, "to"), name=name, kind=VECTOR)
    if base is None:
        raise ShapeError(tr('The starting vector (“base”) is missing.'))
    v = _point(base, "base")

    def unit(a):
        n = _length(a)
        if np.any(n < 1e-12):
            raise ShapeError(tr('A zero vector (0, 0, 0) has no direction.'))
        return a / n

    if mode == 'unit':
        return apply(unit, v, name=name, kind=VECTOR)
    if mode == 'invert':
        return apply(lambda a: -a, v, name=name, kind=VECTOR)
    if mode == 'to a length':
        return apply(lambda a, l: unit(a) * np.asarray(l)[..., None], v, _data(length), name=name, kind=VECTOR)
    if mode == 'multiply':
        return apply(lambda a, f: a * np.asarray(f, dtype=float)[..., None] + 0.0, v, _data(factor), name=name,
                     kind=VECTOR)               # (+ 0.0: no «-0» in the tables)
    if other is None:
        raise ShapeError(tr('This mode needs an “other” vector (for example, the vertical 0, 0, 1).'))
    if mode == 'add':
        return apply(lambda a, b: a + b, v, _point(other, "other"), name=name, kind=VECTOR)
    return apply(lambda a, b: np.cross(a, b), v, _point(other, "other"), name=name, kind=VECTOR)


#: What is measured of a vector.
MEASURES_VECTOR = ('length', 'angle')


def measure_vector(mode: str = 'length', base=None, other=(0.0, 0.0, 1.0), name: str | None = None) -> Data:
    """The length of a vector (*Vector Length*), or the angle in degrees between two (*Angle*): from 0 (equal) to 180
    (opposite); 90, perpendicular."""
    if mode not in MEASURES_VECTOR:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MEASURES_VECTOR)))
    if base is None:
        raise ShapeError(tr('The vector to measure (“base”) is missing.'))
    v = _point(base, "base")
    if mode == 'length':
        return apply(lambda a: np.linalg.norm(a, axis=-1), v, name=name)

    def angle(a, b):
        na, nb = np.linalg.norm(a, axis=-1), np.linalg.norm(b, axis=-1)
        cosine = np.divide((a * b).sum(axis=-1), na * nb, out=np.ones(np.broadcast(na, nb).shape), where=(na * nb) > 0)
        return np.degrees(np.arccos(np.clip(cosine, -1, 1)))

    return apply(angle, v, _point(other, "other"), name=name)


def arrow(from_, vector_, scale=1.0, name: str | None = None) -> Data:
    """A vector placed at a point, to see it (*Vector Display*): a line from `from_` to `from_ + vector × scale`,
    with its tip. It also serves as a line."""
    return apply(lambda a, v, k: np.stack(np.broadcast_arrays(a, a + v * np.asarray(k)[..., None]), axis=-2),
                   _point(from_, "from"), _point(vector_, "vector"), _data(scale), name=name, kind=ARROW)


def drawn_points(points) -> np.ndarray:
    """The points kept in a drawn curve ([[x, y, z], …], or [x, y] in plan) as (n, 3). In a NURBS Curve, a fourth
    value is the weight of the point ([x, y, z, weight]): here it does not count."""
    rows = [(list(map(float, p)) + [0.0, 0.0, 0.0])[:3] for p in (points or [])]
    return np.array(rows, dtype=float).reshape(-1, 3)


def drawn_weights(points) -> np.ndarray:
    """The weights of the drawn points of a NURBS Curve (the fourth value of each one; 1 if it does not have it)."""
    return np.array([float(p[3]) if len(p) > 3 else 1.0 for p in (points or [])], dtype=float)


def drawn_corners(points) -> np.ndarray:
    """Which drawn points are corners (the fifth value of each one, 1; the fourth is the weight of a NURBS Curve):
    there the curve breaks, instead of passing round."""
    return np.array([len(p) > 4 and float(p[4]) > 0.5 for p in (points or [])], dtype=bool)


def drawn_row(point, weight: float = 1.0, corner: bool = False) -> list[float]:
    """A drawn point as it is kept: [x, y, z], with its weight if it is not 1, and 1 at the end if it is a corner."""
    row = [float(c) for c in point]
    if corner:
        return row + [float(weight), 1.0]
    return row + [float(weight)] if abs(weight - 1) > 1e-9 else row


#: The two modes of a Drawn curve: the curve passes through the points, or the points attract it from outside.
MODES_CURVE = ('through points', 'by control points')
#: The highest degree offered (3: the usual smooth curve; 1: a polyline).
MAX_DEGREE = 5
#: How many points are computed in each span of a drawn curve (so that no straight lines show).
SAMPLES_BY_RUN = 32


def drawn_curve(points, mode: str = 'through points', degree=3, closed: bool = False,
                   name: str | None = None) -> Data:
    """A curve drawn with the mouse in the 3D view (Grasshopper's *Crv*):

    - «through points» mode: the curve passes through all of them (*interpolated*);
    - «by control points» mode: the points stay outside and attract it, like magnets (*control points*).

    `degree`: 1 gives a polyline; 2, second-degree curves; 3 (the usual), the smooth curve; up to 5, tauter and rounder.
    """
    p = drawn_points(points)
    corners = drawn_corners(points)
    minimum = 3 if closed else 2
    if len(p) < minimum:
        raise ShapeError(tr('“{name}” has no points yet (it needs {n} or more): select the node and press '
                              '“Edit curve” to mark where the curve passes.').format(
                               name=name or tr('The curve'), n=minimum))
    if mode not in MODES_CURVE:
        raise ShapeError(tr('The curve mode must be “{a}” or “{b}”.').format(a=tr(MODES_CURVE[0]),
                                                                                   b=tr(MODES_CURVE[1])))
    keep = np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-9]   # without repeated points in a row
    p, corners = p[keep], corners[keep]
    if closed and len(p) > 1 and np.linalg.norm(p[0] - p[-1]) < 1e-9:
        p, corners = p[:-1], corners[:-1]
    if len(p) < minimum:
        raise ShapeError(tr('“{name}” has repeated points: it needs {n} different ones.').format(
                               name=name or tr('The curve'), n=minimum))
    k = max(1, min(integer(degree), MAX_DEGREE, len(p) - 1))
    inner = corners.copy()
    if not closed:
        inner[[0, -1]] = False                       # the ends are where it starts and stops anyway
    if k > 1 and inner.any():
        return Data(_with_corners(p, inner, k, mode, closed), (), name, kind=CLOSED_CURVE if closed else CURVE)
    if mode == MODES_CURVE[0]:
        v = _interpolated_closed(p, k) if closed else _interpolated(p, k)
    else:
        v = _closed_from_control(p, k) if closed else _de_control(p, k)
    return Data(v, (), name, kind=CLOSED_CURVE if closed else CURVE)   # a single curve: without levels


def _with_corners(p: np.ndarray, corners: np.ndarray, k: int, mode: str, closed: bool) -> np.ndarray:
    """A drawn curve that breaks at its corners: from corner to corner, each stretch a curve of its own (through its
    points, or pulled by them), all joined at the corners."""
    if closed:                                       # it starts and ends at a corner, as an open curve
        first = int(np.flatnonzero(corners)[0])
        p, corners = np.roll(p, -first, axis=0), np.roll(corners, -first)
        p, corners = np.vstack([p, p[:1]]), np.r_[corners, True]
    cuts = [0] + [int(i) for i in np.flatnonzero(corners) if 0 < i < len(p) - 1] + [len(p) - 1]
    runs = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        stretch = p[a:b + 1]
        kk = max(1, min(k, len(stretch) - 1))
        v = _interpolated(stretch, kk) if mode == MODES_CURVE[0] else _de_control(stretch, kk)
        runs.append(v if not runs else v[1:])      # the corner, once
    v = np.vstack(runs)
    return v[:-1] if closed else v


def _base_bspline(knots: np.ndarray, k: int, t: np.ndarray) -> np.ndarray:
    """The basis functions of a B-spline of degree k (Cox–de Boor): (len(t), len(knots) - k - 1)."""
    t = np.asarray(t, dtype=float)[:, None]
    m = len(knots) - k - 1
    base = ((knots[:-1] <= t) & (t < knots[1:])).astype(float)
    end = knots[m]
    final_on = t[:, 0] >= end                      # the last parameter: inside the last span with length
    if final_on.any():
        last = max(i for i in range(len(knots) - 1) if knots[i] < knots[i + 1] <= end)
        base[final_on] = 0.0
        base[final_on, last] = 1.0
    for d in range(1, k + 1):
        n = len(knots) - d - 1
        left, right = knots[d:d + n] - knots[:n], knots[d + 1:d + 1 + n] - knots[1:1 + n]
        a = np.where(left > 0, (t - knots[:n]) / np.where(left > 0, left, 1.0), 0.0)
        b = np.where(right > 0, (knots[d + 1:d + 1 + n] - t) / np.where(right > 0, right, 1.0), 0.0)
        base = a * base[:, :n] + b * base[:, 1:n + 1]
    return base


def _local_base(knots: np.ndarray, k: int, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The k + 1 basis functions that are not zero at each parameter (The NURBS Book, A2.2), without the whole table:
    (indices of their control points, their values), each one (len(t), k + 1). t inside [knots[k], knots[m]]."""
    m = len(knots) - k - 1
    end = knots[m]
    run = np.clip(np.searchsorted(knots, t, side="right") - 1, k, m - 1)
    last = max(i for i in range(len(knots) - 1) if knots[i] < knots[i + 1] <= end)
    run[t >= end] = last                       # the last parameter: inside the last span with length
    base = np.zeros((len(t), k + 1))
    base[:, 0] = 1.0
    left, right = np.zeros((len(t), k + 1)), np.zeros((len(t), k + 1))
    for j in range(1, k + 1):
        left[:, j] = t - knots[run + 1 - j]
        right[:, j] = knots[run + j] - t
        saved = np.zeros(len(t))
        for r in range(j):
            temp = base[:, r] / (right[:, r + 1] + left[:, j - r])
            base[:, r] = saved + right[:, r + 1] * temp
            saved = left[:, j - r] * temp
        base[:, j] = saved
    return run[:, None] - k + np.arange(k + 1), base


def _samples(knots: np.ndarray, from_: float, to: float, closed: bool) -> np.ndarray:
    """The parameters where the curve is computed: the same in each span between knots."""
    cuts = np.unique(knots[(knots >= from_) & (knots <= to)])
    t = np.concatenate([np.linspace(a, b, SAMPLES_BY_RUN, endpoint=False) for a, b in zip(cuts[:-1], cuts[1:])])
    return t if closed else np.append(t, to)


def _parameters(p: np.ndarray, closed: bool) -> np.ndarray:
    """Centripetal (the root of the distance): without loops or spikes even if the points are uneven."""
    runs = np.diff(np.vstack([p, p[:1]]) if closed else p, axis=0)
    steps = np.sqrt(np.maximum(np.linalg.norm(runs, axis=1), 1e-12))
    return np.concatenate([[0.0], np.cumsum(steps)])


def _interpolated(p: np.ndarray, k: int) -> np.ndarray:
    u = _parameters(p, False)
    u = u / u[-1]
    n = len(p)
    inner = [u[j:j + k].mean() for j in range(1, n - k)]
    knots = np.concatenate([np.zeros(k + 1), inner, np.ones(k + 1)])
    control = np.linalg.solve(_base_bspline(knots, k, u), p)
    t = np.union1d(_samples(knots, 0.0, 1.0, False), u)          # with the points themselves, exact
    return _base_bspline(knots, k, t) @ control


def _interpolated_closed(p: np.ndarray, k: int) -> np.ndarray:
    n = len(p)
    u = _parameters(p, True)                      # n + 1 values: the last one goes back to the first
    length = u[-1]
    knots = np.concatenate([u[n - k:n] - length, u, u[1:k + 1] + length])   # periodic: n + 2k + 1
    # Odd degree: the curve passes through the points at the knots; even, halfway between them.
    s = u[:n] if k % 2 else (u[:n] + u[1:]) / 2
    base = _base_bspline(knots, k, s)
    matrix = np.zeros((n, n))
    for j in range(base.shape[1]):
        matrix[:, j % n] += base[:, j]
    control = np.linalg.solve(matrix, p)
    extended = control[np.arange(n + k) % n]
    t = np.union1d(_samples(knots, 0.0, length, True), s)          # with the points themselves, exact
    return _base_bspline(knots, k, t) @ extended


def _de_control(p: np.ndarray, k: int) -> np.ndarray:
    n = len(p)
    knots = np.concatenate([np.zeros(k + 1), np.arange(1, n - k) / (n - k), np.ones(k + 1)])
    return _base_bspline(knots, k, _samples(knots, 0.0, 1.0, False)) @ p


def _closed_from_control(p: np.ndarray, k: int) -> np.ndarray:
    n = len(p)
    knots = np.arange(n + 2 * k + 1, dtype=float)
    extended = p[np.arange(n + k) % n]
    return _base_bspline(knots, k, _samples(knots, float(k), float(n + k), True)) @ extended


#: How the knots of a NURBS Curve are spread (Rhino's *knot spacing*).
MODES_NODES = ('uniform', 'chord length', 'square root of chord', 'by hand')
#: The highest degree of a NURBS Curve.
MAX_DEGREE_NURBS = 7


def _open_nodes(p: np.ndarray, k: int, mode: str, to_hand: np.ndarray) -> np.ndarray:
    """The knot vector of an open curve that starts and ends at its end points (*clamped*): k + 1 knots repeated at
    each end and n − k − 1 inside."""
    n = len(p)
    inner = n - k - 1
    if mode == 'by hand':
        v = to_hand
        if len(v) == n + k + 1:                      # the complete vector, as Rhino or Grasshopper give it
            v = v[k + 1:n]
        elif len(v) == n + k - 1:                    # Rhino's (without the first or the last)
            v = v[k:n - 1]
        if len(v) != inner:
            raise ShapeError(tr('With {n} points and degree {k} there are {i} inner knots (or the {t} of the '
                                  'full vector), and there are {m}.').format(n=n, k=k, i=inner, t=n + k + 1, m=len(to_hand)))
        if len(to_hand) in (n + k + 1, n + k - 1):
            from_, to = float(to_hand[0]), float(to_hand[-1])
        else:
            from_, to = 0.0, 1.0
        if inner and (np.any(np.diff(v) < 0) or v[0] < from_ or v[-1] > to):
            raise ShapeError(tr('Knots go from low to high, between {a} and {b}.').format(
                                   a=comma(f"{from_:g}"), b=comma(f"{to:g}")))
        _, repeated = np.unique(v, return_counts=True) if inner else (None, np.array([0]))
        if repeated.max() > k:
            raise ShapeError(tr('A knot repeats more than {k} times (the degree): the curve would break.').format(k=k))
        if to <= from_:
            raise ShapeError(tr('Knots go from low to high, between {a} and {b}.').format(
                                   a=comma(f"{from_:g}"), b=comma(f"{to:g}")))
        v = (v - from_) / (to - from_)
    elif mode == 'uniform':
        v = np.arange(1, inner + 1) / (inner + 1)
    else:
        # By chord length: the knots follow the distance between the points (where they are close, the knots too);
        # with the square root of the chord, halfway between that and uniform. The inner ones, averaged (de Boor).
        runs = np.linalg.norm(np.diff(p, axis=0), axis=1)
        if mode == 'square root of chord':
            runs = np.sqrt(runs)
        u = np.concatenate([[0.0], np.cumsum(np.maximum(runs, 1e-12))])
        u = u / u[-1]
        v = np.array([u[j:j + k].mean() for j in range(1, inner + 1)])
    return np.concatenate([np.zeros(k + 1), v, np.ones(k + 1)])


def nurbs(p: np.ndarray, weights: np.ndarray, k: int, mode: str = 'uniform', to_hand=(),
          closed: bool = False) -> np.ndarray:
    """The points of a NURBS curve (n control points, their weights and the degree k), sampled span by span."""
    n = len(p)
    if closed:
        if mode == 'by hand':
            raise ShapeError(tr('A closed curve spreads its own knots: choose another knot mode.'))
        runs = np.linalg.norm(np.diff(np.vstack([p, p[:1]]), axis=0), axis=1)
        if mode == 'uniform':
            runs = np.ones(n)
        elif mode == 'square root of chord':
            runs = np.sqrt(runs)
        u = np.concatenate([[0.0], np.cumsum(np.maximum(runs, 1e-12))])
        length = u[-1]
        # Periodic: the knots keep going round, and the first k points repeat at the end.
        knots = np.concatenate([u[n - k:n] - length, u, u[1:k + 1] + length])
        indices = np.arange(n + k) % n
        t = _samples(knots, knots[k], knots[n + k], True)
        t = np.append(t, knots[n + k])               # it closes: the last point is the first
    else:
        knots = _open_nodes(p, k, mode, np.asarray(to_hand, dtype=float))
        indices = np.arange(n)
        t = _samples(knots, 0.0, 1.0, False)
    which, base = _local_base(knots, k, t)
    which = indices[which]
    base = base * weights[which]
    return np.einsum("tj,tjc->tc", base, p[which]) / base.sum(axis=1)[:, None]


def discrete_curvature(curve: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The curvature of a curve given by its points (in order): at each inner point, (the point, the normal towards the
    centre of turn, the curvature: 1 / radius of the circle through it and its two neighbours)."""
    c = np.asarray(curve, dtype=float).reshape(-1, 3)
    if len(c) > 1:
        c = c[np.r_[True, np.linalg.norm(np.diff(c, axis=0), axis=1) > 1e-9]]   # without repeated points
    if len(c) < 3:
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0)
    a, b, d = c[:-2], c[1:-1], c[2:]
    ab, bd, ad = b - a, d - b, d - a
    area2 = np.linalg.norm(np.cross(ab, bd), axis=1)                     # twice the area of the triangle
    sides = np.linalg.norm(ab, axis=1) * np.linalg.norm(bd, axis=1) * np.linalg.norm(ad, axis=1)
    k = np.divide(2 * area2, sides, out=np.zeros(len(b)), where=sides > 1e-12)
    towards = bd / np.linalg.norm(bd, axis=1)[:, None] - ab / np.linalg.norm(ab, axis=1)[:, None]
    n = np.linalg.norm(towards, axis=1)
    normal = np.divide(towards, n[:, None], out=np.zeros_like(towards), where=n[:, None] > 1e-12)
    return b, normal, k


def curvature_comb(curve, length: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """The curvature comb of one or several curves (their points, in order; several: (curves, points, 3)): a hair at
    each point, perpendicular to the curve and outwards (away from its centre of turn), as long as it curves at that
    point. Returns (bases, tips). `length`: that of the hairs of normal curvature (by default, a fifth of the size of
    everything); all with the same scale, to compare them; the spikes of the corners are trimmed to three times the
    normal, so they do not hide the rest."""
    c = np.asarray(curve, dtype=float)
    curves = c.reshape(-1, c.shape[-2], 3) if c.ndim >= 3 else c.reshape(1, -1, 3)
    parts = [discrete_curvature(x) for x in curves]
    bases = np.concatenate([b for b, _, _ in parts]) if parts else np.zeros((0, 3))
    if not len(bases):
        return np.zeros((0, 3)), np.zeros((0, 3))
    normals = np.concatenate([n for _, n, _ in parts])
    k = np.concatenate([x for _, _, x in parts])
    normal_k = np.percentile(k, 90) if np.any(k > 0) else 0.0
    if normal_k <= 0:
        return bases, bases.copy()
    size_ = float(np.linalg.norm(np.ptp(curves.reshape(-1, 3), axis=0))) or 1.0
    scale = (length if length is not None else size_ / 5) / normal_k
    return bases, bases - normals * (np.minimum(k, 3 * normal_k) * scale)[:, None]


#: The kind of each anchor of a pen stroke: without handles, aligned handles, independent handles.
KINDS_ANCHOR = ("corner", "smooth", "broken")
MODES_NURBS = ('control points', 'pen')


def drawn_anchors(stroke) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The kept stroke of the pen ([[x, y, z, ex, ey, ez, sx, sy, sz, kind], …]: the anchor, its in handle, its out
    handle and its kind, 0 corner, 1 smooth, 2 broken) as (anchors, ins, outs, kinds)."""
    rows = [list(map(float, a)) for a in (stroke or [])]
    anchors = np.array([(f + [0.0] * 3)[:3] for f in rows], dtype=float).reshape(-1, 3)
    inputs = np.array([f[3:6] if len(f) >= 6 else f[:3] for f in rows], dtype=float).reshape(-1, 3)
    outputs = np.array([f[6:9] if len(f) >= 9 else f[:3] for f in rows], dtype=float).reshape(-1, 3)
    kinds = np.array([int(f[9]) if len(f) >= 10 else 0 for f in rows], dtype=int)
    return anchors, inputs, outputs, kinds


def pen(anchors: np.ndarray, inputs: np.ndarray, outputs: np.ndarray, closed: bool = False) -> np.ndarray:
    """The points of a pen stroke: between each anchor and the next, a cubic Bézier curve (the anchor, its out handle,
    the in handle of the other, the other anchor). Without handles, straight. Inside it is a NURBS of degree 3 with
    triple knots at the anchors."""
    n = len(anchors)
    pairs = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed and n > 2 else [])
    t = np.linspace(0, 1, SAMPLES_BY_RUN, endpoint=False)[:, None]
    b = np.hstack([(1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t ** 2 * (1 - t), t ** 3])      # Bernstein
    runs = [b @ np.stack([anchors[i], outputs[i], inputs[j], anchors[j]]) for i, j in pairs]
    final = anchors[0] if closed and n > 2 else anchors[-1]
    return np.vstack(runs + [final[None]]) if runs else anchors.copy()


def split_run(anchors, inputs, outputs, kinds, i: int, t: float):
    """A new anchor in the span that leaves anchor `i`, at its parameter `t`, without changing the shape (de
    Casteljau): the handles of both sides get shorter and the new anchor is smooth."""
    n = len(anchors)
    j = (i + 1) % n
    p0, p1, p2, p3 = anchors[i], outputs[i], inputs[j], anchors[j]
    a, b, c = p0 + (p1 - p0) * t, p1 + (p2 - p1) * t, p2 + (p3 - p2) * t
    d, e = a + (b - a) * t, b + (c - b) * t
    f = d + (e - d) * t                               # the point of the curve at t
    outputs, inputs = outputs.copy(), inputs.copy()
    outputs[i], inputs[j] = a, c
    straight = np.allclose([p1, p2], [p0, p3])            # a straight span: the new anchor, a corner
    where = i + 1
    return (np.insert(anchors, where, f, axis=0), np.insert(inputs, where, f if straight else d, axis=0),
            np.insert(outputs, where, f if straight else e, axis=0), np.insert(kinds, where, 0 if straight else 1))


def curve_pen(stroke, closed: bool = False, name: str | None = None) -> Data:
    """The curve of a pen stroke (drawn with «Edit curve», pen mode)."""
    anchors, inputs, outputs, _ = drawn_anchors(stroke)
    minimum = 3 if closed else 2
    if len(anchors) < minimum:
        raise ShapeError(tr('«{name}» has no path yet (it needs {n} anchors or more): select the node and '
                              'press «Edit curve» to draw it with the pen.').format(
                               name=name or tr('The curve'), n=minimum))
    return Data(pen(anchors, inputs, outputs, closed), (), name, kind=CLOSED_CURVE if closed else CURVE)


def points_in_nurbs(p: np.ndarray, weights: np.ndarray, k: int, knots: np.ndarray, us) -> np.ndarray:
    """The points of an open NURBS at the parameters `us` (between 0 and 1)."""
    us = np.clip(np.asarray(us, dtype=float).ravel(), 0.0, 1.0)
    which, base = _local_base(knots, k, us)
    base = base * weights[which]
    return np.einsum("tj,tjc->tc", base, p[which]) / base.sum(axis=1)[:, None]


def insert_node(p: np.ndarray, weights: np.ndarray, k: int, knots: np.ndarray,
                  u: float) -> tuple[np.ndarray, np.ndarray]:
    """One more control point at the parameter `u` of an open NURBS, without the curve changing shape (with those
    knots; Boehm's knot insertion): the k points around `u` are replaced by k + 1, halfway between their neighbours.
    Returns the new points and weights."""
    n = len(p)
    s = int(np.clip(np.searchsorted(knots, u, side="right") - 1, k, n - 1))
    h = np.column_stack([p * weights[:, None], weights])           # in homogeneous coordinates: exact with weights
    new = []
    for i in range(s - k + 1, s + 1):
        length = knots[i + k] - knots[i]
        a = (u - knots[i]) / length if length > 0 else 0.0
        new.append((1 - a) * h[i - 1] + a * h[i])
    h = np.vstack([h[:s - k + 1], new, h[s:]])
    return h[:, :3] / h[:, 3:], h[:, 3]


def remove_node(p: np.ndarray, weights: np.ndarray, k: int, knots: np.ndarray,
                i: int) -> tuple[np.ndarray, np.ndarray]:
    """An open NURBS without its inner knot number `i` (and with one control point fewer): the new points are those
    that most resemble the curve of before (least squares, in homogeneous coordinates: with weights, the same). If that
    knot had been inserted without changing the shape, the curve is again exactly the one of before. The ends do not
    move."""
    n = len(p)
    inner = list(knots[k + 1:n])
    if not 0 <= i < len(inner) or n - 1 <= k:
        raise ShapeError(tr('That knot cannot be removed (the curve would run out of points for its degree).'))
    new = np.concatenate([knots[:k + 1], np.delete(inner, i), knots[n:]])
    t = np.linspace(0.0, 1.0, max(200, 20 * n))
    h = np.column_stack([p * weights[:, None], weights])                  # the curve of before, in homogeneous coordinates
    before = _base_bspline(knots, k, t) @ h
    base = _base_bspline(new, k, t)
    # The fixed ends: the first and the last control point are those of before.
    fixed = base[:, [0, -1]] @ h[[0, -1]]
    middle, *_ = np.linalg.lstsq(base[:, 1:-1], before - fixed, rcond=None)
    h2 = np.vstack([h[:1], middle, h[-1:]])
    w = np.maximum(h2[:, 3], 1e-9)
    return h2[:, :3] / w[:, None], w


def curve_nurbs(points: Data, along: str | None = None, degree=3, weights=1.0, knots: str = 'uniform',
                items_nodes=None, closed: bool = False, name: str | None = None) -> Data:
    """A NURBS curve (*Nurbs Curve*): the points of a level are its **control points**, which attract it from outside
    like magnets; it removes that level (with more levels, one curve for each).

    - `degree`: 1 gives the polyline of the points; 2, parabolic arcs; 3, the usual smooth curve; more, tauter (up to 7,
      and at most the points minus one).
    - `weights`: how much each point attracts (1: normal; more, the curve comes closer; less, it moves away). One number
      for all or one per point. With weights, the NURBS makes exact arcs and circles.
    - `knots`: how the curve is spread between the points: «uniform» (evenly), «chord length» (by the distance between
      them), «square root of chord» (halfway) or «by hand» (a list, in `list`).
    - `closed`: the curve goes round (periodic: without an end or a break where it closes).

    Without a connected node, `points` are those drawn in the 3D view ([[x, y, z, weight], …]: «Edit curve»).
    """
    weights_own = None
    if not isinstance(points, Data):                 # drawn with the mouse, kept in the node
        list_ = list(points or [])
        minimum = 3 if closed else 2
        if len(list_) < minimum:
            raise ShapeError(tr('«{name}» has no points yet (it needs {n} or more): select the node and press '
                                  '«Edit curve» to place them, or connect some points.').format(
                                   name=name or tr('The curve'), n=minimum))
        weights_own = drawn_weights(list_)
        points = Data(drawn_points(list_), ("point",), name, kind=POINT)
    _require_kind(points, POINT, "point")
    if not points.levels:
        raise ShapeError(tr('“{name}” is a single point: a curve needs several.').format(
                               name=points._name()))
    along = along or points.levels[-1]
    if along not in points.levels:
        raise ShapeError(tr('“{along}” is not a level of “{name}” (its levels: {options}).').format(
                               along=tr(along), name=points._name(), options=', '.join((tr(n) for n in points.levels))))
    if knots not in MODES_NODES:
        raise ShapeError(tr('Knots can be: {options}.').format(options=", ".join(tr(m) for m in MODES_NODES)))
    axis = points.levels.index(along)
    n = points.sizes[along]
    minimum = 3 if closed else 2
    if n < minimum:
        raise ShapeError(tr('A NURBS curve needs at least {m} points in «{along}».').format(
                               m=minimum, along=tr(along)))
    if isinstance(weights, Data):
        require_numbers(weights, "weights")
    w = _values_items(weights, "weights")
    if len(w) == 1:
        w = np.repeat(w, n)
    if len(w) != n:
        raise ShapeError(tr('There are {n} control points and {m} weights: use one weight for all or one per point.').format(
                               n=n, m=len(w)))
    if weights_own is not None:
        w = w * weights_own
    if np.any(w <= 0):
        raise ShapeError(tr('Weights must be greater than 0 (1 is normal).'))
    k = max(1, min(integer(degree), MAX_DEGREE_NURBS, n - 1))
    to_hand = ()
    if knots == 'by hand':
        if items_nodes is None or (isinstance(items_nodes, str) and not items_nodes.strip()):
            raise ShapeError(tr('With knots «by hand», type the list of knots (from low to high, between 0 and 1).'))
        to_hand = _values_items(items_nodes, "list")
    v = np.moveaxis(points.values, axis, -2)
    remain = tuple(x for x in points.levels if x != along)
    if any(along in c.levels or x == along for x, c in points.variables.items() if x != along):
        raise ShapeError(tr('Joining into curves along “{along}” is not possible here yet: another level '
                              'changes size with it.').format(along=tr(along)))
    planes = v.reshape(-1, n, 3)
    curves = [nurbs(c, w, k, knots, to_hand, closed) for c in planes]
    length = max(len(c) for c in curves)
    # All with the same number of points (chord-length knots can give different spans): the padding
    # repeats the last one, as in the rest of the curves.
    curves = [np.concatenate([c, np.repeat(c[-1:], length - len(c), axis=0)]) for c in curves]
    output = np.stack(curves).reshape(v.shape[:-2] + (length, 3))
    variables = {x: c for x, c in points.variables.items() if x != along}
    return Data(output, remain, name, variables, {x: i for x, i in points.starts.items() if x != along},
                CLOSED_CURVE if closed else CURVE)


def curve_by_points(points: Data, along: str | None = None, smooth: bool = True, closed: bool = False,
                     name: str | None = None) -> Data:
    """Joins the points of a level into a curve: it removes that level (R3).

        curve_through_points(vertices [floor 30 × vertex 4], along="vertex")  → outlines [floor 30]

    `smooth`: a curve that passes through all the points (Catmull-Rom); if not, a polyline with its corners. Without
    `along`, the last level.
    """
    _require_kind(points, POINT, "point")
    if not points.levels:
        raise ShapeError(tr('“{name}” is a single point: a curve needs several.').format(
                               name=points._name()))
    along = along or points.levels[-1]
    if along not in points.levels:
        raise ShapeError(tr('“{along}” is not a level of “{name}” (its levels: {options}).').format(
                               along=tr(along), name=points._name(), options=', '.join((tr(n) for n in points.levels))))
    axis = points.levels.index(along)
    if points.sizes[along] < 2:
        raise ShapeError(tr('A curve needs at least 2 points in “{along}”.').format(along=tr(along)))
    v = np.moveaxis(points.values, axis, -2)  # (…, n, 3): the padding repeats the last point
    remain = tuple(n for n in points.levels if n != along)
    if any(along in c.levels or n == along for n, c in points.variables.items() if n != along):
        raise ShapeError(tr('Joining into curves along “{along}” is not possible here yet: another level '
                              'changes size with it.').format(along=tr(along)))
    variables = {n: c for n, c in points.variables.items() if n != along}
    holes = None
    if points.holes is not None:
        # The empty points (from a Filter without removing, or the end of a group of Split) are skipped: the curve
        # passes through those there are, and the padding repeats the last. With fewer than 2, the curve stays empty.
        shape = points.values.shape[:len(points.levels)]
        h = np.moveaxis(np.broadcast_to(points.holes, shape), axis, -1)          # (…, n)
        planes_v = v.reshape(-1, v.shape[-2], 3).copy()
        planes_h = h.reshape(-1, h.shape[-1])
        for k in range(len(planes_v)):
            good = planes_v[k][~planes_h[k]]
            if len(good):
                planes_v[k] = np.concatenate([good, np.repeat(good[-1:], len(planes_v[k]) - len(good), axis=0)])
        v = planes_v.reshape(v.shape)
        holes = (~h).sum(axis=-1) < 2
        if not holes.any():
            holes = None
    if smooth and v.shape[-2] > 2:
        v = _catmull_rom(v, closed)
    return Data(v, remain, name, variables, {n: i for n, i in points.starts.items() if n != along},
                CLOSED_CURVE if closed else CURVE, holes)


def transition(a: Data, b: Data, bulge=0.5, join: bool = True, name: str | None = None) -> Data:
    """A smooth curve that joins the end of `a` with the start of `b` (*Blend Curve*).

    It leaves `a` and reaches `b` following their directions (without breaks). `bulge`: how much the curve stretches
    before turning (0.1: almost straight; 1: very wide). With `join`, the result is a single curve: `a`, the transition
    and `b` (the whole profile of a ribbon).
    """
    for c, role in ((a, "a"), (b, "b")):
        if not isinstance(c, Data) or c.kind is None or not c.kind.curve or c.kind.closed:
            raise ShapeError(tr("The transition curve's “{role}” should be an open curve.").format(role=tr(role)))
    t = np.linspace(0, 1, 32)[:, None]
    bezier = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3)

    def fillet(ca, cb, k):
        p0, p3 = ca[..., -1, :], cb[..., 0, :]
        ta, tb = ca[..., -1, :] - ca[..., -2, :], cb[..., 1, :] - cb[..., 0, :]
        ta = ta / np.maximum(np.linalg.norm(ta, axis=-1, keepdims=True), 1e-12)
        tb = tb / np.maximum(np.linalg.norm(tb, axis=-1, keepdims=True), 1e-12)
        length = np.linalg.norm(p3 - p0, axis=-1, keepdims=True) * np.asarray(k, dtype=float)[..., None]
        p1, p2 = p0 + ta * length, p3 - tb * length
        curve = sum(w * q[..., None, :] for w, q in zip(bezier, (p0, p1, p2, p3)))
        if not join:
            return curve
        ca, cb = np.broadcast_to(ca, curve.shape[:-2] + ca.shape[-2:]), np.broadcast_to(cb, curve.shape[:-2] + cb.shape[-2:])
        return np.concatenate([ca[..., :-1, :], curve, cb[..., 1:, :]], axis=-2)

    return apply(fillet, a, b, _data(bulge), name=name, kind=CURVE)


def smooth_count(n: int, closed: bool) -> int:
    """How many points the smooth curve through n points has (that of `_catmull_rom`), to know it before making it."""
    runs = n if closed else n - 1
    return runs * max(4, SAMPLES // runs) + (0 if closed else 1)


def _catmull_rom(p: np.ndarray, closed: bool) -> np.ndarray:
    """A smooth curve through the points p (…, n, 3), sampled with about 64 points."""
    n = p.shape[-2]
    runs = n if closed else n - 1
    by_run = max(4, SAMPLES // runs)
    if closed:
        ext = np.concatenate([p[..., -1:, :], p, p[..., :2, :]], axis=-2)
    else:
        ext = np.concatenate([2 * p[..., :1, :] - p[..., 1:2, :], p, 2 * p[..., -1:, :] - p[..., -2:-1, :]], axis=-2)
    t = np.linspace(0, 1, by_run, endpoint=False)[:, None]
    t2, t3 = t * t, t * t * t
    parts = []
    for i in range(runs):
        p0, p1, p2, p3 = (ext[..., i + k, None, :] for k in range(4))
        parts.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                             + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        parts.append(p[..., -1:, :])
    return np.concatenate(parts, axis=-2)


#: How points are put on a curve (Points on curve):
#: parts: N equal parts · every: one every so much distance · fraction: 0.5 is the middle · distance: so far from the
#: start (in the unit chosen in the window; the engine, in metres).
MODES_POINTS = ('parts', 'every', 'fraction', 'distance')


def _lengths(curve: Data) -> tuple[np.ndarray, np.ndarray]:
    """The points of the curve (the closed one, with its first point repeated at the end) and its accumulated length."""
    c = curve.values
    if curve.kind.closed:
        c = np.concatenate([c, c[..., :1, :]], axis=-2)
    runs = np.linalg.norm(np.diff(c, axis=-2), axis=-1)            # (…, n-1)
    accumulated = np.concatenate([np.zeros(runs.shape[:-1] + (1,)), np.cumsum(runs, axis=-1)], axis=-1)
    return c, accumulated


def _in_lengths(c: np.ndarray, accumulated: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """The points of each curve c (…, n, 3) that are at the lengths `wanted` (…, m) from its start."""
    m = wanted.shape[-1]
    planes = c.reshape(-1, c.shape[-2], 3)
    cum_planes = accumulated.reshape(-1, accumulated.shape[-1])
    search_planes = np.broadcast_to(wanted, accumulated.shape[:-1] + (m,)).reshape(-1, m)
    output = np.empty((planes.shape[0], m, 3))
    for k in range(planes.shape[0]):
        for axis in range(3):
            output[k, :, axis] = np.interp(search_planes[k], cum_planes[k], planes[k, :, axis])
    return output.reshape(c.shape[:-2] + (m, 3))


def _values_items(values, role: str) -> np.ndarray:
    """One or several numbers: 0,5 · «0,25; 0,5; 0,75» · [2, 4] · a data (all its values)."""
    if isinstance(values, Data):
        v = np.asarray(values.values, dtype=float).ravel()
    elif isinstance(values, str):
        from .values import read_numbers
        numbers = read_numbers(values)
        if numbers is None:
            raise ShapeError(tr('“{role}” should be one or more numbers (separated by “;”).').format(
                                   role=tr(role)))
        v = np.array(numbers, dtype=float)
    else:
        v = np.asarray(values, dtype=float).ravel()
    if not len(v):
        raise ShapeError(tr('“{role}” is empty: at least one number is needed.').format(role=tr(role)))
    return v


def _require_curve(curve, role: str = "curve") -> None:
    if not isinstance(curve, Data) or curve.kind is None or not curve.kind.curve:
        name = curve._name() if isinstance(curve, Data) else tr(role)
        raise ShapeError(tr('“{name}” should be a curve, and it is {what_is}.').format(
                               name=name, what_is=_what_is(curve) if isinstance(curve, Data) else tr('a value')))


def _where_on_curve(curve: Data, mode: str, count, distance, positions, level: str):
    """Where, on each curve, by the modes of Points on curve: (points of the curve, accumulated length, wanted lengths
    (…, m), whether it is a single position). Points on curve and Tangent share it."""
    _require_curve(curve)
    mode = 'distance' if mode == "metros" else mode        # the name of before
    if mode not in MODES_POINTS:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MODES_POINTS)))
    c, accumulated = _lengths(curve)
    total = accumulated[..., -1:]
    closed = curve.kind.closed
    a_only_point = False
    if mode == 'parts':
        count = integer(count)
        if count < 2:
            raise ShapeError(tr('Dividing a curve needs at least 2 points ({count} arrived).').format(
                                   count=count))
        _require_size_({**curve.sizes, level: count}, tr('Dividing the curve'))
        wanted = total * np.linspace(0, 1, count, endpoint=not closed)
    elif mode == 'every':
        step = float(_data(distance).values) if not isinstance(distance, (int, float)) else float(distance)
        if not step > 0:
            raise ShapeError(tr('The distance between points must be greater than 0.'))
        long_more = float(total.max()) if total.size else 0.0
        count = int(np.floor(long_more / step + 1e-9)) + 1
        if closed and count > 1 and abs((count - 1) * step - long_more) < 1e-9 * max(long_more, 1):
            count -= 1                                       # in a closed one, the last would be the first
        _require_size_({**curve.sizes, level: count}, tr('Dividing the curve'))
        # The shorter ones, with fewer points: those that do not fit stay at their end.
        wanted = np.minimum(np.arange(count) * step, total)
    else:
        v = _values_items(positions, "positions")
        if mode == 'fraction':
            v = np.mod(v, 1.0) if closed else np.clip(v, 0.0, 1.0)
            wanted = total * v
        else:                                                   # distance: negative ones, from the end
            wanted = np.where(v < 0, total + v, v)
            wanted = np.mod(wanted, total) if closed else np.clip(wanted, 0.0, total)
        a_only_point = len(v) == 1
        if not a_only_point:
            _require_size_({**curve.sizes, level: len(v)}, tr('Dividing the curve'))
    return c, accumulated, wanted, a_only_point


def curve_points(curve: Data, count=10, level: str = "point", name: str | None = None,
                    mode: str = 'parts', distance=1.0, positions=0.5) -> Data:
    """Points on a curve (*Divide Curve*, *Divide Distance* and *Point On Curve* in one):

    - «parts»: divides it into `count` points spread evenly (in an open one both ends go in; in a closed one, the
      spreading goes back to the start without repeating it);
    - «every»: a point every `distance` metres, from the start;
    - «fraction»: at the `positions` from 0 (the start) to 1 (the end): 0.5 is the middle;
    - «distance»: at `positions` metres from the start (negative: from the end).

    With several points it creates the level `level`; with a single position, one point per curve (no new level).
    """
    c, accumulated, wanted, a_only_point = _where_on_curve(curve, mode, count, distance, positions, level)
    points = _in_lengths(c, accumulated, wanted)
    if a_only_point:
        return curve.derived(points[..., 0, :], name, POINT)
    return curve.derived(points, name, POINT, (level,))


# --- Tangents, flipping and cutting curves -------------------------------------------------

#: What direction Tangent gives: that of the curve, or its perpendicular in the curve's plane (to the left of the
#: direction it goes, looking at the plane from above, from the front or from the right).
WHAT_TANGENT = ('tangent', "normal")


def _curve_plane(c: np.ndarray) -> np.ndarray:
    """The normal of a curve's plane (n, 3), looking as that plane is looked at: from above if it is horizontal, from
    the front (from -y) if it is an elevation, from the right (+x) if it is a side elevation. So «the left» of the curve
    does not depend on its shape. If it is straight: the vertical (or, if the line is vertical, looking from the front)."""
    centre = c.mean(axis=0)
    area = np.cross(c[:-1] - centre, c[1:] - centre).sum(axis=0)
    n = float(np.linalg.norm(area))
    if n <= 1e-9 * max(float(np.ptp(c, axis=0).max()) ** 2, 1e-12):
        d = c[-1] - c[0]
        return np.array([0.0, -1.0, 0.0]) if abs(d[2]) > 0.9 * (np.linalg.norm(d) or 1) else np.array([0.0, 0.0, 1.0])
    normal = area / n
    axis = int(np.argmax(np.abs(normal)))
    towards = {0: 1.0, 1: -1.0, 2: 1.0}[axis]                # side elevation: +x · elevation: -y · plan: +z
    return normal if normal[axis] * towards > 0 else -normal


def _directions(c: np.ndarray, accumulated: np.ndarray, wanted: np.ndarray, closed: bool = False) -> np.ndarray:
    """The (unit) tangent of each curve at the wanted lengths: from the point a little before to the point a little
    after (centred: on a smooth curve, the right tangent even if it falls on a vertex; at a corner, the bisector)."""
    m = wanted.shape[-1]
    planes = c.reshape(-1, c.shape[-2], 3)
    cum_planes = accumulated.reshape(-1, accumulated.shape[-1])
    search_planes = np.broadcast_to(wanted, accumulated.shape[:-1] + (m,)).reshape(-1, m)
    output = np.zeros((planes.shape[0], m, 3))
    for k in range(planes.shape[0]):
        points, cum = planes[k], cum_planes[k]
        total = float(cum[-1])
        lengths = np.diff(cum)
        if total <= 1e-12:
            continue
        h = 0.5 * float(np.median(lengths[lengths > 1e-12]))       # half a span, on each side
        s = search_planes[k]
        if closed:
            before, after = np.mod(s - h, total), np.mod(s + h, total)
        else:
            before, after = np.clip(s - h, 0, total), np.clip(s + h, 0, total)
        at = lambda x: np.stack([np.interp(x, cum, points[:, e]) for e in range(3)], axis=-1)
        d = at(after) - at(before)
        length = np.linalg.norm(d, axis=-1, keepdims=True)
        output[k] = np.divide(d, length, out=np.zeros_like(d), where=length > 1e-12)
    return output.reshape(c.shape[:-2] + (m, 3))


def tangent(curve: Data, what: str = 'tangent', mode: str = 'fraction', count=10, distance=1.0,
             positions=0.5, level: str = "point", name: str | None = None) -> Data:
    """The direction of a curve at some points (*Tangent*, *Evaluate Curve*): a vector of length 1, with the same
    modes as Points on curve (at the same positions it gives the same points). `what`: «tangent» (where the curve goes)
    or «normal» (its perpendicular in the curve's plane, to the left)."""
    if what not in WHAT_TANGENT:
        raise ShapeError(tr('«what» can be: {options}.').format(options=", ".join(tr(q) for q in WHAT_TANGENT)))
    c, accumulated, wanted, a_only = _where_on_curve(curve, mode, count, distance, positions, level)
    directions = _directions(c, accumulated, wanted, curve.kind.closed)
    if what == "normal":
        planes = c.reshape(-1, c.shape[-2], 3)
        normals = np.stack([_curve_plane(_without_padding(p)) for p in planes]).reshape(c.shape[:-2] + (1, 3))
        directions = np.cross(normals, directions)
        length = np.linalg.norm(directions, axis=-1, keepdims=True)
        directions = np.divide(directions, length, out=np.zeros_like(directions), where=length > 1e-12)
    if a_only:
        return curve.derived(directions[..., 0, :], name, VECTOR)
    return curve.derived(directions, name, VECTOR, (level,))


def _without_padding(c: np.ndarray) -> np.ndarray:
    """A curve without the repeated points at the end (the padding of the shorter curves of a data)."""
    n = len(c)
    while n > 2 and np.allclose(c[n - 1], c[n - 2]):
        n -= 1
    return c[:n]


def reverse_curve(curve: Data, direction=None, name: str | None = None) -> Data:
    """Each curve reversed (*Flip Curve*): it starts where it used to end. With a `direction` (a vector), only those
    that go against it, so that all go the same way (before a Loft surface; if not, it comes out twisted); in the closed
    ones, only those that turn the other way seen from it."""
    _require_curve(curve)
    closed = curve.kind.closed
    guide = None
    if direction is not None:
        guide = np.asarray(_point(direction, "direction").values, dtype=float).reshape(-1, 3)
        if guide.shape[0] != 1:
            raise ShapeError(tr('The direction must be a single vector (all curves, towards the same side).'))
        guide = guide[0]
        if np.linalg.norm(guide) < 1e-12:
            raise ShapeError(tr('The direction cannot be zero (0, 0, 0).'))

    def give_turn(v):
        planes = v.reshape(-1, v.shape[-2], 3).copy()
        for k, p in enumerate(planes):
            real = _without_padding(p)
            n = len(real)
            if guide is not None:
                goes = _curve_plane(real) if closed else real[-1] - real[0]
                if float(np.dot(goes, guide)) >= 0:
                    continue                            # it already goes that way
            if closed:                                 # the same first point, turning the other way
                real = np.vstack([real[:1], real[1:][::-1]])
            else:
                real = real[::-1]
            planes[k, :n] = real
            planes[k, n:] = real[-1]                    # the padding, again at the end
        return planes.reshape(v.shape)

    return curve.derived(give_turn(curve.values), name, curve.kind)


#: Where a curve is cut (Cut curve): the modes of Points on curve and, also, where some points fall.
CUT_MODES = ('parts', 'every', 'fraction', 'distance', 'at points')


def cut_curve(curve: Data, mode: str = 'parts', count=4, distance=1.0, positions=0.5, points=None,
                 level: str = "segment", name: str | None = None) -> Data:
    """Each curve cut into pieces (*Shatter*, *Split Curve*), in a new level (`level`):

    - «parts»: into `count` equal pieces;
    - «every»: pieces of `distance` (the last one, what is left);
    - «fraction» or «distance»: cut at those `positions` (as in Points on curve; negative, from the end);
    - «at points»: where some `points` fall (on the curve or near: the closest point of the curve).

    On a closed curve, the cuts spread it going round (a single cut: open there)."""
    _require_curve(curve)
    if mode not in CUT_MODES:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in CUT_MODES)))
    c, accumulated = _lengths(curve)
    closed = curve.kind.closed
    planes = c.reshape(-1, c.shape[-2], 3)
    cum_planes = accumulated.reshape(-1, accumulated.shape[-1])
    cuts_of: list[np.ndarray] = []
    for k, (p, cum) in enumerate(zip(planes, cum_planes)):
        total = float(cum[-1])
        if mode == 'parts':
            n = integer(count)
            if n < 1:
                raise ShapeError(tr('Cutting a curve needs 1 or more pieces (got {n}).').format(n=n))
            cuts = np.linspace(0, total, n + 1)
        elif mode == 'every':
            step = float(_data(distance).values) if not isinstance(distance, (int, float)) else float(distance)
            if not step > 0:
                raise ShapeError(tr('The length of each piece must be greater than 0.'))
            cuts = np.append(np.arange(0, total - 1e-9, step), total)
        else:
            if mode == 'at points':
                if points is None:
                    raise ShapeError(tr('«points» is missing: where the curve is cut.'))
                v = _length_more_nearest(p, cum, np.asarray(_point(points, "points").values, float).reshape(-1, 3))
            else:
                v = _values_items(positions, "positions")
                v = total * (np.mod(v, 1.0) if closed else np.clip(v, 0, 1)) if mode == 'fraction' else \
                    np.where(v < 0, total + v, v)
                v = np.mod(v, total) if closed else np.clip(v, 0, total)
            v = np.unique(np.round(v, 9))
            if closed:                                 # from cut to cut, going round
                cuts = np.append(v, v[0] + total) if len(v) else np.array([0.0, total])
            else:
                cuts = np.unique(np.concatenate([[0.0], v, [total]]))
        cuts_of.append(cuts)
    pieces = max(len(x) - 1 for x in cuts_of)
    _require_size_({**curve.sizes, level: pieces}, tr('The curve pieces'))
    output = np.empty((len(planes), pieces, SAMPLES, 3))
    for k, (p, cum, cuts) in enumerate(zip(planes, cum_planes, cuts_of)):
        total = float(cum[-1]) or 1.0
        for j in range(pieces):
            a, b = (cuts[j], cuts[j + 1]) if j < len(cuts) - 1 else (cuts[-1], cuts[-1])  # those left over: a point
            t = np.linspace(a, b, SAMPLES)
            t = np.mod(t, total) if closed else t
            output[k, j] = np.stack([np.interp(t, cum, p[:, e]) for e in range(3)], axis=-1)
    return curve.derived(output.reshape(curve.values.shape[:-2] + (pieces, SAMPLES, 3)), name, CURVE, (level,))


def _length_more_nearest(p: np.ndarray, cum: np.ndarray, points: np.ndarray) -> np.ndarray:
    """The length, from the start of the curve p, of the point of the curve closest to each of `points`."""
    a, b = p[:-1], p[1:]
    ab = b - a
    largo2 = np.maximum((ab * ab).sum(axis=1), 1e-24)
    output = []
    for q in points:
        t = np.clip(((q - a) * ab).sum(axis=1) / largo2, 0, 1)
        d = np.linalg.norm(a + ab * t[:, None] - q, axis=1)
        i = int(np.argmin(d))
        output.append(cum[i] + t[i] * (cum[i + 1] - cum[i]))
    return np.array(output)


# --- Superficies ----------------------------------------------------------------

SEGMENTS_BETWEEN_SECTIONS = 8  # rows of the grid between two sections of a smooth surface


@lru_cache(maxsize=64)
def kind_surface(rows: int, columns: int) -> Kind:
    """The kind of a surface of rows × columns points: its quadrilaterals."""
    from .data import MAX_ELEMENTS, _number
    if (rows - 1) * (columns - 1) > MAX_ELEMENTS:   # (each face is a Python tuple: with tens of millions, running out
        raise ShapeError(tr(                         # of memory there closed the program instead of saying so)
            'The surface would have {n} faces ({rows} × {columns} points): too many to calculate at once (the '
            'maximum is {maximum}). Is there an extra number?').format(
            n=_number((rows - 1) * (columns - 1)), rows=_number(rows), columns=_number(columns),
            maximum=_number(MAX_ELEMENTS)))
    faces = tuple(
        (i * columns + j, i * columns + j + 1, (i + 1) * columns + j + 1, (i + 1) * columns + j)
        for i in range(rows - 1) for j in range(columns - 1)
    )
    return Kind("surface", faces, grid=(rows, columns))


def _grid(data: Data) -> np.ndarray:
    """The points of a surface as a grid: (…, rows, columns, 3)."""
    f, c = data.kind.grid
    return data.values.reshape(data.values.shape[:-2] + (f, c, 3))


def rounded_rectangle(width, height, radius=1.0, origin=(0.0, 0.0, 0.0), name: str | None = None) -> Data:
    """The outline of a rectangle in plan with rounded corners (*Fillet*): a closed curve.
    `origin`: the bottom left corner, as in Rectangle."""
    by_corner = SAMPLES // 4

    def outline(a, h, r, o):
        a, h, r = np.broadcast_arrays(np.asarray(a, float), np.asarray(h, float), np.asarray(r, float))
        r = np.clip(r, 0.0, np.minimum(a, h) / 2)
        angles = np.linspace(0, np.pi / 2, by_corner)
        corners = []
        for k, (cx, cy) in enumerate(((1, 1), (0, 1), (0, 0), (1, 0))):       # anticlockwise, from the top right
            centre_x = np.where(cx, a - r, r)[..., None]
            centre_y = np.where(cy, h - r, r)[..., None]
            ang = angles + k * np.pi / 2
            corners.append(np.stack([centre_x + r[..., None] * np.cos(ang), centre_y + r[..., None] * np.sin(ang),
                                      np.zeros_like(centre_x + ang)], axis=-1))
        return np.concatenate(corners, axis=-2) + _to(o, corners[0])

    return apply(outline, _data(width), _data(height), _data(radius), _point(origin, "origin"), name=name,
                   kind=CLOSED_CURVE)


RINGS_CAP = 8  # rows of the surface of a cap, from the centre to the edge


def cap(curve: Data, name: str | None = None, holes=None) -> Data:
    """The surface that closes each closed curve (*Patch*, *Boundary Surface*): a roof, a free-form slab. It goes
    from the centre of the curve to the edge, in rings: if the curve is not flat, the cap follows it without creases. With
    `holes` (closed curves inside: a courtyard, a skylight), a flat slab with holes."""
    if holes is not None:
        return _cap_with_holes(curve, holes, name)
    if curve.kind is None or not curve.kind.curve:
        raise ShapeError(tr('“{name}” should be a curve, and it is {what_is}.').format(
                               name=curve._name(), what_is=_what_is(curve)))

    def rings(c):
        edge = np.concatenate([c, c[..., :1, :]], axis=-2)               # closed: the first point, at the end
        centre = c.mean(axis=-2, keepdims=True)
        t = np.linspace(0.0, 1.0, RINGS_CAP)[:, None, None]
        rows = centre[..., None, :, :] + (edge[..., None, :, :] - centre[..., None, :, :]) * t
        return rows.reshape(*c.shape[:-2], -1, 3)

    kind = kind_surface(RINGS_CAP, curve.values.shape[-2] + 1)
    return curve.derived(rings(curve.values), name, kind)


def _inside(p: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Which 2D points (m, 2) fall inside a 2D polygon (n, 2) (even or odd crossings)."""
    x, y = p[:, 0][:, None], p[:, 1][:, None]
    a, b = polygon, np.roll(polygon, -1, axis=0)
    crosses = ((a[:, 1] > y) != (b[:, 1] > y)) & \
        (x < (b[:, 0] - a[:, 0]) * (y - a[:, 1]) / np.where(b[:, 1] == a[:, 1], 1e-30, b[:, 1] - a[:, 1]) + a[:, 0])
    return crosses.sum(axis=1) % 2 == 1


def _cap_with_holes(curve: Data, holes, name: str | None) -> Data:
    """A flat slab: the outline with its holes, in triangles (constrained Delaunay) and some points inside so no very
    long triangles are left."""
    from . import vtk_light as vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    from .meshes import kind_mesh
    _require_curve(curve)
    if curve.levels or not curve.kind.closed:
        raise ShapeError(tr('With holes, the outline must be a single closed curve.'))
    if not isinstance(holes, Data) or holes.kind is None or not holes.kind.closed:
        raise ShapeError(tr('The holes must be closed curves (inside the outline).'))
    outline = _without_padding(np.asarray(curve.values, dtype=float))
    inner = [_without_padding(h) for h in np.asarray(holes.values, dtype=float).reshape(-1, holes.values.shape[-2], 3)]
    normal = _curve_plane(outline)
    origin = outline.mean(axis=0)
    e1 = np.array([1.0, 0, 0]) if abs(normal[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = e1 - normal * (e1 @ normal)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(normal, e1)
    plane = lambda q: np.stack([(q - origin) @ e1, (q - origin) @ e2], axis=-1)

    def with_direction(q2, counterclockwise):
        area = (q2[:, 0] * np.roll(q2[:, 1], -1) - np.roll(q2[:, 0], -1) * q2[:, 1]).sum()
        return q2 if (area > 0) == counterclockwise else q2[::-1]
    edge = with_direction(plane(outline), True)
    cutouts = [with_direction(plane(h), False) for h in inner]
    for h in cutouts:
        if not _inside(h, edge).all():
            raise ShapeError(tr('A hole goes outside the outline: it must stay inside.'))
    # Points inside, on a grid, away from the edges; the edges, in segments of the same size (a long
    # segment with grid points almost on top cannot be respected).
    side = float(np.ptp(edge, axis=0).max()) / 24

    def densify(q2):
        new = []
        for a, b in zip(q2, np.roll(q2, -1, axis=0)):
            parts = max(1, int(np.ceil(np.linalg.norm(b - a) / (side * 0.7))))
            new.append(a + (b - a) * (np.arange(parts) / parts)[:, None])
        return np.vstack(new)
    edge = densify(edge)
    cutouts = [densify(h) for h in cutouts]
    xs = np.arange(edge[:, 0].min() + side / 2, edge[:, 0].max(), side)
    ys = np.arange(edge[:, 1].min() + side / 2, edge[:, 1].max(), side)
    grid_ = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
    remain = _inside(grid_, edge)
    for h in cutouts:
        remain &= ~_inside(grid_, h)
    all_edges = [edge] + cutouts
    points_edge = np.vstack(all_edges)
    if remain.any():
        nearest = np.min(np.linalg.norm(grid_[remain][:, None] - points_edge[None], axis=2), axis=1)
        grid_ = grid_[remain][nearest > side * 0.4]
    else:
        grid_ = np.zeros((0, 2))
    p2 = np.vstack([points_edge, grid_])
    points_vtk = vtk.vtkPoints()
    points_vtk.SetData(numpy_to_vtk(np.ascontiguousarray(np.column_stack([p2, np.zeros(len(p2))])), deep=True))
    input_ = vtk.vtkPolyData()
    input_.SetPoints(points_vtk)
    polygons = vtk.vtkCellArray()
    start = 0
    for b in all_edges:                             # the constrained edges: the outline and each hole
        polygon = vtk.vtkPolygon()
        polygon.GetPointIds().SetNumberOfIds(len(b))
        for k in range(len(b)):
            polygon.GetPointIds().SetId(k, start + k)
        polygons.InsertNextCell(polygon)
        start += len(b)
    source = vtk.vtkPolyData()
    source.SetPoints(points_vtk)
    source.SetPolys(polygons)
    delaunay = vtk.vtkDelaunay2D()
    delaunay.SetInputData(input_)
    delaunay.SetSourceData(source)
    delaunay.Update()
    output = delaunay.GetOutput()
    if output.GetNumberOfPolys() == 0:
        raise ShapeError(tr('The outline with its holes could not be filled (do they cross?).'))
    faces = vtk_to_numpy(output.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    q = vtk_to_numpy(output.GetPoints().GetData())[:, :2]
    vertices = origin + q[:, :1] * e1 + q[:, 1:2] * e2
    return Data(vertices, (), name, kind=kind_mesh(faces))


def curve_part(curve: Data, from_=0.0, to=1.0, name: str | None = None) -> Data:
    """The span of each curve between two fractions of its length (from 0 to 1), as *Sub Curve*: an arc of a circle.

    `from_` and `to` can have levels (two spans of the same circle: `[half 2]`).
    """
    if curve.kind is None or not curve.kind.curve:
        raise ShapeError(tr('“{name}” should be a curve, and it is {what_is}.').format(
                               name=curve._name(), what_is=_what_is(curve)))
    closed = curve.kind.closed

    def run(g, a, b):
        g, a, b = np.broadcast_arrays(g, np.asarray(a, float)[..., None, None], np.asarray(b, float)[..., None, None])
        a, b = a[..., 0, 0], b[..., 0, 0]
        shape = g.shape[:-2]
        planes = g.reshape(-1, *g.shape[-2:])
        # A part of a straight line is a straight line: its two ends are enough.
        samples = 2 if not closed and g.shape[-2] == 2 else SAMPLES
        output = np.empty((len(planes), samples, 3))
        for k, (points, x, y) in enumerate(zip(planes, a.reshape(-1), b.reshape(-1))):
            if closed:
                points = np.vstack([points, points[:1]])
            lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))])
            total = lengths[-1] or 1.0
            if closed:                         # on a closed curve, «to» before «from» goes round
                y = y + 1.0 if y < x else y
                t = np.mod(np.linspace(x, y, samples), 1.0 + 1e-12)
            else:
                x, y = sorted(np.clip([x, y], 0.0, 1.0))
                t = np.linspace(x, y, samples)
            t = t * total
            output[k] = np.stack([np.interp(t, lengths, points[:, i]) for i in range(3)], axis=-1)
        return output.reshape(*shape, samples, 3)

    return apply(run, curve, _data(from_), _data(to), name=name, kind=CURVE)


def surface_by_sections(curves: Data, along: str | None = None, smooth: bool = True,
                             name: str | None = None, closed: bool = False) -> Data:
    """A surface through the curves of a level, in their order (Loft): it removes that level.

        loft(hoops [section 3], along="section")  → the skin of a tower

    The curves must have the same number of points (circles and smooth curves have it). `smooth`: a surface that passes
    smoothly through the sections; if not, straight spans between them. Rectangles (panels, their openings) and polygons
    (the hexagons of a Grid) count as closed curves: between two of them, the sides of a frustum.
    """
    if curves.kind is RECTANGLE or (curves.kind is not None and curves.kind.polygon and curves.kind.name == "polygon"):
        curves = Data(curves.values, curves.levels, curves.name, curves.variables, curves.starts, CLOSED_CURVE,
                      curves.holes)
    if curves.kind is None or not curves.kind.curve:
        raise ShapeError(tr('“{name}” should be curves (the sections), and it is {what_is}.').format(
                               name=curves._name(), what_is=_what_is(curves)))
    if not curves.levels:
        raise ShapeError(tr('“{name}” is a single curve: at least two sections are needed.').format(
                               name=curves._name()))
    along = along or curves.levels[-1]
    if along not in curves.levels:
        raise ShapeError(tr('“{along}” is not a level of “{name}” (its levels: {options}).').format(
                               along=tr(along), name=curves._name(), options=', '.join((tr(n) for n in curves.levels))))
    if curves.sizes[along] < 2:
        raise ShapeError(tr('A surface needs at least 2 sections in “{along}”.').format(
                               along=tr(along)))
    if along in curves.variables or any(along in c.levels for c in curves.variables.values()):
        raise ShapeError(tr('The number of sections in “{name}” changes: not possible yet.').format(
                               name=curves._name()))
    axis = curves.levels.index(along)
    v = np.moveaxis(curves.values, axis, -3)                     # (…, secciones, puntos, 3)
    if curves.kind.closed:                                       # close the skin: repeat the first point
        v = np.concatenate([v, v[..., :1, :]], axis=-2)
    sections = v.shape[-3]
    if closed and sections < 3:
        raise ShapeError(tr('Closing the surface (the last section back to the first) needs at least 3 sections.'))
    # Its size before making it (each section becomes several rows): with many sections, the memory ran out in the
    # middle of making it, and the program closed instead of saying so.
    kind_surface((sections + closed - 1) * SEGMENTS_BETWEEN_SECTIONS + 1, v.shape[-2])
    if sections > 2 and smooth:
        # Along the sections, the same smooth curve as «Curve through points» (closed: it goes round).
        planes = np.moveaxis(v, -3, -2)                           # (…, puntos, secciones, 3)
        rows = _catmull_rom_n(planes, SEGMENTS_BETWEEN_SECTIONS, closed)
        v = np.moveaxis(rows, -2, -3)
    else:
        if closed:                                               # the first section again, at the end
            v = np.concatenate([v, v[..., :1, :, :]], axis=-3)
            sections += 1
        t = np.linspace(0, 1, SEGMENTS_BETWEEN_SECTIONS + 1)[:, None, None]
        runs = [v[..., k, None, :, :] * (1 - t) + v[..., k + 1, None, :, :] * t for k in range(sections - 1)]
        v = np.concatenate([tr[..., :-1, :, :] for tr in runs] + [v[..., -1:, :, :]], axis=-3)
    f, c = v.shape[-3], v.shape[-2]
    remain = tuple(n for n in curves.levels if n != along)
    holes = None if curves.holes is None else np.moveaxis(curves.holes, axis, -1).any(axis=-1)
    return Data(v.reshape(v.shape[:-3] + (f * c, 3)), remain, name,
                {n: k for n, k in curves.variables.items() if n != along},
                {n: i for n, i in curves.starts.items() if n != along}, kind_surface(f, c), holes)


def _catmull_rom_n(p: np.ndarray, by_run: int, closed: bool = False) -> np.ndarray:
    """Like `_catmull_rom`, with `per_span` points per span (p: …, n, 3); closed: it goes back to the first (which
    repeats at the end)."""
    n = p.shape[-2]
    if closed:
        ext = np.concatenate([p[..., -1:, :], p, p[..., :2, :]], axis=-2)
    else:
        ext = np.concatenate([2 * p[..., :1, :] - p[..., 1:2, :], p, 2 * p[..., -1:, :] - p[..., -2:-1, :]], axis=-2)
    t = np.linspace(0, 1, by_run, endpoint=False)[:, None]
    parts = []
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = (ext[..., i + k, None, :] for k in range(4))
        parts.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                             + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    parts.append(p[..., :1, :] if closed else p[..., -1:, :])
    return np.concatenate(parts, axis=-2)


def _triangulate_plan(p: np.ndarray) -> list[tuple[int, int, int]]:
    """The triangles that cover a flat polygon (even if concave, like an L), by ears."""
    normal = np.cross(np.roll(p, -1, axis=0) - p, p - p.mean(axis=0)).sum(axis=0)
    if np.linalg.norm(normal) < 1e-12:
        normal = np.array([0.0, 0.0, 1.0])
    normal = normal / np.linalg.norm(normal)
    u = np.cross(normal, [1.0, 0, 0] if abs(normal[0]) < 0.9 else [0, 1.0, 0])
    u /= np.linalg.norm(u)
    q = np.stack([p @ u, p @ np.cross(normal, u)], axis=1)
    rest = list(range(len(q)))
    scale = float(np.ptp(q, axis=0).max()) ** 2 or 1.0
    if sum(q[i, 0] * q[(i + 1) % len(q), 1] - q[(i + 1) % len(q), 0] * q[i, 1] for i in range(len(q))) < 0:
        rest.reverse()                             # anticlockwise
    triangles = []

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    turns = 0
    while len(rest) > 3 and turns < 4 * len(q) ** 2:
        turns += 1
        for k in range(len(rest)):
            a, b, c = rest[k - 1], rest[k], rest[(k + 1) % len(rest)]
            rotation = cross(q[a], q[b], q[c])
            if rotation < -1e-12 * scale:              # a re-entrant corner: not an ear
                continue
            # A point in a straight line with its neighbours comes out with a flat triangle (without area): the cap stays
            # sewn to all the points of the edge, like the sides. Another point inside the ear, or just on its edge
            # (the inner corner of a cross, on the diagonal), stops it: the cap would come out of the plan.
            tiny = -1e-12 * scale
            if rotation > 1e-12 * scale and any(
                    cross(q[a], q[b], q[x]) >= tiny and cross(q[b], q[c], q[x]) >= tiny
                    and cross(q[c], q[a], q[x]) >= tiny and not any(np.allclose(q[x], q[y]) for y in (a, b, c))
                    for x in rest if x not in (a, b, c)):
                continue
            triangles.append((a, b, c))
            rest.pop(k)
            break
        else:
            break
    if len(rest) == 3:
        triangles.append(tuple(rest))
    return triangles


def _triangulation_serves(p: np.ndarray, triangles) -> bool:
    """Whether some triangles (meant for another plan with the same number of points) cover this one well: all turn
    the same way and add up its area, without overlapping."""
    normal = np.cross(np.roll(p, -1, axis=0) - p, p - p.mean(axis=0)).sum(axis=0)
    area = np.linalg.norm(normal) / 2
    if area < 1e-12:
        return False
    normal = normal / (2 * area)
    t = p[np.asarray(triangles, dtype=int)]                       # (m, 3, 3)
    signs = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]) @ normal / 2
    if signs.min() < -1e-9 * area and signs.max() > 1e-9 * area:
        return False
    return abs(abs(signs.sum()) - area) < 1e-6 * area and np.abs(signs).sum() < area * (1 + 1e-6)


def _loose_bodies(lines: np.ndarray, vectors: np.ndarray, name: str | None) -> Data:
    """Each curve extruded with its own cap, all in a single mesh (without levels)."""
    from .meshes import kind_mesh
    vertices, faces = [], []
    for i, line in enumerate(lines):
        one = _body_extruded(Data(line, (), None, kind=CLOSED_CURVE), vectors[min(i, len(vectors) - 1)], None)
        base = sum(len(v) for v in vertices)
        vertices.append(one.values)
        faces += [tuple(base + j for j in face) for face in one.kind.faces]
    return Data(np.concatenate(vertices), (), name, kind=kind_mesh(faces))


def _body_extruded(curve: Data, vector, name: str | None) -> Data:
    """A closed curve swept and with its two caps: a closed body (a solid wall, a slab)."""
    from .meshes import kind_mesh
    c = curve.values
    lines = c.reshape(-1, c.shape[-2], 3)
    v = np.asarray(_point(vector, "vector").values, dtype=float)
    n = c.shape[-2]
    # A single way to cut the cap into triangles for all (the result is a single kind of mesh):
    # that of the first, if it serves the others (their triangles neither flip nor overlap).
    # First, in strips (each point with its pair on the other side: it serves for out-and-back profiles, like
    # a rib); if not, by ears.
    candidates = []
    if n % 2 == 0 and n >= 4:
        strips = []
        for k in range(n // 2 - 1):
            a, b, c_, d = k, k + 1, n - 2 - k, n - 1 - k
            strips += [(a, b, c_), (a, c_, d)]
        candidates.append(strips)
    chosen = next((t for t in candidates if all(_triangulation_serves(x, t) for x in lines)), None)
    if chosen is None:                              # by ears, only if the strips do not serve (it is slower)
        ears = _triangulate_plan(lines[0])
        chosen = ears if all(_triangulation_serves(x, ears) for x in lines) else None
    if chosen is None and len(lines) == 1:         # a single one and not even so: it encloses nothing (flat, without area)
        raise ShapeError(tr('One of the curves encloses no area (a size set to 0?): it cannot be extruded as a solid.'))
    if chosen is None:                              # very different shapes: each one its own way, in a single body
        return _loose_bodies(lines, v.reshape(-1, 3), name)
    caps = [chosen]
    p0, v0 = lines[0], v.reshape(-1, 3)[0]
    if np.linalg.norm(v0) < 1e-12:
        raise ShapeError(tr('Extruding needs a non-zero vector.'))
    # All outwards: the top cap faces the vector and the bottom one the other way; the sides,
    # outwards according to the direction the plan turns seen from the vector.
    def normal(t):
        a, b, c_ = (p0[i] for i in t)
        return np.cross(b - a, c_ - a)
    rises = sum(float(normal(t) @ v0) for t in caps[0])
    above_t = [t if rises >= 0 else (t[0], t[2], t[1]) for t in caps[0]]
    below = [(a, c_, b) for a, b, c_ in above_t]
    above = [(a + n, b + n, c_ + n) for a, b, c_ in above_t]
    rotation = float(np.cross(p0, np.roll(p0, -1, axis=0)).sum(axis=0) @ v0)     # >0: anticlockwise seen from v
    sides = []
    for i in range(n):
        j = (i + 1) % n
        sides += [(i, j, j + n), (i, j + n, i + n)] if rotation >= 0 else [(i, j + n, j), (i, i + n, j + n)]
    faces = below + above + sides
    return apply(lambda cc, t: np.concatenate([cc, cc + _to(t, cc)], axis=-2), curve, _point(vector, "vector"),
                   name=name, kind=kind_mesh(faces))


#: How it extrudes: along a vector (a sheet, a wall) or up to a point (a pyramid, a cone).
MODES_EXTRUDE = ("vector", 'to a point')


def extrude(curve: Data, vector=(0.0, 0.0, 1.0), name: str | None = None, caps: bool = False,
            mode: str = "vector", point=None) -> Data:
    """Sweeps each curve along `vector`: a surface (a sheet, a wall). With `caps`, a closed curve gives a **closed
    body** (with its cap at the bottom and at the top): a plan that becomes a volume. A rectangle or a polygon is extruded
    by its outline. «to a point» mode: each curve gathers at `point` (a pyramid, a cone, a hip roof); with `caps`, closed
    at the bottom."""
    if curve.kind is not None and curve.kind.faces is not None and len(curve.kind.faces) == 1 \
            and not curve.kind.polygon:                 # a rectangle: its outline
        face = list(curve.kind.faces[0])
        curve = Data(curve.values[..., face, :], curve.levels, curve._name(), curve.variables, curve.starts,
                     CLOSED_CURVE, curve.holes)
    if curve.kind is None or not curve.kind.curve:
        raise ShapeError(tr('“{name}” should be a curve, and it is {what_is}.').format(
                               name=curve._name(), what_is=_what_is(curve)))
    closed = curve.kind.closed
    if mode not in MODES_EXTRUDE:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MODES_EXTRUDE)))
    if mode == 'to a point':
        return _to_a_point(curve, point, caps, name)
    if caps:
        if not closed:
            raise ShapeError(tr('To extrude with caps, “{name}” must be a closed curve.').format(
                                   name=curve._name()))
        return _body_extruded(curve, vector, name)

    def sheet(c, t):
        if closed:
            c = np.concatenate([c, c[..., :1, :]], axis=-2)
        return np.concatenate([c, c + _to(t, c)], axis=-2)

    n = curve.values.shape[-2] + (1 if closed else 0)
    return apply(sheet, curve, _point(vector, "vector"), name=name, kind=kind_surface(2, n))


def _to_a_point(curve: Data, point, caps: bool, name: str | None) -> Data:
    """Each curve joined to a point (its apex): a surface of two rows, the bottom one the curve and the top one the
    point; with `caps`, a closed body (the base, triangulated)."""
    if point is None:
        raise ShapeError(tr('«point» is missing: where it is extruded to (the apex).'))
    closed = curve.kind.closed
    vertex = np.asarray(_point(point, "point").values, dtype=float)
    if not caps:
        def sheet(c, p):
            if closed:
                c = np.concatenate([c, c[..., :1, :]], axis=-2)
            return np.concatenate([c, np.broadcast_to(p[..., None, :], c.shape)], axis=-2)
        n = curve.values.shape[-2] + (1 if closed else 0)
        return apply(sheet, curve, _point(point, "point"), name=name, kind=kind_surface(2, n))
    if not closed:
        raise ShapeError(tr('To extrude with caps, “{name}” must be a closed curve.').format(
                               name=curve._name()))
    from .meshes import kind_mesh
    lines = curve.values.reshape(-1, curve.values.shape[-2], 3)
    vertices_p = np.broadcast_to(vertex.reshape(-1, 3), (len(lines), 3)) if vertex.size == 3 else \
        vertex.reshape(-1, 3)
    if len(vertices_p) != len(lines):
        raise ShapeError(tr('Give one point for all curves or one per curve.'))
    all_, faces = [], []
    for line, apex in zip(lines, vertices_p):
        base = sum(len(v) for v in all_)
        n = len(line)
        v = np.vstack([line, apex[None]])
        sides = [(i, (i + 1) % n, n) for i in range(n)]
        below = [(a, c_, b) for a, b, c_ in _triangulate_plan(line)]
        # All outwards: if the sides face inwards, both are flipped.
        centre = v.mean(axis=0)
        a, b, c_ = (v[i] for i in sides[0])
        if np.dot(np.cross(b - a, c_ - a), a - centre) < 0:
            sides = [(x, z, y) for x, y, z in sides]
            below = [(x, z, y) for x, y, z in below]
        all_.append(v)
        faces += [tuple(base + i for i in t) for t in sides + below]
    return Data(np.concatenate(all_), (), name, kind=kind_mesh(faces))


def _evaluator(geom: Data):
    """A function at(s, t) → points of a rectangle or a surface at the fractions s (across) and t (up), between
    0 and 1: (…, *shape of s, 3)."""
    if geom.kind is not None and geom.kind.grid is not None:
        r = _grid(geom)                                        # (…, F, C, 3)
        F, C = r.shape[-3], r.shape[-2]

        def at(s, t):
            x, y = s * (C - 1), t * (F - 1)
            j0 = np.clip(np.floor(x).astype(int), 0, C - 2)
            i0 = np.clip(np.floor(y).astype(int), 0, F - 2)
            fx, fy = (x - j0)[..., None], (y - i0)[..., None]
            a, b = r[..., i0, j0, :], r[..., i0, j0 + 1, :]
            c, d = r[..., i0 + 1, j0, :], r[..., i0 + 1, j0 + 1, :]
            return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
        return at

    u, v = _sides(geom)
    o = geom.values[..., 0, :]

    def at(s, t):
        extra = (None,) * s.ndim
        return (o[(..., *extra, slice(None))] + s[..., None] * u[(..., *extra, slice(None))]
                + t[..., None] * v[(..., *extra, slice(None))])
    return at


def _is_closed_a_width(geom: Data) -> bool:
    """A surface that goes round (the skin of a tower): its first and last column coincide."""
    if geom.kind is None or geom.kind.grid is None:
        return False
    r = _grid(geom)
    return bool(np.allclose(r[..., :, 0, :], r[..., :, -1, :]))


def _fractions(m: int, n: int, shape: str, closed: bool, cuts_s=None, cuts_t=None) -> tuple[np.ndarray, np.ndarray]:
    """The (s, t) fractions of the 4 corners of each panel: (m, n, 4) each.

    Squares: cells of a grid. Diamonds: alternate rows, each one shifted half a column; the corners go bottom, right,
    top, left (so the panel faces the same way as the surface).
    """
    i, j = np.meshgrid(np.arange(m), np.arange(n), indexing="ij")
    if shape == 'squares':                       # (with cuts: the columns and rows, uneven)
        cs = np.linspace(0, 1, n + 1) if cuts_s is None else np.asarray(cuts_s, float)
        ct = np.linspace(0, 1, m + 1) if cuts_t is None else np.asarray(cuts_t, float)
        s = np.stack([cs[j], cs[j + 1], cs[j + 1], cs[j]], axis=-1)
        t = np.stack([ct[i], ct[i], ct[i + 1], ct[i + 1]], axis=-1)
        return s, t
    if shape == 'hexagons':
        return _hexagon_fractions(m, n, closed)
    if shape == 'triangles':
        return _triangle_fractions(m, n)
    height = 1 / (m + 1)
    centre_s = (j + np.where(i % 2 == 0, 0.5, 0.0)) / n
    centre_t = (i + 1) * height
    mean = 0.5 / n
    s = np.stack([centre_s, centre_s + mean, centre_s, centre_s - mean], axis=-1)
    t = np.stack([centre_t - height, centre_t, centre_t + height, centre_t], axis=-1)
    s = np.mod(s, 1.0) if closed else np.clip(s, 0.0, 1.0)  # on a closed skin, the diamonds go round
    return s, t


def _hexagon_fractions(m: int, n: int, closed: bool) -> tuple[np.ndarray, np.ndarray]:
    """The (s, t) fractions of the 6 corners of each hexagon: (m, n, 6) each.

    A honeycomb of m rows × n columns: the columns overlap a quarter of a hexagon, and the odd ones go half a hexagon
    higher. Only whole hexagons, all inside. The corners go round the same way as a square panel (from the right,
    upwards), so the hexagon faces the same way as the surface. On a skin that goes round, the columns go round too
    (with an even number of them they close without a seam).
    """
    i, j = np.meshgrid(np.arange(m), np.arange(n), indexing="ij")
    width = 1 / (0.75 * n) if closed else 1 / (0.75 * n + 0.25)
    height = 1 / (m + 0.5)
    centre_s = (0.0 if closed else width / 2) + 0.75 * width * j
    centre_t = height / 2 + height * i + np.where(j % 2 == 1, height / 2, 0.0)
    ds = np.array([0.5, 0.25, -0.25, -0.5, -0.25, 0.25]) * width
    dt = np.array([0.0, 0.5, 0.5, 0.0, -0.5, -0.5]) * height
    s = centre_s[..., None] + ds
    t = centre_t[..., None] + dt
    s = np.mod(s, 1.0) if closed else np.clip(s, 0.0, 1.0)
    return s, np.clip(t, 0.0, 1.0)


def _triangle_fractions(m: int, n: int) -> tuple[np.ndarray, np.ndarray]:
    """The (s, t) fractions of the 3 corners of each triangle: (m, 2n + 1, 3) each.

    Rows of triangles pointing up and down in turn, each row shifted half a triangle from the one below; at the
    ends of a row, half triangles, so the rectangle is covered whole. The corners go round like a square panel.
    """
    s_out = np.zeros((m, 2 * n + 1, 3))
    t_out = np.zeros((m, 2 * n + 1, 3))
    for i in range(m):
        low, high = i / m, (i + 1) / m
        # an even row has its points along the bottom at 0, 1/n…, and along the top half a step on; an odd row, the
        # other way round (the same pattern turned upside down)
        b = [j / n for j in range(n + 1)]                                   # the line with whole steps
        h = [min(max((j + 0.5) / n, 0.0), 1.0) for j in range(-1, n + 1)]   # the line half a step on
        tris = []
        for j in range(n + 1):
            tris.append(((b[j], 0), (h[j + 1], 1), (h[j], 1)))              # its point on the whole line
            if j < n:
                tris.append(((b[j], 0), (b[j + 1], 0), (h[j + 1], 1)))      # its side on the whole line
        for k, tri in enumerate(tris):
            if i % 2:                                                       # odd row: turned over, still counterclockwise
                tri = tuple((sv, 1 - tv) for sv, tv in reversed(tri))
            for c, (sv, tv) in enumerate(tri):
                s_out[i, k, c] = sv
                t_out[i, k, c] = low + (high - low) * tv
    return s_out, t_out


def _diamond_trim_fractions(m: int, n: int, closed: bool) -> list[np.ndarray]:
    """The pieces that the diamonds of m rows × n columns leave free in the rectangle, each one its (s, t) corners
    counterclockwise (like a square panel): along the bottom and the top, a triangle between each two diamonds and
    one at each corner; on the right, the half diamond missing in every other row (on the left the Grid already
    gives it). On a skin that goes round, the diamonds close the sides, so only the bottom and the top are left."""
    h, step = 1 / (m + 1), 1 / n
    pieces = []
    mid = [(k + 0.5) * step for k in range(n)]               # the bottom corners of the first row
    pieces.append([(0.0, 0.0), (mid[0], 0.0), (0.0, h)])
    for k in range(n - 1):
        pieces.append([(mid[k], 0.0), (mid[k + 1], 0.0), ((k + 1) * step, h)])
    pieces.append([(mid[-1], 0.0), (1.0, 0.0), (1.0, h)])
    if not closed:
        for i in range(1, m, 2):                              # the rows that start with half a diamond
            centre = (i + 1) * h
            pieces.append([(1.0, centre - h), (1.0, centre + h), (1 - 0.5 * step, centre)])
    if (m - 1) % 2 == 0:                                      # the last row is like the first: its tops halfway
        pieces.append([(0.0, 1 - h), (mid[0], 1.0), (0.0, 1.0)])
        for k in range(n - 1):
            pieces.append([((k + 1) * step, 1 - h), (mid[k + 1], 1.0), (mid[k], 1.0)])
        pieces.append([(1.0, 1 - h), (1.0, 1.0), (mid[-1], 1.0)])
    else:                                                     # its tops at the whole steps
        for k in range(n):
            pieces.append([(mid[k], 1 - h), ((k + 1) * step, 1.0), (k * step, 1.0)])
    return [np.array(q, float) for q in pieces]


def _trims_in(geom: Data, m: int, n: int) -> tuple[np.ndarray, int]:
    """The trims of the diamonds on a rectangle or a surface: (…, pieces, sides, 3), padded with the last corner."""
    pieces = _diamond_trim_fractions(m, n, _is_closed_a_width(geom))
    sides = max(3, max(len(q) for q in pieces))
    st = np.stack([np.vstack([q, np.repeat(q[-1:], sides - len(q), axis=0)]) for q in pieces])   # (k, sides, 2)
    return _evaluator(geom)(st[..., 0], st[..., 1]), sides


def _cells_in_surface(sup: Data, m: int, n: int, shape: str = 'squares', cuts_s=None,
                          cuts_t=None) -> np.ndarray:
    """The 4 corners of each panel of m rows × n columns: (…, m, n, 4, 3)."""
    s, t = _fractions(m, n, shape, _is_closed_a_width(sup), cuts_s, cuts_t)
    return _evaluator(sup)(s, t)


#: Points per side of each curved panel (Grid with curved panels): 4 × 4 faces that follow the surface.
CURVED_POINTS_PANEL = 5


def _curved_panels(sup: Data, cuts_s: np.ndarray, cuts_t: np.ndarray) -> np.ndarray:
    """Each panel, a piece of the surface that follows it (not flat): (…, m, n, k·k, 3), k points per side."""
    k = CURVED_POINTS_PANEL
    a = np.linspace(0, 1, k)
    s0, s1 = cuts_s[:-1], cuts_s[1:]
    t0, t1 = cuts_t[:-1], cuts_t[1:]
    # (m, n, k, k): t along the rows of the panel, s along its columns.
    S = (s0[None, :, None, None] + (s1 - s0)[None, :, None, None] * a[None, None, None, :]) + 0 * t0[:, None, None, None]
    T = (t0[:, None, None, None] + (t1 - t0)[:, None, None, None] * a[None, None, :, None]) + 0 * s0[None, :, None, None]
    p = _evaluator(sup)(S, T)                                      # (…, m, n, k, k, 3)
    return p.reshape(p.shape[:-3] + (k * k, 3))


def _cuts(value, what: str) -> np.ndarray | None:
    """A list of fractions (0; 0,2; 0,5; 1) where a number of rows or columns goes: the cuts, uneven. None if it is a
    single number (the usual even spreading)."""
    if value is None or isinstance(value, (int, float, np.integer, np.floating)):
        return None
    v = _values_items(value, what)
    if len(v) < 2:
        return None
    if np.any(v < 0) or np.any(v > 1):
        raise ShapeError(tr('The cuts of «{what}» are fractions from 0 to 1 (0; 0.2; 0.5; 1).').format(what=tr(what)))
    v = np.unique(np.concatenate([[0.0], v, [1.0]]))
    if len(v) < 2:
        raise ShapeError(tr('At least two different cuts are needed in «{what}».').format(what=tr(what)))
    return v


@lru_cache(maxsize=64)
def _coarse_kind_surface(rows: int, columns: int, closed_u: bool) -> Kind:
    """The faces of a surface with thickness: bottom, top and the edges."""
    N = rows * columns
    idx = lambda i, j, layer=0: layer * N + i * columns + j  # noqa: E731
    faces = []
    for i in range(rows - 1):
        for j in range(columns - 1):
            faces.append((idx(i, j, 1), idx(i, j + 1, 1), idx(i + 1, j + 1, 1), idx(i + 1, j, 1)))  # arriba
            faces.append((idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)))              # abajo
    for j in range(columns - 1):  # edges of the first and the last row
        faces.append((idx(0, j), idx(0, j + 1), idx(0, j + 1, 1), idx(0, j, 1)))
        f = rows - 1
        faces.append((idx(f, j + 1), idx(f, j), idx(f, j, 1), idx(f, j + 1, 1)))
    if not closed_u:  # edges of the first and the last column
        for i in range(rows - 1):
            faces.append((idx(i + 1, 0), idx(i, 0), idx(i, 0, 1), idx(i + 1, 0, 1)))
            c = columns - 1
            faces.append((idx(i, c), idx(i + 1, c), idx(i + 1, c, 1), idx(i, c, 1)))
    return Kind("thick surface", tuple(faces))


def _thicken_surface(sup: Data, thickness, name: str | None) -> Data:
    """Gives thickness to a surface, towards where it faces (positive) or the other way (negative)."""
    F, C = sup.kind.grid
    closed_u = bool(np.allclose(_grid(sup)[..., :, 0, :], _grid(sup)[..., :, -1, :]))

    def solid(v, e):
        r = v.reshape(v.shape[:-2] + (F, C, 3))
        du = np.gradient(r, axis=-2)
        dv = np.gradient(r, axis=-3)
        n = np.cross(du, dv)
        length = np.linalg.norm(n, axis=-1, keepdims=True)
        n = np.divide(n, length, out=np.zeros_like(n), where=length > 1e-12)
        e = np.asarray(e, dtype=float)[..., None, None, None]
        below = (r + n * np.minimum(e, 0)).reshape(v.shape)
        above = (r + n * np.maximum(e, 0)).reshape(v.shape)
        return np.concatenate([below, above], axis=-2)

    return apply(solid, sup, _data(thickness), name=name, kind=_coarse_kind_surface(F, C, closed_u))


# --- Dividir -----------------------------------------------------------------

def grid(rect: Data, columns: int | None = None, rows: int | None = None,
             cell_width: float | None = None, cell_height: float | None = None,
             levels: tuple[str, str] = ("row", "column"), shape: str = 'squares',
             name: str | None = None, panels: str = 'flat') -> Data:
    """Divides a rectangle into cells: it adds two levels, `row` and `column`.

    For each direction, the number of cells or their size is given; or, instead of the number, the **cuts** as fractions
    from 0 to 1 («0; 0,2; 0,5; 1»: uneven cells). Row 0 is the bottom one and column 0 the left one. The levels can be
    named otherwise (`levels=("floor", "module")`). `shape`: squares or diamonds (alternate rows, shifted half a column).
    `panels` (on a curved surface): «flat» (four corners) or «curved» (each panel, a piece that follows the surface).
    """
    if shape not in GRID_SHAPES:
        raise ShapeError(tr("I don't know the shape “{shape}”. Options: squares, diamonds, diamond trims, hexagons, triangles.").format(shape=shape))
    if panels not in ('flat', 'curved'):
        raise ShapeError(tr('Panels can be: flat or curved.'))
    cuts_s, cuts_t = _cuts(columns, "columns"), _cuts(rows, "rows")
    if (cuts_s is not None or cuts_t is not None) and shape != 'squares':
        raise ShapeError(tr('Diamonds, their trims, hexagons and triangles are always even: for uneven cells, use squares.'))
    if shape in ('hexagons', 'triangles', 'diamond trims') and panels == 'curved':
        raise ShapeError(tr('Hexagons, triangles and the trims of the diamonds are flat panels: choose flat panels.'))
    if cuts_s is not None:
        columns = len(cuts_s) - 1
    if cuts_t is not None:
        rows = len(cuts_t) - 1
    if columns is not None and rows is not None:
        _require_size_({**rect.sizes, levels[0]: integer(rows), levels[1]: integer(columns)}, tr('The grid'))
    if rect.kind is not None and rect.kind.grid is not None:  # a curved surface
        if columns is None or rows is None:
            raise ShapeError(tr('To divide the surface “{name}”, give the number of columns and rows (on a '
                                  'curved surface the cell size is not fixed).').format(
                                   name=rect._name()))
        m = _how_many(rect, None, rows, None, "height", "rows")
        n = _how_many(rect, None, columns, None, "width", "columns")
        if panels == 'curved':
            cs = np.linspace(0, 1, n + 1) if cuts_s is None else cuts_s
            ct = np.linspace(0, 1, m + 1) if cuts_t is None else cuts_t
            k = CURVED_POINTS_PANEL
            return rect.derived(_curved_panels(rect, cs, ct), name, kind_surface(k, k), tuple(levels))
        if shape == 'diamond trims':
            cells, sides = _trims_in(rect, m, n)
            return rect.derived(cells, name, _grid_kind(shape, sides), ("trim",))
        return rect.derived(_cells_in_surface(rect, m, n, shape, cuts_s, cuts_t), name, _grid_kind(shape),
                             tuple(levels))
    _require_kind(rect, RECTANGLE, "rectangle")
    u, v = _sides(rect)
    n = _how_many(rect, np.linalg.norm(u, axis=-1), columns, cell_width, "width", "columns")
    m = _how_many(rect, np.linalg.norm(v, axis=-1), rows, cell_height, "height", "rows")
    _require_size_({**rect.sizes, levels[0]: m, levels[1]: n}, tr('The grid'))
    if shape == 'diamonds':
        return rect.derived(_cells_in_surface(rect, m, n, shape), name, RECTANGLE, tuple(levels))
    if shape == 'diamond trims':
        cells, sides = _trims_in(rect, m, n)
        return rect.derived(cells, name, _grid_kind(shape, sides), ("trim",))
    if shape in ('hexagons', 'triangles'):
        fu, fv = _hexagon_fractions(m, n, False) if shape == 'hexagons' else _triangle_fractions(m, n)
        def by_cell(x):  # (…, 3) → (…, 1, 1, 1, 3)
            return x[..., None, None, None, :]
        cells = by_cell(rect.values[..., 0, :]) + fu[..., None] * by_cell(u) + fv[..., None] * by_cell(v)
        return rect.derived(cells, name, _grid_kind(shape), tuple(levels))
    return rect.derived(_cells(rect, m, n, cuts_s, cuts_t), name, RECTANGLE, tuple(levels))


#: The shapes of the cells of a Grid.
GRID_SHAPES = ('squares', 'diamonds', 'diamond trims', 'hexagons', 'triangles')


def _grid_kind(shape: str, sides: int = 4) -> Kind:
    """Squares and diamonds are rectangles (four corners); hexagons and triangles, polygons of six and three; the
    trims of the diamonds, polygons (triangles, and a few with more corners)."""
    if shape == 'diamond trims':
        from .polygons import kind_polygon
        return kind_polygon(sides)
    if shape in ('hexagons', 'triangles'):
        from .polygons import kind_polygon
        return kind_polygon(6 if shape == 'hexagons' else 3)
    return RECTANGLE


def divide(rect: Data, parts: int | None = None, size: float | None = None,
            level: str = "part", direction: str = 'width', name: str | None = None) -> Data:
    """Divides a rectangle into parts in a single direction: it adds a level.

        divide(panels, 3, level="sun fin")   # 3 vertical strips per panel

    `direction`: width (vertical strips, side by side) or height (horizontal strips, one above the other).
    """
    _require_kind(rect, RECTANGLE, "rectangle")
    if direction not in ('width', 'height'):
        raise ShapeError(tr("I don't know the direction “{direction}”. Options: width, height.").format(
                               direction=direction))
    u, v = _sides(rect)
    side = u if direction == 'width' else v
    k = _how_many(rect, np.linalg.norm(side, axis=-1), parts, size, direction, "parts")
    if direction == 'width':
        cells = _cells(rect, 1, k)[..., 0, :, :, :]
    else:
        cells = _cells(rect, k, 1)[..., :, 0, :, :]
    return rect.derived(cells, name, RECTANGLE, (level,))


def _sides(rect: Data) -> tuple[np.ndarray, np.ndarray]:
    """The sides of each rectangle: u (across) and v (up)."""
    corners = rect.values
    return corners[..., 1, :] - corners[..., 0, :], corners[..., 3, :] - corners[..., 0, :]


def _cells(rect: Data, m: int, n: int, cuts_s=None, cuts_t=None) -> np.ndarray:
    """The 4 corners of each cell of m rows × n columns: (…, m, n, 4, 3). With cuts, uneven."""
    u, v = _sides(rect)
    fu, fv = _fractions(m, n, 'squares', False, cuts_s, cuts_t)     # (m, n, 4)
    def by_cell(x):  # (…, 3) → (…, 1, 1, 1, 3)
        return x[..., None, None, None, :]
    return by_cell(rect.values[..., 0, :]) + fu[..., None] * by_cell(u) + fv[..., None] * by_cell(v)


def _average(g: np.ndarray, polygon: bool, keepdims: bool = False) -> np.ndarray:
    """The average of the vertices of each element; in a polygon, without the repeated ones of the padding."""
    if not polygon:
        return g.mean(axis=-2, keepdims=keepdims)
    tally = np.ones(g.shape[:-1], dtype=bool)
    tally[..., 1:] = np.linalg.norm(np.diff(g, axis=-2), axis=-1) > TOLERANCE_VERTEX
    weight = tally[..., None].astype(float)
    return (g * weight).sum(axis=-2, keepdims=keepdims) / np.maximum(weight.sum(axis=-2, keepdims=keepdims), 1)


def centre(geometry: Data, name: str | None = None) -> Data:
    """The centre of each element (the average of its vertices)."""
    if geometry.kind == POINT:
        return geometry
    if geometry.kind is None or (geometry.kind.faces is None and not geometry.kind.curve):
        _require_mesh(geometry)
    return geometry.derived(_average(geometry.values, geometry.kind.polygon), name, POINT)


# --- Measure and transform numbers ---------------------------------------------

def distance(a, b, name: str | None = None) -> Data:
    """Distance in metres between points, or from each point to the nearest curve.

    `b` can be a curve (an attractor curve): the distance is to the closest point of the curve.
    """
    if isinstance(b, Data) and b.kind is not None and b.kind.curve:
        return apply(lambda p, c: _distance_a_curve(p, c, b.kind.closed), _point(a, "a"), b, name=name)
    if isinstance(a, Data) and a.kind is not None and a.kind.curve:
        return distance(b, a, name)
    a, b = _point(a, "a"), _point(b, "b")
    return apply(lambda p, q: np.linalg.norm(p - q, axis=-1), a, b, name=name)


def _distance_a_curve(p: np.ndarray, c: np.ndarray, closed: bool) -> np.ndarray:
    """Distance from each point p (…, 3) to the polyline c (…, n, 3)."""
    if closed:
        c = np.concatenate([c, c[..., :1, :]], axis=-2)
    a, b = c[..., :-1, :], c[..., 1:, :]
    ab = b - a
    ap = p[..., None, :] - a
    largo2 = np.maximum((ab * ab).sum(-1), 1e-18)
    t = np.clip((ap * ab).sum(-1) / largo2, 0, 1)
    near = a + t[..., None] * ab
    return np.linalg.norm(p[..., None, :] - near, axis=-1).min(axis=-1)


def _more_nearest_in_curve(p: np.ndarray, c: np.ndarray, closed: bool) -> tuple[np.ndarray, np.ndarray]:
    """The point of the polyline c (…, n, 3) closest to each p (…, 3), and at what fraction of its length it is."""
    if closed:
        c = np.concatenate([c, c[..., :1, :]], axis=-2)
    a, b = c[..., :-1, :], c[..., 1:, :]
    ab = b - a
    ap = p[..., None, :] - a
    largo2 = np.maximum((ab * ab).sum(-1), 1e-18)
    t = np.clip((ap * ab).sum(-1) / largo2, 0, 1)
    near = a + t[..., None] * ab
    run = np.linalg.norm(p[..., None, :] - near, axis=-1).argmin(axis=-1)
    chosen = np.take_along_axis(near, run[..., None, None], axis=-2)[..., 0, :]
    lengths = np.linalg.norm(ab, axis=-1)
    to = np.concatenate([np.zeros(lengths.shape[:-1] + (1,)), np.cumsum(lengths, axis=-1)], axis=-1)
    route = (np.take_along_axis(to, run[..., None], axis=-1)[..., 0]
                 + np.take_along_axis(t, run[..., None], axis=-1)[..., 0]
                 * np.take_along_axis(lengths, run[..., None], axis=-1)[..., 0])
    total = np.maximum(to[..., -1], 1e-18)
    return chosen, route / total


#: What Closest point gives: the point on the curve, or at what fraction of its length it is (0 at the start, 1 at the end).
GIVES_MORE_NEAREST = ('point', 'fraction', 'distance')


def point_more_nearest(points, curve: Data, gives: str = 'point', name: str | None = None) -> Data:
    """The point of the curve closest to each point (*Curve Closest Point*): to join them with lines, to orient
    something towards the curve, or to know where it falls (the fraction of its length) and at what distance."""
    if gives not in GIVES_MORE_NEAREST:
        raise ShapeError(tr('“gives” must be one of: {options}.').format(options=", ".join(tr(d) for d in GIVES_MORE_NEAREST)))
    if not isinstance(curve, Data) or curve.kind is None or not curve.kind.curve:
        raise ShapeError(tr('“curve” should be a curve (a line, an arc, a drawn curve…).'))
    closed = curve.kind.closed
    p = _centres(points, "points")
    if gives == 'distance':
        return distance(p, curve, name)
    if gives == 'point':
        return apply(lambda q, c: _more_nearest_in_curve(q, c, closed)[0], p, curve, name=name, kind=POINT)
    return apply(lambda q, c: _more_nearest_in_curve(q, c, closed)[1], p, curve, name=name)


def _centres(x, role: str) -> Data:
    """Points; or, if it is a geometry, the centre of each element (a panel, a circle, a column)."""
    if isinstance(x, Data) and x.kind is not None and x.kind is not POINT and x.kind is not VECTOR:
        is_mesh = len(x.shape_element) == 2
        values = _average(x.values, x.kind.polygon) if is_mesh else x.values
        return Data(values, x.levels, x.name, x.variables, x.starts, POINT, x.holes)
    return _point(x, role)


#: With several attractors: the nearest rules, or their effects add up (two attractors together, more effect).
SEVERAL_ATTRACTORS = ('the closest', 'add up')


def attractor(where, attractors, more=None, reach=None, near=1.0, far=0.0, several: str = 'the closest',
             curve: str = 'linear', name: str | None = None) -> Data:
    """A value per element by how close it is to some attractors (points or curves): `near` next to the attractor
    and `far` at the distance `reach` or more (empty: the farthest of all). With several attractors, the nearest rules
    or their effects add up. `curve`: how it goes from near to far.

    It replaces the chain Distance → Bounds → Domain → Remap → Minimum (and A + B with two attractors).

        attractor(centres, point, reach=25, near=0.01, far=0.8)   → small circles next to the point
    """
    if several not in SEVERAL_ATTRACTORS:
        raise ShapeError(tr('“several” must be one of: {options}.').format(
                               options=", ".join(tr(v) for v in SEVERAL_ATTRACTORS)))
    if curve not in CURVES_ANSWER:
        raise ShapeError(tr("I don't know the curve “{curve}”. Options: {options}.").format(
                               curve=curve, options=', '.join(tr(o) for o in CURVES_ANSWER)))
    if where is None:
        raise ShapeError(tr('“Where” is missing: the points (or the geometry: each element by its centre) that '
                              'feel the attractor.'))
    fonts = [a for a in (attractors, more) if a is not None]
    if not fonts:
        raise ShapeError(tr('The attractor is missing: one or more points, or a curve.'))
    p = _centres(where, "where")
    distances = []
    for a in fonts:
        is_curve = isinstance(a, Data) and a.kind is not None and a.kind.curve
        a = a if is_curve else _point(a, "attractor")
        d = distance(p, a)
        own = [n for n in d.levels if n not in p.levels]         # the levels of the attractors
        distances.append((d, own))
    if reach is None:
        valid = [d.values[d.mask] if d.levels else d.values.ravel() for d, _ in distances]
        radius = _data(max(float(v.max()) for v in valid if v.size) or 1.0)
    else:
        radius = _data(reach)
        if np.any(np.asarray(radius.values, dtype=float) <= 0):
            raise ShapeError(tr("The “reach” must be greater than 0: how far the attractor's effect goes."))
    curve_shape = CURVES_ANSWER[curve]
    effects = []
    for d, own in distances:                # the effect of each attractor: 1 next to it, 0 at the reach or more
        effect = apply(lambda x, r: 1.0 - np.clip(x / r, 0.0, 1.0), d, radius)
        if own:
            effect = reduce(effect, 'maximum' if several == 'the closest' else 'sum', own)
        effects.append(effect)
    total = effects[0]
    for other in effects[1:]:
        total = apply(np.maximum if several == 'the closest' else np.add, total, other)

    def value(e, c, l):
        return l + curve_shape(np.clip(e, 0.0, 1.0)) * (c - l)
    return apply(value, total, _data(near), _data(far), name=name)

CURVES_ANSWER = {
    'linear': lambda t: t,
    'smooth': lambda t: (lambda c: c * c * (3 - 2 * c))(np.clip(t, 0, 1)),   # S-shaped: it starts and ends slowly
    'ease in': lambda t: np.clip(t, 0, 1) ** 2,                              # slow at the start
    'ease out': lambda t: 1 - (1 - np.clip(t, 0, 1)) ** 2,                      # fast at the start
}


def remap(value, from_, towards, curve: str = 'linear', name: str | None = None, limit: bool = False) -> Data:
    """Takes `value` from the range `from_` to the range `to`.

        remap(distances, from_=(0, maximum), to=(90, 0))   # near 90°, far 0°
        remap(distances, from_=(None, None), to=(90, 0))  # from: the smallest and largest of the data

    An end of `from_` in None is taken from the data themselves (without counting the empty ones): no Maximum or Minimum
    node is needed.

    `curve`: how it goes from one end to the other (the "response curve" or *Graph Mapper*): linear, smooth
    (S-shaped), ease in or ease out. Except the linear one, it does not leave the range `to`; with `clamp`, the linear
    does not either (what goes past `from_` stays at the end: the «Minimum» that is put afterwards in Grasshopper).
    """
    if curve not in CURVES_ANSWER:
        raise ShapeError(tr("I don't know the curve “{curve}”. Options: {options}.").format(
                               curve=curve, options=', '.join(tr(o) for o in CURVES_ANSWER)))
    curve_shape = CURVES_ANSWER[curve]
    value = _data(value)
    (d0, d1), (h0, h1) = from_, towards
    valid = value.values[value.mask] if value.levels else value.values.ravel()
    if d0 is None:
        d0 = float(valid.min()) if valid.size else 0.0
    if d1 is None:
        d1 = float(valid.max()) if valid.size else 1.0

    def remap(x, a, b, c, d):
        width = b - a
        fraction = np.divide(x - a, width, out=np.zeros(np.broadcast(x, width).shape), where=width != 0)
        if limit:
            fraction = np.clip(fraction, 0.0, 1.0)
        return c + curve_shape(fraction) * (d - c)

    return apply(remap, value, _data(d0), _data(d1), _data(h0), _data(h1), name=name)


#: The starting shapes of a Graph (points from 0 to 1 in x and y); then they are moved by hand.
CHARTS = {
    "linear": [[0, 0], [1, 1]],
    "bell": [[0, 0], [0.5, 1], [1, 0]],
    "smooth rise": [[0, 0], [0.3, 0.08], [0.7, 0.92], [1, 1]],
    "wave": [[0, 0.5], [0.25, 1], [0.5, 0.5], [0.75, 0], [1, 0.5]],
    "stair step": [[0, 0], [0.45, 0], [0.55, 1], [1, 1]],
    "reversed": [[0, 1], [1, 0]],
}


def chart_points(points) -> np.ndarray:
    """The points of a Graph, sorted by x and inside the square from 0 to 1: (n, 2)."""
    p = np.array([[float(c) for c in q[:2]] for q in (points or [])], dtype=float).reshape(-1, 2)
    if len(p) < 2:
        raise ShapeError(tr('The graph needs at least 2 points.'))
    p = np.clip(p, 0.0, 1.0)
    return p[np.argsort(p[:, 0], kind="stable")]


def evaluate_chart(points, x, smooth: bool = True) -> np.ndarray:
    """The height of the graph at x (from 0 to 1). Smooth: a curve through the points without overshooting them
    (monotone by spans, like a tone curve); if not, straight spans."""
    p = chart_points(points)
    x = np.clip(np.asarray(x, dtype=float), p[0, 0], p[-1, 0])
    xs, ys = p[:, 0], p[:, 1]
    if not smooth or len(p) == 2:
        return np.interp(x, xs, ys)
    h = np.diff(xs)
    h = np.where(h <= 1e-12, 1e-12, h)
    d = np.diff(ys) / h
    m = np.zeros(len(p))                                    # slopes that do not bounce (Fritsch–Carlson)
    m[0], m[-1] = d[0], d[-1]
    for k in range(1, len(p) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    k = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, len(p) - 2)
    t = (x - xs[k]) / h[k]
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * ys[k] + (t3 - 2 * t2 + t) * h[k] * m[k]
            + (-2 * t3 + 3 * t2) * ys[k + 1] + (t3 - t2) * h[k] * m[k + 1])


def chart(value, points=None, to_min=0.0, to_max=1.0, from_min=None, from_max=None, smooth: bool = True,
            name: str | None = None) -> Data:
    """Passes each value through a curve drawn by hand (*Graph Mapper*): it is taken to 0–1 (with the smallest and
    largest of the data, or with from_min/from_max), the height of the graph is read there and it is taken to
    to_min–to_max. Near an attractor, a lot; a little farther, suddenly little…: you draw the shape."""
    points = CHARTS["linear"] if points is None else points
    chart_points(points)                                # it warns if it is wrong
    for role, v in (("valor", value), ("hacia_min", to_min), ("hacia_max", to_max)):
        require_numbers(v, role)
    value = _data(value)
    valid = value.values[value.mask] if value.levels else value.values.ravel()
    d0 = float(valid.min()) if from_min is None and valid.size else (0.0 if from_min is None else from_min)
    d1 = float(valid.max()) if from_max is None and valid.size else (1.0 if from_max is None else from_max)

    def map_(x, a, b, c, d):
        width = b - a
        fraction = np.divide(x - a, width, out=np.zeros(np.broadcast(x, width).shape), where=width != 0)
        return c + evaluate_chart(points, fraction, smooth) * (d - c)

    return apply(map_, value, _data(d0), _data(d1), _data(to_min), _data(to_max), name=name)


# --- Move and rotate -----------------------------------------------------------

#: How much it moves is said: with a vector (and maybe a distance), or from one point to another (the base
#: point and the second point).
MODES_MOVE = ("vector", 'point to point')


def move(geometry: Data, vector=(0.0, 0.0, 1.0), distance=None, name: str | None = None,
          mode: str = "vector", from_=None, to=None) -> Data:
    """Moves each element.

    - «vector» mode: along `vector` (a point or three numbers). With `distance`, the vector only gives the direction and
      that distance is travelled: `move(blocks, vector=normal(panels), distance=-2)` sinks them 2 m.
    - «point to point» mode: what is at `from_` reaches `to` (taking a block by its centroid to a point of the terrain).
    """
    _require_geometry(geometry)
    if mode not in MODES_MOVE:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MODES_MOVE)))
    if mode == 'point to point':
        if from_ is None or to is None:
            raise ShapeError(tr('To move from one point to another both are needed: “from” and “to”.'))
        vector = apply(lambda a, b: b - a, _point(from_, "from"), _point(to, "to"), kind=POINT)
        distance = None
    vector = _point(vector, "vector")
    if distance is None:
        return apply(lambda g, t: g + _to(t, g), geometry, vector, name=name, kind=geometry.kind)

    def translate(g, t, d):
        length = np.linalg.norm(t, axis=-1, keepdims=True)
        direction = np.divide(t, length, out=np.zeros(np.broadcast(t, length).shape), where=length != 0)
        return g + _to(direction * np.asarray(d)[..., None], g)

    return apply(translate, geometry, vector, _data(distance), name=name, kind=geometry.kind)


def rotate(geometry: Data, degrees, axis: str = "vertical", centre=(0.0, 0.0, 0.0), direction=None,
          name: str | None = None) -> Data:
    """Rotates each element by `degrees` about an axis that passes through `centre`: vertical, x, y, or any
    `direction` (a vector, or one per element: the axis of a hinge, the slope of a roof).

    Positive is anticlockwise seen from the tip of the axis (from above, if it is vertical).
    """
    _require_geometry(geometry)
    if axis == "direction":
        if direction is None:
            raise ShapeError(tr('“direction” is missing: the vector of the axis to rotate about.'))
        return apply(_rotate_about, geometry, _data(degrees), _point(centre, "centre"), _point(direction, "direction"),
                     name=name, kind=geometry.kind)
    if axis not in AXES:
        raise ShapeError(tr("I don't know the axis “{axis}”. Options: {options}.").format(axis=axis, options=', '.join(tr(o) for o in AXES)))
    k = AXES[axis]
    a, b = [i for i in range(3) if i != k]  # the plane that turns

    def rotate(g, degrees, c):
        rad = np.deg2rad(degrees)
        cosine = _to(np.cos(rad)[..., None], g)[..., 0]
        sine = _to(np.sin(rad)[..., None], g)[..., 0]
        p = g - _to(c, g)
        r = p.copy()
        r[..., a] = p[..., a] * cosine - p[..., b] * sine
        r[..., b] = p[..., a] * sine + p[..., b] * cosine
        return r + _to(c, g)

    return apply(rotate, geometry, _data(degrees), _point(centre, "centre"),
                   name=name, kind=geometry.kind)


def _unit(v: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.divide(v, length, out=np.zeros_like(v, dtype=float), where=length > 1e-12)


def _rotate_about(g, degrees, c, u):
    """Rodrigues: each vertex of `g` turned by `degrees` about the line through `c` with direction `u`."""
    u = _to(_unit(np.asarray(u, dtype=float)), g)
    rad = np.deg2rad(np.asarray(degrees, dtype=float))
    cosine = _to(np.cos(rad)[..., None], g)
    sine = _to(np.sin(rad)[..., None], g)
    p = g - _to(c, g)
    r = p * cosine + np.cross(u, p) * sine + u * np.sum(u * p, axis=-1, keepdims=True) * (1 - cosine)
    return r + _to(c, g)


def _frame(direction: np.ndarray, normal: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Three perpendicular unit axes from a direction (x) and a normal (z). The direction is laid on the plane of
    the normal; if it is missing (NaN) or runs along the normal, the world x laid on it (or the world y)."""
    z = _unit(normal)
    z = np.where(np.linalg.norm(z, axis=-1, keepdims=True) > 0, z, np.array([0.0, 0.0, 1.0]))
    d = np.where(np.isnan(direction), np.array([1.0, 0.0, 0.0]), direction)
    x = d - np.sum(d * z, axis=-1, keepdims=True) * z
    weak = np.linalg.norm(x, axis=-1, keepdims=True) < 1e-9
    other = np.array([0.0, 1.0, 0.0]) - z[..., 1:2] * z
    x = _unit(np.where(weak, other, x))
    return x, np.cross(z, x), z


def orient(geometry: Data, from_=(0.0, 0.0, 0.0), from_direction=(1.0, 0.0, 0.0), from_normal=(0.0, 0.0, 1.0),
           to=(0.0, 0.0, 0.0), to_direction=None, to_normal=(0.0, 0.0, 1.0), name: str | None = None) -> Data:
    """Takes the geometry from one place to another (*Orient*): what is at `from_`, with its x along
    `from_direction` and its up along `from_normal`, goes to `to`, with `to_direction` and `to_normal`. With several
    targets, one copy at each: a module on each point of a surface following its normals (Surface points), a piece
    along a curve following its tangents (Tangent). Without `to_direction`, the x of the world laid on the target.

    Shape and size do not change (a Euclidean transformation): only position and orientation."""
    _require_geometry(geometry)
    if to_direction is None:
        to_direction = Data.value(np.full(3, np.nan))

    def take(g, a, da, na, b, db, nb):
        xa, ya, za = _frame(np.asarray(da, dtype=float), np.asarray(na, dtype=float))
        xb, yb, zb = _frame(np.asarray(db, dtype=float), np.asarray(nb, dtype=float))
        p = g - _to(a, g)
        local = [np.sum(p * _to(axis, g), axis=-1, keepdims=True) for axis in (xa, ya, za)]
        return _to(b, g) + local[0] * _to(xb, g) + local[1] * _to(yb, g) + local[2] * _to(zb, g)

    return apply(take, geometry, _point(from_, "from"), _point(from_direction, "from direction"),
                 _point(from_normal, "from normal"), _point(to, "to"),
                 _data(to_direction) if isinstance(to_direction, Data) and to_direction.kind is None
                 else _point(to_direction, "to direction"), _point(to_normal, "to normal"), name=name,
                 kind=geometry.kind)


def _lift(corners: np.ndarray, height) -> np.ndarray:
    """Four corners (…, 4, 3) as a cell of eight: the same four, and on top of them `height` along the normal of the
    panel (from the first edge to the last, as Thicken does)."""
    n = np.cross(corners[..., 1, :] - corners[..., 0, :], corners[..., 3, :] - corners[..., 0, :])
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, length, out=np.zeros_like(n), where=length > 1e-12)
    top = corners + (n * np.asarray(height, dtype=float)[..., None])[..., None, :]
    return np.concatenate([corners, top], axis=-2)


def cells(into, height=1.0) -> Data:
    """The cells a Morph fills: boxes or blocks as they are; panels (four corners) raised `height` along their normal;
    eight points (a level of eight) as the corners of a box."""
    eight_corners = isinstance(into, Data) and into.kind is POINT and bool(into.levels) and \
        into.values.shape[len(into.levels) - 1] == 8 and bool(np.all(into.mask))
    if not eight_corners and (not isinstance(into, Data) or into.kind is None or into.kind in (POINT, VECTOR)):
        raise ShapeError(tr('“into” must be boxes, blocks, panels or eight corners: the cells the geometry is '
                            'fitted into.'))
    count = into.values.shape[-2] if into.values.ndim >= 2 else 0
    if into.kind in (BOX, BLOCK) and count == 8:
        return into
    if eight_corners:
        # Eight corners (*Twisted Box*): the corners of a box moved one by one, as the cell; the last level of eight,
        # in the order of a box (the four below, then the four above).
        return Data(into.values, into.levels[:-1], into.name,
                    {k: c for k, c in into.variables.items() if k != into.levels[-1]},
                    {k: i for k, i in into.starts.items() if k != into.levels[-1]}, BOX)
    if count == 4 and into.kind.grid is None:
        return apply(_lift, into, _data(height), kind=BLOCK)
    raise ShapeError(tr('“into” must be boxes, blocks or panels (four corners), not “{kind}”. A curved surface is '
                        'panelled with Surface morph.').format(kind=tr(into.kind.name)))


#: The corners of a cell, as (x, y, z) from 0 to 1, in the order of a box: the four below, then the four above.
_CORNERS = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], float)


def morph(geometry: Data, into, height=1.0, reference=None, name: str | None = None) -> Data:
    """Fits the geometry into each cell (*Box Morph*): what fills its bounding box comes to fill the cell, bending
    with it. A cell is a box or block of eight corners, or a panel raised `height` along its normal.

    `reference` is the box that stands for the module (its bounding box is used); without it, that of the geometry.
    A flat module (no height) lies on the bottom face of each cell."""
    _require_geometry(geometry)
    outline = geometry if reference is None else reference
    if not isinstance(outline, Data) or outline.kind is None:
        raise ShapeError(tr('“reference” must be a geometry: its bounding box stands for the module.'))
    every = np.asarray(outline.values, dtype=float).reshape(-1, 3)
    low, high = np.nanmin(every, axis=0), np.nanmax(every, axis=0)
    size = np.where(high - low > 1e-12, high - low, 1.0)
    target = cells(into, height)

    def fit(g, c):
        t = (g - low) / size                                          # where each vertex is in the box: 0 to 1
        w = np.prod(np.where(_CORNERS == 1, t[..., None, :], 1 - t[..., None, :]), axis=-1)   # (…, 8)
        c = c.reshape(c.shape[:-2] + (1,) * (g.ndim - c.ndim + 1) + c.shape[-2:])
        return np.sum(w[..., None] * c, axis=-2)

    return apply(fit, geometry, target, name=name, kind=geometry.kind)


def scale(geometry: Data, factor, centre=None, name: str | None = None) -> Data:
    """Enlarges (factor > 1) or shrinks (factor < 1) each element.

    Without `centre`, each element grows or shrinks about its own centre (a slab stays in its place); with `centre`,
    all with respect to that point.
    """
    _require_geometry(geometry)
    if centre is None:
        is_mesh = len(geometry.shape_element) == 2  # vertices × 3 (a point alone has 3)
        polygon = geometry.kind.polygon

        def scaled(g, f):
            c = _average(g, polygon, keepdims=True) if is_mesh else g
            return c + (g - c) * _to(np.asarray(f)[..., None], g)
        return apply(scaled, geometry, _data(factor), name=name, kind=geometry.kind)

    def scaled_in(g, f, c):
        c = _to(c, g)
        return c + (g - c) * _to(np.asarray(f)[..., None], g)
    return apply(scaled_in, geometry, _data(factor), _point(centre, "centre"), name=name, kind=geometry.kind)


def twist(geometry: Data, degrees, centre=(0.0, 0.0, 0.0), from_=0.0, name: str | None = None) -> Data:
    """Twists the geometry about a vertical axis (through `centre`), as *Twist*: at the bottom it does not turn and at
    the top it turns `degrees`; in between, in proportion to the height. A tower that twists.

    `from_`: at what height it starts twisting (from 0, the bottom, to 1, the top). `degrees` can have levels (several
    ribbons with different twist, as *Tween*).
    """
    _require_geometry(geometry)
    c = _point(centre, "centre").values.reshape(-1, 3)[0]
    v = geometry.values
    existing = (v[geometry.mask] if geometry.levels else v[None]).reshape(-1, 3)
    z0, z1 = existing[:, 2].min(), existing[:, 2].max()
    start = z0 + (z1 - z0) * float(np.clip(from_, 0.0, 1.0))
    height = (z1 - start) or 1.0

    def rotate_by_elevation(g, a):
        fraction = np.clip((g[..., 2] - start) / height, 0.0, 1.0)
        angle = np.radians(np.asarray(a, dtype=float))[(...,) + (None,) * (g.ndim - 1 - np.ndim(a))] * fraction
        cosine, sine = np.cos(angle), np.sin(angle)
        x, y = g[..., 0] - c[0], g[..., 1] - c[1]
        return np.stack([c[0] + x * cosine - y * sine, c[1] + x * sine + y * cosine, g[..., 2]], axis=-1)

    return apply(rotate_by_elevation, geometry, _data(degrees), name=name, kind=geometry.kind)


def scale_by_axes(geometry: Data, x=1.0, y=1.0, z=1.0, centre=None, name: str | None = None) -> Data:
    """Scales differently in x, in y and in z (*Scale NU*): each element about its centre, or all about `centre`.
    A floor that stretches across, a slab that gets shorter."""
    _require_geometry(geometry)
    is_mesh = len(geometry.shape_element) == 2
    polygon = geometry.kind.polygon

    def stretch(g, fx, fy, fz, *c):
        factors = np.stack(np.broadcast_arrays(np.asarray(fx, float), np.asarray(fy, float),
                                                np.asarray(fz, float)), axis=-1)
        if c:
            centre_ = _to(c[0], g)
        else:
            centre_ = _average(g, polygon, keepdims=True) if is_mesh else g
        return centre_ + (g - centre_) * _to(factors, g)

    others = [_point(centre, "centre")] if centre is not None else []
    return apply(stretch, geometry, _data(x), _data(y), _data(z), *others, name=name, kind=geometry.kind)


def coordinate(points: Data, axis: str = "z", name: str | None = None) -> Data:
    """The x, the y or the z of each point (*Deconstruct Point*): to compare it or use it in a Formula."""
    _require_kind(points, POINT, "point")
    if axis not in ("x", "y", "z"):
        raise ShapeError(tr("I don't know the axis “{axis}”. Options: {options}.").format(axis=axis, options="x, y, z"))
    k = "xyz".index(axis)
    return Data(points.values[..., k], points.levels, name, points.variables, points.starts, holes=points.holes)


def project(geometry: Data, amplitude=0.0, name: str | None = None) -> Data:
    """Takes each vertex to a height (*Project* to a horizontal plane): the footprint of a shape on the ground."""
    _require_geometry(geometry)

    def to_elevation(g, h):
        output = np.array(g, dtype=float)
        output[..., 2] = np.asarray(h, dtype=float)[(...,) + (None,) * (g.ndim - 1 - np.ndim(h))]
        return output

    return apply(to_elevation, geometry, _data(amplitude), name=name, kind=geometry.kind)


def join(a: Data, b: Data, level: str = "part", name: str | None = None, *more: Data | None) -> Data:
    """Two (up to four) data in one, with a new level (*Merge*, *Entwine*): a curve and its projection to join them
    with a surface; the start, the middle and the end of each line for a curve through the three."""
    from .data import align
    all_ = [x for x in (a, b, *more) if x is not None]
    all_ = [x if isinstance(x, Data) else _point(x, "point") for x in all_]
    # Curves with a different number of points (drawn with more or fewer clicks): all are spread to the same number,
    # by their length, to be able to join them (and make a surface through them).
    if all(x.kind is not None and x.kind.curve for x in all_) and len({x.shape_element for x in all_}) > 1:
        length = max(x.values.shape[-2] for x in all_)
        all_ = [_curve_with_points(x, length) for x in all_]
    a = all_[0]
    for b in all_[1:]:
        if (a.kind is None) != (b.kind is None) or (a.kind is not None and a.kind.name != b.kind.name):
            raise ShapeError(tr('To merge, both must be the same kind: “{a}” is {what_a} and “{b}”, {what_b}.').format(
                                   a=a._name(), what_a=_what_is(a), b=b._name(), what_b=_what_is(b)))
        if a.shape_element != b.shape_element:
            raise ShapeError(tr('“{a}” and “{b}” do not have the same number of points: they cannot be merged.').format(
                                   a=a._name(), b=b._name()))
        if level in b.levels:
            break
    if any(level in x.levels for x in all_):
        raise ShapeError(tr('“{level}” is already a level: choose another name for the new level.').format(level=tr(level)))
    al = align(*all_)
    together = np.stack(np.broadcast_arrays(*al.values), axis=len(al.levels))
    return Data(together, (*al.levels, level), name, al.variables, al.starts, kind=a.kind)


def _curve_with_points(curve: Data, count: int) -> Data:
    """The same curve with `count` points spread along its length (if it already has them, as it is)."""
    if curve.values.shape[-2] == count:
        return curve
    c = curve.values
    if curve.kind.closed:
        c = np.concatenate([c, c[..., :1, :]], axis=-2)
    runs = np.linalg.norm(np.diff(c, axis=-2), axis=-1)
    accumulated = np.concatenate([np.zeros(runs.shape[:-1] + (1,)), np.cumsum(runs, axis=-1)], axis=-1)
    fractions = np.linspace(0, 1, count, endpoint=not curve.kind.closed)
    points = _in_lengths(c, accumulated, accumulated[..., -1:] * fractions)
    return Data(points, curve.levels, curve._name(), curve.variables, curve.starts, curve.kind, curve.holes)


def place(geometry: Data, at, rotation=0.0, axis: str = "vertical", name: str | None = None) -> Data:
    """Rotates the geometry about its origin and takes it to each point of `at`.

    Step 7 of case 01: a sun fin on each panel, with its angle.
    """
    return move(rotate(geometry, rotation, axis), at, name=name)


# --- Auxiliares --------------------------------------------------------------

def _data(x) -> Data:
    return x if isinstance(x, Data) else Data.value(np.asarray(x, dtype=float))


def _point(x, role: str) -> Data:
    """A point: a data of points (or of vectors), or three numbers."""
    if isinstance(x, Data):
        if x.kind is VECTOR:                     # a vector serves where a point goes (its x, y, z)
            return Data(x.values, x.levels, x._name(), x.variables, x.starts, POINT, x.holes)
        _require_kind(x, POINT, "point", role)
        return x
    if isinstance(x, str):                       # «8; 0; 2,5» (with decimal comma) · «0,0,0» · «8 0 0»
        from .values import read_numbers
        x = read_numbers(x) or x
    try:
        p = np.asarray(x, dtype=float)
    except (TypeError, ValueError):
        p = None
    if p is None or p.shape != (3,):
        raise ShapeError(tr('“{role}” should be a point: type its three coordinates, for example 0, 0, 0 · 8; 0; '
                              '2.5 · (0; 0; 0).').format(role=tr(role)))
    return Data.value(p, role)


def _to(t: np.ndarray, g: np.ndarray) -> np.ndarray:
    """Inserts axes in `t` (…, 3) so it combines with each vertex of `g` (…, [n,] 3)."""
    missing = g.ndim - t.ndim
    return t.reshape(t.shape[:-1] + (1,) * missing + t.shape[-1:])


def _how_many(rect: Data, size: np.ndarray, count, cell, what: str, which: str) -> int:
    if (count is None) == (cell is None):
        raise ShapeError(tr('To divide, give the number of {which} or the size of each cell (one of the two).').format(which=tr(which)))
    if count is not None:
        count = integer(count)
        if count < 1:
            raise ShapeError(tr('The number of {which} must be 1 or more (it is {count}).').format(
                                   which=tr(which), count=count))
        return count
    measures = np.unique(np.round(size[rect.mask], 9))
    if len(measures) > 1:
        raise ShapeError(
            tr('The rectangles of “{name}” have different {what}s; they cannot be divided by cell size yet (use '
               'the number of {which}).').format(name=rect._name(), what=tr(what), which=tr(which))
        )
    total = float(measures[0])
    if float(cell) <= 0:
        raise ShapeError(tr('The cell size must be greater than 0 (it is {cell}).').format(cell=_m(float(cell))))
    n = round(total / cell)
    if n < 1 or abs(n * cell - total) > 1e-6:
        extra = total - np.floor(total / cell + 1e-9) * cell
        raise ShapeError(
            tr('The {what} of “{name}” ({total}) does not divide into {cell} cells: {extra} left over.').format(
                what=tr(what), name=rect._name(), total=_m(total), cell=_m(cell), extra=_m(extra))
        )
    return n


def _m(x: float) -> str:
    """20.5 → '20,5 m' (decimal comma, without extra zeros)."""
    return comma(f"{x:.3f}".rstrip("0").rstrip(".")) + " m"


def _require_kind(data: Data, kind: Kind, what: str, role: str | None = None) -> None:
    if not isinstance(data, Data):               # a value written by hand where a connected data goes
        raise ShapeError(tr('“{value}” should be a {what}: connect a node that gives it (it is not typed by hand).').format(value=tr(role) if role else str(data), what=tr(what)))
    if data.kind != kind:
        raise ShapeError(tr('“{value}” should be a {what}, and it is {what_is}.').format(
                               value=tr(role) if role else data._name(), what=tr(what), what_is=_what_is(data)))


def _require_mesh(data: Data) -> None:
    _require_geometry(data)
    if data.kind is None or data.kind.faces is None:
        raise ShapeError(tr('“{name}” should be a geometry with faces, and it is {what_is}.').format(
                               name=data._name(), what_is=_what_is(data)))


def _what_is(data: Data) -> str:
    kind = getattr(data, "kind", None)
    return f"«{tr(kind.name)}»" if kind is not None else tr('a number')


def _require_geometry(data: Data) -> None:
    if not isinstance(data, Data):                 # a number written where a geometry goes (0 in an input)
        raise ShapeError(tr('A geometry is expected here, and it is {value}.').format(value=data))
    if data.kind is None:
        raise ShapeError(tr('“{name}” should be a geometry, and it is a number.').format(name=data._name()))


#: Two vertices of a polygon closer than this (1 micron) are the same (the padding, or a cut at a vertex).
TOLERANCE_VERTEX = 1e-6


def real_faces(kind: Kind, vertices: np.ndarray) -> list[list[int]]:
    """The faces of an element without the repeated vertices of the padding (polygons); without those left without
    area. For the usual kinds, their faces as they are."""
    if not kind.polygon:
        return [list(c) for c in kind.faces]
    result = []
    for face in kind.faces:
        clean = []
        for i in face:
            if not clean or np.linalg.norm(vertices[i] - vertices[clean[-1]]) > TOLERANCE_VERTEX:
                clean.append(i)
        while len(clean) > 1 and np.linalg.norm(vertices[clean[0]] - vertices[clean[-1]]) <= TOLERANCE_VERTEX:
            clean.pop()
        if len(clean) >= 3:
            result.append(clean)
    return result


def gravity_direction(gravity) -> np.ndarray:
    """Where the weight pulls: a direction of length 1 from a vector (0; 0; -1 by default in the nodes). An empty,
    zero or non-numeric value gives a clear notice instead of an error of Python."""
    try:
        g = np.asarray(gravity.values if isinstance(gravity, Data) else gravity, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        g = np.zeros(0)
    if len(g) < 3 or not np.all(np.isfinite(g[:3])):
        raise ShapeError(tr('The gravity must be a direction: three numbers, such as 0; 0; -1.'))
    g = g[:3]
    if np.linalg.norm(g) < 1e-12:
        raise ShapeError(tr('The gravity cannot be zero (0, 0, 0).'))
    return g / np.linalg.norm(g)
