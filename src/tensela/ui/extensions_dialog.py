"""Extensions → Manage extensions…: those installed, each one a card with what it does, what it may do besides
computing, who makes it and its links (on the left), and its switch (on the right, apart); «Remove» and its links
in its «⋯» menu. «Install from a file…» shows its card first, with what it asks for, before installing (and, if it is
already installed, whether it updates it, is older or the same).

On top, to find one among many: a search (name, what it does, who makes it; without minding accents), what to show
(all, on, off, those that come with Tensela, those that ask for permissions), the order (name, recently installed,
on first) and the two ways of seeing them: detailed (each one a card) and compact (one line each, which opens with a
click). The order and the way of seeing are remembered.

Tensela does not look for extensions on the internet: they come as a .zip, from the Extensions page of tensela.com
or from whoever makes them. An extension is a program: the window says so before installing one.
"""
from __future__ import annotations

from pathlib import Path

import unicodedata

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget)

from .. import extensions as E
from ..data import ShapeError
from ..language import tr
from . import icons, theme
from .widgets import Switch, button_icon

#: Where extensions are found (the catalogue is the site: Tensela itself does not connect).
CATALOGUE = "https://tensela.com/extensions/"
#: What it may do besides computing: its icon, what it is when it asks for it and when it does not.
ASKS = {
    "network": ("globe", 'It connects to the internet', 'It does not connect to the internet', 'Internet'),
    "files": ("folder", 'It reads or writes files outside the project', 'It does not touch files outside the project',
              'Files'),
    "programs": ("program", 'It starts other programs', 'It does not start other programs', 'Programs'),
    "local": ("plug", 'It talks with other programs on this computer (not on the internet)',
              'It does not talk with other programs', 'Other programs'),
}


#: What to show: key → its text.
SHOW = {"all": 'All', "on": 'Those on', "off": 'Those off', "bundled": 'Come with Tensela',
        "asks": 'Ask for permissions', "development": 'In development'}
#: The order: key → its text.
ORDER = {"name": 'Name', "recent": 'Recently installed', "on": 'On first'}
DETAILED, COMPACT = "detailed", "compact"


def _plain(text: str) -> str:
    """Without capitals or accents, to search."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")


def found_by(ext: E.Extension, words: str) -> bool:
    """Whether every word searched is in its name, what it does, who makes it or its id (without minding accents)."""
    where = _plain(" ".join((ext.said("name"), ext.name, ext.said("description"), ext.author, ext.id)))
    return all(word in where for word in _plain(words).split())


def ordered(found: list, order: str, on: list[str]) -> list:
    """`found` (Extension) in the order asked for; those with the same, by name."""
    by_name = sorted(found, key=lambda e: _plain(e.said("name")))
    if order == "recent":                              # the last installed first; those of Tensela at the end
        def when(e):
            try:
                return -e.path.stat().st_mtime if (e.path is not None and not e.bundled) else float("inf")
            except OSError:
                return float("inf")
        return sorted(by_name, key=when)
    if order == "on":
        return sorted(by_name, key=lambda e: e.id not in on)
    return by_name


def shown(found: list, show: str, on: list[str]) -> list:
    keep = {"all": lambda e: True, "on": lambda e: e.id in on, "off": lambda e: e.id not in on,
            "bundled": lambda e: e.bundled, "asks": lambda e: bool(e.permissions),
            "development": lambda e: e.development}[show]
    return [e for e in found if keep(e)]


def version_note(ext: E.Extension, replaces: E.Extension | None) -> tuple[str, str]:
    """Installing over one that is there: what it does («updates», «older», «the same») and its colour key."""
    if replaces is None:
        return "", ""
    if replaces.bundled:
        return tr('It takes the place of the one that comes with Tensela ({version}).').format(
            version=replaces.version), "accent"
    sign = E.compare(ext.version, replaces.version)
    if sign > 0:
        return tr('It updates the one installed: {old} → {new}. If it was on, it stays on.').format(
            old=replaces.version, new=ext.version), "accent"
    if sign < 0:
        return tr('It is older than the one installed ({old} → {new}): it goes back to an earlier version.').format(
            old=replaces.version, new=ext.version), "warn"
    return tr('It is the same version as the one installed ({version}): it installs it again.').format(
        version=ext.version), "soft"


def _colours() -> dict:
    return {"ok": theme.color("recomputed", "#3a9d5d"), "warn": theme.color("warning", "#d99a2b"),
            "danger": theme.color("danger", "#e0605a"), "soft": theme.color("text_2", "#9ca1b0"),
            "border": theme.color("border", "#dfe2e9"), "accent": theme.color("accent", "#5b4bf0"),
            "accent_soft": theme.color("accent_soft", "#e7e4ff")}


def _icon(name: str, colour: str, px: int = 16) -> QLabel:
    label = QLabel()
    label.setPixmap(icons.icon(name, colour, px).pixmap(px, px))
    label.setFixedSize(px + 2, px + 2)
    return label


def _divider(vertical: bool = False) -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine if vertical else QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {_colours()['border']}; background: {_colours()['border']};")
    line.setFixedWidth(1) if vertical else line.setFixedHeight(1)
    return line


def _small(text: str, colour: str | None = None, rich: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {colour or _colours()['soft']}; font-size: 12px;")
    if rich:
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
    return label


def capabilities(ext: E.Extension) -> QWidget:
    """«What it can do»: one row for each thing it may do besides computing, green if it does not, amber (with why)
    if it does."""
    c = _colours()
    box = QWidget()
    column = QVBoxLayout(box)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(6)
    rows = [("check", c["ok"], tr('It works inside Tensela: nodes, panels, menu entries, ways of exporting'), "")]
    for key, (icon, asked, not_asked, _) in ASKS.items():
        if key in ext.permissions:
            rows.append((icon, c["warn"], tr(asked), ext.why(key) or tr('It does not say why.')))
        else:
            rows.append(("check", c["ok"], tr(not_asked), ""))
    for icon, colour, text, why in rows:
        line = QHBoxLayout()
        line.setSpacing(8)
        line.addWidget(_icon(icon, colour), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        title = QLabel(text)
        title.setWordWrap(True)
        if colour == c["warn"]:
            title.setStyleSheet("font-weight: 600;")
        texts.addWidget(title)
        if why:
            texts.addWidget(_small(why))
        line.addLayout(texts, 1)
        column.addLayout(line)
    return box


def links(ext: E.Extension) -> str:
    """Its links (website, where to report a problem, its code, how to reach its maker), as rich text."""
    found = [(ext.website, tr('Website')), (ext.issues, tr('Report a problem')), (ext.source, tr('Code'))]
    if ext.contact:
        found.append((ext.contact if ext.contact.startswith(("http", "mailto:")) else "mailto:" + ext.contact,
                      tr('Contact')))
    colour = _colours()["accent"]
    return "  ·  ".join(f'<a style="color:{colour}" href="{url}">{text}</a>' for url, text in found if url)


def who(ext: E.Extension) -> str:
    """By whom, under what licence, and where it comes from."""
    parts = [tr('by {author}').format(author=ext.author)] if ext.author else []
    if ext.licence:
        parts.append(ext.licence)
    parts.append(tr('in development, from {folder}').format(folder=ext.path) if ext.development else
                 tr('comes with Tensela') if ext.bundled else
                 tr('installed from a file on {date}').format(date=ext.installed()) if ext.installed() else
                 tr('installed from a file'))
    return "  ·  ".join(parts)


class InstallDialog(QDialog):
    """Before installing: its card, what it can do, its links and the warning; «Install» or «Cancel»."""

    def __init__(self, parent, ext: E.Extension, replaces: E.Extension | None = None):
        super().__init__(parent)
        c = _colours()
        self.setWindowTitle(tr('Install an extension'))
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(_icon("extension", c["accent"], 36), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(f"<span style='font-size:17px; font-weight:600'>{ext.said('name')}</span>"
                       f"&nbsp;&nbsp;<span style='color:{c['soft']}'>{ext.version}</span>")
        texts.addWidget(title)
        texts.addWidget(_small(who(ext).replace(tr('installed from a file'), "").strip(" ·")))
        if ext.said("description"):
            description = QLabel(ext.said("description"))
            description.setWordWrap(True)
            texts.addWidget(description)
        head.addLayout(texts, 1)
        layout.addLayout(head)
        note, colour = version_note(ext, replaces)
        if note:
            said = _small(note, c[colour])
            said.setObjectName("version_note")
            if colour == "warn":
                said.setStyleSheet(said.styleSheet() + " font-weight: 600;")
            layout.addWidget(said)
        layout.addWidget(_divider())
        caption = QLabel(tr('What it can do'))
        caption.setStyleSheet("font-weight: 600;")
        layout.addWidget(caption)
        layout.addWidget(capabilities(ext))
        if links(ext):
            layout.addWidget(_divider())
            layout.addWidget(_small(links(ext), rich=True))
        warning = QFrame()
        warning.setStyleSheet(f"QFrame {{ border: 1px solid {c['warn']}; border-radius: 8px; }}"
                              f"QLabel {{ border: none; }}")
        row = QHBoxLayout(warning)
        row.addWidget(_icon("warning", c["warn"], 18), 0, Qt.AlignmentFlag.AlignTop)
        said = QLabel(tr('An extension is a program: install it only if it comes from someone you trust. '
                         'Tensela shows what it says it does, but cannot check it.'))
        said.setWordWrap(True)
        row.addWidget(said, 1)
        layout.addWidget(warning)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr('Cancel'))
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        install = QPushButton(tr('Install'))
        install.setDefault(True)
        install.clicked.connect(self.accept)
        buttons.addWidget(install)
        layout.addLayout(buttons)


class ExtensionsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr('Extensions'))
        self.setMinimumSize(640, 480)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel(tr('What is added to Tensela without changing it: nodes, panels, entries in the menus, ways of '
                          'exporting. An extension is a program: install only those that come from someone you '
                          'trust.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        colour = _colours()["accent"]
        layout.addWidget(_small(tr('They are found on the {page} of tensela.com (each with its page, what it asks '
                                   'for and where to report a problem) or with whoever makes them. Tensela does not '
                                   'look for them by itself: it does not connect to the internet.').format(
            page=f'<a style="color:{colour}" href="{CATALOGUE}">{tr("Extensions page")}</a>'), rich=True))
        settings = QSettings()
        top = QHBoxLayout()
        top.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Search extensions…'))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self.fill())
        top.addWidget(self.search, 1)
        self.show_ = QComboBox()
        for key, text in SHOW.items():
            self.show_.addItem(tr(text), key)
        self.show_.setToolTip(tr('Which to show'))
        self.show_.currentIndexChanged.connect(lambda *_: self.fill())
        top.addWidget(self.show_)
        self.order = QComboBox()
        for key, text in ORDER.items():
            self.order.addItem(tr(text), key)
        self.order.setToolTip(tr('In what order'))
        self.order.setCurrentIndex(max(0, self.order.findData(settings.value("extensions/order", "name"))))
        self.order.currentIndexChanged.connect(lambda *_: (
            QSettings().setValue("extensions/order", self.order.currentData()), self.fill()))
        top.addWidget(self.order)
        self.views = {DETAILED: button_icon("list_view", 'Detailed: each one a card', checkable=True),
                      COMPACT: button_icon("rows", 'Compact: one line each (a click opens it)', checkable=True)}
        for key, button in self.views.items():
            button.clicked.connect(lambda _=False, k=key: self.put_view(k))
            top.addWidget(button)
        layout.addLayout(top)
        self.view = DETAILED if settings.value("extensions/view", DETAILED) != COMPACT else COMPACT
        for key, button in self.views.items():
            button.setChecked(key == self.view)
        self._open: set[str] = set()                     # compact: those opened with a click
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self._scroll, 1)
        buttons = QHBoxLayout()
        install = QPushButton(tr('Install from a file…'))
        install.setToolTip(tr('A .zip of an extension, from the Extensions page of the site or from whoever made it'))
        install.clicked.connect(lambda: self.install())
        install.setAutoDefault(False)                    # (focused, it would become the main one: only Close is)
        buttons.addWidget(install)
        develop = QPushButton(tr('Load a folder…'))
        develop.setToolTip(tr('To write an extension: it is loaded from its folder, without installing it; «Reload» '
                              'after each change'))
        develop.clicked.connect(lambda: self.develop())
        develop.setAutoDefault(False)
        buttons.addWidget(develop)
        where = QPushButton(tr('Open the folder'))
        where.setToolTip(str(E.folder()))
        where.clicked.connect(self._open_folder)
        where.setAutoDefault(False)
        buttons.addWidget(where)
        buttons.addStretch(1)
        close = QPushButton(tr('Close'))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.fill()

    def put_view(self, view: str) -> None:
        """Detailed or compact (remembered)."""
        self.view = view
        for key, button in self.views.items():
            button.setChecked(key == view)
        QSettings().setValue("extensions/view", view)
        self.fill()

    def listed(self) -> list:
        """Those that the search, what to show and the order leave, in that order."""
        on = self.window.extensions_on()
        found = [e for e in E.available() if found_by(e, self.search.text())]
        return ordered(shown(found, self.show_.currentData(), on), self.order.currentData(), on)

    def fill(self) -> None:
        position = self._scroll.verticalScrollBar().value()
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 4, 4, 4)
        column.setSpacing(10 if self.view == DETAILED else 6)
        everything = E.available()
        found = self.listed()
        if not found:
            empty = QLabel(tr('No extension yet. Install one from a file.') if not everything else
                           tr('No extension matches. Change the search or what to show.'))
            empty.setObjectName("empty")
            empty.setProperty("role", "secondary")
            column.addWidget(empty)
        for ext in found:
            column.addWidget(self._card(ext) if self.view == DETAILED else self._line(ext))
        column.addStretch(1)
        self._scroll.setWidget(content)
        self._scroll.verticalScrollBar().setValue(position)
        count = len(everything)
        self.setWindowTitle(tr('Extensions') + (f" ({len(found)} / {count})" if len(found) != count else
                                                f" ({count})" if count else ""))

    def _card(self, ext: E.Extension) -> QWidget:
        c = _colours()
        card = QFrame()
        card.setObjectName("extension_card")
        card.setStyleSheet(f"QFrame#extension_card {{ border: 1px solid {c['border']}; border-radius: 10px; }}")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)
        row.addWidget(_icon("extension", c["accent"], 28), 0, Qt.AlignmentFlag.AlignTop)
        # On the left, what it is.
        info = QVBoxLayout()
        info.setSpacing(4)
        title = QLabel(f"<span style='font-size:15px; font-weight:600'>{ext.said('name')}</span>"
                       f"&nbsp;&nbsp;<span style='color:{c['soft']}'>{ext.version}</span>")
        info.addWidget(title)
        if ext.said("description"):
            description = QLabel(ext.said("description"))
            description.setWordWrap(True)
            info.addWidget(description)
        asks = QHBoxLayout()
        asks.setSpacing(6)
        if not ext.permissions:
            asks.addWidget(_icon("check", c["ok"], 14))
            asks.addWidget(_small(tr('Only computes'), c["ok"]))
        for key in ext.permissions:
            if key in ASKS:
                icon, asked, _, short = ASKS[key]
                why = f"{tr(asked)}: {ext.why(key) or tr('It does not say why.')}"
                mark = _icon(icon, c["warn"], 14)
                mark.setToolTip(why)
                asks.addWidget(mark)
                chip = _small(tr(short), c["warn"])
                chip.setWordWrap(False)
                chip.setToolTip(why)
                asks.addWidget(chip)
        asks.addStretch(1)
        info.addLayout(asks)
        info.addWidget(_small(who(ext)))
        if links(ext):
            info.addWidget(_small(links(ext), rich=True))
        if ext.problem:
            info.addWidget(_small("✖ " + tr('It cannot be used: {problem}').format(problem=ext.problem), c["danger"]))
        row.addLayout(info, 1)
        row.addWidget(_divider(vertical=True))
        # On the right, apart: on or off, and the rest in «⋯».
        controls = QVBoxLayout()
        controls.setSpacing(4)
        switch, state = self._switch(ext)
        controls.addWidget(switch, 0, Qt.AlignmentFlag.AlignHCenter)
        controls.addWidget(state, 0, Qt.AlignmentFlag.AlignHCenter)
        controls.addStretch(1)
        if ext.development:
            controls.addWidget(self._reload(ext), 0, Qt.AlignmentFlag.AlignHCenter)
        controls.addWidget(self._more(ext), 0, Qt.AlignmentFlag.AlignHCenter)
        box = QWidget()
        box.setLayout(controls)
        box.setFixedWidth(92)
        row.addWidget(box)
        return card

    def _switch(self, ext: E.Extension, with_state: bool = True) -> tuple[Switch, QLabel]:
        on = ext.id in self.window.extensions_on()
        switch = Switch("", on)
        switch.setObjectName(f"switch_{ext.id}")
        switch.setEnabled(not ext.problem)
        switch.setToolTip(tr('On or off, at once'))
        state = _small(tr('On') if on else tr('Off'))
        state.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        state.setVisible(with_state)
        switch.toggled.connect(lambda yes, e=ext, s=switch, t=state: self._turn(e, yes, s, t))
        return switch, state

    def _more(self, ext: E.Extension) -> QToolButton:
        more = QToolButton()
        more.setObjectName(f"more_{ext.id}")
        more.setIcon(icons.icon("mas", _colours()["soft"], 16))
        more.setToolTip(tr('Its links, its folder, remove it'))
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        more.setMenu(self._menu(ext, more))
        return more

    def _reload(self, ext: E.Extension) -> QToolButton:
        button = QToolButton()
        button.setObjectName(f"reload_{ext.id}")
        button.setIcon(icons.icon("reload", _colours()["accent"], 16))
        button.setToolTip(tr('Reload: its code again, after a change (it is turned on if it was off)'))
        button.clicked.connect(lambda _=False, e=ext: self.reload(e))
        return button

    def develop(self, path: str | None = None) -> None:
        """Load a folder…: an extension being written, from where it is (not installed); on at once."""
        if not path:
            path = QFileDialog.getExistingDirectory(self, tr('The folder of the extension (with its extension.toml)'),
                                                    str(Path.home()))
        if not path:
            return
        try:
            ext = E.develop(Path(path))
        except ShapeError as error:
            QMessageBox.warning(self, tr('Load a folder'), str(error))
            return
        if ext.id in self.window.extensions_on():
            self.window.turn_extension(ext.id, False)
        said = self.window.turn_extension(ext.id, True) if not ext.problem else ext.problem
        self.fill()
        if said:
            QMessageBox.warning(self, tr('Extensions'), said)
        else:
            self.window.statusBar().showMessage(tr('In development and on: {name}. «Reload» after each change.')
                                                .format(name=ext.said("name")), 10000)

    def reload(self, ext: E.Extension) -> None:
        """Its code again: off (what it added goes) and on (read again from its folder)."""
        self.window.turn_extension(ext.id, False)
        said = self.window.turn_extension(ext.id, True)
        self.fill()
        if said:
            QMessageBox.warning(self, tr('Extensions'), said)
        else:
            self.window.statusBar().showMessage(tr('Reloaded: {name}.').format(name=ext.said("name")), 6000)

    def _line(self, ext: E.Extension) -> QWidget:
        """Compact: one line (its name, version and what it asks for, then its switch and «⋯»); a click on it opens
        what it does, who makes it and its links below."""
        c = _colours()
        card = QFrame()
        card.setObjectName("extension_line")
        card.setStyleSheet(f"QFrame#extension_line {{ border: 1px solid {c['border']}; border-radius: 8px; }}")
        column = QVBoxLayout(card)
        column.setContentsMargins(10, 4, 8, 4)
        column.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        opened = ext.id in self._open
        arrow = QToolButton()
        arrow.setObjectName(f"open_{ext.id}")
        arrow.setAutoRaise(True)
        arrow.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        arrow.setToolTip(tr('What it does, who makes it, its links'))
        arrow.clicked.connect(lambda _=False, e=ext: self._toggle_open(e))
        row.addWidget(arrow)
        row.addWidget(_icon("extension", c["accent"], 18))
        name = QLabel(f"<b>{ext.said('name')}</b>&nbsp;&nbsp;<span style='color:{c['soft']}'>{ext.version}</span>")
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        name.mousePressEvent = lambda _event, e=ext: self._toggle_open(e)
        row.addWidget(name)
        if ext.problem:
            row.addWidget(_small("✖", c["danger"]))
        for key in ext.permissions:
            if key in ASKS:
                icon, asked, _, short = ASKS[key]
                mark = _icon(icon, c["warn"], 14)
                mark.setToolTip(f"{tr(asked)}: {ext.why(key) or tr('It does not say why.')}")
                row.addWidget(mark)
        row.addStretch(1)
        row.addWidget(_divider(vertical=True))
        if ext.development:
            row.addWidget(self._reload(ext))
        switch, _ = self._switch(ext, with_state=False)
        row.addWidget(switch)
        row.addWidget(self._more(ext))
        column.addLayout(row)
        if opened:
            details = QVBoxLayout()
            details.setContentsMargins(52, 0, 0, 4)
            details.setSpacing(3)
            if ext.said("description"):
                description = QLabel(ext.said("description"))
                description.setWordWrap(True)
                details.addWidget(description)
            details.addWidget(_small(tr('Only computes') if not ext.permissions else "  ·  ".join(
                f"{tr(ASKS[k][3])}: {ext.why(k) or tr('It does not say why.')}" for k in ext.permissions if k in ASKS),
                c["ok"] if not ext.permissions else c["warn"]))
            details.addWidget(_small(who(ext)))
            if links(ext):
                details.addWidget(_small(links(ext), rich=True))
            if ext.problem:
                details.addWidget(_small("✖ " + tr('It cannot be used: {problem}').format(problem=ext.problem),
                                         c["danger"]))
            column.addLayout(details)
        return card

    def _toggle_open(self, ext: E.Extension) -> None:
        self._open ^= {ext.id}
        self.fill()

    def _menu(self, ext: E.Extension, parent) -> QMenu:
        menu = QMenu(parent)
        for url, text in ((ext.website, 'Website'), (ext.issues, 'Report a problem'), (ext.source, 'Code')):
            if url:
                menu.addAction(tr(text), lambda u=url: QDesktopServices.openUrl(QUrl(u)))
        if ext.path is not None:
            menu.addAction(tr('Open its folder'), lambda p=ext.path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(p))))
        menu.addSeparator()
        if ext.development:
            menu.addAction(tr('Stop developing it (its folder stays as it is)'), lambda e=ext: self.stop_developing(e))
            return menu
        remove = menu.addAction(tr('Remove…'), lambda e=ext: self.remove(e))
        if ext.bundled:
            remove.setEnabled(False)
            remove.setText(tr('It comes with Tensela: it can only be turned off'))
        return menu

    def _turn(self, ext: E.Extension, yes: bool, switch: Switch, state: QLabel) -> None:
        said = self.window.turn_extension(ext.id, yes)
        if said:                                         # it failed when turned on: back off, and said
            switch.blockSignals(True)
            switch.setChecked(False)
            switch.blockSignals(False)
            QMessageBox.warning(self, tr('Extensions'), said)
        state.setText(tr('On') if switch.isChecked() else tr('Off'))

    def install(self, path: str | None = None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr('Install an extension'), str(Path.home()),
                                                  tr('Extension of Tensela (*.zip)'))
        if not path:
            return
        try:
            ext, _ = E.look_inside(Path(path))
        except ShapeError as error:
            QMessageBox.warning(self, tr('Install an extension'), str(error))
            return
        replaces = next((e for e in E.available() if e.id == ext.id), None)
        if self._ask(ext, replaces) != QDialog.DialogCode.Accepted:
            return
        was_on = ext.id in self.window.extensions_on()
        if was_on:
            self.window.turn_extension(ext.id, False)
        try:
            installed = E.install(Path(path))
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Install an extension'), str(error))
            if was_on:
                self.window.turn_extension(ext.id, True)
            self.fill()
            return
        if replaces is not None and not was_on:          # it was there and off: it stays off
            self.fill()
            self.window.statusBar().showMessage(tr('Extension installed ({version}), off as it was: {name}.').format(
                version=installed.version, name=installed.said("name")), 8000)
            return
        said = self.window.turn_extension(installed.id, True)
        self.fill()
        if said:
            QMessageBox.warning(self, tr('Extensions'), said)
        else:
            self.window.statusBar().showMessage(tr('Extension installed and on: {name}.').format(
                name=installed.said("name")), 8000)

    def _ask(self, ext: E.Extension, replaces: E.Extension | None):
        """(Apart, so the tests can answer it.)"""
        return InstallDialog(self, ext, replaces).exec()

    def stop_developing(self, ext: E.Extension) -> None:
        self.window.turn_extension(ext.id, False)
        E.develop(ext.path, False)                       # (an installed one with its id comes back, off)
        self.fill()

    def remove(self, ext: E.Extension) -> None:
        answer = QMessageBox.question(self, tr('Remove an extension'), tr(
            'Remove «{name}»? Projects that use its nodes keep them, marked, until it is installed again.').format(
            name=ext.said("name")))
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.window.turn_extension(ext.id, False)
        try:
            E.uninstall(ext)
        except (ShapeError, OSError) as error:
            QMessageBox.warning(self, tr('Remove an extension'), str(error))
        self.fill()

    def _open_folder(self) -> None:
        E.folder().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(E.folder())))
