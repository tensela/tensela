"""The panel «AI connection»: whether an AI program is connected, what it may do, how to connect one (what to paste
in its settings, with Copy) and what it did, step by step. «Disconnect and pause» and «Allow again»."""
from __future__ import annotations

import json
import os
import shlex
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from tensela.language import tr

from . import changes


def command() -> list[str]:
    """How the AI program starts the bridge: the AppImage, or the Python of this Tensela."""
    appimage = os.environ.get("APPIMAGE") or os.environ.get("TENSELA_PORTABLE")      # (or its portable folder)
    if appimage:
        return [appimage, "--extension", "ai-connection"]
    return [sys.executable, "-m", "tensela.ui.launch", "--extension", "ai-connection"]


def settings_text() -> str:
    """What to paste in the settings of MCP servers of the AI program."""
    first, *rest = command()
    return json.dumps({"mcpServers": {"tensela": {"command": first, "args": rest}}}, indent=2)


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: 600;")
    return label


def _divider() -> QFrame:
    from tensela.ui import theme
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    colour = theme.color("border", "#dfe2e9")
    line.setStyleSheet(f"color: {colour}; background: {colour}; border: none;")
    return line


class ConnectionPanel(QWidget):
    """Its parts one under the other, separated by lines, inside a scroll (a short panel scrolls: its parts do not
    pile up on each other); what it did, in a frame of its own."""

    def __init__(self, window, server):
        super().__init__()
        self.window, self.server = window, server
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        inside = QWidget()
        scroll.setWidget(inside)
        layout = QVBoxLayout(inside)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(8)
        # Whether one is connected, and stop it.
        self.state = QLabel()
        self.state.setObjectName("state")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        row = QHBoxLayout()
        self.pause = QPushButton(tr('Disconnect and pause'))
        self.pause.setAutoDefault(False)
        self.pause.clicked.connect(self._pause_or_allow)
        row.addWidget(self.pause)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addSpacing(4)
        layout.addWidget(_divider())
        layout.addSpacing(4)
        # What it may do.
        layout.addWidget(_title(tr('What it may do')))
        from tensela.ui.widgets import Segmented
        self.mode = Segmented([("change", 'Look and change', None), ("look", 'Only look', None)], changes.mode())
        self.mode.setObjectName("mode")
        self.mode.change.connect(self._put_mode)
        layout.addWidget(self.mode)
        self.may = QLabel()
        self.may.setObjectName("may")
        self.may.setWordWrap(True)
        self.may.setProperty("role", "secondary")
        layout.addWidget(self.may)
        layout.addSpacing(4)
        layout.addWidget(_divider())
        layout.addSpacing(4)
        # How to connect one: each text with its «Copy» on its own line, above its box.
        layout.addWidget(_title(tr('To connect your AI program')))
        self.settings = self._box("settings", settings_text(), 120)
        layout.addLayout(self._copy_row("copy_settings", self.settings,
                                        tr('In the settings of MCP servers of your AI program, add this:')))
        layout.addWidget(self.settings)
        layout.addSpacing(4)
        self.line = self._box("command", shlex.join(command()), 46)
        layout.addLayout(self._copy_row("copy_command", self.line, tr('Or, where it asks for a command:')))
        layout.addWidget(self.line)
        layout.addSpacing(10)
        # What it did, in a frame of its own.
        frame = QFrame()
        frame.setObjectName("history")
        from tensela.ui import theme
        frame.setStyleSheet(f"QFrame#history {{ border: 1px solid {theme.color('border', '#dfe2e9')}; "
                            f"border-radius: 10px; }}")
        history = QVBoxLayout(frame)
        history.setContentsMargins(12, 10, 12, 12)
        history.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_title(tr('What it did')))
        head.addStretch(1)
        clear = QPushButton(tr('Clear'))
        clear.setAutoDefault(False)
        clear.clicked.connect(lambda: (self.server.done.clear(), self.refresh()))
        head.addWidget(clear)
        history.addLayout(head)
        self.done = QListWidget()
        self.done.setObjectName("done")
        self.done.setFrameShape(QFrame.Shape.NoFrame)
        self.done.setMinimumHeight(160)
        self.done.setWordWrap(True)                        # a long step goes on in the next line, not sideways
        self.done.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        history.addWidget(self.done, 1)
        layout.addWidget(frame, 1)
        server.changed.connect(self.refresh)
        self.refresh()

    def _box(self, name: str, text: str, height: int) -> QPlainTextEdit:
        box = QPlainTextEdit(text)
        box.setObjectName(name)
        box.setReadOnly(True)
        box.setFixedHeight(height)
        box.setStyleSheet("font-family: monospace; font-size: 11px;")
        return box

    def _copy_row(self, name: str, box: QPlainTextEdit, text: str) -> QHBoxLayout:
        """What the box is, and its «Copy» on the right, on one line above it."""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._secondary(text), 1)
        button = QPushButton(tr('Copy'))
        button.setObjectName(name)
        button.setAutoDefault(False)
        button.clicked.connect(lambda _=False: self._copy(box, button))
        row.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
        return row

    def _put_mode(self, key: str) -> None:
        from PySide6.QtCore import QSettings
        QSettings().setValue(changes.MODE, key)
        self.refresh()

    def _secondary(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("role", "secondary")
        return label

    def _copy(self, box: QPlainTextEdit, button: QPushButton) -> None:
        QGuiApplication.clipboard().setText(box.toPlainText())
        button.setText(tr('Copied'))
        QTimer.singleShot(1500, lambda: button.setText(tr('Copy')))

    def _pause_or_allow(self) -> None:
        if self.server.listening:
            self.server.pause()
        else:
            self.server.start()

    def refresh(self) -> None:
        from tensela.ui import theme
        s = self.server
        if s.problem:
            colour, text = theme.color("danger", "#e0605a"), tr('Could not listen: {error}').format(error=s.problem)
        elif not s.listening:
            colour, text = theme.color("warning", "#d99a2b"), tr('Paused: no AI program can connect')
        elif s.connected():
            colour, text = theme.color("recomputed", "#3a9d5d"), tr('Connected: {name}').format(
                name=", ".join(dict.fromkeys(s.connected())))
        else:
            colour, text = theme.color("text_2", "#9ca1b0"), tr('Waiting for an AI program')
        self.state.setText(f"<span style='color:{colour}; font-size:15px'>●</span>&nbsp; <b>{text}</b>")
        self.pause.setText(tr('Disconnect and pause') if s.listening else tr('Allow again'))
        self.may.setText(tr('It looks at the open project (its nodes, values, errors, the 3D view) and changes it: '
                            'each step is undone with Ctrl+Z. Code nodes and files (open, save, export) ask you '
                            'first.')
                         if changes.mode() == "change" else
                         tr('It looks at the open project (its nodes, values, errors, the 3D view), but cannot change '
                            'anything.'))
        self.done.clear()
        if not s.done:
            self.done.addItem(QListWidgetItem(tr('Nothing yet.')))
        for when, who, what, good in reversed(s.done):
            self.done.addItem(QListWidgetItem(f"{when}  {'✓' if good else '✖'}  {what}  ·  {who}"))
