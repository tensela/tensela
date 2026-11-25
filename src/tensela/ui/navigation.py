"""Moving around the 3D view (Delivery 5): orbiting around what is under the pointer.

VTK's style turns around the centre of the view; this navigator turns around the point of the model that is under
the mouse, in *turntable* mode (the Z axis always vertical), and zooms towards the pointer. It does so with the
buttons of each scheme (the others match the programs people already know, for compatibility):

- **Tensela:** left orbits, Shift + left or middle pans, right zooms.
- **Blender:** middle orbits, Shift + middle pans, Ctrl + middle zooms.
- **Rhino:** right orbits, Shift + right pans, Ctrl + right zooms.
- **SketchUp:** middle orbits, Shift + middle pans.

In all of them, the wheel zooms towards the pointer (or towards the centre, in Preferences). A right click without
dragging opens the menu (`menu`), and the clicks on the axes gizmo are its own.
"""
from __future__ import annotations

import numpy as np
import vtk
from PySide6.QtCore import QEvent, QObject, Qt, Signal

LEFT, MIDDLE, RIGHT = Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton
#: (button, modifier) → what dragging does. Modifier: "" , "shift" or "ctrl".
SCHEMES = {
    "tensela": {(LEFT, ""): "orbit", (LEFT, "shift"): "pan", (MIDDLE, ""): "pan",
                    (RIGHT, ""): "zoom"},
    "blender": {(MIDDLE, ""): "orbit", (MIDDLE, "shift"): "pan", (MIDDLE, "ctrl"): "zoom"},
    "rhino": {(RIGHT, ""): "orbit", (RIGHT, "shift"): "pan", (RIGHT, "ctrl"): "zoom"},
    "sketchup": {(MIDDLE, ""): "orbit", (MIDDLE, "shift"): "pan"},
}
NAMES = {"tensela": "Tensela", "blender": "Blender", "rhino": "Rhino", "sketchup": "SketchUp"}
HELP_TEXTS = {
    "tensela": 'Left button: orbit · Shift + left or middle: pan · right or wheel: zoom',
    "blender": 'Middle button: orbit · Shift + middle: pan · Ctrl + middle or wheel: zoom',
    "rhino": 'Right button: orbit · Shift + right: pan · Ctrl + right or wheel: zoom',
    "sketchup": 'Middle button: orbit · Shift + middle: pan · wheel: zoom',
}
DEGREES_BY_PIXEL = 0.35
STEP_WHEEL = 0.85            # each step of the wheel zooms to 85 % of the distance


def _rotate(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """Rodrigues: `v` turned by `angle` (radians) about `axis` (unit)."""
    c, s = np.cos(angle), np.sin(angle)
    return v * c + np.cross(axis, v) * s + axis * np.dot(axis, v) * (1 - c)


class Browser(QObject):
    """Moves the camera of a pyvista plotter (QtInteractor) with the mouse, turntable style."""

    menu = Signal(object)        # a right click without dragging: the point on the screen

    def __init__(self, plotter, gizmo=None, parent=None):
        super().__init__(parent)
        self.plotter = plotter
        self.gizmo = gizmo
        self.scheme = SCHEMES["tensela"]
        self._action = None       # orbit, pan or zoom (while dragging)
        self._pivot = None
        self._last = None
        self._right_click = None
        self._moved = False
        self._finder = vtk.vtkCellPicker()
        self._finder.SetTolerance(0.0005)
        plotter.interactor.installEventFilter(self)

    def put_scheme(self, name: str) -> None:
        self.scheme = SCHEMES.get(name, SCHEMES["tensela"])

    #: Zooming goes towards the pointer (Preferences → Interaction); if not, towards the centre of the view.
    towards_pointer = True

    # --- Points of the screen and of the model -------------------------------------------

    def _screen(self, pos) -> tuple[float, float]:
        """A point of the widget (Qt) in VTK coordinates (its pixels, and from below).

        The ratio is taken from the real sizes: pyvista draws at its own scale (it may not be that of the screen: 2 on a
        1.25 screen).
        """
        w = self.plotter.interactor
        width, height = self.plotter.ren_win.GetSize()
        sx, sy = width / max(w.width(), 1), height / max(w.height(), 1)
        return pos.x() * sx, height - pos.y() * sy

    def _point_under(self, pos):
        """The point of the model under the pointer: a ray up to the first face; None if it is the background.

        (The depth of the image does not serve: with the edge smoothing and the Qt widget, it cannot be read.)
        """
        x, y = self._screen(pos)
        if self._finder.Pick(x, y, 0, self.plotter.renderer):
            return np.array(self._finder.GetPickPosition())
        return None

    def _zoom_anchor(self, pos):
        """Where zooming goes: the point of the model under the pointer or, over the background, the point under it at
        the depth of the centre of the view. None (the centre) if the preference says so."""
        if not self.towards_pointer:
            return None
        hit = self._point_under(pos)
        if hit is not None:
            return hit
        ren = self.plotter.renderer
        ren.SetWorldPoint(*self._camera()[1], 1.0)
        ren.WorldToDisplay()
        x, y = self._screen(pos)
        ren.SetDisplayPoint(x, y, ren.GetDisplayPoint()[2])
        ren.DisplayToWorld()
        w = ren.GetWorldPoint()
        return np.array(w[:3]) / (w[3] or 1.0)

    def _over_gizmo(self, pos) -> bool:
        if self.gizmo is None or not self.gizmo.GetEnabled():
            return False
        r = self.gizmo.GetRepresentation()
        x, y = self._screen(pos)
        width, height = self.plotter.renderer.GetSize()
        side, margin = r.GetSize(), r.GetPadding()
        return x >= width - side[0] - margin[0] and y >= height - side[1] - margin[1]

    def _look_from__gizmo(self, pos) -> None:
        """A click on X, Y or Z (or on their opposites) of the gizmo: the view looks from that side."""
        # VTK's picker misses with the Qt widget (like the depth): the axis tip closest to the click is
        # searched by hand, among those that fall under it (the frontmost if there are two).
        r = self.gizmo.GetRepresentation()
        ren = r.GetRenderer()
        x, y = self._screen(pos)
        length = r.GetTotalLength()
        tips = []
        for axis in range(3):
            for opposite, sign in ((0, 1.0), (1, -1.0)):
                point = [0.0, 0.0, 0.0]
                point[axis] = sign * length
                ren.SetWorldPoint(*point, 1.0)
                ren.WorldToDisplay()
                px, py, pz = ren.GetDisplayPoint()
                tips.append((px, py, pz, axis, opposite))
        ren.SetWorldPoint(0.0, 0.0, 0.0, 1.0)
        ren.WorldToDisplay()
        cx, cy, _ = ren.GetDisplayPoint()
        radius = r.GetNormalizedHandleDia() * 0.5 * max(abs(p[0] - cx) + abs(p[1] - cy) for p in tips)
        near = [p for p in tips if np.hypot(p[0] - x, p[1] - y) <= radius]
        if not near:
            return
        _, _, _, axis, opposite = min(near, key=lambda p: p[2])
        towards = np.zeros(3)
        towards[axis] = -1.0 if opposite == 0 else 1.0              # it looks from the positive side towards the centre
        above = np.array([0.0, 1.0, 0.0]) if axis == 2 else np.array([0.0, 0.0, 1.0])
        if self.on_look is not None:
            self.on_look(towards, above)

    #: What makes the view look from an axis: f(where it looks, what is up). The Viewer sets it.
    on_look = None
    #: What reports that the view was turned by hand (it stops being «Front», «Plan»…). The Viewer sets it.
    on_orbit = None
    on_moving = None

    def _camera(self):
        c = self.plotter.camera
        return np.array(c.position, float), np.array(c.focal_point, float), np.array(c.up, float)

    def _put(self, position, focus, above) -> None:
        c = self.plotter.camera
        c.position, c.focal_point, c.up = tuple(position), tuple(focus), tuple(above)
        self.plotter.renderer.ResetCameraClippingRange()
        self._moving()
        self.plotter.render()

    def _moving(self) -> None:
        """The camera moves: the view can paint lighter until it stops (see Viewer._moving)."""
        if self.on_moving is not None:
            self.on_moving()

    # --- Moves ----------------------------------------------------------------------

    def orbit(self, dx: float, dy: float, pivot) -> None:
        """Turntable: about the Z (vertical) axis and the horizontal axis of the view, through the pivot."""
        p, f, u = self._camera()
        pivot = f if pivot is None else pivot
        z = np.array([0.0, 0.0, 1.0])
        a = -np.radians(dx * DEGREES_BY_PIXEL)
        p, f, u = (pivot + _rotate(p - pivot, z, a), pivot + _rotate(f - pivot, z, a), _rotate(u, z, a))
        looks = f - p
        right = np.cross(looks, u)
        right /= np.linalg.norm(right) or 1.0
        b = -np.radians(dy * DEGREES_BY_PIXEL)
        new = _rotate(looks, right, b)
        if abs(np.dot(new / np.linalg.norm(new), z)) < 0.995:          # without going past the vertical
            p, f = pivot + _rotate(p - pivot, right, b), pivot + _rotate(f - pivot, right, b)
            u = _rotate(u, right, b)
        self._put(p, f, u)

    def pan(self, from_, to) -> None:
        """The grabbed point follows the pointer."""
        p, f, u = self._camera()
        ren = self.plotter.renderer
        ren.SetWorldPoint(*f, 1.0)
        ren.WorldToDisplay()
        zf = ren.GetDisplayPoint()[2]
        world = []
        for pos in (from_, to):
            x, y = self._screen(pos)
            ren.SetDisplayPoint(x, y, zf)
            ren.DisplayToWorld()
            w = ren.GetWorldPoint()
            world.append(np.array(w[:3]) / (w[3] or 1.0))
        d = world[0] - world[1]
        self._put(p + d, f + d, u)

    def approach(self, factor: float, towards=None) -> None:
        """Zooms in (factor < 1) or out towards a point (the one under the pointer)."""
        p, f, u = self._camera()
        c = self.plotter.camera
        if c.parallel_projection:
            c.parallel_scale = c.parallel_scale * factor
            if towards is not None:            # what is under the pointer stays under it
                looks = (f - p) / (np.linalg.norm(f - p) or 1.0)
                across = np.asarray(towards, float) - f
                shift = (across - np.dot(across, looks) * looks) * (1.0 - factor)
                self._put(p + shift, f + shift, u)
                return
            self._moving()
            self.plotter.render()
            return
        towards = f if towards is None else towards
        new = towards + (p - towards) * factor
        if np.linalg.norm(new - f) < 1e-6:
            return
        self._put(new, towards + (f - towards) * factor, u)

    # --- Mouse ------------------------------------------------------------------------

    def _what_makes(self, event) -> str | None:
        mods = event.modifiers()
        mod = "shift" if mods & Qt.KeyboardModifier.ShiftModifier else (
            "ctrl" if mods & Qt.KeyboardModifier.ControlModifier else "")
        return self.scheme.get((event.button(), mod)) or (
            self.scheme.get((event.button(), "")) if mod else None)

    def eventFilter(self, object_, event) -> bool:
        t = event.type()
        if t == QEvent.Type.MouseButtonPress:
            if event.button() == RIGHT:
                self._right_click, self._moved = event.position(), False
            if self._over_gizmo(event.position()):
                self._click_gizmo = event.position()           # on releasing without dragging: look from that axis
                return True
            action = self._what_makes(event)
            if action is None:
                return True                  # no free button moves the view the VTK way
            self._action, self._last = action, event.position()
            self._pivot = (self._point_under(event.position()) if action == "orbit" else
                           self._zoom_anchor(event.position()) if action == "zoom" else None)
            if action == "pan":                # the closed hand while panning, as in the nodes
                self._cursor_before = object_.cursor()
                object_.setCursor(Qt.CursorShape.ClosedHandCursor)
            return True
        if t == QEvent.Type.MouseMove and self._action is not None:
            pos = event.position()
            dx, dy = pos.x() - self._last.x(), pos.y() - self._last.y()
            if abs(dx) + abs(dy) > 0:
                self._moved = True
            if self._action == "orbit":
                self.orbit(dx, dy, self._pivot)
                if self.on_orbit is not None and abs(dx) + abs(dy) > 0:
                    self.on_orbit()
            elif self._action == "pan":
                self.pan(self._last, pos)
            elif self._action == "zoom":
                self.approach(1.0 + dy * 0.01, self._pivot)
            self._last = pos
            return True
        if t == QEvent.Type.MouseButtonRelease and getattr(self, "_click_gizmo", None) is not None:
            still = (event.position() - self._click_gizmo).manhattanLength() < 5
            self._click_gizmo = None
            if still:
                self._look_from__gizmo(event.position())
            return True
        if t == QEvent.Type.MouseButtonRelease:
            had = self._action is not None
            if self._action == "pan":
                object_.setCursor(getattr(self, "_cursor_before", None) or Qt.CursorShape.ArrowCursor)
            self._action = None
            if event.button() == RIGHT and self._right_click is not None:
                still = (event.position() - self._right_click).manhattanLength() < 5 and not self._moved
                self._right_click = None
                if still:
                    self.menu.emit(event.globalPosition().toPoint())
                    return True
            return had
        if t == QEvent.Type.MouseButtonDblClick:
            return not self._over_gizmo(event.position())
        if t == QEvent.Type.Wheel:
            steps = event.angleDelta().y() / 120
            if steps:
                self.approach(STEP_WHEEL ** steps, self._zoom_anchor(event.position()))
            return True
        return False
