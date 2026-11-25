"""The projects of the start screen («Start from a recipe»): the first project of the manual and its recipes, copied
into `src/tensela/templates/` with a small picture of each one (480 × 300), so that they travel inside Tensela.

They come from the examples of the repository (`examples/`, CC0) and the pictures of the manual
(`manual/images/recipes/`, and the result of the first project). Run it again when an example or its picture changes.

    .venv/bin/python tools/start_templates.py                    # from ./examples, or ../tensela/examples
    .venv/bin/python tools/start_templates.py path/to/tensela    # from another copy of the repository
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "tensela" / "templates"
SIZE = (480, 300)
#: The projects, in the order of the start screen, and their pictures in the manual.
PROJECTS = [("first-project", "app/first-project-result-en.png")] + [
    (name, f"recipes/{name}.png") for name in (
        "breathing-facade", "twisting-tower", "hypar-roof", "rib-wall", "voronoi-skin", "hanging-vault",
        "waffle-model", "sun-study")]


def repository(args: list[str]) -> Path:
    if args:
        return Path(args[0]).resolve()
    return ROOT if (ROOT / "examples").is_dir() else ROOT.parent / "tensela"


def picture(source: Path, target: Path) -> None:
    """The picture cut to 16:10 around its centre and made small."""
    image = Image.open(source).convert("RGB")
    w, h = image.size
    ratio = SIZE[0] / SIZE[1]
    if w / h > ratio:
        cut = round(h * ratio)
        image = image.crop(((w - cut) // 2, 0, (w - cut) // 2 + cut, h))
    else:
        cut = round(w / ratio)
        image = image.crop((0, (h - cut) // 2, w, (h - cut) // 2 + cut))
    image.resize(SIZE, Image.Resampling.LANCZOS).save(target, optimize=True)


def main(args: list[str]) -> int:
    repo = repository(args)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, image in PROJECTS:
        project = repo / "examples" / (f"{name}.tela" if name == "first-project" else f"recipes/{name}.tela")
        shutil.copy2(project, OUT / f"{name}.tela")
        picture(repo / "manual" / "images" / image, OUT / f"{name}.png")
        print("✓", name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
