"""
scheduler.py — CP-SAT scheduler for VAY Sports Fest (Issue #93).

CLI:
    python main.py solve-schedule [--input path/to/schedule_input.json]

Reads  : schedule_input.json (written by export-church-teams, Issue #87/#96)
Writes : schedule_output.json to DATA_DIR (or --output path)
Exits  : 0 = OPTIMAL or FEASIBLE, all games scheduled
         1 = any games unscheduled (PARTIAL / INFEASIBLE / unroutable games)
         2 = solver timed out (UNKNOWN) — increase SCHEDULE_SOLVER_TIMEOUT
         3 = error (bad input or ortools missing)

Architecture — pool decomposition:
  Games are partitioned by resource_type and solved independently.
  A Badminton slot shortage cannot cascade into an INFEASIBLE result for Tennis or
  Gym sports.  Each pool's result lands in pool_results[]; the top-level status
  reflects the worst outcome across all pools.

Constraints implemented (per pool):
  C1  Each game assigned to exactly one (resource, start_slot).
  C2  Each (resource, slot) hosts at most one game (multi-slot aware).
  C3  No team plays two games in the same time slot.
  C4  Court-type routing — each game is assigned only to matching resource_type.
  C6  Minimum rest — no team plays in two adjacent global time slots.
  C7  Multi-slot games — a game whose duration > slot_minutes blocks consecutive slots.

Objective (per pool, six-tier lexicographic via integer dominance):
  1. Minimize primary shared-athlete conflicts — two teams share an athlete
     whose primary sport is one of the two events (near-hard constraint).
  2. Minimize secondary shared-athlete conflicts — same collision but the
     athlete's primary sport is a third event (soft penalty).
  3. Minimize the maximum number of games on any single day (spread) —
     distributes pool-play games evenly across all available days instead
     of packing everything into the first available weekend.
  4. Minimize the index of the latest occupied global slot (makespan).
  5. For Volleyball Court pools, minimize adjacent same-court Men/Women
     switches so net-height changes are reduced.
  6. Minimize the sum of all games' global slot indices — within the spread
     and makespan constraints, prefer earlier start slots as a tiebreaker.

Each tier's weight exceeds the maximum possible total of all lower tiers
combined, so the hierarchy is enforced by arithmetic.  See
docs/SCHEDULING.md §"Solver objectives" for the full rationale and examples.

Day ordering for global slots follows weekday-then-cycle chronology
(Fri-1 < Sat-1 < Sun-1 < Fri-2 < ...), so the solver naturally prefers
earlier dates.

Out of scope (future work):
  - Cross-sport participant conflicts (a person in both Basketball and Badminton).
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from config import SCHEDULE_SOLVER_RANDOM_SEED
from schedule_contracts import (
    ScheduleContractError,
    validate_schedule_input,
    validate_schedule_output,
)

_WEEKDAY_ORDER: dict[str, int] = {
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
    "Fri": 4, "Sat": 5, "Sun": 6, "Day": 7,
}
_DEFAULT_TIMEOUT = float(os.getenv("SCHEDULE_SOLVER_TIMEOUT", "90.0"))
_NUM_SEARCH_WORKERS = int(os.getenv("SCHEDULE_SOLVER_WORKERS", "0"))  # 0 = CP-SAT auto
_OUTPUT_FILENAME = "schedule_output.json"

STATUS_OPTIMAL    = "OPTIMAL"
STATUS_FEASIBLE   = "FEASIBLE"
STATUS_PARTIAL    = "PARTIAL"
STATUS_INFEASIBLE = "INFEASIBLE"
STATUS_UNKNOWN    = "UNKNOWN"


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def load_schedule_input(path: Path) -> dict[str, Any]:
    """Load schedule_input.json and validate it against the schedule contract.

    Raises ScheduleContractError (with every violation listed) on malformed
    input; logs contract warnings for conditions the solver tolerates.
    """
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    for warning in validate_schedule_input(data):
        logger.warning(f"schedule_input contract: {warning}")
    return data


# ---------------------------------------------------------------------------
# Slot helpers
# ---------------------------------------------------------------------------

def _parse_time_minutes(time_str: str) -> int:
    """'HH:MM' → minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _slot_label_to_interval(slot_label: str, duration_min: int) -> tuple[str, int, int]:
    """Parse '{day}-HH:MM' → (day, start_min, start_min + duration_min)."""
    day = slot_label[:-6]
    start = _parse_time_minutes(slot_label[-5:])
    return (day, start, start + duration_min)


def _slot_overlaps_any(slot_label: str, slot_min: int, intervals: set[tuple]) -> bool:
    """True if slot starting at slot_label for slot_min minutes overlaps any (day,start,end)."""
    day = slot_label[:-6]
    start = _parse_time_minutes(slot_label[-5:])
    end = start + slot_min
    return any(
        day == av_day and start < av_end and end > av_start
        for (av_day, av_start, av_end) in intervals
    )


def _racquet_pool_entry_count(pool_games: list[dict[str, Any]]) -> int:
    """Return total planned entries across the active divisions in a racquet pool."""
    entries_by_division: dict[str, int] = {}
    for game in pool_games:
        division_id = str(game.get("division_id") or "").strip()
        try:
            entry_count = int(game.get("division_entry_count") or 0)
        except (TypeError, ValueError):
            entry_count = 0
        if division_id and entry_count > 0:
            entries_by_division[division_id] = max(
                entries_by_division.get(division_id, 0),
                entry_count,
            )

    if entries_by_division:
        return sum(entries_by_division.values())

    # Backward compatibility for schedule_input.json files generated before
    # division entry metadata was added.
    return len(pool_games)


def _day_chronological_key(day_label: str) -> tuple[int, int]:
    """Return (cycle, weekday_order) for chronological day sorting.

    Day labels follow 'Weekday-Cycle' (e.g. 'Fri-1', 'Sat-2', 'Sun-1').
    Sort ordering is cycle-first, then weekday within each cycle so the
    real-world chronology is preserved: Fri-1 < Sat-1 < Sun-1 < Fri-2 < ...
    Labels without a recognizable shape sort to the end (99, 99).
    Mirrors gym_allocator._day_sort_key.
    """
    cleaned = (day_label or "").strip()
    if "-" not in cleaned:
        return (99, 99)
    prefix, suffix = cleaned.split("-", 1)
    try:
        cycle = int(suffix)
    except ValueError:
        return (99, 99)
    return (cycle, _WEEKDAY_ORDER.get(prefix, 99))


def _slot_sort_key(label: str) -> tuple[int, int, int]:
    """Fallback sort key for slot labels using weekday-cycle arithmetic.

    Label format: '{day}-{HH:MM}', e.g. 'Sat-1-08:00' or 'Day-1-09:30'.
    Returns (cycle, weekday_order, time_in_minutes).

    NOTE: This produces a reasonable ordering when all days in a cycle fall
    in the same calendar week (Mon–Sun). It may not reflect actual chronology
    when the schedule spans non-contiguous days (e.g. a tournament that uses
    Sat-1/Sun-1 one weekend and Fri-1 the following weekend). For accurate
    ordering, provide 'day_order' in schedule_input so the solver can use
    real calendar dates instead.
    """
    day, time = _parse_slot_label(label)
    h, m = time.split(":")
    cycle, weekday = _day_chronological_key(day)
    return (cycle, weekday, int(h) * 60 + int(m))


_SLOT_LABEL_RE = re.compile(r"^(?P<day>.+)-(?P<time>\d{2}:\d{2})(?:-.+)?$")


def _parse_slot_label(label: str) -> tuple[str, str]:
    """Return (day_key, HH:MM) from a slot label.

    The parser accepts the current '{day}-{HH:MM}' labels and future variants
    that may append a suffix after the time, such as 'Sat-1-08:00-AM'.
    """
    match = _SLOT_LABEL_RE.match(str(label or "").strip())
    if match:
        return match.group("day"), match.group("time")
    return str(label).rsplit("-", maxsplit=1)


def _slot_day_key(label: str) -> str:
    """Return the day portion of a slot label."""
    return _parse_slot_label(label)[0]


def _normalize_conflict_edge_counts(edge: dict[str, Any]) -> dict[str, int]:
    """Normalize primary/secondary/shared counts from one conflict edge.

    Hand-edited inputs may omit `secondary_only_count` and provide only
    `shared_count` plus `primary_overlap_count`. In that case, derive the
    secondary-only count as `shared_count - primary_overlap_count`.
    """
    primary = max(int(edge.get("primary_overlap_count") or 0), 0)
    shared = edge.get("shared_count")
    shared_count = max(int(shared or 0), 0)
    secondary_only = edge.get("secondary_only_count")
    if secondary_only is None:
        secondary = max(shared_count - primary, 0)
    else:
        secondary = max(int(secondary_only or 0), 0)
    if shared is None:
        shared_count = primary + secondary
    return {
        "primary": primary,
        "secondary": secondary,
        "shared_count": shared_count,
    }


def _game_team_ids(game: dict[str, Any]) -> list[str]:
    """Return the distinct scheduled team IDs participating in one game."""
    team_ids: list[str] = []
    for key in ("team_a_id", "team_b_id", "team_c_id"):
        team_id = str(game.get(key) or "").strip()
        if team_id and team_id not in team_ids:
            team_ids.append(team_id)

    explicit_ids = game.get("team_ids") or []
    if isinstance(explicit_ids, list):
        for value in explicit_ids:
            team_id = str(value or "").strip()
            if team_id and team_id not in team_ids:
                team_ids.append(team_id)
    return team_ids


def build_resource_slots(resources: list[dict]) -> dict[str, list[str]]:
    """Return {resource_id: [slot_label, ...]} from each resource's time window.

    Slot labels follow the '{day}-{HH:MM}' convention, e.g. 'Sat-1-08:00'.
    The last slot starts at close_time - slot_minutes (close_time is exclusive).
    """
    result: dict[str, list[str]] = {}
    for res in resources:
        open_min  = _parse_time_minutes(res["open_time"])
        close_min = _parse_time_minutes(res["close_time"])
        slot_min  = res["slot_minutes"]
        day       = res["day"]
        slots: list[str] = []
        t = open_min
        while t + slot_min <= close_min:
            slots.append(f"{day}-{t // 60:02d}:{t % 60:02d}")
            t += slot_min
        result[res["resource_id"]] = slots
    return result


def _solver_pool_key(item: dict[str, Any]) -> str:
    """Return the logical solver pool key for one game/resource row."""
    return str(item.get("solver_pool") or item.get("resource_type") or "")


def build_conflict_audit(
    schedule_input: dict[str, Any],
    assignments: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Summarize whether cross-sport shared-athlete edges were separated."""
    team_conflicts = schedule_input.get("team_conflicts", []) or []
    if not team_conflicts:
        return {
            "total_edges": 0,
            "separated_edges": 0,
            "overlapping_edges": 0,
            "planning_only_edges": 0,
            "incomplete_edges": 0,
            "remaining_primary_overlap_penalty": 0,
            "remaining_secondary_overlap_penalty": 0,
        }, []

    game_meta = {game["game_id"]: game for game in schedule_input.get("games", [])}
    events_with_games = {
        str(game.get("event") or "").strip()
        for game in schedule_input.get("games", [])
        if str(game.get("event") or "").strip()
    }
    games_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in assignments:
        game = game_meta.get(assignment.get("game_id"), {})
        entry = {
            "game_id": assignment.get("game_id"),
            "event": game.get("event", ""),
            "slot": assignment.get("slot", ""),
            "resource_id": assignment.get("resource_id", ""),
            "duration_minutes": int(game.get("duration_minutes") or 60),
        }
        for team_id in _game_team_ids(game):
            games_by_team[team_id].append(entry)

    rows: list[dict[str, Any]] = []
    separated_edges = 0
    overlapping_edges = 0
    planning_only_edges = 0
    incomplete_edges = 0
    remaining_primary_overlap_penalty = 0
    remaining_secondary_overlap_penalty = 0

    for edge in team_conflicts:
        counts = _normalize_conflict_edge_counts(edge)
        team_a_id = str(edge.get("team_a_id") or "").strip()
        team_b_id = str(edge.get("team_b_id") or "").strip()
        event_a = str(edge.get("event_a") or "").strip()
        event_b = str(edge.get("event_b") or "").strip()
        team_a_games = games_by_team.get(team_a_id, [])
        team_b_games = games_by_team.get(team_b_id, [])
        overlap_pairs: list[str] = []
        for game_a in team_a_games:
            for game_b in team_b_games:
                if game_a["slot"] and game_b["slot"]:
                    iv_a = _slot_label_to_interval(game_a["slot"], game_a["duration_minutes"])
                    iv_b = _slot_label_to_interval(game_b["slot"], game_b["duration_minutes"])
                    day_a, start_a, end_a = iv_a
                    day_b, start_b, end_b = iv_b
                    if day_a == day_b and start_a < end_b and start_b < end_a:
                        overlap_pairs.append(
                            f"{game_a['game_id']} vs {game_b['game_id']} @ {game_a['slot']}"
                        )

        if event_a not in events_with_games or event_b not in events_with_games:
            status = "PlanningOnly"
            planning_only_edges += 1
        elif not team_a_games or not team_b_games:
            status = "IncompleteSchedule"
            incomplete_edges += 1
        elif overlap_pairs:
            status = "ConflictRemains"
            overlapping_edges += 1
            remaining_primary_overlap_penalty += counts["primary"]
            remaining_secondary_overlap_penalty += counts["secondary"]
        else:
            status = "SeparatedInSchedule"
            separated_edges += 1

        rows.append({
            "team_a_label": str(edge.get("team_a_label") or team_a_id),
            "event_a": event_a,
            "team_b_label": str(edge.get("team_b_label") or team_b_id),
            "event_b": event_b,
            "shared_count": counts["shared_count"],
            "primary_overlap_count": counts["primary"],
            "secondary_only_count": counts["secondary"],
            "status": status,
            "overlap_count": len(overlap_pairs),
            "scheduled_team_a_games": len(team_a_games),
            "scheduled_team_b_games": len(team_b_games),
            "shared_participant_names": ", ".join(edge.get("shared_participant_names") or []),
            "overlap_game_pairs": " | ".join(overlap_pairs),
        })

    summary = {
        "total_edges": len(rows),
        "separated_edges": separated_edges,
        "overlapping_edges": overlapping_edges,
        "planning_only_edges": planning_only_edges,
        "incomplete_edges": incomplete_edges,
        "remaining_primary_overlap_penalty": remaining_primary_overlap_penalty,
        "remaining_secondary_overlap_penalty": remaining_secondary_overlap_penalty,
    }
    return summary, rows


def _volleyball_category_for_event(event_name: str) -> str | None:
    """Return 'men' / 'women' for volleyball team events, else None."""
    normalized = str(event_name or "").strip().casefold()
    if normalized == "volleyball - men team":
        return "men"
    if normalized == "volleyball - women team":
        return "women"
    return None


def validate_playoff_slots(
    playoff_slots: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, set[str]]]]:
    """Validate manual playoff slots and return reserved solver slots by pool.

    Manual playoff rows are not re-solved, but they must still refer to real
    resources and real slot labels so the pool-play solver can reserve those
    exact court/time pairs.
    """
    if not playoff_slots:
        return [], {}

    res_by_id = {resource["resource_id"]: resource for resource in resources}
    res_slots = build_resource_slots(resources)
    reserved_by_type: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    validated: list[dict[str, Any]] = []
    seen_keys: dict[tuple[str, str], tuple[str, str]] = {}

    for playoff_slot in playoff_slots:
        game_id = str(playoff_slot.get("game_id", "")).strip() or "<unknown>"
        resource_id = str(playoff_slot.get("resource_id", "")).strip()
        slot = str(playoff_slot.get("slot", "")).strip()
        if not resource_id or not slot:
            raise ValueError(
                f"Playoff slot {game_id!r} is missing required resource_id/slot values."
            )

        resource = res_by_id.get(resource_id)
        if resource is None:
            raise ValueError(
                f"Playoff slot {game_id!r} references unknown resource_id {resource_id!r}."
            )

        resource_slots = res_slots.get(resource_id, [])
        valid_slots = set(resource_slots)
        if slot not in valid_slots:
            raise ValueError(
                f"Playoff slot {game_id!r} uses slot {slot!r}, which is not a valid slot "
                f"for resource {resource_id!r}."
            )

        duration_minutes = int(
            playoff_slot.get("duration_minutes")
            or resource.get("slot_minutes")
            or 60
        )
        slot_minutes = int(resource.get("slot_minutes") or 60)
        occupied_count = max(1, math.ceil(duration_minutes / slot_minutes))
        start_index = resource_slots.index(slot)
        occupied_slots = resource_slots[start_index : start_index + occupied_count]
        if len(occupied_slots) != occupied_count:
            raise ValueError(
                f"Playoff slot {game_id!r} ({duration_minutes} min) does not fit "
                f"resource {resource_id!r} starting at {slot!r}."
            )

        for occupied_slot in occupied_slots:
            key = (resource_id, occupied_slot)
            previous = seen_keys.get(key)
            if previous is not None:
                previous_game, previous_start = previous
                if previous_start == slot:
                    raise ValueError(
                        f"Duplicate playoff slot reservation for {resource_id!r} "
                        f"at {slot!r}: {previous_game!r} and {game_id!r}."
                    )
                raise ValueError(
                    f"Overlapping playoff slot reservations on {resource_id!r} at "
                    f"{occupied_slot!r}: {previous_game!r} and {game_id!r}."
                )
        for occupied_slot in occupied_slots:
            seen_keys[(resource_id, occupied_slot)] = (game_id, slot)

        normalized = dict(playoff_slot)
        normalized.setdefault("resource_type", resource["resource_type"])
        normalized.setdefault("duration_minutes", duration_minutes)
        validated.append(normalized)
        reserved_by_type[resource["resource_type"]][resource_id].update(
            occupied_slots
        )

    return validated, reserved_by_type


def ensure_unique_assignment_slots(assignments: list[dict[str, Any]]) -> None:
    """Raise when two assignments occupy the same (resource_id, slot) pair."""
    seen: dict[tuple[str, str], str] = {}
    for assignment in assignments:
        resource_id = assignment.get("resource_id")
        slot = assignment.get("slot")
        game_id = assignment.get("game_id", "<unknown>")
        if not resource_id or not slot:
            continue
        key = (resource_id, slot)
        previous_game = seen.get(key)
        if previous_game is not None:
            raise ValueError(
                f"Assignment collision on {resource_id!r} at {slot!r}: "
                f"{previous_game!r} and {game_id!r}."
            )
        seen[key] = game_id


def ensure_unique_assignment_game_ids(assignments: list[dict[str, Any]]) -> None:
    """Raise when the same game_id appears more than once in the final output."""
    seen: set[str] = set()
    for assignment in assignments:
        game_id = str(assignment.get("game_id") or "").strip()
        if not game_id:
            continue
        if game_id in seen:
            raise ValueError(
                f"Duplicate assignment rows for game_id {game_id!r} were produced."
            )
        seen.add(game_id)


def merge_playoff_slot_assignments(
    assignments: list[dict[str, Any]],
    playoff_slots: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Merge manual playoff slots into solver assignments, replacing same-game rows."""
    merged = [dict(row) for row in assignments]
    index_by_game_id = {
        str(row.get("game_id") or "").strip(): idx
        for idx, row in enumerate(merged)
        if str(row.get("game_id") or "").strip()
    }
    replaced = 0
    for playoff_slot in playoff_slots:
        normalized = dict(playoff_slot)
        game_id = str(normalized.get("game_id") or "").strip()
        if not game_id:
            merged.append(normalized)
            continue
        existing_idx = index_by_game_id.get(game_id)
        if existing_idx is not None:
            merged[existing_idx] = normalized
            replaced += 1
        else:
            index_by_game_id[game_id] = len(merged)
            merged.append(normalized)
    return merged, replaced


def build_infeasibility_diagnostics(schedule_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Return lower-bound capacity diagnostics for operator-facing INFEASIBLE cases.

    The diagnostics intentionally stay simple:
    - `available_slots` = total unreserved start slots available across all
      resources of a type
    - `required_slots`  = sum of the minimum slots each game would occupy on any
      compatible resource of that type

    This does not prove why every infeasible solve failed, but it does surface
    obvious shortages such as "Badminton Court needs 24 slots, only 20 exist".
    """
    games: list[dict]     = schedule_input["games"]
    resources: list[dict] = schedule_input["resources"]
    res_slots = build_resource_slots(resources)
    blocked_slots: dict[str, set[str]] = {
        resource_id: set(slots)
        for resource_id, slots in schedule_input.get("blocked_slots", {}).items()
    }

    resources_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        resources_by_type[resource["resource_type"]].append(resource)

    available_by_type: dict[str, int] = {}
    for resource_type, typed_resources in resources_by_type.items():
        available_by_type[resource_type] = sum(
            sum(
                1
                for slot in res_slots[resource["resource_id"]]
                if slot not in blocked_slots.get(resource["resource_id"], set())
            )
            for resource in typed_resources
        )

    required_by_type: dict[str, int] = defaultdict(int)
    event_rollups:    dict[tuple[str, str], dict[str, Any]] = {}
    missing_rollups:  dict[tuple[str, str], dict[str, Any]] = {}

    for game in games:
        event         = game["event"]
        resource_type = game["resource_type"]
        compatible    = resources_by_type.get(resource_type, [])

        if not compatible:
            key    = (event, resource_type)
            rollup = missing_rollups.setdefault(key, {
                "event": event, "resource_type": resource_type, "game_count": 0,
            })
            rollup["game_count"] += 1
            continue

        min_slots = min(
            max(1, math.ceil(game["duration_minutes"] / resource["slot_minutes"]))
            for resource in compatible
        )
        key    = (event, resource_type)
        rollup = event_rollups.setdefault(key, {
            "event": event, "resource_type": resource_type,
            "game_count": 0, "required_slots": 0,
        })
        rollup["game_count"]    += 1
        rollup["required_slots"] += min_slots
        required_by_type[resource_type] += min_slots

    diagnostics: list[dict[str, Any]] = []
    resource_types = sorted({
        *(rt for _, rt in event_rollups.keys()),
        *(rt for _, rt in missing_rollups.keys()),
    })

    for resource_type in resource_types:
        events = sorted(
            (r for r in event_rollups.values() if r["resource_type"] == resource_type),
            key=lambda r: (-r["required_slots"], r["event"]),
        )
        missing_events = sorted(
            (r for r in missing_rollups.values() if r["resource_type"] == resource_type),
            key=lambda r: (-r["game_count"], r["event"]),
        )
        required_slots  = required_by_type.get(resource_type, 0)
        available_slots = available_by_type.get(resource_type, 0)
        diagnostics.append({
            "resource_type":         resource_type,
            "required_slots":        required_slots,
            "available_slots":       available_slots,
            "shortage_slots":        max(required_slots - available_slots, 0),
            "events":                events,
            "missing_resource_events": missing_events,
        })

    return diagnostics


def format_infeasibility_diagnostics(diagnostics: list[dict[str, Any]]) -> list[str]:
    """Render operator-friendly lower-bound diagnostics for logging/output."""
    lines: list[str] = []
    for diagnostic in diagnostics:
        resource_type   = diagnostic["resource_type"]
        required_slots  = diagnostic["required_slots"]
        available_slots = diagnostic["available_slots"]
        shortage_slots  = diagnostic["shortage_slots"]

        for missing in diagnostic.get("missing_resource_events", []):
            lines.append(
                f"{missing['event']}: {missing['game_count']} game(s) require "
                f"{resource_type}, but 0 compatible slots are available."
            )

        if required_slots:
            if shortage_slots:
                lines.append(
                    f"{resource_type}: requires at least {required_slots} slot(s), "
                    f"but only {available_slots} slot(s) are available "
                    f"(short {shortage_slots})."
                )
            else:
                lines.append(
                    f"{resource_type}: requires at least {required_slots} slot(s); "
                    f"{available_slots} slot(s) are available."
                )

        for event in diagnostic.get("events", []):
            lines.append(
                f"  {event['event']}: {event['game_count']} game(s) would need "
                f"at least {event['required_slots']} slot(s)."
            )

    return lines


# ---------------------------------------------------------------------------
# Single-pool solver (internal)
# ---------------------------------------------------------------------------

def _solve_one_pool(
    pool_input: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Build and solve a CP-SAT model for one resource-type pool.

    pool_input must contain 'games' and 'resources' for a single resource_type.
    Optional 'blocked_slots' reserves exact (resource_id, slot) pairs for manual
    playoff games before the pool-play solver runs. Called by solve() once per pool.

    Returns a dict with keys:
        status              : 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE' | 'UNKNOWN'
        solver_wall_seconds : float
        assignments         : list of {game_id, resource_id, slot}
        unscheduled         : list of game_ids the solver could not place
        diagnostics         : (only present when status is not OPTIMAL/FEASIBLE)
                              lower-bound capacity summary for this pool
    """
    from ortools.sat.python import cp_model  # import guard

    games:     list[dict] = pool_input["games"]
    resources: list[dict] = pool_input["resources"]

    res_by_id:      dict[str, dict]      = {r["resource_id"]: r for r in resources}
    res_slots:      dict[str, list[str]] = build_resource_slots(resources)
    blocked_slots = {
        resource_id: set(slots)
        for resource_id, slots in pool_input.get("blocked_slots", {}).items()
    }

    # C4 — court-type routing (within this pool all games share one resource_type,
    # but res_by_type keeps the structure consistent with the constraint code)
    res_by_type: dict[str, list[str]] = {}
    for r in resources:
        res_by_type.setdefault(r["resource_type"], []).append(r["resource_id"])

    # Build global slot ordering for C6 (min rest) and the objective.
    # When schedule_input carries a 'day_order' list (derived from actual calendar
    # dates), use it for accurate chronological ordering.  Fall back to weekday-
    # cycle arithmetic via _slot_sort_key when day_order is absent (e.g. older
    # files or test fixtures that don't include it).
    _pool_day_order: list[str] = pool_input.get("day_order") or []
    if _pool_day_order:
        _day_idx: dict[str, int] = {d: i for i, d in enumerate(_pool_day_order)}
        _n_days = len(_pool_day_order)

        def _pool_slot_key(label: str) -> tuple[int, int]:
            day, time = _parse_slot_label(label)
            h, m = time.split(":")
            return (_day_idx.get(day, _n_days), int(h) * 60 + int(m))
    else:
        _pool_slot_key = _slot_sort_key  # type: ignore[assignment]

    all_labels: set[str] = set()
    for slots in res_slots.values():
        all_labels.update(slots)
    sorted_labels  = sorted(all_labels, key=_pool_slot_key)
    slot_to_global = {lbl: i for i, lbl in enumerate(sorted_labels)}
    sorted_days = sorted(
        {_slot_day_key(label) for label in sorted_labels},
        key=lambda day: _pool_slot_key(f"{day}-00:00"),
    )
    day_to_absolute_index = {
        day: index for index, day in enumerate(sorted_days)
    }

    def _slot_absolute_minutes(label: str) -> int:
        day, time = _parse_slot_label(label)
        hours, minutes = time.split(":")
        return (
            day_to_absolute_index[day] * 24 * 60
            + int(hours) * 60
            + int(minutes)
        )

    # Map global slot index → day prefix (e.g. "Sat-1") for C6 day-boundary guard
    global_to_day: dict[int, str] = {
        i: _slot_day_key(lbl)
        for i, lbl in enumerate(sorted_labels)
    }
    n_global       = len(sorted_labels)

    model     = cp_model.CpModel()
    game_meta = {g["game_id"]: g for g in games}

    # Decision variables: x[(gid, rid, t)] = BoolVar
    # True iff game gid starts on resource rid at slot index t.
    game_vars: dict[str, dict[tuple[str, int], Any]] = {}

    for game in games:
        gid           = game["game_id"]
        resource_type = game["resource_type"]
        duration      = game["duration_minutes"]
        compatible    = res_by_type.get(resource_type, [])
        earliest_slot = str(game.get("earliest_slot") or "").strip()
        latest_slot   = str(game.get("latest_slot") or "").strip()
        earliest_key  = _pool_slot_key(earliest_slot) if earliest_slot else None
        latest_key    = _pool_slot_key(latest_slot) if latest_slot else None

        game_vars[gid] = {}
        for rid in compatible:
            slots    = res_slots[rid]
            slot_min = res_by_id[rid]["slot_minutes"]
            # C7 — multi-slot: game occupies ceil(duration/slot_min) consecutive slots
            n_slots  = max(1, math.ceil(duration / slot_min))
            for t in range(len(slots) - n_slots + 1):
                start_label = slots[t]
                start_key = _pool_slot_key(start_label)
                if earliest_key is not None and start_key < earliest_key:
                    continue
                if latest_key is not None and start_key > latest_key:
                    continue
                occupied_labels = slots[t : t + n_slots]
                if any(
                    label in blocked_slots.get(rid, set())
                    for label in occupied_labels
                ):
                    continue
                var = model.NewBoolVar(f"x_{gid}_{rid}_{t}")
                game_vars[gid][(rid, t)] = var

        if not game_vars[gid]:
            logger.warning(f"No compatible resources for game {gid!r}; will be unscheduled")

    # C1 — each game assigned to exactly one (resource, start_slot)
    for gid, vd in game_vars.items():
        if vd:
            model.AddExactlyOne(vd.values())

    # C2 — each (resource, slot_idx) hosts at most one game (multi-slot aware)
    slot_occupancy: dict[tuple[str, int], list[Any]] = {}
    for gid, vd in game_vars.items():
        duration = game_meta[gid]["duration_minutes"]
        for (rid, t), var in vd.items():
            slot_min = res_by_id[rid]["slot_minutes"]
            n_slots  = max(1, math.ceil(duration / slot_min))
            for s in range(t, t + n_slots):
                slot_occupancy.setdefault((rid, s), []).append(var)

    for (rid, s), var_list in slot_occupancy.items():
        if len(var_list) > 1:
            model.AddAtMostOne(var_list)

    # C3 — no team plays two games in the same time slot
    team_slot_vars: dict[tuple[str, str], list[Any]] = {}
    for gid, vd in game_vars.items():
        game     = game_meta[gid]
        teams = _game_team_ids(game)
        duration = game["duration_minutes"]
        for (rid, t), var in vd.items():
            slots    = res_slots[rid]
            slot_min = res_by_id[rid]["slot_minutes"]
            n_slots  = max(1, math.ceil(duration / slot_min))
            for s in range(t, t + n_slots):
                slot_label = slots[s]
                for team in teams:
                    team_slot_vars.setdefault((team, slot_label), []).append(var)

    for (team, slot_label), var_list in team_slot_vars.items():
        if len(var_list) > 1:
            model.AddAtMostOne(var_list)

    # C3x — cross-pool: forbid placing a game at any slot that a cross-pool
    # conflict partner is already assigned to in a previously-solved pool.
    # pool_input["cross_pool_avoidance"] = {team_id: {(day, start_min, end_min), ...}}
    # Interval-based so 60-min basketball at 08:00 blocks badminton at 08:30 as well.
    cross_pool_avoidance: dict[str, set[tuple]] = pool_input.get("cross_pool_avoidance") or {}
    if cross_pool_avoidance:
        for gid, vd in game_vars.items():
            game  = game_meta[gid]
            teams = _game_team_ids(game)
            duration = game["duration_minutes"]
            for (rid, t), var in vd.items():
                slot_min = res_by_id[rid]["slot_minutes"]
                n_slots  = max(1, math.ceil(duration / slot_min))
                if any(
                    _slot_overlaps_any(
                        res_slots[rid][s], slot_min,
                        cross_pool_avoidance.get(team, set()),
                    )
                    for s in range(t, t + n_slots)
                    for team in teams
                ):
                    model.Add(var == 0)

    precedence_rules = pool_input.get("precedence", []) or []

    # Global slot IntVars enable C5/C6. Real-time IntVars are added only when
    # precedence exists, avoiding needless search-symmetry changes in pools
    # whose behavior does not use them.
    game_global_slot: dict[str, Any] = {}
    game_start_minutes: dict[str, Any] = {}
    max_absolute_minute = max(
        (_slot_absolute_minutes(label) for label in sorted_labels),
        default=0,
    )
    for gid, vd in game_vars.items():
        if not vd:
            continue
        gv = model.NewIntVar(0, max(n_global - 1, 0), f"gslot_{gid}")
        game_global_slot[gid] = gv
        start_var = None
        if precedence_rules:
            start_var = model.NewIntVar(
                0, max_absolute_minute, f"start_minute_{gid}"
            )
            game_start_minutes[gid] = start_var
        for (rid, t), var in vd.items():
            label = res_slots[rid][t]
            model.Add(gv == slot_to_global[label]).OnlyEnforceIf(var)
            if start_var is not None:
                model.Add(
                    start_var == _slot_absolute_minutes(label)
                ).OnlyEnforceIf(var)

    # C6 — minimum rest: no team plays in two adjacent global slots
    team_global_assignments: dict[str, dict[int, list[Any]]] = {}
    for gid, vd in game_vars.items():
        game  = game_meta[gid]
        teams = _game_team_ids(game)
        for (rid, t), var in vd.items():
            label      = res_slots[rid][t]
            global_idx = slot_to_global[label]
            for team in teams:
                team_global_assignments.setdefault(team, {}).setdefault(global_idx, []).append(var)

    # pinned_game_global: {game_id: global_slot_index} for manually pinned playoff games.
    # Used below so precedence rules whose "after" side is pinned still constrain the
    # solver-assigned "before" pool game to finish early enough.
    pinned_game_global: dict[str, int] = {
        gid: slot_to_global[slot]
        for gid, slot in (pool_input.get("pinned_game_slots") or {}).items()
        if slot in slot_to_global
    }
    pinned_game_start_minutes: dict[str, int] = {
        gid: _slot_absolute_minutes(slot)
        for gid, slot in (pool_input.get("pinned_game_slots") or {}).items()
        if slot in slot_to_global
    }
    pinned_game_durations: dict[str, int] = {
        str(gid): int(duration)
        for gid, duration in (
            pool_input.get("pinned_game_durations") or {}
        ).items()
    }
    for rule in precedence_rules:
        before_game_id = str(rule.get("before_game_id") or "").strip()
        after_game_id = str(rule.get("after_game_id") or "").strip()
        if not before_game_id or not after_game_id:
            continue
        min_gap_slots = max(int(rule.get("min_gap_slots") or 1), 1)
        if before_game_id in game_global_slot and after_game_id in game_global_slot:
            # Both games are solver-assigned: standard ordering constraint.
            model.Add(
                game_global_slot[after_game_id]
                >= game_global_slot[before_game_id] + min_gap_slots
            )
            model.Add(
                game_start_minutes[after_game_id]
                >= game_start_minutes[before_game_id]
                + int(game_meta[before_game_id]["duration_minutes"])
            )
        elif before_game_id in game_global_slot and after_game_id in pinned_game_global:
            # "Before" is solver-assigned; "after" is a manually pinned playoff game.
            # Translate to an upper-bound on the pool game's slot so it must finish
            # before the pinned playoff starts.
            pinned_idx = pinned_game_global[after_game_id]
            model.Add(
                game_global_slot[before_game_id] <= pinned_idx - min_gap_slots
            )
            model.Add(
                game_start_minutes[before_game_id]
                + int(game_meta[before_game_id]["duration_minutes"])
                <= pinned_game_start_minutes[after_game_id]
            )
        elif before_game_id in pinned_game_global and after_game_id in game_global_slot:
            # "Before" is pinned; "after" is solver-assigned. Solver must place the
            # "after" game at or after the pinned "before" + min_gap.
            pinned_idx = pinned_game_global[before_game_id]
            model.Add(
                game_global_slot[after_game_id] >= pinned_idx + min_gap_slots
            )
            model.Add(
                game_start_minutes[after_game_id]
                >= pinned_game_start_minutes[before_game_id]
                + pinned_game_durations.get(before_game_id, 0)
            )
        # Skip if both are pinned (validated at merge time) or both are unknown.

    for team, by_idx in team_global_assignments.items():
        for g_idx, vars_at_g in by_idx.items():
            next_vars = by_idx.get(g_idx + 1, [])
            if not next_vars:
                continue
            # Skip cross-day pairs — overnight gap is not a "no-rest" violation
            if global_to_day.get(g_idx) != global_to_day.get(g_idx + 1):
                continue
            for v1 in vars_at_g:
                for v2 in next_vars:
                    # NOT (v1 AND v2) — at most one of adjacent-slot vars can be true
                    model.AddBoolOr([v1.Not(), v2.Not()])

    team_conflicts = pool_input.get("team_conflicts", []) or []
    game_pair_conflicts: list[dict[str, Any]] = []
    if team_conflicts:
        edge_weights: dict[frozenset[str], dict[str, Any]] = {}
        for edge in team_conflicts:
            team_a_id = str(edge.get("team_a_id") or "").strip()
            team_b_id = str(edge.get("team_b_id") or "").strip()
            if not team_a_id or not team_b_id:
                continue
            edge_weights[frozenset((team_a_id, team_b_id))] = _normalize_conflict_edge_counts(edge)

        ordered_game_ids = [g["game_id"] for g in games]
        for idx, gid_a in enumerate(ordered_game_ids):
            teams_a = [
                t for t in _game_team_ids(game_meta[gid_a])
            ]
            for gid_b in ordered_game_ids[idx + 1:]:
                teams_b = [
                    t for t in _game_team_ids(game_meta[gid_b])
                ]
                primary_weight = 0
                secondary_weight = 0
                shared_weight = 0
                for team_a_id in teams_a:
                    for team_b_id in teams_b:
                        edge = edge_weights.get(frozenset((team_a_id, team_b_id)))
                        if edge is None:
                            continue
                        primary_weight += int(edge["primary"])
                        secondary_weight += int(edge["secondary"])
                        shared_weight += int(edge["shared_count"])
                if not (primary_weight or secondary_weight or shared_weight):
                    continue
                game_pair_conflicts.append({
                    "game_a_id": gid_a,
                    "game_b_id": gid_b,
                    "primary_weight": primary_weight,
                    "secondary_weight": secondary_weight,
                    "shared_weight": shared_weight,
                })

    game_slot_occ: dict[tuple[str, str], Any] = {}
    if game_pair_conflicts:
        conflicted_game_ids = {
            pair["game_a_id"] for pair in game_pair_conflicts
        } | {
            pair["game_b_id"] for pair in game_pair_conflicts
        }
        game_slot_sources: dict[tuple[str, str], list[Any]] = {}
        for gid, vd in game_vars.items():
            if gid not in conflicted_game_ids:
                continue
            duration = game_meta[gid]["duration_minutes"]
            for (rid, t), var in vd.items():
                slots = res_slots[rid]
                slot_min = res_by_id[rid]["slot_minutes"]
                n_slots = max(1, math.ceil(duration / slot_min))
                for s in range(t, t + n_slots):
                    slot_label = slots[s]
                    game_slot_sources.setdefault((gid, slot_label), []).append(var)

        for (gid, slot_label), source_vars in game_slot_sources.items():
            occ_var = model.NewBoolVar(f"gocc_{gid}_{slot_label.replace(':', '')}")
            model.Add(sum(source_vars) == occ_var)
            game_slot_occ[(gid, slot_label)] = occ_var

    # Objective — six-tier lexicographic: conflicts > spread > makespan > VB switches > sum
    max_day_load: Any = None  # set inside block when pool spans multiple days
    if game_global_slot:
        latest = model.NewIntVar(0, max(n_global - 1, 0), "latest_slot")
        for gv in game_global_slot.values():
            model.Add(latest >= gv)
        primary_conflict_terms: list[Any] = []
        secondary_conflict_terms: list[Any] = []
        conflict_overlap_vars: list[dict[str, Any]] = []

        for pair_idx, pair in enumerate(game_pair_conflicts):
            gid_a = pair["game_a_id"]
            gid_b = pair["game_b_id"]
            for slot_label in sorted_labels:
                occ_a = game_slot_occ.get((gid_a, slot_label))
                occ_b = game_slot_occ.get((gid_b, slot_label))
                if occ_a is None or occ_b is None:
                    continue
                overlap_var = model.NewBoolVar(
                    f"xconf_{pair_idx}_{slot_label.replace(':', '')}"
                )
                model.Add(overlap_var <= occ_a)
                model.Add(overlap_var <= occ_b)
                model.Add(overlap_var >= occ_a + occ_b - 1)
                if pair["primary_weight"]:
                    primary_conflict_terms.append(pair["primary_weight"] * overlap_var)
                if pair["secondary_weight"]:
                    secondary_conflict_terms.append(pair["secondary_weight"] * overlap_var)
                conflict_overlap_vars.append({
                    "game_a_id": gid_a,
                    "game_b_id": gid_b,
                    "slot": slot_label,
                    "var": overlap_var,
                    "primary_weight": pair["primary_weight"],
                    "secondary_weight": pair["secondary_weight"],
                    "shared_weight": pair["shared_weight"],
                })
        volleyball_switch_vars: list[Any] = []
        volleyball_slot_vars: dict[tuple[str, int, str], list[Any]] = {}

        for gid, vd in game_vars.items():
            category = _volleyball_category_for_event(game_meta[gid].get("event"))
            if category is None:
                continue
            duration = game_meta[gid]["duration_minutes"]
            for (rid, t), var in vd.items():
                slot_min = res_by_id[rid]["slot_minutes"]
                n_slots  = max(1, math.ceil(duration / slot_min))
                for s in range(t, t + n_slots):
                    volleyball_slot_vars.setdefault((rid, s, category), []).append(var)

        volleyball_occ_vars: dict[tuple[str, int, str], Any] = {}
        for (rid, s, category), source_vars in volleyball_slot_vars.items():
            occ_var = model.NewBoolVar(f"vbocc_{rid}_{s}_{category}")
            model.Add(sum(source_vars) == occ_var)
            volleyball_occ_vars[(rid, s, category)] = occ_var

        for rid, slots in res_slots.items():
            for s in range(len(slots) - 1):
                current_label = slots[s]
                next_label = slots[s + 1]
                if _slot_day_key(current_label) != _slot_day_key(next_label):
                    continue

                men_current = volleyball_occ_vars.get((rid, s, "men"))
                women_current = volleyball_occ_vars.get((rid, s, "women"))
                men_next = volleyball_occ_vars.get((rid, s + 1, "men"))
                women_next = volleyball_occ_vars.get((rid, s + 1, "women"))

                if men_current is not None and women_next is not None:
                    men_to_women = model.NewBoolVar(f"vbswitch_mw_{rid}_{s}")
                    model.Add(men_to_women <= men_current)
                    model.Add(men_to_women <= women_next)
                    model.Add(men_to_women >= men_current + women_next - 1)
                    volleyball_switch_vars.append(men_to_women)

                if women_current is not None and men_next is not None:
                    women_to_men = model.NewBoolVar(f"vbswitch_wm_{rid}_{s}")
                    model.Add(women_to_men <= women_current)
                    model.Add(women_to_men <= men_next)
                    model.Add(women_to_men >= women_current + men_next - 1)
                    volleyball_switch_vars.append(women_to_men)

        # Tier 3 — spread: minimize max games scheduled on any single day.
        # Distributes pool-play games across all available days so the solver
        # does not pack everything into the first available weekend.
        all_pool_days = sorted(
            {_slot_day_key(lbl) for lbl in sorted_labels},
            key=_day_chronological_key,
        )
        day_load_vars: dict[str, Any] = {}
        if len(all_pool_days) > 1:
            for _pool_day in all_pool_days:
                _day_vars = [
                    var
                    for gid, vd in game_vars.items()
                    for (rid, t), var in vd.items()
                    if _slot_day_key(res_slots[rid][t]) == _pool_day
                ]
                if _day_vars:
                    _dload = model.NewIntVar(
                        0, len(game_global_slot), f"dayload_{_pool_day}"
                    )
                    model.Add(_dload == sum(_day_vars))
                    day_load_vars[_pool_day] = _dload

        # Activate spread only when cross-pool avoidance is present — that
        # signals another sport has claimed specific slots, so the solver needs
        # encouragement to use alternate days.  Without cross-sport pressure,
        # prefer the default pack-early behavior so games concentrate on the
        # designated day (e.g. all Table Tennis on Friday).
        spread_max = len(game_global_slot)
        if len(day_load_vars) > 1 and cross_pool_avoidance:
            max_day_load = model.NewIntVar(0, spread_max, "max_day_load")
            for _dload in day_load_vars.values():
                model.Add(max_day_load >= _dload)

        secondary_penalty_max = sum(max(entry["secondary_weight"], 0) for entry in conflict_overlap_vars)
        latest_max = max(n_global - 1, 0)
        vb_switch_max = len(volleyball_switch_vars)
        sum_slots_max = len(game_global_slot) * latest_max

        # Lexicographic objective via integer dominance.  Each higher-tier
        # weight strictly exceeds the maximum possible total of all lower tiers
        # combined, so the solver always settles a higher tier before
        # spending degrees of freedom on a lower one.
        #
        # Tier ordering (highest priority first):
        #   primary conflicts > secondary conflicts > spread (max-per-day)
        #   > latest slot > VB gender switches > sum of slot indices
        sum_slots_weight = 1
        vb_weight = sum_slots_max + 1
        latest_weight = vb_switch_max * vb_weight + sum_slots_max + 1
        spread_weight = (
            latest_max * latest_weight
            + vb_switch_max * vb_weight
            + sum_slots_max + 1
        )
        secondary_weight = (
            spread_max * spread_weight
            + latest_max * latest_weight
            + vb_switch_max * vb_weight
            + sum_slots_max + 1
        )
        primary_weight = (
            secondary_penalty_max * secondary_weight
            + spread_max * spread_weight
            + latest_max * latest_weight
            + vb_switch_max * vb_weight
            + sum_slots_max + 1
        )

        objective_terms: list[Any] = []
        if primary_conflict_terms:
            objective_terms.append(sum(primary_conflict_terms) * primary_weight)
        if secondary_conflict_terms:
            objective_terms.append(sum(secondary_conflict_terms) * secondary_weight)
        if max_day_load is not None:
            objective_terms.append(max_day_load * spread_weight)
        objective_terms.append(latest * latest_weight)
        if volleyball_switch_vars:
            objective_terms.append(sum(volleyball_switch_vars) * vb_weight)
        objective_terms.append(sum(game_global_slot.values()) * sum_slots_weight)
        model.Minimize(sum(objective_terms))

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    if _NUM_SEARCH_WORKERS > 0:
        solver.parameters.num_search_workers = _NUM_SEARCH_WORKERS
    if SCHEDULE_SOLVER_RANDOM_SEED:
        solver.parameters.random_seed = SCHEDULE_SOLVER_RANDOM_SEED
    status_code = solver.Solve(model)

    wall_time   = solver.WallTime()
    status_name = solver.StatusName(status_code)

    status_map = {
        "OPTIMAL":    STATUS_OPTIMAL,
        "FEASIBLE":   STATUS_FEASIBLE,
        "INFEASIBLE": STATUS_INFEASIBLE,
    }
    status = status_map.get(status_name, STATUS_UNKNOWN)

    assignments: list[dict] = []
    unscheduled: list[str]  = []

    if status in (STATUS_OPTIMAL, STATUS_FEASIBLE):
        for gid, vd in game_vars.items():
            assigned = False
            for (rid, t), var in vd.items():
                if solver.Value(var):
                    assignments.append({
                        "game_id":     gid,
                        "resource_id": rid,
                        "slot":        res_slots[rid][t],
                    })
                    assigned = True
                    break
            if not assigned:
                unscheduled.append(gid)
    else:
        unscheduled = [g["game_id"] for g in games]

    # If any game in this pool had no candidate placement vars, CP-SAT can still
    # report the reduced model as solved. Surface that as an infeasible pool so
    # downstream JSON/report consumers do not see "OPTIMAL" beside dropped games.
    if status in (STATUS_OPTIMAL, STATUS_FEASIBLE) and unscheduled:
        status = STATUS_INFEASIBLE

    result: dict[str, Any] = {
        "status":              status,
        "solver_wall_seconds": round(wall_time, 3),
        "assignments":         assignments,
        "unscheduled":         unscheduled,
    }
    if game_global_slot:
        result["latest_slot_index"] = (
            int(solver.Value(latest))
            if status in (STATUS_OPTIMAL, STATUS_FEASIBLE)
            else None
        )
    if max_day_load is not None:
        result["max_games_per_day"] = (
            int(solver.Value(max_day_load))
            if status in (STATUS_OPTIMAL, STATUS_FEASIBLE)
            else None
        )
    if "volleyball_switch_vars" in locals():
        result["volleyball_adjacent_switches"] = (
            int(sum(solver.Value(var) for var in volleyball_switch_vars))
            if status in (STATUS_OPTIMAL, STATUS_FEASIBLE)
            else None
        )
    if "conflict_overlap_vars" in locals():
        if status in (STATUS_OPTIMAL, STATUS_FEASIBLE):
            active_overlaps = [
                entry for entry in conflict_overlap_vars
                if solver.Value(entry["var"])
            ]
            result["cross_sport_same_slot_conflicts"] = len(active_overlaps)
            result["cross_sport_primary_penalty"] = sum(
                int(entry["primary_weight"]) for entry in active_overlaps
            )
            result["cross_sport_secondary_penalty"] = sum(
                int(entry["secondary_weight"]) for entry in active_overlaps
            )
        else:
            result["cross_sport_same_slot_conflicts"] = None
            result["cross_sport_primary_penalty"] = None
            result["cross_sport_secondary_penalty"] = None
    if status not in (STATUS_OPTIMAL, STATUS_FEASIBLE):
        result["diagnostics"] = build_infeasibility_diagnostics(pool_input)

    return result


# ---------------------------------------------------------------------------
# Public solver — decomposes by resource_type pool
# ---------------------------------------------------------------------------

def solve(
    schedule_input: dict[str, Any],
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Partition games by resource_type and solve each pool independently.

    A capacity shortage in one pool (e.g. Badminton Courts) does not cascade
    into an INFEASIBLE result for other pools (e.g. Gym Courts or Tennis).

    Returns a dict with keys:
        status              : 'OPTIMAL' | 'FEASIBLE' | 'PARTIAL' | 'INFEASIBLE' | 'UNKNOWN'
        solver_wall_seconds : float  (sum across all pools)
        assignments         : list of {game_id, resource_id, slot}  (all pools merged)
        unscheduled         : list of game_ids  (all failed pools merged)
        pool_results        : list of per-pool result dicts, each with
                              {resource_type, status, solver_wall_seconds,
                               assignments, unscheduled, diagnostics?}

    Status semantics:
        OPTIMAL    — every pool solved optimally
        FEASIBLE   — every pool solved (at least one FEASIBLE, none failed)
        PARTIAL    — at least one pool solved AND at least one pool failed
        INFEASIBLE — every pool failed (no assignments anywhere)
        UNKNOWN    — at least one pool timed out; none solved
    """
    games:     list[dict] = schedule_input["games"]
    resources: list[dict] = schedule_input["resources"]
    playoff_slots, blocked_slots_by_type = validate_playoff_slots(
        schedule_input.get("playoff_slots", []),
        resources,
    )

    # Partition resources by logical solver pool first so resource_pool_by_id is
    # available when we classify pinned playoff games below.
    resources_by_pool: dict[str, list[dict]] = {}
    for resource in resources:
        resources_by_pool.setdefault(_solver_pool_key(resource), []).append(resource)

    resource_pool_by_id = {
        resource["resource_id"]: _solver_pool_key(resource)
        for resource in resources
    }

    # Partition games by logical solver pool. Most pools still line up 1:1 with
    # resource_type; the core gym sports may opt into a shared pool via
    # schedule_input["solver_pool"] so cross-sport conflicts can be optimized
    # together without mixing their actual court types.
    #
    # pinned_game_id_to_pool: maps each game_id that appears in playoff_slots to
    # its pool key (derived from the resource_id of the pin).  Games in this set are
    # excluded from the solver model — they are treated as fixed reference points so
    # that merge_playoff_slot_assignments cannot silently overwrite a solver-chosen
    # slot with a manual pin that violates precedence.
    pinned_game_id_to_pool: dict[str, str] = {}
    for _ps in playoff_slots:
        _gid = str(_ps.get("game_id") or "").strip()
        _rid  = str(_ps.get("resource_id") or "").strip()
        if _gid and _rid:
            _pk = resource_pool_by_id.get(_rid, "")
            if _pk:
                pinned_game_id_to_pool[_gid] = _pk

    games_by_pool: dict[str, list[dict]] = {}
    for game in games:
        gid = str(game.get("game_id") or "").strip()
        if gid in pinned_game_id_to_pool:
            continue  # pinned games are fixed references, not solver-modeled
        games_by_pool.setdefault(_solver_pool_key(game), []).append(game)
    blocked_slots_by_pool: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for resource_type, blocked_by_resource in blocked_slots_by_type.items():
        for resource_id, slots in blocked_by_resource.items():
            pool_key = resource_pool_by_id.get(resource_id, resource_type)
            blocked_slots_by_pool.setdefault(pool_key, {})[resource_id] = set(slots)

    # pinned_game_slots_by_pool: {pool_key: {game_id: slot_label}} for manually
    # pinned playoff games. Passed to _solve_one_pool so precedence rules whose
    # "after" side is pinned can still constrain pool games (fix for the bug
    # where VBM pool games spilled past VBM-QF-1 start time on 2nd Saturday).
    pinned_game_slots_by_pool: dict[str, dict[str, str]] = defaultdict(dict)
    pinned_game_durations_by_pool: dict[str, dict[str, int]] = defaultdict(dict)
    for _ps in playoff_slots:
        _gid = str(_ps.get("game_id") or "").strip()
        _slot = str(_ps.get("slot") or "").strip()
        _rid  = str(_ps.get("resource_id") or "").strip()
        if _gid and _slot and _rid:
            _pk = resource_pool_by_id.get(_rid, "")
            if _pk:
                pinned_game_slots_by_pool[_pk][_gid] = _slot
                pinned_game_durations_by_pool[_pk][_gid] = int(
                    _ps.get("duration_minutes") or 0
                )

    team_conflicts = schedule_input.get("team_conflicts", []) or []
    team_conflicts_by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    precedence_by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    game_pool_by_id: dict[str, str] = {}
    for pool_key, pool_games in games_by_pool.items():
        for game in pool_games:
            game_id = str(game.get("game_id") or "").strip()
            if game_id:
                game_pool_by_id[game_id] = pool_key
    # Also register pinned games so precedence rules involving them are routed
    # to the correct pool and not silently dropped.
    for _gid, _pk in pinned_game_id_to_pool.items():
        game_pool_by_id.setdefault(_gid, _pk)
    if team_conflicts:
        game_pool_by_team: dict[str, str] = {}
        for pool_key, pool_games in games_by_pool.items():
            for game in pool_games:
                for team_id in _game_team_ids(game):
                    game_pool_by_team[team_id] = pool_key
        for edge in team_conflicts:
            team_a_id = str(edge.get("team_a_id") or "").strip()
            team_b_id = str(edge.get("team_b_id") or "").strip()
            pool_key = game_pool_by_team.get(team_a_id)
            if pool_key and pool_key == game_pool_by_team.get(team_b_id):
                team_conflicts_by_pool[pool_key].append(edge)

    for rule in schedule_input.get("precedence", []) or []:
        before_game_id = str(rule.get("before_game_id") or "").strip()
        after_game_id = str(rule.get("after_game_id") or "").strip()
        if not before_game_id or not after_game_id:
            continue
        pool_key = game_pool_by_id.get(before_game_id)
        if pool_key and pool_key == game_pool_by_id.get(after_game_id):
            precedence_by_pool[pool_key].append(rule)

    if not games_by_pool:
        return {
            "status":              STATUS_OPTIMAL,
            "solver_wall_seconds": 0.0,
            "assignments":         list(playoff_slots),
            "unscheduled":         [],
            "pool_results":        [],
            "conflict_audit_summary": {
                "total_edges": 0,
                "separated_edges": 0,
                "overlapping_edges": 0,
                "planning_only_edges": 0,
                "incomplete_edges": 0,
                "remaining_primary_overlap_penalty": 0,
                "remaining_secondary_overlap_penalty": 0,
            },
            "conflict_audit": [],
            "pod_unprotected_entries": schedule_input.get("pod_unprotected_entries", []) or [],
            "pod_validation_reconciliation": schedule_input.get("pod_validation_reconciliation") or {},
        }

    pool_results:       list[dict[str, Any]] = []
    all_assignments:    list[dict]           = []
    all_unscheduled:    list[str]            = []
    total_wall_seconds: float                = 0.0

    day_order: list[str] = schedule_input.get("day_order") or []

    # Pool solve order governs cross-pool avoidance (C3x): a pool that solves
    # later keeps its games off the slots already taken by its conflict partners
    # in earlier-solved pools.  Team sports are scheduled first; racquet/pod
    # pools solve LAST so a shared athlete's racquet game adapts around the
    # already-placed team-sport slots (Issue #158, Decision 5).  Within the
    # team tier, BC and Soccer still solve before Gym Core (default 99) so Gym
    # Core adapts to them.  Within the racquet tier (100+), more-entry pools
    # solve first (more constrained); ties broken alphabetically.
    _POOL_SOLVE_PRIORITY_FIXED: dict[str, int] = {
        "BC Station":    0,
        "Soccer Field":  1,
        # All other gym resource types fall through to 99.
    }
    _RACQUET_RESOURCE_TYPES: frozenset[str] = frozenset({
        "Tennis Court",
        "Table Tennis Table",
        "Badminton Court",
        "Pickleball Court",
    })
    _racquet_pools_present = sorted(
        [pk for pk in games_by_pool if pk in _RACQUET_RESOURCE_TYPES],
        key=lambda pk: (-_racquet_pool_entry_count(games_by_pool[pk]), pk),
    )
    _RACQUET_PRIORITY: dict[str, int] = {
        pk: 100 + i for i, pk in enumerate(_racquet_pools_present)
    }

    def _pool_sort_key(pk: str) -> tuple[int, str]:
        if pk in _POOL_SOLVE_PRIORITY_FIXED:
            return (_POOL_SOLVE_PRIORITY_FIXED[pk], pk)
        if pk in _RACQUET_PRIORITY:
            return (_RACQUET_PRIORITY[pk], pk)
        return (99, pk)

    # Build cross-pool conflict mapping:
    # cross_pool_partners[pool_key][team_id] = {partner_team_ids in other pools}
    cross_pool_partners: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if team_conflicts and "game_pool_by_team" in dir():
        pass  # game_pool_by_team already built above
    game_pool_by_team_local: dict[str, str] = {}
    for pool_key, pool_games in games_by_pool.items():
        for game in pool_games:
            for team_id in _game_team_ids(game):
                game_pool_by_team_local[team_id] = pool_key
    for edge in team_conflicts:
        ta = str(edge.get("team_a_id") or "").strip()
        tb = str(edge.get("team_b_id") or "").strip()
        pool_a = game_pool_by_team_local.get(ta)
        pool_b = game_pool_by_team_local.get(tb)
        if pool_a and pool_b and pool_a != pool_b:
            cross_pool_partners[pool_a][ta].add(tb)
            cross_pool_partners[pool_b][tb].add(ta)

    # Time intervals occupied by already-solved pools, keyed by team_id.
    # Each entry is (day, start_min, end_min); interval-based so cross-pool
    # avoidance works across resource types with different slot_minutes.
    team_occupied_slots: dict[str, set[tuple]] = defaultdict(set)

    for pool_key in sorted(games_by_pool.keys(), key=_pool_sort_key):
        # Build cross-pool avoidance for this pool's teams: intervals where their
        # cross-pool conflict partners are already assigned in solved pools.
        cross_pool_avoidance: dict[str, set[tuple]] = {}
        for team_id, partner_ids in cross_pool_partners.get(pool_key, {}).items():
            avoided: set[tuple] = set()
            for partner_id in partner_ids:
                avoided.update(team_occupied_slots.get(partner_id, set()))
            if avoided:
                cross_pool_avoidance[team_id] = avoided
        if cross_pool_avoidance:
            logger.debug(
                f"Pool {pool_key!r}: C3x avoidance for "
                f"{len(cross_pool_avoidance)} teams across "
                f"{sum(len(s) for s in cross_pool_avoidance.values())} interval-team pairs"
            )

        pool_input = {
            "games":               games_by_pool[pool_key],
            "resources":           resources_by_pool.get(pool_key, []),
            "blocked_slots":       blocked_slots_by_pool.get(pool_key, {}),
            "team_conflicts":      team_conflicts_by_pool.get(pool_key, []),
            "precedence":          precedence_by_pool.get(pool_key, []),
            "day_order":           day_order,
            "cross_pool_avoidance": cross_pool_avoidance,
            "pinned_game_slots":   pinned_game_slots_by_pool.get(pool_key, {}),
            "pinned_game_durations": pinned_game_durations_by_pool.get(
                pool_key, {}
            ),
        }
        result = _solve_one_pool(pool_input, timeout_seconds)
        result["resource_type"] = pool_key
        pool_results.append(result)
        all_assignments.extend(result["assignments"])
        all_unscheduled.extend(result["unscheduled"])
        total_wall_seconds += result["solver_wall_seconds"]

        # Record the time interval each team occupies for subsequent pools' C3x.
        _pool_game_meta = {g["game_id"]: g for g in games_by_pool[pool_key]}
        _pool_res = {r["resource_id"]: r for r in resources_by_pool.get(pool_key, [])}
        for _asgn in result["assignments"]:
            _gm = _pool_game_meta.get(str(_asgn.get("game_id") or ""), {})
            _slot = str(_asgn.get("slot") or "")
            _rid  = str(_asgn.get("resource_id") or "")
            if not _slot or not _rid:
                continue
            _res = _pool_res.get(_rid, {})
            _slot_min = int(_res.get("slot_minutes") or 60)
            _dur = int(_gm.get("duration_minutes") or _slot_min)
            _interval = _slot_label_to_interval(_slot, _dur)
            for _team in _game_team_ids(_gm):
                team_occupied_slots[_team].add(_interval)
        extra_metrics = ""
        if result.get("max_games_per_day") is not None:
            extra_metrics += f", max_games_per_day={result['max_games_per_day']}"
        if result.get("volleyball_adjacent_switches") is not None:
            extra_metrics += (
                f", volleyball_adjacent_switches={result['volleyball_adjacent_switches']}"
            )
        if result.get("cross_sport_same_slot_conflicts") is not None:
            extra_metrics += (
                f", cross_sport_same_slot_conflicts={result['cross_sport_same_slot_conflicts']}"
            )
        logger.info(
            f"Pool {pool_key!r}: status={result['status']}, "
            f"assigned={len(result['assignments'])}, "
            f"unscheduled={len(result['unscheduled'])}"
            f"{extra_metrics}"
        )

    # Aggregate status across pools
    pool_statuses = {pr["status"] for pr in pool_results}
    solved        = {STATUS_OPTIMAL, STATUS_FEASIBLE}
    if pool_statuses == {STATUS_OPTIMAL}:
        top_status = STATUS_OPTIMAL
    elif pool_statuses.issubset(solved):
        top_status = STATUS_FEASIBLE
    elif pool_statuses & solved:
        top_status = STATUS_PARTIAL
    elif STATUS_UNKNOWN in pool_statuses:
        top_status = STATUS_UNKNOWN
    else:
        top_status = STATUS_INFEASIBLE

    # Merge pre-assigned playoff slots from schedule_input into assignments.
    replaced_playoff_assignments = 0
    if playoff_slots:
        all_assignments, replaced_playoff_assignments = merge_playoff_slot_assignments(
            all_assignments,
            playoff_slots,
        )
        manual_only_count = len(playoff_slots) - replaced_playoff_assignments
        logger.info(
            f"Merged {len(playoff_slots)} pre-assigned playoff slots into output "
            f"({replaced_playoff_assignments} replaced existing modeled assignments, "
            f"{manual_only_count} manual-only rows)."
        )

    ensure_unique_assignment_slots(all_assignments)
    ensure_unique_assignment_game_ids(all_assignments)

    conflict_audit_summary, conflict_audit = build_conflict_audit(
        schedule_input,
        all_assignments,
    )

    modeled_game_ids = {
        str(game.get("game_id") or "").strip()
        for game in games
        if str(game.get("game_id") or "").strip()
    }
    assigned_game_ids = {
        str(assignment.get("game_id") or "").strip()
        for assignment in all_assignments
        if str(assignment.get("game_id") or "").strip()
    }
    modeled_assigned_count = len(assigned_game_ids & modeled_game_ids)
    manual_only_assignment_count = len(assigned_game_ids - modeled_game_ids)

    logger.info(
        f"Solver (all pools): status={top_status}, "
        f"wall_time={total_wall_seconds:.3f}s, "
        f"assigned_modeled_games={modeled_assigned_count}, "
        f"manual_playoff_only={manual_only_assignment_count}, "
        f"output_rows={len(all_assignments)}, "
        f"unscheduled={len(all_unscheduled)}, "
        f"pools={len(pool_results)}"
    )

    return {
        "status":              top_status,
        "solver_wall_seconds": round(total_wall_seconds, 3),
        "assignments":         all_assignments,
        "unscheduled":         all_unscheduled,
        "pool_results":        pool_results,
        "conflict_audit_summary": conflict_audit_summary,
        "conflict_audit":      conflict_audit,
        "pod_unprotected_entries": schedule_input.get("pod_unprotected_entries", []) or [],
        "pod_validation_reconciliation": schedule_input.get("pod_validation_reconciliation") or {},
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_solve_schedule(input_path: Path, output_path: Path) -> int:
    """Load schedule_input.json, solve, write schedule_output.json.

    Returns exit code:
        0 = every pool solved, every game scheduled
        1 = any games unscheduled (PARTIAL, INFEASIBLE, or no compatible resource)
        2 = solver timed out (UNKNOWN) — increase SCHEDULE_SOLVER_TIMEOUT env var
        3 = error (missing input, bad JSON, ortools not installed)
    """
    try:
        schedule_input = load_schedule_input(input_path)
    except ScheduleContractError as e:
        logger.error(
            f"{input_path} failed contract validation with "
            f"{len(e.errors)} error(s):"
        )
        for violation in e.errors:
            logger.error(f"  - {violation}")
        return 3
    except Exception as e:
        logger.error(f"Failed to load {input_path}: {e}")
        return 3

    logger.info(
        f"Loaded {len(schedule_input['games'])} games, "
        f"{len(schedule_input['resources'])} resources from {input_path}"
    )

    try:
        result = solve(schedule_input)
    except ImportError:
        logger.error("ortools not installed. Run: pip install ortools>=9.8")
        return 3
    except Exception as e:
        logger.error(f"Solver error: {e}", exc_info=True)
        return 3

    output = {
        "solved_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        **result,
    }

    # Self-check before writing: a contract-violating output here is a solver
    # bug (e.g. a double-booked slot), not an operator problem — refuse to
    # emit an artifact that produce-schedule would reject anyway.
    try:
        for warning in validate_schedule_output(output):
            logger.warning(f"schedule_output contract: {warning}")
    except ScheduleContractError as e:
        logger.error(
            f"Solver produced contract-violating output ({len(e.errors)} "
            "error(s)) — this is a solver bug, nothing was written:"
        )
        for violation in e.errors:
            logger.error(f"  - {violation}")
        return 3

    try:
        output_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"schedule_output.json written to {output_path}")
    except OSError as e:
        logger.error(f"Failed to write {output_path}: {e}")
        return 3

    timed_out_pools = [
        pr for pr in result["pool_results"]
        if pr["status"] == STATUS_UNKNOWN
    ]
    if timed_out_pools:
        timeout_used = os.getenv("SCHEDULE_SOLVER_TIMEOUT", "90")
        if result["status"] == STATUS_PARTIAL:
            logger.warning(
                f"PARTIAL: {len(timed_out_pools)} pool(s) timed out after "
                f"{timeout_used}s. Assignments from completed pools have been "
                "written, but the schedule is incomplete. Increase "
                "SCHEDULE_SOLVER_TIMEOUT and re-run."
            )
        else:
            logger.warning(
                f"Solver timed out after {timeout_used}s without finding a solution. "
                "This is not proven infeasible — increase SCHEDULE_SOLVER_TIMEOUT and "
                f"re-run. Current timeout: {timeout_used}s."
            )
        for pr in timed_out_pools:
            logger.error(f"  Timed-out pool: {pr['resource_type']!r}")
        return 2

    if result["status"] == STATUS_PARTIAL:
        failed = [
            pr for pr in result["pool_results"]
            if pr["status"] not in (STATUS_OPTIMAL, STATUS_FEASIBLE)
        ]
        logger.warning(
            f"PARTIAL: {len(failed)} pool(s) could not be scheduled; "
            f"{len(result['unscheduled'])} game(s) unscheduled. "
            f"Assignments for feasible pools have been written."
        )
        for pr in failed:
            logger.error(f"  Failed pool: {pr['resource_type']!r} — {pr['status']}")
            for line in format_infeasibility_diagnostics(pr.get("diagnostics", [])):
                logger.error(f"    {line}")
        return 1

    if result["status"] == STATUS_INFEASIBLE:
        logger.error("INFEASIBLE: no pools could be scheduled.")
        for pr in result["pool_results"]:
            logger.error(f"  Pool {pr['resource_type']!r}: {pr['status']}")
            for line in format_infeasibility_diagnostics(pr.get("diagnostics", [])):
                logger.error(f"    {line}")
        has_shortage = any(
            d.get("shortage_slots", 0) > 0 or d.get("missing_resource_events")
            for pr in result["pool_results"]
            for d in pr.get("diagnostics", [])
        )
        if not has_shortage:
            logger.warning(
                "No raw slot shortage detected. The infeasibility may come from "
                "same-team conflicts, stage ordering, or min-rest spacing."
            )
        return 1

    # Defensive fallback: solved statuses should not carry unscheduled games, but if
    # they ever do, keep the CLI non-zero so callers do not silently accept it.
    if result["unscheduled"]:
        logger.warning(
            f"{len(result['unscheduled'])} game(s) could not be scheduled because "
            "no compatible resource exists for their resource_type. "
            "Check that every game's resource_type matches at least one resource in "
            f"schedule_input.json. Unscheduled: {result['unscheduled']}"
        )
        return 1

    return 0
