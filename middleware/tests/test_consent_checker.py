import os
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SF_FIELD_IDS
from sync.consent_checker import CONSENT_CHECKLIST_OPTION_ID, ConsentChecker


def _mock_consent_export(mocker, rows):
    mocker.patch("sync.consent_checker.pd.read_excel", return_value=pd.DataFrame(rows))


def _make_wp_participant(
    *,
    chmeetings_id="111",
    first_name="Jerry",
    last_name="Phan",
    email="jerry@example.com",
    phone="562-555-0101",
    birthdate="2008-04-15",
    church_code="RPC",
):
    return {
        "participant_id": 1,
        "chmeetings_id": chmeetings_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "birthdate": birthdate,
        "church_code": church_code,
    }


def _make_chm_person(
    *,
    chmeetings_id="111",
    first_name="Jerry",
    last_name="Phan",
    selected_option_ids=None,
):
    return {
        "id": chmeetings_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": "jerry@example.com",
        "mobile": "562-555-0101",
        "birthdate": "2008-04-15",
        "additional_fields": [
            {
                "field_id": SF_FIELD_IDS["CHECKLIST"],
                "field_type": "checkbox",
                "selected_option_ids": selected_option_ids or [],
            }
        ],
    }


@pytest.fixture()
def consent_checker(mocker):
    chm = MagicMock()
    chm.authenticate.return_value = True
    chm.update_person.return_value = True
    wp = MagicMock()
    captured = {}

    mocker.patch("sync.consent_checker.time.sleep", return_value=None)
    checker = ConsentChecker(chm, wp)
    mocker.patch.object(
        checker,
        "_write_audit_file",
        side_effect=lambda rows: captured.setdefault("rows", rows),
    )
    return checker, chm, wp, captured


def _read_audit(captured):
    assert "rows" in captured
    return pd.DataFrame(captured["rows"]).fillna("")


def test_check_consent_all_fields_match_auto_checks(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
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
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()

    summary = checker.run("consent.xlsx")

    assert summary["checked"] == 1
    assert summary["api_error"] == 0
    chm.update_person.assert_called_once()
    update_fields = chm.update_person.call_args.args[3]
    assert update_fields == [
        {
            "field_id": SF_FIELD_IDS["CHECKLIST"],
            "field_type": "checkbox",
            "selected_option_ids": [CONSENT_CHECKLIST_OPTION_ID],
        }
    ]

    audit = _read_audit(captured)
    assert audit.loc[0, "Action Taken"] == "checked"
    assert int(audit.loc[0, "Score"]) == 100


def test_check_consent_birthdate_plus_phone_is_above_threshold(consent_checker, mocker):
    checker, chm, wp, _ = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Wrong",
                "Last Name": "Name",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "different@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()

    summary = checker.run("consent.xlsx")

    assert summary["checked"] == 1
    chm.update_person.assert_called_once()


def test_check_consent_birthdate_plus_email_is_above_threshold(consent_checker, mocker):
    checker, chm, wp, _ = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Wrong",
                "Last Name": "Name",
                "Athlete Mobile Phone": "9995550101",
                "Athlete Email": "jerry@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()

    summary = checker.run("consent.xlsx")

    assert summary["checked"] == 1
    chm.update_person.assert_called_once()


def test_check_consent_phone_plus_email_is_above_threshold(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Wrong",
                "Last Name": "Name",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "jerry@example.com",
                "Athlete Birthdate": "2007-01-01",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()

    summary = checker.run("consent.xlsx")

    assert summary["checked"] == 1
    chm.get_person.assert_called_once()
    chm.update_person.assert_called_once()

    audit = _read_audit(captured)
    assert audit.loc[0, "Action Taken"] == "checked"
    assert int(audit.loc[0, "Score"]) == 51


def test_check_consent_birthdate_plus_name_stays_low_confidence(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Jerry",
                "Last Name": "Phan",
                "Athlete Mobile Phone": "9995550101",
                "Athlete Email": "different@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]

    summary = checker.run("consent.xlsx")

    assert summary["low_confidence"] == 1
    chm.get_person.assert_not_called()
    chm.update_person.assert_not_called()

    audit = _read_audit(captured)
    assert audit.loc[0, "Action Taken"] == "low_confidence"
    assert int(audit.loc[0, "Score"]) == 49


def test_check_consent_already_checked_is_skipped(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Jerry",
                "Last Name": "Phan",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "jerry@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person(
        selected_option_ids=[199608, CONSENT_CHECKLIST_OPTION_ID]
    )

    summary = checker.run("consent.xlsx")

    assert summary["skipped_already_done"] == 1
    chm.update_person.assert_not_called()

    audit = _read_audit(captured)
    assert audit.loc[0, "Action Taken"] == "skipped_already_done"


def test_check_consent_duplicate_rows_use_latest_submission_on_tie(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Older",
                "Last Name": "Guardian",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "wrong1@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am the parent or legal guardian and am signing this Agreement on behalf of a minor participant (under age 18).",
                "Full Name of the parents or legal guardian": "Older Guardian",
                "Email of the parents or legal guardian": "older@example.com",
                "Cell phone of the parents or legal guardian": "5551112222",
                "Submission Date": "2026-05-08 08:00:00",
            },
            {
                "First Name": "Newer",
                "Last Name": "Guardian",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "wrong2@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am the parent or legal guardian and am signing this Agreement on behalf of a minor participant (under age 18).",
                "Full Name of the parents or legal guardian": "Newer Guardian",
                "Email of the parents or legal guardian": "newer@example.com",
                "Cell phone of the parents or legal guardian": "5551113333",
                "Submission Date": "2026-05-08 09:00:00",
            },
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()

    summary = checker.run("consent.xlsx")

    assert summary["checked"] == 1
    assert summary["duplicates_collapsed"] == 1
    assert chm.get_person.call_count == 1
    assert chm.update_person.call_count == 1

    audit = _read_audit(captured)
    assert audit.loc[0, "Consent Row Name"] == "Newer Guardian"
    assert int(audit.loc[0, "Duplicate Rows Collapsed"]) == 1


def test_check_consent_guardian_row_matches_on_athlete_fields(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Parent",
                "Last Name": "Signer",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "jerry@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am the parent or legal guardian and am signing this Agreement on behalf of a minor participant (under age 18).",
                "Full Name of the parents or legal guardian": "Parent Signer",
                "Email of the parents or legal guardian": "parent@example.com",
                "Cell phone of the parents or legal guardian": "5551113333",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()

    summary = checker.run("consent.xlsx")

    assert summary["checked"] == 1
    audit = _read_audit(captured)
    assert audit.loc[0, "Consent Form Signer Type"] == "guardian"
    assert int(audit.loc[0, "Score"]) == 84


def test_check_consent_unmatched_row_goes_to_audit(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Nobody",
                "Last Name": "Match",
                "Athlete Mobile Phone": "9999999999",
                "Athlete Email": "nobody@example.com",
                "Athlete Birthdate": "2001-01-01",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]

    summary = checker.run("consent.xlsx")

    assert summary["unmatched"] == 1
    chm.get_person.assert_not_called()
    chm.update_person.assert_not_called()

    audit = _read_audit(captured)
    assert audit.loc[0, "Action Taken"] == "no_match"


def test_check_consent_dry_run_skips_update_calls(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Jerry",
                "Last Name": "Phan",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "jerry@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()

    summary = checker.run("consent.xlsx", dry_run=True)

    assert summary["dry_run"] == 1
    chm.update_person.assert_not_called()

    audit = _read_audit(captured)
    assert audit.loc[0, "Action Taken"] == "dry_run"


def test_check_consent_update_failure_is_reported(consent_checker, mocker):
    checker, chm, wp, captured = consent_checker
    _mock_consent_export(
        mocker,
        [
            {
                "First Name": "Jerry",
                "Last Name": "Phan",
                "Athlete Mobile Phone": "5625550101",
                "Athlete Email": "jerry@example.com",
                "Athlete Birthdate": "2008-04-15",
                "Select one:": "I am 18 or older and am signing this Agreement on my own behalf.",
                "Full Name of the parents or legal guardian": "",
                "Email of the parents or legal guardian": "",
                "Cell phone of the parents or legal guardian": "",
                "Submission Date": "2026-05-08 10:00:00",
            }
        ],
    )
    wp.get_participants.side_effect = [[_make_wp_participant()], []]
    chm.get_person.return_value = _make_chm_person()
    chm.update_person.return_value = False

    summary = checker.run("consent.xlsx")

    assert summary["api_error"] == 1
    assert summary["checked"] == 0

    audit = _read_audit(captured)
    assert audit.loc[0, "Action Taken"] == "api_error"
