"""Tests for the proof-of-insurance attachment mapping in ChurchSyncer (Issue #154)."""

import pandas as pd
import pytest

from sync.churches import ChurchSyncer, INSURANCE_ATTACHMENT_COLUMN


class FakeConnector:
    """Minimal stand-in for WordPressConnector capturing the payloads it receives."""

    def __init__(self, existing=None):
        self._existing = existing or {}
        self.created = []
        self.updated = []

    def get_church_by_code(self, code):
        return self._existing.get(code)

    def create_church(self, data):
        self.created.append(data)
        return data

    def update_church_by_code(self, code, data):
        self.updated.append((code, data))
        return data


def _base_row(**overrides):
    row = {
        "Church Name": "Insurance Test Church",
        "Church Code": "INS",
        "Pastor Name": "Pastor Test",
        "Pastor Email": "pastor@ins.org",
        "Pastor Phone Number": "555-0001",
        "First Name": "Rep",
        "Last Name": "Test",
        "Your Email": "rep@ins.org",
        "Your Mobile Phone": "555-0002",
        "Your Church's Level of Sports Ministry": "Level 1",
    }
    row.update(overrides)
    return row


def _make_excel(tmp_path, rows):
    path = tmp_path / "churches.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return str(path)


def _new_stats():
    return {"churches": {"created": 0, "updated": 0, "errors": 0}}


def test_insurance_url_present_advances_pending_to_submitted(tmp_path):
    """A new church with an attachment URL is created as 'submitted'."""
    excel = _make_excel(tmp_path, [_base_row(**{INSURANCE_ATTACHMENT_COLUMN: "https://forms.example/abc.pdf"})])
    conn = FakeConnector()  # no existing church -> create path
    syncer = ChurchSyncer(conn, _new_stats())

    assert syncer.sync_from_excel(excel) is True
    assert len(conn.created) == 1
    payload = conn.created[0]
    assert payload["insurance_file_url"] == "https://forms.example/abc.pdf"
    assert payload["insurance_status"] == "submitted"


def test_insurance_status_not_downgraded_when_already_approved(tmp_path):
    """An approved church keeps its status even when a new URL is synced."""
    excel = _make_excel(tmp_path, [_base_row(**{INSURANCE_ATTACHMENT_COLUMN: "https://forms.example/new.pdf"})])
    conn = FakeConnector(existing={"INS": {"insurance_status": "approved"}})
    syncer = ChurchSyncer(conn, _new_stats())

    assert syncer.sync_from_excel(excel) is True
    assert len(conn.updated) == 1
    _, payload = conn.updated[0]
    assert payload["insurance_file_url"] == "https://forms.example/new.pdf"
    # status must NOT be forced back to 'submitted'
    assert "insurance_status" not in payload


def test_blank_insurance_cell_is_ignored(tmp_path):
    """Rows whose attachment cell is empty/NaN sync without insurance fields."""
    excel = _make_excel(tmp_path, [_base_row(**{INSURANCE_ATTACHMENT_COLUMN: ""})])
    conn = FakeConnector()
    syncer = ChurchSyncer(conn, _new_stats())

    assert syncer.sync_from_excel(excel) is True
    payload = conn.created[0]
    assert "insurance_file_url" not in payload
    assert "insurance_status" not in payload


def test_missing_insurance_column_is_backward_compatible(tmp_path):
    """Excel files without the attachment column sync exactly as before."""
    excel = _make_excel(tmp_path, [_base_row()])  # no insurance column at all
    conn = FakeConnector()
    syncer = ChurchSyncer(conn, _new_stats())

    assert syncer.sync_from_excel(excel) is True
    payload = conn.created[0]
    assert "insurance_file_url" not in payload


@pytest.mark.parametrize("blank", ["nan", "None", "  "])
def test_clean_insurance_url_blank_variants(blank):
    assert ChurchSyncer._clean_insurance_url(blank) == ""


def test_clean_insurance_url_trims_value():
    assert ChurchSyncer._clean_insurance_url("  https://x/y.pdf  ") == "https://x/y.pdf"
