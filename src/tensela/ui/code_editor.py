"""The editor of a Code node: its Python, with colours and line numbers, checked while it is written.

It stays open beside the window (it is not modal): «Apply» (Ctrl+Enter) puts the code in the node and computes, so
the 3D view shows the result while the code is still at hand. Below, what the check says (code_check.py): ready, or
what does not belong and in which line; after applying, what happened when it ran.

Helps while writing: brackets and quotes closed as they are opened, Tensela's names suggested (and Ctrl+Space),
Ctrl+/ comments or uncomments the lines, Tab and Shift+Tab move the chosen lines in or out, Ctrl+F finds and Ctrl+H
replaces, Ctrl + and Ctrl − make the letter bigger or smaller. Its colours, letter and helps are in Preferences →
Code editor (the gear of the editor goes there): like the window (light or dark), or a theme of its own.
"""
from __future__ import annotations

import keyword
import re

from PySide6.QtCore import QRect, QRegularExpression, QSettings, QSize, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QKeySequence, QPainter, QShortcut, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)
from PySide6.QtWidgets import (QCompleter, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QTextEdit, QToolButton, QVBoxLayout, QWidget)

from ..code_api import ALLOWED_NAMES
from ..code_check import MAX_LINES, check
from ..language import tr
from . import theme

#: What the code can use, in a few lines (the button «What can I use?»).
GUIDE = (
    ('The inputs', 'a, b, c … h: what is connected to the node. A number arrives as a number; a list, as a list; a '
                   'point, as a point; a curve or a panel, as the list of its points.'),
    ('The result', 'result = …: a number, a point, a line, a mesh, or a list of them (lists inside lists give '
                   'levels).'),
    ('Geometry', 'point(x, y, z) · line(p, q) · polyline(points, closed=False) · mesh(points, faces)'),
    ('Points', 'p + q · p - q · p * 2 · p / 2 · p.x p.y p.z · p.length() · p.unit() · p.distance(q) · '
               'p.towards(q, 0.5) · p.rotated(degrees, about=q) · p.dot(q) · p.cross(q)'),
    ('Mathematics', 'sin cos tan asin acos atan atan2 (in degrees) · sqrt exp log floor ceil abs round min max sum '
                    '· pi phi'),
    ('Random', 'random() · uniform(a, b) · randint(a, b) · choice(list) · shuffle(list) · seed(n): the same code '
               'gives the same numbers'),
    ('Python', 'for, while, if, def (also functions that call themselves), lists, dictionaries, range, len, '
               'enumerate, zip, sorted…'),
    ('Not here', 'import, files, the network, other programs, classes: the code of a node only computes with what '
                 'Tensela has. Up to {lines} lines.'),
)


#: The colour themes of the editor: «window» follows the window (paper when it is light, night when it is dark).
COLOUR_THEMES = ('window', 'paper', 'night', 'contrast')
PALETTES = {
    'paper': dict(background="#fbfaf7", text="#2a2c33", keyword="#6a4fd8", ours="#1d7f74", result="#b06a00",
                  number="#b5522b", string="#4f7a28", comment="#8b8f99", lines="#a6a9b2", line="#f0ede5"),
    'night': dict(background="#1b1d23", text="#d9dbe2", keyword="#a99bff", ours="#4fb3a5", result="#e8a33d",
                  number="#d98a5f", string="#9bbf6b", comment="#7d8290", lines="#5b6070", line="#23262e"),
    'contrast': dict(background="#000000", text="#ffffff", keyword="#ffd75f", ours="#5fffd7", result="#ff875f",
                     number="#87d7ff", string="#afff5f", comment="#a8a8a8", lines="#8a8a8a", line="#1c1c1c"),
}
#: The sizes of the letter that can be chosen, in points.
SIZES = (10, 11, 12, 13, 14, 16, 18)


def settings() -> dict:
    """What Preferences → Code editor says: colours, letter (empty: the system's monospace), size, and the helps."""
    a = QSettings()

    def yes(key: str) -> bool:
        return str(a.value(key, True)).lower() not in ("false", "0", "no")
    return {"colours": a.value("code/colours", "window"), "font": a.value("code/font", "") or "",
            "size": float(a.value("code/size", 0) or 0), "pairs": yes("code/pairs"), "complete": yes("code/complete")}


def palette(colours: str) -> dict:
    """The colours of a theme of the editor; «window», those of the window (its accent for Python's words)."""
    if colours in PALETTES:
        return PALETTES[colours]
    surface = QColor(theme.color("surface", "#1b1d23"))
    light = surface.lightnessF() > 0.5
    chosen = dict(PALETTES['paper' if light else 'night'])
    chosen["keyword"] = theme.color("accent", chosen["keyword"])
    return chosen


class _Colours(QSyntaxHighlighter):
    """Python in colours: its words, what Tensela gives, numbers, texts and comments."""

    def __init__(self, document, colours: dict | None = None):
        super().__init__(document)
        self.put(colours or palette("window"))

    def put(self, c: dict) -> None:
        """Other colours (another theme), and the text painted again."""
        def style(colour: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(colour))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            f.setFontItalic(italic)
            return f

        words = "|".join(keyword.kwlist)
        ours = "|".join(sorted(n for n in ALLOWED_NAMES if len(n) > 1 and n not in ("True", "False", "None", "result")))
        self.rules = [
            (QRegularExpression(rf"\b({words})\b"), style(c["keyword"], bold=True)),
            (QRegularExpression(rf"\b({ours})\b(?=\s*\()"), style(c["ours"])),
            (QRegularExpression(r"\bresult\b"), style(c["result"], bold=True)),
            (QRegularExpression(r"\b\d+(\.\d+)?([eE][+-]?\d+)?\b"), style(c["number"])),
            (QRegularExpression(r"\"[^\"\n]*\"|'[^'\n]*'"), style(c["string"])),
            (QRegularExpression(r"#[^\n]*"), style(c["comment"], italic=True)),
        ]
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for expression, style in self.rules:
            matches = expression.globalMatch(text)
            while matches.hasNext():
                m = matches.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), style)


class _Numbers(QWidget):
    """The line numbers, at the left of the code."""

    def __init__(self, editor: "_Code"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.numbers_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_numbers(event)


#: The brackets and quotes closed as they are opened.
PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}


class _Code(QPlainTextEdit):
    """The text of the code: monospace, with line numbers, Tab as four spaces, the line with a problem marked, and
    the helps of the module."""

    #: The size of the letter changed (Ctrl + / Ctrl −): to remember it.
    resized = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._numbers = _Numbers(self)
        self._problem_line = 0
        self.colours = palette("window")
        self.pairs, self.complete = True, True
        self.blockCountChanged.connect(lambda _: self._fit())
        self.updateRequest.connect(self._scrolled)
        self.cursorPositionChanged.connect(self._paint_lines)
        self._completer = QCompleter(self)
        self._completer.setWidget(self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.activated.connect(self._insert_completion)
        self._words = QStringListModel(self)
        self._completer.setModel(self._words)
        self.put_letter("", 0)
        self._fit()

    # --- How it looks ---------------------------------------------------------------------------

    def put_letter(self, family: str, size: float) -> None:
        """The letter: a family (empty: the system's monospace) and a size (0: the usual)."""
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        if family:
            font.setFamily(family)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSizeF(size if size > 0 else max(font.pointSizeF(), 10.5))
        self.setFont(font)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._fit()
        self._numbers.update()

    def put_colours(self, c: dict) -> None:
        self.colours = c
        self.setStyleSheet(f"QPlainTextEdit {{ background: {c['background']}; color: {c['text']}; "
                           f"selection-background-color: {QColor(c['keyword']).darker(130).name()}; "
                           f"selection-color: #ffffff; }}")
        self._paint_lines()
        self._numbers.update()

    def zoom(self, steps: int) -> None:
        """A step bigger or smaller (0: the usual)."""
        size = 0.0 if steps == 0 else min(max(self.font().pointSizeF() + steps, 7.0), 32.0)
        self.put_letter(self.font().family() if steps else QSettings().value("code/font", "") or "", size)
        self.resized.emit(size)

    def numbers_width(self) -> int:
        digits = max(2, len(str(self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _fit(self) -> None:
        self.setViewportMargins(self.numbers_width(), 0, 0, 0)

    def _scrolled(self, rect, dy: int) -> None:
        if dy:
            self._numbers.scroll(0, dy)
        else:
            self._numbers.update(0, rect.y(), self._numbers.width(), rect.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        r = self.contentsRect()
        self._numbers.setGeometry(QRect(r.left(), r.top(), self.numbers_width(), r.height()))

    def paint_numbers(self, event) -> None:
        painter = QPainter(self._numbers)
        painter.fillRect(event.rect(), QColor(self.colours["background"]))
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = round(self.blockBoundingRect(block).height())
        faint, wrong = QColor(self.colours["lines"]), QColor("#e0605a")
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and top + height >= event.rect().top():
                number = block.blockNumber() + 1
                painter.setPen(wrong if number == self._problem_line else faint)
                painter.drawText(0, top, self._numbers.width() - 6, height, Qt.AlignmentFlag.AlignRight, str(number))
            block = block.next()
            top += height
            height = round(self.blockBoundingRect(block).height()) if block.isValid() else height
        painter.end()

    def mark(self, line: int) -> None:
        """The line with a problem, tinted (0: none)."""
        self._problem_line = line
        self._paint_lines()
        self._numbers.update()

    def _paint_lines(self) -> None:
        """The line being written, a little lit; the one with a problem, tinted."""
        marks = []
        here = QTextEdit.ExtraSelection()
        here.format.setBackground(QColor(self.colours["line"]))
        here.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        here.cursor = QTextCursor(self.textCursor().block())
        marks.append(here)
        if self._problem_line > 0:
            block = self.document().findBlockByNumber(self._problem_line - 1)
            if block.isValid():
                mark = QTextEdit.ExtraSelection()
                tint = QColor("#e0605a")
                tint.setAlpha(46)
                mark.format.setBackground(tint)
                mark.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
                mark.cursor = QTextCursor(block)
                marks.append(mark)
        self.setExtraSelections(marks)

    # --- Helps while writing --------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        key, mods, text = event.key(), event.modifiers(), event.text()
        popup = self._completer.popup()
        if popup.isVisible() and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab, Qt.Key.Key_Escape,
                                         Qt.Key.Key_Backtab):
            event.ignore()                                     # (the list of names takes them)
            return
        control = mods & Qt.KeyboardModifier.ControlModifier
        if control and key == Qt.Key.Key_Space:
            self._suggest(force=True)
            return
        if control and key in (Qt.Key.Key_Slash, Qt.Key.Key_NumberSign):
            self.comment()
            return
        if control and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom(+1)
            return
        if control and key == Qt.Key.Key_Minus:
            self.zoom(-1)
            return
        if control and key == Qt.Key.Key_0:
            self.zoom(0)
            return
        if key == Qt.Key.Key_Backtab:
            self.indent(-1)
            return
        if key == Qt.Key.Key_Tab and not mods:
            if self.textCursor().hasSelection() and " " in self.textCursor().selectedText():
                self.indent(+1)
            else:
                self.insertPlainText("    ")
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not mods:
            line = self.textCursor().block().text()[: self.textCursor().positionInBlock()]
            indent = line[: len(line) - len(line.lstrip(" "))]
            if line.rstrip().endswith(":"):                   # after «for …:», one step in
                indent += "    "
            self.insertPlainText("\n" + indent)
            return
        if self.pairs and self._pair(key, text):
            return
        super().keyPressEvent(event)
        if self.complete and text and (text.isalnum() or text == "_"):
            self._suggest()
        elif popup.isVisible() and not text.isalnum():
            popup.hide()

    def _pair(self, key, text: str) -> bool:
        """Brackets and quotes: the closing one put with the opening one, stepped over if it is already there, both
        removed together, and a selection put between them. True if it took the key."""
        cursor = self.textCursor()
        block, at = cursor.block().text(), cursor.positionInBlock()
        after = block[at:at + 1]
        before = block[at - 1:at] if at else ""
        if key == Qt.Key.Key_Backspace and not cursor.hasSelection() and before in PAIRS and PAIRS[before] == after:
            cursor.beginEditBlock()
            cursor.deleteChar()
            cursor.deletePreviousChar()
            cursor.endEditBlock()
            return True
        if text in (")", "]", "}", '"', "'") and after == text and not cursor.hasSelection():
            if text in "\"'" and block[:at].count(text) % 2 == 0:
                pass                                           # (a quote that opens a new text)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.Right)
                self.setTextCursor(cursor)
                return True
        if text in PAIRS:
            if cursor.hasSelection():                          # the chosen text, between them
                chosen = cursor.selectedText()
                cursor.insertText(text + chosen + PAIRS[text])
                return True
            if text in "\"'" and (before.isalnum() or after.isalnum()):
                return False                                   # (an apostrophe inside a word: alone)
            if after and not (after.isspace() or after in ")]},:"):
                return False                                   # before a word: the bracket alone
            cursor.insertText(text + PAIRS[text])
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            return True
        return False

    def _lines(self) -> tuple[int, int]:
        """The first and last lines of the selection (or the line of the cursor)."""
        cursor = self.textCursor()
        doc = self.document()
        first = doc.findBlock(cursor.selectionStart()).blockNumber()
        last_block = doc.findBlock(cursor.selectionEnd())
        last = last_block.blockNumber()
        if cursor.hasSelection() and cursor.selectionEnd() == last_block.position() and last > first:
            last -= 1                                          # (a selection ending at the start of a line)
        return first, last

    def _each_line(self, change) -> None:
        """`change(text) -> new text` on each chosen line, as one step to undo; the lines stay chosen."""
        first, last = self._lines()
        doc = self.document()
        cursor = QTextCursor(doc.findBlockByNumber(first))
        cursor.beginEditBlock()
        for n in range(first, last + 1):
            block = doc.findBlockByNumber(n)
            new = change(block.text())
            if new != block.text():
                line = QTextCursor(block)
                line.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                line.insertText(new)
        cursor.endEditBlock()
        start = doc.findBlockByNumber(first).position()
        end_block = doc.findBlockByNumber(last)
        chosen = QTextCursor(doc)
        chosen.setPosition(start)
        chosen.setPosition(end_block.position() + len(end_block.text()), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(chosen)

    def comment(self) -> None:
        """Ctrl+/: the chosen lines become comments («# »), or stop being so if they all were."""
        first, last = self._lines()
        texts = [self.document().findBlockByNumber(n).text() for n in range(first, last + 1)]
        written = [t for t in texts if t.strip()]
        commented = bool(written) and all(t.lstrip().startswith("#") for t in written)
        margin = min((len(t) - len(t.lstrip(" ")) for t in written), default=0)

        def change(t: str) -> str:
            if not t.strip():
                return t
            if commented:
                k = t.index("#")
                return t[:k] + t[k + 2:] if t[k + 1:k + 2] == " " else t[:k] + t[k + 1:]
            return t[:margin] + "# " + t[margin:]
        self._each_line(change)

    def indent(self, way: int) -> None:
        """Tab with several lines chosen: four spaces in; Shift+Tab: up to four out."""
        def change(t: str) -> str:
            if way > 0:
                return "    " + t if t.strip() else t
            return t[min(4, len(t) - len(t.lstrip(" "))):]
        self._each_line(change)

    def _prefix(self) -> str:
        cursor = self.textCursor()
        line = cursor.block().text()[: cursor.positionInBlock()]
        m = re.search(r"[A-Za-z_][A-Za-z_0-9]*$", line)
        return m.group(0) if m else ""

    def _suggest(self, force: bool = False) -> None:
        """Tensela's names, Python's words and those already in the code that begin as what is being written."""
        prefix = self._prefix()
        if len(prefix) < (1 if force else 2):
            self._completer.popup().hide()
            return
        written = set(re.findall(r"\b[A-Za-z_][A-Za-z_0-9]{2,}\b", self.toPlainText())) - {prefix}
        words = sorted(set(ALLOWED_NAMES) | set(keyword.kwlist) | written | {"result"}, key=str.casefold)
        self._words.setStringList([w for w in words if w != prefix])
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            self._completer.popup().hide()
            return
        self._completer.popup().setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(180, self._completer.popup().sizeHintForColumn(0) + 24))
        self._completer.complete(rect)

    def _insert_completion(self, word: str) -> None:
        cursor = self.textCursor()
        prefix = self._prefix()
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        cursor.insertText(word)
        self.setTextCursor(cursor)

    def find(self, text: str, backwards: bool = False) -> bool:
        """The next place with `text` (from the cursor; at the end, from the start again), chosen."""
        if not text:
            return False
        flags = QTextDocument.FindFlag.FindBackward if backwards else QTextDocument.FindFlag(0)
        found = self.document().find(text, self.textCursor(), flags)
        if found.isNull():                                     # round again
            start = QTextCursor(self.document())
            if backwards:
                start.movePosition(QTextCursor.MoveOperation.End)
            found = self.document().find(text, start, flags)
        if found.isNull():
            return False
        self.setTextCursor(found)
        return True

    def replace(self, text: str, new: str) -> bool:
        """The chosen place, if it is `text`, becomes `new`; then the next one is chosen."""
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectedText().casefold() == text.casefold():
            cursor.insertText(new)
        return self.find(text)

    def replace_all(self, text: str, new: str) -> int:
        """Every place with `text` becomes `new`, as one step to undo. How many."""
        if not text:
            return 0
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        count = 0
        found = self.document().find(text, cursor)
        while not found.isNull():
            found.insertText(new)
            count += 1
            found = self.document().find(text, found)
        cursor.endEditBlock()
        return count


class CodeDialog(QDialog):
    """The code of one node. `applied(node, code)`: the code goes to the node (and it is computed)."""

    applied = Signal(str, str)
    preferences = Signal()                                    # the gear: Preferences → Code editor

    def __init__(self, node: str, code: str, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(tr('Code of «{node}»').format(node=node))
        self.setModal(False)
        self.resize(760, 560)
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(8)
        self.code = _Code()
        self.code.setPlainText(code)
        self._colours = _Colours(self.code.document())
        self.code.resized.connect(lambda size: QSettings().setValue("code/size", size))
        column.addWidget(self.code, 1)
        column.addWidget(self._find_bar())
        self.guide = QLabel()
        self.guide.setWordWrap(True)
        self.guide.setTextFormat(Qt.TextFormat.RichText)
        self.guide.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.guide.setText("<table cellspacing='4'>" + "".join(
            f"<tr><td><b>{tr(title)}</b>&nbsp;&nbsp;</td><td>{tr(text).format(lines=MAX_LINES)}</td></tr>"
            for title, text in GUIDE) + "</table>")
        self.guide.hide()
        column.addWidget(self.guide)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self.status)
        row = QHBoxLayout()
        what = QPushButton(tr('What can I use?'))
        what.setCheckable(True)
        what.toggled.connect(self.guide.setVisible)
        row.addWidget(what)
        from .widgets import button_icon
        gear = button_icon("gear", 'Colours, letter and helps of the editor (Preferences → Code editor)')
        gear.setObjectName("code_settings")
        gear.clicked.connect(self.preferences.emit)
        row.addWidget(gear)
        row.addStretch(1)
        close = QPushButton(tr('Close'))
        close.clicked.connect(self.close)
        row.addWidget(close)
        self.apply_button = QPushButton(tr('Apply'))
        self.apply_button.setDefault(True)
        self.apply_button.setToolTip(tr('Put the code in the node and compute (Ctrl+Enter)'))
        self.apply_button.clicked.connect(self.apply)
        row.addWidget(self.apply_button)
        column.addLayout(row)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.apply)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.apply)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.show_find(False))
        QShortcut(QKeySequence("Ctrl+H"), self, activated=lambda: self.show_find(True))
        QShortcut(QKeySequence("F3"), self, activated=lambda: self.code.find(self.wanted.text()))
        QShortcut(QKeySequence("Shift+F3"), self, activated=lambda: self.code.find(self.wanted.text(), True))
        self.restyle()
        self._later = QTimer(self)                           # the check, a moment after the last key
        self._later.setSingleShot(True)
        self._later.setInterval(250)
        self._later.timeout.connect(self._check)
        self.code.textChanged.connect(self._later.start)
        self._applied = code
        self._check()

    def restyle(self) -> None:
        """The colours, letter and helps of Preferences → Code editor (on opening, and when they change)."""
        chosen = settings()
        colours = palette(chosen["colours"])
        self.code.put_colours(colours)
        self._colours.put(colours)
        self.code.put_letter(chosen["font"], chosen["size"])
        self.code.pairs, self.code.complete = chosen["pairs"], chosen["complete"]

    def _find_bar(self) -> QWidget:
        """Find (Ctrl+F) and replace (Ctrl+H): hidden until asked for; Esc hides it."""
        self.finding = QWidget()
        row = QHBoxLayout(self.finding)
        row.setContentsMargins(0, 0, 0, 0)
        self.wanted = QLineEdit()
        self.wanted.setObjectName("code_find")
        self.wanted.setPlaceholderText(tr('Find'))
        self.wanted.setClearButtonEnabled(True)
        self.wanted.returnPressed.connect(lambda: self._found(self.code.find(self.wanted.text())))
        row.addWidget(self.wanted, 2)
        self.instead = QLineEdit()
        self.instead.setObjectName("code_replace")
        self.instead.setPlaceholderText(tr('Replace with'))
        self.instead.returnPressed.connect(
            lambda: self._found(self.code.replace(self.wanted.text(), self.instead.text())))
        row.addWidget(self.instead, 2)
        for text, action in (('Next', lambda: self._found(self.code.find(self.wanted.text()))),
                             ('Replace', lambda: self._found(self.code.replace(self.wanted.text(),
                                                                                self.instead.text()))),
                             ('Replace all', self._replace_all)):
            button = QPushButton(tr(text))
            button.clicked.connect(action)
            row.addWidget(button)
        close = QToolButton()
        close.setText("✕")
        close.setToolTip(tr('Close (Esc)'))
        close.clicked.connect(self._hide_find)
        row.addWidget(close)
        self.finding.hide()
        return self.finding

    def show_find(self, replacing: bool) -> None:
        self.finding.show()
        chosen = self.code.textCursor().selectedText()
        if chosen and "\u2029" not in chosen:
            self.wanted.setText(chosen)
        (self.instead if replacing and self.wanted.text() else self.wanted).setFocus()
        self.wanted.selectAll()

    def _hide_find(self) -> None:
        self.finding.hide()
        self.code.setFocus()

    def _found(self, yes: bool) -> None:
        if not yes and self.wanted.text():
            self._say(tr('“{text}” is not in the code.').format(text=self.wanted.text()), False)

    def _replace_all(self) -> None:
        n = self.code.replace_all(self.wanted.text(), self.instead.text())
        self._say(tr('{n} replaced.').format(n=n), False)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.finding.isVisible():
            self._hide_find()
            return
        super().keyPressEvent(event)

    def _say(self, text: str, wrong: bool) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {'#e0605a' if wrong else theme.color('text_2', '#9ca1b0')};")

    def _check(self) -> bool:
        problem = check(self.code.toPlainText())
        self.code.mark(problem.line if problem is not None else 0)
        if problem is not None:
            self._say(_capital(str(problem)), True)
            return False
        pending = self.code.toPlainText() != self._applied
        self._say(tr('Ready. Ctrl+Enter applies it.') if pending else tr('Ready.'), False)
        return True

    def apply(self) -> None:
        """The code goes to the node, if the check lets it through (if not, it says why and nothing changes)."""
        if not self._check():
            return
        self._applied = self.code.toPlainText()
        self._say(tr('Computing…'), False)
        self.applied.emit(self.node, self._applied)

    def report(self, error: str | None) -> None:
        """What happened when the node was computed with this code: nothing to say, or its error."""
        if self.code.toPlainText() != self._applied:
            return                                            # already writing something else
        if error:
            line = _line_in(error)
            self.code.mark(line)
            self._say(error, True)
        else:
            self.code.mark(0)
            self._say(tr('Applied: the node computed without problems.'), False)

    def renamed(self, name: str) -> None:
        self.node = name
        self.setWindowTitle(tr('Code of «{node}»').format(node=name))


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _line_in(message: str) -> int:
    """The line a message talks about («Line 7: …», in any language of the interface), or 0."""
    message = message.split("): ", 1)[-1]                   # (without «In “node” (Code): », which may have numbers)
    m = re.search(r"\b(\d+):", message)
    return int(m.group(1)) if m else 0

