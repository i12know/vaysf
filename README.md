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

```bash
# Clone the repository
git clone https://github.com/i12know/vaysf.git

# Install dependencies (all middleware code lives under middleware/)
cd vaysf\middleware
pip install -r requirements.txt

# Copy .env.template to .env and edit with your credentials
copy .env.template .env
```

3. **Running Tests**

```bash
# From the middleware/ directory — mock mode (no credentials needed)
pytest tests/ -v

# Live mode (requires .env with real API keys)
set LIVE_TEST=true && pytest tests/ -v -s
```

See [USAGE.md](docs/USAGE.md#running-tests) for full testing options including live group membership tests.

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
```

For detailed setup and usage instructions, see the [Installation Guide](docs/INSTALLATION.md) and [Usage Guide](docs/USAGE.md).

## Documentation

- [Installation Guide](docs/INSTALLATION.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Usage Guide](docs/USAGE.md)
- [Season Transition Guide](docs/SEASON_TRANSITION.md)
- [ChMeetings API Migration](docs/CHMEETINGS_API_MIGRATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Contributing](docs/CONTRIBUTING.md)

## Project Status

The system is actively maintained and ready for production use for Sports Fest 2026. All core functionality is fully implemented and tested, including recent improvements:

- Church synchronization from Excel to WordPress
- Participant synchronization from ChMeetings to WordPress (v1.05: robust pagination via `total_count`)
- Validation system with JSON rules
- Pastor approval workflow
- WordPress admin interface
- Enhanced reporting capabilities for church representatives
- API-based approval sync (v1.05) — eliminates manual Excel import to ChMeetings
- Direct ChMeetings group membership management via API (v1.05/v1.06)
- Centralized field mapping and API field inspector (v1.05)

The functionality covers the complete operational workflow from registration to participation, with robust error handling and recovery mechanisms. The v1.05/v1.06 releases modernize the ChMeetings integration by removing Selenium in favor of a pure API approach, add tools for easier field mapping maintenance, and eliminate all manual Excel import steps.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Vietnamese Alliance Youth (VAY) Sports Ministry
- Vietnamese District of the Christian and Missionary Alliance (CMA)
- All church representatives and volunteers

## Contact

For support or questions, contact:
- Bumble on the VAY Sports Ministry Team - https://vaysm.org
