"""Group 3.7 of the pending plan: the security review. A project file made to break the program (or to do harm) gives
a clear notice; the theme's images go to a folder of the user's own; the Code node stays closed in."""
import os
import stat
from pathlib import Path

import pytest

from tensela.data import ShapeError
from tensela.graph import Graph, NodeError
from tensela.project_file import from__text, open_

DAMAGED = {
    "too nested": '{"parametrico": 1, "nodes": {"a": {"type": "Number", "value": ' + "[" * 100000 + "]" * 100000
                  + '}}}',
    "not json": "hello",
    "a control that is not a number": '{"parametrico": 1, "nodes": {"a": {"type": "Number"}}, "controls": '
                                      '[{"value": "a.value", "min": "x", "max": 1}]}',
    "a group without its output": '{"parametrico": 1, "groups": {"g": {"nodes": {}, "inputs": {}, "output": "x"}}, '
                                  '"nodes": {"n": {"type": "g"}}}',
    "a group that holds itself": '{"parametrico": 1, "groups": {"g": {"nodes": {"x": {"type": "g"}}, "inputs": {}, '
                                 '"output": "x"}}, "nodes": {"n": {"type": "g"}}}',
    "two groups that hold each other": '{"parametrico": 1, "groups": {"g": {"nodes": {"x": {"type": "h"}}, '
                                       '"inputs": {}, "output": "x"}, "h": {"nodes": {"y": {"type": "g"}}, '
                                       '"inputs": {}, "output": "y"}}, "nodes": {"n": {"type": "g"}}}',
}


@pytest.mark.parametrize("case", list(DAMAGED))
def test_a_damaged_project_gives_a_clear_notice(case):
    with pytest.raises(ShapeError):
        from__text(DAMAGED[case])


def test_opening_what_is_not_a_project_file_gives_a_notice(tmp_path):
    with pytest.raises(ShapeError):
        open_(tmp_path)                                          # a folder
    binary = tmp_path / "binary.json"
    binary.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(ShapeError):
        open_(binary)


@pytest.mark.skipif(not Path("/dev/zero").exists(), reason="a system without /dev/zero")
def test_a_device_is_not_read_as_a_weather_file_or_an_image():
    g = Graph()
    g.node("Climate", "c", file="/dev/zero")
    with pytest.raises(NodeError, match="/dev/zero|zero"):
        g.value("c")
    from tensela.images import read
    with pytest.raises(ShapeError):
        read("/dev/zero")


def test_the_theme_images_go_to_a_folder_of_the_user(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    from tensela.ui.theme import _own_folder
    folder = _own_folder()
    assert folder == tmp_path / "cache" / "tensela" / "theme"
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700           # only its owner reads and writes there


@pytest.mark.parametrize("code", [
    "match 1:\n    case int(__class__=c):\n        result = 1",
    "result = ().__class__.__bases__[0].__subclasses__()",
    "s = '{0' + '._' + '_class_' + '_}'\nresult = s.format(1)",
    "import os\nresult = os.system('true')",
])
def test_the_code_node_stays_closed_in(code):
    g = Graph()
    g.node("Code", "c", code=code)
    with pytest.raises(NodeError):
        g.value("c")


def test_a_huge_surface_says_so_before_making_it():
    """700 000 sections become 5.6 million faces: before, the memory could run out in the middle of making them and
    the program closed (the window computes with a memory limit)."""
    import numpy as np
    from tensela.data import Data
    from tensela.geometry import CURVE, kind_surface, surface_by_sections
    with pytest.raises(ShapeError, match="faces|caras"):
        kind_surface(800_009, 258)
    n = 700_000
    sections = np.zeros((n, 2, 3))
    sections[:, 1, 0] = 1.0
    sections[:, :, 2] = np.arange(n)[:, None]
    with pytest.raises(ShapeError, match="faces|caras"):
        surface_by_sections(Data(sections, ("section",), "s", kind=CURVE), "section", smooth=False)


def test_a_flat_body_is_not_given_to_vtk():
    """A box of height 0 among the supports of a Topology optimization: VTK's test of the points inside it broke its
    memory, and the program closed a while later. It holds no cell: it is left out."""
    pv = pytest.importorskip("pyvista")
    from tensela.geometry import box
    from tensela.topology import _bodies, _has_volume, _in_bodies
    import numpy as np
    flat, solid = _bodies(box(2, 2, 0), "supports")[0], _bodies(box(2, 2, 2), "supports")[0]
    assert not _has_volume(flat) and _has_volume(solid)
    points = np.array([[1.0, 1.0, 1.0], [5.0, 5.0, 5.0]])
    assert _in_bodies(points, [flat, solid]).tolist() == [True, False]


@pytest.mark.parametrize("gravity", [(), "x", [0, 0], [float("nan"), 0, -1]])
def test_a_gravity_that_is_not_a_direction_says_so(gravity):
    from tensela.geometry import gravity_direction
    with pytest.raises(ShapeError, match="gravity|gravedad"):
        gravity_direction(gravity)


def test_a_number_where_a_geometry_goes_says_so():
    g = Graph()
    g.node("Box", "b")
    g.node("Join meshes", "j", a=g.nodes["b"], b=0)
    with pytest.raises(NodeError) as error:
        g.value("j")
    assert isinstance(error.value.__cause__, ShapeError)                 # a notice, not an error of the program


def test_too_many_faces_for_the_rays_say_so(monkeypatch):
    """Tens of millions of triangles: VTK ran out of memory building its tree and aborted the program."""
    pytest.importorskip("pyvista")
    import numpy as np
    from tensela import vtk_light
    monkeypatch.setattr(vtk_light, "MAX_TREE_TRIANGLES", 10)
    with pytest.raises(ShapeError, match="rays|rayos"):
        vtk_light.ray_tree(np.zeros((11, 3, 3)))
    assert vtk_light.ray_tree(np.random.default_rng(0).random((10, 3, 3))) is not None


EXAMPLES = Path(__file__).parent / "data"


def test_a_huge_smooth_grid_says_so_before_making_it():
    """100 000 columns of points, smooth: 45 million faces. Making them closed the program."""
    g = Graph()
    g.node("Series", "x", count=100_000, level="column")
    g.node("Series", "y", count=29, level="row")
    g.node("Point", "p", x=g.nodes["x"], y=g.nodes["y"])
    g.node("Surface from points", "s", points=g.nodes["p"], smooth=True)
    with pytest.raises(NodeError, match="faces|caras") as error:
        g.value("s")
    assert isinstance(error.value.__cause__, ShapeError)


def test_numpy_out_of_memory_inside_an_operation_is_a_notice(monkeypatch):
    """numpy wraps a MemoryError in a SystemError when the memory runs out in the middle of an operation."""
    g = Graph()
    g.node("Box", "b")

    def without_memory(*_, **__):
        try:
            raise MemoryError()
        except MemoryError as error:
            raise SystemError("<ufunc 'multiply'> returned a result with an exception set") from error

    from tensela import geometry
    monkeypatch.setattr(geometry, "box", without_memory)
    with pytest.raises(NodeError, match="memory|memoria") as error:
        g.value("b")
    assert isinstance(error.value.__cause__, MemoryError)
