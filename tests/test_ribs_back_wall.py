"""Ribs whose shape crosses the back wall: a notice that says so and where to move the wall, instead of a
misleading one about curves that enclose no area."""
import pytest

from tensela.graph import Graph, NodeError


def _wall(g, depth):
    bottom = g.node("Drawn curve", "bottom", points=[[0, depth, 0], [2, depth - 0.4, 0], [4, depth, 0]])
    top = g.node("Drawn curve", "top", points=[[0, depth, 0], [2, depth + 0.3, 0], [4, depth, 0]])
    up = g.node("Move", "up", geometry=top, distance=2)
    sections = g.node("Merge", "sections", a=bottom, b=up, level="section")
    return g.node("Loft", "front", curves=sections, along="section")


def test_a_shape_across_the_wall_says_so():
    g = Graph()
    g.node("Ribs", "ribs", shape=_wall(g, -0.2), count=5, weight=0.04, back=0)
    with pytest.raises(NodeError) as notice:
        g.value("ribs")
    text = str(notice.value)
    assert "back wall" in text or "pared de atrás" in text


def test_a_shape_in_front_of_the_wall_works():
    g = Graph()
    g.node("Ribs", "ribs", shape=_wall(g, -0.6), count=5, weight=0.04, back=0)
    assert g.value("ribs").count == 5


def test_the_suggested_wall_works_as_it_is_written():
    import re
    g = Graph()
    g.node("Ribs", "ribs", shape=_wall(g, -0.2), count=5, weight=0.04, back=0)
    with pytest.raises(NodeError) as notice:
        g.value("ribs")
    suggested = float(re.findall(r"-?\d+\.\d+", str(notice.value).replace(",", "."))[-1])
    g.change("ribs", "back", suggested)
    assert g.value("ribs").count == 5
