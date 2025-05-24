# Begin of sync/manager.py
##### version 1.0.1: sync_churches will load from Excel file and update if Church Code is not on WordPress
##### version 1.0.2: Fixed connector references, standardized stats, and updated run_full_sync for Excel
##### version 1.0.3: Added sf_rosters, mocked sync_participants refactor, refactored to ChurchSyncer and ParticipantSyncer

import os
import json
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
    def generate_approvals(self) -> bool:
        """Generate pastor approval tokens for participants with completed validation."""
        logger.info("Starting approval token generation...")
        
        # Get ALL participants with pending approval status
        wp_participants = self.wordpress_connector.get_participants(params={"approval_status": APPROVAL_STATUS["PENDING_APPROVAL"]})
        if not wp_participants:
            logger.info("No pending participants found for approval")
            return True
        
        logger.info(f"Found {len(wp_participants)} participants with pending status")
        wp_approvals = self.wordpress_connector.get_approvals()
        existing_approvals = {(a.get("participant_id"), a.get("church_id")): a for a in wp_approvals}
        
        if not self.churches_cache:
            wp_churches = self.wordpress_connector.get_churches()
            self.churches_cache = {c["church_code"]: c for c in wp_churches}
        
        # Counter for participants ready for pastor approval
        ready_for_approval_count = 0
        
        for participant in tqdm(wp_participants, desc="Generating approval tokens"):
            wp_participant_id = participant["participant_id"]
            church_code = participant["church_code"]
            
            # Skip if approval token already exists
            if (wp_participant_id, self.churches_cache[church_code]["church_id"]) in existing_approvals:
                continue
            
            # Check if participant has completed all pre-approval validation steps
            completion_checklist = participant.get("completion_checklist", "")
            
            # Required checklist items - using constants from config.py
#            required_items = [
#                CHECK_BOXES["1-IDENTITY"],
#                CHECK_BOXES["2-CONSENT"],
#                CHECK_BOXES["3-ACCOUNT"],
#                CHECK_BOXES["4-PHOTO_ID"]
#            ]
            
            # Check if all required items are in the checklist (consider order might vary)
#            all_items_checked = all(
#                item.strip() in completion_checklist for item in required_items
#            )
            
            # Skip if validation is not complete
#            if not all_items_checked:
#                logger.info(f"Skipping participant {wp_participant_id}: incomplete validation")
#                continue
            
            # Check if participant already has the approval item checked (shouldn't happen with proper validation)
#            if CHECK_BOXES["5-APPROVAL"] in completion_checklist:
#                logger.warning(f"Participant {wp_participant_id} already has approval checked but status is still pending")
#                continue
            
            # Participant is validated and ready for pastor approval
            ready_for_approval_count += 1
            
            # Update the approval status to pending_approval to indicate it's awaiting pastor's decision
            self.wordpress_connector.update_participant(
                wp_participant_id, 
                {"approval_status": APPROVAL_STATUS["PENDING_APPROVAL"]}
            )
            
            # Generate and store token for pastor approval
            if church_code not in self.churches_cache:
                logger.warning(f"Church not found for participant {wp_participant_id}")
                continue
            
            church = self.churches_cache[church_code]
            pastor_email = church.get("pastor_email")
            if not pastor_email:
                logger.warning(f"Pastor email not found for church {church.get('church_name')}")
                continue
            
            token = str(uuid4())
            expiry_date = datetime.datetime.now() + datetime.timedelta(days=Config.TOKEN_EXPIRY_DAYS)
            approval_data = {
                "participant_id": wp_participant_id,
                "church_id": church["church_id"],
                "approval_token": token,
                "token_expiry": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                "pastor_email": pastor_email,
                "approval_status": APPROVAL_STATUS["PENDING"],
                "synced_to_chmeetings": False
            }
            
            try:
                if self.wordpress_connector.create_approval(approval_data):
                    self.stats["approvals"]["created"] += 1
                    
                    # Send approval email to pastor (will implement this in the WordPress REST API)
                    participant_name = f"{participant['first_name']} {participant['last_name']}"
                    # Add this debug line near the start of send_pastor_approval_email
                    logger.debug(f"Participant data for email: {json.dumps(participant)}")
                    self.send_pastor_approval_email(pastor_email, participant_name, token, participant, expiry_date)
            except Exception as e:
                logger.error(f"Error creating approval for participant {wp_participant_id}: {e}")
                self.stats["approvals"]["errors"] += 1
        
        logger.info(f"Found {ready_for_approval_count} participants ready for pastor approval")
        logger.info(f"Approval token generation completed: {self.stats['approvals']}")
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
            is_church_member = "Yes" if str(participant_data.get("is_church_member", 0)) == "1" else "No"
            
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
        
## Old Code:
#    def generate_approvals(self) -> bool:
#        """Generate pastor approval tokens for participants needing approval."""
#        logger.info("Starting approval token generation...")
#        wp_participants = self.wordpress_connector.get_participants(params={"approval_status": "pending"})
#        if not wp_participants:
#            logger.info("No pending participants found for approval")
#            return True
#
#        logger.info(f"Found {len(wp_participants)} participants needing approval")
#        wp_approvals = self.wordpress_connector.get_approvals()
#        existing_approvals = {(a.get("participant_id"), a.get("church_id")): a for a in wp_approvals}
#
#        if not self.churches_cache:
#            wp_churches = self.wordpress_connector.get_churches()
#            self.churches_cache = {c["church_code"]: c for c in wp_churches}
#
#        for participant in tqdm(wp_participants, desc="Generating approval tokens"):
#            wp_participant_id = participant["id"]
#            wp_church_id = participant["church_id"]
#            if (wp_participant_id, wp_church_id) in existing_approvals:
#                continue#
#
#            if wp_church_id not in self.churches_cache:
#                logger.warning(f"Church not found for participant {wp_participant_id}")#
#
#                continue
#
#
#            church = self.churches_cache[wp_church_id]
#            pastor_email = church.get("pastor_email")
#            if not pastor_email:
#                logger.warning(f"Pastor email not found for church {church.get('church_name')}")
#                continue
#
#            token = str(uuid4())
#            expiry_date = datetime.datetime.now() + datetime.timedelta(days=Config.TOKEN_EXPIRY_DAYS)
#            approval_data = {
#                "participant_id": wp_participant_id,
#                "church_id": wp_church_id,
#                "approval_token": token,
#                "token_expiry": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
#                "pastor_email": pastor_email,
#                "approval_status": "pending",
#                "synced_to_chmeetings": False
#            }
#            try:
#                if self.wordpress_connector.create_approval(approval_data):
#                    self.stats["approvals"]["created"] += 1
#            except Exception as e:
#                logger.error(f"Error creating approval for participant {wp_participant_id}: {e}")
#                self.stats["approvals"]["errors"] += 1
#
#        logger.info(f"Approval token generation completed: {self.stats['approvals']}")
#        return True

    def sync_approvals_to_chmeetings(self) -> bool:
        """Synchronize approval statuses from WordPress to ChMeetings via Excel import."""
        logger.info("Starting approval synchronization to ChMeetings...")
        if not self.chm_connector:
            logger.warning("ChMeetings connector not available")
            return False

        # Get ALL approved participants from WordPress
        wp_participants = self.wordpress_connector.get_participants(
            params={"approval_status": "approved"}
        )
        
        if not wp_participants:
            logger.info("No approved participants found to sync to ChMeetings")
            return True

        logger.info(f"Found {len(wp_participants)} total approved participants to sync")
        
        # Create pandas DataFrame for Excel export
        import pandas as pd
        
        # Initialize list to hold participant data
        participants_data = []
        
        for participant in wp_participants:
            if not participant.get("chmeetings_id"):
                logger.warning(f"Participant {participant.get('participant_id')} missing ChMeetings ID, skipping")
                continue
            
            chm_id = participant["chmeetings_id"]
            first_name = participant["first_name"]
            last_name = participant["last_name"]
            
            # Add to participants data
            participants_data.append({
                "Person Id": chm_id,
                "First Name": first_name,
                "Last Name": last_name,
                "Group Name": Config.APPROVED_GROUP_NAME
            })
        
        if not participants_data:
            logger.warning("No valid participants found for import")
            return False
        
        # Create DataFrame and export to Excel
        df = pd.DataFrame(participants_data)
        
        # Use the configured Excel file path from Config
        excel_path = Config.APPROVED_EXCEL_FILE
        
        try:
            # Export to Excel
            df.to_excel(excel_path, index=False)
            logger.info(f"Exported {len(participants_data)} approved participants to {excel_path}")
            
            # Mark all approvals as synced in WordPress
            wp_approvals = self.wordpress_connector.get_approvals(
                params={"synced_to_chmeetings": False, "approval_status": "approved"}
            )
            
            for approval in wp_approvals:
                self.wordpress_connector.update_approval(approval["approval_id"], {"synced_to_chmeetings": True})
                self.stats["approvals"]["updated"] += 1
            
            logger.info(f"Marked {len(wp_approvals)} approvals as synced to ChMeetings")
            logger.info(f"Please import the Excel file at {excel_path} to ChMeetings")
            
            # Optional: Open the Excel file for the user
            # import platform
            # import subprocess
            # if platform.system() == 'Windows':
            #     os.startfile(excel_path)
            
            return True
        
        except Exception as e:
            logger.error(f"Error exporting approved participants to Excel: {e}")
            return False

    def validate_data(self) -> bool:
        """Validate participant data against Sports Fest rules."""
        logger.info("Starting data validation...")
        wp_participants = self.wordpress_connector.get_participants()
        if not wp_participants:
            logger.warning("No participants found for validation")
            return False

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