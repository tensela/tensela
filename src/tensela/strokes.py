"""A single-stroke lettering, to engrave numbers and names on pieces to be cut: each character is a few lines (not an
outline), which a laser or a router follows once.

    text_strokes("12", height=0.005)   → a list of polylines (k × 2), the text starting at (0, 0), its baseline on y = 0

The characters are drawn on a grid four units wide and six high; the advance from one to the next is five units.
"""
from __future__ import annotations

import numpy as np

# Each character, its strokes as lists of (x, y) on a grid of 4 × 6 (y up).
_GLYPHS: dict[str, list[list[tuple[float, float]]]] = {
    "0": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)], [(0.5, 1), (3.5, 5)]],
    "1": [[(1, 5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    "3": [[(0, 6), (4, 6), (2, 4), (3, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "4": [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    "5": [[(4, 6), (0, 6), (0, 3.5), (3, 3.5), (4, 2.5), (4, 1), (3, 0), (0, 0)]],
    "6": [[(3.5, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2.5), (3, 3.5), (0, 3.5)]],
    "7": [[(0, 6), (4, 6), (1.5, 0)]],
    "8": [[(1, 3.2), (0, 4.2), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4.2), (3, 3.2), (1, 3.2), (0, 2.2), (0, 1),
           (1, 0), (3, 0), (4, 1), (4, 2.2), (3, 3.2)]],
    "9": [[(4, 2.5), (1, 2.5), (0, 3.5), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (0.5, 0)]],
    "-": [[(0.5, 3), (3.5, 3)]],
    ".": [[(1.8, 0), (2.2, 0), (2.2, 0.4), (1.8, 0.4), (1.8, 0)]],
    "/": [[(0, 0), (4, 6)]],
    "·": [[(1.8, 2.8), (2.2, 2.8), (2.2, 3.2), (1.8, 3.2), (1.8, 2.8)]],
    ",": [[(2.2, 0.4), (2.2, 0), (1.6, -1)]],
    ":": [[(1.8, 0), (2.2, 0), (2.2, 0.4), (1.8, 0.4), (1.8, 0)], [(1.8, 3.6), (2.2, 3.6), (2.2, 4), (1.8, 4),
                                                                    (1.8, 3.6)]],
    "+": [[(0.5, 3), (3.5, 3)], [(2, 1.5), (2, 4.5)]],
    "=": [[(0.5, 2), (3.5, 2)], [(0.5, 4), (3.5, 4)]],
    "(": [[(3, 6.5), (1.5, 5), (1.5, 1), (3, -0.5)]],
    ")": [[(1, 6.5), (2.5, 5), (2.5, 1), (1, -0.5)]],
    "%": [[(0, 0), (4, 6)], [(0.5, 5.5), (1, 6), (1.5, 5.5), (1, 5), (0.5, 5.5)],
          [(2.5, 0.5), (3, 1), (3.5, 0.5), (3, 0), (2.5, 0.5)]],
    "#": [[(1.2, 0), (1.8, 6)], [(2.6, 0), (3.2, 6)], [(0, 2), (4, 2)], [(0, 4), (4, 4)]],
    "°": [[(1.5, 5), (2, 5.5), (2.5, 5), (2, 4.5), (1.5, 5)]],
    "Ñ": [[(0, 0), (0, 5), (4, 0), (4, 5)], [(0.5, 6), (1.5, 6.6), (2.5, 6), (3.5, 6.6)]],
    "A": [[(0, 0), (2, 6), (4, 0)], [(0.7, 2), (3.3, 2)]],
    "B": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 6), (2.5, 6), (4, 4.5), (4, 1.5), (2.5, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2.5, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 6), (3, 6)], [(2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "J": [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 2)], [(1.4, 3.4), (4, 0)]],
    "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    "O": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],
    "P": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]],
    "Q": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)], [(2.5, 1.5), (4, 0)]],
    "R": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(2, 3), (4, 0)]],
    "S": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "U": [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 3), (3, 0), (4, 6)]],
    "X": [[(0, 0), (4, 6)], [(0, 6), (4, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
}
_ADVANCE = 5.0
_HEIGHT = 6.0


def text_width(text: str, height: float) -> float:
    """How long a text is, at a given height (from the left of the first character to the right of the last)."""
    n = len(text)
    return 0.0 if n == 0 else (n * _ADVANCE - 1.0) * height / _HEIGHT


def text_strokes(text: str, height: float) -> list[np.ndarray]:
    """The strokes of a text: its characters side by side from (0, 0), at `height` (the capital height). Characters
    it does not have are left as a space; lower case is drawn as upper case, and accents are taken off."""
    scale = height / _HEIGHT
    strokes = []
    for k, ch in enumerate(_plain(text)):
        for stroke in _GLYPHS.get(ch, []):
            p = np.asarray(stroke, float)
            strokes.append((p + [k * _ADVANCE, 0.0]) * scale)
    return strokes


def _plain(text: str) -> str:
    """The text in capitals, its accents taken off (Á is A, Ü is U; the Ñ stays): the letters the lettering has."""
    import unicodedata
    out = []
    for ch in text.upper():
        if ch != "Ñ" and ch not in _GLYPHS:
            base = unicodedata.normalize("NFD", ch)[0]
            ch = base if base in _GLYPHS else ch
        out.append(ch)
    return "".join(out)


#: The letters: «plain», straight strokes; «rounded», the same with their corners eased.
LETTERS = ('plain', 'rounded')
#: How they are engraved: «single», one pass; «bold», two passes a little apart; «outline», the outline of each stroke
#: (to engrave filled, or to cut the letters out).
WEIGHTS = ('single', 'bold', 'outline')


def styled(strokes: list[np.ndarray], height: float, letter: str = 'plain', weight: str = 'single') -> list[np.ndarray]:
    """The strokes of a text (2D), in another letter or weight. A closed stroke (an O) repeats its first point."""
    if letter == 'rounded':
        strokes = [_eased(s, 0.12 * height) for s in strokes]
    if weight == 'bold':
        shift = np.array([1.0, -1.0]) * (0.045 * height)
        return [q for s in strokes for q in (s, s + shift)]
    if weight == 'outline':
        r = 0.07 * height
        return [ring for s in strokes for ring in _outline(s, r)]
    return strokes


def _closed(s: np.ndarray) -> bool:
    return len(s) > 3 and np.allclose(s[0], s[-1])


def _eased(s: np.ndarray, radius: float = 0.12) -> np.ndarray:
    """A stroke with its corners rounded by a small arc of `radius` (a share of the letter's height), its straight
    parts kept straight: the letter keeps its shape, only its corners soften. Its points (the top of an A, of a 1,
    a turn of more than about 100°) stay sharp, and so do its ends."""
    if len(s) < 3:
        return s
    closed = _closed(s)
    p = s[:-1] if closed else s
    keep = np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12]
    p = p[keep]
    n = len(p)
    if n < 3:
        return s
    out = []
    for i in range(n):
        if not closed and i in (0, n - 1):
            out.append(p[i])
            continue
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]
        u, v = a - b, c - b
        lu, lv = np.linalg.norm(u), np.linalg.norm(v)
        turn = -(u @ v) / (lu * lv)                    # the cosine of how much it turns: 1 straight on, -1 back
        if turn < -0.17 or turn > 0.985:               # a point (kept sharp), or almost straight (nothing to round)
            out.append(b)
            continue
        half = np.arccos(np.clip(-turn, -1.0, 1.0)) / 2    # half the angle between its two sides
        cut = min(radius / np.tan(half), 0.45 * min(lu, lv))   # where the arc starts, along each side
        p1, p2 = b + u / lu * cut, b + v / lv * cut
        for t in np.linspace(0.0, 1.0, 6):
            out.append((1 - t) ** 2 * p1 + 2 * (1 - t) * t * b + t ** 2 * p2)
    out = np.array(out)
    return np.vstack([out, out[:1]]) if closed else out


def _outline(s: np.ndarray, r: float) -> list[np.ndarray]:
    """The outline of a stroke `r` to each side: one ring round an open stroke (with square ends), two for a closed
    one (outside and inside)."""
    closed = _closed(s)
    p = s[:-1] if closed else s
    keep = np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12]
    p = p[keep]
    if len(p) < 2:                                    # a dot: a little square round it
        c = p[0]
        return [np.array([c + [-r, -r], c + [r, -r], c + [r, r], c + [-r, r], c + [-r, -r]])]

    def side(points: np.ndarray, loop: bool, d: float) -> np.ndarray:
        nxt = np.roll(points, -1, axis=0) - points if loop else np.vstack([np.diff(points, axis=0),
                                                                            np.diff(points, axis=0)[-1:]])
        prv = points - np.roll(points, 1, axis=0) if loop else np.vstack([np.diff(points, axis=0)[:1],
                                                                           np.diff(points, axis=0)])
        t1 = nxt / np.linalg.norm(nxt, axis=1, keepdims=True)
        t0 = prv / np.linalg.norm(prv, axis=1, keepdims=True)
        n0, n1 = t0 @ [[0, -1], [1, 0]], t1 @ [[0, -1], [1, 0]]       # to the left of the way
        miter = n0 + n1
        length = np.linalg.norm(miter, axis=1, keepdims=True)
        miter = np.where(length > 1e-9, miter / np.maximum(length, 1e-12), n1)
        cos = np.clip((miter * n1).sum(axis=1, keepdims=True), 0.5, 1.0)  # (a sharp corner: not too far out)
        return points + miter * (d / cos)

    if closed:
        outer, inner = side(p, True, r), side(p, True, -r)
        return [np.vstack([outer, outer[:1]]), np.vstack([inner, inner[:1]])]
    t_start = (p[1] - p[0]) / np.linalg.norm(p[1] - p[0])
    t_end = (p[-1] - p[-2]) / np.linalg.norm(p[-1] - p[-2])
    long = np.vstack([p[0] - t_start * r, p[1:-1], p[-1] + t_end * r]) if len(p) > 2 else \
        np.vstack([p[0] - t_start * r, p[-1] + t_end * r])
    left, right = side(long, False, r), side(long, False, -r)
    ring = np.vstack([left, right[::-1]])
    return [np.vstack([ring, ring[:1]])]
