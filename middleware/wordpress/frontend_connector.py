# wordpress/frontend_connector.py
# version 1.0.5
import requests
import re
import json
from loguru import logger
from config import (Config, SPORT_TYPE, SPORT_CATEGORY, SPORT_FORMAT, GENDER, MEMBERSHIP_QUESTION,
                   RACQUET_SPORTS, VALIDATION_SEVERITY, VALIDATION_STATUS, FORMAT_MAPPINGS,
                   is_racquet_sport)
import datetime  # Add this if not already imported
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class WordPressAPIError(Exception):
    """Exception raised for WordPress API errors."""
    pass

class WordPressConnector:
    """Connector for WordPress REST API."""
    
    def __init__(self):
        """Initialize the WordPress connector."""
#        print("Initializing WordPressConnector")   ## These 2 lines detected all methods in this class
#        print("Methods in WordPressConnector:", [method for method in dir(self) if callable(getattr(self, method))])
        self.api_url = f"{Config.WP_URL}/wp-json/wp/v2"
        self.custom_api_url = f"{Config.WP_URL}/wp-json/vaysf/v1"
        self.total_participants = 0
        self.total_participant_pages = 0
    
        # Create a session to maintain cookies
        self.session = requests.Session()
        
        # Set up headers
        self.session.headers.update({
            "X-VAYSF-API-Key": Config.WP_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json",
            "Origin": Config.WP_URL,
            "Referer": Config.WP_URL
        })
        
        # Initialize the session
        self._initialize_session()
     
    def _initialize_session(self):
        """Initialize session with cookies by visiting the main site."""
        logger.info("Initializing session with WordPress...")
        try:
            # First visit the main site to get any cookies
            main_response = self.session.get(Config.WP_URL)
            
            # Check if we need to handle a bot protection cookie
            if "humans_" in main_response.text:
                logger.info("Detected bot protection. Extracting cookie...")
                cookie_match = re.search(r'document\.cookie\s*=\s*"([^"]+)"', main_response.text)
                if cookie_match:
                    cookie_script = cookie_match.group(1)
                    cookie_name, cookie_value = cookie_script.split('=')
                    self.session.cookies.set(cookie_name, cookie_value)
                    
                    # Visit the site again with the cookie
                    second_response = self.session.get(Config.WP_URL)
                    logger.info(f"Second site visit status code: {second_response.status_code}")
            
            logger.info(f"WordPress session initialized with cookies: {dict(self.session.cookies)}")
        except Exception as e:
            logger.error(f"Failed to initialize WordPress session: {e}")
        
    def get_churches(self) -> List[Dict[str, Any]]:
        """Get churches from WordPress."""
        try:
            response = self.session.get(f"{self.custom_api_url}/churches")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get churches: {str(e)}")
            return []
        
    def create_church(self, church_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a church record in WordPress."""
        try:
            response = self.session.post(
                f"{self.custom_api_url}/churches",
                json=church_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create church: {str(e)}")
            return None
    
    def update_church(self, church_id: int, church_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a church record in WordPress."""
        try:
            response = self.session.put(
                f"{self.custom_api_url}/churches/{church_id}",
                json=church_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to update church {church_id}: {str(e)}")
            return None

    def update_church_by_code(self, church_code: str, church_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a church record in WordPress using its code."""
        try:
            response = self.session.put(
                f"{self.custom_api_url}/churches/{church_code}",
                json=church_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to update church with code {church_code}: {str(e)}")
            return None
    
    def get_church_by_code(self, church_code: str) -> Optional[Dict[str, Any]]:
        """Get a specific church by its church_code from WordPress."""
        try:
            response = self.session.get(f"{self.custom_api_url}/churches/{church_code}")
            
            # For 404s, log at WARNING level
            if response.status_code == 404:
                logger.warning(f"Church with code {church_code} not found (404)")
                return None
                
            # For other errors, still use ERROR level
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get church with code {church_code}: {str(e)}")
            return None
        
##    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(requests.RequestException))
##    def get_participants(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
##        """Get participants from WordPress with pagination support."""
##        params = params or {}
##        chmeetings_id = params.pop('chmeetings_id', None)  # Extract chmeetings_id if present
##        
##        if 'page' not in params:
##            params['page'] = 1
##        if 'per_page' not in params:
##            params['per_page'] = 50  # Default to 50 per page
##
##        try:
##            response = self.session.get(f"{self.custom_api_url}/participants", params=params, timeout=(5, 30))
##            
##            # NEW CODE: Check for 404 and log as warning instead of error
##            if response.status_code == 404:
##                if chmeetings_id:
##                    logger.warning(f"No participant found with chmeetings_id: {chmeetings_id}")
##                else:
##                    logger.warning(f"No participants found for params: {params}")
##                return []
##                
##            response.raise_for_status()
            
            # Store pagination metadata
##            if 'X-WP-Total' in response.headers:
##                self.total_participants = int(response.headers['X-WP-Total'])
##            if 'X-WP-TotalPages' in response.headers:
##                self.total_participant_pages = int(response.headers['X-WP-TotalPages'])
##            
##            results = response.json()

            ### Debug logging for chmeetings_id filtering
            ##if chmeetings_id is not None:
            ##    logger.debug(f"Filtering participants by chmeetings_id: {chmeetings_id} (type: {type(chmeetings_id).__name__})")
            ##    logger.debug(f"Before filtering: Found {len(results)} participants")
            ##    
                # Debug each participant's chmeetings_id
            ##    for i, p in enumerate(results):
            ##        p_id = p.get('chmeetings_id')
            ##        logger.debug(f"Participant {i}: chmeetings_id = {p_id} (type: {type(p_id).__name__})")
                
                # Apply filter
            ##    results = [p for p in results if p.get('chmeetings_id') == chmeetings_id]
                
            ##    logger.debug(f"After filtering: Found {len(results)} participants matching chmeetings_id {chmeetings_id}")
            ### after adding the code above, we now know that James was not in the first page and that's why it was not found
            
            # Filter by chmeetings_id in Python if provided
##            if chmeetings_id is not None:
##                results = [p for p in results if p.get('chmeetings_id') == chmeetings_id]
                
##            return results
##        except requests.RequestException as e:
##            # CHANGED CODE: Only log as error for non-404 exceptions
##            logger.error(f"Failed to get participants: {str(e)}")
##            raise  # Let retry handle it

    ## Newer code:
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(requests.RequestException))
    def get_participants(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get participants from WordPress."""
        params = params or {}
        
        # Set default pagination if not provided
        if 'page' not in params:
            params['page'] = 1
        if 'per_page' not in params:
            params['per_page'] = 50
        
        try:
            response = self.session.get(f"{self.custom_api_url}/participants", params=params, timeout=(5, 30))
            
            if response.status_code == 404:
                logger.warning(f"No participants found for params: {params}")
                return []
                
            response.raise_for_status()
            
            # Store pagination metadata
            if 'X-WP-Total' in response.headers:
                self.total_participants = int(response.headers['X-WP-Total'])
            if 'X-WP-TotalPages' in response.headers:
                self.total_participant_pages = int(response.headers['X-WP-TotalPages'])
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Failed to get participants: {str(e)}")
            raise  # Let retry handle it

    def create_participant(self, participant_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a participant record in WordPress."""
        try:
            # Ensure updated_at is included if provided
            if "updated_at" in participant_data:
                logger.debug(f"Creating participant with updated_at: {participant_data['updated_at']}")
            response = self.session.post(
                f"{self.custom_api_url}/participants",
                json=participant_data
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Created participant response: {result}")
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to create participant: {str(e)}")
            return None
    
    def update_participant(self, participant_id: int, participant_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a participant record in WordPress."""
        try:
            # Ensure updated_at is included if provided
            if "updated_at" in participant_data:
                logger.debug(f"Updating participant {participant_id} with updated_at: {participant_data['updated_at']}")
            response = self.session.put(
                f"{self.custom_api_url}/participants/{participant_id}",
                json=participant_data
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Updated participant response: {result}")
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to update participant {participant_id}: {str(e)}")
            return None

    def get_rosters(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get rosters from WordPress."""
        try:
            response = self.session.get(
                f"{self.custom_api_url}/rosters",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get rosters: {str(e)}")
            return []
            
    def get_roster(self, roster_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific roster by ID from WordPress."""
        try:
            response = self.session.get(f"{self.custom_api_url}/rosters/{roster_id}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if response.status_code == 404:
                logger.warning(f"Roster {roster_id} not found")
            else:
                logger.error(f"Failed to get roster {roster_id}: {str(e)}")
            return None            
            
## Newer code:
    def create_roster(self, roster_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a roster record in WordPress."""
        try:
            response = self.session.post(
                f"{self.custom_api_url}/rosters",
                json=roster_data
            )
            # Debug output of raw response
            logger.debug(f"Raw response for roster creation: {response.text}")
            
            # If it's a success status code but empty response, consider it successful
            if response.status_code in (200, 201, 204) and not response.text:
                logger.info("Roster created successfully (empty response)")
                return roster_data  # Return the original data since the operation succeeded
                
            response.raise_for_status()
            return response.json() if response.text else roster_data
        except requests.RequestException as e:
            logger.error(f"Failed to create roster: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}, response: {response.text}")
            return None
## New Code:
#    def create_roster(self, roster_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
#        try:
#            response = self.session.post(
#                f"{self.custom_api_url}/rosters",
#                json=roster_data
#            )
#            logger.debug(f"Raw response for roster creation: {response.text}")
#            response.raise_for_status()
#            if not response.text.strip():
#                logger.error("Empty response from server")
#                return None
#            return response.json()
#        except requests.RequestException as e:
#            logger.error(f"Failed to create roster: {str(e)}")
#            return None
#        except json.JSONDecodeError as e:
#            logger.error(f"JSON decode error: {e}, response: {response.text}")
#            return None
## Old Code:        
#    def create_roster(self, roster_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a roster record in WordPress."""
#        try:
#            response = self.session.post(
#                f"{self.custom_api_url}/rosters",
#                json=roster_data
#            )
#            response.raise_for_status()
#            return response.json()
#        except requests.RequestException as e:
#            logger.error(f"Failed to create roster: {str(e)}")
#            return None

    def update_roster(self, roster_id: int, roster_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a roster record in WordPress."""
        try:
            # Ensure updated_at is included if provided (though roster_data might not always have it here)
            # The actual updated_at for the roster record itself will be handled by WordPress or the API endpoint.
            # This log is more for if roster_data itself carries a timestamp.
            if "updated_at" in roster_data:
                logger.debug(f"Updating roster {roster_id} with data that includes updated_at: {roster_data['updated_at']}")
            
            response = self.session.put(
                f"{self.custom_api_url}/rosters/{roster_id}",
                json=roster_data  # Send only the fields to be updated
            )
            response.raise_for_status()
            # Check if response is empty, common for successful PUT/PATCH with no content to return
            if response.status_code == 204 or not response.content:
                logger.info(f"Roster {roster_id} updated successfully (empty/204 response). Returning original payload as confirmation.")
                # Return the payload that was sent, or a success marker,
                # as the server might not return the full updated object.
                # Or, you could re-fetch the roster here if needed. For now, return what was intended.
                # To ensure the calling function gets a "truthy" value for success:
                return {"success": True, "roster_id": roster_id, "updated_fields": roster_data}

            result = response.json()
            logger.debug(f"Updated roster {roster_id} response: {result}")
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to update roster {roster_id}: {str(e)}. Data: {roster_data}")
            # Log the response content if it's an HTTP error
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Error response content: {e.response.text}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error updating roster {roster_id}: {e}. Response text: {response.text}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(requests.RequestException))
    def delete_roster(self, roster_id: int) -> bool:
        """Delete a roster entry from sf_rosters by its ID and resolve related validation issues.
        
        Args:
            roster_id: The roster ID to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # First get the roster to know its sport_type and sport_format
## BUG            roster = self.get_rosters({"roster_id": roster_id})
            roster = self.get_roster(roster_id)     ## DEBUG    
            if not roster:                          ## DEBUG     or len(roster) == 0:
                logger.warning(f"Roster {roster_id} not found, cannot delete")
                return False
            
## BUG            roster_data = roster[0]
            
            # Delete the roster
            response = self.session.delete(
                f"{self.custom_api_url}/rosters/{roster_id}"
            )
            response.raise_for_status()
            logger.info(f"Successfully deleted roster with ID {roster_id}")
            
            # Also resolve related validation issues ## DEBUG using the correct participant ID
            if roster.get("participant_id") and roster.get("sport_type"):       ## DEBUG roster_data.get was used instead
                self.resolve_validation_issues_for_sport(
                    participant_id=roster["participant_id"],                    ## DEBUG roster_data.get was used instead
                    sport_type=roster["sport_type"],                            ## DEBUG roster_data.get was used instead
                    sport_format=roster.get("sport_format")                     ## DEBUG roster_data.get was used instead
                )
            
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to delete roster {roster_id}: {str(e)}")
            return False
    
    def create_approval(self, approval_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create an approval record in WordPress."""
        try:
            response = self.session.post(
                f"{self.custom_api_url}/approvals",
                json=approval_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create approval: {str(e)}")
            return None
    
    def get_approvals(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get approvals from WordPress."""
        try:
            response = self.session.get(
                f"{self.custom_api_url}/approvals",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get approvals: {str(e)}")
            return []
    
    def update_approval(self, approval_id: int, approval_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an approval record in WordPress."""
        try:
            response = self.session.put(
                f"{self.custom_api_url}/approvals/{approval_id}",
                json=approval_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to update approval {approval_id}: {str(e)}")
            return None
    
    def create_validation_issue(self, issue_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a validation issue record in WordPress."""
        try:
            response = self.session.post(
                f"{self.custom_api_url}/validation-issues",
                json=issue_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create validation issue: {str(e)}")
            return None
    
    def get_validation_issues(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get validation issues from WordPress."""
        try:
            response = self.session.get(
                f"{self.custom_api_url}/validation-issues",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get validation issues: {str(e)}")
            return []

    def update_validation_issue(self, issue_id: int, issue_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a validation issue record in WordPress."""
        try:
            response = self.session.put(
                f"{self.custom_api_url}/validation-issues/{issue_id}",
                json=issue_data
            )
            logger.debug(f"Raw response for updating issue {issue_id}: {response.text}")
            response.raise_for_status()
            if not response.text.strip():
                logger.error(f"Empty response received for updating issue {issue_id}")
                return None
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to update validation issue {issue_id}: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for issue {issue_id}: {e}, response: {response.text}")
            return None
        
    def resolve_validation_issues_for_sport(self, participant_id: int, sport_type: str, sport_format: str = None) -> bool:
        """Mark validation issues related to a specific sport and participant as resolved.
        
        Args:
            participant_id: The WordPress participant ID
            sport_type: The sport type
            sport_format: Optional sport format
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get matching open validation issues
            params = {
                "participant_id": participant_id,
                "sport_type": sport_type,
                "status": VALIDATION_STATUS["OPEN"]
            }
            if sport_format:
                params["sport_format"] = sport_format
                
            issues = self.get_validation_issues(params)
            logger.info(f"Found {len(issues)} open validation issues to resolve for participant {participant_id}, sport {sport_type}")
            
            resolved_count = 0
            for issue in issues:
                result = self.update_validation_issue(
                    issue["issue_id"],
                    {
                        "status": VALIDATION_STATUS["RESOLVED"], 
                        "resolved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                )
                if result:
                    resolved_count += 1
                
            logger.info(f"Successfully resolved {resolved_count}/{len(issues)} validation issues")
            return resolved_count > 0 or len(issues) == 0
        except Exception as e:
            logger.error(f"Failed to resolve validation issues: {e}")
            return False

    def send_email(self, to: str, subject: str, message: str, from_email: Optional[str] = None, 
                  cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> Dict[str, Any]:
        """Send an email using the WordPress REST API."""
        try:
            data = {
                'to': to,
                'subject': subject,
                'message': message
            }
            
            if from_email:
                data['from'] = from_email
            if cc:
                data['cc'] = cc
            if bcc:
                data['bcc'] = bcc
            
            response = self.session.post(
                f"{self.custom_api_url}/send-email",
                json=data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to send email: {str(e)}")
            return {"success": False, "message": str(e)}

    def update_approval_by_participant(self, participant_id: int, approval_data: Dict[str, Any]) -> bool:
        """Update approval record by participant ID."""
        try:
            # Get the approval record for this participant using existing get_approvals method
            approvals = self.get_approvals(params={"participant_id": participant_id})
            if not approvals or len(approvals) == 0:
                logger.error(f"No approval record found for participant {participant_id}")
                return False
            
            # Update the first (should be only) approval record using existing update_approval method
            approval_id = approvals[0]["approval_id"]
            result = self.update_approval(approval_id, approval_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error updating approval for participant {participant_id}: {e}")
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
# End of wordpress/frontend_connector.py