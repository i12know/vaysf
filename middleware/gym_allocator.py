"""
gym_allocator.py — Layer-2, Stage A: greedy gym mode allocator.

Each physical gym can be configured in mutually-exclusive modes (e.g. Orange
Gym is either 1 Basketball Court OR 2 Volleyball Courts per time block, never
both).  This module decides which mode each gym block gets, structurally
enforcing the exclusivity that the CP-SAT solver (Stage B) cannot handle
across independent per-sport models.

Algorithm — greedy priority
---------------------------
1. Rank sport modes by demand (court-hours needed), most-needed first.
2. For each mode in priority order:
   a. Find eligible gyms (non-zero capacity for this mode).
   b. Sort gyms by courts-per-block DESC; break ties by switch penalty
      (prefer gyms whose last allocated block already carries this mode, or
      fresh gyms with no allocation yet, over gyms that would require a
      mode flip).
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
# Gym-Modes resource_type that serves it.  Events not listed here (Table Tennis,
# Tennis, Bible Challenge, Track & Field, etc.) use dedicated pod courts and are
# not subject to gym-mode allocation.
EVENT_TO_MODE: Dict[str, str] = {
    SPORT_TYPE["BASKETBALL"]:       "Basketball Court",
    SPORT_TYPE["VOLLEYBALL_MEN"]:   "Volleyball Court",
    SPORT_TYPE["VOLLEYBALL_WOMEN"]: "Volleyball Court",
    SPORT_TYPE["SOCCER"]:           "Soccer Field",
    SPORT_TYPE["BADMINTON"]:        "Badminton Court",
    SPORT_TYPE["PICKLEBALL"]:       "Pickleball Court",
    SPORT_TYPE["PICKLEBALL_35"]:    "Pickleball Court",
}

# Canonical day ordering for contiguity-preserving block sort.
_DAY_ORDER: Dict[str, int] = {
    "Sat-1":  0,
    "Sun-1":  1,
    "Sat-2":  2,
    "Sun-2":  3,
    "Day-1":  0,   # pre-Day-column fallback (Issue #102; Day col added in #103)
}


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


@dataclass
class AllocationDecision:
    """Assignment of one GymBlock to one sport mode."""
    gym_name: str
    day: str
    open_time: str
    close_time: str
    mode: str    # e.g. "Basketball Court", "Volleyball Court"
    courts: int  # courts the gym yields under this mode


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

    Rows without an exclusive_group are skipped; those are standalone resources
    that are never subject to gym-mode allocation.
    """
    seen: set = set()
    blocks: List[GymBlock] = []
    for row in venue_rows:
        grp = (row.get("exclusive_group") or "").strip()
        if not grp:
            continue
        key = (grp, row["day"], row["open_time"], row["close_time"], row["slot_minutes"])
        if key not in seen:
            seen.add(key)
            blocks.append(GymBlock(
                gym_name=grp,
                day=row["day"],
                open_time=row["open_time"],
                close_time=row["close_time"],
                slot_minutes=row["slot_minutes"],
            ))
    return blocks


def aggregate_demand_by_mode(venue_capacity_rows: List[Dict]) -> Dict[str, float]:
    """Sum Estimated Court Hours by gym mode across all events.

    venue_capacity_rows is the output of
    ScheduleWorkbookBuilder._build_venue_capacity_rows().
    Events without an EVENT_TO_MODE entry (Table Tennis, Tennis, etc.) are
    skipped — they use dedicated pod courts, not gym floor space.

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
    # Sort modes by demand descending; alphabetical tie-break for stability.
    sorted_modes = sorted(demand, key=lambda m: (-demand[m], m))

    available: set = set(blocks)
    decisions: List[AllocationDecision] = []
    mode_supply: Dict[str, float] = dict.fromkeys(demand, 0.0)

    for mode in sorted_modes:
        remaining = demand[mode]
        if remaining <= 0:
            continue

        # Eligible gyms for this mode sorted by:
        #   1. courts DESC  (cover demand in fewest blocks)
        #   2. switch_penalty ASC  (prefer gyms that won't flip mode)
        #   3. gym name  (stable tie-break)
        eligible = [
            (g, gym_modes[g].get(mode, 0))
            for g in gym_modes
            if gym_modes[g].get(mode, 0) > 0
        ]
        eligible.sort(key=lambda x: (
            -x[1],
            _switch_penalty(x[0], mode, decisions),
            x[0],
        ))

        for gym_name, courts in eligible:
            if remaining <= 0:
                break

            # Claim unallocated blocks in this gym, earliest-first (contiguous).
            gym_blocks = sorted(
                [b for b in available if b.gym_name == gym_name],
                key=lambda b: (_DAY_ORDER.get(b.day, 99), b.open_time),
            )
            for block in gym_blocks:
                if remaining <= 0:
                    break
                ch = _court_hours(block, courts)
                if ch <= 0:
                    continue
                available.discard(block)
                decisions.append(AllocationDecision(
                    gym_name=gym_name,
                    day=block.day,
                    open_time=block.open_time,
                    close_time=block.close_time,
                    mode=mode,
                    courts=courts,
                ))
                mode_supply[mode] += ch
                remaining -= ch

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


def _last_mode_in_gym(gym_name: str, decisions: List[AllocationDecision]) -> Optional[str]:
    """Return the mode of the chronologically latest decision for this gym, or None."""
    gym_decisions = [d for d in decisions if d.gym_name == gym_name]
    if not gym_decisions:
        return None
    latest = max(gym_decisions, key=lambda d: (_DAY_ORDER.get(d.day, 99), d.open_time))
    return latest.mode


def _switch_penalty(gym_name: str, mode: str, decisions: List[AllocationDecision]) -> int:
    """Return 1 if assigning mode to this gym would create a switch, else 0."""
    last = _last_mode_in_gym(gym_name, decisions)
    return 0 if (last is None or last == mode) else 1


def _count_switches(decisions: List[AllocationDecision]) -> int:
    """Count consecutive mode changes across all gyms (summed, not per-gym)."""
    by_gym: Dict[str, List[AllocationDecision]] = {}
    for d in decisions:
        by_gym.setdefault(d.gym_name, []).append(d)

    total = 0
    for gym_decisions in by_gym.values():
        ordered = sorted(
            gym_decisions,
            key=lambda d: (_DAY_ORDER.get(d.day, 99), d.open_time),
        )
        for i in range(1, len(ordered)):
            if ordered[i].mode != ordered[i - 1].mode:
                total += 1
    return total
