"""Surfaces of the challenge «Curves and surfaces»: NURBS (S1), revolution and sweep (S2), by edges (S3)."""

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import Data, ShapeError
from tensela.geometry import POINT
from tensela.graph import Graph
from tensela.surfaces import sweep, revolve, surface_nurbs


def grid(nu=4, nv=5, z=None):
    x, y = np.meshgrid(np.arange(float(nu)), np.arange(float(nv)), indexing="ij")
    return Data(np.stack([x, y, np.zeros_like(x) if z is None else z], -1), ("u", "v"), kind=POINT)


def points(s):
    return s.values.reshape(s.values.shape[:-2] + s.kind.grid + (3,))


def test_flat_nurbs_surface_passes_through_the_corners():
    r = points(surface_nurbs(grid()))
    assert np.allclose(r[0, 0], [0, 0, 0]) and np.allclose(r[-1, -1], [3, 4, 0]) and np.allclose(r[..., 2], 0)


def test_nurbs_surface_of_degree_1_is_the_grid():
    s = surface_nurbs(grid(), degree_u=1, degree_v=1)
    r = points(s)
    assert np.allclose(r[::16][:, ::16], grid().values)


def test_a_raised_point_attracts_the_surface_without_touching_it():
    z = np.zeros((5, 5))
    z[2, 2] = 4
    r = points(surface_nurbs(grid(5, 5, z)))
    assert 0 < r[..., 2].max() < 4                                    # it attracts it, it does not pass through it
    heavy = points(surface_nurbs(grid(5, 5, z), weights="; ".join(["1"] * 12 + ["8"] + ["1"] * 12)))
    assert heavy[..., 2].max() > r[..., 2].max()                       # with more weight, it comes closer


def test_closed_nurbs_surface_and_warnings():
    ang = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    p = np.stack([np.stack([np.cos(ang), np.sin(ang), np.full(8, z)], -1) for z in (0, 1, 2)])
    r = points(surface_nurbs(Data(p, ("piso", "lado"), kind=POINT), closed_v=True))
    assert np.allclose(r[:, 0], r[:, -1])                               # the seam closes
    with pytest.raises(ShapeError, match="filas × columnas"):
        surface_nurbs(Data(p[0], ("lado",), kind=POINT))
    with pytest.raises(ShapeError, match="pesos"):
        surface_nurbs(grid(), weights="1; 2")


def test_revolve():
    profile = G.line_by_direction((2, 0, 0), (0, 0, 1), 5)
    r = points(revolve(profile))
    assert np.allclose(np.linalg.norm(r[..., :2], axis=-1), 2) and np.allclose(r[0], r[-1])
    r = points(revolve(profile, degrees=90))
    assert np.allclose(r[-1, 0], [0, 2, 0])
    with pytest.raises(ShapeError, match="eje"):
        revolve(profile, axis=(0, 0, 0))


def test_straight_sweep_and_centred_on_a_closed_path():
    pipe = points(sweep(G.circle((0, 0, 0), 0.2, plane='side elevation'), G.line_by_direction((0, 0, 0), (1, 0, 0), 10)))
    assert np.allclose(np.linalg.norm(pipe[..., 1:], axis=-1), 0.2) and np.isclose(pipe[-1, :, 0].mean(), 10)
    torus = points(sweep(G.circle((30, 30, 0), 0.5), G.circle((0, 0, 0), 5), 'centred on the path'))
    radius_pipe = np.hypot(np.linalg.norm(torus[..., :2], axis=-1) - 5, torus[..., 2])
    assert np.allclose(radius_pipe, 0.5, atol=0.01) and np.allclose(torus[0], torus[-1], atol=1e-6)


def test_new_surfaces_divide_and_thicken():
    g = Graph()
    g.node("Line by direction", "perfil", from_=(2, 0, 0), direction=(0, 0, 1), length=4)
    g.node("Revolve", "columna", profile=g.nodes["perfil"])
    g.node("Grid", "paneles", rectangle=g.nodes["columna"], columns=8, rows=4)
    g.node("Thicken", "gruesa", rectangle=g.nodes["columna"], thickness=0.1)
    assert g.value("paneles").count == 32
    g.value("gruesa")


def line(a, b):
    d = np.subtract(b, a, dtype=float)
    return G.line_by_direction(a, d, float(np.linalg.norm(d)))


def test_edge_surface_in_any_order_and_direction():
    from tensela.surfaces import surface_by_edges
    a, b = line((0, 0, 0), (4, 0, 0)), line((4, 4, 0), (4, 0, 0))            # b, reversed
    c, d = line((0, 4, 0), (4, 4, 0)), line((0, 0, 0), (0, 4, 0))
    r = points(surface_by_edges(a, c, b, d))                              # desordenados
    corners = sorted(map(tuple, np.round([r[0, 0], r[0, -1], r[-1, 0], r[-1, -1]], 6)))
    assert corners == [(0, 0, 0), (0, 4, 0), (4, 0, 0), (4, 4, 0)] and np.allclose(r[..., 2], 0)
    arc = G.arc('three points', start=(0, 4, 0), middle=(2, 4, 2), end=(4, 4, 0))
    assert np.isclose(points(surface_by_edges(a, b, arc, d))[..., 2].max(), 2)   # it passes through its edges


def test_edge_surface_with_three_and_two_and_its_warnings():
    from tensela.surfaces import surface_by_edges
    surface_by_edges(line((0, 0, 0), (4, 0, 0)), line((4, 0, 0), (2, 3, 1)), line((2, 3, 1), (0, 0, 0)))
    r = points(surface_by_edges(line((0, 0, 0), (4, 0, 0)), line((4, 2, 1), (0, 2, 1))))
    assert np.allclose(r[-1, 0], [0, 2, 1])                                    # ruled: the second one, straightened
    with pytest.raises(ShapeError, match="no se tocan"):
        surface_by_edges(line((0, 0, 0), (4, 0, 0)), line((4, 0, 0), (4, 4, 0)), line((0, 9, 0), (4, 9, 0)))
    with pytest.raises(ShapeError, match="cerrada"):
        surface_by_edges(G.circle((0, 0, 0), 1), line((0, 0, 0), (4, 0, 0)))


def test_the_gaussian_curvature_of_a_dome_and_a_cylinder():
    """S4 · Analyse: the sphere of radius 6, 1/36; the cylinder (made from a flat sheet), 0."""
    from tensela.ui.viewer import _gauss_in_grid
    dome = revolve(G.arc('centre and angles', centre=(0, 0, 0), radius=6.0, from_=0.0, to=90.0, plane='elevation'))
    assert np.median(_gauss_in_grid(dome.values, *dome.kind.grid)) == pytest.approx(1 / 36, rel=1e-3)
    cylinder = revolve(G.line_by_direction((2, 0, 0), (0, 0, 1), 5))
    assert np.abs(_gauss_in_grid(cylinder.values, *cylinder.kind.grid)).max() < 1e-9


# --- More surfaces: isocurves, network, cap with holes, closed loft, extrude to a point, sweep with two paths ---

def test_isocurves_of_a_cylinder():
    from tensela.surfaces import isocurves
    cylinder = revolve(line((2, 0, 0), (2, 0, 5)))
    u = isocurves(cylinder, "u", count=3)
    assert u.shape == "isocurva 3" and np.allclose([c[:, 2].mean() for c in u.values], [0, 2.5, 5])
    v = isocurves(cylinder, "v", mode='fraction', positions="0; 0,25")
    assert np.allclose([np.linalg.norm(c[0, :2]) for c in v.values], 2)
    with pytest.raises(ShapeError, match="superficie"):
        isocurves(line((0, 0, 0), (1, 0, 0)))


def test_network_surface_of_unordered_curves():
    """A hyperbolic paraboloid from 4 × 5 curves in any order and direction: the surface follows it."""
    from tensela.geometry import CURVE
    from tensela.surfaces import surface_by_net
    t = np.linspace(-5, 5, 40)
    shape = lambda x, y: (x * x - y * y) / 10                                  # noqa: E731
    cu = [np.stack([np.full_like(t, x), t, shape(x, t)], -1) for x in np.linspace(-5, 5, 4)]
    cv = [np.stack([t, np.full_like(t, y), shape(t, y)], -1) for y in np.linspace(-5, 5, 5)]
    cu[1] = cu[1][::-1]
    r = points(surface_by_net(Data(np.stack([cu[2], cu[0], cu[3], cu[1]]), ("a",), kind=CURVE),
                                  Data(np.stack(cv[::-1]), ("b",), kind=CURVE)))
    assert np.abs(r[..., 2] - shape(r[..., 0], r[..., 1])).max() < 0.02
    with pytest.raises(ShapeError, match="no se cruzan"):
        far = [c + [0, 0, 5] for c in cv]
        surface_by_net(Data(np.stack(cu), ("a",), kind=CURVE), Data(np.stack(far), ("b",), kind=CURVE))


def test_cap_with_a_hole():
    slab = G.cap(G.rounded_rectangle(10, 8, 1), holes=G.circle((5, 4, 0), 1.5))
    centres = np.array([slab.values[list(c)].mean(axis=0) for c in slab.kind.faces])
    assert slab.kind.name == "mesh" and np.all(np.linalg.norm(centres[:, :2] - [5, 4], axis=1) > 1.4)
    with pytest.raises(ShapeError, match="se sale"):
        G.cap(G.rounded_rectangle(10, 8, 1), holes=G.circle((10, 4, 0), 1.5))


def test_closed_loft():
    g = Graph()
    g.node("Series", "a", count=4, step=90.0, level="sección")
    g.node("Formula", "cx", formula="5 * cos(a)", a=g.nodes["a"])
    g.node("Formula", "cy", formula="5 * sin(a)", a=g.nodes["a"])
    g.node("Point", "c", x=g.nodes["cx"], y=g.nodes["cy"])
    g.node("Circle", "aros", centre=g.nodes["c"], radius=1, plane='elevation')
    g.node("Loft", "anillo", curves=g.nodes["aros"], closed=True)
    r = points(g.value("anillo"))
    assert np.allclose(r[0], r[-1])


def test_extrude_to_a_point():
    cone = G.extrude(G.circle((0, 0, 0), 2), mode='to a point', point=(0, 0, 3))
    assert np.allclose(points(cone)[1], [0, 0, 3])
    pyramid = G.extrude(G.circle((0, 0, 0), 2), mode='to a point', point=(0, 0, 3), caps=True)
    assert pyramid.kind.name == "mesh"
    with pytest.raises(ShapeError, match='punto'):
        G.extrude(G.circle((0, 0, 0), 2), mode='to a point')


def test_sweep_with_two_paths():
    profile = G.arc('three points', start=(0, 0, 0), middle=(0, 1, 1), end=(0, 2, 0))
    r = points(sweep(profile, line((0, 0, 0), (10, 0, 0)), path_2=line((0, 2, 0), (10, 6, 0))))
    assert np.allclose(r[:, 0, 1], 0, atol=1e-6) and np.allclose(r[-1, -1], [10, 6, 0], atol=1e-6)
    assert np.isclose(r[..., 2].max(), 1, atol=1e-3)                          # the height does not stretch


def test_sweep_along_a_closed_nurbs_without_pinch():
    """The closed NURBS repeats its first point at the end: the sweep does not duplicate it (before, a zero-length span
    twisted the profile at the closure)."""
    path = G.curve_nurbs([[0, 0, 0], [6, 2, 0], [8, 8, 1], [2, 9, 0], [-3, 4, 0]], closed=True)
    r = points(sweep(G.circle((0, 0, 0), 0.3), path, 'centred on the path'))
    distance = np.array([np.min(np.linalg.norm(path.values - p, axis=1)) for p in r.reshape(-1, 3)])
    assert np.allclose(distance, 0.3, atol=0.01) and np.allclose(r[0], r[-1], atol=1e-6)


def test_normals_are_sewn_at_the_seam():
    """The seam of a closed surface (and the pole of a dome): the same normal on both sides."""
    from tensela.ui.viewer import _stitched_normals, to_mesh
    dome = revolve(G.arc('centre and angles', centre=(0, 0, 0), radius=2.0, from_=0.0, to=90.0, plane='elevation'))
    m = _stitched_normals(to_mesh(dome))
    n = np.asarray(m.point_data["Normals"]).reshape(*dome.kind.grid, 3)
    assert np.allclose(n[0], n[-1]) and np.allclose(n[:, -1], n[0, -1])            # seam and pole


# --- Surface points, flip, part, curved and uneven Grid -------------------------------

def cylinder():
    return revolve(G.line_by_direction((2, 0, 0), (0, 0, 1), 5))       # u: alrededor; v: hacia arriba


def test_points_and_normals_of_a_surface():
    from tensela.surfaces import surface_points
    p = surface_points(cylinder(), count_u=4, count_v=3)
    assert p.shape == "u 4 × v 3 = 12" and np.allclose(np.linalg.norm(p.values[..., :2], axis=-1), 2)
    point = surface_points(cylinder(), 'points', 'fractions', u=0.25, v=0.5).values
    normal = surface_points(cylinder(), 'normals', 'fractions', u=0.25, v=0.5).values
    assert np.allclose(point, [0, 2, 2.5], atol=1e-6) and np.allclose(normal, [0, 1, 0], atol=1e-6)


def test_flip_surface():
    from tensela.surfaces import reverse_surface, surface_points
    n = surface_points(cylinder(), 'normals', 'fractions', u=0.25, v=0.5).values
    for what in ('face', 'u', 'swap u and v'):
        m = surface_points(reverse_surface(cylinder(), what), 'normals', 'fractions',
                                 u=0.5 if what == 'swap u and v' else (0.75 if what == "u" else 0.25),
                                 v=0.25 if what == 'swap u and v' else 0.5).values
        assert np.allclose(m, -n, atol=1e-6), what


def test_part_of_surface_and_across_the_seam():
    from tensela.surfaces import surface_part
    r = points(surface_part(cylinder(), 0, 0.25, 0.2, 0.6))
    assert np.allclose(np.degrees(np.arctan2(r[[0, -1], 0, 1], r[[0, -1], 0, 0])), [0, 90])
    assert np.allclose(r[0, [0, -1], 2], [1, 3])
    r = points(surface_part(cylinder(), 0.9, 0.1))                       # it goes round through the seam
    assert np.allclose(np.degrees(np.arctan2(r[[0, -1], 0, 1], r[[0, -1], 0, 0])), [-36, 36], atol=0.01)


def test_uneven_grid_and_with_curved_panels():
    facade = G.grid(G.rectangle(10, 6, plane='elevation'), columns="0; 0,2; 0,5; 1", rows=3)
    assert np.allclose(np.ptp(facade.values[0, :, :, 0], axis=-1), [2, 3, 5])
    dome = revolve(G.arc('centre and angles', centre=(0, 0, 0), radius=6.0, from_=0.0, to=90.0, plane='elevation'))
    curved = G.grid(dome, columns=4, rows=12, panels='curved')
    assert curved.shape == "fila 12 × columna 4 = 48" and np.allclose(np.linalg.norm(points(curved), axis=-1), 6, atol=0.05)
    with pytest.raises(ShapeError, match='rombos'):
        G.grid(dome, columns="0; 0,5; 1", rows=4, shape='diamonds')


# --- Intersection and splitting with curves ----------------------------------------------------------

def leaning_plane():
    x, y = np.meshgrid(np.linspace(-4, 4, 5), np.linspace(-4, 4, 5), indexing="ij")
    return surface_nurbs(Data(np.stack([x, y, 2.5 + 0.3 * x], -1), ("u", "v"), kind=POINT), degree_u=1, degree_v=1)


def areas(d):
    pieces = d.values if d.levels else [d.values]
    return [float(0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum())
            for t in (e.reshape(-1, 3, 3) for e in pieces)]


def test_intersection_of_two_surfaces_and_of_a_curve():
    from tensela.surfaces import intersection
    ellipse = intersection(cylinder(), leaning_plane())
    assert ellipse.kind.name == "curve" and np.allclose(np.linalg.norm(ellipse.values[:, :2], axis=1), 2, atol=0.01)
    crossings = intersection(G.line_by_direction((-5, 0, 1), (1, 0, 0), 10), cylinder())
    assert sorted(np.round(crossings.values[:, 0], 6)) == [-2, 2]
    with pytest.raises(ShapeError, match="no atraviesa"):
        intersection(G.line_by_direction((-5, 0, 9), (1, 0, 0), 10), cylinder())


def test_split_a_surface_with_curves():
    from tensela.geometry import CURVE
    from tensela.surfaces import split_surface
    assert np.allclose(sorted(areas(split_surface(leaning_plane(), G.circle((1, 1, 0), 2)))),
                       [13.1, 53.7], atol=0.1)
    cross = Data(np.stack([G.line_by_direction((-1, -6, 0), (0, 1, 0), 12).values,
                          G.line_by_direction((-6, 1, 0), (1, 0, 0), 12).values]), ("c",), kind=CURVE)
    pieces = split_surface(leaning_plane(), cross)
    assert pieces.shape == "trozo 4" and np.isclose(sum(areas(pieces)), 8 * 8 * np.sqrt(1.09), rtol=1e-3)
    g = Graph()                                                              # a piece, with Pick
    g.node("Line by direction", "perfil", from_=(2, 0, 0), direction=(0, 0, 1), length=4)
    g.node("Revolve", "cilindro", profile=g.nodes["perfil"])
    g.node("Line by direction", "corte", from_=(0, -5, 2), direction=(0, 1, 0), length=10)
    g.node("Split surface", "trozos", surface=g.nodes["cilindro"], curves=g.nodes["corte"], direction=(1, 0, 0))
    g.node("Pick", "uno", data=g.nodes["trozos"], position=0)
    assert g.value("trozos").levels == ("piece",) and g.value("uno").kind.name == "mesh"
