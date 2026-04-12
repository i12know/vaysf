# Begin of sync/manager.py
##### version 1.0.1: sync_churches will load from Excel file and update if Church Code is not on WordPress
##### version 1.0.2: Fixed connector references, standardized stats, and updated run_full_sync for Excel
##### version 1.0.3: Added sf_rosters, mocked sync_participants refactor, refactored to ChurchSyncer and ParticipantSyncer

import os
import json
import time
from typing import Dict, Any, Optional
from loguru import logger
from config import (Config, DATA_DIR, APPROVAL_STATUS, CHECK_BOXES, MEMBERSHIP_QUESTION,
                   SPORT_TYPE, SPORT_CATEGORY, SPORT_FORMAT, GENDER, 
                   VALIDATION_SEVERITY, VALIDATION_STATUS, RULE_LEVEL)
from chmeetings.backend_connector import ChMeetingsConnector
from wordpress.frontend_connector import WordPressConnector
from sync.churches import ChurchSyncer
from sync.participants import ParticipantSyncer
import datetime
from uuid import uuid4
from tqdm import tqdm

class SyncManager:
    """Manager for synchronizing data between ChMeetings and WordPress."""

    def __init__(self):
        self.wordpress_connector = WordPressConnector()
        self.chm_connector = ChMeetingsConnector() if Config.CHM_API_URL and Config.CHM_API_KEY else None
        self.participants_cache = {}
        self.churches_cache = {}
        self.stats = {
            "churches": {"created": 0, "updated": 0, "skipped": 0, "errors": 0},
            "participants": {"created": 0, "updated": 0, "errors": 0},
            "rosters": {"created": 0, "deleted": 0, "errors": 0},
            "validation_issues": {"created": 0, "updated": 0, "resolved": 0, "unchanged": 0, "skipped": 0, "errors": 0},
            "approvals": {"created": 0, "updated": 0, "errors": 0}
        }

        self.church_syncer = ChurchSyncer(self.wordpress_connector, self.stats)
        self.participant_syncer = ParticipantSyncer(self.chm_connector, self.wordpress_connector, self.stats, self.churches_cache) if self.chm_connector else None
        logger.info("SyncManager initialized")

    def authenticate(self) -> bool:
        """Authenticate with both systems."""
        wp_auth = self.wordpress_connector is not None
        chm_auth = self.chm_connector.authenticate() if self.chm_connector else True
        if not self.chm_connector:
            logger.info("Skipping ChMeetings authentication (not configured)")
        return wp_auth and chm_auth

    def sync_churches_from_excel(self, excel_file_path: str) -> bool:
        """Trigger church synchronization from an Excel file."""
        return self.church_syncer.sync_from_excel(excel_file_path)

    def sync_participants(self, chm_id: Optional[str] = None) -> bool:
        """
        Trigger participant synchronization from ChMeetings.
        Can sync a single participant if chm_id is provided.
        """
        if self.participant_syncer:
            # Pass the chm_id to the ParticipantSyncer's method
            return self.participant_syncer.sync_participants(chm_id_to_sync=chm_id)
        logger.warning("Participant syncer not initialized. Cannot sync participants.")
        return False

    def get_validation_rules(self) -> Dict[str, Any]:
        """Return centralized validation rules."""
        return {
            "age": {
                "default": {"min": 13, "max": 35},
                "exceptions": {
                    "Scripture Memorization": {"min": 10, "max": 99},
                    "Tug-of-war": {"min": 13, "max": 99},
                    "Pickleball 35+": {"min": 35, "max": 99}
                }
            },
            "gender_restrictions": {
                "men_events": ["Men Basketball", "Men Volleyball"],
                "women_events": ["Women Volleyball"]
            },
            "team_composition": {
                "max_non_members": {
                    "team_events": 2,
                    "doubles_events": 1
                }
            },
            "max_events_per_participant": 2
        }
## New Code:
    def generate_approvals(self, chm_id_to_target: Optional[str] = None) -> bool: # New signature
        """Generate pastor approval tokens for participants with completed validation."""
        logger.info("Starting approval token generation...")

        if chm_id_to_target:
            logger.info(f"Targeting specific ChMeetings ID for approval generation: {chm_id_to_target}")
            # Fetch the specific participant by their chmeetings_id from WordPress
            # The get_participants method returns a list.
            wp_participants_list = self.wordpress_connector.get_participants(params={"chmeetings_id": chm_id_to_target})
            
            if not wp_participants_list:
                logger.warning(f"No participant found in WordPress with ChMeetings ID {chm_id_to_target}. Cannot generate approval.")
                return True # Indicate that the operation completed without error for this specific (not found) ID.
            
            participant_to_check = wp_participants_list[0] # Assuming chmeetings_id is unique

            # Check if this specific participant is in 'pending_approval' status
            if participant_to_check.get("approval_status") != APPROVAL_STATUS["PENDING_APPROVAL"]:
                logger.info(f"Participant ChM ID {chm_id_to_target} (WP ID: {participant_to_check.get('participant_id')}) "
                            f"is not in 'pending_approval' status (current: {participant_to_check.get('approval_status')}). "
                            "Skipping token generation for this participant.")
                return True # Successfully did nothing as participant is not ready.
            
            wp_participants = [participant_to_check] # Process only this participant
            logger.info(f"Processing 1 targeted participant (ChM ID: {chm_id_to_target}, WP ID: {participant_to_check.get('participant_id')}) for approval token generation.")
        else:
            # --- START: MODIFIED LOGIC FOR PAGINATION ---
            logger.info("Fetching ALL participants with 'pending_approval' status...")
            all_pending_approval_participants = [] # List to hold all participants from all pages
            current_page = 1
            fetch_per_page = 100 # You can adjust this, but 100 is a common good value
            max_pages_to_fetch = 50 # Safety limit to prevent infinite loops in unexpected scenarios

            while True:
                logger.info(f"Fetching page {current_page} of 'pending_approval' participants (per_page={fetch_per_page})...")
                page_participants = self.wordpress_connector.get_participants(
                    params={
                        "approval_status": APPROVAL_STATUS["PENDING_APPROVAL"],
                        "page": current_page,
                        "per_page": fetch_per_page
                    }
                )
                
                if not page_participants: # No participants found on this page, means we're done.
                    logger.info(f"No more participants found on page {current_page}. End of list.")
                    break 
                
                all_pending_approval_participants.extend(page_participants)
                logger.info(f"Fetched {len(page_participants)} participants on page {current_page}. Total fetched so far: {len(all_pending_approval_participants)}.")

                if len(page_participants) < fetch_per_page: # Last page fetched
                    logger.info("Last page of participants fetched.")
                    break
                
                current_page += 1
                if current_page > max_pages_to_fetch: 
                    logger.warning(f"Reached maximum page limit ({max_pages_to_fetch}) for fetching 'pending_approval' participants. Stopping to prevent potential infinite loop.")
                    break
            
            wp_participants = all_pending_approval_participants # Assign the fully fetched list

            if not wp_participants:
                logger.info("No participants found with 'pending_approval' status after checking all pages for token generation.")
                return True
            logger.info(f"Found {len(wp_participants)} total participants with 'pending_approval' status for token generation after checking all pages.")
            # --- END: MODIFIED LOGIC FOR PAGINATION ---
        
        # The rest of the original generate_approvals logic can remain largely the same,
        # as it iterates through the `wp_participants` list (which is now either all or one).

        wp_approvals = self.wordpress_connector.get_approvals() # Fetch all existing approvals
        ## old ## existing_approvals = {(a.get("participant_id"), a.get("church_id")): a for a in wp_approvals}
        existing_approvals = {(str(a.get("participant_id")), str(a.get("church_id"))): a for a in wp_approvals}
        
        if not self.churches_cache:
            wp_churches = self.wordpress_connector.get_churches()
            if wp_churches: # Ensure wp_churches is not None or empty
                 self.churches_cache = {c["church_code"]: c for c in wp_churches}
            else:
                logger.error("Failed to load churches into cache. Cannot proceed with approval generation.")
                return False # Critical failure if churches can't be loaded
        
        # Counter for participants ready for pastor approval
        ready_for_approval_count = 0 
        
        for participant in tqdm(wp_participants, desc="Generating approval tokens"):
            logger.debug(f"Processing participant for approval: WP_ID {participant['participant_id']}, Name: {participant['first_name']} {participant['last_name']}, Church: {participant['church_code']}, Status: {participant['approval_status']}") # <-- ADD THIS
            wp_participant_id_int = participant["participant_id"] # Keep as int for DB operations
            wp_participant_id_str = str(wp_participant_id_int)    # Use string for dict keys
            church_code = participant["church_code"]
            
            # Ensure church_code is in cache
            if church_code not in self.churches_cache:
                logger.warning(f"Church with code '{church_code}' not found in cache for participant WP ID {wp_participant_id_str}. Skipping.")
                self.stats["approvals"]["errors"] += 1
                continue
            
            church_wp_id_str = str(self.churches_cache[church_code]["church_id"]) # Use string for dict keys

            # --- CHECK FOR EXISTING APPROVAL ---
            # This check is still important to prevent duplicate emails.
            if (wp_participant_id_str, church_wp_id_str) in existing_approvals:
                logger.info(f"Approval record already exists for participant WP ID {wp_participant_id_str} and church WP ID {church_wp_id_str}. Skipping token generation.")
                continue
            # --- END OF EXISTING APPROVAL CHECK ---

            # If we are here, it means:
            # 1. The participant is in 'PENDING_APPROVAL' status (because of how wp_participants was queried or filtered).
            # 2. No approval token/record exists for them yet.
            # We are trusting that 'PENDING_APPROVAL' implies the checklist was previously satisfied.

            ready_for_approval_count += 1
            
            church = self.churches_cache[church_code] 
            pastor_email = church.get("pastor_email")
            if not pastor_email:
                logger.warning(f"Pastor email not found for church '{church.get('church_name')}' (Code: {church_code}). Cannot send approval for participant WP ID {wp_participant_id_str}.")
                self.stats["approvals"]["errors"] += 1
                continue
            
            token = str(uuid4())
            expiry_date = datetime.datetime.now() + datetime.timedelta(days=Config.TOKEN_EXPIRY_DAYS)
            approval_data = {
                "participant_id": wp_participant_id_int, 
                "church_id": int(church_wp_id_str),      
                "approval_token": token,
                "token_expiry": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                "pastor_email": pastor_email,
                "approval_status": APPROVAL_STATUS["PENDING"], 
                "synced_to_chmeetings": False
            }
            
            try:
                created_approval = self.wordpress_connector.create_approval(approval_data)
                if created_approval:
                    self.stats["approvals"]["created"] += 1
                    logger.info(f"Successfully created approval record for participant WP ID {wp_participant_id_str}. Token: {token}")
                    
                    participant_name = f"{participant['first_name']} {participant['last_name']}"
                    # 'participant' is the dictionary fetched from WordPress containing all participant details
                    # including first_name, last_name, photo_url (if synced), is_church_member, etc.
                    self.send_pastor_approval_email(pastor_email, participant_name, token, participant, expiry_date) 
                else:
                    logger.error(f"Failed to create approval record for participant WP ID {wp_participant_id_str} via WordPress connector.")
                    self.stats["approvals"]["errors"] += 1

            except Exception as e:
                logger.error(f"Error creating approval or sending email for participant WP ID {wp_participant_id_str}: {e}", exc_info=True)
                self.stats["approvals"]["errors"] += 1
        
        if chm_id_to_target:
            if ready_for_approval_count == 0 and not wp_participants: # Means the targeted participant was not found or not ready
                 logger.info(f"Targeted participant ChM ID {chm_id_to_target} was not processed for token generation (either not found, not pending_approval, or already has token).")
            elif ready_for_approval_count > 0 :
                 logger.info(f"Processed targeted participant ChM ID {chm_id_to_target} for approval.")
        else:
             logger.info(f"Found {ready_for_approval_count} participants overall ready for pastor approval email generation.")

        logger.info(f"Approval token generation process completed. Stats: {self.stats['approvals']}")
        return True

## New Code:
    def send_pastor_approval_email(self, pastor_email: str, participant_name: str, token: str, 
                                   participant_data: Dict[str, Any], expiry_date: datetime.datetime) -> bool:
        """Send approval email to pastor and notification to participant/church rep."""
        try:
            # Try to get photo URL from participant data
            photo_url = participant_data.get("photo_url", "")
            
            # If no photo URL in WordPress data, try to get it from ChMeetings
            if not photo_url and participant_data.get("chmeetings_id") and self.chm_connector:
                try:
                    chmeetings_id = participant_data["chmeetings_id"]
                    logger.info(f"Fetching photo for participant {chmeetings_id} from ChMeetings")
                    chm_person = self.chm_connector.get_person(chmeetings_id)
                    if chm_person and chm_person.get("photo"):
                        photo_url = chm_person.get("photo")
                        logger.info(f"Retrieved photo URL from ChMeetings: {photo_url}")
                        
                        # Update the WordPress record with the retrieved photo URL
                        self.wordpress_connector.update_participant(
                            participant_data["participant_id"], 
                            {"photo_url": photo_url}
                        )
                        logger.info(f"Updated WordPress participant record with photo URL")
                except Exception as e:
                    logger.warning(f"Failed to get photo from ChMeetings: {e}")
            
            # Generate HTML for photo
            photo_html = f'<img src="{photo_url}" alt="{participant_name}" style="max-width: 200px; max-height: 200px; margin: 10px 0;">' if photo_url else '<p>(No photo available)</p>'
            
            # Rest of the function remains the same...
            # Get church data
            church_code = participant_data.get("church_code")
            church = self.churches_cache.get(church_code, {})
            church_rep_name = church.get("church_rep_name", "N/A")
            church_rep_email = church.get("church_rep_email", "N/A")
            church_rep_phone = church.get("church_rep_phone", "N/A")
            
            # Format dates for display
            sports_fest_date = datetime.datetime.strptime(Config.SPORTS_FEST_DATE, "%Y-%m-%d").strftime("%B %d, %Y")
            token_expiry_date = expiry_date.strftime("%B %d, %Y at %I:%M %p")
            
            # Get membership claim information
            ## Bug ## is_church_member = "Yes" if participant_data.get("is_church_member", False) else "No"
            ## Bug also ## is_church_member = "Yes" if str(participant_data.get("is_church_member", 0)) == "1" else "No"
            membership_value = participant_data.get("is_church_member", False)
            # Handle various formats: boolean True/False, string "1"/"0", integer 1/0, string "Yes"/"No"
            if membership_value in [True, 1, "1", "Yes", "yes", "TRUE", "true"]:
                is_church_member = "Yes"
            else:
                is_church_member = "No"
            
            # Pastor approval email
            approval_link_base = f"{Config.WP_URL}/pastor-approval"
            approve_link = f"{approval_link_base}?token={token}&decision=approve"
            deny_link = f"{approval_link_base}?token={token}&decision=deny"
            
            pastor_email_data = {
                "to": pastor_email,
                "subject": f"Sports Fest Approval Request for {participant_name}",
                "message": f"""
                <h2>Sports Fest Participant Approval for {participant_name}</h2>
                
                <div style="margin: 20px 0;">
                    {photo_html}
                </div>
                
                <p>Dear Pastor,</p>
                
                <p>A participant, <strong>{participant_name}</strong>, has registered for Sports Fest (starting on {sports_fest_date}) 
                and listed under your church. Please review and approve or deny their participation.</p>
                
                <h3>Participant Information:</h3>
                <ul>
                    <li><strong>Membership Question:</strong> {MEMBERSHIP_QUESTION}</li>
                    <li><strong>Participant's Answer:</strong> {is_church_member}</li>
                </ul>
                
                <p>Please make your decision by clicking one of the buttons below:</p>
                
                <p>
                    <a href="{approve_link}" style="padding: 10px 15px; background: #4CAF50; color: white; text-decoration: none; margin-right: 10px;">Approve</a>
                    <a href="{deny_link}" style="padding: 10px 15px; background: #f44336; color: white; text-decoration: none;">Deny</a>
                </p>
                
                <p><strong>Note:</strong> This approval link will expire on {token_expiry_date}. If you need more time, please contact the church representative: <strong>{church_rep_name}</strong> at {church_rep_phone} or {church_rep_email}</p>
                
                <p>Thank you for your help with Sports Fest!</p>
                """,
                "from_email": Config.EMAIL_FROM
            }
            
            # Send to pastor
            pastor_result = self.wordpress_connector.send_email(**pastor_email_data)
            
            # Send notification to participant and church rep
            participant_email = participant_data.get("email")
            
            if participant_email and church_code in self.churches_cache:
                # Build CC list with church rep if available
                cc_list = []
                if church_rep_email:
                    cc_list.append(church_rep_email)
                
                notification_email_data = {
                    "to": participant_email,
                    "cc": cc_list,
                    "subject": f"Sports Fest Pastor Approval Requested for you, {participant_name}",
                    "message": f"""
                    <p>Dear {participant_name},</p>
                    
                    <p>We have sent an approval request to your church pastor for Sports Fest (starting on {sports_fest_date}).</p>
                    
                    <p>Your Sports Fest registration will be finalized once the pastor confirms your church membership.</p>
                    
                    <p>The pastor has until {token_expiry_date} to respond to this request. If you don't receive confirmation 
                    by then, please follow up with your church representative, {church_rep_name}, at {church_rep_email}.</p>
                    
                    <p>Thank you for registering for Sports Fest!</p>
                    """,
                    "from_email": Config.EMAIL_FROM
                }
                
                participant_result = self.wordpress_connector.send_email(**notification_email_data)
                
                # Return success only if both emails were sent successfully
                return pastor_result.get("success", False) and participant_result.get("success", False)
            
            # If we can't send the notification, at least return pastor email result
            return pastor_result.get("success", False)
        except Exception as e:
            logger.error(f"Failed to send pastor approval email: {e}")
            return False

    def sync_approvals_to_chmeetings(self) -> bool:
        """Synchronize approval statuses from WordPress to ChMeetings via direct API calls."""
        logger.info("Starting approval synchronization to ChMeetings...")
        if not self.chm_connector:
            logger.warning("ChMeetings connector not available")
            return False

        # Fetch all approved WP participants (paginated)
        all_approved_wp_participants = []
        current_page = 1
        fetch_per_page = 100

        while True:
            logger.info(
                f"Fetching page {current_page} of approved participants from WordPress "
                f"(per_page={fetch_per_page})..."
            )
            page_participants = self.wordpress_connector.get_participants(
                params={"approval_status": "approved", "page": current_page, "per_page": fetch_per_page}
            )
            if not page_participants:
                break
            all_approved_wp_participants.extend(page_participants)
            if len(page_participants) < fetch_per_page:
                break
            current_page += 1
            if current_page > 50:
                logger.warning("Reached page limit (50) for fetching approved participants. Stopping.")
                break

        if not all_approved_wp_participants:
            logger.info("No approved participants found to sync to ChMeetings.")
            return True

        logger.info(f"Found {len(all_approved_wp_participants)} approved participants to sync.")

        # Find the configured approved group in ChMeetings (fail hard if missing)
        all_groups = self.chm_connector.get_groups()
        approved_group = next(
            (g for g in all_groups if g.get("name") == Config.APPROVED_GROUP_NAME),
            None,
        )
        if approved_group is None:
            logger.error(
                f"Group '{Config.APPROVED_GROUP_NAME}' not found in ChMeetings. "
                "Cannot sync approvals. Check APPROVED_GROUP_NAME in your .env config."
            )
            return False

        approved_group_id = str(approved_group["id"])
        logger.info(
            f"Found approved group '{Config.APPROVED_GROUP_NAME}' (id={approved_group_id})"
        )

        # Add each approved participant to the ChMeetings group via API
        successfully_synced_ids = []
        failed_count = 0

        for participant in all_approved_wp_participants:
            chmeetings_id = participant.get("chmeetings_id")
            wp_participant_id = str(participant.get("participant_id"))

            if not chmeetings_id:
                logger.warning(
                    f"Participant WP_ID {wp_participant_id} missing ChMeetings ID, skipping."
                )
                failed_count += 1
                continue

            ok = self.chm_connector.add_person_to_group(
                approved_group_id, str(chmeetings_id)
            )
            time.sleep(0.2)  # 200 ms between calls → ~5 req/s, avoids 429 rate limit
            if ok:
                successfully_synced_ids.append(wp_participant_id)
            else:
                logger.warning(
                    f"Failed to add participant WP_ID {wp_participant_id} "
                    f"(ChM ID {chmeetings_id}) to group '{Config.APPROVED_GROUP_NAME}'."
                )
                failed_count += 1

        logger.info(
            f"Group add complete: {len(successfully_synced_ids)} added, {failed_count} failed."
        )

        if not successfully_synced_ids:
            logger.info("No participants successfully added; nothing to mark as synced.")
            return failed_count == 0

        # Mark synced in WordPress — only for participants whose API add succeeded
        logger.info("Fetching approval records to mark as synced...")
        all_relevant_approvals = self.wordpress_connector.get_approvals(
            params={
                "approval_status": "approved",
                "synced_to_chmeetings": False,
                "per_page": 500,
            }
        )
        if all_relevant_approvals is None:
            logger.error("Failed to fetch approval records from WordPress. Cannot mark as synced.")
            return False

        logger.info(
            f"Fetched {len(all_relevant_approvals)} approval records to check for marking as synced."
        )

        approvals_lookup = {
            str(ar.get("participant_id")): ar for ar in all_relevant_approvals
        }

        marked_synced_count = 0
        for p_id_str in successfully_synced_ids:
            approval_record = approvals_lookup.get(p_id_str)
            if approval_record:
                update_success = self.wordpress_connector.update_approval(
                    approval_record["approval_id"],
                    {"synced_to_chmeetings": True},
                )
                if update_success:
                    self.stats["approvals"]["updated"] += 1
                    marked_synced_count += 1
                else:
                    logger.warning(
                        f"Failed to mark approval_id {approval_record['approval_id']} "
                        f"as synced for participant_id {p_id_str}."
                    )
            else:
                logger.debug(
                    f"No 'approved' and 'not synced' approval record found for "
                    f"participant_id {p_id_str}. May already be synced or status changed."
                )

        logger.info(
            f"Sync complete: {marked_synced_count} approvals marked as synced in WordPress."
        )
        return failed_count == 0
        
    def validate_data(self) -> bool:
        """Validate participant data against Sports Fest rules."""
        logger.info("Starting data validation...")
        wp_participants = []
        current_page = 1
        fetch_per_page = 100
        while True:
            page_participants = self.wordpress_connector.get_participants(
                params={"page": current_page, "per_page": fetch_per_page}
            )
            if not page_participants:
                break
            wp_participants.extend(page_participants)
            if len(page_participants) < fetch_per_page:
                break
            current_page += 1
            if current_page > 50:
                logger.warning("Reached page limit (50) fetching participants for validation. Stopping.")
                break
        if not wp_participants:
            logger.warning("No participants found for validation")
            return False
        logger.info(f"Fetched {len(wp_participants)} participants for validation.")

        rules = self.get_validation_rules()
        participants_by_church = {}
        for participant in wp_participants:
            church_id = participant["church_id"]
            participants_by_church.setdefault(church_id, []).append(participant)

        validation_issues = []
        sports_fest_date = datetime.datetime.strptime(Config.SPORTS_FEST_DATE, "%Y-%m-%d").date()

        for church_id, participants in participants_by_church.items():
            # Team composition validation
            team_events = {"Basketball": [], "Men Volleyball": [], "Women Volleyball": [], "Bible Challenge": []}
            double_events = {"Badminton": {}, "Pickleball": {}, "Table Tennis": {}, "Tennis": {}}

            for participant in participants:
                is_member = participant.get("is_church_member", False)
                if not is_member:
                    for field, format_field in [("primary_sport", "primary_format"), ("secondary_sport", "secondary_format")]:
                        sport = participant.get(field, "")
                        format = participant.get(format_field, "")
                        if sport in team_events:
                            team_events[sport].append(participant)
                        elif sport in double_events and format and "double" in format.lower():
                            double_events[sport].setdefault(format, []).append(participant)

            max_team_non_members = rules["team_composition"]["max_non_members"]["team_events"]
            for sport, non_members in team_events.items():
                if len(non_members) > max_team_non_members:
                    validation_issues.append({
                        "church_id": church_id,
                        "participant_id": None,
                        "issue_type": "team_non_member_limit",
                        "issue_description": f"{sport} has {len(non_members)} non-members, exceeding limit of {max_team_non_members}",
                        "status": "open"
                    })

            max_doubles_non_members = rules["team_composition"]["max_non_members"]["doubles_events"]
            for sport, formats in double_events.items():
                for format_name, non_members in formats.items():
                    if len(non_members) > max_doubles_non_members:
                        validation_issues.append({
                            "church_id": church_id,
                            "participant_id": None,
                            "issue_type": "doubles_non_member_limit",
                            "issue_description": f"{sport} {format_name} has {len(non_members)} non-members, exceeding limit of {max_doubles_non_members}",
                            "status": "open"
                        })

        for issue in tqdm(validation_issues, desc="Creating validation issues"):
            try:
                if self.wordpress_connector.create_validation_issue(issue):
                    self.stats["validation_issues"]["created"] += 1
            except Exception as e:
                logger.error(f"Error creating validation issue: {e}")
                self.stats["validation_issues"]["errors"] += 1

        logger.info(f"Data validation completed: {self.stats['validation_issues']}")
        return True

    def run_full_sync(self) -> Dict[str, Any]:
        """Run a full synchronization process."""
        logger.info("Starting full synchronization process...")
        self.stats = {
            "churches": {"created": 0, "updated": 0, "skipped": 0, "errors": 0},
            "participants": {"created": 0, "updated": 0, "errors": 0},
            "approvals": {"created": 0, "updated": 0, "errors": 0},
            "validation_issues": {"created": 0, "errors": 0},
            "rosters": {"created": 0, "deleted": 0, "errors": 0}
        }

        excel_path = os.path.join(DATA_DIR, "Church Application Form.xlsx")
        if os.path.exists(excel_path):
            self.sync_churches_from_excel(excel_path)
        else:
            logger.error(f"Excel file not found at {excel_path}")

        self.sync_participants()
        self.generate_approvals()
        self.sync_approvals_to_chmeetings()
        # self.validate_data() ## temporary skipped until more validations can be tested.

        logger.info("Full synchronization completed")
        return self.stats

    def close(self):
        """Close connections and clean up resources."""
        if self.chm_connector:
            self.chm_connector.close()
        if self.wordpress_connector:
            self.wordpress_connector.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
# End of sync/manager.py