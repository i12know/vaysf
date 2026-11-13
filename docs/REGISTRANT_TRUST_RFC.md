# RFC: Registrant Trust — explicit roles, verified contacts, and minor consent

**Status: Draft; 2027 decisions recorded in §9** · Target: 2027 season · Scope: design only, no
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

*Update, 2026-11-13 (#311): `find-duplicates` and `sync/identity_scoring.py`
now exist. Where the fact-check notes below say A4 is "not built yet" or that
the anchor rule "lives only in the 404 investigator", read them as the
2026-11-12 state: the rule is now shared by the investigator and
`find-duplicates`. `check-consent` still does not apply it. A5 (#312) is
unchanged.*

*Decisions, 2026-11-12/13: the maintainer answered the review's questions on
epic #307 (comment 6839370870 and follow-ups). They are recorded in §9 and
supersede the recommendations they touch: Q1, Q3, Q4 and Q5 are decided. The 2027 issue scopes are in §9.3. §9.4 lists what the decisions
leave open.*

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
   *Fact-check: in the 2026 workflow, staff used Bulk Actions → "Add People"
   for applications without a linked ChMeetings Person (`docs/PRD.md` §5
   step 3a, #62; see #27 for the parent/child mis-linking risk).
   `repair-form-people` can also create a missing profile. Participant sync
   sees the athlete once a People profile is in a `Team` group.*
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
*Decided (§9.1, D1): the consent form must say plainly who is completing and
signing it, as a required question: the athlete, or the athlete's parent or
legal guardian. Reuse the existing "Select one:" question if it can be
reworded and made required.*

**Q2 — Should SMS/email verify the athlete, the parent, or both?**
Open — and the guardian-phone wrinkle above means "verify the athlete's
phone" often actually verifies the *parent's* phone. Recommendation: verify
**the registrant's contact** (whoever is acting), and for minors always
include the guardian contact. Spikes R1/R2 answer feasibility; note there is
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
18 syncs in, a notification (R1 channel) goes to the guardian contact with a
consent link (R3). "At sync" beats "at form submission" because vaysf has no
hook at form-submit time and no forms API, and sync runs nightly or on demand.
*Fact-check: no `age_at_event` value is stored or computed for every
participant. The validator computes age per participant (`_calculate_age`,
event date from the rules file); sync's `_age_at_event` helper is called only
when a birthdate changes, and uses `Config.SPORTS_FEST_DATE`; badge
generation computes its own. Two event-date sources is open issue #69. The
form's fields are the maintainer's to change (#350 adds two for 2027); what
vaysf lacks is a submit-time trigger. "Syncs in" means after the manual
promotion in §1 step 4, which can be days after the form was submitted.*
*Decided (§9.1, D7–D8): email only for 2027, one bilingual reminder per
minor per season, linking to the existing ChMeetings consent form. No
consent-capture page in 2027. Form auto-create is off for 2027 (D10), so
"syncs in" still follows the reviewed promotion step.*

**Q4 — Does parent consent attach to the person, the registration, or the
exact sports selected?**
The guardian release covers the whole Sports Fest. It applies to the athlete
for that season. Changing sports alone leaves consent and pastor approval in
place (§9.1, D2).

**Q5 — What changes require renewed pastor approval or parent consent?**
The system already answers half of this: identity drift
(`approval_identity_drift`: name/gender/church, and birthdate when the age at
the event changes) and registration drift
(`approval_registration_drift`: sports/events) invalidate pastor approval
(#171; the identity/registration split landed under #212, which is still open
as a review of `reapproval_required` side effects; the operator accept
workflow is #252). For 2027, change sync so sport-only changes preserve
pastor approval. The CONSENT HOLD in §9.2 tracks eligibility separately.
*Fact-check: the drift guard runs only after a participant has reached the
pastor-approval surface (an approval record, or a status of approved, denied
or reapproval_required). Before that, a sport change overwrites the WordPress
row and leaves no drift record (`test_pending_participant_no_drift_check`).
Box 2 is a precondition of `pending_approval`, so consent is normally given
before the guard is active.*
*Decided (§9.1, D2–D3): there is no consent drift in 2027. Sport changes do
not touch consent. What invalidates consent is a staff-confirmed
self-signature by a minor, which puts the athlete on CONSENT HOLD (§9.2).
That is a new state, not a sibling of approval drift.*

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
*Decided (§9.1, D9): valid consent carries across a confirmed alias merge
within the same Sports Fest; an unresolved CONSENT HOLD carries too. Form
auto-create stays off for 2027 (§9.1 D10), so intake prevention belongs to
Track P (#351).*

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
  operator `approval-drift-accept` workflow. This framework tracks pastor
  approval. Consent has no persisted invalidation state.
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
  is entirely unused; data quality for VAY SM is unknown (spike R4).
  *Decided (§9.1, D11): sometimes filled in, usually not; optional
  context only.*
- **Signer-type capture** — the consent form already records self vs
  guardian; it has simply never been cross-checked against age (R5 closes
  that). *Fact-check: signer type is read from the consent-form export
  during `check-consent`, used for the match threshold and written to
  `consent_check_audit.xlsx`. It is not stored on the participant in
  WordPress or ChMeetings, so the validator cannot see it; R5 needs a place
  to keep it. The export itself comes from `chrome_export_vaysf_forms.py`,
  the diagnostic-only browser helper.*

## 7. Implementation issues (Track R)

*Sub-issues of epic #307. This RFC uses the epic’s Track R naming. The
original issue bodies may refer to the same issue numbers as Track T.*

The 2027 scope and its mapping to issues #313–#319 are in §9.3.

## 8. Open decisions

See §9.4 for the remaining workflow and storage decisions. The SMS gateway
and verification page are deferred. Form auto-create is off for 2027
(D10, tested 2026-11-13).

## 9. Maintainer decisions for 2027

*Recorded 2026-11-12/13 from the maintainer's answers on epic #307. These are
policy; the build issues implement them.*

### 9.1 Decisions

- **D1. Signer question.** The consent form must say plainly who is
  completing and signing it: the athlete, or the athlete's parent or legal
  guardian. The answer is required. Reuse the existing "Select one:"
  question if it can be reworded and made required; otherwise replace it.
  (Changing the question's text changes the export column the consent
  matcher reads, which is a literal `"Select one:"` in
  `sync/consent_checker.py` today; route it through `CHM_FIELDS` when it
  changes.)
- **D2. Scope of the release.** The guardian release covers the whole Sports
  Fest. Changing sports alone leaves both consent and pastor approval in
  place.
- **D3. Self-signed minor.** If staff confirm that a minor signed for
  themselves, the consent is invalid, the athlete goes on CONSENT HOLD, and
  staff personally contact the parent or guardian for a valid replacement.
- **D4. Replacement consent.** The parent or guardian can use the existing
  ChMeetings consent form. VAY Staff can also accept another signed copy and
  record it as replacement consent.
- **D5. Pastor approval during a hold.** Any existing pastor approval stays
  on record. When the hold clears, the athlete resumes at the next gate: if
  pastor approval is pending it proceeds as usual; if already given, that
  step is complete.
- **D6. Storage and retention.** Guardian contacts and consent records are
  kept in ChMeetings, by season. Prior years are retained until VAY chooses
  to delete that year's records. WordPress holds working state only, so the
  yearly truncation of `sf_participants` must preserve access to the signed
  release and the record of staff acceptance.
- **D7. Channel.** Email only for 2027. No SMS gateway and no verification
  page this season.
- **D8. Guardian reminder and address gate.** A separate bilingual email
  reminder goes out **once** when a new minor registration first comes
  through sync for the season and still needs consent, linking to the
  existing ChMeetings consent form. If the guardian email is missing or
  appears to belong to the athlete, the Church Rep is flagged, the athlete
  cannot advance, and the reminder is sent only after the Church Rep
  resolves the address. Repeat syncs and alias merges never resend it.
  Staff still contact the guardian personally when a self-signature is
  confirmed (D3).
- **D9. Alias merges.** Valid consent for the same Sports Fest carries
  across a confirmed alias merge: finding another ChMeetings ID for the same
  athlete never requires the guardian to sign again. An unresolved CONSENT
  HOLD also carries through the merge and stays in effect.
- **D10. Form auto-create: off for 2027 (decided 2026-11-13).** ChMeetings'
  automatic People profile creation (2026.16) stays **off** on the live
  Individual Application. This supersedes the earlier "preferred, pending
  test" wording; the governing record is
  `docs/DECISION_2027_IDENTITY_FIRST_INTAKE.md` (identity-first intake:
  prevent duplicates at creation, keep Track A aliases as the safety net).

  *Test, 2026-11-13* (copy of the form on the VAY SM tenant, ChMeetings
  v2026.22.7.3, fictional people only; all test data deleted afterwards):

  | Case | Result |
  |---|---|
  | New athlete | One profile created; name, birthdate, email, phone, gender, Church Team and Sports Fest fields written |
  | Returning athlete, same details | Linked to the existing profile; no duplicate |
  | Returning athlete, changed email (same name, birthdate, phone) | Linked to the existing profile; profile email not changed |
  | Siblings sharing a parent's email and phone | Two separate profiles; the second did not overwrite the first |
  | `Đức Phạm` then `Duc Pham`, same birthdate and contacts | Linked; accented name preserved |
  | Withdrawn stand-in (in a Lost and Found test group) resubmits | Linked to the existing profile; group kept; submission accepted |
  | Group assignment | One fixed form-level group; cannot route by the church answered |
  | Parent types their own name in Name | Profile created under the parent's name with the child's birthdate |

  Matched submissions only offer a manual "Update Profile"; nothing on an
  existing profile changed automatically. The settings expose no match
  fields, thresholds or answer-based group rules.

  *Why off, despite good matching:* auto-create creates the Person at
  submission time with no human review, so a withdrawn or merged athlete
  whose submission matches no visible profile gets a fresh ChMeetings ID
  before anyone looks, and the #176/#388 protections in
  `repair-form-people` never run. Team routing (handled by `assign-groups`
  from the Church Team field) and the parent-name case (a form-wording
  problem that manual "Add People" shares; see D1 and #350) are not
  reasons on their own. Revisit only under the decision record's go/no-go:
  the untested cases (cross-church Diocese person, stale/merged pair, an
  existing profile with a fixed group set) pass, the intake review
  boundary is documented, and the maintainer approves.

- **D11. Households are optional context.** VAY SM household records in
  ChMeetings are sometimes filled in but usually are not. The 2027 workflow
  must work with no household record: the guardian contact comes from the
  registration and consent form, and a household link, where one exists,
  is supporting evidence only. Nothing blocks or waits on it.
- **D12. Ages 10–12.** Athletes aged 10–12 (for example in Scripture
  Memorization) take part in the same registration and consent workflow as
  other minors, and VAY collects the contact details that workflow needs.
  The same rule applies: their parent or legal guardian must sign the
  release. No separate path or exemption.

### 9.2 CONSENT HOLD

A per-athlete, per-season state for minors.

- **Set by:** staff confirming a minor's self-signature (D3).
- **Shown as:** "CONSENT HOLD" next to the athlete's name in roster, badge
  and check-in workflows. The athlete stays in the daily roster export so
  the Church Rep can resolve it, and is excluded from the cleared roster.
- **Blocks:** badge issuance and event-day check-in while active, including
  check-in with a badge already issued.
- **Cleared by:** the Church Rep, before a badge is issued, once valid
  replacement consent is on record; only VAY Staff after a badge has been
  issued.
- **Carries:** through a confirmed alias merge (D9). Pastor approval is
  kept during the hold (D5).

The guardian-address gate in D8 is a separate block with its own resolver
(the Church Rep). It is not a CONSENT HOLD.

### 9.3 Effect on Track R

| Issue | 2027 effect |
|---|---|
| R1 (#313) SMS gateway | Deferred (D7) |
| R2 (#314) verification page | Deferred (D7); the role/contact schema memo is still needed for D6 |
| R3 (#315) guardian notice | Build: email reminder and address gate (D8) |
| R4 (#316) `/families` probe | Optional (D11): may show where household links help, but nothing in 2027 depends on it |
| R5 (#317) self-signed flag | Build: flag for staff review after a reliable athlete match; shared family phone and email alone are insufficient (D3) |
| R6 (#318) enforcement | Build: the hold and the address gate block advancement |
| R7 (#319) consent drift | Superseded by D2; CONSENT HOLD replaces it |

### 9.4 Left open by these decisions

1. **Event-day check-in does not exist in vaysf.** `generate-badges` renders
   and uploads badges (`middleware/badges/`), but nothing on `main` records
   a check-in. The existing manual check-in can use a current list that marks
   CONSENT HOLD. Decide who updates the list and relays late changes.
2. **Badge issuance is not recorded.** The before/after-badge rule for who
   clears a hold needs an issuance record per athlete and season. Define
   issuance by when the athlete or church can obtain the badge.
3. **"Appears to belong to the athlete" needs a definition and an
   override.** When a parent fills in the form, the parent's email is often
   used for both athlete and guardian; equality alone will flag many real
   families. D8 needs a "Church Rep confirmed this is the guardian" outcome
   that clears the gate, so it doesn't stall legitimate minors.
4. **Where staff-recorded replacement consent lives.** D4 and D6 put the
   record in ChMeetings, but `consent_status` is recomputed from Box 2 every
   sync. A paper copy recorded by staff must reach ChMeetings (or a field
   sync honours) so the next sync does not undo it.
5. **Where "reminder sent" is recorded.** D8's send-once rule needs a
   per-athlete, per-season marker that survives a resync and follows the
   canonical person through an alias merge (D9).
6. **Which ID carries consent and hold.** D9 requires consent and hold to
   follow the canonical person; WordPress cannot resolve aliases, so the
   carry happens in the middleware. Today `check-consent` can redirect a
   matching form to the surviving record. `apply-aliases` does not migrate
   consent or hold state. Keep an unresolved hold active if records conflict.
7. **Age bands in code.** D12 needs every minor rule to key on "under 18 at
   the event" with no lower bound. The missing-consent ERROR already does
   (`age < 18` in `IndividualValidator._validate_consent`); the self-signed
   flag, CONSENT HOLD and the reminder must match it, with fixtures that
   include a 10–12 year old.

8. **Downstream eligibility.** Identify consumers that use pastor approval
   as eligibility, including badge generation and any use of the ChMeetings
   approved group for admission. Ensure they honor the hold while retaining
   the underlying pastor approval.

---

*Companion reading: `docs/CANONICAL_IDENTITY_RFC.md` (the repair layer this
RFC prevents work for), `docs/EVENT_DAY_RESULTS_WORKFLOW_RFC.md` (the WSMS
deferral and the RFC→issues pattern this document follows), `docs/PRD.md`
§4–§7 (forms, workflow, business rules).*
