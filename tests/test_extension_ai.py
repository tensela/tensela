"""The extension AI connection (extensions/ai-connection): the bridge speaks MCP with the AI program and hands each
tool to the open window through a local socket; the window answers and shows what was done. It comes apart from
Tensela (not in bundled_extensions)."""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tensela import extensions as E

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
FOLDER = HERE.parent / "extensions" / "ai-connection"


def zipped(target: Path) -> Path:
    with zipfile.ZipFile(target, "w") as z:
        for f in sorted(FOLDER.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f"ai-connection/{f.relative_to(FOLDER)}")
    return target


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    yield tmp_path
    for ext_id in list(E.LOADED):
        E.unload(ext_id)


def test_its_card_asks_only_to_talk_with_programs_of_the_computer(home):
    ext, _ = E.look_inside(zipped(home / "ai.zip"))
    assert ext.id == "ai-connection" and not ext.problem and list(ext.permissions) == ["local"]
    assert "internet" in ext.why("local")


def test_the_bridge_speaks_mcp_and_says_when_the_window_is_not_there(home):
    import io
    E.load(E.install(zipped(home / "ai.zip")))
    from tensela_extension_ai_connection import bridge, protocol
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                            "clientInfo": {"name": "test-client", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_project", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "rm_rf", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
                {"jsonrpc": "2.0", "id": 6, "method": "ping"}]
    reading = io.BytesIO(b"".join(protocol.line(m) for m in messages) + b"not json\n")
    writing = io.BytesIO()
    assert bridge.main([], reading, writing) == 0
    answers = [json.loads(x) for x in writing.getvalue().splitlines()]
    by_id = {a.get("id"): a for a in answers}
    assert by_id[1]["result"]["protocolVersion"] == "2025-06-18" and "tools" in by_id[1]["result"]["capabilities"]
    assert by_id[1]["result"]["serverInfo"]["name"] == "tensela"
    tools = {t["name"]: t for t in by_id[2]["result"]["tools"]}
    assert list(tools) == ["get_project", "get_node", "list_node_kinds", "get_node_kind", "view_image",
                           "edit_project", "calculate", "open_project", "save_project", "export"]
    assert all(tools[n]["annotations"]["readOnlyHint"] for n in list(tools)[:5] + ["calculate"])
    assert not tools["edit_project"]["annotations"]["readOnlyHint"]
    assert by_id[3]["result"]["isError"] and "not open" in by_id[3]["result"]["content"][0]["text"]
    assert by_id[4]["error"]["code"] == -32602 and by_id[5]["error"]["code"] == -32601 and by_id[6]["result"] == {}
    assert by_id[None]["error"]["code"] == -32700 and len(answers) == 7                  # no answer to a notification


def test_the_command_only_runs_when_the_extension_is_on(home):
    E.install(zipped(home / "ai.zip"))
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run([sys.executable, "-m", "tensela.ui.launch", "--extension", "ai-connection"],
                            input="", env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2 and "off" in result.stderr.lower() + result.stderr
    result = subprocess.run([sys.executable, "-m", "tensela.ui.launch", "--extension", "nothing-here"],
                            input="", env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2


WINDOW = r'''
import json, os, subprocess, sys, threading, time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela import extensions as E
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1200, 900); w.show()

def settle():
    for _ in range(5):
        w.wait_computation(); app.processEvents(); time.sleep(0.02)

def ask(messages):
    """The bridge, started as an AI program would, with these messages; the window answers meanwhile."""
    out = {}
    def go():
        text = "".join(json.dumps(m) + "\n" for m in messages)
        r = subprocess.run([sys.executable, "-m", "tensela.ui.launch", "--extension", "ai-connection"],
                           input=text, capture_output=True, text=True, timeout=120)
        out["answers"] = {a["id"]: a for a in map(json.loads, r.stdout.splitlines())}
        out["err"] = r.stderr
    t = threading.Thread(target=go); t.start()
    while t.is_alive():
        app.processEvents(); time.sleep(0.01)
    assert out.get("answers"), out.get("err")
    return out["answers"]

def call(i, tool, **arguments):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}

HELLO = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Test client"}}}

def run():
    w.open_(sys.argv[1]); settle()
    E.install(Path(sys.argv[2]))
    assert w.turn_extension("ai-connection", True) == ""; app.processEvents()
    import tensela_extension_ai_connection as A
    from tensela_extension_ai_connection import protocol
    assert A.SERVER is not None and A.SERVER.listening and os.path.exists(protocol.address())
    assert oct(os.stat(protocol.address()).st_mode & 0o777) == "0o700", oct(os.stat(protocol.address()).st_mode)
    answers = ask([HELLO, call(1, "get_project"), call(2, "get_node", name="floor"), call(3, "get_node", name="nope"),
                   call(4, "list_node_kinds", search="rectangle"), call(5, "get_node_kind", kind="Series"),
                   call(6, "view_image", width=400)])
    project = answers[1]["result"]["structuredContent"]
    assert not answers[1]["result"]["isError"]
    names = [n["name"] for n in project["nodes"]]
    assert "floor" in names and project["sliders"] and project["file"].endswith("twisting-tower.tela")
    floor = answers[2]["result"]["structuredContent"]
    assert floor["kind"] == "Series" and floor["result"]["what"] == "number" and floor["result"]["first"]
    assert "height" in floor["used_by"] or floor["used_by"]
    assert answers[3]["result"]["isError"] and "floor" in answers[3]["result"]["content"][0]["text"]
    kinds = [k["kind"] for k in answers[4]["result"]["structuredContent"]["kinds"]]
    assert any("Rectangle" in k for k in kinds), kinds
    series = answers[5]["result"]["structuredContent"]
    assert series["kind"] == "Series" and series["inputs"] and series["help"]
    image = answers[6]["result"]
    if not image["isError"]:                     # (without a screen the view may not draw: then it says why)
        assert image["content"][0]["type"] == "image" and image["content"][0]["mimeType"] == "image/png"
    # What it did, in the panel; the mark of the status bar went with the bridge.
    panel = w.show_extension_panel("AI connection", "ai-connection")
    app.processEvents()
    texts = [panel.done.item(i).text() for i in range(panel.done.count())]
    assert any("Looked at the project" in t and "Test client" in t for t in texts), texts
    assert any("Looked at the node «nope»: There is no node «nope»" in t and "✖" in t for t in texts), texts
    assert "Waiting" in panel.state.text() and not A.SERVER.mark.isVisible()
    assert "--extension" in panel.line.toPlainText() and '"mcpServers"' in panel.settings.toPlainText()
    # Paused: the bridge says so; allowed again, it answers again.
    panel.pause.click(); app.processEvents()
    assert not A.SERVER.listening and "Paused" in panel.state.text() and panel.pause.text() == "Allow again"
    answers = ask([HELLO, call(1, "get_project")])
    assert answers[1]["result"]["isError"] and "paused" in answers[1]["result"]["content"][0]["text"]
    panel.pause.click(); app.processEvents()
    assert A.SERVER.listening
    assert not ask([HELLO, call(1, "get_project")])[1]["result"]["isError"]
    # Off: it stops listening and its socket goes.
    assert w.turn_extension("ai-connection", False) == ""; app.processEvents()
    assert not os.path.exists(protocol.address())
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
QTimer.singleShot(240000, lambda: os._exit(3))
app.exec()
'''


def test_an_ai_program_looks_at_the_open_project(home):
    pytest.importorskip("PySide6")
    script = home / "ai.py"
    script.write_text(WINDOW, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "share"),
           "XDG_CACHE_HOME": str(home / "cache"), "XDG_RUNTIME_DIR": str(home), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(SRC)}
    env.pop("TENSELA_CALCULATE_HERE", None)
    env.pop(E.ENVIRONMENT, None)
    tower = SRC / "tensela" / "templates" / "twisting-tower.tela"
    result = subprocess.run([sys.executable, str(script), str(tower), str(zipped(home / "ai.zip"))], env=env,
                            capture_output=True, text=True, timeout=270)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]


CHANGE = r"""
import json, os, subprocess, sys, threading, time
from pathlib import Path
from PySide6.QtCore import QTimer, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela import extensions as E
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1200, 900); w.show()
OUT = Path(sys.argv[3])

def settle():
    for _ in range(5):
        w.wait_computation(); app.processEvents(); time.sleep(0.02)

def ask(messages):
    out = {}
    def go():
        text = "".join(json.dumps(m) + "\n" for m in messages)
        r = subprocess.run([sys.executable, "-m", "tensela.ui.launch", "--extension", "ai-connection"],
                           input=text, capture_output=True, text=True, timeout=200)
        out["answers"] = {a["id"]: a for a in map(json.loads, r.stdout.splitlines())}
        out["err"] = r.stderr
    t = threading.Thread(target=go); t.start()
    while t.is_alive():
        app.processEvents(); time.sleep(0.01)
    assert out.get("answers") and 1 in out["answers"], (out.get("err")[-3000:], out.get("answers"))
    return out["answers"]

HELLO = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Test client"}}}

def tool(name, **arguments):
    answers = ask([HELLO, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": arguments}}])
    assert 1 in answers, answers
    return answers[1]["result"]

def edit(what, *operations):
    return tool("edit_project", what=what, operations=list(operations))

def run():
    w.open_(sys.argv[1]); settle()
    E.install(Path(sys.argv[2]))
    assert w.turn_extension("ai-connection", True) == ""; app.processEvents()
    import tensela_extension_ai_connection.changes as C
    answer = [False]
    asked = []
    from PySide6.QtWidgets import QLabel
    C.ASKING = lambda dialog: asked.append(dialog.findChild(QLabel).text()) or answer[0]
    g = lambda: w.project.graph
    # One value: changed, computed, said in the status bar; one Ctrl+Z undoes it.
    r = edit("30 floors", {"op": "set_input", "node": "floor", "input": "count", "value": 30})
    assert not r["isError"] and r["structuredContent"]["changed"], r
    assert g().nodes["floor"].inputs["count"] == 30 and w.modified
    assert "30 floors" in w.statusBar().currentMessage() and "Ctrl+Z" in w.statusBar().currentMessage()
    w.undo(); settle()
    assert g().nodes["floor"].inputs["count"] == 24
    # Several operations, one step: a node added, wired, seen, a slider; its card placed to the right of its source.
    sliders = [(c.node, c.input_, c.maximum) for c in w.project.controls]
    r = edit("a railing on every slab",
             {"op": "add_node", "kind": "Move", "name": "railing",
              "inputs": {"geometry": {"from": "turned"}, "distance": 1.1}},
             {"op": "show", "node": "railing", "visible": True},
             {"op": "add_slider", "node": "floor", "input": "count", "minimum": 1, "maximum": 60})
    assert not r["isError"], r
    assert g().nodes["railing"].inputs["geometry"] is g().nodes["turned"] and "railing" in w.project.export
    assert any(c.node == "floor" and c.maximum == 60 and c.step == 1 for c in w.project.controls)
    pos = w.editor.positions()
    assert pos["railing"][0] > pos["turned"][0], pos
    w.undo(); settle()
    assert "railing" not in g().nodes                                     # all of it, in one Ctrl+Z
    assert [(c.node, c.input_, c.maximum) for c in w.project.controls] == sliders
    # One that fails: nothing changes, and it says which.
    before = w._snapshot()
    r = edit("broken", {"op": "rename", "node": "plan", "new_name": "footprint"},
             {"op": "delete_node", "node": "floor"})
    assert r["isError"] and "Operation 2 (delete_node)" in r["content"][0]["text"], r
    assert w._snapshot() == before and "plan" in g().nodes
    # Rename and delete.
    assert not edit("rename", {"op": "rename", "node": "plan", "new_name": "footprint"})["isError"]
    assert "footprint" in g().nodes and g().nodes["raised"].inputs["geometry"] is g().nodes["footprint"]
    # A Code node asks first, showing the code: not allowed, nothing; allowed, it is there.
    code = {"op": "add_node", "kind": "Code", "name": "wave", "inputs": {"code": "result = [1, 2, 3]\n"}}
    r = edit("a wave", code)
    assert r["isError"] and "did not allow" in r["content"][0]["text"] and "wave" not in g().nodes
    assert asked and "Python" in asked[-1]
    answer[0] = True
    assert not edit("a wave", code)["isError"] and "wave" in g().nodes
    # Calculate a node not seen.
    r = tool("calculate", nodes=["turn"])
    assert r["structuredContent"]["turn"]["result"]["what"] == "number", r
    # Files ask first: not allowed, nothing written; allowed, written.
    answer[0] = False
    target = OUT / "tower.tela"
    r = tool("save_project", path=str(target))
    assert r["isError"] and not target.exists()
    answer[0] = True
    assert not tool("save_project", path=str(target))["isError"] and target.exists() and w.filepath == target
    assert not tool("export", format="obj", path=str(OUT / "tower.obj"))["isError"]
    assert (OUT / "tower.obj").stat().st_size
    assert tool("export", format="obj", path="relative.obj")["isError"]
    # Only look: nothing is changed.
    panel = w.show_extension_panel("AI connection", "ai-connection"); app.processEvents()
    panel.mode.put("look"); panel.mode.change.emit("look"); app.processEvents()
    assert QSettings().value(C.MODE) == "look" and "cannot change" in panel.may.text()
    r = edit("no", {"op": "set_input", "node": "floor", "input": "count", "value": 5})
    assert r["isError"] and "Only look" in r["content"][0]["text"] and g().nodes["floor"].inputs["count"] == 24
    assert not tool("get_project")["isError"]                     # looking, yes
    panel.mode.put("change"); panel.mode.change.emit("change"); app.processEvents()
    texts = [panel.done.item(i).text() for i in range(panel.done.count())]
    assert any("Changed the project: 30 floors" in t for t in texts), texts
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
QTimer.singleShot(400000, lambda: os._exit(3))
app.exec()
"""


def test_an_ai_program_changes_the_project_and_asks_for_code_and_files(home):
    pytest.importorskip("PySide6")
    script = home / "change.py"
    script.write_text(CHANGE, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "share"),
           "XDG_CACHE_HOME": str(home / "cache"), "XDG_RUNTIME_DIR": str(home), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(SRC)}
    env.pop("TENSELA_CALCULATE_HERE", None)
    env.pop(E.ENVIRONMENT, None)
    tower = SRC / "tensela" / "templates" / "twisting-tower.tela"
    out = home / "out"
    out.mkdir()
    result = subprocess.run([sys.executable, str(script), str(tower), str(zipped(home / "ai.zip")), str(out)],
                            env=env, capture_output=True, text=True, timeout=420)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
