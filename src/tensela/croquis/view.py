"""Tensela's view as Croquis needs it: camera and geometry.

Croquis asks its host for a **camera** (where the eye is, where it looks, perspective or parallel, and its matrices)
and the **geometry to remove the hidden lines**: the triangles that cover, the «hard» edges (always drawn if they
are seen) and the «soft» ones (those of a curved surface: only drawn on its silhouette), each one with the normals of
its two faces.

The edges come from the kind of each geometry:

- between two faces on the same plane (the front of a frame made of four trapezoids) there is no line: a hand does
  not draw it;
- on a surface (grid of points) the inner edges are soft;
- the others (edges of a box, of a panel, of a frame) are hard;
- the curves are hard edges, without triangles (they cover nothing).

The transparent (opacity < 1, a glass) does not cover: its edges and what is behind are seen.
"""
from __future__ import annotations

import numpy as np

from ..data import Data

#: Two faces whose normals differ less than this (in degrees) are on the same plane.
COPLANAR_DEGREES = 1.0


class _Vector:
    """A point or a direction with Qt's form (x(), y(), z()), without Qt."""

    def __init__(self, v):
        self.v = np.asarray(v, dtype=np.float64)

    def x(self) -> float:
        return float(self.v[0])

    def y(self) -> float:
        return float(self.v[1])

    def z(self) -> float:
        return float(self.v[2])


class _Matrix:
    """A 4 × 4 matrix with QMatrix4x4's form (product and data() by columns), without Qt."""

    def __init__(self, m):
        self.m = np.asarray(m, dtype=np.float64)

    def __mul__(self, other: "_Matriz") -> "_Matriz":
        return _Matrix(self.m @ other.m)

    def data(self) -> list[float]:
        return self.m.flatten(order="F").tolist()


class Camera:
    """A camera with the form Croquis expects (Z up; matrices like OpenGL's).

    Only NumPy: it also works without an interface (the 2D DXF removes the hidden lines with it).
    """

    def __init__(self, eye, target, above, aspect: float, perspective: bool = True,
                 angle: float = 30.0, middle_height: float = 1.0, near: float = 0.1, far: float = 1000.0):
        self._eye = np.asarray(eye, dtype=np.float64)
        self._target = np.asarray(target, dtype=np.float64)
        f = self._target - self._eye
        self._ahead = f / np.linalg.norm(f)
        right = np.cross(self._ahead, np.asarray(above, dtype=np.float64))
        right /= np.linalg.norm(right)
        self._right = right
        self._above = np.cross(right, self._ahead)
        self.target = _Vector(self._target)
        self.aspect = float(aspect)
        self.perspective = bool(perspective)
        self.angle, self.middle_height = float(angle), float(middle_height)
        self.near, self.far = float(near), float(far)

    def eye(self) -> _Vector:
        return _Vector(self._eye)

    def forward(self) -> _Vector:
        return _Vector(self._ahead)

    def up_vector(self) -> _Vector:
        return _Vector(self._above)

    def view_matrix(self) -> _Matrix:
        r, u, f = self._right, self._above, self._ahead
        m = np.eye(4)
        m[0, :3], m[1, :3], m[2, :3] = r, u, -f
        m[:3, 3] = -m[:3, :3] @ self._eye
        return _Matrix(m)

    def projection_matrix(self) -> _Matrix:
        n, f = self.near, self.far
        m = np.zeros((4, 4))
        if self.perspective:
            t = 1.0 / np.tan(np.radians(self.angle) / 2)
            m[0, 0], m[1, 1] = t / self.aspect, t
            m[2, 2], m[2, 3] = -(f + n) / (f - n), -2 * f * n / (f - n)
            m[3, 2] = -1.0
        else:
            h = self.middle_height
            m[0, 0], m[1, 1] = 1.0 / (h * self.aspect), 1.0 / h
            m[2, 2], m[2, 3] = -2.0 / (f - n), -(f + n) / (f - n)
            m[3, 3] = 1.0
        return _Matrix(m)


def pyvista_camera(camera, width: int, height: int, limits=None) -> Camera:
    """The camera of the 3D view (pyvista/VTK) in Croquis's form."""
    eye = np.array(camera.position, dtype=float)
    target = np.array(camera.focal_point, dtype=float)
    distance = float(np.linalg.norm(target - eye))
    radius = distance
    if limits is not None:
        a, b = np.asarray(limits, dtype=float).reshape(2, 3)
        centre, radius = (a + b) / 2, max(float(np.linalg.norm(b - a)) / 2, 1e-6)
        distance = float(np.linalg.norm(centre - eye))
    near = max(distance - radius * 1.5, distance * 1e-3, 1e-4)
    far = distance + radius * 1.5 + 1.0
    return Camera(eye, target, camera.up, width / max(height, 1),
                  perspective=not camera.parallel_projection, angle=camera.view_angle,
                  middle_height=camera.parallel_scale, near=near, far=far)


class Scene:
    """The little Croquis looks at in the scene (without a version: it keeps no cache of colours)."""

    version = None


class SketchView:
    """A Tensela view for Croquis: `camera`, `scene`, `hlr_geometry()`."""

    def __init__(self, objects: list[tuple[str, Data, dict]], camera: Camera):
        self.camera = camera
        self.scene = Scene()
        tris, from_object, hard, soft, normals = [], [], [], [], []
        self.colours = []
        for k, (_name, data, style_name) in enumerate(objects):
            h = style_name.get("color", "#8a96a3").lstrip("#")
            self.colours.append(tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)))
            t, d, b, n = geometry_of(data)
            if float(style_name.get("opacity", 1.0)) >= 1.0:
                tris.append(t)
                from_object.append(np.full(len(t), k, dtype=np.int64))
            hard.append(d)
            soft.append(b)
            normals.append(n)
        self.tris = np.concatenate(tris) if tris else np.empty((0, 3, 3))
        self.from_object = np.concatenate(from_object) if from_object else np.empty(0, dtype=np.int64)
        self._hard = np.concatenate(hard) if hard else np.empty((0, 2, 3))
        self._soft = np.concatenate(soft) if soft else np.empty((0, 2, 3))
        self._normals = np.concatenate(normals) if normals else np.empty((0, 2, 3))

    def hlr_geometry(self):
        return self.tris, self._hard, self._soft, self._normals


def geometry_of(data: Data):
    """(triangles, hard edges, soft edges, normals of the soft ones) of a data."""
    empty = np.empty((0, 3, 3)), np.empty((0, 2, 3)), np.empty((0, 2, 3)), np.empty((0, 2, 3))
    if data.kind is None:
        return empty
    v = data.values[data.mask] if data.levels else data.values[None]     # pieces × vertices × 3
    if data.kind.curve:
        order = list(range(v.shape[1])) + ([0] if data.kind.closed else [])
        a, b = np.array(order[:-1]), np.array(order[1:])
        return empty[0], np.stack([v[:, a], v[:, b]], axis=2).reshape(-1, 2, 3), empty[2], empty[3]
    if data.kind.faces is None:                                               # points: nothing to draw
        return empty
    faces = data.kind.faces

    # Triangles as a fan of each face.
    tri_idx = np.array([(c[0], c[i], c[i + 1]) for c in faces for i in range(1, len(c) - 1)], dtype=int)
    tris = v[:, tri_idx].reshape(-1, 3, 3)

    # Normal of each face (Newell), in each piece.
    normals = np.zeros((v.shape[0], len(faces), 3))
    for k, c in enumerate(faces):
        p = v[:, list(c)]
        q = np.roll(p, -1, axis=1)
        normals[:, k] = np.cross(p, q).sum(axis=1)
    length = np.linalg.norm(normals, axis=-1, keepdims=True)
    normals = np.divide(normals, length, out=np.zeros_like(normals), where=length > 1e-12)

    # Which faces share each edge (the topology is the same in all the pieces).
    neighbours: dict[tuple[int, int], list[int]] = {}
    for k, c in enumerate(faces):
        for i in range(len(c)):
            neighbours.setdefault(tuple(sorted((c[i], c[(i + 1) % len(c)]))), []).append(k)
    surface = data.kind.grid is not None
    threshold = np.cos(np.radians(COPLANAR_DEGREES))
    hard, soft, n_soft = [], [], []
    for (a, b), fs in neighbours.items():
        run = np.stack([v[:, a], v[:, b]], axis=1)                          # piezas × 2 × 3
        if len(fs) != 2:                                                      # an edge, or an odd edge
            hard.append(run)
            continue
        na, nb = normals[:, fs[0]], normals[:, fs[1]]
        cosine = np.abs(np.einsum("ij,ij->i", na, nb))
        plane = cosine >= threshold                                              # same plane: without a line
        if surface:
            soft.append(run[~plane])
            n_soft.append(np.stack([na, nb], axis=1)[~plane])
            # On a surface, a fold on the same plane is not drawn either.
        else:
            hard.append(run[~plane])
    def join(parts, shape=(0, 2, 3)):
        return np.concatenate(parts) if parts else np.empty(shape)
    hard = join(hard)
    if getattr(data.kind, "polygon", False):          # polygons: without the zero-length edges of the padding
        hard = hard[np.linalg.norm(hard[:, 1] - hard[:, 0], axis=-1) > 1e-9]
    return tris, hard, join(soft), join(n_soft)
