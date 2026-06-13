# badges/generator.py
"""
BadgeGenerator — renders a single 1080x1920 athlete badge PNG with Pillow.

This module is intentionally **pure rendering**: it takes already-fetched
participant data (a dict) and optional photo bytes, and produces an image.
No network calls live here — fetching WordPress participants and the
ChMeetings profile photo is the runner's job (``badges/runner.py``).  That
split keeps the renderer trivially unit-testable in mock mode.

v1 layout follows the approximate grid from the Issue #77 plan; it is meant
to be refined against the posted wireframe later.  Key behaviours that the
issue calls out are implemented now:

- Auto-shrink the athlete name so long names still fit (binary search).
- Circular profile photo with an **initials-on-colour** fallback so a missing
  photo is obvious to staff rather than a silent blank.
- Vietnamese diacritics preserved for display (never normalise for output).
- Event-info rows hide themselves when empty rather than rendering blank cards.
- QR slot reserved bottom-right with an ID-only placeholder payload.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import qrcode
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

# ── Canvas + layout constants (approximate v1 grid; refine vs wireframe) ──────

CANVAS_W, CANVAS_H = 1080, 1920

SAFE_PAD = {"left": 80, "right": 80, "top": 120, "bottom": 180}

# (left, top, right, bottom) boxes
TITLE_BOX = (80, 70, 1000, 200)        # event branding / tagline
PHOTO_CIRCLE = (390, 280, 690, 580)    # 300px circular photo, top-centre
NAME_BOX = (80, 610, 1000, 760)        # auto-shrink, centred
CHURCH_BOX = (80, 780, 1000, 900)      # medium, multiline wrap
ID_BOX = (80, 920, 1000, 990)          # fixed-width athlete ID
ROWS_ORIGIN = (80, 1080)               # event-info rows start here
ROW_HEIGHT = 96
QR_RECT = (640, 1420, 940, 1720)       # 300x300 placeholder QR, bottom-right
QR_CAPTION_BOX = (640, 1725, 940, 1785)  # caption sits above the footer band

# Colours (placeholder palette; real branding comes with the designer template)
COL_BG = (245, 247, 250, 255)
COL_HEADER = (18, 52, 86, 255)
COL_FOOTER = (18, 52, 86, 255)
COL_TEXT = (24, 28, 34, 255)
COL_MUTED = (96, 104, 116, 255)
COL_ACCENT = (200, 32, 48, 255)
COL_PHOTO_RING = (18, 52, 86, 255)
COL_WHITE = (255, 255, 255, 255)

# Initials-placeholder palette, chosen by name hash so the same person is stable.
_INITIALS_COLORS = [
    (211, 84, 0), (41, 128, 185), (39, 174, 96), (142, 68, 173),
    (192, 57, 43), (22, 160, 133), (243, 156, 18), (52, 73, 94),
]

# ── Font resolution ───────────────────────────────────────────────────────────
# Preferred fonts ship under middleware/fonts/ (Inter has full Vietnamese
# coverage).  When they are absent we fall back to system Liberation fonts so
# local dev still renders real glyphs, then to Pillow's default as a last
# resort so the renderer never hard-fails in CI.

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

_FONT_CANDIDATES = {
    "bold": [
        _FONTS_DIR / "Inter-Bold.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ],
    "regular": [
        _FONTS_DIR / "Inter-Regular.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ],
    "mono": [
        _FONTS_DIR / "JetBrainsMono-Regular.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ],
}


def _resolve_font_path(role: str) -> Optional[Path]:
    for candidate in _FONT_CANDIDATES.get(role, []):
        if candidate.is_file():
            return candidate
    return None


def _ascii_initials(first: str, last: str) -> str:
    """Return up to two initials, accent-stripped for the placeholder glyph only."""
    def _first_letter(name: str) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        stripped = "".join(
            c for c in unicodedata.normalize("NFD", name[0]) if not unicodedata.combining(c)
        )
        return (stripped or name[0]).upper()

    initials = _first_letter(first) + _first_letter(last)
    return initials or "?"


class BadgeGenerator:
    """Render athlete badges to PNG.  Pure rendering, no network."""

    def __init__(
        self,
        template_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        filename_salt: Optional[str] = None,
    ) -> None:
        base = Path(__file__).resolve().parent.parent
        self.template_path = Path(template_path) if template_path else base / "templates" / "badge_template.png"
        self.output_dir = Path(output_dir) if output_dir else base / "data" / "badges"
        # Deterministic, non-enumerable filename suffix.  Local-only in v1, but
        # this keeps the eventual public URL space un-guessable for free.
        self.filename_salt = filename_salt or os.getenv("BADGE_FILENAME_SALT", "vaysf-badge")
        self._font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def filename_for(self, participant: Dict[str, Any]) -> str:
        """Deterministic ``{church}_{chmid}_{8hex}.png`` filename."""
        chm_id = str(participant.get("chmeetings_id") or participant.get("id") or "unknown")
        church = (participant.get("church_code") or "NA").upper()
        digest = hmac.new(
            self.filename_salt.encode("utf-8"), chm_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:8]
        return f"{church}_{chm_id}_{digest}.png"

    def render(self, participant: Dict[str, Any], photo_bytes: Optional[bytes] = None) -> Image.Image:
        """Render a badge and return the Pillow image (RGBA, 1080x1920)."""
        canvas = self._load_template()
        draw = ImageDraw.Draw(canvas)

        # Title / branding band
        self._draw_text_autoshrink(
            draw, "VAY SPORTS FEST 2026", TITLE_BOX, role="bold",
            max_size=64, min_size=36, fill=COL_WHITE, anchor_center=True,
        )

        # Profile photo (circular) or initials fallback
        first = (participant.get("first_name") or "").strip()
        last = (participant.get("last_name") or "").strip()
        self._draw_photo(canvas, photo_bytes, PHOTO_CIRCLE, first, last)

        # Athlete name (largest dynamic text, auto-shrink for long names)
        full_name = (participant.get("full_name") or f"{first} {last}").strip() or "Unknown Athlete"
        self._draw_text_autoshrink(
            draw, full_name, NAME_BOX, role="bold",
            max_size=110, min_size=48, fill=COL_TEXT, anchor_center=True,
        )

        # Church (medium, wraps to two lines if needed)
        church = self._church_display(participant)
        self._draw_text_wrapped(
            draw, church, CHURCH_BOX, role="regular",
            size=54, fill=COL_MUTED, max_lines=2,
        )

        # Athlete ID (fixed-width)
        chm_id = str(participant.get("chmeetings_id") or participant.get("id") or "")
        self._draw_text_autoshrink(
            draw, f"ATHLETE ID  {chm_id}", ID_BOX, role="mono",
            max_size=44, min_size=24, fill=COL_ACCENT, anchor_center=True,
        )

        # Event-info rows — hide empty rows rather than render blank cards
        self._draw_event_rows(draw, self._event_rows(participant))

        # QR placeholder (ID-only payload for now; interop spike is future work)
        self._draw_qr(canvas, chm_id or "unknown", QR_RECT)
        self._draw_text_autoshrink(
            draw, "Scan at check-in", QR_CAPTION_BOX, role="regular",
            max_size=30, min_size=18, fill=COL_MUTED, anchor_center=True,
        )

        return canvas

    def render_to_file(
        self,
        participant: Dict[str, Any],
        photo_bytes: Optional[bytes] = None,
        force: bool = False,
    ) -> Path:
        """Render and write the PNG; returns the output path.

        When ``force`` is False and a current file already exists, rendering is
        skipped and the existing path returned.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / self.filename_for(participant)
        if out_path.exists() and not force:
            logger.debug(f"Badge already exists, skipping (use --force to regenerate): {out_path.name}")
            return out_path
        image = self.render(participant, photo_bytes)
        image.save(out_path, format="PNG", optimize=True)
        logger.debug(f"Rendered badge: {out_path.name}")
        return out_path

    # ── Layout helpers ──────────────────────────────────────────────────────────

    def _church_display(self, participant: Dict[str, Any]) -> str:
        name = (participant.get("church_name") or "").strip()
        code = (participant.get("church_code") or "").strip().upper()
        if name and code:
            return f"{name} ({code})"
        return name or code or "—"

    def _event_rows(self, participant: Dict[str, Any]) -> List[str]:
        """Build the non-empty event-info lines for the lower badge area."""
        rows: List[str] = []

        def _sport_line(label: str, sport_key: str, fmt_key: str, partner_key: str) -> Optional[str]:
            sport = (participant.get(sport_key) or "").strip()
            if not sport or sport.lower() in ("unselected/na", "na", "n/a", "unselected"):
                return None
            fmt = (participant.get(fmt_key) or "").strip()
            partner = (participant.get(partner_key) or "").strip()
            line = f"{label}: {sport}"
            if fmt:
                line += f" ({fmt})"
            if partner:
                line += f" w/ {partner}"
            return line

        primary = _sport_line("Primary", "primary_sport", "primary_format", "primary_partner")
        if primary:
            rows.append(primary)
        secondary = _sport_line("Secondary", "secondary_sport", "secondary_format", "secondary_partner")
        if secondary:
            rows.append(secondary)

        other = (participant.get("other_events") or "").strip()
        if other:
            rows.append(f"Other: {other}")

        return rows

    def _draw_event_rows(self, draw: ImageDraw.ImageDraw, rows: List[str]) -> None:
        x0, y = ROWS_ORIGIN
        right = CANVAS_W - SAFE_PAD["right"]
        font = self._font("regular", 46)
        for line in rows:
            # Accent bullet + label, left-aligned within the safe zone.
            draw.rounded_rectangle((x0, y + 18, x0 + 12, y + ROW_HEIGHT - 18), radius=6, fill=COL_ACCENT)
            self._draw_fitted_line(draw, line, (x0 + 36, y, right, y + ROW_HEIGHT), font, COL_TEXT)
            y += ROW_HEIGHT

    def _draw_fitted_line(self, draw, text, box, font, fill):
        """Draw a single line, shrinking the given font only if it overflows width."""
        left, top, right, bottom = box
        max_w = right - left
        size = font.size
        chosen = font
        while size > 22:
            w = draw.textlength(text, font=chosen)
            if w <= max_w:
                break
            size -= 2
            chosen = self._font_from(chosen, size)
        cy = top + (bottom - top) // 2
        draw.text((left, cy), text, font=chosen, fill=fill, anchor="lm")

    def _draw_text_autoshrink(self, draw, text, box, *, role, max_size, min_size, fill, anchor_center):
        """Binary-search the largest font size that fits the box width + height."""
        left, top, right, bottom = box
        max_w, max_h = right - left, bottom - top
        lo, hi, best = min_size, max_size, min_size
        while lo <= hi:
            mid = (lo + hi) // 2
            font = self._font(role, mid)
            bbox = draw.textbbox((0, 0), text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w <= max_w and h <= max_h:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        font = self._font(role, best)
        if anchor_center:
            draw.text(((left + right) // 2, (top + bottom) // 2), text, font=font, fill=fill, anchor="mm")
        else:
            draw.text((left, top), text, font=font, fill=fill, anchor="la")

    def _draw_text_wrapped(self, draw, text, box, *, role, size, fill, max_lines):
        """Word-wrap text to the box width, centred, up to ``max_lines`` lines."""
        left, top, right, bottom = box
        max_w = right - left
        font = self._font(role, size)
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) <= max_w or not current:
                current = trial
            else:
                lines.append(current)
                current = word
            if len(lines) == max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        if not lines:
            lines = [text]
        # Truncate the last line with an ellipsis if we ran out of room.
        if len(lines) == max_lines:
            last = lines[-1]
            while draw.textlength(last + "…", font=font) > max_w and len(last) > 1:
                last = last[:-1]
            remaining = " ".join(words)
            if draw.textlength(" ".join(lines), font=font) < draw.textlength(remaining, font=font):
                lines[-1] = last + "…"

        line_h = size + 8
        total_h = line_h * len(lines)
        y = top + max(0, (bottom - top - total_h) // 2) + line_h // 2
        cx = (left + right) // 2
        for line in lines:
            draw.text((cx, y), line, font=font, fill=fill, anchor="mm")
            y += line_h

    def _draw_photo(self, canvas, photo_bytes, rect, first, last):
        left, top, right, bottom = rect
        diameter = right - left
        # Outer ring
        ring = ImageDraw.Draw(canvas)
        ring.ellipse((left - 8, top - 8, right + 8, bottom + 8), fill=COL_PHOTO_RING)

        img = None
        if photo_bytes:
            try:
                img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
            except Exception as e:  # noqa: BLE001 - any decode failure falls back to initials
                logger.warning(f"Could not decode profile photo, using initials fallback: {e}")
                img = None

        if img is not None:
            # Centre-crop to square, resize to the circle, apply a circular mask.
            w, h = img.size
            side = min(w, h)
            img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
            img = img.resize((diameter, diameter), Image.LANCZOS).convert("RGBA")
            mask = Image.new("L", (diameter, diameter), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
            canvas.paste(img, (left, top), mask)
        else:
            # Initials-on-colour placeholder — deliberately obvious to staff.
            initials = _ascii_initials(first, last)
            color = _INITIALS_COLORS[hash(f"{first}{last}") % len(_INITIALS_COLORS)]
            circle = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
            cdraw = ImageDraw.Draw(circle)
            cdraw.ellipse((0, 0, diameter, diameter), fill=color + (255,))
            font = self._font("bold", int(diameter * 0.42))
            cdraw.text((diameter // 2, diameter // 2), initials, font=font, fill=COL_WHITE, anchor="mm")
            canvas.paste(circle, (left, top), circle)

    def _draw_qr(self, canvas, payload, rect):
        left, top, right, bottom = rect
        size = right - left
        qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(str(payload))
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        qr_img = qr_img.resize((size, size), Image.NEAREST)
        # White card behind the QR guarantees the quiet zone against the bg.
        card = Image.new("RGBA", (size + 24, size + 24), COL_WHITE)
        ImageDraw.Draw(card)  # no-op; card is solid white
        canvas.paste(card, (left - 12, top - 12), card)
        canvas.paste(qr_img, (left, top), qr_img)

    # ── Resources ────────────────────────────────────────────────────────────

    def _load_template(self) -> Image.Image:
        """Open the template once per render; generate a flat fallback if absent."""
        if self.template_path.is_file():
            return Image.open(self.template_path).convert("RGBA").resize((CANVAS_W, CANVAS_H))
        logger.warning(f"Template not found at {self.template_path}; using flat fallback background.")
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), COL_BG)
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, CANVAS_W, 220), fill=COL_HEADER)
        draw.rectangle((0, CANVAS_H - 120, CANVAS_W, CANVAS_H), fill=COL_FOOTER)
        return canvas

    def _font(self, role: str, size: int) -> ImageFont.FreeTypeFont:
        key = (role, size)
        if key in self._font_cache:
            return self._font_cache[key]
        path = _resolve_font_path(role)
        try:
            font = ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size)
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default(size)
        self._font_cache[key] = font
        return font

    def _font_from(self, existing: ImageFont.FreeTypeFont, size: int) -> ImageFont.FreeTypeFont:
        try:
            return existing.font_variant(size=size)
        except Exception:  # noqa: BLE001
            return ImageFont.load_default(size)
