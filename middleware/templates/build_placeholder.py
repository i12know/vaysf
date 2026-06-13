# templates/build_placeholder.py
"""
Regenerate the committed placeholder badge template.

This produces a plain 1080x1920 PNG with a header/footer band and subtle
safe-zone guides — enough to render and review badges before a designer
delivers the real branded template.  Run from the middleware/ directory:

    python templates/build_placeholder.py

The output is committed at templates/badge_template.png.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

W, H = 1080, 1920
COL_BG = (245, 247, 250, 255)
COL_BAND = (18, 52, 86, 255)
COL_ACCENT = (200, 32, 48, 255)
COL_GUIDE = (210, 216, 224, 255)

SAFE = {"left": 80, "right": 80, "top": 120, "bottom": 180}


def build(out_path: Path) -> Path:
    img = Image.new("RGBA", (W, H), COL_BG)
    draw = ImageDraw.Draw(img)

    # Header + accent underline
    draw.rectangle((0, 0, W, 220), fill=COL_BAND)
    draw.rectangle((0, 220, W, 232), fill=COL_ACCENT)

    # Footer + accent overline
    draw.rectangle((0, H - 120, W, H), fill=COL_BAND)
    draw.rectangle((0, H - 132, W, H - 120), fill=COL_ACCENT)

    # Subtle safe-zone guide (helps designers align the real template)
    draw.rectangle(
        (SAFE["left"], SAFE["top"], W - SAFE["right"], H - SAFE["bottom"]),
        outline=COL_GUIDE, width=2,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "badge_template.png"
    path = build(target)
    print(f"Wrote placeholder template: {path}")
