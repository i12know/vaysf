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
