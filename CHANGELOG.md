# CHANGELOG

## Version 1.0 (RC - Release Candidate)
*Released: 2025-03-28

- Consolidated full system architecture into final implementation
- Enhanced validation system with JSON rules and multi-level severity
- Added comprehensive middleware components
- Refined the roster validation process
- Added detailed error handling and recovery mechanisms
- Finalized WordPress plugin structure and REST API endpoints
- Completed middleware implementation with full validation support
- Enhanced documentation with implementation details

## Version 0.9
*Released: 2025-03-26

- Enhanced validation system with JSON rules for configurability
- Added multi-level validation approach (individual, team, church, tournament)
- Refined validation severity handling (ERROR, WARNING, INFO)
- Improved validation issue tracking and resolution workflow
- Added support for rule-based validation using Pydantic models
- Enhanced error reporting with contextual details

## Version 0.8
*Released: 2025-03-21

- Added Pydantic framework for improving validation logic & testing
- Enhanced sync_churches and sync_participants with better model validation
- Implemented basic roster reporting functionality
- Improved data mapping between ChMeetings and WordPress
- Added support for rule-based validation
- Enhanced ChMeetingsConnector with more robust error handling

## Version 0.7
*Released: 2025-03-17

- Added sf_rosters table for tracking team composition
- Enhanced sync_participants to create/update sf_rosters entries
- Added support for team-level validations through roster data
- Implemented participant syncing with sport preferences
- Added detailed ChMeetings usage documentation
- Extended sync_participants to work with the new roster structure

## Version 0.6
*Released: 2025-03-15

- Added PyTest framework for automated testing
- Implemented mocking convention for isolated connector testing
- Added detailed testing documentation
- Added support for live/mock testing toggle via LIVE_TEST env variable
- Improved error handling in WordPress and ChMeetings connectors
- Enhanced sync error recovery

## Version 0.5
*Released: 2025-03-14

- Changed architecture to use church_code (3-letter code) as a human-readable identifier
- Maintained church_id as the database primary key for technical efficiency
- Updated API endpoints to use church_code for improved readability
- Clarified the hybrid identifier approach throughout the system
- Updated data mapping to incorporate church_code
- Improved church identification throughout the system

## Version 0.4
*Released: 2025-03-13

- Moved email notifications from Python middleware to WordPress
- Shifted token generation to WordPress for better process flow
- Added sf_email_log table for tracking communications
- Implemented WP Mail SMTP plugin for reliable email delivery
- Improved approval workflow through WordPress
- Enhanced security of approval process

## Version 0.3
*Released: 2025-03-12

- Added detailed Windows environment setup instructions
- Included code examples for all major components
- Added comprehensive database schema definitions
- Created a more granular development roadmap
- Added detailed implementation phases
- Enhanced system architecture documentation
- Added Windows-specific considerations

## Version 0.2
*Released: 2025-03-11

- Simplified the database schema from 11 to 8 tables
- Added detailed data mappings based on actual CSV structure
- Enhanced the approval process workflow
- Refined validation rules based on the Sports Fest Handbook
- Added church and participant data mapping details
- Improved implementation phases and milestones
- Added exact field mappings from ChMeetings to WordPress

## Version 0.1
*Released: 2025-03-10

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
