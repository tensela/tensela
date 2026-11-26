"""Export to DXF (Delivery 4, step 3): for AutoCAD, BricsCAD, Rhino, SketchUp, Revit…

DXF works, like the engine, with **Z up**: there are no turns. Each visible node is a **layer** with its name and its
colour; each element (each sun fin, each panel) is a separate object, which is picked on its own:

- the meshes, as *meshes* (MESH, AutoCAD 2010 onwards: BricsCAD, Rhino, ArchiCAD…). With `compatible=True`, as
  *polyface meshes* (POLYFACE), which old programs and SketchUp also read, but the file takes ten times longer and
  weighs twice as much;
- the curves, as *3D polylines*;
- the points, as *points*.

The unit (m, cm, mm, inches or feet) is written in the file, so that the program that opens it sets the scale right.

**In 2D** (`view=`), the drawing is the projection in plan, from a camera (`CameraView`, as the 3D view is seen), in an
elevation (south, north, east, west; Y is north) or in an isometric (from above each corner), at real size: the edges of
each piece as lines (without repeating those that fall on one another), the curves as polylines and the points as
points. All the edges are seen, also those behind; with `visible_only=True`, only what is seen from that view: the
hidden lines are removed with the same computation Croquis uses (a depth buffer, about 4000 px on the longer side: what
is half cut keeps the precision of one pixel, a few millimetres on a facade). A plan can be **cut at a height**
(`cut=`), as architects draw it: what is above is left out, and the lines of the cut go in a layer of their own per
node, thicker.

It uses the free library `ezdxf` (pip install -e '.[dxf]').
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..data import Data, ShapeError
from ..geometry import real_faces
from ..language import tr

# Scale from metres and $INSUNITS code. Feet and inches: the same in the imperial and the
# US systems (1" = 25.4 mm exactly).
UNITS_DXF = {"m": (1.0, 6), "cm": (100.0, 5), "mm": (1000.0, 4), "in": (1 / 0.0254, 1), "ft": (1 / 0.3048, 2)}

# 2D views: the direction the eye looks in, and what is «up» in the drawing. Each elevation is seen from outside (the
# south from -Y, the north from +Y…); each isometric from above a corner (the southwest from -X -Y, looking down at
# the same angle on the three axes, as the isometric views of the CAD programs).
VIEWS = {
    "plan": ((0, 0, -1), (0, 1, 0)),
    "south elevation": ((0, 1, 0), (0, 0, 1)),
    "north elevation": ((0, -1, 0), (0, 0, 1)),
    "east elevation": ((-1, 0, 0), (0, 0, 1)),
    "west elevation": ((1, 0, 0), (0, 0, 1)),
    "southwest isometric": ((1, 1, -1), (0, 0, 1)),
    "southeast isometric": ((-1, 1, -1), (0, 0, 1)),
    "northeast isometric": ((-1, -1, -1), (0, 0, 1)),
    "northwest isometric": ((1, -1, -1), (0, 0, 1)),
}


@dataclass(frozen=True)
class CameraView:
    """A 2D view from a camera, as the 3D view is seen now: where the eye is, what it looks at, what is up, and whether
    it is in perspective (with its vertical angle of view, in degrees). In perspective the drawing is at real size on
    the plane of what it looks at (closer is bigger, farther smaller); in parallel, at real size everywhere."""
    eye: tuple
    target: tuple
    up: tuple
    perspective: bool = True
    angle: float = 30.0


#: The names of the views before the move to English (saved preferences, scripts).
OLD_VIEWS = {"planta": "plan", "alzado sur": "south elevation", "alzado norte": "north elevation",
             "alzado este": "east elevation", "alzado oeste": "west elevation"}


def _ezdxf():
    try:
        import ezdxf
    except ImportError:
        raise ShapeError(tr("Exporting to DXF needs the ezdxf library: pip install -e '.[dxf]'.")) from None
    return ezdxf


def _layer(name: str, used: set[str]) -> str:
    """A valid DXF layer name (without < > / \\ " : ; ? * | = `), not repeated."""
    base = re.sub(r'[<>/\\":;?*|=`]', "_", name).strip() or tr("object")
    layer, n = base, 2
    while layer.lower() in used:
        layer, n = f"{base} {n}", n + 1
    used.add(layer.lower())
    return layer


def export_dxf(filepath, objects: list[tuple[str, Data, dict]], unit: str = "m",
                 compatible: bool = False, view: str | None = None, visible_only: bool = False,
                 cut: float | None = None) -> Path:
    """Writes the geometries in a DXF (AutoCAD 2010), one layer per node.

    `objects`: (name, data, style), as `Project.visible_objects()`; `style` may have «color» («#rrggbb») and «opacity».
    Without `view`, in 3D; with `view` (plan, south elevation…), in 2D; `visible_only` removes the hidden lines in 2D.
    `cut` (only in plan): the height (in metres, as the model) of a horizontal cut, as in an architect's plan: what is
    above it is not drawn, and where the plane cuts the faces goes in a layer of its own per node, «<name> (cut)»,
    with a thicker line.
    """
    if unit not in UNITS_DXF:
        raise ShapeError(tr("I don't know the unit “{unit}”. Options: {options}.").format(
            unit=unit, options=", ".join(UNITS_DXF)))
    view = OLD_VIEWS.get(view, view) if isinstance(view, str) else view
    if view is not None and not isinstance(view, CameraView) and view not in VIEWS:
        raise ShapeError(tr("I don't know the view “{view}”. Options: {options}.").format(
            view=view, options=", ".join(VIEWS)))
    if cut is not None and view != "plan":
        raise ShapeError(tr("The cut at a height is for the plan."))
    if not objects:
        raise ShapeError(tr("There is nothing to export."))
    ezdxf = _ezdxf()

    scale, code = UNITS_DXF[unit]
    if isinstance(view, CameraView):                     # the camera in the unit of the drawing, like the geometry
        view = CameraView(tuple(np.array(view.eye, dtype=float) * scale),
                          tuple(np.array(view.target, dtype=float) * scale), view.up, view.perspective, view.angle)
    doc = ezdxf.new("R2010", units=code)
    doc.header["$MEASUREMENT"] = 0 if unit in ("in", "ft") else 1  # imperial or metric
    msp = doc.modelspace()
    used: set[str] = set()
    visible = visible_lines(objects, view, scale, below=cut) if view is not None and visible_only else None

    for k, (name, data, style_name) in enumerate(objects):
        if data.kind is None:
            raise ShapeError(tr("“{name}” is not a geometry: it cannot be exported to DXF.").format(name=name))
        layer = doc.layers.add(_layer(name, used))
        h = style_name.get("color", "#8a96a3").lstrip("#")
        layer.rgb = tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))
        opacity = float(style_name.get("opacity", 1.0))
        if opacity < 1.0:
            layer.transparency = 1.0 - opacity
        attributes = {"layer": layer.dxf.name}

        vertices = (data.values[data.mask] if data.levels else data.values[None]) * scale
        if cut is not None:
            _draw_cut(doc, msp, name, data, cut, scale, layer, used)
        if visible is not None and (data.kind.curve or data.kind.faces is not None):
            for a, b in _without_repeat(visible[k]).tolist():
                msp.add_line(a, b, dxfattribs=attributes)
        elif view is not None and cut is not None:
            _draw_2d_below(msp, data, vertices, cut * scale, view, attributes)
        elif view is not None:
            _draw_2d(msp, data, _project(vertices, view), attributes)
        elif data.kind.curve:
            for points in vertices:
                msp.add_polyline3d(points.tolist(), close=data.kind.closed, dxfattribs=attributes)
        elif data.kind.faces is None:                                   # puntos
            for p in vertices.reshape(-1, 3):
                msp.add_point(p.tolist(), dxfattribs=attributes)
        else:
            if compatible:
                faces = _to_4_faces(data.kind.faces)
                for element in vertices:
                    list_ = element.tolist()
                    own = _to_4_faces(real_faces(data.kind, element)) if data.kind.polygon else faces
                    msp.add_polyface(dxfattribs=attributes).append_faces([[list_[i] for i in c] for c in own])
            else:
                faces = [list(c) for c in data.kind.faces]
                for element in vertices:
                    mesh = msp.add_mesh(dxfattribs=attributes)
                    with mesh.edit_data() as data_items:
                        data_items.vertices = element.tolist()
                        data_items.faces = real_faces(data.kind, element) if data.kind.polygon else faces

    filepath = Path(filepath)
    doc.saveas(filepath)
    return filepath


#: Pixels of the longer side of the depth buffer with which the hidden lines are removed.
VISIBLE_RESOLUTION = 4000
#: The line of what is cut in a plan, in hundredths of a millimetre (0.50 mm); the rest keeps that of its layer.
CUT_LINEWEIGHT = 50


def visible_lines(objects, view: str, scale: float = 1.0, below: float | None = None) -> list[np.ndarray]:
    """What is seen of each object from `view`, as 2D segments (N × 2 × 2), already in the drawing.

    The opaque covers; the transparent (opacity < 1) lets what is behind be seen, as in Croquis. `below`: only what is
    under that height (in the units of the model) is seen, as in a plan cut there.
    """
    from ..croquis import visibility as vis
    from ..croquis.view import Camera, geometry_of

    parts = [geometry_of(data) for _, data, _ in objects]
    if below is not None:
        parts = [_below(part, below) for part in parts]
    cover = [t * scale for (t, _, _, _), (_, _, e) in zip(parts, objects) if float(e.get("opacity", 1.0)) >= 1.0]
    tris = np.concatenate(cover) if cover else np.empty((0, 3, 3))
    all_ = np.concatenate([np.concatenate([t.reshape(-1, 3), d.reshape(-1, 3), b.reshape(-1, 3)])
                            for t, d, b, _ in parts]) * scale
    if not len(all_):
        return [np.empty((0, 2, 2)) for _ in objects]
    if isinstance(view, CameraView) and view.perspective:
        return _visible_in_perspective(parts, tris, all_, view, scale)
    under, height = all_.min(axis=0), all_.max(axis=0)
    centre, radius = (under + height) / 2, max(float(np.linalg.norm(height - under)) / 2, 1e-9)
    plane = _project(all_, view)
    width_m, height_m = np.ptp(plane, axis=0) + 2 * radius * 0.02 + 1e-9            # a margin
    size = max(width_m, height_m) / VISIBLE_RESOLUTION                               # metres (or mm) per pixel
    W, H = int(np.ceil(width_m / size)), int(np.ceil(height_m / size))
    _, above, ahead = _basis(view)
    camera = Camera(centre - ahead * radius * 3, centre, above, W / H, perspective=False,
                    middle_height=H * size / 2, near=radius, far=radius * 5)
    zbuf, _ = vis.depth_buffer(tris, vis.clip_matrix(camera), W, H, False)
    u0, v0 = _project(centre, view)
    output = []
    for t, hard, soft, normals in parts:
        geom = (tris, hard * scale, soft * scale, normals)
        segs, _outline = vis.visible_lines(geom, camera, W, H, zbuf=zbuf)
        if len(segs):
            segs, _outline = vis.merge_collinear(segs, _outline, tol=1.5)
            # An edge right on that of a piece in front may stay (it is drawn over its own);
            # the remains of less than two pixels next to a covered corner, no.
            segs = segs[np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]) >= 2.0]
        xs = u0 + (segs[:, [0, 2]] - W / 2) * size
        ys = v0 - (segs[:, [1, 3]] - H / 2) * size
        output.append(np.stack([np.stack([xs[:, 0], ys[:, 0]], -1), np.stack([xs[:, 1], ys[:, 1]], -1)], axis=1))
    return output


def _visible_in_perspective(parts, tris, points: np.ndarray, view: CameraView, scale: float) -> list[np.ndarray]:
    """`visible_lines` from a camera in perspective: the depth buffer framed on all that is in front of the eye (a
    frame centred on where it looks, as wide as needed), and each pixel back to the plane of what it looks at."""
    from ..croquis import visibility as vis
    from ..croquis.view import Camera

    eye, target = np.array(view.eye, dtype=float), np.array(view.target, dtype=float)
    right, up, ahead = _basis(view)
    distance = float(np.linalg.norm(target - eye))
    depth = (points - eye) @ ahead
    ahead_of = points[depth > distance * 1e-3]
    if not len(ahead_of):
        return [np.empty((0, 2, 2)) for _ in parts]
    picture = _project(ahead_of, CameraView(tuple(eye), tuple(target), view.up, True, view.angle))
    half_w, half_h = (np.abs(picture).max(axis=0) * 1.02 + 1e-9)                     # with a margin
    side = VISIBLE_RESOLUTION / 2
    H = int(np.ceil(2 * side * min(1.0, half_h / half_w)))
    W = int(np.ceil(H * half_w / half_h))
    camera = Camera(eye, target, up, W / H, perspective=True, angle=math.degrees(2 * math.atan(half_h / distance)),
                    near=max(float(depth[depth > distance * 1e-3].min()) * 0.5, distance * 1e-3),
                    far=float(depth.max()) * 1.5 + distance)
    zbuf, _ = vis.depth_buffer(tris, vis.clip_matrix(camera), W, H, True)
    output = []
    for t, hard, soft, normals in parts:
        segs, _outline = vis.visible_lines((tris, hard * scale, soft * scale, normals), camera, W, H, zbuf=zbuf)
        if len(segs):
            segs, _outline = vis.merge_collinear(segs, _outline, tol=1.5)
            segs = segs[np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]) >= 2.0]
            segs = _without_stubs(segs)
        unit = half_h / (H / 2)                                     # the plane of what it looks at, per pixel
        xs = (segs[:, [0, 2]] - W / 2) * unit
        ys = -(segs[:, [1, 3]] - H / 2) * unit
        output.append(np.stack([np.stack([xs[:, 0], ys[:, 0]], -1), np.stack([xs[:, 1], ys[:, 1]], -1)], axis=1))
    return output


#: In perspective, the edges that go away behind a face keep a few pixels next to its corner (the depth is compared
#: with a margin): pieces shorter than this, hanging from a corner with the other end in the air, are left out.
STUB_PIXELS = 16.0


def _without_stubs(segs: np.ndarray, touch: float = 2.0) -> np.ndarray:
    """The pieces in pixels (N × 4) without the short ones that hang from the end of another with their other end
    loose."""
    ends = segs.reshape(-1, 2)
    length = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    keep = np.ones(len(segs), dtype=bool)
    for i in np.nonzero(length < STUB_PIXELS)[0]:
        others = np.delete(ends, [2 * i, 2 * i + 1], axis=0)
        touching = [bool((np.hypot(*(others - ends[2 * i + k]).T) <= touch).any()) for k in (0, 1)]
        if touching[0] != touching[1]:
            keep[i] = False
    return segs[keep]


def _basis(view) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The X and the Y of the drawing in the model, and the direction the eye looks in (unit vectors). In the plan
    and the elevations they are axes of the model with their sign, exactly."""
    if isinstance(view, CameraView):
        ahead = np.array(view.target, dtype=float) - np.array(view.eye, dtype=float)
        above = np.array(view.up, dtype=float)
    else:
        ahead, above = (np.array(v, dtype=float) for v in VIEWS[view])
    ahead /= np.linalg.norm(ahead)
    right = np.cross(ahead, above)
    right /= np.linalg.norm(right)
    return right, np.cross(right, ahead), ahead


def _project(vertices: np.ndarray, view) -> np.ndarray:
    """The points in the drawing. From a camera in perspective, on the plane of what it looks at (NaN for what is
    behind the eye)."""
    right, up, ahead = _basis(view)
    if isinstance(view, CameraView) and view.perspective:
        eye = np.array(view.eye, dtype=float)
        distance = float(np.linalg.norm(np.array(view.target, dtype=float) - eye))
        relative = vertices - eye
        depth = relative @ ahead
        with np.errstate(divide="ignore", invalid="ignore"):
            factor = np.where(depth > distance * 1e-3, distance / depth, np.nan)
        return np.stack([(relative @ right) * factor, (relative @ up) * factor], axis=-1)
    return np.stack([vertices @ right, vertices @ up], axis=-1)


# --- The cut of a plan -------------------------------------------------------------------------------------------

def _segments_below(runs: np.ndarray, height: float, more: np.ndarray | None = None):
    """The parts of the 3D segments (N × 2 × 3) under `height`; `more` (N × 2 × 3, the normals of the soft edges)
    travels with them unchanged."""
    if not len(runs):
        return runs, more
    za, zb = runs[:, 0, 2], runs[:, 1, 2]
    keep = (za <= height) | (zb <= height)
    runs, za, zb = runs[keep].copy(), za[keep], zb[keep]
    more = more[keep] if more is not None else None
    for end, z, other in ((0, za, zb), (1, zb, za)):             # the end above the cut comes down to it
        high = z > height
        t = (height - other[high]) / (z[high] - other[high])
        runs[high, end] = runs[high, 1 - end] + (runs[high, end] - runs[high, 1 - end]) * t[:, None]
    return runs, more


def _triangles_below(tris: np.ndarray, height: float) -> np.ndarray:
    """The parts of the triangles (N × 3 × 3) under `height`, as triangles: a triangle cut by the plane leaves one
    triangle (one corner under it) or two (two corners)."""
    if not len(tris):
        return tris
    under = tris[..., 2] <= height
    count = under.sum(axis=1)
    output = [tris[count == 3]]
    for t, inside in zip(tris[(count == 1) | (count == 2)], under[(count == 1) | (count == 2)]):
        ring = []
        for i in range(3):                                   # Sutherland–Hodgman against one plane
            a, b = t[i], t[(i + 1) % 3]
            if inside[i]:
                ring.append(a)
            if inside[i] != inside[(i + 1) % 3]:
                ring.append(a + (b - a) * (height - a[2]) / (b[2] - a[2]))
        output.append(np.array([(ring[0], ring[k], ring[k + 1]) for k in range(1, len(ring) - 1)]).reshape(-1, 3, 3))
    return np.concatenate(output)


def _below(part, height: float):
    """A part of `geometry_of` (triangles, hard edges, soft edges, their normals) cut at `height`: what is under it."""
    tris, hard, soft, normals = part
    soft, normals = _segments_below(soft, height, normals)
    return _triangles_below(tris, height), _segments_below(hard, height)[0], soft, normals


def cut_lines(data: Data, height: float) -> np.ndarray:
    """Where the horizontal plane at `height` cuts the faces of `data`: 3D segments (N × 2 × 3) at that height."""
    from ..croquis.view import geometry_of
    if data.kind is None or data.kind.faces is None:
        return np.empty((0, 2, 3))
    tris = geometry_of(data)[0]
    above = tris[..., 2] > height
    crossing = tris[above.any(axis=1) & ~above.all(axis=1)]
    runs = []
    for t in crossing:
        points = []
        for i in range(3):
            a, b = t[i], t[(i + 1) % 3]
            if (a[2] > height) != (b[2] > height):
                points.append(a + (b - a) * (height - a[2]) / (b[2] - a[2]))
        if len(points) == 2:
            runs.append(points)
    return np.array(runs, dtype=float).reshape(-1, 2, 3)


def _draw_cut(doc, msp, name: str, data: Data, height: float, scale: float, layer, used: set[str]) -> None:
    """The cut lines of a node, in their own layer («<name> (cut)»), with its colour and a thicker line."""
    runs = cut_lines(data, height)
    if not len(runs):
        return
    own = doc.layers.add(_layer(tr("{name} (cut)").format(name=name), used))
    own.rgb = layer.rgb
    own.dxf.lineweight = CUT_LINEWEIGHT
    plane = _joined(_without_repeat(_project(runs * scale, "plan")))
    for a, b in plane.tolist():
        msp.add_line(a, b, dxfattribs={"layer": own.dxf.name})


def _joined(runs: np.ndarray) -> np.ndarray:
    """The 2D segments (N × 2 × 2) with those on the same line that touch or overlap made into one (a cut face comes
    out in pieces, one per triangle)."""
    if len(runs) < 2:
        return runs
    tolerance = 1e-6 * max(1.0, float(np.abs(runs).max()))
    lines: dict[tuple, list] = {}
    for a, b in runs:
        d = b - a
        d = d / np.linalg.norm(d)
        if d[0] < -tolerance or (abs(d[0]) <= tolerance and d[1] < 0):      # one direction for both ways
            d = -d
        offset = d[0] * a[1] - d[1] * a[0]                                  # where the line passes
        key = (round(d[0] / 1e-6), round(d[1] / 1e-6), round(offset / tolerance))
        lines.setdefault(key, []).append(sorted((float(a @ d), float(b @ d))) + [d, offset])
    output = []
    for parts in lines.values():
        parts.sort(key=lambda p: p[0])
        d, offset = parts[0][2], parts[0][3]
        normal = np.array([-d[1], d[0]]) * offset
        start, end = parts[0][0], parts[0][1]
        for p in parts[1:] + [None]:
            if p is not None and p[0] <= end + tolerance:
                end = max(end, p[1])
                continue
            output.append((normal + d * start, normal + d * end))
            if p is not None:
                start, end = p[0], p[1]
    return np.array(output, dtype=float).reshape(-1, 2, 2)


def _draw_2d_below(msp, data: Data, vertices: np.ndarray, height: float, view: str, attributes: dict) -> None:
    """Like `_draw_2d`, of only what is under `height` (all the edges, also those behind)."""
    if data.kind.faces is None and not data.kind.curve:                # puntos
        for p in vertices.reshape(-1, 3):
            if p[2] <= height:
                msp.add_point(_project(p, view).tolist(), dxfattribs=attributes)
        return
    if data.kind.curve:
        order = list(range(vertices.shape[1])) + ([0] if data.kind.closed else [])
        runs = np.stack([vertices[:, order[:-1]], vertices[:, order[1:]]], axis=2).reshape(-1, 2, 3)
    else:
        runs = vertices[:, _edges(data.kind.faces)].reshape(-1, 2, 3)
    runs, _ = _segments_below(runs, height)
    for a, b in _without_repeat(_project(runs, view)).tolist():
        msp.add_line(a, b, dxfattribs=attributes)


def _edges(faces) -> np.ndarray:
    """The edges of a kind of mesh, each one once (E × 2 indices)."""
    unique = {tuple(sorted((c[k], c[(k + 1) % len(c)]))) for c in faces for k in range(len(c))}
    return np.array(sorted(unique), dtype=int)


def _draw_2d(msp, data: Data, plane: np.ndarray, attributes: dict) -> None:
    if data.kind.curve:
        for points in plane:
            if np.isfinite(points).all():                               # not behind the eye of a camera
                msp.add_lwpolyline(points.tolist(), close=data.kind.closed, dxfattribs=attributes)
        return
    if data.kind.faces is None:                                         # puntos
        for p in plane.reshape(-1, 2):
            if np.isfinite(p).all():
                msp.add_point(p.tolist(), dxfattribs=attributes)
        return
    edges = _edges(data.kind.faces)
    runs = plane[:, edges]                                         # piezas × aristas × 2 × 2
    for piece in runs:
        for a, b in _without_repeat(piece).tolist():
            msp.add_line(a, b, dxfattribs=attributes)


def _without_repeat(runs: np.ndarray, tolerance: float | None = None) -> np.ndarray:
    """The 2D segments (N × 2 × 2) without those seen end-on (length 0) and without repeating those that fall on one another."""
    runs = runs[np.isfinite(runs).all(axis=(1, 2))] if len(runs) else runs        # behind the eye of a camera: out
    if not len(runs):
        return runs
    if tolerance is None:
        tolerance = 1e-6 * max(1.0, float(np.abs(runs).max()))
    long = runs[np.linalg.norm(runs[:, 1] - runs[:, 0], axis=-1) > tolerance].copy()
    keys = np.round(long / tolerance).astype(np.int64)
    on_reverse = (keys[:, 0, 0] > keys[:, 1, 0]) | (
        (keys[:, 0, 0] == keys[:, 1, 0]) & (keys[:, 0, 1] > keys[:, 1, 1]))
    long[on_reverse] = long[on_reverse][:, ::-1]
    keys[on_reverse] = keys[on_reverse][:, ::-1]
    _, which = np.unique(keys.reshape(len(keys), 4), axis=0, return_index=True)
    return long[np.sort(which)]


def _to_4_faces(faces) -> list[tuple[int, ...]]:
    """DXF polyface meshes accept faces of 3 or 4 vertices: the bigger ones are opened as a fan."""
    output = []
    for c in faces:
        if len(c) <= 4:
            output.append(tuple(c))
        else:
            output.extend((c[0], c[i], c[i + 1]) for i in range(1, len(c) - 1))
    return output


def read_summary(filepath) -> dict[str, dict[str, int]]:
    """For checking: how many objects of each class there are in each layer."""
    doc = _ezdxf().readfile(filepath)
    summary: dict[str, dict[str, int]] = {}
    for e in doc.modelspace():
        class_ = e.dxftype() if e.dxftype() != "POLYLINE" else ("POLYFACE" if e.is_poly_face_mesh else "POLYLINE3D")
        by_layer = summary.setdefault(e.dxf.layer, {})
        by_layer[class_] = by_layer.get(class_, 0) + 1
    return summary

