# church_teams_export.py
# Version 1.2.0
import pandas as pd
from pathlib import Path
from loguru import logger
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import re
import unicodedata

from config import (
    Config,
    CHECK_BOXES,
    CHM_FIELDS,
    MEMBERSHIP_QUESTION,
    FORMAT_MAPPINGS,
    RULE_LEVEL,
    VALIDATION_SEVERITY,
    ATHLETE_FEE_STANDARD,
    ATHLETE_FEE_OTHER_EVENTS_ONLY,
)
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
            page_issues = self.wp_connector.get_validation_issues({
                "church_id": church_id,
                "status": "open",
                "page": current_page,
                "per_page": fetch_per_page,
            })
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

    @staticmethod
    def _normalized_sport_type(sport_type: Optional[str]) -> str:
        """Normalize sport labels so team issues can match roster rows."""
        return str(sport_type or "").split(" - ")[0].strip().casefold()

    @staticmethod
    def _issue_rule_level(issue: Dict[str, Any]) -> str:
        return str(issue.get("rule_level") or "").strip() or RULE_LEVEL["INDIVIDUAL"]

    @staticmethod
    def _issue_severity(issue: Dict[str, Any]) -> str:
        return str(issue.get("severity") or "").strip() or VALIDATION_SEVERITY["ERROR"]

    @staticmethod
    def _issue_format_type(issue: Dict[str, Any]) -> str:
        issue_format = str(issue.get("sport_format") or "").strip()
        if issue_format in FORMAT_MAPPINGS:
            return FORMAT_MAPPINGS[issue_format][0]
        return issue_format

    @staticmethod
    def _issue_gender(issue: Dict[str, Any]) -> str:
        issue_format = str(issue.get("sport_format") or "").strip()
        if issue_format in FORMAT_MAPPINGS:
            return str(FORMAT_MAPPINGS[issue_format][1])

        sport_type = str(issue.get("sport_type") or "")
        for gender in ("Women", "Men", "Mixed"):
            if gender.casefold() in sport_type.casefold():
                return gender
        return ""

    def _team_issue_matches_roster(self, issue: Dict[str, Any], roster_entry: Dict[str, Any]) -> bool:
        """Return True when a TEAM issue applies to a roster row."""
        if self._issue_rule_level(issue) != RULE_LEVEL["TEAM"]:
            return False

        if self._normalized_sport_type(issue.get("sport_type")) != self._normalized_sport_type(roster_entry.get("sport_type")):
            return False

        issue_gender = self._issue_gender(issue)
        roster_gender = str(roster_entry.get("sport_gender") or "").strip()
        if issue_gender and roster_gender and issue_gender.casefold() != roster_gender.casefold():
            return False

        issue_format_type = self._issue_format_type(issue)
        roster_format = str(roster_entry.get("sport_format") or "").strip()
        if issue_format_type and roster_format and issue_format_type.casefold() != roster_format.casefold():
            return False

        return True

    @staticmethod
    def _team_issue_scope_key(issue: Dict[str, Any]) -> Tuple[str, str, str]:
        return (
            ChurchTeamsExporter._normalized_sport_type(issue.get("sport_type")),
            ChurchTeamsExporter._issue_gender(issue).casefold(),
            ChurchTeamsExporter._issue_format_type(issue).casefold(),
        )

    @staticmethod
    def _normalized_gender(gender: Optional[str]) -> str:
        return str(gender or "").strip().casefold()

    @staticmethod
    def _normalized_name(name: Optional[str]) -> str:
        normalized = unicodedata.normalize("NFKD", str(name or "").strip())
        without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return " ".join(without_marks.casefold().split())

    @staticmethod
    def _token_matches(query_token: str, candidate_token: str) -> bool:
        if query_token == candidate_token:
            return True
        return len(query_token) >= 2 and candidate_token.startswith(query_token)

    @classmethod
    def _is_likely_name_match(cls, query_name_key: str, candidate_name_key: str) -> bool:
        query_tokens = [token for token in str(query_name_key or "").split() if token]
        candidate_tokens = [token for token in str(candidate_name_key or "").split() if token]
        if not query_tokens or not candidate_tokens:
            return False

        return all(
            any(cls._token_matches(query_token, candidate_token) for candidate_token in candidate_tokens)
            for query_token in query_tokens
        )

    @classmethod
    def _reverse_partner_suggestion_key(
        cls,
        participant_id: Any,
        sport_type: Optional[str],
        sport_gender: Optional[str],
        sport_format: Optional[str],
    ) -> Tuple[str, str, str, str]:
        return (
            str(participant_id or ""),
            cls._normalized_sport_type(sport_type),
            cls._normalized_gender(sport_gender),
            str(sport_format or "").strip().casefold(),
        )

    def _build_reverse_partner_suggestion_lookup(
        self,
        roster_rows: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, str, str, str], List[str]]:
        """Infer reverse partner-name suggestions from same-event roster rows."""
        grouped_rows: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}

        for row in roster_rows:
            participant_id = row.get("Participant ID (WP)")
            sport_type = row.get("sport_type")
            sport_gender = row.get("sport_gender")
            sport_format = row.get("sport_format")
            if participant_id in (None, "", 0, "0") or not sport_type or not sport_format:
                continue

            full_name = " ".join(
                part
                for part in (
                    str(row.get("First Name") or "").strip(),
                    str(row.get("Last Name") or "").strip(),
                )
                if part
            ).strip()
            if not full_name:
                continue

            event_key = (
                str(row.get("Church Team") or "").strip().upper(),
                self._normalized_sport_type(sport_type),
                self._normalized_gender(sport_gender),
                str(sport_format).strip().casefold(),
            )
            grouped_rows.setdefault(event_key, []).append({
                "participant_id": str(participant_id),
                "participant_name": full_name,
                "participant_name_key": self._normalized_name(full_name),
                "partner_name": str(row.get("partner_name") or "").strip(),
            })

        suggestions_by_key: Dict[Tuple[str, str, str, str], set[str]] = {}
        for (_, sport_type_key, sport_gender_key, sport_format_key), event_rows in grouped_rows.items():
            for claimant in event_rows:
                partner_name = claimant["partner_name"]
                if not partner_name:
                    continue

                partner_name_key = self._normalized_name(partner_name)
                matching_targets = [
                    candidate
                    for candidate in event_rows
                    if candidate["participant_id"] != claimant["participant_id"]
                    and self._is_likely_name_match(
                        partner_name_key,
                        candidate["participant_name_key"],
                    )
                ]

                unique_targets = {
                    candidate["participant_id"]: candidate
                    for candidate in matching_targets
                }
                if len(unique_targets) != 1:
                    continue

                target = next(iter(unique_targets.values()))
                suggestion_key = self._reverse_partner_suggestion_key(
                    target["participant_id"],
                    sport_type_key,
                    sport_gender_key,
                    sport_format_key,
                )
                suggestions_by_key.setdefault(suggestion_key, set()).add(claimant["participant_name"])

        return {
            key: sorted(names)
            for key, names in suggestions_by_key.items()
        }

    @staticmethod
    def _participant_name_from_lookup(
        participant_id: Any,
        participants_by_wp_id: Dict[str, Dict[str, Any]],
        fallback_first_name: Optional[str] = None,
        fallback_last_name: Optional[str] = None,
    ) -> str:
        participant_key = str(participant_id) if participant_id not in (None, "", 0, "0") else ""
        participant_info = participants_by_wp_id.get(participant_key, {})
        first_name = str(
            participant_info.get("First Name")
            or fallback_first_name
            or ""
        ).strip()
        last_name = str(
            participant_info.get("Last Name")
            or fallback_last_name
            or ""
        ).strip()
        return " ".join(part for part in (first_name, last_name) if part).strip()

    @staticmethod
    def _parse_partner_issue_names(issue_description: str) -> Tuple[str, str]:
        match = re.match(
            r"^(?P<claimant>.+?) listed (?P<partner>.+?) as their partner for ",
            str(issue_description or "").strip(),
        )
        if not match:
            return "", ""
        return match.group("claimant").strip(), match.group("partner").strip()

    def _build_issue_based_reverse_partner_suggestion_lookup(
        self,
        issues: List[Dict[str, Any]],
        participants_by_wp_id: Dict[str, Dict[str, Any]],
    ) -> Dict[Tuple[str, str, str, str], List[str]]:
        """Infer reverse partner suggestions from TEAM unmatched-partner warnings."""
        missing_targets_by_event: Dict[Tuple[str, str, str], List[Dict[str, str]]] = {}

        for issue in issues:
            if issue.get("issue_type") != "missing_doubles_partner":
                continue

            participant_id = issue.get("participant_id")
            if participant_id in (None, "", 0, "0"):
                continue

            participant_name = self._participant_name_from_lookup(
                participant_id,
                participants_by_wp_id,
                issue.get("first_name"),
                issue.get("last_name"),
            )
            if not participant_name:
                continue

            event_key = (
                self._normalized_sport_type(issue.get("sport_type")),
                self._normalized_gender(self._issue_gender(issue)),
                self._issue_format_type(issue).casefold(),
            )
            missing_targets_by_event.setdefault(event_key, []).append({
                "participant_id": str(participant_id),
                "participant_name": participant_name,
                "participant_name_key": self._normalized_name(participant_name),
            })

        suggestions_by_key: Dict[Tuple[str, str, str, str], set[str]] = {}
        for issue in issues:
            if issue.get("issue_type") != "doubles_partner_unmatched":
                continue

            event_key = (
                self._normalized_sport_type(issue.get("sport_type")),
                self._normalized_gender(self._issue_gender(issue)),
                self._issue_format_type(issue).casefold(),
            )
            event_targets = missing_targets_by_event.get(event_key, [])
            if not event_targets:
                continue

            parsed_claimant_name, parsed_partner_name = self._parse_partner_issue_names(
                str(issue.get("issue_description") or "")
            )
            if not parsed_partner_name:
                continue

            claimant_name = self._participant_name_from_lookup(
                issue.get("participant_id"),
                participants_by_wp_id,
            ) or parsed_claimant_name
            if not claimant_name:
                continue

            partner_name_key = self._normalized_name(parsed_partner_name)
            matching_targets = [
                target
                for target in event_targets
                if self._is_likely_name_match(partner_name_key, target["participant_name_key"])
            ]
            unique_targets = {
                target["participant_id"]: target
                for target in matching_targets
            }
            if len(unique_targets) != 1:
                continue

            target = next(iter(unique_targets.values()))
            suggestion_key = self._reverse_partner_suggestion_key(
                target["participant_id"],
                issue.get("sport_type"),
                self._issue_gender(issue),
                self._issue_format_type(issue),
            )
            suggestions_by_key.setdefault(suggestion_key, set()).add(claimant_name)

        return {
            key: sorted(names)
            for key, names in suggestions_by_key.items()
        }

    @staticmethod
    def _merge_reverse_partner_suggestions(
        *lookups: Dict[Tuple[str, str, str, str], List[str]],
    ) -> Dict[Tuple[str, str, str, str], List[str]]:
        merged: Dict[Tuple[str, str, str, str], set[str]] = {}
        for lookup in lookups:
            for key, names in lookup.items():
                merged.setdefault(key, set()).update(names)

        return {
            key: sorted(names)
            for key, names in merged.items()
        }

    def _build_validation_issue_rows(
        self,
        church_code: str,
        issues: List[Dict[str, Any]],
        participants_by_wp_id: Dict[str, Dict[str, Any]],
        reverse_partner_suggestions: Optional[Dict[Tuple[str, str, str, str], List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Build export rows for the Validation-Issues tab."""
        rows: List[Dict[str, Any]] = []
        reverse_partner_suggestions = reverse_partner_suggestions or {}
        for issue in issues:
            participant_id = issue.get("participant_id")
            participant_key = str(participant_id) if participant_id not in (None, "", 0, "0") else ""
            participant_info = participants_by_wp_id.get(participant_key, {})
            first_name = str(issue.get("first_name") or participant_info.get("First Name") or "").strip()
            last_name = str(issue.get("last_name") or participant_info.get("Last Name") or "").strip()
            participant_name = " ".join(part for part in (first_name, last_name) if part).strip()
            issue_description = issue.get("issue_description", "")

            if (
                issue.get("issue_type") == "missing_doubles_partner"
                and participant_key
            ):
                suggestion_key = self._reverse_partner_suggestion_key(
                    participant_key,
                    issue.get("sport_type"),
                    self._issue_gender(issue),
                    self._issue_format_type(issue),
                )
                reverse_claimants = reverse_partner_suggestions.get(suggestion_key, [])
                if len(reverse_claimants) == 1:
                    issue_description = (
                        f"{issue_description}; perhaps {reverse_claimants[0]} listed you as partner."
                    )
                elif len(reverse_claimants) > 1:
                    suggestion_list = ", ".join(reverse_claimants)
                    issue_description = (
                        f"{issue_description}; ambiguous reverse partner claims: "
                        f"{suggestion_list}. Use full name."
                    )

            rows.append({
                "Church Team": church_code,
                "Rule Level": self._issue_rule_level(issue),
                "Severity": self._issue_severity(issue),
                "Status": issue.get("status", "open"),
                "Issue Type": issue.get("issue_type", ""),
                "Rule Code": issue.get("rule_code", ""),
                "Participant ID (WP)": participant_id or "",
                "ChMeetings ID": participant_info.get("ChMeetings ID", ""),
                "Participant Name": participant_name,
                "Approval_Status (WP)": participant_info.get("Approval_Status (WP)", ""),
                "sport_type": issue.get("sport_type"),
                "sport_format": issue.get("sport_format"),
                "Issue Description": issue_description,
            })

        return rows

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
                    "ChM_Roles": additional_fields.get(CHM_FIELDS["ROLES"], ""),
                    "ChM_Completion_Checklist": additional_fields.get(CHM_FIELDS["COMPLETION_CHECKLIST"], ""),
                    "ChM_Primary_Sport": additional_fields.get(CHM_FIELDS["PRIMARY_SPORT"], ""),
                    "ChM_Secondary_Sport": additional_fields.get(CHM_FIELDS["SECONDARY_SPORT"], ""),
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
        logger.info(f"Starting report generation. Target Church: {target_church_code or 'ALL'}. Output Dir: {output_dir}")

        chm_data_by_church = self._fetch_chm_church_team_data(target_church_code)

        if not chm_data_by_church:
            logger.warning("No data fetched from ChMeetings. No reports will be generated.")
            return True 

        all_contacts_data: List[Dict[str, Any]] = []
        all_rosters_data: List[Dict[str, Any]] = []
        all_validation_data: List[Dict[str, Any]] = []
        summary_data_list: List[Dict[str, Any]] = []

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
            church_wp = self.wp_connector.get_church_by_code(church_code_iter)
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

                if is_participant_chm:
                    wp_participants = self.wp_connector.get_participants({"chmeetings_id": chm_id})
                    if wp_participants:
                        wp_participant = wp_participants[0] 
                        wp_participant_id_val = wp_participant.get("participant_id", 0)
                        approval_status_val = wp_participant.get("approval_status", "pending")
                        photo_url_val = wp_participant.get("photo_url", "N/A")
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
                                "First Name": chm_person["First Name"],
                                "Last Name": chm_person["Last Name"],
                                "Approval_Status (WP)": approval_status_val,
                            }
                            wp_rosters = self.wp_connector.get_rosters({"participant_id": wp_participant_id_val})
                            for roster_entry in wp_rosters:
                                matching_team_issues = [
                                    issue for issue in team_validation_issues
                                    if self._team_issue_matches_roster(issue, roster_entry)
                                ]
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

                if is_participant_chm:
                    _primary = chm_person.get("ChM_Primary_Sport", "")
                    _secondary = chm_person.get("ChM_Secondary_Sport", "")
                    _other = chm_person.get("ChM_Other_Events", "")
                    athlete_fee = (
                        ATHLETE_FEE_OTHER_EVENTS_ONLY
                        if (not _primary and not _secondary and _other)
                        else ATHLETE_FEE_STANDARD
                    )
                    total_athlete_fees += athlete_fee
                else:
                    athlete_fee = ""

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

            church_validation_rows = self._build_validation_issue_rows(
                church_code_iter,
                open_validation_issues,
                participants_by_wp_id,
                reverse_partner_suggestions,
            )

            individual_open_errors = [
                issue for issue in open_validation_issues
                if self._issue_rule_level(issue) == RULE_LEVEL["INDIVIDUAL"]
                and self._issue_severity(issue) == VALIDATION_SEVERITY["ERROR"]
            ]
            team_open_errors = [
                issue for issue in team_validation_issues
                if self._issue_severity(issue) == VALIDATION_SEVERITY["ERROR"]
            ]
            open_warnings = [
                issue for issue in open_validation_issues
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

                current_church_contacts = [row for row in all_contacts_data if row["Church Team"] == church_code_iter]
                current_church_rosters = [row for row in all_rosters_data if row["Church Team"] == church_code_iter]
                current_church_validation = [row for row in all_validation_data if row["Church Team"] == church_code_iter]
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
                                     all_validation_data)   

        # Handle force resend options
        if force_resend_pending or force_resend_validated1 or force_resend_validated2:
            resend_count = self._handle_force_resend(
                all_contacts_data, force_resend_pending, force_resend_validated1, 
                force_resend_validated2, dry_run, target_resend_chm_id=target_resend_chm_id
            )
            logger.info(f"Force resend completed. Total emails {'would be sent' if dry_run else 'sent'}: {resend_count}")
        
        logger.info("Report generation process finished.")
        return True

    def _write_excel_report(self, filepath: Path,
                            summary_rows: List[Dict[str, Any]],
                            contacts_rows: List[Dict[str, Any]],
                            roster_rows: List[Dict[str, Any]],
                            validation_rows: List[Dict[str, Any]]):
        """Writes the collected data to an Excel file with specified tabs and formatting."""
        logger.info(f"Writing Excel report to: {filepath}")
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Summary Tab
                df_summary = pd.DataFrame(summary_rows)
                if not df_summary.empty:
                    summary_cols = [
                        "Church Code", "Total Members (ChM Team Group)", "Total Participants (in WP)",
                        "Total Approved (WP)", "Total Pending Approval (WP)", "Total Denied (WP)",
                        "Total Participants w/ Open ERRORs (WP)",
                        "Total Open Individual ERRORs (WP)", "Total Open TEAM ERRORs (WP)",
                        "Total Open WARNINGs (WP)", "Total Sports w/ Open TEAM Issues (WP)",
                        "Total Athlete Fees",
                        "Latest ChM Record Update for Team"
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
                        "Mobile Phone", "Email", "Athlete Fee", "First_Open_ERROR_Desc (WP)",
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
                        "sport_type", "sport_gender", "sport_format", "team_order", "partner_name",
                        "Open_TEAM_Issue_Count (WP)", "Open_TEAM_Issue_Desc (WP)"
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

                # Validation-Issues Tab
                df_validation = pd.DataFrame(validation_rows)
                if not df_validation.empty:
                    validation_cols = [
                        "Church Team", "Rule Level", "Severity", "Status",
                        "Issue Type", "Rule Code",
                        "Participant ID (WP)", "ChMeetings ID", "Participant Name",
                        "Approval_Status (WP)", "sport_type", "sport_format",
                        "Issue Description"
                    ]
                    for col in validation_cols:
                        if col not in df_validation.columns:
                            df_validation[col] = None
                    df_validation = df_validation.reindex(columns=validation_cols).sort_values(
                        by=["Church Team", "Rule Level", "Severity", "Participant Name", "Issue Type"],
                        ascending=[True, True, True, True, True]
                    )
                df_validation.to_excel(writer, sheet_name="Validation-Issues", index=False)
                logger.debug(f"Validation-Issues tab: {len(df_validation)} rows.")

                # Add yellow note to Photo column in Roster sheet
                if not df_roster.empty:
                    from openpyxl.comments import Comment
                    from openpyxl.styles import PatternFill
                    
                    roster_ws = writer.sheets["Roster"]
                    
                    # Add comment to Photo column (column F)
                    photo_comment = Comment(
                        "In Office365 edition 2023 and later, you can remove the @ from the formula to display the image",
                        "Bumble",200,300 # Width and height in pixels
                    )
                    roster_ws["F1"].comment = photo_comment
                    
                    # Add yellow background
                    yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
                    roster_ws["F1"].fill = yellow_fill

                # Sport-Specific Tabs
                if not df_roster.empty and "sport_type" in df_roster.columns:
                    # Group roster data by sport combinations
                    sport_groups = {}
                    
                    for _, row in df_roster.iterrows():
                        sport_type = row.get("sport_type", "")
                        sport_gender = row.get("sport_gender", "")
                        
                        if not sport_type:
                            continue
                            
                        # Special handling for Volleyball - separate by gender
                        if sport_type.upper() == "VOLLEYBALL" or sport_type.upper().startswith("VB"):
                            if sport_gender.upper() == "MEN" or sport_gender.upper() == "MALE":
                                tab_name = "VB Men"
                            elif sport_gender.upper() == "WOMEN" or sport_gender.upper() == "FEMALE":
                                tab_name = "VB Women"
                            else:
                                tab_name = "Volleyball"  # Fallback if gender unclear
                        else:
                            # For all other sports, use sport_type only
                            tab_name = sport_type
                        
                        # Create group if it doesn't exist
                        if tab_name not in sport_groups:
                            sport_groups[tab_name] = []
                        
                        sport_groups[tab_name].append(row.to_dict())
                    
                    # Create tabs for each sport group
                    for sport_name, sport_data in sport_groups.items():
                        if not sport_data:  # Skip empty sports
                            continue
                            
                        df_sport = pd.DataFrame(sport_data)
                        
                        # Modify columns: replace Last Name and First Name with Full Name
                        sport_cols = [
                            "Church Team", "ChMeetings ID", "Participant ID (WP)", "Approval_Status (WP)",
                            "Is_Member_ChM", "Photo", "Full Name", "Gender", "Age (at Event)", 
                            "Mobile Phone", "Email", "sport_type", "sport_gender", "sport_format", 
                            "team_order", "partner_name",
                            "Open_TEAM_Issue_Count (WP)", "Open_TEAM_Issue_Desc (WP)"
                        ]
                        
                        # Create Full Name column
                        df_sport["Full Name"] = df_sport["Last Name"].astype(str) + " " + df_sport["First Name"].astype(str)
                        
                        # Ensure all sport columns exist
                        for col in sport_cols:
                            if col not in df_sport.columns:
                                df_sport[col] = None
                        
                        # Reindex and sort
                        df_sport = df_sport.reindex(columns=sport_cols).sort_values(
                            by=["Church Team", "sport_type", "sport_gender", "Full Name", "Approval_Status (WP)"],
                            ascending=[True, True, True, True, True]
                        )
                        
                        # Write to Excel with sport name as tab name
                        # Clean tab name for Excel compatibility (max 31 characters, no special chars)
                        clean_tab_name = "".join(c for c in sport_name if c.isalnum() or c in " -_")[:31]
                        df_sport.to_excel(writer, sheet_name=clean_tab_name, index=False)
                        logger.debug(f"{clean_tab_name} tab: {len(df_sport)} rows.")

                # SINGLE Excel Formatting Block - Add right before closing writer
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    
                    # Add auto filter to all data (if worksheet has data)
                    if worksheet.max_row > 1:  # More than just headers
                        worksheet.auto_filter.ref = worksheet.dimensions
                    
                    # Auto-adjust column widths
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))/2 # Divide by 2 for better fit
                            except:
                                pass
                        
                        # Set width with some padding
                        adjusted_width = min(max_length + 2, 50)  # Max width of 50
                        worksheet.column_dimensions[column_letter].width = adjusted_width

            logger.info(f"Successfully wrote Excel report: {filepath}")
        except Exception as e:
            logger.error(f"Failed to write Excel file {filepath}: {e}", exc_info=True)

    def _handle_force_resend(self, contacts_data: List[Dict[str, Any]], 
                            force_pending: bool, force_validated1: bool, force_validated2: bool,
                            dry_run: bool, target_resend_chm_id: Optional[str] = None) -> int:
        """Handle force resend based on participant categories."""
        
        from sync.manager import SyncManager  # Import here to avoid circular imports
        
        participants_to_resend = []
        
        for contact in contacts_data:
            approval_status = contact.get("Approval_Status (WP)", "").lower()
            
            # Category 1: Pending participants
            if force_pending and approval_status in ["pending", "pending_approval"]:
                participants_to_resend.append(contact)
                logger.debug(f"Added pending participant: {contact.get('First Name')} {contact.get('Last Name')} ({contact.get('Church Team')})")
                
            # Category 2 & 3: Validated participants  
            elif approval_status == "validated":
                # Check Box 1-6 data to categorize
                has_box_data = any(contact.get(f"Box {i}", "") for i in range(1, 7))
                
                if force_validated1 and has_box_data:
                    # Under review by church rep
                    participants_to_resend.append(contact)
                    logger.debug(f"Added validated-under-review participant: {contact.get('First Name')} {contact.get('Last Name')} ({contact.get('Church Team')})")
                elif force_validated2 and not has_box_data:
                    # Not reviewed yet by church rep
                    participants_to_resend.append(contact)
                    logger.debug(f"Added validated-not-reviewed participant: {contact.get('First Name')} {contact.get('Last Name')} ({contact.get('Church Team')})")

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
                    participant_name = f"{p.get('First Name')} {p.get('Last Name')}"
                    church_code = p.get('Church Team')
                    participant_email = p.get('Email', 'N/A')
                    status = p.get('Approval_Status (WP)')
                    
                    # Get church details for email preview
                    if church_code in churches_cache:
                        church = churches_cache[church_code]
                        pastor_email = church.get('pastor_email', 'N/A')
                        church_rep_email = church.get('church_rep_email', 'N/A')
                        
                        logger.info(f"  {participant_name} ({church_code}) - Status: {status}")
                        logger.info(f"    → Pastor approval email TO: {pastor_email}")
                        logger.info(f"    → Participant notification TO: {participant_email}")
                        if church_rep_email != 'N/A':
                            logger.info(f"    → Church rep CC: {church_rep_email}")
                        logger.info("")  # Empty line for readability
                    else:
                        logger.info(f"  {participant_name} ({church_code}) - Status: {status}")
                        logger.error(f"    → ERROR: Church {church_code} not found in cache!")
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
                    logger.info(f"Resent approval email for {participant_contact.get('First Name')} {participant_contact.get('Last Name')}")
                else:
                    logger.error(f"Failed to resend for {participant_contact.get('First Name')} {participant_contact.get('Last Name')}")
        
        return success_count


    # In church_teams_export.py, update both methods:
    def _resend_approval_for_participant(self, sync_manager, participant_contact: Dict[str, Any]) -> bool:
        """Resend approval email for a specific participant using contact data."""
        try:
            # Extract data from contact
            wp_participant_id = participant_contact.get("Participant ID (WP)")
            first_name = participant_contact.get("First Name", "")
            last_name = participant_contact.get("Last Name", "")
            church_team = participant_contact.get("Church Team", "")
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
                logger.info(f"Successfully resent approval email for {participant_name} (ID: {wp_participant_id})")
                return True
            else:
                logger.error(f"Failed to send approval email for {participant_name} (ID: {wp_participant_id})")
                return False
            
        except Exception as e:
            logger.error(f"Error resending approval for participant {participant_contact.get('First Name')} {participant_contact.get('Last Name')}: {e}", exc_info=True)
            return False
                    
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
