"""Ready-to-use functions (the Function node): shapes with a name and with their «what it is for».

A function takes a number (or two) and gives another: the height of a roof at each point, how much a rib sticks out,
how much a louvre turns. Here they come ready-made, with two measures an architect understands:

- **amplitude**: how much it rises;
- **width**: how often it repeats, or how big the shape is (the wavelength, the span, the radius).

    function("wave", x, amplitude=0.3, width=1.2)      → a 30 cm wave that repeats every 1.2 m
    function("saddle", x, y, amplitude=3, width=10)    → a hyperbolic paraboloid (Candela) of 10 × 10 m

Those of **one variable** give a profile (a wavy louvre, an arch); those of **two**, a surface (a roof, a relief, a
terrain).
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError, apply, require_numbers
from .language import tr

# Each function: (variables, what it is for, the computation with amplitude h and width w).
FUNCTIONS: dict[str, tuple[int, str, object]] = {
    # --- Of one variable: a profile ----------------------------------------------------------------
    'wave': (1, 'Wavy slats, lattices and walls; a rhythm that repeats every “width”.',
             lambda x, y, h, w: h * np.sin(2 * np.pi * x / w)),
    'ramp': (1, 'An even slope: rising “height” over “width” (a ramp, a mono-pitch roof).',
              lambda x, y, h, w: h * x / w),
    'parabola': (1, 'An arch with span “width” and rise “height” (vaults, bridges, a fountain jet).',
                 lambda x, y, h, w: h * (1 - (2 * x / w - 1) ** 2)),
    'catenary': (1, 'The shape of a hanging chain, upside down: the arch that works only in compression (Gaudí); span'
                    ' “width”, rise “height”.',
                  lambda x, y, h, w: _catenary(x, h, w)),
    'bell': (1, 'A soft, isolated bump: a relief that grows at one point and fades to the sides.',
                lambda x, y, h, w: h * np.exp(-0.5 * (x / (w / 4)) ** 2)),
    'stair step': (1, 'A smooth change of level: from 0 to “height” over a stretch of “width” (a step, a slope).',
                lambda x, y, h, w: h / (1 + np.exp(-8 * x / w))),
    'sawtooth': (1, 'Rises that start again: a sawtooth roof (sheds) for north light.',
                         lambda x, y, h, w: h * np.mod(x / w, 1.0)),
    # --- Of two variables: a surface -------------------------------------------------------------
    'swell': (2, 'A relief that waves in two directions: rib walls, ceilings, relief façades.',
            lambda x, y, h, w: h * np.sin(2 * np.pi * x / w) * np.cos(2 * np.pi * y / w)),
    'ripples': (2, 'Concentric ripples, like a stone thrown into water: floors, fountains, radial reliefs.',
              lambda x, y, h, w: h * np.cos(2 * np.pi * np.hypot(x, y) / w)),
    'hill': (2, 'A soft hill: a terrain, a roof that rises at one point, an attractor in height.',
               lambda x, y, h, w: h * np.exp(-0.5 * (np.hypot(x, y) / (w / 4)) ** 2)),
    'saddle': (2, "The hyperbolic paraboloid (saddle): Félix Candela's roofs; it is made of straight lines, though it"
                  ' looks curved.',
              lambda x, y, h, w: h * ((2 * x / w) ** 2 - (2 * y / w) ** 2)),
    'dome': (2, 'A dome (half sphere) of radius “width” / 2 and rise “height”.',
               lambda x, y, h, w: h * np.sqrt(np.clip(1 - (2 * np.hypot(x, y) / w) ** 2, 0, None))),
    'pyramid': (2, 'Four slopes rising towards the centre: a hip roof, a pyramid.',
                 lambda x, y, h, w: h * np.clip(1 - 2 * np.maximum(np.abs(x), np.abs(y)) / w, 0, None)),
}


def _catenary(x, h, w):
    """A catenary of span w (from 0 to w) and rise h: y = h · (cosh(k(x − w/2)) − cosh(k w/2)) / (1 − cosh(k w/2))."""
    k = 2.0 / np.maximum(np.asarray(w, dtype=float), 1e-9)          # a classic catenary shape, scaled
    middle = np.cosh(k * w / 2)
    return h * (middle - np.cosh(k * (x - w / 2))) / (middle - 1)


def from_a_variable() -> list[str]:
    return [n for n, (v, _, _) in FUNCTIONS.items() if v == 1]


def for_what(name: str) -> str:
    """What a function is for (for the node's panel)."""
    return tr(FUNCTIONS[name][1]) if name in FUNCTIONS else ""


def function(shape: str, x, y=None, amplitude=1.0, width=1.0, name: str | None = None) -> Data:
    """One of the functions of `FUNCTIONS`, with its amplitude and its width. `x` (and in those of two variables, `y`)
    are numbers or data with levels: with levels of different names a grid comes out (x × y)."""
    if shape not in FUNCTIONS:
        raise ShapeError(tr('I do not know the function “{shape}”. There are: {options}.').format(
                               shape=shape, options=", ".join(tr(f) for f in FUNCTIONS)))
    variables, _, tally = FUNCTIONS[shape]
    if x is None:
        raise ShapeError(tr('“x” is missing: the values where the function is calculated (a Series, some distances…).'))
    if variables == 2 and y is None:
        raise ShapeError(tr('“{shape}” is a two-variable function: connect “y” too (another Series, with '
                              'another level name, for a grid).').format(shape=tr(shape)))
    for role, v in (("x", x), ("y", y), ("amplitude", amplitude), ("width", width)):
        require_numbers(v, role)
    dx = x if isinstance(x, Data) else Data.value(np.asarray(x, dtype=float))
    dy = (y if isinstance(y, Data) else Data.value(np.asarray(0.0 if y is None else y, dtype=float)))
    dh = amplitude if isinstance(amplitude, Data) else Data.value(np.asarray(amplitude, dtype=float))
    dw = width if isinstance(width, Data) else Data.value(np.asarray(width, dtype=float))
    if np.any(np.asarray(dw.values, dtype=float) == 0):
        raise ShapeError(tr('The “width” cannot be 0: it is how often the shape repeats, or how big it is.'))
    if variables == 1:
        return apply(lambda a, h, w: tally(a, None, h, w), dx, dh, dw, name=name)
    return apply(lambda a, b, h, w: tally(a, b, h, w), dx, dy, dh, dw, name=name)
