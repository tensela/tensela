"""Saving, opening and running a graph (step 1.4b)."""

import json
from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_, save
from tensela.graph import Graph
from tensela.cli import main
from tensela.data import ShapeError

from test_graph import case_01

EXAMPLES = Path(__file__).parent / "data"


def test_save_and_open_give_the_same_result(tmp_path):
    g = case_01()
    filepath = save(g, tmp_path / "caso.json", export=["quiebrasoles"])
    p = open_(filepath)
    other, export = p.graph, p.export
    assert export == ["quiebrasoles"]
    assert list(other.nodes) == list(g.nodes)
    assert np.allclose(other.value("quiebrasoles").values, g.value("quiebrasoles").values)


def test_the_file_has_one_node_per_line_and_only_what_is_needed(tmp_path):
    text = save(case_01(), tmp_path / "caso.json").read_text(encoding="utf-8")
    assert '    "fachada": {"type": "Rectangle", "width": 20, "height": 12, "plane": "elevation"},' in text
    # The attractor does not save y=0 (it is the default value) nor the origin of the rectangle.
    assert '"atractor": {"type": "Point", "x": 4.5, "z": 6.5}' in text
    assert json.loads(text)["parametrico"] == 1


def test_the_order_of_the_nodes_in_the_file_does_not_matter(tmp_path):
    filepath = tmp_path / "desordenado.json"
    filepath.write_text(json.dumps({
        "parametrico": 1,
        "nodos": {
            "paneles": {"tipo": "Retícula", "rectangulo": {"nodo": "fachada"}, "columnas": 4, "filas": 2},
            "fachada": {"tipo": "Rectángulo", "ancho": 8, "alto": 4},
        },
    }), encoding="utf-8")
    g = open_(filepath).graph
    assert g.value("paneles").shape == "fila 2 × columna 4 = 8"


@pytest.mark.parametrize('content, message', [
    ({"nodos": {}}, "es de la versión None del formato"),
    ({"parametrico": 1}, "no es un grafo de Tensela"),
    ({"parametrico": 1, "nodos": {"a": {"ancho": 1}}}, "Al nodo «a» le falta su «type»"),
    ({"parametrico": 1, "nodos": {"a": {"tipo": "Caja", "largo": 1}}}, "«Caja» no tiene la entrada «largo»"),
    ({"parametrico": 1, "nodos": {"a": {"tipo": "Centro", "geometria": {"nodo": "b"}}}},
     "«a» se conecta a «b», que no existe"),
    ({"parametrico": 1, "nodos": {}, "exportar": ["x"]}, "Se pide exportar «x», que no existe"),
])
def test_clear_errors_on_opening(tmp_path, content, message):
    filepath = tmp_path / "malo.json"
    filepath.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ShapeError, match=message):
        open_(filepath)


def test_broken_json_says_where(tmp_path):
    filepath = tmp_path / "roto.json"
    filepath.write_text('{"parametrico": 1,\n "nodos": {,}}', encoding="utf-8")
    with pytest.raises(ShapeError, match="«roto.json» no es un archivo válido: línea 2"):
        open_(filepath)


# --- The command ----------------------------------------------------------------

def test_the_examples_open():
    for name, shape in [("caso_01.json", "fila 12 × columna 20 = 240"),
                          ("caso_01b.json", "fila 12 × columna 20 × quiebrasol 3 = 720")]:
        p = open_(EXAMPLES / name)
        g, export = p.graph, p.export
        assert g.value('sun fins').shape == shape
        assert export == ['facade', 'sun fins', 'attractor marker']


def test_the_command_shows_the_shapes_and_writes_the_obj(tmp_path, capsys):
    output = tmp_path / "f.obj"
    assert main([str(EXAMPLES / "caso_01.json"), "--obj", str(output)]) == 0
    text = capsys.readouterr().out
    assert "  panels  " in text and "rectángulo: fila 12 × columna 20 = 240" in text
    assert f"Escrito: {output}" in text
    obj = output.read_text(encoding="utf-8")
    assert obj.count("\nv ") == 4 + 240 * 8 + 8


def test_the_command_changes_values(tmp_path, capsys):
    output = tmp_path / "f.obj"
    assert main([str(EXAMPLES / "caso_01.json"), "--obj", str(output),
                 "--change", 'facade.width=30', "--change", 'facade.plane=elevation']) == 0
    assert "fila 12 × columna 30 = 360" in capsys.readouterr().out


def test_the_command_shows_the_error_without_code(tmp_path, capsys):
    code = main([str(EXAMPLES / "caso_01.json"), "--obj", str(tmp_path / "f.obj"),
                   "--cambiar", 'facade.ancho=20.5'])
    output = capsys.readouterr()
    assert code == 1
    assert output.err == "✖ En «panels» (Retícula): El ancho de «facade» (20,5 m) no se divide en celdas de 1 m: sobran 0,5 m.\n"
    assert 'facade' in output.out  # what got to be computed is seen
    assert not (tmp_path / "f.obj").exists()


def test_badly_written_change(capsys):
    assert main([str(EXAMPLES / "caso_01.json"), "--cambiar", "ancho=30"]) == 1
    assert "se escribe NODO.ENTRADA=VALOR" in capsys.readouterr().err


# --- Controls and view (Delivery 1) ----------------------------------------------

from tensela.project_file import Control, Project, automatic_controls  # noqa: E402


def test_controls_and_view_round_trip(tmp_path):
    g = case_01()
    controls = [Control("atractor", "x", 0, 20, 0.5, "m"),
                 Control("ángulos", "to_min", 0, 90, 5, "°", "ángulo cerca")]
    view = {"fachada": {"color": "#c9d6e2", "opacity": 0.5}}
    filepath = save(Project(g, ["quiebrasoles"], "prueba", controls, view), tmp_path / "p.json")
    text = filepath.read_text(encoding="utf-8")
    assert '    {"value": "atractor.x", "min": 0, "max": 20, "step": 0.5, "unit": "m"},' in text
    p = open_(filepath)
    assert p.controls == controls
    assert p.view == view
    assert p.description == "prueba"


@pytest.mark.parametrize("control, message", [
    ({"valor": "atractor"}, "Un control debe decir «value»"),
    ({"valor": "nadie.x", "min": 0, "max": 1}, "habla de «nadie», que no existe"),
    ({"valor": "atractor.w", "min": 0, "max": 1}, "«Punto» no tiene la entrada «w»"),
    ({"valor": "paneles.rectangulo", "min": 0, "max": 1}, "solo un valor fijo puede ser un control"),
    ({"valor": "atractor.x", "max": 1}, "Al control «atractor.x» le falta «min»"),
])
def test_badly_written_controls(tmp_path, control, message):
    content = json.loads(save(case_01(), tmp_path / "p.json").read_text(encoding="utf-8"))
    content["controles"] = [control]
    (tmp_path / "p.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ShapeError, match=message):
        open_(tmp_path / "p.json")


def test_automatic_controls_offer_the_fixed_numbers():
    keys = {c.key for c in automatic_controls(case_01())}
    assert {"fachada.width", "atractor.x", "quiebrasol.depth", "ángulos.to_min"} <= keys
    assert "paneles.rectangulo" not in keys  # it is a connection
    assert "fachada.plano" not in keys       # it is a text


def test_the_examples_bring_controls_and_colours():
    p = open_(EXAMPLES / "caso_01.json")
    assert 'attractor.x' in {c.key for c in p.controls}
    assert p.view['attractor marker']["color"] == "#d9534f"


def test_copy_and_paste_remakes_the_connections_between_the_copies():
    from tensela.project_file import from__text, fragment, paste_fragment
    p = from__text((Path(__file__).parent / "data" / "caso_01.json").read_text(encoding="utf-8"))
    g = p.graph
    # Two nodes connected to each other, and one of them with an input from outside.
    origin = next(n for n in g.nodes.values() if any(isinstance(v, type(n)) for v in n.inputs.values()))
    input_, parent = next((e, v) for e, v in origin.inputs.items() if isinstance(v, type(origin)))
    frag = fragment(g, [parent.name, origin.name], {parent.name: (0, 0)})
    before = len(g.nodes)
    new = paste_fragment(g, frag)
    assert len(g.nodes) == before + 2 and set(new) == {parent.name, origin.name}
    assert all(n != v for n, v in new.items())                          # nombres libres
    assert g.nodes[new[origin.name]].inputs[input_] is g.nodes[new[parent.name]]
    # Copying only the lower one: on pasting, its outside input stays loose; on duplicating, it is kept.
    only = fragment(g, [origin.name])
    pasted = paste_fragment(g, only)[origin.name]
    assert not isinstance(g.nodes[pasted].inputs[input_], type(origin))
    duplicated = paste_fragment(g, only, with_inputs=True)[origin.name]
    assert g.nodes[duplicated].inputs[input_] is parent


def test_the_name_of_the_copy_follows_the_numbering():
    from tensela.project_file import _copy_name
    g = Graph()
    g.node("Number", "caja 4")
    g.node("Number", "fachada")
    assert _copy_name(g, "caja 4", set()) == "caja 5"
    assert _copy_name(g, "fachada", set()) == "fachada 2"
    assert _copy_name(g, "libre", set()) == "libre"


def test_a_list_of_numbers_has_one_slider_per_value():
    from tensela.project_file import control_for, automatic_controls, slidable, numbers_items
    assert numbers_items("10; 10; 14,5; 10") == [10, 10, 14.5, 10]
    assert numbers_items([1, 2]) == [1, 2]
    assert numbers_items("alzado") is None and numbers_items(3) is None and numbers_items("a; b") is None
    assert slidable(3) and slidable("1; 2") and not slidable(True) and not slidable("planta")
    g = Graph()
    g.node("Number", "radios", value="10; 4; 14; 10", level="anillo")
    c = control_for(g, "radios", "value")
    assert c.minimum == 0 and c.maximum >= 14                      # the range serves all the values
    assert [x.key for x in automatic_controls(g)] == ["radios.value"]


def test_on_duplicating_the_letter_goes_on():
    from tensela.project_file import _copy_name
    from tensela.graph import Graph
    g = Graph()
    g.node("Line", "borde a", from_=(0, 0, 0), to=(1, 0, 0))
    assert _copy_name(g, "borde a", set()) == "borde b"
    assert _copy_name(g, "borde a", {"borde b"}) == "borde c"
    g.node("Line", "Fachada A", from_=(0, 0, 0), to=(1, 0, 0))
    assert _copy_name(g, "Fachada A", set()) == "Fachada B"
    g.node("Line", "caja 4", from_=(0, 0, 0), to=(1, 0, 0))
    assert _copy_name(g, "caja 4", set()) == "caja 5"


def test_the_canvas_annotations_are_saved_and_read():
    from tensela.project_file import to_text, from__text
    from tensela.graph import Graph
    from tensela.project_file import Project
    g = Graph()
    g.node("Point")
    notes = [{"type": "frame", "x": 0, "y": 0, "width": 400, "height": 200, "text": "Fachada", "color": "blue"},
             {"type": "text", "x": 10, "y": -80, "width": 220, "text": "La planta", "color": "yellow", "size": 11},
             {"type": "arrow", "x": 0, "y": 0, "x2": 140, "y2": 30, "color": "red"}]
    p = from__text(to_text(Project(g, notes=notes)))
    assert p.notes == notes
    assert from__text(to_text(Project(g))).notes == []
