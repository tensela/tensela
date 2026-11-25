import numpy as np
import pytest

pytest.importorskip("pyvista")

from tensela.geometry import line, curve_points, rectangle  # noqa: E402
from tensela.data import series  # noqa: E402
from tensela.ui.viewer import numbers_of  # noqa: E402


def test_each_point_carries_its_number_from_0():
    p = curve_points(line((0, 0, 0), (10, 0, 0)), 6)
    anchors, texts = numbers_of(p)
    assert texts == ["0", "1", "2", "3", "4", "5"] and np.allclose(anchors[:, 0], [0, 2, 4, 6, 8, 10])


def test_with_two_levels_the_number_is_of_both():
    rows = rectangle(2, 1, origin=(0, 0, 0))
    from tensela.geometry import move, point
    several = move(rows, point(0, series(3, 0, 2, "fila"), 0))                  # 3 rectangles
    anchors, texts = numbers_of(several)
    assert texts == ["0", "1", "2"] and np.allclose(anchors[:, 1], [0.5, 2.5, 4.5])   # at its centre
    pts = curve_points(move(line((0, 0, 0), (4, 0, 0)), point(0, series(2, 0, 1, "fila"), 0)), 3)
    assert numbers_of(pts)[1] == ["0·0", "0·1", "0·2", "1·0", "1·1", "1·2"]     # fila · punto


def test_a_single_curve_carries_no_number():
    anchors, texts = numbers_of(line((0, 0, 0), (1, 0, 0)))
    assert texts == [""]
