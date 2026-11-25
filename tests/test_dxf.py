"""Export to DXF (Delivery 4, step 3). Skipped if ezdxf is not there."""

from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from tensela.project_file import open_  # noqa: E402
from tensela.cli import main  # noqa: E402
from tensela.connectors.dxf import _layer, export_dxf, read_summary  # noqa: E402
from tensela.data import Data, ShapeError  # noqa: E402

EXAMPLES = Path(__file__).parent / "data"


def _export(tmp_path, example, unit="m"):
    p = open_(EXAMPLES / f"{example}.json")
    return export_dxf(tmp_path / "x.dxf", p.visible_objects(), unit=unit)


def test_one_layer_per_node_and_one_object_per_element(tmp_path):
    summary = read_summary(_export(tmp_path, "caso_01"))
    assert summary == {'facade': {"MESH": 1}, 'sun fins': {"MESH": 240},
                       'attractor marker': {"MESH": 1}}


def test_maximum_compatibility_with_classic_meshes(tmp_path):
    p = open_(EXAMPLES / "caso_01.json")
    filepath = export_dxf(tmp_path / "x.dxf", p.visible_objects(), compatible=True)
    assert read_summary(filepath)['sun fins'] == {"POLYFACE": 240}


def test_sizes_in_millimetres_without_turns(tmp_path):
    doc = ezdxf.readfile(_export(tmp_path, "caso_01", unit="mm"))
    assert doc.header["$INSUNITS"] == 4 and not doc.audit().has_errors
    facade = next(e for e in doc.modelspace() if e.dxf.layer == 'facade')
    xs, ys, zs = zip(*facade.vertices)
    assert (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) == pytest.approx((20000, 0, 12000))


def test_colour_and_transparency_go_in_the_layer(tmp_path):
    from tensela.geometry import box
    doc = ezdxf.readfile(export_dxf(tmp_path / "c.dxf", [("vidrio", box(1, 1, 1), {"color": "#6b9e4e", "opacity": 0.75})]))
    layer = doc.layers.get("vidrio")
    assert layer.rgb == (0x6b, 0x9e, 0x4e) and layer.transparency == pytest.approx(0.25, abs=0.01)


def test_valid_layer_names_without_repeats():
    used = set()
    assert _layer("planta: 1/2", used) == "planta_ 1_2"
    assert _layer("Planta: 1/2", used) == "Planta_ 1_2 2"


def test_a_number_does_not_go_to_the_dxf(tmp_path):
    with pytest.raises(ShapeError, match="no es una geometría"):
        export_dxf(tmp_path / "n.dxf", [("altura", Data.value(3.0), {})])


def test_from_the_terminal(tmp_path, capsys):
    output = tmp_path / "caso.dxf"
    assert main([str(EXAMPLES / "caso_01.json"), "--obj", str(tmp_path / "c.obj"),
                 "--dxf", str(output), "--unit", "cm"]) == 0
    assert ezdxf.readfile(output).header["$INSUNITS"] == 5 and "en cm" in capsys.readouterr().out


# --- In 2D: plan and elevations ----------------------------------------------------

def _lines(filepath, layer):
    doc = ezdxf.readfile(filepath)
    return [(tuple(e.dxf.start), tuple(e.dxf.end)) for e in doc.modelspace().query(f'LINE[layer=="{layer}"]')]


def test_elevation_of_a_box_is_a_rectangle_of_4_lines(tmp_path):
    from tensela.geometry import prism
    filepath = export_dxf(tmp_path / "a.dxf", [("volumen", prism(4, 2, 3), {})], view="south elevation")
    lines = _lines(filepath, "volumen")
    assert len(lines) == 4                              # those behind fall on those in front
    xs = [p[0] for l in lines for p in l]
    ys = [p[1] for l in lines for p in l]
    assert (min(xs), max(xs), min(ys), max(ys)) == pytest.approx((0, 4, 0, 3))   # ancho × alto


def test_plan_and_elevations_look_from_outside(tmp_path):
    from tensela.geometry import prism
    volume = [("v", prism(4, 2, 3, origin=(10, 20, 0)), {})]
    def box_of(view):
        pts = [p for l in _lines(export_dxf(tmp_path / "v.dxf", volume, view=view), "v") for p in l]
        return min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts)
    assert box_of("plan") == pytest.approx((10, 14, 20, 22))
    assert box_of("north elevation") == pytest.approx((-14, -10, 0, 3))   # seen from the north, X reversed
    assert box_of("east elevation") == pytest.approx((20, 22, 0, 3))
    assert box_of("west elevation") == pytest.approx((-22, -20, 0, 3))


def test_a_view_that_does_not_exist(tmp_path):
    from tensela.geometry import box
    with pytest.raises(ShapeError, match="No conozco la vista «corte»"):
        export_dxf(tmp_path / "x.dxf", [("c", box(1, 1, 1), {})], view="corte")


def test_2d_from_the_terminal(tmp_path, capsys):
    output = tmp_path / "alzado.dxf"
    assert main([str(EXAMPLES / "caso_01.json"), "--obj", str(tmp_path / "c.obj"),
                 "--dxf", str(output), "--dxf-view", "south elevation"]) == 0
    assert "en 2D, alzado sur" in capsys.readouterr().out
    assert set(read_summary(output)['sun fins']) == {"LINE"}


def test_visible_only_removes_what_is_behind(tmp_path):
    from tensela.geometry import prism
    front = ("delante", prism(4, 1, 3), {})
    behind = ("detrás", prism(2, 1, 2, origin=(1, 5, 0)), {})          # smaller, fully covered
    peeks = ("asoma", prism(2, 1, 5, origin=(1, 9, 0)), {})            # taller: it peeps out at the top
    filepath = export_dxf(tmp_path / "v.dxf", [front, behind, peeks], view="south elevation", visible_only=True)
    # Of what is covered nothing remains above the ground (its bottom edge falls on that of the one in front).
    assert all(max(a[1], b[1]) < 0.01 for a, b in _lines(filepath, "detrás"))
    lines = _lines(filepath, "asoma")
    heights = sorted({round(p[1], 2) for l in lines for p in l})
    assert heights[-1] == pytest.approx(5) and all(not (0.01 < z < 2.99) for z in heights)   # it peeps out from the cornice
    assert len(_lines(filepath, "delante")) == 4


def test_without_visible_only_everything_is_seen(tmp_path):
    from tensela.geometry import prism
    filepath = export_dxf(tmp_path / "t.dxf", [("delante", prism(4, 1, 3), {}),
                                            ("detrás", prism(2, 1, 2, origin=(1, 5, 0)), {})], view="south elevation")
    assert "detrás" in read_summary(filepath)


@pytest.mark.parametrize('unit, code, width', [("in", 1, 20 / 0.0254), ("ft", 2, 20 / 0.3048)])
def test_feet_and_inches(tmp_path, unit, code, width):
    doc = ezdxf.readfile(_export(tmp_path, "caso_01", unit=unit))
    assert doc.header["$INSUNITS"] == code and doc.header["$MEASUREMENT"] == 0
    facade = next(e for e in doc.modelspace() if e.dxf.layer == 'facade')
    xs = [v[0] for v in facade.vertices]
    assert max(xs) - min(xs) == pytest.approx(width)        # 20 m = 787,4" = 65,6'
