"""Reads the code of a Code node before it runs, and says kindly what does not belong in Tensela.

The code of a node is a short piece of Python that works with what Tensela has: numbers, lists, points, lines,
meshes, mathematics. The check is a list of what is **allowed**, not of what is forbidden: a name, an attribute or
a statement that is not in the list does not exist for that code. So there is no way to open files, reach the
network, start other programs or get at the inside of Python, however it is disguised.

    problem = check(text)          # None, or a Problem(line, message)

It is the first of two layers; the second one (running the code apart, watched and with limits) is code_run.py.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache

from .code_api import ALLOWED_ATTRIBUTES, ALLOWED_NAMES
from .language import tr

#: A Code node is for short pieces: more than this is a program of its own.
MAX_LINES = 200
MAX_CHARACTERS = 20_000

#: The modules people try to import, by what they are for (to say why it does not belong here).
_FILES = {"os", "pathlib", "shutil", "glob", "io", "tempfile", "pickle", "json", "csv", "zipfile", "sqlite3"}
_NETWORK = {"socket", "urllib", "requests", "http", "httpx", "ftplib", "smtplib", "ssl", "webbrowser", "telnetlib",
            "asyncio", "aiohttp", "email", "xmlrpc"}
_PROGRAMS = {"subprocess", "sys", "ctypes", "multiprocessing", "threading", "signal", "platform", "importlib",
             "builtins", "code", "runpy", "pty", "resource", "gc", "inspect"}
_ALREADY = {"math": 'the mathematics is already there, without «math.»: sqrt(x), sin(x), pi (angles in degrees)',
            "random": 'the random numbers are already there: random(), uniform(a, b), randint(a, b), seed(n)',
            "numpy": 'the code of a node works with plain numbers and lists; for heavy tables of numbers, the nodes '
                     'themselves are faster',
            "np": 'the code of a node works with plain numbers and lists; for heavy tables of numbers, the nodes '
                  'themselves are faster'}
#: Names of Python that reach files, the person at the keyboard or the inside of the language.
_INSIDE = {"eval", "exec", "compile", "getattr", "setattr", "delattr", "hasattr", "globals", "locals", "vars", "dir",
           "type", "object", "super", "breakpoint", "help", "memoryview", "classmethod", "staticmethod", "property",
           "exit", "quit"}


@dataclass(frozen=True)
class Problem:
    """Something in the code that does not belong: where (the line, from 1; 0 if it is the whole) and why."""

    line: int
    message: str
    # Among several on the same line, the one that says more goes first (a name that does not belong, before what
    # is done with it).
    weight: int = 1

    def __str__(self) -> str:
        return tr('Line {line}: {message}').format(line=self.line, message=self.message) if self.line else self.message


def _why_module(name: str, imported: bool = True) -> str:
    root = name.split(".")[0]
    if root in _ALREADY:
        return tr('«{name}» is not imported here: ').format(name=root) + tr(_ALREADY[root]) + "."
    if root in _NETWORK:
        what = tr('it connects to other places (the network)')
    elif root in _FILES:
        what = tr('it reads and writes files')
    elif root in _PROGRAMS:
        what = tr('it reaches the system and other programs')
    else:
        what = tr('it brings in code from outside')
    used = tr('the code uses «import {name}»').format(name=name) if imported else \
        tr('the code uses «{name}»').format(name=name)
    return tr('{used}: {what}. The code of a node only works with the geometry and the mathematics of Tensela; '
              'that goes beyond what a Code node does.').format(used=used, what=what)


def _why_name(name: str) -> str:
    if name in _ALREADY:
        return tr(_ALREADY[name]) + "."
    if name in _NETWORK or name in _FILES or name in _PROGRAMS:
        return _why_module(name, imported=False)
    if name in ("open", "file"):
        return tr('«{name}» opens files. The code of a node only works with the geometry and the mathematics of '
                  'Tensela; reading a file goes beyond what a Code node does.').format(name=name)
    if name == "input":
        return tr('«input» waits for someone to type. What the code needs comes through the inputs a … h.')
    if name in _INSIDE:
        return tr('«{name}» reaches the inside of Python, beyond what a node needs. The code of a node works with '
                  'numbers, lists, points, lines and meshes.').format(name=name)
    return tr('«{name}» is not defined: neither the code gives it a value, nor is it something of Tensela '
              '(point, line, polyline, mesh, sin, sqrt, random, range…).').format(name=name)


def _private(name: str) -> bool:
    return name.startswith("_") and name != "_"


def check(text: str) -> Problem | None:
    """The first thing in the code that does not belong, or None if it can run."""
    if not isinstance(text, str) or not text.strip():
        return Problem(0, tr('There is no code yet: write some, and leave what it computes in «result».'))
    lines = text.count("\n") + 1
    if lines > MAX_LINES or len(text) > MAX_CHARACTERS:
        return Problem(0, tr('This code has {n} lines. A Code node is for short pieces (up to {maximum}); something '
                             'this size is a program of its own, and that goes beyond what a Code node does.').format(
            n=lines, maximum=MAX_LINES))
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return Problem(error.lineno or 0, tr('Python does not understand this ({error}).').format(error=error.msg))
    except (ValueError, RecursionError, MemoryError):
        return Problem(0, tr('Python cannot read this code (it is nested too deep, or has strange characters).'))

    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            defined.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.Lambda)):
            if isinstance(node, ast.FunctionDef):
                defined.add(node.name)
            a = node.args
            defined.update(x.arg for x in a.posonlyargs + a.args + a.kwonlyargs)
            defined.update(x.arg for x in (a.vararg, a.kwarg) if x is not None)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            defined.add(node.rest)

    found = [p for p in (_problem_of(node, defined) for node in ast.walk(tree)) if p is not None]
    return min(found, key=lambda p: (p.line, p.weight)) if found else None      # the first one, reading from the top


def _problem_of(node, defined: set) -> Problem | None:
    """What does not belong in this piece of the code, if anything."""
    line = getattr(node, "lineno", 0)
    if isinstance(node, ast.Import):
        return Problem(line, _why_module(node.names[0].name), 0)
    if isinstance(node, ast.ImportFrom):
        return Problem(line, _why_module(node.module or "."), 0)
    if isinstance(node, ast.ClassDef):
        return Problem(line, tr('the code defines a class («class {name}»). A Code node is for short pieces: '
                                'functions (def) and lists are enough here.').format(name=node.name))
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return Problem(line, tr('«global» and «nonlocal» are not used here: pass the values to the functions '
                                'and return the results.'))
    if isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await)):
        return Problem(line, tr('«async» and «await» are for waiting on other places (the network, files): the '
                                'code of a node only computes.'))
    if isinstance(node, ast.With):
        return Problem(line, tr('«with» is for opening things (files, connections): the code of a node only '
                                'computes.'))
    if isinstance(node, ast.FunctionDef) and node.decorator_list:
        return Problem(line, tr('decorators (@…) are not used here: a plain function is enough.'))
    if isinstance(node, ast.ExceptHandler) and node.type is None:
        return Problem(line, tr('write «except Exception:» instead of «except:» alone (so the node can still '
                                'be stopped).'))
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and (
            "__" in node.value if isinstance(node.value, str) else b"__" in node.value):
        return Problem(line, tr('a text with double underscores (__) reaches the inside of Python: it is not '
                                'needed here.'))
    names = []
    if isinstance(node, ast.Name):
        names.append(node.id)
    elif isinstance(node, ast.FunctionDef):
        names.append(node.name)
    elif isinstance(node, ast.arg):
        names.append(node.arg)
    elif isinstance(node, ast.keyword) and node.arg:
        names.append(node.arg)
    elif isinstance(node, ast.ExceptHandler) and node.name:
        names.append(node.name)
    elif isinstance(node, ast.Attribute):
        names.append(node.attr)
    elif isinstance(node, ast.MatchClass):             # «case Thing(attribute=…)» reads attributes too
        names.extend(node.kwd_attrs)
        for attribute in node.kwd_attrs:
            if attribute not in ALLOWED_ATTRIBUTES and not _private(attribute):
                return Problem(line, tr('«.{name}» is not something the values of a node have (a list has .append, '
                                        '.sort…; a point has .x, .y, .z, .length(), .unit(), .rotated(degrees)…).').format(
                    name=attribute))
    for name in names:
        if _private(name):
            return Problem(line, tr('«{name}» starts with an underscore: those names reach the inside of '
                                    'Python and are not used here (give it another name).').format(name=name))
    if isinstance(node, ast.Attribute) and node.attr not in ALLOWED_ATTRIBUTES:
        if node.attr in ("format", "format_map"):
            return Problem(line, tr('«.format» is not used here: write the text with f"…{value}…".'))
        if isinstance(node.value, ast.Name) and node.value.id not in defined and \
                node.value.id not in ALLOWED_NAMES:
            return Problem(line, _why_name(node.value.id), 0)          # «os.remove»: what matters is «os»
        return Problem(line, tr('«.{name}» is not something the values of a node have (a list has .append, '
                                '.sort…; a point has .x, .y, .z, .length(), .unit(), .rotated(degrees)…).').format(
            name=node.attr))
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in defined \
            and node.id not in ALLOWED_NAMES:
        return Problem(line, _why_name(node.id), 0)
    return None


@lru_cache(maxsize=256)
def names_used(text: str) -> frozenset:
    """The names the code reads (to know which inputs a … h it uses); nothing, if it cannot be read."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return frozenset()
    return frozenset(n.id for n in ast.walk(tree) if isinstance(n, ast.Name))
