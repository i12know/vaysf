# VAYSF Pre-2026 Retrospective

## Before The Agents, There Was The Clipboard

The pre-2026 story of `vaysf` is not mainly a story about automation. It is a story about escaping manual repetition one painful workflow at a time.

Before the 2026 buildout, Sports Fest operations were still carried heavily by human memory, ChMeetings screens, copied fields, exported spreadsheets, pastor emails, and local Excel review. The system that appeared in March 2025 did not replace that world all at once. It wrapped around it. It made the manual work more visible, more repeatable, and a little less dependent on Bumble remembering every edge case at 1:00 AM.

That matters because the 2025 codebase was not immature in a careless way. It was early in a very specific way. It was still close to the lived process. Columns were added because a Church Rep needed to see them. Commands were added because one participant needed debugging. Pagination was fixed because one church was missing people from approval emails. Approval tokens were regenerated because real pastors were clicking expired links.

The system learned Sports Fest by following the smoke.

## Act 1: The Paper Process Became A Shape

The first versions in March 2025 were architecture before they were machinery. Version 0.1 described an eleven-table WordPress model, core workflows, security considerations, and future enhancements. Version 0.2 immediately simplified the schema from eleven tables to eight and anchored the design in actual CSV structures and ChMeetings field mappings. Version 0.3 added Windows setup, implementation phases, and more detailed database definitions.

This was already a sign of the project taking its first serious step away from copy and paste. The work was not yet "the system runs everything." It was "we can finally name the things Bumble has been carrying manually."

The early architecture had the same three-tier skeleton the 2026 system still uses:

- ChMeetings for registration and profile data.
- Python middleware on Windows for synchronization and validation.
- WordPress on Bluehost for operational staff workflows.

That architecture was strong enough to survive the following year. But in 2025 it was still being filled with the artifacts of a manual operation: forms, CSV-like field assumptions, Excel workbooks, ChMeetings exports, approval emails, and WordPress tables that existed because people needed a place to see what had previously lived in scattered spreadsheets.

The first lesson of the pre-2026 era was that before you automate a ministry workflow, you have to make the hidden workflow visible.

## Act 2: WordPress Became The Approval Desk

Version 0.4 moved email notifications from Python to WordPress, shifted token generation into WordPress, added an email log table, and leaned on WP Mail SMTP for delivery. This was a major design decision disguised as implementation detail.

It said: pastor approval is not a local script concern. It belongs where pastors and staff interact with the event.

That decision gave Sports Fest a durable approval surface. Pastors could approve through tokenized email links. Staff could track status in WordPress. Approval records could be synced back toward ChMeetings. The workflow was still fragile, but it had a home.

The first production issue confirmed the fragility. On April 2, 2025, issue #1 fixed the case where clicking Approve from the pastor approval email led to an error screen. That kind of bug is humbling because the data model can be reasonable, the code can mostly exist, and the whole workflow can still fail at the one moment a pastor interacts with it.

This became a recurring pre-2026 pattern: the system was right enough to expose the next real failure.

## Act 3: Validation Started As Translation

Versions 0.5 through 0.9 turned validation from scattered judgment into structured rules.

Version 0.5 introduced `church_code` as the human-readable identifier. That was not just cosmetic. It aligned the system with how operators and church reps actually think. Bumble does not run Sports Fest by internal database IDs; he runs it by church codes like `NHC`, `RPC`, and `ORN`.

Version 0.6 added pytest, mock testing, live/mock toggles, and connector error handling. Version 0.7 added `sf_rosters` and began syncing participants into sport-specific roster entries. Version 0.8 brought Pydantic and stronger data mapping. Version 0.9 made validation JSON-driven, with severity levels and contextual issue reporting.

In hindsight, this is where the project began to encode the Sports Fest handbook into software. But it did not happen as a clean abstraction exercise. It happened because manual review needed help. The software had to answer questions that humans had previously answered by scanning forms and spreadsheets:

- Is this participant old enough?
- Is this person a church member?
- Which church owns this roster row?
- Is this a team sport or individual event?
- Does this issue block approval or simply need review?
- Can Church Reps see the problems clearly enough to help fix them?

The second lesson was that validation is not merely correctness. In this system, validation is communication between staff, pastors, church reps, and the registration source of truth.

## Act 4: The 1.0 Big Bang

On March 28, 2025, the 1.0 release arrived as a large release-candidate commit: roughly 9,200 inserted lines across middleware sync, participant sync, validation tests, WordPress REST endpoints, admin UI, shortcodes, pastor approval templates, and the plugin ZIP.

It was a big bang. The repo went from plan and scaffolding into a working bridge.

The 1.0 system had the recognizable shape of the modern codebase:

- `middleware/sync/manager.py` and `middleware/sync/participants.py` for orchestration.
- `middleware/validation/Summer_2025.json` and validator classes for rules.
- WordPress REST API and admin pages for churches, participants, rosters, approvals, and validation issues.
- Mock ChMeetings fixtures and early unit tests.
- A distributable `plugins/vaysf.zip`.

It is tempting to look back from 2026 and see only what was missing: no scheduling pipeline, no Results Desk, no coordinator score entry, no badge system, no event-day state archive, no mature API-first ChMeetings discipline. But that would miss the real accomplishment.

The 1.0 release created a shared memory surface. Sports Fest could now say, "This participant is here. This church owns them. These are their sports. These are their validation issues. This pastor approval is pending. This roster row exists."

That was a massive move away from copy/paste operations.

## Act 5: ChMeetings Was Still A Mixed World

The early ChMeetings connector explicitly supported both API and Selenium integration. Church sync still came from Excel. Group assignment was introduced in May 2025, but the broader ecosystem still carried the smell of manual exports and imports.

That was not a failure of imagination. It was the state of the available operating surface.

In 2025, the question was not yet "How do we eliminate every manual handoff?" The question was "Can we reduce enough manual handoffs that the event can be managed without losing track of people?"

So the code accepted hybrid reality:

- ChMeetings remained the core person store.
- WordPress became the approval and operations layer.
- Python moved data between them.
- Excel remained the language of review, audit, and church-rep communication.
- Selenium and browser-adjacent workflows existed because not every desired operation had a clean trusted API path yet.

The third lesson was pragmatic: the first bridge out of manual work often has to touch the manual artifacts. You do not get to start in the clean future. You start where the operators are standing.

## Act 6: The Debugging Became Personal

May 2025 reads like a production diary.

Issue #4 fixed pending approval status with James. The solution removed a bad WordPress pagination assumption, copied `approval_status` from `sf_approvals` into `sf_participants`, and prevented participant sync from overwriting that status. Issue #12 fixed minors not appearing for pastoral approval because consent errors were not getting updated. Issue #23 fixed partner names not being recorded on `sf_roster`.

These are not abstract bugs. They are the names and workflows that make a system real.

The single-participant sync command appeared in this phase too:

```bash
python main.py sync --type participants --chm-id <CHMEETINGS_ID>
```

That command is small but historically important. It means the project had crossed into production debugging. Bumble no longer needed to rerun the whole universe just to investigate one person. The system could aim a flashlight at one participant.

The fourth lesson was that good operations software needs narrow repair tools, not only broad sync commands.

## Act 7: Excel Became The Human Interface

Issue #18 added `export-church-teams`, generating Excel files to help Church Reps review their teams. This was one of the defining pre-2026 features.

From a pure software architecture perspective, Excel can look like technical debt. In the 2025 context, it was also mercy. Church Reps did not need a perfect admin portal; they needed a workbook they could inspect, annotate, forward, compare, and understand.

The export grew in exactly the way operator workbooks grow:

- Church-specific roster views.
- Validation issues.
- Partner-name hints.
- Summary counts.
- `Is_Member_ChM` and `Photo` columns.
- Auto filters.
- A `Total Denied` column.
- Sorting by church team, sport type, gender, and name.
- Notes about Excel's `IMAGE()` behavior.

This is the part of the story where "manual copy and paste everywhere" began turning into "at least the copy and paste has a generated source." It did not make Excel disappear. It made Excel less dangerous.

The fifth lesson was that Excel was not merely a workaround. It was the operating language of the volunteer network. The system had to speak it before it could gently reduce dependence on it.

## Act 8: Pastor Approval Became Operationally Real

The pastor approval workflow matured through pain.

Version 1.03 fixed a pagination bug where not everyone from NHC appeared in pastoral approval emails. It also fixed a membership display bug where non-members appeared as "Yes" for church membership. Version 1.04 fixed expired-token resend behavior, added fresh token generation, added Sports Fest start date inclusion in email, and introduced mass pastor approval email sending during roster export.

This sequence says a lot about the pre-2026 operating model. Approval was not a static form. It was a live communication workflow:

- Staff needed to send and resend.
- Pastors needed valid links.
- Participants needed accurate membership status.
- Church teams needed summary counts.
- The system needed to distinguish "not sent," "pending," "approved," "denied," and "synced."

The sixth lesson was that email workflows are state machines, whether the code admits it at first or not.

## Act 9: The Edge Cases Became Policy Signals

The last pre-2026 commits in July 2025 look small, but they reveal where Sports Fest rules were beginning to press against simple field mapping.

The "male athlete signed up for Women Volleyball" fix became smart gender mapping. That sounds like a bug, but it is also a policy/data boundary. The form data, sport labels, participant gender, and roster assignment logic all had to agree. When they did not, the system needed to do something more intelligent than copy a string from one place to another.

Other fixes were similarly revealing:

- Partner names were not just display text; they affected roster validity.
- Minor consent was not just a warning; it affected pastoral approval visibility.
- Membership status was not just a checkbox; it affected trust and eligibility.
- Pagination was not just an API detail; it determined whether entire churches appeared in pastor emails.
- Approval status duplication between tables was not just denormalization; it was needed for staff-facing views to remain coherent.

The seventh lesson was that every "small" data bug was actually a discovered invariant.

## What Held

- The three-tier architecture held from the beginning.
- WordPress was the right place for pastor approval and staff-facing operations.
- Python middleware was the right place for local orchestration, validation, and report generation.
- ChMeetings was correctly treated as the core person-registration system.
- JSON/Pydantic validation gave the project a durable path away from scattered manual rule checks.
- Early pytest/mock fixtures made later API and validation refactors possible.
- Excel exports helped church reps participate in cleanup without requiring them to learn the internals.

## What Bent

- Selenium/API hybrid assumptions were fragile and eventually had to be replaced in 2026.
- Excel was useful, but it also preserved manual handoff habits.
- Approval status lived in multiple places because the UI needed it, creating sync risks.
- ChMeetings field names and response shapes were still too implicit.
- Pagination bugs showed that "works for one page" was not enough for real churches.
- Debugging often depended on specific people and one-off operational knowledge.
- Release history was practical but messy: direct commits, terse messages, and tactical fixes mixed with durable architecture.

## What We Learned

1. The first step away from manual work is not full automation. It is faithful capture of the real workflow.
2. Excel was a bridge, not just debt. It met church reps where they were.
3. Named-person bugs are valuable. They reveal whether abstractions actually fit real ministry operations.
4. Approval, consent, membership, and eligibility are connected. Treating them as separate checkboxes creates hidden risk.
5. Pagination, field mapping, and API response shapes are operational concerns, not low-level details.
6. Narrow debug commands are essential when production data comes from real people.
7. A working system can be born from manual artifacts, but it should not stay dependent on them forever.

## How This Set Up 2026

The pre-2026 codebase gave 2026 a foundation strong enough to extend.

Because WordPress already had approval tables, REST endpoints, admin pages, and pastor-token handling, 2026 could build richer operational surfaces instead of starting from scratch. Because middleware already had sync managers, ChMeetings and WordPress connectors, validators, and tests, 2026 could migrate to API-first behavior instead of inventing orchestration. Because `export-church-teams` already existed, 2026 could expand workbooks into scheduling inputs, badge inputs, score-sheet inputs, and diagnostic artifacts.

But the pre-2026 codebase also left 2026 with the right list of problems:

- Remove Selenium from production paths.
- Replace manual ChMeetings group imports with API calls.
- Centralize ChMeetings field names.
- Make pagination robust.
- Treat Excel as export/audit/fallback, not source of truth.
- Build stronger identity and trust models.
- Turn scheduling from a spreadsheet art into structured data plus human judgment.

In that sense, 2025 was not the primitive version of 2026. It was the seedbed. It preserved the operational truth that later automation needed to respect.

## Closing Reflection

Before 2026, `vaysf` was still very close to the hands that ran Sports Fest. You can see the copy/paste world in the seams: Excel import, Excel export, ChMeetings screens, expired approval links, manual group assignment, one-person debugging, workbook columns, and field labels that mattered because someone had to read them under pressure.

That closeness was inconvenient, but it was also honest. The system learned the real tournament before it tried to optimize it.

The 2026 system became more agentic, more automated, and more ambitious because the 2025 system first became legible. It turned scattered manual effort into tables, commands, reports, tokens, rules, and logs. Once the manual world had a shape, the next season could start replacing pieces of it with structure.

That is the pre-2026 arc: not from bad to good, but from invisible labor to visible workflow. The codebase did not yet know how to run Sports Fest. It was learning how Sports Fest was actually run.
