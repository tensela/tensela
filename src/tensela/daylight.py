"""Daylight: how much of the light of an overcast sky reaches some points inside.

The daylight factor of a point is the illuminance there, as a percentage of the illuminance outside under an open,
overcast sky. It is the usual measure of natural light in a room: about 2 % reads as a lit room, 5 % as a bright
one. Times the illuminance of the sky (in lux, by the latitude: see `sky_illuminance`), it gives the lux.

It is the sum of two parts, as the manuals compute it:

- **The sky component**: the light that comes straight from the sky. The sky is the CIE overcast sky (three times
  brighter at the zenith than at the horizon: (1 + 2 sin θ) / 3). From each point, a ray towards each patch of the
  sky; if it reaches the sky through the windows (and nothing opaque is in the way: walls, louvers, neighbours) it
  counts that patch's light times the cosine on the horizontal work plane, times the transmittance of each glass it
  crosses.
- **The internally reflected component**: the light that comes in and bounces on the walls, floor and ceiling. With
  the BRE split-flux formula: IRC = τ W (C R + 5 R) / (A (1 − R̄)), with W the area of glass, A the area of all the
  room's surfaces, R their reflectance, R̄ the average with the glass, and C = 39 (an open sky in front). It is the
  same everywhere in the room.

The room can be a whole box: where a window lies on one of its walls, the glass opens the wall (the opaque face at
the same place as a glass is not counted). The light that the outside obstructions reflect is not counted (it
errs on the dark side).
"""
from __future__ import annotations

from collections import OrderedDict

from functools import lru_cache

import numpy as np

from . import sun as S
from .data import Data, ShapeError
from .insolation import sky_patches
from .language import tr

SHOW = ('daylight factor', 'illuminance', 'sky component', 'average illuminance', 'average daylight factor',
        'uniformity')
GLASS_REFLECTANCE = 0.1
_ROOM_CACHE: "OrderedDict" = OrderedDict()
C_OPEN_SKY = 39.0


@lru_cache(maxsize=64)
def sky_illuminance(latitude: float) -> float:
    """The design illuminance of the overcast sky at a latitude, in lux: the one exceeded during 85 % of the working
    hours of the year (9 to 17 h, solar time), the usual definition of the design sky.

    The horizontal illuminance of the CIE overcast sky follows the height of the sun (Krochmann and Seidl):
    E = 300 + 21 000 · sin(altitude) lux. The altitude, every quarter of an hour of every day, with the declination
    of the day; the value is the 15th percentile of them. Near the equator it gives about 10 800 lux, at 45° about
    6100, at 60° about 2000. It is an estimate: the project can give its own value instead.
    """
    days = np.arange(1, 366)
    hours = np.arange(9.0, 17.0001, 0.25)
    declination = np.radians(23.44) * np.sin(2 * np.pi * (284 + days) / 365.0)
    angle = np.radians(15.0 * (hours - 12.0))
    phi = np.radians(abs(float(latitude)))
    sine = (np.sin(phi) * np.sin(declination)[:, None]
            + np.cos(phi) * np.cos(declination)[:, None] * np.cos(angle)[None, :])
    return float(np.percentile(300.0 + 21000.0 * np.clip(sine, 0.0, 1.0), 15))


def _triangles_of(data, what: str) -> np.ndarray:
    from .meshes import _triangles
    if data is None:
        return np.zeros((0, 3, 3))
    if not isinstance(data, Data) or data.kind is None or data.kind.faces is None:
        raise ShapeError(tr('“{what}” must have faces: boxes, rectangles, surfaces or meshes.').format(what=tr(what)))
    return _triangles(data)


def _area(t: np.ndarray) -> float:
    return float(0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum()) if len(t) else 0.0


def _tree(triangles: np.ndarray):
    """VTK's spatial index over some triangles (k, 3, 3)."""
    from . import vtk_light as vtk
    tree = vtk.ray_tree(triangles)
    return tree


def _through_the_room(points: np.ndarray, room: np.ndarray, glass: np.ndarray, transmittance: float,
                      directions: np.ndarray, far: float, close: float) -> np.ndarray:
    """For each point and sky patch, what the room lets through that way: 1 the open sky, the transmittance of each
    glass crossed, 0 a wall (points × patches). Kept for the same room, windows and points: while the louvers change
    (Find the best…), only they are looked at again."""
    from . import vtk_light as vtk
    key = (points.tobytes(), room.tobytes(), glass.tobytes(), float(transmittance), directions.tobytes(), far)
    if key in _ROOM_CACHE:
        _ROOM_CACHE.move_to_end(key)
        return _ROOM_CACHE[key]
    through = np.ones((len(points), len(directions)))
    everything = np.concatenate([room, glass])
    if len(everything):
        kind = np.concatenate([np.zeros(len(room), int), np.ones(len(glass), int)])
        tree = _tree(everything)
        hits, cells = vtk.vtkPoints(), vtk.vtkIdList()
        for k, p in enumerate(points):
            for j, d in enumerate(directions):
                hits.Reset()
                cells.Reset()
                if not tree.IntersectWithLine(p, p + d * far, 1e-9, hits, cells):
                    continue                                 # the open sky
                n = hits.GetNumberOfPoints()
                distance = np.array([np.linalg.norm(np.array(hits.GetPoint(i)) - p) for i in range(n)])
                what = kind[[cells.GetId(i) for i in range(n)]]
                glass_at, opaque_at = distance[what == 1], distance[what == 0]
                if len(glass_at):                            # a wall where a glass lies: the glass opens it
                    opaque_at = opaque_at[np.abs(opaque_at[:, None] - glass_at[None, :]).min(1) > close]
                if len(opaque_at):
                    through[k, j] = 0.0
                    continue
                # Each glass crossed (a triangle edge can be hit twice: the same place counts once).
                through[k, j] = transmittance ** len(np.unique(np.round(glass_at / close)))
    _ROOM_CACHE[key] = through
    while len(_ROOM_CACHE) > 4:
        _ROOM_CACHE.popitem(last=False)
    return through


def sky_component(points: np.ndarray, room: np.ndarray, glass: np.ndarray, outside: np.ndarray, transmittance: float,
                  patches: int) -> np.ndarray:
    """The sky component of each point, in % (see the module)."""
    from . import vtk_light as vtk
    directions, solid = sky_patches(patches)
    weight = (1 + 2 * directions[:, 2]) / 3 * directions[:, 2] * solid
    weight = weight / weight.sum()                            # the open sky, exactly 100 %
    allp = np.concatenate([room.reshape(-1, 3), glass.reshape(-1, 3), outside.reshape(-1, 3), points])
    size = float(np.ptp(allp, axis=0).max()) or 1.0
    far, close = 4 * size, 1e-4 * size                      # a glass and a wall closer than this: the glass opens it
    through = _through_the_room(points, room, glass, transmittance, directions, far, close)
    if len(outside):                                          # what blocks outside: only the rays that got out
        tree = _tree(outside)
        hits, cells = vtk.vtkPoints(), vtk.vtkIdList()
        through = through.copy()
        for k, j in zip(*np.nonzero(through)):
            p = points[k]
            if tree.IntersectWithLine(p, p + directions[j] * far, 1e-9, hits, cells):
                through[k, j] = 0.0
    return 100.0 * through @ weight


def reflected_component(room: np.ndarray, glass: np.ndarray, transmittance: float, reflectance: float) -> float:
    """The internally reflected component, in %, the same for the whole room (the BRE split-flux formula)."""
    window, surfaces = _area(glass), _area(room)
    if window <= 0 or surfaces <= 0:
        return 0.0
    whole = max(surfaces, window)
    average = (reflectance * (whole - window) + GLASS_REFLECTANCE * window) / whole
    return transmittance * window * (C_OPEN_SKY * reflectance + 5 * reflectance) / (whole * (1 - average))


def daylight(points, room=None, glass=None, obstructions=None, transmittance=70.0, reflectance=50.0,
             location='Madrid', latitude=None, longitude=None, time_zone=None, sky_lux=0.0, patches=290,
             show='daylight factor', name: str | None = None) -> Data:
    """The node Daylight (see the module)."""
    from .geometry import POINT
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    if not isinstance(points, Data) or points.kind is None or points.kind.name != POINT.name:
        raise ShapeError(tr('Connect the points where the light is measured (a grid of points at the height of a '
                            'desk).'))
    tau, rho = float(transmittance) / 100.0, float(reflectance) / 100.0
    if not 0 <= tau <= 1:
        raise ShapeError(tr('The transmittance goes from 0 to 100 %.'))
    if not 0 <= rho < 1:
        raise ShapeError(tr('The reflectance goes from 0 to 99 %.'))
    patches = int(patches)
    if not 32 <= patches <= 4000:
        raise ShapeError(tr('The sky patches go from 32 to 4000 (290 is the usual here).'))
    p = np.asarray(points.values, float).reshape(-1, 3)
    if len(p) * patches > 600_000:
        raise ShapeError(tr('Too many points ({n}) for the sky patches: use fewer points, or fewer patches.').format(
            n=len(p)))
    room_t, glass_t = _triangles_of(room, 'room'), _triangles_of(glass, 'glass')
    outside_t = _triangles_of(obstructions, 'obstructions')
    sky = sky_component(p, room_t, glass_t, outside_t, tau, patches)
    factor = sky + reflected_component(room_t, glass_t, tau, rho)
    if show == 'average daylight factor':
        return Data(float(factor.mean()), (), name)
    if show == 'uniformity':                                  # the darkest point over the average
        return Data(float(factor.min() / factor.mean()) if factor.mean() > 0 else 0.0, (), name)
    if show in ('illuminance', 'average illuminance'):
        lat = S.place(location, latitude, longitude, time_zone)[0]
        lux = float(sky_lux) if sky_lux and float(sky_lux) > 0 else sky_illuminance(lat)
        values = factor / 100.0 * lux
        if show == 'average illuminance':
            return Data(float(values.mean()), (), name)
    else:
        values = sky if show == 'sky component' else factor
    if not points.levels:
        return Data(float(values[0]), (), name)
    return Data(values.reshape(np.asarray(points.values).shape[:-1]), points.levels, name)
