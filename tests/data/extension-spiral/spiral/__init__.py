"""An example extension: the node Spiral (with its own icon), an action in the Extensions menu, an entry in the
right-click menu of a node and a panel that hears what happens in the window."""
import numpy as np

from tensela.data import Data
from tensela.geometry import POINT, curve_by_points
from tensela.nodes import Input


def spiral(turns, radius, height, name=None):
    t = np.linspace(0.0, float(turns) * 2 * np.pi, max(8, int(float(turns) * 48)))
    r = float(radius) * t / max(t[-1], 1e-9)
    points = np.column_stack([r * np.cos(t), r * np.sin(t), float(height) * t / max(t[-1], 1e-9)])
    return curve_by_points(Data(points, ("point",), kind=POINT), along="point", name=name)


def hello(window):
    from tensela.language import tr
    window.statusBar().showMessage(tr("Hello from an extension!"))


def about(window, node):
    from tensela.language import tr
    kind = window.project.graph.nodes[node].kind.name
    window.statusBar().showMessage(tr("«{node}» is a {kind}.").format(node=node, kind=tr(kind)))


class Heard:
    """What the panel heard: how many computations, and the node chosen."""
    computed = 0
    chosen = None
    label = None


def panel(window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    from tensela.language import tr
    Heard.label = QLabel(tr("Nothing heard yet."))
    Heard.label.setWordWrap(True)
    Heard.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    return Heard.label


def _say(window):
    from tensela.language import tr
    if Heard.label is not None:
        Heard.label.setText(tr("Computed {n} times since it was opened. Node chosen: {node}.").format(
            n=Heard.computed, node=Heard.chosen or "—"))


def computed(window):
    Heard.computed += 1
    _say(window)


def selected(window, node):
    Heard.chosen = node
    _say(window)


def register(tensela):
    tensela.icon("spiral", "spiral.svg")
    tensela.node("Spiral", "Curves", (Input("turns", 3.0, single=True), Input("radius", 2.0, single=True),
                                      Input("height", 4.0, single=True)), "spiral", spiral,
                 "A spiral that climbs: its turns, its radius and its height.", icon="spiral")
    tensela.action("Say hello", hello, "An example action", icon="spiral")
    tensela.menu("node", "What is this node?", about, "An example entry of the right-click menu")
    tensela.panel("Spiral", panel, "An example panel: what the window tells the extensions")
    tensela.on("computed", computed)
    tensela.on("selected", selected)
