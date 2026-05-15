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
                        (Issue #87, done)       (Issue #93, open)       (Issue #94, open)
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

### Step 2 — `schedule_input.json` schema

Every **game object** looks like:

```json
{
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
}
```

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

Every **precedence object** looks like:

```json
{
  "rule":          "stage_order",
  "event":         "Basketball - Men Team",
  "earlier_stage": "Pool",
  "later_stage":   "Final"
}
```

Field notes:
- `resource_type` must match between game and resource; this is how the
  solver knows which court pool to draw from.
- `pool_id` is `""` for playoff/final games.
- `earliest_slot` / `latest_slot` are optional hard windows per game
  (`null` = unconstrained).
- Gym sports (Basketball, Volleyball Men, Volleyball Women) use
  `GYM_RESOURCE_TYPE = "Gym Court"`. Pod sports each have their own
  `POD_RESOURCE_TYPE_*` constant.

### Step 3 — CP-SAT solver (`solve-schedule`) — Issue #93

```bash
python main.py solve-schedule [--input path/to/schedule_input.json]
```

Reads `schedule_input.json`, runs the OR-Tools CP-SAT model, writes
`schedule_output.json` to `DATA_DIR`. Output shape:

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

### Step 4 — Excel output (`export-schedule`) — Issue #94

```bash
python main.py export-schedule [--input path/to/schedule_output.json]
```

Reads `schedule_output.json`, writes `VAYSF_Schedule_YYYY-MM-DD.xlsx` to
`EXPORT_DIR`. Two tabs:

- **Schedule-by-Time** — grid view, color-coded by sport, for coordinators
  running the event floor.
- **Schedule-by-Sport** — flat list with auto-filter, for sport directors
  checking their division.

The JSON file stays in `DATA_DIR` as the machine-readable backup.

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

The POC modelled only Basketball Men pool play. Five constraints are still
missing and must be added in Issue #93:

1. **Court-type routing.** Basketball games must be assigned to `Gym Court`
   resources; racquet games to their respective `POD_RESOURCE_TYPE_*` courts.
   Fix: filter the court pool by `resource_type` before building variables.

2. **Stage ordering.** Playoff games must be scheduled after all pool games
   finish. Fix: use the `precedence` list from `schedule_input.json` to add
   `model.Add(playoff_slot > max_pool_slot)` constraints.

3. **Session windowing.** Games must fall within the open/close window of
   their resource. The POC hard-coded `Sat-1 08:00–20:00`; the full solver
   must read `open_time`/`close_time` per resource object and restrict the
   slot domain accordingly.

4. **Minimum rest between games.** A team that plays at slot T should not
   play again at slot T+1. Fix: for each team, add `AddAtMostOne` over
   consecutive-slot pairs.

5. **Multi-slot games.** A 60-min game in a 30-min slot resolution blocks 2
   consecutive slots on the same court. Fix: use `model.NewIntervalVar` (or
   keep slot resolution == game duration within each sport, which is the
   current approach and works as long as all games in a sport share the same
   duration).

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
| CP-SAT solver module | Issue #93 (open) |
| Excel schedule output | Issue #94 (open, depends on #93) |
| Venue resource template | `middleware/data/venue_input.xlsx` (gitignored; template at `venue_input_template.xlsx`) |
| Schedule config constants | `middleware/config.py` — `SCHEDULE_SKETCH_*`, `COURT_ESTIMATE_*`, `GYM_RESOURCE_TYPE`, `POD_RESOURCE_TYPE_*` |
