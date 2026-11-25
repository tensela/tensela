"""Shadows: on the ground, exact; on surfaces, face by face."""
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as geo
from tensela import language
from tensela import shadows as SH
from tensela.data import Data, ShapeError
from tensela.graph import Graph
from tensela.project_file import open_


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _tower():
    """A box of 2 × 2 × 6 m standing on the ground at the origin."""
    g = Graph()
    g.node("Box", "b", width=2.0, depth=2.0, height=6.0)
    g.node("Move", "tower", geometry=g.nodes["b"], vector=(0.0, 0.0, 3.0))
    return g, g.value("tower")


def _ray(*v):
    return Data(np.array(v, float), ("sun",) if np.ndim(v) > 1 else (), None, kind=geo.VECTOR)


def test_on_the_ground_the_shadow_is_exact():
    _, tower = _tower()
    # The sun at 45° from the south: the top falls 6 m to the north; 2 × (2 + 6) = 16 m².
    assert float(SH.shadow(tower, _ray(0, 1, -1), show='area').values) == pytest.approx(16.0)
    outline = np.asarray(SH.shadow(tower, _ray(0, 1, -1), show='outline').values)
    assert np.allclose(outline.min(0), [-1, -1, 0]) and np.allclose(outline.max(0), [1, 7, 0])
    # A ground 1 m up: what is below it does not cast; 2 × (2 + 5) = 14 m², at that height.
    assert float(SH.shadow(tower, _ray(0, 1, -1), ground=1.0, show='area').values) == pytest.approx(14.0)
    filled = np.asarray(SH.shadow(tower, _ray(0, 1, -1), ground=1.0).values)
    assert np.allclose(filled[:, 2], 1.0)
    # Several hours: the area of each.
    areas = SH.shadow(tower, _ray([0, 1, -1], [1, 0, -1]), show='area')
    assert areas.levels == ("sun",) and np.allclose(areas.values, 16.0)


def test_at_night_there_is_no_shadow():
    _, tower = _tower()
    assert float(SH.shadow(tower, _ray(0, 1, 0.2), show='area').values) == 0.0
    assert len(SH.shadow(tower, _ray(0, 1, 0.2)).values) == 0                  # an empty mesh: the ▶ goes on
    with pytest.raises(ShapeError, match="no shadow"):
        SH.shadow(tower, _ray(0, 1, 0.2), show='outline')


def test_on_surfaces_face_by_face():
    g, tower = _tower()
    g.node("Rectangle", "r", width=20.0, height=20.0, origin=(-10.0, -10.0, 0.0))
    g.node("Mesh surface", "ground", surface=g.nodes["r"], count_u=40, count_v=40)
    ground = g.value("ground")
    shade = np.asarray(SH.shadow(tower, _ray(0, 1, -1), surfaces=ground, show='in shadow').values)
    assert shade.sum() * 0.125 == pytest.approx(16.0, abs=0.5)                 # triangles of 0,125 m²
    lit = SH.shadow(tower, _ray(0, 1, -1), surfaces=ground, show='sunlit')
    assert len(lit.kind.faces) + int(shade.sum()) == 2 * 40 * 40
    # Two hours, one with the shadow to the north and one to the east: the faces shaded in only one, half.
    both = np.asarray(SH.shadow(tower, _ray([0, 1, -1], [1, 0, -1]), surfaces=ground, show='in shadow').values)
    assert set(np.round(np.unique(both), 3)) == {0.0, 0.5, 1.0}
    # «faces»: one element per face, so «in shadow» paints them (the same list «face»).
    faces = SH.shadow(tower, _ray(0, 1, -1), surfaces=ground, show='faces')
    from tensela.project_file import values_by_element
    painted = values_by_element(faces, SH.shadow(tower, _ray(0, 1, -1), surfaces=ground, show='in shadow'))
    assert faces.levels == ("face",) and painted is not None and len(painted) == 2 * 40 * 40
    # The tower on itself: the faces away from the sun are in its own shadow.
    own = np.asarray(SH.shadow(tower, _ray(0, 1, -1), surfaces=tower, show='in shadow').values)
    assert 0 < own.mean() < 1
    with pytest.raises(ShapeError, match="for the shadow on the ground"):
        SH.shadow(tower, _ray(0, 1, -1), surfaces=ground, show='area')


def test_what_it_needs():
    _, tower = _tower()
    with pytest.raises(ShapeError, match="ray of a Sun"):
        SH.shadow(tower, Data(np.zeros((5, 3)), ("p",), None, kind=geo.POINT))


def test_what_show_offers_and_the_faces_painted_by_themselves():
    from tensela.nodes import node_kind, options_of
    from tensela.project_file import Project
    g, tower = _tower()
    g.node("Number", "hours", value=[9.0, 17.0])
    g.node("Sun", "sun", hour=g.nodes["hours"], show="ray")
    g.node("Shadow", "on the ground", geometry=g.nodes["tower"], ray=g.nodes["sun"])
    show = node_kind("Shadow").input_("show")
    assert options_of(g.nodes["on the ground"], show) == list(SH.ON_GROUND)
    g.node("Rectangle", "r", width=20.0, height=20.0, origin=(-10.0, -10.0, 0.0))
    g.node("Mesh surface", "terrain", surface=g.nodes["r"], count_u=20, count_v=20)
    g.node("Shadow", "on the terrain", geometry=g.nodes["tower"], ray=g.nodes["sun"], surfaces=g.nodes["terrain"],
           show="faces")
    assert options_of(g.nodes["on the terrain"], show) == list(SH.ON_SURFACES)
    faces = g.value("on the terrain")
    project = Project(g, ["on the terrain"], "", [], {}, {})
    numbers, gradient = project.colour_by("on the terrain", faces)          # painted without asking
    assert len(numbers) == 2 * 20 * 20 and set(np.unique(numbers)) <= {0.0, 0.5, 1.0} and numbers.max() > 0
    assert SH.shadow(tower, _ray(0, 1, -1)).shade and not SH.shadow(tower, _ray(0, 1, -1), surfaces=g.value(
        "terrain"), show='sunlit').shade                                      # a shadow keeps its colour in the view
