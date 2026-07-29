# Retrospective — Sports Fest 2025 and the Pre-2026 Era

*Written 2026-07-27, reconstructed from the 61 commits between 2025-03-28 and
2025-07-17, the CHANGELOG's version history back to 2025-03-10, and the shape
of what 2026 inherited.*

*Drafted by Claude; reviewed and approved by Bumble 07/28/2026.*

*This sits between two other records. `RETROSPECTIVE_PODIO_2016_2024.md` covers
the nine seasons before this repository existed, when Sports Fest ran on Podio
and Globiflow. `RETROSPECTIVE_2026.md` opens with ChMeetings pulling its API out
from under a working system. This one explains what that system was, how it got
built, and why so much of 2026's spring was spent paying its debts. See
`RETROSPECTIVES.md` for the full series and reading order.*

The central achievement of 2025 was not full automation. It was moving Sports
Fest's operational memory onto infrastructure VAY owned end to end — this
participant exists; this church owns the record; these are the sports and
validation issues; this approval is pending — and making the *rules* behind that
memory readable, testable, and versioned for the first time. Podio had held the
records for nine years; what it could not hold was its own logic in a form anyone
could review. That act of making the work legible is what later automation had to
build on.

---

## By the numbers

| | |
|---|---|
| Commits | **61** (2025-03-28 → 2025-07-17) — vs. 544 in 2026 |
| Churn | **+15,303 / −1,325** across 43 files — vs. 196 files in 2026 |
| Net tree growth | **+13,782 / −3** — near-pure accretion |
| Issues referenced | **21**, spanning #1–#50 |
| Versions | **0.1 → 1.04** |
| Tests | **23** — vs. 889 in 2026 |
| Git tags | **0** |
| CI workflows | **0** |
| Contributors | **3** |
| Dormancy | **8 months** (2025-07-17 → 2026-03-13) |

Commits by month:

| Mar | Apr | May | Jun | Jul | Aug–Feb |
|---:|---:|---:|---:|---:|---:|
| 15 | 6 | 21 | 6 | 13 | 0 |

Fifteen of those March commits landed on a single day. The curve is not a
development arc — it is one large deposit followed by four months of reacting
to whatever the season broke next, and then silence.

---

## Act 0 — The era before git (Mar 10 – Mar 27, 2025)

The most important fact about the pre-2026 codebase is that its design does not
appear in the repository at all.

Two things sit outside git here, and they are different in kind. The first is
**nine seasons of prior operation**: from roughly 2016 through 2024, [Sports Fest
ran on Podio and Globiflow](RETROSPECTIVE_PODIO_2016_2024.md), and before that 
another [two decades on Microsoft Access](RETROSPECTIVE_ACCESS_1998_2015.md). That system knew
what the tournament was — churches, athletes, pastors, church reps, signatures,
medical releases, badges, rosters, score sheets, gyms, fees, deadlines,
volunteers, Bible verses — and it is documented separately in
`RETROSPECTIVE_PODIO_2016_2024.md`. This repository did not invent the domain. It
inherited it.

The second is the **eighteen days in March 2025** when that inherited knowledge
was translated into a new architecture, in conversation, before a repository
existed to record it.

`CHANGELOG.md` documents ten versions — 0.1 through 1.00 — dated March 10
through March 28, 2025. The repository's first commit is March 28. Every one of
those versions predates version control:

| Version | Date | What it records |
|---|---|---|
| 0.1 | Mar 10 | Three-tier architecture, 11 WordPress tables, core workflows |
| 0.2 | Mar 11 | Schema simplified 11 → 8 tables, field mappings from real CSV |
| 0.3 | Mar 12 | Windows setup, database schema, implementation phases |
| 0.4 | Mar 13 | Email moved from Python to WordPress, `sf_email_log` |
| 0.5 | Mar 14 | `church_code` as human-readable identifier |
| 0.6 | Mar 15 | PyTest, mocking convention, `LIVE_TEST` toggle |
| 0.7 | Mar 17 | `sf_rosters` table, team-level validation |
| 0.8 | Mar 21 | Pydantic, rule-based validation |
| 0.9 | Mar 26 | JSON validation rules, ERROR/WARNING/INFO severity |
| 1.00 | Mar 28 | Consolidated into final implementation |

Eighteen days of architecture — including decisions still load-bearing today —
happened in many conversations with GPT 4 and Claude 3.5 (both verbal and textual)
during recovery from a retina detachment and landed as prose. The schema going from 11
tables to 8 in one day, email relocating tiers on another, `church_code` displacing
`church_id` as the operator-facing identifier on a third: these are real design
iterations with real reasoning behind them, and none of that reasoning survives.
Only the conclusions do.

This is the sharpest contrast with 2026. The 2026 retrospective could be written
*because* 191 issues carried their own argument. The 2025 design phase left ten
bullet lists.

It is worth being precise about what was lost and what was not. The *domain*
knowledge was not lost — it had been accumulating in Podio since 2016 and was
still running the 2024 season. What vanished was the **translation layer**: the
reasoning that turned a decade of no-code operational practice into a three-tier
architecture with JSON validation and a `church_code` key. Why the schema went
from 11 tables to 8 in a single day, why email moved tiers, why `church_code`
displaced `church_id` — those were the decisions that converted inherited
experience into a new shape, and they are the ones with no record.

**What this act was really about:** a decade of operational knowledge being
translated into a new architecture, somewhere git could not see.

---

## Act I — The landing (Mar 28, 2025, 15 commits in one day)

The repository was not grown. It was transcribed.

Fifteen commits on March 28 deposited roughly 13,000 lines: docs first
(ARCHITECTURE, CONTRIBUTING, INSTALLATION, TROUBLESHOOTING, USAGE), then config,
then the connectors, then a single "RC commit for 1.0 release" carrying 8,800+
lines — the entire WordPress plugin, the validation package, the sync package,
and all the tests, in one commit. It was the first time I used GitHub after
decades-long absence from SourceForge. Google's AIstudio walked me through
VSCode installation and then the first commit on GitHub.

The transcription shows its seams, and they are worth recording precisely
because they are the fingerprints of the workflow:

- **`95bc75f "Add unit tests for Sports Fest middleware configuration module"`**
  contains `middleware/main.py`, 299 lines. No tests. The message describes what
  was *meant* to go in; the paste buffer held something else.
- **`dddc01e "No code changes made."`** contains `docs/ARCHITECTURE.md`, 540
  lines — the single most consequential document of the era, committed under a
  message asserting that nothing happened.
- **`middleware/wordpress/frontend_connector.104`** was committed alongside
  `frontend_connector.py` — 489 lines beside 502. A save-as backup, versioned by
  filename, that lived in the repository from March 28 until July 14, nearly four
  months. It was removed silently in a commit about adding spreadsheet columns.

Net tree growth across all of 2025 was **+13,782 / −3**. Three lines removed.
Whatever went in, stayed in.

The architecture that landed that day was, to its credit, the right one. Three
tiers with narrow jobs. JSON-driven validation with Pydantic models. Mock-mode
tests with a `LIVE_TEST` toggle. `church_code` as the human-readable key.
WordPress owning tokens and email. All five survive intact into 2026 — the 2026
retrospective's "What Held" section is, almost entirely, a list of decisions made
before this repository existed. I have never coded in Python before, but both ChatGPT
and Claude agreed that this would be the right choice for what we need.

The 1.0 release re-established, on a new stack, something Sports Fest had held
since 2016 and could not afford to lose: a shared place to remember operational
truth. Podio had provided that for nine seasons — visible records, configurable
views, comments and files beside the data. The 2025 bridge had to earn it back
from zero, and at first it held less: a participant, church ownership, sports,
validation issues, roster membership, and pastoral approval state, together in
one record. What it added was not the idea of shared memory but a place where
that memory's *rules* could be read, tested, and versioned.

That is the honest frame for the whole year. 2025 was not a first system. It was
a **replacement in its first season**, competing against a decade-matured
incumbent that still did document generation, badges, and e-signature better than
the new one would for years.

It arrived fully formed because it had been fully designed elsewhere — and
because the domain had been understood for nine years before that. That is the
strength and the weakness in the same sentence.

**What this act was really about:** a good architecture arriving with years of
secular work experience attached, and a decade-old operation beginning its move 
onto rails that could be versioned.

---

## Act II — Season one, under fire (Apr 2 – Jul 17, 2025, 46 commits)

Then real registrations arrived, and the system met its users.

The issue numbers tell the story better than the code does. Issue **#1** —
*"Click Approve on Pastor Approval Email leads to error screen"* — is the first
thing that happened after launch, and it took two commits on the same day, both
with the identical message, to put down. The approval path, the single feature
the entire system existed to provide, was broken in production on day one.

What followed, in order:

- **#4** — approved athletes not showing correct approval status; fixed by
  removing pagination on the WordPress ID search, then re-doing participant sync
  so it would stop overwriting `approval_status`
- **#12** — a minor's record never reaching pastoral approval because a consent
  ERROR never got updated
- **#23** — partner names not recorded on `sf_roster`
- **#32** — *"Not everyone from NHC church show up on Pastoral Approval emails"* —
  a pagination bug, the same class of bug that #58 would rebuild around
  `total_count` a year later
- **#33** — non-members displaying as `Yes` for church membership on the approval
  email, fixed twice in one day
- **#42** — resend approval email reusing expired tokens
- **#50** — a male athlete registered for Women's Volleyball landing on the wrong
  roster team

Read as a set, these are all one bug: **the system could not be trusted to tell
a pastor the truth about who they were approving.** Wrong membership status,
missing minors, missing churches, wrong gendered team, dead approval links. The
2026 retrospective describes issue #78 — the membership freeze — as "the first
place this system stopped assuming everyone using it was acting in good faith."
2025 is the year it could not yet reliably serve users acting in *perfect* good
faith.

These failures also show that validation and approval were never merely technical
correctness. They were communication among staff, pastors, church reps, and the
registration source of truth. A consent error could hide a minor from pastoral
review. A pagination defect could erase a church from an email. A membership
flag could misstate the very fact a pastor was being asked to affirm.

Two other things stand out about how this work was done.

**Debugging ran on human reports.** Branch names are the evidence:
`4-check-on-pending-approval-status-with-james`,
`codex/locate-approval-email-for-matthew-demegillo`. Commit messages name
participants — *"Check for Jasen Pham and Matthew Demegillo who registered for
Scripture Memorization."* There was no monitoring, no reconciliation report, no
audit command. A problem became visible when a person noticed and said something.
The system learned Sports Fest by following the smoke. The 2026 Church Team
export becoming a "diagnostic instrument" is the direct answer to this, and it is
why that mattered.

**The operator was the integration layer.** `run-me.bat` is two lines:

```
python main.py sync --type full
python main.py export-church-teams
```

Everything else was manual. `USAGE.md` states it plainly at line 146: *"After
running this command, you should import the generated file into ChMeetings (or
manually add the people to groups)."* Group assignment generated a spreadsheet
for a human to re-upload. Churches entered through
`sync-churches --file "data/Church Application Form.xlsx"`. Consent verification
was a manual check. Per ChMeetings' ticket #11991, forms that failed to
auto-link had to be connected by hand. The Photo column shipped with an
instruction to press Ctrl+H in Excel to manually load the formula the exporter 
wrote to maintain compatibility with pre-365 versions of Excel.

The Excel spreadsheets Church_Team_Status_*.xlsx files deserve a precise judgment 
here. As an **output and review surface**, it was humane and effective: Church 
Reps could inspect, annotate, forward, compare, and understand a workbook without 
learning the system internals. As a **workflow stage**, where a generated file 
had to be repaired, changed, and re-imported, it was fragile. Excel was both 
mercy and debt, depending on which side of that line it occupied.

And underneath it all, `backend_connector.py` opened Chrome — Selenium login,
`WebDriverWait`, `find_element(By.ID, "password")`, and a `save_screenshot()`
call for when authentication failed. Screenshots as a debugging channel.

**What this act was really about:** a system that worked, provided a person
stood in the middle of it — but one that was already making that person's hidden
work visible enough to improve.

---

## Act III — The first agent (June 2025)

I recollect that this era ran on manual copy-paste with no agentic tooling. The 
evidence has some exceptions of that as memory suggests.

Four merged branches carry the `codex/` prefix:

| PR | Date | Branch |
|---|---|---|
| #37 | Jun 5 | `codex/update-readme-links-to-docs-directory` |
| #38 | Jun 6 | `codex/find-and-fix-bug-in-codebase` |
| #39 | Jun 6 | `codex/update-person_id-in-test` |
| #43 | Jul 14 | `codex/locate-approval-email-for-matthew-demegillo` |

Agentic tooling entered this repository in **June 2025**, not 2026. But look at
the scope: fix README links, fix a config default for tests, correct a person ID
in a test, find one participant's approval email. Small, bounded, verifiable in
seconds. Meanwhile the 2,374-line `rest-api.php` and the 554-line sync manager
were hand-carried. This was Codex's first release, and I was just kicking the tires.

That is the honest characterization of the era. Not "no agents" — rather, agents
were trusted with errands while the load-bearing work stayed manual. There was
also no context for an agent to work from: no `CLAUDE.md`, no `AGENTS.md`, no
skill, no convention document beyond `CONTRIBUTING.md`. The repository could not
tell a tool what it was.

Compare the same repository today: a `CLAUDE.md` establishing tenant scope and
conventions, an `AGENTS.md` kept in sync with it, a vendored `vay-chmeetings`
skill shared across three projects, and a documented rule that `CHM_FIELDS` is
the only way to name a ChMeetings field. The 2026 leverage did not come from
better models alone. It came from a repository that had been made legible.

**What this act was really about:** the tooling arrived a year before the
groundwork that would let it matter.

---

## Act IV — The silence (Jul 17, 2025 – Mar 13, 2026)

Eight months. Zero commits.

The last 2025 commit fixes gendered team mapping four days before the event. Then
the repository stops. `CHANGELOG.md` declares *"Version 1.04 (2025-07-17)"* — but
the commit that actually finalizes v1.04 is dated **2026-03-13**, eight months
after the version it closes. The season ended mid-sentence, and the note was
written the following spring.

Nothing was tagged. There is no `v1.04` in `git tag` — the first tag in this
repository's history is **v1.08, April 2026**. Four releases shipped and ran a
real tournament without a single one being marked in git. The 2026 retrospective
records plugin release discipline "bending under hotfix pressure" in July 2026;
the truthful version is that it had no baseline to bend from.

The dormancy is not a criticism. This is volunteer ministry software with one
primary author and an annual event. But it explains the shape of 2026: when
ChMeetings changed its API over the winter, there was nobody watching, and the
season opened with 77 commits of pure repair.

**What this act was really about:** an annual system discovering that its
dependencies do not take the year off.

---

## What held

Nearly everything structural, which is the striking part.

- **The three-tier architecture.** Designed in the pre-git phase, unbroken through two seasons.
- **JSON-driven validation with Pydantic.** `Summer_2025.json` was joined by `summer_2026.json`; the mechanism never changed.
- **Mock-mode testing with a `LIVE_TEST` toggle.** 23 tests became 889 on the same convention, laid down in v0.6 on March 15, 2025.
- **`church_code` as the human-readable identifier**, with `church_id` kept as the database key.
- **WordPress owning tokens and email**, moved there in v0.4 for "better process flow" — the decision that later let WordPress absorb the entire event-day arena.
- **The Excel export as a staff-facing artifact.** As an output and review surface, it met volunteers where they were; in 2026 it grew into a diagnostic instrument.
- **A shared memory surface, rebuilt on owned infrastructure.** Participants, churches, rosters, validation, and approval state became one operational record again — this time in a place where the rules behind it could be read, tested, and versioned.

## What bent

- **Selenium**, present from the first connector commit, removed root and branch in 2026's v1.05.
- **Excel as a workflow stage rather than an output.** Church intake, group assignment, and consent all round-tripped through a human and a spreadsheet. The same format that served people well for review became risky when treated as an intermediate source of truth.
- **Pagination**, wrong in #32 in May 2025 and still wrong enough to need rebuilding around `total_count` in #58 a year later.
- **Commit hygiene** — `"asdf"`, `"Config"`, `"No code changes made."`, `"Simple change to test push permission"`, the same fix committed twice under one message, `"Total Denided"` corrected by a follow-up commit.
- **Release discipline**, which did not exist: no tags, no CI, no lint, a version declared eight months before it was finalized.
- **The dependency list**, which shipped `uuid>=1.30` on day one.
- **Operational observability.** Without reconciliation reports or audit commands, human complaints and named-person investigations became the monitoring system.

## What we learned

1. **Designing outside version control costs the reasoning, not the design.** The architecture was right and survived two seasons. Why the schema went from 11 tables to 8 is simply gone.
2. **The first step away from manual work is faithful capture, not complete automation.** Before the system could optimize Sports Fest, it had to name and preserve the workflow people were already carrying.
3. **A commit message that does not match its diff is a workflow smell.** Files pasted one at a time produce messages describing intent rather than content.
4. **Excel is a bridge when it is an output and a trap when it becomes a workflow stage.** A workbook can be the right human interface while manual re-import still creates the season's most fragile handoffs.
5. **Validation is communication, not merely correctness.** Consent, membership, eligibility, approval, and roster state shape what pastors and church reps are being told about real people.
6. **Without monitoring, your bug tracker is a list of people who complained.** Branches named after participants are a diagnostic gap, not a naming convention.
7. **Narrow repair tools matter.** A one-participant sync or targeted investigation is operationally safer than rerunning the whole universe to diagnose one record.
8. **Agents need a legible repository more than they need a better model.** Codex was here in June 2025 and fixed README links, because new tools are often not mature.
9. **Annual software still needs a heartbeat.** Eight dormant months turned a vendor API change into a 77-commit emergency.
10. **Tag the thing that ran the event.** Four releases ran a real tournament, and none of them are findable in git.
11. **A first season is not a first system.** 2025 replaced a decade-matured incumbent. Judged as a greenfield build, it looks thin; judged as year one of a migration off nine years of Podio and Globiflow, the surprise is how much of the domain it already had right.

---

## What 2026 inherited

Much of 2026's repair work — most of it in the spring, some as late as the week
before the event — was paying down debt written in 2025:

| 2026 work | 2025 origin |
|---|---|
| Selenium removal (v1.05) | `backend_connector.py`, first connector commit, Mar 28 |
| `CHM_FIELDS` introduced (v1.05) | Field names inlined throughout the original sync package |
| Pagination via `total_count` (#58) | The #32 pagination bug, May 2025 |
| Approval sync moved Excel → API | `sync_churches_from_excel`, Mar 28 |
| 429 retry centralized (#64) | Retry logic scattered across the pasted connectors |
| Membership trust boundary (#78) | Membership status editable after the fact since v1.00 |
| First git tag (v1.08, Apr 2026) | Four untagged 2025 releases |
| First CI workflow (`php.yml`, Jul 2026) | No automation of any kind in 2025 |
| `uuid` flagged in the 2026 debt register | `requirements.txt:14`, committed 2025-03-28 |

That last row deserves its own sentence. `ARCHITECTURE_REVIEW_2026.md` flags the
`uuid` line as a dependency that would break a fresh install. It has been sitting
at `middleware/requirements.txt:14` since the first requirements file, unchanged,
through two tournaments — **sixteen months**, still open today as part of #332.

---

## Closing reflection

It is tempting to read 2025 as the rough draft and 2026 as the real thing. The
commit counts invite it: 61 against 544.

The record does not support that reading. The architecture that carried the 2026
season — three tiers, JSON validation, mock-mode tests, `church_code`,
WordPress-owned approval — was designed in eighteen days in March 2025, mostly
before this repository existed, and required no structural change to absorb
scheduling, badges, scoresheets, live scoring, and public advancement displays a
year later. That is an unusually good call, made early, by someone thinking
carefully without a tool watching.

It was also not a guess. Nine years of Podio had already established what the
tournament needed and, more usefully, where a platform-configured system breaks:
meaning hidden in display labels, logic parsed out of category text, validation
buried in long visual flow chains, annual behavior copied forward instead of
versioned. Read against `RETROSPECTIVE_PODIO_2016_2024.md`, the March 2025
architecture looks less like inspiration and more like a set of deliberate
countermeasures — `CHM_FIELDS` against label-encoded meaning, JSON rules against
flow-buried validation, git against copy-forward configuration. The good call was
real. It was also informed.

Nor should the manual character of 2025 be mistaken for absence of progress.
The system learned the real tournament before it tried to optimize it. It
translated hidden labor into fields, rules, states, exports, and repair commands.
Excel made the operation more visible to volunteers. WordPress gave approval a
home. Validation turned judgment into a conversation the system could preserve.
The bridge's first victory was not replacing the operator; it was reducing how
much of Sports Fest had to exist only in the operator's head.

What 2025 lacked was not judgment. It was **legibility and leverage**. The
decisions were sound and unrecorded. The operator was load-bearing and
undocumented. The tests were real but thin. The releases ran a tournament and
left no marker. Agentic tooling was present and had nothing to grip.

2026's true accomplishment was not the solver, or the plugin, or the 889 tests.
It was converting a system that lived substantially in one person's head and
hands into one that could be described — to a collaborator, to a tool, to next
year. The retrospectives now sitting beside this file are themselves evidence of
that shift: **2026 can be narrated because 2026 wrote things down.** 2025 has to
be reconstructed from filename extensions and mismatched commit messages.

That is the real distance traveled between the two seasons.

*Thus spake the Master: “Write the work plainly, that the next steward may run; 
record the journey, that a generation yet to come may remember.” (Ha.2:2, Ps.102:18)*

Up to [RETROSPECTIVES.md](RETROSPECTIVES.md), back to [GitHub Era, 1st year 2025](RETROSPECTIVE_2025.md), or forward to [GitHub Ere, 2nd year 2026](RETROSPECTIVE_2026.md)?
