"""The matcaps of the 3D view: the light of a material, painted on a sphere.

A *matcap* (material capture) is the photo of a sphere made of a material: each point of a face takes the colour of
the point of the sphere that faces the same way. So a model looks as if it were made of plaster or clay without
setting up lights. These are drawn here (they are not images of other programs): plaster, clay, graphite and
ceramic.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

#: The matcaps, with their name on view.
MATCAPS = {"plaster": 'Plaster', "clay": 'Clay', "graphite": 'Graphite', "ceramic": 'Ceramic'}


def _sphere(n):
    """The normals of a sphere seen from the front (x to the right, y up, z towards the viewer)."""
    y, x = np.mgrid[1:-1:n*1j, -1:1:n*1j]
    z = np.sqrt(np.clip(1 - x*x - y*y, 0, 1))
    return np.stack([x, y, z], -1), z

def _span(N, d, wrap=0.0):
    """A diffuse light from `d`; `wrap` lets it pass a little beyond the edge (softer)."""
    d = np.array(d, float); d /= np.linalg.norm(d)
    return np.clip(((N*d).sum(-1) + wrap) / (1 + wrap), 0, 1)

def _refl(N, d, brightness):
    """The highlight of a light from `d` (more `shine`, smaller and sharper)."""
    d = np.array(d, float); d /= np.linalg.norm(d)
    h = d + np.array([0, 0, 1.0]); h /= np.linalg.norm(h)
    return np.clip((N*h).sum(-1), 0, 1) ** brightness

@lru_cache(maxsize=None)
def matcap(name: str, n: int = 256) -> np.ndarray:
    """The image of the matcap (n × n, RGB from 0 to 255)."""
    if name not in MATCAPS:
        name = "plaster"
    N, z = _sphere(n)
    fres = (1 - z) ** 3                      # the edge of the sphere: the faces seen edge-on
    if name == "clay":
        base = np.array([0.82, 0.70, 0.60])
        span = 0.95*_span(N, [-0.6, 0.8, 0.5], 0.4) + 0.25*_span(N, [0.9, -0.1, 0.4])
        col = base*(0.32 + span)[..., None]*(1 - 0.35*fres)[..., None] + 0.10*_refl(N, [-0.5, 0.6, 0.6], 18)[..., None]
    elif name == "plaster":
        base = np.array([0.93, 0.93, 0.92])
        span = 0.75*_span(N, [-0.4, 0.9, 0.5], 0.6) + 0.30*_span(N, [0.8, 0.2, 0.6], 0.3)
        shadow = 0.55 + 0.45*_span(N, [0, 1, 0.2], 0.8)
        col = base*(0.34 + 0.85*span*shadow)[..., None] + 0.15*fres[..., None]*np.array([0.85, 0.9, 1.0])
    elif name == "graphite":
        base = np.array([0.30, 0.31, 0.34])
        span = 0.9*_span(N, [-0.5, 0.8, 0.6], 0.3) + 0.3*_span(N, [0.7, -0.4, 0.5])
        col = base*(0.25 + span)[..., None] + 0.55*_refl(N, [-0.5, 0.7, 0.5], 40)[..., None] \
              + 0.35*fres[..., None]*np.array([0.7, 0.8, 1.0])
    elif name == "ceramic":
        base = np.array([0.95, 0.94, 0.90])
        span = 0.8*_span(N, [-0.5, 0.8, 0.6], 0.5) + 0.25*_span(N, [0.8, -0.2, 0.5])
        col = base*(0.3 + span)[..., None]*(1 - 0.3*fres)[..., None] + 0.8*_refl(N, [-0.5, 0.7, 0.6], 120)[..., None] \
              + 0.25*_refl(N, [0.7, -0.3, 0.6], 60)[..., None]
    col = np.clip(col, 0, 1)
    return (col * 255).astype(np.uint8)


# --- The user's own matcaps ------------------------------------------------------------------------------------------
# Images of a sphere put in a folder (by default ~/.local/share/tensela/matcaps; TENSELA_MATCAPS changes it):
# PNG, JPG, TIFF, WebP or EXR. Each appears in the menu of the Matcap with its picture, by its file name.

#: What can be read as a matcap.
IMAGES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".exr")
#: The key of an own matcap: this, and its file name («file:bronze.png»).
OWN = "file:"


def folder():
    """Where the own matcaps are."""
    import os
    from pathlib import Path
    own = os.environ.get("TENSELA_MATCAPS")
    if own:
        return Path(own)
    return Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")) / "tensela" / "matcaps"


def own() -> dict:
    """The own matcaps: {key: file}, by name."""
    where = folder()
    if not where.is_dir():
        return {}
    files = sorted((p for p in where.iterdir() if p.is_file() and p.suffix.lower() in IMAGES),
                   key=lambda p: p.name.casefold())
    return {OWN + p.name: p for p in files}


def known(key: str) -> bool:
    return key in MATCAPS or key in own()


def image_of(key: str) -> np.ndarray:
    """The picture of a matcap (rows from the top, RGB from 0 to 255): one of Tensela's, or the user's."""
    if key.startswith(OWN):
        path = own().get(key)
        if path is not None:
            return _read_cached(str(path), path.stat().st_mtime)
    return matcap(key)


@lru_cache(maxsize=16)
def _read_cached(path: str, _mtime: float) -> np.ndarray:
    return read_image(path)


def read_image(path) -> np.ndarray:
    """An image as RGB from 0 to 255 (rows from the top). An EXR (light without limits, linear) is brought to the
    screen's: up to 1, with its gamma."""
    from pathlib import Path
    from ..data import ShapeError
    from ..language import tr
    path = Path(path)
    if path.suffix.lower() == ".exr":
        linear = _exr(path)
        return (np.clip(linear, 0, 1) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8)
    from PySide6.QtGui import QImage
    image = QImage(str(path))
    if image.isNull():
        raise ShapeError(tr('“{name}” cannot be read as an image.').format(name=path.name))
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h = image.width(), image.height()
    raw = np.frombuffer(image.constBits(), np.uint8, count=image.sizeInBytes()).reshape(h, image.bytesPerLine())
    return raw[:, :w * 3].reshape(h, w, 3).copy()


def _exr(path) -> np.ndarray:
    """The R, G, B of an OpenEXR image of scanlines, without compression or with RLE, ZIPS or ZIP (the usual ones):
    linear, as floats (h × w × 3). Other compressions (PIZ, PXR24, B44, DWA…) or tiles are said."""
    import struct
    import zlib
    from ..data import ShapeError
    from ..language import tr
    data = path.read_bytes()

    def refuse(why: str):
        raise ShapeError(tr('“{name}” is an EXR that cannot be read here ({why}): save it as PNG, or as EXR with ZIP '
                            'compression.').format(name=path.name, why=why))
    if data[:4] != b"\x76\x2f\x31\x01":
        refuse(tr('it is not an OpenEXR file'))
    if struct.unpack_from("<I", data, 4)[0] & 0x1600:      # tiles, long names, several parts
        refuse(tr('tiles or several parts'))
    at, header = 8, {}
    while data[at] != 0:
        end = data.index(b"\0", at)
        name = data[at:end].decode("latin-1")
        end2 = data.index(b"\0", end + 1)
        kind = data[end + 1:end2].decode("latin-1")
        size = struct.unpack_from("<i", data, end2 + 1)[0]
        header[name] = (kind, data[end2 + 5:end2 + 5 + size])
        at = end2 + 5 + size
    at += 1
    channels, raw = [], header["channels"][1]
    k = 0
    while raw[k] != 0:
        end = raw.index(b"\0", k)
        name = raw[k:end].decode("latin-1")
        pixel, _, _, xs, ys = struct.unpack_from("<iB3sii", raw, end + 1)
        channels.append((name, pixel, xs, ys))
        k = end + 1 + 16
    compression = header["compression"][1][0]
    lines = {0: 1, 1: 1, 2: 1, 3: 16}.get(compression)
    if lines is None:
        refuse(tr('its compression'))
    x0, y0, x1, y1 = struct.unpack("<4i", header["dataWindow"][1])
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if any(xs != 1 or ys != 1 for _, _, xs, ys in channels):
        refuse(tr('channels at another resolution'))
    width_of = {0: 4, 1: 2, 2: 4}
    dtype_of = {0: np.dtype("<u4"), 1: np.dtype("<f2"), 2: np.dtype("<f4")}
    chunks = -(-h // lines)
    offsets = struct.unpack_from(f"<{chunks}Q", data, at)
    planes = {name: np.zeros((h, w), np.float32) for name, *_ in channels}
    for offset in offsets:
        y, size = struct.unpack_from("<ii", data, offset)
        block = data[offset + 8:offset + 8 + size]
        rows = min(lines, y1 + 1 - y)
        expected = rows * w * sum(width_of[p] for _, p, _, _ in channels)
        if size < expected:                                   # compressed
            block = zlib.decompress(block) if compression in (2, 3) else _rle(block)
            t = np.frombuffer(block, np.uint8).astype(np.int32)
            t = (np.cumsum(np.r_[t[:1], t[1:] - 128]) & 0xFF).astype(np.uint8)   # the predictor, undone
            half = (len(t) + 1) // 2
            out = np.empty(len(t), np.uint8)
            out[0::2], out[1::2] = t[:half], t[half:]
            block = out.tobytes()
        k = 0
        for r in range(rows):
            for name, pixel, _, _ in channels:
                n = w * width_of[pixel]
                planes[name][y - y0 + r] = np.frombuffer(block, dtype_of[pixel], count=w, offset=k).astype(np.float32)
                k += n
    pick = [next((n for n in planes if n.split(".")[-1].upper() == c), None) for c in "RGB"]
    if pick[0] is None:
        pick = [next(iter(planes))] * 3                        # a grey one: its only channel
    return np.stack([planes[p if p is not None else pick[0]] for p in pick], axis=-1)


def _rle(block: bytes) -> bytes:
    """The run-length code of OpenEXR: a negative count, so many bytes as they are; a positive one, the next byte
    count + 1 times."""
    out, k = bytearray(), 0
    while k < len(block):
        count = int.from_bytes(block[k:k + 1], "little", signed=True)
        k += 1
        if count < 0:
            out += block[k:k - count]
            k -= count
        else:
            out += block[k:k + 1] * (count + 1)
            k += 1
    return bytes(out)
