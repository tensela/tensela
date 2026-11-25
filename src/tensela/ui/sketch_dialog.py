"""The Croquis panel (D11, Delivery 5): the 3D view as a freehand sketch.

One more panel of the window (it moves, groups, goes to another screen): at the top the preview; below the style,
the paper, the hand and the shadows; and Save, in PNG, layered SVG (Inkscape, Affinity, Illustrator) or PDF. The
sketch draws what is seen, with the framing of the 3D view, and redraws itself when the view turns or the model
changes (the window gives it the scene: `put_scene`).

The preview is drawn in another thread: the window does not freeze meanwhile.
"""
from __future__ import annotations

import json

from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from .. import croquis
from ..croquis import export, paper, presets, texts
from .widgets import Switch, Segmented, Cards
from ..language import tr

WIDTH_PREVIEW = 720
WIDTHS = [(1600, "1600 px"), (2400, "2400 px (recomendado)"), (3600, "3600 px")]
KEY = "sketch/settings"


class _Drafter(QObject):
    """Draws a sketch in another thread and reports with the image (or the error)."""

    ask = Signal(int, object, object, int, object)
    ready = Signal(int, object)
    failure = Signal(int, str)

    def draw(self, turn: int, objects, camera, width: int, s: dict) -> None:
        try:
            layers = croquis.draw(objects, camera, width, s=s)
            self.ready.emit(turn, layers)
        except Exception as error:          # noqa: BLE001 (the user is told)
            self.failure.emit(turn, str(error))


THUMBNAILS = Path(croquis.__file__).resolve().parent / "thumbnails"


def _title(text: str) -> QLabel:
    e = QLabel(text)
    e.setProperty("role", "title")
    return e


def _secondary(text: str) -> QLabel:
    e = QLabel(text)
    e.setProperty("role", "secondary")
    return e


def _shows(rgb, density: float) -> QPixmap:
    """A paper sample: a rounded rectangle of its colour."""
    side = 22
    image = QPixmap(round(side * 1.6 * density), round(side * density))
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(0, 0, 0, 40))
    p.setBrush(QColor(*rgb))
    p.drawRoundedRect(QRectF(1, 1, image.width() - 2, image.height() - 2), 5 * density, 5 * density)
    p.end()
    image.setDevicePixelRatio(density)
    return image


class SketchPanel(QWidget):
    """The content of the Croquis panel (the window puts it in a DockablePanel)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.objects, self.camera = None, None
        self.name, self.folder = "sketch", ""
        self._turn = 0
        self._layers = None

        self.preview = QLabel(tr('Turn on “Show in 3D” on a node to draw it.'))
        self.preview.setObjectName("sketch_preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview.setMinimumSize(260, 180)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # The styles, with their thumbnail (tools/sketch_thumbnails.py); the papers, with their colour.
        self.style_name = Cards([(key, texts.tr(text), QPixmap(str(THUMBNAILS / f"{key}.png")))
                                for key, (text, _) in presets.PRESETS.items()], columns=3, side=56)
        self.paper = Cards([(key, texts.tr(text), _shows(color, self.devicePixelRatioF()))
                               for key, (text, color) in paper.PAPERS.items()], columns=4, side=22)
        self.hand = QSlider(Qt.Orientation.Horizontal)
        self.hand.setRange(0, 100)
        self.hand.setToolTip(tr('0: with a ruler, straight lines. 100: a loose hand, overshooting the corners.'))
        self.shadows = Switch(tr('Cast shadows'))
        self.width_image = Segmented([(value, f"{value} px", None) for value, _ in WIDTHS], 2400,
                                help_texts={2400: 'Recommended'})
        self.state = QLabel("")
        self.state.setProperty("role", "small")
        self.state.setWordWrap(True)

        settings = QVBoxLayout()
        settings.setSpacing(8)
        for title, control in (('Style', self.style_name), ("Papel", self.paper)):
            settings.addWidget(_title(tr(title)))
            settings.addWidget(control)
            settings.addSpacing(4)
        settings.addWidget(_title(tr('Hand')))
        row_hand = QHBoxLayout()
        for w in (_secondary(tr('ruler')), self.hand, _secondary(tr('loose'))):
            row_hand.addWidget(w, 1 if w is self.hand else 0)
        settings.addLayout(row_hand)
        settings.addWidget(self.shadows)
        settings.addSpacing(4)
        settings.addWidget(_title(tr('Width when saving')))
        settings.addWidget(self.width_image)
        settings.addWidget(self.state)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.save = QPushButton(tr('Save…'))
        self.save.setToolTip(tr('As PNG, layered SVG or PDF'))
        self.save.clicked.connect(self._save)
        buttons.addWidget(self.save)
        settings.addLayout(buttons)

        # The settings, in a scroll area: the panel can end up short.
        from PySide6.QtWidgets import QScrollArea
        box = QWidget()
        box.setLayout(settings)
        scrollable = QScrollArea()
        scrollable.setWidgetResizable(True)
        scrollable.setFrameShape(QScrollArea.Shape.NoFrame)
        scrollable.setWidget(box)
        all_ = QVBoxLayout(self)
        all_.setContentsMargins(0, 0, 0, 0)
        all_.setSpacing(10)
        all_.addWidget(self.preview, 2)
        all_.addWidget(scrollable, 3)

        self._load_settings()
        self._thread = QThread(self)
        self._drafter = _Drafter()
        self._drafter.moveToThread(self._thread)
        self._drafter.ask.connect(self._drafter.draw)
        self._drafter.ready.connect(self._preview_items)
        self._drafter.failure.connect(self._preview_failed)
        self._thread.start()

        self._wait = QTimer(self, singleShot=True, interval=250)   # do not draw at each step of the slider
        self._wait.timeout.connect(self._redraw)
        self.style_name.change.connect(lambda _: self._style_name_changed())
        for signal in (self.paper.change, self.hand.valueChanged, self.shadows.toggled):
            signal.connect(lambda *_: self._wait.start())
        for signal in (self.style_name.change, self.paper.change, self.hand.valueChanged, self.shadows.toggled,
                      self.width_image.change):
            signal.connect(lambda *_: self._save_settings())

    def put_graph_scene(self, objects, camera, name: str = "sketch", folder: str = "") -> None:
        """What is drawn: the visible objects and the camera of the 3D view (the preview is redone)."""
        self.objects, self.camera = objects, camera
        self.name, self.folder = name, folder
        self.save.setEnabled(bool(objects))
        if not objects:
            self._layers = None
            self.preview.setPixmap(QPixmap())
            self.preview.setText(tr('Turn on “Show in 3D” on a node to draw it.'))
            return
        self._wait.start()

    # --- Ajustes ---------------------------------------------------------------

    def settings(self) -> dict:
        s = dict(self._s)
        s.update(presets.PRESETS[self.style_name.value()][1])
        s.update(preset=self.style_name.value(), paper=self.paper.value(),
                 hand=self.hand.value(), shadows=self.shadows.isChecked())
        return presets.clean(s)

    def _load_settings(self) -> None:
        self._s = presets.clean(QSettings().value(KEY, "{}"))
        self.style_name.put(self._s["preset"])
        self.paper.put(self._s["paper"])
        self.hand.setValue(self._s["hand"])
        self.shadows.setChecked(self._s["shadows"])
        self.width_image.put(int(QSettings().value("sketch/width", 2400)))

    def _save_settings(self) -> None:
        QSettings().setValue(KEY, json.dumps(self.settings()))
        QSettings().setValue("sketch/width", self.width_image.value())

    def _style_name_changed(self) -> None:
        # Each style brings its shadows; the hand and the paper stay the user's.
        self.shadows.blockSignals(True)
        self.shadows.setChecked(presets.PRESETS[self.style_name.value()][1].get("shadows", True))
        self.shadows.blockSignals(False)
        self._wait.start()

    # --- Vista previa ----------------------------------------------------------

    def _redraw(self) -> None:
        if not self.objects or self.camera is None:
            return
        self._turn += 1
        self.state.setText(tr('Drawing the preview…'))
        self._drafter.ask.emit(self._turn, self.objects, self.camera, WIDTH_PREVIEW, self.settings())

    def _preview_items(self, turn: int, layers) -> None:
        if turn != self._turn:
            return                                   # it arrived late: another one was already asked for
        self._layers = layers
        image = QPixmap.fromImage(layers.image())
        self.preview.setPixmap(image.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
        self.state.setText("")

    def _preview_failed(self, turn: int, message: str) -> None:
        if turn == self._turn:
            self.state.setText(tr('Could not draw: {message}').format(message=message))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._layers is not None:
            self._preview_items(self._turn, self._layers)

    # --- Guardar ---------------------------------------------------------------

    def _save(self) -> None:
        if not self.objects:
            return
        name = f"{self.name} {tr('sketch')}.png"
        suggested = f"{self.folder}/{name}" if self.folder else name
        filepath, filter_ = QFileDialog.getSaveFileName(
            self, tr('Save the sketch'), suggested,
            tr('PNG image (*.png);;SVG in layers (*.svg);;PDF (*.pdf)'))
        if not filepath:
            return
        extension = {"SVG": ".svg", "PDF": ".pdf"}.get(filter_.split()[0], ".png")
        if not filepath.lower().endswith((".png", ".svg", ".pdf")):
            filepath += extension
        self.state.setText(tr('Drawing at full size…'))
        self.setCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            layers = croquis.draw(self.objects, self.camera, self.width_image.value(), s=self.settings())
            ok = export.save(layers, filepath)
        except Exception as error:                  # noqa: BLE001 (the user is told)
            ok, filepath = False, f"{filepath}\n{error}"
        finally:
            self.unsetCursor()
        if not ok:
            QMessageBox.warning(self, tr("Croquis"), tr('Could not save:') + f"\n{filepath}")
            self.state.setText("")
            return
        self._save_settings()
        self.state.setText(tr('Saved: {path}').format(path=filepath))

    def dismiss(self) -> None:
        """On closing the window: the drawing thread ends."""
        self._save_settings()
        self._thread.quit()
        self._thread.wait(30000)
