"""Odd values in the inputs give a notice written for the user, not Python's own text (the «generic» findings of
`tools/performance.py extremes`)."""
import pytest

from tensela.data import ShapeError
from tensela.graph import Graph, NodeError


def _notice(g: Graph, name: str) -> NodeError:
    with pytest.raises(NodeError) as error:
        g.value(name)
    cause = error.value.__cause__
    assert isinstance(cause, ShapeError), f"{type(cause).__name__}: {error.value}"
    return error.value


def test_letters_where_the_points_of_a_drawn_curve_go():
    g = Graph()
    g.node("Drawn curve", "c", points="x")
    text = str(_notice(g, "c"))
    assert "list of points" in text or "lista de puntos" in text


def test_letters_where_a_number_goes():
    g = Graph()
    g.node("Box", "b", width="abc")
    assert "abc" in str(_notice(g, "b"))


def test_a_list_inside_the_list_of_a_number():
    g = Graph()
    g.node("Number", "n", value=[[0, 0, 0], [0, 0, 0]])
    _notice(g, "n")


def test_a_negative_whole_power_in_a_formula():
    g = Graph()
    g.node("Formula", "f", formula="a ** b", a=2, b=-1)
    assert float(g.value("f").values) == 0.5


def test_an_empty_centre_for_the_sun():
    g = Graph()
    g.node("Sun", "s", centre=())
    _notice(g, "s")


def test_a_single_number_as_the_direction_to_orient():
    g = Graph()
    g.node("Box", "b")
    g.node("Point", "p")
    g.node("Orient", "o", geometry=g.nodes["b"], to=g.nodes["p"], to_direction=0)
    _notice(g, "o")


def test_a_flat_box_has_nothing_to_unroll():
    g = Graph()
    g.node("Box", "b", height=0)
    g.node("Unroll", "u", geometry=g.nodes["b"])
    _notice(g, "u")


@pytest.mark.parametrize("smoothing", [0, -1, 1000])
def test_a_smoothing_out_of_range_in_a_topology_optimization(smoothing):
    from tensela.topology import _check
    with pytest.raises(ShapeError, match="smoothing|suavizado"):
        _check('concrete C25/30', 0.4, 60, 10, 0.3, (0, 0, -1), smoothing)
    _check('concrete C25/30', 0.4, 60, 10, 0.3, (0, 0, -1), 1.5)


def test_compare_with_points_says_so():
    g = Graph()
    g.node("Point", "p")
    g.node("Compare", "c", a=g.nodes["p"], b=1)
    _notice(g, "c")


