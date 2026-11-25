"""The sun: where it is for a place, a day and an hour, and its path.

The position comes from the formulas of the NOAA (the solar calculator of the National Oceanic and Atmospheric
Administration, after Jean Meeus' «Astronomical Algorithms»): the declination and the equation of time for the day,
the hour angle for the hour, and from them the altitude (with the refraction of the air near the horizon) and the
azimuth. A hundredth of a degree off, far below what a design needs. No weather file is needed for this.

The hour is the local standard time of the place, without summer time. The year is a common one (2026): from one year
to another the sun changes by less than what can be drawn.

In Tensela the north is +Y and the east +X; `north` turns the north counterclockwise from +Y, for a project that
is not drawn with the north up. The ray is the way the light goes, from the sun to the ground (the solar ray vector):
the faces that look at the sun have their normal against it.
"""
from __future__ import annotations

import math

import numpy as np

from .data import Data, ShapeError
from .geometry import ARROW, CURVE, POINT, VECTOR
from .language import tr

#: A few cities: (latitude, longitude, time zone without summer time). Latitude + north; longitude + east.
CITIES = {
    'Madrid': (40.42, -3.70, 1.0),
    'Barcelona': (41.39, 2.17, 1.0),
    'Seville': (37.39, -5.98, 1.0),
    'Valencia': (39.47, -0.38, 1.0),
    'Bilbao': (43.26, -2.93, 1.0),
    'Lisbon': (38.72, -9.14, 0.0),
    'Rome': (41.90, 12.50, 1.0),
    'Paris': (48.86, 2.35, 1.0),
    'London': (51.51, -0.13, 0.0),
    'Berlin': (52.52, 13.40, 1.0),
    'New York': (40.71, -74.01, -5.0),
    'Mexico City': (19.43, -99.13, -6.0),
    'Guatemala City': (14.63, -90.51, -6.0),
    'San Jose': (9.93, -84.08, -6.0),
    'Panama City': (8.98, -79.52, -5.0),
    'Havana': (23.11, -82.37, -5.0),
    'Santo Domingo': (18.49, -69.93, -4.0),
    'Caracas': (10.49, -66.88, -4.0),
    'Bogota': (4.71, -74.07, -5.0),
    'Quito': (-0.18, -78.47, -5.0),
    'Lima': (-12.05, -77.04, -5.0),
    'La Paz': (-16.50, -68.15, -4.0),
    'Asuncion': (-25.26, -57.58, -3.0),
    'Sao Paulo': (-23.55, -46.63, -3.0),
    'Rio de Janeiro': (-22.91, -43.17, -3.0),
    'Santiago': (-33.45, -70.67, -4.0),
    'Buenos Aires': (-34.60, -58.38, -3.0),
    'Montevideo': (-34.90, -56.16, -3.0),
}
OTHER = 'other place'
LOCATIONS = tuple(CITIES) + (OTHER,)
SHOW = ('diagram', 'day path', 'position', 'beam', 'ray', 'altitude', 'azimuth', 'sunrise', 'sunset')
YEAR = 2026
DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
SAMPLES = 49                    # points of each curve of the diagram


def place(location: str, latitude=None, longitude=None, time_zone=None) -> tuple[float, float, float]:
    """(latitude, longitude, time zone) of a city of the list, or the three numbers given («other place»)."""
    if location == OTHER:
        lat, lon, zone = (float(x) if x is not None else d for x, d in
                          zip((latitude, longitude, time_zone), CITIES['Madrid']))
        if not -90 <= lat <= 90:
            raise ShapeError(tr('The latitude goes from −90 (the South Pole) to 90 (the North Pole).'))
        if not -180 <= lon <= 180:
            raise ShapeError(tr('The longitude goes from −180 to 180 (+ east of Greenwich, − west).'))
        return lat, lon, zone
    if location not in CITIES:
        raise ShapeError(tr('The place must be one of: {options}.').format(
            options=", ".join(tr(c) for c in LOCATIONS)))
    return CITIES[location]


def _julian(day, month, hour, zone):
    """The Julian day of a local standard time (arrays)."""
    day, month = np.asarray(day, float), np.asarray(month, int)
    start = np.cumsum((0,) + DAYS_IN_MONTH[:-1])
    day_of_year = start[np.clip(month, 1, 12) - 1] + day
    # 2026-01-01 00:00 UTC is the Julian day 2461041.5
    return 2461041.5 + (day_of_year - 1) + (np.asarray(hour, float) - zone) / 24.0


def _solar(jd):
    """The declination (radians) and the equation of time (minutes) at a Julian day (NOAA)."""
    t = (jd - 2451545.0) / 36525.0
    l0 = np.radians((280.46646 + t * (36000.76983 + t * 0.0003032)) % 360)
    m = np.radians(357.52911 + t * (35999.05029 - 0.0001537 * t))
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (np.sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t)) + np.sin(2 * m) * (0.019993 - 0.000101 * t)
         + np.sin(3 * m) * 0.000289)
    omega = np.radians(125.04 - 1934.136 * t)
    apparent = np.radians(np.degrees(l0) + c - 0.00569 - 0.00478 * np.sin(omega))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = np.radians(eps0 + 0.00256 * np.cos(omega))
    declination = np.arcsin(np.sin(eps) * np.sin(apparent))
    y = np.tan(eps / 2) ** 2
    equation = 4 * np.degrees(y * np.sin(2 * l0) - 2 * e * np.sin(m) + 4 * e * y * np.sin(m) * np.cos(2 * l0)
                              - 0.5 * y * y * np.sin(4 * l0) - 1.25 * e * e * np.sin(2 * m))
    return declination, equation


def position(lat, lon, zone, day, month, hour):
    """The altitude and the azimuth of the sun, in degrees (arrays). Azimuth from the north, clockwise: 90 east, 180
    south, 270 west. The altitude counts the refraction of the air (the sun is seen a little higher near the
    horizon); below 0, it is night."""
    declination, equation = _solar(_julian(day, month, hour, zone))
    true_time = (np.asarray(hour, float) * 60 + equation + 4 * lon - 60 * zone) % 1440
    hour_angle = np.radians(true_time / 4 - 180)
    phi = math.radians(lat)
    cos_zenith = np.clip(math.sin(phi) * np.sin(declination) + math.cos(phi) * np.cos(declination)
                         * np.cos(hour_angle), -1, 1)
    zenith = np.arccos(cos_zenith)
    altitude = 90 - np.degrees(zenith)
    # The refraction (NOAA), in degrees: up to about half a degree at the horizon.
    a = altitude
    te = np.tan(np.radians(np.clip(a, -89, 89)))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(a > 85, 0.0,
                     np.where(a > 5, 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5,
                              np.where(a > -0.575, 1735 + a * (-518.2 + a * (103.4 + a * (-12.79 + a * 0.711))),
                                       -20.774 / te))) / 3600
    altitude = altitude + r
    sin_zenith = np.sin(zenith)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos_az = np.clip((math.sin(phi) * cos_zenith - np.sin(declination)) / (math.cos(phi) * sin_zenith), -1, 1)
    az = np.degrees(np.arccos(np.nan_to_num(cos_az, nan=1.0)))
    azimuth = np.where(hour_angle > 0, (az + 180) % 360, (540 - az) % 360)
    return altitude, azimuth


def rise_and_set(lat, lon, zone, day, month):
    """The sunrise and the sunset, in local standard hours (arrays; NaN where the sun does not rise or does not
    set that day: the polar day and night)."""
    noon = 12.0 + np.zeros(np.broadcast(np.asarray(day), np.asarray(month)).shape)
    for _ in range(2):                                      # the noon of that day, then the sun at that noon
        declination, equation = _solar(_julian(day, month, noon, zone))
        noon = (720 - 4 * lon - equation + 60 * zone) / 60
    phi = math.radians(lat)
    cos_h = (math.cos(math.radians(90.833)) / (math.cos(phi) * np.cos(declination))
             - math.tan(phi) * np.tan(declination))
    with np.errstate(invalid="ignore"):
        half = np.degrees(np.arccos(np.where(np.abs(cos_h) <= 1, cos_h, np.nan))) * 4 / 60
    return noon - half, noon + half


def towards(altitude, azimuth, north=0.0) -> np.ndarray:
    """The unit vector from the ground towards the sun (…, 3), with the north turned `north` degrees
    counterclockwise from +Y."""
    h, a = np.radians(altitude), np.radians(np.asarray(azimuth) - north)
    return np.stack([np.sin(a) * np.cos(h), np.cos(a) * np.cos(h), np.sin(h)], -1)


def _numbers(x, what: str) -> np.ndarray:
    v = np.asarray(x.values if isinstance(x, Data) else x, dtype=float).ravel()
    if not len(v) or not np.all(np.isfinite(v)):
        raise ShapeError(tr('“{what}” must be a number, or a list of numbers.').format(what=tr(what)))
    return v


def _path(lat, lon, zone, day, month, north, centre, radius, start=0.0, end=24.0):
    """The path of the sun one day, above the horizon, as points on the sphere of the diagram; None if it does not
    rise. Sampled finely, then evened out."""
    hours = np.linspace(start, end, 24 * 12 + 1)
    alt, az = position(lat, lon, zone, day, month, hours)
    up = alt >= 0
    if not up.any():
        return None
    runs = np.split(np.arange(len(hours)), np.nonzero(np.diff(up.astype(int)))[0] + 1)
    run = max((r for r in runs if up[r[0]]), key=len)       # the longest stretch above the horizon
    p = centre + radius * towards(alt[run], az[run], north)
    return p


def _evenly(curve: np.ndarray, n: int = SAMPLES) -> np.ndarray:
    from .surfaces import _resample
    return _resample(curve, n) if len(curve) > 1 else np.repeat(curve, n, axis=0)


def diagram_curves(lat, lon, zone, north, centre, radius) -> list[np.ndarray]:
    """The solar diagram: the horizon with the four points of the compass (the north, longer), the path of the 21st
    of each month, and the line of each hour from the winter solstice to the summer one."""
    curves = []
    t = np.linspace(0, 2 * np.pi, SAMPLES)
    curves.append(centre + radius * np.stack([np.cos(t), np.sin(t), np.zeros_like(t)], -1))
    for azimuth, long_ in ((0, 0.25), (90, 0.1), (180, 0.1), (270, 0.1)):
        d = towards(0.0, azimuth, north)
        curves.append(np.stack([centre + radius * d, centre + radius * (1 + long_) * d]))
    for month in range(1, 13):
        p = _path(lat, lon, zone, 21, month, north, centre, radius)
        if p is not None:
            curves.append(p)
    # The hours: from the 21st of December to the 21st of June, every few days (in the south, the other way round
    # changes nothing: the same line).
    days = [(21, 12)] + [(d, m) for m in range(1, 7) for d in (1, 11, 21)]
    for h in range(24):
        alt, az = position(lat, lon, zone, np.array([d for d, _ in days]), np.array([m for _, m in days]),
                           np.full(len(days), float(h)))
        up = alt >= 0
        if up.sum() < 2:
            continue
        runs = np.split(np.arange(len(days)), np.nonzero(np.diff(up.astype(int)))[0] + 1)
        run = max((r for r in runs if up[r[0]]), key=len)
        if len(run) >= 2:
            curves.append(centre + radius * towards(alt[run], az[run], north))
    return [_evenly(c) for c in curves]


def sun(location='Madrid', latitude=None, longitude=None, time_zone=None, day=21, month=6, hour=12.0, north=0.0,
        centre=(0.0, 0.0, 0.0), scale=10.0, show='diagram', name: str | None = None) -> Data:
    """The node Sun (see the module)."""
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    lat, lon, zone = place(location, latitude, longitude, time_zone)
    d, m, h = (_numbers(x, w) for x, w in ((day, 'day'), (month, 'month'), (hour, 'hour')))
    if np.any((m < 1) | (m > 12) | (m != np.round(m))):
        raise ShapeError(tr('The month goes from 1 to 12.'))
    if np.any((h < 0) | (h > 24)):
        raise ShapeError(tr('The hour goes from 0 to 24 (local standard time): {hour} is not an hour of the '
                            'day.').format(hour=", ".join(f"{x:g}" for x in h[(h < 0) | (h > 24)][:3])))
    m = m.astype(int)
    longest = np.array(DAYS_IN_MONTH)[m - 1] if len(m) else 31
    if np.any((d < 1) | (d > np.max(longest))):
        raise ShapeError(tr('The day goes from 1 to the last of its month (31 at most).'))
    try:
        d, m, h = np.broadcast_arrays(d, m, h)
    except ValueError:
        raise ShapeError(tr('The lists of days, months and hours must have the same length (or be a single '
                            'number).')) from None
    north = float(north or 0.0)
    radius = float(scale if scale is not None else 10.0)
    if radius <= 0:
        raise ShapeError(tr('The scale is the radius of the diagram: it must be more than 0.'))
    from .geometry import _point
    c = np.asarray(centre.values, float).reshape(-1)[:3] if isinstance(centre, Data) else \
        _point(centre, "centre").values.reshape(-1)
    if c.shape != (3,):                                   # an empty data: no point to stand on
        _point((), "centre")
    many = len(d) > 1

    def one_or_many(values, kind=None):
        values = np.asarray(values, float)
        return Data(values, ("sun",), name, kind=kind) if many else \
            Data(values[0] if values.ndim > 1 or kind is not None else float(values[0]), (), name, kind=kind)

    if show == 'diagram':
        curves = diagram_curves(lat, lon, zone, north, c, radius)
        return Data(np.stack(curves), ("line",), name, kind=CURVE)
    if show == 'day path':
        paths = []
        for dd, mm in zip(d, m):
            p = _path(lat, lon, zone, dd, mm, north, c, radius)
            if p is None:
                raise ShapeError(tr('The sun does not rise that day there (the polar night).'))
            paths.append(_evenly(p, 97))
        return one_or_many(np.stack(paths), CURVE)
    if show in ('sunrise', 'sunset'):
        rise, set_ = rise_and_set(lat, lon, zone, d, m)
        values = rise if show == 'sunrise' else set_
        if np.any(np.isnan(values)):
            raise ShapeError(tr('The sun does not rise or does not set that day there (the polar day or night).'))
        return one_or_many(values)
    alt, az = position(lat, lon, zone, d, m, h)
    if show == 'altitude':
        return one_or_many(alt)
    if show == 'azimuth':
        return one_or_many(az)
    up = towards(alt, az, north)
    if show == 'ray':
        return one_or_many(-up, VECTOR)
    if show == 'position':
        return one_or_many(c + radius * up, POINT)
    beams = np.stack([c + radius * up, np.broadcast_to(c, up.shape)], -2)          # from the sun to the centre
    return one_or_many(beams, ARROW)


INCIDENCE = ('sunlight', 'angle')
SIDES = ('its face', 'both faces')


def incidence(faces, ray, side='its face', show='sunlight', name: str | None = None) -> Data:
    """How straight the sun reaches each face (Lambert's cosine law): «sunlight», from 1 (the sun
    square on the face) to 0 (grazing it, or behind it); «angle», in degrees from the face's normal (0 square, 90
    grazing, more than 90 from behind). Panels and polygons, each element; meshes, surfaces and boxes, each face (the
    list «face»). With several hours, the sunlight is the average of all of them."""
    from . import geometry as geo
    from .meshes import _triangles
    from .shadows import rays_of
    if show not in INCIDENCE:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in INCIDENCE)))
    if side not in SIDES:
        raise ShapeError(tr('The side must be one of: {options}.').format(options=", ".join(tr(o) for o in SIDES)))
    if not isinstance(faces, Data) or faces.kind is None or faces.kind.faces is None:
        raise ShapeError(tr('Connect the faces: panels (a Grid), a mesh, a surface or a box.'))
    rays = rays_of(ray)
    if faces.kind.name in (geo.RECTANGLE.name, "polygon"):
        normals = geo.normal(faces)                            # one per panel, keeping its lists
        n, levels = np.asarray(normals.values, float), normals.levels
    else:
        t = _triangles(faces)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)
        levels = ("face",)
    cosine = -(n[..., None, :] * rays).sum(-1)                  # (…, rays): 1 when the face looks at the sun
    if side == 'both faces':
        cosine = np.abs(cosine)
    cosine = np.where(rays[:, 2] < -1e-6, cosine, -1.0)         # the sun down: nothing reaches
    if show == 'angle':
        if len(rays) > 1:
            raise ShapeError(tr('The angle is for a single hour: give the Sun one hour, or show «sunlight».'))
        values = np.degrees(np.arccos(np.clip(cosine[..., 0], -1, 1)))
    else:
        values = np.clip(cosine, 0, 1).mean(-1)
    if not levels:
        return Data(float(values), (), name)
    return Data(values, levels, name)
