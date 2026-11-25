"""Transformations: rotate about any axis and Orient (package 1); Morph and Surface morph (package 3);
vectors (package 4)."""

import numpy as np
import pytest

from tensela import geometry as G
from tensela.data import ShapeError
from tensela.graph import Graph


def _edges(values):
    """The lengths of all the vertex pairs of each element: they do not change in a Euclidean transformation."""
    v = values.reshape(-1, values.shape[-2], 3)
    return np.linalg.norm(v[:, :, None] - v[:, None, :], axis=-1)


def test_rotating_about_a_direction_matches_the_usual_axes():
    b = G.box(2, 1, 1)
    assert np.allclose(G.rotate(b, 30, "direction", direction=(0, 0, 1)).values, G.rotate(b, 30).values)
    assert np.allclose(G.rotate(b, 30, "direction", direction=(1, 0, 0)).values, G.rotate(b, 30, "x").values)


def test_rotating_about_a_diagonal_keeps_the_distance_to_the_axis():
    p = G.point(3, 0, 0)
    r = G.rotate(p, 120, "direction", direction=(1, 1, 1)).values
    assert np.allclose(r, [0, 3, 0])                     # a third of a turn about the diagonal: x → y
    assert np.isclose(np.linalg.norm(r), 3)


def test_a_direction_per_element():
    p = G.point(G.Data(np.array([1.0, 1.0]), ("piece",)), 0, 0)
    axes = G.Data(np.array([[0.0, 0, 1], [0.0, 1, 0]]), ("piece",), kind=G.VECTOR)
    r = G.rotate(p, 90, "direction", direction=axes).values
    assert np.allclose(r, [[0, 1, 0], [0, 0, -1]])


def test_rotating_about_a_direction_needs_it():
    with pytest.raises(ShapeError, match="dirección"):
        G.rotate(G.box(1, 1, 1), 30, "direction")


def test_orient_by_default_only_moves():
    b = G.box(2, 1, 1)
    assert np.allclose(G.orient(b, to=(5, 2, 0)).values, b.values + [5, 2, 0])


def test_orient_on_a_wall_turns_up_into_the_normal_and_keeps_the_shape():
    module = G.box(2, 1, 0.2)                            # a flat module, its up along z
    o = G.orient(module, to=(0, 0, 3), to_normal=(0, -1, 0))
    v = o.values
    assert np.allclose(np.ptp(v, axis=0), [2, 0.2, 1])  # now it stands on the south facade, thin along y
    assert np.allclose(_edges(v), _edges(module.values))


def test_orient_on_each_point_of_a_surface_follows_its_normals():
    g = Graph()
    g.node("Arc", "profile", mode="centre and angles", centre=(0, 0, 0), radius=5.0, from_=0.0, to=90.0,
           plane="elevation")
    g.node("Revolve", "dome", profile=g.nodes["profile"])
    g.node("Surface points", "points", surface=g.nodes["dome"], mode="centres", count_u=6, count_v=3)
    g.node("Surface points", "normals", surface=g.nodes["dome"], what="normals", mode="centres", count_u=6,
           count_v=3)
    g.node("Box", "module", width=0.6, depth=0.6, height=0.1)
    g.node("Orient", "modules", geometry=g.nodes["module"], to=g.nodes["points"], to_normal=g.nodes["normals"])
    m = g.value("modules")
    assert m.sizes == {"u": 6, "v": 3}                   # one module at each point
    v = m.values
    centres = v.mean(axis=-2)
    assert np.allclose(np.linalg.norm(centres, axis=-1), 5, atol=0.01)      # on the dome
    thin = v[..., 4, :] - v[..., 0, :]                   # the box's own up (base → top corner)
    normals = g.value("normals").values
    cosine = np.sum(thin * normals, axis=-1) / np.linalg.norm(thin, axis=-1)
    assert np.allclose(np.abs(cosine), 1, atol=1e-6)     # each one, along its normal


def test_orient_along_a_curve_follows_its_tangents():
    line = G.line((0, 0, 0), (0, 10, 0))                 # along y
    piece = G.box(2, 0.2, 0.2)                           # long along x
    o = G.orient(piece, to=(0, 5, 0), to_direction=(0, 1, 0))
    assert np.allclose(np.ptp(o.values, axis=0), [0.2, 2, 0.2])            # now long along the curve
    assert line is not None


# --- Package 3: Morph and Surface morph ---------------------------------------------------------------------------

SHEARED = np.array([[0, 0, 0], [2, 0, 0], [3, 1, 0], [1, 1, 0], [0, 0, 2], [2, 0, 2], [3, 1, 2], [1, 1, 2]], float)


def _dome(g, **inputs):
    g.node("Arc", "profile", mode="centre and angles", centre=(0, 0, 0), radius=5.0, from_=0.0, to=80.0,
           plane="elevation")
    g.node("Revolve", "dome", profile=g.nodes["profile"])
    g.node("Surface morph", "panels", surface=g.nodes["dome"], count_u=12, count_v=4, **inputs)
    return g.value("panels")


def test_morph_fills_the_cell_with_the_bounding_box_of_the_module():
    cell = G.Data(SHEARED, (), kind=G.BLOCK)
    assert np.allclose(G.morph(G.box(1, 1, 1), cell).values, SHEARED)
    assert np.allclose(G.morph(G.box(4, 4, 4), cell).values, SHEARED)       # the size of the module does not matter


def test_a_reference_box_keeps_the_module_in_proportion():
    cell = G.Data(SHEARED, (), kind=G.BLOCK)
    small = G.point(0, 0, 0)                                  # the centre of a reference box of 2 × 2 × 2
    m = G.morph(small, cell, reference=G.box(2, 2, 2)).values
    assert np.allclose(m, SHEARED.mean(axis=0))               # the centre of the cell


def test_morph_into_panels_raises_them_along_their_normal():
    g = Graph()
    g.node("Rectangle", "wall", width=6, height=3, plane="elevation")
    g.node("Grid", "panels", rectangle=g.nodes["wall"], columns=6, rows=3)
    g.node("Box", "module", width=1, depth=1, height=0.2)
    g.node("Morph", "m", geometry=g.nodes["module"], into=g.nodes["panels"], height=0.4)
    v = g.value("m")
    assert v.sizes == {"row": 3, "column": 6}
    assert np.allclose(np.ptp(v.values.reshape(-1, 3), axis=0), [6, 0.4, 3])


def test_a_flat_module_lies_on_the_bottom_of_each_cell():
    cell = G.Data(SHEARED, (), kind=G.BLOCK)
    flat = G.rectangle(1, 1)
    assert np.allclose(G.morph(flat, cell).values[..., 2], 0)


def test_each_piece_of_the_module_goes_into_each_cell():
    pieces = G.move(G.box(1, 1, 1), G.point(G.Data(np.array([0.0, 2.0]), ("piece",)), 0, 0))
    g = Graph()
    g.node("Rectangle", "wall", width=4, height=2)
    g.node("Grid", "panels", rectangle=g.nodes["wall"], columns=4, rows=2)
    m = G.morph(pieces, g.value("panels"))
    assert set(m.levels) == {"row", "column", "piece"}


def test_morph_needs_cells():
    with pytest.raises(ShapeError):
        G.morph(G.box(1, 1, 1), G.point(1, 2, 3))
    g = Graph()
    g.node("Rectangle", "r", width=2, height=2)
    g.node("Frame", "f", panel=g.nodes["r"])                  # eight corners too, but not a cell
    with pytest.raises(ShapeError):
        G.morph(G.box(1, 1, 1), g.value("f"))


def test_surface_cells_follow_the_surface_and_share_their_corners():
    c = _dome(Graph(), height=0.3)
    assert c.kind is G.BLOCK and c.sizes == {"u": 12, "v": 4}
    b = c.values
    assert np.allclose(np.linalg.norm(b[..., :4, :], axis=-1), 5, atol=0.01)      # the bottom on the dome
    assert np.allclose(np.linalg.norm(b[..., 4:, :], axis=-1), 5.3, atol=0.01)    # the top, 0.3 outside
    assert np.allclose(b[:-1, :, 1], b[1:, :, 0]) and np.allclose(b[:, :-1, 3], b[:, 1:, 0])
    inwards = _dome(Graph(), height=-0.3).values
    assert np.allclose(np.linalg.norm(inwards[..., 4:, :], axis=-1), 4.7, atol=0.01)


def test_surface_morph_puts_the_module_in_each_cell():
    g = Graph()
    g.node("Box", "module", width=1, depth=1, height=0.2)
    m = _dome(g, geometry=g.nodes["module"], height=0.3)
    assert m.kind is G.BOX and m.sizes == {"u": 12, "v": 4}
    r = np.linalg.norm(m.values, axis=-1)
    assert np.allclose(r[..., :4], 5, atol=0.01) and np.allclose(r[..., 4:], 5.3, atol=0.01)


# --- Package 4: vectors -------------------------------------------------------------------------------------------

def test_the_unit_vectors_of_the_axes_with_a_factor():
    assert np.allclose(G.vector('axis', axis='x').values, [1, 0, 0])
    assert np.allclose(G.vector('axis', axis='y', factor=2.5).values, [0, 2.5, 0])
    floors = G.Data(np.array([0.0, 3.0, 6.0]), ("floor",))
    v = G.vector('axis', factor=floors)                       # z by default
    assert v.levels == ("floor",) and np.allclose(v.values, [[0, 0, 0], [0, 0, 3], [0, 0, 6]])
    with pytest.raises(ShapeError):
        G.vector('axis', axis='w')


def test_multiplying_a_vector_by_a_number():
    assert np.allclose(G.vector('multiply', base=(1, 2, 0), factor=3).values, [3, 6, 0])
    reversed_ = G.vector('multiply', base=(1, 2, 0), factor=-0.5).values
    assert np.allclose(reversed_, [-0.5, -1, 0]) and not np.signbit(reversed_[2])     # a plain 0, not -0
    factors = G.Data(np.array([1.0, 2.0]), ("step",))
    assert np.allclose(G.vector('multiply', base=(0, 1, 0), factor=factors).values, [[0, 1, 0], [0, 2, 0]])


def test_adding_two_vectors():
    assert np.allclose(G.vector('add', base=(1, 0, 0), other=(0, 0, 3)).values, [1, 0, 3])
    g = Graph()
    g.node("Vector", "v", mode="add", base=(1.0, 0.0, 0.0))     # the node gives the vertical as the other one
    assert np.allclose(g.value("v").values, [1, 0, 1])


def test_point_to_point_unit_and_amplitude_together():
    v = G.vector('point to point', from_=(1, 1, 0), to=(4, 5, 0))
    u = G.vector('unit', base=v)
    assert np.allclose(u.values, [0.6, 0.8, 0])
    assert np.allclose(G.vector('to a length', base=v, length=10).values, [6, 8, 0])
    assert np.allclose(G.vector('multiply', base=u, factor=5).values, v.values)


