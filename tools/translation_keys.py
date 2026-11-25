"""Every text the interface translates. The base is English: the tr("…") texts of the code, the help texts and
descriptions of the node catalogue and of the components are in English and need their Spanish in
translations/es.py. Used by tests/test_language.py.

    .venv/bin/python tools/translation_keys.py
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "tensela"


def de_tr() -> set[str]:
    keys = set()
    for filepath in [*ROOT.glob("*.py"), *(ROOT / "ui").glob("*.py")]:      # the engine (its errors) and the window
        for n in ast.walk(ast.parse(filepath.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                keys.add(n.args[0].value)
    return keys


def help_texts_catalog() -> set[str]:
    """The help texts and descriptions of the catalog (English)."""
    from tensela.nodes import CATALOG
    keys = set()
    for t in CATALOG.values():
        keys.add(t.help)
        keys |= {e.help for e in t.inputs if e.help}
    return keys


def names_catalog() -> set[str]:
    """The names of the catalog: nodes, categories, outputs, inputs, options (English)."""
    from tensela.nodes import CATALOG
    keys = set()
    for t in CATALOG.values():
        keys |= {t.name, t.category, t.output}
        for e in t.inputs:
            keys.add(e.name.replace("_", " "))
            keys |= set(e.options)
    return keys


def catalog() -> set[str]:
    return help_texts_catalog() | names_catalog()


def from_components() -> set[str]:
    """Texts translated when shown (tables of options and help texts, styles, kinds of data)."""
    from tensela.ui import dialogs as dialogs, viewer as viewer
    keys = set(viewer.STYLE_NAMES.values()) | set(viewer.HELP_TEXTS_STYLE_NAME.values())
    keys |= {text for _, text, _ in dialogs.DialogDxf.VIEWS} | set(dialogs.DialogDxf.HELP_TEXTS_VIEW.values())
    keys |= set(dialogs.DialogDxf.UNITS) | set(dialogs.DialogDxf.HELP_TEXTS_VIEW)
    keys |= {"Sober", "Vivid", "Like the system", "Light", "Dark", "3D, the model", "2D, plan or elevation",
               "White", "Transparent", "Tensela", "Dots",
               "Square grid", "Plain", "Recommended",
               "Neutral node cards, with a strip of colour",
               "Node headers fully coloured",
               
               'Middle button: orbit · Shift + middle: pan · Ctrl + middle or wheel: zoom',
               # What each data is (Data)
               "number", "yes/no", "point", "rectangle", "box", "block", "curve", "closed curve", "surface",
               "frame"}
    from tensela.ui import navigation as navigation
    keys |= set(navigation.HELP_TEXTS.values())
    keys |= {"General", "3D view", "Nodes", "Units", "Interaction", "Language", "Appearance", "On opening",
               "Node cards", "Canvas", "Lengths", "Mouse in the 3D view", "Keyboard shortcuts",
               "Show in", "Decimals", "Inch fraction", "Like", "Style", "Mode", "Background"}
    return keys


def all_() -> set[str]:
    return de_tr() | catalog() | from_components()


def missing() -> tuple[list[str], list[str]]:
    """(English texts without Spanish, Spanish internal names without English)."""
    from tensela.translations import es
    texts = de_tr() | help_texts_catalog() | from_components()
    without_spanish = sorted(t for t in texts | names_catalog() if t not in es.TEXTS)
    without_english = []                                 # (the base is English: nothing to translate into it)
    return without_spanish, without_english


if __name__ == "__main__":
    a, b = missing()
    print(f"without Spanish: {len(a)}")
    for f in a + b:
        print(repr(f))
