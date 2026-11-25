"""Writing and reading values as an architect would (D2).

    text_value(0.4)             → "0,4"
    text_value([0, -0.3, 0])    → "(0; −0,3; 0)"
    read_value("0,4")           → 0.4
    read_value("120 cm")        → 1.2        (the engine keeps metres)
    read_value("(0; -0,3; 0)")  → [0, -0.3, 0]
    read_value("elevation")     → "elevation"
"""

from __future__ import annotations

import re

from .data import ShapeError
from .language import comma, tr
from .nodes import REQUIRED

# To metres (D2): the engine keeps metres. Any unit can be typed, also feet and
# inches (12' 6 1/2", 4.5', 150"); it is shown in the chosen UNIT.
UNITS = {"mm": 0.001, "cm": 0.01, "m": 1.0}
FOOT, INCH = 0.3048, 0.0254
#: What the lengths are shown in (Preferences): m, cm, mm, ft-in (feet and inches), ft or in.
#: To type, any of them; a plain number, in this unit (in feet and inches: inches).
UNIT = "m"
UNITS_VIEW = {"m": 1.0, "cm": 0.01, "mm": 0.001, "ft-in": INCH, "ft": FOOT, "in": INCH}
SYMBOLS = {"m": " m", "cm": " cm", "mm": " mm", "ft": "'", "in": "\""}
#: Decimals of the lengths: None = as many as needed (up to 4); a number = always those.
DECIMALS: int | None = None
#: Lengths in feet and inches are rounded to this fraction of an inch (as on a drawing).
FRACTION = 16


def imperial() -> bool:
    return UNIT in ("ft-in", "ft", "in")

_IMPERIAL = re.compile(
    r"""^\s*(?P<signo>[-−])?\s*
        (?:(?P<pies>\d+(?:[.,]\d+)?)\s*(?:'|′|ft)\s*-?\s*)?
        (?:(?P<pulg>\d+(?:[.,]\d+)?)?\s*(?:(?P<num>\d+)\s*/\s*(?P<den>\d+))?\s*(?:"|″|''|in))?
        \s*$""", re.VERBOSE)


def read_imperial(text: str) -> float | None:
    """«12' 6 1/2"», «12'-6"», «4.5'», «150"», «1/2"» → metres; None if it is not in feet and inches."""
    m = _IMPERIAL.match(text)
    if not m or not (m["pies"] or m["pulg"] or m["num"]):
        return None
    if not m["pies"] and not re.search(r'["″]|\'\'|in\s*$', text):
        return None                                  # a plain number is not imperial
    def num(x):
        return float(x.replace(",", ".")) if x else 0.0
    inches = num(m["pulg"]) + (num(m["num"]) / num(m["den"]) if m["num"] and float(m["den"]) else 0.0)
    metres = num(m["pies"]) * FOOT + inches * INCH
    return -metres if m["signo"] else metres


def text_imperial(metres: float, fraction: int | None = None) -> str:
    """Metres in feet and inches, as on a drawing: 12'-6 1/2" (rounded to 1/16", or to FRACTION)."""
    from math import gcd
    fraction = fraction or FRACTION
    sign = "−" if metres < 0 else ""
    parts = round(abs(metres) / INCH * fraction)          # in 1/16 of an inch
    feet, rest = divmod(parts, 12 * fraction)
    inches, n = divmod(rest, fraction)
    text_inch = str(inches) if inches or not n or feet else ""   # 59'-0 11/16", not 59'-11/16"
    if n:
        d = gcd(n, fraction)
        text_inch = (f"{text_inch} " if text_inch else "") + f"{n // d}/{fraction // d}"
    if not text_inch:
        text_inch = "0"
    return f"{sign}{feet}'-{text_inch}\"" if feet else f"{sign}{text_inch}\""


def text_length(metres: float) -> str:
    """A length in the chosen unit: 0,4 · 40 cm · 400 mm · 1'-3 3/4" · 1,31' · 15,75"."""
    if UNIT == "ft-in":
        return text_imperial(metres)
    v = metres / UNITS_VIEW[UNIT]
    if DECIMALS is None:
        text = text_value(v)
    else:
        text = comma(f"{v:.{DECIMALS}f}").replace("-", "−")
    return text + SYMBOLS[UNIT]


def text_point(p) -> str:
    """A point in the chosen unit, the unit once at the end: (4,4; 4,4; 0) m · (440; 440; 0) cm; in feet and inches,
    each coordinate with its own marks."""
    if UNIT == "ft-in":
        return "(" + "; ".join(text_length(round(float(c), 6)) for c in p) + ")"
    symbol = SYMBOLS[UNIT]
    return "(" + "; ".join(text_length(round(float(c), 6)).removesuffix(symbol) for c in p) + ")" + symbol


def is_length(node, input_: str) -> bool:
    """Whether an input of a node is a length (shown and typed in the chosen unit): the usual ones (width, radius,
    distance…) and the positions of Points on curve in «distance» mode."""
    from .legacy_names import input_name
    input_ = input_name(input_)
    if unit_of(input_) == "m":
        return True
    inputs = getattr(node, "inputs", {})
    if input_ == "at":                                  # Tangent circle: «at» a distance
        return inputs.get("size") == 'distance'
    return input_ == "positions" and inputs.get("mode") == 'distance'


def text_of(input_: str, v, length: bool | None = None) -> str:
    """The fixed value of an input, on screen: the lengths, in the chosen unit; some drawn points, how many they
    are. `length`: whether it is one (by default, by the input's name)."""
    from .legacy_names import input_name
    input_ = input_name(input_)
    if isinstance(v, str) and (input_ in ("level", "along") or input_.startswith("level_") or input_.endswith("_level")):
        return tr(v)                                     # the name of a level, in the language of the interface
    if input_ == "code" and isinstance(v, str):                      # the code of a Code node: how long it is
        n = len([line for line in v.splitlines() if line.strip()])
        return tr('1 line') if n == 1 else tr('{n} lines').format(n=n)
    if input_ == "moves" and isinstance(v, (list, tuple)):           # the vertices moved by hand (Edit mesh)
        return tr('no vertex moved') if not v else tr('1 vertex moved') if len(v) == 1 else \
            tr('{n} vertices moved').format(n=len(v))
    if input_ == "hand_supports" and isinstance(v, (list, tuple)):   # the supports moved by hand (Equilibrium)
        return tr('no support by hand') if not v else tr('1 support by hand') if len(v) == 1 else \
            tr('{n} supports by hand').format(n=len(v))
    if input_ == "stroke" and isinstance(v, (list, tuple)):          # the pen's anchors
        return tr('no anchors') if not v else tr('1 anchor') if len(v) == 1 else tr('{n} anchors').format(n=len(v))
    if isinstance(v, (list, tuple)) and (not v and input_ == "points" or v and isinstance(v[0], (list, tuple))):
        return tr('no points') if not v else tr('1 point') if len(v) == 1 else tr('{n} points').format(n=len(v))
    if length is None:
        length = unit_of(input_) == "m"
    if length and isinstance(v, (int, float)) and not isinstance(v, bool):
        return text_length(v)
    if length and isinstance(v, (str, list, tuple)):     # several lengths: «2; −2» in the chosen unit
        numbers = read_numbers(v) if isinstance(v, str) else list(v)
        if numbers and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in numbers):
            return "; ".join(text_length(x) for x in numbers)
    return text_value(v)


def read_lengths(text: str):
    """One or several typed lengths (each with its unit or in the chosen one), in metres: a number if it is one;
    «2; −2» (in metres) if there are several."""
    parts = _parts(text)
    if parts is None or len(parts) == 1:
        return read_length(text)
    metres = [read_length(p) for p in parts]
    if not all(isinstance(m, (int, float)) for m in metres):
        return read_value(text)
    return "; ".join(text_value(m) for m in metres)


def read_length(text: str):
    """What is typed in a length box, in metres: with its unit (120 cm, 4'), or a plain number in the chosen unit
    (40 with centimetres is 0.4 m; with feet and inches, 40 are inches)."""
    t = text.strip()
    m = _NUMBER.match(t)
    if m and m.group(2) is None:                     # a plain number: in the view's unit
        return round(float(m.group(1).replace("−", "-").replace(",", ".")) * UNITS_VIEW[UNIT], 9)
    return read_value(t)

_NUMBER = re.compile(r"^\s*([+\-−]?\d+(?:[.,]\d+)?)\s*(mm|cm|m|°)?\s*$")


def text_value(v) -> str:
    """A fixed value, as an architect would write it: 0,4 · (0; −0,3; 0)."""
    if v is REQUIRED:
        return tr("missing")
    if v is None:
        return ""
    if isinstance(v, bool):
        return tr("yes") if v else tr("no")
    if isinstance(v, (int, float)) or hasattr(v, "dtype"):  # numpy numbers too
        if hasattr(v, "dtype") and v.dtype == bool:
            return tr("yes") if v else tr("no")
        return comma(f"{round(float(v), 4):.10g}").replace("-", "−")  # up to 4 decimals
    if isinstance(v, (list, tuple)):
        return "(" + "; ".join(text_value(x) for x in v) + ")"
    return str(v)


#: What the result of some nodes measures (to show it with its unit: m, m², m³; or ft, ft², ft³…).
MAGNITUDE_NODE = {'Area': "area", 'Volume': "volume", 'Distance': "length", 'Length': "length"}
_POWER = {"area": (2, "²"), "volume": (3, "³")}


def text_measure(value: float, magnitude: str | None) -> str:
    """A result with its unit, in the chosen one: 80 m² · 861,11 ft² · 400 m³ · 4,4 m · 14'-5 1/4"."""
    if magnitude == "length":
        return text_length(value)
    if magnitude in _POWER:
        n, exponent = _POWER[magnitude]
        base = {"ft-in": "ft"}.get(UNIT, UNIT)           # in feet and inches, the area goes in ft²
        factor = {"ft": FOOT, "in": INCH}.get(base, UNITS_VIEW.get(base, 1.0))
        v = value / factor ** n
        text = text_value(v) if DECIMALS is None else comma(f"{v:.{DECIMALS}f}").replace("-", "−")
        return f"{text} {base}{exponent}"
    return text_value(value)


def lines_of(data, maximum: int = 12, magnitude: str | None = None) -> list[str]:
    """What a result is worth, one line per element (for the Panel node): «ring 2: 12,57 m²».
    `magnitude`: «length», «area» or «volume», to give it its unit; the points, in the chosen unit."""
    import numpy as np
    from .data import Data
    from .geometry import POINT
    if not isinstance(data, Data):
        return [text_value(data)]
    levels = data.levels
    shape = data.values.shape[:len(levels)]
    mask = np.broadcast_to(data.mask, shape) if levels else None
    lines, total = [], 0
    for index in np.ndindex(shape):
        if mask is not None and not mask[index]:
            continue
        total += 1
        if len(lines) >= maximum:
            continue
        v = data.values[index]
        if data.kind is POINT:
            text = text_point(v)
        elif data.kind is not None:
            text = tr(data.kind.name)
        elif np.ndim(v) == 0 and data.values.dtype != bool:
            text = text_measure(float(v), magnitude)
        else:
            text = text_value(v.item() if hasattr(v, "item") and np.ndim(v) == 0 else (
                v.tolist() if isinstance(v, np.ndarray) else v))
        label = " · ".join(f"{tr(n)} {data.starts.get(n, 0) + i}" for n, i in zip(levels, index))
        lines.append(f"{label}: {text}" if label else text)
    if total > maximum:
        lines.append(tr('… and {n} more').format(n=total - maximum))
    return lines


def read_value(text: str):
    """The opposite of `text_value`: the text the user typed, as a value."""
    t = text.strip()
    if not t:
        return None
    if t.lower() in ("yes", "sí", "si"):
        return True
    if t.lower() == "no":
        return False
    if t[0] in "([" and t[-1] in ")]":
        parts = [p for p in re.split(r"[;]", t[1:-1])] if ";" in t else t[1:-1].split(",")
        return [_number(p, text) for p in parts]
    if _NUMBER.match(t):
        return _number(t, text)
    imperial = read_imperial(t)
    if imperial is not None:
        return round(imperial, 9)
    if ";" not in t:
        numbers = read_numbers(t)
        if numbers is not None and len(numbers) == 3:     # a point without parentheses: «0,0,0» · «8, 0, 0» · «8 0 0»
            return numbers
        if numbers is not None and len(numbers) > 1:      # a list: it stays written with «;» («2,-2» → «2; -2»)
            return "; ".join(text_value(n) for n in numbers)
    return t


def read_numbers(text: str) -> list | None:
    """One or several numbers written however they come; None if something is not a number.

    Not to clash with the decimal comma:
    - «;» always separates: «0,5; 2; -1» · «(0; 0; 0)»;
    - a comma followed by a space separates: «2, -2» · «0,25, 0,75»;
    - two or more commas without spaces separate: «0,0,0» · «2,-2,5»;
    - a comma followed by a sign separates: «2,-2»;
    - spaces separate: «2 -2» · «0,5 0,75»;
    - a single comma between digits is decimal: «0,5».
    """
    parts = _parts(text)
    if parts is None:
        return None
    try:
        return [_number(p, text) for p in parts]
    except ShapeError:
        return None


def _parts(text: str) -> list[str] | None:
    """The pieces of a text with one or several numbers (see `read_numbers`)."""
    t = text.strip()
    if t[:1] in "([" and t[-1:] in ")]":
        t = t[1:-1].strip()
    if not t:
        return None
    if read_imperial(t) is not None:            # 12' 6 1/2": a single length, though it has spaces
        return [t]
    if ";" in t:
        parts = t.split(";")
    elif re.search(r",\s", t):
        parts = re.split(r",\s+", t)
    elif t.count(",") >= 2 and not re.search(r"\s", t):
        parts = t.split(",")
    elif re.search(r",(?=[+\-−])", t):
        parts = re.split(r",(?=[+\-−])", t)
    else:
        parts = re.split(r"\s+(?![mc]?m\b|°)", t)       # «120 cm» is a number with its unit
    parts = [p.strip() for p in parts if p.strip()]
    return parts or None


def _number(part: str, original: str):
    m = _NUMBER.match(part)
    if not m and read_imperial(part) is not None:
        return round(read_imperial(part), 9)
    if not m:
        raise ShapeError(tr('“{text}” cannot be read as a number (for example: 0.4 · 120 cm · (0; −0.3; 0)).').format(
                               text=original.strip()))
    digit, unit = m.group(1).replace("−", "-").replace(",", "."), m.group(2)
    value = float(digit)
    if unit in UNITS:
        value *= UNITS[unit]
        value = round(value, 9)
    return int(value) if value.is_integer() and "." not in digit and unit in (None, "°", "m") else value


#: The inputs that are lengths (shown and written in the chosen unit).
LENGTHS = {"width", "height", "depth", "x", "y", "z", "distance", "thickness", "size", "cell_width", "cell_height",
           "radius", "fillet", "length", "reach"}


def label_input(name: str) -> str:
    """How an input is written on screen: «cell width» (in Spanish, «ancho celda»)."""
    from .language import tr
    from .legacy_names import input_name
    return tr(input_name(name).replace("_", " "))


def unit_of(input_: str) -> str:
    """The unit an input is shown with (for a new slider)."""
    from .legacy_names import input_name
    input_ = input_name(input_)
    if input_ in ("rotation", "degrees"):
        return "°"
    return "m" if input_ in LENGTHS else ""
