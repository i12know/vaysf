##### Begin of tests/test_group_assignment.py
# Tests for group_assignment.assign_people_to_church_team_groups()
# All tests are pure mock tests — no LIVE_TEST guard needed.
import os
import sys
import pytest
from unittest.mock import MagicMock

# Ensure the middleware package root is importable (mirrors conftest.py / pytest.ini)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from group_assignment import assign_people_to_church_team_groups, clear_team_groups


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
