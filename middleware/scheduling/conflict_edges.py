"""conflict_edges — shared-athlete conflict edge construction extracted from
ScheduleWorkbookBuilder.

Step 7 of the Issue #152 decomposition. Pure extraction, no behavior changes.

Functions that need builder state take the ``ScheduleWorkbookBuilder``
``builder`` (the original ``self``/``cls``) as their first parameter and
reach everything through it.
"""
from typing import Any, Dict, List, Optional, Tuple
from config import (
    SPORT_FORMAT,
)


def _build_core_gym_team_lookup(
    builder,
    roster_rows: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Return team membership metadata keyed by (event_name, team_id)."""
    team_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for event_name, _prefix in builder._POOL_ASSIGNMENT_EVENT_DEFS:
        min_team_size = builder._get_min_team_size(event_name)
        target_type, target_gender, _target_format = builder._decompose_event_name(event_name)
        provisional: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for roster_row in roster_rows:
            r_type = str(roster_row.get("sport_type") or "").strip()
            r_gender = str(roster_row.get("sport_gender") or "").strip()
            r_format = str(roster_row.get("sport_format") or "").strip()
            if (
                r_type.casefold() != target_type.casefold()
                and r_type.casefold() != event_name.casefold()
            ):
                continue
            if target_gender and r_gender.casefold() != target_gender.casefold():
                continue
            if r_format and r_format.casefold() != SPORT_FORMAT["TEAM"].casefold():
                continue

            church_code = str(roster_row.get("Church Team") or "").strip().upper()
            if not church_code:
                continue
            team_order = str(roster_row.get("team_order") or "").strip().upper()
            team_id = church_code if not team_order else f"{church_code}-{team_order}"
            key = (event_name, team_id)
            team_state = provisional.setdefault(
                key,
                {
                    "event": event_name,
                    "team_id": team_id,
                    "solver_team_id": builder._solver_team_id(event_name, team_id),
                    "display_label": team_id,
                    "participant_ids": set(),
                    "participant_names": {},
                    "primary_sports": {},
                },
            )
            participant_id = str(
                roster_row.get("Participant ID (WP)")
                or roster_row.get("ChMeetings ID")
                or ""
            ).strip()
            if not participant_id:
                continue

            team_state["participant_ids"].add(participant_id)
            full_name = (
                f"{str(roster_row.get('First Name') or '').strip()} "
                f"{str(roster_row.get('Last Name') or '').strip()}"
            ).strip()
            if full_name:
                team_state["participant_names"][participant_id] = full_name
            team_state["primary_sports"][participant_id] = builder._normalize_primary_sport_name(
                roster_row.get("participant_primary_sport")
            )

        for key, team_state in provisional.items():
            if len(team_state["participant_ids"]) < min_team_size:
                continue
            team_lookup[key] = team_state

    return team_lookup

def _build_gym_team_conflicts(
    builder,
    roster_rows: List[Dict[str, Any]],
    pool_assignment_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return cross-sport shared-athlete edges for the current Phase 1 team sports."""
    team_lookup = builder._build_core_gym_team_lookup(roster_rows)
    if not team_lookup:
        return []

    assigned_rows = {
        (str(row.get("Event") or "").strip(), str(row.get("Team ID") or "").strip())
        for row in pool_assignment_rows
        if str(row.get("Pool ID") or "").strip() and str(row.get("Pool Slot") or "").strip()
    }
    ordered_keys = sorted(
        [key for key in team_lookup.keys() if key in assigned_rows],
        key=lambda item: (builder._event_sort_index(item[0]), item[1]),
    )
    units = {key: builder._team_state_to_unit(team_lookup[key]) for key in ordered_keys}

    conflicts: List[Dict[str, Any]] = []
    for idx, key_a in enumerate(ordered_keys):
        unit_a = units[key_a]
        if not unit_a["participant_ids"]:
            continue
        for key_b in ordered_keys[idx + 1:]:
            if key_a[0] == key_b[0]:
                continue
            edge = builder._make_shared_athlete_edge(unit_a, units[key_b])
            if edge:
                conflicts.append(edge)

    return conflicts

def _team_state_to_unit(team_state: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a gym team-lookup entry into a shared-athlete conflict unit."""
    return {
        "unit_id": team_state["solver_team_id"],
        "label": team_state["display_label"],
        "event": team_state["event"],
        "participant_ids": team_state["participant_ids"],
        "participant_names": team_state["participant_names"],
        "primary_sports": team_state["primary_sports"],
    }

def _make_shared_athlete_edge(
    unit_a: Dict[str, Any],
    unit_b: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return one shared-athlete conflict edge, or None when no athlete overlaps.

    A unit is any scheduling entity with a roster: a gym team (Basketball,
    Volleyball, BC, Soccer) or a racquet doubles pair.  The edge dict shape
    is identical for every conflict class so the solver and Conflict-Audit
    tab consume team↔team, team↔racquet, and racquet↔racquet edges the same
    way.  A shared athlete is counted as a *primary* overlap when their
    declared primary sport matches one of the two units' events; otherwise
    it is *secondary* (their primary sport is a third event).
    """
    shared_ids = sorted(set(unit_a["participant_ids"]) & set(unit_b["participant_ids"]))
    if not shared_ids:
        return None

    primary_overlap_count = 0
    shared_names: List[str] = []
    for participant_id in shared_ids:
        primary_sport = (
            unit_a["primary_sports"].get(participant_id)
            or unit_b["primary_sports"].get(participant_id)
            or ""
        )
        if primary_sport and primary_sport.casefold() in {
            str(unit_a["event"]).casefold(),
            str(unit_b["event"]).casefold(),
        }:
            primary_overlap_count += 1
        shared_names.append(
            unit_a["participant_names"].get(
                participant_id,
                unit_b["participant_names"].get(participant_id, participant_id),
            )
        )

    return {
        "team_a_id": unit_a["unit_id"],
        "team_a_label": unit_a["label"],
        "event_a": unit_a["event"],
        "team_b_id": unit_b["unit_id"],
        "team_b_label": unit_b["label"],
        "event_b": unit_b["event"],
        "shared_participant_ids": shared_ids,
        "shared_participant_names": shared_names,
        "shared_count": len(shared_ids),
        "primary_overlap_count": primary_overlap_count,
        "secondary_only_count": len(shared_ids) - primary_overlap_count,
    }

def _build_cross_sport_conflicts(
    builder,
    roster_rows: List[Dict[str, Any]],
    pool_assignment_rows: List[Dict[str, Any]],
    validation_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return team↔racquet and racquet↔racquet shared-athlete edges (#158, #164).

    Covers the conflict classes the gym-only builder misses:
      (b) a participant in a team sport and a racquet event, and
      (c) a participant in two racquet events.
    Racquet units are confirmed doubles pairs (Issue #158) and all singles
    entries (Issue #164) — singles membership is always known, so every
    singles player is protected in their Round-1 game.  UnresolvedDoubles
    cannot be protected because their membership is unknown.  Edges
    reference the same stable racquet entry IDs that
    `_build_pod_game_objects` assigns to R1 games, so the solver's
    cross-pool avoidance can act on them.  Bye entries and post-R1 rounds
    remain unprotected: their game participation depends on match results.
    """
    # Gym units: team-sport teams actually assigned to a pool.
    team_lookup = builder._build_core_gym_team_lookup(roster_rows)
    assigned_rows = {
        (str(row.get("Event") or "").strip(), str(row.get("Team ID") or "").strip())
        for row in pool_assignment_rows
        if str(row.get("Pool ID") or "").strip() and str(row.get("Pool Slot") or "").strip()
    }
    gym_units = [
        builder._team_state_to_unit(team_lookup[key])
        for key in team_lookup
        if key in assigned_rows
    ]

    # Racquet units: confirmed doubles pairs with stable entry IDs.
    confirmed_by_div, _unprotected = builder._resolve_pod_doubles(roster_rows, validation_rows)
    racquet_units: List[Dict[str, Any]] = []
    for entries in confirmed_by_div.values():
        for entry in entries:
            racquet_units.append({
                "unit_id": entry["entry_id"],
                "label": entry["label"],
                "event": entry["sport_type"],
                "participant_ids": set(entry["participant_ids"]),
                "participant_names": entry["participant_names"],
                "primary_sports": entry["primary_sports"],
            })

    # Racquet units: singles entries with stable entry IDs (Issue #164).
    # Entries with no participant ID can never overlap and are skipped.
    singles_by_div = builder._resolve_pod_singles(roster_rows)
    for division_id in sorted(singles_by_div):
        for entry in singles_by_div[division_id]:
            if not entry["participant_ids"]:
                continue
            racquet_units.append({
                "unit_id": entry["entry_id"],
                "label": entry["label"],
                "event": entry["sport_type"],
                "participant_ids": set(entry["participant_ids"]),
                "participant_names": entry["participant_names"],
                "primary_sports": entry["primary_sports"],
            })

    edges: List[Dict[str, Any]] = []
    # (b) team ↔ racquet
    for gym_unit in gym_units:
        for racquet_unit in racquet_units:
            edge = builder._make_shared_athlete_edge(gym_unit, racquet_unit)
            if edge:
                edges.append(edge)
    # (c) racquet ↔ racquet (distinct entries; same player double-entered in
    # one division produces no overlap and is naturally skipped).
    for idx, unit_a in enumerate(racquet_units):
        for unit_b in racquet_units[idx + 1:]:
            edge = builder._make_shared_athlete_edge(unit_a, unit_b)
            if edge:
                edges.append(edge)
    return edges
