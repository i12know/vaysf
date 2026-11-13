# Decision Record: Identity-First Intake for Sports Fest 2027

**Date:** 2026-11-13  
**Status:** Adopted as the planning direction; configuration and implementation are pending validation  
**Scope:** VAY-SF Individual Application Form, ChMeetings People creation, and middleware person resolution  
**Related:** [Epic #307](https://github.com/i12know/vaysf/issues/307), [Person Resolution Gate #351](https://github.com/i12know/vaysf/issues/351), [Form-submission workflow #62](https://github.com/i12know/vaysf/issues/62), [Withdrawn-person recreation #176](https://github.com/i12know/vaysf/issues/176), [Merged-person recreation #388](https://github.com/i12know/vaysf/issues/388), [Registrant Trust RFC, D10](REGISTRANT_TRUST_RFC.md)

## Decision

Our objective is **one trusted operational identity for each human participant**. Minimize duplicate ChMeetings People records at intake; use the canonical-ID alias and reconciliation layer as a safety net, **not** as the default way to handle every registration.

**Do not enable ChMeetings' "Automatically Create Profiles for New People" on the live 2027 Individual Application Form at this stage.** It remains a test option, not an approved production setting. Reconsider it only after controlled tests demonstrate that its matching and update behavior are reliable for VAY-SF's actual registration cases, and the maintainer approves the resulting intake architecture.

This decision clarifies the *conditional* auto-create preference previously recorded as D10 in the Registrant Trust RFC. It does not reverse the decision to retain the canonical-ID alias layer; it makes duplicate prevention the first line of defense.

## Why

ChMeetings 2026.16 introduced automatic People-profile creation from form submissions. If that feature creates a Person at submission time, middleware cannot run a **pre-creation** identity check for that creation. A downstream `find-duplicates` scan or alias resolution can then only detect or reconcile a duplicate after it exists.

Retaining stale records as `merged` rather than deleting them is safer for WordPress references, but every duplicate still carries operational cost: approvals, consent, rosters, badges, reporting, historical continuity, and future sync paths must agree on which ID survives. The aim is to reduce that cost at the source.

## Target workflow (to implement/validate under #351)

1. Preserve the original form submission without immediately assuming it is a new human being.
2. Resolve the **athlete** separately from any parent/guardian or form submitter.
3. Before any middleware-controlled People creation, search for the existing person in VAY SM, consult confirmed aliases, and perform targeted, read-only Diocese-level candidate searches where authorized.
4. Distinguish the outcomes:
   - **Verified, unambiguous existing person:** reuse/link the existing ChMeetings identity through a supported, tested workflow.
   - **Possible or cross-church match, conflicting evidence, or incomplete search:** hold for human review; do not silently reuse or create.
   - **No match after a complete, successful search:** create one new Person and record why.
5. Keep every outcome auditable. Never auto-merge people based only on name, birthdate, shared phone/email, or a match score. Siblings and minors sharing guardian contacts need particular care.
6. Maintain the alias layer for duplicates that still arrive from vendor workflows, staff actions, re-registrations, or past seasons. Mark the obsolete **VAY-SF/WordPress** identity as stale/merged; do not delete ChMeetings profiles as a routine cleanup tactic.

This is a *target design*, not a claim that #351 is implemented. The current alias map resolves ChMeetings IDs; it is not yet a separate permanent person entity across platforms.

## Test before enabling vendor auto-create

Use a **copy or staging version** of the Individual Application Form, not the live registration form. Capture the before/after ChMeetings IDs, group memberships, and updated fields for:

1. A genuinely new participant.
2. A returning participant already in VAY SM, including re-registration to change sports.
3. A participant with an existing record in another church of the Diocese.
4. Two siblings or minors using the same parent's email and phone.
5. A known stale/merged identity and its surviving canonical ID.
6. The optional automatic group assignment, ensuring an unverified person cannot bypass the intended review boundary.

For each scenario, document whether ChMeetings reused, updated, duplicated, or incorrectly conflated identities. Verify whether an existing profile's current-season registration fields are refreshed; auto-create alone does not establish that.

**Go/no-go:** Auto-create is eligible for production consideration only if these tests establish acceptable identity integrity, the effective intake/review boundary is documented, and the maintainer explicitly approves activation. If results are unreliable or inconclusive, keep it off and implement the middleware-controlled creation path.

## Implementation implications

- **#351:** Own the authoritative intake decision. A gate attached only to `repair-form-people` does not control ChMeetings UI creation or vendor auto-create. Resolve which workflow actually creates or links People before building the gate.
- **#176 and #388:** Prevent old form submissions from resurrecting withdrawn or already-merged people. These remain necessary regardless of the auto-create decision.
- **#307 / Track A:** Keep `find-duplicates`, human-confirmed aliases, `apply-aliases`, and duplicate warnings as fallback protections. They do not substitute for intake prevention.
- **#62:** Preserve the benefit of removing manual "Add People" steps, but do not trade away identity integrity merely for convenience. The chosen intake workflow must still ensure submissions are not silently dropped and that updated registrations reach the correct existing People record.
- **Operational guard:** Until the authoritative intake workflow is established, staff should not treat manual ChMeetings "Add People" or vendor auto-create as an identity-vetted path. Document the human review requirement.

## Success criteria

A returning athlete is recognized as the same person, rather than routinely receiving another ChMeetings ID. A genuinely new athlete is created once. Siblings are never conflated merely because they share household contacts. Ambiguous cross-church cases are reviewed. Past approvals, consent, and participation history remain tied to the correct canonical identity, with clear audit evidence.

**Principle:** *Prevent first. Reconcile when necessary. Preserve history. Keep the human identity decision accountable to a human.*
