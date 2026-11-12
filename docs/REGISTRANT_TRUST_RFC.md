# RFC: Registrant Trust — explicit roles, verified contacts, and minor consent

**Status: Draft for review** · Target: 2027 season · Scope: design only, no
production code changes.

*Companion to `docs/CANONICAL_IDENTITY_RFC.md` (approved). That RFC fixes
duplicate identities after they exist; this one is about preventing them at
the source and making the humans around each athlete — parent, Church Rep,
pastor — explicit in the system instead of implicit in text fields. The
onboarding journey in §1 and the six design questions in §5 were supplied by
the maintainer from two seasons of operating the event.*

*Fact-check, 2026-11-12: every statement in this document about what the
codebase already does was re-checked against `main` at v1.1.15. Corrections
are inline and marked "Fact-check"; the design recommendations are unchanged
and are reviewed on epic #307. Track A status at that date: the alias map,
`merged` tombstones and `apply-aliases` (A1–A3, #308–#310) shipped in v1.1.15;
`find-duplicates` and the shared `identity_scoring` module (A4, #311) and the
duplicate tripwires (A5, #312) are not built yet.*

---

## 1. The current athlete onboarding journey (as-is, 2026)

1. **Church enters Sports Fest first.** The Church Rep fills out the
   ChMeetings Church Application Form from the website. The Senior Pastor
   approves and appoints an official Church Representative, who becomes the
   main liaison between VAY-SM, the pastor, the church, and the athletes —
   responsible for communication, athlete coordination, forms, fees, and
   pastor signoff.
2. **Athlete registers online** through the ChMeetings Individual Application
   Form on the Sports Fest website/WordPress flow: name, church/team,
   birthdate, photo/headshot for the ID badge, church membership claim,
   sports selections, and required acknowledgments/releases. Athletes must
   generally be at least 13 and under 35, with exceptions for events like
   Scripture Memorization and Tug-of-War.
3. **Athlete chooses sports/events.** Up to two main events (Primary and
   Secondary), not counting Track and Field and Scripture Memorization. Team
   events allow unlimited athletes within reason; individual events have
   limits Church Reps help enforce.
4. **The system stores/syncs the athlete** through ChMeetings and WordPress.
   ChMeetings holds the person/application identity; WordPress keeps its own
   participant records for workflow, approvals, rosters, badges, scoresheets,
   and views. *This is where duplicate identities enter* — re-registration,
   changing sports by submitting again, delete/re-add.
   *Fact-check: a form submission is not yet a ChMeetings Person. An admin
   promotes it with Bulk Actions → "Add People" (`docs/PRD.md` §5 step 3a,
   #62; the parent/child mis-linking risk at that step is #27), or
   `repair-form-people` creates it. The ChMeetings ID is minted at that
   promotion, and the registrant is invisible to the middleware until it
   has happened and the person is in a `Team` group.*
5. **Church Rep reviews and coordinates corrections** before
   forwarding/signoff — team rules, registration requirements, fees, event
   limits.
6. **Pastor verifies eligibility and church membership.** Every athlete is
   signed off by the Senior Pastor or designee. Non-member participation is
   allowed only within limits and with pastoral endorsement/outreach intent.
7. **If the athlete is under 18, parent/guardian consent is required.** The
   Handbook says the parent/guardian signs the release for athletes under 18,
   and the electronic approval process should send registration to
   parents/guardians when applicable.
8. **Required releases and ID/photo must be complete** — liability release,
   medical release, passport-like headshot for the electronic ID badge,
   media/image rights.
9. **Approved athletes flow into operational outputs** — rosters, badges,
   scoresheets, church team exports, event-day check-in.
10. **Current pain point: identity changes are not cleanly reconciled.**
    Re-registration, sport changes via resubmission, delete/re-add by a rep,
    or a ChMeetings merge leave stale WordPress rows that leak into badges,
    rosters, and scoresheets unless manually cleaned.
    *Fact-check: true of the 2026 season. Since v1.1.15 an operator-confirmed
    alias retires the stale row (`apply-aliases`, #308–#310); finding the
    duplicate in the first place is still manual until #311 and #312 land.*

## 2. Problem statement

> The current journey assumes **"one athlete registration = one real
> person,"** and real life breaks that assumption. The process is
> church-centered with athlete self-registration, plus pastor approval and
> parent consent layered afterward. The future system should make those
> roles explicit instead of treating everyone as just another "participant
> row."

Concretely, three gaps:

- **Identity**: nothing verifies that a registrant controls the contact
  info they submit, so nothing anchors a person across registrations.
  (The Canonical Identity RFC repairs duplicates; this RFC is upstream
  prevention.)
- **Roles**: the parent/guardian exists only as flat text
  (`parent_info` on the WordPress participant; three ChMeetings custom
  fields). The Church Rep and pastor exist as church-level contacts. No
  relationship connects an athlete to their guardian.
- **Consent for minors**: the Handbook *requires* guardian signature for
  under-18. The system never checks that a minor's consent was
  guardian-signed (a 14-year-old self-signing raises no flag), and has no
  way to notify a parent when a minor registers.
  *Fact-check: an earlier draft said the system "treats consent as a WARNING
  for everyone". That is wrong. The rules file lists `CONSENT_REQUIRED` at
  WARNING, but `IndividualValidator._validate_consent` does not read that
  severity: missing consent is an ERROR for anyone under 18 at the event and
  a WARNING for adults (in place since v1.01/v1.02, #12; pinned by
  `test_missing_consent_stays_error_until_18th_birthday`). Separately, Box 2
  of the Completion Check List must be ticked for every participant, adult
  or minor, before sync moves them to `pending_approval`. "Consent" in the
  system today means that one checkbox, ticked by a Church Rep or by
  `check-consent`; who signed is not stored.*

## 3. Goals and non-goals

**Goals**

1. A registrant's key contact (phone and/or email) can be verified, and a
   verified contact becomes a durable identity anchor for duplicate
   prevention and season-over-season continuity.
2. A self-service path lets an athlete *change* their registration (sports,
   corrections) without re-registering — removing the single largest
   duplicate generator.
3. Parents/guardians of minors are notified at registration and can complete
   consent electronically; consent state is enforced according to the
   Handbook, not merely advised.
4. Athlete, Parent/Guardian, Church Rep, and Pastor are explicit roles with
   defined powers, not inferences from text fields.

**Non-goals**

- Replacing ChMeetings registration forms. Registration stays in ChMeetings;
  everything here attaches after or alongside it.
- Payments, accounting, contributions (out of scope for vaysf, per CLAUDE.md).
- Auto-merging identities — inherits guardrail G3 from the Canonical Identity
  RFC verbatim.
- Building for "any church." This stays VAY-specific.

## 4. The explicit role model

| Role | Today | Future |
|---|---|---|
| **Athlete** | The participant row | The person competing; may or may not be the registrant; owns (or shares) a verified contact |
| **Parent / Guardian** | Flat text (`parent_info`; ChM fields 1283265-67) | A linked actor for each minor: notified at registration, signs consent, may be the registrant and the phone owner |
| **Church Rep** | Church-level contact (`church_rep_phone` etc.); operational glue | Unchanged in authority, but the system should distinguish "rep registered/edited this athlete" from athlete self-action |
| **Pastor** | Approval workflow (tokens, email) | Unchanged; approval invalidation rules extended to cover consent-relevant changes |

The load-bearing distinction: **registrant ≠ athlete.** A parent registering
their child and a rep fixing a record are legitimate, common, and currently
indistinguishable from the athlete acting. Making the actor explicit is what
lets verification, consent, and duplicate prevention each attach to the
right person.

## 5. The six open design questions

Each question below is the maintainer's, verbatim in intent; the notes are
what the codebase already tells us, and recommendations where evidence
exists. Final answers belong to the spikes (§7) and decisions (§8).

**Q1 — Who is the actual registrant: athlete, parent, or Church Rep?**
All three occur. The consent pipeline already half-knows this: the consent
form's "Select one:" field distinguishes self vs guardian signer, and the
matcher applies a *lower* confidence threshold to guardian-signed forms
because parents routinely fill the athlete's phone/email fields with their
own contact info. The role model (§4) makes the registrant a recorded fact
instead of an inference.
*Fact-check: confirmed. The thresholds are 49 (guardian) and 51 (self) in
`sync/consent_checker.py`; signer type is a substring test on the "Select
one:" answer and is self-declared by whoever fills in the form.*

**Q2 — Should SMS/email verify the athlete, the parent, or both?**
Open — and the guardian-phone wrinkle above means "verify the athlete's
phone" often actually verifies the *parent's* phone. Recommendation: verify
**the registrant's contact** (whoever is acting), and for minors always
include the guardian contact. Spikes T1/T2 answer feasibility; note there is
no SMS capability today anywhere in the system, ChMeetings' API has no
messaging endpoints (per the OpenAPI snapshot of 2026-07-17), and the 2026
Event-Day RFC considered SMS magic-links for coordinator login and deferred
them because setup was too risky that close to the event; it did not
evaluate SMS on its merits — so this is an external gateway (e.g., Twilio)
attached to the WordPress token-page pattern, with email as the fallback
channel that costs nothing and needs no carrier registration.

**Q3 — When a minor self-registers, when and how is the parent notified?**
Recommendation: at sync time — the middleware can compute age at the event
from the synced birthdate, so the moment a new registration under
18 syncs in, a notification (T1 channel) goes to the guardian contact with a
consent link (T3). "At sync" beats "at form submission" because vaysf has no
hook at form-submit time and no forms API, and sync runs nightly or on demand.
*Fact-check: no `age_at_event` value is stored or computed for every
participant. The validator computes age per participant (`_calculate_age`,
event date from the rules file); sync's `_age_at_event` helper is called only
when a birthdate changes, and uses `Config.SPORTS_FEST_DATE`; badge
generation computes its own. Two event-date sources is open issue #69. The
form's fields are the maintainer's to change (#350 adds two for 2027); what
vaysf lacks is a submit-time trigger. "Syncs in" means after the manual
promotion in §1 step 4, which can be days after the form was submitted.*

**Q4 — Does parent consent attach to the person, the registration, or the
exact sports selected?**
Recommendation: **the registration + its sports**, not the person. The
consent release is about what the child will actually do; a consent signed
when the child registered for Scripture Memorization shouldn't silently
cover a later switch to Basketball. This makes consent behave like pastor
approval already behaves under the drift framework.

**Q5 — What changes require renewed pastor approval or parent consent?**
The system already answers half of this: identity drift
(`approval_identity_drift`: name/gender/church, and birthdate when the age at
the event changes) and registration drift
(`approval_registration_drift`: sports/events) invalidate pastor approval
(#171; the identity/registration split landed under #212, which is still open
as a review of `reapproval_required` side effects; the operator accept
workflow is #252). Recommendation: add **consent drift** as a sibling — the same
detected changes, evaluated against consent for minors. One framework, two
authorities (pastor, guardian), consistent invalidation rules.
*Fact-check: the drift guard runs only after a participant has reached the
pastor-approval surface (an approval record, or a status of approved, denied
or reapproval_required). Before that, a sport change overwrites the WordPress
row and leaves no drift record (`test_pending_participant_no_drift_check`).
Box 2 is a precondition of `pending_approval`, so consent is normally given
before the guard is active.*

**Q6 — How do we prevent duplicate registrations without blocking siblings,
shared phones, or parent-managed signups?**
The answer already exists in miniature: the consent-404 scorer refuses to
call a match "strong" on shared phone/email alone — it requires a birthdate
or exact-name anchor, precisely because family members share contacts. The
`find-duplicates` command (Canonical Identity RFC §4.4) is specified to
inherit that anchor rule (#311, not built yet), and verified contacts (Q2)
raise confidence without ever auto-acting (guardrail G3: propose, never merge).
*Fact-check: the anchor rule lives only in the 404 investigator
(`_candidate_strength`). The consent matcher that writes to ChMeetings
(`check-consent`) does not apply it: phone + email alone scores 51 and
qualifies (`test_check_consent_phone_plus_email_is_above_threshold`).*

## 6. Foundations already in the codebase

Nothing in this RFC starts from zero:

- **Token-page pattern** — the insurance-upload flow is the template: a
  shortcode page with request-link and act states, public REST endpoint
  pair, 64-hex single-purpose tokens with configurable expiry. Phone
  verification, "My Registration," and parent-consent capture are all
  instances of this shape. Pastor approval tokens prove the email-link
  variant.
- **Drift framework** — `_detect_identity_drift` + the
  `approval_identity_drift` / `approval_registration_drift` split, with the
  operator `approval-drift-accept` workflow. Consent drift (Q5) is a third
  issue type in an existing machine, not a new machine.
  *Fact-check: the machine keeps an invalidated approval invalid through the
  `reapproval_required` status and a rotated approval token. Consent has no
  such state: `consent_status` is recomputed from ChMeetings Box 2 on every
  sync, and an open issue that a sync does not regenerate is auto-resolved.
  `approval-drift-accept` restores the prior approval from local sync logs on
  an operator's say-so.*
- **Identity scoring** — consent-404 weights (birthdate 33 / email 27 /
  phone 24 / name 16) and the family-share anchor rule. *Fact-check: the
  weights live in `sync/consent_checker.py` and the anchor rule in
  `sync/consent_404_investigator.py`; extraction into a shared
  `identity_scoring` module is A4 (#311), still open.*
- **Age machinery** — age at the event can be derived from the synced
  birthdate; minor = under 18 at event (badges already use this).
  *Fact-check: there is no stored `age_at_event`; see the note under Q3.*
- **ChMeetings `/families` API** — full household CRUD exists in the API and
  is entirely unused; data quality for VAY SM is unknown (spike T4).
- **Signer-type capture** — the consent form already records self vs
  guardian; it has simply never been cross-checked against age (T5 closes
  that). *Fact-check: signer type is read from the consent-form export
  during `check-consent`, used for the match threshold and written to
  `consent_check_audit.xlsx`. It is not stored on the participant in
  WordPress or ChMeetings, so the validator cannot see it; T5 needs a place
  to keep it. The export itself comes from `chrome_export_vaysf_forms.py`,
  the diagnostic-only browser helper.*

## 7. Implementation issues (Track T)

*Sub-issues of epic #307. Spikes are discovery: their deliverable is a
written recommendation, not production code. The epic body lists the same
seven issues as "Track R" (R1–R7); the issue bodies and this document say
"Track T".*

### T1 (#313) — `spike: SMS/notification gateway evaluation`
Evaluate Twilio and alternatives for cost, nonprofit A2P 10DLC registration
lead time (weeks — a start-early item), sender identity, and operational
ownership; define the email fallback that works with zero gateway setup.
Deliverable: recommendation + cost model. **Dependencies:** none.

### T2 (#314) — `spike: contact verification page (token-page pattern)`
Prototype a `[contact_verify]`-style page on the insurance-upload pattern:
request-code → token → verified. Prototype storage must explicitly
distinguish whether the verified contact belongs to the **athlete,
registrant, or guardian**; temporary `sf_participants` storage is
acceptable for the spike, but the deliverable must recommend the final
role/contact schema shape before any production implementation —
role-scoped trust data must not be stuffed into the athlete row (that is
how `parent_info` became a flat-text junk drawer). Answers Q2 with a
working prototype; feeds `find-duplicates` a strong anchor.
**Dependencies:** T1 (channel).

### T3 (#315) — `spike: minor registration → parent notification & consent capture`
Design the trigger (sync-time, `age_at_event < 18`, new registration), the
guardian notification (T1 channel), and the consent-capture page (token-page
pattern) as complement or replacement for the ChMeetings consent form.
Consent-capture and guardian-contact storage follow the role/contact schema
recommendation from T2 — no ad-hoc fields on the participant row.
Answers Q3, informs Q4. **Dependencies:** T1, T2.

### T4 (#316) — `spike: ChMeetings /families API evaluation`
Determine whether households are reliably populated for VAY SM families and
whether the API supports a guardian link worth trusting; recommend family
model (ChMeetings households vs WordPress-side guardian link vs flat text).
**Dependencies:** none.

### T5 (#317) — `middleware: flag minor + self-signed consent mismatch`
Buildable now: cross-check signer-type against `age_at_event` during consent
processing; WARNING-severity validation issue first, severity revisited with
T6. **Dependencies:** none.
*Fact-check: one dependency was missed. Participant sync resolves every open
individual issue it did not regenerate in that run, so an issue raised from
`check-consent` would be closed by the next sync unless signer type is stored
where the validator can read it.*

### T6 (#318) — `validation: consent enforcement level for minors`
Rules-JSON change raising missing/self-signed consent for minors to ERROR
(Handbook-aligned), adults stay WARNING. **Dependencies:** §8 decision, T5.
*Fact-check: the missing-consent half is already live, and not through the
rules file: `_validate_consent` sets ERROR for under-18 in code and ignores
the rule's `severity`. A rules-JSON edit alone changes nothing today. What
is left for T6 is the self-signed case, and moving the severity into the
rules file if it is to be JSON-driven.*

### T7 (#319) — `middleware: consent drift — changes that invalidate consent`
Extend the drift framework with consent-drift for minors per Q4/Q5
(registration+sports attachment). **Dependencies:** T3 outcome, T6.

## 8. Open decisions

1. **Consent enforcement level** (gates T6): recommend ERROR for minors —
   the Handbook already requires guardian signature; this is enforcement
   catching up to policy, not new policy. *Fact-check: missing consent is
   already ERROR for minors (see §2). The decision still open is whether a
   minor's self-signed consent is an ERROR.*
2. **SMS budget and ownership** (gates T1's conclusion): who owns the
   gateway account and number; appetite for per-message cost vs email-only
   first season.
3. **Family model** (gates T7 shape): decided by T4 evidence.
4. **Verification target** (Q2, gates T2 conclusion): registrant vs athlete
   vs both — recommend registrant + guardian-for-minors.

*Facts only the maintainer can supply, feeding the spikes: whether VAY SM
households are populated in ChMeetings (T4 verifies); whether the
registration form can gain fields; whether the ChMeetings app offers any
native SMS the tenant already has.*

*Fact-check: the form-fields question is answered in practice: #350 adds two
fields to the 2027 Individual Application. Two things postdate this draft and
bear on it: Track P (#351, the Person Resolution Gate) now owns duplicate
prevention at intake, and ChMeetings 2026.16 (2026-08-06) lets a form create
member profiles automatically on submission.*

---

*Companion reading: `docs/CANONICAL_IDENTITY_RFC.md` (the repair layer this
RFC prevents work for), `docs/EVENT_DAY_RESULTS_WORKFLOW_RFC.md` (the WSMS
deferral and the RFC→issues pattern this document follows), `docs/PRD.md`
§4–§7 (forms, workflow, business rules).*
