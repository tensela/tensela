"""The export dialogs (Delivery 5, step 2): with components, not with lists.

Each decision in view and with its drawing: what is chosen is seen chosen. Text, only where it helps: a line at the
foot that says what is going to happen.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFontComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QKeySequenceEdit, QLabel, QListWidget, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from .widgets import Switch, Segmented, Cards
from ..language import tr


def _buttons(dialog: QDialog, accept: str = 'Save…') -> QDialogButtonBox:
    accept = tr(accept)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    ok.setText(accept)
    cancel.setText(tr('Cancel'))
    for b in (ok, cancel):
        b.setIcon(QIcon())            # without the red and green icons of the desktop
        b.setAutoDefault(False)
    ok.setDefault(True)               # the accent, on the main action (not on the button with the focus)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


def _label(text: str) -> QLabel:
    """The title of a row: in the text colour and a little heavier than what is next to it."""
    e = QLabel(text)
    e.setProperty("role", "label")
    return e


class _Form(QDialog):
    """A dialog of «label: control» rows, with a footnote and the buttons."""

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self._layer = QVBoxLayout(self)
        self._layer.setSpacing(14)
        self._layer.setContentsMargins(20, 18, 20, 16)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(12)
        self._grid.setColumnStretch(1, 1)
        self._layer.addLayout(self._grid)
        self._rows: dict[QWidget, tuple[QLabel | None, QWidget]] = {}
        self.note = QLabel()
        self.note.setProperty("role", "small")
        self.note.setWordWrap(True)

    def row(self, label: str, control: QWidget) -> QWidget:
        n = self._grid.rowCount()
        e = _label(label) if label else None
        if e:
            self._grid.addWidget(e, n, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            e.setContentsMargins(0, 5, 0, 0)
        self._grid.addWidget(control, n, 1)
        self._rows[control] = (e, control)
        return control

    def display_row(self, control: QWidget, yes: bool) -> None:
        e, c = self._rows[control]
        for w in (e, c):
            if w:
                w.setVisible(yes)

    def finish(self, accept: str = 'Save…') -> None:
        self._layer.addWidget(self.note)
        self._layer.addWidget(_buttons(self, accept))


class DialogImage(_Form):
    """Size, background and axes of the image saved from the 3D view."""

    def __init__(self, parent, size__view: tuple[int, int]):
        super().__init__(parent, tr('Export image'))
        self._width, self._height = size__view
        self.size_ = self.row(tr('Size'), Segmented([(k, f"×{k}", None) for k in (1, 2, 3, 4)], 2))
        self.pixels = _label("")
        self.row("", self.pixels)
        self.background = self.row(tr('Background'), Segmented(
            [("white", 'White', None), ("transparent", 'Transparent', None), ("view", 'As in the view', None)],
            help_texts={"view": 'The background of the 3D view (its colour or its gradient), as you see it'}))
        self.axes = self.row("", Switch(tr('Show the X, Y, Z axes')))
        self.note.setText(tr('What you see is saved, with the same framing: for another, turn the view first.'))
        self.size_.change.connect(lambda _: self._pixels())
        self._pixels()
        self.finish()

    def _pixels(self) -> None:
        k = self.size_.value()
        self.pixels.setText(f"{self._width * k} × {self._height * k} px")

    def choice(self) -> tuple[int, str | None, bool]:
        background = self.background.value()
        return self.size_.value(), None if background == "view" else background, self.axes.isChecked()


class DialogDxf(_Form):
    """How the DXF is exported: in 3D (the model) or in 2D (a plan or an elevation), and in what unit."""

    UNITS = {"metres": "m", "centimetres": "cm", "millimetres": "mm", "inches": "in", "feet": "ft"}
    #: The units as the preferences kept them before the move to English.
    OLD_UNITS = {"metros": "metres", "centímetros": "centimetres", "milímetros": "millimetres", "pulgadas": "inches",
                 "pies": "feet"}
    VIEWS = [("plan", 'Top', "from_above"), ("south elevation", 'South', "from_south"),
              ("north elevation", 'North', "from_north"), ("east elevation", 'East', "from_east"),
              ("west elevation", 'West', "from_west")]
    HELP_TEXTS_VIEW = {"plan": 'From above', "south elevation": 'South elevation: looking from the south (−Y)',
                    "north elevation": 'North elevation: looking from the north (+Y)',
                    "east elevation": 'East elevation: looking from the east (+X)',
                    "west elevation": 'West elevation: looking from the west (−X)'}

    def __init__(self, parent, unit: str = "millimetres", compatible: bool = False,
                 mode: int = 0, view: str = "plan", visible_only: bool = True):
        super().__init__(parent, tr('Export DXF'))
        from ..connectors.dxf import OLD_VIEWS
        unit, view = self.OLD_UNITS.get(unit, unit), OLD_VIEWS.get(view, view)
        self.mode = self.row(tr('Drawing'), Segmented(
            [(0, '3D, the model', "obj"), (1, '2D, plan or elevation', "dxf")], mode if mode in (0, 1) else 0))
        self.view = self.row(tr('View'), Cards(self.VIEWS, view, columns=5, side=28, help_texts=self.HELP_TEXTS_VIEW))
        self.unit = self.row(tr('Unit'), Segmented(
            [(k, v, None) for k, v in self.UNITS.items()], unit if unit in self.UNITS else "millimetres",
            help_texts={k: k for k in self.UNITS}))
        self.compatible = self.row("", Switch(tr('Maximum compatibility'), compatible))
        self.compatible.setToolTip(tr('For older programs or SketchUp: classic meshes (slower).'))
        self.visible = self.row("", Switch(tr('Only what is visible'), visible_only))
        self.visible.setToolTip(tr('Removes hidden lines: what is behind is not drawn.'))
        self.mode.change.connect(lambda _: self._by_mode())
        self.visible.toggled.connect(lambda _: self._by_mode())
        self._by_mode()
        self.finish()

    def _by_mode(self) -> None:
        in_2d = self.mode.value() == 1
        self.display_row(self.view, in_2d)
        self.display_row(self.compatible, not in_2d)   # in 2D they are lines: anyone reads them
        self.display_row(self.visible, in_2d)
        if in_2d:
            self.note.setText(tr('At real size (the scale is set when printing). One layer per node, with its colour.')
                              + ("" if self.visible.isChecked() else " " + tr('All edges come out, also those behind.')))
        else:
            self.note.setText(tr('One layer per node, with its colour; each piece, a separate object. Z up.'))
        self.adjustSize()

    def choice(self) -> tuple[str, bool, str | None, bool]:
        """(unit, compatible, view, visible only); the view is None in 3D."""
        view = self.view.value() if self.mode.value() == 1 else None
        return self.unit.value(), self.compatible.isChecked(), view, self.visible.isChecked()


class _Page(QWidget):
    """A page of Preferences: its title, and groups with a heading and a line that separates them."""

    def __init__(self, title: str):
        super().__init__()
        self._layer = QVBoxLayout(self)
        self._layer.setContentsMargins(24, 18, 24, 18)
        self._layer.setSpacing(10)
        head = QLabel(tr(title))
        head.setProperty("role", "page_title")
        self._layer.addWidget(head)
        self._grid = None

    def group(self, title: str, help: str = "") -> None:
        line = QFrame()
        line.setObjectName("divisor")
        line.setFixedHeight(1)
        self._layer.addSpacing(6)
        self._layer.addWidget(line)
        heading = QLabel(tr(title))
        heading.setProperty("role", "title")
        self._layer.addWidget(heading)
        if help:
            note = QLabel(tr(help))
            note.setProperty("role", "small")
            note.setWordWrap(True)
            self._layer.addWidget(note)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(10)
        self._grid.setColumnStretch(1, 1)
        self._grid.setColumnMinimumWidth(0, 150)
        self._layer.addLayout(self._grid)

    def row(self, label: str, control: QWidget, help: str = "") -> QWidget:
        n = self._grid.rowCount()
        if label:
            e = QLabel(tr(label))
            e.setContentsMargins(0, 6, 0, 0)
            self._grid.addWidget(e, n, 0, Qt.AlignmentFlag.AlignTop)
            control.label_of_row = e                  # (so that the whole row can be hidden)
        self._grid.addWidget(control, n, 1)
        if help:
            note = QLabel(tr(help))
            note.setProperty("role", "small")
            note.setWordWrap(True)
            self._grid.addWidget(note, n + 1, 1)
        return control

    def finish(self, extra: QWidget | None = None) -> None:
        if extra is not None:
            self._layer.addWidget(extra, 1)
        else:
            self._layer.addStretch(1)


class DialogPreferences(QDialog):
    """Preferences by sections: General, 3D view, Nodes, Units and Interaction. Each change is applied at once and
    remembered: `apply(key, value)`."""

    SECTIONS = ("General", '3D view', 'Nodes', 'Units', 'Interaction', 'Code editor')

    def __init__(self, parent, values: dict, apply, themes: list[tuple[str, str]], shortcuts: list[tuple]):
        super().__init__(parent)
        self.setWindowTitle(tr('Preferences'))
        self.resize(820, 560)
        self._apply = apply
        list_ = QListWidget()
        list_.setObjectName("sections")
        list_.setFixedWidth(180)
        pages = QStackedWidget()
        for name in self.SECTIONS:
            list_.addItem(tr(name))
        list_.currentRowChanged.connect(pages.setCurrentIndex)
        all_ = QHBoxLayout(self)
        all_.setContentsMargins(0, 0, 0, 0)
        all_.setSpacing(0)
        all_.addWidget(list_)
        right = QVBoxLayout()
        right.addWidget(pages, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(24, 0, 24, 16)
        self.note = QLabel(tr('Changes show at once and are remembered.'))
        self.note.setProperty("role", "small")
        foot.addWidget(self.note, 1)
        ready = QPushButton(tr('Done'))
        ready.setDefault(True)
        ready.clicked.connect(self.accept)
        foot.addWidget(ready)
        right.addLayout(foot)
        all_.addLayout(right, 1)

        def segmented(key, options, help_texts=None):
            control = Segmented(options, values.get(key), help_texts=help_texts)
            control.change.connect(lambda v, k=key: self._change(k, v))
            return control

        def switch(key, text):
            control = Switch(text, bool(values.get(key)))
            control.toggled.connect(lambda v, k=key: self._change(k, v))
            return control

        TONES = [("theme", 'Like the theme', None), ("light", 'Light', None), ("mid", 'Mid', None), ("dark", 'Dark', None)]      # the background, apart from the theme

        # General
        p = _Page("General")
        p.group('Language', 'The language changes when Tensela is opened again.')
        p.row('Language', segmented("preferences/language", [("es", "Español", None), ("en", "English", None)]))
        p.group('On opening')
        p.row("", switch("start/show", 'Show the start screen (new project, recent ones and recipes)'))
        p.group('Calculating', 'What is seen: the nodes with their eye on, the chosen one, the open previews and the '
                'Info nodes, with what feeds them; the rest is calculated when it is looked at (a click on its card '
                'or its row in Data). Everything: every node, each time, as before.')
        p.row('Calculate', segmented("compute/what", [("seen", 'What is seen', None), ("all", 'Everything', None)]))
        p.group('Applications menu', 'Tensela in the menu of your desktop, with its icon, and .tela files that open with '
                'a double click. For the AppImage and the portable folder; it goes into your folders '
                '(~/.local/share), not into the system.')
        p.row("", self._menu_row(values))
        p.group('Appearance')
        p.row('Mode', segmented("theme/mode", [("system", 'Like the system', None), ("light", 'Light', None),
                                                ("dark", 'Dark', None)]))
        p.group('Location', 'Where a new Sun, Insolation or Daylight starts (each one can then have another): the '
                         'sun, the shadows and the light are computed for it.')
        location = QComboBox()
        location.setObjectName("preferences_location")
        from ..sun import CITIES, OTHER
        for key in values.get("_locations") or list(CITIES) + [OTHER]:
            location.addItem(tr(key), key)
        location.setCurrentIndex(max(0, location.findData(values.get("preferences/location"))))
        p.row('City', location)
        # «Other place»: its latitude, longitude and time zone, written.
        from .window import CellNumber
        numbers = []
        for key, label, low, high, default, help_ in (
                ("preferences/latitude", 'Latitude', -90.0, 90.0, 40.42, '+ north of the equator, − south'),
                ("preferences/longitude", 'Longitude', -180.0, 180.0, -3.70, '+ east of Greenwich, − west'),
                ("preferences/time_zone", 'Time zone', -12.0, 14.0, 1.0, 'hours from UTC, without summer time')):
            field = CellNumber()
            field.setRange(low, high)
            field.setDecimals(3 if key != "preferences/time_zone" else 1)
            try:
                field.setValue(float(values.get(key, default)))
            except (TypeError, ValueError):
                field.setValue(default)
            field.setToolTip(tr(help_))
            field.editingFinished.connect(lambda k=key, f=field: self._change(k, f.value()))
            numbers.append(p.row(label, field))

        def show_numbers() -> None:
            for row in numbers:
                row.setVisible(location.currentData() == OTHER)
                row.label_of_row.setVisible(location.currentData() == OTHER)
        location.currentIndexChanged.connect(lambda _: (self._change("preferences/location", location.currentData()),
                                                        show_numbers()))
        show_numbers()
        p.finish()
        pages.addWidget(p)

        # Vista 3D
        p = _Page('3D view')
        p.group('On opening')
        style_name = QComboBox()
        for key, text in values["_styles"]:
            style_name.addItem(tr(text), key)
        style_name.setCurrentIndex(max(0, style_name.findData(values.get("view/style"))))
        style_name.currentIndexChanged.connect(lambda _: self._change("view/style", style_name.currentData()))
        p.row('Style', style_name, "It can also be changed in the view's header or with a right-click.")
        p.row('Background', segmented("preferences/view_tone", TONES))
        p.row("", switch("view/axes", 'Show the axes'))
        p.finish()
        pages.addWidget(p)

        # Nodos
        p = _Page('Nodes')
        p.group('Node cards', "How each node's header is drawn according to its category.")
        p.row('Style', segmented("theme/name", [(k, t, None) for k, t in themes], help_texts={
            "sober": 'Neutral node cards, with a strip of colour',
            "vivid": 'Node headers fully coloured'}))
        p.group('Canvas')
        p.row('Background', segmented("preferences/canvas_tone", TONES))
        p.row('Pattern', segmented("preferences/canvas_background", [("dots", 'Dots', None),
                                                                  ("squares", 'Square grid', None), ("plain", 'Plain', None)]))
        p.row("", switch("canvas/guides", 'Smart guides'))
        p.row("", switch("canvas/grid", 'Snap to grid'))
        p.finish()
        pages.addWidget(p)

        # Unidades
        p = _Page('Units')
        p.group('Lengths', 'You can type any unit (120 cm, 4\', 6 1/2"); a plain number is read in the chosen one. The'
                           ' project is always saved in metres.')
        p.row('Show in', segmented("preferences/length_unit", [
            ("m", "m", None), ("cm", "cm", None), ("mm", "mm", None), ("ft-in", "pies y pulgadas", None),
            ("ft", "pies", None), ("in", "pulgadas", None)]))
        p.row('Decimals', segmented("preferences/decimals", [("auto", "Auto", None)] + [
            (str(n), str(n), None) for n in range(5)], help_texts={"auto": 'As many as needed, up to 4'}))
        self._fraction = p.row('Inch fraction', segmented("preferences/fraction", [
            (n, f"1/{n}", None) for n in (2, 4, 8, 16, 32, 64)]), 'For feet and inches: 12\'-6 1/2".')
        p.finish()
        pages.addWidget(p)

        # Interaction
        p = _Page('Interaction')
        p.group('Mouse in the 3D view', 'In all of them, the view orbits around what is under the pointer.')
        self.mouse = p.row('Like', segmented("preferences/navigation",
                                                  [(k, t, None) for k, t in values["_schemes"]],
                                                  help_texts=values["_scheme_help"]))
        self._mouse_help = QLabel(tr(values["_scheme_help"].get(values.get("preferences/navigation"), "")))
        self._mouse_help.setProperty("role", "small")
        self._mouse_help.setWordWrap(True)
        p.row("", self._mouse_help)
        self.mouse.change.connect(lambda k: self._mouse_help.setText(tr(values["_scheme_help"].get(k, ""))))
        self.zoom = p.row('Zoom', segmented("preferences/zoom", [
            ("pointer", 'Towards the pointer', None), ("centre", 'Towards the centre', None)]),
            'With the wheel or dragging: what is under the pointer stays under it, or the centre of the view stays.')
        p.group('Keyboard shortcuts', 'Click a shortcut and press the new keys.')
        table = QTableWidget(len(shortcuts), 2)
        table.setObjectName("shortcuts_table")
        table.setHorizontalHeaderLabels([tr('Action'), tr('Shortcut')])
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 200)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._editors = {}
        for row, (key, text, current, _default) in enumerate(shortcuts):
            table.setItem(row, 0, QTableWidgetItem(text.replace("&", "")))
            editor = QKeySequenceEdit(QKeySequence(current))
            editor.setMaximumSequenceLength(1)
            editor.editingFinished.connect(lambda k=key, e=editor: self._change(f"shortcuts/{k}", e.keySequence().toString()))
            table.setCellWidget(row, 1, editor)
            self._editors[key] = editor
        reset = QPushButton(tr('Reset the shortcuts'))

        def from_factory():
            for key, _text, _current, default in shortcuts:
                self._editors[key].setKeySequence(QKeySequence(default))
                self._change(f"shortcuts/{key}", default)
        reset.clicked.connect(from_factory)
        box = QWidget()
        layer = QVBoxLayout(box)
        layer.setContentsMargins(0, 0, 0, 0)
        layer.addWidget(table, 1)
        layer.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        p.finish(box)
        pages.addWidget(p)

        # The editor of the Code node
        from .code_editor import SIZES
        p = _Page('Code editor')
        p.group('Colours', 'Like the window follows its light or dark mode; the others are the editor’s own.')
        p.row('Theme', segmented("code/colours", [("window", 'Like the window', None), ("paper", 'Paper', None),
                                                  ("night", 'Night', None), ("contrast", 'High contrast', None)]))
        p.group('Letter', 'Also in the editor: Ctrl + and Ctrl − (Ctrl 0, the usual).')
        fonts = QFontComboBox()
        fonts.setObjectName("code_font")
        fonts.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        from PySide6.QtGui import QFontDatabase
        fonts.setCurrentFont(QFont(values["code/font"]) if values.get("code/font") else
                             QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        fonts.currentFontChanged.connect(lambda f: self._change("code/font", f.family()))
        p.row('Font', fonts)
        size = float(values.get("code/size") or 0)
        sizes = [("0", 'Usual', None)] + [(str(n), str(n), None) for n in SIZES]
        size_control = Segmented(sizes, str(int(size)) if int(size) in SIZES else "0")
        size_control.change.connect(lambda v: self._change("code/size", float(v)))
        p.row('Size', size_control)
        p.group('Helps while writing')
        p.row("", switch("code/pairs", 'Close brackets and quotes'))
        p.row("", switch("code/complete", 'Suggest names while writing (Ctrl+Space, always)'))
        p.finish()
        pages.addWidget(p)

        start = values.get("_section")
        list_.setCurrentRow(self.SECTIONS.index(start) if start in self.SECTIONS else 0)
        self._values = values

    def _menu_row(self, values: dict) -> QWidget:
        """Whether Tensela is in the applications menu, and the button that puts it there or takes it out."""
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        state = QLabel()
        state.setWordWrap(True)
        button = QPushButton()
        button.setObjectName("preferences_menu")
        row.addWidget(state, 1)
        row.addWidget(button)
        image = values.get("_desktop_image")
        current = {"for": values.get("_desktop_for")}

        def show(there: bool) -> None:
            if there and image and current["for"] not in (None, image):
                # The menu starts another copy (the AppImage, and this is the portable folder, or the other way round).
                state.setText(tr('It is in the menu, but for another copy of Tensela: {path}').format(
                    path=current["for"]))
                button.setText(tr('Put this one in the menu'))
                button.setEnabled(True)
                button.setProperty("there", False)
                return
            if there:
                state.setText(tr('It is in the menu.'))
                button.setText(tr('Take it out of the menu'))
            elif image:
                state.setText(tr('It is not in the menu.'))
                button.setText(tr('Add to the menu'))
            else:
                state.setText(tr('Tensela runs from its code here, not from the AppImage or its portable folder: '
                                 'nothing to add.'))
                button.setText(tr('Add to the menu'))
            button.setEnabled(bool(there or image))
            button.setProperty("there", there)

        def click() -> None:
            yes = not button.property("there")
            there = values["_desktop_put"](yes)
            current["for"] = (image if yes else current["for"]) if there else None
            show(there)

        button.clicked.connect(click)
        show(bool(values.get("_desktop_installed")))
        return box

    def _change(self, key: str, value) -> None:
        self._apply(key, value)
        if key == "preferences/language":
            self.note.setText(tr('The language changes when Tensela is opened again.')
                              if value != self._values.get("_current_language") else
                              tr('Changes show at once and are remembered.'))
