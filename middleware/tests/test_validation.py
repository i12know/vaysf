# tests/test_validation.py
# version 1.0.3
# author: Claude 3.7, Bumble & Grok 3
import os
import json
import pytest
from datetime import datetime
from validation.models import Participant, RulesManager
from validation.individual_validator import IndividualValidator
from loguru import logger
from config import Config
from config import (SPORT_TYPE, SPORT_UNSELECTED, DEFAULT_SPORT, 
                   VALIDATION_SEVERITY, AGE_RESTRICTIONS)

@pytest.fixture
def rules_manager():
    """Fixture for RulesManager."""
    return RulesManager(collection="SUMMER_2025")

@pytest.fixture
def validator():
    """Fixture for IndividualValidator."""
    return IndividualValidator(collection="SUMMER_2025")

def test_rules_manager_loads_rules(rules_manager):
    """Test that RulesManager loads rules correctly."""
    assert len(rules_manager.rules) > 0, "Rules should be loaded"
    assert any(r.get("rule_type") == "age" for r in rules_manager.rules), "Should have age rules"
    assert any(r.get("rule_type") == "gender" for r in rules_manager.rules), "Should have gender rules"
    assert any(r.get("rule_type") == "photo" for r in rules_manager.rules), "Should have photo rules"
    assert any(r.get("rule_type") == "consent" for r in rules_manager.rules), "Should have consent rules"

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
            "primary_sport": additional_fields.get("Primary Sport", SPORT_TYPE["BIBLE_CHALLENGE"]),
            "secondary_sport": additional_fields.get("Secondary Sport", "Pickleball - Mixed Doubles"),
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
            "primary_sport": additional_fields.get("Primary Sport", SPORT_TYPE["BIBLE_CHALLENGE"]),
            "secondary_sport": additional_fields.get("Secondary Sport", "Pickleball - Mixed Doubles"),
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
