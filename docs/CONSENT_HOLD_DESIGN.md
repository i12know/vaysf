# CONSENT HOLD — design memo (Track R, 2027)

**Status: M1–M12 approved on 2026-11-16. See [§8](#8-maintainer-decisions-for-2027) for the decisions and rollout checks.**

Scope: the remaining 2027 work in epic #307, Track R: #315 (guardian reminder and
address gate), #317 (self-signed flag) and #318 (enforcement). It answers the eight
questions in `docs/REGISTRANT_TRUST_RFC.md` §9.4 and turns §9.2 into something that
can be built.

Every statement about what the code does was read on `main` at `7480955`
(v1.1.15 plus unreleased changes; plugin `DB_VERSION` 1.0.13). No live API calls were made
and nothing was run against ChMeetings or WordPress. Claims about how the ChMeetings
tenant itself behaves (who can edit a field, who can read a profile note, what a UI
merge does to custom fields) could not be checked from the repo and are marked
**unverified**.

Decisions D1–D12 and §9.2 of the RFC are treated as fixed policy. The approved answers in §8 govern the design where they refine the earlier proposal.

---

## 0. The design in one page

1. **ChMeetings stays the record.** Signed consent is the consent-form submission
   plus Box 2 on the athlete's profile. Staff file signed replacement copies and
   acceptance details in restricted storage (M8).
2. **The hold itself is working state in WordPress**, on the athlete's
   `sf_participants` row, in columns the participant sync never writes. It is keyed on
   the ChMeetings ID (the row is unique per ChMeetings ID and cannot be deleted).
3. **A hold never changes `approval_status`.** Pastor approval stays exactly as it is
   (D5). Eligibility becomes a separate question that every consumer asks through one
   function that checks approval, holds, and required minor consent (M9–M10).
4. **Placing a hold is a staff command.** It marks the row, unticks Box 2 in
   ChMeetings, records the hold, and withdraws a hosted badge. Nothing places a hold
   automatically.
5. **Box 2 alone can no longer clear a minor.** While a hold is active, effective
   consent is false whatever Box 2 says, and the nightly `check-consent` run will not
   re-tick Box 2 from the form that caused the hold.
6. **Clearing follows the badge rule.** Before a badge is issued, the Church Rep clears
   the hold by re-ticking Box 2 once replacement consent is on record; the next sync
   accepts it. After a badge is issued, only the staff command clears it.
7. **Alias merges carry the hold in the middleware.** `apply-aliases` copies an active
   hold to the canonical row before it tombstones the stale one, and a conflict
   resolves to "active".
8. **The guardian-address gate is separate** (RFC §9.2, last paragraph): an
   ERROR-level validation issue that the Church Rep resolves in ChMeetings, with its
   own "confirmed guardian" tick.

The parts most likely to be got wrong are listed in §1 (what today's code would do to
a naive hold) and §7 (risks).

---

## 1. What the code does today

These are the facts the design rests on. Each was read on `main`.

| # | Fact | Evidence |
|---|---|---|
| F1 | `consent_status` is recomputed on every sync as "Box 2's label is in the checklist string". | `middleware/sync/participants.py:1333-1338`, `:1377` |
| F2 | Missing consent is ERROR under 18 and WARNING otherwise. The split is hard-coded; the rule's own `severity` (WARNING) is not read. | `middleware/validation/individual_validator.py:352-361`; `middleware/validation/summer_2026.json:173-182` |
| F3 | Boxes 1–4 must all be ticked before sync sets `pending_approval`. Any ERROR issue keeps the athlete at `pending`. | `middleware/sync/participants.py:1131-1144` |
| F4 | Once a row is `approved`, `denied` or `reapproval_required`, sync preserves that status whatever validation says. An approved athlete who later loses consent stays `approved`; only an issue is raised. | `middleware/sync/participants.py:973-979`, `:1124`, `:1152-1158` |
| F5 | Open validation issues are closed automatically in three places, and by hand in a fourth: any issue the current sync did not regenerate; every INDIVIDUAL issue of a person whose ChMeetings ID now returns 404; every open issue of a row that `apply-aliases` retires; and a GET link on the admin page. | `middleware/sync/participants.py:1845-1868`; `middleware/sync/manager.py:948-1064`; `middleware/sync/alias_reconciler.py:359-374`; `plugins/vaysf/admin/class-vaysf-admin-validation.php:33-46` |
| F6 | `check-consent` runs every night after participant sync. For each form row it takes the best-scoring participant, and if the score reaches 51 (49 for a guardian-signed form) it ticks Box 2 in ChMeetings and mirrors `consent_status` to WordPress. It applies no anchor rule and does not look at signer type against age. | `middleware/daily-run.bat:17-19`; `middleware/sync/consent_checker.py:23-27`, `:419-448`, `:516-531`, `:293-304` |
| F7 | When several form rows qualify for one participant, the one kept is the highest score, then the latest. A self-signed form filled in with the athlete's own phone and email outscores a guardian form that matches only on name and birthdate. | `middleware/sync/consent_checker.py:170-195` |
| F8 | Signer type is a substring test on the "Select one:" answer. It is used for the threshold and written to the audit workbook, and stored nowhere else. | `middleware/sync/consent_checker.py:56-62`, `:115`, `:323`, `:419-422` |
| F9 | A form that matches a `merged` row is credited to the canonical person when the alias is loaded. | `middleware/sync/consent_checker.py:213-246`, `:408-417` |
| F10 | `apply-aliases` writes to WordPress only. It tombstones the participant first, then deletes rosters, tombstones approvals and resolves issues. It reports an approval mismatch and has no consent handling. | `middleware/sync/alias_reconciler.py:3-5`, `:305-331`, `:333-374`, `:529-538` |
| F11 | Badges are rendered for every `approved` participant. Missing consent turns the name card red and prints "Consent Form Needed"; a minor gets a "Minor" tag. The badge is still rendered and uploaded. | `middleware/badges/runner.py:36`, `:297-325`, `:402-404`, `:354-359`; `middleware/badges/generator.py:319-334`, `:668-677` |
| F12 | A badge filename is `{CHURCH}_{chm_id}_{8 hex}.png` with no season in it. An upload replaces a file of the same name, and a DELETE route exists. The public gallery finds a badge by globbing that prefix. | `middleware/badges/generator.py:198-207`; `plugins/vaysf/includes/badge-hosting.php:26-36`, `:140-147`, `:168-193`; `plugins/vaysf/includes/shortcodes.php:1362-1389` |
| F13 | The public `[vaysf_badges]` page lists every `approved` participant of a church by name, or shows their badge images. | `plugins/vaysf/includes/shortcodes.php:1255-1269`, `:1297-1332`, `:284-345` |
| F14 | Approval sync adds every `approved` participant with an unsynced approval row to the ChMeetings approved group. It never removes anyone. | `middleware/sync/manager.py:500-502`, `:567-588`, `:603-617`; `middleware/chmeetings/backend_connector.py:379`, `:408` |
| F15 | Score sheets strike through any roster row whose status is not `approved`. The status reaches them through the Roster tab of the church-team export workbook. | `middleware/scoresheets.py:380-398`, `:401-414`, `:900-901`, `:971-972`, `:1112-1113`; `middleware/church_teams_export.py:514-518`; `middleware/main.py:1983`, `:2136`, `:2268` |
| F16 | Age at the event is computed in four places from two date sources: the validator reads `metadata.event_date` from the rules file; participant sync, badges and the export read `Config.SPORTS_FEST_DATE`. | `middleware/validation/individual_validator.py:25-40`, `:62-68`; `middleware/sync/participants.py:430-442`; `middleware/badges/runner.py:436-451`; `middleware/church_teams_export.py:81`, `:86-97` |
| F17 | The pastor's token endpoint does not look at consent. An outstanding token can be approved at any time and sets the participant to `approved`. | `plugins/vaysf/includes/rest-api/class-vaysf-rest-approvals.php:408-583` |
| F18 | `sf_participants` has `UNIQUE KEY chmeetings_id`, no DELETE route, a GET that returns `p.*`, and an update handler that writes only the keys it is sent. | `plugins/vaysf/vaysf.php:584`; `plugins/vaysf/includes/rest-api/class-vaysf-rest-participants.php:20-45`, `:115`, `:339-510` |
| F19 | Season reset writes an archive note on each profile (checklist ticks, parent info, pastor status) and then clears the Sports Fest fields. WordPress seasonal tables are truncated by hand. | `middleware/season_reset.py:108-159`, `:245-284`, `:67-97`; `docs/SEASON_TRANSITION.md:349-356` |
| F20 | Profile notes are text only (`note`, `created_on`, `updated_on`; no author). `get_person_notes` reads one page and does not follow paging. | `chmeetings_openapi_v1.json` (`MemberNoteDto`, `CreateMemberNoteDto`); `middleware/chmeetings/backend_connector.py:445-470`, `:508-535` |
| F21 | The guardian's name, email and phone are three text fields on the athlete's own profile. Sync joins them into one `parent_info` string. Season reset clears them. | `middleware/config.py:239-241`, `:284-286`, `:418-420`; `middleware/sync/participants.py:1371-1375` |
| F22 | `/send-email` honours `cc` and `bcc`. The email log is optional and is keyed on address and subject, not on athlete. | `plugins/vaysf/includes/rest-api/class-vaysf-rest-email.php:44-60`; `plugins/vaysf/includes/functions.php:803-823`; `plugins/vaysf/vaysf.php:800-811` |
| F23 | There is precedent for the middleware guarding a value against a Church Rep's later edit in ChMeetings: the membership-claim freeze. | `middleware/sync/participants.py:1067-1106`, `:1254` |
| F24 | Nothing in the repo records a check-in. The only trace is a comment about a future QR prefix. | `middleware/config.py:451-456` |

**What follows from F1–F7 for a hold.** A hold that is only "Box 2 unticked" is undone
the same night by `check-consent` (F6). A hold that is only a validation issue is
closed by the next sync, by a 404, by an alias merge or by one click (F5). A hold on an
approved athlete changes nothing any consumer reads, because they all read
`approval_status` (F4, F11–F15). A guardian's replacement form can lose the tie-break to
the form it replaces (F7). The design has to close each of these.

---

## 2. The eight §9.4 questions

This section explains the design alternatives. See §8 for the approved answers and rollout checks.

### Q1. Event-day check-in does not exist. Who updates the list and relays late changes?

See M4 for event-day ownership.

What exists today for the person at the door: the badge image (F11), the public badge
page (F13), the church-team workbook, and score sheets that strike unapproved rows
(F15). `docs/USAGE.md:787-788` tells operators "A badge existing means the athlete is
eligible." That sentence stops being true the moment a hold can be placed after a badge
is issued, and it must be rewritten.

Proposed mechanism:

- One source: the hold state in WordPress (§3).
- `python main.py consent-hold list` writes a staff-only workbook, "Consent Hold List",
  with church, name, ChMeetings ID, hold date, badge issued yes/no and what is still
  needed. It goes to the staff export folder, never to a church folder.
- A read-only plugin admin page, "Consent Holds", shows the same list live so the
  check-in lead can refresh it on a phone.
- Score sheets print `CONSENT HOLD` on the struck row (§4, C9), so a court coordinator
  sees it without the list.

Options for ownership:

| Option | Who updates | How a late change reaches the door |
|---|---|---|
| A | Operator only, printed list | Reprint and hand over |
| B | Operator places and clears; check-in lead reads the live page | Operator messages the lead to refresh |
| C | Any VAY Staff member with a WordPress login places and clears | Live page |

**Recommendation: B.** It needs one writer and no new permissions in 2027, and the list
at the door is never older than a refresh. Print the list the evening before as the
fallback for a WordPress outage.

### Q2. Badge issuance is not recorded. What counts as issued?

See M2 for the issuance rule.

What exists: with `--write-chmeetings-badge-url` the hosted URL is written to the
profile field "Sports Fest Badge URL" (`middleware/badges/runner.py:147-149`,
`:221-258`). That is not a usable issuance record: it is optional, it has no season,
and season reset does not clear it because its field ID is configured as 0
(`middleware/config.py:288`, `:422`).

Proposed definition: a badge is **issued** the first time a badge image for this
season leaves the operator's control, which is the earlier of

1. the PNG being written under `EXPORT_DIR/<church>/badges` (the default output,
   `middleware/main.py:2591-2592`), if that folder is shared with the church, and
2. a successful upload to WordPress (`middleware/badges/runner.py:144-146`).

A `--dry-run` and a scratch `--output` render are not issuance.

Proposed record: `badge_issued_at` on the athlete's WordPress row, set once by
`BadgeRunner` and never cleared during the season, including when the hosted image is
later withdrawn. A screenshot or printout cannot be recalled, so "was a badge ever
obtainable" is the fact the clearing rule needs.

**Recommendation:** treat a render into the church folder as issuance. It is the
conservative reading, and it makes the rule independent of whether `--upload` was used.

### Q3. "Appears to belong to the athlete" needs a definition and an override.

See M7 for the approved guardian email rule.

Data available at sync time without any new call: the athlete's email is the person's
core `email` (`middleware/sync/participants.py:1356`) and the guardian's email is the
custom field `CHM_FIELDS["PARENT_EMAIL"]` (`middleware/config.py:240`).

Proposed definition, for a minor who still needs consent:

| Gate state | Test | Effect |
|---|---|---|
| `missing` | guardian email blank, or not a syntactically valid address | ERROR issue `guardian_email_missing`; athlete cannot advance; no reminder |
| `same_as_athlete` | guardian email equals athlete email after `normalize_text` (`middleware/sync/identity_scoring.py:49-50`) | ERROR issue `guardian_email_matches_athlete`, unless the Church Rep has confirmed it; no reminder until then |
| `ok` | anything else | reminder may be sent |

Equality is the only test that blocks. A "looks like the athlete" heuristic (the
athlete's name inside the address, a school domain) would flag real parents who share a
surname, so it is not proposed, even as a warning.

"Cannot advance" needs no new machinery: an ERROR issue keeps the athlete at `pending`
(F3), so no pastor token is generated (`middleware/sync/manager.py:169-175`).

Override options:

| Option | How the Church Rep confirms | Cost |
|---|---|---|
| A | A new option on the Completion Check List: "7. Parent or guardian email confirmed (minors)" | One option added in ChMeetings; two constants in `config.py`; arrives in the existing `completion_checklist` string; reset and archived with the checklist (F19) |
| B | The rep edits the guardian email to a different address | Nothing to build, and no way to say "it really is the parent's" |
| C | Staff record the rep's word with a command | Rep cannot self-serve; one more staff task per family |

**Recommendation: A**, with B still working when the address really is wrong. The label
must not contain a comma, because the checklist is a comma-joined string
(`middleware/config.py:213`). The gate applies only while consent is still needed (as D8
scopes the reminder). Once a guardian-signed form is on record, that form carries the
guardian's own name, email and phone (`middleware/sync/consent_checker.py:39-41`).

### Q4. Where does staff-recorded replacement consent live?

See M8 for the approved filing and access rules.

The only state the next sync will not undo is Box 2 (F1). So a staff-accepted copy is
recorded as three things, written by one command (`consent-hold accept-copy`):

1. **Box 2 ticked** on the athlete's profile, with the same payload shape
   `check-consent` uses (`middleware/sync/consent_checker.py:277-291`). The next sync
   recomputes `consent_status` as true from it.
2. **A restricted acceptance record** naming who accepted the signed copy and when.
   File it with the copy. An ordinary profile note may carry a minimal status marker only (M8).
3. **Working state** in WordPress: `consent_signer = 'staff_copy'` and a timestamp (§3),
   so the hold logic can tell that replacement consent is on record.

The signed copy stays in restricted storage. Confirm visibility before writing a profile status marker (M8).

### Q5. Where is "reminder sent" recorded?

**Decidable from the code.**

Two columns on the athlete's WordPress row: `guardian_notice_at` and
`guardian_notice_key` (§3). They survive a resync because sync never sends them (F18),
and they end with the season when the table is truncated, which is what "once per minor
per season" needs.

The key is what stops a second email when the same child appears under a new ChMeetings
ID before anyone has written an alias. It is
`sha256(season | guardian email | birthdate | first name)`, all normalised. Before
sending, the middleware looks for that key on any row, `merged` rows included. First
name is in the key so that twins, who share a guardian and a birthdate, each get their
reminder. If the key is ever wrong, it fails towards one extra email, not a missing one.

Send-once is made safe against a half-finished run by claiming first: write the key,
send, then write the timestamp. A row with a key and no timestamp means "claimed, outcome
unknown"; it is not retried and it is shown to staff in the export.

The email log cannot do this job: it is optional and not keyed on the athlete (F22).

### Q6. Which ID carries consent and hold?

**Decidable from the code**, with one sub-decision (M11).

The ChMeetings ID. Hold state lives on the WordPress row for that ID and moves with the
alias map, which only the middleware can read:

- **At merge time.** `apply-aliases --execute` copies hold, reminder and badge markers
  from the stale row to the canonical row *before* the tombstone write
  (`middleware/sync/alias_reconciler.py:308-316` is the tombstone). If the copy fails,
  the entry is skipped and reported, as a failed tombstone is today. The stale row's
  hold is then marked `carried`.
- **Conflict rule.** Active beats cleared and beats empty. Earliest `badge_issued_at`
  wins. Earliest reminder wins. This is RFC §9.4 item 6's "keep an unresolved hold
  active if records conflict".
- **At read time.** When sync loads the canonical row it also loads the rows of every
  stale ID that aliases to it, and treats an `active` (not yet `carried`) hold on any of
  them as active. This covers an alias that was added but not yet applied.
- **Clearing** clears every `active` row in the alias group, so a stale row cannot
  re-impose a hold that staff lifted.

Valid consent (D9) already carries for forms (F9). For a stale Box 2 tick, verify how the consent was recorded. `check-consent` may tick the canonical profile when
same-season consent is verified and the alias group has no active hold. Send a tick
with unknown provenance to staff review (M11). `check-consent` already owns Box 2 writes and
already loads aliases (`middleware/sync/consent_checker.py:239`); `apply-aliases` keeps
its "WordPress only" contract (F10). The reminder is suppressed for a canonical row
whose alias group already has consent, so a guardian is never asked twice.

### Q7. Age bands in code.

**Decidable from the code**, with one sub-decision (M1).

One helper, used everywhere a minor rule is applied: `is_minor_at_event(birthdate)`
returning `True`, `False` or `None`, defined as `age < 18` with no lower bound. It
replaces the four computations in F16 and reads one event date.

- Ages 10–12 need no special case; the only thing that distinguishes them today is the
  minimum-age rule for their event (`middleware/validation/summer_2026.json`, rules
  `MIN_AGE_DEFAULT` and `MIN_AGE_SCRIPTURE`), which is independent of consent.
- An unknown or unparseable birthdate returns `None`. Today the consent check then
  falls to WARNING (`middleware/validation/individual_validator.py:355`); a missing
  birthdate is already an ERROR on its own (`:74-75`). For hold, gate and badge
  purposes `None` is treated as "not known to be an adult": a hold may be placed, and
  the badge tag should say so instead of silently omitting "Minor"
  (`middleware/badges/generator.py:421-432`).
- The event runs over several days. "Under 18 at the event" should mean under 18 on the
  **first** day, so an athlete who turns 18 on day two is treated as a minor (M1).

### Q8. Downstream eligibility.

**Decidable from the code**, with one sub-decision (M9). The full list is §4. The
principle: no consumer may read `approval_status == approved` as "may take part" any
more. Each calls one function that returns `cleared`, `CONSENT HOLD` or the approval
status, and pastor approval is never rewritten.

---

## 3. State and storage

### 3.1 Where each thing lives

| Item | Record (ChMeetings) | Working state (WordPress) | Key |
|---|---|---|---|
| Signed consent | Consent-form submission; Box 2 (checklist option `199609`, `middleware/config.py:389`) | `consent_status` mirror (existing) | ChMeetings person ID |
| Who signed, and when | The form submission | `consent_signer`, `consent_evidence_at` (new) | ChMeetings person ID |
| Hold | Restricted staff audit, with an optional minimal profile status marker (M8) | `consent_hold`, `consent_hold_at` (new) | ChMeetings person ID |
| Replacement consent accepted by staff | Box 2 plus the restricted acceptance record (M8) | `consent_signer = 'staff_copy'` | ChMeetings person ID |
| Guardian contact | The three parent fields (F21) | `parent_info` mirror (existing) | ChMeetings person ID |
| Guardian address confirmed by Church Rep | Checklist option 7 (new option, M7) | part of `completion_checklist` (existing) | ChMeetings person ID |
| Reminder sent | none (not a consent record) | `guardian_notice_at`, `guardian_notice_key` (new) | ChMeetings person ID, plus the key in Q5 |
| Badge issued | none | `badge_issued_at` (new) | ChMeetings person ID |

Every staff action also writes one row to a restricted, git-ignored audit workbook named `consent_hold_<timestamp>_audit.xlsx`, following
`apply-aliases` (`middleware/sync/alias_reconciler.py:26-42`; ignore rule at
`.gitignore:243`).

### 3.2 The new columns

Seven nullable columns on `sf_participants`, added the way `consent_status` was
(`plugins/vaysf/vaysf.php:928-934`), with `DB_VERSION` going from 1.0.13 to 1.0.14
(`plugins/vaysf/vaysf.php:26`).

| Column | Type | Values | Written by |
|---|---|---|---|
| `consent_hold` | `VARCHAR(20) NULL` | `NULL`, `active`, `cleared`, `carried` | `consent-hold` command; sync (rep clear only); `apply-aliases` (carry) |
| `consent_hold_at` | `DATETIME NULL` | when the hold was placed | same |
| `consent_signer` | `VARCHAR(20) NULL` | `guardian`, `self`, `staff_copy`, `staff_reviewed` | `check-consent`; `consent-hold` command |
| `consent_evidence_at` | `DATETIME NULL` | submission date of the form, or time of the staff action | same |
| `guardian_notice_at` | `DATETIME NULL` | when the reminder was sent | reminder step |
| `guardian_notice_key` | `CHAR(64) NULL` | dedupe key (Q5) | reminder step |
| `badge_issued_at` | `DATETIME NULL` | first issuance this season | `BadgeRunner` |

Why columns on this row and not a new table:

- The row is already unique per ChMeetings ID and cannot be deleted (F18), so it gives
  the key the epic asked for without a second table to keep in step.
- GET already returns `p.*`, and the update handler writes only what it is sent (F18),
  so the participant sync cannot overwrite these columns by accident. The create and
  update handlers each need one whitelist entry per column, following the
  `consent_status` pattern (`plugins/vaysf/includes/rest-api/class-vaysf-rest-participants.php:297-299`, `:455-459`).
- They have the same life as `membership_claim_at_approval`: per athlete, per season,
  gone when the table is truncated (`docs/SEASON_TRANSITION.md:351-362`).

On the epic's domain-model guard ("nothing in Track R may stuff role-specific fields
into the participant row"): none of these columns holds guardian or registrant data.
They are the athlete's own consent and eligibility markers for the season. Guardian
contact stays in ChMeetings (D6). The alternative, a table `sf_consent_state` keyed on
`chmeetings_id`, was considered and is the right shape if #314's schema work later
creates role and contact tables; for 2027 it adds a controller and joins with no gain in
safety.

A ChMeetings custom field as the authoritative hold flag was also considered and
rejected: a Church Rep who can tick the checklist can presumably edit it
(**unverified**), and the API gives no author for a field change, so the "staff only
after a badge is issued" rule could not be enforced there.

### 3.3 How each item survives

| Item | Resync | Season reset | Alias merge |
|---|---|---|---|
| Box 2 and `consent_status` | Recomputed from Box 2 every sync (F1). With a hold active, sync writes the *effective* value, false. | Box 2 is archived in the season note, then cleared (F19). | A matching form is credited to the canonical person (F9). Rep-ticked consent carries by the `check-consent` carry pass (Q6). |
| Hold | Not in the sync payload (F18). Sync changes it in exactly one case: the rep-clear transition T4. | Ends with the season when `sf_participants` is truncated. The archive note must first gain a "Consent hold" line (`middleware/season_reset.py:117-141` is where WordPress fields enter the note). Hold notes stay on the profile. | Copied to the canonical row before the tombstone; active wins; read-time check covers an unapplied alias (Q6). |
| Signer evidence | Written only by `check-consent`, and only when the form is newer than what is stored, so a staff decision is not overwritten by the form it reviewed. | Truncated. The form submissions themselves are a ChMeetings retention question (M12). | Evidence found on a `merged` row is written to the canonical row (extends F9). |
| Reminder marker | Not in the sync payload. | Truncated; next season sends once again. | Stays on the tombstone, which the key lookup still sees; also copied at merge. |
| Badge issued | Not in the sync payload. | Truncated. Hosted PNGs and the profile's badge URL are *not* cleaned today (F12, Q2) and need a reset step (§7, R5). | Earliest value copied to the canonical row. `apply-aliases` already reports the stale badge filename (`middleware/sync/alias_reconciler.py:265-277`, `:475`). |
| Staff acceptance of a copy | Box 2 keeps it true on every sync. | Note stays; Box 2 is archived then cleared. | Note stays on the profile it was written to; the carry pass writes a note on the canonical profile. |

A merge done in the ChMeetings UI is a different event from an alias. What happens to
Box 2, custom fields and notes on the losing profile is **unverified**. The design does
not depend on it: the hold is in WordPress and follows the alias the operator writes
after the merge.

### 3.4 States and transitions

Hold states: none, **flagged** (an open issue, not a hold), **active**, **cleared**.

| # | From | To | Trigger | Who may | Preconditions | Writes |
|---|---|---|---|---|---|---|
| T1 | none | flagged | `check-consent` finds a self-signed form whose match to a minor has an identity anchor | system | minor at the event; match includes birthdate or exact name (`middleware/sync/identity_scoring.py:132-134`) | `consent_signer = 'self'`, `consent_evidence_at`; sync raises `minor_self_signed_consent` |
| T2 | flagged | none | `consent-hold dismiss-flag` | VAY Staff | reason given (for example "parent chose the wrong option; confirmed by phone") | `consent_signer = 'staff_reviewed'`, `consent_evidence_at = now`; note |
| T3 | none or flagged | active | `consent-hold place` | VAY Staff | row exists and is not `merged`; athlete is a minor or of unknown age (`--force` otherwise) | in this order: `consent_hold = 'active'`, `consent_hold_at`; Box 2 unticked in ChMeetings; note; hosted badge withdrawn if one was issued |
| T4 | active | cleared | sync sees Box 2 re-ticked | **Church Rep**, by ticking Box 2 | `badge_issued_at` is empty; replacement consent is on record: `consent_signer` is `guardian` or `staff_copy` and `consent_evidence_at` is later than `consent_hold_at` | `consent_hold = 'cleared'` on every active row of the alias group; note "cleared by Church Rep (Box 2)" |
| T5 | active | active | sync sees Box 2 re-ticked and a T4 precondition fails | nobody | none | nothing changes; the hold issue text says which precondition failed |
| T6 | active | cleared | `consent-hold clear` | **VAY Staff**, before or after a badge | replacement consent on record, or `--accept-copy` records it in the same run | Box 2 ticked; `consent_hold = 'cleared'` across the alias group; note |
| T7 | active | carried, and active on the canonical row | `apply-aliases --execute` | operator | alias confirmed and canonical verified as today | Q6 |
| T8 | cleared | active | `consent-hold place` again | VAY Staff | as T3 | as T3 |

Points that are easy to miss:

- **T3 writes WordPress first.** That is the write every consumer keys off, the same
  ordering `apply-aliases` uses for the tombstone
  (`middleware/sync/alias_reconciler.py:305-331`). If the ChMeetings writes then fail,
  the athlete is already held and the command reports what is left to redo. It is safe
  to rerun.
- **T3 unticks Box 2 on purpose.** ChMeetings is what the Church Rep looks at, and it
  should stop asserting a consent that staff have found invalid. It also makes
  re-ticking a deliberate act with a date, which T4 can test.
- **The Church Rep never touches hold state directly.** Their one act is the one they
  already know: ticking Box 2. Whether that clears the hold is decided by the
  middleware from T4's preconditions. After a badge is issued the same tick does
  nothing (T5), which is the "only VAY Staff" rule.
- **VAY Staff** means a named, authorized operator. The command's `--by <name>` records attribution (M8).
- **Pastor approval is not in this table.** No transition reads or writes
  `approval_status`. An athlete at `pending_approval` when a hold is placed drops to
  `pending` through the ordinary ERROR path (F3) and returns to `pending_approval` on
  the first sync after the hold clears. An outstanding token stays valid; if the pastor
  uses it, the approval is recorded (F17) and the hold still blocks. That is D5.

### 3.5 What sync does with a hold

In `_sync_single_participant`, after the WordPress row is loaded
(`middleware/sync/participants.py:916-917`) and before validation (`:1112`):

1. Resolve the hold for the alias group (Q6).
2. If the hold is active and Box 2 is ticked, test T4. If it passes, clear and carry on
   as if there were no hold.
3. If the hold is still active, set the mapped `consent_status` to false. This is the
   **effective** consent that is written to WordPress and validated.
4. Pass the hold, signer evidence and guardian email to the validator as extra fields.
   The `Participant` model already allows extras (`middleware/validation/models.py:34`).
   They are validation context only and are not added to the WordPress payload.

The validator gains three checks, each with its severity in the rules JSON:

| Issue type | Rule code | Severity | Raised when |
|---|---|---|---|
| `consent_hold` | `CONSENT_HOLD` | ERROR | hold active. Replaces `missing_consent` for that athlete so the rep sees one clear reason. |
| `minor_self_signed_consent` | `CONSENT_MINOR_SELF_SIGNED` | WARNING | minor, `consent_signer = 'self'`, no hold yet. This is #317's flag. |
| `guardian_email_missing`, `guardian_email_matches_athlete` | `GUARDIAN_EMAIL_REQUIRED`, `GUARDIAN_EMAIL_DISTINCT` | ERROR | Q3's gate. |

Because sync regenerates these from stored state on every pass, the auto-resolve in F5
closes them only when the state itself has changed. That is the property the RFC's
fact-check said #317 was missing.

### 3.6 What `check-consent` changes

| Today | Proposed | Why |
|---|---|---|
| Any best match at or above threshold ticks Box 2 (F6). | A Box 2 write needs an identity anchor and an unambiguous match. Tied athletes and conflicting birthdates go to review. | A guardian's form for one child can tick a sibling's Box 2 on shared phone and email alone. Changes the behaviour pinned by `test_check_consent_phone_plus_email_is_above_threshold` (`middleware/tests/test_consent_checker.py:184`). M6. |
| Signer type affects only the threshold (F8). | Minor plus self-signed plus reliable match: leave Box 2 as found, store the evidence, and flag it for staff review. | The system should not create an attestation from a form that says a minor signed alone. M5. |
| Highest score wins among rows for one participant (F7). | Among anchored rows, guardian-signed is preferred, then the latest. | Otherwise the replacement form loses to the form it replaces. |
| Box 2 is ticked whatever else is true. | With a hold active: evidence is stored, Box 2 is not ticked. | The Church Rep (T4) or staff (T6) clears. |
| Nothing is stored about the signer. | `consent_signer` and `consent_evidence_at` written to the matched row; for a `merged` match, to the canonical row. | #317 needs it where the validator can read it. |

`"Select one:"` and the other export column names are literals today
(`middleware/sync/consent_checker.py:32-43`). D1 will reword that question, so they move
to a `CONSENT_FORM_COLUMNS` mapping in `config.py` in the same change, and the signer
test stops treating every unrecognised answer as "self"
(`middleware/sync/consent_checker.py:56-62`): an answer that matches neither known
option becomes `unknown` and is flagged, not assumed.

---

## 4. Eligibility consumers

Every place found that treats pastor approval or consent as eligibility. "Hold" below
means the alias-group hold from §3.

### 4.1 Middleware

| # | Consumer | Where | Today | Change |
|---|---|---|---|---|
| C1 | Badge selection | `middleware/badges/runner.py:36`, `:297-325`, `:402-404` | Every `approved` row gets a badge. | Skip held athletes and approved minors who still need consent. Report `CONSENT HOLD` or `CONSENT NEEDED` in staff output. |
| C2 | Badge consent and minor tags | `middleware/badges/runner.py:354-359`, `:407-451`; `middleware/badges/generator.py:319-334`, `:412-432`, `:668-677` | Reads Box 2 straight from ChMeetings; computes its own age. | Use effective consent and the shared minor helper. Add the hold to `_RENDER_FIELDS` (`generator.py:78-96`) so a change re-renders. |
| C3 | Badge upload and issuance | `middleware/badges/runner.py:136-150`; `middleware/badges/uploader.py:55-96` | Uploads; records nothing. | Set `badge_issued_at` on first issue (Q2). On a hold, delete the hosted PNG through the existing DELETE route (`plugins/vaysf/includes/badge-hosting.php:26-36`); the uploader needs a delete method. M3. |
| C4 | Badge URL on the ChMeetings profile | `middleware/badges/runner.py:147-149`, `:221-264` | Written after upload when asked. | Not written for a held athlete. When a hosted badge is withdrawn, blank the field so the profile does not show a dead image. |
| C5 | Approved-group sync | `middleware/sync/manager.py:476-483`, `:500-502`, `:567-617`; Excel fallback `:634-703` | Adds every approved, unsynced participant; never removes. | Apply the clearance rule before adding anyone. Remove athletes who lose clearance and reset `synced_to_chmeetings` so eligible athletes can be re-added after clearance. Preserve the approval record (M9). |
| C6 | Pastor token generation | `middleware/sync/manager.py:134-307` | Tokens for `pending_approval`. | No code change needed for the common path: a held or gated athlete is `pending` (F3). Add a guard for the single-ID path (`:148-158`) so the log says why. |
| C7 | Pastor email resend | `middleware/church_teams_export.py:751-776`, `:866-981` | Resends for pending, validated and `reapproval_required`. | Skip held and gated athletes with a log line. D5: they resume at the next gate after the hold clears. |
| C8 | Daily roster export | `middleware/church_teams_export.py:463-480`, `:487-492`, `:514-544`, `:590-611`, `:680-684`; `middleware/church_teams_report.py:699-700`, `:721-723`, `:780-781`, `:883-884` | Shows `Approval_Status (WP)`; counts "Total Approved (WP)". | The athlete **stays** in the export (§9.2). Add a `Clearance` column to Contacts and Roster: `cleared`, `CONSENT HOLD`, `CONSENT NEEDED`, or the approval status. Add a `Consent Hold` detail column: what is needed and from whom. Summary gains "Total On Consent Hold"; "Total Approved" is unchanged because approval is unchanged. |
| C9 | Score sheets (the cleared roster at the court) | `middleware/scoresheets.py:380-398`, `:401-414`, `:900-901`, `:971-972`, `:1112-1113` | Strikes a row unless status is `approved`. | Read `Clearance` first. Strike rows that lack clearance and show `CONSENT HOLD` or `CONSENT NEEDED` as appropriate (the label slot holds 24 characters, `:409-412`). |
| C10 | Sync status machine | `middleware/sync/participants.py:973-979`, `:1131-1144`, `:1338` | §1, F1–F4. | §3.5. Never sets a status because of a hold. |
| C11 | Individual validator | `middleware/validation/individual_validator.py:335-363` | F2. | §3.5; shared minor helper; severity read from the rules file. |
| C12 | `check-consent` | `middleware/sync/consent_checker.py:347-586` | F6–F9. | §3.6. |
| C13 | `apply-aliases` | `middleware/sync/alias_reconciler.py:445-545` | F10. | Q6: carry before tombstone; audit columns for stale hold, stale consent, stale badge issued. |
| C14 | `find-duplicates` | `middleware/sync/duplicate_finder.py:274-280` | Evidence includes approval and consent. | Add hold to the evidence columns so the operator sees it before writing an alias. |
| C15 | Season archive note | `middleware/season_reset.py:108-159` | Checklist, parent info, pastor status. | Add consent signer and hold lines before the table is truncated. |
| C16 | `approval-drift-accept` | `middleware/approval_drift_history.py:424-501` | Restores a prior approval. | No block (approval is not eligibility). Warn when the target is on hold. |

Checked and **not** eligibility consumers, so no change:

- Scheduling and court estimates count every roster entry and say so
  (`middleware/schedule_workbook.py:539-543`). A held athlete still counts for planning.
- Team and church validation exclude only `merged` rows
  (`middleware/sync/manager.py:1175-1183`). A held athlete still counts towards team
  size and non-member limits, since they are expected to play once cleared.
- Box 5 ("Approval from Pastor") and Box 6 are never read or written by the middleware;
  they appear only as labels (`middleware/config.py:219-220`).

### 4.2 WordPress plugin

| # | Consumer | Where | Today | Change |
|---|---|---|---|---|
| P1 | Public badge page, list mode | `plugins/vaysf/includes/shortcodes.php:1255-1269`, `:1297-1332` | Names every `approved` participant of a church. | Omit held athletes and approved minors who still need consent (M10). |
| P2 | Public badge page, photo mode | `plugins/vaysf/includes/shortcodes.php:284-345`, `:1362-1389` | Shows any PNG whose name starts with church and ID. | Same exclusion. The hosted file is also deleted (C3), so a saved link stops working. |
| P3 | Participants REST | `plugins/vaysf/includes/rest-api/class-vaysf-rest-participants.php:58-100` (GET filters), `:257-299` (create), `:339-510` (update) | Whitelisted fields. | Accept the seven columns on create and update; add a `consent_hold` filter to GET. |
| P4 | Admin participants list | `plugins/vaysf/admin/class-vaysf-admin-participants.php:107-130` | Status chip. | Add a `CONSENT HOLD` chip beside the status. |
| P5 | Admin approvals resend | `plugins/vaysf/admin/class-vaysf-admin-approvals.php:33-48`; `plugins/vaysf/includes/functions.php:834-860` | Refuses `merged`. | Refuse a held participant the same way. |
| P6 | Statistics | `plugins/vaysf/includes/class-vaysf-statistics.php:42-50`, `:137-138`; `plugins/vaysf/admin/class-vaysf-admin-dashboard.php:33`, `:72` | Counts approved and consented. | Add "on consent hold" to the admin dashboard. Public counts unchanged. |
| P7 | "Consent Holds" admin page | new | none | Read-only list for the check-in lead (Q1). Capability `sf2025_read`. |
| P8 | Pastor token endpoint | `plugins/vaysf/includes/rest-api/class-vaysf-rest-approvals.php:408-583` | F17. | No change. D5 keeps a pastor's approval on record during a hold. |

Checked, no use of approval or consent, no change: rosters REST and admin, score entry,
results desk, public schedule display.

The public `[vaysf_participants]` list shows each person's approval status
(`plugins/vaysf/includes/shortcodes.php:196-248`). It keeps showing the pastor's status
and never the hold.

### 4.3 The one function

A new pure module, `middleware/sync/consent_state.py`, holds the rule so the consumers
above cannot drift apart:

```python
def clearance(participant: dict, *, hold_active: bool) -> str:
    """'cleared', 'CONSENT HOLD', 'CONSENT NEEDED', or the unapproved status."""

def resolve_group_hold(rows: list[dict]) -> HoldState:
    """Alias-group rule from Q6: active beats cleared beats empty."""

def rep_may_clear(hold: HoldState) -> tuple[bool, str]:
    """T4 preconditions; the string names the one that failed."""
```

Verify the public exclusions for both hold and missing minor consent in P1 and P2. Verify the hold guard in P5 and the dashboard count in P6. These checks are manual until there is a PHPUnit harness (#363).

---

## 5. Test matrix

All in mock mode. Dates assume the fixtures' event date, 2026-07-18
(`middleware/validation/summer_2026.json` metadata;
`middleware/tests/test_identity_drift.py:30`). "Home" names the existing test file the
case belongs in; builders such as `_make_wp_participant` and `_make_chm_person`
(`middleware/tests/test_consent_checker.py:19-60`) are extended, not replaced.

### 5.1 Age

| ID | Scenario | Setup | Expected | Home |
|---|---|---|---|---|
| A1 | Age 10 | born 2016-03-01, Scripture Memorization, no consent | minor; `missing_consent` ERROR; reminder eligible; no age-rule issue | `test_validation.py` |
| A2 | Age 12 in a 13+ sport | born 2014-03-01, Basketball | minor; `age_restriction` and consent issues are independent of each other | `test_validation.py` |
| A3 | Turns 18 the day after | born 2008-07-19 | minor (existing `test_missing_consent_stays_error_until_18th_birthday`, `test_validation.py:502`, moves onto the shared helper unchanged) | `test_validation.py` |
| A4 | Exactly 18 on event day | born 2008-07-18 | adult; missing consent is WARNING; no flag, no gate, no reminder; `consent-hold place` refuses without `--force` | new `test_age_at_event.py` |
| A5 | Unknown birthdate | blank or `2008/07/19` | helper returns `None`; `missing_birthdate` or `invalid_birthdate` ERROR as today; hold may be placed | `test_age_at_event.py` |
| A6 | One answer everywhere | same birthdate through validator, sync, badge runner, export | identical age and minor flag from all four | `test_age_at_event.py` |
| A7 | Turns 18 on day two | first event day is the age cutoff | minor | `test_age_at_event.py` |

### 5.2 Self-signed flag and `check-consent`

| ID | Scenario | Setup | Expected | Home |
|---|---|---|---|---|
| S1 | Minor signs own form | minor; form "self"; name and birthdate match | Box 2 **not** ticked; `consent_signer = 'self'`; audit action `flagged_minor_self_signed`; next sync raises `minor_self_signed_consent` WARNING | `test_consent_checker.py`, `test_validation.py` |
| S2 | Adult signs own form | adult; form "self" | Box 2 ticked as today; no flag | `test_consent_checker.py` |
| S3 | Guardian signs for minor | minor; form "guardian"; name and birthdate only (score 49) | Box 2 ticked; `consent_signer = 'guardian'` | `test_consent_checker.py` |
| S4 | Shared family contacts only | guardian form for child A; child B matches on phone and email only (score 51) | no write for B; audit action `no_anchor` | `test_consent_checker.py` (replaces the expectation at `:184`) |
| S5 | Replacement beats original | same minor; self form scoring 100, later guardian form scoring 49 | guardian form is the one kept | `test_consent_checker.py` |
| S6 | Flag survives sync | S1, then two syncs with no change | issue stays open; not auto-resolved | `test_sync_manager.py` |
| S7 | Staff dismiss the flag | `dismiss-flag`, then `check-consent` on the same export | signer stays `staff_reviewed`; issue resolves; a *newer* self form flags again | new `test_consent_hold.py` |
| S8 | Unrecognised signer answer | "Select one:" reworded | signer `unknown`; flagged for review; not treated as self or guardian | `test_consent_checker.py` |

### 5.3 Hold

| ID | Scenario | Setup | Expected | Home |
|---|---|---|---|---|
| H1 | Place before approval | minor at `pending_approval`, token outstanding | row `active`; Box 2 unticked; note written; next sync: `consent_status` false, `consent_hold` ERROR, status `pending`; token row untouched | `test_consent_hold.py` |
| H2 | Place after approval, no badge | minor `approved` | status stays `approved`; `clearance` is `CONSENT HOLD`; no badge rendered; not added to the approved group | `test_consent_hold.py`, `test_badges.py`, `test_sync_manager.py` |
| H3 | Place after badge issued | `badge_issued_at` set | hosted PNG delete requested; removed from the approved group and `synced_to_chmeetings` reset; `badge_issued_at` unchanged | `test_badges.py`, `test_sync_manager.py` |
| H4 | Next sync does not clear it | H2, Box 2 still unticked, three syncs | hold `active` each time | `test_consent_hold.py` |
| H5 | `check-consent` does not clear it | H2, export still holds the self-signed form | no Box 2 write | `test_consent_checker.py` |
| H6 | Rep re-ticks with nothing on record | H2, Box 2 ticked, signer still `self` | hold `active` (T5); issue text names the missing replacement | `test_consent_hold.py` |
| H7 | Rep clears before badge | H2, guardian form newer than the hold, Box 2 ticked | hold `cleared`; note "cleared by Church Rep"; status `approved` throughout; badge renders on the next run | `test_consent_hold.py`, `test_badges.py` |
| H8 | Rep cannot clear after badge | H3, guardian form newer, Box 2 ticked | hold `active` (T5); text says VAY Staff must clear | `test_consent_hold.py` |
| H9 | Staff clear after badge | H8, then `consent-hold clear` | hold `cleared`; Box 2 ticked; re-added to group on next approval sync; badge re-rendered and re-uploaded | `test_consent_hold.py` |
| H10 | Staff accept a paper copy | H2, `clear --accept-copy` | note written; Box 2 ticked; signer `staff_copy`; hold `cleared`; later syncs keep consent true | `test_consent_hold.py` |
| H11 | Pastor approves during a hold | H1, then token processed | row `approved`; hold `active`; `clearance` is `CONSENT HOLD`; after clear, `cleared` with no new pastor step | `test_consent_hold.py` |
| H12 | Sport change during a hold | H2, primary sport changed in ChMeetings | hold, signer and reminder markers unchanged. Approval follows the drift guard: today the row goes to `reapproval_required` (`participants.py:565-572`, `:1028-1032`); once D2's sync change lands it stays `approved`. Either way no consent question is reopened. | `test_identity_drift.py` |
| H13 | Place is rerunnable | ChMeetings write fails after the WordPress write | athlete held; command exits non-zero; rerun completes without duplicating the note | `test_consent_hold.py` |
| H14 | Score sheet | held athlete on a roster | row struck, label `CONSENT HOLD` | `test_scoresheets.py` |
| H15 | Daily export | held athlete | present in Contacts and Roster; `Clearance = CONSENT HOLD`; counted in "Total On Consent Hold" and still in "Total Approved" | `test_church_teams_export.py` |

### 5.4 Guardian address and reminder

| ID | Scenario | Setup | Expected | Home |
|---|---|---|---|---|
| G1 | Missing guardian email | minor, no consent, field blank | `guardian_email_missing` ERROR; status `pending`; no email | `test_validation.py`, new `test_guardian_notice.py` |
| G2 | Parent's email used for both, no override | athlete email equals guardian email | `guardian_email_matches_athlete` ERROR; no email | same |
| G3 | Same, Church Rep confirmed | G2 plus checklist option 7 | no gate issue; one email, to that address, Church Rep copied | same |
| G4 | Distinct guardian email | | one email; key and timestamp written | `test_guardian_notice.py` |
| G5 | Repeat sync | G4, sync again | no second email | `test_guardian_notice.py` |
| G6 | Consent already present at first sync | Box 2 ticked | no gate, no email | `test_guardian_notice.py` |
| G7 | Same child under a new ID, no alias yet | second row with same guardian email, birthdate, first name | no second email | `test_guardian_notice.py` |
| G8 | Twins | same guardian email and birthdate, different first names | two emails | `test_guardian_notice.py` |
| G9 | Send fails | `/send-email` returns failure | key written, timestamp empty; reported as "outcome unknown"; not retried silently | `test_guardian_notice.py` |
| G10 | Athlete on hold | hold active | no automated email (D3: staff contact the guardian personally) | `test_guardian_notice.py` |
| G11 | Adult | age 18+ | no gate, no email | `test_guardian_notice.py` |

### 5.5 Alias merges

| ID | Scenario | Setup | Expected | Home |
|---|---|---|---|---|
| M-1 | Stale row carried a hold | stale `active`, canonical empty | after `--execute`: canonical `active`, stale `carried`, then tombstone; audit shows the carry | `test_canonical_identity.py` |
| M-2 | Carry write fails | WordPress refuses the canonical update | stale row **not** tombstoned; outcome `error`; rerun completes | `test_canonical_identity.py` |
| M-3 | Records conflict | stale `active`, canonical `cleared` | canonical `active` | `test_canonical_identity.py` |
| M-4 | Alias written, not yet applied | stale `active`; sync of the canonical person | canonical treated as held | `test_consent_hold.py` |
| M-5 | Clear after a merge | M-1, then staff clear | canonical `cleared`; stale stays `carried`; next sync does not re-impose | `test_consent_hold.py` |
| M-6 | Stale row carried valid consent by form | guardian form matches the stale row's details | canonical Box 2 ticked (existing behaviour, F9); signer written to the canonical row | `test_consent_checker.py` |
| M-7 | Stale row carried rep-ticked consent | verified same-season consent, no form, canonical Box 2 empty, no hold in group | carry pass ticks canonical Box 2 and records the source; a tick of unknown provenance goes to staff review | `test_consent_checker.py`, `test_guardian_notice.py` |
| M-8 | Stale consent, but a hold in the group | as M-7 with a hold active | no Box 2 write | `test_consent_checker.py` |
| M-9 | Stale row had a badge issued | stale `badge_issued_at` set | canonical inherits it; rep clear refused (T5) | `test_canonical_identity.py` |
| M-10 | Reminder already sent to the stale ID | stale has key and timestamp | no email for the canonical row | `test_guardian_notice.py` |

### 5.6 Plugin (manual, on staging; no PHPUnit yet)

| ID | Check |
|---|---|
| W1 | After the schema update, `SHOW COLUMNS` lists the seven columns, all NULL; an existing sync run changes none of them. |
| W2 | PUT with `consent_hold` sets it; a PUT without the key leaves it; PUT with `null` clears it. |
| W3 | `[vaysf_badges]` list and photo modes omit a held athlete and show them again after clearing. |
| W4 | Admin approvals "resend" refuses a held participant. |
| W5 | "Consent Holds" page lists exactly the rows with `consent_hold = 'active'` and is not reachable without `sf2025_read`. |

---

## 6. Implementation plan

Ordered so that each step is reviewable on its own and nothing blocks an athlete until
step 6. **Plugin** steps need `.\scripts\lint-php.ps1` to pass (CLAUDE.md, Testing), a
rebuilt `plugins/vaysf.zip` at release, and the manual checks in §5.6, because there is
no PHPUnit harness (#363).

| Step | Issue | Change | Touches | Behaviour change |
|---|---|---|---|---|
| 1 | #318, refs #69 | One age helper and one event-date accessor; the four call sites in F16 use it; a warning when the rules date and `Config.SPORTS_FEST_DATE` differ. Tests A3–A7. | middleware | none when the two dates agree, as they do today |
| 2 | #318 | Consent severity moves into the rules file (one rule for minors at ERROR, one default at WARNING); validator reads it; `docs/PRD.md:233-234` aligned. | middleware, rules JSON, docs | none |
| 3 | #317, #318 | Seven columns, `DB_VERSION` 1.0.14, REST whitelist and filter (P3). Check W1–W2. | **plugin** | none |
| 4 | #317, #318 | `consent_state.py` (§4.3) with unit tests; `Clearance` and `Consent Hold` columns in the export (C8), all blank or `cleared` until a hold exists. | middleware | two new export columns |
| 5 | #317 | `check-consent`: column mapping in `config.py`, signer `unknown`, anchor rule, guardian-first tie-break, signer evidence stored, no Box 2 write for a self-signed minor; validator raises `minor_self_signed_consent`. Tests S1–S8. Implements M5 and M6. Verify the export and replay before rollout. | middleware, rules JSON | fewer automatic Box 2 ticks |
| 6 | #318 | `consent-hold` command (`place`, `clear`, `accept-copy`, `dismiss-flag`, `list`, `list --verify`), dry-run by default as `apply-aliases` is; sync honours the hold (§3.5); `consent_hold` rule. Tests H1, H4–H13. Implements M4 and M8. | middleware, rules JSON | holds can exist |
| 7 | #318 | Middleware consumers: badges (C1–C4, with `badge_issued_at`), approved group (C5), resend paths (C6–C7), score sheets (C9), drift-accept warning (C16). Tests H2, H3, H14, H15. Implements M2, M3, M9 and the badge rules in M10. | middleware | held athletes lose badge and group membership |
| 8 | #318 | Plugin consumers: P1, P2, P4–P7. Checks W3–W5. Implements M10. | **plugin** | held athletes leave the public badge page |
| 9 | #315 | Guardian-address gate: two rules, checklist option 7 in `CHECK_BOXES` and `SF_CHECKLIST_OPTIONS`, field inspector run. Tests G1–G3, G6, G11. Implements M7. Create the option in ChMeetings first. | middleware, rules JSON | minors with no usable guardian email stop at `pending` |
| 10 | #315 | Reminder: bilingual template, claim-then-send marker, Church Rep copied, off by default behind a config switch until the wording is approved. Tests G4–G10. | middleware | one email per minor |
| 11 | #318, Track A | `apply-aliases` carry, `check-consent` carry pass, `find-duplicates` columns, season archive lines (C13–C15). Tests M-1 to M-10. Implements M11. | middleware | merges keep holds |
| 12 | all three | `docs/USAGE.md` (commands; rewrite `:787-788`), `docs/TROUBLESHOOTING.md` (hold playbook), `docs/SEASON_TRANSITION.md` (M12; delete hosted badges at reset), `CLAUDE.md` and `AGENTS.md` (form-export wording, §7 R8; new doc in the layout list), `CHANGELOG.md`. | docs | none |

Step 1 in enough detail to start: add `middleware/validation/age.py` with
`event_date() -> date` (the body of `IndividualValidator._parse_event_date`,
`individual_validator.py:25-40`, including its fallback and warning),
`age_at_event(birthdate) -> Optional[int]` (the arithmetic at `:62-68`, tolerant of the
`T` and space suffixes handled at `participants.py:432`) and
`is_minor_at_event(birthdate) -> Optional[bool]`. Replace
`IndividualValidator._calculate_age`, `ParticipantSyncer._age_at_event`,
`BadgeRunner._age_at_event` and `ChurchTeamsExporter._calculate_age` with calls to it,
keeping each method name as a thin wrapper so existing tests and the drift guard
(`participants.py:593-594`) are untouched. The existing tests must pass unchanged; add
A4–A6.

Ordering notes:

- M1–M12 are approved in §8. See [rollout follow-through](#follow-through-before-rollout)
  for the remaining verification and operator tasks.
- Steps 3 and 8 are the only plugin changes. Step 3 must be deployed before step 5 is
  run: the update handler ignores keys it does not know, so signer evidence written to
  an older plugin would be dropped without an error.
- Registrations opened on 22 April in 2026 (`docs/RETROSPECTIVE_2026.md:49`). Steps 5,
  9 and 10 depend on form and checklist changes (D1, option 7) that should be in place
  before the form opens.

**Not in these three issues, but D2 depends on it:** "change sync so sport-only changes
preserve pastor approval" (RFC §5, Q5). Today a sport change by an approved athlete is a
hard drift (`middleware/sync/participants.py:565-587`, `:1028-1032`). The natural home
is #212, which is still open. Test H12 is written so it holds before and after.

**#319 (consent drift): close as not planned.** D2 decided there is no consent drift,
and §9.2 replaces it. Nothing in its scope survives: no sibling issue type in the drift
machinery, no extension of `approval-drift-accept` to a guardian's authority. Close it
with a link to RFC §9.1 D2–D3 and to this memo.

**#314's schema memo.** The epic made #314's schema recommendation a gate on #315's
storage. For 2027 that gate is met by §3 of this memo: #315 stores no new contact data
(it reads the guardian email from the existing ChMeetings field), and the consent and
hold state is specified here. Recommended: record that on #314, remove the dependency
from #315, and leave #314 open and deferred with what remains of it, which is the
verification page and the role and contact schema for *verified* contacts. That work
should start from §3.2's rejected alternative.

**Issue bodies.** #315, #317 and #318 were written before the fact-check and the
decisions. They still say consent is a WARNING for everyone, that `age_at_event` is
computed for every participant, and that #315 includes a consent-capture page. Replace
each body's scope with the matching steps above before work starts. #108 overlaps step
10 (send-once email, Church Rep copied); its statement that `/send-email` ignores `cc`
is no longer true (F22).

---

## 7. Risks and non-goals

### 7.1 Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **A badge that has left the building cannot be recalled.** A screenshot or printout still looks valid. | The hold list and score sheets are the authority, not the badge (Q1). Rewrite `docs/USAGE.md:787-788`. |
| R2 | **The hold lives in WordPress.** A restore or a mistaken truncation mid-season loses it. | Every placement also writes a restricted audit row and may write a minimal ChMeetings status marker (M8); `consent-hold list --verify` compares WordPress against the audit workbooks and reports a hold with no row. It does not read notes for state, because `get_person_notes` reads one page (F20). |
| R3 | **The Church Rep can re-tick Box 2.** | By design that is a request, not a clear (T4, T5). The export says in words why a re-tick did nothing. |
| R4 | **Signer type is self-declared** (F8). A minor who picks "parent or legal guardian" is not flagged. | Out of reach of code. D1's wording helps the honest case; the Church Rep's Box 2 attestation and staff confirmation remain the check. |
| R5 | **Old badges look current.** Filenames have no season, the gallery globs by prefix, and reset does not clear hosted files or the profile's badge URL (F12, Q2). A returning athlete, once approved in 2027, shows a 2026 badge until a new one is rendered. | Add "delete hosted badges" and "set `SF_FIELD_IDS['BADGE_URL']`" to the season reset steps (step 12). `badge_issued_at` is a recorded fact for this reason, not inferred from a file. |
| R6 | **Two event dates** (F16). A hold or reminder could use a different age from the validator. | Step 1. |
| R7 | **No plugin tests** (#363). | Two small plugin steps; the eligibility rule lives in the middleware; §5.6 is the manual list. |
| R8 | **The form export becomes more important.** `check-consent` already reads the Playwright export every night (`middleware/daily-run.bat:15-19`), and #317's flag has no other source. CLAUDE.md says that helper is "never a dependency of sync/validation/approval logic". | Require a successful refresh before `check-consent` takes new action. Ordinary sync continues and existing holds stay in force. The rep-clear path needs fresh evidence, so without an export it waits for staff. The CLAUDE.md sentence should be amended to say so (M12). |
| R9 | **Email delivery** is `wp_mail` on shared hosting (F22). A reminder can be accepted and never arrive. | Turn on `vaysf_log_emails`; the export shows "reminder sent on"; the Church Rep is copied and remains the human follow-up. |
| R10 | **A ChMeetings UI merge** may move or drop Box 2 and notes (unverified). | Hold is in WordPress and follows the alias (§3.3). Add "check the survivor's Box 2 and notes" to the merge playbook. |
| R11 | **Placing a hold is easy to do to the wrong person** with a mistyped ID. | Dry-run by default; the command prints name, church, birthdate and age and requires `--execute`; `--by` and `--reason` are mandatory. |
| R12 | **Warn-and-continue.** Nothing here may stop the nightly run. | Every failure is per athlete and fails closed for that athlete only: a failed note write leaves the hold in place and is reported; a failed email is reported; no step raises out of the batch. |

Found in passing and outside this work: the validation admin page resolves and reopens
issues from a GET link with no nonce, and builds its status filter into SQL by string
(`plugins/vaysf/admin/class-vaysf-admin-validation.php:33-65`); the approvals page
resends from a GET link the same way (`class-vaysf-admin-approvals.php:33`). This is one
more reason the hold is not a validation issue, and it deserves its own issue.

### 7.2 What this design deliberately does not do in 2027

- **No SMS** and no verification page (D7; #313 and #314 stay deferred).
- **No consent capture inside WordPress.** The guardian signs the existing ChMeetings
  form, or staff accept a copy. WordPress never stores a signature, a release text or a
  scan.
- **No automatic hold.** The flag proposes; staff confirm (D3). Same spirit as guardrail
  G3 in the Canonical Identity RFC.
- **No change to what pastor approval means**, and no new `approval_status` value. That
  avoids a second sweep of every status whitelist of the kind `merged` needed (#309).
- **No cross-season identity.** Hold, reminder and badge markers end with the season.
  What carries across seasons is only what is already in ChMeetings: forms and notes.
- **No relationship verification.** The gate checks that a guardian address exists and
  is not simply the athlete's; it does not prove who owns it.
- **No writes to `/families`**, and no dependence on household records (D11).
- **No check-in application**, QR scanning or attendance record. Q1 gives the manual
  check-in a correct list.
- **No automated message to the guardian when a hold is placed.** Staff make that
  contact personally (D3, D8).

### 7.3 Against CLAUDE.md's "What NOT to do"

None of the four prohibitions is crossed: no giving or accounting, no sermon or
discipleship features, no district reporting, nothing generalised beyond VAY. Three
conventions elsewhere in CLAUDE.md are touched and are named so the conflict is a
decision, not an accident:

1. **The form-export helper** (R8).
2. **`CHM_FIELDS` as the only way to name ChMeetings fields.** The consent matcher's
   column names are literals today; step 5 moves them into `config.py`.
3. **Validation changes belong in the rules JSON.** The under-18 split is hard-coded
   today (F2); step 2 moves it, and every new rule in §3.5 takes its severity from the
   file.

---

## 8. Maintainer decisions for 2027

**Approved by Bumble, VAY Sports Fest maintainer, on 2026-11-16.** The answers below govern the implementation plan. The checks and assignments at the end of this section are still pending.

### M1 — Which day determines whether an athlete is under 18 for a multi-day event?

Use the first day of the event. Store it in `metadata.event_date` in the season rules and use it for every age calculation. An athlete who turns 18 on day two follows the minor consent process for that event.

### M2 — When does a badge count as issued?

Record issuance at the first render into a shared church folder or the first successful WordPress upload, whichever comes first. Confirm which church folders Church Reps can access. Dry runs and private test renders do not count.

### M3 — What happens to a badge if staff place a hold after it was issued?

Remove the hosted image and clear the ChMeetings badge URL. If a replacement file is needed in the shared folder, use a neutral invalid-badge notice. Show `CONSENT HOLD` on the staff check-in list and authorized score sheets. Reissue the badge after clearance. The check-in lead consults the live list when someone presents an earlier printout or download.

### M4 — Who owns the hold list on event day and relays late changes?

The authorized operator places and clears holds. A named check-in lead and backup use the live list, and the operator alerts them directly when the list changes. Print a dated copy the evening before as an outage fallback.

### M5 — Should the nightly job tick Box 2 from a minor's self-signed form?

No. When the form reliably matches a minor and identifies that athlete as the signer, leave an unticked Box 2 blank and flag the form for staff review. Preserve an existing tick pending review because valid consent may already be on file. Send unclear signer answers or uncertain age to review when they affect eligibility to sign. Staff confirm the self-signature and place any hold.

### M6 — Should automatic Box 2 ticks require an identity anchor for all athletes?

Yes. Keep the existing score threshold and require a matching birthdate or exact athlete name, with one unambiguous athlete. Send shared phone and email alone, tied matches across distinct athletes, and conflicting birthdates to review. Use the athlete's name where the export supplies it. The signer may be the guardian.

Before enabling this rule, replay the 2026 export against a same-season participant snapshot without writes. Compare old and proposed decisions and count the additional reviews by reason. The July 17 audit contained no fresh automatic ticks and cannot supply a season-wide count.

### M7 — When does guardian email block progress, and what can checklist option 7 override?

Apply the gate to minors who still need consent. A missing or invalid address blocks progress. A Church Rep can confirm that a valid address shared with the athlete genuinely belongs to the parent or guardian. Use **`7. Parent or guardian email confirmed (minors)`** for that confirmation. The rep must confirm again if the address changes.

### M8 — Who accepts signed replacement consent, where is it filed, and who can see the record?

Name the authorized VAY Staff operators. Record who accepted each replacement and when. File the signed copy and acceptance details in a restricted season folder. Use `--by` for attribution.

The VAY SM settings review showed that Church Reps can view and edit ordinary Person Notes. If a profile note is needed, use a minimal status marker. Keep guardian names, document references, and hold reasons in restricted storage.

### M9 — Should the `2027 Sports Fest` ChMeetings group represent athletes currently cleared to participate?

Yes. Exclude held athletes and minors who still need consent. Remove any athlete already added who loses clearance. Restore membership once the athlete is cleared and otherwise eligible. Keep pastor approval on record in WordPress and use the staff check-in list as the event-day authority.

### M10 — Should public badge pages omit athletes on hold and approved minors who still need consent?

Yes. Omit their entries and images from the public badge list and gallery. Use `CONSENT NEEDED` for an outstanding release and `CONSENT HOLD` for a hold staff have placed in the appropriate staff or Church Rep view.

### M11 — Can Box 2 carry to a surviving profile when a confirmed duplicate has no form on file?

Carry verified same-season consent across a confirmed alias. Send a prior Box 2 tick with unknown provenance to staff review. A hold anywhere in the alias group blocks an automatic tick.

### M12 — How do we retain prior-season releases, and which nightly decisions require a fresh export?

Keep prior-season form submissions in ChMeetings if they can be separated by season. If the inbox must be cleared, first verify that the restricted archive is complete and retrievable.

Require a successful export refresh before `check-consent` makes new decisions. If the refresh fails, keep existing consent and hold state in force and let ordinary sync continue. Record this distinction in the runbook, `CLAUDE.md`, and `AGENTS.md`.

### Follow-through before rollout

- **M2–M4:** Confirm which church badge folders are shared. Name the check-in lead and backup and agree how the operator will alert them.
- **M5–M6:** Reword and require the signer question (D1), verify its actual export column and answer values, confirm whether the export includes the athlete's name separately, and review the read-only replay before enabling the new matching rule.
- **M7:** Before registration opens, add checklist option 7 in ChMeetings, record its option ID, and verify Church Rep edit access. Confirm whether the form builder can require guardian email for minors (D12).
- **M8:** Name authorized operators and confirm the season folder and its access. Verify who can see any proposed profile marker before writing it.
- **Step 10:** Approve the bilingual reminder text and sender address before enabling reminders.
- **M12:** Confirm the season retention and retrieval procedure before clearing any submissions.

## Appendix: RFC statements re-checked

| RFC statement | Result |
|---|---|
| §2: missing consent is ERROR under 18, WARNING for adults; severity in the rules file is not read | Confirmed (F2) |
| §2: Box 2 is required for everyone before `pending_approval` | Confirmed (F3) |
| Q1: thresholds 49 and 51; signer type is a substring test | Confirmed (F6, F8) |
| Q3: age is computed in the validator, in sync and in badges | Incomplete: the church-team export has a fourth (`middleware/church_teams_export.py:86-97`). Corrected in the RFC. |
| Q5: the drift guard runs only after the pastor-approval surface is reached | Confirmed (`middleware/sync/participants.py:1010-1025`) |
| Q6: `check-consent` does not apply the anchor rule | Confirmed (F6) |
| §6: `consent_status` is recomputed every sync; an issue not regenerated is auto-resolved | Confirmed, and there are three more ways an issue closes (F5) |
| §6: signer type is not stored | Confirmed (F8) |
| §9.1 D1: `"Select one:"` is a literal | Confirmed, with the other export column names (`middleware/sync/consent_checker.py:32-43`) |
| §9.4 item 1: nothing records a check-in | Confirmed (F24). Score sheets are the nearest thing to a court-side check (F15). |
| §9.4 item 2: badge issuance is not recorded | Imprecise: the optional ChMeetings badge-URL write exists but is not a usable record (Q2). Corrected in the RFC. |
| §9.4 item 6: `check-consent` can redirect to the survivor; `apply-aliases` does not migrate consent or hold | Confirmed (F9, F10) |
| §9.4 item 7: the missing-consent ERROR keys on `age < 18` | Confirmed, with the caveat that an unknown age falls to WARNING (Q7) |
