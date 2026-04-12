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
  - [Church Group Assignment Export](#church-group-assignment-export)
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
- **Group ID**: From the ChMeetings group URL — e.g., `?gid=999847` → use `999847`
- **Person ID**: From a member's profile URL — e.g., `.../MemberDashboard/3692903` → use `3692903`

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

#### Approvals Generation

To generate approval tokens for participants who have completed validation:

```bash
python main.py sync --type approvals
```

This will create tokens and send approval emails to pastors.

#### Validation

To run validation without other sync operations:

```bash
python main.py sync --type validation
```

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

The Excel reports contain:
- List of all participants with their details
- Sports and formats they're registered for
- Approval status
- Any missing requirements or validation issues
- Summary statistics for the church

#### Leveraging Church Export for Mass Resending Pastoral Approval Emails 
##### Dry run to see what would happen
python main.py export-church-teams --force-resend-pending --dry-run

##### Actually resend to pending participants
python main.py export-church-teams --force-resend-pending
python main.py export-church-teams --force-resend-validate1 (still under review - any Box 1-6)
python main.py export-church-teams --force-resend-validate2 (no review yet - no Box 1-6)

##### Resend to specific church
python main.py export-church-teams --church-code TLC --force-resend-pending

### Church Group Assignment

Assign participants to their church team groups in ChMeetings directly via API:

```bash
# Preview who would be assigned (no API calls made)
python main.py assign-groups --dry-run

# Live: assign unassigned participants to their Team groups
python main.py assign-groups
```

This command:
- Scans ChMeetings for participants with a "Church Team" additional field who are not yet in their `Team [Code]` group
- Calls `add_person_to_group()` directly for each unassigned participant — no Excel import step required
- Writes `data/church_team_assignments.xlsx` as an audit log (in both live and dry-run modes); the `Outcome` column shows `added`, `failed`, `missing_group`, or `dry_run` per person
- Logs a warning and skips any church code that has no matching group in ChMeetings (e.g. `Team OTHER` if that group doesn't exist)
- Safe to re-run — participants already in their group are detected during identification and skipped

> **Note:** Close `church_team_assignments.xlsx` in Excel before running, or you will see a warning that the audit file could not be written (the API calls still complete successfully).

After assigning participants to their Team groups, run the approval sync to add approved participants to the `2025 Sports Fest` group:

```bash
python main.py sync --type approvals
```

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
2. 2025 Sports Fest (for approved participants)

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
   - Archive data for future reference
   - Prepare system for next year
