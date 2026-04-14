"""
Unit tests for season_reset.SeasonResetter.

All tests run in mock mode (no real API calls).
"""
import pytest
from unittest.mock import MagicMock, patch
from season_reset import SeasonResetter, _build_archive_note, _build_reset_additional_fields


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_resetter(notes=None, get_person_ok=True, add_note_ok=True, update_ok=True):
    """Return a SeasonResetter with fully mocked connectors."""
    chm = MagicMock()
    wp  = MagicMock()

    from config import SF_FIELD_IDS
    mock_additional_fields = [
        {"field_id": SF_FIELD_IDS["PRIMARY_SPORT"],  "field_type": "dropdown",
         "selected_option_id": 199334, "value": "Volleyball - Men Team"},
        {"field_id": SF_FIELD_IDS["MY_ROLE"],        "field_type": "checkbox",
         "selected_option_ids": [199442], "value": "Athlete/Participant"},
    ]
    chm.get_person.return_value = (
        {"id": "111", "first_name": "Jerry", "last_name": "Phan",
         "additional_fields": mock_additional_fields}
        if get_person_ok else None
    )
    chm.get_group_people.return_value = [
        {"id": "111", "first_name": "Jerry", "last_name": "Phan",
         "additional_fields": mock_additional_fields},
        {"id": "222", "first_name": "Khoi",  "last_name": "Nguyen",
         "additional_fields": mock_additional_fields},
    ]
    chm.get_person_notes.return_value = notes if notes is not None else []
    chm.add_member_note.return_value = add_note_ok
    chm.update_person.return_value = update_ok

    wp.get_participants.return_value = [
        {"chmeetings_id": "111", "church_code": "RPC", "primary_sport": "Badminton",
         "primary_format": "Singles", "primary_partner": "", "secondary_sport": "",
         "secondary_format": "", "secondary_partner": "", "other_events": "",
         "is_church_member": 1, "approval_status": "approved", "parent_info": ""},
    ]

    return SeasonResetter(chm, wp), chm, wp


# ── _build_archive_note ───────────────────────────────────────────────────────

def test_build_archive_note_with_wp_data():
    person = {"id": "111", "first_name": "Jerry", "last_name": "Phan", "additional_fields": []}
    wp_p   = {"church_code": "RPC", "primary_sport": "Badminton", "primary_format": "Singles",
              "primary_partner": "", "secondary_sport": "", "secondary_format": "",
              "secondary_partner": "", "other_events": "", "is_church_member": 1,
              "approval_status": "approved", "parent_info": ""}
    note = _build_archive_note(2025, person, wp_p)
    assert "Sports Fest 2025 Archive" in note
    assert "Team: RPC" in note
    assert "Primary: Badminton (Singles)" in note
    assert "Member: Yes" in note
    assert "Pastor Approved: approved" in note


def test_build_archive_note_without_wp_data():
    person = {"id": "111", "first_name": "Jerry", "last_name": "Phan", "additional_fields": []}
    note = _build_archive_note(2025, person, None)
    assert "Sports Fest 2025 Archive" in note
    assert "No WordPress participant record found" in note


def test_build_reset_additional_fields_only_includes_set_fields():
    """Only fields that currently have a value should appear in the reset payload."""
    from config import SF_FIELD_IDS
    # Simulate a person who has Primary Sport and My role is set, but nothing else
    current_fields = [
        {"field_id": SF_FIELD_IDS["PRIMARY_SPORT"], "field_type": "dropdown",
         "selected_option_id": 199334, "value": "Volleyball - Men Team"},
        {"field_id": SF_FIELD_IDS["MY_ROLE"], "field_type": "checkbox",
         "selected_option_ids": [199442], "value": "Athlete/Participant"},
        {"field_id": SF_FIELD_IDS["NOTES_PROGRESS"], "field_type": "multi_line_text",
         "value": "Some notes here"},
    ]
    fields = _build_reset_additional_fields(current_fields)
    field_ids = [f["field_id"] for f in fields]

    assert SF_FIELD_IDS["PRIMARY_SPORT"] in field_ids    # had a value → included
    assert SF_FIELD_IDS["MY_ROLE"] in field_ids          # had a value → included
    assert SF_FIELD_IDS["NOTES_PROGRESS"] in field_ids   # had a value → included
    assert SF_FIELD_IDS["OTHER_EVENTS"] not in field_ids  # not set → excluded
    assert SF_FIELD_IDS["PRIMARY_PARTNER"] not in field_ids  # not set → excluded


def test_build_reset_additional_fields_empty_when_no_sf_fields_set():
    """Person with no SF fields set returns an empty reset payload."""
    current_fields = [
        {"field_id": 1055798, "field_type": "multiple_choice",  # unrelated field
         "selected_option_id": 136778, "value": "Some spiritual stage"},
    ]
    fields = _build_reset_additional_fields(current_fields)
    assert fields == []


def test_build_reset_additional_fields_correct_reset_values():
    """
    Check that reset values use the right property key for each field type
    and that field_type is preserved from the source field (required by the
    ChMeetings API — omitting it causes HTTP 500).
    """
    from config import SF_FIELD_IDS
    current_fields = [
        {"field_id": SF_FIELD_IDS["MY_ROLE"],       "field_type": "checkbox",
         "selected_option_ids": [199442]},
        {"field_id": SF_FIELD_IDS["PRIMARY_SPORT"],  "field_type": "dropdown",
         "selected_option_id": 199334},
        {"field_id": SF_FIELD_IDS["IS_MEMBER"],      "field_type": "multiple_choice",
         "selected_option_id": 199355},
        {"field_id": SF_FIELD_IDS["NOTES_PROGRESS"], "field_type": "multi_line_text",
         "value": "some notes"},
        {"field_id": SF_FIELD_IDS["PARENT_NAME"],    "field_type": "text",
         "value": "Dad Ho"},
    ]
    fields = _build_reset_additional_fields(current_fields)
    by_id = {f["field_id"]: f for f in fields}

    # Clearing values
    assert by_id[SF_FIELD_IDS["MY_ROLE"]]["selected_option_ids"] == []
    assert by_id[SF_FIELD_IDS["PRIMARY_SPORT"]]["selected_option_id"] is None
    assert by_id[SF_FIELD_IDS["IS_MEMBER"]]["selected_option_id"] is None
    assert by_id[SF_FIELD_IDS["NOTES_PROGRESS"]]["value"] is None
    assert by_id[SF_FIELD_IDS["PARENT_NAME"]]["value"] is None

    # field_type must be present and correct (API rejects payloads without it)
    assert by_id[SF_FIELD_IDS["MY_ROLE"]]["field_type"] == "checkbox"
    assert by_id[SF_FIELD_IDS["PRIMARY_SPORT"]]["field_type"] == "dropdown"
    assert by_id[SF_FIELD_IDS["IS_MEMBER"]]["field_type"] == "multiple_choice"
    assert by_id[SF_FIELD_IDS["NOTES_PROGRESS"]]["field_type"] == "multi_line_text"
    assert by_id[SF_FIELD_IDS["PARENT_NAME"]]["field_type"] == "text"


# ── SeasonResetter.run — single person (--person-id) ─────────────────────────

@patch("season_reset.Config")
def test_run_single_person_dry_run(mock_cfg):
    resetter, chm, wp = _make_resetter()
    result = resetter.run(2025, dry_run=True, person_id="111")
    assert result is True
    chm.get_person.assert_called_once_with("111")
    chm.add_member_note.assert_not_called()   # dry-run: no writes
    chm.update_person.assert_not_called()


@patch("season_reset.Config")
def test_run_single_person_live(mock_cfg):
    resetter, chm, wp = _make_resetter()
    result = resetter.run(2025, person_id="111")
    assert result is True
    chm.get_person_notes.assert_called_once_with("111")
    chm.add_member_note.assert_called_once()
    chm.update_person.assert_called_once()


@patch("season_reset.Config")
def test_run_single_person_not_found(mock_cfg):
    resetter, chm, wp = _make_resetter(get_person_ok=False)
    result = resetter.run(2025, person_id="999")
    assert result is False
    chm.add_member_note.assert_not_called()
    chm.update_person.assert_not_called()


# ── Duplicate note prevention ─────────────────────────────────────────────────

@patch("season_reset.Config")
def test_duplicate_note_is_skipped(mock_cfg):
    """If a 'Sports Fest 2025 Archive' note already exists, don't write another."""
    existing = [{"note": "Sports Fest 2025 Archive — 2026-01-01 | Team: RPC | ..."}]
    resetter, chm, wp = _make_resetter(notes=existing)
    result = resetter.run(2025, person_id="111")
    assert result is True
    chm.add_member_note.assert_not_called()   # skipped because note exists


@patch("season_reset.Config")
def test_different_year_note_does_not_block(mock_cfg):
    """A note for a different year should not prevent writing the 2025 note."""
    existing = [{"note": "Sports Fest 2024 Archive — 2025-01-10 | Team: RPC | ..."}]
    resetter, chm, wp = _make_resetter(notes=existing)
    result = resetter.run(2025, person_id="111")
    assert result is True
    chm.add_member_note.assert_called_once()  # 2025 note is new → write it


# ── archive-only / reset-only flags ──────────────────────────────────────────

@patch("season_reset.Config")
def test_archive_only_skips_field_reset(mock_cfg):
    resetter, chm, wp = _make_resetter()
    result = resetter.run(2025, archive_only=True, person_id="111")
    assert result is True
    chm.add_member_note.assert_called_once()
    chm.update_person.assert_not_called()


@patch("season_reset.Config")
def test_reset_only_skips_archive_note(mock_cfg):
    resetter, chm, wp = _make_resetter()
    result = resetter.run(2025, reset_only=True, person_id="111")
    assert result is True
    chm.add_member_note.assert_not_called()
    chm.update_person.assert_called_once()
