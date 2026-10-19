"""Generate the placeholder pictures for a lesson: two portraits and an office background.

These are flat illustrations drawn in code, so a lesson can be rendered before real
artwork exists. Replace them with your own PNGs, keeping the same file names. The
portraits are square; the background is 16:9. Nothing here depends on the renderer.

Usage::

    python -m scripts.blender_lesson.make_placeholder_assets examples/assets/us-sox-0003

Requires Pillow (``pip install pillow``). Only this generator needs it, not the renderer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PORTRAIT_PX = 512
BACKGROUND_SIZE = (1920, 1080)
#: One neutral skin tone for both figures. Swap the artwork if you need a different cast.
SKIN = (226, 190, 160)
FEATURE = (60, 45, 40)


def make_portrait(
    path: Path,
    *,
    hair: tuple[int, int, int],
    shirt: tuple[int, int, int],
    tie: tuple[int, int, int] | None,
) -> None:
    """A head-and-shoulders figure on a plain backdrop."""
    img = Image.new("RGB", (PORTRAIT_PX, PORTRAIT_PX), (232, 236, 242))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((40, 330, 472, 640), radius=70, fill=shirt)
    draw.rectangle((216, 280, 296, 350), fill=SKIN)
    draw.ellipse((156, 96, 356, 316), fill=SKIN)
    draw.pieslice((150, 78, 362, 240), 180, 360, fill=hair)
    if tie is not None:
        draw.polygon([(256, 340), (232, 400), (256, 470), (280, 400)], fill=tie)
    draw.ellipse((205, 200, 223, 218), fill=FEATURE)
    draw.ellipse((289, 200, 307, 218), fill=FEATURE)
    draw.arc((214, 228, 298, 282), 20, 160, fill=FEATURE, width=6)
    img.save(path)


def make_office(path: Path) -> None:
    """A plain office: window, desk, monitor, plant and a framed picture."""
    width, height = BACKGROUND_SIZE
    img = Image.new("RGB", (width, height), (236, 232, 224))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 780, width, height), fill=(200, 190, 175))
    draw.rectangle((1150, 180, 1650, 620), fill=(190, 220, 240), outline=(255, 255, 255), width=18)
    draw.line((1400, 180, 1400, 620), fill=(255, 255, 255), width=12)
    draw.line((1150, 400, 1650, 400), fill=(255, 255, 255), width=12)
    draw.rectangle((360, 600, 1000, 640), fill=(120, 85, 55))
    draw.rectangle((380, 640, 400, 780), fill=(100, 70, 45))
    draw.rectangle((960, 640, 980, 780), fill=(100, 70, 45))
    draw.rectangle((560, 380, 800, 580), fill=(40, 44, 52))
    draw.rectangle((665, 580, 695, 600), fill=(40, 44, 52))
    draw.rectangle((1500, 720, 1560, 800), fill=(150, 90, 60))
    draw.ellipse((1440, 560, 1620, 740), fill=(70, 140, 80))
    draw.rectangle((200, 200, 400, 380), fill=(210, 225, 215), outline=(90, 90, 90), width=10)
    img.save(path)


def generate(out_dir: Path) -> list[Path]:
    """Write the three placeholder pictures into ``out_dir`` and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manager = out_dir / "manager.png"
    intern = out_dir / "intern.png"
    office = out_dir / "office.png"
    make_portrait(manager, hair=(150, 150, 155), shirt=(35, 45, 75), tie=(140, 30, 35))
    make_portrait(intern, hair=(70, 50, 35), shirt=(190, 215, 235), tie=None)
    make_office(office)
    return [manager, intern, office]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate placeholder lesson pictures.")
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args(argv)
    for path in generate(args.out_dir):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
