"""Builds the AppImage of Tensela: one file that runs on most Linux systems of the last years, without installing.

It puts together an AppDir and packs it with appimagetool:

- a portable Python (python-build-standalone, built for old systems: glibc 2.17), so the AppImage does not depend on
  the Python of the computer it was built on;
- the libraries Tensela uses, copied from the development environment (they are manylinux wheels, built to run
  anywhere), leaving out the parts of Qt it does not use (the web engine, 3D, multimedia, the designer tools…);
- Tensela itself, with the manual that comes with it, made again first if the manual changed (see `manuals`);
- its launcher, icons and file type (.tela), so the desktop can integrate it.

Nothing goes in that is not in the lock (tools/appimage.lock.json, see tools/appimage_lock.py): the portable Python
and appimagetool must have the SHA-256 written there, the libraries the versions and files written there, and each
library file is checked against its hash as it is copied. If anything differs, the build stops.

    .venv/bin/python tools/build_appimage.py \
        --python build/appimage/downloads/cpython-3.13.18-install_only.tar.gz \
        --appimagetool path/to/appimagetool-x86_64.AppImage \
        --packages build/appimage/downloads

The result, in build/appimage/:

- `Tensela-<version>-x86_64.AppImage`, the file most people download;
- `Tensela-<version>-x86_64.tar.gz`, the same folder as a portable archive: unpacked anywhere (also /opt), it opens
  with `./tensela`, for whoever cannot or does not want to use an AppImage;
- `SHA256SUMS`, the fingerprints of both, as `sha256sum -c SHA256SUMS` reads them (signed afterwards with
  tools/sign_release.py);
- `release.json`, what the Download page of the site shows (version, files, sizes, fingerprints), also copied into
  the site (src/data/release.json) when it is beside.

Besides the Python libraries, six small libraries of the system go in: those Qt needs to open its windows on X11
(libxcb-cursor, -icccm, -image, -keysyms, -render-util and -util), which many systems do not have installed
(Ubuntu 22.04 lacks libxcb-cursor). They come from the packages of Ubuntu 22.04 (they ask for an old glibc), each
pinned in the lock like the rest, found in the folder `--packages` and unpacked with dpkg-deb.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.metadata as metadata
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import appimage_lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tensela.ui import desktop as desktop_entry  # noqa: E402  (the launcher and the file type, also used by the app)

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "appimage"
APPDIR = BUILD / "Tensela.AppDir"
BRAND = ROOT / "src" / "tensela" / "ui" / "brand"
PYVER = "3.13"

#: Where the libraries start from; the rest are what these need, found in the environment.
ROOTS = ["numpy", "manifold3d", "pillow", "PySide6_Essentials", "shiboken6", "PySide6", "pyvista", "pyvistaqt",
         "ezdxf"]
#: Distributions left out: the parts of Qt that Tensela does not use.
LEFT_OUT = {"pyside6-addons", "pyside6-webengine", "pyside6-pdf"}
#: Files left out inside the libraries (relative to site-packages): the designer and translation tools of Qt, its
#: headers and type stubs, and the translations of Qt that are not English or Spanish.
TRIM = [
    "PySide6/designer", "PySide6/assistant", "PySide6/linguist", "PySide6/lupdate", "PySide6/lrelease",
    "PySide6/qml*", "PySide6/uic", "PySide6/rcc", "PySide6/balsam*", "PySide6/svgtoqml", "PySide6/qsb",
    "PySide6/include/*", "PySide6/typesystems/*", "PySide6/glue/*", "PySide6/*.pyi", "PySide6/Qt/metatypes/*",
    "PySide6/Qt/libexec/*", "PySide6/Qt/qml/*", "PySide6/scripts/*",
    "shiboken6/*.pyi",
]
KEEP_TRANSLATIONS = re.compile(r"^qt(base)?_(es|en)\.qm$")
#: Parts of the standard library that an app does not need.
STDLIB_OUT = ["test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data"]

APPRUN = """#!/bin/sh
# Starts Tensela from the AppImage (or from its portable folder, as ./tensela), with its own Python and libraries:
# the window, or with --cli the command that computes and exports a project without a window.
HERE="$(dirname "$(readlink -f "$0")")"
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP
export PATH="$HERE/usr/bin:$PATH"
if [ -z "$APPIMAGE" ]; then
    export TENSELA_PORTABLE="$HERE/tensela"      # the portable folder: its launcher, for the menu and the AI bridge
fi
if [ "$1" = "--cli" ]; then
    shift
    exec "$HERE/usr/bin/python3" -s -m tensela "$@"
fi
exec "$HERE/usr/bin/python3" -s -m tensela.ui.launch "$@"
"""


def say(text: str) -> None:
    print(f"==> {text}", flush=True)


class Refused(Exception):
    """Something is not what the lock says: the build stops."""


def verified(path: Path, key: str) -> Path:
    """A downloaded file, if its SHA-256 is the one written in the lock."""
    pinned = appimage_lock.read()["downloads"][key]
    found = appimage_lock.sha256_file(path)
    if found != pinned["sha256"]:
        raise Refused(f"{path.name}: SHA-256 {found}, the lock says {pinned['sha256']} ({pinned['url']})")
    say(f"{path.name}: SHA-256 as in the lock")
    return path


#: The libraries of the system that go in (the keys of the lock): what Qt needs to open its windows on X11.
SYSTEM_LIBRARIES = ["xcb_cursor", "xcb_icccm", "xcb_image", "xcb_keysyms", "xcb_render_util", "xcb_util"]


def system_libraries(packages: Path, site: Path) -> None:
    """The libraries of SYSTEM_LIBRARIES, from their packages (pinned in the lock), beside those of Qt (they look for
    them there)."""
    import tempfile
    downloads = appimage_lock.read()["downloads"]
    for key in SYSTEM_LIBRARIES:
        pinned = downloads[key]
        deb = verified(packages / pinned["url"].rsplit("/", 1)[1], key)
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["dpkg-deb", "-x", str(deb), folder], check=True)
            library = Path(folder) / pinned["file"]
            found = appimage_lock.sha256_file(library)
            if found != pinned["file_sha256"]:
                raise Refused(f"{library.name} inside {deb.name}: SHA-256 {found}, the lock says "
                              f"{pinned['file_sha256']}")
            shutil.copy2(library, site / "PySide6" / "Qt" / "lib" / pinned["soname"])
    say(f"{len(SYSTEM_LIBRARIES)} libraries of the system, for the windows on X11")


def requirements(dist) -> list[str]:
    """The names a distribution needs on Linux (not its extras, not what is only for Windows or macOS)."""
    names = []
    for line in dist.requires or []:
        text, _, marker = line.partition(";")
        if "extra" in marker or any(w in marker for w in ("win32", "darwin", "Windows", "Darwin", "cygwin")):
            continue
        if "python_version" in marker and "<" in marker and "3.1" in marker:
            continue                        # backports for older Pythons
        names.append(re.split(r"[<>=!~\[ (]", text.strip())[0])
    return names


def closure() -> list:
    seen, out, todo = set(), [], list(ROOTS)
    while todo:
        name = todo.pop()
        key = name.lower().replace("_", "-")
        if key in seen or key in LEFT_OUT:
            continue
        seen.add(key)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        out.append(dist)
        todo += requirements(dist)
    return out


def copy_distributions(site: Path) -> None:
    """Each distribution's own files (its RECORD), without compiled caches, each one checked against its hash."""
    chosen = closure()
    # The files of the parts left out, except those that the chosen ones also list (PySide6/__init__.py is in both).
    kept = {str(f) for dist in chosen for f in dist.files or []}
    left_out_files = set()
    for name in LEFT_OUT:
        try:
            left_out_files |= {str(f) for f in metadata.distribution(name).files or []} - kept
        except metadata.PackageNotFoundError:
            pass
    count = 0
    for dist in chosen:
        hashes = dict(appimage_lock.entries(dist))
        for f in dist.files or []:
            text = str(f)
            if "__pycache__" in text or text.endswith(".pyc") or text.startswith("..") or text in left_out_files:
                continue
            source = f.locate()
            if not source.is_file():
                continue
            target = site / text
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if text in hashes and appimage_lock.sha256_file(target) != hashes[text]:
                raise Refused(f"{dist.metadata['Name']}: {text} does not match its hash")
            count += 1
    say(f"{count} library files, each one as its hash says")


def trim(site: Path) -> None:
    removed = 0
    for pattern in TRIM:
        for path in site.glob(pattern):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            removed += 1
    translations = site / "PySide6" / "Qt" / "translations"
    for path in translations.glob("*.qm") if translations.is_dir() else []:
        if not KEEP_TRANSLATIONS.match(path.name):
            path.unlink()
            removed += 1
    say(f"{removed} parts of Qt left out")


def slim() -> None:
    """What only a developer of the C code would use, left out:

    - the debugging symbols of every program and library (`strip --strip-unneeded`): the code is the same, but
      Python, VTK and the rest come with them, and they were two thirds of the AppDir;
    - libpython as a shared library: the portable Python carries Python inside its program, and nothing asks for the
      library (checked here: if some file needs it, it stays)."""
    if not (shutil.which("strip") and shutil.which("readelf")):
        raise Refused("strip and readelf are needed (the package binutils)")
    elves = [p for p in APPDIR.rglob("*") if p.is_file() and not p.is_symlink() and p.open("rb").read(4) == b"\x7fELF"]
    needed = set()
    for path in elves:
        if path.name.startswith("libpython3"):        # they ask for each other: what counts is the rest
            continue
        dynamic = subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True).stdout
        needed |= {line.rpartition("[")[2].rstrip("]") for line in dynamic.splitlines() if "(NEEDED)" in line}
    lib = APPDIR / "usr" / "lib"
    for library in sorted(lib.glob("libpython3*.so*")):
        if not any(n.startswith(library.name.split(".so")[0] + ".so") for n in needed):
            library.unlink()
            say(f"{library.name} left out: nothing asks for it")
    before = size(APPDIR)
    for path in elves:
        if path.exists():
            subprocess.run(["strip", "--strip-unneeded", str(path)], check=True)
    say(f"debugging symbols left out: {before:.0f} → {size(APPDIR):.0f} MB")


def python(tarball: Path) -> None:
    """The portable Python into usr/ (the archive holds it under python/)."""
    usr = APPDIR / "usr"
    with tarfile.open(tarball) as archive:
        for member in archive.getmembers():
            if not member.name.startswith("python/"):
                continue
            member.name = member.name[len("python/"):]
            if member.name:
                archive.extract(member, usr, filter="data")
    lib = usr / "lib" / f"python{PYVER}"
    for name in STDLIB_OUT:
        shutil.rmtree(lib / name, ignore_errors=True)
    shutil.rmtree(usr / "include", ignore_errors=True)
    shutil.rmtree(usr / "share", ignore_errors=True)
    say("portable Python")


#: Where the manual is written (the tensela repository) and the site that turns it into the one-file manual.
MANUAL_REPO = Path(os.environ.get("TENSELA_REPO") or ROOT.parent / "tensela")
SITE_REPO = Path(os.environ.get("TENSELA_SITE") or ROOT.parent / "tensela-site")


def _newest(paths) -> float:
    times = [f.stat().st_mtime for p in paths if p.exists()
             for f in ([p] if p.is_file() else p.rglob("*")) if f.is_file()]
    return max(times, default=0.0)


def manuals() -> None:
    """The manual inside Tensela, up to date: if the manual (its pages, pictures, translations) or the way the site
    makes it changed after the copy inside was taken, the site is built again and the copy taken again
    (tools/bundle_manual.py). Each language the manual has comes in."""
    inside = sorted((ROOT / "src" / "tensela" / "help").glob("tensela-manual-*.html"))
    sources = [MANUAL_REPO / "manual", MANUAL_REPO / "examples" / "recipes", SITE_REPO / "scripts",
               SITE_REPO / "astro.config.mjs", SITE_REPO / "src" / "components", SITE_REPO / "src" / "styles"]
    if inside and _newest(sources) <= min(f.stat().st_mtime for f in inside):
        say(f"the manual inside is up to date ({len(inside)} language(s))")
        return
    if not (SITE_REPO / "package.json").is_file() or shutil.which("npm") is None:
        if not inside:
            raise Refused(f"there is no manual inside, and the site to make it is not at {SITE_REPO} (TENSELA_SITE)")
        say("the manual changed, but the site to make it again is not here: the one inside goes as it is")
        return
    say("the manual changed: building the site and taking it again")

    def without_memory_cap() -> None:                 # Node reserves a lot of address space it never uses: a cap on
        import resource                               # it (ulimit -v) makes it fail; the soft one is lifted here
        resource.setrlimit(resource.RLIMIT_AS, (resource.getrlimit(resource.RLIMIT_AS)[1],) * 2)

    subprocess.run(["npm", "run", "build"], cwd=SITE_REPO, check=True, stdout=subprocess.DEVNULL,
                   env={**os.environ, "TENSELA_REPO": str(MANUAL_REPO)}, preexec_fn=without_memory_cap)
    subprocess.run([sys.executable, str(ROOT / "tools" / "bundle_manual.py"), str(SITE_REPO)], check=True)


def tensela(site: Path) -> str:
    source = ROOT / "src" / "tensela"
    shutil.copytree(source, site / "tensela", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manuals = sorted((site / "tensela" / "help").glob("tensela-manual-*.html"))
    say(f"Tensela, with {len(manuals)} manual(s) inside" + ("" if manuals else " (run tools/bundle_manual.py)"))
    text = (source / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def desktop() -> None:
    (APPDIR / "AppRun").write_text(APPRUN, encoding="utf-8")
    (APPDIR / "AppRun").chmod(0o755)
    (APPDIR / "tensela.desktop").write_text(desktop_entry.entry(), encoding="utf-8")
    share = APPDIR / "usr" / "share"
    (share / "applications").mkdir(parents=True, exist_ok=True)
    shutil.copy2(APPDIR / "tensela.desktop", share / "applications" / "tensela.desktop")
    (share / "mime" / "packages").mkdir(parents=True, exist_ok=True)
    (share / "mime" / "packages" / "tensela.xml").write_text(desktop_entry.MIME, encoding="utf-8")
    for side in (16, 24, 32, 48, 64, 128, 256, 512):
        folder = share / "icons" / "hicolor" / f"{side}x{side}" / "apps"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BRAND / f"tensela-{side}.png", folder / "tensela.png")
    for side in (16, 32, 48, 64, 128, 256):
        folder = share / "icons" / "hicolor" / f"{side}x{side}" / "mimetypes"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BRAND / f"application-x-tensela-{side}.png", folder / "application-x-tensela.png")
    scalable = share / "icons" / "hicolor" / "scalable"
    (scalable / "apps").mkdir(parents=True, exist_ok=True)
    (scalable / "mimetypes").mkdir(parents=True, exist_ok=True)
    shutil.copy2(BRAND / "tensela.svg", scalable / "apps" / "tensela.svg")
    shutil.copy2(BRAND / "application-x-tensela.svg", scalable / "mimetypes" / "application-x-tensela.svg")
    shutil.copy2(BRAND / "tensela-256.png", APPDIR / "tensela.png")
    os.symlink("tensela.png", APPDIR / ".DirIcon")
    say("launcher, icons and file type")


def size(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink()) / 1e6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", required=True, type=Path, help="the python-build-standalone archive")
    parser.add_argument("--appimagetool", required=True, type=Path, help="appimagetool (an AppImage itself)")
    parser.add_argument("--packages", required=True, type=Path,
                        help="the folder with the packages of Ubuntu 22.04 of the lock (libxcb-cursor0…)")
    args = parser.parse_args()
    try:
        return build(args)
    except Refused as error:
        print(f"Stopped: {error}", file=sys.stderr)
        return 2


def build(args) -> int:
    verified(args.python, "python")
    verified(args.appimagetool, "appimagetool")
    changed = appimage_lock.check()
    if changed:
        raise Refused("the libraries are not the ones of the lock:\n  " + "\n  ".join(changed)
                      + "\nIf the change was meant, read what changed and run tools/appimage_lock.py --update.")
    say("the libraries are the ones of the lock")
    if APPDIR.exists():
        shutil.rmtree(APPDIR)
    APPDIR.mkdir(parents=True)
    python(args.python)
    site = APPDIR / "usr" / "lib" / f"python{PYVER}" / "site-packages"
    copy_distributions(site)
    trim(site)
    system_libraries(args.packages, site)
    slim()
    manuals()
    version = tensela(site)
    say("compiling the Python files (the AppImage cannot write its caches)")
    subprocess.run([str(APPDIR / "usr" / "bin" / "python3"), "-m", "compileall", "-q", "-j", "0",
                    str(APPDIR / "usr" / "lib" / f"python{PYVER}")], check=False)
    desktop()
    say(f"AppDir: {size(APPDIR):.0f} MB")
    output = BUILD / f"Tensela-{version}-x86_64.AppImage"
    output.unlink(missing_ok=True)                    # if packing fails, no old AppImage is left looking like the new one
    tool = args.appimagetool.resolve()
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "ARCH": "x86_64"}
    done = subprocess.run([str(tool), "--appimage-extract-and-run", "--no-appstream", str(APPDIR), str(output)],
                          env=env, capture_output=True, text=True)
    if done.returncode:
        print(done.stdout[-3000:], done.stderr[-3000:])
        return done.returncode
    say(f"{output} ({output.stat().st_size / 1e6:.0f} MB)")
    portable = archive(version)
    fingerprints(version, [output, portable])
    return 0


PORTABLE_README = """Tensela {version}, portable

Unpack this folder wherever you like (your home, /opt…) and open Tensela with:

    ./tensela

The first time, Preferences → General → Applications menu puts it in the menu of your desktop, with its icon, and
makes .tela files open with a double click. It needs a 64-bit Linux with glibc 2.34 or newer (Ubuntu 22.04,
Debian 12, Fedora 35, RHEL 9 or newer) and OpenGL. The manual: Help → Manual, or https://tensela.com/manual/.

Tensela {version}, portable: descomprime esta carpeta donde quieras y abre Tensela con ./tensela. Preferencias →
General → Menú de aplicaciones la agrega al menú del escritorio.
"""


def archive(version: str) -> Path:
    """The AppDir as a portable folder in a .tar.gz: `./tensela` opens it (the same launcher as the AppImage)."""
    name = f"Tensela-{version}-x86_64"
    os.symlink("AppRun", APPDIR / "tensela")
    (APPDIR / "README.txt").write_text(PORTABLE_README.format(version=version), encoding="utf-8")
    target = BUILD / f"{name}.tar.gz"
    target.unlink(missing_ok=True)
    say(f"the portable folder: {target.name}")
    import datetime
    today = datetime.datetime.combine(datetime.date.today(), datetime.time())     # midnight, here
    # The same order, owner and date for every file (the date of the day it is built, not 1970): the same folder
    # gives the same archive that day.
    subprocess.run(["tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner",
                    f"--mtime=@{int(today.timestamp())}",
                    "--transform", f"s,^\\.,{name},", "-C", str(APPDIR), "-I", "gzip -6", "-cf", str(target), "."],
                   check=True)
    (APPDIR / "tensela").unlink()
    (APPDIR / "README.txt").unlink()
    say(f"{target} ({target.stat().st_size / 1e6:.0f} MB)")
    return target


def fingerprints(version: str, files: list[Path]) -> None:
    """SHA256SUMS beside the files, and release.json for the Download page of the site."""
    import datetime
    import hashlib
    import json
    sums = {}
    for f in files:
        h = hashlib.sha256()
        with open(f, "rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                h.update(block)
        sums[f.name] = h.hexdigest()
    (BUILD / "SHA256SUMS").write_text("".join(f"{v}  {k}\n" for k, v in sums.items()), encoding="utf-8")
    base = f"https://github.com/tensela/tensela/releases/download/v{version}/"
    release = {"version": version, "date": datetime.date.today().isoformat(), "sums": base + "SHA256SUMS",
               "signature": base + "SHA256SUMS.minisig",              # made afterwards, by tools/sign_release.py
               "files": [{"kind": "appimage" if f.suffix == ".AppImage" else "portable", "name": f.name,
                          "url": base + f.name, "size": f.stat().st_size, "sha256": sums[f.name]} for f in files]}
    text = json.dumps(release, indent=2) + "\n"
    (BUILD / "release.json").write_text(text, encoding="utf-8")
    if (SITE_REPO / "src").is_dir():
        (SITE_REPO / "src" / "data").mkdir(exist_ok=True)
        (SITE_REPO / "src" / "data" / "release.json").write_text(text, encoding="utf-8")
    say("SHA256SUMS and release.json (also in the site)" if (SITE_REPO / "src").is_dir() else "SHA256SUMS and release.json")


if __name__ == "__main__":
    sys.exit(main())
