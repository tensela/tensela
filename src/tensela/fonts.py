"""The fonts installed on the computer, as outlines: for the labels of the Text node in another letter than the single
stroke one (with lower case, accents and any sign the font has).

A letter of a font is its outline: closed curves (an «o» is two, the outside and its hole). They are read from the
font file itself (TrueType or OpenType, with fontTools, which comes with the window's libraries) and their curves
are written as short straight pieces. The size is the height of the capitals, as in the single-stroke letters: a
label of 0,2 m has capitals 0,2 m tall, whatever the font.

The fonts are found by the system (fc-list, fc-match) or, without it, in the usual folders.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

from .data import ShapeError
from .language import tr

_CURVE_STEPS = 6                       # each curve of a letter, in this many straight pieces
_SUFFIXES = (".ttf", ".otf", ".ttc")
_GLYPHS: dict = {}                    # {(font file, glyph): its rings, in the font's units}


def _folders() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library/Fonts"]
    if sys.platform.startswith("win"):
        return [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
                Path(os.environ.get("LOCALAPPDATA", home)) / "Microsoft/Windows/Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".local/share/fonts", home / ".fonts"]


@lru_cache(maxsize=1)
def _installed() -> dict[str, list[tuple[str, str]]]:
    """{family: [(style, file), …]} of the fonts that can be read (TrueType or OpenType)."""
    found: dict[str, list[tuple[str, str]]] = {}
    if shutil.which("fc-list"):
        try:
            out = subprocess.run(["fc-list", "--format", "%{family[0]}\t%{style[0]}\t%{file}\n"],
                                 capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[2].lower().endswith(_SUFFIXES):
                found.setdefault(parts[0].strip(), []).append((parts[1].strip(), parts[2]))
    if not found:
        for folder in _folders():
            if folder.is_dir():
                for filepath in folder.rglob("*"):
                    if filepath.suffix.lower() in _SUFFIXES:
                        family, _, style = filepath.stem.partition("-")
                        found.setdefault(family, []).append((style or "Regular", str(filepath)))
    return found


def families() -> list[str]:
    """The names of the installed fonts, in order (for the list of the panel)."""
    return sorted(_installed(), key=str.casefold)


def file_of(family: str) -> str:
    """The file of a font, in its regular style. An empty name: the system's usual sans serif."""
    installed = _installed()
    wanted = family.strip()
    if not wanted:
        for usual in ("DejaVu Sans", "Noto Sans", "Liberation Sans", "Arial", "Helvetica", "Segoe UI"):
            if usual in installed:
                wanted = usual
                break
        else:
            if not installed:
                raise ShapeError(tr('No font was found on this computer: write the labels in single stroke.'))
            wanted = families()[0]
    by_name = {f.casefold(): f for f in installed}
    if wanted.casefold() not in by_name:
        raise ShapeError(tr('There is no font called “{font}” on this computer. Some there are: {some}.').format(
            font=family, some=", ".join(families()[:6])))
    styles = installed[by_name[wanted.casefold()]]
    for liked in ("Regular", "Book", "Normal", "Roman", "Medium"):
        for style, filepath in styles:
            if style.casefold() == liked.casefold():
                return filepath
    return min(styles, key=lambda s: len(s[0]))[1]


@lru_cache(maxsize=8)
def _font(filepath: str):
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        raise ShapeError(tr('The letters of a font need fontTools (it comes with the window: pip install '
                            'fonttools).')) from None
    try:
        return TTFont(filepath, fontNumber=0, lazy=True)
    except Exception as error:                       # a damaged or unknown file
        raise ShapeError(tr('The font “{file}” could not be read: {error}').format(
            file=Path(filepath).name, error=error)) from None


def _pen():
    from fontTools.pens.basePen import BasePen

    class Flat(BasePen):
        """Writes the curves of a glyph as short straight pieces: a list of closed rings."""

        def __init__(self, glyph_set):
            super().__init__(glyph_set)
            self.rings, self._ring = [], []

        def _moveTo(self, p):
            self._ring = [p]

        def _lineTo(self, p):
            self._ring.append(p)

        def _qCurveToOne(self, p1, p2):
            p0 = np.array(self._getCurrentPoint(), float)
            t = np.linspace(0, 1, _CURVE_STEPS + 1)[1:, None]
            q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * np.array(p1) + t ** 2 * np.array(p2)
            self._ring.extend(map(tuple, q))

        def _curveToOne(self, p1, p2, p3):
            p0 = np.array(self._getCurrentPoint(), float)
            t = np.linspace(0, 1, _CURVE_STEPS + 1)[1:, None]
            q = ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * np.array(p1) + 3 * (1 - t) * t ** 2 * np.array(p2)
                 + t ** 3 * np.array(p3))
            self._ring.extend(map(tuple, q))

        def _closePath(self):
            if len(self._ring) > 2:
                ring = np.array(self._ring, float)
                if np.allclose(ring[0], ring[-1]):
                    ring = ring[:-1]
                self.rings.append(np.vstack([ring, ring[:1]]))    # closed: it repeats its first point
            self._ring = []

        _endPath = _closePath

    return Flat


def outlines(text: str, family: str, height: float) -> tuple[list[np.ndarray], float]:
    """The outlines of a text in a font (2D rings from (0, 0), the baseline at y = 0), with capitals `height` tall,
    and how long it is."""
    filepath = file_of(family)
    font = _font(filepath)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap() or {}
    metrics = font["hmtx"].metrics
    em = font["head"].unitsPerEm
    capitals = getattr(font["OS/2"], "sCapHeight", 0) if "OS/2" in font else 0
    scale = height / (capitals if capitals and capitals > 0 else 0.7 * em)
    pen_type = _pen()
    rings, x = [], 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            name = cmap.get(ord("?")) if not ch.isspace() else cmap.get(ord(" "))
        if name is None or name not in glyphs:
            x += 0.5 * em
            continue
        if (filepath, name) not in _GLYPHS:              # (each letter is read once)
            pen = pen_type(glyphs)
            glyphs[name].draw(pen)
            _GLYPHS[(filepath, name)] = pen.rings
        rings.extend((r + [x, 0.0]) * scale for r in _GLYPHS[(filepath, name)])
        x += metrics.get(name, (0.5 * em, 0))[0]
    if rings:
        lows = min(r[:, 0].min() for r in rings)
        highs = max(r[:, 0].max() for r in rings)
        rings = [r - [lows, 0.0] for r in rings]          # from the left of the first letter, as the single stroke
        return rings, highs - lows
    return [], 0.0
