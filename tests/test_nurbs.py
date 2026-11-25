"""The NURBS Curve: degree, weights, knots (uniform, chord length, by hand) and closed."""
import numpy as np
import pytest

from tensela import geometry as geo
from tensela.data import Data, ShapeError
from tensela.graph import Graph


def points(list_, levels=("punto",)):
    return Data(np.array(list_, dtype=float), levels, "control", kind=geo.POINT)


SQUARE = [[1, 0, 0], [1, 1, 0], [0, 1, 0], [-1, 1, 0], [-1, 0, 0], [-1, -1, 0], [0, -1, 0], [1, -1, 0], [1, 0, 0]]


def test_an_exact_circle_with_weights_and_knots_by_hand():
    s = np.sqrt(0.5)
    c = geo.curve_nurbs(points(SQUARE), degree=2, weights=[1, s, 1, s, 1, s, 1, s, 1], knots='by hand',
                        items_nodes="0,25; 0,25; 0,5; 0,5; 0,75; 0,75")
    assert np.linalg.norm(c.values[:, :2], axis=1) == pytest.approx(1.0)
    # The complete vector (as Grasshopper gives it) gives the same curve.
    d = geo.curve_nurbs(points(SQUARE), degree=2, weights=[1, s, 1, s, 1, s, 1, s, 1], knots='by hand',
                        items_nodes=[0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 4])
    assert d.values == pytest.approx(c.values)


def test_starts_and_ends_at_its_end_points():
    for mode in ('uniform', 'chord length', 'square root of chord'):
        c = geo.curve_nurbs(points([[0, 0, 0], [1, 3, 0], [4, 3, 0], [6, 0, 1]]), knots=mode)
        assert c.values[0] == pytest.approx([0, 0, 0]) and c.values[-1] == pytest.approx([6, 0, 1])
        assert c.kind is geo.CURVE


def test_degree_1_is_the_polyline_and_the_degree_is_limited():
    p = [[0, 0, 0], [2, 0, 0], [2, 2, 0]]
    c = geo.curve_nurbs(points(p), degree=1)
    assert any(np.allclose(v, [2, 0, 0]) for v in c.values)        # it passes through the corner
    height = geo.curve_nurbs(points(p), degree=7)                       # with 3 points, at most degree 2
    assert height.values == pytest.approx(geo.curve_nurbs(points(p), degree=2).values)


def test_a_big_weight_brings_the_curve_closer():
    p = points([[0, 0, 0], [1, 2, 0], [2, 0, 0]])
    normal = geo.curve_nurbs(p, degree=2).values[:, 1].max()
    near = geo.curve_nurbs(p, degree=2, weights="1; 10; 1").values[:, 1].max()
    assert normal == pytest.approx(1.0) and near > 1.8


def test_closed_without_break():
    c = geo.curve_nurbs(points(SQUARE[:-1]), degree=3, closed=True)
    assert c.kind is geo.CLOSED_CURVE and c.values[0] == pytest.approx(c.values[-1])
    tangent_start, tangent_end = c.values[1] - c.values[0], c.values[-1] - c.values[-2]
    assert np.dot(tangent_start, tangent_end) > 0


def test_a_curve_per_row():
    v = np.random.default_rng(1).random((4, 6, 3))
    c = geo.curve_nurbs(Data(v, ("fila", "punto"), "m", kind=geo.POINT), knots='chord length')
    assert c.levels == ("fila",) and c.values.shape[0] == 4


def test_warnings():
    p = points([[0, 0, 0], [1, 1, 0], [2, 0, 0], [3, 1, 0]])
    with pytest.raises(ShapeError, match="pesos"):
        geo.curve_nurbs(p, weights=[1, 2])
    with pytest.raises(ShapeError, match="mayores que 0"):
        geo.curve_nurbs(p, weights=[1, 0, 1, 1])
    with pytest.raises(ShapeError, match="van 0 nudos por dentro"):
        geo.curve_nurbs(p, degree=3, knots='by hand', items_nodes="0,5")
    with pytest.raises(ShapeError, match="de menor a mayor"):
        geo.curve_nurbs(p, degree=2, knots='by hand', items_nodes="1,5")
    with pytest.raises(ShapeError, match="escribe la lista"):
        geo.curve_nurbs(p, knots='by hand')


def test_in_the_graph():
    g = Graph()
    x = g.node("Series", "x", count=5, level="punto")
    y = g.node("Formula", "y", formula="si(a > 2; 2; 0)", a=x)
    control = g.node("Point", "control", x=x, y=y)
    curve = g.node("NURBS Curve", "curva", points=control, weights="1; 1; 4; 1; 1")
    assert g.value(curve).kind is geo.CURVE


def test_drawn_points_with_their_weight():
    normal = geo.curve_nurbs([[0, 0], [1, 2, 0], [2, 0, 0]], degree=2)
    with_weight = geo.curve_nurbs([[0, 0], [1, 2, 0, 10], [2, 0, 0]], degree=2)
    assert with_weight.values[:, 1].max() > normal.values[:, 1].max() + 0.5
    # the node's «weights» multiplies with that of each point: all by 3 does not change the curve.
    assert geo.curve_nurbs([[0, 0], [1, 2, 0, 10], [2, 0, 0]], degree=2, weights=3).values == pytest.approx(
        with_weight.values)
    with pytest.raises(ShapeError, match="Editar curva"):
        geo.curve_nurbs([], name="perfil")


def test_it_is_drawn_if_its_points_do_not_come_from_another_node():
    from tensela.graph import drawable
    from tensela.nodes import node_kind
    g = Graph()
    single = g.node("NURBS Curve", "sola")
    assert drawable(single)
    p = g.node("Point", "p", x=1)
    connected = g.node("NURBS Curve", "conectada", points=p)
    assert not drawable(connected)
    assert [e.name for e in node_kind("Curva NURBS").inputs if e.advanced] == ["knots", "list"]


def test_one_more_point_on_the_curve_does_not_change_its_shape():
    """Click on the curve in the editor: knot insertion (Boehm), exact with the previous knots plus the new one."""
    from tensela.geometry import _base_bspline, _open_nodes, insert_node
    rng = np.random.default_rng(0)
    p, w, k = rng.random((7, 3)) * 10, rng.random(7) + 0.5, 3
    knots = _open_nodes(p, k, "uniformes", np.zeros(0))
    p2, w2 = insert_node(p, w, k, knots, 0.37)
    knots2 = np.sort(np.append(knots, 0.37))
    t = np.linspace(0, 1, 200)

    def curve(p, w, knots):
        b = _base_bspline(knots, k, t)
        return (b @ (p * w[:, None])) / (b @ w)[:, None]
    assert len(p2) == 8 and np.allclose(curve(p, w, knots), curve(p2, w2, knots2))


def test_the_crossing_box_takes_the_spans_it_touches():
    from tensela.ui.drawing import _in_box, _run_touches_box
    box = (4, 4, 6, 6)
    assert _in_box((5, 5), box) and not _in_box((7, 5), box)
    assert _run_touches_box((0, 5), (10, 5), box)          # it crosses it without having points inside
    assert not _run_touches_box((0, 0), (10, 1), box)


# --- The pen (C3) -----------------------------------------------------------------------

STROKE = [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0],            # esquina
         [5, 5, 0, 3, 5, 0, 7, 5, 0, 1],            # suave
         [10, 0, 0, 10, 0, 0, 10, 0, 0, 0]]         # esquina


def test_the_pen_passes_through_its_anchors():
    from tensela.graph import Graph
    g = Graph()
    g.node("NURBS Curve", "c", mode='pen', stroke=STROKE)
    v = g.value("c").values
    assert np.allclose(v[0], [0, 0, 0]) and np.allclose(v[-1], [10, 0, 0])
    assert np.min(np.linalg.norm(v - [5, 5, 0], axis=1)) < 1e-9          # it passes through the middle anchor
    g.change("c", "closed", True)
    v = g.value("c")
    assert v.kind.name == "closed curve" and np.allclose(v.values[0], v.values[-1])


def test_a_span_without_handles_is_straight():
    from tensela.geometry import drawn_anchors, pen
    a, e, s, _ = drawn_anchors([[0, 0, 0], [4, 2, 0]])               # without handles (corners)
    v = pen(a, e, s)
    assert np.allclose(np.cross(v - v[0], [4, 2, 0])[:, 2], 0)


def test_splitting_a_span_does_not_change_the_shape():
    from tensela.geometry import drawn_anchors, split_run
    a, e, s, t = drawn_anchors(STROKE)
    a2, e2, s2, t2 = split_run(a, e, s, t, 0, 0.4)

    def bez(p0, p1, p2, p3, u):
        u = u[:, None]
        return (1 - u) ** 3 * p0 + 3 * u * (1 - u) ** 2 * p1 + 3 * u ** 2 * (1 - u) * p2 + u ** 3 * p3
    u = np.linspace(0, 1, 101)
    assert len(a2) == 4 and t2[1] == 1
    assert np.allclose(bez(a2[0], s2[0], e2[1], a2[1], u), bez(a[0], s[0], e[1], a[1], 0.4 * u))
    assert np.allclose(bez(a2[1], s2[1], e2[2], a2[2], u), bez(a[0], s[0], e[1], a[1], 0.4 + 0.6 * u))


def test_the_pen_without_stroke_warns_and_the_control_points_go_on():
    from tensela.graph import NodeError, Graph
    g = Graph()
    g.node("NURBS Curve", "c", mode='pen', points=[[0, 0, 0], [1, 1, 0], [2, 0, 0]])
    with pytest.raises(NodeError, match="trazo"):
        g.value("c")
    g.change("c", "mode", "puntos de control")                         # the control points were not lost
    assert g.value("c").kind.name == "curve"


def test_the_curvature_comb():
    from tensela.geometry import curvature_comb
    t = np.linspace(0, 2 * np.pi, 200)
    bases, tips = curvature_comb(np.column_stack([5 * np.cos(t), 5 * np.sin(t), 0 * t]), length=1.0)
    lengths = np.linalg.norm(tips - bases, axis=1)
    assert np.ptp(lengths) < 1e-3 and np.all(np.linalg.norm(tips[:, :2], axis=1) > 5)   # iguales, hacia fuera
    bases, tips = curvature_comb(np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0.0]]))
    assert np.allclose(bases, tips)                                                     # straight: without hairs


def test_inserting_a_knot_by_hand_does_not_change_the_curve():
    """The knot strip: double-click inserts a knot (and a control point); with the knots «by hand», exact."""
    from tensela.geometry import _open_nodes, insert_node, points_in_nurbs
    p = np.array([[0, 0, 0], [3, 5, 0], [6, -1, 0], [9, 4, 0], [12, 0, 0]], float)
    w, k = np.ones(5), 3
    knots = _open_nodes(p, k, 'by hand', np.array([0.55]))
    p2, w2 = insert_node(p, w, k, knots, 0.8)
    knots2 = _open_nodes(p2, k, 'by hand', np.array([0.55, 0.8]))
    t = np.linspace(0, 1, 300)
    assert np.allclose(points_in_nurbs(p, w, k, knots, t), points_in_nurbs(p2, w2, k, knots2, t))


def test_the_comb_of_several_curves_has_a_single_scale():
    """«See the curvature» in the panel: several curves with the same scale (the tightest, the longest hairs)."""
    from tensela.geometry import curvature_comb
    t = np.linspace(0, 2 * np.pi, 100)
    hoops = np.stack([np.column_stack([r * np.cos(t), r * np.sin(t), 0 * t + z]) for r, z in ((4, 0), (2, 5))])
    bases, tips = curvature_comb(hoops)
    lengths = np.linalg.norm(tips - bases, axis=1)
    half = len(lengths) // 2
    assert lengths[half:].mean() == pytest.approx(2 * lengths[:half].mean(), rel=0.01)   # radio mitad: doble


def test_removing_an_inserted_knot_gives_back_the_previous_curve():
    from tensela.geometry import _open_nodes, insert_node, remove_node
    p = np.array([[0, 0, 0], [3, 5, 0], [6, -1, 0], [9, 4, 0], [12, 0, 0]], float)
    w, k = np.array([1, 2, 1, 0.5, 1.0]), 3
    knots = _open_nodes(p, k, 'by hand', np.array([0.55]))
    p2, w2 = insert_node(p, w, k, knots, 0.8)
    p3, w3 = remove_node(p2, w2, k, _open_nodes(p2, k, 'by hand', np.array([0.55, 0.8])), 1)
    assert np.allclose(p3, p) and np.allclose(w3, w)
