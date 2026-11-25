"""What the AI program can ask of the window, in this version only to look: the project, a node, the kinds of node
and an image of the 3D view. Each tool takes the window and its arguments and gives an MCP result
({"content": [...], "structuredContent": {...}, "isError": bool}). The names of kinds and inputs go in English (the
base of Tensela); the names of the nodes are the person's."""
from __future__ import annotations

import base64
import json
import math
import tempfile
from pathlib import Path

import numpy as np

#: The first values of a result that are given (the rest, counted).
FIRST = 20


class Refused(Exception):
    """What the AI program asked cannot be done (said to it, as an error of the tool)."""


def plain(value, depth: int = 0):
    """A value of an input as JSON: numbers, texts, yes/no, lists (the long ones cut), a wire as {"from": node}."""
    from tensela.graph import Node
    if isinstance(value, Node):
        return {"from": value.name}
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else str(value)
    if isinstance(value, str) or value is None:
        return value
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, dict):
        return {str(k): plain(v, depth + 1) for k, v in list(value.items())[:FIRST]}
    if isinstance(value, (list, tuple)):
        items = [plain(v, depth + 1) for v in list(value)[:FIRST]] if depth < 3 else ["…"]
        if len(value) > FIRST:
            items.append(f"… ({len(value)} in all)")
        return items
    if hasattr(value, "values") and hasattr(value, "levels"):            # a Data given as a value
        return summary(value)
    return str(value)


def summary(data, first: int = 6) -> dict | None:
    """A result in a few words: what it is, how many, its levels and shape, its first values (numbers, texts)."""
    if data is None:
        return None
    values = np.asarray(data.values)
    if data.kind is not None:
        what = data.kind.name
    elif values.dtype == bool:
        what = "yes/no"
    elif values.dtype.kind in "fiu":
        what = "number"
    else:
        what = "text"
    out = {"what": what, "count": int(data.count), "levels": list(data.levels),
           "shape": data.shape if data.levels else "1"}
    if data.kind is None:
        chosen = values[data.mask] if data.levels else values.reshape(-1)
        out["first"] = [plain(v) for v in chosen.reshape(-1)[:first]]
    return out


def _project(window):
    if window.project is None:
        raise Refused("No project is open in Tensela.")
    return window.project


def _result(data: dict, text: str | None = None) -> dict:
    return {"content": [{"type": "text", "text": text or json.dumps(data, ensure_ascii=False, indent=1)}],
            "structuredContent": data, "isError": False}


def get_project(window, arguments: dict) -> dict:
    p = _project(window)
    errors = dict(getattr(window, "last_errors", {}) or {})
    nodes = []
    for node in p.graph.nodes.values():
        nodes.append({"name": node.name, "kind": node.kind.name, "category": node.kind.category,
                      "inputs": {k: plain(v) for k, v in node.inputs.items()},
                      "visible": node.name in p.export, "result": summary(node._value),
                      "error": errors.get(node.name)})
    sliders = []
    for c in p.controls:
        current = p.graph.nodes[c.node].inputs.get(c.input_) if c.node in p.graph.nodes else None
        sliders.append({"node": c.node, "input": c.input_, "label": c.label or None, "value": plain(current),
                        "minimum": c.minimum, "maximum": c.maximum, "step": c.step, "unit": c.unit or None})
    data = {"file": str(window.filepath) if window.filepath else None, "description": p.description or None,
            "nodes": nodes, "sliders": sliders, "chosen": getattr(window, "_selection", None),
            "not_calculated": [n.name for n in p.graph.nodes.values() if n._value is None
                               and n.name not in errors]}
    return _result(data)


def get_node(window, arguments: dict) -> dict:
    p = _project(window)
    name = str(arguments.get("name", ""))
    node = p.graph.nodes.get(name)
    if node is None:
        raise Refused(f"There is no node «{name}». The nodes are: {', '.join(p.graph.nodes) or 'none'}.")
    kind = node.kind
    inputs = []
    for i in kind.inputs:
        inputs.append({"name": i.name, "value": plain(node.inputs.get(i.name)), "help": i.help or None,
                       "options": list(i.options) or None})
    data = {"name": node.name, "kind": kind.name, "category": kind.category, "what_the_kind_does": kind.help,
            "inputs": inputs, "visible": node.name in p.export, "result": summary(node._value, FIRST),
            "error": (getattr(window, "last_errors", {}) or {}).get(node.name),
            "used_by": [n.name for n in p.graph.nodes.values() if any(v is node for v in n.inputs.values())]}
    return _result(data)


def _kinds():
    from tensela.nodes import CATALOG
    return [t for t in CATALOG.values() if t.function is not None]


def list_node_kinds(window, arguments: dict) -> dict:
    search = str(arguments.get("search") or "").casefold().split()
    category = str(arguments.get("category") or "").casefold()
    found = []
    for t in _kinds():
        where = " ".join((t.name, t.help, " ".join(t.synonyms))).casefold()
        if category and t.category.casefold() != category:
            continue
        if search and not all(w in where for w in search):
            continue
        found.append({"kind": t.name, "category": t.category, "inputs": [i.name for i in t.inputs],
                      "does": (t.help.split(". ")[0].rstrip(".") + ".") if t.help else ""})
    return _result({"kinds": found, "categories": sorted({t.category for t in _kinds()})})


def get_node_kind(window, arguments: dict) -> dict:
    from tensela.nodes import CATALOG
    from tensela.nodes import REQUIRED
    name = str(arguments.get("kind", ""))
    t = CATALOG.get(name) or next((k for k in _kinds() if k.name.casefold() == name.casefold()), None)
    if t is None:
        raise Refused(f"There is no kind of node «{name}». list_node_kinds gives them.")
    inputs = [{"name": i.name, "default": None if i.default is REQUIRED else plain(i.default),
               "required": i.default is REQUIRED, "single": i.single, "options": list(i.options) or None,
               "help": i.help or None, "advanced": i.advanced} for i in t.inputs]
    return _result({"kind": t.name, "category": t.category, "help": t.help, "output": t.output,
                    "inputs": inputs, "extension": t.extension or None})


def view_image(window, arguments: dict) -> dict:
    p = _project(window)
    width = int(arguments.get("width") or 1024)
    width = max(320, min(1600, width))
    from PIL import Image
    with tempfile.TemporaryDirectory(prefix="tensela-ai-") as folder:
        path = Path(folder) / "view.png"
        window.viewer.save_image(path, scale=1, background=None, axes=False)
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width != width:
                img = img.resize((width, max(1, round(img.height * width / img.width))), Image.Resampling.LANCZOS)
            img.save(path, optimize=True)
        data = base64.b64encode(path.read_bytes()).decode("ascii")
    seen = ", ".join(p.export) or "nothing"
    return {"content": [{"type": "image", "data": data, "mimeType": "image/png"},
                        {"type": "text", "text": f"The 3D view as it is seen now. Visible nodes: {seen}."}],
            "isError": False}


TOOLS = {"get_project": get_project, "get_node": get_node, "list_node_kinds": list_node_kinds,
         "get_node_kind": get_node_kind, "view_image": view_image}


#: What each tool did, for the panel's list (in the language of the window).
SAID = {"get_project": 'Looked at the project', "get_node": 'Looked at the node «{x}»',
        "list_node_kinds": 'Looked for kinds of node: {x}', "get_node_kind": 'Read the help of {x}',
        "view_image": 'Looked at the 3D view', "edit_project": 'Changed the project: {x}',
        "calculate": 'Calculated: {x}', "open_project": 'Opened {x}', "save_project": 'Saved {x}',
        "export": 'Exported {x}'}


def said(name: str, arguments: dict) -> str:
    from tensela.language import tr
    x = {"get_node": arguments.get("name"), "get_node_kind": arguments.get("kind"),
         "list_node_kinds": arguments.get("search") or arguments.get("category") or "*",
         "edit_project": arguments.get("what") or len(arguments.get("operations") or []),
         "calculate": ", ".join(map(str, arguments.get("nodes") or [])),
         "open_project": arguments.get("path"), "save_project": arguments.get("path") or "—",
         "export": arguments.get("path")}.get(name, "")
    return tr(SAID[name]).format(x=x) if name in SAID else name


def call(window, name: str, arguments: dict) -> tuple[dict, str]:
    """The result of a tool, and what it did in a few words (for the panel's list)."""
    from tensela.language import tr
    from .changes import TOOLS as CHANGES
    tool = TOOLS.get(name) or CHANGES.get(name)
    if tool is None:
        return ({"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True},
                tr('Asked for something unknown: {x}').format(x=name))
    arguments = arguments if isinstance(arguments, dict) else {}
    what = said(name, arguments)
    try:
        result = tool(window, arguments)
    except Refused as error:
        first = str(error).split(". ")[0]
        return {"content": [{"type": "text", "text": str(error)}], "isError": True}, f"{what}: {first}"
    except Exception as error:                          # noqa: BLE001 (said to the AI program, not lost)
        return ({"content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}], "isError": True},
                f"{what}: {type(error).__name__}")
    return result, what
