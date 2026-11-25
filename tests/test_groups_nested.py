"""Group 3.3 of the pending plan: groups with several results, and groups inside groups."""
from pathlib import Path

import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.groups import (INPUT, OUTPUT, RESULT, allowed_inside, group, group_in_project, inner, inner_apply,
                                refresh_kinds, ungroup, ungroup_in_project)
from tensela.project_file import from__text, open_, to_text

CASE = Path(__file__).parent / "data" / "caso_01.json"
ROTATION = ['distances', 'maximum distance', 'angles']


def values(p, name):
    return np.array(p.graph.value(name).values)


def test_a_group_used_outside_twice_gives_two_results():
    p = open_(CASE)
    fins, marker = values(p, 'sun fins'), values(p, 'in front of the facade')
    # «centres» is used by «in front of the facade» outside, and «angles» by «sun fins»
    definition, node = group(p.graph, ['centres', 'distances', 'maximum distance', 'angles'], "rotation", p.export)
    assert list(definition.results) == ['centres', 'angles'] and definition.output == 'centres'
    taker = p.graph.nodes['angles']                                   # the same name, now a Group result
    assert taker.kind.name == RESULT and taker.inputs["group"] is node and taker.inputs["gives"] == 'angles'
    assert p.graph.nodes['sun fins'].inputs["rotation"] is taker
    assert p.graph.nodes['in front of the facade'].inputs["geometry"] is node
    assert np.allclose(values(p, 'sun fins'), fins) and np.allclose(values(p, 'in front of the facade'), marker)
    # the group computes once for both
    p.graph.change('attractor', "x", 2.0)
    p.graph.value('sun fins')
    p.graph.value('in front of the facade')
    assert node.evaluations == 2 and taker.evaluations == 2


def test_two_results_save_open_and_ungroup_with_their_names():
    p = open_(CASE)
    fins = values(p, 'sun fins')
    group_in_project(p, ['centres', 'distances', 'maximum distance', 'angles'], "rotation")
    p.view['angles'] = {"color": "#123456"}
    q = from__text(to_text(p))
    assert q.graph.definitions["rotation"].outputs == {'centres': 'centres', 'angles': 'angles'}
    assert np.allclose(values(q, 'sun fins'), fins)
    new = ungroup_in_project(q, "rotation 1")
    assert new['angles'] == 'angles' and new['centres'] == 'centres'  # back with their own names
    assert q.graph.nodes['sun fins'].inputs["rotation"].name == 'angles'
    assert q.graph.nodes['angles'].kind.name == 'Remap' and q.view['angles'] == {"color": "#123456"}
    assert np.allclose(values(q, 'sun fins'), fins)
    assert not [n for n in q.graph.nodes.values() if n.kind.name == RESULT]


def test_a_group_result_says_what_the_group_gives():
    p = open_(CASE)
    _, node = group(p.graph, ['centres', 'distances', 'maximum distance', 'angles'], "rotation", p.export)
    p.graph.change('angles', "gives", "angels")
    with pytest.raises(ShapeError, match="«centres», «angles»"):
        p.graph.value('angles')
    one = p.graph.node(RESULT, "alone", group=p.graph.nodes['facade'], gives="x")
    with pytest.raises(ShapeError):
        p.graph.value(one)


def test_inside_a_second_output_makes_a_second_result():
    p = open_(CASE)
    _, node = group(p.graph, ROTATION, "rotation", p.export)
    g, _ = inner(p.graph, node.name)
    assert [n.name for n in g.nodes.values() if n.kind is OUTPUT] == ['salida']
    g.node(OUTPUT.name, "distance", data=g.nodes['distances'])
    g.rename('salida', 'angle')
    definition = inner_apply(p.graph, "rotation", g, edited=node.name)
    assert definition.outputs == {'angle': 'angles', 'distance': 'distances'}
    took = p.graph.node(RESULT, "how far", group=node, gives="distance")
    assert np.allclose(p.graph.value(took).values, p.graph.value('distances').values) \
        if 'distances' in p.graph.nodes else p.graph.value(took).values.max() > 0
    # inside again: a Group output for each result
    g, _ = inner(p.graph, node.name)
    assert sorted(n.name for n in g.nodes.values() if n.kind is OUTPUT) == ['angle', 'distance']


def test_a_group_inside_a_group_is_edited_from_inside():
    p = open_(CASE)
    fins = values(p, 'sun fins')
    small = group_in_project(p, ['maximum distance', 'angles'], "scale angles")
    big = group_in_project(p, ['distances', small.name], "rotation")
    assert np.allclose(values(p, 'sun fins'), fins)
    outer, _ = inner(p.graph, big.name)
    assert "rotation" not in outer.kinds                               # it cannot hold itself
    inner_name = next(n for n, x in outer.nodes.items() if x.kind.name == "scale angles")
    deeper, _ = inner(outer, inner_name, around=["rotation"])
    assert "rotation" not in deeper.kinds and "scale angles" not in deeper.kinds
    # inside the inner one: the angles go up to 60 instead of 90
    remap = next(n for n in deeper.nodes.values() if n.kind.name == 'Remap')
    deeper.change(remap, "to_max", 60.0)
    inner_apply(outer, "scale angles", deeper, edited=inner_name, also=(p.graph,))
    inner_apply(p.graph, "rotation", outer, edited=big.name)
    refresh_kinds(p.graph, [(outer, ["rotation"])])
    after = values(p, 'sun fins')
    assert not np.allclose(after, fins)
    q = from__text(to_text(p))                                         # and it stays so in the file
    assert np.allclose(values(q, 'sun fins'), after)


def test_grouping_and_ungrouping_inside_a_group():
    p = open_(CASE)
    fins = values(p, 'sun fins')
    big = group_in_project(p, ROTATION, "rotation")
    outer, _ = inner(p.graph, big.name)
    _, small = group(outer, ['maximum distance', 'angles'], "scale angles", [])
    inner_apply(p.graph, "rotation", outer, edited=big.name)
    refresh_kinds(p.graph, [(outer, ["rotation"])])
    assert any(spec["type"] == "scale angles" for spec in p.graph.definitions["rotation"].nodes.values())
    assert np.allclose(values(p, 'sun fins'), fins)
    # «rotation» comes first in the file, and its output is the group made later inside it: it opens all the same
    assert list(p.graph.definitions) == ["rotation", "scale angles"]
    assert np.allclose(values(from__text(to_text(p)), 'sun fins'), fins)
    with pytest.raises(ShapeError):                                     # Group inputs and outputs stay where they are
        group(outer, ['distances', 'centres'], "with an input", [])
    ungroup(outer, small.name)
    inner_apply(p.graph, "rotation", outer, edited=big.name)
    refresh_kinds(p.graph, [(outer, ["rotation"])])
    assert not any(spec["type"] == "scale angles" for spec in p.graph.definitions["rotation"].nodes.values())
    assert np.allclose(values(p, 'sun fins'), fins)


def test_a_group_cannot_go_inside_one_that_holds_it():
    p = open_(CASE)
    _, small = group(p.graph, ['maximum distance', 'angles'], "scale angles", p.export)
    _, big = group(p.graph, ['distances', small.name], "rotation", p.export)
    allowed = allowed_inside(p.graph.definitions, p.graph.kinds, ["scale angles"])
    assert "rotation" not in allowed and "scale angles" not in allowed
    g, _ = inner(p.graph, big.name)
    deeper, _ = inner(g, next(n for n, x in g.nodes.items() if x.kind.name == "scale angles"), around=["rotation"])
    assert INPUT.name in deeper.kinds and "rotation" not in deeper.kinds
