"""Shadows: the shadow of some geometry with the sun's ray, on the ground or on other surfaces.

On the ground (a horizontal plane at a height) the shadow is exact: each triangle of the geometry is carried along
the ray down to the plane, and the union of all of them (manifold3d's CrossSection, which joins overlapping
polygons) is the shadow, with its holes: the outlines, the area, and the filled region as a flat mesh. What goes
below the ground does not cast.

On other surfaces (a terrain, a façade, another building) each face of the receiving surfaces looks towards the sun
from its centre: if something is in the way (the geometry, or the surfaces themselves) it is in shadow. So the shadow
is as fine as those faces: a Mesh surface with many cells gives a detailed one. The rays go through VTK's spatial
index (vtkModifiedBSPTree): each one only tries the triangles near its path.

With several rays (the Sun with a list of hours) the shadows add up: on the ground, the shadows of all the hours (and
the area of each one); on the surfaces, «in shadow» is the part of those hours that each face is in shadow.
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError
from .geometry import ARROW, CLOSED_CURVE, VECTOR
from .language import tr
from .meshes import _triangles, kind_mesh

SHOW = ('shadow', 'outline', 'area', 'sunlit', 'in shadow', 'faces')
ON_GROUND = ('shadow', 'outline', 'area')                    # what «show» offers on the ground…
ON_SURFACES = ('shadow', 'sunlit', 'in shadow', 'faces')     # …and on surfaces
_MM = 1000.0                    # the 2D union works in millimetres, as whole numbers are kinder to it


def rays_of(ray) -> np.ndarray:
    """The directions of the light (k, 3), unit: from the Sun's «ray» (vectors) or its «beam» (arrows)."""
    if not isinstance(ray, Data) or ray.kind is None or ray.kind.name not in (VECTOR.name, ARROW.name):
        raise ShapeError(tr('Connect the ray of a Sun (its «show» on ray or beam): the way the light goes.'))
    v = np.asarray(ray.values, dtype=float)
    v = v.reshape(-1, 2, 3)[:, 1] - v.reshape(-1, 2, 3)[:, 0] if ray.kind.name == ARROW.name else v.reshape(-1, 3)
    length = np.linalg.norm(v, axis=1)
    if np.any(length < 1e-12):
        raise ShapeError(tr('The ray cannot be zero.'))
    return v / length[:, None]


def _faces(geometry, what: str) -> np.ndarray:
    if not isinstance(geometry, Data):
        raise ShapeError(tr('Connect “{what}”: a box, a surface or a mesh.').format(what=tr(what)))
    t = _triangles(geometry)
    if not len(t):
        raise ShapeError(tr('“{what}” has no faces.').format(what=tr(what)))
    return t


def _above(triangles: np.ndarray, height: float) -> list[np.ndarray]:
    """The triangles cut by the ground: only what is above it (a triangle crossing it leaves a triangle or a
    four-sided piece)."""
    z = triangles[..., 2] - height
    keep = list(triangles[(z >= -1e-12).all(1)])
    for t, d in zip(triangles[((z < -1e-12).any(1)) & ((z > 1e-12).any(1))], z[((z < -1e-12).any(1))
                                                                                & ((z > 1e-12).any(1))]):
        piece = []
        for i in range(3):
            a, b, da, db = t[i], t[(i + 1) % 3], d[i], d[(i + 1) % 3]
            if da >= 0:
                piece.append(a)
            if (da >= 0) != (db >= 0):
                piece.append(a + (b - a) * (da / (da - db)))
        for j in range(1, len(piece) - 1):
            keep.append(np.array([piece[0], piece[j], piece[j + 1]]))
    return keep


def ground_shadow(triangles: np.ndarray, ray: np.ndarray, height: float):
    """The shadow on the ground of one ray: (its outlines as rings in the plane, the area, the filled triangles)."""
    from manifold3d import CrossSection, FillRule
    if ray[2] > -1e-6:                                         # the sun is down (night): no shadow of its own
        return [], 0.0, np.zeros((0, 3, 3))
    contours = []
    for t in _above(triangles, height):
        p = t[:, :2] + ray[None, :2] * ((height - t[:, 2]) / ray[2])[:, None]
        area = 0.5 * ((p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1]))
        if abs(area) < 1e-10:
            continue                                         # a face seen edge-on by the sun: no shadow of its own
        contours.append((p if area > 0 else p[::-1]) * _MM)
    if not contours:
        return [], 0.0, np.zeros((0, 3, 3))
    region = CrossSection(contours, FillRule.NonZero)          # overlapping triangles: one region, with its holes
    rings = [np.asarray(r, float) / _MM for r in region.to_polygons() if len(r) >= 3]
    mesh = region.extrude(1.0).to_mesh()
    vertices = np.asarray(mesh.vert_properties, float)[:, :3]
    tris = np.asarray(mesh.tri_verts)
    bottom = tris[(np.abs(vertices[tris][:, :, 2]) < 1e-9).all(1)][:, ::-1]   # the lower face, turned to look up
    filled = vertices[bottom].copy()
    filled[..., :2] /= _MM
    filled[..., 2] = height
    return rings, region.area() / _MM ** 2, filled


def shaded_faces(receivers: np.ndarray, casters: np.ndarray, rays: np.ndarray) -> np.ndarray:
    """For each face of the receivers (k, 3, 3), the part of the rays for which something stands between its centre
    and the sun (the casters or the receivers themselves)."""
    from . import vtk_light as vtk
    everything = np.concatenate([casters, receivers])
    tree = vtk.ray_tree(everything)
    size = float(np.ptp(everything.reshape(-1, 3), axis=0).max()) or 1.0
    centres = receivers.mean(1)
    gap = 1e-6 * size + 1e-9
    points, cells = vtk.vtkPoints(), vtk.vtkIdList()
    shade = np.zeros(len(receivers))
    for ray in rays:
        if ray[2] > -1e-6:                                    # the sun below the horizon: everything in shadow
            shade += 1
            continue
        towards = -ray
        for k, c in enumerate(centres):
            start = c + towards * gap
            if tree.IntersectWithLine(start, start + towards * 4 * size, 1e-9, points, cells):
                shade[k] += 1
    return shade / len(rays)


def shadow(geometry, ray, ground=0.0, surfaces=None, show='shadow', name: str | None = None) -> Data:
    """The node Shadow (see the module)."""
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    casters = _faces(geometry, 'geometry')
    rays = rays_of(ray)
    if surfaces is not None:                                  # on other surfaces: face by face
        if show in ('outline', 'area'):
            raise ShapeError(tr('«outline» and «area» are for the shadow on the ground (without surfaces).'))
        receivers = _faces(surfaces, 'surfaces')
        if show == 'faces':                 # each face an element of the list «face», painted by «in shadow»
            out = Data(receivers, ("face",), name, kind=kind_mesh([(0, 1, 2)]))
            out.paint = (shaded_faces(receivers, casters, rays), "light to dark")
            return out
        if len(receivers) * len(rays) > 400000:
            raise ShapeError(tr('Too many faces and hours ({n}): use fewer cells in the surfaces, or fewer '
                                'hours.').format(n=len(receivers) * len(rays)))
        shade = shaded_faces(receivers, casters, rays)
        if show == 'in shadow':
            return Data(shade, ("face",), name)
        which = receivers[shade > 0] if show == 'shadow' else receivers[shade == 0]
        # Lifted a hair towards the sun (a thousandth of the size): on the very face of the surface, the screen
        # would not know which of the two to show.
        lift = -rays.mean(0) * 1e-3 * float(np.ptp(receivers.reshape(-1, 3), axis=0).max())
        return _flat_mesh(which + lift, name, shade=show == 'shadow')
    if show in ('sunlit', 'in shadow', 'faces'):
        raise ShapeError(tr('«sunlit», «in shadow» and «faces» are for the shadow on surfaces: connect them.'))
    height = float(ground.values if isinstance(ground, Data) else (ground or 0.0))
    results = [ground_shadow(casters, r, height) for r in rays]
    if show == 'area':
        areas = np.array([a for _, a, _ in results])
        return Data(areas, ("sun",), name) if len(areas) > 1 else Data(float(areas[0]), (), name)
    if show == 'outline':
        from .fabrication import _padded
        rings = [np.column_stack([r, np.full(len(r), height)]) for res in results for r in res[0]]
        if not rings:
            raise ShapeError(tr('There is no shadow at that hour (the sun is down, or the geometry is below the '
                                'ground).'))
        return Data(_padded(rings), ("outline",), name, kind=CLOSED_CURVE) if len(rings) > 1 else \
            Data(rings[0], (), name, kind=CLOSED_CURVE)
    return _flat_mesh(np.concatenate([f for _, _, f in results]), name)


def _flat_mesh(triangles: np.ndarray, name, shade: bool = True) -> Data:
    """Triangles (k, 3, 3) as one mesh; none at all is an empty mesh (with the ▶, an hour without shadow does not
    turn the node red)."""
    out = Data(triangles.reshape(-1, 3), (), name, kind=kind_mesh(np.arange(3 * len(triangles)).reshape(-1, 3)))
    out.shade = shade                    # a shadow: the view keeps its colour in every style (a white model too)
    return out
