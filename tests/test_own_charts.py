"""The user's own curves for the Graph node: saved, replaced and deleted, in a settings file of the test."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from tensela.ui import chart  # noqa: E402


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Never the real preferences: a file of its own for each test."""
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(chart, "QSettings", lambda: QSettings(path, QSettings.Format.IniFormat))


def test_saving_replacing_and_deleting_own_curves(settings):
    assert chart.own_charts() == {}
    chart.save_own_chart("soft start", [[0, 0], [0.4, 0.1], [1, 1]])
    chart.save_own_chart("plateau", [[0, 0], [0.3, 1], [1, 1]])
    assert list(chart.own_charts()) == ["soft start", "plateau"]
    chart.save_own_chart("soft start", [[0, 0], [1, 0.5]])                 # the same name replaces it
    assert chart.own_charts()["soft start"] == [[0, 0], [1, 0.5]]
    chart.delete_own_chart("soft start")
    assert list(chart.own_charts()) == ["plateau"]


def test_a_broken_setting_gives_no_curves(settings):
    chart.QSettings().setValue(chart._OWN_KEY, "not json")
    assert chart.own_charts() == {}


def test_the_panel_offers_own_curves_and_loads_them(settings):
    from tensela.graph import Graph
    from tensela.ui.node_panel import PanelNode
    from PySide6.QtWidgets import QComboBox
    chart.save_own_chart("plateau", [[0, 0], [0.3, 1], [1, 1]])
    g = Graph()
    g.node("Number", "n", value=1.0)
    g.node("Graph", "response", value=g.nodes["n"])
    panel = PanelNode()
    seen = []
    panel.change_value.connect(lambda node, input_, value, final: seen.append(value))
    box = panel._editor_chart(g.nodes["response"])
    shapes = box.findChild(QComboBox)
    index = shapes.findData("own:plateau")
    assert index > 0
    shapes.setCurrentIndex(index)
    shapes.activated.emit(index)
    assert seen[-1] == [[0, 0], [0.3, 1], [1, 1]]


def test_a_click_on_the_image_name_opens_the_file_browser(tmp_path, monkeypatch):
    from PIL import Image
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog, QLabel, QLineEdit
    from tensela.graph import Graph
    from tensela.ui.node_panel import PanelNode
    Image.new("L", (40, 20), 200).save(tmp_path / "patch.png")
    g = Graph()
    g.folder = tmp_path
    g.node("Point", "p")
    g.node("Image sampler", "s", file="", where=g.nodes["p"])
    panel = PanelNode()
    seen = []
    panel.change.connect(lambda node, input_, text: seen.append((input_, text)))
    asked = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (asked.append(a) or str(tmp_path / "patch.png"), "")))
    from tensela.nodes import CATALOG
    box = panel._field(g.nodes["s"], next(i for i in CATALOG["Image sampler"].inputs if i.name == "file"), "")
    field = box.findChild(QLineEdit)
    assert field.isReadOnly()
    QTest.mouseClick(field, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
    assert asked and seen[-1] == ("file", "patch.png")         # inside the project's folder: kept relative
    assert box.findChild(QLabel).pixmap() is not None and not box.findChild(QLabel).pixmap().isNull()
