"""The panel of the selected node (Delivery 2, E2.5 and E2.7).

It shows the node chosen in the editor: its name (it can be changed), what it does, whether it is seen in 3D, and
each input: connected (which node it comes from) or with its fixed value, written as an architect would (0,4 · 120 cm
· elevation). A numeric value can be turned into a slider.

The panel does not touch the graph: it asks for the changes with signals and the window makes them.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton, QScrollArea, QSlider,
    QToolButton, QVBoxLayout, QWidget,
)

from ..project_file import LEVEL_INPUTS, slidable, numbers_items
from ..graph import Node, drawable
from ..nodes import automatic_level, options_of, suggestions, visible_input
from ..values import is_length, label_input, text_of, text_value
from . import icons as icons, theme as theme
from .widgets import (NAME_LIMIT, ActionTile, ButtonColor, Switch, Panel, Segmented, ask_text, button_icon,
                      tile_button, tiles, complete_inline)
from ..language import tr


class SeveralFields(QObject):
    """Several numbers at once: press on one and drag up or down over the others; they are chosen together
    (highlighted) and what is then typed goes to all of them, as one change. Esc, or a click elsewhere, lets go."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fields: list[tuple[QLineEdit, str]] = []   # in their order in the panel
        self.group: list[str] = []
        self._start: QLineEdit | None = None
        self._press_y = 0.0

    def clear_all(self) -> None:
        self.fields, self.group, self._start = [], [], None

    def add(self, field: QLineEdit, input_: str) -> None:
        self.fields.append((field, input_))
        field.setProperty("number_field", True)
        field.installEventFilter(self)

    def _mark(self, names: list[str]) -> None:
        self.group = names if len(names) > 1 else []
        accent = theme.color("accent", "#7c5cff")
        for field, name in self.fields:
            field.setStyleSheet(f"QLineEdit {{ border: 1px solid {accent}; }}" if name in self.group else "")

    def let_go(self) -> None:
        self._mark([])

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if watched not in [f for f, _ in self.group_fields()]:
                self.let_go()
            self._start, self._press_y = watched, event.globalPosition().y()
            return False
        if kind == QEvent.Type.MouseMove and self._start is watched and event.buttons() & Qt.MouseButton.LeftButton:
            if abs(event.globalPosition().y() - self._press_y) < 6 and not self.group:
                return False
            under = QApplication.widgetAt(event.globalPosition().toPoint())
            order = [f for f, _ in self.fields]
            target = next((f for f in order if under is not None and (f is under or f.isAncestorOf(under))), None)
            if target is not None:
                a, b = sorted((order.index(watched), order.index(target)))
                self._mark([name for _, name in self.fields[a:b + 1]])
            return bool(self.group)                  # dragging over others: no text selection meanwhile
        if kind == QEvent.Type.MouseButtonRelease and self._start is watched:
            self._start = None
            if self.group:
                watched.setFocus()
                watched.selectAll()
                return True
        if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and self.group:
            self.let_go()
        return False

    def group_fields(self) -> list[tuple[QLineEdit, str]]:
        return [(f, n) for f, n in self.fields if n in self.group]


class PanelNode(Panel):
    rename = Signal(str, str)              # viejo, nuevo
    change = Signal(str, str, str)           # nodo, entrada, texto escrito
    change_several = Signal(str, list, str)  # node, inputs, the text typed for all of them
    toggle_slider = Signal(str, str, bool)
    toggle_see = Signal(str, bool)
    change_color = Signal(str, str)          # node, colour «#rrggbb»
    change_opacity = Signal(str, float, bool)  # node, opacity (0 to 1), final (on releasing the slider)
    colour_by = Signal(str, str, str)          # node, the node whose value the colour comes from («» = a single colour), gradient
    toggle_number = Signal(str, bool)
    toggle_curvature = Signal(str, bool)
    analyse = Signal(str, str)                 # node, «no» · «gaussian» · «mean» · «zebra»
    change_value = Signal(str, str, object, bool)   # node, input, value (not text), final: the Graph         # node: with its numbers (and the direction of its curves) in the view
    draw = Signal(str)
    code = Signal(str)                              # node: open the editor of its code
    play = Signal(str, str, float, float)           # node, input, from, to: play that input (to see it move)
    stop_play = Signal(str, str)                    # node, input: stop playing it, back to the value of before
    rest = Signal()                                 # «Calculate the rest»: the nodes not seen, calculated once
    playing = None                                  # what is being played now (the window says so)
    waiting = 0                                     # how many nodes are not calculated (not seen): the window says so

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr('Node'), parent)
        # The content scrolls if it does not fit (the rows are not squashed).
        self._scrollable = QScrollArea()
        self._scrollable.setWidgetResizable(True)
        self._scrollable.setFrameShape(QFrame.Shape.NoFrame)
        self.body.addWidget(self._scrollable)
        self._content: QWidget | None = None
        self._scroll_back: int | None = None
        self._scrollable.verticalScrollBar().rangeChanged.connect(self._scroll_to_where_it_was)
        self.several = SeveralFields(self)
        self.display(None)

    def _scroll_to_where_it_was(self, _low: int, high: int) -> None:
        if self._scroll_back is not None and high > 0:
            self._scrollable.verticalScrollBar().setValue(min(self._scroll_back, high))
            if high >= self._scroll_back:
                self._scroll_back = None

    def _stop_scrolling_back(self) -> None:
        if self._scroll_back is not None:
            bar = self._scrollable.verticalScrollBar()
            bar.setValue(min(self._scroll_back, bar.maximum()))
            self._scroll_back = None

    def display(self, node: Node | None, sees: bool = False, sliders: set[str] = frozenset(),
                color: str | None = None, opacity: float = 1.0, number: bool = False,
                by: str | None = None, gradient: str = "", candidates: list[str] | None = None,
                curvature: bool = False, analysis: str = "no", together: int = 1,
                differing: dict[str, list[str]] | None = None) -> None:
        """Shows `node` (or a notice if none is chosen). `together`: how many nodes of its kind are chosen with it (what
        is changed in its inputs changes in all of them); `differing`: the inputs whose value is not the same in all
        of them, {input: ["box A: 1 m", …]} (the panel shows the first one's and marks the row).

        `sliders`: the inputs of this node that are already a slider. `by`: the node whose value its colour comes from
        (painted by a value), and `candidates`, those that can be chosen.
        """
        if hasattr(self, "several"):
            self.several.clear_all()                 # the fields are made again
        # The same node shown again (a value changed): the panel stays where it was scrolled, not at the top.
        # (Shown twice in a row, the second time the scroll is still the one waiting to be put back.)
        bar = self._scrollable.verticalScrollBar()
        same = node is not None and node.name == getattr(self, "_shown", None)
        waiting = getattr(self, "_scroll_back", None)
        where = (waiting if waiting is not None else bar.value()) if same else 0
        self._shown = node.name if node is not None else None
        old = self._scrollable.takeWidget()     # out now, not when Qt deletes it
        if old is not None:
            old.deleteLater()
        self._scroll_back = where or None
        if where:                              # put back once the new content has its height (or as far as it goes)
            QTimer.singleShot(250, self._stop_scrolling_back)
        self._content = QWidget()
        layer = QVBoxLayout(self._content)
        layer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)   # if it does not fit, it scrolls
        layer.setContentsMargins(0, 0, 4, 0)
        layer.setSpacing(8)
        self._scrollable.setWidget(self._content)

        if node is None:
            layer.addStretch(1)
            drawing = QLabel()
            drawing.setPixmap(icons.pixmap("node", theme.color("disabled", "#5b6070"), 44, self.devicePixelRatioF()))
            drawing.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title = QLabel(tr('Pick a node'))
            title.setProperty("role", "title")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            help = QLabel(tr('Double-click on the canvas, or Tab, to add one.'))
            help.setProperty("role", "secondary")
            help.setAlignment(Qt.AlignmentFlag.AlignCenter)
            help.setWordWrap(True)
            for w in (drawing, title, help):
                layer.addWidget(w)
            layer.addStretch(2)
            return

        # The name, as a title that can be edited.
        self.name = QLineEdit(node.name)
        self.name.setMaxLength(max(NAME_LIMIT, len(node.name)))     # (a longer name of before is not cut)
        self.name.setObjectName("editable_title")
        self.name.setToolTip(tr("The node's name. It's yours: give it one that says what it is."))
        previous = node.name
        self.name.editingFinished.connect(
            lambda: self.name.text().strip() != previous and self.rename.emit(previous, self.name.text()))
        head = QHBoxLayout()
        icon_category = icons.of_kind(node.kind.name, node.kind.category)
        if icon_category:
            mark = QLabel()
            color_category = theme.current()["p"]["categories"].get(node.kind.category) if theme.current() else "#8a7dff"
            mark.setPixmap(icons.pixmap(icon_category, color_category, 20, self.devicePixelRatioF()))
            mark.setToolTip(tr(node.kind.category))
            head.addWidget(mark)
        head.addWidget(self.name, 1)
        layer.addLayout(head)

        what = QLabel(f"{tr(node.kind.name)} → {tr(node.kind.output)}")
        what.setProperty("role", "secondary")
        what.setToolTip(tr(node.kind.help))
        layer.addWidget(what)
        if together > 1:                            # several of its kind chosen: one change for all of them
            note = QLabel(tr('{n} “{kind}” chosen: what you change in their inputs changes in all of them (name, '
                             'colour, sliders and “Show in 3D”, each its own).').format(n=together,
                                                                                       kind=tr(node.kind.name)))
            note.setWordWrap(True)
            note.setObjectName("together_note")
            note.setStyleSheet(f"color: {theme.color('accent', '#8a7dff')};")
            layer.addWidget(note)
        if drawable(node):                          # the main thing of this node, at the top, as a tile
            input_ = "stroke" if node.inputs.get('mode') == 'pen' else "points"
            layer.addWidget(tiles([self._button_draw(node, node.inputs.get(input_), input_)]))
        if node.kind.name == 'Code' and not isinstance(node.inputs.get("code"), Node):
            layer.addWidget(self._button_code(node))   # the main thing of this node: its code
        if node.kind.name == 'Lay flat':           # the main thing of this node: how many sheets, how full
            layer.addWidget(self._layout_report(getattr(getattr(node, "_value", None), "layout", None)))
        if node.kind.name == 'Print check':        # the main thing of this node: what it found, piece by piece
            layer.addWidget(self._print_report(getattr(getattr(node, "_value", None), "report", None),
                                               node.inputs.get("show") == 'printer'))
        if node.kind.name == 'Equilibrium':        # moving its supports in the view, and seeing how it reaches its rest
            layer.addWidget(tiles([self._button_move_supports(node), self._button_play_moment(node)]))
        if node.kind.name == 'Topology optimization':   # seeing how it takes shape, turn after turn
            layer.addWidget(tiles([self._button_play_moment(node)]))
        if node.kind.name == 'Edit mesh':          # the main thing of this node: moving its vertices in the view
            layer.addWidget(tiles([self._button_edit_mesh(node)]))
        if node.kind.name == 'Graph':            # the curve, to draw it by moving its points
            layer.addWidget(self._editor_chart(node))
        if node.kind.name in ('Function', 'Formula'):  # what it is for, and how it is written
            layer.addWidget(self._guide_function(node))

        # Seeing it in 3D (and exporting it), with its colour. Not in those that only compute (Area, Formula…) nor in Info:
        # there is nothing to see in 3D (their values are read on the card, with its «i»).
        value = getattr(node, "_value", None)
        only_values = node.kind.name == 'Info' or (value is not None and getattr(value, "kind", None) is None)
        if only_values:
            sees = None
        row_see = QHBoxLayout()
        see = Switch(tr('Show in 3D'), bool(sees))
        see.setToolTip(tr('Shown in the 3D view and included when exporting.'))
        see.toggled.connect(lambda yes: self.toggle_see.emit(node.name, yes))
        row_see.addWidget(see)
        see.setVisible(sees is not None)
        row_see.addStretch(1)
        if sees:
            shows = ButtonColor(color or "#7d8a96", 'The colour it is shown with in 3D (and exported)',
                                 tr('Colour of “{node}”').format(node=node.name))
            shows.chosen.connect(lambda c: self.change_color.emit(node.name, c))
            row_see.addWidget(shows)
        layer.addLayout(row_see)
        if sees:                                # how much is seen through: from 10 % (almost nothing) to 100 % (opaque)
            row_opacity = QHBoxLayout()
            label = QLabel(tr('Opacity'))
            label.setProperty("role", "secondary")
            row_opacity.addWidget(label)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(10, 100)
            slider.setSingleStep(5)
            slider.setPageStep(10)
            slider.setValue(round(opacity * 100))
            slider.setToolTip(tr('How much it hides what is behind: 100 %, opaque; less, see-through.'))
            row_opacity.addWidget(slider, 1)
            percentage = QLabel(f"{slider.value()} %")
            percentage.setMinimumWidth(QFontMetrics(percentage.font()).horizontalAdvance("100 %") + 4)
            percentage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_opacity.addWidget(percentage)

            def move(value: int) -> None:
                percentage.setText(f"{value} %")
                # Dragging: only the view; on releasing (or with the keyboard), the change stays in the project.
                self.change_opacity.emit(node.name, value / 100, not slider.isSliderDown())

            slider.valueChanged.connect(move)
            slider.sliderReleased.connect(lambda: self.change_opacity.emit(node.name,
                                                                                  slider.value() / 100, True))
            layer.addLayout(row_opacity)
            layer.addWidget(self._row_colour_by(node, by, gradient, candidates or []))
            # The order: the number of each point or element (from 0) and, on the curves, where they start and where
            # they go. To know what position to ask for in Pick, or whether a curve has to be flipped.
            # What it shows depends on what it is: the numbers (points, several elements) and, on the curves, their
            # direction (where they start and where they go).
            curve = value is not None and getattr(value, "kind", None) is not None and value.kind.curve
            several = value is not None and bool(getattr(value, "levels", ()))
            if curve or several:                  # a single element that is not a curve: there is nothing to number
                text = (tr('Number and show direction') if curve and several else tr('Show direction') if curve
                         else tr('Number in 3D'))
                numbers = Switch(text, number)
                numbers.setToolTip(tr('The number of each point or element in the view (from 0); on curves, where '
                                      'they start and an arrow showing their direction.'))
                numbers.toggled.connect(lambda yes: self.toggle_number.emit(node.name, yes))
                row_numbers = QHBoxLayout()
                row_numbers.addWidget(numbers)
                row_numbers.addStretch(1)
                layer.addLayout(row_numbers)
            surface = value is not None and getattr(value, "kind", None) is not None and \
                value.kind.faces is not None and not value.kind.curve
            if surface:                       # analyse: the curvature (is it made from a flat sheet?) or the zebra
                row_analysis = QHBoxLayout()
                label = QLabel(tr('Analyse'))
                label.setProperty("role", "secondary")
                row_analysis.addWidget(label)
                from .viewer import ANALYSIS, OLD_ANALYSIS
                analysis = OLD_ANALYSIS.get(analysis, analysis)
                selector = Segmented([(a, a, None) for a in ANALYSIS], analysis if analysis in ANALYSIS else "no",
                                      help_texts={'gaussian': 'Gaussian curvature: green, what can be made from flat sheet or board '
                                                           '(planes, cylinders, cones: developable); orange and red, '
                                                           'dome-like double curvature; blue, saddle-like',
                                              'mean': 'Mean curvature: how much it bends, on average, in both '
                                                      'directions; green, hardly at all (also a balanced saddle); '
                                                      'red and blue, a lot towards one side of the face or the other',
                                              'zebra': 'The reflection of light bars (it moves as the view turns): if '
                                                       'the stripes continue without breaks from one surface to the '
                                                       'next, the join is smooth'})
                selector.change.connect(lambda mode: self.analyse.emit(node.name, mode))
                row_analysis.addWidget(selector, 1)
                layer.addLayout(row_analysis)
            if curve:                            # the curvature comb: is the curve smooth?
                comb = Switch(tr('Show curvature'), curvature)
                comb.setToolTip(tr('The curvature comb: longer hairs where the curve bends more; a really smooth '
                                    'curve has a comb edge without jumps'))
                comb.toggled.connect(lambda yes: self.toggle_curvature.emit(node.name, yes))
                row_comb = QHBoxLayout()
                row_comb.addWidget(comb)
                row_comb.addStretch(1)
                layer.addLayout(row_comb)

        visible = [e for e in node.kind.inputs if visible_input(node, e)]
        main = [e for e in visible if not e.advanced]
        advanced = [e for e in visible if e.advanced]
        for group, inputs in (("main", main), ("advanced", advanced)):
            if not inputs:
                continue
            grid = QGridLayout()
            grid.setColumnStretch(1, 1)
            grid.setVerticalSpacing(8)
            if group == "advanced":             # «More settings»: closed at first; remembered per node kind
                opened = node.kind.name in PanelNode.open_more_settings
                more = QToolButton()
                more.setObjectName("flat_button")
                more.setCheckable(True)
                more.setChecked(opened)
                more.setText(tr('More settings'))
                more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                more.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
                more.setToolTip(tr('Settings for those who need them (the defaults work almost always)'))
                layer.addWidget(more)
                box = QWidget()
                box.setLayout(grid)
                box.setVisible(opened)
                layer.addWidget(box)

                def open_(yes: bool, button=more, box=box) -> None:
                    box.setVisible(yes)
                    button.setArrowType(Qt.ArrowType.DownArrow if yes else Qt.ArrowType.RightArrow)
                    (PanelNode.open_more_settings.add if yes else PanelNode.open_more_settings.discard)(
                        node.kind.name)
                more.toggled.connect(open_)
            else:
                layer.addLayout(grid)
            for row, input_ in enumerate(inputs):
                label = QLabel(label_input(input_.name))
                label.setProperty("role", "secondary")
                label.setToolTip(tr(input_.help))
                if input_.name in (differing or {}):     # not the same in all the chosen: said, with each one's
                    label.setText(label_input(input_.name) + " · " + tr('varies'))
                    label.setObjectName("varies")
                    label.setStyleSheet(f"color: {theme.color('accent', '#8a7dff')};")
                    label.setToolTip(tr('Not the same in all the chosen ones: {values}. The field shows the first '
                                        'one\'s; what you write goes to all of them.').format(
                        values=" · ".join(differing[input_.name])))
                v = node.inputs[input_.name]
                if input_.file and not isinstance(v, Node):     # the picture below: the name, beside the path
                    label.setFixedHeight(QLineEdit().sizeHint().height())
                    grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
                else:
                    grid.addWidget(label, row, 0)
                if isinstance(v, Node):
                    from_ = QLabel(f"← {v.name}")
                    from_.setEnabled(False)
                    from_.setToolTip(tr('Comes from another node. To type a value, disconnect the wire.'))
                    grid.addWidget(from_, row, 1, 1, 2)
                    continue
                if node.kind.name == 'Code' and input_.name == "code":
                    how_long = QLabel(text_of("code", v))   # the button to edit it is above
                    how_long.setProperty("role", "secondary")
                    grid.addWidget(how_long, row, 1, 1, 2)
                    continue
                if node.kind.name == 'Equilibrium' and input_.name == "hand_supports":
                    how_many = QLabel(text_of("hand_supports", v if isinstance(v, (list, tuple)) else []))
                    how_many.setProperty("role", "secondary")
                    grid.addWidget(how_many, row, 1, 1, 2)
                    continue
                if node.kind.name == 'Edit mesh' and input_.name == "moves":
                    how_many = QLabel(_moved_text(v))     # the button to edit them is above
                    how_many.setProperty("role", "secondary")
                    grid.addWidget(how_many, row, 1, 1, 2)
                    continue
                if (node.kind.name == 'Graph' or drawable(node)) and input_.name in ("points", "stroke"):
                    how_many = QLabel(text_of(input_.name, v))     # the button to edit them is above
                    how_many.setProperty("role", "secondary")
                    grid.addWidget(how_many, row, 1, 1, 2)
                    continue
                grid.addWidget(self._field(node, input_, v), row, 1)
                if slidable(v):
                    button = button_icon("values", tr('Show this value as a slider in “Values”') if numbers_items(v) is None
                                        else tr('Show each value of the list as a slider in “Values”'), checkable=True)
                    button.setChecked(input_.name in sliders)
                    button.toggled.connect(lambda yes, e=input_.name: self.toggle_slider.emit(node.name, e, yes))
                    grid.addWidget(button, row, 2)
        layer.addStretch(1)

    #: The node whose points are being drawn in the view (the window sets it).
    drawing: str | None = None
    #: The node kinds with «More settings» open (while the session lasts).
    open_more_settings: set = set()

    def _row_colour_by(self, node: Node, by: str | None, gradient: str, candidates: list[str]) -> QWidget:
        """A single colour, or by a value (the *Gradient*): which node the value comes from, and with what gradient."""
        from .viewer import GRADIENTS
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        row = QHBoxLayout()
        label = QLabel(tr('Colour'))
        label.setProperty("role", "secondary")
        row.addWidget(label)
        mode = Segmented([("one", 'one colour', None), ("value", 'by a value', None)], "value" if by else "one",
                          help_texts={"one": 'All in the same colour',
                                      "value": 'Each element in the colour of its value (an Attractor, a Distance…)'})
        row.addWidget(mode, 1)
        column.addLayout(row)
        gradient = gradient if gradient in GRADIENTS else next(iter(GRADIENTS))
        if by:
            fonts = QComboBox()
            fonts.addItems(sorted(set(candidates) | {by}))
            fonts.setCurrentText(by)
            fonts.setToolTip(tr('The node that gives each element its value'))
            fonts.activated.connect(lambda _: self.colour_by.emit(node.name, fonts.currentText(),
                                                                   gradients.currentData()))
            gradients = QComboBox()
            for name_gradient, stops in GRADIENTS.items():
                gradients.addItem(_icon_gradient(stops), tr(name_gradient), name_gradient)
            gradients.setCurrentIndex(list(GRADIENTS).index(gradient))
            gradients.setToolTip(tr('From the smallest value (left) to the largest (right)'))
            gradients.activated.connect(lambda _: self.colour_by.emit(node.name, fonts.currentText(),
                                                                      gradients.currentData()))
            rows = QGridLayout()
            rows.setColumnStretch(1, 1)
            for i, (text, control) in enumerate(((tr('by'), fonts), (tr('gradient'), gradients))):
                e = QLabel(text)
                e.setProperty("role", "secondary")
                rows.addWidget(e, i, 0)
                rows.addWidget(control, i, 1)
            column.addLayout(rows)

        def pick(value) -> None:
            if value == "one":
                self.colour_by.emit(node.name, "", gradient)
            elif candidates:
                self.colour_by.emit(node.name, by or candidates[0], gradient)
            else:
                warning.show()
        mode.change.connect(pick)
        warning = QLabel(tr('No node gives a value per element of this geometry. Connect, for example, an Attractor '
                          'or a Distance with these same elements.'))
        warning.setWordWrap(True)
        warning.setProperty("role", "small")
        warning.hide()
        column.addWidget(warning)
        if self.waiting:                        # only what is calculated is offered: the rest may give more values
            rest = QPushButton(tr('Calculate the rest ({n} not calculated): they may give more values').format(
                n=self.waiting))
            rest.setToolTip(tr('The nodes that are not seen are not calculated, so they are not offered here yet.'))
            rest.clicked.connect(self.rest.emit)
            rest.setVisible(bool(by))
            mode.change.connect(lambda value: rest.setVisible(value == "value"))
            column.addWidget(rest)
        return box

    def _guide_function(self, node: Node) -> QWidget:
        """A Function: what the chosen one is for. A Formula: what can be written, with examples."""
        if node.kind.name == 'Function':
            from ..functions import for_what
            text = "💡 " + for_what(node.inputs.get("shape", "wave"))
        else:
            text = tr('Variables: from “a” to “h” (connect a number or a list to each).\nFunctions: sin, cos, tan '
                       '(in degrees) · sqrt · abs · min(a; b) · max(a; b) · if(condition; yes; no) · exp · log · '
                       'cosh · round · pi · phi (the golden ratio).\nConditions: < > <= >= = <> · and · or · '
                       'not(…). Several cases: if(a < 2; 0; a < 4; 1; 2).\nExamples: a * 2 · sin(a * 30) * 0.5 · '
                       'if(a > 2 and a < 5; 1; 0) · sqrt(a^2 + b^2).\n“;” separates a function\'s values (a comma is '
                       'read as a decimal); to multiply, “*”.')
        guide = QLabel(text)
        guide.setWordWrap(True)
        guide.setProperty("role", "small")
        return guide

    def _suggested_list(self, node, input_, before: str, send) -> QWidget:
        """Names offered in a list where any other can also be written, filtering as it is typed: the installed
        fonts of a Text."""
        list_ = QComboBox()
        list_.setEditable(True)
        list_.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        list_.setMinimumContentsLength(8)
        list_.addItem("")
        try:
            names = suggestions(node, input_)
        except Exception:                          # noqa: BLE001 (without the list, it is still written by hand)
            names = []
        list_.addItems(names)
        list_.setCurrentText(before or "")
        list_.lineEdit().setPlaceholderText(tr(input_.help) or tr('empty'))
        list_.setToolTip(tr(input_.help) + "\n" + tr('Pick from the list or type.'))
        complete = list_.completer()
        if complete is not None:
            complete.setFilterMode(Qt.MatchFlag.MatchContains)
            complete.setCompletionMode(complete.CompletionMode.PopupCompletion)
        complete_inline(list_.lineEdit(), names, later=True)     # «in» proposes «Inter» in the field itself
        list_.activated.connect(lambda _: send(list_.currentText()))
        list_.lineEdit().editingFinished.connect(lambda: send(list_.currentText()))
        return list_

    def _editor_chart(self, node: Node) -> QWidget:
        """The graph to move its points, some starting shapes, and the user's own curves (saved, renamed by saving
        again with another name, deleted)."""
        from PySide6.QtWidgets import QMessageBox
        from ..geometry import CHARTS
        from .chart import EditorChart, delete_own_chart, own_charts, save_own_chart
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 4, 0, 4)
        row = QHBoxLayout()
        label = QLabel(tr('Start with'))
        label.setProperty("role", "secondary")
        row.addWidget(label)
        shapes = QComboBox()
        shapes.setToolTip(tr('A starting shape, or one of your own curves; then move its points'))
        row.addWidget(shapes, 1)
        save_button = QToolButton()
        save_button.setText(tr('Save'))
        save_button.setToolTip(tr('Keep this curve among your own, to use it in any project'))
        delete_button = QToolButton()
        delete_button.setText(tr('Delete'))
        delete_button.setToolTip(tr('Remove the chosen curve from your own'))
        row.addWidget(save_button)
        row.addWidget(delete_button)
        column.addLayout(row)

        def fill(selected: str | None = None) -> None:
            shapes.clear()
            shapes.addItem("—", None)
            for name in CHARTS:
                shapes.addItem(tr(name), "factory:" + name)
            own = own_charts()
            if own:
                shapes.insertSeparator(shapes.count())
                for name in own:
                    shapes.addItem(name, "own:" + name)
            if selected is not None:
                shapes.setCurrentIndex(max(shapes.findData("own:" + selected), 0))
            delete_button.setEnabled(selected is not None)

        def chosen() -> tuple[str, str] | None:
            """("factory" or "own", name) of the chosen item; None for «—»."""
            data = shapes.currentData()
            return tuple(data.split(":", 1)) if isinstance(data, str) else None

        def choose(_=None) -> None:
            data = chosen()
            delete_button.setEnabled(bool(data) and data[0] == "own")
            if not data:
                return
            curve = CHARTS.get(data[1]) if data[0] == "factory" else own_charts().get(data[1])
            if curve:
                editor.put(curve)

        def save() -> None:
            data = chosen()
            suggested = data[1] if data and data[0] == "own" else ""
            name, ok = ask_text(self, tr('Save curve'), tr('Name of the curve:'), text=suggested)
            name = name.strip()
            if not ok or not name:
                return
            if name in own_charts() and name != suggested and QMessageBox.question(
                    self, tr('Save curve'), tr('There is already a curve called “{name}”. Replace it?').format(
                        name=name)) != QMessageBox.StandardButton.Yes:
                return
            save_own_chart(name, editor.points)
            fill(name)

        def delete() -> None:
            data = chosen()
            if not data or data[0] != "own":
                return
            if QMessageBox.question(self, tr('Delete curve'), tr('Delete your curve “{name}”? The projects that '
                                                                 'use it keep their points.').format(name=data[1])
                                    ) != QMessageBox.StandardButton.Yes:
                return
            delete_own_chart(data[1])
            fill()

        points = node.inputs.get("points")
        editor = EditorChart(points if isinstance(points, (list, tuple)) and len(points) >= 2 else CHARTS["linear"],
                               bool(node.inputs.get("smooth", True)))
        editor.change.connect(lambda list_, final: self.change_value.emit(node.name, "points", list_, final))
        fill()
        shapes.activated.connect(choose)
        save_button.clicked.connect(save)
        delete_button.clicked.connect(delete)
        column.addWidget(editor)
        help = QLabel(tr('Drag the points · click: a new one · double-click: exact values · right click: remove it'))
        help.setProperty("role", "small")
        help.setWordWrap(True)
        column.addWidget(help)
        return box

    def _button_draw(self, node: Node, v, input_: str = "points") -> QWidget:
        """The tile to edit its points in the 3D view, with how many it has (the grid and the snapping, in the
        editor's bar)."""
        active = self.drawing == node.name
        tile = ActionTile("sketch", 'Finish editing' if active else 'Edit curve',
                          tr('Enter or Esc: finishes') if active else text_of(input_, v),
                          'The 3D view becomes the curve editor, with its tools, grid and snap in a bar on top '
                          '· Enter or Esc: finishes', active=active)
        tile.clicked.connect(lambda: self.draw.emit(node.name))
        return tile

    def _button_code(self, node: Node) -> QWidget:
        """The tile that opens the editor of the code, with what the check says of it now."""
        from ..code_check import check
        problem = check(node.inputs.get("code"))
        detail = (str(problem)[:1].upper() + str(problem)[1:]) if problem is not None else \
            tr('It opens beside the window · Ctrl+Enter applies it')
        tile = ActionTile("code", 'Edit code…', detail,
                          'Opens the editor of the code of this node: it stays open beside the window, and '
                          'Ctrl+Enter applies what is written')
        tile.clicked.connect(lambda: self.code.emit(node.name))
        return tiles([tile])

    def _layout_report(self, layout) -> QWidget:
        """Lay flat: how many sheets, how much of them the pieces take, and the pieces left without a number."""
        from ..values import text_length
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        if layout is None:
            column.addWidget(QLabel(tr('Connect the pieces to lay them flat.')))
            return box
        sheets = len(layout.boxes)
        size = f"{text_length(layout.sheet[0])} × {text_length(layout.sheet[1])}"
        title = QLabel((tr('{n} pieces on 1 sheet of {size}') if sheets == 1 else
                        tr('{n} pieces on {sheets} sheets of {size}')).format(n=layout.count, sheets=sheets,
                                                                             size=size))
        title.setProperty("role", "title")
        title.setWordWrap(True)
        column.addWidget(title)
        used = QLabel(tr('The pieces take {used} % of the sheets. File → Export → Cutting file writes one file per '
                         'sheet.').format(used=round(layout.used * 100)))
        used.setWordWrap(True)
        used.setProperty("role", "secondary")
        column.addWidget(used)
        if layout.unnumbered:
            says = QLabel(tr('Too small for their number: {pieces}.').format(pieces=", ".join(layout.unnumbered)))
            says.setWordWrap(True)
            says.setProperty("role", "secondary")
            column.addWidget(says)
        return box

    def _print_report(self, reports, printer: bool = False) -> QWidget:
        """Print check: ready to print, or what keeps each piece from it (and where, in red in the view)."""
        from ..values import text_length
        box = QFrame()
        box.setObjectName("print_report")
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        good, bad = theme.color("recomputed", "#7bd88f"), "#e0605a"
        if reports is None:
            says = QLabel(tr('It shows the printer’s volume around the piece. To check the piece, choose «problems» '
                             'or «ready».') if printer else tr('Connect a piece to check it.'))
            says.setWordWrap(True)
            column.addWidget(says)
            return box
        ready = sum(r.ready for r in reports)
        title = QLabel(tr('Ready to print.') if ready == len(reports) and reports else
                       tr('{ready} of {n} pieces ready to print.').format(ready=ready, n=len(reports)))
        title.setProperty("role", "title")
        title.setStyleSheet(f"color: {good if reports and ready == len(reports) else bad};")
        title.setWordWrap(True)
        column.addWidget(title)
        for r in reports[:30]:
            size = " × ".join(text_length(x) for x in r.size)
            head = (f"{'✔' if r.ready else '✖'}  {r.label + ' · ' if r.label else ''}{size}"
                    + (f" · {tr('thinnest wall')} {text_length(r.thinnest)}" if r.thinnest else ""))
            line = QLabel(head)
            line.setStyleSheet(f"color: {good if r.ready else bad};")
            line.setWordWrap(True)
            column.addWidget(line)
            for problem in r.problems + getattr(r, "notes", []):
                says = QLabel("·  " + problem[:1].upper() + problem[1:])
                says.setWordWrap(True)
                says.setProperty("role", "secondary")
                column.addWidget(says)
        if len(reports) > 30:
            more = QLabel(tr('(And {n} more pieces.)').format(n=len(reports) - 30))
            more.setProperty("role", "secondary")
            column.addWidget(more)
        return box

    def _button_play_moment(self, node: Node) -> QWidget:
        """▶: the moment of an Equilibrium (from the start to the rest) or of a Topology optimization (from the region
        full to the shape), from 0 to 1, to watch it on its way; while it plays, ⏸ pauses it and ■ stops it."""
        what, state = self.playing if self.playing else (None, None)
        state = state if what == ("input", node.name, "moment") else None
        wired = isinstance(node.inputs.get("moment"), Node)
        if node.kind.name == 'Topology optimization':
            title, going, still = ('Watch it take shape', tr('Taking shape…'),
                                   tr('From the region full to the shape, in {s} s').format(s=4))
            help_ = ('From the region full and thin to the shape, in a few seconds (its «moment» from 0 to 1). The '
                     'optimization is computed once: each frame only looks at one of its turns.')
        else:
            title, going, still = ('Watch it reach its rest', tr('Reaching its rest…'),
                                   tr('From the start to the rest, in {s} s').format(s=4))
            help_ = ('From the start to the rest, in a few seconds (its «moment» from 0 to 1). The shape is computed '
                     'once: each frame only looks at it on its way.')
        detail = {"playing": going, "paused": tr('Paused')}.get(state, still)
        tile = ActionTile("play", title, detail,
                          'The moment comes from another node: play that one (the ▶ of its slider).' if wired else
                          help_, active=state is not None, enabled=not wired)
        tile.clicked.connect(lambda: self.play.emit(node.name, "moment", 0.0, 1.0))
        if state is not None:
            pause = tile_button("pause" if state == "playing" else "play",
                                'Pause' if state == "playing" else 'Go on',
                                'Pause' if state == "playing" else 'Go on from here')
            pause.clicked.connect(lambda: self.play.emit(node.name, "moment", 0.0, 1.0))
            stop = tile_button("stop", 'Stop', 'Stop: back to the moment it had before playing')
            stop.clicked.connect(lambda: self.stop_play.emit(node.name, "moment"))
            tile.add_actions(pause, stop)
        return tile

    def _button_move_supports(self, node: Node) -> QWidget:
        """The tile to move the supports of an Equilibrium in the 3D view, and a button to let all those by hand go."""
        held = node.inputs.get("hand_supports")
        active = self.drawing == node.name
        tile = ActionTile("supports", 'Finish moving' if active else 'Move supports',
                          tr('Enter or Esc: finishes') if active else text_of("hand_supports", held) if held
                          else tr('Drag its particles in the view'),
                          'The 3D view shows its particles at rest, the supports as squares: drag any particle and '
                          'it is held where you let it go, and the shape settles again · right click: hold it '
                          'where it is, or let it go · Enter or Esc: finishes', active=active)
        tile.clicked.connect(lambda: self.draw.emit(node.name))
        if held and not isinstance(held, Node) and not active:
            back = button_icon("undo", 'Let go every support by hand')
            back.clicked.connect(lambda: self.change_value.emit(node.name, "hand_supports", [], True))
            tile.add_button(back)
        return tile

    def _button_edit_mesh(self, node: Node) -> QWidget:
        """The tile to move its vertices in the 3D view, with how many were moved, and a button to put them back."""
        moves = node.inputs.get("moves")
        active = self.drawing == node.name
        tile = ActionTile("meshes", 'Finish editing' if active else 'Edit vertices',
                          tr('Enter or Esc: finishes') if active else _moved_text(moves),
                          'The 3D view shows the vertices of the mesh: choose them and drag them (Alt: up or '
                          'down; right click: exact coordinates) · Enter or Esc: finishes', active=active)
        tile.clicked.connect(lambda: self.draw.emit(node.name))
        if moves and not isinstance(moves, Node) and not active:
            back = button_icon("undo", 'Put every vertex back where the mesh has it')
            back.clicked.connect(lambda: self.change_value.emit(node.name, "moves", [], True))
            tile.add_button(back)
        return tile

    def _field(self, node: Node, input_, v) -> QWidget:
        """The control to write a fixed value: switch (yes/no), list (options) or text."""
        before = text_of(input_.name, v, is_length(node, input_.name))

        def send(text: str) -> None:
            if text != before:
                self.change.emit(node.name, input_.name, text)

        if isinstance(input_.default, bool) or isinstance(v, bool):  # yes / no
            cell = Switch(tr("yes") if v else tr("no"), bool(v))
            cell.setToolTip(tr(input_.help))
            cell.toggled.connect(lambda yes: send("yes" if yes else "no"))
            return cell

        if input_.suggest is not None:             # names offered (the installed fonts), any other can be written
            return self._suggested_list(node, input_, before, send)

        # Few fixed and short options (plane, curve, shape): in view, in a pill.
        offered = options_of(node, input_)
        if (offered and not input_.levels_of and input_.default is not None
                and len(offered) <= 4 and sum(len(tr(o)) for o in offered) <= 24
                and before in offered):
            pill = Segmented([(o, o, None) for o in offered], before)
            pill.setToolTip(tr(input_.help))
            pill.change.connect(lambda value: send(value))
            return pill

        options = offered
        if input_.levels_of:  # the levels of the data that arrives through that input
            origin = node.inputs.get(input_.levels_of)
            if isinstance(origin, Node) and origin._value is not None:
                options = list(origin._value.levels)
        if options:
            list_ = QComboBox()
            list_.setEditable(True)  # something else can be written (a number in «position»)
            # It may get narrower than its longest option: a narrow panel does not overflow to the side.
            list_.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            list_.setMinimumContentsLength(8)
            if input_.default is None:
                list_.addItem("")    # empty: the default value («the last level», «all»)
            # In the language of the interface, also the levels the nodes set («row» → «fila»): as on the
            # wires. On choosing, the original is saved.
            list_.addItems([tr(o) for o in options])
            list_.setCurrentText(tr(before) if before in options else before)
            if input_.name in LEVEL_INPUTS:
                list_.lineEdit().setMaxLength(max(NAME_LIMIT, len(str(before or ""))))
            list_.setToolTip(tr(input_.help) + ("\n" + tr('Pick from the list or type.') if input_.help else ""))
            auto = automatic_level(node, input_.name) if input_.levels_of else None
            list_.lineEdit().setPlaceholderText(tr("auto: {level}").format(level=tr(auto)) if auto
                                                else (tr(input_.help) or tr('empty')))
            list_.activated.connect(lambda _: send(list_.currentText()))
            list_.lineEdit().editingFinished.connect(lambda: send(list_.currentText()))
            return list_

        field = QLineEdit(before)
        if input_.name in LEVEL_INPUTS:                 # the name of a level: a name, not a text
            field.setMaxLength(max(NAME_LIMIT, len(str(before or ""))))
        field.setPlaceholderText(tr(input_.help) or tr('empty'))
        field.setToolTip(tr(input_.help) or "")
        if isinstance(v, (int, float)) and not input_.file:   # a number: it can be typed for several at once
            self.several.add(field, input_.name)
            field.setToolTip((tr(input_.help) + "\n" if input_.help else "") +
                             tr('Drag up or down over other numbers to type one value for all of them.'))

            def typed() -> None:
                names = [n for _, n in self.several.group_fields()]
                if len(names) > 1 and input_.name in names:
                    self.several.let_go()
                    if field.isModified():           # only what was typed (leaving without typing changes nothing)
                        self.change_several.emit(node.name, names, field.text())
                else:
                    send(field.text())
            field.editingFinished.connect(typed)
        else:
            field.editingFinished.connect(lambda: send(field.text()))
        if input_.file:
            return self._file_field(node, field, send, input_.file)
        return field

    def _file_field(self, node: Node, field: QLineEdit, send, kind: str = "image") -> QWidget:
        """The file (an image, a weather file): a click on its name (or on the folder) opens the file browser to
        choose it; an image shows a small picture of it below. Inside the folder of the project, it is kept relative
        to it, so the project and its files can travel together."""
        from pathlib import Path
        from PySide6.QtCore import QEvent, QObject
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QLabel, QVBoxLayout
        from ..images import resolve, folder

        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(field, 1)
        image = kind == "image"
        choose = button_icon("open", 'Choose an image…' if image else 'Choose a weather file…')
        row.addWidget(choose)
        column.addLayout(row)
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignLeft)
        column.addWidget(preview)
        field.setReadOnly(True)
        field.setCursor(Qt.CursorShape.PointingHandCursor)
        field.setPlaceholderText(tr('Click to choose an image…') if image else tr('Click to choose a weather file…'))
        field.setToolTip(tr('Click to choose an image in the file browser.') if image else
                         tr('Click to choose a weather file (.epw, or its .zip) in the file browser.'))

        def path_now() -> Path | None:
            if not field.text().strip():
                return None
            with folder(node.graph.folder):
                return resolve(field.text())

        def show_preview() -> None:
            if not image:
                preview.hide()
                return
            path = path_now()
            picture = QPixmap(str(path)) if path is not None and path.exists() else QPixmap()
            if picture.isNull():
                preview.clear()
                preview.hide()
                return
            ratio = self.devicePixelRatioF()
            picture = picture.scaled(int(160 * ratio), int(90 * ratio), Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
            picture.setDevicePixelRatio(ratio)
            preview.setPixmap(picture)
            preview.setToolTip(str(path))
            preview.show()

        def pick() -> None:
            from .editor import choose_file
            chosen = choose_file(self, kind, node.graph.folder, field.text().strip() or None)
            if chosen is None:
                return
            field.setText(chosen)
            send(field.text())
            show_preview()

        class Clicks(QObject):
            """A click on the name opens the file browser."""
            def eventFilter(self, watched, event) -> bool:
                if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    pick()
                    return True
                return False

        clicks = Clicks(field)
        field.installEventFilter(clicks)
        field.editingFinished.connect(show_preview)
        choose.clicked.connect(pick)
        show_preview()
        return box


def _moved_text(moves) -> str:
    """How many vertices an Edit mesh has moved, in words."""
    return text_of("moves", moves if isinstance(moves, (list, tuple)) else [])


def _icon_gradient(stops) -> "QIcon":
    """A sample of the gradient, for the list."""
    from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
    shows = QPixmap(48, 14)
    shows.fill(QColor(0, 0, 0, 0))
    painter = QPainter(shows)
    gradient = QLinearGradient(0, 0, 48, 0)
    for i, c in enumerate(stops):
        gradient.setColorAt(i / max(len(stops) - 1, 1), QColor(c))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 1, 48, 12, 3, 3)
    painter.end()
    return QIcon(shows)
