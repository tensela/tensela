"""Attractors: the Attractor node (points, curves, several, reach, reversed), Remap with «clamp», Closest point, and
painting by a value."""
import numpy as np
import pytest

from tensela import geometry as geo
from tensela.project_file import open_, values_by_element
from tensela.data import ShapeError, series


def _grid():
    return geo.point(series(21, 0, 1, "columna"), series(21, 0, 1, "fila"), 0)


def test_point_attractor():
    a = geo.attractor(_grid(), geo.point(5, 5, 0), near=0.01, far=0.8)
    assert a.levels == ("columna", "fila")
    assert a.values[5, 5] == pytest.approx(0.01)
    assert a.values.max() == pytest.approx(0.8)          # the farthest
    assert a.values[6, 5] < a.values[9, 5]               # it grows moving away


def test_reach_and_reversed():
    a = geo.attractor(_grid(), geo.point(10, 10, 0), reach=4, near=2, far=1)
    assert a.values[10, 10] == pytest.approx(2)
    assert a.values[10, 12] == pytest.approx(1.5)
    assert a.values[0, 0] == pytest.approx(1)             # out of reach: «far»
    assert np.count_nonzero(a.values > 1) < 60
    with pytest.raises(ShapeError, match="mayor que 0"):
        geo.attractor(_grid(), geo.point(0, 0, 0), reach=0)


def test_several_attractors_the_nearest_and_summed():
    two = geo.point(series(2, 2, 16, "atractor"), 10, 0)
    nearest = geo.attractor(_grid(), two, reach=5)
    assert nearest.levels == ("columna", "fila")
    assert nearest.values[2, 10] == pytest.approx(1) and nearest.values[18, 10] == pytest.approx(1)
    together = geo.attractor(_grid(), geo.point(series(2, 9, 2, "atractor"), 10, 0), reach=6, several='add up')
    only = geo.attractor(_grid(), geo.point(9, 10, 0), reach=6)
    assert together.values[10, 10] > only.values[10, 10]


def test_curve_and_point_mixed():
    curve = geo.line((0, 0, 0), (20, 0, 0))
    a = geo.attractor(_grid(), curve, more=geo.point(10, 20, 0), reach=3)
    assert a.values[7, 0] == pytest.approx(1)             # on the curve
    assert a.values[10, 20] == pytest.approx(1)           # on the point
    assert a.values[10, 10] == pytest.approx(0)


def test_geometry_by_its_centre():
    circles = geo.circle(_grid(), 0.5)
    a = geo.attractor(circles, geo.point(5, 5, 0))
    assert a.values[5, 5] == pytest.approx(1, abs=1e-6)


def test_remap_clamp():
    s = series(5)
    assert geo.remap(s, (0, 2), (0, 1)).values.tolist() == [0, 0.5, 1, 1.5, 2]
    assert geo.remap(s, (0, 2), (0, 1), limit=True).values.tolist() == [0, 0.5, 1, 1, 1]


def test_closest_point():
    curve = geo.line((0, 0, 0), (10, 10, 0))
    p = geo.point(10, 0, 0)
    assert geo.point_more_nearest(p, curve).values.tolist() == pytest.approx([5, 5, 0])
    assert float(geo.point_more_nearest(p, curve, 'fraction').values) == pytest.approx(0.5)
    assert float(geo.point_more_nearest(p, curve, 'distance').values) == pytest.approx(50 ** 0.5)
    with pytest.raises(ShapeError, match="debería ser una curva"):
        geo.point_more_nearest(p, p)


def test_values_by_element():
    r = _grid()
    discs = geo.circle(r, 0.5)
    a = geo.attractor(r, geo.point(0, 0, 0))
    v = values_by_element(discs, a)
    assert v.shape == (441,) and v[0] == pytest.approx(1)
    # A value per column holds for the whole column.
    by_column = values_by_element(discs, series(21, 0, 1, "columna"))
    assert by_column[:21].tolist() == [0] * 21
    assert values_by_element(discs, series(5, level="otro")) is None


