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

Examples: Track and Field or other individually measured events.

Capture:

- participant or team;
- heat or attempt;
- time, distance, or score;
- placement;
- qualification status.

This form type may be deferred if the first rollout focuses on scheduled head-to-head and Bible Challenge games.

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

For the rapid 2026 rollout, use individual WordPress accounts rather than shared passwords or anonymous result links.

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

- validate MIME type and file size;
- generate a safe server filename;
- calculate SHA-256;
- store outside normal public browsing where practical;
- require authorization for downloads;
- never expose scans on public result pages;
- allow a scan to be attached after the result is submitted;
- show missing scans on the Results Desk dashboard.

A nightly archive process may copy result manifests and scoresheet files into the VAY shared drive as a secondary archive.

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

## 18. Suggested Implementation Issues After Approval

1. `results: import and freeze published schedule in WordPress`
2. `results: add secure mobile coordinator submission and score revisions`
3. `results: add protected scoresheet archive`
4. `results: add public live schedule and results display`
5. `results: add sport standings and advancement confirmation`
6. `results: add Results Desk monitoring and archive export`

These issues should be created only after this RFC is reviewed and the open decisions below are resolved.

## 19. Open Decisions for Review

1. Which sports must be included in the first event-day release?
2. Which sports require automatic standings before the first weekend?
3. What are the official ranking and tiebreak rules for each included sport?
4. Should a coordinator submission immediately be public as `Reported`, or remain private until Results Desk verification?
5. Who may confirm advancement for each sport?
6. Is a scoresheet image required for every match, or required only before final archive completion?
7. What maximum upload size is practical on Bluehost?
8. Should files remain only on WordPress or also be copied nightly to Google Drive or Dropbox?
9. How should unscheduled events, individual events, and placements be represented in the same public interface?
10. Who will operate the central Results Desk during each venue block?
11. How should schedule revisions be approved once matches have begun?
12. What retention period is required for paper sheets, digital scans, and result revision history?

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
