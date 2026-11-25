"""Topology optimization: where the material should be, inside a region, to carry some loads to some supports.

It starts from the region full of material spread thin (as much as the target density asks), and, turn after turn,
moves the material to where it works and takes it from where it does not, until a structure is left: the arches,
ties and diagonals of an MBB beam, the fan of a Michell truss, the legs of a bridge. It is the method of densities
(SIMP) of the engineers, with a filter so the bars are not thinner than a couple of cells, and the optimality
criteria to move the material: the same family of shapes as the evolutionary methods (ESO, BESO), without having
to tune a rejection ratio.

In 2D the region is a closed curve or a rectangle, in any plane; the material is a plate of some thickness, square
cells of plane stress. In 3D the region is a body (a box, a closed mesh); the material, cubes. The stiffness is
solved slice by slice of the grid along its longer side (block tridiagonal), so no other library is needed.
"""
from __future__ import annotations

import math
from itertools import product

import numpy as np

from .data import Data, ShapeError, integer
from .geometry import BOX, CLOSED_CURVE, POINT, RECTANGLE, VECTOR, gravity_direction
from .language import comma, tr
from .sections import MATERIALS
from .simulation import _items, _loads_at

#: What the node gives.
SHOW = ('shape', 'plate', 'cells', 'grid', 'density', 'stress', 'largest displacement')

#: How many cells along the longer side, at most (more would take too long).
MAXIMUM_RESOLUTION = 240

#: In 3D, at most so many cubes, and so many moves in a slice across the longer side.
MAXIMUM_CUBES = 60000
MAXIMUM_SLICE = 800

#: The stiffness of an empty cell, as a share of the full one (not zero: the system must stay solvable).
EMPTY = 1e-9

PENALTY = 3.0
POISSON = 0.3
GRAVITY = 9.81

#: The corners of a cell, in the order of its stiffness: counterclockwise below, then above.
CORNERS = {2: ((0, 0), (1, 0), (1, 1), (0, 1)),
           3: ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))}


def _elasticity(dim: int, nu: float = POISSON) -> np.ndarray:
    """The elasticity of the material for E = 1: plane stress (3 × 3) or solid (6 × 6)."""
    if dim == 2:
        return np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]]) / (1 - nu * nu)
    lam, mu = nu / ((1 + nu) * (1 - 2 * nu)), 1 / (2 * (1 + nu))
    d = np.zeros((6, 6))
    d[:3, :3] = lam
    d[[0, 1, 2], [0, 1, 2]] += 2 * mu
    d[[3, 4, 5], [3, 4, 5]] = mu
    return d


def _strains(dim: int, at) -> np.ndarray:
    """The strains of a cell of side 1 at a point of it (from −1 to 1 on each axis) from its moves: (3 or 6, …)."""
    corners = np.array(CORNERS[dim], float) * 2 - 1
    at = np.asarray(at, float)
    shape = np.prod(1 + corners * at, axis=1) / 2 ** dim
    gradients = np.stack([corners[:, a] * np.prod(np.delete(1 + corners * at, a, axis=1), axis=1) / 2 ** dim
                          for a in range(dim)], 1) * 2          # d/dx = 2 d/dξ for a side of 1
    del shape
    n = len(corners)
    if dim == 2:
        b = np.zeros((3, 2 * n))
        b[0, 0::2], b[1, 1::2] = gradients[:, 0], gradients[:, 1]
        b[2, 0::2], b[2, 1::2] = gradients[:, 1], gradients[:, 0]
        return b
    b = np.zeros((6, 3 * n))
    gx, gy, gz = gradients[:, 0], gradients[:, 1], gradients[:, 2]
    b[0, 0::3], b[1, 1::3], b[2, 2::3] = gx, gy, gz
    b[3, 0::3], b[3, 1::3] = gy, gx
    b[4, 1::3], b[4, 2::3] = gz, gy
    b[5, 0::3], b[5, 2::3] = gz, gx
    return b


def _cell_stiffness(nu: float = POISSON, dim: int = 2) -> np.ndarray:
    """The stiffness of a square cell of plane stress (E = 1, thickness 1), or of a cube (E = 1, side 1): (8, 8) or
    (24, 24). In 2D the same for any size of square; a cube of side h is h times it."""
    d = _elasticity(dim, nu)
    g = 1 / math.sqrt(3)
    k = 0.0
    for at in product((-g, g), repeat=dim):
        b = _strains(dim, at)
        k = k + b.T @ d @ b / 2 ** dim                          # the Jacobian of a side of 1: (1/2)^dim
    return k


def _strain_at_centre(dim: int = 2) -> np.ndarray:
    return _strains(dim, np.zeros(dim))


def _von_mises(s: np.ndarray) -> np.ndarray:
    if s.shape[1] == 3:
        return np.sqrt(s[:, 0] ** 2 - s[:, 0] * s[:, 1] + s[:, 1] ** 2 + 3 * s[:, 2] ** 2)
    a, b, c = s[:, 0], s[:, 1], s[:, 2]
    return np.sqrt(0.5 * ((a - b) ** 2 + (b - c) ** 2 + (c - a) ** 2) + 3 * (s[:, 3:] ** 2).sum(1))


class _Grid:
    """The cells of a grid (2D: squares; 3D: cubes), and the solution of their stiffness slice by slice along the
    first axis (the longer one)."""

    def __init__(self, *shape: int):
        self.shape = tuple(int(s) for s in shape)
        dim = self.dim = len(shape)
        self.section = tuple(s + 1 for s in self.shape[1:])     # the corners of a slice
        self.m = dim * int(np.prod(self.section))
        cells = np.indices(self.shape).reshape(dim, -1).T       # each cell, slice by slice
        self.cells = cells
        self.i = cells[:, 0]
        self.j = cells[:, 1]
        columns, rows = [], []
        for corner in CORNERS[dim]:
            node = np.ravel_multi_index(tuple(cells[:, a] + corner[a] for a in range(1, dim)), self.section)
            for c in range(dim):
                columns.append(cells[:, 0] + corner[0])
                rows.append(dim * node + c)
        self.columns, self.rows = np.stack(columns, 1), np.stack(rows, 1)
        offsets = np.repeat([c[0] for c in CORNERS[dim]], dim)
        n = len(offsets)
        a, b = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
        oa, ob = offsets[a], offsets[b]
        same, above = oa == ob, (oa == 0) & (ob == 1)
        self.same_ab, self.above_ab = (a[same], b[same]), (a[above], b[above])
        m, nx = self.m, self.shape[0]
        self.index_same = ((self.i[:, None] + oa[same][None, :]) * m + self.rows[:, a[same]]) * m \
            + self.rows[:, b[same]]
        self.index_above = (self.i[:, None] * m + self.rows[:, a[above]]) * m + self.rows[:, b[above]]
        self.size_same, self.size_above = (nx + 1) * m * m, nx * m * m

    @property
    def nx(self) -> int:
        return self.shape[0]

    def solve(self, stiffness: np.ndarray, force: np.ndarray, held: np.ndarray) -> np.ndarray:
        """The moves of every corner (nx + 1, m) under `force`, with the cells' stiffness (cells, k, k) and the
        `held` moves (nx + 1, m) kept at zero."""
        nx, m = self.nx, self.m
        diagonal = np.bincount(self.index_same.ravel(), stiffness[:, self.same_ab[0], self.same_ab[1]].ravel(),
                               self.size_same).reshape(nx + 1, m, m)
        upper = np.bincount(self.index_above.ravel(), stiffness[:, self.above_ab[0], self.above_ab[1]].ravel(),
                            self.size_above).reshape(nx, m, m)
        f = np.where(held, 0.0, force)
        for c in range(nx + 1):                                 # the held moves: a row and a column of the identity
            h = held[c]
            if h.any():
                diagonal[c][h, :] = 0.0
                diagonal[c][:, h] = 0.0
                diagonal[c][h, h] = 1.0
                if c < nx:
                    upper[c][h, :] = 0.0
                if c > 0:
                    upper[c - 1][:, h] = 0.0
        # Block tridiagonal elimination: S_c = D_c − U_{c−1}ᵀ S_{c−1}⁻¹ U_{c−1}, then back.
        w, g = [None] * (nx + 1), [None] * (nx + 1)
        for c in range(nx + 1):
            s = diagonal[c]
            rhs = f[c].copy()
            if c > 0:
                s = s - upper[c - 1].T @ w[c - 1]
                rhs -= upper[c - 1].T @ g[c - 1]
            if c < nx:
                both = np.linalg.solve(s, np.column_stack([upper[c], rhs]))
                w[c], g[c] = both[:, :-1], both[:, -1]
            else:
                g[c] = np.linalg.solve(s, rhs)
        u = np.zeros((nx + 1, m))
        u[nx] = g[nx]
        for c in range(nx - 1, -1, -1):
            u[c] = g[c] - w[c] @ u[c + 1]
        return u

    def cell_moves(self, u: np.ndarray) -> np.ndarray:
        """The moves of each cell: (cells, k)."""
        return u[self.columns, self.rows]

    def shared(self, per_cell: np.ndarray, direction: np.ndarray) -> np.ndarray:
        """A force per cell along `direction`, shared by its corners: (nx + 1, m)."""
        f = np.zeros((self.nx + 1, self.m))
        corners = len(CORNERS[self.dim])
        for k in range(corners):
            for c in range(self.dim):
                np.add.at(f, (self.columns[:, k * self.dim + c], self.rows[:, k * self.dim + c]),
                          per_cell * direction[c] / corners)
        return f


def _smooth_filter(active: np.ndarray, radius: float):
    """The density filter: each cell takes the weighted mean of the active cells within `radius` (in cells). Gives
    the filter and its transpose (for the sensitivities). Any number of dimensions."""
    r = int(math.floor(radius))
    dim = active.ndim
    offsets = [(o, radius - math.sqrt(sum(x * x for x in o))) for o in product(range(-r, r + 1), repeat=dim)
               if radius - math.sqrt(sum(x * x for x in o)) > 0]

    def convolve(x: np.ndarray) -> np.ndarray:
        padded = np.pad(x, r)
        out = np.zeros_like(x, dtype=float)
        for o, weight in offsets:
            out += weight * padded[tuple(slice(r + a, r + a + n) for a, n in zip(o, x.shape))]
        return out

    weights = np.maximum(convolve(active.astype(float)), 1e-12)

    def forward(x: np.ndarray) -> np.ndarray:
        return convolve(x * active) / weights

    def back(d: np.ndarray) -> np.ndarray:
        return convolve(d / weights) * active
    return forward, back


def _stiffness_curve(x: np.ndarray, gentle: bool):
    """How stiff a cell is for its density (SIMP, x³), and its slope. `gentle` (with self weight): straight below
    0.1, so light cells are not heavier than they are stiff (they would never empty)."""
    e = x ** PENALTY
    de = PENALTY * x ** (PENALTY - 1)
    if gentle:
        low = x < 0.1
        slope = 0.1 ** (PENALTY - 1)
        e = np.where(low, slope * x, e)
        de = np.where(low, slope, de)
    return EMPTY + (1 - EMPTY) * e, (1 - EMPTY) * de


def _iterate(grid: _Grid, ke: np.ndarray, setup: dict, target: float, turns: int, smoothing: float) -> dict:
    """The turns: solve, measure where the material works, move it (optimality criteria), until it settles."""
    shape = grid.shape
    active, full, free = setup["active"], setup["full"], setup["free"]
    force, held, weight, down = setup["force"], setup["held"], setup["weight"], setup["down"]
    forward, back = _smooth_filter(active.reshape(shape), smoothing)
    x = np.where(full, 1.0, np.where(free, target, 0.0))
    gentle = weight > 0
    corners = len(CORNERS[grid.dim])
    cell_down = np.tile(down, corners) / corners

    def physical(x_):
        xp_ = forward(x_.reshape(shape)).ravel()
        return np.where(full, 1.0, np.where(free, xp_, 0.0))

    def loads(xp_):
        return force + grid.shared(weight * xp_, down) if weight else force

    xp, history = physical(x), []
    wanted = target * free.sum()
    dv = np.where(free, back(np.ones(shape)).ravel(), 1.0)
    for turn in range(turns):
        e, de = _stiffness_curve(xp, gentle)
        u = grid.solve(ke[None] * e[:, None, None], loads(xp), held)
        ue = grid.cell_moves(u)
        energy = np.einsum("ci,ij,cj->c", ue, ke, ue)
        sensitivity = -de * energy
        if weight:
            sensitivity = sensitivity + 2 * weight * (ue @ cell_down)
        sensitivity = np.minimum(sensitivity, -1e-12 * max(float(np.abs(sensitivity).max()), 1e-300))
        dc = np.where(free, back(sensitivity.reshape(shape)).ravel(), 0.0)
        if len(history) < 79:
            history.append(xp.copy())
        lo, hi, move, new = 0.0, 1e9, 0.2, x
        for _ in range(80):                                     # the bisection on the volume
            mid = 0.5 * (lo + hi)
            step = x * np.sqrt(np.maximum(-dc, 0.0) / (dv * max(mid, 1e-300)))
            new = np.where(free, np.clip(step, np.maximum(x - move, 0.0), np.minimum(x + move, 1.0)), x)
            if physical(new)[free].sum() > wanted:
                lo = mid
            else:
                hi = mid
            if (hi - lo) <= 1e-4 * (hi + lo):
                break
        change = float(np.abs(new - x).max())
        x = new
        xp = physical(x)
        if turn >= 10 and change < 0.01:                       # (the usual criterion of the engineers)
            break
    e, _ = _stiffness_curve(xp, gentle)
    u = grid.solve(ke[None] * e[:, None, None], loads(xp), held)
    history.append(xp.copy())
    return {"density": xp, "u": u, "e": e, "history": history}


# --- The regions -------------------------------------------------------------------------------------------------

def _rings(data, role: str) -> list[np.ndarray]:
    """The closed outlines of an input (closed curves, rectangles, polygons, faces of a mesh): each one (n, 3)."""
    if data is None:
        return []
    kind = getattr(data, "kind", None)
    if not isinstance(data, Data) or kind is None or not (kind.closed or kind.faces is not None):
        raise ShapeError(tr('“{role}” should be closed outlines: a rectangle, a circle, a closed curve or a '
                            'polygon.').format(role=tr(role)))
    out = []
    for _, p in _items(data, CLOSED_CURVE):
        p = np.asarray(p, float)
        if kind.faces is not None:
            out.extend(p[list(face)] for face in kind.faces)
        else:
            out.append(p)
    return out


def _bodies(data, role: str) -> list:
    """The bodies of an input (boxes, closed meshes), as VTK surfaces."""
    import pyvista as pv
    if data is None:
        return []
    kind = getattr(data, "kind", None)
    if not isinstance(data, Data) or kind is None or kind.faces is None:
        raise ShapeError(tr('“{role}” should be bodies: a box or a closed mesh.').format(role=tr(role)))
    out = []
    for _, p in _items(data, CLOSED_CURVE):
        faces = np.concatenate([[len(f), *f] for f in kind.faces])
        out.append(pv.PolyData(np.asarray(p, float), faces).triangulate())
    return out


def _has_volume(body) -> bool:
    """Whether a body (triangulated) encloses some volume. A flat one (a box of height 0) holds no cell, and VTK's
    test of the points inside it broke its memory: the program closed a while later, in another computation."""
    p = np.asarray(body.points, float)
    if body.n_cells == 0 or len(p) < 4 or not np.all(np.isfinite(p)):
        return False
    faces = np.asarray(body.faces).reshape(-1, 4)[:, 1:]
    a, b, c = p[faces[:, 0]], p[faces[:, 1]], p[faces[:, 2]]
    volume = abs(float(np.einsum("ij,ij->", a, np.cross(b, c)))) / 6
    size = float(np.ptp(p, axis=0).max())
    return size > 0 and volume > 1e-9 * size ** 3


def _in_bodies(points: np.ndarray, bodies: list) -> np.ndarray:
    import pyvista as pv
    inside = np.zeros(len(points), dtype=bool)
    cloud = pv.PolyData(np.asarray(points, float))
    for body in bodies:
        if not _has_volume(body):
            continue
        if hasattr(cloud, "select_interior_points"):
            chosen = cloud.select_interior_points(body, check_surface=False)
            inside |= np.asarray(chosen.point_data["selected_points"]).astype(bool)
        else:                                                   # (older VTK helpers)
            chosen = cloud.select_enclosed_points(body, check_surface=False, tolerance=1e-9)
            inside |= np.asarray(chosen.point_data["SelectedPoints"]).astype(bool)
    return inside


def _is_body(region) -> bool:
    """Whether the region is a body (3D) and not a flat outline (2D)."""
    kind = getattr(region, "kind", None)
    if not isinstance(region, Data) or kind is None or kind.faces is None or kind is RECTANGLE:
        return False
    p = np.asarray(region.values, float).reshape(-1, 3)
    if len(p) < 4:
        return False
    s = np.linalg.svd(p - p.mean(0), compute_uv=False)
    return bool(s[2] > 1e-6 * s[0])


def _plane(points: np.ndarray, down: np.ndarray):
    """The plane of the region: its centre and two axes in it. The second axis goes up, against the weight, when the
    weight lies in the plane; in a plate lying flat, the axes follow the global x and y."""
    centre = points.mean(0)
    _, s, vt = np.linalg.svd(points - centre, full_matrices=False)
    if s[1] < 1e-9 * max(s[0], 1e-300):
        raise ShapeError(tr('The region must be flat and have some area (a rectangle, a closed curve).'))
    normal = vt[2]
    in_plane = down - (down @ normal) * normal
    if np.linalg.norm(in_plane) > 0.05:
        ey = -in_plane / np.linalg.norm(in_plane)
        ex = np.cross(ey, normal)
    else:
        reference = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        ex = reference - (reference @ normal) * normal
        ex /= np.linalg.norm(ex)
        ey = np.cross(normal, ex)
    return centre, ex / np.linalg.norm(ex), ey / np.linalg.norm(ey)


def _near_the_plane(points: np.ndarray, centre: np.ndarray, normal: np.ndarray, size: np.ndarray, role: str) -> None:
    """A point well off the plane of the region would be pressed flat onto it without a word, and act on another
    place: almost always the region was drawn in another plane (a Rectangle in plan instead of elevation)."""
    off = np.abs((points - centre) @ normal)
    if len(off) and off.max() > 0.05 * float(max(size)):
        raise ShapeError(tr('A point of “{role}” is {distance} m off the plane of the region. They must be in the '
                            'same plane: look at the «plane» of the region (plan, elevation or side '
                            'elevation).').format(role=tr(role),
                                                  distance=comma(f"{off.max():.2f}".rstrip("0").rstrip("."))))


def _inside(p: np.ndarray, ring: np.ndarray) -> np.ndarray:
    from .geometry import _inside as inside_2d
    return inside_2d(p, ring)


def _held_and_loaded(groups_fixed, groups_rollers, load_groups, vectors, along: int, dim: int, nx: int, m: int,
                     node_index):
    """The held moves and the forces on the corners, from the groups of corners (each, its grid indices)."""
    held = np.zeros((nx + 1, m), dtype=bool)
    if not groups_fixed and not groups_rollers:
        raise ShapeError(tr('Nothing holds it: connect its supports (points or outlines).'))
    # Rollers only hold along the weight: alone, the whole region slides sideways. One support point alone, without
    # a roller, lets it turn about it. Either way the result would mean nothing: said instead.
    if not groups_fixed:
        raise ShapeError(tr('Only rollers hold it, and a roller slides sideways: connect at least one support (it '
                            'holds in every direction).'))
    fixed_nodes = {int(k) for g_ in groups_fixed for k in np.atleast_1d(g_)}
    roller_nodes = {int(k) for g_ in groups_rollers for k in np.atleast_1d(g_)} - fixed_nodes
    if len(fixed_nodes) == 1 and not roller_nodes:
        raise ShapeError(tr('It rests on a single point and would turn about it: add another support or a roller.'))
    for g_ in groups_fixed:
        column, node = node_index(g_)
        for c in range(dim):
            held[column, dim * node + c] = True
    for g_ in groups_rollers:
        column, node = node_index(g_)
        held[column, dim * node + along] = True
    force = np.zeros((nx + 1, m))
    for g_, v in zip(load_groups, vectors):
        column, node = node_index(g_)
        for c in range(dim):
            np.add.at(force, (column, dim * node + c), v[c] / len(g_))
    return held, force


def _check(material, density, resolution, turns, thickness, gravity, smoothing):
    if material not in MATERIALS:
        raise ShapeError(tr('The material must be one of: {options}.').format(
            options=", ".join(tr(o) for o in MATERIALS)))
    target = float(density)
    if not 0.02 <= target <= 0.98:
        raise ShapeError(tr('The density must be between 0.02 and 0.98 (the share of the region that stays full).'))
    res, turns = integer(resolution), integer(turns)
    if not 4 <= res <= MAXIMUM_RESOLUTION:
        raise ShapeError(tr('The resolution must be between 4 and {maximum} cells.').format(maximum=MAXIMUM_RESOLUTION))
    if turns < 1:
        raise ShapeError(tr('It needs at least one turn.'))
    if float(thickness) <= 0:
        raise ShapeError(tr('The thickness must be more than 0.'))
    if not 0 < float(smoothing) <= res / 2:            # in cells: beyond half the grid it only blurs (and takes long)
        raise ShapeError(tr('The smoothing must be more than 0 and at most half the resolution ({maximum} cells).')
                         .format(maximum=comma(f"{res / 2:g}")))
    return MATERIALS[material], target, res, turns, float(thickness), gravity_direction(gravity)


def _load_vectors(loads, load, groups, down):
    if not groups:
        return []
    if isinstance(loads, Data) and loads.kind in (POINT, VECTOR):
        where = np.array([p for _, p in _items(loads, POINT)], float).reshape(-1, 3)
    else:
        where = np.zeros((len(groups), 3))
    return _loads_at(where, load, down)


# --- 2D --------------------------------------------------------------------------------------------------------------

def optimize_2d(region, voids=None, solid=None, supports=None, rollers=None, loads=None, load=1000.0,
                self_weight: bool = False, material: str = 'concrete C25/30', thickness=0.3, density=0.4,
                resolution=60, turns=60, smoothing=1.5, gravity=(0.0, 0.0, -1.0)) -> dict:
    """The optimization of a plate; gives the grid, the densities and what is needed to show them."""
    mat, target, res, turns, t, down = _check(material, density, resolution, turns, thickness, gravity, smoothing)
    outlines = _rings(region, 'region')
    if not outlines:
        raise ShapeError(tr('Connect the region: the outline where the material can go.'))
    centre, ex, ey = _plane(np.vstack(outlines), down)

    def flat(p):
        q = np.asarray(p, float) - centre
        return np.stack([q @ ex, q @ ey], -1)

    rings = [flat(r) for r in outlines]
    allp = np.vstack(rings)
    low, high = allp.min(0), allp.max(0)
    size = high - low
    swap = size[1] > size[0]                                    # the grid runs along its longer side
    if swap:
        rings = [r[:, ::-1] for r in rings]
        low, high, size = low[::-1], high[::-1], size[::-1]
    h = size[0] / res
    nx, ny = max(1, int(math.ceil(size[0] / h - 1e-9))), max(1, int(math.ceil(size[1] / h - 1e-9)))

    def to_grid(q2):                                           # flat coordinates as grid coordinates
        return q2[..., ::-1] if swap else q2

    centres = np.stack(np.meshgrid(low[0] + (np.arange(nx) + 0.5) * h, low[1] + (np.arange(ny) + 0.5) * h,
                                   indexing="ij"), -1).reshape(-1, 2)
    corners = np.stack(np.meshgrid(low[0] + np.arange(nx + 1) * h, low[1] + np.arange(ny + 1) * h,
                                   indexing="ij"), -1).reshape(-1, 2)

    def mask(rs):
        m = np.zeros(len(centres), dtype=bool)
        for r in rs:
            m |= _inside(centres, r)
        return m

    design = mask(rings)
    empty = mask([to_grid(flat(r)) for r in _rings(voids, 'voids')])
    full = mask([to_grid(flat(r)) for r in _rings(solid, 'solid parts')]) & ~empty
    active = (design | full) & ~empty
    free = active & ~full
    if not free.any():
        raise ShapeError(tr('There is nothing to optimize: the region has no cells left (too small for the '
                            'resolution, or covered by the voids and the solid parts).'))
    down_flat = to_grid(np.array([down @ ex, down @ ey]))
    if np.linalg.norm(down_flat) < 0.05:                        # a plate lying flat: the drawing's down
        down_flat = to_grid(np.array([0.0, -1.0]))
    down_flat = down_flat / np.linalg.norm(down_flat)

    def groups_of(data, role):
        """The corners an input holds or loads: the nearest to each point, or all those inside each outline."""
        if data is None:
            return []
        if isinstance(data, Data) and data.kind in (POINT, VECTOR):
            p3 = np.array([p for _, p in _items(data, POINT)], float).reshape(-1, 3)
            _near_the_plane(p3, centre, np.cross(ex, ey), size, role)
            q = to_grid(flat(p3))
            return [np.atleast_1d(np.argmin(((corners - p) ** 2).sum(-1))) for p in q]
        out = []
        for r in _rings(data, role):
            r2 = to_grid(flat(r))
            inside = np.nonzero(_inside(corners, r2))[0]
            out.append(inside if len(inside) else np.atleast_1d(np.argmin(((corners - r2.mean(0)) ** 2).sum(-1))))
        return out

    load_groups = groups_of(loads, 'loads')
    vectors = []
    for v in _load_vectors(loads, load, load_groups, down):
        fv = to_grid(np.array([v @ ex, v @ ey]))
        if np.linalg.norm(fv) < 1e-12 and np.linalg.norm(v) > 0:
            fv = np.linalg.norm(v) * down_flat                  # across a flat plate: the drawing's down
        vectors.append(fv)
    if not load_groups and not self_weight:
        raise ShapeError(tr('There is nothing to carry: connect some loads, or turn on the self weight.'))
    grid = _Grid(nx, ny)
    along = 1 if abs(down_flat[1]) >= abs(down_flat[0]) else 0
    held, force = _held_and_loaded(groups_of(supports, 'supports'), groups_of(rollers, 'rollers'), load_groups,
                                   vectors, along, 2, nx, grid.m, lambda k: (k // (ny + 1), k % (ny + 1)))
    setup = {"active": active, "full": full, "free": free, "force": force, "held": held,
             "weight": mat.density * GRAVITY * t * h * h if self_weight else 0.0, "down": down_flat}
    ke = _cell_stiffness() * mat.elasticity * t
    result = _iterate(grid, ke, setup, target, turns, float(smoothing))
    result.update({"setup": setup, "ke": ke, "dim": 2, "nx": nx, "ny": ny, "h": h, "low": low, "swap": swap, "centre": centre, "ex": ex,
                   "ey": ey, "active": active, "grid": grid, "material": mat, "thickness": t})
    return result


# --- 3D --------------------------------------------------------------------------------------------------------------

def optimize_3d(region, voids=None, solid=None, supports=None, rollers=None, loads=None, load=1000.0,
                self_weight: bool = False, material: str = 'concrete C25/30', density=0.4, resolution=60, turns=60,
                smoothing=1.5, gravity=(0.0, 0.0, -1.0)) -> dict:
    """The optimization of a body, in cubes along the global axes; gives the grid and the densities."""
    mat, target, res, turns, _, down = _check(material, density, resolution, turns, 1.0, gravity, smoothing)
    bodies = _bodies(region, 'region')
    if not bodies:
        raise ShapeError(tr('Connect the region: the body where the material can go.'))
    allp = np.vstack([np.asarray(b.points) for b in bodies])
    low, high = allp.min(0), allp.max(0)
    order = np.argsort(-(high - low), kind="stable")            # the grid's first axis: the longer side
    size = (high - low)[order]
    h = size[0] / res
    shape = tuple(max(1, int(math.ceil(s / h - 1e-9))) for s in size)
    cubes = int(np.prod(shape))
    slice_moves = 3 * (shape[1] + 1) * (shape[2] + 1)
    if cubes > MAXIMUM_CUBES or slice_moves > MAXIMUM_SLICE:
        raise ShapeError(tr('Too many cubes ({n}): lower the resolution (in 3D, the body is cut into resolution '
                            'cubes along its longer side).').format(n=cubes))
    origin = low[order]

    def to_space(q):                                            # grid coordinates (…, 3) to space
        out = np.zeros(q.shape[:-1] + (3,))
        out[..., order] = q
        return out + 0.0

    index = np.indices(shape).reshape(3, -1).T
    centres = to_space(origin + (index + 0.5) * h)
    corner_index = np.indices(tuple(s + 1 for s in shape)).reshape(3, -1).T
    corners = to_space(origin + corner_index * h)
    design = _in_bodies(centres, bodies)
    empty = _in_bodies(centres, _bodies(voids, 'voids')) if voids is not None else np.zeros(cubes, bool)
    full = (_in_bodies(centres, _bodies(solid, 'solid parts')) if solid is not None
            else np.zeros(cubes, bool)) & ~empty
    active = (design | full) & ~empty
    free = active & ~full
    if not free.any():
        raise ShapeError(tr('There is nothing to optimize: the region has no cells left (too small for the '
                            'resolution, or covered by the voids and the solid parts).'))

    def groups_of(data, role):
        if data is None:
            return []
        if isinstance(data, Data) and data.kind in (POINT, VECTOR):
            q = np.array([p for _, p in _items(data, POINT)], float).reshape(-1, 3)
            return [np.atleast_1d(np.argmin(((corners - p) ** 2).sum(-1))) for p in q]
        out = []
        for body in _bodies(data, role):
            inside = np.nonzero(_in_bodies(corners, [body]))[0]
            centre = np.asarray(body.points).mean(0)
            out.append(inside if len(inside) else np.atleast_1d(np.argmin(((corners - centre) ** 2).sum(-1))))
        return out

    load_groups = groups_of(loads, 'loads')
    vectors = [v[order] for v in _load_vectors(loads, load, load_groups, down)]
    if not load_groups and not self_weight:
        raise ShapeError(tr('There is nothing to carry: connect some loads, or turn on the self weight.'))
    grid = _Grid(*shape)
    down_grid = down[order]
    along = int(np.argmax(np.abs(down_grid)))
    section = (shape[1] + 1, shape[2] + 1)

    def node_index(k):
        column, rest = np.divmod(k, section[0] * section[1])
        return column, rest                                     # the node in the slice: j · (nz + 1) + k

    held, force = _held_and_loaded(groups_of(supports, 'supports'), groups_of(rollers, 'rollers'), load_groups,
                                   vectors, along, 3, shape[0], grid.m, node_index)
    setup = {"active": active, "full": full, "free": free, "force": force, "held": held,
             "weight": mat.density * GRAVITY * h ** 3 if self_weight else 0.0, "down": down_grid}
    ke = _cell_stiffness(dim=3) * mat.elasticity * h
    result = _iterate(grid, ke, setup, target, turns, float(smoothing))
    result.update({"setup": setup, "ke": ke, "dim": 3, "shape": shape, "h": h, "origin": origin, "order": order, "active": active,
                   "grid": grid, "material": mat})
    return result


# --- What the node shows --------------------------------------------------------------------------------------------

def _to_space(r: dict, q: np.ndarray) -> np.ndarray:
    """Grid coordinates back to space."""
    if r["dim"] == 3:
        out = np.zeros(q.shape[:-1] + (3,))
        out[..., r["order"]] = q
        return out
    q = q[..., ::-1] if r["swap"] else q
    return r["centre"] + q[..., 0:1] * r["ex"] + q[..., 1:2] * r["ey"]


def _cells(r: dict, which: np.ndarray) -> np.ndarray:
    """The squares (k, 4, 3) or the cubes (k, 8, 3) of some cells, in space."""
    grid, h = r["grid"], r["h"]
    if r["dim"] == 2:
        low = r["low"]
        i, j = grid.i[which], grid.j[which]
        corners = np.stack([np.stack([low[0] + (i + a) * h, low[1] + (j + b) * h], -1)
                            for a, b in CORNERS[2]], 1)
        return _to_space(r, corners)
    cells = grid.cells[which]
    corners = np.stack([r["origin"] + (cells + np.array(c)) * h for c in CORNERS[3]], 1)
    return _to_space(r, corners)


def _outlines(r: dict, level: float = 0.5) -> list[np.ndarray]:
    """The outlines where the density crosses `level`: the shape, as closed curves in space."""
    import pyvista as pv
    from .surfaces import _polylines
    nx, ny = r["nx"], r["ny"]
    padded = np.pad(r["density"].reshape(nx, ny), 1)            # empty around: every outline closes
    image = pv.ImageData(dimensions=(nx + 2, ny + 2, 1), spacing=(r["h"], r["h"], 1.0),
                         origin=(r["low"][0] - 0.5 * r["h"], r["low"][1] - 0.5 * r["h"], 0.0))
    image.point_data["density"] = padded.ravel(order="F")
    out = []
    for p in _polylines(image.contour([level], scalars="density")):
        if len(p) < 4:
            continue
        if np.linalg.norm(p[0] - p[-1]) < 1e-9 * r["h"]:
            p = p[:-1]
        out.append(_to_space(r, p[:, :2]))
    return out


def _plate(r: dict, level: float = 0.5):
    """The shape of a plate filled in, with its holes: a flat mesh (vertices, triangles), cut where the density
    crosses `level`, the same edge as the outlines."""
    import pyvista as pv
    nx, ny = r["nx"], r["ny"]
    padded = np.pad(r["density"].reshape(nx, ny), 1)
    image = pv.ImageData(dimensions=(nx + 2, ny + 2, 1), spacing=(r["h"], r["h"], 1.0),
                         origin=(r["low"][0] - 0.5 * r["h"], r["low"][1] - 0.5 * r["h"], 0.0))
    image.point_data["density"] = padded.ravel(order="F")
    full = image.clip_scalar(scalars="density", value=level, invert=False)
    full = full.extract_surface(algorithm="dataset_surface").triangulate().clean()
    if full.n_points == 0:
        return None
    triangles = np.asarray(full.faces).reshape(-1, 4)[:, 1:]
    return _to_space(r, np.asarray(full.points, float)[:, :2]), triangles


def _surface(r: dict, level: float = 0.5):
    """The surface where the density crosses `level`: the shape of the body, smoothed, as (vertices, triangles)."""
    import pyvista as pv
    shape, h = r["shape"], r["h"]
    padded = np.pad(r["density"].reshape(shape), 1)
    image = pv.ImageData(dimensions=tuple(s + 2 for s in shape), spacing=(h, h, h),
                         origin=tuple(o - 0.5 * h for o in r["origin"]))
    image.point_data["density"] = padded.ravel(order="F")
    skin = image.contour([level], scalars="density").triangulate()
    if skin.n_points == 0:
        return None
    skin = skin.smooth_taubin(n_iter=30, pass_band=0.1)
    triangles = np.asarray(skin.faces).reshape(-1, 4)[:, 1:]
    return _to_space(r, np.asarray(skin.points, float)), triangles


#: The last optimizations, by their inputs: the ▶ (the moment) and the other «show» of the same optimization do not
#: compute it again.
_CACHE: "OrderedDict[tuple, dict]" = None
_CACHE_SIZE = 4


def _key(*inputs) -> tuple:
    """What tells one optimization from another: the values of its inputs."""
    def one(x):
        if isinstance(x, Data):
            return (np.asarray(x.values).tobytes(), np.asarray(x.values).shape, x.levels,
                    getattr(x.kind, "name", None))
        return repr(x)
    return tuple(one(x) for x in inputs)


def _at_moment(r: dict, moment: float) -> dict:
    """The optimization at a moment of its way: 0, the region full and thin; 1, the shape. Between two turns, the
    densities in between; the moves are worked out again for that moment."""
    history = r["history"]
    m = float(np.clip(moment, 0.0, 1.0))
    if m >= 1.0 or len(history) < 2:
        return r
    at = m * (len(history) - 1)
    k = int(np.floor(at))
    t = at - k
    density = history[k] if k + 1 >= len(history) else history[k] * (1 - t) + history[k + 1] * t
    out = dict(r)
    out["density"] = density
    out["at_moment"] = m
    return out


def _moves_at(r: dict) -> tuple[np.ndarray, np.ndarray]:
    """The moves and the stiffness of the cells for the densities of `r` (a moment of the way): one more solve."""
    if "at_moment" not in r:
        return r["u"], r["e"]
    e, _ = _stiffness_curve(r["density"], r["setup"]["weight"] > 0)
    setup = r["setup"]
    force = setup["force"] + (r["grid"].shared(setup["weight"] * r["density"], setup["down"])
                              if setup["weight"] else 0.0)
    return r["grid"].solve(r["ke"][None] * e[:, None, None], force, setup["held"]), e


def topology_2d(region, voids=None, solid=None, supports=None, rollers=None, loads=None, load=1000.0,
                self_weight: bool = False, material: str = 'concrete C25/30', thickness=0.3, density=0.4,
                resolution=60, turns=60, smoothing=1.5, gravity=(0.0, 0.0, -1.0), show: str = 'shape',
                name: str | None = None, moment=1.0) -> Data:
    """The node: the optimization (2D with an outline, 3D with a body), and what it shows (see the module), at a
    `moment` of its way (1: the shape; 0: the region full and thin)."""
    global _CACHE
    from collections import OrderedDict
    from .meshes import kind_mesh
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    moment = float(moment if moment is not None else 1.0)
    if not 0.0 <= moment <= 1.0:
        raise ShapeError(tr('The moment goes from 0 (the start) to 1 (the shape).'))
    if _CACHE is None:
        _CACHE = OrderedDict()
    key = _key(region, voids, solid, supports, rollers, loads, load, bool(self_weight), material, thickness, density,
               resolution, turns, smoothing, gravity)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        r = _CACHE[key]
    else:
        if _is_body(region):
            r = optimize_3d(region, voids, solid, supports, rollers, loads, load, self_weight, material, density,
                            resolution, turns, smoothing, gravity)
        else:
            r = optimize_2d(region, voids, solid, supports, rollers, loads, load, self_weight, material, thickness,
                            density, resolution, turns, smoothing, gravity)
        _CACHE[key] = r
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    r = _at_moment(r, moment)
    active, dim = r["active"], r["dim"]
    # The outline at half density; at the start of the way, when nothing reaches it yet, a little below the most there
    # is: the whole region, which then empties.
    level = min(0.5, 0.95 * float(r["density"][active].max(initial=0.0)))
    if show == 'shape' and dim == 2:
        from .surfaces import _resample
        rings = _outlines(r, level) if level > 0 else []
        if not rings:
            raise ShapeError(tr('No shape was left: raise the density, or check the loads and the supports.'))
        n = max(33, max(len(p) for p in rings))
        curves = np.stack([_resample(np.vstack([p, p[:1]]), n + 1)[:-1] for p in rings])
        out = Data(curves, ("outline",), name, kind=CLOSED_CURVE) if len(curves) > 1 else \
            Data(curves[0], (), name, kind=CLOSED_CURVE)
    elif show == 'plate' and dim == 2:
        full = _plate(r, level) if level > 0 else None
        if full is None:
            raise ShapeError(tr('No shape was left: raise the density, or check the loads and the supports.'))
        out = Data(full[0], (), name, kind=kind_mesh(full[1]))
    elif show in ('shape', 'plate'):                            # in 3D the shape is already a body
        skin = _surface(r, level) if level > 0 else None
        if skin is None:
            raise ShapeError(tr('No shape was left: raise the density, or check the loads and the supports.'))
        out = Data(skin[0], (), name, kind=kind_mesh(skin[1]))
    elif show in ('cells', 'grid'):
        which = active & (r["density"] >= level) if show == 'cells' else active
        out = Data(_cells(r, which), ("cell",), name, kind=RECTANGLE if dim == 2 else BOX)
    elif show == 'density':
        out = Data(r["density"][active], ("cell",), name)
    elif show == 'stress':
        u, e = _moves_at(r)
        ue = r["grid"].cell_moves(u) / r["h"]
        strain = ue @ _strain_at_centre(dim).T
        s = (strain @ _elasticity(dim).T) * (r["material"].elasticity * e)[:, None]
        out = Data(_von_mises(s)[active], ("cell",), name)
    else:
        u, _ = _moves_at(r)
        u = u.reshape(u.shape[0], -1, dim)
        out = Data(float(np.linalg.norm(u, axis=-1).max()), (), name)
    out.optimization = r                      # (not «topology»: for the view that says whether to draw the edges)
    return out
