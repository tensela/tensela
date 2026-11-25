"""Nesting that fits the pieces into one another: the biggest first, each piece goes as far to the left as it fits (and
then as low), in whichever of its four quarter turns reaches least far, also inside the holes of the pieces already
placed (the small rings of a lamp inside the big ones) and in the hollows of their outlines.

The sheet is read as a fine grid of cells. Each piece takes the cells its outline, grown by half the spacing, could
touch (a little more than it needs, never less), so two pieces whose cells do not meet are always at least the spacing
apart. Where a piece fits is found for every position at once, by correlating its cells with the cells already taken
(with the Fourier transform)."""
import numpy as np

#: How many cells the longer side of a sheet is read with (finer: tighter, and slower).
CELLS = 700

_MM = 1000.0


def _fast_size(n: int) -> int:
    """The smallest size from n up whose factors are only 2, 3 and 5 (the transform is fast there)."""
    while True:
        m = n
        for f in (2, 3, 5):
            while m % f == 0:
                m //= f
        if m == 1:
            return n
        n += 1


def _grown(rings: list[np.ndarray], d: float) -> list[np.ndarray]:
    """The piece (outline, holes) grown by d all around: its holes shrink. Square corners, which reach a little past
    the round ones, never short of them."""
    from manifold3d import CrossSection, FillRule, JoinType
    region = CrossSection([r * _MM for r in rings], FillRule.EvenOdd)
    if d > 0:
        region = region.offset(d * _MM, JoinType.Square)
    return [np.asarray(p, float) / _MM for p in region.to_polygons() if len(p) >= 3]


def _raster(rings: list[np.ndarray], origin: np.ndarray, cell: float, shape: tuple[int, int]) -> np.ndarray:
    """The cells (rows along y, columns along x) whose centre falls inside the rings (even-odd), the grid starting at
    `origin`."""
    rows, cols = shape
    mask = np.zeros((rows, cols + 1), np.int32)
    ys = origin[1] + (np.arange(rows) + 0.5) * cell
    hits_row, hits_x = [], []
    for r in rings:
        a, b = r, np.roll(r, -1, axis=0)
        low, high = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
        first = np.ceil((low - origin[1]) / cell - 0.5).astype(int)          # the rows whose centre is in [low, high)
        last = np.ceil((high - origin[1]) / cell - 0.5).astype(int)
        first, last = np.clip(first, 0, rows), np.clip(last, 0, rows)
        counts = last - first
        if counts.sum() == 0:
            continue
        edge = np.repeat(np.arange(len(a)), counts)
        row = np.concatenate([np.arange(f, l) for f, l in zip(first, last) if l > f])
        y = ys[row]
        t = (y - a[edge, 1]) / (b[edge, 1] - a[edge, 1])
        hits_row.append(row)
        hits_x.append(a[edge, 0] + t * (b[edge, 0] - a[edge, 0]))
    if not hits_row:
        return mask[:, :cols].astype(bool)
    row, x = np.concatenate(hits_row), np.concatenate(hits_x)
    order = np.lexsort((x, row))
    row, x = row[order], x[order]
    # Even-odd: the crossings of each row go in pairs, in and out.
    start, end = row[0::2], row[1::2]
    keep = start == end                              # (always, for closed rings)
    x0, x1, row = x[0::2][keep], x[1::2][keep], start[keep]
    i0 = np.clip(np.ceil((x0 - origin[0]) / cell - 0.5).astype(int), 0, cols)
    i1 = np.clip(np.ceil((x1 - origin[0]) / cell - 0.5).astype(int), 0, cols)
    np.add.at(mask, (row, i0), 1)
    np.add.at(mask, (row, i1), -1)
    return np.cumsum(mask, axis=1)[:, :cols] > 0


def _turned(q: list[np.ndarray], degrees: float) -> list[np.ndarray]:
    """The piece turned by so many degrees, from (0, 0) again."""
    a = np.radians(degrees)
    c, s = np.cos(a), np.sin(a)
    out = [r @ np.array([[c, s], [-s, c]]) for r in q]
    low = out[0].min(axis=0)
    return [r - low for r in out]


#: The turns a piece is tried with (degrees).
TURNS = (0, 90, 180, 270)


class _Sheet:
    def __init__(self, rows: int, cols: int, size: tuple[int, int]):
        self.taken = np.ones(size)                   # beyond the sheet counts as taken
        self.taken[:rows, :cols] = 0.0
        self.rows, self.cols = rows, cols
        self.free = rows * cols
        self._spectrum = None
        self.failed = set()                          # the shapes that did not fit: they never will (it only fills)

    def spectrum(self) -> np.ndarray:
        if self._spectrum is None:
            self._spectrum = np.fft.rfft2(self.taken)
        return self._spectrum

    def take(self, mask: np.ndarray, i: int, j: int):
        self.taken[i:i + mask.shape[0], j:j + mask.shape[1]] += mask
        self.free -= int(mask.sum())
        self._spectrum = None


def nest(items: list, usable: tuple[float, float], gap: float, turn: bool, cells: int = CELLS):
    """`items`: [label, index, rings (upright, from (0, 0)), width, height]. Returns how many sheets and, for each
    piece, (label, index, rings turned, sheet, x, y): where its (0, 0) goes from the corner of the usable part of its
    sheet; or None for a piece that does not fit even on an empty sheet."""
    W, H = usable
    cell = max(W, H) / cells
    d = gap / 2 + cell * 0.7072                      # the reach of a cell from its centre, plus half the spacing
    # The grid starts half a spacing before the usable part: a piece's cells cover its outline grown by half the
    # spacing, so a piece whose cells are inside the grid is inside the usable part.
    start = -gap / 2
    cols, rows = int(np.floor((W + gap) / cell + 1e-9)), int(np.floor((H + gap) / cell + 1e-9))
    size = (_fast_size(rows), _fast_size(cols))
    k = int(np.ceil(d / cell)) + 1                   # cells before the piece's (0, 0)
    sheets: list[_Sheet] = []
    placed = []

    def area(item):
        rings = item[2]
        return abs(_signed(rings[0])) - sum(abs(_signed(r)) for r in rings[1:])

    def shapes_for(q, angles):
        shapes = []
        for angle in angles:
            rings = _turned(q, angle)
            span = rings[0].max(axis=0)
            m_cols = int(np.ceil(span[0] / cell)) + 2 * k
            m_rows = int(np.ceil(span[1] / cell)) + 2 * k
            if m_rows > rows or m_cols > cols:
                continue
            mask = _raster(_grown(rings, d), np.array([-k * cell, -k * cell]), cell, (m_rows, m_cols))
            if any(m.shape == mask.shape and (m ^ mask).sum() <= 0.02 * mask.sum() for _, m, _ in shapes):
                continue                             # about the same as a turn already there (a ring, a strip)
            shapes.append([rings, mask, (mask.shape, mask.tobytes())])
        return shapes

    kernels = {}                                     # the transform of each shape: equal pieces share it

    def kernel_of(key, mask):
        if key not in kernels:
            padded = np.zeros(size)
            padded[:mask.shape[0], :mask.shape[1]] = mask
            kernels[key] = np.conj(np.fft.rfft2(padded))
        return kernels[key]

    def where(shapes, choices):
        """The first sheet of `choices` (number, sheet) where one of the shapes fits, and where."""
        for s, sheet in choices:
            best, spectrum = None, None
            for rings, mask, key in shapes:
                # Equal pieces (the triangles of a faceted shell) skip the sheets where one of them did not fit:
                # 144 triangles went from 25 s to about 2, in the same places.
                if key in sheet.failed or mask.sum() > sheet.free:
                    continue
                if spectrum is None:
                    spectrum = sheet.spectrum()
                overlap = np.fft.irfft2(spectrum * kernel_of(key, mask), size)
                valid = overlap[:rows - mask.shape[0] + 1, :cols - mask.shape[1] + 1] < 0.5
                if not valid.any():
                    sheet.failed.add(key)
                    continue
                # The leftmost place, then the lowest; and of the turns, the one whose right side reaches least far.
                j = int(np.flatnonzero(valid.any(axis=0))[0])
                i = int(np.flatnonzero(valid[:, j])[0])
                score = (j + mask.shape[1], i)
                if best is None or score < best[0]:
                    best = (score, s, sheet, rings, mask, i, j)
            if best is not None:
                return best
        return None

    for label, index, q, w, h in sorted(items, key=lambda it: (-max(it[3], it[4]) * min(it[3], it[4]), -area(it))):
        shapes = shapes_for(q, TURNS if turn else (0,))
        if not shapes:
            placed.append((label, index, q, None, 0.0, 0.0))
            continue
        best = where(shapes, list(enumerate(sheets)))
        if best is None:
            best = where(shapes, [(len(sheets), _Sheet(rows, cols, size))])
        if best is None:
            placed.append((label, index, q, None, 0.0, 0.0))
            continue
        _, s, sheet, rings, mask, i, j = best
        if s == len(sheets):
            sheets.append(sheet)
        sheet.take(mask, i, j)
        placed.append((label, index, rings, s, start + (j + k) * cell, start + (i + k) * cell))
    return len(sheets), placed


def _signed(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
