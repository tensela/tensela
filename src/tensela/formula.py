"""Formulas as in a spreadsheet (Delivery 3).

    a * 3.5                       the height of each floor
    1 - a / b * 0.4               a tapering
    if(a < 5; 90; 0)              a condition
    if(a < 2; 0; a < 4; 1; 2)     several cases: if…, else if…, else
    a > 2 and a < 5               and · or · not(…): joining conditions
    sin(a * 10) * 2               the angles, in degrees (D2)

The variables are `a` … `h` (the inputs of the Formula node); each one can be a number or a data with levels, and
they combine with the single rule (R1). Decimal comma and `;` between arguments, as in a spreadsheet in Spanish (the
decimal point is accepted too). The functions and the words of the conditions are also accepted in Spanish (si, sen,
raiz…; y, o, no).

It is safe: the formula is not run as code. It is analysed and only numbers, those variables, the operations and the
functions below are allowed.
"""

from __future__ import annotations

import ast
import re

import numpy as np

from .data import Data, ShapeError, apply, require_numbers
from .language import tr

VARIABLES = ("a", "b", "c", "d", "e", "f", "g", "h")


def _degrees(f):
    return lambda x: f(np.deg2rad(x))


def _to_degrees(f):
    return lambda *x: np.rad2deg(f(*x))


FUNCTIONS = {
    "sin": _degrees(np.sin), "cos": _degrees(np.cos), "tan": _degrees(np.tan),
    "asin": _to_degrees(np.arcsin), "acos": _to_degrees(np.arccos), "atan": _to_degrees(np.arctan),
    "sqrt": np.sqrt, "abs": np.abs, "round": np.round, "floor": np.floor, "ceil": np.ceil,
    "min": np.minimum, "max": np.maximum,
    "if_": lambda *v: _if(*v),                  # «if» is a word of Python: inside, «if_»
    "exp": np.exp, "log": np.log, "cosh": np.cosh, "sinh": np.sinh, "tanh": np.tanh,
}
#: The functions as they are written in Spanish (a formula can use both; they are kept as written).
SPANISH = {"sen": "sin", "asen": "asin", "raiz": "sqrt", "raíz": "sqrt", "redondear": "round", "entero": "floor",
           "techo": "ceil", "si": "if_", "senh": "sinh"}
#: How each function is written on screen, in each language.
WRITTEN = {"if_": ("if", "si"), "sin": ("sin", "sen"), "asin": ("asin", "asen"), "sqrt": ("sqrt", "raiz"),
           "round": ("round", "redondear"), "floor": ("floor", "entero"), "ceil": ("ceil", "techo"),
           "sinh": ("sinh", "senh")}
#: How many values each function takes (the others, one). «if» takes 3, 5, 7…: the cases and the «else».
ARGUMENTS = {"if_": 3, "min": 2, "max": 2}
#: What is often written instead of a known function.
SIMILAR = {"seno": "sin", "coseno": "cos", "tangente": "tan", "sqr": "sqrt", "ln": "log", "pow": "^"}


def written(name: str) -> str:
    """A function as it is written in the language of the interface («if_» → «si» in Spanish)."""
    from .language import LANGUAGE
    en, es = WRITTEN.get(name, (name, name))
    return es if LANGUAGE == "es" else en


CONSTANTS = {"pi": np.pi, "phi": (1 + 5 ** 0.5) / 2}        # phi: the golden number (1.618…)


def _if(*values):
    """if(c1; v1; c2; v2; …; else): the value of the first case that holds; if none, the last one."""
    result = values[-1]
    for c, v in reversed(list(zip(values[:-1:2], values[1:-1:2]))):
        result = np.where(c, v, result)
    return result

_OPERATIONS = {
    ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide,
    ast.Pow: lambda x, y: np.power(np.asarray(x, float), y),   # 2 ** -1 is 0.5 (whole numbers refuse it)
    ast.Mod: np.mod,
}
_COMPARISONS = {
    ast.Lt: np.less, ast.LtE: np.less_equal, ast.Gt: np.greater, ast.GtE: np.greater_equal,
    ast.Eq: np.isclose, ast.NotEq: lambda x, y: ~np.isclose(x, y),
}


def prepare(text: str) -> str:
    """From the shape of a spreadsheet to that of Python: 3,5 → 3.5 and ; → ,"""
    t = text.strip().lstrip("=")
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    # Equal and different as in a spreadsheet: a = 1, a <> 1.
    t = t.replace("<>", "!=")
    t = re.sub(r"(?<![<>=!])=(?!=)", "==", t)
    # The words of the conditions, in Spanish: «a > 2 y a < 5», «a < 1 o a > 4», «no(a > 2)». Only between
    # two parts of a formula (with spaces), not to confuse them with a misplaced variable («x + y»).
    t = re.sub(r"(?<=[\w)])\s+y\s+(?=[\w(\-])", " and ", t)
    t = re.sub(r"(?<=[\w)])\s+o\s+(?=[\w(\-])", " or ", t)
    t = re.sub(r"\bno\s*(?=\()|\bno\s+(?=[\w])", "not ", t)
    t = re.sub(r"\bif\s*(?=\()", "if_", t)              # if(…) («if» is a word of Python)
    t = re.sub(r"\b(" + "|".join(SPANISH) + r")\s*(?=\()", lambda m: SPANISH[m.group(1)], t)   # sen(…) → sin(…)
    t = t.replace(";", ",").replace("^", "**").replace("−", "-").replace("×", "*").replace("÷", "/")
    return t


def _diagnosis(text: str) -> str | None:
    """Why a formula is not understood, in words: a parenthesis, two signs in a row, a number stuck to a letter…
    None if the error is not recognised."""
    t = text.strip().lstrip("=")
    open_ = t.count("(") - t.count(")")
    if open_ > 0:
        return tr('{n} parenthesis not closed: there are more “(” than “)”.').format(n=open_)
    if open_ < 0:
        return tr('{n} extra parenthesis “)”: there are more “)” than “(”.').format(n=-open_)
    z_depth = 0
    for c in t:
        z_depth += (c == "(") - (c == ")")
        if z_depth < 0:
            return tr('There is a “)” before its “(”: check the order of the parentheses.')
    pasted = re.search(r"(\d)\s*([a-h(])", t)
    if pasted:
        return tr('Between “{a}” and “{b}” a sign is missing: to multiply write “{a} * {b}” (in a formula you do '
                  'not multiply by writing them together, as on paper).').format(a=pasted.group(1), b=pasted.group(2))
    pasted = re.search(r"\)\s*([\w(])", t)
    if pasted:
        return tr('After “)” a sign is missing before “{b}”: “) * {b}”?').format(b=pasted.group(1))
    if re.search(r"[+\-*/^]\s*$", t):
        return tr('The formula ends with a sign: what goes after it is missing.')
    double = re.search(r"[*/^]\s*[*/^]", t.replace("**", "^"))
    if double:
        return tr('There are two signs in a row (“{s}”): one is extra.').format(s=double.group(0).strip())
    if re.search(r"\(\s*\)", t):
        return tr('There is an empty parenthesis “()”: a value goes inside.')
    return None


def analyse(text: str) -> ast.Expression:
    """Checks the formula and returns its tree; a clear error if something is not allowed (and how to fix it)."""
    if not text or not text.strip():
        raise ShapeError(tr('The formula is empty.'))
    try:
        tree = ast.parse(prepare(text), mode="eval")
    except SyntaxError:
        pattern = _diagnosis(text)
        raise ShapeError(tr('I do not understand the formula “{formula}”. {reason}').format(
                               formula=text.strip(),
                               reason=pattern or tr('Is a parenthesis missing or a sign extra?'))) from None
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id not in VARIABLES and n.id not in FUNCTIONS and n.id not in CONSTANTS:
            raise ShapeError(_name_unknown(n.id))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCTIONS:
            expected = ARGUMENTS.get(n.func.id, 1)
            if n.func.id == "if_" and len(n.args) >= 3 and len(n.args) % 2 == 1:
                continue                             # if(c1; v1; c2; v2; else): any odd number
            if n.func.id == "if_":
                raise ShapeError(tr('“if” takes a condition and its value, as many times as there are cases, '
                                      'and at the end the “otherwise” value: if(a < 2; 0; 1) · if(a < 2; 0; a < '
                                      '4; 1; 2). It receives {m} values.').format(m=len(n.args)))
            if len(n.args) != expected:
                hint = (tr(' To separate the values of a function use “;” (the comma is the decimal one): “max(a; '
                            '2)”.') if expected > 1 or len(n.args) > 1 else "")
                carries = tr('1 value') if expected == 1 else tr('{n} values').format(n=expected)
                raise ShapeError(tr('“{f}” takes {carries} and receives {m}.{hint}').format(
                                       f=written(n.func.id), carries=carries, m=len(n.args), hint=hint))
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in FUNCTIONS):
            if isinstance(n.func, ast.Name):         # a misspelt function: «seno(a)»
                raise ShapeError(_name_unknown(n.func.id))
            pattern = _diagnosis(text)
            raise ShapeError(pattern or tr('The formula “{formula}” can only use the known functions.').format(
                                   formula=text.strip()))
        if not isinstance(n, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.Call,
                              ast.Name, ast.Constant, ast.Load, ast.operator, ast.unaryop, ast.cmpop,
                              ast.boolop)):
            raise ShapeError(tr('The formula “{formula}” has something that cannot be calculated.').format(
                                   formula=text.strip()))
        if isinstance(n, ast.Constant) and not isinstance(n.value, (int, float)):
            raise ShapeError(tr('A formula can only have numbers, variables and functions (“{value}” does not belong).').format(
                                   value=n.value))
    return tree


def _name_unknown(name: str) -> str:
    """The warning for an unknown word, with a hint of what was meant."""
    import difflib
    if name.lower() in VARIABLES and name != name.lower():
        return tr('“{n}”: variables are lowercase (“{m}”).').format(n=name, m=name.lower())
    if name in ("x", "y", "z", "t", "r"):
        return tr('“{n}” is not a variable of the formula: the variables go from “a” to “h”. Connect your “{n}” '
                  'to input “a” (or b, c…) and write “a” in the formula.').format(n=name)
    if name.lower() in SIMILAR:
        return tr('I do not know “{n}”; did you mean “{m}”?').format(n=name, m=written(SIMILAR[name.lower()]))
    names = sorted({written(f) for f in FUNCTIONS})
    near = difflib.get_close_matches(name.lower(), names + list(CONSTANTS), n=1, cutoff=0.6)
    if near:
        return tr('I do not know “{n}”; did you mean “{m}”?').format(n=name, m=near[0])
    return tr("The formula uses “{name}”, which I don't know. The variables go from a to h; the functions: "
              '{options}.').format(name=name, options=', '.join(names))


def variables_used(text: str) -> list[str]:
    return sorted({n.id for n in ast.walk(analyse(text)) if isinstance(n, ast.Name) and n.id in VARIABLES})


def formula(text: str, a=None, b=None, c=None, d=None, e=None, f=None, g=None, h=None,
            name: str | None = None) -> Data:
    """Computes `text` with the variables a … h (combined by the single rule)."""
    tree = analyse(text)
    given = {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f, "g": g, "h": h}
    used = variables_used(text)
    for v in used:
        if given[v] is None:
            raise ShapeError(tr('The formula uses “{variable}”, but “{variable}” is empty.').format(variable=v))
    for v in used:
        require_numbers(given[v], v)
    inputs = [x if isinstance(x, Data) else Data.value(np.asarray(x, dtype=float), v)
                for v, x in ((v, given[v]) for v in used)]

    def compute(*values):
        with np.errstate(all="ignore"):
            result = np.asarray(_evaluate(tree.body, dict(zip(used, values))))
        shape = np.broadcast_shapes(result.shape, *(np.shape(x) for x in values))
        result = np.broadcast_to(result, shape).copy()  # a formula without variables holds for all
        if result.dtype.kind == "f" and not np.all(np.isfinite(result)):
            bad = int((~np.isfinite(result)).sum())
            raise ShapeError(tr('The formula “{formula}” does not give a number in {n} of {total} cases: {cause}').format(
                                   formula=text.strip(), n=bad, total=result.size, cause=_cause(text)))
        return result

    return apply(compute, *inputs, name=name)


def _cause(text: str) -> str:
    """The probable cause of an impossible result, looking at what is in the formula."""
    t = text.replace(" ", "")
    if "/" in t:
        return tr('probably a division by 0 (some divisor is 0). Add a little to it, or use if(): “if(b = 0; 0; a / b)”.')
    if "raiz" in t or "sqrt" in t:
        return tr('the root of a negative number does not exist. Use abs() inside: “sqrt(abs(a))”, or max(): '
                  '“sqrt(max(a; 0))”.')
    if "log" in t:
        return tr('the logarithm only exists for numbers greater than 0.')
    if "asen" in t or "acos" in t:
        return tr('asin and acos only accept values between −1 and 1.')
    return tr('check divisions by 0, roots of negatives or huge numbers.')


def _evaluate(n, surroundings):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Name):
        return surroundings[n.id] if n.id in surroundings else CONSTANTS[n.id]
    if isinstance(n, ast.BinOp):
        return _OPERATIONS[type(n.op)](_evaluate(n.left, surroundings), _evaluate(n.right, surroundings))
    if isinstance(n, ast.UnaryOp):
        v = _evaluate(n.operand, surroundings)
        return -v if isinstance(n.op, ast.USub) else (np.logical_not(v) if isinstance(n.op, ast.Not) else v)
    if isinstance(n, ast.Compare):
        left, result = _evaluate(n.left, surroundings), True
        for op, right in zip(n.ops, n.comparators):
            d = _evaluate(right, surroundings)
            result = np.logical_and(result, _COMPARISONS[type(op)](left, d))
            left = d
        return result
    if isinstance(n, ast.BoolOp):
        values = [_evaluate(v, surroundings) for v in n.values]
        f = np.logical_and if isinstance(n.op, ast.And) else np.logical_or
        result = values[0]
        for v in values[1:]:
            result = f(result, v)
        return result
    if isinstance(n, ast.Call):
        return FUNCTIONS[n.func.id](*(_evaluate(x, surroundings) for x in n.args))
    raise ShapeError(tr('Part of the formula cannot be calculated.'))
