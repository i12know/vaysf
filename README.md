# Sports Fest 2026 ChMeetings Integration

## Overview

The Sports Fest ChMeetings Integration is a comprehensive system for managing the Vietnamese Alliance Youth (VAY) Sports Festival participant registration, validation, and approval. It bridges ChMeetings (for registration and profile management) with WordPress (for operations) using a Windows-based Python middleware.

### Key Features

- Complete registration management through ChMeetings
- Pastor approval workflow via WordPress/email
- Sophisticated validation system with JSON-based rules
- Team and roster management
- Participant eligibility verification
- Admin dashboard for tournament management
- Targeted participant syncing for debugging (by ChMeetings ID)
- Excel report generation for church team status, including open validation issues and partner-name hints
- Group assignment creation for ChMeetings integration
- API-based approval sync to ChMeetings groups (with Excel fallback)
- Centralized field mapping configuration (`CHM_FIELDS`) for easy maintenance
- API field inspector to detect ChMeetings field name changes
- Game scheduling pipeline: roster export → `schedule_input.json` → OR-Tools CP-SAT solver → Excel timetable workbooks (see [docs/SCHEDULING.md](docs/SCHEDULING.md))
- Athlete badge generation with a public WordPress badge gallery (`[vaysf_badges]`)
- Score-sheet generation, including the Bible Challenge verse bank and a scoped WordPress Bible Verse editor
- Proof-of-insurance upload workflow with token-protected church-rep links
- Season reset tooling for year-over-year transitions

## System Architecture

The system uses a three-tier architecture:

1. **ChMeetings (Core Data & Registration)**
   - Participant registration and profile management
   - Church registration
   - Team and group management
   - Payment processing

2. **Windows-based Python Middleware**
   - Data synchronization between systems
   - JSON-based validation with Pydantic models
   - Comprehensive error handling and logging

3. **WordPress on Bluehost (Operations)**
   - Custom plugin with REST API
   - Pastor approval processing
   - Admin interface
   - Roster management
   - Validation issue tracking

## Quick Start

1. **Prerequisites**
   - Windows 10/11 with Python 3.10+
   - ChMeetings account with API key
   - WordPress site with the VAYSF plugin installed

2. **Installation**

```bat
# Clone the repository
git clone https://github.com/i12know/vaysf.git

# Install dependencies (all middleware code lives under middleware/)
cd vaysf\middleware
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt

# Copy .env.template to .env and edit with your credentials
copy .env.template .env
```

3. **Running Tests**

```bat
# From the middleware/ directory - mock mode (no credentials needed)
.\.venv\Scripts\python.exe -m pytest tests\ -v

# Live mode against real systems (write tests skipped)
set LIVE_TEST=true && .\.venv\Scripts\python.exe -m pytest tests\ -v -s

# Real write tests (only when you intentionally want live mutations)
set LIVE_TEST=true && set LIVE_MUTATION_TESTS=true && .\.venv\Scripts\python.exe -m pytest tests\ -v -s
```

See [USAGE.md](docs/USAGE.md#running-tests) for full testing options including live group membership tests.

Important: `LIVE_TEST=true` points pytest at real ChMeetings and WordPress systems. Tests that write data are skipped unless you also set `LIVE_MUTATION_TESTS=true`.

4. **Basic Usage**

```bash
# Run a full sync
python main.py sync --type full

# Sync churches from Excel
python main.py sync-churches --file "data/Church Application Form.xlsx"

# Sync approvals to ChMeetings (API-based)
python main.py sync --type approvals

# Sync approvals using legacy Excel export
python main.py sync --type approvals --excel-fallback

# Sync a specific participant by ChMeetings ID (for debugging)
python main.py sync --type participants --chm-id <CHMEETINGS_ID>

# Recalculate TEAM-level validation issues from current WordPress participant data
python main.py sync --type validation

# Export Excel reports for all church teams
python main.py export-church-teams

# Export Excel reports for a specific church
python main.py export-church-teams --church-code ABC

# Scheduling pipeline (see docs/SCHEDULING.md for the full workflow)
python main.py build-schedule-workbook
python main.py solve-schedule
python main.py produce-schedule

# Generate athlete badges and score sheets
python main.py generate-badges
python main.py generate-scoresheets
```

`main.py` exposes many more subcommands (group assignment, pool assignment, schedule publishing, consent checks, season reset, and more) — run `python main.py --help` or see the [Usage Guide](docs/USAGE.md) for the complete reference.

For detailed setup and usage instructions, see the [Installation Guide](docs/INSTALLATION.md) and [Usage Guide](docs/USAGE.md).

## Documentation

- [Chatable DeepWiki](https://deepwiki.com/i12know/vaysf) powerered by [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/i12know/vaysf)
- [Installation Guide](docs/INSTALLATION.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Usage Guide](docs/USAGE.md)
- [Scheduling Pipeline](docs/SCHEDULING.md) and [Schedule How-To](docs/SCHEDULE-HOW-TO.md)
- [Season Transition Guide](docs/SEASON_TRANSITION.md)
- [ChMeetings API Migration](docs/CHMEETINGS_API_MIGRATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Contributing](docs/CONTRIBUTING.md)
- [2026 Architecture Review](docs/ARCHITECTURE_REVIEW_2026.md)

## Project Status

The system is actively maintained and in production for Sports Fest 2026. Current release: **v1.12** (2026-07-18), with WordPress plugin **1.0.46** — see [CHANGELOG.md](CHANGELOG.md) for the full history. All core functionality is implemented and tested (889 tests in mock mode):

- Church synchronization from Excel to WordPress
- Participant synchronization from ChMeetings to WordPress with robust `total_count` pagination
- Validation system with JSON rules
- Pastor approval workflow and API-based approval sync to ChMeetings groups
- WordPress admin interface, public church/badge shortcodes, and REST API
- Game scheduling via OR-Tools CP-SAT with Excel timetable workbooks (v1.10–v1.12)
- Athlete badges, score sheets, and the Bible Challenge verse bank (v1.12)
- Proof-of-insurance upload workflow (v1.12)
- Centralized field mapping (`CHM_FIELDS`) and API field inspector

The integration is API-first: the v1.05/v1.06 releases removed Selenium in favor of pure ChMeetings API calls and eliminated manual Excel import steps, and later releases have kept that principle. The one sanctioned exception is a diagnostic-only Playwright helper for exporting ChMeetings form spreadsheets (`middleware/chrome_export_vaysf_forms.py`); production sync paths never use browser automation.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Vietnamese Alliance Youth (VAY) Sports Ministry
- Vietnamese District of the Christian and Missionary Alliance (CMA)
- All church representatives and volunteers

## Contact

For support or questions, contact:
- Bumble on the VAY Sports Ministry Team - https://vaysm.org
