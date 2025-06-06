# Sports Fest 2025 ChMeetings Integration

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
- Excel report generation for church team status
- Group assignment creation for ChMeetings integration

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
   - Windows 10/11 with Python 3.8+
   - ChMeetings account
   - WordPress site with the VAYSF plugin installed

2. **Installation**

```bash
# Clone the repository
git clone https://github.com/i12know/vaysf.git

# Install dependencies
cd vaysf
pip install -r requirements.txt

# Copy .env.template to .env and edit with your credentials
cp .env.template .env
```

3. **Basic Usage**

```bash
# Run a full sync
python main.py sync --type full

# Sync churches from Excel
python main.py sync-churches --file "data/Church Application Form.xlsx"

# Generate approval tokens
python main.py sync --type approvals

# Sync a specific participant by ChMeetings ID (for debugging)
python main.py sync --type participants --chm-id <CHMEETINGS_ID>

# Export Excel reports for all church teams
python main.py export-church-teams

# Export Excel reports for a specific church
python main.py export-church-teams --church-code ABC
```

For detailed setup and usage instructions, see the [Installation Guide](docs/INSTALLATION.md) and [Usage Guide](docs/USAGE.md).

## Documentation

- [Installation Guide](docs/INSTALLATION.md)
- [Architecture Overview](ARCHITECTURE.md)
- [Usage Guide](docs/USAGE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Contributing](CONTRIBUTING.md)

## Project Status

The system has been thoroughly tested and is ready for production use for Sports Fest 2025. All core functionality is fully implemented and tested, including recent improvements:

- Church synchronization from Excel to WordPress
- Participant synchronization from ChMeetings to WordPress
- Validation system with JSON rules
- Pastor approval workflow
- WordPress admin interface
- Enhanced reporting capabilities for church representatives

The functionality covers the complete operational workflow from registration to participation, with robust error handling and recovery mechanisms. Recent updates in v1.01 and v1.02 have improved system reliability and added valuable debugging and reporting tools.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Vietnamese Alliance Youth (VAY) Sports Ministry
- Vietnamese District of the Christian and Missionary Alliance (CMA)
- All church representatives and volunteers

## Contact

For support or questions, contact:
- Bumble on the VAY Sports Ministry Team - https://vaysm.org
