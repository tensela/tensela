"""Run a graph from the terminal.

    tensela examples/case_01.json
    tensela examples/case_01.json --change attractor.x=15 --change sun_fin.width=0.3
    tensela examples/case_01.json --obj other/path.obj --unit mm
    tensela examples/case_01.json --png view.png --size 3840x2160
    tensela examples/case_01.json --dxf facade.dxf --unit mm
    tensela examples/case_01.json --dxf elevation.dxf --dxf-view "south elevation"
    tensela examples/case_01.json --igz facade.igz
    tensela examples/case_01.json --sketch facade.pdf --sketch-style watercolour

The Spanish option names of before (--cambiar, --unidad, --tamaño…) still work.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .project_file import open_
from .connectors.blender import export_blend
from .connectors.dxf import OLD_VIEWS, VIEWS, export_dxf
from .connectors.ingetrazo import export_igz
from .connectors.obj import UNITS, export_obj
from .data import ShapeError
from .language import tr
from .values import text_value


def run() -> int:
    """The command, as it is typed: in the language of the computer."""
    from . import language
    language.LANGUAGE = language.system_language()
    return main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tensela",
        description=tr("Computes a saved graph and exports its geometry to OBJ."),
    )
    # Each option in English; the Spanish name of before still works (scripts written with it).
    parser.add_argument("file", metavar=tr("FILE"), help=tr("the graph (.tela or .json)"))
    parser.add_argument("--change", "--cambiar", action="append", default=[], metavar=tr("NODE.INPUT=VALUE"),
                        help=tr("changes an input before computing; can be repeated"))
    parser.add_argument("--obj", metavar=tr("PATH"),
                        help=tr("where to write the OBJ (by default, next to the file, with extension .obj)"))
    parser.add_argument("--unit", "--unidad", choices=list(UNITS), default="m",
                        help=tr("unit of the OBJ and the DXF: m (default), cm, mm, in (inches) or ft (feet)"))
    parser.add_argument("--dxf", metavar=tr("PATH"), help=tr("also save a DXF (one layer per node)"))
    parser.add_argument("--dxf-view", "--dxf-vista", type=_dxf_view, metavar=tr("VIEW"),
                        help=tr("2D DXF: {views} (without this, in 3D)").format(views=", ".join(VIEWS)))
    parser.add_argument("--dxf-visible", action="store_true",
                        help=tr("2D DXF: only what is seen (removes the hidden lines)"))
    parser.add_argument("--dxf-compatible", action="store_true",
                        help=tr("DXF with classic meshes, for old programs or SketchUp (slower)"))
    parser.add_argument("--blend", metavar=tr("PATH"), help=tr("also save a Blender .blend (needs Blender)"))
    parser.add_argument("--igz", metavar=tr("PATH"), help=tr("also save an IngeTrazo document (.igz)"))
    parser.add_argument("--png", metavar=tr("PATH"), help=tr("also save an image of the 3D view (needs the interface)"))
    parser.add_argument("--size", "--tamaño", default="1920x1080", metavar=tr("WIDTHxHEIGHT"),
                        help=tr("size of the image in pixels (1920x1080 by default)"))
    parser.add_argument("--background", "--fondo", default="white", metavar=tr("COLOUR"),
                        help=tr("background of the image: white (default), #rrggbb or transparent"))
    parser.add_argument("--sketch", "--croquis", metavar=tr("PATH"),
                        help=tr("also a freehand sketch of the view (.png, .svg or .pdf)"))
    parser.add_argument("--sketch-style", "--croquis-estilo", default="colour_marker", metavar=tr("STYLE"),
                        help=tr("ink, grey_marker, colour_marker (default), watercolour, hatched or contrast"))
    parser.add_argument("--by-element", "--por-elemento", action="store_true",
                        help=tr("each element as its own group (Split By Group in Blender)"))
    args = parser.parse_args(argv)

    try:
        project = open_(args.file)
        graph, export = project.graph, project.export
        for change in args.change:
            node, input_, value = _read_change(change)
            graph.change(node, input_, value)

        # Compute everything and show the shape of each data: the data can be seen.
        width = max(len(n) for n in graph.nodes)
        width_kind = max(len(tr(n.kind.name)) for n in graph.nodes.values())
        for name, node in graph.nodes.items():
            data = graph.value(node)
            what = tr(data.kind.name) if data.kind is not None else tr("yes/no" if data.values.dtype == bool else "number")
            shape = text_value(data.values.item()) if not data.levels and data.kind is None else data.shape
            print(f"  {name:<{width}}  {tr(node.kind.name):<{width_kind}}  {what}: {shape}", flush=True)

        if not export:
            print("\n" + tr('(The file does not say what to export: add "export": ["node", …].)'))
            return 0
        output = Path(args.obj) if args.obj else Path(args.file).with_suffix(".obj")
        # An OBJ does not keep loose points: they are seen in the view, but they do not go to the file.
        with_shape = [n for n in export if graph.value(n).kind is not None and
                     (graph.value(n).kind.faces is not None or graph.value(n).kind.curve)]
        if with_shape:
            export_obj(output, *(graph.value(n) for n in with_shape),
                         unit=args.unit, by_element=args.by_element)
            print("\n" + tr("Written: {path} ({nodes}; in {unit})").format(
                path=output, nodes=", ".join(with_shape), unit=args.unit))
        without_shape = [n for n in export if n not in with_shape]
        if without_shape:
            print(tr("(Not passed to the OBJ, which does not keep loose points: {nodes}.)").format(
                nodes=", ".join(without_shape)))
        if args.blend:
            filepath = export_blend(args.blend, project.visible_objects(), Path(args.file).stem)
            print(tr("Written: {path} (Blender: one object per node, in metres, Z up)").format(path=filepath))
        if args.dxf:
            filepath = export_dxf(args.dxf, project.visible_objects(), unit=args.unit,
                                compatible=args.dxf_compatible, view=args.dxf_view,
                                visible_only=args.dxf_visible)
            what = (tr("in 2D, {view}").format(view=tr(args.dxf_view)) if args.dxf_view else tr("in 3D, Z up"))
            print(tr("Written: {path} (DXF {what}: one layer per node, in {unit})").format(
                path=filepath, what=what, unit=args.unit))
        if args.igz:
            filepath = export_igz(args.igz, project.visible_objects(), Path(args.file).stem)
            print(tr("Written: {path} (IngeTrazo: one group per node and per piece, in metres)").format(path=filepath))
        if args.png:
            width, height = _read_size_(args.size)
            try:
                from .ui.viewer import image
            except ImportError:
                raise ShapeError(tr("Saving images needs the interface: pip install -e '.[ui]'.")) from None
            background = "transparent" if args.background in ("transparent", "transparente") else args.background
            width, height = image(args.png, project.visible_objects(), width, height, background=background)
            print(tr("Written: {path} ({width} × {height} px)").format(path=args.png, width=width, height=height))
        if args.sketch:
            width, height = _read_size_(args.size)
            filepath = _sketch(args.sketch, project.visible_objects(), args.sketch_style, width, height)
            print(tr("Written: {path} (sketch, {style}, {width} px wide)").format(
                path=filepath, style=args.sketch_style, width=width))
        return 0
    except ShapeError as error:
        print(f"✖ {error}", file=sys.stderr)
        return 1


def _dxf_view(text: str) -> str:
    """The view of a 2D DXF, in English or as it was written before («alzado sur»)."""
    view = OLD_VIEWS.get(text, text)
    if view not in VIEWS:
        raise argparse.ArgumentTypeError(tr("I don't know the view “{view}”. Options: {options}.").format(
            view=text, options=", ".join(VIEWS)))
    return view


def _sketch(filepath: str, objects, style_name: str, width: int, height: int) -> str:
    try:
        from PySide6.QtGui import QGuiApplication

        from . import croquis
        from .croquis import export, presets
        from .ui.viewer import camera_framed
    except ImportError:
        raise ShapeError(tr("The sketch needs the interface: pip install -e '.[ui]'.")) from None
    if style_name not in presets.PRESETS:
        raise ShapeError(tr("I don't know the style “{style}”. Options: {options}.").format(
            style=style_name, options=", ".join(presets.PRESETS)))
    import os
    if not QGuiApplication.instance():
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _app = QGuiApplication([])  # noqa: F841 (the PDF and Qt's painting need it)
    layers = croquis.draw(objects, camera_framed(objects, width, height), width, style_name)
    if not export.save(layers, filepath):
        raise ShapeError(tr("“{path}” could not be saved.").format(path=filepath))
    return filepath


def _read_size_(text: str) -> tuple[int, int]:
    """'1920x1080' → (1920, 1080)."""
    try:
        width, height = (int(n) for n in text.lower().replace("×", "x").split("x"))
    except ValueError:
        raise ShapeError(tr("“{text}” is not a size: it is written WIDTHxHEIGHT, for example 1920x1080.").format(text=text)) from None
    if not (16 <= width <= 16384 and 16 <= height <= 16384):
        raise ShapeError(tr("“{text}”: the width and the height go from 16 to 16 384 pixels.").format(text=text))
    return width, height


def _read_change(text: str) -> tuple[str, str, object]:
    """'attractor.x=15' → ('attractor', 'x', 15). The value is read as a number, a list or a text."""
    if "=" not in text or "." not in text.split("=", 1)[0]:
        raise ShapeError(tr("“{text}” is not understood: it is written NODE.INPUT=VALUE, for example attractor.x=15.").format(
            text=text))
    key, value = text.split("=", 1)
    node, input_ = key.rsplit(".", 1)
    try:
        read = json.loads(value)
    except json.JSONDecodeError:
        read = value
    return node, input_, read


if __name__ == "__main__":
    sys.exit(main())
