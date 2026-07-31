# Begin of tests/test_alias_reconciler.py
"""Tests for the apply-aliases reconciliation command (Issue #310).

Covers the report-only/--execute split, the missing-canonical-row block, the
approval-mismatch warning (no auto-copy), idempotency on a second run, and
the cyclic-alias-map hard failure.
"""
from unittest.mock import MagicMock

import pytest

from config import APPROVAL_STATUS, VALIDATION_STATUS
from sync.alias_reconciler import apply_aliases
from sync.person_aliases import PersonAliasError


@pytest.fixture()
def wp_connector(mocker):
    wp = MagicMock()
    wp.__enter__.return_value = wp
    wp.__exit__.return_value = None
    mocker.patch("sync.alias_reconciler.WordPressConnector", return_value=wp)
    return wp


def _participant(**overrides):
    base = {
        "participant_id": 501,
        "chmeetings_id": "3634001",
        "first_name": "Ngoc",
        "last_name": "Le",
        "church_code": "WAG",
        "approval_status": APPROVAL_STATUS["PENDING"],
    }
    base.update(overrides)
    return base


def _alias_map(reason="re-registered to change sports"):
    return {
        "3634001": {
            "canonical_chm_id": "3633885",
            "reason": reason,
            "confirmed_by": "Bumble",
            "confirmed_on": "2026-07-20",
            "note": "",
        }
    }


def test_empty_map_makes_no_connector_calls(mocker, wp_connector):
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value={})

    result = apply_aliases(execute=False)

    assert result is True
    wp_connector.get_participants.assert_not_called()


def test_cyclic_map_refuses_to_run(mocker, wp_connector):
    mocker.patch(
        "sync.alias_reconciler.load_person_aliases",
        side_effect=PersonAliasError("cycle: A -> B -> A"),
    )

    result = apply_aliases(execute=False)

    assert result is False
    wp_connector.get_participants.assert_not_called()


def test_no_wp_row_for_stale_id_is_a_noop(mocker, wp_connector):
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    wp_connector.get_participants.return_value = []

    result = apply_aliases(execute=False)

    assert result is True
    wp_connector.get_rosters.assert_not_called()
    wp_connector.delete_roster.assert_not_called()


def test_report_only_makes_zero_write_calls(mocker, wp_connector):
    """Acceptance: report-only mode makes zero write calls."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())

    stale = _participant()
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = [{"roster_id": 10}, {"roster_id": 11}]

    result = apply_aliases(execute=False)

    assert result is True
    wp_connector.delete_roster.assert_not_called()
    wp_connector.update_participant.assert_not_called()
    wp_connector.update_approval.assert_not_called()
    wp_connector.update_validation_issue.assert_not_called()


def test_canonical_missing_blocks_with_no_writes(mocker, wp_connector):
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())

    stale = _participant()

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [stale]
        return []  # canonical not synced to WordPress yet

    wp_connector.get_participants.side_effect = fake_get_participants

    result = apply_aliases(execute=True)

    assert result is True
    wp_connector.delete_roster.assert_not_called()
    wp_connector.update_participant.assert_not_called()


def test_execute_deletes_rosters_tombstones_and_resolves_issues(mocker, wp_connector):
    """Acceptance: --execute performs steps 2-4."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value="WAG_3634001_abcd1234.png")

    stale = _participant()
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = [{"roster_id": 10}, {"roster_id": 11}]
    wp_connector.delete_roster.return_value = True
    wp_connector.update_participant.return_value = {"participant_id": 501, "approval_status": "merged"}
    wp_connector.get_approvals.return_value = [{"approval_id": 77, "approval_status": "pending"}]
    wp_connector.update_approval.return_value = {"approval_id": 77, "approval_status": "merged"}
    wp_connector.get_validation_issues.return_value = [{"issue_id": 901, "status": "open"}]
    wp_connector.update_validation_issue.return_value = {"issue_id": 901, "status": "resolved"}

    result = apply_aliases(execute=True)

    assert result is True
    assert wp_connector.delete_roster.call_count == 2
    wp_connector.delete_roster.assert_any_call(10)
    wp_connector.delete_roster.assert_any_call(11)
    wp_connector.update_participant.assert_called_once_with(501, {"approval_status": "merged"})
    wp_connector.update_approval.assert_called_once_with(77, {"approval_status": "merged"})
    wp_connector.get_validation_issues.assert_called_once_with(
        params={"participant_id": 501, "status": VALIDATION_STATUS["OPEN"]}
    )
    update_issue_args = wp_connector.update_validation_issue.call_args
    assert update_issue_args.args[0] == 901
    assert update_issue_args.args[1]["status"] == VALIDATION_STATUS["RESOLVED"]

    # The canonical row is never written to by the reconciler.
    for call in wp_connector.update_participant.call_args_list:
        assert call.args[0] != 413


def test_execute_warns_on_approval_mismatch_without_auto_copy(mocker, wp_connector):
    """Acceptance: warns on the approval-mismatch case; never auto-copies the approval."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value=None)
    mock_logger = mocker.patch("sync.alias_reconciler.logger")

    stale = _participant(approval_status=APPROVAL_STATUS["APPROVED"])
    canonical = _participant(
        participant_id=413, chmeetings_id="3633885", approval_status=APPROVAL_STATUS["PENDING"]
    )

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = []
    wp_connector.update_participant.return_value = {"participant_id": 501}
    wp_connector.get_approvals.return_value = []
    wp_connector.get_validation_issues.return_value = []

    result = apply_aliases(execute=True)

    assert result is True
    warning_messages = [str(call.args[0]) for call in mock_logger.warning.call_args_list]
    assert any(
        "APPROVAL MISMATCH" in message for message in warning_messages
    ), "expected a loud warning about the approval mismatch"
    # No call ever writes 'approved' onto the canonical participant.
    for call in wp_connector.update_participant.call_args_list:
        assert call.args[1].get("approval_status") != APPROVAL_STATUS["APPROVED"]


def test_second_run_is_a_noop(mocker, wp_connector):
    """Acceptance: idempotent — a second run over a fully-tombstoned row writes nothing."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())

    already_merged_stale = _participant(approval_status=APPROVAL_STATUS["MERGED"])
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [already_merged_stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    # Nothing left behind by the previous run.
    wp_connector.get_rosters.return_value = []
    wp_connector.get_approvals.return_value = [{"approval_id": 77, "approval_status": "merged"}]
    wp_connector.get_validation_issues.return_value = []

    result = apply_aliases(execute=True)

    assert result is True
    wp_connector.delete_roster.assert_not_called()
    wp_connector.update_participant.assert_not_called()
    wp_connector.update_approval.assert_not_called()
    wp_connector.update_validation_issue.assert_not_called()


def test_second_run_retries_residual_approval_tombstone(mocker, wp_connector):
    """A previous run that tombstoned the participant but failed the approval write
    must be retried, not skipped as 'already merged' — otherwise the stale approval
    token stays live forever while the command reports success."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value=None)

    already_merged_stale = _participant(approval_status=APPROVAL_STATUS["MERGED"])
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [already_merged_stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = []
    # Left behind by the failed run: an approval still sitting at 'pending'.
    wp_connector.get_approvals.return_value = [{"approval_id": 77, "approval_status": "pending"}]
    wp_connector.get_validation_issues.return_value = []
    wp_connector.update_participant.return_value = {"participant_id": 501}
    wp_connector.update_approval.return_value = {"approval_id": 77}

    result = apply_aliases(execute=True)

    assert result is True
    wp_connector.update_approval.assert_called_once_with(77, {"approval_status": "merged"})


def test_second_run_retries_residual_open_validation_issue(mocker, wp_connector):
    """Same for a validation issue left open by a partially-failed run."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value=None)

    already_merged_stale = _participant(approval_status=APPROVAL_STATUS["MERGED"])
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [already_merged_stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = []
    wp_connector.get_approvals.return_value = [{"approval_id": 77, "approval_status": "merged"}]
    wp_connector.get_validation_issues.return_value = [{"issue_id": 901, "status": "open"}]
    wp_connector.update_participant.return_value = {"participant_id": 501}
    wp_connector.update_validation_issue.return_value = {"issue_id": 901}

    result = apply_aliases(execute=True)

    assert result is True
    wp_connector.update_validation_issue.assert_called_once()
    assert wp_connector.update_validation_issue.call_args.args[0] == 901


def test_chain_reconciles_against_the_terminal_canonical_id(mocker, wp_connector):
    """For A -> B -> C, sync resolves A to C, so apply-aliases must reconcile A
    against C as well. Checking A against its immediate target B would verify a row
    that is itself about to be tombstoned."""
    chain = {
        "A": {"canonical_chm_id": "B", "reason": "", "confirmed_by": "", "confirmed_on": "", "note": ""},
        "B": {"canonical_chm_id": "C", "reason": "", "confirmed_by": "", "confirmed_on": "", "note": ""},
    }
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=chain)
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value=None)

    rows = {
        "A": _participant(participant_id=501, chmeetings_id="A"),
        "B": _participant(participant_id=502, chmeetings_id="B"),
        "C": _participant(participant_id=503, chmeetings_id="C"),
    }

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        return [rows[chm_id]] if chm_id in rows else []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = []
    wp_connector.get_approvals.return_value = []
    wp_connector.get_validation_issues.return_value = []
    wp_connector.update_participant.return_value = {"participant_id": 0}

    result = apply_aliases(execute=False)

    assert result is True
    # Both A and B must have been looked up against terminal canonical C, never B.
    looked_up = [c.kwargs["params"]["chmeetings_id"] for c in wp_connector.get_participants.call_args_list]
    assert looked_up.count("C") == 2, f"expected both entries resolved to C, got {looked_up}"


def test_roster_delete_failure_is_reported_as_an_error(mocker, wp_connector):
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value=None)

    stale = _participant()
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = [{"roster_id": 10}]
    wp_connector.delete_roster.return_value = False
    wp_connector.update_participant.return_value = {"participant_id": 501}
    wp_connector.get_approvals.return_value = []
    wp_connector.get_validation_issues.return_value = []

    result = apply_aliases(execute=True)

    assert result is False


def test_approval_tombstone_failure_is_reported_as_an_error(mocker, wp_connector):
    """A failed update_approval() must not be reported as 'reconciled' — a stale
    approval token could still be active for the retired duplicate."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value=None)

    stale = _participant()
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = []
    wp_connector.delete_roster.return_value = True
    wp_connector.update_participant.return_value = {"participant_id": 501}
    wp_connector.get_approvals.return_value = [{"approval_id": 77, "approval_status": "pending"}]
    wp_connector.update_approval.return_value = None  # write failed
    wp_connector.get_validation_issues.return_value = []

    result = apply_aliases(execute=True)

    assert result is False


def test_validation_resolve_failure_is_reported_as_an_error(mocker, wp_connector):
    """A failed update_validation_issue() must not be reported as 'reconciled' —
    a stale validation issue could still be left open on the retired duplicate."""
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value=_alias_map())
    mocker.patch("sync.alias_reconciler._stale_badge_filename", return_value=None)

    stale = _participant()
    canonical = _participant(participant_id=413, chmeetings_id="3633885")

    def fake_get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "3634001":
            return [stale]
        if chm_id == "3633885":
            return [canonical]
        return []

    wp_connector.get_participants.side_effect = fake_get_participants
    wp_connector.get_rosters.return_value = []
    wp_connector.delete_roster.return_value = True
    wp_connector.update_participant.return_value = {"participant_id": 501}
    wp_connector.get_approvals.return_value = []
    wp_connector.get_validation_issues.return_value = [{"issue_id": 901, "status": "open"}]
    wp_connector.update_validation_issue.return_value = None  # write failed

    result = apply_aliases(execute=True)

    assert result is False

# End of tests/test_alias_reconciler.py
