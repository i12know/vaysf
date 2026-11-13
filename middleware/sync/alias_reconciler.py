"""Retire stale WordPress participant rows described by the person alias map.

Writes go to WordPress only. ChMeetings is read, never written: before an
alias is reported on or applied, its canonical ID is confirmed to be a live
ChMeetings person (#396).
"""

import datetime
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd
import requests
from loguru import logger
from tenacity import RetryError

from chmeetings.backend_connector import CHM_MIN_REQUEST_INTERVAL_SECONDS, ChMeetingsConnector
from config import APPROVAL_STATUS, DATA_DIR, VALIDATION_STATUS
from sync.person_aliases import AliasMap, PersonAliasError, load_person_aliases, resolve_chm_id
from wordpress.frontend_connector import WordPressConnector

# One workbook per run, e.g. alias_reconciliation_20261112_143005_audit.xlsx.
# The name keeps the `_audit.xlsx` suffix so it stays git-ignored
# (`middleware/data/*_audit.xlsx`). A run never overwrites an earlier run's
# record: the report that lists who lost a pastor approval must survive the
# confirming rerun.
AUDIT_FILE_PREFIX = "alias_reconciliation_"
AUDIT_FILE_SUFFIX = "_audit.xlsx"


def _audit_path(now: Optional[datetime.datetime] = None) -> Path:
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"{AUDIT_FILE_PREFIX}{stamp}{AUDIT_FILE_SUFFIX}"
    counter = 2
    while path.exists():
        path = DATA_DIR / f"{AUDIT_FILE_PREFIX}{stamp}_{counter}{AUDIT_FILE_SUFFIX}"
        counter += 1
    return path


# Outcomes that write nothing but still need the operator: the command exits
# non-zero so they cannot scroll past unnoticed.
_FAILING_OUTCOMES = frozenset(
    {"canonical_is_merged", "canonical_not_in_chmeetings", "canonical_unverified"}
)

# Results of the ChMeetings lookup of an alias's canonical ID (#396).
CANONICAL_EXISTS = "exists"
CANONICAL_NOT_FOUND = "not_found"
CANONICAL_UNVERIFIED = "unverified"

# result -> (audit outcome, "Canonical In ChMeetings" cell, why the entry was skipped)
_CANONICAL_SKIPS = {
    CANONICAL_NOT_FOUND: (
        "canonical_not_in_chmeetings",
        "not found",
        "canonical ID not found in ChMeetings; check direction (the stale ID may be the "
        "live one) and fix the alias file",
    ),
    CANONICAL_UNVERIFIED: (
        "canonical_unverified",
        "could not verify",
        "could not verify the canonical ID in ChMeetings; nothing was applied for this "
        "entry. Rerun apply-aliases.",
    ),
}


_ISSUE_PAGE_SIZE = 100
_ISSUE_MAX_PAGES = 50


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


class _CanonicalVerifier:
    """Ask ChMeetings, with one GET per canonical ID, whether that person exists.

    An alias whose canonical ID is gone sends every later sync and approval
    write to a dead ID. Anything other than a clear "exists" keeps the entry
    from being applied: a 404 and a failed lookup are both skips, reported
    differently. A 404 is reported as "not found", never as "deleted" — the
    VAY SM key gets the same 404 for a person moved to another tenant.

    Read-only: the only ChMeetings call made here is ``get_person``. Rate
    limiting (429 backoff) is the connector's.
    """

    def __init__(self, chm: Any, available: bool) -> None:
        self.chm = chm
        self.available = available
        self._results: Dict[str, Tuple[str, str]] = {}

    def check(self, canonical_chm_id: str) -> Tuple[str, str]:
        """``(result, request_id)``; an ID shared by several aliases is looked up once."""
        if canonical_chm_id not in self._results:
            self._results[canonical_chm_id] = self._lookup(canonical_chm_id)
        return self._results[canonical_chm_id]

    def _lookup(self, canonical_chm_id: str) -> Tuple[str, str]:
        # Middleware-side correlation ID: it ties this log line to the audit row.
        request_id = uuid4().hex[:12]
        endpoint = f"GET api/v1/people/{canonical_chm_id}"
        if not self.available:
            self._log(endpoint, "not_attempted", 0, request_id, CANONICAL_UNVERIFIED)
            return CANONICAL_UNVERIFIED, request_id

        if self._results:
            time.sleep(CHM_MIN_REQUEST_INTERVAL_SECONDS)
        self.chm.last_get_person_status = "unknown"
        started = time.monotonic()
        try:
            person = self.chm.get_person(canonical_chm_id)
            status = self.chm.last_get_person_status
        except (requests.RequestException, ValueError) as exc:
            logger.error(f"[VAY SM] ChMeetings lookup raised for {endpoint}: {exc!r}")
            person, status = None, "failed"
        duration_ms = int((time.monotonic() - started) * 1000)

        if person and status == "ok":
            result = CANONICAL_EXISTS
        elif not person and status == "not_found":
            result = CANONICAL_NOT_FOUND
        else:
            result = CANONICAL_UNVERIFIED
        self._log(endpoint, status, duration_ms, request_id, result)
        return result, request_id

    @staticmethod
    def _log(endpoint: str, status: Any, duration_ms: int, request_id: str, result: str) -> None:
        log = logger.info if result == CANONICAL_EXISTS else logger.error
        log(
            f"[VAY SM] apply-aliases canonical check | scope=church | endpoint={endpoint} | "
            f"status={status} | duration_ms={duration_ms} | request_id={request_id} | "
            f"result={result}"
        )


def _skipped_row(
    stale_chm_id: str,
    canonical_chm_id: str,
    entry: Dict[str, str],
    result: str,
    request_id: str,
) -> Dict[str, Any]:
    outcome, cell, why = _CANONICAL_SKIPS[result]
    logger.error(
        f"[VAY SM] Alias {stale_chm_id} -> {canonical_chm_id} skipped: {why} "
        f"(request_id={request_id}). Nothing was written for this entry."
    )
    return {
        "Stale ChM ID": stale_chm_id,
        "Canonical ChM ID": canonical_chm_id,
        "Reason": entry.get("reason", ""),
        "Confirmed By": entry.get("confirmed_by", ""),
        "Canonical In ChMeetings": cell,
        "ChM Check Request ID": request_id,
        "Outcome": outcome,
        "Skipped Because": why,
    }


def _participant_rows(connector: Any, chm_id: str) -> List[Dict[str, Any]]:
    return _read(
        connector,
        "get_participants",
        "last_get_participants_status",
        f"participant chm_id={chm_id}",
        params={"chmeetings_id": chm_id},
    )


def _open_issues(connector: Any, participant_id: int) -> List[Dict[str, Any]]:
    """Every open validation issue for the participant, across all pages.

    GET /validation-issues returns 20 rows per page by default, so one call
    would report a participant with more open issues as fully reconciled.
    """
    issues: List[Dict[str, Any]] = []
    for page in range(1, _ISSUE_MAX_PAGES + 1):
        batch = _read(
            connector,
            "get_validation_issues",
            "last_get_validation_issues_status",
            f"open validation issues for participant_id={participant_id} (page {page})",
            params={
                "participant_id": participant_id,
                "status": VALIDATION_STATUS["OPEN"],
                "per_page": _ISSUE_PAGE_SIZE,
                "page": page,
            },
        )
        issues.extend(batch)
        if len(batch) < _ISSUE_PAGE_SIZE:
            return issues
    raise ReconcileReadError(
        f"WordPress read failed: more than {_ISSUE_MAX_PAGES * _ISSUE_PAGE_SIZE} open "
        f"validation issues for participant_id={participant_id}"
    )


def _state(connector: Any, participant_id: int) -> ReconcileState:
    return ReconcileState(
        rosters=_read(
            connector,
            "get_rosters",
            "last_get_rosters_status",
            f"rosters for participant_id={participant_id}",
            # Without all_team_orders the endpoint only returns rows whose
            # team_order IS NULL and would hide a roster staff gave an order.
            params={"participant_id": participant_id, "all_team_orders": 1},
        ),
        approvals=_read(
            connector,
            "get_approvals",
            "last_get_approvals_status",
            f"approvals for participant_id={participant_id}",
            params={"participant_id": participant_id},
        ),
        issues=_open_issues(connector, participant_id),
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


def _write(connector: Any, method: str, description: str, *args: Any) -> Any:
    """Run one WordPress write; a raised transient failure is a failed write.

    Connector writes that pre-read through a retried GET (``delete_roster``)
    raise ``tenacity.RetryError`` once the retries are spent. That must fail the
    one write, not abort the run: the remaining aliases still need processing
    and the audit file must be written.
    """
    try:
        return getattr(connector, method)(*args)
    except (RetryError, requests.RequestException) as exc:
        logger.error(f"[VAY SM] WordPress write failed ({description}): {exc!r}")
        return None


def _apply_state(
    connector: Any,
    stale: Dict[str, Any],
    state: ReconcileState,
    row: Dict[str, Any],
) -> bool:
    participant_id = stale["participant_id"]
    success = True
    failed_writes: List[str] = []

    # Tombstone the participant first. Every consumer keys off that one field,
    # so it is the write that makes the row inert; if it does not land, nothing
    # else is touched and the row stays whole for the rerun.
    participant_tombstoned = stale.get("approval_status") == APPROVAL_STATUS["MERGED"]
    if not participant_tombstoned:
        participant_tombstoned = _write(
            connector,
            "update_participant",
            f"tombstone participant {participant_id}",
            participant_id,
            {"approval_status": APPROVAL_STATUS["MERGED"]},
        ) is not None
        if not participant_tombstoned:
            logger.error(
                f"Failed to tombstone stale participant {participant_id}; its rosters, "
                "approvals and validation issues were left untouched. Rerun apply-aliases."
            )
            row.update(
                {
                    "Rosters Deleted": 0,
                    "Participant Tombstoned": False,
                    "Approvals Tombstoned": 0,
                    "Validation Issues Resolved": 0,
                    "Failed Writes": f"participant {participant_id}",
                }
            )
            return False

    deleted = 0
    for roster in state.rosters:
        roster_id = roster.get("roster_id")
        if _write(connector, "delete_roster", f"delete roster {roster_id}", roster_id):
            deleted += 1
        else:
            success = False
            failed_writes.append(f"roster {roster_id}")
            logger.error(f"Failed to delete stale roster {roster_id}")

    approvals_tombstoned = 0
    for approval in state.active_approvals:
        approval_id = approval.get("approval_id")
        if _write(
            connector,
            "update_approval",
            f"tombstone approval {approval_id}",
            approval_id,
            {"approval_status": APPROVAL_STATUS["MERGED"]},
        ):
            approvals_tombstoned += 1
        else:
            success = False
            failed_writes.append(f"approval {approval_id}")
            logger.error(f"Failed to tombstone stale approval {approval_id}")

    issues_resolved = 0
    resolved_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for issue in state.issues:
        issue_id = issue.get("issue_id")
        if _write(
            connector,
            "update_validation_issue",
            f"resolve validation issue {issue_id}",
            issue_id,
            {"status": VALIDATION_STATUS["RESOLVED"], "resolved_at": resolved_at},
        ):
            issues_resolved += 1
        else:
            success = False
            failed_writes.append(f"validation issue {issue_id}")
            logger.error(f"Failed to resolve stale validation issue {issue_id}")

    row.update(
        {
            "Rosters Deleted": deleted,
            "Participant Tombstoned": participant_tombstoned,
            "Approvals Tombstoned": approvals_tombstoned,
            "Validation Issues Resolved": issues_resolved,
            "Failed Writes": ", ".join(failed_writes),
        }
    )
    return success


def _report_surviving_mismatch(
    connector: Any,
    stale_chm_id: str,
    canonical_chm_id: str,
    state: ReconcileState,
    row: Dict[str, Any],
) -> None:
    """Keep reporting a lost pastor decision after the stale row is tombstoned.

    Once the stale participant reads `merged` its old status is gone, but its
    approval row keeps `approval_date`. That date is set for a denial as well as
    an approval, so the result is "possible", not "yes": the operator checks the
    canonical participant, which is the one that needs the pastor's decision.
    """
    decision_dates = sorted(
        str(approval.get("approval_date"))
        for approval in state.approvals
        if approval.get("approval_date")
    )
    if not decision_dates:
        # Nothing was lost, so the canonical row is not needed: residual work
        # on a tombstone must not depend on an extra read.
        row["Approval Mismatch"] = "no"
        return
    try:
        canonical_rows = _participant_rows(connector, canonical_chm_id)
    except ReconcileReadError as exc:
        # Reporting only. A failed lookup must not block finishing the tombstone.
        logger.warning(f"[VAY SM] {exc}; approval mismatch reported as possible")
        row.update(
            {
                "Canonical Approval Status": "unknown (read failed)",
                "Stale Pastor Decision Date": decision_dates[-1],
                "Approval Mismatch": "possible",
            }
        )
        return
    canonical_status = canonical_rows[0].get("approval_status", "") if canonical_rows else ""
    row.update(
        {
            "Canonical WP Participant ID": (
                canonical_rows[0].get("participant_id", "") if canonical_rows else ""
            ),
            "Canonical Approval Status": canonical_status,
            "Stale Pastor Decision Date": decision_dates[-1],
        }
    )
    possible = canonical_status != APPROVAL_STATUS["APPROVED"]
    row["Approval Mismatch"] = "possible" if possible else "no"
    if possible:
        logger.warning(
            f"[VAY SM] Possible approval mismatch for merged chm_id={stale_chm_id}: its "
            f"approval row records a pastor decision on {decision_dates[-1]} and canonical "
            f"chm_id={canonical_chm_id} is '{canonical_status or 'not in WordPress'}', not approved"
        )


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
        _report_surviving_mismatch(connector, stale_chm_id, canonical_chm_id, state, row)
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
    if canonical.get("approval_status") == APPROVAL_STATUS["MERGED"]:
        # The "canonical" row is itself a tombstone: the alias points at a
        # retired identity (typically an executed alias whose direction was
        # later reversed in the map). Tombstoning the stale row too would leave
        # the athlete with no active row at all, so nothing is written.
        row.update(
            {
                "Canonical WP Participant ID": canonical.get("participant_id", ""),
                "Canonical Approval Status": canonical.get("approval_status", ""),
                "Outcome": "canonical_is_merged",
            }
        )
        logger.error(
            f"[VAY SM] Alias {stale_chm_id} -> {canonical_chm_id} not applied: the canonical "
            f"WordPress participant {canonical.get('participant_id')} is itself 'merged'. "
            "Nothing was written. See docs/USAGE.md, 'Reversing an alias'."
        )
        return row

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


def _write_audit(rows: List[Dict[str, Any]]) -> Optional[Path]:
    """Write this run's audit workbook; earlier runs' files are never touched."""
    audit_file = _audit_path()
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_excel(audit_file, index=False)
        logger.info(f"Alias reconciliation audit written to {audit_file}")
        return audit_file
    except OSError as exc:
        logger.error(f"[VAY SM] Could not write alias reconciliation audit {audit_file}: {exc}")
        return None


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
    try:
        with WordPressConnector() as connector, ChMeetingsConnector() as chm:
            chm_available = bool(chm.authenticate())
            if not chm_available:
                logger.error(
                    "[VAY SM] apply-aliases could not authenticate with ChMeetings, so no "
                    "canonical ID can be verified. No alias will be applied in this run."
                )
            verifier = _CanonicalVerifier(chm, chm_available)
            for stale_chm_id, entry in aliases.items():
                # Report-only and --execute alike: an entry is not even reported
                # as "would reconcile" until its canonical ID is known to be live.
                canonical_chm_id = resolve_chm_id(stale_chm_id, aliases)
                result, request_id = verifier.check(canonical_chm_id)
                if result != CANONICAL_EXISTS:
                    rows.append(
                        _skipped_row(stale_chm_id, canonical_chm_id, entry, result, request_id)
                    )
                    continue
                try:
                    row = _reconcile_one(connector, stale_chm_id, entry, aliases, execute)
                    row["Canonical In ChMeetings"] = "yes"
                    row["ChM Check Request ID"] = request_id
                    rows.append(row)
                except ReconcileReadError as exc:
                    logger.error(f"[VAY SM] {exc}")
                    rows.append({"Stale ChM ID": stale_chm_id, "Outcome": "error_read_failed"})
                except (RetryError, requests.RequestException) as exc:
                    # Backstop: every write already goes through _write().
                    logger.error(
                        f"[VAY SM] WordPress call failed for stale chm_id={stale_chm_id}: {exc!r}"
                    )
                    rows.append({"Stale ChM ID": stale_chm_id, "Outcome": "error_write_failed"})
    finally:
        # Whatever happened above, the operator gets a record of the aliases
        # that were already processed in this run.
        _write_audit(rows)

    outcomes = Counter(row["Outcome"] for row in rows)
    logger.info(f"Alias reconciliation complete: {dict(outcomes)}")
    return not any(
        outcome.startswith("error") or outcome in _FAILING_OUTCOMES for outcome in outcomes
    )
