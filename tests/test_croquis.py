"""Croquis inside Tensela (Delivery 4, step 5): the view and the geometry lent to it."""

from pathlib import Path

import numpy as np
import pytest

from tensela.project_file import open_
from tensela.croquis.view import Camera, SketchView, geometry_of
from tensela.data import Data
from tensela.geometry import box, circle, frame, prism, rectangle, surface_by_sections

EXAMPLES = Path(__file__).parent / "data"


# --- The geometry to remove hidden lines -------------------------------------

def test_a_box_has_12_triangles_and_12_hard_edges():
    tris, hard, soft, _ = geometry_of(box(1, 1, 1))
    assert tris.shape == (12, 3, 3) and hard.shape == (12, 2, 3) and len(soft) == 0


def test_two_pieces_give_twice():
    tris, hard, _, _ = geometry_of(box(Data(np.array([1.0, 2.0]), ("pieza",)), 1, 1))
    assert len(tris) == 24 and len(hard) == 24


def test_curves_are_edges_without_triangles():
    tris, hard, _, _ = geometry_of(circle(radius=1))
    assert len(tris) == 0 and len(hard) == 64


def test_between_faces_on_the_same_plane_there_is_no_line():
    # The front of a frame is four trapezoids on a plane: their joints are not drawn.
    m = frame(rectangle(2, 2, plane='elevation'), width=0.2)
    _, hard, _, _ = geometry_of(m)
    assert len(hard) == 8                     # the outer edge and that of the opening: 4 + 4


def test_a_curved_surface_has_soft_edges():
    from tensela.geometry import point
    sections = circle(radius=Data(np.array([1.0, 2.0, 1.0]), ("sección",)),
                        centre=point(0, 0, Data(np.array([0.0, 1.0, 2.0]), ("sección",))))
    skin = surface_by_sections(sections, along="sección")
    _, hard, soft, normals = geometry_of(skin)
    assert len(soft) > 0 and normals.shape == (len(soft), 2, 3)
    assert len(hard) < len(soft)           # only the edges are hard


def test_the_transparent_does_not_cover():
    view = SketchView([("vidrio", rectangle(1, 1), {"opacity": 0.5}),
                          ("muro", prism(1, 1, 1), {})], _camera())
    assert len(view.tris) == 12 and set(view.from_object) == {1}
    assert len(view.hlr_geometry()[1]) == 4 + 12   # the edges of the glass are drawn


# --- The camera -------------------------------------------------------------------

def _camera(perspective=True):
    return Camera((8, -10, 6), (0, 0, 1), (0, 0, 1), 1.5, perspective, 30, 3, 0.5, 60)


@pytest.mark.parametrize('perspective', [True, False])
def test_the_camera_is_like_qts(perspective):
    QtGui = pytest.importorskip("PySide6.QtGui")
    cam = _camera(perspective)
    p, v = QtGui.QMatrix4x4(), QtGui.QMatrix4x4()
    if perspective:
        p.perspective(30, 1.5, 0.5, 60)
    else:
        p.ortho(-4.5, 4.5, -3, 3, 0.5, 60)
    v.lookAt(QtGui.QVector3D(8, -10, 6), QtGui.QVector3D(0, 0, 1), QtGui.QVector3D(0, 0, 1))
    assert np.allclose((cam.projection_matrix() * cam.view_matrix()).data(), (p * v).data(), atol=1e-5)


def test_the_croquis_engine_does_not_need_qt():
    import subprocess
    import sys
    code = ("import sys; import tensela.croquis, tensela.croquis.visibility, tensela.connectors.dxf;"
              "print('PySide6' in sys.modules)")
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "False"


# --- The drawing and its outputs (with Qt) ---------------------------------------------


def test_the_names_come_out_in_spanish_before_drawing():
    import subprocess
    import sys
    code = ("from tensela.croquis import texts, presets, paper;"
              "print(texts.tr(presets.PRESETS['colour_marker'][0]), texts.tr(paper.PAPERS['cream'][0]))")
    output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
    assert output == "Rotulador color Crema"


def test_big_triangles_one_over_another_are_drawn_as_pixel_by_pixel(monkeypatch):
    """The depth buffer of big triangles (row by row, from the nearest, skipping the rows behind what is drawn) is the
    one of testing every pixel against every triangle: a stack of big slabs, as a tower seen from above."""
    from tensela.croquis import visibility as vis
    rng = np.random.default_rng(7)
    slabs = []
    for k in range(12):                                          # twelve squares turning, one over the other
        a = np.deg2rad(7 * k)
        c = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]) @ np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]).T
        corners = np.column_stack([c.T * (0.8 + 0.02 * k), np.full(4, 0.3 * k)])
        slabs += [corners[[0, 1, 2]], corners[[0, 2, 3]]]
    tris = np.array(slabs) + rng.normal(0, 1e-3, (len(slabs), 3, 3))
    camera = Camera(np.array([0, 0, 10.0]), np.zeros(3), np.array([0, 1.0, 0]), 1.0, perspective=False,
                    middle_height=1.3, near=1.0, far=20.0)
    W = H = 160
    monkeypatch.setattr(vis._fill_big, "__defaults__", (4_000_000, 60))   # small batches: the rows behind are skipped
    zbuf, index = vis.depth_buffer(tris, vis.clip_matrix(camera), W, H, False)
    C, src = vis._clip_triangles(vis.to_clip(tris.reshape(-1, 3), vis.clip_matrix(camera)).reshape(-1, 3, 4))
    X, Y, Q = vis._screen(C, W, H, False)
    px, py = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    best, which = np.full((H, W), -np.inf), np.full((H, W), -1)
    for t in range(len(C)):
        (ax, bx, cx), (ay, by, cy) = X[t], Y[t]
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        w0 = ((bx - px) * (cy - py) - (cx - px) * (by - py)) / area
        w1 = ((cx - px) * (ay - py) - (ax - px) * (cy - py)) / area
        w2 = 1 - w0 - w1
        q = w0 * Q[t, 0] + w1 * Q[t, 1] + w2 * Q[t, 2]
        nearer = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6) & (q > best)
        best[nearer], which[nearer] = q[nearer], src[t]
    assert np.array_equal(np.isfinite(zbuf), np.isfinite(best))
    assert np.allclose(zbuf[np.isfinite(best)], best[np.isfinite(best)], atol=1e-9)
    seen = np.isfinite(best)
    assert (index[seen] == which[seen]).mean() > 0.995           # (on a shared edge either triangle may win)
