"""The graph (step 1.4a): case 01 as connected nodes."""

import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.graph import NodeError, Graph
from tensela.nodes import CATALOG, REQUIRED, node_kind


def case_01(three=False):
    """The facade with sun fins, as it is in casos/01-fachada-atractor.md."""
    g = Graph()
    facade = g.node("Rectangle", "fachada", width=20, height=12, plane='elevation')
    panels = g.node("Grid", "paneles", rectangle=facade, cell_width=1, cell_height=1)
    centres = g.node("Centre", "centros", geometry=panels)
    attractor = g.node("Point", "atractor", x=4.5, y=0, z=6.5)
    distances = g.node("Distance", "distancias", a=centres, b=attractor)
    maximum = g.node("Máximo", "distancia máxima", data=distances)
    angles = g.node("Remap", "ángulos", value=distances,
                     from_min=0, from_max=maximum, to_min=90, to_max=0)
    sun_fin = g.node("Box", "quiebrasol", width=0.40, depth=0.05, height=1.00)
    at = centres
    if three:
        strips = g.node("Divide", "franjas", rectangle=panels, parts=3, level="quiebrasol")
        at = g.node("Centre", "centros de franjas", geometry=strips)
        g.change(sun_fin, "width", 0.30)
    g.node("Place", "quiebrasoles", geometry=sun_fin, at=at, rotation=angles)
    return g


def extension(vertices):
    v = np.asarray(vertices)
    return v.max(axis=0) - v.min(axis=0)


# --- Case 01 as a graph ---------------------------------------------------

def test_case_01_as_a_graph():
    g = case_01()
    sun_fins = g.value("quiebrasoles")
    assert repr(sun_fins) == "<Data «quiebrasoles» box: fila 12 × columna 20 = 240>"
    assert extension(sun_fins.values[6, 4]) == pytest.approx([0.05, 0.40, 1.00])


def test_case_01b_as_a_graph():
    sun_fins = case_01(three=True).value("quiebrasoles")
    assert sun_fins.shape == "fila 12 × columna 20 × quiebrasol 3 = 720"


def test_node_names_name_the_data():
    g = case_01()
    assert g.value("paneles").name == "paneles"
    assert g.value("distancia máxima").shape == "· (un valor)"


# --- Recompute only what changes -------------------------------------------

def test_each_node_is_computed_only_once():
    g = case_01()
    g.value("quiebrasoles")
    g.value("quiebrasoles")
    assert all(n.evaluations == 1 for n in g.nodes.values())


def test_moving_the_attractor_does_not_divide_the_facade_again():
    g = case_01()
    g.value("quiebrasoles")
    g.change("atractor", "x", 15)
    new_ = g.value("quiebrasoles")

    recomputed = {n.name for n in g.nodes.values() if n.evaluations == 2}
    assert recomputed == {"atractor", "distancias", "distancia máxima", "ángulos", "quiebrasoles"}
    # And the result really changed: now the open one is in column 15.
    assert extension(new_.values[6, 15]) == pytest.approx([0.05, 0.40, 1.00], abs=0.05)


def test_changing_the_box_only_replaces():
    g = case_01()
    g.value("quiebrasoles")
    g.change("quiebrasol", "depth", 0.10)
    g.value("quiebrasoles")
    recomputed = {n.name for n in g.nodes.values() if n.evaluations == 2}
    assert recomputed == {"quiebrasol", "quiebrasoles"}


def test_reconnect_an_input():
    g = case_01()
    g.value("quiebrasoles")
    other = g.node("Point", "otro atractor", x=19, y=0, z=11)
    g.change("distancias", "b", other)
    angles = g.value("ángulos")
    assert angles.values[11, 18] == pytest.approx(90.0, abs=6)


# --- A number as a control ---------------------------------------------------

def test_a_number_feeds_several_inputs():
    g = Graph()
    module = g.node("Number", "módulo", value=1.5)
    facade = g.node("Rectangle", "fachada", width=12, height=6, plane='elevation')
    panels = g.node("Grid", "paneles", rectangle=facade, cell_width=module, cell_height=module)
    assert g.value(panels).shape == "fila 4 × columna 8 = 32"
    g.change(module, "value", 3)
    assert g.value(panels).shape == "fila 2 × columna 4 = 8"


def test_a_single_input_does_not_accept_a_data_with_levels():
    g = case_01()
    g.node("Divide", "franjas", rectangle=g.nodes["paneles"], parts=g.nodes["distancias"])
    with pytest.raises(NodeError) as error:
        g.value("franjas")
    assert str(error.value) == (
        "En «franjas» (Dividir): «partes» debe ser un solo valor, "
        "y llega «distancias» con forma fila 12 × columna 20 = 240."
    )


# --- Errores claros ------------------------------------------------------------

def test_the_error_says_in_which_node_it_happened():
    g = case_01()
    g.change("fachada", "width", 20.5)
    with pytest.raises(NodeError) as error:
        g.value("quiebrasoles")
    assert str(error.value) == (
        "En «paneles» (Retícula): El ancho de «fachada» (20,5 m) no se divide en celdas de 1 m: sobran 0,5 m."
    )
    assert error.value.node.name == "paneles"


def test_an_input_is_missing():
    g = Graph()
    g.node("Line", "línea", from_=(0, 0, 0))                    # Line has no factory «to»
    with pytest.raises(NodeError, match="En «línea» \\(Línea\\): falta la entrada «hasta»."):
        g.value("línea")


def test_input_that_does_not_exist():
    g = Graph()
    with pytest.raises(ShapeError, match="«Caja» no tiene la entrada «length». Tiene: ancho, fondo, alto."):
        g.node("Box", width=1, depth=1, length=2)
    assert g.nodes == {}  # the half-made node does not stay


def test_a_cycle_cannot_be_connected():
    g = case_01()
    with pytest.raises(ShapeError) as error:
        g.change("fachada", "width", g.nodes["quiebrasoles"])
    assert str(error.value) == "Conectar «quiebrasoles» a «fachada» haría un círculo: «fachada» ya está antes de «quiebrasoles»."


def test_unique_and_automatic_names():
    g = Graph()
    assert g.node("Box", width=1, depth=1, height=1).name == "caja 1"
    assert g.node("Box", width=1, depth=1, height=1).name == "caja 2"
    with pytest.raises(ShapeError, match="Ya hay un nodo llamado «caja 1»"):
        g.node("Box", "caja 1")


def test_remove_a_node_others_use():
    g = case_01()
    with pytest.raises(ShapeError, match="No se puede quitar «atractor»: lo usan «distancias»"):
        g.remove("atractor")
    g.remove("quiebrasoles")
    assert "quiebrasoles" not in g.nodes


def test_value_that_is_not_a_number():
    g = Graph()
    g.node("Box", "caja", width='width', depth=1, height=1)
    with pytest.raises(NodeError, match="En «caja» \\(Caja\\): «ancho» espera un número"):
        g.value("caja")


# --- The catalogue -------------------------------------------------------------

def test_find_nodes_by_synonym():
    assert node_kind("Lama").name == "Box"
    assert node_kind("grilla").name == "Grid"
    assert node_kind("Spline").name == "Curve through points"
    with pytest.raises(ShapeError, match="No conozco el nodo «Nurbs mágica»"):
        node_kind("Nurbs mágica")


def test_the_essentials_are_few_and_exist():
    """D10: about 30 essentials in view; the rest, by need."""
    from tensela.nodes import ESSENTIALS
    assert len(ESSENTIALS) <= 30
    assert all(n in CATALOG for n in ESSENTIALS)


def test_each_node_explains_what_it_does():
    for kind in CATALOG.values():
        assert kind.help and kind.category, kind.name


def test_old_nodes_open_as_summarise():
    g = case_01()  # it uses «Máximo»
    node = g.nodes["distancia máxima"]
    assert node.kind.name == "Summarise" and node.inputs["operation"] == "maximum"
    assert g.value("distancia máxima").shape == "· (un valor)"


def test_rename_a_node():
    g = case_01()
    g.value("quiebrasoles")
    g.rename("paneles", "módulos")
    assert list(g.nodes)[1] == "módulos"  # it keeps the order
    assert g.value("módulos").name == "módulos"
    assert g.nodes["centros"].inputs["geometry"] is g.nodes["módulos"]
    with pytest.raises(ShapeError, match="Ya hay un nodo llamado «fachada»"):
        g.rename("módulos", "fachada")
    with pytest.raises(ShapeError, match="no puede quedar vacío"):
        g.rename("módulos", "  ")


def test_input_options_are_consistent():
    """Test 08: the inputs with options are chosen from a list; the default value is in it."""
    for kind in CATALOG.values():
        names = {e.name for e in kind.inputs}
        for e in kind.inputs:
            if e.options and e.default is not None and e.default is not REQUIRED:
                assert e.default in e.options, (kind.name, e.name)
            if e.levels_of:
                assert e.levels_of in names, (kind.name, e.name)


def test_a_result_computed_with_old_data_is_not_kept():
    """Computing in another thread: if the graph changes while a node is computed, that result is not kept."""
    from tensela.graph import Cancelled
    g = Graph()
    g.node("Number", "a", value=2)
    f = g.node("Formula", "f", formula="a * 10", a=g.nodes["a"])
    original = f.kind.function

    class KindWhatChanges:          # during the computation, «someone» changes «a» (as the window while computing)
        def __getattr__(self, k):
            return getattr(original_kind, k)

        def function(self, **kw):
            g.change("a", "value", 3)
            return original(**kw)
    original_kind = f.kind
    f.kind = KindWhatChanges()
    with pytest.raises(Cancelled):
        g.value("f")
    assert f._value is None
    f.kind = original_kind
    assert g.value("f").values.item() == 30


def test_compute_all_and_stop():
    g = Graph()
    g.node("Number", "a", value=2)
    g.node("Box", "c", width="abc")
    errors = g.compute_all()
    assert list(errors) == ["c"] and "espera un número" in str(errors["c"])
    version = g.version
    g.stop()                     # what another thread computes with the previous version is no longer kept
    assert g.version == version + 1
