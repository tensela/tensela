"""Reading images: the Image sampler node turns a picture into numbers.

A photo, a drawing or a gradient laid over a rectangle gives a value at each point: how light the image is there
(or how much red, green, blue or transparency). It is the way to perforate a façade from a photo, or to set the
height of a field of columns from a drawing.

The path of the image is kept as written. A relative path is read from the folder of the project, which the graph
being computed sets with `folder`.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import numpy as np

from .data import Data, ShapeError, apply
from .language import tr

#: What is read from each pixel.
CHANNELS = ('brightness', 'red', 'green', 'blue', 'alpha')

#: The file types the window offers when choosing an image.
EXTENSIONS = ("png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp")

# The folder relative paths are read from, while a graph computes (see Graph.value).
_FOLDER: ContextVar[Path | None] = ContextVar("folder", default=None)

# The last images read, so that moving a slider does not read the file again. Each one is kept with the date of
# the file: if it changes on disk, it is read again.
_CACHE: OrderedDict[tuple, np.ndarray] = OrderedDict()
_CACHE_SIZE = 6


@contextmanager
def folder(path: Path | None):
    """Relative paths are read from `path` while inside the block."""
    token = _FOLDER.set(Path(path) if path is not None else None)
    try:
        yield
    finally:
        _FOLDER.reset(token)


def resolve(file) -> Path:
    """The path of an image: as written if it is absolute, or else inside the folder of the project."""
    path = Path(str(file)).expanduser()
    base = _FOLDER.get()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path


def read(file) -> np.ndarray:
    """The pixels of an image, as an array (height, width, 4) of 0 to 255 in red, green, blue and alpha."""
    if not isinstance(file, (str, Path)) or not str(file).strip():
        raise ShapeError(tr('“file” is missing: the image to read (a PNG or JPG file).'))
    path = resolve(str(file).strip())
    try:
        stat = path.stat()
    except OSError:
        raise ShapeError(tr('The image “{path}” cannot be found. A relative path is read from the folder of the '
                            'project (save the project first).').format(path=file)) from None
    if not path.is_file():                         # (a device such as /dev/zero would never end)
        raise ShapeError(tr('“{path}” is not a file.').format(path=file))
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(path) as image:
            pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    except (UnidentifiedImageError, OSError) as error:
        raise ShapeError(tr('“{path}” could not be read as an image ({error}).').format(path=file, error=error)) from None
    except Image.DecompressionBombError:          # (more than 178 million pixels: almost surely not a real image)
        raise ShapeError(tr('The image “{path}” is far too big (more than 178 million pixels): use a smaller '
                            'copy.').format(path=file)) from None
    pixels.setflags(write=False)
    _CACHE[key] = pixels
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return pixels


def _channel(pixels: np.ndarray, channel: str) -> np.ndarray:
    """One value from 0 to 1 per pixel."""
    rgba = pixels.astype(np.float32) / 255.0
    if channel == 'brightness':        # how light it looks to the eye: green weighs the most, blue the least
        return rgba[..., 0] * 0.2126 + rgba[..., 1] * 0.7152 + rgba[..., 2] * 0.0722
    if channel not in CHANNELS:
        raise ShapeError(tr('Unknown channel “{channel}”: brightness, red, green, blue or alpha.').format(channel=channel))
    return rgba[..., CHANNELS.index(channel) - 1]


def _bilinear(values: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """The value of the image at (u, v), from 0 to 1 each: u from left to right, v from bottom to top.

    Between pixels it blends the four nearest, so a small image still gives smooth changes. Outside the image it
    takes the nearest edge.
    """
    height, width = values.shape
    x = np.clip(np.nan_to_num(u, nan=0.5), 0, 1) * width - 0.5
    y = (1 - np.clip(np.nan_to_num(v, nan=0.5), 0, 1)) * height - 0.5
    x0 = np.clip(np.floor(x), 0, width - 1).astype(int)
    y0 = np.clip(np.floor(y), 0, height - 1).astype(int)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = np.clip(x - x0, 0, 1), np.clip(y - y0, 0, 1)
    top = values[y0, x0] * (1 - fx) + values[y0, x1] * fx
    bottom = values[y1, x0] * (1 - fx) + values[y1, x1] * fx
    return top * (1 - fy) + bottom * fy


def _axes(low: np.ndarray, high: np.ndarray, plane: str | None) -> tuple[int, int]:
    """The two axes the image is laid on (across, up). Without a plane: the flattest side of the frame is its normal."""
    from .geometry import PLANES
    if plane:
        if plane not in PLANES:
            raise ShapeError(tr('Unknown plane “{plane}”: plan, elevation or side elevation.').format(plane=plane))
        across, up = PLANES[plane]
        return int(np.argmax(across)), int(np.argmax(up))
    size = high - low
    normal = 2 if size[2] <= min(size[0], size[1]) else (1 if size[1] <= size[0] else 0)
    return {2: (0, 1), 1: (0, 2), 0: (1, 2)}[normal]


def sample(file, where, frame=None, plane=None, channel='brightness', black=0.0, white=1.0,
           name: str | None = None) -> Data:
    """A value at each point, read from an image laid over `frame` (stretched to fit it).

    `where` are points, or a geometry (each element by its centre: a panel, a column). `frame` is any geometry: the
    image covers its bounding box; without one, that of the points themselves. The value goes from `black` (where
    the image is dark, or the channel is empty) to `white` (where it is light, or the channel is full).
    """
    from .geometry import _centres, _data

    pixels = read(file)
    values = _channel(pixels, channel or 'brightness')
    points = _centres(where, "where")
    outline = points if frame is None else frame
    if not isinstance(outline, Data) or outline.kind is None:
        raise ShapeError(tr('“frame” must be a geometry (a rectangle, a surface): the image is laid over it.'))
    corners = outline.values.reshape(-1, 3)
    low, high = np.nanmin(corners, axis=0), np.nanmax(corners, axis=0)
    across, up = _axes(low, high, plane)
    size = np.where(high - low > 1e-12, high - low, 1.0)

    def at(p, b, w):
        u = (p[..., across] - low[across]) / size[across]
        v = (p[..., up] - low[up]) / size[up]
        return b + (w - b) * _bilinear(values, u, v)

    return apply(at, points, _data(black), _data(white), name=name)
