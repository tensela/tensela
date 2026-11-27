"""Which OpenGL the 3D view uses on Windows: the graphics card's, or the one drawn by the processor (Mesa llvmpipe).

Windows without a graphics card (a virtual machine, a remote desktop, a server) offers OpenGL 1.1 only, and the 3D
view needs 3.2: it would not open. The folder of Tensela for Windows carries Mesa in `mesa/` beside its Python. Before
the 3D view loads, a short process asks the system for OpenGL 3.2; if it cannot give it, Mesa is loaded first, and the
3D view takes it instead of the system's (a library already loaded is not looked for again). With a graphics card,
Mesa is never loaded: the card is much faster.

`TENSELA_OPENGL=system` or `=software` decides without asking; the processes started from Tensela inherit the choice.
Nothing of this happens outside Windows.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

#: Asks for OpenGL 3.2 the way the 3D view will (VTK), without a window, and draws a cube with it: «yes» only if the
#: cube came out. Some systems say they have it and cannot draw (Windows Server translates OpenGL to Direct3D, and
#: VTK breaks there); if the probe breaks, it is «no» too. The second line says which OpenGL it was.
PROBE = """
import vtkmodules.vtkRenderingOpenGL2
from vtkmodules.vtkFiltersSources import vtkCubeSource
from vtkmodules.vtkRenderingCore import (vtkActor, vtkPolyDataMapper, vtkRenderWindow, vtkRenderer,
                                         vtkWindowToImageFilter)
w = vtkRenderWindow(); w.SetOffScreenRendering(1); w.SetSize(48, 48)
if not w.SupportsOpenGL():
    print("no"); raise SystemExit
r = vtkRenderer(); r.SetBackground(0, 0, 0); w.AddRenderer(r)
c = vtkCubeSource()                                  # (kept: a source freed at once leaves the mapper empty)
m = vtkPolyDataMapper(); m.SetInputConnection(c.GetOutputPort())
a = vtkActor(); a.SetMapper(m); r.AddActor(a); r.ResetCamera()
w.Render()
f = vtkWindowToImageFilter(); f.SetInput(w); f.Update()
s = f.GetOutput().GetPointData().GetScalars()
print("yes" if any(max(s.GetTuple(i)) > 0 for i in range(s.GetNumberOfTuples())) else "no")
print(next((x for x in w.ReportCapabilities().splitlines() if "renderer string" in x), "").strip(), flush=True)
"""
PROBE_SECONDS = 30


def mesa_folder() -> Path:
    return Path(sys.executable).resolve().parent / "mesa"


def system_is_enough(timeout: float = PROBE_SECONDS) -> bool:
    try:
        done = subprocess.run([sys.executable, "-I", "-c", PROBE], capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "TENSELA_OPENGL": "system"},
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return False
    lines = done.stdout.splitlines()
    return done.returncode == 0 and bool(lines) and lines[0].strip() == "yes"


def load_mesa(folder: Path) -> None:
    """Mesa's two libraries loaded by their full path, its own one first: when the 3D view asks for opengl32.dll,
    Windows gives it the one already loaded."""
    import ctypes
    os.add_dll_directory(str(folder))
    ctypes.WinDLL(str(folder / "libgallium_wgl.dll"))
    ctypes.WinDLL(str(folder / "opengl32.dll"))
    os.environ.setdefault("GALLIUM_DRIVER", "llvmpipe")


def choose(probe=system_is_enough) -> str:
    """«system» or «software» (and then Mesa is loaded). Once per process; outside Windows, always «system»."""
    if sys.platform != "win32":
        return "system"
    folder = mesa_folder()
    choice = os.environ.get("TENSELA_OPENGL")
    if choice not in ("system", "software"):
        if not (folder / "opengl32.dll").is_file():
            choice = "system"                             # (a Tensela without Mesa beside it: from the sources)
        else:
            choice = "system" if probe() else "software"
    if choice == "software" and (folder / "opengl32.dll").is_file():
        load_mesa(folder)
    os.environ["TENSELA_OPENGL"] = choice                 # the same for the processes it starts, without asking again
    return choice
