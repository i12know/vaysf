"""Operator-facing diagnostics for iterative schedule planning.

The solver answers "can this exact contract be scheduled?"  This module helps
operators answer the next question: which vector should we adjust before the
next attempt?
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from loguru import logger

from scheduler import build_infeasibility_diagnostics, build_resource_slots


SOLVED_STATUSES = {"OPTIMAL", "FEASIBLE"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_hhmm_minutes(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    hour, minute = text.split(":", 1)
    try:
        return int(hour) * 60 + int(minute)
    except ValueError:
        return None


def _counter_rows(counter: Counter, key_name: str) -> list[dict[str, Any]]:
    return [
        {key_name: key, "count": count}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    ]


def _solver_pool_key(item: dict[str, Any]) -> str:
    return str(item.get("solver_pool") or item.get("resource_type") or "Unspecified")


def _resource_type_by_game(schedule_input: dict[str, Any]) -> dict[str, str]:
    return {
        str(game.get("game_id") or ""): str(game.get("resource_type") or "Unspecified")
        for game in schedule_input.get("games", [])
    }


def _event_by_game(schedule_input: dict[str, Any]) -> dict[str, str]:
    return {
        str(game.get("game_id") or ""): str(game.get("event") or "Unspecified")
        for game in schedule_input.get("games", [])
    }


def _find_exclusive_group_overlaps(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find overlapping sport-mode windows inside one physical gym group.

    These overlaps are dangerous because separate solver pools can each use
    their own resources legally while the physical gym can only be in one mode
    at a time.
    """
    by_group_day: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        group = str(resource.get("exclusive_group") or "").strip()
        day = str(resource.get("day") or "").strip()
        if group and day:
            by_group_day[(group, day)].append(resource)

    grouped_overlaps: dict[tuple[str, ...], dict[str, Any]] = {}
    for (group, day), group_resources in by_group_day.items():
        ordered = sorted(
            group_resources,
            key=lambda resource: (
                str(resource.get("open_time") or ""),
                str(resource.get("close_time") or ""),
                str(resource.get("resource_type") or ""),
                str(resource.get("resource_id") or ""),
            ),
        )
        for idx, first in enumerate(ordered):
            first_type = str(first.get("resource_type") or "Unspecified")
            first_open = _parse_hhmm_minutes(first.get("open_time"))
            first_close = _parse_hhmm_minutes(first.get("close_time"))
            if first_open is None or first_close is None:
                continue
            for second in ordered[idx + 1:]:
                second_type = str(second.get("resource_type") or "Unspecified")
                if second_type == first_type:
                    continue
                second_open = _parse_hhmm_minutes(second.get("open_time"))
                second_close = _parse_hhmm_minutes(second.get("close_time"))
                if second_open is None or second_close is None:
                    continue
                if not (first_open < second_close and second_open < first_close):
                    continue

                left = (
                    first_type,
                    str(first.get("open_time") or ""),
                    str(first.get("close_time") or ""),
                )
                right = (
                    second_type,
                    str(second.get("open_time") or ""),
                    str(second.get("close_time") or ""),
                )
                if right < left:
                    first_resource = second
                    second_resource = first
                    left, right = right, left
                else:
                    first_resource = first
                    second_resource = second
                key = (group, day, *left, *right)
                row = grouped_overlaps.setdefault(
                    key,
                    {
                        "exclusive_group": group,
                        "day": day,
                        "first_resource_type": left[0],
                        "first_open_time": left[1],
                        "first_close_time": left[2],
                        "second_resource_type": right[0],
                        "second_open_time": right[1],
                        "second_close_time": right[2],
                        "overlapping_resource_pairs": 0,
                        "example_resource_ids": [],
                    },
                )
                row["overlapping_resource_pairs"] += 1
                if len(row["example_resource_ids"]) < 3:
                    row["example_resource_ids"].append(
                        [
                            str(first_resource.get("resource_id") or ""),
                            str(second_resource.get("resource_id") or ""),
                        ]
                    )

    return sorted(
        grouped_overlaps.values(),
        key=lambda row: (
            row["exclusive_group"],
            row["day"],
            row["first_open_time"],
            row["first_resource_type"],
            row["second_open_time"],
            row["second_resource_type"],
        ),
    )


def _summarize_resource_contract(
    schedule_input: dict[str, Any],
    supply: dict[str, Any],
) -> dict[str, Any]:
    """Validate the operator contract between Venue-Input, Gym-Modes, and resources."""
    resources = schedule_input.get("resources", []) or []
    gym_modes = schedule_input.get("gym_modes", {}) or {}
    gym_allocation = schedule_input.get("gym_allocation", {}) or {}
    allocation_source = str(gym_allocation.get("source") or "unknown")

    grouped_resources = [
        resource for resource in resources
        if str(resource.get("exclusive_group") or "").strip()
    ]
    grouped_names = {
        str(resource.get("exclusive_group") or "").strip()
        for resource in grouped_resources
    }
    gym_mode_names = {
        str(name).strip()
        for name in gym_modes.keys()
        if str(name).strip()
    }
    issues: list[dict[str, Any]] = []

    for overlap in supply.get("exclusive_group_overlaps", []) or []:
        issues.append(
            {
                "severity": "high",
                "code": "physical_mode_overlap",
                "message": (
                    f"{overlap['exclusive_group']} on {overlap['day']} has overlapping "
                    f"{overlap['first_resource_type']} "
                    f"{overlap['first_open_time']}-{overlap['first_close_time']} and "
                    f"{overlap['second_resource_type']} "
                    f"{overlap['second_open_time']}-{overlap['second_close_time']} windows."
                ),
            }
        )

    if allocation_source == "direct_venue_input" and grouped_names:
        reason = str(gym_allocation.get("reason") or "")
        if reason == "grouped_rows_without_gym_modes":
            message = (
                "Venue-Input has Exclusive Venue Group rows but Gym-Modes was not used; "
                "physical gym mutual exclusivity is not enforced."
            )
        else:
            message = (
                "Grouped venue rows are being used directly; confirm each physical gym "
                "has only one sport mode at a time."
            )
        issues.append(
            {
                "severity": "medium",
                "code": "direct_grouped_resources",
                "message": message,
            }
        )

    if allocation_source == "allocator":
        uncovered_groups = sorted(grouped_names - gym_mode_names)
        if uncovered_groups:
            issues.append(
                {
                    "severity": "medium",
                    "code": "exclusive_group_without_gym_modes",
                    "message": (
                        "Exclusive venue group(s) are present in resources but missing from "
                        f"Gym-Modes coverage: {', '.join(uncovered_groups)}."
                    ),
                }
            )

        direct_covered_resources = sorted(
            str(resource.get("resource_id") or "")
            for resource in grouped_resources
            if str(resource.get("exclusive_group") or "").strip() in gym_mode_names
            and not str(resource.get("resource_id") or "").startswith("GYM-")
            and not resource.get("playoff_pinned")
        )
        if direct_covered_resources:
            issues.append(
                {
                    "severity": "high",
                    "code": "direct_resource_in_allocator_group",
                    "message": (
                        "Allocator-covered gym group contains direct non-GYM resources; "
                        "these can bypass mode exclusivity: "
                        f"{', '.join(direct_covered_resources[:5])}."
                    ),
                }
            )

    if gym_mode_names and not grouped_names:
        issues.append(
            {
                "severity": "info",
                "code": "gym_modes_without_grouped_resources",
                "message": (
                    "Gym-Modes exists, but no resources carry Exclusive Venue Group metadata; "
                    "the allocator has no physical gym blocks to split."
                ),
            }
        )

    severity_rank = {"high": 3, "medium": 2, "info": 1}
    max_rank = max((severity_rank.get(issue["severity"], 0) for issue in issues), default=0)
    status = "error" if max_rank >= 3 else "warn" if max_rank >= 2 else "clean"

    return {
        "status": status,
        "allocation_source": allocation_source,
        "exclusive_group_count": len(grouped_names),
        "gym_modes_count": len(gym_mode_names),
        "issues": issues,
    }


def _summarize_demand(schedule_input: dict[str, Any]) -> dict[str, Any]:
    games = schedule_input.get("games", []) or []
    resources = schedule_input.get("resources", []) or []
    resources_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        resources_by_type[str(resource.get("resource_type") or "Unspecified")].append(resource)

    by_resource_type: dict[str, dict[str, Any]] = {}
    by_event = Counter()
    by_solver_pool = Counter()
    constrained_games = 0

    for game in games:
        resource_type = str(game.get("resource_type") or "Unspecified")
        event = str(game.get("event") or "Unspecified")
        solver_pool = _solver_pool_key(game)
        by_event[event] += 1
        by_solver_pool[solver_pool] += 1
        if game.get("earliest_slot") or game.get("latest_slot"):
            constrained_games += 1

        compatible = resources_by_type.get(resource_type, [])
        lower_bound_slots = 0
        if compatible:
            duration = _as_int(game.get("duration_minutes"), 0)
            lower_bound_slots = min(
                max(1, math.ceil(duration / max(_as_int(resource.get("slot_minutes"), 1), 1)))
                for resource in compatible
            )

        row = by_resource_type.setdefault(
            resource_type,
            {
                "resource_type": resource_type,
                "game_count": 0,
                "required_slots_lower_bound": 0,
                "events": Counter(),
                "solver_pools": Counter(),
            },
        )
        row["game_count"] += 1
        row["required_slots_lower_bound"] += lower_bound_slots
        row["events"][event] += 1
        row["solver_pools"][solver_pool] += 1

    resource_rows = []
    for row in by_resource_type.values():
        resource_rows.append(
            {
                "resource_type": row["resource_type"],
                "game_count": row["game_count"],
                "required_slots_lower_bound": row["required_slots_lower_bound"],
                "events": _counter_rows(row["events"], "event"),
                "solver_pools": _counter_rows(row["solver_pools"], "solver_pool"),
            }
        )

    resource_rows.sort(
        key=lambda row: (-row["required_slots_lower_bound"], -row["game_count"], row["resource_type"])
    )

    return {
        "total_games": len(games),
        "constrained_games": constrained_games,
        "by_resource_type": resource_rows,
        "by_event": _counter_rows(by_event, "event"),
        "by_solver_pool": _counter_rows(by_solver_pool, "solver_pool"),
    }


def _summarize_supply(schedule_input: dict[str, Any]) -> dict[str, Any]:
    resources = schedule_input.get("resources", []) or []
    blocked_slots = {
        str(resource_id): set(slots or [])
        for resource_id, slots in (schedule_input.get("blocked_slots", {}) or {}).items()
    }
    slots_by_resource = build_resource_slots(resources) if resources else {}

    by_resource_type: dict[str, dict[str, Any]] = {}
    by_solver_pool = Counter()

    for resource in resources:
        resource_type = str(resource.get("resource_type") or "Unspecified")
        solver_pool = _solver_pool_key(resource)
        resource_id = str(resource.get("resource_id") or "")
        slots = slots_by_resource.get(resource_id, [])
        blocked_count = sum(1 for slot in slots if slot in blocked_slots.get(resource_id, set()))
        row = by_resource_type.setdefault(
            resource_type,
            {
                "resource_type": resource_type,
                "resource_count": 0,
                "available_slots": 0,
                "blocked_slots": 0,
                "days": set(),
                "solver_pools": Counter(),
            },
        )
        row["resource_count"] += 1
        row["available_slots"] += max(len(slots) - blocked_count, 0)
        row["blocked_slots"] += blocked_count
        row["days"].add(str(resource.get("day") or ""))
        row["solver_pools"][solver_pool] += 1
        by_solver_pool[solver_pool] += len(slots)

    resource_rows = []
    for row in by_resource_type.values():
        resource_rows.append(
            {
                "resource_type": row["resource_type"],
                "resource_count": row["resource_count"],
                "available_slots": row["available_slots"],
                "blocked_slots": row["blocked_slots"],
                "days": sorted(day for day in row["days"] if day),
                "solver_pools": _counter_rows(row["solver_pools"], "solver_pool"),
            }
        )
    resource_rows.sort(key=lambda row: (-row["available_slots"], row["resource_type"]))

    return {
        "total_resources": len(resources),
        "by_resource_type": resource_rows,
        "slot_capacity_by_solver_pool": _counter_rows(by_solver_pool, "solver_pool"),
        "exclusive_group_overlaps": _find_exclusive_group_overlaps(resources),
    }


def _summarize_control(schedule_input: dict[str, Any]) -> dict[str, Any]:
    playoff_slots = schedule_input.get("playoff_slots", []) or []
    gym_modes = schedule_input.get("gym_modes", {}) or {}
    gym_allocation = schedule_input.get("gym_allocation", {}) or {}
    stage_counts = Counter(str(slot.get("stage") or "Unspecified") for slot in playoff_slots)
    resource_counts = Counter(str(slot.get("resource_type") or "Unspecified") for slot in playoff_slots)

    conflict_edges = schedule_input.get("team_conflicts", []) or []
    primary_edges = sum(
        1 for edge in conflict_edges if _as_int(edge.get("primary_overlap_count"), 0) > 0
    )
    secondary_edges = max(len(conflict_edges) - primary_edges, 0)

    return {
        "playoff_slots_count": len(playoff_slots),
        "playoff_slots_by_stage": _counter_rows(stage_counts, "stage"),
        "playoff_slots_by_resource_type": _counter_rows(resource_counts, "resource_type"),
        "precedence_count": len(schedule_input.get("precedence", []) or []),
        "team_conflict_edges": len(conflict_edges),
        "primary_conflict_edges": primary_edges,
        "secondary_conflict_edges": secondary_edges,
        "gym_modes_count": len(gym_modes),
        "gym_allocation": {
            "source": gym_allocation.get("source"),
            "decision_count": len(gym_allocation.get("decisions", []) or []),
            "switch_count": gym_allocation.get("switch_count"),
            "mode_shortfall": gym_allocation.get("mode_shortfall", {}) or {},
        },
    }


def _summarize_audit(
    schedule_input: dict[str, Any],
    schedule_output: dict[str, Any] | None,
) -> dict[str, Any]:
    if not schedule_output:
        return {"available": False}

    resource_type_by_game = _resource_type_by_game(schedule_input)
    event_by_game = _event_by_game(schedule_input)
    unscheduled = [str(game_id) for game_id in schedule_output.get("unscheduled", []) or []]
    unscheduled_by_resource = Counter(
        resource_type_by_game.get(game_id, "Unknown") for game_id in unscheduled
    )
    unscheduled_by_event = Counter(event_by_game.get(game_id, "Unknown") for game_id in unscheduled)
    pool_statuses = Counter(
        str(pool.get("status") or "Unknown")
        for pool in schedule_output.get("pool_results", []) or []
    )

    return {
        "available": True,
        "status": schedule_output.get("status"),
        "assigned_count": len(schedule_output.get("assignments", []) or []),
        "unscheduled_count": len(unscheduled),
        "unscheduled_by_resource_type": _counter_rows(unscheduled_by_resource, "resource_type"),
        "unscheduled_by_event": _counter_rows(unscheduled_by_event, "event"),
        "pool_statuses": _counter_rows(pool_statuses, "status"),
        "conflict_audit_summary": schedule_output.get("conflict_audit_summary", {}) or {},
    }


def _suggest_next_actions(
    diagnostics: dict[str, Any],
    capacity_diagnostics: list[dict[str, Any]],
) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    control = diagnostics["control"]
    audit = diagnostics["audit"]
    supply = diagnostics["supply"]
    resource_contract = diagnostics.get("resource_contract", {}) or {}

    for overlap in supply.get("exclusive_group_overlaps", []):
        suggestions.append(
            {
                "vector": "supply",
                "severity": "high",
                "message": (
                    f"{overlap['exclusive_group']} on {overlap['day']} has overlapping "
                    f"{overlap['first_resource_type']} "
                    f"{overlap['first_open_time']}-{overlap['first_close_time']} and "
                    f"{overlap['second_resource_type']} "
                    f"{overlap['second_open_time']}-{overlap['second_close_time']} windows. "
                    "Split or narrow venue rows so one physical gym is in only one mode at a time."
                ),
            }
        )

    for issue in resource_contract.get("issues", []) or []:
        if issue.get("code") == "physical_mode_overlap":
            continue
        suggestions.append(
            {
                "vector": "resource contract",
                "severity": str(issue.get("severity") or "info"),
                "message": str(issue.get("message") or ""),
            }
        )

    for capacity in capacity_diagnostics:
        for missing in capacity.get("missing_resource_events", []):
            suggestions.append(
                {
                    "vector": "supply",
                    "severity": "high",
                    "message": (
                        f"Add or rename {capacity['resource_type']} supply; "
                        f"{missing['game_count']} {missing['event']} game(s) have no compatible resource."
                    ),
                }
            )
        if capacity.get("shortage_slots", 0) > 0:
            suggestions.append(
                {
                    "vector": "demand/supply",
                    "severity": "high",
                    "message": (
                        f"{capacity['resource_type']} is short by "
                        f"{capacity['shortage_slots']} lower-bound slot(s); reduce games, "
                        "add resources, or widen time windows."
                    ),
                }
            )

    output_status = str(audit.get("status") or "")
    has_bad_output = bool(output_status and output_status not in SOLVED_STATUSES)
    has_unscheduled = _as_int(audit.get("unscheduled_count"), 0) > 0
    has_physical_overlaps = bool(supply.get("exclusive_group_overlaps"))
    has_healthy_solution = (
        audit.get("available")
        and output_status in SOLVED_STATUSES
        and not has_unscheduled
        and not has_physical_overlaps
    )

    gym_shortfall = control.get("gym_allocation", {}).get("mode_shortfall", {}) or {}
    for mode, shortfall in sorted(gym_shortfall.items()):
        if _as_int(shortfall, 0) <= 0:
            continue
        if has_healthy_solution:
            suggestions.append(
                {
                    "vector": "capacity note",
                    "severity": "info",
                    "message": (
                        f"{mode} estimated demand exceeds allocator supply by "
                        f"{shortfall} slot(s), but all games were scheduled."
                    ),
                }
            )
        else:
            suggestions.append(
                {
                    "vector": "gym modes",
                    "severity": "medium",
                    "message": (
                        f"Gym mode allocation reports {shortfall} missing slot(s) for {mode}; "
                        "adjust Gym-Modes or protect direct venue rows."
                    ),
                }
            )

    if (has_bad_output or has_unscheduled) and control.get("playoff_slots_count", 0):
        suggestions.append(
            {
                "vector": "fixed pins",
                "severity": "medium",
                "message": (
                    "Run one solve without Playoff-Slots, then add pins back gradually "
                    "to see whether fixed playoff rows are blocking feasible pool slots."
                ),
            }
        )

    if has_unscheduled and control.get("precedence_count", 0):
        suggestions.append(
            {
                "vector": "precedence",
                "severity": "medium",
                "message": (
                    "Review QF/Semi/Final ordering windows; precedence may be making an "
                    "otherwise roomy schedule impossible."
                ),
            }
        )

    conflict_summary = audit.get("conflict_audit_summary", {}) or {}
    remaining_conflicts = (
        _as_int(conflict_summary.get("overlapping_edges"), 0)
        + _as_int(conflict_summary.get("remaining_primary_overlap_penalty"), 0)
        + _as_int(conflict_summary.get("remaining_secondary_overlap_penalty"), 0)
    )
    if remaining_conflicts > 0:
        suggestions.append(
            {
                "vector": "conflict graph",
                "severity": "medium",
                "message": (
                    "Remaining shared-athlete conflicts exist; inspect Conflict-Audit "
                    "and consider pool assignment changes before adding more supply."
                ),
            }
        )

    if not audit.get("available"):
        suggestions.append(
            {
                "vector": "audit",
                "severity": "info",
                "message": (
                    "No schedule_output.json was supplied; run solve-schedule after "
                    "reviewing demand/supply pressure."
                ),
            }
        )

    quality_warnings = diagnostics.get("quality_warnings", []) or []
    for warning in quality_warnings:
        if warning.get("severity") == "medium":
            suggestions.append({
                "vector": "quality",
                "severity": "medium",
                "message": warning["message"],
            })

    if not suggestions:
        if not quality_warnings:
            suggestions.append({
                "vector": "quality",
                "severity": "info",
                "message": (
                    "No obvious hard pressure or quality concerns found. "
                    "Schedule looks clean."
                ),
            })
        else:
            suggestions.append({
                "vector": "quality",
                "severity": "info",
                "message": (
                    "No hard feasibility pressure found; minor quality notes are "
                    "listed in the Quality Warnings section."
                ),
            })

    return suggestions


_LATE_FINISH_MINUTES = 20 * 60  # 20:00 — flag events ending after this
_TIGHT_TURNAROUND_MINUTES = 30  # < 30 min gap between end of QF/Semi and start of next round
_VOLLEYBALL_SWITCH_MEDIUM_THRESHOLD = 4  # > 4 switches → medium; > 0 → info


def _build_quality_warnings(
    schedule_input: dict[str, Any],
    schedule_output: dict[str, Any],
) -> list[dict[str, Any]]:
    """Quality checks for a solved (FEASIBLE/OPTIMAL/PARTIAL) schedule.

    Returns warning dicts separate from hard feasibility findings.  A clean
    schedule should produce an empty list so callers are not buried in noise.

    Each dict has at minimum: ``check``, ``severity``, ``event``, ``day``,
    ``message``.
    """
    warnings: list[dict[str, Any]] = []

    status = str(schedule_output.get("status") or "")
    if status in ("INFEASIBLE", "UNKNOWN", ""):
        return warnings  # quality checks only make sense for a placed schedule

    game_meta: dict[str, dict[str, Any]] = {}
    for source in (
        schedule_input.get("games", []),
        schedule_input.get("playoff_slots", []),
        schedule_output.get("assignments", []),
    ):
        for game in source or []:
            game_id = str(game.get("game_id") or "").strip()
            if not game_id:
                continue
            game_meta.setdefault(game_id, {}).update(
                {
                    key: value
                    for key, value in game.items()
                    if value not in (None, "")
                }
            )
    res_meta: dict[str, dict[str, Any]] = {
        str(r["resource_id"]): r for r in schedule_input.get("resources", [])
    }

    def _slot_day_and_minutes(slot: str) -> tuple[str, int]:
        day, time_str = str(slot).rsplit("-", maxsplit=1)
        return day, _parse_hhmm_minutes(time_str) or 0

    # --- Check 1: Late finish by event and day ---
    # Track latest finish_minutes and the game_id responsible.
    latest_finish_by: dict[tuple[str, str], tuple[int, str]] = {}
    for asgn in schedule_output.get("assignments", []) or []:
        gid = str(asgn.get("game_id") or "")
        slot = str(asgn.get("slot") or "")
        if not gid or not slot:
            continue
        game = game_meta.get(gid, {})
        res = res_meta.get(str(asgn.get("resource_id") or ""), {})
        event = str(game.get("event") or "Unspecified")
        dur = _as_int(game.get("duration_minutes") or res.get("slot_minutes") or 60)
        day, start_min = _slot_day_and_minutes(slot)
        finish_min = start_min + dur
        key = (event, day)
        if key not in latest_finish_by or finish_min > latest_finish_by[key][0]:
            latest_finish_by[key] = (finish_min, gid)

    for (event, day), (finish_min, game_id) in sorted(latest_finish_by.items()):
        if finish_min > _LATE_FINISH_MINUTES:
            hh, mm = divmod(finish_min, 60)
            warnings.append({
                "check": "late_finish",
                "severity": "medium",
                "event": event,
                "day": day,
                "game_id": game_id,
                "latest_finish": f"{hh:02d}:{mm:02d}",
                "message": (
                    f"{event} on {day}: last game ends at {hh:02d}:{mm:02d} "
                    f"(game {game_id}). Widen the resource window earlier or "
                    "reduce games on this day."
                ),
            })

    # --- Check 2: Tight stage turnaround ---
    # Flag QF→Semi, Semi→Final, Semi→3rd edges where actual gap < threshold.
    _PLAYOFF_STAGES = {"QF", "Semi", "Final", "3rd"}
    slot_by_game = {
        str(a.get("game_id") or ""): str(a.get("slot") or "")
        for a in (schedule_output.get("assignments") or [])
    }
    for rule in schedule_input.get("precedence", []) or []:
        before_id = str(rule.get("before_game_id") or "").strip()
        after_id = str(rule.get("after_game_id") or "").strip()
        before_game = game_meta.get(before_id, {})
        after_game = game_meta.get(after_id, {})
        before_stage = str(before_game.get("stage") or "")
        after_stage = str(after_game.get("stage") or "")
        if before_stage not in _PLAYOFF_STAGES or after_stage not in _PLAYOFF_STAGES:
            continue  # only check named-stage transitions (QF/Semi/Final/3rd)
        before_slot = slot_by_game.get(before_id, "")
        after_slot = slot_by_game.get(after_id, "")
        if not before_slot or not after_slot:
            continue  # one or both games are unscheduled; not our concern here
        before_day, before_start = _slot_day_and_minutes(before_slot)
        after_day, after_start = _slot_day_and_minutes(after_slot)
        if before_day != after_day:
            continue  # cross-day gaps are fine
        before_dur = _as_int(before_game.get("duration_minutes"), 60)
        gap = after_start - (before_start + before_dur)
        if gap < _TIGHT_TURNAROUND_MINUTES:
            event = str(before_game.get("event") or after_game.get("event") or "")
            warnings.append({
                "check": "tight_turnaround",
                "severity": "medium",
                "event": event,
                "day": before_day,
                "before_game_id": before_id,
                "after_game_id": after_id,
                "gap_minutes": gap,
                "message": (
                    f"{event}: {after_stage} ({after_id}) starts {gap} min after "
                    f"{before_stage} ({before_id}) ends on {before_day}. "
                    "Add a Playoff-Slots buffer or extend the resource window."
                ),
            })

    # --- Check 3: Volleyball net-height switches ---
    total_switches = 0
    pool_detail_parts: list[str] = []
    for pr in schedule_output.get("pool_results", []) or []:
        switches = _as_int(pr.get("volleyball_adjacent_switches"), 0)
        if switches:
            total_switches += switches
            pool_detail_parts.append(f"{pr.get('resource_type', '')} ({switches})")

    if total_switches > _VOLLEYBALL_SWITCH_MEDIUM_THRESHOLD:
        warnings.append({
            "check": "volleyball_switches",
            "severity": "medium",
            "event": "Volleyball",
            "day": "",
            "switch_count": total_switches,
            "message": (
                f"Volleyball: {total_switches} adjacent net-height switch(es) "
                f"({'; '.join(pool_detail_parts)}). "
                "Adjust pool assignments to group Men/Women games consecutively."
            ),
        })
    elif total_switches > 0:
        warnings.append({
            "check": "volleyball_switches",
            "severity": "info",
            "event": "Volleyball",
            "day": "",
            "switch_count": total_switches,
            "message": (
                f"Volleyball: {total_switches} adjacent net-height switch(es). "
                "Acceptable but can be reduced via pool assignment changes."
            ),
        })

    return warnings


def build_schedule_diagnostics(
    schedule_input: dict[str, Any],
    schedule_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build demand/supply/control/audit diagnostics for one schedule attempt."""
    capacity = build_infeasibility_diagnostics(schedule_input)
    diagnostics = {
        "summary": {
            "generated_at": schedule_input.get("generated_at"),
            "game_count": len(schedule_input.get("games", []) or []),
            "resource_count": len(schedule_input.get("resources", []) or []),
            "has_schedule_output": schedule_output is not None,
        },
        "demand": _summarize_demand(schedule_input),
        "supply": _summarize_supply(schedule_input),
        "control": _summarize_control(schedule_input),
        "capacity_pressure": capacity,
        "audit": _summarize_audit(schedule_input, schedule_output),
    }
    diagnostics["resource_contract"] = _summarize_resource_contract(
        schedule_input,
        diagnostics["supply"],
    )
    diagnostics["quality_warnings"] = (
        _build_quality_warnings(schedule_input, schedule_output)
        if schedule_output is not None
        else []
    )
    diagnostics["next_actions"] = _suggest_next_actions(diagnostics, capacity)
    return diagnostics


def format_schedule_diagnostics(diagnostics: dict[str, Any]) -> list[str]:
    """Render a compact text summary for CLI logs."""
    summary = diagnostics["summary"]
    audit = diagnostics["audit"]
    lines = [
        (
            "Schedule diagnostics: "
            f"{summary['game_count']} game(s), {summary['resource_count']} resource(s), "
            f"schedule_output={'yes' if summary['has_schedule_output'] else 'no'}."
        )
    ]
    if audit.get("available"):
        lines.append(
            f"Audit: status={audit.get('status')}, assigned={audit.get('assigned_count')}, "
            f"unscheduled={audit.get('unscheduled_count')}."
        )
    contract = diagnostics.get("resource_contract", {}) or {}
    if contract:
        lines.append(
            "Resource contract: "
            f"status={contract.get('status')}, "
            f"source={contract.get('allocation_source')}, "
            f"exclusive_groups={contract.get('exclusive_group_count', 0)}, "
            f"gym_modes={contract.get('gym_modes_count', 0)}, "
            f"issues={len(contract.get('issues', []) or [])}."
        )
        for issue in contract.get("issues", []) or []:
            lines.append(
                f"Resource contract issue [{issue.get('severity')}/{issue.get('code')}]: "
                f"{issue.get('message')}"
            )
    for warning in diagnostics.get("quality_warnings", []) or []:
        lines.append(
            f"Quality [{warning.get('severity', 'info')}/{warning.get('check', '')}]: "
            f"{warning.get('message', '')}"
        )
    for action in diagnostics.get("next_actions", []):
        lines.append(
            f"Next action [{action['severity']}/{action['vector']}]: {action['message']}"
        )
    return lines


def run_diagnose_schedule(
    input_path: Path,
    schedule_output_path: Path | None = None,
    output_path: Path | None = None,
) -> int:
    """Load schedule files, log diagnostics, and optionally write a JSON report."""
    try:
        schedule_input = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error(f"diagnose-schedule: schedule_input.json not found at {input_path}")
        return 1
    except json.JSONDecodeError as exc:
        logger.error(f"diagnose-schedule: invalid JSON in {input_path}: {exc}")
        return 1

    schedule_output = None
    if schedule_output_path:
        path = Path(schedule_output_path)
        if path.exists():
            try:
                schedule_output = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                logger.error(f"diagnose-schedule: invalid JSON in {path}: {exc}")
                return 1
        else:
            logger.warning(f"diagnose-schedule: schedule output not found at {path}")

    diagnostics = build_schedule_diagnostics(schedule_input, schedule_output)
    for line in format_schedule_diagnostics(diagnostics):
        logger.info(line)

    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
        logger.info(f"Schedule diagnostics JSON written to: {output.resolve()}")

    return 0
