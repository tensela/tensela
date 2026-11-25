"""The window's components (Delivery 5, step 2). Skipped if the interface is not there."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from tensela.ui.widgets import Switch, Panel, Segmented, Cards  # noqa: E402


def test_segmented_chooses_and_reports():
    s = Segmented([("a", "A", None), ("b", "B", None)], "b")
    seen = []
    s.change.connect(seen.append)
    assert s.value() == "b"
    s._group.button(0).click()
    assert s.value() == "a" and seen == ["a"]


def test_cards_with_icon():
    t = Cards([("plan", "Plan", "from_above"), ("south elevation", "South", "from_south")], "south elevation")
    assert t.value() == "south elevation"
    t.put("plan")
    assert t.value() == "plan"


def test_switch_is_a_yes_or_no():
    i = Switch("Ver en 3D", True)
    assert i.isChecked()
    i.click()
    assert not i.isChecked() and i.sizeHint().width() > Switch.WIDTH


def test_panel_with_title_and_body():
    p = Panel("Datos")
    assert p.title.text() == "Datos" and p.body is not None


def test_data_table_chooses_a_node_and_exports():
    from tensela.ui.widgets import TableDataItems
    table = TableDataItems()
    table.put([("fachada", "Rectángulo", "Formas", "rectángulo", "1", ""),
                 ("paneles", "Retícula", "Dividir", "rectángulo", "fila 12 × columna 20 = 240", "recalculado")])
    chosen = []
    table.chosen.connect(chosen.append)
    assert table.names() == ["fachada", "paneles"]
    table.itemClicked.emit(table.topLevelItem(1), 0)
    assert chosen == ["paneles"]
    csv = table.as_text(",").splitlines()
    assert csv[0] == "Nodo,Tipo,Qué es,Forma" and csv[2] == "paneles,Retícula,rectángulo,fila 12 × columna 20 = 240"


def test_the_box_reads_comma_and_point_as_decimal():
    from tensela.ui.window import CellNumber
    c = CellNumber()
    c.setRange(-1e9, 1e9)
    c.setDecimals(2)
    assert [c.valueFromText(t) for t in ("0,35", "0.35", "12.5", "1200,5")] == [0.35, 0.35, 12.5, 1200.5]
    assert c.textFromValue(0.35) == "0,35"


def test_preferences_apply_each_change():
    from PySide6.QtWidgets import QListWidget, QStackedWidget
    from tensela.ui import navigation as navigation
    from tensela.ui.dialogs import DialogPreferences
    from tensela.ui.viewer import STYLE_NAMES
    changes = []
    values = {"preferences/language": "es", "_current_language": "es", "theme/mode": "dark", "theme/name": "sober",
               "view/style": "solid", "view/axes": True, "preferences/canvas_background": "dots",
               "canvas/guides": True, "canvas/grid": True, "preferences/length_unit": "m",
               "preferences/decimals": "auto", "preferences/fraction": 16, "preferences/navigation": "tensela",
               "_styles": list(STYLE_NAMES.items()), "_schemes": list(navigation.NAMES.items()),
               "_scheme_help": navigation.HELP_TEXTS}
    d = DialogPreferences(None, values, lambda k, v: changes.append((k, v)), [("sober", "Sober"), ("vivid", "Vivid")],
                            [("Ctrl+N", "&Nuevo", "Ctrl+N", "Ctrl+N")])
    assert d.findChild(QListWidget).count() == 6 and d.findChild(QStackedWidget).count() == 6   # (6: the Code editor)
    d.mouse._group.button(1).click()                         # Blender
    assert changes[-1] == ("preferences/navigation", "blender")
    d._editors["Ctrl+N"].setKeySequence("Ctrl+Alt+N")
    d._editors["Ctrl+N"].editingFinished.emit()
    assert changes[-1] == ("shortcuts/Ctrl+N", "Ctrl+Alt+N")


def test_preferences_say_when_the_menu_starts_another_copy():
    from PySide6.QtWidgets import QLabel, QPushButton
    from tensela import language
    from tensela.ui import navigation as navigation
    from tensela.ui.dialogs import DialogPreferences
    from tensela.ui.viewer import STYLE_NAMES
    language.LANGUAGE, before = "en", language.LANGUAGE
    put = []
    values = {"preferences/language": "en", "_current_language": "en", "theme/mode": "dark", "theme/name": "sober",
              "view/style": "solid", "view/axes": True, "preferences/canvas_background": "dots",
              "canvas/guides": True, "canvas/grid": True, "preferences/length_unit": "m",
              "preferences/decimals": "auto", "preferences/fraction": 16, "preferences/navigation": "tensela",
              "_styles": list(STYLE_NAMES.items()), "_schemes": list(navigation.NAMES.items()),
              "_scheme_help": navigation.HELP_TEXTS,
              "_desktop_image": "/opt/Tensela-0.9.0-x86_64/tensela", "_desktop_installed": True,
              "_desktop_for": "/home/a/Tensela-0.9.0-x86_64.AppImage",
              "_desktop_put": lambda yes: put.append(yes) or True}
    try:
        d = DialogPreferences(None, values, lambda k, v: None, [("sober", "Sober")], [])
        button = d.findChild(QPushButton, "preferences_menu")
        said = [label.text() for label in d.findChildren(QLabel) if "another copy" in label.text()]
        assert said and "Tensela-0.9.0-x86_64.AppImage" in said[0] and button.text() == "Put this one in the menu"
        button.click()                                       # this one goes in the menu (not out of it)
        assert put == [True] and button.text() == "Take it out of the menu"
    finally:
        language.LANGUAGE = before


def test_the_panel_goes_to_a_normal_window_and_back():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QMainWindow

    from tensela.ui.widgets import DockablePanel
    window = QMainWindow()
    window.setCentralWidget(QLabel("centro"))
    panels = []
    for name in ("A", "B"):
        p = DockablePanel(Panel(name), name.lower(), window)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, p)
        panels.append(p)
    a, b = panels
    # It is not dragged (in GNOME it moved the wrong window): it moves with its menu.
    assert not a.features() & a.DockWidgetFeature.DockWidgetMovable
    window.show()
    a.take_out()
    assert a.outside() and a._window.isWindow() and a.panel.window() is a._window
    assert not a._window.windowFlags() & Qt.WindowType.FramelessWindowHint      # with the desktop's bar
    assert a._dismiss.isHidden()                                                  # the X is the desktop's
    a._window.close()                                     # closing it closes the panel, already in its place
    assert not a.outside() and a.panel.window() is window and not a._dismiss.isHidden() and a.isHidden()
    a.toggleViewAction().trigger()                         # Ver → Paneles: vuelve acoplado
    assert a.isVisible() and not a.isFloating()
    a.group_with(b)
    assert window.tabifiedDockWidgets(a) == [b]
    a.separate()
    assert window.tabifiedDockWidgets(a) == []
    a.move_a(Qt.DockWidgetArea.LeftDockWidgetArea)
    assert window.dockWidgetArea(a) == Qt.DockWidgetArea.LeftDockWidgetArea
    window.close()
