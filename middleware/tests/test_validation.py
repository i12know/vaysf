# tests/test_validation.py
# version 1.0.4
# author: Claude 3.7, Bumble & Grok 3
import os
import json
import pytest
from datetime import datetime
from validation.models import Participant, RulesManager
from validation.individual_validator import IndividualValidator
from validation.team_validator import TeamValidator
from loguru import logger
from config import Config, CHM_FIELDS
from config import (SPORT_TYPE, SPORT_UNSELECTED, DEFAULT_SPORT,
                   VALIDATION_SEVERITY, AGE_RESTRICTIONS)

@pytest.fixture
def rules_manager():
    """Fixture for RulesManager."""
    return RulesManager(collection="SUMMER_2026")

@pytest.fixture
def validator():
    """Fixture for IndividualValidator."""
    return IndividualValidator(collection="SUMMER_2026")

def test_rules_manager_loads_rules(rules_manager):
    """Test that RulesManager loads rules correctly."""
    assert len(rules_manager.rules) > 0, "Rules should be loaded"
    assert any(r.get("rule_type") == "age" for r in rules_manager.rules), "Should have age rules"
    assert any(r.get("rule_type") == "gender" for r in rules_manager.rules), "Should have gender rules"
    assert any(r.get("rule_type") == "photo" for r in rules_manager.rules), "Should have photo rules"
    assert any(r.get("rule_type") == "consent" for r in rules_manager.rules), "Should have consent rules"
    assert any(r.get("rule_type") == "partner" for r in rules_manager.rules), "Should have partner rules"
    assert any(r.get("rule_type") == "team_size" for r in rules_manager.rules), "Should have team size rules"

def test_participant_model():
    """Test Participant Pydantic model."""
    valid_data = {
        "chmeetings_id": "12345",
        "first_name": "John",
        "last_name": "Doe",
        "gender": "Male",
        "birthdate": "2000-01-01"
    }
    participant = Participant(**valid_data)
    assert participant.chmeetings_id == "12345"
    assert participant.first_name == "John"
    assert participant.last_name == "Doe"
    
    with pytest.raises(Exception):
        Participant(first_name="John", last_name="Doe")  # Missing required fields

@pytest.fixture
def mock_chm_people_data():
    """Load mock ChMeetings data from JSON file."""
    file_path = os.path.join(os.path.dirname(__file__), "mock_chm_people_good_data.json")
    with open(file_path, "r") as f:
        return json.load(f)

def test_validator_with_good_mock_data(validator, mock_chm_people_data):
    """Test validator with good mock data, expecting all to pass with warnings."""
    failed_participants = []  # To track participants that fail validation
    
    for person in mock_chm_people_data:
        # Get additional fields
        additional_fields = {f["field_name"]: f["value"] for f in person.get("additional_fields", [])}
        
        # Create participant data from mock data
        participant_data = {
            "chmeetings_id": str(person["id"]),
            "first_name": person["first_name"],
            "last_name": person["last_name"],
            "gender": person["gender"],
            "birthdate": person["birth_date"],
            "primary_sport": additional_fields.get(CHM_FIELDS["PRIMARY_SPORT"], SPORT_TYPE["BIBLE_CHALLENGE"]),
            "secondary_sport": additional_fields.get(CHM_FIELDS["SECONDARY_SPORT"], "Pickleball - Mixed Doubles"),
            "photo_url": person["photo"],
            "consent_status": False  # Will cause consent validation warning
        }
        
        # Log participant being tested
        name = f"{person['first_name']} {person['last_name']} (ID: {person['id']})"
        logger.info(f"Testing participant: {name}")
        logger.info(f"Participant data: {participant_data}")
        
        # Validate
        is_valid, issues = validator.validate(participant_data)
        
        # Log validation results
        logger.info(f"Validation result: is_valid={is_valid}, issues={issues}")
        
        # Check for warnings
        warnings = [i for i in issues if i.get("severity") == VALIDATION_SEVERITY["WARNING"]]
        
        if not is_valid:
            failed_participants.append({"name": name, "issues": issues})
        else:
            assert len(warnings) > 0, f"Expected warnings for {name} but got none"
            assert any("consent" in i["type"] for i in warnings), f"Expected consent warning for {name}"
        
        # Test without photo
        participant_data["photo_url"] = None
        logger.info(f"Retesting participant with no photo: {name}")
        logger.info(f"Updated participant data: {participant_data}")
        
        is_valid, issues = validator.validate(participant_data)
        logger.info(f"Validation result (no photo): is_valid={is_valid}, issues={issues}")
        
        warnings = [i for i in issues if i.get("severity") == VALIDATION_SEVERITY["WARNING"]]
        if not is_valid:
            failed_participants.append({"name": f"{name} - No Photo", "issues": issues})
        else:
            assert len(warnings) > 1, f"Expected multiple warnings for {name} (no photo) but got {len(warnings)}"
            assert any("photo" in i["type"] for i in warnings), f"Expected photo warning for {name}"
            assert any("consent" in i["type"] for i in warnings), f"Expected consent warning for {name}"
    
    # All participants should pass with warnings only
    assert not failed_participants, f"Some participants failed validation:\n" + "\n".join(
        f"{p['name']}: {p['issues']}" for p in failed_participants
    )

@pytest.fixture
def mock_chm_bad_people_data():
    """Load bad mock ChMeetings data from JSON file."""
    file_path = os.path.join(os.path.dirname(__file__), "mock_chm_people_bad_data.json")
    with open(file_path, "r") as f:
        return json.load(f)

def test_validator_with_bad_mock_data(validator, mock_chm_bad_people_data):
    """Test validator with bad mock data, expecting all to fail with errors."""
    passed_participants = []  # To track participants that unexpectedly pass
    
    for person in mock_chm_bad_people_data:
        # Get additional fields
        additional_fields = {f["field_name"]: f["value"] for f in person.get("additional_fields", [])}
        
        # Create participant data from mock data
        participant_data = {
            "chmeetings_id": str(person["id"]),
            "first_name": person["first_name"],
            "last_name": person["last_name"],
            "gender": person["gender"],
            "birthdate": person["birth_date"],
            "primary_sport": additional_fields.get(CHM_FIELDS["PRIMARY_SPORT"], SPORT_TYPE["BIBLE_CHALLENGE"]),
            "secondary_sport": additional_fields.get(CHM_FIELDS["SECONDARY_SPORT"], "Pickleball - Mixed Doubles"),
            "photo_url": person["photo"],
            "consent_status": False
        }
        
        # Log participant being tested
        name = f"{person['first_name']} {person['last_name']} (ID: {person['id']})"
        logger.info(f"Testing bad participant: {name}")
        logger.info(f"Participant data: {participant_data}")
        
        # Validate
        is_valid, issues = validator.validate(participant_data)
        
        # Log validation results
        logger.info(f"Validation result: is_valid={is_valid}, issues={issues}")
        
        if is_valid:
            passed_participants.append({"name": name, "issues": issues})
        else:
            errors = [i for i in issues if i.get("severity") == VALIDATION_SEVERITY["ERROR"]]
            assert len(errors) > 0, f"Expected ERROR issues for {name} but got none: {issues}"
    
    # All participants should fail with errors
    assert not passed_participants, f"Some bad participants unexpectedly passed:\n" + "\n".join(
        f"{p['name']}: {p['issues']}" for p in passed_participants
    )

def test_age_validation(validator):
    """Test age validation rules."""
    # Create test participants
    too_young = {
        "chmeetings_id": "young",
        "first_name": "Too",
        "last_name": "Young",
        "gender": "Male",
        "birthdate": "2015-01-01",  # 10 years old in 2025
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }
    
    too_old = {
        "chmeetings_id": "old",
        "first_name": "Too",
        "last_name": "Old",
        "gender": "Male",
        "birthdate": "1985-01-01",  # 40 years old in 2025
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }
    
    scripture_ok = {
        "chmeetings_id": "scripture",
        "first_name": "Scripture",
        "last_name": "Kid",
        "gender": "Female",
        "birthdate": "2015-01-01",  # 10 years old in 2025
        "primary_sport": SPORT_TYPE["SCRIPTURE"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }
    
    pickleball_ok = {
        "chmeetings_id": "pickleball",
        "first_name": "Pickleball",
        "last_name": "Senior",
        "gender": "Male",
        "birthdate": "1985-01-01",  # 40 years old in 2025
        "primary_sport": SPORT_TYPE["PICKLEBALL_35"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }

    table_tennis_35_ok = {
        "chmeetings_id": "tabletennis35",
        "first_name": "Table",
        "last_name": "Senior",
        "gender": "Female",
        "birthdate": "1985-01-01",  # 41 years old on 2026-07-18
        "primary_sport": SPORT_TYPE["TABLE_TENNIS_35"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }

    table_tennis_35_underage = {
        "chmeetings_id": "tabletennis35_underage",
        "first_name": "Table",
        "last_name": "Junior",
        "gender": "Male",
        "birthdate": "1995-01-01",  # 31 years old on 2026-07-18
        "primary_sport": SPORT_TYPE["TABLE_TENNIS_35"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }
    
    # Test too young
    is_valid, issues = validator.validate(too_young)
    assert not is_valid, "Should fail - too young for Basketball"
    assert any("age_restriction" in issue["type"] for issue in issues)
    
    # Test too old
    is_valid, issues = validator.validate(too_old)
    assert not is_valid, "Should fail - too old for Basketball"
    assert any("age_restriction" in issue["type"] for issue in issues)
    
    # Test scripture exception
    is_valid, issues = validator.validate(scripture_ok)
    assert is_valid, f"Should pass Scripture Memorization at 10yo but got issues: {issues}"
    
    # Test pickleball 35+ exception
    is_valid, issues = validator.validate(pickleball_ok)
    assert is_valid, f"Should pass Pickleball 35+ at 40yo but got issues: {issues}"

    # Test table tennis 35+ exception
    is_valid, issues = validator.validate(table_tennis_35_ok)
    assert is_valid, f"Should pass Table Tennis 35+ at 40+yo but got issues: {issues}"

    # Test under-35 table tennis 35+ rejection
    is_valid, issues = validator.validate(table_tennis_35_underage)
    assert not is_valid, "Should fail - under 35 for Table Tennis 35+"
    assert any(
        issue["type"] == "age_restriction" and issue.get("rule_code") == "MIN_AGE_TABLE_TENNIS35"
        for issue in issues
    ), f"Expected MIN_AGE_TABLE_TENNIS35 issue, got: {issues}"

def test_gender_validation(validator):
    """Test gender validation rules."""
    # Male in men's basketball - should pass
    valid_male = {
        "chmeetings_id": "valid_male",
        "first_name": "Valid",
        "last_name": "Male",
        "gender": "Male",
        "birthdate": "2000-01-01",
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }
    
    # Female in men's basketball - should fail
    invalid_female = {
        "chmeetings_id": "invalid_female",
        "first_name": "Invalid",
        "last_name": "Female",
        "gender": "Female",
        "birthdate": "2000-01-01",
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True
    }
    
    # Test valid male
    is_valid, issues = validator.validate(valid_male)
    assert is_valid, f"Should pass for male in men's basketball but got issues: {issues}"
    
    # Test invalid female
    is_valid, issues = validator.validate(invalid_female)
    assert not is_valid, "Should fail for female in men's basketball"
    assert any("gender_mismatch" in issue["type"] for issue in issues)

def test_photo_validation(validator):
    """Test photo validation with various cases."""
    # Case 1: No photo provided
    no_photo = {
        "chmeetings_id": "no_photo",
        "first_name": "No",
        "last_name": "Photo",
        "gender": "Male",
        "birthdate": "2000-01-01",
        "photo_url": None
    }
    _, issues = validator.validate(no_photo)
    photo_issues = [i for i in issues if i["type"] == "missing_photo"]
    assert len(photo_issues) == 1, "Should have one missing photo issue"
    assert photo_issues[0]["severity"] == VALIDATION_SEVERITY["WARNING"], "Missing photo should be a warning"
    
    # Case 2: Invalid URL format
    invalid_url = {
        "chmeetings_id": "invalid_url",
        "first_name": "Invalid",
        "last_name": "URL",
        "gender": "Male",
        "birthdate": "2000-01-01",
        "photo_url": "not-a-url"
    }
    _, issues = validator.validate(invalid_url)
    url_issues = [i for i in issues if i["type"] == "invalid_photo_url"]
    assert len(url_issues) == 1, "Should have one invalid URL issue"
    
    # Case 3: Valid URL
    valid_url = {
        "chmeetings_id": "valid_url",
        "first_name": "Valid",
        "last_name": "URL",
        "gender": "Male",
        "birthdate": "2000-01-01",
        "photo_url": "https://not-exist.example.com/photo.jpg"
    }
    is_valid, issues = validator.validate(valid_url)
    photo_issues = [i for i in issues if i["type"].startswith("photo") or i["type"] == "missing_photo"]
    if os.getenv("LIVE_TEST", "false").strip().lower() == "true":
        # In live test, we might have accessibility issues
        if photo_issues:
            assert all(issue["severity"] == VALIDATION_SEVERITY["WARNING"] for issue in photo_issues), "Photo issues should be warnings"
    else:
        # In mock test, we should have no photo issues
        assert not any(i["type"].startswith("photo") for i in issues), "Should not have photo issues with valid URL"
    
    # If we're in live test mode, test a real working URL vs a broken one
    if os.getenv("LIVE_TEST", "false").strip().lower() == "true":
        # Working URL - use a reliable public image
        working_url = {
            "chmeetings_id": "working_url",
            "first_name": "Working",
            "last_name": "URL",
            "gender": "Male",
            "birthdate": "2000-01-01",
            "photo_url": "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"
        }
        is_valid, issues = validator.validate(working_url)
        photo_issues = [i for i in issues if i["type"].startswith("photo")]
        assert not photo_issues, "Should not have issues with working URL"
        
        # Broken URL - use a non-existent image
        broken_url = {
            "chmeetings_id": "broken_url",
            "first_name": "Broken",
            "last_name": "URL",
            "gender": "Male",
            "birthdate": "2000-01-01",
            "photo_url": "https://not-exist.example.com/nonexistent.jpg"
        }
        _, issues = validator.validate(broken_url)
        photo_issues = [i for i in issues if i["type"].startswith("photo")]
        assert len(photo_issues) > 0, "Should have issues with broken URL"
        assert all(issue["severity"] == VALIDATION_SEVERITY["WARNING"] for issue in photo_issues), "Photo issues should be warnings"

def test_severity_levels(validator):
    """Test how severity levels affect validation results."""
    # Test with all warnings, no errors
    warnings_only = {
        "chmeetings_id": "warning_test",
        "first_name": "Warning",
        "last_name": "Test",
        "gender": "Male",
        "birthdate": "2000-01-01",
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": None,  # Will trigger photo warning
        "consent_status": False  # Will trigger consent warning
    }
    
    is_valid, issues = validator.validate(warnings_only)
    assert is_valid, "Participant with only warnings should still be valid"
    
    warnings = [i for i in issues if i.get("severity") == VALIDATION_SEVERITY["WARNING"]]
    assert len(warnings) == 2, "Should have both photo and consent warnings"
    
    # Test with mix of warnings and errors
    mixed_severity = {
        "chmeetings_id": "mixed_test",
        "first_name": "Mixed",
        "last_name": "Test",
        "gender": "Female",  # Will trigger gender error
        "birthdate": "2000-01-01",
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": None,  # Will trigger photo warning
        "consent_status": False  # Will trigger consent warning
    }
    
    is_valid, issues = validator.validate(mixed_severity)
    assert not is_valid, "Participant with errors should be invalid"
    
    errors = [i for i in issues if i.get("severity") == VALIDATION_SEVERITY["ERROR"]]
    warnings = [i for i in issues if i.get("severity") == VALIDATION_SEVERITY["WARNING"]]
    assert len(errors) == 1, "Should have gender error"
    assert len(warnings) == 2, "Should have both photo and consent warnings"


def test_invalid_birthdate_does_not_crash_consent_validation(validator):
    """Malformed birthdates should return an issue instead of raising."""
    participant = {
        "chmeetings_id": "bad_birthdate",
        "first_name": "Bad",
        "last_name": "Birthdate",
        "gender": "Male",
        "birthdate": "2008/07/19",
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": False,
    }

    is_valid, issues = validator.validate(participant)

    assert not is_valid, "Malformed birthdates should fail validation"
    assert any(issue["type"] == "invalid_birthdate" for issue in issues), issues


def test_missing_consent_stays_error_until_18th_birthday(validator):
    """A participant who is still 17 on event day must keep ERROR severity for consent."""
    participant = {
        "chmeetings_id": "minor_boundary",
        "first_name": "Boundary",
        "last_name": "Minor",
        "gender": "Male",
        "birthdate": "2008-07-19",
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": False,
    }

    is_valid, issues = validator.validate(participant)

    assert not is_valid, "A 17-year-old with missing consent should not validate"
    consent_issue = next(issue for issue in issues if issue["type"] == "missing_consent")
    assert consent_issue["severity"] == VALIDATION_SEVERITY["ERROR"]


def test_doubles_partner_required_for_primary_selection(validator):
    """Racquet doubles entries must include a partner name."""
    participant = {
        "chmeetings_id": "primary_doubles_no_partner",
        "first_name": "Primary",
        "last_name": "Doubles",
        "gender": "Male",
        "birthdate": "2000-01-01",
        "primary_sport": SPORT_TYPE["BADMINTON"],
        "primary_format": "Men Double",
        "primary_partner": "   ",
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True,
    }

    is_valid, issues = validator.validate(participant)

    assert not is_valid, "Missing partner should block doubles validation"
    partner_issue = next(issue for issue in issues if issue["type"] == "missing_doubles_partner")
    assert partner_issue["rule_code"] == "PARTNER_REQUIRED_DOUBLES"
    assert partner_issue["rule_level"] == "INDIVIDUAL"
    assert partner_issue["severity"] == VALIDATION_SEVERITY["ERROR"]
    assert partner_issue["sport"] == SPORT_TYPE["BADMINTON"]
    assert partner_issue["sport_format"] == "Men Double"


def test_doubles_partner_required_for_secondary_selection(validator):
    """Secondary doubles selections should be validated independently."""
    participant = {
        "chmeetings_id": "secondary_doubles_no_partner",
        "first_name": "Secondary",
        "last_name": "Doubles",
        "gender": "Female",
        "birthdate": "2000-01-01",
        "primary_sport": SPORT_TYPE["BASKETBALL"],
        "secondary_sport": SPORT_TYPE["PICKLEBALL"],
        "secondary_format": "Mixed Double",
        "secondary_partner": "",
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True,
    }

    is_valid, issues = validator.validate(participant)

    assert not is_valid, "Missing partner should also fail secondary doubles entries"
    partner_issue = next(issue for issue in issues if issue["type"] == "missing_doubles_partner")
    assert partner_issue["sport"] == SPORT_TYPE["PICKLEBALL"]
    assert partner_issue["sport_format"] == "Mixed Double"


def test_doubles_partner_present_passes_validation(validator):
    """Providing the partner name should satisfy the doubles partner rule."""
    participant = {
        "chmeetings_id": "doubles_with_partner",
        "first_name": "Ready",
        "last_name": "Player",
        "gender": "Female",
        "birthdate": "2000-01-01",
        "primary_sport": SPORT_TYPE["TENNIS"],
        "primary_format": "Mixed Double",
        "primary_partner": "Alex Kim",
        "photo_url": "https://example.com/photo.jpg",
        "consent_status": True,
    }

    is_valid, issues = validator.validate(participant)

    assert is_valid, f"Doubles entries with a partner should pass, got: {issues}"
    assert not any(issue["type"] == "missing_doubles_partner" for issue in issues)


# ---------------------------------------------------------------------------
# TeamValidator tests
# ---------------------------------------------------------------------------

@pytest.fixture
def team_validator():
    return TeamValidator(collection="SUMMER_2026")


def _make_participant(church_id=1, is_member=False,
                      primary_sport="", primary_format="",
                      secondary_sport="", secondary_format="", other_events=""):
    return {
        "church_id": church_id,
        "is_church_member": is_member,
        "primary_sport": primary_sport,
        "primary_format": primary_format,
        "secondary_sport": secondary_sport,
        "secondary_format": secondary_format,
        "other_events": other_events,
    }


def test_team_validator_under_team_limit(team_validator):
    """2 non-members in Basketball — at limit, no issue."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
    ]
    issues = team_validator.validate_church(1, participants)
    assert issues == []


def test_team_validator_exceeds_team_limit(team_validator):
    """3 non-members in Basketball — one team_non_member_limit issue."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
    ]
    issues = team_validator.validate_church(1, participants)
    assert len(issues) == 1
    issue = issues[0]
    assert issue["issue_type"] == "team_non_member_limit"
    assert issue["church_id"] == 1
    assert issue["participant_id"] is None
    assert SPORT_TYPE["BASKETBALL"] in issue["issue_description"]
    assert "3 non-members" in issue["issue_description"]
    assert "exceeding limit of 2" in issue["issue_description"]


def test_team_validator_each_team_sport_independent(team_validator):
    """Basketball at limit and Volleyball at limit are counted independently."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["VOLLEYBALL_MEN"]),
        _make_participant(primary_sport=SPORT_TYPE["VOLLEYBALL_MEN"]),
        _make_participant(primary_sport=SPORT_TYPE["VOLLEYBALL_MEN"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["VOLLEYBALL_MEN"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["VOLLEYBALL_MEN"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["VOLLEYBALL_MEN"], is_member=True),
    ]
    issues = team_validator.validate_church(1, participants)
    assert issues == [], "Two sports each at the limit should produce no issues"


def test_team_validator_ignores_members(team_validator):
    """Church members are never counted toward the non-member limit."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
    ]
    issues = team_validator.validate_church(1, participants)
    assert issues == []


def test_team_validator_secondary_sport_also_counted(team_validator):
    """Non-members with Basketball as secondary sport count toward the limit."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(secondary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
    ]
    issues = team_validator.validate_church(1, participants)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "team_non_member_limit"


def test_team_validator_basketball_requires_minimum_of_five(team_validator):
    """Basketball should use the generic minimum team-size rule path."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
    ]

    issues = team_validator.validate_church(1, participants)

    assert len(issues) == 1
    issue = issues[0]
    assert issue["issue_type"] == "team_min_size"
    assert issue["rule_code"] == "MIN_TEAM_SIZE_BASKETBALL"
    assert issue["rule_level"] == "TEAM"
    assert issue["severity"] == VALIDATION_SEVERITY["ERROR"]
    assert issue["sport_type"] == SPORT_TYPE["BASKETBALL"]
    assert "below minimum size of 5" in issue["issue_description"]


def test_team_validator_soccer_requires_minimum_of_four(team_validator):
    """Soccer - Coed Exhibition should fail until a church has 4 participants."""
    participants = [
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
    ]

    issues = team_validator.validate_church(1, participants)

    assert len(issues) == 1
    issue = issues[0]
    assert issue["issue_type"] == "team_min_size"
    assert issue["rule_code"] == "MIN_TEAM_SIZE_SOCCER_COED"
    assert issue["rule_level"] == "TEAM"
    assert issue["severity"] == VALIDATION_SEVERITY["ERROR"]
    assert issue["sport_type"] == "Soccer - Coed Exhibition"
    assert "below minimum size of 4" in issue["issue_description"]


def test_team_validator_soccer_passes_at_four(team_validator):
    """Soccer - Coed Exhibition should pass the minimum-size check at 4 participants."""
    participants = [
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
    ]

    issues = team_validator.validate_church(1, participants)

    assert not any(issue["issue_type"] == "team_min_size" for issue in issues), issues


def test_team_validator_soccer_disallows_non_members(team_validator):
    """Soccer - Coed Exhibition should not allow any non-members."""
    participants = [
        _make_participant(is_member=False, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
        _make_participant(is_member=True, other_events="Soccer - Coed Exhibition"),
    ]

    issues = team_validator.validate_church(1, participants)

    non_member_issue = next(issue for issue in issues if issue["issue_type"] == "team_non_member_limit")
    assert non_member_issue["rule_code"] == "MAX_NON_MEMBERS_SOCCER_COED"
    assert non_member_issue["rule_level"] == "TEAM"
    assert non_member_issue["severity"] == VALIDATION_SEVERITY["ERROR"]
    assert non_member_issue["sport_type"] == "Soccer - Coed Exhibition"
    assert "exceeding limit of 0" in non_member_issue["issue_description"]


def test_team_validator_under_doubles_limit(team_validator):
    """1 non-member in Mixed Double Pickleball — at limit, no issue."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["PICKLEBALL"],
                          primary_format="Mixed Double"),
    ]
    issues = team_validator.validate_church(1, participants)
    assert issues == []


def test_team_validator_exceeds_doubles_limit(team_validator):
    """2 non-members in Men Double Badminton — one doubles_non_member_limit issue."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BADMINTON"],
                          primary_format="Men Double"),
        _make_participant(primary_sport=SPORT_TYPE["BADMINTON"],
                          primary_format="Men Double"),
    ]
    issues = team_validator.validate_church(1, participants)
    assert len(issues) == 1
    issue = issues[0]
    assert issue["issue_type"] == "doubles_non_member_limit"
    assert issue["church_id"] == 1
    assert issue["participant_id"] is None
    assert SPORT_TYPE["BADMINTON"] in issue["issue_description"]
    assert "Men Double" in issue["issue_description"]
    assert "exceeding limit of 1" in issue["issue_description"]


def test_team_validator_doubles_format_isolated_by_format(team_validator):
    """1 non-member in Men Double + 1 in Women Double — each under limit, no issue."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BADMINTON"],
                          primary_format="Men Double"),
        _make_participant(primary_sport=SPORT_TYPE["BADMINTON"],
                          primary_format="Women Double"),
    ]
    issues = team_validator.validate_church(1, participants)
    assert issues == [], "Different formats must be tracked separately"


def test_team_validator_doubles_limit_is_per_pair(team_validator):
    """Two separate pairs with one non-member each must not trip the per-pair cap."""
    participants = [
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 1,
            "first_name": "Andy",
            "last_name": "Nguyen",
            "primary_partner": "Brian Tran",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double", is_member=True),
            "participant_id": 2,
            "first_name": "Brian",
            "last_name": "Tran",
            "primary_partner": "Andy Nguyen",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 3,
            "first_name": "Chris",
            "last_name": "Pham",
            "primary_partner": "David Le",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double", is_member=True),
            "participant_id": 4,
            "first_name": "David",
            "last_name": "Le",
            "primary_partner": "Chris Pham",
        },
    ]

    issues = team_validator.validate_church(1, participants)

    assert not any(issue["issue_type"] == "doubles_non_member_limit" for issue in issues), issues
    assert not any(issue["issue_type"] == "doubles_partner_unmatched" for issue in issues), issues


def test_team_validator_doubles_limit_flags_two_non_members_in_same_pair(team_validator):
    """A single doubles pair with two non-members must still fail."""
    participants = [
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 1,
            "first_name": "Andy",
            "last_name": "Nguyen",
            "primary_partner": "Brian Tran",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 2,
            "first_name": "Brian",
            "last_name": "Tran",
            "primary_partner": "Andy Nguyen",
        },
    ]

    issues = team_validator.validate_church(1, participants)

    assert len(issues) == 1
    assert issues[0]["issue_type"] == "doubles_non_member_limit"


def test_team_validator_issues_include_rule_metadata(team_validator):
    """Team issues should carry TEAM-level rule metadata into WordPress."""
    participants = [
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"]),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
        _make_participant(primary_sport=SPORT_TYPE["BASKETBALL"], is_member=True),
    ]

    issues = team_validator.validate_church(1, participants)

    assert len(issues) == 1
    issue = issues[0]
    assert issue["rule_code"] == "MAX_NON_MEMBERS_TEAM"
    assert issue["rule_level"] == "TEAM"
    assert issue["severity"] == "ERROR"
    assert issue["sport_type"] == SPORT_TYPE["BASKETBALL"]


def test_team_validator_reciprocal_doubles_partner_match_passes(team_validator):
    """Matching A<->B doubles partner selections should not warn."""
    participants = [
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 1,
            "first_name": "Andy",
            "last_name": "Nguyen",
            "primary_partner": "Brian Tran",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 2,
            "first_name": "Brian",
            "last_name": "Tran",
            "primary_partner": "Andy Nguyen",
        },
    ]

    issues = team_validator.validate_church(1, participants)

    assert not any(issue["issue_type"] == "doubles_partner_unmatched" for issue in issues), issues


def test_team_validator_reciprocal_doubles_partner_mismatch_warns(team_validator):
    """A named partner who does not reciprocate should raise a WARNING TEAM issue."""
    participants = [
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 1,
            "first_name": "Andy",
            "last_name": "Nguyen",
            "primary_partner": "Brian Tran",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Men Double"),
            "participant_id": 2,
            "first_name": "Brian",
            "last_name": "Tran",
            "primary_partner": "Chris Pham",
        },
    ]

    issues = team_validator.validate_church(1, participants)

    partner_issue = next(issue for issue in issues if issue["issue_type"] == "doubles_partner_unmatched")
    assert partner_issue["participant_id"] == 1
    assert partner_issue["rule_code"] == "PARTNER_RECIPROCAL_DOUBLES"
    assert partner_issue["rule_level"] == "TEAM"
    assert partner_issue["severity"] == VALIDATION_SEVERITY["WARNING"]
    assert "did not reciprocally list" in partner_issue["issue_description"]


def test_team_validator_reciprocal_match_can_cross_primary_and_secondary_slots(team_validator):
    """Reciprocal partner matching should work even if the event lives in different slots."""
    participants = [
        {
            **_make_participant(primary_sport=SPORT_TYPE["BADMINTON"], primary_format="Mixed Double"),
            "participant_id": 1,
            "first_name": "Amy",
            "last_name": "Le",
            "primary_partner": "Ben Tran",
        },
        {
            **_make_participant(secondary_sport=SPORT_TYPE["BADMINTON"], secondary_format="Mixed Double"),
            "participant_id": 2,
            "first_name": "Ben",
            "last_name": "Tran",
            "secondary_partner": "Amy Le",
        },
    ]

    issues = team_validator.validate_church(1, participants)

    assert not any(issue["issue_type"] == "doubles_partner_unmatched" for issue in issues), issues


def test_team_validator_partial_partner_name_suggests_full_name(team_validator):
    """A unique short-name match should stay a WARNING with a suggested full name."""
    participants = [
        {
            **_make_participant(primary_sport=SPORT_TYPE["TENNIS"], primary_format="Mixed Double"),
            "participant_id": 1,
            "first_name": "Dean",
            "last_name": "Nguyen",
            "primary_partner": "Janice",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["TENNIS"], primary_format="Mixed Double"),
            "participant_id": 2,
            "first_name": "Janice",
            "last_name": "Vu",
            "primary_partner": "Dean Nguyen",
        },
    ]

    issues = team_validator.validate_church(1, participants)

    partner_issues = [issue for issue in issues if issue["issue_type"] == "doubles_partner_unmatched"]
    assert len(partner_issues) == 1
    assert partner_issues[0]["participant_id"] == 1
    assert partner_issues[0]["severity"] == VALIDATION_SEVERITY["WARNING"]
    assert "ambiguous; use full name" in partner_issues[0]["issue_description"]
    assert "perhaps Janice Vu" in partner_issues[0]["issue_description"]


def test_team_validator_partial_partner_name_lists_possible_matches(team_validator):
    """Multiple short-name matches should list the possible full-name candidates."""
    participants = [
        {
            **_make_participant(primary_sport=SPORT_TYPE["PICKLEBALL"], primary_format="Mixed Double"),
            "participant_id": 1,
            "first_name": "Dean",
            "last_name": "Nguyen",
            "primary_partner": "Janice",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["PICKLEBALL"], primary_format="Mixed Double"),
            "participant_id": 2,
            "first_name": "Janice",
            "last_name": "Vu",
            "primary_partner": "",
        },
        {
            **_make_participant(primary_sport=SPORT_TYPE["PICKLEBALL"], primary_format="Mixed Double"),
            "participant_id": 3,
            "first_name": "Janice",
            "last_name": "Nguyen",
            "primary_partner": "",
        },
    ]

    issues = team_validator.validate_church(1, participants)

    partner_issue = next(issue for issue in issues if issue["issue_type"] == "doubles_partner_unmatched")
    assert partner_issue["participant_id"] == 1
    assert "Possible matches:" in partner_issue["issue_description"]
    assert "Janice Vu" in partner_issue["issue_description"]
    assert "Janice Nguyen" in partner_issue["issue_description"]
