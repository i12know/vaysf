# Product Requirements Document (PRD)
## VAY Sports Fest — ChMeetings Integration System (`vaysf`)

**Version:** 1.0  
**Last Updated:** April 2026  
**Maintainer:** VAY-SM Senior Staff  
**GitHub Repo:** https://github.com/i12know/vaysf  
**Architecture Reference:** [ARCHITECTURE.md](../ARCHITECTURE.md)

---

## 1. Purpose of This Document

`ARCHITECTURE.md` describes *how* the system is built. This PRD answers *why* it was built and *what* it needs to do — providing the domain context, business rules, and user workflows that drive every technical decision in the architecture. Anyone working on the codebase should read this document first.

---

## 2. Background: What is Sports Fest?

**VAY Sports Fest** is an annual two-weekend sports and discipleship gathering organized by the **Vietnamese Alliance Youth Sports Ministry (VAY-SM)** of the Southern California Region Vietnamese Alliance Youth (VAY), a ministry of the Vietnamese District of the Christian and Missionary Alliance (CMA). Sports Fest has run for nearly five decades and draws hundreds of young people from Vietnamese Alliance churches across Southern California.

The event spans four days (two consecutive Saturday/Sunday weekends, typically in July) and includes both competitive events and community gatherings:

**Competitive Events:** Men's Basketball, Men's Volleyball, Women's Volleyball, Bible Challenge (Mixed), Badminton, Pickleball, Pickleball 35+, Table Tennis, Table Tennis 35+, Tennis, Track & Field, Scripture Memorization, Tug-O-War.

**Community Events:** Opening Ceremony, Closing Ceremony, Chapel Services, Community Potlucks.

The event's mission is not merely athletic — it is to *strengthen youth ministries of local churches, equip church fellowships to disciple members, and foster a movement of young people glorifying God through the Great Commandment and Commission lifestyle.*

**VAY-SM Senior Staff (as of 2026):**
- John Chanh Nhan (Director) — nhanjohn@gmail.com
- Pastor Bumble Ho — pastorbumble@gmail.com
- Hanh Nguyen — duchanhnguyen@yahoo.com
- Sean (Khanh) Bui — sean.bui@gmail.com
- Loc Nguyen — readandpray@yahoo.com

---

## 3. Stakeholders and User Roles

There are four primary roles in the Sports Fest system. Every database table, form field, workflow step, and validation rule exists to serve one or more of these roles.

### 3.1 VAY-SM Senior Staff
The organizing body. They configure rules, manage system-wide data, review sportsmanship, adjudicate eligibility disputes, and run the overall operation. They are the top-level admins in both ChMeetings and the WordPress backend.

### 3.2 Church Senior Pastor
The pastoral authority for each participating church. Their primary function in the system is **approval** — they must digitally vouch for every participant from their church, confirming church membership and eligibility. Pastors interact with the system only through email-based approval tokens (the `sf_approvals` table and the pastor approval workflow in WordPress).

### 3.3 Church Representative (Church Rep)
The operational liaison between VAY-SM Staff and each local church. Must be at least 18 years old. Church Reps are the primary data-entry users — they submit the Church Application Form, coordinate individual participant registrations, collect fees, and facilitate the pastor approval process. A church must register its Rep before any participants can sign up. Church Reps interact with both the ChMeetings registration forms and the WordPress admin interface.

### 3.4 Individual Participant (Athlete)
Any person (athlete, fan, volunteer, or leader) registering to participate. Athletes must be at least 13 and under 35 at the start of Sports Fest (with exceptions for Scripture Memorization, Tug-O-War, Pickleball 35+, and Table Tennis 35+). Participants register via the Individual Participant Application Form in ChMeetings and are subject to multi-level validation before they may compete.

---

## 4. The Two Critical Input Forms

These two forms in ChMeetings are the **primary data entry points** for the entire system. All downstream processing — syncing, validation, pastor approvals, roster management, and scheduling — depends on clean data captured here.

### 4.1 Church Application Form
**URL:** https://bit.ly/vaysm-church-signup  
**Submitted by:** Church Representative  
**Deadline:** Church Registration deadline (see annual planning calendar)  
**Purpose:** Enrolls a church and its Rep into the Sports Fest system. Must be completed before any individual participants from that church can register.

| Field | Required | Notes |
|---|---|---|
| Church Name | Yes | Used to create/match `sf_churches.church_name` |
| Pastor Name | Yes | Stored in `sf_churches.pastor_name`; used for approval emails |
| Pastor Email | Yes | Stored in `sf_churches.pastor_email`; all approval tokens sent here |
| Pastor Phone Number | Yes | Stored in `sf_churches.pastor_phone` |
| Church Rep First Name | Yes | Stored in `sf_churches.church_rep_name` |
| Church Rep Last Name | Yes | Stored in `sf_churches.church_rep_name` |
| Church Rep Email | Yes | Stored in `sf_churches.church_rep_email`; notification recipient |
| Church Rep Mobile Phone | Yes | Stored in `sf_churches.church_rep_phone` |
| Church Rep Birthdate | Yes | Used to verify Rep is ≥18 years old |
| Level of Sports Ministry | Yes | Levels 1–6 (see Section 6); stored in `sf_churches.sports_ministry_level` |
| Certificate of Insurance upload | Yes | Must name VAY as Certificate Holder, min $1M/$3M aggregate coverage |
| Additional Notes | No | Free text |

**Post-submission:** VAY-SM Staff review and approve the church's registration. The church is assigned a unique 3-character `church_code` (e.g., `RPC`), which becomes the foreign key linking all participants and rosters to that church.

**Also required at registration (submitted separately at the meeting):**
- Church Registration Fee: $500 (2+ team events) or $300 (1 or fewer team events); $100 late fee applies
- Church flag fee: $50
- Church's proof of insurance (Certificate of Insurance per the spec above)

---

### 4.2 Individual Participant Application Form
**URL:** https://bit.ly/vaysm-signup  
**Submitted by:** Individual Participant (or parent/guardian if under 18)  
**Deadline:** Early registration or late registration deadline (see annual planning calendar)  
**Purpose:** Registers a participant, captures their sport selections, and initiates the pastor approval workflow.

| Field | Required | Notes |
|---|---|---|
| Full Name | Yes | Must match a government-issued photo ID. Stored in `sf_participants.first_name` / `last_name` |
| Gender | Yes | Male / Female. Used for gender-restricted sports validation. Stored in `sf_participants.gender` |
| Church Team (3-char code) | Yes | Links participant to `sf_churches.church_code`. Stored in `sf_participants.church_code` |
| "Would your pastor say you belong to his church?" | Yes | Yes / No. Drives `sf_participants.is_church_member`. Core input for pastor approval Q1/Q2 decision flow |
| How did you hear about us | No | Used for outreach tracking |
| Primary Sport | No | One of: Basketball (Men), Bible Challenge (Mixed), Volleyball (Men), Volleyball (Women), Badminton. Stored in `sf_participants.primary_sport` |
| Primary Sport Format confirmation | No | Unselected/Other, Team Sport, or Racquet Sport. Stored in `sf_participants.primary_format` |
| Secondary Sport | No | One of: Badminton, Tennis, Table Tennis, Table Tennis 35+, Pickleball, Pickleball 35+. Stored in `sf_participants.secondary_sport` |
| Secondary Sport Format confirmation | No | Same options as primary. Stored in `sf_participants.secondary_format` |
| Mobile Phone | Yes | Required for 2FA and emergency mass texting |
| Email | Yes | Required for account and notification |
| Role | Yes | Athlete/Participant, Parent paying for minor, Church Rep, Pastor/Leader/Coach, VAY-SM Staff, Fan/Supporter |
| Birthdate | Yes | Used for age validation. Stored in `sf_participants.birthdate`. Age calculated relative to first day of Sports Fest |
| Age Verification (self-declared) | Yes | Over 18 but under 35 / Under 18 / Over 35. Cross-validated against birthdate |
| Photo (headshot) | Yes | Uploaded for electronic ID badge. URL stored in `sf_participants.photo_url` |
| Liability Release (electronic signature) | Yes | Full legal waiver text; acceptance recorded at registration |
| Medical Release (electronic signature) | Yes | Full medical waiver text; includes consent for event medical team treatment |
| Parent/Guardian signature (if under 18) | Conditional | Required if birthdate indicates participant is a minor |
| Partner name (for doubles events) | Conditional | Required for Doubles Badminton, Doubles Pickleball, Doubles Table Tennis, Doubles Tennis. Stored in `sf_participants.primary_partner` or `secondary_partner` |

**Note:** Each participant may register for up to two events (Primary + Secondary), not counting Track & Field and Scripture Memorization. These two events allow unlimited additional participants and are not counted against the two-event limit.

---

## 5. Registration and Approval Workflow

This is the end-to-end process that the system automates. Understanding this flow explains why the three-tier architecture (ChMeetings → Middleware → WordPress) exists.

```
1. Church Rep submits Church Application Form (ChMeetings)
         ↓
2. VAY-SM Staff approves church; church_code assigned
         ↓
3. Participant submits Individual Participant Application (ChMeetings)
         ↓
3a. [MANUAL — Admin] Admin promotes participant from Form Submission to
    VAY-SM Member via Bulk Actions → "Add People" in ChMeetings.
    If person already exists in the Diocese under another church, the
    bulk action fails; Admin must navigate to Diocese root level and
    add them to the VAY-SM group manually.
    Until this step is done, the participant is invisible to the middleware.
    (See Issue #62 — planned for automation via email-triggered sync)
         ↓
4. Middleware syncs participant data to WordPress (sf_participants)
         ↓
5. Church Rep reviews participant data in ChMeetings; verifies identity & documents
         ↓
6. Church Rep marks participant "ready for approval" in ChMeetings
         ↓
7. Middleware generates approval token; stores in sf_approvals
         ↓
8. WordPress sends approval email to Pastor with secure token link
         ↓
9. Pastor clicks link → reviews participant → Approves or Denies
         ↓
10. WordPress records decision in sf_approvals
         ↓
11. Middleware syncs approval status back to ChMeetings
         ↓
12. Participant receives notification of approval/denial
         ↓
13. Approved participants appear on rosters (sf_rosters) for scheduling
```

**Key constraint:** Pastor approval is required for *every* participant, whether church member or not. The pastor's responses to the five decision-flow questions (see Section 6.2) determine whether and how the participant may compete.

---

## 6. Business Rules and Eligibility Logic

These rules are the source of truth for the JSON validation system (`validation/summer_YYYY.json`) and the `IndividualValidator`, team-level, and church-level validators in the middleware. When rules change year to year, the JSON file must be updated to match the current Handbook.

### 6.1 Age Rules
- **Minimum age:** 13 years old at the start of Sports Fest (rule code: `MIN_AGE_DEFAULT`)
- **Maximum age:** Under 35 at the start of Sports Fest (rule code: `MAX_AGE_DEFAULT`)
- **Exceptions:** Scripture Memorization, Tug-O-War, Pickleball 35+, and Table Tennis 35+ allow participants over 35
- Age is always calculated relative to the **first day of Sports Fest**, not the registration date

### 6.2 Church Membership and the Pastor Approval Decision Tree

The pastor approval email should guide the pastor through this five-question decision flow:

| Question | Yes outcome | No outcome |
|---|---|---|
| Q1: Do you vouch for this participant to represent your church at Sports Fest? | Continue to Q2 | **Reject** |
| Q2: Is participant a confirmed church member or approved via inter-church agreement (small church provision)? | **Approved as member** | Treat as non-member; continue to Q3 |
| Q3: Is there an available non-member slot on this team? (max 2 per Basketball/Volleyball/Bible Challenge team; max 1 per doubles event) | Continue to Q4 | **Reject** (non-member limit exceeded) |
| Q4: Is the non-member participant a Christian? | **Approved as Christian non-member** (no Outreach Plan required) | Participant is pre-Christian; continue to Q5 |
| Q5: Does the church have an approved Outreach Plan for this pre-Christian? | **Approved as pre-Christian with Outreach Plan** | **Reject** (missing Outreach Plan) |

**Church membership definitions:**
- Vietnamese Alliance Church (VAC): Member has attended regularly for at least **3 months** prior to signup (per District Bylaw)
- Other Vietnamese denominations: As defined by the senior pastor

### 6.3 Small Church Provision (Inter-Church Agreement)
Vietnamese churches that cannot field a full team may merge their youth into another participating Vietnamese church's team, subject to:
- All youth from the small church must join the **same** larger church's team
- Both pastors (small and receiving) must approve the arrangement
- These participants register under the receiving church's code

### 6.4 Non-Member (Ringer) Quotas
These are enforced at the **team level** by the middleware validator:
- Basketball, Men's Volleyball, Women's Volleyball, Bible Challenge: **max 2 non-members per team**
- Soccer - Coed Exhibition: **max 0 non-members**
- Singles racquet events (Badminton, Pickleball, Pickleball 35+, Table Tennis, Table Tennis 35+, Tennis): **max 0 non-members**
- Doubles events (Badminton, Pickleball, Table Tennis, Tennis): **max 1 non-member per pair**

### 6.5 Team Event Roster Rules
- Team events are open above their minimum playable roster:
- Basketball: minimum 5 participants
- Men's Volleyball: minimum 6 participants
- Women's Volleyball: minimum 6 participants
- Bible Challenge: minimum 3 participants
- Soccer - Coed Exhibition: minimum 4 participants
- Church-level event entry caps are enforced by the middleware validator:
- Basketball: max 1 team per church
- Men's Volleyball: max 1 team per church
- Women's Volleyball: max 1 team per church
- Bible Challenge: max 1 team per church
- Soccer - Coed Exhibition: max 1 team per church
- Badminton: max 2 Men's Doubles, max 1 Women's Doubles, max 1 Mixed Doubles; Men's/Women's Singles not allowed
- Pickleball: max 3 doubles teams total; max 1 Men's Doubles, max 1 Women's Doubles, max 3 Mixed Doubles; Men's/Women's Singles not allowed
- Pickleball 35+: max 1 doubles team total; Men's/Women's Singles not allowed
- Tennis: max 3 Men's Singles, max 3 Women's Singles, max 2 Mixed Doubles; Men's/Women's Doubles not allowed
- Table Tennis: max 3 Men's Singles, max 3 Women's Singles, max 2 doubles teams total
- Table Tennis 35+: max 1 doubles team total; Men's/Women's Singles not allowed
- For church-level doubles quotas, only resolved reciprocal pairs count toward the church cap; one-sided or ambiguous partner claims stay at the TEAM validation layer until corrected
- Doubles partner matching is deterministic rather than phonetic: the validator may resolve same-event pairs using accent-insensitive normalization, punctuation/parenthetical cleanup, token-order normalization, compact-spacing normalization (for example `Minh Thu` vs `Minhthu`), and unique initial-based abbreviations (for example `Jamie S` vs `Jamie Sauveur`)
- The validator does not use phonetic algorithms such as `soundex` to auto-resolve doubles pairs; if a name remains uncertain after deterministic normalization, it stays a `TEAM` warning instead of silently counting toward church quotas
- Each athlete may register for max 2 events (Primary + Secondary), excluding Track & Field and Scripture Memorization

### 6.6 Photo Requirement
All participants must upload a headshot photo used as their electronic ID badge. A missing or invalid photo is an `ERROR`-level validation issue that blocks participation.

### 6.7 Consent Requirements
Both the Liability Release and Medical Release must be electronically signed during registration. For participants under 18, a parent or guardian signature is required. Missing consent is an `ERROR`-level validation issue.

### 6.8 Validation Severity Levels
| Level | Meaning | Effect |
|---|---|---|
| `ERROR` | Blocks participation | Must be resolved before participant may compete |
| `WARNING` | Notable issue | Does not block; logged for reporting |
| `INFO` | Informational | Logged only |

---

## 7. Church Sports Ministry Levels

Each church self-reports its level of sports ministry engagement on the Church Application Form. This is stored in `sf_churches.sports_ministry_level` and factors into the Sportsmanship Award evaluation.

| Level | Name | Description |
|---|---|---|
| 1 | Unorganized | Participates without prior planning |
| 2 | Organized | Participates with planning and scheduled practices |
| 3 | Intentional | Uses Sports Fest to strengthen weaker Christians |
| 4 | Missional | Uses Sports Fest to reach pre-Christians |
| 5 | Matured | Can run its own sports ministry independent of Sports Fest |
| 6 | Multiplied | Actively multiplies teams, disciples, and leaders beyond the local church |

---

## 8. Key Deadlines and Calendar

The system's scheduled sync jobs and validation runs should be timed around these operational milestones:

| Milestone | Significance |
|---|---|
| Information Meeting (March) | Churches learn about Sports Fest; no system action required |
| **Church Registration Deadline (April)** | Church Application Forms due; `sf_churches` records must be complete |
| **Early Athlete Registration Deadline (May)** | Individual sign-ups due; individual events close |
| **Late Athlete Registration Deadline (June)** | Final cutoff for most events; team events may extend |
| Schedule Preview & Prayer (July ~2 weeks prior) | Rosters finalized; scheduler generates match schedule |
| **Sports Fest Weekend 1** | Live event |
| **Sports Fest Weekend 2** | Live event |

---

## 9. Fee Structure (for reference in payment status fields)

| Fee | Amount | Notes |
|---|---|---|
| Church Registration (2+ team events) | $500 | +$100 late fee |
| Church Registration (≤1 team event) | $300 | +$100 late fee |
| Church Flag | $50 | One-time |
| Athlete Registration | $30/person | Not per event |
| Late Athlete Registration | $60/person | See deadline page |

Fees are non-transferable and non-refundable. All athlete fees must be collected by the Church Rep and submitted as a single transaction — individual payments are not accepted. Payment status is tracked in `sf_churches.payment_status`.

---

## 10. ChMeetings as the System of Record

**ChMeetings** (https://chmeetings.com) is the primary system of record for all registration data. It serves as:
- The platform hosting both the Church Application Form and the Individual Participant Application Form
- The source of truth for participant profiles (name, birthdate, gender, photo, church membership status)
- The group management system — participants are organized into "Team [CODE]" groups (e.g., "Team RPC") using the `assign-groups` middleware command
- The payment processing platform for athlete fees

The middleware's `ChMeetingsConnector` accesses ChMeetings via the REST API only. Selenium/browser automation was removed in v1.05, and Excel export remains a fallback only for approval sync troubleshooting. All data flows from ChMeetings -> Middleware -> WordPress, never the reverse for participant data. Approval decisions flow back from WordPress -> ChMeetings via `sync_approvals_to_chmeetings`.

---

## 11. WordPress as the Operations Layer

The WordPress plugin (`vaysf`) on Bluehost serves as the operational management layer. It does **not** replace ChMeetings but extends it with:
- The **pastor approval workflow** — secure token-based email approval UI that pastors interact with directly
- **Validation issue tracking** — the admin can view, filter, and resolve data quality issues surfaced by the middleware
- **Roster management** — `sf_rosters` aggregates which participants are on which teams for which sports
- **REST API** — exposes structured endpoints consumed by the middleware
- **Statistics and reporting** — `class-vaysf-statistics.php` provides summary views for VAY-SM Staff

---

## 12. Validation Rules File

The JSON validation rules file (`validation/summer_YYYY.json`) must be updated each year before registration opens. Key rules to verify annually:
- `event_date`: First day of Sports Fest for the current year (affects all age calculations)
- `MIN_AGE_DEFAULT`: Currently 13
- `MAX_AGE_DEFAULT`: Currently 35
- Sport-specific age exceptions (Scripture Memorization, Tug-O-War, Pickleball 35+, Table Tennis 35+)
- Non-member quotas per team type
- Partner requirement rules for doubles events

---

## 13. Out of Scope (Current System)

The following are **not** handled by the current system (as of v1.05) and require manual processes:
- Competition scheduling and bracket generation (`sf_schedules`, `sf_competitions`, `sf_results` tables exist but are unused as of v1.02)
- Sportsmanship Award scoring
- Outreach Plan submission and tracking for pre-Christian participants
- On-site check-in and badge printing (photo is collected, but on-site scanning is manual)
- Fee payment processing (handled directly in ChMeetings; only `payment_status` flags are tracked in WordPress)
- **Form submission → VAY-SM Member promotion** (Issue #62): After a participant submits the Individual Participant Application Form, an Admin must manually promote them to a VAY-SM Member in ChMeetings before the middleware can sync them. Automation planned via email-triggered `sync --type form-submitters` command.
- **Annual season reset of ChMeetings custom fields** (Issue #63): Before each season opens, an Admin must archive and clear all Sports Fest and Church Rep Verification custom fields for returning members. Automation planned via `reset-season --year YYYY` command using `PUT /api/v1/people/{id}` with `additional_fields[]` and `POST /api/v1/people/{id}/notes` for archiving.

---

## 14. Planned Enhancements

### Multi-Approver (Triumvirate) Workflow
(See GitHub Issue #5 and ARCHITECTURE.md §Future Enhancement)  
The current system requires only the Senior Pastor's approval. A future enhancement would expand this to a multi-approver model (e.g., Church Rep → Deacon → Pastor) with parallel voting, weighted thresholds, and time-based fallback approvals. This will require schema changes to `sf_approvals` to support multiple approval statuses per participant.

### Scheduling and Results Tracking
Activating `sf_schedules`, `sf_competitions`, and `sf_results` to automate bracket generation, schedule publishing, and result recording — reducing manual coordination during the event weekends.

---

## 15. Glossary

| Term | Definition |
|---|---|
| ChMeetings | Cloud-based church management software (chmeetings.com) used as the primary registration platform |
| Church Code | A unique 3-character identifier for each participating church (e.g., `RPC`) |
| Church Rep | Church Representative; the operational liaison between a church and VAY-SM Staff |
| Non-member / Ringer | A participant not confirmed as a church member by their pastor; subject to quota limits |
| Pre-Christian | A non-member who is not yet a Christian; requires an Outreach Plan |
| Small Church Provision | Rule allowing small churches to merge their youth into a larger church's team |
| VAY | Vietnamese Alliance Youth (Southern California Region) |
| VAY-SM | Vietnamese Alliance Youth Sports Ministry |
| vaysf | The name of the WordPress plugin and GitHub repository powering the integration system |
