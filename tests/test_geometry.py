"""Minimal geometry (step 1.2): point, rectangle, grid, box, rotate, move, place."""

import numpy as np
import pytest

from tensela.data import Data, ShapeError, reduce
from tensela.geometry import (
    BOX, POINT, RECTANGLE, box, centre, place, distance, divide, rotate, move,
    point, rectangle, remap, grid,
)


def extension(vertices):
    """Size of the element in X, Y and Z."""
    v = np.asarray(vertices)
    return v.max(axis=0) - v.min(axis=0)


# --- Crear -------------------------------------------------------------------

def test_loose_point():
    p = point(1, 2, 3)
    assert p.kind == POINT
    assert p.list_() == [1.0, 2.0, 3.0]


def test_points_from_coordinates_with_levels():
    x = Data(np.arange(3.0), ("columna",))
    z = Data(np.arange(2.0) * 3, ("fila",))
    p = point(x, 0, z)
    assert p.shape == "columna 3 × fila 2 = 6"
    assert p.list_()[2][1] == [2.0, 0.0, 3.0]


def test_rectangle_in_elevation():
    r = rectangle(20, 12, plane='elevation', name="fachada")
    assert r.kind == RECTANGLE
    assert r.list_() == [[0, 0, 0], [20, 0, 0], [20, 0, 12], [0, 0, 12]]


def test_rectangle_in_plan_with_origin():
    r = rectangle(4, 3, origin=(1, 1, 0))
    assert r.list_() == [[1, 1, 0], [5, 1, 0], [5, 4, 0], [1, 4, 0]]


def test_unknown_plane():
    with pytest.raises(ShapeError, match="Opciones: planta, alzado, lateral"):
        rectangle(1, 1, plane="corte")


def test_centred_box():
    c = box(0.40, 0.05, 1.00)
    assert c.kind == BOX
    assert len(c.kind.faces) == 6
    assert extension(c.values) == pytest.approx([0.40, 0.05, 1.00])
    assert c.values.mean(axis=0) == pytest.approx([0, 0, 0])


def test_box_faces_face_outwards():
    v = box(2, 2, 2).values
    for face in BOX.faces:
        a, b, c = v[list(face[:3])]
        normal = np.cross(b - a, c - a)
        towards_outside = v[list(face)].mean(axis=0)  # the box is centred on the origin
        assert np.dot(normal, towards_outside) > 0


# --- Dividir -----------------------------------------------------------------

def test_grid_by_cell_size():
    panels = grid(rectangle(20, 12, plane='elevation', name="fachada"), cell_width=1, cell_height=1)
    assert panels.shape == "fila 12 × columna 20 = 240"
    assert panels.kind == RECTANGLE
    centres = centre(panels)
    assert centres.values[0, 0] == pytest.approx([0.5, 0, 0.5])
    assert centres.values[11, 19] == pytest.approx([19.5, 0, 11.5])


def test_grid_by_number_of_cells():
    panels = grid(rectangle(6, 3), columns=4, rows=2)
    assert panels.shape == "fila 2 × columna 4 = 8"
    assert extension(panels.values[1, 3]) == pytest.approx([1.5, 1.5, 0])


def test_a_grid_that_does_not_close_is_a_clear_error():
    with pytest.raises(ShapeError) as error:
        grid(rectangle(20.5, 12, plane='elevation', name="fachada"), cell_width=1, cell_height=1)
    assert str(error.value) == "El ancho de «fachada» (20,5 m) no se divide en celdas de 1 m: sobran 0,5 m."


def test_grid_on_several_facades():
    origins = point(Data(np.array([0.0, 30.0]), ("fachada",)), 0, 0)
    facades = rectangle(20, 12, origin=origins, plane='elevation', name="fachadas")
    panels = grid(facades, cell_width=1, cell_height=1)
    assert panels.shape == "fachada 2 × fila 12 × columna 20 = 480"
    assert centre(panels).values[1, 0, 0] == pytest.approx([30.5, 0, 0.5])


def test_grid_only_divides_rectangles():
    with pytest.raises(ShapeError, match="«caja» debería ser un rectángulo y es «caja»"):
        grid(box(1, 1, 1, name="caja"), columns=2, rows=2)


# --- Measure and remap --------------------------------------------------------

def test_distance():
    assert distance(point(0, 0, 0), point(3, 4, 0)).values == pytest.approx(5.0)
    assert distance((0, 0, 0), (0, 0, 2)).values == pytest.approx(2.0)


def test_remap():
    d = Data(np.array([0.0, 5.0, 10.0]), ("panel",))
    assert remap(d, from_=(0, 10), towards=(90, 0)).list_() == [90.0, 45.0, 0.0]


# --- Move and rotate -----------------------------------------------------------

def test_rotate_a_point_90_degrees_vertically():
    assert rotate(point(1, 0, 0), 90).values == pytest.approx([0, 1, 0])


def test_rotate_about_another_centre():
    assert rotate(point(2, 0, 0), 180, centre=(1, 0, 0)).values == pytest.approx([0, 0, 0])


def test_rotate_about_axis_x():
    assert rotate(point(0, 1, 0), 90, axis="x").values == pytest.approx([0, 0, 1])


def test_move_a_box():
    c = move(box(1, 1, 1), (10, 0, 0))
    assert c.kind == BOX
    assert c.values.mean(axis=0) == pytest.approx([10, 0, 0])


def test_place_a_box_at_many_points_with_its_rotation():
    points = point(Data(np.array([0.0, 5.0]), ("panel",)), 0, 0)
    rotations = Data(np.array([0.0, 90.0]), ("panel",))
    boxes = place(box(0.40, 0.05, 1.00), at=points, rotation=rotations)
    assert boxes.shape == "panel 2"
    assert boxes.kind == BOX
    assert extension(boxes.values[0]) == pytest.approx([0.40, 0.05, 1.00])
    assert extension(boxes.values[1]) == pytest.approx([0.05, 0.40, 1.00])
    assert boxes.values[1].mean(axis=0) == pytest.approx([5, 0, 0])


def test_moving_a_number_is_a_clear_error():
    with pytest.raises(ShapeError, match="debería ser una geometría y es un número"):
        move(Data.value(3.0, "altura"), (1, 0, 0))


# --- Case 01, now with geometry --------------------------------------------

def facade_with_sun_fins(attractor=(4.5, 0.0, 6.5)):
    facade = rectangle(20, 12, plane='elevation', name="fachada")             # 1
    panels = grid(facade, cell_width=1, cell_height=1, name="paneles")  # 2
    centres = centre(panels, name="centros")
    distances = distance(centres, point(*attractor))                          # 3, 4
    maximum = reduce(distances, 'maximum')
    angles = remap(distances, from_=(0, maximum), towards=(90, 0))            # 5
    sun_fin = box(0.40, 0.05, 1.00, name="quiebrasol")                    # 6
    return place(sun_fin, at=centres, rotation=angles, name="quiebrasoles"), angles  # 7


def test_case_01_with_geometry():
    sun_fins, angles = facade_with_sun_fins()
    assert repr(sun_fins) == "<Data «quiebrasoles» box: fila 12 × columna 20 = 240>"
    # Next to the attractor (row 6, column 4): open, perpendicular to the facade.
    assert extension(sun_fins.values[6, 4]) == pytest.approx([0.05, 0.40, 1.00])
    # The farthest: closed, parallel to the facade.
    far = np.unravel_index(np.argmin(angles.values), angles.values.shape)
    assert extension(sun_fins.values[far]) == pytest.approx([0.40, 0.05, 1.00])


def test_case_01_if_the_attractor_leaves_the_facade_everything_still_works():
    sun_fins, angles = facade_with_sun_fins(attractor=(-10.0, 5.0, 30.0))
    assert sun_fins.count == 240
    assert np.all(np.isfinite(sun_fins.values))
    assert angles.values.max() < 90


def test_grid_with_other_names():
    modules = grid(rectangle(30, 12, plane='elevation'), columns=10, rows=4, levels=("piso", "módulo"))
    assert modules.shape == "piso 4 × módulo 10 = 40"


def test_divide_into_vertical_and_horizontal_strips():
    panel = rectangle(3, 2, plane='elevation')
    vertical = divide(panel, 3, level="franja")
    assert vertical.shape == "franja 3"
    assert extension(vertical.values[0]) == pytest.approx([1, 0, 2])
    horizontal = divide(panel, size=0.5, level="tablilla", direction='height')
    assert horizontal.shape == "tablilla 4"
    assert extension(horizontal.values[0]) == pytest.approx([3, 0, 0.5])


def test_case_01b_three_sun_fins_per_panel():
    facade = rectangle(20, 12, plane='elevation', name="fachada")
    panels = grid(facade, cell_width=1, cell_height=1)
    centres = centre(panels)
    distances = distance(centres, point(4.5, 0, 6.5))
    angles = remap(distances, from_=(0, reduce(distances, 'maximum')), towards=(90, 0))

    strips = divide(panels, 3, level="quiebrasol")                         # 6b
    sun_fins = place(box(0.30, 0.05, 1.00), at=centre(strips), rotation=angles)  # 7b

    assert sun_fins.shape == "fila 12 × columna 20 × quiebrasol 3 = 720"
    # The 3 of the attractor's panel: spread across its width and all open (they inherit the angle).
    panel = sun_fins.values[6, 4]
    assert [q.mean(axis=0)[0] for q in panel] == pytest.approx([4 + 1 / 6, 4.5, 5 - 1 / 6])
    for q in panel:
        assert extension(q) == pytest.approx([0.05, 0.30, 1.00])
