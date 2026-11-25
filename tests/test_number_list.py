"""Number with a list written by hand (general comments, batch 3, no. 5)."""

import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.nodes import visible_input, number


def test_a_number_is_still_a_number():
    d = number(3.5)
    assert d.levels == () and float(d.values) == 3.5


def test_a_hand_written_list_is_a_level_with_its_name():
    d = number("3,5; 3; 3; 4", level="piso")
    assert d.shape == "piso 4" and list(d.values) == [3.5, 3, 3, 4]


def test_with_units_and_in_parentheses():
    assert list(number("(120 cm; 1,5 m; 900 mm)", level="vano").values) == pytest.approx([1.2, 1.5, 0.9])


def test_an_already_read_list():
    assert number([1, 2, 3]).shape == "valor 3"


def test_a_text_that_is_not_a_number_gives_a_clear_error():
    with pytest.raises(ShapeError, match="sepáralos con «;»"):
        number("tres")


def test_the_level_only_shows_with_a_list():
    g = Graph()
    g.node("Number", "alturas", value=3.0)
    kind = g.nodes["alturas"].kind
    assert not visible_input(g.nodes["alturas"], kind.input_("nivel"))
    g.change("alturas", "value", "3,5; 3; 4")
    assert visible_input(g.nodes["alturas"], kind.input_("nivel"))


def test_different_floor_heights_in_a_graph():
    g = Graph()
    g.node("Number", "alturas", value="4,5; 3; 3; 3,2", level="piso")
    g.node("Formula", "cota", formula="a * 2", a=g.nodes["alturas"])
    assert g.value("cota").shape == "piso 4"
    assert np.allclose(g.value("cota").values, [9, 6, 6, 6.4])
