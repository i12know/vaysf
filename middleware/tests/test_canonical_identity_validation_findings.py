"""Reproductions for the canonical-identity validation review (Epic #307, #308-#310).

Every test here asserts the behavior the approved design promises
(docs/CANONICAL_IDENTITY_RFC.md §4-§5). Each one currently fails against the
implementation, so it is marked ``xfail(strict=True)``: the suite stays green
while the finding is open, and the test starts failing loudly (XPASS) the moment
the finding is fixed, at which point the marker should simply be deleted.

Finding numbers match the review posted on the promotion PR.

No production code is changed by this file.
"""

import datetime
import json
from unittest.mock import MagicMock

import pytest
from tenacity import RetryError

from config import APPROVAL_STATUS, CHM_FIELDS
from sync.alias_reconciler import apply_aliases
from sync.consent_checker import ConsentChecker
from sync.participants import ParticipantSyncer
from sync.person_aliases import PersonAliasError, load_person_aliases

from test_canonical_identity import (  # noqa: F401  (wp_connector is a fixture)
    _participant,
    _wire_participants,
    wp_connector,
)
from test_consent_checker import (
    _make_chm_person,
    _make_wp_participant,
    _mock_consent_export,
)
from test_sync_manager import (  # noqa: F401  (sync_manager is a fixture)
    _make_person_data,
    _setup_flip_test_mocks,
    sync_manager,
)

MERGED = APPROVAL_STATUS["MERGED"]


# --------------------------------------------------------------------------
# Finding 3 — participant sync overwrites a `merged` tombstone
# --------------------------------------------------------------------------
def test_sync_never_reactivates_a_merged_row_when_alias_is_absent(sync_manager, mocker):
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")
    chm_id = "7001"
    person_data = _make_person_data(chm_id, is_member=True)
    wp_existing = {
        "participant_id": 1,
        "chmeetings_id": chm_id,
        "first_name": "Test",
        "last_name": "Person",
        "church_code": "RPC",
        "approval_status": MERGED,  # retired by apply-aliases --execute
        "is_church_member": True,
        "updated_at": "2025-12-01 00:00:00",
    }
    updated_calls, _ = _setup_flip_test_mocks(
        sync_manager, mocker, chm_id, person_data, wp_existing
    )
    create_roster = sync_manager.wordpress_connector.create_roster

    syncer = ParticipantSyncer(
        sync_manager.chm_connector,
        sync_manager.wordpress_connector,
        sync_manager.stats,
        sync_manager.churches_cache,
    )
    # The alias that retired this row is not in effect for this run: the file
    # was not found (missing file == empty map) or the entry was removed.
    syncer.person_aliases = {}

    errors_before = sync_manager.stats["participants"]["errors"]

    assert syncer._sync_single_participant(chm_id) is False
    assert sync_manager.stats["participants"]["errors"] == errors_before + 1
    assert updated_calls == [], "a merged tombstone must never be rewritten"

    statuses_written = [
        data.get("approval_status")
        for _, data in updated_calls
        if "approval_status" in data
    ]
    assert all(status == MERGED for status in statuses_written), (
        f"sync rewrote a merged tombstone to {statuses_written}"
    )
    create_roster.assert_not_called()


# --------------------------------------------------------------------------
# Finding 1 — team/church validation still counts merged participants
# --------------------------------------------------------------------------
def test_validate_data_excludes_merged_participants_from_team_validation(
    sync_manager, mocker
):
    def _row(participant_id, chm_id, status):
        return {
            "participant_id": participant_id,
            "chmeetings_id": chm_id,
            "church_id": 1,
            "church_code": "WAG",
            "first_name": "Ngoc",
            "last_name": "Le",
            "is_church_member": False,
            "primary_sport": "Basketball",
            "approval_status": status,
        }

    participants = [_row("11", "200", "approved"), _row("10", "100", MERGED)]
    wp = sync_manager.wordpress_connector
    chm = sync_manager.chm_connector
    mocker.patch.object(wp, "get_participants", return_value=participants)
    mocker.patch.object(wp, "get_rosters", return_value=[])
    mocker.patch.object(wp, "get_validation_issues", return_value=[])
    mocker.patch.object(
        wp, "get_churches", return_value=[{"church_code": "WAG", "church_id": 1}]
    )
    mocker.patch.object(wp, "create_validation_issue", return_value={"issue_id": 1})
    mocker.patch.object(wp, "update_validation_issue", return_value=True)

    def get_groups():
        chm.last_get_groups_status = "ok"
        return [{"id": "team-wag", "name": "Team WAG"}]

    def get_group_people(_group_id):
        chm.last_get_group_people_status = "ok"
        # apply-aliases never touches Team groups, so both twins are still members.
        return [{"person_id": "100"}, {"person_id": "200"}]

    def get_person(chm_id):
        chm.last_get_person_status = "ok"
        return {
            "id": chm_id,
            "additional_fields": [{"field_name": CHM_FIELDS["ROLES"], "value": "Athlete"}],
        }

    mocker.patch.object(chm, "get_groups", side_effect=get_groups)
    mocker.patch.object(chm, "get_group_people", side_effect=get_group_people)
    mocker.patch.object(chm, "get_person", side_effect=get_person)

    team_validator = MagicMock()
    team_validator.validate_church.return_value = []
    team_validator.validate_roster_partners.return_value = []
    mocker.patch("sync.manager.TeamValidator", return_value=team_validator)

    sync_manager.validate_data()

    validated = [
        participant
        for call in team_validator.validate_church.call_args_list
        for participant in call.args[1]
    ]
    assert validated, "expected the canonical participant to be validated"
    assert all(p.get("approval_status") != MERGED for p in validated), (
        "a merged tombstone was passed to team validation and is being counted"
    )


def test_validation_eligibility_resolves_stale_team_membership(sync_manager, mocker):
    """Finding 1/6: a canonical person reached only through a stale Team-group
    membership stays in the validation population, and is fetched once."""
    chm = sync_manager.chm_connector
    mocker.patch(
        "sync.manager.load_person_aliases_for_reader",
        return_value={"100": {"canonical_chm_id": "200"}},
    )

    def get_groups():
        chm.last_get_groups_status = "ok"
        return [{"id": "team-wag", "name": "Team WAG"}]

    def get_group_people(_group_id):
        chm.last_get_group_people_status = "ok"
        # Only the retired ID is still listed; a second stale listing must de-dup.
        return [{"person_id": "100"}, {"person_id": "100"}]

    def get_person(chm_id):
        chm.last_get_person_status = "ok"
        return {
            "id": chm_id,
            "additional_fields": [{"field_name": CHM_FIELDS["ROLES"], "value": "Athlete"}],
        }

    mocker.patch.object(chm, "get_groups", side_effect=get_groups)
    mocker.patch.object(chm, "get_group_people", side_effect=get_group_people)
    get_person_mock = mocker.patch.object(chm, "get_person", side_effect=get_person)

    assert sync_manager._load_current_eligible_chm_ids() == {"200"}
    get_person_mock.assert_called_once_with("200")


def test_validation_survives_a_malformed_alias_map(sync_manager, mocker, tmp_path):
    """A malformed map blocks participant sync, not validation (#308 scope):
    eligibility falls back to raw Team-group IDs and says so."""
    bad = tmp_path / "person_aliases.local.json"
    bad.write_text("{not json", encoding="utf-8")
    mocker.patch("sync.person_aliases.Config.PERSON_ALIASES_FILE", bad)
    chm = sync_manager.chm_connector

    def get_groups():
        chm.last_get_groups_status = "ok"
        return [{"id": "team-wag", "name": "Team WAG"}]

    def get_group_people(_group_id):
        chm.last_get_group_people_status = "ok"
        return [{"person_id": "100"}]

    def get_person(chm_id):
        chm.last_get_person_status = "ok"
        return {
            "id": chm_id,
            "additional_fields": [{"field_name": CHM_FIELDS["ROLES"], "value": "Athlete"}],
        }

    mocker.patch.object(chm, "get_groups", side_effect=get_groups)
    mocker.patch.object(chm, "get_group_people", side_effect=get_group_people)
    mocker.patch.object(chm, "get_person", side_effect=get_person)

    assert sync_manager._load_current_eligible_chm_ids() == {"100"}


# --------------------------------------------------------------------------
# Finding 2 — check-consent can credit the merged twin instead of the canonical
# --------------------------------------------------------------------------
def test_check_consent_credits_canonical_person_not_merged_twin(mocker):
    chm = MagicMock()
    chm.authenticate.return_value = True
    chm.update_person.return_value = True
    wp = MagicMock()
    mocker.patch("sync.consent_checker.time.sleep", return_value=None)
    checker = ConsentChecker(chm, wp)
    mocker.patch.object(checker, "_write_audit_file")
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Jerry",
                "Last Name": "Phan",
                "Athlete Mobile Phone": "(562) 555-0101",
                "Athlete Email": "Jerry@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    stale = {**_make_wp_participant(chmeetings_id="100"), "approval_status": MERGED}
    canonical = {
        **_make_wp_participant(chmeetings_id="200"),
        "participant_id": 2,
        "approval_status": "validated",
    }
    # The REST list is ordered by last_name, first_name: identical twins tie and
    # the older (stale) row can come first.
    wp.get_participants.side_effect = [[stale, canonical], []]
    chm.get_person.side_effect = lambda chm_id: _make_chm_person(chmeetings_id=chm_id)

    checker.run("consent.xlsx")

    credited = [call.args[0] for call in chm.update_person.call_args_list]
    assert credited == ["200"], f"consent was credited to ChM person(s) {credited}"


def _consent_checker_with_one_form(mocker, **form_overrides):
    chm = MagicMock()
    chm.authenticate.return_value = True
    chm.update_person.return_value = True
    chm.get_person.side_effect = lambda chm_id: _make_chm_person(chmeetings_id=chm_id)
    wp = MagicMock()
    mocker.patch("sync.consent_checker.time.sleep", return_value=None)
    checker = ConsentChecker(chm, wp)
    mocker.patch.object(checker, "_write_audit_file")
    form = {
        "First Name": "Jerry",
        "Last Name": "Phan",
        "Athlete Mobile Phone": "(562) 555-0101",
        "Athlete Email": "Jerry@example.com",
        "Athlete Birthdate": "2008-04-15",
        "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
        "Full Name of the parents or legal guardian": "",
        "Email of the parents or legal guardian": "",
        "Cell phone of the parents or legal guardian": "",
        "Submission Date": "2026-05-08 10:00:00",
    }
    _mock_consent_export(mocker, [{**form, **form_overrides}])
    return checker, chm, wp


def test_check_consent_form_matching_only_retired_registration_credits_canonical(mocker):
    """Finding 2: the form carries the retired registration's details, so it
    scores against the merged row only. The alias redirects the credit to the
    canonical person before the ChMeetings write."""
    checker, chm, wp = _consent_checker_with_one_form(mocker)
    mocker.patch(
        "sync.consent_checker.load_person_aliases_for_reader",
        return_value={"100": {"canonical_chm_id": "200"}},
    )
    stale = {**_make_wp_participant(chmeetings_id="100"), "approval_status": MERGED}
    canonical = {
        **_make_wp_participant(
            chmeetings_id="200",
            first_name="Gerald",
            last_name="Pham",
            email="other@example.com",
            phone="714-555-0199",
            birthdate="2007-01-01",
        ),
        "participant_id": 2,
        "approval_status": "validated",
    }
    wp.get_participants.side_effect = [[stale, canonical], []]

    checker.run("consent.xlsx")

    assert [call.args[0] for call in chm.update_person.call_args_list] == ["200"]
    mirrored = [call.args[0] for call in wp.update_participant.call_args_list]
    assert mirrored == [2], f"consent mirrored onto participant(s) {mirrored}"


def test_check_consent_never_writes_to_merged_row_without_alias(mocker):
    """Finding 2: a merged row whose alias is not loaded is excluded outright."""
    checker, chm, wp = _consent_checker_with_one_form(mocker)
    stale = {**_make_wp_participant(chmeetings_id="100"), "approval_status": MERGED}
    wp.get_participants.side_effect = [[stale], []]

    summary = checker.run("consent.xlsx")

    chm.update_person.assert_not_called()
    wp.update_participant.assert_not_called()
    assert summary["unmatched"] == 1


# --------------------------------------------------------------------------
# Finding 7 — apply-aliases: a transient WordPress failure inside delete_roster
# escapes as RetryError and aborts the whole run with no audit file
# --------------------------------------------------------------------------
def test_apply_aliases_survives_retry_error_during_roster_delete(wp_connector, mocker):
    _wire_participants(wp_connector)
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.delete_roster.side_effect = RetryError(MagicMock())
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")

    assert apply_aliases(execute=True) is False
    write_audit.assert_called_once()
    (row,) = write_audit.call_args.args[0]
    assert row["Outcome"] == "error"
    assert row["Failed Writes"] == "roster 1"
    # The participant was made inert before the roster delete was attempted.
    assert row["Participant Tombstoned"] is True


def test_apply_aliases_tombstones_participant_before_other_writes(wp_connector):
    """Finding 7: the participant tombstone is the first write."""
    _wire_participants(wp_connector)
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.get_approvals.return_value = [{"approval_id": 2, "approval_status": "pending"}]
    wp_connector.get_validation_issues.return_value = [{"issue_id": 3}]

    assert apply_aliases(execute=True) is True

    writes = [
        call[0]
        for call in wp_connector.method_calls
        if call[0]
        in ("update_participant", "delete_roster", "update_approval", "update_validation_issue")
    ]
    assert writes == [
        "update_participant",
        "delete_roster",
        "update_approval",
        "update_validation_issue",
    ]


def test_apply_aliases_stops_an_alias_when_the_tombstone_does_not_land(wp_connector, mocker):
    """Finding 7: a failed tombstone leaves that row whole and the loop continues."""
    mocker.patch(
        "sync.alias_reconciler.load_person_aliases",
        return_value={
            "100": {"canonical_chm_id": "200"},
            "300": {"canonical_chm_id": "200"},
        },
    )
    rows_by_chm_id = {
        "100": [_participant("100", 10, "approved")],
        "300": [_participant("300", 12, "pending")],
        "200": [_participant("200", 11)],
    }
    wp_connector.get_participants.side_effect = lambda params=None: rows_by_chm_id.get(
        (params or {}).get("chmeetings_id"), []
    )
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.update_participant.side_effect = [RetryError(MagicMock()), {"participant_id": 12}]
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")

    assert apply_aliases(execute=True) is False

    first, second = write_audit.call_args.args[0]
    assert (first["Outcome"], first["Failed Writes"]) == ("error", "participant 10")
    assert second["Outcome"] == "reconciled"
    # Only the second alias reached its roster delete.
    wp_connector.delete_roster.assert_called_once_with(1)


def test_apply_aliases_writes_audit_even_when_the_run_aborts(wp_connector, mocker):
    """Finding 7: an unexpected exception still leaves the audit record."""
    _wire_participants(wp_connector)
    wp_connector.get_rosters.side_effect = KeyError("unexpected")
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")

    with pytest.raises(KeyError):
        apply_aliases(execute=True)
    write_audit.assert_called_once()


# --------------------------------------------------------------------------
# Finding 8 — apply-aliases tombstones the stale row even when the "canonical"
# WordPress row is itself a merged tombstone
# --------------------------------------------------------------------------
def test_apply_aliases_refuses_when_canonical_row_is_merged(wp_connector, mocker):
    _wire_participants(
        wp_connector,
        stale=_participant("100", 10, "approved"),
        canonical=_participant("200", 11, MERGED),
    )
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.get_approvals.return_value = [{"approval_id": 2, "approval_status": "approved"}]
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")

    assert apply_aliases(execute=True) is False

    wp_connector.update_participant.assert_not_called()
    wp_connector.delete_roster.assert_not_called()
    wp_connector.update_approval.assert_not_called()
    wp_connector.update_validation_issue.assert_not_called()
    (row,) = write_audit.call_args.args[0]
    assert row["Outcome"] == "canonical_is_merged"


# --------------------------------------------------------------------------
# Finding 9 — the approval-mismatch record must survive the confirming rerun
# --------------------------------------------------------------------------
def test_apply_aliases_audit_file_is_new_for_every_run(tmp_path, mocker):
    import sync.alias_reconciler as reconciler

    mocker.patch.object(reconciler, "DATA_DIR", tmp_path)
    fixed = datetime.datetime(2026, 11, 12, 14, 30, 5)

    first = reconciler._audit_path(fixed)
    assert first.name == "alias_reconciliation_20261112_143005_audit.xlsx"
    first.write_bytes(b"run one")
    second = reconciler._audit_path(fixed)
    assert second != first and second.name.endswith("_audit.xlsx")

    written = reconciler._write_audit([{"Stale ChM ID": "100", "Outcome": "already_merged"}])
    assert written is not None and written.exists()
    assert first.read_bytes() == b"run one", "an earlier run's audit was overwritten"


def test_already_merged_row_still_reports_the_approval_mismatch(wp_connector, mocker):
    _wire_participants(
        wp_connector,
        stale=_participant("100", 10, MERGED),
        canonical=_participant("200", 11, "validated"),
    )
    wp_connector.get_approvals.return_value = [
        {"approval_id": 2, "approval_status": MERGED, "approval_date": "2026-06-01 09:00:00"}
    ]
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")

    assert apply_aliases(execute=False) is True

    (row,) = write_audit.call_args.args[0]
    assert row["Outcome"] == "already_merged"
    assert row["Approval Mismatch"] == "possible"
    assert row["Stale Pastor Decision Date"] == "2026-06-01 09:00:00"
    assert row["Canonical Approval Status"] == "validated"
    wp_connector.update_participant.assert_not_called()


@pytest.mark.parametrize(
    ("approval_date", "canonical_status"),
    [(None, "validated"), ("2026-06-01 09:00:00", "approved")],
)
def test_already_merged_row_reports_no_mismatch_when_nothing_was_lost(
    wp_connector, mocker, approval_date, canonical_status
):
    _wire_participants(
        wp_connector,
        stale=_participant("100", 10, MERGED),
        canonical=_participant("200", 11, canonical_status),
    )
    wp_connector.get_approvals.return_value = [
        {"approval_id": 2, "approval_status": MERGED, "approval_date": approval_date}
    ]
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")

    assert apply_aliases(execute=False) is True

    (row,) = write_audit.call_args.args[0]
    assert row["Approval Mismatch"] == "no"


# --------------------------------------------------------------------------
# Finding 10 — where the map is read from, and saying so on every load
# --------------------------------------------------------------------------
def test_alias_file_defaults_to_the_private_local_file():
    import config

    assert config.PERSON_ALIASES_FILE == config.DATA_DIR / "person_aliases.local.json"
    assert config._resolve_person_aliases_file(None) == config.PERSON_ALIASES_FILE
    assert config._resolve_person_aliases_file("  ") == config.PERSON_ALIASES_FILE


def test_relative_alias_file_resolves_against_middleware_not_cwd(tmp_path, monkeypatch):
    import config

    monkeypatch.chdir(tmp_path)
    resolved = config._resolve_person_aliases_file("data/person_aliases.local.json")
    assert resolved == config.BASE_DIR / "data" / "person_aliases.local.json"
    absolute = tmp_path / "elsewhere.json"
    assert config._resolve_person_aliases_file(str(absolute)) == absolute


def _capture_log(level="INFO"):
    from loguru import logger

    messages = []
    handler_id = logger.add(lambda message: messages.append(str(message)), level=level)
    return messages, lambda: logger.remove(handler_id)


def test_alias_loader_logs_missing_file_as_zero_aliases_with_path(tmp_path):
    missing = tmp_path / "person_aliases.local.json"
    messages, stop = _capture_log()
    try:
        assert load_person_aliases(missing) == {}
    finally:
        stop()
    assert any(
        "Loaded 0 person aliases (file not found at" in message and str(missing) in message
        for message in messages
    ), messages


@pytest.mark.parametrize(("payload", "count"), [({}, 0), ({"100": "200"}, 1)])
def test_alias_loader_logs_path_and_count_on_every_load(tmp_path, payload, count):
    path = tmp_path / "person_aliases.local.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    messages, stop = _capture_log()
    try:
        load_person_aliases(path)
    finally:
        stop()
    assert any(
        f"Loaded {count} person alias(es) from" in message and str(path) in message
        for message in messages
    ), messages


# --------------------------------------------------------------------------
# Finding 12 — apply-aliases reads stale rosters with the REST default, which
# only returns rows whose team_order IS NULL
# --------------------------------------------------------------------------
def test_apply_aliases_requests_rosters_for_every_team_order(wp_connector):
    _wire_participants(wp_connector)

    apply_aliases(execute=False)

    params = wp_connector.get_rosters.call_args.kwargs["params"]
    assert params.get("all_team_orders")


def test_apply_aliases_pages_through_every_open_validation_issue(wp_connector):
    """Finding 12: more open issues than one page are all read and resolved."""
    _wire_participants(wp_connector)
    pages = {
        1: [{"issue_id": issue_id} for issue_id in range(1, 101)],
        2: [{"issue_id": issue_id} for issue_id in range(101, 131)],
    }
    wp_connector.get_validation_issues.side_effect = lambda params=None: pages.get(
        params["page"], []
    )

    assert apply_aliases(execute=True) is True

    requested = [call.kwargs["params"] for call in wp_connector.get_validation_issues.call_args_list]
    assert [params["page"] for params in requested] == [1, 2]
    assert all(params["per_page"] == 100 for params in requested)
    assert wp_connector.update_validation_issue.call_count == 130


# --------------------------------------------------------------------------
# Finding 13 — alias loader edge cases
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="Finding 13a: json.loads keeps the last of two identical keys, so a "
    "stale ID listed twice with different canonical IDs silently resolves to "
    "whichever line is last instead of failing closed.",
)
def test_alias_loader_rejects_repeated_stale_id(tmp_path):
    path = tmp_path / "person_aliases.json"
    path.write_text('{"100": "200", "100": "300"}', encoding="utf-8")

    with pytest.raises(PersonAliasError):
        load_person_aliases(path)


@pytest.mark.xfail(
    strict=True,
    reason="Finding 13b: a valid map saved with a UTF-8 byte-order mark (Windows "
    "PowerShell 5.1 Set-Content/Out-File -Encoding UTF8) is rejected as "
    "malformed, which blocks every participant sync until it is re-saved.",
)
def test_alias_loader_accepts_utf8_bom(tmp_path):
    path = tmp_path / "person_aliases.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"100": "200"}).encode("utf-8"))

    assert load_person_aliases(path)["100"]["canonical_chm_id"] == "200"


@pytest.mark.xfail(
    strict=True,
    raises=UnicodeDecodeError,
    reason="Finding 13c: a UTF-16 file (PowerShell '>' redirection) raises "
    "UnicodeDecodeError, which is not converted to PersonAliasError, so callers "
    "get a traceback instead of the plain operator message.",
)
def test_alias_loader_reports_wrong_encoding_as_alias_error(tmp_path):
    path = tmp_path / "person_aliases.json"
    path.write_bytes(json.dumps({"100": "200"}).encode("utf-16"))

    with pytest.raises(PersonAliasError):
        load_person_aliases(path)
