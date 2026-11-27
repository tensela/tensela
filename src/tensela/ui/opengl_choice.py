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

#: Asks for OpenGL 3.2 the way the 3D view will (VTK), without a window: «yes» or «no». If it breaks, it is «no».
PROBE = ("import vtkmodules.vtkRenderingOpenGL2, vtkmodules.vtkRenderingCore as r\n"
         "w = r.vtkRenderWindow(); w.SetOffScreenRendering(1)\n"
         "print('yes' if w.SupportsOpenGL() else 'no', flush=True)\n")
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
    return done.returncode == 0 and done.stdout.strip() == "yes"


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
