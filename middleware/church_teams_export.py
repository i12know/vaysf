# church_teams_export.py
# Version 1.4.0
"""Live ChMeetings/WordPress export orchestration (export-church-teams).

Split in Issue #376. This module owns the connectors, the fetch loops, the
per-church aggregation in ``generate_reports`` and the force-resend path.

* Row shaping and the Excel writer live in ``church_teams_report.py``.
* The scheduling hand-off lives in ``church_teams_scheduling.py``, which binds
  ScheduleWorkbookBuilder's methods onto ChurchTeamsExporter. One-way
  dependency: ``schedule_workbook.py`` must never import from any
  church_teams_* module.
"""
import requests
from pathlib import Path
from loguru import logger
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from config import (
    Config,
    APPROVAL_STATUS,
    DATA_DIR,
    CHECK_BOXES,
    CHM_FIELDS,
    EXPORT_COLUMNS,
    MEMBERSHIP_QUESTION,
    RULE_LEVEL,
    VALIDATION_SEVERITY,
    ATHLETE_FEE_STANDARD,
    ATHLETE_FEE_OTHER_EVENTS_ONLY,
    ATHLETE_FEE_LATE,
    REGISTRATION_DEADLINE,
    VENUE_INPUT_FILENAME,
)
from chmeetings.backend_connector import ChMeetingsConnector
from wordpress.frontend_connector import WordPressConnector
from tenacity import RetryError
from time_utils import current_business_date, parse_wordpress_created_at_to_business_date
from church_teams_report import ChurchTeamsReportMixin
from sync.person_aliases import load_person_aliases_for_reader, resolve_chm_id
from church_teams_scheduling import delegate_schedule_workbook_methods

_CHM_UPDATED_ON_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_chm_updated_on(raw_value: Any, chm_id: str) -> datetime:
    """Parse a ChMeetings ``updated_on`` value into a timezone-aware datetime.

    Every return value is aware, so values from different people can always be
    compared. A value with no offset (``2026-04-16T00:00:00`` or
    ``2026-04-03 08:09:10``) is taken as UTC, which leaves its wall-clock
    fields, and so the ``%Y-%m-%d %H:%M:%S`` string built from it, unchanged.
    Missing values fall back to the epoch silently; unparseable ones log a
    warning first.
    """
    if raw_value is None or raw_value == "":
        return _CHM_UPDATED_ON_EPOCH
    try:
        parsed = datetime.fromisoformat(str(raw_value).strip().replace("Z", "+00:00"))
    except ValueError as ve:
        logger.warning(f"Could not parse ChM updated_on '{raw_value}' for person {chm_id}: {ve}. Using epoch.")
        return _CHM_UPDATED_ON_EPOCH
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@delegate_schedule_workbook_methods
class ChurchTeamsExporter(ChurchTeamsReportMixin):
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
        self.last_orphaned_memberships_by_church: Dict[str, int] = {}
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
        group_name = str(group_name or "")
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

    def _fetch_open_validation_issues(self, church_id: Optional[int]) -> List[Dict[str, Any]]:
        """Fetch all open validation issues for one church from WordPress."""
        if not church_id:
            return []

        issues: List[Dict[str, Any]] = []
        current_page = 1
        fetch_per_page = 200

        while True:
            try:
                page_issues = self.wp_connector.get_validation_issues({
                    "church_id": church_id,
                    "status": "open",
                    "page": current_page,
                    "per_page": fetch_per_page,
                })
            except RetryError as exc:
                logger.error(
                    f"WordPress get_validation_issues() failed after all retry attempts "
                    f"for church_id={church_id} page={current_page}: {exc}. "
                    "Returning partial results."
                )
                break
            if not page_issues:
                break

            issues.extend(page_issues)
            if len(page_issues) < fetch_per_page:
                break

            current_page += 1
            if current_page > 50:
                logger.warning(
                    f"Reached validation-issue page limit while exporting church_id={church_id}. "
                    "Stopping after 50 pages."
                )
                break

        return issues

    def _fetch_chm_church_team_data(self, target_church_code: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches data for all individuals in ChMeetings groups starting with 'Team '.
        Organizes data by church code.
        If target_church_code is specified, only fetches for that church.
        """
        logger.info(f"Fetching ChMeetings data. Target church: {target_church_code or 'ALL'}")
        self.last_orphaned_memberships_by_church = {}
        all_chm_groups = self.chm_connector.get_groups()
        if not all_chm_groups:
            logger.warning("No groups found in ChMeetings.")
            return {}

        chm_data_by_church: Dict[str, List[Dict[str, Any]]] = {}
        # Renamed from latest_chm_update_by_church to avoid conflict with instance variable if used directly
        _latest_chm_update_by_church_dt: Dict[str, Optional[datetime]] = {}
        orphaned_ids_by_church: Dict[str, List[str]] = {}


        team_groups = [
            g for g in all_chm_groups
            if str(g.get("name") or "").startswith(Config.TEAM_PREFIX + " ")
        ]
        logger.info(f"Found {len(team_groups)} ChMeetings groups with prefix '{Config.TEAM_PREFIX} '.")

        # Team groups are never edited by apply-aliases, so member IDs are
        # resolved through the person alias map and de-duplicated per church,
        # the same way the participant sync loop does. Without this, a stale ID
        # that never had a WordPress row is listed and billed as an athlete, and
        # a canonical person reached only through a stale membership is missed.
        person_aliases = load_person_aliases_for_reader("export-church-teams")
        seen_ids_by_church: Dict[str, set] = {}

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
                raw_person_id = person_summary.get("person_id")  # API uses person_id in group people
                person_id_str = str(raw_person_id).strip() if raw_person_id is not None else ""
                if not person_id_str:
                    logger.warning(f"Missing person_id in summary from group '{group_name}': {person_summary}")
                    continue

                canonical_id = resolve_chm_id(person_id_str, person_aliases)
                if canonical_id != person_id_str:
                    logger.info(
                        f"[VAY SM] Alias: stale chm_id {person_id_str} in '{group_name}' "
                        f"resolved to {canonical_id} for export"
                    )
                    person_id_str = canonical_id
                seen_ids = seen_ids_by_church.setdefault(church_code, set())
                if person_id_str in seen_ids:
                    logger.info(
                        f"[VAY SM] Skipping duplicate Team-group membership for "
                        f"canonical chm_id={person_id_str} in church {church_code}"
                    )
                    continue
                seen_ids.add(person_id_str)

                person_details_response = self.chm_connector.get_person(person_id_str)
                if not person_details_response:
                    if getattr(self.chm_connector, "last_get_person_status", None) == "not_found":
                        orphaned_ids_by_church.setdefault(church_code, []).append(person_id_str)
                    else:
                        logger.warning(
                            f"Could not fetch details for ChM Person ID: {person_id_str} "
                            f"from group '{group_name}'."
                        )
                    continue
                
                person_data = person_details_response if isinstance(person_details_response, dict) and "data" not in person_details_response else person_details_response.get("data", {})
                if not person_data:
                    logger.warning(f"Empty person data for ChM Person ID: {person_id_str} from group '{group_name}'.")
                    continue

                chm_id = str(person_data.get("id")) 

                additional_fields = {f.get("field_name"): f.get("value") for f in person_data.get("additional_fields", [])}
                
                updated_on_dt = _parse_chm_updated_on(person_data.get("updated_on"), chm_id)

                current_latest_dt = _latest_chm_update_by_church_dt[church_code]
                if current_latest_dt is None or updated_on_dt > current_latest_dt:
                    _latest_chm_update_by_church_dt[church_code] = updated_on_dt

                mapped_person = {
                    EXPORT_COLUMNS["CHURCH_TEAM"]: church_code,
                    "ChMeetings ID": chm_id,
                    EXPORT_COLUMNS["FIRST_NAME"]: person_data.get("first_name", ""),
                    EXPORT_COLUMNS["LAST_NAME"]: person_data.get("last_name", ""),
                    "Gender": person_data.get("gender", ""),
                    "Birthdate": person_data.get("birth_date", ""),
                    "Mobile Phone": person_data.get("mobile", ""),
                    "Email": str(person_data.get("email") or "").strip(),
                    "Is_Member_ChM": additional_fields.get(MEMBERSHIP_QUESTION, "No") == "Yes",
                    "ChM_Roles": additional_fields.get(CHM_FIELDS["ROLES"], ""),
                    "ChM_Completion_Checklist": additional_fields.get(CHM_FIELDS["COMPLETION_CHECKLIST"], ""),
                    "ChM_Primary_Sport": additional_fields.get(CHM_FIELDS["PRIMARY_SPORT"], ""),
                    "ChM_Primary_Format": additional_fields.get(CHM_FIELDS["PRIMARY_FORMAT"], ""),
                    "ChM_Secondary_Sport": additional_fields.get(CHM_FIELDS["SECONDARY_SPORT"], ""),
                    "ChM_Secondary_Format": additional_fields.get(CHM_FIELDS["SECONDARY_FORMAT"], ""),
                    "ChM_Other_Events": additional_fields.get(CHM_FIELDS["OTHER_EVENTS"], ""),
                    "Update_on_ChM": updated_on_dt.strftime("%Y-%m-%d %H:%M:%S") 
                }
                chm_data_by_church[church_code].append(mapped_person)
        
        self.latest_chm_update_by_church = { # Store on instance
            code: dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "N/A"
            for code, dt in _latest_chm_update_by_church_dt.items()
        }
        self.last_orphaned_memberships_by_church = {
            code: len(ids) for code, ids in orphaned_ids_by_church.items()
        }

        total_orphaned_memberships = sum(len(ids) for ids in orphaned_ids_by_church.values())
        if total_orphaned_memberships:
            for church_code, ids in sorted(orphaned_ids_by_church.items()):
                logger.warning(
                    f"Team {church_code}: skipped {len(ids)} orphaned member ID(s) — "
                    f"[{', '.join(ids)}]"
                )
            logger.warning(
                f"Skipped {total_orphaned_memberships} orphaned Team-group membership(s) "
                f"across {len(orphaned_ids_by_church)} church(es). "
                "Run 'python main.py audit-team-groups' to clean up."
            )
        
        if target_church_code and not chm_data_by_church.get(target_church_code.upper()):
             logger.warning(f"No ChMeetings group found or no members in group for target church: {target_church_code}")

        logger.info(f"Fetched ChMeetings data for {len(chm_data_by_church)} churches.")
        return chm_data_by_church

    def generate_reports(self, target_church_code: Optional[str], output_dir: Path,
                        force_resend_pending: bool = False, force_resend_validated1: bool = False, 
                        force_resend_validated2: bool = False, dry_run: bool = False,
                        target_resend_chm_id: Optional[str] = None) -> bool:
        """
        Generates Excel status reports for church teams.
        If target_church_code is provided, generates a single report for that church.
        Otherwise, generates a report for each church and one consolidated "ALL" report.
        Furthermore, the flags force_resend_pending, force_resend_validated1, and force_resend_validated2
        control whether to resend pastoral approval for participants with approval pending, validated1 (under church rep's review),
        and validated2 (no review yet).
        If target_resend_chm_id is provided, resend actions are limited to that participant.
        Dry run mode does not send the email yet but note the actions would be taken.
        """
        if not self.chm_connector.authenticate():
            logger.error("ChMeetings authentication failed. Cannot generate reports.")
            return False

        if (
            target_resend_chm_id
            and not target_church_code
            and (force_resend_pending or force_resend_validated1 or force_resend_validated2)
        ):
            wp_participants = self.wp_connector.get_participants(
                {"chmeetings_id": str(target_resend_chm_id).strip()}
            )
            if wp_participants:
                inferred_church_code = str(wp_participants[0].get("church_code", "")).strip().upper()
                if inferred_church_code:
                    target_church_code = inferred_church_code
                    logger.info(
                        f"Inferred target church '{target_church_code}' for resend ChMeetings ID "
                        f"{target_resend_chm_id}. Limiting report generation to that church."
                    )
                else:
                    logger.warning(
                        f"Target resend ChMeetings ID {target_resend_chm_id} has no church_code in WordPress. "
                        "Falling back to all churches."
                    )
            else:
                logger.warning(
                    f"Could not find WordPress participant for resend ChMeetings ID {target_resend_chm_id}. "
                    "Falling back to all churches."
                )

        deadline_date = datetime.strptime(REGISTRATION_DEADLINE, "%Y-%m-%d").date()
        today = current_business_date()
        # Use > (not >=) so the deadline date itself is the last early-bird day;
        # late fee applies starting the day after (e.g. deadline 2026-05-16 -> late from 2026-05-17).
        if today > deadline_date:
            fee_tier = f"LATE (${ATHLETE_FEE_LATE}, past deadline {REGISTRATION_DEADLINE})"
        else:
            fee_tier = f"STANDARD (${ATHLETE_FEE_STANDARD} early-bird, deadline {REGISTRATION_DEADLINE})"
        logger.info(f"Athlete fee tier: {fee_tier}")

        logger.info(f"Starting report generation. Target Church: {target_church_code or 'ALL'}. Output Dir: {output_dir}")

        chm_data_by_church = self._fetch_chm_church_team_data(target_church_code)

        if not chm_data_by_church:
            logger.warning("No data fetched from ChMeetings. No reports will be generated.")
            return True 

        all_contacts_data: List[Dict[str, Any]] = []
        all_rosters_data: List[Dict[str, Any]] = []
        all_validation_data: List[Dict[str, Any]] = []
        summary_data_list: List[Dict[str, Any]] = []
        _wp_church_fetch_failures = 0
        _wp_participant_fetch_failures = 0
        _wp_roster_fetch_failures = 0

        churches_to_process_codes = [target_church_code.upper()] if target_church_code else sorted(list(chm_data_by_church.keys()))

        for church_code_iter in churches_to_process_codes:
            if church_code_iter not in chm_data_by_church:
                logger.warning(f"Skipping report for {church_code_iter} as no ChM data was found (e.g., no 'Team {church_code_iter}' group).")
                continue
            
            logger.info(f"Processing data for church: {church_code_iter}")
            church_contacts_rows: List[Dict[str, Any]] = []
            church_rosters_rows: List[Dict[str, Any]] = []
            church_validation_rows: List[Dict[str, Any]] = []
            participants_by_wp_id: Dict[str, Dict[str, Any]] = {}

            total_members_chm = len(chm_data_by_church[church_code_iter])
            total_participants_wp = 0
            total_approved_wp = 0
            total_denied_wp = 0
            total_pending_participants_wp = 0
            total_with_open_errors_wp = 0
            total_athlete_fees = 0
            try:
                church_wp = self.wp_connector.get_church_by_code(church_code_iter)
            except RetryError as exc:
                _wp_church_fetch_failures += 1
                logger.error(
                    f"WP church fetch failed for church code {church_code_iter} after all retries: {exc}"
                )
                church_wp = None
            except requests.RequestException as exc:
                _wp_church_fetch_failures += 1
                logger.error(
                    f"WP church fetch failed for church code {church_code_iter}: {exc}"
                )
                church_wp = None
            church_wp_id = church_wp.get("church_id") if church_wp else None
            open_validation_issues = self._fetch_open_validation_issues(church_wp_id)
            participant_error_lookup: Dict[str, List[Dict[str, Any]]] = {}
            team_validation_issues = [
                issue for issue in open_validation_issues
                if self._issue_rule_level(issue) == RULE_LEVEL["TEAM"]
            ]

            for issue in open_validation_issues:
                participant_id = issue.get("participant_id")
                if participant_id in (None, "", 0, "0"):
                    continue
                if self._issue_severity(issue) != VALIDATION_SEVERITY["ERROR"]:
                    continue
                participant_error_lookup.setdefault(str(participant_id), []).append(issue)

            for chm_person in chm_data_by_church[church_code_iter]:
                chm_id = chm_person["ChMeetings ID"]

                roles_str = chm_person.get("ChM_Roles", "")
                is_participant_chm = any(role.strip().lower() in ["athlete", "participant", "athlete/participant"] for role in roles_str.split(","))

                wp_participant_id_val = 0
                approval_status_val = "N/A"
                total_open_errors_val = 0
                first_open_error_desc_val = ""
                photo_url_val = "N/A"
                wp_created_at_str = ""

                if is_participant_chm:
                    try:
                        wp_participants = self.wp_connector.get_participants({"chmeetings_id": chm_id})
                    except RetryError as exc:
                        _wp_participant_fetch_failures += 1
                        logger.error(
                            f"WP participant fetch failed for CHM ID {chm_id} after all retries: {exc}"
                        )
                        wp_participants = []
                    except requests.RequestException as exc:
                        _wp_participant_fetch_failures += 1
                        logger.error(
                            f"WP participant fetch failed for CHM ID {chm_id}: {exc}"
                        )
                        wp_participants = []
                    if wp_participants:
                        wp_participant = wp_participants[0]
                        wp_participant_id_val = wp_participant.get("participant_id", 0)
                        approval_status_val = wp_participant.get("approval_status", "pending")
                        if approval_status_val == APPROVAL_STATUS["MERGED"]:
                            logger.info(
                                f"Skipping merged participant chm_id={chm_id} "
                                f"from church-team export"
                            )
                            continue
                        photo_url_val = wp_participant.get("photo_url", "N/A")
                        wp_created_at_str = wp_participant.get("created_at", "")
                        participant_issue_list = participant_error_lookup.get(str(wp_participant_id_val), [])
                        total_participants_wp += 1

                        if approval_status_val == "approved":
                            total_approved_wp += 1
                        if approval_status_val == "denied": # ADD THIS BLOCK
                            total_denied_wp += 1
                        if approval_status_val in ["pending", "validated", "pending_approval"]:
                            total_pending_participants_wp +=1

                        if wp_participant_id_val:
                            total_open_errors_val = len(participant_issue_list)
                            if participant_issue_list:
                                first_open_error_desc_val = participant_issue_list[0].get("issue_description", "")

                            participants_by_wp_id[str(wp_participant_id_val)] = {
                                "ChMeetings ID": chm_id,
                                EXPORT_COLUMNS["FIRST_NAME"]: chm_person[EXPORT_COLUMNS["FIRST_NAME"]],
                                EXPORT_COLUMNS["LAST_NAME"]: chm_person[EXPORT_COLUMNS["LAST_NAME"]],
                                "Approval_Status (WP)": approval_status_val,
                            }
                            try:
                                wp_rosters = self.wp_connector.get_rosters({"participant_id": wp_participant_id_val})
                            except RetryError as exc:
                                _wp_roster_fetch_failures += 1
                                logger.error(
                                    f"WP roster fetch failed for participant {wp_participant_id_val} "
                                    f"(CHM ID {chm_id}) after all retries: {exc}"
                                )
                                wp_rosters = []
                            except requests.RequestException as exc:
                                _wp_roster_fetch_failures += 1
                                logger.error(
                                    f"WP roster fetch failed for participant {wp_participant_id_val} "
                                    f"(CHM ID {chm_id}): {exc}"
                                )
                                wp_rosters = []
                            for roster_entry in wp_rosters:
                                matching_team_issues = [
                                    issue for issue in team_validation_issues
                                    if self._team_issue_matches_roster(issue, roster_entry)
                                ]
                                church_rosters_rows.append({
                                    EXPORT_COLUMNS["CHURCH_TEAM"]: church_code_iter,
                                    "ChMeetings ID": chm_id,
                                    "Participant ID (WP)": wp_participant_id_val,
                                    "Approval_Status (WP)": approval_status_val,
                                    "Is_Member_ChM": chm_person.get("Is_Member_ChM", False),  # ADD THIS LINE
                                    "Photo": self._excel_image_formula(photo_url_val),  # ADD THIS LINE
#NOTE: The above line assumes the Excel engine supports IMAGE formula, which is not standard in pandas and will insert "@" after "="
                                    EXPORT_COLUMNS["FIRST_NAME"]: chm_person[EXPORT_COLUMNS["FIRST_NAME"]],
                                    EXPORT_COLUMNS["LAST_NAME"]: chm_person[EXPORT_COLUMNS["LAST_NAME"]],
                                    "Gender": chm_person["Gender"],
                                    "Age (at Event)": self._calculate_age(chm_person["Birthdate"]),
                                    "Mobile Phone": chm_person["Mobile Phone"],
                                    "Email": chm_person["Email"],
                                    "participant_primary_sport": chm_person.get("ChM_Primary_Sport", ""),
                                    "participant_primary_format": chm_person.get("ChM_Primary_Format", ""),
                                    "participant_secondary_sport": chm_person.get("ChM_Secondary_Sport", ""),
                                    "participant_secondary_format": chm_person.get("ChM_Secondary_Format", ""),
                                    "participant_other_events": chm_person.get("ChM_Other_Events", ""),
                                    "sport_type": roster_entry.get("sport_type"),
                                    "sport_gender": roster_entry.get("sport_gender"),
                                    "sport_format": roster_entry.get("sport_format"),
                                    "team_order": roster_entry.get("team_order"),
                                    "partner_name": roster_entry.get("partner_name"),
                                    "Open_TEAM_Issue_Count (WP)": len(matching_team_issues),
                                    "Open_TEAM_Issue_Desc (WP)": " | ".join(
                                        str(issue.get("issue_description", "")).strip()
                                        for issue in matching_team_issues
                                        if str(issue.get("issue_description", "")).strip()
                                    ),
                                })
                    else: 
                        approval_status_val = "Not in WordPress"
                
                checklist_statuses = self._get_completion_checklist_statuses(chm_person.get("ChM_Completion_Checklist"))

                registration_date_str = ""
                if is_participant_chm:
                    _primary = chm_person.get("ChM_Primary_Sport", "")
                    _secondary = chm_person.get("ChM_Secondary_Sport", "")
                    _other = chm_person.get("ChM_Other_Events", "")

                    if wp_created_at_str:
                        try:
                            created_date = parse_wordpress_created_at_to_business_date(
                                wp_created_at_str
                            )
                            if created_date is None:
                                raise ValueError("Could not parse WordPress created_at into business date")
                            registration_date_str = created_date.strftime("%Y-%m-%d")
                            deadline_date = datetime.strptime(REGISTRATION_DEADLINE, "%Y-%m-%d").date()

                            if not _primary and not _secondary and _other:
                                athlete_fee = ATHLETE_FEE_OTHER_EVENTS_ONLY
                            # Use > (not >=) so the deadline date itself is the last early-bird day;
                            # late fee applies starting the day after (e.g. deadline 2026-05-16 -> late from 2026-05-17).
                            elif created_date > deadline_date:
                                athlete_fee = ATHLETE_FEE_LATE
                            else:
                                athlete_fee = ATHLETE_FEE_STANDARD
                        except (ValueError, AttributeError):
                            athlete_fee = (
                                ATHLETE_FEE_OTHER_EVENTS_ONLY
                                if (not _primary and not _secondary and _other)
                                else ATHLETE_FEE_STANDARD
                            )
                    else:
                        athlete_fee = (
                            ATHLETE_FEE_OTHER_EVENTS_ONLY
                            if (not _primary and not _secondary and _other)
                            else ATHLETE_FEE_STANDARD
                        )
                    total_athlete_fees += athlete_fee
                else:
                    athlete_fee = ""

                contact_row = {
                    EXPORT_COLUMNS["CHURCH_TEAM"]: church_code_iter,
                    "ChMeetings ID": chm_id,
                    EXPORT_COLUMNS["FIRST_NAME"]: chm_person[EXPORT_COLUMNS["FIRST_NAME"]],
                    EXPORT_COLUMNS["LAST_NAME"]: chm_person[EXPORT_COLUMNS["LAST_NAME"]],
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
                    "Registration Date (WP)": registration_date_str,
                    "Athlete Fee": athlete_fee,
                    "First_Open_ERROR_Desc (WP)": first_open_error_desc_val,
                    **checklist_statuses,
                    "Photo URL (WP)": photo_url_val,
                    "Update_on_ChM": chm_person["Update_on_ChM"]
                }
                church_contacts_rows.append(contact_row)

            reverse_partner_suggestions = self._merge_reverse_partner_suggestions(
                self._build_reverse_partner_suggestion_lookup(church_rosters_rows),
                self._build_issue_based_reverse_partner_suggestion_lookup(
                    open_validation_issues,
                    participants_by_wp_id,
                ),
            )

            reportable_validation_issues = self._filter_reportable_validation_issues(
                church_code_iter,
                open_validation_issues,
                participants_by_wp_id,
            )
            reportable_team_validation_issues = [
                issue for issue in reportable_validation_issues
                if self._issue_rule_level(issue) == RULE_LEVEL["TEAM"]
            ]

            church_validation_rows = self._build_validation_issue_rows(
                church_code_iter,
                reportable_validation_issues,
                participants_by_wp_id,
                reverse_partner_suggestions,
            )

            individual_open_errors = [
                issue for issue in reportable_validation_issues
                if self._issue_rule_level(issue) == RULE_LEVEL["INDIVIDUAL"]
                and self._issue_severity(issue) == VALIDATION_SEVERITY["ERROR"]
            ]
            team_open_errors = [
                issue for issue in reportable_team_validation_issues
                if self._issue_severity(issue) == VALIDATION_SEVERITY["ERROR"]
            ]
            open_warnings = [
                issue for issue in reportable_validation_issues
                if self._issue_severity(issue) == VALIDATION_SEVERITY["WARNING"]
            ]
            participant_ids_with_errors = {
                str(issue.get("participant_id"))
                for issue in individual_open_errors
                if issue.get("participant_id") not in (None, "", 0, "0")
            }
            total_with_open_errors_wp = len(participant_ids_with_errors)
            total_sports_with_team_issues = len({
                self._team_issue_scope_key(issue)
                for issue in team_validation_issues
            })

            summary_data_list.append({
                "Church Code": church_code_iter,
                "Total Members (ChM Team Group)": total_members_chm,
                "Total Participants (in WP)": total_participants_wp,
                "Total Approved (WP)": total_approved_wp,
                "Total Denied (WP)": total_denied_wp,
                "Total Pending Approval (WP)": total_pending_participants_wp,
                "Total Participants w/ Open ERRORs (WP)": total_with_open_errors_wp,
                "Total Open Individual ERRORs (WP)": len(individual_open_errors),
                "Total Open TEAM ERRORs (WP)": len(team_open_errors),
                "Total Open WARNINGs (WP)": len(open_warnings),
                "Total Sports w/ Open TEAM Issues (WP)": total_sports_with_team_issues,
                "Total Athlete Fees": total_athlete_fees,
                "Latest ChM Record Update for Team": self.latest_chm_update_by_church.get(church_code_iter, "N/A")
            })
            
            all_contacts_data.extend(church_contacts_rows)
            all_rosters_data.extend(church_rosters_rows)
            all_validation_data.extend(church_validation_rows)

            if target_church_code: 
                safe_code = "".join(c if c.isalnum() else "_" for c in church_code_iter)
                filename = f"Church_Team_Status_{safe_code}.xlsx"
                self._write_excel_report(output_dir / filename,
                                         [summary_data_list[-1]], 
                                         church_contacts_rows,
                                         church_rosters_rows,
                                         church_validation_rows)
                
        if not target_church_code: 
            for church_code_iter in churches_to_process_codes: # Iterate using the original list of codes
                if church_code_iter not in chm_data_by_church: continue 

                current_church_contacts = [row for row in all_contacts_data if row[EXPORT_COLUMNS["CHURCH_TEAM"]] == church_code_iter]
                current_church_rosters = [row for row in all_rosters_data if row[EXPORT_COLUMNS["CHURCH_TEAM"]] == church_code_iter]
                current_church_validation = [row for row in all_validation_data if row[EXPORT_COLUMNS["CHURCH_TEAM"]] == church_code_iter]
                current_church_summary = [s_data for s_data in summary_data_list if s_data["Church Code"] == church_code_iter]

                safe_code = "".join(c if c.isalnum() else "_" for c in church_code_iter)
                filename = f"Church_Team_Status_{safe_code}.xlsx"
                self._write_excel_report(output_dir / filename,
                                         current_church_summary,
                                         current_church_contacts,
                                         current_church_rosters,
                                         current_church_validation)
            
            all_filename = f"Church_Team_Status_ALL_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
            self._write_excel_report(output_dir / all_filename,
                                     summary_data_list,
                                     all_contacts_data,
                                     all_rosters_data,
                                     all_validation_data,
                                     include_venue_capacity=True)

        # Handle force resend options
        if force_resend_pending or force_resend_validated1 or force_resend_validated2:
            resend_count = self._handle_force_resend(
                all_contacts_data, force_resend_pending, force_resend_validated1, 
                force_resend_validated2, dry_run, target_resend_chm_id=target_resend_chm_id
            )
            logger.info(f"Force resend completed. Total emails {'would be sent' if dry_run else 'sent'}: {resend_count}")
        
        if _wp_church_fetch_failures or _wp_participant_fetch_failures or _wp_roster_fetch_failures:
            logger.warning(
                f"Export finished with transient WordPress fetch failures: "
                f"{_wp_church_fetch_failures} church fetch(es), "
                f"{_wp_participant_fetch_failures} participant fetch(es), and "
                f"{_wp_roster_fetch_failures} roster fetch(es) exhausted all retries. "
                "Output may be incomplete — re-run export to recover missing rows."
            )
        logger.info("Report generation process finished.")
        return True

    def _handle_force_resend(self, contacts_data: List[Dict[str, Any]], 
                            force_pending: bool, force_validated1: bool, force_validated2: bool,
                            dry_run: bool, target_resend_chm_id: Optional[str] = None) -> int:
        """Handle force resend based on participant categories."""
        
        from sync.manager import SyncManager  # Import here to avoid circular imports
        
        participants_to_resend = []
        
        for contact in contacts_data:
            approval_status = contact.get("Approval_Status (WP)", "").lower()
            
            # Category 1: Pending participants, including identity-drift reapproval.
            if force_pending and approval_status in ["pending", "pending_approval", "reapproval_required"]:
                participants_to_resend.append(contact)
                logger.debug(
                    f"Added pending participant: {contact.get(EXPORT_COLUMNS['FIRST_NAME'])} "
                    f"{contact.get(EXPORT_COLUMNS['LAST_NAME'])} ({contact.get(EXPORT_COLUMNS['CHURCH_TEAM'])})"
                )
                
            # Category 2 & 3: Validated participants  
            elif approval_status == "validated":
                # Check Box 1-6 data to categorize
                has_box_data = any(contact.get(f"Box {i}", "") for i in range(1, 7))
                
                if force_validated1 and has_box_data:
                    # Under review by church rep
                    participants_to_resend.append(contact)
                    logger.debug(
                        f"Added validated-under-review participant: {contact.get(EXPORT_COLUMNS['FIRST_NAME'])} "
                        f"{contact.get(EXPORT_COLUMNS['LAST_NAME'])} ({contact.get(EXPORT_COLUMNS['CHURCH_TEAM'])})"
                    )
                elif force_validated2 and not has_box_data:
                    # Not reviewed yet by church rep
                    participants_to_resend.append(contact)
                    logger.debug(
                        f"Added validated-not-reviewed participant: {contact.get(EXPORT_COLUMNS['FIRST_NAME'])} "
                        f"{contact.get(EXPORT_COLUMNS['LAST_NAME'])} ({contact.get(EXPORT_COLUMNS['CHURCH_TEAM'])})"
                    )

        if target_resend_chm_id:
            normalized_target = str(target_resend_chm_id).strip()
            participants_to_resend = [
                contact
                for contact in participants_to_resend
                if str(contact.get("ChMeetings ID", "")).strip() == normalized_target
            ]
            logger.info(
                f"Applied resend filter for ChMeetings ID {normalized_target}. "
                f"Matching participants: {len(participants_to_resend)}"
            )
        
        logger.info(f"Found {len(participants_to_resend)} participants matching criteria")
        
        if dry_run:
            logger.info("DRY RUN - Would resend emails to:")
            
            # Load churches cache to get email addresses for dry run preview
            temp_sync_manager = SyncManager()
            with temp_sync_manager:
                # Load churches cache
                wp_churches = temp_sync_manager.wordpress_connector.get_churches()
                if wp_churches:
                    churches_cache = {c["church_code"]: c for c in wp_churches}
                else:
                    logger.error("Failed to load churches for dry-run preview")
                    return len(participants_to_resend)
                
                for p in participants_to_resend:
                    participant_name = f"{p.get(EXPORT_COLUMNS['FIRST_NAME'])} {p.get(EXPORT_COLUMNS['LAST_NAME'])}"
                    church_code = p.get(EXPORT_COLUMNS['CHURCH_TEAM'])
                    participant_email = p.get('Email', 'N/A')
                    status = p.get('Approval_Status (WP)')
                    
                    # Get church details for email preview
                    if church_code in churches_cache:
                        church = churches_cache[church_code]
                        pastor_email = church.get('pastor_email', 'N/A')
                        church_rep_email = church.get('church_rep_email', 'N/A')
                        
                        logger.info(f"  {participant_name} ({church_code}) - Status: {status}")
                        logger.info(f"    -> Pastor approval email TO: {pastor_email}")
                        logger.info(f"    -> Participant notification TO: {participant_email}")
                        if church_rep_email != 'N/A':
                            logger.info(f"    -> Church rep CC: {church_rep_email}")
                        logger.info("")  # Empty line for readability
                    else:
                        logger.info(f"  {participant_name} ({church_code}) - Status: {status}")
                        logger.error(f"    -> ERROR: Church {church_code} not found in cache!")
                        logger.info("")
            
            return len(participants_to_resend)
        
        # Actually send the emails
        sync_manager = SyncManager()
        with sync_manager:
            success_count = 0
            for participant_contact in participants_to_resend:
                wp_participant_id = participant_contact.get("Participant ID (WP)")
                if wp_participant_id and self._resend_approval_for_participant(sync_manager, participant_contact):
                    success_count += 1
                    logger.info(
                        f"Resent approval email for {participant_contact.get(EXPORT_COLUMNS['FIRST_NAME'])} "
                        f"{participant_contact.get(EXPORT_COLUMNS['LAST_NAME'])}"
                    )
                else:
                    logger.error(
                        f"Failed to resend for {participant_contact.get(EXPORT_COLUMNS['FIRST_NAME'])} "
                        f"{participant_contact.get(EXPORT_COLUMNS['LAST_NAME'])}"
                    )
        
        return success_count


    # In church_teams_export.py, update both methods:
    def _resend_approval_for_participant(self, sync_manager, participant_contact: Dict[str, Any]) -> bool:
        """Resend approval email for a specific participant using contact data."""
        try:
            # Extract data from contact
            wp_participant_id = participant_contact.get("Participant ID (WP)")
            first_name = participant_contact.get(EXPORT_COLUMNS["FIRST_NAME"], "")
            last_name = participant_contact.get(EXPORT_COLUMNS["LAST_NAME"], "")
            church_team = participant_contact.get(EXPORT_COLUMNS["CHURCH_TEAM"], "")
            chm_id = participant_contact.get("ChMeetings ID", "")
            email = participant_contact.get("Email", "")
            
            if not wp_participant_id:
                logger.error(f"No WordPress participant ID found for {first_name} {last_name}")
                return False
            
            # Ensure churches cache is loaded
            if not sync_manager.churches_cache:
                logger.info("Loading churches cache for resend operation...")
                wp_churches = sync_manager.wordpress_connector.get_churches()
                if wp_churches:
                    sync_manager.churches_cache = {c["church_code"]: c for c in wp_churches}
                else:
                    logger.error("Failed to load churches cache")
                    return False
            
            church_code = church_team
            if not church_code or church_code not in sync_manager.churches_cache:
                logger.error(f"Church {church_code} not found for participant {first_name} {last_name}")
                return False
            
            church = sync_manager.churches_cache[church_code]
            pastor_email = church.get("pastor_email")
            if not pastor_email:
                logger.error(f"No pastor email for church {church_code}")
                return False

            existing_approvals = sync_manager.wordpress_connector.get_approvals(
                params={"participant_id": wp_participant_id}
            )
            existing_approval = next(
                (
                    approval for approval in existing_approvals
                    if str(approval.get("church_id")) == str(church.get("church_id"))
                ),
                None,
            )
            
            # Generate new token and expiry
            from uuid import uuid4
            import datetime
            from config import Config
            
            token = str(uuid4())
            expiry_date = datetime.datetime.now() + datetime.timedelta(days=Config.TOKEN_EXPIRY_DAYS)
            
            # Prepare approval data for CREATE endpoint (which now handles UNIQUE constraint properly)
            church_wp_id = church["church_id"]
            approval_data = {
                "participant_id": wp_participant_id,
                "church_id": church_wp_id,
                "approval_token": token,
                "token_expiry": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                "pastor_email": pastor_email,
                "approval_status": "pending",
                "synced_to_chmeetings": False
            }
            
            # Use CREATE endpoint (which now handles UNIQUE constraint with INSERT ... ON DUPLICATE KEY UPDATE)
            logger.info(f"Creating/updating approval record for participant {wp_participant_id} via CREATE endpoint")
            
            result = sync_manager.wordpress_connector.create_approval(approval_data)
            
            if not result:
                logger.error(f"Failed to create/update approval record for participant {wp_participant_id}")
                return False
            
            logger.info(f"Successfully created/updated approval record for participant {wp_participant_id}")
            
            # Build participant data for email
            participant_data = {
                "participant_id": wp_participant_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "church_code": church_code,
                "chmeetings_id": chm_id,
                "is_church_member": participant_contact.get("Is_Member_ChM", "No") == "Yes",
                "photo_url": participant_contact.get("Photo URL (WP)", "")
            }
            
            # Send approval email
            participant_name = f"{first_name} {last_name}"
            success = sync_manager.send_pastor_approval_email(
                pastor_email, participant_name, token, participant_data, expiry_date
            )
            
            if success:
                if existing_approval:
                    logger.info(
                        "Existing approval record before resend for "
                        f"{participant_name} (WP ID: {wp_participant_id}): "
                        f"approval_id={existing_approval.get('approval_id')}, "
                        f"created_at={existing_approval.get('created_at', 'N/A')}, "
                        f"status={existing_approval.get('approval_status', 'N/A')}, "
                        f"token_expiry={existing_approval.get('token_expiry', 'N/A')}, "
                        f"pastor_email={existing_approval.get('pastor_email', 'N/A')}"
                    )
                logger.info(f"Successfully resent approval email for {participant_name} (ID: {wp_participant_id})")
                return True
            else:
                logger.error(f"Failed to send approval email for {participant_name} (ID: {wp_participant_id})")
                return False
            
        except Exception as e:
            logger.error(
                f"Error resending approval for participant {participant_contact.get(EXPORT_COLUMNS['FIRST_NAME'])} "
                f"{participant_contact.get(EXPORT_COLUMNS['LAST_NAME'])}: {e}",
                exc_info=True,
            )
            return False

    def _venue_input_path(self) -> Path:
        """Location of the operator's venue_input.xlsx, read for the consolidated export."""
        return DATA_DIR / VENUE_INPUT_FILENAME

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

# end of the ChurchTeamsExporter class
# end of the middleware/church_teams_export.py file
