"""Writing and reading values like an architect (D2)."""

import pytest

from tensela.data import ShapeError
from tensela.values import read_value, text_value


@pytest.mark.parametrize('text, value', [
    ("0,4", 0.4), ("0.4", 0.4), ("20", 20), ("−3", -3), ("-0,6", -0.6),
    ("120 cm", 1.2), ("1200 mm", 1.2), ("1,2 m", 1.2), ("90°", 90),
    ("(0; −0,3; 0)", [0, -0.3, 0]), ("[1, 2, 3]", [1, 2, 3]),
    ("sí", True), ("no", False), ("alzado", "alzado"), ("", None),
])
def test_read(text, value):
    assert read_value(text) == value


def test_round_trip():
    for v in (0.4, 20, -0.3, [0, -0.3, 0], True, "alzado"):
        assert read_value(text_value(v)) == v


def test_badly_written_number_in_a_list():
    with pytest.raises(ShapeError, match="no se entiende como número"):
        read_value("(1; dos; 3)")


from tensela.values import label_input, unit_of  # noqa: E402


def test_labels_with_accents():
    assert label_input("geometria") == "geometría"
    assert label_input("ancho_celda") == "ancho celda"
    assert label_input("posicion") == "posición"


def test_units_of_a_new_slider():
    from tensela.project_file import control_for
    from test_graph import case_01
    assert unit_of("giro") == "°" and unit_of("ancho") == "m" and unit_of("columnas") == ""
    g = case_01()
    c = control_for(g, "quiebrasol", "depth")
    assert c.unit == "m" and c.step <= 0.01 and c.maximum < 1      # a small size: fine step, short range
    g.change("quiebrasoles", "rotation", 30)
    c = control_for(g, "quiebrasoles", "rotation")
    assert (c.unit, c.minimum, c.maximum, c.step) == ("°", -180, 180, 1)


# --- Feet and inches (Delivery 5) ---------------------------------------------------

@pytest.mark.parametrize('text, metres', [
    ("12' 6 1/2\"", 3.8227), ("12'-6\"", 3.81), ("4.5'", 1.3716), ("4,5'", 1.3716), ("150\"", 3.81),
    ("1/2\"", 0.0127), ("6 1/2\"", 0.1651), ("-3'", -0.9144), ("12'", 3.6576)])
def test_it_is_written_in_feet_and_inches(text, metres):
    from tensela.values import read_value
    assert read_value(text) == pytest.approx(metres)


def test_a_plain_number_is_not_imperial():
    from tensela.values import read_imperial
    assert read_imperial("12") is None and read_imperial("alzado") is None


@pytest.mark.parametrize('metres, text', [
    (3.81, "12'-6\""), (0.0127, "1/2\""), (0.3048, "1'-0\""), (2.4, "7'-10 1/2\""), (18.0, "59'-0 11/16\""), (0.0, "0\""), (-1.0, "−3'-3 3/8\"")])
def test_it_shows_as_on_a_drawing(metres, text):
    from tensela.values import text_imperial
    assert text_imperial(metres) == text


def test_only_lengths_show_in_feet(monkeypatch):
    from tensela import values as values
    monkeypatch.setattr(values, "UNIT", "ft-in")
    assert values.text_of("ancho", 0.3048) == "1'-0\""
    assert values.text_of("columnas", 12) == "12"
    assert values.text_of("giro", 45) == "45"


@pytest.mark.parametrize('unit, decimals, text', [
    ("m", None, "0,4 m"), ("cm", None, "40 cm"), ("mm", None, "400 mm"), ("ft", 2, "1,31'"), ("in", 1, "15,7\""),
    ("m", 2, "0,40 m"), ("cm", 0, "40 cm")])
def test_lengths_in_the_chosen_unit(monkeypatch, unit, decimals, text):
    from tensela import values as values
    monkeypatch.setattr(values, "UNIT", unit)
    monkeypatch.setattr(values, "DECIMALS", decimals)
    assert values.text_length(0.4) == text


@pytest.mark.parametrize('unit, written, metres', [
    ("cm", "40", 0.4), ("mm", "400", 0.4), ("ft-in", "12", 0.3048), ("ft", "2", 0.6096),
    ("cm", "1,2 m", 1.2), ("m", "40", 40.0), ("cm", "4'", 1.2192)])
def test_a_plain_number_is_read_in_the_chosen_unit(monkeypatch, unit, written, metres):
    from tensela import values as values
    monkeypatch.setattr(values, "UNIT", unit)
    assert values.read_length(written) == pytest.approx(metres)


def test_the_inch_fraction_is_chosen(monkeypatch):
    from tensela import values as values
    monkeypatch.setattr(values, "FRACTION", 4)
    assert values.text_imperial(0.0127) == '1/2"' and values.text_imperial(0.01) == '1/2"'


@pytest.mark.parametrize('text, numbers', [
    ("2,-2", [2, -2]), ("2, -2", [2, -2]), ("2 -2", [2, -2]), ("2; -2", [2, -2]), ("0,5", [0.5]),
    ("0,25, 0,75", [0.25, 0.75]), ("0,25; 0,75", [0.25, 0.75]), ("0,0,0", [0, 0, 0]), ("8 0 0", [8, 0, 0]),
    ("(1; 2; 3)", [1, 2, 3]), ("120 cm", [1.2]), ("hola", None),
])
def test_several_numbers_are_written_however_they_come(text, numbers):
    from tensela.values import read_numbers
    assert read_numbers(text) == (numbers if numbers is None else pytest.approx(numbers))


def test_a_list_written_with_commas_stays_with_semicolons():
    import numpy as np
    from tensela.geometry import line, curve_points
    assert read_value("2,-2") == "2; −2" and read_value("0,25, 0,75") == "0,25; 0,75"
    assert read_value("0,0,0") == [0, 0, 0]                                  # three: a point
    p = curve_points(line((0, 0, 0), (10, 0, 0)), mode='distance', positions=read_value("2, -2"))
    assert np.allclose(p.values[:, 0], [2, 8])
