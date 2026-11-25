"""The examples of the catalogue (Delivery 3, E3.7): structural grid, Blondel stair, windows."""

from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.data import ShapeError
from tensela.geometry import COARSE_FRAME, RECTANGLE, frame, rectangle, grid
from tensela.values import text_value

EXAMPLES = Path(__file__).parent / "data"


def graph(name):
    return open_(EXAMPLES / name).graph


# --- Frame by width, and the opening alone --------------------------------------------------

def test_frame_of_fixed_width():
    hole = frame(rectangle(1.2, 1.0, plane='elevation'), width=0.05, output='hole')
    assert hole.kind == RECTANGLE
    assert np.ptp(hole.values, axis=0) == pytest.approx([1.1, 0, 0.9])


def test_frame_of_fixed_width_on_a_diamond():
    diamond = grid(rectangle(2, 2, plane='elevation'), columns=1, rows=1, shape='diamonds')
    hole = frame(diamond, width=0.1, output='hole').values[0, 0]
    # The opening stays 0.1 from each side of the diamond.
    a, b = diamond.values[0, 0][0], diamond.values[0, 0][1]
    side = (b - a) / np.linalg.norm(b - a)
    p = hole[0] - a
    assert np.linalg.norm(p - (p @ side) * side) == pytest.approx(0.1)


def test_frame_with_thickness_and_unknown_output():
    assert frame(rectangle(1, 1), width=0.05, thickness=0.1).kind == COARSE_FRAME
    with pytest.raises(ShapeError, match="Opciones: marco, hueco"):
        frame(rectangle(1, 1), output="vidrio")


# --- Structural grid ----------------------------------------------------------------

def test_structural_grid():
    g = graph("reticula_estructural.json")
    assert g.value('pillars').shape == "eje X 5 × eje Y 4 × piso 6 = 120"
    # The same points, joined along one axis or the other.
    assert g.value('beams in X').shape == "eje Y 4 × piso 6 = 24"
    assert g.value('beams in Y').shape == "eje X 5 × piso 6 = 30"
    g.change('X axes', "count", 8)
    assert g.value('pillars').count == 8 * 4 * 6


# --- Blondel stair -----------------------------------------------------------------

def test_blondel_stair():
    g = graph("escalera_blondel.json")
    n = g.value('steps').values.item()
    c, h = g.value('riser').values.item(), g.value('tread').values.item()
    assert n == 17 and c == pytest.approx(3 / 17)
    assert 2 * c + h == pytest.approx(0.63)  # Blondel's rule
    assert g.value('solid steps').shape == "peldaño 17"
    g.change('floor to floor height', "value", 3.4)
    assert g.value('solid steps').shape == "peldaño 19"
    assert text_value(g.value('riser').values.item()) == "0,1789"


# --- Ventanas: tres niveles anidados ------------------------------------------------------

def test_windows_three_levels():
    g = graph('ventanas.json')
    assert g.value('panes').shape == "ventana 4 × hoja 2 × vidrio 3 = 24"
    g.change('leaves', "parts", 3)
    g.change('glazing', "parts", 2)
    assert g.value('panes').shape == "ventana 4 × hoja 3 × vidrio 2 = 24"
    # Each pane stays inside its leaf.
    leaf = g.value('leaf span').values[0, 0]
    pane = g.value('panes').values[0, 0, 0]
    assert pane[:, 0].min() >= leaf[:, 0].min() and pane[:, 0].max() <= leaf[:, 0].max()
