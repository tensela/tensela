"""Tensela's components (Delivery 5, step 2): less text, clearer.

- :class:`Segmented`: two to five options in a pill (Light | Dark; 3D | 2D).
- :class:`Switch`: yes / no, instead of a check box.
- :class:`Cards`: choosing among options with a drawing (a thumbnail or an icon).
- :func:`button_icon`: an icon-only button; its text goes in the tooltip.
- :class:`ButtonColour`: a colour sample that opens the picker.
- :class:`Panel`: a card of the window, with its header (icon, title, actions).
- :class:`TableDataItems`: the data of each node, as a table (exported to CSV).

All take their colours from the theme (ui/theme.py), when created: the panels and the dialogs are rebuilt on
opening, so they follow the theme set.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QColorDialog, QDockWidget, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QMenu, QSizePolicy, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..language import tr
from . import icons as icons, theme as theme


def _c(key: str, yes_no_there_is: str) -> str:
    return theme.color(key, yes_no_there_is)


class Segmented(QFrame):
    """A few options in a pill; one chosen.

    `options`: [(value, text, icon or None)]. With an icon and without text, the text goes in the tooltip.
    """

    change = Signal(object)

    def __init__(self, options, value=None, parent=None, help_texts: dict | None = None):
        super().__init__(parent)
        self.setObjectName("segmented")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._values = []
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        for i, (v, text, icon) in enumerate(options):
            b = QToolButton()
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setText(tr(text or ""))
            if icon:
                b.setIcon(icons.icon(icon, _c("text", "#ecedf2"), 16))
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text
                                     else Qt.ToolButtonStyle.ToolButtonIconOnly)
            b.setToolTip(tr((help_texts or {}).get(v, "" if text else str(v))))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._group.addButton(b, i)
            self._values.append(v)
            row.addWidget(b)
        self.put(value if value in self._values else self._values[0])
        self._group.idClicked.connect(lambda i: self.change.emit(self._values[i]))

    def value(self):
        return self._values[self._group.checkedId()]

    def put(self, value) -> None:
        if value in self._values:
            self._group.button(self._values.index(value)).setChecked(True)

    def display_option(self, value, yes: bool) -> None:
        """Shows or hides one of the options."""
        if value in self._values:
            self._group.button(self._values.index(value)).setVisible(yes)


class Switch(QAbstractButton):
    """Yes / no, with its text on the right."""

    WIDTH, HEIGHT = 34, 20

    def __init__(self, text: str = "", value: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(value)
        self.setText(tr(text))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        width = self.WIDTH + (8 + self.fontMetrics().horizontalAdvance(self.text()) if self.text() else 0)
        return QSize(width, max(self.HEIGHT + 4, self.fontMetrics().height() + 4))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - self.HEIGHT) / 2
        hint = QRectF(0.5, y + 0.5, self.WIDTH - 1, self.HEIGHT - 1)
        on = self.isChecked()
        off = not self.isEnabled()
        p.setPen(Qt.PenStyle.NoPen)
        if off:
            p.setBrush(QColor(_c("disabled", "#5b6070")))
        elif on:
            p.setBrush(QColor(_c("accent", "#8a7dff")))
        else:
            # Off: the text colour, faint and with its border (it shows on any background, also on a bar).
            faint, edge = QColor(_c("text", "#ecedf2")), QColor(_c("text", "#ecedf2"))
            faint.setAlpha(55)
            edge.setAlpha(120)
            p.setBrush(faint)
            p.setPen(QPen(edge, 1))
        p.drawRoundedRect(hint, self.HEIGHT / 2, self.HEIGHT / 2)
        p.setPen(Qt.PenStyle.NoPen)
        r = self.HEIGHT - 6
        x = self.WIDTH - r - 3 if on else 3
        p.setBrush(QColor(_c("on_accent", "#ffffff") if on else _c("text", "#ecedf2")))
        p.drawEllipse(QRectF(x, y + 3, r, r))
        if self.text():
            p.setPen(QColor(_c("text", self.palette().windowText().color().name()) if not off
                            else _c("disabled", "#5b6070")))
            p.drawText(QRectF(self.WIDTH + 8, 0, self.width() - self.WIDTH - 8, self.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        p.end()


class Cards(QWidget):
    """Choosing with a drawing: a grid of cards, one chosen.

    `options`: [(value, text, drawing)], where drawing is a QPixmap (a thumbnail) or the name of an icon.
    """

    change = Signal(object)

    def __init__(self, options, value=None, columns: int = 3, side: int = 64, parent=None,
                 help_texts: dict | None = None):
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._values = []
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        for i, (v, text, drawing) in enumerate(options):
            b = QToolButton()
            b.setObjectName("card")
            b.setCheckable(True)
            b.setText(tr(text))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            if isinstance(drawing, QPixmap):
                b.setIcon(QIcon(drawing))
                b.setIconSize(QSize(side * drawing.width() // max(1, drawing.height()), side))
            elif drawing:
                b.setIcon(icons.icon(drawing, _c("text", "#ecedf2"), side))
                b.setIconSize(QSize(side, side))
            b.setToolTip(tr((help_texts or {}).get(v, "")))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._group.addButton(b, i)
            self._values.append(v)
            grid.addWidget(b, i // columns, i % columns)
        self.put(value if value in self._values else self._values[0])
        self._group.idClicked.connect(lambda i: self.change.emit(self._values[i]))

    def value(self):
        return self._values[self._group.checkedId()]

    def put(self, value) -> None:
        if value in self._values:
            self._group.button(self._values.index(value)).setChecked(True)


def button_icon(icon: str, help: str, checkable: bool = False, parent=None) -> QToolButton:
    """An icon-only button; what it does is read in the tooltip (on hovering)."""
    b = QToolButton(parent)
    b.setObjectName("icon_button")
    b.setIcon(icons.icon(icon, _c("text_2", "#9ca1b0"), 16, _c("disabled", "#5b6070")))
    b.setIconSize(QSize(16, 16))
    b.setToolTip(tr(help))
    b.setCheckable(checkable)
    # Active: the icon, in the colour readable on the accent (the button's background becomes the accent).
    normal = icons.icon(icon, _c("text_2", "#9ca1b0"), 16, _c("disabled", "#5b6070"))
    active = icons.icon(icon, _c("on_accent", "#0e0f13"), 16)
    b.toggled.connect(lambda yes: b.setIcon(active if yes else normal))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def set_icon(b: QToolButton, icon: str, active: bool = False) -> None:
    """Another icon for a button of button_icon; `active`, on the accent colour (something going on: playing)."""
    b.setIcon(icons.icon(icon, _c("on_accent", "#0e0f13"), 16) if active
              else icons.icon(icon, _c("text_2", "#9ca1b0"), 16, _c("disabled", "#5b6070")))
    if bool(b.property("active")) != active:
        b.setProperty("active", active)
        b.style().unpolish(b)
        b.style().polish(b)


class ActionTile(QFrame):
    """The main thing a node lets one do (edit its curve, move its supports, watch it move), as a tile: an icon in a
    soft square, what it does, and below a line of how it is now; small buttons on the right (put everything back,
    stop). The whole tile is the button: a click, Enter or the space bar. `active`: it is going on now (the tile in the
    accent colour, and its title says how to finish)."""

    clicked = Signal()

    def __init__(self, icon: str, title: str, detail: str = "", help: str = "", active: bool = False,
                 enabled: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("action_tile")
        self.setProperty("active", active)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr(help))
        self.setEnabled(enabled)
        self.setAccessibleName(tr(title))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 8, 8)
        outer.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(10)
        outer.addLayout(row)
        self._outer = outer
        badge = QLabel()
        badge.setObjectName("action_badge")
        badge.setProperty("active", active)
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        colour = _c("on_accent", "#0e0f13") if active else _c("accent", "#8a7dff")
        badge.setPixmap(icons.pixmap(icon, colour if enabled else _c("disabled", "#5b6070"), 18,
                                     self.devicePixelRatioF()))
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.title = QLabel(tr(title))
        self.title.setProperty("role", "tile_title")
        self.title.setWordWrap(True)
        texts.addWidget(self.title)
        self.detail = QLabel(detail)
        self.detail.setProperty("role", "small")
        self.detail.setWordWrap(True)
        self.detail.setVisible(bool(detail))
        texts.addWidget(self.detail)
        texts.addStretch(1)                              # title and detail together at the top, however tall
        row.addLayout(texts, 1)
        for label in (self.title, self.detail):        # the texts wrap: the tile never widens the panel
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setMinimumWidth(40)
        self._buttons = row

    def add_actions(self, *buttons: QWidget) -> None:
        """Buttons in a row of their own, below the title (pause and stop, while it plays): real buttons, each
        with its icon and its word."""
        actions = QHBoxLayout()
        actions.setSpacing(6)
        for b in buttons:
            actions.addWidget(b, 1)
        self._outer.addLayout(actions)

    def add_button(self, button: QWidget) -> None:
        """A small button on the right (it does its own thing: the tile's click does not reach it)."""
        self._buttons.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled() and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.isEnabled():
            self.clicked.emit()
            return
        super().keyPressEvent(event)


def tile_button(icon: str, text: str, help: str = "") -> QToolButton:
    """A button inside an action tile: icon and word, with its own background and border, so it reads as a button."""
    b = QToolButton()
    b.setObjectName("tile_button")
    b.setText(tr(text))
    b.setIcon(icons.icon(icon, _c("text", "#ecedf2"), 14))
    b.setIconSize(QSize(14, 14))
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    b.setToolTip(tr(help or text))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def tiles(items: list[QWidget], columns: int = 2) -> QWidget:
    """Action tiles side by side (two per row, like a bento box); a lone one takes the whole row."""
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 2, 0, 2)
    grid.setSpacing(8)
    for i, item in enumerate(items):
        last_alone = i == len(items) - 1 and i % columns == 0
        grid.addWidget(item, i // columns, i % columns, 1, columns if last_alone else 1)
    for c in range(columns):
        grid.setColumnStretch(c, 1)
    return box


class ButtonColor(QToolButton):
    """A round colour sample; on clicking, the colour picker."""

    chosen = Signal(str)

    def __init__(self, color: str, help: str = 'Change the colour', title: str = 'Colour', parent=None):
        super().__init__(parent)
        self.setObjectName("icon_button")
        self._color, self._title = color, title
        self.setToolTip(tr(help))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(28, 28)
        self.clicked.connect(self._pick)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, self._title)
        if c.isValid():
            self.chosen.emit(c.name())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(_c("border", "#2a2d36")), 1.5))
        p.setBrush(QColor(self._color))
        p.drawEllipse(QRectF(6, 6, self.width() - 12, self.height() - 12))
        p.end()


class Panel(QFrame):
    """A card of the window (bento): a header with title and actions; below, its content."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layer = QVBoxLayout(self)
        layer.setContentsMargins(14, 10, 12, 12)
        layer.setSpacing(8)
        # The header is a widget of its own: in a dockable panel it becomes its bar (it is dragged by it).
        self.header = QWidget()
        self.header.setObjectName("panel_header")
        head = QHBoxLayout(self.header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self.title = QLabel(tr(title))
        self.title.setProperty("role", "title")
        head.addWidget(self.title)
        head.addStretch(1)
        self.action_items = QHBoxLayout()
        self.action_items.setSpacing(2)
        head.addLayout(self.action_items)
        self.fixed = QHBoxLayout()          # float and close, always at the end
        self.fixed.setSpacing(2)
        head.addLayout(self.fixed)
        layer.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        layer.addLayout(self.body, 1)

    def action(self, button: QWidget) -> QWidget:
        self.action_items.addWidget(button)
        return button


class _WindowPanel(QWidget):
    """The separate window of a panel taken out: a utility window of Tensela, with the desktop's bar.

    The desktop moves and resizes it (in GNOME, with Wayland, a frameless window could not be moved); it stays above
    Tensela (not above other programs). On closing it, the panel closes.
    """

    def __init__(self, title: str, on_dismiss, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowTitleHint
                         | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.setObjectName("panel_window")
        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._on_dismiss = on_dismiss
        layer = QVBoxLayout(self)
        layer.setContentsMargins(0, 0, 0, 0)
        layer.setSpacing(0)

    def closeEvent(self, event) -> None:
        event.ignore()
        self._on_dismiss()


def _in_x11() -> bool:
    return QGuiApplication.platformName() == "xcb"


class DockablePanel(QDockWidget):
    """A :class:`Panel` that moves, groups with others, goes to another window or closes.

    On X11 (also XWayland: window.pick_platform) it is dragged by its header: to a side, onto another panel (in tabs) or
    outside, where it is a window with the desktop's frame. On Wayland it cannot be dragged (Qt does not place windows
    there) and the «⋯» menu is used; «Undock» puts it in a separate window. In both, closing the separate window closes
    the panel (it comes back, docked, with View → Panels); the arrow brings it back. `key` names it to remember where it
    was left.
    """

    SIDES = (('Left', Qt.DockWidgetArea.LeftDockWidgetArea), ('Right', Qt.DockWidgetArea.RightDockWidgetArea),
             ('Below', Qt.DockWidgetArea.BottomDockWidgetArea))

    def __init__(self, panel: Panel, key: str, parent=None):
        super().__init__(panel.title.text(), parent)
        self.setObjectName(f"panel_{key}")
        self.panel = panel
        self._native = _in_x11()
        features = QDockWidget.DockWidgetFeature.DockWidgetClosable
        if self._native:
            features |= QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        self.setFeatures(features)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setMinimumSize(220, 140)        # so that on dropping it on a new side it is not squashed (invisible)
        self._window: _WindowPanel | None = None
        self._with_frame = False              # X11: floating, with the desktop's frame and the header inside
        panel.fixed.addSpacing(6)
        self._more = button_icon("mas", tr('Move, group or pop out'))
        panel.fixed.addWidget(self._more)
        self._more.clicked.connect(lambda: self.menu().exec(self._more.mapToGlobal(self._more.rect().bottomLeft())))
        self._take_out = button_icon("undock", tr('Move to a separate window'))
        panel.fixed.addWidget(self._take_out)
        self._take_out.clicked.connect(lambda: self.return_() if self.outside() else self.take_out())
        dismiss = button_icon("close", tr('Close (comes back in View → Panels)'))
        panel.fixed.addWidget(dismiss)
        dismiss.clicked.connect(lambda: (self.return_(), self.close()))
        self._dismiss = dismiss
        bar = panel.header
        panel.layout().removeWidget(bar)
        bar.setObjectName("panel_bar")
        bar.layout().setContentsMargins(14, 8, 10, 6)
        self.setTitleBarWidget(bar)
        panel.setObjectName("panel_body")
        panel.layout().setContentsMargins(12, 4, 12, 12)
        self.setWidget(panel)
        bar.installEventFilter(self)
        self._bar = bar
        self.topLevelChanged.connect(self._on_float)
        # View → Panels with the panel outside: it goes back to its place.
        self.toggleViewAction().triggered.connect(lambda: self.return_() if self.outside() else None)

    # --- Move and group -------------------------------------------------------------

    def menu(self) -> QMenu:
        menu = QMenu(self)
        window = self.parent()
        move = menu.addMenu(tr('Move to'))
        for name, side in self.SIDES:
            move.addAction(tr(name), lambda side=side: self.move_a(side))
        others = [p for p in window.findChildren(DockablePanel)
                 if p is not self and p.isVisible() and not p.outside()] if window else []
        group = menu.addMenu(tr('Group with'))
        for other in others:
            group.addAction(other.windowTitle(), lambda other=other: self.group_with(other))
        group.setEnabled(bool(others))
        separate = menu.addAction(tr('Ungroup'), self.separate)
        separate.setEnabled(bool(window and window.tabifiedDockWidgets(self)))
        menu.addSeparator()
        if self.outside():
            menu.addAction(tr('Back to its place in the window'), self.return_)
        else:
            menu.addAction(tr('Move to a separate window'), self.take_out)
        return menu

    def move_a(self, side) -> None:
        self.return_()
        self.parent().addDockWidget(side, self)
        self.show()

    def group_with(self, other: "PanelAcoplable") -> None:
        """In tabs with `other`, in its place."""
        self.return_()
        self.parent().tabifyDockWidget(other, self)
        self.show()
        self.raise_()

    def separate(self) -> None:
        """Out of its tab group: below the group, on the same side."""
        window = self.parent()
        group = [p for p in window.tabifiedDockWidgets(self) if p is not self]
        if not group:
            return
        side = window.dockWidgetArea(self)
        window.removeDockWidget(self)
        window.addDockWidget(side, self)
        vertical = side in (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea)
        window.splitDockWidget(group[0], self, Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal)
        self.show()

    # --- Take out to a separate window -----------------------------------------------------

    def outside(self) -> bool:
        return self.isFloating() if self._native else self._window is not None

    # X11: float with the desktop's frame ----------------------------------------------

    def _on_float(self, floats: bool) -> None:
        if not self._native:
            return
        if floats:
            self._wait_what_releases()        # while dragging, Qt moves the frameless window
        else:
            self._put_frame(False)
        self._mark(floats)

    def _wait_what_releases(self) -> None:
        if not self.isFloating():
            return
        if QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton:
            QTimer.singleShot(60, self._wait_what_releases)
            return
        self._put_frame(True)

    def _put_frame(self, yes: bool) -> None:
        """Floating: the desktop's frame (title, minimise, maximise, close) and the header inside; docked: the header as
        the panel's bar (it is dragged by it)."""
        if yes == self._with_frame:
            return
        self._with_frame = yes
        self.panel.title.setVisible(not yes)        # with a frame, the name is already in the desktop's title
        layer = self.panel.layout()
        if yes:
            geometry = self.geometry()
            # An empty bar: without it Qt draws its own (on X11 it does not leave the frame to the desktop).
            self.setTitleBarWidget(QWidget())
            layer.insertWidget(0, self._bar)
            self._bar.show()
            # A utility window of Tensela (not a «normal» one, which the desktop treats as another program and leaves
            # behind on clicking Tensela): always above Tensela, below other programs, minimised with it. It moves on
            # its own (also to another monitor): only the windows that block their parent are dragged with it.
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowTitleHint
                                | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMaximizeButtonHint
                                | Qt.WindowType.WindowCloseButtonHint)
            self.setGeometry(geometry)
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            layer.removeWidget(self._bar)
            empty = self.titleBarWidget()
            self.setTitleBarWidget(self._bar)
            self._bar.show()
            if empty is not None and empty is not self._bar:
                empty.deleteLater()

    def closeEvent(self, event) -> None:
        # Closing the separate window (the desktop's X) closes the panel; first it goes back to its place, so
        # that on opening it again (View → Panels) it appears docked where it was.
        if self._native and self.isFloating():
            self.return_()
        super().closeEvent(event)

    def take_out(self) -> None:
        """The panel, with its header, to a normal desktop window; the gap in the window closes."""
        if self._native:
            if not self.isFloating():
                size_ = self.size()
                self.setFloating(True)
                self.resize(max(size_.width(), 360), max(size_.height(), 280))
            self._put_frame(True)
            self.raise_()
            return
        if self.outside():
            self._window.raise_()
            return
        size_ = self.size()
        bar = self.titleBarWidget()
        self.setTitleBarWidget(QWidget())               # the header and the panel go; in their place, gaps
        panel = self.widget()
        self.setWidget(QWidget())
        main = self.parent().window() if self.parent() is not None else None
        self._window = _WindowPanel(self.windowTitle(), lambda: (self.return_(), self.close()), main)
        self._window.layout().addWidget(bar)
        self._window.layout().addWidget(panel, 1)
        for w in (bar, panel):
            w.show()
        self._mark(True)
        self.hide()
        self._window.resize(max(size_.width(), 360), max(size_.height(), 280))
        self._window.show()

    def return_(self) -> None:
        """The panel, from its separate window back to its place."""
        if self._native:
            if self.isFloating():
                self._put_frame(False)
                self.setFloating(False)
            return
        if not self.outside():
            return
        window, self._window = self._window, None
        bar = window.layout().itemAt(0).widget()
        panel = window.layout().itemAt(1).widget()
        holes = (self.titleBarWidget(), self.widget())
        self.setTitleBarWidget(bar)
        self.setWidget(panel)
        for hole in holes:
            if hole is not None:
                hole.deleteLater()
        window.hide()
        window.deleteLater()
        self._mark(False)
        self.show()

    def _mark(self, outside: bool) -> None:
        # Outside, in its window, the X is the desktop's (which brings it back): the inside one was too many.
        self._dismiss.setVisible(not outside)
        self._take_out.setIcon(icons.icon("dock" if outside else "undock", _c("text_2", "#9ca1b0"), 16))
        self._take_out.setToolTip(tr('Back to its place in the window') if outside else tr('Move to a separate window'))
        for w in (self._bar, self.panel):
            w.setProperty("floating", outside)
            w.style().unpolish(w)
            w.style().polish(w)

    def eventFilter(self, object_, event) -> bool:
        # Double-click on the header: take out or bring back.
        if event.type() == QEvent.Type.MouseButtonDblClick:
            self.return_() if self.outside() else self.take_out()
            return True
        return super().eventFilter(object_, event)


class TableDataItems(QTreeWidget):
    """The data of each node as a table: node, kind, what it is and its shape (in monospace).

    A click on a row chooses the node on the canvas. What was recomputed with the last change, in green; an error, in
    red. It can be saved as CSV or copied as text (:meth:`as_text`).
    """

    chosen = Signal(str)
    COLUMNS = ('Node', 'Type', 'What it is', 'Shape')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("data_table")
        self.setColumnCount(len(self.COLUMNS))
        self.setHeaderLabels([tr(c) for c in self.COLUMNS])
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setIndentation(0)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        header = self.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._mono = QFont("JetBrains Mono")
        self._mono.setStyleHint(QFont.StyleHint.Monospace)
        self._mono.setPixelSize(12)
        self._rows: list[tuple] = []
        self.icons: dict[str, str | None] = {}      # node → its icon, when the window knows it (extensions)
        self.itemClicked.connect(lambda item, _c: self.chosen.emit(item.data(0, Qt.ItemDataRole.UserRole)))

    def put(self, rows) -> None:
        """`rows`: (name, node kind, category, what it is, shape, state) per node."""
        self._rows = list(rows)
        self.clear()
        green, red = QColor(_c("recomputed", "#7bd88f")), QColor(_c("danger", "#ff6b81"))
        for name, kind, category, what, shape, state in self._rows:
            item = QTreeWidgetItem([name, kind, what, shape])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            icon = self.icons.get(name) or ("code" if kind == tr('Code') else icons.FROM_CATEGORY.get(category))
            if icon:
                color = (theme.current()["p"]["categories"].get(category) if theme.current() else None) or _c("text_2", "#9ca1b0")
                item.setIcon(0, icons.icon(icon, color, 14))
            for col in (2, 3):
                item.setFont(col, self._mono)
            for col in (1, 2):
                item.setForeground(col, QColor(_c("text_2", "#9ca1b0")))
            if state == "recomputed":
                item.setForeground(3, green)
            elif state == "error":
                for col in range(4):
                    item.setForeground(col, red)
            elif state == "waiting":                       # not seen, so not calculated: faint
                faint = QColor(_c("text_2", "#9ca1b0"))
                faint.setAlpha(150)
                for col in range(4):
                    item.setForeground(col, faint)
            self.addTopLevelItem(item)
        for col in range(3):
            self.resizeColumnToContents(col)

    def names(self) -> list[str]:
        return [self.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) for i in range(self.topLevelItemCount())]

    def as_text(self, separator: str = "\t") -> str:
        """The table as text (with tabs) or CSV (separator «,», with quotes where needed)."""
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output, delimiter=separator, lineterminator="\n")
        writer.writerow([tr(c) for c in self.COLUMNS])
        for name, kind, _cat, what, shape, _state in self._rows:
            writer.writerow([name, kind, what, shape])
        return output.getvalue()

#: How long a name can be (a node, a group, a level, a file): long enough to say what it is, short enough to fit on a
#: card, a wire or a menu. Formulas and code have no limit.
NAME_LIMIT = 40
#: How many characters a line of an explanation in a dialog has, at most: shorter lines are easier to read.
LINE_CHARACTERS = 45                                     # (measured with the average letter: about 50 real ones)


def ask_text(parent, title: str, label: str, text: str = "", limit: int = NAME_LIMIT) -> tuple[str, bool]:
    """Like QInputDialog.getText, with at most `limit` characters (what is typed beyond them is not taken)."""
    from PySide6.QtWidgets import QInputDialog, QLabel, QLineEdit
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setInputMode(QInputDialog.InputMode.TextInput)
    dialog.setTextValue(text[:limit])
    field = dialog.findChild(QLineEdit)
    if field is not None:
        field.setMaxLength(limit)
    # A long explanation in lines of about LINE_CHARACTERS (a short paragraph), not one line across the screen.
    words = dialog.findChild(QLabel)
    if words is not None:
        words.setWordWrap(True)
        width = words.fontMetrics().averageCharWidth() * LINE_CHARACTERS
        words.setMinimumWidth(width)
        words.setMaximumWidth(width)
        dialog.adjustSize()
    ok = dialog.exec() == QInputDialog.DialogCode.Accepted
    return dialog.textValue()[:limit], ok


def offered_first(names: list[str], typed: str) -> list[str]:
    """The names that hold what is typed, those that start with it first (ignoring case)."""
    low = typed.lower()
    starts = [n for n in names if n.lower().startswith(low)]
    return starts + [n for n in names if low in n.lower() and not n.lower().startswith(low)]


def complete_inline(field: QLineEdit, names: list[str], later: bool = False) -> None:
    """As a name is typed, the first one that starts with it is proposed in the field itself, the rest selected: «in»
    shows «Inter», one more key goes on typing, Enter takes it, Backspace leaves what was typed. `later`: once
    a list that filters with what is typed has seen it (the list keeps showing all those that hold «in»)."""
    last = [field.text()]

    def propose(text: str) -> None:
        before, last[0] = last[0], text
        if not text or len(text) <= len(before) or field.text() != text or field.cursorPosition() != len(text):
            return                                  # erasing, or the cursor in the middle: as typed
        for name in offered_first(names, text)[:1]:
            if name.lower().startswith(text.lower()) and len(name) > len(text):
                field.setText(name)
                field.setSelection(len(text), len(name) - len(text))

    if later:
        field.textEdited.connect(lambda text: QTimer.singleShot(0, lambda: propose(text)))
    else:
        field.textEdited.connect(propose)
