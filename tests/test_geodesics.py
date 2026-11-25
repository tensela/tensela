"""Geodesic."""
import time

import numpy as np
import pytest

from tensela import geodesics as G
from tensela import language
from tensela.data import Data, ShapeError
from tensela.geometry import POINT, kind_surface
from tensela.graph import Graph


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _surface(grid):
    f, c = grid.shape[:2]
    return Data(grid.reshape(f * c, 3), (), "s", kind=kind_surface(f, c))


def _points(*points):
    values = np.array(points, float)
    if len(values) == 1 or values.ndim == 1:
        values = values.reshape(-1, 3)[0] if values.size == 3 else values
    return Data(values, ("pair",) if values.ndim == 2 else (), "p", kind=POINT)


def _cylinder(sides=64):
    t, z = np.linspace(0, 2 * np.pi, sides + 1), np.linspace(0, 2, 9)
    t, z = np.meshgrid(t, z, indexing="ij")
    grid = np.stack([np.cos(t), np.sin(t), z], -1)
    grid[-1] = grid[0]                                                   # closed around: the seam is exact
    return _surface(grid)


def _sphere():
    la, lo = np.meshgrid(np.linspace(-np.pi / 2, np.pi / 2, 49), np.linspace(0, 2 * np.pi, 97), indexing="ij")
    grid = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
    grid[:, -1] = grid[:, 0]
    return _surface(grid)


def _plane():
    u, v = np.meshgrid(np.linspace(0, 4, 5), np.linspace(0, 3, 4), indexing="ij")
    return _surface(np.stack([u, v, np.zeros_like(u)], -1))


def test_on_a_plane_it_is_the_straight_line():
    curve = np.asarray(G.geodesic(_plane(), _points(0.5, 0.2, 0), _points(3.7, 2.9, 0)).values)
    assert curve[0] == pytest.approx([0.5, 0.2, 0]) and curve[-1] == pytest.approx([3.7, 2.9, 0])
    direction = (curve[-1] - curve[0]) / np.linalg.norm(curve[-1] - curve[0])
    off = (curve - curve[0]) - ((curve - curve[0]) @ direction)[:, None] * direction
    assert np.abs(off).max() < 1e-6
    length = float(G.geodesic(_plane(), _points(0.5, 0.2, 0), _points(3.7, 2.9, 0), 'lengths').values)
    assert length == pytest.approx(np.hypot(3.2, 2.7), rel=1e-6)


def test_on_a_cylinder_it_is_a_helix_and_takes_the_short_way_round():
    cylinder = _cylinder()
    start, end = (1.0, 0.0, 0.0), (np.cos(2.5), np.sin(2.5), 2.0)
    curve = np.asarray(G.geodesic(cylinder, _points(start), _points(end)).values)
    angle = np.unwrap(np.arctan2(curve[:, 1], curve[:, 0]))
    assert np.allclose(curve[:, 2], 2.0 * angle / 2.5, atol=4e-3)       # climbs evenly as it turns: a helix
    on_the_prism = np.hypot(2.5 * 64 * 2 * np.sin(np.pi / 64) / (2 * np.pi), 2.0)
    length = float(G.geodesic(cylinder, _points(start), _points(end), 'lengths').values)
    assert length == pytest.approx(on_the_prism, rel=1e-3)
    # Across the seam, the other way round: just as long, not round the long way.
    other = float(G.geodesic(cylinder, _points(start), _points((np.cos(2.5), -np.sin(2.5), 2.0)), 'lengths').values)
    assert other == pytest.approx(length, rel=1e-6)


def test_on_a_sphere_it_is_a_great_circle():
    p, q = np.array([1.0, 0, 0]), np.array([0, np.cos(0.6), np.sin(0.6)])
    curve = np.asarray(G.geodesic(_sphere(), _points(p), _points(q)).values)
    normal = np.cross(p, q) / np.linalg.norm(np.cross(p, q))
    assert np.abs(curve @ normal).max() < 5e-3                           # in the plane through the centre
    length = float(G.geodesic(_sphere(), _points(p), _points(q), 'lengths').values)
    assert length == pytest.approx(np.arccos(p @ q), rel=2e-3)


def test_two_diagonals_cross_once_and_give_four_bars():
    starts, ends = _points((0, 0, 0), (4, 0, 0)), _points((4, 3, 0), (0, 3, 0))
    crossings = np.asarray(G.geodesic(_plane(), starts, ends, 'crossings').values)
    assert crossings.shape == (1, 3) and crossings[0] == pytest.approx([2, 1.5, 0])
    bars = np.asarray(G.geodesic(_plane(), starts, ends, 'bars').values)
    assert bars.shape == (4, 2, 3)
    assert np.linalg.norm(bars[:, 1] - bars[:, 0], axis=1) == pytest.approx([2.5] * 4)
    with pytest.raises(ShapeError, match="do not cross"):
        G.geodesic(_plane(), _points((0, 0, 0), (0, 1, 0)), _points((4, 0, 0), (4, 1, 0)), 'crossings')


def test_it_goes_round_a_hill_rather_than_over_it():
    u, v = np.meshgrid(np.linspace(-1, 1, 41), np.linspace(-1, 1, 41), indexing="ij")
    hill = 3.0 * np.exp(-(u ** 2 + v ** 2) / 0.08)
    surface = _surface(np.stack([u, v, hill], -1))
    curve = np.asarray(G.geodesic(surface, _points(-0.9, 0, 0), _points(0.9, 0, 0)).values)
    assert curve[:, 2].max() < 1.0                                        # not over the top (3 m)
    length = float(G.geodesic(surface, _points(-0.9, 0, 0), _points(0.9, 0, 0), 'lengths').values)
    assert length < 1.8 + 2 * 3.0 * 0.5                                    # shorter than climbing it


def test_a_gridshell_of_many_geodesics_is_quick():
    u, v = np.meshgrid(np.linspace(0, 1, 25), np.linspace(0, 1, 17), indexing="ij")
    grid = np.stack([30 * u, 20 * v, 4 + 3 * np.sin(np.pi * u) * np.sin(np.pi * v)], -1)
    surface = _surface(grid)
    t = np.linspace(0, 1, 10, endpoint=False)
    ring = np.vstack([np.c_[30 * t, 0 * t], np.c_[30 + 0 * t, 20 * t], np.c_[30 - 30 * t, 20 + 0 * t],
                      np.c_[0 * t, 20 - 20 * t]])
    ring = np.c_[ring, np.zeros(len(ring))]
    n = len(ring)
    starts = _points(*np.vstack([ring, ring]))
    ends = _points(*np.vstack([ring[(np.arange(n) + 13) % n], ring[(np.arange(n) - 13) % n]]))
    began = time.perf_counter()
    bars = G.geodesic(surface, starts, ends, 'bars')
    assert time.perf_counter() - began < 5.0
    lengths = np.asarray(G.geodesic(surface, starts, ends, 'lengths').values)
    assert lengths.shape == (2 * n,) and (lengths > 0).all()
    assert len(bars.values) > 2 * n                                       # cut at their crossings


def test_the_node_keeps_the_levels_of_the_points():
    g = Graph()
    g.node("Line", "profile", **{"from": (1.0, 0.0, 0.0), "to": (1.0, 0.0, 2.0)})
    g.node("Revolve", "cylinder", profile=g.nodes["profile"])
    g.node("Series", "k", count=3)
    g.node("Point", "a", x=1.0, y=0.0, z=g.nodes["k"])
    g.node("Point", "b", x=-1.0, y=0.0, z=g.nodes["k"])
    g.node("Geodesic", "path", surface=g.nodes["cylinder"], to=g.nodes["b"], show="lengths",
           **{"from": g.nodes["a"]})
    lengths = g.value("path")
    assert np.asarray(lengths.values).shape == (3,)
    assert np.asarray(lengths.values) == pytest.approx([np.pi] * 3, rel=5e-3)   # half way round, at each height


def test_over_the_top_of_a_dome_it_goes_straight_through_its_pole():
    la, lo = np.meshgrid(np.linspace(0, np.pi / 2, 25), np.linspace(0, 2 * np.pi, 97), indexing="ij")
    grid = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
    grid[:, -1] = grid[:, 0]
    grid[-1] = (0.0, 0.0, 1.0)                                          # the top: the whole last row at one point
    dome = _surface(grid)
    a, b = (np.cos(np.pi / 6), 0.0, 0.5), (-np.cos(np.pi / 6), 0.0, 0.5)
    curve = np.asarray(G.geodesic(dome, _points(a), _points(b)).values)
    # In the plane of the two points, but for a smooth bow: on facets a shortest path passes beside the pole, never
    # over it. No hook: it swings to one side and back once.
    assert np.abs(curve[:, 1]).max() < 1.5e-2
    assert np.count_nonzero(np.diff(np.sign(np.diff(curve[:, 1])))) <= 2
    assert curve[:, 2].max() == pytest.approx(1.0, abs=5e-3)
    length = float(G.geodesic(dome, _points(a), _points(b), 'lengths').values)
    assert length == pytest.approx(2 * np.pi / 3, rel=3e-3)


