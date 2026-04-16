##### Begin of tests/test_group_assignment.py
# Tests for group_assignment.assign_people_to_church_team_groups()
# All tests are pure mock tests — no LIVE_TEST guard needed.
import os
import sys
import pytest
from unittest.mock import MagicMock

# Ensure the middleware package root is importable (mirrors conftest.py / pytest.ini)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from group_assignment import assign_people_to_church_team_groups


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
