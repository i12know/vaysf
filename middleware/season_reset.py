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


def _build_reset_additional_fields(current_fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Return the additional_fields payload that clears every SF custom field
    that currently has a value set on the person's profile.

    Sending a null/empty reset for a field that was never filled in causes a
    500 Internal Server Error from the ChMeetings API, so we only include
    entries for fields that are actually present and non-empty.

    Args:
        current_fields: The ``additional_fields`` list from the person's
            ChMeetings profile (as returned by get_person()).
    """
    # Index current values by field_id for quick lookup
    current_by_id: Dict[int, Dict[str, Any]] = {
        f["field_id"]: f for f in current_fields if "field_id" in f
    }

    fields: List[Dict[str, Any]] = []

    for field_id in SF_CHECKBOX_FIELD_IDS:
        cur = current_by_id.get(field_id, {})
        if cur.get("selected_option_ids"):          # non-empty list
            fields.append({"field_id": field_id, "selected_option_ids": []})

    for field_id in SF_DROPDOWN_FIELD_IDS:
        cur = current_by_id.get(field_id, {})
        if cur.get("selected_option_id") is not None:
            fields.append({"field_id": field_id, "selected_option_id": None})

    for field_id in SF_TEXT_FIELD_IDS:
        cur = current_by_id.get(field_id, {})
        if cur.get("value"):                        # non-empty string
            fields.append({"field_id": field_id, "value": None})

    return fields


def _to_alt_format(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert a standard reset payload to the alternative format:
    - selected_option_id: null  →  selected_option_id: 0
    - value: null               →  value: ""
    Checkboxes (selected_option_ids: []) are left unchanged.
    """
    alt = []
    for f in fields:
        if "selected_option_id" in f:
            alt.append({"field_id": f["field_id"], "selected_option_id": 0})
        elif "value" in f:
            alt.append({"field_id": f["field_id"], "value": ""})
        else:
            alt.append(dict(f))
    return alt


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

            # Build reset payload from the person's actual current fields so we
            # only touch fields that have values — sending resets for unfilled
            # fields causes a 500 from the ChMeetings API.
            current_fields = member.get("additional_fields", [])
            reset_fields_payload = _build_reset_additional_fields(current_fields)

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
                    logger.info(f"[DRY RUN] Would reset {len(reset_fields_payload)} field(s) "
                                f"for {first_name} {last_name} ({pid}): "
                                f"{[f['field_id'] for f in reset_fields_payload]}")
                else:
                    if not reset_fields_payload:
                        logger.info(f"No SF fields with values found for {first_name} {last_name} ({pid}) — nothing to reset.")
                    else:
                        ok = self._reset_fields_with_fallback(pid, first_name, last_name, reset_fields_payload)
                        if not ok:
                            logger.warning(f"Failed to reset fields for {pid}")
                            errors += 1

        logger.info(f"Season reset complete. Members processed: {len(members)}, errors: {errors}.")
        return errors == 0

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _reset_fields_with_fallback(
        self,
        pid: str,
        first_name: str,
        last_name: str,
        fields: List[Dict[str, Any]],
    ) -> bool:
        """
        Reset custom fields with automatic format fallbacks.

        The ChMeetings API spec says use null/[] to clear fields, but in
        practice a generic 500 is returned when null is sent for
        selected_option_id.  This method tries three escalating strategies:

        1. **Standard bulk** — null / 0-length list as per spec
        2. **Alternative bulk** — 0 for option IDs, "" for text values
        3. **Field-by-field** — each field individually, cycling through
           both format options, so partial success is still captured

        The first strategy that fully succeeds is used.  Field-by-field
        logging tells you exactly which field/format works, which is
        useful for diagnosing API behaviour differences between field types.
        """
        # ── Strategy 1: standard bulk (null / []) ──────────────────────
        if self.chm.update_person(pid, first_name, last_name, fields):
            logger.info(f"Bulk reset (standard) succeeded for {pid}.")
            return True

        # ── Strategy 2: alternative bulk (0 / "") ──────────────────────
        alt_fields = _to_alt_format(fields)
        logger.warning(
            f"Standard bulk reset failed for {pid} — "
            f"retrying with alternative format (0 / empty-string)."
        )
        if self.chm.update_person(pid, first_name, last_name, alt_fields):
            logger.info(f"Bulk reset (alternative format) succeeded for {pid}.")
            return True

        # ── Strategy 3: field-by-field with format cycling ─────────────
        logger.warning(
            f"Alternative bulk reset also failed for {pid} — "
            f"falling back to field-by-field reset."
        )
        field_errors = 0
        for std_field, alt_field in zip(fields, alt_fields):
            field_id = std_field["field_id"]
            # Try standard format first, then alternative
            for attempt, candidate in enumerate((std_field, alt_field), start=1):
                if self.chm.update_person(pid, first_name, last_name, [candidate]):
                    logger.info(
                        f"  field_id {field_id}: cleared with format #{attempt} — {candidate}"
                    )
                    break
                logger.debug(f"  field_id {field_id}: format #{attempt} failed — {candidate}")
            else:
                logger.error(
                    f"  field_id {field_id}: ALL formats failed — field not cleared"
                )
                field_errors += 1

        return field_errors == 0

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
