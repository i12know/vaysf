# badges/generator.py
"""
BadgeGenerator — renders a single 1080x1920 athlete badge PNG with Pillow.

Layout matches the Issue #77 wireframe exactly (four sections top to bottom):

  1. TAGLINE   — white band; "VAY SPORTS FEST 2026" centred.
  2. THEME     — deep navy; "Ultimate G.O.A.L." in large bold white text
                 + VAY SM logo placeholder.
  3. IDENTITY  — white; circular athlete photo LEFT, QR code RIGHT (both ~220 px),
                 church code centred in large bold text below both.
  4. CARDS     — light blue-grey background; one white rounded-rectangle card
                 per data row (name/ID, primary sport, secondary sport, others),
                 each with a right-aligned colour-coded pill tag.

This module is pure rendering: no network calls.  The runner (``runner.py``)
is responsible for fetching WordPress participant data and the ChMeetings photo.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import qrcode
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

# ── Canvas ────────────────────────────────────────────────────────────────────

CANVAS_W, CANVAS_H = 1080, 1920

# ── Section vertical boundaries (y0, y1) — wireframe-accurate ────────────────

TAGLINE_Y0, TAGLINE_Y1 = 0, 170          # white top band
THEME_Y0,   THEME_Y1   = 170, 800        # deep navy theme block  (~630 px)
IDENTITY_Y0, IDENTITY_Y1 = 800, 1115     # white identity block   (~315 px)
CARDS_Y0                 = 1115          # light-grey cards start here
BOTTOM_SAFE_Y            = 1740          # 1920 − 180 bottom safe padding

# ── Colours ───────────────────────────────────────────────────────────────────

COL_TAGLINE_BG    = (255, 255, 255, 255)
COL_THEME_BG      = (14,  22,  50,  255)   # deep navy  #0e1632
COL_IDENTITY_BG   = (255, 255, 255, 255)
COL_CARDS_BG      = (228, 233, 241, 255)   # light blue-grey
COL_CARD_BG       = (255, 255, 255, 255)

COL_WHITE         = (255, 255, 255, 255)
COL_NAVY          = (14,  22,  50,  255)
COL_MUTED         = (100, 110, 130, 255)

# Tag pill backgrounds
COL_TAG_ID_BG     = (216, 225, 240, 255)   # light navy-tinted (for ID tag)
COL_TAG_ID_TEXT   = (14,  22,  50,  255)   # dark text on light tag
COL_TAG_PRI_BG    = (210,  35,  50,  255)  # red   — Primary
COL_TAG_SEC_BG    = ( 40, 100, 195, 255)   # blue  — Secondary
COL_TAG_OTH_BG    = (210, 118,  14,  255)  # amber — Others
COL_TAG_TEXT      = (255, 255, 255, 255)   # white text on coloured tags

COL_PHOTO_RING    = (14,  22,  50,  255)   # navy ring around photo

# ── Event theme text (2026 season) ───────────────────────────────────────────

THEME_LINE1 = "Ultimate"
THEME_LINE2 = "G.O.A.L."
THEME_LOGO_LABEL = "VAY SM"

# ── Safe padding ─────────────────────────────────────────────────────────────

SAFE_LEFT  = 80
SAFE_RIGHT = 80

# ── Identity block element positions ─────────────────────────────────────────

PHOTO_DIAM  = 228
PHOTO_LEFT  = SAFE_LEFT                            # x: 80
PHOTO_TOP   = IDENTITY_Y0 + 28                     # y: 828

QR_SIZE     = 200
QR_LEFT     = CANVAS_W - SAFE_RIGHT - QR_SIZE      # x: 800
QR_TOP      = IDENTITY_Y0 + 48                     # y: 848

# Church-code text is centred horizontally, below the photo/QR pair
CHURCH_CODE_CX = CANVAS_W // 2                     # x: 540
CHURCH_CODE_CY = IDENTITY_Y1 - 42                  # y: 1073

# ── Event cards ──────────────────────────────────────────────────────────────

CARD_X0      = SAFE_LEFT  - 10   # 70   — slight bleed past safe edge
CARD_X1      = CANVAS_W - SAFE_RIGHT + 10   # 1010
CARD_FIRST_Y = CARDS_Y0 + 18     # 1133
CARD_H       = 102
CARD_GAP     = 10
CARD_RADIUS  = 14
CARD_PAD     = 26   # inner horizontal padding

TAG_RADIUS   = 22   # pill corner radius
TAG_H_PAD    = 16   # horizontal padding inside pill
TAG_V_PAD    = 9    # vertical padding inside pill
TAG_MIN_W    = 90   # minimum pill width

# ── QR caption ───────────────────────────────────────────────────────────────

QR_CAPTION = "ID QR - not for check-in"

# ── Render-fingerprint metadata ───────────────────────────────────────────────
# Bump _RENDER_VERSION whenever the visual layout changes so existing sidecar
# fingerprints automatically invalidate and badges are re-rendered.

_RENDER_VERSION = "issue-77-v1.2"
_RENDER_FIELDS = (
    "chmeetings_id", "church_code", "church_name",
    "first_name", "last_name", "full_name",
    "primary_sport", "primary_format", "primary_partner",
    "secondary_sport", "secondary_format", "secondary_partner",
    "other_events",
)

# ── Initials colour palette (deterministic per name) ─────────────────────────

_INITIALS_COLORS = [
    (211, 84, 0), (41, 128, 185), (39, 174, 96), (142, 68, 173),
    (192, 57, 43), (22, 160, 133), (243, 156, 18), (52, 73, 94),
]

# ── Font resolution ───────────────────────────────────────────────────────────
# Windows (production): Arial / Consolas   — full Vietnamese coverage.
# Linux (CI/dev): Liberation / DejaVu      — full Vietnamese coverage.
# Optional branding: Inter / JetBrains Mono in middleware/fonts/.
# We do NOT fall back to Pillow's bitmap default because it silently drops
# Vietnamese diacritics.

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

_FONT_CANDIDATES: Dict[str, List[Path]] = {
    "bold": [
        _FONTS_DIR / "Inter-Bold.ttf",
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ],
    "regular": [
        _FONTS_DIR / "Inter-Regular.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ],
    "mono": [
        _FONTS_DIR / "JetBrainsMono-Regular.ttf",
        Path("C:/Windows/Fonts/consola.ttf"),
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
            c for c in unicodedata.normalize("NFD", name[0])
            if not unicodedata.combining(c)
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
        self.template_path = (
            Path(template_path) if template_path
            else base / "templates" / "badge_template.png"
        )
        self.output_dir = (
            Path(output_dir) if output_dir
            else base / "data" / "badges"
        )
        salt = filename_salt if filename_salt is not None else os.getenv("BADGE_FILENAME_SALT")
        if not salt or len(salt.strip()) < 16:
            raise ValueError(
                "BADGE_FILENAME_SALT must be set to a private value of at least 16 characters."
            )
        self.filename_salt = salt.strip()
        self._font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._resource_fingerprint_cache: Optional[bytes] = None
        self.last_write_skipped = False

    # ── Public API ────────────────────────────────────────────────────────────

    def filename_for(self, participant: Dict[str, Any]) -> str:
        """Return deterministic ``{church}_{chmid}_{8hex}.png`` filename."""
        chm_id = self._required_chm_id(participant)
        church = (participant.get("church_code") or "NA").upper()
        digest = hmac.new(
            self.filename_salt.encode("utf-8"),
            chm_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:8]
        return f"{church}_{chm_id}_{digest}.png"

    def render(
        self, participant: Dict[str, Any], photo_bytes: Optional[bytes] = None
    ) -> Image.Image:
        """Render a badge image and return it as an RGBA PIL Image (1080×1920)."""
        canvas = self._load_template()
        draw   = ImageDraw.Draw(canvas)

        self._draw_tagline(draw)
        self._draw_theme(draw)
        self._draw_identity(canvas, draw, participant, photo_bytes)
        self._draw_cards(draw, participant)

        return canvas

    def render_to_file(
        self,
        participant: Dict[str, Any],
        photo_bytes: Optional[bytes] = None,
        force: bool = False,
    ) -> Path:
        """Render and save the PNG; return the output path.

        Skips rendering when the content fingerprint matches the on-disk sidecar
        (``{name}.png.sha256``), unless ``force`` is True.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path        = self.output_dir / self.filename_for(participant)
        fingerprint_path = out_path.with_suffix(".png.sha256")
        fingerprint      = self._render_fingerprint(participant, photo_bytes)
        self.last_write_skipped = False

        if (
            out_path.exists()
            and fingerprint_path.exists()
            and not force
            and fingerprint_path.read_text(encoding="ascii").strip() == fingerprint
        ):
            self.last_write_skipped = True
            logger.debug(f"Badge content is current, skipping: {out_path.name}")
            return out_path

        image = self.render(participant, photo_bytes)
        image.save(out_path, format="PNG", optimize=True)
        fingerprint_path.write_text(f"{fingerprint}\n", encoding="ascii")
        logger.debug(f"Rendered badge: {out_path.name}")
        return out_path

    # ── Section renderers ─────────────────────────────────────────────────────

    def _draw_tagline(self, draw: ImageDraw.ImageDraw) -> None:
        """Section 1: white band with event name."""
        cx = CANVAS_W // 2
        cy = (TAGLINE_Y0 + TAGLINE_Y1) // 2
        self._draw_text_autoshrink(
            draw, "VAY SPORTS FEST 2026",
            box=(SAFE_LEFT, TAGLINE_Y0 + 10, CANVAS_W - SAFE_RIGHT, TAGLINE_Y1 - 10),
            role="bold", max_size=56, min_size=32,
            fill=COL_NAVY, anchor_center=True,
        )

    def _draw_theme(self, draw: ImageDraw.ImageDraw) -> None:
        """Section 2: deep navy background with large theme title + logo placeholder."""
        # The template already paints this background; just overlay text.
        cx = CANVAS_W // 2

        # "Ultimate" — line 1
        line1_cy = THEME_Y0 + 215
        self._draw_text_autoshrink(
            draw, THEME_LINE1,
            box=(SAFE_LEFT, THEME_Y0 + 80, CANVAS_W - SAFE_RIGHT, THEME_Y0 + 350),
            role="bold", max_size=168, min_size=80,
            fill=COL_WHITE, anchor_center=True,
        )

        # "G.O.A.L." — line 2
        self._draw_text_autoshrink(
            draw, THEME_LINE2,
            box=(SAFE_LEFT, THEME_Y0 + 330, CANVAS_W - SAFE_RIGHT, THEME_Y0 + 580),
            role="bold", max_size=168, min_size=80,
            fill=COL_WHITE, anchor_center=True,
        )

        # VAY SM logo placeholder — small outlined box + label
        logo_w, logo_h = 160, 90
        logo_x = (CANVAS_W - logo_w) // 2
        logo_y = THEME_Y0 + 600
        draw.rounded_rectangle(
            (logo_x, logo_y, logo_x + logo_w, logo_y + logo_h),
            radius=8, outline=(100, 120, 160, 255), width=2,
        )
        draw.text(
            (logo_x + logo_w // 2, logo_y + logo_h // 2),
            THEME_LOGO_LABEL,
            font=self._font("bold", 32),
            fill=(140, 165, 200, 255),
            anchor="mm",
        )

    def _draw_identity(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        participant: Dict[str, Any],
        photo_bytes: Optional[bytes],
    ) -> None:
        """Section 3: photo LEFT, QR code RIGHT, church code centred below."""
        first = (participant.get("first_name") or "").strip()
        last  = (participant.get("last_name")  or "").strip()

        # Profile photo / initials fallback
        self._draw_photo(
            canvas,
            photo_bytes,
            rect=(PHOTO_LEFT, PHOTO_TOP, PHOTO_LEFT + PHOTO_DIAM, PHOTO_TOP + PHOTO_DIAM),
            first=first, last=last,
        )

        # QR code (ID-only placeholder payload)
        chm_id = self._required_chm_id(participant)
        self._draw_qr_block(canvas, draw, chm_id)

        # Church code in large bold text, centred
        church_code = (participant.get("church_code") or "?").strip().upper()
        draw.text(
            (CHURCH_CODE_CX, CHURCH_CODE_CY),
            church_code,
            font=self._font("bold", 88),
            fill=COL_NAVY,
            anchor="mm",
        )

    def _draw_cards(self, draw: ImageDraw.ImageDraw, participant: Dict[str, Any]) -> None:
        """Section 4: white rounded cards on a light-grey background."""
        rows = self._card_rows(participant)
        y = CARD_FIRST_Y
        for text, tag_label, tag_col_bg, tag_col_text, multiline in rows:
            if y + CARD_H > BOTTOM_SAFE_Y and not multiline:
                break
            card_h = self._card_height(draw, text, multiline)
            if y + card_h > BOTTOM_SAFE_Y:
                break
            self._draw_card(draw, text, tag_label, tag_col_bg, tag_col_text, y, card_h)
            y += card_h + CARD_GAP

    # ── Card data helpers ─────────────────────────────────────────────────────

    def _card_rows(
        self, participant: Dict[str, Any]
    ) -> List[Tuple[str, str, tuple, tuple, bool]]:
        """Return (text, tag_label, tag_bg_col, tag_text_col, multiline) tuples."""
        rows = []

        # Row 1: Athlete name | ID badge code
        first = (participant.get("first_name") or "").strip()
        last  = (participant.get("last_name")  or "").strip()
        name  = (participant.get("full_name") or f"{first} {last}").strip() or "Unknown Athlete"
        chm_id = self._required_chm_id(participant)
        rows.append((name, f"#{chm_id}", COL_TAG_ID_BG, COL_TAG_ID_TEXT, False))

        # Row 2: Primary sport
        primary = self._sport_line(
            participant, "primary_sport", "primary_format", "primary_partner"
        )
        if primary:
            rows.append((primary, "Primary", COL_TAG_PRI_BG, COL_TAG_TEXT, False))

        # Row 3: Secondary sport
        secondary = self._sport_line(
            participant, "secondary_sport", "secondary_format", "secondary_partner"
        )
        if secondary:
            rows.append((secondary, "2ndary", COL_TAG_SEC_BG, COL_TAG_TEXT, False))

        # Row 4: Other events (may be a comma-separated list — multiline)
        other_raw = (participant.get("other_events") or "").strip()
        if other_raw:
            other_events = ", ".join(
                s.strip() for s in other_raw.split(",") if s.strip()
            )
            rows.append((other_events, "Others", COL_TAG_OTH_BG, COL_TAG_TEXT, True))

        return rows

    @staticmethod
    def _sport_line(
        participant: Dict[str, Any],
        sport_key: str,
        fmt_key: str,
        partner_key: str,
    ) -> str:
        sport = (participant.get(sport_key) or "").strip()
        if not sport or sport.lower() in ("unselected/na", "na", "n/a", "unselected"):
            return ""
        fmt     = (participant.get(fmt_key)     or "").strip()
        partner = (participant.get(partner_key) or "").strip()
        line = sport
        if fmt:
            line += f" ({fmt})"
        if partner:
            line += f" w/ {partner}"
        return line

    def _card_height(self, draw: ImageDraw.ImageDraw, text: str, multiline: bool) -> int:
        if not multiline:
            return CARD_H
        # Measure text wrapped at card width and expand height accordingly.
        font = self._font("regular", 40)
        max_w = (CARD_X1 - CARD_X0) - CARD_PAD * 2 - TAG_MIN_W - TAG_H_PAD * 2 - 32
        lines = self._wrap_lines(draw, text, font, max_w)
        line_h = 50
        return max(CARD_H, TAG_V_PAD * 2 + line_h * len(lines) + CARD_PAD)

    # ── Drawing primitives ────────────────────────────────────────────────────

    def _draw_card(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        tag_label: str,
        tag_bg: tuple,
        tag_fg: tuple,
        y: int,
        card_h: int,
    ) -> None:
        x0, x1 = CARD_X0, CARD_X1

        # Card background
        draw.rounded_rectangle((x0, y, x1, y + card_h), radius=CARD_RADIUS, fill=COL_CARD_BG)

        # Pill tag — sized to its label, right-aligned inside the card
        tag_font  = self._font("bold", 34)
        tag_text_w = int(draw.textlength(tag_label, font=tag_font))
        pill_w    = max(TAG_MIN_W, tag_text_w + TAG_H_PAD * 2)
        pill_h    = 46
        pill_x1   = x1 - CARD_PAD
        pill_x0   = pill_x1 - pill_w
        pill_cy   = y + card_h // 2
        pill_y0   = pill_cy - pill_h // 2
        pill_y1   = pill_y0 + pill_h
        draw.rounded_rectangle((pill_x0, pill_y0, pill_x1, pill_y1), radius=TAG_RADIUS, fill=tag_bg)
        draw.text(
            ((pill_x0 + pill_x1) // 2, (pill_y0 + pill_y1) // 2),
            tag_label, font=tag_font, fill=tag_fg, anchor="mm",
        )

        # Card text (left of pill)
        text_x    = x0 + CARD_PAD
        text_right = pill_x0 - 16
        text_max_w = text_right - text_x
        text_font  = self._font("bold", 42)
        text_cy    = y + card_h // 2

        # Try single line first; wrap only for multiline cards
        if int(draw.textlength(text, font=text_font)) <= text_max_w:
            draw.text((text_x, text_cy), text, font=text_font, fill=COL_NAVY, anchor="lm")
        else:
            # Try auto-shrunk single line; fall back to wrapped multiline
            shrunk_font = self._fit_text_to_width(draw, text, text_font, text_max_w, min_size=28)
            if int(draw.textlength(text, font=shrunk_font)) <= text_max_w:
                draw.text((text_x, text_cy), text, font=shrunk_font, fill=COL_NAVY, anchor="lm")
            else:
                wrap_font = self._font("regular", 40)
                lines = self._wrap_lines(draw, text, wrap_font, text_max_w)
                line_h = 50
                total_h = line_h * len(lines)
                ty = y + (card_h - total_h) // 2 + line_h // 2
                for line in lines:
                    draw.text((text_x, ty), line, font=wrap_font, fill=COL_NAVY, anchor="lm")
                    ty += line_h

    def _draw_text_autoshrink(
        self, draw, text, box, *, role, max_size, min_size, fill, anchor_center
    ) -> None:
        """Binary-search the largest font that fits inside ``box``."""
        left, top, right, bottom = box
        max_w, max_h = right - left, bottom - top
        lo, hi, best = min_size, max_size, min_size
        while lo <= hi:
            mid  = (lo + hi) // 2
            font = self._font(role, mid)
            bbox = draw.textbbox((0, 0), text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w <= max_w and h <= max_h:
                best = mid
                lo   = mid + 1
            else:
                hi   = mid - 1
        font = self._font(role, best)
        if anchor_center:
            draw.text(
                ((left + right) // 2, (top + bottom) // 2),
                text, font=font, fill=fill, anchor="mm",
            )
        else:
            draw.text((left, top), text, font=font, fill=fill, anchor="la")

    def _fit_text_to_width(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        base_font: ImageFont.FreeTypeFont,
        max_w: int,
        min_size: int = 22,
    ) -> ImageFont.FreeTypeFont:
        font = base_font
        size = font.size
        while size > min_size and int(draw.textlength(text, font=font)) > max_w:
            size -= 2
            font = self._font_from(font, size)
        return font

    @staticmethod
    def _wrap_lines(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_w: int,
    ) -> List[str]:
        words   = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if int(draw.textlength(trial, font=font)) <= max_w or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [text]

    def _draw_photo(
        self,
        canvas: Image.Image,
        photo_bytes: Optional[bytes],
        rect: Tuple[int, int, int, int],
        first: str,
        last: str,
    ) -> None:
        left, top, right, bottom = rect
        diameter = right - left
        ring = ImageDraw.Draw(canvas)
        ring.ellipse(
            (left - 6, top - 6, right + 6, bottom + 6),
            fill=COL_PHOTO_RING,
        )

        img = None
        if photo_bytes:
            try:
                img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
            except Exception as e:
                logger.warning(f"Could not decode profile photo, using initials fallback: {e}")

        if img is not None:
            w, h   = img.size
            side   = min(w, h)
            img    = img.crop(
                ((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2)
            )
            img    = img.resize((diameter, diameter), Image.LANCZOS).convert("RGBA")
            mask   = Image.new("L", (diameter, diameter), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
            canvas.paste(img, (left, top), mask)
        else:
            initials  = _ascii_initials(first, last)
            name_dig  = hashlib.sha256(f"{first}\0{last}".encode("utf-8")).digest()
            color     = _INITIALS_COLORS[name_dig[0] % len(_INITIALS_COLORS)]
            circle    = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
            cdraw     = ImageDraw.Draw(circle)
            cdraw.ellipse((0, 0, diameter, diameter), fill=color + (255,))
            font      = self._font("bold", int(diameter * 0.40))
            cdraw.text(
                (diameter // 2, diameter // 2),
                initials, font=font, fill=COL_WHITE, anchor="mm",
            )
            canvas.paste(circle, (left, top), circle)

    def _draw_qr_block(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        payload: str,
    ) -> None:
        """Render the QR code with its white card and caption."""
        qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(str(payload))
        qr.make(fit=True)
        qr_img = (
            qr.make_image(fill_color="black", back_color="white")
            .convert("RGBA")
        )
        qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.NEAREST)

        # White card behind QR (quiet-zone guarantee + caption area)
        cap_font   = self._font("regular", 24)
        cap_h      = 36
        card_pad   = 10
        card_x0    = QR_LEFT  - card_pad
        card_y0    = QR_TOP   - card_pad
        card_x1    = QR_LEFT  + QR_SIZE + card_pad
        card_y1    = QR_TOP   + QR_SIZE + cap_h + card_pad * 2
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x1, card_y1),
            radius=10, fill=COL_CARD_BG,
        )
        canvas.paste(qr_img, (QR_LEFT, QR_TOP), qr_img)
        draw.text(
            ((card_x0 + card_x1) // 2, QR_TOP + QR_SIZE + card_pad + cap_h // 2),
            QR_CAPTION, font=cap_font, fill=COL_MUTED, anchor="mm",
        )

    # ── Resources ────────────────────────────────────────────────────────────

    def _load_template(self) -> Image.Image:
        """Load the background template; generate a section-aware fallback if absent."""
        if self.template_path.is_file():
            return Image.open(self.template_path).convert("RGBA").resize((CANVAS_W, CANVAS_H))
        logger.warning(
            f"Template not found at {self.template_path}; using flat section fallback."
        )
        return self._make_section_background()

    def _make_section_background(self) -> Image.Image:
        """Flat four-section background matching the wireframe colour scheme."""
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), COL_TAGLINE_BG)
        draw   = ImageDraw.Draw(canvas)
        draw.rectangle((0, THEME_Y0,    CANVAS_W, THEME_Y1),    fill=COL_THEME_BG)
        draw.rectangle((0, IDENTITY_Y0, CANVAS_W, IDENTITY_Y1), fill=COL_IDENTITY_BG)
        draw.rectangle((0, CARDS_Y0,    CANVAS_W, CANVAS_H),    fill=COL_CARDS_BG)
        return canvas

    def _font(self, role: str, size: int) -> ImageFont.FreeTypeFont:
        key = (role, size)
        if key in self._font_cache:
            return self._font_cache[key]
        path = _resolve_font_path(role)
        if path is None:
            raise RuntimeError(
                f"No scalable {role} font found. See middleware/fonts/README.md."
            )
        try:
            font = ImageFont.truetype(str(path), size)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load {role} font at {path}: {exc}"
            ) from exc
        self._font_cache[key] = font
        return font

    def _font_from(
        self, existing: ImageFont.FreeTypeFont, size: int
    ) -> ImageFont.FreeTypeFont:
        try:
            return existing.font_variant(size=size)
        except Exception as exc:
            raise RuntimeError(
                f"Could not resize badge font to {size}px: {exc}"
            ) from exc

    # ── Fingerprinting ────────────────────────────────────────────────────────

    @staticmethod
    def _required_chm_id(participant: Dict[str, Any]) -> str:
        chm_id = str(participant.get("chmeetings_id") or "").strip()
        if not chm_id:
            raise ValueError("Cannot render a badge without chmeetings_id.")
        return chm_id

    def _render_fingerprint(
        self,
        participant: Dict[str, Any],
        photo_bytes: Optional[bytes],
    ) -> str:
        render_data = {key: participant.get(key) for key in _RENDER_FIELDS}
        digest = hashlib.sha256()
        digest.update(_RENDER_VERSION.encode("ascii"))
        digest.update(
            json.dumps(
                render_data,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        )
        digest.update(photo_bytes or b"<no-photo>")
        digest.update(self._resource_fingerprint())
        return digest.hexdigest()

    def _resource_fingerprint(self) -> bytes:
        if self._resource_fingerprint_cache is not None:
            return self._resource_fingerprint_cache
        digest = hashlib.sha256()
        if self.template_path.is_file():
            digest.update(self.template_path.read_bytes())
        else:
            digest.update(b"<fallback-template>")
        for role in ("bold", "regular", "mono"):
            path = _resolve_font_path(role)
            if path is None:
                raise RuntimeError(
                    f"No scalable {role} font found. See middleware/fonts/README.md."
                )
            digest.update(role.encode("ascii"))
            digest.update(path.read_bytes())
        self._resource_fingerprint_cache = digest.digest()
        return self._resource_fingerprint_cache
