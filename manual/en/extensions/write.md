---
title: Write an extension
description: From the template to the .zip, step by step, and everything an extension can use of Tensela.
---

## What for

For what Tensela does not bring and you need again and again: the module of a façade system of your office, a node
that reads the data of a supplier, the cutting format of a machine, a panel with a check of your own. If it is only
once, a Code node is enough; if it is for you and others, or every week, it is an extension.

## How

You need Tensela and a text editor. It helps to know a little Python: an extension is a folder with its card and a
small Python package.

### 1. Start from the template

Copy the repository [extension-template](https://github.com/tensela/extension-template) (on GitHub, **Use this template**, or download it as
a `.zip`). It brings a node (**Fold**, the zigzag of a folded plate
roof), an action, a right-click entry, a panel, an icon, its tests and what publishes it.

```
facade-tools/                      the folder: the id of the extension
    extension.toml                 its card
    facade_tools/                  its package: the id with "_" instead of "-"
        __init__.py                def register(tensela): …
        fold.svg                   its icon
    tests/test_my_extension.py
```

In `extension.toml`, change the `id` (lowercase letters, digits and `-`), its name, your name, what it does, its
licence and its links. Rename the package folder as the id with `_`.

### 2. Load it from its folder

1. **Extensions → Manage extensions… → Load a folder…** and choose the folder. It is on at once, without installing
   it; its card says «in development».
2. Change the code and save. On its card, **Reload** (the round arrow): Tensela reads it again, without closing it.
3. When you are done, in its **⋯**, **Stop developing it**. The folder stays as it is.

### 3. A node

```python
from tensela.nodes import Input

def fold(length, folds, rise, name=None):
    ...                      # it gives a Data: numbers, points, curves, surfaces…

def register(tensela):
    tensela.node("Fold", "Curves",
                 (Input("length", 12.0, single=True), Input("folds", 4, single=True),
                  Input("rise", 1.2, single=True)),
                 "fold", fold, "A folded line, as in a folded plate roof.", icon="fold")
```

The function receives the inputs by their name (and `name`, the node's) and gives its result. It must only compute:
it runs also in the process that computes, apart from the window, and the same inputs must give the same result.

### 4. Menus, panels, icons

```python
tensela.icon("fold", "facade_tools/fold.svg")              # 24 × 24, drawn with lines
tensela.action("Count the nodes", count_nodes)            # Extensions menu: count_nodes(window)
tensela.menu("node", "Add a Fold", add_fold)              # right click on a node: add_fold(window, node)
tensela.panel("Facade check", build_panel)                # Extensions menu: build_panel(window) gives a QWidget
tensela.on("selected", selected)                          # selected(window, node): a node chosen, or None
tensela.export("Machine format…", ".cut", write_cut)      # File → Export: write_cut(path, objects)
```

### 5. Change the project

Through the window, so Ctrl + Z undoes it in one step:

```python
def add_fold(window, node):
    def change(project):                                  # a copy of the open project
        new = project.graph.node("Fold", None, length=10, folds=4, rise=1)
        project.export.append(new.name)                   # its eye on
    window.edit_project(change, "A Fold node")
```

If `change` fails, nothing changed.

### 6. In Spanish (and other languages)

Write every text in English and translate it in the card:

```toml
[es]
name = "Herramientas de fachada"
description = "…"

[translations.es]
"Fold" = "Pliegue"
"length" = "largo"
```

### 7. Test it and pack it

```bash
python -m pytest tests
tensela-app --pack-extension .
```

With the AppImage: `Tensela.AppImage --pack-extension .`. It checks the card, leaves `<id>-<version>.zip` beside the
folder and says its SHA-256, its fingerprint. Try the `.zip` with **Install from a file…**, as the others will.

To share it with everyone: [Publish an extension](/manual/extensions/publish/).

## What it does

### Its card

| Key | |
|---|---|
| `id` | lowercase letters, digits and `-`; its folder and, with `_`, its package |
| `name`, `version`, `author`, `description` | what the card says |
| `tensela` | the oldest Tensela it works with (`"0.9"`) |
| `licence` | its licence, by its SPDX name (`"GPL-3.0-or-later"`, `"MIT"`…) |
| `website`, `issues`, `source`, `contact` | its links: where it is told about, where to report a problem, its code |
| `[permissions]` | what it may do besides computing, and why: `network`, `files`, `programs`, `local` |
| `[es]`, `[es.permissions]` | the card in Spanish |
| `[translations.es]` | its texts in Spanish |

### The door: what `register(tensela)` receives

| | Its function receives |
|---|---|
| `tensela.node(name, category, inputs, output, function, help, icon=)` | the inputs by name, and `name` |
| `tensela.export(label, suffix, function, help)` | the path and the visible objects (name, Data, style) |
| `tensela.action(label, function, help, icon=)` | the window |
| `tensela.menu(where, label, function, help, icon=)` | the window, and the node (`where="node"`); `"canvas"`, `"view"` |
| `tensela.panel(title, build, help)` | the window; it gives the panel's content |
| `tensela.icon(name, file)` | (an SVG of its folder) |
| `tensela.on(event, function)` | the window; `"window"`, `"computed"`, `"selected"` (+ node), `"project"`, `"sliders"` |
| `tensela.command(function, help)` | the arguments: `--extension <id> …`, without the window |

`unregister()`, if the package has one, is called when it is turned off. Everything it added goes away by itself.

### What it may use of the window

| | |
|---|---|
| `window.project` | the open project: `graph` (its nodes), `export` (those seen), `controls` (the sliders); None if none |
| `window.edit_project(change, what)` | to change it, as one step of Ctrl + Z |
| `window.last_errors` | what failed in the last computation: node → message |
| `window.also_calculate` | nodes to calculate too, though they are not seen (empty it after) |
| `window.show_extension_panel(title)` | to open one of its panels |
| `window.statusBar().showMessage(text)` | to say something at the bottom |
| `window.viewer.save_image(path)` | the 3D view as a PNG |

## Tips

- Keep the function of a node pure: no files, no network, no window. What needs them goes in an action or a panel.
- A long task in an action blocks the window: split it, or say what it does in the status bar while it works.
- The icon is tinted with the colour of the theme: draw it with lines (`stroke`), without fixed colours.
- The animation and the AI connection extensions are also examples: their code is in the repository of Tensela.

## How it runs

An extension is Python that Tensela imports: it can do anything Python does, which is why its card says what it does
and why the catalogue reviews its code. Its nodes are registered in the window and in the process that computes (a
separate process, so a long computation does not freeze the window); that is why a node only computes. When it is
turned off, Tensela takes away what it registered and forgets its package, so **Reload** reads it again from its
folder.
