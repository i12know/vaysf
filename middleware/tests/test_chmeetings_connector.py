import os
import json
import pytest
import sys
import time
import requests
from chmeetings.backend_connector import ChMeetingsConnector
from loguru import logger

# Force logging to console
# logger.remove()
# logger.add(sys.stderr, level="INFO")

# At the top, add the fixture
@pytest.fixture
def mock_chm_people_data():
    """Load mock ChMeetings data from JSON file."""
    file_path = os.path.join(os.path.dirname(__file__), "mock_chm_people_data.json")
    with open(file_path, "r") as f:
        return json.load(f)

@pytest.fixture
def chm_connector(monkeypatch, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    logger.info(f"LIVE_TEST from env: {os.getenv('LIVE_TEST')} -> live_test: {live_test}")
    if not live_test:
        mocker.patch("chmeetings.backend_connector.Config.CHM_API_URL", "https://test.chmeetings.com/")
        mocker.patch("chmeetings.backend_connector.Config.CHM_API_KEY", "test_api_key")
    with ChMeetingsConnector(use_api=True) as connector:
        logger.info(f"Test mode: {'Live' if live_test else 'Mocked'}, API URL: {connector.api_url}")
        yield connector

def test_chm_connector_init(chm_connector):
    assert chm_connector is not None, "ChMeetingsConnector failed to initialize"
    assert chm_connector.use_api, "API usage should be enabled"

def test_authenticate_api(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        start = time.time()
        result = chm_connector.authenticate()
        logger.info(f"Live authenticate result: {result}, took {time.time() - start:.2f}s")
        assert result, "Live API authentication failed"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status_code": 200, "paging": {"total_count": 0, "page": 1, "page_size": 1}, "errors": None, "data": []}
            mock_response.raise_for_status = mocker.Mock()
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            result = chm_connector.authenticate()
            assert result, "Mocked API authentication failed"

def test_get_people(chm_connector, mocker, mock_chm_people_data):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        start = time.time()
        people = chm_connector.get_people()
        elapsed = time.time() - start
        logger.info(f"Live people retrieved: {len(people)} total, took {elapsed:.2f}s")
        assert isinstance(people, list), "Live people data should be a list"
        assert len(people) > 0, "Live test should return non-empty people list"
        logger.info(f"Total people in ChMeetings: {len(people)}")
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = mocker.Mock()
            # Wrap in new API format
            mock_response.json.return_value = {"status_code": 200, "paging": {"total_count": 3, "page": 1, "page_size": 100}, "errors": None, "data": mock_chm_people_data}
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            people = chm_connector.get_people({"page": 1, "page_size": 100})
            assert len(people) == 3, "Expected three people from mock data"


def test_get_people_pagination(chm_connector, mocker, mock_chm_people_data):
    """Verify multi-page pagination terminates correctly using total_count."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        pytest.skip("Pagination logic covered by test_get_people in live mode")

    page1_data = mock_chm_people_data[:2]   # Jerry, Khoi
    page2_data = mock_chm_people_data[2:]   # John

    call_count = {"n": 0}

    def paged_get(*args, **kwargs):
        call_count["n"] += 1
        mock_resp = mocker.Mock()
        mock_resp.status_code = 200
        if call_count["n"] == 1:
            mock_resp.json.return_value = {
                "paging": {"total_count": 3, "page": 1, "page_size": 2},
                "data": page1_data,
            }
        else:
            mock_resp.json.return_value = {
                "paging": {"total_count": 3, "page": 2, "page_size": 2},
                "data": page2_data,
            }
        return mock_resp

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("requests.Session.get", paged_get)
        people = chm_connector.get_people()

    assert len(people) == 3, "All 3 people should be collected across 2 pages"
    assert call_count["n"] == 2, "Should have made exactly 2 page requests"


def test_get_people_request_params(chm_connector, mocker):
    """Verify include_additional_fields and include_family_members are sent."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        pytest.skip("Param verification is a mock-only test")

    captured = {}

    def capturing_get(url, **kwargs):
        captured["params"] = kwargs.get("params", {})
        mock_resp = mocker.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "paging": {"total_count": 0, "page": 1, "page_size": 100},
            "data": [],
        }
        return mock_resp

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("requests.Session.get", capturing_get)
        chm_connector.get_people()

    assert captured["params"].get("include_additional_fields") is True, \
        "include_additional_fields must be True"
    assert captured["params"].get("include_family_members") is False, \
        "include_family_members must be False"
    assert captured["params"].get("page_size") == 100, \
        "page_size should default to 100"

def test_get_person(chm_connector, mocker, mock_chm_people_data):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    # Use an ID that exists in mock_chm_people_data.json
    person_id = "3505203"  # Jerry Phan - Keep as string

    if live_test:
        # Try the hardcoded ID first (season reset keeps people in ChMeetings).
        # Only do an expensive paginated discovery if the ID is gone.
        start = time.time()
        person = chm_connector.get_person(person_id)
        if person is None:
            logger.info(f"Hardcoded person_id {person_id} not found; discovering a real ID...")
            people = chm_connector.get_people({"include_additional_fields": False})
            assert people, "Live get_people returned no records — cannot test get_person"
            person_id = str(people[0]["id"])
            logger.info(f"Using live person_id: {person_id}")
            person = chm_connector.get_person(person_id)

        logger.info("========== FULL RAW PERSON DATA ==========")
        logger.info(f"Person ID: {person_id}")
        for key, value in person.items():
            if key != "additional_fields":
                logger.info(f"{key}: {value}")
        logger.info("-------- ADDITIONAL FIELDS --------")
        for field in person.get("additional_fields", []):
            logger.info(f"Field: {field.get('field_name', 'Unknown')} = {field.get('value', 'None')}")
        logger.info("========== END OF RAW PERSON DATA ==========")

        logger.info(f"Live person retrieved: {person}, took {time.time() - start:.2f}s")
        assert person is not None, "Live person retrieval failed"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = mocker.Mock()
            # Use next with a default value to avoid StopIteration if the ID is missing
            person_data = next((p for p in mock_chm_people_data if str(p["id"]) == person_id), None)
            assert person_data is not None, "Mock data should contain the person"
            # New API returns person directly (not wrapped) for single entity
            mock_response.json.return_value = person_data
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            person = chm_connector.get_person(person_id)
            assert str(person["id"]) == person_id, "Person ID mismatch"
            
def test_get_group_people(chm_connector, mocker, mock_chm_people_data):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    group_id = "870578"  # Real ID from your data (Team RPC)
    if live_test:
        start = time.time()
        people = chm_connector.get_group_people(group_id)
        logger.info(f"Live group people retrieved: {len(people)} - {people}, took {time.time() - start:.2f}s")
        assert isinstance(people, list), "Live group people data should be a list"
        assert people, "Live test should return non-empty group people list"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            # Wrap in "data" key if required by the method
            mock_response.raise_for_status = mocker.Mock()
            mock_response.json.return_value = {"status_code": 200, "errors": None, "data": mock_chm_people_data[:2]}
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            people = chm_connector.get_group_people("G1")
            assert len(people) == 2, "Expected two people in group from mock data"
            
def test_add_person_to_group(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    test_group_id = os.getenv("CHM_TEST_GROUP_ID", "")
    test_person_id = os.getenv("CHM_TEST_PERSON_ID", "")

    if live_test:
        if not test_group_id or not test_person_id:
            pytest.skip(
                "Set CHM_TEST_GROUP_ID and CHM_TEST_PERSON_ID env vars to run live group membership tests"
            )
        result = chm_connector.add_person_to_group(test_group_id, test_person_id)
        assert result, f"Live add_person_to_group failed for person {test_person_id} → group {test_group_id}"
        logger.info(f"Live: added person {test_person_id} to group {test_group_id}")
        # Verify membership via get_group_people
        members = chm_connector.get_group_people(test_group_id)
        member_ids = [str(m.get("person_id") or m.get("id", "")) for m in members]
        assert test_person_id in member_ids, "Person not found in group after add"
    else:
        # 201 — newly added
        mock_response = mocker.Mock()
        mock_response.status_code = 201
        mocker.patch.object(chm_connector.session, "post", return_value=mock_response)
        assert chm_connector.add_person_to_group("G1", "P1") is True, "Should return True on 201"

        # 200 — already a member (also success)
        mock_response.status_code = 200
        assert chm_connector.add_person_to_group("G1", "P1") is True, "Should return True on 200 (already member)"

        # Failure — API error
        mocker.patch.object(
            chm_connector.session, "post",
            side_effect=requests.RequestException("connection error")
        )
        assert chm_connector.add_person_to_group("G1", "P1") is False, "Should return False on error"


def test_remove_person_from_group(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    test_group_id = os.getenv("CHM_TEST_GROUP_ID", "")
    test_person_id = os.getenv("CHM_TEST_PERSON_ID", "")

    if live_test:
        if not test_group_id or not test_person_id:
            pytest.skip(
                "Set CHM_TEST_GROUP_ID and CHM_TEST_PERSON_ID env vars to run live group membership tests"
            )
        # Remove (person was added by test_add_person_to_group above)
        result = chm_connector.remove_person_from_group(test_group_id, test_person_id)
        assert result, f"Live remove_person_from_group failed for person {test_person_id} → group {test_group_id}"
        logger.info(f"Live: removed person {test_person_id} from group {test_group_id}")
        # Verify no longer a member
        members = chm_connector.get_group_people(test_group_id)
        member_ids = [str(m.get("person_id") or m.get("id", "")) for m in members]
        assert test_person_id not in member_ids, "Person still in group after remove"
    else:
        # Success — 200
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mocker.patch.object(chm_connector.session, "delete", return_value=mock_response)
        assert chm_connector.remove_person_from_group("G1", "P1") is True, "Should return True on 200"

        # Failure — API error (e.g. person not in group)
        mocker.patch.object(
            chm_connector.session, "delete",
            side_effect=requests.RequestException("not found")
        )
        assert chm_connector.remove_person_from_group("G1", "P1") is False, "Should return False on error"


def test_get_groups(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        start = time.time()
        groups = chm_connector.get_groups()
        logger.info(f"Live groups retrieved: {len(groups)} - {groups}, took {time.time() - start:.2f}s")
        assert isinstance(groups, list), "Live groups data should be a list"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = mocker.Mock()
            mock_response.json.return_value = {"status_code": 200, "errors": None, "data": [{"id": "G1", "name": "Sports Team"}]}
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            groups = chm_connector.get_groups()
            assert len(groups) == 1, "Expected one group"

def test_close(chm_connector, mocker):
    mock_session_close = mocker.patch.object(chm_connector.session, "close")
    chm_connector.close()
    mock_session_close.assert_called_once()


# ── Tests for Season Reset connector methods ─────────────────────────────────

def test_get_person_notes(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    person_id = "3505203"
    if live_test:
        start = time.time()
        notes = chm_connector.get_person_notes(person_id)
        logger.info(f"Live notes for {person_id}: {notes}, took {time.time() - start:.2f}s")
        assert isinstance(notes, list), "Notes should be a list"
    else:
        mock_notes = [
            {"note": "Sports Fest 2024 Archive — 2025-01-10 | Team: RPC"},
            {"note": "Some other note"},
        ]
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_notes
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            notes = chm_connector.get_person_notes(person_id)
            assert len(notes) == 2
            assert "Sports Fest 2024 Archive" in notes[0]["note"]


def test_get_person_notes_wrapped_in_data(chm_connector, mocker):
    """API may return notes inside a 'data' key."""
    mock_notes = [{"note": "some note"}]
    with pytest.MonkeyPatch.context() as mp:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": mock_notes}
        mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
        notes = chm_connector.get_person_notes("123")
        assert len(notes) == 1


def test_get_person_notes_returns_empty_on_error(chm_connector, mocker):
    import requests as req
    with pytest.MonkeyPatch.context() as mp:
        def raise_error(*args, **kwargs):
            raise req.RequestException("network error")
        mp.setattr("requests.Session.get", raise_error)
        notes = chm_connector.get_person_notes("123")
        assert notes == []

def test_get_member_fields(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    mock_fields = [
        {"field_id": 1282085, "field_name": "My role is", "field_type": "checkbox"},
        {"field_id": 1281851, "field_name": "Church Team", "field_type": "dropdown"},
    ]
    if live_test:
        start = time.time()
        fields = chm_connector.get_member_fields()
        logger.info(f"Live fields retrieved: {len(fields)}, took {time.time() - start:.2f}s")
        assert isinstance(fields, list), "Fields should be a list"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_fields
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            fields = chm_connector.get_member_fields()
            assert len(fields) == 2, "Expected two fields from mock data"
            assert fields[0]["field_id"] == 1282085


def test_get_member_fields_wrapped_in_data(chm_connector, mocker):
    """API may return fields inside a 'data' key."""
    mock_fields = [{"field_id": 1281847, "field_name": "Primary Sport", "field_type": "dropdown"}]
    with pytest.MonkeyPatch.context() as mp:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": mock_fields}
        mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
        fields = chm_connector.get_member_fields()
        assert len(fields) == 1
        assert fields[0]["field_name"] == "Primary Sport"


def test_get_member_fields_returns_empty_on_error(chm_connector, mocker):
    """get_member_fields returns [] when the API call fails."""
    import requests as req
    with pytest.MonkeyPatch.context() as mp:
        def raise_error(*args, **kwargs):
            raise req.RequestException("network error")
        mp.setattr("requests.Session.get", raise_error)
        fields = chm_connector.get_member_fields()
        assert fields == []


def test_add_member_note(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    person_id = "3505203"
    note_text = "Sports Fest 2025 | Team: RPC | Primary: Badminton | Member: Yes"
    if live_test:
        start = time.time()
        result = chm_connector.add_member_note(person_id, note_text)
        logger.info(f"Live add_member_note result: {result}, took {time.time() - start:.2f}s")
        assert result, "Live add_member_note should succeed"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 201
            mock_response.raise_for_status = lambda: None
            mp.setattr("requests.Session.post", lambda *args, **kwargs: mock_response)
            result = chm_connector.add_member_note(person_id, note_text)
            assert result is True, "Mocked add_member_note should return True"


def test_add_member_note_returns_false_on_error(chm_connector, mocker):
    """add_member_note returns False when the API call fails."""
    import requests as req
    with pytest.MonkeyPatch.context() as mp:
        def raise_error(*args, **kwargs):
            raise req.RequestException("network error")
        mp.setattr("requests.Session.post", raise_error)
        result = chm_connector.add_member_note("123", "some note")
        assert result is False


def test_update_person(chm_connector, mocker):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    person_id = "3505203"
    additional_fields = [
        {"field_id": 1282085, "selected_option_ids": []},
        {"field_id": 1281851, "selected_option_id": None},
        {"field_id": 1313282, "value": None},
    ]
    if live_test:
        start = time.time()
        result = chm_connector.update_person(person_id, "Jerry", "Phan", additional_fields)
        logger.info(f"Live update_person result: {result}, took {time.time() - start:.2f}s")
        assert result, "Live update_person should succeed"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = lambda: None
            captured = {}

            def fake_put(url, json=None, **kwargs):
                captured["url"] = url
                captured["json"] = json
                return mock_response

            mp.setattr("requests.Session.put", fake_put)
            result = chm_connector.update_person(person_id, "Jerry", "Phan", additional_fields)
            assert result is True, "Mocked update_person should return True"
            assert "additional_fields" in captured["json"]
            assert len(captured["json"]["additional_fields"]) == 3
            assert captured["json"]["first_name"] == "Jerry"
            assert captured["json"]["last_name"] == "Phan"


def test_update_person_returns_false_on_error(chm_connector, mocker):
    """update_person returns False when the API call fails."""
    import requests as req
    with pytest.MonkeyPatch.context() as mp:
        def raise_error(*args, **kwargs):
            raise req.RequestException("network error")
        mp.setattr("requests.Session.put", raise_error)
        result = chm_connector.update_person("123", "A", "B", [])
        assert result is False