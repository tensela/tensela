"""The shortcuts of the menus: short, smaller than the text and in monospace (Delivery 5).

Qt writes the shortcuts in full and in the system's language («Control+Mayúsculas+R») and, with the stylesheet, with
the same letter as the command: they compete. Here they are abbreviated (`text_shortcut`: «Ctrl+Shift+R») and each
menu is painted with the command as always and the shortcut apart, on the right, smaller and in grey (`MenuPainter`,
a filter of the whole application: it works for the menu bar and for the right-click ones).
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter
from PySide6.QtWidgets import QMenu, QStyle, QStyleOptionFrame, QStyleOptionMenuItem

from .. import language as language

#: How each key is written, in short: (Spanish, English).
_KEYS = {
    "Ctrl": ("Ctrl", "Ctrl"), "Shift": ("Mayús", "Shift"), "Alt": ("Alt", "Alt"), "Meta": ("Súper", "Super"),
    "Del": ("Supr", "Del"), "Backspace": ("Retroceso", "Backspace"), "Return": ("Intro", "Enter"),
    "Enter": ("Intro", "Enter"), "Esc": ("Esc", "Esc"), "Space": ("Espacio", "Space"), "Tab": ("Tab", "Tab"),
    "Ins": ("Insert", "Ins"), "Home": ("Inicio", "Home"), "End": ("Fin", "End"),
    "PgUp": ("RePág", "PgUp"), "PgDown": ("AvPág", "PgDn"),
    "Left": ("←", "←"), "Right": ("→", "→"), "Up": ("↑", "↑"), "Down": ("↓", "↓"),
}
RIGHT_MARGIN = 12          # the shortcut, at this distance from the edge of the line


def text_shortcut(shortcut) -> str:
    """A shortcut (QKeySequence or text) in short and in Tensela's language: «Ctrl+Shift+R», «Del»."""
    sequence = shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(shortcut)
    portable = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if not portable:
        return ""
    english = language.LANGUAGE == "en"
    chords = []
    for chord in portable.split(", "):
        # «Ctrl++» (the + key): the last «+» is the key.
        parts = chord[:-2].split("+") + ["+"] if chord.endswith("++") else chord.split("+")
        chords.append("+".join(_KEYS.get(p, (p, p))[1 if english else 0] for p in parts))
    return ", ".join(chords)


def _color(key: str, yes_no: str) -> QColor:
    from . import theme as theme
    return QColor(theme.color(key, yes_no)) if theme.current() else QColor(yes_no)


class MenusPainter(QObject):
    """Paints each menu with the shortcuts apart (see the module). It is installed on the application."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = QFont("JetBrains Mono")
        self.source.setStyleHint(QFont.StyleHint.Monospace)

    def eventFilter(self, object_, event) -> bool:
        if event.type() == QEvent.Type.Paint and isinstance(object_, QMenu):
            self.paint(object_, event.rect())
            return True
        return False

    def paint(self, menu: QMenu, zone: QRect) -> None:
        """What QMenu does when painting itself (background, lines, border), with the shortcut apart on each line."""
        style_name = menu.style()
        p = QPainter(menu)
        option = QStyleOptionMenuItem()
        option.initFrom(menu)
        option.state = QStyle.StateFlag.State_None
        option.checkType = QStyleOptionMenuItem.CheckType.NotCheckable
        option.maxIconWidth = 0
        option.reservedShortcutWidth = 0
        style_name.drawPrimitive(QStyle.PrimitiveElement.PE_PanelMenu, option, p, menu)
        size_ = max(9.0, menu.font().pixelSize() * 0.84 if menu.font().pixelSize() > 0
                     else menu.font().pointSizeF() * 0.84 * 1.33)
        self.source.setPixelSize(round(size_))
        grey, off = _color("text_2", "#9ca1b0"), _color("disabled", "#5b6070")
        for action in menu.actions():
            if not action.isVisible():
                continue
            box = menu.actionGeometry(action)
            if not box.intersects(zone):
                continue
            option = QStyleOptionMenuItem()
            menu.initStyleOption(option, action)
            option.rect = box
            text, _, _qt = option.text.partition("\t")
            option.text = text
            style_name.drawControl(QStyle.ControlElement.CE_MenuItem, option, p, menu)
            shortcut = text_shortcut(action.shortcut()) if not action.menu() else ""
            if shortcut:
                p.setFont(self.source)
                p.setPen(grey if action.isEnabled() else off)
                p.drawText(box.adjusted(0, 0, -RIGHT_MARGIN, 0),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, shortcut)
        edge = QStyleOptionFrame()
        edge.initFrom(menu)
        edge.rect = menu.rect()
        edge.state = QStyle.StateFlag.State_None
        edge.lineWidth = style_name.pixelMetric(QStyle.PixelMetric.PM_MenuPanelWidth, None, menu)
        edge.midLineWidth = 0
        style_name.drawPrimitive(QStyle.PrimitiveElement.PE_FrameMenu, edge, p, menu)
        p.end()
