# System Architecture

This document provides a comprehensive overview of the Sports Fest ChMeetings Integration system architecture, including components, data flow, database schemas, and key classes.

## Three-Tier Architecture

The system uses a three-tier architecture to separate concerns and provide a robust, maintainable solution:

```
                             +------------------+
                             |                  |
                             |   ChMeetings     |
                             |   (Core Data)    |
                             |                  |
                             +--------^---------+
                                      |
                                      | API
                                      |
                             +--------v---------+
                             |                  |
                             |    Windows       |
                             |    Middleware    |
                             |                  |
                             +--------^---------+
                                      |
                                      | REST API
                                      |
                             +--------v---------+
                             |                  |
                             |    WordPress     |
                             |    (Operations)  |
                             |                  |
                             +------------------+
```

### 1. ChMeetings (Core Data & Registration)

ChMeetings serves as the primary data source and handles:
- Participant registration and profile management
- Church registration and team management
- Group assignments for participants
- Payment processing
- Photo storage

### 2. Windows-based Python Middleware

The middleware is responsible for:
- Data synchronization between ChMeetings and WordPress
- Validation of participant data using JSON rules
- Generation of approval tokens
- Scheduled synchronization tasks
- Error handling and logging

### 3. WordPress on Bluehost (Operations)

WordPress provides:
- Custom REST API endpoints for data access
- Pastor approval workflow via email tokens
- Admin interface for system management
- Participant roster management
- Validation issue tracking and resolution

## Data Flow

```
+----------------+     +-------------------+     +------------------+     +-------------------+
| Registration   |     | Church Rep        |     | Pastor           |     | Event            |
| in ChMeetings  |---->| Verification      |---->| Approval via     |---->| Participation    |
| Forms & Profiles|     | in ChMeetings    |     | WordPress/Email  |     | & Scheduling     |
+----------------+     +-------------------+     +------------------+     +-------------------+
        ^                       ^                        ^                         ^
        |                       |                        |                         |
        |                       |                        |                         |
        +-----------------------+------------------------+-------------------------+
                                           |
                                 +-----------------+
                                 | Validation at   |
                                 | Multiple Levels |
                                 +-----------------+
                                           |
                                  +----------------+
                                  | Middleware     |
                                  | Syncs Data     |
                                  | Between Systems|
                                  +----------------+
```

## WordPress Database Schema

The WordPress plugin uses 10 custom tables to store and manage Sports Fest data:

### 1. sf_churches
Stores church information including pastor and church representative details.

```sql
CREATE TABLE sf_churches (
  church_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  church_code VARCHAR(3) NOT NULL,
  church_name VARCHAR(255) NOT NULL,
  pastor_name VARCHAR(255) NOT NULL,
  pastor_email VARCHAR(255) NOT NULL,
  pastor_phone VARCHAR(50) DEFAULT NULL,
  church_rep_name VARCHAR(255) DEFAULT NULL,
  church_rep_email VARCHAR(255) DEFAULT NULL,
  church_rep_phone VARCHAR(50) DEFAULT NULL,
  sports_ministry_level TINYINT UNSIGNED DEFAULT 1,
  registration_status VARCHAR(50) DEFAULT 'pending',
  insurance_status VARCHAR(50) DEFAULT 'pending',
  payment_status VARCHAR(50) DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (church_id),
  UNIQUE KEY church_code (church_code)
)
```

### 2. sf_participants
Stores participant information including sports preferences and approval status.

```sql
CREATE TABLE sf_participants (
  participant_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  chmeetings_id VARCHAR(50) DEFAULT NULL,
  church_code VARCHAR(3) NOT NULL,
  first_name VARCHAR(255) NOT NULL,
  last_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) DEFAULT NULL,
  phone VARCHAR(50) DEFAULT NULL,
  gender VARCHAR(10) DEFAULT NULL,
  birthdate DATE DEFAULT NULL,
  is_church_member TINYINT(1) DEFAULT 0,
  primary_sport VARCHAR(50) DEFAULT NULL,
  primary_format VARCHAR(50) DEFAULT NULL,
  primary_partner VARCHAR(255) DEFAULT NULL,
  secondary_sport VARCHAR(50) DEFAULT NULL,
  secondary_format VARCHAR(50) DEFAULT NULL,
  secondary_partner VARCHAR(255) DEFAULT NULL,
  other_events TEXT DEFAULT NULL,
  photo_url TEXT DEFAULT NULL,
  approval_status VARCHAR(50) DEFAULT 'pending',
  parent_info TEXT DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (participant_id),
  UNIQUE KEY chmeetings_id (chmeetings_id),
  KEY church_code (church_code)
)
```

### 3. sf_rosters
Manages sport-specific roster entries for participants.

```sql
CREATE TABLE sf_rosters (
  roster_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  church_code VARCHAR(3) NOT NULL,
  participant_id BIGINT UNSIGNED NOT NULL,
  sport_type VARCHAR(50) NOT NULL,
  sport_gender VARCHAR(20) NOT NULL,
  sport_format VARCHAR(20) NOT NULL,
  team_order VARCHAR(5),
  partner_name VARCHAR(50),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (roster_id),
  FOREIGN KEY (church_code) REFERENCES sf_churches(church_code) ON DELETE CASCADE,
  FOREIGN KEY (participant_id) REFERENCES sf_participants(participant_id) ON DELETE CASCADE,
  KEY church_sport (church_code, sport_type, sport_gender, sport_format)
)
```

### 4. sf_approvals
Tracks pastor approval requests and statuses.

```sql
CREATE TABLE sf_approvals (
  approval_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  participant_id BIGINT UNSIGNED NOT NULL,
  church_id BIGINT UNSIGNED NOT NULL,
  approval_token VARCHAR(255) NOT NULL,
  token_expiry DATETIME NOT NULL,
  pastor_email VARCHAR(255) NOT NULL,
  approval_status VARCHAR(50) DEFAULT 'pending',
  approval_date DATETIME DEFAULT NULL,
  approval_notes TEXT DEFAULT NULL,
  synced_to_chmeetings TINYINT(1) DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (approval_id),
  UNIQUE KEY participant_church (participant_id, church_id),
  KEY approval_token (approval_token),
  KEY approval_status (approval_status)
)
```

### 5. sf_validation_issues
Stores validation issues and their resolution status.

```sql
CREATE TABLE sf_validation_issues (
  issue_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  church_id BIGINT UNSIGNED NOT NULL,
  participant_id BIGINT UNSIGNED DEFAULT NULL,
  issue_type VARCHAR(50) NOT NULL,
  issue_description TEXT NOT NULL,
  rule_code VARCHAR(50) DEFAULT NULL,
  rule_level VARCHAR(20) DEFAULT NULL,
  severity VARCHAR(10) DEFAULT 'ERROR',
  sport_type VARCHAR(50) DEFAULT NULL,
  sport_format VARCHAR(20) DEFAULT NULL,
  status VARCHAR(50) DEFAULT 'open',
  reported_at DATETIME DEFAULT NULL,
  resolved_at DATETIME DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (issue_id),
  KEY church_id (church_id),
  KEY participant_id (participant_id),
  KEY rule_code (rule_code),
  KEY rule_level (rule_level),
  KEY severity (severity),
  KEY sport_type (sport_type),
  KEY status (status)
)
```

### Additional Tables 

- **sf_competitions**: Tracks competition categories and formats
- **sf_schedules**: Stores match schedules and locations
- **sf_results**: Tracks competition results and winners
- **sf_sync_log**: Logs synchronization operations and status
- **sf_email_log**: Tracks email communications

(These tables are fully documented in vaysf.php and are not used as of v1.02 (Sports Fest 2025) except for the sf_email_log)

## Windows Middleware Architecture

### Directory Structure

```
%USERPROFILE%\middleware\
├── main.py                     # Main entry script with CLI
├── config.py                   # Configuration and constants
├── requirements.txt            # Python dependencies
├── group_assignment.py         # Script to generate church team assignment Excel (assign-groups command)
├── church_teams_export.py      # Script to generate church status reports (export-church-teams command)
├── .env                        # Environment config
├── .env.template               # Template for .env
├── .key                        # Encryption key for sensitive data
├── run-sync.bat                # Batch file for manual sync
├── chmeetings\                 # ChMeetings connector module
│   ├── __init__.py
│   └── backend_connector.py    # ChMeetings API connector
├── wordpress\                  # WordPress connector module
│   ├── __init__.py
│   └── frontend_connector.py   # REST API client
├── sync\                       # Sync orchestration module
│   ├── __init__.py
│   ├── churches.py             # ChurchSyncer class
│   ├── participants.py         # ParticipantSyncer class
│   └── manager.py              # SyncManager class
├── validation\                 # Validation module
│   ├── __init__.py
│   ├── models.py               # Pydantic models and RulesManager
│   ├── individual_validator.py # Validation implementation
│   └── summer_2025.json        # JSON validation rules
├── tests\                      # PyTest testing framework
│   ├── test_chmeetings_connector.py
│   ├── test_wordpress_connector.py  
│   ├── test_sync_manager.py
│   ├── test_validation.py
│   └── mock_data*.json         # Mock data files for testing
├── logs\                       # Log directory
├── data\                       # Import and export data files from ChMeetings
│   └── Church Application Form.xlsx
└── temp\                       # Temporary files
```

### Key Python Classes

#### ChMeetingsConnector
Provides API access to ChMeetings data.
```python
class ChMeetingsConnector:
    def authenticate(self)
    def get_people(self, params=None)         # paginates via total_count; sends include_additional_fields=True
    def get_person(self, person_id)            # unwraps {"data": {...}} envelope
    def get_groups(self, params=None)
    def get_group_people(self, group_id)
    def get_fields(self)                                      # GET /api/v1/people/fields → field_id / field_type map
    def add_person_to_group(self, group_id, person_id)        # POST /api/v1/groups/{id}/memberships; 429-aware retry
    def remove_person_from_group(self, group_id, person_id)   # DELETE /api/v1/groups/{id}/memberships/{person_id}
    def add_member_note(self, person_id, note_text)           # POST /api/v1/people/{id}/notes
    def update_person(self, person_id, first_name,
                      last_name, additional_fields)           # PUT /api/v1/people/{id} → reset custom fields
```

See [CHMEETINGS_API_MIGRATION.md](CHMEETINGS_API_MIGRATION.md) for the full history of API breaking changes and the fixes applied in v1.05.

#### WordPressConnector
Handles REST API communication with WordPress.
```python
class WordPressConnector:
    def get_churches(self)
    def create_church(self, church_data)
    def update_church_by_code(self, church_code, church_data)
    def get_participants(self, params=None)
    def create_participant(self, participant_data)
    def update_participant(self, participant_id, participant_data)
    def get_rosters(self, params=None)
    def create_roster(self, roster_data)
    def delete_roster(self, roster_id)
    def send_email(self, to, subject, message, from_email=None)
```

#### SyncManager
Orchestrates the synchronization process.
```python
class SyncManager:
    def authenticate(self)
    def sync_churches_from_excel(self, excel_file_path)
    def sync_participants(self, chm_id=None)
    def generate_approvals(self)
    def sync_approvals_to_chmeetings(self, use_excel_fallback=False)
    def validate_data(self)
    def run_full_sync(self)
```
The `sync_approvals_to_chmeetings()` method uses the ChMeetings API (`add_person_to_group()`) by default to add approved participants to the designated group. Pass `use_excel_fallback=True` to fall back to the legacy Excel export workflow.

#### IndividualValidator
Validates participant data against JSON rules.
```python
class IndividualValidator:
    def validate(self, participant_data)
    def _validate_age(self, participant)
    def _validate_gender(self, participant)
    def _validate_photo(self, participant)
    def _validate_consent(self, participant)
```

#### ChurchTeamsExporter Utility
Consolidates data from ChMeetings and WordPress to produce Excel reports of team rosters and statuses.
```python
class ChurchTeamsExporter:
    def generate_reports(self, target_church_code=None, output_dir=None)
    def _fetch_data(self, church_code=None)
    def _create_report(self, church_data, participants_data)
    def _calculate_age(self, birthdate)
```

#### Group Assignment Utility
Scans ChMeetings for ungrouped people with church codes and outputs an Excel file for import. This ensures participants are placed into their 'Team [Code]' groups (related to the assign-groups command).

## WordPress Plugin Architecture

### Plugin Structure
```
/wp-content/plugins/vaysf/
├── vaysf.php                   # Main plugin file
├── assets/
│   └── logo.png
├── includes/
│   ├── rest-api.php            # REST API endpoints
│   ├── functions.php           # Helper functions
│   ├── shortcodes.php          # WordPress shortcodes
│   └── class-vaysf-statistics.php # Statistics utilities
├── templates/
│   └── pastor-approval.php     # Pastor approval page
└── admin/
    └── admin.php               # Admin interface
```

### REST API Endpoints

| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/wp-json/vaysf/v1/churches` | GET, POST | List/create churches |
| `/wp-json/vaysf/v1/churches/{code}` | GET, PUT | Manage specific church |
| `/wp-json/vaysf/v1/participants` | GET, POST | List/create participants |
| `/wp-json/vaysf/v1/participants/{id}` | GET, PUT | Manage specific participant |
| `/wp-json/vaysf/v1/rosters` | GET, POST | List/create roster entries |
| `/wp-json/vaysf/v1/rosters/{id}` | GET, PUT, DELETE | Manage specific roster |
| `/wp-json/vaysf/v1/validation-issues` | GET, POST | List/create validation issues |
| `/wp-json/vaysf/v1/validation-issues/{id}` | PUT | Update validation issue |
| `/wp-json/vaysf/v1/validation-issues/bulk` | POST | Bulk update validation issues |
| `/wp-json/vaysf/v1/approvals` | GET, POST | List/create approval requests |
| `/wp-json/vaysf/v1/approvals/process-token` | GET | Process pastor approval token |
| `/wp-json/vaysf/v1/sync-logs` | GET, POST | List/create sync logs |
| `/wp-json/vaysf/v1/sync-logs/{id}` | PUT | Update sync log |
| `/wp-json/vaysf/v1/send-email` | POST | Send email via WordPress |

## JSON-Based Validation System

The middleware implements a sophisticated validation system using JSON-based rules and Pydantic models:

### Rule Structure

```json
{
  "metadata": {
    "version": "2025.1.0",
    "collection": "SUMMER_2025",
    "event_date": "2025-07-19",
    "last_updated": "2025-03-20",
    "description": "Rules for Sports Fest 2025"
  },
  "rules": [
    {
      "rule_id": 1,
      "rule_code": "MIN_AGE_DEFAULT",
      "rule_level": "INDIVIDUAL",
      "rule_type": "age",
      "category": "min",
      "sport_event": "default",
      "parameter": null,
      "value": "13",
      "severity": "ERROR",
      "description": "Participants must be at least 13 years old",
      "collection": "SUMMER_2025"
    }
  ]
}
```

These rules are stored in SUMMER_2025.json in the validation folder and should match with config.py's constants

### Multi-Level Validation

1. **Individual Level**
   - Age requirements
   - Gender restrictions
   - Photo and consent requirements

2. **Team Level**
   - Team composition rules
   - Partner matching for doubles events
   - Non-member quotas

3. **Church Level**
   - Maximum teams per sport type
   - Roster distribution requirements

4. **Tournament Level**
   - Cross-church validation
   - Overall participation limits

### Validation Severity Levels

- **ERROR**: Blocks participation, requires resolution
- **WARNING**: Generates warnings but doesn't block
- **INFO**: Information-only, logged for reporting

## Pastor Approval Workflow

```
┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Participant│     │  Church Rep │     │  Middleware │     │  WordPress  │     │   Pastor    │
│              │     │             │     │             │     │             │     │             │
└──────┬───────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                    │                   │                   │                   │
       │ Register           │                   │                   │                   │
       │────────────────────┼───────────────────┼───────────────────┼───►               │
       │                    │                   │                   │                   │
       │                    │ Verify Identity   │                   │                   │
       │                    │ & Documents       │                   │                   │
       │                    │◄──────────────────┤                   │                   │
       │                    │                   │                   │                   │
       │                    │ Mark Ready for    │                   │                   │
       │                    │ Approval          │                   │                   │
       │                    │───────────────────┼───────────────────┼───►               │
       │                    │                   │                   │                   │
       │                    │                   │ Sync Participant  │                   │
       │                    │                   │ to WordPress      │                   │
       │                    │                   │───────────────────┼───►               │
       │                    │                   │                   │                   │
       │                    │                   │ Generate Approval │                   │
       │                    │                   │ Token             │                   │
       │                    │                   │───────────────────┼───►               │
       │                    │                   │                   │                   │
       │                    │                   │                   │ Send Approval     │
       │                    │                   │                   │ Email             │
       │                    │                   │                   │───────────────────┼───►
       │                    │                   │                   │                   │ Review and
       │                    │                   │                   │                   │ Approve/Deny
       │                    │                   │                   │ Record            │
       │                    │                   │                   │ Decision          │
       │                    │                   │                   │◄──────────────────┤
       │                    │                   │                   │                   │
       │                    │                   │ Sync Approval     │                   │
       │                    │                   │ to ChMeetings     │                   │
       │                    │                   │◄──────────────────┼───────────────────┤
       │                    │                   │                   │                   │	   
       │ Receive            │                   │                   │                   │
       │ Notification       │                   │                   │                   │
       │◄───────────────────┼───────────────────┼───────────────────┼───────────────────┤
	   
```

## Future Enhancement: Multi-Vote Approval Workflow

As discussed in GitHub Issue #5, a more robust "triumvirate" approval system is planned for future releases. Three main approaches are under consideration: 
  (1) Sequential approval chain where each approver (e.g., Church Rep → Deacon → Pastor) must approve in order; 
  (2) Parallel independent voting where all approvers receive simultaneous notifications and approve independently; 
  (3) Threshold-based approval where different approvers have weighted votes and approval requires meeting a combined threshold. 
The current design favors approach #2 with potential for a time-based fallback mechanism where default approvals occur after certain timeframes, reducing bottlenecks while maintaining oversight. This enhancement would build upon the existing approval infrastructure but require database schema updates to sf_approvals to track multiple approval statuses.

## Command-Line Interface

The middleware provides a command-line interface through `main.py`:

```
Usage: main.py [command] [options]

Commands:
  sync                   Sync data between systems
    --type TYPE          Type of data to sync:
                           churches      Sync churches from ChMeetings
                           participants  Sync participants from VAY-SM group
                           approvals     Sync approval statuses to ChMeetings
                           validation    Run validation rules
                           full          Run complete sync pipeline
                           form-submitters  [Planned - Issue #62] Detect form
                                            submitters not yet added as VAY-SM
                                            Members and promote them via API
    --chm-id ID          ChMeetings ID for syncing a specific participant
    --excel-fallback     Use Excel export instead of API for approval sync
  
  sync-churches          Sync churches from Excel file
    --file FILE          Path to the church Excel file
  
  export-church-teams    Generate Excel reports for church teams
    --church-code CODE   Generate report for specific church
    --output DIR         Output directory for reports
  
  assign-groups          Create group assignments for people with church codes

  reset-season           [Planned - Issue #63] Archive 2025 custom field data
                         as ChMeetings profile notes, then clear all Sports Fest
                         and Church Rep Verification custom fields for all
                         VAY-SM Members
    --year YEAR          Season year to archive (e.g. 2025)
    --dry-run            Show what would change; make no API calls
    --archive-only       Write archive notes only; do not reset fields
    --reset-only         Clear fields only; skip archive note writing
  
  config                 Configure system settings
    --validate           Validate current configuration
  
  schedule               Run scheduled sync jobs
    --interval MINUTES   Interval in minutes between sync jobs
    --daemon             Run as daemon process
  
  test                   Test connectivity and functionality
    --system SYSTEM      System to test (chmeetings, wordpress, all)
    --test-type TYPE     Type of test to run (connectivity, churches, email,
                         api-inspect, all)
    --test-email EMAIL   Email address for email test
```

## Testing Framework

### PyTest Implementation

The project includes a comprehensive test suite:

1. **test_wordpress_connector.py**
   - Tests WordPress REST API connectivity
   - Verifies church CRUD operations
   - Tests email functionality

2. **test_chmeetings_connector.py**
   - Tests ChMeetings API authentication
   - Verifies people data retrieval
   - Tests group membership retrieval

3. **test_sync_manager.py**
   - Tests church data synchronization from Excel
   - Tests participant synchronization workflow
   - Verifies roster creation logic

4. **test_validation.py**
   - Tests the validation system against sample data
   - Verifies rule loading from JSON
   - Tests validation logic for different scenarios

### Live/Mock Testing Toggle

The testing framework supports two modes:
- **Mock mode** (default): Uses mock data for fast, repeatable tests — no credentials needed.
- **Live mode**: Tests against actual APIs for integration testing.

A `pytest.ini` in `middleware/` sets `pythonpath = .` so that `import chmeetings`, `import wordpress`, etc. resolve correctly without manually setting `PYTHONPATH`.

#### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LIVE_TEST` | `false` | Enable live API tests |
| `FULL_LIVE_TEST` | `false` | Also run the slow full-participant-sync test |
| `CHM_TEST_GROUP_ID` | _(none)_ | ChMeetings group ID for group membership round-trip |
| `CHM_TEST_PERSON_ID` | _(none)_ | ChMeetings person ID for group membership round-trip |

```bash
# Mock mode (all tests, no credentials)
pytest tests/ -v

# Live mode
set LIVE_TEST=true && pytest tests/ -v -s

# Live mode with full sync + group membership tests
set LIVE_TEST=true && set FULL_LIVE_TEST=true && set CHM_TEST_GROUP_ID=999847 && set CHM_TEST_PERSON_ID=3692903 && pytest tests/ -v -s
```

For detailed testing instructions see [USAGE.md](USAGE.md#running-tests).

## ChMeetings REST API Surface

The ChMeetings API is documented at `https://api.chmeetings.com/scalar`. The published OpenAPI JSON (`/openapi/v1.json`) is **incomplete** — it covers only ~30 paths (groups, families, contributions, events). The Scalar UI exposes a fuller set of endpoints that should be used as the authoritative reference.

### Confirmed Available Endpoints (as of April 2026)

| Tag | Method | Path | Notes |
|---|---|---|---|
| People | GET | `/api/v1/people` | Supports `include_additional_fields=True` |
| People | POST | `/api/v1/people` | Create a new person |
| People | GET | `/api/v1/people/{id}` | Get person by ID |
| People | PUT | `/api/v1/people/{id}` | Update person + custom fields via `additional_fields[]` |
| People | DELETE | `/api/v1/people/{id}` | Delete person |
| People | GET | `/api/v1/people/fields` | Returns all custom field definitions with `field_id`, `field_type`, and option IDs |
| Notes | GET | `/api/v1/people/{id}/notes` | List all notes on a person's profile |
| Notes | POST | `/api/v1/people/{id}/notes` | Write a note to a person's profile |
| Notes | GET | `/api/v1/people/{id}/notes/{note_id}` | Get a specific note |
| Notes | PUT | `/api/v1/people/{id}/notes/{note_id}` | Update a note |
| Notes | DELETE | `/api/v1/people/{id}/notes/{note_id}` | Delete a note |
| Groups | GET | `/api/v1/groups` | List groups |
| Groups | GET | `/api/v1/groups/people` | Get people in groups (pass `group_ids`) |
| Groups | POST | `/api/v1/groups/{id}/memberships` | Add person to group (201=added, 200=already member) |
| Groups | DELETE | `/api/v1/groups/{id}/memberships/{person_id}` | Remove person from group |

### Custom Fields API Notes

The `PUT /api/v1/people/{id}` endpoint accepts an `additional_fields` array of `CustomFieldRequest` objects. The `field_type` discriminator and corresponding reset property differ by type:

| field_type | required_property | Reset value |
|---|---|---|
| `checkbox` | `selected_option_ids` (array) | `[]` |
| `dropdown` | `selected_option_id` (number) | `null` |
| `multiple_choice` | `selected_option_id` (number) | `null` |
| `text` | `value` (string) | `null` |
| `multi_line_text` | `value` (string) | `null` |

**Important:** Field IDs and option IDs are assigned by ChMeetings at creation time and will change if custom fields are deleted and recreated. Always call `GET /api/v1/people/fields` at runtime to discover current IDs dynamically — never hardcode them. See Issue #63 for the current field ID reference table.

---

## Known Operational Prerequisites (Admin Manual Steps)

These are manual admin steps that currently have no automation and must be performed before or alongside the middleware sync pipeline. They are tracked as GitHub Issues for future automation.

### 1. Form Submission → VAY-SM Member Promotion (Issue #62)

**Problem:** When a participant submits the Individual Participant Application Form in ChMeetings, they appear in the Form Submissions list but are **not** automatically added as a Member of the VAY-SM church group. The `sync_participants` command only reads VAY-SM Members, so unpromotied submitters are silently invisible to the middleware.

**Current manual process:**
1. Admin navigates to VAY SM → Forms → Individual Application Form → Submissions
2. Selects new submitters and uses **Bulk Actions → Add People**
3. If the person already exists in the Diocese (another church), the bulk action fails — admin must go to the Diocese root level and add them to VAY-SM manually

**Planned automation:** `sync --type form-submitters` command using email-based detection (ChMeetings sends a notification email per submission to the admin inbox) combined with `add_person_to_group()` API calls. See Issue #62 for full design.

### 2. Annual Season Reset of Custom Fields (Issue #63)

**Problem:** Sports Fest custom profile fields (sport selections, Church Rep verification checklist) remain set from the prior season on returning members' ChMeetings profiles. These stale values corrupt the next season's sync and validation.

**Current manual process:** Admin manually edits each returning member's profile in ChMeetings to clear all Sports Fest and Church Rep Verification fields.

**Planned automation:** `reset-season --year YYYY` command that:
1. Reads 2025 data from `sf_participants` (WordPress)
2. Writes a structured archive note to each person's ChMeetings profile via `POST /api/v1/people/{id}/notes`
3. Clears all Sports Fest and Church Rep Verification custom fields via `PUT /api/v1/people/{id}` with `additional_fields[]`

See Issue #63 for the complete field ID reference table and implementation plan.
