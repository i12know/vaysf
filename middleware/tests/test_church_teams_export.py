import os
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from church_teams_export import ChurchTeamsExporter, CHM_FIELDS, MEMBERSHIP_QUESTION


@pytest.fixture()
def mock_connectors(mocker):
    chm_connector = MagicMock()
    chm_connector.get_groups.return_value = []
    chm_connector.get_group_people.return_value = []
    chm_connector.last_get_person_status = "ok"

    wp_connector = MagicMock()

    mocker.patch("church_teams_export.ChMeetingsConnector", return_value=chm_connector)
    mocker.patch("church_teams_export.WordPressConnector", return_value=wp_connector)

    return chm_connector, wp_connector


def test_fetch_chm_church_team_data_skips_orphaned_memberships(mock_connectors):
    chm_connector, _ = mock_connectors

    chm_connector.get_groups.return_value = [{"id": "870578", "name": "Team RPC"}]
    chm_connector.get_group_people.return_value = [
        {"person_id": "999999"},
        {"person_id": "101"},
    ]

    valid_person = {
        "id": "101",
        "first_name": "Alice",
        "last_name": "Nguyen",
        "gender": "Female",
        "birth_date": "2000-01-02",
        "mobile": "555-0101",
        "email": "alice@test.com",
        "updated_on": "2026-05-07T22:17:30+00:00",
        "additional_fields": [
            {"field_name": MEMBERSHIP_QUESTION, "value": "Yes"},
            {"field_name": CHM_FIELDS["ROLES"], "value": "Athlete"},
            {"field_name": CHM_FIELDS["COMPLETION_CHECKLIST"], "value": ""},
        ],
    }

    def fake_get_person(person_id):
        if person_id == "999999":
            chm_connector.last_get_person_status = "not_found"
            return None
        chm_connector.last_get_person_status = "ok"
        return valid_person

    chm_connector.get_person.side_effect = fake_get_person

    exporter = ChurchTeamsExporter()
    data = exporter._fetch_chm_church_team_data()

    assert "RPC" in data
    assert len(data["RPC"]) == 1
    assert data["RPC"][0]["ChMeetings ID"] == "101"
    assert exporter.last_orphaned_memberships_by_church == {"RPC": 1}


def test_handle_force_resend_filters_to_one_chm_id(mock_connectors, mocker):
    _, wp_connector = mock_connectors

    fake_sync_manager = MagicMock()
    fake_sync_manager.wordpress_connector.get_churches.return_value = [
        {"church_code": "RPC", "pastor_email": "pastor@rpc.org", "church_rep_email": "rep@rpc.org"}
    ]
    fake_sync_manager.__enter__.return_value = fake_sync_manager
    fake_sync_manager.__exit__.return_value = None

    mocker.patch("sync.manager.SyncManager", return_value=fake_sync_manager)

    exporter = ChurchTeamsExporter()
    contacts = [
        {
            "ChMeetings ID": "3318927",
            "First Name": "Sam",
            "Last Name": "Le",
            "Church Team": "RPC",
            "Email": "sam@example.com",
            "Approval_Status (WP)": "pending_approval",
        },
        {
            "ChMeetings ID": "4363698",
            "First Name": "Thomas",
            "Last Name": "Phan",
            "Church Team": "RPC",
            "Email": "thomas@example.com",
            "Approval_Status (WP)": "pending_approval",
        },
    ]

    resend_count = exporter._handle_force_resend(
        contacts,
        force_pending=True,
        force_validated1=False,
        force_validated2=False,
        dry_run=True,
        target_resend_chm_id="3318927",
    )

    assert resend_count == 1


def test_generate_reports_surfaces_open_validation_issues(mock_connectors, mocker, tmp_path):
    chm_connector, wp_connector = mock_connectors
    chm_connector.authenticate.return_value = True

    exporter = ChurchTeamsExporter()
    exporter.latest_chm_update_by_church = {"RPC": "2026-05-08 10:00:00"}
    mocker.patch.object(
        exporter,
        "_fetch_chm_church_team_data",
        return_value={
            "RPC": [
                {
                    "Church Team": "RPC",
                    "ChMeetings ID": "101",
                    "First Name": "Alice",
                    "Last Name": "Nguyen",
                    "Gender": "Female",
                    "Birthdate": "2000-01-02",
                    "Mobile Phone": "555-0101",
                    "Email": "alice@test.com",
                    "Is_Member_ChM": True,
                    "ChM_Roles": "Athlete",
                    "ChM_Completion_Checklist": "",
                    "Update_on_ChM": "2026-05-08 10:00:00",
                }
            ]
        },
    )

    wp_connector.get_church_by_code.return_value = {"church_id": 1, "church_code": "RPC"}
    wp_connector.get_participants.return_value = [
        {
            "participant_id": 42,
            "approval_status": "pending",
            "photo_url": "https://example.com/photo.jpg",
        }
    ]
    wp_connector.get_validation_issues.return_value = [
        {
            "issue_id": 1,
            "participant_id": 42,
            "issue_type": "missing_photo",
            "issue_description": "No photo uploaded",
            "rule_code": "PHOTO_REQUIRED",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "status": "open",
            "sport_type": None,
            "sport_format": None,
        },
        {
            "issue_id": 2,
            "participant_id": None,
            "issue_type": "team_non_member_limit",
            "issue_description": "Basketball - Men Team has 3 non-members, exceeding limit of 2",
            "rule_code": "MAX_NON_MEMBERS_TEAM",
            "rule_level": "TEAM",
            "severity": "ERROR",
            "status": "open",
            "sport_type": "Basketball - Men Team",
            "sport_format": None,
        },
        {
            "issue_id": 3,
            "participant_id": None,
            "issue_type": "doubles_non_member_limit",
            "issue_description": "Badminton Men Double pair Alice / Guest has 2 non-members, exceeding limit of 1",
            "rule_code": "MAX_NON_MEMBERS_DOUBLES",
            "rule_level": "TEAM",
            "severity": "ERROR",
            "status": "open",
            "sport_type": "Badminton",
            "sport_format": "Men Double",
        },
        {
            "issue_id": 4,
            "participant_id": 42,
            "issue_type": "missing_consent",
            "issue_description": "Missing consent form",
            "rule_code": "CONSENT_REQUIRED",
            "rule_level": "INDIVIDUAL",
            "severity": "WARNING",
            "status": "open",
            "sport_type": None,
            "sport_format": None,
        },
    ]
    wp_connector.get_rosters.return_value = [
        {
            "sport_type": "Basketball",
            "sport_gender": "Men",
            "sport_format": "Team",
            "team_order": None,
            "partner_name": None,
        },
        {
            "sport_type": "Badminton",
            "sport_gender": "Men",
            "sport_format": "Doubles",
            "team_order": None,
            "partner_name": "Guest",
        },
    ]

    write_report = mocker.patch.object(exporter, "_write_excel_report")

    result = exporter.generate_reports("RPC", tmp_path)

    assert result is True
    write_report.assert_called_once()
    _, summary_rows, contacts_rows, roster_rows, validation_rows = write_report.call_args.args

    assert summary_rows[0]["Total Participants w/ Open ERRORs (WP)"] == 1
    assert summary_rows[0]["Total Open Individual ERRORs (WP)"] == 1
    assert summary_rows[0]["Total Open TEAM ERRORs (WP)"] == 2
    assert summary_rows[0]["Total Open WARNINGs (WP)"] == 1
    assert summary_rows[0]["Total Sports w/ Open TEAM Issues (WP)"] == 2

    assert contacts_rows[0]["Total_Open_ERRORs (WP)"] == 1
    assert contacts_rows[0]["First_Open_ERROR_Desc (WP)"] == "No photo uploaded"

    basketball_row = next(row for row in roster_rows if row["sport_type"] == "Basketball")
    badminton_row = next(row for row in roster_rows if row["sport_type"] == "Badminton")
    assert basketball_row["Open_TEAM_Issue_Count (WP)"] == 1
    assert "Basketball - Men Team has 3 non-members" in basketball_row["Open_TEAM_Issue_Desc (WP)"]
    assert badminton_row["Open_TEAM_Issue_Count (WP)"] == 1
    assert "Badminton Men Double pair Alice / Guest" in badminton_row["Open_TEAM_Issue_Desc (WP)"]

    assert len(validation_rows) == 4
    participant_issue = next(row for row in validation_rows if row["Issue Type"] == "missing_photo")
    assert participant_issue["Participant Name"] == "Alice Nguyen"
    team_issue = next(row for row in validation_rows if row["Issue Type"] == "team_non_member_limit")
    assert team_issue["Rule Level"] == "TEAM"
    assert team_issue["Participant Name"] == ""


def test_generate_reports_filters_stale_individual_validation_issues(mock_connectors, mocker, tmp_path):
    chm_connector, wp_connector = mock_connectors
    chm_connector.authenticate.return_value = True

    exporter = ChurchTeamsExporter()
    exporter.latest_chm_update_by_church = {"RPC": "2026-05-08 10:00:00"}
    mocker.patch.object(
        exporter,
        "_fetch_chm_church_team_data",
        return_value={
            "RPC": [
                {
                    "Church Team": "RPC",
                    "ChMeetings ID": "101",
                    "First Name": "Alice",
                    "Last Name": "Nguyen",
                    "Gender": "Female",
                    "Birthdate": "2000-01-02",
                    "Mobile Phone": "555-0101",
                    "Email": "alice@test.com",
                    "Is_Member_ChM": True,
                    "ChM_Roles": "Athlete",
                    "ChM_Completion_Checklist": "",
                    "Update_on_ChM": "2026-05-08 10:00:00",
                }
            ]
        },
    )

    wp_connector.get_church_by_code.return_value = {"church_id": 1, "church_code": "RPC"}
    wp_connector.get_participants.return_value = [
        {
            "participant_id": 42,
            "approval_status": "pending",
            "photo_url": "https://example.com/photo.jpg",
        }
    ]
    wp_connector.get_validation_issues.return_value = [
        {
            "issue_id": 1,
            "participant_id": 42,
            "issue_type": "missing_photo",
            "issue_description": "No photo uploaded",
            "rule_code": "PHOTO_REQUIRED",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "status": "open",
            "sport_type": None,
            "sport_format": None,
        },
        {
            "issue_id": 2,
            "participant_id": 99,
            "issue_type": "missing_consent",
            "issue_description": "Consent form status unknown or not provided",
            "rule_code": "CONSENT_REQUIRED",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "status": "open",
            "sport_type": None,
            "sport_format": None,
        },
    ]
    wp_connector.get_rosters.return_value = []

    write_report = mocker.patch.object(exporter, "_write_excel_report")

    result = exporter.generate_reports("RPC", tmp_path)

    assert result is True
    _, summary_rows, contacts_rows, _, validation_rows = write_report.call_args.args

    assert summary_rows[0]["Total Participants w/ Open ERRORs (WP)"] == 1
    assert summary_rows[0]["Total Open Individual ERRORs (WP)"] == 1
    assert contacts_rows[0]["Total_Open_ERRORs (WP)"] == 1
    assert len(validation_rows) == 1
    assert validation_rows[0]["Participant ID (WP)"] == 42
    assert validation_rows[0]["Issue Type"] == "missing_photo"


def test_write_excel_report_adds_validation_issues_tab(mock_connectors, tmp_path):
    exporter = ChurchTeamsExporter()
    filepath = tmp_path / "church-report.xlsx"

    summary_rows = [{
        "Church Code": "RPC",
        "Total Members (ChM Team Group)": 1,
        "Total Participants (in WP)": 1,
        "Total Approved (WP)": 0,
        "Total Pending Approval (WP)": 1,
        "Total Denied (WP)": 0,
        "Total Participants w/ Open ERRORs (WP)": 1,
        "Total Open Individual ERRORs (WP)": 1,
        "Total Open TEAM ERRORs (WP)": 1,
        "Total Open WARNINGs (WP)": 0,
        "Total Sports w/ Open TEAM Issues (WP)": 1,
        "Latest ChM Record Update for Team": "2026-05-08 10:00:00",
    }]
    contacts_rows = [{
        "Church Team": "RPC",
        "ChMeetings ID": "101",
        "First Name": "Alice",
        "Last Name": "Nguyen",
        "Is_Participant": "Yes",
        "Is_Member_ChM": "Yes",
        "Participant ID (WP)": 42,
        "Approval_Status (WP)": "pending",
        "Total_Open_ERRORs (WP)": 1,
        "Gender": "Female",
        "Birthdate": "2000-01-02",
        "Age (at Event)": 26,
        "Mobile Phone": "555-0101",
        "Email": "alice@test.com",
        "First_Open_ERROR_Desc (WP)": "No photo uploaded",
        "Box 1": "",
        "Box 2": "",
        "Box 3": "",
        "Box 4": "",
        "Box 5": "",
        "Box 6": "",
        "Photo URL (WP)": "N/A",
        "Update_on_ChM": "2026-05-08 10:00:00",
    }]
    roster_rows = [{
        "Church Team": "RPC",
        "ChMeetings ID": "101",
        "Participant ID (WP)": 42,
        "Approval_Status (WP)": "pending",
        "Is_Member_ChM": True,
        "Photo": "",
        "First Name": "Alice",
        "Last Name": "Nguyen",
        "Gender": "Female",
        "Age (at Event)": 26,
        "Mobile Phone": "555-0101",
        "Email": "alice@test.com",
        "sport_type": "Badminton",
        "sport_gender": "Men",
        "sport_format": "Doubles",
        "team_order": None,
        "partner_name": "Guest",
        "Open_TEAM_Issue_Count (WP)": 1,
        "Open_TEAM_Issue_Desc (WP)": "Badminton Men Double pair Alice / Guest has 2 non-members, exceeding limit of 1",
    }]
    validation_rows = [{
        "Church Team": "RPC",
        "Rule Level": "TEAM",
        "Severity": "ERROR",
        "Status": "open",
        "Issue Type": "doubles_non_member_limit",
        "Rule Code": "MAX_NON_MEMBERS_DOUBLES",
        "Participant ID (WP)": "",
        "ChMeetings ID": "",
        "Participant Name": "",
        "Approval_Status (WP)": "",
        "sport_type": "Badminton",
        "sport_format": "Men Double",
        "Issue Description": "Badminton Men Double pair Alice / Guest has 2 non-members, exceeding limit of 1",
    }]

    exporter._write_excel_report(filepath, summary_rows, contacts_rows, roster_rows, validation_rows)

    workbook = pd.ExcelFile(filepath)
    assert "Validation-Issues" in workbook.sheet_names

    validation_df = pd.read_excel(filepath, sheet_name="Validation-Issues")
    roster_df = pd.read_excel(filepath, sheet_name="Roster")
    assert "Rule Level" in validation_df.columns
    assert validation_df.loc[0, "Issue Type"] == "doubles_non_member_limit"
    assert "Open_TEAM_Issue_Count (WP)" in roster_df.columns
    assert int(roster_df.loc[0, "Open_TEAM_Issue_Count (WP)"]) == 1


def test_validation_issue_rows_add_reverse_partner_suggestion(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {
            "Church Team": "RPC",
            "Participant ID (WP)": 72,
            "First Name": "Dean",
            "Last Name": "Nguyen",
            "sport_type": "Pickleball",
            "sport_gender": "Mixed",
            "sport_format": "Doubles",
            "partner_name": "Janice",
        },
        {
            "Church Team": "RPC",
            "Participant ID (WP)": 75,
            "First Name": "Janice",
            "Last Name": "Vu",
            "sport_type": "Pickleball",
            "sport_gender": "Mixed",
            "sport_format": "Doubles",
            "partner_name": "",
        },
    ]
    reverse_lookup = exporter._build_reverse_partner_suggestion_lookup(roster_rows)

    issue_rows = exporter._build_validation_issue_rows(
        "RPC",
        [{
            "participant_id": 75,
            "issue_type": "missing_doubles_partner",
            "issue_description": "Partner name required for Pickleball (Mixed Double)",
            "rule_code": "PARTNER_REQUIRED_DOUBLES",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "status": "open",
            "sport_type": "Pickleball",
            "sport_format": "Mixed Double",
        }],
        {
            "75": {
                "ChMeetings ID": "43636",
                "First Name": "Janice",
                "Last Name": "Vu",
                "Approval_Status (WP)": "pending",
            }
        },
        reverse_lookup,
    )

    assert len(issue_rows) == 1
    assert "perhaps Dean Nguyen listed you as partner." in issue_rows[0]["Issue Description"]


def test_reverse_partner_suggestion_lookup_skips_ambiguous_partial_match(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {
            "Church Team": "RPC",
            "Participant ID (WP)": 72,
            "First Name": "Dean",
            "Last Name": "Nguyen",
            "sport_type": "Pickleball",
            "sport_gender": "Mixed",
            "sport_format": "Doubles",
            "partner_name": "Janice",
        },
        {
            "Church Team": "RPC",
            "Participant ID (WP)": 75,
            "First Name": "Janice",
            "Last Name": "Vu",
            "sport_type": "Pickleball",
            "sport_gender": "Mixed",
            "sport_format": "Doubles",
            "partner_name": "",
        },
        {
            "Church Team": "RPC",
            "Participant ID (WP)": 76,
            "First Name": "Janice",
            "Last Name": "Nguyen",
            "sport_type": "Pickleball",
            "sport_gender": "Mixed",
            "sport_format": "Doubles",
            "partner_name": "",
        },
    ]

    reverse_lookup = exporter._build_reverse_partner_suggestion_lookup(roster_rows)

    janice_vu_key = exporter._reverse_partner_suggestion_key(75, "Pickleball", "Mixed", "Doubles")
    janice_nguyen_key = exporter._reverse_partner_suggestion_key(76, "Pickleball", "Mixed", "Doubles")
    assert janice_vu_key not in reverse_lookup
    assert janice_nguyen_key not in reverse_lookup


def test_validation_issue_rows_do_not_cross_gendered_doubles_formats(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {
            "Church Team": "TLC",
            "Participant ID (WP)": 26,
            "First Name": "Hyewon",
            "Last Name": "Yun",
            "sport_type": "Badminton",
            "sport_gender": "Men",
            "sport_format": "Doubles",
            "partner_name": "Shawn Le",
        },
        {
            "Church Team": "TLC",
            "Participant ID (WP)": 31,
            "First Name": "Shawn",
            "Last Name": "Le",
            "sport_type": "Badminton",
            "sport_gender": "Mixed",
            "sport_format": "Doubles",
            "partner_name": "",
        },
    ]

    reverse_lookup = exporter._build_reverse_partner_suggestion_lookup(roster_rows)

    issue_rows = exporter._build_validation_issue_rows(
        "TLC",
        [{
            "participant_id": 31,
            "issue_type": "missing_doubles_partner",
            "issue_description": "Partner name required for Badminton (Mixed Double)",
            "rule_code": "PARTNER_REQUIRED_DOUBLES",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "status": "open",
            "sport_type": "Badminton",
            "sport_format": "Mixed Double",
        }],
        {
            "31": {
                "ChMeetings ID": "35628",
                "First Name": "Shawn",
                "Last Name": "Le",
                "Approval_Status (WP)": "pending",
            }
        },
        reverse_lookup,
    )

    assert len(issue_rows) == 1
    assert "perhaps Hyewon Yun listed you as partner." not in issue_rows[0]["Issue Description"]


def test_issue_based_reverse_partner_suggestion_handles_incomplete_roster_data(mock_connectors):
    exporter = ChurchTeamsExporter()
    issues = [
        {
            "participant_id": 149,
            "issue_type": "missing_doubles_partner",
            "issue_description": "Partner name required for Table Tennis 35+ (Men Double)",
            "rule_code": "PARTNER_REQUIRED_DOUBLES",
            "rule_level": "INDIVIDUAL",
            "severity": "ERROR",
            "status": "open",
            "sport_type": "Table Tennis 35+",
            "sport_format": "Men Double",
        },
        {
            "participant_id": 156,
            "issue_type": "doubles_partner_unmatched",
            "issue_description": (
                "Long Chung listed Andrew Nguyen as their partner for Table Tennis 35+ "
                "(Men Double), but Andrew Nguyen did not reciprocally list Long Chung."
            ),
            "rule_code": "PARTNER_RECIPROCAL_DOUBLES",
            "rule_level": "TEAM",
            "severity": "WARNING",
            "status": "open",
            "sport_type": "Table Tennis 35+",
            "sport_format": "Men Double",
        },
    ]
    participants_by_wp_id = {
        "149": {
            "ChMeetings ID": "43644",
            "First Name": "Andrew",
            "Last Name": "Nguyen",
            "Approval_Status (WP)": "pending",
        },
        "156": {
            "ChMeetings ID": "43644",
            "First Name": "Long",
            "Last Name": "Chung",
            "Approval_Status (WP)": "pending",
        },
    }

    reverse_lookup = exporter._build_issue_based_reverse_partner_suggestion_lookup(
        issues,
        participants_by_wp_id,
    )

    issue_rows = exporter._build_validation_issue_rows(
        "TLC",
        [issues[0]],
        participants_by_wp_id,
        reverse_lookup,
    )

    assert len(issue_rows) == 1
    assert "perhaps Long Chung listed you as partner." in issue_rows[0]["Issue Description"]
