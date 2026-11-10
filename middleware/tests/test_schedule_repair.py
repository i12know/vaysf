"""Tests for optimize-approved-schedule, the CP-SAT schedule repair (Issue #218)."""
import json

import pytest
from openpyxl import load_workbook

from config import SPORT_TYPE
from schedule_contracts import validate_schedule_output
from scheduling import schedule_repair as sr

pytest.importorskip("ortools")

BB = SPORT_TYPE["BASKETBALL"]
VBM = SPORT_TYPE["VOLLEYBALL_MEN"]
VBW = SPORT_TYPE["VOLLEYBALL_WOMEN"]
BC = SPORT_TYPE["BIBLE_CHALLENGE"]
SOC = SPORT_TYPE["SOCCER"]
TT = SPORT_TYPE["TABLE_TENNIS"]

RESOURCE_TYPE = {
    BB: "Basketball Court",
    VBM: "Volleyball Court",
    VBW: "Volleyball Court",
    BC: "BC Station",
    SOC: "Soccer Field",
    TT: "Table Tennis Table",
}
VENUE = {
    "Basketball Court": "Main Gym",
    "Volleyball Court": "Practice Gym",
    "BC Station": "Library",
    "Soccer Field": "Field",
    "Table Tennis Table": "Chapel",
}


def _court(resource_id, resource_type, label="Court-1", open_time="12:00", close_time="16:00",
           day="Sat-1", slot_minutes=60):
    return {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "label": label,
        "day": day,
        "open_time": open_time,
        "close_time": close_time,
        "slot_minutes": slot_minutes,
        "venue_name": VENUE[resource_type],
        "exclusive_group": VENUE[resource_type],
    }


def _game(key, event, teams, resource_id, slot, **extra):
    row = {
        "game_key": key,
        "event": event,
        "stage": "Pool",
        "resource_type": RESOURCE_TYPE[event],
        "duration_minutes": 60,
        "resource_id": resource_id,
        "scheduled_slot": slot,
        "source_workbook": "approved.xlsx",
        "source_sheet": "Final",
        "source_cell": "B2",
        "raw_source_text": " v ".join(teams),
    }
    for letter, team in zip("abc", teams):
        row[f"team_{letter}_key"] = team
        row[f"team_{letter}_label"] = team.split("::")[-1]
    row.update(extra)
    return row


def _edge(team_a, team_b, primary=0, secondary=1):
    return {
        "team_a_id": team_a,
        "team_b_id": team_b,
        "event_a": "",
        "event_b": "",
        "shared_count": primary + secondary,
        "primary_overlap_count": primary,
        "secondary_only_count": secondary,
        "shared_participant_names": [f"Athlete {i + 1}" for i in range(primary + secondary)],
    }


def _schedule_input(resources, games, edges=(), pins=(), precedence=(), unknown_events=()):
    """schedule_input whose games mirror the baseline (minus `unknown_events`)."""
    return {
        "games": [
            {
                "game_id": g["game_key"],
                "event": g["event"],
                "stage": g["stage"],
                "duration_minutes": g["duration_minutes"],
                "resource_type": g["resource_type"],
                **{f"team_{x}_id": g[f"team_{x}_key"] for x in "abc" if g.get(f"team_{x}_key")},
            }
            for g in games if g["event"] not in unknown_events
        ],
        "resources": list(resources),
        "playoff_slots": list(pins),
        "team_conflicts": list(edges),
        "precedence": list(precedence),
        "day_order": ["Sat-1", "Sun-1"],
    }


def _problem(resources, games, edges=(), **kwargs):
    build_kwargs = {
        key: kwargs.pop(key)
        for key in ("repair_events", "allow_cross_day", "max_move_minutes", "rest_window_minutes")
        if key in kwargs
    }
    return sr.build_repair_problem(
        _schedule_input(resources, games, edges, **kwargs), {"games": list(games)}, **build_kwargs
    )


def _solve(problem, **kwargs):
    result = sr.solve_repair(problem, timeout_seconds=20, **kwargs)
    return result, sr.build_comparison(problem, result)


def _metric(comparison, key, column="optimized"):
    return next(m for m in comparison["metrics"] if m["metric"] == key)[column]


def _tier(result, name):
    return next(t for t in result["tiers"] if t["tier"] == name)["value"]


def _soccer_at(slot, team="SOC::A", key="SOC-G1"):
    return _game(key, SOC, [team, f"{team}-OPP"], "SOC-1", slot)


# --- conflict reduction and movement ----------------------------------------

def test_conflict_free_baseline_is_left_alone():
    resources = [_court("BB-1", "Basketball Court"), _court("VB-1", "Volleyball Court")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("VBM-01", VBM, ["VBM::A", "VBM::C"], "VB-1", "Sat-1-13:00"),
    ]
    problem = _problem(resources, games, [_edge("BBM::A", "VBM::A", secondary=2)])
    result, comparison = _solve(problem)

    assert result["status"] == sr.STATUS_OPTIMAL
    assert result["placements"] == sr.baseline_placements(problem)
    assert comparison["moved_games"] == []
    assert comparison["verdict"] == sr.VERDICT_NO_IMPROVEMENT


def test_one_move_removes_a_shared_athlete_conflict():
    resources = [_court("BB-1", "Basketball Court"), _court("VB-1", "Volleyball Court")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("VBM-01", VBM, ["VBM::A", "VBM::C"], "VB-1", "Sat-1-12:00"),
    ]
    problem = _problem(resources, games, [_edge("BBM::A", "VBM::A", secondary=2)])
    result, comparison = _solve(problem)

    assert _metric(comparison, "secondary_conflict_penalty", "baseline") == 2
    assert _metric(comparison, "secondary_conflict_penalty") == 0
    assert comparison["movement"]["games_moved"] == 1
    assert comparison["movement"]["total_move_minutes"] == 60
    assert [c["status"] for c in comparison["conflicts"]] == ["removed"]
    moved = comparison["moved_games"][0]
    assert moved["reason"].startswith("Removes BBM-01 vs VBM-01")
    assert moved["provenance"]["source_cell"] == "B2"
    # Matchups and game identities never change.
    assert {g["game_id"] for g in comparison["games"]} == {"BBM-01", "VBM-01"}
    assert {g["matchup"] for g in comparison["games"]} == {"A v B", "A v C"}


def test_solver_tiers_match_the_audited_metrics():
    resources = [_court("BB-1", "Basketball Court"), _court("VB-1", "Volleyball Court")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("VBM-01", VBM, ["VBM::A", "VBM::C"], "VB-1", "Sat-1-12:00"),
    ]
    result, comparison = _solve(_problem(resources, games, [_edge("BBM::A", "VBM::A", 1, 1)]))

    assert _tier(result, "primary_conflict_penalty") == _metric(comparison, "primary_conflict_penalty")
    assert _tier(result, "secondary_conflict_penalty") == _metric(comparison, "secondary_conflict_penalty")
    assert _tier(result, "games_moved") == comparison["movement"]["games_moved"]
    assert _tier(result, "move_minutes") == comparison["movement"]["total_move_minutes"]
    assert _tier(result, "court_changes") == comparison["movement"]["court_changes"]


def test_primary_conflict_outranks_secondary_and_movement():
    resources = [_court("VB-1", "Volleyball Court", close_time="14:00"), _court("SOC-1", "Soccer Field")]
    games = [
        _game("VBM-01", VBM, ["VBM::A", "VBM::B"], "VB-1", "Sat-1-12:00"),
        _soccer_at("Sat-1-12:00", "SOC::A", "SOC-G1"),
        _soccer_at("Sat-1-13:00", "SOC::C", "SOC-G2"),
    ]
    edges = [_edge("VBM::A", "SOC::A", primary=1, secondary=0), _edge("VBM::B", "SOC::C", secondary=3)]
    _result, comparison = _solve(_problem(resources, games, edges))

    assert _metric(comparison, "primary_conflict_penalty", "baseline") == 1
    assert _metric(comparison, "primary_conflict_penalty") == 0
    assert _metric(comparison, "secondary_conflict_penalty") == 3
    assert {c["status"] for c in comparison["conflicts"]} == {"removed", "introduced"}


def test_moves_the_shortest_distance():
    resources = [_court("BB-1", "Basketball Court"), _court("SOC-1", "Soccer Field")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::C", "BBM::D"], "BB-1", "Sat-1-13:00"),
        _soccer_at("Sat-1-12:00"),
    ]
    result, comparison = _solve(_problem(resources, games, [_edge("BBM::A", "SOC::A")]))

    # One game moving two hours beats swapping two games.
    assert result["placements"]["BBM-01"] == {"resource_id": "BB-1", "slot": "Sat-1-14:00"}
    assert comparison["movement"] == {
        **comparison["movement"],
        "games_moved": 1, "time_changes": 1, "court_changes": 0,
        "total_move_minutes": 120, "max_move_minutes": 120,
    }


def test_max_move_minutes_limits_displacement():
    resources = [_court("BB-1", "Basketball Court"), _court("SOC-1", "Soccer Field")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::C", "BBM::D"], "BB-1", "Sat-1-13:00", placement_policy="locked"),
        _soccer_at("Sat-1-12:00"),
    ]
    edges = [_edge("BBM::A", "SOC::A")]
    _result, free = _solve(_problem(resources, games, edges))
    _result, capped = _solve(_problem(resources, games, edges, max_move_minutes=60))

    assert free["movement"]["total_move_minutes"] == 120
    assert capped["moved_games"] == []
    assert _metric(capped, "secondary_conflict_penalty") == 1


@pytest.mark.parametrize("priority,minutes,court_changes,slot,resource", [
    ("time,court", 0, 1, "Sat-1-12:00", "BB-2"),
    ("court,time", 60, 0, "Sat-1-13:00", "BB-1"),
])
def test_movement_priority_chooses_court_change_or_time_change(priority, minutes, court_changes,
                                                               slot, resource):
    resources = [
        _court("BB-1", "Basketball Court", close_time="14:00"),
        _court("BB-2", "Basketball Court", "Court-2", close_time="14:00"),
    ]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::C", "BBM::D"], "BB-1", "Sat-1-12:00"),
    ]
    problem = _problem(resources, games)
    result, comparison = _solve(problem, movement_priority=priority)

    # The baseline double-books a court, so it is reported and one game must move.
    assert comparison["verdict"] == sr.VERDICT_BASELINE_INVALID
    assert [v["kind"] for v in comparison["baseline_hard_violations"]] == ["resource_collision"]
    assert comparison["optimized_hard_violations"] == []
    assert comparison["movement"]["total_move_minutes"] == minutes
    assert comparison["movement"]["court_changes"] == court_changes
    moved_id = comparison["moved_games"][0]["game_id"]
    assert result["placements"][moved_id] == {"resource_id": resource, "slot": slot}


def test_split_windows_of_one_court_are_a_time_change_not_a_court_change():
    resources = [
        _court("GYM-1", "Volleyball Court", close_time="14:00"),
        _court("GYM-6", "Volleyball Court", open_time="14:00"),
        _court("SOC-1", "Soccer Field"),
    ]
    games = [
        _game("VBM-01", VBM, ["VBM::A", "VBM::B"], "GYM-1", "Sat-1-12:00"),
        _soccer_at("Sat-1-12:00", "SOC::A", "SOC-G1"),
        _soccer_at("Sat-1-13:00", "SOC::A", "SOC-G2"),
    ]
    result, comparison = _solve(_problem(resources, games, [_edge("VBM::A", "SOC::A")]))

    assert result["placements"]["VBM-01"] == {"resource_id": "GYM-6", "slot": "Sat-1-14:00"}
    moved = comparison["moved_games"][0]
    assert (moved["moved_time"], moved["moved_court"]) == (True, False)
    assert comparison["movement"]["court_changes"] == 0


# --- locked placements --------------------------------------------------------

def test_locked_context_game_stays_and_the_repairable_game_moves():
    resources = [_court("BB-1", "Basketball Court"), _court("SOC-1", "Soccer Field")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"), _soccer_at("Sat-1-12:00")]
    problem = _problem(resources, games, [_edge("BBM::A", "SOC::A")])
    result, comparison = _solve(problem)

    assert problem["repair_events"] == [BB]
    assert problem["context_events"] == [SOC]
    assert result["placements"]["SOC-G1"] == {"resource_id": "SOC-1", "slot": "Sat-1-12:00"}
    assert [m["game_id"] for m in comparison["moved_games"]] == ["BBM-01"]


def test_explicitly_locked_game_cannot_move_and_conflict_is_reported():
    resources = [_court("BB-1", "Basketball Court"), _court("SOC-1", "Soccer Field")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00", placement_policy="locked"),
        _soccer_at("Sat-1-12:00"),
    ]
    _result, comparison = _solve(_problem(resources, games, [_edge("BBM::A", "SOC::A")]))

    assert comparison["moved_games"] == []
    assert comparison["verdict"] == sr.VERDICT_NO_IMPROVEMENT
    assert [(c["status"], c["both_locked"]) for c in comparison["conflicts"]] == [("remaining", True)]


def test_later_round_pin_keeps_its_court_and_precedence():
    resources = [
        _court("BB-1A", "Basketball Court", close_time="13:00"),
        _court("BB-1B", "Basketball Court", open_time="15:00"),
        _court("BB-P", "Basketball Court", "Court-2", open_time="14:00", close_time="15:00"),
        _court("SOC-1", "Soccer Field"),
    ]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1A", "Sat-1-12:00"), _soccer_at("Sat-1-12:00")]
    edges = [_edge("BBM::A", "SOC::A")]
    pin = {"game_id": "BBM-QF-1", "event": BB, "stage": "QF", "resource_id": "BB-P",
           "slot": "Sat-1-14:00", "duration_minutes": 60}
    rule = {"before_game_id": "BBM-01", "after_game_id": "BBM-QF-1", "min_gap_slots": 1}

    _result, free = _solve(_problem(resources, games, edges, pins=[pin]))
    result, bound = _solve(_problem(resources, games, edges, pins=[pin], precedence=[rule]))

    # Without the rule the pool game may pass the quarter-final; with it, it may not.
    assert free["moved_games"][0]["optimized"]["slot"] == "Sat-1-15:00"
    assert bound["moved_games"] == []
    assert result["placements"]["BBM-QF-1"] == {"resource_id": "BB-P", "slot": "Sat-1-14:00"}
    assert "BBM-QF-1" not in {g["game_id"] for g in bound["games"]}


def test_pin_that_reserves_nothing_is_skipped_not_a_baseline_violation():
    resources = [_court("BB-1", "Basketball Court")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00")]
    pin = {"game_id": "BBM-Final", "event": BB, "stage": "Final", "resource_id": "BB-GONE",
           "slot": "Sun-2-15:00"}
    problem = _problem(resources, games, pins=[pin])

    assert [p["game_id"] for p in problem["skipped_pins"]] == ["BBM-Final"]
    assert sr.audit_placements(problem, sr.baseline_placements(problem))["hard_violation_count"] == 0


# --- hard constraints ---------------------------------------------------------

def test_a_team_is_never_double_booked_by_a_move():
    resources = [_court("BB-1", "Basketball Court", close_time="14:00"),
                 _court("BB-2", "Basketball Court", "Court-2", close_time="14:00"),
                 _court("SOC-1", "Soccer Field")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::A", "BBM::C"], "BB-2", "Sat-1-13:00", placement_policy="locked"),
        _soccer_at("Sat-1-12:00"),
    ]
    _result, comparison = _solve(_problem(resources, games, [_edge("BBM::B", "SOC::A")]),
                                 rest_policy="ignore")

    # The only free slots are at 13:00, when team A already plays.
    assert comparison["moved_games"] == []
    assert comparison["optimized_hard_violations"] == []


def test_rest_policy_blocks_a_new_back_to_back_game():
    resources = [_court("BB-1", "Basketball Court"), _court("SOC-1", "Soccer Field")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::D", "BBM::E"], "BB-1", "Sat-1-13:00", placement_policy="locked"),
        _game("BBM-03", BB, ["BBM::A", "BBM::C"], "BB-1", "Sat-1-15:00", placement_policy="locked"),
        _soccer_at("Sat-1-12:00"),
    ]
    problem = _problem(resources, games, [_edge("BBM::B", "SOC::A")])

    _result, kept = _solve(problem)
    _result, relaxed = _solve(problem, rest_policy="ignore")

    assert kept["moved_games"] == []
    assert _metric(kept, "rest_violation_count") == 0
    assert relaxed["moved_games"][0]["optimized"]["slot"] == "Sat-1-14:00"
    assert _metric(relaxed, "rest_violation_count") == 1


def test_placement_outside_the_venue_window_makes_the_baseline_invalid():
    resources = [_court("BB-1", "Basketball Court")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-17:00")]
    result, comparison = _solve(_problem(resources, games))

    assert comparison["verdict"] == sr.VERDICT_BASELINE_INVALID
    assert comparison["baseline_hard_violations"][0]["kind"] == "illegal_placement"
    assert _metric(comparison, "illegal_assignments", "baseline") == 1
    assert _metric(comparison, "illegal_assignments") == 0
    assert result["placements"]["BBM-01"]["resource_id"] == "BB-1"


def test_cross_day_moves_are_off_unless_enabled():
    resources = [
        _court("BB-1", "Basketball Court", close_time="13:00"),
        _court("BB-S1", "Basketball Court", close_time="13:00", day="Sun-1"),
        _court("BB-S2", "Basketball Court", "Court-2", close_time="13:00", day="Sun-1"),
        _court("SOC-1", "Soccer Field"),
    ]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::C", "BBM::D"], "BB-S2", "Sun-1-12:00"),
        _soccer_at("Sat-1-12:00"),
    ]
    edges = [_edge("BBM::A", "SOC::A")]

    _result, same_day = _solve(_problem(resources, games, edges))
    result, cross_day = _solve(_problem(resources, games, edges, allow_cross_day=True))

    assert same_day["moved_games"] == []
    assert cross_day["moved_games"][0]["optimized"]["slot"] == "Sun-1-12:00"
    assert cross_day["movement"]["day_changes"] == 1
    assert _tier(result, "games_moved_day") == 1


# --- scope ----------------------------------------------------------------------

def test_bible_challenge_three_team_grouping_is_kept():
    resources = [_court("BC-1", "BC Station"), _court("SOC-1", "Soccer Field")]
    games = [_game("BC-RR-1", BC, ["BC::A", "BC::B", "BC::C"], "BC-1", "Sat-1-12:00"),
             _soccer_at("Sat-1-12:00")]
    problem = _problem(resources, games, [_edge("BC::C", "SOC::A")])
    _result, comparison = _solve(problem)

    assert problem["games"][0]["team_ids"] == ["BC::A", "BC::B", "BC::C"]
    moved = comparison["moved_games"][0]
    assert (moved["game_id"], moved["matchup"]) == ("BC-RR-1", "A / B / C")


def test_sport_without_matching_team_ids_is_deferred_and_carried_through():
    resources = [_court("BB-1", "Basketball Court"), _court("TT-1", "Table Tennis Table", slot_minutes=15)]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("TT-M-S-01", TT, ["TT-M-S::X", "TT-M-S::Y"], "TT-1", "Sat-1-12:00", duration_minutes=15),
    ]
    problem = _problem(resources, games, unknown_events=[TT])
    result, comparison = _solve(problem)
    output = sr.build_optimized_output(comparison, result)

    assert [(d["event"], d["game_count"]) for d in problem["deferred_events"]] == [(TT, 1)]
    row = next(g for g in comparison["games"] if g["game_id"] == "TT-M-S-01")
    assert row["placement_policy"] == "deferred" and row["optimized"] == row["baseline"]
    assert {a["game_id"] for a in output["assignments"]} == {"BBM-01", "TT-M-S-01"}
    with pytest.raises(ValueError, match="deferred sport"):
        _problem(resources, games, unknown_events=[TT], repair_events=[TT])


def test_conflict_edges_without_approved_games_are_reported():
    resources = [_court("BB-1", "Basketball Court")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00")]
    edge = {**_edge("BBM::A", "TEN::A"), "event_a": BB, "event_b": "Tennis"}
    problem = _problem(resources, games, [edge])

    assert problem["team_conflicts"] == []
    assert problem["unevaluated_edges"] == [
        {"events_without_approved_games": "Tennis", "edge_count": 1}
    ]


def test_unknown_placement_policy_is_rejected():
    resources = [_court("BB-1", "Basketball Court")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00", placement_policy="fixed")]
    with pytest.raises(ValueError, match="placement_policy"):
        _problem(resources, games)


# --- review findings on PR #382 -------------------------------------------------

def _shared_court_world(**kwargs):
    """Two Men's Volleyball games that clash; the only free slot is VB-1 at 13:00."""
    resources = [_court("VB-1", "Volleyball Court", close_time="14:00"),
                 _court("VB-2", "Volleyball Court", "Court-2", close_time="13:00")]
    games = [
        _game("VBM-01", VBM, ["VBM::A", "VBM::B"], "VB-1", "Sat-1-12:00"),
        _game("VBM-02", VBM, ["VBM::C", "VBM::D"], "VB-2", "Sat-1-12:00"),
    ]
    edges = [_edge("VBM::A", "VBM::C", primary=1, secondary=0)]
    return resources, games, edges


def test_free_slot_is_used_when_nothing_reserves_it():
    resources, games, edges = _shared_court_world()
    result, _comparison = _solve(_problem(resources, games, edges))
    assert {"resource_id": "VB-1", "slot": "Sat-1-13:00"} in result["placements"].values()


def test_deferred_game_keeps_its_court():
    resources, games, edges = _shared_court_world()
    games.append(_game("VBW-01", VBW, ["VBW::X", "VBW::Y"], "VB-1", "Sat-1-13:00"))
    problem = _problem(resources, games, edges, unknown_events=[VBW])
    result, comparison = _solve(problem)

    assert [d["event"] for d in problem["deferred_events"]] == [VBW]
    assert comparison["moved_games"] == []
    assert {"resource_id": "VB-1", "slot": "Sat-1-13:00"} not in result["placements"].values()
    assert _metric(comparison, "primary_conflict_penalty") == 1


def test_baseline_game_on_a_deferred_games_court_is_a_collision():
    resources, games, _edges = _shared_court_world()
    games.append(_game("VBW-01", VBW, ["VBW::X", "VBW::Y"], "VB-1", "Sat-1-12:00"))
    problem = _problem(resources, games, unknown_events=[VBW])
    audit = sr.audit_placements(problem, sr.baseline_placements(problem))

    assert [(v["kind"], v["game_ids"]) for v in audit["hard_violations"]] == [
        ("resource_collision", ["VBM-01", "VBW-01"])
    ]


def test_pin_for_a_deferred_sport_keeps_its_court():
    resources, games, edges = _shared_court_world()
    pin = {"game_id": "VBW-Final", "event": VBW, "stage": "Final", "resource_id": "VB-1",
           "slot": "Sat-1-13:00", "duration_minutes": 60}
    problem = _problem(resources, games, edges, pins=[pin])
    result, comparison = _solve(problem)

    assert [r["game_id"] for r in problem["reserved"]] == ["VBW-Final"]
    assert problem["skipped_pins"] == []
    assert comparison["moved_games"] == []
    assert {"resource_id": "VB-1", "slot": "Sat-1-13:00"} not in result["placements"].values()


def test_forced_move_counts_once_and_fits_a_one_move_budget():
    resources = [_court("BB-1", "Basketball Court")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00",
                   earliest_slot="Sat-1-13:00")]
    problem = _problem(resources, games)
    result, comparison = _solve(problem)

    assert _tier(result, "games_moved") == 1 == comparison["movement"]["games_moved"]
    assert sr.solve_repair(problem, timeout_seconds=20, max_moves=1)["status"] == sr.STATUS_OPTIMAL


@pytest.mark.parametrize("limits,fragment", [
    ({"earliest_slot": "Sat-1-13:00"}, "before its earliest slot"),
    ({"latest_slot": "Sat-1-11:00"}, "after its latest slot"),
    ({"allowed_resource_ids": ["BB-2"]}, "not one of its allowed resources"),
])
def test_baseline_outside_a_games_own_limits_is_invalid(limits, fragment):
    resources = [_court("BB-1", "Basketball Court", open_time="11:00"),
                 _court("BB-2", "Basketball Court", "Court-2", open_time="11:00")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00", **limits)]
    _result, comparison = _solve(_problem(resources, games))

    assert comparison["verdict"] == sr.VERDICT_BASELINE_INVALID
    violation = comparison["baseline_hard_violations"][0]
    assert violation["kind"] == "outside_envelope" and fragment in violation["message"]
    assert _metric(comparison, "outside_envelope", "baseline") == 1
    assert _metric(comparison, "outside_envelope") == 0
    assert comparison["moved_games"][0]["reason"].startswith("Approved placement is not legal")


def test_max_move_minutes_is_audited_on_the_result():
    resources = [_court("BB-1", "Basketball Court")]
    games = [_game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00")]
    problem = _problem(resources, games, max_move_minutes=60)
    audit = sr.audit_placements(problem, {"BBM-01": {"resource_id": "BB-1", "slot": "Sat-1-15:00"}})
    assert [v["kind"] for v in audit["hard_violations"]] == ["outside_envelope"]


def test_same_label_courts_with_overlapping_windows_are_different_courts():
    def pod_court(resource_id):
        return {**_court(resource_id, "Volleyball Court", close_time="13:00"), "exclusive_group": ""}

    resources = [pod_court("VB-1"), pod_court("VB-2")]
    games = [
        _game("VBM-01", VBM, ["VBM::A", "VBM::B"], "VB-1", "Sat-1-12:00"),
        _game("VBM-02", VBM, ["VBM::C", "VBM::D"], "VB-1", "Sat-1-12:00"),
    ]
    _result, comparison = _solve(_problem(resources, games))

    moved = comparison["moved_games"][0]
    assert (moved["moved_time"], moved["moved_court"]) == (False, True)
    assert comparison["movement"]["court_changes"] == 1
    assert moved["optimized"]["court"] != moved["baseline"]["court"]


def test_pod_name_keeps_two_pods_apart_when_their_split_windows_do_not_line_up():
    def pod_court(resource_id, pod, open_time, close_time):
        return {**_court(resource_id, "Basketball Court", open_time=open_time, close_time=close_time),
                "exclusive_group": "", "venue_name": "EHS", "pod_name": pod}

    resources = [
        pod_court("BB-1", "Pod A", "08:00", "12:00"),
        pod_court("BB-2", "Pod B", "08:00", "11:00"),
        pod_court("BB-3", "Pod B", "12:00", "16:00"),
        pod_court("BB-4", "Pod A", "13:00", "16:00"),
    ]
    ctx = sr._Context({"resources": resources, "games": [], "day_order": ["Sat-1"]})
    keys = {r["resource_id"]: ctx.court_key(r["resource_id"]) for r in resources}
    # Split windows of one pod are one court; the two pods are different courts.
    assert keys["BB-1"] == keys["BB-4"]
    assert keys["BB-2"] == keys["BB-3"]
    assert keys["BB-1"] != keys["BB-3"]


def _invalid_baseline_with_rest_choice(close_time):
    resources = [_court("BB-1", "Basketball Court", close_time=close_time)]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::C", "BBM::D"], "BB-1", "Sat-1-12:00", placement_policy="locked"),
        _game("BBM-03", BB, ["BBM::A", "BBM::E"], "BB-1", "Sat-1-14:00", placement_policy="locked"),
    ]
    return _problem(resources, games)


def test_rest_cap_still_applies_when_repairing_an_invalid_baseline():
    result, comparison = _solve(_invalid_baseline_with_rest_choice("17:00"))

    # 13:00 and 15:00 are closer but back-to-back with team A's 14:00 game.
    assert comparison["verdict"] == sr.VERDICT_BASELINE_INVALID
    assert result["placements"]["BBM-01"]["slot"] == "Sat-1-16:00"
    assert _metric(comparison, "rest_violation_count") == 0
    assert result["rest_cap_relaxed"] is False


def test_rest_cap_is_dropped_only_when_no_legal_repair_keeps_it():
    result, comparison = _solve(_invalid_baseline_with_rest_choice("16:00"))

    assert result["status"] == sr.STATUS_OPTIMAL
    assert result["rest_cap_relaxed"] is True
    assert comparison["optimized_hard_violations"] == []
    assert _metric(comparison, "rest_violation_count") == 1
    assert any("limit was dropped" in line for line in comparison["summary_lines"])


def test_failed_relaxed_retry_does_not_claim_the_rest_cap_was_dropped():
    # max_moves=0 makes the repair impossible for a reason unrelated to rest.
    problem = _invalid_baseline_with_rest_choice("16:00")
    result = sr.solve_repair(problem, timeout_seconds=20, max_moves=0)
    comparison = sr.build_comparison(problem, result)

    assert result["status"] == sr.STATUS_INFEASIBLE
    assert result["rest_cap_relaxed"] is False
    assert not any("limit was dropped" in line for line in comparison["summary_lines"])


def test_verdict_reports_each_penalty_and_never_a_negative_count():
    def audit(primary, secondary):
        return {"hard_violation_count": 0, "primary_conflict_penalty": primary,
                "secondary_conflict_penalty": secondary}

    verdict, rationale = sr.decide_verdict(audit(1, 0), audit(0, 3), 1, 80)
    assert verdict == sr.VERDICT_MARGINAL
    assert "primary penalty 1 -> 0, secondary penalty 0 -> 3" in rationale
    assert "-2" not in rationale and "clash" not in rationale


def test_move_frontier_stops_when_its_time_budget_is_spent():
    resources, games, edges = _shared_court_world()
    rows = sr.compute_move_frontier(_problem(resources, games, edges), max_budget=5,
                                    timeout_seconds=0.0)
    assert [r["max_moves"] for r in rows] == [0]


# --- metrics --------------------------------------------------------------------

def test_volleyball_switches_and_latest_finish_are_audited():
    resources = [_court("VB-1", "Volleyball Court")]
    games = [
        _game("VBM-01", VBM, ["VBM::A", "VBM::B"], "VB-1", "Sat-1-12:00"),
        _game("VBW-01", VBW, ["VBW::A", "VBW::B"], "VB-1", "Sat-1-13:00"),
        _game("VBW-02", VBW, ["VBW::C", "VBW::D"], "VB-1", "Sat-1-14:00"),
        _game("VBM-02", VBM, ["VBM::C", "VBM::D"], "VB-1", "Sat-1-15:00"),
    ]
    problem = _problem(resources, games)
    audit = sr.audit_placements(problem, sr.baseline_placements(problem))

    assert audit["volleyball_adjacent_switches"] == 2
    assert audit["latest_finish"] == "16:00"
    assert audit["latest_finish_by_day"] == {"Sat-1": "16:00"}
    assert (audit["repairable_games"], audit["locked_games"]) == (4, 0)


def test_move_frontier_shows_the_gain_of_each_extra_move():
    resources = [_court("BB-1", "Basketball Court"), _court("VB-1", "Volleyball Court"),
                 _court("SOC-1", "Soccer Field")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("VBM-01", VBM, ["VBM::A", "VBM::B"], "VB-1", "Sat-1-13:00"),
        _soccer_at("Sat-1-12:00", "SOC::A", "SOC-G1"),
        _soccer_at("Sat-1-13:00", "SOC::B", "SOC-G2"),
    ]
    edges = [_edge("BBM::A", "SOC::A", secondary=3), _edge("VBM::A", "SOC::B", secondary=2)]
    rows = sr.compute_move_frontier(_problem(resources, games, edges), max_budget=2, timeout_seconds=20)

    assert [(r["max_moves"], r["secondary_conflict_penalty"], r["proven"]) for r in rows] == [
        (0, 5, True), (1, 2, True), (2, 0, True)
    ]


def test_max_moves_caps_the_repair():
    resources = [_court("BB-1", "Basketball Court"), _court("VB-1", "Volleyball Court"),
                 _court("SOC-1", "Soccer Field")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("VBM-01", VBM, ["VBM::A", "VBM::B"], "VB-1", "Sat-1-13:00"),
        _soccer_at("Sat-1-12:00", "SOC::A", "SOC-G1"),
        _soccer_at("Sat-1-13:00", "SOC::B", "SOC-G2"),
    ]
    edges = [_edge("BBM::A", "SOC::A", secondary=3), _edge("VBM::A", "SOC::B", secondary=2)]
    _result, comparison = _solve(_problem(resources, games, edges), max_moves=1)

    assert [m["game_id"] for m in comparison["moved_games"]] == ["BBM-01"]
    assert _metric(comparison, "secondary_conflict_penalty") == 2


def test_repeated_runs_give_the_same_schedule():
    resources = [_court("BB-1", "Basketball Court"), _court("BB-2", "Basketball Court", "Court-2"),
                 _court("VB-1", "Volleyball Court"), _court("VB-2", "Volleyball Court", "Court-2")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("BBM-02", BB, ["BBM::C", "BBM::D"], "BB-2", "Sat-1-12:00"),
        _game("VBM-01", VBM, ["VBM::A", "VBM::C"], "VB-1", "Sat-1-12:00"),
        _game("VBM-02", VBM, ["VBM::B", "VBM::D"], "VB-2", "Sat-1-12:00"),
    ]
    edges = [_edge(f"BBM::{t}", f"VBM::{t}", secondary=2) for t in "ABCD"]
    problem = _problem(resources, games, edges)

    first = sr.solve_repair(problem, timeout_seconds=20)
    second = sr.solve_repair(problem, timeout_seconds=20)

    assert first["status"] == sr.STATUS_OPTIMAL
    assert first["placements"] == second["placements"]
    assert [t["value"] for t in first["tiers"]] == [t["value"] for t in second["tiers"]]


@pytest.mark.parametrize("before,after,moved,expected", [
    ((0, 5), (0, 0), 4, sr.VERDICT_ACCEPTABLE),
    ((0, 5), (0, 4), 4, sr.VERDICT_MARGINAL),
    ((0, 50), (0, 0), 40, sr.VERDICT_MARGINAL),
    ((0, 5), (0, 5), 0, sr.VERDICT_NO_IMPROVEMENT),
    ((1, 5), (0, 9), 1, sr.VERDICT_MARGINAL),
])
def test_verdict_labels(before, after, moved, expected):
    def audit(pair):
        return {"hard_violation_count": 0, "primary_conflict_penalty": pair[0],
                "secondary_conflict_penalty": pair[1]}
    assert sr.decide_verdict(audit(before), audit(after), moved, 80)[0] == expected


# --- command --------------------------------------------------------------------

@pytest.fixture
def files(tmp_path):
    resources = [_court("BB-1", "Basketball Court"), _court("VB-1", "Volleyball Court")]
    games = [
        _game("BBM-01", BB, ["BBM::A", "BBM::B"], "BB-1", "Sat-1-12:00"),
        _game("VBM-01", VBM, ["VBM::A", "VBM::C"], "VB-1", "Sat-1-12:00"),
    ]
    edges = [_edge("BBM::A", "VBM::A", secondary=2)]
    paths = {
        "input_path": tmp_path / "schedule_input.json",
        "baseline_path": tmp_path / "approved_schedule_games.json",
        "comparison_path": tmp_path / "optimized_schedule_comparison.json",
        "output_path": tmp_path / "optimized_schedule_output.json",
        "workbook_path": tmp_path / "VAYSF_Optimized_Schedule.xlsx",
    }
    paths["input_path"].write_text(json.dumps(_schedule_input(resources, games, edges)), encoding="utf-8")
    paths["baseline_path"].write_text(json.dumps({"games": games}), encoding="utf-8")
    return paths


def test_dry_run_writes_only_the_comparison(files):
    before = {key: files[key].read_bytes() for key in ("input_path", "baseline_path")}
    assert sr.run_optimize_approved_schedule(**files, execute=False, timeout_seconds=20) == 0

    comparison = json.loads(files["comparison_path"].read_text(encoding="utf-8"))
    assert comparison["experimental"] is True
    assert comparison["movement"]["games_moved"] == 1
    assert [r["max_moves"] for r in comparison["move_frontier"]] == [0, 1]
    assert not files["output_path"].exists() and not files["workbook_path"].exists()
    assert {key: files[key].read_bytes() for key in before} == before


def test_execute_writes_separate_artifacts_and_leaves_the_inputs_alone(files):
    before = {key: files[key].read_bytes() for key in ("input_path", "baseline_path")}
    assert sr.run_optimize_approved_schedule(**files, execute=True, timeout_seconds=20) == 0

    output = json.loads(files["output_path"].read_text(encoding="utf-8"))
    assert validate_schedule_output(output) == []
    assert sorted(a["game_id"] for a in output["assignments"]) == ["BBM-01", "VBM-01"]
    assert sum(a["x_moved"] for a in output["assignments"]) == 1
    assert output["x_repair"]["experimental"] is True
    sheets = load_workbook(files["workbook_path"]).sheetnames
    assert sheets == ["Summary", "Moved-Games", "Conflicts", "Schedule", "Baseline-Issues", "Move-Frontier"]
    assert {key: files[key].read_bytes() for key in before} == before


def test_refuses_to_write_over_an_official_schedule_file(files, tmp_path):
    files["output_path"] = tmp_path / "schedule_output.json"
    assert sr.run_optimize_approved_schedule(**files, execute=True, timeout_seconds=20) == 3
    assert not files["output_path"].exists()

    files["output_path"] = files["baseline_path"]
    assert sr.run_optimize_approved_schedule(**files, execute=True, timeout_seconds=20) == 3


def test_invalid_baseline_and_missing_input_exit_codes(files):
    payload = json.loads(files["baseline_path"].read_text(encoding="utf-8"))
    payload["games"][0]["scheduled_slot"] = "Sat-1-19:00"
    files["baseline_path"].write_text(json.dumps(payload), encoding="utf-8")
    assert sr.run_optimize_approved_schedule(**files, execute=False, timeout_seconds=20) == 1
    comparison = json.loads(files["comparison_path"].read_text(encoding="utf-8"))
    assert comparison["verdict"] == sr.VERDICT_BASELINE_INVALID

    files["input_path"].unlink()
    assert sr.run_optimize_approved_schedule(**files, execute=False, timeout_seconds=20) == 3


def test_cli_runs_the_experiment(monkeypatch, files):
    import main

    argv = [
        "main.py", "optimize-approved-schedule",
        "--input", str(files["input_path"]),
        "--baseline", str(files["baseline_path"]),
        "--comparison", str(files["comparison_path"]),
        "--output", str(files["output_path"]),
        "--workbook", str(files["workbook_path"]),
        "--max-moves", "1", "--timeout", "20", "--no-frontier", "--execute",
    ]
    monkeypatch.setattr(main.sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        main.main()

    assert exc.value.code == 0
    comparison = json.loads(files["comparison_path"].read_text(encoding="utf-8"))
    assert comparison["parameters"]["max_moves"] == 1
    assert comparison["move_frontier"] == []
    assert files["output_path"].exists() and files["workbook_path"].exists()


def test_cli_requires_a_mode(monkeypatch):
    import main

    monkeypatch.setattr(main.sys, "argv", ["main.py", "optimize-approved-schedule"])
    with pytest.raises(SystemExit) as exc:
        main.parse_args()
    assert exc.value.code == 2
