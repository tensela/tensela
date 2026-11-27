"""Insolation: the cumulative sky, checked against itself and the obvious cases."""
from pathlib import Path

import numpy as np
import pytest

from tensela import insolation as I
from tensela import language
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _square(plane="plan", origin=(0.0, 0.0, 0.0)):
    g = Graph()
    g.node("Rectangle", "r", width=1.0, height=1.0, plane=plane, origin=origin)
    return g.value("r")


def test_the_sky_patches_cover_the_sky_evenly():
    directions, solid = I.sky_patches(145)
    assert np.allclose(np.linalg.norm(directions, axis=1), 1) and directions[:, 2].min() > 0
    assert 130 <= len(directions) <= 160 and solid.sum() == pytest.approx(2 * np.pi)
    mirrored = directions * [-1, 1, 1]                                        # east and west, the same patches
    assert np.abs(mirrored[:, None] - directions[None]).sum(-1).min(1).max() < 1e-9
    # A horizontal face sees the whole sky: the cosines times the solid angle add up to π.
    assert (directions[:, 2] * solid).sum() == pytest.approx(np.pi, rel=0.01)


def test_a_flat_roof_receives_the_whole_horizontal_energy():
    sky = I.cumulative_sky('Madrid', None, None, None, 'year', 6, 21, 0.0, 24.0, 0.0, 145)
    roof = float(I.insolation(_square()).values)
    assert roof == pytest.approx(sky[4] / 1000, rel=0.02)                     # the patches lose less than 2 %
    assert 1800 < roof < 2400                                                 # a clear year in Madrid, kWh/m²
    assert float(I.insolation(_square(), show='sky view').values) == pytest.approx(1.0, rel=0.01)
    assert 4300 < float(I.insolation(_square(), show='sun hours').values) < 4500    # about half the year's hours


def test_walls_and_seasons():
    south = float(I.insolation(_square("elevation")).values)                   # an elevation looks to −Y: south
    north = I.insolation(_square("elevation"), side='the other face')
    assert south > 2.5 * float(north.values)
    assert float(I.insolation(_square("elevation"), show='sky view').values) == pytest.approx(0.5, rel=0.02)
    assert float(I.insolation(_square("elevation"), side='the other face', show='direct').values) < 0.15 * south
    summer = float(I.insolation(_square(), period='summer').values)
    winter = float(I.insolation(_square(), period='winter').values)
    assert summer > 2 * winter
    # In the south the seasons turn round: «summer» is December to February there.
    assert float(I.insolation(_square(), location='Montevideo', period='summer').values) > \
        2 * float(I.insolation(_square(), location='Montevideo', period='winter').values)
    one_day = float(I.insolation(_square(), period='day', month=6, day=21).values)
    assert 7 < one_day < 9                                                    # kWh/m² of a clear June day


def test_what_shades_it():
    g = Graph()
    g.node("Box", "b", width=6.0, depth=1.0, height=6.0)
    g.node("Move", "wall in front", geometry=g.nodes["b"], vector=(0.5, -2.0, 3.0))     # 2 m to the south
    window = _square("elevation", origin=(0.0, 0.0, 1.0))
    open_sky = float(I.insolation(window).values)
    shaded = float(I.insolation(window, obstructions=g.value("wall in front")).values)
    assert shaded < 0.5 * open_sky
    assert float(I.insolation(window, obstructions=g.value("wall in front"), show='sky view').values) < 0.4


def test_what_it_says():
    g = Graph()
    g.node("Rectangle", "r", width=4.0, height=4.0)
    g.node("Grid", "roof", rectangle=g.nodes["r"], columns=2, rows=2)
    with pytest.raises(ShapeError, match="face inwards"):
        I.insolation(g.value("roof"), side='the other face')                  # panels looking at the ground
    g.node("Box", "box", width=2.0, depth=2.0, height=2.0)
    faces = I.insolation(g.value("box"), show='faces')
    values = I.insolation(g.value("box"))
    assert faces.levels == values.levels == ("face",) and len(faces.values) == len(values.values) == 12
    with pytest.raises(ShapeError, match="painted as they are"):
        I.insolation(_square(), show='faces')




@pytest.mark.parametrize("from_hour, to_hour", [(0.0, 100000.0), (-3.0, 12.0), (14.0, 10.0), (12.0, 12.0)])
def test_hours_outside_the_day_say_so(from_hour, to_hour):
    """«to hour» = 100 000 broke it with a climate file (its year has 8760 hours): the hours go from 0 to 24, the
    first smaller (found by the review with odd values, 2026-11-26)."""
    with pytest.raises(ShapeError, match="between 0 and 24"):
        I.insolation(_square(), from_hour=from_hour, to_hour=to_hour)
