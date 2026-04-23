# CHANGELOG

## Version 1.08 (2026-04-23)

### Bug Fixes
- Fixed [#61](https://github.com/i12know/vaysf/issues/61): `get_approvals(synced_to_chmeetings=False)` returned 0 records because the WordPress REST API silently drops unregistered query parameters
  - WordPress plugin: added `args` array to the `/approvals` READABLE route in `plugins/vaysf/includes/rest-api.php` declaring `participant_id`, `church_id`, `approval_status`, and `synced_to_chmeetings` (type boolean) so WordPress sanitizes and forwards them to the callback
  - Middleware: `get_approvals()` in `wordpress/frontend_connector.py` now coerces Python bools to 0/1 before URL-encoding — avoids the `"False"` → PHP `true` string-cast pitfall
  - Added `test_get_approvals_coerces_bool_params` mock test asserting `synced_to_chmeetings=False` serializes as `0` in the outgoing request
  - Rebuilt `plugins/vaysf.zip`

### Housekeeping
- Closed [#54](https://github.com/i12know/vaysf/issues/54) and [#55](https://github.com/i12know/vaysf/issues/55): Soccer - Coed Exhibition was implemented as an Other Events checkbox (already shipped as option_id 329599 in `SF_OTHER_EVENTS_OPTIONS` in v1.07). The full "Exhibition event type" feature (EXHIBITION category, `event_type` column on `sf_rosters`, separate fees, admin UI distinction) was deferred as YAGNI — current structural shape already gives Soccer the right behavior end-to-end
  - Added a comment in `middleware/validation/team_validator.py` locking in the intent that `("primary_sport", "secondary_sport")` deliberately excludes `other_events` so exhibition entries bypass the non-member team limit
  - Added `test_sync_rosters_soccer_coed_exhibition` regression test pinning the comma-split path

## Version 1.07 (2026-04-23)

### New Features
- Implemented [#53](https://github.com/i12know/vaysf/issues/53): `TeamValidator` — team-composition rules moved from hardcoded Python into `summer_2026.json`
  - New `middleware/validation/team_validator.py`: reads `max_non_members` limits from JSON, validates non-church-member counts per team sport and per doubles pair using `SPORT_BY_CATEGORY` full sport names and `FORMAT_MAPPINGS` for doubles detection
  - New `middleware/validation/summer_2026.json`: all 11 individual rules from `Summer_2025.json` (updated to `SUMMER_2026` collection) plus 3 new TEAM-level rules: `MAX_NON_MEMBERS_TEAM` (2), `MAX_NON_MEMBERS_DOUBLES` (1), `MAX_EVENTS_PER_PARTICIPANT` (2, defined only — form-enforced)
  - Default collection switches globally to `SUMMER_2026` in `IndividualValidator`, `SyncManager`, and `ParticipantSyncer`
  - Removed `get_validation_rules()` from `SyncManager`; `validate_data()` now delegates to `TeamValidator`
  - Fixed pre-existing bug: old `validate_data()` used abbreviated sport names (`"Basketball"`) that never matched real ChMeetings data (`"Basketball - Men Team"`), causing team checks to silently no-op

### Bug Fixes
- Fixed [#65](https://github.com/i12know/vaysf/issues/65): `NameError: name 'pd' is not defined` in `_sync_approvals_via_excel()` — `import pandas as pd` was missing from `sync/manager.py`
- Fixed `sync_approvals_to_chmeetings()` group-not-found path: now returns `False` with a clear error message instead of falling through to the Excel export path
- Fixed `get_member_fields()` in `ChMeetingsConnector` to handle the new API response format `{"status_code":200, "data": {"sections": [...]}}` — fields are now correctly flattened from all sections
- Fixed `get_people()` pagination: termination check changed from `page * page_size >= total` to `len(all_people) >= total`, preventing early exit when the response page_size differs from the requested page_size

### Tests & Infrastructure
- Added 8 new `TeamValidator` unit tests in `tests/test_validation.py` covering team limits, doubles limits, member exclusion, cross-sport isolation, and secondary sport counting
- Fixed 3 live test failures: `test_get_member_fields` (sections format), `test_add_member_note` and `test_update_person` now discover a valid live person ID when the hardcoded test ID is no longer in ChMeetings
- Fixed 3 pre-existing mock test failures caused by Python bound-method calling convention on Linux: `capturing_get` and `fake_put` mock signatures updated to `*args, **kwargs`

## Version 1.06 (2026-04-12)

Replaced Excel export workarounds with direct ChMeetings API calls (Issue #60):
- Rewrote [#60](https://github.com/i12know/vaysf/issues/60): `group_assignment.py` now calls `add_person_to_group()` directly — no more `chm_group_import.xlsx` or manual ChMeetings import step
- Added `--dry-run` flag to `assign-groups` CLI command (previews who would be assigned, writes audit xlsx, zero API calls)
- `church_team_assignments.xlsx` audit file is still written every run (both live and dry-run) as a record
- Rewrote `sync_approvals_to_chmeetings()` in `sync/manager.py` to use `add_person_to_group()` instead of Excel; fails hard if `APPROVED_GROUP_NAME` group not found in ChMeetings
- `synced_to_chmeetings=True` is now set per-person based on API success (not xlsx write success)
- Removed `import pandas as pd` from `sync/manager.py` (no longer used there)
- Added 429 rate-limit retry with 2/5/10 s back-off to `add_person_to_group()` in the ChMeetings connector
- Added preventive 200 ms delay between API calls in both `sync_approvals_to_chmeetings()` and `assign_people_to_church_team_groups()` to stay under the ChMeetings rate limit
- Added `PermissionError` handling when audit xlsx is open in Excel on Windows
- Added 7 new mock tests in `tests/test_group_assignment.py`
- Added 3 new mock tests for `sync_approvals_to_chmeetings()` in `tests/test_sync_manager.py`
- Opened [#61](https://github.com/i12know/vaysf/issues/61): `get_approvals()` `synced_to_chmeetings` filter not working in WordPress REST API

## Version 1.05 (2026-04-11) — 2026 ChMeetings API Upgrade

### Breaking Changes
- Removed Selenium support entirely — the middleware now uses only the ChMeetings API for all operations
- Removed `CHM_USERNAME`, `CHM_PASSWORD`, `CHROME_DRIVER_PATH`, `USE_CHROME_HEADLESS`, and `CHROME_PROFILE_DIR` from configuration
- Removed `selenium` and `webdriver-manager` from dependencies
- `ChMeetingsConnector` no longer accepts `use_selenium` parameter

### New Features
- **API-based approval sync**: `sync --type approvals` now uses the ChMeetings `add_person_to_group()` API to add approved participants directly to their designated group, eliminating the manual Excel import step
- **Excel fallback for approvals**: Pass `--excel-fallback` to `sync --type approvals` to use the legacy Excel export workflow when needed
- **Field mapping constants** (`CHM_FIELDS`): All ChMeetings custom field names are now centralized in `config.py` instead of being hardcoded across the codebase, making it easy to update if ChMeetings labels change
- **API field inspector**: New `test --system chmeetings --test-type api-inspect` command retrieves custom field definitions from ChMeetings and cross-references them against `CHM_FIELDS` to detect mismatches
- **New API methods**: `ChMeetingsConnector` now exposes `get_fields()`, `add_person_to_group(group_id, person_id)`, and `remove_person_from_group(group_id, person_id)`

### Bug Fixes
- Fixed [#57](https://github.com/i12know/vaysf/issues/57): Auth header casing — `ApiKey` → `apikey` for strict gateway compatibility
- Fixed [#56](https://github.com/i12know/vaysf/issues/56): `get_person()` now correctly unwraps the `{"data": {...}}` response envelope
- Fixed [#58](https://github.com/i12know/vaysf/issues/58): `get_people()` pagination now uses `total_count` for robust termination; respects caller's `page_size`; sends `include_additional_fields=True` and `include_family_members=False`

### Tests & Infrastructure
- Added [#59](https://github.com/i12know/vaysf/issues/59): `add_person_to_group()` and `remove_person_from_group()` API methods with live round-trip test gate (`CHM_TEST_GROUP_ID` / `CHM_TEST_PERSON_ID` env vars)
- Added `test_get_people_pagination` and `test_get_people_request_params` tests
- Added `middleware/pytest.ini` to fix `ModuleNotFoundError` when running `pytest` from the `middleware/` directory
- Added `FULL_LIVE_TEST` env var gate to skip the long-running full-sync test in standard `LIVE_TEST=true` mode

### Documentation
- Updated ARCHITECTURE.md, INSTALLATION.md, TROUBLESHOOTING.md, USAGE.md, and README.md to reflect all changes
- Removed all Selenium references from documentation
- Created `docs/CHMEETINGS_API_MIGRATION.md` documenting all API migration changes

## Version 1.04 (2025-07-17)
- Fixed issue [#42](https://github.com/i12know/vaysf/issues/42): Resend approval email now generates fresh tokens with proper expiry dates instead of using expired tokens
- Added: "Is_Member_ChM" and "Photo" columns to Roster tab in church team reports; Photo column displays images using IMAGE() formula (use Excel Ctrl+H to replace "=@IMAGE" with "=IMAGE" if needed)
- Added: "Total Denied" column in Summary tab
- Added: options to mass pastor approval email sending at export rosters time for issue [#47](https://github.com/i12know/vaysf/issues/47)
- Fixed: plugin's admin Sports Fest Date display issue [#48](https://github.com/i12know/vaysf/issues/48)
- Added: Auto Filter to all columns and a note about Photo formula
- FIXED: Male athelete signed up for Women Volleyball now will be Smart Gender Map to the right team in Roster as issue [#50](https://github.com/i12know/vaysf/issues/50)

## Version 1.03 (2025-05-24)
- Fixed issue [#32](https://github.com/i12know/vaysf/issues/32): Not everyone from NHC church show up on Pastoral Approval emails. (pagination fix)
- Fixed issue [#33](https://github.com/i12know/vaysf/issues/33): Non church member show up on Pastoral Approval email as "Yes" for church membership
- Added: Command for "main.py sync --type approvals --chm-id Specific ID" for sync approvals command

## Version 1.02 (2025-05-15)
- Fixed: issue [#23](https://github.com/i12know/vaysf/issues/23) Partner name didn't get recorded on sf_roster table
- Fixed: Enhanced partner name handling in `_create_or_update_roster` to properly update existing entries
- Fixed: Consent-severity calculation and checklist refresh for minors [#12](https://github.com/i12know/vaysf/issues/12), [#9](https://github.com/i12know/vaysf/issues/9)
- Added: Command for "main.py sync --type participants --chm-id 3139537": sync just one participant by ID to debug issues faster
- Added: Command for "main.py export-church-teams": Generate Excel files for Church Rep's review (use arg --church-code ABC for a church)
- Added: Improved debug logging for roster operations and validation issues
- Updated: Documentation to reflect new commands and fixed issues

## Version 1.01
- Fixed: Minor's record didn't show up for Pastoral Approval because ERROR in consent didn't get updated [#12](https://github.com/i12know/vaysf/issues/12)
- Fixed: issue [#4](https://github.com/i12know/vaysf/issues/4) Approved athletes doesn't show approval_status correctly.
- Added: main.py command "assign-groups": Create group assignments for people with church codes

## Version 1.00
*Released: 2025-03-28*

- Consolidated full system architecture into final implementation
- Enhanced validation system with JSON rules and multi-level severity
- Added comprehensive middleware components
- Refined the roster validation process
- Added detailed error handling and recovery mechanisms
- Finalized WordPress plugin structure and REST API endpoints
- Completed middleware implementation with full validation support
- Enhanced documentation with implementation details

## Version 0.9
*Released: 2025-03-26*

- Enhanced validation system with JSON rules for configurability
- Added multi-level validation approach (individual, team, church, tournament)
- Refined validation severity handling (ERROR, WARNING, INFO)
- Improved validation issue tracking and resolution workflow
- Added support for rule-based validation using Pydantic models
- Enhanced error reporting with contextual details

## Version 0.8
*Released: 2025-03-21*

- Added Pydantic framework for improving validation logic & testing
- Enhanced sync_churches and sync_participants with better model validation
- Implemented basic roster reporting functionality
- Improved data mapping between ChMeetings and WordPress
- Added support for rule-based validation
- Enhanced ChMeetingsConnector with more robust error handling

## Version 0.7
*Released: 2025-03-17*

- Added sf_rosters table for tracking team composition
- Enhanced sync_participants to create/update sf_rosters entries
- Added support for team-level validations through roster data
- Implemented participant syncing with sport preferences
- Added detailed ChMeetings usage documentation
- Extended sync_participants to work with the new roster structure

## Version 0.6
*Released: 2025-03-15*

- Added PyTest framework for automated testing
- Implemented mocking convention for isolated connector testing
- Added detailed testing documentation
- Added support for live/mock testing toggle via LIVE_TEST env variable
- Improved error handling in WordPress and ChMeetings connectors
- Enhanced sync error recovery

## Version 0.5
*Released: 2025-03-14*

- Changed architecture to use church_code (3-letter code) as a human-readable identifier
- Maintained church_id as the database primary key for technical efficiency
- Updated API endpoints to use church_code for improved readability
- Clarified the hybrid identifier approach throughout the system
- Updated data mapping to incorporate church_code
- Improved church identification throughout the system

## Version 0.4
*Released: 2025-03-13*

- Moved email notifications from Python middleware to WordPress
- Shifted token generation to WordPress for better process flow
- Added sf_email_log table for tracking communications
- Implemented WP Mail SMTP plugin for reliable email delivery
- Improved approval workflow through WordPress
- Enhanced security of approval process

## Version 0.3
*Released: 2025-03-12*

- Added detailed Windows environment setup instructions
- Included code examples for all major components
- Added comprehensive database schema definitions
- Created a more granular development roadmap
- Added detailed implementation phases
- Enhanced system architecture documentation
- Added Windows-specific considerations

## Version 0.2
*Released: 2025-03-11*

- Simplified the database schema from 11 to 8 tables
- Added detailed data mappings based on actual CSV structure
- Enhanced the approval process workflow
- Refined validation rules based on the Sports Fest Handbook
- Added church and participant data mapping details
- Improved implementation phases and milestones
- Added exact field mappings from ChMeetings to WordPress

## Version 0.1
*Released: 2025-03-10*

- Initial plan with three-tier architecture
- Defined 11 custom WordPress tables
- Outlined core workflows:
  - Registration and approval
  - Data validation
  - Schedule management
- Created initial system architecture
- Defined basic components for ChMeetings, middleware, and WordPress
- Outlined security considerations
- Added future enhancement proposals