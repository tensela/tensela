"""Unroll: flattening surfaces to cut them from a sheet."""
import numpy as np
import pytest

from tensela.data import ShapeError
from tensela.unrolling import unroll
from tensela.graph import Graph


def area(data):
    total = 0.0
    for v in (data.values[data.mask] if data.levels else data.values[None]):
        for face in data.kind.faces:
            for j in range(1, len(face) - 1):
                a, b, c = v[face[0]], v[face[j]], v[face[j + 1]]
                total += np.linalg.norm(np.cross(b - a, c - a)) / 2
    return total


def graph():
    g = Graph()
    g.node("Line by direction", "l", from_=(4, 0, 0), direction=(0, 0, 1), length=10)
    g.node("Revolve", "cilindro", profile=g.nodes["l"])
    g.node("Line by direction", "lc", from_=(5, 0, 0), direction=(-5, 0, 8), length=9.434)
    g.node("Revolve", "cono", profile=g.nodes["lc"])
    g.node("NURBS Curve", "c", points=[[0, 0, 0], [4, 3, 0], [8, -1, 0], [12, 2, 0]])
    g.node("Extrude", "cilindro general", curve=g.nodes["c"], vector=(0, 0, 6))
    g.node("Extrude", "cono general", curve=g.nodes["c"], mode='to a point', point=(6, 8, 9))
    g.node("Arc", "p", mode='centre and angles', radius=6.0, plane='elevation')
    g.node("Revolve", "cúpula", profile=g.nodes["p"])
    g.node("Number", "n", value=12)
    g.node("Formula", "ancho", formula="1 / a", a=g.nodes["n"])
    g.node("Series", "desde", count=g.nodes["n"], step=g.nodes["ancho"], level="gajo")
    g.node("Formula", "hasta", formula="a + b", a=g.nodes["desde"], b=g.nodes["ancho"])
    g.node("Sub surface", "gajos", surface=g.nodes["cúpula"], u_from=g.nodes["desde"],
           u_to=g.nodes["hasta"])
    return g


@pytest.mark.parametrize('name', ["cilindro", "cono", "cilindro general", "cono general"])
def test_developables_flatten_exactly(name):
    s = graph().value(name)
    d = unroll(s)
    assert np.allclose(d.values[..., 2], 0)                            # on the XY plane
    assert area(d) == pytest.approx(area(s), rel=1e-9)                  # without stretching
    assert float(unroll(s, 'stretch').values) < 1e-6
    assert d.kind.grid == s.kind.grid                             # it is still the same grid


def test_a_cylinder_opens_into_a_rectangle():
    d = unroll(graph().value("cilindro")).values
    sides = np.ptp(d[..., :2].reshape(-1, 2), axis=0)
    assert sorted(sides) == pytest.approx(sorted([10.0, 2 * np.pi * 4]), rel=2e-3)   # height × the circumference


def test_gores_of_a_dome():
    g = graph()
    gores = g.value("gajos")
    assert gores.shape == "parte 12"
    e12 = unroll(gores, 'stretch').values
    assert e12.shape == (12,) and (e12 < 0.5).all() and (e12 > 0).all()   # casi desarrollables
    g.change("n", "value", 6)
    e6 = unroll(g.value("gajos"), 'stretch').values
    assert e6.mean() > e12.mean()                                          # wider ones stretch more
    outlines = unroll(gores, 'outlines')
    assert outlines.shape == "borde 12" and outlines.kind.closed
    planes = unroll(gores, spacing=0.5).values
    xs = [(p[:, 0].min(), p[:, 0].max()) for p in planes]
    assert all(b[0] >= a[1] + 0.5 - 1e-9 for a, b in zip(xs, xs[1:]))      # in a row, without overlapping
    lengths = [np.ptp(p[:, 1]) for p in planes]
    assert np.mean(lengths) == pytest.approx(np.pi * 6 / 2, rel=0.02)        # standing: the meridian, along y


def test_meshes_with_flipped_triangles():
    g = Graph()
    g.node("Series", "x", count=7, step=4.0, level="fila")
    g.node("Series", "y", count=5, step=4.0, level="columna")
    g.node("Formula", "z", formula="4 * exp(-(b - 0,45 * a - 2) * (b - 0,45 * a - 2) / 6)", a=g.nodes["x"],
           b=g.nodes["y"])
    g.node("Point", "pc", x=g.nodes["x"], y=g.nodes["y"], z=g.nodes["z"])
    g.node("NURBS Surface", "relieve", points=g.nodes["pc"])
    common = dict(surface=g.nodes["relieve"], mode='centres', count_u=12, count_v=8)
    g.node("Surface points", "centros", **common)
    g.node("Surface points", "normales", what='normals', **common)
    g.node("Circle", "círculos", centre=g.nodes["centros"], radius=0.6, normal=g.nodes["normales"])
    g.node("Split surface", "recortes", surface=g.nodes["relieve"], curves=g.nodes["círculos"], what='the others')
    offcuts = g.value("recortes")
    e = unroll(offcuts, 'stretch').values
    assert e.max() < 0.05                                                   # almost flat discs: almost nothing
    assert area(unroll(offcuts)) == pytest.approx(area(offcuts), rel=1e-3)


def test_part_of_surface_with_lists():
    g = graph()
    g.node("Sub surface", "dos", surface=g.nodes["cúpula"], u_from="0; 0,5", u_to="0,25; 0,75")
    assert g.value("dos").shape == "parte 2"
    g.node("Sub surface", "mal", surface=g.nodes["cúpula"], u_from="0; 0,5; 0,6", u_to="0,25; 0,75")
    with pytest.raises(Exception, match="misma cantidad"):
        g.value("mal")


def bodies():
    g = Graph()
    g.node("Box", "caja", width=2, depth=3, height=4)
    a = np.linspace(0, 2 * np.pi, 7)[:-1]
    g.node("NURBS Curve", "hex", points=[[3 * np.cos(t), 3 * np.sin(t), 0] for t in a], degree=1, closed=True)
    g.node("Extrude", "prisma", curve=g.nodes["hex"], vector=(0, 0, 5), caps=True)
    g.node("NURBS Curve", "cuad", points=[[0, 0, 0], [4, 0, 0], [4, 4, 0], [0, 4, 0]], degree=1, closed=True)
    g.node("Extrude", "pirámide", curve=g.nodes["cuad"], mode='to a point', point=(2, 2, 5), caps=True)
    return g


@pytest.mark.parametrize('name, faces', [("caja", 6), ("prisma", 8), ("pirámide", 5)])
def test_the_net_of_a_body(name, faces):
    s = bodies().value(name)
    net = unroll(s)
    assert np.allclose(net.values[..., 2], 0) and area(net) == pytest.approx(area(s), rel=1e-9)
    outline = unroll(s, 'outlines')
    assert outline.shape == "borde 1"                                      # a single cut, closed
    q = outline.values[0][:, :2]
    enclosed = abs((q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]).sum()) / 2
    assert enclosed == pytest.approx(area(s), rel=1e-6)                    # the net does not overlap itself
    assert unroll(s, 'folds').shape == f"pliegue {faces - 1}"       # one fold per face minus one
    assert float(unroll(s, 'stretch').values) == 0


def test_the_net_of_a_box_as_a_cross():
    q = unroll(bodies().value("caja"), 'outlines').values[0]
    assert len(q) == 14                                                     # the cross: 14 corners


def test_a_closed_curved_body_warns():
    g = Graph()
    g.node("Arc", "p", mode='centre and angles', radius=3.0, plane='elevation')
    g.node("Revolve", "cúpula", profile=g.nodes["p"])
    with pytest.raises(ShapeError, match="No hay pliegues"):
        unroll(g.value("cúpula"), 'folds')


def test_the_net_is_one_polygon_per_face():
    g = bodies()
    assert [len(c) for c in unroll(g.value("caja")).kind.faces] == [4] * 6
    assert sorted(len(c) for c in unroll(g.value("prisma")).kind.faces) == [4] * 6 + [6, 6]   # without the
    assert sorted(len(c) for c in unroll(g.value("pirámide")).kind.faces) == [3, 3, 3, 3, 4]  # thin triangles
