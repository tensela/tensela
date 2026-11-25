"""Fabrication, package 4: two families of ribs with a slot halfway at each crossing."""
from pathlib import Path

import numpy as np
import pytest

from tensela import fabrication as F
from tensela import printing as P
from tensela.data import Data, ShapeError
from tensela.geometry import CLOSED_CURVE
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def in_english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _rib(axis: int, at: float, length: float = 0.4, height: float = 0.1) -> list:
    """A rectangular rib standing on the ground, across `axis` (0: in the plane x = at; 1: y = at)."""
    corners = [(0.0, 0.0), (length, 0.0), (length, height), (0.0, height)]
    out = []
    for u, z in corners + corners[:1]:
        out.append((at, u, z) if axis == 0 else (u, at, z))
    return out


def _family(axis: int, positions) -> Data:
    return Data(np.array([_rib(axis, p) for p in positions], float), ("rib",), "ribs", starts={"rib": 1},
                kind=CLOSED_CURVE)


def test_each_crossing_gets_two_half_slots_one_from_above_one_from_below():
    xs, ys = _family(0, [0.1, 0.2, 0.3]), _family(1, [0.1, 0.2])
    t, gap = 0.003, 0.0002
    first = F.slots(xs, ys, t, gap, show='first')
    second = F.slots(xs, ys, t, gap, show='second')
    rib = F._closed_ring(np.asarray(first.values)[0], 1e-12)         # the rib x = 0.1, slotted from above
    deep = rib[np.abs(rib[:, 1] - 0.1) < t]                            # its points around the slot at y = 0.1
    assert deep[:, 2].min() == pytest.approx(0.05 - gap / 2, abs=1e-6)   # down to the middle (a hair past)
    width = np.ptp(deep[:, 1])
    assert width == pytest.approx(t + gap, abs=1e-6)
    other = F._closed_ring(np.asarray(second.values)[0], 1e-12)      # the rib y = 0.1, slotted from below
    up = other[np.abs(other[:, 0] - 0.1) < t]
    assert up[:, 2].max() == pytest.approx(0.05 + gap / 2, abs=1e-6)
    assert first.levels == ("rib",) and first.starts == {"rib": 1}


def test_slotted_boards_fit_without_crossing():
    xs, ys = _family(0, [0.1, 0.2, 0.3]), _family(1, [0.1, 0.2])
    boards = F.slots(xs, ys, 0.003, 0.0002, show='boards')
    report = P.check(P.pieces(boards), printer=None, thickness=0)[0]
    assert report.ready, report.problems
    unslotted = F._boards([np.asarray(r) for r in np.asarray(xs.values)] + [np.asarray(r) for r in np.asarray(ys.values)],
                          [np.array([1.0, 0, 0])] * 3 + [np.array([0, 1.0, 0])] * 2, 0.003, None)
    assert not P.check(P.pieces(unslotted), printer=None, thickness=0)[0].ready      # without slots, they cross


def test_from_below_swaps_the_families_and_parallel_ribs_are_left_alone():
    xs, ys = _family(0, [0.1]), _family(1, [0.1])
    below = F._closed_ring(np.asarray(F.slots(xs, ys, slotted='first from below').values)[0], 1e-12)
    around = below[np.abs(below[:, 1] - 0.1) < 0.003]
    assert around[:, 2].max() > 0.05 and around[:, 2].min() == pytest.approx(0.0)
    same = F.slots(xs, _family(0, [0.2]))                              # parallel: no slot
    assert len(F._closed_ring(np.asarray(same.values)[0], 1e-12)) == 4
    with pytest.raises(ShapeError):
        F.slots(xs, ys, thickness=0)


def test_two_families_on_the_same_sheets_numbered_a_and_b():
    xs, ys = _family(0, [0.1, 0.2, 0.3]), _family(1, [0.1, 0.2])
    pieces = F.lay_flat(F.slots(xs, ys, show='first'), more=F.slots(xs, ys, show='second'))
    assert pieces.levels == ("piece",) and pieces.layout.count == 5
    from tensela.strokes import text_strokes
    numbers = F.lay_flat(F.slots(xs, ys, show='first'), more=F.slots(xs, ys, show='second'), show='numbers')
    letters = sum(len(text_strokes(label, 1)) for label in ("A1", "A2", "A3", "B1", "B2"))
    assert numbers.sizes["stroke"] == letters


