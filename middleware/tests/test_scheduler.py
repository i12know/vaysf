"""Tests for scheduler.py (Issue #93)."""
import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# build_resource_slots
# ---------------------------------------------------------------------------

def test_build_resource_slots_basic():
    """Slots are generated from open_time to close_time - slot_minutes, inclusive."""
    from scheduler import build_resource_slots
    resources = [{
        "resource_id": "GYM-Sat-1-1", "resource_type": "Gym Court",
        "label": "Court-1", "day": "Sat-1",
        "open_time": "08:00", "close_time": "10:00", "slot_minutes": 60,
    }]
    slots = build_resource_slots(resources)
    assert slots["GYM-Sat-1-1"] == ["Sat-1-08:00", "Sat-1-09:00"]


def test_build_resource_slots_30min():
    """30-minute slots within a 90-minute window produce 3 slots."""
    from scheduler import build_resource_slots
    resources = [{
        "resource_id": "TT-1", "resource_type": "Table Tennis Table",
        "label": "Table-1", "day": "Day-1",
        "open_time": "09:00", "close_time": "10:30", "slot_minutes": 30,
    }]
    slots = build_resource_slots(resources)
    assert slots["TT-1"] == ["Day-1-09:00", "Day-1-09:30", "Day-1-10:00"]


def test_build_resource_slots_empty_window():
    """A resource whose window is smaller than one slot yields no slots."""
    from scheduler import build_resource_slots
    resources = [{
        "resource_id": "R1", "resource_type": "Gym Court",
        "label": "Court-1", "day": "Sat-1",
        "open_time": "08:00", "close_time": "08:30", "slot_minutes": 60,
    }]
    slots = build_resource_slots(resources)
    assert slots["R1"] == []


def test_build_resource_slots_multiple_resources():
    """Each resource gets its own independent slot list."""
    from scheduler import build_resource_slots
    resources = [
        {
            "resource_id": "A", "resource_type": "Gym Court",
            "label": "Court-1", "day": "Sat-1",
            "open_time": "08:00", "close_time": "10:00", "slot_minutes": 60,
        },
        {
            "resource_id": "B", "resource_type": "Gym Court",
            "label": "Court-2", "day": "Sun-1",
            "open_time": "13:00", "close_time": "15:00", "slot_minutes": 60,
        },
    ]
    slots = build_resource_slots(resources)
    assert slots["A"] == ["Sat-1-08:00", "Sat-1-09:00"]
    assert slots["B"] == ["Sun-1-13:00", "Sun-1-14:00"]


def test_slot_day_key_ignores_optional_suffix():
    """Slot-day extraction should survive future label suffixes."""
    from scheduler import _slot_day_key, _slot_sort_key

    assert _slot_day_key("Sat-1-08:00-AM") == "Sat-1"
    # (cycle=1, weekday=Sat→5, minutes=480)
    assert _slot_sort_key("Sat-1-08:00-AM") == (1, 5, 8 * 60)


def test_slot_sort_key_fallback_different_cycles():
    """Fallback _slot_sort_key: cycle-1 days sort before cycle-2 days."""
    from scheduler import _slot_sort_key

    fri1 = _slot_sort_key("Fri-1-17:00")
    sun2 = _slot_sort_key("Sun-2-16:00")
    sat2 = _slot_sort_key("Sat-2-08:00")

    assert fri1 < sun2, "Fri-1 (cycle 1) must sort before Sun-2 (cycle 2)"
    assert fri1 < sat2, "Fri-1 (cycle 1) must sort before Sat-2 (cycle 2)"


def test_normalize_conflict_edge_counts_derives_secondary_only():
    """Missing secondary_only_count should derive from shared minus primary."""
    from scheduler import _normalize_conflict_edge_counts

    counts = _normalize_conflict_edge_counts(
        {
            "shared_count": 3,
            "primary_overlap_count": 2,
        }
    )

    assert counts == {
        "primary": 2,
        "secondary": 1,
        "shared_count": 3,
    }


def test_build_conflict_audit_marks_unscheduled_event_as_planning_only():
    """Edges touching an event with no Layer-2 games should be planning-only, not incomplete."""
    from scheduler import build_conflict_audit

    schedule_input = {
        "games": [
            {
                "game_id": "BBM-01",
                "event": "Basketball - Men Team",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BBM::RPC",
                "team_b_id": "BBM::ANH",
                "duration_minutes": 60,
                "resource_type": "Basketball Court",
            }
        ],
        "resources": [],
        "team_conflicts": [
            {
                "team_a_id": "BBM::RPC",
                "team_a_label": "RPC",
                "event_a": "Basketball - Men Team",
                "team_b_id": "BC::OCB",
                "team_b_label": "OCB",
                "event_b": "Bible Challenge - Mixed Team",
                "shared_count": 1,
                "primary_overlap_count": 1,
                "secondary_only_count": 0,
                "shared_participant_names": ["An"],
            }
        ],
    }
    assignments = [
        {"game_id": "BBM-01", "resource_id": "BB-1", "slot": "Sat-1-08:00"}
    ]

    summary, rows = build_conflict_audit(schedule_input, assignments)

    assert summary["planning_only_edges"] == 1
    assert summary["incomplete_edges"] == 0
    assert rows[0]["status"] == "PlanningOnly"


def test_build_conflict_audit_marks_bc_edge_scheduled_when_bc_games_exist():
    """BC edges should stop being planning-only once BC queue games exist."""
    from scheduler import build_conflict_audit

    schedule_input = {
        "games": [
            {
                "game_id": "BBM-01",
                "event": "Basketball - Men Team",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BBM::RPC",
                "team_b_id": "BBM::ANH",
                "duration_minutes": 60,
                "resource_type": "Basketball Court",
            },
            {
                "game_id": "BC-P1-RR-1",
                "event": "Bible Challenge - Mixed Team",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BC::OCB",
                "team_b_id": "BC::TLC",
                "team_c_id": "BC::GLA",
                "duration_minutes": 60,
                "resource_type": "BC Station",
            },
        ],
        "resources": [],
        "team_conflicts": [
            {
                "team_a_id": "BBM::RPC",
                "team_a_label": "RPC",
                "event_a": "Basketball - Men Team",
                "team_b_id": "BC::OCB",
                "team_b_label": "OCB",
                "event_b": "Bible Challenge - Mixed Team",
                "shared_count": 1,
                "primary_overlap_count": 1,
                "secondary_only_count": 0,
                "shared_participant_names": ["An"],
            }
        ],
    }
    assignments = [
        {"game_id": "BBM-01", "resource_id": "BB-1", "slot": "Sat-1-08:00"},
        {"game_id": "BC-P1-RR-1", "resource_id": "BC-1", "slot": "Sat-1-09:00"},
    ]

    summary, rows = build_conflict_audit(schedule_input, assignments)

    assert summary["planning_only_edges"] == 0
    assert rows[0]["status"] == "SeparatedInSchedule"
    assert rows[0]["scheduled_team_b_games"] == 1


def test_build_conflict_audit_marks_soccer_edge_scheduled_when_soccer_games_exist():
    """Soccer edges should stop being planning-only once Soccer Field games exist."""
    from scheduler import build_conflict_audit

    schedule_input = {
        "games": [
            {
                "game_id": "BBM-01",
                "event": "Basketball - Men Team",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BBM::RPC",
                "team_b_id": "BBM::ANH",
                "duration_minutes": 60,
                "resource_type": "Basketball Court",
            },
            {
                "game_id": "SOC-01",
                "event": "Soccer - Coed Exhibition",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "SOC::OCB",
                "team_b_id": "SOC::TLC",
                "duration_minutes": 60,
                "resource_type": "Soccer Field",
            },
        ],
        "resources": [],
        "team_conflicts": [
            {
                "team_a_id": "BBM::RPC",
                "team_a_label": "RPC",
                "event_a": "Basketball - Men Team",
                "team_b_id": "SOC::OCB",
                "team_b_label": "OCB",
                "event_b": "Soccer - Coed Exhibition",
                "shared_count": 1,
                "primary_overlap_count": 1,
                "secondary_only_count": 0,
                "shared_participant_names": ["An"],
            }
        ],
    }
    assignments = [
        {"game_id": "BBM-01", "resource_id": "BB-1", "slot": "Sat-1-08:00"},
        {"game_id": "SOC-01", "resource_id": "SOC-1", "slot": "Sat-1-09:00"},
    ]

    summary, rows = build_conflict_audit(schedule_input, assignments)

    assert summary["planning_only_edges"] == 0
    assert rows[0]["status"] == "SeparatedInSchedule"
    assert rows[0]["scheduled_team_b_games"] == 1


# ---------------------------------------------------------------------------
# load_schedule_input
# ---------------------------------------------------------------------------

def test_load_schedule_input_valid(tmp_path):
    """load_schedule_input returns dict when all required keys are present."""
    from scheduler import load_schedule_input
    data = {"games": [], "resources": []}
    path = tmp_path / "si.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load_schedule_input(path)
    assert result["games"] == []
    assert result["resources"] == []


def test_load_schedule_input_missing_key(tmp_path):
    """load_schedule_input raises ValueError when a required key is absent."""
    from scheduler import load_schedule_input
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"games": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="resources"):
        load_schedule_input(path)


def test_load_schedule_input_file_not_found(tmp_path):
    """load_schedule_input raises an appropriate error for missing files."""
    from scheduler import load_schedule_input
    with pytest.raises(FileNotFoundError):
        load_schedule_input(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# solve() — requires ortools
# ---------------------------------------------------------------------------

def _minimal_schedule_input(games, resources):
    return {
        "games": games,
        "resources": resources,
    }


def _gym_resource(resource_id, day="Sat-1", open_time="08:00", close_time="11:00"):
    return {
        "resource_id": resource_id, "resource_type": "Gym Court",
        "label": "Court-1", "day": day,
        "open_time": open_time, "close_time": close_time, "slot_minutes": 60,
    }


def _gym_game(game_id, team_a, team_b, stage="Pool", pool_id="P1"):
    return {
        "game_id": game_id, "event": "Basketball - Men Team",
        "stage": stage, "pool_id": pool_id, "round": 1,
        "team_a_id": team_a, "team_b_id": team_b,
        "duration_minutes": 60, "resource_type": "Gym Court",
        "earliest_slot": None, "latest_slot": None,
    }


def _volleyball_resource(resource_id, day="Sat-1", open_time="08:00", close_time="10:00"):
    return {
        "resource_id": resource_id, "resource_type": "Volleyball Court",
        "label": resource_id, "day": day,
        "open_time": open_time, "close_time": close_time, "slot_minutes": 60,
    }


def _volleyball_game(game_id, event, team_a, team_b, stage="Pool", pool_id="P1"):
    return {
        "game_id": game_id, "event": event,
        "stage": stage, "pool_id": pool_id, "round": 1,
        "team_a_id": team_a, "team_b_id": team_b,
        "duration_minutes": 60, "resource_type": "Volleyball Court",
        "earliest_slot": None, "latest_slot": None,
    }


def _bc_resource(resource_id, day="Sat-1", open_time="08:00", close_time="10:00"):
    return {
        "resource_id": resource_id, "resource_type": "BC Station",
        "label": resource_id, "day": day,
        "open_time": open_time, "close_time": close_time, "slot_minutes": 60,
    }


def _bc_game(game_id, team_a, team_b, team_c, stage="Pool", pool_id="P1", round_num=1):
    return {
        "game_id": game_id,
        "event": "Bible Challenge - Mixed Team",
        "stage": stage,
        "pool_id": pool_id,
        "round": round_num,
        "team_a_id": team_a,
        "team_b_id": team_b,
        "team_c_id": team_c,
        "duration_minutes": 60,
        "resource_type": "BC Station",
        "earliest_slot": None,
        "latest_slot": None,
    }


def _core_gym_resource(resource_id, resource_type):
    return {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "solver_pool": "Gym Core",
        "label": resource_id,
        "day": "Sat-1",
        "open_time": "08:00",
        "close_time": "10:00",
        "slot_minutes": 60,
    }


def _core_gym_game(game_id, event, team_a, team_b, resource_type):
    return {
        "game_id": game_id,
        "event": event,
        "stage": "Pool",
        "pool_id": "P1",
        "round": 1,
        "team_a_id": team_a,
        "team_b_id": team_b,
        "duration_minutes": 60,
        "resource_type": resource_type,
        "solver_pool": "Gym Core",
        "earliest_slot": None,
        "latest_slot": None,
    }


@pytest.mark.skipif(
    not pytest.importorskip("ortools", reason="ortools not installed"),
    reason="ortools not installed",
)
def test_solve_two_games_no_team_overlap():
    """Two games with disjoint teams and one court: both scheduled OPTIMAL."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "BBM-P1-T1", "BBM-P1-T2"),
            _gym_game("G2", "BBM-P1-T3", "BBM-P1-T4"),
        ],
        resources=[_gym_resource("GYM-Sat-1-1")],
    )
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    assert len(result["assignments"]) == 2
    assert result["unscheduled"] == []
    # Both games on the same court must be in different slots
    slots = {a["game_id"]: a["slot"] for a in result["assignments"]}
    assert slots["G1"] != slots["G2"]


def test_solve_bc_three_team_games_respect_shared_team_overlap():
    """A BC team appearing in two 3-team games must not be double-booked across stations."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_INFEASIBLE

    si = _minimal_schedule_input(
        games=[
            _bc_game("BC-1", "BC::A", "BC::B", "BC::C"),
            _bc_game("BC-2", "BC::C", "BC::D", "BC::E"),
        ],
        resources=[
            _bc_resource("BC-1", close_time="09:00"),
            _bc_resource("BC-2", close_time="09:00"),
        ],
    )
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_INFEASIBLE
    assert sorted(result["unscheduled"]) == ["BC-1", "BC-2"]


def test_solve_bc_precedence_keeps_final_after_semis():
    """BC final must be scheduled after all semifinals in the single-room queue."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = _minimal_schedule_input(
        games=[
            _bc_game("BC-Semi-1", "BC-S1A", "BC-S1B", "BC-S1C", stage="Semi", pool_id="", round_num=1),
            _bc_game("BC-Semi-2", "BC-S2A", "BC-S2B", "BC-S2C", stage="Semi", pool_id="", round_num=2),
            _bc_game("BC-Semi-3", "BC-S3A", "BC-S3B", "BC-S3C", stage="Semi", pool_id="", round_num=3),
            _bc_game("BC-Final", "WIN-1", "WIN-2", "WIN-3", stage="Final", pool_id="", round_num=1),
        ],
        resources=[_bc_resource("BC-ROOM-1", close_time="12:00")],
    )
    si["precedence"] = [
        {"before_game_id": "BC-Semi-1", "after_game_id": "BC-Final", "min_gap_slots": 1},
        {"before_game_id": "BC-Semi-2", "after_game_id": "BC-Final", "min_gap_slots": 1},
        {"before_game_id": "BC-Semi-3", "after_game_id": "BC-Final", "min_gap_slots": 1},
    ]

    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    slot_by_game = {row["game_id"]: row["slot"] for row in result["assignments"]}
    assert slot_by_game["BC-Final"] == "Sat-1-11:00"


def test_solve_bc_precedence_keeps_semis_after_pool_rounds():
    """BC semifinals must not start before all BC pool rounds are complete."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = _minimal_schedule_input(
        games=[
            _bc_game("BC-P1-RR-1", "BC::A", "BC::B", "BC::C", stage="Pool", pool_id="P1", round_num=1),
            _bc_game("BC-P2-RR-1", "BC::D", "BC::E", "BC::F", stage="Pool", pool_id="P2", round_num=2),
            _bc_game("BC-Semi-1", "BC-S1A", "BC-S1B", "BC-S1C", stage="Semi", pool_id="", round_num=1),
            _bc_game("BC-Semi-2", "BC-S2A", "BC-S2B", "BC-S2C", stage="Semi", pool_id="", round_num=2),
            _bc_game("BC-Semi-3", "BC-S3A", "BC-S3B", "BC-S3C", stage="Semi", pool_id="", round_num=3),
            _bc_game("BC-Final", "WIN-1", "WIN-2", "WIN-3", stage="Final", pool_id="", round_num=1),
        ],
        resources=[_bc_resource("BC-ROOM-1", close_time="14:00")],
    )
    pool_game_ids = ["BC-P1-RR-1", "BC-P2-RR-1"]
    semi_ids = ["BC-Semi-1", "BC-Semi-2", "BC-Semi-3"]
    si["precedence"] = (
        [
            {"before_game_id": pool_game_id, "after_game_id": semi_id, "min_gap_slots": 1}
            for pool_game_id in pool_game_ids
            for semi_id in semi_ids
        ]
        + [
            {"before_game_id": semi_id, "after_game_id": "BC-Final", "min_gap_slots": 1}
            for semi_id in semi_ids
        ]
    )

    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL

    sorted_slots = sorted({row["slot"] for row in result["assignments"]})
    slot_index = {slot: idx for idx, slot in enumerate(sorted_slots)}
    slot_by_game = {row["game_id"]: row["slot"] for row in result["assignments"]}
    pool_max = max(slot_index[slot_by_game[game_id]] for game_id in pool_game_ids)
    semi_min = min(slot_index[slot_by_game[game_id]] for game_id in semi_ids)
    final_idx = slot_index[slot_by_game["BC-Final"]]

    assert pool_max < semi_min
    assert max(slot_index[slot_by_game[game_id]] for game_id in semi_ids) < final_idx


def test_solve_soccer_precedence_keeps_final_after_pool_games():
    """Soccer semis/final/3rd must come after pool play on the field queue."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    soccer_resource = {
        "resource_id": "SOC-ROOM-1",
        "resource_type": "Soccer Field",
        "label": "Field-1",
        "day": "Sat-1",
        "open_time": "08:00",
        "close_time": "14:00",
        "slot_minutes": 60,
    }
    soccer_game = lambda game_id, team_a, team_b, stage="Pool", pool_id="P1", round_num=1: {
        "game_id": game_id,
        "event": "Soccer - Coed Exhibition",
        "stage": stage,
        "pool_id": pool_id,
        "round": round_num,
        "team_a_id": team_a,
        "team_b_id": team_b,
        "duration_minutes": 60,
        "resource_type": "Soccer Field",
        "earliest_slot": None,
        "latest_slot": None,
    }

    si = _minimal_schedule_input(
        games=[
            soccer_game("SOC-01", "SOC::A", "SOC::B", stage="Pool", pool_id="P1", round_num=1),
            soccer_game("SOC-02", "SOC::C", "SOC::D", stage="Pool", pool_id="P2", round_num=2),
            soccer_game("SOC-Semi-1", "SOC-Seed-1", "SOC-Seed-4", stage="Semi", pool_id="", round_num=1),
            soccer_game("SOC-Semi-2", "SOC-Seed-2", "SOC-Seed-3", stage="Semi", pool_id="", round_num=2),
            soccer_game("SOC-Final", "WIN-SOC-Semi-1", "WIN-SOC-Semi-2", stage="Final", pool_id="", round_num=1),
            soccer_game("SOC-3rd", "LOS-SOC-Semi-1", "LOS-SOC-Semi-2", stage="3rd", pool_id="", round_num=1),
        ],
        resources=[soccer_resource],
    )
    pool_game_ids = ["SOC-01", "SOC-02"]
    semi_ids = ["SOC-Semi-1", "SOC-Semi-2"]
    si["precedence"] = (
        [
            {"before_game_id": pool_game_id, "after_game_id": semi_id, "min_gap_slots": 1}
            for pool_game_id in pool_game_ids
            for semi_id in semi_ids
        ]
        + [
            {"before_game_id": semi_id, "after_game_id": "SOC-Final", "min_gap_slots": 1}
            for semi_id in semi_ids
        ]
        + [
            {"before_game_id": semi_id, "after_game_id": "SOC-3rd", "min_gap_slots": 1}
            for semi_id in semi_ids
        ]
    )

    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL

    sorted_slots = sorted({row["slot"] for row in result["assignments"]})
    slot_index = {slot: idx for idx, slot in enumerate(sorted_slots)}
    slot_by_game = {row["game_id"]: row["slot"] for row in result["assignments"]}
    pool_max = max(slot_index[slot_by_game[game_id]] for game_id in pool_game_ids)
    semi_min = min(slot_index[slot_by_game[game_id]] for game_id in semi_ids)
    final_idx = slot_index[slot_by_game["SOC-Final"]]
    third_idx = slot_index[slot_by_game["SOC-3rd"]]

    assert pool_max < semi_min
    assert max(slot_index[slot_by_game[game_id]] for game_id in semi_ids) < final_idx
    assert max(slot_index[slot_by_game[game_id]] for game_id in semi_ids) < third_idx


def test_solve_precedence_waits_for_multislot_game_completion():
    """A later round cannot start while a multi-slot earlier round is active."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    games = [
        {
            "game_id": "TEN-Men-Singles-Semi-1",
            "event": "Tennis",
            "stage": "Semi",
            "pool_id": "",
            "round": 1,
            "team_a_id": None,
            "team_b_id": None,
            "duration_minutes": 60,
            "resource_type": "Tennis Court",
            "earliest_slot": None,
            "latest_slot": None,
        },
        {
            "game_id": "TEN-Men-Singles-Semi-2",
            "event": "Tennis",
            "stage": "Semi",
            "pool_id": "",
            "round": 1,
            "team_a_id": None,
            "team_b_id": None,
            "duration_minutes": 60,
            "resource_type": "Tennis Court",
            "earliest_slot": None,
            "latest_slot": None,
        },
        {
            "game_id": "TEN-Men-Singles-Final",
            "event": "Tennis",
            "stage": "Final",
            "pool_id": "",
            "round": 2,
            "team_a_id": None,
            "team_b_id": None,
            "duration_minutes": 60,
            "resource_type": "Tennis Court",
            "earliest_slot": None,
            "latest_slot": None,
        },
    ]
    resources = [
        {
            "resource_id": f"TEN-Sat-1-{court}",
            "resource_type": "Tennis Court",
            "label": f"Court-{court}",
            "day": "Sat-1",
            "open_time": "08:00",
            "close_time": "10:30",
            "slot_minutes": 30,
        }
        for court in range(1, 4)
    ]
    precedence = [
        {
            "before_game_id": semi_id,
            "after_game_id": "TEN-Men-Singles-Final",
            "min_gap_slots": 1,
        }
        for semi_id in (
            "TEN-Men-Singles-Semi-1",
            "TEN-Men-Singles-Semi-2",
        )
    ]

    result = solve(
        {
            "games": games,
            "resources": resources,
            "precedence": precedence,
            "day_order": ["Sat-1"],
        },
        timeout_seconds=10.0,
    )

    assert result["status"] == STATUS_OPTIMAL
    starts = {
        row["game_id"]: int(row["slot"][-5:-3]) * 60 + int(row["slot"][-2:])
        for row in result["assignments"]
    }
    assert starts["TEN-Men-Singles-Final"] >= max(
        starts["TEN-Men-Singles-Semi-1"] + 60,
        starts["TEN-Men-Singles-Semi-2"] + 60,
    )


def test_solve_team_conflict_infeasible():
    """Two games sharing a team on a single slot/court must be INFEASIBLE."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_INFEASIBLE
    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "BBM-P1-T1", "BBM-P1-T2"),
            _gym_game("G2", "BBM-P1-T1", "BBM-P1-T3"),  # T1 in both games
        ],
        resources=[_gym_resource("GYM-Sat-1-1", close_time="09:00")],  # only 1 slot
    )
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_INFEASIBLE


def test_solve_court_type_routing():
    """A Badminton game must not be assigned to a Gym Court resource.

    With no compatible resources the pool is infeasible, so downstream JSON and
    workbook consumers do not see an OPTIMAL status beside dropped games.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_INFEASIBLE
    si = _minimal_schedule_input(
        games=[{
            "game_id": "G1", "event": "Badminton",
            "stage": "R1", "pool_id": "", "round": 1,
            "team_a_id": "A", "team_b_id": "B",
            "duration_minutes": 25, "resource_type": "Badminton Court",
            "earliest_slot": None, "latest_slot": None,
        }],
        resources=[_gym_resource("GYM-Sat-1-1")],  # only Gym Court — wrong type
    )
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_INFEASIBLE
    assert result["assignments"] == []
    assert "G1" in result["unscheduled"]
    pool = result["pool_results"][0]
    assert pool["status"] == STATUS_INFEASIBLE
    assert "diagnostics" in pool


def test_solve_min_rest_between_games():
    """A team with two games must not play in adjacent slots (C3 fix for C6 intent check).

    The assertion compares global slot-index distance (>= 2 = at least one slot gap)
    rather than minutes, so it stays valid if slot_minutes changes.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL, _slot_sort_key
    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "BBM-P1-T1", "BBM-P1-T2"),
            _gym_game("G2", "BBM-P1-T1", "BBM-P1-T3"),  # T1 appears in both
        ],
        resources=[
            _gym_resource("GYM-Sat-1-1", close_time="12:00"),  # 4 slots: 08-09-10-11
            _gym_resource("GYM-Sat-1-2", close_time="12:00"),
        ],
    )
    resources = [
        _gym_resource("GYM-Sat-1-1", close_time="12:00"),
        _gym_resource("GYM-Sat-1-2", close_time="12:00"),
    ]
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    assigned = {a["game_id"]: a["slot"] for a in result["assignments"]}
    # Rebuild the same global slot ordering the solver used, then check distance.
    # This avoids hardcoding slot_minutes (the original C3 coupling issue).
    from scheduler import build_resource_slots
    all_labels = sorted(
        {s for sl in build_resource_slots(resources).values() for s in sl},
        key=_slot_sort_key,
    )
    slot_idx = {s: i for i, s in enumerate(all_labels)}
    assert abs(slot_idx[assigned["G1"]] - slot_idx[assigned["G2"]]) >= 2, (
        f"T1 played in adjacent slots: {assigned['G1']} and {assigned['G2']}"
    )


def test_solve_respects_latest_slot_bound():
    """A game whose latest start is before all available starts must stay unscheduled."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_INFEASIBLE

    si = _minimal_schedule_input(
        games=[{
            **_gym_game("G1", "T1", "T2"),
            "latest_slot": "Sat-2-16:00",
        }],
        resources=[_gym_resource("GYM-Sun-2-1", day="Sun-2", open_time="12:00", close_time="14:00")],
    )
    si["day_order"] = ["Sat-2", "Sun-2"]

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_INFEASIBLE
    assert result["assignments"] == []
    assert "G1" in result["unscheduled"]


def test_solve_respects_earliest_slot_bound():
    """A game whose earliest start is after all available starts must stay unscheduled."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_INFEASIBLE

    si = _minimal_schedule_input(
        games=[{
            **_gym_game("G1", "T1", "T2"),
            "earliest_slot": "Sun-2-12:00",
        }],
        resources=[_gym_resource("GYM-Sat-2-1", day="Sat-2", open_time="12:00", close_time="14:00")],
    )
    si["day_order"] = ["Sat-2", "Sun-2"]

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_INFEASIBLE
    assert result["assignments"] == []
    assert "G1" in result["unscheduled"]


def test_solve_empty_input():
    """An input with no games produces OPTIMAL with empty assignments."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(games=[], resources=[])
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    assert result["assignments"] == []
    assert result["unscheduled"] == []


def test_solve_volleyball_prefers_same_court_gender_blocks():
    """When finish time is tied, volleyball courts should avoid Men/Women flips."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = _minimal_schedule_input(
        games=[
            _volleyball_game("VBM-1", "Volleyball - Men Team", "VBM-T1", "VBM-T2"),
            _volleyball_game("VBM-2", "Volleyball - Men Team", "VBM-T3", "VBM-T4"),
            _volleyball_game("VBW-1", "Volleyball - Women Team", "VBW-T1", "VBW-T2"),
            _volleyball_game("VBW-2", "Volleyball - Women Team", "VBW-T3", "VBW-T4"),
        ],
        resources=[
            _volleyball_resource("VB-1"),
            _volleyball_resource("VB-2"),
        ],
    )

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    assert result["unscheduled"] == []
    volleyball_pool = next(
        pr for pr in result["pool_results"] if pr["resource_type"] == "Volleyball Court"
    )
    assert volleyball_pool["volleyball_adjacent_switches"] == 0

    event_by_game = {game["game_id"]: game["event"] for game in si["games"]}
    per_resource: dict[str, list[tuple[str, str]]] = {}
    for assignment in result["assignments"]:
        per_resource.setdefault(assignment["resource_id"], []).append(
            (assignment["slot"], event_by_game[assignment["game_id"]])
        )

    for resource_id, slots in per_resource.items():
        slots.sort()
        if len(slots) < 2:
            continue
        categories = ["Men" if "Men" in event else "Women" for _, event in slots]
        assert len(set(categories)) == 1, (
            f"{resource_id} should keep the same volleyball category across adjacent slots, "
            f"but got {slots}"
        )


def test_solve_core_gym_pool_avoids_cross_sport_same_slot_conflict():
    """Core gym games sharing athletes should be staggered when enough slots exist."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = {
        "games": [
            _core_gym_game(
                "BBM-01",
                "Basketball - Men Team",
                "BBM::OCB",
                "BBM::ANH",
                "Basketball Court",
            ),
            _core_gym_game(
                "VBM-01",
                "Volleyball - Men Team",
                "VBM::OCB",
                "VBM::RPC",
                "Volleyball Court",
            ),
        ],
        "resources": [
            _core_gym_resource("BB-1", "Basketball Court"),
            _core_gym_resource("VB-1", "Volleyball Court"),
        ],
        "team_conflicts": [
            {
                "team_a_id": "BBM::OCB",
                "team_a_label": "OCB",
                "event_a": "Basketball - Men Team",
                "team_b_id": "VBM::OCB",
                "team_b_label": "OCB",
                "event_b": "Volleyball - Men Team",
                "shared_count": 2,
                "primary_overlap_count": 2,
                "secondary_only_count": 0,
                "shared_participant_names": ["An", "Binh"],
            }
        ],
    }

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    slots = {a["game_id"]: a["slot"] for a in result["assignments"]}
    assert slots["BBM-01"] != slots["VBM-01"]
    gym_pool = next(pr for pr in result["pool_results"] if pr["resource_type"] == "Gym Core")
    assert gym_pool["cross_sport_same_slot_conflicts"] == 0
    assert result["conflict_audit_summary"]["separated_edges"] == 1
    assert result["conflict_audit"][0]["status"] == "SeparatedInSchedule"


def test_solve_core_gym_pool_reports_unavoidable_cross_sport_conflict():
    """When only one shared slot exists, the conflict audit should show the overlap."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = {
        "games": [
            _core_gym_game(
                "BBM-01",
                "Basketball - Men Team",
                "BBM::OCB",
                "BBM::ANH",
                "Basketball Court",
            ),
            _core_gym_game(
                "VBM-01",
                "Volleyball - Men Team",
                "VBM::OCB",
                "VBM::RPC",
                "Volleyball Court",
            ),
        ],
        "resources": [
            {
                **_core_gym_resource("BB-1", "Basketball Court"),
                "close_time": "09:00",
            },
            {
                **_core_gym_resource("VB-1", "Volleyball Court"),
                "close_time": "09:00",
            },
        ],
        "team_conflicts": [
            {
                "team_a_id": "BBM::OCB",
                "team_a_label": "OCB",
                "event_a": "Basketball - Men Team",
                "team_b_id": "VBM::OCB",
                "team_b_label": "OCB",
                "event_b": "Volleyball - Men Team",
                "shared_count": 1,
                "primary_overlap_count": 1,
                "secondary_only_count": 0,
                "shared_participant_names": ["An"],
            }
        ],
    }

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    gym_pool = next(pr for pr in result["pool_results"] if pr["resource_type"] == "Gym Core")
    assert gym_pool["cross_sport_same_slot_conflicts"] == 1
    assert result["conflict_audit_summary"]["overlapping_edges"] == 1
    assert result["conflict_audit"][0]["status"] == "ConflictRemains"
    assert "BBM-01" in result["conflict_audit"][0]["overlap_game_pairs"]


def test_solve_core_gym_pool_prioritizes_primary_conflicts_over_secondary():
    """When one overlap is unavoidable, protect the primary-sport edge first."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = {
        "games": [
            _core_gym_game(
                "BBM-01",
                "Basketball - Men Team",
                "BBM::OCB",
                "BBM::RPC",
                "Basketball Court",
            ),
            _core_gym_game(
                "VBM-01",
                "Volleyball - Men Team",
                "VBM::OCB",
                "VBM::ANH",
                "Volleyball Court",
            ),
            _core_gym_game(
                "VBM-02",
                "Volleyball - Men Team",
                "VBM::TLC",
                "VBM::GAC",
                "Volleyball Court",
            ),
        ],
        "resources": [
            {
                **_core_gym_resource("BB-1", "Basketball Court"),
                "close_time": "09:00",
            },
            {
                **_core_gym_resource("VB-1", "Volleyball Court"),
                "close_time": "10:00",
            },
        ],
        "team_conflicts": [
            {
                "team_a_id": "BBM::OCB",
                "team_a_label": "OCB",
                "event_a": "Basketball - Men Team",
                "team_b_id": "VBM::OCB",
                "team_b_label": "OCB",
                "event_b": "Volleyball - Men Team",
                "shared_count": 1,
                "primary_overlap_count": 1,
            },
            {
                "team_a_id": "BBM::OCB",
                "team_a_label": "OCB",
                "event_a": "Basketball - Men Team",
                "team_b_id": "VBM::TLC",
                "team_b_label": "TLC",
                "event_b": "Volleyball - Men Team",
                "shared_count": 1,
                "primary_overlap_count": 0,
            },
        ],
    }

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    slots = {a["game_id"]: a["slot"] for a in result["assignments"]}
    assert slots["BBM-01"] == "Sat-1-08:00"
    assert slots["VBM-01"] == "Sat-1-09:00"
    assert slots["VBM-02"] == "Sat-1-08:00"
    assert result["conflict_audit_summary"]["remaining_primary_overlap_penalty"] == 0
    assert result["conflict_audit_summary"]["remaining_secondary_overlap_penalty"] == 1


def test_solve_racquet_pool_solves_after_gym_and_avoids_shared_athlete_slot():
    """Decision 5 (Issue #158): team sports schedule first; a racquet game with a
    shared athlete adapts onto a different slot than the fixed gym game."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = {
        "games": [
            _core_gym_game(
                "BBM-01", "Basketball - Men Team",
                "BBM::OCB", "BBM::ANH", "Basketball Court",
            ),
            {
                "game_id": "BAD-Men-Doubles-01", "event": "Badminton",
                "stage": "R1", "pool_id": "", "round": 1,
                "team_a_id": "BAD-Men-Doubles-E01", "team_b_id": "BAD-Men-Doubles-E02",
                "duration_minutes": 60, "resource_type": "Badminton Court",
                "earliest_slot": None, "latest_slot": None,
            },
        ],
        "resources": [
            # Gym court with a single slot: BBM-01 is pinned to Sat-1-08:00.
            {**_core_gym_resource("BB-1", "Basketball Court"), "close_time": "09:00"},
            # Badminton court with two slots so the racquet game can move.
            {
                "resource_id": "BAD-1", "resource_type": "Badminton Court",
                "label": "BAD-1", "day": "Sat-1",
                "open_time": "08:00", "close_time": "10:00", "slot_minutes": 60,
            },
        ],
        "team_conflicts": [
            {
                "team_a_id": "BBM::OCB", "team_a_label": "OCB",
                "event_a": "Basketball - Men Team",
                "team_b_id": "BAD-Men-Doubles-E01", "team_b_label": "E01",
                "event_b": "Badminton",
                "shared_count": 1, "primary_overlap_count": 1,
                "secondary_only_count": 0, "shared_participant_names": ["Sang"],
            }
        ],
    }

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    slots = {a["game_id"]: a["slot"] for a in result["assignments"]}
    assert slots["BBM-01"] == "Sat-1-08:00"  # team sport fixed first
    assert slots["BAD-Men-Doubles-01"] == "Sat-1-09:00"  # racquet adapts around it
    assert result["conflict_audit_summary"]["separated_edges"] == 1
    assert result["conflict_audit_summary"]["overlapping_edges"] == 0


def test_cross_pool_avoidance_detects_partial_time_overlap():
    """P1 fix: 60-min basketball at 08:00 must block badminton's 08:30 slot too.

    Before the fix, C3x used exact slot-label matching; Badminton's 08:30 slot
    label was not in the basketball team's occupied-slot set, so the constraint
    was silently skipped.  After the fix, interval-based comparison catches it.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = {
        "games": [
            _core_gym_game(
                "BBM-01", "Basketball - Men Team",
                "BBM::OCB", "BBM::ANH", "Basketball Court",
            ),
            {
                "game_id": "BAD-Men-Doubles-01", "event": "Badminton",
                "stage": "R1", "pool_id": "", "round": 1,
                "team_a_id": "BAD-Men-Doubles-E01", "team_b_id": "BAD-Men-Doubles-E02",
                "duration_minutes": 30, "resource_type": "Badminton Court",
                "earliest_slot": None, "latest_slot": None,
            },
        ],
        "resources": [
            # Basketball: 60-min slot, only one slot (08:00–09:00)
            {**_core_gym_resource("BB-1", "Basketball Court"), "close_time": "09:00"},
            # Badminton: 30-min slots at 08:00, 08:30, 09:00 — three choices
            {
                "resource_id": "BAD-1", "resource_type": "Badminton Court",
                "label": "BAD-1", "day": "Sat-1",
                "open_time": "08:00", "close_time": "09:30", "slot_minutes": 30,
            },
        ],
        "team_conflicts": [
            {
                "team_a_id": "BBM::OCB", "team_a_label": "OCB",
                "event_a": "Basketball - Men Team",
                "team_b_id": "BAD-Men-Doubles-E01", "team_b_label": "E01",
                "event_b": "Badminton",
                "shared_count": 1, "primary_overlap_count": 1,
                "secondary_only_count": 0, "shared_participant_names": ["Sang"],
            }
        ],
    }

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    slots = {a["game_id"]: a["slot"] for a in result["assignments"]}
    assert slots["BBM-01"] == "Sat-1-08:00"
    # Badminton must land at 09:00, NOT at 08:30 (which partially overlaps 08:00-09:00)
    assert slots["BAD-Men-Doubles-01"] == "Sat-1-09:00"
    assert result["conflict_audit_summary"]["separated_edges"] == 1
    assert result["conflict_audit_summary"]["overlapping_edges"] == 0


def test_racquet_pool_order_uses_entry_count_across_divisions(monkeypatch):
    """Eight entries across four divisions solve before seven entries in one division."""
    from scheduler import solve, STATUS_OPTIMAL
    import scheduler

    solve_order = []

    def fake_solve_one_pool(pool_input, timeout_seconds):
        solve_order.append(pool_input["resources"][0]["resource_type"])
        return {
            "status": STATUS_OPTIMAL,
            "solver_wall_seconds": 0.0,
            "assignments": [],
            "unscheduled": [],
        }

    monkeypatch.setattr(scheduler, "_solve_one_pool", fake_solve_one_pool)

    games = []
    for index in range(6):
        games.append({
            "game_id": f"BAD-Men-Doubles-{index + 1:02d}",
            "division_id": "BAD-Men-Doubles",
            "division_entry_count": 7,
            "event": "Badminton", "stage": "R1", "pool_id": "",
            "round": index + 1, "team_a_id": None, "team_b_id": None,
            "duration_minutes": 60, "resource_type": "Badminton Court",
            "earliest_slot": None, "latest_slot": None,
        })
    for division_index in range(4):
        division_id = f"PCK-D{division_index + 1}"
        games.append({
            "game_id": f"{division_id}-01",
            "division_id": division_id,
            "division_entry_count": 2,
            "event": "Pickleball", "stage": "R1", "pool_id": "",
            "round": 1, "team_a_id": None, "team_b_id": None,
            "duration_minutes": 30, "resource_type": "Pickleball Court",
            "earliest_slot": None, "latest_slot": None,
        })

    solve({
        "games": games,
        "resources": [
            {
                "resource_id": "BAD-1", "resource_type": "Badminton Court",
                "day": "Sat-1", "open_time": "08:00", "close_time": "18:00",
                "slot_minutes": 60,
            },
            {
                "resource_id": "PCK-1", "resource_type": "Pickleball Court",
                "day": "Sat-1", "open_time": "08:00", "close_time": "18:00",
                "slot_minutes": 30,
            },
        ],
    }, timeout_seconds=1.0)

    assert solve_order == ["Pickleball Court", "Badminton Court"]


def test_build_infeasibility_diagnostics_reports_slot_shortage():
    """Capacity diagnostics summarize required vs available slots by resource type."""
    from scheduler import build_infeasibility_diagnostics

    si = _minimal_schedule_input(
        games=[
            {
                "game_id": "BAD-01", "event": "Badminton",
                "stage": "R1", "pool_id": "", "round": 1,
                "team_a_id": None, "team_b_id": None,
                "duration_minutes": 30, "resource_type": "Badminton Court",
                "earliest_slot": None, "latest_slot": None,
            },
            {
                "game_id": "BAD-02", "event": "Badminton",
                "stage": "R1", "pool_id": "", "round": 2,
                "team_a_id": None, "team_b_id": None,
                "duration_minutes": 30, "resource_type": "Badminton Court",
                "earliest_slot": None, "latest_slot": None,
            },
        ],
        resources=[{
            "resource_id": "BAD-1", "resource_type": "Badminton Court",
            "label": "Court-1", "day": "Day-1",
            "open_time": "09:00", "close_time": "09:30", "slot_minutes": 30,
        }],
    )

    diagnostics = build_infeasibility_diagnostics(si)
    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert diag["resource_type"] == "Badminton Court"
    assert diag["required_slots"] == 2
    assert diag["available_slots"] == 1
    assert diag["shortage_slots"] == 1
    assert diag["events"] == [{
        "event": "Badminton",
        "resource_type": "Badminton Court",
        "game_count": 2,
        "required_slots": 2,
    }]


def test_run_solve_schedule_writes_output(tmp_path):
    """run_solve_schedule writes a valid schedule_output.json and returns 0."""
    pytest.importorskip("ortools")
    from scheduler import run_solve_schedule, STATUS_OPTIMAL

    si = _minimal_schedule_input(
        games=[_gym_game("G1", "T1", "T2")],
        resources=[_gym_resource("GYM-Sat-1-1")],
    )
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(si), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"

    exit_code = run_solve_schedule(input_path, output_path)
    assert exit_code == 0
    assert output_path.exists()

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["status"] == STATUS_OPTIMAL
    assert "solved_at" in data
    assert "assignments" in data
    assert len(data["assignments"]) == 1
    assert data["unscheduled"] == []


def test_run_solve_schedule_infeasible_writes_diagnostics(tmp_path):
    """INFEASIBLE output includes lower-bound slot diagnostics for operators."""
    pytest.importorskip("ortools")
    from scheduler import run_solve_schedule, STATUS_INFEASIBLE

    si = _minimal_schedule_input(
        games=[
            {
                "game_id": "BAD-01", "event": "Badminton",
                "stage": "R1", "pool_id": "", "round": 1,
                "team_a_id": None, "team_b_id": None,
                "duration_minutes": 30, "resource_type": "Badminton Court",
                "earliest_slot": None, "latest_slot": None,
            },
            {
                "game_id": "BAD-02", "event": "Badminton",
                "stage": "R1", "pool_id": "", "round": 2,
                "team_a_id": None, "team_b_id": None,
                "duration_minutes": 30, "resource_type": "Badminton Court",
                "earliest_slot": None, "latest_slot": None,
            },
        ],
        resources=[{
            "resource_id": "BAD-1", "resource_type": "Badminton Court",
            "label": "Court-1", "day": "Day-1",
            "open_time": "09:00", "close_time": "09:30", "slot_minutes": 30,
        }],
    )
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(si), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"

    exit_code = run_solve_schedule(input_path, output_path)
    assert exit_code == 1
    assert output_path.exists()

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["status"] == STATUS_INFEASIBLE
    assert data["assignments"] == []
    assert sorted(data["unscheduled"]) == ["BAD-01", "BAD-02"]
    # diagnostics now live inside pool_results, not at the top level
    assert "pool_results" in data
    pool = data["pool_results"][0]
    assert pool["resource_type"] == "Badminton Court"
    assert "diagnostics" in pool
    diag = pool["diagnostics"][0]
    assert diag["resource_type"] == "Badminton Court"
    assert diag["required_slots"] == 2
    assert diag["available_slots"] == 1
    assert diag["shortage_slots"] == 1
    assert diag["events"][0]["event"] == "Badminton"


def test_run_solve_schedule_missing_input(tmp_path):
    """run_solve_schedule returns exit code 3 when input file is missing."""
    pytest.importorskip("ortools")
    from scheduler import run_solve_schedule

    exit_code = run_solve_schedule(
        tmp_path / "nonexistent.json",
        tmp_path / "out.json",
    )
    assert exit_code == 3


def test_run_solve_schedule_unroutable_game_exits_1(tmp_path):
    """A game with no compatible resource returns exit 1 and writes INFEASIBLE output.

    Before the A2 fix, run_solve_schedule returned 0 for this case, silently
    producing an incomplete schedule that produce-schedule would render without
    the missing game.
    """
    pytest.importorskip("ortools")
    from scheduler import run_solve_schedule, STATUS_INFEASIBLE

    si = _minimal_schedule_input(
        games=[{
            "game_id": "BAD-01", "event": "Badminton",
            "stage": "R1", "pool_id": "", "round": 1,
            "team_a_id": "A", "team_b_id": "B",
            "duration_minutes": 30, "resource_type": "Badminton Court",
            "earliest_slot": None, "latest_slot": None,
        }],
        resources=[_gym_resource("GYM-Sat-1-1")],  # Gym Court only — wrong type
    )
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(__import__("json").dumps(si), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"

    exit_code = run_solve_schedule(input_path, output_path)
    assert exit_code == 1

    data = __import__("json").loads(output_path.read_text(encoding="utf-8"))
    assert data["status"] == STATUS_INFEASIBLE
    assert "BAD-01" in data["unscheduled"]


def test_solve_unroutable_pool_makes_top_level_partial():
    """A solved pool plus an unroutable pool must aggregate to PARTIAL, not OPTIMAL."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_PARTIAL, STATUS_OPTIMAL, STATUS_INFEASIBLE

    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "T1", "T2"),
            _bad_game("BAD-01", "A", "B"),
        ],
        resources=[_gym_resource("GYM-Sat-1-1")],  # no Badminton Court resources
    )
    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_PARTIAL
    assert any(a["game_id"] == "G1" for a in result["assignments"])
    assert result["unscheduled"] == ["BAD-01"]
    pools = {pr["resource_type"]: pr for pr in result["pool_results"]}
    assert pools["Gym Court"]["status"] == STATUS_OPTIMAL
    assert pools["Badminton Court"]["status"] == STATUS_INFEASIBLE
    assert "diagnostics" in pools["Badminton Court"]


def test_solver_uses_fixed_random_seed():
    """Two identical solve() calls produce the same assignment order (B6 determinism)."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "T1", "T2"),
            _gym_game("G2", "T3", "T4"),
            _gym_game("G3", "T1", "T3"),
        ],
        resources=[_gym_resource("GYM-Sat-1-1", close_time="12:00")],
    )
    result_a = solve(si, timeout_seconds=10.0)
    result_b = solve(si, timeout_seconds=10.0)

    assert result_a["status"] == STATUS_OPTIMAL
    assert result_b["status"] == STATUS_OPTIMAL
    slots_a = {a["game_id"]: a["slot"] for a in result_a["assignments"]}
    slots_b = {a["game_id"]: a["slot"] for a in result_b["assignments"]}
    assert slots_a == slots_b


# ---------------------------------------------------------------------------
# Pool decomposition tests
# ---------------------------------------------------------------------------

def _bad_resource(resource_id, day="Day-1", open_time="09:00", close_time="10:30"):
    return {
        "resource_id": resource_id, "resource_type": "Badminton Court",
        "label": "Court-1", "day": day,
        "open_time": open_time, "close_time": close_time, "slot_minutes": 30,
    }


def _bad_game(game_id, team_a="A", team_b="B"):
    return {
        "game_id": game_id, "event": "Badminton",
        "stage": "R1", "pool_id": "", "round": 1,
        "team_a_id": team_a, "team_b_id": team_b,
        "duration_minutes": 30, "resource_type": "Badminton Court",
        "earliest_slot": None, "latest_slot": None,
    }


def test_solve_pool_results_always_present():
    """solve() always returns pool_results even for a single resource type."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(
        games=[_gym_game("G1", "T1", "T2")],
        resources=[
            _gym_resource("GYM-Sat-1-1"),
            _gym_resource("GYM-Sat-2-1", day="Sat-2"),
        ],
    )
    result = solve(si)
    assert result["status"] == STATUS_OPTIMAL
    assert "pool_results" in result
    assert len(result["pool_results"]) == 1
    pr = result["pool_results"][0]
    assert pr["resource_type"] == "Gym Court"
    assert pr["status"] == STATUS_OPTIMAL
    assert len(pr["assignments"]) == 1


def test_solve_partial_feasibility():
    """Two independent pools: one feasible, one infeasible → PARTIAL status.

    Gym Court pool has enough slots; Badminton Court pool does not.
    The Gym Court assignments must survive even though Badminton is infeasible.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_PARTIAL, STATUS_OPTIMAL, STATUS_INFEASIBLE

    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "T1", "T2"),                    # Gym Court — feasible
            _bad_game("BAD-01", "A", "B"),                   # Badminton Court — infeasible
            _bad_game("BAD-02", "C", "D"),                   # Badminton Court — infeasible
        ],
        resources=[
            _gym_resource("GYM-Sat-1-1"),                    # Gym Court: 3 slots
            _bad_resource("BAD-1", close_time="09:30"),      # Badminton: only 1 slot for 2 games
        ],
    )
    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_PARTIAL

    # Gym assignment must be preserved
    gym_assignments = [a for a in result["assignments"] if a["game_id"] == "G1"]
    assert len(gym_assignments) == 1

    # Badminton games are unscheduled
    assert "BAD-01" in result["unscheduled"] or "BAD-02" in result["unscheduled"]

    # pool_results carries per-pool outcome
    pools = {pr["resource_type"]: pr for pr in result["pool_results"]}
    assert pools["Gym Court"]["status"] == STATUS_OPTIMAL
    assert pools["Badminton Court"]["status"] == STATUS_INFEASIBLE
    assert "diagnostics" in pools["Badminton Court"]


def test_solve_two_independent_pools_both_optimal():
    """Two pools with sufficient resources both solve OPTIMAL independently."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "T1", "T2"),
            _bad_game("BAD-01", "A", "B"),
        ],
        resources=[
            _gym_resource("GYM-Sat-1-1"),
            _bad_resource("BAD-1"),                          # 3 slots — enough for 1 game
        ],
    )
    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    assert len(result["assignments"]) == 2
    assert result["unscheduled"] == []
    pools = {pr["resource_type"]: pr for pr in result["pool_results"]}
    assert pools["Gym Court"]["status"] == STATUS_OPTIMAL
    assert pools["Badminton Court"]["status"] == STATUS_OPTIMAL


def test_solve_partial_exit_code(tmp_path):
    """run_solve_schedule returns exit code 1 for PARTIAL and writes pool_results."""
    pytest.importorskip("ortools")
    from scheduler import run_solve_schedule, STATUS_PARTIAL

    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "T1", "T2"),
            _bad_game("BAD-01"),
            _bad_game("BAD-02"),
        ],
        resources=[
            _gym_resource("GYM-Sat-1-1"),
            _bad_resource("BAD-1", close_time="09:30"),      # 1 slot, 2 games → infeasible
        ],
    )
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(si), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"

    exit_code = run_solve_schedule(input_path, output_path)
    assert exit_code == 1

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["status"] == STATUS_PARTIAL
    assert any(a["game_id"] == "G1" for a in data["assignments"])
    pools = {pr["resource_type"]: pr for pr in data["pool_results"]}
    assert "diagnostics" in pools["Badminton Court"]


def test_solve_c6_min_rest_does_not_span_day_boundary():
    """A team that plays the last slot of one day and the first of the next must be OPTIMAL.

    Before the A1 fix, contiguous global slot indices made the last slot of Sat-1 and
    the first slot of Sun-1 appear 'adjacent', triggering a false min-rest violation.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "T1", "T2"),   # forced onto Sat-1 (only available slot)
            _gym_game("G2", "T1", "T3"),   # forced onto Sun-1 (only available slot)
        ],
        resources=[
            _gym_resource("GYM-Sat-1-1", day="Sat-1", open_time="20:00", close_time="21:00"),
            _gym_resource("GYM-Sun-1-1", day="Sun-1", open_time="13:00", close_time="14:00"),
        ],
    )
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    assert len(result["assignments"]) == 2


def test_solve_playoff_slots_passed_through():
    """Playoff slots from schedule_input are merged into the solver output assignments."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(
        games=[_gym_game("G1", "T1", "T2")],
        resources=[
            _gym_resource("GYM-Sat-1-1"),
            _gym_resource("GYM-Sat-2-1", day="Sat-2"),
        ],
    )
    si["playoff_slots"] = [
        {"game_id": "BBM-Final", "event": "Basketball - Men Team", "stage": "Final",
         "resource_id": "GYM-Sat-2-1", "slot": "Sat-2-09:00"},
    ]
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    game_ids = {a["game_id"] for a in result["assignments"]}
    assert "G1" in game_ids
    assert "BBM-Final" in game_ids
    final_asgn = next(a for a in result["assignments"] if a["game_id"] == "BBM-Final")
    assert final_asgn["slot"] == "Sat-2-09:00"
    assert final_asgn["stage"] == "Final"


def test_solve_playoff_slots_reserve_pool_slots():
    """Manual playoff slots reserve the same court/time from the pool-play solver."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(
        games=[_gym_game("G1", "T1", "T2")],
        resources=[_gym_resource("GYM-Sat-1-1", close_time="10:00")],
    )
    si["playoff_slots"] = [
        {
            "game_id": "BBM-Final",
            "event": "Basketball - Men Team",
            "stage": "Final",
            "resource_id": "GYM-Sat-1-1",
            "slot": "Sat-1-08:00",
        },
    ]
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    pool_asgn = next(a for a in result["assignments"] if a["game_id"] == "G1")
    final_asgn = next(a for a in result["assignments"] if a["game_id"] == "BBM-Final")
    assert pool_asgn["slot"] == "Sat-1-09:00"
    assert final_asgn["slot"] == "Sat-1-08:00"


def test_solve_playoff_slot_replaces_existing_modeled_assignment():
    """When a pinned playoff row targets a modeled game_id, the pinned slot should win once."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(
        games=[
            _gym_game("G1", "T1", "T2"),
            _gym_game("BC-Final", "T3", "T4"),
        ],
        resources=[
            _gym_resource("GYM-Sat-1-1", close_time="10:00"),
            _gym_resource("GYM-Sat-2-1", day="Sat-2", close_time="10:00"),
        ],
    )
    si["playoff_slots"] = [
        {
            "game_id": "BC-Final",
            "event": "Bible Challenge - Mixed Team",
            "stage": "Final",
            "resource_id": "GYM-Sat-2-1",
            "slot": "Sat-2-09:00",
        },
    ]

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    bc_rows = [row for row in result["assignments"] if row["game_id"] == "BC-Final"]
    assert len(bc_rows) == 1
    assert bc_rows[0]["resource_id"] == "GYM-Sat-2-1"
    assert bc_rows[0]["slot"] == "Sat-2-09:00"


def test_solve_packs_games_into_earliest_day_when_capacity_allows():
    """Regression for Issue #134: games with capacity on Day-1 should not scatter to Day-2.

    The pre-fix solver minimized only `max(global_slot)`, so once any game had to
    land on a late day the cost was zero for putting more games there too. The new
    sum-of-slot-indices tier breaks that degenerate tie and packs games into the
    earliest available day first.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    # Friday has 4 tables × 4 slots = 16 placements available (much more than 4 games).
    # Sunday has 4 tables × 1 slot = 4 placements. Pre-fix the solver would scatter.
    fri_resources = [
        {
            "resource_id": f"TT-Fri-1-{i}", "resource_type": "Table Tennis Table",
            "label": f"Table-{i}", "day": "Fri-1",
            "open_time": "17:00", "close_time": "18:20", "slot_minutes": 20,
        }
        for i in range(1, 5)
    ]
    sun_resources = [
        {
            "resource_id": f"TT-Sun-1-{i}", "resource_type": "Table Tennis Table",
            "label": f"Table-{i}", "day": "Sun-1",
            "open_time": "16:00", "close_time": "16:20", "slot_minutes": 20,
        }
        for i in range(1, 5)
    ]
    games = [
        {
            "game_id": f"TT-Singles-{i}", "event": "Table Tennis",
            "stage": "Pool", "pool_id": "P1", "round": 1,
            "team_a_id": f"T{i}A", "team_b_id": f"T{i}B",
            "duration_minutes": 20, "resource_type": "Table Tennis Table",
            "earliest_slot": None, "latest_slot": None,
        }
        for i in range(1, 5)
    ]
    # day_order reflects actual calendar dates: Fri-1 is the first event day,
    # Sun-1 is later in the same weekend series.
    si = {"games": games, "resources": fri_resources + sun_resources,
          "day_order": ["Fri-1", "Sun-1"]}

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    days_used = {a["slot"].split("-", 2)[0] + "-" + a["slot"].split("-", 2)[1]
                 for a in result["assignments"]}
    assert days_used == {"Fri-1"}, (
        f"Expected all 4 games on Fri-1 since capacity is ample; got days {days_used}"
    )


def test_solve_friday_preferred_over_sunday_in_day_ordering():
    """Regression for Issue #134 day-order bug: Fri-1 must beat Sun-2 in the slot ordering.

    Pre-fix _DAY_ORDER only knew Sat/Sun, so Fri-1 fell to 99 and the solver
    treated Friday slots as 'later' than Sunday, sending games to Sunday.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL

    fri_resource = {
        "resource_id": "TT-Fri-1-1", "resource_type": "Table Tennis Table",
        "label": "Table-1", "day": "Fri-1",
        "open_time": "17:00", "close_time": "17:20", "slot_minutes": 20,
    }
    sun_resource = {
        "resource_id": "TT-Sun-2-1", "resource_type": "Table Tennis Table",
        "label": "Table-1", "day": "Sun-2",
        "open_time": "16:00", "close_time": "16:20", "slot_minutes": 20,
    }
    game = {
        "game_id": "TT-1", "event": "Table Tennis",
        "stage": "Pool", "pool_id": "P1", "round": 1,
        "team_a_id": "A", "team_b_id": "B",
        "duration_minutes": 20, "resource_type": "Table Tennis Table",
        "earliest_slot": None, "latest_slot": None,
    }
    # day_order: Fri-1 is chronologically earlier than Sun-2 in this tournament.
    si = {"games": [game], "resources": [fri_resource, sun_resource],
          "day_order": ["Fri-1", "Sun-2"]}

    result = solve(si, timeout_seconds=10.0)

    assert result["status"] == STATUS_OPTIMAL
    assignment = result["assignments"][0]
    assert assignment["resource_id"] == "TT-Fri-1-1", (
        f"Single game must land on Friday (earlier day), got {assignment}"
    )


def test_solve_duplicate_playoff_slot_raises():
    """Duplicate manual playoff reservations fail loudly before rendering can hide them."""
    pytest.importorskip("ortools")
    from scheduler import solve
    si = _minimal_schedule_input(
        games=[_gym_game("G1", "T1", "T2")],
        resources=[_gym_resource("GYM-Sat-1-1", close_time="10:00")],
    )
    si["playoff_slots"] = [
        {
            "game_id": "BBM-Semi-1",
            "event": "Basketball - Men Team",
            "stage": "Semi",
            "resource_id": "GYM-Sat-1-1",
            "slot": "Sat-1-08:00",
        },
        {
            "game_id": "BBM-Final",
            "event": "Basketball - Men Team",
            "stage": "Final",
            "resource_id": "GYM-Sat-1-1",
            "slot": "Sat-1-08:00",
        },
    ]
    with pytest.raises(ValueError, match="Duplicate playoff slot reservation"):
        solve(si, timeout_seconds=10.0)


def test_validate_playoff_slots_rejects_overlapping_multislot_pins():
    """Different start slots still collide when their occupied intervals overlap."""
    from scheduler import validate_playoff_slots

    resources = [{
        "resource_id": "TT-Sun-2-1",
        "resource_type": "Table Tennis Table",
        "label": "Table-1",
        "day": "Sun-2",
        "open_time": "14:00",
        "close_time": "18:00",
        "slot_minutes": 20,
    }]
    playoff_slots = [
        {
            "game_id": "TT-Semi",
            "resource_id": "TT-Sun-2-1",
            "slot": "Sun-2-14:00",
            "duration_minutes": 120,
        },
        {
            "game_id": "TT-Final",
            "resource_id": "TT-Sun-2-1",
            "slot": "Sun-2-15:00",
            "duration_minutes": 120,
        },
    ]

    with pytest.raises(ValueError, match="Overlapping playoff slot reservations"):
        validate_playoff_slots(playoff_slots, resources)


def test_validate_playoff_slots_blocks_every_occupied_slot():
    """A multi-slot playoff pin removes its whole interval from pool play."""
    from scheduler import validate_playoff_slots

    resources = [{
        "resource_id": "TT-Sun-2-1",
        "resource_type": "Table Tennis Table",
        "label": "Table-1",
        "day": "Sun-2",
        "open_time": "14:00",
        "close_time": "16:00",
        "slot_minutes": 20,
    }]
    playoff_slots = [{
        "game_id": "TT-Final",
        "resource_id": "TT-Sun-2-1",
        "slot": "Sun-2-14:00",
        "duration_minutes": 60,
    }]

    validated, blocked = validate_playoff_slots(playoff_slots, resources)

    assert validated[0]["duration_minutes"] == 60
    assert blocked["Table Tennis Table"]["TT-Sun-2-1"] == {
        "Sun-2-14:00", "Sun-2-14:20", "Sun-2-14:40",
    }


def test_solve_pinned_final_cannot_precede_solver_semis():
    """Regression: pinned playoff Final must not appear before solver-assigned Semis.

    When a game exists in both games[] (auto-generated) and playoff_slots (manually
    pinned), the old code let the solver assign it freely, then silently overwrote
    the result with the manual pin — breaking Semi → Final precedence.  The fix
    excludes pinned games from the solver model and treats them as fixed reference
    points, so the solver constrains Semi to finish before the pinned Final time.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL, STATUS_INFEASIBLE

    def _semi_game(gid, ta, tb):
        return {
            "game_id": gid, "event": "Basketball - Men Team",
            "stage": "Semi", "pool_id": "", "round": 1,
            "team_a_id": ta, "team_b_id": tb,
            "duration_minutes": 60, "resource_type": "Gym Court",
            "earliest_slot": None, "latest_slot": None,
        }

    def _final_game(gid, ta, tb):
        return {
            "game_id": gid, "event": "Basketball - Men Team",
            "stage": "Final", "pool_id": "", "round": 1,
            "team_a_id": ta, "team_b_id": tb,
            "duration_minutes": 60, "resource_type": "Gym Court",
            "earliest_slot": None, "latest_slot": None,
        }

    precedence = [
        {"before_game_id": "VBM-Semi-1", "after_game_id": "VBM-Final", "min_gap_slots": 1},
        {"before_game_id": "VBM-Semi-2", "after_game_id": "VBM-Final", "min_gap_slots": 1},
    ]
    resources = [
        _gym_resource("GYM-1", day="Sun-1", open_time="12:00", close_time="17:00"),
        _gym_resource("GYM-2", day="Sun-1", open_time="12:00", close_time="17:00"),
    ]

    # Case A: valid pin — Final at 15:00 leaves room for both Semis before it
    si = _minimal_schedule_input(
        games=[
            _semi_game("VBM-Semi-1", "TA", "TB"),
            _semi_game("VBM-Semi-2", "TC", "TD"),
            _final_game("VBM-Final", "WIN-1", "WIN-2"),
        ],
        resources=resources,
    )
    si["precedence"] = precedence
    si["playoff_slots"] = [
        {"game_id": "VBM-Final", "event": "Basketball - Men Team", "stage": "Final",
         "resource_id": "GYM-1", "slot": "Sun-1-15:00"},
    ]
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    slot_by_game = {a["game_id"]: a["slot"] for a in result["assignments"]}
    assert slot_by_game["VBM-Final"] == "Sun-1-15:00"
    assert slot_by_game["VBM-Semi-1"] < "Sun-1-15:00", "Semi-1 must precede pinned Final"
    assert slot_by_game["VBM-Semi-2"] < "Sun-1-15:00", "Semi-2 must precede pinned Final"

    # Case B: impossible pin — Final at 12:00 with no prior slots for Semis; must be INFEASIBLE
    si2 = {**si}
    si2["playoff_slots"] = [
        {"game_id": "VBM-Final", "event": "Basketball - Men Team", "stage": "Final",
         "resource_id": "GYM-1", "slot": "Sun-1-12:00"},
    ]
    result2 = solve(si2, timeout_seconds=10.0)
    assert result2["status"] == STATUS_INFEASIBLE, (
        "Solver must reject an impossible pin where Final precedes Semis"
    )


def test_solve_qf_semi_gap_enforced():
    """Semi must start at least 2 slots after QF — min_gap_slots=2 enforces a 1-hour rest buffer.

    With slot_minutes=60 and min_gap_slots=2:
      QF at slot N → Semi must be at slot >= N+2 (one empty slot = 1 hour rest).
    Verify this is enforced by the solver: give 4 courts spanning 4 slots each
    (08:00–12:00), schedule two QF games and one Semi with min_gap_slots=2,
    and assert the Semi slot index is at least 2 greater than both QF slot indices.
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL, _slot_sort_key, build_resource_slots

    resources = [
        _gym_resource("GYM-1", day="Sat-1", open_time="08:00", close_time="12:00"),
        _gym_resource("GYM-2", day="Sat-1", open_time="08:00", close_time="12:00"),
        _gym_resource("GYM-3", day="Sat-1", open_time="08:00", close_time="12:00"),
        _gym_resource("GYM-4", day="Sat-1", open_time="08:00", close_time="12:00"),
    ]
    si = _minimal_schedule_input(
        games=[
            {**_gym_game("BBM-QF-1", "T1", "T2"), "latest_slot": None, "earliest_slot": None},
            {**_gym_game("BBM-QF-2", "T3", "T4"), "latest_slot": None, "earliest_slot": None},
            {**_gym_game("BBM-Semi-1", "WIN-QF1", "WIN-QF2"), "latest_slot": None, "earliest_slot": None},
        ],
        resources=resources,
    )
    si["precedence"] = [
        {"before_game_id": "BBM-QF-1", "after_game_id": "BBM-Semi-1", "min_gap_slots": 2},
        {"before_game_id": "BBM-QF-2", "after_game_id": "BBM-Semi-1", "min_gap_slots": 2},
    ]

    result = solve(si, timeout_seconds=15.0)
    assert result["status"] == STATUS_OPTIMAL
    assert result["unscheduled"] == []

    slot_by_game = {a["game_id"]: a["slot"] for a in result["assignments"]}
    all_labels = sorted(
        {s for sl in build_resource_slots(resources).values() for s in sl},
        key=_slot_sort_key,
    )
    slot_idx = {s: i for i, s in enumerate(all_labels)}

    qf1_idx = slot_idx[slot_by_game["BBM-QF-1"]]
    qf2_idx = slot_idx[slot_by_game["BBM-QF-2"]]
    semi_idx = slot_idx[slot_by_game["BBM-Semi-1"]]

    assert semi_idx >= qf1_idx + 2, (
        f"Semi-1 at slot {semi_idx} is too close to QF-1 at slot {qf1_idx} (need gap >= 2)"
    )
    assert semi_idx >= qf2_idx + 2, (
        f"Semi-1 at slot {semi_idx} is too close to QF-2 at slot {qf2_idx} (need gap >= 2)"
    )


def test_run_solve_schedule_timeout_writes_unknown(tmp_path, monkeypatch):
    """Solver timeout returns exit code 2 and writes a parseable output with status UNKNOWN.

    Monkeypatches _solve_one_pool to return STATUS_UNKNOWN immediately so the test
    never flakes on CI due to wall-clock timing.  Verifies the file is written (callers
    must still be able to inspect partial results) and that all required top-level keys
    are present.
    """
    pytest.importorskip("ortools")
    import scheduler as _scheduler
    from scheduler import STATUS_UNKNOWN, run_solve_schedule

    def _mock_timeout(pool_input, timeout_seconds):
        return {
            "status":              STATUS_UNKNOWN,
            "solver_wall_seconds": timeout_seconds,
            "assignments":         [],
            "unscheduled":         [g["game_id"] for g in pool_input.get("games", [])],
            "diagnostics":         [],
        }

    monkeypatch.setattr(_scheduler, "_solve_one_pool", _mock_timeout)

    si = _minimal_schedule_input(
        games=[_gym_game("G1", "T1", "T2"), _gym_game("G2", "T3", "T4")],
        resources=[_gym_resource("GYM-Sat-1-1")],
    )
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(si), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"

    exit_code = run_solve_schedule(input_path, output_path)

    assert exit_code == 2
    assert output_path.exists(), "schedule_output.json must be written even on timeout"

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["status"] == STATUS_UNKNOWN
    assert "solved_at" in data
    assert "assignments" in data
    assert "pool_results" in data
