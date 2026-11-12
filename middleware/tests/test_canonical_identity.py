import json
from unittest.mock import MagicMock

import pytest

import main
from config import APPROVAL_STATUS
from sync.alias_reconciler import apply_aliases
from sync.manager import SyncManager
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


@pytest.fixture
def malformed_alias_file(tmp_path, mocker):
    """Point the configured alias map at a file that fails to parse."""
    path = _write_aliases(tmp_path, "{not-json", raw=True)
    mocker.patch("sync.person_aliases.Config.PERSON_ALIASES_FILE", path)
    return path


def _mock_connector_config(mocker):
    mocker.patch("wordpress.frontend_connector.Config.WP_URL", "https://test.wordpress.com")
    mocker.patch("wordpress.frontend_connector.Config.WP_API_KEY", "test_api_key")
    mocker.patch("chmeetings.backend_connector.Config.CHM_API_URL", "https://test.chmeetings.com/")
    mocker.patch("chmeetings.backend_connector.Config.CHM_API_KEY", "test_api_key")


def test_malformed_alias_file_does_not_block_church_sync(mocker, malformed_alias_file):
    """Maintainer decision: commands that do not consume the map stay available.

    SyncManager builds a ParticipantSyncer eagerly, so this regresses the moment
    the alias load moves back into that constructor.
    """
    _mock_connector_config(mocker)
    manager = SyncManager()
    try:
        sync_from_excel = mocker.patch.object(
            manager.church_syncer, "sync_from_excel", return_value=True
        )
        assert manager.sync_churches_from_excel("Church Application Form.xlsx") is True
        sync_from_excel.assert_called_once()
    finally:
        manager.close()


def test_full_sync_preflights_aliases_before_any_sub_step(mocker, malformed_alias_file):
    """Maintainer decision: full sync validates the map before performing any sub-step."""
    _mock_connector_config(mocker)
    manager = SyncManager()
    try:
        sync_churches = mocker.patch.object(manager, "sync_churches_from_excel")
        sync_participants = mocker.patch.object(manager, "sync_participants")
        generate_approvals = mocker.patch.object(manager, "generate_approvals")

        with pytest.raises(PersonAliasError):
            manager.run_full_sync()

        sync_churches.assert_not_called()
        sync_participants.assert_not_called()
        generate_approvals.assert_not_called()
    finally:
        manager.close()


def test_daemon_reuse_picks_up_aliases_added_between_runs(mocker):
    """A long-lived SyncManager must not pin the alias map from its first run.

    Daemon mode reuses one SyncManager across scheduled runs. If the syncer's
    cache outlived a run, an alias added and reconciled between two runs would
    never take effect, and the next participant sync could resurrect the stale
    ID the operator just retired.
    """
    _mock_connector_config(mocker)
    manager = SyncManager()
    try:
        mocker.patch.object(manager, "sync_churches_from_excel")
        mocker.patch.object(manager, "generate_approvals")
        mocker.patch.object(manager, "sync_approvals_to_chmeetings")
        inner = mocker.patch.object(
            manager.participant_syncer, "sync_participants", return_value=True
        )
        loader = mocker.patch(
            "sync.manager.load_person_aliases", side_effect=[{}, _aliases()]
        )

        manager.run_full_sync()
        assert manager.participant_syncer.person_aliases == {}

        # Operator adds and reconciles an alias between scheduled runs.
        manager.run_full_sync()
        assert manager.participant_syncer.person_aliases == _aliases()

        assert inner.call_count == 2
        # Exactly one load per run: the participant step is handed the
        # preflighted snapshot instead of re-reading the file, so a map edited
        # mid-run cannot be applied half-and-half.
        assert loader.call_count == 2
    finally:
        manager.close()


def test_run_sync_reports_alias_error_without_traceback(mocker):
    """Step 4: a malformed map is operator error, so it reports as a plain message.

    The catch must sit inside run_sync, ahead of its generic ``except Exception``
    handler — that handler logs via ``logger.exception``, which is the traceback
    the decision rules out.
    """
    manager = MagicMock()
    manager.authenticate.return_value = True
    manager.run_full_sync.side_effect = PersonAliasError("cannot load person aliases")
    exception_log = mocker.patch("main.logger.exception")

    assert main.run_sync(manager, "full") is False
    exception_log.assert_not_called()


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


@pytest.mark.parametrize(
    ("reads", "failing_write"),
    [
        ({"get_rosters": [{"roster_id": 1}]}, "delete_roster"),
        ({}, "update_participant"),
        (
            {"get_approvals": [{"approval_id": 2, "approval_status": "pending"}]},
            "update_approval",
        ),
        ({"get_validation_issues": [{"issue_id": 3}]}, "update_validation_issue"),
    ],
    ids=[
        "roster-delete",
        "participant-tombstone",
        "approval-tombstone",
        "validation-resolve",
    ],
)
def test_reconciler_reports_partial_write_failure(wp_connector, reads, failing_write):
    """Every write in _apply_state must drag the run's result to False.

    The participant tombstone uses `success = success and ...` while the other
    three use `success = False`; that asymmetry is why all four are pinned here
    rather than just the approval path.
    """
    _wire_participants(wp_connector)
    for method, value in reads.items():
        getattr(wp_connector, method).return_value = value
    getattr(wp_connector, failing_write).return_value = None

    assert apply_aliases(execute=True) is False


@pytest.mark.parametrize(
    ("stale", "canonical_present", "expected_outcome"),
    [
        (_participant(status=APPROVAL_STATUS["MERGED"]), True, "already_merged"),
        (_participant(), False, "canonical_missing_run_sync_first"),
    ],
    ids=["already-merged", "canonical-missing"],
)
def test_reconciler_reports_stale_badge_for_every_stale_row_outcome(
    wp_connector, mocker, stale, canonical_present, expected_outcome
):
    """#310 asks for the badge to delete whenever a stale row was found.

    It was previously reported only on the reconciled path, so the two outcomes
    that stop earlier left the operator without the filename.
    """
    audit = mocker.patch("sync.alias_reconciler._write_audit")

    def get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        if chm_id == "100":
            return [stale]
        return [_participant("200", 11)] if canonical_present else []

    wp_connector.get_participants.side_effect = get_participants

    assert apply_aliases(execute=False) is True
    (rows,) = audit.call_args.args
    assert rows[0]["Outcome"] == expected_outcome
    assert rows[0]["Stale Badge Filename"] == "stale.png"


def test_reconciler_resolves_chain_to_terminal_canonical_id(wp_connector, mocker):
    """A -> B -> C must reconcile against C, not B.

    Reconciling against the immediate target was a real bug; the loader-level
    chain test does not cover the reconciler's own use of resolve_chm_id.
    """
    mocker.patch(
        "sync.alias_reconciler.load_person_aliases",
        return_value={
            "100": {"canonical_chm_id": "200"},
            "200": {"canonical_chm_id": "300"},
        },
    )
    stale = _participant("100", 10)
    terminal = _participant("300", 12, status=APPROVAL_STATUS["APPROVED"])

    # "200" deliberately has no WordPress row. Resolving to the immediate target
    # instead of the terminal ID would report canonical_missing_run_sync_first.
    def get_participants(params=None):
        chm_id = (params or {}).get("chmeetings_id")
        return {"100": [stale], "300": [terminal]}.get(chm_id, [])

    wp_connector.get_participants.side_effect = get_participants

    assert apply_aliases(execute=True) is True
    wp_connector.update_participant.assert_called_once_with(
        10, {"approval_status": APPROVAL_STATUS["MERGED"]}
    )


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
