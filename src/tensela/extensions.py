"""Extensions: what is added to Tensela without changing it. An extension can bring nodes, ways of exporting and
actions in the Extensions menu.

An extension is a folder (shared as a .zip) with its card, `extension.toml`, and its Python package:

    animation/
        extension.toml          id, name, version, author, what it does, the permissions it asks for
        animation/__init__.py   def register(tensela): …   (and, if it needs it, def unregister(): …)

    id = "animation"
    name = "Animation"
    version = "1.0.0"
    author = "Tensela"
    description = "Exports what a slider does when it plays, as a GIF or a series of PNG images."
    tensela = "0.9"                    # the oldest Tensela it works with
    licence = "GPL-3.0-or-later"
    website = "https://…"              # where it is told about (optional)
    issues = "https://…"               # where to report a problem with it (optional)
    source = "https://…"               # its code (optional)
    contact = "someone@…"              # how to reach whoever makes it (optional)
    [permissions]                      # what it may do besides computing, and why (none: only computes)
    network = "to download the weather of the place"
    [es]                               # its card in other languages
    name = "Animación"
    [translations.es]                  # its texts (node names, inputs, menus) in other languages
    "Spiral" = "Espiral"

Those of the person go in ~/.local/share/tensela/extensions/<id>/; those that come with Tensela, in
`tensela/bundled_extensions/` (off until they are turned on). An extension is a program: Tensela shows what it asks for
before installing it, but cannot shut it in, as with the add-ons of any program.

`register(tensela)` receives an `Api`, the door through which an extension reaches Tensela:

    tensela.node(…)      a kind of node (it also computes in the process that computes)
    tensela.export(…)    a way of exporting (File → Export)
    tensela.action(…)    an entry in the Extensions menu
    tensela.panel(…)     a panel of its own, beside Values (it can go to a separate window)
    tensela.menu(…)      an entry in the right-click menu of a node, of the canvas or of the 3D view
    tensela.icon(…)      an icon of its own (an SVG of its folder), for its nodes and menu entries
    tensela.on(…)        to hear when something happens: the window ready, computed, a node chosen, another project,
                         the sliders
    tensela.command(…)   a command of its own, without the window: `tensela-app --extension <id> …` (the AppImage:
                         `Tensela.AppImage --extension <id> …`); only while the extension is on

Turned off, what it added goes away. What its functions receive is the window; what they may use of it:

    window.project               the open project (its graph, what is seen, its sliders); None if there is none
    window.edit_project(f, what) to change it: f(copy) changes a copy, which takes its place as one step of Ctrl+Z
    window.last_errors           what failed in the last computation (node → message)
    window.also_calculate        nodes to calculate too, though they are not seen (empty it after)
    window.show_extension_panel  to open one of its panels
    window.statusBar()           to say something at the bottom
    window.viewer.save_image(…)  the 3D view as a PNG

Whoever writes one loads it from its folder (Manage extensions → Load a folder, for development; «Reload» after each
change) and packs it with `tensela-app --pack-extension <folder>` (the .zip and its SHA-256). The manual tells how,
step by step (Extensions → Write an extension).
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .data import ShapeError
from .language import tr

MANIFEST = "extension.toml"
#: Those that come with Tensela (off at first).
BUNDLED = Path(__file__).resolve().parent / "bundled_extensions"
PERMISSIONS = {"network": "connect to the internet", "files": "read or write files outside the project",
               "programs": "start other programs", "local": "talk with other programs on this computer"}
_ID = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
#: The most an extension may weigh unpacked (a .zip that would fill the disk is refused).
MAX_SIZE = 500 * 1024 ** 2


def folder() -> Path:
    """Where the extensions of the person go."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "tensela" / "extensions"


@dataclass
class Extension:
    """The card of an extension, as its extension.toml says it."""

    id: str
    name: str
    version: str = ""
    author: str = ""
    description: str = ""
    minimum: str = ""
    licence: str = ""
    permissions: dict = field(default_factory=dict)   # what it may do besides computing → why ("" if not said)
    website: str = ""
    issues: str = ""
    source: str = ""
    contact: str = ""
    path: Path | None = None
    bundled: bool = False
    texts: dict = field(default_factory=dict)          # {"es": {"name": …, "description": …}}
    translations: dict = field(default_factory=dict)   # {"es": {"Spiral": "Espiral"}}
    problem: str = ""                                  # why it cannot be used (its card is wrong, it is too new…)
    development: bool = False                          # loaded from a folder of whoever writes it (not installed)

    def said(self, key: str) -> str:
        """Its name or what it does, in the language of the window if the card has it."""
        from . import language
        return self.texts.get(language.LANGUAGE, {}).get(key) or getattr(self, key)

    @property
    def module(self) -> str:
        return self.id.replace("-", "_")

    def why(self, permission: str) -> str:
        """Why it asks for a permission, in the language of the window if its card says it."""
        from . import language
        said = self.texts.get(language.LANGUAGE, {}).get("permissions", {})
        return (said.get(permission) if isinstance(said, dict) else "") or self.permissions.get(permission, "")

    def installed(self) -> str:
        """When it was installed (the date of its folder), for those of the person."""
        if self.bundled or self.path is None:
            return ""
        import datetime
        try:
            return datetime.date.fromtimestamp(self.path.stat().st_mtime).isoformat()
        except OSError:
            return ""


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3]) or (0,)


def compare(new: str, old: str) -> int:
    """1 if version `new` is newer than `old`, -1 if older, 0 if the same."""
    a, b = _version(new), _version(old)
    a, b = a + (0,) * (3 - len(a)), b + (0,) * (3 - len(b))
    return (a > b) - (a < b)


def card(data: dict, path: Path | None = None, bundled: bool = False) -> Extension:
    """An extension from the content of its extension.toml (with `problem` set if something is wrong)."""
    from . import __version__
    ext_id = str(data.get("id", "")).strip()
    asked = data.get("permissions", {})
    if isinstance(asked, list):                        # (written as a list: without saying why)
        asked = {str(p): "" for p in asked}
    elif not isinstance(asked, dict):
        asked = {}

    def link(key: str) -> str:
        text = str(data.get(key, "")).strip()
        return text if re.match(r"^(https?://|mailto:)\S+$", text) or (key == "contact" and "@" in text) else ""

    ext = Extension(id=ext_id, name=str(data.get("name") or ext_id), version=str(data.get("version", "")),
                    author=str(data.get("author", "")), description=str(data.get("description", "")),
                    minimum=str(data.get("tensela", "")), licence=str(data.get("licence", data.get("license", ""))),
                    permissions={str(k): str(v) for k, v in asked.items()}, website=link("website"),
                    issues=link("issues"), source=link("source"), contact=link("contact"), path=path,
                    bundled=bundled,
                    texts={k: v for k, v in data.items() if isinstance(v, dict)
                           and k not in ("translations", "permissions")},
                    translations=data.get("translations") if isinstance(data.get("translations"), dict) else {})
    if not _ID.match(ext_id):
        ext.problem = tr('its card has no valid id (lower-case letters, digits and hyphens).')
    elif unknown := [p for p in ext.permissions if p not in PERMISSIONS]:
        ext.problem = tr('it asks for permissions Tensela does not know: {names}.').format(names=", ".join(unknown))
    elif ext.minimum and _version(ext.minimum) > _version(__version__):
        ext.problem = tr('it needs Tensela {version} or newer.').format(version=ext.minimum)
    elif path is not None and not (path / ext.module / "__init__.py").is_file():
        ext.problem = tr('its package «{name}» is missing.').format(name=ext.module)
    return ext


def read(path: Path, bundled: bool = False) -> Extension:
    """The extension in a folder."""
    try:
        data = tomllib.loads((path / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        return Extension(id=path.name, name=path.name, path=path, bundled=bundled,
                         problem=tr('its card ({file}) cannot be read: {error}').format(file=MANIFEST, error=error))
    return card(data, path, bundled)


def available() -> list[Extension]:
    """Those that come with Tensela, those of the person and those being written (development folders): one with
    the same id takes the place of the one before, in that order."""
    found: dict[str, Extension] = {}
    for base, bundled in ((BUNDLED, True), (folder(), False)):
        if base.is_dir():
            for path in sorted(base.iterdir()):
                if (path / MANIFEST).is_file():
                    ext = read(path, bundled)
                    found[ext.id] = ext
    for path in development_folders():
        if (path / MANIFEST).is_file():
            ext = read(path)
            ext.development = True
            found[ext.id] = ext
    return sorted(found.values(), key=lambda e: e.said("name").lower())


# --- Writing one: development folders and packing -------------------------------------------------------------------

#: Where the development folders are remembered (the preferences of the window).
DEVELOPMENT = "extensions/development"


def _settings():
    from PySide6.QtCore import QSettings
    return QSettings("Tensela", "Tensela")


def development_folders() -> list[Path]:
    """The folders of extensions being written, loaded from where they are (without installing them)."""
    value = _settings().value(DEVELOPMENT, []) or []
    return [Path(p) for p in ([value] if isinstance(value, str) else value)]


def develop(path: Path, yes: bool = True) -> Extension | None:
    """Adds (or takes away) a development folder. The extension in it, or None if it was taken away."""
    path = Path(path).resolve()
    if yes and not (path / MANIFEST).is_file() and (path.parent / MANIFEST).is_file():
        path = path.parent                              # its package was chosen: the folder is the one above
    if yes and not (path / MANIFEST).is_file():
        raise ShapeError(tr('“{folder}” has no {card}: it is not the folder of an extension. Choose the folder '
                            'that has it (the one with the package inside).').format(folder=path, card=MANIFEST))
    ext_id = read(path).id if (path / MANIFEST).is_file() else None
    # One folder per extension: another of the same one (a copy loaded before) goes, also when it stops.
    others = [p for p in development_folders()
              if p != path and not ((p / MANIFEST).is_file() and read(p).id == ext_id)]
    if yes:
        ext = read(path)
        _settings().setValue(DEVELOPMENT, [str(p) for p in others + [path]])
        ext.development = True
        return ext
    _settings().setValue(DEVELOPMENT, [str(p) for p in others])
    return None


#: What is not packed: the caches, the hidden files and folders (.git…) and the packed ones.
_NOT_PACKED = ("__pycache__",)


def pack(path: Path, out: Path | None = None) -> tuple[Path, str]:
    """The extension of a folder as the .zip to share (`<id>-<version>.zip`, beside the folder or in `out`), after
    checking its card and its register(tensela). The .zip and its SHA-256 (the fingerprint the catalogue asks for)."""
    import hashlib
    path = Path(path).resolve()
    ext = read(path)
    if ext.problem:
        raise ShapeError(tr('It cannot be packed: {problem}').format(problem=ext.problem))
    init = path / ext.module / "__init__.py"
    if not re.search(r"^def register\(", init.read_text(encoding="utf-8"), re.M):
        raise ShapeError(tr('It cannot be packed: {file} has no register(tensela).').format(file=init))
    target = Path(out or path.parent) / f"{ext.id}-{ext.version or '0'}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    files = [f for f in sorted(path.rglob("*")) if f.is_file()
             and not any(part.startswith(".") or part in _NOT_PACKED for part in f.relative_to(path).parts)
             and f.suffix != ".pyc" and f.resolve() != target.resolve()]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            info = zipfile.ZipInfo(f"{ext.id}/{f.relative_to(path).as_posix()}", date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED          # the same files give the same .zip (and fingerprint)
            z.writestr(info, f.read_bytes())
    size = sum(f.stat().st_size for f in files)
    if size > MAX_SIZE:
        target.unlink()
        raise ShapeError(tr('“{file}” is too big for an extension.').format(file=target.name))
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


# --- Installing from a file -----------------------------------------------------------------------------------------

def look_inside(archive: Path) -> tuple[Extension, str]:
    """The card of the extension in a .zip, without unpacking it, and the folder inside where it is."""
    try:
        with zipfile.ZipFile(archive) as z:
            cards = [n for n in z.namelist() if n.endswith("/" + MANIFEST) or n == MANIFEST]
            cards = [n for n in cards if n.count("/") <= 1]
            if len(cards) != 1:
                raise ShapeError(tr('“{file}” is not an extension of Tensela: it has no {card} (or more than one).')
                                 .format(file=archive.name, card=MANIFEST))
            data = tomllib.loads(z.read(cards[0]).decode("utf-8"))
    except (zipfile.BadZipFile, OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ShapeError(tr('“{file}” cannot be read as an extension: {error}').format(file=archive.name,
                                                                                         error=error)) from None
    return card(data), cards[0].rpartition("/")[0]


def install(archive: Path) -> Extension:
    """Unpacks the extension of a .zip in the folder of the person (in place of one with the same id)."""
    ext, top = look_inside(archive)
    if ext.problem and "package" not in ext.problem:
        raise ShapeError(tr('It cannot be installed: {problem}').format(problem=ext.problem))
    target = folder() / ext.id
    staging = folder() / f".{ext.id}.new"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    total = 0
    try:
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                name = info.filename
                if top and not name.startswith(top + "/"):
                    continue
                inner = name[len(top) + 1:] if top else name
                parts = Path(inner).parts
                if not inner or inner.endswith("/") or Path(inner).is_absolute() or ".." in parts:
                    continue
                total += info.file_size
                if total > MAX_SIZE:
                    raise ShapeError(tr('“{file}” is too big for an extension.').format(file=archive.name))
                destination = staging / inner
                destination.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as source, open(destination, "wb") as out:
                    shutil.copyfileobj(source, out)
        installed = read(staging)
        if installed.problem:
            raise ShapeError(tr('It cannot be installed: {problem}').format(problem=installed.problem))
        if target.exists():
            unload(ext.id)
            shutil.rmtree(target)
        staging.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return read(target)


def uninstall(ext: Extension) -> None:
    """Takes away one the person installed (those that come with Tensela are only turned off)."""
    if ext.bundled or ext.path is None:
        raise ShapeError(tr('«{name}» comes with Tensela: it can be turned off, not taken away.').format(
            name=ext.said("name")))
    unload(ext.id)
    shutil.rmtree(ext.path)


# --- Loading --------------------------------------------------------------------------------------------------------

@dataclass
class Entry:
    """A way of exporting, an action, a panel or an entry of a right-click menu an extension added."""

    extension: str
    label: str
    function: object
    help: str = ""
    suffix: str = ""
    icon: str = ""          # the name of a Tensela icon or of one of the extension (Api.icon)
    where: str = ""         # menus: "node", "canvas" or "view"


#: Where an entry of a right-click menu may go.
MENUS = ("node", "canvas", "view")
#: What an extension may hear (Api.on), and what its function receives.
EVENTS = {"window": "function(window)", "computed": "function(window)",
          "selected": "function(window, node name or None)", "project": "function(window)",
          "sliders": "function(window)"}
#: The icons of the extensions on: their name ("<id>.<name>") → the inside of a 24 × 24 SVG (ui/icons.py draws them).
ICONS: dict[str, str] = {}
#: The icon of each kind of node of an extension that brings one: kind → icon name.
KIND_ICONS: dict[str, str] = {}
_SVG = re.compile(r"<svg\b[^>]*>(.*)</svg>", re.S | re.I)


class Api:
    """What `register(tensela)` of an extension receives."""

    def __init__(self, ext: Extension):
        self.extension = ext
        self.kinds: list[str] = []
        self.exports: list[Entry] = []
        self.actions: list[Entry] = []
        self.panels: list[Entry] = []
        self.menus: list[Entry] = []
        self.icons: list[str] = []
        self.listeners: list[tuple[str, object]] = []
        self.commands: list[Entry] = []
        self._texts: list[tuple[str, str]] = []

    def node(self, name: str, category: str, inputs, output: str, function, help: str = "",
             icon: str = "") -> None:
        """A kind of node: `inputs` are `Input` (tensela.nodes), `function(**inputs, name)` gives its Data. Its icon
        on the card is that of its category (if it is one of Tensela), or `icon`."""
        from .nodes import CATALOG, NodeType, _register
        if name in CATALOG and CATALOG[name].extension != self.extension.id:
            raise ShapeError(tr('The extension «{ext}» brings a node «{name}», and Tensela already has one.')
                             .format(ext=self.extension.name, name=name))
        _register(NodeType(name, category, tuple(inputs), output, function, help, extension=self.extension.id))
        self.kinds.append(name)
        if icon:
            KIND_ICONS[name] = self._icon_name(icon)

    def export(self, label: str, suffix: str, function, help: str = "") -> None:
        """A way of exporting (File → Export): `function(path, objects)`, `objects` as `Project.visible_objects`
        gives them (name, Data, style). It runs aside (the window goes on drawing): it must not touch the window."""
        self.exports.append(Entry(self.extension.id, label, function, help, suffix))

    def action(self, label: str, function, help: str = "", icon: str = "") -> None:
        """An entry in the Extensions menu: `function(window)`."""
        self.actions.append(Entry(self.extension.id, label, function, help, icon=self._icon_name(icon)))

    def panel(self, title: str, build, help: str = "") -> None:
        """A panel of its own: `build(window)` gives its content (a QWidget). It starts closed, beside Values; it
        is opened from the Extensions menu (or with `window.show_extension_panel(title)`) and can be moved or taken
        to a separate window like the others. It is built once, when it is first opened."""
        self.panels.append(Entry(self.extension.id, title, build, help))

    def menu(self, where: str, label: str, function, help: str = "", icon: str = "") -> None:
        """An entry in a right-click menu: on a node (`where="node"`, `function(window, node name)`), on the
        background of the canvas (`"canvas"`, `function(window)`) or on the 3D view (`"view"`, `function(window)`)."""
        if where not in MENUS:
            raise ShapeError(tr('A menu entry goes in one of: {places}.').format(places=", ".join(MENUS)))
        self.menus.append(Entry(self.extension.id, label, function, help, icon=self._icon_name(icon), where=where))

    def icon(self, name: str, file: str) -> str:
        """An icon of its own, from an SVG of its folder (24 × 24, drawn with lines: Tensela tints it with the colour
        of the theme). Its name is then used in `icon=` of a node, an action or a menu entry (not of a panel: in the
        list of panels the icon would hide whether it is open)."""
        path = (self.extension.path / file).resolve()
        if self.extension.path.resolve() not in path.parents:
            raise ShapeError(tr('The icon “{file}” is outside the extension.').format(file=file))
        text = path.read_text(encoding="utf-8")
        found = _SVG.search(text)
        key = f"{self.extension.id}.{name}"
        ICONS[key] = found.group(1).strip() if found else text.strip()
        self.icons.append(key)
        return key

    def on(self, event: str, function) -> None:
        """To hear when something happens in the window: "window" (the window is ready with the extension on: at
        the start, or when it is turned on), "computed" (a computation ended; `window.last_errors` says what failed),
        "selected" (a node was chosen, or none), "project" (another project, or another tab) and "sliders" (the
        sliders of Values changed). See EVENTS for what `function` receives. It must be quick: it runs in the
        window. (In the process that computes there is no window: nothing is heard there.)"""
        if event not in EVENTS:
            raise ShapeError(tr('Unknown event “{event}”: {events}.').format(event=event, events=", ".join(EVENTS)))
        self.listeners.append((event, function))

    def command(self, function, help: str = "") -> None:
        """A command of its own, run without the window: `function(arguments)` (a list of texts) gives the exit
        code. Started with `--extension <id>` (see the top of this module)."""
        self.commands.append(Entry(self.extension.id, self.extension.id, function, help))

    def _icon_name(self, icon: str) -> str:
        """An icon of the extension by its short name, or one of Tensela by its own."""
        if not icon:
            return ""
        key = f"{self.extension.id}.{icon}"
        return key if key in ICONS else icon

    def tr(self, text: str) -> str:
        return tr(text)


#: The extensions loaded in this process: id → (module, Api).
LOADED: dict[str, tuple[object, Api]] = {}


def load(ext: Extension) -> Api:
    """Imports an extension and calls its register(tensela)."""
    if ext.id in LOADED:
        return LOADED[ext.id][1]
    if ext.problem:
        raise ShapeError(ext.problem)
    from .translations import es
    api = Api(ext)
    for key, value in (ext.translations.get("es") or {}).items():
        if isinstance(value, str) and key not in es.TEXTS:
            es.TEXTS[key] = value
            api._texts.append((key, value))
    name = f"tensela_extension_{ext.module}"
    spec = importlib.util.spec_from_file_location(name, ext.path / ext.module / "__init__.py",
                                                  submodule_search_locations=[str(ext.path / ext.module)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if not callable(register):
            raise ShapeError(tr('it has no register(tensela).'))
        register(api)
    except Exception as error:                          # noqa: BLE001 (said where it is turned on, not lost)
        _undo(api, name)
        raise ShapeError(tr('The extension «{name}» failed when it was turned on: {error}').format(
            name=ext.said("name"), error=f"{type(error).__name__}: {error}")) from error
    LOADED[ext.id] = (module, api)
    return api


def _undo(api: Api, module_name: str) -> None:
    from .nodes import CATALOG
    from .translations import es
    for kind in api.kinds:
        CATALOG.pop(kind, None)
        KIND_ICONS.pop(kind, None)
    for key in api.icons:
        ICONS.pop(key, None)
    for key, value in api._texts:
        if es.TEXTS.get(key) == value:
            del es.TEXTS[key]
    for name in [n for n in sys.modules if n == module_name or n.startswith(module_name + ".")]:
        del sys.modules[name]


def unload(ext_id: str) -> None:
    """What an extension added goes away (its unregister(), if it has one, is called first)."""
    module, api = LOADED.pop(ext_id, (None, None))
    if api is None:
        return
    unregister = getattr(module, "unregister", None)
    if callable(unregister):
        try:
            unregister()
        except Exception:                               # noqa: BLE001 (it is going away anyway)
            pass
    _undo(api, module.__name__)


def load_these(ids, said=None) -> list[str]:
    """Loads the extensions of `ids` that are available; `said(text)` hears what failed. Those loaded."""
    by_id = {e.id: e for e in available()}
    done = []
    for ext_id in ids:
        ext = by_id.get(ext_id)
        if ext is None:
            continue
        try:
            load(ext)
            done.append(ext_id)
        except ShapeError as error:
            if said is not None:
                said(str(error))
    return done


def exports() -> list[Entry]:
    return [e for _, api in LOADED.values() for e in api.exports]


def actions() -> list[Entry]:
    return [e for _, api in LOADED.values() for e in api.actions]


def panels() -> list[Entry]:
    return [e for _, api in LOADED.values() for e in api.panels]


def menus(where: str) -> list[Entry]:
    return [e for _, api in LOADED.values() for e in api.menus if e.where == where]


def turned_on() -> list[str]:
    """The ids of the extensions the window has on (its preferences), read without starting the window."""
    from PySide6.QtCore import QSettings
    value = QSettings("Tensela", "Tensela").value("extensions/on", []) or []
    return [value] if isinstance(value, str) else list(value)


def run_command(ext_id: str, arguments: list[str]) -> int:
    """`--extension <id> …`: the command of an extension that is installed and on. Its exit code."""
    ext = next((e for e in available() if e.id == ext_id), None)
    if ext is None:
        print(tr('There is no extension «{id}» installed.').format(id=ext_id), file=sys.stderr)
        return 2
    if ext_id not in turned_on():
        print(tr('The extension «{name}» is off: turn it on in Tensela (Extensions → Manage extensions…).').format(
            name=ext.said("name")), file=sys.stderr)
        return 2
    try:
        api = load(ext)
    except ShapeError as error:
        print(str(error), file=sys.stderr)
        return 2
    if not api.commands:
        print(tr('The extension «{name}» has no command.').format(name=ext.said("name")), file=sys.stderr)
        return 2
    return int(api.commands[0].function(list(arguments)) or 0)


def listeners(event: str) -> list[tuple[str, object]]:
    """(extension id, function) of those that hear `event`."""
    return [(ext_id, f) for ext_id, (_, api) in LOADED.items() for e, f in api.listeners if e == event]


#: The environment variable that tells the process that computes which extensions to load.
ENVIRONMENT = "TENSELA_EXTENSIONS"


def for_the_calculator() -> str:
    return ",".join(LOADED)


def load_in_calculator() -> None:
    """(In the process that computes.) The extensions the window has on: their nodes compute here too."""
    load_these([i for i in os.environ.get(ENVIRONMENT, "").split(",") if i])
