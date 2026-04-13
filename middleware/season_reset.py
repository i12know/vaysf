# season_reset.py
"""
Season Reset utility — archives 2025 Sports Fest data as ChMeetings profile
notes then clears all Sports Fest and Church Rep Verification custom fields
for every VAY-SM member, so the 2026 registration cycle starts clean.

Usage (via main.py):
    python main.py reset-season --year 2025              # archive + reset
    python main.py reset-season --year 2025 --dry-run    # preview only
    python main.py reset-season --year 2025 --archive-only
    python main.py reset-season --year 2025 --reset-only
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from tqdm import tqdm

from chmeetings.backend_connector import ChMeetingsConnector
from wordpress.frontend_connector import WordPressConnector
from config import (
    Config,
    SF_FIELD_IDS,
    SF_CHECKBOX_FIELD_IDS,
    SF_DROPDOWN_FIELD_IDS,
    SF_TEXT_FIELD_IDS,
    SF_CHURCH_TEAM_OPTIONS,
    SF_PRIMARY_SPORT_OPTIONS,
    SF_SECONDARY_SPORT_OPTIONS,
    SF_MY_ROLE_OPTIONS,
    SF_OTHER_EVENTS_OPTIONS,
    SF_AGE_VERIFICATION_OPTIONS,
    SF_CHECKLIST_OPTIONS,
)


def _build_reset_additional_fields() -> List[Dict[str, Any]]:
    """Return the additional_fields payload that clears every SF custom field."""
    fields: List[Dict[str, Any]] = []

    for field_id in SF_CHECKBOX_FIELD_IDS:
        fields.append({"field_id": field_id, "selected_option_ids": []})

    for field_id in SF_DROPDOWN_FIELD_IDS:
        fields.append({"field_id": field_id, "selected_option_id": None})

    for field_id in SF_TEXT_FIELD_IDS:
        fields.append({"field_id": field_id, "value": None})

    return fields


def _resolve_option_label(option_id: Optional[int], mapping: Dict[int, str]) -> str:
    """Return the human-readable label for an option ID, or 'Unknown'."""
    if option_id is None:
        return ""
    return mapping.get(int(option_id), f"option#{option_id}")


def _build_archive_note(year: int, person: Dict[str, Any], wp_participant: Optional[Dict[str, Any]]) -> str:
    """
    Build a structured archive note combining ChMeetings custom field data
    with WordPress participant data.

    The note is formatted for easy human reading inside ChMeetings.
    """
    lines: List[str] = [f"Sports Fest {year} Archive — {datetime.date.today().isoformat()}"]

    # --- Data from WordPress sf_participants ---
    if wp_participant:
        church_code   = wp_participant.get("church_code", "")
        primary_sport = wp_participant.get("primary_sport", "")
        primary_fmt   = wp_participant.get("primary_format", "")
        primary_prt   = wp_participant.get("primary_partner", "")
        sec_sport     = wp_participant.get("secondary_sport", "")
        sec_fmt       = wp_participant.get("secondary_format", "")
        sec_prt       = wp_participant.get("secondary_partner", "")
        other_events  = wp_participant.get("other_events", "")
        is_member     = "Yes" if wp_participant.get("is_church_member") else "No"
        approval      = wp_participant.get("approval_status", "")
        parent_info   = wp_participant.get("parent_info", "")

        lines.append(f"Team: {church_code}")
        lines.append(f"Primary: {primary_sport}" + (f" ({primary_fmt})" if primary_fmt else "") +
                     (f" w/ {primary_prt}" if primary_prt else ""))
        lines.append(f"Secondary: {sec_sport}" + (f" ({sec_fmt})" if sec_fmt else "") +
                     (f" w/ {sec_prt}" if sec_prt else ""))
        if other_events:
            lines.append(f"Other: {other_events}")
        lines.append(f"Member: {is_member}")
        lines.append(f"Pastor Approved: {approval}")
        if parent_info:
            lines.append(f"Parent/Guardian: {parent_info}")
    else:
        lines.append("(No WordPress participant record found)")

    # --- Checklist data from ChMeetings additional_fields ---
    additional_fields = person.get("additional_fields", [])
    checklist_ids: List[int] = []
    for field in additional_fields:
        if field.get("field_id") == SF_FIELD_IDS["CHECKLIST"]:
            checklist_ids = [int(x) for x in (field.get("selected_option_ids") or [])]

    if checklist_ids or wp_participant:
        checklist_summary = " ".join(
            f"{idx+1}{'✓' if opt_id in checklist_ids else '✗'}"
            for idx, opt_id in enumerate(sorted(SF_CHECKLIST_OPTIONS.keys()))
        )
        lines.append(f"Checklist: {checklist_summary}")

    return " | ".join(lines)


class SeasonResetter:
    """Orchestrates the season-reset workflow for Sports Fest."""

    def __init__(
        self,
        chm_connector: ChMeetingsConnector,
        wp_connector: WordPressConnector,
    ) -> None:
        self.chm = chm_connector
        self.wp  = wp_connector

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    def run(
        self,
        year: int,
        *,
        dry_run: bool = False,
        archive_only: bool = False,
        reset_only: bool = False,
        person_id: Optional[str] = None,
    ) -> bool:
        """
        Execute the season reset.

        Args:
            year: The season year being archived/reset (e.g. 2025).
            dry_run: If True, log what would happen but make no changes.
            archive_only: If True, write archive notes but skip field reset.
            reset_only: If True, skip archive notes and only clear fields.
            person_id: If given, process only this one ChMeetings person ID
                instead of the entire VAY-SM group.  Useful for spot-testing.

        Returns:
            True if the operation completed without fatal errors.
        """
        mode_tag = "[DRY RUN] " if dry_run else ""
        scope = f"person {person_id}" if person_id else "all VAY-SM members"
        logger.info(f"{mode_tag}Season reset for {year} — scope: {scope} "
                    f"(archive={'yes' if not reset_only else 'no'}, "
                    f"reset={'yes' if not archive_only else 'no'})")

        # Step 1 — resolve the member list
        if person_id:
            member = self.chm.get_person(person_id)
            if not member:
                logger.error(f"Person {person_id} not found in ChMeetings; aborting.")
                return False
            members = [member]
        else:
            members = self._get_vaysm_members(Config.VAYSM_GROUP_ID)
            if not members:
                logger.error("No VAY-SM members found; aborting reset.")
                return False

        logger.info(f"Processing {len(members)} member(s).")

        # Step 2 — fetch WordPress participants for archive enrichment
        wp_participants_by_chmid: Dict[str, Dict[str, Any]] = {}
        if not reset_only:
            wp_participants_by_chmid = self._fetch_wp_participants_by_chmid()

        # Step 3 — process each member
        reset_fields_payload = _build_reset_additional_fields()
        errors = 0
        archive_note_prefix = f"Sports Fest {year} Archive"

        for member in tqdm(members, desc="Processing members", unit="person"):
            pid        = str(member.get("id") or member.get("person_id", ""))
            first_name = member.get("first_name", "")
            last_name  = member.get("last_name", "")
            if not pid:
                logger.warning(f"Skipping member with no ID: {member}")
                errors += 1
                continue

            # a. Archive step
            if not reset_only:
                wp_participant = wp_participants_by_chmid.get(pid)
                note = _build_archive_note(year, member, wp_participant)
                if dry_run:
                    logger.info(f"[DRY RUN] Would archive {first_name} {last_name} ({pid}):\n  {note}")
                else:
                    # Guard against duplicates: skip if an archive note for this
                    # year already exists on the profile.
                    existing_notes = self.chm.get_person_notes(pid)
                    already_archived = any(
                        archive_note_prefix in str(n.get("note", "") or n.get("content", "") or n.get("body", ""))
                        for n in existing_notes
                    )
                    if already_archived:
                        logger.info(f"Archive note for {year} already exists on {pid} — skipping.")
                    else:
                        ok = self.chm.add_member_note(pid, note)
                        if not ok:
                            logger.warning(f"Failed to write archive note for {pid}")
                            errors += 1

            # b. Reset step
            if not archive_only:
                if dry_run:
                    logger.info(f"[DRY RUN] Would reset {len(reset_fields_payload)} fields "
                                f"for {first_name} {last_name} ({pid})")
                else:
                    ok = self.chm.update_person(pid, first_name, last_name, reset_fields_payload)
                    if not ok:
                        logger.warning(f"Failed to reset fields for {pid}")
                        errors += 1

        logger.info(f"Season reset complete. Members processed: {len(members)}, errors: {errors}.")
        return errors == 0

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get_vaysm_members(self, group_id: str) -> List[Dict[str, Any]]:
        """Fetch all members of the VAY-SM group from ChMeetings."""
        logger.info(f"Fetching VAY-SM members from group {group_id}")
        members = self.chm.get_group_people(group_id)
        return members

    def _fetch_wp_participants_by_chmid(self) -> Dict[str, Dict[str, Any]]:
        """
        Pull all sf_participants from WordPress and index them by chmeetings_id.
        """
        logger.info("Fetching WordPress participants for archive enrichment")
        try:
            participants = self.wp.get_participants() or []
        except Exception as e:
            logger.warning(f"Could not fetch WordPress participants: {e}")
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        for p in participants:
            chmid = str(p.get("chmeetings_id") or "")
            if chmid:
                result[chmid] = p
        logger.info(f"Indexed {len(result)} WordPress participants by ChMeetings ID")
        return result
