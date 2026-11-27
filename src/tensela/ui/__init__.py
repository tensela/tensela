"""The graphical interface (Delivery 1). It needs the optional dependencies: pip install -e ".[ui]"."""
import os
import sys

if sys.platform == "win32":
    # The preferences in a file, as on Linux, not in the registry of Windows: %APPDATA%\Tensela\Tensela.ini, or under
    # XDG_CONFIG_HOME when it is set (the tests, a portable folder). Before any QSettings is made.
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    if os.environ.get("XDG_CONFIG_HOME"):
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, os.environ["XDG_CONFIG_HOME"])
    # The OpenGL of the 3D view: the graphics card's, or Mesa beside Python when the system cannot give 3.2 (a virtual
    # machine, a remote desktop). Before the 3D view loads (ui/opengl_choice.py).
    from .opengl_choice import choose
    choose()
