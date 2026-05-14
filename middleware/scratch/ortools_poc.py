"""
ortools_poc.py  —  OR-Tools CP-SAT proof-of-concept for #90
THROWAWAY — lives under scratch/, not part of the main pipeline.

Purpose: learn what CP-SAT actually needs before writing the #87
normalized scheduling-input package.

Dependency: pip install ortools>=9.8  (also in requirements.txt)

Run:
    cd middleware
    python scratch/ortools_poc.py

What it does:
    - Hard-codes a realistic Basketball-Men pool-play fixture list using
      real VAY church codes (ANH, FVC, GAC, NSD, RPC, TLC).
    - Builds a CP-SAT model that assigns each game to a (court, time_slot).
    - Solves and prints the schedule.
    - Writes ortools_poc_report.md next to this script documenting the
      schema lessons learned for #87.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

@dataclass
class Game:
    game_id: str          # e.g. "BBM-P1-R1-G1"
    event: str            # full SPORT_TYPE label
    stage: str            # "Pool" | "Playoff" | "Final"
    pool_id: str          # "P1" | "P2" | "" for playoffs
    team_a_id: str        # church code
    team_b_id: str        # church code
    duration_minutes: int # must be a whole multiple of SLOT_MINUTES
    resource_type: str    # "Gym Court" | "Racquet Court" | "Field"


# Two balanced pools of 3 teams each; each team plays 2 pool games.
# Pool 1: ANH, FVC, GAC   (round-robin = 3 games)
# Pool 2: NSD, RPC, TLC   (round-robin = 3 games)
GAMES: list[Game] = [
    Game("BBM-P1-R1-G1", "Basketball - Men Team", "Pool", "P1", "ANH", "FVC", 60, "Gym Court"),
    Game("BBM-P1-R2-G1", "Basketball - Men Team", "Pool", "P1", "ANH", "GAC", 60, "Gym Court"),
    Game("BBM-P1-R3-G1", "Basketball - Men Team", "Pool", "P1", "FVC", "GAC", 60, "Gym Court"),
    Game("BBM-P2-R1-G1", "Basketball - Men Team", "Pool", "P2", "NSD", "RPC", 60, "Gym Court"),
    Game("BBM-P2-R2-G1", "Basketball - Men Team", "Pool", "P2", "NSD", "TLC", 60, "Gym Court"),
    Game("BBM-P2-R3-G1", "Basketball - Men Team", "Pool", "P2", "RPC", "TLC", 60, "Gym Court"),
]

# ---------------------------------------------------------------------------
# Venue / time parameters
# ---------------------------------------------------------------------------

COURTS: list[str] = ["Court-1", "Court-2", "Court-3", "Court-4"]

# 1st Saturday window: 08:00 – 20:00, one slot per hour.
DAY_LABEL = "Sat-1"
SLOT_START_HOUR = 8   # 08:00
SLOT_END_HOUR   = 20  # last game must START by 19:00 for a 60-min game
SLOT_MINUTES    = 60  # each slot = 1 hour

SLOTS: list[str] = [
    f"{DAY_LABEL}-{SLOT_START_HOUR + i:02d}:00"
    for i in range(SLOT_END_HOUR - SLOT_START_HOUR)
]  # ['Sat-1-08:00', 'Sat-1-09:00', ..., 'Sat-1-19:00']  — 12 slots


# ---------------------------------------------------------------------------
# CP-SAT model
# ---------------------------------------------------------------------------

def build_and_solve() -> Optional[dict[str, tuple[str, str]]]:
    """
    Build and solve the assignment model.

    Decision variables
    ------------------
    x[g, c, t] : BoolVar — game g is assigned to court c at time slot t.

    Constraints
    -----------
    C1  Each game assigned to exactly one (court, slot).
    C2  Each (court, slot) hosts at most one game.
    C3  Each team plays at most one game per slot
        (prevents a church playing two games simultaneously).

    Objective
    ---------
    Minimize the index of the latest occupied slot — packs games toward
    the start of the day.  A feasibility-only solve would also work.

    Returns
    -------
    Dict mapping game_id → (court_label, slot_label), or None if INFEASIBLE.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        raise SystemExit(
            "ortools not installed.  Run: pip install ortools>=9.8"
        )

    model = cp_model.CpModel()

    n_games  = len(GAMES)
    n_courts = len(COURTS)
    n_slots  = len(SLOTS)

    # x[g][c][t] = 1 iff game g is on court c at slot t
    x = [
        [
            [model.NewBoolVar(f"x_g{g}_c{c}_t{t}")
             for t in range(n_slots)]
            for c in range(n_courts)
        ]
        for g in range(n_games)
    ]

    # C1 — each game gets exactly one assignment
    for g in range(n_games):
        model.AddExactlyOne(
            x[g][c][t]
            for c in range(n_courts)
            for t in range(n_slots)
        )

    # C2 — each (court, slot) hosts at most one game
    for c in range(n_courts):
        for t in range(n_slots):
            model.AddAtMostOne(x[g][c][t] for g in range(n_games))

    # C3 — no team plays two games in the same slot
    # Build a lookup: team_id → list of game indices
    team_games: dict[str, list[int]] = {}
    for g, game in enumerate(GAMES):
        team_games.setdefault(game.team_a_id, []).append(g)
        team_games.setdefault(game.team_b_id, []).append(g)

    for team, game_indices in team_games.items():
        if len(game_indices) < 2:
            continue
        for t in range(n_slots):
            model.AddAtMostOne(
                x[g][c][t]
                for g in game_indices
                for c in range(n_courts)
            )

    # Objective — minimize the latest slot used (pack games early)
    latest_slot = model.NewIntVar(0, n_slots - 1, "latest_slot")
    for g in range(n_games):
        for c in range(n_courts):
            for t in range(n_slots):
                # if x[g][c][t] == 1 then latest_slot >= t
                model.Add(latest_slot >= t).OnlyEnforceIf(x[g][c][t])
    model.Minimize(latest_slot)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("SOLVER STATUS:", solver.StatusName(status))
        return None

    result: dict[str, tuple[str, str]] = {}
    for g, game in enumerate(GAMES):
        for c in range(n_courts):
            for t in range(n_slots):
                if solver.Value(x[g][c][t]):
                    result[game.game_id] = (COURTS[c], SLOTS[t])

    return result


# ---------------------------------------------------------------------------
# Pretty-print schedule
# ---------------------------------------------------------------------------

def print_schedule(assignment: dict[str, tuple[str, str]]) -> None:
    print("\n" + "=" * 60)
    print("  Basketball Men — Pool-Play Schedule (POC)")
    print("=" * 60)
    print(f"  {'Game ID':<18} {'Pool':<6} {'Teams':<14} {'Court':<12} {'Slot'}")
    print("  " + "-" * 58)
    game_map = {g.game_id: g for g in GAMES}
    for game_id, (court, slot) in sorted(assignment.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        g = game_map[game_id]
        teams = f"{g.team_a_id} vs {g.team_b_id}"
        print(f"  {game_id:<18} {g.pool_id:<6} {teams:<14} {court:<12} {slot}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

REPORT_PATH = Path(__file__).parent / "ortools_poc_report.md"

def write_report(assignment: Optional[dict[str, tuple[str, str]]]) -> None:
    schedule_lines: list[str] = []
    if assignment:
        game_map = {g.game_id: g for g in GAMES}
        for game_id, (court, slot) in sorted(
            assignment.items(), key=lambda kv: (kv[1][1], kv[1][0])
        ):
            g = game_map[game_id]
            schedule_lines.append(
                f"| {game_id} | {g.pool_id} | {g.team_a_id} vs {g.team_b_id} "
                f"| {court} | {slot} |"
            )
    schedule_table = "\n".join(schedule_lines) if schedule_lines else "_No feasible solution found._"

    report = textwrap.dedent(f"""\
    # OR-Tools CP-SAT POC — Schema Learning Report

    **Issue:** #90
    **Sport:** Basketball Men pool play
    **Status:** {'Solved ✓' if assignment else 'INFEASIBLE ✗'}
    **This file is a checked-in artifact from the throwaway POC. It becomes
    the input spec for #87.**

    ---

    ## Sample Schedule Output

    | Game ID | Pool | Teams | Court | Slot |
    |---------|------|-------|-------|------|
    {schedule_table}

    ---

    ## OR-Tools Constructs Used

    | Construct | Purpose |
    |-----------|---------|
    | `CpModel()` | Container for all variables and constraints |
    | `model.NewBoolVar(name)` | One variable per (game, court, slot) triple |
    | `model.NewIntVar(lo, hi, name)` | `latest_slot` objective variable |
    | `model.AddExactlyOne(literals)` | C1: each game assigned to exactly one slot/court |
    | `model.AddAtMostOne(literals)` | C2: one game per (court, slot); C3: one game per (team, slot) |
    | `model.Add(expr).OnlyEnforceIf(lit)` | Conditional bound for objective tracking |
    | `model.Minimize(var)` | Pack games toward start of day |
    | `CpSolver().Solve(model)` | Solve; check `OPTIMAL` or `FEASIBLE` status |
    | `solver.Value(var)` | Extract assignment from solved model |

    ---

    ## Input Fields the Model Actually Consumed

    From each `Game` object, the solver used:

    | Field | How the solver used it |
    |-------|------------------------|
    | `game_id` | Index key; also used as variable name suffix for debugging |
    | `team_a_id` | Team-conflict constraint (C3): no two games sharing this team in same slot |
    | `team_b_id` | Same as above |
    | `duration_minutes` | Implicitly assumed == `SLOT_MINUTES` (60 min); solver treated every game as exactly 1 slot |
    | `resource_type` | Used only to select which court pool to assign from (all courts were `"Gym Court"` here) |

    Fields that were **present in the fixture but not yet used by the model**:

    | Field | Why unused | What would need it |
    |-------|------------|--------------------|
    | `event` | Only one sport in POC | Multi-sport model: separate court pools by `resource_type` |
    | `stage` | Only pool play | Playoff model: add ordering constraints (pool must finish before playoff starts) |
    | `pool_id` | Not constrained | Could enforce all pool games finish before cross-pool matchups |

    ---

    ## What Had to Be Invented (Not in #85 Output)

    | Item | Invented value | What #87 must supply |
    |------|---------------|----------------------|
    | `team_a_id` / `team_b_id` | Hard-coded church codes | #87 must emit explicit team identifiers per game |
    | `pool_id` | Hard-coded `"P1"` / `"P2"` | #87 must emit a `pool_id` or `stage_group` field |
    | `game_id` structure | `BBM-P1-R2-G1` format (event-pool-round-game) | #87 should generate IDs in this format |
    | Slot duration in slots | Assumed `duration_minutes / SLOT_MINUTES == 1` | #87 should emit `duration_minutes`; solver divides by slot resolution |
    | Court labels | Hard-coded `["Court-1" … "Court-4"]` | Venue input (`venue_input.xlsx`) must supply labeled courts per `resource_type` |
    | Day/window | Hard-coded `Sat-1 08:00–20:00` | Venue input must supply `(day, open_time, close_time)` per resource type |

    ---

    ## Constraint Gaps Discovered

    These constraints were **not modelled** in this POC but will be needed:

    1. **Multi-slot games.** A 60-min game in a 30-min slot resolution blocks 2 consecutive slots
       on the same court. Requires either: (a) keep slot resolution = game duration (current
       approach, only works if all games in a sport have the same duration), or (b) add
       "game occupies slots t through t + n_slots_needed - 1" constraints using interval
       variables (`model.NewIntervalVar`).

    2. **Cross-sport participant conflicts.** A participant registered for both Basketball and
       Table Tennis must not have games scheduled at the same time. Requires a participant →
       games mapping, which #85/#88 produce but is not yet in any solver input.

    3. **Stage ordering.** Playoff games must be scheduled after all pool games finish.
       Requires `model.Add(playoff_slot > max_pool_slot)`.

    4. **Minimum rest between games.** A team that plays at slot T should not play again at
       slot T+1. Add: for each team, consecutive-slot pairs must not both be assigned.

    5. **Court-type routing.** Basketball games must go to `Gym Court`, racquet games to
       `Racquet Court`. Requires filtering the court pool before building variables, keyed on
       `resource_type`.

    ---

    ## Recommended #87 JSON Schema (Per Game Object)

    Based on what the model actually consumed and what it had to invent:

    ```json
    {{
      "game_id":          "BBM-P1-R2-G1",
      "event":            "Basketball - Men Team",
      "stage":            "Pool",
      "pool_id":          "P1",
      "round":            2,
      "team_a_id":        "ANH",
      "team_b_id":        "GAC",
      "duration_minutes": 60,
      "resource_type":    "Gym Court",
      "earliest_slot":    null,
      "latest_slot":      null
    }}
    ```

    And per venue resource:

    ```json
    {{
      "resource_id":    "GYM-1",
      "resource_type":  "Gym Court",
      "label":          "Court-1",
      "day":            "Sat-1",
      "open_time":      "08:00",
      "close_time":     "20:00",
      "slot_minutes":   60
    }}
    ```

    ### Field notes

    - `earliest_slot` / `latest_slot` — optional hard windows per game (e.g. a church requests
      no games before 10:00). `null` means unconstrained.
    - `round` — integer; enables stage-ordering constraints without string parsing.
    - `resource_type` — must match between game and venue resource for court-routing.
    - `pool_id` — empty string `""` for playoff / final games.

    ---

    ## Key Takeaway for #87

    The model is simple (≈ 30 lines of constraint code for 6 games × 4 courts × 12 slots).
    The hard part is not the solver — it is producing clean, typed game and venue objects
    upstream. Every field listed in "What Had to Be Invented" above is a field that #87's
    scheduling-input package must emit. The solver itself is almost mechanical once the input
    schema is right.
    """)

    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Report written → {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Games     : {len(GAMES)}")
    print(f"Courts    : {len(COURTS)}  ({', '.join(COURTS)})")
    print(f"Time slots: {len(SLOTS)}  ({SLOTS[0]} – {SLOTS[-1]})")
    print("\nSolving…")

    assignment = build_and_solve()

    if assignment:
        print_schedule(assignment)
    else:
        print("No feasible schedule found.")

    write_report(assignment)
