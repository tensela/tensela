"""The start screen: what Tensela shows when it opens without a project (and from File ▸ Start screen).

On the left: a new project, open one, and the way into the manual. On the right: the projects saved lately, each one
with the picture of how it looked the last time it was saved, and «Start from a recipe»: the first project of the
manual and its recipes, which travel inside Tensela (`tensela/templates/`) and open as a new project, without a name,
so that the original stays as it is.

The pictures of the recent projects are kept in the cache of Tensela (`~/.cache/tensela/previews/`), one per file;
without one, a woven mesh stands in its place.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import __version__
from ..language import tr
from . import help as help_module
from . import theme
from .widgets import Switch

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
PREVIEW = (480, 300)
COLUMNS = 3
CARD_WIDTH = 256
SHOW_KEY = "start/show"
#: The projects of «Start from a recipe»: the file in templates/, its title and one line about it.
RECIPES = [
    ("first-project", 'Your first project',
     'A facade with sun fins that open near a point, in seven nodes and ten minutes.'),
    ("breathing-facade", 'A facade that breathes', 'Frames whose openings grow near a point and close far from it.'),
    ("twisting-tower", 'A tower that turns', 'Twenty-four floors, each turned a little more than the one below.'),
    ("hypar-roof", 'A roof of hyperbolic paraboloids',
     'Six bays of a roof, each folded into a saddle of straight lines, on columns.'),
    ("rib-wall", 'A rib wall', 'A wavy wall of timber ribs from three hand-drawn curves.'),
    ("voronoi-skin", 'A Voronoi skin', 'A facade of irregular cells with open joints between them.'),
    ("hanging-vault", 'A vault that finds its own shape',
     'A membrane hung from its corners and turned upside down: a vault that works only in compression.'),
    ("waffle-model", 'A waffle model ready to cut',
     'A model of a hill as two families of boards that slot into each other, laid on sheets for the laser cutter.'),
    ("sun-study", 'A sun study',
     'The winter sun on a building in Montevideo: its shadows at three hours and the sun hours on each panel.'),
]


def show_at_start() -> bool:
    return QSettings().value(SHOW_KEY, True, type=bool)


def template(stem: str) -> Path:
    return TEMPLATES / f"{stem}.tela"


# --- The pictures of the recent projects ---------------------------------------------------------------------------

def previews_folder() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")) / "tensela" / "previews"


def preview_path(project: Path | str) -> Path:
    key = hashlib.sha1(str(Path(project).resolve()).encode("utf-8")).hexdigest()[:20]
    return previews_folder() / f"{key}.png"


def save_preview(image: QImage, project: Path | str) -> bool:
    """Keeps the picture of a project (cut to 16:10 around its centre, 480 × 300). Without room, nothing happens."""
    if image is None or image.isNull():
        return False
    w, h = image.width(), image.height()
    ratio = PREVIEW[0] / PREVIEW[1]
    if w / h > ratio:
        cut = round(h * ratio)
        image = image.copy((w - cut) // 2, 0, cut, h)
    else:
        cut = round(w / ratio)
        image = image.copy(0, (h - cut) // 2, w, cut)
    small = image.scaled(*PREVIEW, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    try:
        previews_folder().mkdir(parents=True, exist_ok=True)
        return small.save(str(preview_path(project)))
    except OSError:
        return False


def ago(seconds: float, now: float | None = None) -> str:
    """When a file was saved, in words: today, yesterday, 3 days ago, or the date."""
    now = time.time() if now is None else now
    then, today = time.localtime(seconds), time.localtime(now)
    days = (time.mktime(today[:3] + (0, 0, 0, 0, 0, -1)) - time.mktime(then[:3] + (0, 0, 0, 0, 0, -1))) / 86400
    days = round(days)
    if days <= 0:
        return tr('today')
    if days == 1:
        return tr('yesterday')
    if days < 7:
        return tr('{n} days ago').format(n=days)
    return time.strftime("%d/%m/%Y", then)


# --- The cards ------------------------------------------------------------------------------------------------------

def weave(width: int, height: int, seed: str) -> QPixmap:
    """A woven cloth, for a project without its picture: two families of threads that go over and under each other,
    turned and spaced a little differently for each name."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(theme.color("viewer", "#16181d")))
    accent = QColor(theme.color("accent", "#8a7dff"))
    grey = QColor(theme.color("text_2", "#9ca1b0"))
    shade = QColor(theme.color("viewer", "#16181d"))
    number = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16)
    step = 44 + number % 14
    ribbon = step * 0.64
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(width / 2, height / 2)
    p.rotate(-24 + (number >> 8) % 18)
    reach = int((width + height) / step) + 2
    lit = (number >> 16) % 3 + 2                         # one thread of every few, in the accent

    def colour(base: QColor, alpha: int) -> QColor:
        c = QColor(base)
        c.setAlpha(alpha)
        return c

    def piece(x: float, y: float, w: float, h: float, base: QColor, alpha: int) -> None:
        p.setPen(QPen(shade, 2))
        p.setBrush(colour(base, alpha))
        p.drawRect(QRectF(x, y, w, h))

    for i in range(-reach, reach):                       # the threads across, whole
        piece(-reach * step, i * step - ribbon / 2, 2 * reach * step, ribbon, grey, 22)
    for j in range(-reach, reach):                       # the threads along: over at every other crossing
        base, alpha = (accent, 95) if j % lit == 0 else (grey, 40)
        for i in range(-reach, reach):
            if (i + j) % 2 == 0:
                piece(j * step - ribbon / 2, i * step - ribbon / 2 - (step - ribbon) / 2, ribbon,
                      ribbon + (step - ribbon), base, alpha)
            else:
                piece(j * step - ribbon / 2, i * step + ribbon / 2, ribbon, step - ribbon, base, alpha)
    p.end()
    return pixmap


class Card(QAbstractButton):
    """A project: its picture, its name and a line under it. A click opens it."""

    IMAGE_HEIGHT = round(CARD_WIDTH * PREVIEW[1] / PREVIEW[0])
    TEXT_HEIGHT = 58

    def __init__(self, title: str, line: str, picture: QPixmap, tip: str = "", parent=None):
        super().__init__(parent)
        self.title, self.line, self.picture = title, line, picture
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(CARD_WIDTH, self.IMAGE_HEIGHT + self.TEXT_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setAccessibleName(title)

    def sizeHint(self) -> QSize:
        return QSize(CARD_WIDTH, self.IMAGE_HEIGHT + self.TEXT_HEIGHT)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        radius = 10
        whole = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        shape = QPainterPath()
        shape.addRoundedRect(whole, radius, radius)
        p.fillPath(shape, QColor(theme.color("surface", "#191b21")))
        p.save()
        p.setClipPath(shape)
        image = QRectF(0, 0, self.width(), self.IMAGE_HEIGHT)
        p.drawPixmap(image, self.picture, QRectF(self.picture.rect()))
        p.restore()
        over = self.underMouse() or self.hasFocus()
        p.setPen(QPen(QColor(theme.color("accent" if over else "border", "#2a2d36")), 1.5 if over else 1))
        p.drawPath(shape)
        p.setPen(QColor(theme.color("text", "#ecedf2")))
        title = QFont(self.font())
        title.setWeight(QFont.Weight.DemiBold)
        p.setFont(title)
        width = self.width() - 24
        p.drawText(QRectF(12, self.IMAGE_HEIGHT + 9, width, 20), Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, int(width)))
        small = QFont(self.font())
        small.setPixelSize(theme.SMALL_SIZE_)
        small.setWeight(QFont.Weight.Normal)
        p.setFont(small)
        p.setPen(QColor(theme.color("text_2", "#9ca1b0")))
        p.drawText(QRectF(12, self.IMAGE_HEIGHT + 31, width, 18), Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(self.line, Qt.TextElideMode.ElideRight, int(width)))
        p.end()


def _picture(path: Path, fallback_seed: str) -> QPixmap:
    pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
    return pixmap if not pixmap.isNull() else weave(*PREVIEW, fallback_seed)


class StartScreen(QDialog):
    """The start screen. What is chosen is said by a signal, and the screen closes."""

    new = Signal()
    open_ask = Signal()
    open_file = Signal(str)          # a project of the recent ones
    open_template = Signal(str)      # a recipe: opened as a new project, without a name
    forget_recent = Signal()

    def __init__(self, recent: list[str], icon=None, parent=None):
        super().__init__(parent)
        self.setObjectName("start_screen")
        self.setWindowTitle("Tensela")
        self.resize(1140, 720)
        accent = theme.color("accent", "#8a7dff")
        self.setStyleSheet(
            f"QFrame#start_side {{ background: {theme.color('surface', '#191b21')};"
            f" border-right: 1px solid {theme.color('border', '#2a2d36')}; }}"
            f" QLabel#start_name {{ font-size: 24px; font-weight: 650; }}"
            f" QLabel[role='start_small'] {{ color: {theme.color('text_2', '#9ca1b0')};"
            f" font-size: {theme.SMALL_SIZE_}px; }}"
            f" QLabel[role='start_heading'] {{ font-size: 17px; font-weight: 600; }}"
            f" QPushButton[role='start_link'] {{ border: 0; background: transparent; text-align: left;"
            f" padding: 4px 0; color: {theme.color('text_2', '#9ca1b0')}; }}"
            f" QPushButton[role='start_link']:hover {{ color: {accent}; }}"
            f" QFrame#start_rule {{ background: {theme.color('border', '#2a2d36')}; }}")
        whole = QHBoxLayout(self)
        whole.setContentsMargins(0, 0, 0, 0)
        whole.setSpacing(0)
        whole.addWidget(self._side(icon))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(32, 28, 32, 28)
        self._body.setSpacing(14)
        self.recent_cards = self._recent(recent)
        self._body.addSpacing(18)
        self.recipe_cards = self._recipes()
        self._body.addStretch(1)
        scroll.setWidget(body)
        whole.addWidget(scroll, 1)

    def showEvent(self, event) -> None:
        """Over the centre of the window of Tensela (or of the screen, if the window has no place yet)."""
        super().showEvent(event)
        owner = self.parentWidget().window() if self.parentWidget() is not None else None
        if owner is not None and owner.isVisible() and owner.frameGeometry().isValid():
            centre = owner.frameGeometry().center()
        else:
            centre = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry().center()
        frame = self.frameGeometry()
        frame.moveCenter(centre)
        self.move(frame.topLeft())

    # The left side.
    def _side(self, icon) -> QFrame:
        side = QFrame()
        side.setObjectName("start_side")
        side.setFixedWidth(256)
        column = QVBoxLayout(side)
        column.setContentsMargins(24, 28, 24, 20)
        column.setSpacing(8)
        if icon is not None and not icon.isNull():
            mark = QLabel()
            mark.setPixmap(icon.pixmap(56, 56))
            column.addWidget(mark)
            column.addSpacing(6)
        name = QLabel("Tensela")
        name.setObjectName("start_name")
        column.addWidget(name)
        motto = QLabel(tr("Weave the design."))
        motto.setProperty("role", "start_small")
        column.addWidget(motto)
        column.addSpacing(22)
        new = QPushButton(tr('New project'))
        new.setDefault(True)
        new.setToolTip(tr('An empty project (Ctrl+N)'))
        new.clicked.connect(lambda: self._choose(self.new.emit))
        column.addWidget(new)
        open_ = QPushButton(tr('Open…'))
        open_.setToolTip(tr('A project saved on this computer (Ctrl+O)'))
        open_.clicked.connect(lambda: self._choose(self.open_ask.emit))
        column.addWidget(open_)
        column.addSpacing(26)
        learn = QLabel(tr('Learn'))
        learn.setProperty("role", "start_small")
        column.addWidget(learn)
        links = QVBoxLayout()
        links.setSpacing(0)
        column.addLayout(links)
        for text, page in (('Your first project, step by step', "getting-started/first-project"),
                           ('Recipes', "recipes"), ('The manual', None)):
            link = QPushButton(tr(text))
            link.setProperty("role", "start_link")
            link.setFixedHeight(26)
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _=False, page=page: help_module.open_url(help_module.manual_url(page)))
            links.addWidget(link)
        column.addStretch(1)
        self.show_switch = Switch('Show when Tensela opens', show_at_start())
        self.show_switch.toggled.connect(lambda on: QSettings().setValue(SHOW_KEY, bool(on)))
        column.addWidget(self.show_switch)
        version = QLabel(f'{tr("Version")} {__version__}')
        version.setProperty("role", "start_small")
        column.addWidget(version)
        return side

    # The right side.
    def _heading(self, number: str, text: str, extra: QWidget | None = None) -> None:
        row = QHBoxLayout()
        row.setSpacing(10)
        mark = QLabel(number)
        mark.setStyleSheet(f"font-family: 'JetBrains Mono'; font-size: {theme.SMALL_SIZE_}px;"
                           f" color: {theme.color('accent', '#8a7dff')};")
        row.addWidget(mark)
        title = QLabel(text)
        title.setProperty("role", "start_heading")
        row.addWidget(title)
        rule = QFrame()
        rule.setObjectName("start_rule")
        rule.setFixedHeight(1)
        rule.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(rule, 1)
        if extra is not None:
            row.addWidget(extra)
        self._body.addLayout(row)

    def _grid(self, cards: list[Card]) -> None:
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        for i, card in enumerate(cards):
            grid.addWidget(card, i // COLUMNS, i % COLUMNS)
        grid.setColumnStretch(COLUMNS, 1)
        self._body.addLayout(grid)

    def _recent(self, recent: list[str]) -> list[Card]:
        files = [Path(r) for r in recent if Path(r).is_file()][:2 * COLUMNS]
        forget = None
        if files:
            forget = QPushButton(tr('Forget the list'))
            forget.setProperty("role", "start_link")
            forget.setCursor(Qt.CursorShape.PointingHandCursor)
            forget.clicked.connect(self._forget)
        self._heading("01", tr('Recent'), forget)
        if not files:
            empty = QLabel(tr('The projects you save will be here, with how they looked the last time.'))
            empty.setProperty("role", "start_small")
            self._body.addWidget(empty)
            self._empty_recent = empty
            return []
        cards = []
        for path in files:
            card = Card(path.stem, f"{ago(path.stat().st_mtime)} · {path.parent.name or path.parent}",
                        _picture(preview_path(path), path.name), str(path))
            card.clicked.connect(lambda _=False, p=str(path): self._choose(lambda: self.open_file.emit(p)))
            cards.append(card)
        self._grid(cards)
        return cards

    def _recipes(self) -> list[Card]:
        self._heading("02", tr('Start from a recipe'))
        cards = []
        for stem, title, line in RECIPES:
            if not template(stem).is_file():
                continue
            card = Card(tr(title), tr(line), _picture(TEMPLATES / f"{stem}.png", stem),
                        tr(line) + "\n" + tr('It opens as a new project: the recipe stays as it is.'))
            card.clicked.connect(lambda _=False, s=stem: self._choose(lambda: self.open_template.emit(str(template(s)))))
            cards.append(card)
        self._grid(cards)
        return cards

    def _forget(self) -> None:
        self.forget_recent.emit()
        for card in self.recent_cards:
            card.hide()
        self.sender().hide()

    def _choose(self, then) -> None:
        self.accept()
        then()
