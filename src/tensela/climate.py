"""The climate of a place, from a weather file (.epw): the real sun, temperature, humidity and wind of
each hour of a typical year.

An EPW (EnergyPlus Weather file) is plain text: a first line with the place (its name, latitude, longitude, time zone
and height), seven more lines of header, and one line per hour of the year with some thirty readings. They are free
for almost any city (climate.onebuilding.org; the «TMYx» are typical years made from recent measurements). The file
can be given as it is downloaded, inside its .zip: the .epw is read from it without unpacking.

Only text is read: nothing of the file is run. A leap year loses its 29th of February, so every file has the 8760
hours of a common year, as the sun of sun.py.

The hours of the file end at their number (hour 1 is from 0:00 to 1:00, local standard time): the sun of each one is
taken at its middle.
"""
from __future__ import annotations

import io
import zipfile
from collections import OrderedDict
from pathlib import Path

import numpy as np

from .data import Data, ShapeError
from .language import tr

#: The columns read, by their place in each line of data.
_COLUMNS = {"year": 0, "month": 1, "day": 2, "hour": 3, "temperature": 6, "humidity": 8, "global": 13,
            "direct": 14, "diffuse": 15, "global illuminance": 16, "diffuse illuminance": 18, "wind direction": 20,
            "wind speed": 21, "cloud cover": 22}
SHOW = ('temperature', 'humidity', 'global radiation', 'direct radiation', 'diffuse radiation', 'wind speed',
        'wind direction', 'cloud cover')
PER = ('hour', 'day', 'month')
#: What each «show» reads, and whether it is summed (energy) or averaged when grouped by day or month.
_READS = {'temperature': ("temperature", False), 'humidity': ("humidity", False),
          'global radiation': ("global", True), 'direct radiation': ("direct", True),
          'diffuse radiation': ("diffuse", True), 'wind speed': ("wind speed", False),
          'wind direction': ("wind direction", False), 'cloud cover': ("cloud cover", False)}
_CACHE: OrderedDict = OrderedDict()
_CACHE_SIZE = 4


def _text(path: Path) -> str:
    """The text of the .epw, from the file or from the first .epw inside a .zip."""
    if not path.is_file():                         # (a device such as /dev/zero would never end)
        raise ShapeError(tr('“{path}” is not a file.').format(path=path.name))
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".epw")]
                if not names:
                    raise ShapeError(tr('The .zip “{path}” has no .epw inside.').format(path=path.name))
                info = z.getinfo(names[0])
                if info.file_size > 20_000_000:
                    raise ShapeError(tr('The .epw is too big to be a weather file.'))
                return z.read(names[0]).decode("latin-1")
        except zipfile.BadZipFile:
            raise ShapeError(tr('“{path}” is not a good .zip.').format(path=path.name)) from None
    if path.stat().st_size > 20_000_000:
        raise ShapeError(tr('The .epw is too big to be a weather file.'))
    return path.read_text(encoding="latin-1")


def read(file) -> dict:
    """The climate of a weather file (a path, relative to the project's folder or absolute): the place and the
    readings of the 8760 hours."""
    from .images import resolve
    if not isinstance(file, (str, Path)) or not str(file).strip():
        raise ShapeError(tr('“file” is missing: a weather file (.epw, or the .zip it comes in).'))
    path = resolve(str(file).strip())
    try:
        stat = path.stat()
    except OSError:
        raise ShapeError(tr('The weather file “{path}” cannot be found. A relative path is read from the folder of '
                            'the project (save the project first).').format(path=file)) from None
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    lines = _text(path).splitlines()
    head = lines[0].split(",") if lines else []
    if len(head) < 10 or head[0].strip().upper() != "LOCATION":
        raise ShapeError(tr('“{path}” is not a weather file (.epw): its first line should say LOCATION.').format(
            path=path.name))
    try:
        latitude, longitude, zone, height = (float(x) for x in head[6:10])
        rows = [line.split(",") for line in lines[8:] if line.strip()]
        table = np.array([[float(r[i]) for i in _COLUMNS.values()] for r in rows])
    except (ValueError, IndexError):
        raise ShapeError(tr('“{path}” has a line that cannot be read as a weather file.').format(
            path=path.name)) from None
    columns = dict(zip(_COLUMNS, table.T))
    leap = (columns["month"] == 2) & (columns["day"] == 29)
    columns = {k: v[~leap] for k, v in columns.items()}
    if len(columns["month"]) != 8760:
        raise ShapeError(tr('“{path}” does not have the hours of a whole year ({n} instead of 8760).').format(
            path=path.name, n=len(columns["month"])))
    city = head[1].strip()
    country = head[3].strip()
    climate = {"name": f"{city} ({country})" if country else city, "latitude": latitude, "longitude": longitude,
               "time zone": zone, "height": height, "file": path.name, **columns}
    _CACHE[key] = climate
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return climate


def climate_of(data) -> dict:
    """The climate a node passes on (the output of a Climate node)."""
    climate = getattr(data, "climate", None)
    if climate is None:
        raise ShapeError(tr('Connect a Climate node: it reads the weather file.'))
    return climate


def climate_node(file, show='temperature', per='hour', name: str | None = None) -> Data:
    """The node Climate: the readings of the weather file, hour by hour, or by day or month (the energy summed, in
    kWh/m²; the rest averaged). It carries the whole climate for Insolation."""
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    if per not in PER:
        raise ShapeError(tr('«per» must be one of: {options}.').format(options=", ".join(tr(o) for o in PER)))
    c = read(file)
    column, energy = _READS[show]
    values = np.asarray(c[column], float)
    if energy:
        values = values / 1000.0                                  # Wh/m² each hour → kWh/m²
    if per == 'hour':
        out = Data(values, ("hour",), name)
    else:
        group = (c["month"] - 1).astype(int) if per == 'month' else np.repeat(np.arange(365), 24)
        count = 12 if per == 'month' else 365
        if show == 'wind direction':                              # an angle: the average of the directions
            a = np.radians(values)
            sums = np.degrees(np.arctan2(np.bincount(group, np.sin(a), count), np.bincount(group, np.cos(a), count)))
            sums = sums % 360
        else:
            sums = np.bincount(group, weights=values, minlength=count)
            if not energy:
                sums = sums / np.bincount(group, minlength=count)
        out = Data(sums, (per,), name)
    out.climate = c
    return out
