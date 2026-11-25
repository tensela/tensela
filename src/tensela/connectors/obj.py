"""Export to OBJ (step 1.3): the simplest connector; any 3D program opens it.

The engine works with Z up; OBJ uses Y up. On writing, (x, y, z) → (x, z, -y), so Blender and the others import it
upright with their default options.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..data import Data, ShapeError
from ..language import tr
from ..geometry import real_faces

UNITS = {"m": 1.0, "cm": 100.0, "mm": 1000.0, "in": 1 / 0.0254, "ft": 1 / 0.3048}  # feet and inches: 1" = 25.4 mm


def export_obj(filepath, *data_items: Data, unit: str = "m", by_element: bool = False) -> Path:
    """Writes one or more geometric data in an OBJ file.

    Each data is an object of the file, with its name. With `by_element`, each element is also a group with its place in
    the levels (`sun_fins_row6_column4`), so it can be picked on its own in the destination. Only the elements that exist
    are exported (not the padding of the variable levels).
    """
    if unit not in UNITS:
        raise ShapeError(tr("I don't know the unit “{unit}”. Options: {options}.").format(
            unit=unit, options=", ".join(UNITS)))
    scale = UNITS[unit]
    if not data_items:
        raise ShapeError(tr("There is nothing to export."))

    lines = [f"# Tensela. Unit: {unit}. Y axis up (OBJ convention)."]
    next_ = 1  # OBJ numbers the vertices from 1
    for k, data in enumerate(data_items, start=1):
        if data.kind is None or (data.kind.faces is None and not data.kind.curve):
            what = tr("“{kind}”").format(kind=tr(data.kind.name)) if data.kind is not None else tr("a number")
            raise ShapeError(tr("“{name}” cannot be exported to OBJ: it is {what}, not a geometry with faces nor a "
                                "curve.").format(name=data._name(), what=what))
        name = _clean(data._name(f"objeto {k}"))
        lines.append(f"o {name}")

        vertices = data.values * scale
        by_element_vertices = vertices.shape[-2]
        for pos in np.argwhere(data.mask) if data.levels else [()]:
            pos = tuple(int(p) for p in pos)
            if by_element and data.levels:
                lines.append(f"g {name}_{_label(data, pos)}")
            for x, y, z in vertices[pos]:
                lines.append(f"v {_n(x)} {_n(z)} {_n(-y)}")
            if data.kind.curve:  # a curve is an OBJ line («l»)
                order = list(range(by_element_vertices)) + ([0] if data.kind.closed else [])
                lines.append("l " + " ".join(str(next_ + i) for i in order))
            else:
                for face in real_faces(data.kind, data.values[pos]):     # without the padding of the polygons
                    lines.append("f " + " ".join(str(next_ + i) for i in face))
            next_ += by_element_vertices

    filepath = Path(filepath)
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return filepath


def _label(data: Data, pos: tuple[int, ...]) -> str:
    """row 6, column 4 → 'row6_column4' (with the numbering the user sees)."""
    return "_".join(
        f"{_clean(n)}{p + data.starts.get(n, 0)}" for n, p in zip(data.levels, pos)
    )


def _clean(text: str) -> str:
    """OBJ names have no spaces."""
    return "_".join(text.split())


def _n(x: float) -> str:
    """Six decimals, without '-0.000000'."""
    return f"{round(float(x), 6) + 0.0:.6f}"
