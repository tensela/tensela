"""Groups of nodes (Delivery 6): group, compute, save, ungroup."""

from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import to_text, open_, from__text, fragment, paste_fragment
from tensela.data import ShapeError
from tensela.groups import group, group_in_project, ungroup, ungroup_in_project

CASE = Path(__file__).parent / "data" / "caso_01.json"
ROTATION = ['distances', 'maximum distance', 'angles']        # from the centre of each panel to the attractor → its rotation


def _sun_fins(p):
    return np.array(p.graph.value('sun fins').values)


def test_grouping_gives_the_same_result_and_its_inputs_are_what_is_outside():
    p = open_(CASE)
    before = _sun_fins(p)
    definition, node = group(p.graph, ROTATION, "giro por atractor", p.export)
    assert node.name == "giro por atractor 1" and node.kind.category == "Groups"
    assert set(definition.inputs) == {'centres', 'attractor'} and definition.output == 'angles'
    assert {e: o.name for e, o in node.connections.items()} == {'centres': 'centres', 'attractor': 'attractor'}
    assert not set(ROTATION) & set(p.graph.nodes)
    assert p.graph.nodes['sun fins'].inputs["rotation"] is node         # whoever used its output uses it
    assert np.allclose(_sun_fins(p), before)
    # Moving the attractor still changes the result (the inputs arrive inside).
    p.graph.change('attractor', "x", 1.0)
    assert not np.allclose(_sun_fins(p), before)


def test_the_group_saves_opens_and_ungroups():
    p = open_(CASE)
    before = _sun_fins(p)
    group_in_project(p, ROTATION, "giro por atractor")
    text = to_text(p)
    assert '"groups"' in text and '"type": "giro por atractor"' in text
    q = from__text(text)
    assert np.allclose(_sun_fins(q), before)
    new = ungroup_in_project(q, "giro por atractor 1")
    assert set(new) == set(ROTATION) and "giro por atractor 1" not in q.graph.nodes
    assert np.allclose(_sun_fins(q), before)
    assert q.graph.nodes['sun fins'].inputs["rotation"].name == new['angles']


def test_two_nodes_of_the_same_group_with_different_inputs():
    p = open_(CASE)
    group(p.graph, ROTATION, "giro por atractor", p.export)
    g = p.graph
    g.node("Point", "otro atractor", x=20.0, y=0.0, z=0.0)
    other = g.node("giro por atractor", centres=g.nodes['centres'], attractor=g.nodes["otro atractor"])
    a, b = g.value("giro por atractor 1"), g.value(other)
    assert a.name == "giro por atractor 1" and b.name == other.name
    assert not np.allclose(a.values, b.values)


def test_a_group_gives_a_single_thing():
    p = open_(CASE)
    with pytest.raises(ShapeError, match="dos o más"):
        group(p.graph, ['centres'], "solo", p.export)
    with pytest.raises(ShapeError, match="nodo de Tensela"):
        group(p.graph, ROTATION, "Caja", p.export)


def test_copying_a_group_node_carries_its_definition():
    p = open_(CASE)
    group(p.graph, ROTATION, "giro por atractor", p.export)
    frag = fragment(p.graph, ["giro por atractor 1"])
    assert "giro por atractor" in frag["groups"]
    other = open_(CASE)                                   # another project, without the group
    new = paste_fragment(other.graph, frag)
    assert other.graph.nodes[new["giro por atractor 1"]].kind.name == "giro por atractor"


def test_inside_sliders_move_group_inputs():
    p = open_(CASE)
    keys = {c.key for c in p.controls}
    assert 'angles.to_min' in keys
    before = _sun_fins(p)
    node = group_in_project(p, ROTATION, "giro por atractor")
    control = next(c for c in p.controls if c.node == node.name and c.input_ == "to_min")
    assert node.kind.input_("to_min").default == node.inputs["to_min"]
    assert np.allclose(_sun_fins(p), before)
    p.graph.change(node, control.input_, node.inputs["to_min"] + 20)       # move the slider
    assert not np.allclose(_sun_fins(p), before)
    # And on ungrouping, it goes back to its node, with the new value.
    new = ungroup_in_project(p, node.name)
    control = next(c for c in p.controls if c.input_ == "to_min")
    assert control.node == new['angles']
    assert not np.allclose(_sun_fins(p), before)


def test_the_finder_offers_the_project_groups_first():
    pytest.importorskip("PySide6")
    from tensela.ui.editor import find_kinds
    p = open_(CASE)
    group(p.graph, ROTATION, "giro por atractor", p.export)
    assert find_kinds("", p.graph.kinds)[0].name == "giro por atractor"
    assert [t.name for t in find_kinds("giro", p.graph.kinds)][0] == "giro por atractor"
    assert "giro por atractor" not in [t.name for t in find_kinds("giro")]       # only in its project


def test_inside_it_computes_with_what_arrives_and_edits_apply():
    from tensela.groups import INPUT, OUTPUT, inner_apply, inner
    p = open_(CASE)
    node = group_in_project(p, ROTATION, "giro por atractor")
    outside = p.graph.value(node).values.copy()
    g, positions = inner(p.graph, node.name)
    assert {n.name for n in g.nodes.values() if n.kind is INPUT} == {'centres', 'attractor', "to_min", "to_max"}
    assert [n.name for n in g.nodes.values() if n.kind is OUTPUT] == ["salida"]
    assert set(positions) in (set(), set(g.nodes))               # all, or none (the canvas arranges them)
    assert np.allclose(g.value("salida").values, outside)                  # with the real data
    before = _sun_fins(p)
    # A new input, «tope», that replaces the computed maximum of the remap.
    g.node(INPUT.name, "tope", value=40.0)
    g.change('angles', "from_max", g.nodes["tope"])
    g.remove('maximum distance')
    definition = inner_apply(p.graph, "giro por atractor", g, positions)
    assert "tope" in definition.inputs and definition.values["tope"] == 40.0
    assert 'maximum distance' not in definition.nodes
    assert node.inputs["tope"] == 40.0                                  # the outside node has the new input
    assert not np.allclose(_sun_fins(p), before)                       # and it recomputes
    q = from__text(to_text(p))                                           # and it is saved
    assert np.allclose(_sun_fins(q), _sun_fins(p))


def test_inside_an_output_is_needed():
    from tensela.groups import inner_apply, inner
    p = open_(CASE)
    node = group_in_project(p, ROTATION, "giro por atractor")
    g, _ = inner(p.graph, node.name)
    g.remove("salida")
    with pytest.raises(ShapeError, match="Salida del grupo"):
        inner_apply(p.graph, "giro por atractor", g)


def test_the_finder_separates_the_groups_and_picks_with_one_click():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from tensela.ui.editor import Finder
    QApplication.instance() or QApplication([])
    p = open_(CASE)
    group(p.graph, ROTATION, "giro por atractor", p.export)
    b = Finder(None, p.graph.kinds)
    texts = [b.list_.item(i).text() for i in range(b.list_.count())]
    assert texts[0] == "GRUPOS DEL PROYECTO" and texts[1] == "giro por atractor" and texts[2] == "NODOS"
    assert b.list_.currentRow() == 1                               # the first one that can be chosen
    chosen = []
    b.chosen.connect(lambda kind, by: chosen.append(kind.name))
    b.list_.itemClicked.emit(b.list_.item(3))                      # one click is enough
    assert chosen == [b.list_.item(3).data(Qt.ItemDataRole.UserRole)[0].name]
    without = Finder(None, {})
    assert without.list_.item(0).flags() & Qt.ItemFlag.ItemIsSelectable    # without groups, without headings


def test_a_new_input_keeps_what_was_written_and_can_be_renamed():
    from tensela.groups import INPUT, inner_apply, inner, refresh_inputs, rename_input
    p = open_(CASE)
    node = group_in_project(p, ROTATION, "giro por atractor")
    other = p.graph.node("giro por atractor", centres=p.graph.nodes['centres'], attractor=p.graph.nodes['attractor'])
    g, _ = inner(p.graph, node.name)
    g.node(INPUT.name, "giro máximo")                               # new: it starts at 0, without error
    inner_apply(p.graph, "giro por atractor", g, edited=node.name)
    assert node.inputs["giro máximo"] == 0.0
    g.change("giro máximo", "value", 45.0)                             # 45 is written inside
    g.change('angles', "to_max", g.nodes["giro máximo"])
    inner_apply(p.graph, "giro por atractor", g, edited=node.name)
    refresh_inputs(p.graph, node.name, g)                         # what the window does on recomputing
    assert node.inputs["giro máximo"] == 45.0 and g.nodes["giro máximo"].inputs["value"] == 45.0
    assert other.inputs["giro máximo"] == 45.0                         # the other one did not have one of its own
    # Renaming the input inside: outside its value is kept.
    g.rename("giro máximo", "tope")
    rename_input(p.graph, "giro por atractor", "giro máximo", "tope")
    inner_apply(p.graph, "giro por atractor", g, edited=node.name)
    assert node.inputs["tope"] == 45.0 and "giro máximo" not in node.inputs


def test_the_library_saves_a_group_and_another_project_uses_it(tmp_path):
    from tensela import library as library
    p = open_(CASE)
    node = group_in_project(p, ROTATION, "giro por atractor")
    filepath = library.save(p.graph, "giro por atractor", help="Gira cada panel según su distancia al atractor",
                              where=tmp_path)
    assert filepath.exists() and library.names(tmp_path) == ["giro por atractor"]
    with pytest.raises(FileExistsError):
        library.save(p.graph, "giro por atractor", where=tmp_path)
    kinds = library.kinds(tmp_path)
    assert kinds["giro por atractor"].help == "Gira cada panel según su distancia al atractor"
    # Another project: it brings it and uses it, with the same result.
    other = open_(CASE)
    library.bring(other.graph, "giro por atractor", tmp_path)
    g = other.graph
    new_ = g.node("giro por atractor", centres=g.nodes['centres'], attractor=g.nodes['attractor'],
                   to_min=node.inputs["to_min"], to_max=node.inputs["to_max"])
    assert np.allclose(g.value(new_).values, p.graph.value(node).values)
    assert '"groups"' in to_text(other)                     # and it stays saved in that project
    (tmp_path / "roto.json").write_text("{no es json", encoding="utf-8")
    assert library.names(tmp_path) == ["giro por atractor"]      # what cannot be read is skipped
    with pytest.raises(ShapeError):
        library.bring(other.graph, "no existe", tmp_path)


def test_a_group_placed_from_its_definition_ungroups_though_it_keeps_where_its_inputs_were():
    """Notes of test 11: the definition also keeps where its inputs and its output were drawn inside the group
    («centres», «output»…, saved on entering it); ungrouping a node placed with Tab took them for nodes and failed
    half way."""
    p = open_(CASE)
    g = p.graph
    definition, node = group(g, ROTATION, "giro por atractor", p.export)
    definition.positions = {"distances": [1100, 150], "maximum distance": [1500, 150], "angles": [1900, 150],
                            "centres": [750, 150], "attractor": [750, 250], "output": [2200, 150]}
    g.node("giro por atractor", "a turn", centres=g.nodes["centres"], attractor=g.nodes["attractor"])
    p.positions["a turn"] = [3000, 600]
    new = ungroup_in_project(p, "a turn")
    assert "a turn" not in g.nodes
    assert set(new) == set(definition.nodes)
    assert all(name in p.positions for name in new.values())               # each inside node, at its place


def test_ungrouping_the_last_node_of_a_group_forgets_the_group():
    """Notes of test 126: a group no node uses any more leaves the project's groups (not offered with Tab, its name
    free again); while another node of it is left, it stays."""
    p = open_(CASE)
    g = p.graph
    group_in_project(p, ROTATION, "group 1")
    g.node("group 1", "another", centres=g.nodes["centres"], attractor=g.nodes["attractor"])
    ungroup_in_project(p, "group 1 1")
    assert "group 1" in g.definitions and "group 1" in g.kinds              # «another» still uses it
    ungroup_in_project(p, "another")
    assert "group 1" not in g.definitions and "group 1" not in g.kinds
    names = [n for n in g.nodes if n.startswith(("distances", "maximum distance", "angles"))][:3]
    group_in_project(p, names, "group 1")                                    # the name is free again
    assert "group 1" in g.definitions


def test_a_group_without_a_description_writes_its_own(monkeypatch):
    """Notes of test 126: what a group does, if nobody wrote it: what it takes, what it gives and its nodes (shown
    when the pointer rests on it, in Tab and on the card)."""
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")
    p = open_(CASE)
    node = group_in_project(p, ROTATION, "turn")                            # (its sliders become inputs too)
    assert node.kind.help == ("Takes: centres, attractor, to min and to max. Gives: value. "
                              "Inside: Distance, Summarise, Remap.")
    p.graph.definitions["turn"].help = "Turns each fin towards the attractor."
    from tensela.groups import group_kind
    assert group_kind(p.graph.definitions["turn"], p.graph.kinds).help == "Turns each fin towards the attractor."
