"""Exportar a OBJ (paso 1.3)."""

import numpy as np
import pytest

from tensela.connectors.obj import export_obj
from tensela.data import Data, ShapeError
from tensela.geometry import box, place, point, rectangle, grid


def read_obj(filepath):
    """A minimal reader: vertices, faces (indices from 0), objects and groups."""
    vertices, faces, objects, groups = [], [], [], []
    for line in filepath.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts or parts[0] == "#":
            continue
        if parts[0] == "v":
            vertices.append([float(x) for x in parts[1:]])
        elif parts[0] == "f":
            faces.append([int(i) - 1 for i in parts[1:]])
        elif parts[0] == "o":
            objects.append(parts[1])
        elif parts[0] == "g":
            groups.append(parts[1])
    return np.array(vertices), faces, objects, groups


def test_a_box(tmp_path):
    filepath = export_obj(tmp_path / "caja.obj", box(2, 4, 6, name="caja"))
    vertices, faces, objects, _ = read_obj(filepath)
    assert objects == ["caja"]
    assert len(vertices) == 8 and len(faces) == 6
    # Y up: the height (6, in the engine's Z) becomes the file's Y.
    assert vertices.max(axis=0) - vertices.min(axis=0) == pytest.approx([2, 6, 4])


def test_faces_point_to_existing_vertices(tmp_path):
    boxes = place(box(1, 1, 1), at=point(Data(np.arange(5.0) * 2, ("panel",)), 0, 0), name="cajas")
    vertices, faces, _, _ = read_obj(export_obj(tmp_path / "c.obj", boxes))
    assert len(vertices) == 40 and len(faces) == 30
    assert min(min(c) for c in faces) == 0
    assert max(max(c) for c in faces) == 39


def test_several_objects_in_a_file(tmp_path):
    facade = rectangle(20, 12, plane='elevation', name="fachada")
    panels = grid(facade, columns=4, rows=3, name="paneles")
    vertices, faces, objects, _ = read_obj(export_obj(tmp_path / "f.obj", facade, panels))
    assert objects == ["fachada", "paneles"]
    assert len(vertices) == 4 + 12 * 4
    assert len(faces) == 1 + 12


def test_groups_per_element_with_the_user_numbering(tmp_path):
    floors = Data(np.array([0.0, 3.0, 6.0]), ("piso",), starts={"piso": -1})
    slabs = place(box(10, 10, 0.3), at=point(0, 0, floors), name="losas")
    _, _, _, groups = read_obj(export_obj(tmp_path / "l.obj", slabs, by_element=True))
    assert groups == ["losas_piso-1", "losas_piso0", "losas_piso1"]


def test_only_the_elements_that_exist(tmp_path):
    heights = Data.from_lists([[0.0, 1.0, 2.0], [0.0]], ("columna", "pieza"))
    pieces = place(box(1, 1, 1), at=point(0, 0, heights), name="piezas")
    vertices, faces, _, _ = read_obj(export_obj(tmp_path / "p.obj", pieces))
    assert len(faces) == 4 * 6


def test_in_millimetres(tmp_path):
    vertices, _, _, _ = read_obj(export_obj(tmp_path / "mm.obj", box(2, 2, 2), unit="mm"))
    assert vertices.max() == pytest.approx(1000)


def test_a_point_is_not_exported(tmp_path):
    with pytest.raises(ShapeError, match="no se puede exportar a OBJ: es «punto»"):
        export_obj(tmp_path / "x.obj", point(1, 2, 3, name="atractor"))


def test_without_minus_zero(tmp_path):
    text = export_obj(tmp_path / "c.obj", box(1, 1, 1)).read_text()
    assert "-0.000000" not in text
