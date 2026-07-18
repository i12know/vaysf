# RFC: Registrant Trust — explicit roles, verified contacts, and minor consent

**Status: Draft for review** · Target: 2027 season · Scope: design only, no
production code changes.

*Companion to `docs/CANONICAL_IDENTITY_RFC.md` (approved). That RFC fixes
duplicate identities after they exist; this one is about preventing them at
the source and making the humans around each athlete — parent, Church Rep,
pastor — explicit in the system instead of implicit in text fields. The
onboarding journey in §1 and the six design questions in §5 were supplied by
the maintainer from two seasons of operating the event.*

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
  under-18, but the system treats consent as a WARNING for everyone, never
  checks that a minor's consent was guardian-signed (a 14-year-old
  self-signing raises no flag), and has no way to notify a parent when a
  minor registers.

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

**Q2 — Should SMS/email verify the athlete, the parent, or both?**
Open — and the guardian-phone wrinkle above means "verify the athlete's
phone" often actually verifies the *parent's* phone. Recommendation: verify
**the registrant's contact** (whoever is acting), and for minors always
include the guardian contact. Spikes T1/T2 answer feasibility; note there is
no SMS capability today anywhere in the system, ChMeetings' API has no
messaging endpoints, and the 2026 Event-Day RFC already evaluated and
deferred SMS magic-links — so this is an external gateway (e.g., Twilio)
attached to the WordPress token-page pattern, with email as the fallback
channel that costs nothing and needs no carrier registration.

**Q3 — When a minor self-registers, when and how is the parent notified?**
Recommendation: at sync time — the middleware already computes
`age_at_event` for every participant, so the moment a new registration under
18 syncs in, a notification (T1 channel) goes to the guardian contact with a
consent link (T3). "At sync" beats "at form submission" because we don't
control the ChMeetings form, and sync runs nightly or on demand.

**Q4 — Does parent consent attach to the person, the registration, or the
exact sports selected?**
Recommendation: **the registration + its sports**, not the person. The
consent release is about what the child will actually do; a consent signed
when the child registered for Scripture Memorization shouldn't silently
cover a later switch to Basketball. This makes consent behave like pastor
approval already behaves under the drift framework.

**Q5 — What changes require renewed pastor approval or parent consent?**
The system already answers half of this: identity drift
(`approval_identity_drift`: name/gender/church) and registration drift
(`approval_registration_drift`: sports/events) invalidate pastor approval
(#171, #212). Recommendation: add **consent drift** as a sibling — the same
detected changes, evaluated against consent for minors. One framework, two
authorities (pastor, guardian), consistent invalidation rules.

**Q6 — How do we prevent duplicate registrations without blocking siblings,
shared phones, or parent-managed signups?**
The answer already exists in miniature: the consent-404 scorer refuses to
call a match "strong" on shared phone/email alone — it requires a birthdate
or exact-name anchor, precisely because family members share contacts. The
`find-duplicates` command (Canonical Identity RFC §4.4) inherits that anchor
rule, and verified contacts (Q2) raise confidence without ever auto-acting
(guardrail G3: propose, never merge).

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
- **Identity scoring** — consent-404 weights (birthdate 33 / email 27 /
  phone 24 / name 16) and the family-share anchor rule; being extracted into
  a shared `identity_scoring` module by Canonical Identity Track A.
- **Age machinery** — `age_at_event` computed in sync; minor = under 18 at
  event (badges already use this).
- **ChMeetings `/families` API** — full household CRUD exists in the API and
  is entirely unused; data quality for VAY SM is unknown (spike T4).
- **Signer-type capture** — the consent form already records self vs
  guardian; it has simply never been cross-checked against age (T5 closes
  that today, no new infrastructure).

## 7. Implementation issues (Track T)

*Sub-issues of epic #307. Spikes are discovery: their deliverable is a
written recommendation, not production code.*

### T1 (#313) — `spike: SMS/notification gateway evaluation`
Evaluate Twilio and alternatives for cost, nonprofit A2P 10DLC registration
lead time (weeks — a start-early item), sender identity, and operational
ownership; define the email fallback that works with zero gateway setup.
Deliverable: recommendation + cost model. **Dependencies:** none.

### T2 (#314) — `spike: contact verification page (token-page pattern)`
Prototype a `[contact_verify]`-style page on the insurance-upload pattern:
request-code → token → verified; verified contact stored on the participant.
Answers Q2 with a working prototype; feeds `find-duplicates` a strong
anchor. **Dependencies:** T1 (channel).

### T3 (#315) — `spike: minor registration → parent notification & consent capture`
Design the trigger (sync-time, `age_at_event < 18`, new registration), the
guardian notification (T1 channel), and the consent-capture page (token-page
pattern) as complement or replacement for the ChMeetings consent form.
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

### T6 (#318) — `validation: consent enforcement level for minors`
Rules-JSON change raising missing/self-signed consent for minors to ERROR
(Handbook-aligned), adults stay WARNING. **Dependencies:** §8 decision, T5.

### T7 (#319) — `middleware: consent drift — changes that invalidate consent`
Extend the drift framework with consent-drift for minors per Q4/Q5
(registration+sports attachment). **Dependencies:** T3 outcome, T6.

## 8. Open decisions

1. **Consent enforcement level** (gates T6): recommend ERROR for minors —
   the Handbook already requires guardian signature; this is enforcement
   catching up to policy, not new policy.
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

---

*Companion reading: `docs/CANONICAL_IDENTITY_RFC.md` (the repair layer this
RFC prevents work for), `docs/EVENT_DAY_RESULTS_WORKFLOW_RFC.md` (the WSMS
deferral and the RFC→issues pattern this document follows), `docs/PRD.md`
§4–§7 (forms, workflow, business rules).*
