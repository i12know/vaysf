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

    chm.get_person.return_value = (
        {"id": "111", "first_name": "Jerry", "last_name": "Phan", "additional_fields": []}
        if get_person_ok else None
    )
    chm.get_group_people.return_value = [
        {"id": "111", "first_name": "Jerry", "last_name": "Phan", "additional_fields": []},
        {"id": "222", "first_name": "Khoi",  "last_name": "Nguyen", "additional_fields": []},
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


def test_build_reset_additional_fields_covers_all_field_types():
    from config import SF_CHECKBOX_FIELD_IDS, SF_DROPDOWN_FIELD_IDS, SF_TEXT_FIELD_IDS
    fields = _build_reset_additional_fields()
    expected_count = len(SF_CHECKBOX_FIELD_IDS) + len(SF_DROPDOWN_FIELD_IDS) + len(SF_TEXT_FIELD_IDS)
    assert len(fields) == expected_count

    checkbox_entries  = [f for f in fields if "selected_option_ids" in f]
    dropdown_entries  = [f for f in fields if "selected_option_id" in f]
    text_entries      = [f for f in fields if "value" in f]

    assert len(checkbox_entries) == len(SF_CHECKBOX_FIELD_IDS)
    assert len(dropdown_entries) == len(SF_DROPDOWN_FIELD_IDS)
    assert len(text_entries)     == len(SF_TEXT_FIELD_IDS)

    for e in checkbox_entries:
        assert e["selected_option_ids"] == []
    for e in dropdown_entries:
        assert e["selected_option_id"] is None
    for e in text_entries:
        assert e["value"] is None


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
