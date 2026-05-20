import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sync.consent_404_investigator import Consent404Investigator


def _make_wp_participant(
    *,
    participant_id="10",
    chmeetings_id="3630880",
    first_name="Jerry",
    last_name="Phan",
    email="jerry@example.com",
    phone="562-555-0101",
    birthdate="2008-04-15",
    church_code="RPC",
    created_at="2026-05-17 10:00:00",
    updated_at="2026-05-19 17:00:00",
):
    return {
        "participant_id": participant_id,
        "chmeetings_id": chmeetings_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "birthdate": birthdate,
        "church_code": church_code,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _make_chm_person(
    *,
    chmeetings_id="9999999",
    first_name="Jerry",
    last_name="Phan",
    email="jerry@example.com",
    mobile="562-555-0101",
    birth_date="2008-04-15",
    updated_on="2026-05-19T17:00:00+00:00",
):
    return {
        "id": chmeetings_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "mobile": mobile,
        "birth_date": birth_date,
        "updated_on": updated_on,
    }


@pytest.fixture()
def investigator(tmp_path, mocker):
    chm = MagicMock()
    chm.authenticate.return_value = True
    wp = MagicMock()
    tool = Consent404Investigator(chm, wp, output_dir=tmp_path)

    captured = {}

    def capture_write(summary_rows, candidate_rows, output_file=None):
        captured["summary_rows"] = summary_rows
        captured["candidate_rows"] = candidate_rows
        return Path(output_file) if output_file else tmp_path / "consent_404_investigation.xlsx"

    mocker.patch.object(tool, "_write_audit_file", side_effect=capture_write)
    return tool, chm, wp, captured


def test_parse_log_cases_extracts_unique_404_entries(investigator, tmp_path):
    tool, _, _, _ = investigator
    log_file = tmp_path / "sportsfest_20260519.log"
    log_file.write_text(
        "\n".join(
            [
                "2026-05-19 18:49:30 | WARNING | Could not retrieve ChMeetings person 3630880 while processing consent row 22",
                "2026-05-19 18:49:30 | WARNING | Could not retrieve ChMeetings person 3630880 while processing consent row 22",
                "2026-05-19 18:49:39 | WARNING | Could not retrieve ChMeetings person 3615930 while processing consent row 117",
            ]
        ),
        encoding="utf-8",
    )

    cases = tool._parse_log_cases(log_file)

    assert cases == [
        {"old_chmeetings_id": "3630880", "consent_row": 22, "log_line_number": 1},
        {"old_chmeetings_id": "3615930", "consent_row": 117, "log_line_number": 3},
    ]


def test_run_flags_likely_reregistered_synced_case(investigator, tmp_path):
    tool, chm, wp, captured = investigator
    log_file = tmp_path / "sportsfest_20260519.log"
    log_file.write_text(
        "2026-05-19 18:49:30 | WARNING | Could not retrieve ChMeetings person 3630880 while processing consent row 22\n",
        encoding="utf-8",
    )

    wp.get_participants.return_value = [
        _make_wp_participant(
            participant_id="10",
            chmeetings_id="3630880",
        ),
        _make_wp_participant(
            participant_id="20",
            chmeetings_id="9999999",
        ),
    ]
    chm.get_people.return_value = [_make_chm_person(chmeetings_id="9999999")]

    summary = tool.run(log_file=str(log_file))

    assert summary["api_error"] == 0
    assert summary["likely_reregistered_synced"] == 1
    assert captured["summary_rows"][0]["Investigation Result"] == "likely_reregistered_synced"
    assert captured["summary_rows"][0]["Best WP Candidate ChM ID"] == "9999999"
    assert captured["summary_rows"][0]["Best ChM Candidate ID"] == "9999999"
    assert len(captured["candidate_rows"]) == 2


def test_run_flags_likely_deleted_when_no_replacement_found(investigator, tmp_path):
    tool, chm, wp, captured = investigator
    log_file = tmp_path / "sportsfest_20260519.log"
    log_file.write_text(
        "2026-05-19 18:49:30 | WARNING | Could not retrieve ChMeetings person 3630880 while processing consent row 22\n",
        encoding="utf-8",
    )

    wp.get_participants.return_value = [
        _make_wp_participant(
            participant_id="10",
            chmeetings_id="3630880",
            first_name="Deleted",
            last_name="Player",
            email="deleted@example.com",
            phone="562-555-0199",
            birthdate="2001-01-01",
        ),
    ]
    chm.get_people.return_value = [
        _make_chm_person(
            chmeetings_id="8888888",
            first_name="Another",
            last_name="Person",
            email="another@example.com",
            mobile="562-555-0200",
            birth_date="2000-01-01",
        )
    ]

    summary = tool.run(log_file=str(log_file))

    assert summary["api_error"] == 0
    assert summary["likely_deleted_or_removed"] == 1
    assert captured["summary_rows"][0]["Investigation Result"] == "likely_deleted_or_removed"
    assert captured["candidate_rows"] == []


def test_run_prefers_birthdate_name_candidate_over_family_email_phone_collision(
    investigator, tmp_path
):
    tool, chm, wp, captured = investigator
    log_file = tmp_path / "sportsfest_20260519.log"
    log_file.write_text(
        "2026-05-19 18:50:08 | WARNING | Could not retrieve ChMeetings person 4367410 while processing consent row 400\n",
        encoding="utf-8",
    )

    wp.get_participants.return_value = [
        _make_wp_participant(
            participant_id="270",
            chmeetings_id="4367410",
            first_name="Samantha",
            last_name="Tran",
            email="tranyenquoc@yahoo.com",
            phone="7147246655",
            birthdate="2009-05-12",
            church_code="WAG",
        ),
        _make_wp_participant(
            participant_id="272",
            chmeetings_id="4367408",
            first_name="Quoc",
            last_name="Tran",
            email="tranyenquoc@yahoo.com",
            phone="7147246655",
            birthdate="1975-10-10",
            church_code="WAG",
        ),
        _make_wp_participant(
            participant_id="414",
            chmeetings_id="4371571",
            first_name="Samantha",
            last_name="Tran",
            email="samanthathienantran@gmail.com",
            phone="6574130580",
            birthdate="2009-05-12",
            church_code="WAG",
        ),
    ]
    chm.get_people.return_value = [
        _make_chm_person(
            chmeetings_id="4367408",
            first_name="Quoc",
            last_name="Tran",
            email="tranyenquoc@yahoo.com",
            mobile="7147246655",
            birth_date="1975-10-10",
        ),
        _make_chm_person(
            chmeetings_id="4371571",
            first_name="Samantha",
            last_name="Tran",
            email="samanthathienantran@gmail.com",
            mobile="6574130580",
            birth_date="2009-05-12",
        ),
    ]

    summary = tool.run(log_file=str(log_file))

    assert summary["api_error"] == 0
    assert summary["likely_reregistered_synced"] == 1
    assert captured["summary_rows"][0]["Best WP Candidate ChM ID"] == "4371571"
    assert captured["summary_rows"][0]["Best ChM Candidate ID"] == "4371571"
