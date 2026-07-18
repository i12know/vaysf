# Architecture Review — Sports Fest 2026 (v1.12)

*Written 2026-07-18, the eve of Sports Fest 2026, as part of the pre-event
codebase cleanup. This review records the state of the system at tag `v1.12`,
a register of known technical debt (deliberately **not** fixed before the
event), a proposed triage of the GitHub issue backlog, and a post-event
roadmap. Nothing in this document changes runtime behavior.*

---

## 1. State of the system

The three-tier architecture — **ChMeetings** (source of truth for
registration) → **Python middleware on Windows** (orchestration, validation,
scheduling) → **WordPress on Bluehost** (staff/pastor operations) — has held
up well through its second season. What began as a registration/approval
bridge now also covers game scheduling (OR-Tools CP-SAT), athlete badges,
score sheets with a Bible Challenge verse bank, proof-of-insurance intake,
and season-reset tooling, without breaking the tier boundaries.

**What is healthy:**

- **API-first discipline held.** The v1.05/v1.06 Selenium removal stuck; all
  production sync paths are pure API. The one browser-automation survivor,
  `middleware/chrome_export_vaysf_forms.py` (Playwright), is now explicitly
  sanctioned in CLAUDE.md as a diagnostic-only operator tool, the same status
  as `--excel-fallback`.
- **Test coverage is substantial and honest.** 889 tests pass in mock mode
  with no network access; live tests are opt-in via `LIVE_TEST` and mutations
  additionally gated by `LIVE_MUTATION_TESTS`. Skips are all conditional
  guards, not disabled tests.
- **Secrets and PII hygiene are clean.** No credentials in the tree,
  `.env` correctly gitignored with a committed template, PII-bearing Excel
  files ignored by name, test fixtures synthetic. `middleware/logs/` ignored
  and empty in the repo.
- **The plugin ships from source.** `plugins/vaysf/` (full PHP source) and
  the distributable `plugins/vaysf.zip` are both committed and verified in
  sync at version **1.0.46** as of this review.
- **Validation stays JSON-driven** with Pydantic models, so rule changes are
  data edits plus a fixture, not code surgery.

**What drifted (fixed in this cleanup):** the release process. The repo had
tags only through v1.09, a CHANGELOG with two `Unreleased` sections and a
stranded post-v1.11 block, and a README two major versions stale. This
cleanup cut **v1.12** as the event release, backfilled tags `v1.10` and
`v1.11`, repaired the CHANGELOG structure, and refreshed README/CLAUDE.md.
The root cause — plugin builds and features landing without changelog/tag
discipline — is a process item; see §2.7.

---

## 2. Technical debt register

Deliberately deferred until after the event. Ordered by recommended
post-event priority. File:line references are as of tag `v1.12`.

### 2.1 `requirements.txt` contains the broken `uuid` package (quick win)

`middleware/requirements.txt:14` pins `uuid>=1.30` — a 2006-era PyPI package
that shadows the standard-library `uuid` module and **fails to build on
Python 3**, aborting `pip install -r requirements.txt` entirely on a fresh
machine (confirmed during this review). Existing operator machines with
already-provisioned environments are unaffected, which is why this went
unnoticed. Fix: delete the line; the stdlib `uuid` is what the code actually
imports. One-line change, but it touches the dependency manifest, so it was
kept out of the pre-event freeze.

### 2.2 Literal ChMeetings field strings bypassing `CHM_FIELDS`

CLAUDE.md's rule: any literal ChMeetings field string in middleware business
logic is a bug. Current violations (literals such as `"Church Team"`,
`"Primary Sport"`, `"Secondary Sport"`, `"My role is"`):

- `middleware/group_assignment.py:91, 98, 112, 124–125, 615–616, 904–905`
- `middleware/scoresheets.py:409, 428, 445, 460`
- `middleware/approval_drift_history.py:107, 127`
- `middleware/schedule_workbook.py:98, 131, 564, 716, 945, 977, 993–994` (and more)

Nuance: many of these read **Excel/DataFrame column headers** that happen to
be named after ChMeetings fields, so a ChMeetings rename would break them
indirectly (via the export) rather than directly. The right fix is probably
to extend the mapping in `middleware/config.py:209` (or a sibling
`EXPORT_COLUMNS` constant derived from `CHM_FIELDS`) so both API field names
and export column headers route through one place, then sweep the four
modules. The field inspector should then flag drift in one location.

### 2.3 `church_teams_export.py` is doing too many jobs

At 3,759 lines it mixes live ChMeetings/WordPress export, report formatting,
and scheduling delegation. It is the file most likely to absorb unrelated
changes and the hardest to review. Candidate split: export orchestration /
workbook formatting / scheduling hand-off. Do this early in the off-season
while the 2026 behavior is still fresh and the test suite (which covers it
heavily) can anchor the refactor.

### 2.4 Small code smells

- Bare `except:` with silent `pass` at `middleware/church_teams_export.py:3043`
  (column-width sizing) — narrow to the expected exception and log.
- `print()` instead of logging at `middleware/config.py:66` (directory-creation
  failure handler).
- Hardcoded default export path at `middleware/config.py:39`
  (`G:\Shared drives\...`) — env-overridable, but the default should live in
  `.env.template`, not code.

### 2.5 WordPress plugin/zip drift risk

Source (`plugins/vaysf/`) and distributable (`plugins/vaysf.zip`) are in sync
today (both 1.0.46), but nothing enforces this. A tiny check — CI or a
pre-release script comparing the zip's `vaysf.php` version header against the
source — would prevent silent drift. (The zip is Windows-built with
backslash entry names; a rebuild script would also normalize that.)

### 2.6 Test suite runtime and shape

`test_schedule_workbook.py` alone is 5,371 lines. The suite passes in ~90s,
which is fine, but the largest test files track the largest modules — the
§2.3 split should carry the tests with it.

### 2.7 Release process discipline (the root cause behind this cleanup)

Rules that would have prevented the drift this cleanup repaired:

1. Every plugin rebuild bumps the version **and** adds its changelog line in
   the same commit.
2. Every release gets its `git tag vX.YZ` at release time (CLAUDE.md already
   says this; it now has to actually happen).
3. `## Unreleased` is emptied into the version section when a release is cut
   — never left to accumulate a second time.

---

## 3. Issue triage proposal (43 open issues)

*Proposal only — no labels, closures, or milestones have been applied.
Numbers reference github.com/i12know/vaysf.*

### 3.1 Proposed milestones

| Milestone | Issues |
|---|---|
| **Sports Fest 2026 — event week** | #202 (epic), #207, #208, #209, #212, #293, #297, #299 |
| **Post-event 2026** (bugs + debt) | #66, #40, #176, #181, #228, #216, #218, #296, plus new issues from §2 |
| **2027 season prep** | #268, #270, #69, #45, #108, #109, #138, #155, #227, #187, #188 |
| **2027 Scheduling Helper** | #272 (epic), #273–#279 (spikes) |
| **Admin Manual** (documentation) | #11, #14, #27, #62, #74 |

### 3.2 The stale 2025 tail (#11–#45, untouched since the April bulk-update)

| # | Title (short) | Recommendation |
|---|---|---|
| #11 | Duplicate records across the Diocese | Keep, fold into **Admin Manual** — it documents a ChMeetings-side reality, not a code fix. |
| #14 | ChMeetings Admin Manual Override | Keep as the **anchor issue** for the Admin Manual consolidation (see §3.3). |
| #21 | TeamValidator / ChurchValidator multi-level validation | Close-or-confirm: church-level validation shipped in v1.10 (`middleware: add church validation` commit). Verify remaining scope; close if #270 supersedes it. |
| #26 | Sync just one church? | Likely satisfied by `--church-code` filters and `--chm-id` targeted sync. Verify and close with a pointer to USAGE.md. |
| #27 | Mis-linking parents/kids warning | Keep, fold into **Admin Manual**. |
| #31 | Membership status not resettable by Pastor | Re-scope post-event: partially addressed by the #78 membership-freeze work in v1.10. |
| #40 | Duplicate names in export-church-teams | Keep open as a real bug; retest against v1.12 exports, may already be fixed by later export rewrites. |
| #45 | Manual sport-editing cutoff at deadline | Keep for **2027 season prep** — candidate for a scheduled config flip rather than a manual admin step. |

### 3.3 Consolidations

- **Admin Manual:** #11, #14, #27, #62, #74 all describe manual ChMeetings
  admin procedures and gotchas. Recommendation: one `docs/ADMIN_MANUAL.md`
  authored post-event (much of the content already exists in the issue
  bodies), then close all five against it. #74 ("wish list hack" for
  form-notification emails) should be split out only if someone actually
  intends to build it.
- **Score-sheet verses:** #293 (one-page BC verse layout), #297 (feed
  generator from WordPress-managed verses), and #299 (rotate verse JSON into
  prayer verses) are one feature area; #297 is the architectural direction
  (WordPress as verse source of truth) and #299 is a sub-step of it.

### 3.4 Labeling gaps

Recent issues filed without labels: #296, #299, #270, #212, #181, #176, #69,
#138, #155, #26, #31, #40, #45, #21, #108. Suggested minimum: one tier label
(`middleware` / `wordpress`) plus `bug` or `enhancement`. The `scheduling`,
`spike`, and `epic` labels introduced for #272–#279 are working well — keep
that pattern.

### 3.5 New issues to file (from §2)

1. `middleware: remove broken uuid package from requirements.txt` (§2.1 — quick win)
2. `middleware: route export column headers through CHM_FIELDS` (§2.2)
3. `middleware: split church_teams_export.py into export/formatting/scheduling modules` (§2.3)
4. `middleware: micro-fixes — bare except, print-instead-of-logging, hardcoded export path` (§2.4)
5. `repo: add plugin zip/source version-drift check to release workflow` (§2.5)
6. `docs: author ADMIN_MANUAL.md and close the Admin Manual Override issue family` (§3.3)

---

## 4. Post-event roadmap (recommended sequencing)

1. **Event week (now):** only #202-family results/standings work if still
   needed live, plus any hotfixes. Everything else waits.
2. **Week after the event:** file the §3.5 issues; apply the triage
   (milestones, labels, closures) once approved; ship the §2.1 `uuid` quick
   win and §2.4 micro-fixes in a small v1.12.x patch.
3. **Early off-season:** §2.2 `CHM_FIELDS` unification (pairs naturally with
   the pre-2027 field-inspector run), then the §2.3 export split while 2026
   behavior is fresh.
4. **Season transition:** run `docs/SEASON_TRANSITION.md`, then the **2027
   season prep** milestone (#268, #270, #69, #45 …).
5. **2027 Scheduling Helper:** the #273–#279 spikes are well-scoped; run them
   in the order filed (service skeleton → artifact DAG → state store → rules
   parity → canvas POC → PDF rendering → concurrency) so each spike's output
   feeds the next, per `docs/PRD_SCHEDULING_HELPER.md`.

---

*Review conducted at tag `v1.12` (commit `c0a2d4a`). Companion changes in
this cleanup: CHANGELOG restructure, tags v1.10–v1.12, README/CLAUDE.md
refresh, .gitignore fixes, and this document.*
