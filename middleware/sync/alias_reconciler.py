# Begin of sync/alias_reconciler.py
"""Retire duplicate WordPress rows for stale ChMeetings IDs (Issue #310).

Phase 2 of docs/CANONICAL_IDENTITY_RFC.md §4.3 ("retire, don't delete"): Track
A3 of epic #307. The person-alias map (#308) already stops a stale ChMeetings
ID from being re-created going forward, resolving it to its canonical ID at
the front door of sync. But the WordPress row created *before* the alias was
known still exists — this reconciler cleans that up:

1. Delete the stale row's roster entries (removes it from scoresheets/exports).
2. Tombstone the stale participant and its approval record as ``merged``
   (safe per #309's audit — every consumer already tolerates the value).
3. Resolve the stale row's open validation issues.
4. Warn (never auto-copy) when the stale row was pastor-approved but the
   canonical row is not — an identity change invalidates approval.
5. Print the stale badge filename for manual deletion, and remind the
   operator to regenerate badges/scoresheets.

Deliberately out of scope, per the RFC:
- No ChMeetings-side writes (§6 — "no ChMeetings-side writes beyond what
  already exists"; whether apply-aliases should also clean ChMeetings Team
  groups is an open §8 decision, not resolved here).
- No edits to the alias map itself (guardrail G3 — a human decides who is
  who, never code).

Report-only by default, mirroring ``audit-team-groups --remove-orphans``:
call :func:`apply_aliases` for a dry-run preview, ``apply_aliases(execute=True)``
to act.

Idempotent, but deliberately not naively so: a stale row is skipped as
"already merged" only when its tombstone is *complete* — no leftover rosters,
no non-merged approvals, no open validation issues. A run that tombstones the
participant and then fails on the approval write would otherwise be skipped
forever on every later run, leaving a live approval token on a retired
duplicate while the command reported success. Residual work is retried
instead. A genuinely complete row is still a true no-op.
"""
import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from config import APPROVAL_STATUS, DATA_DIR, VALIDATION_STATUS
from sync.person_aliases import PersonAliasError, load_person_aliases, resolve_chm_id
from wordpress.frontend_connector import WordPressConnector

ALIAS_RECONCILIATION_AUDIT_FILE = "alias_reconciliation_audit.xlsx"


def _write_audit_file(rows: List[Dict[str, Any]]) -> None:
    """Write the reconciliation audit trail to the middleware data directory."""
    output_dir = DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_file = output_dir / ALIAS_RECONCILIATION_AUDIT_FILE
    try:
        pd.DataFrame(rows).to_excel(audit_file, index=False)
        logger.info(f"Audit file written: {audit_file}")
    except PermissionError:
        logger.warning(
            f"Could not write audit file - {audit_file} is open in another program. "
            "Close the file and re-run to get an updated audit log. "
            "API calls already made above are unaffected."
        )


def _residual_tombstone_work(
    wp_connector: Any, participant_id: Any
) -> Dict[str, int]:
    """Return the tombstone work still outstanding on an already-merged stale row.

    A previous ``--execute`` run can tombstone the participant and then fail on
    the approval or validation-issue writes. Because the participant's own status
    is already ``merged``, a naive "already merged, skip" check would never retry
    that leftover work — silently leaving a live approval token on a retired
    duplicate while reporting success. This is what makes the skip safe.
    """
    leftovers: Dict[str, int] = {}

    leftover_rosters = wp_connector.get_rosters(params={"participant_id": participant_id}) or []
    if leftover_rosters:
        leftovers["rosters"] = len(leftover_rosters)

    leftover_approvals = [
        approval
        for approval in (wp_connector.get_approvals(params={"participant_id": participant_id}) or [])
        if approval.get("approval_status") != APPROVAL_STATUS["MERGED"]
    ]
    if leftover_approvals:
        leftovers["approvals"] = len(leftover_approvals)

    leftover_issues = wp_connector.get_validation_issues(
        params={"participant_id": participant_id, "status": VALIDATION_STATUS["OPEN"]}
    ) or []
    if leftover_issues:
        leftovers["validation_issues"] = len(leftover_issues)

    return leftovers


def _stale_badge_filename(stale: Dict[str, Any], stale_chm_id: str) -> Optional[str]:
    """Best-effort stale badge filename for the operator's manual cleanup list.

    Returns None (with a warning) rather than raising when BADGE_FILENAME_SALT
    isn't configured — a missing badge salt must not abort reconciliation.
    """
    try:
        from badges.generator import BadgeGenerator

        generator = BadgeGenerator()
    except ValueError as exc:
        logger.warning(
            f"[VAY SM] Could not compute stale badge filename for chm_id={stale_chm_id}: {exc}"
        )
        return None
    return generator.filename_for({
        "chmeetings_id": stale_chm_id,
        "church_code": stale.get("church_code", ""),
    })


def apply_aliases(execute: bool = False) -> bool:
    """Reconcile WordPress rows for every stale ID in the person alias map.

    Args:
        execute: If False (default), report only — reads and logs what would
            happen, makes zero write calls. If True, actually delete roster
            rows, tombstone the participant/approval rows as 'merged', and
            resolve open validation issues.

    Returns:
        bool: False only on a hard failure (cyclic alias map, or an execute-mode
        reconciliation that didn't fully complete for at least one entry).
        Missing canonical rows and approval mismatches are reported but do not
        fail the run — they need operator follow-up, not a non-zero exit code
        that hides which entries actually succeeded.
    """
    logger.info(f"Starting alias reconciliation (execute={execute})...")
    if execute:
        logger.warning(
            "EXECUTE MODE: stale rows will be tombstoned in WordPress. "
            "This deletes roster rows and cannot be undone from the UI."
        )

    try:
        aliases = load_person_aliases()
    except PersonAliasError as exc:
        logger.error(f"[VAY SM] Refusing to run apply-aliases: {exc}")
        return False

    if not aliases:
        logger.info("Person alias map is empty; nothing to reconcile.")
        return True

    audit_rows: List[Dict[str, Any]] = []
    already_reconciled = 0
    missing_stale_row = 0
    missing_canonical_row = 0
    reconciled = 0
    approval_mismatches = 0
    errors = 0

    with WordPressConnector() as wp_connector:
        for stale_chm_id, entry in aliases.items():
            # Resolve to the *terminal* canonical ID, not this entry's immediate
            # target. For a chain A -> B -> C, sync (#308) resolves A to C, so the
            # reconciler must reconcile A against C too — checking A against B would
            # verify (and compare approvals against) a row that is itself about to be
            # tombstoned, and would wrongly block on "run sync first" whenever the
            # intermediate B has no WordPress row.
            canonical_chm_id = resolve_chm_id(stale_chm_id, aliases)
            row: Dict[str, Any] = {
                "Stale ChM ID": stale_chm_id,
                "Canonical ChM ID": canonical_chm_id,
                "Direct Alias Target": entry["canonical_chm_id"],
                "Reason": entry.get("reason", ""),
                "Confirmed By": entry.get("confirmed_by", ""),
            }

            stale_matches = wp_connector.get_participants(params={"chmeetings_id": stale_chm_id})
            if not stale_matches:
                missing_stale_row += 1
                row["Outcome"] = "no_wp_row"
                logger.info(
                    f"[VAY SM] No WordPress row for stale chm_id={stale_chm_id}; nothing to reconcile."
                )
                audit_rows.append(row)
                continue

            stale = stale_matches[0]
            row["Stale WP Participant ID"] = stale.get("participant_id", "")
            row["Stale Name"] = f"{stale.get('first_name', '')} {stale.get('last_name', '')}".strip()
            row["Stale Approval Status"] = stale.get("approval_status", "")

            if stale.get("approval_status") == APPROVAL_STATUS["MERGED"]:
                residual = _residual_tombstone_work(wp_connector, stale["participant_id"])
                if not residual:
                    already_reconciled += 1
                    row["Outcome"] = "already_merged"
                    logger.info(
                        f"[VAY SM] chm_id={stale_chm_id} (WP participant {stale.get('participant_id')}) "
                        "is already merged; skipping."
                    )
                    audit_rows.append(row)
                    continue

                # Tombstoned, but a previous run left work behind. Fall through and
                # retry it rather than reporting a clean skip over a live token.
                row["Residual Work"] = ", ".join(f"{k}={v}" for k, v in sorted(residual.items()))
                logger.warning(
                    f"[VAY SM] chm_id={stale_chm_id} (WP participant {stale.get('participant_id')}) "
                    f"is tombstoned but a previous run left work incomplete ({row['Residual Work']}). "
                    "Retrying the outstanding tombstone work."
                )

            canonical_matches = wp_connector.get_participants(params={"chmeetings_id": canonical_chm_id})
            if not canonical_matches:
                missing_canonical_row += 1
                row["Outcome"] = "canonical_missing_run_sync_first"
                logger.warning(
                    f"[VAY SM] Canonical chm_id={canonical_chm_id} has no WordPress row yet "
                    f"(aliased from stale chm_id={stale_chm_id}). Run sync first, then re-run apply-aliases."
                )
                audit_rows.append(row)
                continue

            canonical = canonical_matches[0]
            row["Canonical WP Participant ID"] = canonical.get("participant_id", "")
            row["Canonical Approval Status"] = canonical.get("approval_status", "")

            stale_was_approved = stale.get("approval_status") == APPROVAL_STATUS["APPROVED"]
            canonical_is_approved = canonical.get("approval_status") == APPROVAL_STATUS["APPROVED"]
            if stale_was_approved and not canonical_is_approved:
                approval_mismatches += 1
                row["Approval Mismatch"] = "yes"
                logger.warning(
                    f"[VAY SM] APPROVAL MISMATCH: stale chm_id={stale_chm_id} "
                    f"(WP {stale.get('participant_id')}) was pastor-approved, but canonical "
                    f"chm_id={canonical_chm_id} (WP {canonical.get('participant_id')}) is not. "
                    "NOT auto-copying the approval — an identity change invalidates approval. "
                    "Have the pastor re-approve the canonical participant if warranted."
                )
            else:
                row["Approval Mismatch"] = "no"

            stale_rosters = wp_connector.get_rosters(params={"participant_id": stale["participant_id"]})
            row["Stale Roster Rows"] = len(stale_rosters)

            badge_filename = _stale_badge_filename(stale, stale_chm_id)
            row["Stale Badge Filename"] = badge_filename or ""

            if not execute:
                row["Outcome"] = "would_reconcile"
                audit_rows.append(row)
                continue

            # --- Execute: delete rosters, tombstone, resolve validation issues ---
            rosters_deleted = 0
            roster_delete_failed = False
            for roster in stale_rosters:
                if wp_connector.delete_roster(roster["roster_id"]):
                    rosters_deleted += 1
                else:
                    roster_delete_failed = True
                    logger.error(
                        f"[VAY SM] Failed to delete roster {roster.get('roster_id')} "
                        f"for stale participant {stale.get('participant_id')} (chm_id={stale_chm_id})."
                    )

            participant_result = wp_connector.update_participant(
                stale["participant_id"], {"approval_status": APPROVAL_STATUS["MERGED"]}
            )
            participant_tombstoned = participant_result is not None

            stale_approvals = wp_connector.get_approvals(params={"participant_id": stale["participant_id"]})
            approvals_tombstoned = 0
            approval_tombstone_failed = False
            for approval in stale_approvals:
                if wp_connector.update_approval(
                    approval["approval_id"], {"approval_status": APPROVAL_STATUS["MERGED"]}
                ):
                    approvals_tombstoned += 1
                else:
                    approval_tombstone_failed = True
                    logger.error(
                        f"[VAY SM] Failed to tombstone approval {approval.get('approval_id')} "
                        f"for stale participant {stale.get('participant_id')} (chm_id={stale_chm_id}). "
                        "A stale approval token may still be active."
                    )

            open_issues = wp_connector.get_validation_issues(
                params={"participant_id": stale["participant_id"], "status": VALIDATION_STATUS["OPEN"]}
            )
            issues_resolved = 0
            validation_resolve_failed = False
            for issue in open_issues:
                if wp_connector.update_validation_issue(
                    issue["issue_id"],
                    {
                        "status": VALIDATION_STATUS["RESOLVED"],
                        "resolved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                ):
                    issues_resolved += 1
                else:
                    validation_resolve_failed = True
                    logger.error(
                        f"[VAY SM] Failed to resolve validation issue {issue.get('issue_id')} "
                        f"for stale participant {stale.get('participant_id')} (chm_id={stale_chm_id})."
                    )

            row["Rosters Deleted"] = rosters_deleted
            row["Participant Tombstoned"] = participant_tombstoned
            row["Approvals Tombstoned"] = approvals_tombstoned
            row["Validation Issues Resolved"] = issues_resolved

            fully_reconciled = (
                participant_tombstoned
                and not roster_delete_failed
                and not approval_tombstone_failed
                and not validation_resolve_failed
            )
            if fully_reconciled:
                reconciled += 1
                row["Outcome"] = "reconciled"
                logger.info(
                    f"[VAY SM] Reconciled stale chm_id={stale_chm_id} (WP {stale.get('participant_id')}) "
                    f"-> canonical chm_id={canonical_chm_id}: deleted {rosters_deleted} roster row(s), "
                    f"tombstoned participant + {approvals_tombstoned} approval(s), "
                    f"resolved {issues_resolved} validation issue(s)."
                )
                if badge_filename:
                    logger.info(
                        f"[VAY SM] Stale badge to remove manually: {badge_filename} "
                        f"(chm_id={stale_chm_id}). Regenerate badges/scoresheets after this run."
                    )
            else:
                errors += 1
                row["Outcome"] = "error"
                logger.error(
                    f"[VAY SM] Reconciliation incomplete for stale chm_id={stale_chm_id} "
                    f"(WP {stale.get('participant_id')}): "
                    f"participant_tombstoned={participant_tombstoned}, "
                    f"roster_delete_failed={roster_delete_failed}, "
                    f"approval_tombstone_failed={approval_tombstone_failed}, "
                    f"validation_resolve_failed={validation_resolve_failed}."
                )

            audit_rows.append(row)

    _write_audit_file(audit_rows)

    summary = (
        f"Alias reconciliation complete: {len(aliases)} alias entry(ies), "
        f"{missing_stale_row} with no WP row, {already_reconciled} already merged, "
        f"{missing_canonical_row} blocked on a missing canonical row, "
        f"{approval_mismatches} approval mismatch(es) flagged."
    )
    if execute:
        summary += f" Reconciled: {reconciled}, errors: {errors}."
        if reconciled:
            summary += " Regenerate badges and scoresheets to drop the retired duplicates."
    logger.info(summary)

    return errors == 0

# End of sync/alias_reconciler.py
