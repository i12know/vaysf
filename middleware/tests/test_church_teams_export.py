import os
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from church_teams_export import ChurchTeamsExporter, CHM_FIELDS, MEMBERSHIP_QUESTION
from config import SPORT_TYPE


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


def test_contacts_status_tab_includes_sports_registered_column(mock_connectors, tmp_path):
    exporter = ChurchTeamsExporter()
    filepath = tmp_path / "church-report.xlsx"

    contacts_rows = [
        {
            "Church Team": "RPC",
            "ChMeetings ID": "101",
            "First Name": "Alice",
            "Last Name": "Nguyen",
            "Is_Participant": "Yes",
            "Is_Member_ChM": "Yes",
            "Participant ID (WP)": 42,
            "Approval_Status (WP)": "pending",
            "Total_Open_ERRORs (WP)": 0,
            "Gender": "Female",
            "Birthdate": "2000-01-02",
            "Age (at Event)": 26,
            "Mobile Phone": "555-0101",
            "Email": "alice@test.com",
            "Registration Date (WP)": "2026-03-01",
            "Athlete Fee": 30,
            "First_Open_ERROR_Desc (WP)": "",
            "Box 1": "", "Box 2": "", "Box 3": "", "Box 4": "", "Box 5": "", "Box 6": "",
            "Photo URL (WP)": "N/A",
            "Update_on_ChM": "2026-05-08",
        },
        {
            "Church Team": "RPC",
            "ChMeetings ID": "102",
            "First Name": "Bob",
            "Last Name": "Tran",
            "Is_Participant": "Yes",
            "Is_Member_ChM": "Yes",
            "Participant ID (WP)": 99,
            "Approval_Status (WP)": "approved",
            "Total_Open_ERRORs (WP)": 0,
            "Gender": "Male",
            "Birthdate": "1998-05-10",
            "Age (at Event)": 28,
            "Mobile Phone": "555-0202",
            "Email": "bob@test.com",
            "Registration Date (WP)": "2026-03-02",
            "Athlete Fee": 30,
            "First_Open_ERROR_Desc (WP)": "",
            "Box 1": "", "Box 2": "", "Box 3": "", "Box 4": "", "Box 5": "", "Box 6": "",
            "Photo URL (WP)": "N/A",
            "Update_on_ChM": "2026-05-08",
        },
        # No matching roster entry
        {
            "Church Team": "RPC",
            "ChMeetings ID": "103",
            "First Name": "Carol",
            "Last Name": "Pham",
            "Is_Participant": "No",
            "Is_Member_ChM": "Yes",
            "Participant ID (WP)": None,
            "Approval_Status (WP)": "",
            "Total_Open_ERRORs (WP)": 0,
            "Gender": "Female",
            "Birthdate": "2003-09-15",
            "Age (at Event)": 22,
            "Mobile Phone": "555-0303",
            "Email": "carol@test.com",
            "Registration Date (WP)": "",
            "Athlete Fee": "",
            "First_Open_ERROR_Desc (WP)": "",
            "Box 1": "", "Box 2": "", "Box 3": "", "Box 4": "", "Box 5": "", "Box 6": "",
            "Photo URL (WP)": "N/A",
            "Update_on_ChM": "2026-05-08",
        },
    ]
    roster_rows = [
        # Alice plays two sports
        {
            "Church Team": "RPC", "ChMeetings ID": "101", "Participant ID (WP)": 42,
            "sport_type": "Badminton", "sport_gender": "Women", "sport_format": "Doubles",
        },
        {
            "Church Team": "RPC", "ChMeetings ID": "101", "Participant ID (WP)": 42,
            "sport_type": "Basketball", "sport_gender": "", "sport_format": "",
        },
        # Bob plays one sport; duplicate roster row should not duplicate the label
        {
            "Church Team": "RPC", "ChMeetings ID": "102", "Participant ID (WP)": 99,
            "sport_type": "Volleyball", "sport_gender": "Men", "sport_format": "",
        },
        {
            "Church Team": "RPC", "ChMeetings ID": "102", "Participant ID (WP)": 99,
            "sport_type": "Volleyball", "sport_gender": "Men", "sport_format": "",
        },
    ]
    summary_rows = [{
        "Church Code": "RPC",
        "Total Members (ChM Team Group)": 3,
        "Total Participants (in WP)": 2,
        "Total Approved (WP)": 1,
        "Total Pending Approval (WP)": 1,
        "Total Denied (WP)": 0,
        "Total Participants w/ Open ERRORs (WP)": 0,
        "Total Open Individual ERRORs (WP)": 0,
        "Total Open TEAM ERRORs (WP)": 0,
        "Total Open WARNINGs (WP)": 0,
        "Total Sports w/ Open TEAM Issues (WP)": 0,
        "Latest ChM Record Update for Team": "2026-05-08",
    }]

    exporter._write_excel_report(filepath, summary_rows, contacts_rows, roster_rows, [])

    contacts_df = pd.read_excel(filepath, sheet_name="Contacts-Status")
    assert "Sports Registered" in contacts_df.columns

    # Column must appear immediately before "Athlete Fee"
    cols = list(contacts_df.columns)
    assert cols.index("Sports Registered") == cols.index("Athlete Fee") - 1

    alice_row = contacts_df[contacts_df["First Name"] == "Alice"].iloc[0]
    sports = [s.strip() for s in alice_row["Sports Registered"].split(",")]
    assert sorted(sports) == sorted(["Badminton Women Doubles", "Basketball"])

    bob_row = contacts_df[contacts_df["First Name"] == "Bob"].iloc[0]
    assert bob_row["Sports Registered"] == "Volleyball Men"

    carol_row = contacts_df[contacts_df["First Name"] == "Carol"].iloc[0]
    assert carol_row["Sports Registered"] == "" or pd.isna(carol_row["Sports Registered"])


def test_venue_capacity_court_slot_math(mock_connectors):
    """Pool/playoff/total slot math (Issue #83)."""
    exporter = ChurchTeamsExporter()

    # 0 teams → all zeros
    s0 = exporter._compute_court_slots(0)
    assert s0["pool_slots"] == 0
    assert s0["playoff_teams"] == 0
    assert s0["playoff_slots"] == 0
    assert s0["total_slots"] == 0
    assert s0["court_hours"] == 0.0

    # 6 teams, 2 pool games each → ceil(6*2/2) = 6 pool, 4-team playoff = 3 playoff games
    s6 = exporter._compute_court_slots(6)
    assert s6["pool_slots"] == 6
    assert s6["playoff_teams"] == 4
    assert s6["playoff_slots"] == 3
    assert s6["third_place_slots"] == 0  # default off
    assert s6["total_slots"] == 9
    assert s6["court_hours"] == 9.0  # 60 min/game

    # 8 teams → ceil(8*2/2)=8 pool, 8-team playoff = 7 playoff games
    s8 = exporter._compute_court_slots(8)
    assert s8["pool_slots"] == 8
    assert s8["playoff_teams"] == 8
    assert s8["playoff_slots"] == 7
    assert s8["total_slots"] == 15

    # 3 teams → only pool play, no playoff
    s3 = exporter._compute_court_slots(3)
    assert s3["pool_slots"] == 3
    assert s3["playoff_teams"] == 0
    assert s3["playoff_slots"] == 0
    assert s3["total_slots"] == 3


def test_count_estimating_teams_uses_min_team_size(mock_connectors):
    """A church only counts when its roster meets the min team size (Issue #83)."""
    exporter = ChurchTeamsExporter()

    # RPC has 5 basketball players (meets min=5), TLC has 4 (potential only)
    roster_rows = [
        {"Church Team": "RPC", "sport_type": "Basketball", "sport_gender": "Men"} for _ in range(5)
    ] + [
        {"Church Team": "TLC", "sport_type": "Basketball", "sport_gender": "Men"} for _ in range(4)
    ]

    result = exporter._count_estimating_teams(roster_rows, "Basketball - Men Team", min_team_size=5)
    assert result["n_estimating"] == 1       # only RPC qualifies
    assert result["n_potential"] == 2        # RPC (estimating) + TLC (partial) = all with >= 1
    assert result["team_codes"] == "RPC"     # sorted, comma-separated


def test_count_estimating_teams_separates_volleyball_men_and_women(mock_connectors):
    """Volleyball Men and Women are distinct events; team_codes is sorted (Issue #83)."""
    exporter = ChurchTeamsExporter()

    roster_rows = (
        [{"Church Team": "RPC", "sport_type": "Volleyball", "sport_gender": "Men"} for _ in range(6)]
        + [{"Church Team": "RPC", "sport_type": "Volleyball", "sport_gender": "Women"} for _ in range(6)]
        + [{"Church Team": "TLC", "sport_type": "Volleyball", "sport_gender": "Women"} for _ in range(6)]
    )

    men = exporter._count_estimating_teams(roster_rows, "Volleyball - Men Team", 6)
    assert men["n_estimating"] == 1
    assert men["team_codes"] == "RPC"

    women = exporter._count_estimating_teams(roster_rows, "Volleyball - Women Team", 6)
    assert women["n_estimating"] == 2
    assert women["team_codes"] == "RPC, TLC"  # alphabetically sorted


def test_count_estimating_teams_soccer_full_label(mock_connectors):
    """Soccer sport_type is stored as the full Other-Events label, not just 'Soccer'."""
    exporter = ChurchTeamsExporter()

    # Other-events registrations store the full SPORT_TYPE constant value verbatim
    roster_rows = [
        {"Church Team": "RPC", "sport_type": SPORT_TYPE["SOCCER"], "sport_gender": "Mixed"}
        for _ in range(5)
    ] + [
        {"Church Team": "TLC", "sport_type": SPORT_TYPE["SOCCER"], "sport_gender": "Mixed"}
        for _ in range(3)
    ]

    result = exporter._count_estimating_teams(
        roster_rows, SPORT_TYPE["SOCCER"], min_team_size=4
    )
    assert result["n_estimating"] == 1      # only RPC has >= 4
    assert result["n_potential"] == 2       # RPC + TLC both have >= 1
    assert result["team_codes"] == "RPC"


def test_count_racquet_entries(mock_connectors):
    """Racquet entries: complete pairs counted as 1, singles as 1; potential = all regs."""
    exporter = ChurchTeamsExporter()

    roster_rows = [
        # 5 Badminton doubles registrations → 2 complete pairs + 1 waiting
        {"sport_type": "Badminton", "sport_format": "Mixed Doubles"} for _ in range(5)
    ] + [
        # 2 Badminton singles
        {"sport_type": "Badminton", "sport_format": "Men Singles"},
        {"sport_type": "Badminton", "sport_format": "Women Singles"},
    ] + [
        # Pickleball should not bleed into Badminton count
        {"sport_type": "Pickleball", "sport_format": "Mixed Doubles"},
    ]

    result = exporter._count_racquet_entries(roster_rows, "Badminton")
    assert result["n_estimating"] == 2 + 2   # floor(5/2)=2 pairs + 2 singles
    assert result["n_potential"] == 5 + 2    # 5 doubles + 2 singles = 7 registrations
    assert result["team_codes"] == ""


def test_venue_capacity_tab_only_in_consolidated_export(mock_connectors, tmp_path):
    """Venue-Estimator tab appears only when include_venue_capacity=True (Issue #83)."""
    exporter = ChurchTeamsExporter()

    summary_rows = [{
        "Church Code": "RPC",
        "Total Members (ChM Team Group)": 6, "Total Participants (in WP)": 6,
        "Total Approved (WP)": 0, "Total Pending Approval (WP)": 6, "Total Denied (WP)": 0,
        "Total Participants w/ Open ERRORs (WP)": 0,
        "Total Open Individual ERRORs (WP)": 0, "Total Open TEAM ERRORs (WP)": 0,
        "Total Open WARNINGs (WP)": 0, "Total Sports w/ Open TEAM Issues (WP)": 0,
        "Latest ChM Record Update for Team": "2026-05-13",
    }]
    contacts_rows = [{
        "Church Team": "RPC", "ChMeetings ID": str(100 + i), "First Name": f"P{i}",
        "Last Name": "X", "Is_Participant": "Yes", "Is_Member_ChM": "Yes",
        "Participant ID (WP)": i, "Approval_Status (WP)": "pending",
        "Total_Open_ERRORs (WP)": 0, "Gender": "Male", "Birthdate": "2000-01-01",
        "Age (at Event)": 26, "Mobile Phone": "", "Email": "",
        "Registration Date (WP)": "2026-03-01", "Athlete Fee": 30,
        "First_Open_ERROR_Desc (WP)": "",
        "Box 1": "", "Box 2": "", "Box 3": "", "Box 4": "", "Box 5": "", "Box 6": "",
        "Photo URL (WP)": "N/A", "Update_on_ChM": "",
    } for i in range(6)]
    roster_rows = [{
        "Church Team": "RPC", "ChMeetings ID": str(100 + i), "Participant ID (WP)": i,
        "sport_type": "Basketball", "sport_gender": "Men", "sport_format": "Team",
    } for i in range(6)]

    # Single-church export: no Venue-Estimator tab
    single_path = tmp_path / "single.xlsx"
    exporter._write_excel_report(single_path, summary_rows, contacts_rows, roster_rows, [])
    assert "Venue-Estimator" not in pd.ExcelFile(single_path).sheet_names

    # Consolidated ALL export: tab present, snapshot note appended after data
    all_path = tmp_path / "all.xlsx"
    exporter._write_excel_report(all_path, summary_rows, contacts_rows, roster_rows, [],
                                 include_venue_capacity=True)
    sheets = pd.ExcelFile(all_path).sheet_names
    assert "Venue-Estimator" in sheets

    venue_df = pd.read_excel(all_path, sheet_name="Venue-Estimator", header=0)
    assert list(venue_df.columns)[0] == "Event"
    assert "Potential Teams/Entries" in venue_df.columns
    assert "Estimating Teams/Entries" in venue_df.columns
    assert "Teams" in venue_df.columns
    assert "Estimated Court Hours" in venue_df.columns
    # 5 team sports + 6 racquet sports
    assert len(venue_df[venue_df["Minutes Per Game"].notna()]) == 11  # 5 team + 6 racquet sports

    # Column order: Potential before Estimating before Teams
    cols = list(venue_df.columns)
    assert cols.index("Potential Teams/Entries") < cols.index("Estimating Teams/Entries") < cols.index("Teams")

    bball = venue_df[venue_df["Event"] == "Basketball - Men Team"].iloc[0]
    assert int(bball["Estimating Teams/Entries"]) == 1   # RPC's 6 basketball players qualify
    assert int(bball["Potential Teams/Entries"]) == 1    # RPC (estimating) counts in potential too
    assert str(bball["Teams"]) == "RPC"
    assert int(bball["Pool Slots"]) == 1         # ceil(1*2/2) = 1
    assert int(bball["Playoff Teams"]) == 0      # 1 team → no playoff
    assert int(bball["Total Court Slots"]) == 1

    vb_men = venue_df[venue_df["Event"] == "Volleyball - Men Team"].iloc[0]
    assert int(vb_men["Estimating Teams/Entries"]) == 0  # no volleyball rosters
    assert str(vb_men["Teams"]) in ("", "nan")

    # Snapshot disclaimer appears after the data (header + 11 rows + blank = row 13)
    raw = pd.read_excel(all_path, sheet_name="Venue-Estimator", header=None)
    note_row_idx = 13  # 0-based: row 14 in Excel (1 header + 11 data + 1 blank + note)
    assert "Roster snapshot as of" in str(raw.iloc[note_row_idx, 0])


# ── Pod-Divisions / Pod-Entries-Review tests (Issue #88) ────────────────────

def test_pod_format_class(mock_connectors):
    exporter = ChurchTeamsExporter()
    assert exporter._pod_format_class("Men Single") == "singles"
    assert exporter._pod_format_class("Singles") == "singles"
    assert exporter._pod_format_class("Women Singles") == "singles"
    assert exporter._pod_format_class("Men Double") == "doubles"
    assert exporter._pod_format_class("Doubles") == "doubles"
    assert exporter._pod_format_class("Mixed Double") == "doubles"
    assert exporter._pod_format_class("Team") == "anomaly"
    assert exporter._pod_format_class("") == "anomaly"
    assert exporter._pod_format_class(None) == "anomaly"


def test_make_division_id(mock_connectors):
    exporter = ChurchTeamsExporter()
    assert exporter._make_division_id("Badminton", "Men", "singles") == "BAD-Men-Singles"
    assert exporter._make_division_id("Table Tennis", "Women", "doubles") == "TT-Women-Doubles"
    assert exporter._make_division_id("Pickleball 35+", "Mixed", "doubles") == "PCK35-Mixed-Doubles"
    assert exporter._make_division_id("Tennis", "Men", "anomaly") == "TEN-Men-Anomaly"
    assert exporter._make_division_id("Table Tennis 35+", "Men", "singles") == "TT35-Men-Singles"


def test_build_pod_error_lookup(mock_connectors):
    exporter = ChurchTeamsExporter()
    validation_rows = [
        {
            "Participant ID (WP)": "42",
            "sport_type": "Badminton",
            "Severity": "ERROR",
            "Status": "open",
        },
        {
            "Participant ID (WP)": "42",
            "sport_type": "Pickleball",
            "Severity": "WARNING",  # warnings excluded
            "Status": "open",
        },
        {
            "Participant ID (WP)": "99",
            "sport_type": "Table Tennis",
            "Severity": "ERROR",
            "Status": "resolved",  # resolved excluded
        },
        {
            "Participant ID (WP)": "55",
            "sport_type": "Tennis",
            "Severity": "ERROR",
            "Status": "open",
        },
    ]
    lookup = exporter._build_pod_error_lookup(validation_rows)
    assert lookup == {"42": {"Badminton"}, "55": {"Tennis"}}


def test_build_pod_divisions_rows_singles(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Single",
         "Participant ID (WP)": "1", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Single",
         "Participant ID (WP)": "2", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Single",
         "Participant ID (WP)": "3", "Church Team": "TLC"},
    ]
    # Participant 2 has an error
    validation_rows = [
        {"Participant ID (WP)": "2", "sport_type": "Badminton", "Severity": "ERROR", "Status": "open"},
    ]
    rows = exporter._build_pod_divisions_rows(roster_rows, validation_rows)

    assert len(rows) == 1
    div = rows[0]
    assert div["division_id"] == "BAD-Men-Singles"
    assert div["sport_type"] == "Badminton"
    assert div["planning_entries"] == 3
    assert div["confirmed_entries"] == 2  # participant 2 has error
    assert div["provisional_entries"] == 1
    assert div["anomaly_count"] == 0
    assert div["division_status"] == "Partial"


def test_build_pod_divisions_rows_doubles(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "10", "Church Team": "RPC"},
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "11", "Church Team": "RPC"},
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "12", "Church Team": "TLC"},
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "13", "Church Team": "TLC"},
    ]
    rows = exporter._build_pod_divisions_rows(roster_rows, [])

    assert len(rows) == 1
    div = rows[0]
    assert div["division_id"] == "TT-Men-Doubles"
    assert div["planning_entries"] == 2   # floor(4/2)
    assert div["confirmed_entries"] == 2  # no errors
    assert div["provisional_entries"] == 0
    assert div["division_status"] == "Ready"


def test_build_pod_divisions_rows_anomaly(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {"sport_type": "Pickleball", "sport_gender": "Men", "sport_format": "Team",
         "Participant ID (WP)": "20", "Church Team": "RPC"},
    ]
    rows = exporter._build_pod_divisions_rows(roster_rows, [])

    assert len(rows) == 1
    div = rows[0]
    assert div["division_id"] == "PCK-Men-Anomaly"
    assert div["planning_entries"] == 0
    assert div["confirmed_entries"] == 0
    assert div["anomaly_count"] == 1
    assert div["division_status"] == "AnomalyOnly"


def test_build_pod_entries_review_singles(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {"sport_type": "Tennis", "sport_gender": "Women", "sport_format": "Women Single",
         "Participant ID (WP)": "30", "First Name": "Lan", "Last Name": "Tran", "Church Team": "RPC"},
        {"sport_type": "Tennis", "sport_gender": "Women", "sport_format": "Women Single",
         "Participant ID (WP)": "31", "First Name": "Hoa", "Last Name": "Le", "Church Team": "RPC"},
    ]
    validation_rows = [
        {"Participant ID (WP)": "31", "sport_type": "Tennis", "Severity": "ERROR", "Status": "open"},
    ]
    rows = exporter._build_pod_entries_review_rows(roster_rows, validation_rows)

    assert len(rows) == 2
    singles = [r for r in rows if r["entry_type"] == "Singles"]
    assert len(singles) == 2

    lan = next(r for r in singles if r["participant_1_name"] == "Lan Tran")
    assert lan["review_status"] == "OK"
    assert lan["partner_status"] == "N/A"
    assert lan["division_id"] == "TEN-Women-Singles"

    hoa = next(r for r in singles if r["participant_1_name"] == "Hoa Le")
    assert hoa["review_status"] == "NeedsReview"


def test_build_pod_entries_review_doubles_reciprocal(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "40", "First Name": "Anh", "Last Name": "Nguyen",
         "partner_name": "Binh Tran", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "41", "First Name": "Binh", "Last Name": "Tran",
         "partner_name": "Anh Nguyen", "Church Team": "TLC"},
    ]
    rows = exporter._build_pod_entries_review_rows(roster_rows, [])

    assert len(rows) == 1
    pair = rows[0]
    assert pair["entry_type"] == "DoublesPair"
    assert pair["partner_status"] == "Confirmed"
    assert pair["review_status"] == "OK"
    assert "Anh Nguyen" in pair["participant_1_name"] or "Binh Tran" in pair["participant_1_name"]
    assert "Anh Nguyen" in pair["participant_2_name"] or "Binh Tran" in pair["participant_2_name"]
    # cross-church pair shows both church codes
    assert "RPC" in pair["church_team"] and "TLC" in pair["church_team"]


def test_build_pod_entries_review_doubles_missing_partner(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {"sport_type": "Pickleball", "sport_gender": "Women", "sport_format": "Women Double",
         "Participant ID (WP)": "50", "First Name": "Cam", "Last Name": "Ho",
         "partner_name": "", "Church Team": "RPC"},
    ]
    rows = exporter._build_pod_entries_review_rows(roster_rows, [])

    assert len(rows) == 1
    entry = rows[0]
    assert entry["entry_type"] == "UnresolvedDoubles"
    assert entry["partner_status"] == "MissingPartner"
    assert entry["review_status"] == "NeedsReview"


def test_build_pod_entries_review_doubles_non_reciprocal(mock_connectors):
    exporter = ChurchTeamsExporter()
    # A claims B, B claims someone else (non-reciprocal)
    roster_rows = [
        {"sport_type": "Badminton", "sport_gender": "Mixed", "sport_format": "Mixed Double",
         "Participant ID (WP)": "60", "First Name": "Dan", "Last Name": "Vo",
         "partner_name": "Linh Pham", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Mixed", "sport_format": "Mixed Double",
         "Participant ID (WP)": "61", "First Name": "Linh", "Last Name": "Pham",
         "partner_name": "Khoa Bui", "Church Team": "RPC"},  # claims Khoa, not Dan
    ]
    rows = exporter._build_pod_entries_review_rows(roster_rows, [])

    unresolved = [r for r in rows if r["entry_type"] == "UnresolvedDoubles"]
    assert len(unresolved) >= 1
    reasons = {r["partner_status"] for r in unresolved}
    assert "NonReciprocal" in reasons


def test_build_pod_entries_review_anomaly(mock_connectors):
    exporter = ChurchTeamsExporter()
    roster_rows = [
        {"sport_type": "Table Tennis 35+", "sport_gender": "Men", "sport_format": "Team",
         "Participant ID (WP)": "70", "First Name": "Tri", "Last Name": "Nguyen",
         "Church Team": "RPC"},
    ]
    rows = exporter._build_pod_entries_review_rows(roster_rows, [])

    assert len(rows) == 1
    assert rows[0]["entry_type"] == "Anomaly"
    assert rows[0]["review_status"] == "NeedsReview"
    assert "Team" in rows[0]["notes"]


def test_pod_tabs_present_in_consolidated_export(mock_connectors, tmp_path):
    """Pod-Divisions and Pod-Entries-Review tabs appear only in the ALL export."""
    exporter = ChurchTeamsExporter()

    summary_rows = [{
        "Church Code": "RPC",
        "Total Members (ChM Team Group)": 2, "Total Participants (in WP)": 2,
        "Total Approved (WP)": 0, "Total Pending Approval (WP)": 2, "Total Denied (WP)": 0,
        "Total Participants w/ Open ERRORs (WP)": 0,
        "Total Open Individual ERRORs (WP)": 0, "Total Open TEAM ERRORs (WP)": 0,
        "Total Open WARNINGs (WP)": 0, "Total Sports w/ Open TEAM Issues (WP)": 0,
        "Latest ChM Record Update for Team": "2026-05-14",
    }]
    contacts_rows = [{
        "Church Team": "RPC", "ChMeetings ID": "101", "First Name": "Alice", "Last Name": "Nguyen",
        "Is_Participant": "Yes", "Is_Member_ChM": "Yes", "Participant ID (WP)": 1,
        "Approval_Status (WP)": "pending", "Total_Open_ERRORs (WP)": 0,
        "Gender": "Female", "Birthdate": "2000-01-02", "Age (at Event)": 26,
        "Mobile Phone": "", "Email": "", "Registration Date (WP)": "2026-03-01",
        "Athlete Fee": 30, "First_Open_ERROR_Desc (WP)": "",
        "Box 1": "", "Box 2": "", "Box 3": "", "Box 4": "", "Box 5": "", "Box 6": "",
        "Photo URL (WP)": "N/A", "Update_on_ChM": "",
    }]
    # Two badminton singles participants — one confirmed, one with error
    roster_rows = [
        {"Church Team": "RPC", "ChMeetings ID": "101", "Participant ID (WP)": 1,
         "First Name": "Alice", "Last Name": "Nguyen", "Gender": "Female", "Age (at Event)": 26,
         "Mobile Phone": "", "Email": "", "Is_Member_ChM": True, "Photo": "",
         "Approval_Status (WP)": "pending",
         "sport_type": "Badminton", "sport_gender": "Women", "sport_format": "Women Single",
         "team_order": None, "partner_name": None,
         "Open_TEAM_Issue_Count (WP)": 0, "Open_TEAM_Issue_Desc (WP)": ""},
        {"Church Team": "RPC", "ChMeetings ID": "102", "Participant ID (WP)": 2,
         "First Name": "Binh", "Last Name": "Le", "Gender": "Female", "Age (at Event)": 28,
         "Mobile Phone": "", "Email": "", "Is_Member_ChM": True, "Photo": "",
         "Approval_Status (WP)": "pending",
         "sport_type": "Badminton", "sport_gender": "Women", "sport_format": "Women Single",
         "team_order": None, "partner_name": None,
         "Open_TEAM_Issue_Count (WP)": 0, "Open_TEAM_Issue_Desc (WP)": ""},
    ]
    validation_rows = [
        {"Church Team": "RPC", "Rule Level": "INDIVIDUAL", "Severity": "ERROR",
         "Status": "open", "Issue Type": "missing_photo", "Rule Code": "PHOTO_REQUIRED",
         "Participant ID (WP)": 2, "ChMeetings ID": "102", "Participant Name": "Binh Le",
         "Approval_Status (WP)": "pending", "sport_type": "Badminton", "sport_format": None,
         "Issue Description": "No photo uploaded"},
    ]

    # Single-church: no pod tabs
    single_path = tmp_path / "single.xlsx"
    exporter._write_excel_report(single_path, summary_rows, contacts_rows, roster_rows, validation_rows)
    single_sheets = pd.ExcelFile(single_path).sheet_names
    assert "Pod-Divisions" not in single_sheets
    assert "Pod-Entries-Review" not in single_sheets

    # ALL export: pod tabs present
    all_path = tmp_path / "all.xlsx"
    exporter._write_excel_report(all_path, summary_rows, contacts_rows, roster_rows, validation_rows,
                                 include_venue_capacity=True)
    all_sheets = pd.ExcelFile(all_path).sheet_names
    assert "Pod-Divisions" in all_sheets
    assert "Pod-Entries-Review" in all_sheets

    pod_div_df = pd.read_excel(all_path, sheet_name="Pod-Divisions")
    assert list(pod_div_df.columns)[:3] == ["division_id", "sport_type", "sport_gender"]
    assert len(pod_div_df) == 1
    row = pod_div_df.iloc[0]
    assert row["division_id"] == "BAD-Women-Singles"
    assert int(row["planning_entries"]) == 2
    assert int(row["confirmed_entries"]) == 1   # participant 2 has ERROR
    assert int(row["provisional_entries"]) == 1
    assert int(row["anomaly_count"]) == 0

    pod_entry_df = pd.read_excel(all_path, sheet_name="Pod-Entries-Review")
    assert "entry_type" in pod_entry_df.columns
    assert len(pod_entry_df) == 2
    assert set(pod_entry_df["entry_type"]) == {"Singles"}
    ok_rows = pod_entry_df[pod_entry_df["review_status"] == "OK"]
    needs_review_rows = pod_entry_df[pod_entry_df["review_status"] == "NeedsReview"]
    assert len(ok_rows) == 1
    assert len(needs_review_rows) == 1
