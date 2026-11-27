"""The folder of Tensela for Windows, in a .zip: unpacked anywhere, Tensela.exe opens it (nothing to install).

It runs on Windows (the machine of GitHub Actions, .github/workflows/windows-folder.yml). Everything comes from the
lock (tools/appimage.lock.json) and is checked against it before it is used:

- the portable Python for Windows (python-build-standalone, `python_windows`), checked by its SHA-256;
- the libraries, the same versions as the AppImage, their wheels for Windows by their hashes
  (tools/windows-requirements.txt, written by `tools/appimage_lock.py --windows`);
- Mesa (`mesa_windows`): the OpenGL drawn by the processor, in python/mesa/, which Tensela loads only when the
  computer has no OpenGL 3.2 of its own (ui/opengl_choice.py).

The folder:

    Tensela-<version>-windows-x64/
        Tensela.exe          the window (it starts python/pythonw.exe with Tensela)
        tensela-cli.exe      the same as `tensela` on Linux: computes a project and exports it, in a terminal
        README.txt
        python/              the portable Python, the libraries, Tensela, and mesa/

The two .exe are the launchers pip uses for the programs of a library (from distlib, inside pip), with the path of
Python written relative to themselves: the folder works wherever it is unpacked.

    python tools/build_windows.py            # → build/windows/Tensela-<version>-windows-x64.zip
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "windows"
DOWNLOADS = BUILD / "downloads"
LOCK = ROOT / "tools" / "appimage.lock.json"
REQUIREMENTS = ROOT / "tools" / "windows-requirements.txt"

#: Parts of the standard library that an app does not need (as in the AppImage).
STDLIB_OUT = ["test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data"]
#: Inside the libraries: the tools of Qt for developers, its headers and stubs, and its other translations.
TRIM = ["PySide6/*.exe", "PySide6/qml", "PySide6/include", "PySide6/typesystems", "PySide6/glue", "PySide6/*.pyi",
        "PySide6/metatypes", "PySide6/scripts", "shiboken6/*.pyi", "pip", "pip-*.dist-info"]
KEEP_TRANSLATIONS = re.compile(r"^qt(base)?_(es|en)\.qm$")

GUI_MAIN = "import sys\nfrom tensela.ui.launch import main\nsys.exit(main())\n"
CLI_MAIN = "import sys\nfrom tensela.cli import run\nsys.exit(run())\n"

README = """Tensela {version} for Windows (portable, a first version for testing)

Unpack this folder wherever you like (your Documents, a USB stick…) and open Tensela.exe. Nothing is installed:
to remove it, delete the folder. The preferences are kept in %APPDATA%\\Tensela\\Tensela.ini.

On a computer without a graphics card (a virtual machine, a remote desktop), the 3D view is drawn by the processor
(Mesa, in python\\mesa): slower, but it opens. tensela-cli.exe computes a project and exports it from a terminal.

Windows may say that it protected your computer: the folder is not signed yet. «More info» → «Run anyway».

Tensela {version} para Windows (portable, una primera versión para probar): descomprime la carpeta donde quieras y
abre Tensela.exe. No se instala nada: para quitarla, borra la carpeta.
"""


def say(text: str) -> None:
    print(f"==> {text}", flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pinned(key: str) -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))["downloads"][key]


def downloaded(key: str) -> Path:
    """The file of the lock, downloaded (once) and checked by its SHA-256; refused if it does not match."""
    item = pinned(key)
    target = DOWNLOADS / urllib.parse.unquote(item["url"].rsplit("/", 1)[1])
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or sha256(target) != item["sha256"]:
        say(f"downloading {item['url']}")
        urllib.request.urlretrieve(item["url"], target)
    if sha256(target) != item["sha256"]:
        target.unlink()
        raise SystemExit(f"{key}: the download is not the file of the lock")
    say(f"{target.name}: the SHA-256 of the lock")
    return target


def python(folder: Path) -> Path:
    """The portable Python in folder/python (the archive holds it under python/)."""
    with tarfile.open(downloaded("python_windows")) as archive:
        archive.extractall(folder, filter="data")
    home = folder / "python"
    for name in STDLIB_OUT:
        shutil.rmtree(home / "Lib" / name, ignore_errors=True)
    shutil.rmtree(home / "include", ignore_errors=True)
    say("portable Python")
    return home


def libraries(home: Path) -> None:
    """The libraries of the lock, by the hashes of their wheels for Windows; nothing else (no dependencies)."""
    subprocess.run([str(home / "python.exe"), "-m", "pip", "install", "--quiet", "--no-cache-dir", "--require-hashes",
                    "--only-binary=:all:", "--no-deps", "--no-compile", "--no-warn-script-location",
                    "-r", str(REQUIREMENTS)], check=True)
    say(f"{sum(1 for line in REQUIREMENTS.read_text().splitlines() if '==' in line)} libraries, by their hashes")


def tensela(site: Path) -> str:
    source = ROOT / "src" / "tensela"
    shutil.copytree(source, site / "tensela", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manuals = sorted((site / "tensela" / "help").glob("tensela-manual-*.html"))
    say(f"Tensela, with {len(manuals)} manual(s) inside" + ("" if manuals else " (Help opens tensela.com's)"))
    return re.search(r'__version__ = "([^"]+)"', (source / "__init__.py").read_text(encoding="utf-8")).group(1)


def mesa(home: Path) -> None:
    """Mesa's two files of OpenGL, each checked by its own SHA-256, in python/mesa."""
    item = pinned("mesa_windows")
    archive = downloaded("mesa_windows")
    folder = home / "mesa"
    folder.mkdir()
    out = BUILD / "mesa-files"
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run(["7z", "e", "-y", f"-o{out}", str(archive), *item["files"]], check=True,
                   stdout=subprocess.DEVNULL)
    for name, fingerprint in item["files"].items():
        path = out / Path(name).name
        if sha256(path) != fingerprint:
            raise SystemExit(f"Mesa: {name} is not the file of the lock")
        shutil.copy2(path, folder / path.name)
    say("Mesa, for computers without OpenGL 3.2")


def launchers(folder: Path, home: Path) -> None:
    """Tensela.exe and tensela-cli.exe: pip's launchers, Python written relative to them, and the code to run."""
    distlib = home / "Lib" / "site-packages" / "pip" / "_vendor" / "distlib"
    for name, launcher, python_exe, main in (("Tensela.exe", "w64.exe", "pythonw.exe", GUI_MAIN),
                                              ("tensela-cli.exe", "t64.exe", "python.exe", CLI_MAIN)):
        code = io.BytesIO()
        with zipfile.ZipFile(code, "w") as z:
            z.writestr("__main__.py", main)
        shebang = f"#!python\\{python_exe}\r\n".encode()
        (folder / name).write_bytes((distlib / launcher).read_bytes() + shebang + code.getvalue())
    say("Tensela.exe and tensela-cli.exe")


def trim(site: Path) -> None:
    removed = 0
    for pattern in TRIM:
        for path in site.glob(pattern):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            removed += 1
    for path in (site / "PySide6" / "translations").glob("*.qm"):
        if not KEEP_TRANSLATIONS.match(path.name):
            path.unlink()
            removed += 1
    say(f"{removed} parts of Qt and pip left out")


def size(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1e6


def main() -> int:
    shutil.rmtree(BUILD / "folder", ignore_errors=True)
    staging = BUILD / "folder"
    staging.mkdir(parents=True)
    home = python(staging)
    site = home / "Lib" / "site-packages"
    libraries(home)
    version = tensela(site)
    mesa(home)
    launchers(staging, home)
    trim(site)
    shutil.rmtree(home / "Scripts", ignore_errors=True)        # pip's programs, gone with pip
    subprocess.run([str(home / "python.exe"), "-m", "compileall", "-q", "-j", "0", str(home / "Lib")],
                   check=False, stdout=subprocess.DEVNULL)    # (a folder in Program Files cannot write its caches)
    (staging / "README.txt").write_text(README.format(version=version), encoding="utf-8")
    name = f"Tensela-{version}-windows-x64"
    folder = BUILD / name
    shutil.rmtree(folder, ignore_errors=True)
    staging.rename(folder)
    say(f"the folder: {size(folder):.0f} MB")
    target = BUILD / f"{name}.zip"
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(BUILD))
    say(f"{target} ({target.stat().st_size / 1e6:.0f} MB), SHA-256 {sha256(target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
