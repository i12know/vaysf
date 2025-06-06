##### Begin of tests/test_sync_manager
# Version: 1.0.5
import os
import json
import pandas as pd
import pytest
from sync.manager import SyncManager
from sync.participants import ParticipantSyncer  # Import for validation
from loguru import logger
from config import Config
from wordpress.frontend_connector import Config as WPConfig
from chmeetings.backend_connector import Config as CHMConfig
from config import (SPORT_TYPE, SPORT_FORMAT, GENDER, RACQUET_SPORTS, SPORT_UNSELECTED,
                   VALIDATION_SEVERITY, FORMAT_MAPPINGS)


@pytest.fixture
def mock_chmeetings_data():
    """Load mock ChMeetings data from JSON file."""
    file_path = os.path.join(os.path.dirname(__file__), "mock_chm_people_data.json")
    with open(file_path, "r") as f:
        return json.load(f)

@pytest.fixture
def sync_manager(mocker):
    """Fixture to create a SyncManager instance, mocking if not live."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    logger.info(f"LIVE_TEST from env: {os.getenv('LIVE_TEST')} -> live_test: {live_test}")
    if not live_test:
        mocker.patch("wordpress.frontend_connector.Config.WP_URL", "https://test.wordpress.com")
        mocker.patch("wordpress.frontend_connector.Config.WP_API_KEY", "test_api_key")
        mocker.patch("chmeetings.backend_connector.Config.CHM_API_URL", "https://test.chmeetings.com/")
        mocker.patch("chmeetings.backend_connector.Config.CHM_API_KEY", "test_api_key")
    manager = SyncManager()
    yield manager
    manager.close()

def test_sync_manager_init(sync_manager):
    """Test SyncManager initialization."""
    assert sync_manager is not None, "SyncManager failed to initialize"
    assert hasattr(sync_manager, "wordpress_connector"), "WordPressConnector attribute missing"
    assert sync_manager.wordpress_connector is not None, "WordPressConnector not initialized"
    assert hasattr(sync_manager, "chm_connector"), "ChMeetingsConnector attribute missing"
    if sync_manager.chm_connector is None:
        pytest.skip("ChMeetingsConnector not initialized (likely missing config)")
    assert hasattr(sync_manager, "church_syncer"), "ChurchSyncer attribute missing"
    assert hasattr(sync_manager, "participant_syncer"), "ParticipantSyncer attribute missing"


def test_sync_churches(sync_manager, tmp_path, mocker):
    """Test syncing churches from Excel to WordPress, mocked or live based on LIVE_TEST."""
    live_test = os.getenv("LIVE_TEST", "false").lower() == "true"

    if live_test:
        # Live mode: Use CHURCH_EXCEL_FILE from config
        assert Config.WP_URL, "WP_URL must be set in .env for live test"
        assert Config.WP_API_KEY, "WP_API_KEY must be set in .env for live test"
        excel_path = str(Config.CHURCH_EXCEL_FILE)
        logger.info(f"Live mode - Using Excel path: {excel_path}")
        assert os.path.exists(excel_path), f"Excel file not found at {excel_path}"
        sample_code = "RPC"  # Adjust based on your Excel data
    else:
        # Mock mode: Create a test Excel file
        test_data = pd.DataFrame([{
            "Church Name": "Excel Test Church",
            "Church Code": "EXT",
            "Pastor Name": "Pastor Excel",
            "Pastor Email": "pastor@excel.org",
            "Pastor Phone Number": "555-555-5557",
            "First Name": "Rep",
            "Last Name": "Excel",
            "Your Email": "rep@excel.org",
            "Your Mobile Phone": "555-555-5558",
            "Your Church's Level of Sports Ministry": "Level 2",
            "Your Birthdate": "1990-01-01",
            "Additional notes": "Test note",
            "Submission Date": "2025-03-15"
        }])
        excel_path = tmp_path / "test_churches.xlsx"
        test_data.to_excel(excel_writer=excel_path, index=False)
        logger.info(f"Mock mode - Created test Excel file at {excel_path}")
        sample_code = "EXT"  # Matches mock data

    # Define expected church data for verification
    expected_church = {
        "EXT": {
            "church_name": "Excel Test Church",
            "church_code": "EXT",
            "pastor_name": "Pastor Excel",
            "pastor_email": "pastor@excel.org",
            "pastor_phone": "555-555-5557",
            "church_rep_name": "Rep Excel",
            "church_rep_email": "rep@excel.org",
            "church_rep_phone": "555-555-5558",
            "sports_ministry_level": 2
        },
        "RPC": {
            "church_name": "Redemption Point Church",  # Adjust based on your real data
            "church_code": "RPC"
            # Add more fields if known from your Excel
        }
    }

    if live_test:
        # Live sync
        result = sync_manager.sync_churches_from_excel(excel_path)
        assert result, f"Live church sync failed for {excel_path}"
    else:
        # Mocked sync
        mock_church = expected_church["EXT"]
        mock_create = mocker.Mock(return_value=mock_church)
        mock_update = mocker.Mock(return_value=mock_church)
        mock_get = mocker.Mock(return_value=mock_church)
        mocker.patch.object(sync_manager.wordpress_connector, "create_church", mock_create)
        mocker.patch.object(sync_manager.wordpress_connector, "update_church_by_code", mock_update)
        mocker.patch.object(sync_manager.wordpress_connector, "get_church_by_code", mock_get)

        result = sync_manager.sync_churches_from_excel(str(excel_path))
        assert result, f"Mocked church sync failed for {excel_path}"

    # Verify results
    total_processed = sync_manager.stats["churches"]["created"] + sync_manager.stats["churches"]["updated"]
    assert total_processed > 0, "No churches were created or updated"
    assert sync_manager.stats["churches"]["errors"] == 0, "Errors occurred during sync"

    # Check a sample church
    church = sync_manager.wordpress_connector.get_church_by_code(sample_code)
    if church:
        mode = "Live" if live_test else "Mocked"
        logger.info(f"{mode} synced church {sample_code}: {church}")
        expected = expected_church.get(sample_code, {})
        assert church["church_name"] == expected["church_name"], f"{mode} church name mismatch for {sample_code}"
        assert church["church_code"] == sample_code, f"{mode} church code mismatch"
    else:
        logger.warning(f"Church {sample_code} not found; check {'Excel data' if live_test else 'mock setup'}")

    logger.info(f"Church sync stats: {sync_manager.stats['churches']}")
    
def test_validate_participant(sync_manager, mocker):
    """Test participant validation logic using ParticipantSyncer with IndividualValidator."""
    # Mock SPORTS_FEST_DATE to match IndividualValidator’s default (July 19, 2025)
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2025-07-19")

    # Create a ParticipantSyncer instance with mocked dependencies
    participant_syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache
    )

    # Valid participant: 25-year-old male, Bible Challenge, with photo and consent
    valid_participant = {
        "chmeetings_id": "1",
        "first_name": "John",
        "last_name": "Doe",
        "gender": "Male",
        "birthdate": "2000-01-01",  # Age 25 on 2025-07-19
        "primary_sport": SPORT_TYPE["BIBLE_CHALLENGE"],
        "secondary_sport": SPORT_UNSELECTED,
        "other_events": SPORT_TYPE["TUG_OF_WAR"],
        "photo_url": "https://dnadoeproject.org/wp-content/uploads/2022/11/JD-183-website-image-id.png",
        "consent_status": True  # Assuming IndividualValidator checks this
    }
    is_valid, issues = participant_syncer.validate_participant(valid_participant)
    assert is_valid, f"Valid participant should pass, but failed with issues: {issues}"
    assert len(issues) == 0, f"Expected no issues for valid participant, got: {issues}"

    # Too old: 35-year-old for default sport
    old_participant = {
        "chmeetings_id": "2",
        "first_name": "Old",
        "last_name": "Timer",
        "gender": "Male",
        "birthdate": "1990-07-19",  # Age 35 on 2025-07-19
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://dnadoeproject.org/wp-content/uploads/2022/11/JD-183-website-image-id.png",
        "consent_status": True
    }
    is_valid, issues = participant_syncer.validate_participant(old_participant)
    assert not is_valid, "35-year-old should fail for default sport (max age < 35)"
    assert any(i["type"] == "age_restriction" and i["rule_code"] == "MAX_AGE_DEFAULT" for i in issues), f"Expected MAX_AGE_DEFAULT age restriction issue, got: {issues}"

    # Too young: 9-year-old for Basketball
    young_participant = {
        "chmeetings_id": "3",
        "first_name": "Young",
        "last_name": "Kid",
        "gender": "Male",
        "birthdate": "2016-01-01",  # Age 9 on 2025-07-19
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://dnadoeproject.org/wp-content/uploads/2022/11/JD-183-website-image-id.png",
        "consent_status": True
    }
    is_valid, issues = participant_syncer.validate_participant(young_participant)
    assert not is_valid, "Underage participant should fail"
    assert any(i["type"] == "age_restriction" and "below minimum age 13" in i["description"] for i in issues), f"Expected age restriction issue, got: {issues}"

    # Gender mismatch: Male in Women’s event
    gender_mismatch = {
        "chmeetings_id": "4",
        "first_name": "Mismatch",
        "last_name": "Player",
        "gender": "Male",
        "birthdate": "2000-01-01",  # Age 25
        "primary_sport": SPORT_TYPE["VOLLEYBALL_WOMEN"],
        "photo_url": "https://dnadoeproject.org/wp-content/uploads/2022/11/JD-183-website-image-id.png",
        "consent_status": True
    }
    is_valid, issues = participant_syncer.validate_participant(gender_mismatch)
    assert not is_valid, "Gender mismatch should fail"
    assert any(i["type"] == "gender_mismatch" for i in issues), f"Expected gender mismatch issue, got: {issues}"

    # Missing photo and consent
    no_photo_consent = {
        "chmeetings_id": "5",
        "first_name": "NoPhoto",
        "last_name": "NoConsent",
        "gender": "Male",
        "birthdate": "2000-01-01",  # Age 25
        "primary_sport": SPORT_TYPE["BIBLE_CHALLENGE"]
        # No photo, no consent_status
    }
    is_valid, issues = participant_syncer.validate_participant(no_photo_consent)
    assert is_valid, "Participant with only warnings should pass"
    assert len(issues) == 2, f"Expected photo and consent warnings, got: {issues}"
    assert any(i["type"] == "missing_photo" for i in issues), "Expected missing photo warning"
    assert any(i["type"] == "missing_consent" for i in issues), "Expected missing consent warning"

def test_sync_participants(sync_manager, mocker, mock_chmeetings_data):
    """Test participant sync to sf_participants and sf_rosters with role filtering and proper validation issue tracking."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"

    # Patch config values
    mocker.patch("sync.participants.Config.TEAM_PREFIX", "Team")
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2025-07-19")

    if not live_test:
        # Mock ChMeetings responses
        mock_groups = [{"id": "1", "name": "Team RPC"}]
        mock_people = [{"person_id": str(person["id"])} for person in mock_chmeetings_data]

        def get_person_side_effect(person_id):
            for person in mock_chmeetings_data:
                if str(person["id"]) == person_id:
                    return person
            return None

        mocker.patch.object(sync_manager.chm_connector, "get_groups", return_value=mock_groups)
        mocker.patch.object(sync_manager.chm_connector, "get_group_people", return_value=mock_people)
        mocker.patch.object(sync_manager.chm_connector, "get_person", side_effect=get_person_side_effect)

        # Mock WordPress responses
        mock_churches = [
            {"church_code": "RPC", "church_id": 1, "pastor_email": "pastor@rpc.org"},
            {"church_code": "ORN", "church_id": 2, "pastor_email": "pastor@orn.org"}
        ]
        created_participants = []
        created_rosters = []
        created_validation_issues = []

        def get_participants_side_effect(params=None):
            if params and "chmeetings_id" in params:
                chm_id = params["chmeetings_id"]
                return [p for p in created_participants if p["chmeetings_id"] == chm_id]
            return created_participants

        def create_participant_side_effect(participant_data):
            participant = {
                "participant_id": len(created_participants) + 1,
                "chmeetings_id": participant_data["chmeetings_id"],
                "updated_at": "2025-03-01 00:00:00",  # Match WordPress expected format
                **participant_data
            }
            created_participants.append(participant)
            return participant

        def update_participant_side_effect(participant_id, participant_data):
            for p in created_participants:
                if p["participant_id"] == participant_id:
                    p.update(participant_data)
                    p["updated_at"] = "2025-03-01 00:00:00"  # Ensure consistent timestamp
                    return p
            return None

        def create_roster_side_effect(roster_data):
            key = (roster_data["sport_type"], roster_data["sport_format"], roster_data["team_order"])
            if key not in [(r["sport_type"], r["sport_format"], r["team_order"]) for r in created_rosters]:
                roster = {"roster_id": len(created_rosters) + 1, **roster_data}
                created_rosters.append(roster)
                return roster
            return None

        def get_rosters_side_effect(params):
            participant_id = params.get("participant_id")
            sport_type = params.get("sport_type")
            sport_format = params.get("sport_format")
            team_order = params.get("team_order")
            filtered_rosters = [r for r in created_rosters if
                               (participant_id is None or r["participant_id"] == participant_id) and
                               (sport_type is None or r["sport_type"] == sport_type) and
                               (sport_format is None or r["sport_format"] == sport_format) and
                               (team_order is None or r["team_order"] == team_order)]
            return filtered_rosters

        def get_validation_issues_side_effect(params):
            participant_id = params.get("participant_id")
            status = params.get("status")
            filtered_issues = [i for i in created_validation_issues if
                              (participant_id is None or i["participant_id"] == participant_id) and
                              (status is None or i["status"] == status)]
            return filtered_issues

        def create_validation_issue_side_effect(issue_data):
            issue = {"issue_id": len(created_validation_issues) + 1, "updated_at": "2025-03-01 00:00:00", **issue_data}
            created_validation_issues.append(issue)
            return issue

        def update_validation_issue_side_effect(issue_id, issue_data):
            for issue in created_validation_issues:
                if issue["issue_id"] == issue_id:
                    issue.update(issue_data)
                    issue["updated_at"] = "2025-03-01 00:00:00"
                    return issue
            return None

        mocker.patch.object(sync_manager.wordpress_connector, "get_churches", return_value=mock_churches)
        mocker.patch.object(sync_manager.wordpress_connector, "get_participants", side_effect=get_participants_side_effect)
        mocker.patch.object(sync_manager.wordpress_connector, "create_participant", side_effect=create_participant_side_effect)
        mocker.patch.object(sync_manager.wordpress_connector, "update_participant", side_effect=update_participant_side_effect)
        mocker.patch.object(sync_manager.wordpress_connector, "get_rosters", side_effect=get_rosters_side_effect)
        mocker.patch.object(sync_manager.wordpress_connector, "create_roster", side_effect=create_roster_side_effect)
        mocker.patch.object(sync_manager.wordpress_connector, "delete_roster", return_value=True)
        mocker.patch.object(sync_manager.wordpress_connector, "get_validation_issues", side_effect=get_validation_issues_side_effect)
        mocker.patch.object(sync_manager.wordpress_connector, "create_validation_issue", side_effect=create_validation_issue_side_effect)
        mocker.patch.object(sync_manager.wordpress_connector, "update_validation_issue", side_effect=update_validation_issue_side_effect)

    # Run first sync
    result = sync_manager.sync_participants()
    assert result, "First sync participants failed"

    # Verify stats after first sync
    if not live_test:
        assert sync_manager.stats["participants"]["created"] == 2, "Expected 2 participants created (Jerry, Khoi), John skipped due to role"
        assert sync_manager.stats["validation_issues"]["created"] > 0, "Should have created validation issues"
        assert sync_manager.stats["rosters"]["created"] == 4, "Expected 4 roster entries (Jerry: 3, Khoi: 1)"

        # Reset stats for second run
        sync_manager.stats["participants"]["created"] = 0
        sync_manager.stats["participants"]["updated"] = 0
        sync_manager.stats["participants"]["errors"] = 0
        sync_manager.stats["rosters"]["created"] = 0
        sync_manager.stats["rosters"]["updated"] = 0
        sync_manager.stats["rosters"]["deleted"] = 0
        sync_manager.stats["rosters"]["errors"] = 0
        sync_manager.stats["validation_issues"]["created"] = 0
        sync_manager.stats["validation_issues"]["updated"] = 0
        sync_manager.stats["validation_issues"]["skipped"] = 0
        sync_manager.stats["validation_issues"]["unchanged"] = 0
        sync_manager.stats["validation_issues"]["resolved"] = 0
        sync_manager.stats["validation_issues"]["errors"] = 0

        # Run second sync
        result = sync_manager.sync_participants()
        assert result, "Second sync participants run failed"

        # Verify stats after second sync
        assert sync_manager.stats["participants"]["created"] == 0, "Should not create duplicate participants"
        assert sync_manager.stats["participants"]["updated"] == 2, "Should update 2 existing participants"
        assert sync_manager.stats["rosters"]["created"] == 0, "Should not create duplicate rosters"
        assert sync_manager.stats["validation_issues"]["created"] == 0, "Should not create duplicate issues"
        total_tracked = (
            sync_manager.stats["validation_issues"]["unchanged"] +
            sync_manager.stats["validation_issues"]["skipped"]
        )
        assert total_tracked > 0, "Should have tracked unchanged/skipped issues on second run"
    else:
        assert sync_manager.stats["participants"]["errors"] == 0, "Errors in live mode"
        assert sync_manager.stats["participants"]["created"] + sync_manager.stats["participants"]["updated"] > 0, "No participants processed in live mode"
        assert sync_manager.stats["validation_issues"]["errors"] == 0, "Validation errors in live mode"
        
def test_participant_by_chmeetings_id(sync_manager, mocker, mock_chmeetings_data):
    """Test retrieving a participant by ChMeetings ID."""
    # Mock SPORTS_FEST_DATE
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2025-07-19")  # Updated path

    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    chmeetings_id = "3505203"  # Jerry Phan from mock data

    if live_test:
        participant = (sync_manager.wordpress_connector.get_participants({"chmeetings_id": chmeetings_id}) or [None])[0]
        if participant:
            logger.info(f"Found live participant by chmeetings_id: {participant['first_name']} {participant['last_name']}")
        assert participant is not None, "Should find participant by chmeetings_id in live test"
    else:
        mock_participant = next((p for p in mock_chmeetings_data if str(p["id"]) == chmeetings_id), None)

        def fake_get(url, params=None, timeout=None):
            if params and params.get("chmeetings_id") == chmeetings_id:
                resp = mocker.Mock(status_code=200)
                resp.headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
                wp_participant = {
                    "participant_id": 1,
                    "chmeetings_id": str(mock_participant["id"]),
                    "first_name": mock_participant["first_name"],
                    "last_name": mock_participant["last_name"],
                    "email": mock_participant["email"],
                    "church_code": "ORN",
                    "church_name": "Orange County Church"
                }
                resp.json.return_value = [wp_participant]
                return resp
            else:
                resp = mocker.Mock(status_code=404)
                resp.headers = {}
                resp.json.return_value = []
                return resp

        mocker.patch.object(sync_manager.wordpress_connector.session, "get", side_effect=fake_get)
        participant = (sync_manager.wordpress_connector.get_participants({"chmeetings_id": chmeetings_id}) or [None])[0]
        assert participant is not None, "Should find participant by chmeetings_id"
        assert participant["first_name"] == "Jerry", "Should return correct participant"
        assert participant["chmeetings_id"] == chmeetings_id, "Should have matching chmeetings_id"

        not_found = (sync_manager.wordpress_connector.get_participants({"chmeetings_id": "999999"}) or [None])[0]
        assert not_found is None, "Should return None for unknown chmeetings_id"
##### End of tests/test_sync_manager