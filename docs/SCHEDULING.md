# Scheduling Pipeline

This document describes how VAY Sports Fest game schedules are produced —
from registration data to a readable Excel timetable — so future contributors
and Claude sessions do not need to reverse-engineer the design from code.

---

## Four-Step Pipeline

```
Step 1                  Step 2                  Step 3                  Step 4
export-church-teams  →  schedule_input.json  →  solve-schedule       →  produce-schedule
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

- **`games`** — one object per pool-play match placeholder for gym sports
  (Basketball, VB Men, VB Women); pod sports (single-elimination) are also
  included here for solver assignment.
- **`resources`** — one object per physical court or table, expanded from
  `venue_input.xlsx` quantities, each annotated with day, time window, and
  `exclusive_group` (see below).
- **`playoff_slots`** — pre-assigned playoff games loaded from the
  **Playoff-Slots** tab of `venue_input.xlsx` (see below).  If the tab is
  absent, a `WARNING` is logged and `playoff_slots` is an empty list — the
  pipeline does not crash.
- **`gym_modes`** — per-gym mode capacities loaded from the **Gym-Modes**
  tab of `venue_input.xlsx` (see below).  If the tab is absent, a `WARNING`
  is logged and `gym_modes` is an empty dict — the pipeline does not crash.

**`Exclusive Venue Group` column** (`venue_input.xlsx` → `Venue-Input` tab):

A physical gym can often be configured one way *or* another but not both at
once — e.g. 1 Basketball Court **or** 2 Volleyball Courts per time block.
Add one Venue-Input row per mode and tag every row for the same physical gym
with the same `Exclusive Venue Group` value.  Rows that share a group value
compete for that one gym.  Leave the column blank for standalone resources.

**Gym-Modes tab** (`venue_input.xlsx` → sheet `Gym-Modes`):

Records the capacity-per-mode coefficients used by the gym-mode capacity
estimator.  One row per gym.  Columns:

| Column | Example | Notes |
|--------|---------|-------|
| `Gym Name` | `Midsize Gym` | Physical gym identifier |
| `Basketball Courts` | `1` | Courts yielded in BB mode per time block |
| `Volleyball Courts` | `2` | Courts yielded in VB mode per time block |
| `Badminton Courts` | `6` | Courts yielded in BM mode per time block |
| `Pickleball Courts` | `8` | Courts yielded in PB mode per time block |
| `Soccer Fields` | `1` | Fields yielded in Soccer mode per time block |

`0` means the mode is not available in that gym.  A trailing footer/note row
(text in `Gym Name`, no capacities) is ignored.

**Playoff-Slots tab** (`venue_input.xlsx` → sheet `Playoff-Slots`):

This is how you control the exact order and timing of QF/Semi/Final/3rd-place
games.  Add one row per playoff game.  Required columns:

| Column | Example | Notes |
|--------|---------|-------|
| `game_id` | `BBM-Final` | Unique identifier used in the schedule output |
| `event` | `Basketball - Men Team` | Must match the event name exactly |
| `stage` | `Final` | QF, Semi, Final, or 3rd |
| `resource_id` | `GYM-Sat-2-1` | Must match a resource_id in the Resources section |
| `slot` | `Sat-2-14:00` | Slot label in `Day-HH:MM` format |

Optional columns: `team_a_id`, `team_b_id`, `duration_minutes`.

To specify the exact finale order (e.g. VB Women → VB Men → Basketball back-to-back),
simply put those games in that row order with consecutive `slot` values.  No solver
constraints are needed — the timetable is the authority.

Key constants that shape the output live in `config.py`:
`SCHEDULE_SKETCH_SATURDAY_START`, `SCHEDULE_SKETCH_SATURDAY_LAST_GAME`,
`SCHEDULE_SKETCH_SUNDAY_START`, `SCHEDULE_SKETCH_SUNDAY_LAST_GAME`,
`COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME`, `GYM_RESOURCE_TYPE`,
`SCHEDULE_SOLVER_GYM_COURTS` (change to switch between 3/4/5-court scenarios).

### Step 2 — `schedule_input.json` schema (hardened by Issue #96)

The top-level object includes a `gym_court_scenario` field that records the
explicit court count used to build the gym resources for this run.  Change
`SCHEDULE_SOLVER_GYM_COURTS` in `config.py` (currently 4) to switch scenarios;
do not rely on any default inside the code.

Every **game object** (pool play only) looks like:

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
- Team sports currently use a deterministic normalized pool format for
  planning: `2` teams -> direct match, `3` -> 3-team round robin,
  `4` -> fixed 4-match matrix, `5` -> fixed 5-match cycle, `6+` -> a
  composition of 3-team and 4-team pools that keeps every team at exactly
  `2` pool games.
- `null` is never emitted; every game has non-null `team_a_id` and `team_b_id`.

**4-team pool tiebreaker caveat:**
The fixed 4-team format plays 4 games, not a full round robin (which would be
`C(4,2) = 6`).  The matrix template is `[(0,1), (2,3), (0,2), (1,3)]`, so
**T1 vs T4 and T2 vs T3 are never played**.  Every team still plays exactly
2 games (the normalized `gpg=2` policy), but head-to-head results are not
available for every pair.  This is intentional policy, not a bug — but if pool
standings are tied, coordinators must use a tiebreaker that does not rely on
head-to-head for all matchups (e.g. point differential, or a coin toss).
Communicate this to coordinators **before** the tournament, not during.

**`pool_id`:**
- Non-empty string (`"P1"`, `"P2"`, …) for pool games.
- Playoff games are not in `games` — they live in `playoff_slots`.

Every **resource object** looks like:

```json
{
  "resource_id":     "GYM-Sat-1-1",
  "resource_type":   "Gym Court",
  "label":           "Court-1",
  "day":             "Sat-1",
  "open_time":       "08:00",
  "close_time":      "21:00",
  "slot_minutes":    60,
  "exclusive_group": "Midsize Gym"
}
```

`exclusive_group` is the `Exclusive Venue Group` value from `venue_input.xlsx`
(empty string for standalone resources, or for gym courts built from the
`SCHEDULE_SOLVER_GYM_COURTS` scenario).

Every **playoff_slot object** looks like:

```json
{
  "game_id":     "BBM-Final",
  "event":       "Basketball - Men Team",
  "stage":       "Final",
  "resource_id": "GYM-Sat-2-1",
  "slot":        "Sat-2-14:00"
}
```

The top-level **`gym_modes`** object maps each gym to its capacity per mode:

```json
{
  "Midsize Gym": {
    "Basketball Court": 1,
    "Volleyball Court": 2,
    "Badminton Court":  6,
    "Pickleball Court": 8,
    "Soccer Field":     1
  }
}
```

It is an empty object when the Gym-Modes tab is absent.

**`gym_court_scenario`:** The number of gym courts used to build the `GYM-*`
resources in this run.  Controlled by `SCHEDULE_SOLVER_GYM_COURTS` in
`config.py`.  The solver reads this to know which scenario was selected —
no hidden defaults.

Field notes:
- `resource_type` must match between game and resource; this is how the
  solver knows which court pool to draw from (C4 — court-type routing).
- `earliest_slot` / `latest_slot` are present in pool game objects but
  always `null` — they are reserved for future use.
- Gym sports (Basketball, Volleyball Men, Volleyball Women) use
  `GYM_RESOURCE_TYPE = "Gym Court"`. Pod sports each have their own
  `POD_RESOURCE_TYPE_*` constant.

### Step 3 — CP-SAT solver (`solve-schedule`) — Issue #93 (done)

```bash
python main.py solve-schedule [--input path/to/schedule_input.json] [--output path/to/schedule_output.json]
```

Reads `schedule_input.json`, runs the OR-Tools CP-SAT model for **pool play
games only**, reserves any manual `playoff_slots` from the same court/time
inventory, then merges those playoff assignments into the output. Writes
`schedule_output.json` to `DATA_DIR` (or `--output` path).
Exit codes: 0 = OPTIMAL/FEASIBLE (all pools solved), 1 = PARTIAL/INFEASIBLE/UNKNOWN,
2 = error.

Playoff slots are not re-assigned by the solver, but they **are** validated
against the resource list and reserved before pool play is packed. If a
playoff row points at an unknown court, an invalid slot label, or duplicates an
existing playoff reservation, `solve-schedule` fails loudly instead of emitting
a silent collision. If `playoff_slots` is empty (tab missing from
`venue_input.xlsx`), the output `assignments` array contains only pool play
games.

Configurable timeout via `SCHEDULE_SOLVER_TIMEOUT` env var (default: 30 s).

**Pool decomposition:** games are partitioned by `resource_type` and solved in
independent CP-SAT models. A capacity shortage in one pool (e.g. Badminton Court)
does not cascade into an INFEASIBLE result for other pools (e.g. Gym Courts).
Top-level `status` values:

| Status | Meaning |
|--------|---------|
| `OPTIMAL` | Every pool solved optimally |
| `FEASIBLE` | Every pool solved (at least one FEASIBLE) |
| `PARTIAL` | At least one pool solved; at least one pool failed |
| `INFEASIBLE` | No pools produced any assignments |
| `UNKNOWN` | Timeout with no solution found |

Output shape:

```json
{
  "solved_at": "...",
  "status": "PARTIAL",
  "solver_wall_seconds": 1.2,
  "assignments": [
    {"game_id": "BBM-01",    "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-09:00"},
    {"game_id": "BBM-Final", "event": "Basketball - Men Team", "stage": "Final",
     "resource_id": "GYM-Sat-2-1", "slot": "Sat-2-14:00"}
  ],
  "unscheduled": ["BAD-01", "BAD-02"],
  "pool_results": [...]
}
```

When a pool returns `INFEASIBLE` or `UNKNOWN`, its entry in `pool_results`
includes a **`diagnostics`** array with lower-bound capacity summaries
(required slots vs available slots per resource type and per event).

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

Playoff assignments (which carry `event` and `stage` in the assignment object
itself) are rendered alongside pool play assignments.  The renderer falls back
to the assignment's own fields when a game_id is not in the `games` list.

When one day mixes resources with different time windows or slot lengths
(common for pod sports), **Schedule-by-Time** renders separate sections per
uniform day/resource/window group so pod assignments are not collapsed into one
misaligned `Day-1` grid.

The JSON file stays in `DATA_DIR` as the machine-readable backup.

**Constraints implemented in `scheduler.py`:**

| ID | Constraint | CP-SAT construct |
|----|-----------|-----------------|
| C1 | Each game assigned to exactly one (resource, start_slot) | `AddExactlyOne` |
| C2 | Each (resource, slot) hosts at most one game (multi-slot aware) | `AddAtMostOne` |
| C3 | No team plays two games in the same time slot | `AddAtMostOne` per (team, slot_label) |
| C4 | Court-type routing — game assigned only to matching `resource_type` | filter before building vars |
| C6 | Minimum rest — no team plays in two adjacent global slots (within the same day only; cross-day pairs are skipped) | `AddBoolOr([v1.Not(), v2.Not()])` for same-day adjacent slot pairs |
| C7 | Multi-slot games — duration > slot_minutes blocks consecutive slots | restrict start positions; expand slot_occupancy |

**Playoff scheduling (not solver constraints):**
Playoff game timing is controlled entirely by the Playoff-Slots tab in
`venue_input.xlsx` — the exact slot and court for each QF/Semi/Final/3rd game
is specified there by the coordinator.  The solver only packs pool play.
Last-minute changes during the tournament are handled by editing the tab and
re-running `produce-schedule` (no solver re-run needed).

**Out of scope (future work):**
- Cross-sport participant conflicts (person in both Basketball and Badminton).

---

## Offline Planning Workbook (`build-schedule-workbook`)

The four-step pipeline above is the live runtime path.  Alongside it,
`build-schedule-workbook` produces an **offline planning workbook** so
coordinators can iterate on venue and pod planning without re-running a full
live export against ChMeetings and WordPress.

```bash
python main.py build-schedule-workbook \
    [--input-json  path/to/schedule_input.json] \
    [--input-xlsx  path/to/Church_Team_Status_ALL_YYYY-MM-DD.xlsx] \
    [--output      path/to/Schedule_Workbook.xlsx]
```

- **`--input-json`** — the `schedule_input.json` machine contract.  This is the
  primary input.  When omitted, the path is resolved in priority order:
  the sibling of `--input-xlsx`, then `EXPORT_DIR/schedule_input.json`, then
  `DATA_DIR/schedule_input.json`.
- **`--input-xlsx`** — optional `Church_Team_Status_ALL_*.xlsx` snapshot.  Its
  `Roster` and `Validation-Issues` tabs are read back into the row dicts the
  planning tabs need.  When omitted or missing, those tabs degrade to empty
  lists with a `WARNING` — the workbook still builds.
- **`--output`** — defaults to `EXPORT_DIR/Schedule_Workbook_YYYY-MM-DD.xlsx`.

The workbook has six tabs: `Venue-Estimator`, `Pod-Divisions`,
`Pod-Entries-Review`, `Court-Schedule-Sketch`, `Pod-Resource-Estimate`, and
`Schedule-Input` (an echo of the JSON).  None of them consume solver output —
they are pure planning artifacts built from the roster data and
`schedule_input.json`.  When no `venue_input.xlsx` is supplied, the
`Pod-Resource-Estimate` tab derives court availability directly from the
`schedule_input.json` `resources` so an offline build stays self-consistent.

**Two-stage workflow.** `export-church-teams` (Stage 1) owns the live
ChMeetings/WordPress reads, the `Church_Team_Status_ALL.xlsx`, and the
`schedule_input.json` machine contract.  `build-schedule-workbook` (Stage 2) is
an offline, fast, repeatable consumer of those artifacts.  The scheduling logic
lives in `middleware/schedule_workbook.py` (`ScheduleWorkbookBuilder`);
`church_teams_export.py` delegates to it under a strict one-way dependency
(`church_teams_export.py` → `schedule_workbook.py`, never the reverse).

**Transition note (operator-facing).** During this transition the consolidated
`Church_Team_Status_ALL.xlsx` produced by `export-church-teams` **still
contains** the six scheduling tabs.  The same tabs are now also available
standalone via `build-schedule-workbook`.  The tabs are intentionally
duplicated for now so operators are not surprised; a later release may drop
them from the ALL workbook once `build-schedule-workbook` is the established
path.

The solver-rendered workbook (`Schedule-by-Time` / `Schedule-by-Sport`) is a
separate concern handled by `produce-schedule` — `build-schedule-workbook` does
not take a `--schedule-output` argument because none of its six tabs render
solver results.

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

Constraints C1–C4, C6, C7 are implemented in `middleware/scheduler.py`
(Issue #93).  See the constraint table in the Step 3 section above.

Remaining future work:

- **Cross-sport participant conflicts.** A person registered for both
  Basketball and Badminton must not have games at the same time.  Requires
  a participant → games mapping (from roster data), which is not yet in
  `schedule_input.json`.
- **Pool play time windows.** `earliest_slot` / `latest_slot` fields are
  present in the schema but are currently emitted as `null` and are not
  enforced by the solver. Restore a C8-style constraint only after upstream
  data starts populating real pool-game blackout or window values.

---

## Adding New Constraints

The general workflow when a new scheduling rule is needed:

1. Decide whether the rule is a **data constraint** (representable in
   `schedule_input.json`) or a **solver constraint** (pure CP-SAT logic).
2. If data: update `_build_schedule_input()` in `schedule_workbook.py`
   to emit the new field, and update the schema notes above.
3. Add the CP-SAT constraint in the solver module (Issue #93).
4. Write or update a test that exercises the new constraint.
5. Note the change in `CHANGELOG.md`.

---

## Related Issues and Files

| Item | Location |
|------|----------|
| Schedule-Input implementation | Issue #87; `schedule_workbook.py` → `_build_schedule_input()` |
| Scheduling workbook module | Issue #98 (done); `middleware/schedule_workbook.py` → `ScheduleWorkbookBuilder` |
| Offline planning workbook command | Issue #98 (done); `main.py` → `build-schedule-workbook` |
| OR-Tools POC | Issue #90; `middleware/scratch/ortools_poc.py` + `ortools_poc_report.md` |
| CP-SAT solver module | Issue #93 (done); `middleware/scheduler.py` |
| Excel schedule output | Issue #94 (done); `schedule_workbook.py` → `_write_schedule_output_report()` |
| Venue resource template | `middleware/data/venue_input.xlsx` (gitignored; template at `venue_input_template.xlsx`) |
| Schedule config constants | `middleware/config.py` — `SCHEDULE_SKETCH_*`, `COURT_ESTIMATE_*`, `GYM_RESOURCE_TYPE`, `POD_RESOURCE_TYPE_*`, `SCHEDULE_SOLVER_GYM_COURTS` |
