# badges/generator.py
"""Render Issue #77 athlete badges from canonical participant data.

The v1 layout follows the posted 1080x1920 wireframe:

1. The template owns the upper event artwork and title.
2. A photo on the left, QR card on the right, and church code under the photo.
3. Dark-mode event rows with content on the left and plain labels after a
   divider.

This module performs no network calls. BadgeRunner fetches participant data and
photo bytes before invoking BadgeGenerator.
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

CANVAS_W, CANVAS_H = 1080, 1920

# Critical content stays inside the issue's 80/80/120/180 safe area.
SAFE_LEFT, SAFE_RIGHT = 80, 1000
SAFE_TOP, SAFE_BOTTOM = 120, 1740

# Template-owned artwork boxes and generated element positions.
TAGLINE_BOX = (140, 150, 940, 235)
THEME_BOX = (120, 260, 960, 720)

PHOTO_DIAM = 300
PHOTO_LEFT = 155
PHOTO_TOP = 750

QR_CARD = (650, 750, 940, 1080)
QR_SIZE = 220
QR_LEFT = 685
QR_TOP = 775

CHURCH_CODE_CX = PHOTO_LEFT + PHOTO_DIAM // 2
CHURCH_CODE_CY = 1105

CARD_X0, CARD_X1 = 120, 960
CARD_FIRST_Y = 1170
CARD_H = 105
CARD_OTHER_H = 180
CARD_GAP = 12
CARD_RADIUS = 12
CARD_PAD = 26
CARD_DIVIDER_X = 750
LABEL_CX = (CARD_DIVIDER_X + CARD_X1) // 2

COL_WHITE = (255, 255, 255, 255)
COL_CARD = (6, 31, 67, 255)
COL_CONSENT_ALERT = (170, 31, 45, 255)
COL_NAVY = (246, 249, 255, 255)
COL_BORDER = (247, 197, 101, 255)
COL_DIVIDER = (143, 174, 210, 255)
COL_LABEL = (247, 197, 101, 255)
COL_PHOTO_RING = COL_BORDER

THEME_LINE1 = "Ultimate"
THEME_LINE2 = "G.O.A.L."
THEME_LOGO_LABEL = "VAY SM logo"

_RENDER_VERSION = "issue-199-consent-v1.7"
_RENDER_FIELDS = (
    "chmeetings_id",
    "church_code",
    "church_name",
    "first_name",
    "last_name",
    "full_name",
    "primary_sport",
    "primary_format",
    "primary_partner",
    "secondary_sport",
    "secondary_format",
    "secondary_partner",
    "other_events",
    "consent_status",
)

_INITIALS_COLORS = [
    (211, 84, 0),
    (41, 128, 185),
    (39, 174, 96),
    (142, 68, 173),
    (192, 57, 43),
    (22, 160, 133),
    (243, 156, 18),
    (52, 73, 94),
]

_RACQUET_SPORT_MARKERS = (
    "badminton",
    "pickleball",
    "tennis",
    "table tennis",
)

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
    """Return up to two accent-stripped initials for the photo placeholder."""

    def first_letter(name: str) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        stripped = "".join(
            char
            for char in unicodedata.normalize("NFD", name[0])
            if not unicodedata.combining(char)
        )
        return (stripped or name[0]).upper()

    return first_letter(first) + first_letter(last) or "?"


class BadgeGenerator:
    """Render athlete badges to PNG."""

    def __init__(
        self,
        template_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        filename_salt: Optional[str] = None,
        church_subdirs: bool = False,
    ) -> None:
        base = Path(__file__).resolve().parent.parent
        self.template_path = (
            Path(template_path)
            if template_path
            else base / "templates" / "badge_template.png"
        )
        self.output_dir = (
            Path(output_dir) if output_dir else base / "data" / "badges"
        )
        self.church_subdirs = church_subdirs
        salt = (
            filename_salt
            if filename_salt is not None
            else os.getenv("BADGE_FILENAME_SALT")
        )
        if not salt or len(salt.strip()) < 16:
            raise ValueError(
                "BADGE_FILENAME_SALT must be set to a private value "
                "of at least 16 characters."
            )
        self.filename_salt = salt.strip()
        self._font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._resource_fingerprint_cache: Optional[bytes] = None
        self.last_write_skipped = False

    def filename_for(self, participant: Dict[str, Any]) -> str:
        """Return deterministic ``{church}_{chmid}_{8hex}.png`` filename."""
        chm_id = self._required_chm_id(participant)
        church = str(participant.get("church_code") or "NA").strip().upper()
        digest = hmac.new(
            self.filename_salt.encode("utf-8"),
            chm_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:8]
        return f"{church}_{chm_id}_{digest}.png"

    def output_path_for(self, participant: Dict[str, Any]) -> Path:
        """Return the concrete badge PNG path for a participant."""
        filename = self.filename_for(participant)
        if not self.church_subdirs:
            return self.output_dir / filename

        church = str(participant.get("church_code") or "NA").strip().upper()
        return self.output_dir / church / "badges" / filename

    def render(
        self,
        participant: Dict[str, Any],
        photo_bytes: Optional[bytes] = None,
    ) -> Image.Image:
        """Render a 1080x1920 RGBA badge."""
        canvas = self._load_template()
        draw = ImageDraw.Draw(canvas)
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
        """Render the PNG unless its content fingerprint is current."""
        out_path = self.output_path_for(participant)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fingerprint_path = out_path.with_suffix(".png.sha256")
        fingerprint = self._render_fingerprint(participant, photo_bytes)
        self.last_write_skipped = False

        if (
            out_path.exists()
            and fingerprint_path.exists()
            and not force
            and fingerprint_path.read_text(encoding="ascii").strip()
            == fingerprint
        ):
            self.last_write_skipped = True
            logger.debug(f"Badge content is current, skipping: {out_path.name}")
            return out_path

        image = self.render(participant, photo_bytes)
        image.save(out_path, format="PNG", optimize=True)
        fingerprint_path.write_text(f"{fingerprint}\n", encoding="ascii")
        logger.debug(f"Rendered badge: {out_path.name}")
        return out_path

    def _draw_tagline(self, draw: ImageDraw.ImageDraw) -> None:
        # The production template owns the upper title/branding area.
        return None

    def _draw_theme(self, draw: ImageDraw.ImageDraw) -> None:
        # The production template owns the upper theme artwork/logo area.
        return None

    def _draw_identity(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        participant: Dict[str, Any],
        photo_bytes: Optional[bytes],
    ) -> None:
        first = str(participant.get("first_name") or "").strip()
        last = str(participant.get("last_name") or "").strip()
        self._draw_photo(
            canvas,
            photo_bytes,
            (
                PHOTO_LEFT,
                PHOTO_TOP,
                PHOTO_LEFT + PHOTO_DIAM,
                PHOTO_TOP + PHOTO_DIAM,
            ),
            first,
            last,
        )
        self._draw_qr_block(canvas, draw, self._required_chm_id(participant))

        church_code = str(
            participant.get("church_code") or "?"
        ).strip().upper()
        draw.text(
            (CHURCH_CODE_CX, CHURCH_CODE_CY),
            church_code,
            font=self._font("bold", 76),
            fill=COL_LABEL,
            anchor="mm",
        )

    def _draw_cards(
        self,
        draw: ImageDraw.ImageDraw,
        participant: Dict[str, Any],
    ) -> None:
        y = CARD_FIRST_Y
        consent_missing = not self._has_consent(participant)
        for index, (text, label, multiline) in enumerate(self._card_rows(participant)):
            height = CARD_OTHER_H if multiline else CARD_H
            if y + height > SAFE_BOTTOM:
                logger.warning(
                    f"Badge event row omitted because it exceeds safe area: {label}"
                )
                break
            self._draw_card(
                draw,
                text,
                label,
                y,
                height,
                multiline,
                alert=index == 0 and consent_missing,
            )
            y += height + CARD_GAP

    def _card_rows(
        self,
        participant: Dict[str, Any],
    ) -> List[Tuple[str, str, bool]]:
        first = str(participant.get("first_name") or "").strip()
        last = str(participant.get("last_name") or "").strip()
        name = str(
            participant.get("full_name") or f"{first} {last}"
        ).strip() or "Unknown Athlete"
        rows: List[Tuple[str, str, bool]] = [
            (name, f"#{self._required_chm_id(participant)}", False)
        ]

        primary = self._sport_line(
            participant,
            "primary_sport",
            "primary_format",
            "primary_partner",
        )
        if primary:
            rows.append((primary, "Primary", False))

        secondary = self._sport_line(
            participant,
            "secondary_sport",
            "secondary_format",
            "secondary_partner",
        )
        if secondary:
            rows.append((secondary, "2ndary", False))

        other_raw = str(participant.get("other_events") or "").strip()
        if other_raw:
            other = ", ".join(
                value.strip()
                for value in other_raw.split(",")
                if value.strip()
            )
            rows.append((other, "Others", True))
        return rows

    @staticmethod
    def _sport_line(
        participant: Dict[str, Any],
        sport_key: str,
        format_key: str,
        partner_key: str,
    ) -> str:
        sport = str(participant.get(sport_key) or "").strip()
        if not sport or sport.lower() in {
            "unselected/na",
            "na",
            "n/a",
            "unselected",
        }:
            return ""
        sport_format = str(participant.get(format_key) or "").strip()
        partner = str(participant.get(partner_key) or "").strip()
        line = sport
        if sport_format:
            line += f" ({sport_format})"
        if partner and BadgeGenerator._is_racquet_sport(sport):
            line += f" w/ {partner}"
        return line

    @staticmethod
    def _is_racquet_sport(sport: str) -> bool:
        normalized = sport.casefold()
        return any(marker in normalized for marker in _RACQUET_SPORT_MARKERS)

    @staticmethod
    def _has_consent(participant: Dict[str, Any]) -> bool:
        value = participant.get("consent_status")
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().casefold() in {"1", "true", "yes", "y", "checked"}

    def _draw_card(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        label: str,
        y: int,
        height: int,
        multiline: bool,
        alert: bool = False,
    ) -> None:
        draw.rounded_rectangle(
            (CARD_X0, y, CARD_X1, y + height),
            radius=CARD_RADIUS,
            fill=COL_CONSENT_ALERT if alert else COL_CARD,
            outline=COL_BORDER,
            width=2,
        )
        draw.line(
            (CARD_DIVIDER_X, y + 16, CARD_DIVIDER_X, y + height - 16),
            fill=COL_DIVIDER,
            width=2,
        )
        draw.text(
            (LABEL_CX, y + height // 2),
            label,
            font=self._font("regular", 34),
            fill=COL_LABEL,
            anchor="mm",
        )

        text_box = (
            CARD_X0 + CARD_PAD,
            y + 10,
            CARD_DIVIDER_X - CARD_PAD,
            y + height - 10,
        )
        if multiline:
            self._draw_wrapped_text(draw, text, text_box)
        else:
            self._draw_text_autoshrink(
                draw,
                text,
                box=text_box,
                role="bold",
                max_size=38,
                min_size=24,
                fill=COL_NAVY,
                center=False,
            )

    def _draw_wrapped_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        box: Tuple[int, int, int, int],
    ) -> None:
        left, top, right, bottom = box
        font = self._font("bold", 34)
        lines = self._wrap_lines(draw, text, font, right - left)
        while len(lines) > 3 and font.size > 24:
            font = self._font_from(font, font.size - 2)
            lines = self._wrap_lines(draw, text, font, right - left)
        lines = lines[:3]
        line_height = font.size + 10
        total_height = len(lines) * line_height
        y = top + max(0, (bottom - top - total_height) // 2) + line_height // 2
        for line in lines:
            draw.text(
                (left, y),
                line,
                font=font,
                fill=COL_NAVY,
                anchor="lm",
            )
            y += line_height

    def _draw_text_autoshrink(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        box: Tuple[int, int, int, int],
        *,
        role: str,
        max_size: int,
        min_size: int,
        fill: Tuple[int, int, int, int],
        center: bool = True,
    ) -> None:
        left, top, right, bottom = box
        max_width, max_height = right - left, bottom - top
        low, high, best = min_size, max_size, min_size
        while low <= high:
            size = (low + high) // 2
            font = self._font(role, size)
            bbox = draw.textbbox((0, 0), text, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            if width <= max_width and height <= max_height:
                best = size
                low = size + 1
            else:
                high = size - 1
        font = self._font(role, best)
        if center:
            draw.text(
                ((left + right) // 2, (top + bottom) // 2),
                text,
                font=font,
                fill=fill,
                anchor="mm",
            )
        else:
            draw.text(
                (left, (top + bottom) // 2),
                text,
                font=font,
                fill=fill,
                anchor="lm",
            )

    @staticmethod
    def _wrap_lines(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> List[str]:
        lines: List[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if not current or draw.textlength(trial, font=font) <= max_width:
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
        ImageDraw.Draw(canvas).ellipse(
            (left - 5, top - 5, right + 5, bottom + 5),
            fill=COL_PHOTO_RING,
        )

        image = None
        if photo_bytes:
            try:
                image = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"Could not decode profile photo, using initials: "
                    f"{type(exc).__name__}"
                )

        if image is not None:
            width, height = image.size
            side = min(width, height)
            image = image.crop(
                (
                    (width - side) // 2,
                    (height - side) // 2,
                    (width + side) // 2,
                    (height + side) // 2,
                )
            )
            image = image.resize(
                (diameter, diameter),
                Image.LANCZOS,
            ).convert("RGBA")
            mask = Image.new("L", (diameter, diameter), 0)
            ImageDraw.Draw(mask).ellipse(
                (0, 0, diameter - 1, diameter - 1),
                fill=255,
            )
            canvas.paste(image, (left, top), mask)
            return

        initials = _ascii_initials(first, last)
        digest = hashlib.sha256(f"{first}\0{last}".encode("utf-8")).digest()
        color = _INITIALS_COLORS[digest[0] % len(_INITIALS_COLORS)]
        circle = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
        circle_draw = ImageDraw.Draw(circle)
        circle_draw.ellipse(
            (0, 0, diameter - 1, diameter - 1),
            fill=color + (255,),
        )
        circle_draw.text(
            (diameter // 2, diameter // 2),
            initials,
            font=self._font("bold", int(diameter * 0.38)),
            fill=COL_WHITE,
            anchor="mm",
        )
        canvas.paste(circle, (left, top), circle)

    def _draw_qr_block(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        payload: str,
    ) -> None:
        draw.rounded_rectangle(
            QR_CARD,
            radius=12,
            fill=COL_WHITE,
            outline=COL_BORDER,
            width=2,
        )
        qr = qrcode.QRCode(
            border=4,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
        )
        qr.add_data(str(payload))
        qr.make(fit=True)
        qr_image = qr.make_image(
            fill_color="black",
            back_color="white",
        ).convert("RGBA")
        qr_image = qr_image.resize((QR_SIZE, QR_SIZE), Image.NEAREST)
        canvas.paste(qr_image, (QR_LEFT, QR_TOP), qr_image)

    def _load_template(self) -> Image.Image:
        if self.template_path.is_file():
            return Image.open(self.template_path).convert("RGBA").resize(
                (CANVAS_W, CANVAS_H)
            )
        logger.warning(
            f"Template not found at {self.template_path}; using white fallback."
        )
        return Image.new("RGBA", (CANVAS_W, CANVAS_H), COL_WHITE)

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
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Could not load {role} font at {path}: {exc}"
            ) from exc
        self._font_cache[key] = font
        return font

    @staticmethod
    def _font_from(
        existing: ImageFont.FreeTypeFont,
        size: int,
    ) -> ImageFont.FreeTypeFont:
        try:
            return existing.font_variant(size=size)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Could not resize badge font to {size}px: {exc}"
            ) from exc

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
                    f"No scalable {role} font found. "
                    "See middleware/fonts/README.md."
                )
            digest.update(role.encode("ascii"))
            digest.update(path.read_bytes())
        self._resource_fingerprint_cache = digest.digest()
        return self._resource_fingerprint_cache
