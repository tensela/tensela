"""The diagonals of Bar analysis, and one structure solved once for all its analyses."""
from pathlib import Path

import numpy as np
import pytest

from tensela import frames
from tensela import language
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _cubes(diagonals):
    """A row of four cubes of 1 m held at both ends, as one shape for Bar analysis."""
    g = Graph()
    g.node("Number", "x", value=[0.5, 1.5, 2.5, 3.5])
    g.node("Point", "centres", x=g.nodes["x"], y=0.0, z=0.0)
    g.node("Box", "cube", width=1.0, depth=1.0, height=1.0)
    g.node("Move", "cubes", geometry=g.nodes["cube"], vector=g.nodes["centres"])
    g.node("Number", "ends x", value=[0.0, 0.0, 0.0, 0.0, 4.0, 4.0, 4.0, 4.0])
    g.node("Number", "ends y", value=[-0.5, 0.5, -0.5, 0.5, -0.5, 0.5, -0.5, 0.5])
    g.node("Number", "ends z", value=[-0.5, -0.5, 0.5, 0.5, -0.5, -0.5, 0.5, 0.5])
    g.node("Point", "ends", x=g.nodes["ends x"], y=g.nodes["ends y"], z=g.nodes["ends z"])
    common = dict(shape=g.nodes["cubes"], supports=g.nodes["ends"], support="pinned", section="pipe 60x3",
                  diagonals=diagonals)
    g.node("Bar analysis", "move", **common, show="largest displacement")
    g.node("Bar analysis", "weight", **common, show="total weight")
    return g


def test_diagonals_brace_a_frame_of_cubes():
    plain, braced = _cubes("no diagonals"), _cubes("one per square")
    assert float(braced.value("move").values) < 0.5 * float(plain.value("move").values)
    assert float(braced.value("weight").values) > float(plain.value("weight").values)   # more bars, more steel
    # The wall two cubes share gives its bars once: 4 cubes have 4 × 12 − 3 × 4 = 36 edges.
    from tensela.simulation import network
    assert len(network(plain.value("cubes"), 0)["springs"]) == 36


def test_the_analyses_of_one_structure_solve_it_once(monkeypatch):
    calls = []
    original = frames.solve
    monkeypatch.setattr(frames, "solve", lambda *a: calls.append(1) or original(*a))
    frames._LAST.clear()
    g = _cubes("both")
    g.value("move")
    g.value("weight")
    assert len(calls) == 1


