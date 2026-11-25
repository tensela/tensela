"""What the code of a Code node can use: points with their arithmetic, lines, polylines, meshes, the usual
mathematics (angles in degrees, like the Formula) and random numbers that repeat. Nothing else exists for that code:
no files, no network, no other programs (code_check.py reads the code before it runs).

Also here: how the inputs of the node reach the code (numbers, lists, points) and how what the code leaves in
`result` becomes the data of the node.
"""
from __future__ import annotations

import math
import random as _random

import numpy as np

from .data import Data, ShapeError
from .language import tr


#: The most elements the code of a node may give.
MAX_RESULT = 2_000_000


class Vec:
    """A point or a vector: x, y, z, with its arithmetic (a + b, a - b, a * 2, a / 2, -a)."""

    __slots__ = ("x", "y", "z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __repr__(self) -> str:
        return f"point({self.x:g}, {self.y:g}, {self.z:g})"

    def __add__(self, other):
        o = _vec(other)
        return Vec(self.x + o.x, self.y + o.y, self.z + o.z)

    __radd__ = __add__

    def __sub__(self, other):
        o = _vec(other)
        return Vec(self.x - o.x, self.y - o.y, self.z - o.z)

    def __rsub__(self, other):
        return _vec(other) - self

    def __mul__(self, k):
        return Vec(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__

    def __truediv__(self, k):
        return Vec(self.x / k, self.y / k, self.z / k)

    def __neg__(self):
        return Vec(-self.x, -self.y, -self.z)

    def __eq__(self, other):
        return isinstance(other, Vec) and tuple(self) == tuple(other)

    def __hash__(self):
        return hash(tuple(self))

    def length(self) -> float:
        """How long the vector is."""
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def unit(self) -> Vec:
        """The same direction, with length 1."""
        n = self.length()
        return Vec(self.x / n, self.y / n, self.z / n) if n else Vec()

    def dot(self, other) -> float:
        o = _vec(other)
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, other) -> Vec:
        o = _vec(other)
        return Vec(self.y * o.z - self.z * o.y, self.z * o.x - self.x * o.z, self.x * o.y - self.y * o.x)

    def distance(self, other) -> float:
        """How far it is from another point."""
        return (self - _vec(other)).length()

    def towards(self, other, share: float) -> Vec:
        """The point at that share of the way to another one (0.5: the middle)."""
        o = _vec(other)
        return self + (o - self) * share

    def rotated(self, degrees: float, about=None, axis=None) -> Vec:
        """Turned so many degrees about a point (the origin, if none) around the vertical (or another axis)."""
        c = _vec(about) if about is not None else Vec()
        k = (_vec(axis) if axis is not None else Vec(0, 0, 1)).unit()
        v = self - c
        cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        turned = v * cos + k.cross(v) * sin + k * (k.dot(v) * (1 - cos))      # Rodrigues
        return c + turned


def _vec(value) -> Vec:
    if isinstance(value, Vec):
        return value
    try:
        x, y, *rest = value
        return Vec(x, y, rest[0] if rest else 0.0)
    except (TypeError, ValueError):
        raise ShapeError(tr('A point was expected (point(x, y, z)), and it is {value}.').format(value=repr(value))) from None


class Polyline:
    """Points joined by straight lines, open or closed."""

    __slots__ = ("points", "closed")

    def __init__(self, points, closed=False):
        self.points = [_vec(p) for p in points]
        self.closed = bool(closed)
        if len(self.points) < 2:
            raise ShapeError(tr('A line or a polyline needs two points or more.'))

    def __iter__(self):
        return iter(self.points)

    def __len__(self):
        return len(self.points)

    def __repr__(self) -> str:
        return f"polyline({len(self.points)} points)"


class Mesh:
    """A mesh: its vertices and its faces (each face, the numbers of its vertices in order)."""

    __slots__ = ("points", "faces")

    def __init__(self, points, faces):
        self.points = [_vec(p) for p in points]
        self.faces = [tuple(int(i) for i in f) for f in faces]
        if not self.faces or any(len(f) < 3 for f in self.faces):
            raise ShapeError(tr('A mesh needs faces of three vertices or more.'))
        if any(not 0 <= i < len(self.points) for f in self.faces for i in f):
            raise ShapeError(tr('A face of the mesh uses a vertex that does not exist (there are {n} vertices, '
                                'numbered from 0).').format(n=len(self.points)))

    def __repr__(self) -> str:
        return f"mesh({len(self.points)} points, {len(self.faces)} faces)"


def _degrees_in(f):
    return lambda x: f(math.radians(x))


def _degrees_out(f):
    return lambda *x: math.degrees(f(*x))


def names(seed: int = 1) -> dict:
    """Everything the code can call, by its name. The random numbers start from the same seed at each run, so the
    same code gives the same result."""
    rng = _random.Random(seed)
    return {
        # geometry
        "point": Vec, "vector": Vec, "line": lambda a, b: Polyline([a, b]),
        "polyline": lambda points, closed=False: Polyline(points, closed), "mesh": Mesh,
        # mathematics, with the angles in degrees (like the Formula)
        "sin": _degrees_in(math.sin), "cos": _degrees_in(math.cos), "tan": _degrees_in(math.tan),
        "asin": _degrees_out(math.asin), "acos": _degrees_out(math.acos), "atan": _degrees_out(math.atan),
        "atan2": _degrees_out(math.atan2), "sqrt": math.sqrt, "exp": math.exp, "log": math.log,
        "floor": math.floor, "ceil": math.ceil, "pi": math.pi, "phi": (1 + 5 ** 0.5) / 2,
        "radians": math.radians, "degrees": math.degrees,
        # random numbers that repeat
        "random": rng.random, "uniform": rng.uniform, "randint": rng.randint, "choice": rng.choice,
        "shuffle": rng.shuffle, "seed": rng.seed,
        # the usual of Python
        "abs": abs, "min": min, "max": max, "sum": sum, "len": len, "range": range, "enumerate": enumerate,
        "zip": zip, "round": round, "sorted": sorted, "reversed": reversed, "list": list, "tuple": tuple,
        "dict": dict, "set": set, "int": int, "float": float, "bool": bool, "str": str, "any": any, "all": all,
        "map": map, "filter": filter, "divmod": divmod, "pow": pow, "isinstance": isinstance,
        "print": lambda *values, **options: None,              # accepted (pasted code often has it), shows nothing
        "True": True, "False": False, "None": None,
        "Exception": Exception, "ValueError": ValueError, "ZeroDivisionError": ZeroDivisionError,
        "IndexError": IndexError, "KeyError": KeyError, "TypeError": TypeError,
    }


#: The names the code can use without defining them (code_check.py reads them from here).
ALLOWED_NAMES = frozenset(names()) | {"a", "b", "c", "d", "e", "f", "g", "h", "result"}

#: The attributes the code can use (x.append, p.length…): the public ones of the plain values of Python and of the
#: points, polylines and meshes. Formatting texts with «format» is left out: it can reach the inside of any object.
ALLOWED_ATTRIBUTES = frozenset(
    n for kind in (list, dict, set, tuple, str, int, float, Vec, Polyline, Mesh) for n in dir(kind)
    if not n.startswith("_")) - {"format", "format_map"} | {"x", "y", "z", "points", "faces", "closed"}


# --- From the inputs of the node to the code ---------------------------------------------------------------

def to_python(data):
    """An input as the code sees it: a number, a point, a list of points (a curve, the corners of a panel), a mesh;
    with levels, lists inside lists."""
    if data is None:
        return None
    if not isinstance(data, Data):
        return data
    kind, k = data.kind, len(data.levels)
    values = np.asarray(data.values)

    def element(v):
        if kind is None:
            x = v.item() if v.ndim == 0 else v.tolist()
            return x
        if v.ndim == 1:                                        # a point or a vector
            return Vec(*v[:3])
        if kind.faces is not None and not kind.polygon and kind.name == "mesh":
            return Mesh([Vec(*p) for p in v], kind.faces)
        points = [Vec(*p) for p in v.reshape(-1, 3)]
        if kind.polygon:                                       # without the padding (the last vertex, repeated)
            while len(points) > 3 and points[-1] == points[-2]:
                points.pop()
        return points

    def walk(v, depth, mask):
        if depth == k:
            return element(v)
        return [walk(v[i], depth + 1, mask[i]) for i in range(v.shape[0]) if np.any(mask[i])]

    return walk(values, 0, data.mask) if k else element(values)


# --- From what the code leaves in «result» to the data of the node -----------------------------------------

def _shape_of(leaf):
    """(what it is, its points as an array, extra) of one thing the code gives."""
    if isinstance(leaf, bool) or isinstance(leaf, (int, float)):
        return "number", np.float64(leaf), None
    if isinstance(leaf, Vec):
        return "point", np.array(tuple(leaf)), None
    if isinstance(leaf, Polyline):
        return ("closed curve" if leaf.closed else "curve"), np.array([tuple(p) for p in leaf.points]), None
    if isinstance(leaf, Mesh):
        return "mesh", np.array([tuple(p) for p in leaf.points]), tuple(leaf.faces)
    raise ShapeError(tr('The code gives {value}, which is neither a number nor geometry: build points with point(x, '
                        'y, z), lines with line(a, b) or polyline(points), meshes with mesh(points, faces).').format(
        value=repr(leaf)[:60]))


def to_data(result, levels: str = "element", name: str | None = None) -> Data:
    """What the code left in `result`, as data: a number, a point, a line, a mesh, or lists of them (also lists
    inside lists: one level each, named by `levels`, «row; column»)."""
    from .geometry import CLOSED_CURVE, CURVE, POINT
    from .meshes import kind_mesh
    if result is None:
        raise ShapeError(tr('The code gives nothing: leave what it computes in «result» (result = …).'))

    depth = 0
    probe = result
    while isinstance(probe, (list, tuple)):                    # how deep the lists go, by their first elements
        if not probe:
            raise ShapeError(tr('The code gives an empty list: there is nothing to show.'))
        depth, probe = depth + 1, probe[0]
    leaves, kinds = [], set()

    def collect(x, d):
        if d == depth:
            if len(leaves) >= MAX_RESULT:
                raise ShapeError(tr('The code gives more than {maximum} elements: too many to show.').format(
                    maximum=MAX_RESULT))
            what, array, extra = _shape_of(x)
            kinds.add(what)
            leaves.append((array, extra))
            return array
        if not isinstance(x, (list, tuple)):
            raise ShapeError(tr('The lists of «result» are uneven: some elements are lists and others are not.'))
        if not x:
            raise ShapeError(tr('The code gives an empty list: there is nothing to show.'))
        return [collect(y, d + 1) for y in x]

    nested = collect(result, 0)
    if len(kinds) > 1:
        raise ShapeError(tr('The code gives different things in the same list ({kinds}): a list holds one kind of '
                            'thing.').format(kinds=", ".join(tr(k) for k in sorted(kinds))))
    what = kinds.pop()
    names_ = [n.strip() for n in str(levels or "element").split(";") if n.strip()] or ["element"]
    while len(names_) < depth:
        names_.append(f"{names_[0]} {len(names_) + 1}")
    names_ = names_[:depth]
    if what == "mesh":
        if depth:
            if len(leaves) > 1:
                raise ShapeError(tr('The code gives several meshes: give a single one (all the points and all the '
                                    'faces together in one mesh(points, faces)).'))
            nested = leaves[0][0]
        array, faces = leaves[0]
        return Data(array, (), name, kind=kind_mesh(list(faces)))
    kind = {"number": None, "point": POINT, "curve": CURVE, "closed curve": CLOSED_CURVE}[what]
    if what in ("curve", "closed curve") and depth:
        most = max(len(a) for a, _ in leaves)                  # shorter polylines: their last point, repeated

        def pad(x, d):
            if d == depth:
                return np.vstack([x, np.repeat(x[-1:], most - len(x), axis=0)]) if len(x) < most else x
            return [pad(y, d + 1) for y in x]
        nested = pad(nested, 0)
    if not depth:
        return Data(nested, (), name, kind=kind)
    return _with_kind(Data.from_lists(nested, names_, name), kind)


def _with_kind(data: Data, kind) -> Data:
    data.kind = kind
    return data
