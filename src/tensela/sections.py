"""The sections of the bars and their materials, for Bar analysis.

A section is written as in a catalogue: «IPE 300», «HEA 200», «HEB 160» (the European I sections), or by its
measures in millimetres: «rect 200x400» (solid, width × height), «tube 200x100x8» (hollow rectangle, width ×
height × wall), «pipe 168x8» (hollow circle, diameter × wall), «round 50» (solid circle). A number picks one of
the catalogue by its place (0 is IPE 80, the first): so a slider can go through all of them, for Find the best….

The area, the inertias and the section moduli come from the measures (the flanges, the web and the four rounded
corners of the I sections, as the standard tables do): nothing is copied from any table. Height goes up (the strong
axis of an I section resists the weight).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .data import ShapeError
from .language import tr

# The European I sections: height, width, web, flange and the radius of the corners, in millimetres.
_IPE = {80: (80, 46, 3.8, 5.2, 5), 100: (100, 55, 4.1, 5.7, 7), 120: (120, 64, 4.4, 6.3, 7),
        140: (140, 73, 4.7, 6.9, 7), 160: (160, 82, 5.0, 7.4, 9), 180: (180, 91, 5.3, 8.0, 9),
        200: (200, 100, 5.6, 8.5, 12), 220: (220, 110, 5.9, 9.2, 12), 240: (240, 120, 6.2, 9.8, 15),
        270: (270, 135, 6.6, 10.2, 15), 300: (300, 150, 7.1, 10.7, 15), 330: (330, 160, 7.5, 11.5, 18),
        360: (360, 170, 8.0, 12.7, 18), 400: (400, 180, 8.6, 13.5, 21), 450: (450, 190, 9.4, 14.6, 21),
        500: (500, 200, 10.2, 16.0, 21), 550: (550, 210, 11.1, 17.2, 24), 600: (600, 220, 12.0, 19.0, 24)}
_HEA = {100: (96, 100, 5, 8, 12), 120: (114, 120, 5, 8, 12), 140: (133, 140, 5.5, 8.5, 12),
        160: (152, 160, 6, 9, 15), 180: (171, 180, 6, 9.5, 15), 200: (190, 200, 6.5, 10, 18),
        220: (210, 220, 7, 11, 18), 240: (230, 240, 7.5, 12, 21), 260: (250, 260, 7.5, 12.5, 24),
        280: (270, 280, 8, 13, 24), 300: (290, 300, 8.5, 14, 27), 320: (310, 300, 9, 15.5, 27),
        340: (330, 300, 9.5, 16.5, 27), 360: (350, 300, 10, 17.5, 27), 400: (390, 300, 11, 19, 27),
        450: (440, 300, 11.5, 21, 27), 500: (490, 300, 12, 23, 27), 550: (540, 300, 12.5, 24, 27),
        600: (590, 300, 13, 25, 27)}
_HEB = {100: (100, 100, 6, 10, 12), 120: (120, 120, 6.5, 11, 12), 140: (140, 140, 7, 12, 12),
        160: (160, 160, 8, 13, 15), 180: (180, 180, 8.5, 14, 15), 200: (200, 200, 9, 15, 18),
        220: (220, 220, 9.5, 16, 18), 240: (240, 240, 10, 17, 21), 260: (260, 260, 10, 17.5, 24),
        280: (280, 280, 10.5, 18, 24), 300: (300, 300, 11, 19, 27), 320: (320, 300, 11.5, 20.5, 27),
        340: (340, 300, 12, 21.5, 27), 360: (360, 300, 12.5, 22.5, 27), 400: (400, 300, 13.5, 24, 27),
        450: (450, 300, 14, 26, 27), 500: (500, 300, 14.5, 28, 27), 550: (550, 300, 15, 29, 27),
        600: (600, 300, 15.5, 30, 27)}

#: The catalogue, in order: a number picks one by its place (0 is IPE 80).
CATALOGUE = ([f"IPE {n}" for n in _IPE] + [f"HEA {n}" for n in _HEA] + [f"HEB {n}" for n in _HEB])


@dataclass(frozen=True)
class Section:
    """What a bar needs of its section, in metres: area, inertias (strong, weak), torsion, section moduli."""

    name: str
    area: float
    strong: float          # the inertia that resists the weight (about the horizontal axis)
    weak: float
    torsion: float
    modulus_strong: float  # the elastic section modulus, inertia ÷ half the height
    modulus_weak: float


def _i_section(name: str, h, b, tw, tf, r) -> Section:
    """An I section from its measures (mm): two flanges, a web and four rounded corners where they meet."""
    h, b, tw, tf, r = (x / 1000.0 for x in (h, b, tw, tf, r))
    web = h - 2 * tf
    corner = (1 - math.pi / 4) * r * r                         # the area of each rounded corner
    from_centre = 0.2234 * r                                   # its centroid, from the faces it fills
    area = 2 * b * tf + web * tw + 4 * corner
    strong = (b * h ** 3 - (b - tw) * web ** 3) / 12 + 4 * corner * (h / 2 - tf - from_centre) ** 2
    weak = (2 * tf * b ** 3 + web * tw ** 3) / 12 + 4 * corner * (tw / 2 + from_centre) ** 2
    torsion = (2 * b * tf ** 3 + web * tw ** 3) / 3
    return Section(name, area, strong, weak, torsion, 2 * strong / h, 2 * weak / b)


def _rectangle(name: str, b, h) -> Section:
    b, h = b / 1000.0, h / 1000.0
    a, c = max(b, h), min(b, h)
    torsion = a * c ** 3 * (1 / 3 - 0.21 * c / a * (1 - c ** 4 / (12 * a ** 4)))
    return Section(name, b * h, b * h ** 3 / 12, h * b ** 3 / 12, torsion, b * h * h / 6, h * b * b / 6)


def _tube(name: str, b, h, t) -> Section:
    b, h, t = b / 1000.0, h / 1000.0, t / 1000.0
    if 2 * t >= min(b, h):
        raise ShapeError(tr('The wall of «{name}» is as thick as the tube: it would be solid.').format(name=name))
    strong = (b * h ** 3 - (b - 2 * t) * (h - 2 * t) ** 3) / 12
    weak = (h * b ** 3 - (h - 2 * t) * (b - 2 * t) ** 3) / 12
    torsion = 2 * t * (b - t) ** 2 * (h - t) ** 2 / (b + h - 2 * t)
    return Section(name, b * h - (b - 2 * t) * (h - 2 * t), strong, weak, torsion, 2 * strong / h, 2 * weak / b)


def _pipe(name: str, d, t) -> Section:
    d, t = d / 1000.0, t / 1000.0
    if 2 * t >= d:
        raise ShapeError(tr('The wall of «{name}» is as thick as the tube: it would be solid.').format(name=name))
    inner = d - 2 * t
    inertia = math.pi / 64 * (d ** 4 - inner ** 4)
    return Section(name, math.pi / 4 * (d * d - inner * inner), inertia, inertia, 2 * inertia, 2 * inertia / d,
                   2 * inertia / d)


def _round(name: str, d) -> Section:
    d = d / 1000.0
    inertia = math.pi * d ** 4 / 64
    return Section(name, math.pi * d * d / 4, inertia, inertia, 2 * inertia, 2 * inertia / d, 2 * inertia / d)


#: The words for the sections by their measures (and how they are also written in Spanish).
_KINDS = {"rect": "rect", "rectangular": "rect", "solid": "rect", "macizo": "rect", "tube": "tube", "tubo": "tube",
          "pipe": "pipe", "caño": "pipe", "cano": "pipe", "tubo redondo": "pipe", "round": "round",
          "redondo": "round"}


def section(value) -> Section:
    """The section of a name («IPE 300», «rect 200x400», «tube 200x100x8», «pipe 168x8», «round 50») or of a place
    in the catalogue (a number)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        k = int(round(value))
        if not 0 <= k < len(CATALOGUE):
            raise ShapeError(tr('The catalogue has {n} sections (from 0 to {last}): {k} is not one.').format(
                n=len(CATALOGUE), last=len(CATALOGUE) - 1, k=k))
        value = CATALOGUE[k]
    text = str(value or "").strip()
    found = re.fullmatch(r"(IPE|HEA|HEB)\s*(\d+)", text, re.IGNORECASE)
    if found:
        family, size = found.group(1).upper(), int(found.group(2))
        table = {"IPE": _IPE, "HEA": _HEA, "HEB": _HEB}[family]
        if size not in table:
            raise ShapeError(tr('There is no {family} {size}: the sizes are {options}.').format(
                family=family, size=size, options=", ".join(str(s) for s in table)))
        return _i_section(f"{family} {size}", *table[size])
    found = re.fullmatch(r"([a-zñ]+(?:\s+[a-zñ]+)?)\s*([\d.,]+(?:\s*[x×]\s*[\d.,]+)*)", text.lower())
    word = " ".join(found.group(1).split()) if found else ""         # «tubo redondo»: two words
    if word in _KINDS:
        kind = _KINDS[word]
        numbers = [float(x.replace(",", ".")) for x in re.split(r"\s*[x×]\s*", found.group(2))]
        wanted = {"rect": 2, "tube": 3, "pipe": 2, "round": 1}[kind]
        if len(numbers) == wanted and all(x > 0 for x in numbers):
            return {"rect": _rectangle, "tube": _tube, "pipe": _pipe, "round": _round}[kind](text, *numbers)
    raise ShapeError(tr('I do not know the section «{text}». Write IPE 300, HEA 200, HEB 160, rect 200x400, tube '
                        '200x100x8, pipe 168x8 or round 50 (in mm), or a number of the catalogue (0 to {last}).').format(
        text=text, last=len(CATALOGUE) - 1))


@dataclass(frozen=True)
class Material:
    """Stiffness (E and G, in Pa), density (kg/m³) and strength (Pa): what a bar can take before it yields."""

    elasticity: float
    shear: float
    density: float
    strength: float


#: The materials, by their usual names.
MATERIALS = {
    'steel S235': Material(210e9, 81e9, 7850, 235e6),
    'steel S275': Material(210e9, 81e9, 7850, 275e6),
    'steel S355': Material(210e9, 81e9, 7850, 355e6),
    'timber C24': Material(11e9, 0.69e9, 420, 24e6),
    'glulam GL24h': Material(11.5e9, 0.65e9, 420, 24e6),
    'concrete C25/30': Material(31e9, 12.9e9, 2500, 25e6),
    'aluminium': Material(70e9, 26e9, 2700, 200e6),
}
