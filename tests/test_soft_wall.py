"""Fabrication, package 6: a wall of ribs crossed by battens, the ribs slotted from the back."""
from pathlib import Path

import numpy as np
import pytest

from tensela import fabrication as F
from tensela import printing as P
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def in_english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _wall():
    """Two ribs standing out from a wall (y = 0) towards -y, 30 cm deep and 1 m high, and a batten crossing them (a
    rectangle 12 cm deep, from 3 to 15 cm in front of the wall)."""
    from tensela.data import Data
    from tensela.geometry import CLOSED_CURVE
    rings = [[(x, 0.0, 0.0), (x, -0.3, 0.0), (x, -0.3, 1.0), (x, 0.0, 1.0), (x, 0.0, 0.0)] for x in (0.1, 0.2)]
    ribs = Data(np.array(rings, float), ("rib",), "ribs", kind=CLOSED_CURVE)
    g = Graph()
    g.node("Rectangle", "batten", width=0.4, height=0.12, origin=(0.0, -0.15, 0.5))
    return ribs, g.value("batten")


def test_ribs_slotted_from_the_back_and_battens_from_the_front():
    ribs, batten = _wall()
    args = (0.018, 0.0005, 'first from below')
    rib = F._groups(F.slots(ribs, batten, *args, show='first', towards=(0.0, -1.0, 0.0)))[0][1][0]
    notch = rib[np.abs(rib[:, 2] - 0.5) < 0.02]                       # the points of the notch, around z = 0.5
    assert np.isclose(notch[:, 1].max(), 0.0) and np.isclose(notch[:, 1].min(), -0.09 - 0.00025, atol=1e-6)
    assert np.isclose(rib[:, 1].min(), -0.3) and len(rib[np.isclose(rib[:, 1], -0.3)]) == 2   # the front edge whole
    board = F._groups(F.slots(ribs, batten, *args, show='second', towards=(0.0, -1.0, 0.0)))[0][1][0]
    near_rib = board[np.abs(board[:, 0] - 0.1) < 0.02]
    assert np.isclose(near_rib[:, 1].min(), -0.15) and np.isclose(near_rib[:, 1].max(), -0.09 + 0.00025, atol=1e-6)
    boards = F.slots(ribs, batten, *args, show='boards', towards=(0.0, -1.0, 0.0))
    assert P.check(P.pieces(boards), printer=None, thickness=0)[0].ready


