import os
import sys
from unittest.mock import MagicMock

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
