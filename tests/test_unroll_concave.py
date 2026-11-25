"""Group 3.6 of the pending plan: the net of a concave body does not land on itself (an L, a U, a cross, a star, a
comb in plan, extruded). If no order fits it in one piece, it comes in several, side by side."""
import numpy as np
import pytest

from tensela.data import Data
from tensela.geometry import CLOSED_CURVE, _triangulate_plan, extrude
from tensela.unrolling import _triangles_cross, unroll


def star(n, r, r2):
    a = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    rr = np.where(np.arange(2 * n) % 2 == 0, r, r2)
    return np.column_stack([rr * np.cos(a), rr * np.sin(a)])


def comb(teeth=4, w=0.3, gap=0.3, depth=2.0, base=0.4):
    points, x = [(0, 0)], 0.0
    for k in range(teeth):
        points += [(x, base + depth), (x + w, base + depth), (x + w, base)]
        x += w + gap
        if k < teeth - 1:
            points += [(x, base)]
    return points + [(x - gap, 0)]


PLANS = {
    "L": [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)],
    "U": [(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3)],
    "cross": [(1, 0), (2, 0), (2, 1), (3, 1), (3, 2), (2, 2), (2, 3), (1, 3), (1, 2), (0, 2), (0, 1), (1, 1)],
    "star": star(5, 2, 0.8),
    "thin star": star(8, 2, 0.5),
    "comb": comb(),
}


def body(plan, height):
    c = np.column_stack([np.asarray(plan, float), np.zeros(len(plan))])
    return extrude(Data(c, (), "plan", kind=CLOSED_CURVE), (0, 0, height), caps=True)


def surface(b):
    v = np.asarray(b.values, float)
    total = 0.0
    for face in b.kind.faces:
        p = v[list(face)]
        total += 0.5 * np.linalg.norm(sum(np.cross(p[i], p[(i + 1) % len(p)]) for i in range(len(p))))
    return total


def perimeter(ring):
    return float(np.linalg.norm(ring - np.roll(ring, 1, 0), axis=1).sum())


@pytest.mark.parametrize("height", [0.3, 1.0, 3.0])
@pytest.mark.parametrize("name", list(PLANS))
def test_the_net_of_a_concave_body_does_not_land_on_itself(name, height):
    b = body(PLANS[name], height)
    net = unroll(b)
    v = np.asarray(net.values)[:, :2]
    faces = [v[list(f)] for f in net.kind.faces]
    # its faces, as they are: the same surface as the body
    area = sum(abs((q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]).sum()) / 2 for q in faces)
    assert area == pytest.approx(surface(b), rel=1e-6)
    # no face on another (each one cut in triangles: concave faces too)
    size = float(np.ptp(v, axis=0).max())
    pieces = []
    for q in faces:
        flat = np.column_stack([q, np.zeros(len(q))])
        pieces.append(np.array([[q[i] for i in t] for t in _triangulate_plan(flat)]).reshape(-1, 3, 2))
    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            assert not _triangles_cross(pieces[i], pieces[j], 1e-6 * size), (name, i, j)
    # The cut goes around every face except along the folds: no side welded to another, no side lost
    cut = sum(perimeter(np.asarray(c)[:, :2]) for c in unroll(b, 'outlines').values)
    folds = sum(float(np.linalg.norm(f[1] - f[0])) for f in np.asarray(unroll(b, 'folds').values))
    assert cut == pytest.approx(sum(perimeter(q) for q in faces) - 2 * folds, rel=1e-6)


@pytest.mark.parametrize("name", ["L", "U", "star", "comb"])
def test_most_concave_bodies_unroll_in_one_piece(name):
    b = body(PLANS[name], 1.0)
    faces = len(unroll(b).kind.faces)
    assert unroll(b, 'folds').shape.endswith(str(faces - 1))           # a single tree of folds: one piece


def test_a_star_with_thin_points_comes_in_more_pieces():
    b = body(PLANS["thin star"], 1.0)
    faces = len(unroll(b).kind.faces)
    folds = int(unroll(b, 'folds').shape.split()[-1])
    assert folds < faces - 1                                              # a piece more for each fold less
    xs = np.asarray(unroll(b).values)[:, 0]
    assert np.ptp(xs) > 0                                                 # side by side, not on each other


def test_a_plan_in_a_cross_extrudes_as_a_body():
    b = body(PLANS["cross"], 2.0)
    assert surface(b) == pytest.approx(2 * 5 + 12 * 2.0)                   # two caps of 5 m2 and 12 walls of 1 × 2
