"""Challenges of structures on surfaces: diagrid, space frame, Chebyshev net."""
from collections import Counter

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import Data, ShapeError
from tensela.structures import diagrid, mesh_space, chebyshev_net
from tensela.graph import Graph
from tensela.surfaces import revolve, surface_nurbs


def tower():
    return revolve(G.line_by_direction((10, 0, 0), (0, 0, 1), 40))


def pairs(members):
    return {frozenset([tuple(np.round(b[0], 5)), tuple(np.round(b[-1], 5))]) for b in members.values}


def test_diagrid_on_a_tower_goes_round_without_seam():
    d = diagrid(tower(), 12, 8)
    assert d.shape == "barra 384"                       # 2 diagonals per joint, without the top row
    assert len(pairs(d)) == 384                         # ninguna repetida
    degrees = Counter(e for p in pairs(d) for e in p)
    assert Counter(degrees.values()) == {4: 180, 2: 24}  # 4 members per joint; 2 at the top and bottom
    lengths = np.linalg.norm(d.values[:, 1] - d.values[:, 0], axis=1)
    assert np.ptp(lengths) < 1e-2                        # on a cylinder, all equal
    crossings = diagrid(tower(), 12, 8, 'crossings').values
    assert len(crossings) == 204
    assert all(np.min(np.linalg.norm(crossings - e, axis=1)) < 1e-6 for b in d.values for e in (b[0], b[-1]))


def test_rings_and_curved_members():
    a = diagrid(tower(), 12, 8, 'rings')
    assert a.shape == "anillo 17" and a.kind.closed
    assert np.allclose(a.values[:, 0, 2], np.linspace(0, 40, 17))
    c = diagrid(tower(), 12, 8, members='curves')
    assert np.allclose(np.linalg.norm(c.values[..., :2], axis=-1), 10, atol=0.05)   # they follow the surface
    assert c.values.shape[1] > 2
    v = diagrid(tower(), 12, 8, 'rings', rings_along="v")
    assert v.shape == "anillo 24" and not v.kind.closed


def test_diagrid_on_an_open_surface():
    x, y = np.meshgrid(np.arange(5) * 3.0, np.arange(4) * 3.0, indexing="ij")
    pts = Data(np.stack([x, y, np.zeros_like(x)], -1), ("f", "c"), kind=G.POINT)
    d = diagrid(surface_nurbs(pts, degree_u=1, degree_v=1), 4, 3)
    assert d.shape == "barra 48"                        # 4 × 3 diamonds of 4 members
    assert np.allclose(d.values[..., 2], 0)
    with pytest.raises(ShapeError):
        diagrid(tower(), 0, 3)


def test_diagrid_node_with_tube_and_cap():
    g = Graph()
    g.node("Line by direction", "perfil", from_=(10, 0, 0), direction=(0, 0, 1), length=40)
    g.node("Revolve", "torre", profile=g.nodes["perfil"])
    g.node("Diagrid", "diagonales", surface=g.nodes["torre"], divisions_u=6, divisions_v=4)
    g.node("Pipe", "barras", curves=g.nodes["diagonales"], radius=0.3)
    g.node("Diagrid", "anillos", surface=g.nodes["torre"], divisions_u=6, divisions_v=4, what='rings')
    g.node("Cap", "forjados", curve=g.nodes["anillos"])
    assert not g.compute_all()
    assert g.value("barras").shape == "barra 96" and g.value("forjados").shape == "anillo 9"


def plane(nx=5, ny=4, step=3.0):
    x, y = np.meshgrid(np.arange(nx) * step, np.arange(ny) * step, indexing="ij")
    return surface_nurbs(Data(np.stack([x, y, np.zeros_like(x)], -1), ("f", "c"), kind=G.POINT), degree_u=1, degree_v=1)


def test_space_frame_on_a_flat_roof():
    m = lambda q: mesh_space(plane(), 4, 3, 1.5, q)
    assert m('top chord').shape == "barra 31"     # 4·4 + 5·3
    assert m('bottom chord').shape == "barra 17"     # 3·3 + 4·2
    assert m('diagonals').shape == "barra 48"          # 4 per module
    assert m('all members').shape == "barra 96"
    above, below = m('top crossings').values, m('bottom crossings').values
    assert len(above) == 20 and len(below) == 12
    assert np.allclose(above[:, 2], 0) and np.allclose(below[:, 2], -1.5)   # the face looks up: it goes down
    d = m('diagonals').values
    assert np.allclose(np.linalg.norm(d[:, 1] - d[:, 0], axis=1), np.sqrt(1.5 ** 2 * 3))
    assert np.allclose(mesh_space(plane(), 4, 3, -1.5, 'bottom crossings').values[:, 2], 1.5)
    with pytest.raises(ShapeError):
        mesh_space(plane(), 1, 1, 1.0, 'bottom chord')


def test_space_frame_on_a_tower_closes_round():
    t = tower()
    assert mesh_space(t, 12, 8, 1.0).shape == "barra 768"      # 204 + 180 + 384
    below = mesh_space(t, 12, 8, 1.0, 'bottom crossings').values
    assert np.allclose(np.linalg.norm(below[:, :2], axis=1), 9, atol=0.02)   # hacia adentro
    sup = mesh_space(t, 12, 8, 1.0, 'top chord')
    assert len(pairs(sup)) == len(sup.values)                      # without repeated members at the seam
    assert len(pairs(mesh_space(t, 2, 2, 1.0, 'bottom chord'))) == len(
        mesh_space(t, 2, 2, 1.0, 'bottom chord').values)


def test_space_frame_node():
    g = Graph()
    g.node("Line by direction", "perfil", from_=(10, 0, 0), direction=(0, 0, 1), length=40)
    g.node("Revolve", "torre", profile=g.nodes["perfil"])
    g.node("Space frame", "estructura", surface=g.nodes["torre"], divisions_u=6, divisions_v=4, truss_depth=1.2)
    g.node("Pipe", "barras", curves=g.nodes["estructura"], radius=0.1)
    assert not g.compute_all()
    assert g.value("barras").shape == "barra 192"                   # (6·5 + 6·4) + (6·4 + 6·3) + 6·4·4


def sides(net):
    v = net.values
    s = np.linalg.norm(np.diff(v, axis=1), axis=-1)
    return s[s > 1e-9]


def test_chebyshev_on_the_plane_is_a_grid_of_diamonds():
    p = plane(5, 5, 5.0)                                  # 20 × 20
    n = chebyshev_net(p, step=1.0, count=8, what='knots').values
    assert len(n) == 17 * 17 and np.allclose(n[:, 2], 0)
    for ang in (90, 60):
        net = chebyshev_net(p, step=1.0, count=8, angle=ang, what='laths along u')
        assert net.shape == "listón 17" and np.allclose(sides(net), 1.0)
    a = chebyshev_net(p, step=1.0, count=2, angle=60, what='knots').values
    centre = np.array([10.0, 10.0, 0])
    neighbours = a[np.isclose(np.linalg.norm(a - centre, axis=1), 1.0)]
    assert len(neighbours) == 6                              # at 60°, diamonds of two equilateral triangles
    with pytest.raises(ShapeError):
        chebyshev_net(p, angle=0)


def test_chebyshev_on_a_dome_keeps_the_length():
    g = Graph()
    g.node("Arc", "perfil", mode='centre and angles', radius=10.0, plane='elevation')
    g.node("Revolve", "cúpula", profile=g.nodes["perfil"])
    g.node("Chebyshev net", "red", surface=g.nodes["cúpula"], u=0.3, v=0.3, step=1.0, count=10)
    net = g.value("red")
    assert net.shape == "listón 36" and np.allclose(sides(net), 1.0, atol=1e-4)    # lados iguales
    knots = chebyshev_net(g.value("cúpula"), 0.3, 0.3, 1.0, 10, what='knots').values
    assert np.allclose(np.linalg.norm(knots, axis=1), 10, atol=0.02)               # on the sphere
    assert len(knots) > 250


def test_tube_with_rectangular_section_and_profile():
    from tensela import meshes as meshes
    beam = G.line_by_direction((0, 0, 3), (1, 0, 0), 6)
    v = meshes.pipe(beam, section="rectangular", width=0.3, height=0.6).values.reshape(2, -1, 3)[0]
    assert np.isclose(np.ptp(v[:, 1]), 0.3) and np.isclose(np.ptp(v[:, 2]), 0.6)    # viga: ancho horizontal
    column = G.line_by_direction((0, 10, 0), (0, 0, 1), 4)
    v = meshes.pipe(column, section="rectangular", width=0.2, height=0.6).values.reshape(2, -1, 3)[0]
    assert np.isclose(np.ptp(v[:, 1]), 0.6) and np.isclose(np.ptp(v[:, 0]), 0.2)    # column: the height towards the axis
    v = meshes.pipe(beam, section="rectangular", width=0.3, height=0.6, rotation=90).values.reshape(2, -1, 3)[0]
    assert np.isclose(np.ptp(v[:, 1]), 0.6)
    g = Graph()
    g.node("Line by direction", "eje", from_=(0, 0, 0), direction=(1, 0, 0), length=4)
    g.node("NURBS Curve", "L", points=[[0, 0, 0], [0.2, 0, 0], [0.2, 0.02, 0], [0.02, 0.02, 0], [0.02, 0.2, 0],
                                       [0, 0.2, 0]], degree=1, closed=True)
    g.node("Pipe", "angular", curves=g.nodes["eje"], section='profile', profile=g.nodes["L"])
    assert not g.compute_all()
    assert g.value("angular").kind.grid == (2, 13)                  # 6 corners, each one twice, and it closes


def test_sewn_normals_sew_the_seam_and_respect_the_edges():
    from tensela import meshes as meshes
    from tensela.ui.viewer import _stitched_normals, to_mesh
    beam = G.line_by_direction((0, 0, 0), (1, 0, 0), 4)
    m = _stitched_normals(to_mesh(meshes.pipe(beam, section="rectangular", width=1, height=1)))
    n = np.asarray(m.point_data["Normals"])
    faces = np.abs(n).max(axis=1)
    assert np.allclose(faces, 1, atol=1e-6)                             # each normal, that of its face (not at 45°)
    m = _stitched_normals(to_mesh(tower()))
    n, p = np.asarray(m.point_data["Normals"]), np.asarray(m.points)
    radial = p[:, :2] / np.linalg.norm(p[:, :2], axis=1, keepdims=True)
    assert np.allclose(np.abs((n[:, :2] * radial).sum(1)), 1, atol=1e-3)  # also at the seam


def test_tube_with_caps_is_a_closed_body():
    from tensela import meshes as meshes
    axis = G.line_by_direction((0, 0, 0), (1, 0, 0), 4)
    g = Graph()
    g.node("Line by direction", "eje", from_=(0, 0, 0), direction=(1, 0, 0), length=4)
    g.node("NURBS Curve", "I", points=[[-0.3, -0.4, 0], [0.3, -0.4, 0], [0.3, -0.32, 0], [0.05, -0.32, 0],
                                       [0.05, 0.32, 0], [0.3, 0.32, 0], [0.3, 0.4, 0], [-0.3, 0.4, 0],
                                       [-0.3, 0.32, 0], [-0.05, 0.32, 0], [-0.05, -0.32, 0], [-0.3, -0.32, 0]],
           degree=1, closed=True)
    g.node("Pipe", "doble T", curves=g.nodes["eje"], section='profile', profile=g.nodes["I"], caps=True)
    assert not g.compute_all()

    def volume(t):
        v, F = t.values, np.array(t.kind.faces)
        return np.einsum("ij,ij->i", v[F[:, 0]], np.cross(v[F[:, 1]], v[F[:, 2]])).sum() / 6

    def closed(t):
        edges = Counter(tuple(sorted(e)) for a, b, c in t.kind.faces for e in ((a, b), (b, c), (c, a)))
        return all(k == 2 for k in edges.values())

    I = g.value("doble T")
    assert I.kind.name == "mesh" and closed(I) and np.isclose(volume(I), 0.16 * 4)   # the concave one (the I) too
    rect = meshes.pipe(axis, section="rectangular", width=0.3, height=0.6, caps=True)
    assert closed(rect) and np.isclose(volume(rect), 0.3 * 0.6 * 4)                    # hacia fuera: positivo
    assert volume(meshes.pipe(axis, 0.5, 16, caps=True)) > 3.0
    assert meshes.pipe(axis, 0.5).kind.name == "surface"                             # by default, without caps
    hoop = meshes.pipe(G.circle((0, 0, 0), 5), 0.3, caps=True)
    assert hoop.kind.name == "surface"                                               # a hoop has no ends


def test_continuous_diagonals_cover_the_same_members():
    d = diagrid(tower(), 12, 8, continuous=True)
    assert d.shape == "diagonal 24"                                    # 12 helices to each side
    assert np.allclose(d.values[:, 0, 2], 0) and np.allclose(d.values[:, -1, 2], 40)   # from bottom to top
    runs = {frozenset([tuple(np.round(a, 5)), tuple(np.round(b, 5))])
              for line in d.values for a, b in zip(line[:-1], line[1:]) if np.linalg.norm(b - a) > 1e-9}
    assert runs == pairs(diagrid(tower(), 12, 8))                    # the same members, continuous
    open_ = diagrid(plane(), 4, 3, continuous=True)
    assert open_.shape == "diagonal 12"


def test_tube_with_mitre_at_the_breaks():
    from tensela import meshes as meshes
    ell = Data(np.array([[0, 0, 0], [4, 0, 0], [4, 4, 0.0]]), kind=G.CURVE)
    corner = meshes.pipe(ell, section="rectangular", width=1, height=1).values.reshape(3, -1, 3)[1]
    xy = {tuple(np.round(p[:2], 6)) for p in corner}
    assert xy == {(4.5, -0.5), (3.5, 0.5)}                             # the outer corner and the inner one
