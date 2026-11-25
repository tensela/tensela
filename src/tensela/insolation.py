"""Insolation: the solar energy each face receives in a period, with what shades it.

The method is the cumulative sky of the environmental programs (what Ecotect calls the sky subdivision):

1. The sky is divided into patches (about 145 by default, in rings of altitude), each one a direction.
2. Hour by hour through the period, the sun: its position (sun.py) and how much it gives: with a weather file
   (climate.py), what was measured each hour; without it, a clear sky: the direct beam with Meinel's model (it
   weakens with the air mass, the air it crosses, Kasten and Young) and the whole horizontal with Haurwitz's; the
   diffuse is what the whole has beyond the beam, spread evenly over the sky. The direct energy of each hour goes to
   the patch where the sun is; the diffuse, to all.
3. Each face looks at each patch in front of it from its centre: if nothing is in the way (the obstructions or the
   faces themselves, through VTK's spatial index), it receives that patch's energy times the cosine of the angle
   (Lambert's law).

So the hours are summed once, in the sky, and the rays are cast only once per face and patch: a roof of 1500
panels takes seconds. It gives the energy in kWh/m² (total, direct or diffuse), the hours of sun, and the sky view
factor (how much sky a face sees, from 0 to 1). The ground does not reflect here (a light ground would add a little
on the walls).

Validated against itself: a horizontal face open to the sky receives the whole horizontal energy of the period.
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np

from . import sun as S
from .data import Data, ShapeError
from .language import tr

PERIODS = ('year', 'summer', 'winter', 'month', 'day')
SHOW = ('radiation', 'direct', 'diffuse', 'sun hours', 'sky view', 'faces')
SIDES = ('its face', 'the other face')
SOLAR_CONSTANT = 1367.0          # W/m², outside the air
MAXIMUM_RAYS = 400_000
_CACHE: OrderedDict = OrderedDict()
_CACHE_SIZE = 4


def sky_patches(n: int) -> tuple[np.ndarray, np.ndarray]:
    """About `n` patches over the sky, as the environmental programs divide it (Tregenza): rings of the same
    height in altitude, each split into an even number of patches of about the same size, and one patch at the
    zenith. Even and starting half a patch from the north, they are symmetric about the north-south and the
    east-west axes: a symmetric room gives symmetric results. Gives the direction of each patch (its middle) and its
    solid angle (they add up to the whole sky, 2π)."""
    bands = max(3, int(round(np.sqrt(n * 0.45))))
    width = np.radians(90.0) / (bands - 0.5)                  # the cap at the zenith is half as high
    directions, solids = [], []
    for k in range(bands - 1):
        low, high = k * width, (k + 1) * width
        ring = 2 * np.pi * (np.sin(high) - np.sin(low))
        count = max(2, 2 * int(round(n * ring / (2 * np.pi) / 2)))
        middle = 0.5 * (low + high)
        azimuth = (np.arange(count) + 0.5) * 2 * np.pi / count
        directions.append(np.stack([np.cos(middle) * np.sin(azimuth), np.cos(middle) * np.cos(azimuth),
                                    np.full(count, np.sin(middle))], 1))
        solids.append(np.full(count, ring / count))
    cap = 2 * np.pi * (1 - np.sin((bands - 1) * width))
    directions.append(np.array([[0.0, 0.0, 1.0]]))
    solids.append(np.array([cap]))
    return np.concatenate(directions), np.concatenate(solids)


def _days(period: str, month: int, day: int, latitude: float) -> tuple[np.ndarray, np.ndarray]:
    """The (day, month) of each day of the period. Summer and winter: the three months around the solstice, in the
    hemisphere of the place."""
    starts = np.cumsum((0,) + S.DAYS_IN_MONTH)
    every = np.arange(365)
    months = np.searchsorted(starts, every, side="right")
    days = every - starts[months - 1] + 1
    if period == 'year':
        keep = np.ones(365, bool)
    elif period in ('summer', 'winter'):
        northern_summer = (period == 'summer') == (latitude >= 0)
        keep = np.isin(months, (6, 7, 8) if northern_summer else (12, 1, 2))
    elif period == 'month':
        keep = months == month
    else:
        keep = (months == month) & (days == day)
    return days[keep], months[keep]


def clear_sky(altitude: np.ndarray, day_of_year: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The direct normal and the diffuse horizontal irradiance of a clear sky, in W/m² (0 with the sun down)."""
    up = altitude > 0.5
    zenith = np.radians(90.0 - np.where(up, altitude, 45.0))
    cos_z = np.cos(zenith)
    air_mass = 1.0 / (cos_z + 0.50572 * (96.07995 - np.degrees(zenith)) ** -1.6364)
    outside = SOLAR_CONSTANT * (1 + 0.033 * np.cos(2 * np.pi * day_of_year / 365.0))
    direct = outside * 0.7 ** (air_mass ** 0.678)
    whole = 1098.0 * cos_z * np.exp(-0.057 / cos_z)
    diffuse = np.maximum(whole - direct * cos_z, 0.05 * whole)
    return np.where(up, direct, 0.0), np.where(up, diffuse, 0.0)


def cumulative_sky(location, latitude, longitude, time_zone, period, month, day, from_hour, to_hour, north, patches,
                   climate=None):
    """The energy of each patch of the sky over the period, in Wh/m² facing it: (directions, direct, diffuse, hours
    of sun in each patch, the horizontal whole of the period). With a `climate` (climate.read), its place and the
    measured sun of each hour; without it, a clear sky."""
    if climate is not None:
        lat, lon, zone = climate["latitude"], climate["longitude"], climate["time zone"]
    else:
        lat, lon, zone = S.place(location, latitude, longitude, time_zone)
    d, m = _days(period, int(month), int(day), lat)
    if not len(d):
        raise ShapeError(tr('The period has no days: check the month and the day.'))
    hours = np.arange(np.floor(from_hour), np.ceil(to_hour)) + 0.5
    hours = hours[(hours > from_hour) & (hours < to_hour)]
    if not len(hours):
        raise ShapeError(tr('The hours go from «from hour» to «to hour», between 0 and 24, the first smaller.'))
    dd, hh = np.repeat(d, len(hours)), np.tile(hours, len(d))
    mm = np.repeat(m, len(hours))
    altitude, azimuth = S.position(lat, lon, zone, dd, mm, hh)
    start = np.cumsum((0,) + S.DAYS_IN_MONTH)
    doy = start[mm - 1] + dd
    if climate is not None:
        # The file's hour h goes from h − 1 to h: the one whose middle is each of these hours.
        row = (doy - 1) * 24 + (hh - 0.5).astype(int)
        direct_normal = np.asarray(climate["direct"], float)[row]
        diffuse_horizontal = np.asarray(climate["diffuse"], float)[row]
        direct_normal = np.where(altitude > 0.5, direct_normal, 0.0)     # the sun just rising: its beam is lost
    else:
        direct_normal, diffuse_horizontal = clear_sky(altitude, doy)
    directions, solid = sky_patches(int(patches))
    up = altitude > 0.5
    toward = S.towards(altitude[up], azimuth[up], north)
    nearest = np.argmax(toward @ directions.T, axis=1)
    direct = np.bincount(nearest, weights=direct_normal[up], minlength=len(directions))
    hours_of_sun = np.bincount(nearest, minlength=len(directions)).astype(float)
    # The diffuse, even over the sky; scaled so that a flat roof gets exactly the horizontal diffuse.
    diffuse = diffuse_horizontal.sum() * solid / (directions[:, 2] * solid).sum()
    horizontal = float((direct_normal * np.sin(np.radians(np.maximum(altitude, 0)))).sum() + diffuse_horizontal.sum())
    return directions, direct, diffuse, hours_of_sun, horizontal, solid


def _faces(faces):
    """The centre and the normal of each face, and the levels of the result: panels (each element) or the triangles
    of a mesh, a surface or a box (the list «face»)."""
    from . import geometry as geo
    from .meshes import _triangles
    if not isinstance(faces, Data) or faces.kind is None or faces.kind.faces is None:
        raise ShapeError(tr('Connect the faces: panels (a Grid), a mesh, a surface or a box.'))
    if faces.kind.name in (geo.RECTANGLE.name, "polygon"):
        normals = geo.normal(faces)
        centres = np.asarray(faces.values, float).mean(-2)
        return centres.reshape(-1, 3), np.asarray(normals.values, float).reshape(-1, 3), normals.levels, \
            normals.values.shape[:-1], _triangles(faces)
    t = _triangles(faces)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return t.mean(1), n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300), ("face",), (len(t),), t


def _seen(centres, normals, directions, blockers, stop=None) -> np.ndarray:
    """For each face and patch in front of it, whether the sky is open that way (faces × patches, yes or no)."""
    from . import vtk_light as vtk
    front = normals @ directions.T > 1e-9
    if blockers is None or not len(blockers):
        return front
    if int(front.sum()) > MAXIMUM_RAYS:
        raise ShapeError(tr('Too many faces ({n}) for the sky patches: use fewer cells, or fewer patches.').format(
            n=len(centres)))
    tree = vtk.ray_tree(blockers)
    size = float(np.ptp(np.concatenate([blockers.reshape(-1, 3), centres]), axis=0).max()) or 1.0
    gap, far = 1e-6 * size + 1e-9, 4 * size
    points, cells = vtk.vtkPoints(), vtk.vtkIdList()
    open_ = front.copy()
    for k, (c, n) in enumerate(zip(centres, normals)):
        if stop is not None and k % 64 == 0 and stop():
            from .graph import Cancelled
            raise Cancelled()
        start = c + n * gap
        for j in np.nonzero(front[k])[0]:
            d = directions[j]
            if tree.IntersectWithLine(start, start + d * far, 1e-9, points, cells):
                open_[k, j] = False
    return open_


def insolation(faces, obstructions=None, climate=None, location='Madrid', latitude=None, longitude=None, time_zone=None,
               period='year', month=6, day=21, from_hour=0.0, to_hour=24.0, side='its face', north=0.0,
               patches=145, show='radiation', name: str | None = None, stop=None) -> Data:
    """The node Insolation (see the module)."""
    from .meshes import kind_mesh
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    if period not in PERIODS:
        raise ShapeError(tr('The period must be one of: {options}.').format(options=", ".join(tr(o) for o in PERIODS)))
    if side not in SIDES:
        raise ShapeError(tr('The side must be one of: {options}.').format(options=", ".join(tr(o) for o in SIDES)))
    patches = int(patches)
    if not 16 <= patches <= 2000:
        raise ShapeError(tr('The sky patches go from 16 to 2000 (145 is the usual).'))
    centres, normals, levels, shape, triangles = _faces(faces)
    if show == 'faces':
        if levels != ("face",):
            raise ShapeError(tr('«faces» is for a mesh, a surface or a box: panels are painted as they are.'))
        return Data(triangles, ("face",), name, kind=kind_mesh([(0, 1, 2)]))
    if side == 'the other face':
        normals = -normals
    blockers = triangles
    if obstructions is not None:
        from .meshes import _triangles
        if not isinstance(obstructions, Data) or obstructions.kind is None or obstructions.kind.faces is None:
            raise ShapeError(tr('The obstructions must have faces: boxes, surfaces, meshes.'))
        blockers = np.concatenate([_triangles(obstructions), triangles])
    weather = None
    if climate is not None:
        from .climate import climate_of
        weather = climate_of(climate)
    key = (weather["file"] if weather else None, location, latitude, longitude, time_zone, period, int(month),
           int(day), float(from_hour), float(to_hour), side, float(north or 0.0), patches, centres.tobytes(),
           normals.tobytes(), blockers.tobytes())
    if key in _CACHE:
        _CACHE.move_to_end(key)
        sky, open_ = _CACHE[key]
    else:
        sky = cumulative_sky(location, latitude, longitude, time_zone, period, month, day, float(from_hour),
                             float(to_hour), float(north or 0.0), patches, weather)
        open_ = _seen(centres, normals, sky[0], blockers, stop)
        _CACHE[key] = sky, open_
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    directions, direct, diffuse, hours_of_sun, _, solid = sky
    cosine = np.clip(normals @ directions.T, 0, None) * open_
    if show == 'radiation':
        values = cosine @ (direct + diffuse) / 1000.0
    elif show == 'direct':
        values = cosine @ direct / 1000.0
    elif show == 'diffuse':
        values = cosine @ diffuse / 1000.0
    elif show == 'sun hours':
        values = (open_ & (cosine > 0)).astype(float) @ hours_of_sun
    else:
        values = cosine @ (solid / (directions[:, 2] * solid).sum())
    if show in ('radiation', 'direct', 'sun hours') and len(values) > 1 and not np.any(values > 0) and direct.sum() > 0:
        raise ShapeError(tr('No face gets any sun: do they face inwards (or down)? Try «side» on the other face, or '
                            'turn the surface with Flip surface before dividing it.'))
    values = values.reshape(shape)
    return Data(values, levels, name) if levels else Data(float(values), (), name)
