"""
scheduler.py — CP-SAT scheduler for VAY Sports Fest (Issue #93).

CLI:
    python main.py solve-schedule [--input path/to/schedule_input.json]

Reads  : schedule_input.json (written by export-church-teams, Issue #87/#96)
Writes : schedule_output.json to DATA_DIR (or --output path)
Exits  : 0 = OPTIMAL or FEASIBLE, 1 = INFEASIBLE, 2 = error

Constraints implemented:
  C1  Each game assigned to exactly one (resource, start_slot).
  C2  Each (resource, slot) hosts at most one game (multi-slot aware).
  C3  No team plays two games in the same time slot.
  C4  Court-type routing — each game is assigned only to matching resource_type.
  C5  Stage ordering — earlier_stage games finish before later_stage games start.
  C6  Minimum rest — no team plays in two adjacent global time slots.
  C7  Multi-slot games — a game whose duration > slot_minutes blocks consecutive slots.

Objective: minimize the index of the latest occupied global slot (pack games early).

Out of scope for this issue (document for future work):
  - Cross-sport participant conflicts (a person in both Basketball and Badminton).
  - Church-requested blackout windows (earliest_slot / latest_slot fields are in
    the schema; wiring them up is a one-liner once they are populated upstream).
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

_DAY_ORDER: dict[str, int] = {"Sat-1": 0, "Sun-1": 1, "Sat-2": 2, "Sun-2": 3}
_DEFAULT_TIMEOUT = float(os.getenv("SCHEDULE_SOLVER_TIMEOUT", "30.0"))
_OUTPUT_FILENAME = "schedule_output.json"

STATUS_OPTIMAL = "OPTIMAL"
STATUS_FEASIBLE = "FEASIBLE"
STATUS_INFEASIBLE = "INFEASIBLE"
STATUS_UNKNOWN = "UNKNOWN"


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
        open_min = _parse_time_minutes(res["open_time"])
        close_min = _parse_time_minutes(res["close_time"])
        slot_min = res["slot_minutes"]
        day = res["day"]
        slots: list[str] = []
        t = open_min
        while t + slot_min <= close_min:
            slots.append(f"{day}-{t // 60:02d}:{t % 60:02d}")
            t += slot_min
        result[res["resource_id"]] = slots
    return result


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def solve(
    schedule_input: dict[str, Any],
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Build and solve the CP-SAT assignment model.

    Returns a dict with keys:
        status              : 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE' | 'UNKNOWN'
        solver_wall_seconds : float
        assignments         : list of {game_id, resource_id, slot}
        unscheduled         : list of game_ids the solver could not place
    """
    from ortools.sat.python import cp_model  # import guard — keeps module importable without ortools

    games: list[dict] = schedule_input["games"]
    resources: list[dict] = schedule_input["resources"]
    precedence: list[dict] = schedule_input.get("precedence", [])

    res_by_id: dict[str, dict] = {r["resource_id"]: r for r in resources}
    res_slots: dict[str, list[str]] = build_resource_slots(resources)

    # C4 — court-type routing: group resource IDs by resource_type
    res_by_type: dict[str, list[str]] = {}
    for r in resources:
        res_by_type.setdefault(r["resource_type"], []).append(r["resource_id"])

    # Build global slot ordering for C5 (stage ordering) and C6 (min rest)
    all_labels: set[str] = set()
    for slots in res_slots.values():
        all_labels.update(slots)
    sorted_labels = sorted(all_labels, key=_slot_sort_key)
    slot_to_global: dict[str, int] = {lbl: i for i, lbl in enumerate(sorted_labels)}
    n_global = len(sorted_labels)

    model = cp_model.CpModel()
    game_meta: dict[str, dict] = {g["game_id"]: g for g in games}

    # Decision variables: x[(gid, rid, t)] = BoolVar
    # True iff game gid starts on resource rid at slot index t.
    game_vars: dict[str, dict[tuple[str, int], Any]] = {}

    for game in games:
        gid = game["game_id"]
        resource_type = game["resource_type"]
        duration = game["duration_minutes"]
        compatible = res_by_type.get(resource_type, [])

        game_vars[gid] = {}
        for rid in compatible:
            slots = res_slots[rid]
            slot_min = res_by_id[rid]["slot_minutes"]
            # C7 — multi-slot: game occupies ceil(duration/slot_min) consecutive slots
            n_slots = max(1, math.ceil(duration / slot_min))
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
            n_slots = max(1, math.ceil(duration / slot_min))
            for s in range(t, t + n_slots):
                slot_occupancy.setdefault((rid, s), []).append(var)

    for (rid, s), var_list in slot_occupancy.items():
        if len(var_list) > 1:
            model.AddAtMostOne(var_list)

    # C3 — no team plays two games in the same time slot
    team_slot_vars: dict[tuple[str, str], list[Any]] = {}
    for gid, vd in game_vars.items():
        game = game_meta[gid]
        teams = [t for t in (game.get("team_a_id"), game.get("team_b_id")) if t]
        duration = game["duration_minutes"]
        for (rid, t), var in vd.items():
            slots = res_slots[rid]
            slot_min = res_by_id[rid]["slot_minutes"]
            n_slots = max(1, math.ceil(duration / slot_min))
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
        gv = model.NewIntVar(0, n_global - 1, f"gslot_{gid}")
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
        event = rule["event"]
        earlier_gids = by_event_stage.get((event, rule["earlier_stage"]), [])
        later_gids = by_event_stage.get((event, rule["later_stage"]), [])
        for g_e in earlier_gids:
            for g_l in later_gids:
                if g_e in game_global_slot and g_l in game_global_slot:
                    model.Add(game_global_slot[g_l] > game_global_slot[g_e])

    # C6 — minimum rest: no team plays in two adjacent global slots
    team_global_assignments: dict[str, dict[int, list[Any]]] = {}
    for gid, vd in game_vars.items():
        game = game_meta[gid]
        teams = [t for t in (game.get("team_a_id"), game.get("team_b_id")) if t]
        for (rid, t), var in vd.items():
            label = res_slots[rid][t]
            global_idx = slot_to_global[label]
            for team in teams:
                team_global_assignments.setdefault(team, {}).setdefault(global_idx, []).append(var)

    for team, by_idx in team_global_assignments.items():
        for g_idx, vars_at_g in by_idx.items():
            for v1 in vars_at_g:
                for v2 in by_idx.get(g_idx + 1, []):
                    # NOT (v1 AND v2) — at most one of adjacent-slot variables can be true
                    model.AddBoolOr([v1.Not(), v2.Not()])

    # Objective — minimize the latest occupied global slot (pack games toward start)
    if game_global_slot:
        latest = model.NewIntVar(0, n_global - 1, "latest_slot")
        for gv in game_global_slot.values():
            model.Add(latest >= gv)
        model.Minimize(latest)

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    status_code = solver.Solve(model)

    wall_time = solver.WallTime()
    status_name = solver.StatusName(status_code)

    status_map = {
        "OPTIMAL": STATUS_OPTIMAL,
        "FEASIBLE": STATUS_FEASIBLE,
        "INFEASIBLE": STATUS_INFEASIBLE,
    }
    status = status_map.get(status_name, STATUS_UNKNOWN)

    assignments: list[dict] = []
    unscheduled: list[str] = []

    if status in (STATUS_OPTIMAL, STATUS_FEASIBLE):
        for gid, vd in game_vars.items():
            assigned = False
            for (rid, t), var in vd.items():
                if solver.Value(var):
                    assignments.append({
                        "game_id": gid,
                        "resource_id": rid,
                        "slot": res_slots[rid][t],
                    })
                    assigned = True
                    break
            if not assigned:
                unscheduled.append(gid)
    else:
        unscheduled = [g["game_id"] for g in games]

    logger.info(
        f"Solver: status={status}, wall_time={wall_time:.3f}s, "
        f"assigned={len(assignments)}, unscheduled={len(unscheduled)}"
    )
    return {
        "status": status,
        "solver_wall_seconds": round(wall_time, 3),
        "assignments": assignments,
        "unscheduled": unscheduled,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_solve_schedule(input_path: Path, output_path: Path) -> int:
    """Load schedule_input.json, solve, write schedule_output.json.

    Returns exit code: 0 = OPTIMAL/FEASIBLE, 1 = INFEASIBLE/UNKNOWN, 2 = error.
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

    if result["status"] == STATUS_INFEASIBLE:
        logger.error("INFEASIBLE: no valid schedule exists with the current constraints.")
        return 1
    if result["status"] == STATUS_UNKNOWN:
        logger.warning("Solver timed out or reached resource limit without a solution.")
        return 1

    return 0
