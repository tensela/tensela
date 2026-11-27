import numpy as np
import pytest

from tensela import geometry as geo, meshes as meshes, measures as measures
from tensela.project_file import open_
from tensela.data import ShapeError
from tensela.values import lines_of

EXAMPLES = __import__("pathlib").Path(__file__).parent / "data"


def test_area_and_centroid_of_an_l_plan():
    plan = geo.drawn_curve([[0, 0, 0], [12, 0, 0], [12, 4, 0], [4, 4, 0], [4, 12, 0], [0, 12, 0]], degree=1,
                                closed=True)
    assert measures.area(plan).values == pytest.approx(80)
    assert np.allclose(measures.centroid(plan).values, [4.4, 4.4, 0])        # outside the L: it is right
    assert not np.allclose(geo.centre(plan).values, [4.4, 4.4, 0])          # the average of the vertices is another
    assert measures.area(geo.rectangle(10, 5)).values == pytest.approx(50)
    with pytest.raises(ShapeError, match="curva abierta"):
        measures.area(geo.line((0, 0, 0), (1, 0, 0)))


def test_a_closed_tube_closes_without_seam():
    from tensela.data import Data
    t = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    node = np.stack([(2 + np.cos(3 * t)) * np.cos(2 * t), (2 + np.cos(3 * t)) * np.sin(2 * t), np.sin(3 * t)], -1)
    pipe = meshes.pipe(Data(node, (), "nudo", kind=geo.CLOSED_CURVE), 0.2)
    assert measures.volume(pipe).values > 0                                     # cerrado: tiene volumen


def test_measures_follow_the_chosen_unit():
    from tensela import values as values
    from tensela.graph import Graph
    before = values.UNIT
    try:
        values.UNIT = "ft-in"
        assert values.text_measure(80, "area") == "861,1128 ft²"
        assert values.text_of("radio", 0.6) == "1'-11 5/8\""                     # the radius is already a length
        assert values.read_lengths("3', -3'") == "0,9144; −0,9144"             # it is saved in metres
        g = Graph()
        g.node("Line", "viga", from_=(0, 0, 0), to=(8, 0, 0))
        supports = g.node("Points on curve", "apoyos", curve=g.nodes["viga"], mode='distance', positions="2; -2")
        assert values.is_length(supports, "posiciones") and not values.is_length(supports, "cantidad")
        values.UNIT = "m"
        assert values.text_measure(80, "area") == "80 m²" and values.text_measure(4.4, "length") == "4,4 m"
    finally:
        values.UNIT = before


def test_the_old_metres_mode_is_distance(tmp_path):
    import json
    filepath = tmp_path / "viejo.json"
    filepath.write_text(json.dumps({"parametrico": 1, "nodos": {
        "viga": {"tipo": "Línea", "desde": [0, 0, 0], "hasta": [8, 0, 0]},
        "p": {"tipo": "Puntos de curva", "curva": {"nodo": "viga"}, "modo": "metros", "posiciones": "2; -2"}}}))
    g = open_(filepath).graph
    assert g.nodes["p"].inputs["mode"] == "distance" and np.allclose(g.value("p").values[:, 0], [2, 6])


def test_line_by_direction_and_move_up():
    from tensela.graph import Graph
    g = Graph()
    g.node("Point", "c", x=4, y=2.5, z=5)
    g.node("Line by direction", "mástil", from_=g.nodes["c"], length=3)            # by default, upwards
    assert np.allclose(g.value("mástil").values, [[4, 2.5, 5], [4, 2.5, 8]])
    g.node("Move", "arriba", geometry=g.nodes["c"], distance=3)                    # Move also goes up
    assert np.allclose(g.value("arriba").values, [4, 2.5, 8])
    g.node("Info", "ver", value=g.nodes["c"])                                         # Panel is called Info
    assert g.nodes["ver"].kind.name == "Info" and g.node("Panel", "viejo", value=g.nodes["c"]).kind.name == "Info"


def test_move_from_point_to_point():
    from tensela.graph import Graph
    g = Graph()
    g.node("Prism", "bloque", width=8, depth=5, height=10)
    g.node("Centroid", "c", geometry=g.nodes["bloque"])
    g.node("Point", "destino", x=30, y=10)
    g.node("Move", "llevado", geometry=g.nodes["bloque"], mode='point to point', from_=g.nodes["c"],
           to=g.nodes["destino"])
    assert np.allclose(measures.centroid(g.value("llevado")).values, [30, 10, 0])   # its centroid, at the target
    g.node("Move", "a medias", geometry=g.nodes["bloque"], mode='point to point')
    with pytest.raises(Exception, match="«desde» y «hasta»"):
        g.value("a medias")


def test_extrude_with_caps_gives_a_closed_body():
    plan = geo.drawn_curve([[0, 0, 0], [12, 0, 0], [12, 4, 0], [4, 4, 0], [4, 12, 0], [0, 12, 0]], degree=1,
                                closed=True)
    for vector in ((0, 0, 3), (0, 0, -3)):
        body = geo.extrude(plan, vector, caps=True)
        assert measures.volume(body).values == pytest.approx(240)
    on_reverse = geo.drawn_curve([[0, 0, 0], [0, 12, 0], [4, 12, 0], [4, 4, 0], [12, 4, 0], [12, 0, 0]], degree=1,
                                  closed=True)
    assert measures.volume(geo.extrude(on_reverse, (0, 0, 3), caps=True)).values == pytest.approx(240)
    assert measures.volume(geo.extrude(geo.rectangle(4, 3), (0, 0, 2), caps=True)).values == pytest.approx(24)
    with pytest.raises(ShapeError, match="cerrada"):
        geo.extrude(geo.line((0, 0, 0), (1, 0, 0)), (0, 0, 1), caps=True)


def test_booleans():
    pytest.importorskip("manifold3d")
    from tensela.data import series
    wall = geo.prism(10, 0.3, 3, (0, 0, 0))
    bays = geo.move(geo.prism(1.2, 1, 1.5, (0, -0.35, 0.9)), geo.point(series(3, 1.5, 3, "vano"), 0, 0))
    assert measures.volume(meshes.boolean(wall, bays, 'difference')).values == pytest.approx(9 - 3 * 0.54)
    a, b = geo.box(2, 2, 2), geo.move(geo.box(2, 2, 2), (1, 1, 1))
    assert measures.volume(meshes.boolean(a, b, 'union')).values == pytest.approx(15)
    assert measures.volume(meshes.boolean(a, b, 'intersection')).values == pytest.approx(1)
    with pytest.raises(ShapeError, match="cuerpo cerrado"):
        meshes.boolean(geo.rectangle(2, 2), a)
    with pytest.raises(ShapeError, match="No queda nada"):
        meshes.boolean(a, geo.move(geo.box(1, 1, 1), (10, 0, 0)), 'intersection')





def test_a_body_that_folds_over_itself_is_refused_before_the_boolean():
    """A box morphed into corners in the wrong order pinches through itself, its side faces turned into «bow ties»:
    with forty of them the boolean library never ended, or broke (a wall of cells with its block at 0).
    Now it says so first; a healthy body, and a twisted panel that does not fold, still pass."""
    pytest.importorskip("manifold3d")
    from tensela.data import Data
    corners = [(0.04, -0.2, 0.04), (-0.04, -0.2, 0.04), (-0.02, 0.2, -0.1), (-0.1, 0.2, -0.1),
               (0.04, -0.2, -0.04), (-0.04, -0.2, -0.04), (-0.02, 0.2, -0.02), (-0.1, 0.2, -0.02)]
    folded = geo.morph(geo.box(1, 1, 1), Data(np.array(corners, dtype=float), ("corner",), "corners", kind=geo.POINT))
    with pytest.raises(ShapeError, match="se dobla sobre sí mismo"):
        meshes.boolean(geo.box(1, 1, 1), folded)
    twisted = [(0, 0, 0), (1, 0, 0), (1, 1, 0.3), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1.2)]
    leaning = geo.morph(geo.box(1, 1, 1), Data(np.array(twisted, dtype=float), ("corner",), "corners", kind=geo.POINT))
    assert measures.volume(meshes.boolean(leaning, geo.box(0.2, 0.2, 0.2), 'difference')).values > 0
