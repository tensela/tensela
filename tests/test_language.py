"""Spanish and English (Delivery 5): no text of the interface stays untranslated."""

import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from translation_keys import missing  # noqa: E402

from tensela import language as language  # noqa: E402
from tensela.translations import es  # noqa: E402
from tensela.nodes import CATALOG  # noqa: E402


def test_every_interface_text_has_its_translation():
    without_spanish, without_english = missing()
    assert not without_spanish, without_spanish
    assert not without_english, without_english


#: Texts whose braces are what the user types (the Text node: {value} is {valor} in Spanish), not filled in.
TYPED_BRACES = ('of {value}', 'numbers to write with {value}: one for each element (an area, a length)',
                '{n}: the number of each element, as the 3D view numbers it · {floor}, {row}…: its number in that level '
                '· {value}: the number given in «value» · A; B; C: one text for each element, in order · |: a new line · '
                'anything else, as it is: P{floor}-{n}',
                CATALOG['Text'].help)    # its examples, with the levels in the language of the interface


def test_placeholders_are_the_same_in_both_languages():
    for a, b in es.TEXTS.items():
        if a in TYPED_BRACES:
            continue
        assert set(re.findall(r"\{\w+\}", a)) == set(re.findall(r"\{\w+\}", b)), a
    assert all(a in es.TEXTS for a in TYPED_BRACES)


def test_ampersand_shortcuts_are_kept():
    for a, b in es.TEXTS.items():
        assert ("&" in a) == ("&" in b), a


def test_tr_follows_the_language(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert language.tr("Save…") == "Guardar…"
    monkeypatch.setattr(language, "LANGUAGE", "en")
    assert language.tr("Save…") == "Save…"
    assert language.tr("something untranslated") == "something untranslated"


def test_the_finder_finds_in_both_languages(monkeypatch):
    from tensela.ui.editor import find_kinds
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert find_kinds("box")[0].name == "Box"
    assert find_kinds("caja")[0].name == "Box"


def test_input_labels_are_translated(monkeypatch):
    from tensela.values import label_input
    monkeypatch.setattr(language, "LANGUAGE", "en")
    assert label_input("ancho_celda") == "cell width"
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert label_input("ancho_celda") == "ancho celda"


def test_an_option_written_in_spanish_is_saved_as_in_the_file(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert language.on_original("Alzado", ("plan", "elevation", "side elevation")) == "elevation"
    assert language.on_original("elevation", ("plan", "elevation", "side elevation")) == "elevation"
    assert language.on_original("otra cosa", ("plan",)) == "otra cosa"


def test_engine_errors_come_out_in_the_language_set(monkeypatch):
    from tensela.project_file import from__dict
    from tensela.data import ShapeError
    from tensela.formula import formula
    from tensela.geometry import rectangle
    from tensela.graph import Graph

    def message(f):
        with pytest.raises(ShapeError) as e:
            f()
        return str(e.value)

    monkeypatch.setattr(language, "LANGUAGE", "en")
    assert message(lambda: rectangle(1, 1, plane='techo')) == \
        "I don't know the plane “techo”. Options: plan, elevation, side elevation."
    assert "is not a variable of the formula" in message(lambda: formula("z + 1"))
    assert message(lambda: from__dict({"parametrico": 1, "nodos": {"a": {}}})).startswith("Node “a” is missing")
    g = Graph()
    g.node("Desplazar", "mover")
    error = message(lambda: g.value("mover"))
    assert error.startswith("In “mover” (Move): the input “geometry” is missing"), error
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert message(lambda: rectangle(1, 1, plane='techo')) == \
        "No conozco el plano «techo». Opciones: planta, alzado, lateral."


def test_the_name_of_a_new_node_in_the_interface_language():
    from tensela import language as language
    from tensela.graph import Graph
    before = language.LANGUAGE
    try:
        language.LANGUAGE = "en"
        assert Graph().node("Drawn curve").name == "drawn curve 1"
    finally:
        language.LANGUAGE = before
    assert Graph().node("Drawn curve").name == "curva dibujada 1"


def test_level_names_show_in_the_language_and_are_saved_as_always(monkeypatch):
    """«level: segment» shows «tramo» in Spanish; writing «tramo» saves «segment» (the files do not change)."""
    from tensela.values import text_of
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert text_of("level", "segment") == "tramo" and text_of("rows_level", "row") == "fila"
    assert text_of("level", "mis pisos") == "mis pisos"                  # a name of one's own, as it is
    assert language.on_original("tramo", ["segment"]) == "segment"
