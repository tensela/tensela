"""Tensela in the applications menu from its AppImage (ui/desktop.py), and one window for all (ui/launch.py): a
second start hands its projects to the window that is open."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tensela.ui import desktop, launch

SRC = Path(__file__).resolve().parent.parent / "src"


def test_the_exec_line_quotes_the_path():
    assert desktop.quote("/home/ana/Tensela.AppImage") == '"/home/ana/Tensela.AppImage"'
    assert desktop.quote("/home/ana/my apps/T.AppImage") == '"/home/ana/my apps/T.AppImage"'
    assert desktop.quote('/a/b"c$d') == '"/a/b\\\\"c\\\\$d"'


#: The keys of the Desktop Entry Specification 1.3, which the validators of older systems know.
KNOWN_KEYS = {"Type", "Version", "Name", "GenericName", "NoDisplay", "Comment", "Icon", "Hidden", "OnlyShowIn",
              "NotShowIn", "DBusActivatable", "TryExec", "Exec", "Path", "Terminal", "Actions", "MimeType",
              "Categories", "Implements", "Keywords", "StartupNotify", "StartupWMClass", "URL"}


def test_the_launcher_has_only_keys_older_systems_know():
    keys = {line.split("=", 1)[0].split("[", 1)[0] for line in desktop.entry().splitlines() if "=" in line}
    assert keys and all(k in KNOWN_KEYS or k.startswith("X-") for k in keys), keys - KNOWN_KEYS


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    image = tmp_path / "apps" / "Tensela 0.1.AppImage"
    image.parent.mkdir()
    image.write_bytes(b"")
    monkeypatch.setenv("APPIMAGE", str(image))
    return tmp_path, image


def test_into_the_menu_and_out_again(home):
    tmp, image = home
    assert desktop.appimage() == image and desktop.installed_for() is None
    written = desktop.install(image)
    assert all(p.is_file() for p in written) and len(written) == len(desktop.files())
    text = desktop.entry_path().read_text(encoding="utf-8")
    assert f'Exec="{image}" %F' in text and "MimeType=application/x-tensela;" in text
    assert desktop.installed_for() == str(image)
    assert (tmp / "share" / "icons" / "hicolor" / "256x256" / "apps" / "tensela.png").is_file()
    assert "*.tela" in (tmp / "share" / "mime" / "packages" / "tensela.xml").read_text(encoding="utf-8")
    removed = desktop.uninstall()
    assert len(removed) == len(written) and not any(p.exists() for p in written)
    assert desktop.installed_for() is None


def test_the_portable_folder_goes_to_the_menu_too(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert desktop.appimage() is None or "TENSELA_PORTABLE" in __import__("os").environ
    launcher = tmp_path / "Tensela-0.9.0-x86_64" / "tensela"
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\n")
    monkeypatch.setenv("TENSELA_PORTABLE", str(launcher))
    assert desktop.appimage() == launcher
    desktop.install(launcher)
    assert f'Exec="{launcher}" %F' in desktop.entry_path().read_text(encoding="utf-8")


def test_the_launcher_follows_a_moved_appimage(home, monkeypatch):
    tmp, image = home
    desktop.install(image)
    assert not desktop.follow_move()                       # the same one: nothing to do
    newer = tmp / "apps" / "Tensela 0.2.AppImage"
    newer.write_bytes(b"")
    monkeypatch.setenv("APPIMAGE", str(newer))
    assert not desktop.follow_move()                       # the one of the menu is still there: it is left alone
    image.unlink()
    assert desktop.follow_move() and desktop.installed_for() == str(newer)


def test_without_an_open_window_nothing_is_handed_over(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert launch.hand_over(["/nowhere/a.tela"]) is False


def test_other_preferences_listen_somewhere_else(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "one"))
    one = launch.address()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "two"))
    assert launch.address() != one and launch.address().startswith(str(tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / ("long folder " * 10)))
    assert len(launch.address()) <= 100                    # too long for a socket: a short one in the temporary folder


@pytest.fixture
def short_temporary(monkeypatch):
    """A temporary folder with a short path (a socket's address has room for about 100 characters)."""
    import shutil
    import tempfile
    from pathlib import Path
    folder = Path(tempfile.mkdtemp(prefix="ts-", dir="/tmp"))
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    monkeypatch.setattr(launch, "_NOBODY_KNOWS", None)
    yield folder
    shutil.rmtree(folder, ignore_errors=True)


def test_without_a_folder_of_the_session_the_socket_goes_in_a_folder_only_of_this_person(tmp_path, monkeypatch,
                                                                                         short_temporary):
    """Without $XDG_RUNTIME_DIR, not loose in the shared temporary folder (another user could leave a socket there
    and receive what a second start hands over): in /tmp/tensela-<uid>, made with mode 700."""
    import os
    import stat
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    own = short_temporary / f"tensela-{os.getuid()}"
    assert launch.address().startswith(str(own) + "/")
    assert stat.S_IMODE(os.stat(own).st_mode) == 0o700


@pytest.mark.parametrize("spoiled", ["open to others", "a link"])
def test_a_folder_that_is_not_only_of_this_person_is_not_used(tmp_path, monkeypatch, spoiled, short_temporary):
    """If /tmp/tensela-<uid> was left by someone else (open to others, or a link elsewhere), it is not used: an address
    nobody knows (then a second start opens a window of its own), the same one along the process."""
    import os
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    own = short_temporary / f"tensela-{os.getuid()}"
    if spoiled == "a link":
        (short_temporary / "elsewhere").mkdir(mode=0o700)
        own.symlink_to(short_temporary / "elsewhere")
    else:
        own.mkdir()
        own.chmod(0o777)
    first = launch.address()
    assert not first.startswith(str(own)) and not first.startswith(str(short_temporary / "elsewhere"))
    assert launch.address() == first


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import desktop, window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()
assert w.listen_for_others()
w.offer_menu()
assert w.desktop_strip.isVisible()                          # from an AppImage not in the menu: it offers
assert w.put_in_menu(True) and desktop.installed_for() and not w.desktop_strip.isVisible()
print("listening", flush=True)

def look():
    if w.tabs.count() >= 1 and w.filepath is not None and w.filepath.name == "roof.tela":
        assert not w.put_in_menu(False) and desktop.installed_for() is None
        print("ok", flush=True)
        os._exit(0)
    QTimer.singleShot(100, look)

QTimer.singleShot(100, look)
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_a_second_start_opens_its_project_in_the_open_window(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    image = tmp_path / "Tensela.AppImage"
    image.write_bytes(b"")
    project = tmp_path / "roof.tela"
    project.write_bytes((SRC / "tensela" / "templates" / "hypar-roof.tela").read_bytes())
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"), "XDG_RUNTIME_DIR": str(tmp_path), "APPIMAGE": str(image),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(SRC)}
    script = tmp_path / "window.py"
    script.write_text(SCRIPT, encoding="utf-8")
    window = subprocess.Popen([sys.executable, str(script)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True)
    try:
        assert window.stdout.readline().strip() == "listening", window.stderr.read()[-3000:]
        for name in ("XDG_CONFIG_HOME", "XDG_RUNTIME_DIR"):
            monkeypatch.setenv(name, env[name])
        assert launch.hand_over([str(project)])
        out, err = window.communicate(timeout=60)
        assert "ok" in out, out[-2000:] + err[-3000:]
    finally:
        if window.poll() is None:
            window.kill()


def test_the_permission_to_come_forward_travels_with_the_projects(tmp_path, monkeypatch):
    """The activation token the desktop gave the second start goes to the open window (ui/activate.py), so that
    GNOME lets it come to the front instead of saying «Tensela is ready»."""
    import json
    import socket
    import threading
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_ACTIVATION_TOKEN", "token-123")
    monkeypatch.setenv("DESKTOP_STARTUP_ID", "token-123")
    got = {}
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(launch.address())
    server.listen(1)

    def answer():
        connection, _ = server.accept()
        data = b""
        while b"\n" not in data:
            data += connection.recv(4096)
        got.update(json.loads(data))
        connection.sendall(b"ok\n")
        connection.close()

    thread = threading.Thread(target=answer)
    thread.start()
    try:
        assert launch.hand_over(["/a/roof.tela"])
        thread.join(5)
    finally:
        server.close()
    assert got == {"files": ["/a/roof.tela"], "XDG_ACTIVATION_TOKEN": "token-123", "DESKTOP_STARTUP_ID": "token-123"}
