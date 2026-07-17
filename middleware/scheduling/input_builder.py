"""input_builder — schedule_input.json assembly orchestration extracted from
ScheduleWorkbookBuilder.

Step 8 of the Issue #152 decomposition. Pure extraction, no behavior changes.

Functions that need builder state take the ``ScheduleWorkbookBuilder``
``builder`` (the original ``self``/``cls``) as their first parameter and
reach everything through it.
"""
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger
from config import (
    SPORT_TYPE,
    COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
    COURT_ESTIMATE_MINUTES_PER_GAME,
    COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
    GYM_RESOURCE_TYPE_BASKETBALL,
    GYM_RESOURCE_TYPE_VOLLEYBALL,
    TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
    TEAM_RESOURCE_TYPE_SOCCER,
    SCHEDULE_SOLVER_GYM_COURTS,
    POD_RESOURCE_EVENT_TYPE,
)
from scheduling import venue_loader
from scheduling import xlsx_utils
from scheduling import manual_matchups
from scheduling import master_schedule
from scheduling import match_schedule_overrides


def _warn_if_resource_slot_minutes_differ_from_config(
    all_games: List[Dict[str, Any]],
    all_resources: List[Dict[str, Any]],
) -> None:
    """Log advisory warnings when venue slot sizes differ from config durations."""
    expected_minutes_by_resource_type: Dict[str, int] = {
        GYM_RESOURCE_TYPE_BASKETBALL: int(
            COURT_ESTIMATE_MINUTES_PER_GAME.get(
                SPORT_TYPE["BASKETBALL"],
                COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
            )
        ),
        GYM_RESOURCE_TYPE_VOLLEYBALL: int(
            COURT_ESTIMATE_MINUTES_PER_GAME.get(
                SPORT_TYPE["VOLLEYBALL_MEN"],
                COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
            )
        ),
        TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE: int(COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE),
        TEAM_RESOURCE_TYPE_SOCCER: int(
            COURT_ESTIMATE_MINUTES_PER_GAME.get(
                SPORT_TYPE["SOCCER"],
                COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
            )
        ),
    }

    pod_expected_minutes: Dict[str, set[int]] = defaultdict(set)
    for event_name, resource_type in POD_RESOURCE_EVENT_TYPE.items():
        pod_expected_minutes[resource_type].add(
            int(
                COURT_ESTIMATE_MINUTES_PER_GAME.get(
                    event_name,
                    COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
                )
            )
        )
    for resource_type, minute_values in pod_expected_minutes.items():
        if len(minute_values) == 1:
            expected_minutes_by_resource_type[resource_type] = next(iter(minute_values))

    scheduled_resource_types = {
        str(game.get("resource_type") or "").strip()
        for game in all_games
        if str(game.get("resource_type") or "").strip()
    }
    slot_minutes_by_resource_type: Dict[str, set[int]] = defaultdict(set)
    for resource in all_resources:
        resource_type = str(resource.get("resource_type") or "").strip()
        if resource_type not in scheduled_resource_types:
            continue
        try:
            slot_minutes = int(resource.get("slot_minutes") or 0)
        except (TypeError, ValueError):
            continue
        if slot_minutes > 0:
            slot_minutes_by_resource_type[resource_type].add(slot_minutes)

    for resource_type in sorted(scheduled_resource_types):
        expected_minutes = expected_minutes_by_resource_type.get(resource_type)
        actual_slot_minutes = sorted(slot_minutes_by_resource_type.get(resource_type, set()))
        if expected_minutes is None or not actual_slot_minutes:
            continue
        if actual_slot_minutes == [expected_minutes]:
            continue

        actual_text = ", ".join(str(value) for value in actual_slot_minutes)
        logger.warning(
            f"Layer 2 duration mismatch for '{resource_type}': config.py game duration is "
            f"{expected_minutes}m but venue_input.xlsx uses slot_minutes [{actual_text}]. "
            "This is only a warning. The solver keeps the config game duration and uses "
            "venue_input slot sizes for capacity, so games may span multiple slots or "
            "consume padded time. If the venue_input values are an intentional real-world "
            "override, you can ignore this warning."
        )

def _resolve_venue_playoff_slots(
    builder,
    playoff_slots: List[Dict[str, Any]],
    venue_rows: List[Dict[str, Any]],
    date_day_map: Dict[str, str],
    gym_modes: Dict[str, Dict[str, int]],
    allocator_active: bool,
    game_duration_by_id: Optional[Dict[str, int]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Any], set]:
    """Resolve venue-centric Playoff-Slots rows into concrete resources (Issue #127).

    A venue-centric row specifies gym_name + date + start_time instead of an
    internal resource_id + slot.  Resolution validates the venue against the
    Venue-Input rows and fills resource_id/slot in place:

    - **Allocator-managed gyms** (row's Exclusive Venue Group has a Gym-Modes
      entry and the Stage-A allocator is active): a playoff-pinned synthetic
      resource is created covering only the pinned window, and that window is
      returned as a reservation the allocator must skip.  Contiguous pins on
      the same gym/sport merge into one synthetic court track, mirroring the
      legacy same-resource_id merge behavior.
    - **Direct/standalone resources**: the row resolves to an existing
      expanded resource_id; validate_playoff_slots() reserves the exact
      (resource, slot) pair from pool play as it always has.

    Rows that already carry resource_id + slot pass through untouched (the
    explicit form remains valid as an override). Invalid venue-centric rows
    fail the build together so playoff intent is never silently omitted.

    Returns (resolved_playoff_slots, synthetic_resources, reserved_windows,
    synthetic_resource_ids).
    """
    from gym_allocator import EVENT_TO_MODE as _EVENT_TO_MODE, GymBlock

    event_to_resource_type = dict(_EVENT_TO_MODE)
    event_to_resource_type[SPORT_TYPE["BIBLE_CHALLENGE"]] = TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE
    event_to_resource_type[SPORT_TYPE["SOCCER"]] = TEAM_RESOURCE_TYPE_SOCCER

    def _minutes(text: str) -> int:
        hours, mins = text.split(":")
        return int(hours) * 60 + int(mins)

    def _clock(total: int) -> str:
        return f"{total // 60:02d}:{total % 60:02d}"

    def _overlaps(left: Tuple[int, int], right: Tuple[int, int]) -> bool:
        return left[0] < right[1] and right[0] < left[1]

    def _record_error(message: str) -> None:
        logger.error(message)
        errors.append(message)

    game_duration_by_id = game_duration_by_id or {}
    resolved: List[Dict[str, Any]] = []
    synthetic_resources: List[Dict[str, Any]] = []
    reserved_windows: List[Any] = []
    synthetic_ids: set = set()
    errors: List[str] = []
    # (gym exclusive_group, day, resource_type) -> pins for court tracks.
    managed_pending: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    managed_by_gym_day: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    used_intervals_by_resource: Dict[str, List[Tuple[int, int, str]]] = defaultdict(list)

    for entry in playoff_slots:
        if entry.get("resource_id") and entry.get("slot"):
            if entry.get("gym_name") or entry.get("date") or entry.get("start_time"):
                logger.info(
                    f"Playoff slot {entry['game_id']!r}: explicit resource_id+slot "
                    "takes precedence over gym_name/date/start_time."
                )
            game_id = str(entry.get("game_id") or "").strip()
            if game_id in game_duration_by_id:
                entry.setdefault(
                    "duration_minutes", game_duration_by_id[game_id]
                )
            resolved.append(entry)
            continue

        game_id = entry.get("game_id", "<unknown>")
        gym_name = str(entry.get("gym_name") or "").strip()
        date_text = str(entry.get("date") or "").strip()
        start_text = str(entry.get("start_time") or "").strip()

        if re.fullmatch(r"[A-Za-z]+-\d+", date_text):
            day = date_text
        else:
            day = date_day_map.get(date_text, "")
        if not day:
            _record_error(
                f"Playoff slot {game_id!r}: date {date_text!r} matches no "
                "Venue-Input date. Use a date that appears in "
                "the Venue-Input tab (or a day label such as 'Sun-2')."
            )
            continue

        event = str(entry.get("event") or "").strip()
        resource_type = event_to_resource_type.get(event)
        if not resource_type:
            _record_error(
                f"Playoff slot {game_id!r}: cannot infer a resource type from "
                f"event {event!r}. The event must exactly match "
                "a scheduled sport name."
            )
            continue

        gym_key = gym_name.casefold()
        candidates = [
            row for row in venue_rows
            if str(row.get("day") or "").strip() == day
            and str(row.get("resource_type") or "").strip() == resource_type
            and gym_key in (
                str(row.get("venue_name") or "").strip().casefold(),
                str(row.get("exclusive_group") or "").strip().casefold(),
            )
        ]
        if not candidates:
            _record_error(
                f"Playoff slot {game_id!r}: no Venue-Input row found for gym "
                f"{gym_name!r} on {day} with a {resource_type!r}. "
                "Check the gym name, date, and that the venue offers this sport."
            )
            continue

        start_min = _minutes(start_text)
        window_rows: List[Tuple[Dict[str, Any], int, int, int, int]] = []
        for row in candidates:
            row_slot_min = int(row.get("slot_minutes") or 60)
            exclusive_group = str(row.get("exclusive_group") or "").strip()
            managed = bool(
                allocator_active
                and exclusive_group
                and exclusive_group in gym_modes
            )
            grid_minutes = (
                int(entry.get("slot_minutes") or row_slot_min)
                if managed
                else row_slot_min
            )
            if (
                not managed
                and entry.get("slot_minutes")
                and int(entry["slot_minutes"]) != row_slot_min
            ):
                continue
            duration = int(
                entry.get("duration_minutes")
                or game_duration_by_id.get(str(game_id))
                or grid_minutes
            )
            occupied_minutes = (
                (duration + grid_minutes - 1) // grid_minutes
            ) * grid_minutes
            open_min = _minutes(str(row.get("open_time")))
            close_min = _minutes(str(row.get("close_time")))
            if open_min <= start_min and start_min + occupied_minutes <= close_min:
                window_rows.append(
                    (row, grid_minutes, duration, occupied_minutes, open_min)
                )
        if not window_rows:
            windows = sorted({
                f"{row.get('open_time')}-{row.get('close_time')}" for row in candidates
            })
            _record_error(
                f"Playoff slot {game_id!r}: start_time {start_text!r} and its "
                "game duration do not fit "
                f"inside any {gym_name!r} window on {day} ({', '.join(windows)}) "
                "on the venue's slot grid."
            )
            continue

        source_row, grid_minutes, duration, occupied_minutes, _open_min = window_rows[0]
        exclusive_group = str(source_row.get("exclusive_group") or "").strip()
        managed = bool(
            allocator_active and exclusive_group and exclusive_group in gym_modes
        )
        entry.setdefault("duration_minutes", duration)

        if managed:
            pending = {
                "entry":       entry,
                "start_min":   start_min,
                "end_min":     start_min + occupied_minutes,
                "duration":    duration,
                "grid_minutes": grid_minutes,
                "resource_type": resource_type,
                "source_row":  source_row,
            }
            managed_pending[(exclusive_group, day, resource_type)].append(pending)
            managed_by_gym_day[(exclusive_group, day)].append(pending)
            resolved.append(entry)
            continue

        # Direct/standalone resource: resolve to an existing expanded
        # resource whose slot grid contains this start and whose full
        # occupied interval is still free.
        slot_label = f"{day}-{_clock(start_min)}"
        chosen = None
        chosen_interval: Optional[Tuple[int, int, str]] = None
        for row, row_grid_min, row_duration, _occupied, open_min in sorted(
            window_rows,
            key=lambda item: (
                len(str(item[0].get("resource_id") or "")),
                str(item[0].get("resource_id") or ""),
            ),
        ):
            if (start_min - open_min) % row_grid_min != 0:
                continue
            rid = str(row.get("resource_id") or "").strip()
            end_min = start_min + (
                (row_duration + row_grid_min - 1) // row_grid_min
            ) * row_grid_min
            interval = (start_min, end_min)
            if any(
                _overlaps(interval, (used_start, used_end))
                for used_start, used_end, _used_game
                in used_intervals_by_resource[rid]
            ):
                continue
            chosen = rid
            chosen_interval = (start_min, end_min, str(game_id))
            break
        if chosen is None:
            _record_error(
                f"Playoff slot {game_id!r}: every {resource_type!r} at "
                f"{gym_name!r} is already occupied during "
                f"{_clock(start_min)}-{_clock(start_min + occupied_minutes)} "
                f"or has a slot grid that does not start at {start_text!r}."
            )
            continue
        entry["resource_id"] = chosen
        entry["slot"] = slot_label
        if chosen_interval is not None:
            used_intervals_by_resource[chosen].append(chosen_interval)
        resolved.append(entry)

    # Gym-Modes describes mutually-exclusive physical configurations. At
    # every instant a managed gym may host only one mode, and that mode may
    # not exceed its configured court/table count.
    for (exclusive_group, day), pins in managed_by_gym_day.items():
        boundaries = sorted({
            boundary
            for pin in pins
            for boundary in (pin["start_min"], pin["end_min"])
        })
        for segment_start, segment_end in zip(boundaries, boundaries[1:]):
            active = [
                pin for pin in pins
                if pin["start_min"] < segment_end
                and segment_start < pin["end_min"]
            ]
            if not active:
                continue
            active_types = {
                str(pin["resource_type"]) for pin in active
            }
            game_ids = sorted(
                str(pin["entry"].get("game_id") or "<unknown>")
                for pin in active
            )
            if len(active_types) > 1:
                _record_error(
                    f"Playoff-Slots pins "
                    f"{', '.join(repr(game_id) for game_id in game_ids)} "
                    f"overlap at mutually-exclusive gym {exclusive_group!r} on "
                    f"{day} {_clock(segment_start)}-{_clock(segment_end)} using "
                    f"different modes {sorted(active_types)}."
                )
                continue
            resource_type = next(iter(active_types))
            capacity = int(
                gym_modes.get(exclusive_group, {}).get(resource_type, 0)
            )
            if len(active) > capacity:
                _record_error(
                    f"Playoff-Slots pins "
                    f"{', '.join(repr(game_id) for game_id in game_ids)} "
                    f"need {len(active)} concurrent {resource_type!r} resources "
                    f"at {exclusive_group!r} on {day} "
                    f"{_clock(segment_start)}-{_clock(segment_end)}, but "
                    f"Gym-Modes provides {capacity}."
                )

    if errors:
        details = "\n".join(f"  - {message}" for message in errors)
        raise ValueError(
            "Invalid venue-centric Playoff-Slots configuration:\n" + details
        )

    # Track pass for allocator-managed gyms: contiguous pins share one
    # synthetic court; concurrent pins get separate courts.
    synthetic_counters: Dict[Tuple[str, str], int] = {}
    for (exclusive_group, day, resource_type), pins in managed_pending.items():
        pins.sort(key=lambda p: p["start_min"])
        tracks: List[Dict[str, Any]] = []
        prefix = builder._resource_id_prefix(resource_type)
        for pin in pins:
            track = next(
                (
                    t for t in tracks
                    if t["close_min"] == pin["start_min"]
                    and t["slot_minutes"] == pin["grid_minutes"]
                ),
                None,
            )
            if track is None:
                counter_key = (prefix, day)
                n = synthetic_counters.get(counter_key, 0) + 1
                synthetic_counters[counter_key] = n
                label_kind = "Table" if "table" in resource_type.lower() else "Court"
                track = {
                    "resource_id": f"{prefix}-{day}-PF{n}",
                    "label":       f"{label_kind}-PF{n}",
                    "open_min":    pin["start_min"],
                    "close_min":   pin["end_min"],
                    "slot_minutes": pin["grid_minutes"],
                    "source_row":  pin["source_row"],
                }
                tracks.append(track)
            else:
                track["close_min"] = pin["end_min"]
            entry = pin["entry"]
            entry["resource_id"] = track["resource_id"]
            entry["slot"] = f"{day}-{_clock(pin['start_min'])}"

        for track in tracks:
            source_row = track["source_row"]
            synthetic = {
                "resource_id":     track["resource_id"],
                "resource_type":   resource_type,
                "label":           track["label"],
                "day":             day,
                "open_time":       _clock(track["open_min"]),
                "close_time":      _clock(track["close_min"]),
                "slot_minutes":    track["slot_minutes"],
                "venue_name":      source_row.get("venue_name", ""),
                "exclusive_group": exclusive_group,
                "playoff_pinned":  True,
            }
            synthetic_resources.append(synthetic)
            synthetic_ids.add(track["resource_id"])
            reserved_windows.append(GymBlock(
                gym_name=exclusive_group,
                day=day,
                open_time=synthetic["open_time"],
                close_time=synthetic["close_time"],
                slot_minutes=track["slot_minutes"],
                resource_types=frozenset({resource_type}),
            ))
            logger.info(
                f"Playoff venue pin: reserved {exclusive_group!r} "
                f"{day} {synthetic['open_time']}–{synthetic['close_time']} as "
                f"{track['resource_id']!r} ({resource_type}) — excluded from "
                "pool-play allocation."
            )

    return resolved, synthetic_resources, reserved_windows, synthetic_ids

def _build_schedule_input(
    builder,
    roster_rows: List[Dict[str, Any]],
    validation_rows: List[Dict[str, Any]],
    venue_input_path: Path,
    pool_assignment_path: Optional[Path] = None,
    manual_matchup_path: Optional[Path] = None,
    manual_schedule_path: Optional[Path] = None,
    match_schedule_overrides_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Assemble the full schedule_input package consumed by OR-Tools.

    Returns a dict with keys: generated_at, gym_court_scenario, game_count,
    resource_count, games, resources, playoff_slots, gym_modes, gym_allocation.

    When venue_input.xlsx is present with a Gym-Modes tab, the Layer-2
    Stage-A greedy allocator runs and produces real gym resources keyed to
    the booked venue.  Otherwise falls back to the SCHEDULE_SOLVER_GYM_COURTS
    constant split evenly between basketball and volleyball when no explicit
    venue rows exist. If venue rows exist but the allocator cannot run, the
    explicit Venue-Input rows are used directly.
    """
    from gym_allocator import (
        aggregate_demand_by_mode, extract_gym_blocks, allocate,
    )
    gym_modes = builder._load_gym_modes(venue_input_path)
    venue_rows, day_order = builder._load_venue_input_rows(venue_input_path)
    playoff_slots = builder._load_playoff_slots(venue_input_path)
    gym_blocks = extract_gym_blocks(venue_rows)
    explicit_gym_resource_types = {
        GYM_RESOURCE_TYPE_BASKETBALL,
        GYM_RESOURCE_TYPE_VOLLEYBALL,
    }
    has_explicit_gym_rows = any(
        resource.get("resource_type") in explicit_gym_resource_types
        for resource in venue_rows
    )
    gym_resource_strategy = (
        "allocator"
        if gym_blocks and gym_modes
        else "direct_venue_input"
        if has_explicit_gym_rows
        else "fallback"
    )

    pool_assignment_rows = builder._build_pool_assignment_rows(
        roster_rows,
        pool_assignment_path,
    )
    manual_matchup_payload = manual_matchups.load_manual_matchup_sidecar(
        manual_matchup_path
    )
    manual_schedule_summary: Dict[str, Any] = {}
    (
        manual_team_sport_games,
        manual_team_sport_precedence,
        manual_imported_events,
        manual_matchup_summary,
    ) = builder._build_manual_team_sport_game_objects(manual_matchup_payload)
    gym_games, gym_precedence = builder._build_assigned_gym_game_objects(
        roster_rows,
        pool_assignment_rows,
        allow_placeholder_fallback=(gym_resource_strategy == "fallback"),
        excluded_events=manual_imported_events,
    )
    if manual_imported_events:
        logger.info(
            "Manual team matchups imported for events: "
            + ", ".join(sorted(manual_imported_events))
        )
    if SPORT_TYPE["BIBLE_CHALLENGE"] in manual_imported_events:
        bc_games, precedence = [], []
    else:
        bc_games, precedence = builder._build_assigned_bc_game_objects(pool_assignment_rows)
    if SPORT_TYPE["SOCCER"] in manual_imported_events:
        soccer_games, soccer_precedence = [], []
    else:
        soccer_games, soccer_precedence = builder._build_assigned_soccer_game_objects(
            roster_rows,
            pool_assignment_rows,
        )
    pod_games, pod_precedence = builder._build_pod_game_objects(roster_rows, validation_rows)
    all_games = manual_team_sport_games + gym_games + bc_games + soccer_games + pod_games
    team_conflicts = builder._build_gym_team_conflicts(roster_rows, pool_assignment_rows)
    team_conflicts += builder._build_cross_sport_conflicts(
        roster_rows, pool_assignment_rows, validation_rows
    )
    _confirmed_pods, pod_unprotected_entries = builder._resolve_pod_doubles(
        roster_rows, validation_rows
    )
    pod_validation_reconciliation = builder._reconcile_pod_validation(
        pod_unprotected_entries, _confirmed_pods, validation_rows
    )
    precedence.extend(manual_team_sport_precedence)
    precedence.extend(gym_precedence)
    precedence.extend(soccer_precedence)
    precedence.extend(pod_precedence)

    # Resolve venue-centric Playoff-Slots after game generation so physical
    # reservations use each game's real duration, but still before Stage-A
    # allocation so those windows are removed from pool-play inventory.
    date_day_map = builder._load_venue_date_day_map(venue_input_path)
    game_duration_by_id = {
        str(game.get("game_id") or "").strip(): int(
            game.get("duration_minutes") or 0
        )
        for game in all_games
        if str(game.get("game_id") or "").strip()
        and int(game.get("duration_minutes") or 0) > 0
    }
    (
        playoff_slots,
        playoff_synthetic_resources,
        playoff_reserved_windows,
        playoff_synthetic_ids,
    ) = builder._resolve_venue_playoff_slots(
        playoff_slots,
        venue_rows,
        date_day_map,
        gym_modes,
        allocator_active=(gym_resource_strategy == "allocator"),
        game_duration_by_id=game_duration_by_id,
    )

    gym_allocation: Optional[Dict[str, Any]] = None
    if gym_resource_strategy == "allocator":
        venue_capacity_rows = builder._build_venue_capacity_rows(roster_rows)
        demand = aggregate_demand_by_mode(venue_capacity_rows)
        # Days that carry pinned playoff slots are excluded from the
        # spreading pass in allocate() — those blocks are handled by the
        # playoff-slot promotion path below and must not be pre-empted.
        _playoff_days: set = set()
        for _ps in playoff_slots:
            _slot = str(_ps.get("slot") or "").strip()
            if _slot:
                _parts = _slot.rsplit("-", 1)
                if len(_parts) == 2:
                    _playoff_days.add(_parts[0])
        alloc_result = allocate(demand, gym_modes, gym_blocks,
                                spreading_excluded_days=_playoff_days,
                                reserved_windows=playoff_reserved_windows)
        gym_resources = builder._build_gym_resources_from_allocator(alloc_result.decisions)
        # Rows with no exclusive_group are standalone resources — include directly.
        # Rows whose exclusive_group has no Gym-Modes entry were not seen by the
        # allocator; include them directly too, and warn so the operator knows
        # mutual exclusivity is not enforced for those venues.
        covered_groups = set(gym_modes.keys())
        uncovered_groups = {
            r["exclusive_group"] for r in venue_rows
            if r.get("exclusive_group") and r["exclusive_group"] not in covered_groups
        }
        if uncovered_groups:
            logger.warning(
                f"Exclusive venue group(s) {sorted(uncovered_groups)} appear in Venue-Input "
                "but have no entry in the Gym-Modes tab. Their rows are included as direct "
                "resources without mode-exclusivity enforcement. Add them to Gym-Modes if "
                "the courts in those venues cannot be used simultaneously."
            )
        direct_resources = [
            r for r in venue_rows
            if not r.get("exclusive_group") or r["exclusive_group"] not in covered_groups
        ]
        all_resources = gym_resources + direct_resources
        gym_allocation = {
            "source":        "allocator",
            "decisions":     [
                {
                    "gym_name":     d.gym_name,
                    "day":          d.day,
                    "open_time":    d.open_time,
                    "close_time":   d.close_time,
                    "mode":         d.mode,
                    "courts":       d.courts,
                    "slot_minutes": d.slot_minutes,
                }
                for d in alloc_result.decisions
            ],
            "mode_supply":    alloc_result.mode_supply,
            "mode_demand":    alloc_result.mode_demand,
            "mode_shortfall": alloc_result.mode_shortfall,
            "switch_count":   alloc_result.switch_count,
        }
        logger.info(
            f"Gym allocation (Stage A): {len(alloc_result.decisions)} blocks assigned, "
            f"{alloc_result.switch_count} mode switches"
        )
    elif gym_resource_strategy == "direct_venue_input":
        all_resources = venue_rows
        if gym_blocks and not gym_modes:
            reason = "grouped_rows_without_gym_modes"
            logger.warning(
                "Gym allocation skipped: Venue-Input contains Exclusive Venue Group rows "
                "but no Gym-Modes tab. Using Venue-Input rows directly; mutual exclusivity "
                "is not enforced in this mode."
            )
        elif gym_modes and not gym_blocks:
            reason = "gym_modes_without_grouped_rows"
            logger.info(
                "Gym allocation skipped: Gym-Modes tab is present but no Exclusive Venue "
                "Group rows were found. Using Venue-Input rows directly."
            )
        else:
            reason = "explicit_venue_rows_without_allocator"
        gym_allocation = {"source": "direct_venue_input", "reason": reason}
    else:
        n_bb = SCHEDULE_SOLVER_GYM_COURTS // 2
        n_vb = SCHEDULE_SOLVER_GYM_COURTS - n_bb
        gym_resources = builder._build_gym_resource_objects(n_bb, n_vb)
        all_resources = gym_resources + venue_rows
        gym_allocation = {"source": "fallback", "gym_court_scenario": SCHEDULE_SOLVER_GYM_COURTS}
        logger.info(
            f"Gym allocation: fallback mode — {n_bb} basketball + {n_vb} volleyball courts "
            f"per session (SCHEDULE_SOLVER_GYM_COURTS={SCHEDULE_SOLVER_GYM_COURTS})"
        )

    # Synthetic playoff-pinned resources from venue-centric Playoff-Slots
    # rows (Issue #127).  Added as a new list so the direct_venue_input
    # branch's venue_rows alias is never mutated.
    if playoff_synthetic_resources:
        all_resources = all_resources + playoff_synthetic_resources

    # Promote any playoff-pinned resource that the allocator didn't emit.
    # Rather than adding the whole multi-slot venue row (which would expose
    # unused slots to pool play), we synthesise a one-slot resource covering
    # only the exact time window referenced in the playoff entry.  The
    # playoff_pinned flag keeps the resource out of capacity diagnostics;
    # gym-sport synthetics still join the Gym Core solver pool below so
    # precedence rules involving the pinned game stay enforceable.
    #
    # Venue rows for gym sports use BB-*/VB-* resource_ids (per
    # RESOURCE_ID_PREFIX_BY_TYPE), while allocator-generated resources use
    # GYM-* ids — so we cannot look up by resource_id directly.  Instead we
    # derive day from the slot label and resource_type from the game event,
    # then find a representative venue row for slot_minutes / venue metadata.
    from gym_allocator import EVENT_TO_MODE as _EVENT_TO_MODE

    grouped_rows = [row for row in venue_rows if row.get("exclusive_group")]
    if grouped_rows and playoff_slots:
        block_mode_rows: Dict[Tuple[Tuple[str, str, str, str], str], List[Dict[str, Any]]] = defaultdict(list)
        block_capacity: Dict[Tuple[str, str, str, str], int] = {}
        day_blocks: Dict[str, List[Tuple[str, str, str, str]]] = defaultdict(list)

        for venue_row in grouped_rows:
            block_key = (
                str(venue_row.get("day") or "").strip(),
                str(venue_row.get("exclusive_group") or "").strip(),
                str(venue_row.get("open_time") or "").strip(),
                str(venue_row.get("close_time") or "").strip(),
            )
            resource_type = str(venue_row.get("resource_type") or "").strip()
            block_mode_rows[(block_key, resource_type)].append(venue_row)

        for (block_key, _resource_type), rows in block_mode_rows.items():
            block_capacity[block_key] = max(block_capacity.get(block_key, 0), len(rows))

        for block_key in block_capacity:
            day_blocks[block_key[0]].append(block_key)

        for day_label, blocks in day_blocks.items():
            blocks.sort(key=lambda item: (
                builder._parse_hour(item[2]),
                item[1],
                builder._parse_hour(item[3]),
            ))

        block_ranges: Dict[Tuple[str, str, str, str], Tuple[int, int]] = {}
        for day_label, blocks in day_blocks.items():
            ordinal = 0
            for block_key in blocks:
                start_ordinal = ordinal + 1
                ordinal += block_capacity[block_key]
                block_ranges[block_key] = (start_ordinal, ordinal)

        resources_by_id: Dict[str, Dict[str, Any]] = {
            str(resource.get("resource_id") or "").strip(): resource
            for resource in all_resources
        }

        for playoff_slot in playoff_slots:
            game_id = str(playoff_slot.get("game_id") or "").strip() or "<unknown>"
            resource_id = str(playoff_slot.get("resource_id") or "").strip()
            slot_label = str(playoff_slot.get("slot") or "").strip()
            event = str(playoff_slot.get("event") or "").strip()
            if not resource_id or not slot_label:
                continue

            # Venue-centric rows were already resolved (and their windows
            # reserved) by _resolve_venue_playoff_slots — the legacy GYM-*
            # ordinal promotion below does not apply to them.
            if resource_id in playoff_synthetic_ids:
                continue

            existing_resource = resources_by_id.get(resource_id)
            if existing_resource is not None and not existing_resource.get("playoff_pinned"):
                continue

            day, time_part = builder._split_slot_label(slot_label)
            if not day or not time_part:
                logger.warning(
                    f"Playoff slot {game_id!r}: cannot parse day/time from slot {slot_label!r} — skipped."
                )
                continue

            resource_type = _EVENT_TO_MODE.get(event)
            if not resource_type:
                logger.warning(
                    f"Playoff slot {game_id!r}: cannot infer resource_type from "
                    f"event {event!r} — skipped. Ensure event matches a gym sport name."
                )
                continue

            expected_prefix = f"GYM-{day}-"
            if not resource_id.startswith(expected_prefix):
                logger.warning(
                    f"Playoff slot {game_id!r}: resource_id {resource_id!r} does not match "
                    f"slot day {day!r}; expected prefix {expected_prefix!r}. Skipped."
                )
                continue
            ordinal_text = resource_id[len(expected_prefix):]
            if not ordinal_text.isdigit():
                logger.warning(
                    f"Playoff slot {game_id!r}: resource_id {resource_id!r} does not end "
                    "with a numeric court ordinal; skipped."
                )
                continue
            requested_ordinal = int(ordinal_text)
            slot_hour = builder._parse_hour(time_part)

            matched_rows: List[Dict[str, Any]] = []
            matched_local_index = -1
            for block_key in day_blocks.get(day, []):
                block_open = builder._parse_hour(block_key[2])
                block_close = builder._parse_hour(block_key[3])
                if not (block_open <= slot_hour < block_close):
                    continue

                start_ordinal, end_ordinal = block_ranges[block_key]
                if not (start_ordinal <= requested_ordinal <= end_ordinal):
                    continue

                candidate_rows = sorted(
                    block_mode_rows.get((block_key, resource_type), []),
                    key=lambda row: (
                        str(row.get("label") or "").strip(),
                        str(row.get("resource_id") or "").strip(),
                    ),
                )
                if not candidate_rows:
                    continue

                local_index = requested_ordinal - start_ordinal
                if local_index >= len(candidate_rows):
                    continue

                matched_rows = candidate_rows
                matched_local_index = local_index
                break

            if matched_local_index < 0:
                logger.warning(
                    f"Playoff slot {game_id!r}: resource_id {resource_id!r} is not a plausible "
                    f"{resource_type} court for {day} at {time_part}. Check the requested "
                    "court ordinal or add a direct venue row instead."
                )
                continue

            source_row = matched_rows[matched_local_index]
            slot_minutes = int(source_row.get("slot_minutes") or 60)
            try:
                hour, minute = (int(x) for x in time_part.split(":"))
                close_total = hour * 60 + minute + slot_minutes
                close_time = f"{close_total // 60:02d}:{close_total % 60:02d}"
            except (ValueError, AttributeError):
                close_time = str(source_row.get("close_time") or time_part)

            if existing_resource is not None:
                if (
                    str(existing_resource.get("day") or "").strip() != day
                    or str(existing_resource.get("resource_type") or "").strip() != resource_type
                ):
                    logger.warning(
                        f"Playoff slot {game_id!r}: resource_id {resource_id!r} was already "
                        "promoted for a different day/resource_type; skipped."
                    )
                    continue
                existing_resource["open_time"] = min(
                    str(existing_resource.get("open_time") or time_part),
                    time_part,
                    key=builder._parse_hour,
                )
                existing_resource["close_time"] = max(
                    str(existing_resource.get("close_time") or close_time),
                    close_time,
                    key=builder._parse_hour,
                )
                continue

            synthetic = {
                "resource_id":     resource_id,
                "resource_type":   resource_type,
                "label":           source_row.get("label", "Court-1"),
                "day":             day,
                "open_time":       time_part,
                "close_time":      close_time,
                "slot_minutes":    slot_minutes,
                "venue_name":      source_row.get("venue_name", ""),
                "exclusive_group": source_row.get("exclusive_group", ""),
                "playoff_pinned":  True,
            }
            all_resources.append(synthetic)
            resources_by_id[resource_id] = synthetic
            logger.info(
                f"Promoted playoff-pinned resource {resource_id!r} ({resource_type}, "
                f"{day} {time_part}) — single-slot, excluded from pool play."
            )

    manual_schedule_payload = master_schedule.load_master_schedule_sidecar(
        manual_schedule_path
    )
    if manual_schedule_payload:
        playoff_slots, manual_schedule_summary = (
            master_schedule.merge_master_schedule_into_playoff_slots(
                playoff_slots,
                manual_schedule_payload,
                all_games,
                all_resources,
            )
        )
        logger.info(
            "Manual schedule overrides: "
            f"{manual_schedule_summary.get('fixed_count', 0)} fixed assignment(s), "
            f"{manual_schedule_summary.get('unresolved_count', 0)} unresolved row(s)"
        )
        for warning in manual_schedule_summary.get("warnings", []) or []:
            logger.warning(f"manual schedule override: {warning}")
        errors = manual_schedule_summary.get("errors", []) or []
        if errors:
            for error in errors:
                logger.error(f"manual schedule override: {error}")
            raise ValueError(
                "manual_schedule_overrides.json contains conflicting fixed assignments"
            )

    match_schedule_overrides_payload = match_schedule_overrides.load_match_schedule_overrides_sidecar(
        match_schedule_overrides_path
    )
    match_schedule_overrides_summary: Dict[str, Any] = {}
    if match_schedule_overrides_payload:
        all_games, playoff_slots, match_schedule_overrides_summary = (
            match_schedule_overrides.merge_match_schedule_overrides_into_schedule_input(
                all_games,
                playoff_slots,
                match_schedule_overrides_payload,
                all_resources,
            )
        )
        logger.info(
            "Match schedule overrides: "
            f"{match_schedule_overrides_summary.get('fixed_count', 0)} pinned assignment(s), "
            f"{match_schedule_overrides_summary.get('created_game_count', 0)} newly-created game(s)"
        )
        for warning in match_schedule_overrides_summary.get("warnings", []) or []:
            logger.warning(f"match schedule override: {warning}")
        errors = match_schedule_overrides_summary.get("errors", []) or []
        if errors:
            for error in errors:
                logger.error(f"match schedule override: {error}")
            raise ValueError(
                "match_schedule_overrides.json contains conflicting assignments"
            )

    if bc_games and not any(
        str(resource.get("resource_type") or "").strip() == TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE
        for resource in all_resources
    ):
        logger.warning(
            "Bible Challenge games were generated but no 'BC Station' resources were found "
            "in venue_input.xlsx. Those games will be unscheduled until a BC Station row is added."
        )

    if soccer_games and not any(
        str(resource.get("resource_type") or "").strip() == TEAM_RESOURCE_TYPE_SOCCER
        for resource in all_resources
    ):
        logger.warning(
            "Soccer games were generated but no 'Soccer Field' resources were found "
            "in venue_input.xlsx. Those games will be unscheduled until a Soccer Field row is added."
        )

    builder._warn_if_resource_slot_minutes_differ_from_config(all_games, all_resources)

    # Playoff-pinned BB/VB resources join the Gym Core pool too: a pinned
    # Semi/Final game takes its pool from its pinned resource, and the
    # auto-generated QF→Semi→Final precedence rules can only be enforced
    # when the pinned game shares a pool with its pool-play siblings.
    # Pool play still cannot use a pinned resource — its window covers
    # only the pinned slots, all reserved by validate_playoff_slots.
    for resource in all_resources:
        if resource.get("resource_type") in (
            GYM_RESOURCE_TYPE_BASKETBALL,
            GYM_RESOURCE_TYPE_VOLLEYBALL,
        ):
            resource["solver_pool"] = builder._GYM_CORE_SOLVER_POOL

    # Constrain QF games to end no later than the last slot on the day
    # BEFORE the Finals pinned day for that sport.  When the user pins a
    # Final to e.g. Sun-2-14:00, they almost always intend QFs to run the
    # day before (Sat-2) — that's why Sat-2 capacity exists in venue_input.
    # Without this constraint, CP-SAT can FEASIBLY (but undesirably) push
    # a QF onto the Finals day next to its Semi/Final.
    finals_day_by_event: Dict[str, str] = {}
    for ps in playoff_slots:
        if str(ps.get("stage") or "").strip().lower() != "final":
            continue
        slot = str(ps.get("slot") or "").strip()
        event_label = str(ps.get("event") or "").strip()
        if not slot or not event_label:
            continue
        day, _ = builder._split_slot_label(slot)
        if day:
            finals_day_by_event[event_label] = day

    if finals_day_by_event:
        for game in all_games:
            if str(game.get("stage") or "").strip() not in ("QF", "Semi"):
                continue
            event_label = str(game.get("event") or "").strip()
            finals_day = finals_day_by_event.get(event_label)
            if not finals_day:
                continue
            try:
                finals_idx = day_order.index(finals_day)
            except ValueError:
                continue
            if finals_idx <= 0:
                continue
            day_before = day_order[finals_idx - 1]
            court_type = str(game.get("resource_type") or "").strip()
            if not court_type:
                continue
            latest = venue_loader._last_slot_label_on_day(
                all_resources, court_type, day_before,
            )
            if latest:
                game["latest_slot"] = latest

    schedule_input = {
        "generated_at":       datetime.now().isoformat(timespec="seconds"),
        "gym_court_scenario": SCHEDULE_SOLVER_GYM_COURTS,
        "game_count":         len(all_games),
        "resource_count":     len(all_resources),
        "games":              all_games,
        "resources":          all_resources,
        "playoff_slots":      playoff_slots,
        "gym_modes":          gym_modes,
        "gym_allocation":     gym_allocation,
        "team_conflicts":     team_conflicts,
        "pod_unprotected_entries": pod_unprotected_entries,
        "pod_validation_reconciliation": pod_validation_reconciliation,
        "precedence":         precedence,
        "day_order":          day_order,
    }
    if manual_matchup_summary:
        schedule_input["manual_matchups"] = manual_matchup_summary
    if manual_schedule_summary:
        schedule_input["manual_schedule_overrides"] = manual_schedule_summary
    if match_schedule_overrides_summary:
        schedule_input["match_schedule_overrides"] = match_schedule_overrides_summary
    return schedule_input

def _load_available_slots_from_schedule_input(
    schedule_input: Dict[str, Any],
) -> Dict[str, int]:
    """Summarize total available slots per resource_type from schedule_input."""
    totals: Dict[str, int] = {}
    for res in schedule_input.get("resources", []):
        resource_type = xlsx_utils._clean_excel_text(
            res.get("resource_type")
        )
        if not resource_type:
            continue
        open_time = xlsx_utils._clean_excel_text(res.get("open_time"))
        close_time = xlsx_utils._clean_excel_text(res.get("close_time"))
        slot_min = int(res.get("slot_minutes", 0) or 0)
        if not open_time or not close_time or slot_min <= 0:
            continue
        start = xlsx_utils._parse_hour(open_time)
        close = xlsx_utils._parse_hour(close_time)
        if close < start:
            continue
        available = int(((close - start) * 60 / slot_min))
        totals[resource_type] = totals.get(resource_type, 0) + max(available, 0)
    logger.debug(f"Derived availability from schedule_input resources: {totals}")
    return totals

def write_schedule_input_json(
    builder,
    roster_rows: List[Dict[str, Any]],
    validation_rows: List[Dict[str, Any]],
    venue_input_path: Path,
    json_path: Path,
    pool_assignment_path: Optional[Path] = None,
    manual_matchup_path: Optional[Path] = None,
    manual_schedule_path: Optional[Path] = None,
    match_schedule_overrides_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build schedule_input dict and write it as JSON. Returns the dict.
    Always called by export-church-teams, regardless of whether venue_input.xlsx
    exists (graceful degradation is handled inside _build_schedule_input).
    """
    schedule_input = builder._build_schedule_input(
        roster_rows,
        validation_rows,
        venue_input_path,
        pool_assignment_path=pool_assignment_path,
        manual_matchup_path=manual_matchup_path,
        manual_schedule_path=manual_schedule_path,
        match_schedule_overrides_path=match_schedule_overrides_path,
    )
    json_path.write_text(json.dumps(schedule_input, indent=2, default=str), encoding="utf-8")
    logger.info(
        f"Schedule-Input: {schedule_input['game_count']} games, "
        f"{schedule_input['resource_count']} resources -> {json_path}"
    )
    return schedule_input
