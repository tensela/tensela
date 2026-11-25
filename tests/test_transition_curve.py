"""The transition curve: joining curves without breaks (Delivery 3, E3.6)."""

from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.data import ShapeError, series
from tensela.geometry import CURVE, circle, line, point, transition

EXAMPLES = Path(__file__).parent / "data"


def angles(curve):
    d = np.diff(curve, axis=-2)
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    return np.degrees(np.arccos(np.clip((d[1:] * d[:-1]).sum(-1), -1, 1)))


def test_transition_joins_without_breaks():
    a = line((0, 0, 0), (0, 1.48, 0))
    b = line((0, 2.48, 1.5), (0, 2.98, 1.5))
    t = transition(a, b, 0.76)
    assert t.kind == CURVE
    assert t.values[0] == pytest.approx([0, 0, 0]) and t.values[-1] == pytest.approx([0, 2.98, 1.5])
    # At both joints the direction does not change suddenly.
    assert angles(t.values).max() < 15


def test_transition_alone_without_joining():
    a, b = line((0, 0, 0), (1, 0, 0)), line((2, 1, 0), (3, 1, 0))
    t = transition(a, b, 0.5, join=False)
    assert t.values[0] == pytest.approx([1, 0, 0]) and t.values[-1] == pytest.approx([2, 1, 0])


def test_a_transition_per_tread():
    p = series(4, level="peldaño")
    a = line(point(0, p, 0), point(1, p, 0))
    b = line(point(2, p, 1), point(3, p, 1))
    assert transition(a, b).shape == "peldaño 4"


def test_more_bulge_wider():
    a, b = line((0, 0, 0), (1, 0, 0)), line((1, 0, 1), (2, 0, 1))
    far = lambda k: transition(a, b, k, join=False).values[:, 0].max()  # noqa: E731
    assert far(1.0) > far(0.2)


def test_transition_asks_for_open_curves():
    with pytest.raises(ShapeError, match="debería ser una curva abierta"):
        transition(circle(radius=1), line((0, 0, 0), (1, 0, 0)))


