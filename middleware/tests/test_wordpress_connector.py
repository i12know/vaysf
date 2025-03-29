# test_wordpress_connector.py

import os
import pytest
from wordpress.frontend_connector import WordPressConnector
from loguru import logger
from wordpress.frontend_connector import Config

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

def test_send_email(wp_connector, mocker):
    """Test sending an email."""
    live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
    email_data = {
        "to": "pastorbumble@gmail.com",
        "subject": "Pytest Email Test",
        "message": "<p>Test email from pytest</p>",
        "from_email": "SportsFest Staff <info@sportsfest.vayhub.us>"
    }

    if live_test:
        result = wp_connector.send_email(**email_data)
        logger.info(f"Live email result: {result}")
        assert result.get("success", False), "Live email sending failed"
    else:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mocker.patch.object(wp_connector.session, "post", return_value=mock_response)
        result = wp_connector.send_email(**email_data)
        logger.info(f"Mocked email result: {result}")
        assert result.get("success", False), "Mocked email sending failed"