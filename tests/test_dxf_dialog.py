"""The window of Export DXF: the isometric views among the cards, and the cut at a height only in plan."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])


def test_the_cut_is_offered_in_plan_and_given_only_when_it_is_on():
    from tensela.ui.dialogs import DialogDxf
    parent = QWidget()
    dialog = DialogDxf(parent, mode=1, view="plan", cut=True, cut_height=1.5)
    assert dialog.choice()[2:] == ("plan", True, 1.5)
    assert not dialog.cut.isHidden()
    dialog.cut_on.setChecked(False)
    assert dialog.choice()[4] is None and not dialog.cut_height.isEnabled()
    dialog.cut_on.setChecked(True)
    dialog.view.put("southwest isometric")
    dialog._by_mode()
    assert dialog.cut.isHidden() and dialog.choice()[2] == "southwest isometric" and dialog.choice()[4] is None
    dialog.mode.put(0)
    dialog._by_mode()
    assert dialog.choice()[2] is None and dialog.choice()[4] is None        # in 3D, neither view nor cut
    parent.deleteLater()


def test_the_views_are_cards_and_the_last_one_is_the_camera():
    from tensela.ui.dialogs import DialogDxf
    from tensela.connectors.dxf import VIEWS
    assert [v for v, _, _ in DialogDxf.VIEWS] == list(VIEWS) + ["camera"]
    assert set(DialogDxf.HELP_TEXTS_VIEW) == set(VIEWS) | {"camera"}


SCRIPT = r'''
import os, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from PySide6.QtCore import QSettings
from tensela.ui import window
from tensela.ui.dialogs import DialogDxf
out = Path(sys.argv[2])
w = window.Window(); w._continue_without_saving = lambda: True; w.show()
w.open_(sys.argv[1])
for _ in range(8):
    w.wait_computation(); app.processEvents()
objects = w.project.visible_objects(computed_only=True)
dialog = DialogDxf(w, mode=1, view="plan", cut=True, cut_height=21.2)
w._display_dialog(dialog)

def save_as(*_args, **_kwargs):          # as it happens: while «Save as» is open, the closed dialog is deleted
    dialog.close(); dialog.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return str(out), ""

window.QFileDialog.getSaveFileName = save_as
w._export_dxf(dialog, objects)
settings = QSettings()
assert out.exists(), "no DXF"
assert settings.value("dxf/cut", type=bool) and settings.value("dxf/cut_height", type=float) == 21.2
print("ok", flush=True)
os._exit(0)
'''


def test_the_cut_is_remembered_although_the_dialog_is_gone(tmp_path):
    """The dialog closes (and Qt deletes it) while «Save as» is open: the DXF is written and the height remembered
    all the same (test 176: it raised «Internal C++ object already deleted»)."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CACHE_HOME": str(tmp_path / "cache")}
    done = subprocess.run([sys.executable, "-c", SCRIPT, str(root / "src/tensela/templates/twisting-tower.tela"),
                           str(tmp_path / "plan.dxf")], env=env, capture_output=True, text=True, timeout=240)
    assert "ok" in done.stdout, done.stderr[-2000:]
