"""Data without trees: tables with named levels (see DATOS.md).

A `Data` is a numpy array whose first axes are named levels (`row`, `column`, `floor`…). The remaining axes describe
each element: a number has no extra axes; a point has one of size 3.

    centres = Data(array_12x20x3, levels=("row", "column"), name="centres")
    centres.shape  ->  "row 12 × column 20 = 240"

Levels of variable size (R4): a level can have a different size depending on other levels (more panels at the
bottom than at the top of a tower). It is kept as `variables[level]`: a `Data` with the count of elements in each
case. The values are padded up to the maximum size repeating the last valid element, and `mask` says which cells
really exist.

Holes (R6, D6): filtering does not remove elements, it leaves them empty in their place. `holes` marks which; the
grid still reads the same.

Numbering: the elements of a level are numbered from 0 (the ground floor), unless the level starts at another
number: with 2 basements, `starts={"floor": -2}` numbers the floors from -2 onwards.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import NamedTuple

import numpy as np

from .language import tr


class ShapeError(ValueError):
    """The data do not fit. The message is meant for the user."""


# Above this, a computation would freeze the window (and the memory): it is almost
# always a mistake (a crossing of levels that was not wanted, a number too
# many). It is reported before computing (P4 of DATOS.md).
MAX_ELEMENTS = 5_000_000


def _require_size_(sizes: dict[str, int], what: str) -> None:
    total = int(np.prod(list(sizes.values()), dtype=float)) if sizes else 1
    if total > MAX_ELEMENTS:
        detail = " × ".join(f"{n} {_number(t)}" for n, t in sizes.items())
        raise ShapeError(
            tr('{what} would have {total} elements ({detail}): too many to calculate at once (the maximum is '
               '{maximum}). Are levels crossing that should be paired (another level name), or is there an extra '
               'number?').format(
                what=what, total=_number(total), detail=detail, maximum=_number(MAX_ELEMENTS))
        )


class Data:
    """A table of elements with zero or more named levels."""

    def __init__(self, values, levels: Iterable[str] = (), name: str | None = None,
                 variables: dict[str, Data] | None = None, starts: dict[str, int] | None = None,
                 kind=None, holes=None):
        self.values = np.asarray(values)
        self.levels = tuple(levels)
        self.name = name
        self.variables = dict(variables or {})
        self.starts = {n: int(i) for n, i in (starts or {}).items() if i != 0}
        # What each element is (point, rectangle, box…). The geometry nodes set it.
        self.kind = kind

        if len(set(self.levels)) != len(self.levels):
            raise ShapeError(tr('“{name}” has repeated levels: {options}.').format(
                                   name=self._name(), options=', '.join((tr(n) for n in self.levels))))
        if len(self.levels) > self.values.ndim:
            raise ShapeError(
                tr('“{name}” has {how_many} levels but its values only have {ndim} dimensions.').format(
                    name=self._name(), how_many=len(self.levels), ndim=self.values.ndim)
            )
        for level, tally in self.variables.items():
            if level not in self.levels or level in tally.levels or not set(tally.levels) <= set(self.levels):
                raise ShapeError(tr('The count of “{level}” in “{name}” does not match its levels.').format(
                                       level=tr(level), name=self._name()))
        for level in self.starts:
            _require_level(self, level)
        if self.variables:
            self.values = _pad(self.values, self.levels, self.variables)
        # The empty elements (R6): True where there is nothing. None if there is none.
        self.holes = None
        if holes is not None:
            h = np.broadcast_to(np.asarray(holes, dtype=bool), self.values.shape[: len(self.levels)])
            if h.any():
                self.holes = h.copy()

    def derived(self, values, name: str | None = None, kind=None, new_levels: tuple[str, ...] = ()) -> Data:
        """A data with the same levels (plus `new_levels` at the end), numbering, variable levels and holes as this one,
        but other values.

        It is what almost every geometry node does: one result per element.
        """
        holes = None
        if self.holes is not None:
            holes = self.holes.reshape(self.holes.shape + (1,) * len(new_levels))
        return Data(values, self.levels + tuple(new_levels), name, self.variables, self.starts, kind, holes)

    @classmethod
    def value(cls, value, name: str | None = None) -> Data:
        """A single value, without levels (for example, the attractor point)."""
        return cls(value, (), name)

    @classmethod
    def from_lists(cls, lists, levels: Iterable[str], name: str | None = None,
                  starts: dict[str, int] | None = None) -> Data:
        """Builds a data from nested lists, which may have different lengths.

            Data.from_lists([[1, 2, 3], [4, 5]], ("floor", "panel"))  ->  floor 2 × panel 2…3 = 5
        """
        levels = tuple(levels)
        starts = starts or {}
        k = len(levels)
        maximum = [0] * k
        leaves = []

        def measure(x, d, where):
            if d == k:
                leaves.append(np.asarray(x))
                return
            if len(x) == 0:
                place = tr(' at {where}').format(where=where) if where else ""
                raise ShapeError(tr('“{value}” has an empty list of “{levels}”{place}.').format(
                                       value=name or tr('data'), levels=tr(levels[d]), place=place))
            maximum[d] = max(maximum[d], len(x))
            for i, y in enumerate(x):
                here = f"«{levels[d]}» {i + starts.get(levels[d], 0)}"
                measure(y, d + 1, f"{where}, {here}" if where else here)

        measure(lists, 0, "")
        kind = np.result_type(*leaves)
        values = np.zeros(maximum + list(leaves[0].shape), dtype=kind)
        counts = [np.zeros(maximum[:d], dtype=int) for d in range(k)]

        def fill(x, d, pos):
            if d == k:
                values[pos] = x
                return
            counts[d][pos] = len(x)
            for i, y in enumerate(x):
                fill(y, d + 1, pos + (i,))

        fill(lists, 0, ())

        variables: dict[str, Data] = {}
        for d in range(k):
            tally = cls(counts[d], levels[:d], name, variables, _only(starts, levels[:d]))
            if not _constant(tally):
                variables[levels[d]] = tally
        return cls(values, levels, name, variables, starts)

    @property
    def sizes(self) -> dict[str, int]:
        """Size of each level (the maximum, if the level is variable)."""
        return dict(zip(self.levels, self.values.shape))

    @property
    def structure(self) -> np.ndarray:
        """Which cells are part of the table (counts the variable levels, not the holes)."""
        return _mask(self.levels, self.sizes, self.variables)

    @property
    def mask(self) -> np.ndarray:
        """Which cells really have an element: neither padding nor hole."""
        m = self.structure
        return m & ~self.holes if self.holes is not None else m

    @property
    def empty(self) -> int:
        """How many elements are empty (R6)."""
        return 0 if self.holes is None else int((self.structure & self.holes).sum())

    @property
    def count(self) -> int:
        """Number of elements."""
        return int(self.mask.sum())

    @property
    def shape_element(self) -> tuple[int, ...]:
        return self.values.shape[len(self.levels) :]

    @property
    def shape(self) -> str:
        """The shape in words (R8).

            row 12 × column 20 = 240
            floor 30 × panel 12…20 = 486
            floor 13 (from -2 to 10)
        """
        if not self.levels:
            return tr('· (one value)')
        parts = []
        for level, size_ in self.sizes.items():
            start = self.starts.get(level, 0)
            name = tr(level)          # only when showing it: «rib 44» is «costilla 44» in Spanish (the data does not change)
            if level in self.variables:
                counts = _valid(self.variables[level])
                part = f"{name} {counts.min()}…{counts.max()}"
                if start:
                    part += tr(' (from {start})').format(start=start)
            else:
                part = f"{name} {size_}"
                if start:
                    part += tr(' (from {start} to {end})').format(start=start, end=start + size_ - 1)
            parts.append(part)
        text = " × ".join(parts)
        empty = tr(' ({empty} empty)').format(empty=_number(self.empty)) if self.empty else ""
        if len(self.levels) == 1 and not self.variables and not empty:
            return text
        return f"{text} = {_number(self.count)}{empty}"

    def list_(self):
        """The elements as nested lists, without the padding of the variable levels.

        An empty element (R6) appears as None, in its place.
        """
        k = len(self.levels)
        holes = self.holes if self.holes is not None else np.zeros(self.structure.shape, dtype=bool)

        def traverse(v, m, h, d):
            if d == k:
                return None if h else v.tolist()
            return [traverse(v[i], m[i], h[i], d + 1) for i in range(v.shape[0]) if np.any(m[i])]

        return traverse(self.values, self.structure, holes, 0)

    def _tally(self, level: str) -> Data:
        """How many elements `level` has, as a data (one value if the level is fixed)."""
        if level in self.variables:
            c = self.variables[level]
            return Data(c.values, c.levels, self.name, c.variables, c.starts)
        return Data.value(self.sizes[level], self.name)

    def _name(self, default: str = 'data') -> str:
        return self.name or tr(default)

    def __repr__(self) -> str:
        name = f"«{self.name}» " if self.name else ""
        kind = f"{self.kind.name}: " if self.kind is not None else ""
        return f"<Data {name}{kind}{self.shape}>"


# --- R1 and R2: the single combination rule -------------------------------

class Alignment(NamedTuple):
    """Result of `align`: the common shape and the values of each input in it."""

    levels: tuple[str, ...]
    values: list[np.ndarray]
    variables: dict[str, Data]
    starts: dict[str, int]
    holes: np.ndarray | None  # empty in the result if it is empty in some input


def align(*data_items: Data) -> Alignment:
    """The single combination rule (R1).

    The result has all the levels of the inputs, in order of appearance. The levels with the same name pair up; the
    others combine with everything. If a shared level does not have the same size in all the inputs (or, if it is
    variable, in each case) or does not start numbering at the same number, a clear error (R2).

    Returns the levels of the result, the values of each input extended to those levels (without copying memory), the
    variable levels and the numbering.
    """
    levels: list[str] = []
    sizes: dict[str, int] = {}
    first: dict[str, Data] = {}
    variables: dict[str, Data] = {}
    starts: dict[str, int] = {}
    for i, data in enumerate(data_items, start=1):
        if data.name is None:
            data = Data(data.values, data.levels, tr('input {i}').format(i=i), data.variables, data.starts)
        for level, size_ in data.sizes.items():
            if level not in sizes:
                levels.append(level)
                sizes[level] = size_
                first[level] = data
                starts[level] = data.starts.get(level, 0)
            else:
                _compare_starts(level, first[level], data)
                _compare_sizes(level, first[level], data)
            if level in data.variables and level not in variables:
                variables[level] = data.variables[level]

    _require_size_({n: sizes[n] for n in levels}, tr('The result'))
    aligned = [_extend(d.values, d.levels, levels, sizes) for d in data_items]
    holes = None
    for d in data_items:
        if d.holes is not None:
            h = _extend(d.holes, d.levels, levels, sizes)
            holes = h if holes is None else (holes | h)
    return Alignment(tuple(levels), aligned, variables, starts, holes)


def apply(function: Callable[..., np.ndarray], *data_items: Data, name: str | None = None,
            kind=None) -> Data:
    """Applies `function` element by element following the rule R1.

    `function` receives the arrays already aligned and must return an array whose first axes are the levels of the
    result.
    """
    a = align(*data_items)
    return Data(function(*a.values), a.levels, name, a.variables, a.starts, kind, a.holes)


def _compare_starts(level: str, a: Data, b: Data) -> None:
    ia, ib = a.starts.get(level, 0), b.starts.get(level, 0)
    if ia != ib:
        raise ShapeError(tr('“{level}” starts at {start_a} in “{a}” and at {start_b} in “{b}”.').format(
                               level=tr(level), start_a=ia, a=a.name, start_b=ib, b=b.name))


def _compare_sizes(level: str, a: Data, b: Data) -> None:
    al = align(a._tally(level), b._tally(level))
    xa, xb = al.values
    different = (xa != xb) & _mask(al.levels, dict(zip(al.levels, xa.shape)), al.variables)
    if not different.any():
        return
    pos = tuple(np.argwhere(different)[0])
    where = ", ".join(f"«{tr(n)}» {p + al.starts.get(n, 0)}" for n, p in zip(al.levels, pos))
    where = tr(' at {where}').format(where=where) if where else ""
    raise ShapeError(
        tr('The sizes of “{level}” do not match{where}: {size_a} in “{a}”, {size_b} in “{b}”.').format(
            level=tr(level), where=where, size_a=xa[pos], a=a.name, size_b=xb[pos], b=b.name)
    )


# --- R3: reduce by name -------------------------------------------------

_OPERATIONS = ('maximum', 'minimum', 'sum', 'average', 'tally')


def reduce(data: Data, operation: str, along: str | Iterable[str] | None = None,
            name: str | None = None) -> Data:
    """Removes one or several levels, by their name (R3).

    Without `along`, it reduces all the levels and returns a single value. `operation`: maximum, minimum, sum, average
    or tally. In the variable levels only the elements that exist count.
    """
    if operation not in _OPERATIONS:
        raise ShapeError(tr("I don't know the operation “{operation}”. Options: {options}.").format(
                               operation=operation, options=', '.join(tr(o) for o in _OPERATIONS)))
    if along is None:
        remove = list(data.levels)
    elif isinstance(along, (list, tuple)):
        remove = [str(x) for x in along]
    else:
        remove = [str(along)]                       # a level name written as a number («0»)
    for level in remove:
        _require_level(data, level)
    # Of a geometry the elements are counted; of some points, also their average (their centre).
    if operation != 'tally' and not (operation == 'average' and getattr(data.kind, "name", None) == "point"):
        require_numbers(data, "data")

    axes = tuple(data.levels.index(n) for n in remove)
    remain = tuple(n for n in data.levels if n not in remove)

    mask = data.mask
    count = mask.sum(axis=axes)
    if operation == 'tally':
        values = count
    else:
        m = mask.reshape(mask.shape + (1,) * len(data.shape_element))
        v = data.values
        if operation == 'maximum':
            values = np.where(m, v, -np.inf).max(axis=axes)
        elif operation == 'minimum':
            values = np.where(m, v, np.inf).min(axis=axes)
        else:
            values = np.where(m, v, 0).sum(axis=axes)
            if operation == 'average':
                values = values / np.maximum(count, 1).reshape(count.shape + (1,) * len(data.shape_element))

    # The variable levels that remain: their count becomes the largest among the removed levels.
    variables = {}
    for level, tally in data.variables.items():
        if level in remove:
            continue
        in_tally = [n for n in remove if n in tally.levels]
        if in_tally:
            r = reduce(tally, 'maximum', along=in_tally)
            tally = Data(r.values.astype(int), r.levels, r.name, r.variables, r.starts)
        if not _constant(tally):
            variables[level] = tally
    holes = (count == 0) if data.holes is not None else None
    # The average of some points is a point (the centre of a cell, of a group of panels).
    kind = data.kind if operation == 'average' and getattr(data.kind, "name", None) == "point" else None
    return Data(values, remain, name, variables, _only(data.starts, remain), kind=kind, holes=holes)


# --- R5: operate along a level -----------------------------------------

def position(data: Data, level: str, name: str | None = None) -> Data:
    """The number of each element in `level`.

    It starts at 0 (the ground floor is floor 0), or at the start of the level if it has one (with 2 basements, the floors
    go from -2 onwards).
    """
    _require_level(data, level)
    axis = data.levels.index(level)
    shape = data.values.shape[: len(data.levels)]
    start = data.starts.get(level, 0)
    indices = (np.arange(shape[axis]) + start).reshape(_to_length(axis, len(shape)))
    return data.derived(np.broadcast_to(indices, shape).copy(), name)


def pairs(data: Data, level: str, closed: bool = False, name: str | None = None) -> Data:
    """Each element together with the next one in `level`: (current, next).

    Open, there is one pair fewer than elements (beams between columns). Closed, the last one joins the first (sides of
    an outline).
    """
    _require_level(data, level)
    _require_independent(data, level, tr('Making pairs'))
    tally = data._tally(level)
    if _valid(tally).min() < 2:
        raise ShapeError(tr('Making pairs needs at least 2 elements in “{level}” of “{name}”.').format(
                               level=tr(level), name=data._name()))

    axis = data.levels.index(level)
    n = data.sizes[level]
    c = _extend(tally.values, tally.levels, data.levels, data.sizes)
    next_ = np.arange(n).reshape(_to_length(axis, len(data.levels))) + 1
    next_ = np.where(next_ >= c, 0, next_) if closed else np.minimum(next_, n - 1)
    holes = None
    if data.holes is not None:  # a pair with an empty element stays empty
        holes = data.holes | np.take_along_axis(data.holes, np.broadcast_to(next_, data.holes.shape), axis=axis)
    next_ = next_.reshape(next_.shape + (1,) * len(data.shape_element))
    together = np.stack(
        [data.values, np.take_along_axis(data.values, next_, axis=axis)],
        axis=len(data.levels),
    )

    variables = dict(data.variables)
    if not closed:
        together = np.take(together, np.arange(n - 1), axis=axis)
        if holes is not None:
            holes = np.take(holes, np.arange(n - 1), axis=axis)
        if level in variables:
            variables[level] = Data(tally.values - 1, tally.levels, tally.name, tally.variables, tally.starts)
    return Data(together, data.levels, name, variables, data.starts, holes=holes)


def accumulate(data: Data, level: str, name: str | None = None) -> Data:
    """Running total along `level` (the height of each floor, a grandstand)."""
    _require_level(data, level)
    _require_independent(data, level, tr('Accumulating'))
    axis = data.levels.index(level)
    return data.derived(np.cumsum(data.values, axis=axis), name)


# --- Crear niveles ---------------------------------------------------------------

def integer(x) -> int:
    """A count (of points, of rows, a seed…) as an integer: the nearest one, like Grasshopper.

    So a count that comes from a Formula (`a / 3`) or from a slider with decimals works all the same.
    """
    if isinstance(x, Data):
        x = x.values
    x = np.asarray(x, dtype=float)
    if x.size != 1:
        raise ShapeError(tr('A count must be a single number, not a list.'))
    return int(np.floor(float(x.reshape(-1)[0]) + 0.5))


def series(count: int, start: float = 0, step: float = 1, level: str = "element",
          name: str | None = None, mode: str = 'with step', to: float = 1.0) -> Data:
    """A series of numbers that creates a level: `series(25, level="floor")` → floor 25.

    «with step» mode: from `start`, in steps of `step`. «between two» mode: `count` numbers spread from `start` to `to`,
    both included (the *Range* of a domain): `series(5, 0, mode="between two", to=1)` → 0; 0,25; 0,5; 0,75; 1.

    If it starts at an integer and goes one by one, the numbering of the level matches its values (D8):
    `series(13, start=-2, level="floor")` gives the floors from -2 to 10.
    """
    count = integer(count)
    if count < 1:
        raise ShapeError(tr('The count of a series must be 1 or more (it is {count}).').format(
                               count=count))
    _require_size_({level: count}, tr('The series'))
    if mode == 'between two':
        values = np.linspace(float(start), float(to), count)
        return Data(values, (level,), name)
    if mode != 'with step':
        raise ShapeError(tr('The series mode must be “with step” or “between two”.')) 
    values = start + step * np.arange(count)
    starts = {level: int(start)} if float(start).is_integer() and step == 1 else None
    return Data(values, (level,), name, starts=starts)


# --- Compare, filter (R6) and pick ----------------------------------------------

COMPARISONS = {
    'less': np.less,
    'less or equal': np.less_equal,
    'greater': np.greater,
    'greater or equal': np.greater_equal,
    'equal': np.isclose,
    'different': lambda a, b: ~np.isclose(a, b),
}


def on_random(data: Data | None = None, along: str | None = None, minimum: float = 0.0, maximum: float = 1.0,
            seed: int = 1, name: str | None = None, mode: str = 'per element', count=10,
            level: str = "element", integers: bool = False) -> Data:
    """Random numbers between `minimum` and `maximum`. The same seed, the same numbers.

    - «per element» mode: one per element of `data`, along its levels up to `along` (included; without it, the first
      one): a cell, a row…
    - «count» mode: `count` loose numbers, with their level (`level`): «20 numbers between 1 and 5».

    With `integers`, whole numbers from `minimum` to `maximum` (both included): to pick at random.
    """
    rng = np.random.default_rng(abs(integer(seed)))
    minimum, maximum = sorted((float(minimum), float(maximum)))      # written the other way round: the same interval

    def draw(shape):
        if integers:
            return rng.integers(integer(minimum), integer(maximum) + 1, shape)
        return rng.uniform(minimum, maximum, shape)

    if mode == 'count':
        n = integer(count)
        if n < 1:
            raise ShapeError(tr('The amount of random numbers must be 1 or more.'))
        _require_size_({level: n}, tr('The random numbers'))
        return Data(draw(n), (level,), name)
    if mode != 'per element':
        raise ShapeError(tr('The mode must be “per element” or “amount”.'))
    if data is None:
        raise ShapeError(tr('The “data” is missing: one random number per element (or use the “amount” mode).'))
    if not data.levels:
        return Data.value(draw(()), name)
    along = along or data.levels[0]
    _require_level(data, along)
    levels = data.levels[: data.levels.index(along) + 1]
    sizes = tuple(data.sizes[n] for n in levels)
    values = draw(sizes)
    variables = {n: c for n, c in data.variables.items() if n in levels and set(c.levels) <= set(levels)}
    holes = data.holes if data.holes is not None and levels == data.levels else None
    return Data(values, levels, name, variables, _only(data.starts, levels), holes=holes)


def compare(a: Data, b: Data, operation: str = 'less', name: str | None = None) -> Data:
    """Yes or no for each element: `a` is less (greater, equal…) than `b`."""
    if operation not in COMPARISONS:
        raise ShapeError(tr("I don't know the comparison “{operation}”. Options: {options}.").format(
                               operation=operation, options=', '.join(tr(o) for o in COMPARISONS)))
    a, b = _as_data(a), _as_data(b)
    for x in (a, b):
        if x.kind is not None:                            # points, curves…: there is no «less» between them
            raise ShapeError(tr('Compare works with numbers (a distance, a height, an area…), and “{name}” is '
                                'a geometry ({what}).').format(name=x._name(), what=tr(x.kind.name)))
    return apply(COMPARISONS[operation], a, b, name=name)


def filter_(data: Data, condition: Data, reverse: bool = False, name: str | None = None) -> Data:
    """Leaves empty (R6) the elements that do not meet the condition; nothing moves from its place.

    With `reverse`, it keeps those that do not meet it. The condition combines with the data by the single rule (R1): a
    yes/no per facade holds for all its panels.
    """
    a = align(data, _as_data(condition))
    values, meets = a.values
    if meets.ndim != len(a.levels):
        raise ShapeError(tr('The condition to filter “{name}” must be a yes or a no for each element.').format(
                               name=data._name()))
    meets = meets.astype(bool)
    if reverse:
        meets = ~meets
    holes = ~meets if a.holes is None else (~meets | a.holes)
    return Data(np.array(values), a.levels, name, a.variables, a.starts, data.kind, holes)


#: How it filters: by a condition (yes/no per element), by a repeating pattern, or one in every N.
MODES_FILTER = ('condition', 'pattern', 'every')
_SI = ("sí", "si", "s", "1", "x", "true", "yes", "y", "verdadero")
_NO = ("no", "n", "0", "-", "·", ".", "false", "falso")


def _single_level(data: Data, level: str | None, what: str) -> str:
    """The level asked for, or the only one the data has."""
    if level:
        _require_level(data, level)
        return level
    if len(data.levels) == 1:
        return data.levels[0]
    raise ShapeError(tr('Say which level {what} in “{name}” (its levels: {options}).').format(
                           what=tr(what), name=data._name(), options=", ".join((tr(n) for n in data.levels)) or tr('none')))


def read_pattern(pattern) -> list[bool]:
    """«yes; no» · «1 0 0» · «x..» · [True, False]: the repeating pattern."""
    import re
    if isinstance(pattern, Data):
        return [bool(x) for x in np.asarray(pattern.values).ravel()]
    if isinstance(pattern, (list, tuple)):
        return [bool(x) for x in pattern]
    if isinstance(pattern, bool):
        return [pattern]
    text = str(pattern).strip().lower()
    pieces = [t for t in re.split(r"[;,\s]+", text) if t]
    if len(pieces) == 1 and len(pieces[0]) > 1 and set(pieces[0]) <= set("x.-·10"):   # «x..», «100»
        pieces = list(pieces[0])
    pattern_ = []
    for t in pieces:
        if t in _SI:
            pattern_.append(True)
        elif t in _NO:
            pattern_.append(False)
        else:
            raise ShapeError(tr('The pattern is written with yes and no (or 1 and 0): “yes; no; no” keeps one '
                                  'in three. I do not understand “{t}”.').format(t=t))
    if not pattern_:
        raise ShapeError(tr('The pattern is empty: type, for example, “yes; no”.'))
    return pattern_


def filter_by_position(data: Data, level: str | None, pass_: np.ndarray, remove: bool = True,
                         reverse: bool = False, name: str | None = None) -> Data:
    """Filters the elements of `level` by `pass_` (a yes/no per position). With `remove`, those that do not pass are
    removed (the level gets shorter and is numbered again); if not, they stay empty in their place."""
    level = _single_level(data, level, "to filter")
    if level in data.variables or any(level in c.levels for c in data.variables.values()):
        raise ShapeError(tr('Filtering “{level}” by position is not possible yet: “{level}” changes size in '
                              '“{name}”.').format(level=tr(level), name=data._name()))
    pass_ = np.asarray(pass_, dtype=bool)
    if reverse:
        pass_ = ~pass_
    axis = data.levels.index(level)
    if remove:
        indices = np.flatnonzero(pass_)
        if not len(indices):
            raise ShapeError(tr('No element of “{level}” is left after filtering.').format(level=tr(level)))
        holes = None if data.holes is None else np.take(data.holes, indices, axis=axis)
        starts = {n: i for n, i in data.starts.items() if n != level}
        return Data(np.take(data.values, indices, axis=axis), data.levels, name, data.variables, starts,
                    data.kind, holes)
    shape = data.values.shape[:len(data.levels)]
    empty = np.broadcast_to((~pass_).reshape((-1,) + (1,) * (len(shape) - axis - 1)), shape[axis:])
    empty = np.broadcast_to(empty, shape)
    holes = empty if data.holes is None else (empty | data.holes)
    return Data(data.values, data.levels, name, data.variables, data.starts, data.kind, np.array(holes))


def filter_mode(data: Data, mode: str = 'condition', condition=None, level: str | None = None, pattern="yes; no",
                 every=2, from_=0, remove: bool = True, reverse: bool = False, name: str | None = None) -> Data:
    """Filter in its three modes:

    - «condition»: a yes/no per element (Compare…); those that do not hold stay empty in their place.
    - «pattern»: «yes; no» repeats along the level (one yes, one no…).
    - «every»: one in every `every`, starting at `from_` (from 0).
    """
    if mode not in MODES_FILTER:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MODES_FILTER)))
    if mode == 'condition':
        if condition is None:
            raise ShapeError(tr('Filtering by condition needs a “condition”: a yes/no per element (for example, '
                                  'from Compare).'))
        return filter_(data, condition, reverse, name)
    n_level = _single_level(data, level, "to filter")
    size_ = data.sizes[n_level]
    if mode == 'pattern':
        p = read_pattern(pattern)
        pass_ = np.array([p[i % len(p)] for i in range(size_)])
    else:
        step = integer(every)
        if step < 1:
            raise ShapeError(tr('“every” must be 1 or more (1: all; 2: one yes, one no).'))
        start = integer(from_) % step
        pass_ = (np.arange(size_) % step) == start
    return filter_by_position(data, n_level, pass_, remove, reverse, name)


#: How two conditions join (yes/no per element).
COMBINATIONS = {
    'and': np.logical_and,                                  # both
    'or': np.logical_or,                                   # either (or both)
    'not': lambda a, b: np.logical_not(a),                 # the opposite of «a» (b is not used)
    'only one': np.logical_xor,                           # one or the other, but not both
}


def _yes_no(x, what: str) -> Data:
    """A condition: a yes/no data (numbers count as yes if they are not 0)."""
    if isinstance(x, Data) and x.kind is not None:
        raise ShapeError(tr('“{what}” should be a condition (a yes/no per element, from Compare…), and it '
                              'receives a geometry.').format(what=what))
    if isinstance(x, str):
        x = x.strip().lower() in _SI
    d = _as_data(x)
    return Data(np.asarray(d.values).astype(bool), d.levels, d.name, d.variables, d.starts, None, d.holes)


def combine_conditions(a, b=None, operation: str = "and", name: str | None = None) -> Data:
    """Joins two conditions: «and» (both), «or» (either), «not» (the opposite of a), «only one» (one or the other)."""
    if operation not in COMBINATIONS:
        raise ShapeError(tr("I don't know “{operation}”. I can do: {options}.").format(
                               operation=operation, options=", ".join(tr(o) for o in COMBINATIONS)))
    if a is None:
        raise ShapeError(tr('Condition “a” is missing: a yes/no per element (from Compare, from Inside…).'))
    if operation == "not":
        return apply(np.logical_not, _yes_no(a, "a"), name=name)
    if b is None:
        raise ShapeError(tr('“{operation}” needs two conditions: connect “b” too.').format(
                               operation=tr(operation)))
    return apply(COMBINATIONS[operation], _yes_no(a, "a"), _yes_no(b, "b"), name=name)


def choose(condition, yes, no, name: str | None = None) -> Data:
    """For each element: if the condition is yes, the «yes» one; if not, the «no» one (like the Formula's if(), but
    also with geometry: an open or a closed panel, one column or another).

    With a single condition (a Yes or no), it picks one of the two whole: one variant of the project or another."""
    if condition is None:
        raise ShapeError(tr('The “condition” is missing: a yes/no per element (from Compare, from Inside…), or '
                              'a single Yes or no to choose a whole variant.'))
    if yes is None or no is None:
        raise ShapeError(tr('Choose needs both options: what goes where it is “yes” and what goes where it is “no”.'))
    c = _yes_no(condition, tr('condition'))
    a, b = _as_data(yes), _as_data(no)
    if not c.levels:                                     # a single condition: a whole option
        chosen = a if bool(c.values) else b
        return Data(chosen.values, chosen.levels, name, chosen.variables, chosen.starts, chosen.kind,
                    chosen.holes)
    if a.kind != b.kind or a.shape_element != b.shape_element:
        raise ShapeError(tr('To choose element by element, “yes” and “no” must be of the same kind (two '
                              'numbers, two points, two panels of the same shape). If they differ (a circle and a '
                              'square), use two Filters: one with “those that do” and one with “those that '
                              "don't”."))
    element = len(a.shape_element)

    def picked(cc, x, y):
        cc = np.asarray(cc).reshape(np.shape(cc) + (1,) * element)
        return np.where(cc, x, y)
    return apply(picked, c, a, b, name=name, kind=a.kind)


def repeat(data: Data, level: str | None = None, length=5, name: str | None = None) -> Data:
    """Repeats the elements of a level, in order, until it has `length` (*Repeat Data*): 2; 6; 1 up to 5 →
    2; 6; 1; 2; 6. A smaller length shortens the list. It helps a short list go with a long one."""
    level = _single_level(data, level, "to repeat")
    if level in data.variables or any(level in c.levels for c in data.variables.values()):
        raise ShapeError(tr('Repeating “{level}” is not possible yet: “{level}” changes size in “{name}”.').format(
                               level=tr(level), name=data._name()))
    n = integer(length)
    if n < 1:
        raise ShapeError(tr('The length to repeat must be 1 or more.'))
    _require_size_({**data.sizes, level: n}, tr('The repetition'))
    indices = np.arange(n) % data.sizes[level]
    axis = data.levels.index(level)
    holes = None if data.holes is None else np.take(data.holes, indices, axis=axis)
    starts = {k: v for k, v in data.starts.items() if k != level}
    return Data(np.take(data.values, indices, axis=axis), data.levels, name, data.variables, starts, data.kind,
                holes)


#: How a level is split into groups: so many at a time, or in so many parts.
SPLIT_MODES = ('groups of', 'in parts')


def split(data: Data, level: str | None = None, mode: str = 'groups of', count=2, new_level: str = "group",
           name: str | None = None) -> Data:
    """Splits the elements of a level into groups (a new level, before that of the elements):

    - «groups of»: `count` at a time (12 points in groups of 4 → group 3 × point 4);
    - «in parts»: in `count` equal groups (except the last one, if they do not come out even).

    If they do not come out even, the last group keeps holes (empty ones) at the end.
    """
    if mode not in SPLIT_MODES:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in SPLIT_MODES)))
    level = _single_level(data, level, "to split")
    if level in data.variables or any(level in c.levels for c in data.variables.values()):
        raise ShapeError(tr('Splitting “{level}” is not possible yet: “{level}” changes size in “{name}”.').format(
                               level=tr(level), name=data._name()))
    if not new_level or new_level in data.levels:
        raise ShapeError(tr('The new level needs a name that “{name}” does not use (it has: {options}).').format(
                               name=data._name(), options=", ".join((tr(n) for n in data.levels))))
    n = integer(count)
    if n < 1:
        raise ShapeError(tr('The amount to split must be 1 or more.'))
    m = data.sizes[level]
    by_group = n if mode == 'groups of' else -(-m // n)
    groups = -(-m // by_group)
    axis = data.levels.index(level)
    shape = data.values.shape[:len(data.levels)]
    padding = groups * by_group - m
    indices = np.minimum(np.arange(groups * by_group), m - 1)          # the padding repeats the last one…
    values = np.take(data.values, indices, axis=axis)
    empty = np.arange(groups * by_group) >= m                         # …and stays empty
    holes = None
    if padding or data.holes is not None:
        new_shape = shape[:axis] + (groups * by_group,) + shape[axis + 1:]
        holes = np.broadcast_to(empty.reshape((-1,) + (1,) * (len(shape) - axis - 1)), new_shape[axis:])
        holes = np.broadcast_to(holes, new_shape)
        if data.holes is not None:
            holes = holes | np.take(np.broadcast_to(data.holes, shape), indices, axis=axis)
        holes = np.array(holes).reshape(shape[:axis] + (groups, by_group) + shape[axis + 1:])
    values = values.reshape(shape[:axis] + (groups, by_group) + values.shape[axis + 1:])
    levels = data.levels[:axis] + (new_level, level) + data.levels[axis + 1:]
    starts = {k: v for k, v in data.starts.items() if k != level}
    return Data(values, levels, name, data.variables, starts, data.kind, holes)


def join_levels(data: Data, first: str | None = None, second: str | None = None, new_level: str | None = None,
                name: str | None = None) -> Data:
    """Joins two levels into one, in order: all of `second` for the first of `first`, then for the next…
    (triangle 4 × vertex 3 → vertex 12: the three vertices of triangle 0, then those of triangle 1…).

    Without saying which, the first and the last level. The joined level is called `new_level`, or like `second`.
    It is undone by Split in groups of the size of `second`. Empty places (holes, as Split leaves them) are dropped
    when each remaining element keeps the same number."""
    if len(data.levels) < 2:
        raise ShapeError(tr('“{name}” has a single level ({levels}): there is nothing to join.').format(
            name=data._name(), levels=", ".join(tr(n) for n in data.levels) or tr('none')))
    first = first or data.levels[0]
    _require_level(data, first)
    second = second or next(n for n in reversed(data.levels) if n != first)
    _require_level(data, second)
    if first == second:
        raise ShapeError(tr('Choose two different levels to join (both are “{level}”).').format(level=tr(first)))
    for level in (first, second):
        if level in data.variables or any(level in c.levels for c in data.variables.values()):
            raise ShapeError(tr('Joining “{level}” is not possible yet: “{level}” changes size in “{name}”.').format(
                level=tr(level), name=data._name()))
    new_level = new_level or second
    rest = [n for n in data.levels if n not in (first, second)]
    if new_level in rest:
        raise ShapeError(tr('The joined level needs a name that “{name}” does not use (it has: {options}).').format(
            name=data._name(), options=", ".join(tr(n) for n in rest)))

    # The two levels side by side, where `first` was: the rest keep their order.
    order = [n for n in data.levels if n != second]
    order.insert(order.index(first) + 1, second)
    axes = [data.levels.index(n) for n in order]
    count = len(data.levels)
    element = list(range(count, data.values.ndim))
    values = np.transpose(data.values, axes + element)
    merged_at = order.index(first)
    shape = values.shape
    values = values.reshape(shape[:merged_at] + (shape[merged_at] * shape[merged_at + 1],) + shape[merged_at + 2:])
    levels = tuple(order[:merged_at]) + (new_level,) + tuple(order[merged_at + 2:])
    starts = {k: v for k, v in data.starts.items() if k not in (first, second)}

    holes = None
    if data.holes is not None:
        h = np.transpose(np.broadcast_to(data.holes, data.values.shape[:count]), axes)
        h = h.reshape(h.shape[:merged_at] + (-1,) + h.shape[merged_at + 2:])
        kept = np.sum(~h, axis=merged_at)
        if kept.size and np.all(kept == kept.flat[0]):                    # the same in each: the empty ones go
            moved = np.moveaxis(values, merged_at, -1 - (values.ndim - len(levels)))
            keep = np.moveaxis(~h, merged_at, -1)
            values = moved[keep].reshape(keep.shape[:-1] + (int(kept.flat[0]),) + values.shape[len(levels):])
            values = np.moveaxis(values, len(levels) - 1, merged_at)
        else:
            holes = h
    return Data(values, levels, name, data.variables, starts, data.kind, holes)


_FIRST = ("primero", "primera", "first")
_LAST = ("último", "última", "ultimo", "ultima", "last")


def _positions(position, level: str) -> tuple[list, bool]:
    """What is asked to pick, as a list of user numbers (or «first»/«last»), and whether it was a single one (then the
    level is removed). It accepts: 4 · last · -1 · «1; 5; 3» · «2-5» (from 2 to 5) · «0; 3-5; -1» · a data with numbers
    (a Series)."""
    import re
    if isinstance(position, Data):
        return [int(round(float(x))) for x in np.asarray(position.values).ravel()], False
    if isinstance(position, (list, tuple)):
        return [int(round(float(x))) for x in position], False
    if isinstance(position, (int, float, np.integer, np.floating)) and not isinstance(position, bool):
        return [int(round(float(position)))], True
    text = str(position).strip()
    parts = [p.strip() for p in re.split(r"[;,]", text) if p.strip()]
    requested = []
    for part in parts:
        word = r"[+\-−]?\d+|primer[oa]|últim[oa]|ultim[oa]|first|last"
        range_ = re.fullmatch(rf"({word})\s*(?:\.\.|\s-\s|-|–|\sa\s|\sto\s)\s*({word})", part.lower())
        if range_:
            requested.append(("rango",) + tuple(int(x.replace("−", "-")) if re.fullmatch(r"[+\-−]?\d+", x) else x
                                                for x in range_.groups()))
        elif part.lower() in _FIRST + _LAST:
            requested.append(part.lower())
        elif re.fullmatch(r"[+\-−]?\d+", part):
            requested.append(int(part.replace("−", "-")))
        else:
            raise ShapeError(tr('To pick in “{level}” a number, “first” or “last” is needed, or several (“1; 5; '
                                  '3”, “2-5”) (got “{position}”.)').format(level=tr(level), position=position))
    if not requested:
        raise ShapeError(tr('To pick in “{level}” a number, “first” or “last” is needed, or several (“1; 5; 3”, '
                              '“2-5”) (got “{position}”.)').format(level=tr(level), position=position))
    one = len(parts) == 1 and len(requested) == 1 and not isinstance(requested[0], tuple)
    return requested, one


def pick(data: Data, level: str | None, position, name: str | None = None) -> Data:
    """Takes elements of `level` by their number (D8: the first is 0): row 4, the last floor, points 1, 5 and 3,
    from 2 to 5…

    - a single one (4 · «first» · «last» · -1): removes that level;
    - several («1; 5; 3» · «2-5» · a Series): the level stays, with those elements in that order (numbered again from 0).
      So two Picks with the same level pair one to one.

    The negative ones count from the end: -1 is the last, -2 the one before. Without `level`, the only one it has.
    """
    level = _single_level(data, level, "to pick")
    _require_level(data, level)
    if level in data.variables or any(level in c.levels for c in data.variables.values()):
        raise ShapeError(tr('Picking in “{level}” is not possible yet: “{level}” changes size in “{name}”.').format(
                               level=tr(level), name=data._name()))
    size_, start = data.sizes[level], data.starts.get(level, 0)
    requested, one = _positions(position, level)

    def number(x):                              # an end of a range, as a user number
        if x in _FIRST:
            return start
        if x in _LAST:
            return start + size_ - 1
        return x if x >= 0 else start + size_ + x

    open_ = []
    for p in requested:                           # the ranges («2-5», «4-last», «0--2»), number by number
        if isinstance(p, tuple):
            a, b = number(p[1]), number(p[2])
            open_.extend(range(a, b + 1) if a <= b else range(a, b - 1, -1))
        else:
            open_.append(p)
    requested = open_
    indices = []
    for p in requested:
        if p in _FIRST:
            i = 0
        elif p in _LAST:
            i = size_ - 1
        elif p < 0:
            i = size_ + p                           # -1: the last one
        else:
            i = p - start
        if not 0 <= i < size_:
            raise ShapeError(
                tr('“{level}” {position} does not exist in “{name}”: it goes from {start} to {value}.').format(
                    level=tr(level), position=p, name=data._name(), start=start, value=start + size_ - 1)
            )
        indices.append(i)
    axis = data.levels.index(level)
    if one:
        i = indices[0]
        remain = tuple(n for n in data.levels if n != level)
        holes = None if data.holes is None else np.take(data.holes, i, axis=axis)
        return Data(np.take(data.values, i, axis=axis), remain, name, data.variables,
                    _only(data.starts, remain), data.kind, holes)
    indices = np.array(indices, dtype=int)
    holes = None if data.holes is None else np.take(data.holes, indices, axis=axis)
    starts = {n: i for n, i in data.starts.items() if n != level}           # the chosen ones, from 0
    return Data(np.take(data.values, indices, axis=axis), data.levels, name, data.variables, starts,
                data.kind, holes)


#: How a level is reordered: reversed, shifted N places, or from smallest to largest by a value.
MODES_REORDER = ('invert', 'shift', 'sort')


def _key_aligned(key: Data, data: Data, shape: tuple) -> np.ndarray:
    """The values of `key` spread over the levels of `data` (by their name), with the shape `shape`."""
    extras = [n for n in key.levels if n not in data.levels]
    if extras:
        raise ShapeError(tr('To sort, “{key}” cannot have levels that “{name}” does not have ({extras}).').format(
                               key=key._name(), name=data._name(), extras=", ".join(extras)))
    v = np.asarray(key.values, dtype=float)
    if v.shape[len(key.levels):]:
        raise ShapeError(tr('Sorting needs one number per element (a distance, a height…), and “{key}” is a '
                              'geometry.').format(key=key._name()))
    order = [key.levels.index(n) for n in data.levels if n in key.levels]
    v = np.transpose(v, order) if order else v
    shape_k = tuple(shape[k] if n in key.levels else 1 for k, n in enumerate(data.levels))
    try:
        return np.broadcast_to(v.reshape(shape_k), shape)
    except ValueError:
        raise ShapeError(tr('The sizes do not match to sort “{name}” by “{key}”.').format(
                               name=data._name(), key=key._name())) from None


def reorder(data: Data, level: str | None = None, mode: str = 'invert', count=1, wrap: bool = True,
              key: Data | None = None, name: str | None = None) -> Data:
    """Changes the order of the elements of a level (the level and its elements are the same):

    - «invert»: the other way round. Without a level, on a curve, it reverses its direction (it starts at the end).
    - «shift»: moves the elements `count` places towards the start (1 becomes 0). With `wrap`, those that leave at the
      start enter at the end (as in a ring); if not, they are lost and the level gets shorter. Negative, the other way.
    - «sort»: from smallest to largest by `key` (a number per element: a distance, a height, a coordinate); without a key,
      by their own values if they are numbers.

    The elements are numbered again from 0.
    """
    if mode not in MODES_REORDER:
        raise ShapeError(tr('The mode must be one of: {options}.').format(options=", ".join(tr(m) for m in MODES_REORDER)))
    if not level:
        if mode == 'invert' and data.kind is not None and data.kind.curve:     # the direction of each curve
            return Data(np.flip(data.values, axis=-2), data.levels, name, data.variables, data.starts, data.kind,
                        data.holes)
        if len(data.levels) == 1:
            level = data.levels[0]
        else:
            raise ShapeError(tr('Say which level of “{name}” to reorder (its levels: {options}).').format(
                                   name=data._name(), options=", ".join((tr(n) for n in data.levels)) or tr('none')))
    _require_level(data, level)
    if level in data.variables or any(level in c.levels for c in data.variables.values()):
        raise ShapeError(tr('Reordering “{level}” is not possible yet: “{level}” changes size in “{name}”.').format(
                               level=tr(level), name=data._name()))
    axis = data.levels.index(level)
    shape = data.values.shape[:len(data.levels)]
    starts = {n: i for n, i in data.starts.items() if n != level}
    extra = data.values.ndim - len(data.levels)              # the axes of each element (x, y, z; vertices)

    def take(indices: np.ndarray) -> Data:
        """The elements in the order of `indices` (with the shape of the levels, or 1D along the level)."""
        if indices.ndim == 1:
            values = np.take(data.values, indices, axis=axis)
            holes = None if data.holes is None else np.take(data.holes, indices, axis=axis)
        else:
            values = np.take_along_axis(data.values, indices.reshape(indices.shape + (1,) * extra), axis=axis)
            holes = None if data.holes is None else np.take_along_axis(
                np.broadcast_to(data.holes, shape), indices, axis=axis)
        return Data(values, data.levels, name, data.variables, starts, data.kind, holes)

    size_ = shape[axis]
    if mode == 'invert':
        return take(np.arange(size_)[::-1])
    if mode == 'shift':
        n = integer(count)
        if wrap:
            return take((np.arange(size_) + n) % size_)
        if abs(n) >= size_:
            raise ShapeError(tr('Shifting {n} places without wrapping leaves “{level}” empty (it has {size}).').format(
                                   n=n, level=tr(level), size=size_))
        return take(np.arange(n, size_) if n >= 0 else np.arange(0, size_ + n))
    if key is None:
        if data.kind is not None:
            raise ShapeError(tr('Sorting a geometry needs a “key”: one number per element (its distance to a '
                                  'point, its height with Coordinate…).'))
        key = data
    k = _key_aligned(key if isinstance(key, Data) else Data.value(np.asarray(key, dtype=float)), data, shape)
    return take(np.argsort(k, axis=axis, kind="stable"))


# --- Auxiliares --------------------------------------------------------------

def _as_data(x) -> Data:
    """A loose number (or a list) becomes a data of a single value."""
    return x if isinstance(x, Data) else Data.value(np.asarray(x))


def require_numbers(data, role: str) -> None:
    """Where numbers go (a Formula, a Function, a Summarise…), a point or a geometry does not serve as it is."""
    if isinstance(data, Data) and data.kind is not None:
        raise ShapeError(tr('«{role}» gets «{what}» ({name}), and numbers go here. Get a number out of it with '
                              'Coordinate (its x, y or z), Distance, Area, Length…').format(
                                  role=role, what=tr(data.kind.name), name=data._name()))


def _require_level(data: Data, level: str) -> None:
    if level not in data.levels:
        available = ", ".join(tr(n) for n in data.levels) or tr('none')
        raise ShapeError(tr('“{level}” is not a level of “{name}” (its levels: {available}).').format(
                               level=tr(level), name=data._name(), available=available))


def _require_independent(data: Data, level: str, action: str) -> None:
    """Going along `level` when another level changes size with it is not solved yet."""
    for other, tally in data.variables.items():
        if level in tally.levels:
            raise ShapeError(
                tr('{action} along “{level}” is not possible in “{name}” yet: the size of “{other}” changes with '
                   '“{level}”.').format(action=action, level=tr(level), name=data._name(), other=other)
            )


def _only(starts: dict[str, int], levels: Iterable[str]) -> dict[str, int]:
    """The numbering starts that correspond to `levels`."""
    return {n: starts[n] for n in levels if n in starts}


def _to_length(axis: int, dimensions: int) -> list[int]:
    """Shape to place a vector along `axis` among `dimensions` axes."""
    return [-1 if i == axis else 1 for i in range(dimensions)]


def _extend(values: np.ndarray, origin: tuple[str, ...], target: Iterable[str],
              sizes: dict[str, int]) -> np.ndarray:
    """Takes values with levels `origin` to the levels `target` (which contain them)."""
    target = list(target)
    own = len(origin)
    order = sorted(range(own), key=lambda axis: target.index(origin[axis]))
    v = np.transpose(values, order + list(range(own, values.ndim)))
    measures = dict(zip(origin, values.shape))
    element = list(values.shape[own:])
    v = v.reshape([measures.get(n, 1) for n in target] + element)
    return np.broadcast_to(v, [sizes[n] for n in target] + element)


def _mask(levels: tuple[str, ...], sizes: dict[str, int], variables: dict[str, Data]) -> np.ndarray:
    shape = [sizes[n] for n in levels]
    mask = np.ones(shape, dtype=bool)
    for level, tally in variables.items():
        axis = levels.index(level)
        c = _extend(tally.values, tally.levels, levels, sizes)
        mask &= np.arange(sizes[level]).reshape(_to_length(axis, len(levels))) < c
    return mask


def stack(items: list[Data], level: str, name: str | None = None) -> Data:
    """Several data of the same kind, one after another along a new first level (the steps of a repetition).

    They may have different sizes: a level that changes from one to the next becomes a variable level (step 0 has 1
    segment, step 1 has 4…), and curves or polygons with different numbers of points are padded repeating the last
    one. What cannot go together (different kinds, meshes with different faces, other levels) is said."""
    first = items[0]
    if any(d.levels != first.levels for d in items):
        raise ShapeError(tr('The steps do not have the same levels ({a} and {b}): they cannot be kept together.').format(
            a=", ".join(tr(n) for n in first.levels) or tr('none'),
            b=next(", ".join(tr(n) for n in d.levels) or tr('none') for d in items if d.levels != first.levels)))
    if level in first.levels:
        raise ShapeError(tr('The steps already have a level called “{level}”: give the level of the steps another '
                            'name.').format(level=tr(level)))
    kinds = {d.kind for d in items}
    kind = first.kind
    k = len(first.levels)
    shapes = {d.values.shape[k:] for d in items}
    if len(kinds) > 1 or len(shapes) > 1:
        # Curves (or polygons) with more or fewer points: the same thing, padded. Anything else does not stack.
        strings = all(d.kind is not None and (d.kind.curve or d.kind.polygon) for d in items)
        same = len({(d.kind.name, d.kind.closed) for d in items}) == 1 if strings else False
        if not same or any(len(sh) != 2 for sh in shapes):
            raise ShapeError(tr('The steps are not the same kind of thing (or are meshes with different faces): they '
                                'cannot be kept together. Keep the last step.'))
        points = max(sh[0] for sh in shapes)
        if first.kind.polygon:
            from .polygons import kind_polygon
            kind = kind_polygon(points)
        padded = []
        for d in items:
            v = d.values
            if v.shape[k] < points:
                last = np.repeat(v[..., -1:, :], points - v.shape[k], axis=-2)
                v = np.concatenate([v, last], axis=-2)
            padded.append(v)
    else:
        padded = [d.values for d in items]
    element = padded[0].shape[k:]
    sizes = [tuple(d.values.shape[:k]) for d in items]
    simple = all(not d.variables and d.holes is None and not d.starts for d in items)
    if len(set(sizes)) == 1 and (simple or all(_same_structure(d, first) for d in items)):
        holes = None if first.holes is None else np.stack([d.holes for d in items])
        variables = {n: c for n, c in first.variables.items()}
        _require_size_({level: len(items), **first.sizes}, tr('The steps'))
        return Data(np.stack(padded), (level,) + first.levels, name, variables, first.starts, kind, holes)
    if not simple:
        raise ShapeError(tr('The steps have lists of different lengths inside, or empty elements: they cannot be kept '
                            'together. Keep the last step.'))
    largest = tuple(max(sh[i] for sh in sizes) for i in range(k))
    _require_size_({level: len(items), **dict(zip(first.levels, largest))}, tr('The steps'))
    values = np.zeros((len(items),) + largest + element, dtype=np.result_type(*padded))
    for i, v in enumerate(padded):
        values[(i,) + tuple(slice(0, n) for n in v.shape[:k])] = v
    variables = {n: Data(np.array([sh[i] for sh in sizes]), (level,))
                 for i, n in enumerate(first.levels) if len({sh[i] for sh in sizes}) > 1}
    return Data(values, (level,) + first.levels, name, variables, kind=kind)


def _same_structure(a: Data, b: Data) -> bool:
    """The same variable levels (with the same counts), numbering and holes."""
    if set(a.variables) != set(b.variables) or a.starts != b.starts or (a.holes is None) != (b.holes is None):
        return False
    if a.holes is not None and not np.array_equal(a.holes, b.holes):
        return False
    return all(a.variables[n].levels == b.variables[n].levels
               and np.array_equal(a.variables[n].values, b.variables[n].values) for n in a.variables)


def _pad(values: np.ndarray, levels: tuple[str, ...], variables: dict[str, Data]) -> np.ndarray:
    """Fills the cells that do not exist repeating the last valid element.

    So any computation on the padding gives reasonable values (without divisions by zero or garbage) and the mask only
    has to hide them.
    """
    sizes = dict(zip(levels, values.shape))
    extra = (1,) * (values.ndim - len(levels))
    for level, tally in variables.items():
        if _valid(tally).min() < 1:
            raise ShapeError(tr('“{level}” cannot have 0 elements.').format(level=tr(level)))
        axis = levels.index(level)
        c = _extend(tally.values, tally.levels, levels, sizes)
        indices = np.minimum(np.arange(sizes[level]).reshape(_to_length(axis, len(levels))), c - 1)
        values = np.take_along_axis(values, indices.reshape(indices.shape + extra), axis=axis)
    return values


def _valid(data: Data) -> np.ndarray:
    """The values that really exist, in a flat list."""
    return data.values[data.mask]


def _constant(data: Data) -> bool:
    valid = _valid(data)
    return bool(np.all(valid == valid.flat[0]))


def _number(n: int) -> str:
    """240 → '240'; 80000 → '80 000' (thousands separator with a space)."""
    return f"{n:,}".replace(",", " ")
