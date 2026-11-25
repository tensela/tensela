"""The shortcuts of the menus, in short and in Tensela's language."""

import pytest

pytest.importorskip("PySide6")

from tensela import language as language  # noqa: E402
from tensela.ui.menus import text_shortcut  # noqa: E402


def test_shortcuts_are_abbreviated_in_spanish_and_english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "es")
    assert text_shortcut("Ctrl+Shift+R") == "Ctrl+Mayús+R"
    assert text_shortcut("Del") == "Supr"
    assert text_shortcut("Ctrl++") == "Ctrl++"
    assert text_shortcut("Ctrl+K, Ctrl+S") == "Ctrl+K, Ctrl+S"
    assert text_shortcut("") == ""
    monkeypatch.setattr(language, "LANGUAGE", "en")
    assert text_shortcut("Ctrl+Shift+R") == "Ctrl+Shift+R"
    assert text_shortcut("Return") == "Enter"
