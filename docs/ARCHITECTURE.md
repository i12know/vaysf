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
                                      | API/Selenium
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
│   └── backend_connector.py    # API and Selenium connector
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
    def get_people(self, params=None)
    def get_person(self, person_id)
    def get_groups(self, params=None)
    def get_group_people(self, group_id)
```

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
    def sync_approvals_to_chmeetings(self)
    def validate_data(self)
    def run_full_sync(self)
```

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
    --type TYPE          Type of data to sync (churches, participants, 
                         approvals, validation, full)
    --chm-id ID          ChMeetings ID for syncing a specific participant
  
  sync-churches          Sync churches from Excel file
    --file FILE          Path to the church Excel file
  
  export-church-teams    Generate Excel reports for church teams
    --church-code CODE   Generate report for specific church
    --output DIR         Output directory for reports
  
  assign-groups          Create group assignments for people with church codes
  
  config                 Configure system settings
    --validate           Validate current configuration
  
  schedule               Run scheduled sync jobs
    --interval MINUTES   Interval in minutes between sync jobs
    --daemon             Run as daemon process
  
  test                   Test connectivity and functionality
    --system SYSTEM      System to test (chmeetings, wordpress, all)
    --test-type TYPE     Type of test to run (connectivity, churches, email, all)
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
- **Mock mode** (default): Uses mock data for fast, repeatable tests
- **Live mode**: Tests against actual APIs for integration testing

Toggle between modes using the LIVE_TEST environment variable:
```bash
# Mock mode
pytest tests/test_wordpress_connector.py -v -s

# Live mode 
set LIVE_TEST=true && pytest tests/test_wordpress_connector.py -v -s
```