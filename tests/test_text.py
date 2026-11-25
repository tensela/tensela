"""The Text node (plan of the pending work, 2.4; Victor, test 122): a label on each element, in single-stroke
letters, for drawings."""
from pathlib import Path

import numpy as np
import pytest

from tensela import language
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.labels import _fill, _as_text
from tensela.strokes import text_strokes


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _floors():
    g = Graph()
    g.node("Series", "s", count=4, level="floor", step=3.0)
    g.node("Point", "p", z=g.nodes["s"])
    return g


def test_each_label_has_its_own_strokes_and_an_empty_one_is_a_hole():
    g = _floors()
    g.node("Text", "t", at=g.nodes["p"], text="A; BB; ;C")
    v = g.value("t")
    assert v.levels == ("floor", "stroke")
    assert v.count == 2 + 4 + 1                                 # A: two strokes, BB: four, nothing, C: one
    assert not v.mask[2].any()                                 # the empty one, a hole
    assert v.kind.curve


def test_what_the_labels_say():
    numbers = {"floor": "2", "panel": "5"}
    names = {"floor": "floor", "panel": "panel", "n": "n"}
    assert _fill("{n}", numbers, names, None, 2) == "2·5"
    assert _fill("P{floor}-{panel}", numbers, names, None, 2) == "P2-5"
    assert _fill("{value} m2", numbers, names, 3.456, 1) == "3.5 m2"
    assert _fill("{other}", numbers, names, None, 2) == "{other}"   # unknown: as it is
    assert _as_text(12) == "12" and _as_text(2.5) == "2.5" and _as_text([1, 2]) == "1; 2"


def test_the_value_and_the_level_names_in_spanish(monkeypatch):
    g = _floors()
    g.node("Text", "t", at=g.nodes["p"], text="P{piso}")                       # written in Spanish, read in English
    g.node("Text", "same", at=g.nodes["p"], text="P{floor}")
    assert np.allclose(g.value("t").values, g.value("same").values)
    monkeypatch.setattr(language, "LANGUAGE", "es")
    numbers = {"floor": "1"}
    names = {"floor": "floor", "piso": "floor", "n": "n"}
    assert _fill("P{piso} · {valor}", numbers, names, 2.25, 2) == "P1 · 2,25"


def test_the_value_goes_one_per_element():
    g = _floors()
    g.node("Formula", "area", formula="a * 1.25", a=g.nodes["s"])
    g.node("Text", "t", at=g.nodes["p"], text="{value}", value=g.nodes["area"], decimals=1)
    v = g.value("t")
    # 0.0, 3.8, 7.5, 11.2: three, three, three and four characters (with their point)
    widths = np.ptp(np.asarray(v.values)[..., 0].reshape(4, -1), axis=1)
    assert widths[3] > widths[0]
    g.node("Series", "other", count=2, level="side")
    g.node("Text", "wrong", at=g.nodes["p"], text="{value}", value=g.nodes["other"])
    with pytest.raises(ShapeError, match="levels that the labels do not have"):
        g.value("wrong")


def test_the_planes_and_the_face_that_looks_at_the_reader():
    g = Graph()
    g.node("Box", "b", width=1.0, depth=1.0, height=2.0)
    for plane in ("plan", "elevation", "side elevation", "on the face"):
        g.node("Text", plane, at=g.nodes["b"], text="H", plane=plane, height=0.3)
    box = np.asarray(g.value("b").values).reshape(-1, 3)
    top, front, right = box[:, 2].max(), box[:, 1].min(), box[:, 0].max()
    plan = np.asarray(g.value("plan").values).reshape(-1, 3)
    assert np.allclose(plan[:, 2], plan[0, 2]) and plan[0, 2] > top           # on the top, lying, a little above
    assert np.ptp(plan[:, 1]) == pytest.approx(0.3)                            # read from the front: up is +y
    elevation = np.asarray(g.value("elevation").values).reshape(-1, 3)
    assert np.allclose(elevation[:, 1], elevation[0, 1]) and elevation[0, 1] < front
    side = np.asarray(g.value("side elevation").values).reshape(-1, 3)
    assert np.allclose(side[:, 0], side[0, 0]) and side[0, 0] > right
    face = np.asarray(g.value("on the face").values).reshape(-1, 3)
    assert np.allclose(face, elevation)                                        # a body: on its front


def test_on_the_face_of_tilted_panels():
    g = Graph()
    g.node("Rectangle", "r", width=2.0, height=1.0, plane="elevation")
    g.node("Rotate", "tilted", geometry=g.nodes["r"], degrees=30.0, axis="z")
    g.node("Text", "t", at=g.nodes["tilted"], text="E", plane="on the face", height=0.5)
    panel = np.asarray(g.value("tilted").values).reshape(-1, 3)
    normal = np.cross(panel[1] - panel[0], panel[3] - panel[0])
    normal /= np.linalg.norm(normal)
    strokes = np.asarray(g.value("t").values).reshape(-1, 3)
    heights = (strokes - panel.mean(axis=0)) @ normal
    assert np.allclose(heights, heights[0]) and abs(heights[0]) == pytest.approx(0.5 * 0.04)   # on it, stood off
    assert np.ptp(strokes[:, 2]) == pytest.approx(0.5)                         # upright


def test_the_lettering_takes_accents_off_and_has_more_signs():
    assert len(text_strokes("Á", 1.0)) == len(text_strokes("A", 1.0))
    assert len(text_strokes("ñ", 1.0)) == 2
    for sign in "·,:()+=%#":
        assert text_strokes(sign, 1.0), sign


def test_the_labels_go_out_in_a_drawing(tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    from tensela.connectors.dxf import export_dxf
    g = _floors()
    g.node("Text", "t", at=g.nodes["p"], text="A; BB; ;C", plane="elevation")
    export_dxf(tmp_path / "t.dxf", [("t", g.value("t"), {})], view="south elevation")
    assert len(list(ezdxf.readfile(tmp_path / "t.dxf").modelspace())) == 7      # each stroke once


