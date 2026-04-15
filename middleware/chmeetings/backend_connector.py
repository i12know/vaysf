# chmeetings/backend-connector.py

import os
import requests
import time
from typing import Dict, List, Optional, Union, Any
from urllib.parse import urljoin
from loguru import logger

from config import Config

class ChMeetingsAPIError(Exception):
    """Exception raised for ChMeetings API errors."""
    pass

class ChMeetingsConnector:
    """Connector for ChMeetings API."""


    def __init__(self, use_api: bool = True):
        self.api_url = Config.CHM_API_URL
        self.api_key = Config.CHM_API_KEY
        self.use_api = use_api
        self.session = requests.Session()
        # Set headers with API key (new API uses lowercase "apikey")
        self.session.headers.update({
            "accept": "application/json",
            "apikey": self.api_key
        })
    
    def _extract_data(self, response_json: Any) -> Any:
        """Extract data from the new API response wrapper.

        Handles both new format: {"status_code": 200, "paging": {...}, "data": [...]}
        and old format: [...] or {"data": [...]}
        """
        if isinstance(response_json, list):
            return response_json
        if isinstance(response_json, dict):
            if "data" in response_json:
                return response_json["data"]
        return response_json

    def _get_paging(self, response_json: Any) -> Optional[Dict[str, Any]]:
        """Extract paging info from new API response, if present."""
        if isinstance(response_json, dict):
            return response_json.get("paging")
        return None

    def authenticate(self) -> bool:
        """
        Verify API key works by testing a simple request.
        Returns True if successful.
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return False

        try:
            response = self.session.get(
                urljoin(self.api_url, "api/v1/people"),
                params={"page": 1, "page_size": 1,
                        "include_additional_fields": False,
                        "include_family_members": False,
                        "include_organizations": False}
            )
            response.raise_for_status()
            data = response.json()
            # New API returns status_code in wrapper
            if isinstance(data, dict) and data.get("status_code") == 200:
                logger.info("API key verified successfully with ChMeetings API (new API format)")
            elif isinstance(data, dict) and "data" in data:
                logger.info("API key verified successfully with ChMeetings API")
            else:
                logger.info("API key verified (response format unrecognized, but HTTP 200 OK)")
            return True
        except requests.RequestException as e:
            logger.error(f"API key verification failed: {str(e)}")
            return False

    
    def get_people(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get people records from ChMeetings.

        Args:
            params: Query parameters (include_additional_fields, name, mobile, email, etc.)

        Returns:
            List of people records
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return []

        all_people = []
        page = 1
        params = params or {}
        # Respect caller's page_size if provided, default to 100
        page_size = params.pop("page_size", 100)
        # Default to including additional fields for backward compat with sync
        params.setdefault("include_additional_fields", True)
        params.setdefault("include_family_members", False)
        params.setdefault("include_organizations", False)

        while True:
            params.update({
                "page": page,
                "page_size": page_size,
                "include_additional_fields": True,
                "include_family_members": False,
            })
            try:
                response = self.session.get(
                    urljoin(self.api_url, "api/v1/people"),
                    params=params
                )
                response.raise_for_status()
                raw = response.json()
                people = self._extract_data(raw)
                if not isinstance(people, list):
                    people = []
                all_people.extend(people)

                # Use paging.total_count if available for proper pagination
                paging = self._get_paging(raw)
                if paging and "total_count" in paging:
                    total = paging["total_count"]
                    logger.info(f"Fetched page {page}: {len(people)} people (total: {total})")
                    if page * page_size >= total:
                        break
                else:
                    logger.info(f"Fetched page {page}: {len(people)} people")
                    if len(people) < page_size:
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
            raw = response.json()
            # New API may return person directly or wrapped in data
            data = self._extract_data(raw)
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
            raw = response.json()
            data = self._extract_data(raw)
            return data if isinstance(data, list) else []
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
                params={"group_ids": group_id}
            )
            response.raise_for_status()
            raw = response.json()
            data = self._extract_data(raw)
            return data if isinstance(data, list) else []
        except requests.RequestException as e:
            logger.error(f"Failed to get people in group {group_id}: {str(e)}")
            return []

    def get_fields(self) -> Optional[Dict[str, Any]]:
        """
        Get custom member field definitions from ChMeetings.
        Returns sections with fields and their options (for mapping field_id to field_name).
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return None
        try:
            response = self.session.get(
                urljoin(self.api_url, "api/v1/people/fields")
            )
            response.raise_for_status()
            raw = response.json()
            return self._extract_data(raw)
        except requests.RequestException as e:
            logger.error(f"Failed to get member fields: {str(e)}")
            return None

    def add_person_to_group(self, group_id: str, person_id: str) -> bool:
        """
        Add a person to a ChMeetings group.

        Returns True if successful.
        Note: 201 = newly added, 200 = already a member — both are success.
        Retries up to 3 times on 429 (rate limit) with 2 / 5 / 10 s back-off.

        Args:
            group_id: The group ID
            person_id: The person ID to add
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return False

        retry_waits = [2, 5, 10]  # seconds to wait after each 429 response

        for attempt in range(len(retry_waits) + 1):
            try:
                response = self.session.post(
                    urljoin(self.api_url, f"api/v1/groups/{group_id}/memberships"),
                    json={"person_id": person_id}
                )
                if response.status_code == 429:
                    if attempt < len(retry_waits):
                        wait = retry_waits[attempt]
                        logger.warning(
                            f"Rate limited adding person {person_id} to group {group_id}. "
                            f"Waiting {wait}s before retry {attempt + 1}/{len(retry_waits)}..."
                        )
                        time.sleep(wait)
                        continue
                    logger.error(
                        f"Rate limit persists after {len(retry_waits)} retries "
                        f"for person {person_id} → group {group_id}"
                    )
                    return False
                response.raise_for_status()
                logger.info(
                    f"Added person {person_id} to group {group_id} "
                    f"(status {response.status_code})"
                )
                return True
            except requests.RequestException as e:
                logger.error(f"Failed to add person {person_id} to group {group_id}: {e}")
                return False
        return False

    def remove_person_from_group(self, group_id: str, person_id: str) -> bool:
        """
        Remove a person from a ChMeetings group.

        Returns True if successful, False if not found or error.

        Args:
            group_id: The group ID
            person_id: The person ID to remove
        """
        if not self.use_api:
            logger.error("API usage is disabled")
            return False
        try:
            response = self.session.delete(
                urljoin(self.api_url, f"api/v1/groups/{group_id}/memberships/{person_id}")
            )
            response.raise_for_status()
            logger.info(f"Removed person {person_id} from group {group_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to remove person {person_id} from group {group_id}: {e}")
            return False
    
    def close(self):
        """Close connections and clean up resources."""
        self.session.close()

    def __enter__(self):
        """Context manager entry point."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        self.close()
