"""The Help menu: the manual (the one that comes with Tensela, read without internet, or the one of the site), the
part of the manual about a node, the links of the project, and the window About Tensela.

The manual that comes with Tensela is the one-file HTML of each language that the site builds
(`tensela-manual-en.html`, `tensela-manual-es.html`); `tools/bundle_manual.py` copies it into `tensela/help/`. If it
is not there (working from the code), the same pages open on tensela.com.

Nothing here reaches the network by itself: each link opens the browser only when it is clicked.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QHBoxLayout

from .. import __version__, language
from ..language import tr

HELP = Path(__file__).resolve().parent.parent / "help"
SITE = "https://tensela.com"
REPOSITORY = "https://github.com/tensela/tensela"

#: The page of the manual of each family of nodes.
PAGES = {"Values": "values", "Shapes": "shapes", "Curves": "curves", "Surfaces": "surfaces", "Divide": "divide",
         "Measure": "measure", "Transform": "transform", "Meshes": "meshes", "Fabrication": "fabrication",
         "Environment": "environment", "Simulation": "simulation", "Groups": "groups"}

#: The libraries and fonts Tensela is built with, and their licences (shown in About Tensela → Licences).
THIRD_PARTY = [
    ("Qt and Qt for Python (PySide6)", "LGPL-3.0", "https://www.qt.io/qt-for-python"),
    ("VTK", "BSD-3-Clause", "https://vtk.org"),
    ("PyVista and pyvistaqt", "MIT", "https://pyvista.org"),
    ("NumPy", "BSD-3-Clause", "https://numpy.org"),
    ("Manifold (manifold3d)", "Apache-2.0", "https://github.com/elalish/manifold"),
    ("ezdxf", "MIT", "https://ezdxf.mozman.at"),
    ("Pillow", "MIT-CMU", "https://python-pillow.org"),
    ("fontTools", "MIT", "https://github.com/fonttools/fonttools"),
    ("Inter (font)", "SIL Open Font License 1.1", "https://rsms.me/inter/"),
    ("JetBrains Mono (font)", "SIL Open Font License 1.1", "https://www.jetbrains.com/lp/mono/"),
]


def _lang() -> str:
    """The language of the manual: that of the window, if the manual comes in it; if not, English."""
    return language.LANGUAGE if (HELP / f"tensela-manual-{language.LANGUAGE}.html").is_file() else "en"


def online_manual(lang: str | None = None) -> QUrl:
    """The manual on the site (always up to date, with the interactive map of the nodes)."""
    lang = lang or _lang()
    return QUrl(f"{SITE}/manual/" if lang == "en" else f"{SITE}/{lang}/manual/")


def manual_file(lang: str | None = None) -> Path | None:
    """The manual that comes with Tensela, in a language, if it is there."""
    path = HELP / f"tensela-manual-{lang or _lang()}.html"
    return path if path.is_file() else None


def anchor(name: str) -> str:
    """The anchor of a heading of the manual, as the site makes it: lower case, without punctuation, spaces as
    hyphens, accents kept («Análisis de barras» → «análisis-de-barras»)."""
    return re.sub(r"[^\w\- ]", "", name.lower()).replace(" ", "-")


def manual_url(page: str | None = None, heading: str | None = None, lang: str | None = None) -> QUrl:
    """Where a page of the manual (and a heading in it) is: in the manual that comes with Tensela, or on the site.
    `page` is the path inside the manual («nodes/curves»); none, the welcome."""
    lang = lang or _lang()
    local = manual_file(lang)
    if local is not None:
        url = QUrl.fromLocalFile(str(local))
        if page:
            # In the one-file manual each page is a section; its headings carry the page in front.
            section = page.replace("/", "-")
            url.setFragment(f"{section}--{heading}" if heading else section)
        return url
    url = QUrl(online_manual(lang).toString() + (page.strip("/") + "/" if page else ""))
    if heading:
        url.setFragment(heading)
    return url


def node_place(kind) -> tuple[str | None, str | None]:
    """The page of the manual about a kind of node, and its heading there (the name of the node in the language of
    the window). A group made in the project has no page of its own: the page of groups."""
    category = getattr(kind, "category", None)
    page = PAGES.get(category)
    if page is None:
        return "nodes/groups", None
    return f"nodes/{page}", anchor(tr(kind.name))


def open_url(url: QUrl | str) -> None:
    """Opens an address in the browser. A page of the manual on this computer with a heading (`…html#section`) goes
    through a small page that jumps there: the desktop opens local files by their path, and the part after «#» would
    make it look for a file that does not exist."""
    url = url if isinstance(url, QUrl) else QUrl(url)
    if url.isLocalFile() and url.hasFragment():
        url = QUrl.fromLocalFile(str(jump_page(url)))
    QDesktopServices.openUrl(url)


def jump_page(target: QUrl) -> Path:
    """A page that takes the browser to `target` (a local file with its heading), written in the cache of Tensela."""
    import html
    import os
    import tempfile
    cache = Path(os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")) / "tensela"
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        cache = Path(tempfile.gettempdir())
    address = target.toString(QUrl.ComponentFormattingOption.FullyEncoded)
    page = cache / "manual.html"
    page.write_text(
        '<!doctype html><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0; url={html.escape(address)}">'
        f'<script>location.replace({address!r});</script>'
        f'<a href="{html.escape(address)}">Tensela</a>', encoding="utf-8")
    return page


def link(path: str) -> str:
    """An address of the site in the language of the window («/donate/» → «https://tensela.com/es/donate/»)."""
    return f"{SITE}/es{path}" if _lang() == "es" else f"{SITE}{path}"


LINKS = {
    "pdf": lambda: link("/manual/download-this-manual/"),
    "community": lambda: f"{REPOSITORY}/discussions",
    "report": lambda: f"{REPOSITORY}/issues/new",
    "donate": lambda: link("/donate/"),
}


def credits_text() -> str:
    """The thanks: the file CREDITS.md that comes with Tensela (CREDITS.es.md in Spanish), in Markdown."""
    for name in (("CREDITS.es.md",) if _lang() == "es" else ()) + ("CREDITS.md",):
        path = HELP / name
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return ""


class DialogAbout(QDialog):
    """About Tensela: what it is and its licence; the people to thank (a list that grows, scrolling slowly when it is
    long); and the libraries and fonts it is built with, with their licences."""

    def __init__(self, parent=None, icon: QIcon | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr('About Tensela'))
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        about = QLabel()
        about.setTextFormat(Qt.TextFormat.RichText)
        about.setOpenExternalLinks(True)
        about.setWordWrap(True)
        about.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        picture = ""
        if icon is not None and not icon.isNull():
            import base64
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            icon.pixmap(96, 96).save(buffer, "PNG")
            picture = f'<p><img src="data:image/png;base64,{base64.b64encode(bytes(data)).decode()}" width="96"></p>'
        about.setText(
            f'<div style="text-align:center">{picture}'
            f'<h2 style="margin:4px 0">Tensela</h2>'
            f'<p>{tr("Version")} {__version__}</p>'
            f'<p><b>{tr("Weave the design.")}</b><br>{tr("Parametric design an architect understands.")}</p>'
            f'<p>{tr("Made by Victor Crespo.")}<br><a href="{link("/")}">tensela.com</a></p>'
            f'<p>{tr("Free software under the GNU General Public License, version 3 or later: you can use it for "
                     "anything, study it, share it and change it.")}<br>'
            f'<a href="https://www.gnu.org/licenses/gpl-3.0.html">GPL-3.0</a> · '
            f'<a href="{REPOSITORY}">{tr("Source code")}</a></p>'
            f'<p>{tr("It works on your computer, without internet: it sends nothing anywhere.")}</p>'
            f'<p><small>{tr("It comes without warranty: have a professional check the results that carry "
                            "responsibility.")}<br><a href="{link("/legal/")}">{tr("Licence, warranty and privacy")}</a>'
            f'</small></p></div>')
        about.setContentsMargins(16, 16, 16, 16)
        tabs.addTab(about, tr('About'))

        self.thanks = QTextBrowser()
        self.thanks.setOpenExternalLinks(True)
        self.thanks.setMarkdown(credits_text())
        tabs.addTab(self.thanks, tr('Thanks'))
        self._roll = QTimer(self)
        self._roll.timeout.connect(self._scroll_thanks)
        self._roll.start(60)

        licences = QTextBrowser()
        licences.setOpenExternalLinks(True)
        rows = "".join(f'<tr><td><a href="{url}">{name}</a></td><td style="padding-left:16px">{licence}</td></tr>'
                       for name, licence, url in THIRD_PARTY)
        licences.setHtml(f'<p>{tr("Tensela is built with these libraries and fonts. Thank you to their authors.")}'
                         f'</p><table>{rows}</table>')
        tabs.addTab(licences, tr('Licences'))

        foot = QHBoxLayout()
        foot.addStretch(1)
        close = QPushButton(tr('Close'))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        layout.addLayout(foot)

    def _scroll_thanks(self) -> None:
        """The thanks roll by slowly when they do not fit, and stop while the pointer is over them."""
        bar = self.thanks.verticalScrollBar()
        if bar.maximum() <= 0 or self.thanks.underMouse() or not self.thanks.isVisible():
            return
        bar.setValue(0 if bar.value() >= bar.maximum() else bar.value() + 1)
