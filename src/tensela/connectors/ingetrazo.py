"""IngeTrazo (Delivery 4, step 4): Marco Sumari's free modeller.

Tensela writes IngeTrazo's own format directly (`.igz`, plain JSON, format 1), which IngeTrazo opens like any of
its documents. Both applications work the same way: **metres, Z up, Y north**, so there is no conversion at all.

What reaches IngeTrazo:

- each visible node is a **group** with its name, in a **layer** with its colour and with a **material** with its
  name (to paint or measure m² later);
- inside, each piece is a **group** of its own («sun fins · row 6, column 4»), which is picked and moved on its own;
- the curves, as edges that IngeTrazo recognises as a single curve;
- the points, as **guide points**.

It opens no connection: it writes a file and, if asked, launches the installed IngeTrazo with that file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..data import Data, ShapeError
from ..language import tr
from ..geometry import real_faces

USUAL_PLACES = ("~/AppImages/ingetrazo.appimage", "~/Applications/ingetrazo.appimage",
                      "~/.local/bin/ingetrazo", "/usr/bin/ingetrazo", "/usr/local/bin/ingetrazo")


def find_ingetrazo(preferred: str | None = None) -> str:
    """The path of IngeTrazo: the one given, the variable TENSELA_INGETRAZO, the system's or a usual place."""
    for candidate in (preferred, os.environ.get("TENSELA_INGETRAZO"), shutil.which("ingetrazo"),
                      *USUAL_PLACES):
        if candidate and Path(os.path.expanduser(candidate)).is_file():
            return str(Path(os.path.expanduser(candidate)))
    raise ShapeError(tr("I can't find IngeTrazo on this computer. Say where it is with the variable "
                          "TENSELA_INGETRAZO, or save an .igz and open it from IngeTrazo."))


def _rgb(color: str) -> list[float]:
    h = color.lstrip("#")
    return [round(int(h[k:k + 2], 16) / 255, 4) for k in (0, 2, 4)]


def _place(data: Data, pos: tuple[int, ...]) -> str:
    """row 6, column 4 (with the numbering the user sees)."""
    return ", ".join(f"{n} {p + data.starts.get(n, 0)}" for n, p in zip(data.levels, pos))


def _with_area(vertices: np.ndarray, faces) -> np.ndarray:
    """Which faces have an area, in all the pieces at once (pieces × faces).

    Those that do not (a panel of width 0) are skipped: IngeTrazo does not accept them.
    """
    valid = np.empty((len(vertices), len(faces)), dtype=bool)
    for k, face in enumerate(faces):
        points = vertices[:, list(face)]
        centre = points.mean(axis=1, keepdims=True)
        normal = np.cross(points - centre, np.roll(points, -1, axis=1) - centre).sum(axis=1)
        valid[:, k] = np.linalg.norm(normal, axis=-1) > 1e-12
    return valid


def document_igz(objects: list[tuple[str, Data, dict]], project: str = "Tensela") -> dict:
    """The IngeTrazo document (format 1) with the geometries.

    `objects`: (name, data, style), as `Project.visible_objects()`.
    """
    if not objects:
        raise ShapeError(tr("There is nothing to take to IngeTrazo."))
    groups, layers, materials, guides = [], [{"name": "Layer 0"}], [], []
    curve = 1  # each curve, a number of its own: so IngeTrazo treats it as a single one
    for name, data, style_name in objects:
        if data.kind is None:
            raise ShapeError(tr("“{name}” is not a geometry: it cannot be taken to IngeTrazo.").format(name=name))
        color = _rgb(style_name.get("color", "#8a96a3"))
        opacity = float(style_name.get("opacity", 1.0))
        layer = {"name": name, "color": color}
        material = {"name": name, "color": color}
        painting = {"color": [*color, 1.0], "mat": name}
        if opacity < 1.0:
            layer["opacity"] = material["opacity"] = painting["opacity"] = round(opacity, 3)
        layers.append(layer)
        materials.append(material)

        positions = [tuple(int(p) for p in pos) for pos in np.argwhere(data.mask)] if data.levels else [()]
        if data.kind.faces is None and not data.kind.curve:              # points: guide points
            for pos in positions:
                guides.append({"point": data.values[pos].tolist(), "layer": name})
            continue

        all_ = data.values[data.mask] if data.levels else data.values[None]
        if not np.isfinite(all_).all():
            raise ShapeError(tr("“{name}” has coordinates that are not numbers (a division by zero, perhaps): "
                                  "IngeTrazo could not open the document.").format(name=name))
        if data.kind.faces is not None:
            valid = _with_area(all_, data.kind.faces)
            indices = [list(c) for c in data.kind.faces]
        pieces = []
        for i, pos in enumerate(positions):
            v = all_[i]
            if data.kind.curve:
                order = list(range(len(v))) + ([0] if data.kind.closed else [])
                body = {"edges": [{"a": v[a].tolist(), "b": v[b].tolist(), "curve": curve, "layer": name}
                                    for a, b in zip(order, order[1:])], "faces": []}
                curve += 1
            elif data.kind.polygon:                                    # polygons: without the padding
                list_ = v.tolist()
                body = {"edges": [], "faces": [{"vertices": [list_[j] for j in c], **painting}
                                                 for c in real_faces(data.kind, v)]}
            else:
                list_ = v.tolist()
                body = {"edges": [], "faces": [{"vertices": [list_[j] for j in c], **painting}
                                                 for c, ok in zip(indices, valid[i]) if ok]}
            title = f"{name} · {_place(data, pos)}" if pos else name
            pieces.append({"name": title, "layer": name, "component": False, **body})
        if len(pieces) == 1 and not data.levels:
            groups.append(pieces[0])                                     # a single piece: one group
        else:
            groups.append({"name": name, "layer": name, "component": False,
                           "edges": [], "faces": [], "children": pieces})

    graph_scene = {"edges": [], "faces": [], "groups": groups, "layers": layers, "materials": materials,
              "plugin_data": {"tensela": {"proyecto": project}}}
    if guides:
        graph_scene["guides"] = guides
    return {"igz_format": 1, "app_version": "tensela", "scene": graph_scene}


def export_igz(filepath, objects: list[tuple[str, Data, dict]], project: str = "Tensela") -> Path:
    """Saves an IngeTrazo document (.igz)."""
    document = document_igz(objects, project)
    _without_infinite(document)
    filepath = Path(filepath)
    filepath.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return filepath


def _without_infinite(document: dict) -> None:
    """A NaN or an infinity would break the document: it is reported before writing."""
    try:
        json.dumps(document, allow_nan=False)
    except ValueError:
        raise ShapeError(tr("There are coordinates that are not numbers (a division by zero, perhaps): "
                              "IngeTrazo could not open the document.")) from None


def open_in_ingetrazo(objects: list[tuple[str, Data, dict]], project: str = "Tensela",
                       ingetrazo: str | None = None) -> Path:
    """Opens IngeTrazo with the scene. The document stays in a temporary folder:
    to keep it, it is saved from IngeTrazo (Save as…)."""
    program = find_ingetrazo(ingetrazo)
    folder = Path(tempfile.mkdtemp(prefix="tensela-ingetrazo-"))  # only the user reads it
    filepath = export_igz(folder / f"{project}.igz", objects, project)
    subprocess.Popen([program, str(filepath)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return filepath

