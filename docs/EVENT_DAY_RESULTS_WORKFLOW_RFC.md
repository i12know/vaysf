# RFC: Event-Day Results, Standings, and Advancement Workflow

**Status:** Draft for review  
**Target:** VAY Sports Fest 2026  
**Scope:** Event-day match results, scoresheet archiving, public progress display, standings, and advancement  
**Important:** This RFC proposes a workflow and data model only. It intentionally makes no production code changes.

## 1. Problem Statement

Sports Fest currently relies on Sport Coordinators to oversee each competition and record wins, losses, and scores manually on paper scoresheets. That paper trail must remain because it is simple, resilient, familiar to coordinators, and useful when resolving disputes.

However, paper alone does not provide a timely, centralized way to:

- know which scheduled matches have been completed;
- collect results consistently from multiple venues and sports;
- calculate standings and identify advancing teams;
- inform spectators about current results and upcoming matches;
- preserve a digital copy of the official scoresheet;
- audit corrections or disputed results.

The proposed system makes WordPress the event-day operational record while keeping the signed paper scoresheet as the authoritative field record.

## 2. Goals

1. Load the final published schedule into WordPress using stable game identifiers.
2. Give authorized Sport Coordinators a secure, mobile-friendly way to report results.
3. Preserve the existing paper scoresheet process.
4. Allow a photograph or PDF scan of the paper scoresheet to be attached to the result.
5. Maintain an append-only history of submissions and corrections.
6. Display completed results, upcoming matches, standings, and confirmed advancement publicly.
7. Recalculate provisional standings promptly while requiring human confirmation before semifinal or final advancement becomes official.
8. Deliver a usable minimum viable workflow within a few days.

## 3. Non-Goals for the Initial Release

The first release should not attempt to provide:

- a native iPhone or Android application;
- live play-by-play scoring;
- OCR of handwritten scoresheets;
- elimination of paper scoresheets;
- ChMeetings result synchronization;
- automatic advancement without human confirmation;
- full bracket automation for every sport;
- complex push-notification infrastructure.

## 4. Governing Principles

### 4.1 Paper remains authoritative

The signed paper scoresheet is the official field record. The WordPress result is the operational digital copy used for standings, advancement, and public communication.

When a conflict occurs, staff compare the digital entry against the paper scoresheet or its archived image.

### 4.2 Published schedule is frozen

The repository currently generates `schedule_output.json` from the scheduling pipeline. Once event-day results begin, the system must distinguish between:

- **Generated schedule:** the latest solver or operator output;
- **Published schedule:** the frozen schedule currently used by coordinators and spectators;
- **Schedule revision:** an explicit, reviewed change to the published schedule.

A nightly scheduling run must never silently replace the schedule against which results have already been submitted.

### 4.3 Stable `game_id` is the integration key

The scheduling system already assigns each game a stable string `game_id`. That identifier should connect:

- the generated schedule;
- the WordPress match record;
- the printed scoresheet;
- the QR code;
- the submitted result;
- any later correction or archived file.

### 4.4 Results are append-only

Corrections should create a new revision rather than overwrite history. The system should always retain:

- original submission;
- corrected submission;
- who made each change;
- when each change occurred;
- the reason for correction;
- the scoresheet file associated with each revision.

### 4.5 Advancement requires confirmation

Standings may be calculated automatically, but semifinal and final advancement should remain provisional until an authorized Sport Coordinator or Results Desk administrator confirms it.

## 5. User Roles

### 5.1 Sport Coordinator

A Sport Coordinator may:

- view matches for assigned sports;
- submit and certify match results;
- upload scoresheet photographs or PDFs;
- review provisional standings for assigned sports;
- request or enter corrections with a reason;
- confirm advancement if granted that authority.

A coordinator must not be able to modify unrelated sports.

### 5.2 Results Desk

The central Results Desk may:

- view all sports and venues;
- identify overdue or missing results;
- verify submissions;
- review disputes and corrections;
- attach scans received through another channel;
- confirm advancement;
- publish schedule revisions;
- export the event archive.

### 5.3 Spectator

A spectator may view only public information:

- schedule;
- match status;
- official or reported scores;
- standings;
- confirmed advancing teams;
- last-updated time.

Scoresheet files, coordinator identities, internal notes, and audit history remain private.

## 6. Proposed Operational Workflow

## 6.1 Before Sports Fest

1. Finalize the schedule and choose the version to publish.
2. Run a schedule publication command in dry-run mode.
3. Review the proposed additions, changes, cancellations, and conflicts.
4. Publish the schedule to WordPress.
5. Generate paper scoresheets containing:
   - Game ID;
   - sport and division;
   - stage or pool;
   - scheduled time and location;
   - participating teams or entries;
   - a QR code linking directly to the secure result-entry page.
6. Create an individual WordPress account for each Sport Coordinator.
7. Assign authorized sports to each coordinator.
8. Test result submission from a phone before the event.

## 6.2 At the end of a match

1. Officials complete the normal paper scoresheet.
2. The Sport Coordinator verifies that the paper is complete.
3. The coordinator scans the QR code or selects the match from `Needs Result`.
4. WordPress opens the correct match.
5. The coordinator enters the required score details.
6. The coordinator checks a certification statement confirming that the entry matches the official paper scoresheet.
7. The coordinator submits the result.
8. WordPress stores the result, submitter, timestamp, schedule version, and revision number.
9. The coordinator photographs or uploads the scoresheet immediately or later.
10. Public pages update with the appropriate status.
11. Provisional standings are recalculated.

A failed photo upload must not erase or block a valid score submission. The result may be saved with `scan pending` and the file attached later.

## 6.3 At the end of pool play

1. WordPress detects that all required pool matches have official results.
2. The system displays provisional standings and the tiebreak calculation.
3. The Sport Coordinator compares the result against paper records and the sport's rules.
4. An authorized person clicks `Confirm advancement`.
5. The confirmed teams populate semifinal or final placeholders.
6. The public advancement page updates.

## 6.4 Corrections and disputes

1. A coordinator or administrator opens the current result.
2. The user enters the corrected score and a required correction reason.
3. The system creates a new revision without deleting the previous revision.
4. The match may temporarily display `Under Review` if the correction affects standings or advancement.
5. Standings are recalculated.
6. Previously confirmed advancement must be re-confirmed if the correction changes the qualifiers.

## 7. Schedule Publication Workflow

Add a middleware command conceptually shaped as:

```text
python main.py publish-schedule --dry-run
python main.py publish-schedule --execute
```

The command should:

1. Load and contract-validate `schedule_input.json` and `schedule_output.json`.
2. Merge game metadata with assignments.
3. Calculate a schedule version and source hash.
4. Compare the proposed schedule with the currently published WordPress schedule.
5. Report:
   - new games;
   - changed future games;
   - cancelled games;
   - unchanged games;
   - completed games that would be affected.
6. Refuse to overwrite or delete completed matches.
7. Upsert future matches by stable `game_id` only after explicit execution.
8. Store an import audit summary.

After event-day scoring begins, removed future games should be marked cancelled rather than deleted.

## 8. WordPress Data Model

The plugin already defines `sf_competitions`, `sf_schedules`, and `sf_results`, but the schema predates the current string-based scheduling model. The existing tables may be upgraded rather than replaced.

## 8.1 Proposed `sf_schedules` additions

- `game_key` - unique scheduler `game_id`;
- `schedule_version`;
- `event`;
- `stage`;
- `pool_id`;
- `round_number`;
- `team_a_key`, `team_a_label`;
- `team_b_key`, `team_b_label`;
- `team_c_key`, `team_c_label`;
- `team_ids_json`;
- `resource_id`;
- `scheduled_slot`;
- `game_status`;
- `source_hash`;
- `published_at`.

Suggested statuses:

- `scheduled`;
- `in_progress`;
- `reported`;
- `official`;
- `under_review`;
- `cancelled`.

## 8.2 Proposed `sf_results` additions

- `score_json`;
- `winner_keys_json`;
- `submitted_by_user_id`;
- `certified_at`;
- `verified_by_user_id`;
- `verified_at`;
- `current_revision`;
- `correction_reason`;
- `public_status`;
- `scan_status`.

## 8.3 New `sf_result_revisions` table

One row per submission or correction:

- revision ID;
- result ID;
- revision number;
- submitted score JSON;
- winner JSON;
- notes;
- correction reason;
- submitted by;
- submitted at;
- verification state;
- source IP or request metadata where appropriate.

## 8.4 New `sf_result_files` table

One row per scoresheet file:

- file ID;
- result revision ID;
- protected file path;
- original filename;
- MIME type;
- byte size;
- SHA-256 hash;
- uploaded by;
- uploaded at.

## 9. Result Form Types

A universal pair of score boxes is insufficient. The MVP should support a small number of reusable result types.

### 9.1 Simple score

Examples: Basketball and Soccer.

Capture:

- Team A score;
- Team B score;
- overtime or tie note;
- winner derived from validated values.

### 9.2 Set-based score

Examples: Volleyball, Badminton, Pickleball, Tennis, and Table Tennis.

Capture:

- per-set or per-game scores;
- sets or games won;
- winner;
- optional retirement, default, or forfeit state.

### 9.3 Multi-team score

Example: Bible Challenge.

Capture:

- all participating teams;
- cumulative score for each team;
- ordering or winner as defined by the competition rules.

Bible Challenge requires special treatment because a game may have three teams, the top teams advance based on cumulative score, and semifinals and finals also use three-team games.

### 9.4 Placement or measured result

A fully measured result type (heats, attempts, times, distances) is **out of scope for 2026**. Track & Field — the event that would have needed it — instead uses the simple final-placement form in §9.5. Revisit only if a future season requires detailed meet management.

### 9.5 Track & Field final-placement events

**Scope decision (2026-07-10):** Track & Field is modeled as a container of six individual events, not one competition. For 2026, the system does **not** model heats, lanes, qualifying rounds, or race operations — T&F staff handle those manually on the field. The digital record exists for medal preparation and accurate closing-ceremony announcements only.

The six events:

1. Women 100m
2. Men 100m
3. Women Half-Mile
4. Women 4x100m Relay
5. Men 4x100m Relay
6. Men Mile

Each event is its own row in `sf_schedules` with its own `game_key` (e.g. `TF-W100M`, `TF-M4X100`), its own QR code, and its own result record. The "Track & Field" category is only a display grouping, never a scoring entity — the data model must not hard-code T&F as one sport with one set of results.

The result form is a simple **final-placement entry**, per event:

- 1st place team/church;
- 2nd place team/church;
- 3rd place team/church;
- optional notes;
- optional scoresheet/photo attachment;
- submitted by / submitted at;
- official or under-review status.

This fits the existing data model without new machinery: placements go in `winner_keys_json` (ordered 1st→3rd), and the standard revision, attachment, and status flow from §§4.4, 8.2–8.4 applies unchanged. No `sub_event` hierarchy, participant lists, or measured-result fields are needed for 2026.

Background for context: T&F registrations live in the `Other Events` checkbox (not Primary/Secondary sport), are categorized `INDIVIDUAL`, and are not scheduled by the CP-SAT solver — so the six T&F rows will be entered via the schedule publication path as fixed-time entries rather than solver output.

**Tug-of-War** uses this same final-placement form: one fixed-time schedule row (`TF`-style, e.g. `TOW-MIXED`), public display of 1st/2nd/3rd place churches. Scripture Memorization is excluded from the 2026 results system.

## 10. Sport Rules Configuration

Each Sport Coordinator should supply or approve a one-page rules configuration containing:

- result form type;
- whether ties are allowed;
- points awarded for wins, losses, or ties;
- ranking metrics;
- tiebreaker order;
- number advancing;
- semifinal mapping;
- final mapping;
- result certification authority;
- correction authority.

Automatic standings should be enabled only when the governing rules are confirmed in writing.

## 11. Security Model

**Decision (2026-07-11):** Use restricted individual WordPress coordinator accounts for the 2026 release. SMS magic-link authentication (via WSMS) was considered as an alternative but is deferred — the setup and gateway integration risk is too high this close to the event. QR codes on scoresheets will link directly to the match result form; coordinators log in with their WordPress credentials.

Each submission should require:

- HTTPS;
- authenticated WordPress user;
- Sports Fest write capability;
- WordPress nonce;
- authorization for the match's sport;
- validation that the match belongs to the currently published schedule version.

User metadata may store the sports each coordinator is authorized to manage.

The existing role and capability names may remain unchanged for this release even though they contain the older `sf2025` label. Renaming capabilities immediately before the event would add unnecessary migration risk.

## 12. Mobile Coordinator Interface

Provide a front-end, phone-friendly coordinator page rather than requiring normal WordPress administration screens.

Primary views:

1. `Needs Result`
2. `Reported Today`
3. `All My Matches`

Each match card should show:

- Game ID;
- teams or participants;
- scheduled time;
- location;
- current status;
- result-entry button;
- scoresheet scan status.

The result screen should use large controls, minimal typing, and clear confirmation before submission.

## 13. Scoresheet File Handling

Accepted initial formats:

- JPEG;
- PNG;
- PDF.

Suggested mobile file input:

```html
<input type="file" accept="image/jpeg,image/png,application/pdf" capture="environment">
```

Requirements:

- validate MIME type and file size (maximum 32 MB, the practical Bluehost limit);
- generate a safe server filename;
- calculate SHA-256;
- store outside normal public browsing where practical;
- require authorization for downloads;
- never expose scans on public result pages;
- allow a scan to be attached after the result is submitted;
- show missing scans on the Results Desk dashboard.

Storage split (decided 2026-07-11): blank scoresheets are generated to **Google Drive**; digital scoresheet scans collected from staff are archived to **Dropbox**; WordPress remains the operational store for submitted results and attachments. Paper and digital records are disposed of **6 months** after the event.

## 14. Public Display

Proposed shortcodes:

- `[vaysf_live_schedule]`
- `[vaysf_standings]`
- `[vaysf_advancement]`

Public presentation should support:

- now playing;
- recently completed;
- coming next;
- filters by sport, day, and venue;
- reported or official scores;
- pool standings;
- confirmed semifinalists and finalists;
- last-updated timestamp;
- automatic refresh every 20 to 30 seconds.

Public REST responses must exclude:

- scoresheet file paths;
- coordinator identities;
- internal notes;
- revision history;
- private dispute information.

## 15. Results Desk Dashboard

The central dashboard should surface:

- matches past their scheduled end time without results;
- reported results awaiting verification;
- official results missing a scoresheet scan;
- duplicate or conflicting submissions;
- corrected results;
- disputed results;
- pools with all matches complete;
- advancement awaiting confirmation;
- public data last-updated status.

## 16. Reliability and Offline Fallback

The process must remain usable when cellular or Wi-Fi service is weak.

Fallback procedure:

1. Continue completing paper scoresheets.
2. Collect completed sheets at the sport table or Results Desk.
3. Enter delayed results when connectivity returns.
4. Preserve the actual match completion time separately from the later data-entry timestamp.
5. Use the paper sequence and Game ID to reconcile any duplicate submissions.

No match should be delayed solely because the digital system is unavailable.

## 17. Rapid Delivery Plan

### Day 1 - Data and schedule foundation

- Confirm MVP sports and rules.
- Upgrade WordPress tables.
- Add schedule import endpoints.
- Build `publish-schedule --dry-run` and `--execute`.
- Import a test schedule.
- Create Sport Coordinator accounts and assignments.

### Day 2 - Result submission

- Build the mobile coordinator page.
- Implement simple-score, set-based, and multi-team forms.
- Add certification and append-only revision history.
- Add scoresheet upload.
- Build initial Results Desk status page.

### Day 3 - Public display and advancement

- Add live schedule and result shortcodes.
- Add public read-only result API.
- Implement confirmed standings for highest-priority sports.
- Add provisional advancement and human confirmation.
- Generate QR codes for paper scoresheets.

### Day 4 - Rehearsal and hardening

Simulate a mini-tournament and test:

- normal score submission;
- simultaneous submissions;
- duplicate submission;
- wrong score correction;
- missing scan and later upload;
- disputed result;
- tied standings;
- advancement confirmation;
- schedule revision;
- offline paper fallback;
- public display on iPhone and Android;
- final audit export.

## 18. Implementation Issues

The following issues should be created as sub-issues of a tracking Epic once the remaining open decisions (§19) are resolved. Each issue is scoped to be independently shippable and testable.

### Issue 1 — `results: redesign schedule/results schema and publish-schedule command`

Redesign the existing `sf_competitions`, `sf_schedules`, and `sf_results` tables (currently empty and unused) to support the data model in §8. Add the new `sf_result_revisions` and `sf_result_files` tables. Key columns: `game_key` (maps to scheduler `game_id`), `schedule_version`, `game_status`, `score_json`, `winner_keys_json`, `current_revision`, `sub_event` (for T&F hierarchy). Build the `publish-schedule --dry-run` and `--execute` middleware commands (§7) that load `schedule_output.json`, diff against the current WordPress state, and upsert matches by stable `game_key`. Refuse to overwrite completed matches. Include a `--force-cancel` flag for marking removed future games as cancelled rather than deleting them.

**Schema design note:** Track & Field needs nothing special — each of the six T&F events (§9.5) is an ordinary `sf_schedules` row with a `TF-` game_key, entered as a fixed-time entry rather than solver output. The `team_ids_json` column handles variable participant counts (2 for basketball, 3 for Bible Challenge).

**QR code coordination:** The badge pipeline (#184–#188) already generates person-ID QR codes for athlete check-in. This issue must define the match-QR payload format so scanners can distinguish person QRs from match QRs. Suggested: person QRs use `CHM:<person_id>`, match QRs use `MATCH:<game_key>`.

**Dependencies:** None — this is the foundation issue. Must land before Issues 2–6.

### Issue 2 — `results: add coordinator accounts, sport authorization, and mobile submission`

Create restricted WordPress coordinator accounts with per-sport authorization stored in user meta (§11). Build the mobile coordinator interface (§12): `Needs Result`, `Reported Today`, `All My Matches` views. Implement the three MVP result form types (§9.1 simple score, §9.2 set-based, §9.3 multi-team). Each submission records submitter, timestamp, schedule version, certification flag, and creates an append-only revision in `sf_result_revisions` (§4.4). Corrections require a reason and create a new revision without deleting history. A match may be flagged `Under Review` if a correction affects standings.

**Scope for 2026 MVP:** Basketball (simple score), Soccer (simple score), Volleyball Men/Women (set-based — best of 3 or 5 sets). Bible Challenge (multi-team) may be included if time permits.

**Dependencies:** Issue 1 (schema and published schedule must exist).

### Issue 3 — `results: add protected scoresheet file upload and archive`

Implement secure file upload for JPEG/PNG/PDF scoresheets (§13). Files are stored outside the public web root, require authorization to download, and are associated with a specific result revision in `sf_result_files`. Calculate SHA-256 on upload. Allow scans to be attached after the result is submitted (scan status: `pending`, `uploaded`, `verified`). A failed upload must never block or erase a valid score submission.

**Dependencies:** Issue 2 (result revisions must exist to attach files to).

### Issue 4 — `results: add public live schedule, results, and standings display`

Build the public-facing shortcodes: `[vaysf_live_schedule]`, `[vaysf_standings]`, `[vaysf_advancement]` (§14). Support filtering by sport, day, and venue. Show now-playing, recently-completed, and coming-next sections. Auto-refresh every 20–30 seconds. Public REST endpoints must exclude scoresheet paths, coordinator identities, internal notes, and revision history. Display reported results immediately with a visual indicator (red highlight) when multiple submissions have discrepant scores — show the average per the owner's decision.

**Dependencies:** Issue 1 (published schedule) and Issue 2 (submitted results).

### Issue 5 — `results: add standings calculation and advancement confirmation`

Implement provisional standings calculation for configured sports (§10). Standings are calculated automatically when all pool matches have results, but advancement to semifinals/finals requires explicit human confirmation by an authorized coordinator or Results Desk administrator (§4.5, §6.3). If a post-advancement correction changes the qualifiers, previously confirmed advancement is reset and must be re-confirmed. Automatic standings should be enabled only for sports whose ranking metrics and tiebreak rules are confirmed in writing (per the Sports Fest Handbook).

**2026 scope:** No automatic standings for the first version (per owner decision). The infrastructure should exist so standings can be enabled per-sport via configuration once the rules are confirmed.

**Dependencies:** Issue 2 (results must exist to calculate standings from).

### Issue 6 — `results: add Results Desk dashboard and event archive export`

Build the central Results Desk dashboard (§15) showing: overdue matches, unverified results, missing scans, duplicates/conflicts, corrections, disputes, pools awaiting advancement confirmation, and a last-updated heartbeat. Add an event archive export that bundles result manifests and optionally scoresheet files for the VAY shared drive (§13).

**Dependencies:** Issues 2–5 (needs results, files, and standings data to monitor).

### Issue 7 — `results: add Track & Field and Tug-of-War final-placement entry`

Add the six T&F events plus Tug-of-War (§9.5) as fixed-time schedule rows and a simple final-placement form: 1st/2nd/3rd church, optional notes, optional attachment. Reuses the standard revision, attachment, and status flow — no heats, lanes, or measured results. Small enough to ship alongside or immediately after Issue 2.

**Dependencies:** Issue 1 (schema), Issue 2 (submission flow).

## 19. Open Decisions for Review

### Resolved

1. **Which sports must be included in the first event-day release?** Basketball, Soccer, Volleyball Men, Volleyball Women.
2. **Which sports require automatic standings before the first weekend?** None for the first version. Infrastructure will exist to enable per-sport once tiebreak rules are confirmed.
3. **What are the official ranking and tiebreak rules for each included sport?** Defined in the Sports Fest Handbook. Must be transcribed into the sport rules configuration (§10) before standings are enabled.
4. **Should a coordinator submission immediately be public as `Reported`, or remain private until Results Desk verification?** Yes, show publicly. When multiple submissions have discrepant scores, display the average and flag in red.
5. **Who may confirm advancement for each sport?** Decided by a human (Sport Coordinator or Results Desk administrator) on a case-by-case basis.
6. **Is a scoresheet image required for every match?** No. The scoresheet QR leads to the web result form; the scan is optional supporting evidence, not a gate.
7. **Security model?** Restricted WordPress coordinator accounts (decided 2026-07-11). SMS magic-links deferred.
8. **Track & Field?** Six individual events with final medal placements only (1st/2nd/3rd church) — no heats, lanes, or race operations (§9.5, decided 2026-07-10).
9. **Maximum upload size on Bluehost?** 32 MB.
10. **File storage?** Blank scoresheets are generated to Google Drive. Digital scoresheet scans collected from staff are archived to Dropbox. WordPress remains the operational store for submissions.
11. **Tug-of-War and Scripture Memorization?** Tug-of-War gets a public display of 1st/2nd/3rd place churches, using the same final-placement form as Track & Field (§9.5). Scripture Memorization is excluded from the 2026 results system entirely.
12. **Who operates the Results Desk?** The Sports Fest administrator (Bumble) staffs it directly.
13. **Schedule revisions?** No pre-event revision workflow. If the schedule changes before Sports Fest starts, re-run `publish-schedule` to reload the tables. Once matches begin, the §7 protections apply (completed matches are never overwritten; removed games are cancelled, not deleted).
14. **Retention period?** Paper and digital records are disposed of 6 months after the event.

All open decisions are now resolved. Implementation issues (§18) may be created.

## 20. Acceptance Criteria for the MVP

The MVP is ready for live use when:

- a published schedule can be imported without changing completed matches;
- every included match has a stable Game ID;
- an authorized coordinator can submit a result from a phone;
- unauthorized users and coordinators from another sport cannot submit that result;
- every correction creates a visible audit revision;
- a JPEG, PNG, or PDF scoresheet can be attached securely;
- public pages show current schedule and scores without exposing private data;
- provisional standings recalculate correctly for configured sports;
- advancement requires explicit authorized confirmation;
- Results Desk can identify missing, late, disputed, corrected, or scan-pending results;
- the full process succeeds in an end-to-end rehearsal using the paper fallback.
