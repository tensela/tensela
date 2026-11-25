"""«Find the best…»: the sliders of Values move until a number reaches its minimum, its maximum or a value.

It stays open beside the window (it is not modal). Above, what is searched for: the number a node gives (a Length,
a Distance, an Area…) and whether its minimum, its maximum or a value is wanted. Below, which sliders it moves: those
that change that number, all marked to start with. «Search» works on a copy of the project, in a process of its own
(calculator.py), so the window keeps responding and a slow node or a failure does not touch it; each time it finds
something better, the sliders and the 3D view show it. «Stop» keeps the best found, at once. At the end, the best
values stay in the sliders, and one Ctrl + Z goes back to how they were. The list keeps the best ones found: a click
puts any of them back.
"""
from __future__ import annotations

import math
import threading
import time

from PySide6.QtCore import QObject, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .. import optimize as O
from ..data import ShapeError
from ..graph import Cancelled, Node
from ..language import tr
from ..project_file import from__text, numbers_items
from ..values import label_input, text_value
from . import theme
from .widgets import Segmented


def _upstream(graph, name: str) -> set[str]:
    """The nodes whose values reach `name` (and it itself)."""
    found, pending = set(), [name]
    while pending:
        n = pending.pop()
        if n in found or n not in graph.nodes:
            continue
        found.add(n)
        for v in graph.nodes[n].inputs.values():
            for item in (v if isinstance(v, (list, tuple)) else [v]):
                if isinstance(item, Node):
                    pending.append(item.name)
    return found


def numbers_of(graph) -> list[str]:
    """The nodes that give a single number from other nodes (what can be searched for)."""
    out = []
    for name, node in graph.nodes.items():
        value = getattr(node, "_value", None)
        if value is None or getattr(value, "kind", None) is not None:
            continue
        if not any(isinstance(v, Node) or (isinstance(v, (list, tuple)) and any(isinstance(i, Node) for i in v))
                   for v in node.inputs.values()):
            continue                                       # a fixed value is not something to search for
        try:
            O.single_number(value)
        except Exception:                                  # noqa: BLE001
            continue
        out.append(name)
    return out


def sliders_of(project, objective: str) -> list[tuple]:
    """The sliders that change `objective`: (control, index or None, its name, its value now)."""
    g = project.graph
    reach = _upstream(g, objective) if objective in g.nodes else set()
    out = []
    for c in project.controls:
        if c.node not in g.nodes or c.node not in reach:
            continue
        v = g.nodes[c.node].inputs.get(c.input_)
        items = numbers_items(v)
        name = c.label or (c.node if c.input_ == "value" else f"{c.node} · {tr(c.input_)}")
        if items is None:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append((c, None, name, float(v)))
        else:
            out.extend((c, i, f"{name} {i}", float(x)) for i, x in enumerate(items))
    return out


def values_of(project, objective: str) -> list[tuple[str, str, object]]:
    """The fixed numbers that reach `objective` and are not sliders yet: (node, input, value), in the project's
    order. What could move it, to offer them as sliders."""
    from ..project_file import slidable
    g = project.graph
    reach = _upstream(g, objective) if objective in g.nodes else set()
    taken = {c.key for c in project.controls}
    out = []
    for name in g.nodes:
        if name not in reach:
            continue
        node = g.nodes[name]
        for e in node.kind.inputs:
            v = node.inputs.get(e.name)
            if e.options or f"{name}.{e.name}" in taken or not slidable(v):
                continue
            out.append((name, e.name, v))
    return out


class _Progress(QWidget):
    """The best number found, attempt after attempt: how the search improves."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.points: list[tuple[int, float]] = []

    def put(self, points, total: int = 0, generations=()) -> None:
        self.points = [(a, n) for a, n in points if math.isfinite(n)]
        self.total = total
        self.averages = [(a, m) for a, b, m in generations if math.isfinite(m)]
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(6, 6, -6, -18)
        p.setPen(QPen(QColor(theme.color("border", "#2a2d36")), 1))
        p.drawRect(r)
        text = QColor(theme.color("text_2", "#9ca1b0"))
        if len(self.points) < 1:
            p.setPen(text)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, tr('The improvement shows here while it searches.'))
            return
        last = max([a for a, _ in self.points] + [getattr(self, "total", 0)]) or 1
        numbers = [n for _, n in self.points]
        averages = getattr(self, "averages", [])
        low, high = min(numbers + [m for _, m in averages]), max(numbers + [m for _, m in averages])
        span = (high - low) or 1.0
        to = lambda a, n: QPointF(r.left() + r.width() * a / last, r.bottom() - r.height() * (n - low) / span)
        if len(averages) > 1:                            # the average of each generation: how the population closes in
            faint = QColor(theme.color("text_2", "#9ca1b0"))
            faint.setAlpha(140)
            p.setPen(QPen(faint, 1, Qt.PenStyle.DashLine))
            for (a0, m0), (a1, m1) in zip(averages, averages[1:]):
                p.drawLine(to(a0, m0), to(a1, m1))
        pen = QPen(QColor(theme.color("accent", "#8a7dff")), 2)
        p.setPen(pen)
        before = None
        for a, n in self.points:                         # in steps: the best stays until something better comes
            here = to(a, n)
            if before is not None:
                p.drawLine(before, QPointF(here.x(), before.y()))
                p.drawLine(QPointF(here.x(), before.y()), here)
            before = here
        p.drawLine(before, QPointF(r.right(), before.y()))
        p.setPen(text)
        p.drawText(self.rect().adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                   tr('attempts: {n}').format(n=last))
        p.drawText(self.rect().adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                   text_value(round(numbers[-1], 6)))


class _Signals(QObject):
    progress = Signal(object)
    finished = Signal(object)


class SearchDialog(QDialog):
    """«Find the best…» of a window (it asks the window for the project and gives it the values found)."""

    def __init__(self, window, objective: str | None = None):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr('Find the best…'))
        self.setModal(False)
        self.resize(500, 780)
        self._thread = None
        self._stop = False
        self._last = None
        self._last_put = 0.0
        self._pieces: list[tuple] = []
        self.signals = _Signals()
        self.signals.progress.connect(self._on_progress)
        self.signals.finished.connect(self._on_finished)

        column = QVBoxLayout(self)
        column.setContentsMargins(14, 14, 14, 14)
        column.setSpacing(8)
        intro = QLabel(tr('It moves the marked sliders until the number you choose reaches its minimum, its maximum '
                          'or a value.'))
        intro.setWordWrap(True)
        intro.setProperty("role", "secondary")
        column.addWidget(intro)

        column.addWidget(self._title('What to look for'))
        self.objective = QComboBox()
        self.objective.setToolTip(tr('A node that gives a single number (a Length, a Distance, an Area, a Formula…)'))
        column.addWidget(self.objective)
        row = QHBoxLayout()
        self.goal = Segmented([(g, t, None) for g, t in (('minimum', 'its minimum'), ('maximum', 'its maximum'),
                                                         ('value', 'a value'))], 'minimum')
        row.addWidget(self.goal, 1)
        column.addLayout(row)
        # «a value»: a row of its own with the number to reach, written already with the one there is now.
        self.target_row = QWidget()
        row = QHBoxLayout(self.target_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr('Value to reach')))
        from .window import CellNumber                    # (the window imports this dialog)
        self.target = CellNumber()
        self.target.setRange(-1e12, 1e12)
        self.target.setDecimals(4)
        self.target.setToolTip(tr('The value it should reach: it looks for the one nearest to it'))
        self.target.setFixedWidth(140)
        self.target.setObjectName("search_target")
        row.addWidget(self.target)
        row.addStretch(1)
        column.addWidget(self.target_row)
        self.goal.change.connect(self._goal_changed)
        self.target_row.hide()

        column.addWidget(self._title('How'))
        self.method = Segmented([(m, t, None) for m, t in (('near', 'near'), ('wide', 'over the whole range'),
                                                           ('both', 'both ways'))], 'near')
        column.addWidget(self.method)
        self.how = QLabel()
        self.how.setWordWrap(True)
        self.how.setProperty("role", "secondary")
        column.addWidget(self.how)
        self.evolution = QWidget()
        row = QHBoxLayout(self.evolution)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr('Population')))
        self.population = QSpinBox()
        self.population.setRange(6, 500)
        self.population.setValue(30)
        self.population.setToolTip(tr('How many candidates each generation has: more, it explores more, but each '
                                      'generation takes longer'))
        row.addWidget(self.population)
        row.addSpacing(12)
        row.addWidget(QLabel(tr('Stop if it does not improve in')))
        self.patience = QSpinBox()
        self.patience.setRange(2, 1000)
        self.patience.setValue(25)
        self.patience.setSuffix(" " + tr('generations'))
        row.addWidget(self.patience)
        row.addStretch(1)
        column.addWidget(self.evolution)
        self.method.change.connect(self._show_how)
        self._show_how('near')

        column.addWidget(self._title('Moving'))
        self.sliders = QListWidget()
        self.sliders.itemChanged.connect(lambda _: self._can_start())    # a mark: Search on or off
        self.sliders.setToolTip(tr('The sliders of Values that change that number. Unmark those it should not move.'))
        column.addWidget(self.sliders, 1)
        self.offer = QPushButton(tr('Show the marked ones as sliders'))
        self.offer.setToolTip(tr('They go to Values with a range around their value (its range and step, with a '
                                 'right click on the slider), and the search can move them.'))
        self.offer.clicked.connect(self._make_sliders)
        self.offer.hide()
        column.addWidget(self.offer)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr('Stop after')))
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 3600)
        self.seconds.setValue(30)
        self.seconds.setSuffix(" s")
        row.addWidget(self.seconds)
        row.addStretch(1)
        self.start = QPushButton(tr('Search'))
        self.start.setDefault(True)
        self.start.setMinimumHeight(32)
        self.start.clicked.connect(self._start_or_stop)
        row.addWidget(self.start)
        column.addLayout(row)

        self.status = QLabel()
        self.status.setWordWrap(True)
        column.addWidget(self.status)
        self.progress = _Progress()
        column.addWidget(self.progress)
        column.addWidget(self._title('The best found (a click puts it back)'))
        self.found = QListWidget()
        self.found.itemClicked.connect(self._put_back)
        column.addWidget(self.found, 1)
        close = QPushButton(tr('Close'))
        close.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        column.addLayout(bottom)

        self.objective.currentIndexChanged.connect(lambda _: self._fill_sliders())
        self.fill(objective)

    def _show_how(self, method: str) -> None:
        self.how.setText(tr({
            'near': 'From where the sliders are, it refines step by step. Fast; with several valleys, it stays in '
                    'the one where it starts.',
            'wide': 'A population of candidates over the whole range: the best cross and mutate, generation after '
                    'generation (an evolutionary search). Slower, but it does not stay in the nearest valley.',
            'both': 'First over the whole range, then it refines the best one step by step: for hard problems.',
        }[method]))
        self.evolution.setVisible(method != 'near')

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(tr(text))
        label.setProperty("role", "tile_title")
        return label

    # --- What can be searched, and with what ----------------------------------------------------

    def _goal_changed(self, goal: str) -> None:
        self.target_row.setVisible(goal == 'value')
        if goal == 'value':
            name = self.objective.currentData()
            if name and self.target.value() == 0:
                value = O.single_number(self.window.project.graph.nodes[name]._value)
                if math.isfinite(value):
                    self.target.setValue(round(value, 4))
            self.target.setFocus()
            self.target.selectAll()

    def fill(self, objective: str | None = None) -> None:
        """The numbers of the project (again: after a change in the graph), keeping the chosen one if it is there."""
        before = objective or self.objective.currentData()
        names = numbers_of(self.window.project.graph)
        self.objective.blockSignals(True)
        self.objective.clear()
        for name in names:
            value = O.single_number(self.window.project.graph.nodes[name]._value)
            self.objective.addItem(f"{name}  ({text_value(round(value, 6))})", name)
        if before in names:
            self.objective.setCurrentIndex(names.index(before))
        self.objective.blockSignals(False)
        if not names:
            self.status.setText(tr('There is no number to look for: measure something first (Length, Area, '
                                   'Distance…), from nodes that depend on a slider.'))
            self._warned = True
        self._fill_sliders()

    def _fill_sliders(self) -> None:
        unmarked = {(c.key, i) for k, (c, i, name, value) in enumerate(self._pieces)
                    if k < self.sliders.count() and self.sliders.item(k).checkState() != Qt.CheckState.Checked}
        self.sliders.clear()
        objective = self.objective.currentData()
        self._pieces = sliders_of(self.window.project, objective) if objective else []
        for c, i, name, value in self._pieces:
            item = QListWidgetItem(tr('{name}: {value} (from {low} to {high})').format(
                name=name, value=text_value(value), low=text_value(c.minimum), high=text_value(c.maximum)))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if (c.key, i) in unmarked else Qt.CheckState.Checked)
            self.sliders.addItem(item)
        self._offered = values_of(self.window.project, objective) if objective and not self._pieces else []
        for node, input_, value in self._offered:     # what could move it: to mark and show as sliders
            item = QListWidgetItem(tr('{node} · {input}: {value}').format(
                node=node, input=label_input(input_), value=text_value(value) if isinstance(value, (int, float))
                else value))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.sliders.addItem(item)
        self.offer.setVisible(bool(self._offered))
        if objective and not self._pieces:
            self.status.setText(tr('No slider of Values changes «{node}». Mark below the values it depends on that '
                                   'should move, and show them as sliders.').format(node=objective)
                                if self._offered else
                                tr('No slider of Values changes «{node}», and it depends on no fixed number.').format(
                                    node=objective))
            self._warned = True
        elif objective and getattr(self, "_warned", False):     # (what the last search said stays)
            self.status.setText("")
            self._warned = False
        self._can_start()

    def _can_start(self) -> None:
        """Search, only with some slider marked to move (Stop, always while it searches)."""
        self.start.setEnabled(self._thread is not None or bool(self._chosen()))

    def _make_sliders(self) -> None:
        """The marked values, as sliders of Values (one step to undo); then the search can move them."""
        from ..project_file import control_for
        marked = [(node, input_) for k, (node, input_, _) in enumerate(self._offered)
                  if self.sliders.item(k).checkState() == Qt.CheckState.Checked]
        if not marked:
            self.status.setText(tr('Mark at least one value.'))
            return
        w = self.window
        for node, input_ in marked:
            w.project.controls.append(control_for(w.project.graph, node, input_))
        w._create_controls()
        w._register()
        self._fill_sliders()
        self.status.setText(tr('{n} new slider(s) in Values: the search can move them.').format(n=len(marked)))
        self._warned = True

    def _chosen(self) -> list[tuple]:
        return [piece for k, piece in enumerate(self._pieces)
                if k < self.sliders.count() and self.sliders.item(k).checkState() == Qt.CheckState.Checked]

    # --- Searching ------------------------------------------------------------------------------

    #: After «Stop», how long the process may take to answer with the best found before it is closed (it may be in
    #: the middle of a long node): the best found so far is kept.
    STOP_SECONDS = 1.0

    def _start_or_stop(self) -> None:
        if self._thread is not None:
            self._stop = True
            self.status.setText(tr('Stopping… it keeps the best found.'))
            worker = self._thread
            if not isinstance(worker, threading.Thread):     # the process: asked, and closed if it does not answer
                worker.send({"op": "stop"})
                QTimer.singleShot(int(self.STOP_SECONDS * 1000), lambda: self._cut(worker, 'stopped'))
            return
        objective, chosen = self.objective.currentData(), self._chosen()
        if not objective:
            return
        if not chosen:
            self.status.setText(tr('Mark at least one slider to move.'))
            return
        goal, target, seconds = self.goal.value(), self.target.value(), float(self.seconds.value())
        method, population, patience = self.method.value(), self.population.value(), self.patience.value()
        self._searching = chosen
        self._stop, self._last, self._last_put = False, None, 0.0
        self.found.clear()
        self.progress.put([])
        self.start.setText(tr('Stop'))
        self.status.setText(tr('Searching…'))
        for w in self._settings():
            w.setEnabled(False)
        if self._search_apart(objective, chosen, goal, target, seconds, method, population, patience):
            return
        copy = from__text(self.window._snapshot()).graph           # it searches on a copy: the window goes on
        copy.folder = self.window.project.graph.folder
        variables = [O.Variable(value, c.minimum, c.maximum, c.step) for c, i, name, value in chosen]

        def evaluate(x: list[float]) -> float:
            for (c, i, name, value), v in zip(chosen, x):
                O.put_value(copy, c.node, c.input_, v, i, float(c.step).is_integer())
            return O.single_number(copy.value(objective))

        def work() -> None:
            window = self.window
            window._thread_started("search")
            try:
                result = O.search(evaluate, variables, goal, target, method, seconds, stop=lambda: self._stop,
                                  report=self.signals.progress.emit, population=population, patience=patience)
            except Cancelled:
                result = self._last
                if result is not None:
                    result.end = 'stopped'
            except Exception as e:                          # noqa: BLE001 (said in the dialog, not lost)
                result = e
            finally:
                window._thread_ended("search")
            self.signals.finished.emit(result)

        self._thread = threading.Thread(target=work, daemon=True, name="find the best")
        self._thread.start()

    def _search_apart(self, objective: str, chosen: list, goal: str, target: float, seconds: float, method: str,
                      population: int, patience: int) -> bool:
        """The search in a process of its own. False if it cannot start (then it searches in a thread, as before)."""
        window = self.window
        if not window.use_calculator:
            return False
        from .. import language
        from ..calculator import _Worker, graph_message
        g = window.project.graph
        message = {"op": "search", "graph": graph_message(g), "folder": str(g.folder) if g.folder else None,
                   "language": language.LANGUAGE, "objective": objective,
                   # what the window already has of what reaches the number: not computed again
                   "seed": {n: g.nodes[n]._value for n in _upstream(g, objective) if g.nodes[n]._value is not None},
                   "chosen": [(c.node, c.input_, i, float(c.step).is_integer()) for c, i, name, value in chosen],
                   "variables": [(value, c.minimum, c.maximum, c.step) for c, i, name, value in chosen],
                   "goal": goal, "target": target, "method": method, "seconds": seconds,
                   "population": population, "patience": patience}
        try:
            worker = _Worker(self._from_apart)
        except OSError:
            return False
        self._thread = worker
        worker.send(message)
        return True

    def _from_apart(self, worker, message) -> None:
        """(In the thread that reads the process.) What it found, to the dialog's thread."""
        if worker is not self._thread:
            return
        if message is None:                                 # it ended by itself (the memory, a library that fails)
            self.signals.finished.emit(self._kept('closed'))
        elif message.get("op") == "progress":
            self.signals.progress.emit(message["result"])
        elif message.get("op") == "found":
            self.signals.finished.emit(message["result"] or self._kept('stopped'))
        elif message.get("op") == "failed":
            self.signals.finished.emit(ShapeError(message["error"]))

    def _kept(self, end: str):
        """The best found so far, as the end of the search."""
        result = self._last
        if result is not None:
            result.end = end
        return result if result is not None or end != 'closed' else ShapeError(
            tr('The calculation closed unexpectedly before finding anything: it may have needed more memory than '
               'there is, or a library failed. The window goes on.'))

    def _cut(self, worker, end: str) -> None:
        """The process did not answer «Stop» in time (it is in a long node): closed, with the best found so far."""
        if worker is self._thread:
            self._thread = None
            worker.kill()
            self._on_finished(self._kept(end))

    def _settings(self) -> tuple:
        return (self.objective, self.goal, self.target, self.method, self.evolution, self.sliders, self.seconds)

    def _values(self, result) -> list[tuple]:
        return [(c, i, v) for (c, i, name, value), v in zip(self._searching, result.values)]

    def _on_progress(self, result) -> None:
        self._last = result
        self.progress.put(result.history, result.attempts, result.generations)
        self.status.setText(tr('Searching… best so far: {number} (attempt {n})').format(
            number=text_value(round(result.number, 6)), n=result.attempts))
        now = time.monotonic()
        if now - self._last_put > 0.3 and self.window._in_progress is None:   # the view follows, without piling up
            self._last_put = now
            self.window.put_found(self._values(result), final=False)

    def _on_finished(self, result) -> None:
        worker, self._thread = self._thread, None
        if worker is not None and not isinstance(worker, threading.Thread):
            worker.kill()                                   # (its work is done)
        self.start.setText(tr('Search'))
        for w in self._settings():
            w.setEnabled(True)
        if isinstance(result, Exception):
            self.status.setText(str(result))
            return
        if result is None:
            self.status.setText(tr('Stopped before finding anything.'))
            return
        self.progress.put(result.history, result.attempts, result.generations)
        self.window.put_found(self._values(result), final=True)
        ends = {'found': 'Found: it cannot improve by moving the sliders one step.',
                'settled': 'It no longer improves: many generations without finding anything better.',
                'time': 'The time ran out: this is the best found.',
                'attempts': 'Too many attempts: this is the best found.',
                'stopped': 'Stopped: this is the best found.',
                'closed': 'The calculation closed unexpectedly (it may have needed more memory than there is): this '
                          'is the best found.'}
        said = tr(ends.get(result.end, ends['found']))
        if not math.isfinite(result.score):
            said = tr('Every attempt failed: look at the warning of the node.')
        failed = (" " + tr('({n} attempts failed and were left out.)').format(n=result.failed)) if result.failed \
            else ""
        self.status.setText(tr('{said} {number}, in {n} attempts and {s} s.').format(
            said=said, number=text_value(round(result.number, 6)), n=result.attempts,
            s=text_value(round(result.seconds, 1))) + failed)
        names = [name for c, i, name, value in self._searching]
        for number, values in result.best:
            text = f"{text_value(round(number, 6))}  ·  " + ", ".join(
                f"{name} = {text_value(v)}" for name, v in zip(names, values))
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, values)
            self.found.addItem(item)
        self.fill(self.objective.currentData())

    def _put_back(self, item: QListWidgetItem) -> None:
        values = item.data(Qt.ItemDataRole.UserRole)
        if values and self._thread is None:
            self.window.put_found([(c, i, v) for (c, i, name, value), v in zip(self._searching, values)],
                                  final=True)
            self._fill_sliders()

    def closeEvent(self, event) -> None:
        self._stop = True                                   # closing stops the search (it keeps the best found)
        worker = self._thread
        if worker is not None and not isinstance(worker, threading.Thread):
            worker.send({"op": "stop"})
            QTimer.singleShot(int(self.STOP_SECONDS * 1000), lambda: self._cut(worker, 'stopped'))
        super().closeEvent(event)
