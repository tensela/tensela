"""Lay flat «fit together»: the pieces fitted into one another, always at least the spacing apart and inside the margin."""
import numpy as np
import pytest
from manifold3d import CrossSection, FillRule

from tensela import fabrication as F
from tensela import language
from tensela.values import ShapeError


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _circle(r, n=64, centre=(0.0, 0.0)):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([centre[0] + r * np.cos(a), centre[1] + r * np.sin(a), np.zeros(n)])


def _rings(radii, wall=0.012):
    """Flat rings (outline and hole), as the level sections of a lamp."""
    return F._pieces_table([[_circle(r), _circle(r - wall)[::-1]] for r in radii], "ring", None)


def _ells(count, arm=0.18, width=0.04):
    """L-shaped pieces."""
    shape = np.array([[0, 0], [arm, 0], [arm, width], [width, width], [width, arm], [0, arm]], float)
    return F._pieces_table([[np.column_stack([shape, np.zeros(6)])] for _ in range(count)], "piece", None)


def _apart_and_inside(laid, gap, margin):
    """Every two pieces at least `gap` apart; every piece at least `margin` from the edge of its sheet."""
    regions, boxes = [], laid.layout.boxes
    for _, rings in F._groups(laid):
        flat = [r[:, :2] * 1000 for r in rings]
        regions.append(CrossSection(flat, FillRule.EvenOdd))
        low, high = flat[0].min(axis=0) / 1000, flat[0].max(axis=0) / 1000
        assert any(b[0] + margin - 1e-9 <= low[0] and high[0] <= b[2] - margin + 1e-9 and
                   b[1] + margin - 1e-9 <= low[1] and high[1] <= b[3] - margin + 1e-9 for b in boxes)
    grown = [r.offset(gap / 2 * 1000 * 0.999) for r in regions]
    for i in range(len(grown)):
        for j in range(i + 1, len(grown)):
            assert (grown[i] ^ grown[j]).area() < 1e-6, (i, j)


def test_small_rings_go_inside_the_holes_of_the_big_ones():
    rings = _rings([0.17, 0.15, 0.13, 0.11, 0.09, 0.07, 0.05, 0.03])
    rows = F.lay_flat(rings, 0.6, 0.4, 0.004, 0.01, nesting='in rows')
    fitted = F.lay_flat(rings, 0.6, 0.4, 0.004, 0.01)
    assert len(rows.layout.boxes) >= 3
    assert len(fitted.layout.boxes) == 1                    # all of them, one inside the other
    assert fitted.layout.used > 2.5 * rows.layout.used
    _apart_and_inside(fitted, 0.004, 0.01)
    numbers = F.lay_flat(rings, 0.6, 0.4, 0.004, 0.01, show='numbers')
    assert not F.lay_flat(rings, 0.6, 0.4, 0.004, 0.01).layout.unnumbered and len(numbers.values)


def test_spacing_and_margin_are_kept_whatever_they_are():
    for gap, margin in ((0.004, 0.01), (0.012, 0.02), (0.0, 0.0)):
        _apart_and_inside(F.lay_flat(_ells(10), 0.6, 0.4, gap, margin), gap, margin)
    _apart_and_inside(F.lay_flat(_rings([0.12, 0.1, 0.06, 0.04]), 0.5, 0.3, 0.006, 0.015, more=_ells(4)), 0.006,
                      0.015)


def test_ells_take_less_sheet_fitted_than_in_rows():
    rows = F.lay_flat(_ells(16), 0.6, 0.4, 0.004, 0.01, nesting='in rows')
    fitted = F.lay_flat(_ells(16), 0.6, 0.4, 0.004, 0.01)
    assert len(fitted.layout.boxes) < len(rows.layout.boxes)


def test_without_turning_the_pieces_keep_their_lie():
    laid = F.lay_flat(_ells(3), 0.6, 0.4, 0.004, 0.01, turn=False)
    for _, rings in F._groups(laid):                        # the corner of the L, down and to the left, as given
        outline = rings[0][:, :2]
        low = outline.min(axis=0)
        assert np.isclose(np.linalg.norm(outline - low, axis=1).min(), 0, atol=1e-9)


def test_what_does_not_fit_and_a_wrong_option_are_said():
    with pytest.raises(ShapeError, match="does not fit"):
        F.lay_flat(_rings([0.3]), 0.6, 0.4)
    with pytest.raises(ShapeError, match="nesting"):
        F.lay_flat(_rings([0.1]), 0.6, 0.4, nesting='tightly')


def test_the_cutting_file_cuts_from_the_inside_out():
    from tensela.connectors.cutting import gather
    rings = _rings([0.17, 0.13, 0.09, 0.05])
    lines, _ = gather([("pieces", F.lay_flat(rings, 0.6, 0.4, 0.004, 0.01))])
    sizes = [float(np.ptp(p[:, 0])) for op, p, closed in lines if op == "cut"]
    assert sizes == sorted(sizes)                    # nested one inside the other: the smallest contour first


def test_many_sheets_go_in_rows():
    from tensela import fabrication as F
    from tensela import geometry as geo
    from tensela.data import Data
    square = np.array([[0, 0, 0], [0.3, 0, 0], [0.3, 0.3, 0], [0, 0.3, 0]], float)
    many = Data(np.repeat(square[None], 30, axis=0), ("piece",), None, kind=geo.CLOSED_CURVE)
    sheets = np.asarray(F.lay_flat(many, 0.4, 0.4, show='sheets', nesting='in rows').values)
    corners = sheets.reshape(len(sheets), -1, 3).min(1)
    assert len(sheets) == 30 and len(np.unique(np.round(corners[:, 1], 6))) > 1    # more than one row
    few = Data(np.repeat(square[None], 5, axis=0), ("piece",), None, kind=geo.CLOSED_CURVE)
    corners = np.asarray(F.lay_flat(few, 0.4, 0.4, show='sheets', nesting='in rows').values).reshape(5, -1, 3).min(1)
    assert np.allclose(corners[:, 1], corners[0, 1])                          # a few: side by side, as before
