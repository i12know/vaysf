# CHANGELOG

## Unreleased

### Bible Verse editor follow-up and badge route polish (#289, #294)

- Moved `Bible Verses` under the main `Sports Fest` menu for staff who already
  have Sports Fest access, while keeping a standalone entry for coordinator-only
  verse editors.
- Fixed the editor workflow to preserve the selected event filter, default new
  rows to the current filtered event, and redirect after save/delete/import so
  the refreshed row list and success notice appear immediately.
- Added an explicit `Download JSON` action plus a bundled verse-set loader for
  the seeded 2026 Bible Challenge rows.
- Registered a plugin-owned `/badges/` public route and template so the
  churches shortcode's `Participants` buttons resolve without requiring a
  manually created WordPress page.
- Hotfixed the Bible Verse delete/save notice flow to avoid a blank admin page
  after POST actions, and made automatic bundled verse seeding a one-time
  fresh-install helper.
- Bumped plugin header/version to `1.0.46` and rebuilt `plugins/vaysf.zip`.

### Scoped WordPress Bible Verse Editor (#294)

- Added an option-backed WordPress Bible Verse Editor for score-sheet scripture
  rows, stored in `vaysf_bible_verse_sets` instead of a new database table.
- Added `sf2025_manage_bible_verses` and wired it to Sports Fest Admin,
  Manager, Coordinator, and WordPress Administrator roles.
- The editor uses the same published-event authorization model as Coordinator
  Score Entry: admins/managers manage all events, while ordinary coordinators
  are limited to their assigned `vaysf_authorized_events`.
- Supports CRUD for verse rows, plus deactivate and middleware-compatible JSON
  import/export. Deletes are permanent; no revision history is kept.
- Bumped plugin header/version to `1.0.44` and rebuilt `plugins/vaysf.zip`
  for combined server testing. Database version remains `1.0.8` because the
  editor uses an option-backed store and role capabilities, not a schema change.

### Bible Challenge score-sheet verse source (#292)

- Added a reusable score-sheet Bible verse source at
  `middleware/config/bible_verse_sets.json` plus a validating loader for
  event-locked or reusable verse sets.
- Seeded the active 2026 Bible Challenge reference set (`bc_2026`) with the
  14 requested references and locked it to `bible-challenge` so it cannot be
  accidentally used by other sports.
- Bible Challenge score-sheet generation now loads `bc_2026` and replaces the
  old hard-coded prayer verse with a compact reference summary. Full-text
  one-page layout work remains tracked separately in #293.

### Church participants badge links (#289)

- Replaced the public churches shortcode's inactive Registration/Pending text
  with a `Participants` button for each church.
- Buttons link to the badge gallery page with the row's church code, defaulting
  to `/badges/?church_code=ABC`; sites can override the base URL with
  `badges_page_url`.
- Bumped plugin header/version to `1.0.43` and rebuilt `plugins/vaysf.zip`
  for combined server testing of #289 and #290. Database version remains
  `1.0.8`.

### Church badge gallery shortcode (#290)

- Added `[vaysf_badges]` to display approved participant badge PNGs for one
  church code, using either `church_code="ABC"` or the `?church_code=ABC`
  query parameter.
- The shortcode reads approved participants from WordPress and resolves hosted
  badge images from the existing `wp-content/uploads/vaysf/badges` upload
  location using the middleware's deterministic badge filename pattern.
- Bumped plugin header/version to `1.0.42` and rebuilt `plugins/vaysf.zip`
  for server testing. Database version remains `1.0.8`.

### WordPress plugin test build 1.0.41

- Bumped plugin header/version to `1.0.41` and rebuilt `plugins/vaysf.zip`
  for server testing of the consent-ratio PR.
- Database version remains `1.0.8`; this is a packaging/version bump for
  the current plugin code, not a new schema change beyond Issue #183.

### Consent ratio chip for the churches shortcode (#183)

- Added participant `consent_status` storage to the WordPress plugin schema
  and REST participant create/update endpoints, with database migration from
  `1.0.7` to `1.0.8`.
- `[vaysf_churches stats=participants,approval_ratio,consent_ratio]` now
  displays a per-church consent count/percentage using synced participant
  data instead of reading ChMeetings live.
- `check-consent` now mirrors successful consent matches back to the
  WordPress participant row immediately; a later participant sync still
  self-heals the value if that mirror call fails.

### Completed the schedule_workbook.py decomposition (#152, Steps 5-8)

- Extracted the four remaining method groups from `ScheduleWorkbookBuilder`
  into the `middleware/scheduling/` package, one step per commit:
  `pool_assignment.py` (sidecar state, seeding/serpentine draw, tab
  refresh), `game_builder.py` (BC/Soccer/gym/pod game objects, bracket
  math, pool-geometry policy, gym resource expansion),
  `conflict_edges.py` (shared-athlete edge construction), and
  `input_builder.py` (`schedule_input.json` assembly and venue playoff
  slot resolution).
- `schedule_workbook.py` shrinks from 5,051 to 1,971 lines and keeps the
  established facade pattern: staticmethod aliases and thin wrappers
  preserve every method name for `church_teams_export.py`'s `__dict__`
  delegation and for tests.
- Verified no behavior change: all 875 tests pass unchanged, and a
  fixed-fixture guard-rail run (per the issue's suggestion) produced a
  byte-identical normalized `schedule_input.json` and a cell-identical
  planning workbook on `main` vs the refactor, differing only in the
  `generated_at` wall-clock stamp.
### WordPress plugin test build 1.0.40

- Bumped plugin header/version to `1.0.40` and rebuilt `plugins/vaysf.zip`
  for server testing after the REST API and admin PHP refactors.
- Database version remains `1.0.7`; the refactors do not require a schema
  migration.

### Split admin monolith into page-owned modules (#284)

- Refactored `plugins/vaysf/admin/admin.php` (~2,575 lines) into nine
  page modules under `plugins/vaysf/admin/`: dashboard, churches (incl.
  insurance approve/upload), participants, rosters, approvals, validation
  issues, schedules (incl. save/cancel handlers and source-hash helpers),
  results (incl. corrections, revisions, verify/certify), and settings
  (incl. the event-day results reset section).
- Added shared `VAYSF_Admin_Page` base holding the schedule/result status
  vocabularies, `format_game_teams()`, and admin-notice printing so those
  helpers keep one authoritative implementation; `admin.php` is now an
  orchestration-only bootstrap (menu registration + delegation).
- No menu slug, capability, nonce action, POST field name, or rendering
  change — verified by a stubbed-WordPress harness that fired
  `admin_menu`/`admin_init` against old and new code and diffed all 26
  menu/settings registrations (identical).

### Reapproval validation issue lifecycle - refs [#212](https://github.com/i12know/vaysf/issues/212)

- Split approval-invalidating participant changes into identity drift and
  sport/event registration drift so sports changes no longer create
  `approval_identity_drift` validation issues (they now create
  `approval_registration_drift`).
- Kept approval-drift validation reasons open while a participant remains
  `reapproval_required`, and added a diagnostic issue for orphaned
  `reapproval_required` rows that have no open reason.
- Taught `approval-drift-accept` to resolve all three reapproval-reason
  issue types, and the approval-drift log line stays `APPROVAL IDENTITY
  DRIFT` so `approval-drift-history` keeps parsing old and new logs alike.

### Split REST API monolith into domain controllers (#265)

- Refactored `plugins/vaysf/includes/rest-api.php` (~3,130 lines) into nine
  domain controllers under `plugins/vaysf/includes/rest-api/`, each owning
  its own routes: churches (incl. insurance link/upload), participants,
  rosters, approvals (incl. public token processing), validation issues,
  schedules (incl. publish upsert), public spectator display, send-email,
  and sync-log stubs.
- Added shared `VAYSF_REST_Controller` base carrying the `vaysf/v1`
  namespace, API-key verification, and the common permission callback;
  `rest-api.php` is now an orchestration-only bootstrap. The
  `VAYSF_REST_API` class and its `API_NAMESPACE` constant are preserved for
  external callers (`includes/shortcodes.php`).
- No route, method, permission, or response-shape changes — verified by a
  stubbed-WordPress harness that registered both old and new code and
  diffed the full 23-route table (identical).
- Fixed two undefined-variable warnings in `process_approval_token()`:
  `$approval_result` / `$participant_result` debug checks now actually
  capture the `$wpdb->update()` return values they log.

### Bible Challenge score-sheet rosters

- Replaced the blank "Question / Appeal Notes" grid on generated Bible
  Challenge score sheets with three compact roster tables (one per team),
  matching the photo/age/approval-strike-through treatment Basketball,
  Volleyball, and Soccer score sheets already use.
- Added `build_bible_challenge_roster_index()` and wired
  `generate-scoresheets --sport bible-challenge` to the roster/photo
  workbook context it already loads for the other sports, instead of
  discarding `roster_rows`.
- Generalized the soccer-specific compact roster-table renderer
  (renamed `_draw_soccer_roster_table` to `_draw_compact_roster_table`) so
  the same drawing code produces Soccer's two wide columns or Bible
  Challenge's three narrow columns.

### Fixed permanent false approval-identity-drift for self-healed primary/secondary sport

- `_sync_single_participant()` ran the approval identity-drift comparison
  (`_detect_identity_drift`) on the raw ChMeetings-mapped record before
  `_self_heal_missing_primary_sport()` had a chance to promote a populated
  `secondary_sport` into a blank `primary_sport`. Every sync therefore
  compared this run's raw shape against last run's already-healed
  WordPress snapshot, saw a "changed" primary/secondary sport that never
  actually changed, and permanently reset the participant to
  `reapproval_required` — no number of manual `approval-drift-accept` runs
  could make it stick, since the very next sync reintroduced the same
  false drift.
- Moved the self-heal call to run immediately after ChMeetings data is
  mapped, before the drift comparison, so both sides compare the same
  (healed) shape. Confirmed against real 2026-07-16 sync logs and fixed
  for the 3 real participants hitting this exact pattern (chm_id
  3318938, 4387145, 4386750); 2 further `reapproval_required`
  participants that day (chm_id 3618011, 4464026) were genuine one-time
  sport-drop drift, not this bug, and were restored via the normal
  `approval-drift-accept` prior-status inference.
- Added a regression test reproducing the exact bug (raw primary blank /
  secondary populated vs. a self-healed WordPress snapshot) that fails
  without the reorder and passes with it.

### Public church filter fallback - part of [#269](https://github.com/i12know/vaysf/issues/269)

- Fixed the public live-schedule church filter never appearing because
  `vaysf_get_public_schedule_churches()` only read the dedicated
  `team_a_church_code`/`team_b_church_code`/`team_c_church_code` columns,
  which are still `NULL` on the currently published schedule (the
  middleware change that populates them has not been republished yet).
  The dropdown and the `church` filter in `vaysf_get_public_schedule_rows()`
  now fall back to extracting a church code from each slot's team key/label,
  matching the fallback rule `vaysf_schedule_church_signature()` already used
  for result matching.
- Confirmed the separate "Scheduled instead of Reported" report was stale
  test data (a score submitted against a since-reshuffled matchup that no
  longer exists in the current published schedule), not a code defect.

### Results Desk church filter and review-queue accuracy - part of [#269](https://github.com/i12know/vaysf/issues/269)

- Added a Church filter to the Results Desk toolbar, next to the Event filter,
  using the same church-code fallback as the public schedule filter so it
  works even before schedule data is backfilled with `team_*_church_code`.
  Applied to every Results Desk section, the summary counts, and the CSV
  manifest export via a new `vaysf_results_desk_add_church_filter()` helper.
- Moved "Recent Corrections" to display right after "Late / Missing Results".
- Fixed "Needs Review / Disputed" flagging every reported result forever
  (nothing ever set `verified_at`, so a single first-time submission never
  left the queue). A first submission is now accepted immediately; a game
  only lands in this section once an actual correction has come in
  (`current_revision > 1`) or is explicitly flagged `in_progress`/
  `under_review`.
- Coordinator score-entry submissions now automatically append
  " - Submitted by {wp_username}" to the result's Notes field in
  `vaysf_persist_score_result()`, so it's immediately visible who submitted
  a score without checking `submitted_by_user_id`.
- Added a "Results Desk" button to the WordPress user profile screen (own
  profile and admin-edited profiles), right above "Update Profile", for any
  user who passes `vaysf_user_can_view_results_desk()` (Sports Fest Admin or
  Manager, or a plain WordPress administrator).
- Bumped the WordPress plugin to `1.0.39`.

### WordPress-hosted athlete badge uploads - closes [#186](https://github.com/i12know/vaysf/issues/186)

- Added authenticated WordPress REST badge hosting at
  `POST /wp-json/vaysf/v1/badges`, storing generated 1080x1920 PNGs under
  `wp-content/uploads/vaysf/badges/` and returning their public URL.
- Added `DELETE /wp-json/vaysf/v1/badges/{filename}` for cleanup of
  deterministic badge filenames.
- Added middleware `WordPressBadgeUploader` plus
  `python main.py generate-badges --upload` so badge generation can remain
  local-only by default or upload to WordPress when explicitly requested.
- Added opt-in ChMeetings write-back with
  `python main.py generate-badges --upload --write-chmeetings-badge-url`,
  storing the hosted badge URL in the `Sports Fest Badge URL` one-line Text
  custom field rather than writing unsupported profile HTML; closes
  [#261](https://github.com/i12know/vaysf/issues/261).
- Made badge uploads retry once with a re-encoded PNG payload after a
  WordPress/host 403 response, so one problematic compressed image does not
  block the rest of the final badge upload run.
- Bumped the WordPress plugin to `1.0.31`.

### Score-sheet roster approval markings - closes [#258](https://github.com/i12know/vaysf/issues/258)

- Kept rostered athletes visible on Basketball, Volleyball, and Soccer score
  sheets even when they are not currently approved, but marked any
  non-`approved` roster row with a red strike-through and small status label so
  referees and coordinators can see who is not cleared to play.
- Added compact Soccer roster blocks to generated Soccer score sheets so Soccer
  follows the same roster visibility/approval-marking convention as Basketball
  and Volleyball.
- Logged a warning when roster workbook rows do not include approval status
  values, because those rows are intentionally treated as not approved for
  printed score-sheet marking.

### Approval drift acceptance workflow - closes [#252](https://github.com/i12know/vaysf/issues/252)

- Added `approval-drift-history` to audit current `reapproval_required`
  participants against local `APPROVAL IDENTITY DRIFT` sync-log entries,
  including the ChMeetings membership answer for operator review.
- Added `approval-drift-accept` as an explicit operator action for reviewed
  final-week sport/event drift. It updates the WordPress participant row,
  matching approval row, and open drift issue together so the approval trail
  stays consistent.
- Made acceptance restore the single prior approval state from local logs
  instead of always forcing `approved`. `reapproval_required` is ignored as a
  prior-state candidate because it is the problem state being resolved; genuine
  ambiguity still blocks unless the operator passes `--force-approved`.

### Soccer and Bible Challenge score-sheet generators - closes [#254](https://github.com/i12know/vaysf/issues/254), [#255](https://github.com/i12know/vaysf/issues/255)

- Extended `python main.py generate-scoresheets` with `--sport soccer` and
  `--sport bible-challenge`.
- Generated Soccer score sheets from approved schedule artifacts with the VAY
  logo, QR score-entry link, game metadata, final score boxes, referee blanks,
  half/final/shootout score tracker, event log, and signature lines.
- Generated Bible Challenge score sheets for the official three-team matchup
  shape with the VAY logo, QR score-entry link, final score boxes for all three
  teams, moderator/scorekeeper blanks, three referee/church lines, two-round
  score tracker, question/appeal notes, and certification/signature space.
- Added focused tests for the new CLI sport choices, renderers, and PDF
  filtering while preserving the existing Basketball and Volleyball score-sheet
  behavior.

### Public schedule location labels and score-sheet polish

- Joined schedule assignments to `schedule_input.json` resource metadata during
  publish so WordPress schedule rows receive friendly `scheduled_location`
  labels such as `EHS Main Gym - Court 1` and `EHS Library - Station 1`.
- Kept the public schedule from rendering a blank Location cell by falling back
  to `resource_id` when older published rows do not yet have a friendly
  `scheduled_location`.
- Added `python main.py generate-scoresheets --sport volleyball` to create
  print-ready MVB/WVB score sheets with QR links, set-score tracker rows,
  referee/comment/signature blanks, and compact 20-player roster blocks with
  photo/name/age when a roster workbook is supplied.
- Bumped the WordPress plugin to `1.0.30` and rebuilt `plugins/vaysf.zip`.

### Basketball score-sheet generator - closes [#211](https://github.com/i12know/vaysf/issues/211)

- Added `python main.py generate-scoresheets --sport basketball` to create a
  combined print-ready PDF from the approved schedule artifacts.
- Rendered the committed VAY Sports Ministry logo from
  `plugins/vaysf/assets/logo.png` in the upper-left corner of every generated
  basketball score-sheet page.
- Included game ID, schedule/court, final score boxes, referee blanks, opening
  prayer verse, comments/signature lines, and a QR code on each sheet that opens
  the coordinator score-entry page by stable `game_key`.
- Rendered basketball roster tables with up to 15 athletes per team, including
  profile photos from the roster workbook's Excel `IMAGE()` formulas, names,
  ages, writable jersey-number blanks, and five foul-tracking bubbles.
- Enlarged basketball roster rows, photo boxes, and player-name text after the
  first 1.0.29 print review while keeping the one-page, 15-player-per-team
  layout.
- Fixed roster photo recovery when Excel cached `IMAGE()` cells as blank/NaN,
  accepted Excel's `_xludf.IMAGE()` formula shape, and removed the heavy
  separator above referee comments to give the printed roster more room.
- Added WordPress score-entry support for `?action=score&game_key=...` links so
  printed QR codes do not depend on unstable database `schedule_id` values.
- Formatted published schedule slot ids such as `Sat-1-16:00` as visible match
  times on the public schedule and coordinator score-entry pages when
  `scheduled_time` is blank.
- Bumped the WordPress plugin to `1.0.29` and rebuilt `plugins/vaysf.zip`
  together with the protected score-sheet scan upload work.

### Protected score-sheet scan uploads - closes [#205](https://github.com/i12know/vaysf/issues/205)

- Added optional score-sheet scan upload to the coordinator score-entry form.
  Accepted files are PDF, JPEG, and PNG up to 32 MB.
- Stored score-sheet scans under the protected `uploads/vaysf/result-scans/`
  path, recorded SHA-256 hash, MIME type, byte size, original filename,
  uploader, and revision linkage in `sf_result_files`, and marked the result
  `scan_status` as `uploaded` when a scan is attached.
- Kept score submission independent from scan upload: if a scan upload fails,
  the score/revision still saves and the scan can be attached later by editing
  the same match.
- Added protected View/Download links for uploaded scans on the coordinator
  score form and admin result revision screen. WordPress Administrators, Sports
  Fest Admins, and Sports Fest Managers can view all scans; ordinary
  coordinators can view scans only for schedule rows they are authorized to
  submit.
- Bumped plugin header/version to `1.0.29`; database version remains `1.0.6`
  because #203 already created the `sf_result_files` table.

### Public live schedule and advancement display - closes [#206](https://github.com/i12know/vaysf/issues/206)

- Added `includes/public-display.php` with helpers to fetch the currently
  published, non-cancelled schedule (optionally filtered by event/day/venue)
  joined with each game's current result, and to fetch confirmed
  Semifinal/Final advancement placeholders.
- Added public, unauthenticated REST endpoints `GET /public/schedule` and
  `GET /public/advancement`, matching the existing public insurance-link
  pattern (no API key, no login). Both exclude scoresheet file paths,
  coordinator/submitter identities, internal notes, and revision history —
  a reported/official score is reduced to its headline numbers only.
- Added `[vaysf_live_schedule event="" day="" venue="" refresh="25"]` and
  `[vaysf_advancement event="" refresh="60"]` shortcodes. Each renders a
  server-side table on page load (works without JavaScript) plus a small
  polling script that patches status/score cells in place from the public
  REST endpoint every `refresh` seconds; a plain GET filter form lets
  spectators narrow by sport/day/venue without JavaScript.
- "Confirmed advancement" reflects an admin having populated a Semifinal/Final
  schedule row's team slots after deciding pool-play qualifiers — there is no
  separate advancement-confirmation flag in the current schema, so none was
  added.
- Did **not** add a `[vaysf_standings]` shortcode or the RFC's discrepancy
  averaging/red-flag display: neither has real data to work from yet.
  Standings requires per-sport rules configuration and calculation (future
  #207); discrepancy detection requires the submission flow to distinguish a
  second coordinator's independent report from an ordinary correction, which
  `vaysf_persist_score_result()` does not do today (every resubmission
  overwrites the current result as a revision). Both are follow-up work, not
  silently faked here.
- Bumped plugin header/version to `1.0.27`; database version remains `1.0.6`
  because this issue only reads existing tables.

### Score-entry helper extraction - closes [#243](https://github.com/i12know/vaysf/issues/243)

- Split coordinator score-entry and event-day result helpers out of
  `includes/functions.php` into `includes/score-entry.php`.
- Loaded the new module explicitly from `vaysf.php` after the base helper file
  so existing score-entry behavior remains unchanged.
- Rebuilt `plugins/vaysf.zip`; plugin and database versions remain unchanged
  because this is a maintainability-only refactor.

### Volleyball coordinator score entry form - closes [#244](https://github.com/i12know/vaysf/issues/244)

- Added Volleyball Men/Women set-based score entry to the coordinator score
  dashboard.
- Required Set 1 and Set 2 scores for both teams, with an optional tiebreaker
  row. Preliminary/pool matches may be submitted as 1-1 split matches; the form
  includes a strict-rule checkbox for playoff-style matches that require one
  winner.
- Accepted capped scores such as `25-24` and time-capped scores such as
  `21-18` without enforcing a win-by-2 rule.
- Stored volleyball set details in `score_json`, recorded winner keys only for
  decided matches, appended revisions through the existing event-day results
  audit trail, and left standings/advancement manual for this slice.
- Bumped plugin header/version to `1.0.26`; database version remains `1.0.6`
  because #244 writes to the existing event-day results tables.

### Simple coordinator score entry form - closes [#241](https://github.com/i12know/vaysf/issues/241)

- Added coordinator-facing score forms for simple two-team Basketball/Soccer
  style games and three-team Bible Challenge games from
  `/coordinator-score-entry/`.
- Replaced eligible dashboard placeholders with **Enter Score** / **Edit
  Score** links while keeping Volleyball and racquet sport games disabled until
  their sport-specific forms are implemented.
- Enforced login, `sf2025_submit_results`, nonce validation, current published
  schedule version, non-cancelled schedule rows, score-form event support, and
  coordinator event authorization before accepting a score.
- Persisted submissions to `sf_results`, appended every submission/correction to
  `sf_result_revisions`, marked the schedule row `reported`, and captured the
  submitter, timestamp, certification, optional notes, and source metadata.
- Made **Submitted Today** personal for ordinary coordinators but global for
  WordPress Administrators, Sports Fest Admins, and Sports Fest Managers, and
  forced the wp-admin score-entry dashboard widget visible for result-entry
  users so existing dashboard preferences do not hide it.
- Moved the event filter above the dashboard tabs so the selected event governs
  the counts shown in **Needs Results**, **Submitted Today**, and **Assigned
  Games**.
- Bumped plugin header/version to `1.0.25`; database version remains `1.0.6`
  because #241 writes to the existing event-day results tables.

### Coordinator score entry dashboard - closes [#239](https://github.com/i12know/vaysf/issues/239)

- Added a front-end `/coordinator-score-entry/` route and
  `[coordinator_score_entry]` shortcode for the coordinator score entry
  dashboard.
- The dashboard requires login plus `sf2025_submit_results`, then filters the
  latest published, non-cancelled schedule rows by the user's
  `vaysf_authorized_events`.
- Added **Needs Results**, **Submitted Today**, and **Assigned Games** views;
  the initial #239 dashboard kept score entry buttons disabled until #241 added
  the first result-form slice.
- Added an event dropdown below the dashboard tabs so coordinators can filter
  by all assigned events or one assigned event at a time; the filter now applies
  immediately when changed.
- Added a coordinator wp-admin Dashboard widget and Profile-page link so
  event-day users can open the score entry dashboard immediately after login;
  the widget is placed first in the normal Dashboard column.
- Gave WordPress Administrators, Sports Fest Admins, and Sports Fest Managers
  all published score-entry dashboard events without per-event user-meta
  assignments; ordinary coordinators remain limited to their assigned events.
- Replaced confusing `My Matches` wording in the event-day results RFC with
  coordinator-facing `Assigned Games` language.
- Bumped plugin header/version to `1.0.22`; database version remains `1.0.6`
  because #239 adds a read-only front-end dashboard only.

### Schedule-driven coordinator event authorization - closes [#237](https://github.com/i12know/vaysf/issues/237)

- Added user-meta based coordinator event authorization with schedule-derived
  options from the latest published, non-cancelled `sf_schedules.event` values
  instead of a hard-coded plugin sports list.
- Added WordPress user-profile controls so admins can assign one or more
  published schedule events to coordinator, manager, or admin users.
- Added `vaysf_user_can_submit_schedule_result()` so future event-day score
  submission endpoints can require `sf2025_submit_results`, the current
  published schedule version, a non-cancelled game, and matching event
  authorization before accepting a result.
- Documented the source-of-truth split: ChMeetings owns coordinator identity
  and contact data, while WordPress owns event-day login, roles, schedule rows,
  result submissions, and coordinator event authorization.
- Bumped plugin header/version to `1.0.19`; database version remains `1.0.6`
  because #237 stores assignments in WordPress user meta only.

### Event-day coordinator role foundation - closes [#235](https://github.com/i12know/vaysf/issues/235)

- Added a narrow `sf2025_coordinator` WordPress role with `read` and
  `sf2025_submit_results` for event-day score entry, without exposing the
  existing broad Sports Fest wp-admin menus.
- Added `sf2025_submit_results` to Sports Fest admins, managers, and WordPress
  administrators so existing operator accounts keep result-submission access.
- Made role registration upgrade-safe by explicitly adding new capabilities to
  existing roles; `add_role()` alone is a no-op after first activation.
- Documented coordinator account setup and the intentional temporary use of the
  older `sf2025_` capability prefix for the 2026 release.
- Bumped plugin header/version to `1.0.18`; database version remains `1.0.6`
  because #235 adds roles/capabilities only.

### Draft 12 visual schedule override import - closes [#233](https://github.com/i12know/vaysf/issues/233)

- Updated `import-match-schedule-overrides` to understand Excel theme/tint
  fills in Loc's `VAY2026_Main_Schedule_draft_12.xlsx` workbook, so BB/MVB
  cells no longer fail sport detection when the workbook stores colors as
  theme references instead of literal RGB fills.
- Rounded real Excel time values to the nearest minute before building slot
  ids, avoiding false `13:59`/`19:59` resource lookups from near-hour floating
  point time values in the workbook.
- Suppressed intentional control/reservation blocks such as QF/SF labels,
  Scripture Memorization, Bible Challenge finals, and broad playoff blocks
  from the team-code override audit so dry-runs focus on actual matchup rows.
- Updated scheduler documentation and importer defaults to reference
  `VAY2026_Main_Schedule_draft_12.xlsx` as the current official override
  workbook.

### Event-day schedule/results admin screens - closes [#229](https://github.com/i12know/vaysf/issues/229)

- Added wp-admin `Schedules` and `Results` submenu pages for back-office
  inspection and correction of event-day schedule/result data.
- `Schedules` now supports filtered list views plus create/edit/cancel forms
  for `sf_schedules`, with protected-status and cancellation confirmations and
  source-hash recomputation matching the middleware publish diff fields.
- `Results` now supports joined result listing, current-result creation and
  correction, verify/certify actions, and read-only per-result revision
  history. Corrections append a new `sf_result_revisions` row and advance
  `sf_results.current_revision` in a single transaction.
- Bumped plugin header/version to `1.0.17` and rebuilt `plugins/vaysf.zip`;
  database version remains `1.0.6` because #229 adds admin UI only.
- Review fix: the initially-committed `plugins/vaysf.zip` had CRLF line
  endings injected into all nine packaged files (not just the two edited by
  this PR), including inside the `dbDelta()`-parsed `CREATE TABLE` string
  literals in `vaysf.php`. The git-tracked source files were unaffected
  (still pure LF) — this was purely a zip-build artifact. Rebuilt with clean
  LF content, verified byte-for-byte against the tracked source, and
  confirmed `php -l` passes on the extracted copies.
- Review fix: `sanitize_schedule_payload_from_post()` now normalizes a blank
  optional `sf_schedules` field to `null` instead of `''` before
  `compute_schedule_source_hash()` runs, so an admin-edited row with a blank
  `pool_id`/`team_c_key`/etc. hashes identically to how
  `schedule_publisher.py` hashes the same game when that field is simply
  absent from `schedule_input.json`. Verified the PHP and Python hashes now
  match byte-for-byte for an equivalent row. Previously the mismatch would
  make `publish-schedule --dry-run` report every admin-touched row as
  "changed" even when nothing meaningful did.
- Review fix: cancelling a protected (`reported`/`official`/`under_review`)
  schedule row from the Schedules list now shows a distinct confirmation
  naming the row's actual status and a "Cancel (protected)" button label,
  instead of the same generic "Cancel this schedule row?" prompt used for an
  ordinary row.
- Review fix: `save_result_correction_from_post()` now rejects a non-blank
  `score_json`/`winner_keys_json` submission that isn't valid JSON (blank is
  still allowed, matching the nullable column). Verified against valid,
  malformed, plain-text, and literal-`null` JSON inputs.
- Review fix: `sf_results` and `sf_result_revisions` now declare
  `ENGINE=InnoDB` explicitly. The admin correction flow wraps a
  `sf_result_revisions` insert and a `sf_results` update in a single
  `START TRANSACTION`/`COMMIT`, which is only a real atomicity guarantee if
  both tables are transactional; this removes the dependency on the
  server's default storage engine. `dbDelta()` does not diff table-level
  options, so this only affects table creation, not existing installs (moot
  here since the plugin has never been deployed).

### Remove dead Competitions tab and superseded sf_competitions schema - closes [#230](https://github.com/i12know/vaysf/issues/230)

- Removed the wp-admin "Competitions" submenu. Its callback,
  `display_competitions_page`, was never implemented in any commit since the
  menu item was added in the v1.0 RC — clicking it in wp-admin has always
  thrown a fatal `Call to undefined method` error.
- Removed the `sf_competitions` table (`sport_type`/`category`/`format`
  taxonomy) from `create_tables()`. It predates the #203 event-day results
  redesign, was never populated by any code path, and is superseded by the
  `event`/`stage`/`sub_event` columns now carried directly on each
  `sf_schedules` row.
- Removed the unused `sf_schedules.competition_id` column and its index.
  Confirmed via full-repo search that neither `competition_id` nor
  `sf_competitions` is referenced anywhere outside `vaysf.php`'s own schema
  definitions — no REST endpoint, admin page, or middleware code reads or
  writes either.
- Repointed the legacy `game_key` column-position ALTER (used only when
  upgrading a hypothetical pre-#203 install in place) from
  `AFTER competition_id` to `AFTER schedule_id`, since the former column no
  longer exists in the canonical schema.
- Bumped plugin `DB_VERSION` to `1.0.6`. No data migration is included or
  needed — the plugin has never been deployed to a live WordPress install, so
  there is no `sf_competitions` data or `competition_id` value to preserve.
  If a live install is ever found to predate this change, this removal must
  be redone as a real migration instead.

### Approved preliminary games for WordPress score entry - closes [#217](https://github.com/i12know/vaysf/issues/217)

- Added `import-approved-games --dry-run|--execute` to parse the four approved
  2026 preliminary-game workbooks, preserve source workbook/sheet/cell
  provenance, generate stable `game_key` records, and block execution on
  duplicate keys, duplicate resource slots, unresolved resources, or the known
  Table Tennis U35 `SBC` roster/schedule discrepancy unless explicitly waived.
- Wrote `scheduling/approved_games.py` to normalize Main Schedule
  BB/MVB/WVB/BC games, Badminton category matches, Soccer G1-G6, and Table
  Tennis preliminary games into `approved_schedule_games.json`.
- Emit `approved_schedule_input.json` and `approved_schedule_output.json` on
  clean execute so the existing guarded `publish-schedule` command remains the
  only WordPress write path.
- Skip explicit `BYE` rows symmetrically in Soccer, Badminton, and Table
  Tennis imports so byes never become phantom WordPress score-entry games.
  Skipped Badminton and Table Tennis byes are now also recorded in the audit
  `placeholders` list with `classification=bye`, matching Soccer, so a
  dry-run's placeholder count reflects every skipped bye across all three
  sports instead of only Soccer's.
- Added `--input-xlsx` roster context support to `import-approved-games` so the
  Table Tennis source workbook is dry-run checked against the latest
  `Church_Team_Status_ALL` export: source team codes must exist in registered
  Table Tennis roster rows, and named athletes must match the event/category
  they are scheduled for before execution is allowed.
- Added Table Tennis preliminary row-count balance validation so uneven
  category schedules, such as one athlete receiving too few appearances while
  another receives an extra bye row, are reported during dry run.
- Added the final #197 Table Tennis venue/date guard: the approved Table
  Tennis workbook must visibly declare Friday 7/24 in its header, and every
  imported Table Tennis / Table Tennis 35+ game must resolve to a Table
  Tennis resource at Orange before execution is allowed.
- Treat the approved COED Soccer schedule workbook as an operator override
  source when it uses a field slot outside generated venue availability:
  `import-approved-games` now creates an auditable `SOC-APPROVED-*` resource
  for that exact slot instead of blocking execution on an unresolved
  Soccer Field resource.
- Review fix: removed `_validate_table_tennis_friday_orange()`'s per-game day
  comparison. `_parse_table_tennis` always builds every record's
  `scheduled_slot` with the hardcoded required day, so that comparison could
  never actually disagree with it — it read as day-drift protection per game
  but was unreachable dead code. Verified by direct reproduction that the
  workbook-header scan (the other half of the same guard) still catches a
  wrong-day workbook on its own — including a workbook dated a different day
  outright (`Sat 7/25`), not just a Friday-dated header with a contradicting
  weekday label. New regression test locks this in.
- Review fixes to the roster-vs-source validation:
  - `_table_tennis_side_parts()`'s `Name (CODE)` parser now accepts a
    lower/mixed-case church code (e.g. `Nhan Micah (orn)`), not just
    uppercase. It previously fell through to treating the whole
    `"Name (code)"` string as a single athlete label whenever the code
    wasn't already uppercase, which would have raised a spurious
    "not present in the current roster" error for a hand-typed cell.
  - `_format_class()` now delegates to the existing
    `ScheduleWorkbookBuilder._pod_format_class()` instead of re-implementing
    the same "single"/"double" substring check a second time.
- Downgraded unique same-church/same-category Table Tennis athlete name typos
  to dry-run warnings instead of hard errors, preserving an audit trail while
  allowing source sheets like `Justin Pham` vs `Justtin Pham` to proceed.
- Documented the dry-run-first operator workflow and approved-game publication
  path in `docs/SCHEDULE-HOW-TO.md` and `docs/SCHEDULING.md`.

### Visual match schedule team-code overrides (BB/MVB/WVB) - closes [#214](https://github.com/i12know/vaysf/issues/214)

- Added `import-match-schedule-overrides` to parse the visual match schedule
  workbook Loc (the human Sports Fest scheduler) fills in with real team
  codes for Basketball/MVB/WVB pool games, validate them against the roster,
  and write a `match_schedule_overrides.json` sidecar with a required
  `--dry-run`/`--execute` mode pair and full sheet/cell provenance.
- Built a dedicated parser (`scheduling/match_schedule_overrides.py`) rather
  than extending `import-master-schedule`'s: the real workbook uses a
  `TeamCode | "v" | TeamCode` three-cell layout instead of numbered-game
  cells, and its own `LEGEND` row swatches don't reliably match the actual
  game-cell fill colors. Sport is resolved by nearest-color match against
  `schedule_styles.SPORT_STYLES`, the same canonical palette already used to
  render every other schedule export.
- Wired `export-church-teams` / `ScheduleWorkbookBuilder` to merge the
  sidecar into `schedule_input.json`: a team pairing matching an existing
  generated pool game gets its time/court pinned via the existing fixed-slot
  mechanism; a pairing with no existing match is created from the visual
  schedule (logged, with provenance, not applied silently) since Loc's sheet
  is the authoritative source for who plays whom.
- Let team-code match schedule overrides supersede older numbered
  `import-master-schedule` pool pins for the same BB/MVB/WVB visual cells,
  while keeping hard conflicts for every other fixed-slot source.
- Prefixed team labels on match-schedule fixed-slot provenance so
  `schedule_input.json` and `schedule_output.json` stay inside the documented
  contract schema.
- Documented the operator workflow in `docs/SCHEDULE-HOW-TO.md` (Step 4C) and
  `docs/SCHEDULING.md`.

### 2026 scheduling source-of-truth documentation - refs [#215](https://github.com/i12know/vaysf/issues/215)

- Consolidated the 2026 scheduling history from venue estimation through
  human matchups, Master Schedule boundaries, detailed sport workbooks, solver
  output, and WordPress publication.
- Documented the current source hierarchy and precedence rules for live roster
  data, `venue_input.xlsx`, imported matchup sidecars, Master Schedule blocks,
  detailed sport workbooks, `schedule_input.json`, and solver output.
- Added human-scheduler clarifications for BB game 20 as a bye, the WVB O12
  typo, Badminton reserved blocks, Bible Challenge match order/final duration,
  and hard setup/service/ceremony/closure constraints.

### Church export validation issue freshness - refs [#201](https://github.com/i12know/vaysf/issues/201)

- Kept pastor-approved participant status locked during participant sync while
  still recomputing and syncing current validation issues from the live
  ChMeetings profile, so approved minors missing Box 2 consent surface in the
  Church Status `Validation-Issues` tab.
- Verified the hot case with Adam Lien (`chmeetings_id=3623168`): targeted sync
  created a `missing_consent` ERROR for WP participant `199`, and an RPC scratch
  export included that row while preserving `approval_status=approved`.

### Publish-schedule post-merge hardening - refs [#203](https://github.com/i12know/vaysf/issues/203)

- Fixed a `main.py` Python scoping regression from PR #213 that could crash
  later commands such as `check-consent` after adding `publish-schedule`.
- Made `publish-schedule` fail closed when WordPress schedules cannot be read,
  instead of treating a failed read as an empty published schedule.
- Blocked publishing `PARTIAL` or otherwise unscheduled `schedule_output.json`
  by default; added explicit `--allow-partial` for emergency operator-approved
  publishes.
- Made WordPress schedule upsert responses report `success=false` when any row
  is skipped or fails, and hardened the `sf_schedules.game_key` migration for
  legacy rows before adding the unique index.

### Event-day results schema + publish-schedule command - closes [#203](https://github.com/i12know/vaysf/issues/203)

- Redesigned `sf_schedules`/`sf_results` around the string `game_key`
  scheduling model (dropping the old numeric `team_a_id`/`team_b_id` shape,
  which was never used in production) and added `sf_result_revisions`
  (append-only submission/correction history) and `sf_result_files`
  (protected scoresheet attachments), per the event-day results RFC
  (`docs/EVENT_DAY_RESULTS_WORKFLOW_RFC.md` §8). Bumped plugin `DB_VERSION`
  to `1.0.5`.
- Added `GET /schedules`, `GET /schedules/{game_key}`, and
  `POST /schedules/upsert` REST endpoints. Upsert refuses to touch any row
  whose current status is `reported`/`official`/`under_review`, and refuses
  cancellations unless the request is marked `force_cancel`, independent of
  the middleware-side diff.
- Added `python main.py publish-schedule --dry-run|--execute [--force-cancel]`:
  merges `schedule_output.json` assignments against `schedule_input.json`
  game metadata, diffs against the currently published WordPress schedule by
  a per-game content hash, and upserts only new/changed future games.
  Completed matches are never overwritten; games missing from a republish are
  only ever marked cancelled (never deleted), and only with
  `--force-cancel --execute`. Writes a JSON audit summary of the diff.
- Defined the `MATCH:<game_key>` QR payload prefix (`config.QR_PAYLOAD_PREFIX`)
  for the event-day match-QR scoresheets that Issue #211 will generate. Badge
  QR codes remain an unprefixed ChMeetings ID for now (see #77) — adopting the
  matching `CHM:` prefix so scanners can tell person and match QRs apart is
  left for a follow-up issue coordinated with the badge pipeline (#184-#188),
  not done here.
- Per RFC §9.5, Track & Field and Tug-of-War need no special schema handling:
  each event is an ordinary `sf_schedules` row with its own `TF-`/`TOW-`
  `game_key`, entered via `publish-schedule` as a fixed-time entry rather than
  solver output — `Issue 7` in the RFC's implementation plan.

### Badge consent warning - refs [#199](https://github.com/i12know/vaysf/issues/199)

- Turned missing ChMeetings Profile Box 2 consent into a red athlete-name card
  on generated badges while keeping the athlete name in white for readability.
- Added small black QR-card tags for `Minor` and `Consent Form Needed`, with
  minor status calculated from the live ChMeetings birth date using the same
  event-date age calculation as the church export.
- Backfilled badge `consent_status` from the live ChMeetings Completion Check
  List, plus event-day age and minor status from the live birth date, when
  fetching the athlete person record.
- Added regression coverage for the red consent warning, white name text, and
  ChMeetings checklist and minor-status interpretation.

### Badge production template dark-mode pass - refs [#185](https://github.com/i12know/vaysf/issues/185)

- Updated the athlete badge renderer so the new dark-blue production
  `badge_template.png` owns the upper event artwork/title area instead of being
  covered by generated placeholder panels.
- Restyled generated lower-badge content for dark mode: light/gold church code
  and labels, dark event cards, gold outlines, and a white QR card retained for
  scanner contrast.
- Bolded the lower-card athlete/event text for readability on the dark cards.
- Removed the QR caption text after mobile scan review confirmed the QR exposes
  the expected ChMeetings ID payload.
- Default badge output now writes to `EXPORT_DIR/<church-code>/badges/`
  (for example the church-specific Google Drive export folder), while
  `--output` remains a direct flat-folder override for scratch review renders.
- Limited partner-name display to racquet sports so team-sport rows do not
  inherit stale doubles partner fields.
- Bumped the badge render fingerprint and added regression coverage so template
  artwork is not overpainted and event cards remain dark-mode surfaces.

### 2026 main schedule workbook override import - closes [#196](https://github.com/i12know/vaysf/issues/196)

- Added `import-master-schedule` to parse the visual
  `VAY2026_Main_Schedule_draft_4.xlsx` master allocation workbook into a
  `manual_schedule_overrides.json` sidecar, mapping numbered BB/MVB/WVB gym
  games and BC three-team rows back to generated/manual game IDs.
- Wired `export-church-teams` / `ScheduleWorkbookBuilder` to merge confidently
  resolved master-schedule rows into `schedule_input.json["playoff_slots"]`
  via the existing fixed-slot scheduler path, without replacing roster or
  matchup import data.
- Rows the importer cannot confidently map (unknown game IDs, missing
  resources, unresolved slots) are preserved as comparison diagnostics
  instead of guessed, and surfaced with source-cell/source-raw columns on the
  Schedule-Input `PLAYOFF-SLOTS` echo.
- Documented the operator workflow in `docs/SCHEDULE-HOW-TO.md` and
  `docs/SCHEDULING.md`.

### Tennis doubles rule update - refs [#194](https://github.com/i12know/vaysf/issues/194)

- Updated the Summer 2026 validation rules so Tennis allows `Men Double`,
  `Women Double`, and `Mixed Double` registrations while enforcing a combined
  maximum of two resolved Tennis doubles teams per church across all doubles
  genders.
- Replaced the old regression test that disallowed men's Tennis doubles with
  coverage for two total Tennis doubles teams being allowed and a third team
  triggering `MAX_CHURCH_TENNIS_DOUBLES_TOTAL`.

### 2026 manual team-sport matchup import - refs [#190](https://github.com/i12know/vaysf/issues/190), [#191](https://github.com/i12know/vaysf/issues/191)

- Added `import-team-matchups` for the 2026 all-team-sports matchup workbook,
  writing `manual_team_matchups.json` for schedule generation.
- Manual BB/MVB/WVB/SOC/BC pool-game matchups now replace generated team-sport
  pairings, with BC imported as three-team Jeopardy-style `BC-RR-*` games and
  Soccer accepting the exported `Mixed`/`Coed` roster shape.
- Added the all-team-sports workbook template, documented the operator workflow,
  and kept pool maps optional when the manual matchup list has complete slot
  and team-code values.

### Public church shortcode stats

- Added optional per-church statistics to `[vaysf_churches]`, showing
  WordPress participant totals and approval ratios beneath each church name by
  default. The shortcode now supports `show_stats="no"` and a flexible
  `stats="participants,approval_ratio"` list for future church-level metrics.

### Nightly middleware run robustness

- Made console logging UTF-8 tolerant so names with diacritics do not break
  Windows console or scheduled-task runs.
- Hardened the ChMeetings form export helper against promotional overlays that
  can block Export/Download clicks during `daily-run.bat`.
- Suppressed `tqdm` progress bars when middleware sync runs are non-interactive,
  keeping nightly logs readable while preserving interactive progress output.
- Ignored generated form-repair workbooks and a local-only late-racquet override
  filename for operator data that should not be published.

### Admin insurance PDF upload - refs [#180](https://github.com/i12know/vaysf/issues/180)

- Added an admin-only PDF upload form to the Sports Fest Churches screen so staff
  can attach a church's proof of insurance when the church rep cannot complete
  the public upload flow.
- Shared the public and admin upload paths through one validation/storage helper
  for the 10 MB PDF limit, MIME/extension/magic-byte checks, uploads directory
  storage, status update, token cleanup, and optional notification emails.
- Admin uploads preserve an already approved insurance status; otherwise the
  church moves to Submitted so the existing approval button remains the review
  step.

### ChMeetings profile photo upload — refs [#175](https://github.com/i12know/vaysf/issues/175)

- Added a `ChMeetingsConnector.upload_person_photo()` wrapper for the new
  `POST /api/v1/people/{person_id}/photo` multipart endpoint announced by
  ChMeetings Developer Support on 2026-07-07. This keeps `photo` out of normal
  People create/update payloads while giving the missing-person repair workflow
  an API path to attach athlete headshots after creating a Person record.
- Added an operator-gated `upload-person-photo --chm-id ... --photo-file ...`
  command with documented `file` multipart-field handling, 2 MB local image
  validation, dry-run support, and post-upload People re-read confirmation for
  the first safe live mutation test.
- Extended `upload-person-photo` with `--photo-url` for ChMeetings-hosted form
  photo URLs, so an operator can promote a form-submission headshot into the
  linked People profile without a manual download step.

### Decompose schedule_workbook.py — Step 4: planning_tabs.py — refs [#152](https://github.com/i12know/vaysf/issues/152)

Extraction-only refactor (Step 4 of 8): no behavior changes, all call sites
and the `church_teams_export.py` method-copy loop keep working unchanged.

- **`scheduling/planning_tabs.py`** (new) — the offline planning-workbook tab
  renderers: `_write_summary_tab`, `_write_schedule_input_tab`,
  `_write_gym_allocation_tab`, `_write_court_schedule_sketch` +
  `_build_scenario_schedule`, `_write_pod_resource_estimate` +
  `_build_pod_resource_rows`, and the per-tab `_annotate_*` helpers
  (Venue-Estimator, Pod-Divisions, Pod-Entries-Review, Pool-Assignment).
- Because several of these renderers call **outward** into methods that stay
  in the class (`_compute_court_slots`, `_count_racquet_entries`,
  `_make_playoff_ids`, …), the nine builder-dependent functions take the
  `ScheduleWorkbookBuilder` as a `builder` first parameter and reach class
  state/methods through it. The class keeps thin wrappers preserving each
  method's original `@classmethod`/instance binding; the two pure functions
  (`_write_summary_tab`, `_build_scenario_schedule`) use `staticmethod()`
  aliases like Steps 1–3.
- `schedule_workbook.py`: 5,714 → 4,770 lines (−944). Eleven now-orphaned
  imports removed (`deque`, `SCHEDULE_SKETCH_N_COURTS`, the
  `SCHEDULE_SKETCH_COLOR_*` set, the `POD_FIT_*` set).
- All 11 extracted bodies verified AST-identical to the originals (docstring
  reindentation to module level aside); 634 tests pass.

### Generate athlete photo-ID badges — refs [#77](https://github.com/i12know/vaysf/issues/77)

v1 scope: visual identity verification, local render only. Adds a
`generate-badges` command that renders a 1080×1920 PNG credential per approved
athlete (photo, name, church, sport(s), athlete ID, QR slot).

- **`middleware/badges/generator.py`** — `BadgeGenerator`: Pillow rendering with
  name auto-shrink, multiline church wrap, hide-empty event rows, circular photo
  crop with an initials-on-colour fallback, and a deterministic
  `{church}_{chmid}_{8hex}.png` filename. Vietnamese diacritics preserved.
- **`middleware/badges/runner.py`** — `BadgeRunner`: fetches approved
  participants from WordPress (re-checked client-side), resolves the photo from
  the ChMeetings person record (fallback to WordPress `photo_url`), and drives
  the generator. Supports `--church-code`, `--chm-id`, `--dry-run`, `--force`.
- **`middleware/templates/build_placeholder.py`** + committed
  `templates/badge_template.png` — placeholder background until a designer
  delivers the real template.
- Added Pillow and qrcode to `requirements.txt`; `data/badges/` is gitignored.
- QR carries the ChMeetings person ID payload; WordPress hosting and
  ChMeetings `<img>` write-back are deferred follow-ups.
- Documented in `docs/USAGE.md`; unit tests in `tests/test_badges.py`.
- **Current real-world eligibility status:** badges intentionally use pastor
  approval only. Payment status is not currently reliable enough to filter
  athletes, so an approved athlete is rendered regardless of the stored
  payment flag.
- Review hardening: use Vietnamese-capable Windows/Linux system fonts instead
  of Pillow's missing-glyph fallback; skip records without `chmeetings_id`;
  refresh stale PNGs using content/resource fingerprints; and require a private
  `BADGE_FILENAME_SALT`.
- Wireframe correction: keep all content inside the 80/80/120/180 safe area;
  place the church code directly beneath the photo; keep the logo fully inside
  the theme panel; and use the wireframe's divider-and-label event rows instead
  of colored pills.
- Photo resolution now tries a valid ChMeetings image first, then retries with
  the WordPress `photo_url` when the ChMeetings request or image decode fails,
  then uses initials. Logs record only source, result, ChMeetings ID, and error
  type; private profile-photo URLs are not logged.

### Issue #165 follow-up review fixes

- Fail safely when seasonal ChMeetings participant-role configuration is
  missing or invalid: validation keeps the unfiltered WordPress population
  instead of treating every athlete as ineligible.
- Use deduplicated singles membership consistently for pod division counts and
  bracket generation, preventing duplicate roster rows from creating phantom
  entrants or `None` Round-1 opponents.
- Merge game, playoff-slot, and assignment metadata in post-solve quality
  diagnostics so manual-only pinned playoff games retain their event and
  duration in actionable warnings.

### Decompose schedule_workbook.py into scheduling/ package — refs [#152](https://github.com/i12know/vaysf/issues/152)

Extraction-only refactor (Steps 1–3 of 8): no behavior changes, all imports
and call sites unchanged. The three new modules live under
`middleware/scheduling/` and are imported by `schedule_workbook.py` via
backward-compat `staticmethod()` class aliases.

- **`scheduling/xlsx_utils.py`** — 16 pure static helpers: `_clean_excel_text`,
  `_float_from_excel`, `_normalize_resource_type_name`, `_resource_id_prefix`,
  `_ordinal`, `_day_sort_key`, `_day_display_label`, `_coerce_excel_date`,
  `_derive_day_labels_from_dates`, `_set_excel_comment`,
  `_make_excel_note_shapes_visible`, `_stamp_tab_status_banner`,
  `_annotate_header_row`, `_parse_hour`, `_read_xlsx_sheet_rows`, plus the
  `_TAB_STATUS_GUIDE` dict and `_stamp_known_tab_statuses` function (moved here
  to avoid circular imports from `output_report`).
- **`scheduling/venue_loader.py`** — 7 venue-loading functions:
  `_load_venue_input_rows`, `_load_playoff_slots`, `_load_venue_date_day_map`,
  `_split_slot_label`, `_last_slot_label_on_day`, `_load_gym_modes`,
  `_load_venue_input`.
- **`scheduling/output_report.py`** — 4 output-report writers:
  `_warn_if_schedules_mismatched`, `_build_schedule_output_flat_rows`,
  `_write_schedule_diagnostics_tab`, `_write_schedule_output_report`.
- **`schedule_workbook.py`** reduced from 7,703 → 5,706 lines (−1,997);
  exposes all 27 symbols as `staticmethod()` class aliases for full
  backward compatibility.
- 629 tests pass unchanged.

### Participant-level singles conflict protection — closes [#164](https://github.com/i12know/vaysf/issues/164)

Extends #158's Round-1 conflict protection from racquet doubles to racquet
**singles** entries. Singles membership is always known (one participant per
entry, no partner declaration to fail), so every singles player now gets a
stable entry ID and shared-athlete conflict edges.

- **`_resolve_pod_singles()`** (`schedule_workbook.py`) — assigns each singles
  roster row a stable, reproducible entry ID of the form
  `{division_id}-S{nn}` (e.g. `BAD-Men-Singles-S01`), parallel to the doubles
  `-E{nn}` model. Entries sort by participant ID before numbering; duplicate
  roster rows for the same player in one division collapse.
- **`_build_pod_game_objects()`** — singles divisions now use the same
  bye-aware bracket math as doubles to attach entry IDs to **Round-1** games.
  Bye entries and post-R1 rounds keep `team_a_id`/`team_b_id` of `null`
  (bracket-unknown limitation, same as doubles).
- **`_build_cross_sport_conflicts()`** — singles entries join the racquet
  unit list, so the existing pairwise loops emit **team↔singles**,
  **doubles↔singles**, and **singles↔singles** edges automatically — including
  same-sport overlap (one player in Badminton singles *and* doubles).
- **No solver or audit changes** — edges use the identical dict shape and
  reference entry IDs that now appear as game team IDs, so in-pool overlap
  penalties, C3x cross-pool avoidance, and Conflict-Audit attribution all act
  on singles edges through the existing machinery.
- `docs/SCHEDULING.md` — new "Singles conflict protection (Issue #164,
  shipped)" section documenting the protection and its R1-only limits.
- 6 new tests: R1 entry-ID assignment (N=4), bye entry unprotected (N=3),
  team↔singles edge with Basketball, three-event participant (3 edges incl.
  singles↔singles), same-sport singles+doubles edge, resolver determinism +
  dedupe.
- Identified in the 2026 pre-season scheduling review (#165). Scope narrowed
  per issue review: protection covers known Round-1 participation only — no
  claims about post-R1 rounds.

### Move qualifying_roles into validation rules JSON — closes [#163](https://github.com/i12know/vaysf/issues/163)

Eliminates the last hardcoded ChMeetings role-string set in business logic.
Previously `qualifying_roles = {"athlete", "participant", "athlete/participant"}` was
a literal constant in `sync/manager.py`; an unknown role would silently exclude the
participant with no log entry.

- **`validation/summer_2026.json`** — new `configuration.participant_roles` section:
  ```json
  "qualifying":      ["Athlete", "Participant", "Athlete/Participant"],
  "known_excluded":  ["VAY SM Staff", "Fan and Supporter"]
  ```
- **`RulesManager`** (`validation/models.py`) — new `qualifying_roles` and
  `known_excluded_roles` properties return case-folded `frozenset`s from the
  `configuration` section. `_load_configuration()` reads the config key alongside
  rules; an empty or missing key yields empty sets without crashing.
- **`_is_eligible_by_role()`** (`sync/manager.py`) — new module-level helper
  replaces the inline comprehension. Logs a WARNING (with ChMeetings ID, no PII
  such as names) for any nonblank role that is neither qualifying nor
  known_excluded, so new ChMeetings role values surface in logs rather than
  causing silent exclusions.
- **`_load_current_eligible_chm_ids()`** — calls `_is_eligible_by_role()` via
  a `RulesManager(collection="SUMMER_2026")` instance; no behavior change for
  the three existing role values.
- 13 new tests across `test_validation.py` (RulesManager properties, empty
  config, disjoint check) and `test_sync_manager.py` (all five suggested cases:
  qualifying values, known-excluded silent skip, novel role warning,
  comma-separated list, blank roles).

### Post-solve quality audit — closes [#153](https://github.com/i12know/vaysf/issues/153)

Adds a `quality_warnings` section to `build_schedule_diagnostics()` (and the
`Schedule-Diagnostics` workbook tab) that runs after a feasible solve to flag
schedules that technically fit but may be unreasonable to publish.

Three checks are implemented, each separate from hard infeasibility findings:

- **Late finish** (`late_finish`): flags any event+day where the last game ends
  after 20:00. Reports the finish time and game ID so operators can widen the
  resource window or reduce games on that day. Severity: medium.
- **Tight stage turnaround** (`tight_turnaround`): for each QF→Semi, Semi→Final,
  or Semi→3rd precedence edge, flags when the actual gap between end of the
  prior round and start of the next is under 30 minutes. Suggests adding a
  Playoff-Slots buffer. Severity: medium.
- **Volleyball net-height switches** (`volleyball_switches`): surfaces the
  `volleyball_adjacent_switches` count already computed by the solver. Medium
  when > 4 switches; info when 1–4. Suggests pool assignment changes.

Behaviour:
- Quality checks are skipped for INFEASIBLE/UNKNOWN schedules (nothing to assess).
- Medium-severity quality warnings propagate into `next_actions` as
  `vector: "quality"` suggestions so operators see them in the CLI output.
- `format_schedule_diagnostics()` logs a `Quality [severity/check]` line per
  warning.
- The `Schedule-Diagnostics` workbook tab renders a "Quality Warnings" section
  with severity, check name, event, day, and actionable message.
- 10 new tests in `test_schedule_diagnostics.py` cover all three checks plus
  edge cases (clean schedule, infeasible schedule, propagation to next_actions,
  format output).

### Event-critical test coverage — closes [#162](https://github.com/i12know/vaysf/issues/162)

Adds the two remaining coverage gaps identified in the 2026 pre-season
scheduling review (#165, P0c).

- **Solver timeout** — focused tests monkeypatch `_solve_one_pool` to return
  `STATUS_UNKNOWN`, verifying both all-timeout and mixed solved/timed-out runs.
  A mixed run preserves completed assignments under `PARTIAL` while returning
  exit code 2 so automation can distinguish timeout from infeasibility.
- **Vietnamese diacritics** — `test_main_produce_schedule_preserves_vietnamese_diacritics`
  reads UTF-8 `schedule_input.json` and `schedule_output.json` through the real
  `produce-schedule` command and verifies team and participant names in
  Schedule-by-Time, Schedule-by-Sport, and Conflict-Audit.

Coverage status after this change:

| # | Failure path | Covered by |
|---|---|---|
| 1 | Solver timeout | `test_run_solve_schedule_timeout_writes_unknown` ✓ |
| 2 | Malformed input | `test_run_solve_schedule_contract_violation_exits_3` + schedule-contract tests ✓ |
| 3 | Duplicate/invalid playoff reservations | duplicate, overlap, capacity, unknown-resource, and invalid-slot tests ✓ |
| 4 | Vietnamese diacritics survive | real `produce-schedule` JSON-to-workbook test across named tabs ✓ |
| 5 | Solver determinism | `test_solver_uses_fixed_random_seed` ✓ |

### Stage-aware racquet late-round game IDs — closes [#130](https://github.com/i12know/vaysf/issues/130)

Racquet sport (TT, TT 35+, Pickleball, Pickleball 35+, Tennis, Badminton)
bracket games now receive stable stage-aware IDs, enabling operators to pin
late rounds via `Playoff-Slots` the same way team-sport finals are pinned.

- **Bracket-aware game generation** — `_build_pod_game_objects()` replaces
  the flat sequential `R1` loop with a round-by-round bracket. Late-round
  games receive named IDs: `-QF-1..N` (bracket size ≥ 8), `-Semi-1`,
  `-Semi-2`, `-Final`. Early rounds keep sequential numeric IDs (`-01`,
  `-02`, …) for very large brackets.
- **Precedence** — per-division precedence edges enforce round ordering
  (every game in round R must complete before round R+1 starts,
  `min_gap_slots=1`). These edges are included in `schedule_input.json`
  alongside the existing Soccer and Basketball precedence chains.
- **Duration-aware precedence** — the solver now combines the declared slot
  gap with each prior game's real duration, so a 60-minute Tennis match on a
  30-minute grid cannot be followed by the next round after only 30 minutes.
- **Third place** — racquet brackets with two played Semis emit stable
  `<division_id>-3rd` games when third-place scheduling is enabled, with both
  Semis preceding the Final and third-place game.
- **Large-bracket report order** — numeric early stages (`R1`, `R2`, ...)
  sort chronologically before QF/Semi/Final in Schedule-by-Sport.
- **Return type** — `_build_pod_game_objects()` now returns
  `(games, precedence)` and the caller `_build_schedule_input()` extends the
  top-level precedence list accordingly.
- **Doubles assignment preserved** — bracket round-1 matchups for confirmed
  doubles pairs carry real entry IDs as before; bye-aware math is unchanged.
- Five new unit tests: TT bracket structures (P=8 with N=6 and N=8),
  Pickleball P=4 bracket, precedence inclusion in `schedule_input.json`, and
  an end-to-end Playoff-Slots pin of a `TT-Men-Singles-Final` game.
- Identified in the 2026 pre-season scheduling review (#165, P0b).

### Venue-centric Playoff-Slots — pin finals by gym + date + time — closes [#127](https://github.com/i12know/vaysf/issues/127)

Operators can now pin playoff games without knowing internal allocator
resource IDs. A `Playoff-Slots` row may specify `gym_name` + `date` +
`start_time` (preferred) instead of `resource_id` + `slot`; the explicit form
remains valid as an override and for legacy files.

- **Two-pass reservation** — venue-centric rows are resolved against
  `Venue-Input` *before* the Stage-A gym allocator runs. For
  allocator-managed gyms, a dedicated playoff-pinned resource (e.g.
  `BB-Sun-2-PF1`) is synthesized covering only the pinned window, and that
  window is carved out of the allocator inventory (`gym_allocator.allocate()`
  gains a `reserved_windows` parameter) — pool play can never consume a
  pinned Final's court time, with any non-overlapping remainder of the block
  still allocatable. This is the allocator "reserve" concept #133 needs.
- **Standalone venues** — venue-centric rows resolve to the existing expanded
  resource IDs (e.g. `TT-Sun-2-1`); concurrent pins land on distinct courts
  and the exact `(resource, slot)` pairs are reserved from pool play at solve
  time as before.
- **Contiguous pins merge** — Semi at 14:00 + Final at 15:00 on the same
  gym/sport share one synthetic playoff court, mirroring the legacy
  same-`resource_id` merge behavior.
- **Fail loudly, not deep** — invalid venue-centric rows abort schedule-input
  generation with all detected errors instead of silently omitting playoff
  intent. Validation covers unknown gym/date/start values, mutually-exclusive
  gym-mode overlap, configured court-count overflow, and overlapping
  multi-slot reservations.
- **Duration-aware reservations** — generated game duration is used when a
  playoff row omits `duration_minutes`, and every occupied resource slot is
  reserved and collision-checked rather than only the start slot.
- **Schema** — resolved rows keep `gym_name`/`date`/`start_time` for
  traceability; the schedule contract models the new fields on both playoff
  slots and merged output assignments. The venue input template's
  `Playoff-Slots` tab gained the new columns.
- **Pinned gym resources now join the Gym Core solver pool.** Previously a
  synthetic playoff-pinned BB/VB resource carried no `solver_pool`, so a
  pinned Semi/Final (whose pool derives from its pinned resource) landed in a
  different pool than its pool-play siblings — the auto-generated
  QF→Semi→Final precedence rules became cross-pool, which the solver silently
  dropped and the #161 contract rejected with exit 3. Pinned BB/VB resources
  (venue-centric and legacy promotion alike) now take `solver_pool: Gym
  Core`, keeping precedence enforceable; pool play still cannot use them
  because their windows contain only reserved slots. Covered by an
  end-to-end test (build → contract → solve) of the full pinned-finals
  scenario.
- Identified in the 2026 pre-season scheduling review (#165, P0b).

### Fail-fast contract validation for scheduling JSON files — closes [#161](https://github.com/i12know/vaysf/issues/161)

The scheduling bridge files now have a Pydantic contract, so malformed or
hand-edit-damaged input fails at load time with field-level messages instead
of a mid-solve traceback or a silently wrong schedule.

- **New `middleware/schedule_contracts.py`** — `validate_schedule_input()` /
  `validate_schedule_output()` check `schedule_input.json` and
  `schedule_output.json` against Pydantic models covering the full documented
  schema (docs/SCHEDULING.md). Validation is read-only — valid inputs solve
  without changing assignment/status semantics (proven by a behavioral
  equivalence test comparing assignments, status, and unscheduled lists with
  and without validation). All violations are collected into one
  `ScheduleContractError`, each message carrying the offending
  `game_id`/`resource_id`.
- **Strict numerics** — numeric strings (`"60"`) and booleans are rejected on
  every modeled numeric field, never coerced. Clock fields must be real times
  (`HH:MM`, hours < 24, minutes < 60) with `close_time > open_time`, and
  `min_gap_slots` must be ≥ 1 (the solver silently converts 0 to 1).
- **Unknown fields warn instead of failing** — the schema grows every season,
  so unknown fields are accepted with a deduplicated warning. The reserved
  annotation namespace (`operator_notes` or any `x_*` field) never warns.
- **`solve-schedule`** validates at load and exits 3 listing every violation,
  and self-checks its own output against the contract before writing it (a
  violating output is a solver bug — nothing is written, exit 3).
  **`produce-schedule`** validates both files plus output→input referential
  integrity (every assignment's `game_id`/`resource_id` must exist in the
  input) before rendering. `diagnose-schedule` intentionally keeps reading
  raw JSON so it can inspect broken files.
- **Precedence integrity** — a cycle in `precedence` rules is reported as a
  contract error naming the cycle members (previously a silent INFEASIBLE).
  A rule spanning solver pools is also an error: the pool-decomposed solver
  silently drops such rules, and a declared constraint that cannot be
  enforced must not be silently ignored. A rule referencing an unknown
  game/playoff id logs a warning (previously silently ignored).
- **Reference checks** — duplicate game/resource IDs and playoff slots
  pointing at unknown `resource_id`s are contract errors; slot-window
  validity stays in `scheduler.validate_playoff_slots`. `team_conflicts`
  endpoints are deliberately NOT required to appear in `games`: planning-only
  edges (an event with no Layer-2 games yet) are a legitimate, documented
  state with their own `PlanningOnly` conflict-audit status.
- **Review fixes** — resource-fit checks are keyed by
  `(solver_pool, resource_type)`, so a roomy same-type resource in a
  different pool no longer masks that a game cannot fit within its own pool;
  the resource model gained `venue_name`/`playoff_pinned` and the playoff
  model gained `team_a_id`/`team_b_id`/`duration_minutes` so real exporter
  output produces zero unknown-field warnings; a malformed (truncated) JSON
  file at `produce-schedule` now fails through the controlled contract-error
  path instead of an uncaught `JSONDecodeError`.
- **Unfittable games are hard errors** — a game whose `duration_minutes`
  cannot fit any resource of its `resource_type` (per C7 consecutive-slot
  math) now fails the contract instead of surfacing downstream as a mystery
  unscheduled/INFEASIBLE. A `resource_type` with *zero* resources stays a
  warning, preserving the solver's documented unroutable-game exit-1 path,
  and plain capacity shortages remain solver INFEASIBLE with diagnostics.
- **Output sanity** — duplicate game assignments or a double-booked
  `(resource_id, slot)` in `schedule_output.json` block rendering.
- **Conflict-edge warning** — an edge with `primary_overlap_count > 0` but an
  empty `shared_participant_names` list is flagged so empty Conflict-Audit
  name cells get noticed at export time.

### Consolidated doubles selections in validation + scheduler↔validation reconciliation — closes [#160](https://github.com/i12know/vaysf/issues/160)

Follow-up to the canonical resolver work below. The June 11, 2026 real-data run
still showed a nine-record disagreement between scheduler `pod_unprotected_entries`
and the open partner validation issues exported to `Validation-Issues`. Root cause:
the validators evaluated *raw* primary/secondary participant fields while
scheduling resolves the *consolidated* sf_rosters declarations, so a duplicate
blank slot (e.g. WP 156's secondary Table Tennis 35+ selection) produced false
`missing_doubles_partner` / nonreciprocal reports.

- **New `consolidate_doubles_selections()` in `validation/doubles_resolver.py`** —
  collapses duplicate doubles selections for one participant exactly like the
  sf_rosters consolidation in `sync/participants.py` (`remember_roster`): the
  first occurrence of an event wins and a blank partner is filled from the first
  later duplicate that declared one.
- **`IndividualValidator._validate_doubles_partner`** now consolidates duplicate
  primary/secondary declarations of the same doubles event before requiring a
  partner, so a redundant blank slot never creates a false
  `PARTNER_REQUIRED_DOUBLES` issue (WP 156 regression).
- **`TeamValidator._doubles_selections`** applies the same per-participant
  consolidation before canonical resolution, so duplicate-slot candidates no
  longer cause false `AmbiguousPartner`/`NonReciprocal` reports for the
  reciprocal partner (WP 446/441 regression).
- **New automated reconciliation check** — `_reconcile_pod_validation()` in
  `schedule_workbook.py` runs inside `_build_schedule_input` and compares
  scheduler-unprotected doubles keys against open partner validation issues from
  the same snapshot. It reports `missing_validation_issues` (subset criterion
  violations), `mismatched_issue_types`, `contradictory_open_issues` (confirmed
  pair members with a still-open partner issue), and `validation_only_issues`
  (issues referencing participants absent from the exported roster). The result
  is embedded in `schedule_input.json` / `schedule_output.json` as
  `pod_validation_reconciliation`, logged with `[VAY SM]` warnings when dirty,
  and each unprotected entry is annotated with `validation_issue_status`
  (surfaced as a new column in the Conflict-Audit tab).
- **Roster-derived issue persistence** — `sync --type validation` now resolves
  partner declarations from each church's persisted WordPress roster snapshot
  and sends the resulting participant/event issues through the existing
  validation upsert/resolve lifecycle. Scheduler-only failures therefore appear
  in the Church Rep `Validation-Issues` tab instead of remaining export warnings.
- **Event-specific reconciliation keys** now include participant, sport, doubles
  format, and gender. An issue for one division can no longer satisfy another
  division in the same sport, and validation-only records make reconciliation
  explicitly dirty.
- **Current Team-group validation scope** now filters historical WordPress
  participants and rosters against the current eligible ChMeetings `Team *`
  athlete snapshot. Deleted, re-registered, and role-ineligible duplicates no
  longer create false partner ambiguity; stale TEAM issues resolve normally,
  while current athletes naming an ineligible partner receive an actionable
  validation issue. Participant sync also moves an existing roster row to the
  participant's current church after a church transfer, keeping validation and
  scheduling on the same church-owned roster.
- **Expanded tests** cover duplicate-slot consolidation, roster-derived partner
  issue persistence and resolution, event-isolated reconciliation, missing
  issues, contradictions, validation-only divergence, and resolved-issue
  exclusion.
- **Known latent risk:** `qualifying_roles` in `_load_current_eligible_chm_ids`
  is hardcoded as `{"athlete", "participant", "athlete/participant"}`. If VAY
  adds a new combined role string (e.g. `"athlete/leader"`), eligible athletes
  carrying it would be silently excluded from the validation population. Promote
  to a config value when the role taxonomy next changes.

### Nightly sync correctness fixes

- Consolidated duplicate primary/secondary roster selections before writing to
  WordPress. When both selections map to the same event, a blank partner no
  longer overwrites the nonblank partner declaration.
- Approval synchronization now sends only participants with an approved,
  unsynced approval record to ChMeetings. Previously it re-added every approved
  participant on each run, even when there was nothing left to mark as synced.
- WordPress approval reads now expose success/failure status so an API failure is
  not mistaken for an empty unsynced-approval list.

### Canonical doubles resolver: self-pairing prevention and full unresolved coverage — closes [#160](https://github.com/i12know/vaysf/issues/160)

Root cause of the 60-vs-48 `pod_unprotected_entries` gap: three divergent partner
resolvers (TeamValidator, schedule_workbook, church_teams_export dead copy) applied
different matching policies, allowing self-pairings to slip through and letting
12 entries be silently resolved in the validator while remaining unprotected for
scheduling.

- **New `middleware/validation/doubles_resolver.py`** — canonical `resolve_doubles()`
  shared by all consumers. Two-phase algorithm:
  - *Phase 1 (confirm):* T1 exact `normalized_name` lookup → unique candidate →
    `resolvable_name_match` reciprocal check on both sides. Falls through to T2
    (`resolvable_name_match` lookup) only when T1 finds zero candidates.
  - *Phase 2 (diagnose):* emits `UnresolvedRecord` with reason codes
    `MissingPartner`, `SelfPaired`, `AmbiguousPartner`, `NonReciprocal`,
    `PartnerNotFound` and T3 (`likely_name_match`) suggestion hints.
- **Self-pairing rejected** — Phase 1 and Phase 2 both detect
  `partner_norm_name == self.norm_name` and short-circuit with `SelfPaired` before
  any candidate search. Fixes the bug in the old exact-match loop that missed this
  guard.
- **`TeamValidator._check_doubles_partner_matching`** rewritten to call
  `resolve_doubles()`; `MissingPartner` records are still skipped (already caught
  by `IndividualValidator`). Removed no-longer-needed private helpers
  `_same_event_candidates`, `_partial_same_event_candidates`,
  `_resolvable_same_event_candidates`, `_is_unique_partial_reciprocal_match`.
  Added `_doubles_issue_description()` for clean reason→text mapping.
- **`_build_pod_entries_review_rows` in `schedule_workbook.py`** refactored to call
  `resolve_doubles()`. The old `name_to_rows` + `paired_pids` loop is gone.
- **`pod_unprotected_entries` enriched** — each unresolved entry now carries
  `participant_id`, `sport_type`, `sport_format`, and `church_code` so downstream
  tooling can match them to open validation issues without guessing.
- **Dead copy removed** from `church_teams_export.py` (lines 1388–1576 of the
  old file). The setattr loop already overwrote the copy at module load time; it
  is now gone entirely with a tombstone comment.
- **Behavior change for mismatched-name pairs:** both sides of a non-reciprocal pair
  now always receive a validation issue (Issue #160 Tier 2 requirement). Two existing
  tests updated: `test_team_validator_compact_spacing_reduces_to_one_warning` →
  `test_team_validator_compact_spacing_both_sides_warned` (now expects 2 issues);
  `test_team_validator_partial_partner_name_suggests_full_name` updated to expect
  2 issues (Dean PartnerNotFound + Janice NonReciprocal T1).
- **Same-church rule enforced** — `resolve_doubles()` now filters candidates to
  `c.church_code == sel.church_code` in both Phase 1 (`peers_unconfirmed`) and
  Phase 2 (`all_peers`). Cross-church declarations are always `PartnerNotFound` or
  `NonReciprocal` unresolved records, never confirmed pairs. This ensures the
  per-church `TeamValidator` and the all-roster schedule workbook produce the same
  confirmed/unresolved split when given the same data.
- **Bug fix — multi-event participant skip:** confirmation tracking changed from
  `confirmed_ids: set[str]` to `confirmed_gkpids: set[tuple[str, str]]`
  (`(group_key, participant_id)`), so a participant confirmed in Badminton doubles
  is not incorrectly skipped in a second event (e.g. Pickleball doubles).
- **Bug fix — duplicate participant_id rows:** added
  `c.participant_id != sel.participant_id` guard (when participant_id is non-empty)
  to prevent two data rows for the same person from forming a spurious pair.
- **New `middleware/tests/test_doubles_resolver.py`** — 24 tests covering exact
  reciprocal, T2 initial-abbreviation, self-pairing, missing partner,
  NonReciprocal (T1 and T2), PartnerNotFound with 0/1/2+ T3 suggestions,
  AmbiguousPartner, group isolation, same-church confirmation, cross-church
  rejection, already-confirmed exclusion, multi-event independence, duplicate-ID
  guard, and group_key override.
- **New tests in `test_schedule_workbook.py`:** self-paired entry flags as
  `SelfPaired` in POD review rows; enriched `pod_unprotected_entries` fields
  verified; cross-church pair stays unresolved in the scheduler path.

### Racquet (pod) cross-sport conflict modeling — closes [#158](https://github.com/i12know/vaysf/issues/158)

- Extended shared-athlete conflict modeling beyond team sports to racquet
  **doubles** entries, covering the two classes the gym-only builder missed:
  **team ↔ racquet** (e.g. Basketball + Badminton) and **racquet ↔ racquet**
  (e.g. Badminton + Pickleball). Singles remain a follow-up (Decision 3).
- Added `_resolve_pod_doubles()`, which reuses the reciprocal-partner pairing in
  `_build_pod_entries_review_rows()` to resolve confirmed doubles pairs and
  assign each a stable, reproducible ID (`{division_id}-E{nn}`, e.g.
  `BAD-Men-Doubles-E01`); entries are sorted by participant ID so IDs are
  identical across re-runs.
- `_build_pod_game_objects()` now attaches those IDs to each division's
  **Round-1** games. Only R1 is protected — later single-elimination rounds keep
  `team_a_id`/`team_b_id` of `null` because their participants are unknowable
  until earlier rounds are played (Decision 1); byes are likewise unprotected.
- Added `_build_cross_sport_conflicts()` plus the shared
  `_make_shared_athlete_edge()` / `_team_state_to_unit()` helpers (the gym
  builder was refactored onto the same edge helper). Edges keep the existing
  primary/secondary-overlap protection so the solver and `Conflict-Audit` tab
  consume every conflict class identically.
- **Solve order (Decision 5):** racquet/pod pools now solve **after** the team
  sports in `scheduler.py` (`_POOL_SOLVE_PRIORITY`), so a shared athlete's
  racquet game adapts around the already-placed team-sport slots via cross-pool
  avoidance (C3x) rather than the team game moving.
- `UnresolvedDoubles` (missing/non-reciprocal partner) cannot be protected;
  they are surfaced in a new `pod_unprotected_entries` field, passed through the
  solver, and listed in the `Conflict-Audit` tab rather than silently dropped.
- Added tests covering stable-ID assignment, R1 team-ID attachment,
  team↔racquet and racquet↔racquet edge generation, unprotected-entry
  reporting, and the racquet-after-gym solve order with cross-pool avoidance.
- Updated `docs/SCHEDULING.md` Phase 2 section.

### Post-review fixes for #158

- **[P1] Partial time-overlap detection in C3x and `build_conflict_audit()`:**
  `team_occupied_slots` now stores `(day, start_min, end_min)` intervals instead
  of slot labels; `cross_pool_avoidance` carries the same tuples. The C3x
  constraint in `_solve_one_pool` and the audit overlap check both use
  interval-intersection logic (`start_a < end_b and start_b < end_a`) so a
  60-min basketball game at 08:00 correctly blocks a 30-min badminton slot at
  08:30, which shared an athlete but different slot labels. New helper functions
  `_slot_label_to_interval()` and `_slot_overlaps_any()` in `scheduler.py`.
  New regression test `test_cross_pool_avoidance_detects_partial_time_overlap`.

- **[P2] Bye-aware R1 bracket math in `_build_pod_game_objects()`:**
  Replaced `floor(N/2)` with standard single-elimination bracket math:
  bracket size `P = 2^ceil(log2(N))`, byes `= P - N`, R1 games `= (N - byes) / 2`.
  For N=5 this correctly produces 1 R1 match (E04 vs E05) with E01–E03 on byes,
  instead of the previous 2 matches. New test `test_pod_game_objects_r1_matchups_are_bye_aware`.

- **[P2] Dynamic racquet pool solve order:**
  Removed hardcoded priorities 100–103 for specific court names. Racquet pools
  (Tennis Court, Table Tennis Table, Badminton Court, Pickleball Court) are now
  sorted dynamically: descending by game count (more entries → more constrained →
  solve first), with alphabetical tiebreaking. Refactored `_POOL_SOLVE_PRIORITY`
  into `_POOL_SOLVE_PRIORITY_FIXED` (BC/Soccer only) + `_RACQUET_PRIORITY` (computed
  at solve time from `games_by_pool`).

- Follow-up review fixes now carry each pod game's `division_id` and
  `division_entry_count` into `schedule_input.json`. Racquet solve priority
  aggregates planned entries across active divisions, rather than using game
  count as a proxy. Bye placement likewise uses all planned doubles entries;
  unresolved entries occupy anonymous draw positions and affect R1/byes without
  receiving false conflict-protection IDs.

- Added `middleware/chrome_export_vaysf_forms.py`, an operator helper that
  attaches to an authenticated Chrome debugging session and concurrently exports
  the Consent Form and Individual Application Form to stable files under
  `middleware/data/`.
- Documented the dedicated Windows Chrome debugging profile, first-run VAY SM
  login, export command, output filenames, and 15-minute per-form timeout.
- Added `middleware/daily-run.bat` for fail-fast nightly form export, group
  assignment, synchronization, validation, report generation, and scheduling.
- Chrome form exports now append progress, success, and traceback-backed failure
  messages to the normal daily `middleware/logs/sportsfest_YYYYMMDD.log` file.

## WordPress Plugin 1.0.14 (2026-05-30)

- **Admin insurance approval email**: clicking **Approve Insurance** now automatically emails the Church Rep that staff reviewed and approved the church's COI.
- Rebuilt `plugins/vaysf.zip` with plugin header/version `1.0.14`; database version remains `1.0.4`.

## WordPress Plugin 1.0.13 (2026-05-30)

- **Admin Churches table**: added a nonce-protected **Approve Insurance** button for submitted PDFs, restricted to users with `manage_options`.
- Rebuilt `plugins/vaysf.zip` with plugin header/version `1.0.13`; database version remains `1.0.4`.

### Proof-of-insurance upload — public token link + Church Application Form sync — closes [#154](https://github.com/i12know/vaysf/issues/154)

- **WordPress plugin 1.0.12 / DB 1.0.4**: added four columns to `sf_churches` (`insurance_file_url`, `insurance_uploaded_at`, `insurance_token`, `insurance_token_expiry`) via `dbDelta` plus fallback `ALTER` migrations for upgrades
- **Self-service upload (Path 1)**: new public `/insurance-upload/` page with a two-state template (`templates/insurance-upload.php`)
  - State A: church rep enters Church Code + Email; a one-time 64-char token (48 h default expiry, configurable via `vaysf_insurance_token_expiry_hours`) is emailed only when the email matches `church_rep_email`. The response is always the same generic message to prevent church/email enumeration
  - State B (`?token=`): validates the token; shows the PDF upload form when valid, or an expiry notice with a "Request a New Link" path when expired/unknown
  - Upload validates PDF type (declared MIME + `.pdf` extension + `%PDF-` magic bytes) and ≤ 10 MB before storing to `wp-content/uploads/vaysf/insurance/{church_code}_{YmdHis}.pdf`, then sets `insurance_file_url`/`insurance_uploaded_at`, advances `insurance_status` to `submitted` (never downgrading `approved`), invalidates the token, and emails a confirmation. Optional admin notification via the `vaysf_insurance_admin_notify` toggle
- **New public REST endpoints** (no API key — guarded by the per-church token): `POST /vaysf/v1/insurance/request-link` and `POST /vaysf/v1/insurance/upload`
- **New shortcode**: `[insurance_upload]` renders the Church Rep proof-of-insurance request/upload flow inside a normal WordPress page
- Insurance request emails now return Church Reps to the same shortcode page that requested the link, so sites do not depend on the `/insurance-upload/` rewrite route
- **Frontend church list**: `[vaysf_churches]` now shows registration and proof-of-insurance status, with optional `insurance_status="pending|submitted|approved|rejected"` filtering
- **`POST /vaysf/v1/churches` and `PUT /vaysf/v1/churches/{code}`** now accept `insurance_file_url` and `insurance_uploaded_at` from the middleware; token columns remain server-managed and are not writable through the API-key endpoint
- **Admin Churches table**: insurance column now shows a status badge, upload timestamp, and admin-only Download PDF link; rows in `submitted` status are highlighted for staff attention
- **Middleware (Path 2)**: `sync/churches.py` maps the Church Application Form attachment column (named constant `INSURANCE_ATTACHMENT_COLUMN = "Proof of Insurance"`) to `insurance_file_url`, advancing `pending` → `submitted` when a URL is present and never downgrading `approved`. The column is optional, so existing forms without it sync unchanged
- Added `tests/test_sync_churches_insurance.py` covering URL mapping, no-downgrade, blank/NaN cells, and missing-column backward compatibility; rebuilt `plugins/vaysf.zip`

### Solver improvements — day spread + cross-pool conflict elimination

- **Six-tier lexicographic objective** (scheduler.py) — upgraded from five tiers
  - New **Tier 3 — Max-per-day spread**: when cross-pool avoidance is active, minimize the maximum number of games on any single day, distributing pool-play games evenly across both weekends instead of packing everything into the first Saturday/Sunday
  - **Tier 5 — VB gender switches** promoted above **Tier 6 — sum of slot indices**: net-height changes between Men's VB and Women's VB now outrank the pack-early preference, reducing the "VBW game right after VBM on the same court" placement that previously occurred
  - Sum-of-slot-indices demoted to Tier 6 (tiebreaker only)
  - Updated weight construction in `scheduler.py` and objective table in `docs/SCHEDULING.md`

- **C3x — cross-pool conflict constraint** (scheduler.py): pools are now solved in priority order (BC Station → Soccer Field → Tennis/Badminton/Pickleball/Table Tennis → Gym Core). After each pool is solved, team slot occupancies are collected. Cross-sport conflict edges in `team_conflicts` are used to identify gym-sport partner teams; those teams are forbidden from being assigned to any slot already claimed by their BC/Soccer counterpart in the same time window. This hard constraint eliminates the cross-sport pink rows (BBM/VBM/VBW vs BC, BBM/VBM/VBW vs Soccer) that the within-pool penalty alone could not fix. `max_games_per_day` is reported per pool in solver logs.

## Version 1.11 (2026-05-23)

### New Features
- Added Master-Schedule tab to `VAYSF_Schedule_*.xlsx` workbook
  - New `Master-Schedule` tab shows all sports side-by-side with one row per time slot and one column per court/field/table
  - Column headers are natural-sorted (Court-1 before Court-2) with `Other` gym grouped before `Orange` gym
  - Empty columns (courts with no assigned games) are hidden automatically; empty time-slot rows are suppressed
  - Cell text is compacted to a single line showing game ID, teams, and venue name
  - `produce-schedule` wires the tab in automatically when `VAYSF_Schedule` workbook is built

- Redesigned Bible Challenge pool-play to a single global pool with no repeated opponents
  - Replaced the previous multi-pool + cross-pool rotation with a single flat pool using backtracking constraint solver
  - New `_bc_no_repeat_triplets()` generates Jeopardy-format triplets (3 teams per game) where no pair of teams ever meets more than once in the preliminary round
  - Each team plays exactly `COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM` games (currently 3), matching the 2025 season format
  - For n ≥ 7 teams the no-repeat constraint is always satisfiable; solver warns and omits BC games if the constraint cannot be met
  - Game IDs changed from pool-qualified (`BC-P1-RR-1`) to flat global (`BC-RR-1`, `BC-RR-2`, …)

- Seeded Bible Challenge teams are guaranteed different preliminary games
  - Teams with a non-empty non-zero `Seed` field in `Pool-Assignment` are tracked as seeded
  - Backtracking solver enforces that at most one seeded team appears in any single triplet, so TLC (seed 1) and SFV (seed 2) will never meet in pool play

- Documented the five-tier lexicographic solver objective in `docs/SCHEDULING.md` and `scheduler.py`
  - Tier 1: minimize same-slot shared-athlete conflicts (weighted by primary/secondary sport penalty)
  - Tier 2: minimize same-slot volleyball net-height switches on shared courts
  - Tier 3: minimize latest finish slot index across all games (end the event as early as possible)
  - Tier 4: minimize sum of all assigned slot indices (pack games toward earlier slots)
  - Tier 5: minimize same-court sport-type switches for non-volleyball courts
  - Table of all five tiers with player-facing examples and weight-construction code added to SCHEDULING.md

- Added chronological day ordering and sum-of-slots slot-packing to solver objective — closes [#134](https://github.com/i12know/vaysf/issues/134)
  - Solver now fills earlier date slots first (Fri-1 → Sat-1 → Sun-1) before overflowing to later days
  - Tier 4 weight construction uses the slot's date-index multiplied by a large constant so cross-day preference dominates within-day ordering

- Standardized schedule colors and category prefixes for all sports — closes [#131](https://github.com/i12know/vaysf/issues/131)
  - All schedule tabs now share a single color palette defined in `schedule_workbook.py`
  - Sport category prefixes (BB, VBM, VBW, BC, SOC, TT, TEN, BAD, PCK) are applied consistently across Pool-Assignment, Court-Schedule-Sketch, and Master-Schedule

- Extended Gym-Modes support to Tennis Court and Table Tennis Table resource types
  - `_build_gym_resources_from_allocator()` now maps Tennis and Table Tennis through the allocator so these surfaces participate in Stage-A allocation rather than falling through to the constant fallback

- Added retry logic for `get_validation_issues()` on transient WordPress disconnect — closes [#115](https://github.com/i12know/vaysf/issues/115)
  - Up to 3 retries with exponential back-off when the connection resets mid-read during a church export

- Guardian consent self-healing: accept name+birthdate fuzzy match at score ≥ 49
  - Consent check now falls through to a name+birthdate fuzzy match when a direct ID lookup returns no record, covering re-registered participants whose ChMeetings ID changed between seasons

### Bug Fixes
- Fixed BC cross-pool repeat opponents: under the old 4–5 team sub-pool design, TLC and MWC appeared in both `BC-P1-RR-1` and `BC-P1-RR-2`, violating the "play every opponent only once" rule; the global no-repeat redesign eliminates this entirely
- Fixed seeded teams appearing in the same BC pool-play game: TLC (seed 1) and SFV (seed 2) were placed in the same triplet because the backtracking pivot selected index-0 (TLC) first and tried the `{0,1,2}` triple; the new seed-count guard breaks this

## Unreleased

### New Features
- Auto-generate gym playoff game objects (QF/Semi/Final/3rd) for Basketball, VB Men, VB Women — closes [#132](https://github.com/i12know/vaysf/issues/132)
  - `_build_assigned_gym_game_objects()` now returns pool games AND auto-generated single-elimination playoff games sized to the estimating-team count (4-team → Semi/Final/3rd; 8-team → QF/Semi/Final/3rd), matching the existing Soccer pattern
  - Playoff games carry standard seed/winner/loser references (`BBM-Seed-1`, `WIN-BBM-QF-1`, `LOS-BBM-Semi-2`, etc.) so they appear in `schedule_input.json` without requiring any `Playoff-Slots` entries
  - Precedence rules are auto-wired: Pool → QF → Semi → Final / 3rd with a one-slot gap between rounds
  - Operators who still want to pin a specific game to a court/time can continue to do so via the `Playoff-Slots` tab in `venue_input.xlsx` — those rows override the solver assignment via `merge_playoff_slot_assignments()`
  - New shared helper `_build_single_elim_playoff()` centralizes the bracket-generation logic so future sports can reuse it


- Added first-class 2-game / 3-game team-sport pool policies
  - Core gym team sports no longer rely on the vague legacy fallback when `Target Pool Games/Team` is set to `3`
  - `Venue-Estimator`, `Pool-Assignment`, `Court-Schedule-Sketch`, and `schedule_input.json` now all share the same explicit policy for `2` and `3`
  - Unsupported targets such as `4` now fail loudly instead of silently drifting into a legacy round-robin layout
  - Operator docs now explain that `Target Pool Games/Team` is driven from `middleware/config.py`, not edited directly in Excel, and that a `2 -> 3` change requires rebuilding the workbook and rerunning `assign-pools`
  - Layer 2 now logs an advisory warning when `venue_input.xlsx` `slot_minutes` values do not match the configured per-sport game duration for the same scheduled resource type
  - Standard bracket sports now default to one 3rd-place game instead of zero; Soccer's live Layer-2 generator now adds `SOC-3rd` after the semi-finals, while Bible Challenge remains a special case because its 3-team final already resolves 1st / 2nd / 3rd
  - Venue resource naming is now normalized to one canonical vocabulary (`BC Station`, `Soccer Field`, `Table Tennis Table`, etc.), direct venue `resource_id` prefixes now use `BB` / `VB` / `PCK` / `TT` / `TEN` instead of mixed legacy abbreviations like `BAS` / `VOL` / `PIC`, and date-derived logical day keys now use weekday labels such as `Fri-1`, `Sat-1`, `Sun-1`
  - `Venue-Estimator` now treats racquet `Potential Teams/Entries` as a rule-aware ceiling from current registrations, capped by the 2026 church entry limits; `Estimating Teams/Entries` remains the operational count used for the current schedule build
- Added Soccer (Coed Exhibition) Phase-1 planning support
  - New `SOCCER_ENABLED` config flag (default `True` for 2026); set to `False` to remove Soccer from the Phase-1 scheduling/planning outputs (`Venue-Estimator`, `Pool-Assignment`, and conflict edges)
  - `Pool-Assignment` now includes Soccer team rows (prefix `SOC`) alongside BB / VBM / VBW / BC, with up-to-3 seeds
  - Soccer shared-athlete edges with BB / VBM / VBW / BC are included in `team_conflicts`
  - `schedule_input.json` now includes real Soccer pool games plus `SOC-Semi-1`, `SOC-Semi-2`, and `SOC-Final` on `Soccer Field` resources
  - Soccer precedence rules now force all Soccer pool rounds to finish before the semis, and the final to start after both semis
  - `Conflict-Audit` now evaluates Soccer shared-athlete edges against real scheduled Soccer field games instead of leaving them `PlanningOnly`
  - Completes Phase 1 of the scheduling roadmap for the 2026 season
- Added Bible Challenge Phase-1 planning support
  - `Venue-Estimator` now treats Bible Challenge as a sequential single-classroom Jeopardy queue instead of a normal concurrent court-hours sport
  - `Pool-Assignment` now includes BC team rows alongside BB / VBM / VBW
  - `schedule_input.json` now includes real BC Jeopardy round-robin queue games on `BC Station`, generated from the BC pool draw
  - BC playoff placeholders (`BC-Semi-1..3`, `BC-Final`) are now generated with precedence rules so BC prelim rounds finish before the semis, and the final stays after the semis
  - `scheduler.py` and `produce-schedule` now support optional third-team games via `team_c_id`, so BC appears in the final schedule workbook instead of staying planning-only
  - `Conflict-Audit` now evaluates BC shared-athlete edges against scheduled BC round-robin games

- Improved final `Schedule-by-Time` readability for mixed-venue gym schedules
  - `venue_input.xlsx` rows now derive logical day labels from the `Date` column when `Day` is absent, so direct venue rows no longer collapse across multiple actual dates into one fake `Day-1`
  - Direct venue resources now carry `venue_name` through to `schedule_input.json`
  - `produce-schedule` now renders one continuous day section per Gym Core sport and uses venue-qualified court headers such as `Orange Gym Court-1` and `HS Big Gym Court-3` for more consistent operator-facing output

- Added an editable `Pool-Assignment` tab and `assign-pools` command for Layer-1 team seeding
  - `build-schedule-workbook` now writes a `Pool-Assignment` tab for BB / VBM / VBW with one row per eligible team grouping, editable `Seed` cells, computed draw position, and computed pool placement
  - New `python main.py assign-pools --workbook ...` command re-reads the edited workbook, recomputes the serpentine draw, writes the refreshed tab back, and persists the editable state in `pool_assignments.json`
  - Rebuilt workbooks now reload the prior seed state from `pool_assignments.json`, so operator edits survive future `build-schedule-workbook` runs

- Wired Pool-Assignment seeding into Layer 2 and added shared-athlete conflict audit output
  - `export-church-teams` now reads `pool_assignments.json` beside the export artifacts and writes seeded core gym teams into `schedule_input.json` for Basketball / VB Men / VB Women instead of leaving Layer-2 on raw placeholder slots
  - `schedule_input.json` now carries `team_conflicts` edges so the solver can see shared-athlete overlap between those seeded core gym teams
  - `scheduler.py` now solves the core gym sports as one conflict-aware `Gym Core` pool while still routing Basketball only to basketball courts and Volleyball only to volleyball courts
  - The solver objective now minimizes same-slot shared-athlete conflicts before finish time / volleyball net-switch tie-breaks, with heavier penalty when the overlap touches an athlete's declared primary sport
  - `schedule_output.json` now includes `conflict_audit_summary` and `conflict_audit`
  - `produce-schedule` now renders a third `Conflict-Audit` tab in `VAYSF_Schedule_*.xlsx`

- Added participant self-healing when primary sport is blank but secondary sport is populated
  - Participant sync now promotes the secondary sport into the primary slot before roster sync and validation when the form data is internally inconsistent
  - The original secondary slot is cleared after promotion so the athlete is not double-counted across primary/secondary paths
  - A warning-level `primary_sport_self_healed` validation issue is synced to WordPress so staff can still audit the correction

- Added a `Summary` tab to `Schedule_Workbook_*.xlsx`
  - `build-schedule-workbook` now writes an operator-facing first tab that explains the Layer 1 / Layer 2 workflow, the main commands to rerun while iterating, and where to find the full scheduling HOW-TO docs

- Improved Layer-2 volleyball scheduling to reduce same-court net-height changes
  - `scheduler.py` now keeps the existing earliest-finish objective as primary, but adds a secondary tie-breaker for `Volleyball Court` pools that minimizes adjacent same-court `Volleyball - Men Team` ↔ `Volleyball - Women Team` switches when multiple equally-early solutions exist
  - Added solver coverage proving the tie-breaker prefers same-court volleyball blocks without weakening feasibility or the pack-early behavior

- Added a consent-404 investigation workflow for stale ChMeetings IDs found during `check-consent`
  - New `python main.py investigate-consent-404s [--log-file ...] [--output ...]` command reads consent-run log warnings, loads current WordPress and ChMeetings data, and classifies each stale ID as likely re-registered, likely deleted, or manual-review-needed
  - New `middleware/run-consent-404-investigation.bat` helper for one-click reruns on the middleware machine
  - Writes `data/consent_404_investigation.xlsx` with `Cases` and `Candidates` sheets so staff can audit replacement IDs and match evidence

- Added middleware late-racquet overrides and aligned cutoff timing with season registration dates
  - New `middleware/data/late_racquet_overrides.json` allowlist plus `Config.LATE_RACQUET_OVERRIDES_FILE` for pastor-approved / scheduler-approved exception handling on the middleware side
  - Late racquet enforcement now uses the participant's effective season registration date: existing WordPress `sf_participants.created_at` when present, otherwise the current sync date on first create
  - WordPress `created_at` timestamps are now interpreted in `WORDPRESS_CREATED_AT_TIMEZONE` (default `UTC`) and converted into `BUSINESS_TIMEZONE` (default `America/Los_Angeles`) before late-racquet or athlete-fee date comparisons
  - Overrides are keyed by `chmeetings_id`, can be scoped to specific racquet sports, and can carry optional `approved_by` / `reason` metadata for operator context
  - Re-syncs now stay blocked for post-deadline racquet athletes until an override is added, closing the previous "brand-new only" loophole
  - Added sync tests covering first-sync late pruning, pre-deadline re-sync allowance, post-deadline re-sync blocking, and scoped override behavior

- Wired the Layer-2 Stage-A gym mode allocator into the live scheduling pipeline — closes [#103](https://github.com/i12know/vaysf/issues/103)
  - `_build_schedule_input()` now runs the greedy allocator (Stage A) when `venue_input.xlsx` is present with a `Gym-Modes` tab and gym blocks with `Exclusive Venue Group` set; falls back to the `SCHEDULE_SOLVER_GYM_COURTS` constant when not
  - New `_build_gym_resources_from_allocator(decisions)`: converts `AllocationDecision` objects into `schedule_input.json` resources with day-aware IDs (`GYM-{day}-{n}`), `exclusive_group` set to the gym name, and the allocator-assigned `resource_type`
  - `_load_venue_input_rows()` now reads the `Day` column (if present) and uses day-aware resource IDs: `BAD-Sat-1-1`, `PCK-Sun-1-1`, etc.  Falls back to `"Day-1"` when the column is absent.  Counter is keyed by `(resource_type, day)` so courts on different days are numbered independently
  - `GYM_RESOURCE_TYPE` (`"Gym Court"`) split into `GYM_RESOURCE_TYPE_BASKETBALL = "Basketball Court"` and `GYM_RESOURCE_TYPE_VOLLEYBALL = "Volleyball Court"` in `config.py`; `_build_gym_game_objects()` assigns these specific types per sport
  - `_build_gym_resource_objects()` signature changed from `(n_courts)` to `(n_basketball, n_volleyball)` for the fallback path; basketball courts numbered first within each session
  - `AllocationDecision` dataclass gains `slot_minutes: int = 60` field (populated from the source `GymBlock`)
  - New `Gym-Allocation` tab added as 7th tab in `Schedule_Workbook_*.xlsx`; shows allocation decisions, mode demand vs supply, and shortfall table (or a fallback note when the allocator did not run)
  - `gym_allocation` key added to `schedule_input.json`; carries full allocator output or `{"source": "fallback", ...}` when the constant-based fallback was used
  - `generate_venue_template()` regenerated: new `Day` and `Exclusive Venue Group` columns in `Venue-Input`; new `Gym-Modes` and `Playoff-Slots` sheets with example rows; `SportsFest_2026_Venue_Input_Template.xlsx` updated accordingly
  - `docs/SCHEDULING.md`, `docs/SCHEDULE-HOW-TO.md`, and `CHANGELOG.md` updated

- Added greedy gym mode allocator (`middleware/gym_allocator.py`) — closes [#102](https://github.com/i12know/vaysf/issues/102)
  - New module implementing Layer-2, Stage A of the scheduling pipeline
  - `allocate(demand, gym_modes, blocks)` — greedy priority allocator: ranks sport modes by court-hours demand (most-needed first), claims gym time-ranges until demand is met, prefers the gym with most courts for each mode, and breaks ties by switch penalty (avoids mode flips)
  - `extract_gym_blocks(venue_rows)` — collapses expanded per-court venue rows into unique `GymBlock` objects keyed on `(exclusive_group, day, open_time, close_time, slot_minutes)`
  - `aggregate_demand_by_mode(venue_capacity_rows)` — sums `Estimated Court Hours` per mode; Volleyball Men + Women aggregate under `"Volleyball Court"`, Pickleball + Pickleball 35+ under `"Pickleball Court"`; Table Tennis and Tennis are excluded (dedicated pod courts)
  - `EVENT_TO_MODE` maps all gym-sport event names to their Gym-Modes resource type
  - `AllocationResult` reports `decisions`, `mode_supply`, `mode_demand`, `mode_shortfall`, and `switch_count`
  - Structural exclusivity guaranteed — no block is ever handed to two modes
  - Graceful on demand > capacity: `mode_shortfall` carries the per-mode gap, no crash
  - 32 unit tests in `tests/test_gym_allocator.py` covering: block extraction, demand aggregation, demand-fits, demand-exceeds-capacity, priority ordering, structural exclusivity, switch minimization, and preferred-gym selection

### Removed
- Dropped 6 scheduling tabs (`Venue-Estimator`, `Pod-Divisions`, `Pod-Entries-Review`, `Court-Schedule-Sketch`, `Pod-Resource-Estimate`, `Schedule-Input`) from `Church_Team_Status_ALL_*.xlsx` — closes [#101](https://github.com/i12know/vaysf/issues/101)
  - `export-church-teams` still writes `schedule_input.json` alongside the ALL workbook for `solve-schedule` and `build-schedule-workbook`
  - All 6 tabs remain available via `python main.py build-schedule-workbook` → `Schedule_Workbook_*.xlsx`
  - `docs/SCHEDULING.md` and `docs/SCHEDULE-HOW-TO.md` updated: transition note removed; Step 1 description and resource-ID lookup instructions updated to point operators to `build-schedule-workbook`

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
- Pinned `Playoff-Slots` rows now replace modeled assignments with the same `game_id` instead of duplicating finals in `schedule_output.json` / `VAYSF_Schedule_*.xlsx`
  - Fixes cases like `BC-Final` appearing once from the solver and a second time from a pinned Sunday finals row
  - Solver summary logging now separates modeled scheduled games from manual playoff-only rows so the output count is easier to audit
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
