"""The rules of DATOS.md, with the examples of case 01 (step 1.1a)."""

import numpy as np
import pytest

from tensela.data import Data, ShapeError, apply, reduce


def panels_centres(rows=12, columns=20, size_=1.0):
    """Centres of a facade on the XZ plane, panels of `size_` × `size_`."""
    x = (np.arange(columns) + 0.5) * size_
    z = (np.arange(rows) + 0.5) * size_
    zz, xx = np.meshgrid(z, x, indexing="ij")
    points = np.stack([xx, np.zeros_like(xx), zz], axis=-1)
    return Data(points, ("fila", "columna"), "centros")


def distance(a, b):
    return np.linalg.norm(a - b, axis=-1)


# --- What a data is -------------------------------------------------------

def test_the_shape_reads_in_words():
    assert panels_centres().shape == "fila 12 × columna 20 = 240"
    assert Data(np.zeros(30), ("piso",)).shape == "piso 30"
    assert Data.value(3.0).shape == "· (un valor)"
    assert Data(np.zeros((50, 40, 40)), ("piso", "eje X", "eje Y")).shape == (
        "piso 50 × eje X 40 × eje Y 40 = 80 000"
    )


def test_a_point_is_one_element():
    centres = panels_centres()
    assert centres.count == 240
    assert centres.shape_element == (3,)


def test_repeated_levels_is_an_error():
    with pytest.raises(ShapeError, match="niveles repetidos"):
        Data(np.zeros((2, 2)), ("fila", "fila"))


# --- R1: the single rule ---------------------------------------------------

def test_r1a_one_against_many():
    attractor = Data.value([5.0, 0.0, 3.0], "atractor")
    d = apply(distance, panels_centres(), attractor)
    assert d.levels == ("fila", "columna")
    assert d.shape == "fila 12 × columna 20 = 240"


def test_r1b_same_level_pairs():
    centres = panels_centres(rows=3, columns=4)
    angles = Data(np.arange(12.0).reshape(3, 4), ("fila", "columna"), "ángulos")
    together = apply(lambda c, a: a + 0 * c[..., 0], centres, angles)
    # Row 2, column 3 (indices 1, 2) receives its own angle, not another.
    assert together.values[1, 2] == angles.values[1, 2]


def test_r1b_the_order_of_the_levels_does_not_matter():
    angles = Data(np.arange(12.0).reshape(3, 4), ("fila", "columna"), "ángulos")
    transposed = Data(angles.values.T, ("columna", "fila"), "traspuestos")
    subtraction = apply(np.subtract, angles, transposed)
    assert np.all(subtraction.values == 0)


def test_r1c_a_level_only_one_has_repeats():
    strips = Data(np.zeros((3, 4, 3)), ("fila", "columna", "quiebrasol"), "franjas")
    angles = Data(np.arange(12.0).reshape(3, 4), ("fila", "columna"), "ángulos")
    sun_fins = apply(lambda f, a: f + a, strips, angles)
    assert sun_fins.shape == "fila 3 × columna 4 × quiebrasol 3 = 36"
    # The 3 sun fins of the panel (row 2, column 3) carry the angle of their panel.
    assert list(sun_fins.values[1, 2]) == [6.0, 6.0, 6.0]


def test_r1d_different_levels_cross():
    columns = Data(np.zeros((5, 4)), ("eje X", "eje Y"), "pilares")
    heights = Data(np.arange(6.0) * 3, ("piso",), "alturas")
    in_elevation = apply(np.add, columns, heights)
    assert in_elevation.count == 120
    assert in_elevation.sizes == {"eje X": 5, "eje Y": 4, "piso": 6}
    assert np.all(in_elevation.values[:, :, 2] == 6.0)


# --- R2: error claro ------------------------------------------------------

def test_r2_different_sizes_give_a_clear_error():
    centres = panels_centres(rows=12, columns=20)
    angles = Data(np.zeros((12, 10)), ("fila", "columna"), "ángulos")
    with pytest.raises(ShapeError) as error:
        apply(lambda c, a: a, centres, angles)
    assert str(error.value) == "No coinciden los tamaños de «columna»: 20 en «centros», 10 en «ángulos»."


def test_r2_without_a_name_it_says_which_input():
    with pytest.raises(ShapeError, match="2 en «entrada 1», 3 en «entrada 2»"):
        apply(np.add, Data(np.zeros(2), ("piso",)), Data(np.zeros(3), ("piso",)))


# --- R3: reduce by name -----------------------------------------------

def test_r3_maximum_of_all_gives_a_value():
    d = apply(distance, panels_centres(), Data.value([0.0, 0.0, 0.0]))
    maximum = reduce(d, 'maximum')
    assert maximum.shape == "· (un valor)"
    assert maximum.values == pytest.approx(np.hypot(19.5, 11.5))


def test_r3_sum_along_a_level_area_per_floor():
    areas = Data(np.full((30, 40), 2.5), ("piso", "panel"), "áreas")
    by_floor = reduce(areas, 'sum', along="panel")
    assert by_floor.shape == "piso 30"
    assert np.all(by_floor.values == 100.0)


def test_r3_tally():
    sun_fins = Data(np.zeros((12, 20, 3)), ("fila", "columna", "quiebrasol"))
    assert reduce(sun_fins, 'tally').values == 720
    assert np.all(reduce(sun_fins, 'tally', along="quiebrasol").values == 3)


def test_r3_a_level_that_does_not_exist_gives_a_clear_error():
    areas = Data(np.zeros((30, 40)), ("piso", "panel"), "áreas")
    with pytest.raises(ShapeError) as error:
        reduce(areas, 'sum', along='planta')
    assert str(error.value) == "«planta» no es un nivel de «áreas» (sus niveles: piso, panel)."


# --- Case 01 from end to end, only with numbers ------------------------

def test_case_01_facade_with_attractor():
    centres = panels_centres()                                  # paso 2
    attractor = Data.value([4.5, 0.0, 6.5], "atractor")              # paso 3
    distances = apply(distance, centres, attractor, name="distancias")  # paso 4
    maximum = reduce(distances, 'maximum')                          # step 5: max
    angles = apply(lambda d, m: 90.0 * (1 - d / m), distances, maximum,
                      name="ángulos")                             # paso 5: remapear

    assert angles.shape == "fila 12 × columna 20 = 240"
    # The panel where the attractor is (row 7, column 5) stays fully open.
    assert angles.values[6, 4] == pytest.approx(90.0)
    # The farthest stays closed.
    assert angles.values.min() == pytest.approx(0.0)


def test_case_01b_three_sun_fins_per_panel_inherit_the_angle():
    centres = panels_centres()
    distances = apply(distance, centres, Data.value([4.5, 0.0, 6.5]))
    angles = apply(lambda d, m: 90.0 * (1 - d / m), distances, reduce(distances, 'maximum'))

    offsets = Data(np.array([-1 / 3, 0.0, 1 / 3]), ("quiebrasol",), "desfases")
    positions_x = apply(lambda c, d: c[..., 0] + d, centres, offsets)
    sun_fins = apply(lambda x, a: np.stack([x, a], axis=-1), positions_x, angles)

    assert sun_fins.shape == "fila 12 × columna 20 × quiebrasol 3 = 720"
    # The 3 sun fins of the attractor's panel: different positions, same angle 90°.
    panel = sun_fins.values[6, 4]
    assert list(panel[:, 0]) == pytest.approx([4.5 - 1 / 3, 4.5, 4.5 + 1 / 3])
    assert list(panel[:, 1]) == pytest.approx([90.0, 90.0, 90.0])


# --- Oversized sizes: a warning before freezing the window ---------------------------

def test_an_oversized_crossing_warns_before_computing():
    from tensela.data import series
    a, b = series(5000, level="eje X"), series(5000, level="eje Y")
    with pytest.raises(ShapeError, match="tendría 25 000 000 elementos .eje X 5 000 × eje Y 5 000."):
        apply(np.add, a, b)


def test_an_oversized_series_warns():
    from tensela.data import series
    with pytest.raises(ShapeError, match="La serie tendría 10 000 000 elementos"):
        series(10_000_000, level="piso")


def test_an_oversized_grid_warns():
    from tensela.geometry import rectangle, grid
    with pytest.raises(ShapeError, match="La retícula tendría"):
        grid(rectangle(10, 10), columns=5000, rows=5000)
