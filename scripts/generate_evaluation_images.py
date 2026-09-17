"""Generate the deterministic synthetic image corpus used by Phase 7 tests."""

from __future__ import annotations

from pathlib import Path
from random import Random

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "fixtures" / "vision_v1"


def _shirt(draw: ImageDraw.ImageDraw, color: tuple[int, int, int], x: int = 64) -> None:
    draw.polygon([(x, 58), (x + 30, 38), (x + 58, 58), (x + 44, 88), (x + 44, 208), (x - 14, 208), (x - 14, 88)], fill=color)


def _trousers(draw: ImageDraw.ImageDraw, color: tuple[int, int, int], x: int = 80) -> None:
    draw.polygon([(x, 36), (x + 72, 36), (x + 64, 214), (x + 37, 214), (x + 34, 96), (x + 26, 214), (x, 214)], fill=color)


def generate() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rng = Random(7)
    for index in range(1, 31):
        image = Image.new("RGB", (256, 256), (242, 239, 232))
        draw = ImageDraw.Draw(image)
        if index <= 20:
            if index % 2:
                _shirt(draw, (244, 244, 240), 92)
                draw.rectangle((90, 58, 152, 61), fill=(190, 187, 180))
            else:
                _trousers(draw, (35, 52, 86), 92)
        elif index <= 23:
            _shirt(draw, (235, 235, 228), 40)
            _trousers(draw, (35, 52, 86), 142)
        elif index <= 26:
            draw.ellipse((94, 18, 160, 84), fill=(184, 142, 112))
            _shirt(draw, (235, 235, 228), 94)
            _trousers(draw, (35, 52, 86), 92)
        elif index <= 28:
            for _ in range(18):
                x1, y1 = rng.randrange(0, 220), rng.randrange(0, 220)
                draw.rectangle((x1, y1, x1 + rng.randrange(15, 60), y1 + rng.randrange(15, 60)), fill=(rng.randrange(30, 230), rng.randrange(30, 230), rng.randrange(30, 230)))
        else:
            _shirt(draw, (225, 225, 218), 92)
            image = image.filter(ImageFilter.GaussianBlur(radius=8))
        image.save(OUTPUT / f"v{index:02d}.jpg", format="JPEG", quality=88, optimize=True)


if __name__ == "__main__":
    generate()
