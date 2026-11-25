"""The look of the 3D view in the Studio and Model styles.

- **Studio** (the usual style): each object with its own colour, as a matte physical material lit by a soft sky; a
  key light, a fill from the camera and a back light; the corners and the openings a little darker (occlusion);
  thin outlines at the silhouettes and the sharp edges; a soft gradient behind.
- **Model**: everything white, on a light background, with the same outlines and occlusion: like an architect's
  model in foam board, to look at the form without its colours.

The sky is drawn by the program (six small images in memory), so there are no files to install. It is prepared
once, the first time the view is painted.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pyvista as pv
import vtk

#: The colour of everything in the Model style, and its background (bottom and top of the gradient).
MODEL_COLOUR = "#f3f1ec"
MODEL_BACKGROUND = ("#e6e4df", "#f8f7f4")
#: The outlines: a soft grey that goes with the form without marking it too much (a little darker on a light
#: background), half transparent.
OUTLINE_DARK, OUTLINE_LIGHT = "#4a4d55", "#3a3d45"
OUTLINE_OPACITY = 0.55
#: The borders of the cells of a grid (panels, a honeycomb): firmer than the outlines, so the grid reads (test 54).
CELLS_OPACITY, CELLS_WIDTH, CELLS_DARK = 0.9, 1.5, "#2a2d33"
#: A mesh with up to this many faces shows all its edges in Studio and Model (its topology); a bigger one, only
#: its outlines.
MESH_EDGES_LIMIT = 1500
#: Above this many faces the outlines are fixed (borders and sharp edges, computed once) instead of the silhouette
#: that follows the camera: on a big mesh it would slow every move.
OUTLINE_STATIC_ABOVE = 20_000
#: Edges sharper than this (degrees between faces) are outlined too, not only the silhouette.
OUTLINE_ANGLE = 40.0
#: The radius of the occlusion, as a share of the size of what is seen.
OCCLUSION_SHARE = {"solid": 0.025, "model": 0.04}


@lru_cache(maxsize=1)
def _sky_faces(size: int = 128) -> tuple[np.ndarray, ...]:
    """The six faces of the sky (posx, negx, posy, negy, posz, negz): bright above, a light horizon, a darker
    ground and a broad warm glow where the key light comes from."""
    faces = (lambda a, b: (np.ones_like(a), -b, -a), lambda a, b: (-np.ones_like(a), -b, a),
             lambda a, b: (a, np.ones_like(a), b), lambda a, b: (a, -np.ones_like(a), -b),
             lambda a, b: (a, -b, np.ones_like(a)), lambda a, b: (-a, -b, -np.ones_like(a)))
    t = np.linspace(-1, 1, size)
    a, b = np.meshgrid(t, t)
    key = np.array([-0.5, -0.6, 0.62])
    key /= np.linalg.norm(key)
    out = []
    for face in faces:
        x, y, z = face(a, b)
        n = np.sqrt(x * x + y * y + z * z)
        x, y, z = x / n, y / n, z / n
        sky, ground = np.clip(z, 0, 1), np.clip(-z, 0, 1)
        base = 0.85 + 0.35 * sky ** 0.7 - 0.20 * ground
        glow = np.clip(x * key[0] + y * key[1] + z * key[2], 0, 1) ** 10 * 1.2
        rgb = np.stack([base + glow, base * 0.99 + glow * 0.95, base * 1.02 + glow * 0.85], axis=-1)
        out.append((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    return tuple(out)


def sky_texture() -> pv.Texture:
    """The sky as a cube map, for the physical materials to take their light from it."""
    texture = pv.Texture()
    texture.mipmap = True
    texture.interpolate = True
    texture.color_mode = "direct"
    texture.cube_map = True                         # before the images
    for i, face in enumerate(_sky_faces()):
        h, w, _ = face.shape
        image = pv.ImageData(dimensions=(w, h, 1))
        image.point_data["sky"] = face.reshape(-1, 3)
        texture.SetInputDataObject(i, image)
    return texture


def put_sky(plotter: pv.Plotter) -> None:
    """The sky lights the physical materials; it is not shown behind (the background stays the theme's)."""
    try:
        plotter.set_environment_texture(sky_texture(), is_srgb=True, resample=1.0, show_background=False)
    except Exception:                                # an old graphics driver: the materials are lit by the lamps alone
        pass


def put_lights(plotter: pv.Plotter, style: str) -> None:
    """A key light from front-left-above, a fill from the camera, a back light that separates the object from the
    background, and a soft bounce from below (the light the floor gives back): the faces that look down, under a skin
    or a slab, do not go black. Model: softer and more even (a white model in a bright room)."""
    key, fill, back, bounce = (0.95, 0.3, 0.28, 0.25) if style == "model" else (1.4, 0.3, 0.35, 0.45)
    plotter.remove_all_lights()
    k = pv.Light(light_type="scene light", intensity=key)
    k.position, k.focal_point = (-0.6, -0.9, 1.3), (0, 0, 0)
    k.positional = False
    b = pv.Light(light_type="scene light", intensity=back)
    b.position, b.focal_point = (0.7, 0.9, 0.8), (0, 0, 0)
    b.positional = False
    u = pv.Light(light_type="scene light", intensity=bounce)
    u.position, u.focal_point = (0.3, -0.4, -1.0), (0, 0, 0)
    u.positional = False
    f = pv.Light(light_type="headlight", intensity=fill)
    for light in (k, f, b, u):
        plotter.add_light(light)


def material(style: str) -> dict:
    """How a face is painted in Studio (a matte physical material) or Model (matte white)."""
    if style == "model":
        return dict(ambient=0.2, diffuse=0.78, specular=0.04)
    return dict(pbr=True, metallic=0.0, roughness=0.55)


def add_back_faces(plotter: pv.Plotter, name: str, actor, mesh: pv.PolyData) -> None:
    """The physical material does not draw the back of a face; an open surface (a skin, the sides of a frustum, a
    wall) is seen from both sides. So each surface is drawn twice: its front with the Studio material (the backs
    hidden) and its back with a usual matte material a little darker (the fronts hidden). A face turned over reads
    darker than its neighbours: the way to see that a mesh is not orientable."""
    actor.prop.backface_culling = True
    mapper = pv.DataSetMapper()
    mapper.ShallowCopy(actor.mapper)                  # the same colours (also when painted by a value)
    mapper.SetInputData(mesh)
    back = pv.Actor(mapper=mapper)
    c = np.array(actor.prop.color.float_rgb) * 0.72
    back.prop.color = tuple(c)
    back.prop.opacity = actor.prop.opacity
    back.prop.ambient, back.prop.diffuse, back.prop.specular = 0.35, 0.7, 0.03
    back.prop.interpolation = "phong" if actor.prop.interpolation != "Flat" else "flat"
    back.prop.frontface_culling = True
    back.pickable = False
    back.mapper.SetResolveCoincidentTopologyToPolygonOffset()
    plotter.add_actor(back, name=back_name(name), reset_camera=False, pickable=False)


def back_name(name: str) -> str:
    return name + "·back"


def add_outline(plotter: pv.Plotter, name: str, mesh: pv.PolyData, light_background: bool,
                opacity: float = 1.0, cells: bool = False):
    """The thin lines at the silhouette (they follow the camera) and at the sharp edges of a mesh. `cells`: a grid of
    panels (rectangles, hexagons): the border of each cell, firmer, so the grid reads."""
    if mesh.n_cells == 0:
        return None
    mapper = pv.DataSetMapper()
    if mesh.n_cells > OUTLINE_STATIC_ABOVE:
        # A big mesh (a smoothed skin): the silhouette, which follows the camera, would be computed again at every
        # move. Its borders and sharp edges, once: on a smooth form they are what matters.
        edges = mesh.extract_feature_edges(feature_angle=OUTLINE_ANGLE, boundary_edges=True, feature_edges=True,
                                           manifold_edges=False, non_manifold_edges=False)
        if edges.n_cells == 0:
            return None
        mapper.SetInputData(edges)
    else:
        alg = vtk.vtkPolyDataSilhouette()
        alg.SetInputData(mesh)
        alg.SetCamera(plotter.renderer.camera)
        alg.SetEnableFeatureAngle(True)
        alg.SetFeatureAngle(OUTLINE_ANGLE)
        alg.SetBorderEdges(True)                     # the outline of each panel of a grid
        mapper.SetInputConnection(alg.GetOutputPort())
    actor = pv.Actor(mapper=mapper)
    actor.prop.color = (CELLS_DARK if cells else OUTLINE_DARK) if light_background else OUTLINE_LIGHT
    actor.prop.line_width = CELLS_WIDTH if cells else 1.0
    actor.prop.opacity = min(1.0, opacity) * (CELLS_OPACITY if cells else OUTLINE_OPACITY)
    actor.prop.lighting = False
    actor.pickable = False
    mapper.SetResolveCoincidentTopologyToPolygonOffset()
    mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-1.0, -30.0)
    plotter.add_actor(actor, name=outline_name(name), reset_camera=False, pickable=False)
    return actor


def outline_name(name: str) -> str:
    return name + "·outline"


def lighter(colour: str, amount: float = 0.09) -> str:
    """The same colour, a little lighter: the top of the gradient behind."""
    c = np.array(pv.Color(colour).float_rgb)
    c = c + (1 - c) * amount
    return pv.Color(tuple(c)).hex_rgb
