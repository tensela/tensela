"""Planarize."""
from pathlib import Path

import numpy as np
import pytest

from tensela import language
from tensela import planarize as P
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _cells(shape="hexagons", columns=8, rows=6, height=0.0):
    """A Grid on a vault (an Extrude of an arc), or on a flat rectangle (height 0)."""
    g = Graph()
    if height:
        g.node("Arc", "plan", mode="centre and angles", centre=(0.0, 0.0, 0.0), radius=6.0, **{"from": 200.0},
               to=340.0)
        g.node("Extrude", "surface", curve=g.nodes["plan"], vector=(0.0, 0.0, height))
        g.node("Rotate", "lying", geometry=g.nodes["surface"], degrees=90.0, axis="x")
        g.node("Grid", "cells", rectangle=g.nodes["lying"], columns=columns, rows=rows, shape=shape)
    else:
        g.node("Rectangle", "surface", width=8.0, height=6.0)
        g.node("Grid", "cells", rectangle=g.nodes["surface"], columns=columns, rows=rows, shape=shape)
    return g.value("cells")


def test_flat_panels_stay_as_they_are():
    cells = _cells()
    assert np.asarray(P.planarize(cells, show="flatness before").values).max() == 0
    assert np.allclose(np.asarray(P.planarize(cells).values), np.asarray(cells.values))


def test_quadrilaterals_of_a_vault_and_the_node():
    cells = _cells("squares", 6, 4, height=8.0)
    assert np.asarray(P.planarize(cells, show="flatness before").values).max() < 1e-6   # a vault: already flat
    g = Graph()
    g.node("Rectangle", "r", width=8.0, height=6.0)
    g.node("Grid", "cells", rectangle=g.nodes["r"], columns=4, rows=3, shape="hexagons")
    g.node("Planarize", "flat", panels=g.nodes["cells"], show="flatness")
    assert np.asarray(g.value("flat").values).shape == (3, 4)
    with pytest.raises(ShapeError, match="Connect panels"):
        P.planarize(g.value("r").derived(np.zeros(3), kind=None))


