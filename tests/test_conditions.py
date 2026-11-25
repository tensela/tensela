"""Conditions: and / or / not in the Formula, if with several cases, Yes or no, Combine conditions, Choose,
Inside, and Filter «those that don't» (the Dispatch)."""
import numpy as np
import pytest

from tensela import geometry as geo
from tensela.project_file import open_
from tensela.data import ShapeError, combine_conditions, choose, filter_mode, series
from tensela.formula import formula
from tensela.graph import Graph
from tensela.measures import inside


def test_formula_in_spanish():
    a = series(6)
    assert formula("a > 2 y a < 5", a=a).values.tolist() == [False, False, False, True, True, False]
    assert formula("a < 1 o a > 4", a=a).values.tolist() == [True, False, False, False, False, True]
    assert formula("no(a > 2)", a=a).values.tolist() == [True, True, True, False, False, False]
    assert formula("si(a < 2; 0; a < 4; 1; 2)", a=a).values.tolist() == [0, 0, 1, 1, 2, 2]
    assert formula("phi").values == pytest.approx(1.6180339887)


def test_a_loose_y_still_warns_it_is_not_a_variable():
    with pytest.raises(ShapeError, match="no es una variable"):
        formula("a * y", a=series(3))


def test_if_with_an_even_number_of_values():
    with pytest.raises(ShapeError, match="Le llegan 4 valores"):
        formula("si(a < 2; 0; 1; 2)", a=series(3))


def test_combine_conditions():
    a = formula("a > 1", a=series(4))
    b = formula("a < 3", a=series(4))
    assert combine_conditions(a, b, 'and').values.tolist() == [False, False, True, False]
    assert combine_conditions(a, b, 'or').values.tolist() == [True, True, True, True]
    assert combine_conditions(a, b, 'only one').values.tolist() == [True, True, False, True]
    assert combine_conditions(a, None, 'not').values.tolist() == [True, True, False, False]
    with pytest.raises(ShapeError, match="conecta también «b»"):
        combine_conditions(a, None, 'and')


def test_choose_numbers_and_geometry():
    s = series(4)
    c = formula("a >= 2", a=s)
    assert choose(c, 10, 20).values.tolist() == [20, 20, 10, 10]
    panels = geo.move(geo.rectangle(1, 1), geo.point(s, 0, 0))
    open_ = geo.move(panels, (0, 0, 5))
    r = choose(c, open_, panels)
    assert r.kind == panels.kind
    assert r.values[..., 2].max(axis=-1).tolist() == [0, 0, 5, 5]


def test_choose_a_whole_variant():
    assert choose(True, geo.box(1, 1, 1), geo.circle(radius=1)).kind.name == "box"
    assert choose(False, geo.box(1, 1, 1), geo.circle(radius=1)).kind.curve


def test_choosing_different_shapes_per_element_warns():
    c = formula("a >= 2", a=series(4))
    with pytest.raises(ShapeError, match="dos Filtrar"):
        choose(c, geo.box(1, 1, 1), geo.circle(radius=1))


def test_inside_a_plan_and_a_volume():
    x, y, z = series(9, -3.5, 1, "x"), series(9, -3.5, 1, "y"), series(5, -1.5, 1, "z")
    assert int(inside(geo.point(x, y, 0), geo.rectangle(4, 3, origin=(-2, -1.5, 0))).values.sum()) == 12
    assert int(inside(geo.point(x, y, z), geo.box(4, 4, 2)).values.sum()) == 32
    # A geometry is tested by its centre.
    small_boxes = geo.move(geo.box(0.2, 0.2, 0.2), geo.point(x, 0, 0))
    assert int(inside(small_boxes, geo.circle(radius=2)).values.sum()) == 4
    with pytest.raises(ShapeError, match="curva abierta"):
        inside(geo.point(x, y, 0), geo.line((0, 0, 0), (1, 0, 0)))


def test_filter_those_that_do_not():
    s = series(4)
    c = formula("a >= 2", a=s)
    g = Graph()
    ns = g.node("Series", "s", count=4)
    nc = g.node("Formula", "c", formula="a >= 2", a=ns)
    g.node("Filter", "no", data=ns, condition=nc, keep="those that don't")
    assert g.value("no").mask.tolist() == [True, True, False, False]
    assert filter_mode(s, condition=c).mask.tolist() == [False, False, True, True]


def test_old_file_with_invert(tmp_path):
    filepath = tmp_path / "viejo.json"
    filepath.write_text('{"parametrico": 1, "nodos": {"s": {"tipo": "Serie", "cantidad": 3}, '
                    '"f": {"tipo": "Filtrar", "dato": {"nodo": "s"}, "modo": "cada", "invertir": true}}}',
                    encoding="utf-8")
    p = open_(filepath)
    assert p.graph.nodes["f"].inputs["keep"] == "those that don't"


def test_where_numbers_go_a_geometry_warns():
    """A point or a circle in a Formula, Function, Graph or Summarise: a warning, not a loose list."""
    for node, input_ in (("Formula", "a"), ("Function", "x"), ("Graph", "value"), ("Summarise", "data")):
        g = Graph()
        n = g.node(node)
        g.change(n, input_, g.node("Circle", radius=1))
        with pytest.raises(ShapeError, match="aquí van números"):
            g.value(n)
    g = Graph()
    points = g.node("Point", x=g.node("Series", count=4))
    assert g.value(g.node("Summarise", data=points, operation='average')).kind is not None
    assert g.value(g.node("Summarise", data=points, operation='tally')).values.item() == 4


def test_not_operation_saved_as_false_opens_the_same():
    """Choosing «not» from the list saved it as a yes/no (false): those files give «not» and hide «b»."""
    from tensela.nodes import visible_input
    g = Graph()
    a = g.node("Compare", a=g.node("Series", count=4), b=1, operation='greater')
    n = g.node("Combine conditions", a=a, operation=False)
    assert g.value(n).values.tolist() == [True, True, False, False]
    assert not visible_input(n, n.kind.input_("b"))
