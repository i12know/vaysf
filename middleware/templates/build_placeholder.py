# templates/build_placeholder.py
"""Regenerate the neutral 1080x1920 badge background.

All wireframe panels and dynamic elements are drawn by BadgeGenerator. Keeping
the committed template neutral prevents stale background geometry from leaking
into future layout revisions.
"""

from pathlib import Path

from PIL import Image

W, H = 1080, 1920
COL_BG = (255, 255, 255, 255)


def build(out_path: Path) -> Path:
    image = Image.new("RGBA", (W, H), COL_BG)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "badge_template.png"
    path = build(target)
    print(f"Wrote placeholder template: {path}")
