"""Blender, directly (Delivery 4, step 1).

Tensela does not write the .blend format (it is internal to Blender and changes between versions): **it asks
Blender to build the scene**. The data go to a temporary file (NumPy, no code) and a script of our own, run inside
Blender, creates one object per node with its name and its material, in metres and with Z up (the same coordinates
as the engine: without the 90° turn the OBJ importer adds).

    export_blend("facade.blend", objects)    # Blender without a window saves the file
    open_in_blender(objects)                 # Blender opens with the scene built

It opens no connection or port: it only launches the installed Blender program.
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

USUAL_PLACES = ("~/.local/bin/blender", "/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender")


def find_blender(preferred: str | None = None) -> str:
    """The path of the Blender program: the one given, the system's or one of the usual places."""
    for candidate in (preferred, os.environ.get("TENSELA_BLENDER"), shutil.which("blender"),
                      *USUAL_PLACES):
        if candidate and Path(os.path.expanduser(candidate)).is_file():
            return str(Path(os.path.expanduser(candidate)))
    raise ShapeError(tr("I can't find Blender on this computer. Install it (blender.org) or say where it is with "
                          "the variable TENSELA_BLENDER."))


def prepare(objects: list[tuple[str, Data, dict]], folder, project: str = "Tensela") -> Path:
    """Writes the data the Blender script needs: vertices, faces, lines and colours.

    `objects`: (name, data, style) for each visible node; `style` may have «color» («#rrggbb») and «opacity».
    """
    arrays: dict[str, np.ndarray] = {}
    meta = {"project": project, "objects": []}
    for i, (name, data, style_name) in enumerate(objects):
        if data.kind is None:
            raise ShapeError(tr("“{name}” is not a geometry: it cannot be taken to Blender.").format(name=name))
        vertices = data.values[data.mask] if data.levels else data.values[None]
        if data.kind.faces is None and not data.kind.curve:            # puntos
            arrays[f"v{i}"] = vertices.reshape(-1, 3).astype(np.float64)
            class_ = "points"
        else:
            elements, by_element = vertices.shape[0], vertices.shape[1]
            arrays[f"v{i}"] = vertices.reshape(-1, 3).astype(np.float64)
            base = (np.arange(elements) * by_element)[:, None]
            if data.kind.curve:
                pairs = np.stack([np.arange(by_element - 1), np.arange(1, by_element)], axis=-1)
                if data.kind.closed:
                    pairs = np.vstack([pairs, [[by_element - 1, 0]]])
                arrays[f"l{i}"] = (base[:, None, :] + pairs[None]).reshape(-1, 2).astype(np.int32)
                class_ = "curve"
            elif data.kind.polygon:                                    # polygons: each element, its faces
                own = [(e * by_element, c) for e in range(elements)
                           for c in real_faces(data.kind, vertices[e])]
                arrays[f"t{i}"] = np.array([len(c) for _, c in own], dtype=np.int32)
                arrays[f"c{i}"] = np.array([b + j for b, c in own for j in c], dtype=np.int32)
                class_ = "mesh"
            else:
                size = np.array([len(c) for c in data.kind.faces], dtype=np.int32)
                plane = np.concatenate([np.array(c) for c in data.kind.faces]).astype(np.int32)
                arrays[f"t{i}"] = np.tile(size, elements)
                arrays[f"c{i}"] = (base + plane[None, :]).reshape(-1).astype(np.int32)
                class_ = "mesh"
        meta["objects"].append({
            "name": name, "class": class_,
            "color": style_name.get("color", "#8a96a3"), "opacity": float(style_name.get("opacity", 1.0)),
        })
    arrays["meta"] = np.array(json.dumps(meta, ensure_ascii=False))
    filepath = Path(folder) / "escena.npz"
    np.savez_compressed(filepath, **arrays)
    return filepath


def _temporary_folder() -> Path:
    return Path(tempfile.mkdtemp(prefix="tensela-blender-"))  # only the user reads it (mode 700)


def _script(folder: Path) -> Path:
    filepath = folder / "armar_escena.py"
    filepath.write_text(SCRIPT_BLENDER, encoding="utf-8")
    return filepath


def export_blend(filepath, objects: list[tuple[str, Data, dict]], project: str = "Tensela",
                   blender: str | None = None, wait: float = 300) -> Path:
    """Saves a .blend with the scene built (Blender without a window)."""
    program = find_blender(blender)
    folder = _temporary_folder()
    data_items = prepare(objects, folder, project)
    filepath = Path(filepath).resolve()
    result = subprocess.run(
        [program, "-b", "--factory-startup", "--python", str(_script(folder)), "--", str(data_items), str(filepath)],
        capture_output=True, text=True, timeout=wait,
    )
    shutil.rmtree(folder, ignore_errors=True)
    if result.returncode != 0 or not filepath.exists():
        last = "\n".join((result.stdout + result.stderr).strip().splitlines()[-5:])
        raise ShapeError(tr("Blender could not save “{name}”.").format(name=filepath.name) + f"\n{last}")
    return filepath


def open_in_blender(objects: list[tuple[str, Data, dict]], project: str = "Tensela",
                     blender: str | None = None) -> subprocess.Popen:
    """Opens Blender with the scene built (saving nothing: it is saved from Blender)."""
    program = find_blender(blender)
    folder = _temporary_folder()
    data_items = prepare(objects, folder, project)
    return subprocess.Popen([program, "--python", str(_script(folder)), "--", str(data_items)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


# The script that runs inside Blender. It only reads the data file (without
# running anything from it) and builds the scene.
SCRIPT_BLENDER = r'''
import json
import sys

import bpy
import numpy as np

arguments = sys.argv[sys.argv.index("--") + 1:]
data_file, output = arguments[0], (arguments[1] if len(arguments) > 1 else None)
z = np.load(data_file, allow_pickle=False)
meta = json.loads(str(z["meta"]))


def linear(c):  # from sRGB (what the window shows) to linear (what Blender uses)
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# Una scene limpia: sin el cubo, la cámara y la luz de inicio.
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "METERS"
collection = bpy.data.collections.new(meta["project"])
scene.collection.children.link(collection)

for i, o in enumerate(meta["objects"]):
    v = z[f"v{i}"]
    edges, faces = [], []
    if o["class"] == "mesh":
        faces = [c.tolist() for c in np.split(z[f"c{i}"], np.cumsum(z[f"t{i}"])[:-1])]
    elif o["class"] == "curve":
        edges = z[f"l{i}"].tolist()
    mesh = bpy.data.meshes.new(o["name"])
    mesh.from_pydata(v.tolist(), edges, faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(o["name"], mesh)
    collection.objects.link(obj)

    h = o["color"].lstrip("#")
    r, g, b = (linear(int(h[k:k + 2], 16)) for k in (0, 2, 4))
    a = o["opacity"]
    material = bpy.data.materials.new(o["name"])
    material.diffuse_color = (r, g, b, a)            # the colour in the «solid» view
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Alpha"].default_value = a
    if a < 1.0:
        for attribute, value in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            if hasattr(material, attribute):
                try:
                    setattr(material, attribute, value)
                except TypeError:
                    pass
    mesh.materials.append(material)

if output:
    bpy.ops.wm.save_as_mainfile(filepath=output)
else:
    def frame_all():
        # En la ventana: ver los colores de los nodos y frame_all todo.
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            space.shading.color_type = "MATERIAL"
                    region = next((r for r in area.regions if r.type == "WINDOW"), None)
                    if region is not None:
                        with bpy.context.temp_override(area=area, region=region):
                            bpy.ops.view3d.view_all()
        return None

    bpy.app.timers.register(frame_all, first_interval=0.5)
'''
