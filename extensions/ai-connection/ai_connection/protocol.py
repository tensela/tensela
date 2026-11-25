"""What the bridge (the command the AI program starts) and the window say to each other, and the tools the AI
program sees. Without Qt: the bridge does not start the window.

The window listens on a local socket of the person (`tensela-ai-<key>.sock`, beside the one that hands projects to
the open window: ui/launch.py); one JSON object per line:

    bridge → window   {"hello": "<name of the AI program>"}
    bridge → window   {"id": 3, "tool": "get_node", "arguments": {"name": "floor"}}
    window → bridge   {"id": 3, "result": {"content": [...], "isError": false}}
"""
from __future__ import annotations

import json
from pathlib import Path

#: The versions of MCP it speaks (the newest first): it answers with the one the AI program asks for, if it is one.
VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def address() -> str:
    """Where the window listens for the bridge."""
    from tensela.ui.launch import address as window
    path = Path(window())
    return str(path.with_name(path.name.replace("tensela-", "tensela-ai-", 1)))


def line(message: dict) -> bytes:
    return json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"


INSTRUCTIONS = (
    "Tensela is a parametric design program for architects: a project is a graph of nodes (each one a kind, such as "
    "Rectangle, Series, Formula, Extrude, with inputs that are values or wires from other nodes). The window is "
    "open on the person's computer, with one project. Start with get_project to see its nodes, their values, what "
    "is visible in 3D and what failed; get_node for one node in detail; list_node_kinds and get_node_kind for what "
    "each kind of node does and its inputs; view_image to see the 3D view. Names of node kinds and inputs are in "
    "English; the names of the nodes are the person's. To change the project use edit_project with a list of "
    "operations: they are applied together as one step that the person undoes with Ctrl+Z, and if one fails "
    "nothing changes. Say in «what», in the person's language and in a few words, what the step does. Tensela "
    "calculates only what is seen: calculate gives the result of nodes that are not. A Code node runs Python: adding "
    "one asks the person. open_project, save_project and export also ask the person first. If the person set the "
    "connection to «Only look», nothing can be changed.")

_NOTHING = {"type": "object", "properties": {}, "additionalProperties": False}
_LOOK = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TOOLS = [
    {"name": "get_project", "title": "The open project",
     "description": "The project open in the Tensela window: its file, its description, every node (kind, inputs "
                    "with their values or the node each wire comes from, whether it is seen in 3D, a summary of its "
                    "result, its error), the sliders of Values, the node chosen and those not calculated yet.",
     "inputSchema": _NOTHING, "annotations": _LOOK},
    {"name": "get_node", "title": "A node in detail",
     "description": "One node of the open project in detail: what its kind does, each input (its value or wire, "
                    "and what the input is for), its result (what it is, its levels and shape, its first values) "
                    "and its error.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "The node's name"}},
                     "required": ["name"], "additionalProperties": False}, "annotations": _LOOK},
    {"name": "list_node_kinds", "title": "Kinds of node",
     "description": "The kinds of node Tensela has (also those of the extensions on): name, category, inputs and "
                    "what it does in one line. Optionally only those that match a search or a category.",
     "inputSchema": {"type": "object", "properties": {
         "search": {"type": "string", "description": "Words to look for in the name or what it does"},
         "category": {"type": "string", "description": "Only this category (Values, Curves, Surfaces…)"}},
         "additionalProperties": False}, "annotations": _LOOK},
    {"name": "get_node_kind", "title": "A kind of node in detail",
     "description": "What a kind of node does (its help) and each input: default value, the options it accepts, "
                    "whether it takes a single value, and what it is for.",
     "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "description": "The kind's name"}},
                     "required": ["kind"], "additionalProperties": False}, "annotations": _LOOK},
    {"name": "view_image", "title": "The 3D view",
     "description": "An image (PNG) of the 3D view of the window as it is seen now, with the same framing.",
     "inputSchema": {"type": "object", "properties": {
         "width": {"type": "integer", "minimum": 320, "maximum": 1600, "description": "Width in pixels (1024)"}},
         "additionalProperties": False}, "annotations": _LOOK},
]

_CHANGE = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}
_FILES = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
_OPERATION = {
    "type": "object",
    "description": (
        "One of: "
        "{op: add_node, kind, name?, inputs?: {input: value}, position?: [x, y], visible?: bool} · "
        "{op: set_input, node, input, value} · {op: connect, from, to, input} · {op: disconnect, node, input} "
        "(back to its default) · {op: rename, node, new_name} · {op: delete_node, node} (not if others use it) · "
        "{op: show, node, visible} (its eye: seen in 3D or not) · "
        "{op: add_slider, node, input, minimum, maximum, step?, label?, unit?} (in Values, for a fixed number) · "
        "{op: remove_slider, node, input}. A value is a number, a text, yes/no, a list, or {\"from\": \"<node>\"} "
        "for a wire from another node (also one added earlier in the same list)."),
    "properties": {"op": {"type": "string", "enum": ["add_node", "set_input", "connect", "disconnect", "rename",
                                                      "delete_node", "show", "add_slider", "remove_slider"]}},
    "required": ["op"],
}
TOOLS += [
    {"name": "edit_project", "title": "Change the project",
     "description": "Changes the open project with a list of operations, applied together as one step the person "
                    "undoes with Ctrl+Z; if one fails, nothing is changed and it says which. Then it calculates and "
                    "gives the result and the errors of the nodes touched. Code nodes ask the person first.",
     "inputSchema": {"type": "object", "properties": {
         "operations": {"type": "array", "items": _OPERATION, "minItems": 1, "maxItems": 200},
         "what": {"type": "string", "description": "What this step does, in a few words, in the person's language "
                                                  "(shown to them)"}},
         "required": ["operations", "what"], "additionalProperties": False}, "annotations": _CHANGE},
    {"name": "calculate", "title": "Calculate nodes not seen",
     "description": "Tensela calculates only what is seen (nodes with their eye on, the chosen one…). This gives the "
                    "result and error of the nodes asked for, calculating them now, without changing anything.",
     "inputSchema": {"type": "object", "properties": {"nodes": {"type": "array", "items": {"type": "string"},
                                                                "minItems": 1}},
                     "required": ["nodes"], "additionalProperties": False}, "annotations": _LOOK},
    {"name": "open_project", "title": "Open a project",
     "description": "Opens a project file (.tela) in a new tab of the window. It asks the person first.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "Absolute path"}},
                     "required": ["path"], "additionalProperties": False}, "annotations": _FILES},
    {"name": "save_project", "title": "Save the project",
     "description": "Saves the open project: in its file, or in `path` (.tela). It asks the person first.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "Absolute path "
                                                                                                "(optional)"}},
                     "additionalProperties": False}, "annotations": _FILES},
    {"name": "export", "title": "Export",
     "description": "Exports what is seen: OBJ or DXF (the geometry of the nodes with their eye on) or PNG (an image "
                    "of the 3D view). It asks the person first.",
     "inputSchema": {"type": "object", "properties": {
         "format": {"type": "string", "enum": ["obj", "dxf", "png"]},
         "path": {"type": "string", "description": "Absolute path ending in .obj, .dxf or .png"}},
         "required": ["format", "path"], "additionalProperties": False}, "annotations": _FILES},
]

#: The tools by name.
BY_NAME = {t["name"]: t for t in TOOLS}
