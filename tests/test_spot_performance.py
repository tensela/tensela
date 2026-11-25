"""Group 3.5 of the pending plan: spot performance. Delaunay (a cloud, and many small groups at once), nesting equal
pieces, and Bar analysis past the old limit of 800 joints (the system solved in its band)."""
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from tensela import frames, mesh_tools, nesting
from tensela.data import Data, ShapeError
from tensela.geometry import POINT, line
from tensela.meshes import surface_by_points
from tensela.sections import MATERIALS, section
from tensela.simulation import network

SRC = Path(__file__).parent.parent / "src"


def triangles(mesh):
    return {tuple(sorted(f)) for f in mesh.kind.faces}


def hull_size(xy):
    points = sorted(map(tuple, xy))

    def half(ps):
        h = []
        for p in ps:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h
    return len(half(points)) + len(half(points[::-1])) - 2


# --- Delaunay -----------------------------------------------------------------------------------------------------

def test_many_small_groups_come_out_whole_and_fast(monkeypatch):
    rng = np.random.default_rng(2)
    corners = rng.random((2000, 5, 3))
    points = Data(corners, ("panel", "point"), "p", kind=POINT)
    start = time.perf_counter()
    mesh = mesh_tools.delaunay(points)
    assert time.perf_counter() - start < 1.0                      # one call to VTK each took about 1.5 s
    # each group covers its whole outline (VTK lost a thin triangle on the outline in some): 2n − h − 2 triangles
    faces = np.array(mesh.kind.faces)
    for g in range(0, 2000, 37):
        own = faces[(faces >= 5 * g).all(axis=1) & (faces < 5 * g + 5).all(axis=1)]
        _, _, vt = np.linalg.svd(corners[g] - corners[g].mean(0))
        assert len(own) == 2 * 5 - hull_size((corners[g] - corners[g].mean(0)) @ vt[:2].T) - 2
    # the same triangles as one call each, plus those it lost
    monkeypatch.setattr(mesh_tools, "SMALL_GROUP", 0)
    one_by_one = mesh_tools.delaunay(points)
    assert triangles(one_by_one) <= triangles(mesh)
    assert len(triangles(mesh) - triangles(one_by_one)) < 0.05 * len(mesh.kind.faces)


@pytest.mark.parametrize("more", [0.3, -0.3])
def test_pyramids_on_panels_look_the_same_way_as_before(monkeypatch, more):
    rng = np.random.default_rng(5)
    square = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    panels = square[None] + rng.random((300, 1, 3)) * 5
    centres = Data(panels.mean(axis=1) + [0, 0, more], ("panel",), "c", kind=POINT)
    points = Data(panels, ("panel", "point"), "p", kind=POINT)
    at_once = mesh_tools.delaunay(points, centres)
    monkeypatch.setattr(mesh_tools, "SMALL_GROUP", 0)
    one_by_one = mesh_tools.delaunay(points, centres)

    def turned(mesh):                                              # each face, from its smallest corner on
        return {tuple(f[f.index(min(f)):] + f[:f.index(min(f))]) for f in mesh.kind.faces}
    assert turned(at_once) == turned(one_by_one)


def test_four_points_on_a_circle_go_the_usual_way(monkeypatch):
    square = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    points = Data(np.broadcast_to(square, (10, 4, 3)).copy(), ("panel", "point"), "p", kind=POINT)
    mesh = mesh_tools.delaunay(points)
    assert len(mesh.kind.faces) == 20                              # two triangles each, not four on top of each other
    monkeypatch.setattr(mesh_tools, "SMALL_GROUP", 0)
    assert triangles(mesh_tools.delaunay(points)) == triangles(mesh)


def test_a_big_cloud_is_quick_and_keeps_its_points():
    rng = np.random.default_rng(1)
    cloud = np.column_stack([rng.random((40_000, 2)) * 100, rng.random(40_000)])
    start = time.perf_counter()
    mesh = mesh_tools.delaunay(Data(cloud, ("point",), "p", kind=POINT), plane="plan")   # 20 000 ran out of memory
    assert time.perf_counter() - start < 3.0                      # in the order they came, about 10 s
    assert np.allclose(mesh.values, cloud)
    assert len(mesh.kind.faces) > 2 * 40_000 - 2 * 400            # (minus those of the outline, a few hundred)
    terrain = surface_by_points(Data(cloud, ("point",), "p", kind=POINT), mode="cloud")
    assert np.allclose(terrain.values, cloud)                     # the vertices, in the order of the survey
    assert triangles(terrain) == triangles(mesh)


def test_the_engine_does_not_load_the_whole_of_vtk():
    script = ("import sys; import numpy as np\n"
              "from tensela.data import Data\nfrom tensela.geometry import POINT\n"
              "from tensela.mesh_tools import delaunay\n"
              "delaunay(Data(np.random.default_rng(0).random((150, 3)), ('point',), 'p', kind=POINT))\n"
              "print('vtk' in sys.modules, 'vtkmodules.vtkRenderingCore' in sys.modules)\n")
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                         env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"})
    assert out.stdout.split() == ["False", "False"], out.stderr[-2000:]


# --- Nesting ------------------------------------------------------------------------------------------------------

def test_equal_pieces_nest_in_the_same_places_without_trying_the_full_sheets(monkeypatch):
    rng = np.random.default_rng(3)
    items = []
    for k in range(60):
        size = (0.30, 0.22, 0.15)[k % 3]                           # three kinds of triangle, many of each
        tri = np.array([[0, 0], [size, 0], [size * 0.4, size * 0.8]])
        items.append(["piece", k, [tri], size, size * 0.8])
    rng.shuffle(items)
    tries = []
    real = np.fft.irfft2
    monkeypatch.setattr(nesting.np.fft, "irfft2", lambda *a, **k: tries.append(1) or real(*a, **k))
    sheets, placed = nesting.nest(items, (1.2, 0.6), 0.01, True, cells=240)
    remembered = len(tries)

    class Forgets(set):
        def add(self, key):
            pass
    plain = nesting._Sheet.__init__

    def forgetting(self, *a):
        plain(self, *a)
        self.failed = Forgets()
    monkeypatch.setattr(nesting._Sheet, "__init__", forgetting)
    tries.clear()
    sheets_again, placed_again = nesting.nest(items, (1.2, 0.6), 0.01, True, cells=240)
    assert (sheets, [p[3:] for p in placed]) == (sheets_again, [p[3:] for p in placed_again])
    assert sheets > 2 and remembered < 0.6 * len(tries)


# --- Bar analysis -------------------------------------------------------------------------------------------------

def band_matrix(size, band, seed):
    rng = np.random.default_rng(seed)
    a = np.zeros((size, size))
    for d in range(band + 1):
        v = rng.normal(size=size - d)
        a[np.arange(size - d), np.arange(d, size)] = v
        a[np.arange(d, size), np.arange(size - d)] = v
    a += np.eye(size) * (2 * band + 2) * 3                         # positive
    return a


@pytest.mark.parametrize("size,band", [(1, 0), (7, 0), (50, 3), (300, 10), (700, 120), (1000, 300)])
def test_the_band_solves_like_the_whole_matrix(size, band):
    a = band_matrix(size, band, size + band)
    rows, cols = np.nonzero(a)
    rhs = np.random.default_rng(1).normal(size=size)
    blocks = frames._band_factor(size, rows, cols, a[rows, cols], 0.5)
    assert np.allclose(frames._band_solve(blocks, rhs), np.linalg.solve(a + 0.5 * np.eye(size), rhs), atol=1e-10)


def test_the_joints_are_ordered_along_the_band():
    rng = np.random.default_rng(0)
    shuffled = rng.permutation(500)
    chain = np.column_stack([shuffled[:-1], shuffled[1:]])         # a chain of joints numbered at random
    order = frames._band_order(500, chain)
    assert sorted(order) == list(range(500))
    rank = np.empty(500, int)
    rank[order] = np.arange(500)
    assert np.abs(rank[chain[:, 0]] - rank[chain[:, 1]]).max() == 1
    two_parts = np.vstack([chain[:200], chain[300:]])              # in two pieces: both are walked
    assert sorted(frames._band_order(500, two_parts)) == list(range(500))


def lattice(nx, ny, nz):
    index = np.arange(nx * ny * nz).reshape(nx, ny, nz)
    joints = np.stack(np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij"), -1)
    bars = [np.stack([np.moveaxis(index, k, 0)[:-1].ravel(), np.moveaxis(index, k, 0)[1:].ravel()], 1)
            for k in range(3)]
    return joints.reshape(-1, 3).astype(float), np.vstack(bars)


def test_a_structure_past_the_old_limit_is_solved_and_balanced():
    joints, bars = lattice(40, 6, 5)                                # 1200 joints: the old limit was 800
    held = np.flatnonzero((joints[:, 0] == 0) | (joints[:, 0] == 39))
    forces = np.zeros_like(joints)
    forces[:, 2] = -1000.0
    per_metre = np.tile([0.0, 0.0, -300.0], (len(bars), 1))
    start = time.perf_counter()
    r = frames.solve(joints, bars, held, ["clamped"] * len(held), forces, per_metre, MATERIALS["steel S275"],
                     section("IPE 300"))
    assert time.perf_counter() - start < 5.0
    total = 1000.0 * len(joints) + 300.0 * len(bars)                # every bar is 1 m long
    assert r["reactions"][held, 2].sum() == pytest.approx(total, rel=1e-6)    # (the soft spring keeps a trace)
    assert np.allclose(r["reactions"][np.setdiff1d(np.arange(len(joints)), held)], 0, atol=1e-6 * total)
    assert r["moves"][:, 2].min() < 0


def test_a_lattice_too_interwoven_is_held_back(monkeypatch):
    monkeypatch.setattr(frames, "MAXIMUM_BAND", 100_000)
    joints, bars = lattice(10, 10, 10)
    held = np.flatnonzero(joints[:, 2] == 0)
    with pytest.raises(ShapeError, match="interwoven|entrelazados"):
        frames.solve(joints, bars, held, ["pinned"] * len(held), np.zeros_like(joints),
                     np.zeros((len(bars), 3)), MATERIALS["steel S275"], section("IPE 300"))


def test_the_limit_counts_the_joints_once_welded():
    # a row of 3000 lines end to end: 6000 ends, 3001 joints once welded
    xs = np.arange(3001.0)
    lines = Data(np.stack([np.column_stack([xs[:-1], 0 * xs[:-1], 0 * xs[:-1]]),
                           np.column_stack([xs[1:], 0 * xs[1:], 0 * xs[1:]])], axis=1), ("bar",), "l",
                 kind=line((0, 0, 0), (1, 0, 0)).kind)
    assert len(network(lines, 0, most=3001)["particles"]) == 3001
    with pytest.raises(ShapeError, match="3001"):
        network(lines, 0, most=3000)
