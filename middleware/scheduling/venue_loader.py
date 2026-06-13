"""venue_loader — venue/resource loading helpers extracted from ScheduleWorkbookBuilder.

Pure functions; no class state.  Extracted as part of Issue #152.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from scheduling.xlsx_utils import (
    _clean_excel_text,
    _coerce_excel_date,
    _derive_day_labels_from_dates,
    _float_from_excel,
    _normalize_resource_type_name,
    _parse_hour,
    _resource_id_prefix,
)


def _load_venue_input_rows(venue_input_path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Expand venue_input.xlsx into per-resource objects for schedule_input.json.

    Each row with Quantity=N emits N resource objects labelled Court-1…N or
    Table-1…N.

    Returns (rows, day_order) where day_order is a list of unique day labels
    in actual calendar date order (e.g. ['Sat-1', 'Sun-1', 'Fri-1', 'Sat-2',
    'Sun-2']).  Both are empty when the file does not exist.
    """
    if not venue_input_path.exists():
        return [], []
    try:
        df = pd.read_excel(
            venue_input_path, sheet_name="Venue-Input", engine="openpyxl"
        )
    except Exception as e:
        logger.warning(f"Could not read venue input rows from {venue_input_path}: {e}")
        return [], []

    rows: List[Dict[str, Any]] = []
    # Counter keyed by (resource_type, day) for day-aware resource IDs.
    resource_counts: Dict[tuple, int] = {}
    has_day_col = "Day" in df.columns
    date_day_map = (
        _derive_day_labels_from_dates(df["Date"].tolist())
        if "Date" in df.columns else {}
    )

    for _, row in df.iterrows():
        resource_type = _normalize_resource_type_name(row.get("Resource Type"))
        if not resource_type:
            continue
        venue_name = _clean_excel_text(row.get("Venue Name"))
        # Exclusive Venue Group: rows sharing a group value compete for the
        # same physical gym (only one mode active per time block). Optional
        # column — blank means the resource stands alone.
        exclusive_group = _clean_excel_text(
            row.get("Exclusive Venue Group")
        )
        # Day column: use explicit value when present; otherwise derive from Date.
        if has_day_col:
            day = _clean_excel_text(row.get("Day"))
        else:
            day = ""
        if not day:
            parsed_date = _coerce_excel_date(row.get("Date"))
            day = (
                date_day_map.get(parsed_date.date().isoformat(), "")
                if parsed_date else ""
            )
        if not day:
            day = "Day-1"
        qty = max(1, int(_float_from_excel(row.get("Quantity"), 1)))
        slot_min = max(1, int(_float_from_excel(row.get("Slot Minutes"), 60)))
        start = _parse_hour(row.get("Start Time"))
        last_start = _parse_hour(row.get("Last Start Time"))
        open_time = f"{int(start):02d}:{int(round((start % 1) * 60)):02d}"
        close_decimal = last_start + slot_min / 60.0
        close_time = f"{int(close_decimal):02d}:{int(round((close_decimal % 1) * 60)):02d}"

        abbrev = _resource_id_prefix(resource_type)
        count_key = (resource_type, day)
        rc = resource_counts.get(count_key, 0)

        for i in range(1, qty + 1):
            rc += 1
            label = (
                f"Table-{i}" if "table" in resource_type.lower() else f"Court-{i}"
            )
            rows.append({
                "resource_id":     f"{abbrev}-{day}-{rc}",
                "resource_type":   resource_type,
                "label":           label,
                "day":             day,
                "open_time":       open_time,
                "close_time":      close_time,
                "slot_minutes":    slot_min,
                "venue_name":      venue_name,
                "exclusive_group": exclusive_group,
            })
        resource_counts[count_key] = rc

    logger.debug(f"Loaded {len(rows)} venue resource rows from {venue_input_path}")
    # day_order preserves the insertion order from _derive_day_labels_from_dates,
    # which sorts unique dates chronologically before assigning labels — so this
    # list is in actual calendar order (e.g. Sat-1, Sun-1, Fri-1, Sat-2, Sun-2).
    day_order: List[str] = list(dict.fromkeys(date_day_map.values()))
    return rows, day_order


def _load_playoff_slots(venue_input_path: Path) -> List[Dict[str, Any]]:
    """Load pre-assigned playoff game slots from the Playoff-Slots tab in venue_input.xlsx.

    Returns an empty list (with a WARNING) if the file or tab is absent.
    Required columns: game_id, event, stage
    A row must then carry one of two placement forms (Issue #127):
      - venue-centric (preferred): gym_name + date + start_time — resolved
        against Venue-Input by _resolve_venue_playoff_slots(), so the
        operator never has to know internal resource IDs
      - explicit: resource_id + slot — copied from the generated
        Schedule-Input Resources section (override / legacy form)
    Optional columns: slot_minutes, team_a_id, team_b_id, duration_minutes
    """
    if not venue_input_path.exists():
        return []
    try:
        df = pd.read_excel(venue_input_path, sheet_name="Playoff-Slots", engine="openpyxl")
    except Exception:
        logger.warning(
            "venue_input.xlsx is present but has no 'Playoff-Slots' tab — "
            "playoff games will not appear in the schedule. "
            "Add a 'Playoff-Slots' tab to include them."
        )
        return []

    required = {"game_id", "event", "stage"}
    cols = {str(c).strip() for c in df.columns}
    missing = required - cols
    has_explicit_cols = {"resource_id", "slot"} <= cols
    has_venue_cols = {"gym_name", "date", "start_time"} <= cols
    if missing or not (has_explicit_cols or has_venue_cols):
        problem = (
            f"is missing required columns {sorted(missing)}" if missing
            else "needs either resource_id+slot or gym_name+date+start_time columns"
        )
        logger.warning(
            f"Playoff-Slots tab {problem}; "
            "playoff games will not appear in the schedule."
        )
        return []

    slots: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        game_id = _clean_excel_text(row.get("game_id"))
        if not game_id:
            continue
        entry: Dict[str, Any] = {
            "game_id":     game_id,
            "event":       _clean_excel_text(row.get("event", "")),
            "stage":       _clean_excel_text(row.get("stage", "")),
            "resource_id": _clean_excel_text(row.get("resource_id", "")),
            "slot":        _clean_excel_text(row.get("slot", "")),
        }
        for optional in ("team_a_id", "team_b_id", "duration_minutes"):
            val = row.get(optional)
            if val is not None and str(val).strip() not in ("", "nan"):
                entry[optional] = _clean_excel_text(str(val)) if optional != "duration_minutes" else int(val)

        # Venue-centric placement fields (Issue #127). Date is kept as an
        # ISO day string when parseable so _resolve_venue_playoff_slots can
        # match it against the Venue-Input date→day-label mapping; a
        # day-label like "Sun-2" is passed through verbatim.
        gym_name = _clean_excel_text(row.get("gym_name"))
        raw_date = row.get("date")
        parsed_date = _coerce_excel_date(raw_date)
        date_text = (
            parsed_date.date().isoformat() if parsed_date
            else _clean_excel_text(raw_date)
        )
        raw_start = row.get("start_time")
        if pd.isna(raw_start) or str(raw_start).strip() in ("", "nan"):
            start_text = ""
        else:
            start_decimal = _parse_hour(raw_start)
            start_text = (
                f"{int(start_decimal):02d}:"
                f"{int(round((start_decimal % 1) * 60)):02d}"
            )
        if gym_name:
            entry["gym_name"] = gym_name
        if date_text:
            entry["date"] = date_text
        if start_text:
            entry["start_time"] = start_text
        slot_minutes_val = row.get("slot_minutes")
        if slot_minutes_val is not None and str(slot_minutes_val).strip() not in ("", "nan"):
            entry["slot_minutes"] = int(slot_minutes_val)

        has_explicit = bool(entry["resource_id"] and entry["slot"])
        has_venue = bool(gym_name and date_text and start_text)
        if has_explicit or has_venue:
            slots.append(entry)
        else:
            logger.warning(
                f"Playoff-Slots row for {game_id!r} has neither a complete "
                "resource_id+slot pair nor a complete gym_name+date+start_time "
                "set; skipped."
            )
    return slots


def _load_venue_date_day_map(venue_input_path: Path) -> Dict[str, str]:
    """Map each Venue-Input date (ISO string) to its logical day label.

    Used to resolve the venue-centric Playoff-Slots `date` column against
    the same day labels the Venue-Input rows received (Issue #127).  An
    explicit `Day` column value overrides the derived label, exactly as in
    _load_venue_input_rows.  Returns an empty dict when the file, tab, or
    Date column is absent.
    """
    if not venue_input_path.exists():
        return {}
    try:
        df = pd.read_excel(
            venue_input_path, sheet_name="Venue-Input", engine="openpyxl"
        )
    except Exception:
        return {}
    if "Date" not in df.columns:
        return {}
    derived = _derive_day_labels_from_dates(df["Date"].tolist())
    has_day_col = "Day" in df.columns
    date_day_map: Dict[str, str] = {}
    for _, row in df.iterrows():
        parsed = _coerce_excel_date(row.get("Date"))
        if not parsed:
            continue
        iso = parsed.date().isoformat()
        explicit = (
            _clean_excel_text(row.get("Day"))
            if has_day_col else ""
        )
        day = explicit or derived.get(iso, "")
        if day and iso not in date_day_map:
            date_day_map[iso] = day
    return date_day_map


def _split_slot_label(slot_label: str) -> Tuple[str, str]:
    """Split a slot label like 'Sun-2-14:00' into ('Sun-2', '14:00')."""
    cleaned = str(slot_label or "").strip()
    if "-" not in cleaned:
        return "", cleaned
    day, time_part = cleaned.rsplit("-", 1)
    return day, time_part


def _last_slot_label_on_day(
    resources: List[Dict[str, Any]],
    court_type: str,
    day: str,
) -> Optional[str]:
    """Return the last valid slot label (e.g. 'Sat-2-16:00') for the given
    court_type on the given day, derived from close_time and slot_minutes
    of all matching resources.  Returns None if no matching resource exists.
    """
    best: Optional[str] = None
    for r in resources:
        if str(r.get("resource_type") or "").strip() != court_type:
            continue
        if str(r.get("day") or "").strip() != day:
            continue
        close_text = str(r.get("close_time") or "").strip()
        if ":" not in close_text:
            continue
        try:
            close_h, close_m = (int(x) for x in close_text.split(":"))
        except ValueError:
            continue
        slot_min = int(r.get("slot_minutes") or 60)
        last_start = close_h * 60 + close_m - slot_min
        if last_start < 0:
            continue
        label = f"{day}-{last_start // 60:02d}:{last_start % 60:02d}"
        if best is None or label > best:
            best = label
    return best


def _load_gym_modes(venue_input_path: Path) -> Dict[str, Dict[str, int]]:
    """Load per-gym mode capacities from the Gym-Modes tab in venue_input.xlsx.

    A gym that can be configured as either-or (e.g. 1 Basketball Court OR
    2 Volleyball Courts per time block) records both options on one row.
    Returns {gym_name: {resource_type: courts_per_block}}; 0 means that
    mode is not available in that gym.

    Returns an empty dict (with a WARNING) if the file or tab is absent —
    the schedule is still produced; the gym-mode capacity estimator simply
    has no mode data to work with.
    """
    # Maps a Gym-Modes column header to the resource_type it represents.
    mode_column_map = {
        "Basketball Courts":   "Basketball Court",
        "Volleyball Courts":   "Volleyball Court",
        "Badminton Courts":    "Badminton Court",
        "Pickleball Courts":   "Pickleball Court",
        "Tennis Courts":       "Tennis Court",
        "Table Tennis Tables": "Table Tennis Table",
        "Soccer Fields":       "Soccer Field",
    }
    if not venue_input_path.exists():
        return {}
    try:
        df = pd.read_excel(venue_input_path, sheet_name="Gym-Modes", engine="openpyxl")
    except Exception:
        logger.warning(
            "venue_input.xlsx is present but has no 'Gym-Modes' tab — "
            "gym-mode capacity estimation will be skipped. "
            "Add a 'Gym-Modes' tab to enable it."
        )
        return {}

    df = df.rename(columns=lambda c: str(c).strip())
    cols = set(df.columns)
    if "Gym Name" not in cols:
        logger.warning(
            "Gym-Modes tab is missing the 'Gym Name' column — "
            "gym-mode capacity estimation will be skipped."
        )
        return {}

    active_modes = {col: rt for col, rt in mode_column_map.items() if col in cols}
    if not active_modes:
        logger.warning(
            "Gym-Modes tab has no recognized mode columns "
            f"({sorted(mode_column_map)}); gym-mode capacity estimation "
            "will be skipped."
        )
        return {}

    gym_modes: Dict[str, Dict[str, int]] = {}
    for _, row in df.iterrows():
        gym_name = _clean_excel_text(row.get("Gym Name"))
        if not gym_name:
            continue
        capacities = {
            rt: int(_float_from_excel(row.get(col), 0))
            for col, rt in active_modes.items()
        }
        # Skip note/blank rows — a "gym" with zero capacity in every mode
        # is the documentation footer, not a real venue.
        if not any(capacities.values()):
            continue
        gym_modes[gym_name] = capacities

    logger.debug(f"Loaded {len(gym_modes)} gym mode rows from {venue_input_path}")
    return gym_modes


def _load_venue_input(venue_input_path: Path) -> Dict[str, int]:
    """Read venue_input.xlsx and return {resource_type: total_available_slots}.

    Each row may have Available Slots pre-computed (formula or number).
    If Available Slots is missing/zero, falls back to computing from
    Quantity, Start Time, Last Start Time, and Slot Minutes.
    Returns an empty dict if the file does not exist.
    """
    if not venue_input_path.exists():
        return {}
    try:
        df = pd.read_excel(venue_input_path, sheet_name="Venue-Input", engine="openpyxl")
    except Exception as e:
        logger.warning(f"Could not read venue input file {venue_input_path}: {e}")
        return {}

    totals: Dict[str, int] = {}
    for _, row in df.iterrows():
        resource_type = _normalize_resource_type_name(
            row.get("Resource Type")
        )
        if not resource_type:
            continue
        avail = row.get("Available Slots")
        if pd.isna(avail) or not avail:
            # Formula wasn't cached — compute from component columns.
            qty       = _float_from_excel(row.get("Quantity"), 0)
            start     = _parse_hour(row.get("Start Time"))
            last_start = _parse_hour(row.get("Last Start Time"))
            slot_min  = _float_from_excel(row.get("Slot Minutes"), 1)
            if slot_min > 0 and qty > 0 and last_start >= start:
                avail = qty * ((last_start - start) * 60 / slot_min + 1)
            else:
                avail = 0
        totals[resource_type] = totals.get(resource_type, 0) + int(
            _float_from_excel(avail, 0)
        )
    logger.debug(f"Loaded venue input: {totals}")
    return totals
