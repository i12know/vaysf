"""Tests for schedule_contracts.py (Issue #161)."""
import json

import pytest

from schedule_contracts import (
    ScheduleContractError,
    validate_schedule_input,
    validate_schedule_output,
)


def _game(game_id="G1", **overrides):
    game = {
        "game_id": game_id, "event": "Basketball - Men Team",
        "stage": "Pool", "pool_id": "P1", "round": 1,
        "team_a_id": "T1", "team_b_id": "T2",
        "duration_minutes": 60, "resource_type": "Gym Court",
        "earliest_slot": None, "latest_slot": None,
    }
    game.update(overrides)
    return game


def _resource(resource_id="GYM-Sat-1-1", **overrides):
    resource = {
        "resource_id": resource_id, "resource_type": "Gym Court",
        "label": "Court-1", "day": "Sat-1",
        "open_time": "08:00", "close_time": "11:00", "slot_minutes": 60,
    }
    resource.update(overrides)
    return resource


# ---------------------------------------------------------------------------
# schedule_input — clean inputs
# ---------------------------------------------------------------------------

def test_clean_input_passes_with_no_warnings():
    data = {"games": [_game()], "resources": [_resource()]}
    assert validate_schedule_input(data) == []


def test_clean_input_is_not_mutated():
    data = {
        "games": [_game()],
        "resources": [_resource()],
        "precedence": [
            {"before_game_id": "G1", "after_game_id": "G2", "min_gap_slots": 1},
        ],
        "team_conflicts": [],
        "operator_note": "hand-edited",
    }
    data["games"].append(_game("G2"))
    snapshot = json.loads(json.dumps(data))
    validate_schedule_input(data)
    assert data == snapshot


def test_empty_games_and_resources_pass():
    assert validate_schedule_input({"games": [], "resources": []}) == []


def test_extra_fields_are_allowed():
    data = {
        "games": [_game(custom_marker="operator-added")],
        "resources": [_resource(exclusive_group="Midsize Gym")],
        "gym_court_scenario": 4,
    }
    assert validate_schedule_input(data) == []


# ---------------------------------------------------------------------------
# schedule_input — field-level errors
# ---------------------------------------------------------------------------

def test_missing_required_game_field_names_game():
    game = _game("BBM-04")
    del game["resource_type"]
    data = {"games": [game], "resources": [_resource()]}
    with pytest.raises(ScheduleContractError) as exc_info:
        validate_schedule_input(data)
    message = str(exc_info.value)
    assert "games[0]" in message
    assert "BBM-04" in message
    assert "resource_type" in message


def test_wrong_type_duration_is_an_error():
    data = {
        "games": [_game(duration_minutes="sixty")],
        "resources": [_resource()],
    }
    with pytest.raises(ScheduleContractError, match="duration_minutes"):
        validate_schedule_input(data)


def test_zero_slot_minutes_is_an_error():
    data = {
        "games": [_game()],
        "resources": [_resource(slot_minutes=0)],
    }
    with pytest.raises(ScheduleContractError, match="slot_minutes"):
        validate_schedule_input(data)


def test_bad_time_format_is_an_error():
    data = {
        "games": [_game()],
        "resources": [_resource(open_time="8am")],
    }
    with pytest.raises(ScheduleContractError, match="open_time"):
        validate_schedule_input(data)


def test_all_errors_reported_in_one_pass():
    bad_game = _game("BBM-04", duration_minutes=-5)
    bad_resource = _resource(slot_minutes=0)
    data = {"games": [bad_game], "resources": [bad_resource]}
    with pytest.raises(ScheduleContractError) as exc_info:
        validate_schedule_input(data)
    assert len(exc_info.value.errors) >= 2


def test_duplicate_game_id_is_an_error():
    data = {
        "games": [_game("G1"), _game("G1")],
        "resources": [_resource()],
    }
    with pytest.raises(ScheduleContractError, match="duplicate game_id"):
        validate_schedule_input(data)


def test_duplicate_resource_id_is_an_error():
    data = {
        "games": [_game()],
        "resources": [_resource("R1"), _resource("R1")],
    }
    with pytest.raises(ScheduleContractError, match="duplicate resource_id"):
        validate_schedule_input(data)


# ---------------------------------------------------------------------------
# schedule_input — resource fit
# ---------------------------------------------------------------------------

def test_game_that_fits_no_resource_of_its_type_is_an_error():
    """A 120-min game with only a 60-min window of its type can never run."""
    data = {
        "games": [_game("BAD-01", duration_minutes=120,
                        resource_type="Badminton Court")],
        "resources": [
            _resource("BAD-1", resource_type="Badminton Court",
                      open_time="09:00", close_time="10:00", slot_minutes=30),
        ],
    }
    with pytest.raises(ScheduleContractError) as exc_info:
        validate_schedule_input(data)
    message = str(exc_info.value)
    assert "BAD-01" in message
    assert "cannot fit" in message


def test_capacity_shortage_is_not_a_contract_error():
    """Two games competing for one slot is solver INFEASIBLE, not bad input.

    Mirrors test_run_solve_schedule_infeasible_writes_diagnostics: each game
    individually fits, so the contract must stay quiet and let the solver
    report the shortage with diagnostics (exit 1).
    """
    data = {
        "games": [
            _game("BAD-01", duration_minutes=30, resource_type="Badminton Court"),
            _game("BAD-02", duration_minutes=30, resource_type="Badminton Court"),
        ],
        "resources": [
            _resource("BAD-1", resource_type="Badminton Court",
                      open_time="09:00", close_time="09:30", slot_minutes=30),
        ],
    }
    assert validate_schedule_input(data) == []


def test_unroutable_resource_type_is_a_warning_not_error():
    """A resource_type with zero resources keeps the solver's exit-1 path."""
    data = {
        "games": [_game("BAD-01", resource_type="Badminton Court")],
        "resources": [_resource()],  # Gym Court only
    }
    warnings = validate_schedule_input(data)
    assert len(warnings) == 1
    assert "Badminton Court" in warnings[0]
    assert "unscheduled" in warnings[0]


def test_multi_slot_game_fits_via_consecutive_slots():
    """A 60-min game on 30-min slots needs two consecutive slots (C7)."""
    data = {
        "games": [_game("TT-01", duration_minutes=60,
                        resource_type="Table Tennis Table")],
        "resources": [
            _resource("TT-1", resource_type="Table Tennis Table",
                      open_time="09:00", close_time="10:00", slot_minutes=30),
        ],
    }
    assert validate_schedule_input(data) == []


# ---------------------------------------------------------------------------
# schedule_input — precedence
# ---------------------------------------------------------------------------

def test_precedence_cycle_is_reported_with_members():
    data = {
        "games": [_game("A"), _game("B"), _game("C")],
        "resources": [_resource()],
        "precedence": [
            {"before_game_id": "A", "after_game_id": "B"},
            {"before_game_id": "B", "after_game_id": "C"},
            {"before_game_id": "C", "after_game_id": "A"},
        ],
    }
    with pytest.raises(ScheduleContractError) as exc_info:
        validate_schedule_input(data)
    message = str(exc_info.value)
    assert "cycle" in message
    for game_id in ("A", "B", "C"):
        assert game_id in message


def test_acyclic_precedence_passes():
    data = {
        "games": [_game("A"), _game("B"), _game("C")],
        "resources": [_resource()],
        "precedence": [
            {"before_game_id": "A", "after_game_id": "B"},
            {"before_game_id": "B", "after_game_id": "C"},
            {"before_game_id": "A", "after_game_id": "C"},
        ],
    }
    assert validate_schedule_input(data) == []


def test_dangling_precedence_reference_is_a_warning():
    data = {
        "games": [_game("A")],
        "resources": [_resource()],
        "precedence": [
            {"before_game_id": "A", "after_game_id": "GHOST"},
        ],
    }
    warnings = validate_schedule_input(data)
    assert any("GHOST" in w and "ignored" in w for w in warnings)


def test_precedence_may_reference_pinned_playoff_games():
    """Playoff-Slots game_ids are valid precedence targets even when the
    pinned game has no game object (see #132)."""
    data = {
        "games": [_game("BBM-01")],
        "resources": [_resource()],
        "playoff_slots": [
            {"game_id": "BBM-Final", "resource_id": "GYM-Sat-1-1",
             "slot": "Sat-1-10:00"},
        ],
        "precedence": [
            {"before_game_id": "BBM-01", "after_game_id": "BBM-Final"},
        ],
    }
    assert validate_schedule_input(data) == []


# ---------------------------------------------------------------------------
# schedule_input — team_conflicts
# ---------------------------------------------------------------------------

def test_conflict_edge_without_names_is_a_warning():
    data = {
        "games": [_game()],
        "resources": [_resource()],
        "team_conflicts": [{
            "team_a_id": "BBM::RPC", "team_b_id": "VBM::RPC",
            "event_a": "Basketball - Men Team",
            "event_b": "Volleyball - Men Team",
            "shared_count": 2, "primary_overlap_count": 2,
            "secondary_only_count": 0,
            "shared_participant_names": [],
        }],
    }
    warnings = validate_schedule_input(data)
    assert any("shared_participant_names" in w for w in warnings)


def test_hand_edited_conflict_edge_without_counts_passes():
    """Hand-edited inputs may omit derived count fields (see scheduler
    _normalize_conflict_edge_counts)."""
    data = {
        "games": [_game()],
        "resources": [_resource()],
        "team_conflicts": [{
            "team_a_id": "BBM::RPC", "team_b_id": "VBM::RPC",
            "shared_count": 2, "primary_overlap_count": 2,
        }],
    }
    assert validate_schedule_input(data) == []


# ---------------------------------------------------------------------------
# schedule_output
# ---------------------------------------------------------------------------

def _output(**overrides):
    data = {
        "solved_at": "2026-06-12T14:30:00+00:00",
        "status": "OPTIMAL",
        "assignments": [
            {"game_id": "G1", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
        ],
        "unscheduled": [],
        "pool_results": [
            {"resource_type": "Gym Court", "status": "OPTIMAL",
             "solver_wall_seconds": 0.1, "assignments": [], "unscheduled": []},
        ],
    }
    data.update(overrides)
    return data


def test_clean_output_passes():
    assert validate_schedule_output(_output()) == []


def test_output_missing_status_is_an_error():
    data = _output()
    del data["status"]
    with pytest.raises(ScheduleContractError, match="status"):
        validate_schedule_output(data)


def test_output_unknown_status_is_an_error():
    with pytest.raises(ScheduleContractError, match="status"):
        validate_schedule_output(_output(status="SOLVED"))


def test_output_missing_assignments_is_an_error():
    data = _output()
    del data["assignments"]
    with pytest.raises(ScheduleContractError, match="assignments"):
        validate_schedule_output(data)


def test_output_duplicate_game_assignment_is_an_error():
    data = _output(assignments=[
        {"game_id": "G1", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
        {"game_id": "G1", "resource_id": "GYM-Sat-1-2", "slot": "Sat-1-09:00"},
    ])
    with pytest.raises(ScheduleContractError, match="assigned more than once"):
        validate_schedule_output(data)


def test_output_double_booked_slot_is_an_error():
    data = _output(assignments=[
        {"game_id": "G1", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
        {"game_id": "G2", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
    ])
    with pytest.raises(ScheduleContractError, match="double-booked"):
        validate_schedule_output(data)


# ---------------------------------------------------------------------------
# Integration — solve-schedule load path
# ---------------------------------------------------------------------------

def test_run_solve_schedule_contract_violation_exits_3(tmp_path):
    pytest.importorskip("ortools")
    from scheduler import run_solve_schedule

    bad_game = _game("BBM-04")
    del bad_game["resource_type"]
    si = {"games": [bad_game], "resources": [_resource()]}
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(si), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"

    exit_code = run_solve_schedule(input_path, output_path)
    assert exit_code == 3
    assert not output_path.exists()


def test_load_schedule_input_raises_contract_error(tmp_path):
    from scheduler import load_schedule_input

    si = {"games": [_game(duration_minutes=0)], "resources": [_resource()]}
    path = tmp_path / "si.json"
    path.write_text(json.dumps(si), encoding="utf-8")
    with pytest.raises(ScheduleContractError, match="duration_minutes"):
        load_schedule_input(path)
