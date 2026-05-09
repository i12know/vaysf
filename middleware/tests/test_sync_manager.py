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
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")

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
        "birthdate": "2000-01-01",  # Age 26 on 2026-07-18
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
        "birthdate": "1991-07-18",  # Age 35 on 2026-07-18
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
        "birthdate": "2017-01-01",  # Age 9 on 2026-07-18
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
    full_live_test = os.getenv("FULL_LIVE_TEST", "false").strip().lower() == "true"
    if live_test and not full_live_test:
        pytest.skip("Full participant sync skipped in standard LIVE_TEST mode — set FULL_LIVE_TEST=true to run")

    # Patch config values
    mocker.patch("sync.participants.Config.TEAM_PREFIX", "Team")
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")

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
            sync_manager.wordpress_connector.last_get_rosters_status = "ok"
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
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")  # Updated path

    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    chmeetings_id = "3505203"  # Jerry Phan from mock data

    if live_test:
        # Discover a real participant from WordPress rather than assuming a hardcoded ID exists
        all_participants = sync_manager.wordpress_connector.get_participants()
        if not all_participants:
            pytest.skip("No participants synced to WordPress yet — run a full sync first (FULL_LIVE_TEST=true)")
        first = all_participants[0]
        chmeetings_id = str(first["chmeetings_id"])
        logger.info(f"Using live chmeetings_id: {chmeetings_id} ({first.get('first_name')} {first.get('last_name')})")
        participant = (sync_manager.wordpress_connector.get_participants({"chmeetings_id": chmeetings_id}) or [None])[0]
        if participant:
            logger.info(f"Found live participant by chmeetings_id: {participant['first_name']} {participant['last_name']}")
        assert participant is not None, "Should find participant by chmeetings_id in live test"
    else:
        mock_response = mocker.Mock(status_code=200)
        mock_response.headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        mock_participant = next((p for p in mock_chmeetings_data if str(p["id"]) == chmeetings_id), None)
        wp_participant = {
            "participant_id": 1,
            "chmeetings_id": str(mock_participant["id"]),
            "first_name": mock_participant["first_name"],
            "last_name": mock_participant["last_name"],
            "email": mock_participant["email"],
            "church_code": "ORN",  # Adjusted to match mock data
            "church_name": "Orange County Church"
        }
        mock_response.json.return_value = [wp_participant]
        empty_response = mocker.Mock(status_code=200)
        empty_response.headers = {'X-WP-Total': '0', 'X-WP-TotalPages': '0'}
        empty_response.json.return_value = []

        def _mock_get(url, **kwargs):
            if kwargs.get("params", {}).get("chmeetings_id") == chmeetings_id:
                return mock_response
            return empty_response

        mocker.patch.object(sync_manager.wordpress_connector.session, "get", side_effect=_mock_get)
        participant = (sync_manager.wordpress_connector.get_participants({"chmeetings_id": chmeetings_id}) or [None])[0]
        assert participant is not None, "Should find participant by chmeetings_id"
        assert participant["first_name"] == "Jerry", "Should return correct participant"
        assert participant["chmeetings_id"] == chmeetings_id, "Should have matching chmeetings_id"

        # Mock empty response for unknown chmeetings_id
        mock_empty_response = mocker.Mock(status_code=200)
        mock_empty_response.headers = {'X-WP-Total': '0', 'X-WP-TotalPages': '0'}
        mock_empty_response.json.return_value = []
        mocker.patch.object(sync_manager.wordpress_connector.session, "get", return_value=mock_empty_response)
        not_found = (sync_manager.wordpress_connector.get_participants({"chmeetings_id": "999999"}) or [None])[0]
        assert not_found is None, "Should return None for unknown chmeetings_id"

def test_validate_data_pagination(sync_manager, mocker):
    """validate_data() must fetch ALL participants across pages, not just the first page.
    Runs in both mock and live mode — all external calls are patched by this test itself."""

    # Page 1 returns a full page of 100 → loop must request page 2
    page1 = [
        {"participant_id": i, "church_id": 1, "is_church_member": True,
         "primary_sport": "", "primary_format": "",
         "secondary_sport": "", "secondary_format": ""}
        for i in range(1, 101)
    ]
    # Page 2 returns 5 items → signals last page (< per_page)
    page2 = [
        {"participant_id": i, "church_id": 1, "is_church_member": True,
         "primary_sport": "", "primary_format": "",
         "secondary_sport": "", "secondary_format": ""}
        for i in range(101, 106)
    ]

    call_count = {"n": 0}

    def paged_get_participants(params=None):
        call_count["n"] += 1
        page = (params or {}).get("page", 1)
        return page1 if page == 1 else page2

    mocker.patch.object(sync_manager.wordpress_connector, "get_participants",
                        side_effect=paged_get_participants)
    mocker.patch.object(sync_manager.wordpress_connector, "get_validation_issues",
                        return_value=[])
    mocker.patch.object(sync_manager.wordpress_connector, "create_validation_issue",
                        return_value={"issue_id": 1})
    mocker.patch.object(sync_manager.wordpress_connector, "update_validation_issue",
                        return_value=True)

    result = sync_manager.validate_data()

    assert result, "validate_data() should return True with participants present"
    assert call_count["n"] == 2, (
        f"Expected exactly 2 page requests (page 1 full, page 2 partial), got {call_count['n']}"
    )


def test_validate_data_syncs_team_issues_idempotently(sync_manager, mocker):
    """Repeated validation should reuse matching TEAM issues and resolve stale ones."""
    participants = [
        {"participant_id": i, "church_id": 1, "is_church_member": False,
         "first_name": f"Player{i}", "last_name": "Test",
         "primary_sport": SPORT_TYPE["BASKETBALL"], "primary_format": "",
         "secondary_sport": "", "secondary_format": ""}
        for i in range(1, 4)
    ]
    existing_issues = [
        {
            "issue_id": 10,
            "church_id": 1,
            "participant_id": None,
            "issue_type": "team_non_member_limit",
            "issue_description": "Basketball - Men Team has 3 non-members, exceeding limit of 2",
            "rule_code": "MAX_NON_MEMBERS_TEAM",
            "rule_level": "TEAM",
            "severity": "ERROR",
            "sport_type": SPORT_TYPE["BASKETBALL"],
            "sport_format": None,
            "status": "open",
        },
        {
            "issue_id": 11,
            "church_id": 1,
            "participant_id": None,
            "issue_type": "doubles_non_member_limit",
            "issue_description": "stale",
            "rule_code": "MAX_NON_MEMBERS_DOUBLES",
            "rule_level": "TEAM",
            "severity": "ERROR",
            "sport_type": SPORT_TYPE["BADMINTON"],
            "sport_format": "Men Double",
            "status": "open",
        },
    ]

    mocker.patch.object(sync_manager.wordpress_connector, "get_participants", return_value=participants)
    mocker.patch.object(sync_manager.wordpress_connector, "get_validation_issues", return_value=existing_issues)
    create_issue = mocker.patch.object(sync_manager.wordpress_connector, "create_validation_issue", return_value={"issue_id": 12})
    update_issue = mocker.patch.object(sync_manager.wordpress_connector, "update_validation_issue", return_value=True)

    result = sync_manager.validate_data()

    assert result, "validate_data() should succeed"
    create_issue.assert_not_called()
    update_issue.assert_called_once()
    assert update_issue.call_args.args[0] == 11
    assert update_issue.call_args.args[1]["status"] == "resolved"
    assert sync_manager.stats["validation_issues"]["unchanged"] == 1
    assert sync_manager.stats["validation_issues"]["resolved"] == 1


def test_validate_data_resolves_church_id_from_church_code(sync_manager, mocker):
    """TEAM validation should work with live-shaped WP participants that only include church_code."""
    participants = [
        {
            "participant_id": str(i),
            "church_code": "RPC",
            "is_church_member": False,
            "first_name": f"Player{i}",
            "last_name": "Test",
            "primary_sport": SPORT_TYPE["BASKETBALL"],
            "primary_format": "",
            "secondary_sport": "",
            "secondary_format": "",
        }
        for i in range(1, 4)
    ]

    mocker.patch.object(sync_manager.wordpress_connector, "get_participants", return_value=participants)
    mocker.patch.object(
        sync_manager.wordpress_connector,
        "get_churches",
        return_value=[{"church_code": "RPC", "church_id": 1, "church_name": "Redemption Point Church"}],
    )
    mocker.patch.object(sync_manager.wordpress_connector, "get_validation_issues", return_value=[])
    create_issue = mocker.patch.object(
        sync_manager.wordpress_connector,
        "create_validation_issue",
        return_value={"issue_id": 21},
    )

    result = sync_manager.validate_data()

    assert result, "validate_data() should succeed when church_id is resolved from church_code"
    create_issue.assert_called_once()
    issue_payload = create_issue.call_args.args[0]
    assert issue_payload["church_id"] == 1
    assert issue_payload["issue_type"] == "team_non_member_limit"
    assert issue_payload["rule_level"] == "TEAM"


def test_validate_data_creates_participant_scoped_team_warning(sync_manager, mocker):
    """Reciprocal doubles-partner mismatches should sync as TEAM warnings with participant_id."""
    participants = [
        {
            "participant_id": "1",
            "church_code": "RPC",
            "is_church_member": True,
            "first_name": "Andy",
            "last_name": "Nguyen",
            "primary_sport": SPORT_TYPE["BADMINTON"],
            "primary_format": "Men Double",
            "primary_partner": "Brian Tran",
            "secondary_sport": "",
            "secondary_format": "",
            "secondary_partner": "",
        },
        {
            "participant_id": "2",
            "church_code": "RPC",
            "is_church_member": True,
            "first_name": "Brian",
            "last_name": "Tran",
            "primary_sport": SPORT_TYPE["BADMINTON"],
            "primary_format": "Men Double",
            "primary_partner": "Chris Pham",
            "secondary_sport": "",
            "secondary_format": "",
            "secondary_partner": "",
        },
    ]

    mocker.patch.object(sync_manager.wordpress_connector, "get_participants", return_value=participants)
    mocker.patch.object(
        sync_manager.wordpress_connector,
        "get_churches",
        return_value=[{"church_code": "RPC", "church_id": 1, "church_name": "Redemption Point Church"}],
    )
    mocker.patch.object(sync_manager.wordpress_connector, "get_validation_issues", return_value=[])
    create_issue = mocker.patch.object(
        sync_manager.wordpress_connector,
        "create_validation_issue",
        return_value={"issue_id": 22},
    )

    result = sync_manager.validate_data()

    assert result
    warning_payload = next(
        call.args[0]
        for call in create_issue.call_args_list
        if call.args[0]["issue_type"] == "doubles_partner_unmatched"
    )
    assert warning_payload["participant_id"] == "1"
    assert warning_payload["rule_code"] == "PARTNER_RECIPROCAL_DOUBLES"
    assert warning_payload["rule_level"] == "TEAM"
    assert warning_payload["severity"] == "WARNING"


def test_sync_validation_issues_per_page(sync_manager, mocker):
    """_sync_validation_issues() must pass per_page=200 to avoid silent PHP-default truncation.
    Runs in both mock and live mode — all external calls are patched by this test itself."""

    from sync.participants import ParticipantSyncer

    participant_syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache,
    )

    captured = {}

    def capturing_get_validation_issues(params=None):
        captured["params"] = params or {}
        return []

    mocker.patch.object(sync_manager.wordpress_connector, "get_validation_issues",
                        side_effect=capturing_get_validation_issues)
    # Prevent _create_or_update_validation_issue from needing churches_cache
    mocker.patch.object(participant_syncer, "_create_or_update_validation_issue")

    issues = [{
        "type": "missing_photo",
        "description": "No photo uploaded",
        "rule_code": "PHOTO_REQUIRED",
        "rule_level": "INDIVIDUAL",
        "severity": "WARNING",
    }]

    participant_syncer._sync_validation_issues("42", "RPC", issues, "2025-01-01")

    assert "params" in captured, "get_validation_issues was never called"
    assert captured["params"].get("per_page") == 200, (
        f"Expected per_page=200, got: {captured['params']}"
    )
    assert captured["params"].get("participant_id") == "42"
    assert captured["params"].get("status") == "open"


def test_sync_validation_issues_resolves_stale_issues_when_current_list_is_empty(sync_manager, mocker):
    """A now-clean participant should still resolve previously open validation issues."""

    from sync.participants import ParticipantSyncer

    participant_syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache,
    )

    existing_issue = {
        "issue_id": "99",
        "participant_id": "42",
        "issue_type": "missing_consent",
        "rule_code": "CONSENT_REQUIRED",
        "status": "open",
    }

    mocker.patch.object(
        sync_manager.wordpress_connector,
        "get_validation_issues",
        return_value=[existing_issue],
    )
    update_issue = mocker.patch.object(
        sync_manager.wordpress_connector,
        "update_validation_issue",
        return_value=True,
    )

    participant_syncer._sync_validation_issues("42", "RPC", [], "2025-01-01")

    update_issue.assert_called_once()
    assert update_issue.call_args.args[0] == "99"
    payload = update_issue.call_args.args[1]
    assert payload["status"] == "resolved"
    assert "resolved_at" in payload
    assert sync_manager.stats["validation_issues"]["resolved"] == 1


def test_sync_validation_issues_distinguishes_same_rule_by_sport_and_format(sync_manager, mocker):
    """Two doubles-partner issues should both sync when they target different events."""

    from sync.participants import ParticipantSyncer

    participant_syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache,
    )
    sync_manager.churches_cache["RPC"] = {"church_id": 1}

    mocker.patch.object(
        sync_manager.wordpress_connector,
        "get_validation_issues",
        return_value=[],
    )
    create_issue = mocker.patch.object(
        sync_manager.wordpress_connector,
        "create_validation_issue",
        return_value={"issue_id": 1},
    )

    issues = [
        {
            "type": "missing_doubles_partner",
            "description": "Partner name required for Badminton (Men Double)",
            "rule_code": "PARTNER_REQUIRED_DOUBLES",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "sport": SPORT_TYPE["BADMINTON"],
            "sport_format": "Men Double",
        },
        {
            "type": "missing_doubles_partner",
            "description": "Partner name required for Pickleball (Mixed Double)",
            "rule_code": "PARTNER_REQUIRED_DOUBLES",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "sport": SPORT_TYPE["PICKLEBALL"],
            "sport_format": "Mixed Double",
        },
    ]

    participant_syncer._sync_validation_issues("42", "RPC", issues, "2026-05-09 00:00:00")

    assert create_issue.call_count == 2
    created_payloads = [call.args[0] for call in create_issue.call_args_list]
    assert {
        (payload["sport_type"], payload["sport_format"])
        for payload in created_payloads
    } == {
        (SPORT_TYPE["BADMINTON"], "Men Double"),
        (SPORT_TYPE["PICKLEBALL"], "Mixed Double"),
    }


def test_sync_participants_skips_orphaned_group_membership(sync_manager, mocker):
    """Full Team-group sync should skip API-only orphaned memberships whose person lookup returns 404."""
    mocker.patch("sync.participants.Config.TEAM_PREFIX", "Team")

    mocker.patch.object(
        sync_manager.wordpress_connector,
        "get_churches",
        return_value=[{"church_code": "RPC", "church_id": 1, "pastor_email": "pastor@rpc.org"}],
    )
    mocker.patch.object(
        sync_manager.chm_connector,
        "get_groups",
        return_value=[{"id": "870578", "name": "Team RPC"}],
    )
    mocker.patch.object(
        sync_manager.chm_connector,
        "get_group_people",
        return_value=[{"person_id": "999999"}],
    )

    def missing_person(_person_id):
        sync_manager.chm_connector.last_get_person_status = "not_found"
        return None

    mocker.patch.object(sync_manager.chm_connector, "get_person", side_effect=missing_person)

    result = sync_manager.sync_participants()

    assert result is True
    assert sync_manager.stats["participants"]["errors"] == 0
    assert sync_manager.stats["participants"]["skipped_missing_people"] == 1


# ---------------------------------------------------------------------------
# Tests for sync_approvals_to_chmeetings() — Issue #60
# All three tests are pure mock tests (no LIVE_TEST guard needed).
# ---------------------------------------------------------------------------

def test_sync_approvals_api_happy(sync_manager, mocker):
    """Happy path: 2 approved participants → add_person_to_group called twice,
    both marked synced in WordPress."""
    participants = [
        {"participant_id": 1, "chmeetings_id": "CHM1", "first_name": "Alice", "last_name": "A"},
        {"participant_id": 2, "chmeetings_id": "CHM2", "first_name": "Bob",   "last_name": "B"},
    ]
    mocker.patch.object(sync_manager.wordpress_connector, "get_participants",
                        return_value=participants)

    groups = [{"id": 999, "name": "2026 Sports Fest"}]
    mocker.patch.object(sync_manager.chm_connector, "get_groups", return_value=groups)
    mocker.patch.object(sync_manager.chm_connector, "add_person_to_group", return_value=True)

    approvals = [
        {"approval_id": 10, "participant_id": 1},
        {"approval_id": 20, "participant_id": 2},
    ]
    mocker.patch.object(sync_manager.wordpress_connector, "get_approvals",
                        return_value=approvals)
    mocker.patch.object(sync_manager.wordpress_connector, "update_approval",
                        return_value=True)

    mocker.patch("sync.manager.Config.APPROVED_GROUP_NAME", "2026 Sports Fest")

    result = sync_manager.sync_approvals_to_chmeetings()

    assert result is True
    assert sync_manager.chm_connector.add_person_to_group.call_count == 2
    sync_manager.chm_connector.add_person_to_group.assert_any_call("999", "CHM1")
    sync_manager.chm_connector.add_person_to_group.assert_any_call("999", "CHM2")
    assert sync_manager.wordpress_connector.update_approval.call_count == 2


def test_sync_approvals_group_not_found(sync_manager, mocker):
    """If APPROVED_GROUP_NAME doesn't exist in ChMeetings, return False immediately
    and make zero update_approval calls."""
    participants = [
        {"participant_id": 1, "chmeetings_id": "CHM1", "first_name": "Alice", "last_name": "A"},
    ]
    mocker.patch.object(sync_manager.wordpress_connector, "get_participants",
                        return_value=participants)

    # Group list has no entry matching APPROVED_GROUP_NAME
    mocker.patch.object(sync_manager.chm_connector, "get_groups", return_value=[
        {"id": 1, "name": "Some Other Group"},
    ])
    mock_update = mocker.patch.object(sync_manager.wordpress_connector, "update_approval",
                                      return_value=True)

    mocker.patch("sync.manager.Config.APPROVED_GROUP_NAME", "2026 Sports Fest")

    result = sync_manager.sync_approvals_to_chmeetings()

    assert result is False
    mock_update.assert_not_called()


def test_sync_approvals_partial_failure(sync_manager, mocker):
    """First add succeeds, second fails → only the first is marked synced,
    function returns False (failed_count > 0)."""
    participants = [
        {"participant_id": 1, "chmeetings_id": "CHM1", "first_name": "Alice", "last_name": "A"},
        {"participant_id": 2, "chmeetings_id": "CHM2", "first_name": "Bob",   "last_name": "B"},
    ]
    mocker.patch.object(sync_manager.wordpress_connector, "get_participants",
                        return_value=participants)

    groups = [{"id": 999, "name": "2026 Sports Fest"}]
    mocker.patch.object(sync_manager.chm_connector, "get_groups", return_value=groups)
    # First call True, second False
    mocker.patch.object(sync_manager.chm_connector, "add_person_to_group",
                        side_effect=[True, False])

    approvals = [
        {"approval_id": 10, "participant_id": 1},
        {"approval_id": 20, "participant_id": 2},
    ]
    mocker.patch.object(sync_manager.wordpress_connector, "get_approvals",
                        return_value=approvals)
    mock_update = mocker.patch.object(sync_manager.wordpress_connector, "update_approval",
                                      return_value=True)

    mocker.patch("sync.manager.Config.APPROVED_GROUP_NAME", "2026 Sports Fest")

    result = sync_manager.sync_approvals_to_chmeetings()

    assert result is False  # failed_count == 1
    # Only participant 1 (Alice) should have been marked synced
    assert mock_update.call_count == 1
    mock_update.assert_called_once_with(10, {"synced_to_chmeetings": True})

def test_sync_rosters_soccer_coed_exhibition(sync_manager, mocker):
    """Soccer - Coed Exhibition arrives via the other_events checkbox; the comma-split
    loop must produce a single roster row with sport_format=Team and sport_gender=Mixed,
    so it bypasses the non-member team limit by living outside primary/secondary slots."""
    participant_syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache,
    )

    captured = []

    def capture_create_or_update_roster(roster_data):
        captured.append(roster_data)
        return {"roster_id": len(captured), **roster_data}

    mocker.patch.object(participant_syncer, "_create_or_update_roster",
                        side_effect=capture_create_or_update_roster)

    participant = {
        "church_code": "RPC",
        "primary_sport": SPORT_UNSELECTED,
        "secondary_sport": SPORT_UNSELECTED,
        "other_events": "Soccer - Coed Exhibition",
    }
    participant_syncer._sync_rosters("42", participant)

    assert len(captured) == 1, f"Expected 1 roster row, got {len(captured)}: {captured}"
    row = captured[0]
    assert row["sport_type"] == "Soccer - Coed Exhibition"
    assert row["sport_format"] == SPORT_FORMAT["TEAM"]
    assert row["sport_gender"] == GENDER["MIXED"]
    assert row["participant_id"] == 42
    assert row["church_code"] == "RPC"


def test_sync_rosters_skips_create_when_lookup_fails_after_retry(sync_manager, mocker):
    participant_syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache,
    )

    participant = {
        "church_code": "RPC",
        "primary_sport": SPORT_UNSELECTED,
        "secondary_sport": SPORT_UNSELECTED,
        "other_events": "Soccer - Coed Exhibition",
    }

    call_counter = {"count": 0}

    def get_rosters_side_effect(params):
        call_counter["count"] += 1
        if call_counter["count"] <= 2:
            sync_manager.wordpress_connector.last_get_rosters_status = "failed"
            return []
        sync_manager.wordpress_connector.last_get_rosters_status = "ok"
        return []

    mocker.patch.object(
        sync_manager.wordpress_connector,
        "get_rosters",
        side_effect=get_rosters_side_effect,
    )
    mock_create = mocker.patch.object(
        sync_manager.wordpress_connector,
        "create_roster",
        return_value={"roster_id": "501"},
    )
    mock_delete = mocker.patch.object(
        sync_manager.wordpress_connector,
        "delete_roster",
        return_value=True,
    )

    participant_syncer._sync_rosters("131", participant)

    mock_create.assert_not_called()
    mock_delete.assert_not_called()
    assert sync_manager.stats["rosters"]["errors"] == 1


def test_sync_rosters_deletes_duplicate_current_rosters(sync_manager, mocker):
    participant_syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache,
    )

    participant = {
        "church_code": "RPC",
        "primary_sport": SPORT_UNSELECTED,
        "secondary_sport": SPORT_UNSELECTED,
        "other_events": "Soccer - Coed Exhibition",
    }

    duplicate_rosters = [
        {
            "roster_id": "10",
            "participant_id": 131,
            "sport_type": "Soccer - Coed Exhibition",
            "sport_format": SPORT_FORMAT["TEAM"],
            "sport_gender": GENDER["MIXED"],
            "team_order": None,
            "partner_name": None,
        },
        {
            "roster_id": "11",
            "participant_id": 131,
            "sport_type": "Soccer - Coed Exhibition",
            "sport_format": SPORT_FORMAT["TEAM"],
            "sport_gender": GENDER["MIXED"],
            "team_order": None,
            "partner_name": None,
        },
    ]

    def get_rosters_side_effect(_params):
        sync_manager.wordpress_connector.last_get_rosters_status = "ok"
        return [dict(r) for r in duplicate_rosters]

    mocker.patch.object(
        sync_manager.wordpress_connector,
        "get_rosters",
        side_effect=get_rosters_side_effect,
    )
    mock_create = mocker.patch.object(sync_manager.wordpress_connector, "create_roster")
    mock_delete = mocker.patch.object(
        sync_manager.wordpress_connector,
        "delete_roster",
        return_value=True,
    )

    participant_syncer._sync_rosters("131", participant)

    mock_create.assert_not_called()
    mock_delete.assert_called_once_with("11")
    assert sync_manager.stats["rosters"]["deleted"] == 1


##### End of tests/test_sync_manager
