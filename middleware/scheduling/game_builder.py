"""game_builder — pool/playoff game-object construction, pool-geometry policy,
and gym resource expansion extracted from ScheduleWorkbookBuilder.

Step 6 of the Issue #152 decomposition. Pure extraction, no behavior changes.

Functions that need builder state take the ``ScheduleWorkbookBuilder``
``builder`` (the original ``self``/``cls``) as their first parameter and
reach everything through it.
"""
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger
from config import (
    SPORT_TYPE,
    SOCCER_ENABLED,
    COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM,
    COURT_ESTIMATE_POOL_GAMES_PER_TEAM,
    COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
    COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME,
    COURT_ESTIMATE_MINUTES_PER_GAME,
    COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
    COURT_ESTIMATE_BC_TEAMS_PER_GAME,
    COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM,
    COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF,
    COURT_ESTIMATE_PLAYOFF_RULES,
    SCHEDULE_SKETCH_SATURDAY_START,
    SCHEDULE_SKETCH_SATURDAY_LAST_GAME,
    SCHEDULE_SKETCH_SUNDAY_START,
    SCHEDULE_SKETCH_SUNDAY_LAST_GAME,
    GYM_RESOURCE_TYPE_BASKETBALL,
    GYM_RESOURCE_TYPE_VOLLEYBALL,
    TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
    TEAM_RESOURCE_TYPE_SOCCER,
)


def _pool_numeric_suffix(value: str, prefix: str) -> int:
    """Extract the trailing numeric suffix from pool or pool-slot labels."""
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.match(rf"^{re.escape(prefix)}(\d+)$", text)
    if match:
        return int(match.group(1))
    return 0

def _bc_no_repeat_triplets(
    builder,
    all_rows: List[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    """Generate BC round-robin triplets across all teams in one global pool.

    Each team appears in exactly COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM triplets.
    No pair of teams is in more than one triplet (the "no same opponent twice"
    rule the user expects from traditional BC Jeopardy format).

    Seeded teams (rows with a non-empty Seed value) are never placed in the
    same triplet as another seeded team, preserving the convention that top
    seeds meet each other only in the playoffs.

    Uses backtracking with a most-constrained-first pivot.  For n ≥ 7 with
    3 games/team a valid schedule always exists; for smaller n the constraint
    cannot be satisfied and the method returns [] with a warning.
    """
    ordered = sorted(
        all_rows,
        key=lambda r: (
            builder._pool_numeric_suffix(str(r.get("Pool ID") or ""), "P"),
            builder._pool_numeric_suffix(str(r.get("Pool Slot") or ""), "T"),
            str(r.get("Team ID") or ""),
        ),
    )
    n = len(ordered)
    gpt = COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM
    if n < COURT_ESTIMATE_BC_TEAMS_PER_GAME:
        return []
    n_games = (n * gpt) // COURT_ESTIMATE_BC_TEAMS_PER_GAME

    # Track which indices correspond to seeded teams so the validity check
    # can reject any triplet that pairs two seeded teams together.
    seeded: set = {
        i for i, r in enumerate(ordered)
        if str(r.get("Seed") or "").strip() not in ("", "0")
    }

    from itertools import combinations as _combinations
    all_triples: List[Tuple[int, int, int]] = list(_combinations(range(n), 3))

    used_pairs: set = set()
    count = [0] * n
    chosen: List[Tuple[int, int, int]] = []

    def _pair(a: int, b: int) -> Tuple[int, int]:
        return (a, b) if a < b else (b, a)

    def _valid(a: int, b: int, c: int) -> bool:
        # Seeded teams must not share a triplet with another seeded team.
        seed_count = (a in seeded) + (b in seeded) + (c in seeded)
        return (
            seed_count <= 1
            and count[a] < gpt and count[b] < gpt and count[c] < gpt
            and _pair(a, b) not in used_pairs
            and _pair(b, c) not in used_pairs
            and _pair(a, c) not in used_pairs
        )

    def _apply(a: int, b: int, c: int) -> None:
        count[a] += 1; count[b] += 1; count[c] += 1
        used_pairs.add(_pair(a, b))
        used_pairs.add(_pair(b, c))
        used_pairs.add(_pair(a, c))
        chosen.append((a, b, c))

    def _undo(a: int, b: int, c: int) -> None:
        count[a] -= 1; count[b] -= 1; count[c] -= 1
        used_pairs.discard(_pair(a, b))
        used_pairs.discard(_pair(b, c))
        used_pairs.discard(_pair(a, c))
        chosen.pop()

    def _solve() -> bool:
        if len(chosen) == n_games:
            return True
        incomplete = [i for i in range(n) if count[i] < gpt]
        pivot = min(incomplete, key=lambda i: count[i])
        for a, b, c in all_triples:
            if pivot not in (a, b, c):
                continue
            if _valid(a, b, c):
                _apply(a, b, c)
                if _solve():
                    return True
                _undo(a, b, c)
        return False

    if not _solve():
        logger.warning(
            "BC: no-repeat triplet schedule is not possible for %d teams "
            "with %d games/team (need n ≥ 7 for 3 games/team). "
            "BC pool games will be omitted.",
            n, gpt,
        )
        return []

    return [tuple(ordered[i] for i in t) for t in chosen]  # type: ignore[return-value]

def _build_assigned_bc_game_objects(
    builder,
    pool_assignment_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return BC queue games and precedence using the assigned BC pool draw.

    All BC teams are treated as a single global pool.  Triplets are generated
    by _bc_no_repeat_triplets so no pair of teams meets more than once before
    the playoffs — equivalent to last year's manually-scheduled 16-team format.
    """
    event_name = SPORT_TYPE["BIBLE_CHALLENGE"]
    prefix = builder._pool_assignment_event_prefix(event_name)
    bc_rows = [
        row
        for row in pool_assignment_rows
        if str(row.get("Event") or "").strip() == event_name
        and str(row.get("Pool ID") or "").strip()
        and str(row.get("Pool Slot") or "").strip()
    ]
    if len(bc_rows) < COURT_ESTIMATE_BC_TEAMS_PER_GAME:
        return [], []

    triplets = builder._bc_no_repeat_triplets(bc_rows)
    if not triplets:
        return [], []

    games: List[Dict[str, Any]] = []
    precedence: List[Dict[str, Any]] = []
    for game_num, trio in enumerate(triplets, start=1):
        solver_team_ids = [
            builder._solver_team_id(event_name, str(row.get("Team ID") or "").strip())
            for row in trio
        ]
        labels = [
            str(row.get("Team Label") or row.get("Team ID") or "").strip()
            for row in trio
        ]
        games.append({
            "game_id": f"{prefix}-RR-{game_num}",
            "event": event_name,
            "stage": "Pool",
            "pool_id": "",
            "round": game_num,
            "team_a_id": solver_team_ids[0],
            "team_b_id": solver_team_ids[1],
            "team_c_id": solver_team_ids[2],
            "team_a_label": labels[0],
            "team_b_label": labels[1],
            "team_c_label": labels[2],
            "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
            "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
            "earliest_slot": None,
            "latest_slot": None,
        })

    if len(bc_rows) >= COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF:
        pool_game_ids = [
            str(game.get("game_id") or "").strip()
            for game in games
            if str(game.get("stage") or "").strip() == "Pool"
        ]
        semi_ids: List[str] = []
        for semi_idx in range(1, 4):
            semi_id = f"{prefix}-Semi-{semi_idx}"
            semi_ids.append(semi_id)
            games.append({
                "game_id": semi_id,
                "event": event_name,
                "stage": "Semi",
                "pool_id": "",
                "round": semi_idx,
                "team_a_id": f"{prefix}-Semi-{semi_idx}-A",
                "team_b_id": f"{prefix}-Semi-{semi_idx}-B",
                "team_c_id": f"{prefix}-Semi-{semi_idx}-C",
                "team_a_label": f"Semi {semi_idx} Qualifier A",
                "team_b_label": f"Semi {semi_idx} Qualifier B",
                "team_c_label": f"Semi {semi_idx} Qualifier C",
                "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
                "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                "earliest_slot": None,
                "latest_slot": None,
            })

        precedence.extend(
            {
                "before_game_id": pool_game_id,
                "after_game_id": semi_id,
                "min_gap_slots": 1,
            }
            for pool_game_id in pool_game_ids
            for semi_id in semi_ids
        )

        final_id = f"{prefix}-Final"
        games.append({
            "game_id": final_id,
            "event": event_name,
            "stage": "Final",
            "pool_id": "",
            "round": 1,
            "team_a_id": f"WIN-{semi_ids[0]}",
            "team_b_id": f"WIN-{semi_ids[1]}",
            "team_c_id": f"WIN-{semi_ids[2]}",
            "team_a_label": "Winner Semi 1",
            "team_b_label": "Winner Semi 2",
            "team_c_label": "Winner Semi 3",
            "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
            "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
            "earliest_slot": None,
            "latest_slot": None,
        })
        precedence.extend(
            {
                "before_game_id": semi_id,
                "after_game_id": final_id,
                "min_gap_slots": 1,
            }
            for semi_id in semi_ids
        )

    return games, precedence

def _build_assigned_soccer_game_objects(
    builder,
    roster_rows: List[Dict[str, Any]],
    pool_assignment_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return Soccer field games plus playoff precedence using the assigned pool draw."""
    if not SOCCER_ENABLED:
        return [], []

    event_name = SPORT_TYPE["SOCCER"]
    prefix = builder._pool_assignment_event_prefix(event_name)
    min_team_size = builder._get_min_team_size(event_name)
    counts = builder._count_estimating_teams(roster_rows, event_name, min_team_size)
    slot_map = builder._pool_assignment_placeholder_map(pool_assignment_rows).get(event_name, {})
    if slot_map:
        n_teams = len(slot_map)
    elif counts["n_estimating"] >= 2:
        n_teams = counts["n_estimating"]
    else:
        return [], []

    gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(
        event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM
    )
    mpg = COURT_ESTIMATE_MINUTES_PER_GAME.get(
        event_name, COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
    )

    games: List[Dict[str, Any]] = []
    precedence: List[Dict[str, Any]] = []
    pool_pairs = builder._make_pool_game_pairs(prefix, n_teams, gpg)
    for pair_idx, (team_a_id, team_b_id, pool_id) in enumerate(pool_pairs, start=1):
        team_a_meta = slot_map.get(team_a_id)
        team_b_meta = slot_map.get(team_b_id)
        if slot_map and (team_a_meta is None or team_b_meta is None):
            logger.warning(
                f"Pool-assignment map for event '{event_name}' is missing "
                f"{team_a_id!r} or {team_b_id!r}; falling back to placeholders."
            )
        games.append({
            "game_id": f"{prefix}-{pair_idx:02d}",
            "event": event_name,
            "stage": "Pool",
            "pool_id": pool_id,
            "round": pair_idx,
            "team_a_id": (
                team_a_meta["solver_team_id"] if team_a_meta is not None else team_a_id
            ),
            "team_b_id": (
                team_b_meta["solver_team_id"] if team_b_meta is not None else team_b_id
            ),
            "team_a_label": (
                team_a_meta["display_label"] if team_a_meta is not None else team_a_id
            ),
            "team_b_label": (
                team_b_meta["display_label"] if team_b_meta is not None else team_b_id
            ),
            "duration_minutes": mpg,
            "resource_type": TEAM_RESOURCE_TYPE_SOCCER,
            "earliest_slot": None,
            "latest_slot": None,
        })

    playoff_teams = builder._get_playoff_teams_for_event(event_name, n_teams)
    if playoff_teams >= 4:
        pool_game_ids = [str(game.get("game_id") or "").strip() for game in games]
        semi_ids = [f"{prefix}-Semi-1", f"{prefix}-Semi-2"]
        semi_seed_pairs = [("Seed 1", "Seed 4"), ("Seed 2", "Seed 3")]
        for semi_idx, (semi_id, labels) in enumerate(zip(semi_ids, semi_seed_pairs), start=1):
            games.append({
                "game_id": semi_id,
                "event": event_name,
                "stage": "Semi",
                "pool_id": "",
                "round": semi_idx,
                "team_a_id": f"{prefix}-Seed-{semi_idx}",
                "team_b_id": f"{prefix}-Seed-{5 - semi_idx}",
                "team_a_label": labels[0],
                "team_b_label": labels[1],
                "duration_minutes": mpg,
                "resource_type": TEAM_RESOURCE_TYPE_SOCCER,
                "earliest_slot": None,
                "latest_slot": None,
            })

        precedence.extend(
            {
                "before_game_id": pool_game_id,
                "after_game_id": semi_id,
                "min_gap_slots": 1,
            }
            for pool_game_id in pool_game_ids
            for semi_id in semi_ids
        )

        final_id = f"{prefix}-Final"
        games.append({
            "game_id": final_id,
            "event": event_name,
            "stage": "Final",
            "pool_id": "",
            "round": 1,
            "team_a_id": f"WIN-{semi_ids[0]}",
            "team_b_id": f"WIN-{semi_ids[1]}",
            "team_a_label": "Winner Semi 1",
            "team_b_label": "Winner Semi 2",
            "duration_minutes": mpg,
            "resource_type": TEAM_RESOURCE_TYPE_SOCCER,
            "earliest_slot": None,
            "latest_slot": None,
        })
        precedence.extend(
            {
                "before_game_id": semi_id,
                "after_game_id": final_id,
                "min_gap_slots": 1,
            }
            for semi_id in semi_ids
        )
        if COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME:
            third_id = f"{prefix}-3rd-Place"
            games.append({
                "game_id": third_id,
                "event": event_name,
                "stage": "3rd",
                "pool_id": "",
                "round": 1,
                "team_a_id": f"LOS-{semi_ids[0]}",
                "team_b_id": f"LOS-{semi_ids[1]}",
                "team_a_label": "Loser Semi 1",
                "team_b_label": "Loser Semi 2",
                "duration_minutes": mpg,
                "resource_type": TEAM_RESOURCE_TYPE_SOCCER,
                "earliest_slot": None,
                "latest_slot": None,
            })
            precedence.extend(
                {
                    "before_game_id": semi_id,
                    "after_game_id": third_id,
                    "min_gap_slots": 1,
                }
                for semi_id in semi_ids
            )

    return games, precedence

def _build_single_elim_playoff(
    builder,
    event_name: str,
    prefix: str,
    playoff_teams: int,
    pool_game_ids: List[str],
    extra_fields: Dict[str, Any],
    include_third: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build single-elimination playoff games + precedence for a 4- or 8-team bracket.

    Seed pairings (highest seed plays lowest):
      4 teams: Semi-1 = Seed 1 vs Seed 4; Semi-2 = Seed 2 vs Seed 3
      8 teams: QF-1=S1vS8, QF-2=S4vS5, QF-3=S2vS7, QF-4=S3vS6;
               Semi-1 = WIN-QF-1 vs WIN-QF-2; Semi-2 = WIN-QF-3 vs WIN-QF-4
    Final = WIN-Semi-1 vs WIN-Semi-2; 3rd = LOS-Semi-1 vs LOS-Semi-2 (when
    include_third).  Precedence wires Pool→QF (if any)→Semi→Final/3rd with a
    one-slot gap between rounds.  Returns ([], []) for unsupported sizes.

    ``extra_fields`` is merged into each generated game dict so callers can
    attach sport-specific fields (resource_type, duration_minutes, solver_pool).
    """
    if playoff_teams not in (4, 8):
        return [], []

    games: List[Dict[str, Any]] = []
    precedence: List[Dict[str, Any]] = []

    semi_ids = [f"{prefix}-Semi-1", f"{prefix}-Semi-2"]

    if playoff_teams == 8:
        qf_ids = [f"{prefix}-QF-{i}" for i in range(1, 5)]
        qf_seeds = [(1, 8), (4, 5), (2, 7), (3, 6)]
        for qf_idx, (qf_id, (seed_a, seed_b)) in enumerate(
            zip(qf_ids, qf_seeds), start=1
        ):
            qf_game = {
                "game_id": qf_id,
                "event": event_name,
                "stage": "QF",
                "pool_id": "",
                "round": qf_idx,
                "team_a_id": f"{prefix}-Seed-{seed_a}",
                "team_b_id": f"{prefix}-Seed-{seed_b}",
                "team_a_label": f"Seed {seed_a}",
                "team_b_label": f"Seed {seed_b}",
            }
            qf_game.update(extra_fields)
            games.append(qf_game)
        precedence.extend(
            {"before_game_id": pid, "after_game_id": qid, "min_gap_slots": 1}
            for pid in pool_game_ids for qid in qf_ids
        )
        precedence.extend([
            {"before_game_id": qf_ids[0], "after_game_id": semi_ids[0], "min_gap_slots": 2},
            {"before_game_id": qf_ids[1], "after_game_id": semi_ids[0], "min_gap_slots": 2},
            {"before_game_id": qf_ids[2], "after_game_id": semi_ids[1], "min_gap_slots": 2},
            {"before_game_id": qf_ids[3], "after_game_id": semi_ids[1], "min_gap_slots": 2},
        ])
        semi_team_pairs = [
            (f"WIN-{qf_ids[0]}", f"WIN-{qf_ids[1]}", "Winner QF-1", "Winner QF-2"),
            (f"WIN-{qf_ids[2]}", f"WIN-{qf_ids[3]}", "Winner QF-3", "Winner QF-4"),
        ]
    else:
        semi_team_pairs = [
            (f"{prefix}-Seed-1", f"{prefix}-Seed-4", "Seed 1", "Seed 4"),
            (f"{prefix}-Seed-2", f"{prefix}-Seed-3", "Seed 2", "Seed 3"),
        ]
        precedence.extend(
            {"before_game_id": pid, "after_game_id": sid, "min_gap_slots": 1}
            for pid in pool_game_ids for sid in semi_ids
        )

    for semi_idx, (semi_id, (team_a, team_b, label_a, label_b)) in enumerate(
        zip(semi_ids, semi_team_pairs), start=1
    ):
        semi_game = {
            "game_id": semi_id,
            "event": event_name,
            "stage": "Semi",
            "pool_id": "",
            "round": semi_idx,
            "team_a_id": team_a,
            "team_b_id": team_b,
            "team_a_label": label_a,
            "team_b_label": label_b,
        }
        semi_game.update(extra_fields)
        games.append(semi_game)

    final_id = f"{prefix}-Final"
    final_game = {
        "game_id": final_id,
        "event": event_name,
        "stage": "Final",
        "pool_id": "",
        "round": 1,
        "team_a_id": f"WIN-{semi_ids[0]}",
        "team_b_id": f"WIN-{semi_ids[1]}",
        "team_a_label": "Winner Semi 1",
        "team_b_label": "Winner Semi 2",
    }
    final_game.update(extra_fields)
    games.append(final_game)
    precedence.extend(
        {"before_game_id": sid, "after_game_id": final_id, "min_gap_slots": 2}
        for sid in semi_ids
    )

    if include_third:
        third_id = f"{prefix}-3rd-Place"
        third_game = {
            "game_id": third_id,
            "event": event_name,
            "stage": "3rd",
            "pool_id": "",
            "round": 1,
            "team_a_id": f"LOS-{semi_ids[0]}",
            "team_b_id": f"LOS-{semi_ids[1]}",
            "team_a_label": "Loser Semi 1",
            "team_b_label": "Loser Semi 2",
        }
        third_game.update(extra_fields)
        games.append(third_game)
        precedence.extend(
            {"before_game_id": sid, "after_game_id": third_id, "min_gap_slots": 2}
            for sid in semi_ids
        )

    return games, precedence

def _build_assigned_gym_game_objects(
    builder,
    roster_rows: List[Dict[str, Any]],
    pool_assignment_rows: List[Dict[str, Any]],
    allow_placeholder_fallback: bool = True,
    excluded_events: Optional[set[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return gym games (pool + auto-generated playoffs) plus precedence.

    Pool games come from the seeded draw in ``pool_assignment_rows``.  Playoff
    games (QF/Semi/Final/3rd) are auto-generated based on the playoff-team count
    and wired into precedence so the solver can place them in any open slot.
    Operators who want a specific game pinned to a court/time still do that
    via the Playoff-Slots tab in venue_input.xlsx — those rows override the
    auto-generated assignments via merge_playoff_slot_assignments.
    """
    sport_defs = [
        (SPORT_TYPE["BASKETBALL"], "BBM", GYM_RESOURCE_TYPE_BASKETBALL),
        (SPORT_TYPE["VOLLEYBALL_MEN"], "VBM", GYM_RESOURCE_TYPE_VOLLEYBALL),
        (SPORT_TYPE["VOLLEYBALL_WOMEN"], "VBW", GYM_RESOURCE_TYPE_VOLLEYBALL),
    ]
    mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
    games: List[Dict[str, Any]] = []
    precedence: List[Dict[str, Any]] = []
    placeholder_map_by_event = builder._pool_assignment_placeholder_map(pool_assignment_rows)
    excluded_events = excluded_events or set()

    for event_name, prefix, resource_type in sport_defs:
        if event_name in excluded_events:
            continue
        min_team_size = builder._get_min_team_size(event_name)
        counts = builder._count_estimating_teams(roster_rows, event_name, min_team_size)
        slot_map = placeholder_map_by_event.get(event_name, {})
        if slot_map:
            n_teams = len(slot_map)
        elif counts["n_estimating"] >= 2:
            n_teams = counts["n_estimating"]
        elif allow_placeholder_fallback:
            n_teams = 8
        else:
            continue

        gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(
            event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM
        )
        pool_pairs = builder._make_pool_game_pairs(prefix, n_teams, gpg)
        sport_pool_game_ids: List[str] = []
        for pair_idx, (team_a_id, team_b_id, pool_id) in enumerate(pool_pairs, start=1):
            team_a_meta = slot_map.get(team_a_id)
            team_b_meta = slot_map.get(team_b_id)
            if slot_map and (team_a_meta is None or team_b_meta is None):
                logger.warning(
                    f"Pool-assignment map for event '{event_name}' is missing "
                    f"{team_a_id!r} or {team_b_id!r}; falling back to placeholders."
                )
            pool_game_id = f"{prefix}-{pair_idx:02d}"
            sport_pool_game_ids.append(pool_game_id)
            games.append({
                "game_id": pool_game_id,
                "event": event_name,
                "stage": "Pool",
                "pool_id": pool_id,
                "round": pair_idx,
                "team_a_id": (
                    team_a_meta["solver_team_id"] if team_a_meta is not None else team_a_id
                ),
                "team_b_id": (
                    team_b_meta["solver_team_id"] if team_b_meta is not None else team_b_id
                ),
                "team_a_label": (
                    team_a_meta["display_label"] if team_a_meta is not None else team_a_id
                ),
                "team_b_label": (
                    team_b_meta["display_label"] if team_b_meta is not None else team_b_id
                ),
                "duration_minutes": mpg,
                "resource_type": resource_type,
                "solver_pool": builder._GYM_CORE_SOLVER_POOL,
                "earliest_slot": None,
                "latest_slot": None,
            })

        playoff_teams = builder._get_playoff_teams_for_event(event_name, n_teams)
        if playoff_teams >= 4:
            playoff_games, playoff_precedence = builder._build_single_elim_playoff(
                event_name=event_name,
                prefix=prefix,
                playoff_teams=playoff_teams,
                pool_game_ids=sport_pool_game_ids,
                extra_fields={
                    "duration_minutes": mpg,
                    "resource_type": resource_type,
                    "solver_pool": builder._GYM_CORE_SOLVER_POOL,
                    "earliest_slot": None,
                    "latest_slot": None,
                },
                include_third=COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME,
            )
            games.extend(playoff_games)
            precedence.extend(playoff_precedence)

    return games, precedence

def _build_manual_team_sport_game_objects(
    builder,
    manual_matchup_payload: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], set[str], Optional[Dict[str, Any]]]:
    """Return imported team-sport pool games plus generated playoff edges.

    The manual sidecar owns pool-game pairings only. Playoff game objects
    stay generated from the imported pool-game list so Playoff-Slots and
    precedence rules continue to behave like the normal team-sport path.
    """
    if not manual_matchup_payload:
        return [], [], set(), None

    sidecar_errors = (
        manual_matchup_payload.get("validation", {}) or {}
    ).get("errors", [])
    if sidecar_errors:
        raise ValueError(
            "Manual team matchup sidecar has validation errors; rerun "
            "import-team-matchups and fix the workbook before exporting."
        )

    games_by_event: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for game in manual_matchup_payload.get("games", []) or []:
        if not isinstance(game, dict):
            continue
        event_name = str(game.get("event") or "").strip()
        if not event_name:
            continue
        games_by_event[event_name].append(dict(game))

    imported_games: List[Dict[str, Any]] = []
    precedence: List[Dict[str, Any]] = []
    imported_events: set[str] = set()

    event_metadata = {
        str(event.get("event") or "").strip(): event
        for event in manual_matchup_payload.get("events", []) or []
        if isinstance(event, dict)
    }

    for event_name, event_games in games_by_event.items():
        imported_events.add(event_name)
        imported_games.extend(event_games)
        event_meta = event_metadata.get(event_name, {})
        prefix = str(event_meta.get("prefix") or builder._pool_assignment_event_prefix(event_name))
        resource_type = str(event_meta.get("resource_type") or "")
        duration = int(
            COURT_ESTIMATE_MINUTES_PER_GAME.get(
                event_name,
                COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
            )
        )
        team_codes = {
            str(game.get(label_key) or "").strip()
            for game in event_games
            for label_key in ("team_a_label", "team_b_label", "team_c_label")
            if str(game.get(label_key) or "").strip()
        }
        pool_game_ids = [
            str(game.get("game_id") or "").strip()
            for game in event_games
            if str(game.get("game_id") or "").strip()
        ]
        if event_name == SPORT_TYPE["BIBLE_CHALLENGE"]:
            if len(team_codes) >= COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF:
                semi_ids: List[str] = []
                for semi_idx in range(1, 4):
                    semi_id = f"{prefix}-Semi-{semi_idx}"
                    semi_ids.append(semi_id)
                    imported_games.append({
                        "game_id": semi_id,
                        "event": event_name,
                        "stage": "Semi",
                        "pool_id": "",
                        "round": semi_idx,
                        "team_a_id": f"{prefix}-Semi-{semi_idx}-A",
                        "team_b_id": f"{prefix}-Semi-{semi_idx}-B",
                        "team_c_id": f"{prefix}-Semi-{semi_idx}-C",
                        "team_a_label": f"Semi {semi_idx} Qualifier A",
                        "team_b_label": f"Semi {semi_idx} Qualifier B",
                        "team_c_label": f"Semi {semi_idx} Qualifier C",
                        "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
                        "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                        "earliest_slot": None,
                        "latest_slot": None,
                    })

                precedence.extend(
                    {
                        "before_game_id": pool_game_id,
                        "after_game_id": semi_id,
                        "min_gap_slots": 1,
                    }
                    for pool_game_id in pool_game_ids
                    for semi_id in semi_ids
                )

                final_id = f"{prefix}-Final"
                imported_games.append({
                    "game_id": final_id,
                    "event": event_name,
                    "stage": "Final",
                    "pool_id": "",
                    "round": 1,
                    "team_a_id": f"WIN-{semi_ids[0]}",
                    "team_b_id": f"WIN-{semi_ids[1]}",
                    "team_c_id": f"WIN-{semi_ids[2]}",
                    "team_a_label": "Winner Semi 1",
                    "team_b_label": "Winner Semi 2",
                    "team_c_label": "Winner Semi 3",
                    "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
                    "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                    "earliest_slot": None,
                    "latest_slot": None,
                })
                precedence.extend(
                    {
                        "before_game_id": semi_id,
                        "after_game_id": final_id,
                        "min_gap_slots": 1,
                    }
                    for semi_id in semi_ids
                )
            continue

        playoff_teams = builder._get_playoff_teams_for_event(event_name, len(team_codes))
        if playoff_teams >= 4:
            extra_fields: Dict[str, Any] = {
                "duration_minutes": duration,
                "resource_type": resource_type,
                "earliest_slot": None,
                "latest_slot": None,
            }
            solver_pools = [
                str(game.get("solver_pool") or "").strip()
                for game in event_games
                if str(game.get("solver_pool") or "").strip()
            ]
            if solver_pools:
                extra_fields["solver_pool"] = solver_pools[0]
            playoff_games, playoff_precedence = builder._build_single_elim_playoff(
                event_name=event_name,
                prefix=prefix,
                playoff_teams=playoff_teams,
                pool_game_ids=pool_game_ids,
                extra_fields=extra_fields,
                include_third=COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME,
            )
            imported_games.extend(playoff_games)
            precedence.extend(playoff_precedence)

    summary = {
        "source_workbook": manual_matchup_payload.get("source_workbook"),
        "imported_at": manual_matchup_payload.get("imported_at"),
        "active_sheets": manual_matchup_payload.get("active_sheets", []),
        "events": [
            {
                "sheet_name": event.get("sheet_name"),
                "event": event.get("event"),
                "game_count": len(event.get("games", []) or []),
                "expected_games_per_team": event.get("expected_games_per_team"),
                "team_game_counts": event.get("team_game_counts", {}),
                "skipped_byes": event.get("skipped_byes", []),
                "count_warnings": event.get("count_warnings", []),
            }
            for event in manual_matchup_payload.get("events", []) or []
            if isinstance(event, dict)
        ],
        "validation": manual_matchup_payload.get("validation", {}),
    }
    return imported_games, precedence, imported_events, summary

def _build_gym_game_objects(
    builder,
    roster_rows: List[Dict[str, Any]],
    allow_placeholder_fallback: bool = True,
) -> List[Dict[str, Any]]:
    """Return pool-play game placeholder dicts for gym sports (Basketball, VB Men, VB Women).

    Pool games carry stable placeholder team IDs (e.g. BBM-P1-T1, BBM-P1-T2)
    and non-empty pool_id values so the solver can enforce team-overlap and
    min-rest constraints even before final church assignments are known.

    Playoff games (QF/Semi/Final/3rd) are pre-assigned via the Playoff-Slots
    tab in venue_input.xlsx and are not included here.

    When allow_placeholder_fallback is True, sports with fewer than two
    estimating teams fall back to the legacy 8-team planning scaffold so
    offline sketching still works without venue data. When False, those
    sports are omitted from the solver input entirely.
    """
    sport_defs = [
        (SPORT_TYPE["BASKETBALL"],       "BBM", GYM_RESOURCE_TYPE_BASKETBALL),
        (SPORT_TYPE["VOLLEYBALL_MEN"],   "VBM", GYM_RESOURCE_TYPE_VOLLEYBALL),
        (SPORT_TYPE["VOLLEYBALL_WOMEN"], "VBW", GYM_RESOURCE_TYPE_VOLLEYBALL),
    ]
    mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
    games: List[Dict[str, Any]] = []

    for event_name, prefix, resource_type in sport_defs:
        min_sz = builder._get_min_team_size(event_name)
        counts = builder._count_estimating_teams(roster_rows, event_name, min_sz)
        if counts["n_estimating"] >= 2:
            n_teams = counts["n_estimating"]
        elif allow_placeholder_fallback:
            n_teams = 8
        else:
            continue
        gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(
            event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM
        )

        # Pool games — stable team IDs and non-empty pool_id
        pool_pairs = builder._make_pool_game_pairs(prefix, n_teams, gpg)
        for pair_idx, (team_a_id, team_b_id, pool_id) in enumerate(pool_pairs, start=1):
            games.append({
                "game_id": f"{prefix}-{pair_idx:02d}",
                "event": event_name,
                "stage": "Pool",
                "pool_id": pool_id,
                "round": pair_idx,
                "team_a_id": team_a_id,
                "team_b_id": team_b_id,
                "duration_minutes": mpg,
                "resource_type": resource_type,
                "earliest_slot": None,
                "latest_slot":   None,
            })

    return games

def _build_pod_game_objects(
    builder,
    roster_rows: List[Dict[str, Any]],
    validation_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (games, precedence) for single-elimination brackets for pod (racquet) sports.

    Uses planning_entries (confirmed + provisional) from Pod-Divisions.
    Elimination games per division = planning_entries − 1, plus an optional
    third-place game when two Semis are played.
    Divisions with fewer than 2 planning entries are skipped.

    Late rounds receive stage-aware IDs so operators can pin them in
    Playoff-Slots (Issue #130):
      - ``-QF-N``   quarter-final games (bracket size >= 8)
      - ``-Semi-N`` semi-final games
      - ``-Final``  championship game
      - ``-3rd-Place`` third-place game when enabled and two Semis are played
    Early rounds keep sequential numeric IDs (``-01``, ``-02``, ...).

    Precedence edges enforce round ordering: every game in round R must
    complete (min_gap_slots=1) before any game in round R+1 can start.

    For doubles divisions, the first ``floor(c / 2)`` games (where ``c`` is
    the number of *confirmed* pairs) are real Round-1 matchups carrying the
    stable entry IDs from `_resolve_pod_doubles`, so the solver can keep a
    shared athlete's R1 game off another sport's slot (Issue #158,
    Decision 1).  Singles divisions get the same Round-1 protection using
    the ``-S{nn}`` entry IDs from `_resolve_pod_singles` (Issue #164).
    Later-round games, bye entries, and any games beyond the known
    matchups keep ``team_a_id``/``team_b_id`` of ``None`` because their
    participants are not knowable until earlier rounds are played.
    """
    div_rows = builder._build_pod_divisions_rows(roster_rows, validation_rows)
    confirmed_by_div, _unprotected = builder._resolve_pod_doubles(roster_rows, validation_rows)
    singles_by_div = builder._resolve_pod_singles(roster_rows)
    all_games: List[Dict[str, Any]] = []
    all_precedence: List[Dict[str, Any]] = []

    for div in div_rows:
        if div["division_status"] in ("Empty", "AnomalyOnly"):
            continue
        fmt_class = builder._pod_format_class(str(div.get("sport_format") or ""))
        if fmt_class == "singles":
            n_entries = len(singles_by_div.get(div["division_id"], []))
        else:
            n_entries = div["planning_entries"]
        if n_entries < 2:
            continue
        division_id = div["division_id"]
        sport_type = div["sport_type"]
        resource_type = div["resource_type"]
        mpg = div["minutes_per_game"]

        # Bracket size P = smallest power of 2 >= n_entries.
        P = 1
        while P < n_entries:
            P <<= 1
        n_rounds = P.bit_length() - 1  # log2(P)

        # Stage name for each bracket round (from the Final backward).
        def _round_stage(r: int, _nr: int = n_rounds) -> str:
            rounds_from_end = _nr - r
            if rounds_from_end == 0:
                return "Final"
            if rounds_from_end == 1:
                return "Semi"
            if rounds_from_end == 2:
                return "QF"
            return f"R{r}"  # pre-QF rounds for very large brackets

        # Round-1 matchup assignment for divisions with known entries —
        # confirmed doubles pairs (Issue #158) and all singles players
        # (Issue #164).  Bracket math mirrors the outer P computation so
        # byes are placed correctly.
        r1_matchups: List[Tuple[Optional[str], Optional[str]]] = []
        if fmt_class == "doubles":
            entries = confirmed_by_div.get(division_id, [])
        elif fmt_class == "singles":
            entries = singles_by_div.get(division_id, [])
        else:
            entries = []
        if entries and n_entries >= 2:
            byes = P - n_entries
            r1_match_count = (n_entries - byes) // 2
            planned_entry_ids: List[Optional[str]] = [
                entry["entry_id"] for entry in entries[:n_entries]
            ]
            planned_entry_ids.extend([None] * (n_entries - len(planned_entry_ids)))
            r1_starters = planned_entry_ids[n_entries - 2 * r1_match_count:]
            for k in range(0, 2 * r1_match_count, 2):
                r1_matchups.append((r1_starters[k], r1_starters[k + 1]))

        # Generate games round by round.
        # Round 1 actual games: n_entries - P//2  (byes happen only in round 1)
        # Round r > 1: P // 2^r games  (no more byes)
        div_games: List[Dict[str, Any]] = []
        games_by_round: Dict[int, List[str]] = {}
        stage_counters: Dict[str, int] = {}
        early_seq = 0   # sequential counter for pre-QF numeric IDs
        game_idx = 0    # total games generated (for doubles matchup assignment)

        for r in range(1, n_rounds + 1):
            stage = _round_stage(r)
            n_games = (
                max(0, n_entries - P // 2) if r == 1 else P // (2 ** r)
            )
            stage_counters.setdefault(stage, 0)
            games_by_round[r] = []

            for _ in range(n_games):
                stage_counters[stage] += 1
                cnt = stage_counters[stage]

                if stage == "Final":
                    game_id = f"{division_id}-Final"
                elif stage in ("Semi", "QF"):
                    game_id = f"{division_id}-{stage}-{cnt}"
                else:
                    early_seq += 1
                    game_id = f"{division_id}-{early_seq:02d}"

                games_by_round[r].append(game_id)

                if game_idx < len(r1_matchups):
                    team_a_id, team_b_id = r1_matchups[game_idx]
                else:
                    team_a_id, team_b_id = None, None
                game_idx += 1

                div_games.append({
                    "game_id":              game_id,
                    "division_id":          division_id,
                    "division_entry_count": n_entries,
                    "event":                sport_type,
                    "stage":                stage,
                    "pool_id":              "",
                    "round":                r,
                    "team_a_id":            team_a_id,
                    "team_b_id":            team_b_id,
                    "duration_minutes":     mpg,
                    "resource_type":        resource_type,
                    "earliest_slot":        None,
                    "latest_slot":          None,
                })

        # Precedence: every game in round R must finish before round R+1 starts.
        for r in range(1, n_rounds):
            for before_id in games_by_round[r]:
                for after_id in games_by_round[r + 1]:
                    all_precedence.append({
                        "before_game_id": before_id,
                        "after_game_id":  after_id,
                        "min_gap_slots":  1,
                    })

        semi_round = n_rounds - 1
        semi_ids = games_by_round.get(semi_round, [])
        if (
            COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME
            and len(semi_ids) == 2
        ):
            third_id = f"{division_id}-3rd-Place"
            div_games.append({
                "game_id":              third_id,
                "division_id":          division_id,
                "division_entry_count": n_entries,
                "event":                sport_type,
                "stage":                "3rd",
                "pool_id":              "",
                "round":                n_rounds,
                "team_a_id":            None,
                "team_b_id":            None,
                "duration_minutes":     mpg,
                "resource_type":        resource_type,
                "earliest_slot":        None,
                "latest_slot":          None,
            })
            all_precedence.extend(
                {
                    "before_game_id": semi_id,
                    "after_game_id": third_id,
                    "min_gap_slots": 1,
                }
                for semi_id in semi_ids
            )

        all_games.extend(div_games)

    return all_games, all_precedence

def _build_gym_resource_objects(
    n_basketball: int = 2,
    n_volleyball: int = 2,
) -> List[Dict[str, Any]]:
    """Fallback gym resource builder (no venue_input.xlsx).

    Generates n_basketball + n_volleyball resources per session across four
    sessions (Sat-1, Sun-1, Sat-2, Sun-2) using SCHEDULE_SKETCH_* time
    windows.  Basketball courts are numbered first within each session,
    volleyball courts second.
    """
    mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
    close_sat = f"{SCHEDULE_SKETCH_SATURDAY_LAST_GAME + mpg // 60:02d}:00"
    close_sun = f"{SCHEDULE_SKETCH_SUNDAY_LAST_GAME + mpg // 60:02d}:00"
    sessions = [
        ("Sat-1", f"{SCHEDULE_SKETCH_SATURDAY_START:02d}:00", close_sat),
        ("Sun-1", f"{SCHEDULE_SKETCH_SUNDAY_START:02d}:00",   close_sun),
        ("Sat-2", f"{SCHEDULE_SKETCH_SATURDAY_START:02d}:00", close_sat),
        ("Sun-2", f"{SCHEDULE_SKETCH_SUNDAY_START:02d}:00",   close_sun),
    ]
    type_blocks = [
        (GYM_RESOURCE_TYPE_BASKETBALL, n_basketball),
        (GYM_RESOURCE_TYPE_VOLLEYBALL, n_volleyball),
    ]
    resources: List[Dict[str, Any]] = []
    for day_label, open_time, close_time in sessions:
        c = 0
        for rtype, count in type_blocks:
            for local in range(1, count + 1):
                c += 1
                resources.append({
                    "resource_id":     f"GYM-{day_label}-{c}",
                    "resource_type":   rtype,
                    "label":           f"Court-{c}",
                    "day":             day_label,
                    "open_time":       open_time,
                    "close_time":      close_time,
                    "slot_minutes":    mpg,
                    "exclusive_group": "",
                })
    return resources

def _build_gym_resources_from_allocator(decisions) -> List[Dict[str, Any]]:
    """Convert Stage-A AllocationDecision objects into schedule_input resources.

    Courts within each decision are numbered per-day sequentially so that
    resource IDs remain stable across re-runs with the same venue configuration.
    """
    resources: List[Dict[str, Any]] = []
    court_counter: Dict[str, int] = {}  # day → running counter

    # Sort for ID stability: day order, then open_time, then gym name.
    from gym_allocator import _day_sort_key
    sorted_decisions = sorted(
        decisions,
        key=lambda d: (_day_sort_key(d.day), d.open_time, d.gym_name),
    )
    for decision in sorted_decisions:
        day = decision.day
        for local in range(1, decision.courts + 1):
            court_counter[day] = court_counter.get(day, 0) + 1
            n = court_counter[day]
            resources.append({
                "resource_id":     f"GYM-{day}-{n}",
                "resource_type":   decision.mode,
                "label":           f"Court-{local}",
                "day":             day,
                "open_time":       decision.open_time,
                "close_time":      decision.close_time,
                "slot_minutes":    decision.slot_minutes,
                "venue_name":      decision.gym_name,
                "exclusive_group": decision.gym_name,
            })
    return resources

def _two_game_pool_sizes(n_teams: int) -> List[int]:
    """Return deterministic pool sizes for the normalized 2-game/team policy."""
    if n_teams < 2:
        return []
    if n_teams in (2, 3, 4, 5):
        return [n_teams]

    for n_fours in range(n_teams // 4, -1, -1):
        remainder = n_teams - (4 * n_fours)
        if remainder >= 0 and remainder % 3 == 0:
            return ([4] * n_fours) + ([3] * (remainder // 3))

    raise ValueError(f"Unable to build normalized 2-game pools for n_teams={n_teams}")

def _three_game_even_pool_sizes(n_teams: int) -> List[int]:
    """Return exact 3-game/team pool sizes for even team counts."""
    if n_teams < 4 or n_teams % 2:
        raise ValueError(
            f"Exact normalized 3-game pools require an even team count >= 4; got {n_teams}"
        )

    for n_sixes in range(n_teams // 6, -1, -1):
        remainder = n_teams - (6 * n_sixes)
        if remainder >= 0 and remainder % 4 == 0:
            return ([6] * n_sixes) + ([4] * (remainder // 4))

    raise ValueError(f"Unable to build normalized 3-game pools for n_teams={n_teams}")

def _three_game_pool_sizes(n_teams: int) -> List[int]:
    """Return deterministic pool sizes for the supported 3-game/team policy."""
    if n_teams < 2:
        return []
    if n_teams in (2, 3, 4, 5, 7):
        return [n_teams]
    if n_teams % 2 == 0:
        return _three_game_even_pool_sizes(n_teams)
    if n_teams >= 9:
        return _three_game_even_pool_sizes(n_teams - 5) + [5]

    raise ValueError(f"Unable to build normalized 3-game pools for n_teams={n_teams}")

def _format_pool_games_per_team(value: float) -> Any:
    """Return ints when whole, otherwise a rounded operator-facing float."""
    rounded = round(float(value), 2)
    return int(rounded) if float(rounded).is_integer() else rounded

def _format_pool_composition(pool_sizes: List[int], gpg: int) -> str:
    """Return the operator-facing pool composition summary string."""
    if not pool_sizes:
        return ""

    base = " + ".join(str(size) for size in pool_sizes)
    notes: List[str] = []

    if gpg == 2:
        if 5 in pool_sizes:
            notes.append("5-team pools include one bye per round")
    elif gpg == 3:
        if any(size in (2, 3) for size in pool_sizes):
            notes.append("small pools cannot reach the full 3-game target")
        if 5 in pool_sizes:
            notes.append("5-team pools give T5 the extra 4th game")
        if 7 in pool_sizes:
            notes.append("7-team pools give T7 the extra 4th game")

    if not notes:
        return base
    return f"{base} ({'; '.join(notes)})"

def _summarize_pool_policy(n_teams: int, gpg: int) -> Dict[str, Any]:
    """Return operator-facing metadata for the current pool-generation policy."""
    if n_teams < 2:
        return {
            "target_pool_games_per_team": gpg,
            "actual_pool_games_per_team": 0,
            "pool_composition": "",
            "bye_slots": 0,
            "actual_pool_games": 0,
        }

    if gpg == 2:
        pool_sizes = _two_game_pool_sizes(n_teams)
        games_by_pool_size = {2: 1, 3: 3, 4: 4, 5: 5}
        actual_pool_games = sum(games_by_pool_size[size] for size in pool_sizes)
        actual_pool_games_per_team = 1 if n_teams == 2 else 2
        bye_slots = 5 * pool_sizes.count(5)
    elif gpg == 3:
        pool_sizes = _three_game_pool_sizes(n_teams)
        games_by_pool_size = {2: 1, 3: 3, 4: 6, 5: 8, 6: 9, 7: 11}
        actual_pool_games = sum(games_by_pool_size[size] for size in pool_sizes)
        actual_pool_games_per_team = _format_pool_games_per_team(
            (2 * actual_pool_games) / n_teams
        )
        bye_slots = 0
    else:
        raise ValueError(
            f"Unsupported team-sport pool target {gpg}. Only 2 and 3 games/team are supported."
        )

    return {
        "target_pool_games_per_team": gpg,
        "actual_pool_games_per_team": actual_pool_games_per_team,
        "pool_composition": _format_pool_composition(pool_sizes, gpg),
        "bye_slots": bye_slots,
        "actual_pool_games": actual_pool_games,
    }

def _make_legacy_pool_game_pairs(
    prefix: str, n_teams: int, gpg: int
) -> List[Tuple[str, str, str]]:
    """Legacy balanced round-robin fallback for non-default pool-game targets."""
    if n_teams < 2:
        return []

    target_pool_size = max(2, gpg + 1)
    n_pools = max(1, n_teams // target_pool_size)

    pools: List[List[int]] = [[] for _ in range(n_pools)]
    for i in range(n_teams):
        pools[i % n_pools].append(i + 1)

    team_id: Dict[int, str] = {}
    for p_idx, pool_teams in enumerate(pools, start=1):
        for t_idx, team_num in enumerate(pool_teams, start=1):
            team_id[team_num] = f"{prefix}-P{p_idx}-T{t_idx}"

    pairs: List[Tuple[str, str, str]] = []
    for p_idx, pool_teams in enumerate(pools, start=1):
        pool_id = f"P{p_idx}"
        for i in range(len(pool_teams)):
            for j in range(i + 1, len(pool_teams)):
                pairs.append((
                    team_id[pool_teams[i]],
                    team_id[pool_teams[j]],
                    pool_id,
                ))
    return pairs

def _make_pool_game_pairs(
    prefix: str, n_teams: int, gpg: int
) -> List[Tuple[str, str, str]]:
    """Return (team_a_id, team_b_id, pool_id) tuples for pool-play games.

    Supported team-sport planning policies are:

    2-game mode:
    - 2 teams  -> one direct match
    - 3 teams  -> 3-team round robin
    - 4 teams  -> 4-match matrix (every team plays exactly twice)
    - 5 teams  -> 5-match cycle (every team plays exactly twice)
    - 6+ teams -> deterministic composition of 3-team and 4-team pools

    3-game mode:
    - 4 teams  -> 4-team round robin (every team plays exactly three)
    - 6 teams  -> 6-team 3-round matrix (every team plays exactly three)
    - odd team counts may require one 5-team or 7-team pool where the
      highest slot (T5 or T7) receives the extra 4th game

    Any target other than 2 or 3 is rejected loudly.

    Team IDs are stable planning placeholders: {prefix}-P{pool}-T{slot}.
    The same placeholder is reused across all games involving that team,
    allowing the solver to enforce team-overlap and min-rest constraints.
    """
    if n_teams < 2:
        return []

    if gpg == 2:
        template_pairs = {
            2: [(0, 1)],
            3: [(0, 1), (0, 2), (1, 2)],
            4: [(0, 1), (2, 3), (0, 2), (1, 3)],
            5: [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)],
        }
        pool_sizes = _two_game_pool_sizes(n_teams)
    elif gpg == 3:
        template_pairs = {
            2: [(0, 1)],
            3: [(0, 1), (0, 2), (1, 2)],
            4: [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)],
            5: [
                (0, 1), (1, 2), (2, 3), (3, 4), (4, 0),
                (4, 1), (4, 2), (0, 3),
            ],
            6: [
                (0, 5), (1, 4), (2, 3),
                (0, 4), (5, 3), (1, 2),
                (0, 3), (4, 2), (5, 1),
            ],
            7: [
                (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 0),
                (6, 1), (6, 3), (0, 4), (2, 5),
            ],
        }
        pool_sizes = _three_game_pool_sizes(n_teams)
    else:
        raise ValueError(
            f"Unsupported team-sport pool target {gpg}. Only 2 and 3 games/team are supported."
        )

    pairs: List[Tuple[str, str, str]] = []
    for p_idx, pool_size in enumerate(pool_sizes, start=1):
        pool_id = f"P{p_idx}"
        pool_team_ids = [
            f"{prefix}-P{p_idx}-T{slot_idx}"
            for slot_idx in range(1, pool_size + 1)
        ]
        for team_a_idx, team_b_idx in template_pairs[pool_size]:
            pairs.append((
                pool_team_ids[team_a_idx],
                pool_team_ids[team_b_idx],
                pool_id,
            ))
    return pairs

def _make_playoff_ids(
    prefix: str, playoff_teams: int, include_third: bool
) -> Tuple[List[str], List[str]]:
    """Return (early_ids, final_ids) split by which weekend they belong to.

    early_ids  — QF + Semi games, scheduled on 2nd Saturday.
    final_ids  — Final (+ optional 3rd-place), scheduled on 2nd Sunday.

    Bracket size is determined by playoff_teams (from COURT_ESTIMATE_PLAYOFF_RULES):
        0 teams  → no playoff games
        4 teams  → Semi-1, Semi-2 | Final [+ 3rd]
        8 teams  → QF-1…4, Semi-1, Semi-2 | Final [+ 3rd]

    To add a new bracket size (e.g. 16 teams with quarter-finals already
    called Round-of-16), extend the if/elif chain here and add matching
    rows to COURT_ESTIMATE_PLAYOFF_RULES in config.py.
    """
    early_ids: List[str] = []
    if playoff_teams >= 8:
        for i in range(1, 5):
            early_ids.append(f"{prefix}-QF-{i}")
        early_ids.extend([f"{prefix}-Semi-1", f"{prefix}-Semi-2"])
    elif playoff_teams >= 4:
        early_ids.extend([f"{prefix}-Semi-1", f"{prefix}-Semi-2"])

    final_ids: List[str] = []
    if playoff_teams >= 4:
        final_ids.append(f"{prefix}-Final")
        if include_third:
            final_ids.append(f"{prefix}-3rd-Place")
    return early_ids, final_ids
