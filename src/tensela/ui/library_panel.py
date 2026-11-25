"""The Library panel: the groups of the project and those of the library, to find them and put them on the canvas.

A search on top, with the two ways of seeing it on its right; below, two parts: «In this project» (the groups the
project has) and «In the library» (the ones saved to use in any project).

- **List**: each group in a row, with a swatch and two lines: its name, and how many nodes it has, what it takes and
  what it gives.
- **Tiles**: each group as a small card, side by side, with its swatch on top and its name below.

The swatch is the colour and the icon of the family of nodes the group has most of (a group mostly of surfaces is
blue, with the surfaces icon), the same colours as the cards of the canvas: groups that do alike look alike. The way
of seeing it is remembered.

The pointer resting on a group shows what it does (its description, or the one it writes by itself: what it takes,
what it gives and its nodes). A double click, or dragging it to the canvas, puts it there. The right click: put it,
save it to the library, rename it, delete it (to the trash) or open the folder.

Later it can hold other things saved for reuse (the user's own curves, matcaps).
"""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QMimeData, QRect, QRectF, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QListView, QListWidget, QListWidgetItem, QMenu,
                               QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from ..language import tr
from . import icons

#: What a dragged group carries: «project:name» or «library:name».
MIME_GROUP = "application/x-tensela-group"
PROJECT, LIBRARY = "project", "library"
LIST, TILES = "list", "tiles"
VIEWS = (LIST, TILES)
SETTING = "library/view"

# What each row holds, besides its text and tooltip.
_WHAT = Qt.ItemDataRole.UserRole + 1         # «header», «hint» or «group»
_INFO = Qt.ItemDataRole.UserRole + 2         # of a group: {category, nodes, takes, gives}
_GROUP = Qt.ItemDataRole.UserRole            # of a group: (where, name)

ROW = 46                                     # the height of a row in the list
TILE = QSize(96, 98)                         # a card in tiles, at least (it widens to fill each row)
SWATCH = 30                                  # the swatch of the list


def summary(definition, kinds: dict) -> dict:
    """What the panel shows of a group: the family most of its nodes belong to, how many nodes it has, its inputs
    and what comes out. `kinds`: {name: NodeType}, to know the family of each node inside."""
    families = Counter()
    for node in definition.nodes.values():
        kind = kinds.get(node.get("type"))
        families[getattr(kind, "category", "Groups") or "Groups"] += 1
    category = families.most_common(1)[0][0] if families else "Groups"
    output = definition.output
    out_kind = kinds.get(definition.nodes.get(output, {}).get("type"))
    gives = getattr(out_kind, "output", None) or output
    return {"category": category, "nodes": len(definition.nodes), "takes": list(definition.inputs), "gives": gives}


def _color(key: str, fallback: str) -> QColor:
    from . import theme as theme
    return QColor(theme.color(key, fallback))


class _Groups(QListWidget):
    """The groups, as a list or as tiles: they can be dragged, carrying where each one comes from and its name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("library_groups")
        self.setMouseTracking(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(_Card(self))
        self.view = LIST

    def put_view(self, view: str) -> None:
        self.view = view if view in VIEWS else LIST
        tiles = self.view == TILES
        self.setViewMode(QListView.ViewMode.IconMode if tiles else QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.LeftToRight if tiles else QListView.Flow.TopToBottom)
        self.setWrapping(tiles)
        self.setSpacing(4 if tiles else 0)
        self.setMovement(QListView.Movement.Static)
        self.setDragEnabled(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.scheduleDelayedItemsLayout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.scheduleDelayedItemsLayout()           # the headers and hints take the whole width again

    def mimeTypes(self) -> list[str]:
        return [MIME_GROUP]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        item = next((i for i in items if i.data(_GROUP)), None)
        if item is not None:
            where, name = item.data(_GROUP)
            data.setData(MIME_GROUP, f"{where}:{name}".encode("utf-8"))
        return data


class _Card(QStyledItemDelegate):
    """Paints each row: a part's title, a hint (no groups yet) or a group, in the list or as a tile."""

    def _width(self) -> int:
        view = self.parent()
        return max(80, view.viewport().width() - 2 * view.spacing() - 2)

    def sizeHint(self, option, index) -> QSize:
        what = index.data(_WHAT)
        if what == "header":
            return QSize(self._width(), 30)
        if what == "hint":
            fm = QFontMetrics(option.font)
            text_rect = fm.boundingRect(QRect(0, 0, self._width() - 16, 1000), Qt.TextFlag.TextWordWrap,
                                        index.data(Qt.ItemDataRole.DisplayRole) or "")
            return QSize(self._width(), text_rect.height() + 12)
        if self.parent().view == TILES:
            view = self.parent()
            # (Qt wraps a row keeping room for the scroll bar, shown or not)
            bar = view.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
            room = view.viewport().width() - view.spacing() - bar - 4
            columns = max(1, room // (TILE.width() + view.spacing()))
            return QSize(min(room // columns - view.spacing(), 2 * TILE.width()), TILE.height())
        return QSize(self._width(), ROW)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        what = index.data(_WHAT)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        r = option.rect
        if what == "header":
            font = QFont(option.font)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(_color("text_2", "#9ca1b0"))
            painter.drawText(r.adjusted(6, 0, -6, -4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, text)
        elif what == "hint":
            painter.setPen(_color("disabled", "#5b6070"))
            painter.drawText(r.adjusted(8, 4, -8, -4), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft, text)
        else:
            self._paint_group(painter, option, index, text)
        painter.restore()

    def _paint_group(self, painter: QPainter, option, index, name: str) -> None:
        from . import editor as editor
        info = index.data(_INFO) or {}
        category = info.get("category", "Groups")
        colour = QColor(editor.COLOURS_CATEGORY.get(category, editor.BODY))
        # The icon, white on a dark swatch and dark on a light one (the colours change with the theme).
        light = colour.lightnessF() > 0.62
        icon = icons.icon(icons.FROM_CATEGORY.get(category, "group"), "#1d1f24" if light else "#ffffff", 16)
        r = option.rect
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        chosen = bool(option.state & QStyle.StateFlag.State_Selected)
        nodes = tr('{n} nodes').format(n=info.get("nodes", 0)) if info.get("nodes") != 1 else tr('1 node')
        if self.parent().view == TILES:
            card = QRectF(r).adjusted(1, 1, -1, -1)
            painter.setPen(QPen(_color("accent", "#8b7cf6") if chosen else _color("border", "#2a2d36"), 1.2))
            painter.setBrush(_color("hover", "#24262d") if hover or chosen else _color("field", "#0e0f13"))
            painter.drawRoundedRect(card, 6, 6)
            swatch = QRectF(card.left() + 7, card.top() + 7, card.width() - 14, 30)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawRoundedRect(swatch, 4, 4)
            icon.paint(painter, swatch.toRect())
            painter.setPen(_color("text", "#eceff1"))
            text_rect = QRect(int(card.left()) + 6, int(swatch.bottom()) + 5, int(card.width()) - 12, 36)
            fm = QFontMetrics(option.font)
            two_lines = _two_lines(name, fm, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, two_lines)
            small = QFont(option.font)
            small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.85))
            painter.setFont(small)
            painter.setPen(_color("text_2", "#9ca1b0"))
            painter.drawText(QRect(int(card.left()), int(card.bottom()) - 19, int(card.width()), 15),
                             Qt.AlignmentFlag.AlignHCenter, nodes)
            return
        if hover or chosen:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_color("accent_soft", "#2b2840") if chosen else _color("hover", "#24262d"))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 1, -2, -1), 5, 5)
        swatch = QRectF(r.left() + 8, r.top() + (r.height() - SWATCH) / 2, SWATCH, SWATCH)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(swatch, 5, 5)
        icon.paint(painter, swatch.adjusted(7, 7, -7, -7).toRect())
        left = int(swatch.right()) + 10
        width = r.right() - left - 8
        painter.setPen(_color("text", "#eceff1"))
        fm = QFontMetrics(option.font)
        painter.drawText(QRect(left, r.top() + 5, width, r.height() // 2 - 3),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                         fm.elidedText(name, Qt.TextElideMode.ElideRight, width))
        parts = [nodes]
        if info.get("takes"):
            parts.append(tr('takes: {inputs}').format(inputs=", ".join(info["takes"])))
        if info.get("gives"):
            parts.append(tr('gives: {output}').format(output=tr(info["gives"])))
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.88))
        painter.setFont(small)
        painter.setPen(_color("text_2", "#9ca1b0"))
        painter.drawText(QRect(left, r.top() + r.height() // 2 + 1, width, r.height() // 2 - 4),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         QFontMetrics(small).elidedText(" · ".join(parts), Qt.TextElideMode.ElideRight, width))


def _two_lines(text: str, fm: QFontMetrics, width: int) -> str:
    """The name of a tile in two lines at most, the second cut with «…» if it does not fit."""
    words, first = text.split(), ""
    while words and fm.horizontalAdvance((first + " " + words[0]).strip()) <= width:
        first = (first + " " + words.pop(0)).strip()
    if not first:                                       # one long word: cut it
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, width)
    if not words:
        return first
    return first + "\n" + fm.elidedText(" ".join(words), Qt.TextElideMode.ElideRight, width)


class LibraryPanel(QWidget):
    """See the module. It asks the window to do things (put, save, rename, delete, open the folder) with signals."""

    put = Signal(str, str)              # where it comes from (project or library) and its name: to the canvas
    save = Signal(str)                  # a project group, to the library
    rename = Signal(str, str)           # where and name: rename it
    delete = Signal(str)                # a library group: to the trash
    open_folder = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from .widgets import button_icon
        layer = QVBoxLayout(self)
        layer.setContentsMargins(0, 0, 0, 0)
        layer.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(2)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Search groups…'))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.buttons = {LIST: button_icon("list_view", 'As a list: each group with its swatch, its nodes, what it '
                                                       'takes and what it gives', checkable=True),
                        TILES: button_icon("tiles", 'As tiles: each group as a small card', checkable=True)}
        for view, button in self.buttons.items():
            button.clicked.connect(lambda _=False, view=view: self.put_view(view))
            top.addWidget(button)
        layer.addLayout(top)
        self.groups = _Groups()
        self.groups.itemDoubleClicked.connect(self._double_click)
        self.groups.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.groups.customContextMenuRequested.connect(self._menu)
        layer.addWidget(self.groups, 1)
        self.put_view(str(QSettings().value(SETTING, LIST)), remember=False)

    @property
    def view(self) -> str:
        return self.groups.view

    def put_view(self, view: str, remember: bool = True) -> None:
        """As a list or as tiles (remembered)."""
        self.groups.put_view(view)
        for v, button in self.buttons.items():
            button.setChecked(v == self.groups.view)
        if remember:
            QSettings().setValue(SETTING, self.groups.view)

    def show_groups(self, project: dict, library: dict) -> None:
        """The groups, by part: `project` and `library` are {name: description} or {name: (description, info)},
        where the info is what `summary` gives."""
        self.groups.clear()
        for where, title, groups in ((PROJECT, 'In this project', project), (LIBRARY, 'In the library', library)):
            header = QListWidgetItem(tr(title))
            header.setData(_WHAT, "header")
            header.setData(Qt.ItemDataRole.UserRole + 3, where)
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.groups.addItem(header)
            if not groups:
                hint = QListWidgetItem(tr('(none yet: select some nodes and Ctrl + G)') if where == PROJECT
                                       else tr('(none yet: right click on a group → Save to library)'))
                hint.setData(_WHAT, "hint")
                hint.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.groups.addItem(hint)
            for name in sorted(groups, key=str.casefold):
                described = groups[name]
                help_, info = described if isinstance(described, tuple) else (described, {})
                item = QListWidgetItem(name)
                item.setData(_WHAT, "group")
                item.setData(_GROUP, (where, name))
                item.setData(_INFO, info)
                item.setToolTip(help_)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                self.groups.addItem(item)
        self._filter(self.search.text())

    def items(self, where: str, visible: bool = True) -> list[QListWidgetItem]:
        """The groups of a part (`project` or `library`), only those the search leaves if `visible`."""
        found = []
        for k in range(self.groups.count()):
            item = self.groups.item(k)
            data = item.data(_GROUP)
            if data and data[0] == where and not (visible and item.isHidden()):
                found.append(item)
        return found

    def names(self, where: str) -> list[str]:
        """The names of the groups of a part that the search leaves."""
        return [item.text() for item in self.items(where)]

    def _filter(self, text: str) -> None:
        """Only the groups whose name or description has the text searched (without minding capitals)."""
        wanted = text.strip().casefold()
        for k in range(self.groups.count()):
            item = self.groups.item(k)
            if item.data(_WHAT) != "group":
                continue
            found = not wanted or wanted in item.text().casefold() or wanted in item.toolTip().casefold()
            item.setHidden(not found)

    def _double_click(self, item: QListWidgetItem) -> None:
        data = item.data(_GROUP)
        if data:
            self.put.emit(*data)

    def _menu(self, point) -> None:
        item = self.groups.itemAt(point)
        data = item.data(_GROUP) if item is not None else None
        menu = QMenu(self)
        if data:
            where, name = data
            menu.addAction(tr('Put on the canvas'), lambda: self.put.emit(where, name))
            if where == PROJECT:
                menu.addAction(tr('Save to library…'), lambda: self.save.emit(name))
            else:
                menu.addAction(tr('Rename…'), lambda: self.rename.emit(where, name))
                menu.addAction(tr('Delete from the library…'), lambda: self.delete.emit(name))
            menu.addSeparator()
        view = menu.addMenu(tr('See as'))
        for v, label in ((LIST, 'List'), (TILES, 'Tiles')):
            action = view.addAction(tr(label), lambda v=v: self.put_view(v))
            action.setCheckable(True)
            action.setChecked(v == self.view)
        menu.addAction(tr('Open the library folder'), self.open_folder.emit)
        menu.exec(self.groups.viewport().mapToGlobal(point))
