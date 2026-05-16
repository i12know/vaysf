# CHANGELOG

## Unreleased

### Breaking Changes / Refactor
- Solver now handles **pool play only**; playoffs managed via Playoff-Slots tab in `venue_input.xlsx`
  - Gym sport playoff games (QF/Semi/Final/3rd) removed from `schedule_input.json` `games` array — `_build_gym_game_objects()` now emits pool-play games only
  - New `Playoff-Slots` tab in `venue_input.xlsx`: coordinators fill in one row per playoff game with columns `game_id`, `event`, `stage`, `resource_id`, `slot`; optional `team_a_id`, `team_b_id`, `duration_minutes`
  - If the tab is absent, a `WARNING` is logged and `playoff_slots` is an empty list — no crash
  - Playoff slots are stored in `schedule_input.json` under `"playoff_slots"` and merged into `schedule_output.json` `"assignments"` by the solver unchanged — last-minute changes require only editing the tab and re-running `produce-schedule` (no re-solve needed)
  - Finale order is now controlled by row order in the Playoff-Slots tab rather than solver constraints
  - Removed constraints C5 (stage ordering), C8 (per-game time windows), C9 (finale sequence) from the CP-SAT solver
  - Removed config constants: `SCHEDULE_STAGE_WINDOWS`, `SCHEDULE_FINAL_SEQUENCE`, `GYM_SPORT_EVENTS`
  - Removed methods: `_build_precedence_objects()`, `_build_sequence_objects()`; replaced with `_load_playoff_slots()`
  - Updated `_write_schedule_input_tab()`: Precedence section replaced with Playoff-Slots section
  - 8 solver tests removed (C5/C8/C9); 1 new test added (`test_solve_playoff_slots_passed_through`); 22 tests total

### Bug Fixes
- Reserve manual playoff slots from the pool-play solver
  - New `validate_playoff_slots()` validates each playoff row (real `resource_id`, real `slot` label, no duplicate court/slot) and extracts per-pool `blocked_slots` so the CP-SAT pool-play solver cannot place a pool game on a court/time already given to a playoff game
  - New `ensure_unique_assignment_slots()` guards the merged output against collisions
  - 2 new solver tests: pool game pushed off a reserved slot, duplicate playoff reservation raises
- Fixed C6 min-rest constraint incorrectly spanning day boundaries — resolves issue #97 A1
  - Global slot indices are contiguous across days, so the last slot of Sat-1 and the first slot of Sun-1 were treated as "adjacent" and a team was falsely forbidden from playing both
  - Added `global_to_day` map in `_solve_one_pool()`; C6 `AddBoolOr` is now skipped when the two adjacent global indices belong to different days
  - Added regression test `test_solve_c6_min_rest_does_not_span_day_boundary`

### New Features
- Split the scheduling workbook pipeline out of `church_teams_export.py` into a dedicated module — closes [#98](https://github.com/i12know/vaysf/issues/98)
  - New `middleware/schedule_workbook.py` with a `ScheduleWorkbookBuilder` class that owns all scheduling logic: `schedule_input.json` builders, pool planning, the six planning tabs, and the `produce-schedule` renderer
  - `church_teams_export.py` delegates the moved methods to `ScheduleWorkbookBuilder` under a strict one-way dependency (`church_teams_export.py` → `schedule_workbook.py`, never the reverse); `export-church-teams` and `produce-schedule` behavior is unchanged
  - New `python main.py build-schedule-workbook [--input-json …] [--input-xlsx …] [--output …]` command builds the offline planning workbook (`Schedule_Workbook_YYYY-MM-DD.xlsx`) without re-running a live export
  - `--input-json` resolves in priority order when omitted: sibling of `--input-xlsx`, then `EXPORT_DIR/schedule_input.json`, then `DATA_DIR/schedule_input.json`
  - New `read_roster_validation_rows()` / `_read_xlsx_sheet_rows()` parse the `Roster` and `Validation-Issues` tabs of an `ALL` workbook back into builder row dicts; missing files or tabs degrade to empty lists with a `WARNING`
  - When no `venue_input.xlsx` is supplied, the `Pod-Resource-Estimate` tab derives court availability from the `schedule_input.json` `resources` so offline builds stay self-consistent
  - Transition behavior: `Church_Team_Status_ALL.xlsx` still contains the six scheduling tabs; they are intentionally duplicated with the standalone workbook for now
  - Pure scheduling tests migrated from `test_church_teams_export.py` to `test_schedule_workbook.py`; `_write_excel_report` integration tests stay; new tests cover `build-schedule-workbook` and the xlsx-tab readers
  - `docs/SCHEDULING.md` documents the two-stage workflow and the 4-team pool tiebreaker caveat (the fixed 4-team format never plays T1 vs T4 or T2 vs T3)
- Added gym-mode venue modeling to `venue_input.xlsx` for gyms that can be configured one way or another but not both at once (e.g. 1 Basketball Court **or** 2 Volleyball Courts per time block)
  - New `Exclusive Venue Group` column in the `Venue-Input` tab: rows sharing a group value compete for the same physical gym; `_load_venue_input_rows()` attaches the value to each resource object as `exclusive_group` (empty string when blank)
  - New `Gym-Modes` tab: one row per gym with `Gym Name` and per-mode capacity columns (`Basketball Courts`, `Volleyball Courts`, `Badminton Courts`, `Pickleball Courts`, `Soccer Fields`)
  - New `_load_gym_modes()` loader returns `{gym_name: {resource_type: courts_per_block}}`; trailing footer/note rows are ignored
  - If the file or `Gym-Modes` tab is absent, a `WARNING` is logged and `gym_modes` is an empty dict — no crash (same graceful-degradation pattern as `Playoff-Slots`)
  - `schedule_input.json` gains a top-level `gym_modes` object; the Schedule-Input tab gains a `GYM-MODES` section and an `exclusive_group` column in the Resources section
  - 6 new tests covering the `Exclusive Venue Group` reader and the `Gym-Modes` loader
- Refactored `solve-schedule` to decompose by resource-type pool — closes issue #93 comment (pool decomposition requirement from live-run testing)
  - Games are partitioned by `resource_type` and each pool runs an independent CP-SAT solve; a Badminton Court shortage no longer cascades into INFEASIBLE for Gym Courts or Tennis
  - New top-level status `PARTIAL` (some pools solved, some failed); exit code 1 covers PARTIAL/INFEASIBLE/UNKNOWN
  - `schedule_output.json` now includes `pool_results` array with per-pool `{resource_type, status, assignments, unscheduled, diagnostics?}`; diagnostics are attached to the failing pool rather than at the top level
  - `produce-schedule` Schedule-by-Sport tab gains a **Pool Results** section showing per-pool status and shortage summaries when `pool_results` is present
  - 4 new tests covering pool decomposition: `pool_results` always present, partial feasibility, two independent pools both optimal, partial exit code
- Added `python main.py produce-schedule [--input …] [--constraint …] [--output …]` Excel schedule renderer — closes [#94](https://github.com/i12know/vaysf/issues/94)
  - Reads `schedule_output.json` (produced by `solve-schedule`) via `--input` and `schedule_input.json` (produced by `export-church-teams`) via `--constraint`, writes `VAYSF_Schedule_YYYY-MM-DD.xlsx` to `EXPORT_DIR`
  - **Schedule-by-Time** tab: grid view (rows = time slots, columns = courts), color-coded by sport (brown = Basketball, blue = VB Men, pink = VB Women), title row merged, column headers from first session resources, session section headers in grey, blank row between sessions, freeze at A3
  - **Schedule-by-Sport** tab: flat list sorted by event → stage order (Pool < R1 < QF < Semi < Final < 3rd) → round → slot, auto-filter, freeze at A2, unscheduled section in red at bottom when applicable, snapshot note at bottom of both tabs
  - Both tabs carry a snapshot line: `Generated: … | Status: … | Scheduled: N | Unscheduled: N`
  - Implemented via `_build_schedule_output_flat_rows()` and `_write_schedule_output_report()` static methods on `ChurchTeamsExporter`
  - 9 new tests covering flat-row count, field presence, sort order, time extraction, day display, empty input, tab presence, grid content, and unscheduled section
- Added `python main.py solve-schedule [--input …] [--output …]` CP-SAT scheduler — closes [#93](https://github.com/i12know/vaysf/issues/93)
  - Reads `schedule_input.json` (produced by `export-church-teams`), solves a CP-SAT assignment model, writes `schedule_output.json`
  - Implements seven constraints: C1 (each game assigned to one slot/court), C2 (one game per slot/court, multi-slot aware), C3 (no team plays two games in the same slot), C4 (court-type routing — gym games to Gym Courts, racquet games to their matching resource type), C5 (stage ordering — Pool before Semi, Semi before Final via the `precedence` rules in the input), C6 (minimum rest — no team plays in adjacent global time slots), C7 (multi-slot games — duration > slot_minutes blocks consecutive slots)
  - Objective: pack games toward the earliest slots (minimize latest occupied global slot)
  - Exit codes: 0 = OPTIMAL/FEASIBLE, 1 = INFEASIBLE, 2 = error (missing input or ortools not installed)
  - Timeout configurable via `SCHEDULE_SOLVER_TIMEOUT` env var (default 30 s)
  - Import guard: `from ortools.sat.python import cp_model` is inside the function so the module is importable without ortools
  - 15 new tests in `middleware/tests/test_scheduler.py`
- Hardened `schedule_input.json` contract for solver-ready team IDs, pool IDs, and gym resource selection — closes [#96](https://github.com/i12know/vaysf/issues/96)
  - Pool games now carry stable placeholder team IDs (`BBM-P1-T1`, `BBM-P1-T2`, …) instead of `null`; the same ID is reused across all games involving that team so the solver can enforce C3 and C6 constraints in planning mode
  - Gym/team pool planning now uses deterministic templates instead of generic round-robin inference: `2` teams -> direct match, `3` -> RR-3, `4` -> 4-match matrix, `5` -> 5-match cycle, `6+` -> a 3/4-pool composition that keeps every team at exactly 2 pool games
  - Playoff games use explicit seed/winner references (`BBM-Seed-1`, `WIN-BBM-QF-1`, `WIN-BBM-Semi-1`, `LOSE-BBM-Semi-2`) rather than `null`
  - Pool games now emit a non-empty `pool_id` (`"P1"`, `"P2"`, …); playoff/final games emit `""`
  - `schedule_input.json` now includes `gym_court_scenario` (the explicit court count used); controlled by new `SCHEDULE_SOLVER_GYM_COURTS = 4` constant in `config.py` — change the constant to switch between 3/4/5-court scenarios without touching code
  - `_build_schedule_input()` calls `_build_gym_resource_objects(SCHEDULE_SOLVER_GYM_COURTS)` explicitly instead of relying on the invisible `n_courts=4` default
  - New helper `_make_pool_game_pairs()` encapsulates pool generation and team ID assignment
  - 4 new tests; existing structure tests updated
- Normalized Layer 1 team-sport planning around exact two-game pool play
  - Volleyball Women now uses the same 2-game/team baseline as Basketball and Volleyball Men
  - `Venue-Estimator` now shows target vs actual pool games/team, pool composition, and BYE slots so the workbook matches the generated pool policy
  - `docs/SCHEDULING.md` now correctly states that `earliest_slot` / `latest_slot` remain reserved fields and are not currently enforced by the solver
- Added command-level and local pipeline regression coverage for scheduling commands
  - New `tests/test_main.py` covers `parse_args()`, default path resolution in `main.py`, and a local `export-church-teams -> solve-schedule -> produce-schedule` happy path using a repo-local fake export artifact
  - This closes the remaining `#97` testing gaps around CLI wiring (C1) and a deterministic end-to-end scheduling pipeline check (C2)


- Added `--remove-orphans` flag to `python main.py audit-team-groups`
  - After identifying each orphaned Team-group membership (person_id returns 404 from ChMeetings), the membership is deleted from the group via `DELETE /api/v1/groups/{group_id}/memberships/{person_id}`
  - Audit summary line now includes a `Removed: N/M (stuck/API-undeleteable: K)` count when removal is active; "stuck" records are ones where DELETE also returns 404 due to a ChMeetings platform bug (filed as ChMeetings support ticket **#20188** — follow up if stuck count remains non-zero after resolution)
  - Run without the flag first to review `data/team_group_orphan_audit.xlsx`, then re-run with `--remove-orphans` to clean up
  - Combines cleanly with `--church-code` to target a single church: `python main.py audit-team-groups --church-code GAC --remove-orphans`
- Added `Pod-Resource-Estimate` tab to the consolidated ALL Excel export — closes [#86](https://github.com/i12know/vaysf/issues/86)
  - Compares current racquet-sport registration demand against staff-entered venue resources for Tennis, Pickleball, Pickleball 35+, Table Tennis, Table Tennis 35+, and Badminton
  - Required slots use single-elimination formula: `entries − 1` (doubles counted as complete pairs, matching the Venue-Estimator definition)
  - Available slots are read from `middleware/data/venue_input.xlsx` (staff fills this in); multiple pod rows for the same resource type are summed automatically
  - Fit Status color-coded: **Green** (surplus ≥ 0), **Yellow** (short 1–3), **Red** (short 4+)
  - If `venue_input.xlsx` is missing, the tab renders with a `"No venue data"` status and a notice pointing to the template
  - Resource type groupings: Tennis Court (Tennis), Pickleball Court (Pickleball + Pickleball 35+), Table Tennis Table (Table Tennis + Table Tennis 35+), Badminton Court (Badminton)
  - Added `python main.py generate-venue-template` command to create (or regenerate) `SportsFest_2026_Venue_Input_Template.xlsx` with pre-filled example rows and formula column `=D*(((G-F)*60/H)+1)` for Available Slots
  - Starter template committed at `middleware/data/SportsFest_2026_Venue_Input_Template.xlsx`; staff copy it to `venue_input.xlsx`, fill in pod details, and re-run the export
  - `POD_RESOURCE_TYPE_*` and `POD_RESOURCE_EVENT_TYPE` constants added to `config.py`; fit-status colour constants `POD_FIT_COLOR_*` and `POD_FIT_YELLOW_MAX = 3` also configurable there
  - **Excel-only planning artifact** — no data is written to WordPress `sf_schedules`; no OR-Tools scheduling
  - Tab is absent from per-church exports; only appears in the consolidated ALL export
- Added `Court-Schedule-Sketch` tab to the consolidated ALL Excel export — closes [#85](https://github.com/i12know/vaysf/issues/85)
  - Renders three side-by-side court-count scenarios (3, 4, 5 courts) separated by an empty column on a single worksheet
  - Each scenario shows four sessions: 1st Saturday (08:00–20:00), 1st Sunday (13:00–20:00), 2nd Saturday (08:00–20:00), 2nd Sunday (13:00–20:00), matching Sports Fest two-weekend format
  - Pool games fill Weekend 1 sessions first and spill into the start of 2nd Saturday; playoffs start from where pool play ends on 2nd Saturday; finals land in 2nd Sunday
  - Game IDs are sequential placeholders (`BBM01`–`BBMnn` Basketball Men, `VBM01`–`VBMnn` Volleyball Men, `VBW01`–`VBWnn` Volleyball Women) — no actual team assignments or conflict enforcement
  - Games are color-coded: brown (Basketball), blue (Volleyball Men), pink (Volleyball Women)
  - Pool games are interleaved across sports (BBM01, VBM01, VBW01, BBM02, …) to balance court load
  - Inputs summary row now shows target/actual pool games per team, minutes/game, and 3rd-place flag; row 2 shows actual pool-game totals plus pool composition
  - Falls back to 8 teams per sport when fewer than 2 estimating teams exist (planning mode)
  - **Excel-only planning artifact** — no data is written to WordPress `sf_schedules` until the OR-Tools scheduling review step
  - Tab is absent from per-church exports; only appears in the consolidated ALL export alongside `Venue-Estimator`
  - Added `SCHEDULE_SKETCH_*` constants in `config.py` for hours, court counts, and hex colours
- Expanded `Venue-Estimator` tab to cover all Sports Fest events — closes [#83](https://github.com/i12know/vaysf/issues/83)
  - **Team sports** (Basketball, Volleyball Men/Women, Soccer, Bible Challenge): one row per event; a church counts as an "Estimating" team when its roster meets the minimum team size; "Potential" = estimating + partial (all churches with ≥ 1 entry)
  - **Racquet sports** (Badminton, Pickleball, Pickleball 35+, Table Tennis, Table Tennis 35+, Tennis): one row per sport; "Estimating" = complete pairs `floor(doubles / 2)` + singles; "Potential" = all individual registrations including unpaired
  - Added `SPORT_TYPE["SOCCER"] = "Soccer - Coed Exhibition"` and added Soccer to `SPORT_BY_CATEGORY["TEAM"]`
  - Added `COURT_ESTIMATE_RACQUET_EVENTS` list in `config.py`
  - Per-sport minutes constants in `config.py` (`COURT_ESTIMATE_MINUTES_BASKETBALL = 60`, `_VOLLEYBALL = 60`, `_SOCCER = 60`, `_BIBLE_CHALLENGE = 45`, `_BADMINTON = 25`, `_PICKLEBALL = 20`, `_PICKLEBALL_35 = 20`, `_TABLE_TENNIS = 20`, `_TABLE_TENNIS_35 = 20`, `_TENNIS = 30`) — tune these in `config.py` before each season
  - `COURT_ESTIMATE_MINUTES_PER_GAME` lookup dict maps every sport label to its constant
  - `_compute_court_slots` now accepts a `minutes_per_game` parameter; per-sport minutes used automatically
  - Column headers renamed to `Potential Teams/Entries` and `Estimating Teams/Entries` to cover both team and racquet semantics
  - Minimum team sizes are sourced from the `summer_2026.json` validation rules (with `COURT_ESTIMATE_MIN_TEAM_SIZE` as fallback); Soccer=4, Bible Challenge=3 added as fallbacks
  - Tab appears only in the consolidated ALL export; per-church exports omit it
- Fixed case-sensitive bug in `sync/participants.py` that caused team-sport `sport_gender` to always be written as `Mixed` (e.g. `Basketball Mixed Team` instead of `Basketball Men Team`)
  - Comparisons like `GENDER["MEN"] in param.upper()` were checking `"Men" in "MEN TEAM"` and silently failing because `in` is case-sensitive
  - Roster sync now compares case-insensitively in both the full-label branch and a new bare-name lookup branch
  - Added a bare-name fallback that recovers gender/format by looking up the canonical `SPORT_TYPE` entry, so older registrations stored as `"Basketball"` (without the `- Men Team` suffix) heal on the next sync without manual DB edits
  - Format heuristic flipped from "contains Team" to "not contains Singles" so `"Coed Exhibition"` and other non-standard suffixes still map to Team
- Added `Sports Registered` column to the `Contacts-Status` tab in church-team Excel exports — closes [#82](https://github.com/i12know/vaysf/issues/82)
  - Appears immediately before `Athlete Fee`
  - Lists all sports/events for each participant as a comma-separated, sorted string (e.g. `Badminton Women Doubles, Basketball`)
  - Matched by `Participant ID (WP)` with `ChMeetings ID` as fallback; blank when the person has no roster entries
  - Duplicates within the same participant are suppressed
- Added `python main.py inspect-person --chm-id <ID>` for read-only ChMeetings person inspection with WordPress fallback context
  - Prints the raw ChMeetings record when the person still exists
  - Reports cleanly when ChMeetings returns `404 Not Found`
  - Also shows any matching WordPress participant, rosters, approvals, and validation issues for the same `chmeetings_id`
- Added `python main.py audit-team-groups [--church-code ABC]` to audit `Team XXX` memberships for orphaned ChMeetings IDs
  - Flags rows where the Team-group membership still exists but `GET /people/{id}` returns `404`
  - Writes `middleware/data/team_group_orphan_audit.xlsx` with ChMeetings membership details, lookup status, and any matching WordPress participants
- Implemented [#76](https://github.com/i12know/vaysf/issues/76): added `python main.py check-consent --file "...xlsx" [--dry-run] [--church-code ABC]` to auto-check the consent checklist box from a ChMeetings form export
  - Reads the manual consent-form xlsx export, validates the expected column set, and matches rows against synced participants using weighted birthdate/phone/email/name scoring
  - Uses the tuned `33/27/24/16` weighting so `birthdate + phone`, `birthdate + email`, and `phone + email` qualify while `birthdate + name` still stays below the 51% auto-check threshold
  - Auto-checks checklist option `199609` only for matches at or above the 51% threshold, while preserving any other existing checklist boxes already selected in ChMeetings
  - Skips participants whose consent checkbox is already checked, collapses duplicate consent rows per participant by highest score and latest submission date, and writes `middleware/data/consent_check_audit.xlsx`
  - Added mock-test coverage for threshold behavior, guardian-signed rows, duplicate collapse, already-checked skips, dry-run mode, unmatched rows, and API failure handling
- Implemented doubles partner validation for the 2026 ruleset
  - Added `PARTNER_REQUIRED_DOUBLES` to `middleware/validation/summer_2026.json`
  - `IndividualValidator` now raises an `ERROR` when a racquet doubles selection is missing its partner name
  - Added `PARTNER_RECIPROCAL_DOUBLES` as a `TEAM`-level `WARNING` when a doubles partner selection is not reciprocally matched within the same church roster
  - Reciprocal partner warnings now suggest likely full-name matches for short-name entries when there is a unique same-event candidate
  - Church-team Excel exports now enrich `missing_doubles_partner` rows with reverse partner suggestions when one same-event participant uniquely points back to the missing-partner player
  - Reverse partner suggestions in church-team Excel exports now also learn from existing TEAM partner-warning rows, which helps when roster-side partner data is incomplete
  - Participant issue sync now keys individual validation issues by `issue_type + rule_code + sport_type + sport_format`, so distinct partner issues for multiple doubles events are preserved in WordPress
  - TEAM and CHURCH doubles matching now share a deterministic name matcher that safely resolves live formatting variants such as parenthetical aliases, reordered tokens, compact spacing, hyphen/punctuation noise, and unique initial-based abbreviations
  - Partner auto-resolution remains conservative: phonetic algorithms such as `soundex` are not used for quota counting, so uncertain names remain `TEAM` warnings until a unique deterministic match exists
- Added 2026 co-ed soccer TEAM validation rules
  - `Soccer - Coed Exhibition` now requires at least 4 participants per church team
  - `Soccer - Coed Exhibition` now allows 0 non-members
  - Added `MAX_NON_MEMBERS_SINGLES` so non-members cannot participate in racquet singles events
  - Added JSON-driven minimum playable roster rules for Basketball (5), Men's Volleyball (6), Women's Volleyball (6), and Bible Challenge (3)
  - Implemented `ChurchValidator` to enforce CHURCH-level `entry_limit` rules from `middleware/validation/summer_2026.json` for team-sport caps and racquet-event quotas, including disallowed formats such as Badminton singles, Pickleball singles, Tennis men's/women's doubles, and Table Tennis 35+ singles
  - `validate_data()` now syncs CHURCH-level validation issues idempotently alongside TEAM issues
  - Added church-wide roster fetching for validation so CHURCH team-count caps can see explicit `team_order` entries such as Team A / Team B
  - Church-level doubles quotas now count only resolved reciprocal pairs, so one-sided or ambiguous partner claims remain TEAM issues until the pairing is corrected
  - `TeamValidator` now reads sport-specific TEAM non-member limits from `middleware/validation/summer_2026.json`
  - `TeamValidator` now enforces JSON-driven minimum team sizes for team/exhibition events, including `other_events` selections such as soccer

### Bug Fixes
- Fixed consolidated ALL-export workbook generation when `middleware/data/venue_input.xlsx` contains blank or partially filled rows
  - Venue-input parsing now treats blank/`NaN` spreadsheet cells as empty instead of converting them into a literal `"nan"` resource type or crashing on `int(float(NaN))`
  - `Pod-Resource-Estimate`, `Schedule-Input`, and `schedule_input.json` now continue to generate when staff leave trailing blank rows in the venue workbook
  - Added regression coverage for blank venue-resource rows in both `_load_venue_input()` and `_load_venue_input_rows()`
- Fixed stale orphaned participant issues in church-team exports and validation refreshes
  - `export-church-teams` now hides stale `INDIVIDUAL` WordPress validation issues that no longer map to any participant in the current ChMeetings Team-group snapshot
  - `sync --type validation` now self-resolves open `INDIVIDUAL` validation issues when the linked WordPress participant's `chmeetings_id` returns `404 Not Found` from ChMeetings
  - This prevents deleted/re-registered people from showing contradictory state such as receiving a fresh pastor approval email while still appearing on the church workbook's `Validation-Issues` tab under an older orphaned participant record

### Documentation
- Documented the new live-test safety rail requiring `LIVE_MUTATION_TESTS=true` for tests that write to real ChMeetings or WordPress data
  - Added a prominent warning to the README and test docs that `LIVE_TEST=true` points pytest at real systems
  - Updated contributor guidance so future live write tests must call `require_live_mutation_test(...)`
- Added `EXPORT_DIR` to `middleware/.env.template` with the shared Google Drive example used for church-team report exports
- Updated `docs/USAGE.md` and `docs/TROUBLESHOOTING.md` with operator guidance for `inspect-person`, `audit-team-groups`, orphaned Team-group memberships, and shared-drive export configuration

## Version 1.10 (2026-05-12)

### Security Fix
- Patched [#78](https://github.com/i12know/vaysf/issues/78): non-member status flip exploit by a dishonest Church Rep
  - Added `membership_claim_at_approval TINYINT(1) NULL DEFAULT NULL` to `wp_sf_participants`
  - `generate_approvals()` now freezes the membership claim at the moment the pastor approval email is sent
  - `_sync_single_participant()` detects any subsequent ChMeetings flip and reverts `is_church_member` in WordPress to the frozen value on every sync
  - Legacy `approved` / `pending_approval` participants with a NULL frozen field are now backfilled from the existing WordPress membership value on the first protected sync
  - `sync --type approvals --chm-id <CHM_ID>` now stays scoped to the requested participant instead of syncing the full approved cohort
  - CHM write-back: the reverted value is also pushed back to ChMeetings automatically using the verified VAY SM option IDs `Yes=199355` and `No=199356`
  - Warning log line `"Non-member status flip detected"` provides an auditable paper trail; repeated flips for the same rep are evidence of deliberate manipulation
  - Operator correction path: set `membership_claim_at_approval = NULL` via a direct DB update (or future admin endpoint) to unfreeze a participant whose claim was honestly wrong

### Housekeeping
- Cleaned current setup docs to match the API-only architecture
  - Removed obsolete Selenium-era variables from `middleware/.env.template`
  - Updated `docs/PRD.md` to describe the REST API-only middleware path
  - Updated the root `README.md` quick start to use the repo-local `.venv` for installs and pytest

## Version 1.09 (2026-05-02)

### New Features
- Implemented [#70](https://github.com/i12know/vaysf/issues/70): added `python main.py clear-team-groups` to remove seasonal `Team XXX` memberships directly through the ChMeetings API
  - Supports `--dry-run` preview mode and explicit `--execute` live mode
  - Supports `--church-code ABC` for safe single-group testing before a full rollout
  - Writes `middleware/data/team_group_clearing_audit.xlsx` with group, person, and outcome details
  - Treats empty groups as a clean no-op and logs orphaned DELETE `404` rows as `already absent`
  - Added mock-test coverage for dry run, scoped execution, partial failures, empty groups, and orphaned membership cleanup

### Housekeeping
- Completed [#71](https://github.com/i12know/vaysf/issues/71): swept remaining live `2025-07-19` event-date defaults and stale 2025 fallback logic from active middleware/plugin paths and current-season docs
  - Preserved the historical `2025-07-19` reference in `middleware/validation/Summer_2025.json`
  - Updated season-transition and usage docs to document the new team-group clearing workflow and the verified behavior that Group Leaders remain assigned after memberships are cleared
  - Confirmed via local verification that no active plugin, middleware, or current-season doc path still uses the 2025 event date fallback
- Implemented [#72](https://github.com/i12know/vaysf/issues/72): added first-class `Table Tennis 35+` support across middleware config, 2026 validation rules, tests, and current-season docs
  - Verified live ChMeetings dropdown option IDs on 2026-05-02: `330427` for Primary Sport and `330428` for Secondary Sport
  - Added the event to `SPORT_TYPE`, `RACQUET_SPORTS`, `AGE_RESTRICTIONS`, and the ChMeetings option maps in `middleware/config.py`
  - Added `MIN_AGE_TABLE_TENNIS35` and `MAX_AGE_TABLE_TENNIS35` to `middleware/validation/summer_2026.json`
  - Removed the stale rule-scan event-date fallback from `IndividualValidator`; 2026 validation now uses rules metadata first and `Config.SPORTS_FEST_DATE` only as a final fallback
  - Added regression coverage for passing 35+ and failing under-35 `Table Tennis 35+` participants
- Implemented [#73](https://github.com/i12know/vaysf/issues/73): updated WordPress plugin helpers to keep `Table Tennis 35+` in sync with the live 2026 registration form
  - Added `Table Tennis 35+` and `Pickleball 35+` to plugin sport/racquet helper lists where appropriate
  - Updated plugin helper labels to match middleware and ChMeetings exact event names such as `Basketball - Men Team`, `Volleyball - Men Team`, `Track & Field`, and `Tug-of-war`
  - Replaced the stale Pickleball-only age-exception special case with explicit event support for `Scripture Memorization`, `Tug-of-war`, `Pickleball 35+`, and `Table Tennis 35+`
- Added an optional `--file` source filter to `assign-groups` so current-season team assignment can be limited to rows from an Individual Application export while still resolving real ChMeetings person IDs through the API
  - Supports post-reset 2026 operations where older ChMeetings people may still retain stale `Church Team` values outside the current registration batch
  - Verified live on 2026-05-02 with a 3-row export: Sam Le (`3318927`), Thomas Chau (`3631500`), and Timmy Ho (`3139537`) were added to `Team RPC`
  - Verified idempotence on 2026-05-02: rerunning that same 3-row export in `--dry-run` mode immediately afterward found `0` remaining assignments
  - Verified broader current-season backlog detection on 2026-05-02: a dry run against `Individual Application Form (2).xlsx` surfaced 10 remaining assignments after the RPC spot-check, including 2 expected `Team OTHER` skips
  - Verified another live RPC batch on 2026-05-02 with `Individual Application Form (4).xlsx`: 8 additional linked current-season registrants were added to `Team RPC` with HTTP `201` responses for Daniel Kang (`3618011`), Emily Duong (`3615935`), Jacob Le (`3618796`), James Nguyen (`3555636`), Johnny Nguyen (`3318764`), Julianna Faith Ramirez (`3623153`), Khoi Quach (`3319105`), and Serena Mai (`3622254`)
  - Documented two operator gotchas from that live batch: ChMeetings Forms exports can include duplicate submission rows for the same linked person, and a linked form row name can differ from the underlying ChMeetings profile name without indicating a bad match
  - Verified the full same-day current-season batch on 2026-05-02 with `Individual Application Form (5).xlsx`: a dry run found 60 pending assignments across GAC, SDC, LBC, FVC, ORN, GLA, RPC, NHC, and TLC with `0` missing groups; the live run added all 60 with HTTP `201`, and an immediate rerun of the same file returned `0` remaining assignments
  - Hardened full participant sync against orphaned Team-group memberships that still appear in the ChMeetings group-membership API but return `404` on `GET /people/{id}`; those rows are now skipped as `skipped_missing_people` warnings instead of counted as participant-sync errors
  - Verified live on 2026-05-02: the initial full participant sync created 66 participants but surfaced 19 `404` group-member fetch errors; after the middleware change, the rerun completed cleanly with `created=0`, `updated=69`, `errors=0`, and `skipped_missing_people=19`
## Version 1.08 (2026-04-23)

### Bug Fixes
- Fixed [#61](https://github.com/i12know/vaysf/issues/61) (two layers):
  - **Read path:** `get_approvals(synced_to_chmeetings=False)` returned 0 records because the WordPress REST API silently drops unregistered query parameters
    - Plugin: added `args` array to the `/approvals` READABLE route in `plugins/vaysf/includes/rest-api.php` declaring `participant_id`, `church_id`, `approval_status`, and `synced_to_chmeetings` (type boolean) so WordPress sanitizes and forwards them to the callback
    - Middleware: `get_approvals()` in `wordpress/frontend_connector.py` now coerces Python bools to 0/1 before URL-encoding — avoids the `"False"` → PHP `true` string-cast pitfall
    - Added `test_get_approvals_coerces_bool_params` mock test asserting `synced_to_chmeetings=False` serializes as `0` in the outgoing request
  - **Write path:** `update_approval(approval_id, {"synced_to_chmeetings": True})` returned a 2xx with an empty body, causing `response.json()` to throw and the synced flag to never flip (surfaced during live testing on 2026-04-23)
    - Plugin: `update_approval` callback referenced an undefined `$table_participants` variable in its post-update JOIN SELECT, producing malformed SQL. Replaced the expensive and broken JOIN with a minimal `{approval_id, updated, fields}` success payload — callers only need a truthy signal
    - Middleware: `update_approval()` now treats 2xx with empty body as success (hosting stacks like Bluehost + nfd caching occasionally strip PUT bodies), and logs HTTP status + body preview on failure for easier diagnosis
  - Rebuilt `plugins/vaysf.zip`

### Housekeeping
- Closed [#54](https://github.com/i12know/vaysf/issues/54) and [#55](https://github.com/i12know/vaysf/issues/55): Soccer - Coed Exhibition was implemented as an Other Events checkbox (already shipped as option_id 329599 in `SF_OTHER_EVENTS_OPTIONS` in v1.07). The full "Exhibition event type" feature (EXHIBITION category, `event_type` column on `sf_rosters`, separate fees, admin UI distinction) was deferred as YAGNI — current structural shape already gives Soccer the right behavior end-to-end
  - Added a comment in `middleware/validation/team_validator.py` locking in the intent that `("primary_sport", "secondary_sport")` deliberately excludes `other_events` so exhibition entries bypass the non-member team limit
  - Added `test_sync_rosters_soccer_coed_exhibition` regression test pinning the comma-split path

## Version 1.07 (2026-04-23)

### New Features
- Implemented [#53](https://github.com/i12know/vaysf/issues/53): `TeamValidator` — team-composition rules moved from hardcoded Python into `summer_2026.json`
  - New `middleware/validation/team_validator.py`: reads `max_non_members` limits from JSON, validates non-church-member counts per team sport and per doubles pair using `SPORT_BY_CATEGORY` full sport names and `FORMAT_MAPPINGS` for doubles detection
  - New `middleware/validation/summer_2026.json`: all 11 individual rules from `Summer_2025.json` (updated to `SUMMER_2026` collection) plus 3 new TEAM-level rules: `MAX_NON_MEMBERS_TEAM` (2), `MAX_NON_MEMBERS_DOUBLES` (1), `MAX_EVENTS_PER_PARTICIPANT` (2, defined only — form-enforced)
  - Default collection switches globally to `SUMMER_2026` in `IndividualValidator`, `SyncManager`, and `ParticipantSyncer`
  - Removed `get_validation_rules()` from `SyncManager`; `validate_data()` now delegates to `TeamValidator`
  - Fixed pre-existing bug: old `validate_data()` used abbreviated sport names (`"Basketball"`) that never matched real ChMeetings data (`"Basketball - Men Team"`), causing team checks to silently no-op

### Bug Fixes
- Fixed [#65](https://github.com/i12know/vaysf/issues/65): `NameError: name 'pd' is not defined` in `_sync_approvals_via_excel()` — `import pandas as pd` was missing from `sync/manager.py`
- Fixed `sync_approvals_to_chmeetings()` group-not-found path: now returns `False` with a clear error message instead of falling through to the Excel export path
- Fixed `get_member_fields()` in `ChMeetingsConnector` to handle the new API response format `{"status_code":200, "data": {"sections": [...]}}` — fields are now correctly flattened from all sections
- Fixed `get_people()` pagination: termination check changed from `page * page_size >= total` to `len(all_people) >= total`, preventing early exit when the response page_size differs from the requested page_size

### Tests & Infrastructure
- Added 8 new `TeamValidator` unit tests in `tests/test_validation.py` covering team limits, doubles limits, member exclusion, cross-sport isolation, and secondary sport counting
- Fixed 3 live test failures: `test_get_member_fields` (sections format), `test_add_member_note` and `test_update_person` now discover a valid live person ID when the hardcoded test ID is no longer in ChMeetings
- Fixed 3 pre-existing mock test failures caused by Python bound-method calling convention on Linux: `capturing_get` and `fake_put` mock signatures updated to `*args, **kwargs`

## Version 1.06 (2026-04-12)

Replaced Excel export workarounds with direct ChMeetings API calls (Issue #60):
- Rewrote [#60](https://github.com/i12know/vaysf/issues/60): `group_assignment.py` now calls `add_person_to_group()` directly — no more `chm_group_import.xlsx` or manual ChMeetings import step
- Added `--dry-run` flag to `assign-groups` CLI command (previews who would be assigned, writes audit xlsx, zero API calls)
- `church_team_assignments.xlsx` audit file is still written every run (both live and dry-run) as a record
- Rewrote `sync_approvals_to_chmeetings()` in `sync/manager.py` to use `add_person_to_group()` instead of Excel; fails hard if `APPROVED_GROUP_NAME` group not found in ChMeetings
- `synced_to_chmeetings=True` is now set per-person based on API success (not xlsx write success)
- Removed `import pandas as pd` from `sync/manager.py` (no longer used there)
- Added 429 rate-limit retry with 2/5/10 s back-off to `add_person_to_group()` in the ChMeetings connector
- Added preventive 200 ms delay between API calls in both `sync_approvals_to_chmeetings()` and `assign_people_to_church_team_groups()` to stay under the ChMeetings rate limit
- Added `PermissionError` handling when audit xlsx is open in Excel on Windows
- Added 7 new mock tests in `tests/test_group_assignment.py`
- Added 3 new mock tests for `sync_approvals_to_chmeetings()` in `tests/test_sync_manager.py`
- Opened [#61](https://github.com/i12know/vaysf/issues/61): `get_approvals()` `synced_to_chmeetings` filter not working in WordPress REST API

## Version 1.05 (2026-04-11) — 2026 ChMeetings API Upgrade

### Breaking Changes
- Removed Selenium support entirely — the middleware now uses only the ChMeetings API for all operations
- Removed `CHM_USERNAME`, `CHM_PASSWORD`, `CHROME_DRIVER_PATH`, `USE_CHROME_HEADLESS`, and `CHROME_PROFILE_DIR` from configuration
- Removed `selenium` and `webdriver-manager` from dependencies
- `ChMeetingsConnector` no longer accepts `use_selenium` parameter

### New Features
- **API-based approval sync**: `sync --type approvals` now uses the ChMeetings `add_person_to_group()` API to add approved participants directly to their designated group, eliminating the manual Excel import step
- **Excel fallback for approvals**: Pass `--excel-fallback` to `sync --type approvals` to use the legacy Excel export workflow when needed
- **Field mapping constants** (`CHM_FIELDS`): All ChMeetings custom field names are now centralized in `config.py` instead of being hardcoded across the codebase, making it easy to update if ChMeetings labels change
- **API field inspector**: New `test --system chmeetings --test-type api-inspect` command retrieves custom field definitions from ChMeetings and cross-references them against `CHM_FIELDS` to detect mismatches
- **New API methods**: `ChMeetingsConnector` now exposes `get_fields()`, `add_person_to_group(group_id, person_id)`, and `remove_person_from_group(group_id, person_id)`

### Bug Fixes
- Fixed [#57](https://github.com/i12know/vaysf/issues/57): Auth header casing — `ApiKey` → `apikey` for strict gateway compatibility
- Fixed [#56](https://github.com/i12know/vaysf/issues/56): `get_person()` now correctly unwraps the `{"data": {...}}` response envelope
- Fixed [#58](https://github.com/i12know/vaysf/issues/58): `get_people()` pagination now uses `total_count` for robust termination; respects caller's `page_size`; sends `include_additional_fields=True` and `include_family_members=False`

### Tests & Infrastructure
- Added [#59](https://github.com/i12know/vaysf/issues/59): `add_person_to_group()` and `remove_person_from_group()` API methods with live round-trip test gate (`CHM_TEST_GROUP_ID` / `CHM_TEST_PERSON_ID` env vars)
- Added `test_get_people_pagination` and `test_get_people_request_params` tests
- Added `middleware/pytest.ini` to fix `ModuleNotFoundError` when running `pytest` from the `middleware/` directory
- Added `FULL_LIVE_TEST` env var gate to skip the long-running full-sync test in standard `LIVE_TEST=true` mode

### Documentation
- Updated ARCHITECTURE.md, INSTALLATION.md, TROUBLESHOOTING.md, USAGE.md, and README.md to reflect all changes
- Removed all Selenium references from documentation
- Created `docs/CHMEETINGS_API_MIGRATION.md` documenting all API migration changes

## Version 1.04 (2025-07-17)
- Fixed issue [#42](https://github.com/i12know/vaysf/issues/42): Resend approval email now generates fresh tokens with proper expiry dates instead of using expired tokens
- Added: "Is_Member_ChM" and "Photo" columns to Roster tab in church team reports; Photo column displays images using IMAGE() formula (use Excel Ctrl+H to replace "=@IMAGE" with "=IMAGE" if needed)
- Added: "Total Denied" column in Summary tab
- Added: options to mass pastor approval email sending at export rosters time for issue [#47](https://github.com/i12know/vaysf/issues/47)
- Fixed: plugin's admin Sports Fest Date display issue [#48](https://github.com/i12know/vaysf/issues/48)
- Added: Auto Filter to all columns and a note about Photo formula
- FIXED: Male athelete signed up for Women Volleyball now will be Smart Gender Map to the right team in Roster as issue [#50](https://github.com/i12know/vaysf/issues/50)

## Version 1.03 (2025-05-24)
- Fixed issue [#32](https://github.com/i12know/vaysf/issues/32): Not everyone from NHC church show up on Pastoral Approval emails. (pagination fix)
- Fixed issue [#33](https://github.com/i12know/vaysf/issues/33): Non church member show up on Pastoral Approval email as "Yes" for church membership
- Added: Command for "main.py sync --type approvals --chm-id Specific ID" for sync approvals command

## Version 1.02 (2025-05-15)
- Fixed: issue [#23](https://github.com/i12know/vaysf/issues/23) Partner name didn't get recorded on sf_roster table
- Fixed: Enhanced partner name handling in `_create_or_update_roster` to properly update existing entries
- Fixed: Consent-severity calculation and checklist refresh for minors [#12](https://github.com/i12know/vaysf/issues/12), [#9](https://github.com/i12know/vaysf/issues/9)
- Added: Command for "main.py sync --type participants --chm-id 3139537": sync just one participant by ID to debug issues faster
- Added: Command for "main.py export-church-teams": Generate Excel files for Church Rep's review (use arg --church-code ABC for a church)
- Added: Improved debug logging for roster operations and validation issues
- Updated: Documentation to reflect new commands and fixed issues

## Version 1.01
- Fixed: Minor's record didn't show up for Pastoral Approval because ERROR in consent didn't get updated [#12](https://github.com/i12know/vaysf/issues/12)
- Fixed: issue [#4](https://github.com/i12know/vaysf/issues/4) Approved athletes doesn't show approval_status correctly.
- Added: main.py command "assign-groups": Create group assignments for people with church codes

## Version 1.00
*Released: 2025-03-28*

- Consolidated full system architecture into final implementation
- Enhanced validation system with JSON rules and multi-level severity
- Added comprehensive middleware components
- Refined the roster validation process
- Added detailed error handling and recovery mechanisms
- Finalized WordPress plugin structure and REST API endpoints
- Completed middleware implementation with full validation support
- Enhanced documentation with implementation details

## Version 0.9
*Released: 2025-03-26*

- Enhanced validation system with JSON rules for configurability
- Added multi-level validation approach (individual, team, church, tournament)
- Refined validation severity handling (ERROR, WARNING, INFO)
- Improved validation issue tracking and resolution workflow
- Added support for rule-based validation using Pydantic models
- Enhanced error reporting with contextual details

## Version 0.8
*Released: 2025-03-21*

- Added Pydantic framework for improving validation logic & testing
- Enhanced sync_churches and sync_participants with better model validation
- Implemented basic roster reporting functionality
- Improved data mapping between ChMeetings and WordPress
- Added support for rule-based validation
- Enhanced ChMeetingsConnector with more robust error handling

## Version 0.7
*Released: 2025-03-17*

- Added sf_rosters table for tracking team composition
- Enhanced sync_participants to create/update sf_rosters entries
- Added support for team-level validations through roster data
- Implemented participant syncing with sport preferences
- Added detailed ChMeetings usage documentation
- Extended sync_participants to work with the new roster structure

## Version 0.6
*Released: 2025-03-15*

- Added PyTest framework for automated testing
- Implemented mocking convention for isolated connector testing
- Added detailed testing documentation
- Added support for live/mock testing toggle via LIVE_TEST env variable
- Improved error handling in WordPress and ChMeetings connectors
- Enhanced sync error recovery

## Version 0.5
*Released: 2025-03-14*

- Changed architecture to use church_code (3-letter code) as a human-readable identifier
- Maintained church_id as the database primary key for technical efficiency
- Updated API endpoints to use church_code for improved readability
- Clarified the hybrid identifier approach throughout the system
- Updated data mapping to incorporate church_code
- Improved church identification throughout the system

## Version 0.4
*Released: 2025-03-13*

- Moved email notifications from Python middleware to WordPress
- Shifted token generation to WordPress for better process flow
- Added sf_email_log table for tracking communications
- Implemented WP Mail SMTP plugin for reliable email delivery
- Improved approval workflow through WordPress
- Enhanced security of approval process

## Version 0.3
*Released: 2025-03-12*

- Added detailed Windows environment setup instructions
- Included code examples for all major components
- Added comprehensive database schema definitions
- Created a more granular development roadmap
- Added detailed implementation phases
- Enhanced system architecture documentation
- Added Windows-specific considerations

## Version 0.2
*Released: 2025-03-11*

- Simplified the database schema from 11 to 8 tables
- Added detailed data mappings based on actual CSV structure
- Enhanced the approval process workflow
- Refined validation rules based on the Sports Fest Handbook
- Added church and participant data mapping details
- Improved implementation phases and milestones
- Added exact field mappings from ChMeetings to WordPress

## Version 0.1
*Released: 2025-03-10*

- Initial plan with three-tier architecture
- Defined 11 custom WordPress tables
- Outlined core workflows:
  - Registration and approval
  - Data validation
  - Schedule management
- Created initial system architecture
- Defined basic components for ChMeetings, middleware, and WordPress
- Outlined security considerations
- Added future enhancement proposals
