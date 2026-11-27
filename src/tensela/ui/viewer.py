"""The 3D view (D9).

It is the only piece that knows about VTK/pyvista: the rest of the interface talks to `Viewer` (display, clear,
frame, save_image). If VTK gave problems, this file is changed and nothing else.

`image()` draws the same without a window (for the `tensela --png` command).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv

# An empty geometry (a Filter that left nothing) is not seen, but it is not an error: the view goes on.
pv.global_theme.allow_empty_mesh = True
import vtk
from pyvistaqt import QtInteractor
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..language import comma, tr
from ..data import Data, ShapeError
from .drawing import Drafter
from .drawing import BarDrawing, StripNodes
from .navigation import Browser
from . import studio

# VTK warnings without consequences on Wayland ("Failed to get red color buffer
# size"): they tell the user nothing and fill the terminal.
vtk.vtkObject.GlobalWarningDisplayOff()

# Two surfaces on the same plane (a facade and its grid) must not
# "fight" pixel by pixel (z-fighting): each object comes forward a little by
# the order in which it is shown, and the same one always wins.
vtk.vtkMapper.SetResolveCoincidentTopologyToPolygonOffset()

COLOR_DEPTH = "#eef0f2"
COLOR_GEOMETRY = "#8a96a3"


def to_mesh(data: Data) -> pv.PolyData:
    """Turns a geometric data with faces into a pyvista mesh.

    Only the elements that exist go in (not the padding of the variable levels). Units: the engine's (metres).
    """
    if data.kind is None:
        raise ShapeError(tr("“{name}” cannot be shown in 3D: it is a number, not a geometry.").format(name=data._name()))
    vertices = data.values[data.mask] if data.levels else data.values[None]
    vertices = np.asarray(vertices, dtype=float)         # some points with integer coordinates, too
    if data.kind.faces is None and not data.kind.curve:  # puntos
        return pv.PolyData(vertices.reshape(-1, 3))
    elements, by_element = vertices.shape[0], vertices.shape[1]
    if data.kind.curve:  # each curve, a polyline (closed if it has to be)
        indices = np.arange(elements * by_element).reshape(elements, by_element)
        if data.kind.closed:
            indices = np.concatenate([indices, indices[:, :1]], axis=1)
        lines = np.concatenate([np.full((elements, 1), indices.shape[1]), indices], axis=1)
        return pv.PolyData(vertices.reshape(-1, 3), lines=lines.ravel())

    from ..geometry import real_faces
    if not data.kind.polygon and data.kind.faces:  # the same faces in all: at once, without loops
        cells = []
        lengths = sorted({len(c) for c in data.kind.faces})
        for k in lengths:
            group = np.array([c for c in data.kind.faces if len(c) == k], dtype=np.int64)       # (F, k)
            indices = group[None] + (np.arange(elements) * by_element)[:, None, None]       # (E, F, k)
            cells.append(np.concatenate([np.full(indices.shape[:2] + (1,), k), indices], axis=2).ravel())
        return pv.PolyData(vertices.reshape(-1, 3), np.concatenate(cells))
    faces = []
    for i in range(elements):
        base = i * by_element
        for face in (real_faces(data.kind, vertices[i]) if data.kind.polygon else data.kind.faces):
            faces.append([len(face), *(base + j for j in face)])
    if not faces:
        return pv.PolyData(vertices.reshape(-1, 3))
    return pv.PolyData(vertices.reshape(-1, 3), np.concatenate(faces))


#: Past this, the view asks before drawing a node (a digit too many in a count: 12 bars × 8760 hours gave 105 000
#: boxes): how many pieces, and how many points in all (a single mesh can be huge too). With 100 000 boxes the view
#: still turns, but slowly; with a million it stops.
#: The letter of the name of the view («Front · Parallel»): the monospace of the window, small, like a label.
VIEW_NAME_FONT = Path(__file__).resolve().parent / "fonts" / "jetbrainsmono" / "JetBrainsMono-Regular.ttf"
MANY_PIECES = 50_000
MANY_POINTS = 2_000_000


def amount(data: Data) -> tuple[int, int]:
    """How many pieces a geometry has and how many points they add up to (what the view has to draw)."""
    if data is None or data.kind is None:
        return 0, 0
    values = np.asarray(data.values)
    if not data.levels:
        return 1, int(np.prod(values.shape[:-1], dtype=np.int64))
    pieces = int(np.count_nonzero(data.mask))
    return pieces, pieces * int(np.prod(values.shape[np.ndim(data.mask):-1], dtype=np.int64))


def heaviness(data: Data) -> float:
    """How far a geometry goes past what the view draws without asking: 1, just at the limit."""
    pieces, points = amount(data)
    return max(pieces / MANY_PIECES, points / MANY_POINTS)


#: The gradients to paint by a value (the *Gradient*): from the smallest value to the largest.
GRADIENTS = {
    "light to dark": ("#f4f3ef", "#1d1d20"),
    "cool to warm": ("#3b6fb6", "#f2f0ea", "#c8423b"),
    "sun": ("#2b1b4a", "#a3305a", "#f08a3c", "#f9e58a"),
    "foliage": ("#f3e9a6", "#6fb36b", "#1f5f6b"),
}


def colours_table(gradient: str) -> pv.LookupTable:
    """The 256 colours of a gradient, for pyvista (without depending on matplotlib)."""
    stops = GRADIENTS.get(gradient, GRADIENTS["cool to warm"])
    rgb = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in stops], dtype=float)
    t = np.linspace(0, 1, 256)
    places = np.linspace(0, 1, len(stops))
    colours = np.stack([np.interp(t, places, rgb[:, k]) for k in range(3)] + [np.full(256, 255.0)], axis=1)
    table = pv.LookupTable()
    table.values = colours.astype(np.uint8)
    return table


def smooth_edges(plotter, kind: str) -> None:
    """The smoothing of the edges: «fxaa» (light, on the finished image) or «ssaa» (the image drawn larger). FXAA goes
    straight to VTK: pyvista takes VTK on Windows for a build without windows (EGL, as it has no X11 window) and
    changes FXAA for SSAA, which breaks drawing with Mesa (llvmpipe)."""
    if kind == "fxaa":
        for renderer in plotter.renderers:
            renderer.SetUseFXAA(True)
            renderer.Modified()
    else:
        plotter.enable_anti_aliasing(kind)


def prepare(plotter: pv.Plotter, axes: bool = True) -> None:
    """Background, axes and lights: a sun from front-left-above and a soft light from the camera.

    So each face of a block has a different tone and the depth reads.
    """
    plotter.set_background(COLOR_DEPTH)
    smooth_edges(plotter, "fxaa")
    if axes:
        plotter.add_axes(interactive=False, line_width=2, labels_off=False)
    studio.put_sky(plotter)
    light_up(plotter, style="solid")


#: What the OpenGL renderer says when there is no graphics card doing the work: the processor draws each image.
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swrast", "swiftshader", "software rasterizer", "gdi generic")


def software_rendering(render_window) -> bool | None:
    """Whether the images are drawn by the processor (Mesa's llvmpipe and the like) instead of a graphics card. None
    until the window has drawn once and can say it."""
    try:
        report = render_window.ReportCapabilities() or ""
    except Exception:                                  # noqa: BLE001: without an answer, as if not known yet
        return None
    for line in report.splitlines():
        if "renderer string" in line.lower():
            name = line.split(":", 1)[-1].strip().lower()
            return any(word in name for word in SOFTWARE_RENDERERS)
    return None


def light_up(plotter: pv.Plotter, with_camera: bool = False, style: str | None = None) -> None:
    """The sun and the camera's light (also after clearing the scene, which takes them away).

    `with_camera` (occlusion): the sun goes with the camera, up to the left of the viewer, so that what is seen is
    never against the light, and a fill light.
    """
    if style in ("solid", "model"):                  # Studio and Model: key, fill, back, bounce (ui/studio.py)
        studio.put_lights(plotter, style)
        return
    plotter.remove_all_lights()
    if with_camera:
        sun = pv.Light(light_type="camera light", intensity=1.0)
        sun.position, sun.focal_point = (-0.8, 1.2, 1.0), (0, 0, 0)
        sun.positional = False
        sun.shadow_attenuation = 0.6
        plotter.add_light(sun)
        padding = pv.Light(light_type="camera light", intensity=0.45)
        padding.position, padding.focal_point = (0.6, -0.3, 1.0), (0, 0, 0)
        padding.positional = False
        padding.shadow_attenuation = 0.0
        plotter.add_light(padding)
        return
    sun = pv.Light(light_type="scene light", intensity=0.75)
    sun.position, sun.focal_point = (-0.6, -1.0, 1.3), (0, 0, 0)
    sun.positional = False
    plotter.add_light(sun)
    plotter.add_light(pv.Light(light_type="headlight", intensity=0.45))


#: The styles of the 3D view (Delivery 5): how each object is painted, and whether the scene carries shadows or occlusion.
STYLE_NAMES = {"solid": 'Studio', "model": 'Model', "matcap": "Matcap", "wireframe": 'Wireframe', "hidden lines": 'Hidden lines',
           "x-ray": 'X-ray', "occlusion": 'Ambient occlusion'}

#: The material of the Matcap style (View → Matcap): plaster, clay, graphite or ceramic (ui/matcaps.py).
MATCAP = {"name": "plaster"}
HELP_TEXTS_STYLE_NAME = {
    "solid": 'Each object with its colour, lit like in a studio: soft light, darker corners and thin outlines',
    "model": 'Everything white, with outlines: like a foam board model, to see the form. On its light paper, or on '
             'the background chosen in View → Background',
    "matcap": 'Each face takes the light of a material (plaster, clay, graphite, ceramic) according to where it '
              'faces; parts close together, like ribs, read one by one',
    "wireframe": 'Only the edges: you see through',
    "hidden lines": 'Like a line drawing: faces the colour of the paper, with their edges; what is behind is hidden',
    "x-ray": 'Everything semi-transparent: what is inside and behind, in view',
    "occlusion": 'Solid, with corners and junctions darker (like the light of an overcast day)',
}


def _arrows(data: Data) -> pv.PolyData | None:
    """A vector (from the origin) or an arrow (from its point), as solid arrows: the shaft and the tip."""
    v = np.asarray(data.values[data.mask] if data.levels else data.values[None], dtype=float)
    if data.kind.name == "vector":
        starts, directions = np.zeros_like(v.reshape(-1, 3)), v.reshape(-1, 3)
    else:
        v = v.reshape(-1, 2, 3)
        starts, directions = v[:, 0], v[:, 1] - v[:, 0]
    lengths = np.linalg.norm(directions, axis=1)
    valid = lengths > 1e-12
    if not valid.any():
        return None
    cloud = pv.PolyData(starts[valid])
    cloud["direction"] = directions[valid]
    cloud["length"] = lengths[valid]
    tip = pv.Arrow(start=(0, 0, 0), direction=(1, 0, 0), tip_length=0.18, tip_radius=0.045, shaft_radius=0.012,
                     scale=1.0)
    return cloud.glyph(orient="direction", scale="length", factor=1.0, geom=tip)


def draw(plotter: pv.Plotter, name: str, data: Data, color: str = COLOR_GEOMETRY, opacity: float = 1.0,
            edges: bool | None = None, order: int = 0, style_name_view: str = "solid",
            paper: str = "#ffffff", ink: str = "#20222a", colour_by: tuple | None = None, analyse: str | None = None,
            outlines: bool = True):
    """Adds the geometry `name` to the scene and returns its actor. `outlines`: in Studio and Model, the thin lines
    at the edges (View → Outlines).

    Without explicit `edges`, the outline of the rectangles is drawn when there are many (a grid of panels): so the grid
    reads. `order` brings each object forward a little so that two surfaces on the same plane do not fight.

    `colour_by`: (a number per element, the name of a gradient): each element with the colour of its value, and the
    legend at one side.
    """
    if edges is None:
        # The outline of each cell when there are many (a grid of panels, a honeycomb): so the grid reads.
        edges = data.kind is not None and data.kind.name in ("rectangle", "polygon") and bool(data.levels)
    if data.kind is not None and data.kind.name in ("vector", "arrow"):
        mesh = _arrows(data)
        if mesh is not None:
            actor = plotter.add_mesh(mesh, color=color, opacity=opacity, name=name, reset_camera=False,
                                     smooth_shading=True)
            return actor
    mesh = to_mesh(data)
    paint = {}
    if colour_by is not None and style_name_view != "hidden lines" and mesh.n_points:
        numbers, gradient = colour_by
        numbers = np.asarray(numbers, dtype=float)
        if len(numbers) and mesh.n_points % len(numbers) == 0:      # (before the normals: they are copied with them)
            mesh.point_data["value"] = np.repeat(numbers, mesh.n_points // len(numbers))
            range_ = (float(numbers.min()), float(numbers.max()))
            if range_[1] - range_[0] < 1e-12:            # all the same: that value, at the start of the gradient
                range_ = (range_[0], range_[0] + max(abs(range_[0]) * 1e-6, 1e-9))
            table = colours_table(gradient)
            table.scalar_range = range_                  # the table rules over clim: if not, it would go from 0 to 1
            paint = dict(scalars="value", cmap=table, clim=range_, show_scalar_bar=False)
    if data.kind.curve:
        style_name = dict(line_width=3, render_lines_as_tubes=False)
    elif data.kind.faces is None:  # puntos: esferitas
        style_name = dict(point_size=11, render_points_as_spheres=True)
    elif style_name_view == "wireframe":
        style_name = dict(style="wireframe", line_width=1)
    elif style_name_view == "hidden lines":                 # a drawing: paper with its edges, without light
        # A shadow stays a shadow: grey, as in a drawing; everything else, the colour of the paper.
        color, opacity = ("#9a9a9a" if getattr(data, "shade", False) else paper), 1.0
        style_name = dict(show_edges=True, edge_color=ink, line_width=1, ambient=1.0, diffuse=0.0, specular=0.0)
    else:
        smooth_curve = data.kind.grid is not None or data.kind.name == "mesh"  # surface or mesh: smooth
        if data.kind.name == "mesh" and mesh.n_cells:
            # Smooth where the mesh is curved (tubes, spheres) and with sharp edges where it breaks more than 30°
            # (a box, a wall with openings): the normals split at those edges.
            mesh = mesh.compute_normals(split_vertices=True, feature_angle=30, auto_orient_normals=False,
                                          consistent_normals=False)
        stitched = data.kind.grid is not None and mesh.n_cells and style_name_view not in ("matcap",)
        if stitched:                                     # smooth shading without a streak at the seam (own normals)
            mesh = _stitched_normals(mesh)
        style_name = dict(show_edges=edges, edge_color="#5a5f66", line_width=1.5 if edges else 1,
                          smooth_shading=smooth_curve and not stitched,
                          ambient=0.25, diffuse=0.8, specular=0.1 if smooth_curve else 0.05)
        if style_name_view in ("solid", "model"):     # Studio and Model (ui/studio.py): the outlines draw the edges
            # A small mesh shows every edge (its topology: the diagonal of each triangle too), in the outlines'
            # grey; a big one (a welded skin, a smoothed mesh), only its outlines: so many lines would hide the form.
            # Boards (Sections, Bevel): their triangles say nothing of the form, only their outlines.
            mesh_edges = outlines and data.kind.name == "mesh" and len(data.kind.faces) <= studio.MESH_EDGES_LIMIT \
                and getattr(data, "topology", True)
            style_name = dict(show_edges=mesh_edges, edge_color=studio.OUTLINE_DARK, line_width=1,
                              smooth_shading=smooth_curve and not stitched, **studio.material(style_name_view))
            if style_name_view == "model" and not getattr(data, "shade", False):   # a shadow keeps its tone
                color = studio.MODEL_COLOUR
        if style_name_view == "matcap" and mesh.n_cells:
            mesh = _for_matcap(mesh, smooth_curve)
            style_name.update(smooth_shading=False, texture=_texture_matcap(MATCAP["name"]), ambient=0.0, diffuse=1.0,
                          specular=0.0)
        if style_name_view == "x-ray":
            opacity = min(opacity, 0.25)
    analyse = OLD_ANALYSIS.get(analyse, analyse)
    analysis = analyse in ("gaussian", "mean", "zebra") and data.kind.faces is not None and not data.kind.curve \
        and style_name_view not in ("hidden lines", "wireframe") and mesh.n_cells
    if analysis and analyse == "zebra":               # the zebra, in the shader: pixel by pixel
        mesh, paint = _stitched_normals(mesh.triangulate()), dict(color="#ffffff")
    elif analysis:                                     # the surface, analysed: its colour is the analysis
        mesh, paint = _analysis(mesh, analyse, data)
        style_name = {k: v for k, v in style_name.items() if k not in ("texture", "pbr", "metallic", "roughness")}
        style_name.update(smooth_shading=True, ambient=0.35, diffuse=0.7, specular=0.0)
    if not paint:
        paint = dict(color=color)
    actor = plotter.add_mesh(mesh, opacity=opacity, name=name, reset_camera=False, **paint, **style_name)
    if "texture" in style_name and not analysis:
        _use_matcap(actor)
    if analysis and analyse == "zebra":
        _use_zebra(actor)
    elif analysis or (data.kind.grid is not None and style_name.get("smooth_shading") is False
                      and style_name_view not in ("hidden lines", "wireframe")):
        actor.prop.interpolation = "phong"             # with the normals of each point (the sewn ones)
        actor.mapper.SetInterpolateScalarsBeforeMapping(True)   # the stripes and the colours, without steps
    # Only a little, and without multiplying by the slope of the face: enough for two faces on the same plane, without
    # an object that is behind (a box inside a prism) showing in front.
    actor.mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(0.0, -2.0 * min(order, 50))
    if style_name_view == "solid" and data.kind.faces is not None and not data.kind.curve and not analysis \
            and "texture" not in style_name and mesh.n_cells:
        studio.add_back_faces(plotter, name, actor, mesh)
    if (outlines and style_name_view in ("solid", "model") and data.kind.faces is not None and not data.kind.curve
            and mesh.n_cells and not analysis):
        light = sum(pv.Color(paper).float_rgb) / 3 > 0.5
        studio.add_outline(plotter, name, mesh, light, opacity, cells=bool(edges))
    if data.kind.curve or data.kind.faces is None:
        # The lines and the points, a little in front: some contour lines on their terrain, or some edges
        # on their surface, are not covered by it.
        actor.mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-2.0, -60.0)
        actor.mapper.SetRelativeCoincidentTopologyPointOffsetParameter(-60.0)
    if "scalars" in paint and not (analysis and analyse == "zebra"):
        _legend(plotter, name, actor, ink)
    return actor


def _stitched_normals(mesh: pv.PolyData) -> pv.PolyData:
    """The normals of each point, and at the points that coincide (the seam of a closed surface, the pole of a dome)
    the average of those that look alike: so the light does not mark a streak where the surface closes, and a sharp edge
    (the corner of a beam, with its repeated points) stays sharp."""
    mesh = mesh.compute_normals(cell_normals=False, point_normals=True, split_vertices=False,
                                  auto_orient_normals=False, consistent_normals=False)
    points = np.asarray(mesh.points)
    if not len(points):
        return mesh
    size_ = float(np.ptp(points, axis=0).max()) or 1.0
    keys = np.round(points / (size_ * 1e-7)).astype(np.int64)
    order = np.lexsort(keys.T[::-1])                  # (much faster than np.unique by rows)
    c = keys[order]
    new_group = np.r_[True, (c[1:] != c[:-1]).any(axis=1)]
    group = np.cumsum(new_group) - 1                  # the group of each point, in order
    n = np.asarray(mesh.point_data["Normals"], dtype=float)[order]
    total = np.zeros((group[-1] + 1, 3))
    np.add.at(total, group, n)
    mean = total / np.maximum(np.linalg.norm(total, axis=1, keepdims=True), 1e-12)
    # The average only where all look alike (a seam); at a sharp edge each one keeps its own.
    similar = np.ones(len(total))
    np.minimum.at(similar, group, (n * mean[group]).sum(axis=1)
                  / np.maximum(np.linalg.norm(n, axis=1), 1e-12))
    stitch = similar[group] > np.cos(np.radians(25))
    normals = np.empty_like(n)
    normals[order] = np.where(stitch[:, None], mean[group], n)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    mesh.point_data["Normals"] = np.divide(normals, length, out=np.zeros_like(normals), where=length > 1e-12)
    mesh.point_data.active_normals_name = "Normals"
    return mesh


def _for_matcap(mesh: pv.PolyData, smooth: bool) -> pv.PolyData:
    """The normals of each vertex (the matcap looks at them), split at the sharp edges, and some empty texture
    coordinates: so VTK passes the matcap image to the shader."""
    mesh = mesh.extract_surface(algorithm="dataset_surface") if not isinstance(mesh, pv.PolyData) else mesh
    if smooth and mesh.n_cells:                        # a surface: without a streak at its seam
        mesh = _stitched_normals(mesh)
    else:
        mesh = mesh.compute_normals(split_vertices=True, feature_angle=30, auto_orient_normals=False,
                                      consistent_normals=False)
    mesh.active_texture_coordinates = np.zeros((mesh.n_points, 2), np.float32)
    return mesh


_TEXTURES_MATCAP: dict[str, pv.Texture] = {}


def _texture_matcap(name: str) -> pv.Texture:
    from .matcaps import OWN, image_of, own
    key = name
    if name.startswith(OWN):                       # the user's: again if the file changed
        path = own().get(name)
        key = (name, path.stat().st_mtime if path is not None else 0)
    if key not in _TEXTURES_MATCAP:
        try:
            _TEXTURES_MATCAP[key] = pv.Texture(image_of(name))
        except Exception:                          # noqa: BLE001 (a file that is not an image: plaster)
            _TEXTURES_MATCAP[key] = _texture_matcap("plaster")
    return _TEXTURES_MATCAP[key]


def _use_matcap(actor) -> None:
    """Instead of the lights, the colour comes from the matcap: the point of the sphere that faces where the face
    faces (in the view), tinted with the object's colour (or that of «by a value»)."""
    actor.prop.interpolation = "phong"
    actor.GetShaderProperty().AddFragmentShaderReplacement(
        "//VTK::TCoord::Impl", True,
        "  vec3 nm = normalize(normalVCVSOutput);\n"
        "  if (nm.z < 0.0) nm = -nm;\n"                                   # a face seen from behind
        "  vec3 luz = texture(actortexture, nm.xy * 0.49 + 0.5).rgb;\n"
        "  gl_FragData[0] = vec4(clamp(luz * diffuseColor * 1.4, 0.0, 1.0), opacity);\n", False)


def _use_zebra(actor) -> None:
    """The zebra at each pixel (not by triangles): the reflection of the gaze on the surface (with the normal of that
    pixel) against some light bars; the edges, smoothed over the width of a pixel. It moves when the view turns, like a
    reflection: if the stripes continue without breaks from one surface to another, the join is smooth."""
    actor.prop.interpolation = "phong"
    actor.GetShaderProperty().AddFragmentShaderReplacement(
        "//VTK::Light::Impl", True,
        "  vec3 nz = normalize(normalVCVSOutput);\n"
        "  if (nz.z < 0.0) nz = -nz;\n"                                   # a face seen from behind
        "  vec3 r = reflect(vec3(0.0, 0.0, -1.0), nz);\n"
        f"  float s = sin(r.y * {STRIPS_ZEBRA:.1f} * 3.14159265);\n"
        "  float w = max(fwidth(s), 1e-4);\n"
        "  float t = smoothstep(-w, w, s);\n"
        "  vec3 c = mix(vec3(0.07, 0.07, 0.08), vec3(0.96, 0.96, 0.96), t);\n"
        "  c *= 0.85 + 0.15 * nz.z;\n"                                    # a little volume
        "  gl_FragData[0] = vec4(c, opacity);\n", False)


#: How a surface is analysed in the view (the node's panel): without analysis, its curvature, or zebra stripes.
ANALYSIS = ("no", "gaussian", "mean", "zebra")
#: The names of before (a project saved with «curvatura» opens with the Gaussian).
OLD_ANALYSIS = {"curvatura": "gaussian", "gaussiana": "gaussian", "media": "mean", "cebra": "zebra"}
#: The Gaussian curvature: blue the saddle-like one (negative), green the one that can be made from a flat sheet
#: (zero: planes, cylinders, cones), orange and red the dome-like one (positive).
COLOURS_CURVATURE = ("#2c5fb8", "#5fa8e0", "#5cb85c", "#f0ad4e", "#d9534f")
STRIPS_ZEBRA = 8


def _gauss_in_grid(values: np.ndarray, rows: int, columns: int, mean: bool = False) -> np.ndarray:
    """The Gaussian (or the mean) curvature at each point of some grid surfaces: (elements, rows·columns)."""
    from ..surfaces import grid_curvatures
    k, h = grid_curvatures(np.asarray(values, dtype=float).reshape(-1, rows, columns, 3), rows, columns)
    return (h if mean else k).reshape(len(k), -1)


def _analysis(mesh: pv.PolyData, mode: str, data=None):
    """The triangulated mesh with its Gaussian curvature at each point, and how to paint it: (mesh, add_mesh options),
    trimmed to the normal (the spikes at the edges do not hide the rest). (The zebra goes in the shader: `_use_zebra`.)"""
    grid = getattr(getattr(data, "kind", None), "grid", None)
    tri = _stitched_normals(mesh.triangulate())       # without cleaning: the points, in the same order as the data
    if mode in ("gaussian", "mean"):
        if grid is not None and tri.n_points == np.asarray(data.values).reshape(-1, 3).shape[0]:
            k = _gauss_in_grid(data.values, *grid, mean=mode == "mean").ravel()
        else:                                          # a loose mesh: VTK's, without counting its edges
            k = np.asarray(tri.curvature(curv_type="gaussian" if mode == "gaussian" else "mean"), dtype=float)
            edges = tri.extract_feature_edges(boundary_edges=True, feature_edges=False, manifold_edges=False,
                                               non_manifold_edges=False)
            if edges.n_points:
                near = tri.find_closest_point(edges.points) if hasattr(tri, "find_closest_point") else []
                k[np.unique(np.atleast_1d(near))] = 0.0
        k[~np.isfinite(k)] = 0.0
        limit = float(np.percentile(np.abs(k), 95)) if k.size else 0.0
        # A minimum by the size: what is almost zero (the noise of a developable) stays green, it is not painted
        # as if it were curvature.
        size_ = float(np.ptp(np.asarray(tri.points), axis=0).max()) or 1.0
        limit = max(limit, 0.02 / size_ ** 2 if mode == "gaussian" else 0.02 / size_)
        tri.point_data["curvature"] = np.clip(k, -limit, limit)
        table = pv.LookupTable()
        rgb = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in COLOURS_CURVATURE], dtype=float)
        t = np.linspace(0, 1, 256)
        places = np.linspace(0, 1, len(rgb))
        table.values = np.stack([np.interp(t, places, rgb[:, j]) for j in range(3)] + [np.full(256, 255.0)],
                                axis=1).astype(np.uint8)
        table.scalar_range = (-limit, limit)
        return tri, dict(scalars="curvature", cmap=table, clim=(-limit, limit), show_scalar_bar=False)
    raise ValueError(mode)


def _wrap(text: str, width: int = 22) -> str:
    """A long name in several short lines, at the spaces: it fits over its legend."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    lines.append(line)
    return "\n".join(lines[:3]) + ("…" if len(lines) > 3 else "")


#: The box of a legend in pixels (title included), and the share of its width the colour bar takes. The text has a
#: fixed size; the box is placed in pixels too (arrange_legends, also when the view changes size), so it always fits.
LEGEND_PIXELS, LEGEND_BAR = (170, 150), 0.11
#: The room on the left of the bar for its numbers when they are written as annotations (decimal comma), in pixels.
ANNOTATIONS_ROOM = 38
#: The height of a legend of a single value (no bar: its name and the value).
LEGEND_CONSTANT = 64


def legend_numbers(low: float, high: float, fmt: str) -> list[tuple[float, str]]:
    """The three numbers of a legend (its ends and its middle), written in the language set: 17,2 in Spanish."""
    return [(v, comma(fmt % v)) for v in (low, (low + high) / 2, high)]


def _legend(plotter: pv.Plotter, name: str, actor, ink: str) -> None:
    """The colour bar of an object painted by a value, with its name. The box is wide enough for the name, and the
    whole box stays inside the view (on either side), so the name is never cut by the edge."""
    if name in plotter.scalar_bars:
        plotter.remove_scalar_bar(name, render=False)
    low, high = actor.mapper.scalar_range
    constant = high - low <= max(abs(low) * 1e-6, 1e-9) * 1.01   # all the same value: say it, without a scale
    # Numbers as an architect writes them: 2420, not 2.42e+03 (the «g» format turns big ones into powers of ten).
    biggest = max(abs(low), abs(high))
    fmt = "%.0f" if biggest >= 100 else "%.3g"
    title = _wrap(name) + (f"\n= {comma(fmt % low)}" if constant else "")
    # Its numbers, written as the interface writes them (17,2 in Spanish): as annotations of the colour table, which
    # take any text (the labels of the bar only know the decimal point).
    marks = [] if constant else legend_numbers(low, high, fmt)
    written = any("," in text for _, text in marks)
    table = actor.mapper.lookup_table
    table.ResetAnnotations()
    for value, text in marks if written else []:
        table.SetAnnotation(value, text)
    bar = plotter.add_scalar_bar(title=title, mapper=actor.mapper, vertical=True,
                                 n_labels=0 if constant or written else 3, fmt=fmt, title_font_size=12,
                                 label_font_size=11, color=ink, render=False)
    if written:
        bar.SetDrawAnnotations(True)                 # (on the left of the bar: arrange_legends leaves them room)
        bar.SetAnnotationLeaderPadding(2)
        bar.GetAnnotationTextProperty().ShallowCopy(bar.GetLabelTextProperty())
    bar.SetBarRatio(LEGEND_BAR)
    bar.SetUnconstrainedFontSize(True)               # the text keeps its size: the box is made to fit it
    bar.SetVerticalTitleSeparation(8)
    bar.SetTextPad(6)                                # the values a little apart from the bar
    if constant:
        bar.SetDrawColorBar(False)                   # a single value: its name and the value are enough
    arrange_legends(plotter)


#: On which side of the view the legends go (View → Legends): «right» or «left». Also in the image. «top» is the
#: height kept free at the top right (the orientation of the view is there), in pixels.
LEGENDS = {"side": "right", "top": 0}


def arrange_legends(plotter: pv.Plotter) -> None:
    """The legends, at one side and without overlapping: from bottom to top, as many as fit in the height; then,
    another column towards the centre. Each box, of fixed size in pixels, stays inside the view. On the right the
    first column stays below the orientation of the view. The size is the one the view really has; if it changes later (a window
    that settles after being resized), they are placed again before painting (_follow_size)."""
    width, height = (max(int(n), 1) for n in plotter.window_size)
    _follow_size(plotter)
    plotter._legends_size = (width, height)
    scale = max(plotter.render_window.GetDPI() / 72, 1.0)   # a scaled screen: the text grows, so does the box
    w = round(LEGEND_PIXELS[0] * scale)
    margin = round(10 * scale)
    bars = list(plotter.scalar_bars.values())
    # A legend of a single value has no bar: its name and the value, a low box.
    heights = [round((LEGEND_PIXELS[1] if bar.GetDrawColorBar() else LEGEND_CONSTANT) * scale) for bar in bars]

    # On the right, the first column stays below the orientation of the view (it is as wide as a legend); the others
    # take the whole height.
    top = LEGENDS["top"] if LEGENDS["side"] != "left" else 0
    spots, column, y = [], 0, margin
    for h in heights:
        if y > margin and y + h > height - (top if column == 0 else 0) - margin:
            column, y = column + 1, margin
        spots.append((column, y))
        y += h + margin
    for bar, h, (column, y) in zip(bars, heights, spots):
        x = margin + (w + margin) * column
        if LEGENDS["side"] != "left":
            x = width - margin - w - (w + margin) * column
        x = min(max(x, 0), max(width - w, 0))
        room = round(ANNOTATIONS_ROOM * scale) if bar.GetDrawAnnotations() else 0
        # Numbers written as annotations (with the decimal comma) go on the left of the bar: the bar moves in.
        bar.SetWidth((w - room) / width)
        bar.SetBarRatio(LEGEND_BAR * w / (w - room))
        bar.SetHeight(h / height)
        bar.GetPositionCoordinate().SetValue((x + room) / width, y / height)


def _follow_size(plotter: pv.Plotter) -> None:
    """Once per view: before each painting, if the view has another size than the one the legends were placed for,
    they are placed again."""
    if getattr(plotter, "_legends_follow", False):
        return
    plotter._legends_follow = True

    def check(*_):
        if plotter.scalar_bars and tuple(int(n) for n in plotter.window_size) != getattr(plotter, "_legends_size", None):
            arrange_legends(plotter)

    plotter.renderer.AddObserver("StartEvent", check)


#: The side of the orientation of the view (top right), in pixels.
GIZMO_PIXELS = 230

#: More numbers than these are not put (they would not be read and would make the view slow).
MAX_NUMBERS = 2000


def numbers_of(data: Data):
    """Where the number of each element goes and which it is: the points, on themselves; a curve, at its middle; a
    surface or a volume, at the centre of its vertices. Without levels, nothing to number (except a single curve, which
    carries no number but its direction)."""
    if data.kind is None:
        return None, []
    v = np.asarray(data.values, dtype=float)
    if data.kind.faces is None and not data.kind.curve:     # puntos
        shape = v.shape[:-1]
        anchors = v.reshape(-1, 3)
    else:
        shape = v.shape[:-2]
        elements = v.reshape((-1,) + v.shape[-2:])
        anchors = elements[:, elements.shape[1] // 2] if data.kind.curve else elements.mean(axis=1)
    if not data.levels:
        return anchors, [""]
    mask = np.broadcast_to(data.mask, shape).reshape(-1)
    texts = ["·".join(str(data.starts.get(n, 0) + i) for n, i in zip(data.levels, index))
              for index in np.ndindex(shape)]
    return anchors[mask], [t for t, m in zip(texts, mask) if m]


def frame(plotter: pv.Plotter) -> None:
    """Frames everything, in perspective from the front, the left and a little above.

    "Front" is -Y: where a facade in elevation faces.
    """
    plotter.view_vector((-0.55, -1.0, 0.45), viewup=(0, 0, 1))
    plotter.reset_camera()


def _snapshot(plotter: pv.Plotter, filepath, scale: int = 1, background: str | None = "white",
                 axes: bool = False, gizmo=None) -> tuple[int, int]:
    """Saves the view in PNG; leaves the background and the axes as they were.

    `gizmo`: that of the view's orientation (Viewer); without it, the usual axes (without a window).
    """
    transparent = background == "transparent"
    color_before = plotter.background_color
    renderer = plotter.renderer                       # the gradient of Studio and Model, to be put back as it was
    gradient_before, top_before = bool(renderer.GetGradientBackground()), renderer.GetBackground2()
    if background and not transparent:
        plotter.set_background(background)
    gizmo_before = bool(gizmo.GetEnabled()) if gizmo is not None else False
    if gizmo is not None:
        gizmo.SetEnabled(axes)
    elif not axes:
        plotter.hide_axes()
    try:
        img = plotter.screenshot(str(filepath), transparent_background=transparent, scale=scale, return_img=True)
    finally:
        plotter.set_background(color_before)
        if gradient_before:
            renderer.SetBackground2(*top_before)
            renderer.GradientBackgroundOn()
        if gizmo is not None:
            gizmo.SetEnabled(gizmo_before)
        else:
            plotter.show_axes()
        plotter.render()
    return int(img.shape[1]), int(img.shape[0])


def image(filepath, objects: list[tuple[str, Data, dict]], width: int = 1920, height: int = 1080,
           background: str | None = "white", axes: bool = False) -> tuple[int, int]:
    """A PNG image of the scene, without a window, with the usual framing."""
    plotter = pv.Plotter(off_screen=True, window_size=(width, height))
    try:
        prepare(plotter)
        for order, (name, data, style_name) in enumerate(objects):
            draw(plotter, name, data, color=style_name.get("color", COLOR_GEOMETRY),
                    opacity=float(style_name.get("opacity", 1.0)), edges=style_name.get("edges"), order=order,
                    colour_by=style_name.get("_colour_by"))
        frame(plotter)
        limits = np.array(plotter.bounds).reshape(3, 2)
        size_ = float(np.linalg.norm(limits[:, 1] - limits[:, 0])) or 1.0
        plotter.enable_ssao(radius=size_ * studio.OCCLUSION_SHARE["solid"], bias=size_ * 0.0008, kernel_size=128,
                            blur=True)
        return _snapshot(plotter, filepath, background=background, axes=axes)
    finally:
        plotter.close()


def camera_framed(objects: list[tuple[str, Data, dict]], width: int = 1600, height: int = 1000):
    """The camera of the usual framing, without a window, in Croquis's form."""
    from ..croquis import pyvista_camera
    plotter = pv.Plotter(off_screen=True, window_size=(width, height))
    try:
        for order, (name, data, style_name) in enumerate(objects):
            draw(plotter, name, data, order=order)
        frame(plotter)
        return pyvista_camera(plotter.camera, width, height, np.array(plotter.bounds).reshape(3, 2).T)
    finally:
        plotter.close()


class Viewer(QWidget):
    """3D view with an orbit camera (left button turns, wheel zooms).

    A right click without dragging asks for the menu (`menu_asked`); dragging, it zooms.
    """

    requested_menu = Signal(object)   # the point (on the screen) where it was clicked
    view_changed = Signal(str)   # the name of the view («Front», «Isometric», «Free»…)
    projection_changed = Signal(bool)   # parallel or not (also with key 5 of the numeric keypad)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.view = QtInteractor(self)
        prepare(self.view, axes=False)
        self._gizmo = self._create_gizmo()
        LEGENDS["top"] = GIZMO_PIXELS if self._gizmo.GetEnabled() else 0
        self._browser = Browser(self.view, self._gizmo, self)   # orbit where the pointer is
        self._browser.menu.connect(self.requested_menu)
        self._browser.on_look = self._look_towards
        self._browser.on_orbit = lambda: self._name_view('Free')
        self._browser.on_moving = self._moving
        # While the camera moves, the occlusion (the dearest part of the image on a big screen) is left out; a moment
        # after it stops, the view is painted again with everything.
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(220)
        self._settle_timer.timeout.connect(self._settle)
        self._light_while_moving = False
        self.name_view = 'Free'
        self.drawing = Drafter(self.view, self)     # draw points with the mouse (Drawn curve)
        self.bar_drawing = BarDrawing(self)         # its tools, over the view while drawing
        self.bar_drawing.tool.connect(self.drawing.put_tool)
        self.bar_drawing.curvature.connect(self.drawing.put_curvature)
        self.drawing.tool_changed.connect(self.bar_drawing.put_tool)
        self.view_changed.connect(lambda *_: self.drawing.repaint())   # another view: it draws on its plane
        # Before each image, the camera's clipping planes adjust to what there is: if not, on adding something or
        # zooming in, what is outside them gets «eaten» (and on starting to draw, the view stayed empty).
        self.view.renderer.AddObserver("StartEvent", lambda *_: self._paint_before())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.bar_drawing)
        self.strip_nodes = StripNodes(self)              # the knots of the curve being edited (if asked for)
        layout.addWidget(self.strip_nodes)
        layout.addWidget(self.view.interactor)
        self._actors: dict[str, object] = {}
        self._order: dict[str, int] = {}  # to resolve surfaces on the same plane
        self._data_items: dict[str, tuple] = {}  # what is shown, to paint it again with another style
        self._number: set[str] = set()     # those that carry their numbers (and the direction of their curves) in view
        self._curvature: set[str] = set()   # the curves with their curvature comb in view
        self._analyse: dict[str, str] = {}  # the analysed surfaces: «gaussian», «mean» or «zebra»
        self._colour_by: dict[str, tuple] = {}  # those painted by a value: (a number per element, gradient)
        self.style_name = "solid"
        self.software: bool | None = None            # drawn by the processor (known after the first image)
        self._radius_occlusion = self._margin_occlusion = 1.0   # the occlusion, by the size of the scene
        self._theme_background = COLOR_DEPTH
        self.outlines = True                         # the thin lines at the edges in Studio and Model
        self.put_style_name("solid")                 # Studio from the start: its light, occlusion and background

    def display(self, name: str, data: Data, color: str = COLOR_GEOMETRY, opacity: float = 1.0,
                edges: bool | None = None, number: bool | None = None, colour_by=..., force: bool = False,
                paint: bool = True, curvature: bool | None = None, analyse=...) -> None:
        """Shows (or replaces) the geometry `name`. `number`: with the number of each element (and the direction of the
        curves); without saying, as it was. `colour_by`: (a number per element, gradient) to paint it by a value, None for a
        single colour; without saying, as it was.

        If that same result is already shown with the same, it is not redone (on recomputing, most do not change); `force`
        redoes it anyway (another view style). `paint`: False to paint only once at the end."""
        if analyse is not ... and analyse != self._analyse.get(name):
            force = True
            if analyse:
                self._analyse[name] = analyse
            else:
                self._analyse.pop(name, None)
        if curvature is not None and curvature != (name in self._curvature):
            force = True
            (self._curvature.add if curvature else self._curvature.discard)(name)
        if not force and self._already_sees(name, data, color, opacity, edges, number, colour_by):
            return
        if name in self._actors:
            self.view.remove_actor(self._actors[name], render=False)
        self.view.remove_actor(studio.outline_name(name), render=False)
        self.view.remove_actor(studio.back_name(name), render=False)
        if colour_by is not ...:
            if colour_by is None:
                self._colour_by.pop(name, None)
            else:
                self._colour_by[name] = colour_by
        self._remove_legend(name)
        if number is not None:
            (self._number.add if number else self._number.discard)(name)
        order = self._order.setdefault(name, len(self._order))
        self._data_items[name] = (data, color, opacity, edges)
        self._actors[name] = draw(self.view, name, data, color, opacity, edges, order,
                                        self.style_name, *self._paper_y_ink(), colour_by=self._colour_by.get(name),
                                        analyse=self._analyse.get(name), outlines=self.outlines)
        self._remove_numbers(name)
        if name in self._number:
            self._put_numbers(name, data)
        self._put_comb(name, data if name in self._curvature else None)
        if paint:
            self.view.render()

    #: More curves than this, without a comb (it would not read, and it takes long).
    MAX_COMBS = 400

    def _put_comb(self, name: str, data) -> None:
        """The curvature comb of the curves of `name` (None: none): hairs outwards, longer where they curve more, all
        with the same scale."""
        for extra in ("·peine", "·peine_borde"):
            self.view.remove_actor(name + extra, render=False)
        if data is None or data.kind is None or not data.kind.curve:
            return
        from ..geometry import curvature_comb
        v = np.asarray(data.values, dtype=float)
        curves = v.reshape(-1, v.shape[-2], 3)
        if len(curves) > self.MAX_COMBS:
            return
        bases, tips = curvature_comb(curves)
        if not len(bases):
            return
        color = "#ff8fb3" if self._paper_y_ink()[1] == "#e6e7ec" else "#b0245a"
        m = len(bases)
        hairs = np.column_stack([np.full(m, 2), np.arange(m), np.arange(m) + m]).ravel()
        self.view.add_mesh(pv.PolyData(np.vstack([bases, tips]), lines=hairs), color=color, opacity=0.45,
                            line_width=1, name=name + "·peine", pickable=False, reset_camera=False, lighting=False)
        # The edge: the line of the tips, curve by curve (it does not jump from one curve to the other).
        how_many = [len(x) for x in (curvature_comb(c)[0] for c in curves)]
        cells, start = [], 0
        for n in how_many:
            if n >= 2:
                cells += [n, *range(start, start + n)]
            start += n
        if cells:
            self.view.add_mesh(pv.PolyData(tips, lines=np.array(cells)), color=color, line_width=2,
                                name=name + "·peine_borde", pickable=False, reset_camera=False, lighting=False)

    def put_curvature(self, name: str, yes: bool) -> None:
        """Puts or removes the curvature comb of what is already shown (the switch of the node's panel)."""
        (self._curvature.add if yes else self._curvature.discard)(name)
        self._put_comb(name, self._data_items[name][0] if yes and name in self._data_items else None)
        self.view.render()

    def _already_sees(self, name, data, color, opacity, edges, number, colour_by) -> bool:
        before = self._data_items.get(name)
        if name not in self._actors or before is None or before[0] is not data or before[1:] != (color, opacity, edges):
            return False
        if number is not None and number != (name in self._number):
            return False
        if colour_by is ...:
            return True
        had = self._colour_by.get(name)
        if colour_by is None or had is None:
            return colour_by is had
        return colour_by[1] == had[1] and np.array_equal(colour_by[0], had[0])

    def legends_side(self, side: str) -> None:
        LEGENDS["side"] = side
        arrange_legends(self.view)
        self.view.render()

    def _remove_legend(self, name: str) -> None:
        if name in self.view.scalar_bars:
            self.view.remove_scalar_bar(name, render=False)
            arrange_legends(self.view)

    _EXTRAS = ("·numbers", "·numbers-labels", "·direction", "·start")   # (pyvista calls the labels «-labels»)

    def _remove_numbers(self, name: str) -> None:
        for extra in self._EXTRAS:
            self.view.remove_actor(name + extra, render=False)

    def _put_numbers(self, name: str, data: Data) -> None:
        """The number of each element (from 0) in the view; on the curves, their start and an arrow with their
        direction. With several levels, the number of each: «2·5» is ring 2, point 5."""
        paper, ink = self._paper_y_ink()
        anchors, texts = numbers_of(data)
        if anchors is None:
            return
        size_ = float(np.linalg.norm(np.ptp(np.asarray(data.values).reshape(-1, 3), axis=0))) or 1.0
        if len(texts) and len(texts) <= MAX_NUMBERS and texts != [""]:
            self.view.add_point_labels(anchors, texts, name=name + "·numbers", font_size=13, text_color=ink,
                                        shape_color=paper, shape_opacity=0.75, show_points=False,
                                        always_visible=True, reset_camera=False, pickable=False)
        if data.kind.curve:                                   # where each curve starts, and where it goes
            curves = np.asarray(data.values).reshape(-1, data.values.shape[-2], 3)
            if len(curves) <= MAX_NUMBERS:
                k = max(1, int(curves.shape[1] * 0.45))
                direction = curves[:, k] - curves[:, k - 1]
                length = np.linalg.norm(direction, axis=1, keepdims=True)
                valid = length[:, 0] > 1e-12
                if valid.any():
                    self.view.add_arrows(curves[valid, k - 1], direction[valid] / length[valid],
                                          mag=size_ * 0.05, color=ink, name=name + "·direction",
                                          reset_camera=False, pickable=False)
                self.view.add_mesh(pv.PolyData(curves[:, 0]), color=ink, point_size=10,
                                    render_points_as_spheres=True, name=name + "·start", reset_camera=False,
                                    pickable=False)

    def put_numbers(self, name: str, yes: bool) -> None:
        """Puts or removes the numbers of what is already shown (the switch of the node's panel)."""
        (self._number.add if yes else self._number.discard)(name)
        self._remove_numbers(name)
        if yes and name in self._data_items:
            self._put_numbers(name, self._data_items[name][0])
        self.view.render()

    def put_opacity(self, name: str, opacity: float) -> None:
        """Another opacity for what is already shown (without recomputing anything): for the panel's slider."""
        if name in self._data_items:
            data, color, _, edges = self._data_items[name]
            self.display(name, data, color, opacity, edges, force=True)

    def _paper_y_ink(self) -> tuple[str, str]:
        background = self.view.background_color
        paper = background.hex_rgb if hasattr(background, "hex_rgb") else "#ffffff"
        light = sum(background.float_rgb) / 3 > 0.5 if hasattr(background, "float_rgb") else True
        return paper, ("#20222a" if light else "#e6e7ec")

    def resizeEvent(self, event) -> None:
        """The legends, placed again for the new size (they are in pixels: they must not be cut by the edge)."""
        super().resizeEvent(event)
        if self.view.scalar_bars:
            QTimer.singleShot(0, self._arrange_legends_now)

    def _arrange_legends_now(self) -> None:
        if self.view.scalar_bars:
            arrange_legends(self.view)
            self.view.render()

    def put_outlines(self, yes: bool) -> None:
        """Shows or hides the outlines of Studio and Model (everything is painted again)."""
        self.outlines = bool(yes)
        for name, (data, color, opacity, edges) in list(self._data_items.items()):
            self.display(name, data, color, opacity, edges, force=True, paint=False)
        self.view.render()

    def _moving(self) -> None:
        """The camera is moving: without occlusion until it stops."""
        if self.style_name in ("solid", "model", "occlusion", "matcap") and not self._light_while_moving:
            self.view.disable_ssao()
            self._light_while_moving = True
        if self._light_while_moving:
            self._settle_timer.start()

    def _settle(self) -> None:
        """The camera stopped: the occlusion again, and one full image."""
        if not self._light_while_moving:
            return
        self._light_while_moving = False
        if self.style_name in ("solid", "model", "occlusion", "matcap"):
            self.view.enable_ssao(radius=self._radius_occlusion, bias=self._margin_occlusion, kernel_size=128,
                                   blur=True)
            self.view.render()

    def _occlusion_for_scene(self, style_name: str) -> tuple[float, float]:
        """The radius and margin of the occlusion of Studio and Model, by the size of what is shown."""
        limits = np.array(self.view.renderer.ComputeVisiblePropBounds(), dtype=float)
        if not np.all(np.isfinite(limits)) or limits[1] < limits[0]:
            return 1.0, 0.001
        limits = limits.reshape(3, 2)
        size_ = float(np.linalg.norm(limits[:, 1] - limits[:, 0])) or 1.0
        return size_ * studio.OCCLUSION_SHARE[style_name], size_ * 0.0008

    def _apply_background(self) -> None:
        """The theme's background; in Studio, a soft gradient of it; in Model, its own light paper, unless another
        background was chosen for the view (View → Background: light, mid or dark), then a gradient of that one."""
        from . import theme
        theme_colour = getattr(self, "_theme_background", COLOR_DEPTH)
        if self.style_name == "model" and theme.TONE.get("view", "theme") == "theme":
            self.view.set_background(studio.MODEL_BACKGROUND[0], top=studio.MODEL_BACKGROUND[1])
        elif self.style_name == "model":
            self.view.set_background(theme_colour, top=studio.lighter(theme_colour))
        elif self.style_name == "solid":
            self.view.set_background(theme_colour, top=studio.lighter(theme_colour))
        else:
            self.view.set_background(theme_colour)
        if hasattr(self, "name_view"):                # the name of the view, readable on the new background
            self._name_view(self.name_view)

    def put_style_name(self, style_name: str) -> None:
        """Studio, model, matcap, wireframe, hidden lines, x-ray or occlusion: everything is painted again."""
        if style_name not in STYLE_NAMES:
            style_name = "solid"
        if hasattr(self, "_settle_timer"):            # a change of style in the middle of a move: start clean
            self._settle_timer.stop()
            self._light_while_moving = False
        if self.style_name in ("occlusion", "matcap", "solid", "model"):
            self.view.disable_ssao()
        self.style_name = style_name
        self._smooth_edges()
        light_up(self.view, with_camera=style_name == "occlusion", style=style_name)
        self._apply_background()
        if style_name in ("solid", "model"):           # their occlusion follows what is seen (_paint_before)
            self._radius_occlusion, self._margin_occlusion = self._occlusion_for_scene(style_name)
            self.view.enable_ssao(radius=self._radius_occlusion, bias=self._margin_occlusion, kernel_size=128,
                                   blur=True)
        elif style_name in ("occlusion", "matcap"):
            limits = np.array(self.view.bounds).reshape(3, 2)
            size_ = float(np.linalg.norm(limits[:, 1] - limits[:, 0])) or 1.0
            # The matcap's occlusion is fine (the corners, like a «cavity» shading): the ribs
            # close together, the junctions; that of the Occlusion style, broad (an overcast day).
            radius = 0.03 if style_name == "matcap" else 0.12
            self._radius_occlusion, self._margin_occlusion = size_ * radius, size_ * 0.001
            self.view.enable_ssao(radius=self._radius_occlusion, bias=self._margin_occlusion, kernel_size=128,
                                   blur=True)
        for name, (data, color, opacity, edges) in list(self._data_items.items()):
            self.display(name, data, color, opacity, edges, force=True, paint=False)
        self.view.render()

    def _parallel_camera_outside_in(self) -> None:
        camera = self.view.camera
        if not camera.GetParallelProjection():
            return
        limits = np.array(self.view.renderer.ComputeVisiblePropBounds(), dtype=float)
        if not np.all(np.isfinite(limits)) or limits[1] < limits[0]:
            return
        limits = limits.reshape(3, 2)
        centre, radius = limits.mean(axis=1), float(np.linalg.norm(limits[:, 1] - limits[:, 0])) / 2
        focus, position = np.array(camera.GetFocalPoint()), np.array(camera.GetPosition())
        distance = float(np.linalg.norm(focus - position))
        if distance < 1e-12:
            return
        towards = (focus - position) / distance                      # where it looks
        needed = float(np.dot(focus - centre, towards)) + radius * 1.05 + 1e-3   # everything, in front of the camera
        if needed > distance:
            camera.SetPosition(*(focus - towards * needed))

    def _smooth_edges(self) -> None:
        """The smoothing of the edges. The usual one (SSAA) draws the image larger and reduces it: the lines come out
        clean. It does not let occlusion through, so the styles with occlusion use FXAA (light: on a big screen the view
        stays fluid). Without a graphics card every style uses FXAA: drawn by the processor, SSAA made the lines styles
        three times slower while orbiting."""
        light = self.style_name in ("occlusion", "matcap", "solid", "model") or bool(self.software)
        self.view.disable_anti_aliasing()
        smooth_edges(self.view, "fxaa" if light else "ssaa")

    def _learn_renderer(self) -> None:
        """After the first image: whether a graphics card draws. If it is the processor, the edges change at once."""
        self.software = software_rendering(self.view.ren_win)
        self._renderer_asked = getattr(self, "_renderer_asked", 0) + 1
        if self.software is None and self._renderer_asked >= 3:     # it does not say: as with a graphics card
            self.software = False
        if self.software:
            QTimer.singleShot(0, self._smooth_edges_again)

    def _smooth_edges_again(self) -> None:
        self._smooth_edges()
        self.view.render()

    def _paint_before(self) -> None:
        """Before each image: the clipping planes, and the radius of the occlusion by what is seen.

        The occlusion reads the depth of the neighbours in a reduced image, coarser the farther it searches on the screen:
        with zoom from far away (or in parallel), a fixed radius took up half the screen and the flat faces got streaked in
        stripes. The radius does not go beyond a quarter of the height seen.

        In parallel, the camera moves away (in its same direction) until it is outside everything that is seen: zooming
        towards the pointer it could end up inside the model, and what was behind it was cut in a straight line. In parallel,
        the distance does not change what is seen."""
        if self.software is None:
            self._learn_renderer()
        self._parallel_camera_outside_in()
        self.view.renderer.ResetCameraClippingRange()
        occlusion = self.view.renderer._render_passes._ssao_pass
        if occlusion is not None and self.style_name in studio.OCCLUSION_SHARE:
            self._radius_occlusion, self._margin_occlusion = self._occlusion_for_scene(self.style_name)
        if occlusion is not None:
            camera = self.view.camera
            if camera.GetParallelProjection():
                height = camera.GetParallelScale()
            else:
                height = camera.GetDistance() * np.tan(np.radians(camera.GetViewAngle() / 2))
            radius = min(self._radius_occlusion, 0.25 * height)
            occlusion.SetRadius(radius)
            # The margin goes in proportion to the radius, but from far away the depth loses precision: it does not go below
            # a fraction of the camera's distance.
            occlusion.SetBias(max(self._margin_occlusion * radius / self._radius_occlusion, 0.002 * camera.GetDistance()))

    def put_matcap(self, name: str) -> None:
        """The matcap's material (plaster, clay, graphite, ceramic); if it is being seen in Matcap, it is repainted."""
        from .matcaps import known
        MATCAP["name"] = name if known(name) else "plaster"
        if self.style_name == "matcap":
            for n, (data, color, opacity, edges) in list(self._data_items.items()):
                self.display(n, data, color, opacity, edges, force=True, paint=False)
            self.view.render()

    def remove_except(self, names, paint: bool = True) -> None:
        """Removes from the view everything that is not in `names`."""
        for name in [n for n in self._actors if n not in names]:
            self.view.remove_actor(self._actors.pop(name), render=False)
            self.view.remove_actor(studio.outline_name(name), render=False)
            self.view.remove_actor(studio.back_name(name), render=False)
            self._data_items.pop(name, None)
            self._colour_by.pop(name, None)
            self._remove_legend(name)
            self._remove_numbers(name)
            self._put_comb(name, None)
        if paint:
            self.view.render()

    def clean(self) -> None:
        self.drawing.finish()
        self.view.clear()
        light_up(self.view, with_camera=self.style_name == "occlusion", style=self.style_name)   # clear() takes the lights away
        self._actors.clear()
        self._order.clear()
        self._data_items.clear()
        self._number.clear()
        self._curvature.clear()
        self._analyse.clear()
        self._colour_by.clear()
        self._size_ = None
        self._name_view(self.name_view)          # clear() also takes away the name of the view

    def frame(self, fresh: bool = False) -> None:
        """Frames everything from where the camera already looks (from the front it stays the front); `fresh`, from
        the usual direction (a project opened without its camera)."""
        if fresh:
            frame(self.view)
            self._name_view('Free')
        else:
            self.view.reset_camera()
            self._name_view(self.name_view)
        self._size_ = self._visible_size_()

    # The size of what is seen the last time it was looked at (None: not known yet, e.g. on opening a project with its
    # saved camera).
    _size_: float | None = 0.0

    def frame_si_appears(self) -> None:
        """If before nothing with size was seen (nothing, or a single point) and now it is, it frames: if not, the camera
        stays with the zoom of that point and the new falls out of the view. While drawing, the camera belongs to whoever
        draws: only the size is noted."""
        size_ = self._visible_size_()
        before, self._size_ = self._size_, size_
        if before is not None and before < 1e-9 < size_ and not self.drawing.active:
            self.frame()

    def _visible_size_(self) -> float:
        minima, maximum = [], []
        for data, *_ in self._data_items.values():
            v = np.asarray(data.values, dtype=float)
            if v.size and v.shape[-1] == 3:
                v = v.reshape(-1, 3)
                minima.append(np.nanmin(v, axis=0))
                maximum.append(np.nanmax(v, axis=0))
        if not minima:
            return 0.0
        return float(np.linalg.norm(np.max(maximum, axis=0) - np.min(minima, axis=0)))

    def rotate_camera(self, degrees: float) -> None:
        self.view.camera.azimuth = self.view.camera.azimuth + degrees
        self.view.render()

    def capture(self, filepath) -> None:
        """Saves an image of the 3D view."""
        self.view.screenshot(str(filepath))

    def put_navigation(self, as_: str = "tensela") -> None:
        """The mouse buttons of a scheme (Tensela, Blender, Rhino, SketchUp; ui/navigation.py).

        In all of them it orbits around what is under the pointer and zooms towards it. With the numeric keypad: 1 front,
        3 right, 7 plan (with Ctrl, the opposite) and 5 perspective or parallel.
        """
        self.navigation = as_
        self._browser.put_scheme(as_)
        if not getattr(self, "_keys", False):
            self._keys = True
            for keys, view in ((("KP_1", "KP_End"), "front"), (("KP_3", "KP_Next"), "right"),
                                  (("KP_7", "KP_Home"), "plan")):
                for key in keys:
                    self.view.add_key_event(key, lambda v=view: self.look(v))
            for key in ("KP_5", "KP_Begin"):
                self.view.add_key_event(key, self.parallel_toggle)

    # From where each view of the numeric keypad looks (Y is north): (where it looks, what is up).
    VIEWS = {"front": ((0, 1, 0), (0, 0, 1)), "right": ((-1, 0, 0), (0, 0, 1)), "plan": ((0, 0, -1), (0, 1, 0))}

    def plane_of_view(self) -> str:
        """The plane a new rectangle, circle or arc is put in: the one the view looks at, the same rule as drawing
        (plan in plan and in 3D; elevation from the front; side elevation from the side)."""
        return ('side elevation', 'elevation', 'plan')[self.drawing._axis_plane()]

    def look(self, view: str, opposite: bool | None = None) -> None:
        """Front (from the south), right (from the east) or plan; with Ctrl, the opposite."""
        if opposite is None:
            opposite = bool(self.view.iren.interactor.GetControlKey())
        ahead, above = (np.array(v, dtype=float) for v in self.VIEWS[view])
        if opposite:
            ahead = -ahead
        self._look_towards(ahead, above)

    def isometric(self) -> None:
        """An isometric view: from the south-west and above, at 45° and 35° (with Ctrl, from the north-east)."""
        opposite = bool(self.view.iren.interactor.GetControlKey())
        # Where the camera looks: the camera stays in the south-west and above (or in the north-east).
        self._look_towards((-1.0, -1.0, -1.0) if opposite else (1.0, 1.0, -1.0), (0, 0, 1))

    #: The name of each view, by where the camera looks.
    NAMES_VIEW = {(0, 1, 0): 'Front', (0, -1, 0): 'Back', (-1, 0, 0): 'Right', (1, 0, 0): 'Left',
                     (0, 0, -1): 'Top', (0, 0, 1): 'Bottom', (1, 1, -1): 'Isometric', (-1, -1, -1): 'Isometric'}

    def _look_towards(self, ahead, above) -> None:
        """Another view direction with the same centre and the same zoom (like a numeric keypad): from plan to front it
        does not move away; to see everything there is «Frame all»."""
        camera = self.view.camera
        focus, distance, scale = np.array(camera.focal_point), camera.distance, camera.parallel_scale
        ahead = np.asarray(ahead, dtype=float)
        ahead = ahead / (np.linalg.norm(ahead) or 1.0)
        camera.position = tuple(focus - ahead * distance)
        camera.focal_point = tuple(focus)
        camera.up = tuple(above)
        camera.parallel_scale = scale
        key = tuple(int(round(c)) for c in np.sign(np.asarray(ahead, dtype=float)))
        self._name_view(self.NAMES_VIEW.get(key, 'Free'))
        self.view.render()

    def parallel_toggle(self) -> None:
        self.parallel_put(not self.view.camera.parallel_projection)

    def parallel_put(self, yes: bool) -> None:
        self.view.camera.parallel_projection = yes
        self._name_view(self.name_view)
        self.projection_changed.emit(yes)

    def _name_view(self, name: str) -> None:
        """The name of the view, at the top left of the 3D view («Front · Parallel»), and a notice to the button."""
        from ..language import tr
        change = name != self.name_view
        self.name_view = name
        text = f"{tr(name)} · {tr('Parallel') if self.view.camera.parallel_projection else tr('Perspective')}"
        ink = self._paper_y_ink()[1]
        self.view.add_text(text, position="upper_left", font_size=7, color=ink, name="_view_name",
                           font_file=str(VIEW_NAME_FONT) if VIEW_NAME_FONT.is_file() else None)
        self.view.render()
        if change:
            self.view_changed.emit(name)

    def put_background(self, color: str) -> None:
        """The background of the view (the theme's)."""
        self._theme_background = color
        self._apply_background()
        if self.style_name == "hidden lines":       # the paper of the hidden lines is the background
            self.put_style_name("hidden lines")
        self.drawing.repaint()            # the drawing grid and its points, with the colours of the new background
        self._name_view(self.name_view)   # the name of the view, with the colour of the new background
        self.view.render()

    def camera_sketch(self):
        """The camera of the view, in the form Croquis asks for."""
        from ..croquis import pyvista_camera
        width, height = self.size_()
        limits = np.array(self.view.bounds).reshape(3, 2).T
        return pyvista_camera(self.view.camera, width, height, limits)

    def size_(self) -> tuple[int, int]:
        """The size of the view in pixels of the image (with high-density screens, more than in Qt)."""
        return tuple(int(n) for n in self.view.window_size)

    def save_image(self, filepath, scale: int = 2, background: str | None = "white", axes: bool = False) -> tuple[int, int]:
        """Saves the view as it is seen (same framing), `scale` times bigger, in PNG.

        `background`: a colour («white», the usual; «#rrggbb»), «transparent» or None (that of the view). Returns the size in
        pixels.
        """
        return _snapshot(self.view, filepath, scale=scale, background=background, axes=axes, gizmo=self._gizmo)

    # Colours of the axes (the usual ones, in today's tones): X red, Y green, Z blue.
    COLOURS_AXES = {"x": (0.90, 0.28, 0.30), "y": (0.27, 0.65, 0.35), "z": (0.24, 0.39, 0.87)}

    def _create_gizmo(self):
        """The orientation of the view, at the top right: a circle per axis; on pressing it, the view looks from that
        axis."""
        gizmo = self.view.add_camera_orientation_widget(animate=True, n_frames=12)
        r = gizmo.GetRepresentation()
        r.AnchorToUpperRight()
        r.SetSize(GIZMO_PIXELS, GIZMO_PIXELS)
        r.SetHandleSize(22)
        r.SetPadding(8, 8) if hasattr(r, "SetPadding") else None
        for axis, color in self.COLOURS_AXES.items():
            getattr(r, f"Set{axis.upper()}AxisColor")(*color)
            getattr(r, f"Set{axis.upper()}PlusLabelText")(axis.upper())
            getattr(r, f"Set{axis.upper()}MinusLabelText")("")
        return gizmo

    def display_axes(self, yes: bool) -> None:
        self._gizmo.SetEnabled(bool(yes))
        LEGENDS["top"] = GIZMO_PIXELS if yes else 0
        arrange_legends(self.view)
        self.view.render()

    def visible_axes(self) -> bool:
        return bool(self._gizmo.GetEnabled())

    def dismiss(self) -> None:
        self.view.close()
