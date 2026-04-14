# Usage Specifications

This guide provides instructions for using the Sports Fest ChMeetings Integration system, including the Windows middleware and WordPress plugin.

## Table of Contents

- [Windows Middleware](#windows-middleware)
  - [Running Synchronization Tasks](#running-synchronization-tasks)
  - [Exporting Church Team Reports](#exporting-church-team-reports)
  - [Season Reset (Year-End Archive and Field Clear)](#season-reset-year-end-archive-and-field-clear)
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
# Dry run — show what would be archived and reset, make no changes
python main.py reset-season --year 2025 --dry-run

# Archive 2025 data as ChMeetings profile notes (WORKING)
python main.py reset-season --year 2025 --archive-only

# Archive + reset — full season reset (reset step blocked; see note below)
python main.py reset-season --year 2025

# Reset only — clear fields without writing archive notes (blocked; see note below)
python main.py reset-season --year 2025 --reset-only

# Diagnostic probe — identify what PUT /api/v1/people/{id} accepts (requires --person-id)
python main.py reset-season --year 2025 --person-id 3139537 --probe
```

**What the command does**

1. **Fetches** all members of the VAY-SM ChMeetings group (`VAYSM_GROUP_ID`).
2. **Archive step** (skipped with `--reset-only`): for each member, reads their
   2025 participant record from WordPress (`sf_participants`) and writes a
   structured note to their ChMeetings profile, e.g.:

   > Sports Fest 2025 Archive — 2026-04-14 | Team: RPC | Primary: Badminton (Singles) | Secondary: Bible Challenge - Mixed Team | Member: Yes | Pastor Approved: approved | Checklist: 1✓ 2✓ 3✓ 4✓ 5✓ 6✗

   Archive notes are idempotent — re-running will not create duplicate notes.

3. **Reset step** (skipped with `--archive-only`): intended to call
   `PUT /api/v1/people/{id}` to clear all Sports Fest and Church Rep
   Verification custom fields (dropdowns → `null`, checkboxes → `[]`,
   text fields → `null`).

   > **KNOWN LIMITATION (as of April 2026):** The ChMeetings API returns
   > HTTP 500 whenever `additional_fields` is included in a PUT request,
   > even when sending the current values unchanged.  A tech support ticket
   > has been filed with ChMeetings.  Until a fix or alternate endpoint is
   > provided, use the **manual CSV workaround** below to clear fields.

**Manual CSV workaround for field reset**

Until the API limitation is resolved, clear custom fields via ChMeetings bulk import:

1. Export a people CSV from ChMeetings (`People → Export`).
2. In the exported CSV, blank out all Sports Fest columns for each VAY-SM member.
3. Re-import the CSV via `People → Import`, mapping columns to the same fields.
4. Verify a few profiles manually to confirm fields were cleared.

This is a one-time manual step per season and typically takes 15–30 minutes.

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

Identify participants who need to be added to their respective church team groups in ChMeetings:

```bash
python main.py assign-groups
```

This command:
- Scans ChMeetings for participants with Church Codes who aren't in their church's team group
- Creates an Excel file listing these participants
- Generates a ChMeetings-importable file (`chm_group_import.xlsx`) to easily add them to their "Team [Code]" groups

The Excel files are saved in the `data/` directory by default. On Windows, the system will attempt to automatically open the file upon successful generation.

After running this command, you should import the generated file into ChMeetings (or manually add the people to groups) to ensure every participant is in the correct church group.

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
   - Archive each member's 2025 data as ChMeetings profile notes:
     `python main.py reset-season --year 2025 --archive-only`
   - Clear Sports Fest custom fields using the **manual CSV workaround** described
     in the Season Reset section above (API field reset is pending ChMeetings support)
   - Prepare system for next year
