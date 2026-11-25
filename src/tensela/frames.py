"""Bar analysis: how much a structure of bars bends, and how hard each bar works.

Each line (or each span of a curve, or each edge of a mesh) is a bar, welded to the others where they touch: a
beam, a column, a truss, a gridshell. The joints are rigid; the supports hold the joints nearest to some points
(clamped: nothing moves nor turns; pinned: it turns but does not move; roller: it only cannot move along the
weight). The loads: forces at points, a load per metre on every bar, and the weight of the bars themselves.

The engine is the usual one of structural programs, the stiffness method for frames in 3D (Euler-Bernoulli bars:
bending in two directions, axial force and torsion). Inside each bar, the deformed shape and the forces come out
exactly from its ends and its load (no need to divide it): the deformed shape with the cubic of the beam, the
moments with the parabola of a uniform load. The height of each section goes up (the strong axis resists the
weight); in a vertical bar, along x.

The check (utilization) is the elastic one: the largest stress of the bar, |N| / A + |M strong| / W strong +
|M weak| / W weak, over the strength of the material, in %. It does not check buckling, shear nor joints: it says
which bars work hardest and roughly how much, as a first sizing.
"""
from __future__ import annotations

import numpy as np

from .data import Data, ShapeError, integer
from .geometry import CURVE, VECTOR, gravity_direction
from .language import tr
from .sections import MATERIALS, section
from .simulation import _loads_at, _nearest, _points, network

#: How each support holds its joint.
SUPPORTS = ('clamped', 'pinned', 'roller')

#: What the node gives.
SHOW = ('deformed', 'displacements', 'axial forces', 'moments', 'utilization', 'reactions', 'largest displacement',
        'largest utilization', 'total weight')

#: At most this many joints. Solved in its band, a bridge of 3000 joints takes about 3 s and 500 MB; a lattice packed
#: every way has a wider band, and the limit below holds it back first.
MAXIMUM_JOINTS = 8000

#: The most numbers the band may keep (8 bytes each; with the window, about 850 MB at most): a solid lattice of
#: 18 × 18 × 18 joints fits, one of 20 × 20 × 20 does not.
MAXIMUM_BAND = 70_000_000

#: How many points each bar of the deformed shape has.
SAMPLES = 11

GRAVITY = 9.81


def _frames_of(a: np.ndarray, b: np.ndarray, up: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Length and local axes of each bar (m, 3, 3: rows x along the bar, y, z): z is the up of its section (the
    weight bends it about its strong axis); in a vertical bar, z is the global x."""
    d = b - a
    length = np.linalg.norm(d, axis=1)
    x = d / length[:, None]
    reference = np.broadcast_to(up, x.shape).copy()
    vertical = np.abs((x * reference).sum(1)) > 0.999
    reference[vertical] = (1.0, 0.0, 0.0)
    z = reference - (reference * x).sum(1)[:, None] * x
    z /= np.linalg.norm(z, axis=1)[:, None]
    y = np.cross(z, x)
    return length, np.stack([x, y, z], axis=1)


def _local_stiffness(length, e, g, area, strong, weak, torsion) -> np.ndarray:
    """The stiffness of each bar in its own axes (m, 12, 12): at each end, 3 moves and 3 turns."""
    m = len(length)
    k = np.zeros((m, 12, 12))
    L = length

    def put(i, j, value):
        k[:, i, j] = value
        k[:, j, i] = value

    axial, twist = e * area / L, g * torsion / L
    put(0, 0, axial), put(6, 6, axial), put(0, 6, -axial)
    put(3, 3, twist), put(9, 9, twist), put(3, 9, -twist)
    # Bending in the plane x-y (moves along y, turns about z): the weak inertia.
    a, b, c, d = 12 * e * weak / L ** 3, 6 * e * weak / L ** 2, 4 * e * weak / L, 2 * e * weak / L
    put(1, 1, a), put(1, 5, b), put(1, 7, -a), put(1, 11, b)
    put(5, 5, c), put(5, 7, -b), put(5, 11, d)
    put(7, 7, a), put(7, 11, -b), put(11, 11, c)
    # Bending in the plane x-z (moves along z, turns about y): the strong inertia.
    a, b, c, d = 12 * e * strong / L ** 3, 6 * e * strong / L ** 2, 4 * e * strong / L, 2 * e * strong / L
    put(2, 2, a), put(2, 4, -b), put(2, 8, -a), put(2, 10, -b)
    put(4, 4, c), put(4, 8, b), put(4, 10, d)
    put(8, 8, a), put(8, 10, b), put(10, 10, c)
    return k


def _fixed_end(length: np.ndarray, q: np.ndarray) -> np.ndarray:
    """The forces at the ends of each bar held fixed under a uniform load q (m, 3, in its own axes): (m, 12)."""
    L = length
    f = np.zeros((len(L), 12))
    f[:, 0] = f[:, 6] = q[:, 0] * L / 2
    f[:, 1] = f[:, 7] = q[:, 1] * L / 2
    f[:, 2] = f[:, 8] = q[:, 2] * L / 2
    f[:, 5], f[:, 11] = q[:, 1] * L ** 2 / 12, -q[:, 1] * L ** 2 / 12
    f[:, 4], f[:, 10] = -q[:, 2] * L ** 2 / 12, q[:, 2] * L ** 2 / 12
    return f


def _band_order(n: int, bars: np.ndarray) -> np.ndarray:
    """An order of the joints where each bar joins two that come near one another (reverse Cuthill-McKee): each part
    of the structure walked from one far end, joint after joint, the neighbours with fewer bars first. The numbers of
    the stiffness then lie in a narrow band around the diagonal (in a bridge, about two layers of joints wide)."""
    ends = np.unique(np.concatenate([bars, bars[:, ::-1]]), axis=0)
    first = np.searchsorted(ends[:, 0], np.arange(n + 1))
    degree = np.diff(first)
    seen = np.zeros(n, dtype=bool)

    def walk(root):
        out, head = [root], 0
        seen[root] = True
        while head < len(out):
            near = ends[first[out[head]]:first[out[head] + 1], 1]
            head += 1
            near = near[~seen[near]]
            near = near[np.argsort(degree[near], kind="stable")]
            seen[near] = True
            out.extend(near.tolist())
        return out
    order = []
    for root in np.argsort(degree, kind="stable"):
        if seen[root]:
            continue
        part = walk(int(root))
        seen[part] = False
        part = walk(part[-1])                        # again, from the far end the first walk reached
        order.extend(part)
    return np.array(order[::-1], dtype=np.int64)


def _band_factor(size: int, rows: np.ndarray, cols: np.ndarray, values: np.ndarray, extra: float) -> list:
    """The Cholesky factor of a symmetric matrix whose numbers lie in a band around the diagonal (rows, cols, values:
    both halves; repeated places add up), plus `extra` on the diagonal. It goes down the diagonal in blocks, keeping
    only a window as wide as the band: time and memory grow with the size times the band, not with the size cubed
    and squared as with the whole matrix."""
    band = int(np.abs(rows - cols).max()) if len(rows) else 0
    step = int(min(max(band, 64), 256))
    span = step + band
    enters = np.maximum(rows, cols)                  # a number enters the window with the later of its two places
    order = np.argsort(enters, kind="stable")
    rows, cols, values, enters = rows[order], cols[order], values[order], enters[order]
    window = np.zeros((span, span))
    blocks = []

    def load(start, low, high):                      # the numbers of the places low..high, into the window
        a, b = np.searchsorted(enters, [low, high])
        np.add.at(window, (rows[a:b] - start, cols[a:b] - start), values[a:b])
        diagonal = np.arange(low, high) - start
        window[diagonal, diagonal] += extra
    loaded = min(size, span)
    load(0, 0, loaded)
    start = 0
    while start < size:
        b = min(step, size - start)
        m = min(size, start + span) - start
        inverse = np.linalg.inv(np.linalg.cholesky(window[:b, :b]))
        lower = inverse @ window[:b, b:m]            # the block below, transposed: L21ᵀ = L11⁻¹ A12
        window[b:m, b:m] -= lower.T @ lower
        blocks.append((start, inverse, lower))
        window[:m - b, :m - b] = window[b:m, b:m].copy()
        window[m - b:, :] = 0.0
        window[:, m - b:] = 0.0
        start += b
        if loaded < min(size, start + span):
            load(start, loaded, min(size, start + span))
            loaded = min(size, start + span)
    return blocks


def _band_solve(blocks: list, rhs: np.ndarray) -> np.ndarray:
    """x with L Lᵀ x = rhs, for the factor of `_band_factor`."""
    x = np.array(rhs, dtype=float)
    for start, inverse, lower in blocks:             # L y = rhs, going down
        b = len(inverse)
        x[start:start + b] = inverse @ x[start:start + b]
        x[start + b:start + b + lower.shape[1]] -= lower.T @ x[start:start + b]
    for start, inverse, lower in reversed(blocks):   # Lᵀ x = y, going up
        b = len(inverse)
        x[start:start + b] = inverse.T @ (x[start:start + b] - lower @ x[start + b:start + b + lower.shape[1]])
    return x


def solve(joints, bars, supports, kinds, forces, line_load, material, sec) -> dict:
    """The analysis: joints (n, 3), bars (m, 2), supported joints and how, forces at the joints (n, 3), a uniform
    load on each bar (m, 3, global, N/m). Gives the moves of the joints, the forces at the ends of the bars, the
    reactions."""
    n, m = len(joints), len(bars)
    up = -line_load.sum(0)
    if np.linalg.norm(up) < 1e-12:
        up = np.array([0.0, 0.0, 1.0])
    up = up / np.linalg.norm(up)
    a, b = joints[bars[:, 0]], joints[bars[:, 1]]
    length, axes = _frames_of(a, b, up)
    if np.any(length < 1e-9):
        raise ShapeError(tr('A bar has no length (two joints in the same place).'))
    k_local = _local_stiffness(length, material.elasticity, material.shear, sec.area, sec.strong, sec.weak,
                               sec.torsion)
    t = np.zeros((m, 12, 12))
    for block in range(4):
        t[:, 3 * block:3 * block + 3, 3 * block:3 * block + 3] = axes
    k_global = np.einsum("mji,mjk,mkl->mil", t, k_local, t)
    q_local = np.einsum("mij,mj->mi", axes, line_load)
    f_fixed = _fixed_end(length, q_local)
    dofs = (6 * bars[:, [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1]] + np.tile(np.arange(6), 2)[None, :])
    size = 6 * n
    rows = np.broadcast_to(dofs[:, :, None], k_global.shape).reshape(-1)       # the stiffness, number by number
    cols = np.broadcast_to(dofs[:, None, :], k_global.shape).reshape(-1)
    values = k_global.reshape(-1)
    load = np.zeros(size)
    load[0::6], load[1::6], load[2::6] = forces[:, 0], forces[:, 1], forces[:, 2]
    np.add.at(load, dofs, np.einsum("mji,mj->mi", t, f_fixed))
    held = np.zeros(size, dtype=bool)
    for joint, kind in zip(supports, kinds):
        if kind == 'clamped':
            held[6 * joint:6 * joint + 6] = True
        elif kind == 'pinned':
            held[6 * joint:6 * joint + 3] = True
        else:                                                   # a roller: only along the weight
            axis = int(np.argmax(np.abs(up)))
            held[6 * joint + axis] = True
    free = ~held
    if not free.any():
        raise ShapeError(tr('Every joint is held: there is nothing to move.'))
    # A very soft spring on every move and turn: what nothing holds (the turn of a pinned beam about itself) stays
    # still instead of making the system unsolvable; what really moves freely shows up as a huge move.
    on_diagonal = rows == cols
    soft = 1e-12 * float(np.abs(np.bincount(rows[on_diagonal], values[on_diagonal], minlength=size)).max())
    # The free moves, in the order of the joints along the band (rows and columns of what is held, left out).
    rank = np.empty(n, dtype=np.int64)
    rank[_band_order(n, bars)] = np.arange(n)
    place = (6 * rank[:, None] + np.arange(6)).reshape(-1)
    free_moves = np.flatnonzero(free)[np.argsort(place[free], kind="stable")]
    number = np.full(size, -1, dtype=np.int64)
    number[free_moves] = np.arange(len(free_moves))
    both = (number[rows] >= 0) & (number[cols] >= 0)
    r, c, v = number[rows[both]], number[cols[both]], values[both]
    band = int(np.abs(r - c).max()) if len(r) else 0
    if len(free_moves) * (band + 256) > MAXIMUM_BAND:
        raise ShapeError(tr('Too many joints, too interwoven ({n}): use fewer spans, or fewer and larger '
                            'pieces.').format(n=n))

    def solved(extra):
        try:
            return _band_solve(_band_factor(len(free_moves), r, c, v, extra), load[free_moves])
        except np.linalg.LinAlgError:                # not positive even with the soft spring: something is loose
            return None
    moves_free = solved(soft)
    if moves_free is None:
        raise ShapeError(tr('The structure moves freely: it needs more supports, or supports that hold it sideways '
                            '(clamped or pinned).'))
    moves = np.zeros(size)
    moves[free_moves] = moves_free
    extent = float(np.ptp(joints, axis=0).max()) or 1.0
    largest = np.linalg.norm(moves.reshape(n, 6)[:, :3], axis=1).max() if np.all(np.isfinite(moves)) else np.inf
    # A move as large as the whole structure: something loose, or a bar far too weak for its load. What is loose
    # hangs only on the soft spring, so with a stiffer spring it moves much less; real bending does not change.
    if largest > extent and np.isfinite(largest):
        stiffer = solved(100.0 * soft)
        loose = stiffer is None or np.abs(stiffer).max() < 0.1 * np.abs(moves_free).max()
    else:
        loose = not np.isfinite(largest)
    if loose:
        raise ShapeError(tr('The structure moves freely: it needs more supports, or supports that hold it sideways '
                            '(clamped or pinned).'))
    u_local = np.einsum("mij,mj->mi", t, moves[dofs])
    ends = np.einsum("mij,mj->mi", k_local, u_local) - f_fixed
    reactions = np.bincount(rows, values * moves[cols], minlength=size) - load
    return {"joints": joints, "bars": bars, "length": length, "axes": axes, "u_local": u_local, "ends": ends,
            "q_local": q_local, "moves": moves.reshape(n, 6), "reactions": reactions.reshape(n, 6),
            "material": material, "section": sec}


def _along(r: dict, s: np.ndarray):
    """At the fractions s of each bar: the axial force (tension +), and the moments about the strong and the weak
    axes (m, k each), from the forces at its first end and its load."""
    L, q, f1 = r["length"][:, None], r["q_local"], r["ends"][:, :6]
    x = s[None, :] * L
    axial = -(f1[:, 0:1] + q[:, 0:1] * x)
    strong = -(f1[:, 4:5] + x * f1[:, 2:3] + q[:, 2:3] * x ** 2 / 2)
    weak = -(f1[:, 5:6] - x * f1[:, 1:2] - q[:, 1:2] * x ** 2 / 2)
    return axial, strong, weak


def _deformed(r: dict, scale: float) -> np.ndarray:
    """Each bar bent as it is (m, SAMPLES, 3): the moves of its ends along the cubic of the beam, plus the sag of its
    own load between them; `scale` times the real moves."""
    s = np.linspace(0, 1, SAMPLES)
    L = r["length"][:, None]
    u = r["u_local"]
    h1, h2, h3, h4 = 1 - 3 * s ** 2 + 2 * s ** 3, s - 2 * s ** 2 + s ** 3, 3 * s ** 2 - 2 * s ** 3, -s ** 2 + s ** 3
    e, sec = r["material"].elasticity, r["section"]
    bubble = (s * (1 - s)) ** 2 * L ** 4 / 24                  # the sag of a uniform load between fixed ends
    along = u[:, 0:1] * (1 - s) + u[:, 6:7] * s
    side = h1 * u[:, 1:2] + h2 * L * u[:, 5:6] + h3 * u[:, 7:8] + h4 * L * u[:, 11:12] \
        + r["q_local"][:, 1:2] * bubble / (e * sec.weak)
    up = h1 * u[:, 2:3] - h2 * L * u[:, 4:5] + h3 * u[:, 8:9] - h4 * L * u[:, 10:11] \
        + r["q_local"][:, 2:3] * bubble / (e * sec.strong)
    local = np.stack([along, side, up], axis=-1)               # (m, k, 3)
    moved = np.einsum("mji,mkj->mki", r["axes"], local)
    a = r["joints"][r["bars"][:, 0]]
    b = r["joints"][r["bars"][:, 1]]
    straight = a[:, None, :] + s[None, :, None] * (b - a)[:, None, :]
    return straight + scale * moved


def _largest_move(r: dict) -> float:
    """The largest move of the structure, along its bars too: a beam held at both ends moves most between them."""
    bent = _deformed(r, 1.0)
    a, b = r["joints"][r["bars"][:, 0]], r["joints"][r["bars"][:, 1]]
    s = np.linspace(0, 1, SAMPLES)
    straight = a[:, None, :] + s[None, :, None] * (b - a)[:, None, :]
    return float(max(np.linalg.norm(bent - straight, axis=-1).max(), np.linalg.norm(r["moves"][:, :3], axis=1).max()))


#: The last analyses, by everything that goes into them: the several Bar analysis nodes of one structure (the deformed
#: shape, the utilization, the weight…) solve it once.
_LAST: dict = {}


def _solved(joints, bars, held, support, forces, line_load, material, mat, sec) -> dict:
    key = (joints.tobytes(), bars.tobytes(), held.tobytes(), support, forces.tobytes(), line_load.tobytes(), material,
           repr(sec))
    if key not in _LAST:
        if len(_LAST) >= 8:
            _LAST.pop(next(iter(_LAST)))
        _LAST[key] = solve(joints, bars, held, [support] * len(held), forces, line_load, mat, sec)
    return _LAST[key]


#: The last networks of bars: the several Bar analysis nodes of one structure build it once (1300 cubes, 0.4 s each).
_NETWORKS: dict = {}


def _network(shape: Data, spans, diagonals: str) -> dict:
    holes = None if getattr(shape, "holes", None) is None else np.asarray(shape.holes).tobytes()
    key = (np.asarray(shape.values).tobytes(), np.asarray(shape.values).shape, shape.levels, shape.kind, holes,
           integer(spans), diagonals)
    if key not in _NETWORKS:
        if len(_NETWORKS) >= 4:
            _NETWORKS.pop(next(iter(_NETWORKS)))
        _NETWORKS[key] = network(shape, spans, diagonals, most=None)  # (its own limit, in joints: in bar_analysis)
    return _NETWORKS[key]


def bar_analysis(shape: Data, spans=0, supports=None, support='clamped', loads=None, load=10000.0, load_per_metre=0.0,
                 self_weight: bool = True, material: str = 'steel S275', section_=None, gravity=(0.0, 0.0, -1.0),
                 scale=0.0, show: str = 'deformed', name: str | None = None, diagonals: str = 'no diagonals') -> Data:
    """The analysis of a structure of bars (see the module). `section_`: a name («IPE 300») or a place in the
    catalogue; `scale`: how many times the moves are drawn (0: automatic, the largest a twentieth of the size);
    `diagonals`: in a mesh, bars across its squares too (one or both), to brace it."""
    if show not in SHOW:
        raise ShapeError(tr('«show» must be one of: {options}.').format(options=", ".join(tr(o) for o in SHOW)))
    if support not in SUPPORTS:
        raise ShapeError(tr('The supports must be one of: {options}.').format(
            options=", ".join(tr(o) for o in SUPPORTS)))
    if material not in MATERIALS:
        raise ShapeError(tr('The material must be one of: {options}.').format(
            options=", ".join(tr(o) for o in MATERIALS)))
    mat = MATERIALS[material]
    sec = section(section_ if section_ is not None else 'IPE 300')
    net = _network(shape, spans, diagonals)
    joints, bars = net["particles"], net["springs"]
    if len(joints) > MAXIMUM_JOINTS:
        raise ShapeError(tr('Too many joints ({n}; at most {maximum}): use fewer spans, or fewer and larger '
                            'pieces.').format(
            n=len(joints), maximum=MAXIMUM_JOINTS))
    down = gravity_direction(gravity)
    where = _points(supports, 'supports')
    if not len(where):
        raise ShapeError(tr('Nothing holds it: connect the points of its supports.'))
    held = np.unique(_nearest(joints, where))
    forces = np.zeros_like(joints)
    at = _points(loads, 'loads')
    if len(at):
        np.add.at(forces, _nearest(joints, at), _loads_at(at, load, down))
    per_metre = float(load_per_metre or 0.0) + (mat.density * GRAVITY * sec.area if self_weight else 0.0)
    line_load = np.broadcast_to(per_metre * down, (len(bars), 3)).copy()
    r = _solved(joints, bars, held, support, forces, line_load, material, mat, sec)
    if show == 'deformed':
        largest = _largest_move(r)
        extent = float(np.ptp(joints, axis=0).max()) or 1.0
        factor = float(scale or 0.0)
        if factor <= 0:
            factor = 0.05 * extent / largest if largest > 1e-15 else 1.0
        out = Data(_deformed(r, factor), ("bar",), name, kind=CURVE)
    elif show == 'displacements':
        out = Data(np.linalg.norm(r["moves"][:, :3], axis=1), ("joint",), name)
    elif show in ('axial forces', 'moments', 'utilization', 'largest utilization'):
        s = np.linspace(0, 1, SAMPLES)
        axial, strong, weak = _along(r, s)
        if show == 'axial forces':
            ends = axial[:, [0, -1]]
            out = Data(ends[np.arange(len(ends)), np.argmax(np.abs(ends), axis=1)], ("bar",), name)
        elif show == 'moments':
            out = Data(np.maximum(np.abs(strong), np.abs(weak)).max(1), ("bar",), name)
        else:
            stress = np.abs(axial) / sec.area + np.abs(strong) / sec.modulus_strong + np.abs(weak) / sec.modulus_weak
            used = 100.0 * stress.max(1) / mat.strength
            out = Data(used, ("bar",), name) if show == 'utilization' else Data(float(used.max()), (), name)
    elif show == 'reactions':
        out = Data(r["reactions"][held, :3], ("support",), name, kind=VECTOR)
    elif show == 'largest displacement':
        out = Data(_largest_move(r), (), name)
    else:
        out = Data(float(mat.density * sec.area * r["length"].sum()), (), name)
    out.analysis = r
    return out
