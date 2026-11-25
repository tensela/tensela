"""Tensela in the applications menu, when it runs from its AppImage.

An AppImage is a single file the desktop does not know about: no entry in the menu, the icon of the window generic, and
a `.tela` does not open with a double click. Tensela offers to fix that the first time (and Preferences can do it or
undo it later). Everything goes into the folders of the person, never into the system:

- the launcher: `~/.local/share/applications/tensela.desktop`, which starts this AppImage (wherever it is);
- the icons of Tensela and of its files: `~/.local/share/icons/hicolor/<size>/{apps,mimetypes}/`;
- the file type: `~/.local/share/mime/packages/tensela.xml` (`*.tela` is a Tensela project).

If the AppImage is moved or replaced by a newer one, the next time it opens the launcher is pointed at it.

Nothing here needs Qt: tools/build_appimage.py takes the launcher and the file type from here too.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

BRAND = Path(__file__).resolve().parent / "brand"
NAME = "tensela.desktop"
APP_SIDES = (16, 24, 32, 48, 64, 128, 256, 512)
FILE_SIDES = (16, 32, 48, 64, 128, 256)
#: The line of the launcher that says which AppImage it was made for.
MARK = "X-Tensela-AppImage"

#: Only keys that older validators know too (Ubuntu 22.04 refuses SingleMainWindow, and so did the catalogue of
#: AppImages); the test lists them.
ENTRY = """[Desktop Entry]
Type=Application
Name=Tensela
GenericName=Parametric design
GenericName[es]=Diseño paramétrico
Comment=Parametric design an architect understands
Comment[es]=Diseño paramétrico que un arquitecto entiende
Exec={exec} %F
Icon=tensela
Terminal=false
Categories=Graphics;3DGraphics;Engineering;
MimeType=application/x-tensela;
StartupWMClass=tensela
Keywords=parametric;architecture;nodes;design;facade;
Keywords[es]=paramétrico;arquitectura;nodos;diseño;fachada;
"""

MIME = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-tensela">
    <comment>Tensela project</comment>
    <comment xml:lang="es">Proyecto de Tensela</comment>
    <sub-class-of type="application/json"/>
    <icon name="application-x-tensela"/>
    <glob pattern="*.tela"/>
  </mime-type>
</mime-info>
"""


def entry(command: str = "tensela", appimage: str | None = None) -> str:
    """The launcher: `command` is what Exec starts (already quoted); with `appimage`, the mark of which one."""
    text = ENTRY.format(exec=command)
    if appimage:
        text += f"TryExec={appimage}\n{MARK}={appimage}\n"
    return text


def quote(path: str) -> str:
    """A path as the Exec line of a launcher wants it: between double quotes, with \\, ", ` and $ escaped (and each
    backslash doubled once more, because the value of the line is a string too)."""
    inner = "".join("\\" + c if c in '"`$\\' else c for c in path)
    return '"' + inner.replace("\\", "\\\\") + '"'


def appimage() -> Path | None:
    """What starts this Tensela from the menu: the AppImage it runs from (its runtime says it in APPIMAGE), or the
    launcher of its portable folder (`./tensela`, which says it in TENSELA_PORTABLE); None when it runs from the code."""
    path = os.environ.get("APPIMAGE") or os.environ.get("TENSELA_PORTABLE")
    return Path(path) if path and Path(path).is_file() else None


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))


def entry_path() -> Path:
    return data_home() / "applications" / NAME


def installed_for() -> str | None:
    """The AppImage the launcher in the menu starts, if Tensela put one there."""
    try:
        for line in entry_path().read_text(encoding="utf-8").splitlines():
            if line.startswith(MARK + "="):
                return line.split("=", 1)[1]
    except OSError:
        pass
    return None


def files() -> list[Path]:
    """Every file `install` writes."""
    home = data_home()
    icons = home / "icons" / "hicolor"
    out = [entry_path(), home / "mime" / "packages" / "tensela.xml"]
    out += [icons / f"{s}x{s}" / "apps" / "tensela.png" for s in APP_SIDES]
    out += [icons / f"{s}x{s}" / "mimetypes" / "application-x-tensela.png" for s in FILE_SIDES]
    out += [icons / "scalable" / "apps" / "tensela.svg", icons / "scalable" / "mimetypes" / "application-x-tensela.svg"]
    return out


def install(image: Path) -> list[Path]:
    """Puts Tensela in the menu, starting the AppImage `image`. Returns the files written."""
    image = Path(image).resolve()
    home = data_home()
    icons = home / "icons" / "hicolor"
    sources = [None, None] + [BRAND / f"tensela-{s}.png" for s in APP_SIDES] \
        + [BRAND / f"application-x-tensela-{s}.png" for s in FILE_SIDES] \
        + [BRAND / "tensela.svg", BRAND / "application-x-tensela.svg"]
    written = []
    for target, source in zip(files(), sources):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target == entry_path():
            target.write_text(entry(quote(str(image)), str(image)), encoding="utf-8")
            target.chmod(0o755)
        elif source is None:
            target.write_text(MIME, encoding="utf-8")
        else:
            shutil.copyfile(source, target)
        written.append(target)
    refresh()
    return written


def uninstall() -> list[Path]:
    """Takes Tensela out of the menu: the files `install` wrote. Returns the ones removed."""
    removed = []
    for path in files():
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            pass
    refresh()
    return removed


def follow_move() -> bool:
    """If the launcher starts an AppImage that is no longer there and Tensela runs from another one (moved, or a newer
    one), the launcher is pointed at this one. Returns whether it was."""
    image, before = appimage(), installed_for()
    if image is None or before is None or Path(before) == image.resolve() or Path(before).is_file():
        return False
    install(image)
    return True


def refresh() -> None:
    """Tells the desktop: the list of applications, the file types and (if it keeps one) the cache of icons."""
    home = data_home()
    commands = [["update-desktop-database", "-q", str(home / "applications")],
                ["update-mime-database", str(home / "mime")]]
    cache = home / "icons" / "hicolor"
    if (cache / "icon-theme.cache").is_file():
        commands.append(["gtk-update-icon-cache", "-q", "-t", "-f", str(cache)])
    for command in commands:
        if shutil.which(command[0]) and Path(command[-1]).is_dir():
            try:
                subprocess.run(command, capture_output=True, timeout=20, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
