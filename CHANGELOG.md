# CHANGELOG

## Version 1.04 (2025-07-16)
- Fixed issue [#42](https://github.com/i12know/vaysf/issues/42): Resend approval email now generates fresh tokens with proper expiry dates instead of using expired tokens
- Added: "Is_Member_ChM" and "Photo" columns to Roster tab in church team reports; Photo column displays images using IMAGE() formula (use Excel Ctrl+H to replace "=@IMAGE" with "=IMAGE" if needed)
- Added: "Total Denied" column in Summary tab
- Added: options to mass pastor approval email sending at export rosters time for issue [#47](https://github.com/i12know/vaysf/issues/47)

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