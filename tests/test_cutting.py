"""Fabrication, package 3b: flat pieces laid on sheets with their numbers, and the cutting file."""
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from tensela import fabrication as F
from tensela.connectors.cutting import export_cutting
from tensela.data import Data, ShapeError
from tensela.geometry import CLOSED_CURVE
from tensela.graph import Graph
from tensela.project_file import open_
from tensela.strokes import text_strokes, text_width


@pytest.fixture(autouse=True)
def in_english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _strips(n=12, length=0.2, width=0.03):
    """`n` flat strips standing up in space (like sections), numbered from 1."""
    rings = []
    for k in range(n):
        x = k * 0.01
        rings.append([(x, 0, 0), (x, length, 0), (x, length, width), (x, 0, width), (x, 0, 0)])
    return Data(np.array(rings, float), ("section",), "strips", starts={"section": 1}, kind=CLOSED_CURVE)


def test_the_lettering_has_digits_and_letters():
    assert text_width("12", 0.006) == pytest.approx(0.009)
    strokes = text_strokes("A-7", 0.006)
    every = np.vstack(strokes)
    assert every[:, 1].min() >= 0 and every[:, 1].max() == pytest.approx(0.006) and len(strokes) == 4


def test_pieces_lie_on_the_ground_inside_their_sheets_without_touching():
    strips = _strips()
    pieces = F.lay_flat(strips, 0.6, 0.4, 0.004, 0.01)
    layout = pieces.layout
    v = np.asarray(pieces.values)
    assert pieces.levels == ("section",) and pieces.starts == {"section": 1} and np.allclose(v[..., 2], 0)
    assert len(layout.boxes) == 1 and layout.count == 12
    x0, y0, x1, y1 = layout.boxes[0]
    assert v[..., 0].min() >= x0 + 0.01 - 1e-9 and v[..., 0].max() <= x1 - 0.01 + 1e-9
    assert v[..., 1].min() >= y0 + 0.01 - 1e-9 and v[..., 1].max() <= y1 - 0.01 + 1e-9
    boxes = [(c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max()) for c in v]
    for i in range(len(boxes)):                         # at least the spacing between any two
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            apart = max(b[0] - a[2], a[0] - b[2], b[1] - a[3], a[1] - b[3])
            assert apart >= 0.004 - 1e-9
    assert layout.used == pytest.approx(12 * 0.2 * 0.03 / (0.6 * 0.4), rel=1e-6)


def test_more_pieces_need_more_sheets_and_the_too_big_one_is_said():
    many = F.lay_flat(_strips(60), 0.6, 0.4, 0.004, 0.01)
    assert len(many.layout.boxes) >= 2
    with pytest.raises(ShapeError, match="does not fit"):
        F.lay_flat(_strips(1, length=0.9), 0.6, 0.4)
    turned = F.lay_flat(_strips(1, length=0.35, width=0.5), 0.6, 0.4, 0.004, 0.01)     # it fits turned a quarter
    assert len(turned.layout.boxes) == 1


def test_numbers_go_inside_their_pieces():
    strips = _strips(3)
    pieces = F.lay_flat(strips, show='pieces')
    numbers = F.lay_flat(strips, show='numbers')
    strokes = np.asarray(numbers.values)[..., :2]
    rings = [F._closed_ring(c, 1e-12)[:, :2] for c in np.asarray(pieces.values)]
    for s in strokes:
        assert any(F._inside(s, r).all() for r in rings)
    assert numbers.operation == 'engrave' and pieces.operation == 'cut' and not pieces.layout.unnumbered


def test_the_sheets_and_where_they_start():
    sheets = F.lay_flat(_strips(60), 0.6, 0.4, show='sheets', origin=(1.0, 2.0, 0.0))
    v = np.asarray(sheets.values)
    assert sheets.levels == ("sheet",) and np.allclose(v[0, 0], (1.0, 2.0, 0.0))
    assert np.allclose(np.ptp(v[0], axis=0)[:2], (0.6, 0.4))


def test_svg_and_dxf_one_file_per_sheet_in_millimetres(tmp_path):
    strips = _strips(60)
    items = [(show, F.lay_flat(strips, show=show)) for show in ('pieces', 'numbers', 'sheets')]
    svgs = export_cutting(tmp_path / "cut.svg", items)
    sheets = len(items[0][1].layout.boxes)
    assert len(svgs) == sheets + 1 and sheets >= 2 and svgs[-1].name == "cut_all.svg"
    together = ET.fromstring(svgs[-1].read_text())                       # all of them side by side, with their edges
    ns_ = "{http://www.w3.org/2000/svg}"
    groups = {g.get("id"): g for g in together.iter(ns_ + "g")}
    assert set(groups) == {"sheet", "cut", "engrave"} and len(groups["sheet"]) == sheets
    assert sum(len(ET.fromstring(f.read_text()).find(ns_ + "g[@id='cut']")) for f in svgs[:-1]) == len(groups["cut"])
    assert float(together.get("viewBox").split()[2]) > 600
    root = ET.fromstring(svgs[0].read_text())
    assert root.get("width") == "600.0000mm" and root.get("viewBox") == "0 0 600.0000 400.0000"
    ns = "{http://www.w3.org/2000/svg}"
    layers = {g.get("id"): g for g in root.iter(ns + "g")}
    assert set(layers) == {"cut", "engrave"} and layers["cut"].get("stroke") == "#FF0000"
    points = np.array([[float(c) for c in pt.split(",")] for poly in layers["cut"] for pt in poly.get("points").split()])
    assert points.min() >= 0 and points[:, 0].max() <= 600 and points[:, 1].max() <= 400
    import ezdxf
    dxfs = export_cutting(tmp_path / "cut.dxf", items)
    doc = ezdxf.readfile(dxfs[0])
    by_layer = {}
    for e in doc.modelspace():
        by_layer[e.dxf.layer] = by_layer.get(e.dxf.layer, 0) + 1
    assert set(by_layer) == {"cut", "engrave", "sheet"} and doc.layers.get("sheet").is_off()
    assert doc.header["$INSUNITS"] == 4                                # millimetres
    assert dxfs[-1].name == "cut_all.dxf" and not ezdxf.readfile(dxfs[-1]).layers.get("sheet").is_off()


def test_what_is_not_flat_on_the_ground_is_refused(tmp_path):
    with pytest.raises(ShapeError, match="lying flat"):
        export_cutting(tmp_path / "cut.svg", [("strips", _strips())])


