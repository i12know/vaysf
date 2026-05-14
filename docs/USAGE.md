# Usage Specifications

This guide provides instructions for using the Sports Fest ChMeetings Integration system, including the Windows middleware and WordPress plugin.

## Table of Contents

- [Running Tests](#running-tests)
  - [Mock Mode (Default)](#mock-mode-default)
  - [Live Mode](#live-mode)
  - [Live Group Membership Tests](#live-group-membership-tests)
  - [Full Live Tests](#full-live-tests)
- [Windows Middleware](#windows-middleware)
  - [Running Synchronization Tasks](#running-synchronization-tasks)
  - [Exporting Church Team Reports](#exporting-church-team-reports)
  - [Processing Consent Forms](#processing-consent-forms)
  - [Season Reset (Year-End Archive and Field Clear)](#season-reset-year-end-archive-and-field-clear)
  - [Church Team Group Assignment](#church-team-group-assignment)
  - [Auditing Team Groups for Orphaned Members](#auditing-team-groups-for-orphaned-members)
  - [Clearing Seasonal Team Groups](#clearing-seasonal-team-groups)
  - [Inspecting a Single Person](#inspecting-a-single-person)
  - [Scheduled Syncs](#scheduled-syncs)
  - [Testing and Configuration](#testing-and-configuration)
- [WordPress Plugin](#wordpress-plugin)
  - [Admin Dashboard](#admin-dashboard)
  - [Managing Churches](#managing-churches)
  - [Managing Participants](#managing-participants)
  - [Managing Rosters](#managing-rosters)
  - [Handling Validation Issues](#handling-validation-issues)
  - [Pastor Approval Process](#pastor-approval-process)
- [ChMeetings Setup](#chmeetings-setup)
  - [Forms Configuration](#forms-configuration)
  - [Group Structure](#group-structure)
- [Complete Workflow](#complete-workflow)
  - [Before Sports Fest](#before-sports-fest)
  - [During Registration Period](#during-registration-period)
  - [Final Preparations](#final-preparations)
  - [After Sports Fest](#after-sports-fest)

## Running Tests

The middleware ships with a pytest-based test suite covering all connectors and sync logic. Tests run in two modes: **mock** (fast, no credentials) and **live** (hits real APIs).

All commands below assume you are in the `vaysf/middleware/` directory.

### Environment Variables for Testing

| Variable | Default | Description |
|----------|---------|-------------|
| `LIVE_TEST` | `false` | Set to `true` to run all tests against live APIs |
| `FULL_LIVE_TEST` | `false` | Set to `true` to also run the full participant sync (~570 people, takes several minutes) |
| `CHM_TEST_GROUP_ID` | _(none)_ | ChMeetings group ID for live group membership round-trip tests |
| `CHM_TEST_PERSON_ID` | _(none)_ | ChMeetings person ID for live group membership round-trip tests |

### Mock Mode (Default)

No credentials required. All external API calls are intercepted by mock objects.

```bash
pytest tests/ -v
```

Expected result: `27 passed, 5 skipped` (skipped tests require live mode).

### Live Mode

Requires valid `.env` with `CHM_API_URL`, `CHM_API_KEY`, `WP_URL`, and `WP_API_KEY`.

**Windows CMD:**
```cmd
set LIVE_TEST=true && pytest tests/ -v -s
```

**Windows PowerShell:**
```powershell
$env:LIVE_TEST="true"; pytest tests/ -v -s
```

Expected result: most tests pass; `test_sync_participants` is skipped unless `FULL_LIVE_TEST=true` is also set.

### Live Group Membership Tests

`test_add_person_to_group` and `test_remove_person_from_group` perform a self-cleaning round-trip: add a person to a group, confirm they appear in `get_group_people()`, then remove them and confirm they're gone. These tests are skipped if either env var is missing.

**How to find the IDs:**
- **Group ID**: From the ChMeetings group URL - e.g., `?gid=999847` -> use `999847`
- **Person ID**: From a member's profile URL - e.g., `.../MemberDashboard/3692903` -> use `3692903`

**Windows CMD:**
```cmd
set LIVE_TEST=true
set CHM_TEST_GROUP_ID=999847
set CHM_TEST_PERSON_ID=3692903
pytest tests/test_chmeetings_connector.py::test_add_person_to_group tests/test_chmeetings_connector.py::test_remove_person_from_group -v -s
```

**Warning:** Use a disposable test group/person. The test adds then immediately removes the person; if it crashes mid-way the person may remain in the group and need to be removed manually.

### Full Live Tests

Includes `test_sync_participants`, which processes all registered participants and takes several minutes.

**Windows CMD:**
```cmd
set LIVE_TEST=true && set FULL_LIVE_TEST=true && pytest tests/ -v -s
```

For details on what each API call does and how the response format changed in 2026, see [CHMEETINGS_API_MIGRATION.md](CHMEETINGS_API_MIGRATION.md).

---

## Windows Middleware

### Running Synchronization Tasks

The middleware provides several synchronization commands through the `main.py` script:

#### Full Synchronization

To run a complete synchronization of all data:

```bash
python main.py sync --type full
```

This will perform:
- Church synchronization from Excel
- Participant synchronization from ChMeetings
- Validation and roster creation
- Approval token generation
- Approval sync to ChMeetings

#### Churches Sync

To sync only church data from an Excel file:

```bash
python main.py sync-churches --file "data/Church Application Form.xlsx"
```

You can specify a different Excel file if needed:

```bash
python main.py sync-churches --file "path/to/your/excel/file.xlsx"
```

#### Participants Sync

To sync all participants:

```bash
python main.py sync --type participants
```

##### Sync Single Participant

To sync only one participant (for debugging or retries), provide their ChMeetings ID:

```bash
python main.py sync --type participants --chm-id 1234567
```

This will fetch and sync only the participant with ID 1234567 from ChMeetings. Note: The `--chm-id` option works only with `--type participants`.

#### Approvals Sync

To sync approved participants to ChMeetings (adds them to the approved group via API):

```bash
python main.py sync --type approvals
```

By default, this uses the ChMeetings API to add approved participants directly to the designated group (configured via `APPROVED_GROUP_NAME` in `.env`). If the API approach is unavailable or you prefer the legacy Excel export workflow, use the `--excel-fallback` flag:

```bash
python main.py sync --type approvals --excel-fallback
```

The Excel fallback generates an import-ready file that can be manually imported into ChMeetings.

#### Validation

To run validation without other sync operations:

```bash
python main.py sync --type validation
```

This command recalculates non-individual validation issues from the current
WordPress participant/roster data. That includes both `TEAM` and `CHURCH`
issues. It does not pull fresh people from ChMeetings, does not change
approvals, and does not create rosters. It is primarily used to refresh
church-level roster warnings such as:

- non-member quota violations
- reciprocal doubles partner warnings
- ambiguous doubles partner-name warnings

It also performs a conservative self-heal for stale participant-scoped issues:
- if an open `INDIVIDUAL` WordPress validation issue points to a participant whose
  `chmeetings_id` now returns `404 Not Found` from ChMeetings, the issue is
  auto-resolved during validation sync
- this is meant for deleted/re-registered records, so old orphaned validation
  issues do not keep appearing in later church-team workbooks

### Exporting Church Team Reports

Generate Excel reports showing church teams, participants, and their registration/approval status:

```bash
python main.py export-church-teams
```

This will generate reports for all churches in the system, pulling data from both ChMeetings and WordPress.

To generate a report for a specific church:

```bash
python main.py export-church-teams --church-code ABC
```

Where `ABC` is the 3-letter church code.

By default, reports are saved to the export directory (`EXPORT_DIR`) configured in your `.env` file. You can override the output location for a specific run:

```bash
python main.py export-church-teams --output "path/to/custom/directory"
```

For normal church-rep sharing, set `EXPORT_DIR` in `middleware/.env` to your
shared Google Drive folder so `run-me.bat` and `export-church-teams` write the
reports there automatically. Example:

```env
EXPORT_DIR=G:\Shared drives\RP Google Drive\VAY\SportsFest\VAYSF-data
```

The Excel reports contain:
- List of all participants with their details
- Sports and formats they're registered for
- Approval status
- **Registration Date (WP)** - WordPress sports-fest registration timestamp (2026-MM-DD format)
- **Athlete Fee** per participant - deadline-based pricing:
  - $35 for sports athletes (primary or secondary sport) registered before 2026-05-16
  - $60 for sports athletes registered on/after 2026-05-16 (late registration fee)
  - $20 for Other Events only athletes (no deadline increase)
  - blank for Church Rep / VAY SM Staff (non-athletes)
- **Total Athlete Fees** per church on the Summary tab
- Any missing requirements or validation issues
- Summary statistics for the church

The generated workbook includes these operator-focused tabs:

- `Summary`: church-level counts for participants, approvals, open individual `ERROR`s, open TEAM `ERROR`s, and warnings
- `Contacts-Status`: participant directory plus open individual `ERROR` counts
- `Roster`: roster rows with `Open_TEAM_Issue_Count (WP)` and `Open_TEAM_Issue_Desc (WP)`
- `Validation-Issues`: one row per open WordPress validation issue, including `INDIVIDUAL`, `TEAM`, and `CHURCH` issues

The `Validation-Issues` tab is based on the current ChMeetings Team-group
snapshot. Open `INDIVIDUAL` issues tied only to older orphaned WordPress
participant records are filtered out so the workbook stays aligned with the
current participant list.

For doubles partner validation, the export intentionally reports a few
different cases:

- `missing_doubles_partner` (`INDIVIDUAL`, `ERROR`): the participant left the partner field blank
- `doubles_partner_unmatched` (`TEAM`, `WARNING`): a named partner was not reciprocally matched for that same church and event
- short-name ambiguity help: if someone typed a short partner name like `Janice`
  and there is one likely same-event full-name match, the warning can suggest
  `use full name, perhaps Janice Vu`
- reverse partner hint on missing-partner rows: if a participant left the
  partner field blank but one same-event player uniquely points back to them,
  the `Validation-Issues` tab can append a hint such as `perhaps Dean Nguyen
  listed you as partner`; this hint can be inferred from the current roster
  rows and, when needed, from existing TEAM partner-warning rows

#### Leveraging Church Export for Mass Resending Pastoral Approval Emails 
##### Dry run to see what would happen
python main.py export-church-teams --force-resend-pending --dry-run

##### Actually resend to pending participants
python main.py export-church-teams --force-resend-pending
python main.py export-church-teams --force-resend-validate1 (still under review - any Box 1-6)
python main.py export-church-teams --force-resend-validate2 (no review yet - no Box 1-6)

##### Resend to specific church
python main.py export-church-teams --church-code TLC --force-resend-pending

### Processing Consent Forms

Participants receive a link to the Consent Form in their registration confirmation email. Once the church rep has exported completed consent form responses from ChMeetings, the middleware can match each response to a participant record and automatically check the consent checklist box (Box 6) on their ChMeetings profile.

**Basic usage - process all churches:**

```bash
python main.py check-consent --file "data/Consent Form Export.xlsx"
```

**Dry run - preview matches and write audit file without updating ChMeetings:**

```bash
python main.py check-consent --file "data/Consent Form Export.xlsx" --dry-run
```

**Limit to one church:**

```bash
python main.py check-consent --file "data/Consent Form Export.xlsx" --church-code RPC
```

The command writes an audit workbook (`data/consent_check_audit.xlsx`) on every run, including both matched and unmatched rows so you can investigate any gaps.

> **Manual verification:** If a participant's consent form does not auto-link in ChMeetings (per ChMeetings ticket #11991 - linking only works when name and email match exactly), check the Forms section separately and connect the form manually before re-running `check-consent`.

### Season Reset (Year-End Archive and Field Clear)

Before each new registration period opens, all Sports Fest custom fields on
every VAY-SM member's ChMeetings profile must be archived and cleared.  The
`reset-season` command handles this automatically.

**Prerequisites**

- Set `VAYSM_GROUP_ID` in your `.env` file to the ChMeetings group ID for
  the VAY-SM member group.
- Ensure `CHM_API_KEY` and `WP_API_KEY` are configured so the middleware can
  reach both ChMeetings and WordPress.

**Commands**

```bash
# Dry run - show what would be archived and reset, make no changes
python main.py reset-season --year 2025 --dry-run

# Archive 2025 data as ChMeetings profile notes, then clear all custom fields
python main.py reset-season --year 2025

# Archive only - write notes but do not clear fields
python main.py reset-season --year 2025 --archive-only

# Reset only - clear fields without writing archive notes
python main.py reset-season --year 2025 --reset-only

# Test against a single person before running on the full group
python main.py reset-season --year 2025 --person-id 3139537
python main.py reset-season --year 2025 --person-id 3139537 --dry-run

# Diagnostic: probe what the PUT endpoint accepts for a single person
python main.py reset-season --year 2025 --probe --person-id 3139537
```

### Church Team Group Assignment

Use the assignment command to add people with a Church Team code into their
matching `Team XXX` group directly via the ChMeetings API:

```bash
python main.py assign-groups
```

Preview the changes without making API calls:

```bash
python main.py assign-groups --dry-run
```

This command writes an audit workbook to `data/church_team_assignments.xlsx`
on every run.

### Clearing Seasonal Team Groups

Use the clearing command during season transition to remove current members
from `Team XXX` groups without deleting the groups themselves.

Preview one church first:

```bash
python main.py clear-team-groups --church-code RPC --dry-run
```

Then execute for that church:

```bash
python main.py clear-team-groups --church-code RPC --execute
```

When ready, preview all team groups:

```bash
python main.py clear-team-groups --dry-run
```

Then execute for all team groups:

```bash
python main.py clear-team-groups --execute
```

Notes:
- Only groups matching the `TEAM_PREFIX` pattern (for example `Team RPC`) are targeted.
- Approved, staff, and volunteer groups are never touched by this command.
- Empty groups are treated as a clean no-op.
- Orphaned membership rows that return DELETE `404` are logged as `already absent` and do not fail the run.
- The audit workbook is written to `data/team_group_clearing_audit.xlsx`.
- Group Leaders remain assigned to the group after members are cleared; that is expected.

### Inspecting One ChMeetings Person ID

Use this command when you need to debug one ChMeetings ID without running a
full participant sync:

```bash
python main.py inspect-person --chm-id 3628898
```

This command:
- fetches the raw ChMeetings person record if it still exists
- reports a clean `404 Not Found` if the ChMeetings record is gone
- looks for any matching WordPress participant with the same `chmeetings_id`
- prints any matching WordPress participant, roster, approval, and validation-issue data

This is useful when a Team-group membership looks stale and you need to confirm
whether the person still exists in ChMeetings, WordPress, both, or neither.

### Auditing Team Groups for Orphaned IDs

Use this command when `export-church-teams` or `sync --type participants`
reports Team-group members whose ChMeetings person records return `404`:

```bash
python main.py audit-team-groups --church-code GAC
```

To audit all Team groups:

```bash
python main.py audit-team-groups
```

This command:
- reads the current memberships in each `Team XXX` group
- checks each membership ID with `GET /people/{id}`
- flags rows as orphaned when the Team-group membership exists but the person record is gone
- looks for any matching WordPress participant with the same `chmeetings_id`
- writes the audit workbook to `data/team_group_orphan_audit.xlsx`

This is the safest way to confirm stale Team-group memberships before manually
cleaning them up in ChMeetings.

**Recommended run order**

Before running on the full VAY-SM group, test with a single person and a small
church team first:

```bash
# 1. Probe - verify the PUT endpoint accepts clearing values (should all pass)
python main.py reset-season --year 2025 --probe --person-id <any_person_id>

# 2. Single person - confirm archive note and field clear look correct
python main.py reset-season --year 2025 --person-id <any_person_id>

# 3. Small group - set VAYSM_GROUP_ID to a small church team group ID
set VAYSM_GROUP_ID=<small_group_id>
python main.py reset-season --year 2025 --dry-run
python main.py reset-season --year 2025

# 4. Full run - restore VAYSM_GROUP_ID to the real VAY-SM group
set VAYSM_GROUP_ID=<vaysm_group_id>
python main.py reset-season --year 2025
```

**What the command does**

1. **Fetches** all members of the VAY-SM ChMeetings group (`VAYSM_GROUP_ID`).
2. **Archive step** (skipped with `--reset-only`): for each member, reads their
   2025 participant record from WordPress (`sf_participants`) and writes a
   structured note to their ChMeetings profile, e.g.:

   > Sports Fest 2025 Archive - 2026-04-14 | Team: RPC | Primary: Badminton (Singles) | Secondary: Bible Challenge - Mixed Team | Member: Yes | Pastor Approved: approved | Checklist: 1[Y] 2[Y] 3[Y] 4[Y] 5[Y] 6[N]

   Archive notes are idempotent - re-running will not create duplicate notes.

3. **Reset step** (skipped with `--archive-only`): calls
   `PUT /api/v1/people/{id}` to clear all Sports Fest and Church Rep
   Verification custom fields (dropdowns -> `null`, checkboxes -> `[]`,
   text fields -> `null`). The full person profile is included in the
   request to preserve standard fields (email, mobile, birthdate, etc.)
   that would otherwise be wiped by the PUT full-replace semantics.

**Fields cleared**

Sports Fest section (section 116139): My role is, Church Team, Church
membership question, Primary Sport, Primary Racquet Format, Primary Racquet
Partner, Secondary Sport, Secondary Racquet Format, Secondary Racquet Partner,
Other Events, Age Verification, Parent/Guardian name/email/phone, Additional
Info.

Church Rep Verification section (section 116188): Completion Check List,
Notes on Progress.

**Timing**

Run this command **before the new Individual Participant Application Form goes
live** — typically at or before the Church Registration Deadline for the
upcoming year.

### Church Group Assignment Export

Assign participants to their church team groups in ChMeetings directly via API:

```bash
# Preview who would be assigned (no API calls made)
python main.py assign-groups --dry-run

# Live: assign unassigned participants to their Team groups
python main.py assign-groups

# Limit the run to the current-season Individual Application export
python main.py assign-groups --file "data/Individual Application Form.xlsx" --dry-run
```

This command:
- Scans ChMeetings for participants with a "Church Team" additional field who are not yet in their `Team [Code]` group
- Calls `add_person_to_group()` directly for each unassigned participant - no Excel import step required
- Writes `data/church_team_assignments.xlsx` as an audit log (in both live and dry-run modes); the `Outcome` column shows `added`, `failed`, `missing_group`, or `dry_run` per person
- Logs a warning and skips any church code that has no matching group in ChMeetings (e.g. `Team OTHER` if that group doesn't exist)
- Safe to re-run - participants already in their group are detected during identification and skipped

> **Current-season filter:** When `--file` is provided, only registrants present in that Individual Application export are considered for assignment; this is useful after a season reset when older ChMeetings people still retain stale church-team values.

> **Note:** Close `church_team_assignments.xlsx` in Excel before running, or you will see a warning that the audit file could not be written (the API calls still complete successfully).
After assigning participants to their Team groups, run the approval sync to add approved participants to the `2025 Sports Fest` group:

```bash
python main.py sync --type approvals
```

### Auditing Team Groups for Orphaned Members

Over time, ChMeetings group memberships can contain person IDs that no longer resolve to a live person record (deleted or merged accounts). The `audit-team-groups` command identifies these orphaned IDs so you can clean them up.

**Audit all Team groups (review only - no changes):**

```bash
python main.py audit-team-groups
```

**Audit a single church team:**

```bash
python main.py audit-team-groups --church-code GAC
```

The command writes an audit workbook to `data/team_group_orphan_audit.xlsx` listing every orphaned ID, the group it was found in, and lookup status.

**Remove orphaned memberships from ChMeetings:**

```bash
python main.py audit-team-groups --remove-orphans
```

Run the plain audit first to review the workbook, then re-run with `--remove-orphans` to delete the stale memberships. The flag combines with `--church-code` for targeted cleanup:

```bash
python main.py audit-team-groups --church-code GAC --remove-orphans
```

The summary log will confirm how many were removed (e.g., `Removed: 21/21 orphaned membership(s).`). After cleanup, future `export-church-teams` runs will no longer log 404 warnings for those IDs.

> During `export-church-teams`, orphaned IDs are silently skipped and a summary warning is logged per church (e.g., `Team GAC: skipped 10 orphaned member IDs - [...]`). Run `audit-team-groups` after seeing those warnings to get the full list, then use `--remove-orphans` to clean up.

### Inspecting a Single Person

For debugging, you can pull the full ChMeetings profile and any matching WordPress participant record for one person by their ChMeetings ID:

```bash
python main.py inspect-person --chm-id 3139537
```

This prints all standard and custom fields from ChMeetings alongside the WordPress approval status, validation issues, and roster entries - useful when a participant's data looks inconsistent between the two systems.

### Scheduled Syncs

For automatic synchronization at regular intervals:

```bash
# Run sync every 60 minutes
python main.py schedule --interval 60

# Run as a background process (daemon)
python main.py schedule --interval 60 --daemon
```

To set up as a Windows scheduled task:

1. Create a batch file (e.g., `run-sync.bat`):
   ```
   @echo off
   cd %USERPROFILE%\vaysf-middleware
   call venv\Scripts\activate
   python main.py sync --type full
   ```

2. Use Windows Task Scheduler to run this batch file at desired intervals.

### Testing and Configuration

#### Testing Connectivity

To test system connectivity:

```bash
# Test all connections
python main.py test --system all --test-type connectivity

# Test only WordPress connection
python main.py test --system wordpress --test-type connectivity

# Test only ChMeetings connection
python main.py test --system chmeetings --test-type connectivity
```

To test email functionality:

```bash
python main.py test --system wordpress --test-type email --test-email "test@example.com"
```

#### Inspecting ChMeetings API Fields

To inspect ChMeetings custom field definitions and verify that your configured field mappings match what the API returns:

```bash
python main.py test --system chmeetings --test-type api-inspect
```

This will:
- Retrieve all custom field definitions from ChMeetings via the `get_fields()` API
- Cross-reference each field in `CHM_FIELDS` (in `config.py`) against the live API response
- Report OK or MISSING for each expected field name

This is useful after ChMeetings updates or when setting up a new environment to ensure field names haven't changed.

#### Validating Configuration

Verify your configuration file by running:

```bash
python main.py config --validate
```

This will check that all required environment variables and settings are properly set and will report any issues.

## WordPress Plugin

### Admin Dashboard

After logging into WordPress admin, navigate to the Sports Fest menu in the sidebar to access:

- **Dashboard**: Overview of statistics and quick actions
- **Churches**: Church management and approval status
- **Participants**: Participant management and approval status
- **Rosters**: Sport roster management
- **Approvals**: Pastor approval token management
- **Validation**: Validation issue tracking and resolution
- **Settings**: System configuration

### Managing Churches

The Churches page displays all participating churches with their details:

- **Add Church**: Manually add a church (usually done via sync)
- **Edit Church**: Update church details including pastor and rep info
- **View Participants**: Filter participants by church
- **Church Sync**: Trigger church sync from Excel

### Managing Participants

The Participants page shows all registered participants:

- **Filter Options**: Filter by church, approval status, or sport
- **Edit Participant**: Update participant details
- **View Approvals**: Check approval status
- **Participant Sync**: Trigger participant sync from ChMeetings

Church representatives can be identified by the "Church Rep" role in the system.

### Managing Rosters

The Rosters page manages sport roster entries:

- **Filter Options**: Filter by church, sport, or format
- **Add Roster Entry**: Manually add roster entry
- **Edit Roster Entry**: Update roster details
- **Delete Roster Entry**: Remove participant from a sport

### Handling Validation Issues

The Validation Issues page helps identify and resolve participant eligibility issues:

- **Filter Options**: Filter by church, severity, rule level, or sport
- **Severity Levels**: ERROR (blocks participation), WARNING (informational)
- **Resolution**: Mark issues as resolved once addressed
- **Bulk Actions**: Resolve or reopen multiple issues at once

Common validation issues include:
- Age restrictions (too young/old for a sport)
- Gender mismatches (wrong gender for gender-specific sports)
- Missing consent forms
- Missing profile photos
- Missing doubles partner names (`ERROR`)
- Doubles partner reciprocity or name-matching warnings (`WARNING`)

For doubles issues, use this interpretation:

- `Partner name required ...` means the participant must fill in the partner
  field on their own registration
- `... did not reciprocally list ...` means both participants should review the
  same doubles event and make sure they list each other
- `... ambiguous; use full name ...` means the short partner name was not
  precise enough; ask the participant to enter the full partner name
- `perhaps <Full Name> listed you as partner` is an export-time hint derived
  from the current church roster, intended to help church reps resolve blank
  partner fields faster

### Pastor Approval Process

The Approval workflow works as follows:

1. Participant registers in ChMeetings
2. Church Rep verifies their eligibility
3. Middleware generates approval token
4. WordPress sends approval email to pastor
5. Pastor clicks approve/deny link in email
6. WordPress records decision
7. Middleware syncs approval status back to ChMeetings

The Approvals page allows you to:
- View pending/completed approvals
- Resend approval emails
- Generate new tokens
- Check token expiry dates

## ChMeetings Setup

### Forms Configuration

Three primary forms are needed in ChMeetings:

#### Church Application Form

Fields required:
- Church Name
- Church Code (3-letter code)
- Pastor Name
- Pastor Email
- Pastor Phone Number
- Church Rep Name
- Church Rep Email
- Church Rep Phone
- Sports Ministry Level (1-6)

#### Individual Application Form

Fields required:
- First Name
- Last Name
- Gender
- Church Team (dropdown of 3-letter codes)
- Would the team's Senior Pastor say that you belong to his church? (Yes/No)
- Mobile Phone
- Email
- My role is (Athlete/Participant, Church Rep, VAY SM Staff)
- Birthdate
- Primary Sport
- Primary Racquet Sport Format (if applicable)
- Primary Racquet Sport Partner (if applicable)
- Secondary Sport
- Secondary Racquet Sport Format (if applicable)
- Secondary Racquet Sport Partner (if applicable)
- Other Events
- Photo (upload field)

#### Consent Form

Required sections:
- Liability Release and Assumption of Risk
- Medical Release & Disclaimer
- Media/Photo Release
- Behavior/Conduct Agreement
- Confirmation & Signature
- For minors: Parent/Guardian information and signature

### Checking Consent Forms

Upon completion of the Individual Application Form, user will receive an email confirmation with the https://bit.ly/vaysm-consent link to the Consent Form. The church rep will need to verify the consent form manually:

1. **Use the People Record panel in ChMeetings** - Linked forms appear automatically in each participant's record if their name and email match exactly. This allows for quick verification of consent form completion.

2. **Form-link caveat** - Per ChMeetings ticket #11991: automatic linking only works when the registrant already exists at the same level and contact information matches exactly; otherwise a manual form link is required. For participants whose forms don't automatically link, check the Forms section separately and manually connect them.

### Group Structure

ChMeetings group structure should include:

1. Team Groups (named "Team XYZ" where XYZ is the church code)
2. Approved participants group (configured via `APPROVED_GROUP_NAME` in `.env`, e.g., "2026 Sports Fest")

Church Reps should be assigned as group leaders for their respective teams.

## Complete Workflow

### Before Sports Fest

1. **Initial Setup**
   - Install and configure the WordPress plugin
   - Set up the Windows middleware
   - Create forms in ChMeetings
   - Configure groups in ChMeetings

2. **Church Registration**
   - Churches submit applications via the Church Application Form
   - Collect Excel export of churches
   - Run church sync to WordPress
   - Verify church data in WordPress admin

### During Registration Period

1. **Participant Registration**
   - Participants register via Individual Application Form
   - Church Reps verify participant information
   - Run regular participant syncs to WordPress
   - Check validation issues in WordPress admin
   - Resolve validation issues with Church Reps
   - Regularly run the group assignment export (`assign-groups`) to assign participants into their church teams, and import those assignments in ChMeetings

2. **Approval Process**
   - Generate approval tokens for validated participants
   - Pastors receive approval emails and make decisions
   - Track approval status in WordPress admin
   - Follow up on pending approvals

### Final Preparations

1. **Roster Finalization**
   - Verify all rosters are complete
   - Confirm all validation issues are resolved
   - Ensure all participants have pastor approval
   - Sync approved participants to ChMeetings
   - Generate final Church Team Status reports (`export-church-teams`) for each church to review their roster and participant statuses
   - Provide these reports to church representatives for a final verification before the event (via Google Drive shared files)

2. **Data Export**
   - Export participant lists for event check-in
   - Export rosters for competition organizers
   - Generate reports for VAY-SM Staff

### After Sports Fest

1. **Data Collection**
   - Record competition results
   - Document participation statistics

2. **System Cleanup**
   - Archive all members' data and clear all Sports Fest custom fields:
     `python main.py reset-season --year 2025`
   - Verify a few profiles in ChMeetings to confirm archive notes were written
     and fields are cleared
   - Prepare system for next year (see [SEASON_TRANSITION.md](SEASON_TRANSITION.md))
