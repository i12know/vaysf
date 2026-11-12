"""audit-team-groups and the person alias map (PR #387 finding 6)."""

from unittest.mock import MagicMock

import pytest

import group_assignment
from sync.person_aliases import PersonAliasError


@pytest.fixture()
def audit_env(mocker):
    chm = MagicMock()
    chm.__enter__.return_value = chm
    chm.authenticate.return_value = True
    chm.get_groups.return_value = [{"id": "1", "name": "Team WAG"}]
    chm.get_group_people.return_value = [{"person_id": "100"}, {"person_id": "999"}]

    def get_person(_person_id):
        chm.last_get_person_status = "not_found"
        return None

    chm.get_person.side_effect = get_person

    def remove(_group_id, _person_id, not_found_ok=False):
        chm.last_group_membership_delete_status = "removed"
        return True

    chm.remove_person_from_group.side_effect = remove

    wp = MagicMock()
    wp.__enter__.return_value = wp
    wp.get_participants.return_value = []

    mocker.patch("group_assignment.ChMeetingsConnector", return_value=chm)
    mocker.patch("group_assignment.WordPressConnector", return_value=wp)
    mocker.patch("group_assignment.time.sleep", return_value=None)
    write_audit = mocker.patch("group_assignment._write_audit_file")
    return chm, write_audit


def _statuses(write_audit):
    rows = write_audit.call_args.args[1]
    return {row["Membership Person Id"]: row for row in rows}


def test_remove_orphans_keeps_an_aliased_membership(audit_env, mocker):
    chm, write_audit = audit_env
    mocker.patch(
        "sync.person_aliases.load_person_aliases",
        return_value={"100": {"canonical_chm_id": "200"}},
    )

    assert group_assignment.audit_team_groups(remove_orphans=True) is True

    rows = _statuses(write_audit)
    assert rows["100"]["Lookup Status"] == "aliased"
    assert rows["100"]["Alias Canonical ChM Id"] == "200"
    assert rows["999"]["Lookup Status"] == "orphan_removed"
    chm.remove_person_from_group.assert_called_once_with("1", "999", not_found_ok=True)


def test_remove_orphans_refuses_on_a_malformed_alias_map(audit_env, mocker):
    chm, write_audit = audit_env
    mocker.patch(
        "sync.person_aliases.load_person_aliases",
        side_effect=PersonAliasError("cannot load person aliases"),
    )

    assert group_assignment.audit_team_groups(remove_orphans=True) is False

    chm.remove_person_from_group.assert_not_called()
    write_audit.assert_not_called()


def test_report_only_audit_still_runs_on_a_malformed_alias_map(audit_env, mocker):
    chm, write_audit = audit_env
    mocker.patch(
        "sync.person_aliases.load_person_aliases",
        side_effect=PersonAliasError("cannot load person aliases"),
    )

    assert group_assignment.audit_team_groups() is True

    assert _statuses(write_audit)["100"]["Lookup Status"] == "not_found"
    chm.remove_person_from_group.assert_not_called()
