# Product Requirements Document (PRD)
## VAY Sports Fest — Scheduling Helper (GUI)

**Version:** 0.1 (draft for 2027 planning)
**Last Updated:** July 2026
**Maintainer:** VAY-SM Senior Staff
**Companion documents:** [PRD.md](PRD.md) (system-wide PRD), [SCHEDULING.md](SCHEDULING.md) (pipeline architecture), [SCHEDULE-HOW-TO.md](SCHEDULE-HOW-TO.md) (2026 operator guide)

---

## 1. Purpose of This Document

Scheduling is the most complex operation in `vaysf`. The 2026 season proved
the *pipeline* (four-step CLI + CP-SAT solver + importers) but also proved that
the *operator experience* does not scale: the season's authoritative schedule
was ultimately assembled by hand in Excel, exported to PDF, and re-imported
into the system through fragile visual-workbook parsers.

This PRD specifies the **Sports Fest Scheduling Helper** — a graphical
front-end over the existing middleware pipeline — so that in the 2027 season a
non-programmer operator can drive every stage of scheduling from a browser,
with the CLI remaining available as the power-user and automation path.

This document answers *what the Helper must do and why*. Implementation issues
will decompose it into build phases (§13).

---

## 2. What the 2026 Final Artifacts Tell Us

The eight PDFs delivered as the 2026 "system of record" are the best evidence
of what the Helper must produce and what it must replace:

| Artifact | What it is | How it was made |
|---|---|---|
| `VAY2026_Main_Schedule_FINAL.pdf` / `_Final_2.pdf` | Event-wide master grid: days × courts/rooms, color-coded game cells with team codes, ceremonies, meals, setup/teardown, closures, sport envelopes | Hand-built Excel visual grid (Loc), exported to PDF |
| `VAY2026_Pickleball_FINAL.pdf` / `_final_2.pdf` | Pickleball division schedules and brackets | Sport coordinator Excel, exported to PDF |
| `VAY2026_Coed_Soccer_FINAL.pdf` | Soccer groups, six pool matches, referee assignments, advancement bracket | Sport coordinator Excel, exported to PDF |
| `VAY2026_Table_Tennis_FINAL.pdf` | Table Tennis schedule + doubles rosters + rules | Sport coordinator Excel, exported to PDF |
| `VAY2026_Tennis_FINAL.pdf` | Tennis division schedule/brackets | Sport coordinator Excel, exported to PDF |
| `VAY2026_BC_Hosts_Judges Schedule_FINAL.pdf` | Bible Challenge hosts/judges staffing rotation | Hand-built Excel, exported to PDF |

Observed failure modes these artifacts encode (each maps to a requirement in
§7–§9):

1. **Filename versioning.** `FINAL` and `final_2` coexist for the Main
   Schedule and Pickleball. There is no authoritative version pointer; the
   operator must remember which file superseded which.
2. **Free-text cells.** The WVB `s` typo (read as "game 7") and the implicit
   "Basketball game 20 is a bye" convention required a human interpretation
   rulebook inside `SCHEDULING.md`. A GUI with structured cells makes these
   states impossible to mistype.
3. **Color semantics are fragile.** The Main Schedule's own legend swatches
   did not match the actual game-cell fill colors; the importer had to resolve
   sport by nearest-color match against `schedule_styles.SPORT_STYLES`.
4. **Roster/schedule drift across files.** The Table Tennis U35 discrepancy
   (roster said `SBC`, schedule said `FVC`) survived to publication gating and
   needed an explicit `--waive-table-tennis-discrepancy` flag.
5. **Sport workbooks each invent their own layout.** Every coordinator's
   Excel is a new parsing project; each new sport (Tennis, Pickleball in 2026)
   arrived with no importer at all.
6. **Staffing lives outside the system.** The BC hosts/judges schedule is a
   parallel hand-maintained artifact that must agree with the game schedule
   but nothing checks that it does.
7. **Late changes ripple invisibly.** The human scheduler confirmed that a
   late church request "can ripple through the entire event" — but the ripple
   is discovered by eyeball, not computed.

The Helper's core thesis: **keep the humans authoritative** (venue booking,
lottery draw, matchup identity, event envelope — exactly the 2026 precedence
hierarchy) **but move their authoring surface from freeform Excel into
structured GUI editors** so provenance, validation, and re-solving are
automatic instead of forensic.

---

## 3. Problem Statement

> An operator preparing the 2027 Sports Fest schedule must today coordinate
> ~10 CLI commands, 4+ hand-edited Excel workbooks, 6 generated JSON sidecars,
> and an email loop with sport coordinators — while manually tracking which
> artifact supersedes which. Every human edit requires knowing the correct
> rerun chain (`import-* → export-church-teams → build-schedule-workbook →
> run-schedule.bat`), and mistakes surface late as import audit errors or
> publication blocks.

The system's *engine* is sound. The *cockpit* is missing.

---

## 4. Goals

1. **One operator, one screen per stage.** Every scheduling stage (§6) has a
   dedicated GUI screen; the operator never needs a terminal for the happy
   path.
2. **The rerun chain becomes invisible.** When an input changes, the Helper
   knows what is now stale and offers a one-click "Regenerate" that runs the
   correct command sequence.
3. **Structured authoring replaces visual Excel.** Matchups, master-schedule
   blocks, and playoff pins are entered in editors that validate on entry
   (team codes against live rosters, times against venue windows) instead of
   being reverse-engineered from cell colors after the fact.
4. **Provenance and precedence are visible.** Every scheduled cell shows its
   source class (human matchup, master-schedule pin, solver placement,
   envelope, blackout) per the 2026 precedence table, and conflicts between
   sources surface as a work queue, not as buried log lines.
5. **The final deliverables are generated, not hand-exported.** The Helper
   renders the master grid and per-sport schedules to print-quality PDF from
   the same data that publishes to WordPress — one source, no drift between
   the PDF and the score-entry table.
6. **The 2026 file formats remain the interchange layer.** The Helper reads
   and writes the same `schedule_input.json`, sidecar JSONs, and
   `venue_input.xlsx` the pipeline already uses, so the CLI, tests, and
   Excel-fallback workflows keep working unchanged.

## 5. Non-Goals

- **Not a new solver.** The CP-SAT solver, contract validation
  (`schedule_contracts.py`), diagnostics (`schedule_diagnostics.py`), and
  publisher (`schedule_publisher.py`) are reused as-is behind the GUI.
- **Not a registration or approval UI.** ChMeetings and the WordPress plugin
  remain authoritative for who registered and who is approved.
- **Not a generic tournament scheduler.** Per repo policy, the Helper is
  VAY-specific: its sports list, precedence rules, and event envelope model
  are the VAY Sports Fest ones.
- **Not a multi-user collaborative editor in v1.** One operator drives the
  Helper; coordinators contribute through structured intake (§7.4) or Excel
  import fallback, not concurrent editing.
- **Not score entry / results.** Event-day results stay in the WordPress
  Results Desk flow.

---

## 6. Personas and the Stage Model

### Personas

| Persona | 2026 example | Interaction with the Helper |
|---|---|---|
| **Scheduling Operator** | Bumble | Drives all stages; the primary user |
| **Human Scheduler** | Loc | Authors matchups and the master grid — in 2027, ideally directly in the Helper's editors (or via Excel import fallback) |
| **Sport Coordinator** | Andrew (Badminton), Soccer/TT/Tennis/Pickleball leads | Supplies detailed schedules for envelope blocks; reviews their sport's generated PDF |
| **Leadership / Senior Staff** | John, Hanh, Sean | Reviews and approves; consumes read-only views and PDFs |

### The seven stages

The Helper organizes the season as a **Season Board** — a persistent
left-rail checklist mirroring the real chronology. Each stage is a screen;
stages unlock progressively but remain revisitable (registration keeps moving
until late June).

```
1. Demand        Layer-1 estimation while registration is open
2. Venue         record the booked venue (replaces venue_input.xlsx editing)
3. Draw          seeding, lottery draw, approved matchups
4. Master Plan   event-wide grid: envelopes, blackouts, pins (Layer 3)
5. Solve         fill unresolved space, diagnose, iterate
6. Review        conflict audit, discrepancy queue, leadership sign-off
7. Publish       WordPress publication + PDF pack generation
```

---

## 7. Stage-by-Stage GUI Specification

### 7.1 Stage 1 — Demand Dashboard (Layer 1)

**Replaces:** reading `Venue-Estimator`, `Pod-Resource-Estimate`, and
`Pod-Entries-Review` tabs out of `Schedule_Workbook_*.xlsx`.

- **Data freshness header.** Shows when `export-church-teams` last ran, with
  a **Refresh from live** button (runs the export; progress streamed to the
  UI). All later stages show the same staleness banner when the underlying
  snapshot is older than their inputs.
- **Demand cards per event** (BB, MVB, WVB, BC, SOC, and each racquet
  division): estimating teams/entries vs. potential ceiling, target pool
  games/team (from config), computed court-hours or room-minutes (BC's
  sequential-queue model displayed distinctly, as room-hours on a timeline,
  not courts).
- **Venue scenario slider.** The 3/4/5-court sketch becomes an interactive
  what-if: drag court counts and see projected end-times per day. Output is
  labeled *estimate — for venue negotiation*, mirroring the Layer-1 caveat.
- **Registration watchlist.** Divisions whose entry counts changed since last
  refresh are flagged, since pool geometry can shift (`4+3+3` → `6+4`).

### 7.2 Stage 2 — Venue Editor (Layer 2 inputs)

**Replaces:** hand-editing `venue_input.xlsx` (Venue-Input, Gym-Modes,
Playoff-Slots tabs).

- **Venue list + calendar strip.** Each physical venue is a card: dates,
  open/close windows, slot minutes, court/table/field counts. Days render as
  a horizontal strip so gaps and asymmetric weekends are visible.
- **Gym mode editor.** For each gym, a mode matrix (1 BB court *or* 2 VB
  courts *or* 6 badminton courts …) with the exclusive-group relationship
  drawn explicitly — the operator sees "these rows are the same physical
  room" instead of inferring it from a shared text tag.
- **Playoff pin placer.** Pins (QF/SF/Final/3rd) are placed by clicking a
  venue-day-time cell — the venue-centric form from Issue #127 made literal.
  The Helper validates on placement (inside the venue window, no overlap with
  other pins, court-count capacity) and shows reserved windows shaded on the
  strip so pool play visibly loses that inventory.
- **On save:** writes `venue_input.xlsx` (kept as the canonical file) and
  marks downstream artifacts stale.

### 7.3 Stage 3 — Draw Board (seeding, lottery, matchups)

**Replaces:** the editable `Pool-Assignment` tab + `assign-pools`, the
lottery workbook + `import-team-matchups`.

- **Seeding panel.** Registered teams per event with drag-to-rank seeds
  (prior-year winners pre-suggested). Persists to `pool_assignments.json`.
- **Draw ceremony mode.** The lottery drawing is a live VAY event. The Helper
  provides a projector-friendly full-screen mode that performs the serpentine
  draw with the audience watching: seeded teams placed first, unseeded teams
  revealed one at a time. Result is captured directly — no transcription from
  a whiteboard into Excel afterward.
- **Matchup editor.** For events where humans author matchups (2026:
  BB/MVB/WVB/SOC/BC), a structured grid: slot number, team A, team B (or the
  BC three-team triplet). Team codes are chosen from the live roster —
  unknown codes and wrong-event codes are impossible, byes are an explicit
  cell state (fixing failure modes #2 and #4). Excel import of a
  lottery-workbook remains as fallback intake, running the existing
  `import-team-matchups` audit and showing its findings inline.
- **Per-team game count summary** so a WVB 4-games-per-team plan is verified
  at entry, not at import audit.

### 7.4 Stage 4 — Master Plan Canvas (Layer 3)

**Replaces:** the hand-built visual Excel Main Schedule and
`import-master-schedule` / `import-match-schedule-overrides`.

This is the flagship screen: an interactive grid — **columns = courts/rooms
(grouped by venue), rows = time slots, one tab per event day** — the same
mental model as Loc's Excel, but structured.

- **Typed blocks, not colored cells.** Every block on the canvas has an
  explicit class from the 2026 taxonomy: *resolved matchup*, *bye/reserved*,
  *stage reservation* (`BB QF`), *broad envelope* (Badminton playoff block),
  *operational blackout* (setup, meal, service, ceremony, closed,
  community-game), *external-reference* (points at a sport workbook). Colors
  come from `SPORT_STYLES` and are rendering, never meaning (failure mode #3).
- **Drag-and-drop with live validation.** Dragging a game block to a new cell
  immediately checks: venue window, court-type routing, exclusive-group gym
  mode, team double-booking, shared-athlete conflict edges, and precedence
  (pool before SF before Final). Violations render on the block
  (hard = red/blocked, soft = amber warning with explanation).
- **Ripple preview.** Before committing a move, the Helper shows what else
  becomes invalid or must re-solve — making the "late change ripples through
  the event" cost visible before it is paid (failure mode #7).
- **Envelope drill-down.** A broad envelope block (e.g., Badminton playoffs
  on 3 courts) opens a sub-schedule panel where the coordinator's detailed
  games live. Sub-games are validated to fit inside the envelope; a
  coordinator's Excel can be imported into the envelope as fallback intake,
  with out-of-envelope rows queued as discrepancies rather than silently
  extending availability.
- **Lock states.** Blocks can be locked (leadership-confirmed ceremonies and
  finals become hard once allocated). Locked blocks are immovable without an
  explicit unlock action that is recorded in the change log.
- **Special-duration slots** are first-class: the BC Final's 2:30–4:00 PM
  window is a block with a real 90-minute duration, not a footnote.
- **Staffing lane (v1.1).** An optional per-room lane for hosts/judges
  assignments (the BC Hosts/Judges schedule), validated against the game
  blocks in the same room so staffing and games cannot drift (failure
  mode #6).

### 7.5 Stage 5 — Solve & Diagnose

**Replaces:** `run-schedule.bat`, `solve-schedule`, `diagnose-schedule`, and
reading solver logs.

- **Solve button with scope display.** Before solving, the Helper lists
  exactly what the solver may touch: *N unresolved games; M fixed pins,
  K locked blocks, and all blackouts are untouchable*. This enforces the 2026
  rule that the solver fills only unresolved legal space.
- **Progress + result panel.** Per-pool status (BC Station → Soccer Field →
  racquet pools → Gym Core, in solve-priority order), wall time, and the
  contract-validation findings rendered as actionable items (each names its
  `game_id`/`resource_id` and deep-links to the offending editor).
- **Diagnostics, visualized.** The `diagnose-schedule` vectors — demand vs.
  supply per resource type, gym-mode shortfalls, overlapping mode windows,
  unscheduled games, precedence problems — render as a triage list sorted by
  "what should I adjust next", each with a jump-to-stage link.
- **Solution overlay on the canvas.** Solver placements appear on the Master
  Plan canvas in a visually distinct "proposed" treatment. The operator
  accepts all, or drags individual proposals (which converts them to human
  pins), then re-solves the remainder. This is the iterative operator loop
  (Issues #139/#140) with the file shuffling removed.

### 7.6 Stage 6 — Review & Audit

**Replaces:** `Conflict-Audit` tab reading, import audit reports, and the
pre-publication judgment calls.

- **Conflict audit board.** Shared-athlete conflicts grouped by athlete and
  severity (primary-sport vs. secondary), each showing the two games, the
  gap between them, and status (avoided / remaining / PlanningOnly).
  Unprotected racquet entries (`UnresolvedDoubles`, bye-round entries) are a
  visible chase-down list with the missing-partner reason.
- **Discrepancy queue.** Every cross-source disagreement — roster vs.
  schedule team code, sport workbook outside its envelope, XLSX/PDF pair
  divergence, master plan vs. venue availability — is a queue item with the
  two sources shown side-by-side and explicit resolutions: *fix source A*,
  *fix source B*, or *waive with reason* (the generalization of
  `--waive-table-tennis-discrepancy`; waivers are logged with operator and
  timestamp).
- **Readability checks.** Soft-quality signals the 2026 scheduler cared
  about: back-to-back games within a sport, per-day spread, VB net-height
  flips, teams with long idle gaps, churches with simultaneous games across
  sports.
- **Sign-off checklist.** A publish gate mirroring the release checklist:
  zero unscheduled games, zero unwaived discrepancies, all envelope
  sub-schedules resolved or explicitly deferred, leadership sign-off
  recorded.

### 7.7 Stage 7 — Publish & Export

**Replaces:** `import-approved-games`, `publish-schedule`, and hand-exporting
each Excel workbook to PDF.

- **Publish to WordPress.** One action that builds stable `game_key` records
  and runs the existing `publish-schedule` path with a mandatory dry-run
  preview first (rows to be created/updated/removed shown as a diff).
  `publish-schedule` remains the only code path that writes to WordPress.
- **PDF pack generator.** From the same published data, render the 2027
  equivalents of the 2026 pack: the master grid (per day, color-coded,
  legend generated from `SPORT_STYLES` so it *cannot* disagree with the
  cells), one PDF per sport in a standardized layout (schedule + bracket +
  roster reference), and the hosts/judges staffing sheet. Filenames carry a
  build number and content hash; the Helper tracks which pack is *current*
  (failure mode #1).
- **Version history.** Every publish and every pack build is a snapshot with
  a diff view against the previous one ("what changed since the version the
  coordinators printed?").

---

## 8. Cross-Cutting Requirements

### 8.1 Staleness and the dependency graph

The Helper owns the artifact dependency graph (today's "what to rerun" table
in `SCHEDULING.md`). Every screen shows whether its inputs are current;
a global **Regenerate** action runs the minimal correct chain
(`import-* → export-church-teams → build-schedule-workbook → solve`) with
streamed progress. The operator never memorizes the chain again.

### 8.2 Provenance on every cell

Every scheduled game/block records: source class (per the precedence table),
originating artifact or editor action, timestamp, and operator. Hovering any
cell answers "who decided this and when." Precedence conflicts are never
resolved silently — they enter the discrepancy queue.

### 8.3 Change log

All mutating actions (block moves, pin edits, waiver grants, unlocks,
solver-accept) append to a human-readable season change log, exportable for
leadership review.

### 8.4 Excel remains a citizen, not the backbone

Import fallbacks (lottery workbook, coordinator schedules, master-schedule
visual grid) are retained for 2027 because coordinators may still deliver
Excel. Imports always run the existing audit logic and land findings in the
discrepancy queue. Exports (planning workbook tabs) remain available for
people who review in Excel. But the Helper's editors are the primary
authoring surface, and the JSON sidecars remain the machine truth.

### 8.5 Bilingual and print fidelity

Team and church names render with full Vietnamese diacritics everywhere,
including generated PDFs (per repo convention: never strip accents for
display). PDF layouts must be legible in black-and-white photocopy — color
encodes sport, but each block also carries its sport code in text.

### 8.6 Offline-tolerant

Stages 2–6 operate on local snapshots; only *Refresh from live* (Stage 1)
and *Publish* (Stage 7) require ChMeetings/WordPress connectivity. The gym
has bad Wi-Fi; the Helper must not.

---

## 9. Architecture

### Recommended shape

**A local-first web application served by the existing Python middleware on
the operator's Windows machine.**

```
Browser (operator UI)
   │  HTTP (localhost)
   ▼
FastAPI service (new: middleware/helper/)
   │  direct Python calls — no subprocess re-parsing
   ▼
Existing modules: church_teams_export, schedule_workbook, gym_allocator,
scheduler, schedule_contracts, schedule_diagnostics, schedule_publisher
   │
   ▼
Existing artifacts: venue_input.xlsx, schedule_input.json, sidecar JSONs,
pool_assignments.json, EXPORT_DIR workbooks
```

Rationale:

- **Reuses the engine.** The solver, contracts, diagnostics, importers, and
  publisher are already modular Python; a FastAPI layer calls them in-process
  and streams progress over WebSocket/SSE. No logic is duplicated.
- **No new deployment surface.** It runs where the middleware already runs
  (the operator's Windows machine), started via a `run-helper.bat` alongside
  the existing batch scripts. Bluehost/WordPress is untouched except through
  the existing publisher.
- **Files stay canonical.** The Helper reads/writes the same files the CLI
  does, so CLI and GUI can be interleaved safely and the existing pytest
  suite keeps guarding the engine. New Helper state (locks, waivers,
  provenance, change log) lives in a local SQLite database in `DATA_DIR`
  (§9.5) that the CLI path can ignore.

### 9.1 Service layout

New code lives in one package so the boundary with the engine stays visible
in the tree:

```
middleware/
├── helper/
│   ├── app.py              # FastAPI app factory; binds 127.0.0.1 only
│   ├── api/                # one router per stage
│   │   ├── season.py       #   Season Board, staleness, regenerate
│   │   ├── demand.py       #   Stage 1
│   │   ├── venue.py        #   Stage 2
│   │   ├── draw.py         #   Stage 3
│   │   ├── plan.py         #   Stage 4 (blocks, moves, validation)
│   │   ├── solve.py        #   Stage 5 (jobs, diagnostics)
│   │   ├── review.py       #   Stage 6 (conflicts, discrepancies, waivers)
│   │   └── publish.py      #   Stage 7 (dry-run, execute, pack builds)
│   ├── services/
│   │   ├── artifacts.py    # dependency graph + content-hash staleness
│   │   ├── jobs.py         # background job runner + progress streaming
│   │   ├── plan_rules.py   # static move-validation (no solver invocation)
│   │   └── state.py        # helper_state.sqlite access layer
│   ├── pdf/                # PDF pack renderer + HTML print templates
│   └── ui/                 # built SPA static assets, served by FastAPI
├── run-helper.bat          # start service + open browser
└── (existing modules unchanged)
```

Dependency rule (same spirit as `church_teams_export.py` →
`schedule_workbook.py`): `helper/*` imports engine modules; **no engine
module ever imports from `helper/`**. The CLI must keep working with the
`helper/` directory deleted.

### 9.2 API surface (v1 sketch)

All endpoints are JSON over localhost. Mutations return the new resource
state plus any staleness transitions they caused.

| Method + path | Purpose |
|---|---|
| `GET /api/season` | Season Board: stage statuses, artifact freshness, active job |
| `POST /api/season/regenerate` | Run the minimal correct rerun chain (returns a job id) |
| `GET /api/demand` | Demand cards, scenario sketch inputs, registration watchlist |
| `GET /api/venue` / `PUT /api/venue` | Read/write venue model (persists to `venue_input.xlsx`) |
| `POST /api/venue/pins/validate` | Check a playoff pin placement before saving |
| `GET /api/draw/{event}` / `PUT /api/draw/{event}` | Seeds, draw results, matchup grid per event |
| `POST /api/draw/{event}/ceremony` | Start/advance ceremony-mode draw (offline-safe) |
| `POST /api/import/{kind}` | Excel fallback intake (`matchups`, `master-schedule`, `sport-detail`); returns audit findings |
| `GET /api/plan/days/{day}` | All blocks for one day tab (typed, with provenance) |
| `POST /api/plan/validate-move` | Dry-run a block move; returns violations + ripple set |
| `PATCH /api/plan/blocks/{id}` | Commit a move/edit/lock/unlock (writes change log) |
| `POST /api/solve` | Launch solve job (scope summary echoed back first) |
| `GET /api/jobs/{id}` / `GET /api/jobs/{id}/events` | Job status / SSE progress stream |
| `GET /api/diagnostics` | `diagnose-schedule` vectors as triage items with deep links |
| `GET /api/review/conflicts` | Conflict audit board data |
| `GET /api/review/discrepancies` / `POST /api/review/discrepancies/{id}/resolve` | Queue + fix-A/fix-B/waive resolutions |
| `GET /api/review/checklist` | Sign-off gate state |
| `POST /api/publish/dry-run` / `POST /api/publish/execute` | Guarded WordPress publication (execute requires a dry-run token from the same input hash) |
| `POST /api/pack/build` / `GET /api/pack/builds` | PDF pack generation + version history |

### 9.3 Job model

Every long-running action (refresh from live, regenerate, solve, publish,
pack build) is a **job**:

- Jobs run in a background worker; **at most one job at a time** (the
  single-operator invariant made structural — two concurrent
  `export-church-teams` runs would race on the same artifacts).
- A job record carries `id`, `kind`, `status`
  (`queued|running|succeeded|failed`), start/end times, structured log lines,
  and the artifact hashes it read and wrote.
- Progress streams to the UI over **Server-Sent Events** (simpler than
  WebSocket, one-directional is all we need). The engine's existing logging
  is captured via a per-job handler — engine modules are not modified to
  report progress.
- Jobs invoke engine modules **in-process** (direct function calls), not via
  `subprocess` to the CLI, so errors carry real tracebacks and no output
  re-parsing exists. The CLI and the Helper are two thin front-ends over the
  same functions.

### 9.4 Staleness and the artifact dependency graph

`services/artifacts.py` formalizes the "what to rerun" table from
`SCHEDULING.md` as a DAG:

- **Nodes:** `venue_input.xlsx`, `pool_assignments.json`,
  `manual_team_matchups.json`, `manual_schedule_overrides.json`,
  `match_schedule_overrides.json`, `schedule_input.json`,
  `schedule_output.json`, `Schedule_Workbook_*.xlsx`, `VAYSF_Schedule_*.xlsx`,
  `approved_schedule_*.json`, pack builds.
- **Edges:** producer command → consumed artifacts (e.g. `solve-schedule`
  reads `schedule_input.json`, writes `schedule_output.json`).
- Each generation records the **content hash of every input** it consumed
  (stored in `helper_state.sqlite`). An artifact is *stale* when any of its
  recorded input hashes differs from the file currently on disk. This also
  detects out-of-band CLI or hand edits — external modification is just
  another hash mismatch, surfaced in the change log rather than fought.
- `POST /api/season/regenerate` topologically sorts the stale subgraph and
  runs only the necessary producers, in order, as one job.

### 9.5 Helper state persistence

A single SQLite file, `DATA_DIR/helper_state.sqlite`. SQLite over a JSON
sidecar because the change log and provenance tables are append-heavy,
queried by screen filters, and must survive a crash mid-write
(WAL mode); Python's `sqlite3` adds no new dependency. Tables:

| Table | Contents |
|---|---|
| `blocks` | Master Plan block registry: id, class, day, resource, start/end slot, payload (game_id or label), style key |
| `provenance` | block id → source class, source ref (file/import/editor action), actor, timestamp |
| `locks` | block id, locked_by, locked_at, reason; unlock events go to `change_log` |
| `waivers` | discrepancy id, fingerprint, waived_by, timestamp, reason |
| `discrepancies` | open/resolved cross-source disagreements with both source refs |
| `staffing` | room, slot, role, person (v1.1 lane) |
| `artifact_hashes` | artifact path, producer job id, input-hash snapshot (staleness engine, §9.4) |
| `jobs` | job records incl. captured logs |
| `change_log` | append-only mutation history (also exportable to Markdown) |
| `pack_builds` | build_no, content hash, file list, published_at |

**Interchange rule:** anything the *solver or publisher* must see travels in
the existing JSON contract (using the reserved `x_` / `operator_notes`
annotation namespace where needed — e.g. locked solver proposals become
ordinary `playoff_slots`-style fixed assignments). SQLite holds only
GUI-side state; deleting it loses locks/waivers/history but never corrupts a
schedule.

### 9.6 Move validation engine (`plan_rules.py`)

Canvas interactions need sub-second feedback, so `validate-move` does **not**
run CP-SAT. It statically evaluates the checkable subset of the constraint
model against the current placement map:

- resource window and court-type routing (C4), slot occupancy (C2, multi-slot
  aware, C7), team double-booking (C3), same-day adjacency/min-rest (C6),
  exclusive-group gym-mode consistency, precedence direction
  (pool < SF < Final), shared-athlete conflict edges (from
  `team_conflicts`), and blackout/lock collision.
- Verdicts are structured: `{rule, severity: hard|soft, message, refs[]}`.
  Hard violations block the drop; soft ones annotate it.
- The **ripple set** is computed by re-running these checks for every block
  whose validity depended on the moved block's old or new position, plus the
  set of solver placements that would need re-solving. Ripple preview is
  advisory; the authoritative re-check is the next solve's contract
  validation — `plan_rules.py` never needs to be *complete*, only fast and
  never wrong about hard violations it does report.

### 9.7 Frontend stack

- **React + TypeScript + Vite**, single-page app, served as static files by
  FastAPI. No runtime network access except the localhost API (gym-Wi-Fi
  rule, §8.6).
- Server state via **TanStack Query** keyed by artifact hashes, so a
  completed job invalidates exactly the screens whose inputs changed.
- The Master Plan canvas is a **CSS-grid virtualized custom component**
  (columns = courts grouped by venue, rows = time slots) with pointer-event
  drag-and-drop. No heavyweight scheduler/grid library: the 2026 event is
  ~10 courts × ~30 slots × 4 day-tabs, well within DOM budget, and typed
  blocks with our own validation hooks are the product.
- Sport colors come from a build-time export of
  `schedule_styles.SPORT_STYLES` so UI, Excel, and PDF can never disagree.
- Frontend build artifacts are produced at release time and committed under
  `helper/ui/` (mirroring the `plugins/vaysf.zip` convention) so the
  operator's machine needs Python only, never Node.

### 9.8 PDF pack rendering

Recommendation: **server-driven HTML print templates rendered to PDF by
headless Chromium** (via `playwright`'s bundled browser, invoked only for
pack builds):

- The print templates reuse the canvas's rendering vocabulary, so the PDF
  master grid is pixel-consistent with what the operator reviewed on screen
  — the strongest guarantee against a 2026-style legend/cell mismatch.
- Full Unicode/diacritics fidelity comes free from the browser text stack
  (§8.5), which pure-Python PDF layout libraries make hard.
- Fallback if the Chromium dependency proves troublesome on the operator
  Windows box: `reportlab` layouts for the per-sport pack only, keeping the
  master grid as the browser-printed piece. Decide in H4 with a spike.

### 9.9 Security and testing posture

- The service binds `127.0.0.1` only; `run-helper.bat` starts it and opens
  the browser with a random session token in the URL (defense against other
  local processes, not against the operator). No accounts in v1 — the
  machine login is the auth boundary. CORS disabled; no external origins.
- Secrets stay in `middleware/.env` exactly as today; the browser never
  receives API keys — all ChMeetings/WordPress traffic goes through the
  middleware process.
- **Testing:** every `api/` router gets pytest coverage in mock mode against
  the existing fixtures (per §11.5). `plan_rules.py` gets table-driven unit
  tests mirroring the solver-constraint tests. Pack builds get golden-file
  tests on the *structural* output (block positions/labels extracted from
  the print HTML), not PDF bytes.

### Explicitly rejected alternatives

- **WordPress plugin UI** — scheduling iteration is local, pre-publication,
  and data-heavy; putting it on Bluehost couples drafting to hosting and
  violates the "publish is the only WP write path" boundary.
- **Excel as the GUI (more macros/tabs)** — 2026 demonstrated the ceiling of
  this approach; the failure modes in §2 are inherent to freeform cells.
- **Desktop app (Tkinter/Qt/Electron)** — heavier build/packaging burden for
  one machine; a localhost web app gets modern grid/drag-drop tooling with
  none of that cost.

---

## 10. Data Model Additions

New concepts the Helper introduces (persisted in `helper_state.sqlite` per
§9.5, never breaking the `schedule_input.json` contract — new fields ride in
the reserved `x_`/`operator_notes` annotation namespace where they must
travel with the contract):

| Concept | Fields (sketch) |
|---|---|
| Block class | `class: matchup \| bye \| stage_reservation \| envelope \| blackout \| external_ref` |
| Lock | `locked_by`, `locked_at`, `reason` |
| Provenance | `source_class`, `source_ref`, `actor`, `at` |
| Waiver | `discrepancy_id`, `waived_by`, `at`, `reason` |
| Staffing assignment | `room`, `slot`, `role: host \| judge \| referee`, `person` |
| Pack build | `build_no`, `content_hash`, `files[]`, `published_at` |

The six-tier solver objective, constraint set (C1–C7), pool decomposition,
and precedence semantics are unchanged and are rendered — not re-implemented —
by the GUI.

---

## 11. Constraints and Invariants the GUI Must Respect

These are inherited from the 2026 season and are non-negotiable in v1:

1. **Precedence hierarchy** exactly as in `SCHEDULING.md` §"2026 Source Of
   Truth And Precedence". The GUI visualizes it; it never reorders it.
2. **The solver fills only unresolved legal space.** Human blocks, pins, and
   blackouts are never moved by a solve.
3. **Publish is guarded.** Dry-run preview is mandatory; unwaived
   discrepancies block execution; `publish-schedule` remains the only
   WordPress write path.
4. **Registration data is fixed upstream.** The Helper links to ChMeetings/
   WordPress for roster fixes; it never edits registration or approval state.
5. **Mock-mode testability.** Every Helper endpoint must work against the
   existing test fixtures with no live credentials, so CI covers the GUI's
   API layer the same way it covers the pipeline.

---

## 12. Success Metrics (2027 season)

| Metric | 2026 baseline | 2027 target |
|---|---|---|
| Terminal commands needed for a full schedule iteration | ~5–10 per loop | 0 (happy path) |
| Time from "late matchup change" to re-validated full schedule | hours (manual rerun chain + eyeball) | < 15 minutes, ripple shown before commit |
| Schedule-vs-roster discrepancies discovered at publication gate | ≥ 1 (TT `SBC`/`FVC`) | 0 — all caught at entry or queued in Review |
| Interpretation rules needed to parse the master schedule | a documented rulebook (typos, byes, legend mismatch) | 0 — structured cells |
| "Which file is FINAL?" ambiguity | FINAL vs final_2 pairs | Single current pack pointer + version history |
| PDF pack vs. WordPress score-entry drift | manually reconciled | impossible by construction (one source) |
| People able to operate scheduling end-to-end | 1 (developer-operator) | ≥ 2, including one non-programmer |

---

## 13. Rollout Plan (tied to the season calendar)

Phases are sized so each delivers standalone value even if later phases slip;
the CLI remains the safety net throughout.

| Phase | Target | Scope |
|---|---|---|
| **H1 — Read-only cockpit** | Winter 2026–27 | FastAPI service + Season Board + Demand Dashboard + rendered (read-only) Master Plan canvas from existing JSONs + Solve/Diagnose panel wrapping existing commands + staleness tracking. *Value: no more log spelunking; one Regenerate button.* |
| **H2 — Structured editors** | Early spring 2027 (before venue booking) | Venue Editor, Draw Board (incl. ceremony mode), Matchup Editor; Excel importers wired as fallback intake with inline audits. |
| **H3 — Interactive canvas** | Late spring 2027 (before lottery drawing) | Drag-and-drop Master Plan with live validation, ripple preview, locks, envelope drill-down, solver-proposal overlay. |
| **H4 — Review & publish** | Early June 2027 (before schedule finalization) | Conflict audit board, discrepancy queue with waivers, sign-off checklist, publish flow, PDF pack generator with version history. |
| **H5 — Polish (v1.1)** | If time permits | Staffing lane, readability heuristics, coordinator read-only share links. |

Season fallback rule: at any point, the artifacts on disk are valid CLI
inputs, so if the Helper is behind schedule the 2026 workflow still runs the
event.

---

## 14. Risks and Open Questions

1. **Coordinator adoption.** If sport coordinators keep authoring in Excel,
   the Helper's value concentrates in import-audit UX rather than editors.
   Mitigation: envelope drill-down treats coordinator Excel as first-class
   intake; standardized per-sport export templates give coordinators a
   familiar starting file.
2. **Canvas complexity.** Drag-and-drop with live constraint checking is the
   largest frontend build. Mitigation: H1 ships the canvas read-only; H3 adds
   interaction; validation logic stays server-side in existing Python.
3. **Two writers, one file.** GUI and CLI both writing sidecars risks
   clobbering. Mitigation: the Helper takes a lock file while running and
   re-reads artifacts before each mutation; the change log records external
   modifications detected via content hash.
4. **Draw ceremony reliability.** A live-audience feature must not fail on
   stage. Mitigation: ceremony mode is fully offline (roster snapshot loaded
   beforehand) and its output is a plain `pool_assignments.json` an operator
   could also produce by hand.
5. **Open:** should leadership sign-off (Stage 6) be recorded per-person with
   an emailed review link, or is a single operator-recorded checkbox enough
   for 2027? (Recommend: checkbox in v1; review links in v1.1.)
6. **Open:** does the hosts/judges staffing lane generalize to referees for
   Soccer and line judges for racquet finals in v1.1, or BC-only first?
   (Recommend: BC-only first — it is the one with a proven 2026 artifact.)

---

## 15. Glossary Cross-Reference

Terms used here — *Layer 1/2/3, Stage A/B, Gym Core, shared-athlete edge,
PlanningOnly, envelope, blackout, pin, precedence, pool decomposition* — are
defined in [SCHEDULING.md](SCHEDULING.md) and are used with identical meaning.
The Helper introduces only: **Season Board, block class, ripple preview,
discrepancy queue, waiver, pack build**.
