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


# ---------------------------------------------------------------------------
# load_schedule_input
# ---------------------------------------------------------------------------

def test_load_schedule_input_valid(tmp_path):
    """load_schedule_input returns dict when all required keys are present."""
    from scheduler import load_schedule_input
    data = {"games": [], "resources": [], "precedence": []}
    path = tmp_path / "si.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load_schedule_input(path)
    assert result["games"] == []
    assert result["resources"] == []


def test_load_schedule_input_missing_key(tmp_path):
    """load_schedule_input raises ValueError when a required key is absent."""
    from scheduler import load_schedule_input
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"games": [], "resources": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="precedence"):
        load_schedule_input(path)


def test_load_schedule_input_file_not_found(tmp_path):
    """load_schedule_input raises an appropriate error for missing files."""
    from scheduler import load_schedule_input
    with pytest.raises(FileNotFoundError):
        load_schedule_input(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# solve() — requires ortools
# ---------------------------------------------------------------------------

def _minimal_schedule_input(games, resources, precedence=None):
    return {
        "games": games,
        "resources": resources,
        "precedence": precedence or [],
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

    With no compatible resources the game lands in 'unscheduled'; the solver
    still returns OPTIMAL (trivially — no constraints to violate for that game).
    """
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
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
    assert result["status"] == STATUS_OPTIMAL
    assert result["assignments"] == []
    assert "G1" in result["unscheduled"]


def test_solve_stage_ordering():
    """A Pool game must be assigned to an earlier slot than a Final game."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL, _slot_sort_key
    si = _minimal_schedule_input(
        games=[
            _gym_game("BBM-01", "BBM-P1-T1", "BBM-P1-T2", stage="Pool", pool_id="P1"),
            _gym_game("BBM-Final", "WIN-BBM-Semi-1", "WIN-BBM-Semi-2", stage="Final", pool_id=""),
        ],
        resources=[_gym_resource("GYM-Sat-1-1", close_time="11:00")],  # 3 slots
        precedence=[{
            "rule": "All Pool before Final",
            "event": "Basketball - Men Team",
            "earlier_stage": "Pool",
            "later_stage": "Final",
        }],
    )
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    slots = {a["game_id"]: a["slot"] for a in result["assignments"]}
    assert _slot_sort_key(slots["BBM-01"]) < _slot_sort_key(slots["BBM-Final"])


def test_solve_min_rest_between_games():
    """A team with two games must not play in adjacent slots."""
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
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    slots = {a["game_id"]: a["slot"] for a in result["assignments"]}
    key1 = _slot_sort_key(slots["G1"])
    key2 = _slot_sort_key(slots["G2"])
    # Slots must differ by at least 2 positions (min rest = no consecutive slots)
    assert abs(key1[1] - key2[1]) >= 120 or key1[0] != key2[0], (
        f"T1 played consecutive slots: {slots['G1']} and {slots['G2']}"
    )


def test_solve_empty_input():
    """An input with no games produces OPTIMAL with empty assignments."""
    pytest.importorskip("ortools")
    from scheduler import solve, STATUS_OPTIMAL
    si = _minimal_schedule_input(games=[], resources=[])
    result = solve(si, timeout_seconds=10.0)
    assert result["status"] == STATUS_OPTIMAL
    assert result["assignments"] == []
    assert result["unscheduled"] == []


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
    """run_solve_schedule returns exit code 2 when input file is missing."""
    pytest.importorskip("ortools")
    from scheduler import run_solve_schedule

    exit_code = run_solve_schedule(
        tmp_path / "nonexistent.json",
        tmp_path / "out.json",
    )
    assert exit_code == 2


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
        resources=[_gym_resource("GYM-Sat-1-1")],
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
