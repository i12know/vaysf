# chmeetings/backend-connector.py

import os
import requests
import time
from typing import Dict, List, Optional, Union, Any
from urllib.parse import urljoin
from loguru import logger

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from config import Config

class ChMeetingsAPIError(Exception):
    """Exception raised for ChMeetings API errors."""
    pass


# Fields returned by GET /api/v1/people/{id} that must NOT be sent in
# PUT /api/v1/people/{id}.  Sending them causes HTTP 400 or 500 errors:
#   - full_name      : computed by the server from first + last name
#   - photo          : managed via a separate upload endpoint
#   - created_on /
#     updated_on     : server-managed timestamps (read-only)
#   - family         : related-record array, not a writable person field
#   - is_archived /
#     archived_at    : managed via archive/unarchive actions, not PUT
# first_name, last_name, id, additional_fields are passed as explicit
# parameters and are always excluded here too.
PERSON_PUT_EXCLUDE = frozenset({
    "id", "first_name", "last_name",
    "full_name",
    "photo",
    "created_on", "updated_on",
    "family",
    "is_archived", "archived_at",
    "additional_fields",
})

class ChMeetingsConnector:
    """Connector for ChMeetings API and web interface."""


    def __init__(self, use_api: bool = True, use_selenium: bool = False):
        self.api_url = Config.CHM_API_URL
        self.api_key = Config.CHM_API_KEY  # Replace username/password with api_key
        self.use_api = use_api
        self.use_selenium = use_selenium
        self.session = requests.Session()
        # Set headers with API key
        self.session.headers.update({
            "accept": "application/json",
            "ApiKey": self.api_key  # Or try "Api-Key" or "Authorization" based on what works
        })
        self.selenium_driver = None
        
        if self.use_selenium:
            self._init_selenium()

        
    def _init_selenium(self):
        """Initialize Selenium WebDriver for Windows."""
        options = Options()
        
        # Set headless mode if configured
        if Config.USE_CHROME_HEADLESS:
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")  # Required for Windows
        
        # Add common options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")  # Set a reasonable window size
        
        # Add user profile if specified
        if Config.CHROME_PROFILE_DIR and os.path.exists(Config.CHROME_PROFILE_DIR):
            options.add_argument(f"--user-data-dir={Config.CHROME_PROFILE_DIR}")
        
        # Initialize driver with specific path or using webdriver-manager
        if Config.CHROME_DRIVER_PATH and os.path.exists(Config.CHROME_DRIVER_PATH):
            self.selenium_driver = webdriver.Chrome(
                service=Service(Config.CHROME_DRIVER_PATH),
                options=options
            )
        else:
            # Use webdriver-manager to auto-download the correct chromedriver
            self.selenium_driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
        
        logger.info("Selenium WebDriver initialized for Chrome on Windows")
    
    def authenticate(self) -> bool:
        """
        Verify API key works by testing a simple request.
        Returns True if successful.
        """
        if self.use_api:
            try:
                # Test the API key with a basic request (e.g., to /people)
                response = self.session.get(
                    urljoin(self.api_url, "api/v1/people"),
                    params={"page": 1, "page_size": 10}
                )
                response.raise_for_status()
                logger.info("API key verified successfully with ChMeetings API")
                return True
            except requests.RequestException as e:
                logger.error(f"API key verification failed: {str(e)}")
                return False
                
        if self.use_selenium and self.selenium_driver:
            try:
                self.selenium_driver.get(urljoin(self.api_url.replace("api.", ""), "login"))
                
                # Wait for login form
                username_field = WebDriverWait(self.selenium_driver, 10).until(
                    EC.presence_of_element_located((By.ID, "username"))
                )
                password_field = self.selenium_driver.find_element(By.ID, "password")
                
                # Fill in login form
                username_field.send_keys(self.username)
                password_field.send_keys(self.password)
                
                # Submit form
                password_field.submit()
                
                # Wait for successful login
                WebDriverWait(self.selenium_driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".dashboard"))
                )
                
                logger.info("Successfully authenticated with ChMeetings via Selenium")
                return True
            except Exception as e:
                logger.error(f"Failed to authenticate with ChMeetings via Selenium: {str(e)}")
                
                # Take screenshot if debugging is enabled
                if Config.DEBUG and self.selenium_driver:
                    screenshot_path = os.path.join(Config.TEMP_DIR, f"auth_error_{int(time.time())}.png")
                    self.selenium_driver.save_screenshot(screenshot_path)
                    logger.info(f"Screenshot saved to {screenshot_path}")
                
                return False
        
        return False

    
    def get_people(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get people records from ChMeetings.
        
        Args:
            params: Query parameters
            
        Returns:
            List of people records
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return []
        
        all_people = []
        page = 1
        page_size = 50  # Adjust based on API limits if needed
        params = params or {}
        
        while True:
            params.update({"page": page, "page_size": page_size})
            try:
                response = self.session.get(
                    urljoin(self.api_url, "api/v1/people"),
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                people = data if isinstance(data, list) else data.get("data", [])
                all_people.extend(people)
                logger.info(f"Fetched page {page}: {len(people)} people")
                if len(people) < page_size:  # No more pages
                    break
                page += 1
            except requests.RequestException as e:
                logger.error(f"Failed to get people on page {page}: {str(e)}")
                break
        
        return all_people

    
    def get_person(self, person_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific person record from ChMeetings.
        
        Args:
            person_id: The person ID
            
        Returns:
            Person record or None if not found
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return None
        
        try:
            response = self.session.get(
                urljoin(self.api_url, f"api/v1/people/{person_id}")
            )
            response.raise_for_status()
            data = response.json()
            # Unwrap {"status_code":..., "data": {...}} envelope if present
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            return data
        except requests.RequestException as e:
            logger.error(f"Failed to get person {person_id}: {str(e)}")
            return None

    
    def get_groups(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get groups from ChMeetings.
        
        Args:
            params: Query parameters
            
        Returns:
            List of group records
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return []
        try:
            response = self.session.get(
                urljoin(self.api_url, "api/v1/groups"),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else data.get("data", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get groups: {str(e)}")
            return []

    
    def get_group_people(self, group_id: str) -> List[Dict[str, Any]]:
        """
        Get people in a specific group from ChMeetings.
        
        Args:
            group_id: The group ID
            
        Returns:
            List of people in the group
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return []
        try:
            response = self.session.get(
                urljoin(self.api_url, "api/v1/groups/people"),
                params={"group_ids": group_id}  # Note the plural "group_ids"
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", []) if isinstance(data, dict) else data
        except requests.RequestException as e:
            logger.error(f"Failed to get people in group {group_id}: {str(e)}")
            return []
    
    def update_person_via_selenium(self, person_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update a person record using Selenium (for cases where API doesn't support the operation).
        
        Args:
            person_id: The person ID
            update_data: Data to update
            
        Returns:
            True if successful
        """
        if not self.use_selenium or not self.selenium_driver:
            logger.error("Selenium usage is disabled")
            return False
        
        try:
            # Navigate to the person edit page
            self.selenium_driver.get(urljoin(
                self.api_url.replace("api.", ""),
                f"people/{person_id}/edit"
            ))
            
            # Take screenshot if debugging is enabled
            if Config.DEBUG:
                screenshot_path = os.path.join(Config.TEMP_DIR, f"person_edit_{person_id}.png")
                self.selenium_driver.save_screenshot(screenshot_path)
                logger.info(f"Screenshot saved to {screenshot_path}")
            
            # Wait for the form to load
            WebDriverWait(self.selenium_driver, 10).until(
                EC.presence_of_element_located((By.ID, "personForm"))
            )
            
            # Update fields
            for field, value in update_data.items():
                try:
                    field_element = self.selenium_driver.find_element(By.ID, field)
                    field_element.clear()
                    field_element.send_keys(str(value))
                except Exception as e:
                    logger.warning(f"Failed to update field {field}: {str(e)}")
            
            # Submit form
            self.selenium_driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            
            # Wait for success message
            WebDriverWait(self.selenium_driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".alert-success"))
            )
            
            logger.info(f"Successfully updated person {person_id} via Selenium")
            return True
        except Exception as e:
            logger.error(f"Failed to update person {person_id} via Selenium: {str(e)}")
            
            # Take error screenshot if debugging is enabled
            if Config.DEBUG and self.selenium_driver:
                screenshot_path = os.path.join(Config.TEMP_DIR, f"person_edit_error_{person_id}.png")
                self.selenium_driver.save_screenshot(screenshot_path)
                logger.info(f"Error screenshot saved to {screenshot_path}")
            
            return False
    
    def get_person_notes(self, person_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve existing notes from a person's ChMeetings profile.

        Calls GET /api/v1/people/{person_id}/notes.

        Args:
            person_id: ChMeetings person ID.

        Returns:
            List of note dicts (each has at least a ``note`` key), or empty
            list on failure.
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return []
        try:
            response = self.session.get(
                urljoin(self.api_url, f"api/v1/people/{person_id}/notes")
            )
            response.raise_for_status()
            data = response.json()
            notes = data if isinstance(data, list) else data.get("data", [])
            logger.debug(f"Retrieved {len(notes)} note(s) for person {person_id}")
            return notes
        except requests.RequestException as e:
            logger.error(f"Failed to get notes for person {person_id}: {str(e)}")
            return []

    def get_member_fields(self) -> List[Dict[str, Any]]:
        """
        Retrieve all custom field definitions from ChMeetings.

        Calls GET /api/v1/people/fields and returns the full list of field
        definitions, each containing field_id, field_name, field_type, and
        available options.

        Returns:
            List of field definition dicts, or empty list on failure.
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return []
        try:
            response = self.session.get(
                urljoin(self.api_url, "api/v1/people/fields")
            )
            response.raise_for_status()
            data = response.json()
            fields = data if isinstance(data, list) else data.get("data", [])
            logger.info(f"Retrieved {len(fields)} custom field definitions")
            return fields
        except requests.RequestException as e:
            logger.error(f"Failed to get member fields: {str(e)}")
            return []

    def add_member_note(self, person_id: str, note_text: str) -> bool:
        """
        Write a note to a person's ChMeetings profile.

        Calls POST /api/v1/people/{person_id}/notes.

        Args:
            person_id: ChMeetings person ID.
            note_text: Plain-text note content to store on the profile.

        Returns:
            True if the note was created successfully, False otherwise.
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return False
        try:
            response = self.session.post(
                urljoin(self.api_url, f"api/v1/people/{person_id}/notes"),
                json={"note": note_text}
            )
            response.raise_for_status()
            logger.info(f"Added note to person {person_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to add note to person {person_id}: {str(e)}")
            return False

    def update_person(
        self,
        person_id: str,
        first_name: str,
        last_name: str,
        additional_fields: List[Dict[str, Any]],
        *,
        method: str = "PUT",
        extra_person_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update a person's profile including custom field values.

        PUT is a full-replace operation on the ChMeetings API: standard
        person fields not present in the body will be cleared.  Pass
        ``extra_person_data`` (the full dict from ``get_person()``) so that
        all writable standard fields are preserved.

        Read-only and server-managed fields returned by ``get_person()``
        (timestamps, computed fields, related-record arrays) are
        automatically excluded from the payload to avoid HTTP 500 errors.

        Args:
            person_id: ChMeetings person ID.
            first_name: Person's first name (required by the API).
            last_name: Person's last name (required by the API).
            additional_fields: List of custom field update dicts.
                Every item **must** include ``field_type``.
            method: HTTP method to use — "PUT" (default).
            extra_person_data: Full person dict from ``get_person()``; used
                to populate all writable standard fields in the PUT body.

        Returns:
            True if the update succeeded, False otherwise.
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return False

        payload: Dict[str, Any] = {"first_name": first_name, "last_name": last_name}
        if extra_person_data:
            for k, v in extra_person_data.items():
                if k not in PERSON_PUT_EXCLUDE:
                    if k == "address" and isinstance(v, dict):
                        # The API rejects the 'country' key with HTTP 400:
                        # "Changing country is not allowed."
                        # Strip it so the rest of the address is preserved.
                        v = {ak: av for ak, av in v.items() if ak != "country"}
                    payload[k] = v
        payload["additional_fields"] = additional_fields

        url = urljoin(self.api_url, f"api/v1/people/{person_id}")
        http_call = self.session.patch if method.upper() == "PATCH" else self.session.put

        try:
            logger.debug(f"update_person [{method}] payload for {person_id}: {payload}")
            response = http_call(url, json=payload)
            if not response.ok:
                logger.error(
                    f"Failed to update person {person_id} [{method}]: "
                    f"HTTP {response.status_code} — {response.text}"
                )
                return False
            logger.info(f"Updated person {person_id} with {len(additional_fields)} field(s) via {method}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to update person {person_id} [{method}]: {str(e)}")
            return False

    def close(self):
        """Close connections and clean up resources."""
        self.session.close()

        if self.selenium_driver:
            self.selenium_driver.quit()
            logger.info("Selenium WebDriver closed")

    def __enter__(self):
        """Context manager entry point."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        self.close()
