import datetime
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from chmeetings.backend_connector import ChMeetingsConnector
from config import DATA_DIR, SF_FIELD_IDS
from wordpress.frontend_connector import WordPressConnector


CONSENT_CHECKLIST_OPTION_ID = 199609
CONSENT_THRESHOLD = 51
CONSENT_SCORE_WEIGHTS = {
    "birthdate": 33,
    "email": 27,
    "phone": 24,
    "name": 16,
}
CONSENT_AUDIT_FILE = "consent_check_audit.xlsx"
CONSENT_REQUIRED_COLUMNS = [
    "First Name",
    "Last Name",
    "Athlete Mobile Phone",
    "Athlete Email",
    "Athlete Birthdate",
    "Select one:",
    "Full Name of the parents or legal guardian",
    "Email of the parents or legal guardian",
    "Cell phone of the parents or legal guardian",
    "Submission Date",
]


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalize_birthdate(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ""

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def _parse_submission_date(value: Any) -> Optional[datetime.datetime]:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return None

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _normalize_signer_type(value: Any) -> str:
    normalized = _normalize_text(value)
    if "parent or legal guardian" in normalized:
        return "guardian"
    if normalized:
        return "self"
    return ""


def _full_name(first_name: Any, last_name: Any) -> str:
    return _normalize_text(f"{first_name or ''} {last_name or ''}")


def _format_breakdown(breakdown: Dict[str, int]) -> str:
    return (
        f"birthdate={breakdown.get('birthdate', 0)}, "
        f"phone={breakdown.get('phone', 0)}, "
        f"email={breakdown.get('email', 0)}, "
        f"name={breakdown.get('name', 0)}"
    )


class ConsentChecker:
    """Match consent-form exports to registered participants and update ChMeetings."""

    def __init__(
        self,
        chm_connector: ChMeetingsConnector,
        wp_connector: WordPressConnector,
        output_dir: Optional[Path] = None,
    ) -> None:
        self.chm = chm_connector
        self.wp = wp_connector
        self.output_dir = Path(output_dir or DATA_DIR)

    def load_consent_export(self, path: str) -> List[Dict[str, Any]]:
        """Read and normalize a ChMeetings consent-form export."""
        df = pd.read_excel(path)
        missing_columns = [col for col in CONSENT_REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            raise ValueError(
                f"Missing required column(s) in consent export: {missing_columns}"
            )

        rows: List[Dict[str, Any]] = []
        for index, row in df.iterrows():
            rows.append(
                {
                    "source_row_number": index + 2,
                    "signer_first_name": str(row.get("First Name", "") or "").strip(),
                    "signer_last_name": str(row.get("Last Name", "") or "").strip(),
                    "signer_name": str(
                        f"{row.get('First Name', '') or ''} {row.get('Last Name', '') or ''}"
                    ).strip(),
                    "athlete_phone": _normalize_phone(row.get("Athlete Mobile Phone", "")),
                    "athlete_email": _normalize_text(row.get("Athlete Email", "")),
                    "athlete_birthdate": _normalize_birthdate(
                        row.get("Athlete Birthdate", "")
                    ),
                    "signer_type": _normalize_signer_type(row.get("Select one:", "")),
                    "guardian_name": str(
                        row.get("Full Name of the parents or legal guardian", "") or ""
                    ).strip(),
                    "guardian_email": _normalize_text(
                        row.get("Email of the parents or legal guardian", "")
                    ),
                    "guardian_phone": _normalize_phone(
                        row.get("Cell phone of the parents or legal guardian", "")
                    ),
                    "submission_date": _parse_submission_date(row.get("Submission Date", "")),
                    "submission_date_display": str(
                        row.get("Submission Date", "") or ""
                    ).strip(),
                    "normalized_signer_name": _full_name(
                        row.get("First Name", ""), row.get("Last Name", "")
                    ),
                }
            )

        logger.info(f"Loaded {len(rows)} consent row(s) from {path}")
        return rows

    def _score(
        self, consent_row: Dict[str, Any], participant: Dict[str, Any]
    ) -> Tuple[int, Dict[str, int]]:
        """Return weighted score and per-field breakdown for one row/candidate pair."""
        participant_birthdate = _normalize_birthdate(participant.get("birthdate"))
        participant_phone = _normalize_phone(participant.get("phone", ""))
        participant_email = _normalize_text(participant.get("email", ""))
        participant_name = _full_name(
            participant.get("first_name", ""), participant.get("last_name", "")
        )

        breakdown = {
            "birthdate": CONSENT_SCORE_WEIGHTS["birthdate"]
            if consent_row["athlete_birthdate"]
            and consent_row["athlete_birthdate"] == participant_birthdate
            else 0,
            "phone": CONSENT_SCORE_WEIGHTS["phone"]
            if consent_row["athlete_phone"]
            and consent_row["athlete_phone"] == participant_phone
            else 0,
            "email": CONSENT_SCORE_WEIGHTS["email"]
            if consent_row["athlete_email"]
            and consent_row["athlete_email"] == participant_email
            else 0,
            "name": CONSENT_SCORE_WEIGHTS["name"]
            if consent_row["normalized_signer_name"]
            and consent_row["normalized_signer_name"] == participant_name
            else 0,
        }
        return sum(breakdown.values()), breakdown

    def _deduplicate(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collapse multiple qualifying consent rows down to one row per participant."""
        matches_by_participant: Dict[str, List[Dict[str, Any]]] = {}
        for match in matches:
            participant_id = str(match["participant"]["chmeetings_id"])
            matches_by_participant.setdefault(participant_id, []).append(match)

        deduped: List[Dict[str, Any]] = []
        for participant_id, participant_matches in matches_by_participant.items():
            if len(participant_matches) > 1:
                logger.info(
                    f"Duplicate consent rows collapsed for participant {participant_id}: "
                    f"{len(participant_matches)} qualifying rows"
                )

            chosen = max(
                participant_matches,
                key=lambda item: (
                    item["score"],
                    item["consent_row"]["submission_date"] or datetime.datetime.min,
                ),
            )
            chosen["duplicate_rows_collapsed"] = max(0, len(participant_matches) - 1)
            deduped.append(chosen)

        return deduped

    def _fetch_participants(self, church_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all synced WordPress participants that have ChMeetings IDs."""
        all_participants: List[Dict[str, Any]] = []
        page = 1
        per_page = 100
        normalized_church_code = church_code.strip().upper() if church_code else None

        while True:
            batch = self.wp.get_participants({"page": page, "per_page": per_page}) or []
            if not batch:
                break
            all_participants.extend(batch)
            if len(batch) < per_page:
                break
            page += 1

        candidates = []
        for participant in all_participants:
            if normalized_church_code and str(
                participant.get("church_code", "") or ""
            ).strip().upper() != normalized_church_code:
                continue
            if not participant.get("chmeetings_id"):
                continue
            candidates.append(participant)

        logger.info(
            f"Loaded {len(candidates)} WordPress participant candidate(s)"
            + (
                f" for church {normalized_church_code}"
                if normalized_church_code
                else ""
            )
        )
        return candidates

    def _is_consent_already_checked(self, person: Dict[str, Any]) -> bool:
        checklist = self._find_checklist_field(person)
        selected_option_ids = checklist.get("selected_option_ids", []) if checklist else []
        normalized_ids = {int(option_id) for option_id in selected_option_ids}
        return CONSENT_CHECKLIST_OPTION_ID in normalized_ids

    def _find_checklist_field(self, person: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for field in person.get("additional_fields", []):
            if field.get("field_id") == SF_FIELD_IDS["CHECKLIST"]:
                return field
        return None

    def _build_checklist_update(self, person: Dict[str, Any]) -> List[Dict[str, Any]]:
        checklist = self._find_checklist_field(person) or {}
        selected_option_ids = [
            int(option_id) for option_id in checklist.get("selected_option_ids", []) or []
        ]
        if CONSENT_CHECKLIST_OPTION_ID not in selected_option_ids:
            selected_option_ids.append(CONSENT_CHECKLIST_OPTION_ID)

        return [
            {
                "field_id": SF_FIELD_IDS["CHECKLIST"],
                "field_type": checklist.get("field_type", "checkbox"),
                "selected_option_ids": selected_option_ids,
            }
        ]

    def _build_audit_row(
        self,
        consent_row: Dict[str, Any],
        participant: Optional[Dict[str, Any]],
        *,
        score: int,
        breakdown: Dict[str, int],
        action: str,
        duplicate_rows_collapsed: int = 0,
        chm_person: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resolved_person = chm_person or participant or {}
        return {
            "CHM ID": str(resolved_person.get("id") or resolved_person.get("chmeetings_id") or ""),
            "First Name": resolved_person.get("first_name", ""),
            "Last Name": resolved_person.get("last_name", ""),
            "Church Code": resolved_person.get("church_code", participant.get("church_code", "") if participant else ""),
            "Consent Form Signer Type": consent_row.get("signer_type", ""),
            "Consent Row Name": consent_row.get("signer_name", ""),
            "Consent Row Email": consent_row.get("athlete_email", ""),
            "Consent Row Phone": consent_row.get("athlete_phone", ""),
            "Consent Row Birthdate": consent_row.get("athlete_birthdate", ""),
            "Score": score,
            "Score Breakdown": _format_breakdown(breakdown),
            "Duplicate Rows Collapsed": duplicate_rows_collapsed,
            "Action Taken": action,
        }

    def _write_audit_file(self, rows: List[Dict[str, Any]]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        audit_file = self.output_dir / CONSENT_AUDIT_FILE
        try:
            pd.DataFrame(rows).to_excel(audit_file, index=False)
            logger.info(f"Audit file written: {audit_file}")
        except PermissionError:
            logger.warning(
                f"Could not write audit file - {audit_file} is open in another program. "
                "Close the file and re-run to get an updated audit log. "
                "API calls already made above are unaffected."
            )

    def run(
        self,
        consent_file: str,
        *,
        dry_run: bool = False,
        church_code: Optional[str] = None,
    ) -> Dict[str, int]:
        """Run the consent-check workflow and return a run summary."""
        summary = {
            "rows_processed": 0,
            "checked": 0,
            "dry_run": 0,
            "skipped_already_done": 0,
            "low_confidence": 0,
            "unmatched": 0,
            "duplicates_collapsed": 0,
            "api_error": 0,
        }

        if not self.chm.authenticate():
            logger.error("Authentication with ChMeetings failed")
            summary["api_error"] += 1
            return summary

        consent_rows = self.load_consent_export(consent_file)
        participants = self._fetch_participants(church_code=church_code)
        summary["rows_processed"] = len(consent_rows)

        qualifying_matches: List[Dict[str, Any]] = []
        audit_rows: List[Dict[str, Any]] = []

        for consent_row in consent_rows:
            best_participant: Optional[Dict[str, Any]] = None
            best_score = -1
            best_breakdown = {"birthdate": 0, "phone": 0, "email": 0, "name": 0}

            for participant in participants:
                score, breakdown = self._score(consent_row, participant)
                if score > best_score:
                    best_score = score
                    best_breakdown = breakdown
                    best_participant = participant

            if best_participant is None or best_score <= 0:
                summary["unmatched"] += 1
                logger.debug(
                    f"No matching participant found for consent row "
                    f"{consent_row['source_row_number']}: {consent_row['signer_name']} "
                    f"(score={max(best_score, 0)}, breakdown={_format_breakdown(best_breakdown)})"
                )
                audit_rows.append(
                    self._build_audit_row(
                        consent_row,
                        None,
                        score=max(best_score, 0),
                        breakdown=best_breakdown,
                        action="no_match",
                    )
                )
                continue

            if best_score < CONSENT_THRESHOLD:
                summary["low_confidence"] += 1
                logger.debug(
                    f"Low-confidence consent match for row {consent_row['source_row_number']} "
                    f"against participant {best_participant.get('chmeetings_id')}: score={best_score}"
                )
                audit_rows.append(
                    self._build_audit_row(
                        consent_row,
                        best_participant,
                        score=best_score,
                        breakdown=best_breakdown,
                        action="low_confidence",
                    )
                )
                continue

            qualifying_matches.append(
                {
                    "consent_row": consent_row,
                    "participant": best_participant,
                    "score": best_score,
                    "breakdown": best_breakdown,
                    "duplicate_rows_collapsed": 0,
                }
            )

        for match in self._deduplicate(qualifying_matches):
            participant = match["participant"]
            consent_row = match["consent_row"]
            score = match["score"]
            breakdown = match["breakdown"]
            duplicate_rows_collapsed = match["duplicate_rows_collapsed"]
            summary["duplicates_collapsed"] += duplicate_rows_collapsed
            chm_id = str(participant.get("chmeetings_id"))

            person = self.chm.get_person(chm_id)
            if not person:
                summary["api_error"] += 1
                logger.warning(
                    f"Could not retrieve ChMeetings person {chm_id} while processing consent row "
                    f"{consent_row['source_row_number']}"
                )
                audit_rows.append(
                    self._build_audit_row(
                        consent_row,
                        participant,
                        score=score,
                        breakdown=breakdown,
                        action="api_error",
                        duplicate_rows_collapsed=duplicate_rows_collapsed,
                    )
                )
                continue

            if self._is_consent_already_checked(person):
                summary["skipped_already_done"] += 1
                logger.info(
                    f"Skipped consent checkbox for {person.get('first_name', '')} "
                    f"{person.get('last_name', '')} ({chm_id}) - already checked"
                )
                audit_rows.append(
                    self._build_audit_row(
                        consent_row,
                        participant,
                        score=score,
                        breakdown=breakdown,
                        action="skipped_already_done",
                        duplicate_rows_collapsed=duplicate_rows_collapsed,
                        chm_person=person,
                    )
                )
                continue

            if dry_run:
                summary["dry_run"] += 1
                logger.info(
                    f"[dry-run] Would check consent checkbox for "
                    f"{person.get('first_name', '')} {person.get('last_name', '')} ({chm_id})"
                )
                audit_rows.append(
                    self._build_audit_row(
                        consent_row,
                        participant,
                        score=score,
                        breakdown=breakdown,
                        action="dry_run",
                        duplicate_rows_collapsed=duplicate_rows_collapsed,
                        chm_person=person,
                    )
                )
                continue

            update_payload = self._build_checklist_update(person)
            ok = self.chm.update_person(
                chm_id,
                person.get("first_name", participant.get("first_name", "")),
                person.get("last_name", participant.get("last_name", "")),
                update_payload,
                extra_person_data=person,
            )
            time.sleep(0.2)
            if ok:
                summary["checked"] += 1
                logger.info(
                    f"Auto-checked consent checkbox for {person.get('first_name', '')} "
                    f"{person.get('last_name', '')} ({chm_id})"
                )
                audit_rows.append(
                    self._build_audit_row(
                        consent_row,
                        participant,
                        score=score,
                        breakdown=breakdown,
                        action="checked",
                        duplicate_rows_collapsed=duplicate_rows_collapsed,
                        chm_person=person,
                    )
                )
            else:
                summary["api_error"] += 1
                logger.warning(
                    f"Failed to update consent checkbox for "
                    f"{person.get('first_name', '')} {person.get('last_name', '')} ({chm_id})"
                )
                audit_rows.append(
                    self._build_audit_row(
                        consent_row,
                        participant,
                        score=score,
                        breakdown=breakdown,
                        action="api_error",
                        duplicate_rows_collapsed=duplicate_rows_collapsed,
                        chm_person=person,
                    )
                )

        self._write_audit_file(audit_rows)

        if dry_run:
            logger.info(
                "check-consent [dry-run]: "
                f"{summary['rows_processed']} rows processed -> "
                f"{summary['dry_run']} dry_run, "
                f"{summary['skipped_already_done']} skipped (already done), "
                f"{summary['low_confidence']} low-confidence, "
                f"{summary['unmatched']} unmatched, "
                f"{summary['duplicates_collapsed']} duplicates collapsed, "
                f"{summary['api_error']} api_error"
            )
        else:
            logger.info(
                "check-consent: "
                f"{summary['rows_processed']} rows processed -> "
                f"{summary['checked']} checked, "
                f"{summary['skipped_already_done']} skipped (already done), "
                f"{summary['low_confidence']} low-confidence, "
                f"{summary['unmatched']} unmatched, "
                f"{summary['duplicates_collapsed']} duplicates collapsed, "
                f"{summary['api_error']} api_error"
            )

        return summary
