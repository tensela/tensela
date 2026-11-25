"""Transformations: the Image sampler reads numbers from a picture."""

import os

import numpy as np
import pytest
from PIL import Image

from tensela import images
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_, save


def _image(path, rows):
    """A tiny image from a list of rows of grey levels (0 to 255), or of (r, g, b, a) tuples."""
    a = np.array(rows, dtype=np.uint8)
    Image.fromarray(a, "RGBA" if a.ndim == 3 and a.shape[-1] == 4 else None).save(path)
    return path


def _facade(g, file, **inputs):
    """A façade of 4 × 2 panels of 1 m, in elevation, sampled at each panel."""
    g.node("Rectangle", "facade", width=4, height=2, plane="elevation")
    g.node("Grid", "panels", rectangle=g.nodes["facade"], cell_width=1, cell_height=1)
    g.node("Image sampler", "sample", file=str(file), where=g.nodes["panels"], frame=g.nodes["facade"], **inputs)
    return g.value("sample")


def test_each_panel_reads_its_part_of_the_image(tmp_path):
    file = _image(tmp_path / "half.png", [[0, 0, 255, 255], [0, 0, 255, 255]])
    v = _facade(Graph(), file)
    assert v.levels == ("row", "column")
    assert np.allclose(v.values, [[0, 0, 1, 1], [0, 0, 1, 1]])


def test_the_top_of_the_image_is_the_top_of_the_facade(tmp_path):
    file = _image(tmp_path / "sky.png", [[255] * 4, [0] * 4])     # the first row of pixels is the top
    g = Graph()
    v = _facade(g, file).values
    z = g.value("panels").values.mean(axis=-2)[..., 2]       # the height of each panel's centre
    assert np.allclose(v[z > 1], 1) and np.allclose(v[z < 1], 0)


def test_black_and_white_set_the_range_and_swapping_them_inverts(tmp_path):
    file = _image(tmp_path / "half.png", [[0, 0, 255, 255]])
    v = _facade(Graph(), file, black=0.9, white=0.1)
    assert np.allclose(v.values[:, :2], 0.9) and np.allclose(v.values[:, 2:], 0.1)


def test_between_two_pixels_it_blends():
    a = np.array([[0.0, 1.0]])
    assert np.isclose(images._bilinear(a, np.array(0.5), np.array(0.5)), 0.5)
    assert np.isclose(images._bilinear(a, np.array(0.0), np.array(0.5)), 0.0)     # outside: the nearest edge
    assert np.isclose(images._bilinear(a, np.array(1.0), np.array(0.5)), 1.0)


def test_the_channels(tmp_path):
    file = _image(tmp_path / "red.png", [[(255, 0, 0, 128)] * 2] * 2)
    g = Graph()
    g.node("Rectangle", "r", width=2, height=2)
    g.node("Point", "p", x=1, y=1)
    g.node("Image sampler", "s", file=str(file), where=g.nodes["p"], frame=g.nodes["r"])
    for channel, expected in [("red", 1), ("green", 0), ("blue", 0), ("alpha", 128 / 255), ("brightness", 0.2126)]:
        g.change("s", "channel", channel)
        assert np.isclose(float(g.value("s").values), expected, atol=1e-6), channel


def test_without_a_frame_the_image_covers_the_points(tmp_path):
    file = _image(tmp_path / "half.png", [[0, 255]])
    g = Graph()
    g.node("Series", "xs", start=0, step=1, count=4)
    g.node("Point", "p", x=g.nodes["xs"])
    g.node("Image sampler", "s", file=str(file), where=g.nodes["p"])
    # From x = 0 to 3 over two pixels: the ends take each pixel, in between they blend.
    assert np.allclose(g.value("s").values, [0, 1 / 6, 5 / 6, 1])


def test_a_relative_path_is_read_from_the_folder_of_the_project(tmp_path):
    _image(tmp_path / "half.png", [[0, 0, 255, 255]])
    g = Graph()
    g.folder = tmp_path
    v = _facade(g, "half.png")
    assert np.allclose(v.values[0], [0, 0, 1, 1])
    save(g, tmp_path / "project.json")
    project = open_(tmp_path / "project.json")
    assert project.graph.folder == tmp_path
    assert np.allclose(project.graph.value("sample").values[0], [0, 0, 1, 1])


def test_changing_the_folder_reads_the_image_again(tmp_path):
    for name, grey in (("a", 0), ("b", 255)):
        os.makedirs(tmp_path / name)
        _image(tmp_path / name / "img.png", [[grey]])
    g = Graph()
    g.folder = tmp_path / "a"
    assert np.allclose(_facade(g, "img.png").values, 0)
    g.folder = tmp_path / "b"
    assert np.allclose(g.value("sample").values, 1)


def test_an_image_changed_on_disk_is_read_again(tmp_path):
    file = _image(tmp_path / "img.png", [[0]])
    assert images.read(file)[..., :3].max() == 0
    _image(file, [[255, 255]])                       # another size: the cache notices even within the same second
    assert images.read(file)[..., :3].min() == 255


def test_a_missing_image_says_so(tmp_path):
    g = Graph()
    g.folder = tmp_path
    with pytest.raises(ShapeError, match="nope.png"):
        _facade(g, "nope.png")
    with pytest.raises(ShapeError, match="nope.txt"):
        (tmp_path / "nope.txt").write_text("not an image")
        _facade(Graph(), tmp_path / "nope.txt")
