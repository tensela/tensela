"""Formula, Series and Scale (Delivery 3, E3.1)."""

import re

import numpy as np
import pytest

from tensela.data import Data, ShapeError, series
from tensela.formula import formula, prepare
from tensela.geometry import box, scale, point, rectangle
from tensela.graph import Graph


def floors(n=5):
    return series(n, level="piso")


# --- Formula -----------------------------------------------------------------

def test_as_in_a_spreadsheet():
    assert prepare("=SI(a<5;1;0)") == "SI(a<5,1,0)"
    assert prepare("a * 3,5") == "a * 3.5"
    assert formula("a * 3,5", a=floors()).list_() == [0.0, 3.5, 7.0, 10.5, 14.0]
    assert formula("a * 3.5", a=floors()).list_() == [0.0, 3.5, 7.0, 10.5, 14.0]


def test_variables_combine_by_the_single_rule():
    rows = series(3, level="fila")
    r = formula("a * 10 + b", a=rows, b=floors(2))
    assert r.shape == "fila 3 × piso 2 = 6"
    assert r.list_() == [[0.0, 1.0], [10.0, 11.0], [20.0, 21.0]]


def test_angles_in_degrees():
    assert formula("sen(30)").values == pytest.approx(0.5)
    assert formula("cos(a)", a=180).values == pytest.approx(-1)
    assert formula("atan(1)").values == pytest.approx(45)


def test_conditions_and_functions():
    assert formula("si(a < 2; 90; 0)", a=floors()).list_() == [90, 90, 0, 0, 0]
    assert formula("max(a; 2)", a=floors()).list_() == [2, 2, 2, 3, 4]
    assert formula("raiz(a)", a=16).values == 4
    assert formula("redondear(a / 3)", a=floors()).list_() == [0, 0, 1, 1, 1]
    assert formula("2 ^ 3").values == 8


def test_equal_and_different_as_in_a_spreadsheet():
    assert formula("si(a = 1; 10; 0)", a=floors(3)).list_() == [0, 10, 0]
    assert formula("si(a <> 1; 10; 0)", a=floors(3)).list_() == [10, 0, 10]
    assert formula("si(a >= 1; 1; 0)", a=floors(3)).list_() == [0, 1, 1]


def test_a_formula_without_variables_is_a_value():
    assert formula("2 * pi").shape == "· (un valor)"


@pytest.mark.parametrize('text, message', [
    ("a *", "No entiendo la fórmula «a *»"),
    ("x + 1", "«x» no es una variable de la fórmula"),
    ("abrir(a)", "La fórmula usa «abrir», que no conozco"),
    ("2a + 1", "para multiplicar escribe «2 * a»"),
    ("(a + 1", "Falta cerrar 1 paréntesis"),
    ("seno(a)", "¿quisiste decir «sen»?"),
    ("A * 2", "las variables van en minúscula"),
    ("si(a > 2; 1)", "Le llegan 2 valores"),
    ("a / (a - 1)", "seguramente se divide por 0"),
    ("a.real", "tiene algo que no se puede calcular"),
    ("'hola'", "solo van números"),
    ("", "La fórmula está vacía"),
])
def test_clear_errors(text, message):
    with pytest.raises(ShapeError, match=re.escape(message)):
        formula(text, a=1)


def test_empty_variable():
    with pytest.raises(ShapeError, match="usa «b», pero «b» está vacía"):
        formula("a + b", a=1)


def test_does_not_run_code():
    for dangerous in ("__import__('os').system('ls')", "open('x')", "(lambda: 1)()", "[1, 2]"):
        with pytest.raises(ShapeError):
            formula(dangerous)


def test_formula_as_a_node_in_a_graph():
    g = Graph()
    p = g.node("Series", "pisos", count=4, level="piso")
    g.node("Formula", "cotas", formula="a * 3,5", a=p)
    assert g.value("cotas").list_() == [0.0, 3.5, 7.0, 10.5]


# --- Serie ----------------------------------------------------------------------

def test_series_creates_a_level():
    s = series(4, start=10, step=0.5, level="peldaño")
    assert s.shape == "peldaño 4" and s.list_() == [10.0, 10.5, 11.0, 11.5]


def test_series_of_floors_with_basements_numbers_the_same():
    s = series(13, start=-2, level="piso")
    assert s.shape == "piso 13 (de -2 a 10)"
    assert s.list_()[2] == 0  # the ground floor


def test_badly_asked_series():
    with pytest.raises(ShapeError, match="1 o más"):
        series(0)


def test_a_count_with_decimals_is_rounded():
    # As in Grasshopper: a count that comes from a Formula (a / 3) works the same.
    from tensela.geometry import circle, curve_points
    assert series(4.4).shape.startswith("elemento 4") and series(4.6).shape.startswith("elemento 5")
    assert curve_points(circle(radius=1.0), 72.4).shape == "punto 72"


# --- Escalar -------------------------------------------------------------------------

def test_scale_about_its_own_centre():
    c = scale(box(2, 2, 2), 0.5)
    assert c.values.max(axis=0) == pytest.approx([0.5, 0.5, 0.5])


def test_scale_about_a_point():
    r = scale(rectangle(4, 4), 0.5, centre=(0, 0, 0))
    assert r.values.max(axis=0) == pytest.approx([2, 2, 0])


def test_a_factor_per_floor():
    slabs = scale(box(10, 10, 0.3), Data(np.array([1.0, 0.5]), ("piso",)))
    assert slabs.shape == "piso 2"
    assert (slabs.values[1].max(axis=0) - slabs.values[1].min(axis=0))[0] == pytest.approx(5)


def test_scaling_a_point_about_itself_does_not_move_it():
    assert scale(point(3, 4, 5), 2).values == pytest.approx([3, 4, 5])


# --- The example of the turning tower ---------------------------------------------------

def test_turning_tower():
    from pathlib import Path
    from tensela.project_file import open_
    p = open_(Path(__file__).parent / "data" / "torre_que_gira.json")
    g = p.graph
    slabs = g.value('slabs')
    assert slabs.shape == "piso 30"
    level_marks = [v.min(axis=0)[2] for v in slabs.values]
    assert level_marks[1] == pytest.approx(3.5) and level_marks[29] == pytest.approx(29 * 3.5)
    width = lambda v: np.linalg.norm(v[1] - v[0])  # side of the slab (corner 0 → 1)
    assert width(slabs.values[0]) == pytest.approx(24)
    assert width(slabs.values[29]) < width(slabs.values[0])  # it tapers
    g.change('floors', "count", 10)
    assert g.value('glass').shape == "piso 10"


def test_more_variables_e_to_h():
    assert formula("a + e + h", a=1, e=10, h=100).values == 111


def test_variables_e_to_h_appear_when_used():
    from tensela.nodes import visible_input
    g = Graph()
    n = g.node("Formula", "cuenta", formula="a * 2")
    visible = lambda: [e.name for e in n.kind.inputs if visible_input(n, e)]  # noqa: E731
    assert visible() == ["formula", "a", "b", "c", "d"]
    g.change(n, "formula", "a * e + g")
    assert visible() == ["formula", "a", "b", "c", "d", "e", "g"]
    g.change(n, "formula", "a")      # «e» is no longer used…
    g.change(n, "f", 3)              # …but «f» has a value: it is seen
    assert "f" in visible() and "e" not in visible()


def test_pick_several_ranges_and_negatives():
    import numpy as np
    from tensela.geometry import line, curve_points
    from tensela.data import pick
    p = curve_points(line((0, 0, 0), (20, 0, 0)), 6)                 # x = 0, 4, 8, 12, 16, 20
    x = lambda d: np.round(d.values.reshape(-1, 3)[:, 0], 6).tolist()
    assert pick(p, "point", 3).levels == () and x(pick(p, "point", 3)) == [12]   # one: without level
    assert x(pick(p, "point", -1)) == [20] and x(pick(p, "point", "último")) == [20]
    assert x(pick(p, "point", "1; 5; 3")) == [4, 20, 12]                       # in that order
    assert x(pick(p, "point", "2-4")) == [8, 12, 16] and x(pick(p, "point", "4-2")) == [16, 12, 8]
    assert pick(p, "point", "2-4").levels == ("point",)
    assert x(pick(p, "point", [0, 5])) == [0, 20]
    with pytest.raises(ShapeError, match="no existe"):
        pick(p, "point", "2; 9")


def test_reorder_invert_shift_sort():
    import numpy as np
    from tensela.data import reorder
    from tensela.geometry import distance, line, point, curve_points
    s = series(5, 0, 1, "p")
    assert reorder(s, "p").values.tolist() == [4, 3, 2, 1, 0]
    assert reorder(s, "p", 'shift', 2).values.tolist() == [2, 3, 4, 0, 1]
    assert reorder(s, "p", 'shift', 2, False).values.tolist() == [2, 3, 4]       # without wrapping round
    assert reorder(s, "p", 'shift', -1).values.tolist() == [4, 0, 1, 2, 3]
    assert reorder(series(4, 9, -2, "p"), "p", 'sort').values.tolist() == [3, 5, 7, 9]
    p = curve_points(line((0, 0, 0), (10, 0, 0)), 5)
    near = reorder(p, "point", 'sort', key=distance(p, point(7, 0, 0)))
    assert np.allclose(near.values[:, 0], [7.5, 5, 10, 2.5, 0])                         # the nearest, first
    assert np.allclose(reorder(line((0, 0, 0), (5, 0, 0))).values, [[5, 0, 0], [0, 0, 0]])   # the direction
    with pytest.raises(ShapeError, match="clave"):
        reorder(p, "point", 'sort')


def test_filter_by_pattern_and_every():
    from tensela.data import filter_mode
    s = series(10, 0, 1, "p")
    assert filter_mode(s, 'pattern').values.tolist() == [0, 2, 4, 6, 8]                  # yes; no
    assert filter_mode(s, 'pattern', pattern="sí; no; no").values.tolist() == [0, 3, 6, 9]
    assert filter_mode(s, 'pattern', pattern="x..").values.tolist() == [0, 3, 6, 9]
    assert filter_mode(s, 'every', every=3, from_=1).values.tolist() == [1, 4, 7]
    assert filter_mode(s, 'pattern', reverse=True).values.tolist() == [1, 3, 5, 7, 9]
    empty = filter_mode(s, 'pattern', remove=False)                                     # without removing: holes
    assert empty.sizes["p"] == 10 and empty.holes.tolist()[:4] == [False, True, False, True]
    with pytest.raises(ShapeError, match="sí y no"):
        filter_mode(s, 'pattern', pattern="quizás")
    with pytest.raises(ShapeError, match='condición'):
        filter_mode(s, 'condition')


def test_split_into_groups_and_pick_ranges_with_words():
    from tensela.data import pick, split
    s = series(10, 0, 1, "p")
    g = split(s, "p", 'groups of', 4)
    assert g.levels == ("group", "p") and g.values.tolist()[:2] == [[0, 1, 2, 3], [4, 5, 6, 7]]
    assert g.holes.tolist()[2] == [False, False, True, True]                           # the last, with holes
    assert split(series(12, 0, 1, "p"), None, 'in parts', 3).shape == "grupo 3 × p 4 = 12"
    assert pick(s, "p", "4-último").values.tolist() == [4, 5, 6, 7, 8, 9]            # split in two
    assert pick(s, "p", "-3--1").values.tolist() == [7, 8, 9]
    with pytest.raises(ShapeError, match="nombre"):
        split(s, "p", 'groups of', 2, "p")


def test_a_geometry_where_a_number_goes_gives_a_clear_warning():
    from tensela.graph import NodeError, Graph
    g = Graph()
    g.node("Point", "p", x=3)
    g.node("Line", "l", from_=(0, 0, 0), to=(5, 0, 0))
    g.node("Points on curve", "pc", curve=g.nodes["l"], count=g.nodes["p"])
    with pytest.raises(NodeError, match="un solo número"):
        g.value("pc")


def test_in_english_if_and_or_not():
    a = Data.value(np.array([3.0, 10.0, 20.0]))
    assert formula("if(a < 7; 3; a < 16; 4,5; 6)", a=a).values.tolist() == [3, 4.5, 6]
    assert formula("if(a > 5 and a < 20; 1; 0)", a=a).values.tolist() == [0, 1, 0]
    assert formula("if(a < 5 or not(a < 15); 1; 0)", a=a).values.tolist() == [1, 0, 1]
