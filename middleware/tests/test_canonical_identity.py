import json
from unittest.mock import MagicMock

import pytest

from config import APPROVAL_STATUS
from sync.alias_reconciler import apply_aliases
from sync.participants import ParticipantSyncer
from sync.person_aliases import PersonAliasError, load_person_aliases, resolve_chm_id


def _write_aliases(tmp_path, payload, raw=False):
    path = tmp_path / "person_aliases.json"
    path.write_text(payload if raw else json.dumps(payload), encoding="utf-8")
    return path


def _aliases():
    return {
        "100": {
            "canonical_chm_id": "200",
            "reason": "duplicate registration",
            "confirmed_by": "Bumble",
            "confirmed_on": "2026-07-20",
            "note": "",
        }
    }


def _participant(chm_id="100", participant_id=10, status="pending"):
    return {
        "participant_id": participant_id,
        "chmeetings_id": chm_id,
        "first_name": "Ngoc",
        "last_name": "Le",
        "church_code": "WAG",
        "approval_status": status,
    }


def test_alias_loader_normalizes_metadata_and_resolves_chains(tmp_path):
    path = _write_aliases(
        tmp_path,
        {
            " 100 ": {"canonical_chm_id": " 200 ", "reason": " duplicate "},
            "200": 300,
        },
    )

    aliases = load_person_aliases(path)

    assert aliases["100"]["reason"] == "duplicate"
    assert resolve_chm_id("100", aliases) == "300"
    assert resolve_chm_id("999", aliases) == "999"


@pytest.mark.parametrize(
    ("payload", "raw"),
    [
        ("{not-json", True),
        (["100", "200"], False),
        ({"100": "100"}, False),
        ({"100": "200", "200": "100"}, False),
        ({"100": {"reason": "missing target"}}, False),
        ({"100": True}, False),
    ],
)
def test_existing_invalid_alias_file_fails_closed(tmp_path, payload, raw):
    with pytest.raises(PersonAliasError):
        load_person_aliases(_write_aliases(tmp_path, payload, raw=raw))


def test_missing_alias_file_is_an_empty_map(tmp_path):
    assert load_person_aliases(tmp_path / "missing.json") == {}


def _stats():
    return {
        "participants": {"created": 0, "updated": 0, "errors": 0},
        "rosters": {"created": 0, "updated": 0, "deleted": 0, "errors": 0},
        "validation_issues": {
            "created": 0,
            "updated": 0,
            "resolved": 0,
            "unchanged": 0,
            "skipped": 0,
            "errors": 0,
        },
        "approvals": {"created": 0, "updated": 0, "errors": 0},
    }


def test_participant_sync_resolves_before_chmeetings_fetch(mocker):
    mocker.patch("sync.participants.load_person_aliases", return_value=_aliases())
    chm = MagicMock()
    wp = MagicMock()

    def missing_person(chm_id):
        chm.last_get_person_status = "not_found"
        return None

    chm.get_person.side_effect = missing_person
    syncer = ParticipantSyncer(chm, wp, _stats(), {})

    assert syncer._sync_single_participant("100", allow_missing_person_skip=True) is True
    chm.get_person.assert_called_once_with("200")
    wp.create_participant.assert_not_called()


def test_full_sync_deduplicates_alias_and_canonical_memberships(mocker):
    mocker.patch("sync.participants.load_person_aliases", return_value=_aliases())
    chm = MagicMock()
    wp = MagicMock()
    wp.get_churches.return_value = [{"church_code": "WAG", "church_id": 1}]
    chm.get_groups.return_value = [{"id": 1, "name": "Team WAG"}]
    chm.get_group_people.return_value = [{"person_id": "100"}, {"person_id": "200"}]
    syncer = ParticipantSyncer(chm, wp, _stats(), {})
    process = mocker.patch.object(syncer, "_sync_single_participant", return_value=True)

    assert syncer.sync_participants() is True
    process.assert_called_once()


@pytest.fixture
def wp_connector(mocker):
    connector = MagicMock()
    connector.__enter__.return_value = connector
    connector.__exit__.return_value = None
    connector.get_rosters.return_value = []
    connector.get_approvals.return_value = []
    connector.get_validation_issues.return_value = []
    connector.delete_roster.return_value = True
    connector.update_participant.return_value = {"participant_id": 10}
    connector.update_approval.return_value = {"approval_id": 20}
    connector.update_validation_issue.return_value = {"issue_id": 30}
    mocker.patch("sync.alias_reconciler.WordPressConnector", return_value=connector)
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_aliases())
    mocker.patch("sync.alias_reconciler._write_audit")
    mocker.patch("sync.alias_reconciler._badge_filename", return_value="stale.png")
    return connector


def _wire_participants(connector, stale=None, canonical=None):
    stale = stale or _participant()
    canonical = canonical or _participant("200", 11)

    def get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        return {"100": [stale], "200": [canonical]}.get(chm_id, [])

    connector.get_participants.side_effect = get_participants


def test_reconciler_report_only_reads_once_and_never_writes(wp_connector):
    _wire_participants(wp_connector)
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.get_approvals.return_value = [{"approval_id": 2, "approval_status": "pending"}]

    assert apply_aliases(execute=False) is True
    wp_connector.get_rosters.assert_called_once()
    wp_connector.get_approvals.assert_called_once()
    wp_connector.get_validation_issues.assert_called_once()
    wp_connector.update_participant.assert_not_called()
    wp_connector.update_approval.assert_not_called()


def test_reconciler_executes_complete_tombstone(wp_connector):
    _wire_participants(wp_connector)
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.get_approvals.return_value = [{"approval_id": 2, "approval_status": "pending"}]
    wp_connector.get_validation_issues.return_value = [{"issue_id": 3}]

    assert apply_aliases(execute=True) is True
    wp_connector.delete_roster.assert_called_once_with(1)
    wp_connector.update_participant.assert_called_once_with(10, {"approval_status": "merged"})
    wp_connector.update_approval.assert_called_once_with(2, {"approval_status": "merged"})
    wp_connector.update_validation_issue.assert_called_once()


@pytest.mark.parametrize(
    ("method", "status_attribute"),
    [
        ("get_participants", "last_get_participants_status"),
        ("get_rosters", "last_get_rosters_status"),
        ("get_approvals", "last_get_approvals_status"),
        ("get_validation_issues", "last_get_validation_issues_status"),
    ],
)
def test_reconciler_fails_closed_on_read_errors(
    wp_connector, method, status_attribute
):
    _wire_participants(wp_connector)

    def failed_read(*args, **kwargs):
        setattr(wp_connector, status_attribute, "failed")
        return []

    getattr(wp_connector, method).side_effect = failed_read

    assert apply_aliases(execute=True) is False
    wp_connector.update_participant.assert_not_called()


def test_reconciler_reports_partial_write_failure(wp_connector):
    _wire_participants(wp_connector)
    wp_connector.get_approvals.return_value = [{"approval_id": 2, "approval_status": "pending"}]
    wp_connector.update_approval.return_value = None

    assert apply_aliases(execute=True) is False


def test_reconciler_finishes_residual_work_without_canonical_row(wp_connector):
    merged = _participant(status=APPROVAL_STATUS["MERGED"])

    def stale_only(params=None):
        return [merged] if (params or {}).get("chmeetings_id") == "100" else []

    wp_connector.get_participants.side_effect = stale_only
    wp_connector.get_approvals.return_value = [{"approval_id": 2, "approval_status": "pending"}]

    assert apply_aliases(execute=True) is True
    wp_connector.get_participants.assert_called_once()
    wp_connector.update_approval.assert_called_once_with(2, {"approval_status": "merged"})
    wp_connector.update_participant.assert_not_called()


def test_reconciler_is_noop_when_tombstone_is_complete(wp_connector):
    _wire_participants(
        wp_connector,
        stale=_participant(status=APPROVAL_STATUS["MERGED"]),
    )

    assert apply_aliases(execute=True) is True
    wp_connector.update_participant.assert_not_called()
    wp_connector.update_approval.assert_not_called()
