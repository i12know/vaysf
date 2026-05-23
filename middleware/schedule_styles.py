"""schedule_styles.py — central palette for VAY Sports Fest schedule rendering.

One module owns every color and prefix used in the Excel schedule outputs:
the master Schedule-by-Time grid, the Schedule-by-Sport flat list, and any
future printable/screenshot exports.  Operators changing the look-and-feel
edit this file (or override at call sites) instead of hunting through tab
writers.

Two-layer visual code (per Issue #131):
  * Fill color  = sport / event family.
  * Text color  = division category (M / W / X / N / N35+).
  * Prefix      = same category, in text, so the schedule survives black-
    -and-white printing and color-vision limitations.

All colors are Excel "RRGGBB" hex strings (no leading '#'), the form
openpyxl's PatternFill / Font accept directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from config import SPORT_TYPE


# ---------------------------------------------------------------------------
# Category styles (M / W / X / N / N35+)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CategoryStyle:
    code: str          # short key: "M", "W", "X", "N", "N35+"
    prefix: str        # text shown in cells: "M", "W", "X", "N", "N35+"
    text_color: str    # Excel "RRGGBB"
    description: str   # legend / tooltip


CATEGORY_STYLES: Dict[str, CategoryStyle] = {
    "M":    CategoryStyle("M",    "M",    "1F3864", "Men"),
    "W":    CategoryStyle("W",    "W",    "9C2A6D", "Women"),
    "X":    CategoryStyle("X",    "X",    "0F6F73", "Mixed"),
    "N":    CategoryStyle("N",    "N",    "333333", "Any-gender / neutral"),
    "N35+": CategoryStyle("N35+", "N35+", "5C2A12", "35+ division"),
}

# Default category when none can be inferred — keeps cells readable.
_DEFAULT_CATEGORY = "N"


# ---------------------------------------------------------------------------
# Sport / event styles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SportStyle:
    fill_color: str          # Excel "RRGGBB" for cell fill
    abbrev: str              # 2-letter event abbreviation: BB, VB, BC, ...
    default_category: str    # M / W / X / N / N35+


# Per the Issue #131 palette.  Light fills so category text colors stay
# readable on top of them.
SPORT_STYLES: Dict[str, SportStyle] = {
    SPORT_TYPE["BASKETBALL"]:       SportStyle("FFD8B5", "BB", "N"),
    SPORT_TYPE["VOLLEYBALL_MEN"]:   SportStyle("BDD7EE", "VB", "M"),
    SPORT_TYPE["VOLLEYBALL_WOMEN"]: SportStyle("FAD2CF", "VB", "W"),
    SPORT_TYPE["BIBLE_CHALLENGE"]:  SportStyle("C6E0B4", "BC", "N"),
    SPORT_TYPE["SCRIPTURE"]:        SportStyle("D5C8E4", "SM", "N"),
    SPORT_TYPE["BADMINTON"]:        SportStyle("FFE699", "BD", "M"),
    SPORT_TYPE["PICKLEBALL"]:       SportStyle("E1D5E7", "PB", "X"),
    SPORT_TYPE["PICKLEBALL_35"]:    SportStyle("E1D5E7", "PB", "N35+"),
    SPORT_TYPE["TABLE_TENNIS"]:     SportStyle("FFF2CC", "TT", "N"),
    SPORT_TYPE["TABLE_TENNIS_35"]:  SportStyle("FFF2CC", "TT", "N35+"),
    SPORT_TYPE["TENNIS"]:           SportStyle("D5E8D4", "TN", "M"),
    SPORT_TYPE["SOCCER"]:           SportStyle("DEEBF7", "SC", "X"),
    SPORT_TYPE["TRACK_FIELD"]:      SportStyle("E7E6E6", "TF", "N"),
    SPORT_TYPE["TUG_OF_WAR"]:       SportStyle("E7E6E6", "TW", "N"),
}

# Fallback used when an unknown event slips through (so renderers never
# crash on a new sport added before this map is updated).
_FALLBACK_SPORT = SportStyle("EBF1DE", "??", "N")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def sport_style(event_name: str) -> SportStyle:
    """Look up the SportStyle for an event name, with safe fallback."""
    return SPORT_STYLES.get(str(event_name or "").strip(), _FALLBACK_SPORT)


def category_style(code: Optional[str]) -> CategoryStyle:
    """Look up the CategoryStyle for a category code, with safe fallback."""
    key = str(code or "").strip()
    return CATEGORY_STYLES.get(key, CATEGORY_STYLES[_DEFAULT_CATEGORY])


def infer_category(event_name: str, sport_format: str = "") -> str:
    """Best-effort category code from event name and optional sport_format.

    Priority:
      1. Explicit sport_format (e.g. "Men", "Women", "Mixed Doubles") wins —
         lets racquet sports tag individual matches.
      2. SPORT_STYLES.default_category for the event (per Issue #131 the
         palette declares the canonical default, e.g. Basketball=N even
         though its SPORT_TYPE name contains "Men").
      3. Heuristic from the event name suffix, for events not in the
         SPORT_STYLES map.
      4. "N" as the universal fallback.
    """
    fmt = str(sport_format or "").strip().casefold()
    if fmt:
        if "women" in fmt:
            return "W"
        if "men" in fmt:
            return "M"
        if "mixed" in fmt or "coed" in fmt:
            return "X"

    style = SPORT_STYLES.get(str(event_name or "").strip())
    if style is not None:
        return style.default_category

    name = str(event_name or "").strip().casefold()
    if name:
        if "women" in name:
            return "W"
        if "men" in name and "women" not in name:
            return "M"
        if "mixed" in name or "coed" in name:
            return "X"

    return _DEFAULT_CATEGORY


def style_for_game(game: Dict) -> Tuple[SportStyle, CategoryStyle, str]:
    """Resolve fill + text styles + category code for one scheduled game.

    A game dict may carry an explicit "category" (M/W/X/N/N35+) or a
    "sport_format" string; either is honored before falling back to
    inference from the event name.
    """
    event = str(game.get("event") or "")
    explicit = str(game.get("category") or "").strip()
    if explicit and explicit in CATEGORY_STYLES:
        cat = explicit
    else:
        cat = infer_category(event, str(game.get("sport_format") or ""))
    return sport_style(event), category_style(cat), cat


def category_prefix(event_name: str, sport_format: str = "",
                    category: Optional[str] = None) -> str:
    """Return the visible category prefix (e.g. "M", "X", "N35+")."""
    if category and category in CATEGORY_STYLES:
        return CATEGORY_STYLES[category].prefix
    return CATEGORY_STYLES[infer_category(event_name, sport_format)].prefix


def format_compact_label(event_name: str, sport_format: str = "",
                         category: Optional[str] = None) -> str:
    """Compact "[Prefix] [Abbrev]" label, e.g. "M VB" or "N35+ PB"."""
    return f"{category_prefix(event_name, sport_format, category)} {sport_style(event_name).abbrev}"
