"""Tests for schedule_contracts.py (Issue #161)."""
import json

import pytest

from schedule_contracts import (
    ScheduleContractError,
    validate_output_against_input,
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
        "operator_notes": "hand-edited",
    }
    data["games"].append(_game("G2"))
    snapshot = json.loads(json.dumps(data))
    validate_schedule_input(data)
    assert data == snapshot


def test_empty_games_and_resources_pass():
    assert validate_schedule_input({"games": [], "resources": []}) == []


def test_annotation_namespace_fields_pass_silently():
    """x_* and operator_notes are the reserved annotation namespace."""
    data = {
        "games": [_game(x_custom_marker="operator-added", operator_notes="check")],
        "resources": [_resource(exclusive_group="Midsize Gym")],
        "gym_court_scenario": 4,
        "x_session_note": "dry run",
    }
    assert validate_schedule_input(data) == []


def test_unknown_field_warns_once_per_section_and_field():
    """Unknown fields are accepted but warned, deduplicated across items."""
    data = {
        "games": [_game("G1", colour="red"), _game("G2", colour="blue")],
        "resources": [_resource()],
    }
    warnings = validate_schedule_input(data)
    colour_warnings = [w for w in warnings if "'colour'" in w]
    assert len(colour_warnings) == 1
    assert "games" in colour_warnings[0]


def test_unknown_top_level_section_warns():
    data = {"games": [_game()], "resources": [_resource()], "mystery": {}}
    warnings = validate_schedule_input(data)
    assert any("'mystery'" in w for w in warnings)


def test_documented_schema_fields_do_not_warn():
    """Every field the exporters actually emit must be modeled (no noise)."""
    data = {
        "generated_at": "2026-06-12T08:00:00",
        "gym_court_scenario": 4,
        "game_count": 2,
        "resource_count": 1,
        "games": [
            _game("BBM-01", stage="Pool", pool_id="P1", round=1,
                  team_a_label="OCB", team_b_label="RPC", solver_pool="Gym Core"),
            _game("BAD-Men-Doubles-01", resource_type="Badminton Court",
                  division_id="BAD-Men-Doubles", division_entry_count=4,
                  team_a_id=None, team_b_id=None),
        ],
        "resources": [
            _resource(solver_pool="Gym Core", venue_name="EHS Main Gym"),
            _resource("GYM-Sun-2-5", venue_name="EHS Main Gym",
                      playoff_pinned=True),
        ],
        "playoff_slots": [
            {"game_id": "BBM-Final", "event": "Basketball - Men Team",
             "stage": "Final", "resource_id": "GYM-Sun-2-5",
             "slot": "Sat-1-10:00", "team_a_id": "BBM-P1-T1",
             "team_b_id": "BBM-P2-T1", "duration_minutes": 60,
             # Venue-centric placement intent kept on resolved rows (#127).
             "gym_name": "EHS Main Gym", "date": "2026-07-26",
             "start_time": "10:00"},
        ],
        "gym_modes": {"Midsize Gym": {"Basketball Court": 1}},
        "gym_allocation": {"source": "allocator"},
        "team_conflicts": [],
        "pod_unprotected_entries": [],
        "pod_validation_reconciliation": {},
        "precedence": [],
        "day_order": ["Sat-1", "Sun-1"],
    }
    warnings = validate_schedule_input(data)
    assert [w for w in warnings if "unknown" in w] == []


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


# ---------------------------------------------------------------------------
# Strict numerics (review follow-up)
# ---------------------------------------------------------------------------

def test_numeric_string_duration_is_rejected():
    data = {"games": [_game(duration_minutes="60")], "resources": [_resource()]}
    with pytest.raises(ScheduleContractError, match="duration_minutes"):
        validate_schedule_input(data)


def test_numeric_string_slot_minutes_is_rejected():
    data = {"games": [_game()], "resources": [_resource(slot_minutes="60")]}
    with pytest.raises(ScheduleContractError, match="slot_minutes"):
        validate_schedule_input(data)


def test_boolean_slot_minutes_is_rejected():
    data = {"games": [_game()], "resources": [_resource(slot_minutes=True)]}
    with pytest.raises(ScheduleContractError, match="slot_minutes"):
        validate_schedule_input(data)


def test_integer_duration_is_accepted_for_float_field():
    """Strict float fields still accept JSON integers (60, not just 60.0)."""
    data = {"games": [_game(duration_minutes=60)], "resources": [_resource()]}
    assert validate_schedule_input(data) == []


# ---------------------------------------------------------------------------
# Clock windows and min_gap_slots (review follow-up)
# ---------------------------------------------------------------------------

def test_close_time_not_after_open_time_is_an_error():
    data = {
        "games": [_game()],
        "resources": [_resource(open_time="11:00", close_time="11:00")],
    }
    with pytest.raises(ScheduleContractError, match="close_time"):
        validate_schedule_input(data)


def test_hour_out_of_clock_range_is_an_error():
    data = {
        "games": [_game()],
        "resources": [_resource(close_time="24:00")],
    }
    with pytest.raises(ScheduleContractError, match="hours"):
        validate_schedule_input(data)


def test_min_gap_slots_zero_is_an_error():
    """The solver silently converts 0 to 1, so a declared 0 is dishonest."""
    data = {
        "games": [_game("A"), _game("B")],
        "resources": [_resource()],
        "precedence": [
            {"before_game_id": "A", "after_game_id": "B", "min_gap_slots": 0},
        ],
    }
    with pytest.raises(ScheduleContractError, match="min_gap_slots"):
        validate_schedule_input(data)


# ---------------------------------------------------------------------------
# Reference checks (review follow-up)
# ---------------------------------------------------------------------------

def test_playoff_slot_unknown_resource_is_an_error():
    data = {
        "games": [_game()],
        "resources": [_resource("GYM-Sat-1-1")],
        "playoff_slots": [
            {"game_id": "BBM-Final", "resource_id": "GYM-Sun-2-1",
             "slot": "Sun-2-14:00"},
        ],
    }
    with pytest.raises(ScheduleContractError, match="GYM-Sun-2-1"):
        validate_schedule_input(data)


def test_cross_pool_precedence_is_an_error():
    """A rule spanning solver pools is silently dropped by the solver today;
    the contract must reject it instead (#161 review decision)."""
    data = {
        "games": [
            _game("BBM-01"),
            _game("BAD-01", resource_type="Badminton Court"),
        ],
        "resources": [
            _resource("GYM-1"),
            _resource("BAD-1", resource_type="Badminton Court"),
        ],
        "precedence": [
            {"before_game_id": "BBM-01", "after_game_id": "BAD-01"},
        ],
    }
    with pytest.raises(ScheduleContractError, match="spans solver pools"):
        validate_schedule_input(data)


def test_same_pool_precedence_via_solver_pool_passes():
    """Basketball and Volleyball share the 'Gym Core' pool, so precedence
    between them is enforceable and must pass."""
    data = {
        "games": [
            _game("BBM-01", solver_pool="Gym Core"),
            _game("VBM-01", event="Volleyball - Men Team",
                  resource_type="Volleyball Court", solver_pool="Gym Core"),
        ],
        "resources": [
            _resource("BB-1", solver_pool="Gym Core"),
            _resource("VB-1", resource_type="Volleyball Court",
                      solver_pool="Gym Core"),
        ],
        "precedence": [
            {"before_game_id": "BBM-01", "after_game_id": "VBM-01"},
        ],
    }
    assert validate_schedule_input(data) == []


def test_resource_fit_is_scoped_to_solver_pool():
    """A roomy resource of the right type in a DIFFERENT pool must not mask
    that the game cannot fit within its own pool (#161 review finding 1)."""
    data = {
        "games": [
            _game("BBM-01", duration_minutes=120, solver_pool="Gym Core"),
        ],
        "resources": [
            # Same resource_type, big window — but outside the game's pool.
            _resource("BB-OUTSIDE", open_time="08:00", close_time="16:00"),
            # Inside the pool, but only one 60-min slot: 120 min cannot fit.
            _resource("BB-CORE", solver_pool="Gym Core",
                      open_time="08:00", close_time="09:00"),
        ],
    }
    with pytest.raises(ScheduleContractError) as exc_info:
        validate_schedule_input(data)
    message = str(exc_info.value)
    assert "BBM-01" in message
    assert "Gym Core" in message
    assert "BB-OUTSIDE" not in message


def test_resource_type_outside_game_pool_is_a_warning():
    """resource_type exists, but not within the game's solver pool — the
    solver leaves the game unscheduled (exit 1), so the contract warns."""
    data = {
        "games": [_game("BBM-01", solver_pool="Gym Core")],
        "resources": [_resource("BB-OUTSIDE")],  # no solver_pool
    }
    warnings = validate_schedule_input(data)
    assert len(warnings) == 1
    assert "Gym Core" in warnings[0]
    assert "unscheduled" in warnings[0]


def test_gym_modes_bad_shape_is_an_error():
    data = {
        "games": [_game()],
        "resources": [_resource()],
        "gym_modes": {"Midsize Gym": {"Basketball Court": "one"}},
    }
    with pytest.raises(ScheduleContractError, match="gym_modes"):
        validate_schedule_input(data)


def test_top_level_must_be_an_object():
    with pytest.raises(ScheduleContractError, match="JSON object"):
        validate_schedule_input([_game()])


def test_missing_top_level_section_is_a_contract_error():
    with pytest.raises(ScheduleContractError, match="resources"):
        validate_schedule_input({"games": []})


# ---------------------------------------------------------------------------
# Output-to-input cross-file checks (review follow-up)
# ---------------------------------------------------------------------------

def test_output_assignment_unknown_game_is_an_error():
    si = {"games": [_game("G1")], "resources": [_resource()]}
    so = _output(assignments=[
        {"game_id": "GHOST", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
    ])
    with pytest.raises(ScheduleContractError, match="GHOST"):
        validate_output_against_input(so, si)


def test_output_assignment_unknown_resource_is_an_error():
    si = {"games": [_game("G1")], "resources": [_resource("GYM-Sat-1-1")]}
    so = _output(assignments=[
        {"game_id": "G1", "resource_id": "GHOST-COURT", "slot": "Sat-1-08:00"},
    ])
    with pytest.raises(ScheduleContractError, match="GHOST-COURT"):
        validate_output_against_input(so, si)


def test_output_assignment_may_reference_pinned_playoff_game():
    """Pinned playoff games exist only in playoff_slots, not games (#132)."""
    si = {
        "games": [_game("G1")],
        "resources": [_resource("GYM-Sat-1-1")],
        "playoff_slots": [
            {"game_id": "BBM-Final", "resource_id": "GYM-Sat-1-1",
             "slot": "Sat-1-10:00"},
        ],
    }
    so = _output(assignments=[
        {"game_id": "G1", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
        {"game_id": "BBM-Final", "resource_id": "GYM-Sat-1-1",
         "slot": "Sat-1-10:00"},
    ])
    assert validate_output_against_input(so, si) == []


def test_output_unknown_unscheduled_id_is_a_warning():
    si = {"games": [_game("G1")], "resources": [_resource()]}
    so = _output(
        assignments=[],
        unscheduled=["GHOST"],
        status="INFEASIBLE",
    )
    warnings = validate_output_against_input(so, si)
    assert any("GHOST" in w for w in warnings)


# ---------------------------------------------------------------------------
# Solver self-check and behavioral equivalence (review follow-up)
# ---------------------------------------------------------------------------

def test_run_solve_schedule_rejects_corrupt_solver_output(tmp_path, monkeypatch):
    """A solver bug producing a double-booked slot must exit 3, write nothing."""
    pytest.importorskip("ortools")
    import scheduler

    def corrupt_solve(schedule_input, timeout_seconds=None):
        return {
            "status": "OPTIMAL",
            "solver_wall_seconds": 0.0,
            "assignments": [
                {"game_id": "G1", "resource_id": "R1", "slot": "Sat-1-08:00"},
                {"game_id": "G2", "resource_id": "R1", "slot": "Sat-1-08:00"},
            ],
            "unscheduled": [],
            "pool_results": [],
        }

    monkeypatch.setattr(scheduler, "solve", corrupt_solve)
    si = {"games": [_game("G1"), _game("G2")], "resources": [_resource("R1")]}
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(si), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"

    exit_code = scheduler.run_solve_schedule(input_path, output_path)
    assert exit_code == 3
    assert not output_path.exists()


def test_validation_does_not_change_solver_behavior(tmp_path, monkeypatch):
    """Validation passes the same input to the solver and preserves its result."""
    import scheduler

    si = {
        "games": [
            _game("G1", team_a_id="T1", team_b_id="T2"),
            _game("G2", team_a_id="T1", team_b_id="T3"),
            _game("G3", team_a_id="T2", team_b_id="T3"),
        ],
        "resources": [
            _resource("GYM-Sat-1-1", close_time="16:00"),
            _resource("GYM-Sat-1-2", close_time="16:00"),
        ],
    }
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(si), encoding="utf-8")

    solver_inputs = []

    def deterministic_solve(schedule_input, timeout_seconds=None):
        solver_inputs.append(json.loads(json.dumps(schedule_input)))
        return {
            "status": "OPTIMAL",
            "solver_wall_seconds": 0.0,
            "assignments": [
                {
                    "game_id": "G1",
                    "resource_id": "GYM-Sat-1-1",
                    "slot": "Sat-1-08:00",
                },
                {
                    "game_id": "G2",
                    "resource_id": "GYM-Sat-1-1",
                    "slot": "Sat-1-10:00",
                },
                {
                    "game_id": "G3",
                    "resource_id": "GYM-Sat-1-1",
                    "slot": "Sat-1-12:00",
                },
            ],
            "unscheduled": [],
            "pool_results": [],
        }

    monkeypatch.setattr(scheduler, "solve", deterministic_solve)

    def solve_and_strip(out_name):
        output_path = tmp_path / out_name
        exit_code = scheduler.run_solve_schedule(input_path, output_path)
        assert exit_code == 0
        data = json.loads(output_path.read_text(encoding="utf-8"))
        data.pop("solved_at", None)
        data.pop("solver_wall_seconds", None)
        for pool in data.get("pool_results", []):
            pool.pop("solver_wall_seconds", None)
        return data

    validated = solve_and_strip("out_validated.json")

    monkeypatch.setattr(scheduler, "validate_schedule_input", lambda d: [])
    monkeypatch.setattr(scheduler, "validate_schedule_output", lambda d: [])
    unvalidated = solve_and_strip("out_unvalidated.json")

    assert solver_inputs == [si, si]
    assert validated["assignments"] == unvalidated["assignments"]
    assert validated["status"] == unvalidated["status"]
    assert validated["unscheduled"] == unvalidated["unscheduled"]
    assert validated == unvalidated
