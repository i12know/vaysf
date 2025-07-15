# church_teams_export.py
# Version 1.2.0
import pandas as pd
from pathlib import Path
from loguru import logger
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import re

from config import Config, CHECK_BOXES, MEMBERSHIP_QUESTION
from chmeetings.backend_connector import ChMeetingsConnector
from wordpress.frontend_connector import WordPressConnector

class ChurchTeamsExporter: # MODIFIED CLASS NAME
    """
    Generates Excel reports for church team statuses, combining data from
    ChMeetings and WordPress.
    """

    def __init__(self):
        logger.info("Initializing ChurchTeamsExporter...") # MODIFIED LOGGER MESSAGE
        self.chm_connector = ChMeetingsConnector()
        self.wp_connector = WordPressConnector()
        self.sports_fest_date = datetime.strptime(Config.SPORTS_FEST_DATE, "%Y-%m-%d").date()
        self.latest_chm_update_by_church: Dict[str, str] = {} # Initialize here
        logger.info("ChurchTeamsExporter initialized.") # MODIFIED LOGGER MESSAGE

    def _calculate_age(self, birthdate_str: Optional[str]) -> Optional[int]:
        """Calculates age as of the Sports Fest date."""
        if not birthdate_str:
            return None
        try:
            birth_date_obj = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
            age = self.sports_fest_date.year - birth_date_obj.year - \
                  ((self.sports_fest_date.month, self.sports_fest_date.day) < (birth_date_obj.month, birth_date_obj.day))
            return age
        except ValueError:
            logger.warning(f"Invalid birthdate format encountered: '{birthdate_str}' for age calculation.")
            return None

    def _parse_church_code_from_group_name(self, group_name: str) -> Optional[str]:
        """Extracts church code from a ChMeetings group name like 'Team ABC'."""
        if group_name.startswith(Config.TEAM_PREFIX + " "):
            return group_name[len(Config.TEAM_PREFIX + " "):].strip().upper()
        logger.warning(f"Could not parse church code from group name: '{group_name}'")
        return None

    def _get_completion_checklist_statuses(self, checklist_str: Optional[str]) -> Dict[str, str]:
        """Parses the 'Completion Check List' string and returns status for each box."""
        statuses = {f"Box {i+1}": "" for i in range(len(CHECK_BOXES))}
        if not checklist_str:
            return statuses

        for i, (key, text_value) in enumerate(CHECK_BOXES.items()):
            # Ensure we're checking for the full text of the checklist item
            if text_value in checklist_str:
                statuses[f"Box {i+1}"] = text_value # Store the constant text
        return statuses

    def _fetch_chm_church_team_data(self, target_church_code: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches data for all individuals in ChMeetings groups starting with 'Team '.
        Organizes data by church code.
        If target_church_code is specified, only fetches for that church.
        """
        logger.info(f"Fetching ChMeetings data. Target church: {target_church_code or 'ALL'}")
        all_chm_groups = self.chm_connector.get_groups()
        if not all_chm_groups:
            logger.warning("No groups found in ChMeetings.")
            return {}

        chm_data_by_church: Dict[str, List[Dict[str, Any]]] = {}
        # Renamed from latest_chm_update_by_church to avoid conflict with instance variable if used directly
        _latest_chm_update_by_church_dt: Dict[str, Optional[datetime]] = {}


        team_groups = [g for g in all_chm_groups if g.get("name", "").startswith(Config.TEAM_PREFIX + " ")]
        logger.info(f"Found {len(team_groups)} ChMeetings groups with prefix '{Config.TEAM_PREFIX} '.")

        for group in team_groups:
            group_name = group.get("name", "")
            group_id = str(group.get("id"))
            church_code = self._parse_church_code_from_group_name(group_name)

            if not church_code:
                continue

            if target_church_code and church_code != target_church_code.upper():
                continue

            logger.debug(f"Processing ChMeetings group: '{group_name}' (ID: {group_id}, Church: {church_code})")
            chm_data_by_church.setdefault(church_code, [])
            _latest_chm_update_by_church_dt.setdefault(church_code, None)


            group_people_summaries = self.chm_connector.get_group_people(group_id)
            if not group_people_summaries:
                logger.info(f"No people found in ChMeetings group '{group_name}'.")
                continue

            for person_summary in group_people_summaries:
                person_id_str = str(person_summary.get("person_id")) # API uses person_id in group people
                if not person_id_str:
                    logger.warning(f"Missing person_id in summary from group '{group_name}': {person_summary}")
                    continue

                person_details_response = self.chm_connector.get_person(person_id_str)
                if not person_details_response:
                    logger.warning(f"Could not fetch details for ChM Person ID: {person_id_str} from group '{group_name}'.")
                    continue
                
                person_data = person_details_response if isinstance(person_details_response, dict) and "data" not in person_details_response else person_details_response.get("data", {})
                if not person_data:
                    logger.warning(f"Empty person data for ChM Person ID: {person_id_str} from group '{group_name}'.")
                    continue

                chm_id = str(person_data.get("id")) 

                additional_fields = {f.get("field_name"): f.get("value") for f in person_data.get("additional_fields", [])}
                
                updated_on_str = person_data.get("updated_on", "1970-01-01T00:00:00+00:00")
                try:
                    if 'Z' in updated_on_str:
                         updated_on_dt = datetime.fromisoformat(updated_on_str.replace("Z", "+00:00"))
                    elif 'T' in updated_on_str and ('+' in updated_on_str or '-' in updated_on_str[updated_on_str.rfind('T'):]): # Check for timezone info after T
                        updated_on_dt = datetime.fromisoformat(updated_on_str)
                    else: 
                        updated_on_dt = datetime.strptime(updated_on_str, "%Y-%m-%d %H:%M:%S")
                except ValueError as ve:
                    logger.warning(f"Could not parse ChM updated_on '{updated_on_str}' for person {chm_id}: {ve}. Using epoch.")
                    updated_on_dt = datetime.fromisoformat("1970-01-01T00:00:00+00:00")

                current_latest_dt = _latest_chm_update_by_church_dt[church_code]
                if current_latest_dt is None or updated_on_dt > current_latest_dt:
                    _latest_chm_update_by_church_dt[church_code] = updated_on_dt


                mapped_person = {
                    "Church Team": church_code,
                    "ChMeetings ID": chm_id,
                    "First Name": person_data.get("first_name", ""),
                    "Last Name": person_data.get("last_name", ""),
                    "Gender": person_data.get("gender", ""),
                    "Birthdate": person_data.get("birth_date", ""),
                    "Mobile Phone": person_data.get("mobile", ""),
                    "Email": person_data.get("email", "").strip(),
                    "Is_Member_ChM": additional_fields.get(MEMBERSHIP_QUESTION, "No") == "Yes",
                    "ChM_Roles": additional_fields.get("My role is", ""),
                    "ChM_Completion_Checklist": additional_fields.get("Completion Check List", ""),
                    "Update_on_ChM": updated_on_dt.strftime("%Y-%m-%d %H:%M:%S") 
                }
                chm_data_by_church[church_code].append(mapped_person)
        
        self.latest_chm_update_by_church = { # Store on instance
            code: dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "N/A"
            for code, dt in _latest_chm_update_by_church_dt.items()
        }
        
        if target_church_code and not chm_data_by_church.get(target_church_code.upper()):
             logger.warning(f"No ChMeetings group found or no members in group for target church: {target_church_code}")

        logger.info(f"Fetched ChMeetings data for {len(chm_data_by_church)} churches.")
        return chm_data_by_church

    def generate_reports(self, target_church_code: Optional[str], output_dir: Path) -> bool:
        """
        Generates Excel status reports for church teams.
        If target_church_code is provided, generates a single report for that church.
        Otherwise, generates a report for each church and one consolidated "ALL" report.
        """
        if not self.chm_connector.authenticate(): 
            logger.error("ChMeetings authentication failed. Cannot generate reports.")
            return False
        logger.info(f"Starting report generation. Target Church: {target_church_code or 'ALL'}. Output Dir: {output_dir}")

        chm_data_by_church = self._fetch_chm_church_team_data(target_church_code)

        if not chm_data_by_church:
            logger.warning("No data fetched from ChMeetings. No reports will be generated.")
            return True 

        all_contacts_data: List[Dict[str, Any]] = []
        all_rosters_data: List[Dict[str, Any]] = []
        summary_data_list: List[Dict[str, Any]] = []

        churches_to_process_codes = [target_church_code.upper()] if target_church_code else sorted(list(chm_data_by_church.keys()))

        for church_code_iter in churches_to_process_codes:
            if church_code_iter not in chm_data_by_church:
                logger.warning(f"Skipping report for {church_code_iter} as no ChM data was found (e.g., no 'Team {church_code_iter}' group).")
                continue
            
            logger.info(f"Processing data for church: {church_code_iter}")
            church_contacts_rows: List[Dict[str, Any]] = []
            church_rosters_rows: List[Dict[str, Any]] = []

            total_members_chm = len(chm_data_by_church[church_code_iter])
            total_participants_wp = 0
            total_approved_wp = 0
            total_pending_participants_wp = 0 
            total_with_open_errors_wp = 0
            participants_with_errors_set = set() # To count unique participants with errors

            for chm_person in chm_data_by_church[church_code_iter]:
                chm_id = chm_person["ChMeetings ID"]
                
                roles_str = chm_person.get("ChM_Roles", "")
                is_participant_chm = any(role.strip().lower() in ["athlete", "participant", "athlete/participant"] for role in roles_str.split(","))

                wp_participant_id_val = 0
                approval_status_val = "N/A" 
                total_open_errors_val = 0
                first_open_error_desc_val = ""
                photo_url_val = "N/A"

                if is_participant_chm:
                    wp_participants = self.wp_connector.get_participants({"chmeetings_id": chm_id})
                    if wp_participants:
                        wp_participant = wp_participants[0] 
                        wp_participant_id_val = wp_participant.get("participant_id", 0)
                        approval_status_val = wp_participant.get("approval_status", "pending")
                        photo_url_val = wp_participant.get("photo_url", "N/A")
                        total_participants_wp += 1

                        if approval_status_val == "approved":
                            total_approved_wp += 1
                        if approval_status_val in ["pending", "validated", "pending_approval"]:
                            total_pending_participants_wp +=1

                        if wp_participant_id_val:
                            validation_issues = self.wp_connector.get_validation_issues({
                                "participant_id": wp_participant_id_val,
                                "severity": "ERROR",
                                "status": "open"
                            })
                            total_open_errors_val = len(validation_issues)
                            if validation_issues:
                                first_open_error_desc_val = validation_issues[0].get("issue_description", "")
                                participants_with_errors_set.add(wp_participant_id_val)

                            wp_rosters = self.wp_connector.get_rosters({"participant_id": wp_participant_id_val})
                            for roster_entry in wp_rosters:
                                church_rosters_rows.append({
                                    "Church Team": church_code_iter,
                                    "ChMeetings ID": chm_id,
                                    "Participant ID (WP)": wp_participant_id_val,
                                    "Approval_Status (WP)": approval_status_val,
                                    "Is_Member_ChM": chm_person.get("Is_Member_ChM", False),  # ADD THIS LINE
                                    "Photo": f'=IMAGE("{photo_url_val}")' if photo_url_val != "N/A" and photo_url_val.startswith(("http://", "https://")) else "",  # ADD THIS LINE
#NOTE: The above line assumes the Excel engine supports IMAGE formula, which is not standard in pandas and will insert "@" after "="
                                    "First Name": chm_person["First Name"], 
                                    "Last Name": chm_person["Last Name"],
                                    "Gender": chm_person["Gender"],
                                    "Age (at Event)": self._calculate_age(chm_person["Birthdate"]),
                                    "Mobile Phone": chm_person["Mobile Phone"],
                                    "Email": chm_person["Email"],
                                    "sport_type": roster_entry.get("sport_type"),
                                    "sport_gender": roster_entry.get("sport_gender"),
                                    "sport_format": roster_entry.get("sport_format"),
                                    "team_order": roster_entry.get("team_order"),
                                    "partner_name": roster_entry.get("partner_name")
                                })
                    else: 
                        approval_status_val = "Not in WordPress"
                
                checklist_statuses = self._get_completion_checklist_statuses(chm_person.get("ChM_Completion_Checklist"))

                contact_row = {
                    "Church Team": church_code_iter,
                    "ChMeetings ID": chm_id,
                    "First Name": chm_person["First Name"],
                    "Last Name": chm_person["Last Name"],
                    "Is_Participant": "Yes" if is_participant_chm else "No",
                    "Is_Member_ChM": "Yes" if chm_person["Is_Member_ChM"] else "No",
                    "Participant ID (WP)": wp_participant_id_val,
                    "Approval_Status (WP)": approval_status_val,
                    "Total_Open_ERRORs (WP)": total_open_errors_val,
                    "Gender": chm_person["Gender"], 
                    "Birthdate": chm_person["Birthdate"], 
                    "Age (at Event)": self._calculate_age(chm_person["Birthdate"]),
                    "Mobile Phone": chm_person["Mobile Phone"], 
                    "Email": chm_person["Email"], 
                    "First_Open_ERROR_Desc (WP)": first_open_error_desc_val,
                    **checklist_statuses, 
                    "Photo URL (WP)": photo_url_val,
                    "Update_on_ChM": chm_person["Update_on_ChM"]
                }
                church_contacts_rows.append(contact_row)
            
            total_with_open_errors_wp = len(participants_with_errors_set) # Count unique participants

            summary_data_list.append({
                "Church Code": church_code_iter,
                "Total Members (ChM Team Group)": total_members_chm,
                "Total Participants (in WP)": total_participants_wp,
                "Total Approved (WP)": total_approved_wp,
                "Total Pending Approval (WP)": total_pending_participants_wp, 
                "Total Participants w/ Open ERRORs (WP)": total_with_open_errors_wp,
                "Latest ChM Record Update for Team": self.latest_chm_update_by_church.get(church_code_iter, "N/A")
            })
            
            all_contacts_data.extend(church_contacts_rows)
            all_rosters_data.extend(church_rosters_rows)

            if target_church_code: 
                safe_code = "".join(c if c.isalnum() else "_" for c in church_code_iter)
                filename = f"Church_Team_Status_{safe_code}.xlsx"
                self._write_excel_report(output_dir / filename,
                                         [summary_data_list[-1]], 
                                         church_contacts_rows,
                                         church_rosters_rows)
                
        if not target_church_code: 
            for church_code_iter in churches_to_process_codes: # Iterate using the original list of codes
                if church_code_iter not in chm_data_by_church: continue 

                current_church_contacts = [row for row in all_contacts_data if row["Church Team"] == church_code_iter]
                current_church_rosters = [row for row in all_rosters_data if row["Church Team"] == church_code_iter]
                current_church_summary = [s_data for s_data in summary_data_list if s_data["Church Code"] == church_code_iter]

                safe_code = "".join(c if c.isalnum() else "_" for c in church_code_iter)
                filename = f"Church_Team_Status_{safe_code}.xlsx"
                self._write_excel_report(output_dir / filename,
                                         current_church_summary,
                                         current_church_contacts,
                                         current_church_rosters)
            
            all_filename = f"Church_Team_Status_ALL_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
            self._write_excel_report(output_dir / all_filename,
                                     summary_data_list, 
                                     all_contacts_data, 
                                     all_rosters_data)   

        logger.info("Report generation process finished.")
        return True

    def _write_excel_report(self, filepath: Path,
                            summary_rows: List[Dict[str, Any]],
                            contacts_rows: List[Dict[str, Any]],
                            roster_rows: List[Dict[str, Any]]):
        """Writes the collected data to an Excel file with specified tabs and formatting."""
        logger.info(f"Writing Excel report to: {filepath}")
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Summary Tab
                df_summary = pd.DataFrame(summary_rows)
                if not df_summary.empty:
                    summary_cols = [
                        "Church Code", "Total Members (ChM Team Group)", "Total Participants (in WP)",
                        "Total Approved (WP)", "Total Pending Approval (WP)", 
                        "Total Participants w/ Open ERRORs (WP)", "Latest ChM Record Update for Team"
                    ]
                    # Ensure all summary columns exist
                    for col in summary_cols:
                        if col not in df_summary.columns:
                            df_summary[col] = None 
                    df_summary = df_summary.reindex(columns=summary_cols).sort_values(by="Church Code")
                df_summary.to_excel(writer, sheet_name="Summary", index=False)
                logger.debug(f"Summary tab: {len(df_summary)} rows.")

                # Contacts-Status Tab
                df_contacts = pd.DataFrame(contacts_rows)
                if not df_contacts.empty:

                    photo_url_col_name = "Photo URL (WP)"
                    if photo_url_col_name in df_contacts.columns:
                        # Create the hyperlink formula if the URL is not "N/A" and looks like a URL
                        df_contacts[photo_url_col_name] = df_contacts[photo_url_col_name].apply(
                            lambda url: f'=HYPERLINK("{url}", "{url}")' 
                            if isinstance(url, str) and url != "N/A" and (url.startswith("http://") or url.startswith("https://")) 
                            else url # Keep "N/A" or other non-URL values as is
                        )

                    contacts_cols = [
                        "Church Team", "ChMeetings ID", "First Name", "Last Name", "Is_Participant",
                        "Is_Member_ChM", "Participant ID (WP)", "Approval_Status (WP)", 
                        "Total_Open_ERRORs (WP)", "Gender", "Birthdate", "Age (at Event)",
                        "Mobile Phone", "Email", "First_Open_ERROR_Desc (WP)",
                        "Box 1", "Box 2", "Box 3", "Box 4", "Box 5", "Box 6", 
                        photo_url_col_name, "Update_on_ChM"
                    ]
                    for col in contacts_cols: # Ensure all contact columns exist
                        if col not in df_contacts.columns:
                            df_contacts[col] = None
                    df_contacts = df_contacts.reindex(columns=contacts_cols).sort_values(
                        by=["Church Team", "Total_Open_ERRORs (WP)", "Is_Participant", "Last Name", "First Name"],
                        ascending=[True, False, False, True, True]
                    )
                df_contacts.to_excel(writer, sheet_name="Contacts-Status", index=False)
                logger.debug(f"Contacts-Status tab: {len(df_contacts)} rows.")

                # Roster Tab
                df_roster = pd.DataFrame(roster_rows)
                if not df_roster.empty:
                    roster_cols = [
                        "Church Team", "ChMeetings ID", "Participant ID (WP)", "Approval_Status (WP)",
                        "Is_Member_ChM", "Photo",          # ADD THIS LINE
                        "First Name", "Last Name", "Gender", "Age (at Event)", "Mobile Phone", "Email",
                        "sport_type", "sport_gender", "sport_format", "team_order", "partner_name"
                    ]
                    for col in roster_cols: # Ensure all roster columns exist
                        if col not in df_roster.columns:
                            df_roster[col] = None
                    df_roster = df_roster.reindex(columns=roster_cols).sort_values(
                        by=["Church Team", "sport_type", "sport_gender", "Last Name", "First Name", 
                            "Approval_Status (WP)", "sport_format"] # Removed team_order and partner_name from sort if they are often None
                    )
                df_roster.to_excel(writer, sheet_name="Roster", index=False)
                logger.debug(f"Roster tab: {len(df_roster)} rows.")

            logger.info(f"Successfully wrote Excel report: {filepath}")
        except Exception as e:
            logger.error(f"Failed to write Excel file {filepath}: {e}", exc_info=True)

    def close(self):
        """Closes any open connections (if necessary)."""
        logger.info("Closing ChurchTeamsExporter resources.") # MODIFIED LOGGER MESSAGE
        if self.chm_connector:
            self.chm_connector.close()
        logger.info("ChurchTeamsExporter resources closed.") # MODIFIED LOGGER MESSAGE

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

