"""A three-dimensional fractal with a group that repeats itself, and Delaunay of three or four points."""

import time
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from tensela.mesh_tools import _delaunay_few, mesh_faces
from tensela.project_file import open_


def _circle_is_empty(xy, triangles) -> bool:
    for a, b, c in triangles:
        p = xy[[a, b, c]]
        m = 2 * np.array([p[1] - p[0], p[2] - p[0]])
        centre = np.linalg.solve(m, [p[1] @ p[1] - p[0] @ p[0], p[2] @ p[2] - p[0] @ p[0]])
        radius = np.linalg.norm(p[0] - centre)
        if any(np.linalg.norm(xy[i] - centre) < radius - 1e-9 for i in range(len(xy)) if i not in (a, b, c)):
            return False
    return True


def test_three_or_four_points_give_the_delaunay_triangles_directly():
    rng = np.random.default_rng(3)
    for _ in range(2000):
        xy = rng.random((4, 2))
        triangles = _delaunay_few(xy)
        assert _circle_is_empty(xy, triangles)
        area = sum(0.5 * abs((xy[b] - xy[a])[0] * (xy[c] - xy[a])[1] - (xy[b] - xy[a])[1] * (xy[c] - xy[a])[0])
                   for a, b, c in triangles)
        from itertools import permutations
        best = max(0.5 * abs((xy[b] - xy[a])[0] * (xy[c] - xy[a])[1] - (xy[b] - xy[a])[1] * (xy[c] - xy[a])[0])
                   for a, b, c in permutations(range(4), 3))
        assert area >= best - 1e-9                              # it covers at least the largest triangle (the hull)
    triangle = np.array([[0, 0], [2, 0], [1, 2]], float)
    assert _delaunay_few(triangle) == [(0, 1, 2)]
    assert _delaunay_few(np.vstack([triangle, [[1, 0.6]]])) == [(0, 1, 3), (1, 2, 3), (2, 0, 3)]
    assert _delaunay_few(np.array([[0, 0], [1, 0], [2, 0]], float)) == []      # in a line: nothing


