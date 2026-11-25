"""What the AI program can change (version 2): the project, in one step that Ctrl+Z undoes, and, with the person's
permission, files (open, save, export).

`edit_project` takes a list of operations and applies them all to a copy of the project: if one fails, nothing is
changed and it says which and why. Then the copy takes the place of the project (the previous one goes to the undo
list) and it is computed. A Code node runs Python: adding one or changing its code asks the person first, showing the
code. The person can set the connection to «Only look»: then nothing is changed.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from tensela.language import tr

from .tools import Refused, _project, _result, plain, summary

#: Where the mode is remembered: "change" (look and change, as it starts) or "look" (only look).
MODE = "extensions/ai-connection/mode"
#: How many operations at most in one step, and the room between the cards of the canvas.
MOST, ACROSS, DOWN = 200, 350, 180
EXPORTS = ("obj", "dxf", "png")


def mode() -> str:
    return "look" if QSettings().value(MODE, "change") == "look" else "change"


def _may_change() -> None:
    if mode() == "look":
        raise Refused("The person set the AI connection to «Only look»: you can look at the project but not change "
                      "it. Ask them to choose «Look and change» in its panel if they want you to.")


def _value(g, value):
    """A value of the AI program as a value of an input: {"from": "node"} is a wire."""
    if isinstance(value, dict) and set(value) == {"from"}:
        name = str(value["from"])
        if name not in g.nodes:
            raise Refused(f"there is no node «{name}» to connect from")
        return g.nodes[name]
    if isinstance(value, dict):
        raise Refused('a value is a number, a text, yes/no, a list, or {"from": "<node>"} for a wire')
    return value


def _input(node, name: str):
    found = next((i for i in node.kind.inputs if i.name == name), None)
    if found is None:
        raise Refused(f"«{node.name}» ({node.kind.name}) has no input «{name}»; it has: "
                      f"{', '.join(i.name for i in node.kind.inputs)}")
    return found


def _node(g, name):
    name = str(name or "")
    if name not in g.nodes:
        raise Refused(f"there is no node «{name}»")
    return g.nodes[name]


def _place(p, node) -> None:
    """Where a new card goes: to the right of what reaches it, or under everything; never on another."""
    taken = [tuple(v) for n, v in p.positions.items() if n != node.name]
    if not taken:
        return                                          # (a project without positions arranges itself)
    sources = [p.positions[v.name] for v in node.inputs.values()
               if getattr(v, "name", None) in p.positions]
    if sources:
        x = max(s[0] for s in sources) + ACROSS
        y = sum(s[1] for s in sources) / len(sources)
    else:
        x = min(t[0] for t in taken)
        y = max(t[1] for t in taken) + DOWN
    while any(abs(x - tx) < ACROSS * 0.8 and abs(y - ty) < DOWN * 0.8 for tx, ty in taken):
        y += DOWN
    p.positions[node.name] = [round(x), round(y)]


def _forget(p, name: str) -> None:
    p.export = [n for n in p.export if n != name]
    p.view.pop(name, None)
    p.positions.pop(name, None)
    p.thumbnails = [n for n in p.thumbnails if n != name]
    p.controls = [c for c in p.controls if c.node != name]


def apply(p, op: dict, code: list, touched: list) -> None:
    """One operation on the project `p` (a copy). The code of Code nodes goes to `code` (to ask first)."""
    from tensela.nodes import CATALOG, CODE_AT_FIRST
    from tensela.project_file import Control
    g = p.graph
    kind = op.get("op")
    if kind == "add_node":
        name_kind = str(op.get("kind", ""))
        if name_kind not in CATALOG and name_kind not in g.kinds:
            raise Refused(f"there is no kind of node «{name_kind}» (list_node_kinds gives them)")
        inputs = {k: _value(g, v) for k, v in (op.get("inputs") or {}).items()}
        name = op.get("name") or None
        node = g.node(name_kind, str(name) if name else None, **inputs)
        if name_kind == "Code":
            code.append((node.name, str(node.inputs.get("code", CODE_AT_FIRST))))
        position = op.get("position")
        if isinstance(position, (list, tuple)) and len(position) == 2:
            p.positions[node.name] = [float(position[0]), float(position[1])]
        else:
            _place(p, node)
        if op.get("visible"):
            p.export.append(node.name)
        touched.append(node.name)
    elif kind in ("set_input", "connect", "disconnect"):
        if kind == "connect":
            node, name, value = _node(g, op.get("to")), str(op.get("input", "")), {"from": op.get("from")}
        else:
            node, name, value = _node(g, op.get("node")), str(op.get("input", "")), op.get("value")
        found = _input(node, name)
        if kind == "disconnect":
            from tensela.nodes import REQUIRED
            value = None if found.default is REQUIRED else found.default
        g.change(node, name, _value(g, value))
        if node.kind.name == "Code" and name == "code":
            code.append((node.name, str(node.inputs["code"])))
        p.controls = [c for c in p.controls if not (c.node == node.name and c.input_ == name
                                                    and not isinstance(node.inputs[name], (int, float)))]
        touched.append(node.name)
    elif kind == "rename":
        node = _node(g, op.get("node"))
        old, new = node.name, str(op.get("new_name", "")).strip()
        g.rename(node, new)
        p.export = [new if n == old else n for n in p.export]
        p.view = {(new if n == old else n): v for n, v in p.view.items()}
        for style in p.view.values():
            if style.get("by") == old:
                style["by"] = new
        for c in p.controls:
            if c.node == old:
                c.node = new
        if old in p.positions:
            p.positions[new] = p.positions.pop(old)
        p.thumbnails = [new if n == old else n for n in p.thumbnails]
        touched.append(new)
    elif kind == "delete_node":
        node = _node(g, op.get("node"))
        g.remove(node)
        _forget(p, node.name)
    elif kind == "show":
        node = _node(g, op.get("node"))
        p.export = [n for n in p.export if n != node.name] + ([node.name] if op.get("visible", True) else [])
        touched.append(node.name)
    elif kind == "add_slider":
        node = _node(g, op.get("node"))
        name = str(op.get("input", ""))
        _input(node, name)
        value = node.inputs.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Refused(f"a slider is for an input with a fixed number; «{node.name}.{name}» has {plain(value)!r}")
        low, high = float(op.get("minimum", 0)), float(op.get("maximum", max(1.0, float(value) * 2)))
        if not low < high:
            raise Refused("the minimum of a slider must be less than its maximum")
        step = float(op.get("step") or (1 if float(value).is_integer() and low.is_integer() and high.is_integer()
                                        else round((high - low) / 100, 6)))
        p.controls = [c for c in p.controls if not (c.node == node.name and c.input_ == name)]
        p.controls.append(Control(node.name, name, low, high, step, str(op.get("unit") or ""),
                                  str(op.get("label") or "")))
        touched.append(node.name)
    elif kind == "remove_slider":
        node = _node(g, op.get("node"))
        p.controls = [c for c in p.controls if not (c.node == node.name and c.input_ == str(op.get("input", "")))]
    else:
        raise Refused(f"unknown operation «{kind}»")


def edit_project(window, arguments: dict) -> dict:
    from tensela.data import ShapeError
    _project(window)
    _may_change()
    if window._inside is not None:
        raise Refused("The person is inside a group in the canvas: ask them to leave it first (Esc).")
    operations = arguments.get("operations")
    if not isinstance(operations, list) or not operations:
        raise Refused("operations must be a list with at least one operation.")
    if len(operations) > MOST:
        raise Refused(f"At most {MOST} operations in one step.")
    code, touched = [], []
    what = str(arguments.get("what") or "").strip()

    def change(p):
        for k, op in enumerate(operations, 1):
            if not isinstance(op, dict):
                raise Refused(f"Operation {k} is not an object. Nothing was changed.")
            try:
                apply(p, op, code, touched)
            except (Refused, ShapeError, KeyError, ValueError, TypeError) as error:
                raise Refused(f"Operation {k} ({op.get('op')}) failed: {error}. Nothing was changed.") from error
        if code and not ask_code(window, code, what):
            raise Refused("The person did not allow the code of the Code node(s). Nothing was changed.")

    said = tr('The AI changed the project: {what}').format(
        what=what or tr('{n} operation(s)').format(n=len(operations)))
    if not window.edit_project(change, said):
        return _result({"changed": False}, "Nothing changed: the project was already like that.")
    calculate(window, {"nodes": [n for n in dict.fromkeys(touched) if n in window.project.graph.nodes]},
              said=False)
    window.statusBar().showMessage(tr('{what}. Ctrl+Z undoes it.').format(what=said), 15000)   # (after computing)
    errors = dict(getattr(window, "last_errors", {}) or {})
    nodes = {n: {"result": summary(window.project.graph.nodes[n]._value), "error": errors.get(n)}
             for n in dict.fromkeys(touched) if n in window.project.graph.nodes}
    data = {"changed": True, "operations": len(operations), "nodes": nodes,
            "errors_in_the_project": errors, "undo": "The person can undo it all with Ctrl+Z."}
    return _result(data)


def calculate(window, arguments: dict, said: bool = True) -> dict:
    """Calculates nodes that are not seen (Tensela calculates only what is seen), without changing anything."""
    p = _project(window)
    names = [str(n) for n in (arguments.get("nodes") or []) if str(n) in p.graph.nodes]
    if said and not names:
        raise Refused(f"None of those nodes exists. The nodes are: {', '.join(p.graph.nodes)}.")
    window.also_calculate = set(names)
    try:
        window.recompute()
        window.wait_computation()
    finally:
        window.also_calculate = set()
    errors = dict(getattr(window, "last_errors", {}) or {})
    return _result({n: {"result": summary(p.graph.nodes[n]._value if n in p.graph.nodes else None),
                        "error": errors.get(n)} for n in names})


# --- Permission -------------------------------------------------------------------------------------------------------

def ask(window, title: str, text: str, detail: str = "") -> bool:
    """The person decides: Allow or Do not allow (the window waits). Do not allow is the one at hand."""
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout
    dialog = QDialog(window)
    dialog.setObjectName("ai_permission")
    dialog.setWindowTitle(tr('AI connection'))
    dialog.setMinimumWidth(520)
    layout = QVBoxLayout(dialog)
    head = QLabel(f"<b>{title}</b>")
    head.setWordWrap(True)
    layout.addWidget(head)
    said = QLabel(text)
    said.setWordWrap(True)
    layout.addWidget(said)
    if detail:
        box = QPlainTextEdit(detail)
        box.setReadOnly(True)
        box.setMinimumHeight(220)
        box.setStyleSheet("font-family: monospace;")
        layout.addWidget(box)
    row = QHBoxLayout()
    row.addStretch(1)
    no = QPushButton(tr('Do not allow'))
    no.setDefault(True)
    no.clicked.connect(dialog.reject)
    yes = QPushButton(tr('Allow'))
    yes.setAutoDefault(False)
    yes.clicked.connect(dialog.accept)
    row.addWidget(no)
    row.addWidget(yes)
    layout.addLayout(row)
    window.raise_()
    window.activateWindow()
    return ASKING(dialog)


def _exec(dialog) -> bool:
    from PySide6.QtWidgets import QDialog
    return dialog.exec() == QDialog.DialogCode.Accepted


#: How the question is asked (the tests answer it instead).
ASKING = _exec


def ask_code(window, code: list, what: str) -> bool:
    shown = "\n\n".join(f"# {name}\n{text}" for name, text in code)
    return ask(window, tr('The AI wants to put code that runs Python'),
               tr('A Code node runs its Python on your computer (apart, with limits: without files, network or '
                  'other programs). Read it before allowing it.') + (f"\n\n{what}" if what else ""), shown)


# --- Files ------------------------------------------------------------------------------------------------------------

def _path(arguments: dict, suffixes: tuple) -> Path:
    raw = str(arguments.get("path") or "").strip()
    if not raw:
        raise Refused("A path is needed.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise Refused("The path must be absolute (for example /home/…/project.tela).")
    if path.suffix.lower() not in suffixes:
        raise Refused(f"The path must end in {' or '.join(suffixes)}.")
    return path


def open_project(window, arguments: dict) -> dict:
    _may_change()
    path = _path(arguments, (".tela", ".json"))
    if not path.is_file():
        raise Refused(f"There is no file {path}.")
    if not ask(window, tr('The AI wants to open a project'), tr('It opens in a new tab: {path}').format(path=path)):
        raise Refused("The person did not allow it.")
    if not window.open_(str(path)):
        raise Refused(f"It could not be opened: {path}.")
    window.wait_computation()
    return _result({"opened": str(path)})


def save_project(window, arguments: dict) -> dict:
    from tensela.project_file import save
    _project(window)
    _may_change()
    path = _path(arguments, (".tela",)) if arguments.get("path") else window.filepath
    if path is None:
        raise Refused("The project has no file yet: give a path ending in .tela.")
    path = Path(path)
    over = path.exists()
    text = (tr('It saves the project over the file that is there: {path}') if over
            else tr('It saves the project in a new file: {path}')).format(path=path)
    if not ask(window, tr('The AI wants to save the project'), text):
        raise Refused("The person did not allow it.")
    window._collect_canvas()
    save(window.project, path)
    window.filepath = path
    window.modified = False
    window._title()
    return _result({"saved": str(path)})


def export(window, arguments: dict) -> dict:
    p = _project(window)
    _may_change()
    form = str(arguments.get("format", "")).lower()
    if form not in EXPORTS:
        raise Refused(f"The format must be one of: {', '.join(EXPORTS)}.")
    path = _path(arguments, ("." + form,))
    if form != "png" and not p.export:
        raise Refused("Nothing is seen in 3D: turn on the eye of a node first (edit_project, op show).")
    over = path.exists()
    text = (tr('It exports {format} over the file that is there: {path}') if over
            else tr('It exports {format} to a new file: {path}')).format(format=form.upper(), path=path)
    if not ask(window, tr('The AI wants to export'), text):
        raise Refused("The person did not allow it.")
    window.wait_computation()
    if form == "png":
        window.viewer.save_image(path, scale=2, background="white", axes=False)
    else:
        objects = p.visible_objects(computed_only=True)
        if form == "obj":
            from tensela.connectors.obj import export_obj
            export_obj(path, *(data for _, data, _ in objects))
        else:
            from tensela.connectors.dxf import export_dxf
            export_dxf(path, objects)
    return _result({"exported": str(path), "format": form})


TOOLS = {"edit_project": edit_project, "calculate": calculate, "open_project": open_project,
         "save_project": save_project, "export": export}
