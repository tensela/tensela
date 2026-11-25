"""Gaussian and mean curvature, developable surfaces and the curvature pattern (perforations)."""
import numpy as np
import pytest

from tensela import geometry as G
from tensela import surfaces as S
from tensela.data import Data, ShapeError
from tensela.graph import Graph


def surfaces():
    g = Graph()
    g.node("Arc", "p", mode='centre and angles', radius=6.0, plane='elevation')
    g.node("Revolve", "cúpula", profile=g.nodes["p"])
    g.node("Line by direction", "l", from_=(4, 0, 0), direction=(0, 0, 1), length=10)
    g.node("Revolve", "cilindro", profile=g.nodes["l"])
    g.node("Line by direction", "lc", from_=(5, 0, 0), direction=(-5, 0, 8), length=9.434)
    g.node("Revolve", "cono", profile=g.nodes["lc"])
    g.node("NURBS Curve", "c", points=[[0, 0, 0], [4, 3, 0], [8, -1, 0], [12, 2, 0]])
    g.node("Extrude", "cilindro general", curve=g.nodes["c"], vector=(0, 0, 6))
    g.node("Extrude", "cono general", curve=g.nodes["c"], mode='to a point', point=(6, 8, 9))
    g.node("Line by direction", "b1", from_=(0, 0, 0), direction=(1, 0, 0), length=10)
    g.node("Line by direction", "b2", from_=(0, 10, 3), direction=(1, 0, -0.6), length=10)
    g.node("Edge surface", "paraboloide", a=g.nodes["b1"], b=g.nodes["b2"])
    g.node("Series", "t", count=41, step=9.0, level="i")
    for n, f in (("hx", "6 * cos(a)"), ("hy", "6 * sen(a)"), ("hz", "a / 30")):
        g.node("Formula", n, formula=f, a=g.nodes["t"])
    g.node("Point", "hp", x=g.nodes["hx"], y=g.nodes["hy"], z=g.nodes["hz"])
    g.node("Curve through points", "hélice", points=g.nodes["hp"])
    g.node("Points on curve", "pies", curve=g.nodes["hélice"], mode='parts', count=24)
    g.node("Tangent", "dir", curve=g.nodes["hélice"], mode='parts', count=24)
    g.node("Line by direction", "gen", from_=g.nodes["pies"], direction=g.nodes["dir"], length=5.0)
    g.node("Loft", "desarrollable tangente", curves=g.nodes["gen"])
    return g


def test_exact_gaussian_and_mean_curvature():
    g = surfaces()
    c = lambda n, q: S.surface_curvature(g.value(n), q, count_u=5, count_v=5).values
    assert np.median(c("cúpula", 'Gaussian')) == pytest.approx(1 / 36, rel=1e-3)
    assert abs(np.median(c("cúpula", 'mean'))) == pytest.approx(1 / 6, rel=1e-3)
    assert np.abs(c("cilindro", 'Gaussian')).max() < 1e-9
    assert np.abs(c("cilindro", 'mean')) == pytest.approx(np.full((5, 5), 1 / 8), rel=1e-3)
    middle = S.surface_curvature(g.value("cono"), 'mean', count_u=1, count_v=5).values
    assert abs(middle[2]) == pytest.approx(8 / 9.434 / (2 * 2.5), rel=2e-3)   # a media altura, radio 2,5
    assert c("cúpula", 'Gaussian').shape == (5, 5)


def test_developable_yes_or_no():
    g = surfaces()
    for n in ("cilindro", "cono", "cilindro general", "cono general", "desarrollable tangente"):
        assert S.surface_curvature(g.value(n), 'developable').values, n
    for n in ("cúpula", "paraboloide"):
        assert not S.surface_curvature(g.value(n), 'developable').values, n
    g.node("Surface curvature", "¿?", surface=g.nodes["cúpula"], what='developable')
    assert not g.value("¿?").values


def test_points_at_the_centres_of_the_panels():
    x, y = np.meshgrid(np.arange(3) * 5.0, np.arange(3) * 5.0, indexing="ij")
    plane = S.surface_nurbs(Data(np.stack([x, y, np.zeros_like(x)], -1), ("f", "c"), kind=G.POINT),
                               degree_u=1, degree_v=1)
    p = S.surface_points(plane, 'points', 'centres', 4, 2).values
    assert np.allclose(p[:, 0, 0], [1.25, 3.75, 6.25, 8.75]) and np.allclose(p[0, :, 1], [2.5, 7.5])


def test_circle_resting_on_a_normal():
    c = G.circle((1, 2, 3), 2.0, normal=(1, 0, 0)).values
    assert np.allclose(c[:, 0], 1) and np.allclose(np.linalg.norm(c - [1, 2, 3], axis=1), 2)
    n = Data(np.array([[0, 0, 1], [0, 1, 0.0]]), ("p",), kind=G.VECTOR)
    p = Data(np.array([[0, 0, 0], [5, 5, 5.0]]), ("p",), kind=G.POINT)
    assert np.allclose(G.circle(p, 0.5, normal=n).values[1][:, 1], 5)


def perforated_relief(max_radius=0.18, threshold=0.05, n=(20, 14)):
    g = Graph()
    g.node("Series", "x", count=7, step=4.0, level="fila")
    g.node("Series", "y", count=5, step=4.0, level="columna")
    g.node("Formula", "z", formula="4 * exp(-(b - 0,45 * a - 2) * (b - 0,45 * a - 2) / 6)", a=g.nodes["x"],
           b=g.nodes["y"])
    g.node("Point", "pc", x=g.nodes["x"], y=g.nodes["y"], z=g.nodes["z"])
    g.node("NURBS Surface", "relieve", points=g.nodes["pc"])
    common = dict(surface=g.nodes["relieve"], mode='centres', count_u=n[0], count_v=n[1])
    g.node("Surface points", "centros", **common)
    g.node("Surface points", "normales", what='normals', **common)
    g.node("Surface curvature", "k", what='mean', **common)
    g.node("Formula", "radios", formula="min(abs(a) * 4, b)", a=g.nodes["k"], b=max_radius)
    g.node("Circle", "círculos", centre=g.nodes["centros"], radius=g.nodes["radios"], normal=g.nodes["normales"])
    g.node("Formula", "grandes", formula="a > b", a=g.nodes["radios"], b=threshold)
    g.node("Filter", "perforaciones", data=g.nodes["círculos"], condition=g.nodes["grandes"])
    for q in ("todos los trozos", "el más grande", "los demás"):
        g.node("Split surface", q, surface=g.nodes["relieve"], curves=g.nodes["perforaciones"], what=q)
    return g


def area(d):
    if d.levels:
        x = np.asarray(d.values).reshape(len(d.values), -1, 3, 3)
        return np.linalg.norm(np.cross(x[..., 1, :] - x[..., 0, :], x[..., 2, :] - x[..., 0, :]), axis=-1).sum(-1) / 2
    v, f = d.values, np.array(d.kind.faces)
    return np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1).sum() / 2


def test_fast_and_exact_perforations():
    g = perforated_relief()
    radii = g.value("radios").values
    holes = int((radii > 0.05).sum())
    assert holes > 40                                                  # by the fast way
    sheet, offcuts = g.value("el más grande"), g.value("los demás")
    assert offcuts.shape == f"trozo {holes}"
    assert sheet.levels == () and sheet.kind.name == "mesh"
    assert area(offcuts).sum() == pytest.approx((np.pi * radii[radii > 0.05] ** 2).sum(), rel=0.01)
    r = g.value("relieve")
    R = np.asarray(r.values).reshape(*r.kind.grid, 3)
    whole = np.linalg.norm(np.cross(np.diff(R, axis=0)[:, :-1], np.diff(R, axis=1)[:-1]), axis=-1).sum()
    assert area(sheet) + area(offcuts).sum() == pytest.approx(whole, rel=2e-3)
    with pytest.raises(Exception, match="memoria"):                    # all together would take up too much
        g.value("todos los trozos")
    few = perforated_relief(n=(8, 6))
    all_ = few.value("todos los trozos")
    assert area(all_)[0] == pytest.approx(area(few.value("el más grande")), rel=1e-9)


def test_many_touching_perforations_warn():
    g = perforated_relief(max_radius=0.6, threshold=0.05)
    with pytest.raises(Exception, match="se tocan"):
        g.value("el más grande")


def test_without_perforations_the_sheet_stays_whole_and_the_view_does_not_crash():
    g = perforated_relief(threshold=10.0)                                  # Filter leaves no circle
    assert g.value("perforaciones").empty == g.value("perforaciones").values.shape[0] * \
        g.value("perforaciones").values.shape[1]
    sheet = g.value("el más grande")
    assert sheet.kind.name == "mesh" and area(sheet) > 300
    with pytest.raises(Exception, match="ninguna curva la corta"):
        g.value("los demás")
    import pyvista as pv
    from tensela.ui.viewer import draw
    pl = pv.Plotter(off_screen=True)
    assert draw(pl, "perforaciones", g.value("perforaciones")) is not None
    pl.close()
