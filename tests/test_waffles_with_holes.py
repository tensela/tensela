"""Fabrication, package 5: pieces with holes, radial cuts, and the four waffles."""
from pathlib import Path

import numpy as np
import pytest

from tensela import fabrication as F
from tensela import printing as P
from tensela.connectors.cutting import gather
from tensela.graph import Graph
from tensela.project_file import open_

HERE = Path(__file__).parent / "data"


@pytest.fixture(autouse=True)
def in_english(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _shell() -> Graph:
    """A hollow shell of revolution open at both ends (a lamp)."""
    R, wall = 0.12, 0.012
    a = np.radians(np.linspace(-55, 65, 25))
    profile = [(R * np.cos(x), 0.0, R * np.sin(x)) for x in a] + \
        [((R - wall) * np.cos(x), 0.0, (R - wall) * np.sin(x)) for x in a[::-1]]
    g = Graph()
    g.node("Drawn curve", "profile", points=profile, degree=1, closed=True)
    g.node("Revolve", "shell", profile=g.nodes["profile"])
    return g


def test_level_cuts_of_a_hollow_shell_are_rings_with_a_hole():
    g = _shell()
    rings = F.sections(g.value("shell"), 0.003, 0.027, 'z')
    assert rings.levels == ("section", "contour") and rings.starts == {"section": 1}
    groups = F._groups(rings)
    assert all(len(r) == 2 for _, r in groups)                        # outline and hole
    outer, hole = groups[len(groups) // 2][1]
    r_out = np.linalg.norm(outer[:, :2], axis=1).mean()
    r_in = np.linalg.norm(hole[:, :2], axis=1).mean()
    assert r_out - r_in == pytest.approx(0.012, rel=0.15)


def test_radial_cuts_go_through_the_axis_half_a_turn_shared_out():
    g = _shell()
    ribs = F.sections(g.value("shell"), cuts='radial', count=6)
    assert ribs.sizes["section"] == 12                                 # each plane, a piece on each side of the hole
    for _, (ring,) in F._groups(ribs):
        angle = np.degrees(np.arctan2(ring[:, 1], ring[:, 0])) % 180
        assert np.ptp(angle) < 1e-6 or np.ptp((angle + 90) % 180) < 1e-6      # each one in a plane through the axis
        assert round(float(np.median(angle)) / 30, 6) % 1 == 0                    # at 0°, 30°, 60°…


def test_rings_and_ribs_slot_into_each_other():
    g = _shell()
    rings = F.sections(g.value("shell"), 0.003, 0.027, 'z')
    ribs = F.sections(g.value("shell"), cuts='radial', count=6)
    boards = F.slots(rings, ribs, show='boards')
    assert P.check(P.pieces(boards), printer=None, thickness=0)[0].ready
    slotted = F.slots(rings, ribs, show='first')
    assert slotted.levels == ("section", "contour")                     # the rings keep their hole
    outer = F._groups(slotted)[4][1][0]
    radius = np.linalg.norm(outer[:, :2], axis=1)
    assert radius.min() < radius.max() - 0.005                          # notches from the outer edge


def test_pieces_with_holes_are_laid_flat_together_and_holes_cut_first(tmp_path):
    g = _shell()
    rings = F.sections(g.value("shell"), 0.003, 0.027, 'z')
    pieces = F.lay_flat(rings, 0.6, 0.4)
    assert pieces.levels == ("section", "contour")
    for _, (outer, hole) in F._groups(pieces):
        assert F._inside(hole[:, :2], outer[:, :2]).all()               # each hole inside its own outline
    lines, _ = gather([("pieces", pieces), ("numbers", F.lay_flat(rings, 0.6, 0.4, show='numbers'))])
    operations = [op for op, _, _ in lines]
    assert operations.index("cut") > operations.index("engrave")         # engraving first
    numbers = F.lay_flat(rings, 0.6, 0.4, show='numbers')
    strokes = np.asarray(numbers.values)[..., :2]
    solids = [(outer[:, :2], hole[:, :2]) for _, (outer, hole) in F._groups(pieces)]
    for s in strokes:                                # each number on the wood of a piece, not in its hole (where
        assert any(F._inside(s, o).all() and not F._inside(s, h).any() for o, h in solids)   # a smaller one may sit)


def test_cuts_along_a_curve_are_square_to_it():
    g = Graph()
    g.node("Series", "f", count=7, level="floor")
    g.node("Formula", "x", formula="0.18 * (a / 6)^2", a=g.nodes["f"])
    g.node("Formula", "z", formula="a * 0.075", a=g.nodes["f"])
    g.node("Point", "pts", x=g.nodes["x"], y=0.0, z=g.nodes["z"])
    g.node("Curve through points", "axis", points=g.nodes["pts"])
    g.node("Pipe", "column", curves=g.nodes["axis"], radius=0.07, sides=40, caps=True)
    slices = F.sections(g.value("column"), 0.003, 0.027, 'along a curve', guide=g.value("axis"))
    axis = np.asarray(g.value("axis").values, float).reshape(-1, 3)
    for _, (ring,) in F._groups(slices):
        centre = ring.mean(axis=0)
        k = int(np.argmin(np.linalg.norm(axis - centre, axis=1)))
        tangent = axis[min(k + 1, len(axis) - 1)] - axis[max(k - 1, 0)]
        tangent /= np.linalg.norm(tangent)
        normal = np.cross(ring[len(ring) // 3] - ring[0], ring[2 * len(ring) // 3] - ring[0])
        normal /= np.linalg.norm(normal)
        assert abs(normal @ tangent) > 0.98                              # square to the axis where it crosses it
    ribs = F.sections(g.value("column"), 0.003, 0.022, 'y')
    boards = F.slots(ribs, slices, show='boards')
    assert P.check(P.pieces(boards), printer=None, thickness=0)[0].ready


def test_each_board_has_its_slots_on_one_edge_only():
    g = Graph()
    g.node("Sphere", "ball", radius=0.1)
    xs = F.sections(g.value("ball"), 0.003, 0.02, 'x')
    ys = F.sections(g.value("ball"), 0.003, 0.02, 'y')
    rib = F._groups(F.slots(xs, ys, show='first'))[len(F._groups(xs)) // 2][1][0]
    plain = F._groups(xs)[len(F._groups(xs)) // 2][1][0]
    z_centre = plain[:, 2].mean()
    cut_points = rib[~np.isin(np.round(rib, 9).view([("", float)] * 3), np.round(plain, 9).view([("", float)] * 3)).ravel()]
    assert (cut_points[:, 2] > z_centre - 0.002).all()                   # every notch comes in from above


