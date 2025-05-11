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

    def sync_participants(self) -> bool:
        """Synchronize participant data from ChMeetings 'Team...' groups to WordPress."""
        logger.info("Starting participant synchronization...")
        # Define the target ChMeetings ID for detailed logging
        TARGET_CHM_ID_FOR_DEBUG = '0000000' # No chmeetings_id as Debugging Target for Logging
        
        if not self.chm_connector or not self.wordpress_connector:
            logger.warning("Connectors not available")
            return False

        if not self.churches_cache:
            wp_churches = self.wordpress_connector.get_churches()
            self.churches_cache.update({c["church_code"]: c for c in wp_churches})

        groups = self.chm_connector.get_groups()
        # Reduced verbosity for general group fetching unless it's a specific debug need
        # logger.info(f"All groups fetched: {groups}") 
        team_groups = [g for g in groups if g["name"].startswith(Config.TEAM_PREFIX)]
        logger.info(f"Filtered team_groups: {team_groups}")
        if not team_groups:
            logger.warning(f"No groups found with prefix '{Config.TEAM_PREFIX}'")
            return False

        logger.info(f"Found {len(team_groups)} '{Config.TEAM_PREFIX}' groups")

        for group in team_groups:
            participants = self.chm_connector.get_group_people(group["id"])
            if not participants:
                logger.info(f"No participants in group {group['name']}")
                continue

            logger.info(f"Processing {len(participants)} participants in group {group['name']}")
            for person in participants:
                person_id = str(person.get("person_id"))
                # Limit fetching person_data log too if needed, but often useful
                # person_data = self.chm_connector.get_person(person_id)
                # if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                #     logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Raw person_data for {person_id}: {person_data}")


                # Early exit for chm_id to avoid deep processing if not target (optional, but good for performance)
                # However, we need chm_id first.
                
                # Get chm_id as early as possible to apply the debug condition
                temp_person_data = self.chm_connector.get_person(person_id)
                if not temp_person_data:
                    logger.warning(f"Could not fetch details for person {person_id}")
                    continue
                
                temp_full_person = temp_person_data if isinstance(temp_person_data, dict) and "data" not in temp_person_data else temp_person_data.get("data", {})
                if not temp_full_person:
                    logger.warning(f"Skipping person {person_id}: No data returned from get_person")
                    continue
                
                # Assuming 'id' in temp_full_person is the chmeetings_id after get_person
                # or use a lightweight way to get chm_id if possible before full mapping
                # For now, we'll proceed with mapping to get chm_id cleanly.
                # If performance is still an issue, this part might need optimization
                # to get chm_id before full mapping for non-target records.

                mapped = self._map_chmeetings_participants([temp_full_person])[0]
                chm_id = mapped["chmeetings_id"]
                
                # Conditional detailed logging starts here
                if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                    logger.debug(f"--------------------------------------------------------------------------")
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] START PROCESSING TARGET RECORD")
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Raw person_data from ChM: {temp_person_data}")
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Full person data after initial parse: {temp_full_person}")
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Initial mapped data: {mapped}")

                roles = mapped.get("roles", "")
                is_athlete_or_participant = any(role.strip() in ["Athlete", "Participant", "Athlete/Participant"] for role in roles.split(","))
                if not is_athlete_or_participant:
                    # This log can be general or also conditional if too noisy
                    # logger.info(f"Skipping {chm_id} ({mapped.get('first_name', 'N/A')} {mapped.get('last_name', 'N/A')}): Roles '{roles}' do not qualify.")
                    continue

                required_fields = ["first_name", "last_name", "church_code"]
                missing_fields = [field for field in required_fields if not mapped.get(field)]
                if missing_fields:
                    logger.error(f"Skipping {chm_id}: Missing required fields {missing_fields} in mapped data.")
                    if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                        logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Mapped data causing missing fields: {mapped}")
                    self.stats["participants"]["errors"] += 1
                    continue

                chm_updated_on_str = temp_full_person.get("updated_on", "1970-01-01T00:00:00+00:00").replace("Z", "+00:00")
                chm_updated_on = datetime.datetime.fromisoformat(chm_updated_on_str)
                chm_updated_on_utc = chm_updated_on.astimezone(pytz.UTC)
                mapped["updated_at"] = chm_updated_on_utc.strftime("%Y-%m-%d %H:%M:%S")
                
                if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] ChMeetings updated_on (UTC): {chm_updated_on_utc}, Mapped updated_at: {mapped['updated_at']}")

                current_wp_status = mapped.get("approval_status", APPROVAL_STATUS["PENDING"])
                final_status_determined = False
                wp_participant_id = None 

                participant_in_wp = (self.wordpress_connector.get_participants({"chmeetings_id": chm_id}) or [None])[0]

                if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Participant in WP (sf_participants direct fetch): {participant_in_wp}")
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Initial current_wp_status (from mapped before P1/P2): {current_wp_status}")

                if participant_in_wp:
                    wp_participant_id = participant_in_wp["participant_id"]
                    status_in_sf_participants = participant_in_wp.get("approval_status")
                    if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                        logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] P1 - WP Participant ID: {wp_participant_id}, Status from sf_participants: {status_in_sf_participants}")

                    if status_in_sf_participants in [APPROVAL_STATUS["APPROVED"], APPROVAL_STATUS["DENIED"]]:
                        current_wp_status = status_in_sf_participants
                        final_status_determined = True
                        if chm_id == TARGET_CHM_ID_FOR_DEBUG: # Also make existing info logs conditional for the target
                            logger.info(f"[TARGET] Participant {wp_participant_id} (ChM ID: {chm_id}): Status preserved as '{current_wp_status}' from existing sf_participants record.")
                    else:
                        existing_approvals = self.wordpress_connector.get_approvals(
                            params={"participant_id": wp_participant_id}
                        )
                        if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                            logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] P2 - Fetched sf_approvals records: {existing_approvals}")

                        if existing_approvals:
                            approval_record = existing_approvals[0] # Assuming the first one is the most relevant/latest
                            status_from_sf_approvals = approval_record.get("approval_status")
                            if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                                logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] P2 - Approval record found: {approval_record}")
                                logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] P2 - Status from sf_approvals: {status_from_sf_approvals}")

                            if status_from_sf_approvals in [APPROVAL_STATUS["APPROVED"], APPROVAL_STATUS["DENIED"]]:
                                current_wp_status = status_from_sf_approvals
                                final_status_determined = True
                                if chm_id == TARGET_CHM_ID_FOR_DEBUG: # Also make existing info logs conditional for the target
                                    logger.info(f"[TARGET] Participant {wp_participant_id} (ChM ID: {chm_id}): Status set to '{current_wp_status}' from sf_approvals table.")
                
                if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] After P1/P2 - current_wp_status: {current_wp_status}, final_status_determined: {final_status_determined}")
                
                mapped["approval_status"] = current_wp_status
                issues = [] 
                
                if not final_status_determined:
                    if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                        logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Entering validation/checklist logic. mapped['approval_status'] before this block: {mapped.get('approval_status')}")
                    
                    is_valid, issues = self.validate_participant(mapped) # 'issues' is populated here
                    
                    if is_valid:
                        completion_checklist = mapped.get("completion_checklist", "")
                        required_items = [
                            CHECK_BOXES["1-IDENTITY"], CHECK_BOXES["2-CONSENT"],
                            CHECK_BOXES["3-ACCOUNT"], CHECK_BOXES["4-PHOTO_ID"]
                        ]
                        all_items_checked = all(item.strip() in completion_checklist for item in required_items)
                        
                        if all_items_checked:
                            mapped["approval_status"] = APPROVAL_STATUS["PENDING_APPROVAL"]
                            # General info log, can be kept or made conditional if too noisy
                            # logger.info(f"Participant {chm_id}: Status set to '{mapped['approval_status']}' (validation passed, checklist complete).")
                        else:
                            mapped["approval_status"] = APPROVAL_STATUS["VALIDATED"]
                            # logger.info(f"Participant {chm_id}: Status set to '{mapped['approval_status']}' (validation passed, checklist incomplete).")
                    else:
                        mapped["approval_status"] = APPROVAL_STATUS["PENDING"]
                        # logger.info(f"Participant {chm_id}: Status set to '{mapped['approval_status']}' (failed validation).")
                    
                    if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                        logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] After validation/checklist logic - mapped['approval_status']: {mapped.get('approval_status')}, Issues: {issues}")
                
                if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Final approval_status for {chm_id} before WP update/create: {mapped.get('approval_status')}")

                try:
                    if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                        logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Payload for WordPress (participant_in_wp: {bool(participant_in_wp)}) MAPPED DATA: {mapped}")
                    
                    participant_id_for_roster_validation = None 

                    if participant_in_wp:
                        updated_participant = self.wordpress_connector.update_participant(wp_participant_id, mapped)
                        if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                            logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Update result: {updated_participant}")
                        if updated_participant:
                            # logger.info(f"Updated participant {chm_id}") # General log
                            self.stats["participants"]["updated"] += 1
                            self.participants_cache[chm_id] = updated_participant
                            participant_id_for_roster_validation = updated_participant["participant_id"]
                        else:
                            logger.error(f"Failed to update participant {chm_id}: No result returned")
                            self.stats["participants"]["errors"] += 1
                            continue
                    else:
                        created_participant = self.wordpress_connector.create_participant(mapped)
                        if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                            logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Create result: {created_participant}")
                        if created_participant:
                            # logger.info(f"Created participant {chm_id}") # General log
                            self.stats["participants"]["created"] += 1
                            self.participants_cache[chm_id] = created_participant
                            participant_id_for_roster_validation = created_participant["participant_id"]
                        else:
                            logger.error(f"Failed to create participant {chm_id}: No result returned")
                            self.stats["participants"]["errors"] += 1
                            continue

                    if participant_id_for_roster_validation:
                        if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                            logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Syncing rosters for WP participant_id {participant_id_for_roster_validation}")
                        self._sync_rosters(participant_id_for_roster_validation, mapped) # Pass mapped here
                        chm_updated_on_utc_str = mapped["updated_at"]
                        if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                             logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] Syncing validation issues for WP participant_id {participant_id_for_roster_validation}. Issues to sync: {issues}")
                        self._sync_validation_issues(participant_id_for_roster_validation, mapped["church_code"], issues, chm_updated_on_utc_str)
                    else:
                        logger.error(f"[SYNC_PARTICIPANT - {chm_id}] participant_id_for_roster_validation was not defined. Skipping roster and validation sync.")                   

                except Exception as e:
                    logger.exception(f"Error syncing participant {chm_id}: {e}")
                    self.stats["participants"]["errors"] += 1
                    if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                        logger.error(f"[SYNC_PARTICIPANT - {chm_id}] Exception occurred during WP update/create or subsequent sync.")
                    continue
                
                if chm_id == TARGET_CHM_ID_FOR_DEBUG:
                    logger.debug(f"[SYNC_PARTICIPANT - {chm_id}] END PROCESSING TARGET RECORD")
                    logger.debug(f"--------------------------------------------------------------------------")


        logger.info(f"Participant sync completed: Stats: Participants {self.stats['participants']}, Rosters: {self.stats['rosters']}, Validation Issues: {self.stats['validation_issues']}")
        return True
## New Code:
    def _map_chmeetings_participants(self, people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map ChMeetings person data to participant format."""
        TARGET_CHM_ID_FOR_DEBUG = '0000000' # No chmeetings_id as Debugging Target for Logging
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
            
            if current_person_chm_id_for_map == TARGET_CHM_ID_FOR_DEBUG: # Conditional log for photo
                logger.debug(f"[SYNC_PARTICIPANT_MAP - {current_person_chm_id_for_map}] Photo URL: {photo_url}")
                logger.debug(f"[SYNC_PARTICIPANT_MAP - {current_person_chm_id_for_map}] Additional Fields from ChM: {additional_fields}")

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
                "primary_partner": additional_fields.get("Primary Partner", ""),
                "secondary_sport": secondary_sport,
                "secondary_format": secondary_format_val,
                "secondary_partner": additional_fields.get("Secondary Partner", ""),
                "other_events": additional_fields.get("Other Events", ""),
                "approval_status": "pending", 
                "completion_checklist": additional_fields.get("Completion Check List", ""),
                "parent_info": additional_fields.get("Parent Info", ""),
                "roles": additional_fields.get("My role is", "")
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
                    logger.debug(f"Adding to current_sports: ('{other_sport}', 'Team', None)")
                    current_sports.add((other_sport, SPORT_FORMAT["TEAM"], None))
                    self._create_or_update_roster(roster_data, current_sports)
            else:
                sport_type = sport_value
                format_value = participant.get(format_field) if format_field else None

                if is_racquet_sport(sport_type) and format_value:
                    sport_format, sport_gender = parse_format(format_value)
                else:
                    # Team sport or no format specified
                    sport_parts = sport_value.split(" - ")
                    sport_type = sport_parts[0]
                    if len(sport_parts) > 1:
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
                logger.debug(f"Adding to current_sports: ('{sport_type}', '{sport_format}', {roster_data['team_order']})")
                current_sports.add((roster_data["sport_type"], roster_data["sport_format"], roster_data["team_order"]))
                self._create_or_update_roster(roster_data, current_sports)

        ## Debug next line - show all current sports
        logger.debug(f"Current sports after processing: {current_sports}")
    
        # Cleanup outdated rosters
        try:
            all_rosters = self.wordpress_connector.get_rosters({"participant_id": participant_id})
            logger.debug(f"Found {len(all_rosters)} existing rosters for participant_id={participant_id}") ## Debug
 
            for roster in all_rosters:
                roster_key = (roster["sport_type"], roster["sport_format"], roster["team_order"])
                logger.debug(f"Checking roster_id={roster['roster_id']}: key={roster_key}") ## debug
                if roster_key not in current_sports:
                    logger.info(f"Deleting roster_id={roster['roster_id']}: {roster_key} NOT in current_sports") ## debug
                    self.wordpress_connector.delete_roster(roster["roster_id"])
                    self.stats["rosters"]["deleted"] += 1
                else:
                    logger.debug(f"Keeping roster_id={roster['roster_id']}: {roster_key} found in current_sports")
        except Exception as e:
            logger.error(f"Error cleaning up rosters: {e}")
            self.stats["rosters"]["errors"] += 1

    def _create_or_update_roster(self, roster_data, current_sports):
        """Create or update a roster entry."""
        try:
            existing_rosters = self.wordpress_connector.get_rosters({
                "participant_id": roster_data["participant_id"],
                "sport_type": roster_data["sport_type"],
                "sport_format": roster_data["sport_format"],
                "team_order": roster_data["team_order"]
            })
            if not any(
                r["sport_type"] == roster_data["sport_type"] and
                r["sport_format"] == roster_data["sport_format"] and
                r["team_order"] == roster_data["team_order"]
                for r in existing_rosters
            ):
                logger.info(f"Creating roster: {roster_data}")
                result = self.wordpress_connector.create_roster(roster_data)
                logger.debug(f"Roster creation result: {result}")
                if result:
                    self.stats["rosters"]["created"] += 1
                else:
                    logger.error(f"Failed to create roster, no result returned: {roster_data}")
        except Exception as e:
            logger.error(f"Failed to create roster: {e}, data: {roster_data}")
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