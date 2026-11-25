"""The theme of the window (Delivery 5): all the colour and the shape come from a file of *tokens*.

Tensela's identity: cool graphite, indigo accent, rounded corners and the window as cards on a background
(*bento*). Each theme (ui/themes/*.json) has, in light and in dark, the colours of the interface and those of the
node canvas («tensela»: canvas, cards, wires, the colour of each category and how the header is painted: a band
or whole).

    apply(app, "sober", "dark")      # or "light", or None: like the system

A new theme is one more JSON in ui/themes/. The typeface does not change with the theme: Inter, which travels with
Tensela (ui/fonts, OFL licence).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from string import Template

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette

THEMES = Path(__file__).resolve().parent / "themes"
FONTS = Path(__file__).resolve().parent / "fonts"
FAMILIES = ("Inter", "Noto Sans")
DEFAULT_BY = "sober"
SIZE__BASE = 13
SMALL_SIZE_ = 11
WEIGHT_TITLE = 600

_current: dict | None = None


def themes() -> list[str]:
    return sorted(p.stem for p in THEMES.glob("*.json"))


def mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def contrast(a: str, b: str) -> float:
    """The WCAG contrast between two colours (4.5 to read text; 3 for icons)."""
    def span(c):
        q = QColor(c)
        v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in (q.redF(), q.greenF(), q.blueF())]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    l1, l2 = sorted((span(a), span(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def mode_system() -> str:
    scheme = QGuiApplication.styleHints().colorScheme()
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def load(name: str = DEFAULT_BY, mode: str | None = None) -> dict:
    """The tokens of a theme in a mode, with the derived ones (hover, press)."""
    filepath = THEMES / f"{name}.json"
    if not filepath.exists():
        name, filepath = DEFAULT_BY, THEMES / f"{DEFAULT_BY}.json"   # a theme that no longer exists
    d = json.loads(filepath.read_text(encoding="utf-8"))
    mode = mode or mode_system()
    c = dict(d[mode])
    p = c.pop("tensela")
    c["hover"] = mix(c["surface"], c["text"], 0.07)
    c["pressed"] = mix(c["surface"], c["text"], 0.13)
    c["accent_hover"] = mix(c["accent"], c["text"], 0.15)
    # What rises above a field (the chosen segment): white in light, a little lighter in dark.
    c["raised"] = c["surface"] if mode == "light" else mix(c["surface"], c["text"], 0.10)
    return {"name": d["name"], "key": name, "mode": mode, "c": c, "p": p,
            "r_control": d["radius"]["control"], "r_panel": d["radius"]["panel"],
            "r_card": d["radius"].get("card", d["radius"]["panel"]), "height": d["control_height"]}


def check_contrasts(tk: dict) -> list[tuple[str, float, float]]:
    """The pairs that must be readable: (what, contrast, minimum)."""
    c, p = tk["c"], tk["p"]
    pairs = [("text", c["text"], c["surface"], 4.5), ("text on the background", c["text"], c["background"], 4.5),
             ("secondary text", c["text_2"], c["surface"], 4.5), ("on the accent", c["on_accent"], c["accent"], 4.5),
             ("accent", c["accent"], c["surface"], 3.0), ("text on the card", c["text"], p["card"], 4.5),
             ("value on the card", c["text_2"], p["card"], 4.5), ("wire", p["wire"], p["canvas"], 3.0)]
    if p.get("header") == "filled":          # the title goes on the colour
        pairs += [(f"header {k}", p["header_text"], v, 4.5) for k, v in p["categories"].items()]
    else:                                     # a band of colour: it must stand out from the card
        pairs += [(f"band {k}", v, p["card"], 3.0) for k, v in p["categories"].items()]
        pairs.append(("title on the card", p["header_text"], p["card"], 4.5))
    return [(what, contrast(a, b), minimum) for what, a, b, minimum in pairs]


# --- Qt ---------------------------------------------------------------------------

def _svg(name: str, color: str, folder: Path) -> str:
    """An arrow or a check mark, in the theme's colour (Qt paints the combos and the check boxes with images)."""
    shapes = {
        "down": '<path d="M3 5.5 L8 10.5 L13 5.5" fill="none" stroke="{c}" stroke-width="1.8" '
                 'stroke-linecap="round" stroke-linejoin="round"/>',
        "check": '<path d="M3.5 8.5 L6.8 11.5 L12.5 4.5" fill="none" stroke="{c}" stroke-width="2" '
                 'stroke-linecap="round" stroke-linejoin="round"/>',
        "close": '<path d="M3.5 3.5 L12.5 12.5 M12.5 3.5 L3.5 12.5" fill="none" stroke="{c}" stroke-width="1.5" '
                  'stroke-linecap="round"/>',
    }
    import zlib
    tread = zlib.crc32((shapes[name] + ("18" if name == "close" else "")).encode()) & 0xFFFF          # if the shape changes, another file
    filepath = folder / f"{name}-{color.lstrip('#')}-{tread:04x}.svg"
    if not filepath.exists():
        side = 18 if name == "close" else 16          # Qt paints it at this size, not at that of its box
        filepath.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" viewBox="0 0 16 16">'
                        f'{shapes[name].format(c=color)}</svg>', encoding="utf-8")
    return filepath.as_posix()


QSS = Template(r"""
/* El escritorio (Ubuntu, GNOME) impone su fuente a menús, botones y avisos: aquí manda la del tema. */
QWidget { font-size: ${base}px; font-family: "$family"; }
QMainWindow, QDialog, QWidget#panel_window { background: $background; }
QToolTip { background: $surface; color: $text; border: 1px solid $border; padding: 4px 6px; }
QLabel { color: $text; background: transparent; }

QMenuBar { background: $background; color: $text_2; }
QMenuBar::item { background: transparent; padding: 5px 9px; border-radius: ${r_control}px; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: $hover; color: $text; }
QMenu { background: $surface; color: $text; border: 1px solid $border; border-radius: ${r_control}px; padding: 6px; }
QMenu::item { padding: 6px 28px 6px 12px; border-radius: ${r_small}px; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::item:disabled { color: $disabled; }
QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }

/* Tarjetas (bento): el título dentro, arriba a la izquierda; aire entre ellas. */
QGroupBox { background: $surface; border: 1px solid $border; border-radius: ${r_panel}px;
    margin-top: 0; padding: 36px 10px 10px 10px; color: $text; }
QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; left: 16px; top: 12px;
    color: $text; font-weight: $title_weight; font-size: ${title}px; }
QGroupBox#value_group { background: transparent; border: none; border-top: 1px solid $border;
    border-radius: 0; padding: 24px 0 2px 0; }
QGroupBox#value_group::title { left: 2px; top: 6px; color: $text_2; font-size: ${small_size}px; }
QGroupBox#value_alone { background: transparent; border: none; border-top: 1px solid $border;
    border-radius: 0; padding: 6px 0 2px 0; }
QSplitter::handle { background: $background; }
QSplitter::handle:hover { background: $accent_soft; }
QLabel#warning { background: $warning_background; color: $danger; padding: 8px 10px; border-radius: ${r_panel}px; }
QFrame#computing_strip { background: $raised; border: 1px solid $accent; border-radius: ${r_panel}px; }

QPushButton { background: transparent; color: $text; border: 1px solid $border;
    border-radius: ${r_control}px; padding: 0 12px; min-height: ${height}px; }
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $pressed; }
QPushButton:default { background: $accent; color: $on_accent; border-color: $accent; }
QPushButton:default:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton:disabled, QPushButton:default:disabled { background: transparent; color: $disabled; border-color: $border; }
QToolButton { background: transparent; color: $text; border: 1px solid transparent; border-radius: ${r_control}px; padding: 3px 6px; }
QToolButton:hover { background: $hover; }
QToolButton:checked { background: $accent_soft; border-color: $accent; }

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { background: $field; color: $text; border: 1px solid $field_border;
    border-radius: ${r_control}px; padding: 0 10px; min-height: ${height}px;
    selection-background-color: $accent; selection-color: $on_accent; }
QComboBox QLineEdit { border: none; background: transparent; }
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover { border-color: $field_border_hover; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid $accent; }
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled { color: $disabled;
    border-color: $border; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url($arrow); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $surface; color: $text; border: 1px solid $border;
    selection-background-color: $accent_soft; selection-color: $text; outline: 0; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QCheckBox { color: $text; spacing: 7px; background: transparent; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid $border; border-radius: 3px; background: $field; }
QCheckBox::indicator:hover { border-color: $text_2; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($check); }

QSlider::groove:horizontal { height: 6px; background: $field; border-radius: 3px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 3px; }
QSlider::handle:horizontal { background: $text; border: none; width: 14px; height: 14px;
    margin: -4px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: $accent; }

QTreeWidget, QTreeView, QListView { background: $surface; color: $text; border: none;
    alternate-background-color: $field; selection-background-color: $accent_soft; selection-color: $text; outline: 0; }
QHeaderView::section { background: $surface; color: $text_2; border: none; border-bottom: 1px solid $border;
    padding: 4px 6px; font-weight: $title_weight; font-size: ${small_size}px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* Componentes (ui/componentes.py) */
QFrame#segmented { background: $field; border-radius: ${r_control}px; }
QToolButton#segment { background: transparent; border: none; border-radius: ${r_small}px;
    padding: 4px 10px; color: $text_2; min-height: 20px; }
QToolButton#segment:hover { color: $text; }
QToolButton#segment:checked { background: $raised; color: $text; font-weight: $title_weight; }
QToolButton#card { background: $field; border: 2px solid transparent; border-radius: ${r_control}px;
    padding: 8px 4px 6px 4px; color: $text_2; }
QToolButton#card:hover { border-color: $border; color: $text; }
QToolButton#card:checked { border-color: $accent; color: $text; font-weight: $title_weight; }
QToolButton#menu_button { background: $field; border: none; border-radius: ${r_small}px; padding: 4px 10px;
    color: $text; }
QToolButton#menu_button:hover { background: $hover; }
QToolButton#flat_button { background: transparent; border: none; color: $text_2; padding: 2px 0px; }
QToolButton#flat_button:hover, QToolButton#flat_button:checked { color: $text; }
QFrame#drawing_bar { background: $raised; border-bottom: 2px solid $accent; }
QToolButton#menu_button::menu-indicator { image: none; width: 0; }
QToolButton#icon_button { background: transparent; border: none; border-radius: ${r_small}px; padding: 5px; }
QToolButton#icon_button:hover { background: $hover; }
QToolButton#icon_button:checked { background: $accent; }
QToolButton#icon_button:checked:hover { background: $accent_hover; }
QToolButton#icon_button[active="true"] { background: $accent; }
QToolButton#icon_button[active="true"]:hover { background: $accent_hover; }
QLabel[role="secondary"] { color: $text_2; }
QFrame#action_tile { background: $field; border: 1px solid $border; border-radius: ${r_card}px; }
QFrame#action_tile:hover, QFrame#action_tile:focus { border-color: $accent; }
QFrame#action_tile[active="true"] { background: $accent_soft; border-color: $accent; }
QFrame#action_tile:disabled { border-color: $border; }
QLabel#action_badge { background: $accent_soft; border-radius: ${r_control}px; }
QLabel#action_badge[active="true"] { background: $accent; }
QToolButton#tile_button { background: $surface; color: $text; border: 1px solid $border;
    border-radius: ${r_control}px; padding: 4px 8px; }
QToolButton#tile_button:hover { border-color: $accent; background: $hover; }
QToolButton#tile_button:pressed { background: $pressed; }
QLabel[role="tile_title"] { color: $text; font-weight: $title_weight; }
QLabel[role="tile_title"]:disabled { color: $disabled; }
QFrame#panel { background: $surface; border: 1px solid $border; border-radius: ${r_panel}px; }
/* Un panel acoplable: su barra (la cabecera) y su cuerpo se ven como una sola tarjeta. */
QWidget#panel_bar { background: $surface; border: 1px solid $border; border-bottom: none;
    border-top-left-radius: ${r_panel}px; border-top-right-radius: ${r_panel}px; }
QFrame#panel_body { background: $surface; border: 1px solid $border; border-top: none;
    border-bottom-left-radius: ${r_panel}px; border-bottom-right-radius: ${r_panel}px; }
QWidget#panel_bar[floating="true"] { border-radius: 0; border: none; }
QFrame#panel_body[floating="true"] { border-radius: 0; border: none; }
QDockWidget { color: $text; }
QMainWindow::separator { background: transparent; width: 8px; height: 8px; }
QMainWindow::separator:hover { background: $accent_soft; }
QTreeWidget#data_table { background: transparent; alternate-background-color: $alternate_row; border: none; }
QTreeWidget#data_table::item { padding: 3px 4px; border: none; }
QTreeWidget#data_table::item:selected { background: $accent_soft; color: $text; }
QTreeWidget#data_table QHeaderView::section { background: transparent; color: $text_2; border: none;
    border-bottom: 1px solid $border; padding: 4px 6px; font-size: ${small_size}px; font-weight: $title_weight; }
QLineEdit#card_field { background: $field; border: 1px solid $accent; border-radius: 4px; padding: 0 4px;
    min-height: 0; font-size: ${small_size}px; }
QListWidget#card_list { background: $surface; color: $text; border: 1px solid $border; border-radius: 4px;
    outline: 0; font-size: ${small_size}px; padding: 2px; }
QListWidget#card_list::item { padding: 1px 6px; border-radius: 3px; }
QListWidget#card_list::item:hover { background: $hover; }
QListWidget#card_list::item:selected { background: $accent_soft; color: $text; }
/* Las pestañas de los paneles agrupados (Valores | Croquis): como las de los proyectos, pero chicas. */
QMainWindow > QTabBar { background: transparent; }
QMainWindow > QTabBar::tab { background: transparent; color: $text_2; border: none; padding: 4px 12px;
    margin: 2px 2px 0 0; border-radius: ${r_control}px; }
QMainWindow > QTabBar::tab:hover { color: $text; background: $hover; }
QMainWindow > QTabBar::tab:selected { color: $text; background: $surface; font-weight: $title_weight; }
QTabBar#project_tabs { background: transparent; }
QTabBar#project_tabs::tab { background: transparent; color: $text_2; border: none; padding: 5px 8px 5px 14px;
    margin-right: 4px; border-radius: ${r_control}px; }
QTabBar#project_tabs::tab:hover { color: $text; background: $hover; }
QTabBar#project_tabs::tab:selected { color: $text; background: $surface; font-weight: $title_weight; }
QTabBar#project_tabs::close-button { image: url($close); subcontrol-position: right; margin: 0 6px 0 2px;
    padding: 1px; border-radius: 5px; }
QTabBar#project_tabs::close-button:hover { image: url($close_hover); background: $hover; }
/* Preferencias: secciones a la izquierda, títulos con jerarquía, líneas entre grupos. */
QLabel[role="label"] { color: $text; font-weight: 500; }
QLabel[role="page_title"] { font-size: ${page_title}px; font-weight: $title_weight; color: $text; }
QFrame#divisor { background: $border; border: none; }
QListWidget#sections { background: $background; border: none; border-right: 1px solid $border; padding: 12px 8px; outline: 0; }
QListWidget#sections::item { padding: 8px 12px; border-radius: ${r_control}px; color: $text_2; margin-bottom: 2px; }
QListWidget#sections::item:hover { background: $hover; color: $text; }
QListWidget#sections::item:selected { background: $accent_soft; color: $text; font-weight: $title_weight; }
QTableWidget#shortcuts_table { background: transparent; border: 1px solid $border; border-radius: ${r_control}px;
    gridline-color: $border; }
QTableWidget#shortcuts_table QHeaderView::section { background: transparent; color: $text_2; border: none;
    border-bottom: 1px solid $border; padding: 4px 8px; font-size: ${small_size}px; font-weight: $title_weight; }
QKeySequenceEdit QLineEdit { background: $field; border: none; min-height: 22px; }
QLabel#sketch_preview { background: $field; color: $text_2; border-radius: ${r_panel}px; }
QLineEdit#editable_title { background: transparent; border-color: transparent; font-size: ${big_title}px;
    font-weight: $title_weight; padding: 0 4px; }
QLineEdit#editable_title:hover { background: $field; border-color: $field_border; }
QLineEdit#editable_title:focus { background: $field; border-color: $accent; }
QLabel[role="small"] { color: $text_2; font-size: ${small_size}px; }
QLabel[role="title"] { font-weight: $title_weight; font-size: ${title}px; }

QStatusBar { background: $background; color: $text_2; border-top: 1px solid $border; }
QStatusBar::item { border: none; }

/* Barras de desplazamiento: anchas y con el elevador bien visible (comentario general 15). */
QScrollBar:vertical, QScrollBar:horizontal { background: transparent; border: none; margin: 0; }
QScrollBar:vertical { width: 12px; } QScrollBar:horizontal { height: 12px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: $scroll_handle; border-radius: 4px;
    margin: 2px; min-height: 28px; min-width: 28px; }
QScrollBar::handle:hover { background: $text_2; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
""")


def _own_folder() -> Path:
    """Where the theme's little images go: in the user's own cache, not in the shared temporary folder (there,
    another user of the computer could leave a link with the same name and make Tensela write over a file of
    yours)."""
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    folder = Path(cache) / "tensela" / "theme"
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:                                    # (a read-only home: a private folder of its own, each time)
        folder = Path(tempfile.mkdtemp(prefix="tensela-theme-"))
    return folder


def qss(tk: dict) -> str:
    c = tk["c"]
    folder = _own_folder()
    return QSS.substitute(dict(c, base=SIZE__BASE, family=source().family(), small_size=SMALL_SIZE_, title_weight=WEIGHT_TITLE,
                               r_control=tk["r_control"], r_panel=tk["r_panel"], r_card=tk["r_card"],
                               height=tk["height"] - 2,
                               r_small=max(2, tk["r_control"] - 3), title=SIZE__BASE + 1,
                               big_title=SIZE__BASE + 4, page_title=SIZE__BASE + 7,
                               arrow=_svg("down", c["text_2"], folder),
                               check=_svg("check", c["on_accent"], folder),
                               close=_svg("close", c["text_2"], folder),
                               close_hover=_svg("close", c["text"], folder),
                               scroll_handle=mix(c["border"], c["text_2"], 0.5),
                               # The edge of a field: seen at rest (where to write), firmer under the pointer.
                               field_border=mix(c["border"], c["text_2"], 0.3),
                               field_border_hover=mix(c["border"], c["text_2"], 0.6),
                               alternate_row=mix(c["surface"], c["text"], 0.035),
                               warning_background=mix(c["surface"], c["danger"], 0.14)))


def palette(c: dict) -> QPalette:
    p = QPalette()
    for role, k in [(QPalette.Window, "background"), (QPalette.WindowText, "text"), (QPalette.Base, "field"),
                   (QPalette.AlternateBase, "surface"), (QPalette.Text, "text"), (QPalette.Button, "surface"),
                   (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"), (QPalette.HighlightedText, "on_accent"),
                   (QPalette.ToolTipBase, "surface"), (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "disabled"),
                   (QPalette.Mid, "border"), (QPalette.Midlight, "border"), (QPalette.Dark, "border"), (QPalette.Light, "surface"),
                   (QPalette.Link, "accent"), (QPalette.BrightText, "danger")]:
        p.setColor(role, QColor(c[k]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["disabled"]))
    return p


def source() -> QFont:
    for file in sorted(FONTS.glob("*/*.ttf")):
        QFontDatabase.addApplicationFont(str(file))
    available = set(QFontDatabase.families())
    family = next((f for f in FAMILIES if f in available), None)
    f = QFont(family) if family else QFont()
    f.setPixelSize(SIZE__BASE)
    return f


#: The backgrounds chosen apart from the theme (Preferences or the right click): that of the canvas and that of the 3D view.
#: The cards are still the theme's; the wires and the grid, the background's, so they can be read.
#: The mid one of the view is darker than half way: the usual colours of the geometry (greys, red, green) sit half
#: way, and on a background of their own tone they would vanish.
TONES = {
    "light": {"viewer": "#f3f4f7", "canvas": "#f3f4f7", "grid": "#dcdfe6", "wire": "#7a8091"},
    "mid": {"viewer": "#464a52", "canvas": "#555963", "grid": "#666a74", "wire": "#c6cad3"},
    "dark": {"viewer": "#16181d", "canvas": "#0f1014", "grid": "#1f2128", "wire": "#6f7588"},
}
NAMES_TONE = {"theme": 'Like the theme', "light": 'Light', "mid": 'Mid', "dark": 'Dark'}
TONE = {"canvas": "theme", "view": "theme"}


def put_tones(canvas: str | None = None, view: str | None = None) -> None:
    """The background of the canvas and that of the view: "theme" (that of the light or dark mode), "light", "mid" or "dark"."""
    if canvas is not None:
        TONE["canvas"] = canvas if canvas in TONES else "theme"
    if view is not None:
        TONE["view"] = view if view in TONES else "theme"
    if _current is not None:
        _al_editor(_current)
    elif TONE["canvas"] in TONES:
        from . import editor
        t = TONES[TONE["canvas"]]
        editor.DEPTH, editor.GRID, editor.WIRE = QColor(t["canvas"]), QColor(t["grid"]), QColor(t["wire"])


def color_view(tk: dict | None = None) -> str:
    """The background of the 3D view: the chosen one, or the theme's."""
    tk = tk or _current
    tone = TONES.get(TONE["view"])
    return tone["viewer"] if tone else (tk["c"]["viewer"] if tk else "#16181d")


def _al_editor(tk: dict) -> None:
    """The node canvas is painted by hand: its colours, from the tokens."""
    from . import editor
    c, p = tk["c"], dict(tk["p"])
    p.update({k: v for k, v in TONES.get(TONE["canvas"], {}).items() if k != "viewer"})
    editor.DEPTH = QColor(p["canvas"])
    editor.GRID = QColor(p["grid"])
    editor.BODY = QColor(p["card"])
    editor.EDGE = QColor(p["card_border"])
    editor.TEXT = QColor(c["text"])
    editor.SMOOTH_TEXT = QColor(c["text_2"])
    editor.TEXT_HEADER = QColor(p["header_text"])
    editor.WIRE = QColor(p["wire"])
    editor.RED = QColor(c["danger"])
    editor.SELECTION = QColor(c["accent"])
    editor.COLOURS_CATEGORY.update({k: QColor(v) for k, v in p["categories"].items()})
    editor.HEADER = p.get("header", "filled")
    editor.RADIUS = tk["r_card"]


def _without_underlined(app) -> None:
    """Without the underlined letter of the menus and buttons (the Alt one): it clutters reading.

    Alt + letter still works; it is only not drawn. (Qt, on Linux, always showed it.)
    """
    from PySide6.QtWidgets import QProxyStyle, QStyle

    class WithoutUnderlined(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, return_=None):
            if hint == QStyle.StyleHint.SH_UnderlineShortcut:
                return 0
            return super().styleHint(hint, option, widget, return_)

    if not app.property("no_underlines"):
        app.setProperty("no_underlines", True)
        app.setStyle(WithoutUnderlined(app.style().name()))


#: Where the text of a number box starts, as in a text field (the stylesheet's padding does not reach inside it).
NUMBER_MARGIN = 11


class _NumberMargins(QObject):
    """Gives each number box (spin box) the left margin of the text fields, when it is first shown."""

    def eventFilter(self, object_, event) -> bool:
        if event.type() == QEvent.Type.Polish and object_.inherits("QAbstractSpinBox"):
            edit = object_.findChild(QObject, "qt_spinbox_lineedit")
            if edit is not None and edit.textMargins().left() < NUMBER_MARGIN:
                edit.setTextMargins(NUMBER_MARGIN, 0, 0, 0)
        return False


def _number_margins(app) -> None:
    if not app.property("number_margins"):
        app.setProperty("number_margins", True)
        app._number_margins = _NumberMargins(app)
        app.installEventFilter(app._number_margins)


def apply(app, name: str = DEFAULT_BY, mode: str | None = None) -> dict:
    """Puts the theme on the whole application and returns it (for the 3D view and the editor already open)."""
    global _current
    _without_underlined(app)
    _number_margins(app)
    tk = load(name, mode)
    f = source()
    app.setFont(f)
    for class_ in ("QMenu", "QMenuBar", "QToolTip", "QComboBox", "QListView"):   # Qt gives them the system's
        app.setFont(f, class_)
    app.setPalette(palette(tk["c"]))
    app.setStyleSheet(qss(tk))
    _al_editor(tk)
    _current = tk
    return tk


def current() -> dict | None:
    return _current


def color(key: str, yes_no_there_is: str) -> str:
    """A colour of the theme set (of the interface or of Tensela's own)."""
    if _current is None:
        return yes_no_there_is
    return _current["c"].get(key) or _current["p"].get(key) or yes_no_there_is
