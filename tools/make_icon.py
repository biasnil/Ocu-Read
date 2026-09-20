"""Build assets/icon.ico from assets/icon.png (and draw a placeholder icon.png if none exists).

Usage:
    python tools/make_icon.py            # regenerate icon.ico if it is missing or older than icon.png
    python tools/make_icon.py --force    # always regenerate icon.ico

To use your own artwork: replace assets/icon.png (square, at least 256x256, transparent corners look best)
and run this script - build.bat does it automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "assets"
PNG, ICO = ASSETS / "icon.png", ASSETS / "icon.ico"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw_placeholder(size: int = 512) -> Image.Image:
    """A simple document with a magnifier, used only when no icon.png was supplied."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 512
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(110 * s), fill=(32, 34, 38, 255))
    d.polygon([(130 * s, 70 * s), (320 * s, 70 * s), (390 * s, 140 * s), (390 * s, 420 * s), (130 * s, 420 * s)],
              fill=(236, 228, 210, 255))
    d.polygon([(320 * s, 70 * s), (390 * s, 140 * s), (320 * s, 140 * s)], fill=(190, 180, 160, 255))
    for i in range(6):
        y = (170 + i * 38) * s
        d.rectangle([165 * s, y, (335 if i % 2 == 0 else 300) * s, y + 14 * s], fill=(40, 40, 40, 255))
    d.ellipse([250 * s, 250 * s, 400 * s, 400 * s], outline=(231, 76, 60, 255), width=int(20 * s))
    d.line([(385 * s, 385 * s), (450 * s, 450 * s)], fill=(231, 76, 60, 255), width=int(28 * s))
    return img


def main(argv: list[str]) -> int:
    """Create whatever is missing; returns a process exit code."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    if not PNG.exists():
        draw_placeholder().save(PNG)
        print(f"[icon] {PNG.name} not found - wrote a placeholder (replace it with your own artwork)")
    if "--force" in argv or not ICO.exists() or ICO.stat().st_mtime < PNG.stat().st_mtime:
        src = Image.open(PNG).convert("RGBA")
        if src.width != src.height:  # centre on a square canvas
            side = max(src.size)
            canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            canvas.paste(src, ((side - src.width) // 2, (side - src.height) // 2))
            src = canvas
        if src.width < 256:
            src = src.resize((256, 256), Image.LANCZOS)
        src.save(ICO, format="ICO", sizes=ICO_SIZES)
        print(f"[icon] wrote {ICO.name} ({len(ICO_SIZES)} sizes, 16-256 px)")
    else:
        print("[icon] icon.ico is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
