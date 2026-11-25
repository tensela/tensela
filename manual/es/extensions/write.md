---
title: Escribir una extensión
description: De la plantilla al .zip, paso a paso, y todo lo que una extensión puede usar de Tensela.
---

## Para qué

Para lo que Tensela no trae y necesitas una y otra vez: el módulo de un sistema de fachada de tu estudio, un nodo que
lee los datos de un proveedor, el formato de corte de una máquina, un panel con una verificación propia. Si es una
sola vez, alcanza con un nodo Código; si es para ti y para otros, o para cada semana, es una extensión.

## Cómo

Necesitas Tensela y un editor de texto. Ayuda saber un poco de Python: una extensión es una carpeta con su ficha y un
paquete de Python pequeño.

### 1. Empieza por la plantilla

Copia el repositorio [extension-template](https://github.com/tensela/extension-template) (en GitHub, **Use this template**, o descárgalo como
`.zip`). Trae un nodo (**Pliegue**, el zigzag de una cubierta
plegada), una acción, una entrada del clic derecho, un panel, un icono, sus pruebas y lo que la publica.

```
facade-tools/                      la carpeta: el id de la extensión
    extension.toml                 su ficha
    facade_tools/                  su paquete: el id con "_" en vez de "-"
        __init__.py                def register(tensela): …
        fold.svg                   su icono
    tests/test_my_extension.py
```

En `extension.toml`, cambia el `id` (minúsculas, números y `-`), su nombre, tu nombre, qué hace, su licencia y sus
enlaces. Renombra la carpeta del paquete como el id con `_`.

### 2. Cárgala desde su carpeta

1. **Extensiones → Gestionar extensiones… → Cargar una carpeta…** y elige la carpeta. Queda encendida en el acto, sin
   instalarla; su tarjeta dice «en desarrollo».
2. Cambia el código y guarda. En su tarjeta, **Recargar** (la flecha circular): Tensela la vuelve a leer, sin
   cerrarse.
3. Cuando termines, en su **⋯**, **Dejar de desarrollarla**. La carpeta queda como está.

### 3. Un nodo

```python
from tensela.nodes import Input

def fold(length, folds, rise, name=None):
    ...                      # da un Data: números, puntos, curvas, superficies…

def register(tensela):
    tensela.node("Fold", "Curves",
                 (Input("length", 12.0, single=True), Input("folds", 4, single=True),
                  Input("rise", 1.2, single=True)),
                 "fold", fold, "A folded line, as in a folded plate roof.", icon="fold")
```

La función recibe las entradas por su nombre (y `name`, el del nodo) y da su resultado. Solo debe calcular: corre
también en el proceso que calcula, aparte de la ventana, y las mismas entradas deben dar el mismo resultado.

### 4. Menús, paneles, iconos

```python
tensela.icon("fold", "facade_tools/fold.svg")              # 24 × 24, dibujado con líneas
tensela.action("Count the nodes", count_nodes)            # menú Extensiones: count_nodes(window)
tensela.menu("node", "Add a Fold", add_fold)              # clic derecho en un nodo: add_fold(window, node)
tensela.panel("Facade check", build_panel)                # menú Extensiones: build_panel(window) da un QWidget
tensela.on("selected", selected)                          # selected(window, node): un nodo elegido, o None
tensela.export("Machine format…", ".cut", write_cut)      # Archivo → Exportar: write_cut(path, objects)
```

### 5. Cambiar el proyecto

A través de la ventana, así Ctrl + Z lo deshace en un paso:

```python
def add_fold(window, node):
    def change(project):                                  # una copia del proyecto abierto
        new = project.graph.node("Fold", None, length=10, folds=4, rise=1)
        project.export.append(new.name)                   # su ojo encendido
    window.edit_project(change, "A Fold node")
```

Si `change` falla, no cambió nada.

### 6. En español (y otros idiomas)

Escribe cada texto en inglés y tradúcelo en la ficha:

```toml
[es]
name = "Herramientas de fachada"
description = "…"

[translations.es]
"Fold" = "Pliegue"
"length" = "largo"
```

### 7. Pruébala y empaquétala

```bash
python -m pytest tests
tensela-app --pack-extension .
```

Con la AppImage: `Tensela.AppImage --pack-extension .`. Revisa la ficha, deja `<id>-<versión>.zip` al lado de la
carpeta y dice su SHA-256, su huella. Prueba el `.zip` con **Instalar desde un archivo…**, como lo harán los demás.

Para compartirla con todos: [Publicar una extensión](/es/manual/extensions/publish/).

## Qué hace

### Su ficha

| Clave | |
|---|---|
| `id` | minúsculas, números y `-`; su carpeta y, con `_`, su paquete |
| `name`, `version`, `author`, `description` | lo que dice la ficha |
| `tensela` | la Tensela más vieja con la que funciona (`"0.9"`) |
| `licence` | su licencia, por su nombre SPDX (`"GPL-3.0-or-later"`, `"MIT"`…) |
| `website`, `issues`, `source`, `contact` | sus enlaces: dónde se cuenta, dónde reportar un problema, su código |
| `[permissions]` | qué puede hacer además de calcular, y para qué: `network`, `files`, `programs`, `local` |
| `[es]`, `[es.permissions]` | la ficha en español |
| `[translations.es]` | sus textos en español |

### La puerta: lo que recibe `register(tensela)`

| | Su función recibe |
|---|---|
| `tensela.node(name, category, inputs, output, function, help, icon=)` | las entradas por nombre, y `name` |
| `tensela.export(label, suffix, function, help)` | la ruta y los objetos visibles (nombre, Data, estilo) |
| `tensela.action(label, function, help, icon=)` | la ventana |
| `tensela.menu(where, label, function, help, icon=)` | la ventana, y el nodo (`where="node"`); `"canvas"`, `"view"` |
| `tensela.panel(title, build, help)` | la ventana; da el contenido del panel |
| `tensela.icon(name, file)` | (un SVG de su carpeta) |
| `tensela.on(event, function)` | la ventana; `"window"`, `"computed"`, `"selected"` (+ nodo), `"project"`, `"sliders"` |
| `tensela.command(function, help)` | los argumentos: `--extension <id> …`, sin la ventana |

`unregister()`, si el paquete tiene uno, se llama al apagarla. Todo lo que agregó se va solo.

### Lo que puede usar de la ventana

| | |
|---|---|
| `window.project` | el proyecto abierto: `graph` (sus nodos), `export` (los visibles), `controls` (los deslizadores); None si no hay |
| `window.edit_project(change, what)` | para cambiarlo, como un paso de Ctrl + Z |
| `window.last_errors` | lo que falló en el último cálculo: nodo → mensaje |
| `window.also_calculate` | nodos para calcular también, aunque no se vean (vacíalo después) |
| `window.show_extension_panel(title)` | para abrir uno de sus paneles |
| `window.statusBar().showMessage(text)` | para decir algo abajo |
| `window.viewer.save_image(path)` | la vista 3D como PNG |

## Trucos

- Mantén pura la función de un nodo: sin archivos, sin red, sin ventana. Lo que los necesita va en una acción o un
  panel.
- Una tarea larga en una acción bloquea la ventana: divídela, o di qué hace en la barra de abajo mientras trabaja.
- El icono se tiñe con el color del tema: dibújalo con líneas (`stroke`), sin colores fijos.
- Las extensiones Animación y Conexión con IA también son ejemplos: su código está en el repositorio de Tensela.

## Cómo corre

Una extensión es Python que Tensela importa: puede hacer todo lo que hace Python, y por eso su ficha dice qué hace y
el catálogo revisa su código. Sus nodos se registran en la ventana y en el proceso que calcula (un proceso aparte,
para que un cálculo largo no congele la ventana); por eso un nodo solo calcula. Al apagarla, Tensela quita lo que
registró y olvida su paquete, así **Recargar** la vuelve a leer desde su carpeta.
