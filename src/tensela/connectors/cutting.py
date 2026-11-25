"""The cutting file: flat pieces for a laser, a router, a plasma or a water jet, in DXF or SVG, in millimetres.

What is cut and what is engraved go apart, as the machines expect: the outlines of the pieces on the layer «cut» (red)
and their numbers on «engrave» (blue). In DXF, the sheets go on a layer «sheet» that is off (a reference: switch it on
to see the edge of the board). The curves are polylines of short straight segments (as fine as the pieces were
computed), which every machine reads; no NURBS.

With the pieces laid on several sheets (Lay flat), each sheet is a file of its own, from (0, 0): `name_1.svg`,
`name_2.svg`…, and one more, `name_all.svg`, with all of them side by side and their edges drawn, to check them at a
glance (not to cut: the machine takes one sheet at a time). Anything visible must lie flat on the ground (z = 0):
Lay flat does that.
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np

from ..data import Data, ShapeError
from ..language import tr

SCALE = {"mm": 1000.0, "cm": 100.0, "m": 1.0, "in": 1 / 0.0254}
#: The operations, their layer colour (SVG) and their AutoCAD colour number (DXF).
OPERATIONS = {"cut": ("#FF0000", 1), "engrave": ("#0000FF", 5), "sheet": ("#808080", 8)}


def _curves(data: Data) -> list[tuple[np.ndarray, bool]]:
    """Each element of a flat geometry as (its points, closed?), without the padding."""
    from ..fabrication import _closed_ring, _without_repeats
    kind = data.kind
    if kind is None or kind.curve is False and kind.faces is None:
        raise ShapeError(tr('“{name}” is not a drawing of lines: it cannot go in a cutting file.').format(
            name=data._name()))
    values = np.asarray(data.values, float)
    if kind.faces is not None and not kind.curve:
        if len(kind.faces) != 1:
            raise ShapeError(tr('“{name}” has faces in space: lay its pieces flat first (Lay flat).').format(
                name=data._name()))
        values, closed = values[..., list(kind.faces[0]), :], True
    else:
        closed = kind.closed
    flat = values.reshape((-1,) + values.shape[-2:])
    # With a level «contour» (pieces with holes), which are holes: contour 1 onwards.
    holes = np.zeros(len(flat), bool)
    if data.levels and data.levels[-1] == "contour":
        holes = (np.indices(values.shape[:len(data.levels)])[-1] > 0).reshape(-1)
    mask = np.broadcast_to(data.mask, values.shape[:len(data.levels)]).reshape(-1) if data.levels else [True]
    out = []
    for c, hole, there in zip(flat, holes, mask):
        if not there or np.isnan(c).any():
            continue
        c = _closed_ring(c, 1e-12) if closed else _without_repeats(c, 1e-12)
        if len(c) >= 2:
            out.append((c, closed, bool(hole)))
    return out


def lying_flat(items: list[tuple[str, Data]]) -> tuple[list[tuple[str, Data]], list[str]]:
    """What can go in a cutting file (lines lying flat on the ground) and the names of what cannot (the model in 3D,
    which is usually visible beside its sheets)."""
    keep, out = [], []
    for name, data in items:
        try:
            lines = _curves(data)
        except ShapeError:
            out.append(name)
            continue
        if lines and all(np.abs(p[:, 2]).max() <= 1e-6 for p, _, _ in lines):
            keep.append((name, data))
        else:
            out.append(name)
    return keep, out


def gather(items: list[tuple[str, Data]]) -> tuple[list[tuple[str, np.ndarray, bool]], list]:
    """What goes in the file: (operation, points, closed) for each line, and the boxes of the sheets (if a Lay flat
    gives them). Anything not lying flat on the ground is said."""
    lines, boxes = [], []
    for name, data in items:
        layout = getattr(data, "layout", None)
        if layout is not None:                       # the sheets of every Lay flat shown (each once)
            boxes += [b for b in layout.boxes if not any(np.allclose(b, c) for c in boxes)]
        operation = getattr(data, "operation", "cut")
        for points, closed, hole in _curves(data):
            if np.abs(points[:, 2]).max() > 1e-6:
                raise ShapeError(tr('“{name}” is not lying flat on the ground (z = 0): lay its pieces flat first, '
                                    'with Lay flat.').format(name=name))
            lines.append((operation, points[:, :2], closed, hole))
    if not lines:
        raise ShapeError(tr('There is nothing to cut: no visible node has lines.'))
    # The engraving first, then the cuts from the inside out: a hole before the outline around it, and a piece laid
    # in the hole of another before that hole (cut free first, it would fall out with the piece still in it).
    order = {"engrave": 0, "cut": 1, "sheet": 2}
    depth = _depths([line[1] if line[0] == "cut" and line[2] else None for line in lines],
                    [line[1][0] if line[0] == "cut" else None for line in lines])
    keys = [(order.get(line[0], 1), -depth[k] if order.get(line[0], 1) == 1 else 0) for k, line in enumerate(lines)]
    lines = [lines[k] for k in sorted(range(len(lines)), key=lambda k: keys[k])]
    return [line[:3] for line in lines], boxes


def _depths(rings: list, probes: list) -> list[int]:
    """For each probe point, inside how many of the rings it lies (not counting its own)."""
    from ..fabrication import _inside
    boxes = [(r.min(axis=0), r.max(axis=0)) if r is not None else None for r in rings]
    out = []
    for k, p in enumerate(probes):
        count = 0
        if p is None:
            out.append(0)
            continue
        for m, (r, box) in enumerate(zip(rings, boxes)):
            if r is None or m == k or not ((box[0] <= p).all() and (p <= box[1]).all()):
                continue
            count += bool(_inside(p[None], r)[0])
        out.append(count)
    return out


def _per_sheet(lines, boxes):
    """The lines of each sheet, moved so the sheet starts at (0, 0); without sheets, all together from their corner."""
    if len(boxes) <= 1:
        if boxes:
            x0, y0, x1, y1 = boxes[0]
        else:
            every = np.vstack([p for _, p, _ in lines])
            (x0, y0), (x1, y1) = every.min(axis=0), every.max(axis=0)
        return [([(op, p - [x0, y0], c) for op, p, c in lines], (x1 - x0, y1 - y0))]
    sheets = []
    for x0, y0, x1, y1 in boxes:
        mine = []
        for op, p, c in lines:
            centre = (p.min(axis=0) + p.max(axis=0)) / 2
            if x0 - 1e-9 <= centre[0] <= x1 + 1e-9 and y0 - 1e-9 <= centre[1] <= y1 + 1e-9:
                mine.append((op, p - [x0, y0], c))
        sheets.append((mine, (x1 - x0, y1 - y0)))
    return sheets


def export_cutting(filepath, items: list[tuple[str, Data]], unit: str = "mm") -> list[Path]:
    """The cutting file(s), DXF or SVG by the extension of `filepath`; one per sheet if there are several. Returns
    the files written."""
    filepath = Path(filepath)
    kind = filepath.suffix.lower()
    if kind not in (".dxf", ".svg"):
        raise ShapeError(tr('A cutting file is DXF or SVG.'))
    if unit not in SCALE:
        raise ShapeError(tr("I don't know the unit “{unit}”. Options: {options}.").format(
            unit=unit, options=", ".join(SCALE)))
    lines, boxes = gather(items)
    sheets = _per_sheet(lines, boxes)
    written = []
    for k, (mine, size) in enumerate(sheets, start=1):
        target = filepath if len(sheets) == 1 else filepath.with_name(f"{filepath.stem}_{k}{filepath.suffix}")
        scale = SCALE[unit]
        if kind == ".svg":
            _svg(target, mine, size, scale, unit)
        else:
            _dxf(target, mine, size, scale, unit, with_sheet=bool(boxes))
        written.append(target)
    if len(sheets) > 1:                               # and one more with all of them, to check them at a glance
        every = np.asarray(boxes, float)
        x0, y0 = every[:, :2].min(axis=0)
        x1, y1 = every[:, 2:].max(axis=0)
        outlines = [] if any(op == "sheet" for op, _, _ in lines) else \
            [("sheet", np.array([[a, b], [c, b], [c, d], [a, d]]) - [x0, y0], True) for a, b, c, d in boxes]
        together = outlines + [(op, p - [x0, y0], c) for op, p, c in lines]
        target = filepath.with_name(f"{filepath.stem}_{ALL}{filepath.suffix}")
        if kind == ".svg":
            _svg(target, together, (x1 - x0, y1 - y0), SCALE[unit], unit, with_sheet=True)
        else:
            _dxf(target, together, (x1 - x0, y1 - y0), SCALE[unit], unit, with_sheet=False, sheet_off=False)
        written.append(target)
    return written


#: The end of the name of the file with all the sheets side by side (name_all.svg).
ALL = "all"


def _svg(path: Path, lines, size, scale: float, unit: str, with_sheet: bool = False) -> None:
    w, h = size[0] * scale, size[1] * scale
    groups = []
    # In the order they are done; the edges of the sheets, only in the file to look at (they are not cut).
    for operation in ("sheet", "engrave", "cut") if with_sheet else ("engrave", "cut"):
        colour = OPERATIONS[operation][0]
        shapes = []
        for op, p, closed in lines:
            if op != operation:
                continue
            q = p * scale
            points = " ".join(f"{x:.4f},{h - y:.4f}" for x, y in q)        # SVG: y downwards
            tag = "polygon" if closed else "polyline"
            shapes.append(f'<{tag} points="{points}"/>')
        if shapes:
            groups.append(f'<g id="{operation}" inkscape:groupmode="layer" inkscape:label={quoteattr(operation)} '
                          f'fill="none" stroke="{colour}" stroke-width="{0.1 * scale / 1000:.4g}">'
                          + "".join(shapes) + "</g>")
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{w:.4f}{unit}" height="{h:.4f}{unit}" viewBox="0 0 {w:.4f} {h:.4f}">'
        "<!-- Tensela: red, cut; blue, engrave. -->" + "".join(groups) + "</svg>\n", encoding="utf-8")


def _dxf(path: Path, lines, size, scale: float, unit: str, with_sheet: bool, sheet_off: bool = True) -> None:
    from .dxf import UNITS_DXF, _ezdxf
    ezdxf = _ezdxf()
    doc = ezdxf.new("R2010", units=UNITS_DXF[unit][1] if unit in UNITS_DXF else 4)
    doc.header["$MEASUREMENT"] = 0 if unit == "in" else 1
    msp = doc.modelspace()
    for operation, (_, number) in OPERATIONS.items():
        layer = doc.layers.add(operation)
        layer.color = number
    for op, p, closed in lines:
        msp.add_lwpolyline([(float(x), float(y)) for x, y in p * scale], close=closed, dxfattribs={"layer": op})
    if with_sheet:
        w, h = size[0] * scale, size[1] * scale
        msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True, dxfattribs={"layer": "sheet"})
    if sheet_off:
        doc.layers.get("sheet").off()
    doc.saveas(path)
