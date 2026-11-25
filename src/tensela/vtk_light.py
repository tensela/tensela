"""The few VTK classes the engine uses, each loaded from its own module when first asked for.

``import vtk`` loads the whole library (close to a second the first time, more with a cold disk): the first Delaunay
of a session took half a second with 150 points. Here only the module of each class is loaded, so the engine writes
``from . import vtk_light as vtk`` and keeps using ``vtk.vtkPoints`` and the rest as before.
"""
from importlib import import_module

_WHERE = {
    "vtkPoints": "vtkCommonCore",
    "vtkIdList": "vtkCommonCore",
    "vtkPolyData": "vtkCommonDataModel",
    "vtkCellArray": "vtkCommonDataModel",
    "vtkPolygon": "vtkCommonDataModel",
    "vtkImageData": "vtkCommonDataModel",
    "vtkStaticCellLocator": "vtkCommonDataModel",
    "vtkModifiedBSPTree": "vtkFiltersFlowPaths",
    "vtkDelaunay2D": "vtkFiltersCore",
    "vtkFlyingEdges3D": "vtkFiltersCore",
    "vtkCleanPolyData": "vtkFiltersCore",
    "vtkStripper": "vtkFiltersCore",
    "vtkImplicitPolyDataDistance": "vtkFiltersCore",
    "vtkIntersectionPolyDataFilter": "vtkFiltersGeneral",
}


def __getattr__(name: str):
    if name not in _WHERE:
        raise AttributeError(f"vtk_light has no {name}: add it to _WHERE with its module")
    found = getattr(import_module(f"vtkmodules.{_WHERE[name]}"), name)
    globals()[name] = found                                   # the next time, straight from here
    return found


def nearby_order(xy):
    """An order of some points on a plane where each one comes near the one before (along a Z-shaped curve that
    fills the square). VTK's Delaunay adds the points one by one and walks to each from the triangle of the last
    one: in this order the walk is short. 200 000 random points went from 50 s to 2 s, with the same triangles."""
    import numpy as np
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 64:
        return np.arange(len(xy))
    low = xy.min(axis=0)
    size = max(float(np.ptp(xy, axis=0).max()), 1e-300)
    cells = ((xy - low) / size * 65535).astype(np.uint64)

    def spread(v):                                   # the 16 bits of v, with a zero between each two
        for shift, mask in ((8, 0x00FF00FF), (4, 0x0F0F0F0F), (2, 0x33333333), (1, 0x55555555)):
            v = (v | (v << np.uint64(shift))) & np.uint64(mask)
        return v
    return np.argsort(spread(cells[:, 0]) | (spread(cells[:, 1]) << np.uint64(1)), kind="stable")


#: The most triangles a tree for rays may hold (a million takes about 150 MB and a second): beyond, VTK could run
#: out of memory, and then it aborts the whole program instead of saying so.
MAX_TREE_TRIANGLES = 3_000_000


def ray_tree(triangles):
    """VTK's spatial index over some triangles (k, 3, 3), to ask which ones a ray (a line) crosses."""
    import numpy as np
    import pyvista as pv
    from .data import ShapeError, _number
    from .language import tr
    triangles = np.asarray(triangles, dtype=float)
    if len(triangles) > MAX_TREE_TRIANGLES:
        raise ShapeError(tr('Too many faces to follow the rays of the sun ({n} triangles; at most {maximum}): use '
                            'fewer cells in the surfaces.').format(n=_number(len(triangles)),
                                                                   maximum=_number(MAX_TREE_TRIANGLES)))
    faces = np.hstack([np.full((len(triangles), 1), 3), np.arange(3 * len(triangles)).reshape(-1, 3)]).ravel()
    tree = __getattr__("vtkModifiedBSPTree")()
    tree.SetDataSet(pv.PolyData(triangles.reshape(-1, 3), faces))
    tree.BuildLocator()
    return tree
