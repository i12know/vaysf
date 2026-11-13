"""Propose likely duplicate WordPress participants for the person alias map.

``find-duplicates`` (#311, docs/CANONICAL_IDENTITY_RFC.md §4.4) scores every
pair of live WordPress participants with the shared identity scoring and
writes a workbook of candidate pairs. Each proposal carries a one-line JSON
entry the operator can paste into ``person_aliases.local.json`` for
``apply-aliases`` to act on.

Guardrail G3 — propose, never merge. This module:

- reads WordPress participants and rosters, and nothing else;
- never talks to ChMeetings (it does not import that connector);
- never calls a WordPress write;
- reads the alias map only to skip IDs that are already aliased, and never
  writes it. The only file it creates is the proposal workbook.

Whether two rows are one human is a pastoral judgment. The workbook is the
evidence for that judgment, not the judgment.
"""

import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import requests
from loguru import logger
from tenacity import RetryError

from config import APPROVAL_STATUS, DATA_DIR
from sync.identity_scoring import (
    STRENGTH_POSSIBLE,
    STRENGTH_STRONG,
    candidate_strength,
    format_basis,
    full_name,
    has_identity_anchor,
    identity_from_wp_participant,
    safe_str,
    score_identity_match,
    strength_rank,
)
from sync.person_aliases import AliasMap, PersonAliasError, load_person_aliases, resolve_chm_id
from validation.name_matcher import normalized_name

# Holds names, birthdates and contact details: git-ignored, like every other
# operator workbook under data/.
DUPLICATE_AUDIT_FILE = "duplicate_participants.xlsx"

PROPOSALS_SHEET = "Proposals"
NOT_PROPOSED_SHEET = "Not Proposed"
HOW_TO_SHEET = "How To Use"

_PAGE_SIZE = 100  # the plugin caps per_page at 100
_MAX_PAGES = 200

# Two rows can only score above zero if they share one of these, so comparing
# rows within each shared value finds every scoring pair without comparing
# everyone to everyone.
_BLOCKING_FIELDS = ("birthdate", "email_norm", "phone_norm", "name_norm")

_SIDE_COLUMNS = (
    "ChM ID",
    "WP Participant ID",
    "Name",
    "Church Code",
    "Birthdate",
    "Email",
    "Phone",
    "Gender",
    "Approval Status",
    "Consent On File",
    "Updated At",
)
PROPOSAL_COLUMNS = [
    "Strength",
    "Score",
    "Match Basis",
    "Review Notes",
    "Alias Map Snippet",
    "Canonical Pick Basis",
    *(f"Canonical {column}" for column in _SIDE_COLUMNS),
    "Canonical Has Rosters",
    *(f"Stale {column}" for column in _SIDE_COLUMNS),
    "Stale Has Rosters",
]
NOT_PROPOSED_COLUMNS = [
    "Why Not Proposed",
    "Score",
    "Match Basis",
    "Review Notes",
    *(f"A {column}" for column in _SIDE_COLUMNS),
    *(f"B {column}" for column in _SIDE_COLUMNS),
]

_HOW_TO_LINES = [
    "This workbook is a proposal. find-duplicates changed nothing in ChMeetings or "
    "WordPress and did not touch the alias map.",
    f"'{PROPOSALS_SHEET}' lists pairs of live WordPress participants that look like one "
    "person. For each row, decide whether they are. Read 'Review Notes' first.",
    "A pair with different names that shares a birthdate, phone and email can be one "
    "person under two names. It can also be twins. The data cannot tell them apart; "
    "you can.",
    "Check the direction before you paste. The canonical ID must be the record that "
    "is still live in ChMeetings: run 'python main.py inspect-person --chm-id <id>' "
    "on both IDs. The pick here only sees WordPress: approved, then has rosters, "
    "then most recent update.",
    "To confirm a pair, paste its 'Alias Map Snippet' inside the outer { } of "
    "data/person_aliases.local.json, with a comma between entries, and fill in "
    "confirmed_by and confirmed_on. A stale ID may appear in the file only once.",
    "Then run 'python main.py apply-aliases', review its audit workbook, and run "
    "'python main.py apply-aliases --execute'.",
    "If the stale row has consent on file and the canonical row does not, rerun "
    "check-consent after apply-aliases so the signed form is credited to the "
    "canonical person. A confirmed merge never requires the guardian to sign again.",
    f"'{NOT_PROPOSED_SHEET}' lists pairs that share contact details but are not offered "
    "as a merge, with the reason. A shared phone and email with no matching birthdate "
    "or name is what siblings and parent-managed signups look like. So is a pair with "
    "different names and different genders.",
    "A pair with the same name and different genders is still proposed: that is usually "
    "a gender typed wrong on one registration. Fix it in ChMeetings before applying "
    "the alias.",
]


class DuplicateFinderReadError(RuntimeError):
    """A WordPress read failed and must not be mistaken for an empty result."""


def duplicate_name_key(first_name: Any, last_name: Any) -> str:
    """Diacritic-insensitive name key, so "Ngọc Lê" and "Ngoc Le" are one name.

    For matching only; the name as registered is what the workbook shows.
    ``normalized_name`` strips combining marks, which leaves ``đ`` alone
    (it is a letter of its own, not ``d`` plus a mark), so "Đinh" and "Dinh"
    are folded here.
    """
    return normalized_name(f"{first_name or ''} {last_name or ''}").replace("đ", "d")


def _genders_differ(left: Dict[str, str], right: Dict[str, str]) -> bool:
    """True only when both rows record a gender and the two disagree."""
    return bool(
        left["gender"] and right["gender"] and left["gender"].lower() != right["gender"].lower()
    )


def _is_numeric_id(value: str) -> bool:
    return bool(value) and value.isascii() and value.isdigit()


def _epoch(value: Any) -> float:
    parsed = pd.to_datetime(value or None, errors="coerce", utc=True)
    return float("-inf") if pd.isna(parsed) else parsed.timestamp()


def _has_consent(value: Any) -> bool:
    return safe_str(value).lower() in {"1", "true"}


def alias_snippet(stale: Dict[str, str], canonical: Dict[str, str], reason: str) -> str:
    """One alias-map entry, ``"<stale id>": {...}``, on a single line.

    Single line on purpose: Excel wraps a copied cell in quotes and doubles
    the quotes inside it when the cell contains a line break.
    ``confirmed_by`` and ``confirmed_on`` are left blank for the operator —
    a proposal is not a confirmation.
    """
    entry = {
        "canonical_chm_id": canonical["chmeetings_id"],
        "reason": reason,
        "confirmed_by": "",
        "confirmed_on": "",
        "note": f"{stale['name']} / {canonical['name']}",
    }
    return (
        f"{json.dumps(stale['chmeetings_id'])}: "
        f"{json.dumps(entry, ensure_ascii=False)}"
    )


class DuplicateFinder:
    """Score all live WordPress participant pairs and write a proposal workbook."""

    def __init__(self, wp_connector: Any, output_dir: Optional[Path] = None) -> None:
        self.wp = wp_connector
        self.output_dir = Path(output_dir or DATA_DIR)

    # ── WordPress reads (the only I/O besides the workbook) ──────────────────

    def _read(
        self, method: str, status_attribute: str, description: str, params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        setattr(self.wp, status_attribute, "unknown")
        try:
            result = getattr(self.wp, method)(params)
        except (RetryError, requests.RequestException) as exc:
            raise DuplicateFinderReadError(f"WordPress read failed: {description}") from exc
        if getattr(self.wp, status_attribute, None) == "failed":
            raise DuplicateFinderReadError(f"WordPress read failed: {description}")
        return result or []

    def _fetch_participants(self) -> List[Dict[str, Any]]:
        participants: List[Dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            batch = self._read(
                "get_participants",
                "last_get_participants_status",
                f"participants page {page}",
                {"page": page, "per_page": _PAGE_SIZE},
            )
            participants.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
        else:
            raise DuplicateFinderReadError(
                f"WordPress read failed: more than {_MAX_PAGES * _PAGE_SIZE} participants"
            )

        # The connector keeps WordPress's X-WP-Total here; 0 means "not reported".
        total = getattr(self.wp, "total_participants", None)
        if isinstance(total, int) and total > 0 and total != len(participants):
            logger.warning(
                f"[VAY SM] find-duplicates loaded {len(participants)} WordPress participant "
                f"row(s) but WordPress reported {total}; the scan may be incomplete. Rerun."
            )
        logger.info(
            f"[VAY SM] find-duplicates loaded {len(participants)} WordPress participant row(s)"
        )
        return participants

    def _has_rosters(self, participant_id: str, cache: Dict[str, Optional[bool]]) -> Optional[bool]:
        """True/False, or None when the roster read failed (unknown, not "no")."""
        if participant_id not in cache:
            try:
                rosters = self._read(
                    "get_rosters",
                    "last_get_rosters_status",
                    f"rosters for participant_id={participant_id}",
                    # all_team_orders: without it the endpoint hides rosters
                    # that staff have given a team order.
                    {"participant_id": int(participant_id), "all_team_orders": 1},
                )
                cache[participant_id] = bool(rosters)
            except (DuplicateFinderReadError, ValueError) as exc:
                logger.warning(f"[VAY SM] {exc}; canonical pick will not use rosters for this row")
                cache[participant_id] = None
        return cache[participant_id]

    # ── Selection ────────────────────────────────────────────────────────────

    @staticmethod
    def _live_records(
        participants: List[Dict[str, Any]], aliases: AliasMap
    ) -> Tuple[List[Dict[str, str]], Counter]:
        """Identity records for the rows worth comparing, and why the rest were skipped."""
        records: List[Dict[str, str]] = []
        skipped: Counter = Counter()
        for participant in participants:
            chm_id = safe_str(participant.get("chmeetings_id"))
            if participant.get("approval_status") == APPROVAL_STATUS["MERGED"]:
                skipped["merged"] += 1  # already retired by apply-aliases
            elif not _is_numeric_id(chm_id):
                skipped["no_chm_id"] += 1  # nothing an alias entry could name
            elif chm_id in aliases:
                skipped["aliased"] += 1  # the operator has already decided this one
            else:
                record = identity_from_wp_participant(participant, name_key=duplicate_name_key)
                record.update(
                    {
                        "exact_name_norm": full_name(
                            participant.get("first_name", ""), participant.get("last_name", "")
                        ),
                        "gender": safe_str(participant.get("gender")),
                        "approval_status": safe_str(participant.get("approval_status")),
                        "consent": "yes" if _has_consent(participant.get("consent_status")) else "no",
                    }
                )
                records.append(record)
        return records, skipped

    @staticmethod
    def _blocks(records: List[Dict[str, str]]) -> Dict[str, Dict[str, List[int]]]:
        blocks: Dict[str, Dict[str, List[int]]] = {field: defaultdict(list) for field in _BLOCKING_FIELDS}
        for index, record in enumerate(records):
            for field in _BLOCKING_FIELDS:
                if record[field]:
                    blocks[field][record[field]].append(index)
        return blocks

    @staticmethod
    def _candidate_pairs(blocks: Dict[str, Dict[str, List[int]]]) -> Set[Tuple[int, int]]:
        pairs: Set[Tuple[int, int]] = set()
        for field_blocks in blocks.values():
            for members in field_blocks.values():
                pairs.update(combinations(members, 2))
        return pairs

    # ── Judging one pair ─────────────────────────────────────────────────────

    @staticmethod
    def _why_not_proposed(left: Dict[str, str], right: Dict[str, str], basis: List[str]) -> str:
        """Empty when the pair may be offered as a merge; otherwise the reason."""
        if not has_identity_anchor(basis):
            return (
                "Shared contact only: no matching birthdate or name. Typical of siblings "
                "or a parent-managed signup."
            )
        # Different names and different genders is what brother/sister twins
        # look like. With a matching name the same disagreement is far more
        # likely a gender typed wrong on one registration (#395), so that pair
        # is proposed and the disagreement becomes an evidence note.
        if "name" not in basis and _genders_differ(left, right):
            return f"Genders differ ({left['gender']} / {right['gender']})."
        return ""

    @staticmethod
    def _evidence_notes(
        left: Dict[str, str],
        right: Dict[str, str],
        basis: List[str],
        blocks: Dict[str, Dict[str, List[int]]],
    ) -> List[str]:
        notes: List[str] = []
        if "name" not in basis:
            notes.append(
                "Names differ: one person under two names, or twins/relatives sharing a "
                "household's contact details?"
            )
        elif left["exact_name_norm"] != right["exact_name_norm"]:
            notes.append("Names match only after removing diacritics.")
        if "birthdate" not in basis:
            if left["birthdate"] and right["birthdate"]:
                notes.append("Birthdates differ.")
            else:
                notes.append("Birthdate missing on at least one row.")
        if "name" in basis and _genders_differ(left, right):
            notes.append(
                f"Genders differ ({left['gender']} / {right['gender']}): likely a data-entry "
                "error. Fix the gender in ChMeetings before applying the alias."
            )
        if left["church_code"].upper() != right["church_code"].upper():
            notes.append("Different churches.")
        for field, block_field in (("phone", "phone_norm"), ("email", "email_norm")):
            shared_by = len(blocks[block_field].get(left[block_field], []))
            if field in basis and shared_by > 2:
                notes.append(f"{field.capitalize()} shared by {shared_by} live participants.")
        return notes

    def _pick_canonical(
        self,
        left: Dict[str, str],
        right: Dict[str, str],
        roster_cache: Dict[str, Optional[bool]],
    ) -> Tuple[Dict[str, str], Dict[str, str], str, List[str]]:
        """Proposed (canonical, stale, basis, notes): approved > has rosters > most recent update."""
        notes: List[str] = []
        rosters = {
            record["chmeetings_id"]: self._has_rosters(record["participant_id"], roster_cache)
            for record in (left, right)
        }
        rosters_known = None not in rosters.values()
        if not rosters_known:
            notes.append("Roster lookup failed; the canonical pick did not consider rosters.")

        def rank(record: Dict[str, str]) -> Tuple[Any, ...]:
            return (
                record["approval_status"] == APPROVAL_STATUS["APPROVED"],
                bool(rosters[record["chmeetings_id"]]) if rosters_known else False,
                _epoch(record["updated_at"]),
                int(record["chmeetings_id"]),
            )

        labels = ("approved", "has rosters", "most recent update")
        left_rank, right_rank = rank(left), rank(right)
        canonical, stale = (left, right) if left_rank > right_rank else (right, left)
        basis = next(
            (label for label, a, b in zip(labels, left_rank, right_rank) if a != b),
            "tie-break: newer ChMeetings ID",
        )
        if basis.startswith("tie-break"):
            notes.append("No clear canonical row; direction is a tie-break. Confirm it.")
        return canonical, stale, basis, notes

    @staticmethod
    def _roster_label(has_rosters: Optional[bool]) -> str:
        return "unknown" if has_rosters is None else "yes" if has_rosters else "no"

    @staticmethod
    def _side(prefix: str, record: Dict[str, str]) -> Dict[str, Any]:
        return {
            f"{prefix} ChM ID": record["chmeetings_id"],
            f"{prefix} WP Participant ID": record["participant_id"],
            f"{prefix} Name": record["name"],
            f"{prefix} Church Code": record["church_code"],
            f"{prefix} Birthdate": record["birthdate"],
            f"{prefix} Email": record["email"],
            f"{prefix} Phone": record["phone"],
            f"{prefix} Gender": record["gender"],
            f"{prefix} Approval Status": record["approval_status"],
            f"{prefix} Consent On File": record["consent"],
            f"{prefix} Updated At": record["updated_at"],
        }

    def _build_rows(
        self, records: List[Dict[str, str]], aliases: AliasMap, summary: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        blocks = self._blocks(records)
        pairs = self._candidate_pairs(blocks)
        summary["pairs_scored"] = len(pairs)
        alias_targets = {resolve_chm_id(stale_id, aliases) for stale_id in aliases}

        proposals: List[Dict[str, Any]] = []
        not_proposed: List[Dict[str, Any]] = []
        roster_cache: Dict[str, Optional[bool]] = {}

        for left_index, right_index in sorted(pairs):
            left, right = records[left_index], records[right_index]
            if left["chmeetings_id"] == right["chmeetings_id"]:
                continue
            score, _, basis = score_identity_match(left, right)
            strength = candidate_strength(score, basis)
            if strength not in (STRENGTH_STRONG, STRENGTH_POSSIBLE):
                continue  # one shared field: far too common to list

            notes = self._evidence_notes(left, right, basis, blocks)
            reason = self._why_not_proposed(left, right, basis)
            if reason:
                not_proposed.append(
                    {
                        "Why Not Proposed": reason,
                        "Score": score,
                        "Match Basis": format_basis(basis),
                        "Review Notes": " ".join(notes),
                        **self._side("A", left),
                        **self._side("B", right),
                    }
                )
                continue

            canonical, stale, pick_basis, pick_notes = self._pick_canonical(left, right, roster_cache)
            notes.extend(pick_notes)
            if stale["consent"] == "yes" and canonical["consent"] != "yes":
                notes.append(
                    "Consent is on file for the stale row only. It carries to the canonical "
                    "person: rerun check-consent after apply-aliases; no new signature."
                )
            if stale["chmeetings_id"] in alias_targets:
                notes.append(
                    f"ChM ID {stale['chmeetings_id']} is already the canonical target of an "
                    "existing alias; this entry would chain that alias onward."
                )
            proposals.append(
                {
                    "Strength": strength,
                    "Score": score,
                    "Match Basis": format_basis(basis),
                    "_notes": notes,
                    "Alias Map Snippet": alias_snippet(
                        stale,
                        canonical,
                        f"find-duplicates: {strength} match, score {score} ({format_basis(basis)})",
                    ),
                    "Canonical Pick Basis": pick_basis,
                    **self._side("Canonical", canonical),
                    "Canonical Has Rosters": self._roster_label(
                        roster_cache[canonical["participant_id"]]
                    ),
                    **self._side("Stale", stale),
                    "Stale Has Rosters": self._roster_label(roster_cache[stale["participant_id"]]),
                }
            )

        # An ID can be an alias-map key only once; say so when the proposals
        # would have the operator paste the same stale ID twice.
        stale_counts = Counter(row["Stale ChM ID"] for row in proposals)
        for row in proposals:
            notes = row.pop("_notes")
            if stale_counts[row["Stale ChM ID"]] > 1:
                notes.append(
                    f"ChM ID {row['Stale ChM ID']} is the stale side of "
                    f"{stale_counts[row['Stale ChM ID']]} proposals; use at most one of them."
                )
            row["Review Notes"] = " ".join(notes)

        proposals.sort(
            key=lambda row: (
                strength_rank(row["Strength"]),
                -row["Score"],
                int(row["Canonical ChM ID"]),
                int(row["Stale ChM ID"]),
            )
        )
        not_proposed.sort(key=lambda row: (-row["Score"], int(row["A ChM ID"]), int(row["B ChM ID"])))
        return proposals, not_proposed

    # ── Output ───────────────────────────────────────────────────────────────

    def _write_workbook(
        self,
        proposals: List[Dict[str, Any]],
        not_proposed: List[Dict[str, Any]],
        output_file: Optional[str] = None,
    ) -> Path:
        workbook = Path(output_file) if output_file else self.output_dir / DUPLICATE_AUDIT_FILE
        workbook.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(workbook) as writer:
            pd.DataFrame(proposals, columns=PROPOSAL_COLUMNS).to_excel(
                writer, sheet_name=PROPOSALS_SHEET, index=False
            )
            pd.DataFrame(not_proposed, columns=NOT_PROPOSED_COLUMNS).to_excel(
                writer, sheet_name=NOT_PROPOSED_SHEET, index=False
            )
            pd.DataFrame({"How to use this workbook": _HOW_TO_LINES}).to_excel(
                writer, sheet_name=HOW_TO_SHEET, index=False
            )
        return workbook

    def run(self, *, output_file: Optional[str] = None) -> Dict[str, Any]:
        """Scan, write the proposal workbook, and return a run summary."""
        summary: Dict[str, Any] = {
            "participants": 0,
            "live": 0,
            "skipped_merged": 0,
            "skipped_aliased": 0,
            "skipped_no_chm_id": 0,
            "pairs_scored": 0,
            "strong": 0,
            "possible": 0,
            "not_proposed": 0,
            "error": 0,
            "output_file": "",
        }

        try:
            # Fail closed, like apply-aliases: with an unreadable map there is
            # no telling which IDs the operator has already aliased.
            aliases = load_person_aliases()
        except PersonAliasError as exc:
            logger.error(
                f"[VAY SM] find-duplicates cannot tell which IDs are already aliased: {exc}. "
                "Fix the alias file and rerun."
            )
            summary["error"] += 1
            return summary

        try:
            participants = self._fetch_participants()
        except DuplicateFinderReadError as exc:
            logger.error(f"[VAY SM] {exc}; no proposal workbook was written")
            summary["error"] += 1
            return summary

        records, skipped = self._live_records(participants, aliases)
        summary.update(
            {
                "participants": len(participants),
                "live": len(records),
                "skipped_merged": skipped["merged"],
                "skipped_aliased": skipped["aliased"],
                "skipped_no_chm_id": skipped["no_chm_id"],
            }
        )

        proposals, not_proposed = self._build_rows(records, aliases, summary)
        strengths = Counter(row["Strength"] for row in proposals)
        summary.update(
            {
                "strong": strengths[STRENGTH_STRONG],
                "possible": strengths[STRENGTH_POSSIBLE],
                "not_proposed": len(not_proposed),
            }
        )

        try:
            workbook = self._write_workbook(proposals, not_proposed, output_file=output_file)
        except OSError as exc:
            logger.error(
                f"[VAY SM] Could not write the duplicate proposal workbook ({exc}). "
                "If it is open in Excel, close it and rerun."
            )
            summary["error"] += 1
            return summary

        summary["output_file"] = str(workbook)
        logger.info(
            f"[VAY SM] find-duplicates: {summary['live']} live participant(s) compared "
            f"(skipped {summary['skipped_merged']} merged, {summary['skipped_aliased']} already "
            f"aliased, {summary['skipped_no_chm_id']} without a numeric ChMeetings ID); "
            f"{summary['pairs_scored']} pair(s) scored -> {summary['strong']} strong, "
            f"{summary['possible']} possible, {summary['not_proposed']} listed but not proposed."
        )
        logger.info(
            f"[VAY SM] Proposal workbook written: {workbook}. Nothing was changed in "
            "ChMeetings, WordPress or the alias map; confirmed entries are yours to paste."
        )
        return summary
