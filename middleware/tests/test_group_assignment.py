##### Begin of tests/test_group_assignment.py
# Tests for group_assignment.assign_people_to_church_team_groups()
# All tests are pure mock tests — no LIVE_TEST guard needed.
import os
import sys
import pytest
import pandas as pd
import requests
from unittest.mock import MagicMock

# Ensure the middleware package root is importable (mirrors conftest.py / pytest.ini)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chmeetings.backend_connector import ChMeetingsReadError
from group_assignment import (
    assign_people_to_church_team_groups,
    audit_form_people,
    clear_team_groups,
    repair_form_people,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_person(person_id, church_code="RPC"):
    return {
        "id": person_id,
        "first_name": "Test",
        "last_name": f"Person{person_id}",
        "email": f"person{person_id}@test.com",
        "additional_fields": [{"field_name": "Church Team", "value": church_code}],
    }


def _individual_row(**overrides):
    row = {
        "First Name": "Brendan",
        "Last Name": "Nguyen",
        "Church Team": "SFV",
        "Email": "bnguyen0217@gmail.com",
        "Mobile Phone": "7142344207",
        "Gender": "Male",
        "My role is": "Athlete/Participant",
        "Birthdate": "02/17/2003",
        "Would the church pastor say that you belong to his church?": "Yes",
        "Age verification (by the date of Sports Fest)": "I am over 18 but under 35",
        "Submission Date": "06/12/2026",
        "Primary Sport": "Volleyball - Men Team",
        "Secondary Sport": "Unselected/NA",
        "Other Events": "",
        "Additional Info": "",
    }
    row.update(overrides)
    return row


def _blank_matched_person(person_id="3631503"):
    return {
        "id": person_id,
        "first_name": "Brendan",
        "last_name": "Nguyen",
        "email": "bnguyen0217@gmail.com",
        "mobile": "7142344207",
        "additional_fields": [
            {"field_id": 1282085, "field_name": "My role is", "field_type": "checkbox", "selected_option_ids": [], "value": ""},
            {"field_id": 1281851, "field_name": "Church Team", "field_type": "dropdown", "selected_option_id": None, "value": ""},
            {"field_id": 1281847, "field_name": "Primary Sport", "field_type": "dropdown", "selected_option_id": None, "value": ""},
            {"field_id": 1281848, "field_name": "Secondary Sport", "field_type": "dropdown", "selected_option_id": None, "value": ""},
        ],
    }


@pytest.fixture()
def mock_connector(mocker):
    """
    Patch ChMeetingsConnector so `with ChMeetingsConnector() as conn` returns
    a controllable mock.  Tests can override any attribute after getting the fixture.
    """
    connector = MagicMock()
    connector.authenticate.return_value = True
    connector.get_people.return_value = []
    connector.get_groups.return_value = []
    connector.get_group_people.return_value = []
    connector.add_person_to_group.return_value = True
    connector.remove_person_from_group.return_value = True
    connector.update_person.return_value = True

    def _get_person(person_id):
        for person in connector.get_people.return_value or []:
            if str(person.get("id")) == str(person_id):
                return person
        return None

    connector.get_person.side_effect = _get_person

    mock_cls = mocker.patch("group_assignment.ChMeetingsConnector")
    mock_cls.return_value.__enter__ = lambda s: connector
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)

    return connector


@pytest.fixture(autouse=True)
def mock_wp_connector(mocker):
    """Never let a test reach WordPress.

    ``repair_form_people`` reads the merged tombstones from WordPress when none
    are injected. By default that read returns no participants.
    """
    wp = MagicMock()
    wp.get_participants.return_value = []
    wp.last_get_participants_status = "ok"
    wp.total_participants = 0
    mock_cls = mocker.patch("group_assignment.WordPressConnector")
    mock_cls.return_value.__enter__ = lambda s: wp
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return wp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_assign_happy_path(mock_connector, mocker, tmp_path):
    """Two unassigned people → add_person_to_group called twice → returns True."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [
        _make_person("101", "RPC"),
        _make_person("102", "ORN"),
    ]
    mock_connector.get_groups.return_value = [
        {"id": "870578", "name": "Team RPC"},
        {"id": "872490", "name": "Team ORN"},
    ]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(dry_run=False)

    assert result is True
    assert mock_connector.add_person_to_group.call_count == 2
    mock_connector.add_person_to_group.assert_any_call("870578", "101")
    mock_connector.add_person_to_group.assert_any_call("872490", "102")

    audit_file = tmp_path / "church_team_assignments.xlsx"
    assert audit_file.exists(), "Audit xlsx must be written in live mode"


def test_assign_missing_group(mock_connector, mocker, tmp_path):
    """Church code XYZ has no matching group → warning, skipped, returns True (0 API failures)."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [_make_person("201", "XYZ")]
    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(dry_run=False)

    # missing_group is not an API failure — still returns True
    assert result is True
    mock_connector.add_person_to_group.assert_not_called()


def test_assign_dry_run(mock_connector, mocker, tmp_path):
    """dry_run=True → no API calls, audit xlsx still written."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [_make_person("301", "RPC")]
    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(dry_run=True)

    assert result is True
    mock_connector.add_person_to_group.assert_not_called()

    audit_file = tmp_path / "church_team_assignments.xlsx"
    assert audit_file.exists(), "Audit xlsx must be written even in dry-run mode"


def test_assign_partial_failure(mock_connector, mocker, tmp_path):
    """First add succeeds, second fails → returns False (failed > 0)."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [
        _make_person("401", "RPC"),
        _make_person("402", "RPC"),
    ]
    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = []
    mock_connector.add_person_to_group.side_effect = [True, False]

    result = assign_people_to_church_team_groups(dry_run=False)

    assert result is False
    assert mock_connector.add_person_to_group.call_count == 2


def test_assign_already_in_team(mock_connector, mocker, tmp_path):
    """People already in a team group are skipped — no API call made."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [_make_person("501", "RPC")]
    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    # Person 501 is already in the group
    mock_connector.get_group_people.return_value = [{"person_id": "501"}]

    result = assign_people_to_church_team_groups(dry_run=False)

    assert result is True
    mock_connector.add_person_to_group.assert_not_called()


def test_assign_hydrates_matched_existing_person_already_in_team(
    mock_connector, mocker, tmp_path
):
    """Matched current-season people are hydrated before the team-group skip."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    mock_connector.get_people.return_value = [_blank_matched_person()]
    mock_connector.get_groups.return_value = [{"id": "885442", "name": "Team SFV"}]
    mock_connector.get_group_people.return_value = [{"person_id": "3631503"}]

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.add_person_to_group.assert_not_called()
    mock_connector.update_person.assert_called_once()
    args, kwargs = mock_connector.update_person.call_args
    assert args[:3] == ("3631503", "Brendan", "Nguyen")
    assert kwargs["extra_person_data"] == mock_connector.get_people.return_value[0]
    fields_by_id = {field["field_id"]: field for field in args[3]}
    assert fields_by_id[1282085]["selected_option_ids"] == [199442]
    assert fields_by_id[1281851]["selected_option_id"] == 227692
    assert fields_by_id[1281847]["selected_option_id"] == 199334
    assert fields_by_id[1281848]["selected_option_id"] == 199352

    audit_file = tmp_path / "church_team_assignments.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    assert df.iloc[0]["Outcome"] == "already_in_team"
    assert df.iloc[0]["Hydration Outcome"] == "hydrated"
    assert "My role is" in df.iloc[0]["Hydrated Fields"]


def test_assign_hydrates_before_adding_to_team(mock_connector, mocker, tmp_path):
    """A matched ungrouped person is hydrated and then assigned to the team group."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    mock_connector.get_people.return_value = [_blank_matched_person()]
    mock_connector.get_groups.return_value = [{"id": "885442", "name": "Team SFV"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.update_person.assert_called_once()
    mock_connector.add_person_to_group.assert_called_once_with("885442", "3631503")


def test_assign_rechecks_fresh_person_before_hydration_to_avoid_drift(
    mock_connector, mocker, tmp_path
):
    """Fresh ChMeetings fields win over stale blank bulk-list fields."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    stale_person = _blank_matched_person()
    fresh_person = _blank_matched_person()
    fresh_person["additional_fields"] = [
        {
            "field_id": 1282085,
            "field_name": "My role is",
            "field_type": "checkbox",
            "selected_option_ids": [199447],
            "value": "Fan and Supporter",
        },
        {
            "field_id": 1281851,
            "field_name": "Church Team",
            "field_type": "dropdown",
            "selected_option_id": 227692,
            "value": "SFV",
        },
        {
            "field_id": 1281852,
            "field_name": "Would the team's Senior Pastor say that you belong to his church?",
            "field_type": "multiple_choice",
            "selected_option_id": 199355,
            "value": "Yes",
        },
        {
            "field_id": 1283264,
            "field_name": "Age verification (by the date of Sports Fest)",
            "field_type": "multiple_choice",
            "selected_option_id": 199606,
            "value": "I am over 18 but under 35",
        },
        {
            "field_id": 1281847,
            "field_name": "Primary Sport",
            "field_type": "dropdown",
            "selected_option_id": 199334,
            "value": "Volleyball - Men Team",
        },
        {
            "field_id": 1281848,
            "field_name": "Secondary Sport",
            "field_type": "dropdown",
            "selected_option_id": 199352,
            "value": "Unselected/NA",
        },
    ]

    mock_connector.get_people.return_value = [stale_person]
    mock_connector.get_person.side_effect = None
    mock_connector.get_person.return_value = fresh_person
    mock_connector.get_groups.return_value = [{"id": "885442", "name": "Team SFV"}]
    mock_connector.get_group_people.return_value = [{"person_id": "3631503"}]

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.get_person.assert_called_once_with("3631503")
    mock_connector.update_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()

    df = pd.read_excel(tmp_path / "church_team_assignments.xlsx")
    assert df.iloc[0]["Outcome"] == "already_in_team"
    assert df.iloc[0]["Hydration Outcome"] == "conflict"
    assert "Fan and Supporter" in df.iloc[0]["Hydration Conflicts"]


def test_assign_chm_id_filter_limits_hydration_and_assignment(
    mock_connector, mocker, tmp_path
):
    """Focused runs only process the requested ChMeetings IDs."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([
        _individual_row(),
        _individual_row(
            **{
                "First Name": "Other",
                "Last Name": "Person",
                "Email": "other@example.com",
                "Mobile Phone": "7145550100",
            }
        ),
    ]).to_excel(source_file, index=False)

    other_person = _blank_matched_person("9999999")
    other_person["first_name"] = "Other"
    other_person["last_name"] = "Person"
    other_person["email"] = "other@example.com"
    other_person["mobile"] = "7145550100"
    mock_connector.get_people.return_value = [_blank_matched_person(), other_person]
    mock_connector.get_groups.return_value = [{"id": "885442", "name": "Team SFV"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
        chm_ids=["3631503"],
    )

    assert result is True
    mock_connector.update_person.assert_called_once()
    assert mock_connector.update_person.call_args.args[0] == "3631503"
    mock_connector.add_person_to_group.assert_called_once_with("885442", "3631503")


def test_assign_church_code_filter_limits_to_source_church(
    mock_connector, mocker, tmp_path
):
    """Focused church runs only inspect current-season rows for that church."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([
        _individual_row(**{"Church Team": "LBC"}),
        _individual_row(
            **{
                "First Name": "Other",
                "Last Name": "Person",
                "Church Team": "SFV",
                "Email": "other@example.com",
                "Mobile Phone": "7145550100",
            }
        ),
    ]).to_excel(source_file, index=False)

    lbc_person = _blank_matched_person()
    other_person = _blank_matched_person("9999999")
    other_person["first_name"] = "Other"
    other_person["last_name"] = "Person"
    other_person["email"] = "other@example.com"
    other_person["mobile"] = "7145550100"

    mock_connector.get_people.return_value = [lbc_person, other_person]
    mock_connector.get_groups.return_value = [
        {"id": "885441", "name": "Team LBC"},
        {"id": "885442", "name": "Team SFV"},
    ]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(
        dry_run=True,
        source_file=str(source_file),
        church_codes=["lbc"],
    )

    assert result is True
    mock_connector.get_person.assert_called_once_with("3631503")
    mock_connector.update_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()

    df = pd.read_excel(tmp_path / "church_team_assignments.xlsx")
    assert len(df) == 1
    assert df.iloc[0]["Church Code"] == "LBC"
    assert df.iloc[0]["Target Group"] == "Team LBC"
    assert df.iloc[0]["Outcome"] == "dry_run"
    assert df.iloc[0]["Hydration Outcome"] == "would_hydrate"


def test_assign_hydration_dry_run_makes_no_update_call(
    mock_connector, mocker, tmp_path
):
    """dry_run=True reports hydration without calling update_person."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    mock_connector.get_people.return_value = [_blank_matched_person()]
    mock_connector.get_groups.return_value = [{"id": "885442", "name": "Team SFV"}]
    mock_connector.get_group_people.return_value = [{"person_id": "3631503"}]

    result = assign_people_to_church_team_groups(
        dry_run=True,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.update_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()
    df = pd.read_excel(tmp_path / "church_team_assignments.xlsx")
    assert df.iloc[0]["Hydration Outcome"] == "would_hydrate"


def test_assign_hydration_preserves_nonblank_conflicting_role(
    mock_connector, mocker, tmp_path
):
    """Conflicting nonblank ChMeetings fields are audited but not overwritten."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    person = _blank_matched_person()
    person["additional_fields"][0] = {
        "field_id": 1282085,
        "field_name": "My role is",
        "field_type": "checkbox",
        "selected_option_ids": [199447],
        "value": "Fan and Supporter",
    }
    mock_connector.get_people.return_value = [person]
    mock_connector.get_groups.return_value = [{"id": "885442", "name": "Team SFV"}]
    mock_connector.get_group_people.return_value = [{"person_id": "3631503"}]

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.update_person.assert_called_once()
    update_fields = mock_connector.update_person.call_args.args[3]
    role_field = next(field for field in update_fields if field["field_id"] == 1282085)
    assert role_field["selected_option_ids"] == [199447]
    df = pd.read_excel(tmp_path / "church_team_assignments.xlsx")
    assert df.iloc[0]["Hydration Outcome"] == "hydrated_with_conflicts"
    assert "Fan and Supporter" in df.iloc[0]["Hydration Conflicts"]


def test_assign_hydration_noops_when_profile_already_matches(
    mock_connector, mocker, tmp_path
):
    """Already-populated matching source data is idempotent."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    person = _blank_matched_person()
    person["additional_fields"] = [
        {
            "field_id": 1282085,
            "field_name": "My role is",
            "field_type": "checkbox",
            "selected_option_ids": [199442],
            "value": "Athlete/Participant",
        },
        {
            "field_id": 1281851,
            "field_name": "Church Team",
            "field_type": "dropdown",
            "selected_option_id": 227692,
            "value": "SFV",
        },
        {
            "field_id": 1281847,
            "field_name": "Primary Sport",
            "field_type": "dropdown",
            "selected_option_id": 199334,
            "value": "Volleyball - Men Team",
        },
        {
            "field_id": 1281848,
            "field_name": "Secondary Sport",
            "field_type": "dropdown",
            "selected_option_id": 199352,
            "value": "Unselected/NA",
        },
        {
            "field_id": 1281852,
            "field_name": "Would the team's Senior Pastor say that you belong to his church?",
            "field_type": "multiple_choice",
            "selected_option_id": 199355,
            "value": "Yes",
        },
        {
            "field_id": 1283264,
            "field_name": "Age verification (by the date of Sports Fest)",
            "field_type": "multiple_choice",
            "selected_option_id": 199606,
            "value": "I am over 18 but under 35",
        },
    ]
    mock_connector.get_people.return_value = [person]
    mock_connector.get_groups.return_value = [{"id": "885442", "name": "Team SFV"}]
    mock_connector.get_group_people.return_value = [{"person_id": "3631503"}]

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.update_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()


def test_assign_no_church_code(mock_connector, mocker, tmp_path):
    """Person with no church code is ignored."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [
        {
            "id": "601",
            "first_name": "No",
            "last_name": "Code",
            "email": "nocode@test.com",
            "additional_fields": [],  # no Church Team field
        }
    ]
    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(dry_run=False)

    assert result is True
    mock_connector.add_person_to_group.assert_not_called()


def test_assign_auth_failure(mock_connector, mocker, tmp_path):
    """Authentication failure → returns False immediately."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)
    mock_connector.authenticate.return_value = False

    result = assign_people_to_church_team_groups(dry_run=False)

    assert result is False
    mock_connector.get_people.assert_not_called()


def test_assign_source_export_filters_historical_people(mock_connector, mocker, tmp_path):
    """A source export should limit assignment to current-season rows only."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([
        {
            "First Name": "Sam",
            "Last Name": "Le",
            "Church Team": "RPC",
            "Email": "samuel93le@yahoo.com",
            "Mobile Phone": "562-519-9430",
        }
    ]).to_excel(source_file, index=False)

    mock_connector.get_people.return_value = [
        {
            "id": "3318927",
            "first_name": "Sam",
            "last_name": "Le",
            "email": "samuel93le@yahoo.com",
            "mobile": "5625199430",
            "additional_fields": [{"field_name": "Church Team", "value": "RPC"}],
        },
        {
            "id": "3139537",
            "first_name": "Timmy",
            "last_name": "Ho",
            "email": "timmyho@gmail.com",
            "mobile": "7144020871",
            "additional_fields": [{"field_name": "Church Team", "value": "RPC"}],
        },
    ]
    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.add_person_to_group.assert_called_once_with("870578", "3318927")


def test_assign_source_export_supplies_missing_profile_church_code(
    mock_connector, mocker, tmp_path
):
    """A unique email match should route a registrant whose profile field is blank."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([
        {
            "First Name": "PETER",
            "Last Name": "PHAN",
            "Church Team": "ORN",
            "Email": "pphan0703@gmail.com",
            "Mobile Phone": "714-624-1226",
        }
    ]).to_excel(source_file, index=False)

    mock_connector.get_people.return_value = [
        {
            "id": "3632793",
            "first_name": "Phuoc",
            "last_name": "Phan",
            "email": "pphan0703@gmail.com",
            "mobile": "7146241226",
            "additional_fields": [],
        },
    ]
    mock_connector.get_groups.return_value = [{"id": "872490", "name": "Team ORN"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.add_person_to_group.assert_called_once_with("872490", "3632793")


def test_assign_source_export_does_not_use_name_only_for_missing_profile_code(
    mock_connector, mocker, tmp_path
):
    """A common-name match alone is not strong enough to assign a team."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([
        {
            "First Name": "Andrew",
            "Last Name": "Nguyen",
            "Church Team": "TLC",
            "Email": "current@example.com",
            "Mobile Phone": "714-555-0100",
        }
    ]).to_excel(source_file, index=False)

    mock_connector.get_people.return_value = [
        {
            "id": "999",
            "first_name": "Andrew",
            "last_name": "Nguyen",
            "email": "different@example.com",
            "mobile": "7145550199",
            "additional_fields": [],
        },
    ]
    mock_connector.get_groups.return_value = [{"id": "123", "name": "Team TLC"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.add_person_to_group.assert_not_called()


def test_audit_form_people_reports_missing_chmeetings_person(mocker, tmp_path):
    """Form rows without visible ChMeetings People records should be audited."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([
        {
            "First Name": "Sayana",
            "Last Name": "Lee",
            "Church Team": "RPC",
            "Email": "sayanaoaklee@gmail.com",
            "Mobile Phone": "7143217013",
            "My role is": "Athlete/Participant",
            "Submission Date": "06/15/2026",
            "Primary Sport": "Volleyball - Women Team",
            "Secondary Sport": "",
            "Other Events": "Track & Field, Soccer - Coed Exhibition",
        },
        {
            "First Name": "Sam",
            "Last Name": "Le",
            "Church Team": "RPC",
            "Email": "sam@example.com",
            "Mobile Phone": "5625199430",
            "My role is": "Athlete/Participant",
            "Submission Date": "05/03/2026",
            "Primary Sport": "Unselected/NA",
            "Secondary Sport": "",
            "Other Events": "Track & Field",
        },
    ]).to_excel(source_file, index=False)

    result = audit_form_people(
        str(source_file),
        people=[
            {
                "id": "3318927",
                "first_name": "Sam",
                "last_name": "Le",
                "email": "sam@example.com",
                "mobile": "5625199430",
            }
        ],
    )

    assert result is True
    audit_file = tmp_path / "form_people_audit.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    sayana = df[df["Email"] == "sayanaoaklee@gmail.com"].iloc[0]
    assert sayana["Match Status"] == "missing_person"
    assert sayana["Primary Sport"] == "Volleyball - Women Team"
    sam = df[df["Email"] == "sam@example.com"].iloc[0]
    assert sam["Match Status"] == "matched_email"
    assert str(int(sam["Matched ChMeetings IDs"])) == "3318927"


def test_assign_source_export_writes_form_people_audit_even_when_no_assignment_needed(
    mock_connector, mocker, tmp_path
):
    """assign-groups --file should surface stranded form rows even if no team adds run."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([
        {
            "First Name": "Sayana",
            "Last Name": "Lee",
            "Church Team": "RPC",
            "Email": "sayanaoaklee@gmail.com",
            "Mobile Phone": "7143217013",
        }
    ]).to_excel(source_file, index=False)

    mock_connector.get_people.return_value = []
    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(
        dry_run=False,
        source_file=str(source_file),
    )

    assert result is True
    mock_connector.add_person_to_group.assert_not_called()
    audit_file = tmp_path / "form_people_audit.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    assert df.iloc[0]["Match Status"] == "missing_person"


def test_clear_team_groups_dry_run(mock_connector, mocker, tmp_path):
    """dry_run=True previews removals and ignores non-Team groups."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_groups.return_value = [
        {"id": "870578", "name": "Team RPC"},
        {"id": "999999", "name": "2026 Sports Fest"},
    ]
    mock_connector.get_group_people.side_effect = [
        [
            {"person_id": "701", "first_name": "Amy", "last_name": "Nguyen", "email": "amy@test.com"},
            {"person_id": "702", "first_name": "Ben", "last_name": "Tran", "email": "ben@test.com"},
        ]
    ]

    result = clear_team_groups(dry_run=True, execute=False)

    assert result is True
    mock_connector.remove_person_from_group.assert_not_called()

    audit_file = tmp_path / "team_group_clearing_audit.xlsx"
    assert audit_file.exists(), "Audit xlsx must be written in dry-run mode"


def test_clear_team_groups_scoped_execute(mock_connector, mocker, tmp_path):
    """--church-code scopes the run to one Team XXX group in live mode."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_groups.return_value = [
        {"id": "870578", "name": "Team RPC"},
        {"id": "872490", "name": "Team ORN"},
    ]
    mock_connector.get_group_people.return_value = [
        {"person_id": "801", "first_name": "Test", "last_name": "Person801", "email": "p801@test.com"},
    ]

    result = clear_team_groups(church_code="rpc", dry_run=False, execute=True)

    assert result is True
    mock_connector.remove_person_from_group.assert_called_once_with(
        "870578", "801", not_found_ok=True
    )


def test_clear_team_groups_partial_failure(mock_connector, mocker, tmp_path):
    """A failed removal should make the command return False."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = [
        {"person_id": "901", "first_name": "A", "last_name": "One", "email": "a@test.com"},
        {"person_id": "902", "first_name": "B", "last_name": "Two", "email": "b@test.com"},
    ]
    mock_connector.remove_person_from_group.side_effect = [True, False]

    result = clear_team_groups(dry_run=False, execute=True)

    assert result is False
    assert mock_connector.remove_person_from_group.call_count == 2


def test_clear_team_groups_orphaned_membership_404_is_nonfatal(mock_connector, mocker, tmp_path):
    """A DELETE 404 should be treated as already absent, not a failed cleanup."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_groups.return_value = [{"id": "885446", "name": "Team SGV"}]
    mock_connector.get_group_people.return_value = [
        {"person_id": "3616813", "first_name": "Ghost", "last_name": "Member", "email": "ghost@test.com"},
    ]

    def fake_remove(group_id, person_id, not_found_ok=False):
        mock_connector.last_group_membership_delete_status = "already_absent"
        return True

    mock_connector.remove_person_from_group.side_effect = fake_remove

    result = clear_team_groups(church_code="SGV", dry_run=False, execute=True)

    assert result is True
    mock_connector.remove_person_from_group.assert_called_once_with("885446", "3616813", not_found_ok=True)


def test_clear_team_groups_empty_group(mock_connector, mocker, tmp_path):
    """Already-empty Team XXX groups should be treated as a clean no-op."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    mock_connector.get_group_people.return_value = []

    result = clear_team_groups(dry_run=False, execute=True)

    assert result is True
    mock_connector.remove_person_from_group.assert_not_called()


def test_clear_team_groups_requires_execute_for_live_mode(mock_connector, mocker, tmp_path):
    """Live mode without --execute should be rejected before any API work."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    result = clear_team_groups(dry_run=False, execute=False)

    assert result is False
    mock_connector.authenticate.assert_not_called()


def test_assign_other_routed_to_lost_and_found(mock_connector, mocker, tmp_path):
    """Person with church_code 'Other' is assigned to the Lost and Found group."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [_make_person("501", "Other")]
    mock_connector.get_groups.return_value = [
        {"id": "999001", "name": "Lost and Found"},
        {"id": "870578", "name": "Team RPC"},
    ]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(dry_run=False)

    assert result is True
    mock_connector.add_person_to_group.assert_called_once_with("999001", "501")

    audit_file = tmp_path / "church_team_assignments.xlsx"
    assert audit_file.exists()
    df = __import__("pandas").read_excel(audit_file)
    assert df.iloc[0]["Target Group"] == "Lost and Found"
    assert df.iloc[0]["Outcome"] == "added"


def test_assign_other_missing_lost_and_found_group_warns_and_skips(mock_connector, mocker, tmp_path):
    """Person with church_code 'Other' but no Lost and Found group → warning + skip, no API call."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    mock_connector.get_people.return_value = [_make_person("502", "Other")]
    mock_connector.get_groups.return_value = [
        {"id": "870578", "name": "Team RPC"},
        # "Lost and Found" intentionally absent
    ]
    mock_connector.get_group_people.return_value = []

    result = assign_people_to_church_team_groups(dry_run=False)

    # missing_group is not an API failure — returns True
    assert result is True
    mock_connector.add_person_to_group.assert_not_called()

    audit_file = tmp_path / "church_team_assignments.xlsx"
    assert audit_file.exists()
    df = __import__("pandas").read_excel(audit_file)
    assert df.iloc[0]["Outcome"] == "missing_group"


# ---------------------------------------------------------------------------
# repair_form_people tests
# ---------------------------------------------------------------------------

def _sayana_row():
    """Minimal valid form row for Sayana Lee (missing person scenario)."""
    return {
        "First Name": "Sayana",
        "Last Name": "Lee",
        "Church Team": "RPC",
        "Email": "sayanaoaklee@gmail.com",
        "Mobile Phone": "7143217013",
        "Gender": "Female",
        "My role is": "Athlete/Participant",
        "Birthdate": "10/05/2002",
        "Would the church pastor say that you belong to his church?": "Yes",
        "Age verification (by the date of Sports Fest)": "I am over 18 but under 35",
        "Name of my parents or legal guardian": "",
        "Email of my parents or legal guardian": "",
        "Cell phone of my parents or legal guardian": "",
        "Submission Date": "06/15/2026",
        "Primary Sport": "Volleyball - Women Team",
        "Secondary Sport": "",
        "Other Events": "Track & Field, Soccer - Coed Exhibition",
        "Additional Info": "",
    }


def test_repair_form_people_dry_run_no_api_calls(mock_connector, mocker, tmp_path):
    """dry_run=True → no create_person or add_person_to_group calls; audit xlsx written."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_sayana_row()]).to_excel(source_file, index=False)

    counts = repair_form_people(
        str(source_file),
        dry_run=True,
        people=[],
        groups=[{"id": "870578", "name": "Team RPC"}],
    )

    assert counts["skipped"] == 1
    assert counts["created"] == 0
    assert counts["errored"] == 0
    mock_connector.create_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()

    audit_file = tmp_path / "form_people_repair.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    assert df.iloc[0]["Outcome"] == "dry_run"


def test_repair_form_people_execute_creates_missing_person(mock_connector, mocker, tmp_path):
    """execute=True, missing person → create_person called, person added to group."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_sayana_row()]).to_excel(source_file, index=False)

    mock_connector.create_person.return_value = {
        "id": "999001",
        "first_name": "Sayana",
        "last_name": "Lee",
    }

    counts = repair_form_people(
        str(source_file),
        dry_run=False,
        execute=True,
        people=[],
        groups=[{"id": "870578", "name": "Team RPC"}],
    )

    assert counts["created"] == 1
    assert counts["errored"] == 0
    mock_connector.create_person.assert_called_once()
    call_kwargs = mock_connector.create_person.call_args
    assert call_kwargs.kwargs["first_name"] == "Sayana"
    assert call_kwargs.kwargs["last_name"] == "Lee"
    assert call_kwargs.kwargs["extra_fields"] == {
        "gender": "Female",
        "birth_date": "2002-10-05",
    }
    fields_by_id = {
        field["field_id"]: field
        for field in call_kwargs.kwargs["additional_fields"]
    }
    assert fields_by_id[1281851]["selected_option_id"] == 199354  # Church Team: RPC
    assert fields_by_id[1282085]["selected_option_ids"] == [199442]  # Athlete/Participant
    assert fields_by_id[1281852]["selected_option_id"] == 199355  # Member: Yes
    assert fields_by_id[1283264]["selected_option_id"] == 199606  # Over 18 but under 35
    assert fields_by_id[1281847]["selected_option_id"] == 199335  # VB Women
    assert sorted(fields_by_id[1281849]["selected_option_ids"]) == [199341, 329599]
    mock_connector.add_person_to_group.assert_called_once_with("870578", "999001")

    audit_file = tmp_path / "form_people_repair.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    assert df.iloc[0]["Outcome"] == "created"


def test_repair_form_people_execute_skips_matched_person(mock_connector, mocker, tmp_path):
    """execute=True, person already in ChMeetings → no create or group-add side effect."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_sayana_row()]).to_excel(source_file, index=False)

    existing_person = {
        "id": "3318927",
        "first_name": "Sayana",
        "last_name": "Lee",
        "email": "sayanaoaklee@gmail.com",
        "mobile": "7143217013",
    }

    counts = repair_form_people(
        str(source_file),
        dry_run=False,
        execute=True,
        people=[existing_person],
        groups=[{"id": "870578", "name": "Team RPC"}],
    )

    assert counts["skipped_matched"] == 1
    assert counts["created"] == 0
    mock_connector.create_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()

    audit_file = tmp_path / "form_people_repair.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    assert df.iloc[0]["Outcome"] == "skipped_matched"


def test_repair_form_people_blocks_unmappable_church_code(mock_connector, mocker, tmp_path):
    """execute=True, unrecognised church code → blocked, no API calls."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    row = _sayana_row()
    row["Church Team"] = "XYZ"
    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([row]).to_excel(source_file, index=False)

    counts = repair_form_people(
        str(source_file),
        dry_run=False,
        execute=True,
        people=[],
        groups=[{"id": "870578", "name": "Team RPC"}],
    )

    assert counts["blocked"] == 1
    assert counts["created"] == 0
    mock_connector.create_person.assert_not_called()

    audit_file = tmp_path / "form_people_repair.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    assert df.iloc[0]["Outcome"] == "blocked"


def test_repair_form_people_chm_email_filter_limits_to_one_row(mock_connector, mocker, tmp_path):
    """--chm-email restricts processing to only the matching row."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    row2 = _sayana_row()
    row2["First Name"] = "Sam"
    row2["Last Name"] = "Le"
    row2["Email"] = "samuel93le@yahoo.com"
    pd.DataFrame([_sayana_row(), row2]).to_excel(source_file, index=False)

    counts = repair_form_people(
        str(source_file),
        dry_run=True,
        chm_email="sayanaoaklee@gmail.com",
        people=[],
        groups=[{"id": "870578", "name": "Team RPC"}],
    )

    assert counts["skipped"] == 1
    audit_file = tmp_path / "form_people_repair.xlsx"
    assert audit_file.exists()
    df = pd.read_excel(audit_file)
    assert len(df) == 1
    assert df.iloc[0]["Email"] == "sayanaoaklee@gmail.com"


def test_repair_form_people_blocks_duplicate_source_submissions(mock_connector, mocker, tmp_path):
    """Duplicate missing form identities require human review before creation."""
    mocker.patch("group_assignment.DATA_DIR", tmp_path)

    source_file = tmp_path / "individual.xlsx"
    row1 = _sayana_row()
    row1["First Name"] = "Kyle"
    row1["Last Name"] = "Tran"
    row1["Email"] = "kyletran3815@gmail.com"
    row1["Church Team"] = "ORN"
    row2 = row1.copy()
    row2["Church Team"] = "GLA"
    pd.DataFrame([row1, row2]).to_excel(source_file, index=False)

    counts = repair_form_people(
        str(source_file),
        dry_run=False,
        execute=True,
        people=[],
        groups=[
            {"id": "872490", "name": "Team ORN"},
            {"id": "870999", "name": "Team GLA"},
        ],
    )

    assert counts["blocked"] == 2
    assert counts["created"] == 0
    mock_connector.create_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()

    audit_file = tmp_path / "form_people_repair.xlsx"
    df = pd.read_excel(audit_file)
    assert set(df["Outcome"]) == {"blocked_duplicate_source"}


# ---------------------------------------------------------------------------
# ChMeetingsReadError handling — a mid-pagination ChMeetings read failure must
# not crash these operator commands (daily-run.bat runs assign-groups
# unattended); it must be logged and reported as a clean failure instead.
# ---------------------------------------------------------------------------

def test_assign_people_to_church_team_groups_returns_false_on_get_people_read_error(mock_connector):
    """A mid-pagination ChMeetings read failure must be a clean False, not a crash."""
    mock_connector.get_people.side_effect = ChMeetingsReadError("page 2 connection dropped")

    result = assign_people_to_church_team_groups(dry_run=False)

    assert result is False
    mock_connector.get_groups.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()


def test_audit_form_people_returns_false_on_get_people_read_error(mock_connector, tmp_path):
    """A mid-pagination ChMeetings read failure must be a clean False, not a crash."""
    mock_connector.get_people.side_effect = ChMeetingsReadError("page 2 connection dropped")

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    result = audit_form_people(str(source_file))

    assert result is False


def test_repair_form_people_returns_empty_on_get_people_read_error(mock_connector, tmp_path):
    """A mid-pagination ChMeetings read failure must be a clean empty result, not a crash."""
    mock_connector.get_people.side_effect = ChMeetingsReadError("page 2 connection dropped")

    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_individual_row()]).to_excel(source_file, index=False)

    counts = repair_form_people(str(source_file), dry_run=True)

    assert counts["created"] == 0
    assert counts["linked"] == 0
    mock_connector.create_person.assert_not_called()


# ---------------------------------------------------------------------------
# repair_form_people: merged-identity guard (#388)
# ---------------------------------------------------------------------------

def _tombstone(participant_id="501", chm_id="100", **overrides):
    """A WordPress participant retired by apply-aliases (approval_status=merged)."""
    participant = {
        "participant_id": participant_id,
        "chmeetings_id": chm_id,
        "first_name": "Sayana",
        "last_name": "Lee",
        "email": "old.address@example.com",
        "phone": "555-000-1111",
        "birthdate": "1999-01-01",
        "approval_status": "merged",
    }
    participant.update(overrides)
    return participant


def _repair(tmp_path, mocker, rows, *, dry_run=False, tombstones=None, **kwargs):
    mocker.patch("group_assignment.DATA_DIR", tmp_path)
    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame(rows).to_excel(source_file, index=False)
    counts = repair_form_people(
        str(source_file),
        dry_run=dry_run,
        execute=not dry_run,
        people=[],
        groups=[{"id": "870578", "name": "Team RPC"}],
        merged_tombstones=tombstones,
        **kwargs,
    )
    audit_file = tmp_path / "form_people_repair.xlsx"
    audit = pd.read_excel(audit_file, dtype=str).fillna("") if audit_file.exists() else None
    return counts, audit


def _assert_nothing_created(mock_connector):
    mock_connector.create_person.assert_not_called()
    mock_connector.add_person_to_group.assert_not_called()


def test_repair_form_people_blocks_merged_identity_on_email_and_name(mock_connector, mocker, tmp_path):
    tombstone = _tombstone(email="SayanaOakLee@gmail.com", phone="", birthdate="")

    counts, audit = _repair(tmp_path, mocker, [_sayana_row()], tombstones=[tombstone])

    assert counts["blocked"] == 1
    assert counts["blocked_merged_identity"] == 1
    assert counts["created"] == 0
    _assert_nothing_created(mock_connector)
    row = audit.iloc[0]
    assert row["Outcome"] == "blocked_merged_identity"
    assert "participant_id=501" in row["Outcome Detail"]
    assert "ChMeetings ID 100" in row["Outcome Detail"]
    assert "email, name" in row["Outcome Detail"]
    assert (
        "Check whether this is the merged person before creating. "
        "If it is, add an alias instead."
    ) in row["Outcome Detail"]


def test_repair_form_people_blocks_merged_identity_on_phone_and_birthdate(mock_connector, mocker, tmp_path):
    tombstone = _tombstone(
        first_name="Different", last_name="Spelling",
        email="someone.else@example.com", phone="(714) 321-7013", birthdate="2002-10-05",
    )

    counts, audit = _repair(tmp_path, mocker, [_sayana_row()], tombstones=[tombstone])

    assert counts["blocked_merged_identity"] == 1
    assert counts["created"] == 0
    _assert_nothing_created(mock_connector)
    assert audit.iloc[0]["Outcome"] == "blocked_merged_identity"
    assert "birthdate, phone" in audit.iloc[0]["Outcome Detail"]


def test_repair_form_people_creates_when_no_tombstone_matches(mock_connector, mocker, tmp_path):
    mock_connector.create_person.return_value = {"id": "999001"}
    unrelated = _tombstone(
        first_name="Nobody", last_name="Else", email="nobody@example.com",
        phone="555-999-0000", birthdate="1980-02-02",
    )
    # A live (not merged) participant with the same identity is not a tombstone.
    live_twin = _tombstone(participant_id="502", approval_status="pending",
                           email="sayanaoaklee@gmail.com", phone="7143217013",
                           birthdate="2002-10-05")

    counts, audit = _repair(tmp_path, mocker, [_sayana_row()], tombstones=[unrelated, live_twin])

    assert counts["created"] == 1
    assert counts["blocked"] == 0
    mock_connector.create_person.assert_called_once()
    mock_connector.add_person_to_group.assert_called_once_with("870578", "999001")
    assert audit.iloc[0]["Outcome"] == "created"
    assert "Note:" not in audit.iloc[0]["Outcome Detail"]


def test_repair_form_people_sibling_sharing_parent_contact_is_created_with_note(mock_connector, mocker, tmp_path):
    """A younger sibling shares the parent's email and phone with an older sibling's tombstone."""
    mock_connector.create_person.return_value = {"id": "999001"}
    older_sibling = _tombstone(
        participant_id="777", chm_id="321", first_name="Khoa", last_name="Lee",
        email="sayanaoaklee@gmail.com", phone="714-321-7013", birthdate="1996-03-03",
    )

    counts, audit = _repair(tmp_path, mocker, [_sayana_row()], tombstones=[older_sibling])

    assert counts["created"] == 1
    assert counts["blocked"] == 0
    mock_connector.create_person.assert_called_once()
    row = audit.iloc[0]
    assert row["Outcome"] == "created"
    assert "participant_id=777" in row["Outcome Detail"]
    assert "ChMeetings ID 321" in row["Outcome Detail"]
    assert "email, phone" in row["Outcome Detail"]


def test_repair_form_people_dry_run_reports_blocked_rows_and_mutates_nothing(
    mock_connector, mock_wp_connector, mocker, tmp_path
):
    blocked_row = _sayana_row()
    free_row = _sayana_row()
    free_row.update({
        "First Name": "Minh", "Last Name": "Tran", "Email": "minh.tran@example.com",
        "Mobile Phone": "5625550123", "Birthdate": "03/04/2001",
    })
    mock_wp_connector.get_participants.return_value = [
        _tombstone(email="sayanaoaklee@gmail.com"),
        _tombstone(participant_id="900", approval_status="pending", first_name="Minh",
                   last_name="Tran", email="minh.tran@example.com"),
    ]

    # No injected tombstones: this goes through the WordPress read.
    counts, audit = _repair(tmp_path, mocker, [blocked_row, free_row], dry_run=True)

    assert counts["blocked_merged_identity"] == 1
    assert counts["dry_run"] == 1
    assert counts["created"] == 0
    _assert_nothing_created(mock_connector)
    assert list(audit["Outcome"]) == ["blocked_merged_identity", "dry_run"]
    # The only WordPress call is the participants read.
    assert {call[0] for call in mock_wp_connector.method_calls} == {"get_participants"}


@pytest.mark.parametrize("failure", ["exception", "status_failed", "incomplete"])
def test_repair_form_people_refuses_whole_run_when_wordpress_read_fails(
    mock_connector, mock_wp_connector, mocker, tmp_path, failure
):
    if failure == "exception":
        mock_wp_connector.get_participants.side_effect = requests.ConnectionError("down")
    elif failure == "status_failed":
        def _failed(params):
            mock_wp_connector.last_get_participants_status = "failed"
            return []
        mock_wp_connector.get_participants.side_effect = _failed
    else:
        mock_wp_connector.get_participants.return_value = [_tombstone()]
        mock_wp_connector.total_participants = 250  # WordPress says more exist than were returned

    counts, audit = _repair(tmp_path, mocker, [_sayana_row()])

    assert counts["created"] == 0
    assert counts["errored"] == 1
    _assert_nothing_created(mock_connector)
    assert audit is None  # a refused run writes no repair workbook


def test_repair_form_people_refuses_run_when_wordpress_cannot_be_reached(mock_connector, mocker, tmp_path):
    mocker.patch("group_assignment.WordPressConnector", side_effect=RuntimeError("no credentials"))

    counts, _ = _repair(tmp_path, mocker, [_sayana_row()])

    assert counts["created"] == 0
    assert counts["errored"] == 1
    _assert_nothing_created(mock_connector)


def test_repair_form_people_wordpress_not_read_when_nothing_is_missing(
    mock_connector, mock_wp_connector, mocker, tmp_path
):
    mocker.patch("group_assignment.DATA_DIR", tmp_path)
    source_file = tmp_path / "individual.xlsx"
    pd.DataFrame([_sayana_row()]).to_excel(source_file, index=False)
    existing = {"id": "3318927", "first_name": "Sayana", "last_name": "Lee",
                "email": "sayanaoaklee@gmail.com", "mobile": "7143217013"}

    counts = repair_form_people(
        str(source_file), dry_run=False, execute=True, people=[existing],
        groups=[{"id": "870578", "name": "Team RPC"}],
    )

    assert counts["skipped_matched"] == 1
    mock_wp_connector.get_participants.assert_not_called()


def test_repair_form_people_merged_match_ignores_diacritics_but_shows_original_spelling(
    mock_connector, mocker, tmp_path
):
    row = _sayana_row()
    row.update({"First Name": "Duc", "Last Name": "Pham", "Email": "ducpham@example.com",
                "Mobile Phone": "", "Birthdate": ""})
    tombstone = _tombstone(first_name="Đức", last_name="Phạm",
                           email="ducpham@example.com", phone="", birthdate="")

    counts, audit = _repair(tmp_path, mocker, [row], tombstones=[tombstone])

    assert counts["blocked_merged_identity"] == 1
    _assert_nothing_created(mock_connector)
    out = audit.iloc[0]
    # The form row and the tombstone are each shown as registered.
    assert (out["First Name"], out["Last Name"]) == ("Duc", "Pham")
    assert "Đức Phạm" in out["Outcome Detail"]
