"""Diamonds, response curves and frames on panels (Delivery 3, E3.5)."""

from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.data import Data, ShapeError, series
from tensela.geometry import (
    FRAME, COARSE_FRAME, centre, circle, frame, normal, point, rectangle, remap, grid,
    surface_by_sections,
)

EXAMPLES = Path(__file__).parent / "data"


def skin():
    heights = Data(np.array([0.0, 9, 18]), ("sección",))
    return surface_by_sections(circle(point(0, 0, heights), radius=3), along="sección")


# --- Rombos ----------------------------------------------------------------------

def test_diamonds_on_a_rectangle():
    r = grid(rectangle(12, 6, plane='elevation'), columns=4, rows=3, shape='diamonds')
    assert r.shape == "fila 3 × columna 4 = 12"
    below, right, above, left = r.values[0, 1]
    assert below[2] == pytest.approx(0) and above[2] == pytest.approx(3)     # alto: 2 × 6/(3+1)
    assert right[0] - left[0] == pytest.approx(3)                       # ancho: 12/4
    # The next row is shifted half a column.
    assert centre(r).values[1, 1][0] == pytest.approx(centre(r).values[0, 1][0] - 1.5)


def test_diamonds_on_a_closed_skin_go_round_and_face_outwards():
    r = grid(skin(), columns=12, rows=12, shape='diamonds')
    c, n = centre(r).values, normal(r).values
    assert ((c[..., :2] * n[..., :2]).sum(-1) > 0).all()
    # No diamond is squashed at the seam of the skin.
    widths = np.linalg.norm(r.values[..., 1, :] - r.values[..., 3, :], axis=-1)
    assert widths.min() > 0.5 * widths.max()


def test_unknown_shape():
    with pytest.raises(ShapeError, match="cuadrados, rombos, remates de rombos, hexágonos, triángulos"):
        grid(rectangle(2, 2), columns=2, rows=2, shape="pentagons")


# --- Response curve ------------------------------------------------------------

def test_response_curves():
    t = series(5, level="i")  # 0..4
    assert remap(t, (None, None), (0, 1)).list_() == [0, 0.25, 0.5, 0.75, 1]
    smooth = remap(t, (None, None), (0, 1), curve='smooth').list_()
    assert smooth[0] == 0 and smooth[2] == pytest.approx(0.5) and smooth[1] < 0.25 and smooth[-1] == 1
    assert remap(t, (None, None), (0, 1), curve='ease in').list_()[1] < 0.25
    assert remap(t, (None, None), (0, 1), curve='ease out').list_()[1] > 0.25


def test_with_a_curve_it_does_not_leave_the_range():
    far = remap(Data(np.array([-5.0, 0, 10, 20]), ("i",)), (0, 10), (0, 1), curve='smooth')
    assert far.list_() == [0, 0, 1, 1]


def test_unknown_response_curve():
    with pytest.raises(ShapeError, match="No conozco la curva «rara»"):
        remap(1, (0, 1), (0, 1), curve="rara")


# --- Marco ------------------------------------------------------------------------------

def test_flat_frame_and_with_thickness():
    panel = rectangle(2, 2, plane='elevation')
    m = frame(panel, opening=0.5)
    assert m.kind == FRAME and m.values.shape == (8, 3)
    hole = m.values[4:]
    assert np.ptp(hole, axis=0)[0] == pytest.approx(1)  # the opening measures half
    g = frame(panel, opening=0.5, thickness=0.2)
    assert g.kind == COARSE_FRAME and np.ptp(g.values, axis=0)[1] == pytest.approx(0.2)


def test_one_opening_per_panel():
    panels = grid(rectangle(4, 2, plane='elevation'), columns=2, rows=1)
    m = frame(panels, opening=Data(np.array([[0.2, 0.8]]), ("row", "column")))
    widths = [np.ptp(m.values[0, k, 4:], axis=0)[0] for k in range(2)]
    assert widths == pytest.approx([0.4, 1.6])


def test_frame_only_for_panels():
    with pytest.raises(ShapeError, match="debería ser un rectángulo"):
        frame(point(1, 1, 1, name="p"))


# --- A second case ----------------------------------------------------------------

