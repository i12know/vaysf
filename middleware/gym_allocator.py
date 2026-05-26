"""
gym_allocator.py — Layer-2, Stage A: greedy gym mode allocator.

Each physical gym can be configured in mutually-exclusive modes (e.g. Orange
Gym is either 1 Basketball Court OR 2 Volleyball Courts per time block, never
both).  This module decides which mode each gym block gets, structurally
enforcing the exclusivity that the CP-SAT solver (Stage B) cannot handle
across independent per-sport models.

Algorithm — scarcity-aware greedy priority
-----------------------------------------
1. Rank sport modes by scarcity first:
   fewer eligible gyms / blocks first, then higher demand pressure.
2. For each mode in priority order:
   a. Find eligible gyms (non-zero capacity for this mode).
   b. Sort gyms by specialization first (preserve flexible gyms for modes
      that need them), then switch penalty, then courts-per-block DESC.
   c. Within each gym, claim contiguous unallocated blocks (earliest first)
      until demand is satisfied.
3. After all allocations, count total mode switches (consecutive blocks in the
   same gym assigned to different modes).

Inputs
------
demand    : {mode_resource_type: court_hours_needed}
            Build from venue_capacity_rows via aggregate_demand_by_mode().
gym_modes : {gym_name: {mode_resource_type: courts_per_block}}
            Loaded by ScheduleWorkbookBuilder._load_gym_modes().
blocks    : List[GymBlock]
            Unique allocatable time windows; build from venue resource rows
            via extract_gym_blocks().

Outputs
-------
AllocationResult with decisions, mode_supply, mode_demand, mode_shortfall,
and switch_count.  Shortfall is positive when demand exceeds available
capacity — reported but never a crash.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from config import SPORT_TYPE


# ---------------------------------------------------------------------------
# Mode → sport family mapping
# ---------------------------------------------------------------------------

# Maps every event name that may appear in venue_capacity_rows["Event"] to the
# Gym-Modes resource_type that serves it. Events not listed here (Bible
# Challenge, Soccer, Track & Field, etc.) are not subject to gym-mode
# allocation in the current pipeline.
EVENT_TO_MODE: Dict[str, str] = {
    SPORT_TYPE["BASKETBALL"]:       "Basketball Court",
    SPORT_TYPE["VOLLEYBALL_MEN"]:   "Volleyball Court",
    SPORT_TYPE["VOLLEYBALL_WOMEN"]: "Volleyball Court",
    SPORT_TYPE["BADMINTON"]:        "Badminton Court",
    SPORT_TYPE["PICKLEBALL"]:       "Pickleball Court",
    SPORT_TYPE["PICKLEBALL_35"]:    "Pickleball Court",
    SPORT_TYPE["TENNIS"]:           "Tennis Court",
    SPORT_TYPE["TABLE_TENNIS"]:     "Table Tennis Table",
    SPORT_TYPE["TABLE_TENNIS_35"]:  "Table Tennis Table",
}

def _day_sort_key(day_label: str) -> tuple[int, int, str]:
    """Sort logical day labels like Fri-1, Sat-1, Sun-2 chronologically."""
    cleaned = str(day_label or "").strip()
    if not cleaned:
        return (99, 99, "")
    if "-" not in cleaned:
        return (99, 99, cleaned)
    prefix, suffix = cleaned.split("-", 1)
    try:
        cycle = int(suffix)
    except ValueError:
        return (99, 99, cleaned)
    weekday_order = {
        "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
        "Fri": 4, "Sat": 5, "Sun": 6, "Day": 7,
    }
    return (cycle, weekday_order.get(prefix, 99), cleaned)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GymBlock:
    """One unique allocatable time window in one gym."""
    gym_name: str
    day: str
    open_time: str   # "HH:MM"
    close_time: str  # "HH:MM"  (last_start + slot_min; last game ends here)
    slot_minutes: int
    resource_types: frozenset = frozenset()  # resource_types from rows collapsed here


@dataclass
class AllocationDecision:
    """Assignment of one GymBlock to one sport mode."""
    gym_name: str
    day: str
    open_time: str
    close_time: str
    mode: str         # e.g. "Basketball Court", "Volleyball Court"
    courts: int       # courts the gym yields under this mode
    slot_minutes: int = 60  # inherited from the GymBlock


@dataclass
class AllocationResult:
    """Full output of the greedy gym mode allocator."""
    decisions: List[AllocationDecision]
    mode_supply: Dict[str, float]    # mode → court-hours allocated
    mode_demand: Dict[str, float]    # mode → court-hours requested
    mode_shortfall: Dict[str, float] # mode → max(0, demand − supply)
    switch_count: int                # total mode switches across all gyms


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def extract_gym_blocks(venue_rows: List[Dict]) -> List[GymBlock]:
    """Collapse expanded venue resource rows into unique GymBlock objects.

    venue_rows is the output of ScheduleWorkbookBuilder._load_venue_input_rows().
    Rows for the same (exclusive_group, day, open_time, close_time, slot_minutes)
    are deduplicated — the per-court Quantity expansion is irrelevant here; the
    allocator works at the block level, not the individual-court level.

    Each GymBlock records the set of resource_types from the rows that were
    collapsed into it.  The allocator uses this to prefer assigning a block to
    the mode(s) that explicitly defined that time window, preventing a mode
    from claiming a block that was authored for a different mode.

    Rows without an exclusive_group are skipped; those are standalone resources
    that are never subject to gym-mode allocation.
    """
    seen_order: List[tuple] = []
    rt_map: dict = {}
    for row in venue_rows:
        grp = (row.get("exclusive_group") or "").strip()
        if not grp:
            continue
        key = (grp, row["day"], row["open_time"], row["close_time"], row["slot_minutes"])
        if key not in rt_map:
            seen_order.append(key)
            rt_map[key] = set()
        rt = (row.get("resource_type") or "").strip()
        if rt:
            rt_map[key].add(rt)
    return [
        GymBlock(
            gym_name=key[0],
            day=key[1],
            open_time=key[2],
            close_time=key[3],
            slot_minutes=key[4],
            resource_types=frozenset(rt_map[key]),
        )
        for key in seen_order
    ]


def aggregate_demand_by_mode(venue_capacity_rows: List[Dict]) -> Dict[str, float]:
    """Sum Estimated Court Hours by gym mode across all events.

    venue_capacity_rows is the output of
    ScheduleWorkbookBuilder._build_venue_capacity_rows().
    Events without an EVENT_TO_MODE entry (Table Tennis, Tennis, Soccer, etc.)
    are skipped — they do not consume Stage-A gym allocator demand today.

    Volleyball Men + Women demand is aggregated under "Volleyball Court".

    Returns {mode_resource_type: total_court_hours}.
    """
    demand: Dict[str, float] = {}
    for row in venue_capacity_rows:
        mode = EVENT_TO_MODE.get(row.get("Event", ""))
        if mode is None:
            continue
        hours = float(row.get("Estimated Court Hours") or 0.0)
        demand[mode] = demand.get(mode, 0.0) + hours
    return demand


# ---------------------------------------------------------------------------
# Main allocator
# ---------------------------------------------------------------------------

def allocate(
    demand: Dict[str, float],
    gym_modes: Dict[str, Dict[str, int]],
    blocks: List[GymBlock],
    spreading_excluded_days: Optional[set] = None,
) -> AllocationResult:
    """Greedy priority gym mode allocator.

    Parameters
    ----------
    demand    : {mode_resource_type: court_hours_needed}
    gym_modes : {gym_name: {mode_resource_type: courts_per_block}}
    blocks    : unique GymBlock list from extract_gym_blocks()

    Returns an AllocationResult.  Never raises on demand/capacity mismatch —
    the shortfall field captures the gap instead.
    """
    def _mode_priority(mode: str) -> tuple[float, float, float, float, str]:
        eligible_blocks = [
            block for block in blocks
            if gym_modes.get(block.gym_name, {}).get(mode, 0) > 0
        ]
        eligible_gyms = {
            block.gym_name for block in eligible_blocks
        }
        total_supply = sum(
            _court_hours(block, gym_modes[block.gym_name][mode])
            for block in eligible_blocks
        )
        pressure = float("inf") if total_supply <= 0 else demand[mode] / total_supply
        return (
            len(eligible_gyms),
            len(eligible_blocks),
            -pressure,
            -demand[mode],
            mode,
        )

    # Scarcer modes go first so flexible gyms remain available for them.
    sorted_modes = sorted(demand, key=_mode_priority)

    available: set = set(blocks)
    decisions: List[AllocationDecision] = []
    mode_supply: Dict[str, float] = dict.fromkeys(demand, 0.0)

    for mode in sorted_modes:
        remaining = demand[mode]
        if remaining <= 0:
            continue

        # Eligible gyms for this mode sorted by:
        #   1. specialization ASC (use single-purpose gyms before flexible ones)
        #   2. switch_penalty ASC (prefer gyms that won't flip mode)
        #   3. courts DESC (cover remaining demand in fewer blocks)
        #   4. gym name (stable tie-break)
        eligible = [
            (g, gym_modes[g].get(mode, 0))
            for g in gym_modes
            if gym_modes[g].get(mode, 0) > 0
        ]
        eligible.sort(key=lambda x: (
            _active_mode_count(x[0], gym_modes),
            _switch_penalty(x[0], mode, decisions),
            -x[1],
            x[0],
        ))

        for gym_name, courts in eligible:
            if remaining <= 0:
                break

            # Claim unallocated blocks in this gym. Blocks whose resource_types
            # explicitly include this mode are preferred (sort key 0) over blocks
            # that were authored for a different mode but happen to share the same
            # (gym, day) window (sort key 1). Within each tier: earliest day first,
            # then earliest open_time.
            gym_blocks = sorted(
                [b for b in available if b.gym_name == gym_name],
                key=lambda b: (
                    0 if mode in b.resource_types else 1,
                    _day_sort_key(b.day),
                    b.open_time,
                ),
            )
            for block in gym_blocks:
                if remaining <= 0:
                    break
                # Honour the user's intent: if the block was explicitly authored
                # for specific modes (resource_types is non-empty) and this mode
                # is not among them, skip it.  This prevents, e.g., a large BB
                # demand from consuming a 13:00-17:00 block that the user defined
                # exclusively for Badminton.  Falls back to claiming any block
                # when resource_types is empty (legacy rows without type tracking).
                if block.resource_types and mode not in block.resource_types:
                    continue
                ch = _court_hours(block, courts)
                if ch <= 0:
                    continue
                _claim_physical_gym_window(available, block)
                decisions.append(AllocationDecision(
                    gym_name=gym_name,
                    day=block.day,
                    open_time=block.open_time,
                    close_time=block.close_time,
                    mode=mode,
                    courts=courts,
                    slot_minutes=block.slot_minutes,
                ))
                mode_supply[mode] += ch
                remaining -= ch

    # Spreading pass: claim any blocks still unclaimed after the demand-driven
    # pass.  This happens when demand for a mode was already met by earlier days
    # (e.g. BB/VB satisfied by Sat-1+Sun-1) but the user's venue_input also
    # defines capacity for that mode on a later day (e.g. Sat-2).  Providing
    # those extra resources costs nothing — the solver simply won't fill unused
    # slots — but it gives the CP-SAT pool more layout options, improving
    # convergence speed and solution quality.
    #
    # Days in spreading_excluded_days (typically Finals days with pinned playoff
    # slots) are skipped: those blocks are handled by the playoff-slot promotion
    # path in schedule_workbook.py and must not be pre-empted here.
    #
    # Only claim a block for a mode that explicitly defined it (mode in
    # block.resource_types) to avoid cross-contamination between modes.
    _skip_days = spreading_excluded_days or set()
    # Track blocks each mode has received in this pass for round-robin fairness.
    _spread_blocks_per_mode: Dict[str, int] = dict.fromkeys(sorted_modes, 0)
    for block in sorted(available, key=lambda b: (_day_sort_key(b.day), b.open_time)):
        if block.day in _skip_days:
            continue
        # Rank candidate modes: fewer spreading-pass blocks first (fairness), then
        # higher court count (efficiency), then original demand-priority order.
        candidates = [
            (mode, gym_modes.get(block.gym_name, {}).get(mode, 0))
            for mode in sorted_modes
            if gym_modes.get(block.gym_name, {}).get(mode, 0) > 0
            and mode in block.resource_types
        ]
        if not candidates:
            continue
        best_mode, best_courts = min(
            candidates,
            key=lambda mc: (_spread_blocks_per_mode[mc[0]], -mc[1], sorted_modes.index(mc[0])),
        )
        _claim_physical_gym_window(available, block)
        decisions.append(AllocationDecision(
            gym_name=block.gym_name,
            day=block.day,
            open_time=block.open_time,
            close_time=block.close_time,
            mode=best_mode,
            courts=best_courts,
            slot_minutes=block.slot_minutes,
        ))
        mode_supply[best_mode] += _court_hours(block, best_courts)
        _spread_blocks_per_mode[best_mode] += 1

    return AllocationResult(
        decisions=decisions,
        mode_supply=mode_supply,
        mode_demand=dict(demand),
        mode_shortfall={
            m: max(0.0, demand[m] - mode_supply.get(m, 0.0))
            for m in demand
        },
        switch_count=_count_switches(decisions),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_time(t: str) -> float:
    """Parse "HH:MM" to decimal hours."""
    h, m = t.split(":")
    return int(h) + int(m) / 60.0


def _court_hours(block: GymBlock, courts: int) -> float:
    """Court-hours a block provides at a given court count."""
    duration = max(0.0, _parse_time(block.close_time) - _parse_time(block.open_time))
    return courts * duration


def _blocks_overlap_same_gym(left: GymBlock, right: GymBlock) -> bool:
    """Return True when two blocks consume the same physical gym time."""
    if left.gym_name != right.gym_name or left.day != right.day:
        return False
    return (
        _parse_time(left.open_time) < _parse_time(right.close_time)
        and _parse_time(right.open_time) < _parse_time(left.close_time)
    )


def _claim_physical_gym_window(available: set[GymBlock], block: GymBlock) -> None:
    """Remove the claimed window while preserving non-overlapping fragments."""
    replacements: set[GymBlock] = set()
    for candidate in list(available):
        if not _blocks_overlap_same_gym(block, candidate):
            continue
        available.discard(candidate)
        if candidate == block:
            continue

        candidate_open = _parse_time(candidate.open_time)
        candidate_close = _parse_time(candidate.close_time)
        claim_open = _parse_time(block.open_time)
        claim_close = _parse_time(block.close_time)

        if candidate_open < claim_open:
            before = GymBlock(
                gym_name=candidate.gym_name,
                day=candidate.day,
                open_time=candidate.open_time,
                close_time=block.open_time,
                slot_minutes=candidate.slot_minutes,
                resource_types=candidate.resource_types,
            )
            if _court_hours(before, 1) * 60 >= candidate.slot_minutes:
                replacements.add(before)

        if claim_close < candidate_close:
            after = GymBlock(
                gym_name=candidate.gym_name,
                day=candidate.day,
                open_time=block.close_time,
                close_time=candidate.close_time,
                slot_minutes=candidate.slot_minutes,
                resource_types=candidate.resource_types,
            )
            if _court_hours(after, 1) * 60 >= candidate.slot_minutes:
                replacements.add(after)

    available.update(replacements)


def _last_mode_in_gym(gym_name: str, decisions: List[AllocationDecision]) -> Optional[str]:
    """Return the mode of the chronologically latest decision for this gym, or None."""
    gym_decisions = [d for d in decisions if d.gym_name == gym_name]
    if not gym_decisions:
        return None
    latest = max(gym_decisions, key=lambda d: (_day_sort_key(d.day), d.open_time))
    return latest.mode


def _switch_penalty(gym_name: str, mode: str, decisions: List[AllocationDecision]) -> int:
    """Return 1 if assigning mode to this gym would create a switch, else 0."""
    last = _last_mode_in_gym(gym_name, decisions)
    return 0 if (last is None or last == mode) else 1


def _active_mode_count(gym_name: str, gym_modes: Dict[str, Dict[str, int]]) -> int:
    """Count how many sport modes this gym can host with non-zero capacity."""
    return sum(1 for courts in gym_modes.get(gym_name, {}).values() if courts > 0)


def _count_switches(decisions: List[AllocationDecision]) -> int:
    """Count consecutive mode changes across all gyms (summed, not per-gym)."""
    by_gym: Dict[str, List[AllocationDecision]] = {}
    for d in decisions:
        by_gym.setdefault(d.gym_name, []).append(d)

    total = 0
    for gym_decisions in by_gym.values():
        ordered = sorted(
            gym_decisions,
            key=lambda d: (_day_sort_key(d.day), d.open_time),
        )
        for i in range(1, len(ordered)):
            if ordered[i].mode != ordered[i - 1].mode:
                total += 1
    return total
