"""Tooltips that read comfortably: a long help comes in short lines, about 50 characters, instead of one line across
the whole screen.

Qt shows a plain-text tooltip in a single line, as long as it is (a node's help can take the width of the screen).
`TipWrapper`, a filter of the whole application, catches the request for a tooltip before Qt answers it, finds the text
that would be shown (a widget's, an item's in a list, a card's on the canvas, a tab's, a menu entry's) and shows it
itself in short lines (`wrapped`). Shown once, where Qt would put it: it neither jumps nor blinks. The line breaks a
text already has are kept; a short tooltip, or one in rich text (Qt wraps it itself), is left to Qt.
"""
from __future__ import annotations

import textwrap

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QAbstractItemView, QGraphicsProxyWidget, QGraphicsView, QMenu, QTabBar, QToolTip, QWidget

#: The longest line of a tooltip, in characters: what reads at a glance without moving the eyes across.
TIP_WIDTH = 50


def wrapped(text: str, width: int = TIP_WIDTH) -> str:
    """The text in lines of `width` characters at most (a word longer than that, such as a path, stays whole)."""
    lines = []
    for paragraph in text.split("\n"):
        if len(paragraph) <= width:
            lines.append(paragraph)
        else:
            lines.extend(textwrap.wrap(paragraph, width, break_long_words=False, break_on_hyphens=False) or [""])
    return "\n".join(lines)


def needs_wrapping(text: str, width: int = TIP_WIDTH) -> bool:
    return bool(text) and not Qt.mightBeRichText(text) and wrapped(text, width) != text


class TipWrapper(QObject):
    """Shows each long tooltip in short lines (see the module). It is installed on the application."""

    def eventFilter(self, object_, event) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(object_, QWidget):
            text, rect = tip_of(object_, event.pos())
            if text and needs_wrapping(text):
                QToolTip.showText(event.globalPos(), wrapped(text), object_, rect)
                return True                       # answered: Qt does not show it a second time, in one line
        return False


def tip_of(widget: QWidget, pos) -> tuple[str | None, QRect]:
    """The tooltip Qt would show over `widget` at `pos`, and the area it belongs to (it hides on leaving it). None
    when it is not known here (an embedded widget answers for itself): then Qt shows it as always."""
    parent = widget.parentWidget()
    if isinstance(parent, QGraphicsView) and widget is parent.viewport():     # the canvas: the card under the pointer
        for item in parent.items(pos):
            if isinstance(item, QGraphicsProxyWidget):
                return None, QRect()              # a field open on a card: its own
            if item.toolTip():
                return item.toolTip(), QRect()
        return None, QRect()
    if isinstance(parent, QAbstractItemView) and widget is parent.viewport():
        index = parent.indexAt(pos)
        text = index.data(Qt.ItemDataRole.ToolTipRole) if index.isValid() else None
        return (text, parent.visualRect(index)) if isinstance(text, str) else (None, QRect())
    if isinstance(widget, QTabBar):
        i = widget.tabAt(pos)
        return (widget.tabToolTip(i), widget.tabRect(i)) if i >= 0 else (None, QRect())
    if isinstance(widget, QMenu):
        action = widget.actionAt(pos)
        if action is None or not widget.toolTipsVisible():
            return None, QRect()
        return action.toolTip(), widget.actionGeometry(action)
    return widget.toolTip() or None, QRect()
