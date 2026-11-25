"""The interface language. The program's base is English; Spanish (and, later, other languages) is a translation.

Every visible text goes through :func:`tr`, written in English; in Spanish it is looked up in
``translations/es.py``. Texts with data are translated with their placeholders and filled in afterwards:

    tr("Written: {path}").format(path=path)

Project files do not change with the language: they keep the internal names (of the nodes, the inputs, the
options), which are the English ones.
"""
from __future__ import annotations

LANGUAGES = {"es": "Español", "en": "English"}
#: The language set («es» or «en»); the window sets it at start-up (Preferences).
LANGUAGE = "es"


def system_language() -> str:
    """The language of the computer, as Tensela speaks it: Spanish if the system is in Spanish, English otherwise.
    It is where a new installation starts; Preferences can change it."""
    import os
    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(name, "")
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return "es" if value.lower().startswith("es") else "en"
    return "en"


def in_spanish(*texts: str) -> list[str]:
    """The texts in Spanish, whatever the language set (the node finder searches in both)."""
    from .translations import es
    return [es.TEXTS.get(t, t) for t in texts]


def on_original(text: str, options) -> str:
    """An option written in the language set («alzado») → as the file keeps it («elevation»)."""
    for o in options:
        if text == o or text.lower() == tr(o).lower():
            return o
    return text


def tr(text: str) -> str:
    """`texto` (English) in the current language; if the translation is missing, the original."""
    if not text:
        return text
    if LANGUAGE == "es":
        from .translations import es
        return es.TEXTS.get(text, text)
    return text


def comma(text: str) -> str:
    """A number written with a point, with the decimal comma in Spanish (3,5); in English it keeps the point (3.5).
    When reading, both are valid."""
    return text.replace(".", ",") if LANGUAGE == "es" else text
