# middleware/group_assignment.py
import html
import os
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from loguru import logger
from config import (
    Config, CHM_FIELDS, DATA_DIR,
    MEMBERSHIP_QUESTION,
    SF_FIELD_IDS,
    SF_CHURCH_TEAM_OPTIONS,
    SF_MY_ROLE_OPTIONS,
    SF_PRIMARY_SPORT_OPTIONS,
    SF_SECONDARY_SPORT_OPTIONS,
    SF_OTHER_EVENTS_OPTIONS,
    SF_AGE_VERIFICATION_OPTIONS,
    SF_IS_MEMBER_OPTION_IDS,
)

# Add parent directory to import path to access other modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from chmeetings.backend_connector import ChMeetingsConnector, ChMeetingsReadError
from wordpress.frontend_connector import WordPressConnector


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


def _normalize_text(value: Optional[str]) -> str:
    if pd.isna(value):
        return ""
    return str(value or "").strip().lower()


def _normalize_phone(value: Optional[str]) -> str:
    if pd.isna(value):
        return ""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _clean_cell(value: Optional[str]) -> str:
    if pd.isna(value):
        return ""
    return str(value or "").strip()


def _row_first_clean(row: pd.Series, *columns: str) -> str:
    for column in columns:
        value = _clean_cell(row.get(column, ""))
        if value:
            return value
    return ""


def _load_source_export_rows(source_file: str) -> List[Dict[str, str]]:
    """Load current-season registrants from an Individual Application export."""
    df = pd.read_excel(source_file)
    required_columns = ["First Name", "Last Name", "Church Team"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s) in source export: {missing}")

    rows: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        church_code = str(row.get("Church Team", "") or "").strip().upper()
        if not church_code:
            continue
        rows.append({
            "source_row": str(int(row.name) + 2),
            "first_name": _clean_cell(row.get("First Name", "")),
            "last_name": _clean_cell(row.get("Last Name", "")),
            "email": _normalize_text(row.get("Email", "")),
            "email_display": _clean_cell(row.get("Email", "")),
            "mobile_phone": _normalize_phone(row.get("Mobile Phone", "")),
            "mobile_phone_display": _clean_cell(row.get("Mobile Phone", "")),
            "gender": _clean_cell(row.get("Gender", "")),
            "birth_date": _parse_form_date(row.get("Birthdate", "")),
            "church_code": church_code,
            "role": _clean_cell(row.get("My role is", "")),
            "is_member": _row_first_clean(
                row,
                MEMBERSHIP_QUESTION,
                "Would the church pastor say that you belong to his church?",
            ),
            "age_verification": _clean_cell(row.get("Age verification (by the date of Sports Fest)", "")),
            "parent_name": _clean_cell(row.get(CHM_FIELDS["PARENT_NAME"], "")),
            "parent_email": _clean_cell(row.get(CHM_FIELDS["PARENT_EMAIL"], "")),
            "parent_phone": _clean_cell(row.get(CHM_FIELDS["PARENT_PHONE"], "")),
            "additional_info": _clean_cell(row.get("Additional Info", "")),
            "submission_date": _clean_cell(row.get("Submission Date", "")),
            "primary_sport": _clean_cell(row.get("Primary Sport", "")),
            "secondary_sport": _clean_cell(row.get("Secondary Sport", "")),
            "other_events": _clean_cell(row.get("Other Events", "")),
        })
    return rows


def _index_people_for_form_audit(
    people: List[Dict[str, str]],
) -> Dict[str, Dict[object, List[Dict[str, str]]]]:
    people_by_email: Dict[object, List[Dict[str, str]]] = {}
    people_by_phone_name: Dict[object, List[Dict[str, str]]] = {}
    people_by_name: Dict[object, List[Dict[str, str]]] = {}

    for person in people:
        first_name = _normalize_text(person.get("first_name", ""))
        last_name = _normalize_text(person.get("last_name", ""))
        email = _normalize_text(person.get("email", ""))
        mobile = _normalize_phone(person.get("mobile", ""))

        if email:
            people_by_email.setdefault(email, []).append(person)
        if mobile:
            people_by_phone_name.setdefault((mobile, first_name, last_name), []).append(person)
        people_by_name.setdefault((first_name, last_name), []).append(person)

    return {
        "email": people_by_email,
        "phone_name": people_by_phone_name,
        "name": people_by_name,
    }


def _source_row_people_match(
    row: Dict[str, str],
    people_index: Dict[str, Dict[object, List[Dict[str, str]]]],
) -> Tuple[str, List[Dict[str, str]]]:
    first_name = _normalize_text(row.get("first_name", ""))
    last_name = _normalize_text(row.get("last_name", ""))
    email = _normalize_text(row.get("email", ""))
    mobile = _normalize_phone(row.get("mobile_phone", ""))

    if email:
        matches = people_index["email"].get(email, [])
        if matches:
            return "matched_email", matches

    if mobile:
        matches = people_index["phone_name"].get((mobile, first_name, last_name), [])
        if matches:
            return "matched_phone_name", matches

    matches = people_index["name"].get((first_name, last_name), [])
    if len(matches) == 1:
        return "matched_name_only", matches
    if len(matches) > 1:
        return "ambiguous_name_only", matches
    return "missing_person", []


# ── Label-to-option-id reverse maps for repair payload building ──────────────
# Inverted at module load from the authoritative config dicts.
# All lookups are exact-string; callers must unescape HTML entities first.
_CHURCH_CODE_TO_OPTION_ID: Dict[str, int] = {v: k for k, v in SF_CHURCH_TEAM_OPTIONS.items()}
_ROLE_LABEL_TO_OPTION_ID: Dict[str, int]  = {v: k for k, v in SF_MY_ROLE_OPTIONS.items()}
_PRIMARY_SPORT_LABEL_TO_OPTION_ID: Dict[str, int]    = {v: k for k, v in SF_PRIMARY_SPORT_OPTIONS.items()}
_SECONDARY_SPORT_LABEL_TO_OPTION_ID: Dict[str, int]  = {v: k for k, v in SF_SECONDARY_SPORT_OPTIONS.items()}
_OTHER_EVENTS_LABEL_TO_OPTION_ID: Dict[str, int]     = {v: k for k, v in SF_OTHER_EVENTS_OPTIONS.items()}
_AGE_VERIFICATION_LABEL_TO_OPTION_ID: Dict[str, int] = {v: k for k, v in SF_AGE_VERIFICATION_OPTIONS.items()}
_IS_MEMBER_LABEL_TO_OPTION_ID: Dict[str, int] = {
    label.strip(): option_id
    for label, option_id in SF_IS_MEMBER_OPTION_IDS.items()
    if option_id
}

_ADDITIONAL_FIELD_PAYLOAD_KEYS = (
    "field_id",
    "field_type",
    "selected_option_id",
    "selected_option_ids",
    "value",
)

_SF_FIELD_TYPE_BY_ID: Dict[int, str] = {
    SF_FIELD_IDS["MY_ROLE"]: "checkbox",
    SF_FIELD_IDS["CHURCH_TEAM"]: "dropdown",
    SF_FIELD_IDS["IS_MEMBER"]: "multiple_choice",
    SF_FIELD_IDS["PRIMARY_SPORT"]: "dropdown",
    SF_FIELD_IDS["PRIMARY_FORMAT"]: "dropdown",
    SF_FIELD_IDS["PRIMARY_PARTNER"]: "text",
    SF_FIELD_IDS["SECONDARY_SPORT"]: "dropdown",
    SF_FIELD_IDS["SECONDARY_FORMAT"]: "dropdown",
    SF_FIELD_IDS["SECONDARY_PARTNER"]: "text",
    SF_FIELD_IDS["OTHER_EVENTS"]: "checkbox",
    SF_FIELD_IDS["AGE_VERIFICATION"]: "multiple_choice",
    SF_FIELD_IDS["PARENT_NAME"]: "text",
    SF_FIELD_IDS["PARENT_EMAIL"]: "text",
    SF_FIELD_IDS["PARENT_PHONE"]: "text",
    SF_FIELD_IDS["ADDITIONAL_INFO"]: "multi_line_text",
}

_FORM_FIELD_NAME_BY_ID: Dict[int, str] = {
    SF_FIELD_IDS["MY_ROLE"]: CHM_FIELDS["ROLES"],
    SF_FIELD_IDS["CHURCH_TEAM"]: CHM_FIELDS["CHURCH_TEAM"],
    SF_FIELD_IDS["IS_MEMBER"]: MEMBERSHIP_QUESTION,
    SF_FIELD_IDS["PRIMARY_SPORT"]: CHM_FIELDS["PRIMARY_SPORT"],
    SF_FIELD_IDS["PRIMARY_PARTNER"]: CHM_FIELDS["PRIMARY_PARTNER"],
    SF_FIELD_IDS["SECONDARY_SPORT"]: CHM_FIELDS["SECONDARY_SPORT"],
    SF_FIELD_IDS["SECONDARY_PARTNER"]: CHM_FIELDS["SECONDARY_PARTNER"],
    SF_FIELD_IDS["OTHER_EVENTS"]: CHM_FIELDS["OTHER_EVENTS"],
    SF_FIELD_IDS["AGE_VERIFICATION"]: "Age verification (by the date of Sports Fest)",
    SF_FIELD_IDS["PARENT_NAME"]: CHM_FIELDS["PARENT_NAME"],
    SF_FIELD_IDS["PARENT_EMAIL"]: CHM_FIELDS["PARENT_EMAIL"],
    SF_FIELD_IDS["PARENT_PHONE"]: CHM_FIELDS["PARENT_PHONE"],
    SF_FIELD_IDS["ADDITIONAL_INFO"]: "Additional Info",
}


def _field_id(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_labels(raw_value: str) -> str:
    labels = [label.strip() for label in html.unescape(raw_value or "").split(",") if label.strip()]
    return ", ".join(labels)


def _parse_form_date(value: Optional[str]) -> str:
    """Return a ChMeetings date string (YYYY-MM-DD) from a form/export cell."""
    if pd.isna(value):
        return ""
    if hasattr(value, "date"):
        return value.date().isoformat()

    raw = str(value or "").strip()
    if not raw:
        return ""

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return pd.to_datetime(raw, format=fmt).date().isoformat()
        except (TypeError, ValueError):
            pass

    try:
        return pd.to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _load_repair_extra_cols(source_file: str) -> Dict[str, Dict[str, str]]:
    """Return racquet partner/format columns indexed by source_row key (e.g. '2').

    Returns an empty dict on failure — these columns are optional for the
    create payload so a missing or corrupt column should not abort a repair run.
    """
    try:
        df = pd.read_excel(source_file)
        result: Dict[str, Dict[str, str]] = {}
        for i, row in df.iterrows():
            row_key = str(int(i) + 2)
            result[row_key] = {
                "primary_format":   _clean_cell(row.get(CHM_FIELDS["PRIMARY_FORMAT"],   "")),
                "primary_partner":  _clean_cell(row.get(CHM_FIELDS["PRIMARY_PARTNER"],  "")),
                "secondary_format": _clean_cell(row.get(CHM_FIELDS["SECONDARY_FORMAT"], "")),
                "secondary_partner":_clean_cell(row.get(CHM_FIELDS["SECONDARY_PARTNER"],"" )),
            }
        return result
    except Exception as exc:
        logger.warning(f"Could not load racquet extra columns from {source_file!r}: {exc}")
        return {}


def _build_form_additional_fields(
    row: Dict[str, str],
    extra_cols: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Build Sports Fest custom field payload from a form export source row."""
    extra = extra_cols or {}
    first_name = row.get("first_name", "").strip()
    last_name = row.get("last_name", "").strip()

    church_code = row.get("church_code", "").strip().upper()
    church_option_id = _CHURCH_CODE_TO_OPTION_ID.get(church_code)
    if church_option_id is None:
        return None, f"church_code {church_code!r} not in SF_CHURCH_TEAM_OPTIONS"

    additional_fields: List[Dict[str, Any]] = [
        {
            "field_type": "dropdown",
            "field_id": SF_FIELD_IDS["CHURCH_TEAM"],
            "selected_option_id": church_option_id,
            "value": church_code,
        },
    ]

    # Role (checkbox, multi-select) — skip unknown labels here; if every role
    # label is unknown, the caller receives a blocked reason for the audit.
    role_str = html.unescape(row.get("role", ""))
    role_labels = [r.strip() for r in role_str.split(",") if r.strip()]
    role_option_ids = []
    for label in role_labels:
        opt_id = _ROLE_LABEL_TO_OPTION_ID.get(label)
        if opt_id is not None:
            role_option_ids.append(opt_id)
        else:
            logger.debug(
                f"Role label {label!r} not in SF_MY_ROLE_OPTIONS — "
                f"omitting from create payload for {first_name} {last_name}"
            )
    if role_option_ids:
        additional_fields.append({
            "field_type": "checkbox",
            "field_id": SF_FIELD_IDS["MY_ROLE"],
            "selected_option_ids": role_option_ids,
            "value": ", ".join(role_labels),
        })
    elif role_str:
        return None, f"role {role_str!r} not in SF_MY_ROLE_OPTIONS"

    is_member = html.unescape(row.get("is_member", "").strip())
    if is_member:
        opt_id = _IS_MEMBER_LABEL_TO_OPTION_ID.get(is_member)
        if opt_id is None:
            return None, f"membership answer {is_member!r} not in SF_IS_MEMBER_OPTION_IDS"
        additional_fields.append({
            "field_type": "multiple_choice",
            "field_id": SF_FIELD_IDS["IS_MEMBER"],
            "selected_option_id": opt_id,
            "value": is_member,
        })

    age_verification = html.unescape(row.get("age_verification", "").strip())
    if age_verification:
        opt_id = _AGE_VERIFICATION_LABEL_TO_OPTION_ID.get(age_verification)
        if opt_id is None:
            return None, f"age_verification {age_verification!r} not in SF_AGE_VERIFICATION_OPTIONS"
        additional_fields.append({
            "field_type": "multiple_choice",
            "field_id": SF_FIELD_IDS["AGE_VERIFICATION"],
            "selected_option_id": opt_id,
            "value": age_verification,
        })

    # Primary sport (dropdown) — block if label is present and unmappable.
    primary_sport = html.unescape(row.get("primary_sport", "").strip())
    if primary_sport:
        opt_id = _PRIMARY_SPORT_LABEL_TO_OPTION_ID.get(primary_sport)
        if opt_id is None:
            return None, f"primary_sport {primary_sport!r} not in SF_PRIMARY_SPORT_OPTIONS"
        additional_fields.append({
            "field_type": "dropdown",
            "field_id": SF_FIELD_IDS["PRIMARY_SPORT"],
            "selected_option_id": opt_id,
            "value": primary_sport,
        })

    # Secondary sport (dropdown) — same treatment.
    secondary_sport = html.unescape(row.get("secondary_sport", "").strip())
    if secondary_sport:
        opt_id = _SECONDARY_SPORT_LABEL_TO_OPTION_ID.get(secondary_sport)
        if opt_id is None:
            return None, f"secondary_sport {secondary_sport!r} not in SF_SECONDARY_SPORT_OPTIONS"
        additional_fields.append({
            "field_type": "dropdown",
            "field_id": SF_FIELD_IDS["SECONDARY_SPORT"],
            "selected_option_id": opt_id,
            "value": secondary_sport,
        })

    # Other events (checkbox, multi-select) — block if any single label is unmappable.
    other_events_str = html.unescape(row.get("other_events", "").strip())
    if other_events_str:
        other_labels = [e.strip() for e in other_events_str.split(",") if e.strip()]
        other_ids: List[int] = []
        for label in other_labels:
            opt_id = _OTHER_EVENTS_LABEL_TO_OPTION_ID.get(label)
            if opt_id is None:
                return None, f"other_events label {label!r} not in SF_OTHER_EVENTS_OPTIONS"
            other_ids.append(opt_id)
        if other_ids:
            additional_fields.append({
                "field_type": "checkbox",
                "field_id": SF_FIELD_IDS["OTHER_EVENTS"],
                "selected_option_ids": other_ids,
                "value": ", ".join(other_labels),
            })

    # Racquet partner text fields (optional) — skip gracefully if absent.
    primary_partner = extra.get("primary_partner", "").strip()
    if primary_partner:
        additional_fields.append({
            "field_type": "text",
            "field_id": SF_FIELD_IDS["PRIMARY_PARTNER"],
            "value": primary_partner,
        })
    secondary_partner = extra.get("secondary_partner", "").strip()
    if secondary_partner:
        additional_fields.append({
            "field_type": "text",
            "field_id": SF_FIELD_IDS["SECONDARY_PARTNER"],
            "value": secondary_partner,
        })

    # Racquet format dropdowns have field IDs but no option-id maps in config.
    # Block instead of creating an incomplete racquet registration.
    for fmt_key in ("primary_format", "secondary_format"):
        fmt_val = extra.get(fmt_key, "").strip()
        if fmt_val:
            return None, (
                f"{fmt_key} value {fmt_val!r} present but format option_ids are not yet "
                "mapped in config.py"
            )

    for row_key, field_key in [
        ("parent_name", "PARENT_NAME"),
        ("parent_email", "PARENT_EMAIL"),
        ("parent_phone", "PARENT_PHONE"),
        ("additional_info", "ADDITIONAL_INFO"),
    ]:
        value = row.get(row_key, "").strip()
        if value:
            additional_fields.append({
                "field_type": "multi_line_text" if field_key == "ADDITIONAL_INFO" else "text",
                "field_id": SF_FIELD_IDS[field_key],
                "value": value,
            })

    return additional_fields, None


def _form_field_display_values(
    row: Dict[str, str],
    extra_cols: Optional[Dict[str, str]] = None,
) -> Dict[int, str]:
    """Return human-readable source values keyed by ChMeetings field_id."""
    extra = extra_cols or {}
    values: Dict[int, str] = {}

    church_code = row.get("church_code", "").strip().upper()
    if church_code:
        values[SF_FIELD_IDS["CHURCH_TEAM"]] = church_code

    role = _format_labels(row.get("role", ""))
    if role:
        values[SF_FIELD_IDS["MY_ROLE"]] = role

    is_member = html.unescape(row.get("is_member", "").strip())
    if is_member:
        values[SF_FIELD_IDS["IS_MEMBER"]] = is_member

    age_verification = html.unescape(row.get("age_verification", "").strip())
    if age_verification:
        values[SF_FIELD_IDS["AGE_VERIFICATION"]] = age_verification

    primary_sport = html.unescape(row.get("primary_sport", "").strip())
    if primary_sport:
        values[SF_FIELD_IDS["PRIMARY_SPORT"]] = primary_sport

    secondary_sport = html.unescape(row.get("secondary_sport", "").strip())
    if secondary_sport:
        values[SF_FIELD_IDS["SECONDARY_SPORT"]] = secondary_sport

    other_events = _format_labels(row.get("other_events", ""))
    if other_events:
        values[SF_FIELD_IDS["OTHER_EVENTS"]] = other_events

    for extra_key, field_key in [
        ("primary_partner", "PRIMARY_PARTNER"),
        ("secondary_partner", "SECONDARY_PARTNER"),
    ]:
        value = extra.get(extra_key, "").strip()
        if value:
            values[SF_FIELD_IDS[field_key]] = value

    for row_key, field_key in [
        ("parent_name", "PARENT_NAME"),
        ("parent_email", "PARENT_EMAIL"),
        ("parent_phone", "PARENT_PHONE"),
        ("additional_info", "ADDITIONAL_INFO"),
    ]:
        value = row.get(row_key, "").strip()
        if value:
            values[SF_FIELD_IDS[field_key]] = value

    return values


def _build_create_payload(
    row: Dict[str, str],
    extra_cols: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Build a CreatePersonDto payload from a form export source row.

    Returns ``(payload, None)`` on success or ``(None, blocked_reason)`` when a
    required field label cannot be mapped to a ChMeetings option_id.  An
    unmappable required label is treated as a hard block (fail-closed) so the
    caller can report it rather than create a partially-populated record.
    """
    first_name = row.get("first_name", "").strip()
    last_name  = row.get("last_name", "").strip()
    if not first_name or not last_name:
        return None, "missing name"

    additional_fields, blocked_reason = _build_form_additional_fields(row, extra_cols)
    if blocked_reason:
        return None, blocked_reason

    assert additional_fields is not None

    payload: Dict[str, Any] = {"first_name": first_name, "last_name": last_name}
    email_display = row.get("email_display", "").strip()
    mobile_display = row.get("mobile_phone_display", "").strip()
    if email_display:
        payload["email"] = email_display
    if mobile_display:
        payload["mobile"] = mobile_display
    extra_fields: Dict[str, Any] = {}
    gender = row.get("gender", "").strip()
    birth_date = row.get("birth_date", "").strip()
    if gender:
        extra_fields["gender"] = gender
    if birth_date:
        extra_fields["birth_date"] = birth_date
    if extra_fields:
        payload["extra_fields"] = extra_fields
    payload["additional_fields"] = additional_fields

    return payload, None


def _source_identity_keys(row: Dict[str, str]) -> List[Tuple[str, str]]:
    keys: List[Tuple[str, str]] = []
    email = row.get("email", "")
    mobile = row.get("mobile_phone", "")
    name_key = f"{_normalize_text(row.get('first_name', ''))}|{_normalize_text(row.get('last_name', ''))}"
    if email:
        keys.append(("email", email))
    if mobile:
        keys.append(("phone_name", f"{mobile}|{name_key}"))
    return keys


def _duplicate_source_repair_keys(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str], List[Dict[str, str]]]:
    by_key: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for row in rows:
        for key in _source_identity_keys(row):
            by_key.setdefault(key, []).append(row)
    return {key: value for key, value in by_key.items() if len(value) > 1}


def _duplicate_source_reason(
    row: Dict[str, str],
    duplicate_keys: Dict[Tuple[str, str], List[Dict[str, str]]],
) -> Optional[str]:
    for key in _source_identity_keys(row):
        duplicates = duplicate_keys.get(key)
        if duplicates:
            rows = ", ".join(str(item.get("source_row", "")) for item in duplicates)
            churches = ", ".join(sorted({str(item.get("church_code", "")) for item in duplicates}))
            return f"duplicate source submissions by {key[0]} on rows {rows} (churches: {churches})"
    return None


def _repair_audit_row(
    row: Dict[str, str],
    outcome: str,
    outcome_detail: str,
    matches: List[Dict[str, Any]],
) -> Dict[str, str]:
    return {
        "Source Row": row.get("source_row", ""),
        "First Name": row.get("first_name", ""),
        "Last Name": row.get("last_name", ""),
        "Email": row.get("email_display", ""),
        "Mobile Phone": row.get("mobile_phone_display", ""),
        "Gender": row.get("gender", ""),
        "Birthdate": row.get("birth_date", ""),
        "Church Code": row.get("church_code", ""),
        "Role": row.get("role", ""),
        "Membership Answer": row.get("is_member", ""),
        "Age Verification": row.get("age_verification", ""),
        "Parent Name": row.get("parent_name", ""),
        "Parent Email": row.get("parent_email", ""),
        "Parent Phone": row.get("parent_phone", ""),
        "Submission Date": row.get("submission_date", ""),
        "Primary Sport": row.get("primary_sport", ""),
        "Secondary Sport": row.get("secondary_sport", ""),
        "Other Events": row.get("other_events", ""),
        "Outcome": outcome,
        "Outcome Detail": outcome_detail,
        "Existing ChM IDs": ", ".join(str(p.get("id", "")) for p in matches),
    }


def repair_form_people(
    source_file: str,
    *,
    dry_run: bool = True,
    chm_email: Optional[str] = None,
    execute: bool = False,
    people: Optional[List[Dict[str, Any]]] = None,
    groups: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Create missing ChMeetings People records from Individual Application form rows.

    Performs a fresh live re-check first so the repair set reflects current
    ChMeetings state, not a stale audit file.  Only rows that are still
    ``missing_person`` after the re-check are eligible for creation.

    Args:
        source_file: Path to the Individual Application form export xlsx.
        dry_run: If True (default), log what would be done without any writes.
        chm_email: Restrict the run to a single form row by email address.
        execute: Must be True for any live creates or group-add calls.
        people: Pre-fetched people list (injected in tests to skip get_people()).
        groups: Pre-fetched groups list (injected in tests to skip get_groups()).

    Returns:
        Dict with integer counts: ``created``, ``linked``, ``skipped``,
        ``blocked``, ``errored``.
    """
    empty: Dict[str, int] = {
        "created": 0,
        "linked": 0,
        "skipped": 0,
        "skipped_matched": 0,
        "dry_run": 0,
        "blocked": 0,
        "errored": 0,
    }

    if not dry_run and not execute:
        logger.error("repair-form-people requires --dry-run or --execute.")
        return empty

    try:
        source_rows = _load_source_export_rows(source_file)
    except Exception as exc:
        logger.error(f"Failed to load source export {source_file!r}: {exc}")
        return empty

    extra_cols_by_row = _load_repair_extra_cols(source_file)

    if chm_email:
        target = _normalize_text(chm_email)
        source_rows = [r for r in source_rows if r["email"] == target]
        if not source_rows:
            logger.warning(f"No form rows found for email {chm_email!r}")
            return empty

    counts: Dict[str, int] = {
        "created": 0,
        "linked": 0,
        "skipped": 0,
        "skipped_matched": 0,
        "dry_run": 0,
        "blocked": 0,
        "errored": 0,
    }
    audit_rows: List[Dict[str, str]] = []

    with ChMeetingsConnector() as chm_connector:
        if not chm_connector.authenticate():
            logger.error("Authentication with ChMeetings failed")
            return empty

        try:
            live_people: List[Dict[str, Any]] = (
                people if people is not None else chm_connector.get_people()
            )
        except ChMeetingsReadError as exc:
            logger.error(f"Failed to load ChMeetings people for repair-form-people: {exc}")
            return empty

        live_groups: List[Dict[str, Any]] = (
            groups if groups is not None else chm_connector.get_groups()
        )
        people_index = _index_people_for_form_audit(live_people)
        team_group_by_name = {
            g["name"]: str(g["id"])
            for g in live_groups
            if _is_team_group(g.get("name", ""))
        }
        repair_candidates: List[Dict[str, str]] = [
            row for row in source_rows
            if _source_row_people_match(row, people_index)[0] == "missing_person"
        ]
        duplicate_source_keys = _duplicate_source_repair_keys(repair_candidates)

        for row in source_rows:
            match_status, matches = _source_row_people_match(row, people_index)
            row_key = row.get("source_row", "?")
            name = f"{row['first_name']} {row['last_name']}"

            if match_status != "missing_person":
                # Person already exists in ChMeetings.
                if match_status == "ambiguous_name_only":
                    counts["blocked"] += 1
                    outcome = "blocked_ambiguous"
                    outcome_detail = (
                        f"ambiguous name-only match: ids="
                        f"{[str(p.get('id', '')) for p in matches]}"
                    )
                    logger.warning(
                        f"[repair] Row {row_key} ({name}): blocked — {outcome_detail}"
                    )
                else:
                    # matched_email / matched_phone_name / matched_name_only.
                    # This command repairs missing People only. Existing People
                    # are left for assign-groups to route into Team groups.
                    matched = matches[0]
                    matched_id = str(matched.get("id", ""))
                    counts["skipped"] += 1
                    counts["skipped_matched"] += 1
                    outcome = "skipped_matched"
                    outcome_detail = f"matched by {match_status} (id={matched_id}); no repair needed"

                audit_rows.append(_repair_audit_row(row, outcome, outcome_detail, matches))
                continue

            # Row is still missing_person after fresh re-check.
            duplicate_reason = _duplicate_source_reason(row, duplicate_source_keys)
            if duplicate_reason:
                counts["blocked"] += 1
                logger.warning(
                    f"[repair] Row {row_key} ({name}): blocked — {duplicate_reason}"
                )
                audit_rows.append(
                    _repair_audit_row(row, "blocked_duplicate_source", duplicate_reason, [])
                )
                continue

            extra = extra_cols_by_row.get(row_key, {})
            payload, blocked_reason = _build_create_payload(row, extra)

            if blocked_reason:
                counts["blocked"] += 1
                logger.warning(
                    f"[repair] Row {row_key} ({name}): blocked — {blocked_reason}"
                )
                audit_rows.append(
                    _repair_audit_row(row, "blocked", blocked_reason, [])
                )
                continue

            if dry_run:
                counts["skipped"] += 1
                counts["dry_run"] += 1
                outcome_detail = (
                    f"would create {name} for church {row.get('church_code')} "
                    f"(sport={row.get('primary_sport')})"
                )
                logger.info(f"[dry-run] Row {row_key}: {outcome_detail}")
                audit_rows.append(_repair_audit_row(row, "dry_run", outcome_detail, []))
                continue

            # Live execute path.
            assert payload is not None
            created_person = chm_connector.create_person(
                first_name=payload["first_name"],
                last_name=payload["last_name"],
                email=payload.get("email"),
                mobile=payload.get("mobile"),
                additional_fields=payload.get("additional_fields"),
                extra_fields=payload.get("extra_fields"),
            )
            time.sleep(0.3)

            if not created_person:
                counts["errored"] += 1
                logger.error(
                    f"[repair] Row {row_key} ({name}): create_person API call failed"
                )
                audit_rows.append(
                    _repair_audit_row(row, "errored", "create_person returned None", [])
                )
                continue

            new_id = str(created_person.get("id") or created_person.get("person_id") or "")
            logger.info(
                f"[repair] Row {row_key}: created {name} as ChMeetings person_id={new_id}"
            )

            # Refresh index so a second row for the same person doesn't re-create.
            live_people.append(created_person)
            people_index = _index_people_for_form_audit(live_people)

            # Add the new person to their Team group.
            church_code = row.get("church_code", "").strip().upper()
            group_name = _team_group_name(church_code)
            group_id = team_group_by_name.get(group_name)
            group_note = ""
            if group_id and new_id:
                ok = chm_connector.add_person_to_group(group_id, new_id)
                time.sleep(0.2)
                group_note = (
                    f", added to {group_name}" if ok
                    else f", failed to add to {group_name}"
                )
                if not ok:
                    logger.error(
                        f"[repair] Failed to add new person {new_id} to {group_name}"
                    )
            elif not group_id:
                group_note = f", group {group_name!r} not found in ChMeetings"
                logger.warning(
                    f"[repair] Group {group_name!r} not found — cannot assign {name}"
                )

            counts["created"] += 1
            audit_rows.append(
                _repair_audit_row(
                    row, "created",
                    f"new_person_id={new_id}{group_note}",
                    [],
                )
            )

    _write_audit_file("form_people_repair.xlsx", audit_rows)
    logger.info(
        f"repair-form-people complete: "
        f"{counts['created']} created, {counts['linked']} linked, "
        f"{counts['skipped']} skipped, {counts['blocked']} blocked, "
        f"{counts['errored']} errored."
    )
    return counts


def audit_form_people(
    source_file: str,
    people: Optional[List[Dict[str, str]]] = None,
    output_filename: str = "form_people_audit.xlsx",
) -> bool:
    """Audit Individual Application rows against visible ChMeetings People records."""
    try:
        source_rows = _load_source_export_rows(source_file)
    except Exception as exc:
        logger.error(f"Failed to load source export '{source_file}': {exc}")
        return False

    if people is None:
        with ChMeetingsConnector() as chm_connector:
            if not chm_connector.authenticate():
                logger.error("Authentication with ChMeetings failed")
                return False
            try:
                people = chm_connector.get_people()
            except ChMeetingsReadError as exc:
                logger.error(f"Failed to load ChMeetings people for audit-form-people: {exc}")
                return False

    people_index = _index_people_for_form_audit(people)
    audit_rows: List[Dict[str, str]] = []

    for row in source_rows:
        match_status, matches = _source_row_people_match(row, people_index)
        blank_field_warnings: List[str] = []
        source_values = _form_field_display_values(row)
        for person in matches:
            current_by_id, current_by_name = _current_field_indexes(person)
            for field_id in [
                SF_FIELD_IDS["MY_ROLE"],
                SF_FIELD_IDS["CHURCH_TEAM"],
                SF_FIELD_IDS["PRIMARY_SPORT"],
                SF_FIELD_IDS["SECONDARY_SPORT"],
                SF_FIELD_IDS["OTHER_EVENTS"],
            ]:
                if field_id not in source_values:
                    continue
                current_field = _current_field_for_id(field_id, current_by_id, current_by_name)
                if _is_field_blank(current_field):
                    blank_field_warnings.append(
                        f"{person.get('id', '')}:{_FORM_FIELD_NAME_BY_ID.get(field_id, field_id)}"
                    )
        audit_rows.append({
            "Source Row": row.get("source_row", ""),
            "First Name": row.get("first_name", ""),
            "Last Name": row.get("last_name", ""),
            "Email": row.get("email_display", ""),
            "Mobile Phone": row.get("mobile_phone_display", ""),
            "Church Code": row.get("church_code", ""),
            "Role": row.get("role", ""),
            "Submission Date": row.get("submission_date", ""),
            "Primary Sport": row.get("primary_sport", ""),
            "Secondary Sport": row.get("secondary_sport", ""),
            "Other Events": row.get("other_events", ""),
            "Match Status": match_status,
            "Match Count": str(len(matches)),
            "Matched ChMeetings IDs": ", ".join(str(person.get("id", "")) for person in matches),
            "Matched Names": ", ".join(
                f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
                for person in matches
            ),
            "Matched Emails": ", ".join(str(person.get("email", "") or "") for person in matches),
            "Matched Blank Sports Fest Fields": "; ".join(blank_field_warnings),
        })

    _write_audit_file(output_filename, audit_rows)

    missing_count = sum(1 for row in audit_rows if row["Match Status"] == "missing_person")
    ambiguous_count = sum(1 for row in audit_rows if row["Match Status"] == "ambiguous_name_only")
    blank_field_count = sum(
        1 for row in audit_rows if row.get("Matched Blank Sports Fest Fields")
    )
    if missing_count:
        logger.warning(
            f"Found {missing_count} Individual Application row(s) with no matching "
            f"ChMeetings People record. See data/{output_filename}."
        )
    if ambiguous_count:
        logger.warning(
            f"Found {ambiguous_count} Individual Application row(s) with ambiguous "
            f"name-only ChMeetings People matches. See data/{output_filename}."
        )
    if blank_field_count:
        logger.warning(
            f"Found {blank_field_count} matched Individual Application row(s) with blank "
            f"Sports Fest profile fields. See data/{output_filename}."
        )
    if not missing_count and not ambiguous_count and not blank_field_count:
        logger.info(
            f"Individual Application People audit clean: {len(audit_rows)} row(s) matched. "
            f"See data/{output_filename}."
        )
    return True


def _person_matches_source_export(
    person: Dict[str, str],
    church_code: str,
    source_rows: List[Dict[str, str]],
) -> bool:
    """True when a ChMeetings person is present in the source export rows."""
    first_name = _normalize_text(person.get("first_name", ""))
    last_name = _normalize_text(person.get("last_name", ""))
    email = _normalize_text(person.get("email", ""))
    mobile = _normalize_phone(person.get("mobile", ""))
    church_code = church_code.strip().upper()

    for row in source_rows:
        if row["church_code"] != church_code:
            continue
        if row["email"] and email and row["email"] == email:
            return True
        if row["mobile_phone"] and mobile and row["mobile_phone"] == mobile:
            if (
                _normalize_text(row["first_name"]) == first_name
                and _normalize_text(row["last_name"]) == last_name
            ):
                return True
        if (
            _normalize_text(row["first_name"]) == first_name
            and _normalize_text(row["last_name"]) == last_name
        ):
            return True
    return False


def _source_export_church_code(
    person: Dict[str, str],
    source_rows: List[Dict[str, str]],
) -> Optional[str]:
    """Resolve one church code from the strongest current-season export match."""
    first_name = _normalize_text(person.get("first_name", ""))
    last_name = _normalize_text(person.get("last_name", ""))
    email = _normalize_text(person.get("email", ""))
    mobile = _normalize_phone(person.get("mobile", ""))

    match_groups = [
        [
            row for row in source_rows
            if row["email"] and email and row["email"] == email
        ],
        [
            row for row in source_rows
            if row["mobile_phone"]
            and mobile
            and row["mobile_phone"] == mobile
            and _normalize_text(row["first_name"]) == first_name
            and _normalize_text(row["last_name"]) == last_name
        ],
    ]

    for matches in match_groups:
        if not matches:
            continue
        church_codes = {row["church_code"] for row in matches}
        if len(church_codes) == 1:
            return church_codes.pop()
        return None

    return None


def _source_export_row_match(
    person: Dict[str, str],
    source_rows: List[Dict[str, str]],
) -> Tuple[str, Optional[Dict[str, str]], str]:
    """Return one strong current-season source row match for a ChMeetings person."""
    first_name = _normalize_text(person.get("first_name", ""))
    last_name = _normalize_text(person.get("last_name", ""))
    email = _normalize_text(person.get("email", ""))
    mobile = _normalize_phone(person.get("mobile", ""))

    match_groups = [
        (
            "matched_email",
            [
                row for row in source_rows
                if row["email"] and email and row["email"] == email
            ],
        ),
        (
            "matched_phone_name",
            [
                row for row in source_rows
                if row["mobile_phone"]
                and mobile
                and row["mobile_phone"] == mobile
                and _normalize_text(row["first_name"]) == first_name
                and _normalize_text(row["last_name"]) == last_name
            ],
        ),
    ]

    for match_status, matches in match_groups:
        if len(matches) == 1:
            return match_status, matches[0], ""
        if len(matches) > 1:
            source_rows_text = ", ".join(str(row.get("source_row", "")) for row in matches)
            return (
                f"ambiguous_{match_status.removeprefix('matched_')}",
                None,
                f"{len(matches)} source rows match by {match_status}: {source_rows_text}",
            )

    return "missing_source_row", None, ""


def _current_field_indexes(
    person: Dict[str, Any],
) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_id: Dict[int, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for field in person.get("additional_fields", []) or []:
        field_id = _field_id(field.get("field_id"))
        if field_id is not None:
            by_id[field_id] = field
        field_name = str(field.get("field_name", "") or "").strip()
        if field_name:
            by_name[field_name] = field
    return by_id, by_name


def _current_field_for_id(
    field_id: int,
    by_id: Dict[int, Dict[str, Any]],
    by_name: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    field = by_id.get(field_id)
    if field is not None:
        return field
    field_name = _FORM_FIELD_NAME_BY_ID.get(field_id)
    if field_name:
        return by_name.get(field_name)
    return None


def _field_display_value(field: Optional[Dict[str, Any]]) -> str:
    if not field:
        return ""
    value = field.get("value")
    if value not in (None, ""):
        return str(value).strip()
    selected_option_ids = field.get("selected_option_ids")
    if selected_option_ids:
        return ", ".join(str(option_id) for option_id in selected_option_ids)
    selected_option_id = field.get("selected_option_id")
    if selected_option_id not in (None, ""):
        return str(selected_option_id).strip()
    return ""


def _normalized_field_value(value: str) -> str:
    labels = [
        html.unescape(label).strip().casefold()
        for label in str(value or "").split(",")
        if label.strip()
    ]
    if len(labels) > 1:
        labels = sorted(labels)
    return ", ".join(labels)


def _is_field_blank(field: Optional[Dict[str, Any]]) -> bool:
    return not _field_display_value(field)


def _sanitize_additional_field_payload(field: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    field_id = _field_id(field.get("field_id"))
    if field_id is None:
        return None

    field_type = field.get("field_type") or _SF_FIELD_TYPE_BY_ID.get(field_id)
    if not field_type:
        return None

    payload: Dict[str, Any] = {"field_id": field_id, "field_type": field_type}
    for key in _ADDITIONAL_FIELD_PAYLOAD_KEYS:
        if key in ("field_id", "field_type"):
            continue
        if key in field and field[key] is not None:
            payload[key] = field[key]
    return payload


def _merge_additional_fields_for_update(
    person: Dict[str, Any],
    replacements_by_id: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged_by_id: Dict[int, Dict[str, Any]] = {}
    field_order: List[int] = []

    for field in person.get("additional_fields", []) or []:
        payload = _sanitize_additional_field_payload(field)
        if not payload:
            continue
        field_id = int(payload["field_id"])
        if field_id not in merged_by_id:
            field_order.append(field_id)
        merged_by_id[field_id] = replacements_by_id.get(field_id, payload)

    for field_id, payload in replacements_by_id.items():
        if field_id not in merged_by_id:
            field_order.append(field_id)
        merged_by_id[field_id] = payload

    return [merged_by_id[field_id] for field_id in field_order]


def _hydration_audit(
    outcome: str = "not_applicable",
    *,
    source_match: str = "",
    source_row: str = "",
    fields: Optional[List[str]] = None,
    conflicts: Optional[List[str]] = None,
    detail: str = "",
) -> Dict[str, Any]:
    return {
        "outcome": outcome,
        "source_match": source_match,
        "source_row": source_row,
        "fields": fields or [],
        "conflicts": conflicts or [],
        "detail": detail,
    }


def _should_audit_hydration(hydration: Dict[str, Any]) -> bool:
    return hydration.get("outcome") not in ("not_applicable", "unchanged")


def _build_hydration_update(
    person: Dict[str, Any],
    row: Dict[str, str],
    extra_cols: Optional[Dict[str, str]],
) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    form_fields, blocked_reason = _build_form_additional_fields(row, extra_cols)
    if blocked_reason:
        return None, _hydration_audit("blocked", detail=blocked_reason)

    assert form_fields is not None

    source_values = _form_field_display_values(row, extra_cols)
    current_by_id, current_by_name = _current_field_indexes(person)
    replacements_by_id: Dict[int, Dict[str, Any]] = {}
    updated_fields: List[str] = []
    conflicts: List[str] = []

    for form_field in form_fields:
        field_id = _field_id(form_field.get("field_id"))
        if field_id is None:
            continue
        field_name = _FORM_FIELD_NAME_BY_ID.get(field_id, str(field_id))
        source_value = source_values.get(field_id, "")
        current_field = _current_field_for_id(field_id, current_by_id, current_by_name)
        current_value = _field_display_value(current_field)

        if _is_field_blank(current_field):
            replacements_by_id[field_id] = form_field
            updated_fields.append(field_name)
        elif source_value and (
            _normalized_field_value(current_value) != _normalized_field_value(source_value)
        ):
            conflicts.append(f"{field_name}: ChM={current_value!r}; form={source_value!r}")

    if replacements_by_id:
        merged_fields = _merge_additional_fields_for_update(person, replacements_by_id)
        outcome = "pending_with_conflicts" if conflicts else "pending"
        return merged_fields, _hydration_audit(
            outcome,
            fields=updated_fields,
            conflicts=conflicts,
        )

    if conflicts:
        return None, _hydration_audit("conflict", conflicts=conflicts)

    return None, _hydration_audit("unchanged")


def _assignment_audit_row(
    person: Dict[str, Any],
    *,
    church_code: str,
    target_group: str,
    outcome: str,
    hydration: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    hydration = hydration or _hydration_audit()
    return {
        "Person Id": str(person.get("person_id") or person.get("id", "")),
        "First Name": person.get("first_name", ""),
        "Last Name": person.get("last_name", ""),
        "Email": person.get("email", ""),
        "Church Code": church_code,
        "Target Group": target_group,
        "Outcome": outcome,
        "Hydration Outcome": hydration.get("outcome", ""),
        "Hydration Source Match": hydration.get("source_match", ""),
        "Hydration Source Row": hydration.get("source_row", ""),
        "Hydrated Fields": ", ".join(hydration.get("fields", [])),
        "Hydration Conflicts": "; ".join(hydration.get("conflicts", [])),
        "Hydration Detail": hydration.get("detail", ""),
    }


def _assign_people_to_church_team_groups_legacy(
    dry_run: bool = False,
    source_file: Optional[str] = None,
) -> bool:
    """
    Assign people in ChMeetings to their church team groups via direct API calls.

    Identifies people who have a church code in their ChMeetings profile, or a
    unique match in the supplied current-season export, but are not yet members
    of the corresponding "Team XYZ" group. Then calls add_person_to_group().

    Args:
        dry_run: If True, only generate the audit file — no API calls are made.

    Returns:
        True if the run succeeded with zero API failures.
        False if authentication failed, an unexpected error occurred,
        or any add_person_to_group() call returned False.
    """
    logger.info(
        f"Starting church team group assignment (dry_run={dry_run}, "
        f"source_file={source_file or 'ALL_CHM_PEOPLE'})..."
    )

    source_rows: Optional[List[Dict[str, str]]] = None
    extra_cols_by_row: Dict[str, Dict[str, str]] = {}
    if source_file:
        try:
            source_rows = _load_source_export_rows(source_file)
        except Exception as exc:
            logger.error(f"Failed to load source export '{source_file}': {exc}")
            return False
        extra_cols_by_row = _load_repair_extra_cols(source_file)
        logger.info(
            f"Loaded {len(source_rows)} row(s) from source export for current-season filtering"
        )

    with ChMeetingsConnector() as chm_connector:
        if not chm_connector.authenticate():
            logger.error("Authentication with ChMeetings failed")
            return False

        # --- Identification (unchanged logic) ---
        try:
            all_people = chm_connector.get_people()
        except ChMeetingsReadError as exc:
            logger.error(f"Failed to load ChMeetings people for group assignment: {exc}")
            return False
        logger.info(f"Retrieved {len(all_people)} people from ChMeetings")
        if source_file:
            audit_form_people(source_file, people=all_people)

        all_groups = chm_connector.get_groups()
        team_groups = [g for g in all_groups if _is_team_group(g.get("name", ""))]

        # Build name → id lookup for fast group resolution
        team_group_by_name = {g["name"]: str(g["id"]) for g in team_groups}

        # Resolve Lost and Found group for "Other" church applicants
        laf_group = next(
            (g for g in all_groups if g.get("name") == Config.LOST_AND_FOUND_GROUP_NAME),
            None,
        )
        laf_group_id: Optional[str] = str(laf_group["id"]) if laf_group else None
        people_in_laf: set = set()
        if laf_group_id:
            for p in chm_connector.get_group_people(laf_group_id):
                people_in_laf.add(str(p.get("person_id")))

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
            if not church_code:
                if source_rows is None:
                    continue
                church_code = _source_export_church_code(person, source_rows) or ""
                if not church_code:
                    continue
                logger.info(
                    f"[VAY SM] Using current-season source export church_code={church_code} "
                    f"for chm_id={person_id} because the ChMeetings profile field is blank."
                )
            elif source_rows is not None:
                if not _person_matches_source_export(person, church_code, source_rows):
                    continue

            if church_code == "OTHER":
                # Route to Lost and Found instead of a normal team group
                if person_id in people_in_laf:
                    continue  # already there — idempotent
                people_for_assignment.append({
                    "person_id": person_id,
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "email": person.get("email", ""),
                    "church_code": church_code,
                    "target_group": Config.LOST_AND_FOUND_GROUP_NAME,
                })
            else:
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
            is_laf = target_group_name == Config.LOST_AND_FOUND_GROUP_NAME
            if is_laf:
                group_id = laf_group_id
                if group_id is None:
                    logger.warning(
                        f"Lost and Found group '{Config.LOST_AND_FOUND_GROUP_NAME}' not found "
                        f"in ChMeetings — skipping {person['first_name']} {person['last_name']} "
                        f"(id={person['person_id']}). Create the group in ChMeetings first."
                    )
                    missing_group += 1
                    outcome = "missing_group"
                elif dry_run:
                    logger.info(
                        f"[dry-run] Would add {person['first_name']} {person['last_name']} "
                        f"(id={person['person_id']}) to '{target_group_name}' [REVIEW NEEDED]"
                    )
                    outcome = "dry_run"
                else:
                    ok = chm_connector.add_person_to_group(group_id, person["person_id"])
                    time.sleep(0.2)
                    if ok:
                        logger.info(
                            f"[REVIEW NEEDED] Added {person['first_name']} {person['last_name']} "
                            f"(id={person['person_id']}) to '{Config.LOST_AND_FOUND_GROUP_NAME}' "
                            f"— submitted church/team: Other"
                        )
                        added += 1
                        outcome = "added"
                    else:
                        failed += 1
                        outcome = "failed"
            elif team_group_by_name.get(target_group_name) is None:
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
                group_id = team_group_by_name[target_group_name]
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


def assign_people_to_church_team_groups(
    dry_run: bool = False,
    source_file: Optional[str] = None,
    chm_ids: Optional[List[str]] = None,
    church_codes: Optional[List[str]] = None,
) -> bool:
    """
    Assign people in ChMeetings to church team groups and hydrate source forms.

    When a current-season source export is supplied, existing matched people
    are hydrated from the form before the already-in-team idempotency skip.
    """
    target_chm_ids = {str(chm_id).strip() for chm_id in (chm_ids or []) if str(chm_id).strip()}
    target_church_codes = {
        str(church_code).strip().upper()
        for church_code in (church_codes or [])
        if str(church_code).strip()
    }

    logger.info(
        f"Starting church team group assignment (dry_run={dry_run}, "
        f"source_file={source_file or 'ALL_CHM_PEOPLE'}, "
        f"chm_ids={sorted(target_chm_ids) if target_chm_ids else 'ALL'}, "
        f"church_codes={sorted(target_church_codes) if target_church_codes else 'ALL'})..."
    )

    source_rows: Optional[List[Dict[str, str]]] = None
    extra_cols_by_row: Dict[str, Dict[str, str]] = {}
    if source_file:
        try:
            source_rows = _load_source_export_rows(source_file)
        except Exception as exc:
            logger.error(f"Failed to load source export '{source_file}': {exc}")
            return False
        extra_cols_by_row = _load_repair_extra_cols(source_file)
        logger.info(
            f"Loaded {len(source_rows)} row(s) from source export for current-season filtering"
        )

    with ChMeetingsConnector() as chm_connector:
        if not chm_connector.authenticate():
            logger.error("Authentication with ChMeetings failed")
            return False

        try:
            all_people = chm_connector.get_people()
        except ChMeetingsReadError as exc:
            logger.error(f"Failed to load ChMeetings people for group assignment: {exc}")
            return False
        logger.info(f"Retrieved {len(all_people)} people from ChMeetings")
        if target_chm_ids:
            found_target_ids = {str(person.get("id")) for person in all_people} & target_chm_ids
            missing_target_ids = sorted(target_chm_ids - found_target_ids)
            if missing_target_ids:
                logger.warning(
                    f"Requested ChMeetings ID(s) not found in People export: {missing_target_ids}"
                )
        if source_file and not target_chm_ids and not target_church_codes:
            audit_form_people(source_file, people=all_people)
        elif source_file and (target_chm_ids or target_church_codes):
            logger.info(
                "Skipping broad form/people audit because assign-groups is limited "
                f"to ChMeetings ID(s): {sorted(target_chm_ids) if target_chm_ids else 'ALL'} "
                f"and church code(s): {sorted(target_church_codes) if target_church_codes else 'ALL'}"
            )

        all_groups = chm_connector.get_groups()
        team_groups = [g for g in all_groups if _is_team_group(g.get("name", ""))]
        team_group_by_name = {g["name"]: str(g["id"]) for g in team_groups}

        laf_group = next(
            (g for g in all_groups if g.get("name") == Config.LOST_AND_FOUND_GROUP_NAME),
            None,
        )
        laf_group_id: Optional[str] = str(laf_group["id"]) if laf_group else None
        people_in_laf: set = set()
        if laf_group_id:
            for p in chm_connector.get_group_people(laf_group_id):
                people_in_laf.add(str(p.get("person_id")))

        people_in_teams = set()
        for group in team_groups:
            for person in chm_connector.get_group_people(group["id"]):
                people_in_teams.add(str(person.get("person_id")))

        logger.info(f"Found {len(people_in_teams)} people already in team groups")

        people_for_assignment = []
        audit_rows = []
        hydrated = 0
        hydration_failed = 0
        hydration_blocked = 0
        hydration_blocked_reasons: Counter[str] = Counter()
        hydration_conflict_rows = 0
        hydration_skipped_reasons: Counter[str] = Counter()

        for person in all_people:
            person_id = str(person.get("id"))
            if target_chm_ids and person_id not in target_chm_ids:
                continue
            additional_fields = {
                f["field_name"]: f["value"]
                for f in person.get("additional_fields", [])
                if "field_name" in f
            }
            if source_rows is None and target_church_codes:
                profile_church_code = additional_fields.get(CHM_FIELDS["CHURCH_TEAM"], "").strip().upper()
                if profile_church_code not in target_church_codes:
                    continue
            source_row: Optional[Dict[str, str]] = None
            hydration = _hydration_audit()

            if source_rows is not None:
                source_match, source_row, source_detail = _source_export_row_match(person, source_rows)
                if target_church_codes:
                    if not source_row:
                        continue
                    source_church_code = source_row.get("church_code", "").strip().upper()
                    if source_church_code not in target_church_codes:
                        continue
                if source_row:
                    fresh_person = chm_connector.get_person(person_id)
                    time.sleep(0.2)
                    if not fresh_person:
                        hydration = _hydration_audit(
                            "blocked",
                            source_match=source_match,
                            source_row=source_row.get("source_row", ""),
                            detail="fresh get_person failed before hydration",
                        )
                        hydration_blocked += 1
                        hydration_blocked_reasons[hydration.get("detail", "")] += 1
                        logger.debug(
                            f"[VAY SM] Hydration blocked for chm_id={person_id}: "
                            "fresh get_person failed before hydration"
                        )
                        if _should_audit_hydration(hydration):
                            audit_rows.append(_assignment_audit_row(
                                person,
                                church_code="",
                                target_group="",
                                outcome="fresh_person_fetch_failed",
                                hydration=hydration,
                            ))
                        continue

                    person = fresh_person
                    additional_fields = {
                        f["field_name"]: f["value"]
                        for f in person.get("additional_fields", [])
                        if "field_name" in f
                    }
                    extra_cols = extra_cols_by_row.get(source_row.get("source_row", ""), {})
                    update_fields, hydration = _build_hydration_update(person, source_row, extra_cols)
                    hydration["source_match"] = source_match
                    hydration["source_row"] = source_row.get("source_row", "")

                    if update_fields:
                        if dry_run:
                            hydration["outcome"] = (
                                "would_hydrate_with_conflicts"
                                if hydration.get("conflicts")
                                else "would_hydrate"
                            )
                            logger.info(
                                f"[dry-run] Would hydrate {len(hydration['fields'])} "
                                f"Sports Fest field(s) for chm_id={person_id}: "
                                f"{hydration['fields']}"
                            )
                        else:
                            ok = chm_connector.update_person(
                                person_id,
                                person.get("first_name", ""),
                                person.get("last_name", ""),
                                update_fields,
                                extra_person_data=person,
                            )
                            time.sleep(0.2)
                            if ok:
                                hydrated += 1
                                hydration["outcome"] = (
                                    "hydrated_with_conflicts"
                                    if hydration.get("conflicts")
                                    else "hydrated"
                                )
                                logger.info(
                                    f"[VAY SM] Hydrated {len(hydration['fields'])} "
                                    f"Sports Fest field(s) for chm_id={person_id} "
                                    f"from Individual Application row {hydration['source_row']}"
                                )
                            else:
                                hydration_failed += 1
                                hydration["outcome"] = "failed"
                                hydration["detail"] = "update_person returned False"
                                logger.error(
                                    f"[VAY SM] Failed to hydrate Sports Fest fields "
                                    f"for chm_id={person_id} from source row "
                                    f"{hydration['source_row']}"
                                )
                    elif hydration["outcome"] == "blocked":
                        hydration_blocked += 1
                        hydration_blocked_reasons[hydration.get("detail", "")] += 1
                        logger.debug(
                            f"[VAY SM] Hydration blocked for chm_id={person_id}: "
                            f"{hydration.get('detail', '')}"
                        )
                    elif hydration["outcome"] == "conflict":
                        hydration_conflict_rows += 1
                        logger.debug(
                            f"[VAY SM] Hydration conflict for chm_id={person_id}: "
                            f"{'; '.join(hydration.get('conflicts', []))}"
                        )
                elif source_match.startswith("ambiguous_"):
                    hydration = _hydration_audit(
                        source_match,
                        source_match=source_match,
                        detail=source_detail,
                    )
                    hydration_skipped_reasons[source_match] += 1
                    logger.debug(
                        f"[VAY SM] Hydration skipped for chm_id={person_id}: {source_detail}"
                    )

            church_code = additional_fields.get(CHM_FIELDS["CHURCH_TEAM"], "").strip().upper()
            if not church_code:
                if source_row:
                    church_code = source_row.get("church_code", "")
                elif source_rows is None:
                    continue
                else:
                    church_code = _source_export_church_code(person, source_rows) or ""
                if not church_code:
                    if _should_audit_hydration(hydration):
                        audit_rows.append(_assignment_audit_row(
                            person,
                            church_code="",
                            target_group="",
                            outcome="no_church_code",
                            hydration=hydration,
                        ))
                    continue
                logger.info(
                    f"[VAY SM] Using current-season source export church_code={church_code} "
                    f"for chm_id={person_id} because the ChMeetings profile field is blank."
                )
            elif source_rows is not None:
                if not _person_matches_source_export(person, church_code, source_rows):
                    if _should_audit_hydration(hydration):
                        audit_rows.append(_assignment_audit_row(
                            person,
                            church_code=church_code,
                            target_group="",
                            outcome="source_filter_skip",
                            hydration=hydration,
                        ))
                    continue

            if person_id in people_in_teams:
                if _should_audit_hydration(hydration):
                    target_group = (
                        Config.LOST_AND_FOUND_GROUP_NAME
                        if church_code == "OTHER"
                        else _team_group_name(church_code)
                    )
                    audit_rows.append(_assignment_audit_row(
                        person,
                        church_code=church_code,
                        target_group=target_group,
                        outcome="already_in_team",
                        hydration=hydration,
                    ))
                continue

            if church_code == "OTHER":
                if person_id in people_in_laf:
                    if _should_audit_hydration(hydration):
                        audit_rows.append(_assignment_audit_row(
                            person,
                            church_code=church_code,
                            target_group=Config.LOST_AND_FOUND_GROUP_NAME,
                            outcome="already_in_lost_and_found",
                            hydration=hydration,
                        ))
                    continue
                people_for_assignment.append({
                    "person_id": person_id,
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "email": person.get("email", ""),
                    "church_code": church_code,
                    "target_group": Config.LOST_AND_FOUND_GROUP_NAME,
                    "hydration": hydration,
                })
            else:
                people_for_assignment.append({
                    "person_id": person_id,
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "email": person.get("email", ""),
                    "church_code": church_code,
                    "target_group": _team_group_name(church_code),
                    "hydration": hydration,
                })

        if hydration_blocked_reasons:
            top_reasons = "; ".join(
                f"{reason or 'unknown'} ({count})"
                for reason, count in hydration_blocked_reasons.most_common(8)
            )
            logger.warning(
                f"Hydration blocked for {sum(hydration_blocked_reasons.values())} "
                f"record(s). Top reasons: {top_reasons}. See data/church_team_assignments.xlsx."
            )
        if hydration_conflict_rows:
            logger.warning(
                f"Hydration found nonblank ChMeetings/form conflicts for "
                f"{hydration_conflict_rows} record(s); preserved ChMeetings values. "
                "See data/church_team_assignments.xlsx."
            )
        if hydration_skipped_reasons:
            skipped_summary = "; ".join(
                f"{reason} ({count})"
                for reason, count in hydration_skipped_reasons.most_common()
            )
            logger.warning(
                f"Hydration skipped {sum(hydration_skipped_reasons.values())} "
                f"ambiguous source match(es): {skipped_summary}. "
                "See data/church_team_assignments.xlsx."
            )

        logger.info(f"Found {len(people_for_assignment)} people needing team assignment")

        if not people_for_assignment:
            if audit_rows:
                _write_audit_file("church_team_assignments.xlsx", audit_rows)
            logger.info(
                f"No people need team assignment. Hydration summary: "
                f"{hydrated} hydrated, {hydration_failed} failed, "
                f"{hydration_blocked} blocked."
            )
            return hydration_failed == 0

        added = 0
        failed = 0
        missing_group = 0

        for person in people_for_assignment:
            target_group_name = person["target_group"]
            is_laf = target_group_name == Config.LOST_AND_FOUND_GROUP_NAME
            if is_laf:
                group_id = laf_group_id
                if group_id is None:
                    logger.warning(
                        f"Lost and Found group '{Config.LOST_AND_FOUND_GROUP_NAME}' not found "
                        f"in ChMeetings - skipping {person['first_name']} {person['last_name']} "
                        f"(id={person['person_id']}). Create the group in ChMeetings first."
                    )
                    missing_group += 1
                    outcome = "missing_group"
                elif dry_run:
                    logger.info(
                        f"[dry-run] Would add {person['first_name']} {person['last_name']} "
                        f"(id={person['person_id']}) to '{target_group_name}' [REVIEW NEEDED]"
                    )
                    outcome = "dry_run"
                else:
                    ok = chm_connector.add_person_to_group(group_id, person["person_id"])
                    time.sleep(0.2)
                    if ok:
                        logger.info(
                            f"[REVIEW NEEDED] Added {person['first_name']} {person['last_name']} "
                            f"(id={person['person_id']}) to '{Config.LOST_AND_FOUND_GROUP_NAME}' "
                            f"- submitted church/team: Other"
                        )
                        added += 1
                        outcome = "added"
                    else:
                        failed += 1
                        outcome = "failed"
            elif team_group_by_name.get(target_group_name) is None:
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
                group_id = team_group_by_name[target_group_name]
                ok = chm_connector.add_person_to_group(group_id, person["person_id"])
                time.sleep(0.2)
                if ok:
                    added += 1
                    outcome = "added"
                else:
                    failed += 1
                    outcome = "failed"

            audit_rows.append(_assignment_audit_row(
                person,
                church_code=person["church_code"],
                target_group=target_group_name,
                outcome=outcome,
                hydration=person.get("hydration"),
            ))

        _write_audit_file("church_team_assignments.xlsx", audit_rows)

        if dry_run:
            logger.info(
                f"[dry-run] Would assign {len(people_for_assignment)} people "
                f"({missing_group} with missing group). No API calls made."
            )
        else:
            logger.info(
                f"Group assignment complete: {added} added, {failed} failed, "
                f"{missing_group} skipped (group not found in ChMeetings). "
                f"Hydration: {hydrated} hydrated, {hydration_failed} failed, "
                f"{hydration_blocked} blocked."
            )

        return failed == 0 and hydration_failed == 0


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


def audit_team_groups(church_code: Optional[str] = None,
                      remove_orphans: bool = False) -> bool:
    """
    Audit Team XXX groups for orphaned ChMeetings memberships.

    A membership is considered orphaned when it appears in a Team group but
    GET /people/{id} returns 404 Not Found.

    If remove_orphans=True, each orphaned membership is deleted from ChMeetings
    immediately after identification. This is irreversible — run without the flag
    first to review the audit file before committing to removal.
    """
    normalized_code = church_code.strip().upper() if church_code else None
    logger.info(
        f"Starting team-group orphan audit (church_code={normalized_code or 'ALL'}, "
        f"remove_orphans={remove_orphans})..."
    )
    if remove_orphans:
        logger.warning(
            "REMOVE MODE: orphaned memberships will be deleted from ChMeetings. "
            "This action is irreversible."
        )

    with ChMeetingsConnector() as chm_connector, WordPressConnector() as wp_connector:
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

        logger.info(f"Found {len(team_groups)} target team group(s) to audit.")

        groups_processed = 0
        memberships_found = 0
        orphans_found = 0
        orphans_removed = 0
        orphans_stuck = 0
        resolved_found = 0
        failed_lookups = 0
        audit_rows: List[Dict[str, str]] = []

        for group in team_groups:
            group_id = str(group["id"])
            group_name = group.get("name", "")
            groups_processed += 1

            group_people = chm_connector.get_group_people(group_id)
            logger.info(f"Auditing group '{group_name}' with {len(group_people)} membership(s).")
            memberships_found += len(group_people)

            if not group_people:
                audit_rows.append({
                    "Group Id": group_id,
                    "Group Name": group_name,
                    "Membership Person Id": "",
                    "Membership First Name": "",
                    "Membership Last Name": "",
                    "Membership Email": "",
                    "Lookup Status": "empty_group",
                    "Resolved ChM First Name": "",
                    "Resolved ChM Last Name": "",
                    "Resolved ChM Email": "",
                    "WP Match Count": "0",
                    "WP Participant IDs": "",
                    "WP Names": "",
                })
                continue

            for person in group_people:
                person_id = str(person.get("person_id") or person.get("id") or "")
                membership_first_name = person.get("first_name", "")
                membership_last_name = person.get("last_name", "")
                membership_email = person.get("email", "")

                resolved_person = chm_connector.get_person(person_id) if person_id else None
                time.sleep(0.2)

                lookup_status = getattr(chm_connector, "last_get_person_status", "failed")
                resolved_first_name = ""
                resolved_last_name = ""
                resolved_email = ""

                if resolved_person:
                    resolved_found += 1
                    lookup_status = "ok"
                    resolved_first_name = resolved_person.get("first_name", "")
                    resolved_last_name = resolved_person.get("last_name", "")
                    resolved_email = resolved_person.get("email", "")
                elif lookup_status == "not_found":
                    orphans_found += 1
                    logger.warning(
                        f"Orphaned Team-group membership found: {group_name} has person_id={person_id}, "
                        f"but ChMeetings GET /people/{person_id} returned 404."
                    )
                    if remove_orphans:
                        removed = chm_connector.remove_person_from_group(
                            group_id, person_id, not_found_ok=True
                        )
                        delete_status = getattr(
                            chm_connector, "last_group_membership_delete_status", "failed"
                        )
                        if removed and delete_status == "removed":
                            orphans_removed += 1
                            lookup_status = "orphan_removed"
                            logger.info(
                                f"Removed orphaned membership: person_id={person_id} from {group_name}."
                            )
                        elif removed and delete_status == "already_absent":
                            orphans_stuck += 1
                            lookup_status = "orphan_stuck"
                            logger.warning(
                                f"Cannot remove orphaned membership: person_id={person_id} from "
                                f"{group_name} — ChMeetings DELETE also returned 404. "
                                f"This record is permanently stuck (ChMeetings bug ticket #20188) "
                                f"and must be resolved by ChMeetings support."
                            )
                        else:
                            lookup_status = "orphan_remove_failed"
                            logger.error(
                                f"Failed to remove orphaned membership: person_id={person_id} from {group_name}."
                            )
                else:
                    failed_lookups += 1
                    logger.warning(
                        f"Could not fully audit person_id={person_id} in {group_name}; "
                        f"lookup status was '{lookup_status}'."
                    )

                wp_matches = wp_connector.get_participants(
                    params={"chmeetings_id": person_id, "per_page": 100}
                ) if person_id else []
                wp_ids = ",".join(str(p.get("participant_id", "")) for p in wp_matches)
                wp_names = "; ".join(
                    f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
                    for p in wp_matches
                )

                audit_rows.append({
                    "Group Id": group_id,
                    "Group Name": group_name,
                    "Membership Person Id": person_id,
                    "Membership First Name": membership_first_name,
                    "Membership Last Name": membership_last_name,
                    "Membership Email": membership_email,
                    "Lookup Status": lookup_status,
                    "Resolved ChM First Name": resolved_first_name,
                    "Resolved ChM Last Name": resolved_last_name,
                    "Resolved ChM Email": resolved_email,
                    "WP Match Count": str(len(wp_matches)),
                    "WP Participant IDs": wp_ids,
                    "WP Names": wp_names,
                })

        _write_audit_file("team_group_orphan_audit.xlsx", audit_rows)
        summary = (
            f"Team-group orphan audit complete: {groups_processed} group(s), "
            f"{memberships_found} membership(s), {orphans_found} orphan(s), "
            f"{resolved_found} resolved lookup(s), {failed_lookups} failed lookup(s)."
        )
        if remove_orphans:
            summary += (
                f" Removed: {orphans_removed}/{orphans_found} orphaned membership(s)"
                f" (stuck/API-undeleteable: {orphans_stuck})."
            )
        logger.info(summary)

        return True


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
