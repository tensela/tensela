"""The library of groups (Delivery 6): your groups, to use them in any project.

Each group is a JSON file in a folder (by default ``~/.local/share/tensela/groups``; ``TENSELA_LIBRARY``
changes it) with its definition and those of the groups it uses inside. They can be copied, shared or deleted from
the file manager.

    save(graph, "sun fin")                # from the project to the library
    kinds()                               # {name: NodeType} of what there is
    bring(graph, "sun fin")               # from the library to the project (then it is added as a node)
    rename("sun fin", "louver")           # its name in the library (and its file)
    file_of("sun fin")                    # where it is (to delete it, or see it in the file manager)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .data import ShapeError
from .graph import Graph
from .language import tr


def folder() -> Path:
    own = os.environ.get("TENSELA_LIBRARY") or os.environ.get("TENSELA_BIBLIOTECA")
    if own:
        return Path(own)
    data_items = Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")) / "tensela"
    # The library of before the move to English («grupos»), while there is no new one.
    if not (data_items / "groups").exists() and (data_items / "grupos").is_dir():
        return data_items / "grupos"
    return data_items / "groups"


def _file(name: str, where: Path | None = None) -> Path:
    clean = re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "group"
    return (where or folder()) / f"{clean}.json"


def save(graph: Graph, kind: str, help: str | None = None, replace: bool = False,
            where: Path | None = None) -> Path:
    """Saves the group `kind` of the project (and those it uses inside) in the library."""
    from .project_file import KEY, VERSION, _groups_used
    if kind not in graph.definitions:
        raise ShapeError(tr('“{name}” is not a group.').format(name=kind))
    filepath = _file(kind, where)
    if filepath.exists() and not replace:
        raise FileExistsError(filepath)
    if help is not None:
        graph.definitions[kind].help = help.strip()
    content = {KEY: VERSION, "group": kind, "groups": _groups_used(graph, [kind])}
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    return filepath


def _read(filepath: Path) -> dict | None:
    try:
        content = json.loads(filepath.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if isinstance(content, dict) and "grupo" in content:          # saved before the move to English
        from .project_file import KEY, format_version
        content = {KEY: format_version(content), "group": content["grupo"],
                   "groups": content.get("grupos", {})}
    if not isinstance(content, dict) or content.get("group") not in content.get("groups", {}):
        return None
    return content


def names(where: Path | None = None) -> list[str]:
    """The groups of the library, in alphabetical order (the files that cannot be read are skipped)."""
    root = where or folder()
    if not root.is_dir():
        return []
    read = [_read(r) for r in sorted(root.glob("*.json"))]
    return sorted((c["group"] for c in read if c), key=str.casefold)


def kinds(where: Path | None = None) -> dict:
    """{name: NodeType} of each group of the library (for the finder)."""
    return {name: g.kinds[name] for name, g in graphs(where).items()}


def graphs(where: Path | None = None) -> dict:
    """{name: Graph} of each group of the library: a graph with the group and those it uses (its kind, its
    definition, the kinds of its nodes)."""
    from .project_file import _read_groups
    result = {}
    root = where or folder()
    if not root.is_dir():
        return result
    for filepath in sorted(root.glob("*.json")):
        content = _read(filepath)
        if content is None:
            continue
        g = Graph()
        try:
            _read_groups(g, content["groups"])
        except ShapeError:
            continue
        result[content["group"]] = g
    return result


def bring(graph: Graph, name: str, where: Path | None = None) -> str:
    """Puts in the project the definition of the group `name` from the library (and those it uses).

    If the project already has a group with that name, the project's one is used.
    """
    from .project_file import _read_groups
    if name in graph.definitions:
        return name
    root = where or folder()
    for filepath in sorted(root.glob("*.json")) if root.is_dir() else []:
        content = _read(filepath)
        if content and content["group"] == name:
            _read_groups(graph, content["groups"])
            return name
    raise ShapeError(tr('“{name}” is not in the library.').format(name=name))


def file_of(name: str, where: Path | None = None) -> Path:
    """The file of the group `name` in the library (whatever the file is called)."""
    root = where or folder()
    for filepath in sorted(root.glob("*.json")) if root.is_dir() else []:
        content = _read(filepath)
        if content and content["group"] == name:
            return filepath
    raise ShapeError(tr('“{name}” is not in the library.').format(name=name))


def rename(old: str, new: str, where: Path | None = None) -> Path:
    """The group `old` of the library is called `new` from now on (its file too). The projects that already use it
    keep their own copy, with the old name."""
    new = new.strip()
    if not new:
        raise ShapeError(tr('The name cannot be empty.'))
    filepath = file_of(old, where)
    if new == old:
        return filepath
    if new in names(where):
        raise ShapeError(tr('There is already a “{name}” in the library.').format(name=new))
    content = _read(filepath)
    groups = content["groups"]
    groups[new] = groups.pop(old)
    for definition in groups.values():                  # another group of the file that uses it inside
        for spec in definition.get("nodes", {}).values():
            if spec.get("type") == old:
                spec["type"] = new
    content["group"] = new
    target = _file(new, where)
    target.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    if target != filepath:
        filepath.unlink()
    return target

