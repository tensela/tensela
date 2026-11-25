"""Blender, directly (Delivery 4, step 1). The tests with Blender are skipped if it is not installed."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.connectors.blender import find_blender, export_blend, prepare
from tensela.data import Data, ShapeError
from tensela.geometry import box, circle, point

EXAMPLES = Path(__file__).parent / "data"


def test_prepare_data_for_blender(tmp_path):
    objects = [("caja", box(1, 2, 3), {"color": "#ff0000"}),
               ("aro", circle(radius=1), {}),
               ("atractor", point(1, 2, 3), {"opacity": 0.5})]
    z = np.load(prepare(objects, tmp_path, "prueba"), allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    assert [o["class"] for o in meta["objects"]] == ["mesh", "curve", "points"]
    assert z["v0"].shape == (8, 3) and z["t0"].tolist() == [4] * 6
    assert z["l1"].shape == (64, 2)  # cerrado: 64 tramos
    assert meta["objects"][2]["opacity"] == 0.5


def test_a_number_does_not_go_to_blender(tmp_path):
    with pytest.raises(ShapeError, match="no es una geometría"):
        prepare([("altura", Data.value(3.0), {})], tmp_path)


def test_without_blender_it_says_so(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setattr("tensela.connectors.blender.USUAL_PLACES", ())
    monkeypatch.delenv("TENSELA_BLENDER", raising=False)
    with pytest.raises(ShapeError, match="No encuentro Blender"):
        find_blender()


def _there_is_blender():
    try:
        find_blender()
        return True
    except ShapeError:
        return False


@pytest.mark.skipif(not _there_is_blender(), reason="Blender no está instalado")
def test_the_blend_has_the_objects_upright(tmp_path):
    p = open_(EXAMPLES / "caso_01.json")
    objects = [(n, p.graph.value(n), p.view.get(n, {})) for n in p.export]
    filepath = export_blend(tmp_path / "caso.blend", objects, "caso_01")
    check = (
        "import bpy, json\n"
        "print('JSON', json.dumps({o.name: [list(o.rotation_euler), list(o.dimensions), len(o.data.polygons)]"
        " for o in bpy.data.objects}))"
    )
    output = subprocess.run([find_blender(), "-b", str(filepath), "--python-expr", check],
                            capture_output=True, text=True, timeout=120).stdout
    data_items = json.loads(next(l for l in output.splitlines() if l.startswith("JSON "))[5:])
    rot, dims, faces = data_items['facade']
    assert rot == [0, 0, 0]                                  # without the OBJ's 90° turn
    assert dims == pytest.approx([20, 0, 12], abs=1e-4)      # the height, in Z
    assert data_items['sun fins'][2] == 240 * 6
