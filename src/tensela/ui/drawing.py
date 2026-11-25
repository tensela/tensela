"""Drawing with the mouse in the 3D view: the points of a «Drawn curve» (Grasshopper's *Crv*) or the control points
of a «NURBS Curve».

While drawing, a bar over the view gives the **tools** (each one with its key):

- **Select (V)**: click on a point chooses it; dragging it moves all the chosen ones. **Shift + click** adds or
  removes one; **Ctrl + drag** in an empty place, a box. Click in an empty place: none.
- **Add (A)**: click in an empty place, a new point at the end; click **on the control line** (the one that joins
  the points), a new one in that span. Dragging a point moves it.
- **Delete (X)**: click on a point removes it.
- **Weight (W)**, in a NURBS Curve: dragging a point upwards attracts the curve more; downwards, less.

In all of them:

- With **Alt**, a dragged point leaves the plane: it goes up or down (in plan, in z). The new points stay at the
  height of the last one.
- **Right-click on a point**: its exact coordinates, its weight, insert one before or after, delete it.
- **Double click on a point**: its exact coordinates, straight away.
- **Del** or **Backspace**: deletes the chosen ones (or the point under the pointer; if there is none, the last one).
- With «Snap», the points fall **only** on the crossings of the grid; a «ghost» point shows where the click would
  fall. **Ctrl** inverts it while pressed.
- **Enter** or **Esc**: finish.

It draws on the plane the view looks at (the «Views» menu): the ground (z = 0) in plan or in 3D; from the front, the
elevation; from the side, the side elevation. Dragging in an empty place still moves the view as always.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pyvista as pv
from PySide6.QtCore import QEvent, QObject, QRect, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QMenu, QPushButton, QWidget)

from ..language import comma, tr

#: At how many pixels from the pointer a point is «grabbed» to drag it.
RADIUS_TAKE = 12
#: At how many pixels from the control line a click puts a point in that span.
RADIUS_RUN = 7
#: The more marked lines of the grid: every so many steps.
CHECKED_EACH = 5
COLOR_POINTS = "#f2a93b"
#: The axes of the plane where it draws, with the usual colours (those of the corner cube): x red, y green,
#: z azul.
COLOR_AXES = ("#d9534f", "#4fa35a", "#4a7fd4")
#: What changes with the background, so it looks equally good in the light and dark themes.
CHOSEN_COLOR = {"dark": "#ffffff", "light": "#1d2027"}      # the point under the pointer and the ghost on a crossing
COLOR_GRID = {"dark": "#b4bac4", "light": "#5d6470"}
OPACITY_GRID = {"dark": (0.32, 0.7), "light": (0.38, 0.8)}  # (thin lines, marked lines)
#: The line that joins the points: light on a dark background, dark on a light background (always distinguishable).
COLOR_CONTROL = {"dark": "#ffc861", "light": "#7a3c00"}
#: The grid steps offered in the panel (in metres).
STEPS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
#: The tools of the curve editor and their key.
TOOLS = ("select", "add", "pen", "delete", "weight")
KEYS = {Qt.Key.Key_V: "select", Qt.Key.Key_A: "add", Qt.Key.Key_P: "pen", Qt.Key.Key_X: "delete",
          Qt.Key.Key_W: "weight"}
#: The pen's handles: their point and the line that joins them to their anchor.
COLOR_HANDLE = {"dark": "#9fd0ff", "light": "#1f5fa8"}
#: The curvature comb: the hairs, faint; its edge (the line that joins the tips), marked.
COLOR_COMB = {"dark": "#ff8fb3", "light": "#b0245a"}
COLOR_GUIDE = {"dark": "#7fd6ff", "light": "#0b6aa8"}     # the alignment guides of Shift
#: How near (in pixels on the screen) another point has to be, along an axis, for Shift to align with it.
ALIGN_PIXELS = 12
#: With the Weight tool: how many pixels of dragging double (or halve) the weight.
PIXELS_BY_DOUBLE = 60


def grid_curvature() -> bool:
    """Whether the curvature comb is seen when editing (remembered between sessions)."""
    return QSettings().value("drawing/curvature", False, type=bool)


def grid() -> tuple[float, bool]:
    """The step of the drawing grid (m) and whether the points snap to it; remembered between sessions."""
    a = QSettings()
    step = a.value("drawing/step", 1.0, type=float)
    return (step if step > 0 else 1.0), a.value("drawing/snap", True, type=bool)


class Drafter(QObject):
    """Collects the clicks of the 3D view while drawing; otherwise, it does nothing."""

    tool_changed = Signal(str)

    def __init__(self, plotter, parent=None):
        super().__init__(parent)
        self.plotter = plotter
        self.points: np.ndarray | None = None          # (n, 3) while drawing; None if not
        self.weights = np.zeros(0)                      # the weight of each point (NURBS Curve; 1 normal)
        self.corners = np.zeros(0, dtype=bool)          # which points are corners (Drawn curve)
        self.with_weights = False
        self.edges = None                               # the edges of a mesh being edited (Edit mesh); None: a curve
        self._on_change: Callable | None = None
        self._on_finish: Callable | None = None
        self._over: int | None = None               # the point under the pointer
        self._dragging: int | None = None
        self._click = None                             # where the left button was pressed in an empty place
        self._snapped = False                        # the last computed point fell on a crossing of the grid
        self.tool = "add"
        self.chosen: set[int] = set()               # with Select: the chosen points
        self._group = None                            # (the grabbed point, where all were) when moving the chosen ones
        self._moved = False
        self._weight = None                             # (point, weight at the start, and y at the start) when dragging its weight
        self._box = None                         # (the box, where it started) with Ctrl + drag
        self.step, self.adjust = grid()
        self.see_curvature = QSettings().value("drawing/curvature", False, type=bool)
        self.samples = None
        plotter.interactor.installEventFilter(self)   # after the navigator: this one looks first

    @property
    def active(self) -> bool:
        return self.points is not None

    def start(self, points, on_change: Callable, on_finish: Callable, with_weights: bool = False,
                curve: Callable | None = None, pen: bool = False, on_dismiss: Callable | None = None,
                samples: Callable | None = None, edges=None, marked=None, on_mark: Callable | None = None) -> None:
        """`points`: those kept in the node ([x, y, z] or, with weight, [x, y, z, weight]). `on_change(points, final)`:
        final is False while dragging and True on releasing or adding. `with_weights`: each point has its weight (NURBS
        Curve). `curve()`: (degree, knot mode, closed) of the NURBS, to put a point with a click on the curve itself. `pen`:
        `points` is the pen's stroke (anchors with their handles); `on_close()`: a click on the first anchor closes the
        stroke. `samples()`: the points of the computed curve (for its curvature comb). `edges`: the points are the
        vertices of a mesh (Edit mesh), joined by these pairs; they can only be chosen and moved, never added or
        removed (the faces need them all). `marked`: which of them are drawn as squares (the supports of an
        Equilibrium); `on_mark(i, yes)`: the right-click menu offers to hold point i where it is, or to let it go."""
        self.marked = None if marked is None else np.asarray(marked, dtype=bool).copy()
        self._on_mark = on_mark
        self.curve, self.pen, self._on_dismiss = curve, pen, on_dismiss
        self.edges = None if edges is None else np.asarray(edges, dtype=int).reshape(-1, 2)
        self.samples = samples
        self._pulling = None
        from ..geometry import drawn_anchors, drawn_corners, drawn_weights, drawn_points
        if pen:                                     # the anchors are the points; apart, their handles
            self.points, self.inputs, self.outputs, self.kinds = drawn_anchors(points)
            self.weights = np.ones(len(self.points))
            self.corners = np.zeros(len(self.points), dtype=bool)
        else:
            self.points = drawn_points(points)
            self.weights = drawn_weights(points)
            self.corners = drawn_corners(points) if edges is None else np.zeros(len(self.points), dtype=bool)
        self.with_weights = with_weights
        self._on_change, self._on_finish = on_change, on_finish
        self._over = self._dragging = None
        self.chosen = set()
        new = "pen" if pen else "add"
        self.tool = "select" if len(self.points) or self.edges is not None else new   # a new curve: to put points
        self.tool_changed.emit(self.tool)
        if self.edges is not None:
            # A mesh: its vertices move freely (a cage is shaped by eye, not on a metre grid; Ctrl snaps), and the
            # view frames it.
            self._adjust_before, self.adjust = self.adjust, False
            width, height = self.plotter.ren_win.GetSize()
            screen = np.array([self._in_screen(q) for q in self.points]) if len(self.points) else np.zeros((0, 2))
            seen = len(screen) and screen.min() >= 0 and screen[:, 0].max() <= width and screen[:, 1].max() <= height
            size = float(np.ptp(screen, axis=0).max()) if len(screen) else 0.0
            if not seen or size < 0.4 * max(width, height):    # out of view or too small to grab a vertex
                low, high = self.points.min(axis=0), self.points.max(axis=0)
                pad = max(float((high - low).max()) * 0.15, 0.05)
                self.plotter.reset_camera(bounds=(low[0] - pad, high[0] + pad, low[1] - pad, high[1] + pad,
                                                  low[2] - pad, high[2] + pad), render=False)
        reach = self._draw_grid()
        if not len(self.points) and self.edges is None:   # a new curve: the whole grid in view
            limits = [0.0] * 6
            for i in self._others_axes():
                limits[2 * i], limits[2 * i + 1] = -reach, reach
            self.plotter.reset_camera(bounds=tuple(limits), render=False)
        self._paint()
        self.paint_comb()
        self.plotter.interactor.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.plotter.interactor.setFocus()

    def put_tool(self, tool: str) -> None:
        """Select, Add, Delete or Weight (from the bar or with its key)."""
        if tool not in TOOLS or (tool == "weight" and (not self.with_weights or self.pen)) \
                or (tool == "pen" and not self.pen) or (tool == "add" and self.pen) \
                or (self.edges is not None and tool != "select"):
            return
        self.tool = tool
        if self.active:
            self.plotter.remove_actor("_drawing_ghost", render=False)
            self.plotter.interactor.setCursor(QCursor(self._cursor(None)))
            self._paint()
        self.tool_changed.emit(tool)

    def _cursor(self, over: int | None) -> Qt.CursorShape:
        """The pointer, by the tool and whether there is a point under it."""
        if over is None:
            return Qt.CursorShape.CrossCursor if self.tool in ("add", "pen") else Qt.CursorShape.ArrowCursor
        return {"delete": Qt.CursorShape.PointingHandCursor,
                "weight": Qt.CursorShape.SizeVerCursor}.get(self.tool, Qt.CursorShape.OpenHandCursor)

    def change_grid(self, step: float, adjust: bool) -> None:
        """Another grid step or snap yes/no (from the node's panel); remembered."""
        self.step, self.adjust = (step if step > 0 else 1.0), adjust
        a = QSettings()
        a.setValue("drawing/step", self.step)
        a.setValue("drawing/snap", self.adjust)
        self.repaint()

    def put_curvature(self, yes: bool) -> None:
        """The curvature comb yes or no (from the bar); remembered."""
        self.see_curvature = bool(yes)
        QSettings().setValue("drawing/curvature", self.see_curvature)
        self.paint_comb()

    def paint_comb(self) -> None:
        """The curvature comb of the curve being edited (with the curve already computed: the window asks for it)."""
        for name in ("_drawing_comb", "_drawing_comb_edge"):
            self.plotter.remove_actor(name, render=False)
        curve = self.samples() if (self.active and self.see_curvature and self.samples is not None) else None
        if curve is not None and len(curve) >= 3:
            from ..geometry import curvature_comb
            bases, tips = curvature_comb(curve)
            if len(bases):
                color = COLOR_COMB[self._background()]
                m = len(bases)
                hairs = np.column_stack([np.full(m, 2), np.arange(m), np.arange(m) + m]).ravel()
                self.plotter.add_mesh(pv.PolyData(np.vstack([bases, tips]), lines=hairs), color=color,
                                      opacity=0.45, line_width=1, name="_drawing_comb", pickable=False,
                                      reset_camera=False, lighting=False)
                self.plotter.add_mesh(pv.PolyData(tips, lines=np.concatenate([[m], np.arange(m)])), color=color,
                                      line_width=2, name="_drawing_comb_edge", pickable=False, reset_camera=False,
                                      lighting=False)
        self.plotter.render()

    def mark_nodes(self, points, highlighted=None) -> None:
        """Where the knots fall on the curve (small dots), and the one of the strip under the pointer, bigger."""
        for name in ("_drawing_knots", "_drawing_knot"):
            self.plotter.remove_actor(name, render=False)
        if self.active and points is not None and len(points):
            self.plotter.add_mesh(pv.PolyData(np.asarray(points, dtype=float)), color=self._ink(), point_size=8,
                                  render_points_as_spheres=True, name="_drawing_knots", pickable=False,
                                  reset_camera=False)
        if self.active and highlighted is not None:
            self.plotter.add_mesh(pv.PolyData(np.asarray(highlighted, dtype=float).reshape(1, 3)),
                                  color=COLOR_COMB[self._background()], point_size=16, render_points_as_spheres=True,
                                  name="_drawing_knot", pickable=False, reset_camera=False)
        self.plotter.render()

    def put_points(self, points, marked=None) -> None:
        """New positions for the same points (an Equilibrium, after it settles again): the one being dragged stays
        under the pointer."""
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        if self.points is None or len(points) != len(self.points):
            return
        keep = set()
        if self._dragging is not None:                 # the grabbed one (and, moving the chosen ones, all of them)
            keep = (set(self.chosen) if self._group is not None else set()) | {self._dragging}
        for i in range(len(points)):
            if i not in keep:
                self.points[i] = points[i]
        if marked is not None:
            self.marked = np.asarray(marked, dtype=bool).copy()
        self._paint()

    def repaint(self) -> None:
        """The grid and the points again (the background changed: their colours depend on it)."""
        if self.active:
            self._draw_grid()
            self._paint()

    def finish(self, warn: bool = True) -> None:
        if not self.active:
            return
        if self.edges is not None:                     # the snapping, as it was for the curves
            self.adjust = getattr(self, "_adjust_before", self.adjust)
            self.edges = None
        self.points = None
        self.chosen = set()
        if self._box is not None:
            self._box[0].hide()
            self._box = None
        for name in ("_drawing_points", "_drawing_chosen", "_drawing_polygon", "_drawing_grid", "_drawing_weights",
                       "_drawing_weights-labels",
                       "_drawing_grid_marked", "_drawing_ghost", "_drawing_coordinates", "_drawing_axis_0",
                       "_drawing_axis_1", "_drawing_axes_names", "_drawing_axes_names-labels", "_drawing_handles",
                       "_drawing_handle_lines", "_drawing_comb", "_drawing_comb_edge", "_drawing_knots",
                       "_drawing_knot", "_drawing_corners", "_drawing_guides"):
            self.plotter.remove_actor(name, render=False)
        self.plotter.interactor.unsetCursor()
        self.plotter.render()
        on_finish, self._on_finish = self._on_finish, None
        if warn and on_finish is not None:
            on_finish()

    # --- From the pointer to the model ---------------------------------------------------------------

    def _screen(self, pos) -> tuple[float, float]:
        w = self.plotter.interactor
        width, height = self.plotter.ren_win.GetSize()
        return pos.x() * width / max(w.width(), 1), height - pos.y() * height / max(w.height(), 1)

    def _ray(self, pos) -> tuple[np.ndarray, np.ndarray]:
        ren = self.plotter.renderer
        x, y = self._screen(pos)
        ends = []
        for z in (0.0, 1.0):
            ren.SetDisplayPoint(x, y, z)
            ren.DisplayToWorld()
            w = np.array(ren.GetWorldPoint())
            ends.append(w[:3] / (w[3] or 1.0))
        return ends[0], ends[1] - ends[0]

    def _axis_plane(self) -> int:
        """On which plane it draws: the ground (z), except looking almost from the front (y) or from the side (x)."""
        direction = np.abs(np.array(self.plotter.camera.direction))
        return 2 if direction[2] >= 0.25 else int(np.argmax(direction[:2]))

    def _in_plane(self, pos, by: np.ndarray | None = None, adjust: bool = False) -> np.ndarray | None:
        """The point of the drawing plane under the pointer (through `through`, if a point is dragged)."""
        axis = self._axis_plane()
        level = 0.0 if by is None else float(by[axis])
        origin, direction = self._ray(pos)
        if abs(direction[axis]) < 1e-12:
            return None
        point = origin + direction * (level - origin[axis]) / direction[axis]
        point[axis] = level
        self._snapped = False
        if adjust:                                    # with «Snap», only on the crossings of the grid
            others = [i for i in range(3) if i != axis]
            point[others] = np.round(point[others] / self.step) * self.step
            self._snapped = True
        return np.round(point, 4)

    def _in_normal(self, pos, point: np.ndarray, adjust: bool = False) -> np.ndarray | None:
        """With Alt: the point moves out of the drawing plane, along the perpendicular line through it (in plan, it goes
        up or down). As close to that line as the ray of the pointer passes."""
        axis = self._axis_plane()
        origin, direction = self._ray(pos)
        normal = np.zeros(3)
        normal[axis] = 1.0
        d = direction / max(np.linalg.norm(direction), 1e-12)
        w = point - origin
        b = float(np.dot(normal, d))
        if 1 - b * b < 1e-6:                           # looking right along the line: it cannot be done
            return None
        s = (b * float(np.dot(w, d)) - float(np.dot(w, normal))) / (1 - b * b)
        new_ = np.array(point, dtype=float)
        new_[axis] += s
        if adjust:
            new_[axis] = np.round(new_[axis] / self.step) * self.step
        return np.round(new_, 4)

    def _in_screen(self, p) -> np.ndarray:
        ren = self.plotter.renderer
        ren.SetWorldPoint(*p, 1.0)
        ren.WorldToDisplay()
        return np.array(ren.GetDisplayPoint()[:2])

    def _run_nearest(self, pos) -> int | None:
        """The span of the control line under the pointer: the index where a new point would go."""
        if self.points is None or len(self.points) < 2:
            return None
        x = np.array(self._screen(pos))
        best, distance = None, RADIUS_RUN * self.plotter.ren_win.GetSize()[0] / max(self.plotter.interactor.width(), 1)
        screen = [self._in_screen(p) for p in self.points]
        for i in range(len(screen) - 1):
            a, b = screen[i], screen[i + 1]
            ab = b - a
            t = float(np.dot(x - a, ab) / max(np.dot(ab, ab), 1e-9))
            if not 0.05 < t < 0.95:                    # near a point the point rules
                continue
            d = float(np.linalg.norm(a + t * ab - x))
            if d < distance:
                best, distance = i + 1, d
        return best

    def _point_nearest(self, pos) -> int | None:
        if self.points is None or not len(self.points):
            return None
        ren = self.plotter.renderer
        x, y = self._screen(pos)
        best, distance = None, RADIUS_TAKE * self.plotter.ren_win.GetSize()[0] / max(self.plotter.interactor.width(), 1)
        for i, p in enumerate(self.points):
            ren.SetWorldPoint(*p, 1.0)
            ren.WorldToDisplay()
            px, py, _ = ren.GetDisplayPoint()
            d = np.hypot(px - x, py - y)
            if d < distance:
                best, distance = i, d
        return best

    # --- What is seen ------------------------------------------------------------------------

    def _others_axes(self) -> list[int]:
        """The two axes of the plane where it draws (x and y in plan; x and z from the front; y and z from the side)."""
        axis = self._axis_plane()
        return [i for i in range(3) if i != axis]

    def _draw_grid(self) -> float:
        """A help grid on the plane where it draws (the ground; from the front, the elevation; from the side, the side
        elevation), of one metre, covering what is in the scene; it gives its reach."""
        others = self._others_axes()
        self._axis_grid = self._axis_plane()
        limits = np.array(self.plotter.bounds).reshape(3, 2) if self.plotter.renderer.actors else np.zeros((3, 2))
        reach = max(20.0, float(np.abs(limits[others]).max()) + 5.0) if np.isfinite(limits).all() else 20.0
        if self.points is not None and len(self.points):
            reach = max(reach, float(np.abs(self.points[:, others]).max()) + 5.0)
        self._reach = reach
        step = self.step
        while reach / step > 400:                    # a fine step in a big scene: not so many lines
            step *= 2
        n = int(np.ceil(reach / step))
        edge = n * step
        # Always 1 px: thicker lines get deformed in VTK when zooming in a lot (wide bands).
        background = self._background()
        fine, checked_ = OPACITY_GRID[background]
        for name, checked, opacity in (("_drawing_grid", False, fine), ("_drawing_grid_marked", True, checked_)):
            indices = [i for i in range(-n, n + 1) if (i % CHECKED_EACH == 0) == checked]
            values = np.array(indices, dtype=float) * step
            runs = []
            for v in values:                          # lines in both directions of the plane
                for fixed, long in ((others[0], others[1]), (others[1], others[0])):
                    a, b = np.zeros(3), np.zeros(3)
                    a[fixed] = b[fixed] = v
                    a[long], b[long] = -edge, edge
                    runs.append((a, b))
            if not runs:
                self.plotter.remove_actor(name, render=False)
                continue
            points = np.array(runs, dtype=float).reshape(-1, 3)
            lines = np.column_stack([np.full(len(runs), 2), np.arange(0, 2 * len(runs), 2),
                                      np.arange(1, 2 * len(runs), 2)]).ravel()
            self.plotter.add_mesh(pv.PolyData(points, lines=lines), color=COLOR_GRID[background], opacity=opacity,
                                  line_width=1, name=name, pickable=False, reset_camera=False, lighting=False)
        self._draw_axes(others, edge)
        return edge

    def _draw_axes(self, others: list[int], edge: float) -> None:
        """The two axes of the plane, coloured, through the origin, with their name at 1 m: where 0 is and where each
        coordinate grows (in plan: x to the right, y to the back)."""
        for k, axis in enumerate(others):
            a, b = np.zeros(3), np.zeros(3)
            a[axis], b[axis] = -edge, edge
            actor = self.plotter.add_mesh(pv.Line(a, b), color=COLOR_AXES[axis], line_width=2,
                                          name=f"_drawing_axis_{k}", pickable=False, reset_camera=False, lighting=False)
            actor.mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-2.0, -80.0)   # on the grid
        names = np.zeros((2, 3))
        for k, axis in enumerate(others):
            names[k, axis] = 1.0
        self.plotter.add_point_labels(names, [f"{'xyz'[e]} +" for e in others], name="_drawing_axes_names",
                                      font_size=12, text_color=self._ink(), shape_opacity=0.0, show_points=False,
                                      always_visible=True, pickable=False, reset_camera=False)

    def _paint(self) -> None:
        if self.points is None:
            return
        if getattr(self, "_axis_grid", None) != self._axis_plane() or (
                len(self.points) and float(np.abs(self.points[:, self._others_axes()]).max()) > getattr(self, "_reach", 0) - 2):
            # The view changed (from plan to front…) or the points reach the edge: the grid, again.
            self._draw_grid()                   # the points reach the edge: the grid grows
        for name in ("_drawing_points", "_drawing_chosen", "_drawing_polygon"):
            self.plotter.remove_actor(name, render=False)
        self.plotter.remove_actor("_drawing_corners", render=False)
        if len(self.points):
            corners = self._corners_now() if self.can_corner() else np.zeros(len(self.points), dtype=bool)
            if self.marked is not None and len(self.marked) == len(self.points):
                corners = self.marked
            if (~corners).any():                       # round points: circles
                self.plotter.add_mesh(pv.PolyData(self.points[~corners]), color=COLOR_POINTS,
                                      point_size=9 if self.edges is not None else 18,
                                      render_points_as_spheres=True, name="_drawing_points", pickable=False,
                                      reset_camera=False)
            else:
                self.plotter.remove_actor("_drawing_points", render=False)
            if corners.any():                          # corners: squares
                self.plotter.add_mesh(pv.PolyData(self.points[corners]), color=COLOR_POINTS, point_size=16,
                                      render_points_as_spheres=False, name="_drawing_corners", pickable=False,
                                      reset_camera=False)
        self._paint_handles()
        if self.edges is not None and len(self.edges):   # a mesh: its edges
            lines = np.column_stack([np.full(len(self.edges), 2), self.edges]).ravel()
            self.plotter.add_mesh(pv.PolyData(self.points, lines=lines), color=COLOR_CONTROL[self._background()],
                                  line_width=1, name="_drawing_polygon", pickable=False, reset_camera=False,
                                  lighting=False)
        elif len(self.points) > 1 and not self.pen:   # the order of the points: the control line
            n = len(self.points)
            self.plotter.add_mesh(pv.PolyData(self.points, lines=np.concatenate([[n], np.arange(n)])),
                                  color=COLOR_CONTROL[self._background()], line_width=1, name="_drawing_polygon",
                                  pickable=False, reset_camera=False, lighting=False)
        self.plotter.remove_actor("_drawing_weights", render=False)
        different = [i for i in range(len(self.points)) if i < len(self.weights) and abs(self.weights[i] - 1) > 1e-9]
        if self.with_weights and different:              # the weight of those that do not have 1, next to the point
            self.plotter.add_point_labels(self.points[different], [f"×{comma(_m(self.weights[i]))}" for i in different],
                                          name="_drawing_weights", font_size=11, text_color=self._ink(),
                                          shape_opacity=0.0, show_points=False, always_visible=True,
                                          pickable=False, reset_camera=False)
        highlighted = set(self.chosen) | {i for i in (self._dragging, self._over) if i is not None}
        highlighted = sorted(i for i in highlighted if i < len(self.points))
        if highlighted:                                # the chosen ones and the one under the pointer
            self.plotter.add_mesh(pv.PolyData(self.points[highlighted]), color=CHOSEN_COLOR[self._background()],
                                  point_size=14 if self.edges is not None else 24, render_points_as_spheres=True,
                                  name="_drawing_chosen",
                                  pickable=False, reset_camera=False)
        self.plotter.render()

    def _coordinates(self, point) -> None:
        """Where the pointer is (or the point it has under it, or the one being dragged), in the two coordinates of the
        plane: to draw «from x = 0 to x = 3». At the top, to the left of the axes cube."""
        self.plotter.remove_actor("_drawing_coordinates", render=False)
        if point is None:
            return
        text = "   ".join(f"{'xyz'[e]} = {comma(_m(point[e])).replace('-', '−')}"
                           for e in self._others_axes())
        self.plotter.add_text(text, position=(0.66, 0.93), viewport=True, font_size=11,
                              color=self._ink(), name="_drawing_coordinates")

    def _world_tolerance(self, point: np.ndarray, axis: int) -> float:
        """How many metres ALIGN_PIXELS are along `axis`, where the point is on the screen."""
        step = np.zeros(3)
        step[axis] = 1.0
        pixels = float(np.linalg.norm(self._in_screen(point + step) - self._in_screen(point)))
        return ALIGN_PIXELS / pixels if pixels > 1e-9 else 0.0

    def _aligned(self, point: np.ndarray, moving: int | None = None, reference: int | None = None):
        """With Shift: the point in line with `reference` (horizontal or vertical in the drawing plane, whichever is
        nearer), and, along the axis left free, in line with any other point that is near enough. Returns the point
        and the guides (from each point it lines up with, to it)."""
        others = self._others_axes()
        q = np.array(point, dtype=float)
        sources, locked = [], set()
        if reference is not None and 0 <= reference < len(self.points) and reference != moving:
            r = self.points[reference]
            d = q - r
            lock = others[1] if abs(d[others[0]]) >= abs(d[others[1]]) else others[0]
            q[lock] = r[lock]
            locked.add(lock)
            sources.append(r.copy())
        candidates = [j for j in range(len(self.points)) if j != moving]
        for axis in others:
            if axis in locked or not candidates:
                continue
            tolerance = self._world_tolerance(q, axis)
            gaps = np.abs(self.points[candidates, axis] - q[axis])
            k = int(np.argmin(gaps))
            if gaps[k] < tolerance:
                q[axis] = self.points[candidates[k], axis]
                sources.append(self.points[candidates[k]].copy())
        q = np.round(q, 4)
        return q, [(a, q) for a in sources if np.linalg.norm(a - q) > 1e-9]

    def _paint_guides(self, guides) -> None:
        """The alignment guides of Shift: thin lines from the points it lines up with."""
        self.plotter.remove_actor("_drawing_guides", render=False)
        if guides:
            points = np.array([p for pair in guides for p in pair], dtype=float)
            m = len(guides)
            lines = np.column_stack([np.full(m, 2), np.arange(0, 2 * m, 2), np.arange(1, 2 * m, 2)]).ravel()
            actor = self.plotter.add_mesh(pv.PolyData(points, lines=lines), color=COLOR_GUIDE[self._background()],
                                          line_width=1, name="_drawing_guides", pickable=False, reset_camera=False,
                                          lighting=False)
            actor.mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-2.0, -90.0)

    def _reference(self, moving: int | None = None) -> int | None:
        """Which point Shift lines up with: the one before the moved one (the second, for the first); when adding, the
        last one."""
        n = len(self.points) if self.points is not None else 0
        if moving is None:
            return n - 1 if n else None
        if moving > 0:
            return moving - 1
        return 1 if n > 1 else None

    def _ghost(self, pos, adjust: bool, over=None, shift: bool = False) -> None:
        """Where a click would fall: white on a crossing of the grid; faint orange if it goes free. On a point (`over`),
        without a ghost, but with its coordinates."""
        self.plotter.remove_actor("_drawing_ghost", render=False)
        self._coordinates(None if over is None else self.points[over])
        guides = []
        if pos is not None:
            point = self._in_plane(pos, adjust=adjust)
            if point is not None and shift and self.tool == "add" and len(self.points):
                point, guides = self._aligned(point, None, self._reference())
            if point is not None:
                self._coordinates(point)
                self.plotter.add_mesh(pv.PolyData(point[None]),
                                      color=CHOSEN_COLOR[self._background()] if self._snapped else COLOR_POINTS,
                                      opacity=0.9 if self._snapped else 0.6, point_size=14,
                                      render_points_as_spheres=True, name="_drawing_ghost", pickable=False,
                                      reset_camera=False)
        self._paint_guides(guides)
        self.plotter.render()

    def _ink(self) -> str:
        return "#1d2027" if self._background() == "light" else "#e6e7ec"

    def _background(self) -> str:
        r, g, b = self.plotter.background_color.float_rgb
        return "light" if 0.299 * r + 0.587 * g + 0.114 * b > 0.5 else "dark"

    def _warn(self, final: bool) -> None:
        if self._on_change is None:
            return
        if self.pen:                                # the stroke: anchor, in handle, out handle and kind
            self._on_change([[float(c) for c in (*a, *e, *s)] + [int(t)] for a, e, s, t in
                              zip(self.points, self.inputs, self.outputs, self.kinds)], final)
            return
        from ..geometry import drawn_row
        list_ = []
        corners = self._corners_now()
        for i, p in enumerate(self.points):
            weight = float(self.weights[i]) if self.with_weights and i < len(self.weights) else 1.0
            list_.append(drawn_row(p, weight, bool(corners[i])))   # the weight if it is not 1; 1 more if a corner
        self._on_change(list_, final)

    def _corners_now(self) -> np.ndarray:
        """The corners, as many as there are points (a point added by other means is not one)."""
        n = len(self.points)
        if len(self.corners) != n:
            self.corners = np.r_[self.corners[:n], np.zeros(max(0, n - len(self.corners)), dtype=bool)]
        return self.corners

    def can_corner(self) -> bool:
        """Corners: in a Drawn curve (not in the pen, which has its own, nor in a NURBS Curve or a mesh)."""
        return not self.pen and self.edges is None and not self.with_weights

    def toggle_corner(self, indices) -> None:
        """Those points become corners (the curve breaks there), or, if they all were, round again."""
        corners = self._corners_now()
        indices = sorted(i for i in indices if 0 <= i < len(self.points))
        if not indices or not self.can_corner():
            return
        corners[indices] = not corners[indices].all()
        self._paint()
        self._warn(True)

    def _put_in(self, i: int, point) -> None:
        """A new point at position `i` (with weight 1)."""
        corners = self._corners_now()
        self.points = np.insert(self.points, i, point, axis=0)
        self.weights = np.insert(self.weights, min(i, len(self.weights)), 1.0)
        self.corners = np.insert(corners, min(i, len(corners)), False)
        if self.pen:                                # a corner anchor: its handles, on it
            self.inputs = np.insert(self.inputs, i, point, axis=0)
            self.outputs = np.insert(self.outputs, i, point, axis=0)
            self.kinds = np.insert(self.kinds, i, 0)
        self.chosen = {j + 1 if j >= i else j for j in self.chosen}   # the chosen ones stay the same

    # --- Mouse and keyboard ---------------------------------------------------------------------

    def eventFilter(self, object_, event) -> bool:
        if not self.active:
            return False
        t = event.type()
        left = Qt.MouseButton.LeftButton
        mods = event.modifiers() if hasattr(event, "modifiers") else Qt.KeyboardModifier.NoModifier
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        adjust = self.adjust != ctrl                 # Ctrl inverts the snapping to the grid
        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
            nearest = self._point_nearest(event.position())
            if nearest is not None:                    # right-click on a point: its menu
                self._menu_point(nearest, event.globalPosition().toPoint())
                return True
            return False
        if t == QEvent.Type.MouseButtonDblClick and event.button() == left:
            nearest = self._point_nearest(event.position())
            if nearest is not None:                    # double click on a point: its exact coordinates
                self._dragging = None
                self.ask_coordinates(nearest)
                return True
            return False
        if t == QEvent.Type.MouseButtonPress and event.button() == left:
            return self._press(event.position(), ctrl, shift)
        if t == QEvent.Type.MouseMove and self._box is not None:
            band, from_ = self._box
            band.setGeometry(QRect(from_.toPoint(), event.position().toPoint()).normalized())
            # To the right, «window» (blue, solid: what stays inside); to the
            # left, «crossing» (green, dashed: also what it touches).
            capture = event.position().x() < from_.x()
            color = "rgba(80, 200, 120, {})" if capture else "rgba(70, 140, 255, {})"
            band.setStyleSheet(f"QFrame {{ background: {color.format(0.12)}; border: 1px "
                                f"{'dashed' if capture else 'solid'} {color.format(0.95)}; }}")
            return True
        if t == QEvent.Type.MouseMove and self._weight is not None:
            i, weight, y = self._weight
            new_ = float(np.clip(weight * 2 ** ((y - event.position().y()) / PIXELS_BY_DOUBLE), 0.01, 1000))
            self.weights[i] = round(new_, 3 if new_ < 10 else 1)
            self._display_text(tr('weight ×{weight}').format(weight=comma(_m(self.weights[i]))))
            self._paint()
            self._warn(False)
            return True
        if t == QEvent.Type.MouseMove and self.active and getattr(self, "_pulling", None) is not None:
            self._pull(event.position(), bool(mods & Qt.KeyboardModifier.AltModifier), adjust)
            return True
        if t == QEvent.Type.MouseMove and self._dragging is not None:
            self._drag(event.position(), bool(mods & Qt.KeyboardModifier.AltModifier), adjust, shift)
            return True
        if t == QEvent.Type.MouseMove and not event.buttons():
            if getattr(self, "_axis_grid", None) != self._axis_plane():   # the view changed: another plane
                self._paint()
            nearest = self._point_nearest(event.position())
            if nearest != self._over:
                self._over = nearest
                self.plotter.interactor.setCursor(QCursor(self._cursor(nearest)))
                self._paint()
            ghost = nearest is None and self.tool in ("add", "pen")   # where a new one would fall
            self._ghost(event.position() if ghost else None, adjust, nearest, shift)
            return False
        if t == QEvent.Type.Leave:
            self._ghost(None, adjust)
            return False
        if t == QEvent.Type.MouseButtonRelease and event.button() == left:
            return self._release(event.position(), shift, adjust)
        if t == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.finish()
                return True
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                if self.edges is not None:              # the vertices of a mesh are not removed
                    return True
                if self.chosen:
                    self.delete_several(self.chosen)
                elif len(self.points):
                    self.delete(self._over if self._over is not None else len(self.points) - 1)
                return True
            if key == Qt.Key.Key_C and self.can_corner() and not mods & (Qt.KeyboardModifier.ControlModifier |
                                                                          Qt.KeyboardModifier.AltModifier):
                which = self.chosen or ({self._over} if self._over is not None else set())
                self.toggle_corner(which)                 # C: the chosen points (or the one under the pointer)
                return True
            if key in KEYS and not mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
                self.put_tool(KEYS[key])
                return True
        return False

    def _press(self, pos, ctrl: bool, shift: bool) -> bool:
        """The left button, by the tool. True: it belongs to the editor (the view does not turn)."""
        nearest = self._point_nearest(pos)
        h = self.tool
        if self.pen:
            handle = self._handle_nearest(pos)
            if handle is not None and h in ("select", "pen"):     # grab a handle
                self._pulling = (*handle, False)
                return True
            if handle is not None and h == "delete":                # remove a handle: it goes back to its anchor
                i, side = handle
                (self.inputs if side == "in" else self.outputs)[i] = self.points[i]
                if np.allclose(self.inputs[i], self.points[i]) and np.allclose(self.outputs[i], self.points[i]):
                    self.kinds[i] = 0
                else:
                    self.kinds[i] = 2
                self._paint()
                self._warn(True)
                return True
            if h == "pen":
                return self._press_pen(pos, nearest, shift)
        if h == "delete":
            if nearest is not None:
                self.delete(nearest)
                return True
            return False
        if h == "weight":
            if nearest is not None:
                self._weight = (nearest, float(self.weights[nearest]), pos.y())
                self._over = nearest
                return True
            return False
        if h == "select":
            if nearest is not None:
                if shift:                              # adds or removes one
                    self.chosen ^= {nearest}
                    self._paint()
                    return True
                if nearest not in self.chosen:
                    self.chosen = {nearest}
                self._take(nearest, group=True)
                return True
            if ctrl:                                   # a box to choose several
                band = QFrame(self.plotter.interactor)
                band.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                band.setGeometry(QRect(pos.toPoint(), QSize()))
                band.show()
                self._box = (band, pos)
                return True
            self._click = pos                           # a click in an empty place: none chosen (if dragged, it turns)
            return False
        if nearest is not None:
            self._take(nearest, group=False)
            return True
        if shift:                                      # Add: Shift + click, a point in line; Shift + drag pans
            self._click = pos
            return False
        self._click = pos                               # maybe a new point; if dragged, the view moves
        return False

    def _take(self, i: int, group: bool) -> None:
        """A point is grabbed to drag it (with Select, all the chosen ones go)."""
        self.plotter.remove_actor("_drawing_ghost", render=False)
        self._dragging = i
        self._group = (i, self.points.copy()) if group else None
        if self.pen:                                # the handles move with their anchor
            self._handles_take = (self.inputs.copy(), self.outputs.copy(), self.points.copy())
        self._moved = False
        self._paint()

    def _drag(self, pos, alt: bool, adjust: bool, shift: bool = False) -> None:
        i = self._dragging
        before = self._group[1][i] if self._group is not None else self.points[i]
        if alt:                                        # Alt: out of the plane (up or down)
            new_ = self._in_normal(pos, self.points[i], adjust)
        else:
            new_ = self._in_plane(pos, self.points[i], adjust)
        if new_ is None:
            return
        guides = []
        if shift and not alt:                          # Shift: in line with its neighbour, or with another point
            moving = set(self.chosen) if self._group is not None else {i}
            if len(moving) == 1:
                new_, guides = self._aligned(new_, i, self._reference(i))
        self._paint_guides(guides)
        if self._group is not None:                    # all the chosen ones, the same as the grabbed one
            delta = new_ - before
            moved = self.chosen
            for j in moved:
                self.points[j] = np.round(self._group[1][j] + delta, 4)
        else:
            moved = {i}
            self.points[i] = new_
        if self.pen:
            inputs, outputs, anchors = self._handles_take
            for j in moved:
                self.inputs[j] = inputs[j] + (self.points[j] - anchors[j])
                self.outputs[j] = outputs[j] + (self.points[j] - anchors[j])
        self._moved = True
        self._coordinates(new_)
        self._paint()
        self._warn(False)

    def _release(self, pos, shift: bool, adjust: bool) -> bool:
        if getattr(self, "_pulling", None) is not None:
            i, side, moved = self._pulling
            self._pulling = None
            if side == "new" and not moved and self._convert:   # Alt + click on an anchor: to a corner
                self.inputs[i] = self.outputs[i] = self.points[i]
                self.kinds[i] = 0
            self._paint()
            self._warn(True)
            return True
        if self._box is not None:                 # the points inside the box
            band, from_ = self._box
            self._box = None
            band.hide()
            (x0, y0), (x1, y1) = self._screen(from_), self._screen(pos)
            box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            screen = [self._in_screen(p) for p in self.points]
            inside = {i for i, q in enumerate(screen) if _in_box(q, box)}
            if pos.x() < from_.x():                    # crossing: also the spans the box touches
                pairs = self.edges if self.edges is not None else zip(range(len(screen) - 1), range(1, len(screen)))
                for i, j in pairs:
                    if _run_touches_box(screen[i], screen[j], box):
                        inside |= {int(i), int(j)}
            self.chosen = (self.chosen | inside) if shift else inside
            self._paint()
            return True
        if self._weight is not None:
            self._weight = None
            self._display_text(None)
            self._paint()
            self._warn(True)
            return True
        if self._dragging is not None:
            self._dragging, self._group = None, None
            self._paint_guides([])
            self._paint()
            if self._moved:
                self._warn(True)
            return True
        click, self._click = self._click, None
        if click is None or (pos - click).manhattanLength() >= 5:
            return False                               # it was dragged: it was the view
        if self.tool == "select":               # click in an empty place: none chosen
            if self.chosen:
                self.chosen = set()
                self._paint()
            return False
        run = self._run_nearest(pos)
        if run is None and self._put_in_curve(pos):
            return False                               # on the curve itself: one more control point, there
        if run is not None:                          # in a span: at the height of its two points
            by = (self.points[run - 1] + self.points[run]) / 2
        else:                                          # at the end: at the height of the last one (if it went up, it stays up)
            by = self.points[-1] if len(self.points) else None
        new_ = self._in_plane(pos, by, adjust)
        if new_ is not None and shift and len(self.points):   # Shift: in line with the point before
            new_, _ = self._aligned(new_, None, (run - 1) if run is not None else self._reference())
        self._paint_guides([])
        if new_ is not None:                          # on the control line: in that span; if not, at the end
            where = len(self.points) if run is None else run
            self._put_in(where, new_)
            self._paint()
            self._warn(True)
        return False                                   # the navigator also releases its own

    # --- The pen -------------------------------------------------------------------------------

    def _press_pen(self, pos, nearest: int | None, shift: bool) -> bool:
        """The Pen tool: click, a corner anchor; click and drag, a smooth anchor (with Alt, the handle breaks); click on
        the first one, closes; click on the curve, one more anchor there; Alt on an anchor converts it (dragging, new
        handles; without dragging, a corner)."""
        alt = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)
        if nearest is not None:
            if alt:
                self._pulling, self._convert = (nearest, "new", False), True
                return True
            if nearest == 0 and len(self.points) >= 3 and not self._closed_this() and self._on_dismiss:
                self._on_dismiss()                      # the first anchor: the stroke closes
                return True
            self._take(nearest, group=False)
            return True
        if shift:                                      # Shift + drag pans the view
            return False
        run = self._run_pen(pos)
        if run is not None:                          # on the curve: one more anchor, without changing the shape
            from ..geometry import split_run
            i, t = run
            self.points, self.inputs, self.outputs, self.kinds = split_run(
                self.points, self.inputs, self.outputs, self.kinds, i, t)
            self.weights = np.ones(len(self.points))
            self.chosen = set()
            self._paint()
            self._warn(True)
            return True
        ctrl = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
        by = self.points[-1] if len(self.points) else None
        new_ = self._in_plane(pos, by, self.adjust != ctrl)
        if new_ is None:
            return True
        self._put_in(len(self.points), new_)        # at the end, a corner; if dragged, smooth
        self._pulling, self._convert = (len(self.points) - 1, "new", False), False
        self.plotter.remove_actor("_drawing_ghost", render=False)
        self._paint()
        self._warn(False)
        return True

    def _pull(self, pos, alt: bool, adjust: bool) -> None:
        """A handle is dragged (or those of a new anchor are pulled out)."""
        i, side, _ = self._pulling
        a = self.points[i]
        q = self._in_plane(pos, a, adjust)
        if q is None:
            return
        if side == "new":                            # the out one goes to the pointer; the in one, symmetric
            self.outputs[i] = q
            if alt and not self._convert:            # Alt: it breaks (the in one stays)
                self.kinds[i] = 2
            else:
                self.inputs[i] = 2 * a - q
                self.kinds[i] = 1
        else:
            (self.inputs if side == "in" else self.outputs)[i] = q
            other = self.outputs if side == "in" else self.inputs
            if alt:
                self.kinds[i] = 2                      # Alt: each handle on its own
            elif self.kinds[i] == 1:                   # smooth: the other one turns to stay aligned (with its length)
                length = float(np.linalg.norm(other[i] - a))
                d = q - a
                n = float(np.linalg.norm(d))
                if n > 1e-9 and length > 1e-9:
                    other[i] = a - d / n * length
            elif self.kinds[i] == 0:
                self.kinds[i] = 2                      # a handle comes out of a corner: broken
        self._pulling = (i, side, True)
        self._coordinates(q)
        self._paint()
        self._warn(False)

    def _handle_nearest(self, pos):
        """The handle under the pointer: (anchor, "in" or "out"), or None."""
        if not self.pen or self.points is None or not len(self.points):
            return None
        x = np.array(self._screen(pos))
        best, distance = None, RADIUS_TAKE * self.plotter.ren_win.GetSize()[0] / max(self.plotter.interactor.width(), 1)
        for i in range(len(self.points)):
            for side, handles in (("in", self.inputs), ("out", self.outputs)):
                if np.allclose(handles[i], self.points[i]):
                    continue                           # without a handle on that side
                d = float(np.linalg.norm(self._in_screen(handles[i]) - x))
                if d < distance:
                    best, distance = (i, side), d
        return best

    def _run_pen(self, pos):
        """The span of the stroke under the pointer and its parameter: (anchor it leaves, t), or None."""
        from ..geometry import SAMPLES_BY_RUN
        n = len(self.points)
        if n < 2:
            return None
        x = np.array(self._screen(pos))
        radius = RADIUS_RUN * self.plotter.ren_win.GetSize()[0] / max(self.plotter.interactor.width(), 1)
        t = np.linspace(0, 1, SAMPLES_BY_RUN + 1)[1:-1, None]
        best, distance = None, radius
        runs = range(n if self._closed_this() and n > 2 else n - 1)
        for i in runs:
            j = (i + 1) % n
            p0, p1, p2, p3 = self.points[i], self.outputs[i], self.inputs[j], self.points[j]
            curve = (1 - t) ** 3 * p0 + 3 * t * (1 - t) ** 2 * p1 + 3 * t ** 2 * (1 - t) * p2 + t ** 3 * p3
            for k, c in enumerate(curve):
                d = float(np.linalg.norm(self._in_screen(c) - x))
                if d < distance:
                    best, distance = (i, float(t[k, 0])), d
        return best

    def _closed_this(self) -> bool:
        data_items = self.curve() if self.curve is not None else None
        return bool(data_items and data_items[2])

    def _paint_handles(self) -> None:
        """The pen's handles: a point and a thin line up to its anchor."""
        for name in ("_drawing_handles", "_drawing_handle_lines"):
            self.plotter.remove_actor(name, render=False)
        if not self.pen or not len(self.points):
            return
        tips, lines = [], []
        for i in range(len(self.points)):
            for handles in (self.inputs, self.outputs):
                if not np.allclose(handles[i], self.points[i]):
                    tips.append(handles[i])
                    lines += [self.points[i], handles[i]]
        if not tips:
            return
        color = COLOR_HANDLE[self._background()]
        self.plotter.add_mesh(pv.PolyData(np.array(tips)), color=color, point_size=11,
                              render_points_as_spheres=True, name="_drawing_handles", pickable=False,
                              reset_camera=False)
        n = len(lines)
        cells = np.column_stack([np.full(n // 2, 2), np.arange(0, n, 2), np.arange(1, n, 2)]).ravel()
        self.plotter.add_mesh(pv.PolyData(np.array(lines), lines=cells), color=color, line_width=1,
                              name="_drawing_handle_lines", pickable=False, reset_camera=False, lighting=False)

    def _put_in_curve(self, pos) -> bool:
        """A click on the NURBS itself (not on its control line): one more control point at that place, without the curve
        changing shape with those knots (knot insertion). True if it put it."""
        from .. import geometry as geo
        data_items = self.curve() if self.curve is not None else None
        if data_items is None or len(self.points) < 2:
            return False
        degree, mode, closed = data_items
        if closed or mode not in ('uniform', 'chord length', 'square root of chord'):
            return False                               # (closed or by hand: the knots are not recomputed by themselves)
        k = max(1, min(int(degree), geo.MAX_DEGREE_NURBS, len(self.points) - 1))
        try:
            knots = geo._open_nodes(self.points, k, mode, np.zeros(0))
            t = geo._samples(knots, 0.0, 1.0, False)
            which, base = geo._local_base(knots, k, t)
            base = base * self.weights[which]
            curve = np.einsum("tj,tjc->tc", base, self.points[which]) / base.sum(axis=1)[:, None]
        except Exception:
            return False
        x = np.array(self._screen(pos))
        distances = [np.linalg.norm(self._in_screen(c) - x) for c in curve]
        more_near = int(np.argmin(distances))
        radius = RADIUS_RUN * self.plotter.ren_win.GetSize()[0] / max(self.plotter.interactor.width(), 1)
        if distances[more_near] > radius or not 0 < t[more_near] < 1:
            return False
        points, weights = geo.insert_node(self.points, self.weights, k, knots, float(t[more_near]))
        self.points, self.weights = np.round(points, 4), np.round(weights, 6)
        self.chosen = set()
        self._paint()
        self._warn(True)
        return True

    def _display_text(self, text: str | None) -> None:
        """A text where the coordinates go (the weight, while dragging)."""
        self.plotter.remove_actor("_drawing_coordinates", render=False)
        if text:
            self.plotter.add_text(text, position=(0.66, 0.93), viewport=True, font_size=11,
                                  color=self._ink(), name="_drawing_coordinates")

    # --- A particular point (right click) ---------------------------------------------------

    def _menu_point(self, i: int, where) -> None:
        p = self.points[i]
        menu = QMenu(self.plotter.interactor)
        if self.edges is not None:                     # a vertex of a mesh: where it is, and exactly where it goes
            title = menu.addAction(tr('Vertex {n}: ({x}, {y}, {z})').format(n=i, x=_m(p[0]), y=_m(p[1]), z=_m(p[2])))
            title.setEnabled(False)
            menu.addSeparator()
            menu.addAction(tr('Exact coordinates…'), lambda: self.ask_coordinates(i))
            if self._on_mark is not None:              # a particle of an Equilibrium: held here, or let go
                held = self.marked is not None and i < len(self.marked) and bool(self.marked[i])
                menu.addAction(tr('Let it go (a support by hand)') if held else tr('Hold it here (a support)'),
                               lambda: self._on_mark(i, not held))
            self._over = i
            self._paint()
            menu.exec(where)
            self._over = None
            if self.active:
                self._paint()
            return
        title = menu.addAction(tr('Point {n} of {total}: ({x}, {y}, {z})').format(
            n=i + 1, total=len(self.points), x=_m(p[0]), y=_m(p[1]), z=_m(p[2])))
        title.setEnabled(False)
        menu.addSeparator()
        menu.addAction(tr('Exact coordinates…'), lambda: self.ask_coordinates(i))
        if self.with_weights:
            menu.addAction(tr('Weight… (now {weight})').format(weight=comma(_m(self.weights[i]))), lambda: self.ask_weight(i))
        if self.pen:
            menu.addAction(tr('Corner anchor (no handles)'), lambda: self.convert(i, 0))
            menu.addAction(tr('Smooth anchor (aligned handles)'), lambda: self.convert(i, 1))
        if self.can_corner():
            which = sorted(self.chosen) if i in self.chosen and len(self.chosen) > 1 else [i]
            corner = menu.addAction(tr('Corner: the curve breaks here (C)') if len(which) == 1 else
                                    tr('Corners: the curve breaks at the {n} chosen (C)').format(n=len(which)))
            corner.setCheckable(True)
            corner.setChecked(bool(self._corners_now()[which].all()))
            corner.triggered.connect(lambda _=False: self.toggle_corner(which))
        menu.addAction(tr('Insert a point before'), lambda: self.insert(i))
        menu.addAction(tr('Insert a point after'), lambda: self.insert(i + 1))
        menu.addSeparator()
        menu.addAction(tr('Delete this point'), lambda: self.delete(i)).setShortcut("Del")
        self._over = i
        self._paint()
        menu.exec(where)
        self._over = None
        if self.active:
            self._paint()

    def convert(self, i: int, kind: int) -> None:
        """A pen anchor to a corner (without handles) or smooth (aligned handles, towards its neighbours)."""
        a = self.points[i]
        if kind == 0:
            self.inputs[i] = self.outputs[i] = a
        else:
            n = len(self.points)
            before = self.points[i - 1] if i > 0 else a
            after = self.points[i + 1] if i < n - 1 else a
            direction = after - before
            length = float(np.linalg.norm(direction))
            if length < 1e-9:
                return
            d = direction / length
            self.inputs[i] = a - d * np.linalg.norm(a - before) / 3
            self.outputs[i] = a + d * np.linalg.norm(after - a) / 3
        self.kinds[i] = kind
        self._paint()
        self._warn(True)

    def move(self, i: int, point) -> None:
        new_ = np.round(np.array(point, dtype=float), 4)
        if self.pen:                                # its handles, with it
            self.inputs[i] += new_ - self.points[i]
            self.outputs[i] += new_ - self.points[i]
        self.points[i] = new_
        self._paint()
        self._warn(True)

    def insert(self, i: int) -> None:
        """A new point at position `i`: halfway between its neighbours (or one step beyond the end)."""
        n = len(self.points)
        if n == 0:
            return
        if 0 < i < n:
            new_ = (self.points[i - 1] + self.points[i]) / 2
        elif n == 1:
            new_ = self.points[0] + (self.step if i else -self.step, 0, 0)
        elif i == 0:
            new_ = 2 * self.points[0] - self.points[1]
        else:
            new_ = 2 * self.points[-1] - self.points[-2]
        self._put_in(i, np.round(new_, 4))
        self._paint()
        self._warn(True)

    def delete(self, i: int) -> None:
        self.delete_several({i})

    def delete_several(self, indices) -> None:
        """Removes those points at once (they are undone at once)."""
        remove = sorted(i for i in indices if 0 <= i < len(self.points))
        if not remove:
            return
        self.points = np.delete(self.points, remove, axis=0)
        self.weights = np.delete(self.weights, [i for i in remove if i < len(self.weights)])
        self.corners = np.delete(self.corners, [i for i in remove if i < len(self.corners)])
        if self.pen:
            self.inputs = np.delete(self.inputs, remove, axis=0)
            self.outputs = np.delete(self.outputs, remove, axis=0)
            self.kinds = np.delete(self.kinds, remove)
        self.chosen = set()
        self._over = None
        self._paint()
        self._warn(True)

    def put_weight(self, i: int, weight: float) -> None:
        if 0 <= i < len(self.weights) and weight > 0:
            self.weights[i] = float(weight)
            self._paint()
            self._warn(True)

    def ask_weight(self, i: int) -> None:
        weight = _ask_weight(self.plotter.interactor, i + 1, float(self.weights[i]))
        if weight is not None and self.active:
            self.put_weight(i, weight)

    def ask_coordinates(self, i: int) -> None:
        dialog = QDialog(self.plotter.interactor)
        dialog.setWindowTitle(tr('Point {n}').format(n=i + 1))
        shape = QFormLayout(dialog)
        fields = []
        for axis, value in zip("xyz", self.points[i]):
            field = QDoubleSpinBox()
            field.setRange(-1e6, 1e6)
            field.setDecimals(3)
            field.setSingleStep(self.step)
            field.setSuffix(" m")
            field.setValue(float(value))
            shape.addRow(axis, field)
            fields.append(field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        shape.addRow(buttons)
        fields[0].selectAll()
        if dialog.exec() == QDialog.DialogCode.Accepted and self.active:
            self.move(i, [c.value() for c in fields])


def _in_box(q, box) -> bool:
    return box[0] <= q[0] <= box[2] and box[1] <= q[1] <= box[3]


def _run_touches_box(a, b, box) -> bool:
    """Whether the segment ab (on screen) touches the rectangle `box` (x0, y0, x1, y1)."""
    if _in_box(a, box) or _in_box(b, box):
        return True
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return any(_cut(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4))


def _cut(a, b, c, d) -> bool:
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) <= 0 and side(c, d, a) * side(c, d, b) <= 0


def _ask_weight(parent, n: int, current: float) -> float | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(tr('Weight of point {n}').format(n=n))
    shape = QFormLayout(dialog)
    field = QDoubleSpinBox()
    field.setRange(0.01, 1000.0)
    field.setDecimals(3)
    field.setSingleStep(0.25)
    field.setValue(current)
    shape.addRow(tr('Weight'), field)
    help = QLabel(tr('1: normal · more: the curve comes closer to the point · less: it moves away'))
    help.setWordWrap(True)
    shape.addRow(help)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    shape.addRow(buttons)
    field.selectAll()
    return field.value() if dialog.exec() == QDialog.DialogCode.Accepted else None


def _m(value: float) -> str:
    """A short coordinate: 2.5, -3, 0.125."""
    return f"{value:.3f}".rstrip("0").rstrip(".") if abs(value) >= 5e-4 else "0"


class StripNodes(QWidget):
    """The knots of the curve being edited on a ruler from 0 to 1 (under the editor's bar): dragging one moves it;
    double-click, one more knot (and a control point, without changing the shape); right-click on one, repeat it (a
    break) or remove it. On hovering over one, the view marks where it falls on the curve."""

    moved = Signal(list, bool)            # the new inner knots; final (on releasing)
    insert = Signal(float)               # double-click: one more knot at that value
    remove = Signal(int)                   # right-click → remove: the inner knot number such
    over = Signal(object)                # the value of the knot under the pointer (or None)

    MARGIN = 26
    HEIGHT = 34

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        self.inner: list[float] = []
        self.degree = 3
        self._taken: int | None = None
        self._over: int | None = None
        self.hide()

    def put(self, inner, degree: int) -> None:
        if self._taken is None:                       # while dragging, the drag rules
            self.inner = [float(u) for u in inner]
        self.degree = degree
        self.update()

    def _x(self, u: float) -> float:
        return self.MARGIN + u * (self.width() - 2 * self.MARGIN)

    def _u(self, x: float) -> float:
        return float(np.clip((x - self.MARGIN) / max(self.width() - 2 * self.MARGIN, 1), 0.0, 1.0))

    def _nearest(self, x: float) -> int | None:
        if not self.inner:
            return None
        d = [abs(self._x(u) - x) for u in self.inner]
        i = int(np.argmin(d))
        return i if d[i] <= 6 else None

    def paintEvent(self, _event) -> None:
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QColor, QPainter, QPen
        from . import theme as theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        text, accent = QColor(theme.color("text", "#ecedf2")), QColor(theme.color("accent", "#8a7dff"))
        faint = QColor(text)
        faint.setAlpha(90)
        y = self.height() / 2 + 3
        p.setPen(QPen(faint, 1))
        p.drawLine(QPointF(self._x(0), y), QPointF(self._x(1), y))
        p.setPen(QPen(text, 2))
        for u in (0.0, 1.0):                           # the ends: fixed (the curve starts and ends at its points)
            p.drawLine(QPointF(self._x(u), y - 7), QPointF(self._x(u), y + 7))
        font = p.font()
        font.setPixelSize(15)                         # 0 and 1, at the height of the end marks
        font.setBold(True)
        p.setFont(font)
        p.setPen(text)
        p.drawText(QRectF(0, 0, self.MARGIN - 5, self.height() + 6), Qt.AlignmentFlag.AlignVCenter
                   | Qt.AlignmentFlag.AlignRight, "0")
        p.drawText(QRectF(self.width() - self.MARGIN + 5, 0, self.MARGIN, self.height() + 6),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "1")
        font.setPixelSize(12)
        font.setBold(False)
        p.setFont(font)
        if not self.inner:                        # a single span: so it does not look as if something were missing
            p.setPen(faint)
            p.drawText(QRectF(self._x(0) + 10, 0, self._x(1) - self._x(0) - 20, y - 4),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                       tr('No inner knots: with so few points for its degree, the curve is a single span. '
                          'Double-click here to add one.'))
        times: dict[float, int] = {}
        for u in self.inner:
            times[round(u, 6)] = times.get(round(u, 6), 0) + 1
        for i, u in enumerate(self.inner):
            checked = i in (self._taken, self._over)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent if checked else text)
            x = self._x(u)
            p.drawPolygon([QPointF(x, y - 7), QPointF(x + 5, y), QPointF(x, y + 7), QPointF(x - 5, y)])   # rombo
            if times[round(u, 6)] > 1:                 # repeated: how many times (a break)
                p.setPen(text)
                p.drawText(QRectF(x + 5, 0, 30, y - 4), Qt.AlignmentFlag.AlignBottom, f"×{times[round(u, 6)]}")
            if checked:
                p.setPen(text)
                p.drawText(QRectF(x - 40, 0, 80, y - 6), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                           comma(f"{u:.3f}"))
        p.end()

    def mousePressEvent(self, event) -> None:
        i = self._nearest(event.position().x())
        if event.button() == Qt.MouseButton.RightButton and i is not None:
            menu = QMenu(self)
            repeat = menu.addAction(tr('Repeat this knot (a kink)'))
            repeat.setEnabled(self.inner.count(self.inner[i]) < self.degree)
            remove = menu.addAction(tr('Remove this knot (and a control point)'))
            chosen = menu.exec(event.globalPosition().toPoint())
            if chosen is repeat:
                self.insert.emit(self.inner[i])
            elif chosen is remove:
                self.remove.emit(i)
            return
        if event.button() == Qt.MouseButton.LeftButton and i is not None:
            self._taken = i
            self.update()

    def mouseMoveEvent(self, event) -> None:
        x = event.position().x()
        if self._taken is not None:                   # between its neighbours (or on top of one: a break)
            i = self._taken
            under = self.inner[i - 1] if i > 0 else 0.0
            height = self.inner[i + 1] if i < len(self.inner) - 1 else 1.0
            self.inner[i] = round(float(np.clip(self._u(x), under + 1e-3, height - 1e-3)), 4)
            self.moved.emit(list(self.inner), False)
            self.over.emit(self.inner[i])
            self.update()
            return
        i = self._nearest(x)
        if i != self._over:
            self._over = i
            self.over.emit(None if i is None else self.inner[i])
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._taken is not None:
            self._taken = None
            self.moved.emit(list(self.inner), True)
            self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._nearest(event.position().x()) is None:
            u = self._u(event.position().x())
            if 0.0 < u < 1.0:
                self.insert.emit(round(u, 4))

    def leaveEvent(self, _event) -> None:
        if self._over is not None:
            self._over = None
            self.over.emit(None)
            self.update()


class BarDrawing(QFrame):
    """The curve editor's bar: over the 3D view while the points of a curve are edited. The tools (Select, Add,
    Delete, Weight), the grid and the snapping, whether the curve is closed, and finish. From which side it draws is said
    by the view itself (its «Views» menu)."""

    tool = Signal(str)              # "select", "add", "delete" or "weight"
    grid_changed = Signal(float, bool)
    closed = Signal(bool)
    curvature = Signal(bool)
    knots = Signal(bool)
    rest = Signal(bool)
    finish = Signal()

    #: The tools: (value, text, tooltip on the button, help in the bar while it is chosen).
    TOOLS = (
        ("select", 'Select', 'Pick points and move them (V)',
         'Drag a point: moves the selected ones (holding Shift: in line) · Shift + click: add or remove · '
         'Ctrl + drag: a box · C: corner'),
        ("add", 'Add', 'Place new points (A)',
         'Click: a point at the end · on the control line: in that segment · Shift + click: in line with the one '
         'before · Alt + drag: up or down · C: corner'),
        ("pen", 'Pen', 'Draw with anchors the curve passes through and handles that shape it (P)',
         'Click: a corner anchor · click and drag: smooth (Alt: breaks the handle) · click the first one: closes · '
         'click on the curve: one more anchor · Alt + click an anchor: converts it'),
        ("delete", 'Delete', 'Remove points with a click (X)', 'Click a point: removes it (on a handle: retracts it)'),
        ("weight", 'Weight', 'Change how much each point pulls, by dragging (W)',
         'Drag a point up: pulls the curve more · down: less'),
    )

    def __init__(self, parent=None):
        from .widgets import Switch, Segmented
        super().__init__(parent)
        self.setObjectName("drawing_bar")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        self.title = QLabel()
        self.title.setProperty("role", "secondary")
        row.addWidget(self.title)
        self.tools = Segmented([(v, t, None) for v, t, _, _ in self.TOOLS], "add",
                                       help_texts={v: a for v, _, a, _ in self.TOOLS})
        self.tools.change.connect(self.tool.emit)
        row.addWidget(self.tools)
        label = QLabel(tr('Drawing grid'))
        label.setProperty("role", "secondary")
        row.addWidget(label)
        self.steps = QComboBox()
        self.steps.setEditable(True)
        self.steps.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for value in STEPS:
            self.steps.addItem(f"{value:g} m", value)
        self.steps.setMinimumContentsLength(6)
        self.steps.setToolTip(tr('The spacing of the drawing grid, in metres: pick one or type your own'))
        row.addWidget(self.steps)
        self.setting = Switch(tr('Snap'), True)
        self.setting.setToolTip(tr('Points land only on the grid crossings. Holding Ctrl inverts it.'))
        row.addWidget(self.setting)
        self.closing = Switch(tr('Closed'), False)
        self.closing.setToolTip(tr('The curve goes around and returns to the first point'))
        self.closing.toggled.connect(self.closed.emit)
        row.addWidget(self.closing)
        # What is seen besides the curve, in a menu (the bar has no room for more switches).
        display = QPushButton(tr('Show'))
        display.setToolTip(tr('What else is shown while editing: the curvature comb, the knots, the rest of the project'))
        menu = QMenu(display)
        display.setMenu(menu)

        def option(text, help, key, default, signal):
            a = menu.addAction(tr(text))
            a.setCheckable(True)
            a.setChecked(QSettings().value(key, default, type=bool))
            a.setToolTip(tr(help))
            a.toggled.connect(lambda yes: QSettings().setValue(key, bool(yes)))
            a.toggled.connect(signal.emit)
            return a
        menu.setToolTipsVisible(True)
        self.comb = option('Curvature', 'The curvature comb: longer hairs where the curve bends more; a really smooth'
                                        ' curve has a comb edge without jumps', "drawing/curvature", False, self.curvature)
        self.see_nodes = option('Knots', 'The curve knots on a ruler from 0 to 1: drag one to move it (the curve '
                                         'switches to «by hand» knots); double-click adds one; right-click repeats it',
                                "drawing/knots", False, self.knots)
        self.see_rest = option('The rest', 'Also show the rest of the project, faded, as a reference (it cannot be '
                                           'touched). Off: only the curve being edited.', "drawing/rest", False, self.rest)
        row.addWidget(display)
        row.addStretch(1)
        self.help_text = ""                      # what the tool does: it goes in the status bar
        ready = QPushButton(tr('Finish'))
        ready.setDefault(True)
        ready.setToolTip(tr('Finish editing the curve (Enter or Esc)'))
        ready.clicked.connect(self.finish.emit)
        row.addWidget(ready)
        self.steps.activated.connect(self._warn_grid)
        self.steps.lineEdit().editingFinished.connect(self._warn_grid)
        self.setting.toggled.connect(self._warn_grid)
        self.hide()

    def display(self, node: str, closed: bool | None, with_weights: bool, pen: bool = False,
                mesh: bool = False) -> None:
        """`closed`: None if the curve does not have that option. `mesh`: the vertices of a mesh (Edit mesh): only
        Select (they are moved, never added or removed)."""
        self.title.setText(tr('Editing «{node}»').format(node=node))
        self.put_grid(*grid())
        self.closing.setVisible(closed is not None and not mesh)
        self.closing.blockSignals(True)
        self.closing.setChecked(bool(closed))
        self.closing.blockSignals(False)
        self.tools.display_option("weight", with_weights and not pen and not mesh)
        self.tools.display_option("add", not pen and not mesh)
        self.tools.display_option("pen", pen and not mesh)
        self.tools.display_option("delete", not mesh)
        self.tools.setVisible(not mesh)              # a mesh has a single tool: no buttons to choose from
        self.see_nodes.setVisible(with_weights and not pen and not mesh)   # the knots: only with control points
        self.comb.setVisible(not mesh)
        self.show()

    def put_tool(self, tool: str) -> None:
        """The chosen tool (also with its key, in the view), with its help."""
        self.tools.put(tool)
        help_texts = {v: a for v, _, _, a in self.TOOLS}
        self.help_text = tr(help_texts.get(tool, "")) + " · " + tr('double click a point: its exact coordinates') \
            + " · " + tr('right-click a point: more')

    def put_grid(self, step: float, adjust: bool) -> None:
        for control in (self.steps, self.setting):
            control.blockSignals(True)
        self.steps.setCurrentText(f"{step:g} m")
        self.setting.setChecked(adjust)
        for control in (self.steps, self.setting):
            control.blockSignals(False)

    def _warn_grid(self, *_) -> None:
        text = self.steps.currentText().replace("m", "").replace(",", ".").strip()
        try:
            value = float(text)
        except ValueError:
            value = 0.0
        if not 0.001 <= value <= 1000:               # something that is not a step: back to the previous one
            self.steps.setCurrentText(f"{grid()[0]:g} m")
            return
        self.steps.setCurrentText(f"{value:g} m")
        self.grid_changed.emit(value, self.setting.isChecked())
