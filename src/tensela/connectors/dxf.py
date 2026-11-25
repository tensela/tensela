"""Export to DXF (Delivery 4, step 3): for AutoCAD, BricsCAD, Rhino, SketchUp, Revit…

DXF works, like the engine, with **Z up**: there are no turns. Each visible node is a **layer** with its name and its
colour; each element (each sun fin, each panel) is a separate object, which is picked on its own:

- the meshes, as *meshes* (MESH, AutoCAD 2010 onwards: BricsCAD, Rhino, ArchiCAD…). With `compatible=True`, as
  *polyface meshes* (POLYFACE), which old programs and SketchUp also read, but the file takes ten times longer and
  weighs twice as much;
- the curves, as *3D polylines*;
- the points, as *points*.

The unit (m, cm, mm, inches or feet) is written in the file, so that the program that opens it sets the scale right.

**In 2D** (`view=`), the drawing is the projection in plan or in an elevation (south, north, east, west; Y is north),
at real size: the edges of each piece as lines (without repeating those that fall on one another), the curves as
polylines and the points as points. All the edges are seen, also those behind; with `visible_only=True`, only what
is seen from that view: the hidden lines are removed with the same computation Croquis uses (a depth buffer, about
4000 px on the longer side: what is half cut keeps the precision of one pixel, a few millimetres on a facade).

It uses the free library `ezdxf` (pip install -e '.[dxf]').
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from ..data import Data, ShapeError
from ..geometry import real_faces
from ..language import tr

# Scale from metres and $INSUNITS code. Feet and inches: the same in the imperial and the
# US systems (1" = 25.4 mm exactly).
UNITS_DXF = {"m": (1.0, 6), "cm": (100.0, 5), "mm": (1000.0, 4), "in": (1 / 0.0254, 1), "ft": (1 / 0.3048, 2)}

# 2D views: which axes of the model go to the X and Y of the drawing, and with what sign.
# Each elevation is seen from outside: the south from -Y, the north from +Y…
VIEWS = {
    "plan": ((0, 1.0), (1, 1.0)),
    "south elevation": ((0, 1.0), (2, 1.0)),
    "north elevation": ((0, -1.0), (2, 1.0)),
    "east elevation": ((1, 1.0), (2, 1.0)),
    "west elevation": ((1, -1.0), (2, 1.0)),
}
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
                 compatible: bool = False, view: str | None = None, visible_only: bool = False) -> Path:
    """Writes the geometries in a DXF (AutoCAD 2010), one layer per node.

    `objects`: (name, data, style), as `Project.visible_objects()`; `style` may have «color» («#rrggbb») and «opacity».
    Without `view`, in 3D; with `view` (plan, south elevation…), in 2D; `visible_only` removes the hidden lines in 2D.
    """
    if unit not in UNITS_DXF:
        raise ShapeError(tr("I don't know the unit “{unit}”. Options: {options}.").format(
            unit=unit, options=", ".join(UNITS_DXF)))
    view = OLD_VIEWS.get(view, view)
    if view is not None and view not in VIEWS:
        raise ShapeError(tr("I don't know the view “{view}”. Options: {options}.").format(
            view=view, options=", ".join(VIEWS)))
    if not objects:
        raise ShapeError(tr("There is nothing to export."))
    ezdxf = _ezdxf()

    scale, code = UNITS_DXF[unit]
    doc = ezdxf.new("R2010", units=code)
    doc.header["$MEASUREMENT"] = 0 if unit in ("in", "ft") else 1  # imperial or metric
    msp = doc.modelspace()
    used: set[str] = set()
    visible = visible_lines(objects, view, scale) if view is not None and visible_only else None

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
        if visible is not None and (data.kind.curve or data.kind.faces is not None):
            for a, b in _without_repeat(visible[k]).tolist():
                msp.add_line(a, b, dxfattribs=attributes)
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
# From where each view is seen (where the eye looks) and what is «up» in the drawing.
_VIEWS = {
    "plan": ((0, 0, -1), (0, 1, 0)),
    "south elevation": ((0, 1, 0), (0, 0, 1)),
    "north elevation": ((0, -1, 0), (0, 0, 1)),
    "east elevation": ((-1, 0, 0), (0, 0, 1)),
    "west elevation": ((1, 0, 0), (0, 0, 1)),
}


def visible_lines(objects, view: str, scale: float = 1.0) -> list[np.ndarray]:
    """What is seen of each object from `view`, as 2D segments (N × 2 × 2), already in the drawing.

    The opaque covers; the transparent (opacity < 1) lets what is behind be seen, as in Croquis.
    """
    from ..croquis import visibility as vis
    from ..croquis.view import Camera, geometry_of

    parts = [geometry_of(data) for _, data, _ in objects]
    cover = [t * scale for (t, _, _, _), (_, _, e) in zip(parts, objects) if float(e.get("opacity", 1.0)) >= 1.0]
    tris = np.concatenate(cover) if cover else np.empty((0, 3, 3))
    all_ = np.concatenate([np.concatenate([t.reshape(-1, 3), d.reshape(-1, 3), b.reshape(-1, 3)])
                            for t, d, b, _ in parts]) * scale
    if not len(all_):
        return [np.empty((0, 2, 2)) for _ in objects]
    under, height = all_.min(axis=0), all_.max(axis=0)
    centre, radius = (under + height) / 2, max(float(np.linalg.norm(height - under)) / 2, 1e-9)
    plane = _project(all_, view)
    width_m, height_m = np.ptp(plane, axis=0) + 2 * radius * 0.02 + 1e-9            # a margin
    size = max(width_m, height_m) / VISIBLE_RESOLUTION                               # metres (or mm) per pixel
    W, H = int(np.ceil(width_m / size)), int(np.ceil(height_m / size))
    ahead, above = (np.array(v, dtype=float) for v in _VIEWS[view])
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


def _project(vertices: np.ndarray, view: str) -> np.ndarray:
    (i, yes), (j, sj) = VIEWS[view]
    return np.stack([vertices[..., i] * yes, vertices[..., j] * sj], axis=-1)


def _edges(faces) -> np.ndarray:
    """The edges of a kind of mesh, each one once (E × 2 indices)."""
    unique = {tuple(sorted((c[k], c[(k + 1) % len(c)]))) for c in faces for k in range(len(c))}
    return np.array(sorted(unique), dtype=int)


def _draw_2d(msp, data: Data, plane: np.ndarray, attributes: dict) -> None:
    if data.kind.curve:
        for points in plane:
            msp.add_lwpolyline(points.tolist(), close=data.kind.closed, dxfattribs=attributes)
        return
    if data.kind.faces is None:                                         # puntos
        for p in plane.reshape(-1, 2):
            msp.add_point(p.tolist(), dxfattribs=attributes)
        return
    edges = _edges(data.kind.faces)
    runs = plane[:, edges]                                         # piezas × aristas × 2 × 2
    for piece in runs:
        for a, b in _without_repeat(piece).tolist():
            msp.add_line(a, b, dxfattribs=attributes)


def _without_repeat(runs: np.ndarray, tolerance: float | None = None) -> np.ndarray:
    """The 2D segments (N × 2 × 2) without those seen end-on (length 0) and without repeating those that fall on one another."""
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

