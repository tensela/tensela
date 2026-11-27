"""The process that computes: the window of Tensela hands it the graph, and it gives back the results.

Computing apart keeps the window light: a slow node (many pieces, a long loop in Python) does not freeze it, and the
memory of a huge computation is that process's, not the window's. The window keeps editing its own graph; each time
something changes it sends the graph as data (the nodes and their inputs, as the file keeps them), and this process
gives back the result of each node, its errors and which nodes it computed again.

It remembers what it computed by a fingerprint of each node: its kind, its inputs and the fingerprints of the nodes
that feed it (and, if it reads a file, the date of the file). A node whose fingerprint did not change is not computed
again, as the window did before. It remembers the last projects (one per tab).

If a newer request arrives while it computes (another slider move, «Stop»), it drops the old computation at the next
node.

    calculator = Calculator(on_reply)          # (in the window) starts the process
    calculator.send(request(graph, turn, …))   # each change; the reply arrives to on_reply, in another thread
    python -s -c "from tensela.calculator import serve; serve()"      # the process itself

The two talk through the input and output of the process: each message, its length and the message (pickle).
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import queue
import signal
import struct
import subprocess
import sys
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path

#: How many projects (tabs) the process remembers.
PROJECTS_REMEMBERED = 6
_HEADER = struct.Struct("<Q")


# --- The channel ---------------------------------------------------------------------------------------------------

def _write(fd: int, message) -> None:
    data = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    view = memoryview(_HEADER.pack(len(data)) + data)
    while view:
        done = os.write(fd, view)
        view = view[done:]


def _read_exact(fd: int, n: int) -> bytes | None:
    parts, left = [], n
    while left:
        chunk = os.read(fd, min(left, 1 << 20))
        if not chunk:
            return None
        parts.append(chunk)
        left -= len(chunk)
    return b"".join(parts)


def _read(fd: int):
    """The next message, or None if the other side closed."""
    header = _read_exact(fd, _HEADER.size)
    if header is None:
        return None
    data = _read_exact(fd, _HEADER.unpack(header)[0])
    return None if data is None else pickle.loads(data)


# --- What the window sends -----------------------------------------------------------------------------------------

def graph_message(graph) -> dict:
    """The graph as data: the definitions of its groups and its nodes with their inputs (as the file keeps them)."""
    from .project_file import _node_a_json
    return {"groups": {n: d.a_json() for n, d in graph.definitions.items()},
            "nodes": {name: _node_a_json(node) for name, node in graph.nodes.items()}}


def request(graph, turn: int, project: int, folder, language: str, inside: list | None = None,
            wanted: list | None = None) -> dict:
    """A request to compute `graph`. `project` tells the projects apart (one per tab); the process sends back the
    result of the nodes it computed again and of those the window has without a result.

    `inside`: the groups entered, from the outermost, as [(group node, its graph in the window), …]: the process
    builds each inside as the window did (groups.py, `inner`) and computes it too.
    `wanted`: the nodes to compute (with what feeds them); None, all of them."""
    return {"op": "compute", "turn": turn, "project": project, "graph": graph_message(graph), "wanted": wanted,
            "folder": str(folder) if folder else None, "language": language,
            "missing": [name for name, node in graph.nodes.items() if node._value is None],
            "inside": [{"node": node, "missing": [n for n, x in g.nodes.items() if x._value is None]}
                       for node, g in (inside or [])]}


def build(message: dict):
    """The graph of a request."""
    from .project_file import KEY, VERSION, from__dict
    content = {KEY: VERSION, "nodes": message["nodes"]}
    if message.get("groups"):
        content["groups"] = message["groups"]
    return from__dict(content).graph


def fingerprints(graph, message: dict) -> dict[str, str]:
    """A fingerprint for each node: what it is, its inputs and those of all that feed it."""
    from .graph import Node
    nodes, groups = message["nodes"], message.get("groups") or {}
    every_group = json.dumps(groups, sort_keys=True, default=str) if groups else ""
    folder = graph.folder
    out: dict[str, str] = {}

    def of(name: str) -> str:
        if name in out:
            return out[name]
        node = graph.nodes[name]
        parts = [json.dumps(nodes[name], sort_keys=True, default=str)]
        if node.kind.name in groups:
            parts.append(every_group)
        for input_ in node.kind.inputs:
            value = node.inputs[input_.name]
            if isinstance(value, Node):
                parts.append(f"{input_.name}<{of(value.name)}")
            elif input_.file and isinstance(value, str) and value:
                path = Path(value) if Path(value).is_absolute() or folder is None else Path(folder) / value
                try:
                    parts.append(f"{path}@{path.stat().st_mtime_ns}")
                except OSError:
                    parts.append(f"{path}@none")
        out[name] = hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()
        return out[name]

    for name in graph.nodes:
        of(name)
    return out


# --- The process ---------------------------------------------------------------------------------------------------

class _Inbox:
    """The messages from the window, read by a thread of its own as they arrive, so the computation can ask whether a
    newer one is there without waiting (`select` on a pipe is only for Unix: on Windows it takes sockets only). None
    when the window closed its side."""

    def __init__(self, fd: int):
        self._queue: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, args=(fd,), daemon=True, name="window requests").start()

    def _read(self, fd: int) -> None:
        while True:
            try:
                message = _read(fd)
            except Exception:                                   # a broken message: as if the window had closed
                message = None
            self._queue.put(message)
            if message is None:
                return

    def get(self):
        return self._queue.get()

    def arrived(self) -> list:
        """The messages already there, taken out (none: an empty list)."""
        out = []
        while True:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                return out


class _Process:
    """The state of the process: the results remembered and the messages that arrived while it computed."""

    def __init__(self, fd_in: int, fd_out: int):
        self.inbox, self.fd_out = _Inbox(fd_in), fd_out
        self.results: dict[str, object] = {}                   # fingerprint → result
        self.projects: OrderedDict = OrderedDict()             # project → fingerprints with a result
        self.waiting: list = []
        self.turn = None

    def newer(self, node) -> None:
        """(Before each node.) It says which node it starts (if the process ends there, the window knows where); if
        another message arrived, this computation no longer serves."""
        from .graph import Cancelled
        arrived = self.inbox.arrived()
        if arrived:
            self.waiting.extend(arrived)
            raise Cancelled()
        _write(self.fd_out, {"op": "at", "turn": self.turn, "node": node.name})

    def compute(self, message: dict) -> dict:
        from . import language
        from .graph import Cancelled
        from .memory import memory_cap, return_memory
        language.LANGUAGE = message.get("language") or language.LANGUAGE
        start = time.perf_counter()
        turn = self.turn = message["turn"]
        try:
            graph = build(message["graph"])
            graph.folder = message.get("folder")
            prints = fingerprints(graph, message["graph"])
        except Exception as error:                              # it should not happen: the window's graph was valid
            return {"turn": turn, "failure": f"{type(error).__name__}: {error}", "trace": traceback.format_exc()}
        remembered = set()
        # The results the window already has, for a process that does not know the project yet (a new one, after
        # «Stop» or a failure): the nodes that feed what is to compute.
        seed = message.get("seed") or {}
        for name, node in graph.nodes.items():
            value = seed.get(name)
            if value is None:
                value = self.results.get(prints[name])
            if value is not None:
                node._value = value
                remembered.add(name)
        graph.on_node = self.newer
        memory_cap(True)
        try:
            errors = graph.compute_all(message.get("wanted"))
        except Cancelled:
            return {"turn": turn, "cancelled": True}
        finally:
            graph.on_node = None
            memory_cap(False)
        with_result = {name: node._value for name, node in graph.nodes.items() if node._value is not None}
        computed = [name for name in with_result if name not in remembered]
        kept_prints = {prints[name] for name in with_result}
        try:
            inside = self.inside(graph, prints, message.get("inside") or [], kept_prints)
        except Cancelled:
            return {"turn": turn, "cancelled": True}
        # What it remembers: the results of this project and of the last others.
        self.projects[message["project"]] = kept_prints
        self.projects.move_to_end(message["project"])
        while len(self.projects) > PROJECTS_REMEMBERED:
            self.projects.popitem(last=False)
        for name, value in with_result.items():
            self.results[prints[name]] = value
        kept = set().union(*self.projects.values())
        if len(kept) < len(self.results):
            self.results = {k: v for k, v in self.results.items() if k in kept}
            return_memory()
        send = set(computed) | set(message.get("missing", []))
        return {"turn": turn, "values": {n: with_result[n] for n in send if n in with_result}, "computed": computed,
                "errors": _errors_out(errors), "inside": inside, "ms": (time.perf_counter() - start) * 1000}

    def inside(self, graph, prints: dict, levels: list, kept: set) -> list[dict]:
        """The groups entered, each built from the one around (as the window did) and computed. What reaches a group
        node decides all its inside, so the fingerprint of an inside node is that of its group node and its name."""
        from .data import ShapeError
        from .groups import inner
        out, around, outer, kinds = [], graph, prints, []
        for level in levels:
            name = level["node"]
            node = around.nodes.get(name)
            if node is None or node.kind.name not in graph.definitions or name not in outer:
                break
            try:
                g, _ = inner(around, name, kinds)
            except ShapeError:
                break
            kinds.append(node.kind.name)
            g.folder = graph.folder
            mine = {n: hashlib.sha1(f"{outer[name]}\ninside\n{n}".encode("utf-8")).hexdigest() for n in g.nodes}
            remembered = set()
            for n, x in g.nodes.items():
                value = self.results.get(mine[n])
                if value is not None:
                    x._value = value
                    remembered.add(n)
            g.on_node = self.newer
            try:
                errors = g.compute_all()
            finally:
                g.on_node = None
            with_result = {n: x._value for n, x in g.nodes.items() if x._value is not None}
            for n, value in with_result.items():
                self.results[mine[n]] = value
                kept.add(mine[n])
            computed = [n for n in with_result if n not in remembered]
            send = set(computed) | set(level.get("missing", []))
            out.append({"node": name, "values": {n: with_result[n] for n in send if n in with_result},
                        "computed": computed, "errors": _errors_out(errors)})
            around, outer = g, mine
        return out

    def search(self, message: dict) -> dict:
        """«Find the best…» (optimize.py) on the project sent: it moves the sliders chosen until the number of the
        objective reaches what is wanted. Each time it finds something better it says so; a message from the window
        («stop») ends it with the best found, also in the middle of a node."""
        from . import language
        from . import optimize as O
        from .graph import Cancelled
        from .memory import memory_cap
        language.LANGUAGE = message.get("language") or language.LANGUAGE
        stopped = []

        def stop() -> bool:
            if not stopped:
                arrived = self.inbox.arrived()
                stopped.extend(arrived[:1])                     # the first one stops it; the rest, for later
                self.waiting.extend(arrived[1:])
            return bool(stopped)

        def at_node(node) -> None:
            if stop():
                raise O._Enough('stopped')

        try:
            graph = build(message["graph"])
            graph.folder = message.get("folder")
            for name, value in (message.get("seed") or {}).items():
                if name in graph.nodes:
                    graph.nodes[name]._value = value
            chosen, objective = message["chosen"], message["objective"]
            variables = [O.Variable(*v) for v in message["variables"]]

            def evaluate(x: list[float]) -> float:
                for (node, input_, index, whole), v in zip(chosen, x):
                    O.put_value(graph, node, input_, v, index, whole)
                return O.single_number(graph.value(objective))

            graph.on_node = at_node
            memory_cap(True)
            try:
                result = O.search(evaluate, variables, message["goal"], message["target"], message["method"],
                                  message["seconds"], stop=stop,
                                  report=lambda r: _write(self.fd_out, {"op": "progress", "result": r}),
                                  population=message["population"], patience=message["patience"])
            finally:
                graph.on_node = None
                memory_cap(False)
        except Cancelled:
            return {"op": "found", "result": None}
        except Exception as error:                              # said in the dialog
            return {"op": "failed", "error": str(error)}
        if stopped and stopped[0] is None:
            return {}                                           # the window closed
        return {"op": "found", "result": result}

    def run(self) -> None:
        while True:
            message = self.waiting.pop(0) if self.waiting else self.inbox.get()
            if message is None or message.get("op") == "quit":
                return
            if message.get("op") == "search":
                reply = self.search(message)
                if not reply:
                    return
                _write(self.fd_out, reply)
                continue
            if message.get("op") != "compute":
                continue                                        # («stop»: it only cut what was being computed)
            self.waiting.extend(self.inbox.arrived())
            if any(m is None or m.get("op") in ("compute", "quit") for m in self.waiting):
                _write(self.fd_out, {"turn": message["turn"], "cancelled": True})     # a newer one is waiting
                continue
            _write(self.fd_out, self.compute(message))


def _errors_out(errors: dict) -> list[tuple]:
    """The errors of a computation as data for the window: (node, expected, text, where it failed)."""
    from .graph import NodeError
    out = []
    for name, error in errors.items():
        expected = isinstance(error, NodeError)
        out.append((name, expected, str(error) if expected else f"{type(error).__name__}: {error}",
                    "" if expected else "".join(traceback.format_exception(error))))
    return out


def serve() -> None:
    """The process: it reads requests from its input and writes the replies to its output. What the nodes or the
    libraries print goes to the terminal (the error output), never into the channel."""
    fd_in, fd_out = os.dup(0), os.dup(1)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    from . import nodes, project_file  # noqa: F401  (ready before the first request)
    import importlib
    for module in filter(None, (m.strip() for m in os.environ.get("TENSELA_EXTRA_NODES", "").split(","))):
        importlib.import_module(module)                         # nodes of the tests
    from .extensions import load_in_calculator
    load_in_calculator()                                        # the nodes of the extensions the window has on
    _Process(fd_in, fd_out).run()


# --- In the window -------------------------------------------------------------------------------------------------

class _Worker:
    """One process that computes: what is sent goes through a thread of its own (sending never makes the window
    wait, however big the project), and what it answers is read in another."""

    def __init__(self, on_message):
        self.on_message = on_message                            # on_message(worker, message or None)
        self.killed = False
        package = Path(__file__).resolve().parent.parent
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(package)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        self.process = subprocess.Popen(
            [sys.executable, "-s", "-c", "from tensela.calculator import serve; serve()"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, bufsize=0, close_fds=True, process_group=0)
        self._outbox: queue.Queue = queue.Queue()
        threading.Thread(target=self._write, daemon=True, name="calculator requests").start()
        threading.Thread(target=self._read, daemon=True, name="calculator replies").start()

    def alive(self) -> bool:
        return not self.killed and self.process.poll() is None

    def send(self, message: dict) -> None:
        self._outbox.put(message)

    def kill(self) -> None:
        """Closed on purpose (it is not reported as a failure)."""
        self.killed = True
        self._outbox.put(None)
        try:                                                    # with what it started (the helper of the Code nodes)
            os.killpg(self.process.pid, signal.SIGKILL)         # (Unix only: on Windows, AttributeError)
        except (OSError, AttributeError):
            try:
                self.process.kill()
            except OSError:
                pass

    def close(self) -> None:
        if self.alive():
            self.send({"op": "quit"})
            self._outbox.put(None)
            try:
                self.process.wait(2)
            except subprocess.TimeoutExpired:
                self.kill()

    def _write(self) -> None:
        fd = self.process.stdin.fileno()
        while True:
            message = self._outbox.get()
            if message is None:
                return
            try:
                _write(fd, message)
            except (OSError, ValueError):
                return

    def _read(self) -> None:
        fd = self.process.stdout.fileno()
        while True:
            try:
                message = _read(fd)
            except Exception:                                   # a broken message: the process is not trusted any more
                message = None
            if message is None:
                self.process.wait()
                if not self.killed:
                    self.on_message(self, None)
                return
            self.on_message(self, message)


class Calculator:
    """The process that computes, seen from the window, with another one ready to take its place.

    `on_reply(reply)` receives, in a thread of its own: each reply; {"op": "at", "turn", "node"} when the process
    starts a node; and {"op": "ended", "turn", "node"} if the process ended by itself while computing (a failure of a
    library, the memory of the computer): the node is the one it was computing.

    `restart()` closes the process at once (also in the middle of a long node) and the one ready takes its place:
    «Stop», or a new request while it is stuck in a node of what no longer serves.
    """

    def __init__(self, on_reply):
        self.on_reply = on_reply
        self._lock = threading.Lock()
        self.current = _Worker(self._message)
        self.spare: _Worker | None = None
        self.known: OrderedDict = OrderedDict()                 # the projects the current process remembers
        self.busy: int | None = None                            # the turn being computed
        self.at: tuple | None = None                            # (turn, node, since when)
        timer = threading.Timer(1.0, self._ready_spare)
        timer.daemon = True
        timer.start()

    def _ready_spare(self) -> None:
        with self._lock:
            if self.spare is None and self.current is not None:
                try:
                    self.spare = _Worker(self._message)
                except OSError:
                    self.spare = None

    def alive(self) -> bool:
        return self.current is not None and self.current.alive()

    def knows(self, project: int) -> bool:
        return project in self.known

    def send(self, message: dict) -> bool:
        """Sends a request (it never waits). False if there is no process to send it to."""
        with self._lock:
            if self.current is None:                            # closed
                return False
            if not self.current.alive():                        # it ended: the one ready takes its place
                try:
                    self.current, self.spare = self.spare or _Worker(self._message), None
                except OSError:
                    return False
                self.known.clear()
            if message.get("op") == "compute":
                self.busy, self.at = message["turn"], None
                self.known[message["project"]] = True
                self.known.move_to_end(message["project"])
                while len(self.known) > PROJECTS_REMEMBERED:
                    self.known.popitem(last=False)
            self.current.send(message)
            return True

    def stuck_for(self) -> float:
        """How long the process has been in the same node of the turn it computes (0 if it is not computing)."""
        at = self.at
        if self.busy is None or at is None or at[0] != self.busy:
            return 0.0
        return time.monotonic() - at[2]

    def restart(self) -> None:
        """Closes the current process at once; the one ready (or a new one) takes its place."""
        with self._lock:
            if self.current is not None:
                self.current.kill()
            self.current, self.spare = self.spare or _Worker(self._message), None
            self.known.clear()
            self.busy = self.at = None
        timer = threading.Timer(0.5, self._ready_spare)
        timer.daemon = True
        timer.start()

    def renew(self) -> None:
        """Both processes closed and new ones started (with the environment of now: the extensions turned on)."""
        with self._lock:
            for worker in (self.current, self.spare):
                if worker is not None:
                    worker.kill()
            self.current, self.spare = _Worker(self._message), None
            self.known.clear()
            self.busy = self.at = None
        timer = threading.Timer(0.5, self._ready_spare)
        timer.daemon = True
        timer.start()

    def stop(self) -> None:
        """«Stop»: if it is computing, it is closed at once."""
        if self.busy is not None:
            self.restart()

    def close(self) -> None:
        with self._lock:
            workers, self.current, self.spare = [self.current, self.spare], None, None
        for worker in workers:
            if worker is not None:
                worker.close()

    def _message(self, worker: _Worker, message) -> None:
        if worker is not self.current:
            return                                              # the spare, or one closed on purpose
        if message is None:                                     # it ended by itself
            with self._lock:
                turn, at = self.busy, self.at
                self.known.clear()
                self.busy = self.at = None
            self.on_reply({"op": "ended", "turn": turn, "node": at[1] if at and at[0] == turn else None})
            return
        if message.get("op") == "at":
            self.at = (message["turn"], message["node"], time.monotonic())
        elif message.get("turn") == self.busy:
            self.busy = self.at = None
        self.on_reply(message)
