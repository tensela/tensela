"""Smoke test of the interface (Delivery 1, D9).

    .venv/bin/python -m tensela.ui.smoke_test

Opens a window with a spinning cube. If the cube is seen and spins, the window (PySide6) and the 3D view (VTK) work
on this computer. Below it says with which window system and which graphics card.

Options for the diagnosis:
    --seconds N       close by itself after N seconds
    --capture PATH    save an image of the 3D view before closing
"""

from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
import vtk

from ..geometry import box
from ..language import tr
from .viewer import Viewer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tensela.ui.smoke_test", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", "--segundos", dest="seconds", type=float, default=0)
    parser.add_argument("--capture", "--captura", dest="capture")
    args = parser.parse_args(argv)

    # Internal Qt messages on Wayland that do not mean any problem.
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.textinput=false")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = QMainWindow()
    window.setWindowTitle(tr("Tensela: 3D view test"))
    window.resize(800, 600)

    central = QWidget()
    layout = QVBoxLayout(central)
    viewer = Viewer()
    viewer.display("cube", box(1, 1, 1, name="cube"), color="#6b8e4e")
    viewer.frame()
    layout.addWidget(viewer, stretch=1)

    info = QLabel()
    info.setWordWrap(True)
    layout.addWidget(info)
    window.setCentralWidget(central)
    window.show()

    def describe():
        render = viewer.view.ren_win
        graphics = render.ReportCapabilities().splitlines()[1].split(':', 1)[-1].strip() if render.ReportCapabilities() else '?'
        info.setText(tr("If the green cube spins, the 3D view works on this computer.  ·  "
                        "Window system: {windows}  ·  VTK {vtk}  ·  Graphics: {graphics}").format(
            windows=QGuiApplication.platformName(), vtk=vtk.vtkVersion.GetVTKVersion(), graphics=graphics))
        print(info.text(), flush=True)

    QTimer.singleShot(300, describe)

    rotation = QTimer()
    rotation.timeout.connect(lambda: viewer.rotate_camera(2))
    rotation.start(30)

    if args.seconds:
        def finish():
            if args.capture:
                viewer.capture(args.capture)
                print(f"Captura: {args.capture}", flush=True)
            rotation.stop()
            viewer.dismiss()
            window.close()
            app.quit()

        QTimer.singleShot(int(args.seconds * 1000), finish)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
