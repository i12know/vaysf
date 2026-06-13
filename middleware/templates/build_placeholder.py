# templates/build_placeholder.py
"""
Regenerate the committed placeholder badge template.

Produces a 1080x1920 PNG with the wireframe-accurate four-section layout
so badges render correctly from the fallback background.  Run from the
middleware/ directory:

    python templates/build_placeholder.py

The output is committed at templates/badge_template.png.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

W, H = 1080, 1920

# Section boundaries — must match badges/generator.py constants
TAGLINE_Y0, TAGLINE_Y1   = 0,   170
THEME_Y0,   THEME_Y1     = 170, 800
IDENTITY_Y0, IDENTITY_Y1 = 800, 1115
CARDS_Y0                 = 1115

# Section colours
COL_TAGLINE_BG  = (255, 255, 255, 255)
COL_THEME_BG    = (14,  22,  50,  255)   # deep navy  #0e1632
COL_IDENTITY_BG = (255, 255, 255, 255)
COL_CARDS_BG    = (228, 233, 241, 255)   # light blue-grey

# Subtle divider line between sections
COL_DIVIDER     = (180, 190, 210, 255)


def build(out_path: Path) -> Path:
    img  = Image.new("RGBA", (W, H), COL_TAGLINE_BG)
    draw = ImageDraw.Draw(img)

    # Section 2 — deep navy theme block
    draw.rectangle((0, THEME_Y0,    W, THEME_Y1),    fill=COL_THEME_BG)

    # Section 3 — white identity block (already the base colour; draw explicitly
    #             so the boundary is clear if someone opens the raw template file)
    draw.rectangle((0, IDENTITY_Y0, W, IDENTITY_Y1), fill=COL_IDENTITY_BG)

    # Section 4 — light blue-grey cards area
    draw.rectangle((0, CARDS_Y0,    W, H),            fill=COL_CARDS_BG)

    # Thin divider at section boundaries (subtle, not visible on the final badge
    # because text/photo sit on top, but useful when inspecting the template file)
    for y in (TAGLINE_Y1, IDENTITY_Y0, CARDS_Y0):
        draw.line((0, y, W, y), fill=COL_DIVIDER, width=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "badge_template.png"
    path = build(target)
    print(f"Wrote placeholder template: {path}")
