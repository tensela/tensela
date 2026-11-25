"""Runs the code of a Code node, once code_check.py has read it.

The code runs with only the names of code_api.py (nothing else of Python exists for it), with its loops and
functions watched: it stops when it takes too long or when the computation is no longer wanted. What it leaves in
`result` becomes the data of the node.

    data = run(text, {"a": …, "b": …}, levels="element", name="my code")
"""
from __future__ import annotations

import ast
import time

from .code_api import names, to_data, to_python
from .code_check import check
from .data import Data, ShapeError
from .language import tr

#: How long the code of a node may take, in seconds.
MAX_SECONDS = 10.0
#: The longest range() the code may ask for.
MAX_RANGE = 10_000_000
_FILE = "<code>"


class _Stopped(BaseException):
    """The code took too long (or the computation is no longer wanted). Not an Exception: the code cannot catch it."""


class _Watch(ast.NodeTransformer):
    """Puts a call to the watcher at the start of every loop and every function of the code."""

    @staticmethod
    def _tick(node) -> ast.Expr:
        call = ast.Expr(ast.Call(ast.Name("_tick", ast.Load()), [], []))
        return ast.copy_location(call, node)

    def _watched(self, node):
        self.generic_visit(node)
        node.body.insert(0, self._tick(node))
        return node

    visit_For = visit_While = visit_FunctionDef = _watched

    def _watched_element(self, node):
        """A comprehension is a loop too: the watcher is asked before each of its elements («_tick() or element»)."""
        self.generic_visit(node)
        field = "value" if isinstance(node, ast.DictComp) else "elt"
        element = getattr(node, field)
        call = ast.copy_location(ast.Call(ast.Name("_tick", ast.Load()), [], []), element)
        setattr(node, field, ast.copy_location(ast.BoolOp(ast.Or(), [call, element]), element))
        return node

    visit_ListComp = visit_SetComp = visit_GeneratorExp = visit_DictComp = _watched_element


def _line_of(error: BaseException) -> int:
    """The line of the code where the error happened (the deepest one that is in the code itself)."""
    line, step = 0, error.__traceback__
    while step is not None:                            # (by hand: reading the source lines would open files)
        if step.tb_frame.f_code.co_filename == _FILE:
            line = step.tb_lineno or line
        step = step.tb_next
    if not line and isinstance(error, SyntaxError):
        line = error.lineno or 0
    return line


def _in_words(error: BaseException) -> str:
    if isinstance(error, ZeroDivisionError):
        return tr('a division by zero')
    if isinstance(error, RecursionError):
        return tr('a function calls itself without end (or too many times)')
    if isinstance(error, IndexError):
        return tr('a list has no element at that position ({error})').format(error=error)
    if isinstance(error, KeyError):
        return tr('there is nothing under that key ({error})').format(error=error)
    if isinstance(error, MemoryError):
        return tr('the result does not fit in memory')
    if isinstance(error, ShapeError):
        return str(error)
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__


def run(text: str, inputs: dict, levels: str = "element", name: str | None = None,
        seconds: float = MAX_SECONDS, wanted=None) -> Data:
    """The data the code gives. `inputs`: what reaches a … h (data, or None). `wanted()`: False when the computation
    is no longer wanted (the code stops at its next loop)."""
    problem = check(text)
    if problem is not None:
        raise ShapeError(str(problem))
    tree = ast.fix_missing_locations(_Watch().visit(ast.parse(text)))
    until = time.monotonic() + seconds
    count, stopped = 0, ""

    def tick() -> None:
        nonlocal count, stopped
        if stopped:                                   # once stopped, at every step (a «finally: return» in the code
            raise _Stopped(stopped)                   # could swallow it once, not always)
        count += 1
        if count % 256 == 0:
            if time.monotonic() > until:
                stopped = "time"
            elif wanted is not None and not wanted():
                stopped = "stop"
            if stopped:
                raise _Stopped(stopped)

    def counted(*limits):
        """range, but not an endless one: a loop inside Python itself cannot be watched."""
        numbers = range(*limits)
        if len(numbers) > MAX_RANGE:
            raise ShapeError(tr('range({n}) is too long (the maximum is {maximum}): is there an extra digit?').format(
                n=len(numbers), maximum=MAX_RANGE))
        return numbers

    surroundings = {"__builtins__": {}, **names(), "range": counted, "result": None, "_tick": tick}
    for letter in "abcdefgh":
        surroundings[letter] = to_python(inputs.get(letter))
    try:
        exec(compile(tree, _FILE, "exec"), surroundings)
        return to_data(surroundings.get("result"), levels, name)
    except _Stopped as stopped:
        if str(stopped) == "stop":
            from .graph import Cancelled
            raise Cancelled() from None
        raise ShapeError(tr('The code took more than {seconds} s and was stopped. Is there a loop that does not '
                            'end?').format(seconds=f"{seconds:g}")) from None
    except ShapeError as error:
        line = _line_of(error)
        raise ShapeError(tr('Line {line}: {message}').format(line=line, message=error) if line else str(error)) from None
    except Exception as error:
        line = _line_of(error)
        words = _in_words(error)
        raise ShapeError(tr('Line {line}: {message}').format(line=line, message=words) if line else words) from None
