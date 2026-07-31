"""Retire stale WordPress participant rows described by the person alias map."""

import datetime
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd
from loguru import logger
from tenacity import RetryError

from config import APPROVAL_STATUS, DATA_DIR, VALIDATION_STATUS
from sync.person_aliases import AliasMap, PersonAliasError, load_person_aliases, resolve_chm_id
from wordpress.frontend_connector import WordPressConnector

AUDIT_FILE = DATA_DIR / "alias_reconciliation_audit.xlsx"


class ReconcileReadError(RuntimeError):
    """A WordPress read failed and must not be mistaken for an empty result."""


@dataclass(frozen=True)
class ReconcileState:
    rosters: List[Dict[str, Any]]
    approvals: List[Dict[str, Any]]
    issues: List[Dict[str, Any]]

    @property
    def active_approvals(self) -> List[Dict[str, Any]]:
        return [
            item
            for item in self.approvals
            if item.get("approval_status") != APPROVAL_STATUS["MERGED"]
        ]

    @property
    def has_work(self) -> bool:
        return bool(self.rosters or self.active_approvals or self.issues)


def _read(
    connector: Any,
    method: str,
    status_attribute: str,
    description: str,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    setattr(connector, status_attribute, "unknown")
    try:
        result = getattr(connector, method)(**kwargs) or []
    except RetryError as exc:
        raise ReconcileReadError(f"WordPress read failed: {description}") from exc
    if getattr(connector, status_attribute, None) == "failed":
        raise ReconcileReadError(f"WordPress read failed: {description}")
    return result


def _participant_rows(connector: Any, chm_id: str) -> List[Dict[str, Any]]:
    return _read(
        connector,
        "get_participants",
        "last_get_participants_status",
        f"participant chm_id={chm_id}",
        params={"chmeetings_id": chm_id},
    )


def _state(connector: Any, participant_id: int) -> ReconcileState:
    return ReconcileState(
        rosters=_read(
            connector,
            "get_rosters",
            "last_get_rosters_status",
            f"rosters for participant_id={participant_id}",
            params={"participant_id": participant_id},
        ),
        approvals=_read(
            connector,
            "get_approvals",
            "last_get_approvals_status",
            f"approvals for participant_id={participant_id}",
            params={"participant_id": participant_id},
        ),
        issues=_read(
            connector,
            "get_validation_issues",
            "last_get_validation_issues_status",
            f"open validation issues for participant_id={participant_id}",
            params={"participant_id": participant_id, "status": VALIDATION_STATUS["OPEN"]},
        ),
    )


def _badge_filename(stale: Dict[str, Any], stale_chm_id: str) -> str:
    try:
        from badges.generator import BadgeGenerator

        return BadgeGenerator().filename_for(
            {
                "chmeetings_id": stale_chm_id,
                "church_code": stale.get("church_code", ""),
            }
        )
    except ValueError as exc:
        logger.warning(f"[VAY SM] Could not compute stale badge filename: {exc}")
        return ""


def _apply_state(
    connector: Any,
    stale: Dict[str, Any],
    state: ReconcileState,
    row: Dict[str, Any],
) -> bool:
    participant_id = stale["participant_id"]
    success = True

    deleted = 0
    for roster in state.rosters:
        if connector.delete_roster(roster["roster_id"]):
            deleted += 1
        else:
            success = False
            logger.error(f"Failed to delete stale roster {roster.get('roster_id')}")

    participant_tombstoned = stale.get("approval_status") == APPROVAL_STATUS["MERGED"]
    if not participant_tombstoned:
        participant_tombstoned = connector.update_participant(
            participant_id,
            {"approval_status": APPROVAL_STATUS["MERGED"]},
        ) is not None
        success = success and participant_tombstoned

    approvals_tombstoned = 0
    for approval in state.active_approvals:
        if connector.update_approval(
            approval["approval_id"],
            {"approval_status": APPROVAL_STATUS["MERGED"]},
        ):
            approvals_tombstoned += 1
        else:
            success = False
            logger.error(f"Failed to tombstone stale approval {approval.get('approval_id')}")

    issues_resolved = 0
    resolved_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for issue in state.issues:
        if connector.update_validation_issue(
            issue["issue_id"],
            {"status": VALIDATION_STATUS["RESOLVED"], "resolved_at": resolved_at},
        ):
            issues_resolved += 1
        else:
            success = False
            logger.error(f"Failed to resolve stale validation issue {issue.get('issue_id')}")

    row.update(
        {
            "Rosters Deleted": deleted,
            "Participant Tombstoned": participant_tombstoned,
            "Approvals Tombstoned": approvals_tombstoned,
            "Validation Issues Resolved": issues_resolved,
        }
    )
    return success


def _reconcile_one(
    connector: Any,
    stale_chm_id: str,
    entry: Dict[str, str],
    aliases: AliasMap,
    execute: bool,
) -> Dict[str, Any]:
    canonical_chm_id = resolve_chm_id(stale_chm_id, aliases)
    row: Dict[str, Any] = {
        "Stale ChM ID": stale_chm_id,
        "Canonical ChM ID": canonical_chm_id,
        "Reason": entry.get("reason", ""),
        "Confirmed By": entry.get("confirmed_by", ""),
    }

    stale_rows = _participant_rows(connector, stale_chm_id)
    if not stale_rows:
        row["Outcome"] = "no_wp_row"
        return row

    stale = stale_rows[0]
    participant_id = stale["participant_id"]
    row.update(
        {
            "Stale WP Participant ID": participant_id,
            "Stale Name": f"{stale.get('first_name', '')} {stale.get('last_name', '')}".strip(),
            "Stale Approval Status": stale.get("approval_status", ""),
            # Computed once, as soon as a stale row exists, so every outcome that
            # has one reports the badge to delete — including already_merged and
            # canonical_missing_run_sync_first, not just the reconciled path.
            "Stale Badge Filename": _badge_filename(stale, stale_chm_id),
        }
    )

    already_merged = stale.get("approval_status") == APPROVAL_STATUS["MERGED"]
    if already_merged:
        state = _state(connector, participant_id)
        if not state.has_work:
            row["Outcome"] = "already_merged"
            return row
        row["Residual Work"] = (
            f"rosters={len(state.rosters)}, approvals={len(state.active_approvals)}, "
            f"validation_issues={len(state.issues)}"
        )
        if not execute:
            row["Outcome"] = "would_finish_residual"
            return row
        row["Outcome"] = "residual_completed" if _apply_state(connector, stale, state, row) else "error"
        return row

    canonical_rows = _participant_rows(connector, canonical_chm_id)
    if not canonical_rows:
        row["Outcome"] = "canonical_missing_run_sync_first"
        return row

    canonical = canonical_rows[0]
    state = _state(connector, participant_id)
    row.update(
        {
            "Canonical WP Participant ID": canonical.get("participant_id", ""),
            "Canonical Approval Status": canonical.get("approval_status", ""),
            "Stale Roster Rows": len(state.rosters),
        }
    )
    mismatch = (
        stale.get("approval_status") == APPROVAL_STATUS["APPROVED"]
        and canonical.get("approval_status") != APPROVAL_STATUS["APPROVED"]
    )
    row["Approval Mismatch"] = "yes" if mismatch else "no"
    if mismatch:
        logger.warning(
            f"[VAY SM] Approval mismatch for stale chm_id={stale_chm_id}; "
            "the canonical participant must be re-approved"
        )

    if not execute:
        row["Outcome"] = "would_reconcile"
        return row

    row["Outcome"] = "reconciled" if _apply_state(connector, stale, state, row) else "error"
    return row


def _write_audit(rows: List[Dict[str, Any]]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_excel(AUDIT_FILE, index=False)
        logger.info(f"Alias reconciliation audit written to {AUDIT_FILE}")
    except PermissionError:
        logger.warning(f"Could not write {AUDIT_FILE}; close it and rerun the command")


def apply_aliases(execute: bool = False) -> bool:
    """Report or apply WordPress cleanup for every configured person alias."""
    try:
        aliases = load_person_aliases()
    except PersonAliasError as exc:
        logger.error(f"[VAY SM] Refusing to reconcile person aliases: {exc}")
        return False

    if not aliases:
        logger.info("Person alias map is empty; nothing to reconcile")
        return True

    rows: List[Dict[str, Any]] = []
    with WordPressConnector() as connector:
        for stale_chm_id, entry in aliases.items():
            try:
                rows.append(_reconcile_one(connector, stale_chm_id, entry, aliases, execute))
            except ReconcileReadError as exc:
                logger.error(f"[VAY SM] {exc}")
                rows.append({"Stale ChM ID": stale_chm_id, "Outcome": "error_read_failed"})

    _write_audit(rows)
    outcomes = Counter(row["Outcome"] for row in rows)
    logger.info(f"Alias reconciliation complete: {dict(outcomes)}")
    return not any(outcome.startswith("error") for outcome in outcomes)
