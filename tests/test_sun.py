"""The sun: checked against the published times and the geometry of the sky."""
import numpy as np
import pytest

from tensela import language
from tensela import sun as S
from tensela.data import ShapeError
from tensela.graph import Graph


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


def _minutes(hours):
    return float(hours) * 60


def test_madrid_its_sunrise_sunset_and_the_noon_sun():
    lat, lon, zone = S.CITIES['Madrid']
    # The almanacs: on 21 June 6:45 and 21:48 summer time (5:45 and 20:48 standard); on 21 December 8:33 and 17:51.
    rise, set_ = S.rise_and_set(lat, lon, zone, 21, 6)
    assert abs(_minutes(rise) - (5 * 60 + 45)) < 3 and abs(_minutes(set_) - (20 * 60 + 48)) < 3
    rise, set_ = S.rise_and_set(lat, lon, zone, 21, 12)
    assert abs(_minutes(rise) - (8 * 60 + 33)) < 3 and abs(_minutes(set_) - (17 * 60 + 51)) < 3
    hours = np.linspace(11, 15, 2401)
    alt, az = S.position(lat, lon, zone, 21, 6, hours)
    assert alt.max() == pytest.approx(90 - 40.42 + 23.44, abs=0.1)              # 90 − latitude + declination
    assert az[alt.argmax()] == pytest.approx(180, abs=1)                         # due south


def test_in_the_south_the_sun_goes_by_the_north_and_at_the_equator_overhead():
    lat, lon, zone = S.CITIES['Montevideo']
    hours = np.linspace(10, 15, 3001)
    alt, az = S.position(lat, lon, zone, 21, 6, hours)
    assert alt.max() == pytest.approx(90 - 34.90 - 23.44, abs=0.15)
    assert min(az[alt.argmax()], 360 - az[alt.argmax()]) < 1                     # due north
    alt, _ = S.position(0.0, 0.0, 0.0, 20, 3, hours)
    assert alt.max() > 88.5                                                      # the equinox: almost overhead


def test_the_node_what_it_shows():
    g = Graph()
    g.node("Sun", "s", hour=[8.0, 12.0, 16.0], show="position", scale=10.0)
    points = np.asarray(g.value("s").values)
    assert g.value("s").levels == ("sun",) and np.allclose(np.linalg.norm(points, axis=1), 10)
    g.change("s", "show", "ray")
    rays = np.asarray(g.value("s").values)
    assert np.allclose(rays, -points / 10)                                       # the light goes from the sun down
    g.change("s", "show", "diagram")
    diagram = g.value("s")
    assert diagram.kind.curve and np.asarray(diagram.values)[..., 2].min() > -1e-9   # nothing below the horizon
    g.node("Sun", "noon", hour=13.25, show="azimuth", north=90.0)
    g.node("Sun", "noon direction", hour=13.25, show="ray", north=90.0)
    assert float(g.value("noon").values) == pytest.approx(180, abs=2)            # the azimuth does not turn
    assert np.asarray(g.value("noon direction").values)[0] < -0.2                # south turned to +X: light to −X


def test_what_it_does_not_accept():
    g = Graph()
    g.node("Sun", "s", month=13, show="altitude")
    with pytest.raises(Exception, match="month goes from 1 to 12"):
        g.value("s")
    with pytest.raises(ShapeError, match="does not rise"):
        S.sun('other place', 78.0, 15.0, 1.0, 21, 12, 12.0, show='day path')     # the polar night
    with pytest.raises(ShapeError, match="same length"):
        S.sun(day=[1, 2], month=[1, 2, 3], show='altitude')
    with pytest.raises(ShapeError, match="hour goes from 0 to 24"):
        S.sun(hour=63.0, show='ray')                                          # a slider widened by hand


def test_incidence_the_cosine_law():
    from tensela import geometry as geo
    from tensela.data import Data
    g = Graph()
    g.node("Box", "box", width=2.0, depth=2.0, height=2.0)
    south_45 = Data(np.array([0.0, 1.0, -1.0]) / np.sqrt(2), (), None, kind=geo.VECTOR)   # from the south, at 45°
    light = np.asarray(S.incidence(g.value("box"), south_45).values)
    t = __import__("tensela.meshes", fromlist=["_triangles"])._triangles(g.value("box"))
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    south, roof, north = n[:, 1] < -0.9, n[:, 2] > 0.9, n[:, 1] > 0.9
    assert np.allclose(light[south], np.cos(np.radians(45))) and np.allclose(light[roof], np.cos(np.radians(45)))
    assert np.allclose(light[north], 0)                                           # from behind: nothing
    assert np.allclose(S.incidence(g.value("box"), south_45, show='angle').values[north], 135)
    assert np.allclose(S.incidence(g.value("box"), south_45, side='both faces').values[north],
                       np.cos(np.radians(45)))
    night = Data(np.array([0.0, 1.0, 0.3]), (), None, kind=geo.VECTOR)
    assert np.allclose(S.incidence(g.value("box"), night).values, 0)
    two = Data(np.array([[0.0, 1.0, -1.0], [0.0, -1.0, -1.0]]) / np.sqrt(2), ("sun",), None, kind=geo.VECTOR)
    assert np.allclose(S.incidence(g.value("box"), two).values[roof], np.cos(np.radians(45)))   # the average
    with pytest.raises(ShapeError, match="single hour"):
        S.incidence(g.value("box"), two, show='angle')


