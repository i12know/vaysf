import os
import json
import pytest
import sys
import time
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
    with ChMeetingsConnector(use_api=True, use_selenium=False) as connector:
        logger.info(f"Test mode: {'Live' if live_test else 'Mocked'}, API URL: {connector.api_url}")
        yield connector

def test_chm_connector_init(chm_connector):
    assert chm_connector is not None, "ChMeetingsConnector failed to initialize"
    assert chm_connector.use_api, "API usage should be enabled"
    assert not chm_connector.use_selenium, "Selenium should be disabled"

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
            mock_response.json.return_value = {"data": []}
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            result = chm_connector.authenticate()
            assert result, "Mocked API authentication failed"

def test_get_people(chm_connector, mocker, mock_chm_people_data):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        start = time.time()
        people = chm_connector.get_people({"page": 1, "page_size": 10})
        logger.info(f"Live people retrieved: {len(people)} - {people}, took {time.time() - start:.2f}s")
        assert isinstance(people, list), "Live people data should be a list"
        assert people, "Live test should return non-empty people list"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            # Use the full JSON data
            mock_response.json.return_value = mock_chm_people_data
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            people = chm_connector.get_people({"page": 1, "page_size": 50})
            assert len(people) == 3, "Expected three people from mock data"

def test_get_person(chm_connector, mocker, mock_chm_people_data):
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    # Use an ID that exists in mock_chm_people_data.json
    person_id = "3505203"  # Jerry Phan - Keep as string
## NEW CODE:
    if live_test:
        start = time.time()
        person = chm_connector.get_person(person_id)
        
        # Enhanced logging - dump the full raw person data
        logger.info("========== FULL RAW PERSON DATA ==========")
        logger.info(f"Person ID: {person_id}")
        
        # Log all top-level fields
        for key, value in person.items():
            if key != "additional_fields":
                logger.info(f"{key}: {value}")
        
        # Log each additional field separately for clarity
        logger.info("-------- ADDITIONAL FIELDS --------")
        if "additional_fields" in person:
            additional_fields = person["additional_fields"]
            for field in additional_fields:
                field_name = field.get("field_name", "Unknown")
                field_value = field.get("value", "None")
                logger.info(f"Field: {field_name} = {field_value}")
        
        logger.info("========== END OF RAW PERSON DATA ==========")
## OLD CODE:
#    if live_test:
#        start = time.time()
#        person = chm_connector.get_person(person_id)
        logger.info(f"Live person retrieved: {person}, took {time.time() - start:.2f}s")
        assert person is not None, "Live person retrieval failed"
    else:
        with pytest.MonkeyPatch.context() as mp:
            mock_response = mocker.Mock()
            mock_response.status_code = 200
            # Use next with a default value to avoid StopIteration if the ID is missing
            person_data = next((p for p in mock_chm_people_data if str(p["id"]) == person_id), None)
            assert person_data is not None, "Mock data should contain the person"
            mock_response.json.return_value = person_data
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            person = chm_connector.get_person(person_id)
            assert str(person["id"]) == person_id, "Person ID mismatch"  # Convert to string here
            
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
            mock_response.json.return_value = {"data": mock_chm_people_data[:2]}  # Jerry and Khoi (RPC)
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            people = chm_connector.get_group_people("G1")
            assert len(people) == 2, "Expected two people in group from mock data"
            
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
            mock_response.json.return_value = [{"id": "G1", "Name": "Sports Team"}]
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            groups = chm_connector.get_groups()
            assert len(groups) == 1, "Expected one group"

def test_close(chm_connector, mocker):
    mock_session_close = mocker.patch.object(chm_connector.session, "close")
    chm_connector.close()
    mock_session_close.assert_called_once()


# ── Tests for Season Reset connector methods ─────────────────────────────────

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