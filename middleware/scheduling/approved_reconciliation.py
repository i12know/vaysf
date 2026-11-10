"""approved_reconciliation - fold the approved 2026 schedules into venue_input.xlsx.

Issue #216.  ``venue_input.xlsx`` describes what was *booked*: physical
resources, gym modes, and operating windows.  The four approved schedule
workbooks describe what the event will actually *do* with that booking:
ceremonies, worship, meals, setup, CLOSED windows, community events, which
sport owns which court when, and the Friday Orange Church racquet grids.

This module parses every meaningful cell of the four workbooks into an
``operational block`` record with source provenance, reconciles those blocks
against the booked Venue-Input / Gym-Modes model, and proposes a new
``Venue-Input`` tab that exposes only operationally valid windows:

* non-sport blocks (setup, meals, ceremonies/worship, community events,
  CLOSED) are subtracted from every resource row on that physical area;
* sport blocks lock the area to that sport's resource type: rows of the
  matching type keep the window, rows of any other mode in the same physical
  area lose it, so the Stage-A gym allocator cannot hand the window to
  another sport;
* the Friday Orange Church Badminton / Table Tennis rows are re-gridded to
  the approved 20- / 15-minute grids and limited to the approved court/table
  count.

The approved schedules only *constrain* the booking.  Nothing here adds
capacity: a block that needs a court, table, day, or time the booking does
not have is reported as an error instead.

Workbook contract written on ``--execute``:

* ``Booked-Venue-Input`` - the untouched booking, copied from Venue-Input on
  the first execute.  Every later run reconciles from this tab, so a changed
  approved workbook can re-open a window an earlier run closed, and running
  twice with unchanged inputs produces an identical workbook.  Operators edit
  bookings here (or add new rows to Venue-Input; rows without a Booked Row ID
  are adopted into the booking automatically).
* ``Venue-Input`` - the reconciled, scheduler-consumable windows.
* ``Operational-Blocks`` - every parsed block, including CLOSED / setup /
  meal / ceremony rows that never become resource rows, with provenance.
* ``Reconciliation-Sources`` - source workbook names and content hashes.

Gym-Modes and Playoff-Slots are preserved untouched.  Stage blocks (QF / SF /
3rd / Final) lock the gym mode for their window but are not written to
Playoff-Slots: their participants are unknown, and the existing
import-master-schedule / Playoff-Slots path stays the single owner of pinned
playoff games.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from gym_allocator import extract_gym_blocks
from schedule_workbook import ScheduleWorkbookBuilder

from config import (
    GYM_RESOURCE_TYPE_BASKETBALL,
    GYM_RESOURCE_TYPE_VOLLEYBALL,
    POD_RESOURCE_TYPE_BADMINTON,
    POD_RESOURCE_TYPE_TABLE_TENNIS,
    SPORT_TYPE,
    TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
    TEAM_RESOURCE_TYPE_SOCCER,
)
from scheduling import approved_games
from scheduling import master_schedule
from scheduling import match_schedule_overrides
from scheduling.xlsx_utils import (
    _coerce_excel_date,
    _derive_day_labels_from_dates,
    _normalize_resource_type_name,
    _parse_hour,
)

RECONCILIATION_AUDIT_FILENAME = "approved_schedule_reconciliation.audit.json"

VENUE_SHEET = "Venue-Input"
BOOKED_SHEET = "Booked-Venue-Input"
PLAYOFF_SHEET = "Playoff-Slots"
BLOCKS_SHEET = "Operational-Blocks"
SOURCES_SHEET = "Reconciliation-Sources"
BOOKED_ROW_ID_COLUMN = "Booked Row ID"

# Block classifications (Issue #216 "Recommended block classifications").
SPORT_MATCH = "sport_match"
SPORT_STAGE_BLOCK = "sport_stage_block"
SPORT_RESERVATION = "sport_reservation"
SETUP = "setup"
MEAL_OR_BREAK = "meal_or_break"
CEREMONY_OR_WORSHIP = "ceremony_or_worship"
COMMUNITY_EVENT = "community_event"
CLOSED = "closed"
REFERENCE = "reference_to_separate_schedule"
UNRESOLVED = "unresolved"

SPORT_CLASSIFICATIONS = {SPORT_MATCH, SPORT_STAGE_BLOCK, SPORT_RESERVATION}
BLACKOUT_CLASSIFICATIONS = {SETUP, MEAL_OR_BREAK, CEREMONY_OR_WORSHIP, COMMUNITY_EVENT, CLOSED}

ACTION_BY_CLASSIFICATION = {
    SPORT_MATCH: "lock_sport_mode",
    SPORT_STAGE_BLOCK: "lock_sport_mode",
    SPORT_RESERVATION: "lock_sport_mode",
    SETUP: "blackout",
    MEAL_OR_BREAK: "blackout",
    CEREMONY_OR_WORSHIP: "blackout",
    COMMUNITY_EVENT: "blackout",
    CLOSED: "blackout",
    REFERENCE: "none_reference",
    UNRESOLVED: "none_unresolved",
}

ORANGE_VENUE_MARKERS = ("orange", "orn")
DEFAULT_ROW_MINUTES = 60
SOCCER_MATCH_MINUTES = 60
EXPECTED_BADMINTON_MATCHES = 39
EXPECTED_SOCCER_EXACT_MATCHES = 6

_EVENT_RESOURCE_TYPE = {
    SPORT_TYPE["BASKETBALL"]: GYM_RESOURCE_TYPE_BASKETBALL,
    SPORT_TYPE["VOLLEYBALL_MEN"]: GYM_RESOURCE_TYPE_VOLLEYBALL,
    SPORT_TYPE["VOLLEYBALL_WOMEN"]: GYM_RESOURCE_TYPE_VOLLEYBALL,
    SPORT_TYPE["BIBLE_CHALLENGE"]: TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
    SPORT_TYPE["SOCCER"]: TEAM_RESOURCE_TYPE_SOCCER,
    SPORT_TYPE["BADMINTON"]: POD_RESOURCE_TYPE_BADMINTON,
    SPORT_TYPE["TABLE_TENNIS"]: POD_RESOURCE_TYPE_TABLE_TENNIS,
    SPORT_TYPE["TABLE_TENNIS_35"]: POD_RESOURCE_TYPE_TABLE_TENNIS,
}

# Words that name the lane/court rather than the physical area in a visual
# header such as "EHS Main Gym BB1" -> area "ehs main gym".
# "gym" is too generic to tell two gyms apart, so it never decides a match.
_AREA_STOP_WORDS = {"court", "courts", "table", "tables", "room", "gym", "the"}

# Visual-header abbreviations that must resolve to the same word the booked
# Venue Name / Exclusive Venue Group uses, or the area token match in
# target_rows()/_area_score() silently finds zero overlap (e.g. "Prac. Gym
# VB1" vs. booked "EHS Practice Gym" -> unknown_venue, Issue #216 dry run).
_AREA_WORD_ALIASES = {"prac": "practice"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def default_venue_input_path(data_dir: Path) -> Path:
    from config import VENUE_INPUT_FILENAME

    return Path(data_dir) / VENUE_INPUT_FILENAME


def default_audit_path(base_dir: Path) -> Path:
    return Path(base_dir) / RECONCILIATION_AUDIT_FILENAME


def _clean(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _norm(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _clean(value).casefold()).split())


def _to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _clock(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _decimal_hours(minutes: int) -> float:
    hours = minutes / 60.0
    return int(hours) if minutes % 60 == 0 else round(hours, 6)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _issue(kind: str, message: str, **details: Any) -> Dict[str, Any]:
    return {"kind": kind, "message": message, **{k: v for k, v in details.items() if v not in (None, "")}}


# ---------------------------------------------------------------------------
# Text and header classification
# ---------------------------------------------------------------------------

_STAGE_RE = re.compile(r"\b(QF|SF|SEMI|SEMIS|SEMIFINAL|FINALS?|3RD|THIRD|PLAYOFFS?)\b")


def _resource_type_from_text(text: str) -> Optional[str]:
    upper = f" {text.upper()} "
    if re.search(r"\b(BB|BASKETBALL)\b", upper):
        return GYM_RESOURCE_TYPE_BASKETBALL
    if re.search(r"\b(MVB|WVB|VB|VOLLEYBALL)\b", upper):
        return GYM_RESOURCE_TYPE_VOLLEYBALL
    if re.search(r"\b(BC|BIBLE)\b", upper):
        return TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE
    if re.search(r"\bSOCCER\b", upper):
        return TEAM_RESOURCE_TYPE_SOCCER
    if re.search(r"\bBADMINTON\b", upper):
        return POD_RESOURCE_TYPE_BADMINTON
    if re.search(r"\b(TABLE TENNIS|PING ?PONG|TT)\b", upper):
        return POD_RESOURCE_TYPE_TABLE_TENNIS
    return None


def classify_text(text: str) -> Tuple[str, Optional[str]]:
    """Classify a non-game schedule cell. Returns (classification, resource_type).

    Order matters: a cell reading "BADMINTON / TABLE TENNIS @ ORANGE" is a
    pointer to the separate racquet schedules, while "BB QF" is a stage block
    that still occupies the court it is drawn on.
    """
    upper = " ".join(_clean(text).upper().split())
    if not upper:
        return UNRESOLVED, None
    if re.fullmatch(r"CLOSED\b.*", upper) or upper == "CLOSED":
        return CLOSED, None
    if re.search(r"\b(BADMINTON|TABLE TENNIS|PING ?PONG|ORANGE|ORN)\b", upper) or "SEPARATE SCHEDULE" in upper:
        return REFERENCE, _resource_type_from_text(upper)
    if re.search(r"SET\s*-?\s*UP|TAPE|AUDIO|\bA/?V\b|CLEAN\s*-?\s*UP|TEAR\s*DOWN", upper):
        return SETUP, None
    if re.search(r"\b(DINNER|LUNCH|BREAKFAST|BREAK|MEAL|SNACK)\b", upper):
        return MEAL_OR_BREAK, None
    if re.search(r"CEREMONY|SERVICE|WORSHIP|DEVOTION|PRAYER|OPENING|CLOSING|CHECK\s*-?\s*INS?", upper):
        return CEREMONY_OR_WORSHIP, None
    if re.search(r"TRACK|TUG|SCRIPTURE|MEMORIZATION|CONTEST|COMMUNITY|FIELD DAY", upper):
        return COMMUNITY_EVENT, None
    if _STAGE_RE.search(upper) or "PLAYOFF" in upper:
        return SPORT_STAGE_BLOCK, _resource_type_from_text(upper)
    return UNRESOLVED, None


def parse_visual_venue(header: str) -> Dict[str, Any]:
    """Split a visual venue header such as "EHS Main Gym BB1" into parts."""
    text = _clean(header)
    upper = text.upper()
    lane: Optional[int] = None
    resource_type: Optional[str] = None
    lane_match = re.search(r"\b(BB|VB|COURT|CT|TABLE|FIELD)\s*-?\s*(\d+)\b", upper)
    if lane_match:
        lane = int(lane_match.group(2))
        token = lane_match.group(1)
        if token == "BB":
            resource_type = GYM_RESOURCE_TYPE_BASKETBALL
        elif token == "VB":
            resource_type = GYM_RESOURCE_TYPE_VOLLEYBALL
    if resource_type is None:
        resource_type = _resource_type_from_text(upper)
        if resource_type is None and re.search(r"LIBRARY|CLASS", upper):
            resource_type = TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE
    area = upper
    if lane_match:
        area = area[: lane_match.start()] + area[lane_match.end():]
    area = re.sub(r"\b(BB|VB|MVB|WVB|BC)\b", " ", area)
    area_tokens = [
        _AREA_WORD_ALIASES.get(tok, tok)
        for tok in _norm(area).split()
        if tok not in _AREA_STOP_WORDS
    ]
    return {
        "header": text,
        "area": " ".join(area_tokens),
        "resource_type": resource_type,
        "lane": lane,
        "offsite_orange": any(re.search(rf"\b{m}\b", text.casefold()) for m in ORANGE_VENUE_MARKERS),
    }


# ---------------------------------------------------------------------------
# Block records
# ---------------------------------------------------------------------------

def _block(
    *,
    source_path: Path,
    sheet: str,
    cell: str,
    raw_text: str,
    day: Optional[str],
    start: Optional[str],
    end: Optional[str],
    venue: str,
    classification: str,
    resource_type: Optional[str] = None,
    lane: Optional[int] = None,
    lane_resource_type: Optional[str] = None,
    event: Optional[str] = None,
    area: str = "",
    offsite_orange: bool = False,
    source_role: str = "",
    confidence: str = "high",
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    record = {
        "source_file": Path(source_path).name,
        "source_role": source_role,
        "source_sheet": sheet,
        "source_cell": cell,
        "raw_text": raw_text,
        "day": day,
        "start_time": start,
        "end_time": end,
        "venue": venue,
        "area": area,
        "resource_type": resource_type,
        "lane": lane,
        "lane_resource_type": lane_resource_type or resource_type,
        "event": event,
        "classification": classification,
        "offsite_orange": offsite_orange,
        "confidence": confidence,
        "action": ACTION_BY_CLASSIFICATION[classification],
    }
    if extra:
        record.update(extra)
    return record


def _merged_lookup(ws) -> Dict[Tuple[int, int], Tuple[int, int, str]]:
    lookup: Dict[Tuple[int, int], Tuple[int, int, str]] = {}
    for merged in ws.merged_cells.ranges:
        anchor = (merged.min_row, merged.min_col, merged.coord)
        for row in range(merged.min_row, merged.max_row + 1):
            for col in range(merged.min_col, merged.max_col + 1):
                lookup[(row, col)] = anchor
    return lookup


def _effective(ws, merged: Mapping[Tuple[int, int], Tuple[int, int, str]], row: int, col: int) -> Tuple[Any, str, bool]:
    """Return (value, provenance, is_merged) honoring merged ranges."""
    anchor = merged.get((row, col))
    if anchor:
        return ws.cell(row=anchor[0], column=anchor[1]).value, anchor[2], True
    return ws.cell(row=row, column=col).value, ws.cell(row=row, column=col).coordinate, False


def _row_ends(times: Sequence[Tuple[int, str]]) -> Dict[int, str]:
    """Map each time row to its end time = the next row's start in the section."""
    minutes = [_to_minutes(t) for _, t in times]
    diffs = [b - a for a, b in zip(minutes, minutes[1:]) if b > a]
    default = Counter(diffs).most_common(1)[0][0] if diffs else DEFAULT_ROW_MINUTES
    ends: Dict[int, str] = {}
    for index, (row_idx, start) in enumerate(times):
        start_min = minutes[index]
        if index + 1 < len(times) and minutes[index + 1] > start_min:
            ends[row_idx] = _clock(minutes[index + 1])
        else:
            ends[row_idx] = _clock(start_min + default)
    return ends


def _grid_minutes(times: Sequence[str]) -> Optional[int]:
    minutes = sorted({_to_minutes(t) for t in times})
    diffs = [b - a for a, b in zip(minutes, minutes[1:]) if b > a]
    return Counter(diffs).most_common(1)[0][0] if diffs else None


def coalesce_blocks(blocks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge vertically contiguous identical non-game blocks into one range.

    A CLOSED or DINNER cell drawn across three consecutive time rows on one
    court becomes one 3-hour block whose provenance lists every source cell.
    Individual games are never merged: each is its own approved placement.
    """
    out: List[Dict[str, Any]] = []
    for block in blocks:
        prev = out[-1] if out else None
        if (
            prev is not None
            and block["classification"] != SPORT_MATCH
            and prev["classification"] == block["classification"]
            and prev["source_file"] == block["source_file"]
            and prev["day"] == block["day"]
            and prev["venue"] == block["venue"]
            and prev["raw_text"] == block["raw_text"]
            and prev["end_time"] == block["start_time"]
        ):
            prev["end_time"] = block["end_time"]
            cells = prev["source_cell"].split(", ")
            if block["source_cell"] not in cells:
                prev["source_cell"] = f"{prev['source_cell']}, {block['source_cell']}"
            continue
        out.append(dict(block))
    return out


# ---------------------------------------------------------------------------
# Workbook parsers
# ---------------------------------------------------------------------------

def parse_main_schedule_blocks(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse every meaningful venue cell of the Main Schedule workbook."""
    path = Path(path)
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    merged = _merged_lookup(ws)
    warnings: List[str] = []

    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for row_idx in range(1, ws.max_row + 1):
        header = master_schedule._date_header_day(ws.cell(row=row_idx, column=1).value)
        if header:
            current = {
                "day": header[1],
                "venues": match_schedule_overrides._venue_blocks_for_header_row(ws, row_idx),
                "times": [],
            }
            sections.append(current)
            continue
        start = match_schedule_overrides._time_label(ws.cell(row=row_idx, column=1).value)
        if current is not None and start and current["venues"]:
            current["times"].append((row_idx, start))

    per_venue: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for section in sections:
        ends = _row_ends(section["times"])
        for row_idx, start in section["times"]:
            for start_col, end_col, venue_name in section["venues"]:
                venue = parse_visual_venue(venue_name)
                block = _main_cell_block(
                    ws, merged, path, row_idx, start_col, end_col,
                    day=section["day"], start=start, end=ends[row_idx], venue=venue,
                )
                if block is not None:
                    per_venue[(section["day"], venue_name)].append(block)

    blocks: List[Dict[str, Any]] = []
    for key in per_venue:
        blocks.extend(coalesce_blocks(per_venue[key]))
    blocks.sort(key=lambda b: (b["day"] or "", b["start_time"] or "", b["venue"], b["source_cell"]))
    for block in blocks:
        if block["classification"] == UNRESOLVED:
            warnings.append(f"{block['source_sheet']}!{block['source_cell']}: unresolved cell {block['raw_text']!r}")
    return blocks, warnings


def _main_cell_block(ws, merged, path, row_idx, start_col, end_col, *, day, start, end, venue):
    effective = [_effective(ws, merged, row_idx, col) for col in range(start_col, end_col + 1)]
    values = [_clean(value) for value, _, _ in effective]
    if not any(values):
        return None
    any_merged = any(is_merged for _, _, is_merged in effective)
    provenance = list(dict.fromkeys(ref for (_, ref, _), value in zip(effective, values) if value))
    cell_ref = ", ".join(provenance)
    raw_text = " / ".join(dict.fromkeys(v for v in values if v))
    common = dict(
        source_path=path,
        sheet=ws.title,
        cell=cell_ref,
        raw_text=raw_text,
        day=day,
        start=start,
        end=end,
        venue=venue["header"],
        area=venue["area"],
        lane=venue["lane"],
        lane_resource_type=venue["resource_type"],
        offsite_orange=venue["offsite_orange"],
        source_role="main_schedule",
    )

    if not any_merged:
        cells = [ws.cell(row=row_idx, column=col) for col in range(start_col, end_col + 1)]
        game = match_schedule_overrides._classify_block(
            cells, day, start, master_schedule._slot_label(day, start), venue["header"], ws.title,
        )
        if game is not None and game.get("kind") in {"two_team_game", "three_team_game"}:
            teams = game.get("teams") or [game.get("team_a"), game.get("team_b")]
            return _block(
                **common,
                classification=SPORT_MATCH,
                resource_type=game.get("resource_type"),
                event=game.get("event"),
                extra={"teams": [t for t in teams if t]},
            )
        if game is not None and game.get("kind") == "bye":
            event = game.get("event")
            return _block(
                **common,
                classification=SPORT_RESERVATION,
                resource_type=_EVENT_RESOURCE_TYPE.get(event) or venue["resource_type"],
                event=event,
                extra={"note": "bye cell keeps the court reserved for its sport"},
            )
        if game is not None and game.get("kind") == "block" and game.get("severity") == "error":
            return _block(
                **common,
                classification=UNRESOLVED,
                confidence="low",
                extra={"note": game.get("note")},
            )

    classification, resource_type = classify_text(raw_text)
    if classification == SPORT_STAGE_BLOCK and resource_type is None:
        resource_type = venue["resource_type"]
        if resource_type is None:
            return _block(**common, classification=UNRESOLVED, confidence="low",
                          extra={"note": "stage block with no resolvable sport"})
    return _block(**common, classification=classification, resource_type=resource_type)


def parse_badminton_blocks(path: Path) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """Parse the Friday Orange Church Badminton grid (three courts, 20-minute slots)."""
    path = Path(path)
    wb = load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    warnings: List[str] = []
    blocks: List[Dict[str, Any]] = []
    times: List[Tuple[int, str]] = []
    for row in range(1, ws.max_row + 1):
        start = approved_games._time_label(ws.cell(row=row, column=1).value)
        if start:
            times.append((row, start))
    grid = _grid_minutes([t for _, t in times]) or 20
    ends = {row: _clock(_to_minutes(start) + grid) for row, start in times}
    lanes_used: set[int] = set()
    match_count = 0
    match_minutes: List[int] = []
    for row, start in times:
        row_has_match = False
        for lane, start_col in enumerate((2, 6, 10), start=1):
            match_no = ws.cell(row=row, column=start_col).value
            team_a = approved_games._team_code(ws.cell(row=row, column=start_col + 1).value)
            middle = _clean(ws.cell(row=row, column=start_col + 2).value).casefold()
            team_b = approved_games._team_code(ws.cell(row=row, column=start_col + 3).value)
            if match_no not in (None, "") and middle == "v" and team_a and team_b:
                row_has_match = True
                lanes_used.add(lane)
                is_bye = approved_games._is_bye(team_a) or approved_games._is_bye(team_b)
                if not is_bye:
                    match_count += 1
                match_minutes.append(_to_minutes(start))
                blocks.append(_block(
                    source_path=path, sheet=ws.title,
                    cell=approved_games._cell_range(ws.title, row, start_col, start_col + 3).split("!", 1)[1],
                    raw_text=f"{match_no}: {team_a} v {team_b}",
                    day="Fri-1", start=start, end=ends[row],
                    venue=f"Orange Church Badminton Court {lane}", area="orange church",
                    resource_type=POD_RESOURCE_TYPE_BADMINTON, lane=lane,
                    event=SPORT_TYPE["BADMINTON"],
                    classification=SPORT_RESERVATION if is_bye else SPORT_MATCH,
                    offsite_orange=True, source_role="badminton",
                ))
        if row_has_match:
            continue
        texts = [_clean(ws.cell(row=row, column=col).value) for col in range(2, ws.max_column + 1)]
        text = " / ".join(dict.fromkeys(t for t in texts if t and not re.fullmatch(r"\d+", t)))
        if not text:
            continue
        classification, resource_type = classify_text(text)
        if classification == REFERENCE:
            # "Badminton" mentioned inside the badminton workbook is not a pointer
            # elsewhere; an un-gamed labelled row is check-in / transition time.
            classification = UNRESOLVED
        blocks.append(_block(
            source_path=path, sheet=ws.title, cell=f"A{row}:{get_column_letter(ws.max_column)}{row}",
            raw_text=text, day="Fri-1", start=start, end=ends[row],
            venue="Orange Church Badminton", area="orange church",
            resource_type=POD_RESOURCE_TYPE_BADMINTON if classification in SPORT_CLASSIFICATIONS else resource_type,
            lane_resource_type=POD_RESOURCE_TYPE_BADMINTON,
            classification=classification, offsite_orange=True, source_role="badminton",
        ))
    if match_count != EXPECTED_BADMINTON_MATCHES:
        warnings.append(
            f"Badminton grid has {match_count} preliminary match(es); expected {EXPECTED_BADMINTON_MATCHES}."
        )
    for block in blocks:
        if block["classification"] == UNRESOLVED:
            warnings.append(f"{path.name} {block['source_cell']}: unresolved cell {block['raw_text']!r}")
    grid_info = {
        "resource_type": POD_RESOURCE_TYPE_BADMINTON,
        "day": "Fri-1",
        "slot_minutes": grid,
        "lanes": len(lanes_used),
        "window_start": _clock(min(match_minutes)) if match_minutes else None,
        "window_end": _clock(max(match_minutes) + grid) if match_minutes else None,
        "match_count": match_count,
    }
    return coalesce_blocks(blocks), warnings, grid_info


def parse_soccer_blocks(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse the Co-ed Soccer sheet: exact G1-G6 matches, TBD advancement rows."""
    path = Path(path)
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    warnings: List[str] = []
    blocks: List[Dict[str, Any]] = []
    exact = 0
    for row in range(1, ws.max_row + 1):
        game_no = _clean(ws.cell(row=row, column=3).value)
        if not re.fullmatch(r"G\s*\d+.*", game_no, re.I):
            continue
        team_a = _clean(ws.cell(row=row, column=4).value)
        middle = _clean(ws.cell(row=row, column=5).value).casefold()
        team_b = _clean(ws.cell(row=row, column=6).value)
        referee = _clean(ws.cell(row=row, column=7).value)
        raw = " ".join(part for part in (game_no, team_a, "v", team_b) if part)
        day = approved_games._date_to_day(ws.cell(row=row, column=1).value)
        start = approved_games._time_label(ws.cell(row=row, column=2).value)
        is_exact = bool(
            day and start and middle == "v"
            and approved_games._TEAM_CODE_RE.match(team_a.upper())
            and approved_games._TEAM_CODE_RE.match(team_b.upper())
            and not approved_games._is_bye(team_a) and not approved_games._is_bye(team_b)
        )
        common = dict(
            source_path=path, sheet=ws.title, cell=f"A{row}:G{row}", raw_text=raw,
            venue="Soccer Field", area="", resource_type=TEAM_RESOURCE_TYPE_SOCCER,
            event=SPORT_TYPE["SOCCER"], source_role="soccer",
        )
        if is_exact:
            exact += 1
            blocks.append(_block(
                **common, day=day, start=start, end=_clock(_to_minutes(start) + SOCCER_MATCH_MINUTES),
                lane=None, classification=SPORT_MATCH,
                extra={"game_key": f"SOC-{game_no.split()[0].upper()}",
                       "teams": [team_a.upper(), team_b.upper()], "referee": referee},
            ))
        else:
            blocks.append(_block(
                **common, day=day, start=start,
                end=_clock(_to_minutes(start) + SOCCER_MATCH_MINUTES) if start else None,
                classification=UNRESOLVED, confidence="low",
                extra={"game_key": f"SOC-{game_no.split()[0].upper()}", "referee": referee,
                       "note": "advancement/TBD row kept unresolved; no venue window invented"},
            ))
    if exact != EXPECTED_SOCCER_EXACT_MATCHES:
        warnings.append(
            f"Soccer sheet has {exact} exact pool match(es); expected {EXPECTED_SOCCER_EXACT_MATCHES}."
        )
    return blocks, warnings


def parse_table_tennis_blocks(path: Path) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any], Dict[str, Any]]:
    """Parse the Friday Orange Church Table Tennis grid (four tables, 15-minute slots).

    Also compares the U35 doubles teams in the workbook's roster section with
    the U35 teams actually scheduled (the known FVC vs SBC discrepancy).
    """
    path = Path(path)
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    warnings: List[str] = []
    blocks: List[Dict[str, Any]] = []
    times: List[Tuple[int, str]] = []
    for row in range(1, ws.max_row + 1):
        start = approved_games._time_label(ws.cell(row=row, column=1).value)
        if start:
            times.append((row, start))
    grid = _grid_minutes([t for _, t in times]) or 15
    lanes_used: set[int] = set()
    match_minutes: List[int] = []
    schedule_u35: set[str] = set()
    for row, start in times:
        end = _clock(_to_minutes(start) + grid)
        for column in range(2, 6):
            raw = _clean(ws.cell(row=row, column=column).value)
            if not raw:
                continue
            lane = column - 1
            common = dict(
                source_path=path, sheet=ws.title, cell=ws.cell(row=row, column=column).coordinate,
                raw_text=raw, day="Fri-1", start=start, end=end,
                venue=f"Orange Church Table {lane}", area="orange church", lane=lane,
                offsite_orange=True, source_role="table_tennis",
                resource_type=POD_RESOURCE_TYPE_TABLE_TENNIS,
                lane_resource_type=POD_RESOURCE_TYPE_TABLE_TENNIS,
            )
            if re.search(r"\b(SF|SEMI|FINAL|3RD)\b", raw, re.I):
                lanes_used.add(lane)
                match_minutes.append(_to_minutes(start))
                blocks.append(_block(**common, classification=SPORT_STAGE_BLOCK,
                                     event=SPORT_TYPE["TABLE_TENNIS"]))
                continue
            if " - " in raw:
                event, sub_event, prefix = approved_games._table_tennis_category(raw, column)
                left, right = [part.strip() for part in raw.split(" - ", 1)]
                if prefix == "TT-U35-D":
                    for side in (left, right):
                        code = approved_games._team_code(approved_games._strip_table_tennis_marker(side))
                        if code and not approved_games._is_bye(code):
                            schedule_u35.add(code)
                lanes_used.add(lane)
                match_minutes.append(_to_minutes(start))
                blocks.append(_block(**common, classification=SPORT_MATCH, event=event,
                                     extra={"sub_event": sub_event}))
                continue
            classification, resource_type = classify_text(raw)
            if classification == REFERENCE:
                classification = UNRESOLVED
            common["resource_type"] = (
                POD_RESOURCE_TYPE_TABLE_TENNIS if classification in SPORT_CLASSIFICATIONS else resource_type
            )
            blocks.append(_block(**common, classification=classification))

    roster_u35 = {
        approved_games._team_code(approved_games._strip_table_tennis_marker(_clean(value)))
        for value in (ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1))
        if _clean(value).upper().startswith("(U35)")
    }
    roster_u35.discard("")
    discrepancy = {
        "roster_u35_teams": sorted(roster_u35),
        "scheduled_u35_teams": sorted(schedule_u35),
        "roster_not_scheduled": sorted(roster_u35 - schedule_u35),
        "scheduled_not_in_roster": sorted(schedule_u35 - roster_u35) if roster_u35 else [],
    }
    discrepancy["has_discrepancy"] = bool(
        discrepancy["roster_not_scheduled"] or discrepancy["scheduled_not_in_roster"]
    )
    if not roster_u35:
        warnings.append("Table Tennis workbook has no (U35) roster section; U35 discrepancy check skipped.")
    for block in blocks:
        if block["classification"] == UNRESOLVED:
            warnings.append(f"{path.name} {block['source_cell']}: unresolved cell {block['raw_text']!r}")
    grid_info = {
        "resource_type": POD_RESOURCE_TYPE_TABLE_TENNIS,
        "day": "Fri-1",
        "slot_minutes": grid,
        "lanes": len(lanes_used),
        "window_start": _clock(min(match_minutes)) if match_minutes else None,
        "window_end": _clock(max(match_minutes) + grid) if match_minutes else None,
    }
    return blocks, warnings, grid_info, discrepancy


# ---------------------------------------------------------------------------
# Venue workbook model
# ---------------------------------------------------------------------------

def _sheet_rows(ws) -> Tuple[List[str], List[Dict[str, Any]]]:
    headers = [_clean(cell.value) for cell in ws[1]]
    while headers and not headers[-1]:
        headers.pop()
    rows: List[Dict[str, Any]] = []
    for row_idx in range(2, ws.max_row + 1):
        values = {header: ws.cell(row=row_idx, column=index + 1).value
                  for index, header in enumerate(headers) if header}
        if not any(_clean(v) for v in values.values()):
            continue
        values["__row__"] = row_idx
        rows.append(values)
    return headers, rows


def load_venue_model(venue_input_path: Path) -> Dict[str, Any]:
    """Read the booked venue model.

    The booking comes from ``Booked-Venue-Input`` when an earlier execute
    created it, plus any Venue-Input row without a Booked Row ID (an operator
    addition since the last reconciliation).  Otherwise Venue-Input itself is
    the booking.
    """
    wb = load_workbook(venue_input_path, data_only=False)
    if VENUE_SHEET not in wb.sheetnames:
        raise ValueError(f"{venue_input_path} has no '{VENUE_SHEET}' tab")
    venue_headers, venue_rows = _sheet_rows(wb[VENUE_SHEET])
    adopted: List[Dict[str, Any]] = []
    if BOOKED_SHEET in wb.sheetnames:
        headers, booked = _sheet_rows(wb[BOOKED_SHEET])
        for row in venue_rows:
            if _normalize_resource_type_name(row.get("Resource Type")) and not _clean(row.get(BOOKED_ROW_ID_COLUMN)):
                adopted.append(row)
        for header in venue_headers:
            if header and header not in headers:
                headers.append(header)
        booking_source = BOOKED_SHEET
    else:
        headers, booked = venue_headers, venue_rows
        booking_source = VENUE_SHEET
    if BOOKED_ROW_ID_COLUMN not in headers:
        headers = headers + [BOOKED_ROW_ID_COLUMN]

    resource_rows = [r for r in booked if _normalize_resource_type_name(r.get("Resource Type"))]
    note_rows = [r for r in booked if not _normalize_resource_type_name(r.get("Resource Type"))]
    used_ids = {_clean(r.get(BOOKED_ROW_ID_COLUMN)) for r in resource_rows if _clean(r.get(BOOKED_ROW_ID_COLUMN))}
    next_id = 1
    for row in resource_rows + adopted:
        if _clean(row.get(BOOKED_ROW_ID_COLUMN)):
            continue
        while f"B{next_id:03d}" in used_ids:
            next_id += 1
        row[BOOKED_ROW_ID_COLUMN] = f"B{next_id:03d}"
        used_ids.add(row[BOOKED_ROW_ID_COLUMN])
    resource_rows = resource_rows + adopted

    date_day = _derive_day_labels_from_dates([r.get("Date") for r in resource_rows])
    model_rows: List[Dict[str, Any]] = []
    for row in resource_rows:
        day = _clean(row.get("Day"))
        if not day:
            parsed = _coerce_excel_date(row.get("Date"))
            day = date_day.get(parsed.date().isoformat(), "") if parsed else ""
        slot = max(1, int(float(row.get("Slot Minutes") or 60)))
        start_min = int(round(_parse_hour(row.get("Start Time")) * 60))
        last_min = int(round(_parse_hour(row.get("Last Start Time")) * 60))
        qty = max(1, int(float(row.get("Quantity") or 1)))
        model_rows.append({
            "booked_row_id": _clean(row.get(BOOKED_ROW_ID_COLUMN)),
            "raw": row,
            "resource_type": _normalize_resource_type_name(row.get("Resource Type")),
            "pod_name": _clean(row.get("Pod Name")),
            "venue_name": _clean(row.get("Venue Name")),
            "exclusive_group": _clean(row.get("Exclusive Venue Group")),
            "day": day or "Day-1",
            "quantity": qty,
            "slot_minutes": slot,
            "start": start_min,
            "end": last_min + slot,
        })
    gym_modes = {}
    if "Gym-Modes" in wb.sheetnames:
        _, gm_rows = _sheet_rows(wb["Gym-Modes"])
        gym_modes = {_clean(r.get("Gym Name")): r for r in gm_rows if _clean(r.get("Gym Name"))}
    return {
        "path": str(venue_input_path),
        "booking_source": booking_source,
        "headers": headers,
        "rows": model_rows,
        "note_rows": note_rows,
        "adopted_row_ids": [_clean(r.get(BOOKED_ROW_ID_COLUMN)) for r in adopted],
        "gym_modes": gym_modes,
        "current_venue_rows": venue_rows,
        "current_venue_headers": venue_headers,
    }


def _row_area_text(row: Mapping[str, Any]) -> str:
    return _norm(" ".join([row["pod_name"], row["venue_name"], row["exclusive_group"]]))


def _area_score(area: str, row: Mapping[str, Any]) -> int:
    """Number of distinctive header-area words found in the booked row's names."""
    row_tokens = set(_row_area_text(row).split())
    return sum(1 for tok in area.split() if tok in row_tokens)


def _is_orange(row: Mapping[str, Any]) -> bool:
    tokens = _row_area_text(row).split()
    return any(marker in tokens for marker in ORANGE_VENUE_MARKERS)


def target_rows(block: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Booked rows on the block's day that sit on the block's physical area."""
    day_rows = [r for r in rows if r["day"] == block["day"]]
    if block.get("offsite_orange") or block.get("source_role") in {"badminton", "table_tennis"}:
        wanted = block.get("lane_resource_type") or block.get("resource_type")
        return [r for r in day_rows if r["resource_type"] == wanted]
    if block.get("source_role") == "soccer":
        return [r for r in day_rows if r["resource_type"] == TEAM_RESOURCE_TYPE_SOCCER]
    if (block.get("resource_type") or block.get("lane_resource_type")) == TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE:
        # Bible Challenge has one stage per day; the Main Schedule's visual
        # area label for it drifts (e.g. a Final moved to "Practice Gym -
        # Center Court" while the only booked BC/Jeopardy-stage row that day
        # is still named for the Main Gym). Match by resource type, not area.
        return [r for r in day_rows if r["resource_type"] == TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE]
    area = block.get("area", "")
    if area:
        # Best token match: "EHS Main Gym BB1" picks the Main Gym rows even if
        # the booking never says "EHS".  A named area that matches nothing is
        # an unknown venue - never silently re-homed onto another gym.
        scores = {id(r): _area_score(area, r) for r in day_rows}
        best = max(scores.values(), default=0)
        matched = [r for r in day_rows if best and scores[id(r)] == best]
    else:
        matched = []
    if matched:
        # Widen to every mode sharing a physical gym with a matched row.
        groups = {r["exclusive_group"] for r in matched if r["exclusive_group"]}
        widened = [r for r in day_rows if r["exclusive_group"] and r["exclusive_group"] in groups]
        merged = {id(r): r for r in matched + widened}
        return list(merged.values())
    if not area and block.get("lane_resource_type"):
        return [r for r in day_rows if r["resource_type"] == block["lane_resource_type"]]
    return []


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def _lanes_affected(block: Mapping[str, Any], row: Mapping[str, Any]) -> List[int]:
    lane = block.get("lane")
    if lane is not None and block.get("lane_resource_type") == row["resource_type"]:
        return [lane] if 1 <= lane <= row["quantity"] else []
    return list(range(1, row["quantity"] + 1))


def _block_window(block: Mapping[str, Any]) -> Optional[Tuple[int, int]]:
    if not block.get("start_time") or not block.get("end_time"):
        return None
    start = _to_minutes(block["start_time"])
    end = _to_minutes(block["end_time"])
    return (start, end) if end > start else None


def _validate_blocks(
    blocks: Sequence[Dict[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    issues: Dict[str, List[Dict[str, Any]]],
) -> None:
    booked_days = {r["day"] for r in rows}
    sport_claims: Dict[Tuple[str, str, Optional[int]], List[Tuple[int, int, Mapping[str, Any]]]] = defaultdict(list)
    mode_claims: Dict[Tuple[str, str], List[Tuple[int, int, str, Mapping[str, Any]]]] = defaultdict(list)

    for block in blocks:
        window = _block_window(block)
        cls = block["classification"]
        if window is None or cls in {REFERENCE, UNRESOLVED}:
            continue
        where = f"{block['source_file']} {block['source_sheet']}!{block['source_cell']}"
        targets = target_rows(block, rows)
        block["matched_booked_rows"] = sorted({t["booked_row_id"] for t in targets})
        is_sport = cls in SPORT_CLASSIFICATIONS

        if block["day"] not in booked_days:
            if is_sport:
                issues["errors"].append(_issue(
                    "date_outside_booking",
                    f"{where}: {block['raw_text']!r} is on {block['day']}, which has no booked venue rows.",
                    source=where))
            continue
        if not targets:
            if is_sport:
                issues["errors"].append(_issue(
                    "unknown_venue",
                    f"{where}: venue {block['venue']!r} ({block.get('resource_type') or 'unknown type'}) "
                    f"does not match any booked row on {block['day']}.", source=where))
            else:
                issues["warnings"].append(_issue(
                    "unknown_venue",
                    f"{where}: {block['classification']} block on venue {block['venue']!r} does not match "
                    f"any booked row on {block['day']}; nothing to black out.", source=where))
            continue

        if block.get("offsite_orange"):
            not_orange = [t for t in targets if not _is_orange(t)]
            if not_orange:
                issues["errors"].append(_issue(
                    "offsite_mapped_onsite",
                    f"{where}: Orange Church block maps onto non-Orange booked row(s) "
                    f"{', '.join(t['booked_row_id'] for t in not_orange)}.", source=where))

        if not is_sport:
            continue

        same_type = [t for t in targets if t["resource_type"] == block.get("resource_type")]
        if not same_type:
            issues["errors"].append(_issue(
                "no_booked_mode",
                f"{where}: {block['raw_text']!r} needs a {block.get('resource_type')} but the booked area "
                f"only offers {', '.join(sorted({t['resource_type'] for t in targets}))}.", source=where))
            continue
        inside = [t for t in same_type if t["start"] <= window[0] and window[1] <= t["end"]]
        if not inside:
            issues["errors"].append(_issue(
                "time_outside_booking",
                f"{where}: {block['raw_text']!r} at {block['day']} {block['start_time']}-{block['end_time']} "
                f"falls outside every booked {block.get('resource_type')} window.", source=where))
        lane = block.get("lane")
        if lane is not None and block.get("source_role") not in {"badminton", "table_tennis"}:
            max_qty = max(t["quantity"] for t in same_type)
            if lane > max_qty:
                issues["errors"].append(_issue(
                    "capacity_overflow",
                    f"{where}: venue {block['venue']!r} is lane {lane} but only {max_qty} "
                    f"{block.get('resource_type')} unit(s) are booked.", source=where))
        # The racquet grids replace the booked slot length, so only check the rest.
        for t in ([] if block.get("source_role") in {"badminton", "table_tennis"} else inside or same_type):
            if t["slot_minutes"] and (window[1] - window[0]) % t["slot_minutes"]:
                issues["warnings"].append(_issue(
                    "slot_duration_mismatch",
                    f"{where}: block length {window[1] - window[0]} min is not a multiple of booked row "
                    f"{t['booked_row_id']} slot length {t['slot_minutes']} min.", source=where))
                break

        if cls == SPORT_MATCH:
            claim_key = (block["day"], block["venue"], lane)
            for start, end, other in sport_claims[claim_key]:
                if _overlaps(start, end, *window):
                    issues["errors"].append(_issue(
                        "overlapping_blocks",
                        f"{where}: {block['raw_text']!r} overlaps {other['raw_text']!r} "
                        f"({other['source_cell']}) on {block['venue']} {block['day']}.", source=where))
            sport_claims[claim_key].append((window[0], window[1], block))
        for t in targets:
            if not t["exclusive_group"]:
                continue
            group_key = (block["day"], t["exclusive_group"])
            for start, end, rtype, other in mode_claims[group_key]:
                if rtype != block["resource_type"] and other is not block and _overlaps(start, end, *window):
                    issues["errors"].append(_issue(
                        "gym_mode_conflict",
                        f"{where}: {block['resource_type']} use overlaps {rtype} use "
                        f"({other['source_cell']}) in exclusive gym {t['exclusive_group']} on {block['day']}.",
                        source=where))
            mode_claims[group_key].append((window[0], window[1], block["resource_type"], block))


def _row_blackouts(row: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]], rows) -> Dict[int, List[Tuple[int, int]]]:
    """Intervals to remove from each lane of one booked row."""
    out: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    for block in blocks:
        cls = block["classification"]
        if cls not in SPORT_CLASSIFICATIONS and cls not in BLACKOUT_CLASSIFICATIONS:
            continue
        if block.get("source_role") in {"badminton", "table_tennis", "soccer"}:
            continue  # handled by grid override / validation only
        window = _block_window(block)
        if window is None or block["day"] != row["day"]:
            continue
        if not any(t is row for t in target_rows(block, rows)):
            continue
        if cls in SPORT_CLASSIFICATIONS and block.get("resource_type") == row["resource_type"]:
            continue  # the approved sport keeps its own window
        for lane in _lanes_affected(block, row) if cls in BLACKOUT_CLASSIFICATIONS else range(1, row["quantity"] + 1):
            out[lane].append(window)
    return out


def _windows_for_row(row: Mapping[str, Any], blackouts: Mapping[int, List[Tuple[int, int]]]) -> List[Tuple[int, int, int]]:
    """Return (first_start, last_start, quantity) windows aligned to the row's slot grid."""
    start, end, slot, qty = row["start"], row["end"], row["slot_minutes"], row["quantity"]
    points = {start, end}
    for intervals in blackouts.values():
        for a, b in intervals:
            points.update(p for p in (a, b) if start < p < end)
    ordered = sorted(points)
    segments: List[Tuple[int, int, int]] = []
    for a, b in zip(ordered, ordered[1:]):
        open_lanes = sum(
            1 for lane in range(1, qty + 1)
            if not any(_overlaps(a, b, x, y) for x, y in blackouts.get(lane, []))
        )
        if segments and segments[-1][2] == open_lanes and segments[-1][1] == a:
            segments[-1] = (segments[-1][0], b, open_lanes)
        else:
            segments.append((a, b, open_lanes))
    windows: List[Tuple[int, int, int]] = []
    for a, b, open_lanes in segments:
        if open_lanes <= 0:
            continue
        first = start + math.ceil((a - start) / slot) * slot
        last = start + math.floor((b - slot - start) / slot) * slot
        if last >= first:
            windows.append((first, last, open_lanes))
    return windows


def _venue_row(row: Mapping[str, Any], first: int, last: int, qty: int, slot: int) -> Dict[str, Any]:
    out = {k: v for k, v in row["raw"].items() if k != "__row__"}
    out["Quantity"] = qty
    out["Start Time"] = _decimal_hours(first)
    out["Last Start Time"] = _decimal_hours(last)
    out["Slot Minutes"] = slot
    out["Available Slots"] = qty * ((last - first) // slot + 1)
    out[BOOKED_ROW_ID_COLUMN] = row["booked_row_id"]
    return out


def reconcile(
    blocks: Sequence[Dict[str, Any]],
    venue_model: Mapping[str, Any],
    grids: Sequence[Mapping[str, Any]],
    issues: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (proposed Venue-Input rows, per-booked-row change log)."""
    rows = venue_model["rows"]
    _validate_blocks(blocks, rows, issues)
    grid_by_key = {(g["day"], g["resource_type"]): g for g in grids if g.get("window_start")}

    proposed: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []
    for row in rows:
        grid = grid_by_key.get((row["day"], row["resource_type"]))
        if grid is not None:
            if not _is_orange(row):
                # Approved racquet grids are Orange-only; a same-type row elsewhere
                # that day is outside this delivery's scope and is preserved.
                windows = [(row["start"], row["end"] - row["slot_minutes"], row["quantity"])]
                slot = row["slot_minutes"]
                reason = "preserved (not the Orange Church racquet booking)"
            else:
                slot = int(grid["slot_minutes"])
                g_start, g_end = _to_minutes(grid["window_start"]), _to_minutes(grid["window_end"])
                lanes = int(grid["lanes"])
                if lanes > row["quantity"]:
                    issues["errors"].append(_issue(
                        "capacity_overflow",
                        f"{grid['resource_type']} grid uses {lanes} lane(s) but booked row "
                        f"{row['booked_row_id']} has only {row['quantity']}."))
                if g_start < row["start"] or g_end > row["end"]:
                    issues["errors"].append(_issue(
                        "time_outside_booking",
                        f"{grid['resource_type']} grid {grid['window_start']}-{grid['window_end']} extends "
                        f"outside booked row {row['booked_row_id']} "
                        f"{_clock(row['start'])}-{_clock(row['end'])}."))
                first, end = max(g_start, row["start"]), min(g_end, row["end"])
                last = first + ((end - first) // slot - 1) * slot
                qty = min(lanes, row["quantity"]) or row["quantity"]
                windows = [(first, last, qty)] if last >= first else []
                reason = f"approved {slot}-minute grid, {qty} unit(s)"
        else:
            blackouts = _row_blackouts(row, blocks, rows)
            windows = _windows_for_row(row, blackouts)
            slot = row["slot_minutes"]
            reason = "blackouts/mode locks applied" if blackouts else "unchanged"
        new_rows = [_venue_row(row, first, last, qty, slot) for first, last, qty in windows]
        proposed.extend(new_rows)
        before = (row["start"], row["end"] - row["slot_minutes"], row["quantity"], row["slot_minutes"])
        after = [(_clock(f), _clock(l), q, slot) for f, l, q in windows]
        changed = not (len(windows) == 1 and (windows[0][0], windows[0][1], windows[0][2], slot) == before)
        changes.append({
            "booked_row_id": row["booked_row_id"],
            "pod_name": row["pod_name"],
            "resource_type": row["resource_type"],
            "day": row["day"],
            "booked": {"first_start": _clock(before[0]), "last_start": _clock(before[1]),
                       "quantity": before[2], "slot_minutes": before[3]},
            "proposed": [{"first_start": f, "last_start": l, "quantity": q, "slot_minutes": s}
                         for f, l, q, s in after],
            "action": ("removed" if not windows else "split_or_changed" if changed else "preserved"),
            "reason": reason,
        })
    return proposed, changes


def _venue_output_rows(
    venue_model: Mapping[str, Any],
    proposed: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Rows for the reconciled Venue-Input tab: proposed windows, then note rows."""
    return list(proposed) + [
        {k: v for k, v in r.items() if k != "__row__"} for r in venue_model["note_rows"]
    ]


def _validate_playoff_pins(
    venue_model: Mapping[str, Any],
    proposed: Sequence[Mapping[str, Any]],
    issues: Dict[str, List[Dict[str, Any]]],
) -> int:
    """Check venue-centric Playoff-Slots pins against the proposed Venue-Input.

    Reconciliation re-grids and removes windows but leaves Playoff-Slots alone,
    so a pin that was valid against the booking can stop resolving.  The schedule
    builder rejects the whole build when that happens and export-church-teams
    then writes no schedule_input.json, so it has to be caught before --execute.

    Runs the builder's own resolver on a throwaway copy of the workbook so both
    always agree.  Game durations need the roster and are unknown here, so each
    pin is checked as one grid slot; explicit resource_id + slot pins are not
    resolved at this stage.  Returns the number of venue-centric pins checked.
    """
    builder = ScheduleWorkbookBuilder()
    wb = load_workbook(venue_model["path"], data_only=False)
    _write_table(wb[VENUE_SHEET], list(venue_model["headers"]), _venue_output_rows(venue_model, proposed))
    with tempfile.TemporaryDirectory(prefix="vaysf-reconcile-") as tmp_dir:
        candidate = Path(tmp_dir) / "venue_input.xlsx"
        wb.save(candidate)
        pins = builder._load_playoff_slots(candidate)
        venue_rows, _ = builder._load_venue_input_rows(candidate)
        gym_modes = builder._load_gym_modes(candidate)
        date_day_map = builder._load_venue_date_day_map(candidate)
    checked = sum(1 for pin in pins if not (pin.get("resource_id") and pin.get("slot")))
    try:
        builder._resolve_venue_playoff_slots(
            pins, venue_rows, date_day_map, gym_modes,
            allocator_active=bool(extract_gym_blocks(venue_rows) and gym_modes),
        )
    except ValueError as exc:
        for line in str(exc).splitlines():
            if line.startswith("  - "):
                issues["errors"].append(_issue(
                    "playoff_slot_conflict",
                    f"{line[4:]} Update this {PLAYOFF_SHEET} row to fit the reconciled "
                    f"{VENUE_SHEET} windows, or remove it."))
    return checked


# ---------------------------------------------------------------------------
# Payload / audit
# ---------------------------------------------------------------------------

def _summary(blocks: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def count(key) -> Dict[str, int]:
        return dict(sorted(Counter(str(b.get(key) or "") for b in blocks).items()))
    return {
        "by_file": count("source_file"),
        "by_venue": count("venue"),
        "by_day": count("day"),
        "by_classification": count("classification"),
        "by_action": count("action"),
    }


def build_reconciliation_payload(
    *,
    main_schedule_path: Path,
    badminton_path: Path,
    soccer_path: Path,
    table_tennis_path: Path,
    venue_input_path: Path,
    waive_table_tennis_discrepancy: bool = False,
) -> Dict[str, Any]:
    issues: Dict[str, List[Dict[str, Any]]] = {"errors": [], "warnings": []}
    sources = {
        "main_schedule": Path(main_schedule_path),
        "badminton": Path(badminton_path),
        "soccer": Path(soccer_path),
        "table_tennis": Path(table_tennis_path),
        "venue_input": Path(venue_input_path),
    }
    missing = [f"{role}: {path}" for role, path in sources.items() if not path.exists()]
    payload: Dict[str, Any] = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": {
            role: {"path": str(path), "file": path.name,
                   "sha256": file_sha256(path) if path.exists() else None}
            for role, path in sources.items()
        },
    }
    if missing:
        for item in missing:
            issues["errors"].append(_issue("missing_source", f"source workbook not found: {item}"))
        payload.update({"blocks": [], "proposed_venue_rows": [], "row_changes": [], "issues": issues,
                        "summary": {}, "table_tennis_u35": {}, "grids": []})
        return payload

    blocks: List[Dict[str, Any]] = []
    main_blocks, warns = parse_main_schedule_blocks(sources["main_schedule"])
    blocks += main_blocks
    issues["warnings"] += [_issue("unresolved_cell", w) for w in warns]
    bad_blocks, warns, bad_grid = parse_badminton_blocks(sources["badminton"])
    blocks += bad_blocks
    issues["warnings"] += [_issue("source_note", w) for w in warns]
    soc_blocks, warns = parse_soccer_blocks(sources["soccer"])
    blocks += soc_blocks
    issues["warnings"] += [_issue("source_note", w) for w in warns]
    tt_blocks, warns, tt_grid, discrepancy = parse_table_tennis_blocks(sources["table_tennis"])
    blocks += tt_blocks
    issues["warnings"] += [_issue("source_note", w) for w in warns]

    if discrepancy.get("has_discrepancy"):
        message = (
            "Table Tennis U35 roster/schedule discrepancy: roster-only "
            f"{discrepancy['roster_not_scheduled'] or 'none'}, schedule-only "
            f"{discrepancy['scheduled_not_in_roster'] or 'none'}."
        )
        if waive_table_tennis_discrepancy:
            issues["warnings"].append(_issue("source_discrepancy", message + " Explicitly waived by operator."))
        else:
            issues["errors"].append(_issue(
                "source_discrepancy",
                message + " Resolve it in the source workbook or rerun with "
                "--waive-table-tennis-discrepancy after operator approval."))

    venue_model = load_venue_model(sources["venue_input"])
    grids = [bad_grid, tt_grid]
    proposed, changes = reconcile(blocks, venue_model, grids, issues)
    playoff_pins_checked = _validate_playoff_pins(venue_model, proposed, issues)

    # De-duplicate identical issue messages (one bad block can hit several rows).
    for level in ("errors", "warnings"):
        seen: set = set()
        unique = []
        for item in issues[level]:
            if item["message"] not in seen:
                seen.add(item["message"])
                unique.append(item)
        issues[level] = unique

    payload.update({
        "booking_source": venue_model["booking_source"],
        "adopted_booked_rows": venue_model["adopted_row_ids"],
        "grids": grids,
        "table_tennis_u35": discrepancy,
        "blocks": blocks,
        "proposed_venue_rows": proposed,
        "row_changes": changes,
        "issues": issues,
        "summary": {
            **_summary(blocks),
            "booked_rows": len(venue_model["rows"]),
            "proposed_rows": len(proposed),
            "rows_changed": sum(1 for c in changes if c["action"] != "preserved"),
            "unresolved_cells": sum(1 for b in blocks if b["classification"] == UNRESOLVED),
            "errors": len(issues["errors"]),
            "warnings": len(issues["warnings"]),
        },
        "playoff_slots": {
            "action": "preserved",
            "note": "Stage blocks lock gym modes only; Playoff-Slots rows are left untouched.",
            "pins_checked": playoff_pins_checked,
            "stage_blocks": [
                {k: b.get(k) for k in ("source_cell", "raw_text", "day", "start_time", "end_time", "venue")}
                for b in blocks if b["classification"] == SPORT_STAGE_BLOCK
            ],
        },
        "_venue_model": venue_model,
    })
    return payload


def audit_json(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def write_audit(payload: Mapping[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit_json(payload), indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8")


def summarize_payload_for_log(payload: Mapping[str, Any]) -> List[str]:
    summary = payload.get("summary") or {}
    return [
        "approved schedule reconciliation: "
        f"{len(payload.get('blocks') or [])} operational block(s) parsed; "
        f"{summary.get('booked_rows', 0)} booked row(s) -> {summary.get('proposed_rows', 0)} "
        f"Venue-Input row(s); {summary.get('rows_changed', 0)} booked row(s) changed",
        "approved schedule reconciliation classifications: "
        + ", ".join(f"{k}={v}" for k, v in (summary.get("by_classification") or {}).items()),
        f"approved schedule reconciliation validation: {summary.get('errors', 0)} error(s), "
        f"{summary.get('warnings', 0)} warning(s), {summary.get('unresolved_cells', 0)} unresolved cell(s)",
    ]


# ---------------------------------------------------------------------------
# Workbook writer
# ---------------------------------------------------------------------------

_BLOCK_COLUMNS = (
    "source_file", "source_sheet", "source_cell", "raw_text", "day", "start_time", "end_time",
    "venue", "resource_type", "lane", "event", "classification", "action", "confidence",
    "matched_booked_rows", "referee", "note",
)


def _write_table(ws, headers: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    ws.delete_rows(1, ws.max_row)
    ws.append(list(headers))
    for row in rows:
        values = []
        for header in headers:
            value = row.get(header)
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value)
            values.append(None if value == "" else value)
        ws.append(values)


def _ensure_sheet(wb, name: str, after: Optional[str] = None):
    if name in wb.sheetnames:
        return wb[name]
    index = wb.sheetnames.index(after) + 1 if after and after in wb.sheetnames else None
    return wb.create_sheet(name, index)


def _sheet_signature(ws) -> List[Tuple[Any, ...]]:
    return [tuple(None if cell == "" else cell for cell in row) for row in ws.iter_rows(values_only=True)
            if any(cell not in (None, "") for cell in row)]


def apply_reconciliation(payload: Mapping[str, Any], venue_input_path: Path) -> Dict[str, Any]:
    """Write the reconciled workbook: backup first, atomic replace, idempotent.

    Returns {"changed": bool, "backup": path or None}.
    """
    venue_input_path = Path(venue_input_path)
    model = payload["_venue_model"]
    headers = list(model["headers"])
    wb = load_workbook(venue_input_path, data_only=False)

    booked_rows = [{k: v for k, v in r["raw"].items() if k != "__row__"} for r in model["rows"]]
    booked_rows += [{k: v for k, v in r.items() if k != "__row__"} for r in model["note_rows"]]
    venue_rows = _venue_output_rows(model, payload["proposed_venue_rows"])
    block_rows = sorted(
        payload["blocks"],
        key=lambda b: (b["source_file"], b.get("day") or "", b.get("start_time") or "", b["venue"], b["source_cell"]),
    )
    source_rows = [
        {"role": role, "file": info["file"], "sha256": info["sha256"]}
        for role, info in payload["sources"].items() if role != "venue_input"
    ]

    before = {name: _sheet_signature(wb[name]) for name in (VENUE_SHEET, BOOKED_SHEET, BLOCKS_SHEET, SOURCES_SHEET)
              if name in wb.sheetnames}

    _write_table(_ensure_sheet(wb, BOOKED_SHEET, after=VENUE_SHEET), headers, booked_rows)
    _write_table(wb[VENUE_SHEET], headers, venue_rows)
    _write_table(_ensure_sheet(wb, BLOCKS_SHEET), list(_BLOCK_COLUMNS), block_rows)
    _write_table(_ensure_sheet(wb, SOURCES_SHEET), ["role", "file", "sha256"], source_rows)

    after = {name: _sheet_signature(wb[name]) for name in (VENUE_SHEET, BOOKED_SHEET, BLOCKS_SHEET, SOURCES_SHEET)}
    if before == after:
        return {"changed": False, "backup": None}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = venue_input_path.with_name(f"{venue_input_path.stem}.backup-{stamp}{venue_input_path.suffix}")
    shutil.copy2(venue_input_path, backup)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{venue_input_path.stem}.", suffix=venue_input_path.suffix,
                                    dir=str(venue_input_path.parent))
    os.close(fd)
    try:
        wb.save(tmp_name)
        # Re-open the temp file before replacing: a workbook the loader cannot
        # read must never replace the operator's file.
        check = load_venue_model(Path(tmp_name))
        if len(check["rows"]) != len(model["rows"]):
            raise RuntimeError("reconciled workbook failed read-back validation")
        os.replace(tmp_name, venue_input_path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return {"changed": True, "backup": str(backup)}
