# middleware/group_assignment.py
import os
import sys
import time
from typing import Dict, List, Optional
import pandas as pd
from loguru import logger
from config import Config, CHM_FIELDS, DATA_DIR

# Add parent directory to import path to access other modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from chmeetings.backend_connector import ChMeetingsConnector


def _team_group_prefix() -> str:
    """Return the exact prefix that identifies seasonal team groups."""
    return f"{Config.TEAM_PREFIX} "


def _is_team_group(group_name: str) -> bool:
    """True only for church team groups such as 'Team RPC'."""
    return group_name.startswith(_team_group_prefix())


def _team_group_name(church_code: str) -> str:
    """Build the canonical ChMeetings team-group name for a church code."""
    return f"{_team_group_prefix()}{church_code.strip().upper()}"


def _write_audit_file(filename: str, rows: List[Dict[str, str]]) -> None:
    """Write an Excel audit file to the middleware data directory."""
    output_dir = DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    audit_file = os.path.join(output_dir, filename)
    try:
        pd.DataFrame(rows).to_excel(audit_file, index=False)
        logger.info(f"Audit file written: {audit_file}")
    except PermissionError:
        logger.warning(
            f"Could not write audit file - {audit_file} is open in another program. "
            "Close the file and re-run to get an updated audit log. "
            "API calls already made above are unaffected."
        )


def assign_people_to_church_team_groups(dry_run: bool = False) -> bool:
    """
    Assign people in ChMeetings to their church team groups via direct API calls.

    Identifies people who have a church code in their ChMeetings profile but are
    not yet members of the corresponding "Team XYZ" group, then calls
    add_person_to_group() for each one.

    Args:
        dry_run: If True, only generate the audit file — no API calls are made.

    Returns:
        True if the run succeeded with zero API failures.
        False if authentication failed, an unexpected error occurred,
        or any add_person_to_group() call returned False.
    """
    logger.info(f"Starting church team group assignment (dry_run={dry_run})...")

    with ChMeetingsConnector() as chm_connector:
        if not chm_connector.authenticate():
            logger.error("Authentication with ChMeetings failed")
            return False

        # --- Identification (unchanged logic) ---
        all_people = chm_connector.get_people()
        logger.info(f"Retrieved {len(all_people)} people from ChMeetings")

        all_groups = chm_connector.get_groups()
        team_groups = [g for g in all_groups if _is_team_group(g.get("name", ""))]

        # Build name → id lookup for fast group resolution
        team_group_by_name = {g["name"]: str(g["id"]) for g in team_groups}

        # Build set of people already in a team group
        people_in_teams = set()
        for group in team_groups:
            for person in chm_connector.get_group_people(group["id"]):
                people_in_teams.add(str(person.get("person_id")))

        logger.info(f"Found {len(people_in_teams)} people already in team groups")

        # Collect people needing assignment
        people_for_assignment = []
        for person in all_people:
            person_id = str(person.get("id"))
            if person_id in people_in_teams:
                continue

            # Get all additional fields
            additional_fields = {f["field_name"]: f["value"] for f in person.get("additional_fields", [])}

            # Check if they have a church code
            church_code = additional_fields.get(CHM_FIELDS["CHURCH_TEAM"], "").strip().upper()
            if church_code:
                people_for_assignment.append({
                    "person_id": person_id,
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "email": person.get("email", ""),
                    "church_code": church_code,
                    "target_group": _team_group_name(church_code),
                })

        logger.info(f"Found {len(people_for_assignment)} people needing team assignment")

        if not people_for_assignment:
            logger.info("No people need team assignment — nothing to do.")
            return True

        # --- Action ---
        added = 0
        failed = 0
        missing_group = 0
        audit_rows = []

        for person in people_for_assignment:
            target_group_name = person["target_group"]
            group_id = team_group_by_name.get(target_group_name)

            if group_id is None:
                logger.warning(
                    f"Group '{target_group_name}' not found in ChMeetings - "
                    f"skipping {person['first_name']} {person['last_name']} "
                    f"(id={person['person_id']})"
                )
                missing_group += 1
                outcome = "missing_group"
            elif dry_run:
                logger.info(
                    f"[dry-run] Would add {person['first_name']} {person['last_name']} "
                    f"(id={person['person_id']}) to {target_group_name}"
                )
                outcome = "dry_run"
            else:
                ok = chm_connector.add_person_to_group(group_id, person["person_id"])
                time.sleep(0.2)  # 200 ms between calls — avoids 429 rate limit
                if ok:
                    added += 1
                    outcome = "added"
                else:
                    failed += 1
                    outcome = "failed"

            audit_rows.append({
                "Person Id": person["person_id"],
                "First Name": person["first_name"],
                "Last Name": person["last_name"],
                "Email": person["email"],
                "Church Code": person["church_code"],
                "Target Group": target_group_name,
                "Outcome": outcome,
            })

        # Always write audit file (both live and dry-run)
        _write_audit_file("church_team_assignments.xlsx", audit_rows)

        if dry_run:
            logger.info(
                f"[dry-run] Would assign {len(people_for_assignment)} people "
                f"({missing_group} with missing group). No API calls made."
            )
        else:
            logger.info(
                f"Group assignment complete: {added} added, {failed} failed, "
                f"{missing_group} skipped (group not found in ChMeetings)."
            )

        return failed == 0


def clear_team_groups(
    church_code: Optional[str] = None,
    dry_run: bool = True,
    execute: bool = False,
) -> bool:
    """
    Clear memberships from seasonal Team XXX groups via the ChMeetings API.

    Args:
        church_code: Optional church code to limit the operation to one Team XXX group.
        dry_run: If True, preview removals only and write an audit file.
        execute: Must be True for live API deletions.

    Returns:
        True if the run succeeded with zero API failures.
        False if authentication failed, execution was not explicitly confirmed,
        or any remove_person_from_group() call returned False.
    """
    normalized_code = church_code.strip().upper() if church_code else None
    logger.info(
        f"Starting team-group clear run (church_code={normalized_code or 'ALL'}, "
        f"dry_run={dry_run}, execute={execute})..."
    )

    if not dry_run and not execute:
        logger.error("Live clearing requires --execute. Use --dry-run for preview mode.")
        return False

    with ChMeetingsConnector() as chm_connector:
        if not chm_connector.authenticate():
            logger.error("Authentication with ChMeetings failed")
            return False

        all_groups = chm_connector.get_groups()
        team_groups = [g for g in all_groups if _is_team_group(g.get("name", ""))]

        if normalized_code:
            target_group_name = _team_group_name(normalized_code)
            team_groups = [g for g in team_groups if g.get("name") == target_group_name]
            if not team_groups:
                logger.warning(f"No team group named '{target_group_name}' was found in ChMeetings.")

        logger.info(f"Found {len(team_groups)} target team group(s) to inspect.")

        groups_processed = 0
        empty_groups = 0
        memberships_found = 0
        removed = 0
        already_absent = 0
        failed = 0
        audit_rows: List[Dict[str, str]] = []

        for group in team_groups:
            group_id = str(group["id"])
            group_name = group.get("name", "")
            groups_processed += 1

            group_people = chm_connector.get_group_people(group_id)
            if not group_people:
                empty_groups += 1
                logger.info(f"Group '{group_name}' is already empty.")
                audit_rows.append({
                    "Group Id": group_id,
                    "Group Name": group_name,
                    "Person Id": "",
                    "First Name": "",
                    "Last Name": "",
                    "Email": "",
                    "Outcome": "empty_group",
                })
                continue

            memberships_found += len(group_people)

            for person in group_people:
                person_id = str(person.get("person_id") or person.get("id") or "")
                first_name = person.get("first_name", "")
                last_name = person.get("last_name", "")
                email = person.get("email", "")

                if dry_run:
                    logger.info(
                        f"[dry-run] Would remove {first_name} {last_name} "
                        f"(id={person_id}) from {group_name}"
                    )
                    outcome = "dry_run"
                else:
                    ok = chm_connector.remove_person_from_group(
                        group_id, person_id, not_found_ok=True
                    )
                    time.sleep(0.2)  # 200 ms between calls - avoids 429 rate limit
                    if ok:
                        delete_status = getattr(
                            chm_connector, "last_group_membership_delete_status", "removed"
                        )
                        if delete_status == "already_absent":
                            already_absent += 1
                            outcome = "already_absent"
                        else:
                            removed += 1
                            outcome = "removed"
                    else:
                        failed += 1
                        outcome = "failed"

                audit_rows.append({
                    "Group Id": group_id,
                    "Group Name": group_name,
                    "Person Id": person_id,
                    "First Name": first_name,
                    "Last Name": last_name,
                    "Email": email,
                    "Outcome": outcome,
                })

        _write_audit_file("team_group_clearing_audit.xlsx", audit_rows)

        if dry_run:
            logger.info(
                f"[dry-run] Reviewed {groups_processed} group(s), found {memberships_found} "
                f"membership(s), and would remove them. Empty groups: {empty_groups}."
            )
        else:
            logger.info(
                f"Team-group clearing complete: {groups_processed} group(s) processed, "
                f"{removed} removed, {already_absent} already absent, "
                f"{failed} failed, {empty_groups} already empty."
            )

        return failed == 0


# Back-compat alias — main.py imports this name
export_people_with_church_codes = assign_people_to_church_team_groups


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Assign ChMeetings people to church team groups"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview only — no API calls, audit xlsx still written"
    )
    script_args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(os.path.join(current_dir, "logs", "group_assignment.log"), rotation="10 MB")

    try:
        success = assign_people_to_church_team_groups(dry_run=script_args.dry_run)
        if not success:
            sys.exit(1)
    except Exception as e:
        logger.exception(f"Error in group assignment process: {e}")
        sys.exit(1)
