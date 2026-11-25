"""Runs the code of the Code nodes apart from Tensela: in a helper process, watched and with limits.

It is the second layer (the first one, code_check.py, reads the code before it runs). If some code got past the
check, here it still cannot leave:

- a **watcher of Python itself** (an audit hook) stops anything that is not computing: opening a file, a connection,
  starting a program, importing a module, reaching the inside of the interpreter;
- **limits**: memory (a huge list fails there, not in Tensela), no files written, and time: if the helper does
  not answer, it is closed and another one starts the next time;
- where the system allows it, the helper has **no network at all** (its own empty network).

The window talks to the helper through its input and output, with data only (a header and the numbers; nothing that
could carry code back).

    data = helper().run(text, {"a": …}, "element", "my code")        # from Tensela
    python -I -c "… main()"                                           # the helper itself
"""
from __future__ import annotations

import atexit
import json
import os
import struct
import sys
import threading

import numpy as np

from .data import Data, ShapeError
from .language import tr

#: How much more memory than it has at the start the helper may use.
MEMORY = 1024 ** 3
#: How long the window waits beyond the time of the code itself before closing the helper.
GRACE = 3.0
#: The largest message accepted from the helper (the numbers of a result).
MAX_MESSAGE = 512 * 1024 ** 2
#: What the watcher lets through: computing. Everything else Python reports (files, network, programs, imports, the
#: inside of the interpreter…) is stopped.
ALLOWED_EVENTS = frozenset({"compile", "exec", "builtins.id", "object.__getattr__"})


#: Modules the helper must not keep loaded (they start programs, connect or map memory): once closed in, nothing can
#: be imported again.
_NOT_IN_THE_HELPER = frozenset({"subprocess", "_posixsubprocess", "socket", "_socket", "multiprocessing", "mmap",
                                "pty", "ssl", "_ssl", "asyncio", "select", "selectors", "signal", "_signal",
                                "threading", "_thread", "shutil", "tempfile", "glob", "pathlib", "urllib", "http",
                                "pickle", "_pickle", "marshal", "importlib", "runpy", "pkgutil", "zipimport"})


# --- Data, as bytes (a header and the numbers) --------------------------------------------------------------

_KIND_FIELDS = ("name", "faces", "curve", "closed", "grid", "polygon")


def _header(data: Data, arrays: list) -> dict:
    values = np.asarray(data.values, order="C")           # (ascontiguousarray would turn a single number into a list)
    if values.dtype.kind not in "fiub":
        raise ShapeError(tr('The code of a node works with numbers and geometry (it gets {kind}).').format(
            kind=str(values.dtype)))
    arrays.append(values)
    head = {"levels": list(data.levels), "shape": list(values.shape), "dtype": values.dtype.str,
            "name": data.name, "starts": dict(data.starts),
            "kind": None if data.kind is None else {f: getattr(data.kind, f) for f in _KIND_FIELDS},
            "variables": {level: _header(count, arrays) for level, count in data.variables.items()}}
    if data.holes is not None:
        holes = np.asarray(data.holes, dtype=np.uint8, order="C")
        arrays.append(holes)
        head["holes"] = True
    return head


def pack(data: Data | None) -> tuple[dict | None, bytes]:
    """A data as a header (plain values) and its numbers, one after another."""
    if data is None:
        return None, b""
    arrays: list = []
    head = _header(data, arrays)
    return head, b"".join(a.tobytes() for a in arrays)


def _kind_of(fields):
    """The kind a header describes: one of Tensela's own if it is the same, or a mesh with those faces."""
    from . import geometry as G
    if fields is None:
        return None
    if not isinstance(fields, dict) or set(fields) != set(_KIND_FIELDS) or not isinstance(fields["name"], str):
        raise ValueError("kind")
    faces = fields["faces"]
    if faces is not None:
        faces = tuple(tuple(int(i) for i in face) for face in faces)
    grid = fields["grid"]
    kind = G.Kind(fields["name"][:40], faces, bool(fields["curve"]), bool(fields["closed"]),
                  None if grid is None else (int(grid[0]), int(grid[1])), bool(fields["polygon"]))
    for own in (G.POINT, G.CURVE, G.CLOSED_CURVE, G.VECTOR, G.RECTANGLE, G.BOX):
        if kind == own:
            return own
    return kind


def _data_of(head: dict, numbers: memoryview, at: int) -> tuple[Data, int]:
    shape = tuple(int(n) for n in head["shape"])
    dtype = np.dtype(str(head["dtype"]))
    if dtype.kind not in "fiub" or len(shape) > 8 or any(n < 0 for n in shape):
        raise ValueError("numbers")
    size = int(np.prod(shape, dtype=np.int64)) * dtype.itemsize
    if at + size > len(numbers):
        raise ValueError("short")
    values = np.frombuffer(numbers[at:at + size], dtype=dtype).reshape(shape).copy()
    at += size
    levels = tuple(str(n)[:80] for n in head["levels"])
    variables = {}
    for level, count in dict(head.get("variables") or {}).items():
        variables[str(level)], at = _data_of(count, numbers, at)
    holes = None
    if head.get("holes"):
        cells = int(np.prod(shape[:len(levels)], dtype=np.int64))
        if at + cells > len(numbers):
            raise ValueError("short")
        holes = np.frombuffer(numbers[at:at + cells], dtype=np.uint8).reshape(shape[:len(levels)]).astype(bool)
        at += cells
    name = head.get("name")
    starts = {str(k): int(v) for k, v in dict(head.get("starts") or {}).items()}
    return Data(values, levels, None if name is None else str(name), variables, starts, _kind_of(head.get("kind")),
                holes), at


def unpack(head: dict | None, numbers) -> Data | None:
    """The data of a header and its numbers. What does not fit (a made-up header) is an error, never code."""
    if head is None:
        return None
    data, _ = _data_of(head, memoryview(numbers), 0)
    return data


def _send(stream, head: dict, numbers: bytes = b"") -> None:
    text = json.dumps(head).encode()
    stream.write(struct.pack("<II", len(text), len(numbers)) + text + numbers)
    stream.flush()


def _read(stream, most: int = MAX_MESSAGE) -> tuple[dict, bytes]:
    sizes = stream.read(8)
    if len(sizes) < 8:
        raise EOFError()
    n_text, n_numbers = struct.unpack("<II", sizes)
    if n_text > 64 * 1024 ** 2 or n_numbers > most:
        raise ValueError("too large")
    text, numbers = stream.read(n_text), stream.read(n_numbers)
    if len(text) < n_text or len(numbers) < n_numbers:
        raise EOFError()
    head = json.loads(text)
    if not isinstance(head, dict):
        raise ValueError("header")
    return head, numbers


# --- The helper process ------------------------------------------------------------------------------------

def _enclose() -> dict:
    """Closes the helper in: no network of its own where the system allows it, limits of memory and files, and the
    watcher that only lets computing through. Returns what could be put (for the tests and the diagnosis)."""
    put = {"network": False, "memory": False, "watcher": False}
    for name in list(sys.modules):                     # what starts programs or connects, if something loaded it
        if name.split(".")[0] in _NOT_IN_THE_HELPER:
            del sys.modules[name]
    try:                                               # an empty network of its own: nothing to connect to
        os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNET)
        put["network"] = True
    except (AttributeError, OSError):
        pass
    try:
        import resource
        with open("/proc/self/statm") as f:
            now = int(f.read().split()[0]) * resource.getpagesize()
        resource.setrlimit(resource.RLIMIT_AS, (now + MEMORY, now + MEMORY))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))          # no file can grow
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))          # no other process (or thread) can be started
        put["memory"] = True
    except (ImportError, OSError, ValueError):
        pass

    allowed = ALLOWED_EVENTS

    def watcher(event: str, arguments) -> None:
        if event not in allowed:
            raise _Outside(event)

    sys.addaudithook(watcher)
    put["watcher"] = True
    return put


class _Outside(BaseException):
    """Something tried to leave the helper. Not an Exception: the code cannot catch it."""


def main() -> None:
    """The helper: it answers one request after another until its input closes."""
    from . import language
    from .code_run import run
    conversation_in, conversation_out = sys.stdin.buffer, os.fdopen(os.dup(1), "wb")
    sink = open(os.devnull, "w")
    sys.stdout = sys.stderr = sink                     # nothing written by mistake gets into the conversation
    # Everything needed, loaded and used once before closing in (afterwards nothing can be imported or opened).
    for warm in ("result = [point(i, 0, sin(i)) for i in range(3)]",
                 "result = [polyline([point(0, 0), point(1, random())]), polyline([point(0, 0), point(1, 1), point(2, 2)])]",
                 "result = mesh([point(0, 0), point(1, 0), point(1, 1)], [(0, 1, 2)])",
                 "result = [[1, 2], [3]]", "result = 1 / 0", "import os", "result = 'text'", "result = point(1, 2).nothing",
                 "def f(n):\n    return f(n + 1)\nresult = f(0)", "result = [a, b, c]"):
        for name in language.LANGUAGES:
            language.LANGUAGE = name
            try:
                run(warm, {"a": Data(1.0), "b": Data(np.zeros((2, 3)), ("n",)), "c": None}, "row; column", "warm", 0.5)
            except ShapeError:
                pass
    put = _enclose()
    _send(conversation_out, {"ready": True, **put})
    while True:
        try:
            head, numbers = _read(conversation_in)
        except (EOFError, ValueError, OSError):
            return
        try:
            language.LANGUAGE = head.get("language") if head.get("language") in language.LANGUAGES else "en"
            inputs, at, view = {}, 0, memoryview(numbers)
            for letter, description in dict(head.get("inputs") or {}).items():
                if description is None:
                    inputs[letter] = None
                else:
                    inputs[letter], at = _data_of(description, view, at)
            data = run(str(head["code"]), inputs, str(head.get("levels") or "element"), head.get("name"),
                       float(head.get("seconds") or 10.0))
            answer, numbers_out = pack(data)
            _send(conversation_out, {"ok": True, "data": answer}, numbers_out)
        except ShapeError as error:
            _send(conversation_out, {"ok": False, "error": str(error)})
        except _Outside as outside:
            _send(conversation_out, {"ok": False, "outside": str(outside)})
        except MemoryError:
            _send(conversation_out, {"ok": False, "memory": True})
        except BaseException as error:               # whatever it is, the helper says it and goes on
            _send(conversation_out, {"ok": False, "error": f"{type(error).__name__}: {error}"})


# --- From Tensela: starting the helper and asking it ---------------------------------------------------------

class Helper:
    """The helper process, started when first needed and kept for the next codes."""

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self.enclosed: dict = {}

    def _start(self) -> None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))       # where «tensela» is found
        start = ("import sys; sys.path.insert(0, sys.argv[1]); "
                 "from tensela.code_worker import main; main()")
        import subprocess                              # (here: the helper itself must not have it loaded)
        environment = {"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "OPENBLAS_NUM_THREADS": "1",
                       "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        self._process = subprocess.Popen([sys.executable, "-I", "-c", start, root], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment,
                                         cwd=os.path.abspath(os.sep), close_fds=True)
        head, _ = self._answer(30.0)
        if not head.get("ready") or not head.get("watcher"):
            raise OSError("not ready")
        self.enclosed = {k: bool(head.get(k)) for k in ("network", "memory", "watcher")}

    def _answer(self, seconds: float) -> tuple[dict, bytes]:
        """What the helper says, waiting at most so long (if it does not answer, TimeoutError)."""
        box: dict = {}

        def read() -> None:
            try:
                box["answer"] = _read(self._process.stdout)
            except BaseException as error:           # noqa: BLE001  (kept, to say it in the asking thread)
                box["error"] = error

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        reader.join(seconds)
        if reader.is_alive():
            raise TimeoutError()
        if "error" in box:
            raise box["error"]
        return box["answer"]

    def close(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            try:
                process.kill()
                process.wait(2)
            except Exception:                          # noqa: BLE001  (already gone, or slow to go: nothing to do)
                pass
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass

    def run(self, text: str, inputs: dict, levels: str = "element", name: str | None = None,
            seconds: float | None = None) -> Data:
        """The data the code gives, computed in the helper."""
        from . import language
        from .code_check import check
        from .code_run import MAX_SECONDS
        problem = check(text)                          # the first layer, here: what does not belong never leaves
        if problem is not None:
            raise ShapeError(str(problem))
        seconds = MAX_SECONDS if seconds is None else seconds
        heads, numbers = {}, []
        for letter, value in inputs.items():
            if value is not None and not isinstance(value, Data):
                value = Data.value(value)
            heads[letter], block = pack(value)
            numbers.append(block)
        request = {"code": text, "levels": levels, "name": name, "seconds": seconds, "language": language.LANGUAGE,
                   "inputs": heads}
        with self._lock:
            try:
                if self._process is None or self._process.poll() is not None:
                    self.close()
                    self._start()
                _send(self._process.stdin, request, b"".join(numbers))
                head, block = self._answer(seconds + GRACE)
            except TimeoutError:
                self.close()
                raise ShapeError(tr('The code took more than {seconds} s and was stopped. Is there a loop that does '
                                    'not end?').format(seconds=f"{seconds:g}")) from None
            except (OSError, EOFError, ValueError):
                self.close()
                raise ShapeError(tr('The helper that runs the code stopped (it ran out of memory, or the code closed '
                                    'it). Nothing was lost: it starts again with the next change.')) from None
            if head.get("ok"):
                try:
                    data = unpack(head.get("data"), block)
                except (ValueError, TypeError, KeyError, ShapeError):
                    data = None
                if data is None:
                    self.close()
                    raise ShapeError(tr('The helper that runs the code answered something that is not data. Nothing '
                                        'was lost: it starts again with the next change.'))
                return data
            if head.get("outside"):
                self.close()                           # whatever tried it, with a fresh helper the next time
                raise ShapeError(tr('The code tried to do something outside Tensela ({what}) and was stopped. '
                                    'The code of a node only works with the geometry and the mathematics of '
                                    'Tensela.').format(what=str(head["outside"])[:60]))
            if head.get("memory"):
                raise ShapeError(tr('The code needs more memory than a node may use (about 1 GB). Is there a list '
                                    'far too long?'))
            raise ShapeError(str(head.get("error") or tr('the code could not be run')))


_HELPER: Helper | None = None


def helper() -> Helper:
    """The helper of this Tensela (one for all the Code nodes)."""
    global _HELPER
    if _HELPER is None:
        _HELPER = Helper()
        atexit.register(_HELPER.close)
    return _HELPER
