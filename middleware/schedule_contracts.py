"""
schedule_contracts.py — fail-fast contract validation for the scheduling
pipeline's JSON bridge files (Issue #161).

Validates:
  - schedule_input.json  (written by export-church-teams, read by solve-schedule)
  - schedule_output.json (written by solve-schedule, read by produce-schedule)

Design rules:
  - Validation is read-only.  Valid inputs are returned to the caller untouched
    so solver behavior is byte-identical with or without this module.
  - Unknown / extra fields are allowed everywhere — the schema evolves each
    season and hand-edited inputs may carry operator annotations.
  - Errors are collected, not first-fail: one run reports every violation,
    each with the offending game_id / resource_id for context.
  - Conditions the solver already handles gracefully (e.g. a resource_type
    with zero resources → unscheduled games, exit 1) stay WARNINGS here so
    existing operator workflows and exit-code semantics are unchanged.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")

_OUTPUT_STATUSES = {"OPTIMAL", "FEASIBLE", "PARTIAL", "INFEASIBLE", "UNKNOWN"}


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
# Item models (extra fields allowed everywhere)
# ---------------------------------------------------------------------------

class _GameContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    game_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    duration_minutes: float = Field(gt=0)
    resource_type: str = Field(min_length=1)
    team_a_id: Optional[str] = None
    team_b_id: Optional[str] = None
    team_c_id: Optional[str] = None
    earliest_slot: Optional[str] = None
    latest_slot: Optional[str] = None


class _ResourceContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource_id: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    day: str = Field(min_length=1)
    open_time: str
    close_time: str
    slot_minutes: int = Field(gt=0)

    @field_validator("open_time", "close_time")
    @classmethod
    def _valid_time(cls, value: str) -> str:
        if not _TIME_RE.match(value or ""):
            raise ValueError("must be 'HH:MM'")
        if int(value.split(":")[1]) >= 60:
            raise ValueError("minutes must be < 60")
        return value


class _PlayoffSlotContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    game_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    slot: str = Field(min_length=1)


class _PrecedenceContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    before_game_id: str = Field(min_length=1)
    after_game_id: str = Field(min_length=1)
    min_gap_slots: Optional[int] = Field(default=None, ge=0)


class _TeamConflictContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    team_a_id: str = Field(min_length=1)
    team_b_id: str = Field(min_length=1)
    shared_count: Optional[int] = Field(default=None, ge=0)
    primary_overlap_count: Optional[int] = Field(default=None, ge=0)
    secondary_only_count: Optional[int] = Field(default=None, ge=0)
    shared_participant_names: Optional[list[str]] = None


class _AssignmentContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    game_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    slot: str = Field(min_length=1)


class _PoolResultContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource_type: str = Field(min_length=1)
    status: str

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str) -> str:
        if value not in _OUTPUT_STATUSES:
            raise ValueError(f"must be one of {sorted(_OUTPUT_STATUSES)}")
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


def _validate_items(
    items: Any,
    model: type[BaseModel],
    section: str,
    id_field: str,
    errors: list[str],
) -> None:
    """Validate each entry of one top-level list section, collecting errors."""
    if items is None:
        return
    if not isinstance(items, list):
        errors.append(f"{section}: must be a list, got {type(items).__name__}")
        return
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


def _parse_time_minutes(time_str: str) -> int:
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_schedule_input(data: dict[str, Any]) -> list[str]:
    """Validate a parsed schedule_input.json document.

    Returns a list of WARNING messages (conditions the solver tolerates but an
    operator should know about).  Raises ScheduleContractError when the
    document cannot be solved correctly as written.
    """
    errors: list[str] = []
    warnings: list[str] = []

    games = data.get("games")
    resources = data.get("resources")
    _validate_items(games, _GameContract, "games", "game_id", errors)
    _validate_items(resources, _ResourceContract, "resources", "resource_id", errors)
    _validate_items(
        data.get("playoff_slots"), _PlayoffSlotContract, "playoff_slots",
        "game_id", errors,
    )
    _validate_items(
        data.get("precedence"), _PrecedenceContract, "precedence",
        "before_game_id", errors,
    )
    _validate_items(
        data.get("team_conflicts"), _TeamConflictContract, "team_conflicts",
        "team_a_id", errors,
    )

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

    # Resource fit:
    #   - a resource_type with zero resources stays a WARNING — the solver
    #     reports those games as unscheduled and exits 1 (pinned behavior);
    #   - a game that cannot physically fit ANY resource of its own type is an
    #     ERROR — it would otherwise surface downstream as a mystery
    #     INFEASIBLE/unscheduled (previously only an advisory log).
    # A game needs ceil(duration / slot_minutes) consecutive slots on a single
    # resource, which fits exactly when slots × slot_minutes >= duration.
    capacity_by_type: dict[str, float] = {}
    windows_by_type: dict[str, list[str]] = {}
    for resource in resource_dicts:
        rtype = str(resource.get("resource_type") or "").strip()
        slot_min = resource.get("slot_minutes")
        if not rtype or not isinstance(slot_min, (int, float)) or slot_min <= 0:
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
    warned_missing_types: set[str] = set()
    for game in game_dicts:
        gid = str(game.get("game_id") or "").strip() or "<unknown>"
        rtype = str(game.get("resource_type") or "").strip()
        duration = game.get("duration_minutes")
        if not rtype or not isinstance(duration, (int, float)) or duration <= 0:
            continue  # field-level errors already recorded above
        if rtype not in types_with_resources:
            if rtype not in warned_missing_types:
                warned_missing_types.add(rtype)
                warnings.append(
                    f"games: resource_type {rtype!r} (e.g. game {gid!r}) has no "
                    "resources — those games will be reported as unscheduled"
                )
            continue
        if capacity_by_type.get(rtype, 0) < duration:
            available = "; ".join(windows_by_type.get(rtype, [])) or "none"
            errors.append(
                f"games: game {gid!r} ({duration:g} min) cannot fit any "
                f"{rtype!r} resource — available windows: {available}"
            )

    # Precedence integrity: cycles are errors; dangling references are
    # warnings because the solver silently ignores rules it cannot route.
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
    playoff_slots = data.get("playoff_slots")
    pinned_ids = {
        str(p.get("game_id") or "").strip()
        for p in (playoff_slots if isinstance(playoff_slots, list) else [])
        if isinstance(p, dict)
    }
    known_ids = seen_game_ids | pinned_ids
    for rule in precedence_rules:
        for side in ("before_game_id", "after_game_id"):
            ref = str(rule.get(side) or "").strip()
            if ref and ref not in known_ids:
                warnings.append(
                    f"precedence: {side} {ref!r} matches no game or playoff "
                    "slot — this rule will be ignored"
                )

    # Conflict edges with real overlaps but no names render empty
    # Conflict-Audit rows — warn so the export-side bug gets noticed.
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


def validate_schedule_output(data: dict[str, Any]) -> list[str]:
    """Validate a parsed schedule_output.json document before rendering.

    Returns WARNING messages; raises ScheduleContractError when the document
    would render an incorrect or ambiguous timetable.
    """
    errors: list[str] = []
    warnings: list[str] = []

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
        assignments, _AssignmentContract, "assignments", "game_id", errors
    )
    _validate_items(
        data.get("pool_results"), _PoolResultContract, "pool_results",
        "resource_type", errors,
    )

    unscheduled = data.get("unscheduled")
    if unscheduled is not None and not isinstance(unscheduled, list):
        errors.append(
            f"unscheduled: must be a list, got {type(unscheduled).__name__}"
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
