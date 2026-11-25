"""Groups of nodes (Delivery 6): several nodes turned into one, like a function.

A group is defined once per project (`Definition`) and used like any other kind of node: its **inputs** are what
reached the grouped nodes from outside (one per outside node: «facade», «attractor») and its **output** is what the
inside node used outside gives. Inside it is a graph like any other; when computed, it receives its inputs and
returns its output, with the same cache as the rest.

A group can give **several results** (two inside nodes used outside): its card gives the first one and carries the
others along (`Data.results`); a «Group result» node takes each of the others, without computing the group again. A
group can also hold other groups, as deep as needed (but never itself, nor a group that holds it).

    definition, node = group(graph, ["panels", "distances", "sun fins"], "sun fin")
    ungroup(graph, node.name)               # back to the loose nodes

In the file, the definitions go in «groups» and each group node carries its name as «type» (project_file.py).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .data import Data, ShapeError
from .graph import Graph, Node, NodeError
from .language import tr
from .nodes import REQUIRED, Input, NodeType

CATEGORY = 'Groups'


@dataclass
class Definition:
    """A group: its inside nodes (as in the file), its inputs and its output."""

    name: str                                   # the kind: «sun fin»
    nodes: dict[str, dict]                        # {name: {"type": …, input: value or {"node": …}}}
    inputs: dict[str, list[tuple[str, str]]]    # {group input: [(inside node, its input), …]}
    output: str                                   # the inside node whose result comes out
    positions: dict[str, list[float]] = field(default_factory=dict)
    help: str = ""
    # The inputs with a value of their own (those that had a slider): {group input: value}.
    values: dict[str, object] = field(default_factory=dict)
    # With several results: {result: the inside node that gives it}, in order (empty: a single one, `output`).
    outputs: dict[str, str] = field(default_factory=dict)
    # On grouping: {(node, input) inside: group input} of the promoted ones (not saved).
    promoted: dict = field(default_factory=dict, repr=False, compare=False)
    # On grouping with several results: {result: the Group result node that takes it outside} (not saved).
    takers: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def results(self) -> dict[str, str]:
        """{result: inside node}: those of `outputs`, or the single one (named after its node)."""
        return self.outputs or {self.output: self.output}

    def a_json(self) -> dict:
        data_items = {"nodes": self.nodes, "inputs": {e: [list(d) for d in targets] for e, targets in self.inputs.items()},
                 "output": self.output}
        if self.values:
            data_items["values"] = self.values
        if self.positions:
            data_items["positions"] = self.positions
        if self.help:
            data_items["help"] = self.help
        if self.outputs:
            data_items["outputs"] = self.outputs
        return data_items

    @classmethod
    def de_json(cls, name: str, data_items: dict) -> Definition:
        from .project_file import group_in_english
        try:
            data_items = group_in_english(data_items)                 # (a group written before: Spanish keys)
            inputs = {e: [tuple(d) for d in targets] for e, targets in data_items.get("inputs", {}).items()}
            return cls(name, dict(data_items["nodes"]), inputs, data_items["output"], dict(data_items.get("positions", {})),
                       data_items.get("help", ""), dict(data_items.get("values", {})),
                       dict(data_items.get("outputs", {})))
        except (KeyError, TypeError, ValueError):
            raise ShapeError(tr('The group “{name}” is incomplete in the file.').format(name=name)) from None


def _build(g: Graph, nodes: dict[str, dict]) -> None:
    """The nodes of a definition, into `g`. An input the kind no longer has (a group inside lost one of its inputs
    while edited) is left out instead of failing."""
    connections = []
    for name, data_items in nodes.items():
        node = g.node(data_items["type"], name)
        known = {e.name for e in node.kind.inputs}
        for input_, value in data_items.items():
            if input_ == "type" or input_ not in known and input_.rstrip("_") not in known:
                continue
            if isinstance(value, dict) and "node" in value:
                connections.append((name, input_, value["node"]))
            else:
                g.change(name, input_, value)
    for name, input_, origin in connections:
        if origin in g.nodes:
            g.change(name, input_, g.nodes[origin])


def _inside_graph(definition: Definition, kinds: dict[str, NodeType]) -> Graph:
    """The inside graph, built once (with the project's groups: a group can use another)."""
    g = Graph()
    g.kinds = kinds
    _build(g, definition.nodes)
    return g


def uses(definitions: dict, kind: str) -> set[str]:
    """The groups `kind` holds inside, at any depth."""
    found, pending = set(), [kind]
    while pending:
        definition = definitions.get(pending.pop())
        if definition is None:
            continue
        for spec in definition.nodes.values():
            if spec.get("type") in definitions and spec["type"] not in found:
                found.add(spec["type"])
                pending.append(spec["type"])
    return found


#: What a repeated group keeps: every step (with the start first), or only the last one.
KEEP = ('last step', 'every step')
#: The inputs every group has to repeat itself (a loop): they are not inputs of what is inside.
REPEAT_INPUTS = ('repeat', 'back_into', 'keep', 'step_level')
#: More repetitions than this are almost always a mistake (and each one computes the whole group).
MAX_REPEAT = 1000
#: An input of the group with one of these names receives the number of each step (0, 1, 2…).
STEP_NAMES = ('step', 'paso')
#: The node that takes another result of a group that gives several.
RESULT = 'Group result'


def describe(definition: Definition, output: str = "") -> str:
    """What a group does when nobody wrote it: what it takes, what it gives and the nodes inside («Takes: centres and
    attractor. Gives: value. Inside: Distance, Summarise, Remap.»), as a comment says what a function does."""
    from .values import label_input
    inside = list(dict.fromkeys(tr(spec.get("type", "")) for spec in definition.nodes.values()))
    takes = [label_input(e) for e in definition.inputs]
    gives = tr(output) if output else label_input(definition.output)
    if definition.outputs:                        # several results: their names
        gives = ", ".join(definition.outputs)
    if len(takes) > 1:
        takes_text = tr('{some} and {last}').format(some=", ".join(takes[:-1]), last=takes[-1])
    else:
        takes_text = "".join(takes)
    parts = [tr('Takes: {inputs}.').format(inputs=takes_text)] if takes else []
    parts.append(tr('Gives: {output}.').format(output=gives))
    parts.append(tr('Inside: {nodes}.').format(nodes=", ".join(inside)))
    return " ".join(parts)


def group_kind(definition: Definition, kinds: dict[str, NodeType]) -> NodeType:
    """The node kind of a group: it receives its inputs, computes inside and gives its output.

    A group can **repeat** itself (a loop): what comes out goes back in through one of its inputs, so many times. The
    first time it receives what is connected (the start); then, its own result. It gives the last step, or every step
    along a new level.

    `kinds`: the project's groups (shared: if one is added later, it is found too).
    """
    state: dict = {}                               # the inside graph, built at the first computation
    can_repeat = bool(definition.inputs) and not set(REPEAT_INPUTS) & set(definition.inputs)

    results = definition.results

    def once(inputs: dict) -> Data:
        g = state.get("grafo")
        if g is None:
            g = state["grafo"] = _inside_graph(definition, kinds)
        for input_, targets in definition.inputs.items():
            for node, its in targets:
                if g.nodes[node].inputs[its] is not inputs[input_]:
                    g.change(node, its, inputs[input_])
        return g.value(definition.output)

    def with_results(result: Data, name) -> Data:
        result = copy.copy(result)
        result.name = name                        # the result carries the group's name, not the inside one
        if len(results) > 1:                      # the others ride along, for the Group result nodes
            g = state["grafo"]
            result.results = {r: g.value(n) for r, n in results.items()}
        return result

    def compute(name: str | None = None, **inputs):
        times, keep = inputs.pop("repeat", 1), inputs.pop("keep", KEEP[0])
        back, level = inputs.pop("back_into", None), inputs.pop("step_level", None) or "step"
        if not can_repeat or (_whole(times) == 1 and keep != 'every step'):
            return with_results(once(inputs), name)
        times = _whole(times)
        if not 0 <= times <= MAX_REPEAT:
            raise ShapeError(tr('A group repeats from 0 to {maximum} times (it says {times}).').format(
                maximum=MAX_REPEAT, times=times))
        if keep not in KEEP:
            raise ShapeError(tr('A repeated group keeps: {options}.').format(options=", ".join(tr(k) for k in KEEP)))
        back = back or next(iter(definition.inputs))
        if back not in definition.inputs:
            raise ShapeError(tr('“{back}” is not an input of the group (it has: {options}).').format(
                back=back, options=", ".join(definition.inputs)))
        start = inputs[back]
        if not isinstance(start, Data):
            start = Data.value(start)
        counter = next((e for e in definition.inputs if e.lower() in STEP_NAMES and e != back), None)
        steps, current = [start], start
        for k in range(times):
            if counter is not None:
                inputs[counter] = Data.value(k)
            inputs[back] = current
            try:
                current = once(inputs)
            except (ShapeError, NodeError) as error:
                if k == 0:
                    raise
                raise ShapeError(tr('At step {k}, what came out of the previous step could not go back in through '
                                    '“{back}”: {error}').format(k=k + 1, back=back, error=error)) from error
            steps.append(current)
        if keep == 'last step':
            return with_results(current, name)
        from .data import stack
        if len(steps) > 1 and not start.levels and len(steps[1].levels) == 1 and not start.variables:
            # A single thing at the start and a list from then on (one line, then four segments): the start counts as
            # a list of one.
            steps[0] = start = Data(start.values[None], steps[1].levels, start.name, kind=start.kind)
        if len(steps) > 1 and (start.kind != steps[1].kind or start.levels != steps[1].levels) \
                and not _stackable(start, steps[1]):
            steps = steps[1:]                     # the start is another kind of thing: only what the group gives
        return stack(steps, level, name)

    output = definition.nodes[definition.output]["type"]
    kind_output = kinds[output].output if output in kinds else _kind(output).output
    help = definition.help or describe(definition, kind_output)
    inputs = tuple(Input(e, definition.values.get(e, REQUIRED)) for e in definition.inputs)
    if can_repeat:
        repeats = lambda e: e.get("repeat") != 1 or e.get("keep") == 'every step'   # noqa: E731
        inputs += (
            Input('repeat', 1, single=True,
                  help='how many times the group runs, one after another: each time, what comes out goes back in '
                       '(a loop). 1: just once, as usual'),
            Input('back_into', None, single=True, options=tuple(definition.inputs), visible_if=repeats,
                  help='the input through which the result goes back in; empty: the first one'),
            Input('keep', KEEP[0], single=True, options=KEEP, visible_if=repeats,
                  help='last step: only the final result · every step: all of them along a new level, with the '
                       'start first'),
            Input('step_level', 'step', single=True, visible_if=lambda e: e.get("keep") == 'every step',
                  help='name of the level of the steps'),
        )
    return NodeType(definition.name, CATEGORY, inputs, kind_output, compute, help)


def _whole(value) -> int:
    """The number of repetitions, as a whole number (a slider can give 3.0)."""
    import numpy as np
    v = value.values if isinstance(value, Data) else value
    return int(round(float(np.asarray(v, dtype=float).reshape(-1)[0])))


def _stackable(a: Data, b: Data) -> bool:
    """Can the start go with the steps (the same kind of thing)?"""
    from .data import stack
    try:
        stack([a, b], "_")
        return True
    except ShapeError:
        return False


def _kind(name: str) -> NodeType:
    from .nodes import OLD, node_kind
    return node_kind(OLD[name][0] if name in OLD else name)


def register(graph: Graph, definition: Definition) -> NodeType:
    """Puts the group among the graph's kinds (and its project's)."""
    from .nodes import CATALOG
    from .legacy_names import NODES
    if definition.name in CATALOG or definition.name in NODES:      # (also an old name)
        raise ShapeError(tr('“{name}” is already the name of a Tensela node: choose another one for the group.').format(
                               name=definition.name))
    kind = group_kind(definition, graph.kinds)
    graph.kinds[definition.name] = kind
    graph.definitions[definition.name] = definition
    return kind


# --- Group and ungroup ------------------------------------------------------------------------

def _node_a_json(node: Node, inside: set[str]) -> tuple[dict, list[tuple[str, str]]]:
    """A node as in the file; the connections that come from outside are removed and returned apart."""
    data_items: dict = {"type": node.kind.name}
    from_outside = []
    for input_ in node.kind.inputs:
        v = node.inputs[input_.name]
        if isinstance(v, Node):
            if v.name in inside:
                data_items[input_.name] = {"node": v.name}
            else:
                from_outside.append((input_.name, v.name))
        elif v is not input_.default and v != input_.default:
            data_items[input_.name] = list(v) if isinstance(v, tuple) else v
    return data_items, from_outside


def group(graph: Graph, names, kind: str, export: list[str] | None = None,
            positions: dict[str, list[float]] | None = None, help: str = "",
            promote=()) -> tuple[Definition, Node]:
    """Turns the nodes `names` into a group node of the new kind `kind`.

    What reached them from outside becomes inputs of the group; what of them was used outside (or seen in 3D,
    `export`), its output. If several of them were used outside, the group gives several results: the group node
    gives the first, and a Group result node takes the place of each other one (`definition.takers`). `export` is
    corrected in place (the group is seen if its output was seen). `promote`: (node, input) inside with a fixed
    value that become inputs of the group, with their value (those that had a slider); `definition.promoted` says
    what they are called.
    """
    inside = [n for n in graph.nodes if n in set(names)]          # in the order of the graph
    if len(inside) < 2:
        raise ShapeError(tr('To group, select two or more nodes.'))
    kind = kind.strip()
    if not kind:
        raise ShapeError(tr('The group needs a name.'))
    if kind in graph.kinds or kind in graph.definitions:          # (also one around, when grouping inside a group)
        raise ShapeError(tr('There is already a group called “{name}”.').format(name=kind))
    if any(graph.nodes[n].kind.name in ("Group input", "Group output") for n in inside):
        raise ShapeError(tr('The Group input and Group output nodes stay where they are: group the others.'))
    set_ = set(inside)
    export = export if export is not None else []

    # The output: the inside node the outside ones use (or that is seen in 3D); if none, the last one.
    used_outside = [n for n in inside if any(c.name == n for o in graph.nodes.values() if o.name not in set_
                                             for c in o.connections.values())]
    # Seen in 3D counts only for a node the others inside do not use: new nodes turn their eye on by themselves, so
    # «Scale» and then «Rotate», both seen, give what «Rotate» gives (the step in between is not a second result).
    used_inside = {c.name for n in inside for c in graph.nodes[n].connections.values()}
    seen = [n for n in inside if n in export and n not in used_inside]
    candidates = list(dict.fromkeys(used_outside + seen))
    if candidates:
        output = candidates[0]
    else:
        final = [n for n in inside if not any(c.name == n for o in inside for c in graph.nodes[o].connections.values())]
        output = final[-1]

    # The inside nodes, and their inputs that come from outside: one group input per outside node.
    nodes, inputs, origins = {}, {}, {}
    for n in inside:
        data_items, from_outside = _node_a_json(graph.nodes[n], set_)
        nodes[n] = data_items
        for input_, origin in from_outside:
            inputs.setdefault(origin, []).append((n, input_))
            origins[origin] = graph.nodes[origin]
    # The promoted fixed values: one group input each, with its value.
    values, promoted = {}, {}
    for from_inside, its in promote:
        if from_inside not in set_ or isinstance(graph.nodes[from_inside].inputs.get(its), Node):
            continue
        name = its if its not in inputs and its not in values else f"{its} {from_inside}"
        inputs[name] = [(from_inside, its)]
        values[name] = graph.nodes[from_inside].inputs[its]
        promoted[(from_inside, its)] = name
    positions = positions or {}
    definition = Definition(kind, nodes, inputs, output, {n: list(positions[n]) for n in inside if n in positions},
                            help, values, outputs={c: c for c in candidates} if len(candidates) > 1 else {},
                            promoted=promoted)
    register(graph, definition)

    # The group node: it takes the place of its output (the outside ones that used it, use the group). Each other
    # result, a Group result node with the name of the inside node it replaces: its wires, its eye and its colour
    # outside stay as they were.
    name_node = graph._free_name(kind)
    node = graph.node(kind, name_node, **{e: origins[e] for e in inputs if e in origins},
                      **{e: v for e, v in values.items()})
    users = {r: [(o, i) for o in graph.nodes.values() if o.name not in set_ and o is not node
                 for i, c in o.connections.items() if c.name == r] for r in definition.results}
    for n in inside:
        del graph.nodes[n]
    takers = {output: node}
    for result in list(definition.results)[1:]:
        takers[result] = graph.node(RESULT, result, group=node, gives=result)
    for result, taker in takers.items():
        for other, input_ in users[result]:
            graph.change(other, input_, taker)
    if output in export:
        export[export.index(output)] = name_node
    export[:] = [n for n in export if n not in set_ or n in takers]
    definition.takers = {r: t.name for r, t in takers.items() if t is not node}
    return definition, node


def takers(graph: Graph, name: str) -> list[Node]:
    """The Group result nodes that take the other results of the group node `name`."""
    node = graph._find(name)
    return [o for o in graph.nodes.values() if o.kind.name == RESULT and o.inputs.get("group") is node]


def ungroup(graph: Graph, name: str, export: list[str] | None = None, taken: dict | None = None) -> dict[str, str]:
    """Puts the inside nodes of a group node back, loose. Returns {inside name: new name}.

    Its Group result nodes go too: what used each of them uses its inside node (`taken`, if given, receives
    {Group result: inside node}). The definition stays in the project (there may be more nodes of that group).
    """
    from .project_file import paste_fragment
    node = graph._find(name)
    definition = graph.definitions.get(node.kind.name)
    if definition is None:
        raise ShapeError(tr('“{name}” is not a group.').format(name=node.name))
    cards = [(node, definition.output)] + [(t, t.inputs.get("gives")) for t in takers(graph, node.name)]
    names = {card.name for card, _ in cards}
    users = {card.name: [(o, i) for o in graph.nodes.values() if o.name not in names
                         for i, c in o.connections.items() if c is card] for card, _ in cards}
    for card, _ in cards[1:]:                     # first out: their names (those of the inside nodes) are free again
        del graph.nodes[card.name]
    new = paste_fragment(graph, {"nodes": definition.nodes})
    for input_, targets in definition.inputs.items():
        origin = node.inputs[input_]
        if origin is REQUIRED:
            continue
        for from_inside, its in targets:          # a wire from outside, or the value of a promoted input
            graph.change(new[from_inside], its, origin)
    results = definition.results
    for card, result in cards:
        output = graph.nodes[new[results.get(result, definition.output)]]
        for other, input_ in users[card.name]:
            graph.change(other, input_, output)
        if export is not None and card.name in export:
            if output.name in export:
                export.remove(card.name)
            else:
                export[export.index(card.name)] = output.name
    del graph.nodes[node.name]
    if taken is not None:
        taken.update({card.name: new[results.get(result, definition.output)] for card, result in cards[1:]})
    return new


# --- In a project: what is seen, the sliders, the colours and the boxes ------------------------

def group_in_project(project, names, kind: str, help: str = "") -> Node:
    """`group`, and also: the sliders of the inside nodes move the group's inputs; the colour of the output goes to
    the group; the group's box goes where the inside ones were."""
    inside = set(names)
    promote = [(c.node, c.input_) for c in project.controls if c.node in inside]
    definition, node = group(project.graph, names, kind, project.export, project.positions, help, promote)
    for c in project.controls:
        if (c.node, c.input_) in definition.promoted:
            c.node, c.input_ = node.name, definition.promoted[(c.node, c.input_)]
    project.controls = [c for c in project.controls if c.node not in inside]
    if definition.output in project.view:
        project.view[node.name] = project.view[definition.output]
    gone = inside - set(definition.takers.values())      # a Group result keeps what its inside node had
    project.view = {n: v for n, v in project.view.items() if n not in gone}
    project.positions = boxes_grouped(project.positions, names, definition, node.name)
    project.thumbnails = [n for n in project.thumbnails if n not in gone]
    return node


def boxes_grouped(positions: dict, names, definition: Definition, node: str) -> dict:
    """Where the boxes go after grouping: the group's where the grouped ones were; its Group result nodes beside it,
    one under the other."""
    positions = dict(positions)
    boxes = [positions[n] for n in names if n in positions]
    if boxes:
        positions[node] = [round(sum(p[0] for p in boxes) / len(boxes)), round(sum(p[1] for p in boxes) / len(boxes))]
        for k, taker in enumerate(definition.takers.values()):
            positions[taker] = [positions[node][0] + 260, positions[node][1] + 90 * (k + 1)]
    gone = set(names) - set(definition.takers.values())
    return {n: p for n, p in positions.items() if n not in gone}


def boxes_ungrouped(positions: dict, name: str, definition: Definition, new: dict, taken: dict) -> dict:
    """Where the boxes go after ungrouping: the inside ones as they were inside, around where the group was."""
    positions = {n: p for n, p in positions.items() if n not in taken}
    where = positions.pop(name, None)
    # Only the boxes of the inside nodes: the definition also keeps where its inputs and its output were drawn
    # inside the group («centres», «output»…), which are not nodes and have no place outside.
    boxes = {n: p for n, p in (definition.positions or {}).items() if n in new}
    if where and boxes:
        cx = sum(p[0] for p in boxes.values()) / len(boxes)
        cy = sum(p[1] for p in boxes.values()) / len(boxes)
        for from_inside, p in boxes.items():
            positions[new[from_inside]] = [round(where[0] + p[0] - cx), round(where[1] + p[1] - cy)]
    return positions


def ungroup_in_project(project, name: str) -> dict[str, str]:
    """`ungroup`, and also: the group's sliders go back to their nodes; the boxes, to their place (as they were
    inside, around where the group was)."""
    g = project.graph
    node = g._find(name)
    definition = g.definitions.get(node.kind.name)
    taken = {}
    new = ungroup(g, name, project.export, taken)
    for c in project.controls:
        if c.node == name and c.input_ in definition.inputs:
            from_inside, its = definition.inputs[c.input_][0]
            c.node, c.input_ = new[from_inside], its
    if name in project.view:
        project.view[new[definition.output]] = project.view.pop(name)
    for taker, inside in taken.items():   # its Group result nodes: what they had, to their inside node
        if taker in project.view:
            project.view[inside] = project.view.pop(taker)
    project.thumbnails = [n for n in project.thumbnails if n not in taken]
    project.positions = boxes_ungrouped(project.positions, name, definition, new, taken)
    project.thumbnails = [n for n in project.thumbnails if n != name]
    _forget_if_unused(g, definition.name)
    return new


def _forget_if_unused(graph: Graph, kind: str) -> None:
    """A project group that no node uses any more (its last one was ungrouped) leaves the project's groups: it is no
    longer offered with Tab, and its name can be used again. One saved in the library stays there."""
    if any(n.kind.name == kind for n in graph.nodes.values()):
        return
    if any(spec.get("type") == kind for d in graph.definitions.values() for spec in d.nodes.values()):
        return                                    # (used inside another group)
    graph.definitions.pop(kind, None)
    graph.kinds.pop(kind, None)


# --- Inside: seeing and editing a group (Delivery 6, part 2) ---------------------------------
#
# Inside a group, its inputs are «Group input» nodes (named like the input; their
# «value» is what reaches that group node: so it computes with real data) and its output,
# a «Group output» node. The rest are the usual nodes. On editing, `inner_apply` writes it
# back into the definition and updates all the nodes of that group.

def _from_input(value=None, name: str | None = None) -> Data:
    if value is None:
        raise ShapeError(tr('Nothing reaches this group input.'))
    if isinstance(value, Data):
        return value
    return Data.value(value, name) if isinstance(value, (int, float)) else value


INPUT = NodeType("Group input", CATEGORY, (Input("value", 0.0),), "value", _from_input,
                     "A group input: what reaches it from outside. Its name is the input's name; its value, the "
                     'current one (or the one it will have if nothing is connected).')
OUTPUT = NodeType("Group output", CATEGORY, (Input("data"),), "data",
                    lambda data, name=None: data, 'What leaves the group: connect its result here.')
_SUFFIX = " (entrada)"
#: Added to the name of a Group output node when an inside node already has the name of its result.
_SUFFIX_OUTPUT = " (output)"


def allowed_inside(definitions: dict, kinds: dict, around: list[str]) -> dict:
    """The kinds that can go inside the groups `around` (the one being edited and those that hold it): neither them
    nor a group that holds one of them (it would contain itself)."""
    banned = set(around)
    return {t: v for t, v in kinds.items() if t not in banned and not uses(definitions, t) & banned}


def inner(graph: Graph, name: str, around: list[str] = ()) -> tuple[Graph, dict[str, list[float]]]:
    """The inside graph of the group node `name`, to see and edit it, and the positions of its boxes. `around`: the
    groups that hold it, when one entered it from inside another.

    The inputs carry what reaches that node (computed), so the wires show real data.
    """
    node = graph._find(name)
    definition = graph.definitions[node.kind.name]
    g = Graph()
    g.kinds = {**allowed_inside(graph.definitions, graph.kinds, [*around, definition.name]),
               INPUT.name: INPUT, OUTPUT.name: OUTPUT}
    g.definitions = graph.definitions
    _build(g, definition.nodes)
    positions = {n: list(p) for n, p in definition.positions.items() if n in g.nodes}
    xs = [p[0] for p in positions.values()] or [0]
    ys = [p[1] for p in positions.values()] or [0]
    for i, (input_, targets) in enumerate(definition.inputs.items()):
        arrives = node.inputs.get(input_)
        if isinstance(arrives, Node):
            try:
                arrives = graph.value(arrives)
            except ShapeError:
                arrives = None
        elif arrives is REQUIRED:
            arrives = None
        n = input_ if input_ not in g.nodes else input_ + _SUFFIX
        g.node(INPUT.name, n, value=arrives)
        for from_inside, its in targets:
            g.change(from_inside, its, g.nodes[n])
        positions.setdefault(n, [min(xs) - 340, min(ys) + 110 * i])     # to the left, with room
    if definition.outputs:                        # several results: a Group output for each, named like it
        for i, (result, from_inside) in enumerate(definition.outputs.items()):
            n = result if result not in g.nodes else result + _SUFFIX_OUTPUT
            g.node(OUTPUT.name, n, data=g.nodes[from_inside])
            positions.setdefault(n, [max(xs) + 300, min(ys) + 110 * i])
    else:
        output = tr("output") if tr("output") not in g.nodes else tr("group output")
        g.node(OUTPUT.name, output, data=g.nodes[definition.output])
        positions.setdefault(output, [max(xs) + 300, min(ys)])
    if any(n not in definition.positions for n in definition.nodes):
        return g, {}                    # without the inside boxes: let the canvas arrange it all, by the flow
    return g, positions


def refresh_inputs(graph: Graph, name: str, g: Graph) -> None:
    """The inside inputs, with what reaches the group node `name` now (something changed outside)."""
    node = graph.nodes.get(name)
    if node is None:
        return
    for input_ in graph.definitions[node.kind.name].inputs:
        n = input_ if input_ in g.nodes and g.nodes[input_].kind is INPUT else input_ + _SUFFIX
        if n not in g.nodes:
            continue
        arrives = node.inputs.get(input_)
        if isinstance(arrives, Node):
            try:
                arrives = graph.value(arrives)
            except ShapeError:
                arrives = None
        elif arrives is REQUIRED:
            arrives = None
        if g.nodes[n].inputs["value"] is not arrives:
            g.change(n, "value", arrives)


def inner_apply(graph: Graph, kind: str, g: Graph, positions: dict | None = None,
                     edited: str | None = None, also: tuple = ()) -> Definition:
    """Writes what was edited inside (`g`, from `inside`) into the definition of the group `kind`, and updates all its
    nodes in `graph` (and in the graphs `also`: those of the groups around, when it was entered from inside another):
    the new kind, the new inputs (the removed ones, out) and the cache.

    `edited`: the group node through which one entered. A value written inside in an input is its own (if no wire
    reaches it from outside); the other nodes take it if they did not have one of their own.
    """
    old = graph.definitions[kind]
    for name, definition in graph.definitions.items():    # brought inside (from the library, pasted)
        if name not in graph.kinds:
            graph.kinds[name] = group_kind(definition, graph.kinds)
    inputs_nodes = [n for n in g.nodes.values() if n.kind is INPUT]
    outputs = [n for n in g.nodes.values() if n.kind is OUTPUT]
    if not outputs:
        raise ShapeError(tr('A group needs a “Group output” node: connect to it what leaves the group.'))
    for out in outputs:
        origin = out.inputs["data"]
        if not isinstance(origin, Node) or origin.kind is INPUT:
            raise ShapeError(tr('Connect to “{output}” the node whose result leaves the group.').format(
                output=out.name))
    origin = outputs[0].inputs["data"]
    results = {}
    if len(outputs) > 1:                         # several results, named like their Group output nodes
        results = {(o.name[:-len(_SUFFIX_OUTPUT)] if o.name.endswith(_SUFFIX_OUTPUT) else o.name): o.inputs["data"].name
                   for o in outputs}
    special = {n.name for n in inputs_nodes} | {o.name for o in outputs}
    nodes = {}
    for n in g.nodes.values():
        if n.name in special:
            continue
        data_items, _ = _node_a_json(n, set(g.nodes) - special)
        nodes[n.name] = data_items
    inputs, values = {}, {}
    for e in inputs_nodes:
        name = e.name[: -len(_SUFFIX)] if e.name.endswith(_SUFFIX) else e.name
        inputs[name] = [(n.name, its) for n in g.nodes.values() if n.name not in special
                            for its, o in n.connections.items() if o is e]
        v = e.inputs["value"]
        if v is not None and not isinstance(v, (Data, Node)):
            values[name] = v                     # a value of its own: that of the input if nothing is connected
    positions = dict(positions or old.positions)
    definition = Definition(kind, nodes, inputs, origin.name, {n: list(p) for n, p in positions.items()},
                            old.help, values, results)
    new_kind = group_kind(definition, graph.kinds)
    graph.kinds[kind] = new_kind
    graph.definitions[kind] = definition
    for other in also:
        if kind in other.kinds:
            other.kinds[kind] = new_kind
    for node in [n for each in (graph, *also) for n in each.nodes.values()]:
        if node.kind.name != kind:
            continue
        node.kind = new_kind
        before = node.inputs
        new = {}
        for e in new_kind.inputs:
            v = before.get(e.name, REQUIRED)
            own = not isinstance(v, Node) and v is not REQUIRED and v != old.values.get(e.name, REQUIRED)
            if e.name in values and not isinstance(v, Node) and (node.name == edited or not own):
                v = values[e.name]           # what was written inside (or the default value, if it had none of its own)
            new[e.name] = e.default if v is REQUIRED else v
        node.inputs = new
        node.graph._invalidate(node)
    return definition


def refresh_kinds(graph: Graph, levels=()) -> None:
    """Every group made again from its definition: a group that holds one just edited computes with its new inside.
    `levels`: the inside graphs open, each with the groups around it ([(graph, around)]): what each can hold, again
    (a group made in one of them is offered in the others). Their nodes, with the new kind and computed again."""
    for name, definition in graph.definitions.items():
        graph.kinds[name] = group_kind(definition, graph.kinds)
    for g, around in levels:
        g.kinds = {**allowed_inside(graph.definitions, graph.kinds, list(around)), INPUT.name: INPUT,
                   OUTPUT.name: OUTPUT}
    for g in [graph, *(g for g, _ in levels)]:
        for node in g.nodes.values():
            if node.kind.name in graph.definitions:
                node.kind = graph.kinds[node.kind.name]
                g._invalidate(node)


def rename_input(graph: Graph, kind: str, old: str, new_: str, also: tuple = ()) -> None:
    """A group input is renamed (its inside node was renamed): its nodes keep what is connected (in `graph` and in
    the graphs `also`)."""
    for node in [n for each in (graph, *also) for n in each.nodes.values()]:
        if node.kind.name == kind and old in node.inputs:
            node.inputs = {(new_ if e == old else e): v for e, v in node.inputs.items()}
        if node.kind.name == kind and node.inputs.get("back_into") == old:
            node.inputs["back_into"] = new_      # a repeated group: its result goes back in through the same input
    definition = graph.definitions[kind]
    if old in definition.values:
        definition.values[new_] = definition.values.pop(old)


def in_use(graph: Graph, kind: str) -> list[str]:
    return [n.name for n in graph.nodes.values() if n.kind.name == kind]
