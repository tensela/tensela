"""Export for a 3D printer: STL and 3MF. Both keep Z up, as the engine and the printers do.

- **STL** (binary): the one every slicer reads. Only triangles: it does not say its unit (by custom, millimetres),
  and all the pieces go in one solid.
- **3MF**: the modern one. It says its unit, so the piece arrives at its size; each visible node is an object of its
  own, with its name and its colour.

Each element is welded before writing (printing.pieces), so the file has shared vertices, as a printer expects.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from ..data import Data, ShapeError
from ..language import tr
from ..printing import pieces

#: Metres → the unit of the file. 3MF names them; STL does not, so millimetres is the one to use.
SCALE = {"mm": 1000.0, "cm": 100.0, "m": 1.0, "in": 1 / 0.0254}
UNITS_3MF = {"mm": "millimeter", "cm": "centimeter", "m": "meter", "in": "inch"}


def _named_pieces(data_items) -> list[tuple[str, list]]:
    if not data_items:
        raise ShapeError(tr('There is nothing to export.'))
    result = []
    for k, data in enumerate(data_items, start=1):
        result.append((data._name(f"object {k}"), pieces(data)))
    if not any(p for _, p in result):
        raise ShapeError(tr('There is nothing to export: no visible node has faces.'))
    return result


def export_stl(filepath, *data_items: Data, unit: str = "mm") -> Path:
    """All the faces of the visible nodes in one binary STL, in `unit` (millimetres unless asked otherwise)."""
    scale = _scale(unit)
    triangles = []
    for _, items in _named_pieces(data_items):
        for piece in items:
            triangles.append(piece.vertices[piece.triangles] * scale)
    t = np.concatenate(triangles) if triangles else np.zeros((0, 3, 3))
    normals = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, length, out=np.zeros_like(normals), where=length > 0)
    record = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    body = np.zeros(len(t), dtype=record)
    body["normal"] = normals
    body["vertices"] = t
    header = f"Tensela STL, unit: {unit}".encode("ascii")[:80].ljust(80, b" ")
    filepath = Path(filepath)
    with open(filepath, "wb") as f:
        f.write(header)
        f.write(np.uint32(len(t)).tobytes())
        f.write(body.tobytes())
    return filepath


def export_3mf(filepath, *data_items: Data, unit: str = "mm", colours: dict[str, str] | None = None) -> Path:
    """Each visible node as an object of a 3MF file (with its name and colour), in `unit`; its elements, as the
    pieces of that object."""
    scale = _scale(unit)
    colours = colours or {}
    named = [(name, items) for name, items in _named_pieces(data_items) if items]
    materials = "".join(f'<base name={quoteattr(name)} displaycolor="{_colour(colours.get(name))}"/>'
                        for name, _ in named)
    objects, build = [], []
    next_id = 2
    for k, (name, items) in enumerate(named):
        for j, piece in enumerate(items):
            v = piece.vertices * scale
            vertices = "".join(f'<vertex x="{x:.6g}" y="{y:.6g}" z="{z:.6g}"/>' for x, y, z in v)
            faces = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in piece.triangles)
            label = name if len(items) == 1 else f"{name} ({piece.label or j + 1})"
            objects.append(f'<object id="{next_id}" type="model" name={quoteattr(label)} pid="1" pindex="{k}">'
                           f'<mesh><vertices>{vertices}</vertices><triangles>{faces}</triangles></mesh></object>')
            build.append(f'<item objectid="{next_id}"/>')
            next_id += 1
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<model unit="{UNITS_3MF[unit]}" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<metadata name="Application">{escape("Tensela")}</metadata>'
             f'<resources><basematerials id="1">{materials}</basematerials>{"".join(objects)}</resources>'
             f'<build>{"".join(build)}</build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    filepath = Path(filepath)
    with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
    return filepath


def _scale(unit: str) -> float:
    if unit not in SCALE:
        raise ShapeError(tr("I don't know the unit “{unit}”. Options: {options}.").format(
            unit=unit, options=", ".join(SCALE)))
    return SCALE[unit]


def _colour(colour: str | None) -> str:
    colour = (colour or "#b8b8b8").strip()
    return colour.upper() if colour.startswith("#") and len(colour) == 7 else "#B8B8B8"
