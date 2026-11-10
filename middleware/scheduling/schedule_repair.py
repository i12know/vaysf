"""CP-SAT repair of the approved preliminary schedule (Issue #218).

CLI:
    python main.py optimize-approved-schedule --dry-run|--execute

This is a schedule-*repair* experiment, not a redesign.  It keeps every
approved matchup and the reconciled venue windows (Issue #216), treats the
human scheduler's court/time placements as the preferred baseline, and asks
CP-SAT whether moving a few preliminary games removes shared-athlete
conflicts.

Placement policy (per game):
    locked            the placement may not move
    repairable        the baseline placement is preferred but may move
    solver_controlled no baseline preference; the solver places it freely

Why one joint model instead of scheduler.solve():
    solve() decomposes by pool and hard-blocks every slot a cross-pool
    conflict partner already holds.  For repair that would make a legal
    baseline infeasible, so Gym Core, Bible Challenge and the locked context
    games are modelled together here.  The slot grid, team identity, conflict
    edge weights and edge audit all come from scheduler.py, and solve-schedule
    itself is unchanged.

Hard constraints:
    one (resource, start) per game; one game per resource slot (multi-slot
    aware); matching resource type; no team in two overlapping games;
    mutually exclusive gym modes; precedence; locked placements; no more
    back-to-back games than the baseline has; optional same-day and
    max-move-minutes envelopes.

Objective (strictly lexicographic, solved one tier at a time):
    1. primary shared-athlete conflict penalty
    2. secondary shared-athlete conflict penalty
    3. games moved to another day (only when cross-day moves are allowed)
    4. games moved at all
    5. total minutes moved   } order set by movement_priority
    6. court changes         }
    7. back-to-back games, then Volleyball Men/Women court switches
    8. a canonical tie-break so equal-quality answers are reproducible

Each tier is minimised, then frozen at its value before the next tier runs,
so a tier reported OPTIMAL is proven minimal under every constraint above.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from loguru import logger

from config import SCHEDULE_SOLVER_RANDOM_SEED, SPORT_TYPE
from schedule_contracts import ScheduleContractError, validate_schedule_output
from scheduler import (
    STATUS_FEASIBLE,
    STATUS_INFEASIBLE,
    STATUS_OPTIMAL,
    STATUS_UNKNOWN,
    _DEFAULT_TIMEOUT,
    _NUM_SEARCH_WORKERS,
    _day_chronological_key,
    _game_team_ids,
    _normalize_conflict_edge_counts,
    _parse_slot_label,
    _parse_time_minutes,
    _volleyball_category_for_event,
    build_conflict_audit,
    build_resource_slots,
)

POLICY_LOCKED = "locked"
POLICY_REPAIRABLE = "repairable"
POLICY_SOLVER_CONTROLLED = "solver_controlled"
PLACEMENT_POLICIES = (POLICY_LOCKED, POLICY_REPAIRABLE, POLICY_SOLVER_CONTROLLED)

# Stage A of the experiment: the Gym Core sports plus Bible Challenge.
DEFAULT_REPAIR_EVENTS: Tuple[str, ...] = (
    SPORT_TYPE["BASKETBALL"],
    SPORT_TYPE["VOLLEYBALL_MEN"],
    SPORT_TYPE["VOLLEYBALL_WOMEN"],
    SPORT_TYPE["BIBLE_CHALLENGE"],
)
_PRELIMINARY_STAGES = {"", "pool", "rr", "prelim", "preliminary", "round robin"}

VERDICT_ACCEPTABLE = "ACCEPTABLE"
VERDICT_MARGINAL = "MARGINAL"
VERDICT_NO_IMPROVEMENT = "NO IMPROVEMENT"
VERDICT_BASELINE_INVALID = "BASELINE INVALID"
VERDICT_NO_SOLUTION = "NO SOLUTION"

# Verdict heuristic: a label for the report, never a decision.
ACCEPTABLE_MAX_MOVE_SHARE = 0.25
ACCEPTABLE_MIN_GAIN_PER_MOVE = 1.0

MOVEMENT_PRIORITIES = ("time,court", "court,time")
REST_POLICIES = ("no_worse", "strict", "ignore")

OPTIMIZED_OUTPUT_FILENAME = "optimized_schedule_output.json"
COMPARISON_FILENAME = "optimized_schedule_comparison.json"
WORKBOOK_FILENAME_TEMPLATE = "VAYSF_Optimized_Schedule_{date}.xlsx"
PROTECTED_OUTPUT_NAMES = {
    "schedule_input.json",
    "schedule_output.json",
    "approved_schedule_games.json",
    "approved_schedule_input.json",
    "approved_schedule_output.json",
}


def default_output_path(base_dir: Path) -> Path:
    return Path(base_dir) / OPTIMIZED_OUTPUT_FILENAME


def default_comparison_path(base_dir: Path) -> Path:
    return Path(base_dir) / COMPARISON_FILENAME


def default_workbook_path(base_dir: Path) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return Path(base_dir) / WORKBOOK_FILENAME_TEMPLATE.format(date=today)


def _clean(value: Any) -> str:
    return str(value or "").strip()


# ---------------------------------------------------------------------------
# Problem construction
# ---------------------------------------------------------------------------

def _baseline_team_ids(row: Mapping[str, Any]) -> List[str]:
    team_ids: List[str] = []
    for key in ("team_a_key", "team_b_key", "team_c_key"):
        team_id = _clean(row.get(key))
        if team_id and team_id not in team_ids:
            team_ids.append(team_id)
    raw_json = row.get("team_ids_json")
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            for value in json.loads(raw_json):
                team_id = _clean(value)
                if team_id and team_id not in team_ids:
                    team_ids.append(team_id)
        except (TypeError, ValueError):
            pass
    for team_id in _game_team_ids(dict(row)):
        if team_id not in team_ids:
            team_ids.append(team_id)
    return team_ids


def _baseline_team_labels(row: Mapping[str, Any]) -> List[str]:
    labels = [
        _clean(row.get(key))
        for key in ("team_a_label", "team_b_label", "team_c_label")
    ]
    return [label for label in labels if label]


def _is_preliminary_stage(stage: Any) -> bool:
    return _clean(stage).casefold() in _PRELIMINARY_STAGES


def build_repair_problem(
    schedule_input: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    repair_events: Optional[Sequence[str]] = None,
    allow_cross_day: bool = False,
    max_move_minutes: Optional[int] = None,
    rest_window_minutes: int = 0,
) -> Dict[str, Any]:
    """Combine schedule_input.json and the approved baseline into one problem.

    Every baseline game keeps its stable id and matchup.  Events whose team
    keys cannot be matched to schedule_input team ids are *deferred*: their
    placements are carried through untouched and reported, never guessed at.
    Raises ValueError when a requested repair event cannot be evaluated or a
    row carries an unknown placement_policy.
    """
    resources = [dict(r) for r in schedule_input.get("resources", []) or []]
    resource_by_id = {r["resource_id"]: r for r in resources}
    team_conflicts = [dict(e) for e in schedule_input.get("team_conflicts", []) or []]
    input_games = {
        _clean(g.get("game_id")): g for g in schedule_input.get("games", []) or []
    }

    known_team_ids: set[str] = set()
    for game in input_games.values():
        known_team_ids.update(_game_team_ids(game))
    for edge in team_conflicts:
        known_team_ids.update(
            t for t in (_clean(edge.get("team_a_id")), _clean(edge.get("team_b_id"))) if t
        )

    rows = [dict(r) for r in baseline.get("games", []) or []]
    rows_by_event: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_event[_clean(row.get("event"))].append(row)

    evaluated_events: set[str] = set()
    deferred: List[Dict[str, Any]] = []
    for event, event_rows in rows_by_event.items():
        event_team_ids = {t for row in event_rows for t in _baseline_team_ids(row)}
        if event_team_ids & known_team_ids:
            evaluated_events.add(event)
        else:
            deferred.append({
                "event": event,
                "game_count": len(event_rows),
                "reason": (
                    "team keys in the approved baseline do not match any "
                    "schedule_input team id, so shared-athlete conflicts cannot "
                    "be evaluated; placements are carried through unchanged"
                ),
            })

    if repair_events is None:
        active_repair_events = {e for e in DEFAULT_REPAIR_EVENTS if e in evaluated_events}
    else:
        active_repair_events = {_clean(e) for e in repair_events if _clean(e)}
        unknown = sorted(active_repair_events - set(rows_by_event))
        if unknown:
            raise ValueError(
                f"repair event(s) {unknown} have no games in the approved baseline; "
                f"available events: {sorted(rows_by_event)}"
            )
        blocked = sorted(active_repair_events - evaluated_events)
        if blocked:
            raise ValueError(
                f"repair event(s) {blocked} cannot be repaired: their baseline team "
                "keys do not match schedule_input team ids (deferred sport)"
            )

    games: List[Dict[str, Any]] = []
    deferred_games: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        game_id = _clean(row.get("game_key") or row.get("game_id"))
        if not game_id:
            raise ValueError("approved baseline contains a game without game_key/game_id")
        if game_id in seen_ids:
            raise ValueError(f"approved baseline lists game {game_id!r} more than once")
        seen_ids.add(game_id)
        event = _clean(row.get("event"))
        resource_id = _clean(row.get("baseline_resource_id") or row.get("resource_id"))
        slot = _clean(
            row.get("baseline_slot") or row.get("scheduled_slot") or row.get("slot")
        )
        resource = resource_by_id.get(resource_id, {})
        policy = _clean(row.get("placement_policy")).casefold()
        if policy and policy not in PLACEMENT_POLICIES:
            raise ValueError(
                f"game {game_id!r}: placement_policy {policy!r} must be one of "
                f"{list(PLACEMENT_POLICIES)}"
            )
        if not policy:
            policy = (
                POLICY_REPAIRABLE
                if event in active_repair_events and _is_preliminary_stage(row.get("stage"))
                else POLICY_LOCKED
            )
        game = {
            "game_id": game_id,
            "event": event,
            "stage": _clean(row.get("stage")),
            "pool_id": _clean(row.get("pool_id")),
            "team_ids": _baseline_team_ids(row),
            "team_labels": _baseline_team_labels(row),
            "resource_type": _clean(row.get("resource_type") or resource.get("resource_type")),
            "duration_minutes": int(
                row.get("duration_minutes") or resource.get("slot_minutes") or 60
            ),
            "baseline_resource_id": resource_id,
            "baseline_slot": slot,
            "placement_policy": policy,
            "origin": "approved_baseline",
            "allowed_resource_ids": list(row.get("allowed_resource_ids") or []) or None,
            "earliest_slot": _clean(row.get("earliest_slot")) or None,
            "latest_slot": _clean(row.get("latest_slot")) or None,
            "max_move_minutes": (
                int(row["max_move_minutes"])
                if row.get("max_move_minutes") not in (None, "")
                else None
            ),
            "provenance": {
                "source_workbook": _clean(row.get("source_workbook")),
                "source_sheet": _clean(row.get("source_sheet")),
                "source_cell": _clean(row.get("source_cell")),
                "raw_source_text": _clean(row.get("raw_source_text")),
            },
        }
        if event in evaluated_events:
            games.append(game)
        else:
            game["placement_policy"] = POLICY_LOCKED
            deferred_games.append(game)

    # Later-round pins from schedule_input stay where they are and keep their
    # courts reserved.  A pin for a baseline game is superseded by the baseline,
    # and a pin that reserves nothing real is reported, not treated as a game.
    resource_slots = build_resource_slots(resources)
    approved_placement = {
        g["game_id"]: (g["baseline_resource_id"], g["baseline_slot"])
        for g in games + deferred_games
    }
    superseded_pins: List[str] = []
    skipped_pins: List[Dict[str, str]] = []
    for pin in schedule_input.get("playoff_slots", []) or []:
        game_id = _clean(pin.get("game_id"))
        resource_id = _clean(pin.get("resource_id"))
        slot = _clean(pin.get("slot"))
        if not game_id or not resource_id or not slot:
            continue
        if game_id in approved_placement:
            if approved_placement[game_id] != (resource_id, slot):
                superseded_pins.append(game_id)
            continue
        if game_id in seen_ids:
            continue
        event = _clean(pin.get("event") or input_games.get(game_id, {}).get("event"))
        if event not in evaluated_events:
            continue
        if slot not in resource_slots.get(resource_id, ()):
            skipped_pins.append({
                "game_id": game_id,
                "reason": (
                    f"resource {resource_id!r} does not exist in schedule_input"
                    if resource_id not in resource_by_id
                    else f"{slot} is not a bookable slot of {resource_id}"
                ),
            })
            continue
        resource = resource_by_id.get(resource_id, {})
        source_game = input_games.get(game_id, {})
        seen_ids.add(game_id)
        games.append({
            "game_id": game_id,
            "event": event,
            "stage": _clean(pin.get("stage") or source_game.get("stage")),
            "pool_id": "",
            "team_ids": _game_team_ids(dict(pin)) or _game_team_ids(dict(source_game)),
            "team_labels": [],
            "resource_type": _clean(resource.get("resource_type") or pin.get("resource_type")),
            "duration_minutes": int(
                pin.get("duration_minutes")
                or source_game.get("duration_minutes")
                or resource.get("slot_minutes")
                or 60
            ),
            "baseline_resource_id": resource_id,
            "baseline_slot": slot,
            "placement_policy": POLICY_LOCKED,
            "origin": "schedule_input_pin",
            "allowed_resource_ids": None,
            "earliest_slot": None,
            "latest_slot": None,
            "max_move_minutes": None,
            "provenance": {
                "source_workbook": _clean(pin.get("x_master_schedule_source")),
                "source_sheet": _clean(pin.get("x_master_schedule_sheet")),
                "source_cell": _clean(pin.get("x_master_schedule_cell")),
                "raw_source_text": _clean(pin.get("x_master_schedule_raw")),
            },
        })

    game_ids = {g["game_id"] for g in games}
    teams_with_games: set[str] = {t for g in games for t in g["team_ids"]}
    evaluated_edges: List[Dict[str, Any]] = []
    unevaluated: Counter = Counter()
    for edge in team_conflicts:
        team_a, team_b = _clean(edge.get("team_a_id")), _clean(edge.get("team_b_id"))
        if team_a in teams_with_games and team_b in teams_with_games:
            evaluated_edges.append(edge)
        else:
            missing = [
                _clean(edge.get(event_key))
                for team, event_key in ((team_a, "event_a"), (team_b, "event_b"))
                if team not in teams_with_games
            ]
            unevaluated[" / ".join(sorted(set(missing))) or "unknown"] += 1

    precedence = [
        dict(rule) for rule in schedule_input.get("precedence", []) or []
        if _clean(rule.get("before_game_id")) in game_ids
        and _clean(rule.get("after_game_id")) in game_ids
    ]

    problem: Dict[str, Any] = {
        "games": games,
        "deferred_games": deferred_games,
        "resources": resources,
        "team_conflicts": evaluated_edges,
        "precedence": precedence,
        "day_order": list(schedule_input.get("day_order") or []),
        "repair_events": sorted(active_repair_events),
        "context_events": sorted(evaluated_events - active_repair_events),
        "deferred_events": sorted(deferred, key=lambda d: d["event"]),
        "unevaluated_edges": [
            {"events_without_approved_games": events, "edge_count": count}
            for events, count in sorted(unevaluated.items())
        ],
        "superseded_pins": sorted(superseded_pins),
        "skipped_pins": skipped_pins,
        "options": {
            "allow_cross_day": bool(allow_cross_day),
            "max_move_minutes": max_move_minutes,
            "rest_window_minutes": int(rest_window_minutes),
        },
    }
    _attach_pairs(problem)
    return problem


def _attach_pairs(problem: Dict[str, Any]) -> None:
    """Precompute same-team pairs and shared-athlete game pairs."""
    games = problem["games"]
    edge_by_pair: Dict[frozenset, Dict[str, Any]] = {}
    for edge in problem["team_conflicts"]:
        team_a, team_b = _clean(edge.get("team_a_id")), _clean(edge.get("team_b_id"))
        if not team_a or not team_b or team_a == team_b:
            continue
        counts = _normalize_conflict_edge_counts(edge)
        edge_by_pair[frozenset((team_a, team_b))] = {
            **counts,
            "names": list(edge.get("shared_participant_names") or []),
        }

    same_team: List[Tuple[str, str]] = []
    conflicts: List[Dict[str, Any]] = []
    for index, game_a in enumerate(games):
        teams_a = game_a["team_ids"]
        for game_b in games[index + 1:]:
            teams_b = game_b["team_ids"]
            if set(teams_a) & set(teams_b):
                same_team.append((game_a["game_id"], game_b["game_id"]))
                continue
            primary = secondary = shared = 0
            names: List[str] = []
            for team_a in teams_a:
                for team_b in teams_b:
                    edge = edge_by_pair.get(frozenset((team_a, team_b)))
                    if edge is None:
                        continue
                    primary += edge["primary"]
                    secondary += edge["secondary"]
                    shared += edge["shared_count"]
                    names.extend(n for n in edge["names"] if n not in names)
            if primary or secondary or shared:
                conflicts.append({
                    "game_a_id": game_a["game_id"],
                    "game_b_id": game_b["game_id"],
                    "primary": primary,
                    "secondary": secondary,
                    "shared_count": shared,
                    "shared_participant_names": names,
                })
    problem["_same_team_pairs"] = same_team
    problem["_conflict_pairs"] = conflicts


class _Context:
    """Resource grid, real-time arithmetic and physical-court identity."""

    def __init__(self, problem: Mapping[str, Any]) -> None:
        self.resources = {r["resource_id"]: r for r in problem["resources"]}
        self.slots = build_resource_slots(problem["resources"])
        self.slot_index = {
            rid: {label: idx for idx, label in enumerate(labels)}
            for rid, labels in self.slots.items()
        }
        days = list(problem.get("day_order") or [])
        seen = set(days)
        extra = {r["day"] for r in problem["resources"]} - seen
        for game in list(problem["games"]) + list(problem.get("deferred_games", [])):
            if game.get("baseline_slot"):
                extra.add(_parse_slot_label(game["baseline_slot"])[0])
        days += sorted(extra - seen, key=_day_chronological_key)
        self.day_index = {day: idx for idx, day in enumerate(days)}
        self.days = days

    def absolute_minutes(self, slot: str) -> int:
        day, time = _parse_slot_label(slot)
        return self.day_index.get(day, len(self.day_index)) * 1440 + _parse_time_minutes(time)

    def court_key(self, resource_id: str) -> Tuple[str, str, str]:
        res = self.resources.get(resource_id) or {}
        return (
            _clean(res.get("exclusive_group") or res.get("venue_name")),
            _clean(res.get("resource_type")),
            _clean(res.get("label")) or resource_id,
        )

    def court_label(self, resource_id: str) -> str:
        res = self.resources.get(resource_id) or {}
        venue = _clean(res.get("venue_name") or res.get("exclusive_group"))
        label = _clean(res.get("label")) or resource_id
        return f"{venue} {label}".strip()

    def geometry(self, game: Mapping[str, Any], resource_id: str, slot: str) -> Dict[str, Any]:
        """Describe one placement; 'problem' is set when it is not legal."""
        duration = int(game["duration_minutes"])
        info: Dict[str, Any] = {
            "resource_id": resource_id,
            "slot": slot,
            "problem": None,
            "cells": [],
            "court": self.court_key(resource_id),
        }
        try:
            day, _time = _parse_slot_label(slot)
            start = self.absolute_minutes(slot)
        except (ValueError, AttributeError):
            info.update(day="", start=None, end=None, occupied_end=None,
                        problem=f"slot {slot!r} is not a valid slot label")
            return info
        info.update(day=day, start=start, end=start + duration, occupied_end=start + duration)
        res = self.resources.get(resource_id)
        if res is None:
            info["problem"] = f"resource {resource_id!r} does not exist"
            return info
        if _clean(res.get("resource_type")) != _clean(game.get("resource_type")):
            info["problem"] = (
                f"resource {resource_id!r} is a {res.get('resource_type')}, "
                f"not a {game.get('resource_type')}"
            )
            return info
        idx = self.slot_index[resource_id].get(slot)
        if idx is None:
            info["problem"] = (
                f"{slot} is not a bookable slot of {resource_id} "
                f"({res.get('open_time')}-{res.get('close_time')})"
            )
            return info
        slot_minutes = int(res["slot_minutes"])
        n_slots = max(1, math.ceil(duration / slot_minutes))
        if idx + n_slots > len(self.slots[resource_id]):
            info["problem"] = (
                f"a {duration}-minute game at {slot} runs past the close of {resource_id}"
            )
            return info
        info["cells"] = [(resource_id, i) for i in range(idx, idx + n_slots)]
        info["occupied_end"] = start + n_slots * slot_minutes
        return info


def baseline_placements(problem: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    return {
        g["game_id"]: {"resource_id": g["baseline_resource_id"], "slot": g["baseline_slot"]}
        for g in problem["games"]
        if g["baseline_resource_id"] and g["baseline_slot"]
    }


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _back_to_back(a_start: int, a_end: int, b_start: int, b_end: int, window: int) -> bool:
    """True when two same-day, non-overlapping games leave at most `window` minutes."""
    if a_start // 1440 != b_start // 1440 or _overlap(a_start, a_end, b_start, b_end):
        return False
    gap = b_start - a_end if b_start >= a_end else a_start - b_end
    return 0 <= gap <= window


def _mode_conflict_pairs(ctx: _Context) -> List[Tuple[str, str]]:
    """Resource pairs in one exclusive gym with different modes and overlapping windows."""
    by_group: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for res in ctx.resources.values():
        group = _clean(res.get("exclusive_group"))
        if group:
            by_group[(group, res["day"])].append(res)
    pairs: List[Tuple[str, str]] = []
    for group_resources in by_group.values():
        for index, res_a in enumerate(group_resources):
            for res_b in group_resources[index + 1:]:
                if res_a["resource_type"] == res_b["resource_type"]:
                    continue
                if _overlap(
                    _parse_time_minutes(res_a["open_time"]), _parse_time_minutes(res_a["close_time"]),
                    _parse_time_minutes(res_b["open_time"]), _parse_time_minutes(res_b["close_time"]),
                ):
                    pairs.append((res_a["resource_id"], res_b["resource_id"]))
    return pairs


# ---------------------------------------------------------------------------
# Audit: one definition of every metric, used for baseline and optimized alike
# ---------------------------------------------------------------------------

def audit_placements(
    problem: Mapping[str, Any],
    placements: Mapping[str, Mapping[str, str]],
) -> Dict[str, Any]:
    """Measure a set of placements.  Hard violations are listed, never hidden."""
    ctx = _Context(problem)
    games = {g["game_id"]: g for g in problem["games"]}
    window = int(problem["options"].get("rest_window_minutes") or 0)

    geometry: Dict[str, Dict[str, Any]] = {}
    unplaced: List[str] = []
    hard: List[Dict[str, Any]] = []
    for game_id, game in games.items():
        placement = placements.get(game_id)
        if not placement or not placement.get("resource_id") or not placement.get("slot"):
            unplaced.append(game_id)
            continue
        info = ctx.geometry(game, placement["resource_id"], placement["slot"])
        geometry[game_id] = info
        if info["problem"]:
            hard.append({
                "kind": "illegal_placement",
                "game_ids": [game_id],
                "message": f"{game_id}: {info['problem']}",
            })

    occupancy: Dict[Tuple[str, int], List[str]] = defaultdict(list)
    for game_id, info in geometry.items():
        for cell in info["cells"]:
            occupancy[cell].append(game_id)
    reported: set[frozenset] = set()
    for (resource_id, idx), occupants in sorted(occupancy.items()):
        if len(occupants) < 2:
            continue
        key = frozenset(occupants)
        if key in reported:
            continue
        reported.add(key)
        hard.append({
            "kind": "resource_collision",
            "game_ids": sorted(occupants),
            "message": (
                f"{' and '.join(sorted(occupants))} share {resource_id} at "
                f"{ctx.slots[resource_id][idx]}"
            ),
        })

    mode_pairs = set()
    for res_a, res_b in _mode_conflict_pairs(ctx):
        mode_pairs.add((res_a, res_b))
        mode_pairs.add((res_b, res_a))
    if mode_pairs:
        placed = [(gid, info) for gid, info in geometry.items() if info["cells"]]
        for index, (gid_a, info_a) in enumerate(placed):
            for gid_b, info_b in placed[index + 1:]:
                if (info_a["resource_id"], info_b["resource_id"]) not in mode_pairs:
                    continue
                if _overlap(info_a["start"], info_a["occupied_end"],
                            info_b["start"], info_b["occupied_end"]):
                    hard.append({
                        "kind": "gym_mode_conflict",
                        "game_ids": sorted((gid_a, gid_b)),
                        "message": (
                            f"{gid_a} and {gid_b} need different modes of the same gym "
                            f"at {info_a['slot']}"
                        ),
                    })

    def _timed(game_id: str) -> Optional[Dict[str, Any]]:
        info = geometry.get(game_id)
        return info if info and info.get("start") is not None else None

    rest_rows: List[Dict[str, Any]] = []
    for gid_a, gid_b in problem["_same_team_pairs"]:
        info_a, info_b = _timed(gid_a), _timed(gid_b)
        if not info_a or not info_b:
            continue
        shared = sorted(set(games[gid_a]["team_ids"]) & set(games[gid_b]["team_ids"]))
        if _overlap(info_a["start"], info_a["end"], info_b["start"], info_b["end"]):
            hard.append({
                "kind": "same_team_overlap",
                "game_ids": sorted((gid_a, gid_b)),
                "message": (
                    f"{', '.join(shared)} plays {gid_a} ({info_a['slot']}) and "
                    f"{gid_b} ({info_b['slot']}) at the same time"
                ),
            })
        elif _back_to_back(info_a["start"], info_a["end"],
                           info_b["start"], info_b["end"], window):
            first, second = sorted((info_a, info_b), key=lambda i: i["start"])
            rest_rows.append({
                "team_ids": shared,
                "game_a_id": gid_a,
                "game_b_id": gid_b,
                "first_slot": first["slot"],
                "second_slot": second["slot"],
            })

    for rule in problem["precedence"]:
        before, after = _clean(rule.get("before_game_id")), _clean(rule.get("after_game_id"))
        info_a, info_b = _timed(before), _timed(after)
        if info_a and info_b and info_b["start"] < info_a["end"]:
            hard.append({
                "kind": "precedence_violation",
                "game_ids": [before, after],
                "message": f"{after} ({info_b['slot']}) starts before {before} ({info_a['slot']}) ends",
            })

    conflict_rows: List[Dict[str, Any]] = []
    for pair in problem["_conflict_pairs"]:
        info_a, info_b = _timed(pair["game_a_id"]), _timed(pair["game_b_id"])
        if not info_a or not info_b:
            continue
        if not _overlap(info_a["start"], info_a["end"], info_b["start"], info_b["end"]):
            continue
        game_a, game_b = games[pair["game_a_id"]], games[pair["game_b_id"]]
        conflict_rows.append({
            "game_a_id": pair["game_a_id"],
            "game_b_id": pair["game_b_id"],
            "event_a": game_a["event"],
            "event_b": game_b["event"],
            "slot_a": info_a["slot"],
            "slot_b": info_b["slot"],
            "primary": pair["primary"],
            "secondary": pair["secondary"],
            "shared_count": pair["shared_count"],
            "shared_participant_names": list(pair["shared_participant_names"]),
            "both_locked": (
                game_a["placement_policy"] == POLICY_LOCKED
                and game_b["placement_policy"] == POLICY_LOCKED
            ),
        })

    switches = 0
    by_court: Dict[Tuple[str, str, str], List[Tuple[int, int, str]]] = defaultdict(list)
    for game_id, info in geometry.items():
        category = _volleyball_category_for_event(games[game_id]["event"])
        if category and info["cells"]:
            by_court[info["court"]].append((info["start"], info["occupied_end"], category))
    for timeline in by_court.values():
        timeline.sort()
        for (_s1, end_1, cat_1), (start_2, _e2, cat_2) in zip(timeline, timeline[1:]):
            if end_1 == start_2 and cat_1 != cat_2:
                switches += 1

    latest_by_day: Dict[str, int] = {}
    for info in geometry.values():
        if info.get("end") is None:
            continue
        minute_of_day = info["end"] % 1440 or 1440
        latest_by_day[info["day"]] = max(latest_by_day.get(info["day"], 0), minute_of_day)

    def _clock(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    edge_summary, _edge_rows = build_conflict_audit(
        {
            "games": [
                {
                    "game_id": g["game_id"],
                    "event": g["event"],
                    "duration_minutes": g["duration_minutes"],
                    "team_ids": g["team_ids"],
                }
                for g in games.values()
            ],
            "team_conflicts": problem["team_conflicts"],
        },
        [
            {"game_id": gid, "resource_id": p["resource_id"], "slot": p["slot"]}
            for gid, p in placements.items() if gid in games
        ],
    )

    kinds = Counter(item["kind"] for item in hard)
    policies = Counter(g["placement_policy"] for g in games.values())
    return {
        "total_games": len(games),
        "preliminary_games": sum(
            1 for g in games.values() if g["origin"] == "approved_baseline"
        ),
        "repairable_games": policies.get(POLICY_REPAIRABLE, 0),
        "solver_controlled_games": policies.get(POLICY_SOLVER_CONTROLLED, 0),
        "locked_games": policies.get(POLICY_LOCKED, 0),
        "legal_assignments": len(geometry) - kinds.get("illegal_placement", 0),
        "illegal_assignments": kinds.get("illegal_placement", 0),
        "unplaced_games": sorted(unplaced),
        "hard_violation_count": len(hard),
        "hard_violations": hard,
        "resource_collisions": kinds.get("resource_collision", 0),
        "same_team_overlaps": kinds.get("same_team_overlap", 0),
        "gym_mode_conflicts": kinds.get("gym_mode_conflict", 0),
        "precedence_violations": kinds.get("precedence_violation", 0),
        "primary_conflict_penalty": sum(r["primary"] for r in conflict_rows),
        "secondary_conflict_penalty": sum(r["secondary"] for r in conflict_rows),
        "conflict_pair_count": len(conflict_rows),
        "locked_conflict_pair_count": sum(1 for r in conflict_rows if r["both_locked"]),
        "overlapping_edges": int(edge_summary.get("overlapping_edges", 0)),
        "conflict_pairs": conflict_rows,
        "rest_violation_count": len(rest_rows),
        "rest_violations": rest_rows,
        "volleyball_adjacent_switches": switches,
        "latest_finish_by_day": {
            day: _clock(latest_by_day[day])
            for day in sorted(latest_by_day, key=lambda d: ctx.day_index.get(d, 99))
        },
        "latest_finish": _clock(max(latest_by_day.values())) if latest_by_day else None,
    }


# ---------------------------------------------------------------------------
# CP-SAT repair model
# ---------------------------------------------------------------------------

class _Lin:
    """A linear sum of BoolVars plus a constant."""

    def __init__(self) -> None:
        self.vars: List[Any] = []
        self.coefs: List[int] = []
        self.const = 0

    def add(self, var: Any, coef: int = 1) -> None:
        if coef:
            self.vars.append(var)
            self.coefs.append(int(coef))

    def upper_bound(self) -> int:
        return self.const + sum(c for c in self.coefs if c > 0)

    def expr(self, cp_model: Any) -> Any:
        if not self.vars:
            return self.const
        return cp_model.LinearExpr.WeightedSum(self.vars, self.coefs) + self.const


def _movement_order(movement_priority: str) -> List[str]:
    if movement_priority not in MOVEMENT_PRIORITIES:
        raise ValueError(
            f"movement_priority must be one of {list(MOVEMENT_PRIORITIES)}, "
            f"got {movement_priority!r}"
        )
    return ["move_minutes", "court_changes"] if movement_priority == "time,court" else [
        "court_changes", "move_minutes"
    ]


def solve_repair(
    problem: Mapping[str, Any],
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
    max_moves: Optional[int] = None,
    movement_priority: str = "time,court",
    rest_policy: str = "no_worse",
    conflict_tiers_only: bool = False,
) -> Dict[str, Any]:
    """Solve the repair model tier by tier.

    Returns {status, placements, tiers, unscheduled, solver_wall_seconds}.
    `placements` covers every game in the problem (locked games keep their
    baseline placement).  status is OPTIMAL only when every tier was proven.
    """
    from ortools.sat.python import cp_model  # import guard, as in scheduler.py

    if rest_policy not in REST_POLICIES:
        raise ValueError(f"rest_policy must be one of {list(REST_POLICIES)}, got {rest_policy!r}")
    movement_order = _movement_order(movement_priority)

    ctx = _Context(problem)
    options = problem["options"]
    window = int(options.get("rest_window_minutes") or 0)
    games = {g["game_id"]: g for g in problem["games"]}
    fixed: Dict[str, Dict[str, Any]] = {}
    movable: List[str] = []
    for game_id, game in games.items():
        if game["placement_policy"] == POLICY_LOCKED:
            fixed[game_id] = ctx.geometry(game, game["baseline_resource_id"], game["baseline_slot"])
        else:
            movable.append(game_id)

    baseline = baseline_placements(problem)
    baseline_audit = audit_placements(problem, baseline)

    locked_cells: set[Tuple[str, int]] = set()
    for info in fixed.values():
        locked_cells.update(info["cells"])
    mode_pairs = _mode_conflict_pairs(ctx)
    mode_partners: Dict[str, List[str]] = defaultdict(list)
    for res_a, res_b in mode_pairs:
        mode_partners[res_a].append(res_b)
        mode_partners[res_b].append(res_a)

    # Precedence against locked games becomes a real-time window per game.
    not_before: Dict[str, int] = defaultdict(int)
    not_after_end: Dict[str, int] = {}
    free_precedence: List[Tuple[str, str]] = []
    for rule in problem["precedence"]:
        before, after = _clean(rule.get("before_game_id")), _clean(rule.get("after_game_id"))
        if before in fixed and after in fixed:
            continue
        if before in fixed:
            if fixed[before].get("end") is not None:
                not_before[after] = max(not_before[after], fixed[before]["end"])
        elif after in fixed:
            if fixed[after].get("start") is not None:
                not_after_end[before] = min(
                    not_after_end.get(before, fixed[after]["start"]), fixed[after]["start"]
                )
        else:
            free_precedence.append((before, after))

    event_days: Dict[str, set] = defaultdict(set)
    for game in games.values():
        if game["origin"] == "approved_baseline" and game["baseline_slot"]:
            event_days[game["event"]].add(_parse_slot_label(game["baseline_slot"])[0])

    model = cp_model.CpModel()
    candidates: Dict[str, List[Dict[str, Any]]] = {}
    x: Dict[str, List[Any]] = {}
    cell_vars: Dict[Tuple[str, int], List[Any]] = defaultdict(list)
    unscheduled: List[str] = []

    for game_id in movable:
        game = games[game_id]
        base_info = (
            ctx.geometry(game, game["baseline_resource_id"], game["baseline_slot"])
            if game["baseline_resource_id"] and game["baseline_slot"] else None
        )
        base_start = base_info["start"] if base_info else None
        base_day = base_info["day"] if base_info else None
        has_preference = game["placement_policy"] == POLICY_REPAIRABLE and base_start is not None
        if not has_preference:
            allowed_days = None
        elif options.get("allow_cross_day"):
            allowed_days = event_days.get(game["event"]) or {base_day}
        else:
            allowed_days = {base_day}
        limit = game["max_move_minutes"]
        if limit is None:
            limit = options.get("max_move_minutes")
        earliest = ctx.absolute_minutes(game["earliest_slot"]) if game["earliest_slot"] else None
        latest = ctx.absolute_minutes(game["latest_slot"]) if game["latest_slot"] else None
        allowed_resources = set(game["allowed_resource_ids"] or [])

        options_for_game: List[Dict[str, Any]] = []
        for resource_id, labels in ctx.slots.items():
            res = ctx.resources[resource_id]
            if _clean(res.get("resource_type")) != game["resource_type"]:
                continue
            if allowed_resources and resource_id not in allowed_resources:
                continue
            if allowed_days is not None and res["day"] not in allowed_days:
                continue
            for label in labels:
                info = ctx.geometry(game, resource_id, label)
                if info["problem"]:
                    continue
                if any(cell in locked_cells for cell in info["cells"]):
                    continue
                if earliest is not None and info["start"] < earliest:
                    continue
                if latest is not None and info["start"] > latest:
                    continue
                if info["start"] < not_before[game_id]:
                    continue
                if game_id in not_after_end and info["end"] > not_after_end[game_id]:
                    continue
                if has_preference and limit is not None and abs(info["start"] - base_start) > int(limit):
                    continue
                if any(
                    _overlap(info["start"], info["occupied_end"], other["start"], other["occupied_end"])
                    for other in fixed.values()
                    if other["cells"] and other["resource_id"] in mode_partners.get(resource_id, ())
                ):
                    continue
                if any(
                    set(game["team_ids"]) & set(games[other_id]["team_ids"])
                    and other.get("start") is not None
                    and _overlap(info["start"], info["end"], other["start"], other["end"])
                    for other_id, other in fixed.items()
                ):
                    continue
                info["is_baseline"] = bool(
                    base_info
                    and resource_id == game["baseline_resource_id"]
                    and label == game["baseline_slot"]
                )
                options_for_game.append(info)

        options_for_game.sort(key=lambda i: (i["start"], i["court"], i["resource_id"]))
        candidates[game_id] = options_for_game
        x[game_id] = [
            model.NewBoolVar(f"x_{game_id}_{idx}") for idx in range(len(options_for_game))
        ]
        if not options_for_game:
            unscheduled.append(game_id)
            continue
        model.AddExactlyOne(x[game_id])
        for info, var in zip(options_for_game, x[game_id]):
            for cell in info["cells"]:
                cell_vars[cell].append(var)

    if unscheduled:
        return {
            "status": STATUS_INFEASIBLE,
            "placements": {},
            "tiers": [],
            "unscheduled": sorted(unscheduled),
            "solver_wall_seconds": 0.0,
            "baseline_audit": baseline_audit,
        }

    for var_list in cell_vars.values():
        if len(var_list) > 1:
            model.AddAtMostOne(var_list)

    for res_a, res_b in mode_pairs:
        for idx_a, label_a in enumerate(ctx.slots[res_a]):
            vars_a = cell_vars.get((res_a, idx_a))
            if not vars_a:
                continue
            start_a = ctx.absolute_minutes(label_a)
            end_a = start_a + int(ctx.resources[res_a]["slot_minutes"])
            for idx_b, label_b in enumerate(ctx.slots[res_b]):
                vars_b = cell_vars.get((res_b, idx_b))
                if not vars_b:
                    continue
                start_b = ctx.absolute_minutes(label_b)
                end_b = start_b + int(ctx.resources[res_b]["slot_minutes"])
                if _overlap(start_a, end_a, start_b, end_b):
                    model.AddAtMostOne(vars_a + vars_b)

    # starts[game_id][start] -> vars placing the game at that real-time start.
    starts: Dict[str, Dict[int, List[Any]]] = {}
    for game_id in movable:
        by_start: Dict[int, List[Any]] = defaultdict(list)
        for info, var in zip(candidates[game_id], x[game_id]):
            by_start[info["start"]].append(var)
        starts[game_id] = by_start

    def _duration(game_id: str) -> int:
        return int(games[game_id]["duration_minutes"])

    def _partners(gid_a: str, start_a: int, gid_b: str, test) -> List[Any]:
        """Vars of gid_b whose start satisfies test() against gid_a at start_a."""
        end_a = start_a + _duration(gid_a)
        found: List[Any] = []
        for start_b, vars_b in starts[gid_b].items():
            if test(start_a, end_a, start_b, start_b + _duration(gid_b)):
                found.extend(vars_b)
        return found

    def _is_rest_clash(a_start, a_end, b_start, b_end) -> bool:
        return _back_to_back(a_start, a_end, b_start, b_end, window)

    rest = _Lin()
    for gid_a, gid_b in problem["_same_team_pairs"]:
        a_fixed, b_fixed = gid_a in fixed, gid_b in fixed
        if a_fixed and b_fixed:
            info_a, info_b = fixed[gid_a], fixed[gid_b]
            if info_a.get("start") is not None and info_b.get("start") is not None and _back_to_back(
                info_a["start"], info_a["end"], info_b["start"], info_b["end"], window
            ):
                rest.const += 1
            continue
        if a_fixed or b_fixed:
            free_id, locked = (gid_b, fixed[gid_a]) if a_fixed else (gid_a, fixed[gid_b])
            if locked.get("start") is None:
                continue
            for start, var_list in starts[free_id].items():
                if _back_to_back(start, start + _duration(free_id),
                                 locked["start"], locked["end"], window):
                    for var in var_list:
                        rest.add(var)
            continue
        rest_var = None
        for start_a, vars_a in starts[gid_a].items():
            clashing = _partners(gid_a, start_a, gid_b, _overlap)
            if clashing:
                model.Add(sum(vars_a) + sum(clashing) <= 1)
            tight = _partners(gid_a, start_a, gid_b, _is_rest_clash)
            if tight:
                if rest_var is None:
                    rest_var = model.NewBoolVar(f"rest_{gid_a}_{gid_b}")
                    rest.add(rest_var)
                model.Add(rest_var >= sum(vars_a) + sum(tight) - 1)

    for before, after in free_precedence:
        for start_a, vars_a in starts[before].items():
            end_a = start_a + _duration(before)
            too_early = [
                var for start_b, vars_b in starts[after].items() if start_b < end_a
                for var in vars_b
            ]
            if too_early:
                model.Add(sum(vars_a) + sum(too_early) <= 1)

    primary, secondary = _Lin(), _Lin()
    for index, pair in enumerate(problem["_conflict_pairs"]):
        gid_a, gid_b = pair["game_a_id"], pair["game_b_id"]
        a_fixed, b_fixed = gid_a in fixed, gid_b in fixed
        if a_fixed and b_fixed:
            info_a, info_b = fixed[gid_a], fixed[gid_b]
            if info_a.get("start") is not None and info_b.get("start") is not None and _overlap(
                info_a["start"], info_a["end"], info_b["start"], info_b["end"]
            ):
                primary.const += pair["primary"]
                secondary.const += pair["secondary"]
            continue
        if a_fixed or b_fixed:
            free_id, locked = (gid_b, fixed[gid_a]) if a_fixed else (gid_a, fixed[gid_b])
            if locked.get("start") is None:
                continue
            for start, var_list in starts[free_id].items():
                if _overlap(start, start + _duration(free_id), locked["start"], locked["end"]):
                    for var in var_list:
                        primary.add(var, pair["primary"])
                        secondary.add(var, pair["secondary"])
            continue
        overlap_var = None
        for start_a, vars_a in starts[gid_a].items():
            clashing = _partners(gid_a, start_a, gid_b, _overlap)
            if not clashing:
                continue
            if overlap_var is None:
                overlap_var = model.NewBoolVar(f"conflict_{index}")
                primary.add(overlap_var, pair["primary"])
                secondary.add(overlap_var, pair["secondary"])
            model.Add(overlap_var >= sum(vars_a) + sum(clashing) - 1)

    moved, moved_day, minutes, court_changes, tie_break = _Lin(), _Lin(), _Lin(), _Lin(), _Lin()
    for game_id in movable:
        game = games[game_id]
        if game["placement_policy"] != POLICY_REPAIRABLE:
            for rank, var in enumerate(x[game_id]):
                tie_break.add(var, rank)
            continue
        base_info = ctx.geometry(game, game["baseline_resource_id"], game["baseline_slot"])
        if base_info.get("start") is None:
            moved.const += 1
            continue
        if not any(info["is_baseline"] for info in candidates[game_id]):
            moved.const += 1
        for rank, (info, var) in enumerate(zip(candidates[game_id], x[game_id])):
            tie_break.add(var, rank)
            if info["is_baseline"]:
                continue
            moved.add(var)
            minutes.add(var, abs(info["start"] - base_info["start"]))
            if info["court"] != base_info["court"]:
                court_changes.add(var)
            if info["day"] != base_info["day"]:
                moved_day.add(var)

    # Constant sums (no free game involved) cannot be changed by the solver.
    if max_moves is not None and moved.vars:
        model.Add(moved.expr(cp_model) <= int(max_moves))

    if rest_policy != "ignore" and rest.vars and not baseline_audit["hard_violation_count"]:
        cap = 0 if rest_policy == "strict" else baseline_audit["rest_violation_count"]
        model.Add(rest.expr(cp_model) <= max(cap, rest.const))

    # Volleyball Men/Women switches on one physical court in consecutive slots.
    occupancy: Dict[Tuple[Tuple[str, str, str], int, int], Dict[str, _Lin]] = {}

    def _note_volleyball(info: Mapping[str, Any], category: str, var: Any = None) -> None:
        for resource_id, idx in info["cells"]:
            start = ctx.absolute_minutes(ctx.slots[resource_id][idx])
            end = start + int(ctx.resources[resource_id]["slot_minutes"])
            cell = occupancy.setdefault(
                (ctx.court_key(resource_id), start, end), {"men": _Lin(), "women": _Lin()}
            )
            if var is None:
                cell[category].const += 1
            else:
                cell[category].add(var)

    for game_id, info in fixed.items():
        category = _volleyball_category_for_event(games[game_id]["event"])
        if category and info["cells"]:
            _note_volleyball(info, category)
    for game_id in movable:
        category = _volleyball_category_for_event(games[game_id]["event"])
        if category:
            for info, var in zip(candidates[game_id], x[game_id]):
                _note_volleyball(info, category, var)

    switches = _Lin()
    cells_by_court: Dict[Tuple[str, str, str], List[Tuple[int, int]]] = defaultdict(list)
    for court, start, end in occupancy:
        cells_by_court[court].append((start, end))
    for court, spans in cells_by_court.items():
        spans.sort()
        for (start_1, end_1), (start_2, end_2) in zip(spans, spans[1:]):
            if end_1 != start_2:
                continue
            first, second = occupancy[(court, start_1, end_1)], occupancy[(court, start_2, end_2)]
            for cat_1, cat_2 in (("men", "women"), ("women", "men")):
                lin_1, lin_2 = first[cat_1], second[cat_2]
                if not lin_1.vars and not lin_2.vars:
                    if lin_1.const and lin_2.const:
                        switches.const += 1
                    continue
                if not (lin_1.upper_bound() and lin_2.upper_bound()):
                    continue
                switch_var = model.NewBoolVar(f"vbswitch_{len(switches.vars)}")
                model.Add(switch_var >= lin_1.expr(cp_model) + lin_2.expr(cp_model) - 1)
                switches.add(switch_var)

    quality = _Lin()
    switch_weight = 1
    rest_weight = switches.upper_bound() + 1
    quality.const = rest.const * rest_weight + switches.const * switch_weight
    for var, coef in zip(rest.vars, rest.coefs):
        quality.add(var, coef * rest_weight)
    for var, coef in zip(switches.vars, switches.coefs):
        quality.add(var, coef * switch_weight)

    named = {
        "primary_conflict_penalty": primary,
        "secondary_conflict_penalty": secondary,
        "games_moved_day": moved_day,
        "games_moved": moved,
        "move_minutes": minutes,
        "court_changes": court_changes,
        "operational_quality": quality,
        "tie_break": tie_break,
    }
    order = ["primary_conflict_penalty", "secondary_conflict_penalty"]
    if not conflict_tiers_only:
        if options.get("allow_cross_day"):
            order.append("games_moved_day")
        order += ["games_moved"] + movement_order + ["operational_quality", "tie_break"]

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(timeout_seconds)
    solver.parameters.random_seed = int(SCHEDULE_SOLVER_RANDOM_SEED or 0)
    # One worker keeps repeated runs identical; opt in to more with
    # SCHEDULE_SOLVER_WORKERS when a tier cannot be proven in time.
    solver.parameters.num_search_workers = _NUM_SEARCH_WORKERS if _NUM_SEARCH_WORKERS > 0 else 1

    all_vars = [(gid, idx, var) for gid in movable for idx, var in enumerate(x[gid])]
    for gid, idx, var in all_vars:
        model.AddHint(var, 1 if candidates[gid][idx]["is_baseline"] else 0)

    tiers: List[Dict[str, Any]] = []
    chosen: Dict[str, int] = {}
    total_wall = 0.0
    final_status = STATUS_OPTIMAL
    for name in order:
        lin = named[name]
        if not lin.vars and chosen:
            tiers.append({"tier": name, "value": lin.const, "status": STATUS_OPTIMAL,
                          "solver_wall_seconds": 0.0})
            continue
        model.Minimize(lin.expr(cp_model))
        status_name = solver.StatusName(solver.Solve(model))
        wall = float(solver.WallTime())
        total_wall += wall
        if status_name not in ("OPTIMAL", "FEASIBLE"):
            failed = STATUS_INFEASIBLE if status_name == "INFEASIBLE" else STATUS_UNKNOWN
            tiers.append({"tier": name, "value": None, "status": failed,
                          "solver_wall_seconds": round(wall, 3)})
            if not chosen:
                return {
                    "status": failed,
                    "placements": {},
                    "tiers": tiers,
                    "unscheduled": sorted(movable),
                    "solver_wall_seconds": round(total_wall, 3),
                    "baseline_audit": baseline_audit,
                }
            final_status = STATUS_FEASIBLE
            break
        value = int(round(solver.ObjectiveValue()))
        if status_name != "OPTIMAL":
            final_status = STATUS_FEASIBLE
        tiers.append({
            "tier": name,
            "value": value,
            "status": STATUS_OPTIMAL if status_name == "OPTIMAL" else STATUS_FEASIBLE,
            "solver_wall_seconds": round(wall, 3),
        })
        chosen = {
            gid: next(idx for idx, var in enumerate(x[gid]) if solver.Value(var))
            for gid in movable
        }
        if lin.vars:
            model.Add(lin.expr(cp_model) <= value)
        model.ClearHints()
        for gid, idx, var in all_vars:
            model.AddHint(var, 1 if chosen[gid] == idx else 0)

    placements = {
        gid: {"resource_id": info["resource_id"], "slot": info["slot"]}
        for gid, info in fixed.items()
    }
    for gid in movable:
        info = candidates[gid][chosen[gid]] if gid in chosen else None
        if info is not None:
            placements[gid] = {"resource_id": info["resource_id"], "slot": info["slot"]}
    return {
        "status": final_status,
        "placements": placements,
        "tiers": tiers,
        "unscheduled": [],
        "solver_wall_seconds": round(total_wall, 3),
        "baseline_audit": baseline_audit,
    }


def compute_move_frontier(
    problem: Mapping[str, Any],
    *,
    max_budget: int,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
    rest_policy: str = "no_worse",
) -> List[Dict[str, Any]]:
    """Best conflict penalties achievable with at most k moved games, k = 0..max_budget."""
    rows: List[Dict[str, Any]] = []
    for budget in range(0, max(int(max_budget), 0) + 1):
        result = solve_repair(
            problem,
            timeout_seconds=timeout_seconds,
            max_moves=budget,
            rest_policy=rest_policy,
            conflict_tiers_only=True,
        )
        values = {tier["tier"]: tier for tier in result["tiers"]}
        primary = values.get("primary_conflict_penalty", {})
        secondary = values.get("secondary_conflict_penalty", {})
        rows.append({
            "max_moves": budget,
            "status": result["status"],
            "primary_conflict_penalty": primary.get("value"),
            "secondary_conflict_penalty": secondary.get("value"),
            "proven": (
                primary.get("status") == STATUS_OPTIMAL
                and secondary.get("status") == STATUS_OPTIMAL
            ),
        })
    return rows


# ---------------------------------------------------------------------------
# Baseline-versus-optimized comparison
# ---------------------------------------------------------------------------

_METRICS: Tuple[Tuple[str, str], ...] = (
    ("primary_conflict_penalty", "Primary shared-athlete conflict penalty"),
    ("secondary_conflict_penalty", "Secondary shared-athlete conflict penalty"),
    ("conflict_pair_count", "Conflicting game pairs"),
    ("locked_conflict_pair_count", "Conflicting pairs where both games are locked"),
    ("overlapping_edges", "Overlapping shared-athlete team edges"),
    ("hard_violation_count", "Hard violations"),
    ("illegal_assignments", "Placements outside a valid window"),
    ("resource_collisions", "Resource collisions"),
    ("same_team_overlaps", "Same-team overlaps"),
    ("gym_mode_conflicts", "Gym mode conflicts"),
    ("precedence_violations", "Precedence violations"),
    ("rest_violation_count", "Back-to-back games (same team)"),
    ("volleyball_adjacent_switches", "Volleyball adjacent Men/Women switches"),
    ("latest_finish", "Latest finish (any day)"),
)


def _slot_text(slot: str) -> str:
    try:
        day, time = _parse_slot_label(slot)
        return f"{day} {time}"
    except (ValueError, AttributeError):
        return _clean(slot)


def _matchup(game: Mapping[str, Any]) -> str:
    labels = game.get("team_labels") or game.get("team_ids") or []
    return " / ".join(labels) if len(labels) > 2 else " v ".join(labels)


def _pair_key(row: Mapping[str, Any]) -> Tuple[str, str]:
    return (row["game_a_id"], row["game_b_id"])


def _pair_text(row: Mapping[str, Any]) -> str:
    return (
        f"{row['game_a_id']} vs {row['game_b_id']} "
        f"({row['shared_count']} shared: {', '.join(row['shared_participant_names']) or 'n/a'})"
    )


def decide_verdict(
    baseline_audit: Mapping[str, Any],
    optimized_audit: Optional[Mapping[str, Any]],
    moved_count: int,
    repairable_count: int,
) -> Tuple[str, str]:
    """Label the result.  Leadership decides; this only names what the numbers show."""
    if baseline_audit["hard_violation_count"]:
        return (
            VERDICT_BASELINE_INVALID,
            f"the approved baseline has {baseline_audit['hard_violation_count']} hard "
            "violation(s) against the reconciled venue model",
        )
    if optimized_audit is None:
        return VERDICT_NO_SOLUTION, "the solver returned no schedule"
    before = (baseline_audit["primary_conflict_penalty"], baseline_audit["secondary_conflict_penalty"])
    after = (optimized_audit["primary_conflict_penalty"], optimized_audit["secondary_conflict_penalty"])
    if after >= before:
        return VERDICT_NO_IMPROVEMENT, "no legal move reduces shared-athlete conflicts"
    removed = sum(before) - sum(after)
    share = moved_count / repairable_count if repairable_count else 0.0
    gain = removed / moved_count if moved_count else float(removed)
    detail = (
        f"{removed} athlete clash(es) removed by moving {moved_count} of "
        f"{repairable_count} repairable game(s) ({share:.0%})"
    )
    if share <= ACCEPTABLE_MAX_MOVE_SHARE and gain >= ACCEPTABLE_MIN_GAIN_PER_MOVE:
        return VERDICT_ACCEPTABLE, detail
    return VERDICT_MARGINAL, detail


def build_comparison(
    problem: Mapping[str, Any],
    solve_result: Mapping[str, Any],
    *,
    frontier: Optional[Sequence[Mapping[str, Any]]] = None,
    parameters: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the review artifact: metrics, moves, conflicts, verdict."""
    ctx = _Context(problem)
    games = {g["game_id"]: g for g in problem["games"]}
    baseline = baseline_placements(problem)
    baseline_audit = audit_placements(problem, baseline)
    solved = solve_result["status"] in (STATUS_OPTIMAL, STATUS_FEASIBLE)
    optimized = dict(solve_result["placements"]) if solved else {}
    optimized_audit = audit_placements(problem, optimized) if solved else None

    metrics = []
    for key, label in _METRICS:
        before = baseline_audit[key]
        after = optimized_audit[key] if optimized_audit else None
        delta = (
            after - before
            if isinstance(before, int) and isinstance(after, int) else None
        )
        metrics.append({"metric": key, "label": label, "baseline": before,
                        "optimized": after, "delta": delta})

    before_pairs = {_pair_key(r): r for r in baseline_audit["conflict_pairs"]}
    after_pairs = {_pair_key(r): r for r in (optimized_audit or {}).get("conflict_pairs", [])}
    conflicts = []
    for key, row in before_pairs.items():
        status = "remaining" if key in after_pairs else "removed"
        conflicts.append({**(after_pairs.get(key) or row), "status": status,
                          "baseline_slot_a": row["slot_a"], "baseline_slot_b": row["slot_b"]})
    for key, row in after_pairs.items():
        if key not in before_pairs:
            conflicts.append({**row, "status": "introduced",
                              "baseline_slot_a": None, "baseline_slot_b": None})
    order = {"removed": 0, "remaining": 1, "introduced": 2}
    conflicts.sort(key=lambda r: (order[r["status"]], -r["primary"], -r["secondary"],
                                  r["game_a_id"], r["game_b_id"]))

    def _describe(game_id: str, placement: Optional[Mapping[str, str]]) -> Dict[str, Any]:
        if not placement:
            return {"resource_id": None, "slot": None, "court": None}
        return {
            "resource_id": placement["resource_id"],
            "slot": placement["slot"],
            "court": ctx.court_label(placement["resource_id"]),
        }

    rows = []
    moved_games = []
    for game_id, game in games.items():
        if game["origin"] != "approved_baseline":
            continue
        before = baseline.get(game_id)
        after = optimized.get(game_id) if solved else before
        base_info = ctx.geometry(game, before["resource_id"], before["slot"]) if before else None
        new_info = ctx.geometry(game, after["resource_id"], after["slot"]) if after else None
        moved_time = bool(base_info and new_info and base_info["start"] != new_info["start"])
        moved_court = bool(base_info and new_info and base_info["court"] != new_info["court"])
        moved_day = bool(base_info and new_info and base_info["day"] != new_info["day"])
        row = {
            "game_id": game_id,
            "event": game["event"],
            "stage": game["stage"],
            "matchup": _matchup(game),
            "placement_policy": game["placement_policy"],
            "baseline": _describe(game_id, before),
            "optimized": _describe(game_id, after),
            "moved": moved_time or moved_court,
            "moved_time": moved_time,
            "moved_court": moved_court,
            "moved_day": moved_day,
            "move_minutes": (
                abs(new_info["start"] - base_info["start"])
                if base_info and new_info and base_info["start"] is not None
                and new_info["start"] is not None else 0
            ),
            "provenance": game["provenance"],
        }
        if row["moved"]:
            removed = [_pair_text(r) for r in conflicts
                       if r["status"] == "removed" and game_id in _pair_key(r)]
            added = [_pair_text(r) for r in conflicts
                     if r["status"] == "introduced" and game_id in _pair_key(r)]
            row["conflicts_removed"] = removed
            row["conflicts_introduced"] = added
            row["reason"] = (
                "Removes " + "; ".join(removed) if removed
                else "Makes room for another move (no conflict of its own)"
            )
            moved_games.append(row)
        rows.append(row)
    for game in problem.get("deferred_games", []):
        placement = {"resource_id": game["baseline_resource_id"], "slot": game["baseline_slot"]}
        rows.append({
            "game_id": game["game_id"],
            "event": game["event"],
            "stage": game["stage"],
            "matchup": _matchup(game),
            "placement_policy": "deferred",
            "baseline": _describe(game["game_id"], placement),
            "optimized": _describe(game["game_id"], placement),
            "moved": False, "moved_time": False, "moved_court": False, "moved_day": False,
            "move_minutes": 0,
            "provenance": game["provenance"],
        })

    def _row_order(row: Mapping[str, Any]) -> Tuple[int, str, str]:
        slot = row["optimized"]["slot"] or row["baseline"]["slot"] or ""
        try:
            minute = ctx.absolute_minutes(slot)
        except (ValueError, AttributeError):
            minute = 10 ** 9
        return (minute, row["optimized"]["court"] or "", row["game_id"])

    rows.sort(key=_row_order)
    moved_games.sort(key=_row_order)

    repairable = baseline_audit["repairable_games"]
    verdict, rationale = decide_verdict(
        baseline_audit, optimized_audit, len(moved_games), repairable
    )
    tiers = {tier["tier"]: tier for tier in solve_result.get("tiers", [])}
    conflicts_proven = all(
        tiers.get(name, {}).get("status") == STATUS_OPTIMAL
        for name in ("primary_conflict_penalty", "secondary_conflict_penalty")
    ) and solved
    movement = {
        "games_moved": len(moved_games),
        "repairable_games": repairable,
        "preliminary_games": baseline_audit["preliminary_games"] + len(problem.get("deferred_games", [])),
        "time_changes": sum(1 for r in moved_games if r["moved_time"]),
        "court_changes": sum(1 for r in moved_games if r["moved_court"]),
        "day_changes": sum(1 for r in moved_games if r["moved_day"]),
        "total_move_minutes": sum(r["move_minutes"] for r in moved_games),
        "max_move_minutes": max((r["move_minutes"] for r in moved_games), default=0),
    }

    summary_lines = [
        f"The approved baseline has {baseline_audit['conflict_pair_count']} shared-athlete "
        f"conflict(s): primary penalty {baseline_audit['primary_conflict_penalty']}, "
        f"secondary penalty {baseline_audit['secondary_conflict_penalty']}.",
    ]
    if baseline_audit["hard_violation_count"]:
        summary_lines.append(
            f"The baseline has {baseline_audit['hard_violation_count']} hard violation(s); "
            "the proposal below is a repair, not an optimization of a valid schedule."
        )
    if optimized_audit:
        removed_pairs = sum(1 for r in conflicts if r["status"] == "removed")
        summary_lines.append(
            f"Moving {movement['games_moved']} of {repairable} repairable preliminary game(s) "
            f"removes {removed_pairs} conflict(s), leaving "
            f"{optimized_audit['conflict_pair_count']} (primary penalty "
            f"{optimized_audit['primary_conflict_penalty']}, secondary penalty "
            f"{optimized_audit['secondary_conflict_penalty']})."
        )
        summary_lines.append(
            f"Movement: {movement['time_changes']} time change(s), "
            f"{movement['court_changes']} court change(s), {movement['total_move_minutes']} "
            f"total minute(s), largest single move {movement['max_move_minutes']} minute(s)."
        )
        if optimized_audit["conflict_pair_count"]:
            summary_lines.append(
                "The remaining conflict penalties are proven minimal under the current "
                "constraints." if conflicts_proven else
                "The remaining conflicts are NOT proven minimal: a conflict tier stopped "
                "at the time limit."
            )
    else:
        summary_lines.append(f"The solver returned no schedule (status {solve_result['status']}).")
    summary_lines.append(f"Verdict: {verdict} - {rationale}.")

    return {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "experimental": True,
        "note": (
            "Schedule-repair experiment (Issue #218). This proposal is not official "
            "until the human scheduler and Sports Fest leadership approve it."
        ),
        "verdict": verdict,
        "verdict_rationale": rationale,
        "summary_lines": summary_lines,
        "scope": {
            "repair_events": problem["repair_events"],
            "locked_context_events": problem["context_events"],
            "deferred_events": problem["deferred_events"],
            "unevaluated_conflict_edges": problem["unevaluated_edges"],
            "schedule_input_pins_overridden_by_baseline": problem["superseded_pins"],
            "schedule_input_pins_skipped": problem["skipped_pins"],
        },
        "parameters": {**problem["options"], **dict(parameters or {})},
        "solver": {
            "status": solve_result["status"],
            "solver_wall_seconds": solve_result.get("solver_wall_seconds", 0.0),
            "tiers": list(solve_result.get("tiers", [])),
            "conflict_tiers_proven_optimal": conflicts_proven,
            "unscheduled": list(solve_result.get("unscheduled", [])),
        },
        "metrics": metrics,
        "movement": movement,
        "moved_games": moved_games,
        "unchanged_game_ids": [r["game_id"] for r in rows if not r["moved"]],
        "conflicts": conflicts,
        "baseline_hard_violations": baseline_audit["hard_violations"],
        "optimized_hard_violations": (optimized_audit or {}).get("hard_violations", []),
        "baseline_rest_violations": baseline_audit["rest_violations"],
        "optimized_rest_violations": (optimized_audit or {}).get("rest_violations", []),
        "move_frontier": list(frontier or []),
        "games": rows,
    }


def build_optimized_output(
    comparison: Mapping[str, Any],
    solve_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """schedule_output-shaped document for the optimized placements."""
    assignments = []
    for row in comparison["games"]:
        placement = row["optimized"]
        if not placement["resource_id"] or not placement["slot"]:
            continue
        assignments.append({
            "game_id": row["game_id"],
            "resource_id": placement["resource_id"],
            "slot": placement["slot"],
            "event": row["event"],
            "stage": row["stage"] or None,
            "x_baseline_resource_id": row["baseline"]["resource_id"],
            "x_baseline_slot": row["baseline"]["slot"],
            "x_placement_policy": row["placement_policy"],
            "x_moved": row["moved"],
        })
    return {
        "solved_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "status": solve_result["status"],
        "solver_wall_seconds": solve_result.get("solver_wall_seconds", 0.0),
        "assignments": assignments,
        "unscheduled": list(solve_result.get("unscheduled", [])),
        "x_repair": {
            "experimental": True,
            "issue": 218,
            "verdict": comparison["verdict"],
            "summary_lines": comparison["summary_lines"],
            "movement": comparison["movement"],
            "scope": comparison["scope"],
        },
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_json(payload: Mapping[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_comparison_workbook(comparison: Mapping[str, Any], path: Path) -> None:
    """Render the comparison for the human scheduler."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill(fgColor="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    moved_fill = PatternFill(fgColor="FFF2CC", fill_type="solid")
    good_fill = PatternFill(fgColor="D9EAD3", fill_type="solid")
    bad_fill = PatternFill(fgColor="F4CCCC", fill_type="solid")

    def _sheet(wb, title: str, headers: Sequence[str], rows: Iterable[Sequence[Any]],
               fills: Optional[Sequence[Any]] = None):
        ws = wb.create_sheet(title)
        ws.append(list(headers))
        for cell in ws[1]:
            cell.fill, cell.font = header_fill, header_font
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        widths = [len(str(h)) for h in headers]
        for index, row in enumerate(rows):
            ws.append([("" if v is None else v) for v in row])
            fill = fills[index] if fills else None
            if fill is not None:
                for cell in ws[ws.max_row]:
                    cell.fill = fill
            for col, value in enumerate(row):
                widths[col] = max(widths[col], len(str(value if value is not None else "")))
        for col, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 10), 70)
        ws.freeze_panes = "A2"
        return ws

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary["A1"] = "Approved schedule repair experiment (Issue #218) - NOT OFFICIAL"
    summary["A1"].font = Font(bold=True, size=14)
    summary["A2"] = comparison["note"]
    row_no = 4
    for line in comparison["summary_lines"]:
        summary.cell(row=row_no, column=1, value=line)
        row_no += 1
    row_no += 1
    for col, text in enumerate(("Metric", "Baseline", "Optimized", "Change"), start=1):
        cell = summary.cell(row=row_no, column=col, value=text)
        cell.fill, cell.font = header_fill, header_font
    for metric in comparison["metrics"]:
        row_no += 1
        summary.cell(row=row_no, column=1, value=metric["label"])
        summary.cell(row=row_no, column=2, value=metric["baseline"])
        summary.cell(row=row_no, column=3, value=metric["optimized"])
        delta_cell = summary.cell(row=row_no, column=4, value=metric["delta"])
        if isinstance(metric["delta"], int) and metric["delta"]:
            delta_cell.fill = good_fill if metric["delta"] < 0 else bad_fill
    row_no += 2
    scope = comparison["scope"]
    scope_lines = [
        ("Repairable sports", ", ".join(scope["repair_events"]) or "none"),
        ("Locked but counted", ", ".join(scope["locked_context_events"]) or "none"),
        ("Deferred sports (carried through unchanged)",
         ", ".join(f"{d['event']} ({d['game_count']} games)" for d in scope["deferred_events"]) or "none"),
        ("Conflict edges not evaluated",
         "; ".join(f"{u['events_without_approved_games']}: {u['edge_count']}"
                   for u in scope["unevaluated_conflict_edges"]) or "none"),
        ("Solver status", comparison["solver"]["status"]),
    ]
    for label, value in scope_lines:
        summary.cell(row=row_no, column=1, value=label).font = Font(bold=True)
        summary.cell(row=row_no, column=2, value=value)
        row_no += 1
    summary.column_dimensions["A"].width = 48
    for letter in ("B", "C", "D"):
        summary.column_dimensions[letter].width = 16

    _sheet(
        wb, "Moved-Games",
        ["Game", "Sport", "Matchup", "Approved time", "Approved court", "Proposed time",
         "Proposed court", "Time changed", "Court changed", "Minutes moved", "Why",
         "Source workbook", "Source cell"],
        [
            [r["game_id"], r["event"], r["matchup"], _slot_text(r["baseline"]["slot"]),
             r["baseline"]["court"], _slot_text(r["optimized"]["slot"]), r["optimized"]["court"],
             "Yes" if r["moved_time"] else "", "Yes" if r["moved_court"] else "",
             r["move_minutes"], r["reason"],
             r["provenance"]["source_workbook"], r["provenance"]["source_cell"]]
            for r in comparison["moved_games"]
        ],
    )
    status_fill = {"removed": good_fill, "introduced": bad_fill, "remaining": None}
    _sheet(
        wb, "Conflicts",
        ["Status", "Game A", "Game B", "Sport A", "Sport B", "Primary", "Secondary",
         "Shared athletes", "Names", "Time A", "Time B", "Both locked"],
        [
            [r["status"], r["game_a_id"], r["game_b_id"], r["event_a"], r["event_b"],
             r["primary"], r["secondary"], r["shared_count"],
             ", ".join(r["shared_participant_names"]),
             _slot_text(r["slot_a"]), _slot_text(r["slot_b"]),
             "Yes" if r["both_locked"] else ""]
            for r in comparison["conflicts"]
        ],
        fills=[status_fill[r["status"]] for r in comparison["conflicts"]],
    )
    _sheet(
        wb, "Schedule",
        ["Proposed time", "Proposed court", "Game", "Sport", "Matchup", "Policy",
         "Approved time", "Approved court", "Moved"],
        [
            [_slot_text(r["optimized"]["slot"]), r["optimized"]["court"], r["game_id"],
             r["event"], r["matchup"], r["placement_policy"],
             _slot_text(r["baseline"]["slot"]), r["baseline"]["court"],
             "Yes" if r["moved"] else ""]
            for r in comparison["games"]
        ],
        fills=[moved_fill if r["moved"] else None for r in comparison["games"]],
    )
    _sheet(
        wb, "Baseline-Issues",
        ["Kind", "Games", "Detail"],
        [[v["kind"], ", ".join(v["game_ids"]), v["message"]]
         for v in comparison["baseline_hard_violations"]]
        or [["none", "", "The approved baseline has no hard violations."]],
    )
    if comparison["move_frontier"]:
        _sheet(
            wb, "Move-Frontier",
            ["Games allowed to move", "Primary penalty", "Secondary penalty", "Proven best"],
            [[r["max_moves"], r["primary_conflict_penalty"], r["secondary_conflict_penalty"],
              "Yes" if r["proven"] else "No"] for r in comparison["move_frontier"]],
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

def run_optimize_approved_schedule(
    *,
    input_path: Path,
    baseline_path: Path,
    comparison_path: Path,
    output_path: Path,
    workbook_path: Path,
    execute: bool,
    repair_events: Optional[Sequence[str]] = None,
    allow_cross_day: bool = False,
    max_move_minutes: Optional[int] = None,
    max_moves: Optional[int] = None,
    movement_priority: str = "time,court",
    rest_policy: str = "no_worse",
    rest_window_minutes: int = 0,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
    frontier: bool = True,
    frontier_limit: int = 15,
) -> int:
    """Run the experiment.

    Exit codes: 0 = comparison produced from a valid baseline; 1 = baseline
    invalid or no legal schedule; 2 = solver timed out with no schedule;
    3 = bad input.  A dry run writes the comparison JSON only.
    """
    input_path, baseline_path = Path(input_path), Path(baseline_path)
    comparison_path, output_path, workbook_path = (
        Path(comparison_path), Path(output_path), Path(workbook_path)
    )
    sources = {input_path.resolve(), baseline_path.resolve()}
    for label, target in (("--comparison", comparison_path), ("--output", output_path),
                          ("--workbook", workbook_path)):
        if target.name.casefold() in PROTECTED_OUTPUT_NAMES or target.resolve() in sources:
            logger.error(
                f"optimize-approved-schedule: {label} {target} would overwrite an official "
                "schedule file; choose another path."
            )
            return 3

    try:
        schedule_input = json.loads(input_path.read_text(encoding="utf-8"))
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        logger.error(f"optimize-approved-schedule: file not found: {exc.filename}")
        return 3
    except json.JSONDecodeError as exc:
        logger.error(f"optimize-approved-schedule: invalid JSON: {exc}")
        return 3

    try:
        problem = build_repair_problem(
            schedule_input,
            baseline,
            repair_events=repair_events,
            allow_cross_day=allow_cross_day,
            max_move_minutes=max_move_minutes,
            rest_window_minutes=rest_window_minutes,
        )
    except ValueError as exc:
        logger.error(f"optimize-approved-schedule: {exc}")
        return 3

    policies = Counter(g["placement_policy"] for g in problem["games"])
    logger.info(
        f"optimize-approved-schedule: {len(problem['games'])} game(s) in the model "
        f"({policies.get(POLICY_REPAIRABLE, 0)} repairable, {policies.get(POLICY_LOCKED, 0)} "
        f"locked), {len(problem['team_conflicts'])} shared-athlete edge(s), "
        f"{len(problem['resources'])} resource(s)"
    )
    logger.info(
        "optimize-approved-schedule: repairable sports: "
        + (", ".join(problem["repair_events"]) or "none")
    )
    for item in problem["deferred_events"]:
        logger.warning(
            f"optimize-approved-schedule: deferred {item['event']} "
            f"({item['game_count']} game(s)): {item['reason']}"
        )
    for item in problem["skipped_pins"]:
        logger.warning(
            f"optimize-approved-schedule: later-round pin {item['game_id']} reserves "
            f"nothing and was skipped: {item['reason']}"
        )
    if problem["superseded_pins"]:
        logger.warning(
            "optimize-approved-schedule: the approved baseline overrides a different "
            f"schedule_input pin for: {', '.join(problem['superseded_pins'])}"
        )
    for item in problem["unevaluated_edges"]:
        logger.warning(
            f"optimize-approved-schedule: {item['edge_count']} shared-athlete edge(s) not "
            f"evaluated: no approved games for {item['events_without_approved_games']}"
        )

    try:
        result = solve_repair(
            problem,
            timeout_seconds=timeout_seconds,
            max_moves=max_moves,
            movement_priority=movement_priority,
            rest_policy=rest_policy,
        )
    except ImportError:
        logger.error("ortools not installed. Run: pip install ortools>=9.8")
        return 3
    except ValueError as exc:
        logger.error(f"optimize-approved-schedule: {exc}")
        return 3

    solved = result["status"] in (STATUS_OPTIMAL, STATUS_FEASIBLE)
    frontier_rows: List[Dict[str, Any]] = []
    baseline_audit = result["baseline_audit"]
    if frontier and solved and not baseline_audit["hard_violation_count"]:
        moved_tier = next((t for t in result["tiers"] if t["tier"] == "games_moved"), None)
        budget = min(int(moved_tier["value"]), int(frontier_limit)) if moved_tier else 0
        if budget > 0:
            frontier_rows = compute_move_frontier(
                problem, max_budget=budget, timeout_seconds=timeout_seconds,
                rest_policy=rest_policy,
            )

    comparison = build_comparison(
        problem,
        result,
        frontier=frontier_rows,
        parameters={
            "max_moves": max_moves,
            "movement_priority": movement_priority,
            "rest_policy": rest_policy,
            "timeout_seconds": timeout_seconds,
            "random_seed": SCHEDULE_SOLVER_RANDOM_SEED,
            "schedule_input": str(input_path),
            "baseline": str(baseline_path),
        },
    )
    for line in comparison["summary_lines"]:
        logger.info(f"optimize-approved-schedule: {line}")
    for violation in comparison["baseline_hard_violations"]:
        logger.error(f"optimize-approved-schedule: baseline {violation['kind']}: {violation['message']}")
    for tier in result["tiers"]:
        logger.info(
            f"optimize-approved-schedule: tier {tier['tier']} = {tier['value']} "
            f"({tier['status']}, {tier['solver_wall_seconds']}s)"
        )
    for row in frontier_rows:
        logger.info(
            f"optimize-approved-schedule: with at most {row['max_moves']} move(s): primary "
            f"{row['primary_conflict_penalty']}, secondary {row['secondary_conflict_penalty']}"
        )

    write_json(comparison, comparison_path)
    logger.info(f"Comparison written to: {comparison_path.resolve()}")

    if execute and solved:
        output = build_optimized_output(comparison, result)
        try:
            for warning in validate_schedule_output(output):
                logger.warning(f"optimized schedule output contract: {warning}")
        except ScheduleContractError as exc:
            logger.error(
                f"optimize-approved-schedule: refusing to write a contract-violating "
                f"output ({len(exc.errors)} error(s)):"
            )
            for violation in exc.errors:
                logger.error(f"  - {violation}")
            return 3
        write_json(output, output_path)
        write_comparison_workbook(comparison, workbook_path)
        logger.info(f"Optimized schedule written to: {output_path.resolve()}")
        logger.info(f"Comparison workbook written to: {workbook_path.resolve()}")
        logger.info(
            "optimize-approved-schedule: nothing official was changed. The approved "
            "workbooks and schedule_output.json are untouched."
        )
    elif execute:
        logger.error("optimize-approved-schedule: no schedule to write.")
    else:
        logger.info("Dry run; rerun with --execute to write the optimized schedule and workbook.")

    if not solved:
        return 2 if result["status"] == STATUS_UNKNOWN else 1
    if comparison["verdict"] == VERDICT_BASELINE_INVALID:
        return 1
    return 0
