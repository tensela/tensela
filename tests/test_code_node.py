"""The Code node: a short piece of Python that only works with what Tensela has."""

import time
from pathlib import Path

import numpy as np
import pytest

from tensela import geometry as G
from tensela.code_api import ALLOWED_ATTRIBUTES, to_data, to_python
from tensela.code_check import MAX_LINES, check
from tensela.code_run import run
from tensela.data import Data, ShapeError
from tensela.graph import Graph, NodeError
from tensela.project_file import Project, from__text, open_, to_text


# --- What the code gives ---------------------------------------------------------------------------------

def test_numbers_points_lines_and_meshes_come_out_as_data():
    assert float(run("result = 2 + 3", {}).values) == 5
    points = run("result = [point(i, 0, i * 2) for i in range(4)]", {}, levels="seed")
    assert points.kind is G.POINT and points.levels == ("seed",) and points.values[3].tolist() == [3, 0, 6]
    curve = run("result = polyline([point(0, 0), point(1, 0), point(1, 1)], closed=True)", {})
    assert curve.kind is G.CLOSED_CURVE and curve.values.shape == (3, 3)
    lines = run("result = [line(point(0, 0), point(i, 1)) for i in range(3)]", {})
    assert lines.kind is G.CURVE and lines.values.shape == (3, 2, 3)
    m = run("result = mesh([point(0, 0), point(1, 0), point(1, 1), point(0, 1)], [(0, 1, 2, 3)])", {})
    assert m.kind.name == "mesh" and m.kind.faces == ((0, 1, 2, 3),)


def test_lists_inside_lists_give_levels_also_uneven_ones():
    table = run("result = [[i * j for j in range(3)] for i in range(2)]", {}, levels="row; column")
    assert table.levels == ("row", "column") and table.values.tolist() == [[0, 0, 0], [0, 1, 2]]
    uneven = run("result = [[1], [1, 2, 3]]", {})
    assert uneven.levels == ("element", "element 2") and uneven.count == 4
    short_and_long = run("result = [polyline([point(0, 0), point(1, 0)]), "
                         "polyline([point(0, 0), point(1, 0), point(2, 0)])]", {})
    assert short_and_long.values.shape == (2, 3, 3)            # the shorter one, its last point repeated
    assert np.allclose(short_and_long.values[0, 2], [1, 0, 0])


def test_the_inputs_arrive_as_numbers_lists_and_points():
    assert to_python(Data(3.0)) == 3.0
    assert to_python(Data(np.arange(3.0), ("n",))) == [0.0, 1.0, 2.0]
    p = to_python(Data(np.array([1.0, 2.0, 3.0]), (), kind=G.POINT))
    assert (p.x, p.y, p.z) == (1, 2, 3)
    g = Graph()
    g.node("Line", "line", from_=(0.0, 0.0, 0.0), to=(4.0, 0.0, 0.0))
    g.node("Code", "middle", code="start, end = a\nresult = start.towards(end, 0.5) + point(0, 0, b)",
           a=g.nodes["line"], b=2.0)
    assert g.value("middle").values.tolist() == [2, 0, 2]


def test_points_have_their_arithmetic_and_angles_go_in_degrees():
    code = ("p = point(1, 0)\nq = p.rotated(90)\n"
            "result = [q.x, q.y, (p + q).length(), p.dot(q), p.cross(q).z, sin(90), atan2(1, 1), p.distance(q)]")
    assert np.allclose(run(code, {}).values, [0, 1, 2 ** 0.5, 0, 1, 1, 45, 2 ** 0.5])


def test_the_same_code_gives_the_same_random_numbers():
    a = run("result = [random() for i in range(5)]", {}).values
    b = run("result = [random() for i in range(5)]", {}).values
    assert np.array_equal(a, b) and len(set(a.tolist())) == 5


# --- What does not belong ---------------------------------------------------------------------------------

@pytest.mark.parametrize("code, says", [
    ("import socket\nresult = 1", "socket"),
    ("from os import path\nresult = 1", "os"),
    ("import numpy as np\nresult = 1", "numpy"),
    ("result = open('x').read()", "open"),
    ("result = os.remove('x')", "os"),
    ("result = eval('1')", "eval"),
    ("result = exec('x = 1')", "exec"),
    ("result = getattr(1, 'real')", "getattr"),
    ("result = globals()", "globals"),
    ("result = type(1)", "type"),
    ("result = input()", "input"),
    ("result = math.sin(1)", "math"),
    ("result = ().__class__", "__class__"),
    ("result = __import__('os')", "__import__"),
    ("result = __builtins__", "__builtins__"),
    ("x = point\nresult = x.__init__", "__init__"),
    ("result = '{0.__class__}'.format(1)", "format"),
    ("result = '{}'.format_map({})", "format"),
    ("result = 'a__b'", "__"),
    ("g = (i for i in range(3))\nresult = g.gi_frame", "gi_frame"),
    ("def f():\n    pass\nresult = f.func_globals", "func_globals"),
    ("try:\n    1 / 0\nexcept Exception as e:\n    result = e.args", "args"),
    ("try:\n    1 / 0\nexcept Exception as e:\n    match e:\n        case Exception(__traceback__=t):\n            result = 1",
     "__traceback__"),
    ("match 1:\n    case int(denominator=d):\n        result = d\n    case Exception(with_traceback=w):\n        result = 2",
     "with_traceback"),
    ("class A:\n    pass\nresult = 1", "class"),
    ("with a as f:\n    result = 1", "with"),
    ("async def f():\n    pass\nresult = 1", "async"),
    ("def f():\n    global x\nresult = 1", "global"),
    ("@print\ndef f():\n    pass\nresult = 1", "@"),
    ("try:\n    x = 1\nexcept:\n    pass\nresult = 1", "except"),
    ("_hidden = 1\nresult = _hidden", "_hidden"),
    ("def f(_x):\n    return 1\nresult = f(1)", "_x"),
    ("result = _tick", "_tick"),
    ("result = nothing_like_this", "nothing_like_this"),
    ("result = 1\nx: __import__ = 2", "__import__"),
    ("result = ｅｖａｌ('1')", "eval"),                           # full-width letters are the same names for Python
    ("result = ().＿＿class＿＿", "Python"),                       # (a full-width underscore is not even a name)
    ("result = ().__ｃｌａｓｓ__", "__class__"),
])
def test_what_reaches_outside_tensela_is_said_and_does_not_run(code, says):
    problem = check(code)
    assert problem is not None and says in str(problem)
    with pytest.raises(ShapeError):
        run(code, {})


def test_the_first_problem_is_the_one_reported_with_its_line():
    problem = check("x = 1\ny = 2\nimport os\nz = eval('3')")
    assert problem.line == 3 and "os" in problem.message
    assert check("for i in range(3)\n    pass").line == 1         # a slip of Python: its line too


def test_a_program_is_not_a_fragment():
    long = "\n".join(f"x{i} = {i}" for i in range(MAX_LINES + 50)) + "\nresult = 1"
    assert str(MAX_LINES) in str(check(long))
    assert check("") is not None and check("   \n") is not None


def test_no_dangerous_attribute_is_in_the_allowed_list():
    assert not any(n.startswith("_") for n in ALLOWED_ATTRIBUTES)
    assert not {"format", "format_map", "gi_frame", "f_globals", "mro", "args", "with_traceback"} & ALLOWED_ATTRIBUTES


def test_the_ordinary_things_of_python_pass():
    for code in ("def f(n):\n    return 1 if n < 2 else n * f(n - 1)\nresult = f(5)",
                 "total = 0\nfor i, x in enumerate([1, 2, 3]):\n    total += i * x\nresult = total",
                 "d = {}\nd['a'] = 1\nresult = sorted(d.items())[0][1]",
                 "result = [x for x in range(10) if x % 2]\n_ = 0",
                 "try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    x = 0\nresult = x",
                 "words = 'a b'.split()\nresult = len(f'{words[0]}!')",
                 "squares = list(map(lambda x: x * x, range(4)))\nresult = max(squares)"):
        assert check(code) is None, code
        run(code, {})


# --- Running it ----------------------------------------------------------------------------------------------

def test_mistakes_while_running_say_the_line():
    for code, line in (("x = 1\nresult = x / 0", 2), ("x = [1]\ny = 2\nresult = x[5]", 3),
                       ("def f(n):\n    return f(n + 1)\nresult = f(0)", 1)):
        with pytest.raises(ShapeError, match=str(line)):
            run(code, {})
    for code in ("x = 1", "result = 'text'", "result = []", "result = [1, point(0, 0)]",
                 "result = [mesh([point(0,0), point(1,0), point(1,1)], [(0, 1, 2)])] * 2",
                 "result = mesh([point(0,0)], [(0, 1, 5)])"):
        with pytest.raises(ShapeError):
            run(code, {})


@pytest.mark.parametrize("code", [
    "while True:\n    pass",
    "def f():\n    while True:\n        pass\nf()",
    "result = sum(1 for i in range(10 ** 7) for j in range(10 ** 7))",
    "result = [i for i in range(10 ** 7) for j in range(10 ** 7)][0]",
    "def f():\n    try:\n        while True:\n            pass\n    finally:\n        return 1\nwhile True:\n    f()",
    "for i in range(10 ** 7):\n    try:\n        for j in range(10 ** 7):\n            pass\n    finally:\n        continue",
])
def test_a_loop_that_does_not_end_is_stopped(code):
    t = time.time()
    with pytest.raises(ShapeError, match="0.3"):
        run(code, {}, seconds=0.3)
    assert time.time() - t < 3


def test_a_range_too_long_is_said():
    with pytest.raises(ShapeError, match="range"):
        run("result = sum(range(10 ** 12))", {})


# --- The node -------------------------------------------------------------------------------------------------

def test_the_node_shows_only_the_letters_its_code_reads():
    from tensela.nodes import CATALOG, visible_input
    g = Graph()
    n = g.node("Code", "c")
    shown = lambda: [i.name for i in CATALOG["Code"].inputs if visible_input(n, i)]   # noqa: E731
    assert shown() == ["code", "a", "b", "levels"]
    g.change(n, "code", "# h is only in a comment\nresult = a + d")
    assert shown() == ["code", "a", "b", "d", "levels"]
    assert g.value(g.node("Code", "new")).values.shape == (13, 3)      # a new node already shows something


def test_the_node_says_its_problem_and_is_saved_with_its_code():
    g = Graph()
    g.node("Code", "c", code="import os\nresult = 1")
    with pytest.raises(NodeError, match="os"):
        g.value("c")
    code = "# two lines\nresult = [point(i, i) for i in range(3)]\n"
    g.change("c", "code", code)
    q = from__text(to_text(Project(g, ["c"])))
    assert q.graph.nodes["c"].inputs["code"] == code and q.graph.value("c").values.shape == (3, 3)
    from tensela.values import text_of
    assert "2" in text_of("code", code)


SCRIPT = r'''
import os, sys
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela.ui import window
w = window.Window(); w._continue_without_saving = lambda: True; w.resize(1400, 900); w.show()

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

def run():
    w.open_(sys.argv[1]); w.wait_computation(); app.processEvents()
    node = w.project.graph.nodes["1 Koch in code"]
    w.edit_code("1 Koch in code"); pump(400)
    d = w._code_dialog
    good = d.code.toPlainText()
    assert good == node.inputs["code"] and d.code._problem_line == 0
    d.code.setPlainText("import os\n" + good); pump(400)
    assert d.code._problem_line == 1 and "os" in d.status.text()         # said while writing, with its line
    d.apply(); pump(200)
    assert node.inputs["code"] == good                                    # and it does not reach the node
    d.code.setPlainText(good.replace("rotated(60", "rotated(80")); pump(400)
    d.apply(); pump(200); w.wait_computation(); pump(400)
    assert "rotated(80" in node.inputs["code"] and d.code._problem_line == 0
    d.code.setPlainText(good.replace("int(b)", "int(b) / 0")); pump(400)
    d.apply(); pump(200); w.wait_computation(); pump(600)
    assert d.code._problem_line == 14, d.status.text()                    # what happened when it ran, in its line
    w.undo(); pump(300)
    print("ok", flush=True)
    os._exit(0)

def safely():
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(4)

QTimer.singleShot(500, safely)
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_a_project_with_code_is_counted_also_inside_groups():
    from tensela.groups import group
    from tensela.ui.window import _code_nodes
    g = Graph()
    assert _code_nodes(g) == 0
    g.node("Code", "loose")
    g.node("Number", "n", value=2.0)
    g.node("Code", "inside", code="result = a * 2", a=g.nodes["n"])
    g.node("Formula", "after", formula="a + 1", a=g.nodes["inside"])
    group(g, ["inside", "after"], "doubled")
    assert _code_nodes(g) == 2
