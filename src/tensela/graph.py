"""The graph: connected nodes that the engine evaluates (step 1.4a).

    g = Graph()
    facade = g.node("Rectangle", "facade", width=20, height=12, plane="elevation")
    panels = g.node("Grid", "panels", rectangle=facade, cell_width=1, cell_height=1)
    g.value(panels)  ->  <Data «panels» rectangle: row 12 × column 20 = 240>

Each input of a node is a fixed value or a connection to another node. The graph keeps the result of each node and,
when something changes, only recomputes the nodes that depend on that change: moving the attractor does not divide
the facade again.
"""

from __future__ import annotations

import keyword
import threading
from pathlib import Path
from typing import Any

from . import images
from .data import Data, ShapeError
from .language import tr
from .nodes import OLD, REQUIRED, NodeType, node_kind


def label_input(name: str) -> str:
    from .values import label_input as label      # here: values uses the nodes
    return label(name)


class Cancelled(Exception):
    """A computation that no longer serves: the graph changed (or a stop was asked) while computing."""


class NodeError(ShapeError):
    """An error computing a node; the message says in which node it happened."""

    def __init__(self, node: Node, message: str):
        super().__init__(tr('In “{node}” ({kind}): {message}').format(node=node.name, kind=tr(node.kind.name),
                                                                       message=message))
        self.node = node


#: The nodes whose points can be drawn with the mouse in the 3D view («Edit curve»).
DRAWABLE = ('Drawn curve', 'NURBS Curve')


def drawable(node) -> bool:
    """Are its points drawn in the view? Yes, if it is one of the DRAWABLE and its points do not come from another node."""
    return node.kind.name in DRAWABLE and not isinstance(node.inputs.get("points"), Node)


def is_automatic_name(node) -> bool:
    """Is its name the one it got on being added («merge 1»), not one of its own?"""
    import re
    return re.fullmatch(re.escape(tr(node.kind.name).lower()) + r" \d+", node.name) is not None


class Node:
    """A node of the graph: a kind, a unique name and its inputs."""

    def __init__(self, graph: Graph, kind: NodeType, name: str):
        self.graph = graph
        self.kind = kind
        self.name = name
        self.inputs: dict[str, Any] = {e.name: e.default for e in kind.inputs}
        self.evaluations = 0  # how many times it was computed (to check the cache)
        self._value: Data | None = None

    @property
    def connections(self) -> dict[str, Node]:
        """The inputs that come from another node."""
        return {n: v for n, v in self.inputs.items() if isinstance(v, Node)}

    def __repr__(self) -> str:
        return f"<Node «{self.name}» ({self.kind.name})>"


class Graph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        # The project's own kinds (the groups, groups.py) and their definitions, by name.
        self.kinds: dict[str, NodeType] = {}
        self.definitions: dict = {}
        # It can be computed in another thread (the window does not freeze): each change bumps the version, and a
        # result computed with an old version is not kept. The lock does both things at once.
        self.version = 0
        self._lock = threading.RLock()
        self._folder = None
        # Called with each node right before it is computed (the process that computes, calculator.py, looks there
        # for a newer request: then it raises Cancelled).
        self.on_node = None

    @property
    def folder(self):
        """The folder of the project: the relative paths of the files it reads (an image) start there."""
        return self._folder

    @folder.setter
    def folder(self, path) -> None:
        path = Path(path) if path is not None else None
        if path == self._folder:
            return
        self._folder = path
        for node in self.nodes.values():            # what reads a file may now read another one
            if any(input_.file for input_ in node.kind.inputs):
                self._invalidate(node)

    # --- Construir -------------------------------------------------------

    def node(self, kind: str, name: str | None = None, **inputs) -> Node:
        """Adds a node. The inputs are fixed values or other nodes."""
        if kind in OLD:  # e.g. «Máximo» → Summarise with operation «maximum» (D10)
            kind, fixed = OLD[kind]
            inputs = {**fixed, **inputs}
        t = self.kinds.get(kind) or node_kind(kind)
        if name is None:
            name = self._free_name(tr(t.name).lower())     # in the language of the interface: «drawn curve 1»
        elif name in self.nodes:
            raise ShapeError(tr('There is already a node called “{name}”.').format(name=name))
        node = Node(self, t, name)
        with self._lock:
            self.nodes[name] = node
            self.version += 1
        try:
            for input_, value in inputs.items():
                self.change(node, input_, value)
        except ShapeError:
            del self.nodes[name]
            raise
        return node

    def change(self, node: Node | str, input_: str, value: Any) -> None:
        """Changes an input: a new fixed value or a connection to another node."""
        node = self._find(node)
        if input_.endswith("_") and keyword.iskeyword(input_[:-1]):     # «from_» (as written in Python) → «from»
            input_ = input_[:-1]
        if not any(e.name == input_ for e in node.kind.inputs):       # an old Spanish name (old project)
            from .legacy_names import input_in_english
            input_, _ = input_in_english(node.kind.name, input_, None)
        e = node.kind.input_(input_)  # a clear error if it does not exist
        if isinstance(value, str) and e.options and value not in e.options:
            from .legacy_names import input_in_english
            _, value = input_in_english(node.kind.name, input_, value, e.options)
        if isinstance(value, Node):
            if value.graph is not self:
                raise ShapeError(tr('“{name}” belongs to another graph.').format(name=value.name))
            if value is node or node in self._ancestors(value):
                raise ShapeError(
                    tr('Connecting “{name}” to “{name2}” would make a loop: “{name2}” already comes before '
                       '“{name}”.').format(name=value.name, name2=node.name)
                )
        node.inputs[input_] = value
        self._invalidate(node)

    def rename(self, node: Node | str, new_: str) -> None:
        """Renames a node (the connections stay; the data take the new name)."""
        node = self._find(node)
        new_ = new_.strip()
        if not new_:
            raise ShapeError(tr('A node name cannot be empty.'))
        if new_ == node.name:
            return
        if new_ in self.nodes:
            raise ShapeError(tr('There is already a node called “{new}”.').format(new=new_))
        old = node.name
        node.name = new_
        self.nodes = {(new_ if n == old else n): v for n, v in self.nodes.items()}  # same order
        self._invalidate(node)  # its data and the messages carry its name

    def rename_level(self, node: Node | str, old: str, new: str) -> list[str]:
        """The level `old` that `node` names is called `new` now: the nodes after it that pick it by its name (an
        «along», the «level» of a Pick or a Split…) are changed too. Gives the names of those changed."""
        start = self._find(node)
        changed, seen, pending = [], set(), list(self._next(start))
        while pending:
            other = pending.pop(0)
            if other.name in seen:
                continue
            seen.add(other.name)
            pending.extend(self._next(other))
            for e in other.kind.inputs:
                value = other.inputs.get(e.name)
                if not e.levels_of or not isinstance(value, str):
                    continue
                parts = [p.strip() for p in value.split(",")]
                if old in parts:
                    self.change(other, e.name, ", ".join(new if p == old else p for p in parts))
                    if other.name not in changed:
                        changed.append(other.name)
        return changed

    def replace(self, node: Node | str, kind: str, automatic_name: bool = True) -> tuple[Node, list[str]]:
        """Changes a node for another of `kind`, in its place: what reached it by inputs of the same name reaches the
        new one, and whoever used it uses the new one. Its name stays (if it was the automatic one of its kind, «merge
        1», it takes the automatic one of the new kind). Gives the new node and the inputs that had something (a wire
        or a value of their own) and have no place in the new one."""
        old = self._find(node)
        new_kind = self.kinds.get(kind) or node_kind(kind)
        name = old.name
        if automatic_name and is_automatic_name(old):
            name = self._free_name(tr(new_kind.name).lower())
        new = Node(self, new_kind, name)
        with self._lock:
            self.nodes = {(name if n == old.name else n): (new if v is old else v) for n, v in self.nodes.items()}
            self.version += 1
        lost = []
        for input_, value in old.inputs.items():
            own = isinstance(value, Node) or value != old.kind.input_(input_).default
            if any(e.name == input_ for e in new_kind.inputs):
                try:
                    self.change(new, input_, value)
                    continue
                except ShapeError:
                    pass
            if own:
                lost.append(input_)
        for other in list(self.nodes.values()):
            for input_, origin in list(other.inputs.items()):
                if origin is old:
                    try:
                        self.change(other, input_, new)
                    except ShapeError:
                        other.inputs[input_] = other.kind.input_(input_).default
                        self._invalidate(other)
        self._invalidate(new)
        return new, lost

    def remove(self, node: Node | str) -> None:
        """Removes a node; it cannot be done if others depend on it."""
        node = self._find(node)
        dependent = [n.name for n in self._next(node)]
        if dependent:
            raise ShapeError(tr('“{name}” cannot be removed: {options} use it.').format(
                                   name=node.name, options=', '.join((f'«{d}»' for d in dependent))))
        with self._lock:
            del self.nodes[node.name]
            self.version += 1

    def stop(self) -> None:
        """Whatever is being computed in another thread is no longer kept (and it stops as soon as the current node ends)."""
        with self._lock:
            self.version += 1

    def compute_all(self, names=None) -> dict[str, Exception]:
        """Computes each node (or those of `names`, with what feeds them); returns the error of those that fail (by
        the node where it starts). If the graph changes meanwhile, it stops with Cancelled."""
        version, errors = self.version, {}
        for name in (list(self.nodes) if names is None else [n for n in names if n in self.nodes]):
            if self.version != version:
                raise Cancelled()
            node = self.nodes.get(name)
            if node is None:
                continue
            try:
                self.value(node)
            except NodeError as e:
                errors.setdefault(e.node.name, e)
            except Cancelled:
                raise
            except Exception as e:                  # an unexpected failure: it is reported, it breaks nothing
                errors.setdefault(name, e)
        return errors

    # --- Calcular --------------------------------------------------------

    def value(self, node: Node | str) -> Data:
        """The result of a node, computing first whatever is needed."""
        node = self._find(node)
        if node._value is not None:
            return node._value

        version = self.version
        arguments = {}
        for input_ in node.kind.inputs:
            v = node.inputs[input_.name]
            if v is REQUIRED:
                raise NodeError(node, tr('the input “{name}” is missing.').format(name=label_input(input_.name)))
            if isinstance(v, Node):
                v = self.value(v)
            if input_.single:
                v = _single(node, input_.name, v)
            arguments[input_.name] = v
        for input_ in node.kind.inputs:          # a level written by hand in the language of the interface
            source = arguments.get(input_.levels_of) if input_.levels_of else None
            if isinstance(source, Data) and isinstance(arguments[input_.name], str) and arguments[input_.name]:
                from .legacy_names import level_name
                arguments[input_.name] = level_name(arguments[input_.name], source.levels)

        if self.on_node is not None:
            self.on_node(node)
        try:
            if self._folder is not None:            # a group computes inside its project: it keeps that folder
                with images.folder(self._folder):
                    result = node.kind.function(**arguments, name=node.name)
            else:
                result = node.kind.function(**arguments, name=node.name)
        except (NodeError, Cancelled):            # Cancelled: «Stop» raises it inside the computation
            raise
        except ShapeError as error:
            raise NodeError(node, str(error)) from error
        except (TypeError, ValueError) as error:
            written = _text_where_a_number_goes(node)
            if written:                                # a notice written for the user, not Python's text
                notice = ShapeError(written)
                notice.__cause__ = error
                raise NodeError(node, written) from notice
            raise NodeError(node, tr('it could not be calculated with these inputs ({error}).').format(
                error=error)) from error
        except MemoryError as error:
            raise NodeError(node, _memory_notice()) from error
        except RecursionError as error:
            raise NodeError(node, tr('the calculation does not finish with these inputs (a size set to 0, or huge?).')) from error
        except RuntimeError as error:
            if "exceed permitted range" in str(error):  # the cuts and offsets of outlines (manifold3d) work with
                notice = ShapeError(tr(                  # whole numbers: huge sizes do not fit in them
                    'the sizes are far too big to cut and offset outlines. Is there an extra digit?'))
                notice.__cause__ = error
                raise NodeError(node, str(notice)) from notice
            raise NodeError(node, _unexpected(error)) from error
        except SystemError as error:
            inside = error.__cause__ or error.__context__
            if isinstance(inside, MemoryError):            # numpy ran out of memory in the middle of an operation
                raise NodeError(node, _memory_notice()) from inside
            raise NodeError(node, _unexpected(error)) from error
        except Exception as error:  # a failure of the program: it must not close the application
            raise NodeError(node, _unexpected(error)) from error

        with self._lock:
            if self.version != version:             # something changed while computing: it does not serve
                raise Cancelled()
            node.evaluations += 1
            node._value = result
        return result

    # --- Auxiliares ------------------------------------------------------

    def _find(self, node: Node | str) -> Node:
        if isinstance(node, Node):
            if self.nodes.get(node.name) is not node:
                raise ShapeError(tr('“{name}” is not in this graph.').format(name=node.name))
            return node
        if node not in self.nodes:
            raise ShapeError(tr('There is no node called “{node}”.').format(node=node))
        return self.nodes[node]

    def _free_name(self, base: str) -> str:
        i = 1
        while f"{base} {i}" in self.nodes:
            i += 1
        return f"{base} {i}"

    def _next(self, node: Node) -> list[Node]:
        """The nodes that use `node` directly."""
        return [n for n in self.nodes.values() if any(c is node for c in n.connections.values())]

    def _ancestors(self, node: Node) -> set[Node]:
        """All the nodes `node` depends on, directly or indirectly."""
        seen: set[Node] = set()
        pending = list(node.connections.values())
        while pending:
            n = pending.pop()
            if n not in seen:
                seen.add(n)
                pending.extend(n.connections.values())
        return seen

    def _invalidate(self, node: Node) -> None:
        """Clears the kept result of `node` and of everything that depends on it."""
        with self._lock:
            self.version += 1
            pending, seen = [node], set()
            while pending:
                n = pending.pop()
                if n not in seen:
                    seen.add(n)
                    n._value = None
                    pending.extend(self._next(n))


def _memory_notice() -> str:
    return tr('the result does not fit in memory: too many elements. Is there an extra digit in a count?')


def _unexpected(error: BaseException) -> str:
    return tr('unexpected program error ({class_}: {error}). This is a bug in Tensela, not in the project.').format(
        class_=type(error).__name__, error=error)


def _text_where_a_number_goes(node: Node) -> str | None:
    """If the computation failed because a number input has letters («abc»), the warning that says so."""
    from .values import read_numbers
    for input_ in node.kind.inputs:
        v = node.inputs[input_.name]
        if (not isinstance(v, str) or not v.strip() or input_.options or input_.levels_of
                or isinstance(input_.default, str) or read_numbers(v) is not None):
            continue
        if isinstance(input_.default, (list, tuple)):  # points drawn in the view or moved in the panel
            return tr('«{input}» expects a list of points (drawn in the view or in the panel), and it has '
                      '«{text}».').format(input=label_input(input_.name), text=v.strip()[:40])
        return tr('«{input}» expects a number (or a list: 1; 2; 3), and it has «{text}».').format(
            input=label_input(input_.name), text=v.strip()[:40])
    return None


def _single(node: Node, input_: str, v: Any) -> Any:
    """A data without levels becomes its plain value; with levels, an error."""
    if not isinstance(v, Data):
        return v
    if v.levels:
        raise NodeError(node, tr('“{input}” must be a single value, and “{name}” arrives with shape {shape}.').format(
                                    input=label_input(input_), name=v._name(), shape=v.shape))
    if v.values.size != 1:                     # a loose geometry (a point, a curve) where a number goes
        what = tr(v.kind.name) if v.kind is not None else tr('a list of values')
        raise NodeError(node, tr('“{input}” must be a single number (or a text), and it receives “{name}”, '
                                   'which is {what}.').format(input=label_input(input_), name=v._name(), what=what))
    value = v.values.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value
