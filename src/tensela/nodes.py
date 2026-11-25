"""The catalogue of nodes (step 1.4a).

Each node kind has an architect's name (D4), some named inputs and a single output. Inside it calls the functions
of `data` and `geometry`; the node's name becomes the name of its result, so the error messages speak of «panels» or
«facade», not of variables.

Principle: few nodes that are understood (CONCEPTO.md). Each new node has to come out of a case of the catalogue.
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from . import geometry as geo
from . import functions as fun, meshes as meshes, measures as measures
from . import images
from . import printing
from . import fabrication as fab
from . import bevel as bevel_module
from . import simulation as sim
from . import frames as fra
from . import sections as sec
from . import topology as top
from . import labels
from . import strokes
from . import sun as sn
from . import shadows as sha
from . import insolation as ins
from . import climate as cli
from . import daylight as day
from . import geodesics as geod
from . import hypar as hyp
from . import planarize as pln
from . import plates as pla
from . import mesh_tools
from . import polygons as pol
from . import unrolling as des
from . import structures as est
from . import surfaces as sup
from .data import (COMBINATIONS, COMPARISONS, MODES_FILTER, SPLIT_MODES, MODES_REORDER, Data, ShapeError, on_random,
                    combine_conditions, compare, pick, choose, filter_, filter_mode, split, join_levels, reduce, reorder,
                    repeat, series)
from .formula import formula as compute_formula
from .language import tr


class _Required:
    def __repr__(self) -> str:
        return "required"


REQUIRED: Any = _Required()


@dataclass(frozen=True)
class Input:
    """An input of a node kind."""

    name: str
    default: Any = REQUIRED
    # A single value (a number, a text), not a data with levels: the number
    # of columns, the name of a level. If a data arrives, it is unwrapped.
    single: bool = False
    help: str = ""
    # The values it accepts (chosen from a list in the window)…
    options: tuple[str, ...] = ()
    # …or the name of another input whose levels are the options (e.g. «along»: a level of «points»).
    levels_of: str | None = None
    # It is hidden on the card while it is empty and the formula does not use it (the variables e … h).
    hidden_if_empty: bool = False
    # It is shown only if this, with the node's inputs, gives true (the «level» of a Number list).
    visible_if: Callable[[dict], bool] | None = None
    # It goes in «More settings» of the panel (closed at first): what hardly ever needs touching.
    advanced: bool = False
    # A file to read ("image"): the panel offers a button to choose it, and keeps its path relative to the project.
    file: str = ""
    # Which of the options make sense with the node's inputs (the panel offers only those): «outline» of a Shadow,
    # only on the ground.
    options_if: Callable[[dict], tuple] | None = None
    # Names offered in a list, though any other can be written (the installed fonts of a Text): a function that
    # gives them, asked when the list opens.
    suggest: Callable[[], list] | None = None


def options_of(node, input_: Input) -> list[str]:
    """The options the panel offers for an input: all, or those that make sense with the other inputs (and the one
    chosen, even if it does not: so it is seen, with its notice)."""
    options = list(input_.options)
    if input_.options_if is not None:
        allowed = set(input_.options_if(node.inputs))
        current = node.inputs.get(input_.name)
        options = [o for o in options if o in allowed or o == current]
    return options


def _font_families() -> list[str]:
    from .fonts import families
    return families()


@dataclass(frozen=True)
class NodeType:
    name: str
    category: str
    inputs: tuple[Input, ...]
    output: str
    function: Callable[..., Data]
    help: str = ""
    synonyms: tuple[str, ...] = ()
    extension: str = ""          # the extension that brings it (extensions.py); "" for those of Tensela

    def input_(self, name: str) -> Input:
        for e in self.inputs:
            if e.name == name:
                return e
        from .legacy_names import INPUTS                # an old Spanish name (old project, old code)
        new_ = INPUTS.get(self.name, {}).get(name)
        for e in self.inputs:
            if e.name == new_:
                return e
        from .values import label_input      # here: values uses this module
        available = ", ".join(label_input(e.name) for e in self.inputs)
        raise ShapeError(tr('“{name}” has no input “{input}”. It has: {available}.').format(
                               name=tr(self.name), input=name, available=available))


CATALOG: dict[str, NodeType] = {}

#: Synonyms that are names of other programs: typing them still finds the node (whoever knows that name looks for
#: it), but the finder does not print them next to the node.
PROGRAM_NAMES = frozenset({
    "Kangaroo", "Karamba", "Millipede", "Topostruct", "Ladybug", "Honeybee", "Radiance", "GECO", "Ecotect",
    "EcoLightCal", "EcoSolCal", "EcoSunPath", "EcoSunRays", "EcoWeatherFile", "Galapagos", "Grasshopper", "Rhino",
})


def _register(kind: NodeType) -> None:
    t = _in_english(kind)
    CATALOG[t.name] = t


def _in_english(t: NodeType) -> NodeType:
    """A node type as registered: its function receives «from» as «from_» (a Python keyword), and its old Spanish
    name stays as a synonym (search, old projects)."""
    from . import legacy_names as R
    name = R.NODES.get(t.name, t.name)
    new = list(t.inputs)
    function_raw = t.function

    def function(**arguments):
        name_data = arguments.pop("name", None)
        arguments = {(k + "_" if keyword.iskeyword(k) else k): v for k, v in arguments.items()}
        return function_raw(**arguments, name=name_data)       # («from» is written «from_» in Python)

    return NodeType(name, R.CATEGORIES.get(t.category, t.category), tuple(new),
                      R.OUTPUTS.get(t.output, t.output), function, t.help,
                      tuple(dict.fromkeys((*(old for old, new_ in R.NODES.items() if new_ == name),
                                           t.name, *t.synonyms))), t.extension)


# The essentials (D10): those that come first in the finder and are enough to
# start. No more than about 30.
ESSENTIALS = (
    'Number', 'Formula', 'Series', 'Point',
    'Line', 'Circle', 'Curve through points', 'Points on curve', 'Transition curve',
    'Loft', 'Extrude',
    'Rectangle', 'Box', 'Prism',
    'Grid', 'Divide', 'Centre', 'Faces', 'Pick',
    'Distance', 'Remap', 'Summarise', 'Compare', 'Filter',
    'Move', 'Rotate', 'Scale', 'Place', 'Thicken', 'Frame',
)


def visible_input(node, input_: Input) -> bool:
    """Whether the input is shown on the card and in the panel (the variables e … h, only if they are used). One
    that is connected is always shown: hidden, its wire would end in the air."""
    if _connected(node.inputs.get(input_.name)):
        return True
    if input_.visible_if is not None:
        # A choice that comes connected (a «mode» wired to another node) counts as its default for what it shows.
        inputs = dict(node.inputs)
        inputs.update({e.name: e.default for e in node.kind.inputs if e.options and _connected(inputs.get(e.name))})
        return input_.visible_if(inputs)
    if not input_.hidden_if_empty:
        return True
    v = node.inputs.get(input_.name)
    if v is not None:
        return True
    code = node.inputs.get("code")
    if isinstance(code, str):                      # a Code node: the letters its code reads (not those in comments)
        from .code_check import names_used
        return input_.name in names_used(code)
    text = node.inputs.get("formula")
    return isinstance(text, str) and re.search(rf"\b{input_.name}\b", text) is not None


def _connected(v) -> bool:
    return hasattr(v, "graph") and hasattr(v, "kind") and hasattr(v, "inputs")


def automatic_level(node, input_: str) -> str | None:
    """Which level is used when a level input («level», «along») is left empty, to say so on the card and in the
    panel: «point» (the only one), «the direction of the curve», «all»… None if it is not known."""
    e = node.kind.input_(input_)
    if not e.levels_of:
        return None
    origin = node.inputs.get(e.levels_of)
    value = getattr(origin, "_value", origin)
    levels = getattr(value, "levels", None)
    if levels is None:
        return None
    kind = node.kind.name
    if kind in ('Reorder', 'Filter', 'Split', 'Repeat'):          # empty: the only level there is
        if len(levels) == 1:
            return levels[0]
        if not levels and kind == 'Reorder' and value.kind is not None and value.kind.curve:
            return tr('the curve direction')
        return None
    if kind == 'Summarise':
        return tr('all')
    if kind == 'Join levels':                                      # the first one outside, the last one inside
        if len(levels) < 2:
            return None
        first = node.inputs.get('first') or levels[0]
        if input_ == 'first':
            return first
        return next((n for n in reversed(levels) if n != first), None)
    return levels[-1] if levels else None                          # empty: the last level


def node_kind(name: str) -> NodeType:
    """Finds a node kind by its name or by a synonym."""
    if name in CATALOG:
        return CATALOG[name]
    from .legacy_names import NODES                     # an old Spanish name (before its synonyms in other nodes)
    if NODES.get(name) in CATALOG:
        return CATALOG[NODES[name]]
    for kind in CATALOG.values():
        if name.lower() in (s.lower() for s in (kind.name, *kind.synonyms)):
            return kind
    raise ShapeError(tr("I don't know the node “{name}”. There are: {options}.").format(
                           name=name, options=', '.join(tr(o) for o in CATALOG)))


# --- Valores -----------------------------------------------------------------

def _is_items(value) -> bool:
    if isinstance(value, (list, tuple)) or (isinstance(value, str) and ";" in value):
        return True
    if isinstance(value, str):                   # «2, -2» · «2,-2» · «2 -2»: a list too
        from .values import read_numbers
        numbers = read_numbers(value)
        return numbers is not None and len(numbers) > 1
    return False


def number(value, level=None, name=None) -> Data:
    """A number, or a list written by hand («3,5; 3; 3; 4») as a level with its name."""
    if not _is_items(value):
        if isinstance(value, str):
            from .values import read_value
            value = read_value(value)
        try:
            return Data.value(float(value), name)
        except (TypeError, ValueError):
            raise ShapeError(tr('“{value}” is not a number. For several, separate them with “;”: 3.5; 3; 3; 4.').format(
                                   value=value)) from None
    if isinstance(value, str):
        from .values import read_value
        value = read_value(f"({value.strip().strip('()')})")
    try:
        values = [float(v) for v in value]
    except (TypeError, ValueError):                       # a list inside the list (only a damaged file has it)
        raise ShapeError(tr('The list must hold numbers only, separated by “;”, like 3.5; 3; 3; 4.')) from None
    if not values:
        raise ShapeError(tr('The list is empty: write the values separated by “;”, like 3.5; 3; 3; 4.'))
    return Data(np.array(values), (str(level or "value"),), name)


_register(NodeType(
    'Number', 'Values',
    (Input('value', 0.0, help='a number (a slider in the window), or several separated by “;”: 3.5; 3; 3; 4'),
     Input('level', "value", single=True, help='the name of the list: floor, bay, axis…',
             visible_if=lambda e: _is_items(e.get('value')))),
    'number',
    number,
    'A fixed number you can change by hand, or a list of values typed by hand (different floor heights, bay '
    'widths): 3.5; 3; 3; 4.',
    ("Deslizador", "Valor", "Valores", "Lista", "Números"),
))

_register(NodeType(
    'Formula', 'Values',
    (Input('formula', "a", single=True, help='as in a spreadsheet: a * 3.5 · if(a < 5; 90; 0) · sin(a)'),
     Input('a', None), Input('b', None), Input('c', None), Input('d', None),
     *(Input(v, None, hidden_if_empty=True, help='appears when you write it in the formula') for v in "efgh")),
    'result',
    lambda formula, a, b, c, d, e, f, g, h, name: compute_formula(formula, a, b, c, d, e, f, g, h, name),
    'A calculation with a … h, as in a spreadsheet (angles in degrees). Variables e … h appear when you use them.',
    ("Expresión", "Expression", "Cuenta", "Calcular", "Operación", "Multiplicar", "Sumar"),
))

#: The code a new Code node starts with: something to see (a wave of points). How it is written is told by the
#: editor («What can I use?»), in the language of the interface.
CODE_AT_FIRST = "result = [point(i, 0, sin(i * 30)) for i in range(13)]\n"


def _run_code(code, a, b, c, d, e, f, g, h, levels, name):
    """The code runs apart from Tensela, in its helper (code_worker.py): watched and with limits."""
    from .code_worker import helper
    return helper().run(code, dict(zip("abcdefgh", (a, b, c, d, e, f, g, h))), levels, name)


_register(NodeType(
    'Code', 'Values',
    (Input('code', CODE_AT_FIRST, single=True,
           help='a short piece of Python: it works with numbers, lists, points, lines and meshes, and leaves what it '
                'computes in «result»'),
     *(Input(v, None, hidden_if_empty=v not in "ab", help='what is connected here reaches the code under this letter '
                                                          '(c … h appear when the code uses them)') for v in "abcdefgh"),
     Input('levels', "element", single=True, advanced=True,
           help='the name of the list the code gives; for lists inside lists, one name each, separated by «;» '
                '(row; column)')),
    'result',
    _run_code,
    'Your own piece of Python, for what the nodes do not reach: loops, functions that call themselves, a rule of '
    'your own. It only works with what Tensela has (numbers, lists, points, lines, meshes, mathematics): no '
    'files, no network, no other programs. Short pieces: up to 200 lines.',
    ("Script", "Python", "Mi código", "My code", "Programa", "Programar", "Macro", "Código propio"),
))

_register(NodeType(
    'Random', 'Values',
    (Input('mode', 'per element', single=True, options=('per element', 'count'),
             help='per element: one per element of some data · amount: so many loose numbers'),
     Input('data', None, visible_if=lambda e: e.get('mode', 'per element') == 'per element'),
     Input('along', None, single=True, help='one number for each… (cell, row…); empty = the first level',
             levels_of='data', visible_if=lambda e: e.get('mode', 'per element') == 'per element'),
     Input('count', 10, single=True, visible_if=lambda e: e.get('mode') == 'count'),
     Input('level', "element", single=True, help='name of the new level (the same as another list, to pair them)',
             visible_if=lambda e: e.get('mode') == 'count'),
     Input('minimum', 0.0), Input('maximum', 1.0),
     Input('integers', False, single=True, help='yes: whole numbers, from minimum to maximum (both included)'),
     Input('seed', 1, single=True, help='another seed, other numbers (the same one, the same numbers)')),
    'value',
    lambda mode, data, along, count, level, minimum, maximum, integers, seed, name: on_random(
        data, along, minimum, maximum, seed, name, mode, count, level, bool(integers)),
    'Random numbers: one per element of some data, or a loose amount (“20 between 1 and 5”).',
    ("Aleatorio", "Random", "Random Split", "Sorteo", "Azar", "Jitter", "Números al azar"),
))

_register(NodeType(
    'Series', 'Values',
    (Input('count', 10, single=True),
     Input('mode', 'with step', single=True, options=('with step', 'between two'),
             help='with step: from the start, so much at a time · between two: spread from the start to “to”'),
     Input('start', 0, single=True), Input('step', 1, single=True, visible_if=lambda e: e.get('mode', 'with step') == 'with step'),
     Input('to', 1, single=True, help='the last number (included)', visible_if=lambda e: e.get('mode') == 'between two'),
     Input('level', "element", single=True, help='name of the new level: floor, step, axis…')),
    'series',
    lambda count, mode, start, step, to, level, name: series(count, start, step, level, name, mode, to),
    'A series of numbers that creates a level: 25 floors, 12 steps; with a step, or spread between two values.',
    ("Series", "Range", "Rango de números", "Pisos", "Dominio", "Domain", "Secuencia", "Linspace"),
))

_register(NodeType(
    'Point', 'Values',
    (Input('x', 0.0), Input('y', 0.0), Input('z', 0.0)),
    'point',
    lambda x, y, z, name: geo.point(x, y, z, name),
    'A point, or many if a coordinate has levels.',
    ("Atractor",),
))

# --- Formas ------------------------------------------------------------------

_register(NodeType(
    'Random points', 'Shapes',
    (Input('region'), Input('count', 10, single=True),
     Input('seed', 1, single=True, help='another seed, other points (the same one, the same points)'),
     Input('level', "point", single=True, help='name of the points level')),
    'points',
    lambda region, count, seed, level, name: pol.points_random(region, count, seed, level, name),
    'Random points inside a volume (a box, a prism) or a rectangle (in plan or in elevation).',
    ("Poblar", "Populate 3D", "Populate 2D", "Populate", "Aleatorio", "Random"),
))

_register(NodeType(
    'Rectangle', 'Shapes',
    (Input('width', 4.0), Input('height', 3.0), Input('origin', (0.0, 0.0, 0.0)),
     Input('plane', 'plan', single=True, help='plan, elevation or side', options=('plan', 'elevation', 'side elevation'))),
    'rectangle',
    lambda width, height, origin, plane, name: geo.rectangle(width, height, origin, plane, name),
    'A rectangle with its lower-left corner at the origin.',
    ("Fachada", "Plano"),
))

_register(NodeType(
    'Box', 'Shapes',
    (Input('width', 2.0), Input('depth', 2.0), Input('height', 2.0)),
    'box',
    lambda width, depth, height, name: geo.box(width, depth, height, name),
    'A box centred on the origin.',
    ("Prisma", "Bloque", "Quiebrasol", "Lama"),
))

_register(NodeType(
    'Bounding box', 'Shapes',
    (Input('geometry', help='what to wrap'),
     Input('of', 'all', single=True, options=geo.BOUNDING,
           help='all: one box around everything · each: one box around each element')),
    'box',
    lambda geometry, of, name: geo.bounding_box(geometry, of, name),
    'The box that wraps a geometry, aligned with the axes: its size, where it is, or the cell to deform it with '
    'Morph (move its corners and fit the geometry into them).',
    ("Bounding Box", "BBox", "Caja envolvente", "Caja contenedora", "Envolvente", "Extensión", "Límites"),
))

_register(NodeType(
    'Prism', 'Shapes',
    (Input('width', 4.0, help='east-west (X)'), Input('depth', 3.0, help='north-south (Y)'), Input('height', 3.0),
     Input('origin', (0.0, 0.0, 0.0), help='lower south-west corner')),
    'prism',
    lambda width, depth, height, origin, name: geo.prism(width, depth, height, origin, name),
    'A straight volume; its faces are asked for by name with “Faces”.',
    ("Volumen", "Cubo", "Edificio", "Extruir rectángulo"),
))

# --- Curvas ------------------------------------------------------------------

_register(NodeType(
    'Line', 'Curves',
    (Input('from'), Input('to')),
    'line',
    lambda from_, to, name: geo.line(from_, to, name),
    'A straight line between two points (or many, if the points have levels).',
    ("Recta", "Segmento", "Line"),
))

_register(NodeType(
    'Line by direction', 'Curves',
    (Input('from'), Input('direction', (0.0, 0.0, 1.0), help='which way it goes; by default, upwards (0, 0, 1)'),
     Input('length', 1.0, help='how long it is; negative, the other way')),
    'line',
    lambda from_, direction, length, name: geo.line_by_direction(from_, direction, length, name),
    'A line from a point, in a direction and with a length: a mast, a column, a perpendicular.',
    ("Line SDL", "Línea SDL", "Perpendicular", "Mástil", "Pilar", "Vertical", "Línea hacia arriba"),
))

_register(NodeType(
    'Arc', 'Curves',
    (Input('mode', 'three points', single=True, options=geo.MODES_ARC,
             help='three points: start, one it passes through and end · centre and angles: centre, radius and '
                   'from which angle to which · start, direction and end: leaves tangent to a direction '
                   '(continues a curve without a kink)'),
     Input('start', (0.0, 0.0, 0.0), visible_if=lambda e: e.get('mode', 'three points') in ('three points',
                                                                                                'start, direction and end')),
     Input('direction', (1.0, 0.0, 0.0), help='where the arc leaves the start towards (a vector: the Tangent of a curve, to continue it)',
             visible_if=lambda e: e.get('mode') == 'start, direction and end'),
     Input('middle', (2.0, 1.0, 0.0), help='a point the arc passes through',
             visible_if=lambda e: e.get('mode', 'three points') == 'three points'),
     Input('end', (4.0, 0.0, 0.0), visible_if=lambda e: e.get('mode', 'three points') in ('three points',
                                                                                            'start, direction and end')),
     Input('centre', (0.0, 0.0, 0.0), visible_if=lambda e: e.get('mode') == 'centre and angles'),
     Input('radius', 2.0, visible_if=lambda e: e.get('mode') == 'centre and angles'),
     Input('from', 0.0, help='the start angle (degrees; 0° towards +X)',
             visible_if=lambda e: e.get('mode') == 'centre and angles'),
     Input('to', 90.0, help='the end angle (degrees, counter-clockwise)',
             visible_if=lambda e: e.get('mode') == 'centre and angles'),
     Input('plane', 'plan', single=True, help='plan, elevation or side', options=('plan', 'elevation', 'side elevation'),
             visible_if=lambda e: e.get('mode') == 'centre and angles')),
    'arc',
    lambda mode, start, direction, middle, end, centre, radius, from_, to, plane, name: geo.arc(
        mode, start, middle, end, centre, radius, from_, to, plane, name, direction),
    'A circular arc: through three points, with its centre, radius and angles, or leaving tangent to a direction.',
    ("Arc", "Arc 3Pt", "Arc SED", "Arco por tres puntos", "Bóveda", "Medio punto", "Arco de medio punto",
     "Arco tangente", "Tangent Arc"),
))

_register(NodeType(
    'Catenary', 'Curves',
    (Input('start', (0.0, 0.0, 0.0), help='where the cable hangs from'),
     Input('end', (4.0, 0.0, 0.0), help='where it hangs from at the other end'),
     Input('length', 5.0, help='of the cable: longer, it sags more; shorter than the distance, it stays taut (straight)'),
     Input('length_in', 'metres', single=True, options=geo.LENGTHS_CATENARY,
           help='metres · times the distance between the ends (1.2: a fifth longer), for many cables between points '
                'that are more or less apart'),
     Input('gravity', (0.0, 0.0, -1.0),
           help='where it hangs towards (a vector) · upwards, (0, 0, 1): the arch that works only in compression')),
    'catenary',
    lambda start, end, length, length_in, gravity, name: geo.catenary(start, end, length, gravity, length_in, name),
    'The exact shape of a chain or a cable hanging from two points: give its length and it sags just as the real one. '
    'Upside down (gravity upwards) it is the arch or the vault that works only in compression, as Gaudí found with his '
    'hanging models. Its points are evenly spaced along it.',
    ("Catenary", "Cat", "Catenaria", "Cadena", "Chain", "Hanging chain", "Cadena colgada", "Cable", "Cable colgado",
     "Funicular", "Arco funicular", "Arco catenario", "Gaudí"),
))

_register(NodeType(
    'Circle', 'Curves',
    (Input('mode', 'centre and radius', single=True, options=geo.MODES_CIRCLE,
             help='centre and radius · tangent to a curve: touches it at a point, without crossing it'),
     Input('centre', (0.0, 0.0, 0.0), visible_if=lambda e: e.get('mode', 'centre and radius') == 'centre and radius'),
     Input('curve', None, help='the curve the circle touches',
             visible_if=lambda e: e.get('mode') == 'tangent to a curve'),
     Input('at', 0.5, help='where it touches: a fraction from 0 to 1 (0.5 the middle), or a distance (with '
                              '«measure»); several with «;»', visible_if=lambda e: e.get('mode') == 'tangent to a curve'),
     Input('size', 'fraction', single=True, options=('fraction', 'distance'),
             help='«at» as a fraction of the length or as a distance from the start (negative: from the end)',
             visible_if=lambda e: e.get('mode') == 'tangent to a curve'),
     Input('side', 'left', single=True, options=geo.SIDES,
             help='which side of the curve, looking where it goes',
             visible_if=lambda e: e.get('mode') == 'tangent to a curve'),
     Input('radius', 1.0),
     Input('radius_2', None, help='empty: circle; with a value: ellipse',
             visible_if=lambda e: e.get('mode', 'centre and radius') == 'centre and radius'),
     Input('plane', 'plan', single=True, help='plan, elevation or side', options=('plan', 'elevation', 'side elevation'),
             visible_if=lambda e: e.get('mode', 'centre and radius') == 'centre and radius' and e.get('normal') is None),
     Input('normal', None, help='which way the circle faces (a vector, or the normals of a surface: it lies on '
                                   'it); empty: in the plane',
             visible_if=lambda e: e.get('mode', 'centre and radius') == 'centre and radius')),
    'circle',
    lambda mode, centre, curve, at, size, side, radius, radius_2, plane, normal, name: (
        geo.circle_tangent(_connected_require(curve, "curve"), radius, at, size, side, name)
        if mode == 'tangent to a curve' else geo.circle(centre, radius, radius_2, plane, name, normal)),
    'A circle with its centre, or tangent to a curve; with a second radius, an ellipse.',
    ("Elipse", "Circunferencia", "Circle", "Ellipse", "Círculo tangente", "Tangent Circle", "Tangencia"),
))

_register(NodeType(
    'Curve through points', 'Curves',
    (Input('points'), Input('along', None, single=True, help='the level of the points to join; empty: the last',
                                levels_of='points'),
     Input('smooth', True, single=True, help='yes: smooth curve; no: polyline with corners'),
     Input('closed', False, single=True)),
    'curve',
    lambda points, along, smooth, closed, name: geo.curve_by_points(points, along, bool(smooth), bool(closed), name),
    'Joins the points of a level into a curve (removes that level).',
    ("Interpolate", "Polilínea", "Polyline", "Spline", "Unir puntos", "Contorno"),
))

_register(NodeType(
    'Transition curve', 'Curves',
    (Input('a', help='the curve it starts from'), Input('b', help='the curve it arrives at'),
     Input('bulge', 0.5, help='0.1: almost straight; 1: very wide'),
     Input('join', True, single=True, help='yes: returns a + transition + b as one curve')),
    'curve',
    lambda a, b, bulge, join, name: geo.transition(a, b, bulge, bool(join), name),
    'A smooth curve that joins the end of one curve to the start of another, without kinks.',
    ("Blend Curve", "Empalme", "Enlace", "Unir curvas", "Join Curves", "Transición"),
))

_register(NodeType(
    'Drawn curve', 'Curves',
    (Input('points', (), single=True, help='the points drawn in the 3D view'),
     Input('mode', 'through points', single=True, options=geo.MODES_CURVE,
             help='through the points: the curve passes through them; control: they stay outside and pull it like magnets'),
     Input('degree', 3, single=True, help='1: polyline with corners; 3: smooth curve; up to 5: tauter'),
     Input('closed', False, single=True)),
    'curve',
    lambda points, mode, degree, closed, name: geo.drawn_curve(points, mode, degree, bool(closed), name),
    'A curve drawn with the mouse: click in the view to place its points; then drag them.',
    ("Crv", "Curve", "Dibujar", "Trazar", "Curva a mano", "Spline", "Polilínea", "Referenciar curva"),
))

def _connected_require(v, input_: str):
    """An input that has to come from another node (a curve): if it is empty, a clear warning."""
    if v is None:
        raise ShapeError(tr('«{input}» is missing: connect a curve.').format(input=tr(input_)))
    return v


def _possible_pen(e: dict) -> bool:
    """The pen, only if the points do not come from another node (drawn by hand)."""
    return isinstance(e.get("points", ()), (list, tuple))


def _in_pen(e: dict) -> bool:
    return e.get('mode') == 'pen' and _possible_pen(e)


_register(NodeType(
    'NURBS Curve', 'Curves',
    (Input('mode', 'control points', single=True, options=geo.MODES_NURBS,
             help='control points: the curve does not pass through them, they pull it like magnets · pen: '
                   'anchors it passes through, with handles that shape it',
             visible_if=lambda e: _possible_pen(e)),
     Input('points', (), help='the control points: the curve does not pass through them, they pull it. Connect '
                                 'some points, or draw them with «Edit curve»', visible_if=lambda e: not _in_pen(e)),
     Input('stroke', (), help='the pen anchors and their handles: drawn with «Edit curve»',
             visible_if=_in_pen),
     Input('along', None, single=True, help='the level of the points of one curve; empty: the last one',
             levels_of='points', visible_if=lambda e: not isinstance(e.get('points', ()), (list, tuple))),
     Input('degree', 3, single=True, help='1: the polyline of the points; 2: arcs; 3: smooth; up to 7: tauter',
             visible_if=lambda e: not _in_pen(e)),
     Input('weights', 1.0,
             help='how much each point pulls: 1 is normal, more brings the curve closer; one for all or one per point (;)',
             visible_if=lambda e: not _in_pen(e)),
     Input('knots', 'uniform', single=True, options=geo.MODES_NODES, advanced=True,
             help='how the curve is spread between the points: evenly, by distance, halfway, or by hand', visible_if=lambda e: not _in_pen(e)),
     Input('list', "", visible_if=lambda e: e.get('knots') == 'by hand' and not _in_pen(e), advanced=True,
             help='the inner knots, from low to high between 0 and 1 (or the full knot vector, end knots included, '
                   'as other programs give it); repeating one makes a kink'),
     Input('closed', False, single=True)),
    'curve',
    lambda mode, points, stroke, along, degree, weights, knots, list, closed, name: (
        geo.curve_pen(stroke, bool(closed), name) if mode == 'pen' and _possible_pen({"points": points})
        else geo.curve_nurbs(points, along, degree, weights, knots, list, bool(closed), name)),
    'A NURBS curve: its control points pull it like magnets, with its degree, weights and knots.',
    ("Nurbs Curve", "NURBS", "B-spline", "Bspline", "Control Point Curve", "Curva por puntos de control",
     "Puntos de control", "Pesos", "Weights", "Knots", "Nudos", "Grado", "Degree", "Spline", "Pluma", "Pen",
     "Bézier", "Bezier", "Path", "Trazo", "Anclas"),
))

_register(NodeType(
    'Points on curve', 'Curves',
    (Input('curve'),
     Input('mode', 'parts', single=True, options=geo.MODES_POINTS,
             help='parts: N equal parts · every: one every so much distance · fraction: 0.5 is the middle · '
                   'distance: so far from the start (negative: from the end)'),
     Input('count', 10, single=True, visible_if=lambda e: e.get('mode', 'parts') == 'parts'),
     Input('distance', 1.0, single=True, help='one point every so much distance',
             visible_if=lambda e: e.get('mode') == 'every'),
     Input('positions', 0.5, help='one or more, separated by “;”: 0.5 · 0.25; 0.75 · 2; -2',
             visible_if=lambda e: e.get('mode') in ('fraction', 'distance')),
     Input('level', "point", single=True, help='name of the new level')),
    'points',
    lambda curve, mode, count, distance, positions, level, name: geo.curve_points(
        curve, count, level, name, mode, distance, positions),
    'Points on a curve: in equal parts, every so many metres, at its middle or at a distance.',
    ("Divide Curve", "Dividir curva", "Repartir en curva", "Point On Curve", "Punto en curva",
     "Divide Distance", "Measure", "Medir curva", "Mitad", "Punto medio", "Evaluate Length"),
))

_register(NodeType(
    'Tangent', 'Curves',
    (Input('curve'),
     Input('what', 'tangent', single=True, options=geo.WHAT_TANGENT,
             help='tangent: where the curve goes · normal: its perpendicular in the curve plane (to the left, '
                   'looking at the plane from above, from the front or from the right)'),
     Input('mode', 'fraction', single=True, options=geo.MODES_POINTS,
             help='where, as in Curve points: equal parts · every so much distance · fraction · distance'),
     Input('count', 10, single=True, visible_if=lambda e: e.get('mode') == 'parts'),
     Input('distance', 1.0, single=True, help='one every so much distance', visible_if=lambda e: e.get('mode') == 'every'),
     Input('positions', 0.5, help='one or more, separated by “;”: 0.5 · 0.25; 0.75 · 2; -2',
             visible_if=lambda e: e.get('mode', 'fraction') in ('fraction', 'distance')),
     Input('level', "point", single=True, help='name of the new level')),
    'vector',
    lambda curve, what, mode, count, distance, positions, level, name: geo.tangent(
        curve, what, mode, count, distance, positions, level, name),
    'The direction of a curve at some points (a vector of length 1): where it goes, or its perpendicular. With '
    'Curve points at the same positions, the point and its direction.',
    ("Tangent", "Evaluate Curve", "Curve Frame", "Perpendicular Frame", "Normal", "Dirección de curva",
     "Tangencia", "Perpendicular a la curva"),
))

_register(NodeType(
    'Flip curve', 'Curves',
    (Input('curve'),
     Input('direction', None, help='empty: flips them all · with a vector: only those going against it, so all '
                                      'go towards the same side (closed ones: the way they turn)')),
    'curve',
    lambda curve, direction, name: geo.reverse_curve(curve, direction, name),
    'Each curve reversed: it starts where it ended. With a direction, all of them towards the same side (before a '
    'loft, so it does not come out twisted).',
    ("Flip Curve", "Flip", "Reverse Curve", "Invertir sentido", "Dar la vuelta", "Sentido de la curva"),
))

_register(NodeType(
    'Cut curve', 'Curves',
    (Input('curve'),
     Input('mode', 'parts', single=True, options=geo.CUT_MODES,
             help='parts: N equal pieces · every: pieces of so much distance · fraction or distance: cut there '
                   '(as in Curve points) · at points: where some points fall'),
     Input('count', 4, single=True, help='how many pieces', visible_if=lambda e: e.get('mode', 'parts') == 'parts'),
     Input('distance', 1.0, single=True, help='the length of each piece (the last one, whatever is left)',
             visible_if=lambda e: e.get('mode') == 'every'),
     Input('positions', 0.5, help='where it is cut: one or several, separated by «;»',
             visible_if=lambda e: e.get('mode') in ('fraction', 'distance')),
     Input('points', None, help='where it is cut: the closest curve point to each one',
             visible_if=lambda e: e.get('mode') == 'at points'),
     Input('level', "segment", single=True, help='name of the pieces level')),
    'curves',
    lambda curve, mode, count, distance, positions, points, level, name: geo.cut_curve(
        curve, mode, count, distance, positions, points, level, name),
    'Cuts each curve into pieces (into parts, every so often, at some positions or where some points fall), to '
    'work on them one by one.',
    ("Shatter", "Split Curve", "Partir curva", "Trocear curva", "Dividir en tramos", "Segmentos", "Tramos de curva"),
))

# --- Superficies ---------------------------------------------------------------

_register(NodeType(
    'Rounded rectangle', 'Curves',
    (Input('width', 10.0), Input('height', 5.0), Input('radius', 1.0, help='the corner radius'),
     Input('origin', (0.0, 0.0, 0.0), help='the bottom left corner')),
    'outline',
    lambda width, height, radius, origin, name: geo.rounded_rectangle(width, height, radius, origin, name),
    'The outline of a rectangle with rounded corners (in plan).',
    ("Fillet", "Esquinas redondeadas", "Rectángulo con radio", "Chaflán redondo"),
))

_register(NodeType(
    'Cap', 'Surfaces',
    (Input('curve'),
     Input('holes', None, help='optional: closed curves inside (a courtyard, a skylight): a flat slab with those holes')),
    'surface',
    lambda curve, holes, name: geo.cap(curve, name, holes),
    'The surface that closes a closed curve: a roof, a free-form slab.',
    ("Patch", "Boundary Surface", "Superficie de contorno", "Cubrir", "Cap"),
))

_register(NodeType(
    'Part of curve', 'Curves',
    (Input('curve'), Input('from', 0.0, help='from 0 (the start) to 1 (the end)'),
     Input('to', 1.0, help='from 0 to 1; on a closed curve it can wrap around')),
    'segment',
    lambda curve, from_, to, name: geo.curve_part(curve, from_, to, name),
    'The part of a curve between two fractions of its length: an arc of a circle, a piece of an edge.',
    ("Sub Curve", "Subcurva", "Arco", "Tramo", "Recortar curva"),
))

_register(NodeType(
    'Loft', 'Surfaces',
    (Input('curves'), Input('along', None, single=True, help='the level of the sections; empty: the last',
                                levels_of='curves'),
     Input('smooth', True, single=True, help='yes: passes smoothly through the sections; no: straight spans'),
     Input('closed', False, single=True, help='yes: the last section goes back to the first (a ring of sections)')),
    'surface',
    lambda curves, along, smooth, closed, name: geo.surface_by_sections(curves, along, bool(smooth), name,
                                                                              bool(closed)),
    'A surface through the curves of a level, in order (removes that level).',
    ("Loft", "Piel", "Superficie", "Secciones"),
))

_register(NodeType(
    'Extrude', 'Surfaces',
    (Input('curve'),
     Input('mode', "vector", single=True, options=geo.MODES_EXTRUDE,
             help='vector: dragged (a sheet, a wall) · to a point: meets at an apex (a pyramid, a cone, a hip '
                   'roof)'),
     Input('vector', (0.0, 0.0, 1.0), help='which way and how far; by default, 1 m up',
             visible_if=lambda e: e.get('mode', "vector") == "vector"),
     Input('point', None, help='the apex where they meet', visible_if=lambda e: e.get('mode') == 'to a point'),
     Input('caps', False, single=True, help='yes: a closed curve gives a closed body, with a cap below and above')),
    'surface',
    lambda curve, mode, vector, point, caps, name: geo.extrude(curve, vector, name, bool(caps), mode, point),
    'Drags each curve along a vector: a sheet, a wall. With caps, a closed plan becomes a volume.',
    ("Extrude", "Lámina", "Muro", "Barrer", "Extruir planta", "Volumen de planta", "Sólido"),
))

# --- Dividir -----------------------------------------------------------------

_register(NodeType(
    'Grid', 'Divide',
    (Input('rectangle'),
     Input('columns', None, help='how many, or the cuts as fractions (0; 0.2; 0.5; 1: uneven), also from another '
                                 'node (a Formula: cells that grow)'),
     Input('rows', None, help='how many, or the cuts as fractions (0; 0.3; 1: uneven), also from another node'),
     Input('cell_width', None, single=True), Input('cell_height', None, single=True),
     Input('rows_level', "row", single=True), Input('columns_level', "column", single=True),
     Input('shape', 'squares', single=True, options=geo.GRID_SHAPES,
           help='squares, diamonds, hexagons (a honeycomb) or triangles; «diamond trims»: the triangles that '
                'complete the border around the diamonds'),
     Input('panels', 'flat', single=True, options=('flat', 'curved'),
             help='on a curved surface: flat (four corners) or curved (each panel follows the surface)')),
    'cells',
    lambda rectangle, columns, rows, cell_width, cell_height, rows_level, columns_level, shape, panels, name:
        geo.grid(rectangle, columns, rows, cell_width, cell_height, (rows_level, columns_level), shape, name,
                     panels),
    'Divides a rectangle (by number, cell size or uneven cuts) or a curved surface into rows and columns; on a '
    'surface, with flat or curved panels.',
    ("Dividir en retícula", "Paneles", "Grilla", "Cuadrícula", "Modulación", "Rombos", "Diamond Panels",
     "Divide Surface", "Isotrim", "Paneles curvos", "División desigual", "Subdividir superficie"),
))

_register(NodeType(
    'Divide', 'Divide',
    (Input('rectangle'), Input('parts', None, single=True), Input('size', None, single=True),
     Input('level', "part", single=True, help='name of the new level'),
     Input('direction', 'width', single=True, help='width or height', options=('width', 'height'))),
    'parts',
    lambda rectangle, parts, size, level, direction, name:
        geo.divide(rectangle, parts, size, level, direction, name),
    'Divides a rectangle into parts in one direction; the new level gets the name you choose.',
    ("Franjas", "Partir"),
))

_register(NodeType(
    'Voronoi 3D', 'Divide',
    (Input('points'), Input('region'),
     Input('level', "cell", single=True, help='name of the cells level'),
     Input('faces_level', "face", single=True, help="name of the level of each cell's faces")),
    'cells',
    lambda points, region, level, faces_level, name: pol.voronoi_3d(points, region, level, faces_level, name),
    'Divides a volume into cells: each point gets the space closer to it than to the others. Each cell is a '
    'polyhedron; its faces, polygons.',
    ("Celdas en volumen", "Espuma", "Cristales", "Voronoi 3D"),
))

_register(NodeType(
    'Voronoi', 'Divide',
    (Input('points', help='the seeds: each one gets the part of the plane closer to it than to the others'),
     Input('boundary', None, help='a closed curve or polygon that holds the cells (a rectangle, a circle, a drawn '
                                  'outline); empty: a rectangle a little larger than the seeds'),
     Input('radius', None, help='no cell goes farther than this from its seed (they round off and leave gaps); '
                                'empty: no limit'),
     Input('level', "cell", single=True, help='name of the cells level')),
    'cells',
    lambda points, boundary, radius, level, name: pol.voronoi(points, boundary, radius, level, name),
    'Divides a plane into cells: each seed gets the part closer to it than to the others. Each cell is a polygon, '
    'on the plane of the boundary. With Vertices, Centre and Delaunay, a pyramid on each cell (a Voronoi skin).',
    ("Celdas", "Teselación", "Diagrama de Voronoi", "Voronoi 2D", "Mosaico", "Piel Voronoi", "Cells"),
))

_register(NodeType(
    'Centre', 'Divide',
    (Input('geometry'),),
    'centres',
    lambda geometry, name: geo.centre(geometry, name),
    'The centre of each element.',
))

_register(NodeType(
    'Faces', 'Divide',
    (Input('volume'),
     Input('which', 'façades', single=True, help='south, east, north, west, roof, base; or “façades”, “all”',
             options=('façades', 'all faces', 'roof', "base", 'south', 'east', 'north', 'west', 'south, east')),
     Input('level', "face", single=True, help='name of the new level')),
    'faces',
    lambda volume, which, level, name: geo.faces(volume, which, level, name),
    'The faces of a prism or a box, by name (south, roof…), as rectangles.',
    ("Fachadas", "Descomponer", "Deconstruct Brep"),
))

_register(NodeType(
    'Pick', 'Divide',
    (Input('data'), Input('level', None, single=True, levels_of='data', help='the level to pick from; empty: the only one'),
     Input('position', help='from 0: 4 · last · -1 (the last) · several: 1; 5; 3 · from 2 to 5: 2-5')),
    'picked',
    lambda data, level, position, name: pick(data, level, position, name),
    'Takes elements of a level by their number (from 0): row 4, the top floor, points 1, 5 and 3, from 2 to 5.',
    ("Tomar", "List Item", "Seleccionar", "Sub List", "Índice", "Index", "Escoger"),
))

_register(NodeType(
    'Repeat', 'Values',
    (Input('data'), Input('level', None, single=True, levels_of='data', help='the level to repeat; empty: the only one'),
     Input('length', 5, single=True, help='how many elements it must have in the end')),
    'repeated',
    lambda data, level, length, name: repeat(data, level, length, name),
    'Repeats a list, in order, up to a length: 2; 6; 1 up to 5 gives 2; 6; 1; 2; 6. So a short list can go with a '
    'long one.',
    ("Repeat Data", "Repetir lista", "Ciclo", "Patrón de alturas", "Longest List", "Alargar"),
))

_register(NodeType(
    'Split', 'Divide',
    (Input('data'), Input('level', None, single=True, levels_of='data', help='the level to split; empty: the only one'),
     Input('mode', 'groups of', single=True, options=SPLIT_MODES,
             help='groups of: so many at a time · in parts: into so many equal groups'),
     Input('count', 2, single=True, help='how many per group (groups of) or how many groups (in parts)'),
     Input('new_level', "group", single=True, help='name of the groups level: span, module, floor…')),
    'groups',
    lambda data, level, mode, count, new_level, name: split(data, level, mode, count, new_level, name),
    'Splits the elements of a level into groups: in fours, or into 3 parts. To split in two at a point, Pick with '
    'a range (0-3 and 4-last).',
    ("Partition", "Split List", "Agrupar", "Grupos", "Tramos", "Dividir lista", "Módulos", "Trocear"),
))

_register(NodeType(
    'Join levels', 'Divide',
    (Input('data'),
     Input('first', None, single=True, levels_of='data', help='the outer level; empty: the first one'),
     Input('second', None, single=True, levels_of='data',
           help='the level that goes inside, in order for each of the first; empty: the last one'),
     Input('new_level', None, single=True, help='name of the joined level; empty: that of the second')),
    'joined',
    lambda data, first, second, new_level, name: join_levels(data, first, second, new_level, name),
    'Joins two levels into one, in order: triangle 4 × vertex 3 becomes vertex 12 (the three of the first triangle, '
    'then those of the next…). To draw one curve through all the points, or to number them in a row. Split in '
    'groups undoes it.',
    ("Flatten", "Flatten Tree", "List.Flatten", "Aplanar", "Aplanar lista", "Unir niveles", "Juntar niveles",
     "Una sola lista", "Simplificar"),
))

_register(NodeType(
    'Reorder', 'Divide',
    (Input('data'), Input('level', None, single=True, levels_of='data',
                              help='the level to reorder; empty on a curve: reverse its direction'),
     Input('mode', 'invert', single=True, options=MODES_REORDER,
             help='reverse: back to front · shift: move N places · sort: from smallest to largest by a key'),
     Input('count', 1, single=True, help='how many places (negative, the other way)',
             visible_if=lambda e: e.get('mode') == 'shift'),
     Input('wrap', True, single=True,
             help='yes: those that leave at the start come back at the end; no: they are dropped',
             visible_if=lambda e: e.get('mode') == 'shift'),
     Input('key', None, help='one number per element to sort by (a distance, a height); empty: its own values',
             visible_if=lambda e: e.get('mode') == 'sort')),
    'reordered',
    lambda data, level, mode, count, wrap, key, name: reorder(
        data, level, mode, count, bool(wrap), key, name),
    'Changes the order of a level: reversed, shifted a few places, or from smallest to largest by a value. On a '
    'single curve, reverses its direction.',
    ("Reverse", "Invertir", "Shift", "Desplazar lista", "Correr", "Sort", "Ordenar", "Flip", "Invertir curva",
     "Girar lista", "Rotar lista"),
))

# --- Measure and compute --------------------------------------------------------

_register(NodeType(
    'Distance', 'Measure',
    (Input('a'), Input('b')),
    'distance',
    lambda a, b, name: geo.distance(a, b, name),
    'Distance between points, in metres.',
))

_register(NodeType(
    'Function', 'Values',
    (Input('shape', 'wave', single=True, options=tuple(fun.FUNCTIONS),
             help='the function: of one variable (wave, ramp, parabola, catenary, bell, step, sawtooth) or of '
                   'two (swell, ripples, hill, saddle, dome, pyramid)'),
     Input('x', None, help='where it is calculated: a Series, some distances, the x of some points…'),
     Input('y', None, help='the second variable (only for two-variable ones): another Series, with another level name',
             visible_if=lambda e: fun.FUNCTIONS.get(e.get('shape', 'wave'), (1,))[0] == 2),
     Input('amplitude', 1.0, help='how high it rises (the amplitude)'),
     Input('width', 4.0, help='how often it repeats, or how big the shape is (the span, the radius)')),
    'value',
    lambda shape, x, y, amplitude, width, name: fun.function(shape, x, y, amplitude, width, name),
    'Ready-to-use functions: a wave, an arch, a catenary, a hill, a saddle (Candela)…, with their height and '
    'width. The panel says what each one is for.',
    ("Function", "Seno", "Sine", "Onda", "Catenaria", "Parábola", "Paraboloide", "Ola", "Cúpula", "Colina",
     "Math", "Matemática", "Curva matemática"),
))

_register(NodeType(
    'Surface from points', 'Surfaces',
    (Input('points', help='in a grid (two levels: rows × columns) or loose (a cloud)'),
     Input('mode', 'grid', single=True, options=meshes.MODES_SURFACE_POINTS,
             help='grid: points ordered in rows × columns · cloud: loose (a survey), in triangles'),
     Input('smooth', False, single=True, help='yes: curved between the points; no: flat facets (in a cloud, triangles)')),
    'surface',
    lambda points, mode, smooth, name: meshes.surface_by_points(points, mode, bool(smooth), name),
    'A surface through some points: in a grid (rows × columns), or a loose cloud, like the points of a land '
    'survey.',
    ("SrfGrid", "Surface from Points", "Delaunay", "Terreno", "Topografía", "Malla de puntos", "Mapa de puntos",
     "Superficie de puntos", "Levantamiento"),
))

_register(NodeType(
    'NURBS Surface', 'Surfaces',
    (Input('points', help='the control points, in rows × columns (two levels): the surface does not pass '
                             'through them, they pull it'),
     Input('level_u', None, single=True, levels_of='points', help='the rows level (u); empty: the second to last'),
     Input('level_v', None, single=True, levels_of='points', help='the columns level (v); empty: the last one'),
     Input('degree_u', 3, single=True, help='in u: 1, facets; 2, curves; 3, smooth (up to 7)'),
     Input('degree_v', 3, single=True, help='in v: 1, facets; 2, curves; 3, smooth (up to 7)'),
     Input('weights', 1.0, help='how much each point pulls: one for all or one per point, row by row (;)'),
     Input('closed_u', False, single=True, help='goes all the way round in u (a tube)'),
     Input('closed_v', False, single=True, help='goes all the way round in v (a tube; in both, a torus)')),
    'surface',
    lambda points, level_u, level_v, degree_u, degree_v, weights, closed_u, closed_v, name: sup.surface_nurbs(
        points, level_u, level_v, degree_u, degree_v, weights, bool(closed_u), bool(closed_v), name),
    'A NURBS surface: a grid of control points (rows × columns) that pull it, with its degree in each direction, '
    'its weights and closed if wanted. For roofs, shells and free skins.',
    ("Surface from control points", "NURBS Surface", "Superficie libre", "Cáscara", "Piel", "Membrana",
     "Control points surface", "Superficie de puntos de control"),
))

_register(NodeType(
    'Revolve', 'Surfaces',
    (Input('profile', help='the curve that turns (half section: the edge of a column, of a dome)'),
     Input('origin', (0.0, 0.0, 0.0), help='a point on the axis'),
     Input('axis', (0.0, 0.0, 1.0), help='the axis direction (0, 0, 1: vertical)'),
     Input('degrees', 360.0, help='how much it turns: 360, a full turn; less, a part')),
    'surface',
    lambda profile, origin, axis, degrees, name: sup.revolve(profile, origin, axis, degrees, name),
    'The surface a profile leaves when turning around an axis: a column, a dome, a vase, a tower.',
    ("Revolve", "Revolución", "Girar perfil", "Torno", "Superficie de revolución", "Rail Revolve", "Cúpula",
     "Columna", "Balaustre"),
))

_register(NodeType(
    'Sweep', 'Surfaces',
    (Input('profile', help='the section that runs along the path (a circle, the profile of a moulding)'),
     Input('path', help='the curve it runs along (a single one)'),
     Input('path_2', None, help='optional: a second path; the profile goes from one to the other and '
                                     'stretches across to touch both'),
     Input('place', 'where it is', single=True, options=sup.PLACE_PROFILE,
             help='where it is: the profile, drawn at the start of the path · centred on the path: drawn '
                   'anywhere (in plan, for example); its centre goes to the path'),
     Input('rotation', 0.0, help='degrees the profile turns along the whole path (0: no twist)',
             visible_if=lambda e: e.get('path_2') is None)),
    'surface',
    lambda profile, path, path_2, place, rotation, name: sup.sweep(profile, path, place, rotation, name,
                                                                       path_2),
    'The surface a profile leaves when running along a path without twisting: a handrail, a moulding, a curved '
    'beam, a tube.',
    ("Sweep", "Sweep1", "Sweep2", "Dos caminos", "Barrer", "Extruir por un camino", "Extrude along curve", "Moldura", "Pasamanos",
     "Barandilla", "Perfil por camino"),
))

_register(NodeType(
    'Surface points', 'Surfaces',
    (Input('surface'),
     Input('what', 'points', single=True, options=sup.WHAT_POINTS_SURFACE,
             help='points on the surface, or its normal there (where it faces, length 1)'),
     Input('mode', 'lattice', single=True, options=sup.MODES_POINTS_SURFACE,
             help='grid: count u × count v evenly spread, from edge to edge · centres: the centre of each panel '
                   'of a division into count u × count v · fractions: at some u and v from 0 to 1'),
     Input('count_u', 5, single=True, visible_if=lambda e: e.get('mode', 'lattice') in ('lattice', 'centres')),
     Input('count_v', 5, single=True, visible_if=lambda e: e.get('mode', 'lattice') in ('lattice', 'centres')),
     Input('u', 0.5, help='along the rows, from 0 to 1; several with «;»', visible_if=lambda e: e.get('mode') == 'fractions'),
     Input('v', 0.5, help='along the columns, from 0 to 1; several with «;»',
             visible_if=lambda e: e.get('mode') == 'fractions'),
     Input('level_u', "u", single=True, advanced=True,
             help='the name of the level along u: the same name as another list pairs them one by one'),
     Input('level_v', "v", single=True, advanced=True, help='the name of the level along v')),
    'points',
    lambda surface, what, mode, count_u, count_v, u, v, level_u, level_v, name: sup.surface_points(
        surface, what, mode, count_u, count_v, u, v, name, level_u, level_v),
    'Points on a surface (in a grid or at some fractions of u and v), or its normal there: to leave the surface '
    'with something (a column, an anchor, a piece).',
    ("Evaluate Surface", "Divide Surface", "Surface Points", "Punto en superficie", "Normal de superficie",
     "Surface Normal", "Puntos sobre la superficie", "Anclajes"),
))

_register(NodeType(
    'Surface morph', 'Surfaces',
    (Input('geometry', None, help='the module: a piece drawn anywhere; its bounding box becomes each cell. '
                                  'Empty: the cells themselves'),
     Input('surface', help='the surface that is panelled (a loft, a revolve, a NURBS…)'),
     Input('count_u', 6, single=True, help='cells along u'),
     Input('count_v', 6, single=True, help='cells along v'),
     Input('height', 1.0, help='how far the top of the module rises along the normal (negative: inwards)'),
     Input('reference', None, advanced=True,
           help='a box that stands for the module (its bounding box); empty: that of the module itself')),
    'geometry',
    lambda geometry, surface, count_u, count_v, height, reference, name: sup.surface_morph(
        geometry, surface, count_u, count_v, height, reference, name),
    'Covers a surface with a module (paneling): the surface is divided into cells that follow its curve and its '
    'normal, and the module is fitted into each one, bending with it. Neighbouring cells share their corners, so '
    'nothing is left open.',
    ("Surface Morph", "Paneling", "Panelling", "Panelizar", "Panelizado", "Surface Box", "Morph en superficie",
     "Cubrir superficie", "Módulo en superficie", "Celdas de superficie"),
))

_register(NodeType(
    'Mesh', 'Meshes',
    (Input('points', help='the vertices, in order: they are numbered from 0'),
     Input('faces', single=True,
           help='the vertices of each face, in order (counterclockwise seen from the front), «;» between faces: '
                '«0 1 2; 2 1 3» (two triangles), «0 1 2 3» (a quadrilateral)'),
     Input('along', None, single=True, levels_of='points', advanced=True,
           help='the level of the vertices; empty: the last one (with other levels, one mesh for each)')),
    'mesh',
    lambda points, faces, along, name: mesh_tools.mesh(points, faces, along, name),
    'A mesh from its vertices and its faces: the points say where (its geometry), the faces how they are joined '
    '(its topology). The order of each face says which side is the front.',
    ("Construct Mesh", "Mesh", "Malla", "Construir malla", "Mesh Triangle", "Mesh Quad", "Triángulo", "Cuadrilátero",
     "Topología", "Polígonos"),
))

_register(NodeType(
    'Flip faces', 'Meshes',
    (Input('mesh', help='a mesh (or a box, a surface: anything with faces)'),
     Input('which', None, single=True, help='the faces to turn over («1» · «0 3»); empty: all of them')),
    'mesh',
    lambda mesh, which, name: mesh_tools.flip_faces(mesh, which, name),
    'Turns faces over: the front becomes the back (its vertices, in the opposite order). To make the faces of a mesh '
    'compatible, all looking the same way.',
    ("Mesh Flip", "Flip", "Invertir caras", "Dar vuelta", "Dar vuelta caras", "Voltear caras", "Orientar caras"),
))

_register(NodeType(
    'Mesh faces', 'Meshes',
    (Input('mesh', help='a mesh (or a box, a surface: anything with faces)'),
     Input('what', 'normals', single=True, options=mesh_tools.FACE_READINGS,
           help='outlines: each face as a closed polygon · centres · normals: where it looks · sides: 3, 4… · '
                'orientation: +1 if it looks like its neighbours, −1 if it is turned over · flatness: how far the '
                'face is from flat, in metres'),
     Input('level', "face", single=True, advanced=True, help='name of the new level')),
    'faces',
    lambda mesh, what, level, name: mesh_tools.mesh_faces(mesh, what, level, name),
    'Reads each face of a mesh: its outline, its centre, its normal, how many sides it has, or whether it looks '
    'the same way as its neighbours (a mesh with a face turned over is not orientable).',
    ("Face Normals", "Face Boundaries", "Deconstruct Mesh", "Caras de malla", "Normales de malla", "Mesh Faces",
     "Orientación", "Orientable", "Bordes de caras"),
))

_register(NodeType(
    'Mesh surface', 'Meshes',
    (Input('surface', help='a surface (or a rectangle)'),
     Input('count_u', 10, single=True, help='faces across'),
     Input('count_v', 10, single=True, help='faces up')),
    'mesh',
    lambda surface, count_u, count_v, name: mesh_tools.mesh_surface(surface, count_u, count_v, name),
    'A surface as one mesh of quadrilaterals that share their vertices (on a surface that goes round, the seam is '
    'closed too). A surface of revolution or of translation gives flat quadrilaterals: panels that can be built '
    'with flat glass.',
    ("Mesh Surface", "Mesh UV", "Malla de superficie", "Convertir a malla", "Mallar", "NURBS a malla", "Quad mesh"),
))

_register(NodeType(
    'Triangulate', 'Meshes',
    (Input('mesh', help='a mesh (or a box, a surface: anything with faces)'),
     Input('diagonal', 'shorter', single=True, options=mesh_tools.DIAGONALS,
           help='how each quadrilateral is split: by its shorter diagonal, or always the first (0-2) or the second '
                '(1-3)')),
    'mesh',
    lambda mesh, diagonal, name: mesh_tools.triangulate(mesh, diagonal, name),
    'Every face as triangles: each quadrilateral split by a diagonal. Triangles are always flat.',
    ("Triangulate", "Triangular", "Mesh Triangulate", "Triángulos", "Partir en triángulos"),
))

_register(NodeType(
    'Surface curvature', 'Surfaces',
    (Input('surface'),
     Input('what', 'Gaussian', single=True, options=sup.WHAT_CURVATURE,
             help='Gaussian: zero, made from flat sheet; positive, dome-like; negative, saddle-like · mean: how '
                   'much it bends on average (its sign depends on which way the face looks) · developable: yes or '
                   'no'),
     Input('mode', 'lattice', single=True, options=sup.MODES_POINTS_SURFACE,
             help='at the same points as Surface points with the same mode',
             visible_if=lambda e: e.get('what', 'Gaussian') != 'developable'),
     Input('count_u', 5, single=True,
             visible_if=lambda e: e.get('mode', 'lattice') in ('lattice', 'centres') and e.get('what') != 'developable'),
     Input('count_v', 5, single=True,
             visible_if=lambda e: e.get('mode', 'lattice') in ('lattice', 'centres') and e.get('what') != 'developable'),
     Input('u', 0.5, help='along the rows, from 0 to 1; several with «;»',
             visible_if=lambda e: e.get('mode') == 'fractions' and e.get('what') != 'developable'),
     Input('v', 0.5, help='along the columns, from 0 to 1; several with «;»',
             visible_if=lambda e: e.get('mode') == 'fractions' and e.get('what') != 'developable')),
    'curvature',
    lambda surface, what, mode, count_u, count_v, u, v, name: sup.surface_curvature(
        surface, what, mode, count_u, count_v, u, v, name),
    'The curvature of a surface at some points, as numbers to use: the Gaussian (can it be made from flat '
    'sheet?), the mean (how much does it bend?), or whether the surface is developable (yes or no).',
    ("Surface Curvature", "Curvature", "Gaussian curvature", "Mean curvature", "Curvatura gaussiana",
     "Curvatura media", "Desarrollable", "Developable", "Chapa plana", "Doble curvatura"),
))

_register(NodeType(
    'Unroll', 'Surfaces',
    (Input('geometry', help='a surface, a mesh or a body with flat faces (or a list: the gores of a dome, '
                                'some offcuts, some boxes)'),
     Input('what', 'unrolled', single=True, options=des.WHAT_UNROLL,
             help='unrolled: the flattened pieces (a body with flat faces: its net) · outlines: their edges, to '
                   'cut or export to DXF · folds: in a net, the edges where it folds (to score them) · stretch: '
                   'how much their sides change length when flattened, on average (%)'),
     Input('place', 'in a row', single=True, options=des.PLACE,
             help='in a row: one beside the other, each standing up (lengthwise along y) · in place: flattened '
                   'where it lies',
             visible_if=lambda e: e.get('what', 'unrolled') != 'stretch'),
     Input('spacing', 1.0, single=True, help='between one piece and the next',
             visible_if=lambda e: e.get('what', 'unrolled') != 'stretch'
             and e.get('place', 'in a row') == 'in a row')),
    'plane',
    lambda geometry, what, place, spacing, name: des.unroll(geometry, what, place, spacing, name),
    'Flattens surfaces onto the plane to cut them from a sheet (metal, board, fabric): a developable one without '
    'stretching; one that is not (a dome), approximately, saying how much it stretches. A body with flat faces (a '
    'box, a prism, a pyramid), its net: to cut out and fold. The pieces, in a row.',
    ("Unroll", "Unroll surface", "Flatten", "Desplegar", "Aplanar", "Patrón de corte", "Despiece", "Chapa",
     "Desarrollo", "Gajos", "Plantilla", "Cortar en plancha", "Red", "Unfold", "Net", "Red de un cuerpo",
     "Plegar", "Maqueta"),
))

_register(NodeType(
    'Flip surface', 'Surfaces',
    (Input('surface'),
     Input('what', 'face', single=True, options=sup.WHAT_REVERSE,
             help='face: looks the other way (Thicken grows the other way) · u or v: that direction reversed · '
                   'swap u and v: rows become columns')),
    'surface',
    lambda surface, what, name: sup.reverse_surface(surface, what, name),
    'The surface flipped: towards the other side (its normal), or its u and v directions.',
    ("Flip Surface", "Flip", "Swap UV", "Reverse Surface", "Dar vuelta la superficie", "Normal al revés"),
))

_register(NodeType(
    'Closest point on surface', 'Surfaces',
    (Input('points', None, help='the points to bring to the surface'),
     Input('surface', None, help='the surface to search on'),
     Input('gives', 'point', single=True, options=sup.GIVES_SURFACE,
             help='the point on the surface · its u and v (from 0 to 1, as a point u, v, 0: for Curve on surface) · '
                  'the distance · the normal there (where the surface faces)')),
    'point',
    lambda points, surface, gives, name: sup.closest_on_surface(points, surface, gives, name),
    'The point of a surface closest to each point: to bring something onto the surface, or to know where it falls '
    'on it (its u and v), how far it is, and where the surface faces there.',
    ("Surface Closest Point", "Surface CP", "Punto más cercano en superficie", "Proyectar en superficie",
     "Pull point"),
))

_register(NodeType(
    'Curve on surface', 'Surfaces',
    (Input('surface'),
     Input('points', None, help='points given by their u and v (from 0 to 1): from Closest point on surface (u v), '
                                'or a Point with x = u and y = v'),
     Input('along', None, single=True, help='the level of the points to join; empty: the last', levels_of='points'),
     Input('smooth', True, single=True, help='yes: smooth through the points; no: straight on the map of the surface'),
     Input('closed', False, single=True)),
    'curve',
    lambda surface, points, along, smooth, closed, name: sup.curve_on_surface(surface, points, along, bool(smooth),
                                                                              bool(closed), name),
    'A curve that lies on a surface, through some points given by their u and v: drawn on the flat map of the '
    'surface and laid on it, so it follows every bump. A path on a roof, a seam on a membrane, a cut on a shell.',
    ("Curve On Surface", "CrvSrf", "Interpolate on surface", "Curva en superficie", "Camino en superficie"),
))

_register(NodeType(
    'Geodesic', 'Surfaces',
    (Input('surface'),
     Input('from', None, help='the points where each geodesic starts (on the surface, or near it)'),
     Input('to', None, help='the points where each one ends: one for each start'),
     Input('show', 'curves', single=True, options=geod.SHOW,
           help='curves: the geodesics · lengths: of each one, in m · crossings: the points where they cross each '
                'other (the knots of a gridshell) · bars: each geodesic cut at its crossings, as straight bars, for '
                'Bar analysis'),
     Input('detail', 32, single=True, advanced=True,
           help='points of the coarse net along the surface, to choose which way round a hill each one goes (more: '
                'surer on a very wavy surface, and slower)')),
    'curve',
    lambda surface, from_, to, show, detail, name: geod.geodesic(surface, from_, to, show, detail, name),
    'The shortest path between two points over a surface, like a string pulled tight on it: it bends only with the '
    'surface, never sideways. Laths laid along geodesics stay straight in their own plane, which is why gridshells '
    'use them. Gives the curves, their lengths, where they cross, and the bars between the crossings.',
    ("Geodesic", "Geodésica", "Shortest path", "Camino más corto", "Gridshell", "Malla de listones", "Lath",
     "Listón", "Shortest walk", "Geodesic curve"),
))

_register(NodeType(
    'Sub surface', 'Surfaces',
    (Input('surface'),
     Input('u_from', 0.0, help='from 0 to 1, along the rows'), Input('u_to', 1.0),
     Input('v_from', 0.0, help='from 0 to 1, along the columns'), Input('v_to', 1.0)),
    'surface',
    lambda surface, u_from, u_to, v_from, v_to, name: sup.surface_part(
        surface, u_from, u_to, v_from, v_to, name),
    'The piece of a surface between two fractions of u and two of v: a bay of a roof, a segment of a dome.',
    ("Isotrim", "Sub Surface", "Subsuperficie", "Recortar superficie", "Trozo de superficie", "Gajo", "Paño"),
))

_register(NodeType(
    'Intersection', 'Surfaces',
    (Input('a', help='a surface or a body (or a curve)'),
     Input('b', help='another surface or body: with two, the crossing curves; with a curve, the points')),
    'crossing',
    lambda a, b, name: sup.intersection(a, b, name),
    'Where two geometries cross: two surfaces (or bodies) give the crossing curves; a curve and a surface, the '
    'points where it goes through.',
    ("Intersection", "Brep Brep", "Curve Brep", "Surface Surface", "Cruce", "Intersecar", "Corte de superficies",
     "Puntos de cruce"),
))

_register(NodeType(
    'Split surface', 'Surfaces',
    (Input('surface'),
     Input('curves', help='the curves that cut it (projected onto it along the direction)'),
     Input('direction', (0.0, 0.0, 1.0), help='where the curves are projected from; by default, from above'),
     Input('what', 'all pieces', single=True, options=sup.SPLIT_WHAT,
             help='all pieces (from largest to smallest) · the largest: with perforations, the perforated sheet '
                   '· the others: the offcuts')),
    'pieces',
    lambda surface, curves, direction, what, name: sup.split_surface(surface, curves, direction, name,
                                                                             what),
    'A surface split into pieces by curves that cross it or pierce it (projected onto it): all, the largest or '
    'the others; each piece is taken with Pick.',
    ("Split Surface", "Split", "Partir con curvas", "Cortar superficie", "Trozos de superficie", "Recortar"),
))

_register(NodeType(
    'Isocurves', 'Surfaces',
    (Input('surface'),
     Input('direction', "u", single=True, options=sup.DIRECTIONS,
             help='u: along the surface rows · v: along the columns'),
     Input('mode', 'parts', single=True, options=('parts', 'fraction'),
             help='parts: N spread evenly · fraction: at some positions from 0 to 1'),
     Input('count', 10, single=True, visible_if=lambda e: e.get('mode', 'parts') == 'parts'),
     Input('positions', 0.5, help='one or several, separated by «;»: 0.5 · 0.25; 0.75',
             visible_if=lambda e: e.get('mode') == 'fraction'),
     Input('level', "isocurve", single=True, help='name of the curves level')),
    'curves',
    lambda surface, direction, mode, count, positions, level, name: sup.isocurves(
        surface, direction, mode, count, positions, level, name),
    'The surface’s own lines, in u or v: ribs, mullions or a layout that follows the shape.',
    ("Isocurve", "Isocurvas paramétricas", "Isoparamétricas", "Extract isocurve", "Curvas de la superficie",
     "Nervaduras", "Montantes", "Líneas u", "Líneas v"),
))

_register(NodeType(
    'Network surface', 'Surfaces',
    (Input('curves_u', help='a family of curves (at least 2), in any order and direction'),
     Input('curves_v', help='the other family: each one must cross all those of the first')),
    'surface',
    lambda curves_u, curves_v, name: sup.surface_by_net(curves_u, curves_v, name),
    'The surface through a network of curves in two crossing directions: the ribs of a hull or of a free-form '
    'roof.',
    ("Network Surface", "NetworkSrf", "Red de curvas", "Gordon", "Superficie de red", "Costillas cruzadas", "Casco"),
))

_register(NodeType(
    'Edge surface', 'Surfaces',
    (Input('a', help='an edge (a curve going from one corner to another)'),
     Input('b', help='another edge; with only two, a ruled surface between them'),
     Input('c', None, help='a third edge (optional): with three, one side closes into a point'),
     Input('d', None, help='a fourth edge (optional)')),
    'surface',
    lambda a, b, c, d, name: sup.surface_by_edges(a, b, c, d, name),
    'The surface stretched between two, three or four edges that meet at the corners (in any order and '
    'direction): a slab or a roof with curved edges.',
    ("Edge Surface", "EdgeSrf", "Coons", "Superficie de bordes", "Network Surface", "Ruled Surface", "Reglada",
     "Superficie reglada", "Rellenar bordes"),
))

_register(NodeType(
    'Graph', 'Measure',
    (Input('value', help='the numbers that go through the graph (distances, heights…)'),
     Input('points', geo.CHARTS["linear"], single=True, help='the points of the graph: moved in the panel'),
     Input('to_min', 0.0, help='what comes out at the bottom of the graph'),
     Input('to_max', 1.0, help='what comes out at the top of the graph'),
     Input('smooth', True, single=True, help='yes: smooth curve; no: straight segments'),
     Input('from_min', None, help='empty: the smallest of the data'),
     Input('from_max', None, help='empty: the largest of the data')),
    'value',
    lambda value, points, to_min, to_max, smooth, from_min, from_max, name: geo.chart(
        value, points, to_min, to_max, from_min, from_max, bool(smooth), name),
    'Passes each value through a curve you draw by hand: you decide how it changes from near to far (or bottom to '
    'top) by moving its points, without writing formulas.',
    ("Graph Mapper", "Gráfico", "Curva de respuesta", "Mapear", "Perfil", "Relieve", "Curva a mano"),
))

_register(NodeType(
    'Image sampler', 'Measure',
    (Input('file', single=True, file="image",
           help='the image to read (PNG, JPG…): a photo, a drawing, a gradient. Kept relative to the project'),
     Input('where', help='the points that read the image, or a geometry (each element by its centre: a panel)'),
     Input('frame', None, help='where the image is laid, stretched to fit (a rectangle, a façade); '
                               'empty: around the points themselves'),
     Input('plane', None, single=True, options=('plan', 'elevation', 'side elevation'),
           help='how the image is laid; empty: on the flattest side of the frame'),
     Input('channel', 'brightness', single=True, options=images.CHANNELS,
           help='what is read: how light it is, or how much red, green, blue or opacity'),
     Input('black', 0.0, help='the value where the image is dark (or the channel is empty)'),
     Input('white', 1.0, help='the value where the image is light (or the channel is full)')),
    'value',
    lambda file, where, frame, plane, channel, black, white, name: images.sample(
        file, where, frame, plane, channel, black, white, name),
    'A value at each point, read from an image laid over a rectangle: how light the picture is there. To perforate '
    'a façade from a photo, or to raise columns from a drawing. Black gives “black”, white gives “white”; swap '
    'them to invert.',
    ("Image Sampler", "Muestreador de imagen", "Imagen", "Image", "Picture", "Photo", "Foto", "Bitmap",
     "Mapa de imagen", "Leer imagen"),
))

_register(NodeType(
    'Attractor', 'Measure',
    (Input('where', None, help='the points that feel the attractor, or a geometry (each element by its centre)'),
     Input('attractors', None, help='one or more points, or one or more curves'),
     Input('more', None, help='other attractors, to mix points and curves'),
     Input('reach', None, help='how far the effect goes (m); empty: to the farthest one'),
     Input('near', 1.0, help='the value next to the attractor'),
     Input('far', 0.0, help='the value at the reach, or beyond'),
     Input('several', 'the closest', single=True, options=geo.SEVERAL_ATTRACTORS,
             help='with several attractors: the closest one rules, or their effects add up'),
     Input('curve', 'linear', single=True, help='how it goes from near to far: linear, smooth (S), accelerates or slows down', options=tuple(geo.CURVES_ANSWER))),
    'value',
    lambda where, attractors, more, reach, near, far, several, curve, name: geo.attractor(
        where, attractors, more, reach, near, far, several, curve, name),
    'A value per element according to how close it is to some points or curves: “near” next to the attractor, '
    '“far” at the reach. To scale, move or rotate by closeness.',
    ("Attractor", "Atracción", "Influencia", "Radio de influencia", "Campo", "Cercanía"),
))

_register(NodeType(
    'Closest point', 'Measure',
    (Input('points', None, help='the points, or a geometry (each element by its centre)'),
     Input('curve', None, help='the curve to search on'),
     Input('gives', 'point', single=True, options=geo.GIVES_MORE_NEAREST,
             help='the point on the curve · the fraction of its length (0 at the start, 1 at the end) · the distance')),
    'point',
    lambda points, curve, gives, name: geo.point_more_nearest(points, curve, gives, name),
    'The point on the curve closest to each point: to join them with lines, orient something towards the curve, '
    'or know where it falls.',
    ("Curve Closest Point", "Curve CP", "Pull Point", "Proyectar en curva", "Más cercano", "Cercano"),
))

_register(NodeType(
    'Remap', 'Measure',
    (Input('value'),
     Input('from_min', None, help='empty: the smallest of the data'),
     Input('from_max', None, help='empty: the largest of the data'),
     Input('to_min'), Input('to_max'),
     Input('curve', 'linear', single=True, help='linear, smooth (S-shaped), ease in or ease out',
             options=('linear', 'smooth', 'ease in', 'ease out')),
     Input('limit', False, single=True,
             help='yes: whatever goes past the source range stays at the end (does not leave “to”)')),
    'value',
    lambda value, from_min, from_max, to_min, to_max, curve, limit, name:
        geo.remap(value, (from_min, from_max), (to_min, to_max), curve, name, bool(limit)),
    "Maps a value from one range to another (near = 90°, far = 0°). Without a source range, it uses the data's.",
    ("Rango", "Escalar rango", "Interpolar", "Graph Mapper", "Curva de respuesta", "Radio de influencia"),
))

_register(NodeType(
    'Summarise', 'Measure',
    (Input('data'),
     Input('operation', 'sum', single=True, help='maximum, minimum, sum, average or count',
             options=('maximum', 'minimum', 'sum', 'average', 'tally')),
     Input('along', None, single=True, help='the level that is removed; empty = all', levels_of='data')),
    'summary',
    lambda data, operation, along, name: reduce(data, operation, along, name),
    'The maximum, minimum, sum, average or count of the values; removes the given level, or all.',
    ("Máximo", "Mínimo", "Suma", "Promedio", "Contar", "Total", "Media", "Bounds", "Superficie por piso"),
))

# The nodes that used to be separate (D10): they still open and are found by their
# name, and they create a Summarise with their operation.
OLD = {
    "Máximo": ('Summarise', {"operation": "maximum"}),
    "Mínimo": ('Summarise', {"operation": "minimum"}),
    "Suma": ('Summarise', {"operation": "sum"}),
    "Promedio": ('Summarise', {"operation": "average"}),
    "Contar": ('Summarise', {"operation": "tally"}),
}

_register(NodeType(
    'Compare', 'Measure',
    (Input('a'), Input('b'),
     Input('operation', 'less', single=True, help=", ".join(COMPARISONS), options=tuple(COMPARISONS))),
    'yes/no',
    lambda a, b, operation, name: compare(a, b, operation, name),
    'Yes or no for each element: a is less than (greater, equal…) b.',
    ("Menor que", "Mayor que", "Condición"),
))

#: What Filter keeps: those that hold, or those that do not (the *Dispatch*: two Filters, one of each).
KEEP = ('those that do', "those that don't")


def _those_not(keep) -> bool:
    if isinstance(keep, bool):               # «invertir: sí» of before
        return keep
    if keep not in KEEP:
        raise ShapeError(tr("“keep” must be “those that do” or “those that don't”."))
    return keep == "those that don't"


_register(NodeType(
    'Yes or no', 'Values',
    (Input('value', True, single=True, help='yes or no: turn a part on or off, choose a variant'),),
    'yes/no',
    lambda value, name: Data.value(np.asarray(_yes_or_no(value)), name),
    'A switch: yes or no. To turn a part of the model on or off (with Choose), or to try a variant.',
    ("Boolean", "Booleano", "Interruptor", "Toggle", "Verdadero o falso", "Encender", "Apagar"),
))


def _yes_or_no(value) -> bool:
    if isinstance(value, str):
        from .values import read_value
        value = read_value(value)
    if isinstance(value, str):
        raise ShapeError(tr('“{value}” is neither yes nor no.').format(value=value))
    return bool(value)


_register(NodeType(
    'Combine conditions', 'Measure',
    (Input('a', None, help='a condition: a yes/no per element (from Compare, from Inside…)'),
     Input('b', None, help='another condition', visible_if=lambda e: e.get('operation', 'and') not in ('not', False)),
     Input('operation', 'and', single=True, options=tuple(COMBINATIONS),
             help='and: both · or: either · not: the opposite of a · only one: one or the other, not both')),
    'yes/no',
    # «no» chosen from the list used to be saved as a yes/no (false): those files open the same.
    lambda a, b, operation, name: combine_conditions(a, b, "not" if operation is False else operation, name),
    'Combines two conditions: both (and), either (or), only one (only one), or the opposite (not).',
    ("And", "Or", "Not", "Xor", "Gate", "Y", "O", "No", "Lógica", "Operador lógico", "Ambas", "Alguna"),
))

_register(NodeType(
    'Choose', 'Measure',
    (Input('condition', None, help='a yes/no per element, or a single Yes or no to choose a whole variant'),
     Input('yes', None, help='what goes where the condition is yes'),
     Input('no', None, help='what goes where it is no')),
    'chosen',
    lambda condition, yes, no, name: choose(condition, yes, no, name),
    'For each element: where the condition holds, the “yes” one; otherwise the “no” one (numbers or geometry: an '
    'open or closed panel). With a Yes or no, one variant or the other.',
    ("If", "Si", "Si entonces", "Pick", "Pick and Choose", "Stream Filter", "Condicional", "Variante", "Alternativa"),
))

_register(NodeType(
    'Inside', 'Measure',
    (Input('points', None, help='the points to test, or a geometry (each element by its centre)'),
     Input('region', None, help='a plan (closed curve, rectangle) or a closed volume (box, prism)')),
    'yes/no',
    lambda points, region, name: measures.inside(points, region, name),
    'Yes or no for each point: whether it falls inside a plan (seen in plan) or a closed volume. The columns '
    'inside the courtyard, the trees inside the building.',
    ("Contiene", "Contains", "Point in Curve", "Point in Brep", "Inclusión", "Adentro", "Dentro", "Interior"),
))

_register(NodeType(
    'Filter', 'Measure',
    (Input('data'),
     Input('mode', 'condition', single=True, options=MODES_FILTER,
             help='condition: a yes/no per element · pattern: a repeating “yes; no” · every: one in every N'),
     Input('condition', None, help='a yes/no per element (from Compare…)',
             visible_if=lambda e: e.get('mode', 'condition') == 'condition'),
     Input('level', None, single=True, levels_of='data', help='the level to filter; empty: the only one there is',
             visible_if=lambda e: e.get('mode') in ('pattern', 'every')),
     Input('pattern', "yes; no", single=True, help='repeating yes and no (or 1 and 0): “yes; no; no” keeps one in three',
             visible_if=lambda e: e.get('mode') == 'pattern'),
     Input('every', 2, single=True, help='one in every so many (2: one yes, one no)',
             visible_if=lambda e: e.get('mode') == 'every'),
     Input('from', 0, single=True, help='the first one kept (from 0)',
             visible_if=lambda e: e.get('mode') == 'every'),
     Input('remove', True, single=True,
             help='yes: those that do not pass are removed and the level gets shorter; no: they stay empty in their place',
             visible_if=lambda e: e.get('mode') in ('pattern', 'every')),
     Input('keep', 'those that do', single=True, options=KEEP,
             help="those that meet it, or those that don't (two Filters, one of each, split into two groups)")),
    'filtered',
    lambda data, mode, condition, level, pattern, every, from_, remove, keep, name: filter_mode(
        data, mode, condition, level, pattern, every, from_, bool(remove), _those_not(keep), name),
    'Keeps some elements: those meeting a condition, those of a repeating pattern (yes; no) or one in every N.',
    ("Dispatch", "Cull", "Separar", "Repartir", "Cull Pattern", "Cull Nth", "Patrón", "Uno de cada", "Alternar", "Saltear"),
))

_register(NodeType(
    'Normal', 'Measure',
    (Input('rectangle'),),
    'vector',
    lambda rectangle, name: geo.normal(rectangle, name),
    'Where each rectangle faces (outwards, on the faces of a prism).',
))

# --- Move and rotate -----------------------------------------------------------

_register(NodeType(
    'Vector', 'Transform',
    (Input('mode', "x, y, z", single=True, options=geo.MODES_VECTOR,
             help='x, y, z: type it · axis: along x, y or z · point to point · unit: length 1 · to a length · '
                  'multiply: times a number · add two · reverse · perpendicular to two'),
     Input('x', 0.0, visible_if=lambda e: e.get('mode', "x, y, z") == "x, y, z"),
     Input('y', 0.0, visible_if=lambda e: e.get('mode', "x, y, z") == "x, y, z"),
     Input('z', 1.0, visible_if=lambda e: e.get('mode', "x, y, z") == "x, y, z"),
     Input('axis', 'z', single=True, options=geo.VECTOR_AXES, help='the axis it goes along',
           visible_if=lambda e: e.get('mode') == 'axis'),
     Input('from', None, visible_if=lambda e: e.get('mode') == 'point to point'),
     Input('to', None, visible_if=lambda e: e.get('mode') == 'point to point'),
     Input('base', None, help='the starting vector',
             visible_if=lambda e: e.get('mode') in ('unit', 'invert', "perpendicular", 'to a length', 'multiply',
                                                    'add')),
     Input('other', (0.0, 0.0, 1.0), help='the second vector; by default, the vertical',
             visible_if=lambda e: e.get('mode') in ("perpendicular", 'add')),
     Input('length', 1.0, visible_if=lambda e: e.get('mode') == 'to a length'),
     Input('factor', 1.0, help='how many times: 2 doubles it, 0.5 halves it, negative reverses it; one per element '
                               'if it has levels',
           visible_if=lambda e: e.get('mode') in ('axis', 'multiply'))),
    'vector',
    lambda mode, x, y, z, axis, from_, to, base, other, length, factor, name: geo.vector(
        mode, x, y, z, from_, to, base, other, length, name, axis, factor),
    'A direction with its length: typed (x, y, z) or along an axis, from one point to another, or from another one '
    '(unit, with a length, times a number, added to another, reversed, perpendicular to two). It works wherever a '
    'point goes: Move, Line by direction…',
    ("Vector XYZ", "Vector 2Pt", "Unit Vector", "Unit X", "Unit Y", "Unit Z", "Reverse", "Cross Product",
     "Amplitude", "Multiply", "Scalar multiplication", "Addition", "Vector sum", "Dirección", "Producto vectorial",
     "Tangente", "Multiplicar vector", "Sumar vectores", "Eje"),
))

_register(NodeType(
    'Measure vector', 'Measure',
    (Input('mode', 'length', single=True, options=geo.MEASURES_VECTOR,
             help='length: how long it is · angle: the degrees between two vectors'),
     Input('base', None, help='the vector to measure'),
     Input('other', (0.0, 0.0, 1.0), help='the second vector (by default, the vertical)',
             visible_if=lambda e: e.get('mode') == 'angle')),
    'size',
    lambda mode, base, other, name: geo.measure_vector(mode, base, other, name),
    'The length of a vector, or the angle (in degrees) between two: 90, perpendicular.',
    ("Vector Length", "Angle", "Ángulo", "Largo de vector", "Inclinación", "Deconstruct Vector"),
))

_register(NodeType(
    'Arrow', 'Curves',
    (Input('from', (0.0, 0.0, 0.0), help='where the arrow starts'), Input('vector'),
     Input('scale', 1.0, help='to see it longer or shorter')),
    'arrow',
    lambda from_, vector, scale, name: geo.arrow(from_, vector, scale, name),
    'A vector placed at a point, to see it: an arrow. It also works as a line.',
    ("Vector Display", "Mostrar vector", "Ver vector", "Arrow"),
))

_register(NodeType(
    'Move', 'Transform',
    (Input('geometry'),
     Input('mode', "vector", single=True, options=geo.MODES_MOVE,
             help='vector: which way and how far · point to point: what is at “from” ends up at “to”'),
     Input('vector', (0.0, 0.0, 1.0), help='which way; by default, upwards (0, 0, 1)',
             visible_if=lambda e: e.get('mode', "vector") == "vector"),
     Input('distance', None, help='if given, the vector only sets the direction: “3” moves 3 m up',
             visible_if=lambda e: e.get('mode', "vector") == "vector"),
     Input('from', None, help='the starting point (the base point): a centroid, a corner…',
             visible_if=lambda e: e.get('mode') == 'point to point'),
     Input('to', None, help='where that point ends up',
             visible_if=lambda e: e.get('mode') == 'point to point')),
    'geometry',
    lambda geometry, mode, vector, distance, from_, to, name: geo.move(
        geometry, vector, distance, name=name, mode=mode, from_=from_, to=to),
    'Moves each element: by a vector (or a distance along it; by default, upwards), or from one point to another.',
    ("Trasladar", "Desplazar", "Move", "Llevar", "Punto base", "Vector 2Pt", "De un punto a otro"),
))

_register(NodeType(
    'Rotate', 'Transform',
    (Input('geometry'), Input('degrees'),
     Input('axis', "vertical", single=True, options=("vertical", "x", "y", "direction"),
           help='vertical, x, y, or any direction (a vector): the axis of a hinge, the slope of a roof'),
     Input('centre', (0.0, 0.0, 0.0), help='a point the axis passes through'),
     Input('direction', None, help='the direction of the axis (a vector, or one per element)',
           visible_if=lambda e: e.get('axis') == "direction")),
    'geometry',
    lambda geometry, degrees, axis, centre, direction, name: geo.rotate(geometry, degrees, axis, centre, direction,
                                                                        name),
    'Rotates each element about an axis: vertical, x, y or any direction, through a centre.',
    ("Rotar", "Rotate Axis", "Rotate 3D", "Girar sobre un eje"),
))

_register(NodeType(
    'Orient', 'Transform',
    (Input('geometry'),
     Input('from', (0.0, 0.0, 0.0), help='the point of the geometry that goes to «to» (its base, its corner)'),
     Input('from_direction', (1.0, 0.0, 0.0), help='which way the geometry looks along: its x', advanced=True),
     Input('from_normal', (0.0, 0.0, 1.0), help='which way is up in the geometry', advanced=True),
     Input('to', (0.0, 0.0, 0.0), help='where it goes: one point, or many (one copy at each)'),
     Input('to_direction', None, help='where its x looks there (some tangents); empty: the world x laid on the place'),
     Input('to_normal', (0.0, 0.0, 1.0), help='what is up there (the normals of a surface)')),
    'geometry',
    lambda geometry, from_, from_direction, from_normal, to, to_direction, to_normal, name: geo.orient(
        geometry, from_, from_direction, from_normal, to, to_direction, to_normal, name),
    'Takes the geometry to other places, turning it to their direction and their normal: a module on each point of '
    'a surface, a piece along a curve. It keeps shape and size.',
    ("Orient", "Orientar", "Orient Direction", "Plane to plane", "Align", "Alinear", "Ubicar"),
))

_register(NodeType(
    'Morph', 'Transform',
    (Input('geometry', help='the module: a piece drawn anywhere; its bounding box becomes each cell'),
     Input('into', help='the cells: boxes or blocks (eight corners, they can be twisted), panels, or eight points '
                        '(the corners of a box moved one by one: the four below, then the four above)'),
     Input('height', 1.0, help='for panels: how far the cell rises along the panel normal'),
     Input('reference', None, advanced=True,
           help='a box that stands for the module (its bounding box); empty: that of the module itself')),
    'geometry',
    lambda geometry, into, height, reference, name: geo.morph(geometry, into, height, reference, name),
    'Fits a module into each cell, bending with it: what fills the bounding box of the module comes to fill the '
    'cell, however twisted. Cells can be boxes, blocks (Thicken), panels of a Grid, or eight corners (the '
    'Vertices of a Bounding box, some of them moved).',
    ("Box Morph", "Morph", "Deformar", "Deformar en caja", "Encajar", "Twisted Box", "Caja torcida", "Mapear módulo"),
))

_register(NodeType(
    'Scale', 'Transform',
    (Input('geometry'), Input('factor', 1.0, help='more than 1 enlarges, less than 1 shrinks'),
     Input('centre', None, help='empty: each element about its own centre')),
    'geometry',
    lambda geometry, factor, centre, name: geo.scale(geometry, factor, centre, name),
    'Enlarges or shrinks each element.',
    ("Scale", "Escala", "Reducir tamaño", "Agrandar"),
))

def _panel(value, name=None) -> Data:
    if value is None:
        raise ShapeError(tr('Connect something to Info to see its value.'))
    return value if isinstance(value, Data) else Data.value(value, name)


_register(NodeType(
    'Info', 'Values',
    (Input('value', None, help='what you want to read: a number, a list, some points…'),),
    'value',
    lambda value, name: _panel(value, name),
    'Shows on its card the value of what it receives (and passes it on unchanged): numbers, lists, points.',
    ("Print", "Panel", "Mostrar", "Ver valores", "Leer", "Imprimir", "Watch", "Inspeccionar", "Nota", "Información"),
))

_register(NodeType(
    'Sections', 'Fabrication',
    (Input('shape', help='a surface, a mesh or a body: what is cut into boards'),
     Input('thickness', 0.003, single=True, help='of the boards (the sheet they are cut from)'),
     Input('gap', 0.0, single=True, help='between one board and the next (0: glued together)'),
     Input('cuts', 'x', single=True, options=fab.CUTS,
           help='x: boards across x · y: across y · z: level boards, stacked · radial: boards through the vertical '
                'axis of the shape, like the segments of an orange · along a curve: boards square to a guide curve, '
                'which follow the shape'),
     Input('count', 8, single=True, help='how many radial boards (half a turn shared out)',
           visible_if=lambda e: e.get('cuts') == 'radial'),
     Input('guide', None, help='the curve the boards follow: each one square to it, one every board and gap along it '
                               '(a spine, the axis of a leaning tower)',
           visible_if=lambda e: e.get('cuts') == 'along a curve'),
     Input('piece', 'band', single=True, options=fab.PIECES,
           help='how the section of a surface becomes a piece: band: the curve and its offset under it · to base: '
                'the curve down to a common base under the whole shape'),
     Input('depth', 0.01, single=True,
           help='band: how deep it is · to base: how far the base is under the lowest point'),
     Input('show', 'outlines', single=True, options=fab.SHOW_SECTIONS,
           help='outlines: the closed curves to cut · boards: with their thickness, to see them')),
    'sections',
    lambda shape, thickness, gap, cuts, count, guide, piece, depth, show, name: fab.sections(
        shape, thickness, gap, cuts, piece, depth, show, count, guide, name),
    'Cuts a shape into boards of a sheet’s thickness, each one a closed outline ready to cut: a surface closes as '
    'a band that follows it, or down to a common base (a terrain model, a sliced landscape). Glued in order, the '
    'boards rebuild the shape.',
    ("Sectioning", "Seccionar", "Secciones", "Contouring", "Rebanar", "Láminas", "Maqueta por capas",
     "Rodajas", "Slices", "Laser cut", "Corte láser", "CNC"),
))

_register(NodeType(
    'Slots', 'Fabrication',
    (Input('first', help='a family of flat boards (the Sections across x, for example)'),
     Input('second', help='another family that crosses the first (the Sections across y)'),
     Input('thickness', 0.003, single=True, help='of the boards (the sheet): the width of each slot'),
     Input('clearance', 0.0002, single=True, help='added to the width of the slots, so the boards go in (a laser: '
                                                  '0.1 to 0.2 mm; a router: more)'),
     Input('slotted', 'first from above', single=True, options=fab.SLOTTED_FROM,
           help='which family is slotted from above; the other, from below'),
     Input('show', 'first', single=True, options=fab.SHOW_SLOTS,
           help='first or second: that family with its slots, ready to lay flat and cut · boards: all of them with '
                'their thickness, to see how they fit'),
     Input('towards', None, advanced=True,
           help='which way is «above» (a vector); empty: upwards, or away from the centre if the crossings spread out '
                '· a wall’s front, so «first from below» slots the first family from the back')),
    'slotted',
    lambda first, second, thickness, clearance, slotted, show, towards, name: fab.slots(
        first, second, thickness, clearance, slotted, show, towards, name),
    'Where two families of boards cross (a waffle, an egg-crate), a slot halfway in each: one board slotted from '
    'above, the other from below, as wide as the board that goes in plus a clearance. Slotted, the boards slide into '
    'one another and the structure holds itself.',
    ("Waffle", "Waffling", "Encastres", "Encastre", "Ranuras", "Half lap", "Media madera", "Egg crate",
     "Costillas cruzadas", "Retícula de costillas", "Intersecciones", "Notch", "Slot"),
))

_register(NodeType(
    'Lay flat', 'Fabrication',
    (Input('pieces', help='flat closed curves: the outlines to cut (from Sections, Unroll…)'),
     Input('width', 0.6, single=True, help='of the sheet (600 × 400 mm: the bed of a laser; 2440 × 1220 mm: a '
                                           'board for a router)'),
     Input('height', 0.4, single=True, help='of the sheet'),
     Input('spacing', 0.004, single=True, help='between pieces (a laser: a few millimetres; a router: more than its '
                                               'bit)'),
     Input('margin', 0.01, single=True, help='from the edge of the sheet'),
     Input('turn', True, single=True, help='turn the pieces a quarter at a time if they fit better so'),
     Input('number', 0.005, single=True, help='the height of the numbers engraved on the pieces (0: without numbers)'),
     Input('show', 'pieces', single=True, options=fab.SHOW_SHEETS,
           help='(from files of before: now, Numbers and sheets shows the numbers and the sheets of a Lay flat)',
           visible_if=lambda e: e.get('show', 'pieces') != 'pieces'),
     Input('origin', (0.0, 0.0, 0.0), help='where the corner of the first sheet goes (on the ground)'),
     Input('more', None, help='a second family of pieces on the same sheets (the other ribs of a waffle): the '
                              'numbers then carry a letter, A for the first family and B for this one'),
     Input('nesting', 'fit together', single=True, options=fab.NESTING, advanced=True,
           help='fit together: each piece where it fits, also in the holes and hollows of the others (uses less '
                'sheet) · in rows: each one in its rectangle, in rows (quicker, tidier)')),
    'sheets',
    lambda pieces, width, height, spacing, margin, turn, number, show, origin, more, nesting, name: fab.lay_flat(
        pieces, width, height, spacing, margin, turn, number, show, origin, more, nesting, name),
    'Lays flat pieces on sheets, ready to cut: fitted into one another, the small ones in the holes and hollows of '
    'the big ones, each one with a number to engrave inside (the same number the 3D view gives it, to put them '
    'together). The panel says how many sheets and how much of them is used. Its numbers and the outlines of the '
    'sheets come out of a Numbers and sheets connected to it. Export them with File → Export → Cutting file.',
    ("Nesting", "Nest", "Anidar", "Acomodar en planchas", "Planchas", "Tableros", "Despiece", "Orient", "Lay flat",
     "Corte láser", "CNC", "Plancha", "Etiquetas", "Numerar piezas"),
))

_register(NodeType(
    'Bevel', 'Fabrication',
    (Input('pieces', help='flat closed curves (the outlines of Sections, Slots…), or the boards of Sections'),
     Input('thickness', 0.003, single=True, help='of the board (the sheet): it is centred on the piece, as Sections draws it'),
     Input('size', 0.001, single=True, help='how far the bevel goes, in and down: less than half the thickness on both faces'),
     Input('profile', 'rounded', single=True, options=bevel_module.PROFILES,
           help='rounded: convex, eased · chamfer: a straight cut at 45° · cove: concave, hollowed · custom: drawn '
                'with a curve'),
     Input('segments', 4, single=True, help='facets of the rounded or the cove: 1 is a chamfer, 2 is octagonal, more is '
                                                   'smoother',
           visible_if=lambda e: e.get('profile', 'rounded') in ('rounded', 'cove')),
     Input('curve', None, help='the corner of the board seen from its side: from the top face (left, high) down to '
                               'the edge (right, low); its size does not matter',
           visible_if=lambda e: e.get('profile') == 'custom'),
     Input('faces', 'both faces', single=True, options=bevel_module.FACES,
           help='both · top: the one looking up (an upright board, towards +x or +y) · bottom: the other one')),
    'boards',
    lambda pieces, thickness, size, profile, segments, curve, faces, name: bevel_module.bevel(
        pieces, thickness, size, profile, segments, curve, faces, name),
    'Boards with their edges eased, to see them, print them or mill them with a bevel bit (a laser always cuts '
    'straight). Rounded, chamfer, cove, a few facets or a profile of one’s own, on one face or both. The outline in the '
    'middle of the board is still the piece’s, so it lays flat and cuts the same.',
    ("Bisel", "Chaflán", "Chamfer", "Fillet", "Redondeo", "Media caña", "Cove", "Canto", "Matar el canto", "Round over",
     "Edge", "Bevel"),
))

_register(NodeType(
    'Numbers and sheets', 'Fabrication',
    (Input('laid', help='the pieces of a Lay flat'),
     Input('show', 'numbers', single=True, options=fab.SHOW_MARKS,
           help='numbers: to engrave, inside each piece · sheets: their outlines'),
     Input('lettering', 'plain', single=True, options=fab.NUMBER_LETTERS,
           help='plain: straight strokes · rounded: their corners eased · font: an installed font, its outlines (to '
                'engrave the numbers filled)',
           visible_if=lambda e: e.get('show', 'numbers') == 'numbers'),
     Input('weight', 'single', single=True, options=strokes.WEIGHTS,
           help='single: one pass of the machine · bold: two passes, a little apart · outline: the outline of each '
                'stroke, to engrave the numbers filled',
           visible_if=lambda e: e.get('show', 'numbers') == 'numbers' and e.get('lettering') != 'font'),
     Input('reading', 'along the sheet', single=True, options=fab.READINGS,
           help='along the sheet: read from its long side · turned a quarter: read from its short side (where it '
                'fits)', visible_if=lambda e: e.get('show', 'numbers') == 'numbers'),
     Input('font', "", single=True, suggest=_font_families,
           visible_if=lambda e: e.get('show', 'numbers') == 'numbers' and e.get('lettering') == 'font',
           help='the name of an installed font; empty: the usual one of the system')),
    'marks',
    lambda laid, show, lettering, weight, reading, font, name: fab.numbers_and_sheets(
        laid, show, lettering, weight, reading, font, name),
    'The numbers of the pieces laid by a Lay flat (to engrave, blue) or the outlines of its sheets. They always follow '
    'the pieces: change the Lay flat and they move with them. Their colour, in the node panel.',
    ("Numbers", "Labels", "Tags", "Números", "Etiquetas", "Grabado", "Engrave", "Planchas", "Sheets", "Tag"),
))

_register(NodeType(
    'Print check', 'Fabrication',
    (Input('geometry', help='the piece to print: a body, a mesh, a surface (or a list of pieces)'),
     Input('show', 'problems', single=True, options=printing.SHOW,
           help='problems: where it fails, as red lines in the view (open edges, crossings, thin walls) · ready: '
                'yes or no for each piece · printer: the printer’s volume around the piece, to see whether it fits'),
     Input('width', 0.2, single=True, help='of the printer (its build volume)'),
     Input('depth', 0.2, single=True, help='of the printer (its build volume)'),
     Input('height', 0.2, single=True, help='of the printer (its build volume)'),
     Input('thickness', 0.0008, single=True, help='the thinnest wall the printer can make (0: not checked)')),
    'problems',
    lambda geometry, show, width, depth, height, thickness, name: printing.print_check(
        geometry, show, width, depth, height, thickness, name),
    'Says whether a piece can be 3D printed, and if not, why and where: closed (watertight), every edge between '
    'two faces, the faces turned outwards, not crossing itself, it fits in the printer, no wall thinner than the '
    'printer can make. The report, in the panel.',
    ("Printable", "3D print", "Imprimible", "Impresión 3D", "Revisar para imprimir", "Check", "Watertight",
     "Estanco", "Manifold", "Mesh check", "STL", "Volumen de impresión", "Build volume", "Espesor mínimo"),
))

_register(NodeType(
    'Equilibrium', 'Simulation',
    (Input('shape', help='what hangs: curves or lines (cables: the springs are their spans) or a mesh (a membrane: '
                         'the springs are its edges)'),
     Input('spans', 10, single=True, help='into how many equal spans each curve is divided: more, a smoother shape '
                                           '· 0: the vertices it already has (lines: one span each) · a mesh keeps '
                                           'its own'),
     Input('supports', 'ends or corners', single=True, options=sim.SUPPORTS,
           help='ends or corners: of each curve, of each mesh · border: the whole edge of each mesh · start: only '
                'the start of each curve (a weight hanging from it) · none: only «more supports»'),
     Input('more_supports', None, help='points that also hold it: the particle nearest each one is pinned there '
                                       '(move the point and the shape follows)'),
     Input('self_weight', 100.0, single=True, help='of all of it, in N (1 kg ≈ 10 N), shared out along the cables or '
                                                   'over the membrane'),
     Input('loads', None, help='points where a load hangs (on the particle nearest each one)'),
     Input('load', 10.0, help='at each load point: N towards gravity, or a vector (wind, a pull to one side)',
           visible_if=lambda e: e.get('loads') is not None),
     Input('stiffness', 10000.0, single=True,
           help='of the material, in N: the force that would stretch it to twice its length · more, it stretches '
                'less (a chain: very high)'),
     Input('rest_length', 1.0, single=True,
           help='how long each span wants to be, times its starting length: 1 elastic · less, pre-tensioned (it '
                'pulls itself shorter) · 0, a soap film (the least area) · more, relaxed'),
     Input('diagonals', 'no diagonals', single=True, options=sim.DIAGONALS,
           help='of each square of a mesh, as springs too: no diagonals, a cable net (the squares turn into '
                'diamonds) · one per square or both, a sheet that keeps its shape'),
     Input('weft', 1.0, single=True, advanced=True,
           help='the stiffness up the mesh (the second and fourth edge of each square), times the one across: a '
                'fabric that stretches more one way than the other'),
     Input('bending', 0.0, single=True,
           help='how much it resists bending, times the stiffness: 0 a cable, a net or a cloth, which fold freely · '
                '0.001 a sheet of rubber · 0.01 or more a shell or a bar, which keep their curvature'),
     Input('floor', None, single=True,
           help='the height of a floor it rests on and cannot go through (empty: no floor) · with a floor, it needs no '
                'supports'),
     Input('imperfection', 0.0, single=True, advanced=True,
           help='how far (m) its particles are shaken at random before starting: a stable shape comes back to the '
                'same rest; one that is not buckles (try 0.01)'),
     Input('ties', None, help='optional: lines whose two ends are pulled together, as stitches (a smocking, a '
                              'gather, a pleat)'),
     Input('tie_strength', 1.0, single=True, advanced=True,
           help='how hard the ties pull, times a typical span', visible_if=lambda e: e.get('ties') is not None),
     Input('gravity', (0.0, 0.0, -1.0), help='where the weight goes (a vector) · upwards: the hanging shape turned '
                                             'over, which works in compression'),
     Input('moment', 1.0, single=True,
           help='1: at rest · 0: the start · in between, on its way to the rest (the ▶ of the panel plays it from 0 '
                'to 1)'),
     Input('show', 'shape', single=True, options=sim.SHOW,
           help='shape: at rest · spans: each span as a line · elongation: how much each span stretched, in % · '
                'forces: in each span, in N (tension +, compression −)'),
     Input('hand_supports', (), hidden_if_empty=True,
           help='the supports moved by hand in the 3D view (the «Move supports» button): each one, where its particle '
                'started and where it is held')),
    'equilibrium',
    lambda shape, spans, supports, more_supports, self_weight, loads, load, stiffness, rest_length, diagonals, weft,
    bending, floor, imperfection, ties, tie_strength, gravity, moment, show, hand_supports, name: sim.equilibrium(
        shape, spans, supports, more_supports, self_weight, loads, load, stiffness, rest_length, gravity, show, name,
        diagonals, weft, moment, bending, floor, imperfection, hand_supports, ties, tie_strength),
    'The shape a cable, a membrane or a shell takes at rest, hanging from its supports or lying on a floor, under its '
    'weight and its loads: the form finding of hanging models, cable nets, tensile fabrics, soap films and shells. It '
    'always gives the shape already at rest: change a support or a load and it hangs again. It can also say how much '
    'each span stretches and with what force. The forces are for finding the shape, not for sizing cables or '
    'membranes.',
    ("Equilibrium", "Kangaroo", "Form finding", "Búsqueda de forma", "Simulation", "Simulación", "Springs",
     "Resortes", "Cable", "Cable colgado", "Hanging", "Colgar", "Particle", "Partículas", "Physics", "Física",
     "Relax", "Relajar", "Funicular", "Hooke", "Membrane", "Membrana", "Tela", "Fabric", "Tensile",
     "Tensoestructura", "Soap film", "Película de jabón", "Minimal surface", "Superficie mínima", "Red de cables",
     "Cable net", "Shell", "Cáscara", "Bending", "Flexión", "Floor", "Piso", "Imperfection", "Pandeo", "Buckling",
     "Smocking", "Fruncido", "Frunce", "Pliegues", "Pinch", "Lazos"),
))

_register(NodeType(
    'Bar analysis', 'Simulation',
    (Input('shape', None, help='the bars: lines, curves (each span a bar) or a mesh (each edge a bar), welded where '
                               'they touch'),
     Input('spans', 0, single=True, help='in how many bars each curve is divided; 0: the vertices it has'),
     Input('diagonals', 'no diagonals', single=True, options=sim.DIAGONALS,
           help='of each square of a mesh, as bars too: no diagonals, a frame of squares (it holds by its rigid '
                'joints) · one per square or both, braced like a truss (much stiffer)'),
     Input('supports', None, help='points: the joint nearest each one is held'),
     Input('support', 'clamped', single=True, options=fra.SUPPORTS,
             help='clamped: nothing moves nor turns · pinned: it turns but does not move · roller: it only cannot move '
                  'along the weight'),
     Input('loads', None, help='points where a force is applied (at the nearest joint)'),
     Input('load', 10000.0, help='in N, towards the gravity (1 kN = 1000 N), or a vector; one for all or one per '
                                 'point', visible_if=lambda e: e.get('loads') is not None),
     Input('load_per_metre', 0.0, single=True, help='a load spread along every bar, in N per metre, towards the '
                                                    'gravity (a slab, a roof, snow)'),
     Input('self_weight', True, single=True, help='yes: the weight of the bars themselves is added'),
     Input('material', 'steel S275', single=True, options=tuple(sec.MATERIALS),
             help='its stiffness, its weight and its strength'),
     Input('section', 'IPE 300', single=True,
             help='IPE 300 · HEA 200 · HEB 160 · rect 200x400 · tube 200x100x8 · pipe 168x8 · round 50 (in mm), or a '
                  'number: its place in the catalogue (0 = IPE 80 … 55 = HEB 600), for a slider'),
     Input('gravity', (0.0, 0.0, -1.0), single=True, advanced=True, help='where the weight goes'),
     Input('scale', 0.0, single=True, help='how many times the moves are drawn in the deformed shape; 0: automatic '
                                           '(the largest, a twentieth of the size, so it always looks as large: to '
                                           'compare loads or sections, give a number)'),
     Input('show', 'deformed', single=True, options=fra.SHOW,
             help='deformed: the bars bent (exaggerated) · displacements: how much each joint moves, in m · axial '
                  'forces: in N, tension +, compression − · moments: the largest of each bar, in N·m · utilization: '
                  'how hard each bar works, in % of its strength · reactions: the force at each support · largest '
                  'displacement, largest utilization, total weight (kg): a single number, for Find the best…')),
    'bars',
    lambda shape, spans, diagonals, supports, support, loads, load, load_per_metre, self_weight, material, section,
    gravity, scale, show, name: fra.bar_analysis(shape, spans, supports, support, loads, load, load_per_metre,
                                                 bool(self_weight), material, section, gravity, scale, show, name,
                                                 diagonals),
    'How much a structure of bars bends, and how hard each bar works: beams, columns, porticos, trusses, '
    'gridshells. Give the bars, the supports, the loads, the material and the section (IPE, HEA, HEB, tubes…): it '
    'gives the deformed shape, the forces in each bar, how much of its strength it uses, and the weight. A first '
    'sizing: it does not check buckling nor the joints, and applies no safety factors or building codes: an '
    'approximation for design, to be checked by a structural engineer.',
    ("Karamba", "Frame", "Pórtico", "Beam", "Viga", "Columna", "Column", "Truss", "Cercha", "Celosía", "FEM", "FEA",
     "Elementos finitos", "Estructura", "Structure", "Cálculo estructural", "Deflection", "Flecha", "Deformada",
     "Momento", "Moment", "Axil", "Utilization", "Aprovechamiento", "IPE", "HEA", "HEB", "Perfil", "Section",
     "Dimensionar", "Sizing", "Reacciones"),
))

_register(NodeType(
    'Topology optimization', 'Simulation',
    (Input('region', None, help='where the material can go: a rectangle, a circle or a closed curve, in any plane '
                                '(2D); a box or a closed mesh (3D)'),
     Input('voids', None, help='outlines (or bodies, in 3D) that must stay empty: a door, a window, a passage'),
     Input('solid_parts', None, help='outlines (or bodies, in 3D) that must stay full (they are not optimized): a '
                                     'slab, a support plate'),
     Input('supports', None, help='points or outlines held in every direction'),
     Input('rollers', None, help='points or outlines held only along the weight: they can slide sideways'),
     Input('loads', None, help='points or outlines where a force is applied'),
     Input('load', 1000.0, help='in N, towards the gravity, or a vector; on an outline, shared by its corners',
             visible_if=lambda e: e.get('loads') is not None),
     Input('self_weight', False, single=True, help='yes: the weight of the material itself is a load too'),
     Input('material', 'concrete C25/30', single=True, options=tuple(sec.MATERIALS),
             help='its stiffness and its weight (the shape does not depend on it; the displacements do)'),
     Input('thickness', 0.3, single=True, advanced=True, help='of the plate, in m (in 2D)'),
     Input('density', 0.4, single=True, help='how much of the region stays full, from 0 to 1: 0.3 leaves 30 % of the '
                                             'material'),
     Input('resolution', 60, single=True, help='cells along the longer side: more, finer and slower'),
     Input('turns', 60, single=True, advanced=True, help='at most; it stops earlier when it no longer changes'),
     Input('smoothing', 1.5, single=True, advanced=True,
             help='in cells: the thinnest bar it leaves is about twice this'),
     Input('gravity', (0.0, 0.0, -1.0), single=True, advanced=True, help='where the weight goes'),
     Input('moment', 1.0, single=True,
           help='1: the shape · 0: the start, the region full and thin · in between, on its way (the ▶ of the panel '
                'plays it from 0 to 1)'),
     Input('show', 'shape', single=True, options=top.SHOW,
             help='shape: its outline, closed curves to extrude or cut (2D), or the surface of the body (3D) · '
                  'plate: the shape filled in, with its holes, to give it thickness (2D) · cells: the full cells, '
                  'as squares or cubes · grid: all the cells (to colour by density or stress) · density: of each cell, from 0 to 1 · stress: Von Mises, in Pa · largest displacement: '
                  'a single number, in m')),
    'shape',
    lambda region, voids, solid_parts, supports, rollers, loads, load, self_weight, material, thickness, density,
    resolution, turns, smoothing, gravity, moment, show, name: top.topology_2d(
        region, voids, solid_parts, supports, rollers, loads, load, bool(self_weight), material, thickness, density,
        resolution, turns, smoothing, gravity, show, name, moment),
    'Where the material should be, inside a region, to carry some loads to some supports with the least of it: '
    'it starts full and thin, and turn after turn the material goes to where it works, until a structure is left '
    '(the arches and diagonals of a beam, the fan of a Michell truss, the legs of a bridge). Give the region (an '
    'outline in 2D, a body in 3D), the supports, the loads and how much material stays: it gives the shape. A '
    'form study: the result still has to be designed and checked as a structure.',
    ("Millipede", "Topostruct", "ESO", "BESO", "XESO", "SIMP", "Topology", "Topología", "Optimización",
     "Optimization", "Form finding", "Estructura óptima", "Michell", "MBB", "Ameba"),
))

_register(NodeType(
    'Planarize', 'Fabrication',
    (Input('panels', None, help='the panels of a surface: closed curves that share their corners, like the cells of a '
                                'Grid on a surface (squares, hexagons…)'),
     Input('iterations', 2000, single=True, advanced=True,
           help='how many rounds at most (it stops before when nothing moves): more, flatter on a saddle'),
     Input('show', 'panels', single=True, options=pln.SHOW,
           help='panels: flat, still corner to corner · flatness: how far each one still is from flat, in m · '
                'flatness before: how warped each one was')),
    'panels',
    lambda panels, iterations, show, name: pln.planarize(panels, iterations, show, name),
    'Makes the panels of a curved surface flat, so they can be cut from boards or glass, while they keep meeting '
    'corner to corner: each panel goes onto the plane that fits it best and each corner to the average of what its '
    'panels ask, again and again. Easy on a vault or a scroll; on a saddle, hexagons bend inwards.',
    ("Planarize", "Planarizar", "Planar panels", "Paneles planos", "PQ mesh", "P-Hex", "Planar quads",
     "Cuadriláteros planos", "Hexágonos planos", "Vidrio", "Glass", "Flat panels", "Panelizar"),
))

_register(NodeType(
    'Plates', 'Fabrication',
    (Input('shape', None, help='a mesh, a box or a surface: each face, a plate'),
     Input('thickness', 0.012, single=True, help='of the board the plates are cut from, in m'),
     Input('gap', 0.01, single=True, help='between two plates that meet, in m, the same at any angle'),
     Input('show', 'plates', single=True, options=pla.SHOW,
           help='plates: each face as a board of its thickness, trimmed back from its edges · outlines: the trimmed '
                'faces, flat, for Lay flat · angles: between the two faces of each edge, in degrees · setbacks: how '
                'far each edge is trimmed back, in m')),
    'plates',
    lambda shape, thickness, gap, show, name: pla.plates(shape, thickness, gap, show, name),
    'Turns each face of a shape into a plate of some thickness, trimmed back from each edge just enough for the '
    'plates that meet there to keep the same gap, whatever their angle (an acute edge, more; a flat one, little). '
    'For faceted pavilions of boards: the plates, their outlines to cut, and the angles of the edges.',
    ("Plates", "Placas", "Paneles", "Tableros", "Facetado", "Faceted", "Hinge", "Bisagra", "Gap", "Junta",
     "Pabellón", "Pavilion", "Plywood", "Contrachapado"),
))

_register(NodeType(
    'Hypar', 'Surfaces',
    (Input('panels', None, help='panels of four corners: a Grid on a surface, rectangles'),
     Input('lift', 0.1, help='how much two opposite corners rise, in m, along the panel\'s normal: one for all, or one '
                             'per panel (0: flat)'),
     Input('corners', 'first and third', single=True, options=hyp.CORNERS,
           help='which two opposite corners rise (the other two stay, and the fold joins them)'),
     Input('show', 'folded piece', single=True, options=hyp.SHOW,
           help='folded piece: the curved saddle between the four corners · flat piece: what is cut out of the '
                'sheet, opened along its fold (every edge keeps its length), for Lay flat · fold: the diagonal to '
                'score · longest edge: of each piece, the one that has to fit on the sheet')),
    'hypar',
    lambda panels, lift, corners, show, name: hyp.hypar(panels, lift, corners, show, name),
    'Folds each panel into a hypar (a hyperbolic paraboloid): two opposite corners rise and the panel becomes a '
    'saddle of straight lines, like a sheet of paper folded along a diagonal. Gives the folded piece, the flat piece '
    'to cut, its fold and its longest edge.',
    ("Hypar", "Paraboloide hiperbólico", "Hyperbolic paraboloid", "Silla de montar", "Origami", "Plegado", "Fold",
     "Papel plegado", "Folded panel", "Panel plegado", "Superficie reglada"),
))

_register(NodeType(
    'Sun', 'Environment',
    (Input('location', 'Madrid', single=True, options=sn.LOCATIONS,
           help='a city of the list, or «other place» to give its latitude, longitude and time zone'),
     Input('latitude', 40.42, single=True, help='degrees: + north of the equator, − south',
           visible_if=lambda e: e.get('location') == sn.OTHER),
     Input('longitude', -3.70, single=True, help='degrees: + east of Greenwich, − west',
           visible_if=lambda e: e.get('location') == sn.OTHER),
     Input('time_zone', 1.0, single=True, help='hours from UTC without summer time (Madrid +1, Montevideo −3)',
           visible_if=lambda e: e.get('location') == sn.OTHER),
     Input('day', 21, help='from 1 to 31; or a list'),
     Input('month', 6, help='from 1 (January) to 12 (December); or a list'),
     Input('hour', 12.0, help='local standard time, without summer time: 13.5 is half past one; or a list'),
     Input('north', 0.0, single=True, advanced=True,
           help='degrees the north is turned from +Y, counterclockwise (0: the north is up in plan)'),
     Input('centre', (0.0, 0.0, 0.0), single=True, advanced=True, help='where the diagram stands'),
     Input('scale', 10.0, single=True, help='the radius of the diagram and the distance of the sun, in m'),
     Input('show', 'diagram', single=True, options=sn.SHOW,
           help='diagram: the horizon, the path of the 21st of each month and the hour lines · day path: the curve '
                'of the sun that day · position: a point in the sky · beam: an arrow from the sun to the centre · '
                'ray: the way the light goes (a vector, for angles and shadows) · altitude and azimuth: in degrees '
                '(azimuth from the north, clockwise) · sunrise and sunset: in hours')),
    'sun',
    lambda location, latitude, longitude, time_zone, day, month, hour, north, centre, scale, show, name: sn.sun(
        location, latitude, longitude, time_zone, day, month, hour, north, centre, scale, show, name),
    'Where the sun is for a place, a day and an hour, and its path: the solar diagram, the ray of light for angles '
    'and shadows, its altitude and azimuth, and the sunrise and sunset. The ▶ of the hour plays the day.',
    ("Sun path", "Recorrido solar", "Diagrama solar", "Carta solar", "Sunlight", "Soleamiento", "Asoleamiento",
     "Ladybug", "GECO", "Ecotect", "EcoSunPath", "EcoSunRays", "Solar", "Sol", "Rayo de sol", "Altura solar",
     "Azimut", "Amanecer", "Atardecer", "Salida del sol", "Puesta del sol"),
))

_register(NodeType(
    'Shadow', 'Environment',
    (Input('geometry', None, help='what casts the shadow: boxes, surfaces, meshes'),
     Input('ray', None, help='the ray of a Sun (its «show» on ray): the way the light goes; with a list of hours, '
                             'the shadows of all of them'),
     Input('ground', 0.0, single=True, help='the height of the ground where the shadow falls',
           visible_if=lambda e: e.get('surfaces') is None),
     Input('surfaces', None, help='optional: where the shadow falls instead of the ground (a terrain, a façade, '
                                  'another building), face by face: more cells, a finer shadow'),
     Input('show', 'shadow', single=True, options=sha.SHOW,
           options_if=lambda e: sha.ON_SURFACES if e.get('surfaces') is not None else sha.ON_GROUND,
           help='shadow: the shadow as a flat mesh (on surfaces, their faces in shadow) · outline: its closed '
                'curves, on the ground · area: in m², on the ground · sunlit: the faces of the surfaces in the sun · '
                'in shadow: for each face of the surfaces, from 0 (in the sun) to 1 (in shadow all the hours) · faces: '
                'all the faces of the surfaces, painted by how long they are in shadow')),
    'shadow',
    lambda geometry, ray, ground, surfaces, show, name: sha.shadow(geometry, ray, ground, surfaces, show, name),
    'The shadow of some geometry with the ray of a Sun: on the ground, exact, with its outline and its area; or on '
    'other surfaces (a terrain, a façade), face by face. With the ▶ of the hour, it moves through the day.',
    ("Shadow", "Sombra", "Sombras", "MeshShadow", "Proyectar sombra", "Sombra arrojada", "Cast shadow",
     "Asoleamiento", "Soleamiento", "Ladybug", "GECO"),
))

_register(NodeType(
    'Incidence', 'Environment',
    (Input('faces', None, help='panels (a Grid), a mesh, a surface or a box'),
     Input('ray', None, help='the ray of a Sun (its «show» on ray); with a list of hours, their average'),
     Input('side', 'its face', single=True, options=sn.SIDES,
           help='its face: the sun counts on the side each face looks to (its normal) · both faces: on either side '
                '(for a surface whose side does not matter)'),
     Input('show', 'sunlight', single=True, options=sn.INCIDENCE,
           help='sunlight: from 1 (the sun square on the face) to 0 (grazing, or from behind) · angle: in degrees '
                'from the normal of the face (0 square, 90 grazing, more than 90 from behind)')),
    'incidence',
    lambda faces, ray, side, show, name: sn.incidence(faces, ray, side, show, name),
    'How straight the sun reaches each face (the cosine law): 1 when it falls square, 0 when it grazes or comes from '
    'behind. For panels that open or close with the sun, or to see which side of a building gets the sun.',
    ("Incidence", "Incidencia", "Ángulo solar", "Angle", "Ángulo de incidencia", "Lambert", "Coseno",
     "Responsive skin", "Piel que responde", "Piel adaptable", "Sol en la fachada"),
))

_register(NodeType(
    'Insolation', 'Environment',
    (Input('faces', None, help='what is analysed: panels (a Grid), a mesh, a surface or a box'),
     Input('obstructions', None, help='optional: what shades the faces (the neighbours, the trees, the rest of the '
                                      'building); the faces shade each other anyway'),
     Input('climate', None, help='optional: a Climate node, the real sun of each hour from a weather file (and its '
                                 'place); without it, a clear sky'),
     Input('location', 'Madrid', single=True, options=sn.LOCATIONS,
           help='a city of the list, or «other place» to give its latitude, longitude and time zone',
           visible_if=lambda e: e.get('climate') is None),
     Input('latitude', 40.42, single=True, help='degrees: + north of the equator, − south',
           visible_if=lambda e: e.get('climate') is None and e.get('location') == sn.OTHER),
     Input('longitude', -3.70, single=True, help='degrees: + east of Greenwich, − west',
           visible_if=lambda e: e.get('climate') is None and e.get('location') == sn.OTHER),
     Input('time_zone', 1.0, single=True, help='hours from UTC without summer time (Madrid +1, Montevideo −3)',
           visible_if=lambda e: e.get('climate') is None and e.get('location') == sn.OTHER),
     Input('period', 'year', single=True, options=ins.PERIODS,
           help='year · summer and winter: the three months around the solstice (in the hemisphere of the place) · '
                'month · day'),
     Input('month', 6, single=True, help='from 1 to 12', visible_if=lambda e: e.get('period') in ('month', 'day')),
     Input('day', 21, single=True, help='from 1 to 31', visible_if=lambda e: e.get('period') == 'day'),
     Input('from_hour', 0.0, single=True, advanced=True, help='only the hours from this one (local standard time)'),
     Input('to_hour', 24.0, single=True, advanced=True, help='up to this one'),
     Input('side', 'its face', single=True, options=ins.SIDES, advanced=True,
           help='its face: the side each face looks to (its normal) · the other face: the opposite (if the faces '
                'come turned inwards)'),
     Input('north', 0.0, single=True, advanced=True,
           help='degrees the north is turned from +Y, counterclockwise (0: the north is up in plan)'),
     Input('sky_patches', 145, single=True, advanced=True,
           help='in how many pieces the sky is divided: more is finer and slower (145 is the usual)'),
     Input('show', 'radiation', single=True, options=ins.SHOW,
           help='radiation: the solar energy of the period, in kWh/m² (direct and diffuse: each part) · sun hours: '
                'the hours the sun reaches the face · sky view: how much sky it sees, from 0 to 1 · faces: the faces '
                'of a mesh, a surface or a box, one by one, to paint them (panels are painted as they are)')),
    'insolation',
    lambda faces, obstructions, climate, location, latitude, longitude, time_zone, period, month, day, from_hour,
    to_hour, side, north, sky_patches, show, name: ins.insolation(
        faces, obstructions, climate, location, latitude, longitude, time_zone, period, month, day, from_hour,
        to_hour, side, north, sky_patches, show, name),
    'The solar energy each face receives in a period (a year, a season, a month, a day), with what shades it: in '
    'kWh/m², or the hours of sun, or how much sky it sees. With a Climate, the real sun; without it, a clear sky. '
    'For passive gain '
    '(much sun in winter, little in summer) and to place solar panels: an estimate for comparing options, not an '
    'energy or yield calculation.',
    ("Insolation", "Asoleamiento", "Soleamiento", "Radiación solar", "Solar radiation", "Irradiation",
     "Irradiación", "kWh", "Horas de sol", "Sunlight hours", "Factor de cielo", "Sky view", "EcoSolCal",
     "Insolation Calculations", "Ladybug", "Radiation analysis", "Paneles solares", "Fotovoltaico",
     "Photovoltaic", "Ganancia solar", "Passive solar"),
))

_register(NodeType(
    'Climate', 'Environment',
    (Input('file', single=True, file="climate",
           help='a weather file (.epw), or the .zip it is downloaded in (climate.onebuilding.org)'),
     Input('show', 'temperature', single=True, options=cli.SHOW,
           help='temperature (°C) · humidity (%) · global, direct and diffuse radiation (kWh/m²) · wind speed (m/s) '
                'and direction (degrees from the north) · cloud cover (tenths of sky)'),
     Input('per', 'hour', single=True, options=cli.PER,
           help='hour: the 8760 of the year · day: 365 · month: 12 (the radiation summed, the rest averaged)')),
    'climate',
    lambda file, show, per, name: cli.climate_node(file, show, per, name),
    'The climate of a place from a weather file (.epw): the temperature, humidity, sun and wind of each hour of a '
    'typical year, or by day or month. Connected to Insolation, the real sun instead of a clear sky.',
    ("Climate", "Clima", "Weather", "EPW", "Weather file", "Archivo de clima", "Temperatura", "Humedad", "Viento",
     "EcoWeatherFile", "Ladybug", "Import EPW", "TMY", "Radiación medida"),
))

_register(NodeType(
    'Daylight', 'Environment',
    (Input('points', None, help='where the light is measured: points, a grid at the height of a desk (0.7 to 0.85 m)'),
     Input('room', None, help='the room: a box, or its walls, floor and ceiling; they reflect the light inside'),
     Input('glass', None, help='the windows: rectangles (or faces) on the walls of the room; where they lie on a '
                               'wall, they open it'),
     Input('obstructions', None, help='optional: what blocks the sky outside (louvers, eaves, neighbours)'),
     Input('transmittance', 70.0, single=True, help='how much light the glass lets through, in % (double glazing '
                                                    'about 70; single, 85)'),
     Input('reflectance', 50.0, single=True, help='how much light the walls, floor and ceiling reflect, in % (light '
                                                  'walls about 70; dark, 30)'),
     Input('location', 'Madrid', single=True, options=sn.LOCATIONS,
           help='a city of the list (its latitude gives the light of the sky), or «other place»'),
     Input('latitude', 40.42, single=True, help='degrees: + north of the equator, − south',
           visible_if=lambda e: e.get('location') == sn.OTHER),
     Input('sky_lux', 0.0, single=True, advanced=True,
           help='the illuminance of the overcast sky outside, in lux; 0: by the latitude (the usual design sky)'),
     Input('sky_patches', 290, single=True, advanced=True,
           help='in how many pieces the sky is divided: more is finer and slower'),
     Input('show', 'daylight factor', single=True, options=day.SHOW,
           help='daylight factor: the light of each point as a % of the light outside (as a reference, 2 % is often '
                'taken as a well-lit room and 5 % as a bright one) · illuminance: in lux · sky component: only '
                'what comes straight from the sky · average illuminance, average daylight factor and uniformity '
                '(the darkest over the average): a single number, for Find the best…')),
    'daylight',
    lambda points, room, glass, obstructions, transmittance, reflectance, location, latitude, sky_lux, sky_patches,
    show, name: day.daylight(points, room, glass, obstructions, transmittance, reflectance, location, latitude,
                             None, None, sky_lux, sky_patches, show, name),
    'How much natural light reaches some points inside a room, under an overcast sky: the daylight factor (in %), '
    'the lux, and the average and uniformity of the room. Give the points, the room, its windows and what shades '
    'them outside. A simplified estimate for comparing options; for regulations or certification, a validated '
    'simulation.',
    ("Daylight", "Luz natural", "Iluminación natural", "Daylight factor", "Factor de luz diurna", "FLD", "Lux",
     "Iluminancia", "Illuminance", "EcoLightCal", "Lighting Calculations", "Ladybug", "Honeybee", "Radiance",
     "Confort visual", "Visual comfort"),
))

_register(NodeType(
    'Length', 'Measure',
    (Input('curve', help='one or more curves (a closed one, its whole loop)'),),
    'length',
    lambda curve, name: measures.length(curve, name),
    'The length of each curve, in metres: a cable, an edge, a perimeter. Multiplied by a factor, it is the rest length '
    'of the springs of a simulation.',
    ("Length", "Len", "Largo", "Longitud", "Perímetro", "Perimeter", "Medir largo", "Metros lineales"),
))

_register(NodeType(
    'Area', 'Measure',
    (Input('geometry', help='a plan (closed curve), a surface or a volume (its skin)'),),
    'area',
    lambda geometry, name: measures.area(geometry, name),
    'The area of each element, in m²: a plan, a surface, the skin of a volume.',
    ("Area", "Superficie útil", "Metros cuadrados", "m2", "Medir área"),
))

_register(NodeType(
    'Volume', 'Measure',
    (Input('geometry', help='a closed body: a box, a prism, some pipes'),),
    'volume',
    lambda geometry, name: measures.volume(geometry, name),
    'The volume of each closed body, in m³.',
    ("Volume", "Metros cúbicos", "m3", "Medir volumen", "Cubicar"),
))

_register(NodeType(
    'Centroid', 'Measure',
    (Input('geometry'),),
    'centroid',
    lambda geometry, name: measures.centroid(geometry, name),
    'The centre of gravity of each element: of its volume, area or length (not the average of its vertices).',
    ("Centroid", "Area Centroid", "Volume Centroid", "Centro de gravedad", "Baricentro", "Centro de masa"),
))

_register(NodeType(
    'Coordinate', 'Measure',
    (Input('point'), Input('axis', "z", single=True, help='x, y or z', options=("x", "y", "z"))),
    'value',
    lambda point, axis, name: geo.coordinate(point, axis, name),
    'The x, y or z of each point: to compare it (the panels on one side, the ones at the top) or use it in a Formula.',
    ("Deconstruct Point", "Descomponer punto", "X", "Y", "Z", "Altura de un punto"),
))

_register(NodeType(
    'Project', 'Transform',
    (Input('geometry'), Input('amplitude', 0.0, help='at what height it ends up (0: the ground)')),
    'geometry',
    lambda geometry, amplitude, name: geo.project(geometry, amplitude, name),
    'Brings the geometry to a height, flat: its footprint on the ground (or on another horizontal plane).',
    ("Project", "Huella", "Aplanar", "Al suelo"),
))

#: c … h: optional inputs that appear one by one, on connecting the previous one (Merge, Join lists).
_OPTIONAL = tuple(
    Input(font, None, help='one more (optional): connect it and the next one appears',
            visible_if=None if font == "c" else (lambda e, before=before: e.get(before) is not None))
    for before, font in zip("bcdefg", "cdefgh"))

_register(NodeType(
    'Merge', 'Values',
    (Input('a'), Input('b'), *_OPTIONAL,
     Input('level', "part", single=True, help='name of the new level (of 2 to 8)')),
    'merged',
    lambda a, b, c, d, e, f, g, h, level, name: geo.join(a, b, level, name, c, d, e, f, g, h),
    'Two to eight data in one, with a new level: a curve and its footprint to join them with a surface; the '
    'start, middle and end of each line, for a curve through the three. Connect the last one and another appears.',
    ("Entwine", "Combinar", "Weave"),
))

_register(NodeType(
    'Merge lists', 'Values',
    (Input('a'), Input('b'), *_OPTIONAL,
     Input('level', "element", single=True, help='name of the merged list')),
    'list',
    lambda a, b, c, d, e, f, g, h, level, name: meshes.join_lists(a, b, level, name, c, d, e, f, g, h),
    'The elements of one list followed by those of another (up to eight), in a single list: the edges of a box '
    'and some bars. Connect the last one and another appears.',
    ("Merge", "Sumar listas", "Concatenar", "Encadenar"),
))

_register(NodeType(
    'Join meshes', 'Meshes',
    (Input('a', help='a mesh, or anything with faces (boxes, panels, frames, surfaces): all its elements'),
     Input('b', None, help='more to join (connect the last one and another appears)'), *_OPTIONAL,
     Input('weld', True, single=True,
           help='yes: the vertices that touch become one, and the mesh is a single piece (what smoothing needs)'),
     Input('doubled_faces', 'leave', single=True, options=mesh_tools.DOUBLED_FACES,
           help='a face with the same corners as another one (the wall between two boxes side by side): leave them, '
                'or remove both and leave only the outer skin'),
     Input('tolerance', 0.001, single=True, advanced=True,
           help='vertices closer than this (metres) are welded')),
    'mesh',
    lambda a, b, c, d, e, f, g, h, weld, doubled_faces, tolerance, name: mesh_tools.join_meshes(
        (a, b, c, d, e, f, g, h), bool(weld), tolerance, name, doubled_faces),
    'Everything with faces, with all its elements, as one mesh. Welded, the faces that touch share their vertices: '
    'a single piece. Where the edges of two parts do not meet vertex to vertex (a T-node), they do not weld: Mesh '
    'edges → naked shows those seams. With doubled faces removed, a group of boxes becomes its outer skin.',
    ("Mesh Join", "Join Meshes and Weld", "Weld", "Unir mallas", "Soldar", "Juntar mallas", "Una sola malla",
     "Cull adjacent faces", "Caras interiores", "Quitar caras dobles", "Caras compartidas", "Cáscara"),
))

_register(NodeType(
    'Mesh edges', 'Meshes',
    (Input('mesh', help='a mesh (or anything with faces)'),
     Input('which', 'naked', single=True, options=mesh_tools.EDGE_KINDS,
           help='naked: used by one face (the border, or a seam that did not weld) · inner: shared · all'),
     Input('level', "edge", single=True, advanced=True, help='name of the new level')),
    'edges',
    lambda mesh, which, level, name: mesh_tools.mesh_edges(mesh, which, level, name),
    'The edges of a mesh as lines. The naked ones are its border; inside a welded mesh, a naked edge is a seam '
    'that did not weld (two parts whose edges do not meet vertex to vertex: a T-node).',
    ("Mesh Edges", "Naked Edges", "Aristas de malla", "Bordes libres", "Bordes desnudos", "Costuras", "Nodos en T"),
))

_register(NodeType(
    'Smooth mesh', 'Meshes',
    (Input('mesh', help='a mesh (or anything with faces); for a shape of several parts, join and weld them first'),
     Input('method', 'Catmull-Clark', single=True, options=mesh_tools.SMOOTHING,
           help='Catmull-Clark: any faces (they become quadrilaterals) · Loop: triangles (each one becomes four)'),
     Input('levels', 2, single=True, help='how many times it is subdivided: each level, about four times the faces'),
     Input('border', 'smooth', single=True, options=mesh_tools.BORDERS,
           help='smooth: the border tends to a curve · fixed: it stays where it is · corners fixed: smooth, but its '
                'corners stay')),
    'mesh',
    lambda mesh, method, levels, border, name: mesh_tools.smooth_mesh(mesh, method, levels, border, name),
    'A smooth mesh from a simple one: each level splits every face and moves the vertices towards the smooth '
    'surface the mesh stands for. Model the shape with few faces, and let the levels round it.',
    ("Catmull-Clark", "Loop", "Subdivision", "Subdivisión", "Suavizar", "Smooth", "Suavizar malla", "Redondear",
     "Mesh smooth", "Superficie de subdivisión"),
))

_register(NodeType(
    'Edit mesh', 'Meshes',
    (Input('mesh', help='a mesh or anything with faces: the cage to shape by hand (boxes joined without their '
                        'doubled faces, for example)'),
     Input('moves', (), help='the vertices moved by hand, as [vertex, dx, dy, dz]: they are edited in the 3D view')),
    'mesh',
    lambda mesh, moves, name: mesh_tools.edit_mesh(mesh, moves, name),
    'Shape a mesh by hand: in the 3D view, choose its vertices and drag them (Alt: up or down). Only the moves are '
    'kept, so if the mesh that comes in changes, the edits stay. With Smooth mesh after it, the way to model a free '
    'shape: a coarse cage moved by hand, and the levels round it.',
    ("Edit Mesh", "Mover vértices", "Jaula", "Cage", "Modelar a mano", "Box modelling", "Editar vértices"),
))

_register(NodeType(
    'Delaunay', 'Meshes',
    (Input('points', help='the points to join in triangles; with other levels, one group for each'),
     Input('more', None, help='optional: a point (or several) added to each group, as the raised centre of a '
                              'triangle to make a pyramid'),
     Input('along', None, single=True, levels_of='points', advanced=True,
           help='the level of the points of each group; empty: the last one'),
     Input('plane', 'best fit', single=True, options=mesh_tools.DELAUNAY_PLANES, advanced=True,
           help='best fit: each group on the plane that fits it · plan: from above')),
    'mesh',
    lambda points, more, along, plane, name: mesh_tools.delaunay(points, more, along, plane, name),
    'Joins points in triangles as even as possible (no point inside the circle through the corners of a '
    'triangle): good triangles, without thin ones. With groups, one triangulation for each, all in one mesh.',
    ("Delaunay Mesh", "Delaunay", "Triangulación", "Triangular puntos", "Malla de puntos", "TIN"),
))

_register(NodeType(
    'Vertices', 'Divide',
    (Input('geometry'), Input('level', "vertex", single=True, help='name of the new level')),
    'points',
    lambda geometry, level, name: meshes.vertices(geometry, level, name),
    'The vertices of each element, as points: the 8 corners of a box.',
    ("Box Corners", "Esquinas", "Deconstruct Brep", "Puntos de control"),
))

_register(NodeType(
    'Edges', 'Divide',
    (Input('geometry'), Input('level', "edge", single=True, help='name of the new level')),
    'lines',
    lambda geometry, level, name: meshes.edges(geometry, level, name),
    'The edges of each element, as lines: the 12 of a box.',
    ("Wireframe", "Bordes", "Edges", "Deconstruct Brep"),
))

_register(NodeType(
    'Join nearest', 'Curves',
    (Input('points'), Input('count', 3, single=True, help='how many neighbours each point is joined to'),
     Input('level', "neighbour", single=True, help='name of the new level')),
    'lines',
    lambda points, count, level, name: meshes.join_nearest(points, count, level, name),
    'Joins each point to its nearest neighbours: a network of bars.',
    ("Closest Points", "Vecinos", "Red", "Proximity 3D", "Más cercanos"),
))

_register(NodeType(
    'Diagrid', 'Surfaces',
    (Input('surface', help='a tower, a dome, a roof'),
     Input('divisions_u', 8, single=True, help='diamonds along u (around, on a revolved tower)'),
     Input('divisions_v', 6, single=True, help='diamonds along v'),
     Input('what', 'diagonals', single=True, options=est.WHAT_DIAGRID,
             help='diagonals: the members, each one once · crossings: the nodes, where they cross · rings: the '
                   'belts through the nodes (with Cap, the floor slabs)'),
     Input('members', 'straight', single=True, options=est.BARS,
             help='straight from node to node, or curved following the surface',
             visible_if=lambda e: e.get('what', 'diagonals') != 'crossings'),
     Input('rings_along', "u", single=True, options=("u", "v"), help='along u or along v',
             visible_if=lambda e: e.get('what') == 'rings'),
     Input('continuous', False, single=True, help='each diagonal from end to end, as a single member (on a tower, '
                                                  'a helix): the two families cross cleanly at the nodes',
             visible_if=lambda e: e.get('what', 'diagonals') == 'diagonals')),
    'diagrid',
    lambda surface, divisions_u, divisions_v, what, members, rings_along, continuous, name: est.diagrid(
        surface, divisions_u, divisions_v, what, members, rings_along, name, bool(continuous)),
    'A grid of diagonal members on a surface, in diamonds: its members, its nodes and the rings that pass through '
    'them. With Pipe, the structure; with Cap on the rings, the floor slabs.',
    ("Diagrid", "Diagonal grid", "Malla diagonal", "Rombos", "Estructura en diagonal", "Torre diagrid",
     "Celosía", "Nudos", "Anillos", "Forjados"),
))

_register(NodeType(
    'Space frame', 'Surfaces',
    (Input('surface', help='a roof, a vault, a tower'),
     Input('divisions_u', 8, single=True, help='modules along u'),
     Input('divisions_v', 6, single=True, help='modules along v'),
     Input('truss_depth', 1.0, single=True, help='the distance between the two chords, along the normal (towards the '
                                             'back of the face; negative, to the other side)'),
     Input('what', 'all members', single=True, options=est.WHAT_MESH_SPACE,
             help='the members (all, one chord, or the diagonals) or the top or bottom crossings')),
    'space frame',
    lambda surface, divisions_u, divisions_v, truss_depth, what, name: est.mesh_space(
        surface, divisions_u, divisions_v, truss_depth, what, name),
    'A two-layer structure of members on a surface: the top chord on the surface, the bottom one shifted half a '
    'module and lowered by the depth, and diagonals joining them in pyramids. With Pipe, the members.',
    ("Space frame", "Spaceframe", "Malla espacial", "Estructura espacial", "Celosía espacial", "Estéreo estructura",
     "Mero", "Cordón superior", "Cordón inferior", "Pirámides", "Dos capas"),
))

_register(NodeType(
    'Chebyshev net', 'Surfaces',
    (Input('surface', help='the shape the lath mesh or fabric has to take'),
     Input('u', 0.5, single=True, help='the starting point, from 0 to 1 along the rows'),
     Input('v', 0.5, single=True, help='the starting point, from 0 to 1 along the columns'),
     Input('step', 1.0, single=True, help='the length of each side: the distance between nodes along a lath'),
     Input('count', 10, single=True, help='nodes on each side of the starting point (as far as it reaches)'),
     Input('angle', 90.0, single=True, help='between the two laths leaving the starting point, in degrees'),
     Input('rotation', 0.0, single=True, help='rotates the two starting laths, in degrees'),
     Input('what', 'all laths', single=True, options=est.WHAT_CHEBYSHEV,
             help='the laths (all, or one family) or the nodes')),
    'net',
    lambda surface, u, v, step, count, angle, rotation, what, name: est.chebyshev_net(
        surface, u, v, step, count, angle, rotation, what, name),
    'A net of quadrilaterals with four equal sides on a surface: the way a mesh of laths settles when bent (a '
    'lath roof, gridshell) or a fabric when it drapes. The laths keep their length between nodes; what changes is '
    'the angle between them.',
    ("Chebyshev net", "Chebyshev", "Tchebychev", "Gridshell", "Malla de listones", "Listones", "Red de pesca",
     "Tela", "Drapeado", "Compás", "Lados iguales"),
))

_register(NodeType(
    'Pipes', 'Surfaces',
    (Input('curves'), Input('radius', 1.0, single=True),
     Input('fillet', None, single=True, help='how much the nodes are filled; 0: no fillet; empty: half the radius'),
     Input('detail', meshes.DETAIL, single=True, help='points per radius: more is finer and slower')),
    'mesh',
    lambda curves, radius, fillet, detail, name: meshes.pipes(curves, radius, fillet, detail, name),
    'A pipe around each line, all fused into a single skin with smooth fillets at the nodes.',
    ("MultiPipe", "Barras", "Estructura", "Celosía espacial", "Tubos fundidos"),
))

_register(NodeType(
    'Pipe', 'Surfaces',
    (Input('curves'),
     Input('section', 'round', single=True, options=meshes.SECTIONS_PIPE,
             help='round · rectangular (width × height: a beam, a hollow section) · profile: that of a curve you '
                   'draw'),
     Input('radius', 0.5, single=True, visible_if=lambda e: e.get('section', 'round') == 'round'),
     Input('sides', meshes.SIDES_PIPE, single=True, help='sides of the section: more, rounder',
             visible_if=lambda e: e.get('section', 'round') == 'round'),
     Input('width', 0.3, single=True, help='on a beam, the horizontal side; on a column, the one facing sideways',
             visible_if=lambda e: e.get('section') == "rectangular"),
     Input('height', 0.5, single=True, help='on a beam, the vertical side; on a column, the one towards the vertical axis (the centre of a tower)',
             visible_if=lambda e: e.get('section') == "rectangular"),
     Input('profile', None, help='a curve drawn around the origin, in plan: x towards the width of the member, '
                                   'y towards its height (an I, an L, your own shape)',
             visible_if=lambda e: e.get('section') == 'profile'),
     Input('rotation', 0.0, single=True, help='rotates the section around the member, in degrees',
             visible_if=lambda e: e.get('section', 'round') != 'round'),
     Input('caps', False, single=True, help='closes both ends of each member: the result is a closed body (a '
                                               'mesh); its curvature, when analysed, is approximate')),
    'surface',
    lambda curves, section, radius, sides, width, height, profile, rotation, caps, name: meshes.pipe(
        curves, radius, sides, name, section, width, height, profile, rotation, bool(caps)),
    'A member along each curve, each on its own (not fused): with a round section (hoops, railings, cables), a '
    'rectangular one (beams, mullions) or that of a curve you draw (an I, an L).',
    ("Pipe", "Tubería", "Baranda", "Pasamanos", "Cable", "Aro", "Viga", "Sección rectangular", "Perfil",
     "Sección", "Montante", "Barra", "Sweep perfil", "Perfil I", "Perfil L"),
))

_register(NodeType(
    'Ribs', 'Surfaces',
    (Input('shape', help='a surface (the front of a wall, a ceiling), a mesh or a volume'),
     Input('count', 30, single=True, help='how many ribs, spread from end to end'),
     Input('weight', 0.02, help='the board thickness'),
     Input('cuts', "x", single=True, options=meshes.AXES_RIBS,
             help='x: vertical ribs along X · y: along Y · z: horizontal slices'),
     Input('back', 0.0, help='where the back wall is: the plane each rib is closed against (y = …; x = … '
                                   'when cutting along y)')),
    'ribs',
    lambda shape, count, weight, cuts, back, name: meshes.ribs(shape, count, weight, cuts, back,
                                                                             name),
    'Cuts a shape into parallel boards, closed against the wall: a rib wall, a slatted ceiling, a sliced bench.',
    ("Ribs", "Lamas", "Fins", "Rebanar", "Contour ribs", "Waffle", "Tableros", "Láminas", "Slices", "Muro de costillas"),
))

_register(NodeType(
    'Offset curve', 'Curves',
    (Input('curve', help='one or more curves, each one flat (in a plane)'),
     Input('distance', 0.01, help='a closed curve: outwards (negative: inwards) · an open curve: to its left, '
                                  'looking along it from above its plane (negative: to its right)'),
     Input('corners', 'round', single=True, options=fab.CORNERS,
           help='for closed curves: round or sharp corners')),
    'curve',
    lambda curve, distance, corners, name: fab.offset_curve(curve, distance, corners, name),
    'Moves each curve aside in its own plane, keeping the same distance all along: the outline of a wall from its '
    'axis, a border around a plan, the second side of a piece to be cut.',
    ("Offset", "Offset curve", "Equidistante", "Desfase", "Paralela", "Contorno exterior", "Borde"),
))

_register(NodeType(
    'Text', 'Curves',
    (Input('at', help='where the labels go: points, or the panels, bodies or curves to label (each one at its '
                      'centre, on the face that looks at the reader)'),
     Input('text', "{n}", single=True,
           help='{n}: the number of each element, as the 3D view numbers it · {floor}, {row}…: its number in that '
                'level · {value}: the number given in «value» · A; B; C: one text for each element, in order · '
                '|: a new line · anything else, as it is: P{floor}-{n}'),
     Input('value', None, help='numbers to write with {value}: one for each element (an area, a length)'),
     Input('decimals', 2, single=True, help='of {value}', visible_if=lambda e: e.get('value') is not None),
     Input('height', 0.2, single=True, help='of the letters (the capitals)'),
     Input('plane', 'plan', single=True, options=labels.LABEL_PLANES,
           help='how the labels are read: in plan (from above), in elevation (from the front, -y), in side elevation '
                '(from +x) · on the face: lying on each panel, read from where it looks'),
     Input('lettering', 'plain', single=True, options=labels.LABEL_LETTERS,
           help='plain or rounded: single-stroke capitals (one line per stroke, to engrave) · font: an installed '
                'font, its outlines (closed curves), with lower case and accents'),
     Input('font', "", single=True, visible_if=lambda e: e.get('lettering') == 'font', suggest=_font_families,
           help='the name of an installed font; empty: the usual one of the system'),
     Input('align', 'centre', single=True, options=labels.LABEL_ALIGNS,
           help='with several lines (split by «|»): each one at the centre, on the left or on the right')),
    'text',
    lambda at, text, value, decimals, height, plane, lettering, font, align, name: labels.text(
        at, text, value, decimals, height, plane, lettering, font, align, name),
    'Writes a label on each element: the number of a panel, the letter of a brick type, an area. In “text”, what '
    'goes in braces changes on each element: “P{n}” writes P0, P1, P2…; “F{floor}-{bay}” writes F0-0, F0-1…; '
    '“{value} m2”, the number given in “value”; “N; S; E; O”, one text for each element; “|” starts a new line. '
    'In single-stroke letters (lines, to engrave) or in an installed font (outlines). They are seen in 3D, take a '
    'colour, and go out in the drawings and the cutting files.',
    ("Label", "Labels", "Tag", "Etiqueta", "Etiquetas", "Rótulo", "Rotular", "Letras", "Texto", "Text tag",
     "Numerar", "Número de panel", "Cotas de texto", "Annotate", "Anotar", "Leyenda"),
))

_register(NodeType(
    'Contour', 'Curves',
    (Input('geometry', help='a surface, a volume or a mesh'),
     Input('distance', 1.0, single=True, help='how often to cut'),
     Input('direction', (0.0, 0.0, 1.0), help='which way the cuts advance; upwards: horizontal'),
     Input('start', None, single=True, help='the height of the first cut; empty: the lowest point'),
     Input('level', "cut", single=True, help='name of the new level')),
    'curves',
    lambda geometry, distance, direction, start, level, name: meshes.level_curves(
        geometry, distance, direction, start, level, name),
    'Cuts a surface or a volume with parallel planes at a set spacing: rings, slabs, contour lines.',
    ("Contour", "Contorno", "Cortes", "Rebanar", "Secciones horizontales", "Topografía", "Losas"),
))

_register(NodeType(
    'Boolean', 'Surfaces',
    (Input('a', help='a closed body (or several)'), Input('b', help='another closed body (or several)'),
     Input('operation', 'difference', single=True, options=meshes.OPERATIONS_BOOLEANS,
             help='union: all together · difference: a minus b · intersection: what they have in common')),
    'body',
    lambda a, b, operation, name: meshes.boolean(a, b, operation, name),
    'Unites, subtracts or intersects closed bodies: a wall minus its openings, two volumes in a single skin.',
    ("Boolean", "Solid Difference", "Solid Union", "Solid Intersection", "Restar", "Vaciar", "Vano", "Unir sólidos",
     "Intersecar", "Diferencia", "Unión", "Hueco"),
))

_register(NodeType(
    'Sphere', 'Shapes',
    (Input('centre', (0.0, 0.0, 0.0)), Input('radius', 1.0)),
    'sphere',
    lambda centre, radius, name: meshes.sphere(centre, radius, name),
    'A sphere.',
    ("Sphere", "Bola", "Cúpula"),
))

_register(NodeType(
    'Scale by axis', 'Transform',
    (Input('geometry'), Input('x', 1.0, help='more than 1 stretches, less than 1 shrinks'), Input('y', 1.0),
     Input('z', 1.0), Input('centre', None, help='empty: each element about its own centre')),
    'geometry',
    lambda geometry, x, y, z, centre, name: geo.scale_by_axes(geometry, x, y, z, centre, name),
    'Scales differently in x, y and z: a floor that stretches in width, a slab that gets shorter.',
    ("Scale NU", "Escalar no uniforme", "Estirar", "Deformar"),
))

_register(NodeType(
    'Twist', 'Transform',
    (Input('geometry'), Input('degrees', 90.0, help='how much the top turns (the bottom does not)'),
     Input('centre', (0.0, 0.0, 0.0), help='where the vertical axis passes'),
     Input('from', 0.0, single=True, help='at what height the twist starts: from 0 (bottom) to 1 (top)')),
    'geometry',
    lambda geometry, degrees, centre, from_, name: geo.twist(geometry, degrees, centre, from_, name),
    'Twists the geometry around a vertical axis: the bottom does not turn, the top turns by the given amount.',
    ("Twist", "Retorcer", "Torsión", "Helicoidal", "Torre que gira"),
))

_register(NodeType(
    'Place', 'Transform',
    (Input('geometry'), Input('at'), Input('rotation', 0.0),
     Input('axis', "vertical", single=True, options=("vertical", "x", "y"))),
    'geometry',
    lambda geometry, at, rotation, axis, name: geo.place(geometry, at, rotation, axis, name),
    'Rotates the geometry about its origin and takes it to each point.',
    ("Ubicar", "Instanciar", "Repetir en puntos"),
))

_register(NodeType(
    'Thicken', 'Transform',
    (Input('rectangle'), Input('thickness', help='positive outwards, negative inwards')),
    'block',
    lambda rectangle, thickness, name: geo.thicken(rectangle, thickness, name),
    'Gives thickness to each rectangle (a block) or to a surface.',
    ("Offset Surface", "Extruir", "Dar espesor", "Losa"),
))

_register(NodeType(
    'Frame', 'Transform',
    (Input('panel'), Input('opening', 0.5, help='the opening relative to the panel: from 0 (closed) to 1'),
     Input('thickness', 0.0, single=True, help='0: a flat frame'),
     Input('width', None, help='frame width in metres (instead of opening): the same all round'),
     Input('output', 'frame', single=True, help='frame, or opening (the rectangle inside: the glass)',
             options=('frame', 'hole'))),
    'frame',
    lambda panel, opening, thickness, width, output, name: geo.frame(panel, opening, thickness, width, output, name),
    'A frame with an opening in each panel (by proportion or by frame width), or the opening alone.',
    ("Panel Frame", "Abertura", "Ventana en panel", "Celosía"),
))


def suggestions(node, input_: Input) -> list[str]:
    """The names an input offers in its list: those of a function without arguments (the installed fonts), or of one
    that looks at the node (the results of the group connected to a Group result)."""
    import inspect
    try:
        takes_node = bool(inspect.signature(input_.suggest).parameters)
    except (TypeError, ValueError):
        takes_node = False
    return list(input_.suggest(node) if takes_node else input_.suggest())


def _results_of(node) -> list[str]:
    origin = node.inputs.get("group")
    value = getattr(origin, "_value", None) if origin is not None else None
    return list(getattr(value, "results", None) or {})


def _group_result(group, gives, name=None) -> Data:
    results = getattr(group, "results", None)
    if not results:
        raise ShapeError(tr('“group” must be the card of a group with several results.'))
    if gives not in results:
        raise ShapeError(tr('The group gives: {options} (not “{gives}”).').format(
            options=", ".join(f"«{r}»" for r in results), gives=gives))
    import copy
    result = copy.copy(results[gives])
    result.name = name
    return result


_register(NodeType(
    'Group result', 'Groups',
    (Input('group', help='the card of a group with several results'),
     Input('gives', '', single=True, suggest=_results_of,
           help='which result of the group: the name of one of its Group output nodes')),
    'value',
    _group_result,
    'Another result of a group that gives several: the card of the group gives the first one; each Group result '
    'takes one more, without computing the group again.',
    ("Group results", "Output of group", "Salida de grupo"),
))
