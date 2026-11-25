"""Surfaces (Delivery 3, E3.4): loft, extrude, grid and thickness on a surface."""

import numpy as np
import pytest

from tensela.connectors.obj import export_obj
from tensela.data import Data, ShapeError
from tensela.geometry import (
    centre, circle, thicken, extrude, line, normal, point, grid, surface_by_sections,
)


def hoops():
    heights = Data(np.array([0.0, 9, 18]), ("sección",))
    radii = Data(np.array([3.0, 1.5, 3.0]), ("sección",))
    return circle(point(0, 0, heights), radius=radii, name="aros")


def test_loft_removes_the_level():
    skin = surface_by_sections(hoops(), along="sección")
    assert skin.shape == "· (un valor)" and skin.kind.grid is not None
    z = skin.values[:, 2]
    assert z.min() == pytest.approx(0) and z.max() == pytest.approx(18)


def test_the_skin_passes_through_the_sections():
    skin = surface_by_sections(hoops(), along="sección")
    r = np.linalg.norm(skin.values[:, :2], axis=-1)
    in_middle = r[np.isclose(skin.values[:, 2], 9)]
    assert in_middle == pytest.approx(np.full(in_middle.shape, 1.5), abs=1e-6)


def test_smooth_or_straight():
    smooth = surface_by_sections(hoops(), along="sección")
    straight = surface_by_sections(hoops(), along="sección", smooth=False)
    r = lambda p, z: np.linalg.norm(p.values[np.isclose(p.values[:, 2], z, atol=0.6), :2], axis=-1).mean()  # noqa: E731
    # At 4.5 m of height the smooth skin curves inwards; the straight one goes in a straight line.
    assert r(smooth, 4.5) != pytest.approx(r(straight, 4.5), abs=0.01)


def test_one_skin_per_tower():
    heights = Data(np.array([[0.0, 10], [0.0, 20]]), ("torre", "sección"))
    skins = surface_by_sections(circle(point(0, 0, heights), radius=2), along="sección")
    assert skins.shape == "torre 2"


def test_grid_on_the_skin():
    panels = grid(surface_by_sections(hoops(), along="sección"), columns=12, rows=12)
    assert panels.shape == "fila 12 × columna 12 = 144"
    n, c = normal(panels).values, centre(panels).values
    assert ((n[..., :2] * c[..., :2]).sum(-1) > 0).all()  # miran hacia fuera


def test_grid_on_a_surface_asks_for_numbers():
    with pytest.raises(ShapeError, match="hay que decir el número de columnas y de filas"):
        grid(surface_by_sections(hoops(), along="sección", name="piel"), cell_width=1, cell_height=1)


def test_extruding_a_line_gives_a_sheet():
    sheet = extrude(line((0, 0, 0), (0, 1.48, 0)), (0.25, 0, 0))
    assert sheet.kind.grid == (2, 2)
    assert np.ptp(sheet.values, axis=0) == pytest.approx([0.25, 1.48, 0])


def test_thicken_a_surface():
    sheet = extrude(line((0, 0, 0), (0, 1, 0)), (1, 0, 0))
    coarse = thicken(sheet, 0.05)
    assert np.ptp(coarse.values, axis=0)[2] == pytest.approx(0.05)
    skin = thicken(surface_by_sections(hoops(), along="sección"), 0.2)
    assert len(skin.kind.faces) > 0


def test_clear_errors():
    with pytest.raises(ShapeError, match="deberían ser curvas"):
        surface_by_sections(point(1, 2, 3, name="p"))
    with pytest.raises(ShapeError, match="hacen falta al menos dos secciones"):
        surface_by_sections(circle(radius=1, name="uno"))


def test_surfaces_go_to_the_obj(tmp_path):
    text = export_obj(tmp_path / "s.obj", surface_by_sections(hoops(), along="sección", name="piel")).read_text()
    assert text.count("\nf ") == 16 * 64
