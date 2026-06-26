##### Begin of tests/test_group_assignment.py
# Tests for group_assignment.assign_people_to_church_team_groups()
# All tests are pure mock tests — no LIVE_TEST guard needed.
import os
import sys
import pytest
import pandas as pd
from unittest.mock import MagicMock

# Ensure the middleware package root is importable (mirrors conftest.py / pytest.ini)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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

    mock_cls = mocker.patch("group_assignment.ChMeetingsConnector")
    mock_cls.return_value.__enter__ = lambda s: connector
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)

    return connector


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
