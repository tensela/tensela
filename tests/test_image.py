"""Image of the 3D view (Delivery 4, step 2). Skipped if the interface is not there."""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pyvista")

from tensela.project_file import open_  # noqa: E402
from tensela.cli import main  # noqa: E402
from tensela.data import ShapeError  # noqa: E402
from tensela.ui.viewer import image  # noqa: E402

EXAMPLES = Path(__file__).parent / "data"


def _read(filepath):
    import pyvista as pv
    return np.asarray(pv.read(str(filepath)).active_scalars)  # pixels (RGB or RGBA)


def test_the_image_has_the_asked_size_and_shows_the_geometry(tmp_path):
    p = open_(EXAMPLES / "caso_01.json")
    assert image(tmp_path / "v.png", p.visible_objects(), 640, 360, background="white") == (640, 360)
    pixels = _read(tmp_path / "v.png")
    assert pixels.shape[0] == 640 * 360
    blank = np.all(pixels[:, :3] == 255, axis=1).mean()
    assert 0.2 < blank < 0.95          # there is a white background and there is a facade


def test_transparent_background(tmp_path):
    p = open_(EXAMPLES / "caso_01.json")
    image(tmp_path / "t.png", p.visible_objects(), 320, 200, background="transparent")
    pixels = _read(tmp_path / "t.png")
    assert pixels.shape[1] == 4 and (pixels[:, 3] == 0).any()


def test_the_colours_are_those_of_the_view():
    p = open_(EXAMPLES / "caso_01.json")
    colours = {n: e["color"] for n, _, e in p.visible_objects()}
    assert set(colours) == set(p.export) and all(c.startswith("#") for c in colours.values())


def test_from_the_terminal(tmp_path, capsys):
    output = tmp_path / "caso.png"
    assert main([str(EXAMPLES / "caso_01.json"), "--obj", str(tmp_path / "c.obj"),
                 "--png", str(output), "--size", "400x300"]) == 0
    assert output.exists() and "400 × 300 px" in capsys.readouterr().out


def test_a_badly_written_size_gives_a_clear_error(tmp_path, capsys):
    assert main([str(EXAMPLES / "caso_01.json"), "--obj", str(tmp_path / "c.obj"),
                 "--png", str(tmp_path / "x.png"), "--size", "grande"]) == 1
    assert "se escribe ANCHOxALTO" in capsys.readouterr().err
