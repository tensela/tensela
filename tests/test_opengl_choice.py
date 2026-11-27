"""The OpenGL of the 3D view on Windows (ui/opengl_choice.py): the card's when the system gives OpenGL 3.2, Mesa
beside Python when it does not; outside Windows, nothing changes."""
import sys

import pytest

from tensela.ui import opengl_choice as O


def test_outside_windows_always_the_system(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert O.choose(probe=lambda: pytest.fail("it should not ask")) == "system"


@pytest.fixture
def windows(tmp_path, monkeypatch):
    """As on Windows, with a Mesa folder (or not) and nothing really loaded."""
    loaded = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(O, "mesa_folder", lambda: tmp_path / "mesa")
    monkeypatch.setattr(O, "load_mesa", lambda folder: loaded.append(folder))
    monkeypatch.delenv("TENSELA_OPENGL", raising=False)
    return tmp_path / "mesa", loaded


def test_with_a_card_mesa_is_not_loaded(windows):
    folder, loaded = windows
    folder.mkdir()
    (folder / "opengl32.dll").write_bytes(b"")
    assert O.choose(probe=lambda: True) == "system" and loaded == []


def test_without_opengl_3_2_mesa_is_loaded_and_the_choice_is_inherited(windows, monkeypatch):
    import os
    folder, loaded = windows
    folder.mkdir()
    (folder / "opengl32.dll").write_bytes(b"")
    assert O.choose(probe=lambda: False) == "software" and loaded == [folder]
    assert os.environ["TENSELA_OPENGL"] == "software"
    assert O.choose(probe=lambda: pytest.fail("it should not ask again")) == "software"


def test_without_mesa_beside_it_there_is_nothing_to_choose(windows):
    folder, loaded = windows
    assert O.choose(probe=lambda: pytest.fail("it should not ask")) == "system" and loaded == []


def test_the_probe_says_no_when_it_cannot_ask(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("no")
    monkeypatch.setattr(O.subprocess, "run", broken)
    assert O.system_is_enough() is False


def test_the_probe_itself_runs_to_the_end():
    """The probe draws its cube and answers, without breaking (a source freed at once broke it: then every computer
    seemed to have no OpenGL, or the one of Windows Server seemed good)."""
    import os
    import subprocess
    pytest.importorskip("vtkmodules")
    done = subprocess.run([sys.executable, "-I", "-c", O.PROBE], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "TENSELA_OPENGL": "system"})
    if sys.platform == "win32" and done.returncode != 0:
        return                                    # (Windows Server: its OpenGL breaks VTK, and that is a «no»)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.splitlines()[0] in ("yes", "no")


def test_the_complaints_of_the_probe_stay_inside():
    """On Windows VTK shows its errors in a window of its own: on a computer without a card the probe would open it
    («failed to get wglChoosePixelFormatARB») before Tensela, for an expected «no». Here they would go to the
    terminal: neither one nor the other."""
    import os
    import subprocess
    pytest.importorskip("vtkmodules")
    quiet = O.PROBE.split("import vtkmodules.vtkRenderingOpenGL2")[0]
    complaint = ("from vtkmodules.vtkIOXML import vtkXMLPolyDataReader\n"
                 "r = vtkXMLPolyDataReader(); r.SetFileName('no-such-file.vtp'); r.Update()\nprint('done')\n")
    done = subprocess.run([sys.executable, "-I", "-c", quiet + complaint], capture_output=True, text=True,
                          timeout=60, env=os.environ)
    assert done.stdout.strip() == "done"
    assert "vtk" not in done.stderr.lower(), done.stderr[-2000:]
