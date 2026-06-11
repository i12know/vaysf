# test_wordpress_connector.py

import os
import pytest
import requests
from http.client import RemoteDisconnected
from tenacity import RetryError
from wordpress.frontend_connector import WordPressConnector
from loguru import logger
from wordpress.frontend_connector import Config
from conftest import require_live_mutation_test

@pytest.fixture
def wp_connector(mocker):
    """Fixture to create a WordPressConnector instance, mocking if not live."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    logger.info(f"LIVE_TEST from env: {os.getenv('LIVE_TEST')} -> live_test: {live_test}")
    if not live_test:
        mocker.patch("wordpress.frontend_connector.Config.WP_URL", "https://test.wordpress.com")
        mocker.patch("wordpress.frontend_connector.Config.WP_API_KEY", "test_api_key")
    connector = WordPressConnector()
    logger.info(f"Test mode: {'Live' if live_test else 'Mocked'}, API URL: {connector.api_url}")
    yield connector
    connector.close()

def test_connectivity(wp_connector, mocker):
    """Test basic connectivity to WordPress."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        churches = wp_connector.get_churches()
        logger.info(f"Live churches retrieved: {len(churches)} - {churches}")
        assert churches is not None, "Failed to connect to WordPress"
        assert isinstance(churches, list), "Churches should be a list"
    else:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "name": "Mock Church"}]
        mocker.patch.object(wp_connector.session, "get", return_value=mock_response)
        churches = wp_connector.get_churches()
        logger.info(f"Mocked churches retrieved: {len(churches)} - {churches}")
        assert churches is not None, "Mocked connectivity failed"
        assert isinstance(churches, list), "Mocked churches should be a list"
        assert len(churches) == 1, "Expected one mocked church"

def test_create_and_update_church(wp_connector, mocker):
    """Test creating and updating a church."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    test_church = {
        "church_name": "Test Church Pytest",
        "church_code": "PYT",
        "pastor_name": "Pastor Pytest",
        "pastor_email": "pastor@pytest.org",
        "pastor_phone": "555-555-5555",
        "church_rep_name": "Rep Pytest",
        "church_rep_email": "rep@pytest.org",
        "church_rep_phone": "555-555-5556",
        "sports_ministry_level": 2
    }
    update_data = {"church_name": "Updated Test Church Pytest", "sports_ministry_level": 3}  # Moved outside if/else

    if live_test:
        require_live_mutation_test("creating/updating a live WordPress church record")
        # Create
        new_church = wp_connector.create_church(test_church)
        if new_church:
            logger.info(f"Live created church: {new_church}")
            assert new_church.get("church_name") == "Test Church Pytest", "Church name mismatch"
        else:
            logger.warning("Church creation failed, possibly exists; proceeding with update")

        # Get by code
        church = wp_connector.get_church_by_code("PYT")
        logger.info(f"Live church by code: {church}")
        assert church is not None, "Failed to retrieve church by code"
        assert church["church_code"] == "PYT", "Church code mismatch"

        # Update
        updated_church = wp_connector.update_church_by_code("PYT", update_data)
        logger.info(f"Live updated church: {updated_church}")
        assert updated_church is not None, "Failed to update church"
        assert updated_church["church_name"] == "Updated Test Church Pytest", "Updated name mismatch"
    else:
        with pytest.MonkeyPatch.context() as mp:
            # Mock create
            mock_create_response = mocker.Mock()
            mock_create_response.status_code = 201
            mock_create_response.json.return_value = test_church
            mp.setattr(wp_connector.session, "post", lambda *args, **kwargs: mock_create_response)

            # Mock get by code
            mock_get_response = mocker.Mock()
            mock_get_response.status_code = 200
            mock_get_response.json.return_value = test_church
            mp.setattr(wp_connector.session, "get", lambda *args, **kwargs: mock_get_response)

            # Mock update
            updated_church_data = {**test_church, **update_data}
            mock_update_response = mocker.Mock()
            mock_update_response.status_code = 200
            mock_update_response.json.return_value = updated_church_data
            mp.setattr(wp_connector.session, "put", lambda *args, **kwargs: mock_update_response)

            # Run the sequence
            new_church = wp_connector.create_church(test_church)
            logger.info(f"Mocked created church: {new_church}")
            assert new_church.get("church_name") == "Test Church Pytest", "Mocked church name mismatch"

            church = wp_connector.get_church_by_code("PYT")
            logger.info(f"Mocked church by code: {church}")
            assert church is not None, "Mocked get church by code failed"
            assert church["church_code"] == "PYT", "Mocked church code mismatch"

            updated_church = wp_connector.update_church_by_code("PYT", update_data)
            logger.info(f"Mocked updated church: {updated_church}")
            assert updated_church is not None, "Mocked update church failed"
            assert updated_church["church_name"] == "Updated Test Church Pytest", "Mocked updated name mismatch"

def test_get_approvals_coerces_bool_params(wp_connector, mocker):
    """Issue #61: Python bools must be serialized as 0/1 in query params, not
    the strings 'True'/'False' — the WordPress REST API's 'args' boolean
    sanitizer tolerates both, but PHP (bool) casts on raw strings read 'False'
    as truthy. Asserts synced_to_chmeetings=False → 0 in the outgoing request."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        pytest.skip("Pure mock test — no live variant needed")

    captured = {}

    def capturing_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        resp = mocker.Mock()
        resp.status_code = 200
        resp.raise_for_status = mocker.Mock()
        resp.json.return_value = []
        return resp

    mocker.patch.object(wp_connector.session, "get", side_effect=capturing_get)

    wp_connector.get_approvals(params={
        "approval_status": "approved",
        "synced_to_chmeetings": False,
        "per_page": 500,
    })

    assert captured["params"] is not None, "get_approvals did not pass params"
    assert captured["params"]["synced_to_chmeetings"] == 0, (
        f"Expected bool False → int 0, got: {captured['params']['synced_to_chmeetings']!r}"
    )
    assert captured["params"]["approval_status"] == "approved", "non-bool params preserved"
    assert captured["params"]["per_page"] == 500, "non-bool params preserved"
    assert wp_connector.last_get_approvals_status == "ok"

    # True must coerce to 1 too
    wp_connector.get_approvals(params={"synced_to_chmeetings": True})
    assert captured["params"]["synced_to_chmeetings"] == 1, (
        f"Expected bool True → int 1, got: {captured['params']['synced_to_chmeetings']!r}"
    )


def test_get_approvals_records_failed_read_status(wp_connector, mocker):
    mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=requests.ConnectionError("WordPress unavailable"),
    )

    result = wp_connector.get_approvals(
        params={"approval_status": "approved", "synced_to_chmeetings": False}
    )

    assert result == []
    assert wp_connector.last_get_approvals_status == "failed"


def test_send_email(wp_connector, mocker):
    """Test sending an email."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    email_data = {
        "to": "pastorbumble@gmail.com",
        "subject": "Pytest Email Test",
        "message": "<p>Test email from pytest</p>",
        "from_email": "SportsFest Staff <info@sportsfest.vayhub.us>",
        "cc": ["churchrep@example.com"],
        "bcc": ["ops@example.com"],
    }

    if live_test:
        require_live_mutation_test("sending a real WordPress email")
        result = wp_connector.send_email(**email_data)
        logger.info(f"Live email result: {result}")
        assert result.get("success", False), "Live email sending failed"
    else:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mocked_post = mocker.patch.object(wp_connector.session, "post", return_value=mock_response)
        result = wp_connector.send_email(**email_data)
        logger.info(f"Mocked email result: {result}")
        assert result.get("success", False), "Mocked email sending failed"
        mocked_post.assert_called_once_with(
            f"{wp_connector.custom_api_url}/send-email",
            json={
                "to": "pastorbumble@gmail.com",
                "subject": "Pytest Email Test",
                "message": "<p>Test email from pytest</p>",
                "from": "SportsFest Staff <info@sportsfest.vayhub.us>",
                "cc": ["churchrep@example.com"],
                "bcc": ["ops@example.com"],
            },
        )


def test_update_validation_issue_empty_success_response(wp_connector, mocker):
    """A successful empty 2xx response should count as an update, not an error."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    if live_test:
        pytest.skip("Pure mock test — no live variant needed")

    issue_data = {
        "status": "resolved",
        "resolved_at": "2026-05-07 22:15:09",
    }

    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_response.raise_for_status = mocker.Mock()

    mocker.patch.object(wp_connector.session, "put", return_value=mock_response)

    result = wp_connector.update_validation_issue(234, issue_data)

    assert result is not None, "Successful empty response should not be treated as a failure"
    assert result["issue_id"] == 234
    assert result["status"] == "resolved"
    assert wp_connector.last_update_validation_issue_status == "empty_success"


# ---------------------------------------------------------------------------
# Retry behaviour — transient RemoteDisconnected
# ---------------------------------------------------------------------------

def _connection_error():
    """Build a requests.ConnectionError wrapping RemoteDisconnected, as requests does."""
    return requests.exceptions.ConnectionError(
        ("Connection aborted.", RemoteDisconnected("Remote end closed connection without response"))
    )


def test_get_rosters_retries_on_transient_disconnect(wp_connector, mocker):
    """get_rosters() retries on ConnectionError and returns data on recovery."""
    mocker.patch("time.sleep")

    good_response = mocker.Mock()
    good_response.status_code = 200
    good_response.json.return_value = [{"roster_id": 1}]
    good_response.raise_for_status = mocker.Mock()

    mock_get = mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=[_connection_error(), _connection_error(), good_response],
    )

    result = wp_connector.get_rosters({"participant_id": 42})

    assert result == [{"roster_id": 1}]
    assert mock_get.call_count == 3


def test_get_rosters_raises_retry_error_after_exhausted_attempts(wp_connector, mocker):
    """get_rosters() raises RetryError when all retry attempts fail."""
    mocker.patch("time.sleep")

    mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=_connection_error(),
    )

    with pytest.raises(RetryError):
        wp_connector.get_rosters({"participant_id": 42})


def test_get_participants_retries_on_transient_disconnect(wp_connector, mocker):
    """get_participants() retries on ConnectionError and returns data on recovery."""
    mocker.patch("time.sleep")

    good_response = mocker.Mock()
    good_response.status_code = 200
    good_response.headers = {}
    good_response.json.return_value = [{"participant_id": 7}]
    good_response.raise_for_status = mocker.Mock()

    mock_get = mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=[_connection_error(), good_response],
    )

    result = wp_connector.get_participants({"chmeetings_id": "123"})

    assert result == [{"participant_id": 7}]
    assert mock_get.call_count == 2


def test_get_participants_raises_retry_error_after_exhausted_attempts(wp_connector, mocker):
    """get_participants() raises RetryError when all retry attempts fail."""
    mocker.patch("time.sleep")

    mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=_connection_error(),
    )

    with pytest.raises(RetryError):
        wp_connector.get_participants({"chmeetings_id": "123"})


def test_get_church_by_code_retries_on_transient_disconnect(wp_connector, mocker):
    """get_church_by_code() retries on ConnectionError and returns data on recovery."""
    mocker.patch("time.sleep")

    good_response = mocker.Mock()
    good_response.status_code = 200
    good_response.json.return_value = {"church_id": 15, "church_code": "GLA"}
    good_response.raise_for_status = mocker.Mock()

    mock_get = mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=[_connection_error(), good_response],
    )

    result = wp_connector.get_church_by_code("GLA")

    assert result == {"church_id": 15, "church_code": "GLA"}
    assert mock_get.call_count == 2


def test_get_church_by_code_raises_retry_error_after_exhausted_attempts(wp_connector, mocker):
    """get_church_by_code() raises RetryError when all transient attempts fail."""
    mocker.patch("time.sleep")

    mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=_connection_error(),
    )

    with pytest.raises(RetryError):
        wp_connector.get_church_by_code("GLA")


def test_get_rosters_does_not_retry_non_transient_errors(wp_connector, mocker):
    """Non-transient HTTP errors should fail immediately without retry."""
    mocker.patch("time.sleep")

    bad_response = mocker.Mock()
    bad_response.status_code = 500
    bad_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=bad_response
    )

    mock_get = mocker.patch.object(
        wp_connector.session, "get", return_value=bad_response
    )

    result = wp_connector.get_rosters()

    assert result == []
    assert mock_get.call_count == 1


def test_get_validation_issues_retries_on_transient_disconnect(wp_connector, mocker):
    """get_validation_issues() retries on ConnectionError and returns data on recovery."""
    mocker.patch("time.sleep")

    good_response = mocker.Mock()
    good_response.status_code = 200
    good_response.json.return_value = [{"issue_id": 5, "status": "open"}]
    good_response.raise_for_status = mocker.Mock()

    mock_get = mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=[_connection_error(), _connection_error(), good_response],
    )

    result = wp_connector.get_validation_issues({"church_id": 10, "status": "open"})

    assert result == [{"issue_id": 5, "status": "open"}]
    assert mock_get.call_count == 3
    assert wp_connector.last_get_validation_issues_status == "ok"


def test_get_validation_issues_raises_retry_error_after_exhausted_attempts(wp_connector, mocker):
    """get_validation_issues() raises RetryError when all retry attempts fail."""
    mocker.patch("time.sleep")

    mocker.patch.object(
        wp_connector.session,
        "get",
        side_effect=_connection_error(),
    )

    with pytest.raises(RetryError):
        wp_connector.get_validation_issues({"church_id": 10})


def test_get_validation_issues_does_not_retry_non_transient_errors(wp_connector, mocker):
    """Non-transient HTTP errors from get_validation_issues() fail immediately."""
    mocker.patch("time.sleep")

    bad_response = mocker.Mock()
    bad_response.status_code = 500
    bad_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=bad_response
    )

    mock_get = mocker.patch.object(
        wp_connector.session, "get", return_value=bad_response
    )

    result = wp_connector.get_validation_issues()

    assert result == []
    assert mock_get.call_count == 1
    assert wp_connector.last_get_validation_issues_status == "failed"
