# church_teams_report.py
# Version 1.0.0
"""Row shaping and Excel formatting for the church-teams export (Issue #376).

Everything here turns data that ``church_teams_export.py`` has already fetched
into report rows and the Church_Team_Status workbook. Nothing in this module
calls ChMeetings or WordPress.

``ChurchTeamsReportMixin`` is mixed into ``ChurchTeamsExporter`` so the
long-standing ``exporter._build_validation_issue_rows(...)`` /
``exporter._write_excel_report(...)`` call surface is unchanged. The host class
must provide:

* ``_venue_input_path()`` - where venue_input.xlsx lives (export orchestration owns paths)
* ``_decompose_event_name`` and ``write_schedule_input_json`` - bound from
  ScheduleWorkbookBuilder by ``church_teams_scheduling.delegate_schedule_workbook_methods``
"""
import pandas as pd
from pathlib import Path
from loguru import logger
from typing import Optional, List, Dict, Any, Tuple
import re
import unicodedata

from config import (
    EXPORT_COLUMNS,
    FORMAT_MAPPINGS,
    RULE_LEVEL,
    VALIDATION_SEVERITY,
    SPORT_TYPE,
    SPORT_FORMAT,
    GENDER,
    RACQUET_SPORTS,
)
from church_teams_scheduling import (
    stamp_sport_export_tab_statuses,
    write_schedule_input_for_export,
)


class ChurchTeamsReportMixin:
    """Validation-issue rows, partner suggestions, the multi-sport matrix and the workbook writer."""

    # ── Validation issues and reverse partner suggestions ───────────────────

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
            ChurchTeamsReportMixin._normalized_sport_type(issue.get("sport_type")),
            ChurchTeamsReportMixin._issue_gender(issue).casefold(),
            ChurchTeamsReportMixin._issue_format_type(issue).casefold(),
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
                    str(row.get(EXPORT_COLUMNS["FIRST_NAME"]) or "").strip(),
                    str(row.get(EXPORT_COLUMNS["LAST_NAME"]) or "").strip(),
                )
                if part
            ).strip()
            if not full_name:
                continue

            event_key = (
                str(row.get(EXPORT_COLUMNS["CHURCH_TEAM"]) or "").strip().upper(),
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
            participant_info.get(EXPORT_COLUMNS["FIRST_NAME"])
            or fallback_first_name
            or ""
        ).strip()
        last_name = str(
            participant_info.get(EXPORT_COLUMNS["LAST_NAME"])
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
            first_name = str(issue.get("first_name") or participant_info.get(EXPORT_COLUMNS["FIRST_NAME"]) or "").strip()
            last_name = str(issue.get("last_name") or participant_info.get(EXPORT_COLUMNS["LAST_NAME"]) or "").strip()
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
                EXPORT_COLUMNS["CHURCH_TEAM"]: church_code,
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

    def _filter_reportable_validation_issues(
        self,
        church_code: str,
        issues: List[Dict[str, Any]],
        participants_by_wp_id: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Keep only validation issues that belong in the current church snapshot.

        The export is driven by current ChMeetings Team-group membership. If a person
        was deleted/re-registered in ChMeetings, WordPress can still hold open
        individual issues tied to an older participant_id. Those stale issues should
        not appear in the current church workbook.
        """
        current_participant_ids = {
            str(participant_id)
            for participant_id in participants_by_wp_id
            if str(participant_id).strip()
        }
        filtered_issues: List[Dict[str, Any]] = []
        skipped_stale_individual_issues = 0

        for issue in issues:
            if self._issue_rule_level(issue) != RULE_LEVEL["INDIVIDUAL"]:
                filtered_issues.append(issue)
                continue

            participant_id = issue.get("participant_id")
            participant_key = (
                str(participant_id).strip()
                if participant_id not in (None, "", 0, "0")
                else ""
            )
            if not participant_key or participant_key in current_participant_ids:
                filtered_issues.append(issue)
                continue

            skipped_stale_individual_issues += 1

        if skipped_stale_individual_issues:
            logger.warning(
                f"Team {church_code}: filtered out {skipped_stale_individual_issues} "
                "stale INDIVIDUAL validation issue(s) that no longer map to a "
                "current participant in the ChMeetings Team-group snapshot."
            )

        return filtered_issues

    # ── Multi-Sport-Matrix labels ───────────────────────────────────────────

    @staticmethod
    def _matrix_sport_label(sport_type: Any, sport_gender: Any = "", sport_format: Any = "") -> str:
        return " ".join(
            str(part or "").strip()
            for part in (sport_type, sport_gender, sport_format)
            if str(part or "").strip()
        )

    @staticmethod
    def _normalize_matrix_label(label: Any) -> str:
        return " ".join(str(label or "").split()).casefold()

    def _matrix_labels_for_selection(self, sport_value: Any, format_value: Any = "") -> set:
        """Return possible matrix labels for a ChMeetings sport selection."""
        sport_value = str(sport_value or "").strip()
        format_value = str(format_value or "").strip()
        if not sport_value or sport_value in ("Unselected/NA", "None"):
            return set()

        sport_parts = sport_value.split(" - ", 1)
        sport_type = sport_parts[0].strip()

        if sport_type in RACQUET_SPORTS:
            if format_value in FORMAT_MAPPINGS:
                sport_format, sport_gender = FORMAT_MAPPINGS[format_value]
                return {self._matrix_sport_label(sport_type, sport_gender, sport_format)}
            return {
                self._matrix_sport_label(sport_type, gender, sport_format)
                for sport_format, gender in dict.fromkeys(FORMAT_MAPPINGS.values())
            }

        if len(sport_parts) > 1:
            decomposed_type, sport_gender, sport_format = self._decompose_event_name(sport_value)
            return {self._matrix_sport_label(decomposed_type, sport_gender, sport_format)}

        canonical = next(
            (
                value for value in SPORT_TYPE.values()
                if value.split(" - ", 1)[0].strip().casefold() == sport_type.casefold()
            ),
            None,
        )
        if canonical and " - " in canonical:
            decomposed_type, sport_gender, sport_format = self._decompose_event_name(canonical)
            return {self._matrix_sport_label(decomposed_type, sport_gender, sport_format)}
        return {self._matrix_sport_label(sport_type, GENDER["MIXED"], SPORT_FORMAT["TEAM"])}

    def _matrix_labels_for_other_events(self, other_events: Any) -> set:
        labels = set()
        for event_name in str(other_events or "").split(","):
            labels.update(self._matrix_labels_for_selection(event_name.strip()))
        return labels

    def _matrix_role_for_roster_row(self, roster_row: Dict[str, Any], label: str) -> str:
        normalized_label = self._normalize_matrix_label(label)
        primary_labels = {
            self._normalize_matrix_label(item)
            for item in self._matrix_labels_for_selection(
                roster_row.get("participant_primary_sport"),
                roster_row.get("participant_primary_format"),
            )
        }
        if normalized_label in primary_labels:
            return "Primary"

        secondary_labels = {
            self._normalize_matrix_label(item)
            for item in self._matrix_labels_for_selection(
                roster_row.get("participant_secondary_sport"),
                roster_row.get("participant_secondary_format"),
            )
        }
        if normalized_label in secondary_labels:
            return "Secondary"

        other_labels = {
            self._normalize_matrix_label(item)
            for item in self._matrix_labels_for_other_events(roster_row.get("participant_other_events"))
        }
        if normalized_label in other_labels:
            return "Other"

        return "Other"

    def _canonical_matrix_sport_labels(self) -> List[str]:
        labels: List[str] = []

        def add(label: str) -> None:
            if label and label not in labels:
                labels.append(label)

        for sport_value in SPORT_TYPE.values():
            sport_type = sport_value.split(" - ", 1)[0].strip()
            if sport_type in RACQUET_SPORTS:
                for sport_format, sport_gender in dict.fromkeys(FORMAT_MAPPINGS.values()):
                    add(self._matrix_sport_label(sport_type, sport_gender, sport_format))
                continue

            if " - " in sport_value:
                decomposed_type, sport_gender, sport_format = self._decompose_event_name(sport_value)
                add(self._matrix_sport_label(decomposed_type, sport_gender, sport_format))
            else:
                add(self._matrix_sport_label(sport_type, GENDER["MIXED"], SPORT_FORMAT["TEAM"]))

        return labels

    @staticmethod
    def _prefer_matrix_role(existing: Optional[str], new: str) -> str:
        rank = {"Primary": 3, "Secondary": 2, "Other": 1, "": 0, None: 0}
        return new if rank.get(new, 0) > rank.get(existing, 0) else existing

    # ── Workbook writer ─────────────────────────────────────────────────────

    @staticmethod
    def _excel_image_formula(photo_url: Any) -> str:
        """Return an Excel IMAGE formula only for non-empty HTTP(S) URLs."""
        if not isinstance(photo_url, str):
            return ""
        photo_url = photo_url.strip()
        if photo_url.startswith(("http://", "https://")):
            return f'=IMAGE("{photo_url}")'
        return ""

    def _write_excel_report(self, filepath: Path,
                            summary_rows: List[Dict[str, Any]],
                            contacts_rows: List[Dict[str, Any]],
                            roster_rows: List[Dict[str, Any]],
                            validation_rows: List[Dict[str, Any]],
                            include_venue_capacity: bool = False):
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
                # Build sports-registered lookup keyed by Participant ID (WP) and ChMeetings ID
                sports_by_wp_id: Dict[str, list] = {}
                sports_by_chm_id: Dict[str, list] = {}
                for rrow in roster_rows:
                    label = self._matrix_sport_label(
                        rrow.get("sport_type"),
                        rrow.get("sport_gender"),
                        rrow.get("sport_format"),
                    )
                    if not label:
                        continue
                    wp_pid = str(rrow.get("Participant ID (WP)") or "").strip()
                    chm_pid = str(rrow.get("ChMeetings ID") or "").strip()
                    if wp_pid and wp_pid not in ("0", ""):
                        sports_by_wp_id.setdefault(wp_pid, [])
                        if label not in sports_by_wp_id[wp_pid]:
                            sports_by_wp_id[wp_pid].append(label)
                    if chm_pid and chm_pid not in ("0", ""):
                        sports_by_chm_id.setdefault(chm_pid, [])
                        if label not in sports_by_chm_id[chm_pid]:
                            sports_by_chm_id[chm_pid].append(label)

                # Multi-Sport-Matrix: per-participant {sport_label: "Primary"|"Secondary"|"Other"}
                sport_role_by_wp_id: Dict[str, Dict[str, str]] = {}
                sport_role_by_chm_id: Dict[str, Dict[str, str]] = {}
                for rrow in roster_rows:
                    label = self._matrix_sport_label(
                        rrow.get("sport_type"),
                        rrow.get("sport_gender"),
                        rrow.get("sport_format"),
                    )
                    if not label:
                        continue
                    role = self._matrix_role_for_roster_row(rrow, label)
                    wp_pid = str(rrow.get("Participant ID (WP)") or "").strip()
                    chm_pid = str(rrow.get("ChMeetings ID") or "").strip()
                    if wp_pid and wp_pid not in ("0", ""):
                        sport_role_by_wp_id.setdefault(wp_pid, {})
                        sport_role_by_wp_id[wp_pid][label] = self._prefer_matrix_role(
                            sport_role_by_wp_id[wp_pid].get(label),
                            role,
                        )
                    if chm_pid and chm_pid not in ("0", ""):
                        sport_role_by_chm_id.setdefault(chm_pid, {})
                        sport_role_by_chm_id[chm_pid][label] = self._prefer_matrix_role(
                            sport_role_by_chm_id[chm_pid].get(label),
                            role,
                        )

                for crow in contacts_rows:
                    wp_pid = str(crow.get("Participant ID (WP)") or "").strip()
                    chm_pid = str(crow.get("ChMeetings ID") or "").strip()
                    sports = (
                        sports_by_wp_id.get(wp_pid)
                        or sports_by_chm_id.get(chm_pid)
                        or []
                    )
                    crow["Sports Registered"] = ", ".join(sorted(sports)) if sports else ""

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
                        EXPORT_COLUMNS["CHURCH_TEAM"], "ChMeetings ID", EXPORT_COLUMNS["FIRST_NAME"],
                        EXPORT_COLUMNS["LAST_NAME"], "Is_Participant",
                        "Is_Member_ChM", "Participant ID (WP)", "Approval_Status (WP)",
                        "Total_Open_ERRORs (WP)", "Gender", "Birthdate", "Age (at Event)",
                        "Mobile Phone", "Email", "Registration Date (WP)", "Sports Registered", "Athlete Fee",
                        "First_Open_ERROR_Desc (WP)",
                        "Box 1", "Box 2", "Box 3", "Box 4", "Box 5", "Box 6",
                        photo_url_col_name, "Update_on_ChM"
                    ]
                    for col in contacts_cols: # Ensure all contact columns exist
                        if col not in df_contacts.columns:
                            df_contacts[col] = None
                    df_contacts = df_contacts.reindex(columns=contacts_cols).sort_values(
                        by=[EXPORT_COLUMNS["CHURCH_TEAM"], "Total_Open_ERRORs (WP)", "Is_Participant",
                            EXPORT_COLUMNS["LAST_NAME"], EXPORT_COLUMNS["FIRST_NAME"]],
                        ascending=[True, False, False, True, True]
                    )
                df_contacts.to_excel(writer, sheet_name="Contacts-Status", index=False)
                logger.debug(f"Contacts-Status tab: {len(df_contacts)} rows.")

                # Roster Tab
                df_roster = pd.DataFrame(roster_rows)
                if not df_roster.empty:
                    roster_cols = [
                        EXPORT_COLUMNS["CHURCH_TEAM"], "ChMeetings ID", "Participant ID (WP)", "Approval_Status (WP)",
                        "Is_Member_ChM", "Photo",          # ADD THIS LINE
                        EXPORT_COLUMNS["FIRST_NAME"], EXPORT_COLUMNS["LAST_NAME"], "Gender", "Age (at Event)",
                        "Mobile Phone", "Email",
                        "sport_type", "sport_gender", "sport_format", "team_order", "partner_name",
                        "Open_TEAM_Issue_Count (WP)", "Open_TEAM_Issue_Desc (WP)"
                    ]
                    for col in roster_cols: # Ensure all roster columns exist
                        if col not in df_roster.columns:
                            df_roster[col] = None
                    df_roster = df_roster.reindex(columns=roster_cols).sort_values(
                        by=[EXPORT_COLUMNS["CHURCH_TEAM"], "sport_type", "sport_gender",
                            EXPORT_COLUMNS["LAST_NAME"], EXPORT_COLUMNS["FIRST_NAME"],
                            "Approval_Status (WP)", "sport_format"] # Removed team_order and partner_name from sort if they are often None
                    )
                df_roster.to_excel(writer, sheet_name="Roster", index=False)
                logger.debug(f"Roster tab: {len(df_roster)} rows.")

                # Multi-Sport-Matrix Tab
                # One row per participant; one column per sport label; value = Primary / Secondary / Other.
                observed_sport_labels = (
                    {lbl for roles in sport_role_by_wp_id.values() for lbl in roles}
                    | {lbl for roles in sport_role_by_chm_id.values() for lbl in roles}
                )
                all_sport_labels: list = self._canonical_matrix_sport_labels()
                all_sport_labels.extend(
                    sorted(lbl for lbl in observed_sport_labels if lbl not in all_sport_labels)
                )
                matrix_rows: List[Dict[str, Any]] = []
                seen_matrix_pids: set = set()
                for crow in contacts_rows:
                    if crow.get("Is_Participant") != "Yes":
                        continue
                    wp_pid = str(crow.get("Participant ID (WP)") or "").strip()
                    chm_pid = str(crow.get("ChMeetings ID") or "").strip()
                    participant_key = wp_pid if (wp_pid and wp_pid not in ("0", "")) else chm_pid
                    if participant_key in seen_matrix_pids:
                        continue
                    seen_matrix_pids.add(participant_key)
                    sport_roles = (
                        sport_role_by_wp_id.get(wp_pid)
                        or sport_role_by_chm_id.get(chm_pid)
                        or {}
                    )
                    mrow: Dict[str, Any] = {
                        EXPORT_COLUMNS["CHURCH_TEAM"]: crow.get(EXPORT_COLUMNS["CHURCH_TEAM"], ""),
                        "ChMeetings ID": chm_pid,
                        "Participant ID (WP)": wp_pid,
                        EXPORT_COLUMNS["FIRST_NAME"]: crow.get(EXPORT_COLUMNS["FIRST_NAME"], ""),
                        EXPORT_COLUMNS["LAST_NAME"]: crow.get(EXPORT_COLUMNS["LAST_NAME"], ""),
                        "Gender": crow.get("Gender", ""),
                        "Age (at Event)": crow.get("Age (at Event)", ""),
                        "Approval_Status (WP)": crow.get("Approval_Status (WP)", ""),
                    }
                    for sport_col in all_sport_labels:
                        mrow[sport_col] = sport_roles.get(sport_col, "")
                    matrix_rows.append(mrow)
                matrix_identity_cols = [
                    EXPORT_COLUMNS["CHURCH_TEAM"], "ChMeetings ID", "Participant ID (WP)",
                    EXPORT_COLUMNS["FIRST_NAME"], EXPORT_COLUMNS["LAST_NAME"], "Gender", "Age (at Event)",
                    "Approval_Status (WP)",
                ]
                df_matrix = pd.DataFrame(matrix_rows) if matrix_rows else pd.DataFrame(columns=matrix_identity_cols + all_sport_labels)
                if not df_matrix.empty:
                    matrix_all_cols = matrix_identity_cols + all_sport_labels
                    for col in matrix_all_cols:
                        if col not in df_matrix.columns:
                            df_matrix[col] = ""
                    df_matrix = df_matrix.reindex(columns=matrix_all_cols).sort_values(
                        by=[EXPORT_COLUMNS["CHURCH_TEAM"], EXPORT_COLUMNS["LAST_NAME"], EXPORT_COLUMNS["FIRST_NAME"]]
                    )
                df_matrix.to_excel(writer, sheet_name="Multi-Sport-Matrix", index=False)
                logger.debug(f"Multi-Sport-Matrix tab: {len(df_matrix)} rows.")

                # Validation-Issues Tab
                df_validation = pd.DataFrame(validation_rows)
                if not df_validation.empty:
                    validation_cols = [
                        EXPORT_COLUMNS["CHURCH_TEAM"], "Rule Level", "Severity", "Status",
                        "Issue Type", "Rule Code",
                        "Participant ID (WP)", "ChMeetings ID", "Participant Name",
                        "Approval_Status (WP)", "sport_type", "sport_format",
                        "Issue Description"
                    ]
                    for col in validation_cols:
                        if col not in df_validation.columns:
                            df_validation[col] = None
                    df_validation = df_validation.reindex(columns=validation_cols).sort_values(
                        by=[EXPORT_COLUMNS["CHURCH_TEAM"], "Rule Level", "Severity", "Participant Name", "Issue Type"],
                        ascending=[True, True, True, True, True]
                    )
                df_validation.to_excel(writer, sheet_name="Validation-Issues", index=False)
                logger.debug(f"Validation-Issues tab: {len(df_validation)} rows.")

                # schedule_input.json for the consolidated ALL export (scheduling hand-off).
                # A failure there is logged and must not stop the sport-specific tabs below.
                if include_venue_capacity:
                    write_schedule_input_for_export(
                        self,
                        roster_rows,
                        validation_rows,
                        self._venue_input_path(),
                        filepath.parent,
                    )

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
                        sport_type = str(row.get("sport_type") or "")
                        sport_gender = str(row.get("sport_gender") or "")
                        
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
                            EXPORT_COLUMNS["CHURCH_TEAM"], "ChMeetings ID", "Participant ID (WP)", "Approval_Status (WP)",
                            "Is_Member_ChM", "Photo", "Full Name", "Gender", "Age (at Event)",
                            "Mobile Phone", "Email", "sport_type", "sport_gender", "sport_format",
                            "team_order", "partner_name",
                            "Open_TEAM_Issue_Count (WP)", "Open_TEAM_Issue_Desc (WP)"
                        ]

                        # Create Full Name column
                        df_sport["Full Name"] = (
                            df_sport[EXPORT_COLUMNS["LAST_NAME"]].astype(str)
                            + " "
                            + df_sport[EXPORT_COLUMNS["FIRST_NAME"]].astype(str)
                        )

                        # Ensure all sport columns exist
                        for col in sport_cols:
                            if col not in df_sport.columns:
                                df_sport[col] = None

                        # Reindex and sort
                        df_sport = df_sport.reindex(columns=sport_cols).sort_values(
                            by=[EXPORT_COLUMNS["CHURCH_TEAM"], "sport_type", "sport_gender", "Full Name", "Approval_Status (WP)"],
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
                            except (AttributeError, TypeError, ValueError) as e:
                                # Per-cell and non-fatal: the column just keeps the
                                # width computed from its other cells. Logged at debug
                                # so a wide sheet cannot flood the run log.
                                logger.debug(f"Skipped column-width sizing for cell {cell.coordinate!r}: {e}")
                        
                        # Set width with some padding
                        adjusted_width = min(max_length + 2, 50)  # Max width of 50
                        worksheet.column_dimensions[column_letter].width = adjusted_width

                stamp_sport_export_tab_statuses(writer.book)

            logger.info(f"Successfully wrote Excel report: {filepath}")
        except Exception as e:
            logger.error(f"Failed to write Excel file {filepath}: {e}", exc_info=True)
