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
