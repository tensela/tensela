"""Daylight: the CIE overcast sky and the BRE split flux."""
from pathlib import Path

import numpy as np
import pytest

from tensela import daylight as D
from tensela import geometry as geo
from tensela import language
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _points(*p):
    return Data(np.array(p, float), ("p",), None, kind=geo.POINT)


def _room(glass=True):
    """A room of 12 × 6 × 6 m, its east wall in glass."""
    g = Graph()
    g.node("Box", "box", width=12.0, depth=6.0, height=6.0)
    g.node("Move", "room", geometry=g.nodes["box"], vector=(6.0, 3.0, 3.0))
    g.node("Rectangle", "glass", width=6.0, height=6.0, origin=(12.0, 0.0, 0.0), plane="side elevation")
    return g, g.value("room"), g.value("glass") if glass else None


def test_outside_the_whole_sky_and_shut_in_none():
    assert float(D.daylight(_points((0, 0, 0)), show='sky component').values[0]) == pytest.approx(100, abs=1e-9)
    _, room, _ = _room(glass=False)
    inside = _points((6, 3, 0.7), (2, 2, 0.7))
    assert np.allclose(D.daylight(inside, room, show='daylight factor').values, 0)


def test_a_room_with_a_glass_wall():
    _, room, glass = _room()
    line = _points(*[(x, 3.0, 0.7) for x in (1.0, 4.0, 7.0, 10.0, 11.5)])
    factor = np.asarray(D.daylight(line, room, glass).values)
    assert (np.diff(factor) > 0).all()                                        # more light nearer the glass
    # The reflected part, by hand: A = 360 m², W = 36 m², R̄ = (0,5·324 + 0,1·36) / 360 = 0,46.
    irc = D.reflected_component(D._triangles_of(room, 'room'), D._triangles_of(glass, 'glass'), 0.7, 0.5)
    assert irc == pytest.approx(0.7 * 36 * (39 * 0.5 + 5 * 0.5) / (360 * (1 - 0.46)), rel=1e-6)
    sky = np.asarray(D.daylight(line, room, glass, show='sky component').values)
    assert np.allclose(factor - sky, irc)                                     # the same everywhere
    # The glass: its transmittance scales what comes straight from the sky.
    clear = np.asarray(D.daylight(line, room, glass, transmittance=100.0, show='sky component').values)
    assert np.allclose(sky, 0.7 * clear)
    # Symmetric about the middle of the room.
    pair = np.asarray(D.daylight(_points((9.0, 1.5, 0.7), (9.0, 4.5, 0.7)), room, glass).values)
    assert pair[0] == pytest.approx(pair[1], rel=1e-9)                       # the sky patches are symmetric


def test_louvers_outside_take_light_and_the_lux():
    g, room, glass = _room()
    g.node("Box", "slab", width=2.0, depth=6.0, height=0.1)
    g.node("Move", "eave", geometry=g.nodes["slab"], vector=(13.0, 3.0, 5.0))
    near = _points((10.0, 3.0, 0.7))
    open_sky = float(D.daylight(near, room, glass, show='sky component').values[0])
    shaded = float(D.daylight(near, room, glass, obstructions=g.value("eave"), show='sky component').values[0])
    assert shaded < open_sky
    factor = float(D.daylight(near, room, glass).values[0])
    lux = float(D.daylight(near, room, glass, show='illuminance').values[0])
    assert lux == pytest.approx(factor / 100 * D.sky_illuminance(40.42))
    # The design sky, computed (85 % of the working hours): bright near the equator, dim far from it, the same south.
    assert D.sky_illuminance(0) == pytest.approx(10800, rel=0.03)
    assert D.sky_illuminance(45) == pytest.approx(6100, rel=0.03)
    assert D.sky_illuminance(-30) == pytest.approx(D.sky_illuminance(30))
    assert D.sky_illuminance(0) > D.sky_illuminance(30) > D.sky_illuminance(60)
    assert float(D.daylight(near, room, glass, sky_lux=10000, show='illuminance').values[0]) == \
        pytest.approx(factor * 100)


def test_what_it_says():
    _, room, glass = _room()
    with pytest.raises(ShapeError, match="points where the light"):
        D.daylight(room, room, glass)
    with pytest.raises(ShapeError, match="transmittance"):
        D.daylight(_points((6, 3, 0.7)), room, glass, transmittance=150)


