"""Ties in the Equilibrium."""
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import simulation as SIM
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _lines(*pairs):
    return Data(np.array(pairs, float), ("tie",), None, kind=geo.CURVE)


def test_a_tie_pulls_its_two_ends_together():
    cable = geo.line((0, 0, 0), (4, 0, 0))
    free = SIM.equilibrium(cable, spans=8, self_weight=1.0, stiffness=1000.0)
    tied = SIM.equilibrium(cable, spans=8, self_weight=1.0, stiffness=1000.0,
                           ties=_lines([[1.0, 0, 0], [3.0, 0, 0]]), tie_strength=50.0)
    x0, x1 = free.network["rest"], tied.network["rest"]
    a, b = SIM._nearest(free.network["start"], np.array([[1.0, 0, 0], [3.0, 0, 0]]))
    assert np.linalg.norm(x1[a] - x1[b]) < 0.2 * np.linalg.norm(x0[a] - x0[b])   # almost together
    assert len(tied.network["springs"]) == len(free.network["springs"])        # a tie is not a span of the cable


def test_what_ties_accept():
    cable = geo.line((0, 0, 0), (4, 0, 0))
    with pytest.raises(ShapeError, match="lines"):
        SIM.equilibrium(cable, ties=Data(np.zeros((2, 3)), ("p",), None, kind=geo.POINT))
    same = SIM.equilibrium(cable, spans=8, self_weight=1.0, ties=_lines([[2.0, 0, 0], [2.01, 0, 0]]))
    plain = SIM.equilibrium(cable, spans=8, self_weight=1.0)
    assert np.allclose(same.network["rest"], plain.network["rest"])            # both ends on one particle: nothing
    with pytest.raises(ShapeError, match="greater than 0"):
        SIM.equilibrium(cable, ties=_lines([[1.0, 0, 0], [3.0, 0, 0]]), tie_strength=0.0)


