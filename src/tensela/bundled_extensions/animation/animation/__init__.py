"""Animation: what a slider does as it moves, exported as a GIF or a series of PNG images.

It is a panel (Extensions → Animation), beside Values: the 3D view stays in sight, to frame it.
The slider goes from one value to another in a number of frames; at each one Tensela computes, and the 3D view is
saved as it is seen (the same framing). Then Pillow (which comes with Tensela) joins them into a GIF, or they stay as
PNG images in a folder (for a video editor). At the end the slider is back where it was.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from tensela.language import tr
from tensela.values import label_input

WIDTHS = (640, 800, 1080, 1280, 1920)


def sliders(window) -> list[tuple[str, object, int | None]]:
    """The sliders of Values: (what it is called, its control, its index in a list or None)."""
    out = []
    for key in window.sliders:
        base, _, rest = key.partition("[")
        control = next((c for c in window.project.controls if c.key == base), None)
        if control is None:
            continue
        index = int(rest.rstrip("]")) if rest else None
        name = control.label or f"{control.node} · {label_input(control.input_)}"
        out.append((name + (f" [{index + 1}]" if index is not None else ""), control, index))
    return out


def values(start: float, end: float, frames: int, back_and_forth: bool) -> list[float]:
    """The value of the slider at each frame (back and forth: and back again, without repeating the ends)."""
    frames = max(2, int(frames))
    there = [start + (end - start) * k / (frames - 1) for k in range(frames)]
    return there + there[-2:0:-1] if back_and_forth else there


def make_gif(images: list[Path], target: Path, seconds: float, width: int | None) -> None:
    """The images, in order, as a GIF that loops; each frame lasts the same."""
    from PIL import Image
    frames = []
    for path in images:
        with Image.open(path) as img:
            frame = img.convert("RGB")
        if width and frame.width != width:
            frame = frame.resize((width, round(frame.height * width / frame.width)), Image.Resampling.LANCZOS)
        frames.append(frame.quantize(colors=255, method=Image.Quantize.MEDIANCUT))
    duration = max(20, round(1000 * seconds / len(frames)))
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=duration, loop=0, optimize=True,
                   disposal=2)


def save_pngs(images: list[Path], folder: Path, width: int | None) -> list[Path]:
    from PIL import Image
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for k, path in enumerate(images, 1):
        target = folder / f"frame-{k:04d}.png"
        with Image.open(path) as img:
            frame = img.convert("RGB")
        if width and frame.width != width:
            frame = frame.resize((width, round(frame.height * width / frame.width)), Image.Resampling.LANCZOS)
        frame.save(target)
        out.append(target)
    return out


def capture(window, control, index, value_list, background, stop=lambda: False, step=lambda k, n: None):
    """Each value, computed and the view saved; the slider back where it was. The images (in a temporary folder:
    the caller deletes it), or None if it was stopped."""
    from PySide6.QtWidgets import QApplication
    key = control.key if index is None else f"{control.key}[{index}]"
    from tensela.project_file import numbers_items
    current = window.project.graph.nodes[control.node].inputs[control.input_]
    before = float(numbers_items(current)[index] if index is not None else current)
    folder = Path(tempfile.mkdtemp(prefix="tensela-animation-"))
    images = []
    try:
        for k, value in enumerate(value_list):
            if stop():
                return None, folder
            if float(control.step).is_integer():
                value = round(value)
            window.change(control, value, index)
            window.wait_computation()
            QApplication.processEvents()
            path = folder / f"{k:04d}.png"
            window.viewer.save_image(path, scale=1, background=background, axes=False)
            images.append(path)
            step(k + 1, len(value_list))
        return images, folder
    finally:
        window.change(control, before, index)
        window.wait_computation()
        slider = window.sliders.get(key)
        if slider is not None:
            try:
                slider.put(before)
            except RuntimeError:
                pass


def animate(window) -> None:
    """Extensions → Animate a slider…: its panel, open and in front."""
    window.show_extension_panel("Animation", "animation")


#: Its panel, once built (it is built the first time it is opened).
_PANEL = None


def panel(window):
    global _PANEL
    from .panel import AnimationPanel
    _PANEL = AnimationPanel(window)
    return _PANEL


def _refresh(window, *_):
    """The panel, once built, reads the sliders again (one added, another project)."""
    if _PANEL is not None:
        _PANEL.refresh()


def register(tensela) -> None:
    tensela.icon("film", "film.svg")
    tensela.panel("Animation", panel, "What a slider does as it moves, as a GIF or PNG images")
    tensela.menu("view", "Animate a slider…", animate, "What a slider does as it moves, as a GIF or PNG images",
                 icon="film")
    for event in ("sliders", "project", "computed"):
        tensela.on(event, _refresh)
