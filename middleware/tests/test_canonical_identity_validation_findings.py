"""Reproductions for the canonical-identity validation review (Epic #307, #308-#310).

Every test here asserts the behavior the approved design promises
(docs/CANONICAL_IDENTITY_RFC.md §4-§5). Each one currently fails against the
implementation, so it is marked ``xfail(strict=True)``: the suite stays green
while the finding is open, and the test starts failing loudly (XPASS) the moment
the finding is fixed, at which point the marker should simply be deleted.

Finding numbers match the review posted on the promotion PR.

No production code is changed by this file.
"""

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
@pytest.mark.xfail(
    strict=True,
    reason="Finding 2: ConsentChecker scores every WP participant including "
    "merged rows and keeps the first on a tie, so the consent form can be "
    "credited to the stale ChMeetings person and never reach the canonical one.",
)
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


# --------------------------------------------------------------------------
# Finding 7 — apply-aliases: a transient WordPress failure inside delete_roster
# escapes as RetryError and aborts the whole run with no audit file
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    raises=RetryError,
    reason="Finding 7: WordPressConnector.delete_roster() pre-reads the roster "
    "through the retried get_roster(); on a transient failure that raises "
    "tenacity.RetryError, which neither delete_roster nor apply_aliases catches.",
)
def test_apply_aliases_survives_retry_error_during_roster_delete(wp_connector, mocker):
    _wire_participants(wp_connector)
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.delete_roster.side_effect = RetryError(MagicMock())
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")

    assert apply_aliases(execute=True) is False
    write_audit.assert_called_once()


# --------------------------------------------------------------------------
# Finding 8 — apply-aliases tombstones the stale row even when the "canonical"
# WordPress row is itself a merged tombstone
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="Finding 8: _reconcile_one never checks that the canonical WP row is "
    "active; reversing an already-executed alias leaves both rows merged.",
)
def test_apply_aliases_refuses_when_canonical_row_is_merged(wp_connector):
    _wire_participants(
        wp_connector,
        stale=_participant("100", 10, "approved"),
        canonical=_participant("200", 11, MERGED),
    )

    apply_aliases(execute=True)

    wp_connector.update_participant.assert_not_called()


# --------------------------------------------------------------------------
# Finding 12 — apply-aliases reads stale rosters with the REST default, which
# only returns rows whose team_order IS NULL
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="Finding 12: GET /rosters filters to team_order IS NULL unless "
    "all_team_orders is sent; the reconciler does not send it, so stale rosters "
    "that carry a team_order are neither reported nor deleted.",
)
def test_apply_aliases_requests_rosters_for_every_team_order(wp_connector):
    _wire_participants(wp_connector)

    apply_aliases(execute=False)

    params = wp_connector.get_rosters.call_args.kwargs["params"]
    assert params.get("all_team_orders")


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
