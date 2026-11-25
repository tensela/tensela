"""IngeTrazo (Delivery 4, step 4). The test with IngeTrazo's reader is skipped if its code is not there."""

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.cli import main
from tensela.connectors.ingetrazo import document_igz, export_igz
from tensela.data import Data, ShapeError
from tensela.geometry import box, circle, point, rectangle

EXAMPLES = Path(__file__).parent / "data"
SOURCE = Path(os.environ.get("TENSELA_INGETRAZO_FUENTE",
                             "~/Documents/claude-code/ingetrazo/ingetrazo-0.5.11")).expanduser()


def test_one_group_per_node_and_one_per_piece():
    p = open_(EXAMPLES / "caso_01.json")
    graph_scene = document_igz(p.visible_objects())["scene"]
    names = [g["name"] for g in graph_scene["groups"]]
    assert names == p.export
    sun_fins = graph_scene["groups"][names.index('sun fins')]
    assert len(sun_fins["children"]) == 240
    assert sun_fins["children"][0]["name"] == "sun fins · row 0, column 0"
    assert len(sun_fins["children"][0]["faces"]) == 6


def test_layers_materials_and_colours():
    graph_scene = document_igz([("vidrio", rectangle(1, 1), {"color": "#ff8000", "opacity": 0.4})])["scene"]
    assert graph_scene["layers"][1] == {"name": "vidrio", "color": [1.0, 0.502, 0.0], "opacity": 0.4}
    assert graph_scene["materials"] == [{"name": "vidrio", "color": [1.0, 0.502, 0.0], "opacity": 0.4}]
    face = graph_scene["groups"][0]["faces"][0]
    assert face["mat"] == "vidrio" and face["opacity"] == 0.4


def test_curves_as_edges_of_a_curve_and_points_as_guides():
    graph_scene = document_igz([("aro", circle(radius=1), {}), ("atractor", point(1, 2, 3), {})])["scene"]
    edges = graph_scene["groups"][0]["edges"]
    assert len(edges) == 64 and {a["curve"] for a in edges} == {1}      # cerrado: 64 tramos
    assert graph_scene["guides"] == [{"point": [1.0, 2.0, 3.0], "layer": "atractor"}]


def test_faces_without_area_are_skipped():
    panels = rectangle(Data(np.array([1.0, 0.0]), ("panel",)), 1)
    children = document_igz([("paneles", panels, {})])["scene"]["groups"][0]["children"]
    assert [len(h["faces"]) for h in children] == [1, 0]


def test_coordinates_that_are_not_numbers_give_a_clear_error(tmp_path):
    with pytest.raises(ShapeError, match="no son números"):
        export_igz(tmp_path / "x.igz", [("caja", box(float("nan"), 1, 1), {})])


def test_from_the_terminal(tmp_path, capsys):
    output = tmp_path / "caso.igz"
    assert main([str(EXAMPLES / "caso_01.json"), "--obj", str(tmp_path / "c.obj"), "--igz", str(output)]) == 0
    assert json.loads(output.read_text())["igz_format"] == 1 and "IngeTrazo" in capsys.readouterr().out


