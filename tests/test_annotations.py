"""The annotations of the node canvas: their settings are read and written (only those that were changed)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from tensela.ui import annotations as annotations  # noqa: E402


def test_factory_settings_leave_the_file_unchanged():
    for d in ({"type": "text", "x": 0, "y": 0, "color": "yellow", "width": 220, "text": "hola", "size": 11},
              {"type": "arrow", "x": 0, "y": 0, "color": "red", "x2": 140, "y2": 0},
              {"type": "frame", "x": 0, "y": 0, "color": "blue", "width": 420, "height": 260, "text": "Fachada"}):
        assert annotations.from__dict(d).a_dict() == d


def test_changed_settings_are_saved_and_read():
    text = {"type": "text", "x": 0, "y": 0, "color": "green", "background": False, "border": False,
            "typeface": "serif", "italic": True, "text_colour": "white", "width": 220, "text": "", "size": 24}
    arrow = {"type": "arrow", "x": 0, "y": 0, "color": "orange", "start": "dot", "end": "swiss",
             "weight": "thick", "line": "dashed", "x2": 100, "y2": 50}
    frame = {"type": "frame", "x": 0, "y": 0, "color": "violet", "background": "none", "border": "red",
             "line": "dotted", "title": "text", "typeface": "monospace", "title_size": 16,
             "width": 300, "height": 200, "text": "Planta"}
    for d in (text, arrow, frame):
        assert annotations.from__dict(d).a_dict() == d


def test_notes_saved_before_are_read():
    """The notes of the files of before (Spanish keys and values) are read and saved in English."""
    old = {"tipo": "marco", "x": 0, "y": 0, "color": "violeta", "fondo": "ninguno", "borde": "rojo",
           "linea": "punteada", "titulo": "texto", "letra": "monoespaciada", "tamaño_titulo": 16,
           "ancho": 300, "alto": 200, "texto": "Planta"}
    assert annotations.from__dict(old).a_dict() == {
        "type": "frame", "x": 0, "y": 0, "color": "violet", "background": "none", "border": "red", "line": "dotted",
        "title": "text", "typeface": "monospace", "title_size": 16, "width": 300, "height": 200, "text": "Planta"}
    arrow = annotations.from__dict({"tipo": "flecha", "inicio": "punto", "fin": "suiza", "grosor": "grueso"})
    assert arrow.settings["start"] == "dot" and arrow.settings["end"] == "swiss" and arrow.settings["weight"] == "thick"


def test_an_odd_setting_in_the_file_does_not_break():
    item = annotations.from__dict({"type": "arrow", "x": 0, "y": 0, "end": 3, "weight": "enorme"})
    assert item.settings["end"] == "classic"            # a number where a name goes: the factory one
    assert item.a_dict()["weight"] == "enorme"           # an unknown name is kept; it is drawn «medium»
    item.put("end", "dot")
    assert item.a_dict()["end"] == "dot"


def test_text_only():
    item = annotations.from__dict({"type": "text", "text": "hola"})
    item.only_text(True)
    assert item.a_dict()["background"] is False and item.a_dict()["border"] is False
    item.only_text(False)
    assert "background" not in item.a_dict()