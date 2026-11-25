"""R4 (levels of variable size) and R5 (operating along a level), step 1.1b.

Each test is a case of the catalogue, only with numbers.
"""

import numpy as np
import pytest

from tensela.data import Data, ShapeError, accumulate, apply, pairs, position, reduce


def narrow_tower_what():
    """5 floors: 20 panels at the bottom, fewer and fewer above. Each panel measures 2.5 m²."""
    panels_by_floor = [20, 20, 18, 16, 12]
    return Data.from_lists([[2.5] * n for n in panels_by_floor], ("piso", "panel"), "áreas")


# --- R4: what a variable level is --------------------------------------------

def test_r4_the_shape_says_the_range():
    areas = narrow_tower_what()
    assert areas.shape == "piso 5 × panel 12…20 = 86"
    assert areas.count == 86


def test_r4_a_level_that_does_not_vary_stays_fixed():
    d = Data.from_lists([[1, 2, 3], [4, 5, 6]], ("fila", "columna"))
    assert d.variables == {}
    assert d.shape == "fila 2 × columna 3 = 6"


def test_r4_round_trip_to_lists():
    lists = [[1, 2, 3], [4, 5], [6]]
    assert Data.from_lists(lists, ("piso", "panel")).list_() == lists


def test_r4_points_as_elements():
    outlines = Data.from_lists(
        [[[0, 0, 0], [1, 0, 0], [1, 1, 0]], [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]]],
        ("celda", "vértice"), 'outlines',
    )
    assert outlines.shape == "celda 2 × vértice 3…4 = 7"
    assert outlines.shape_element == (3,)


def test_r4_an_empty_list_is_a_clear_error():
    with pytest.raises(ShapeError) as error:
        Data.from_lists([[1, 2], []], ("piso", "panel"), "paneles")
    assert str(error.value) == "«paneles» tiene una lista vacía de «panel» en «piso» 1."


# --- R4 with R1: combining variable data -------------------------------------

def test_r4_a_data_per_floor_repeats_in_its_panels():
    areas = narrow_tower_what()
    price_m2 = Data(np.array([100.0, 100, 120, 120, 150]), ("piso",), "precio por m²")
    cost = apply(np.multiply, areas, price_m2, name="coste")
    assert cost.shape == "piso 5 × panel 12…20 = 86"
    assert cost.list_()[4] == [375.0] * 12


def test_r4_two_equal_variable_data_pair():
    a = Data.from_lists([[1, 2, 3], [4, 5]], ("piso", "panel"), "a")
    b = Data.from_lists([[10, 20, 30], [40, 50]], ("piso", "panel"), "b")
    assert apply(np.add, a, b).list_() == [[11, 22, 33], [44, 55]]


def test_r4_different_sizes_in_a_floor_say_where():
    a = Data.from_lists([[1, 2, 3], [4, 5], [6, 7]], ("piso", "panel"), "a")
    b = Data.from_lists([[1, 2, 3], [4, 5], [6, 7, 8]], ("piso", "panel"), "b")
    with pytest.raises(ShapeError) as error:
        apply(np.add, a, b)
    assert str(error.value) == "No coinciden los tamaños de «panel» en «piso» 2: 2 en «a», 3 en «b»."


def test_r4_fixed_against_variable_is_an_error():
    variable = Data.from_lists([[1, 2, 3], [4, 5]], ("piso", "panel"), "variable")
    fixed = Data(np.zeros((2, 3)), ("piso", "panel"), "fijo")
    with pytest.raises(ShapeError, match="«panel» en «piso» 1: 2 en «variable», 3 en «fijo»"):
        apply(np.add, variable, fixed)


# --- R4 with R3: reducing variable data --------------------------------------

def test_r4_area_per_floor():
    by_floor = reduce(narrow_tower_what(), 'sum', along="panel")
    assert by_floor.shape == "piso 5"
    assert by_floor.list_() == [50.0, 50.0, 45.0, 40.0, 30.0]


def test_r4_tally_and_average_only_what_exists():
    d = Data.from_lists([[1.0, 2.0, 3.0], [10.0]], ("piso", "panel"))
    assert reduce(d, 'tally', along="panel").list_() == [3, 1]
    assert reduce(d, 'average', along="panel").list_() == [2.0, 10.0]
    assert reduce(d, 'maximum').values == 10.0
    assert reduce(d, 'minimum').values == 1.0
    assert reduce(d, 'tally').values == 4


def test_r4_removing_the_outer_level_leaves_the_inner_fixed():
    # Adding all the floors panel by panel: the result has as many panels as the biggest floor.
    d = Data.from_lists([[1, 2, 3], [10, 20]], ("piso", "panel"))
    by_panel = reduce(d, 'sum', along="piso")
    assert by_panel.shape == "panel 3"
    assert by_panel.list_() == [11, 22, 3]


# --- R4 with three levels: the window -----------------------------------------

def windows():
    """Window A: 2 leaves (2 and 4 panes). Window B: 3 leaves (1, 1 and 2 panes). Areas in m²."""
    return Data.from_lists(
        [
            [[0.5, 0.5], [0.25, 0.25, 0.25, 0.25]],
            [[0.8], [0.8], [0.4, 0.4]],
        ],
        ("ventana", "hoja", "vidrio"), "vidrios",
    )


def test_r4_window_three_levels():
    v = windows()
    assert v.shape == "ventana 2 × hoja 2…3 × vidrio 1…4 = 10"
    assert reduce(v, 'tally').values == 10


def test_r4_window_panes_per_leaf_and_area_per_window():
    v = windows()
    assert reduce(v, 'tally', along="vidrio").list_() == [[2, 4], [1, 1, 2]]
    assert reduce(v, 'sum', along=["hoja", "vidrio"]).list_() == pytest.approx([2.0, 2.4])


# --- R5: position, pairs, accumulate -------------------------------------------

def test_r5_tower_turning_three_degrees_per_floor():
    floors = Data(np.zeros(30), ("piso",), "pisos")
    rotation = apply(lambda p: p * 3.0, position(floors, "piso"), name="giro")
    assert rotation.list_()[:4] == [0.0, 3.0, 6.0, 9.0]
    assert rotation.list_()[-1] == 87.0


def test_r5_brick_wall_alternate_courses():
    """Courses of 10 and 11 pieces of 24 cm; the odd courses shift half a piece."""
    pieces_by_course = [10, 11, 10, 11]
    wall = Data.from_lists([[0.0] * n for n in pieces_by_course], ("hilada", "pieza"), "muro")
    length = 0.24
    odd = apply(lambda h: h % 2, position(wall, "hilada"))
    x = apply(lambda p, i: p * length - i * length / 2, position(wall, "pieza"), odd, name="x")

    assert x.shape == "hilada 4 × pieza 10…11 = 42"
    rows = x.list_()
    assert rows[0][:2] == pytest.approx([0.0, 0.24])
    assert rows[1][:2] == pytest.approx([-0.12, 0.12])
    assert len(rows[1]) == 11


def test_r5_beams_between_consecutive_columns():
    xx, yy = np.meshgrid(np.arange(5) * 6.0, np.arange(4) * 5.0, indexing="ij")
    columns = Data(np.stack([xx, yy, np.zeros_like(xx)], axis=-1), ("eje X", "eje Y"), "pilares")
    beams = pairs(columns, "eje X", name="vigas en X")
    assert beams.shape == "eje X 4 × eje Y 4 = 16"
    assert beams.shape_element == (2, 3)
    assert beams.list_()[0][0] == [[0.0, 0.0, 0.0], [6.0, 0.0, 0.0]]


def test_r5_sides_of_closed_outlines_of_different_length():
    outlines = Data.from_lists([[1, 2, 3], [4, 5, 6, 7]], ("celda", "vértice"), 'outlines')
    sides = pairs(outlines, "vértice", closed=True)
    assert sides.list_() == [
        [[1, 2], [2, 3], [3, 1]],
        [[4, 5], [5, 6], [6, 7], [7, 4]],
    ]


def test_r5_open_pairs_in_a_variable_level():
    d = Data.from_lists([[1, 2, 3], [4, 5]], ("piso", "panel"))
    assert pairs(d, "panel").list_() == [[[1, 2], [2, 3]], [[4, 5]]]


def test_r5_pairs_with_a_single_element_is_an_error():
    d = Data.from_lists([[1, 2], [3]], ("piso", "panel"), "paneles")
    with pytest.raises(ShapeError, match="al menos 2 elementos en «panel»"):
        pairs(d, "panel")


def test_r5_height_of_each_floor():
    heights = Data(np.array([4.5, 3.0, 3.0, 3.0]), ("piso",), "alturas")
    assert accumulate(heights, "piso").list_() == [4.5, 7.5, 10.5, 13.5]


def test_r5_grandstand_rows_of_different_length():
    """Each row rises 40 cm; the accumulated width of the seats of each row."""
    widths = Data.from_lists([[0.5] * 3, [0.5] * 5], ("fila", "asiento"), "anchos")
    assert accumulate(widths, "asiento").list_() == [[0.5, 1.0, 1.5], [0.5, 1.0, 1.5, 2.0, 2.5]]


def test_r5_going_along_a_level_others_depend_on_not_yet():
    areas = narrow_tower_what()
    with pytest.raises(ShapeError, match="el tamaño de «panel» cambia según «piso»"):
        accumulate(areas, "piso")


# --- Numbering: ground floor = 0, basements negative -------------------------

def building_with_basements():
    """2 basements, ground floor and 10 floors: from -2 to 10."""
    return Data(np.zeros(13), ("piso",), "pisos", starts={"piso": -2})


def test_numbering_ground_floor_is_zero():
    floors = Data(np.zeros(4), ("piso",), "pisos")
    assert position(floors, "piso").list_() == [0, 1, 2, 3]


def test_numbering_with_basements():
    floors = building_with_basements()
    assert floors.shape == "piso 13 (de -2 a 10)"
    assert position(floors, "piso").list_()[:4] == [-2, -1, 0, 1]


def test_turning_tower_the_basements_turn_the_other_way():
    rotation = apply(lambda p: p * 3.0, position(building_with_basements(), "piso"))
    assert rotation.list_()[:3] == [-6.0, -3.0, 0.0]


def test_numbering_is_kept_on_combining_and_reducing():
    floors = building_with_basements()
    panels = Data(np.ones((13, 8)), ("piso", "panel"), "paneles", starts={"piso": -2})
    together = apply(np.add, panels, floors)
    assert together.starts == {"piso": -2}
    assert reduce(together, 'sum', along="panel").shape == "piso 13 (de -2 a 10)"
    assert reduce(together, 'sum', along="piso").starts == {}


def test_different_numbering_is_a_clear_error():
    without_basements = Data(np.zeros(13), ("piso",), "plantas")
    with pytest.raises(ShapeError) as error:
        apply(np.add, building_with_basements(), without_basements)
    assert str(error.value) == "«piso» empieza en -2 en «pisos» y en 0 en «plantas»."


def test_the_errors_use_the_same_numbering():
    a = Data.from_lists([[1, 2], [3, 4], [5]], ("piso", "panel"), "a", starts={"piso": -1})
    b = Data.from_lists([[1, 2], [3], [5]], ("piso", "panel"), "b", starts={"piso": -1})
    with pytest.raises(ShapeError, match="en «piso» 0: 2 en «a», 1 en «b»"):
        apply(np.add, a, b)
