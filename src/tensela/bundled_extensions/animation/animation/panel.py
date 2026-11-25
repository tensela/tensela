"""The panel Animation: which slider, from where to where, how many frames and how long, and how it is saved (GIF or
PNG images). A panel, not a window over Tensela: the 3D view stays in sight, to frame it before exporting."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QMessageBox, QProgressDialog, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from tensela.language import tr

from . import WIDTHS, capture, make_gif, save_pngs, sliders, values


class AnimationPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.found: list = []
        self.busy = False                                 # exporting: the sliders are not read again meanwhile
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        note = QLabel(tr('The 3D view as it is now (the same framing), at each value of the slider. Frame it, then '
                         'export.'))
        note.setWordWrap(True)
        note.setProperty("role", "secondary")
        layout.addWidget(note)
        self.missing = QLabel()                           # why it cannot export (no slider, nothing seen)
        self.missing.setWordWrap(True)
        layout.addWidget(self.missing)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.slider = QComboBox()
        self.slider.currentIndexChanged.connect(self._range)
        form.addRow(tr('Slider'), self.slider)
        self.start, self.end = QDoubleSpinBox(), QDoubleSpinBox()
        for box in (self.start, self.end):
            box.setRange(-1e9, 1e9)
            box.setDecimals(3)
        row = QHBoxLayout()
        row.addWidget(self.start, 1)
        row.addWidget(QLabel("→"))
        row.addWidget(self.end, 1)
        form.addRow(f"{tr('From')} / {tr('To')}", row)
        self.frames = QSpinBox()
        self.frames.setRange(2, 600)
        self.frames.setValue(48)
        form.addRow(tr('Frames'), self.frames)
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0.5, 120)
        self.seconds.setValue(4.0)
        self.seconds.setSingleStep(0.5)
        form.addRow(tr('Seconds'), self.seconds)
        self.back = QCheckBox(tr('Back and forth'))
        form.addRow("", self.back)
        self.width = QComboBox()
        self.width.addItem(tr('Like the view'), None)
        for w in WIDTHS:
            self.width.addItem(f"{w} px", w)
        self.width.setCurrentIndex(2)                      # 800 px: light enough for a GIF
        form.addRow(tr('Width'), self.width)
        self.background = QComboBox()
        self.background.addItem(tr('Like the view'), None)
        self.background.addItem(tr('White'), "white")
        form.addRow(tr('Background'), self.background)
        self.format = QComboBox()
        self.format.addItem(tr('GIF (one file)'), "gif")
        self.format.addItem(tr('PNG images (a folder)'), "png")
        form.addRow(tr('Format'), self.format)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.go = QPushButton(tr('Export…'))
        self.go.setDefault(True)                           # the accent: the main action of the panel
        self.go.clicked.connect(lambda: self.export())         # (clicked gives «checked»: it is not a file)
        buttons.addWidget(self.go)
        layout.addLayout(buttons)
        layout.addStretch(1)
        self.refresh()

    def refresh(self, *_) -> None:
        """The sliders of Values, again (one added or taken away, another project); the one chosen stays chosen."""
        if self.busy:
            return
        found = sliders(self.window) if self.window.project is not None else []
        names = [name for name, _, _ in found]
        if names == [name for name, _, _ in self.found]:
            self.found = found
            self._can()
            return
        chosen = self.slider.currentText()
        self.found = found
        self.slider.blockSignals(True)
        self.slider.clear()
        self.slider.addItems(names)
        self.slider.blockSignals(False)
        if names:
            self.slider.setCurrentIndex(names.index(chosen) if chosen in names else 0)
            self._range(self.slider.currentIndex())
        self._can()

    def _can(self) -> None:
        """Whether it can export, and if not, why (said in the panel, not in a window that stops everything)."""
        p = self.window.project
        why = (tr('There is no slider in Values: add one first (the slider button of an input, in the node\'s '
                  'panel).') if not self.found else
               tr('There is nothing seen in 3D: turn on the eye of a node.') if p is None or not p.export else "")
        self.missing.setText(why)
        self.missing.setVisible(bool(why))
        self.go.setEnabled(not why)

    def _range(self, k: int) -> None:
        if not 0 <= k < len(self.found):
            return
        name, control, index = self.found[k]
        for box in (self.start, self.end):              # a slider of whole steps, without decimals
            box.setDecimals(0 if float(control.step).is_integer() else 3)
        self.start.setValue(control.minimum)
        self.end.setValue(control.maximum)

    def choice(self) -> dict:
        name, control, index = self.found[self.slider.currentIndex()]
        return {"control": control, "index": index, "values": values(self.start.value(), self.end.value(),
                                                                     self.frames.value(), self.back.isChecked()),
                "seconds": self.seconds.value(), "width": self.width.currentData(),
                "background": self.background.currentData(), "format": self.format.currentData()}

    def export(self, target: str | None = None) -> Path | None:
        """Asks where (unless `target`), makes the frames and saves them. Where it was saved, or None."""
        self.refresh()
        if not self.go.isEnabled():
            return None
        c = self.choice()
        base = self.window.filepath.with_suffix("") if self.window.filepath else Path.home() / "animation"
        if target is None:
            if c["format"] == "gif":
                target, _ = QFileDialog.getSaveFileName(self, tr('Save the animation'), str(base) + ".gif",
                                                        tr('Animated GIF (*.gif)'))
            else:
                target = QFileDialog.getExistingDirectory(self, tr('A folder for the images'), str(base.parent))
        if not target:
            return None
        target = Path(target)
        if c["format"] == "gif" and target.suffix.lower() != ".gif":
            target = target.with_suffix(".gif")
        progress = QProgressDialog(tr('Making the animation…'), tr('Cancel'), 0, len(c["values"]), self.window)
        progress.setWindowTitle(tr('Animation'))
        progress.setWindowModality(Qt.WindowModality.WindowModal)   # while it records, the project is not touched
        progress.setMinimumDuration(0)

        def step(n: int, total: int) -> None:
            progress.setValue(n)
            progress.setLabelText(tr('Frame {n} of {total}').format(n=n, total=total))

        self.busy = True
        try:
            images, folder = capture(self.window, c["control"], c["index"], c["values"], c["background"],
                                     stop=progress.wasCanceled, step=step)
        finally:
            self.busy = False
        try:
            if images is None:
                self.window.statusBar().showMessage(tr('Animation stopped: nothing was saved.'), 8000)
                return None
            if c["format"] == "gif":
                make_gif(images, target, c["seconds"], c["width"])
            else:
                save_pngs(images, target, c["width"])
        except OSError as error:
            QMessageBox.warning(self, tr('Animation'), str(error))
            return None
        finally:
            progress.close()
            shutil.rmtree(folder, ignore_errors=True)
        self.window.statusBar().showMessage(tr('Animation saved: {path} ({n} frames)').format(
            path=target, n=len(images)), 10000)
        return target
