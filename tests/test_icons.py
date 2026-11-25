"""Our own icons (Delivery 5, step 1). Skipped if the interface is not there."""

import pytest

pytest.importorskip("PySide6.QtSvg")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from tensela.nodes import CATALOG  # noqa: E402

_app = QGuiApplication.instance() or QGuiApplication([])

from tensela.ui import icons as icons  # noqa: E402


def test_each_node_category_has_its_icon():
    categories = {t.category for t in CATALOG.values()}
    assert categories <= set(icons.FROM_CATEGORY)
    assert all(n in icons.ICONS for n in icons.FROM_CATEGORY.values())


@pytest.mark.parametrize('name', sorted(icons.ICONS))
def test_each_icon_is_drawn(name):
    image = icons.pixmap(name, "#ff0000", 24, 1.0).toImage()
    painted = sum(image.pixelColor(x, y).alpha() > 0 for x in range(24) for y in range(24))
    assert painted > 20                       # something was drawn…
    assert image.pixelColor(0, 0).alpha() == 0 or name == "grid"   # …on a transparent background


def test_it_is_tinted_with_the_colour_asked():
    image = icons.pixmap("search", "#00ff00", 24, 1.0).toImage()
    colours = {image.pixelColor(x, y).name() for x in range(24) for y in range(24) if image.pixelColor(x, y).alpha() == 255}
    assert colours == {"#00ff00"}
