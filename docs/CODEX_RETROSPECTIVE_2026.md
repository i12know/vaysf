# VAYSF 2026 Retrospective

## From Registration Bridge To Event Operations

Sports Fest 2026 was the season when `vaysf` crossed a threshold. It began the year as a production bridge between ChMeetings and WordPress: pull registrations, validate participants, route pastor approvals, build rosters, and sync approval state back to ChMeetings. By the end of July, it had become something larger and more demanding: an event-operations system.

That expansion was not theoretical. The codebase grew to support scheduling, solver inputs, manual schedule overrides, printable score sheets, athlete badges, hosted badge images, public live schedules, coordinator score entry, Results Desk review, playoff advancement, Bible Challenge verse management, proof-of-insurance intake, and post-event archival questions. The system did not become generic; it became more specifically VAY Sports Fest shaped.

The story of 2026 is the story of moving from fragile manual bridges toward structured operational truth, while learning exactly where that truth did and did not exist yet.

## Act 1: Escaping Fragility

The first major movement of 2026 was the ChMeetings API migration. The project had already proven its value in 2025, but parts of the workflow still leaned on workarounds that were too fragile for a second season.

The 2026 API upgrade changed that posture. Selenium was removed from production sync paths. ChMeetings group assignment and approval sync moved to direct API calls. Pagination was repaired around `total_count`. The `CHM_FIELDS` mapping became the central guard against field-name drift. The field inspector became part of the release discipline. API failures, 404s, 429s, and malformed payloads became things the system could observe and handle instead of mysteries that surfaced as broken spreadsheets.

This was the season's first lesson: production ministry software cannot depend on hope, screenshots, or manual import rituals when an API path exists. The system needed to become boring in the places where operators most needed it to be reliable.

## Act 2: Preparing The Season

Once the API foundation stabilized, the work turned to season preparation. Dates, deadlines, event names, age rules, Table Tennis 35+, Soccer Coed Exhibition, athlete fees, team-group clearing, season reset, and church export logic all had to be made current for 2026.

This phase was less glamorous than scheduling or live scoring, but it mattered deeply. It exposed how many operational assumptions live in small corners: whether a deadline is inclusive, whether a ChMeetings option ID is current, whether a form row maps to a real Person, whether a stale team-group membership returns 404, whether an export row represents current-season reality or old tenant residue.

The codebase responded by adding audit commands, targeted sync paths, consent checks, orphan detection, repair workflows, and richer Excel reports. The Church Team export became not just a report but a diagnostic instrument. It told staff where the data was trustworthy, where it was stale, and where human review was still needed.

The second lesson was simple: data cleanup is not administrative overhead. For Sports Fest, data cleanup is event preparation.

## Act 3: Scheduling Became The Monster

Scheduling became the dominant engineering problem in May and June. What started as venue estimation and schedule workbook tabs grew into an OR-Tools CP-SAT pipeline, `schedule_input.json`, `schedule_output.json`, gym-mode allocation, venue windows, pool assignments, playoff pins, conflict edges, manual overrides, master schedule imports, and Excel/PDF publication workflows.

The project learned that Sports Fest scheduling is not just "place games into slots." It is a negotiation between registration demand, venue geometry, sport-specific formats, shared-athlete conflicts, church constraints, coordinator preferences, leadership events, meals, ceremonies, setup/teardown, and the human scheduler's final authority.

The solver proved valuable, but the season also proved that the operator interface was too scattered. The authoritative schedule was ultimately assembled through a mix of generated workbooks, manual Excel edits, coordinator PDFs, importer audits, sidecar JSON, and rerun chains. The engine improved faster than the cockpit.

That is why the 2027 Scheduling Helper PRD exists. It is not an indulgent GUI idea. It is the natural conclusion of the 2026 scheduling experience: the system needs a structured authoring surface where humans remain authoritative but their decisions become typed data instead of forensic clues in colored cells.

The third lesson was that automation can assist complex scheduling, but only when the human decisions are captured in a structure the system can understand.

## Act 4: Identity And Trust Got Real

The season also exposed a deeper problem: a participant is not just a row.

People registered for themselves, for children, through different forms, with different names, with missing or stale ChMeetings profiles, with merged records, with profile photos missing, with church affiliations that changed, and with consent or approval state that could become invalid after identity-relevant changes. Some WordPress participant rows pointed at ChMeetings IDs that later returned 404 because profiles had been merged. Some form-created people needed repair. Some "Other" church applicants needed to be routed to Lost and Found. Some Church Rep actions raised trust questions around membership status and eligibility.

This produced the Identity & Registrant Trust work: canonical person IDs, alias maps, duplicate detection, registrant roles, contact verification, minor consent, guardian relationships, and eventually the idea of a Person Resolution Gate before creating new ChMeetings people.

The project learned that duplicate prevention is better than duplicate repair, but prevention depends on having the right intake model. It also learned that policy, pastoral trust, and software state are intertwined. A bad identity match is not just a technical inconvenience; it can affect approval, eligibility, consent, badges, rosters, and event-day accountability.

The fourth lesson was that trust is a data model, not just a human virtue. If the system does not represent roles, relationships, and verification clearly, operators have to carry that ambiguity in their heads.

## Act 5: WordPress Became The Event-Day Arena

In July, the center of gravity shifted sharply toward WordPress. The plugin had always been the staff-facing surface, but event-day requirements turned it into an operational arena.

The system gained coordinator accounts, schedule-driven sport authorization, mobile-friendly score entry, volleyball set scoring, Bible Challenge scoring, protected score-sheet uploads, public live schedules, public results display, Results Desk status views, pool progress review, advancement confirmation, playoff previews, QF apply flows, Bible Challenge semifinal setup, manager playoff placement tools, and front-page advancement displays.

This was the season when WordPress became the place where the tournament lived during the event. ChMeetings remained the source of registration truth. The middleware remained the orchestrator and generator. But WordPress became the live operations board: what is scheduled, what is scored, what is missing, what is public, what needs review, what can advance.

The plugin also changed structurally under pressure. Large REST and admin files were split into domain modules. PHP lint tooling was added. Cache guards and no-cache headers appeared because hotfixing live event screens taught the system that stale admin pages are not harmless.

The fifth lesson was that event-day software must treat UI state, permissions, cache behavior, and recovery paths as operational safety features, not polish.

## Act 6: The Event Taught The System Its Limits

The final week before and during Sports Fest was intense. The system had enough structure to be useful, but live tournament reality kept adding specificity.

Basketball and Volleyball tiebreak rules had to match coordinator spreadsheets and handbook interpretation. Volleyball ranking needed rally-game records and set-point details. Basketball Difficulty of Schedule had to be corrected. Bible Challenge semifinal grouping had to respect the actual 2026 coordinator artifact, even while preserving a possible 2027 RFC about snake seeding. Playoff rows needed placeholders, schedule version guards, stale-page warnings, public advancement refresh behavior, and manager-controlled venue/time placement.

These were not random hotfixes. They were the system learning the tournament's real rules under time pressure.

The Track & Field experience revealed an equally important boundary. The code shipped final-placement plumbing for Track & Field and Tug-of-War rows, but Track & Field itself could not become first-class digital workflow because the upstream source of truth did not exist. Most actual Track & Field participation happened on site or on paper. Only a small fraction appeared through the online form. Without structured sub-event signup before event day, the system cannot responsibly generate start lists, heats, lanes, schedules, or automated result rows.

The sixth lesson was the cleanest one of the season: automation only works where the source of truth exists. Where the source is structured, the system can help. Where the source is paper, memory, or hallway coordination, the system must either stay manual or first solve intake.

## Act 7: Post-Event Clarity

After the event, the backlog became clearer.

Some work is truly complete: the 2026 event-day results epic, Results Desk, advancement confirmation, public display, final-placement plumbing, protected uploads, score sheets, and many live playoff hotfixes.

Some work is real post-event repair: stale WordPress participant rows after ChMeetings profile merges, approved-athlete stat mismatches, PHP REST behavior tests, dependency cleanup, source/zip drift checks, and remaining release discipline.

Some work is 2027 design: the Scheduling Helper, identity and registrant trust, Track & Field structured sub-event signup, eligibility-category policy, playoff and tiebreak RFCs, Bible Challenge seeding policy, and a more explicit Admin Manual.

This is a healthier backlog than the one that existed before the event. It no longer says only "build more things." It says where the system held, where the system bent, where human policy must lead code, and where better source data must exist before automation is honest.

## What Held

- The three-tier architecture held: ChMeetings for registration, middleware for orchestration, WordPress for operations.
- The API-first migration held; production sync did not regress back to Selenium.
- Mock-mode testing became a real safety net, with hundreds of tests covering critical middleware behavior.
- The WordPress plugin could absorb live event-day responsibilities without abandoning its boundary with middleware.
- The schedule pipeline produced reusable contracts and artifacts even when final authority remained with human-edited schedules.
- The issue tracker became a useful operational memory, not just a bug list.

## What Bent

- Scheduling workflow bent under the weight of Excel handoffs, manual overrides, and artifact version tracking.
- WordPress plugin release discipline bent under hotfix pressure; version, zip, changelog, and tag discipline had to be repaired after the fact.
- Identity assumptions bent when ChMeetings merges, duplicate people, parent/child registration, and role ambiguity entered the workflow.
- Track & Field bent because the actual signup process was not digitally structured.
- Results and advancement logic bent where written rules, coordinator spreadsheets, and event-day interpretation diverged.
- Some plugin REST behavior still lacks automated test coverage.

## What We Learned

1. API-first is not just a technical preference. It is what makes the operation repeatable.
2. Excel is a useful interchange format but a poor long-term source of truth for complex event operations.
3. A solver is only as good as the structured constraints and human decisions fed into it.
4. Event-day UX is operational safety. Stale pages, unclear buttons, and hidden state can cause real mistakes.
5. Identity needs first-class modeling before 2027. Duplicate repair is not enough.
6. Track & Field cannot be automated until sub-event signup is structured before event day.
7. Policy decisions should precede code for eligibility, tiebreakers, advancement, and manual overrides.
8. The system should stay VAY-specific. Its value comes from fitting the real tournament, not pretending to be generic.

## 2027 Priorities Emerging From 2026

### 1. Scheduling Helper

Build a localhost GUI over the existing scheduling pipeline so operators can see freshness, edit structured inputs, validate moves, rerun the right chain, review discrepancies, and publish artifacts without memorizing CLI sequences.

### 2. Identity & Registrant Trust

Implement alias maps, duplicate detection, role-aware contact storage, minor consent improvements, and eventually a Person Resolution Gate before automated ChMeetings person creation.

### 3. Track & Field Intake

Decide whether Track & Field sub-event signup belongs in ChMeetings, WordPress, or a hybrid. Without structured sub-event entries before the event, Track & Field should remain manual/offline with post-event archival only.

### 4. Rules Governance

Resolve 2027 policy before implementation: eligibility categories, non-member/outreach framing, team-sport tiebreakers, Difficulty of Schedule formulas, byes, point-differential caps, Bible Challenge seeding, and who can approve manual overrides.

### 5. Release And Test Discipline

Add plugin REST tests, source/zip drift checks, dependency cleanup, and stricter release habits so event-week hotfixes do not leave confusing historical state behind.

### 6. Admin Manual

Consolidate ChMeetings manual operations, known limitations, duplicate-person gotchas, form submitter prerequisites, and operator workflows into one durable `ADMIN_MANUAL.md`.

## Closing Reflection

The 2026 season stretched `vaysf` hard, but it did not break the architecture. Instead, it revealed what the architecture is becoming.

The system is no longer merely a bridge between ChMeetings and WordPress. It is becoming a memory and coordination layer for Sports Fest: a place where registration, validation, scheduling, approval, scoring, advancement, and public communication can meet without depending entirely on one person's private spreadsheet logic.

That is both promising and sobering. The more the system can do, the more carefully it must distinguish between facts, assumptions, policies, and human decisions. The best version of `vaysf` will not remove human judgment from Sports Fest. It will make the places where human judgment is needed visible, auditable, and easier to act on.

Sports Fest 2026 showed that this is possible. It also showed exactly what needs to be built next.
