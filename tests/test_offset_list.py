"""Offset curve with several distances: one outline for each distance, combined with the curves by their levels (a
Series of 4 distances and one curve: four outlines; the same level: each curve with its own distance)."""
import numpy as np
import pytest

from tensela.graph import Graph


def _span(values):
    return float(np.ptp(np.asarray(values)[..., 0]))


def test_a_series_of_distances_gives_one_outline_each():
    g = Graph()
    plan = g.node("Circle", "plan", radius=5)
    steps = g.node("Series", "steps", count=4, start=0.5, step=0.5, level="ring")
    g.node("Offset curve", "rings", curve=plan, distance=steps)
    rings = g.value("rings")
    assert rings.levels == ("ring",) and rings.sizes == {"ring": 4}
    widths = [_span(rings.values[i]) for i in range(4)]
    assert widths == pytest.approx([11, 12, 13, 14], rel=0.01)


def test_the_same_level_pairs_each_curve_with_its_distance():
    g = Graph()
    radii = g.node("Series", "radii", count=2, start=2.5, step=2, level="plan")
    gaps = g.node("Series", "gaps", count=2, start=0.5, step=1, level="plan")
    plans = g.node("Circle", "plans", radius=radii)
    g.node("Offset curve", "outlines", curve=plans, distance=gaps)
    out = g.value("outlines")
    assert len(out.levels) == 1 and out.count == 2
    assert [_span(out.values[i]) for i in range(2)] == pytest.approx([6, 12], rel=0.01)   # 2 × (2.5 + 0.5), 2 × (4.5 + 1.5)


def test_one_distance_works_as_before():
    g = Graph()
    plan = g.node("Circle", "plan", radius=5)
    g.node("Offset curve", "ring", curve=plan, distance=1)
    assert _span(g.value("ring").values) == pytest.approx(12, rel=0.01)
