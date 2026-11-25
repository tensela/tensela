"""Saving and opening a project (graph and its presentation) in a file.

JSON text, meant to be read and touched up by hand, in a `.tela` file:

    {
      "tensela": 1,
      "description": "…",
      "nodes": {
        "facade": {"type": "Rectangle", "width": 20, "height": 12, "plane": "elevation"},
        "panels": {"type": "Grid", "rectangle": {"node": "facade"}, "cell_width": 1, "cell_height": 1}
      },
      "export": ["facade", "sun fins"],
      "controls": [
        {"value": "attractor.x", "min": 0, "max": 20, "step": 0.5, "unit": "m", "label": "x"}
      ],
      "view": {
        "facade": {"color": "#c9d6e2", "opacity": 0.6}
      }
    }

- `nodes`: each node with its name as key, its type and only the inputs that do not have the default value. A
  connection is `{"node": "name"}`.
- `export`: the nodes seen in the window and that go to the 3D file.
- `controls` (optional): the values the window offers as a slider, with their range. Without this list, the window
  offers all the fixed numbers.
- `view` (optional): colour and opacity of each exported node.
- `positions` (optional): where each box is in the node editor.

Files written before the move to English (with Spanish keys) are read too: `in_english` turns them into the
keys of now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .data import ShapeError
from .legacy_names import OLD_LEVELS, input_in_english
from .graph import NodeError, Graph, Node
from .language import tr
from .nodes import node_kind
from .values import read_value, unit_of

VERSION = 1

#: The key that says the version of the format. The projects of before the new name (`.json`, from Parametrico) have
#: "parametrico": they are read as they are, and saved again with that key while they stay `.json`, so the program
#: of before still opens them. A `.tela` file has "tensela".
KEY = "tensela"
OLD_KEY = "parametrico"
#: The extension of a project, and the ones that open (the second one, the projects of before).
EXTENSION = ".tela"
EXTENSIONS = (".tela", ".json")


def format_key(filepath) -> str:
    """The key of the format for a file: the one of before in a `.json`, the new one in any other."""
    return OLD_KEY if Path(filepath).suffix.lower() == ".json" else KEY


def format_version(content: dict):
    """The version of the format a file says, with either key."""
    return content.get(KEY, content.get(OLD_KEY))

# Colours of what is seen in 3D when the project says no other (in order).
COLOURS = ["#7d8a96", "#c9d6e2", "#d9534f", "#6b8e4e", "#e0a03a"]


@dataclass
class Control:
    """A fixed value of a node offered as a slider."""

    node: str
    input_: str
    minimum: float
    maximum: float
    step: float = 0.1
    unit: str = ""
    label: str = ""  # what it is called in the window, if the input's name is not enough

    @property
    def key(self) -> str:
        return f"{self.node}.{self.input_}"


@dataclass
class Project:
    graph: Graph
    export: list[str] = field(default_factory=list)
    description: str = ""
    controls: list[Control] = field(default_factory=list)
    view: dict[str, dict] = field(default_factory=dict)
    positions: dict[str, list[float]] = field(default_factory=dict)
    thumbnails: list[str] = field(default_factory=list)   # the cards with the preview open
    notes: list[dict] = field(default_factory=list)       # the annotations of the canvas: texts, arrows, frames
    look: dict = field(default_factory=dict)              # how its 3D view is drawn: {"style": …, "outlines": …}

    def visible_objects(self, computed_only: bool = False) -> list[tuple[str, object, dict]]:
        """(name, data, style) of each visible geometry, with the colours of the 3D view.

        The nodes with an error and those that are not geometry (a number) are skipped. `computed_only`: with the
        results the nodes already have, nothing is computed (the window: its process computes).
        """
        computed = []
        for name in self.export:
            if computed_only:
                if self.graph.nodes[name]._value is not None:
                    computed.append((name, self.graph.nodes[name]._value))
                continue
            try:
                computed.append((name, self.graph.value(name)))
            except NodeError:
                continue
        objects = []
        for i, (name, data) in enumerate(computed):
            if data.kind is None:
                continue
            style_name = dict(self.view.get(name, {}))
            style_name.setdefault("color", COLOURS[i % len(COLOURS)])
            colour_by = self.colour_by(name, data, computed_only)
            if colour_by is not None:
                style_name["_colour_by"] = colour_by
            objects.append((name, data, style_name))
        return objects

    def colour_by(self, name: str, data, computed_only: bool = False) -> tuple | None:
        """If `name` is painted by a value (the *Gradient*): (a number per element, the gradient). None if it has a
        single colour, or if the chosen value does not fit its elements (or has an error, or `computed_only` and it
        has no result yet)."""
        style_name = self.view.get(name, {})
        source = style_name.get("by")
        if not source or source not in self.graph.nodes:
            # A geometry that brings its own values to be painted by (the faces of a Shadow, by how long they are in
            # shadow): painted so, unless it is painted by another node.
            return getattr(data, "paint", None)
        if computed_only:
            value = self.graph.nodes[source]._value
            if value is None:
                return None
        else:
            try:
                value = self.graph.value(source)
            except NodeError:
                return None
        numbers = values_by_element(data, value)
        if numbers is None or not len(numbers):
            return None
        return numbers, style_name.get("gradient", GRADIENT)

    def for_colour_by(self, name: str) -> list[str]:
        """The nodes whose values fit the elements of `name` (one per element, or per group): those that can be chosen
        to paint it by a value."""
        node = self.graph.nodes.get(name)
        data = getattr(node, "_value", None)
        if data is None or data.kind is None:
            return []
        # First the nodes the geometry comes from, from the nearest to the farthest (the Attractor that
        # scales it before the Series of the grid); then, the others.
        nearness, front = {}, [node]
        while front:
            next_ = []
            for n in front:
                for origin in n.inputs.values():
                    if hasattr(origin, "inputs") and origin.name not in nearness:
                        nearness[origin.name] = len(nearness)
                        next_.append(origin)
            front = next_
        candidates = []
        for other in self.graph.nodes.values():
            value = other._value
            if other.name == name or value is None or value.kind is not None or not value.levels:
                continue
            if values_by_element(data, value) is not None:
                candidates.append(other.name)
        return sorted(candidates, key=lambda c: nearness.get(c, len(nearness) + candidates.index(c)))


#: The starting gradient when painting by a value.
GRADIENT = "cool to warm"


def values_by_element(geometry, value) -> "np.ndarray | None":
    """A number for each element drawn of `geometry` (in the order of the view), taken from `value`: its levels
    must be among those of the geometry (with the same size). None if they do not fit."""
    import numpy as np
    from .data import Data, _extend
    if not isinstance(value, Data) or value.kind is not None or value.shape_element != ():
        return None
    if not set(value.levels) <= set(geometry.levels):
        return None
    if any(value.sizes[n] != geometry.sizes[n] for n in value.levels):
        return None
    try:
        numbers = np.asarray(value.values, dtype=float)
    except (TypeError, ValueError):
        return None
    extended = np.broadcast_to(_extend(numbers, value.levels, geometry.levels, geometry.sizes),
                                tuple(geometry.sizes[n] for n in geometry.levels))
    return extended[geometry.mask] if geometry.levels else extended.reshape(1)


def save(graph: Graph | Project, filepath, export: list[str] | None = None, description: str = "",
            controls: list[Control] | None = None, view: dict[str, dict] | None = None,
            positions: dict[str, list[float]] | None = None) -> Path:
    """Writes the graph (or the whole project) in a file: `.tela`, or `.json` for the projects of before."""
    if not isinstance(graph, Project):
        graph = Project(graph, export or [], description, controls or [], view or {}, positions or {})
    filepath = Path(filepath)
    filepath.write_text(to_text(graph, format_key(filepath)), encoding="utf-8")
    return filepath


def to_text(project: Project, key: str = KEY) -> str:
    """The project as the text of the file (it also serves as a "snapshot" for undo)."""
    return _write(a_dict(project, key))


# --- Files written before the move to English: their Spanish keys, to the ones of now ------------------------

_FILE = {"descripcion": "description", "grupos": "groups", "nodos": "nodes", "exportar": "export",
            "controles": "controls", "vista": "view", "posiciones": "positions", "miniaturas": "previews",
            "notas": "notes"}
_CONTROL = {"valor": "value", "paso": "step", "unidad": "unit", "etiqueta": "label"}
_VIEW = {"opacity": "opacity", "analizar": "analyze", "curvatura": "curvature_comb", "numerar": "numbers",
          "bordes": "edges", "segun": "by", "degradado": "gradient"}
_ANALYSE = {"gaussiana": "gaussian", "media": "mean", "cebra": "zebra", "curvatura": "gaussian"}
_GRADIENTS = {"claro a oscuro": "light to dark", "frío a cálido": "cool to warm", "sol": "sun", "vegetal": "foliage"}
_GROUP = {"nodos": "nodes", "entradas": "inputs", "salida": "output", "valores": "values", "posiciones": "positions",
          "ayuda": "help"}


#: The inputs that name a level (also with their Spanish names of before).
LEVEL_INPUTS = {"level", "along", "level_u", "level_v", "new_level", "rows_level", "columns_level", "faces_level",
                "nivel", "sobre", "nivel_u", "nivel_v", "nivel_nuevo", "nivel_filas", "nivel_columnas", "nivel_caras"}


def level_in_english(value):
    """«fila» → «row»; «fila, columna» → «row, column»; a name of one's own («quiebrasol»), as it is."""
    if not isinstance(value, str):
        return value
    parts = [x.strip() for x in value.split(",")]
    if not any(x in OLD_LEVELS for x in parts):
        return value
    return ", ".join(OLD_LEVELS.get(x, x) for x in parts)


def node_in_english(data_items: dict) -> dict:
    """A node as a file keeps it: «tipo» → «type», {"nodo": …} → {"node": …} and the level names the program
    gave before, in English (files of before)."""
    output = {}
    for k, v in data_items.items():
        if k == "tipo":
            k = "type"
        if isinstance(v, dict) and "nodo" in v:
            v = {"node": v["nodo"]}
        if k in LEVEL_INPUTS:
            v = level_in_english(v)
        output[k] = v
    return output


def group_in_english(data_items: dict) -> dict:
    """A group definition of before (Spanish keys) → as it is written now."""
    output = {_GROUP.get(k, k): v for k, v in data_items.items()}
    if isinstance(output.get("nodes"), dict):
        output["nodes"] = {n: node_in_english(d) for n, d in output["nodes"].items()}
    return output


def in_english(content: dict) -> dict:
    """A file written before the move to English (Spanish keys) → as it is written now. The rest, as it is."""
    output = {}
    for key, value in content.items():
        key = _FILE.get(key, key)
        if key == "nodes" and isinstance(value, dict):
            value = {n: node_in_english(d) if isinstance(d, dict) else d for n, d in value.items()}
        elif key == "groups" and isinstance(value, dict):
            value = {n: group_in_english(g) if isinstance(g, dict) else g for n, g in value.items()}
        elif key == "controls" and isinstance(value, list):
            value = [{_CONTROL.get(k, k): v for k, v in c.items()} if isinstance(c, dict) else c for c in value]
        elif key == "view" and isinstance(value, dict):
            value = {n: {_VIEW.get(k, k): v for k, v in e.items()} if isinstance(e, dict) else e
                     for n, e in value.items()}
        output[key] = value
    for e in output.get("view", {}).values():
        if isinstance(e, dict) and e.get("analyze") in _ANALYSE:
            e["analyze"] = _ANALYSE[e["analyze"]]
        if isinstance(e, dict) and e.get("gradient") in _GRADIENTS:
            e["gradient"] = _GRADIENTS[e["gradient"]]
    return output


def a_dict(project: Project, key: str = KEY) -> dict:
    p = project
    graph, export, description, controls, view, positions = (
        p.graph, p.export, p.description, p.controls, p.view, p.positions)

    nodes = {node.name: _node_a_json(node) for node in graph.nodes.values()}

    content: dict = {key: VERSION}
    if description:
        content["description"] = description
    if graph.definitions:
        content["groups"] = {n: d.a_json() for n, d in graph.definitions.items()}
    content["nodes"] = nodes
    if export:
        for name in export:
            graph._find(name)
        content["export"] = list(export)
    if controls:
        content["controls"] = [_control_a_json(c) for c in controls]
    if view:
        content["view"] = view
    if positions:
        content["positions"] = {n: positions[n] for n in graph.nodes if n in positions}
    thumbnails = [n for n in p.thumbnails if n in graph.nodes]
    if thumbnails:
        content["previews"] = thumbnails
    if p.notes:
        content["notes"] = list(p.notes)
    if p.look:
        content["look"] = dict(p.look)

    return content


def missing_kind(data_items: dict):
    """A kind of node of an extension that is not installed (or is off): it keeps its inputs and connections, so the
    project is saved as it was, and says which extension it needs."""
    from .nodes import Input, NodeType
    extension, name = str(data_items["extension"]), str(data_items["type"])

    def function(name=None, **arguments):
        raise ShapeError(tr('this node comes from the extension «{extension}», which is not installed or is off '
                            '(Extensions → Manage extensions…).').format(extension=extension))

    inputs = tuple(Input(k, None) for k in data_items if k not in ("type", "extension"))
    return NodeType(name, "Extensions", inputs, "result", function,
                    tr('A node of the extension «{extension}», which is not here.').format(extension=extension),
                    extension=extension)


def _node_a_json(node: Node) -> dict:
    data_items: dict = {"type": node.kind.name}
    if node.kind.extension:                  # a node of an extension: which one, to say it if it is missing
        data_items["extension"] = node.kind.extension
    for input_ in node.kind.inputs:
        v = node.inputs[input_.name]
        if isinstance(v, Node):
            data_items[input_.name] = {"node": v.name}
        elif v is not input_.default and v != input_.default:
            data_items[input_.name] = list(v) if isinstance(v, tuple) else v
    return data_items


def _read_groups(graph: Graph, groups: dict) -> None:
    """The definitions of the groups, before the nodes (a node can be of a group)."""
    from .groups import Definition, register, uses
    read = {name: Definition.de_json(name, data_items) for name, data_items in groups.items()
            if name not in graph.definitions}
    for name in read:
        if name in uses({**graph.definitions, **read}, name):
            raise ShapeError(tr('The group “{name}” holds itself (perhaps through another group): the file is '
                                'damaged.').format(name=name))
        if read[name].output not in read[name].nodes:
            raise ShapeError(tr('The group “{name}” is incomplete in the file.').format(name=name))
    done = set()

    def put(name, path=()):                  # those it holds inside first: a group whose output is a group needs it
        if name in done or name in path:
            return
        for spec in read[name].nodes.values():
            if spec.get("type") in read:
                put(spec["type"], (*path, name))
        done.add(name)
        register(graph, read[name])
    for name in read:
        put(name)


def _groups_used(graph: Graph, kinds) -> dict:
    """The definitions of those kinds (and of the groups they use inside), to carry them with the nodes."""
    used, pending = {}, [t for t in kinds if t in graph.definitions]
    while pending:
        t = pending.pop()
        if t in used:
            continue
        used[t] = graph.definitions[t].a_json()
        pending.extend(d["type"] for d in graph.definitions[t].nodes.values() if d["type"] in graph.definitions)
    return used


# --- Copy and paste nodes ---------------------------------------------------------------

def fragment(graph: Graph, names, positions: dict | None = None) -> dict:
    """Some nodes to copy: as in the file, with their values, connections and positions."""
    positions = positions or {}
    frag = {KEY: VERSION,
            "nodes": {n: _node_a_json(graph.nodes[n]) for n in names if n in graph.nodes},
            "positions": {n: list(positions[n]) for n in names if n in positions}}
    groups = _groups_used(graph, {d["type"] for d in frag["nodes"].values()})
    if groups:
        frag["groups"] = groups                      # to paste them in another project
    return frag


def _copy_name(graph: Graph, name: str, taken: set[str]) -> str:
    """«facade» → «facade» if it is free; if not, «facade 2», «facade 3»…; «box 4» → «box 5»;
    «edge a» → «edge b»."""
    if name not in graph.nodes and name not in taken:
        return name
    base, _, number = name.rpartition(" ")
    free = lambda n: n not in graph.nodes and n not in taken
    if base and len(number) == 1 and number.isalpha() and number.lower() in "abcdefghijklmnopqrstuvwxyz":
        # «edge a» → «edge b» (and «facade A» → «facade B»): the next letter, the first free one.
        letters = "abcdefghijklmnopqrstuvwxyz"
        for font in letters[letters.index(number.lower()) + 1:]:
            candidate = f"{base} {font.upper() if number.isupper() else font}"
            if free(candidate):
                return candidate
    if not (base and number.isdigit()):
        base, number = name, "1"
    i = int(number) + 1
    while f"{base} {i}" in graph.nodes or f"{base} {i}" in taken:
        i += 1
    return f"{base} {i}"


def paste_fragment(graph: Graph, frag: dict, with_inputs: bool = False) -> dict[str, str]:
    """Adds the nodes of a `frag` to the graph, with free names. Returns {copied name: new}.

    The connections between the copied nodes are remade between the copies. Those that arrive from outside are kept
    with `with_inputs` (duplicate, in the same project) if that node exists; if not, the input keeps its default value.
    """
    if isinstance(frag, dict):
        frag = in_english(frag)
    if not isinstance(frag, dict) or not isinstance(frag.get("nodes"), dict):
        raise ShapeError(tr('What was copied is not Tensela nodes.'))
    _read_groups(graph, frag.get("groups", {}))       # the groups they bring (if there already are some, those of here are used)
    new: dict[str, str] = {}
    for name in frag["nodes"]:
        new[name] = _copy_name(graph, name, set(new.values()))
    connections = []
    for name, data_items in frag["nodes"].items():
        fixed = {}
        for input_, value in data_items.items():
            if input_ == "type":
                continue
            if isinstance(value, dict) and "node" in value:
                connections.append((new[name], input_, value["node"]))
            else:
                fixed[input_] = value
        graph.node(data_items["type"], new[name], **fixed)
    for name, input_, origin in connections:
        if origin in new:
            graph.change(name, input_, graph.nodes[new[origin]])
        elif with_inputs and origin in graph.nodes:
            graph.change(name, input_, graph.nodes[origin])
    return new


#: Inputs that changed name or meaning: (node type, old input) → f(value) gives the (input, value) of now.
OLD_INPUTS = {
    ("Drawn curve", "suave"): lambda v: ("degree", 3 if v is True or v == "sí" else 1),
    ("Points on curve", "modo"): lambda v: ("mode", 'distance' if v == "metros" else v),
    ("Points on curve", "mode"): lambda v: ("mode", 'distance' if v == "metros" else v),
    ("Filter", "invertir"): lambda v: ("keep", v if isinstance(v, dict)
                                       else ("those that don't" if v is True or v == "sí" else 'those that do')),
    ("Text", "letter"): lambda v: ("lettering", v),
    ("Numbers and sheets", "letter"): lambda v: ("lettering", v),
}


def open_(filepath) -> Project:
    """Reads a project from a JSON file."""
    filepath = Path(filepath)
    try:
        content = json.loads(filepath.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ShapeError(tr('The file “{path}” does not exist.').format(path=filepath)) from None
    except json.JSONDecodeError as error:
        raise ShapeError(tr('“{file}” is not a valid file: line {line}, column {column}.').format(
                               file=filepath.name, line=error.lineno, column=error.colno)) from None
    except (OSError, UnicodeDecodeError, RecursionError) as error:   # a folder, no permission, not text, too nested
        raise ShapeError(tr('“{file}” could not be read ({error}).').format(file=filepath.name,
                                                                          error=type(error).__name__)) from None

    project = from__dict(content, filepath.name)
    project.graph.folder = filepath.parent
    return project


def from__text(text: str) -> Project:
    """The opposite of `to_text`."""
    try:
        content = json.loads(text)
    except (ValueError, RecursionError) as error:
        raise ShapeError(tr('“{file}” could not be read ({error}).').format(file=tr("the project"),
                                                                          error=type(error).__name__)) from None
    return from__dict(content)


def from__dict(content, name: str = "") -> Project:
    """A project from what its file says. A file that is damaged (or made to break the program) gives a clear
    notice, never an error of Python."""
    try:
        return _from__dict(content, name)
    except ShapeError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, RecursionError) as error:
        raise ShapeError(tr('“{file}” is damaged: part of it could not be read ({error}).').format(
            file=name or tr("the project"), error=f"{type(error).__name__}: {error}"[:120])) from None


def _from__dict(content, name: str = "") -> Project:
    name = name or tr("the project")
    if isinstance(content, dict):
        content = in_english(content)
    if not isinstance(content, dict) or "nodes" not in content:
        raise ShapeError(tr('“{name}” is not a Tensela graph (“nodes” is missing).').format(name=name))
    version = format_version(content)
    if version != VERSION:
        raise ShapeError(tr('“{name}” uses version {version} of the format; this version reads {current}.').format(
                               name=name, version=version, current=VERSION))

    graph = Graph()
    _read_groups(graph, content.get("groups", {}))
    connections: list[tuple[str, str, str]] = []
    # First all the nodes with their fixed values; then the connections,
    # so the order of the nodes in the file does not matter.
    for name, data_items in content["nodes"].items():
        if "type" not in data_items:
            raise ShapeError(tr('Node “{name}” is missing its “type”.').format(name=name))
        kind = graph.kinds.get(data_items["type"])
        if kind is None:
            try:
                kind = node_kind(data_items["type"])
            except ShapeError:
                if not data_items.get("extension"):
                    raise
                kind = missing_kind(data_items)      # its extension is not here: kept, not lost on saving
                graph.kinds[kind.name] = kind
        fixed = {}
        for input_, value in data_items.items():
            if input_ in ("type", "extension"):
                continue
            if (kind.name, input_) in OLD_INPUTS:   # a file of before: to its input of now
                input_, value = OLD_INPUTS[kind.name, input_](value)
            if not any(e.name == input_ for e in kind.inputs):      # an old Spanish name
                input_, _ = input_in_english(kind.name, input_, None)
            kind.input_(input_)  # a clear error if it does not exist
            if isinstance(value, dict) and "node" in value:
                connections.append((name, input_, value["node"]))
            else:
                fixed[input_] = value
        graph.node(data_items["type"], name, **fixed)

    for name, input_, origin in connections:
        if origin not in graph.nodes:
            raise ShapeError(tr('“{name}” connects to “{origin}”, which does not exist.').format(
                                   name=name, origin=origin))
        graph.change(name, input_, graph.nodes[origin])

    export = list(content.get("export", []))
    for name in export:
        if name not in graph.nodes:
            raise ShapeError(tr('Exporting “{name}” was requested, but it does not exist.').format(name=name))

    controls = [_control_de_json(graph, c) for c in content.get("controls", [])]

    view = dict(content.get("view", {}))
    for name in view:
        if name not in graph.nodes:
            raise ShapeError(tr('The view refers to “{name}”, which does not exist.').format(name=name))

    positions = dict(content.get("positions", {}))
    for name in list(positions):
        if name not in graph.nodes:  # a box of a node that no longer exists: forgotten
            del positions[name]

    thumbnails = [n for n in content.get("previews", []) if n in graph.nodes]
    notes = [dict(n) for n in content.get("notes", []) if isinstance(n, dict) and ("type" in n or "tipo" in n)]
    look = content.get("look", {})
    return Project(graph, export, content.get("description", ""), controls, view, positions, thumbnails,
                    notes, dict(look) if isinstance(look, dict) else {})


def numbers_items(v) -> list[float] | None:
    """The numbers of a list written by hand («10; 10; 14; 10» or [10, 10, 14, 10]); None if it is not one."""
    if isinstance(v, str) and ";" in v:
        try:
            v = read_value(f"({v.strip().strip('()')})")
        except ShapeError:
            return None
    if not isinstance(v, (list, tuple)) or not v:
        return None
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return None
    return list(v)


def slidable(v) -> bool:
    """Whether a fixed value can be a slider: a number, or a list of numbers (one slider per value)."""
    return (isinstance(v, (int, float)) and not isinstance(v, bool)) or numbers_items(v) is not None


def control_for(graph: Graph, node: str, input_: str) -> Control:
    """A slider for a numeric fixed value, with a reasonable range around its value.

    For a list of numbers, a range that serves all its values."""
    n = graph.nodes[node]
    v = n.inputs[input_]
    list_ = numbers_items(v)
    if list_ is not None:
        v = max(list_, key=abs)
    unit = unit_of(input_)
    if unit == "°":  # a rotation: from −180° to 180°, degree by degree
        return Control(node, input_, -180, 180, 1, unit)
    import math
    av = abs(float(v))
    # The range: up to twice the value (a thickness of 0.018 m: from 0 to 0.036; a length of 3: from 0 to 6).
    reach = 2 * av if 0 < av < 0.5 else max(1.0, 2 * av)
    minimum = 0.0 if v >= 0 else -reach
    # The step, by the size of the value: an integer (60 ribs) one by one; a small one, fine (0.018 → 0.001).
    if float(v).is_integer() and av >= 2:
        step = 1.0
    elif av == 0:
        step = 0.1
    else:
        step = max(10.0 ** (math.floor(math.log10(av)) - 1), 0.0001)
    return Control(node, input_, minimum, reach, step, unit)


def automatic_controls(graph: Graph) -> list[Control]:
    """A control for each fixed number of the graph, with a reasonable range.

    For when the file does not say what to control.
    """
    controls = []
    for node in graph.nodes.values():
        for input_ in node.kind.inputs:
            v = node.inputs[input_.name]
            if not slidable(v):
                continue
            controls.append(control_for(graph, node.name, input_.name))
    return controls


def _control_de_json(graph: Graph, c: dict) -> Control:
    key = c.get("value", "")
    if "." not in key:
        raise ShapeError(tr('A control must say “value”: "node.input" (it says “{key}”).').format(key=key))
    node, input_ = key.rsplit(".", 1)
    if node not in graph.nodes:
        raise ShapeError(tr('Control “{key}” refers to “{node}”, which does not exist.').format(
                               key=key, node=node))
    n = graph.nodes[node]
    if not any(e.name == input_ for e in n.kind.inputs):            # an old Spanish name
        input_, _ = input_in_english(n.kind.name, input_, None)
    n.kind.input_(input_)  # a clear error if it does not exist
    if isinstance(n.inputs[input_], Node):
        raise ShapeError(tr('“{key}” comes from another node; only a fixed value can be a control.').format(
                               key=key))
    try:
        return Control(node, input_, float(c["min"]), float(c["max"]),
                       float(c.get("step", 0.1)), str(c.get("unit", "")), str(c.get("label", "")))
    except KeyError as missing:
        raise ShapeError(tr('Control “{key}” is missing “{args}”.').format(
                               key=key, args=missing.args[0])) from None


def _control_a_json(c: Control) -> dict:
    def number(x: float):
        return int(x) if float(x).is_integer() else x

    data_items = {"value": c.key, "min": number(c.minimum), "max": number(c.maximum), "step": number(c.step)}
    if c.unit:
        data_items["unit"] = c.unit
    if c.label:
        data_items["label"] = c.label
    return data_items


def _write(content: dict) -> str:
    """JSON with one node (or one control) per line: it reads at a glance and the changes show in git."""
    def a_line(x):
        return json.dumps(x, ensure_ascii=False)

    lines = ["{"]
    keys = list(content)
    for i, key in enumerate(keys):
        comma = "," if i < len(keys) - 1 else ""
        value = content[key]
        if key in ("nodes", "view", "positions"):
            lines.append(f"  {a_line(key)}: {{")
            elements = list(value.items())
            for j, (name, data_items) in enumerate(elements):
                end = "," if j < len(elements) - 1 else ""
                lines.append(f"    {a_line(name)}: {a_line(data_items)}{end}")
            lines.append("  }" + comma)
        elif key == "controls":
            lines.append(f"  {a_line(key)}: [")
            for j, data_items in enumerate(value):
                end = "," if j < len(value) - 1 else ""
                lines.append(f"    {a_line(data_items)}{end}")
            lines.append("  ]" + comma)
        else:
            lines.append(f"  {a_line(key)}: {a_line(value)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"
