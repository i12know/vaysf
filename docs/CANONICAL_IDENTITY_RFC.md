# RFC: Canonical Person Identity — untangling the duplicate-people problem

*Written the night before Sports Fest 2026, after two seasons of living with
duplicate "Justin Nguyen" scoresheets and twin "Ngoc Le / Khoa Le" badges.
This is a design document, not code. Nothing described here exists yet.
Read it with coffee; decide at leisure. The event-day workaround in §6 is
the only part relevant before Monday.*

---

## 1. The feeling you couldn't name

You said the system feels entangled — that merging duplicates makes it
worse, that deleted players reincarnate, that re-registrations haunt the
scoresheets. Here is the sentence underneath all of it:

> **The system has no concept of a *person*. It only has a concept of a
> *ChMeetings ID* — and ChMeetings IDs are not people.**

A ChMeetings ID is an *identifier*: a label the vendor mints when a record
is created. A *person* is the human who may, over two seasons, accumulate
several of those labels — because they re-registered to change sports,
because a church rep deleted them and they re-applied, because you merged
two profiles in ChMeetings and the merge retired one ID.

Every tier of vaysf treats the identifier as if it were the person:

- **Sync** looks up WordPress participants by `chmeetings_id` and creates
  a new row when it finds nothing (`middleware/sync/participants.py`,
  the lookup inside `_sync_single_participant`).
- **WordPress** enforces `UNIQUE KEY chmeetings_id`
  (`plugins/vaysf/vaysf.php`) — which *sounds* like duplicate prevention
  but is actually duplicate *manufacturing*: a second ID for the same
  human sails through the uniqueness check as a brand-new person.
- **Rosters** hang off the participant row; **badges** are one PNG per
  `chmeetings_id`; **scoresheets** append every roster row with no dedup.

So when ChMeetings mints a second ID for one human, the system doesn't
make an error — it does exactly what it was built to do, twice. That is
why the symptoms feel scattered (a duplicate on a Basketball scoresheet
here, twin badges there, a 404 during approval sync somewhere else) while
being one disease. And it is why the entanglement never yields to local
fixes: each artifact is faithfully printing the duplicate identity it was
handed.

## 2. Why everything you built so far detects but never cures

Two seasons of tooling have grown around this problem, and an honest
audit shows a pattern:

| Tool | What it does | What it doesn't do |
|---|---|---|
| `investigate-consent-404s` | Scores stale IDs against live people (birthdate/email/phone/name) and classifies: *likely re-registered*, *likely deleted*… | Read-only. Writes an Excel report. Merges nothing. |
| `audit-team-groups --remove-orphans` | Removes group memberships whose person ID 404s | ChMeetings-side only. The WordPress row lives on. |
| Identity-drift detection (#171) | Catches when the *same* ID's name/church/sport changes; forces re-approval | Never fires across two IDs — a re-registration looks like a brand-new person, not drift. |
| `repair_form_people` | Blocks creating people from duplicate form submissions | Pre-sync only; can't see duplicates already live. |
| Troubleshooting playbooks | Classify a 404 as stale-merge vs needs-investigation | Manual, case-by-case, after the haunting has begun. |

Every one of these is **detection and classification**. None of them is
**resolution** — nothing anywhere says "these two IDs are the same human,
and from now on the system should behave accordingly." The stale
WordPress row is never reconciled, so it reincarnates through every
export until someone hand-edits it. Your instinct that "fixing them
sometimes makes it worse" is correct: merging in ChMeetings retires an ID
that WordPress still holds, which *creates* a 404 where there wasn't one.
The cure at the wrong layer deepens the disease.

## 3. The missing concept: canonical identity

The elegant fix is not to chase duplicates through four subsystems. It is
to introduce the one concept that's missing — **a canonical identity
layer** — at the one place all data already flows through.

The idea in one sentence:

> **Keep a small, human-confirmed map of "stale ID → canonical ID," and
> apply it once, at the front door of the sync, so the rest of the system
> never sees a duplicate identity again.**

Three properties make this elegant rather than clever:

1. **It doesn't fight ChMeetings.** ChMeetings will keep minting IDs;
   church reps will keep deleting people; players will keep
   re-registering. The design accepts that as weather, and puts up an
   umbrella at the single doorway instead of chasing raindrops through
   the house.
2. **One concept, one file, one choke point.** Every participant already
   passes through `_sync_single_participant()`. Resolution is three lines
   at the top of it. Everything downstream — validation, rosters, badges,
   scoresheets, approval sync — stays exactly as simple as it is today,
   because it now receives only canonical identities.
3. **The empty map is today's system.** With no alias entries, behavior
   is byte-for-byte unchanged. Risk of landing it: near zero.

## 4. The design, in five parts

### 4.1 The alias map — `person_aliases.json`

An operator-maintained JSON file mapping stale IDs to canonical ones,
following the exact pattern of the existing `late_racquet_overrides.json`
(committed example file; real entries in a git-ignored `.local.json`;
path overridable in `.env`):

```json
{
  "3634001": "3633885",
  "3634002": {
    "canonical_chm_id": "3633885",
    "reason": "re-registered to change sports; old profile deleted by rep",
    "confirmed_by": "Bumble",
    "confirmed_on": "2026-07-20",
    "note": "Ngoc Le / Khoa Le"
  }
}
```

You are the only writer of this file. The code never edits it. That keeps
the merge decision — a pastoral, human judgment about who is who — in
human hands, permanently.

### 4.2 Resolution at the choke point

At the top of `_sync_single_participant()` in
`middleware/sync/participants.py`:

```python
canonical_id = resolve_chm_id(chm_id, self.person_aliases)
if canonical_id != chm_id:
    logger.info("[VAY SM] Alias: stale chm_id %s resolved to canonical %s", chm_id, canonical_id)
    chm_id = canonical_id
```

From that line on, the ChMeetings fetch, the WordPress lookup, the
create/update decision, drift detection, roster sync — all of it operates
on the canonical identity. The stale WordPress row is never touched
again; the duplicate can no longer be *re-created*. This also quietly
fixes the ChMeetings-merge case: the retired ID resolves to its
replacement *before* the fetch that would have 404'd.

### 4.3 Retire, don't delete — `apply-aliases`

Resolution stops new hauntings; the *existing* stale WordPress row still
needs an exorcism. A new `apply-aliases` command (report-only by default,
`--execute` to act, mirroring `audit-team-groups --remove-orphans`)
retires each aliased row in place:

1. Delete its roster rows (existing `delete_roster` API) — this is what
   actually removes the duplicate from scoresheets and exports, which
   read rosters.
2. Set its `approval_status` to `merged` — a tombstone. The status column
   is a plain VARCHAR, so this needs **zero plugin changes**, and every
   consumer that filters (badges: approved-only; approval sync:
   approved-only; pending queues) now ignores the row.
3. Tombstone its approval row the same way, so an old email token can't
   resurrect it.
4. Resolve its open validation issues.
5. If the *stale* row was pastor-approved but the *canonical* row isn't:
   warn loudly and do **not** auto-copy the approval. An identity change
   invalidates approval — the same philosophy as the drift guard (#171).

Why not just delete the row? Because there is no participant DELETE
route in the plugin, and — more importantly — `sf_approvals` and
`sf_validation_issues` have **no cascading foreign keys** to
participants. A hard delete would strand orphaned rows pointing at a dead
`participant_id`: a brand-new species of ghost. The tombstone keeps
referential integrity, keeps the audit trail, and is reversible if an
alias entry turns out to be a mistake.

### 4.4 A duplicate finder that proposes, never merges — `find-duplicates`

Maintaining the alias map shouldn't require detective work. A new
`find-duplicates` command reuses the identity scoring you already trust
from the consent-404 investigator — birthdate 33, email 27, phone 24,
name 16, with the "strong match needs a birthdate-or-exact-name anchor"
rule that protects family members who share phones — and runs it across
**all** live participants, not just 404 cases. Output: an Excel workbook
of candidate pairs with scores, evidence, and a ready-to-paste JSON
snippet column. You review, confirm, paste into the alias map.

Worth savoring: **the Ngoc Le / Khoa Le case is already solved by your
existing weights.** Same birthdate + email + phone scores 84 — a strong
match — with *zero* points from the name. The scoring you built for
consent 404s was always the right instrument; it was just pointed at too
narrow a target.

### 4.5 Tripwires downstream

Sync-level resolution is the cure; downstream gets cheap smoke alarms.
Warning-only detectors (never filters — paper must match data) in
scoresheet, badge, and church-team-export generation: two rows on one
team sharing a normalized name and birthdate logs a WARNING. That catches
*new* duplicates — ones with no alias entry yet — before an operator sees
them on paper at 7 a.m. This is also the honest fix for issue #40
("duplicate names in export-church-teams").

## 5. What this deliberately does not do

- **No ChMeetings-side writes** beyond what already exists. The diocese
  data stays under human control.
- **No WordPress plugin changes, no schema migration.** The tombstone
  rides an existing VARCHAR column.
- **No auto-merge, ever.** The code proposes; you decide. A wrong
  automatic merge of two *actual* different people named Justin Nguyen
  would be far worse than a duplicate badge.
- **No new database, no new service.** One JSON file, four small Python
  modules, three lines in the syncer.

## 6. The event-day playbook (usable tomorrow, no new code)

For tonight's Justin Nguyen and Ngoc/Khoa Le — with existing tools only:

1. `python main.py inspect-person <id>` on both IDs to confirm which is
   the stale twin (the one with no live ChMeetings record, or the older
   registration).
2. In ChMeetings, remove the stale person from their `Team ...` group so
   the next sync stops promoting them.
3. Via the WordPress connector (interactive Python):
   `get_rosters({"participant_id": <stale_wp_id>})`, then
   `delete_roster(roster_id)` for each; then
   `update_participant(<stale_wp_id>, {"approval_status": "denied"})`.
4. Rerun `generate-scoresheets` and `generate-badges --church-code <X>`.
   Delete the stale badge PNG — its filename contains the stale
   ChMeetings ID, so it's easy to find.

Ten minutes per ghost. §4 is how we make it the last ten minutes you ever
spend this way.

## 7. Decisions that are yours

1. **Re-approval policy.** When an alias retires a pastor-approved row
   and the canonical row isn't approved: force re-approval (my
   recommendation, consistent with #171) or carry the approval over?
2. **Scope of `apply-aliases`.** WordPress-only, or also remove the stale
   person from ChMeetings Team groups via the existing membership API?
3. **Where real alias entries live.** Git-ignored `.local.json` (my
   lean — the notes column carries names) or committed to the repo?
4. **The `merged` status value.** Confirm no WordPress dashboard or
   pastor UI chokes on an unfamiliar status string (to be verified
   against `class-vaysf-rest-approvals.php` during implementation).

## 8. Implementation sketch (post-event, one focused week)

| Phase | What | New files |
|---|---|---|
| 1 | Alias map + loader + resolution at choke point | `middleware/sync/person_aliases.py`, `middleware/data/person_aliases.json` (example) |
| 2 | `apply-aliases` reconciliation command | `middleware/sync/alias_reconciler.py` |
| 3 | `find-duplicates` proposal command; extract shared scoring | `middleware/sync/duplicate_finder.py`, `middleware/sync/identity_scoring.py` |
| 4 | Downstream warning tripwires (#40) | — (edits to scoresheets/badges/export) |

Config lands beside the late-racquet precedent in `middleware/config.py`;
CLI subcommands in `middleware/main.py`; mock-mode tests for the loader,
sync resolution (including the empty-map regression guard), reconciler
idempotency, and finder scoring; docs in `USAGE.md` and a "duplicate
person" playbook in `TROUBLESHOOTING.md`. Phase 1 alone stops the
bleeding; each later phase is independently shippable.

## 9. The verge of something great

What you sensed is real, and it's this: **the entanglement was never many
problems.** Two seasons of scattered symptoms — 404s, ghosts, twins,
re-approval confusion — trace to a single missing abstraction, and that
abstraction costs one JSON file and three lines at a door the data
already walks through. The system underneath is sound; it has been
faithfully amplifying an identity error it was never given the vocabulary
to express. Give it the word *person*, and the haunting ends.

---

*Companion reading: `docs/ARCHITECTURE_REVIEW_2026.md` (state of the
system at v1.12), `docs/TROUBLESHOOTING.md` §"Approval Sync Returns 404"
(today's manual classification of stale IDs), issue #40 (duplicate names
in exports), issue #171 (identity drift).*
