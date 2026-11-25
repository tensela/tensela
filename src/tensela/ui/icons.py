"""Tensela's icons (Delivery 5): our own, stroked, on a 24 px grid.

A 1.75 px stroke with round caps and joins, without fill except for some dot. Each icon is the inside of a 24 × 24
SVG; it is tinted with the colour asked for (the theme's), so it works in light and in dark.

    icon("curves", "#ecedf2", 16)        # QIcon
    pixmap("shapes", "#8a7dff", 24, 2.0)  # QPixmap (with the screen's density)

There are no logos of other programs: «Blender» and «IngeTrazo» carry a drawing of what they do (a lit scene, a set
square), not their brand.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONS = {
    # --- Node categories ---------------------------------------------------------
    # Valores: dos deslizadores.
    # A gear: the settings of something.
    "gear": '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="6.5"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3'
            'M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "code": '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 5l-3 14"/>',
    "values": '<path d="M4 8h9M17 8h3M4 16h3M11 16h9"/><circle cx="15" cy="8" r="2"/><circle cx="9" cy="16" r="2"/>',
    # Shapes: a square and a circle that overlap.
    "shapes": '<rect x="3.5" y="3.5" width="11" height="11" rx="2"/><circle cx="15" cy="15" r="5.5"/>',
    # Curves: a smooth curve between two points.
    "curves": '<path d="M5 18c4 0 4-12 8-12s3 6 6 6"/><circle cx="4" cy="18" r="1.6" fill="currentColor" stroke="none"/>'
              '<circle cx="20" cy="12" r="1.6" fill="currentColor" stroke="none"/>',
    # Surfaces: a wavy skin with its rulings.
    "meshes": '<path d="M4 18.5 9 5l6 2.5 5 11zM9 5l-5 13.5 11-11M15 7.5l5 11-11-13.5M15 7.5 4 18.5"/>',
    "surfaces": '<path d="M3 7c3-2.5 6 2.5 9 0s6-2.5 9 0M3 12.5c3-2.5 6 2.5 9 0s6-2.5 9 0M3 18c3-2.5 6 2.5 9 0s6-2.5 9 0"/>'
                   '<path d="M3 7v11M21 7v11M9 7.3v11M15 6.7v11" stroke-width="1.4"/>',
    # Divide: a panel split into a grid.
    "divide": '<rect x="3.5" y="3.5" width="17" height="17" rx="2.5"/><path d="M12 3.5v17M3.5 12h17"/>',
    # Measure: a ruler with its marks.
    "measure": '<rect x="2.5" y="8" width="19" height="8" rx="1.5"/><path d="M6.5 8v3M10.5 8v4M14.5 8v3M18.5 8v4"/>',
    # Fabrication: a printer nozzle over the layers it lays down.
    "fabrication": '<path d="M9 3.5h6l-1.5 5h-3zM12 8.5v3M4 15h16M4 18h16M4 21h16"/>',
    # Environment: the sun, a disc with its rays.
    "environment": '<circle cx="12" cy="12" r="3.6"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4 '
                   'M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7"/>',
    # Simulation: a cable hanging between two supports, with one of its particles.
    "simulation": '<path d="M2.5 5h5M16.5 5h5M5 5c2 9 12 9 14 0"/><circle cx="12" cy="11.8" r="1.7" fill="currentColor" '
                  'stroke="none"/>',
    # Transform: move in the four directions.
    "transform": '<path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',

    # Play a value from its start to its end, and stop it.
    "play": '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/>',
    "pause": '<rect x="7" y="6" width="3.6" height="12" rx="1.2" fill="currentColor"/>'
             '<rect x="13.4" y="6" width="3.6" height="12" rx="1.2" fill="currentColor"/>',
    # Find the best: a target.
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.8" '
              'fill="currentColor"/>',
    # A support: a pin on its base, and the arrow of moving it.
    "supports": '<path d="M12 3v7M9 6l3-3 3 3"/><path d="M12 13l-5 7h10z"/><path d="M5 21h14"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5" fill="currentColor"/>',

    # --- Export and open in ----------------------------------------------------------
    "export": '<path d="M12 15V3.5M8 7.5l4-4 4 4M5 12v6.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V12"/>',
    "open_in": '<path d="M14 4h6v6M20 4l-8.5 8.5M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
    "image": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="M3.5 17l5-4.5 3.5 3 3-2.5 5.5 4.5"/>',
    # Croquis, with its own icon (the one of the Croquis extension): an open notebook with a cube drawn by hand, its
    # lines running past the corners.
    "croquis": '<path d="M3 7.5V18.5Q7.5 17.5 12 19.5Q16.5 17.5 21 18.5V7.5" stroke-width="1.5"/>'
               '<path d="M12 15.5v4" stroke-width="1.3"/>'
               '<path d="M6.2 7.4L13 3.5M11 3.5l6.8 3.9M6.2 6.2L13 10.2M11 10.2l6.8-4M7.2 5.8v8M16.8 5.8v8M12 8.6v7.6'
               'M6.2 12.2L13 16.2M11 16.2l6.8-4" stroke-width="1.5"/>',
    "sketch": '<path d="M4.5 19.5l1-4.2L16 4.8a2 2 0 0 1 2.8 0l.4.4a2 2 0 0 1 0 2.8L8.7 18.5z"/><path d="M14 6.8l3.2 3.2M3 21.5c3-1 5 1 8-0.5"/>',
    # DXF: a drawing with its dimension.
    "dxf": '<rect x="4" y="3.5" width="16" height="12" rx="1.5"/><path d="M8 3.5v12M4 9h4M4 20h16M4 18.5v3M20 18.5v3"/>',
    # OBJ: a cube in isometric.
    "obj": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    # Blender: a scene (a volume) with its light (not its logo).
    "blender": '<path d="M9 9.5l5.5 3v6L9 21.5l-5.5-3v-6zM9 15.5l5.5-3M9 15.5v6M9 15.5l-5.5-3"/>'
               '<circle cx="18" cy="6" r="2.2"/><path d="M18 1.5v1M18 9.5v1M13.5 6h1M21.5 6h1"/>',
    # IngeTrazo: a set square (not its logo).
    "ingetrazo": '<path d="M4 20V4l16 16z"/><path d="M8 16v-4l4 4zM4 8h2M4 12h2"/>',

    # --- Views of a 2D drawing: the plan of the building and from where it is seen (north, up) ---
    "from_above": '<rect x="6" y="6" width="12" height="12" rx="1.5"/><circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/>',
    "from_south": '<rect x="6" y="3.5" width="12" height="10" rx="1.5"/><path d="M12 21.5v-5M9.5 19l2.5-2.5 2.5 2.5"/>',
    "from_north": '<rect x="6" y="10.5" width="12" height="10" rx="1.5"/><path d="M12 2.5v5M9.5 5l2.5 2.5 2.5-2.5"/>',
    "from_east": '<rect x="3.5" y="6" width="10" height="12" rx="1.5"/><path d="M21.5 12h-5M19 9.5l-2.5 2.5 2.5 2.5"/>',
    "from_below": '<rect x="6" y="6" width="12" height="12" rx="1.5" stroke-dasharray="2 2"/><circle cx="12" cy="12" r="2.2"/>',
    "isometric": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "from_west": '<rect x="10.5" y="6" width="10" height="12" rx="1.5"/><path d="M2.5 12h5M5 9.5l2.5 2.5-2.5 2.5"/>',

    # --- Panels and areas -------------------------------------------------------------
    "view3d": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" stroke-dasharray="2 2.2"/>',
    "nodes": '<rect x="2.5" y="4" width="8" height="6" rx="1.5"/><rect x="13.5" y="14" width="8" height="6" rx="1.5"/>'
             '<path d="M10.5 7c4 0 3 10 3 10"/>',
    "node": '<rect x="4" y="4.5" width="16" height="15" rx="3"/><path d="M4 9.5h16"/>'
            '<circle cx="4" cy="14.5" r="1.6" fill="currentColor" stroke="none"/><circle cx="20" cy="14.5" r="1.6" fill="currentColor" stroke="none"/>',
    "data": '<path d="M8 6.5h12M8 12h12M8 17.5h12"/><circle cx="4.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/>'
             '<circle cx="4.5" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="4.5" cy="17.5" r="1.2" fill="currentColor" stroke="none"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.6" r="1.1" fill="currentColor" stroke="none"/>',
    "eye_closed": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'
                   '<path d="M4 4l16 16"/>',

    # --- Acciones --------------------------------------------------------------------
    "nuevo": '<path d="M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8.5z"/><path d="M13.5 3.5v5h5M12 11.5v6M9 14.5h6"/>',
    "open": '<path d="M3.5 18.5V6A1.5 1.5 0 0 1 5 4.5h4.5l2 2.5H19a1.5 1.5 0 0 1 1.5 1.5V10"/><path d="M3.5 18.5l2.6-7A1.5 1.5 0 0 1 7.5 10.5h13l-2.7 8z"/>',
    "save": '<path d="M12 3.5v11M8 10.5l4 4 4-4"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5l5 5"/>',
    "frame_all": '<path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15"/>'
                 '<rect x="9" y="9" width="6" height="6" rx="1"/>',
    "arrange": '<rect x="3" y="4" width="6" height="5" rx="1.2"/><rect x="3" y="15" width="6" height="5" rx="1.2"/>'
               '<rect x="15" y="9.5" width="6" height="5" rx="1.2"/><path d="M9 6.5h2.5a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H9M13 12h2"/>',
    "grid": '<path d="M4 4h16v16H4zM9.3 4v16M14.7 4v16M4 9.3h16M4 14.7h16" stroke-width="1.4"/>',
    "theme": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none"/>',
    # Move a panel to a separate window (an arrow that goes out) and bring it back (an arrow that comes in).
    "undock": '<path d="M10 4.5H6A1.5 1.5 0 0 0 4.5 6v12A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-4"/>'
             '<path d="M13.5 4.5h6v6M19.5 4.5l-8 8"/>',
    "dock": '<path d="M10 4.5H6A1.5 1.5 0 0 0 4.5 6v12A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-4"/>'
               '<path d="M18.5 5.5l-7 7M11.5 7v5.5H17"/>',
    "guides": '<rect x="3" y="4" width="8" height="6" rx="1.5"/><rect x="13" y="14" width="8" height="6" rx="1.5"/>'
             '<path d="M3 13v8M11 13v1M11 17v1M11 21v-1" stroke-dasharray="2 2"/>',
    "axes": '<path d="M6 18V5M6 18h13M6 18l-3.5 3.5M3.5 7.5L6 5l2.5 2.5M16.5 15.5L19 18l-2.5 2.5"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    # A group: a node in brackets (several nodes inside one).
    "group": '<rect x="7.5" y="8" width="9" height="8" rx="1.5"/><path d="M7.5 11h9M4.5 4.5v15M4.5 4.5h2M4.5 19.5h2'
             'M19.5 4.5v15M19.5 4.5h-2M19.5 19.5h-2"/>',
    "mas": '<circle cx="5.5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" '
           'fill="currentColor" stroke="none"/><circle cx="18.5" cy="12" r="1.4" fill="currentColor" stroke="none"/>',
    # A new tab (beside the tabs of the projects).
    "plus": '<path d="M12 5.5v13M5.5 12h13"/>',
    # An extension: a piece of a puzzle (something added that fits).
    "extension": '<path d="M5 8.5h3.2a2.3 2.3 0 1 1 4.6 0H16v3.2a2.3 2.3 0 1 1 0 4.6V19.5H12.8'
                 'a2.3 2.3 0 1 0-4.6 0H5z"/>',
    # Yes, it is so: a tick.
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5" stroke-width="2.2"/>',
    # Take care: a triangle with an exclamation mark.
    "warning": '<path d="M12 3.8 21.2 19.5H2.8z"/><path d="M12 10v4.6"/>'
               '<circle cx="12" cy="17" r="1.1" fill="currentColor" stroke="none"/>',
    # The internet: a globe.
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c3 3 3 14 0 17M12 3.5c-3 3-3 14 0 17"/>',
    # Files: a folder.
    "folder": '<path d="M3.5 6.5a1.5 1.5 0 0 1 1.5-1.5h4.2l2 2.3H19a1.5 1.5 0 0 1 1.5 1.5v9.2a1.5 1.5 0 0 1-1.5 1.5H5'
              'a1.5 1.5 0 0 1-1.5-1.5z"/>',
    # Another program: a terminal window.
    "program": '<rect x="3" y="4.5" width="18" height="15" rx="2"/><path d="M7 10l3 2.5L7 15M12.5 15h4.5"/>',
    "panels": '<rect x="3.5" y="4" width="17" height="16" rx="2.5"/><path d="M14 4v16M14 12h6.5"/>',
    # A list that drops down (on the cards, the values chosen from a list).
    "chevron_down": '<path d="M6 9.5l6 6 6-6" stroke-width="2.2"/>',
    # The two ways of seeing the Library: a list (a swatch and two lines) and tiles.
    "list_view": '<rect x="3.5" y="4.5" width="5" height="5" rx="1.2"/><rect x="3.5" y="14.5" width="5" height="5" '
                 'rx="1.2"/><path d="M11.5 6h9M11.5 8.5h6M11.5 16h9M11.5 18.5h6"/>',
    "tiles": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" '
             'rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" '
             'height="7" rx="1.5"/>',
    # Two arrows going round: load again (an extension being written).
    "reload": '<path d="M19.5 12a7.5 7.5 0 0 1-13 5.1M4.5 12a7.5 7.5 0 0 1 13-5.1M17.5 3.5v3.4h-3.4M6.5 20.5v-3.4h3.4"/>',
    # A plug: talks with other programs of the computer.
    "plug": '<path d="M9 3.5v4M15 3.5v4M6.5 7.5h11v3a5.5 5.5 0 0 1-11 0zM12 16v4.5"/>',
    # Compact rows: three lines, each with its dot (one line per thing).
    "rows": '<circle cx="5" cy="6.5" r="1" fill="currentColor"/><circle cx="5" cy="12" r="1" fill="currentColor"/>'
            '<circle cx="5" cy="17.5" r="1" fill="currentColor"/><path d="M9 6.5h11M9 12h11M9 17.5h11"/>',
    "quit": '<path d="M14 4h4.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H14M9.5 8l-4 4 4 4M5.5 12H15"/>',
}

#: The icon of each node category (nodes.py).
FROM_CATEGORY = {'Values': "values", 'Shapes': "shapes", 'Curves': "curves", 'Surfaces': "surfaces",
                'Meshes': "meshes",
                'Divide': "divide", 'Measure': "measure", 'Transform': "transform", 'Fabrication': "fabrication",
                'Simulation': "simulation", 'Environment': "environment",
                'Groups': "group"}


def svg(name: str, color: str) -> str:
    from ..extensions import ICONS as OF_EXTENSIONS         # those of the extensions on ("<id>.<name>")
    inside = ICONS.get(name) or OF_EXTENSIONS.get(name) or ICONS["extension"]
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" color="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
            f'{inside}</svg>')


def of_kind(kind: str, category: str) -> str | None:
    """The icon of a kind of node on its card: Code has its own; one of an extension, the one it brings; the rest,
    that of its category (an extension node in a category of its own: the extension icon)."""
    from ..extensions import KIND_ICONS
    from ..nodes import CATALOG
    if kind == 'Code':
        return "code"
    if kind in KIND_ICONS:
        return KIND_ICONS[kind]
    if category in FROM_CATEGORY:
        return FROM_CATEGORY[category]
    t = CATALOG.get(kind)
    return "extension" if t is not None and t.extension else None


@lru_cache(maxsize=256)
def _drawing(name: str, color: str) -> QSvgRenderer:
    return QSvgRenderer(QByteArray(svg(name, color).encode()))


def paint(painter: QPainter, name: str, color: str, rect: QRectF) -> None:
    """Draws the icon as a vector (sharp at any zoom: the node canvas)."""
    _drawing(name, color).render(painter, rect)


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, px: int = 16, density: float = 1.0) -> QPixmap:
    side = max(1, round(px * density))
    image = QPixmap(side, side)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, color).encode())).render(painter, QRectF(0, 0, side, side))
    painter.end()
    image.setDevicePixelRatio(density)
    return image


def icon(name: str, color: str, px: int = 16, disabled: str | None = None) -> QIcon:
    """A tinted QIcon (at 1× and 2×, for high-density screens)."""
    ic = QIcon()
    for d in (1.0, 2.0):
        ic.addPixmap(pixmap(name, color, px, d))
        if disabled:
            ic.addPixmap(pixmap(name, disabled, px, d), QIcon.Mode.Disabled)
    return ic
