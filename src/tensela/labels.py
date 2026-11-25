"""Texts in the view: a label on each element (the number of a panel, the letter of a brick, an area), written with
the single-stroke lettering of the engraved numbers. They are curves: they are seen in 3D, take a colour, and go out
in the drawings (DXF, SVG) and the cutting files like any other line.

What each label says (`text`):
- `{n}`: the number of the element, as the 3D view numbers it (with several levels, «2·5»: ring 2, point 5).
- `{floor}`, `{row}`…: its number in that level only, by the level's name.
- `{value}`: a number given in `value` (one per element: an area, a length), with `decimals`.
- Several texts separated by «;» («A; B; C»): one for each element, in order, starting again when they run out.
- «|» starts a new line («F{floor}-{bay} | {value} m2»); `align` lines them up (centre, left, right).
- Anything else is written as it is («P{floor}-{panel}», «N»).

Where it goes: on the points; at the middle of a curve; at the centre of a surface or a body, on its face that looks
at the reader (the top in plan, the front in elevation). `plane`: how it is read (plan, elevation, side elevation),
or on the face of each panel (on the face).
"""
from __future__ import annotations

import re

import numpy as np

from .data import Data, ShapeError
from .geometry import CURVE, PLANES, POINT, VECTOR
from .language import comma, tr

#: How each label is laid: the three planes of a drawing, or on the face of each element.
LABEL_PLANES = ('plan', 'elevation', 'side elevation', 'on the face')
#: The letter: the single-stroke one, straight or with its corners rounded, or an installed font (outlines).
LABEL_LETTERS = ('plain', 'rounded', 'font')
_LIFT = 0.04                    # a label on a face stands off it (a share of its height), not to be hidden in it
_LINE_SPACING = 1.6             # from one line to the next, in heights of the capitals
#: How the lines of a label line up: at their centre, on the left, on the right.
LABEL_ALIGNS = ('centre', 'left', 'right')


def text(at, text="{n}", value=None, decimals=2, height=0.2, plane='plan', letter='plain', font="",
         align='centre', name: str | None = None) -> Data:
    """See the module. The result has the levels of `at` and one more, «stroke» (the strokes of each label).
    `letter`: the single-stroke one (plain or rounded: capitals only) or a `font` installed (its outlines, closed
    curves: with lower case and accents)."""
    if align not in LABEL_ALIGNS:
        raise ShapeError(tr('“align” must be one of: {options}.').format(
            options=", ".join(tr(p) for p in LABEL_ALIGNS)))
    if letter not in LABEL_LETTERS:
        raise ShapeError(tr('“lettering” must be one of: {options}.').format(
            options=", ".join(tr(p) for p in LABEL_LETTERS)))
    if not isinstance(at, Data) or at.kind is None:
        raise ShapeError(tr('“at” should be geometry (points, curves, panels, bodies): where the labels go.'))
    if plane not in LABEL_PLANES:
        raise ShapeError(tr('“plane” must be one of: {options}.').format(
            options=", ".join(tr(p) for p in LABEL_PLANES)))
    h = float(np.asarray(getattr(height, "values", height), float).reshape(-1)[0])
    if not h > 0:
        raise ShapeError(tr('The height of the letters must be greater than zero.'))
    places = int(round(float(np.asarray(getattr(decimals, "values", decimals), float).reshape(-1)[0])))
    places = min(max(places, 0), 6)
    anchors, normals = _anchors(at, plane)                     # (… , 3) each, the shape of the elements
    shape = anchors.shape[:-1]
    values = _values(value, at, shape)
    written = _as_text(text)
    choices = [t.strip() for t in written.split(";")] if ";" in written else None
    level_names = _level_names(at)
    n = int(np.prod(shape, dtype=int))
    flat_anchors, flat_normals = anchors.reshape(-1, 3), normals.reshape(-1, 3)
    flat_values = None if values is None else values.reshape(-1)
    labels, frames = [], []
    for k, index in enumerate(np.ndindex(shape) if shape else [()]):
        label = choices[k % len(choices)] if choices else written
        numbers = {lv: str(at.starts.get(lv, 0) + i) for lv, i in zip(at.levels, index)}
        label = _fill(label, numbers, level_names, None if flat_values is None else flat_values[k], places)
        labels.append(label.strip())
        frames.append(_frame(plane, flat_normals[k]))
    strokes_of, most_strokes, most_points = [], 1, 2
    for k, label in enumerate(labels):
        u, v, normal = frames[k]
        lift = normal * (h * _LIFT) if np.any(flat_normals[k]) else 0.0     # off its face, not hidden in it
        drawn = [flat_anchors[k] + lift + s[:, :1] * u + s[:, 1:] * v
                 for s in _block(label, h, letter, str(font or ""), align)]
        strokes_of.append(drawn)
        most_strokes = max(most_strokes, len(drawn))
        most_points = max([most_points] + [len(s) for s in drawn])
    out = np.zeros((n, most_strokes, most_points, 3))
    empty = np.zeros((n, most_strokes), dtype=bool)
    for k, drawn in enumerate(strokes_of):
        if not drawn:                                          # nothing to write here (a space, an unknown sign)
            out[k] = flat_anchors[k]
            empty[k] = True
            continue
        for j in range(most_strokes):
            s = drawn[min(j, len(drawn) - 1)]                   # (the missing strokes repeat the last one)
            out[k, j] = np.vstack([s, np.repeat(s[-1:], most_points - len(s), axis=0)])
    out = out.reshape(shape + (most_strokes, most_points, 3))
    empty = empty.reshape(shape + (most_strokes,))
    holes = empty
    if at.holes is not None:
        holes = holes | at.holes.reshape(at.holes.shape + (1,))
    # Each label, with as many strokes as it has (not repeated: a drawing would get each line twice).
    counts = np.array([max(1, len(d)) for d in strokes_of]).reshape(shape)
    variables = dict(at.variables)
    if (counts != most_strokes).any():
        variables["stroke"] = Data(counts, at.levels, None, at.variables, at.starts)
    return Data(out, at.levels + ("stroke",), name, variables, at.starts, CURVE, holes)


def _block(label: str, h: float, letter: str, font: str, align: str) -> list[np.ndarray]:
    """The lines of a label (split at «|»), one under the other, each aligned to the left, the centre or the right
    of the longest, and the whole block centred on its place: 2D, the capitals `h` tall."""
    from .strokes import styled, text_strokes, text_width
    lines = [line.strip() for line in label.split("|")]
    drawn = []
    for line in lines:
        if letter == 'font':
            from .fonts import outlines
            shapes, w = outlines(line, font, h)
        else:
            shapes, w = styled(text_strokes(line, h), h, letter), text_width(line, h)
        drawn.append((shapes, w))
    widest = max(w for _, w in drawn)
    tall = h + (len(lines) - 1) * _LINE_SPACING * h
    placed = []
    for i, (shapes, w) in enumerate(drawn):
        x = {'left': -widest / 2, 'right': widest / 2 - w}.get(align, -w / 2)
        y = tall / 2 - h - i * _LINE_SPACING * h               # the first line on top
        placed += [s + [x, y] for s in shapes]
    return placed


def _as_text(text) -> str:
    """What was typed, as text: a number typed alone (12, 2,5) comes read as a number; a list, as numbers."""
    if text is None:
        return ""
    if isinstance(text, bool):
        return tr('yes') if text else tr('no')
    if isinstance(text, (int, float, np.number)):
        x = float(text)
        return str(int(x)) if x.is_integer() else comma(f"{x:g}")
    if isinstance(text, (list, tuple)):
        return "; ".join(_as_text(t) for t in text)
    return str(text)


def _anchors(at: Data, plane: str) -> tuple[np.ndarray, np.ndarray]:
    """Where each label goes, and (for «on the face», or a body read from a side) the way its face looks: zero where
    it has none (a point, a curve)."""
    v = np.asarray(at.values, float)
    kind = at.kind
    if kind in (POINT, VECTOR) or (kind.faces is None and not kind.curve):
        return v, np.zeros_like(v)
    elements = v.reshape((-1,) + v.shape[-2:])
    shape = v.shape[:-2]
    if kind.curve:
        middle = elements[:, elements.shape[1] // 2]
        return middle.reshape(shape + (3,)), np.zeros(shape + (3,))
    centre = elements.mean(axis=1)
    normal = np.zeros_like(centre)
    for face in kind.faces:                                    # Newell: the way each element looks
        ring = elements[:, list(face)]
        nxt = np.roll(ring, -1, axis=1)
        normal += np.stack([((ring[..., 1] - nxt[..., 1]) * (ring[..., 2] + nxt[..., 2])).sum(1),
                            ((ring[..., 2] - nxt[..., 2]) * (ring[..., 0] + nxt[..., 0])).sum(1),
                            ((ring[..., 0] - nxt[..., 0]) * (ring[..., 1] + nxt[..., 1])).sum(1)], axis=1)
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    size = np.ptp(elements, axis=1).max(axis=1, keepdims=True)
    open_ = length[:, 0] > 1e-9 * np.maximum(size[:, 0], 1e-12) ** 2
    normal = np.where(open_[:, None], normal / np.maximum(length, 1e-300), 0.0)
    if plane != 'on the face' or not open_.all():
        # A body (closed), or any surface read in plan or elevation: on the side that looks at the reader.
        axis, toward = {'plan': (2, 1.0), 'elevation': (1, -1.0), 'side elevation': (0, 1.0),
                        'on the face': (1, -1.0)}[plane]
        side = elements[..., axis].max(axis=1) if toward > 0 else elements[..., axis].min(axis=1)
        reader = np.zeros(3)
        reader[axis] = toward
        body = ~open_ if plane == 'on the face' else np.ones(len(centre), dtype=bool)
        centre[body, axis] = side[body]
        normal[body] = reader
    return centre.reshape(shape + (3,)), normal.reshape(shape + (3,))


def _frame(plane: str, normal: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The across (u) and up (v) of a label, and the way it looks."""
    if plane != 'on the face' or not np.any(normal):
        u, v = (np.asarray(a, float) for a in PLANES['plan' if plane == 'on the face' else plane])
        return u, v, np.cross(u, v)                           # (towards the reader: up, to the front, to +x)
    n = normal / np.linalg.norm(normal)
    up = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([0.0, 1.0, 0.0] if n[2] > 0 else [0.0, -1.0, 0.0])
    v = up - n * (up @ n)                                      # «up» on the face
    v /= np.linalg.norm(v)
    u = np.cross(v, n)                                         # read from where the face looks
    return u, v, n


def _values(value, at: Data, shape: tuple) -> np.ndarray | None:
    """The numbers of `value`, one per element of `at` (by their levels)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    from .data import align
    if not isinstance(value, Data):
        try:
            value = Data.value(float(np.asarray(value, float).reshape(-1)[0]))
        except (TypeError, ValueError):
            raise ShapeError(tr('“value” should be numbers: one for each label (an area, a length).')) from None
    if value.kind is not None:
        raise ShapeError(tr('“value” should be numbers: one for each label (an area, a length).'))
    marks = Data(np.zeros(shape), at.levels, at.name, at.variables, at.starts)
    aligned = align(marks, value)
    if aligned.levels != at.levels:
        extra = [lv for lv in aligned.levels if lv not in at.levels]
        raise ShapeError(tr('“value” has levels that the labels do not have: {levels}. One number for each '
                            'label.').format(levels=", ".join(tr(lv) for lv in extra)))
    return np.broadcast_to(np.asarray(aligned.values[1], float), shape)


def _level_names(at: Data) -> dict[str, str]:
    """Each level by the names it can be written with: its own («floor») and in Spanish («piso»), whatever the
    language set (a project written in one language reads the same in the other)."""
    from .translations import es
    names = {}
    for lv in at.levels:
        names[es.TEXTS.get(lv, lv).casefold()] = lv
        names[lv.casefold()] = lv
    names["n"] = "n"
    return names


def _fill(label: str, numbers: dict[str, str], level_names: dict[str, str], value, places: int) -> str:
    """The label with its {…} written: the number of the element, of a level, or its value."""
    def one(match):
        key = match.group(1).strip().casefold()
        if key in ("value", "valor"):
            if value is None:
                return "?"
            return comma(f"{float(value):.{places}f}")
        if key == "n":
            return "·".join(numbers.values()) if numbers else "0"
        level = level_names.get(key)
        if level in numbers:
            return numbers[level]
        return match.group(0)
    return re.sub(r"\{([^{}]*)\}", one, label)
