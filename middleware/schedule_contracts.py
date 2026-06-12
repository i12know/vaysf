"""
schedule_contracts.py — fail-fast contract validation for the scheduling
pipeline's JSON bridge files (Issue #161).

Validates:
  - schedule_input.json  (written by export-church-teams, read by solve-schedule)
  - schedule_output.json (written by solve-schedule, read by produce-schedule)

Design rules (per #161 review):
  - Validation is read-only.  Valid inputs are returned to the caller
    untouched, so a validated solve produces identical assignments, status,
    and unscheduled lists to an unvalidated one (see the behavioral
    equivalence test in tests/test_schedule_contracts.py).
  - Numeric fields are STRICT: numeric strings and booleans are rejected,
    never coerced.
  - The models cover the full documented schema (docs/SCHEDULING.md §Step 2
    and §Step 3).  Unknown fields are still accepted — the schema grows every
    season — but produce a deduplicated WARNING, except inside the reserved
    operator-annotation namespace: any field starting with ``x_`` or named
    ``operator_notes``.
  - Errors are collected, not first-fail: one run reports every violation,
    each with the offending game_id / resource_id for context.
  - Conditions the solver already handles gracefully (e.g. a resource_type
    with zero resources → unscheduled games, exit 1) stay WARNINGS so the
    documented exit-code semantics are unchanged.
  - team_conflicts endpoints are intentionally NOT required to appear in
    games: planning-only edges (an event with no Layer-2 games yet) are a
    legitimate, documented state with their own ``PlanningOnly`` status in
    the conflict audit.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")

_OUTPUT_STATUSES = {"OPTIMAL", "FEASIBLE", "PARTIAL", "INFEASIBLE", "UNKNOWN"}
_AUDIT_STATUSES = {
    "SeparatedInSchedule", "ConflictRemains", "PlanningOnly", "IncompleteSchedule",
}

# Operator-annotation namespace: never warned as unknown.
_ANNOTATION_FIELD = "operator_notes"
_ANNOTATION_PREFIX = "x_"

_KNOWN_INPUT_TOP_LEVEL = {
    "games", "resources", "playoff_slots", "gym_modes", "gym_allocation",
    "team_conflicts", "precedence", "day_order", "generated_at",
    "gym_court_scenario", "game_count", "resource_count",
    "pod_unprotected_entries", "pod_validation_reconciliation",
}
_KNOWN_OUTPUT_TOP_LEVEL = {
    "solved_at", "status", "solver_wall_seconds", "assignments", "unscheduled",
    "pool_results", "conflict_audit_summary", "conflict_audit",
    "pod_unprotected_entries", "pod_validation_reconciliation",
}


class ScheduleContractError(ValueError):
    """Raised when a scheduling JSON file violates its contract.

    Carries the full list of human-readable violation messages in `.errors`
    so CLI handlers can log each one on its own line.
    """

    def __init__(self, file_label: str, errors: list[str]) -> None:
        self.file_label = file_label
        self.errors = list(errors)
        lines = "\n".join(f"  - {e}" for e in self.errors)
        super().__init__(
            f"{file_label} failed contract validation "
            f"with {len(self.errors)} error(s):\n{lines}"
        )


# ---------------------------------------------------------------------------
# Item models — full documented schema, strict numerics, extras allowed
# ---------------------------------------------------------------------------

class _GameContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    game_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    duration_minutes: float = Field(gt=0, strict=True)
    resource_type: str = Field(min_length=1)
    stage: Optional[str] = None
    pool_id: Optional[str] = None
    round: Optional[int] = Field(default=None, strict=True)
    team_a_id: Optional[str] = None
    team_b_id: Optional[str] = None
    team_c_id: Optional[str] = None
    team_ids: Optional[list[str]] = None
    team_a_label: Optional[str] = None
    team_b_label: Optional[str] = None
    team_c_label: Optional[str] = None
    earliest_slot: Optional[str] = None
    latest_slot: Optional[str] = None
    division_id: Optional[str] = None
    division_entry_count: Optional[int] = Field(default=None, ge=0, strict=True)
    solver_pool: Optional[str] = None
    seed: Optional[int] = Field(default=None, ge=0, strict=True)


class _ResourceContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource_id: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    day: str = Field(min_length=1)
    open_time: str
    close_time: str
    slot_minutes: int = Field(gt=0, strict=True)
    label: Optional[str] = None
    exclusive_group: Optional[str] = None
    solver_pool: Optional[str] = None

    @field_validator("open_time", "close_time")
    @classmethod
    def _valid_time(cls, value: str) -> str:
        if not _TIME_RE.match(value or ""):
            raise ValueError("must be 'HH:MM'")
        hours, minutes = value.split(":")
        if int(hours) >= 24:
            raise ValueError("hours must be < 24")
        if int(minutes) >= 60:
            raise ValueError("minutes must be < 60")
        return value


class _PlayoffSlotContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    game_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    slot: str = Field(min_length=1)
    event: Optional[str] = None
    stage: Optional[str] = None
    resource_type: Optional[str] = None
    slot_minutes: Optional[int] = Field(default=None, gt=0, strict=True)


class _PrecedenceContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    before_game_id: str = Field(min_length=1)
    after_game_id: str = Field(min_length=1)
    # The solver coerces 0/None to 1, so a declared 0 would be silently
    # rewritten — require >= 1 to keep declarations honest.
    min_gap_slots: Optional[int] = Field(default=None, ge=1, strict=True)


class _TeamConflictContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    team_a_id: str = Field(min_length=1)
    team_b_id: str = Field(min_length=1)
    event_a: Optional[str] = None
    event_b: Optional[str] = None
    team_a_label: Optional[str] = None
    team_b_label: Optional[str] = None
    shared_count: Optional[int] = Field(default=None, ge=0, strict=True)
    primary_overlap_count: Optional[int] = Field(default=None, ge=0, strict=True)
    secondary_only_count: Optional[int] = Field(default=None, ge=0, strict=True)
    shared_participant_ids: Optional[list[str]] = None
    shared_participant_names: Optional[list[str]] = None


class _AssignmentContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    game_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    slot: str = Field(min_length=1)
    # Merged playoff rows are full playoff_slot dicts, so they carry these.
    event: Optional[str] = None
    stage: Optional[str] = None
    resource_type: Optional[str] = None
    slot_minutes: Optional[int] = Field(default=None, gt=0, strict=True)


class _PoolResultContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource_type: str = Field(min_length=1)
    status: str
    solver_wall_seconds: Optional[float] = Field(default=None, ge=0, strict=True)
    assignments: Optional[list[dict[str, Any]]] = None
    unscheduled: Optional[list[str]] = None
    # Per-pool metrics are None when the pool did not solve.
    latest_slot_index: Optional[int] = Field(default=None, ge=0, strict=True)
    max_games_per_day: Optional[int] = Field(default=None, ge=0, strict=True)
    volleyball_adjacent_switches: Optional[int] = Field(default=None, ge=0, strict=True)
    cross_sport_same_slot_conflicts: Optional[int] = Field(default=None, ge=0, strict=True)
    cross_sport_primary_penalty: Optional[int] = Field(default=None, ge=0, strict=True)
    cross_sport_secondary_penalty: Optional[int] = Field(default=None, ge=0, strict=True)
    diagnostics: Optional[list[dict[str, Any]]] = None

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str) -> str:
        if value not in _OUTPUT_STATUSES:
            raise ValueError(f"must be one of {sorted(_OUTPUT_STATUSES)}")
        return value


class _ConflictAuditRowContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    team_a_label: str
    team_b_label: str
    event_a: Optional[str] = None
    event_b: Optional[str] = None
    status: str
    shared_count: Optional[int] = Field(default=None, ge=0, strict=True)
    primary_overlap_count: Optional[int] = Field(default=None, ge=0, strict=True)
    secondary_only_count: Optional[int] = Field(default=None, ge=0, strict=True)
    overlap_count: Optional[int] = Field(default=None, ge=0, strict=True)
    scheduled_team_a_games: Optional[int] = Field(default=None, ge=0, strict=True)
    scheduled_team_b_games: Optional[int] = Field(default=None, ge=0, strict=True)
    shared_participant_names: Optional[str] = None
    overlap_game_pairs: Optional[str] = None
    validation_issue_status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str) -> str:
        if value not in _AUDIT_STATUSES:
            raise ValueError(f"must be one of {sorted(_AUDIT_STATUSES)}")
        return value


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _format_pydantic_errors(
    exc: ValidationError, location: str, identity: str
) -> list[str]:
    """Flatten a pydantic ValidationError into one message per violation."""
    messages = []
    for err in exc.errors():
        field = ".".join(str(part) for part in err["loc"]) or "<item>"
        messages.append(f"{location}{identity}: {field} — {err['msg']}")
    return messages


def _is_annotation_field(name: str) -> bool:
    return name == _ANNOTATION_FIELD or name.startswith(_ANNOTATION_PREFIX)


def _validate_items(
    items: Any,
    model: type[BaseModel],
    section: str,
    id_field: str,
    errors: list[str],
    warnings: list[str],
    warned_unknown: set[tuple[str, str]],
) -> None:
    """Validate one top-level list section, collecting errors and
    deduplicated unknown-field warnings."""
    if items is None:
        return
    if not isinstance(items, list):
        errors.append(f"{section}: must be a list, got {type(items).__name__}")
        return
    known_fields = set(model.model_fields)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(
                f"{section}[{index}]: must be an object, got {type(item).__name__}"
            )
            continue
        identity = item.get(id_field)
        identity_note = f" ({id_field}={identity!r})" if identity else ""
        try:
            model.model_validate(item)
        except ValidationError as exc:
            errors.extend(
                _format_pydantic_errors(exc, f"{section}[{index}]", identity_note)
            )
        for field_name in item:
            if field_name in known_fields or _is_annotation_field(field_name):
                continue
            key = (section, field_name)
            if key not in warned_unknown:
                warned_unknown.add(key)
                warnings.append(
                    f"{section}: unknown field {field_name!r} (first seen at "
                    f"{section}[{index}]{identity_note}) — not part of the "
                    "documented schema; use 'operator_notes' or an 'x_' prefix "
                    "for operator annotations"
                )


def _warn_unknown_top_level(
    data: dict[str, Any],
    known: set[str],
    warnings: list[str],
) -> None:
    for key in data:
        if key not in known and not _is_annotation_field(key):
            warnings.append(
                f"top-level: unknown section {key!r} — not part of the "
                "documented schema"
            )


def _require_object(data: Any, file_label: str) -> None:
    if not isinstance(data, dict):
        raise ScheduleContractError(
            file_label,
            [f"top-level: must be a JSON object, got {type(data).__name__}"],
        )


def _parse_time_minutes(time_str: str) -> int:
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _solver_pool_key(item: dict[str, Any]) -> str:
    """Mirror of scheduler._solver_pool_key for cross-pool precedence checks."""
    return str(item.get("solver_pool") or item.get("resource_type") or "")


def _find_precedence_cycle(rules: list[dict[str, Any]]) -> Optional[list[str]]:
    """Return one cycle (as an ordered list of game_ids) in the precedence
    graph, or None.  Iterative DFS with white/grey/black coloring."""
    adjacency: dict[str, list[str]] = {}
    for rule in rules:
        before = str(rule.get("before_game_id") or "").strip()
        after = str(rule.get("after_game_id") or "").strip()
        if before and after:
            adjacency.setdefault(before, []).append(after)

    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in adjacency}
    parent: dict[str, str] = {}

    for root in adjacency:
        if color.get(root, WHITE) != WHITE:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        color[root] = GREY
        while stack:
            node, child_index = stack[-1]
            children = adjacency.get(node, [])
            if child_index < len(children):
                stack[-1] = (node, child_index + 1)
                child = children[child_index]
                state = color.get(child, WHITE)
                if state == GREY:
                    # Back edge — walk parents from `node` up to `child`.
                    cycle = [child, node]
                    cursor = node
                    while parent.get(cursor) and parent[cursor] != child:
                        cursor = parent[cursor]
                        cycle.insert(1, cursor)
                    return list(reversed(cycle))
                if state == WHITE:
                    color[child] = GREY
                    parent[child] = node
                    stack.append((child, 0))
            else:
                color[node] = BLACK
                stack.pop()
    return None


def _resource_capacity_slots(resource: dict[str, Any]) -> int:
    """How many whole slots fit in one resource's daily window."""
    try:
        open_min = _parse_time_minutes(resource["open_time"])
        close_min = _parse_time_minutes(resource["close_time"])
        slot_min = int(resource["slot_minutes"])
    except (KeyError, TypeError, ValueError):
        return 0
    if slot_min <= 0 or close_min <= open_min:
        return 0
    return (close_min - open_min) // slot_min


def _validate_gym_modes(gym_modes: Any, errors: list[str]) -> None:
    if gym_modes is None:
        return
    if not isinstance(gym_modes, dict):
        errors.append(
            f"gym_modes: must be an object, got {type(gym_modes).__name__}"
        )
        return
    for gym_name, modes in gym_modes.items():
        if not isinstance(modes, dict):
            errors.append(
                f"gym_modes[{gym_name!r}]: must be an object mapping "
                f"resource_type → count, got {type(modes).__name__}"
            )
            continue
        for resource_type, count in modes.items():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                errors.append(
                    f"gym_modes[{gym_name!r}][{resource_type!r}]: must be a "
                    f"non-negative integer, got {count!r}"
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_schedule_input(data: Any) -> list[str]:
    """Validate a parsed schedule_input.json document.

    Returns a list of WARNING messages (conditions the solver tolerates but an
    operator should know about).  Raises ScheduleContractError when the
    document cannot be solved correctly as written.
    """
    _require_object(data, "schedule_input.json")

    errors: list[str] = []
    warnings: list[str] = []
    warned_unknown: set[tuple[str, str]] = set()

    for key in ("games", "resources"):
        if key not in data:
            errors.append(f"top-level: missing required section {key!r}")
    _warn_unknown_top_level(data, _KNOWN_INPUT_TOP_LEVEL, warnings)

    games = data.get("games")
    resources = data.get("resources")
    _validate_items(
        games, _GameContract, "games", "game_id", errors, warnings, warned_unknown
    )
    _validate_items(
        resources, _ResourceContract, "resources", "resource_id",
        errors, warnings, warned_unknown,
    )
    _validate_items(
        data.get("playoff_slots"), _PlayoffSlotContract, "playoff_slots",
        "game_id", errors, warnings, warned_unknown,
    )
    _validate_items(
        data.get("precedence"), _PrecedenceContract, "precedence",
        "before_game_id", errors, warnings, warned_unknown,
    )
    _validate_items(
        data.get("team_conflicts"), _TeamConflictContract, "team_conflicts",
        "team_a_id", errors, warnings, warned_unknown,
    )
    _validate_gym_modes(data.get("gym_modes"), errors)
    gym_allocation = data.get("gym_allocation")
    if gym_allocation is not None and not isinstance(gym_allocation, dict):
        errors.append(
            f"gym_allocation: must be an object, got {type(gym_allocation).__name__}"
        )
    day_order = data.get("day_order")
    if day_order is not None and (
        not isinstance(day_order, list)
        or any(not isinstance(d, str) for d in day_order)
    ):
        errors.append("day_order: must be a list of day-label strings")

    games = games if isinstance(games, list) else []
    resources = resources if isinstance(resources, list) else []
    game_dicts = [g for g in games if isinstance(g, dict)]
    resource_dicts = [r for r in resources if isinstance(r, dict)]

    # Duplicate IDs make assignments ambiguous — always an error.
    seen_game_ids: set[str] = set()
    for game in game_dicts:
        gid = str(game.get("game_id") or "").strip()
        if gid and gid in seen_game_ids:
            errors.append(f"games: duplicate game_id {gid!r}")
        seen_game_ids.add(gid)
    seen_resource_ids: set[str] = set()
    for resource in resource_dicts:
        rid = str(resource.get("resource_id") or "").strip()
        if rid and rid in seen_resource_ids:
            errors.append(f"resources: duplicate resource_id {rid!r}")
        seen_resource_ids.add(rid)

    # Real clock windows: close_time must be after open_time.
    for index, resource in enumerate(resource_dicts):
        open_t, close_t = resource.get("open_time"), resource.get("close_time")
        if (
            isinstance(open_t, str) and isinstance(close_t, str)
            and _TIME_RE.match(open_t) and _TIME_RE.match(close_t)
            and _parse_time_minutes(close_t) <= _parse_time_minutes(open_t)
        ):
            errors.append(
                f"resources[{index}] (resource_id="
                f"{resource.get('resource_id')!r}): close_time {close_t!r} "
                f"must be after open_time {open_t!r}"
            )

    # Playoff reference check: every pinned slot must point at a known
    # resource.  (Slot-label validity within the window stays in
    # scheduler.validate_playoff_slots, which owns slot generation.)
    playoff_slots = data.get("playoff_slots")
    playoff_dicts = [
        p for p in (playoff_slots if isinstance(playoff_slots, list) else [])
        if isinstance(p, dict)
    ]
    for index, playoff_slot in enumerate(playoff_dicts):
        rid = str(playoff_slot.get("resource_id") or "").strip()
        if rid and rid not in seen_resource_ids:
            errors.append(
                f"playoff_slots[{index}] (game_id="
                f"{playoff_slot.get('game_id')!r}): references unknown "
                f"resource_id {rid!r}"
            )

    # Resource fit:
    #   - a resource_type with zero resources stays a WARNING — the solver
    #     reports those games as unscheduled and exits 1 (pinned behavior);
    #   - a game that cannot physically fit ANY resource of its own type is
    #     an ERROR — it would otherwise surface downstream as a mystery
    #     INFEASIBLE/unscheduled.
    # A game needs ceil(duration / slot_minutes) consecutive slots on a single
    # resource, which fits exactly when slots × slot_minutes >= duration —
    # duration does NOT need to divide slot_minutes evenly (C7).
    capacity_by_type: dict[str, float] = {}
    windows_by_type: dict[str, list[str]] = {}
    for resource in resource_dicts:
        rtype = str(resource.get("resource_type") or "").strip()
        slot_min = resource.get("slot_minutes")
        if (
            not rtype or isinstance(slot_min, bool)
            or not isinstance(slot_min, (int, float)) or slot_min <= 0
        ):
            continue
        slots = _resource_capacity_slots(resource)
        capacity_by_type[rtype] = max(
            capacity_by_type.get(rtype, 0), slots * slot_min
        )
        windows_by_type.setdefault(rtype, []).append(
            f"{resource.get('resource_id')}: {slots} × {slot_min:g}min"
        )

    types_with_resources = {
        str(r.get("resource_type") or "").strip() for r in resource_dicts
    }
    pools_with_resources = {_solver_pool_key(r) for r in resource_dicts}
    warned_missing_types: set[str] = set()
    warned_missing_pools: set[str] = set()
    for game in game_dicts:
        gid = str(game.get("game_id") or "").strip() or "<unknown>"
        rtype = str(game.get("resource_type") or "").strip()
        duration = game.get("duration_minutes")
        if (
            not rtype or isinstance(duration, bool)
            or not isinstance(duration, (int, float)) or duration <= 0
        ):
            continue  # field-level errors already recorded above
        if rtype not in types_with_resources:
            if rtype not in warned_missing_types:
                warned_missing_types.add(rtype)
                warnings.append(
                    f"games: resource_type {rtype!r} (e.g. game {gid!r}) has no "
                    "resources — those games will be reported as unscheduled"
                )
            continue
        pool_key = _solver_pool_key(game)
        if pool_key not in pools_with_resources:
            if pool_key not in warned_missing_pools:
                warned_missing_pools.add(pool_key)
                warnings.append(
                    f"games: solver pool {pool_key!r} (e.g. game {gid!r}) has "
                    "no resources — those games will be reported as unscheduled"
                )
            continue
        if capacity_by_type.get(rtype, 0) < duration:
            available = "; ".join(windows_by_type.get(rtype, [])) or "none"
            errors.append(
                f"games: game {gid!r} ({duration:g} min) cannot fit any "
                f"{rtype!r} resource — available windows: {available}"
            )

    # Precedence integrity.  Cycles are errors.  Rules that span solver pools
    # are also errors: the pool-decomposed solver silently drops them today
    # (scheduler routes a rule only when both games share a pool), and a
    # declared constraint that cannot be enforced must not be silently
    # ignored while producing a schedule.  Dangling references stay warnings.
    precedence = data.get("precedence")
    precedence_rules = [
        r for r in (precedence if isinstance(precedence, list) else [])
        if isinstance(r, dict)
    ]
    cycle = _find_precedence_cycle(precedence_rules)
    if cycle:
        path = " → ".join(cycle + cycle[:1])
        errors.append(
            f"precedence: rules form a cycle ({path}) — the schedule can "
            "never satisfy them"
        )

    resource_by_id = {
        str(r.get("resource_id") or "").strip(): r for r in resource_dicts
    }
    # Pinned games take the pool of their pinned resource, mirroring how
    # solve() registers them for precedence routing.
    pool_by_game_id: dict[str, str] = {}
    for game in game_dicts:
        gid = str(game.get("game_id") or "").strip()
        if gid:
            pool_by_game_id[gid] = _solver_pool_key(game)
    for playoff_slot in playoff_dicts:
        gid = str(playoff_slot.get("game_id") or "").strip()
        resource = resource_by_id.get(
            str(playoff_slot.get("resource_id") or "").strip()
        )
        if gid and resource is not None:
            pool_by_game_id[gid] = _solver_pool_key(resource)

    for rule in precedence_rules:
        before = str(rule.get("before_game_id") or "").strip()
        after = str(rule.get("after_game_id") or "").strip()
        sides_known = True
        for side, ref in (("before_game_id", before), ("after_game_id", after)):
            if ref and ref not in pool_by_game_id:
                sides_known = False
                warnings.append(
                    f"precedence: {side} {ref!r} matches no game or playoff "
                    "slot — this rule will be ignored"
                )
        if sides_known and before and after:
            pool_before = pool_by_game_id[before]
            pool_after = pool_by_game_id[after]
            if pool_before and pool_after and pool_before != pool_after:
                errors.append(
                    f"precedence: rule {before!r} → {after!r} spans solver "
                    f"pools {pool_before!r} and {pool_after!r} — the "
                    "pool-decomposed solver cannot enforce it"
                )

    # Conflict edges with real overlaps but no names render empty
    # Conflict-Audit rows — warn so the export-side bug gets noticed.
    # (Endpoints are deliberately not checked against games: planning-only
    # edges are valid — see module docstring.)
    team_conflicts = data.get("team_conflicts")
    for index, edge in enumerate(
        team_conflicts if isinstance(team_conflicts, list) else []
    ):
        if not isinstance(edge, dict):
            continue
        try:
            primary = int(edge.get("primary_overlap_count") or 0)
        except (TypeError, ValueError):
            continue
        names = edge.get("shared_participant_names")
        if primary > 0 and isinstance(names, list) and not names:
            warnings.append(
                f"team_conflicts[{index}] ({edge.get('team_a_id')!r} ↔ "
                f"{edge.get('team_b_id')!r}): primary_overlap_count={primary} "
                "but shared_participant_names is empty — Conflict-Audit will "
                "show this overlap without names"
            )

    if errors:
        raise ScheduleContractError("schedule_input.json", errors)
    return warnings


def validate_schedule_output(data: Any) -> list[str]:
    """Validate a schedule_output.json document (parsed file or the dict
    produced by solve() before it is written).

    Returns WARNING messages; raises ScheduleContractError when the document
    would render an incorrect or ambiguous timetable.
    """
    _require_object(data, "schedule_output.json")

    errors: list[str] = []
    warnings: list[str] = []
    warned_unknown: set[tuple[str, str]] = set()

    _warn_unknown_top_level(data, _KNOWN_OUTPUT_TOP_LEVEL, warnings)

    status = data.get("status")
    if not isinstance(status, str) or status not in _OUTPUT_STATUSES:
        errors.append(
            f"status: must be one of {sorted(_OUTPUT_STATUSES)}, got {status!r}"
        )

    assignments = data.get("assignments")
    if assignments is None:
        errors.append("assignments: required key is missing")
        assignments = []
    _validate_items(
        assignments, _AssignmentContract, "assignments", "game_id",
        errors, warnings, warned_unknown,
    )
    _validate_items(
        data.get("pool_results"), _PoolResultContract, "pool_results",
        "resource_type", errors, warnings, warned_unknown,
    )
    _validate_items(
        data.get("conflict_audit"), _ConflictAuditRowContract, "conflict_audit",
        "team_a_label", errors, warnings, warned_unknown,
    )

    unscheduled = data.get("unscheduled")
    if unscheduled is not None and (
        not isinstance(unscheduled, list)
        or any(not isinstance(g, str) for g in unscheduled)
    ):
        errors.append("unscheduled: must be a list of game_id strings")

    summary = data.get("conflict_audit_summary")
    if summary is not None and not isinstance(summary, dict):
        errors.append(
            f"conflict_audit_summary: must be an object, got "
            f"{type(summary).__name__}"
        )

    # An assignment list with duplicate game_ids or double-booked
    # (resource_id, slot) pairs would render a corrupt timetable.
    seen_games: set[str] = set()
    seen_occupancy: dict[tuple[str, str], str] = {}
    for item in assignments if isinstance(assignments, list) else []:
        if not isinstance(item, dict):
            continue
        gid = str(item.get("game_id") or "").strip()
        rid = str(item.get("resource_id") or "").strip()
        slot = str(item.get("slot") or "").strip()
        if gid:
            if gid in seen_games:
                errors.append(f"assignments: game {gid!r} is assigned more than once")
            seen_games.add(gid)
        if rid and slot:
            key = (rid, slot)
            other = seen_occupancy.get(key)
            if other is not None:
                errors.append(
                    f"assignments: {rid!r} at {slot!r} is double-booked "
                    f"({other!r} and {gid!r})"
                )
            seen_occupancy[key] = gid

    if errors:
        raise ScheduleContractError("schedule_output.json", errors)
    return warnings


def validate_output_against_input(
    schedule_output: dict[str, Any],
    schedule_input: dict[str, Any],
) -> list[str]:
    """Cross-file referential check before produce-schedule renders.

    Every assignment must reference a game (or pinned playoff slot) and a
    resource that exist in the schedule_input the output was solved from.
    Unscheduled IDs that match no input game are downgraded to warnings —
    they cannot corrupt the rendered timetable.
    """
    errors: list[str] = []
    warnings: list[str] = []

    games = schedule_input.get("games")
    playoff_slots = schedule_input.get("playoff_slots")
    resources = schedule_input.get("resources")
    known_game_ids = {
        str(g.get("game_id") or "").strip()
        for g in (games if isinstance(games, list) else [])
        if isinstance(g, dict)
    } | {
        str(p.get("game_id") or "").strip()
        for p in (playoff_slots if isinstance(playoff_slots, list) else [])
        if isinstance(p, dict)
    }
    known_resource_ids = {
        str(r.get("resource_id") or "").strip()
        for r in (resources if isinstance(resources, list) else [])
        if isinstance(r, dict)
    }

    assignments = schedule_output.get("assignments")
    for index, item in enumerate(
        assignments if isinstance(assignments, list) else []
    ):
        if not isinstance(item, dict):
            continue
        gid = str(item.get("game_id") or "").strip()
        rid = str(item.get("resource_id") or "").strip()
        if gid and gid not in known_game_ids:
            errors.append(
                f"assignments[{index}]: game_id {gid!r} does not exist in "
                "schedule_input.json — output and input are out of sync"
            )
        if rid and rid not in known_resource_ids:
            errors.append(
                f"assignments[{index}] (game_id={gid!r}): resource_id {rid!r} "
                "does not exist in schedule_input.json"
            )

    unscheduled = schedule_output.get("unscheduled")
    for gid in unscheduled if isinstance(unscheduled, list) else []:
        gid = str(gid or "").strip()
        if gid and gid not in known_game_ids:
            warnings.append(
                f"unscheduled: game_id {gid!r} does not exist in "
                "schedule_input.json"
            )

    if errors:
        raise ScheduleContractError("schedule_output.json vs schedule_input.json", errors)
    return warnings
