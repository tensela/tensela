"""The node editor (Delivery 2): automatic arrangement, texts and saved positions."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tensela.project_file import open_, save  # noqa: E402
from tensela.ui.editor import arrange, text_shape, text_value  # noqa: E402

from test_graph import case_01  # noqa: E402

app = QApplication.instance() or QApplication([])


def test_each_node_goes_to_the_right_of_what_it_uses():
    g = case_01()
    pos = arrange(g)
    for node in g.nodes.values():
        for origin in node.connections.values():
            assert pos[origin.name][0] < pos[node.name][0], (origin.name, node.name)


def test_values_are_written_like_an_architect():
    assert text_value(0.4) == "0,4"
    assert text_value([0, -0.3, 0]) == "(0; −0,3; 0)"
    assert text_value(True) == "sí"
    assert text_value(None) == ""


def test_the_shape_on_the_wire():
    g = case_01()
    assert text_shape(g.value("paneles")) == "fila 12 × columna 20 = 240"
    assert text_shape(g.value("atractor")) == "·"


def test_positions_are_saved_and_those_of_missing_nodes_forgotten(tmp_path):
    from tensela.project_file import Project
    p = Project(case_01(), ["quiebrasoles"], positions={"fachada": [10, 20], "fantasma": [0, 0]})
    filepath = save(p, tmp_path / "p.json")
    assert '    "fachada": [10, 20]' in filepath.read_text(encoding="utf-8")
    assert open_(filepath).positions == {"fachada": [10, 20]}


# --- Editing without a mouse (E2.3) -------------------------------------------------------

from tensela.ui.editor import Editor  # noqa: E402


def editor_with_case_01():
    e = Editor()
    e.display(case_01())
    warnings, changes = [], []
    e.warning.connect(warnings.append)
    e.changed.connect(lambda: changes.append(1))
    return e, warnings, changes


def test_connect_another_attractor():
    e, warnings, changes = editor_with_case_01()
    e.graph.node("Point", "otro", x=19, y=0, z=11)
    e.display(e.graph)
    assert e.link("otro", "distancias", "b")
    assert e.graph.nodes["distancias"].inputs["b"].name == "otro"
    assert changes == [1] and not warnings
    assert sum(1 for c in e.cables if c.input_.input_ == "b" and c.input_.box.node.name == "distancias") == 1


def test_a_cycle_is_explained_and_not_made():
    e, warnings, changes = editor_with_case_01()
    assert not e.link("quiebrasoles", "fachada", "width")
    assert warnings == ["Conectar «quiebrasoles» a «fachada» haría un círculo: «fachada» ya está antes de «quiebrasoles»."]
    assert changes == []


def test_disconnecting_goes_back_to_the_default():
    e, warnings, changes = editor_with_case_01()
    cables = len(e.cables)
    e.unlink("quiebrasoles", "rotation")
    assert e.graph.nodes["quiebrasoles"].inputs["rotation"] == 0.0
    assert len(e.cables) == cables - 1


def test_deleting_a_node_disconnects_whoever_used_it():
    e, warnings, changes = editor_with_case_01()
    e.delete(["atractor"])
    assert "atractor" not in e.graph.nodes and "atractor" not in e.boxes
    from tensela.nodes import REQUIRED
    assert e.graph.nodes["distancias"].inputs["b"] is REQUIRED
    assert changes == [1]


# --- Adding nodes (E2.4) -------------------------------------------------------------

from tensela.ui.editor import find_kinds  # noqa: E402


def names(text):
    return [t.name for t in find_kinds(text)]


def test_find_by_name_synonym_and_without_accents():
    assert names("reti")[0] == "Grid"
    assert names("lama")[0] == "Box" and "Ribs" in names("lama")   # a loose louvre, or many
    assert "Grid" in names("grilla")
    assert names("numero")[0] == "Number"
    assert "Filter" in names("dispatch")  # for whoever comes from Grasshopper


def test_names_of_other_programs_find_but_are_not_shown():
    from tensela.nodes import CATALOG
    from tensela.ui.editor import synonym_shown
    assert names("kangaroo")[0] == "Equilibrium" and "Bar analysis" in names("karamba")
    assert synonym_shown(CATALOG["Equilibrium"], "Kangaroo", "kangaroo") is None
    assert synonym_shown(CATALOG["Daylight"], "Ladybug", "lady") is None
    assert synonym_shown(CATALOG["Box"], "Quiebrasol", "quiebra") == "Quiebrasol"   # other synonyms still show


def test_empty_search_shows_everything():
    from tensela.nodes import CATALOG
    assert len(find_kinds("")) == len(CATALOG)


def test_add_a_node_and_connect_it():
    e, warnings, changes = editor_with_case_01()
    node = e.add("Point", (100, 200))
    assert node.name == "punto 1" and "punto 1" in e.boxes
    assert e.boxes["punto 1"].pos().x() == 100
    assert e.link("punto 1", "distancias", "b")
    assert changes == [1, 1]


# --- Arrangement and alignment ---------------------------------------------------------------

from tensela.ui.editor import STEP_GRID  # noqa: E402


def test_automatic_arrangement_falls_on_the_grid():
    for x, y in arrange(case_01()).values():
        assert x % STEP_GRID == 0 and y % STEP_GRID == 0


def test_moving_a_box_snaps_it_to_the_grid():
    e, _, _ = editor_with_case_01()
    box = e.boxes["fachada"]
    box.setPos(37, 61)
    assert (box.pos().x(), box.pos().y()) == (25, 50)


def test_align_left():
    e, warnings, _ = editor_with_case_01()
    moved = []
    e.moved.connect(lambda: moved.append(1))
    e.align("left")
    assert warnings and "elige dos o más cajas" in warnings[0]
    for n in ("atractor", "quiebrasol", "fachada"):
        e.boxes[n].setSelected(True)
    e.boxes["atractor"].setPos(100, 0)
    e.align("left")
    xs = {e.boxes[n].pos().x() for n in ("atractor", "quiebrasol", "fachada")}
    assert len(xs) == 1 and moved


def test_find_a_node_of_the_project():
    from tensela.ui.editor import NodesFinder
    b = NodesFinder(case_01())
    b.field.setText("angulos")    # without accent: it finds «ángulos»
    assert b.list_.count() == 1 and b.list_.item(0).data(0x0100) == "ángulos"
    b.field.setText("caja")       # by kind
    assert b.list_.count() == 1 and "quiebrasol" in b.list_.item(0).text()


def test_the_formula_card_grows_when_using_more_variables():
    from tensela.graph import Graph
    from tensela.ui.editor import BoxNode
    g = Graph()
    n = g.node("Formula", "cuenta", formula="a * 2")
    box = BoxNode(n)
    height = box.height
    g.change(n, "formula", "a * e")
    box.refresh()
    assert box.height > height and box.ports["e"].isVisible() and not box.ports["f"].isVisible()


def test_themes_read_in_light_and_dark():
    """All the pairs of colours that must read pass the WCAG contrast (text 4.5; icons and wires 3)."""
    from tensela.ui import theme as theme
    assert set(theme.themes()) >= {"sober", "vivid"}
    for name in theme.themes():
        for mode in ("light", "dark"):
            bad = [(what, round(r, 2)) for what, r, minimum in theme.check_contrasts(theme.load(name, mode))
                     if r < minimum]
            assert not bad, (name, mode, bad)


def test_each_catalogue_category_has_its_colour_in_each_theme():
    """The node headers take the colour of their category from the theme (if the name does not match, they come out grey)."""
    import json
    from tensela.groups import CATEGORY
    from tensela.nodes import CATALOG
    from tensela.ui import theme as theme
    categories = {t.category for t in CATALOG.values()} | {CATEGORY}
    for name in theme.themes():
        d = json.loads((theme.THEMES / f"{name}.json").read_text(encoding="utf-8"))
        for mode in ("light", "dark"):
            assert categories <= set(d[mode]["tensela"]["categories"]), (name, mode)


def test_the_stylesheet_builds_with_all_themes():
    """Each $colour of the stylesheet exists in the theme (if one is missing, the program does not start)."""
    from tensela.ui import theme as theme
    for name in theme.themes():
        for mode in ("light", "dark"):
            assert "$" not in theme.qss(theme.load(name, mode)), (name, mode)


def test_light_mid_and_dark_backgrounds_let_the_wires_read():
    from tensela.ui import theme as theme
    assert set(theme.TONES) == {"light", "mid", "dark"} and set(theme.NAMES_TONE) == {"theme", *theme.TONES}
    for tone, t in theme.TONES.items():
        assert theme.contrast(t["wire"], t["canvas"]) >= 3.0, tone
        assert theme.contrast(t["grid"], t["canvas"]) >= 1.1, tone          # the pattern shows, without shouting


def test_write_a_value_on_the_card_itself():
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QLineEdit
    from tensela.graph import Graph
    from tensela.ui.editor import HEIGHT_HEADER, HEIGHT_ROW, Editor
    app = QApplication.instance() or QApplication([])
    g = Graph()
    g.node("Box", "pieza", width=1.0, depth=2.0, height=3.0)
    e = Editor()
    e.display(g)
    box = e.boxes["pieza"]
    written = []
    e.value_changed.connect(lambda n, at, t: written.append((n, at, t)))
    assert e._edit_in_card(box, QPointF(box.width - 20, HEIGHT_HEADER + 1.5 * HEIGHT_ROW))   # «background»
    field = next(w.widget() for w in e.graph_scene.items() if hasattr(w, "widget") and isinstance(w.widget(), QLineEdit))
    assert field.text() == "2 m"                             # with its unit, as in mm or cm
    field.setText("120 cm")
    field.returnPressed.emit()
    assert written == [("pieza", "depth", "120 cm")]
    assert not e._edit_in_card(box, QPointF(10, 5))          # on the header, nothing
    app.processEvents()


def test_export_the_nodes_in_png_and_svg(tmp_path):
    from PySide6.QtWidgets import QApplication
    from tensela.graph import Graph
    from tensela.ui.editor import Editor
    app = QApplication.instance() or QApplication([])  # noqa: F841
    g = Graph()
    g.node("Box", "pieza", width=1.0, depth=2.0, height=3.0)
    g.node("Move", "movida", geometry=g.nodes["pieza"], vector=[1, 0, 0])
    e = Editor()
    e.display(g)
    width, height = e.export(tmp_path / "nodos.png", scale=3)
    assert (tmp_path / "nodos.png").stat().st_size > 2000 and width > 300
    e.export(tmp_path / "nodos.svg")
    svg = (tmp_path / "nodos.svg").read_text()
    assert "<svg" in svg and "pieza" in svg            # the text goes as text: vector


def test_guides_snap_a_box_to_another():
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    from tensela.graph import Graph
    from tensela.ui import editor as m
    app = QApplication.instance() or QApplication([])  # noqa: F841
    g = Graph()
    g.node("Box", "una", width=1.0, depth=1.0, height=1.0)
    g.node("Box", "otra", width=1.0, depth=1.0, height=1.0)
    e = m.Editor()
    e.display(g)
    e.resetTransform()
    a, other = e.boxes["una"], e.boxes["otra"]
    m.SETTING.update(grid=False, guides=True)
    try:
        a.setPos(0, 0)
        other.setSelected(True)
        other.setPos(5, 300)                       # almost aligned to the left with «una» (5 px)
        assert other.x() == 0 and e._lines_guide   # it snapped, and the guide shows
        other.setPos(200, 300)                     # far from everything: it stays where it is dropped
        assert other.x() == 200
        m.SETTING["guides"] = False
        other.setPos(5, 300)
        assert other.x() == 5
    finally:
        m.SETTING.update(grid=True, guides=True)


def test_the_project_node_finder_uses_the_arrows():
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    from tensela.graph import Graph
    from tensela.ui.editor import NodesFinder
    app = QApplication.instance() or QApplication([])  # noqa: F841
    g = Graph()
    g.node("Box", "una", width=1.0, depth=1.0, height=1.0)
    g.node("Box", "otra", width=1.0, depth=1.0, height=1.0)
    b = NodesFinder(g)
    assert b.eventFilter(b.field, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))
    assert b.eventFilter(b.field, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)) is False


def test_the_card_field_goes_with_it_and_is_only_one():
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QGraphicsProxyWidget
    from tensela.graph import Graph
    from tensela.ui.editor import HEIGHT_HEADER, HEIGHT_ROW, Editor
    app = QApplication.instance() or QApplication([])  # noqa: F841
    g = Graph()
    g.node("Box", "pieza", width=1.0, depth=2.0, height=3.0)
    e = Editor()
    e.display(g)
    box = e.boxes["pieza"]
    written = []
    e.value_changed.connect(lambda n, at, t: written.append((at, t)))
    e._edit_in_card(box, QPointF(box.width - 20, HEIGHT_HEADER + 0.5 * HEIGHT_ROW))
    e._edit_in_card(box, QPointF(box.width - 20, HEIGHT_HEADER + 1.5 * HEIGHT_ROW))
    fields = [i for i in e.graph_scene.items() if isinstance(i, QGraphicsProxyWidget)]
    assert len(fields) == 1 and fields[0].parentItem() is box          # only one, inside the card
    box.setPos(box.pos() + QPointF(50, 25))
    assert fields[0].pos().y() == HEIGHT_HEADER + HEIGHT_ROW            # it moved with it
    fields[0].widget().setText("5")
    e.dismiss_field()
    assert written[-1] == ("depth", "5") and not [i for i in e.graph_scene.items() if isinstance(i, QGraphicsProxyWidget)]


def test_copy_paste_duplicate_align_and_distribute():
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    from tensela.graph import Graph
    from tensela.ui.editor import Editor
    QApplication.instance() or QApplication([])
    g = Graph()
    length = g.node("Number", "largo", value=2.0)
    g.node("Box", "pieza", width=length)
    e = Editor()
    e.display(g)
    e.boxes["pieza"].setSelected(True)
    e.duplicate()                                         # it still uses «largo»
    assert set(g.nodes) == {"largo", "pieza", "pieza 2"} and g.nodes["pieza 2"].inputs["width"] is length
    e.graph_scene.clearSelection()
    e.boxes["pieza"].setSelected(True)
    assert e.copy()
    e.paste(QPointF(500, 500))                           # paste: without the outside input
    assert "pieza 3" in g.nodes and g.nodes["pieza 3"].inputs["width"] is not length
    assert e.boxes["pieza 3"].pos() == QPointF(500, 500)
    # Align right and distribute horizontally.
    for x, name in ((0, "largo"), (100, "pieza"), (1000, "pieza 2")):
        e.boxes[name].setPos(x, x / 10)
    e.graph_scene.clearSelection()
    for name in ("largo", "pieza", "pieza 2"):
        e.boxes[name].setSelected(True)
    e.distribute("horizontal")
    c = [e.boxes[n] for n in ("largo", "pieza", "pieza 2")]
    holes = [c[i + 1].pos().x() - (c[i].pos().x() + c[i].width) for i in range(2)]
    assert abs(holes[0] - holes[1]) < 1e-6 and c[0].pos().x() == 0
    e.align("right")
    assert len({round(k.pos().x() + k.width, 6) for k in c}) == 1
    e.align("mid")
    assert len({round(k.pos().y() + k.height / 2, 6) for k in c}) == 1
    e.cut()
    assert not {"largo", "pieza", "pieza 2"} & set(g.nodes)
    QApplication.clipboard().clear()        # a clipboard left full makes Qt crash on closing, without a screen


def test_the_card_preview_opens_draws_and_is_saved(tmp_path):
    from PySide6.QtWidgets import QApplication
    from tensela.project_file import Project, open_, save
    from tensela.graph import Graph
    from tensela.ui.editor import HEIGHT_THUMBNAIL, Editor
    from tensela.ui.thumbnail import draw
    QApplication.instance() or QApplication([])
    g = Graph()
    g.node("Box", "pieza", width=1.0, depth=2.0, height=3.0)
    n = g.node("Number", "n", value=3.0)
    g.value("pieza"), g.value("n")
    assert draw(g.value("pieza"), 120, 80, "#999999", "#222222") is not None
    assert draw(g.value("n"), 120, 80, "#999999", "#222222") is None          # a number is not drawn
    e = Editor()
    e.display(g)
    box = e.boxes["pieza"]
    assert box.gives_geometry() and not e.boxes["n"].gives_geometry()
    height = box.height
    e.toggle_thumbnail(["pieza"])
    assert box.thumbnail and box.height == height + HEIGHT_THUMBNAIL + 4 and box._drawing is not None
    assert e.thumbnails() == ["pieza"]
    filepath = save(Project(g, thumbnails=e.thumbnails()), tmp_path / "p.json")
    assert open_(filepath).thumbnails == ["pieza"]
    e.toggle_thumbnail(["pieza"])
    assert not box.thumbnail and box.height == height and n is g.nodes["n"]


def test_the_wheel_zooms_back_from_a_canvas_framed_very_far():
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from tensela.ui.editor import Editor
    e = Editor()
    e.resetTransform()
    e.scale(0.08, 0.08)                                   # a big project framed whole: below the minimum
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    e.wheelEvent(ev)
    assert e.transform().m11() > 0.08                     # it zooms in: not stuck


def test_the_theme_is_light_unless_the_desktop_asks_for_dark(monkeypatch):
    """A desktop that says nothing (a plain X session) gets the light theme, as the catalogues of AppImages expect."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from tensela.ui import theme
    for scheme, expected in ((Qt.ColorScheme.Dark, "dark"), (Qt.ColorScheme.Light, "light"),
                             (Qt.ColorScheme.Unknown, "light")):
        hints = type("Hints", (), {"colorScheme": staticmethod(lambda s=scheme: s)})()
        monkeypatch.setattr(QGuiApplication, "styleHints", staticmethod(lambda h=hints: h))
        assert theme.mode_system() == expected, scheme
