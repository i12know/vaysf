# Scheduling Pipeline

This document describes how VAY Sports Fest game schedules are produced —
from registration data to a readable Excel timetable — so future contributors
and Claude sessions do not need to reverse-engineer the design from code.

---

## Four-Step Pipeline

```
Step 1                  Step 2                  Step 3                  Step 4
export-church-teams  →  schedule_input.json  →  solve-schedule       →  export-schedule
                        + Schedule-Input tab    schedule_output.json    VAYSF_Schedule_*.xlsx
                        (Issue #87, done)       (Issue #93, done)       (Issue #94, done)
```

### Step 1 — Build scheduling inputs (`export-church-teams`)

```bash
python main.py export-church-teams
```

Produces the consolidated `Church_Team_Status_ALL.xlsx` in `EXPORT_DIR`.
When `middleware/data/venue_input.xlsx` is present, the workbook also gets a
**Schedule-Input** tab and a companion **`schedule_input.json`** (written
alongside the xlsx) containing:

- **`games`** — one object per match placeholder (pool rounds + playoff
  bracket for gym sports; single-elimination bracket for pod sports).
- **`resources`** — one object per physical court or table, expanded from
  `venue_input.xlsx` quantities, each annotated with day and time window.
- **`precedence`** — stage-ordering rules (e.g. Pool must finish before
  Semi-Final).

Key constants that shape the output live in `config.py`:
`SCHEDULE_SKETCH_SATURDAY_START`, `SCHEDULE_SKETCH_SATURDAY_LAST_GAME`,
`SCHEDULE_SKETCH_SUNDAY_START`, `SCHEDULE_SKETCH_SUNDAY_LAST_GAME`,
`COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME`, `GYM_RESOURCE_TYPE`.

### Step 2 — `schedule_input.json` schema (hardened by Issue #96)

The top-level object includes a `gym_court_scenario` field that records the
explicit court count used to build the gym resources for this run.  Change
`SCHEDULE_SOLVER_GYM_COURTS` in `config.py` (currently 4) to switch scenarios;
do not rely on any default inside the code.

Every **game object** looks like:

```json
{
  "game_id":          "BBM-01",
  "event":            "Basketball - Men Team",
  "stage":            "Pool",
  "pool_id":          "P1",
  "round":            1,
  "team_a_id":        "BBM-P1-T1",
  "team_b_id":        "BBM-P1-T2",
  "duration_minutes": 60,
  "resource_type":    "Gym Court",
  "earliest_slot":    null,
  "latest_slot":      null
}
```

**`team_a_id` / `team_b_id` in planning mode:**
- Pool games use stable placeholder IDs like `BBM-P1-T1`, `BBM-P1-T2`.
  The same placeholder ID is reused across every game that team plays, so
  the solver can enforce team-overlap (C3) and min-rest (C6) constraints
  even before final church assignments are known.
- Teams are grouped into balanced pools of size `gpg + 1` (full round-robin
  within each pool gives each team exactly `gpg` games).
- Playoff QF games use pool-seed references: `BBM-Seed-1`, `BBM-Seed-8`, etc.
- Playoff Semi/Final/3rd games use winner/loser references:
  `WIN-BBM-QF-1`, `WIN-BBM-Semi-1`, `LOSE-BBM-Semi-2`, etc.
- `null` is never emitted; every game has non-null `team_a_id` and `team_b_id`.

**`pool_id`:**
- Non-empty string (`"P1"`, `"P2"`, …) for pool games.
- Empty string `""` for all playoff/final games.

Every **resource object** looks like:

```json
{
  "resource_id":   "GYM-Sat-1-1",
  "resource_type": "Gym Court",
  "label":         "Court-1",
  "day":           "Sat-1",
  "open_time":     "08:00",
  "close_time":    "21:00",
  "slot_minutes":  60
}
```

**`gym_court_scenario`:** The number of gym courts used to build the `GYM-*`
resources in this run.  Controlled by `SCHEDULE_SOLVER_GYM_COURTS` in
`config.py`.  The solver reads this to know which scenario was selected —
no hidden defaults.

Every **precedence object** looks like:

```json
{
  "rule":          "All Pool before Semi",
  "event":         "Basketball - Men Team",
  "earlier_stage": "Pool",
  "later_stage":   "Semi"
}
```

Field notes:
- `resource_type` must match between game and resource; this is how the
  solver knows which court pool to draw from (C4 — court-type routing).
- `earliest_slot` / `latest_slot` are optional hard windows per game
  (`null` = unconstrained; wiring them up in the solver is a one-liner).
- Gym sports (Basketball, Volleyball Men, Volleyball Women) use
  `GYM_RESOURCE_TYPE = "Gym Court"`. Pod sports each have their own
  `POD_RESOURCE_TYPE_*` constant.

### Step 3 — CP-SAT solver (`solve-schedule`) — Issue #93 (done)

```bash
python main.py solve-schedule [--input path/to/schedule_input.json] [--output path/to/schedule_output.json]
```

Reads `schedule_input.json`, runs the OR-Tools CP-SAT model, writes
`schedule_output.json` to `DATA_DIR` (or `--output` path). Exit codes:
0 = OPTIMAL/FEASIBLE, 1 = INFEASIBLE, 2 = error (bad input or ortools missing).

Configurable timeout via `SCHEDULE_SOLVER_TIMEOUT` env var (default: 30 s).

Output shape:

```json
{
  "solved_at": "...",
  "status": "OPTIMAL",
  "solver_wall_seconds": 0.4,
  "assignments": [
    {"game_id": "BBM-P1-R2-G1", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-09:00"}
  ],
  "unscheduled": []
}
```

### Step 4 — Excel output (`produce-schedule`) — Issue #94 (done)

```bash
python main.py produce-schedule [--input path/to/schedule_output.json] [--constraint path/to/schedule_input.json] [--output path/to/VAYSF_Schedule.xlsx]
```

Reads `schedule_output.json`, writes `VAYSF_Schedule_YYYY-MM-DD.xlsx` to
`EXPORT_DIR`. Two tabs:

- **Schedule-by-Time** — grid view, color-coded by sport, for coordinators
  running the event floor.
- **Schedule-by-Sport** — flat list with auto-filter, for sport directors
  checking their division.

The JSON file stays in `DATA_DIR` as the machine-readable backup.

**Constraints implemented in `scheduler.py`:**

| ID | Constraint | CP-SAT construct |
|----|-----------|-----------------|
| C1 | Each game assigned to exactly one (resource, start_slot) | `AddExactlyOne` |
| C2 | Each (resource, slot) hosts at most one game (multi-slot aware) | `AddAtMostOne` |
| C3 | No team plays two games in the same time slot | `AddAtMostOne` per (team, slot_label) |
| C4 | Court-type routing — game assigned only to matching `resource_type` | filter before building vars |
| C5 | Stage ordering — earlier_stage games precede later_stage games | pairwise `Add(g_l_slot > g_e_slot)` on global slot IntVars |
| C6 | Minimum rest — no team plays in two adjacent global slots | `AddBoolOr([v1.Not(), v2.Not()])` for adjacent slot pairs |
| C7 | Multi-slot games — duration > slot_minutes blocks consecutive slots | restrict start positions; expand slot_occupancy |

**Out of scope (future work):**
- Cross-sport participant conflicts (person in both Basketball and Badminton).
- Church-requested blackout windows (`earliest_slot` / `latest_slot` fields
  already in the schema — wiring them up is a one-liner).

---

## OR-Tools POC — What Was Proven

Issue #90 ran a throwaway CP-SAT proof-of-concept against Basketball Men
pool play (6 games, 4 courts, 12 slots). It solved optimally in < 1 s and
validated the `schedule_input.json` schema. Full findings are in
`middleware/scratch/ortools_poc_report.md`.

**OR-Tools constructs used:**

| Construct | Purpose |
|-----------|---------|
| `CpModel()` | Container for variables and constraints |
| `model.NewBoolVar(name)` | One variable per (game, court, slot) triple |
| `model.AddExactlyOne(literals)` | Each game assigned to exactly one slot/court |
| `model.AddAtMostOne(literals)` | One game per (court, slot); one game per (team, slot) |
| `model.Minimize(var)` | Pack games toward start of day |
| `CpSolver().Solve(model)` | Solve; check `OPTIMAL` or `FEASIBLE` |

---

## Constraint Gaps (POC → Production)

All five constraints identified in the POC report have been implemented in
`middleware/scheduler.py` (Issue #93).  See the constraint table in the
Step 3 section above.

Remaining future work (out of scope for Issue #93):

- **Cross-sport participant conflicts.** A person registered for both
  Basketball and Badminton must not have games at the same time.  Requires
  a participant → games mapping (from roster data), which is not yet in
  `schedule_input.json`.
- **Church-requested blackout windows.** `earliest_slot` / `latest_slot`
  fields are already in the game schema.  Wiring them up in the solver
  is a one-liner once they are populated upstream.

---

## Adding New Constraints

The general workflow when a new scheduling rule is needed:

1. Decide whether the rule is a **data constraint** (representable in
   `schedule_input.json`) or a **solver constraint** (pure CP-SAT logic).
2. If data: update `_build_schedule_input()` in `church_teams_export.py`
   to emit the new field, and update the schema notes above.
3. Add the CP-SAT constraint in the solver module (Issue #93).
4. Write or update a test that exercises the new constraint.
5. Note the change in `CHANGELOG.md`.

---

## Related Issues and Files

| Item | Location |
|------|----------|
| Schedule-Input implementation | Issue #87; `church_teams_export.py` → `_build_schedule_input()` |
| OR-Tools POC | Issue #90; `middleware/scratch/ortools_poc.py` + `ortools_poc_report.md` |
| CP-SAT solver module | Issue #93 (done); `middleware/scheduler.py` |
| Excel schedule output | Issue #94 (done); `church_teams_export.py` → `_write_schedule_output_report()` |
| Venue resource template | `middleware/data/venue_input.xlsx` (gitignored; template at `venue_input_template.xlsx`) |
| Schedule config constants | `middleware/config.py` — `SCHEDULE_SKETCH_*`, `COURT_ESTIMATE_*`, `GYM_RESOURCE_TYPE`, `POD_RESOURCE_TYPE_*` |
