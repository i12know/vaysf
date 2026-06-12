# Scheduling Pipeline

This document describes how VAY Sports Fest game schedules are produced —
from registration data to a readable Excel timetable — so future contributors
and Claude sessions do not need to reverse-engineer the design from code.

---

## Strategic vs Tactical: Layer 1 and Layer 2

VAY Sports Fest scheduling spans two layers, divided by the moment the venue
contract is signed.

**Layer 1 — strategic (pre-booking).** Before any gym is contracted, the
question is *estimation*: what is the minimum venue capacity we need to book?
The output informs the venue contract negotiation. This layer is **not yet
built** — `SCHEDULE_SOLVER_GYM_COURTS` and `SCHEDULE_SKETCH_N_COURTS` in
`config.py` are crude scenario stand-ins for it, and the `Venue-Estimator` tab
covers part of the demand estimate. A dedicated gym-capacity estimator is
future work.

**Layer 2 — tactical (post-booking).** The venue contract is signed; the
question becomes *maximization*: how do we get the most out of the courts and
hours already paid for? Layer 2 reads the real booked venue from
`venue_input.xlsx` and runs in two stages:

- **Stage A — gym mode allocation.** Each gym can be configured in one of
  several mutually-exclusive modes per time block (e.g. 1 basketball court
  *or* 2 volleyball courts). Stage A decides each gym's mode per time range —
  greedily, most-populous-sport-first. Inputs: the `Gym-Modes` and
  `Venue-Input` tabs plus per-sport demand. See Issue #102.
- **Stage B — per-sport game scheduling.** The CP-SAT solver (`scheduler.py`)
  packs each sport's games into the courts Stage A allocated, one sport at a
  time.

The four-step pipeline below is the Layer-2 runtime path.  When
`venue_input.xlsx` is present with a `Gym-Modes` tab, `export-church-teams`
runs the Stage-A allocator and writes real Layer-2 gym resources into
`schedule_input.json`.  When the file is absent, the pipeline falls back to
the `SCHEDULE_SOLVER_GYM_COURTS` estimate (Issues #102 and #103, done).

---

## Moving Parts Map

### Data flow by layer

```
LAYER 1 — STRATEGIC (pre-booking): estimate the minimum venue to book
──────────────────────────────────────────────────────────────────────────────
  ChMeetings + WordPress
       │
       │  export-church-teams  (run-me.bat includes this)
       ▼
  Church_Team_Status_ALL_*.xlsx          schedule_input.json  ◄─ venue_input.xlsx
  ├─ Summary                             [BRIDGE: Layer 1 → 2]   (manual, booked
  ├─ Contacts-Status                      currently built from    venue goes here)
  ├─ Roster                               Layer-1 estimate;
  ├─ Validation-Issues                    fixed by #102 + #103
  └─ {Sport} tabs                                │
       │                                         │  build-schedule-workbook
       │  (human review / approvals)             ▼
       │                               Schedule_Workbook_*.xlsx
       │                               ├─ Summary               ← operator guide
       │                               ├─ Venue-Estimator       ← demand estimate
       │                               ├─ Court-Schedule-Sketch ← 3/4/5-court sketch
       │                               ├─ Pod-Divisions         ← division planning
       │                               ├─ Pod-Entries-Review    ← entry checklist
       │                               ├─ Pod-Resource-Estimate ← capacity vs demand
       │                               └─ Schedule-Input        ← JSON echo (bridge)
       │
       │  ── VENUE CONTRACT SIGNED ──────────────────────────────────────────
       │
LAYER 2 — TACTICAL (post-booking): maximize use of the booked venue
──────────────────────────────────────────────────────────────────────────────
  venue_input.xlsx
       │
       │  Stage A: gym mode allocator  (Issue #102, done — gym_allocator.py)
       │    Greedy priority allocation of gym time-ranges to sport modes.
       │    Structural exclusivity: no gym block handed to two modes.
       ▼
  schedule_input.json  (real Layer-2 gym resources when venue_input.xlsx present)
       │
       │  solve-schedule  (Stage B: CP-SAT solver — run-schedule.bat Step 1)
       ▼
  schedule_output.json
       │
       │  produce-schedule  (run-schedule.bat Step 2)
       ▼
  VAYSF_Schedule_*.xlsx
  ├─ Schedule-by-Time   ← color-coded grid for floor coordinators
  ├─ Schedule-by-Sport  ← flat list with auto-filter for sport directors
  └─ Conflict-Audit     ← verify shared-athlete conflicts were avoided or remain
```

### Source files (scheduling-related)

| File | Role | Layer |
|------|------|-------|
| `main.py` | CLI entry — all commands | — |
| `church_teams_export.py` | Live ChMeetings + WP export; writes `schedule_input.json`; delegates scheduling tab rendering to `schedule_workbook.py` | Layer 1 + bridge |
| `schedule_workbook.py` | `ScheduleWorkbookBuilder` — all scheduling tabs, both workbooks, schedule output renderer | Layer 1 + bridge + Layer 2 output |
| `scheduler.py` | CP-SAT solver (Stage B) | Layer 2 |
| `config.py` | All configuration constants; `SCHEDULE_SKETCH_*` and `SCHEDULE_SOLVER_GYM_COURTS` are Layer-1 stand-ins | — |
| `gym_allocator.py` | Stage A greedy mode allocator | Layer 2 (Issue #102, done) |

### Batch scripts (Windows operator shortcuts)

| Script | Runs | Layer |
|--------|------|-------|
| `run-me.bat` | `sync --type full` → `sync --type validation` → `export-church-teams` | Non-scheduling + Layer 1 |
| `run-schedule.bat` | `solve-schedule` → `produce-schedule` | Layer 2 |

### Input files

| File | Location | Role | Layer |
|------|----------|------|-------|
| `venue_input.xlsx` | `middleware/data/` (gitignored) | Booked venue: courts, times, gym modes, playoff slots | Layer 2 input |
| `SportsFest_2026_Venue_Input_Template.xlsx` | `middleware/data/` (committed) | Operator template for `venue_input.xlsx` | — |

### Generated artifacts

| Artifact | Produced by | Consumed by | Layer |
|----------|-------------|-------------|-------|
| `Church_Team_Status_ALL_*.xlsx` | `export-church-teams` | Human review, approvals | Non-scheduling |
| `Church_Team_Status_{CODE}.xlsx` | `export-church-teams` | Pastor / church coordinator | Non-scheduling |
| `schedule_input.json` | `export-church-teams` | `solve-schedule`, `build-schedule-workbook` | Bridge (includes Layer-2 gym resources, seeded pool assignments, and shared-athlete conflict edges when available) |
| `Schedule_Workbook_*.xlsx` | `build-schedule-workbook` | Coordinator planning / venue contract decision | **Layer 1** |
| `schedule_output.json` | `solve-schedule` | `produce-schedule` | Layer 2 |
| `VAYSF_Schedule_*.xlsx` | `produce-schedule` | Floor coordinators, sport directors | Layer 2 (`Schedule-by-Time`, `Schedule-by-Sport`, `Conflict-Audit`) |

---

## Scheduling Terms

- **Shared-athlete edge** — one `team_conflicts` row connecting two different sport teams when at least one participant appears on both rosters.
- **PlanningOnly** — a `Conflict-Audit` status meaning the overlap is real, but at least one side of the edge does not currently generate Layer-2 games. After Soccer field scheduling landed, this status should be rare and usually indicates an intentionally unsolved event or missing schedule-input resources.
- **Organizer-scheduled** — the event is still visible in planning tabs and conflict audit, but its actual timetable is managed manually outside the solver.
- **Solver-scheduled** — the event contributes concrete game rows to `schedule_input.json["games"]`, so Stage B places it onto real resources and times.
- **Stage A demand** — the per-mode slot demand fed into the gym allocator before the solver runs. Soccer is intentionally excluded from this demand model today.
- **Gym Core** — the shared Layer-2 solver pool where Basketball / VB Men / VB Women are optimized together for athlete conflicts while still routing to their own court types.

---

## Four-Step Pipeline

```
Step 1                  Step 2                  Step 3                  Step 4
export-church-teams  →  schedule_input.json  →  solve-schedule       →  produce-schedule
                        (Issue #87, done)       schedule_output.json    VAYSF_Schedule_*.xlsx
                                                (Issue #93, done)       (Issue #94, done)
```

## Implementation roadmap

The scheduling expansion is being delivered in three major phases so the team
can keep the big-picture plan visible while iterating on this season:

### Phase 1 - Core team-sport conflict engine

Scope:
- Basketball - Men Team
- Volleyball - Men Team
- Volleyball - Women Team
- Bible Challenge - Mixed Team
- Soccer - Coed Exhibition (optional / config-driven)

#### Bible Challenge format (confirmed 2026)

Bible Challenge runs as a **Jeopardy-style game with 3 church teams per game**.

Key constraints the pipeline must respect:

- **Single classroom, sequential only.** There is exactly one Bible Challenge
  room and games never run concurrently. The scheduling problem for BC is a
  simple queue, not a resource-allocation problem. There is no "court-hours"
  model — only total room-minutes.
- **Round-robin phase.** Each registered BC team is planned for **2 games** in
  the round-robin once at least 3 church teams exist. Total RR games = ⌈N × 2 / 3⌉
  where N is the number of teams. The queue is generated directly from the
  `Pool-Assignment` draw:
  - 3-team pool → 2 Jeopardy rounds with the same trio
  - 4-team pool → 3 rounds, with the extra third appearance assigned to `T4`
  - 5-team pool → 4 rounds, with the extra appearances assigned to `T4` and `T5`
  This keeps the bonus rounds away from the top-seeded slots.
- **Playoff phase.** The **top 9 teams by cumulative Jeopardy score** advance
  to the playoff. Playoff structure: **3 semi-final games** (3 pools of 3
  teams) then **1 final game** (3 semi-final winners) = 4 total playoff games.
  Playoff phase only runs when N ≥ 9 registered teams. The current pipeline
  schedules these as placeholder queue games and adds precedence rules so all
  BC round-robin queue games finish before any semi-final starts, and the
  final always starts after all three semi-finals.
- **Seeding.** Up to 3 seeds from prior-year winners. Remaining teams enter
  the draw unseeded. The existing serpentine-fill `assign-pools` workflow
  applies unchanged.
- **Per-game duration.** 60 minutes (includes buffer for late starts).
- **Venue-Estimator model.** BC appears as a separate row in the
  Venue-Estimator showing total sequential room-hours, not concurrent
  court-hours. Formula: `(RR games + playoff games) × 60 min`. If fewer than
  3 BC teams exist, the estimator shows that the room queue is still waiting
  for the first 3-team game.
- **Cross-sport conflict edges.** BC teams produce pairwise shared-athlete
  edges with BB / VBM / VBW teams exactly like any other team sport. An
  athlete on a BC team who also plays Basketball still generates a
  primary-vs-secondary conflict edge in `team_conflicts`.

Status as of May 20, 2026:
- Phase 1 complete (for the 2026 season)
- Implemented:
  - editable `Pool-Assignment` workflow for BB / VBM / VBW
  - persisted seeded pool draw via `pool_assignments.json`
  - Layer 2 shared-athlete conflict edges for BB / VBM / VBW
  - conflict-aware Gym Core solve with primary-vs-secondary weighting
  - `Conflict-Audit` output in `VAYSF_Schedule_*.xlsx`
  - Venue-Estimator rewritten for BC sequential single-classroom model
  - BC teams included in `Pool-Assignment`
  - BC shared-athlete edges included in `team_conflicts`
  - BC round-robin queue games generated into `schedule_input.json` using the
    seeded BC pool draw
  - BC semi-final / final placeholder games plus precedence rules so the BC
    round-robin queue finishes before the semis, and the final stays after the
    semis in the single-room queue
  - BC cross-sport edges now audit against real scheduled RR queue games rather
    than planning-only placeholders
  - Soccer included in `Pool-Assignment`, `team_conflicts`, and real Layer-2
    Soccer Field game generation via the `SOCCER_ENABLED` config flag
    (default `True`)
  - Soccer pool rounds must finish before the Soccer semi-finals, and the
    Soccer final must start after both semi-finals
  - Soccer now appears in `Schedule-by-Time` / `Schedule-by-Sport`, and
    Soccer cross-sport edges audit against real scheduled field games
  - When `SOCCER_ENABLED` is set to `False`, Soccer is removed from the
    Phase-1 scheduling/planning outputs so the design stays flexible if the
    Coed Exhibition does not return in future seasons.

#### Soccer (optional, config-driven)

Soccer - Coed Exhibition is gated on `SOCCER_ENABLED` in `config.py`:

- **`SOCCER_ENABLED = True`** (current 2026 default): Soccer appears in
  `Venue-Estimator`, in `Pool-Assignment` with up to-3 seeds, and produces
  shared-athlete conflict edges with BB / VBM / VBW / BC in `team_conflicts`.
  Soccer pool/playoff games are generated into `schedule_input.json` and
  solved on real `Soccer Field` resources from `venue_input.xlsx`. Soccer
  does not participate in the Stage-A gym allocator demand model because it
  uses dedicated field resources rather than flexible gym modes.
- **`SOCCER_ENABLED = False`**: Soccer is removed from `COURT_ESTIMATE_EVENTS`
  and from `_POOL_ASSIGNMENT_EVENT_DEFS`, so the scheduling/planning outputs
  omit Soccer. Raw roster exports still reflect the underlying registrations;
  additional validation enforcement for stray Soccer entries is future work.

Current Soccer defaults (May 21, 2026):
- `2` pool games per team
- `60` minutes per game
- top `4` teams advance to `2` semi-finals + `1` final
- `1` third-place game by default

### Phase 2 - Racquet conflict engine

Scope:
- Badminton
- Pickleball
- Pickleball 35+
- Table Tennis
- Table Tennis 35+
- Tennis

Goal:
- model doubles first, then singles, while preserving the same primary-sport
  protection rules and cross-sport conflict reduction priorities

#### Doubles cross-sport conflicts (Issue #158, shipped)

The first slice of Phase 2 extends shared-athlete conflict modeling — which
previously covered only team sports (Basketball, Volleyball, Bible Challenge,
Soccer) — to racquet **doubles** entries. It closes the two gaps the gym-only
builder missed:

- **team ↔ racquet** — a participant on a team-sport roster and in a racquet
  doubles pair (e.g. Basketball + Badminton), and
- **racquet ↔ racquet** — a participant in two racquet doubles events
  (e.g. Badminton + Pickleball).

How it works:

- `_resolve_pod_doubles()` reuses the reciprocal-partner pairing from
  `_build_pod_entries_review_rows()` to resolve **confirmed** doubles pairs and
  assigns each a stable, reproducible ID of the form `{division_id}-E{nn}`
  (e.g. `BAD-Men-Doubles-E01`). IDs are stable across re-runs because entries
  are sorted by participant ID before numbering.
- `_build_pod_game_objects()` attaches those entry IDs to the division's
  **Round-1** games (`E01` vs `E02`, …). Only R1 is protected: in single
  elimination, later-round participants are not knowable until earlier rounds
  are played, so deeper games keep `team_a_id`/`team_b_id` of `null`. Entries
  with a bye (odd entry counts) are likewise unprotected for their first match.
- `_build_cross_sport_conflicts()` emits the team↔racquet and racquet↔racquet
  edges in the same dict shape as the gym builder, so the solver and the
  `Conflict-Audit` tab consume every conflict class identically. A shared
  athlete is a *primary* overlap when their declared primary sport matches one
  of the two events, otherwise *secondary* — the same protection rule team
  sports already use.
- **Solve order (Decision 5):** team sports are scheduled first; racquet/pod
  pools solve **last** (`_POOL_SOLVE_PRIORITY` puts the racquet court types
  after Gym Core). A shared athlete's racquet game adapts around the
  already-placed team-sport slots via cross-pool avoidance (C3x), rather than
  the team game moving.
- **Unprotected entries:** `UnresolvedDoubles` (missing / non-reciprocal
  partner) have unknown membership and cannot be protected. They are surfaced
  in `pod_unprotected_entries` and listed in the `Conflict-Audit` tab so
  operators can chase down the missing partner, never silently dropped.

Still future work within Phase 2:

- **Singles** conflict protection (this slice is doubles-only).
- Coarse division-level windowing to approximate **later-round** coverage
  beyond R1 without pretending to know bracket winners.

### Phase 3 - Audit, overrides, and operator polish

Scope:
- richer conflict audit / explanation output
- operator override loops
- workbook readability and reporting polish
- final review of scheduling heuristics that are helpful but not required for
  correctness, such as conflict-aware tie-breaking inside `assign-pools`

### Step 1 — Build scheduling inputs (`export-church-teams`)

```bash
python main.py export-church-teams
```

Produces the consolidated `Church_Team_Status_ALL.xlsx` in `EXPORT_DIR`.
When `middleware/data/venue_input.xlsx` is present, also writes
**`schedule_input.json`** alongside the xlsx containing:

- **`games`** — one object per pool-play match for the gym sports
  (Basketball, VB Men, VB Women), one object per BC Jeopardy queue game, plus
  pod sports (single-elimination). When a `pool_assignments.json` sidecar is
  present beside the export artifacts, the gym and BC games use the real seeded
  team draw from the `Pool-Assignment` workflow instead of raw placeholders.
  When explicit venue rows exist, gym sports with fewer than two estimating
  teams are omitted instead of using the legacy 8-team planning scaffold.
- **`resources`** — one object per physical court or table, expanded from
  `venue_input.xlsx` quantities, each annotated with day, time window, and
  `exclusive_group` (see below).
  If a scheduled resource type's `slot_minutes` values do not match the
  corresponding `COURT_ESTIMATE_MINUTES_*` config duration, Layer 2 logs an
  advisory warning. This does **not** block the build: config still defines the
  game duration, while `venue_input.xlsx` still defines the slot granularity.
  Intentional venue-side overrides are allowed.
- **`playoff_slots`** — pre-assigned playoff games loaded from the
  **Playoff-Slots** tab of `venue_input.xlsx` (see below).  If the tab is
  absent, a `WARNING` is logged and `playoff_slots` is an empty list — the
  pipeline does not crash.
- **`gym_modes`** — per-gym mode capacities loaded from the **Gym-Modes**
  tab of `venue_input.xlsx` (see below).  If the tab is absent, a `WARNING`
  is logged and `gym_modes` is an empty dict — the pipeline does not crash.
- **`gym_allocation`** — output of the Stage-A greedy allocator.  When
  `venue_input.xlsx` contains both gym blocks (rows with `Exclusive Venue
  Group`) and a `Gym-Modes` tab, this records which mode each gym block was
  assigned, the demand/supply/shortfall per mode, and the mode-switch count.
  When the allocator is not run and no venue rows exist, `{"source": "fallback",
  "gym_court_scenario": N}` is written instead. When venue rows do exist but
  allocator inputs are incomplete, the Venue-Input rows are used directly and
  `gym_allocation.source` is `direct_venue_input`.
- **`team_conflicts`** — shared-athlete edges between the seeded core gym teams.
  These let Layer 2 solve Basketball / VB Men / VB Women together as one
  conflict-aware gym cluster while still routing Basketball only to Basketball
  courts and Volleyball only to Volleyball courts. BC and Soccer edges are also
  carried here so `Conflict-Audit` can report them against real scheduled BC
  classroom games and Soccer field games.
- **`precedence`** — optional ordering constraints between generated games.
  Today this is used for Bible Challenge and Soccer so pool rounds finish before
  the semi-finals, and the final starts after the semis.

Bible Challenge is a special case: its 3-team final already resolves
1st / 2nd / 3rd place, so there is no separate `BC-3rd` game or extra
third-place slot.

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

Each row must then carry **one of two placement forms** (Issue #127):

*Venue-centric form (preferred)* — specify the physical venue directly; no
knowledge of internal resource IDs required:

| Column | Example | Notes |
|--------|---------|-------|
| `gym_name` | `EHS Main Gym` | Matches `Venue Name` or `Exclusive Venue Group` in Venue-Input (case-insensitive) |
| `date` | `7/26/2026` | Must be a date that appears in Venue-Input (a day label like `Sun-2` also works) |
| `start_time` | `14:00` | Must fall inside that venue's Venue-Input time window |
| `slot_minutes` | `60` | Optional synthetic-resource grid size; defaults to the venue row's slot size |

At build time (`export-church-teams`), each venue-centric row is validated
against Venue-Input and resolved to a concrete resource:

- For an **allocator-managed gym** (its `Exclusive Venue Group` has a
  Gym-Modes entry), a dedicated playoff-pinned resource (e.g. `BB-Sun-2-PF1`)
  is created covering only the pinned window, and that window is **reserved
  out of the Stage-A allocator inventory** before pool-play demand is
  satisfied — regular games can never consume a pinned Final's court time.
  Contiguous pins on the same gym/sport (e.g. Semi at 14:00, Final at 15:00)
  merge onto one playoff court.
- For a **standalone venue row**, the pin resolves to one of the existing
  expanded resource IDs (e.g. `TT-Sun-2-1`) and the exact `(resource, slot)`
  pair is reserved from pool play at solve time, as always.
- Invalid venue pins abort schedule-input generation with all detected errors
  listed. This includes unknown gym/date/start values, overlapping mutually
  exclusive gym modes, court-count overflow, and overlapping multi-slot pins.
  Fix the rows and re-run `export-church-teams`.

*Explicit form (override / legacy)* — copy internal IDs from the generated
`Schedule-Input` Resources section:

| Column | Example | Notes |
|--------|---------|-------|
| `resource_id` | `GYM-Sat-2-1` or `BB-Sun-2-3` | Must match a resource_id in the Resources section |
| `slot` | `Sat-2-14:00` | Slot label in `Day-HH:MM` format |

When a row carries both forms, the explicit `resource_id` + `slot` wins.
Note that generated resource ordinals can drift when Venue-Input changes —
the venue-centric form exists precisely so operators do not have to track
that drift.

Optional columns (either form): `team_a_id`, `team_b_id`, `duration_minutes`.
When `duration_minutes` is omitted for a generated game, the build uses that
game's configured duration and reserves every occupied resource slot.

Canonical direct-venue resource prefixes are now:
- `BB-` Basketball Court
- `VB-` Volleyball Court
- `BC-` BC Station
- `SOC-` Soccer Field
- `BAD-` Badminton Court
- `PCK-` Pickleball Court
- `TT-` Table Tennis Table
- `TEN-` Tennis Court

Allocator-managed gym blocks may still use `GYM-*`, while direct standalone
venue rows usually use one of the sport-specific prefixes above. Operators
should copy the exact `resource_id` from the generated `Schedule-Input`
Resources section rather than guessing.

Logical day keys are weekday-based (`Fri-1`, `Sat-1`, `Sun-1`, `Sat-2`, ...).

Merge behavior at solve time:

- if a `Playoff-Slots` row names a `game_id` that already exists in
  `schedule_input.json["games"]`, the pinned row replaces the modeled
  assignment for that game in the final output
- if a `Playoff-Slots` row names a `game_id` that is not in `games`, it is
  carried through as a manual playoff-only assignment

This lets coordinators pin modeled finals such as `BC-Final` or `VBM-Final`
to exact courts/times without editing the generated game list first.

To specify the exact finale order (e.g. VB Women → VB Men → Basketball back-to-back),
simply put those games in that row order with consecutive `slot` values.  No solver
constraints are needed — the timetable is the authority.

Key constants in `config.py`:
`SCHEDULE_SKETCH_SATURDAY_START`, `SCHEDULE_SKETCH_SATURDAY_LAST_GAME`,
`SCHEDULE_SKETCH_SUNDAY_START`, `SCHEDULE_SKETCH_SUNDAY_LAST_GAME`,
`COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME`,
`GYM_RESOURCE_TYPE_BASKETBALL`, `GYM_RESOURCE_TYPE_VOLLEYBALL`,
`SCHEDULE_SOLVER_GYM_COURTS` (fallback court count when venue_input.xlsx absent).

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
  "resource_type":    "Basketball Court",
  "earliest_slot":    null,
  "latest_slot":      null
}
```

**`team_a_id` / `team_b_id` in planning mode:**
- Pool games use stable placeholder IDs like `BBM-P1-T1`, `BBM-P1-T2`.
  The same placeholder ID is reused across every game that team plays, so
  the solver can enforce team-overlap (C3) and min-rest (C6) constraints
  even before final church assignments are known.
- The legacy 8-team placeholder scaffold is used only when schedule input is
  being built without explicit venue rows. With a real `venue_input.xlsx`,
  gym sports need at least two estimating teams to appear in `games`.
- Team sports currently use a deterministic normalized pool format for
  planning: `2` teams -> direct match, `3` -> 3-team round robin,
  `4` -> fixed 4-match matrix, `5` -> fixed 5-match cycle, `6+` -> a
  composition of 3-team and 4-team pools that keeps every team at exactly
  `2` pool games.
- `null` is never emitted; every game has non-null `team_a_id` and `team_b_id`.

**Current team seeding / pool-assignment policy:**
- Each real team may carry an integer `seed`.
- `seed = 0`, blank, or missing means **unseeded** and should participate in a
  random draw.
- `seed > 0` means **ranked**; lower numbers are placed earlier in the draw.
- The current `assign-pools` workflow applies the fairness layer now:
  1. sort all non-zero seeds ascending
  2. randomly shuffle the unseeded teams once
  3. append the shuffled unseeded teams after the ranked teams
  4. assign that ordered list into the normalized pool structure using a snake
     / serpentine draw
- Future enhancement:
  - add conflict-aware tie-breaking within equal-seed or unseeded buckets,
    while still preserving the seed order and the fair serpentine structure

**Example: 13 teams, 4 pools, only seeds 1 / 2 / 3**
- Pool sizes follow the normalized planning structure: `3, 3, 3, 4`.
- Ordered draw list: `1, 2, 3, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10`
  where `R1..R10` are the unseeded teams after one random shuffle.
- Serpentine placement:
  - Row 1: `P1=1`, `P2=2`, `P3=3`, `P4=R1`
  - Row 2: `P4=R2`, `P3=R3`, `P2=R4`, `P1=R5`
  - Row 3: `P1=R6`, `P2=R7`, `P3=R8`, `P4=R9`
  - Row 4: `P4=R10`
- Final pools:
  - `P1`: `1, R5, R6`
  - `P2`: `2, R4, R7`
  - `P3`: `3, R3, R8`
  - `P4`: `R1, R2, R9, R10`

**Current primary-sport conflict priority:**
- In Layer 2 today, BB / VBM / VBW shared-athlete edges already use this policy
  in the conflict-aware Gym Core solver.
- Cross-sport conflict handling should start **as soon as one sport's pool
  assignment is frozen**, not only at final timetable rendering.
- Each athlete's **primary sport** should be treated as the protected
  commitment.
- The first sport assigned is **not** automatically protected for every
  dual-sport athlete; protection follows the athlete's own primary-sport
  designation.
- When assigning a later sport (for example Men Volleyball after Basketball is
  frozen), the system should try to minimize conflicts for athletes who appear
  in both sports, but if there is a breaking point:
  - protect the athlete's primary sport placement first
  - allow conflict pressure to fall on the athlete's non-primary sport
- This means pool assignment fairness remains the first-order rule, while
  cross-sport conflict reduction becomes a bounded second-order optimization.
- Future enhancement:
  - use the same primary-sport policy earlier during pool assignment for later
    sports such as Bible Challenge and optional Soccer, not only during the
    final timetable solve

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
  "resource_type":   "Basketball Court",
  "label":           "Court-1",
  "day":             "Sat-1",
  "open_time":       "08:00",
  "close_time":      "21:00",
  "slot_minutes":    60,
  "exclusive_group": "Midsize Gym"
}
```

Direct venue rows use the canonical short prefixes above, for example
`BB-Sat-1-1`, `VB-Sat-1-1`, `BC-Sat-1-1`, `PCK-Sat-1-1`, or `TT-Fri-1-1`.

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
- Basketball games use `GYM_RESOURCE_TYPE_BASKETBALL = "Basketball Court"`;
  Volleyball Men and Women use `GYM_RESOURCE_TYPE_VOLLEYBALL = "Volleyball Court"`.
  Pod sports each have their own `POD_RESOURCE_TYPE_*` constant.

### Step 3 — CP-SAT solver (`solve-schedule`) — Issue #93 (done)

```bash
python main.py solve-schedule [--input path/to/schedule_input.json] [--output path/to/schedule_output.json]
```

Reads `schedule_input.json`, runs the OR-Tools CP-SAT model for **pool play
games only**, reserves any manual `playoff_slots` from the same court/time
inventory, then merges those playoff assignments into the output. Writes
`schedule_output.json` to `DATA_DIR` (or `--output` path).
Exit codes: 0 = OPTIMAL/FEASIBLE (all pools solved), 1 = PARTIAL/INFEASIBLE
without a timeout, 2 = at least one pool timed out (`UNKNOWN`), 3 = contract,
input, solver, or output error. A mixed solve keeps top-level status `PARTIAL`
and preserves completed assignments, but still exits 2 so automation knows to
retry with a larger timeout.

Before anything is solved, the input is checked against the schedule contract
(`middleware/schedule_contracts.py`, Issue #161): Pydantic models covering the
full schema documented here, with strict numerics (numeric strings and
booleans rejected), real clock windows (`HH:MM`, `close_time > open_time`),
`min_gap_slots >= 1`, plus cross-checks for duplicate IDs, playoff slots
referencing unknown resources, precedence cycles, precedence rules spanning
solver pools (unenforceable by the pool-decomposed solver, so rejected), and
games whose `duration_minutes` cannot fit any resource of their
`resource_type`. Contract violations exit 3 with every violation listed (each
message names the offending `game_id`/`resource_id`); tolerable conditions —
a `resource_type` with no resources, a precedence rule referencing an unknown
game — are logged as warnings and the solve proceeds. The solver also
self-checks its output against the contract before writing
`schedule_output.json`, and `produce-schedule` validates both JSON files plus
output→input referential integrity before rendering.

Unknown fields are accepted with a deduplicated warning (the schema grows
every season); the reserved annotation namespace — a field named
`operator_notes` or any field starting with `x_` — never warns, so
hand-annotated inputs stay clean. `team_conflicts` endpoints are deliberately
not required to appear in `games`: planning-only edges (an event with no
Layer-2 games yet) are a legitimate state with their own `PlanningOnly`
conflict-audit status.

Playoff slots are not re-assigned by the solver, but they **are** validated
against the resource list and reserved before pool play is packed. If a
playoff row points at an unknown court, an invalid slot label, or duplicates an
existing playoff reservation, `solve-schedule` fails loudly instead of emitting
a silent collision. If `playoff_slots` is empty (tab missing from
`venue_input.xlsx`), the output `assignments` array contains only pool play
games.

Configurable timeout via `SCHEDULE_SOLVER_TIMEOUT` env var (default: 30 s).

#### Solver objectives (six-tier lexicographic)

The solver minimizes a single combined integer that encodes six goals in strict
priority order.  Because each tier's weight exceeds the maximum possible total of
all lower tiers combined, improving a higher-tier goal is **always** worth more
than any improvement at lower tiers — the hierarchy is enforced by arithmetic,
not policy.

| Tier | Goal | What it means in practice |
|------|------|--------------------------|
| 1 | **Primary conflict penalty** | Two teams share an athlete whose *primary* sport is one of the two events. Example: a player whose primary sport is Basketball also registers for Bible Challenge — a BB vs BC same-slot collision is a primary conflict. The solver treats this as a near-hard constraint and will sacrifice any Tier 2–6 improvement to eliminate it. |
| 2 | **Secondary conflict penalty** | Same shared-athlete collision, but the athlete's primary sport is a *third* event. Example: a Soccer-primary player who also plays Basketball and Bible Challenge. A BB vs BC clash is now a secondary conflict — still penalised, but slightly below Tier 1. |
| 3 | **Max-per-day spread** | When cross-pool avoidance is active (another sport has already claimed certain time slots), minimize the *maximum number of games on any single day*. This distributes pool-play games evenly across all available days rather than packing everything into the first available weekend. Activated only when C3x (cross-pool) constraints are present; otherwise skipped so single-sport pools (e.g. Table Tennis) still concentrate on their designated day. |
| 4 | **Latest slot index** (makespan) | After conflicts and spread are settled, minimize the index of the *last occupied slot* across all games. This shrinks the right edge of the schedule. |
| 5 | **Volleyball court switches** | On a court that alternates between Men's VB and Women's VB, each gender flip requires a net-height change. The solver minimizes back-to-back gender changes per court. This is prioritized **above** packing (Tier 6) to reduce net-adjustment disruptions. |
| 6 | **Sum of slot indices** (packing) | Within the constraints set by Tiers 1–5, minimize `sum(slot_index for each game)` as a tiebreaker. Prefers filling slot 3 before slot 7, keeping games front-loaded within each day. |

Weight construction (from `scheduler.py`):

```python
sum_slots_weight = 1
vb_weight        = sum_slots_max + 1                                    # beats any packing saving
latest_weight    = vb_switch_max * vb_weight + sum_slots_max + 1       # beats Tiers 5+6
spread_weight    = latest_max * latest_weight + … + 1                  # beats Tiers 4+5+6
secondary_weight = spread_max * spread_weight + …                      # beats Tiers 3–6
primary_weight   = secondary_penalty_max * secondary_weight + …        # beats Tiers 2–6
```

**Cross-pool conflict avoidance (C3x):** Pools are solved in priority order — BC
Station first, then Soccer Field, then Tennis/Badminton/Pickleball/Table Tennis,
and finally Gym Core (BB + VB) last.  After each pool is solved, every team's
assigned slots are recorded.  Conflict edges in `team_conflicts` are used to
identify cross-sport partner teams: if ANH-BC occupies Sat-1-13:00, the solver
forbids ANH-BBM from starting any game that spans Sat-1-13:00.  This hard
constraint (C3x) eliminates the cross-sport pink rows in the Conflict-Audit that
the within-pool penalty alone could not fix.

Day ordering for global slot indices follows weekday-then-cycle chronology
(Fri-1 < Sat-1 < Sun-1 < Fri-2 < …), so Tier 4/6 packing naturally prefers
earlier dates in the weekend without any extra constraint.

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

For the shared **Gym Core** pool, the renderer instead merges same-day
Basketball / Volleyball resources into one continuous section per sport and
uses venue-qualified court headers such as `Orange Gym Court-1` or
`HS Big Gym Court-3` so floor coordinators can tell mixed venues apart at a
glance.

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

**Playoff scheduling:**
Generated playoff games participate in solver precedence, including
duration-aware round ordering. The optional Playoff-Slots tab in
`venue_input.xlsx` fixes exact QF/Semi/Final/3rd games to operator-selected
venues and times; unpinned playoff games remain solver-assigned. Last-minute
pin changes require regenerating and solving the schedule before running
`produce-schedule`.

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

The workbook has nine tabs: `Summary`, `Venue-Estimator`, `Pool-Assignment`,
`Pod-Divisions`, `Pod-Entries-Review`, `Court-Schedule-Sketch`,
`Pod-Resource-Estimate`, `Schedule-Input` (an echo of the JSON), and
`Gym-Allocation` (a summary of the Stage-A allocator output, or a note when the
allocator was not run).
None of them consume solver output —
they are pure planning artifacts built from the roster data and
`schedule_input.json`.  When no `venue_input.xlsx` is supplied, the
`Pod-Resource-Estimate` tab derives court availability directly from the
`schedule_input.json` `resources` so an offline build stays self-consistent.

`Venue-Estimator` has two intentionally different demand columns:

- **`Estimating Teams/Entries`** â€” the operational count used for the current
  schedule build
- **`Potential Teams/Entries`** â€” a ceiling / contingency signal

For racquet sports, `Potential Teams/Entries` is rule-aware: it is calculated
from current registrations, includes incomplete doubles pairing where that
still affects possible entries, and caps the result using the active 2026
church entry limits. It is useful for court-capacity planning, but it is not
the default number of racquet entries the current run will schedule.

The `Pool-Assignment` tab is the editable Layer-1 seeding workspace for the
current Phase 1 team sports (`BB`, `VBM`, `VBW`, `BC`, and `SOC` when
`SOCCER_ENABLED`). Operators can review
the inferred team rows, set `Seed` values, and rerun:

```bash
python main.py assign-pools --workbook path/to/Schedule_Workbook_YYYY-MM-DD.xlsx
```

The command refreshes pool placement in the workbook and persists the editable
state in `pool_assignments.json` beside the workbook so later rebuilds can
reload the same seed inputs. A later `export-church-teams` run in that same
folder reads the sidecar back into `schedule_input.json`, so Layer 2 scheduling
and the conflict audit use the same pool draw you reviewed in Excel.

### Changing `Target Pool Games/Team`

For the core gym team sports (`Basketball - Men Team`, `Volleyball - Men Team`,
`Volleyball - Women Team`, and optionally `Soccer - Coed Exhibition`), the
`Venue-Estimator` column **Target Pool Games/Team** is generated from
`middleware/config.py`. It is **not** edited directly in Excel.

The per-sport knobs are:

- `COURT_ESTIMATE_POOL_GAMES_BASKETBALL`
- `COURT_ESTIMATE_POOL_GAMES_VOLLEYBALL_MEN`
- `COURT_ESTIMATE_POOL_GAMES_VOLLEYBALL_WOMEN`
- `COURT_ESTIMATE_POOL_GAMES_SOCCER`

Supported live values are **2** and **3** only.

- **2-game mode** is the established normalized policy:
  - 3-team pool -> full round robin (`2` games/team)
  - 4-team pool -> 4-match matrix (`2` games/team)
  - 5-team pool -> 5-match cycle (`2` games/team)
- **3-game mode** is now a first-class policy too:
  - 4-team pool -> full round robin (`3` games/team)
  - 6-team pool -> 3-round matrix (`3` games/team)
  - odd team counts may require one **5-team** or **7-team** pool; the highest
    slot in that odd pool (`T5` or `T7`) receives the extra 4th game

Operationally, changing one of these config values affects **both Layer 1 and
Layer 2** because the same policy is used to:

- estimate demand in `Venue-Estimator`
- compute `Pool-Assignment` pool sizes / slot meanings
- generate the actual pool-play games written into `schedule_input.json`

So after changing a team-sport pool target, rerun:

```bash
python main.py export-church-teams
python main.py build-schedule-workbook
python main.py assign-pools --workbook path/to/Schedule_Workbook_YYYY-MM-DD.xlsx
run-schedule.bat
```

Re-running `assign-pools` matters because changing from `2` to `3` can change
the pool geometry itself (`4 + 3 + 3` may become `6 + 4`, `4 + 4 + 5`, etc.),
which changes what `P1-T1`, `P2-T4`, and similar slots actually mean.

**Two-stage workflow.** `export-church-teams` (Stage 1) owns the live
ChMeetings/WordPress reads, the `Church_Team_Status_ALL.xlsx`, and the
`schedule_input.json` machine contract.  `build-schedule-workbook` (Stage 2) is
an offline, fast, repeatable consumer of those artifacts.  The scheduling logic
lives in `middleware/schedule_workbook.py` (`ScheduleWorkbookBuilder`);
`church_teams_export.py` delegates to it under a strict one-way dependency
(`church_teams_export.py` → `schedule_workbook.py`, never the reverse).

One important operator consequence follows from that dependency:

- editing `venue_input.xlsx` does **not** update `schedule_input.json` by itself
- `build-schedule-workbook` does **not** regenerate `schedule_input.json`
- `export-church-teams` is the command that pulls venue edits back into the
  machine contract

So the practical rerun loops are:

| What changed? | What to rerun |
|---------------|---------------|
| `Venue-Input` or `Gym-Modes` | `export-church-teams`, then `build-schedule-workbook` |
| `Pool-Assignment` | `assign-pools`, then `export-church-teams`, then `build-schedule-workbook` |
| `Playoff-Slots` only | `export-church-teams`, then `produce-schedule` (or `run-schedule.bat` if you want a full rerun) |

The step-by-step operator walkthrough for these loops lives in
`docs/SCHEDULE-HOW-TO.md`.

The solver-rendered workbook (`Schedule-by-Time` / `Schedule-by-Sport` /
`Conflict-Audit`) is a
separate concern handled by `produce-schedule` — `build-schedule-workbook` does
not take a `--schedule-output` argument because none of its nine tabs render
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
