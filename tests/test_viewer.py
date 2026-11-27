"""The conversion from the engine to the 3D view (Delivery 1). Skipped if the interface is not there."""

import numpy as np
import pytest

pytest.importorskip("pyvista")
pytest.importorskip("PySide6")

from tensela.data import Data, ShapeError  # noqa: E402
from tensela.geometry import box, place, point, rectangle, grid  # noqa: E402
from tensela.ui.viewer import to_mesh  # noqa: E402


def test_a_box_is_a_mesh_of_6_faces():
    mesh = to_mesh(box(1, 2, 3))
    assert mesh.n_points == 8 and mesh.n_cells == 6
    assert np.allclose(np.array(mesh.bounds), [-0.5, 0.5, -1, 1, -1.5, 1.5])


def test_many_elements_in_a_single_mesh():
    panels = grid(rectangle(20, 12, plane='elevation'), cell_width=1, cell_height=1)
    mesh = to_mesh(panels)
    assert mesh.n_cells == 240 and mesh.n_points == 960


def test_only_the_elements_that_exist():
    heights = Data.from_lists([[0.0, 1.0, 2.0], [0.0]], ("columna", "pieza"))
    pieces = place(box(1, 1, 1), at=point(0, 0, heights))
    assert to_mesh(pieces).n_cells == 4 * 6


def test_points_show_as_points():
    centres = point(Data(np.arange(5.0), ("panel",)), 0, 0)
    mesh = to_mesh(centres)
    assert mesh.n_points == 5 and mesh.n_cells == 5


def test_curves_show_as_lines():
    from tensela.geometry import circle, line
    c = to_mesh(circle(radius=2))
    assert c.n_points == 64 and c.n_lines == 1
    assert to_mesh(line((0, 0, 0), (1, 0, 0))).n_lines == 1


def test_a_number_is_not_shown():
    with pytest.raises(ShapeError, match="no se puede mostrar en 3D: es un número"):
        to_mesh(Data.value(3.0, "altura"))


@pytest.mark.parametrize('style_name', ["solid", "model", "wireframe", "hidden lines", "x-ray", "occlusion"])
def test_each_view_style_is_drawn(style_name):
    import pyvista as pv
    from tensela.ui.viewer import STYLE_NAMES, draw, prepare
    assert style_name in STYLE_NAMES
    pl = pv.Plotter(off_screen=True, window_size=(120, 80))
    prepare(pl)
    actor = draw(pl, "caja", box(1, 1, 1), "#ff0000", 1.0, style_name_view=style_name, paper="#ffffff", ink="#000000")
    if style_name == "wireframe":
        assert actor.prop.style == "Wireframe"
    if style_name == "x-ray":
        assert actor.prop.opacity <= 0.25
    if style_name == "hidden lines":
        assert actor.prop.show_edges and actor.prop.color.hex_rgb == "#ffffff"
    if style_name == "model":
        from tensela.ui.studio import MODEL_COLOUR
        assert actor.prop.color.hex_rgb == MODEL_COLOUR                 # everything white
    if style_name in ("solid", "model"):
        assert "caja·outline" in pl.actors                              # with its outlines
    pl.close()


def test_outlines_can_be_left_out():
    import pyvista as pv
    from tensela.ui.viewer import draw, prepare
    pl = pv.Plotter(off_screen=True, window_size=(120, 80))
    prepare(pl)
    draw(pl, "caja", box(1, 1, 1), "#ff0000", 1.0, style_name_view="solid", paper="#ffffff", ink="#000000",
         outlines=False)
    assert "caja·outline" not in pl.actors
    pl.close()


def test_the_old_shadows_style_opens_in_studio():
    from tensela.ui.viewer import STYLE_NAMES
    assert "shadows" not in STYLE_NAMES                                   # left out: its shadow maps had artefacts


def test_clearing_does_not_take_the_lights():
    import pyvista as pv
    from tensela.ui.viewer import light_up
    pl = pv.Plotter(off_screen=True)
    light_up(pl)
    pl.clear()
    light_up(pl)
    assert len(pl.renderer.lights) == 2
    pl.close()


def test_recomputing_does_not_redo_what_did_not_change():
    """Viewer.display skips a result that is already seen the same (same data, colour, numbers and gradient)."""
    from types import SimpleNamespace
    from tensela.ui.viewer import Viewer
    data = box(1, 1, 1)
    v = SimpleNamespace(_actors={"c": object()}, _data_items={"c": (data, "#fff", 1.0, None)}, _number=set(),
                        _colour_by={"c": (np.array([1.0, 2.0]), "calor")})
    equal = lambda *a: Viewer._already_sees(v, "c", *a)           # noqa: E731
    assert equal(data, "#fff", 1.0, None, None, ...)
    assert equal(data, "#fff", 1.0, None, False, (np.array([1.0, 2.0]), "calor"))
    assert not equal(box(1, 1, 1), "#fff", 1.0, None, None, ...)          # another result
    assert not equal(data, "#000", 1.0, None, None, ...)
    assert not equal(data, "#fff", 1.0, None, True, ...)                   # now with numbers
    assert not equal(data, "#fff", 1.0, None, None, (np.array([1.0, 3.0]), "calor"))
    assert not equal(data, "#fff", 1.0, None, None, None)                  # now without gradient


def test_a_long_legend_title_is_wrapped():
    from tensela.ui.viewer import _wrap
    t = _wrap("1 free surface as a mesh: faces")
    assert "\n" in t and all(len(line) <= 22 for line in t.split("\n"))


def test_legends_stay_inside_a_narrow_view():
    import pyvista as pv
    from tensela.ui import viewer as V
    from tensela.graph import Graph
    from tensela.data import Data
    g = Graph()
    g.node("Rectangle", "r", width=4.0, height=2.0)
    g.node("Grid", "a long name for some panels", rectangle=g.nodes["r"], columns=4, rows=2)
    d = g.value("a long name for some panels")
    for side in ("left", "right"):
        V.LEGENDS["side"] = side
        pl = pv.Plotter(off_screen=True, window_size=(300, 400))
        V.prepare(pl, axes=False)
        V.draw(pl, "a long name for some panels", d, colour_by=(np.arange(8.0), "cool to warm"))
        bar = next(iter(pl.scalar_bars.values()))
        x, y = bar.GetPositionCoordinate().GetValue()[:2]
        assert 0 <= x and x + bar.GetWidth() <= 1.0001
        pl.close()
    V.LEGENDS["side"] = "right"


def test_legends_follow_the_view_when_it_changes_size_and_do_not_overlap():
    import pyvista as pv
    from tensela.ui import viewer as V
    from tensela.graph import Graph
    g = Graph()
    g.node("Rectangle", "r", width=4.0, height=2.0)
    g.node("Grid", "panels", rectangle=g.nodes["r"], columns=4, rows=2)
    d = g.value("panels")
    V.LEGENDS.update(side="right", top=V.GIZMO_PIXELS)
    pl = pv.Plotter(off_screen=True, window_size=(1000, 700))
    V.prepare(pl, axes=False)
    V.draw(pl, "varied", d, colour_by=(np.arange(8.0), "cool to warm"))
    for name in ("same one", "same two"):
        V.draw(pl, name, d, colour_by=(np.zeros(8), "cool to warm"))
    pl.window_size = (600, 420)                     # the window settles later: placed again before painting
    pl.render()
    w, h = pl.window_size
    boxes = []
    for bar in pl.scalar_bars.values():
        x, y = bar.GetPositionCoordinate().GetValue()[:2]
        boxes.append((x * w, y * h, (x + bar.GetWidth()) * w, (y + bar.GetHeight()) * h))
        assert x >= 0 and x + bar.GetWidth() <= 1.0001 and y + bar.GetHeight() <= 1.0001
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] + 0.5 or b[2] <= a[0] + 0.5 or a[3] <= b[1] + 0.5 or b[3] <= a[1] + 0.5
    pl.close()
    V.LEGENDS.update(side="right", top=0)


def test_the_look_of_the_view_is_saved_with_the_project(tmp_path):
    from tensela.graph import Graph
    from tensela.project_file import Project, open_, save
    g = Graph()
    g.node("Box", "b")
    save(Project(g, ["b"], look={"style": "model", "outlines": False}), tmp_path / "p.json")
    assert open_(tmp_path / "p.json").look == {"style": "model", "outlines": False}
    save(Project(g, ["b"]), tmp_path / "q.json")
    assert open_(tmp_path / "q.json").look == {}


def test_software_rendering_is_told_by_the_renderer_name():
    from types import SimpleNamespace
    from tensela.ui.viewer import software_rendering
    says = lambda text: SimpleNamespace(ReportCapabilities=lambda: text)        # noqa: E731
    assert software_rendering(says("OpenGL vendor string:  Mesa\nOpenGL renderer string:  llvmpipe (LLVM 21, 256 bits)"))
    assert software_rendering(says("OpenGL renderer string:  SwiftShader Device"))
    assert software_rendering(says("OpenGL renderer string:  AMD Radeon Graphics (radeonsi)")) is False
    assert software_rendering(says("")) is None                                 # not drawn yet
    assert software_rendering(SimpleNamespace(ReportCapabilities=lambda: 1 / 0)) is None


def test_without_a_graphics_card_every_style_smooths_with_fxaa(monkeypatch):
    """Drawn by the processor, SSAA made the line styles three times slower while orbiting."""
    from types import SimpleNamespace
    from tensela.ui import viewer
    chosen = []
    monkeypatch.setattr(viewer, "smooth_edges", lambda view, kind: chosen.append(kind))
    view = SimpleNamespace(disable_anti_aliasing=lambda: None)
    for software, style, expected in ((False, "wireframe", "ssaa"), (False, "solid", "fxaa"),
                                      (True, "wireframe", "fxaa"), (True, "hidden lines", "fxaa"),
                                      (None, "x-ray", "ssaa")):
        viewer.Viewer._smooth_edges(SimpleNamespace(view=view, style_name=style, software=software))
        assert chosen[-1] == expected, (software, style)


def test_fxaa_goes_straight_to_vtk():
    """pyvista takes VTK on Windows for a build without windows and changes FXAA for SSAA, which broke drawing with
    Mesa: FXAA is turned on in each renderer, without asking pyvista."""
    from types import SimpleNamespace
    from tensela.ui.viewer import smooth_edges
    asked, renderers = [], [SimpleNamespace(on=None, SetUseFXAA=None, Modified=lambda: None) for _ in range(2)]
    for r in renderers:
        r.SetUseFXAA = lambda yes, r=r: setattr(r, "on", yes)
    plotter = SimpleNamespace(renderers=renderers, enable_anti_aliasing=asked.append)
    smooth_edges(plotter, "fxaa")
    assert all(r.on is True for r in renderers) and asked == []
    smooth_edges(plotter, "ssaa")
    assert asked == ["ssaa"]


def test_a_renderer_that_never_says_counts_as_a_graphics_card():
    from types import SimpleNamespace
    from tensela.ui.viewer import Viewer
    v = SimpleNamespace(view=SimpleNamespace(ren_win=SimpleNamespace(ReportCapabilities=lambda: "")), software=None)
    for _ in range(3):
        Viewer._learn_renderer(v)
    assert v.software is False


def test_the_sky_is_gathered_lightly_so_the_window_does_not_wait():
    """VTK's own gathering of the light of the sky took 45 s without a graphics card (the window waited); Tensela
    asks for a coarser one, which gives the same image."""
    import pyvista as pv
    from tensela.ui import studio
    from tensela.ui.viewer import prepare
    pl = pv.Plotter(off_screen=True)
    prepare(pl)
    assert pl.renderer.GetEnvMapIrradiance().GetIrradianceStep() == pytest.approx(studio.IRRADIANCE_STEP)
    pl.close()
