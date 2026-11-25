"""Qt only calls its own names: a method meant to replace one of Qt's must keep that name exactly.

When the code was moved to English, «contextMenuEvent» became «context_menu_event» and the right click on the
canvas stopped doing anything (prueba 71). This catches that kind of slip.
"""
import importlib
import inspect
import pkgutil
import re

from PySide6 import QtWidgets

from tensela import ui
from tensela.graph import Graph
from tensela.ui.editor import Editor, editable

QT_EVENTS = {n for c in (QtWidgets.QWidget, QtWidgets.QGraphicsView, QtWidgets.QGraphicsItem)
             for n in dir(c) if n.endswith("Event") or n == "itemChange"}


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()


def test_no_qt_event_was_renamed_by_mistake():
    snake = {_snake(n): n for n in QT_EVENTS}
    for info in pkgutil.iter_modules(ui.__path__):
        module = importlib.import_module(f"tensela.ui.{info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__:
                continue                                # (classes of other libraries, imported here)
            for name in vars(cls):
                assert name not in snake, f"{cls.__name__}.{name} should be {snake[name]}"


def test_the_canvas_answers_the_right_click():
    assert "contextMenuEvent" in vars(Editor)


def test_nodes_with_an_editor_of_their_own():
    g = Graph()
    assert editable(g.node("Code", "code"))
    assert editable(g.node("Drawn curve", "drawn"))
    assert not editable(g.node("Rectangle", "rect"))
