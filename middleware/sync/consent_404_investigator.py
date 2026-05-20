import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from chmeetings.backend_connector import ChMeetingsConnector
from config import DATA_DIR, LOG_DIR
from sync.consent_checker import (
    CONSENT_SCORE_WEIGHTS,
    _full_name,
    _normalize_birthdate,
    _normalize_phone,
    _normalize_text,
)
from wordpress.frontend_connector import WordPressConnector


CONSENT_404_AUDIT_FILE = "consent_404_investigation.xlsx"
CONSENT_404_LOG_PATTERN = re.compile(
    r"Could not retrieve ChMeetings person (?P<chm_id>\S+) while processing consent row (?P<row>\d+)"
)


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _identity_from_wp_participant(participant: Dict[str, Any]) -> Dict[str, str]:
    return {
        "source": "wordpress",
        "participant_id": _safe_str(participant.get("participant_id")),
        "chmeetings_id": _safe_str(participant.get("chmeetings_id")),
        "first_name": _safe_str(participant.get("first_name")),
        "last_name": _safe_str(participant.get("last_name")),
        "name": _safe_str(
            f"{participant.get('first_name', '') or ''} {participant.get('last_name', '') or ''}"
        ),
        "name_norm": _full_name(
            participant.get("first_name", ""), participant.get("last_name", "")
        ),
        "email": _safe_str(participant.get("email")),
        "email_norm": _normalize_text(participant.get("email", "")),
        "phone": _safe_str(participant.get("phone")),
        "phone_norm": _normalize_phone(participant.get("phone", "")),
        "birthdate": _normalize_birthdate(participant.get("birthdate")),
        "church_code": _safe_str(participant.get("church_code")),
        "created_at": _safe_str(participant.get("created_at")),
        "updated_at": _safe_str(participant.get("updated_at")),
    }


def _identity_from_chm_person(person: Dict[str, Any]) -> Dict[str, str]:
    return {
        "source": "chmeetings",
        "participant_id": "",
        "chmeetings_id": _safe_str(person.get("id")),
        "first_name": _safe_str(person.get("first_name")),
        "last_name": _safe_str(person.get("last_name")),
        "name": _safe_str(
            f"{person.get('first_name', '') or ''} {person.get('last_name', '') or ''}"
        ),
        "name_norm": _full_name(person.get("first_name", ""), person.get("last_name", "")),
        "email": _safe_str(person.get("email")),
        "email_norm": _normalize_text(person.get("email", "")),
        "phone": _safe_str(person.get("mobile")),
        "phone_norm": _normalize_phone(person.get("mobile", "")),
        "birthdate": _normalize_birthdate(
            person.get("birth_date", person.get("birthdate", ""))
        ),
        "church_code": _safe_str(person.get("church_code")),
        "created_at": _safe_str(person.get("created_on")),
        "updated_at": _safe_str(person.get("updated_on")),
    }


def _score_identity_match(
    stale_identity: Dict[str, str], candidate_identity: Dict[str, str]
) -> Tuple[int, Dict[str, int], List[str]]:
    breakdown = {
        "birthdate": CONSENT_SCORE_WEIGHTS["birthdate"]
        if stale_identity["birthdate"]
        and stale_identity["birthdate"] == candidate_identity["birthdate"]
        else 0,
        "email": CONSENT_SCORE_WEIGHTS["email"]
        if stale_identity["email_norm"]
        and stale_identity["email_norm"] == candidate_identity["email_norm"]
        else 0,
        "phone": CONSENT_SCORE_WEIGHTS["phone"]
        if stale_identity["phone_norm"]
        and stale_identity["phone_norm"] == candidate_identity["phone_norm"]
        else 0,
        "name": CONSENT_SCORE_WEIGHTS["name"]
        if stale_identity["name_norm"]
        and stale_identity["name_norm"] == candidate_identity["name_norm"]
        else 0,
    }
    basis = [field for field, weight in breakdown.items() if weight]
    return sum(breakdown.values()), breakdown, basis


def _candidate_strength(score: int, basis: List[str]) -> str:
    basis_set = set(basis)
    # Family members often share phone/email, so require at least one
    # identity anchor (birthdate or exact full name) before calling a
    # replacement candidate "strong".
    if score >= 49 and ("birthdate" in basis_set or "name" in basis_set):
        return "strong"
    if score >= 27 and len(basis_set) >= 2:
        return "possible"
    if score > 0:
        return "weak"
    return ""


def _format_basis(basis: List[str]) -> str:
    return ", ".join(basis)


def _strength_rank(strength: str) -> int:
    return {
        "strong": 0,
        "possible": 1,
        "weak": 2,
        "": 3,
    }.get(strength, 3)


class Consent404Investigator:
    """Investigate consent rows whose stored ChMeetings IDs now return 404."""

    def __init__(
        self,
        chm_connector: ChMeetingsConnector,
        wp_connector: WordPressConnector,
        output_dir: Optional[Path] = None,
    ) -> None:
        self.chm = chm_connector
        self.wp = wp_connector
        self.output_dir = Path(output_dir or DATA_DIR)

    def _resolve_log_file(self, log_file: Optional[str]) -> Path:
        if log_file:
            return Path(log_file)

        candidates = sorted(
            LOG_DIR.glob("sportsfest_*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError("No sportsfest_*.log files were found in middleware/logs")
        return candidates[0]

    def _parse_log_cases(self, log_file: Path) -> List[Dict[str, Any]]:
        cases: List[Dict[str, Any]] = []
        seen = set()

        with log_file.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                match = CONSENT_404_LOG_PATTERN.search(line)
                if not match:
                    continue
                chm_id = match.group("chm_id").strip()
                consent_row = int(match.group("row"))
                dedupe_key = (chm_id, consent_row)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                cases.append(
                    {
                        "old_chmeetings_id": chm_id,
                        "consent_row": consent_row,
                        "log_line_number": line_number,
                    }
                )

        logger.info(
            f"Parsed {len(cases)} consent 404 case(s) from log file {log_file}"
        )
        return cases

    def _fetch_wp_participants(self) -> List[Dict[str, Any]]:
        all_participants: List[Dict[str, Any]] = []
        page = 1
        per_page = 100

        while True:
            batch = self.wp.get_participants({"page": page, "per_page": per_page}) or []
            if not batch:
                break
            all_participants.extend(batch)
            if len(batch) < per_page:
                break
            page += 1

        logger.info(f"Loaded {len(all_participants)} WordPress participant row(s)")
        return all_participants

    def _fetch_chm_people(self) -> List[Dict[str, Any]]:
        people = self.chm.get_people(
            {
                "page_size": 100,
                "include_additional_fields": False,
                "include_family_members": False,
                "include_organizations": False,
            }
        )
        logger.info(f"Loaded {len(people)} live ChMeetings people row(s)")
        return people

    def _find_candidates(
        self,
        stale_identity: Dict[str, str],
        wp_participants: List[Dict[str, Any]],
        chm_people: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        wp_candidates: List[Dict[str, Any]] = []
        chm_candidates: List[Dict[str, Any]] = []

        stale_participant_id = stale_identity["participant_id"]
        stale_chm_id = stale_identity["chmeetings_id"]

        for participant in wp_participants:
            candidate_identity = _identity_from_wp_participant(participant)
            if candidate_identity["participant_id"] == stale_participant_id:
                continue
            if candidate_identity["chmeetings_id"] == stale_chm_id:
                continue

            score, breakdown, basis = _score_identity_match(
                stale_identity, candidate_identity
            )
            if score <= 0:
                continue
            wp_candidates.append(
                {
                    **candidate_identity,
                    "score": score,
                    "strength": _candidate_strength(score, basis),
                    "basis": basis,
                    "basis_display": _format_basis(basis),
                    "breakdown": breakdown,
                }
            )

        for person in chm_people:
            candidate_identity = _identity_from_chm_person(person)
            if candidate_identity["chmeetings_id"] == stale_chm_id:
                continue

            score, breakdown, basis = _score_identity_match(
                stale_identity, candidate_identity
            )
            if score <= 0:
                continue
            chm_candidates.append(
                {
                    **candidate_identity,
                    "score": score,
                    "strength": _candidate_strength(score, basis),
                    "basis": basis,
                    "basis_display": _format_basis(basis),
                    "breakdown": breakdown,
                }
            )

        sort_key = lambda row: (
            _strength_rank(row["strength"]),
            -row["score"],
            row["chmeetings_id"],
            row["participant_id"],
        )
        wp_candidates.sort(key=sort_key)
        chm_candidates.sort(key=sort_key)
        return wp_candidates, chm_candidates

    def _classify_case(
        self,
        stale_identity: Dict[str, str],
        wp_candidates: List[Dict[str, Any]],
        chm_candidates: List[Dict[str, Any]],
    ) -> Tuple[str, str]:
        strong_wp = [candidate for candidate in wp_candidates if candidate["strength"] == "strong"]
        strong_chm = [candidate for candidate in chm_candidates if candidate["strength"] == "strong"]

        if not stale_identity["participant_id"]:
            return (
                "old_wp_record_missing",
                "No WordPress participant currently carries this stale ChMeetings ID.",
            )

        if len(strong_chm) > 1 or len(strong_wp) > 1:
            return (
                "ambiguous_multiple_strong_candidates",
                "More than one strong candidate matched; review the Candidates sheet manually.",
            )

        if strong_wp and strong_chm:
            wp_chm_id = strong_wp[0]["chmeetings_id"]
            chm_id = strong_chm[0]["chmeetings_id"]
            if wp_chm_id and wp_chm_id == chm_id:
                return (
                    "likely_reregistered_synced",
                    f"Strong WordPress and ChMeetings candidate agree on new ID {chm_id}.",
                )
            return (
                "possible_match_manual_review",
                "Strong WordPress and ChMeetings candidates disagree on the new ID.",
            )

        if strong_chm:
            return (
                "likely_reregistered_not_synced",
                f"Found strong live ChMeetings candidate {strong_chm[0]['chmeetings_id']}, but no matching new WordPress row yet.",
            )

        if strong_wp:
            return (
                "likely_reregistered_wp_only",
                f"Found strong WordPress candidate with new ID {strong_wp[0]['chmeetings_id']}, but no strong live ChMeetings match was found.",
            )

        if wp_candidates or chm_candidates:
            return (
                "possible_match_manual_review",
                "Only partial matches were found; review the Candidates sheet manually.",
            )

        return (
            "likely_deleted_or_removed",
            "No matching live ChMeetings or replacement WordPress record was found.",
        )

    def _build_summary_row(
        self,
        case: Dict[str, Any],
        stale_identity: Dict[str, str],
        wp_candidates: List[Dict[str, Any]],
        chm_candidates: List[Dict[str, Any]],
        result: str,
        note: str,
    ) -> Dict[str, Any]:
        best_wp = wp_candidates[0] if wp_candidates else {}
        best_chm = chm_candidates[0] if chm_candidates else {}
        strong_wp_ids = [
            candidate["chmeetings_id"]
            for candidate in wp_candidates
            if candidate["strength"] == "strong"
        ]
        strong_chm_ids = [
            candidate["chmeetings_id"]
            for candidate in chm_candidates
            if candidate["strength"] == "strong"
        ]

        return {
            "Old ChM ID": case["old_chmeetings_id"],
            "Consent Row": case["consent_row"],
            "Log Line": case["log_line_number"],
            "Old WP Participant ID": stale_identity["participant_id"],
            "Old WP Name": stale_identity["name"],
            "Church Code": stale_identity["church_code"],
            "Old WP Email": stale_identity["email"],
            "Old WP Phone": stale_identity["phone"],
            "Old WP Birthdate": stale_identity["birthdate"],
            "Old WP Created At": stale_identity["created_at"],
            "Old WP Updated At": stale_identity["updated_at"],
            "Investigation Result": result,
            "Best WP Candidate ID": best_wp.get("participant_id", ""),
            "Best WP Candidate ChM ID": best_wp.get("chmeetings_id", ""),
            "Best WP Candidate Score": best_wp.get("score", 0),
            "Best WP Match Basis": best_wp.get("basis_display", ""),
            "Best ChM Candidate ID": best_chm.get("chmeetings_id", ""),
            "Best ChM Candidate Score": best_chm.get("score", 0),
            "Best ChM Match Basis": best_chm.get("basis_display", ""),
            "Strong WP Candidate IDs": ", ".join(strong_wp_ids),
            "Strong ChM Candidate IDs": ", ".join(strong_chm_ids),
            "Notes": note,
        }

    def _build_candidate_rows(
        self,
        case: Dict[str, Any],
        wp_candidates: List[Dict[str, Any]],
        chm_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        for candidate in wp_candidates + chm_candidates:
            rows.append(
                {
                    "Old ChM ID": case["old_chmeetings_id"],
                    "Consent Row": case["consent_row"],
                    "Candidate Source": candidate["source"],
                    "Candidate Strength": candidate["strength"],
                    "Candidate Score": candidate["score"],
                    "Match Basis": candidate["basis_display"],
                    "Candidate WP Participant ID": candidate["participant_id"],
                    "Candidate ChM ID": candidate["chmeetings_id"],
                    "Candidate Name": candidate["name"],
                    "Candidate Church Code": candidate["church_code"],
                    "Candidate Email": candidate["email"],
                    "Candidate Phone": candidate["phone"],
                    "Candidate Birthdate": candidate["birthdate"],
                    "Candidate Created/Seen": candidate["created_at"],
                    "Candidate Updated": candidate["updated_at"],
                }
            )

        return rows

    def _write_audit_file(
        self,
        summary_rows: List[Dict[str, Any]],
        candidate_rows: List[Dict[str, Any]],
        output_file: Optional[str] = None,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        audit_file = Path(output_file) if output_file else self.output_dir / CONSENT_404_AUDIT_FILE

        summary_df = pd.DataFrame(summary_rows)
        candidate_df = pd.DataFrame(candidate_rows)

        try:
            with pd.ExcelWriter(audit_file) as writer:
                summary_df.to_excel(writer, sheet_name="Cases", index=False)
                candidate_df.to_excel(writer, sheet_name="Candidates", index=False)
            logger.info(f"Consent 404 investigation workbook written: {audit_file}")
            return audit_file
        except PermissionError:
            logger.warning(
                f"Could not write investigation workbook - {audit_file} is open in another program."
            )
            return audit_file

    def run(
        self,
        *,
        log_file: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        summary = {
            "cases": 0,
            "likely_reregistered_synced": 0,
            "likely_reregistered_not_synced": 0,
            "likely_reregistered_wp_only": 0,
            "likely_deleted_or_removed": 0,
            "possible_match_manual_review": 0,
            "ambiguous_multiple_strong_candidates": 0,
            "old_wp_record_missing": 0,
            "api_error": 0,
            "output_file": "",
        }

        try:
            resolved_log_file = self._resolve_log_file(log_file)
        except FileNotFoundError as exc:
            logger.error(str(exc))
            summary["api_error"] += 1
            return summary

        if not resolved_log_file.exists():
            logger.error(f"Log file not found: {resolved_log_file}")
            summary["api_error"] += 1
            return summary

        cases = self._parse_log_cases(resolved_log_file)
        summary["cases"] = len(cases)
        if not cases:
            logger.info("No consent 404 cases found in the selected log.")
            output_path = self._write_audit_file([], [], output_file=output_file)
            summary["output_file"] = str(output_path)
            return summary

        if not self.chm.authenticate():
            logger.error("Authentication with ChMeetings failed")
            summary["api_error"] += 1
            return summary

        try:
            wp_participants = self._fetch_wp_participants()
            chm_people = self._fetch_chm_people()
        except Exception as exc:
            logger.error(f"Consent 404 investigation failed while loading live data: {exc}")
            summary["api_error"] += 1
            return summary

        wp_by_old_chm_id = {
            _safe_str(participant.get("chmeetings_id")): participant
            for participant in wp_participants
            if participant.get("chmeetings_id")
        }

        summary_rows: List[Dict[str, Any]] = []
        candidate_rows: List[Dict[str, Any]] = []

        for case in cases:
            stale_participant = wp_by_old_chm_id.get(case["old_chmeetings_id"], {})
            stale_identity = _identity_from_wp_participant(stale_participant)
            if not stale_identity["chmeetings_id"]:
                stale_identity["chmeetings_id"] = case["old_chmeetings_id"]

            wp_candidates, chm_candidates = self._find_candidates(
                stale_identity, wp_participants, chm_people
            )
            result, note = self._classify_case(
                stale_identity, wp_candidates, chm_candidates
            )
            summary[result] += 1

            summary_rows.append(
                self._build_summary_row(
                    case, stale_identity, wp_candidates, chm_candidates, result, note
                )
            )
            candidate_rows.extend(
                self._build_candidate_rows(case, wp_candidates, chm_candidates)
            )

            logger.info(
                f"Consent 404 case old_id={case['old_chmeetings_id']} row={case['consent_row']} -> "
                f"{result}"
            )

        output_path = self._write_audit_file(
            summary_rows, candidate_rows, output_file=output_file
        )
        summary["output_file"] = str(output_path)
        logger.info(
            "Consent 404 investigation summary: "
            f"cases={summary['cases']}, "
            f"likely_reregistered_synced={summary['likely_reregistered_synced']}, "
            f"likely_reregistered_not_synced={summary['likely_reregistered_not_synced']}, "
            f"likely_reregistered_wp_only={summary['likely_reregistered_wp_only']}, "
            f"likely_deleted_or_removed={summary['likely_deleted_or_removed']}, "
            f"manual_review={summary['possible_match_manual_review']}, "
            f"ambiguous={summary['ambiguous_multiple_strong_candidates']}, "
            f"old_wp_record_missing={summary['old_wp_record_missing']}"
        )
        return summary
