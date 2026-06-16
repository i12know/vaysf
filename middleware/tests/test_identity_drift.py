# Begin of tests/test_identity_drift.py
"""Tests for approval identity drift detection (Issue #171).

Verifies that _detect_identity_drift, _age_at_event, and _sync_single_participant
correctly identify and handle post-approval identity changes.
"""
import datetime
import pytest
from unittest.mock import MagicMock, call
from sync.participants import ParticipantSyncer
from config import APPROVAL_STATUS, RULE_LEVEL, VALIDATION_SEVERITY, SPORT_UNSELECTED


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def syncer(mocker):
    """ParticipantSyncer with fully mocked connectors."""
    mock_chm = MagicMock()
    mock_wp = MagicMock()
    mock_stats = {
        "participants": {"created": 0, "updated": 0, "errors": 0},
        "rosters": {"created": 0, "deleted": 0, "errors": 0, "updated": 0},
        "validation_issues": {
            "created": 0, "updated": 0, "resolved": 0,
            "unchanged": 0, "skipped": 0, "errors": 0,
        },
        "approvals": {"created": 0, "updated": 0, "errors": 0},
    }
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")
    return ParticipantSyncer(mock_chm, mock_wp, mock_stats, {})


def _wp_participant(overrides=None):
    """Return a baseline WordPress participant snapshot."""
    base = {
        "participant_id": 413,
        "chmeetings_id": "4371570",
        "first_name": "Matthew",
        "last_name": "Tran",
        "email": "tran.thgam@gmail.com",
        "phone": "(714) 657-2461",
        "gender": "Male",
        "birthdate": "2008-04-23",
        "church_code": "WAG",
        "primary_sport": "Basketball - Men Team",
        "secondary_sport": SPORT_UNSELECTED,
        "other_events": "",
        "approval_status": APPROVAL_STATUS["APPROVED"],
        "is_church_member": False,
        "membership_claim_at_approval": None,
        "photo_url": "",
        "created_at": "2026-05-01 10:00:00",
    }
    if overrides:
        base.update(overrides)
    return base


def _live_mapped(overrides=None):
    """Return a baseline live-ChMeetings mapped participant (same person, no drift)."""
    base = {
        "chmeetings_id": "4371570",
        "first_name": "Matthew",
        "last_name": "Tran",
        "email": "tran.thgam@gmail.com",
        "phone": "(714) 657-2461",
        "gender": "Male",
        "birthdate": "2008-04-23",
        "church_code": "WAG",
        "primary_sport": "Basketball - Men Team",
        "secondary_sport": SPORT_UNSELECTED,
        "other_events": "",
        "approval_status": APPROVAL_STATUS["PENDING"],
        "is_church_member": False,
        "photo_url": "",
        "roles": "Athlete/Participant",
        "completion_checklist": "",
        "consent_status": False,
        "primary_format": "",
        "primary_partner": "",
        "secondary_format": "",
        "secondary_partner": "",
        "parent_info": "",
    }
    if overrides:
        base.update(overrides)
    return base


# ── _age_at_event tests ───────────────────────────────────────────────────────

class TestAgeAtEvent:
    def test_returns_correct_age(self, mocker):
        mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")
        assert ParticipantSyncer._age_at_event("2008-04-23") == 18  # birthday before event
        assert ParticipantSyncer._age_at_event("2006-05-23") == 20  # birthday after July cutoff

    def test_birthday_on_event_date(self, mocker):
        mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")
        assert ParticipantSyncer._age_at_event("2008-07-18") == 18

    def test_birthday_after_event_date(self, mocker):
        mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")
        assert ParticipantSyncer._age_at_event("2008-12-31") == 17  # hasn't turned 18 yet

    def test_returns_none_for_blank(self, mocker):
        mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")
        assert ParticipantSyncer._age_at_event("") is None
        assert ParticipantSyncer._age_at_event(None) is None


# ── _detect_identity_drift tests ─────────────────────────────────────────────

class TestDetectIdentityDrift:
    def test_no_drift_returns_empty(self, syncer):
        hard, soft = syncer._detect_identity_drift(_live_mapped(), _wp_participant())
        assert hard == []
        assert soft == []

    def test_name_change_is_hard_drift(self, syncer):
        live = _live_mapped({"first_name": "Andy", "last_name": "Nguyen"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        assert len(hard) == 2
        fields = {d["field"] for d in hard}
        assert "first_name" in fields
        assert "last_name" in fields
        assert soft == []

    def test_gender_change_is_hard_drift(self, syncer):
        live = _live_mapped({"gender": "Female"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        assert any(d["field"] == "gender" for d in hard)

    def test_church_change_is_hard_drift(self, syncer):
        live = _live_mapped({"church_code": "RPC"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        assert any(d["field"] == "church_code" for d in hard)

    def test_primary_sport_change_is_hard_drift(self, syncer):
        live = _live_mapped({"primary_sport": "Volleyball - Men Team"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        assert any(d["field"] == "primary_sport" for d in hard)

    def test_secondary_sport_change_is_hard_drift(self, syncer):
        live = _live_mapped({"secondary_sport": "Badminton"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        assert any(d["field"] == "secondary_sport" for d in hard)

    def test_unselected_vs_blank_secondary_sport_is_not_drift(self, syncer):
        """SPORT_UNSELECTED and '' should compare equal."""
        live = _live_mapped({"secondary_sport": SPORT_UNSELECTED})
        wp = _wp_participant({"secondary_sport": ""})
        hard, soft = syncer._detect_identity_drift(live, wp)
        sport_fields = [d["field"] for d in hard]
        assert "secondary_sport" not in sport_fields

    def test_other_events_change_is_hard_drift(self, syncer):
        live = _live_mapped({"other_events": "Bible Challenge"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        assert any(d["field"] == "other_events" for d in hard)

    def test_other_events_order_does_not_matter(self, syncer):
        live = _live_mapped({"other_events": "Bible Challenge, Tug of War"})
        wp = _wp_participant({"other_events": "Tug of War, Bible Challenge"})
        hard, soft = syncer._detect_identity_drift(live, wp)
        sport_fields = [d["field"] for d in hard]
        assert "other_events" not in sport_fields

    def test_birthdate_age_change_is_hard_drift(self, syncer):
        """2008-04-23 → 2006-05-23: age at 2026-07-18 changes from 18 to 20."""
        live = _live_mapped({"birthdate": "2006-05-23"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        assert any(d["field"] == "birthdate" for d in hard)
        assert soft == []

    def test_birthdate_correction_same_age_is_soft_drift(self, syncer):
        """2008-04-23 → 2008-04-22: age at event stays 18; should be soft drift only."""
        live = _live_mapped({"birthdate": "2008-04-22"})
        hard, soft = syncer._detect_identity_drift(live, _wp_participant())
        bd_hard = [d for d in hard if d["field"] == "birthdate"]
        assert bd_hard == []
        assert any(d["field"] == "birthdate" for d in soft)

    def test_multiple_hard_drifts_all_reported(self, syncer):
        live = _live_mapped({
            "first_name": "Andy",
            "last_name": "Nguyen",
            "birthdate": "2006-05-23",
        })
        hard, _ = syncer._detect_identity_drift(live, _wp_participant())
        fields = {d["field"] for d in hard}
        assert "first_name" in fields
        assert "last_name" in fields
        assert "birthdate" in fields


# ── _reset_approval_for_drift tests ──────────────────────────────────────────

class TestResetApprovalForDrift:
    def test_resets_approval_record(self, syncer):
        approval = {"approval_id": 182, "approval_status": "approved"}
        syncer.wordpress_connector.get_approvals.return_value = [approval]
        syncer.wordpress_connector.update_approval.return_value = {"approval_id": 182}

        syncer._reset_approval_for_drift(413, "4371570", [{"label": "First name"}])

        syncer.wordpress_connector.update_approval.assert_called_once_with(
            182,
            {"approval_status": APPROVAL_STATUS["PENDING"], "synced_to_chmeetings": False},
        )

    def test_no_approval_record_logs_warning(self, syncer, caplog):
        syncer.wordpress_connector.get_approvals.return_value = []
        import logging
        with caplog.at_level(logging.WARNING):
            syncer._reset_approval_for_drift(413, "4371570", [{"label": "First name"}])
        syncer.wordpress_connector.update_approval.assert_not_called()


# ── _sync_single_participant integration tests ────────────────────────────────

def _make_chm_person(overrides=None):
    """Build a minimal ChMeetings API person response using exact CHM_FIELDS names."""
    base = {
        "id": "4371570",
        "first_name": "Andy",
        "last_name": "Nguyen",
        "email": "andnyguyen24@gmail.com",
        "mobile": "(714) 391-1875",
        "gender": "Male",
        "birth_date": "2006-05-23",
        "photo": "",
        "updated_on": "2026-06-15T16:30:12.280-07:00",
        "additional_fields": [
            {"field_name": "Church Team", "value": "WAG"},
            {"field_name": "My role is", "value": "Athlete/Participant"},
            {"field_name": "Primary Sport", "value": "Basketball - Men Team"},
            {"field_name": "Secondary Sport", "value": ""},
            {"field_name": "Other Events", "value": ""},
            {"field_name": "Primary Racquet Sport Format", "value": ""},
            {"field_name": "Primary Racquet Sport Partner (if applied)", "value": ""},
            {"field_name": "Secondary Racquet Sport Format", "value": ""},
            {"field_name": "Secondary Racquet Sport Partner (if applied)", "value": ""},
            {"field_name": "Completion Check List", "value": ""},
            {"field_name": "Name of my parents or legal guardian", "value": ""},
            {"field_name": "Email of my parents or legal guardian", "value": ""},
            {"field_name": "Cell phone of my parents or legal guardian", "value": ""},
            {"field_name": "Would the team's Senior Pastor say that you belong to his church?", "value": "No"},
        ],
    }
    if overrides:
        base.update(overrides)
    return base


def _setup_syncer_for_integration(syncer, wp_snapshot, chm_person, existing_approval=None):
    """Wire up connector mocks for _sync_single_participant tests."""
    syncer.chm_connector.get_person.return_value = chm_person
    syncer.chm_connector.last_get_person_status = "ok"
    syncer.wordpress_connector.get_participants.return_value = [wp_snapshot]
    if existing_approval:
        syncer.wordpress_connector.get_approvals.return_value = [existing_approval]
    else:
        syncer.wordpress_connector.get_approvals.return_value = []
    syncer.wordpress_connector.update_participant.return_value = dict(wp_snapshot, participant_id=413)
    syncer.wordpress_connector.get_rosters.return_value = []
    syncer.wordpress_connector.get_validation_issues.return_value = []
    syncer.churches_cache = {"WAG": {"church_id": 16, "church_code": "WAG"}}


class TestSyncSingleParticipantDrift:
    def test_no_drift_preserves_approved_status(self, syncer):
        """Identical live data → approval status preserved, no approval reset."""
        wp = _wp_participant()
        chm = _make_chm_person({
            "first_name": "Matthew",
            "last_name": "Tran",
            "birth_date": "2008-04-23",
        })
        _setup_syncer_for_integration(syncer, wp, chm)

        syncer._sync_single_participant("4371570")

        # update_approval should NOT be called (no drift)
        for c in syncer.wordpress_connector.update_approval.call_args_list:
            args, kwargs = c
            payload = args[1] if len(args) > 1 else kwargs.get("approval_data", {})
            assert payload.get("approval_status") != APPROVAL_STATUS["PENDING"], (
                "update_approval should not reset to pending when there is no drift"
            )

        # The participant update should carry 'approved' status
        call_args = syncer.wordpress_connector.update_participant.call_args
        payload = call_args[0][1]
        assert payload["approval_status"] == APPROVAL_STATUS["APPROVED"]

    def test_hard_drift_resets_to_reapproval_required(self, syncer):
        """Name + birthdate changed after approval → reapproval_required."""
        wp = _wp_participant()
        chm = _make_chm_person()  # Andy Nguyen, born 2006-05-23
        approval = {"approval_id": 182, "approval_status": "approved"}
        _setup_syncer_for_integration(syncer, wp, chm, existing_approval=approval)
        syncer.wordpress_connector.update_approval.return_value = {"approval_id": 182}

        syncer._sync_single_participant("4371570")

        # Approval record must be reset to pending
        reset_calls = [
            c for c in syncer.wordpress_connector.update_approval.call_args_list
            if (c[0][1] if len(c[0]) > 1 else {}).get("approval_status") == APPROVAL_STATUS["PENDING"]
        ]
        assert len(reset_calls) >= 1, "Expected approval record to be reset to pending"

        # Participant update must use reapproval_required status
        call_args = syncer.wordpress_connector.update_participant.call_args
        payload = call_args[0][1]
        assert payload["approval_status"] == APPROVAL_STATUS["REAPPROVAL_REQUIRED"]

    def test_hard_drift_creates_drift_validation_issue(self, syncer):
        """Hard drift must produce an approval_identity_drift validation issue."""
        wp = _wp_participant()
        chm = _make_chm_person()  # Different person
        approval = {"approval_id": 182, "approval_status": "approved"}
        _setup_syncer_for_integration(syncer, wp, chm, existing_approval=approval)
        syncer.wordpress_connector.update_approval.return_value = {"approval_id": 182}

        syncer._sync_single_participant("4371570")

        created_issues = [
            c[0][0] for c in syncer.wordpress_connector.create_validation_issue.call_args_list
        ]
        drift_issues = [i for i in created_issues if i.get("issue_type") == "approval_identity_drift"]
        assert len(drift_issues) == 1
        assert drift_issues[0]["severity"] == VALIDATION_SEVERITY["ERROR"]

    def test_birthdate_correction_same_age_preserves_approval(self, syncer):
        """Birthdate corrected but age unchanged → approval preserved, warning issued."""
        wp = _wp_participant()
        # Change day only: 2008-04-23 → 2008-04-22; both are age 18 at 2026-07-18
        chm = _make_chm_person({
            "first_name": "Matthew",
            "last_name": "Tran",
            "birth_date": "2008-04-22",
        })
        _setup_syncer_for_integration(syncer, wp, chm)

        syncer._sync_single_participant("4371570")

        # Approval should NOT be reset
        for c in syncer.wordpress_connector.update_approval.call_args_list:
            payload = c[0][1] if len(c[0]) > 1 else {}
            assert payload.get("approval_status") != APPROVAL_STATUS["PENDING"]

        # Participant status must stay approved
        call_args = syncer.wordpress_connector.update_participant.call_args
        payload = call_args[0][1]
        assert payload["approval_status"] == APPROVAL_STATUS["APPROVED"]

        # A warning validation issue should be created
        created_issues = [
            c[0][0] for c in syncer.wordpress_connector.create_validation_issue.call_args_list
        ]
        bd_issues = [i for i in created_issues if i.get("issue_type") == "approval_birthdate_correction"]
        assert len(bd_issues) == 1
        assert bd_issues[0]["severity"] == VALIDATION_SEVERITY["WARNING"]

    def test_denied_participant_with_drift_resets_to_reapproval(self, syncer):
        """Drift after a 'denied' decision also triggers reapproval_required."""
        wp = _wp_participant({"approval_status": APPROVAL_STATUS["DENIED"]})
        chm = _make_chm_person()  # Andy Nguyen
        approval = {"approval_id": 182, "approval_status": "denied"}
        _setup_syncer_for_integration(syncer, wp, chm, existing_approval=approval)
        syncer.wordpress_connector.update_approval.return_value = {"approval_id": 182}

        syncer._sync_single_participant("4371570")

        call_args = syncer.wordpress_connector.update_participant.call_args
        payload = call_args[0][1]
        assert payload["approval_status"] == APPROVAL_STATUS["REAPPROVAL_REQUIRED"]

    def test_pending_participant_no_drift_check(self, syncer):
        """Drift guard must not run for participants who are not yet approved/denied."""
        wp = _wp_participant({"approval_status": APPROVAL_STATUS["PENDING"]})
        # Even with completely different data, no drift reset should happen
        chm = _make_chm_person()  # Andy Nguyen
        _setup_syncer_for_integration(syncer, wp, chm)

        syncer._sync_single_participant("4371570")

        # update_approval should not be called with a pending reset
        for c in syncer.wordpress_connector.update_approval.call_args_list:
            payload = c[0][1] if len(c[0]) > 1 else {}
            assert payload.get("approval_status") != APPROVAL_STATUS["PENDING"], (
                "Drift guard should not fire for non-approved/denied participants"
            )

# End of tests/test_identity_drift.py
