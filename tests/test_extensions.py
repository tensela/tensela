"""Extensions (extensions.py): their card, installing from a .zip, turning them on and off, the nodes they bring
(also in the process that computes) and projects with nodes of an extension that is not here."""
import os
import queue
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tensela import extensions as E
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import Project, from__text, to_text

HERE = Path(__file__).resolve().parent
SPIRAL = HERE / "data" / "extension-spiral"
SRC = HERE.parent / "src"


def zipped(folder: Path, target: Path, top: str = "spiral", extra: dict | None = None) -> Path:
    with zipfile.ZipFile(target, "w") as z:
        for f in folder.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f"{top}/{f.relative_to(folder)}" if top else str(f.relative_to(folder)))
        for name, text in (extra or {}).items():
            z.writestr(name, text)
    return target


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    yield tmp_path
    for ext_id in list(E.LOADED):
        E.unload(ext_id)


def test_a_card_says_what_is_wrong(monkeypatch):
    from tensela import language
    monkeypatch.setattr(language, "LANGUAGE", "en")
    assert E.card({"id": "Bad Id"}).problem
    assert "network" in E.PERMISSIONS and "permissions" in E.card({"id": "ok", "permissions": ["camera"]}).problem
    assert "99" in E.card({"id": "ok", "tensela": "99.0"}).problem
    good = E.card({"id": "ok", "name": "Ok", "es": {"name": "Bien"}, "website": "https://example.org",
                   "issues": "javascript:alert(1)", "permissions": {"network": "to read the weather"}})
    assert not good.problem and good.said("name") in ("Ok", "Bien")
    assert good.website == "https://example.org" and good.issues == ""      # only real addresses
    assert good.why("network") == "to read the weather"
    assert E.card({"id": "ok", "permissions": ["files"]}).permissions == {"files": ""}


def test_install_turn_on_and_off_and_remove(home):
    archive = zipped(SPIRAL, home / "spiral.zip", extra={"spiral/../../evil.txt": "no", "/etc/evil": "no"})
    ext, _ = E.look_inside(archive)
    assert ext.id == "spiral" and ext.version == "1.1.0" and ext.permissions == {}
    installed = E.install(archive)
    assert installed.path == E.folder() / "spiral" and not installed.problem
    assert not (home / "evil.txt").exists() and not any(p.name == "evil.txt" for p in home.rglob("*"))
    assert [e.id for e in E.available() if not e.bundled] == ["spiral"]
    from tensela.nodes import CATALOG
    from tensela.translations import es
    E.load(installed)
    assert CATALOG["Spiral"].extension == "spiral" and es.TEXTS["Spiral"] == "Espiral"
    assert [a.label for a in E.actions()] == ["Say hello"]
    g = Graph()
    g.node("Spiral", "s", turns=2)
    assert g.value("s").kind is not None
    E.unload("spiral")
    assert "Spiral" not in CATALOG and "Spiral" not in es.TEXTS and not E.actions()
    E.uninstall(installed)
    assert not (E.folder() / "spiral").exists()


def test_a_zip_that_is_not_an_extension_is_refused(home):
    with zipfile.ZipFile(home / "nothing.zip", "w") as z:
        z.writestr("readme.txt", "hello")
    with pytest.raises(ShapeError):
        E.install(home / "nothing.zip")


def test_a_project_keeps_the_nodes_of_an_extension_that_is_not_here(home):
    E.load(E.install(zipped(SPIRAL, home / "spiral.zip")))
    g = Graph()
    g.node("Number", "n", value=4)
    g.node("Spiral", "s", turns=g.nodes["n"], radius=3)
    text = to_text(Project(g, ["s"]))
    assert '"extension": "spiral"' in text
    E.unload("spiral")
    p = from__text(text)                                     # it opens: the node is kept, marked
    node = p.graph.nodes["s"]
    assert node.kind.extension == "spiral" and node.inputs["turns"] is p.graph.nodes["n"]
    with pytest.raises(ShapeError, match="spiral"):
        p.graph.value("s")
    again = to_text(p)                                       # saved as it was
    assert '"type": "Spiral"' in again and '"extension": "spiral"' in again and '"radius": 3' in again
    E.load_these(["spiral"])
    assert from__text(again).graph.value("s").kind is not None   # with it here again, it computes


def test_its_nodes_compute_in_the_process_that_computes(home, monkeypatch):
    from tensela import calculator as C
    E.install(zipped(SPIRAL, home / "spiral.zip"))
    E.load_these(["spiral"])
    monkeypatch.setenv(E.ENVIRONMENT, E.for_the_calculator())
    replies = queue.Queue()
    calc = C.Calculator(lambda r: r.get("op") != "at" and replies.put(r))
    try:
        g = Graph()
        g.node("Spiral", "s", turns=2)
        calc.send(C.request(g, 1, 1, None, "en"))
        reply = replies.get(timeout=60)
        assert not reply["errors"] and reply["values"]["s"].kind is not None
    finally:
        calc.close()


WINDOW = r'''
import os, sys, time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela import extensions as E
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 1000); w.show()

def every(menu):
    # The entries of a menu, also those of its submenus (one per extension)...
    out = []
    for a in menu.actions():
        out.append(a)
        if a.menu() is not None:
            out += every(a.menu())
    return out

def settle():
    for _ in range(5):
        w.wait_computation(); app.processEvents(); time.sleep(0.02)

def run():
    # A project with a Spiral, opened while the extension is not installed: the node is there, marked.
    w.open_(sys.argv[1]); settle()
    assert w.project.graph.nodes["s"].kind.extension == "spiral"
    assert w.editor.boxes["s"].with_error, "the node of the missing extension is not marked"
    labels = [a.text() for a in every(w._menu_extensions)]
    assert labels[0].replace("&", "") == "Manage extensions…" and len(labels) == 1
    # Installed from the dialog (its question answered «Install»): on at once; the project computes it.
    from PySide6.QtWidgets import QDialog
    w.manage_extensions(); app.processEvents()
    asked = []
    w._extensions_dialog._ask = lambda ext, replaces: asked.append(ext.id) or QDialog.DialogCode.Accepted
    w._extensions_dialog.install(sys.argv[2]); settle()
    assert asked == ["spiral"]
    assert "spiral" in w.extensions_on() and os.environ[E.ENVIRONMENT] == "spiral"
    assert not w.editor.boxes["s"].with_error and w.project.graph.nodes["s"]._value is not None
    assert any(a.text() == "Say hello" for a in every(w._menu_extensions))
    next(a for a in every(w._menu_extensions) if a.text() == "Say hello").trigger()
    assert "Hello" in w.statusBar().currentMessage()
    # Its icon: on its node card (and in its menu entries), drawn from the SVG of its folder.
    from tensela.ui import icons
    assert icons.of_kind("Spiral", "Curves") == "spiral.spiral" and "spiral.spiral" in E.ICONS
    assert "<path" in icons.svg("spiral.spiral", "#000")
    hello = next(a for a in every(w._menu_extensions) if a.text() == "Say hello")
    assert not hello.icon().isNull()
    # Its entry in the right-click menu of a node.
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    w._menu_canvas_and_extensions(menu, "s")
    entry = next(a for a in menu.actions() if a.text() == "What is this node?")
    entry.trigger()
    assert "«s» is a Spiral" in w.statusBar().currentMessage(), w.statusBar().currentMessage()
    menu = QMenu()
    w._menu_canvas_and_extensions(menu, None)                 # not on the background: it asked for nodes only
    assert not any(a.text() == "What is this node?" for a in menu.actions())
    # Its panel: closed until it is opened (Extensions menu), beside Values; it hears what happens.
    toggle = next(a for a in every(w._menu_extensions) if a.text() == "Panel: Spiral")
    assert toggle.isCheckable() and not toggle.isChecked()
    dock = w._extension_panels[("spiral", "Spiral")]
    assert not dock.built
    toggle.trigger(); app.processEvents()
    assert dock.isVisible() and dock.built and w.panels["values"] in w.tabifiedDockWidgets(dock)
    assert toggle.icon().isNull()                    # (an icon would hide the check: open or closed)
    # Taken out to a separate window: a utility window of Tensela, above it (not left behind on clicking Tensela).
    from PySide6.QtCore import Qt
    dock.take_out(); app.processEvents()
    out = dock._window if dock._window is not None else dock
    assert out.windowType() == Qt.WindowType.Tool and out.parentWidget() is not None, out.windowFlags()
    dock.return_(); app.processEvents()
    label = w.show_extension_panel("Spiral")
    import re
    times = lambda: int(re.search(r"Computed (\d+) times", label.text()).group(1))
    w.recompute(); settle()
    before = times()
    w.recompute(); settle()
    assert times() == before + 1, label.text()
    w._display_node("s")
    assert "Node chosen: s" in label.text(), label.text()
    # The window of extensions: search, what to show, order, the compact view.
    d = w._extensions_dialog
    d.search.setText("spír"); app.processEvents()             # without minding accents
    assert [e.id for e in d.listed()] == ["spiral"]
    d.search.setText("nothing like this"); app.processEvents()
    from PySide6.QtWidgets import QLabel
    assert d.listed() == [] and d.findChild(QLabel, "empty") is not None
    d.search.setText("")
    d.show_.setCurrentIndex(d.show_.findData("on")); app.processEvents()
    assert [e.id for e in d.listed()] == ["spiral"]               # Animation is off
    d.show_.setCurrentIndex(d.show_.findData("bundled")); app.processEvents()
    assert [e.id for e in d.listed()] == ["animation"]
    d.show_.setCurrentIndex(0)
    d.order.setCurrentIndex(d.order.findData("on")); app.processEvents()
    assert [e.id for e in d.listed()][0] == "spiral"
    d.put_view("compact"); app.processEvents()
    from PySide6.QtWidgets import QFrame, QToolButton
    assert d.findChild(QFrame, "extension_line") is not None and d.findChild(QFrame, "extension_card") is None
    d.findChild(QToolButton, "open_spiral").click(); app.processEvents()
    assert "spiral" in d._open
    from tensela.ui.widgets import Switch
    assert d.findChild(Switch, "switch_spiral").isChecked()
    d.put_view("detailed")
    # Installed again (the same version): it says so, and on as it was.
    from tensela.ui.extensions_dialog import InstallDialog
    same = next(e for e in E.available() if e.id == "spiral")
    note = InstallDialog(d, same, same).findChild(QLabel, "version_note")
    assert "same version" in note.text()
    # Off: its node marked again, its action, menu entry, panel and icon gone; the process that computes was started
    # again without it.
    pid = w._calculator_.current.process.pid
    assert w.turn_extension("spiral", False) == ""; settle()
    assert w.editor.boxes["s"].with_error and not any(a.text() == "Say hello" for a in every(w._menu_extensions))
    assert w._calculator_.current.process.pid != pid and w.extensions_on() == []
    assert ("spiral", "Spiral") not in w._extension_panels and "spiral.spiral" not in E.ICONS
    menu = QMenu()
    w._menu_canvas_and_extensions(menu, "s")
    assert not any(a.text() == "What is this node?" for a in menu.actions())
    w.recompute(); settle()                                    # nobody hears now: nothing fails
    print("ok", flush=True)
    os._exit(0)

def safely():
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(4)

QTimer.singleShot(500, safely)
QTimer.singleShot(90000, lambda: os._exit(3))
app.exec()
'''


def test_in_the_window(home):
    pytest.importorskip("PySide6")
    E.load(E.install(zipped(SPIRAL, home / "spiral.zip")))
    g = Graph()
    g.node("Spiral", "s", turns=2)
    project = home / "spiral.tela"
    project.write_text(to_text(Project(g, ["s"])), encoding="utf-8")
    E.unload("spiral")
    E.uninstall(next(e for e in E.available() if e.id == "spiral"))
    script = home / "window.py"
    script.write_text(WINDOW, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "share"),
           "XDG_CACHE_HOME": str(home / "cache"), "XDG_RUNTIME_DIR": str(home), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(SRC)}
    env.pop("TENSELA_CALCULATE_HERE", None)
    env.pop(E.ENVIRONMENT, None)
    result = subprocess.run([sys.executable, str(script), str(project), str(home / "spiral.zip")], env=env,
                            capture_output=True, text=True, timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]


def test_the_door_refuses_what_it_does_not_know(home):
    ext = E.install(zipped(SPIRAL, home / "spiral.zip"))
    api = E.Api(ext)
    with pytest.raises(ShapeError):
        api.menu("toolbar", "x", print)
    with pytest.raises(ShapeError):
        api.on("clicked", print)
    with pytest.raises(ShapeError):
        api.icon("bad", "../../outside.svg")
    assert api.icon("spiral", "spiral.svg") == "spiral.spiral" and E.ICONS["spiral.spiral"].startswith("<path")
    assert api._icon_name("spiral") == "spiral.spiral" and api._icon_name("gear") == "gear"
    E.ICONS.pop("spiral.spiral")


def test_packing_one_being_written(home):
    import shutil
    folder = home / "spiral-dev"
    shutil.copytree(SPIRAL, folder)
    (folder / "spiral" / "__pycache__").mkdir(exist_ok=True)
    (folder / "spiral" / "__pycache__" / "x.pyc").write_bytes(b"no")
    (folder / ".git").mkdir()
    (folder / ".git" / "config").write_text("no")
    target, fingerprint = E.pack(folder, home / "out")
    assert target.name == "spiral-1.1.0.zip" and len(fingerprint) == 64
    names = zipfile.ZipFile(target).namelist()
    assert "spiral/extension.toml" in names and "spiral/spiral/__init__.py" in names
    assert not any("__pycache__" in n or ".git" in n for n in names)
    assert E.pack(folder, home / "out")[1] == fingerprint            # the same files, the same fingerprint
    assert E.look_inside(target)[0].id == "spiral" and E.install(target).id == "spiral"
    (folder / "spiral" / "__init__.py").write_text("x = 1\n")
    with pytest.raises(ShapeError, match="register"):
        E.pack(folder, home / "out")
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run([sys.executable, "-m", "tensela.ui.launch", "--pack-extension", str(SPIRAL),
                             str(home / "cli")], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and "sha256 " in result.stdout and (home / "cli" / "spiral-1.1.0.zip").is_file()


def test_versions_and_finding_among_many():
    pytest.importorskip("PySide6")
    from tensela import language
    from tensela.ui import extensions_dialog as D
    language.LANGUAGE, before = "en", language.LANGUAGE
    try:
        assert E.compare("1.2.0", "1.10") == -1 and E.compare("2", "1.9.9") == 1 and E.compare("1.0", "1.0.0") == 0
        old, new = E.card({"id": "wall", "version": "1.0.0"}), E.card({"id": "wall", "version": "1.1.0"})
        assert "updates" in D.version_note(new, old)[0] and D.version_note(new, old)[1] == "accent"
        assert "older" in D.version_note(old, new)[0] and D.version_note(old, new)[1] == "warn"
        assert D.version_note(new, None) == ("", "")
        a = E.card({"id": "facade", "name": "Fachada paramétrica", "author": "Ana", "description": "Quiebrasoles"})
        b = E.card({"id": "weather", "name": "Weather", "author": "Luis", "permissions": {"network": "the sky"}})
        c = E.card({"id": "bricks", "name": "Bricks", "author": "Ana"})
        assert [e.id for e in (a, b, c) if D.found_by(e, "parametrica")] == ["facade"]   # without accents
        assert [e.id for e in (a, b, c) if D.found_by(e, "ana")] == ["facade", "bricks"]  # by who makes it
        assert [e.id for e in (a, b, c) if D.found_by(e, "QUIEBRA ana")] == ["facade"]   # every word
        assert [e.id for e in D.ordered([b, c, a], "name", [])] == ["bricks", "facade", "weather"]
        assert [e.id for e in D.ordered([b, c, a], "on", ["weather"])] == ["weather", "bricks", "facade"]
        assert [e.id for e in D.shown([a, b, c], "asks", [])] == ["weather"]
        assert [e.id for e in D.shown([a, b, c], "off", ["bricks"])] == ["facade", "weather"]
    finally:
        language.LANGUAGE = before


# --- The extension Animation (bundled, off at first) -----------------------------------------------------------------

def test_animation_comes_with_tensela_and_is_off(home):
    found = {e.id: e for e in E.available()}
    assert "animation" in found and found["animation"].bundled and not found["animation"].problem
    assert found["animation"].permissions == {}


ANIMATION = r'''
import os, sys, time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1200, 900); w.show()

def every(menu):
    # The entries of a menu, also those of its submenus (one per extension)...
    out = []
    for a in menu.actions():
        out.append(a)
        if a.menu() is not None:
            out += every(a.menu())
    return out

def settle():
    for _ in range(5):
        w.wait_computation(); app.processEvents(); time.sleep(0.02)

def run():
    w.open_(sys.argv[1]); settle()
    assert not any("Anim" in a.text() for a in every(w._menu_extensions))      # off at first
    assert w.turn_extension("animation", True) == ""
    # A panel (not a window over Tensela): in the Extensions menu, and in the right-click menu of the 3D view.
    toggle = next(a for a in every(w._menu_extensions) if a.text() == "Panel: Animation")
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    w._extension_entries(menu, "view")
    next(a for a in menu.actions() if a.text() == "Animate a slider…").trigger(); app.processEvents()
    assert toggle.isChecked()
    import tensela_extension_animation as A
    d = w.show_extension_panel("Animation", "animation")
    found = A.sliders(w)
    name, control, index = found[0]
    assert [n for n, _, _ in d.found] == [n for n, _, _ in found] and d.go.isEnabled()
    before = w.project.graph.nodes[control.node].inputs[control.input_]
    assert A.values(0, 10, 3, False) == [0, 5, 10] and A.values(0, 10, 3, True) == [0, 5, 10, 5]
    d.frames.setValue(5); d.back.setChecked(True); d.width.setCurrentIndex(1)     # 640 px
    out = Path(sys.argv[2])
    # The button itself (it asks where, answered here), not only the function behind it.
    import tensela_extension_animation.panel as D
    D.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out / "tower.gif"), ""))
    d.go.click()
    saved = out / "tower.gif"
    assert saved.is_file(), "the button did nothing"
    from PIL import Image
    with Image.open(saved) as gif:
        assert gif.n_frames == 8 and gif.width == 640, (gif.n_frames, gif.width)
    assert w.project.graph.nodes[control.node].inputs[control.input_] == before      # the slider, back
    assert d.isVisible()                                                             # the panel stays
    d.frames.setValue(3); d.format.setCurrentIndex(1); d.back.setChecked(False)   # (the panel keeps what was put)
    d.export(str(out / "frames"))
    assert sorted(p.name for p in (out / "frames").iterdir()) == ["frame-0001.png", "frame-0002.png", "frame-0003.png"]
    assert "Animation saved" in w.statusBar().currentMessage()
    # Nothing seen in 3D: it says why in the panel, and the button waits.
    w.project.export.clear(); w.recompute(); settle()
    assert not d.go.isEnabled() and "nothing seen" in d.missing.text()
    print("ok", flush=True)
    os._exit(0)

def safely():
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(4)

QTimer.singleShot(500, safely)
QTimer.singleShot(120000, lambda: os._exit(3))
app.exec()
'''


def test_animation_makes_a_gif_and_png_images_of_a_slider(home):
    pytest.importorskip("PySide6")
    script = home / "animation.py"
    script.write_text(ANIMATION, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "share"),
           "XDG_CACHE_HOME": str(home / "cache"), "XDG_RUNTIME_DIR": str(home), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(SRC)}
    env.pop("TENSELA_CALCULATE_HERE", None)
    env.pop(E.ENVIRONMENT, None)
    tower = SRC / "tensela" / "templates" / "twisting-tower.tela"
    result = subprocess.run([sys.executable, str(script), str(tower), str(home)], env=env, capture_output=True,
                            text=True, timeout=150)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]


DEVELOP = r"""
import os, sys, time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela import extensions as E
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1200, 900); w.show()

def every(menu):
    # The entries of a menu, also those of its submenus (one per extension)...
    out = []
    for a in menu.actions():
        out.append(a)
        if a.menu() is not None:
            out += every(a.menu())
    return out

def run():
    folder = Path(sys.argv[1])
    w.manage_extensions(); app.processEvents()
    d = w._extensions_dialog
    d.develop(str(folder / "spiral")); app.processEvents()        # its package chosen: the folder above is taken
    ext = next(e for e in E.available() if e.id == "spiral")
    assert ext.development and ext.path == folder.resolve() and "spiral" in w.extensions_on()
    assert any(a.text() == "Say hello" for a in every(w._menu_extensions))
    from PySide6.QtWidgets import QToolButton
    assert d.findChild(QToolButton, "reload_spiral") is not None
    d.show_.setCurrentIndex(d.show_.findData("development")); app.processEvents()
    assert [e.id for e in d.listed()] == ["spiral"]
    d.show_.setCurrentIndex(0)
    # A change in its code, and Reload: the new one, without closing Tensela.
    init = folder / "spiral" / "__init__.py"
    init.write_text(init.read_text().replace('tensela.action("Say hello"', 'tensela.action("Say hello again"'))
    d.findChild(QToolButton, "reload_spiral").click(); app.processEvents()
    labels = [a.text() for a in every(w._menu_extensions)]
    assert "Say hello again" in labels and "Say hello" not in labels, labels
    sub = next(a.menu() for a in w._menu_extensions.actions() if a.menu() is not None)
    assert [a.text() for a in sub.actions() if a.text()] == ["Say hello again", "Panel: Spiral"]   # whose, apart
    # Another copy of the same one loaded: it takes the place of the first (one folder per extension).
    import shutil
    copy = folder.parent / "spiral-copy"
    shutil.copytree(folder, copy)
    d.develop(str(copy)); app.processEvents()
    assert E.development_folders() == [copy.resolve()], E.development_folders()
    # It stops being developed: it goes (its folder stays).
    d.stop_developing(next(e for e in E.available() if e.id == "spiral")); app.processEvents()
    assert E.development_folders() == []
    assert not any(e.id == "spiral" for e in E.available()) and init.is_file()
    assert not any("Say hello" in a.text() for a in every(w._menu_extensions))
    print("ok", flush=True)
    os._exit(0)

def safely():
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(4)

QTimer.singleShot(500, safely)
QTimer.singleShot(90000, lambda: os._exit(3))
app.exec()
"""


def test_one_being_written_loads_from_its_folder_and_reloads(home):
    pytest.importorskip("PySide6")
    import shutil
    folder = home / "spiral-dev"
    shutil.copytree(SPIRAL, folder)
    script = home / "develop.py"
    script.write_text(DEVELOP, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "share"),
           "XDG_CACHE_HOME": str(home / "cache"), "XDG_RUNTIME_DIR": str(home), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(SRC)}
    env.pop("TENSELA_CALCULATE_HERE", None)
    env.pop(E.ENVIRONMENT, None)
    result = subprocess.run([sys.executable, str(script), str(folder)], env=env, capture_output=True, text=True,
                            timeout=120)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
