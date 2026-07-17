"""Reusable Bible verse sets for generated score sheets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


DEFAULT_VERSE_SOURCE = Path(__file__).resolve().parent / "config" / "bible_verse_sets.json"

EVENT_ALIASES = {
    "bible challenge": "bible-challenge",
    "bible challenge mixed team": "bible-challenge",
    "bible-challenge": "bible-challenge",
}


class VerseSetError(ValueError):
    """Raised when a score-sheet verse source is missing or malformed."""


@dataclass(frozen=True)
class BibleVerse:
    set_key: str
    event: str
    season: int
    sort_order: int
    reference: str
    verse_text: str
    translation: str = ""
    active: bool = True
    event_locked: bool = False
    general_pool: bool = True
    allowed_events: tuple[str, ...] = ()


def _normalize_event(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    tokenized = re.sub(r"[^a-z0-9]+", " ", raw).strip()
    compact = re.sub(r"\s+", " ", tokenized)
    slug = compact.replace(" ", "-")
    return EVENT_ALIASES.get(raw) or EVENT_ALIASES.get(compact) or EVENT_ALIASES.get(slug) or slug


def _expect_text(row: dict[str, Any], field: str, row_idx: int) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise VerseSetError(f"Verse row {row_idx} is missing required field {field!r}.")
    return value


def _expect_int(row: dict[str, Any], field: str, row_idx: int) -> int:
    value = row.get(field)
    if not isinstance(value, int) or value <= 0:
        raise VerseSetError(f"Verse row {row_idx} field {field!r} must be a positive integer.")
    return value


def _normalize_allowed_events(value: Any, row_idx: int) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise VerseSetError(f"Verse row {row_idx} field 'allowed_events' must be a list.")
    normalized = tuple(_normalize_event(item) for item in value if _normalize_event(item))
    return normalized


def _read_rows(source_path: Path) -> Iterable[dict[str, Any]]:
    if not source_path.exists():
        raise VerseSetError(f"Bible verse source not found: {source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VerseSetError(f"Bible verse source is not valid JSON: {source_path}") from exc
    rows = payload.get("verse_sets") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise VerseSetError("Bible verse source must contain a 'verse_sets' list.")
    for row_idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise VerseSetError(f"Verse row {row_idx} must be an object.")
        yield row


def load_bible_verse_set(
    set_key: str,
    *,
    event: Optional[str] = None,
    source_path: Optional[Path] = None,
    active_only: bool = True,
) -> list[BibleVerse]:
    """Load and validate a reusable Bible verse set."""

    wanted_set = str(set_key or "").strip()
    if not wanted_set:
        raise VerseSetError("A verse set_key is required.")
    wanted_event = _normalize_event(event)
    verses: list[BibleVerse] = []
    for row_idx, row in enumerate(_read_rows(source_path or DEFAULT_VERSE_SOURCE), start=1):
        row_set_key = _expect_text(row, "set_key", row_idx)
        if row_set_key != wanted_set:
            continue
        active = bool(row.get("active", True))
        if active_only and not active:
            continue

        row_event = _normalize_event(_expect_text(row, "event", row_idx))
        allowed_events = _normalize_allowed_events(row.get("allowed_events"), row_idx)
        event_locked = bool(row.get("event_locked", False))
        if wanted_event:
            allowed_for_event = row_event == wanted_event or wanted_event in allowed_events
            if event_locked and row_event != wanted_event:
                continue
            if not allowed_for_event:
                continue

        reference = _expect_text(row, "reference", row_idx)
        verse_text = _expect_text(row, "verse_text", row_idx)
        if verse_text.casefold() == reference.casefold():
            raise VerseSetError(
                f"Verse row {row_idx} ({reference}) has placeholder verse_text matching its reference."
            )

        verses.append(
            BibleVerse(
                set_key=row_set_key,
                event=row_event,
                season=_expect_int(row, "season", row_idx),
                sort_order=_expect_int(row, "sort_order", row_idx),
                reference=reference,
                verse_text=verse_text,
                translation=str(row.get("translation") or "").strip(),
                active=active,
                event_locked=event_locked,
                general_pool=bool(row.get("general_pool", True)),
                allowed_events=allowed_events,
            )
        )

    if not verses:
        scope = f" for event {wanted_event!r}" if wanted_event else ""
        raise VerseSetError(f"No active Bible verse rows found for set {wanted_set!r}{scope}.")

    sort_orders = [verse.sort_order for verse in verses]
    if len(sort_orders) != len(set(sort_orders)):
        raise VerseSetError(f"Bible verse set {wanted_set!r} has duplicate sort_order values.")

    return sorted(verses, key=lambda verse: verse.sort_order)

