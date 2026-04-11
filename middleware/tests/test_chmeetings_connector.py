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
            mock_response.json.return_value = {
                "paging": {"total_count": 3, "page": 1, "page_size": 100},
                "data": mock_chm_people_data,
            }
            mp.setattr("requests.Session.get", lambda *args, **kwargs: mock_response)
            people = chm_connector.get_people()
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
        # Discover a real person ID from the live API (page 1, first record)
        people = chm_connector.get_people({"page": 1, "page_size": 1})
        assert people, "Live get_people returned no records — cannot test get_person"
        person_id = str(people[0]["id"])
        logger.info(f"Using live person_id: {person_id}")

        start = time.time()
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
            # Use next with a default value to avoid StopIteration if the ID is missing
            person_data = next((p for p in mock_chm_people_data if str(p["id"]) == person_id), None)
            assert person_data is not None, "Mock data should contain the person"
            mock_response.json.return_value = {"data": person_data}
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