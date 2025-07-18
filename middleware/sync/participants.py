# Begin of sync/participants.py
# Version 1.0.4: replaced _map_chmeetings_participants, added _parse_format() before _sync_roster, updated _sync_rosters to use primary_format when available
# Version 1.0.5: Fixed imports, removed redundant logger setup, update log_validation_issues only with newer chmeetings timestamp
from typing import Dict, List, Tuple, Any, Optional
from loguru import logger  # Import from config.py
from chmeetings.backend_connector import ChMeetingsConnector
from wordpress.frontend_connector import WordPressConnector
from config import (Config, APPROVAL_STATUS, CHECK_BOXES, MEMBERSHIP_QUESTION,
                   SPORT_TYPE, SPORT_CATEGORY, SPORT_FORMAT, GENDER, RULE_LEVEL, FORMAT_MAPPINGS,
                   SPORT_UNSELECTED, RACQUET_SPORTS, VALIDATION_SEVERITY, is_racquet_sport)                   
import datetime
import pytz

# Add imports for validation
from validation.individual_validator import IndividualValidator
from validation.models import Participant
from pydantic import ValidationError

# Helper functions
def parse_format(format_value: str) -> tuple[str, str]:
    """Parse sport format and gender from a format string.

    Args:
        format_value (str): The format string (e.g., "Men Single").

    Returns:
        tuple[str, str]: (sport_format, sport_gender)
    """
    if not format_value:
        return SPORT_FORMAT["TEAM"], GENDER["MIXED"]
    format_value = format_value.strip()
    return FORMAT_MAPPINGS.get(format_value, (SPORT_FORMAT["TEAM"], GENDER["MIXED"]))
    
class ParticipantSyncer:
    """Handles synchronization of participant data from ChMeetings to WordPress."""

    def __init__(self, chm_connector: ChMeetingsConnector, wordpress_connector: WordPressConnector, stats: dict, churches_cache: dict):
        self.chm_connector = chm_connector
        self.wordpress_connector = wordpress_connector
        self.stats = stats  # Reference to SyncManager's stats dictionary
        self.churches_cache = churches_cache  # Cache of church data for validation
        self.participants_cache = {}  # Local cache for participant IDs
        # Initialize the IndividualValidator with the event collection
        self.validator = IndividualValidator(collection="SUMMER_2025")

# In sync/participants.py, inside the ParticipantSyncer class

    def sync_participants(self, chm_id_to_sync: Optional[str] = None) -> bool:
        """
        Synchronize participant data from ChMeetings to WordPress.
        Can sync a single participant if chm_id_to_sync is provided,
        otherwise performs a full sync from 'Team...' groups.
        """
        # Define the target ChMeetings ID for detailed logging (used by _sync_single_participant)
        # This could also be an instance variable or passed differently if needed.
        TARGET_CHM_ID_FOR_DEBUG = '3633885' 

        if chm_id_to_sync:
            logger.info(f"Starting synchronization for single participant: ChM ID {chm_id_to_sync}...")
        else:
            logger.info(f"Starting full participant synchronization from groups with prefix '{Config.TEAM_PREFIX}'...")

        if not self.chm_connector or not self.wordpress_connector:
            logger.warning("Connectors not available. Participant sync cannot proceed.")
            return False

        # Ensure churches_cache is populated, as it's used by _sync_validation_issues
        # (which is called by _sync_single_participant)
        if not self.churches_cache:
            wp_churches = self.wordpress_connector.get_churches()
            if wp_churches:
                self.churches_cache.update({c["church_code"]: c for c in wp_churches})
            else:
                logger.warning("Failed to load churches into cache. Some operations like validation issue logging might be affected.")
                # Depending on strictness, you might want to return False here
                # if church_cache is essential for all paths.

        if chm_id_to_sync:
            # Syncing a single participant
            logger.info(f"Attempting to sync participant with ChMeetings ID: {chm_id_to_sync}.")
            # The _sync_single_participant method handles its own detailed logging using TARGET_CHM_ID_FOR_DEBUG
            success = self._sync_single_participant(chm_id_to_sync, TARGET_CHM_ID_FOR_DEBUG)
            if success:
                logger.info(f"Successfully processed participant with ChM ID: {chm_id_to_sync}.")
            else:
                logger.error(f"Failed to process participant with ChM ID: {chm_id_to_sync}. Check logs for details.")
            # Final stats log will be outside this specific branch
            logger.info(f"Participant sync completed. Stats: Participants {self.stats['participants']}, Rosters: {self.stats['rosters']}, Validation Issues: {self.stats['validation_issues']}")
            return success
        else:
            # Full synchronization from groups
            groups = self.chm_connector.get_groups()
            if not groups: # Check if groups itself is None or empty, not just team_groups
                logger.warning("No groups returned from ChMeetings.")
                # This could be a False return if groups are expected. Original code would filter an empty list.
                # Let's consider it an issue that prevents proceeding.
                return False

            team_groups = [g for g in groups if g["name"].startswith(Config.TEAM_PREFIX)]
            
            if not team_groups:
                logger.warning(f"No groups found with prefix '{Config.TEAM_PREFIX}'. Full participant sync will not process any participants from groups.")
                # Original code returned False here. Let's maintain that behavior for consistency.
                logger.info(f"Participant sync completed (no team groups found). Stats: Participants {self.stats['participants']}, Rosters: {self.stats['rosters']}, Validation Issues: {self.stats['validation_issues']}")
                return False

            logger.info(f"Found {len(team_groups)} '{Config.TEAM_PREFIX}' groups for full sync.")
            
            all_participants_processed_successfully = True # Assume success unless a participant fails

            for group in team_groups:
                participants_in_group = self.chm_connector.get_group_people(group["id"])
                if not participants_in_group:
                    logger.info(f"No participants in group '{group['name']}' (ID: {group['id']}). Skipping.")
                    continue

                logger.info(f"Processing {len(participants_in_group)} participants in group '{group['name']}' (ID: {group['id']}).")
                for person_summary in participants_in_group:
                    # person_id from the group listing is the ChMeetings ID
                    current_chm_id = str(person_summary.get("person_id")) 
                    if not current_chm_id or current_chm_id == "None": # Check for valid ID
                        logger.warning(f"Skipping a person in group '{group['name']}' due to missing or invalid person_id: {person_summary}")
                        self.stats["participants"]["errors"] += 1
                        all_participants_processed_successfully = False # Mark overall as not entirely successful
                        continue
                    
                    # Call the helper method for each person_chm_id
                    # TARGET_CHM_ID_FOR_DEBUG is passed for detailed logging if current_chm_id matches
                    if not self._sync_single_participant(current_chm_id, TARGET_CHM_ID_FOR_DEBUG):
                        # _sync_single_participant already logs its own errors and updates stats
                        logger.warning(f"Failed to sync participant ChM ID {current_chm_id} from group '{group['name']}'.")
                        all_participants_processed_successfully = False # Mark overall as not entirely successful
                        # Continue processing other participants

            if all_participants_processed_successfully:
                logger.info("Full participant sync from groups completed. All encountered participants processed (either successfully synced or validly skipped).")
            else:
                logger.warning("Full participant sync from groups completed, but one or more participants encountered errors or were invalid. Check logs and stats.")

            logger.info(f"Participant sync completed. Stats: Participants {self.stats['participants']}, Rosters: {self.stats['rosters']}, Validation Issues: {self.stats['validation_issues']}")
            # For full sync, the method is considered "successful" if it ran through.
            # Individual errors are in stats. The original code implies a True return if it reaches the end.
            # However, all_participants_processed_successfully gives a more nuanced status.
            # Let's return True if the process completed, consistent with original high-level behavior.
            # If you want it to return False if ANY participant fails, change the return to `all_participants_processed_successfully`.
            return True
# START --- New helper method for ParticipantSyncer in participants.py ---
    def _sync_single_participant(self, chm_id: str, target_chm_id_for_debug: Optional[str] = None) -> bool:
        """
        Synchronizes a single participant from ChMeetings to WordPress.

        Args:
            chm_id (str): The ChMeetings ID of the participant to sync.
            target_chm_id_for_debug (Optional[str]): A specific ChMeetings ID for detailed debugging.

        Returns:
            bool: True if the participant was successfully processed (created or updated), False otherwise.
        """
        if chm_id == target_chm_id_for_debug:
            logger.debug(f"--------------------------------------------------------------------------")
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] START PROCESSING TARGET RECORD")

        person_data_from_chm = self.chm_connector.get_person(chm_id)
        if not person_data_from_chm:
            logger.warning(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Could not fetch details for person {chm_id}.")
            self.stats["participants"]["errors"] += 1
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (FETCH FAILED)")
            return False

        # The get_person response might be directly the data or nested under "data"
        full_person_data = person_data_from_chm if isinstance(person_data_from_chm, dict) and "data" not in person_data_from_chm else person_data_from_chm.get("data", {})
        if not full_person_data:
            logger.warning(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Skipping person {chm_id}: No data returned from get_person.")
            self.stats["participants"]["errors"] += 1
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (NO DATA)")
            return False

        # Ensure 'id' exists and matches chm_id for consistency, as mapping relies on it.
        # The 'id' from full_person_data is the definitive ChMeetings ID after a get_person call.
        if str(full_person_data.get("id")) != chm_id:
            logger.warning(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Mismatch between requested chm_id ({chm_id}) and fetched person's id ({full_person_data.get('id')}). Using fetched ID.")
            # Potentially update chm_id to the one fetched if this is a desired behavior,
            # but for now, it signals a potential issue. We'll proceed with the original chm_id for logging consistency
            # but the mapping will use full_person_data.get("id").
            # This scenario should be rare if the initial chm_id is correct.

        if chm_id == target_chm_id_for_debug:
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Raw person_data from ChM: {person_data_from_chm}")
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Full person data after initial parse: {full_person_data}")

        # _map_chmeetings_participants expects a list of person data
        mapped_list = self._map_chmeetings_participants([full_person_data])
        if not mapped_list:
            logger.error(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Failed to map data for ChMeetings ID {chm_id}.")
            self.stats["participants"]["errors"] += 1
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (MAPPING FAILED)")
            return False
        mapped = mapped_list[0]

        # The chm_id in 'mapped' should be the one from full_person_data.get('id')
        # We use the input `chm_id` for consistent logging if target_chm_id_for_debug is set.
        # mapped_chm_id = mapped["chmeetings_id"] # This is derived from the actual data

        if chm_id == target_chm_id_for_debug:
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Initial mapped data: {mapped}")

        roles = mapped.get("roles", "")
        is_athlete_or_participant = any(role.strip() in ["Athlete", "Participant", "Athlete/Participant"] for role in roles.split(","))
        if not is_athlete_or_participant:
            logger.info(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Skipping {mapped.get('first_name', 'N/A')} {mapped.get('last_name', 'N/A')} (ChM ID: {chm_id}): Roles '{roles}' do not qualify.")
            # This is not an error, but a valid skip.
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (ROLE SKIP)")
            return True # Successfully processed by skipping

        required_fields = ["first_name", "last_name", "church_code"]
        missing_fields = [field for field in required_fields if not mapped.get(field)]
        if missing_fields:
            logger.error(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Skipping ChM ID {chm_id}: Missing required fields {missing_fields} in mapped data.")
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Mapped data causing missing fields: {mapped}")
            self.stats["participants"]["errors"] += 1
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (MISSING FIELDS)")
            return False

        chm_updated_on_str = full_person_data.get("updated_on", "1970-01-01T00:00:00+00:00").replace("Z", "+00:00")
        chm_updated_on = datetime.datetime.fromisoformat(chm_updated_on_str)
        chm_updated_on_utc = chm_updated_on.astimezone(pytz.UTC)
        mapped["updated_at"] = chm_updated_on_utc.strftime("%Y-%m-%d %H:%M:%S")
        
        if chm_id == target_chm_id_for_debug:
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] ChMeetings updated_on (UTC): {chm_updated_on_utc}, Mapped updated_at: {mapped['updated_at']}")

        current_wp_status = mapped.get("approval_status", APPROVAL_STATUS["PENDING"]) # Default from mapping
        final_status_determined = False
        wp_participant_id = None 

        # Use mapped["chmeetings_id"] as it's directly from the mapped data which is from full_person_data
        participant_in_wp_list = self.wordpress_connector.get_participants({"chmeetings_id": mapped["chmeetings_id"]})
        participant_in_wp = (participant_in_wp_list[0] if participant_in_wp_list else None)

        if chm_id == target_chm_id_for_debug:
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Participant in WP (direct fetch by chmeetings_id '{mapped['chmeetings_id']}'): {participant_in_wp}")
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Initial current_wp_status (from mapped before P1/P2): {current_wp_status}")

        if participant_in_wp:
            wp_participant_id = participant_in_wp["participant_id"]
            status_in_sf_participants = participant_in_wp.get("approval_status")
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] P1 - WP Participant ID: {wp_participant_id}, Status from sf_participants: {status_in_sf_participants}")

            if status_in_sf_participants in [APPROVAL_STATUS["APPROVED"], APPROVAL_STATUS["DENIED"]]:
                current_wp_status = status_in_sf_participants
                final_status_determined = True
                if chm_id == target_chm_id_for_debug:
                    logger.info(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}][TARGET] Participant {wp_participant_id}: Status preserved as '{current_wp_status}' from existing sf_participants record.")
            else:
                existing_approvals = self.wordpress_connector.get_approvals(
                    params={"participant_id": wp_participant_id}
                )
                if chm_id == target_chm_id_for_debug:
                    logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] P2 - Fetched sf_approvals records: {existing_approvals}")

                if existing_approvals:
                    approval_record = existing_approvals[0] 
                    status_from_sf_approvals = approval_record.get("approval_status")
                    if chm_id == target_chm_id_for_debug:
                        logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] P2 - Approval record found: {approval_record}")
                        logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] P2 - Status from sf_approvals: {status_from_sf_approvals}")

                    if status_from_sf_approvals in [APPROVAL_STATUS["APPROVED"], APPROVAL_STATUS["DENIED"]]:
                        current_wp_status = status_from_sf_approvals
                        final_status_determined = True
                        if chm_id == target_chm_id_for_debug:
                            logger.info(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}][TARGET] Participant {wp_participant_id}: Status set to '{current_wp_status}' from sf_approvals table.")
        
        if chm_id == target_chm_id_for_debug:
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] After P1/P2 - current_wp_status: {current_wp_status}, final_status_determined: {final_status_determined}")
        
        mapped["approval_status"] = current_wp_status
        validation_issues_list = [] # Renamed to avoid conflict with 'issues' from validate_participant
        
        if not final_status_determined:
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Entering validation/checklist logic. mapped['approval_status'] before: {mapped.get('approval_status')}")
            
            is_valid, validation_issues_list = self.validate_participant(mapped)
            
            if is_valid:
                completion_checklist = mapped.get("completion_checklist", "")
                required_items = [
                    CHECK_BOXES["1-IDENTITY"], CHECK_BOXES["2-CONSENT"],
                    CHECK_BOXES["3-ACCOUNT"], CHECK_BOXES["4-PHOTO_ID"]
                ]
                all_items_checked = all(item.strip() in completion_checklist for item in required_items)
                
                if all_items_checked:
                    mapped["approval_status"] = APPROVAL_STATUS["PENDING_APPROVAL"]
                else:
                    mapped["approval_status"] = APPROVAL_STATUS["VALIDATED"]
            else:
                mapped["approval_status"] = APPROVAL_STATUS["PENDING"]
            
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] After validation/checklist logic - mapped['approval_status']: {mapped.get('approval_status')}, Issues: {validation_issues_list}")
        
        if chm_id == target_chm_id_for_debug:
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Final approval_status for {mapped['chmeetings_id']} before WP update/create: {mapped.get('approval_status')}")

        try:
            if chm_id == target_chm_id_for_debug:
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Payload for WordPress (participant_in_wp: {bool(participant_in_wp)}) MAPPED DATA: {mapped}")
            
            participant_id_for_roster_sync = None # Use a distinct name

            if participant_in_wp:
                # wp_participant_id is already defined if participant_in_wp is True
                updated_participant = self.wordpress_connector.update_participant(wp_participant_id, mapped)
                if chm_id == target_chm_id_for_debug:
                    logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Update result: {updated_participant}")
                if updated_participant:
                    self.stats["participants"]["updated"] += 1
                    self.participants_cache[mapped["chmeetings_id"]] = updated_participant
                    participant_id_for_roster_sync = updated_participant["participant_id"]
                else:
                    logger.error(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Failed to update participant {mapped['chmeetings_id']}: No result returned")
                    self.stats["participants"]["errors"] += 1
                    if chm_id == target_chm_id_for_debug:
                        logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (WP UPDATE FAILED)")
                    return False
            else:
                created_participant = self.wordpress_connector.create_participant(mapped)
                if chm_id == target_chm_id_for_debug:
                    logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Create result: {created_participant}")
                if created_participant:
                    self.stats["participants"]["created"] += 1
                    self.participants_cache[mapped["chmeetings_id"]] = created_participant
                    participant_id_for_roster_sync = created_participant["participant_id"]
                else:
                    logger.error(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Failed to create participant {mapped['chmeetings_id']}: No result returned")
                    self.stats["participants"]["errors"] += 1
                    if chm_id == target_chm_id_for_debug:
                        logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (WP CREATE FAILED)")
                    return False

            if participant_id_for_roster_sync:
                if chm_id == target_chm_id_for_debug:
                    logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Syncing rosters for WP participant_id {participant_id_for_roster_sync}")
                self._sync_rosters(str(participant_id_for_roster_sync), mapped) # Ensure participant_id is string if expected by _sync_rosters
                
                chm_updated_on_utc_for_issues = mapped["updated_at"] # Already a string
                if chm_id == target_chm_id_for_debug:
                     logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Syncing validation issues for WP participant_id {participant_id_for_roster_sync}. Issues to sync: {validation_issues_list}")
                self._sync_validation_issues(str(participant_id_for_roster_sync), mapped["church_code"], validation_issues_list, chm_updated_on_utc_for_issues)
            else:
                # This case should ideally be caught by create/update failures above
                logger.error(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] participant_id_for_roster_sync was not defined. Skipping roster and validation sync.")                   
                if chm_id == target_chm_id_for_debug:
                    logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (NO WP PID FOR ROSTER/ISSUES)")
                return False # Indicate failure as subsequent steps were skipped

        except Exception as e:
            logger.exception(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Error syncing participant {mapped['chmeetings_id']}: {e}")
            self.stats["participants"]["errors"] += 1
            if chm_id == target_chm_id_for_debug:
                logger.error(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] Exception occurred during WP update/create or subsequent sync.")
                logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING (EXCEPTION)")
            return False
        
        if chm_id == target_chm_id_for_debug:
            logger.debug(f"[_SYNC_SINGLE_PARTICIPANT - {chm_id}] END PROCESSING TARGET RECORD (SUCCESS)")
            logger.debug(f"--------------------------------------------------------------------------")
        
        return True # Successfully processed
# END --- New helper method for ParticipantSyncer in participants.py ---        
## New Code:
    def _map_chmeetings_participants(self, people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map ChMeetings person data to participant format."""
        TARGET_CHM_ID_FOR_DEBUG = '3633885' # Chmeetings_id as Debugging Target for Logging
        mapped_list = []
        for person_loop_item in people: # Renamed person to avoid conflict with outer scope if any
            p = person_loop_item.get("data", person_loop_item) if "data" in person_loop_item else person_loop_item
            
            # Get chm_id for conditional logging, p.get('id') should be the chmeetings_id here
            current_person_chm_id_for_map = str(p.get("id"))

            additional_fields = {f["field_name"]: f["value"] for f in p.get("additional_fields", [])}
            
            primary_sport = additional_fields.get("Primary Sport", "")
            if " - " in primary_sport:
                primary_format_val = "" 
            else:
                primary_format_val = additional_fields.get("Primary Racquet Sport Format", "")
            
            secondary_sport = additional_fields.get("Secondary Sport", "")
            if " - " in secondary_sport:
                secondary_format_val = ""
            else:
                secondary_format_val = additional_fields.get("Secondary Racquet Sport Format", "")

            photo_url = p.get("photo", "")
            if not photo_url and isinstance(p.get("additional_fields"), list):
                photo_fields = [f for f in p.get("additional_fields", []) 
                             if f.get("field_name", "").lower() in ["photo", "profile_photo", "photo_url"]]
                if photo_fields and photo_fields[0].get("value"):
                    photo_url = photo_fields[0].get("value")

            # Let's get this string first.
            completion_checklist_str = additional_fields.get("Completion Check List", "") 

            # --- START NEW LOGIC TO SET consent_status ---
            # (This block will be inserted BEFORE the participant_mapped_data dictionary)
            # Ensure CHECK_BOXES is accessible (it is imported from config at the top of the file)
            has_consent_checked = CHECK_BOXES["2-CONSENT"] in completion_checklist_str
            # --- END NEW LOGIC TO SET consent_status ---
            
            if current_person_chm_id_for_map == TARGET_CHM_ID_FOR_DEBUG: # Conditional log for photo
                logger.debug(f"[SYNC_PARTICIPANT_MAP - {current_person_chm_id_for_map}] Photo URL: {photo_url}")
                logger.debug(f"[SYNC_PARTICIPANT_MAP - {current_person_chm_id_for_map}] Additional Fields from ChM: {additional_fields}")
                # Add the new debug logs here as well:
                logger.debug(f"[SYNC_PARTICIPANT_MAP - {current_person_chm_id_for_map}] Raw completion_checklist_str: '{completion_checklist_str}'")
                logger.debug(f"[SYNC_PARTICIPANT_MAP - {current_person_chm_id_for_map}] CHECK_BOXES['2-CONSENT'] value is: '{CHECK_BOXES['2-CONSENT']}'")
                logger.debug(f"[SYNC_PARTICIPANT_MAP - {current_person_chm_id_for_map}] Derived has_consent_checked: {has_consent_checked}")

            # Original start of participant_mapped_data dictionary
            # ChMeetings field name, MUST match the label in ChMeetings custom fields exactly
            participant_mapped_data = {
                "chmeetings_id": current_person_chm_id_for_map, # Use the chm_id derived for logging
                "church_code": additional_fields.get("Church Team", "").strip().upper(),
                "first_name": p.get("first_name", ""),
                "last_name": p.get("last_name", ""),
                "email": p.get("email", "").strip(),
                "phone": p.get("mobile", ""),
                "gender": p.get("gender", ""),
                "birthdate": p.get("birth_date", ""),
                "photo_url": photo_url,
                "is_church_member": additional_fields.get(MEMBERSHIP_QUESTION, "No") == "Yes",
                "primary_sport": primary_sport,
                "primary_format": primary_format_val,
                "primary_partner": additional_fields.get("Primary Racquet Sport Partner (if applied)", ""),
                "secondary_sport": secondary_sport,
                "secondary_format": secondary_format_val,
                "secondary_partner": additional_fields.get("Secondary Racquet Sport Partner (if applied)", ""),
                "other_events": additional_fields.get("Other Events", ""),
                "approval_status": "pending", 
                "completion_checklist": additional_fields.get("Completion Check List", ""),
                "parent_info": additional_fields.get("Parent Info", ""),
                "roles": additional_fields.get("My role is", ""),
                "consent_status": has_consent_checked # New field added here
            }
            mapped_list.append(participant_mapped_data)
        return mapped_list

### WORKING CODE for validate_participant   
    def validate_participant(self, participant: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
        is_valid, issues = self.validator.validate(participant)
        return is_valid, issues

### DEBUG CODE BUT WON'T WORK
#    def validate_participant(self, participant: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
#        print(f"Type of participant: {type(participant)}")
#        print(f"Type of Participant: {type(Participant)}")
#        print(f"Is Participant a class? {isinstance(Participant, type)}")
#        print(f"Participant: {Participant}")
#        try:
#            participant_obj = Participant(**participant)  ### This is the line that cause the assertion error.
#        except Exception as e:
#            logger.error(f"Caught exception: {type(e).__name__}: {str(e)}")
#            raise  # Temporarily re-raise to get the stack trace
#        is_valid, issues = self.validator.validate(participant_obj)
#        return is_valid, issues      

### ORIGINAL CODE
#    def validate_participant(self, participant: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
#        """Validate a participant using the IndividualValidator."""
#        try:
#            # Convert the participant dictionary to a Participant object
#            participant_obj = Participant(**participant)
#        except ValidationError as e:
#            # Handle cases where required fields are missing or invalid
#            issues = [{"type": "invalid_data", "description": str(e)}]
#            return False, issues
#
#        # Validate using the IndividualValidator
#        is_valid, issues = self.validator.validate(participant_obj)
#        return is_valid, issues
    def _sync_rosters(self, participant_id: str, participant: Dict[str, Any]):
        """Sync participant sport preferences to sf_rosters."""
        sport_fields = [
            ("primary_sport", "primary_format", "primary_partner"),
            ("secondary_sport", "secondary_format", "secondary_partner"),
            ("other_events", None, None),
        ]
        current_sports = set()

        ## Add debug info next 4 lines - what participant are we syncing?
        logger.debug(f"=== ROSTER SYNC START for participant_id={participant_id} ===")
        logger.debug(f"Participant primary_sport: '{participant.get('primary_sport', '')}', format: '{participant.get('primary_format', '')}'")
        logger.debug(f"Participant secondary_sport: '{participant.get('secondary_sport', '')}', format: '{participant.get('secondary_format', '')}'")
        logger.debug(f"Participant other_events: '{participant.get('other_events', '')}'")
    
        for sport_field, format_field, partner_field in sport_fields:
            sport_value = participant.get(sport_field, "")
            if not sport_value or sport_value in [SPORT_UNSELECTED, "", "None"]:
                continue

            if sport_field == "other_events":
                # Handle multiple events
                other_sports = [s.strip() for s in sport_value.split(",")]
                for other_sport in other_sports:
                    roster_data = {
                        "church_code": participant["church_code"],
                        "participant_id": int(participant_id),
                        "sport_type": other_sport,
                        "sport_gender": GENDER["MIXED"],
                        "sport_format": SPORT_FORMAT["TEAM"],
                        "team_order": None,
                        "partner_name": None,
                    }
                    ## Debug for other_events roster in next 2 lines
                    logger.debug(f"Adding to current_sports: ('{other_sport}', 'Team', 'Mixed', None)")
                    current_sports.add((roster_data["sport_type"], roster_data["sport_format"], roster_data["sport_gender"], roster_data["team_order"]))
                    self._create_or_update_roster(roster_data)
            else:
                sport_type = sport_value
                format_value = participant.get(format_field) if format_field else None

                if is_racquet_sport(sport_type) and format_value:
                    sport_format, sport_gender = parse_format(format_value)
                else:
                    # Team sport or no format specified
                    sport_parts = sport_value.split(" - ")
                    sport_type = sport_parts[0]

                    # BUGGY: Smart Gender Mapping for Volleyball is NOT working correctly yet!!! 
                    if sport_type.upper() == "VOLLEYBALL":
                        participant_gender = participant.get("gender", "").lower()
                        if participant_gender == "male":
                            sport_gender = GENDER["MEN"]
                            sport_type = "Volleyball"  # Normalize the sport name
                        elif participant_gender == "female":
                            sport_gender = GENDER["WOMEN"] 
                            sport_type = "Volleyball"  # Normalize the sport name
                        else:
                            sport_gender = GENDER["MIXED"]  # Fallback
                        sport_format = SPORT_FORMAT["TEAM"]
                    elif len(sport_parts) > 1:
                        param = sport_parts[1]
                        if GENDER["MEN"] in param:
                            sport_gender = GENDER["MEN"]
                        elif GENDER["WOMEN"] in param:
                            sport_gender = GENDER["WOMEN"]
                        elif GENDER["MIXED"] in param:
                            sport_gender = GENDER["MIXED"]
                        else:
                            sport_gender = GENDER["MIXED"]
                        sport_format = SPORT_FORMAT["TEAM"] if SPORT_FORMAT["TEAM"] in param else SPORT_FORMAT["SINGLES"]
                    else:
                        sport_format, sport_gender = parse_format(format_value)

                roster_data = {
                    "church_code": participant["church_code"],
                    "participant_id": int(participant_id),
                    "sport_type": sport_type,
                    "sport_gender": sport_gender,
                    "sport_format": sport_format,
                    "team_order": None,
                    "partner_name": participant.get(partner_field) if partner_field else None,
                }

                required = ["church_code", "participant_id", "sport_type", "sport_gender", "sport_format"]
                if any(not roster_data.get(field) for field in required):
                    logger.error(f"Missing required field in roster_data: {roster_data}")
                    continue

                ## Debug next 1 line for primary/secondary sport roster
                logger.debug(f"Adding to current_sports: ('{sport_type}', '{sport_format}', '{sport_gender}', {roster_data['team_order']})")
                current_sports.add((roster_data["sport_type"], roster_data["sport_format"], roster_data["sport_gender"], roster_data["team_order"]))
                self._create_or_update_roster(roster_data)

        ## Debug next line - show all current sports
        logger.debug(f"Current sports after processing: {current_sports}")
    
        # Cleanup outdated rosters
        try:
            all_rosters = self.wordpress_connector.get_rosters({"participant_id": participant_id})
            logger.debug(f"Found {len(all_rosters)} existing rosters for participant_id={participant_id}") ## Debug
 
            for roster in all_rosters:
                roster_key = (roster["sport_type"], roster["sport_format"], roster["sport_gender"], roster["team_order"])
                logger.debug(f"Checking roster_id={roster['roster_id']}: key={roster_key}")
                if roster_key not in current_sports:
                    logger.info(f"Deleting roster_id={roster['roster_id']}: {roster_key} NOT in current_sports") ## debug
                    self.wordpress_connector.delete_roster(roster["roster_id"])
                    self.stats["rosters"]["deleted"] += 1
                else:
                    logger.debug(f"Keeping roster_id={roster['roster_id']}: {roster_key} found in current_sports")
        except Exception as e:
            logger.error(f"Error cleaning up rosters: {e}")
            self.stats["rosters"]["errors"] += 1

    def _create_or_update_roster(self, roster_data: Dict[str, Any]): # Your correct signature
        """Create or update a roster entry."""
        # Get details for logging prefix
        participant_id_log = roster_data.get("participant_id")
        sport_type_log = roster_data.get("sport_type")
        sport_format_log = roster_data.get("sport_format")
        log_prefix = f"C_O_U_R [P:{participant_id_log} S:{sport_type_log} F:{sport_format_log}]"

        logger.debug(f"{log_prefix} - ENTRY. Full roster_data received: {roster_data}")
        try:
            query_params = {
                "participant_id": roster_data["participant_id"],
                "sport_type": roster_data["sport_type"],
                "sport_format": roster_data["sport_format"],
                "sport_gender": roster_data["sport_gender"],  # Needed to flip Smart Gender Mapping for Volleyball
            }
            # Explicitly add team_order to query_params IF IT EXISTS in roster_data
            # This ensures that if team_order is None or not present, it's not part of the query,
            # unless your WP API specifically handles a 'team_order=null' query parameter.
            # For now, let's assume if team_order is None in roster_data, we don't send it.
            # If team_order: None should match team_order IS NULL in DB, then Python must send
            # team_order as a parameter (e.g. team_order=None) and PHP API must handle it.
            # Current: if roster_data.get("team_order") is None, it WONT be in query_params.
            # This might be an issue if team_order IS NULL is a key differentiator.
            if roster_data.get("team_order") is not None:
                query_params["team_order"] = roster_data["team_order"]
            
            logger.debug(f"{log_prefix} - Querying WP with params: {query_params}")
            existing_rosters_list = self.wordpress_connector.get_rosters(query_params) # Expect a list
            logger.debug(f"{log_prefix} - WP get_rosters returned (list): {existing_rosters_list}")

            matched_existing_roster_details = None
            if existing_rosters_list: # Check if the list is not empty
                # If multiple matches, this takes the first. This is a key assumption.
                # This could be problematic if (participant_id, sport, format) without team_order
                # returns multiple rosters (e.g., Volleyball Team A, Volleyball Team B)
                # and team_order was not specific enough in the query or roster_data.
                matched_existing_roster_details = existing_rosters_list[0]
                logger.debug(f"{log_prefix} - Selected matched_existing_roster_details (from list[0]): {matched_existing_roster_details}")
            else:
                logger.debug(f"{log_prefix} - No existing rosters found by query.")


            if matched_existing_roster_details:
                roster_id_to_update = matched_existing_roster_details['roster_id']
                logger.debug(f"{log_prefix} - Existing roster found (ID: {roster_id_to_update}). Checking for updates.")

                fields_to_check_for_update = ["partner_name", "team_order"]
                update_payload = {}
                needs_db_update = False

                for field_key in fields_to_check_for_update:
                    new_value = roster_data.get(field_key)
                    existing_value = matched_existing_roster_details.get(field_key)

                    # Normalize for comparison
                    normalized_new = "" if new_value is None else str(new_value)
                    normalized_existing = "" if existing_value is None else str(existing_value)
                    
                    if normalized_new != normalized_existing:
                        logger.debug(f"{log_prefix} - Field '{field_key}' differs. From CHM/Mapped: '{new_value}' (normalized: '{normalized_new}'). In DB: '{existing_value}' (normalized: '{normalized_existing}').")
                        update_payload[field_key] = new_value # Send original new_value (None, empty, or actual)
                        needs_db_update = True
                
                if needs_db_update:
                    logger.info(f"{log_prefix} - Updating existing roster_id {roster_id_to_update}. Current DB values from matched: {matched_existing_roster_details}. Payload for update: {update_payload}")
                    result = self.wordpress_connector.update_roster(roster_id_to_update, update_payload)
                    if result:
                        self.stats["rosters"].setdefault("updated", 0)
                        self.stats["rosters"]["updated"] += 1
                        logger.debug(f"{log_prefix} - Roster update successful for ID {roster_id_to_update}. Result: {result}")
                    else:
                        logger.error(f"{log_prefix} - Failed to update roster ID {roster_id_to_update}. WP Connector returned no/false result.")
                        self.stats["rosters"]["errors"] += 1
                else:
                    logger.debug(f"{log_prefix} - Existing roster_id {roster_id_to_update} found, but no relevant fields changed. No DB update needed.")

            else: # No existing roster found, create a new one
                logger.info(f"{log_prefix} - Creating new roster with data: {roster_data}")
                result = self.wordpress_connector.create_roster(roster_data)
                if result:
                    self.stats["rosters"]["created"] += 1
                    logger.debug(f"{log_prefix} - Roster creation successful. Result: {result}")
                else:
                    logger.error(f"{log_prefix} - Failed to create roster. WP Connector returned no/false result. Data: {roster_data}")
                    self.stats["rosters"]["errors"] += 1
        except Exception as e:
            logger.error(f"{log_prefix} - Exception in _create_or_update_roster. Current roster_data: {roster_data}", exc_info=True)
            self.stats["rosters"]["errors"] += 1

    def _log_validation_issues(self, participant_id: str, church_code: str, issues: List[Dict[str, str]]):
        """Log validation issues to sf_validation_issues."""
        for issue in issues:
            issue_data = {
                "church_id": self.churches_cache[church_code]["church_id"],
                "participant_id": participant_id,
                "issue_type": issue["type"],
                "issue_description": issue["description"],
                "status": "open"
            }
            self.wordpress_connector.create_validation_issue(issue_data)
            self.stats["validation_issues"]["created"] += 1

    def _sync_validation_issues(self, participant_id: str, church_code: str, issues: List[Dict[str, str]], last_updated: str):
        """Sync validation issues for a participant based on last update time.
        
        Args:
            participant_id: The WordPress participant ID
            church_code: The church code
            issues: List of validation issues from the validator
            last_updated: Timestamp when the participant was last updated
        """
        if not issues:
            # No issues to sync, we can return early
            return
        
        # Get existing issues for this participant
        existing_issues = self.wordpress_connector.get_validation_issues({
            "participant_id": participant_id,
            "status": "open"  # Only check open issues
        })
        
        # Create a lookup dictionary of existing issues
        existing_lookup = {}
        for issue in existing_issues:
            # Create a composite key using issue_type and rule_code (if available)
            key = f"{issue['issue_type']}:{issue.get('rule_code', '')}"
            existing_lookup[key] = issue
        
        # Set of issue keys we're processing now
        current_issue_keys = set()
        
        # Process each issue
        for issue in issues:
            issue_type = issue["type"]
            rule_code = issue.get("rule_code", "")
            key = f"{issue_type}:{rule_code}"
            current_issue_keys.add(key)
            
            # Extract sport_type from the issue dictionary
#            sport_type = issue.get("sport", None)  # Use the "sport" field from validator
#            sport_format = None  # Set to None unless available elsewhere
## Is this issue_data defined here but not use?
#            issue_data = {
#                "church_id": self.churches_cache[church_code]["church_id"],
#                "participant_id": participant_id,
#                "issue_type": issue_type,
#                "issue_description": issue["description"],
#                "rule_code": rule_code,
#                "rule_level": issue.get("rule_level", RULE_LEVEL["INDIVIDUAL"]),
#                "severity": issue.get("severity", VALIDATION_SEVERITY["ERROR"]),
#                "sport_type": sport_type,  # Now correctly populated
#                "sport_format": sport_format,  # Optional field, set to None
#                "status": "open",
#                "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#            }
            
            self._create_or_update_validation_issue(participant_id, church_code, issue, existing_lookup.get(key), last_updated)
        
        # Close any issues that weren't in the current validation results
        # (This means the issue has been resolved)
        for key, existing_issue in existing_lookup.items():
            if key not in current_issue_keys:
                # Issue is no longer present, mark it as resolved
                self.wordpress_connector.update_validation_issue(
                    existing_issue["issue_id"],
                    {
                        "status": "resolved",
                        "resolved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                )
                self.stats["validation_issues"]["resolved"] += 1
                logger.info(f"Resolved validation issue {existing_issue['issue_id']} for participant {participant_id}")

    def _create_or_update_validation_issue(self, participant_id: str, church_code: str, 
                                          issue: Dict[str, str], existing_issue: Optional[Dict[str, Any]],
                                          last_updated: str):
        """Create or update a validation issue based on timestamps.
        
        Args:
            participant_id: The WordPress participant ID
            church_code: The church code
            issue: The validation issue data
            existing_issue: Existing issue record from WordPress if any
            last_updated: Timestamp when the participant was last updated
        """
        issue_type = issue["type"]
        rule_code = issue.get("rule_code", "")
        
        # Prepare the issue data
        issue_data = {
            "church_id": self.churches_cache[church_code]["church_id"],
            "participant_id": participant_id,
            "issue_type": issue_type,
            "issue_description": issue["description"],
            "rule_code": rule_code,
            "rule_level": issue.get("rule_level", RULE_LEVEL["INDIVIDUAL"]),
            "severity": issue.get("severity", VALIDATION_SEVERITY["ERROR"]),
            "status": "open",
            "sport_type": issue.get("sport", None),  # Extract from issue
            "sport_format": issue.get("sport_format", None),  # Extract from issue, defaults to None
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if existing_issue:
            # Issue already exists, check if we need to update it
            existing_updated = existing_issue.get("updated_at", "1970-01-01 00:00:00")
            
            # Only update if the participant data has changed since the last validation
            if last_updated > existing_updated:
                # Check if any content actually changed
                if (existing_issue["issue_description"] != issue_data["issue_description"] or
                    existing_issue["severity"] != issue_data["severity"] or
                    existing_issue["status"] != "open"):  # Reopen if it was closed
                    
                    self.wordpress_connector.update_validation_issue(
                        existing_issue["issue_id"], 
                        issue_data
                    )
                    self.stats["validation_issues"]["updated"] += 1
                    logger.debug(f"Updated validation issue {existing_issue['issue_id']} for participant {participant_id}")
                else:
                    # Issue exists but hasn't changed
                    self.stats["validation_issues"]["unchanged"] += 1
            else:
                # Participant hasn't been updated since this validation issue was created or updated
                self.stats["validation_issues"]["skipped"] += 1
        else:
            # New issue, create it
            self.wordpress_connector.create_validation_issue(issue_data)
            self.stats["validation_issues"]["created"] += 1
            logger.debug(f"Created new validation issue for participant {participant_id}: {issue_type}")

# End of sync/participants.py