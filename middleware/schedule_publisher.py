"""Publish a generated schedule (schedule_input.json + schedule_output.json)
into WordPress's sf_schedules table by stable game_key (Issue #203).

Design rules (RFC docs/EVENT_DAY_RESULTS_WORKFLOW_RFC.md §7):
  - The generated schedule is diffed against the currently published
    WordPress schedule; nothing is written until --execute is passed.
  - A game whose current WordPress status is "protected" (reported, official,
    under_review) is never overwritten, even in --execute mode. If its
    source_hash still matches, the REST endpoint may carry it forward to the
    new schedule_version by updating only version/bookkeeping fields.
  - A game that disappears from the newly generated schedule is only ever
    marked cancelled (never deleted), and only when --force-cancel is passed.
  - A protected game disappearing from the newly generated schedule is a
    scheduler/game-key-drift bug, not a legitimate cancellation — it is
    reported separately (missing_completed) rather than silently folded into
    the ordinary cancellation bucket.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from scheduler import _game_team_ids

PROTECTED_GAME_STATUSES = {"reported", "official", "under_review"}
CANCELLABLE_GAME_STATUSES = {"scheduled", "in_progress"}

# Fields carried into the sf_schedules upsert payload, and included in the
# source_hash. game_key/schedule_version/game_status/source_hash/published_at
# are deliberately excluded — they are identity or bookkeeping, not "did the
# game itself change" content.
_HASHED_FIELDS = (
    "event", "stage", "pool_id", "round_number",
    "team_a_key", "team_a_label", "team_b_key", "team_b_label",
    "team_c_key", "team_c_label", "team_ids_json",
    "resource_id", "scheduled_slot", "scheduled_location",
)


def compute_source_hash(merged_game: dict[str, Any]) -> str:
    """SHA-256 hex digest over the content fields of one merged game record.

    Deterministic and field-order independent, so "did this game change" is a
    cheap string comparison against the value WordPress already has stored,
    instead of a field-by-field diff against its response shape.
    """
    subset = {field: merged_game.get(field) for field in _HASHED_FIELDS}
    canonical = json.dumps(subset, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _format_resource_label(resource: dict[str, Any]) -> str:
    """Return a public-friendly resource label from schedule_input metadata."""

    label = str(resource.get("label") or "").strip()
    if not label:
        return ""

    label = label.replace("-", " ")
    resource_type = str(resource.get("resource_type") or "").strip().casefold()
    if resource_type == "bc station" and label.casefold().startswith("court "):
        return "Station " + label.split(" ", 1)[1]

    return label


def _format_scheduled_location(resource: dict[str, Any]) -> str:
    """Return a venue/court label suitable for WordPress sf_schedules."""

    if not resource:
        return ""

    venue_name = str(resource.get("venue_name") or "").strip()
    resource_label = _format_resource_label(resource)

    if venue_name and resource_label:
        return f"{venue_name} - {resource_label}"
    return venue_name or resource_label or str(resource.get("resource_id") or "").strip()


def merge_schedule(
    schedule_input: dict[str, Any],
    schedule_output: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join schedule_output assignments against schedule_input games by game_id.

    Ordinary solver-produced assignment rows carry only game_id/resource_id/
    slot; every other field (team labels, pool, stage, ...) must come from
    the matching schedule_input.games[] record. Produces one sf_schedules-
    shaped upsert dict per assigned game.
    """
    game_meta = {
        str(game.get("game_id")): game
        for game in schedule_input.get("games", [])
        if isinstance(game, dict) and game.get("game_id")
    }
    resource_meta = {
        str(resource.get("resource_id")): resource
        for resource in schedule_input.get("resources", [])
        if isinstance(resource, dict) and resource.get("resource_id")
    }

    merged: list[dict[str, Any]] = []
    for assignment in schedule_output.get("assignments", []):
        if not isinstance(assignment, dict):
            continue
        game_id = str(assignment.get("game_id") or "").strip()
        if not game_id:
            continue
        game = game_meta.get(game_id, {})
        resource_id = str(assignment.get("resource_id") or "").strip()
        scheduled_location = (
            str(assignment.get("scheduled_location") or "").strip()
            or _format_scheduled_location(resource_meta.get(resource_id, {}))
        )

        merged_game: dict[str, Any] = {
            "game_key": game_id,
            "event": assignment.get("event") or game.get("event"),
            "stage": assignment.get("stage") or game.get("stage"),
            "pool_id": game.get("pool_id"),
            "round_number": game.get("round"),
            "team_a_key": assignment.get("team_a_id") or game.get("team_a_id"),
            "team_a_label": game.get("team_a_label"),
            "team_b_key": assignment.get("team_b_id") or game.get("team_b_id"),
            "team_b_label": game.get("team_b_label"),
            "team_c_key": game.get("team_c_id"),
            "team_c_label": game.get("team_c_label"),
            "team_ids_json": json.dumps(_game_team_ids({**game, **assignment})),
            "resource_id": resource_id,
            "scheduled_slot": assignment.get("slot"),
            "scheduled_location": scheduled_location,
            "game_status": "scheduled",
        }
        merged_game["source_hash"] = compute_source_hash(merged_game)
        merged.append(merged_game)

    return merged


def build_publish_diff(
    merged_games: list[dict[str, Any]],
    published_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Bucket merged games against the currently published WordPress schedule.

    Returns a dict with seven lists: new, changed, unchanged,
    protected_unchanged, cancelled_candidates, completed_conflicts,
    missing_completed.
    """
    published_by_key = {
        str(row.get("game_key")): row for row in published_rows if row.get("game_key")
    }
    merged_by_key = {game["game_key"]: game for game in merged_games}

    diff: dict[str, list[dict[str, Any]]] = {
        "new": [],
        "changed": [],
        "unchanged": [],
        "protected_unchanged": [],
        "cancelled_candidates": [],
        "completed_conflicts": [],
        "missing_completed": [],
    }

    for game_key, game in merged_by_key.items():
        published = published_by_key.get(game_key)
        if published is None:
            diff["new"].append(game)
            continue

        current_status = str(published.get("game_status") or "")
        protected = current_status in PROTECTED_GAME_STATUSES
        changed = published.get("source_hash") != game.get("source_hash")

        if protected:
            if changed:
                diff["completed_conflicts"].append(game)
            if not changed:
                diff["protected_unchanged"].append(game)
            continue

        if changed:
            diff["changed"].append(game)
        else:
            diff["unchanged"].append(game)

    for game_key, published in published_by_key.items():
        if game_key in merged_by_key:
            continue
        current_status = str(published.get("game_status") or "")
        if current_status in PROTECTED_GAME_STATUSES:
            diff["missing_completed"].append(published)
        elif current_status in CANCELLABLE_GAME_STATUSES:
            diff["cancelled_candidates"].append(published)
        # else: already cancelled — nothing to do.

    return diff


def format_publish_report(
    diff: dict[str, list[dict[str, Any]]],
    schedule_version: int,
    force_cancel: bool,
) -> list[str]:
    """Render the diff as plain log lines for console/dry-run output."""
    lines = [f"=== publish-schedule report (schedule_version would be {schedule_version}) ==="]
    lines.append(f"New games:              {len(diff['new'])}")
    lines.append(f"Changed future games:   {len(diff['changed'])}")
    cancel_note = "" if force_cancel else "   (pass --force-cancel with --execute to apply)"
    lines.append(f"Cancelled candidates:   {len(diff['cancelled_candidates'])}{cancel_note}")
    lines.append(f"Unchanged games:        {len(diff['unchanged'])}")
    lines.append(f"Protected unchanged:    {len(diff['protected_unchanged'])}   (carry forward version only)")
    conflict_note = "   (refused — would overwrite a completed match)" if diff["completed_conflicts"] else ""
    lines.append(f"Completed conflicts:    {len(diff['completed_conflicts'])}{conflict_note}")
    missing_note = "   (refused — completed game absent from new schedule; investigate)" if diff["missing_completed"] else ""
    lines.append(f"Missing completed:      {len(diff['missing_completed'])}{missing_note}")

    for label, key in (
        ("New games", "new"),
        ("Changed future games", "changed"),
        ("Cancelled candidates", "cancelled_candidates"),
        ("Completed conflicts", "completed_conflicts"),
        ("Missing completed", "missing_completed"),
    ):
        rows = diff[key]
        if not rows:
            continue
        lines.append(f"--- {label} ---")
        for row in rows:
            game_key = row.get("game_key", "?")
            event = row.get("event", "")
            resource_id = row.get("resource_id", "")
            slot = row.get("scheduled_slot", "")
            lines.append(f"  {game_key}  {event}  {resource_id}  {slot}")

    return lines


def run_publish_schedule(
    schedule_input_path: Path,
    schedule_output_path: Path,
    wp_connector: Any,
    dry_run: bool,
    force_cancel: bool = False,
    allow_partial: bool = False,
    audit_output_path: Optional[Path] = None,
) -> int:
    """Load, contract-validate, diff, and (if --execute) upsert a schedule.

    Returns a process exit code: 0 on success, 1 on any contract or I/O
    failure.
    """
    from schedule_contracts import (
        ScheduleContractError,
        validate_output_against_input,
        validate_schedule_input,
        validate_schedule_output,
    )

    try:
        schedule_input = json.loads(Path(schedule_input_path).read_text(encoding="utf-8"))
        schedule_output = json.loads(Path(schedule_output_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        logger.error(f"publish-schedule: required file not found — {exc.filename}")
        return 1
    except json.JSONDecodeError as exc:
        logger.error(f"publish-schedule: invalid JSON — {exc}")
        return 1

    try:
        for warning in validate_schedule_input(schedule_input):
            logger.warning(f"schedule_input contract: {warning}")
        for warning in validate_schedule_output(schedule_output):
            logger.warning(f"schedule_output contract: {warning}")
        for warning in validate_output_against_input(schedule_output, schedule_input):
            logger.warning(f"schedule_output contract: {warning}")
    except ScheduleContractError as exc:
        logger.error(
            f"publish-schedule: {exc.file_label} failed contract validation "
            f"with {len(exc.errors)} error(s):"
        )
        for violation in exc.errors:
            logger.error(f"  - {violation}")
        return 1

    output_status = str(schedule_output.get("status") or "")
    unscheduled = schedule_output.get("unscheduled") or []
    incomplete = (
        output_status not in {"OPTIMAL", "FEASIBLE"}
        or bool(unscheduled)
    )
    if incomplete and not allow_partial:
        logger.error(
            "publish-schedule: refusing to publish incomplete schedule_output.json "
            f"(status={output_status!r}, unscheduled={len(unscheduled)}). "
            "Rerun after a complete solve, or pass --allow-partial for an "
            "intentional emergency publish."
        )
        return 1

    merged_games = merge_schedule(schedule_input, schedule_output)
    try:
        published_rows = wp_connector.get_schedules()
    except Exception as exc:
        logger.error(f"publish-schedule: failed to read WordPress schedule: {exc}")
        return 1
    if published_rows is None:
        logger.error(
            "publish-schedule: could not read existing WordPress schedule; "
            "refusing to diff against an unknown published state."
        )
        return 1
    existing_versions = [
        int(row.get("schedule_version") or 0) for row in published_rows
    ]
    schedule_version = (max(existing_versions) if existing_versions else 0) + 1

    diff = build_publish_diff(merged_games, published_rows)
    for line in format_publish_report(diff, schedule_version, force_cancel):
        logger.info(("[DRY RUN] " if dry_run else "") + line)

    if audit_output_path:
        audit = {
            "schedule_version": schedule_version,
            "dry_run": dry_run,
            "force_cancel": force_cancel,
            "allow_partial": allow_partial,
            "diff": diff,
        }
        audit_output_path.parent.mkdir(parents=True, exist_ok=True)
        audit_output_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
        logger.info(f"Publish audit JSON written to: {audit_output_path.resolve()}")

    if dry_run:
        return 0

    upsert_games = (
        list(diff["new"])
        + list(diff["changed"])
        + list(diff["unchanged"])
        + list(diff["protected_unchanged"])
    )
    if force_cancel:
        for row in diff["cancelled_candidates"]:
            upsert_games.append({**row, "game_status": "cancelled"})

    if not upsert_games:
        logger.info("publish-schedule: nothing to upsert.")
        return 0

    response = wp_connector.upsert_schedules(
        games=upsert_games,
        schedule_version=schedule_version,
        force_cancel=force_cancel,
    )
    if response is None or not response.get("success"):
        logger.error("publish-schedule: upsert request failed.")
        return 1

    logger.info(
        f"publish-schedule: created={response.get('created_count')} "
        f"updated={response.get('updated_count')} "
        f"skipped={response.get('skipped_count')}"
    )

    if audit_output_path:
        audit_data = json.loads(audit_output_path.read_text(encoding="utf-8"))
        audit_data["upsert_response"] = response
        audit_output_path.write_text(json.dumps(audit_data, indent=2), encoding="utf-8")

    return 0
