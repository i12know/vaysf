# How to Create the Sports Fest Competition Schedule

This guide walks you through the four-step scheduling pipeline from venue setup to a
printed Excel timetable.  For the full technical reference, see `docs/SCHEDULING.md`.

---

## Prerequisites

- `pip install -r requirements.txt` done (includes `ortools`)
- `.env` configured with working API credentials
- Approved rosters in WordPress (run a full sync first if unsure)

---

## Step 1 — Fill out `venue_input.xlsx`

Copy the template into the data folder and rename it:

```
middleware/data/SportsFest_2026_Venue_Input_Template.xlsx
→ middleware/data/venue_input.xlsx
```

The file is gitignored — do not commit it.  It has three tabs:

### `Venue-Input` tab

One row per physical court or table resource.  Required columns:

| Column | Example | Notes |
|--------|---------|-------|
| Sport / Resource Type | `Gym Court` | Must match a `POD_RESOURCE_TYPE_*` or `GYM_RESOURCE_TYPE` constant in `config.py` |
| Day | `Sat-1` | `Sat-1`, `Sat-2`, or `Sun` |
| Open Time | `08:00` | 24-hour format |
| Close Time | `21:00` | Last slot starts before this time |
| Slot Minutes | `60` | Game duration for this resource |
| Quantity | `4` | Number of identical courts on this day |
| Exclusive Venue Group | `Main Gym` | Fill this in when one physical gym can be configured as BB courts **or** VB courts but not both simultaneously.  Tag every row for the same gym with the same label.  Leave blank for standalone courts. |

### `Gym-Modes` tab

One row per physical gym.  Records how many courts each gym yields per sport mode.
Use `0` for modes the gym cannot host.

| Column | Example |
|--------|---------|
| Gym Name | `Main Gym` |
| Basketball Courts | `1` |
| Volleyball Courts | `2` |
| Badminton Courts | `0` |
| Pickleball Courts | `0` |
| Soccer Fields | `0` |

### `Playoff-Slots` tab

One row per knockout game (QF, Semi, Final, 3rd place).  The solver does **not**
assign playoff timing — you control it exactly here.

| Column | Example | Notes |
|--------|---------|-------|
| `game_id` | `BBM-Final` | Unique; used in the schedule output |
| `event` | `Basketball - Men Team` | Must match the event name exactly |
| `stage` | `Final` | `QF`, `Semi`, `Final`, or `3rd` |
| `resource_id` | `GYM-Sat-2-1` | Must match a `resource_id` from the `resources` array in `schedule_input.json` (run `export-church-teams` first, then copy IDs from that file) |
| `slot` | `Sat-2-14:00` | `Day-HH:MM` format |

To lock in a finale order (e.g. VB Women → VB Men → Basketball back-to-back),
put those rows in that order with consecutive slot values.

---

## Step 2 — (Optional) Adjust config constants

Open `middleware/config.py` and check these values match your new venue:

| Constant | Default | What it controls |
|----------|---------|-----------------|
| `SCHEDULE_SOLVER_GYM_COURTS` | `4` | Number of gym courts for the solver scenario |
| `SCHEDULE_SKETCH_SATURDAY_START` | `8` | First game hour on Saturday (24h) |
| `SCHEDULE_SKETCH_SATURDAY_LAST_GAME` | `20` | Last game start hour on Saturday |
| `SCHEDULE_SKETCH_SUNDAY_START` | `13` | First game hour on Sunday |
| `SCHEDULE_SKETCH_SUNDAY_LAST_GAME` | `20` | Last game start hour on Sunday |

---

## Step 3 — Pull registrations and generate `schedule_input.json`

```bash
cd middleware
python main.py export-church-teams
```

Because `venue_input.xlsx` is present, this also writes a **Schedule-Input** tab in
the output workbook and a `schedule_input.json` alongside it.  That JSON file is the
machine contract the solver reads in the next step.

**Check the output:** open `Church_Team_Status_ALL_*.xlsx` and look at the
`Schedule-Input` tab to verify game counts and resource rows look right before solving.

### Optional — offline planning workbook

Before solving you can iterate on venue layout without hitting the live APIs:

```bash
python main.py build-schedule-workbook
```

This produces a 6-tab planning Excel (`Venue-Estimator`, `Pod-Divisions`,
`Court-Schedule-Sketch`, etc.) so coordinators can verify court counts and time
estimates.

---

## Step 4 — Run the CP-SAT solver

**On Windows (recommended):**

```bat
run-schedule.bat
```

This runs both the solver and the Excel renderer in one shot and prints a clear
pass/fail summary.

**Or run each step individually:**

```bash
python main.py solve-schedule
```

Exit codes:

| Code | Meaning | What to do |
|------|---------|-----------|
| `0` | All games scheduled (OPTIMAL or FEASIBLE) | Proceed to Step 5 |
| `1` | Partial — some games unscheduled | Check the log; add courts or expand time window, then re-run |
| `2` | Timeout — no solution found | Set `SCHEDULE_SOLVER_TIMEOUT=120` and retry |
| `3+` | Hard error (bad input, ortools not installed) | Check the log for details |

**If you get exit code `1` (partial):** the log prints a diagnostics table showing
required slots vs. available slots per resource type.  The usual fix is increasing
`Quantity` in `venue_input.xlsx` for the over-subscribed resource type, or widening
the time window in `config.py`.

---

## Step 5 — Render the Excel timetable

```bash
python main.py produce-schedule
```

Writes `VAYSF_Schedule_YYYY-MM-DD.xlsx` to `EXPORT_DIR`.  Two tabs:

- **Schedule-by-Time** — color-coded grid view for floor coordinators
- **Schedule-by-Sport** — flat list with auto-filter for sport directors

Playoff games from your `Playoff-Slots` tab appear alongside pool play.

---

## Last-minute playoff changes

If a playoff game time or court needs to change during the tournament:

1. Edit the `Playoff-Slots` tab in `venue_input.xlsx`.
2. Re-run `produce-schedule` only — no solver re-run needed:

```bash
python main.py produce-schedule --input data/schedule_output.json --constraint data/schedule_input.json
```

---

## Quick checklist

- [ ] `venue_input.xlsx` filled out (Venue-Input, Gym-Modes, Playoff-Slots tabs)
- [ ] `SCHEDULE_SOLVER_GYM_COURTS` in `config.py` matches your gym court count
- [ ] Time window constants updated if venue hours changed
- [ ] `export-church-teams` run successfully → `schedule_input.json` produced
- [ ] `solve-schedule` exits `0` (or `1` with acceptable partial result)
- [ ] `produce-schedule` writes `VAYSF_Schedule_*.xlsx` to `EXPORT_DIR`
- [ ] Coordinators review both tabs before printing
