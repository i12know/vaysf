"""
scheduler.py — CP-SAT scheduler for VAY Sports Fest (Issue #93).

CLI:
    python main.py solve-schedule [--input path/to/schedule_input.json]

Reads  : schedule_input.json (written by export-church-teams, Issue #87/#96)
Writes : schedule_output.json to DATA_DIR (or --output path)
Exits  : 0 = OPTIMAL or FEASIBLE (all pools solved)
         1 = PARTIAL (some pools failed) / INFEASIBLE (no pools solved) / UNKNOWN
         2 = error (bad input or ortools missing)

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
  C5  Stage ordering — earlier_stage games finish before later_stage games start.
  C6  Minimum rest — no team plays in two adjacent global time slots.
  C7  Multi-slot games — a game whose duration > slot_minutes blocks consecutive slots.

Objective (per pool): minimize the index of the latest occupied global slot.

Out of scope (future work):
  - Cross-sport participant conflicts (a person in both Basketball and Badminton).
  - Church-requested blackout windows (earliest_slot / latest_slot fields are in
    the schema; wiring them up is a one-liner once they are populated upstream).
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

_DAY_ORDER: dict[str, int] = {"Sat-1": 0, "Sun-1": 1, "Sat-2": 2, "Sun-2": 3}
_DEFAULT_TIMEOUT = float(os.getenv("SCHEDULE_SOLVER_TIMEOUT", "30.0"))
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
    """Load schedule_input.json and validate required top-level keys."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("games", "resources", "precedence"):
        if key not in data:
            raise ValueError(f"schedule_input.json missing required key: {key!r}")
    return data


# ---------------------------------------------------------------------------
# Slot helpers
# ---------------------------------------------------------------------------

def _parse_time_minutes(time_str: str) -> int:
    """'HH:MM' → minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _slot_sort_key(label: str) -> tuple[int, int]:
    """Sort key for slot labels: (day_order, time_in_minutes).

    Label format: '{day}-{HH:MM}', e.g. 'Sat-1-08:00' or 'Day-1-09:30'.
    Unknown day labels are placed after known weekends (order 99).
    """
    day, time = label.rsplit("-", maxsplit=1)
    h, m = time.split(":")
    return (_DAY_ORDER.get(day, 99), int(h) * 60 + int(m))


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


def build_infeasibility_diagnostics(schedule_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Return lower-bound capacity diagnostics for operator-facing INFEASIBLE cases.

    The diagnostics intentionally stay simple:
    - `available_slots` = total start slots available across all resources of a type
    - `required_slots`  = sum of the minimum slots each game would occupy on any
      compatible resource of that type

    This does not prove why every infeasible solve failed, but it does surface
    obvious shortages such as "Badminton Court needs 24 slots, only 20 exist".
    """
    games: list[dict]     = schedule_input["games"]
    resources: list[dict] = schedule_input["resources"]
    res_slots = build_resource_slots(resources)

    resources_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        resources_by_type[resource["resource_type"]].append(resource)

    available_by_type: dict[str, int] = {}
    for resource_type, typed_resources in resources_by_type.items():
        available_by_type[resource_type] = sum(
            len(res_slots[resource["resource_id"]])
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

    pool_input must contain 'games', 'resources', and 'precedence' for a single
    resource_type.  Called by solve() once per pool.

    Returns a dict with keys:
        status              : 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE' | 'UNKNOWN'
        solver_wall_seconds : float
        assignments         : list of {game_id, resource_id, slot}
        unscheduled         : list of game_ids the solver could not place
        diagnostics         : (only present when status is not OPTIMAL/FEASIBLE)
                              lower-bound capacity summary for this pool
    """
    from ortools.sat.python import cp_model  # import guard

    games:      list[dict] = pool_input["games"]
    resources:  list[dict] = pool_input["resources"]
    precedence: list[dict] = pool_input.get("precedence", [])

    res_by_id:   dict[str, dict]        = {r["resource_id"]: r for r in resources}
    res_slots:   dict[str, list[str]]   = build_resource_slots(resources)

    # C4 — court-type routing (within this pool all games share one resource_type,
    # but res_by_type keeps the structure consistent with the constraint code)
    res_by_type: dict[str, list[str]] = {}
    for r in resources:
        res_by_type.setdefault(r["resource_type"], []).append(r["resource_id"])

    # Build global slot ordering for C5 (stage ordering) and C6 (min rest)
    all_labels: set[str] = set()
    for slots in res_slots.values():
        all_labels.update(slots)
    sorted_labels  = sorted(all_labels, key=_slot_sort_key)
    slot_to_global = {lbl: i for i, lbl in enumerate(sorted_labels)}
    # Map global slot index → day prefix (e.g. "Sat-1") for C6 day-boundary guard
    global_to_day: dict[int, str] = {
        i: lbl.rsplit("-", maxsplit=1)[0]
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

        game_vars[gid] = {}
        for rid in compatible:
            slots    = res_slots[rid]
            slot_min = res_by_id[rid]["slot_minutes"]
            # C7 — multi-slot: game occupies ceil(duration/slot_min) consecutive slots
            n_slots  = max(1, math.ceil(duration / slot_min))
            for t in range(len(slots) - n_slots + 1):
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
        teams    = [t for t in (game.get("team_a_id"), game.get("team_b_id")) if t]
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

    # Global slot IntVar per game (enables C5 and C6)
    game_global_slot: dict[str, Any] = {}
    for gid, vd in game_vars.items():
        if not vd:
            continue
        gv = model.NewIntVar(0, max(n_global - 1, 0), f"gslot_{gid}")
        game_global_slot[gid] = gv
        for (rid, t), var in vd.items():
            label = res_slots[rid][t]
            model.Add(gv == slot_to_global[label]).OnlyEnforceIf(var)

    # C5 — stage ordering: every earlier_stage game must precede every later_stage game
    by_event_stage: dict[tuple[str, str], list[str]] = {}
    for game in games:
        key = (game["event"], game["stage"])
        by_event_stage.setdefault(key, []).append(game["game_id"])

    for rule in precedence:
        event       = rule["event"]
        earlier_gids = by_event_stage.get((event, rule["earlier_stage"]), [])
        later_gids   = by_event_stage.get((event, rule["later_stage"]),   [])
        for g_e in earlier_gids:
            for g_l in later_gids:
                if g_e in game_global_slot and g_l in game_global_slot:
                    model.Add(game_global_slot[g_l] > game_global_slot[g_e])

    # C9 — finale sequence: enforce exact ordering between named game IDs
    # Rules where one or both game IDs are absent from this pool are silently skipped
    # (cross-resource-type finale pairs live in separate pools; handle them via C8).
    for rule in pool_input.get("sequence", []):
        g_e = rule.get("earlier_game_id")
        g_l = rule.get("later_game_id")
        if g_e in game_global_slot and g_l in game_global_slot:
            model.Add(game_global_slot[g_l] > game_global_slot[g_e])

    # C6 — minimum rest: no team plays in two adjacent global slots
    team_global_assignments: dict[str, dict[int, list[Any]]] = {}
    for gid, vd in game_vars.items():
        game  = game_meta[gid]
        teams = [t for t in (game.get("team_a_id"), game.get("team_b_id")) if t]
        for (rid, t), var in vd.items():
            label      = res_slots[rid][t]
            global_idx = slot_to_global[label]
            for team in teams:
                team_global_assignments.setdefault(team, {}).setdefault(global_idx, []).append(var)

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

    # C8 — per-game time windows (earliest_slot / latest_slot from schedule_input.json)
    for game in games:
        gid = game["game_id"]
        if gid not in game_global_slot:
            continue
        lo_label = game.get("earliest_slot")
        hi_label = game.get("latest_slot")
        if lo_label:
            lo = slot_to_global.get(lo_label)
            if lo is not None:
                model.Add(game_global_slot[gid] >= lo)
            else:
                logger.warning(f"Game {gid!r}: earliest_slot {lo_label!r} not in this pool's slots; ignored")
        if hi_label:
            hi = slot_to_global.get(hi_label)
            if hi is not None:
                model.Add(game_global_slot[gid] <= hi)
            else:
                logger.warning(f"Game {gid!r}: latest_slot {hi_label!r} not in this pool's slots; ignored")

    # Objective — minimize the latest occupied global slot (pack games toward start)
    if game_global_slot:
        latest = model.NewIntVar(0, max(n_global - 1, 0), "latest_slot")
        for gv in game_global_slot.values():
            model.Add(latest >= gv)
        model.Minimize(latest)

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
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

    result: dict[str, Any] = {
        "status":              status,
        "solver_wall_seconds": round(wall_time, 3),
        "assignments":         assignments,
        "unscheduled":         unscheduled,
    }
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
    games:      list[dict] = schedule_input["games"]
    resources:  list[dict] = schedule_input["resources"]
    precedence: list[dict] = schedule_input.get("precedence", [])

    # Partition games and resources by resource_type
    games_by_type:     dict[str, list[dict]] = {}
    for g in games:
        games_by_type.setdefault(g["resource_type"], []).append(g)

    resources_by_type: dict[str, list[dict]] = {}
    for r in resources:
        resources_by_type.setdefault(r["resource_type"], []).append(r)

    # Route each precedence rule to its pool via event → resource_type
    event_to_type: dict[str, str] = {g["event"]: g["resource_type"] for g in games}
    precedence_by_type: dict[str, list[dict]] = {}
    for rule in precedence:
        rt = event_to_type.get(rule["event"])
        if rt:
            precedence_by_type.setdefault(rt, []).append(rule)

    # Route each sequence rule to its pool via game_id → resource_type.
    # Cross-pool rules (earlier and later in different pools) are sent to both
    # pools; _solve_one_pool silently skips rules where one ID is absent.
    game_id_to_type: dict[str, str] = {g["game_id"]: g["resource_type"] for g in games}
    sequence: list[dict] = schedule_input.get("sequence", [])
    sequence_by_type: dict[str, list[dict]] = {}
    for rule in sequence:
        types_touched: set[str] = set()
        for key in ("earlier_game_id", "later_game_id"):
            rt = game_id_to_type.get(rule.get(key, ""))
            if rt:
                types_touched.add(rt)
        for rt in types_touched:
            sequence_by_type.setdefault(rt, []).append(rule)

    if not games_by_type:
        return {
            "status":              STATUS_OPTIMAL,
            "solver_wall_seconds": 0.0,
            "assignments":         [],
            "unscheduled":         [],
            "pool_results":        [],
        }

    pool_results:       list[dict[str, Any]] = []
    all_assignments:    list[dict]           = []
    all_unscheduled:    list[str]            = []
    total_wall_seconds: float                = 0.0

    for resource_type in sorted(games_by_type.keys()):
        pool_input = {
            "games":      games_by_type[resource_type],
            "resources":  resources_by_type.get(resource_type, []),
            "precedence": precedence_by_type.get(resource_type, []),
            "sequence":   sequence_by_type.get(resource_type, []),
        }
        result = _solve_one_pool(pool_input, timeout_seconds)
        result["resource_type"] = resource_type
        pool_results.append(result)
        all_assignments.extend(result["assignments"])
        all_unscheduled.extend(result["unscheduled"])
        total_wall_seconds += result["solver_wall_seconds"]
        logger.info(
            f"Pool {resource_type!r}: status={result['status']}, "
            f"assigned={len(result['assignments'])}, "
            f"unscheduled={len(result['unscheduled'])}"
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

    logger.info(
        f"Solver (all pools): status={top_status}, "
        f"wall_time={total_wall_seconds:.3f}s, "
        f"assigned={len(all_assignments)}, unscheduled={len(all_unscheduled)}, "
        f"pools={len(pool_results)}"
    )

    return {
        "status":              top_status,
        "solver_wall_seconds": round(total_wall_seconds, 3),
        "assignments":         all_assignments,
        "unscheduled":         all_unscheduled,
        "pool_results":        pool_results,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_solve_schedule(input_path: Path, output_path: Path) -> int:
    """Load schedule_input.json, solve, write schedule_output.json.

    Returns exit code:
        0 = OPTIMAL or FEASIBLE (every pool solved)
        1 = PARTIAL (some pools failed) / INFEASIBLE / UNKNOWN
        2 = error (missing input, bad JSON, ortools not installed)
    """
    try:
        schedule_input = load_schedule_input(input_path)
    except Exception as e:
        logger.error(f"Failed to load {input_path}: {e}")
        return 2

    logger.info(
        f"Loaded {len(schedule_input['games'])} games, "
        f"{len(schedule_input['resources'])} resources from {input_path}"
    )

    try:
        result = solve(schedule_input)
    except ImportError:
        logger.error("ortools not installed. Run: pip install ortools>=9.8")
        return 2
    except Exception as e:
        logger.error(f"Solver error: {e}", exc_info=True)
        return 2

    output = {
        "solved_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        **result,
    }

    try:
        output_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"schedule_output.json written to {output_path}")
    except OSError as e:
        logger.error(f"Failed to write {output_path}: {e}")
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

    if result["status"] == STATUS_UNKNOWN:
        logger.warning("Solver timed out or reached resource limit without a solution.")
        return 1

    return 0
