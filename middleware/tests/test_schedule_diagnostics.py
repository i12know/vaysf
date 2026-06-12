import json

from schedule_diagnostics import (
    build_schedule_diagnostics,
    format_schedule_diagnostics,
    run_diagnose_schedule,
)


def _diagnostic_schedule_input() -> dict:
    return {
        "generated_at": "2026-05-15T00:00:00",
        "games": [
            {
                "game_id": "BAD-01",
                "event": "Badminton - Men Doubles",
                "stage": "Pool",
                "team_a_id": "BAD-T1",
                "team_b_id": "BAD-T2",
                "duration_minutes": 30,
                "resource_type": "Badminton Court",
                "earliest_slot": None,
                "latest_slot": None,
            },
            {
                "game_id": "BAD-02",
                "event": "Badminton - Women Doubles",
                "stage": "Pool",
                "team_a_id": "BAD-T3",
                "team_b_id": "BAD-T4",
                "duration_minutes": 30,
                "resource_type": "Badminton Court",
                "earliest_slot": None,
                "latest_slot": None,
            },
            {
                "game_id": "BAD-03",
                "event": "Badminton - Mixed Doubles",
                "stage": "Pool",
                "team_a_id": "BAD-T5",
                "team_b_id": "BAD-T6",
                "duration_minutes": 30,
                "resource_type": "Badminton Court",
                "earliest_slot": None,
                "latest_slot": None,
            },
        ],
        "resources": [
            {
                "resource_id": "BAD-Sat-1",
                "resource_type": "Badminton Court",
                "label": "Court-1",
                "day": "Sat-2",
                "open_time": "08:00",
                "close_time": "09:00",
                "slot_minutes": 30,
            }
        ],
        "playoff_slots": [
            {
                "game_id": "BAD-QF-1",
                "event": "Badminton - Men Doubles",
                "stage": "QF",
                "resource_type": "Badminton Court",
                "resource_id": "BAD-Sat-1",
                "slot": "Sat-2-08:00",
            }
        ],
        "precedence": [{"before": "BAD-01", "after": "BAD-QF-1", "min_gap_slots": 1}],
        "team_conflicts": [{"team_a_id": "BAD-T1", "team_b_id": "BAD-T3", "primary_overlap_count": 1}],
        "gym_modes": {},
        "gym_allocation": {"source": "allocator", "mode_shortfall": {"Badminton Court": 2}},
    }


def test_build_schedule_diagnostics_groups_vectors_and_suggests_next_actions():
    schedule_input = _diagnostic_schedule_input()
    schedule_output = {
        "status": "PARTIAL",
        "assignments": [{"game_id": "BAD-01", "resource_id": "BAD-Sat-1", "slot": "Sat-2-08:00"}],
        "unscheduled": ["BAD-02", "BAD-03"],
        "pool_results": [{"resource_type": "Badminton Court", "status": "INFEASIBLE"}],
        "conflict_audit_summary": {"overlapping_edges": 1},
    }

    diagnostics = build_schedule_diagnostics(schedule_input, schedule_output)

    assert diagnostics["summary"]["game_count"] == 3
    assert diagnostics["demand"]["by_resource_type"][0]["resource_type"] == "Badminton Court"
    assert diagnostics["demand"]["by_resource_type"][0]["required_slots_lower_bound"] == 3
    assert diagnostics["supply"]["by_resource_type"][0]["available_slots"] == 2
    assert diagnostics["control"]["playoff_slots_count"] == 1
    assert diagnostics["audit"]["unscheduled_count"] == 2

    vectors = {action["vector"] for action in diagnostics["next_actions"]}
    assert "demand/supply" in vectors
    assert "gym modes" in vectors
    assert "fixed pins" in vectors
    assert "precedence" in vectors
    assert "conflict graph" in vectors


def test_build_schedule_diagnostics_reports_missing_resource_type():
    schedule_input = _diagnostic_schedule_input()
    schedule_input["resources"] = []

    diagnostics = build_schedule_diagnostics(schedule_input)

    assert diagnostics["supply"]["total_resources"] == 0
    assert diagnostics["capacity_pressure"][0]["missing_resource_events"]
    assert diagnostics["next_actions"][0]["vector"] == "supply"
    assert diagnostics["audit"]["available"] is False


def test_build_schedule_diagnostics_flags_exclusive_group_mode_overlap():
    schedule_input = _diagnostic_schedule_input()
    schedule_input["resources"] = [
        {
            "resource_id": "GYM-Sat-2-1",
            "resource_type": "Basketball Court",
            "label": "Court-1",
            "day": "Sat-2",
            "open_time": "08:00",
            "close_time": "17:00",
            "slot_minutes": 60,
            "exclusive_group": "EHS Main Gym",
        },
        {
            "resource_id": "GYM-Sat-2-6",
            "resource_type": "Badminton Court",
            "label": "Court-1",
            "day": "Sat-2",
            "open_time": "13:00",
            "close_time": "17:00",
            "slot_minutes": 60,
            "exclusive_group": "EHS Main Gym",
        },
    ]
    schedule_output = {
        "status": "OPTIMAL",
        "assignments": [],
        "unscheduled": [],
        "pool_results": [],
        "conflict_audit_summary": {},
    }

    diagnostics = build_schedule_diagnostics(schedule_input, schedule_output)

    overlaps = diagnostics["supply"]["exclusive_group_overlaps"]
    assert len(overlaps) == 1
    assert overlaps[0]["exclusive_group"] == "EHS Main Gym"
    assert overlaps[0]["first_resource_type"] == "Badminton Court"
    assert overlaps[0]["second_resource_type"] == "Basketball Court"
    assert overlaps[0]["overlapping_resource_pairs"] == 1
    assert diagnostics["resource_contract"]["status"] == "error"
    assert diagnostics["resource_contract"]["issues"][0]["code"] == "physical_mode_overlap"
    assert any(
        action["severity"] == "high"
        and action["vector"] == "supply"
        and "EHS Main Gym on Sat-2" in action["message"]
        for action in diagnostics["next_actions"]
    )


def test_build_schedule_diagnostics_flags_direct_grouped_rows_without_gym_modes():
    schedule_input = _diagnostic_schedule_input()
    schedule_input["gym_modes"] = {}
    schedule_input["gym_allocation"] = {
        "source": "direct_venue_input",
        "reason": "grouped_rows_without_gym_modes",
    }
    schedule_input["resources"] = [
        {
            "resource_id": "BB-Sat-2-1",
            "resource_type": "Basketball Court",
            "label": "Court-1",
            "day": "Sat-2",
            "open_time": "08:00",
            "close_time": "12:00",
            "slot_minutes": 60,
            "exclusive_group": "EHS Main Gym",
        }
    ]

    diagnostics = build_schedule_diagnostics(schedule_input)

    contract = diagnostics["resource_contract"]
    assert contract["status"] == "warn"
    assert contract["allocation_source"] == "direct_venue_input"
    assert contract["issues"][0]["code"] == "direct_grouped_resources"
    assert any(
        action["vector"] == "resource contract"
        and "mutual exclusivity is not enforced" in action["message"]
        for action in diagnostics["next_actions"]
    )


def test_build_schedule_diagnostics_flags_allocator_contract_gaps():
    schedule_input = _diagnostic_schedule_input()
    schedule_input["gym_modes"] = {"EHS Main Gym": {"Basketball Court": 2}}
    schedule_input["gym_allocation"] = {"source": "allocator", "mode_shortfall": {}}
    schedule_input["resources"] = [
        {
            "resource_id": "GYM-Sat-2-1",
            "resource_type": "Basketball Court",
            "label": "Court-1",
            "day": "Sat-2",
            "open_time": "08:00",
            "close_time": "12:00",
            "slot_minutes": 60,
            "exclusive_group": "EHS Main Gym",
        },
        {
            "resource_id": "BB-Sat-2-direct",
            "resource_type": "Basketball Court",
            "label": "Court-2",
            "day": "Sat-2",
            "open_time": "08:00",
            "close_time": "12:00",
            "slot_minutes": 60,
            "exclusive_group": "EHS Main Gym",
        },
        {
            "resource_id": "BAD-Sat-2-uncovered",
            "resource_type": "Badminton Court",
            "label": "Court-1",
            "day": "Sat-2",
            "open_time": "13:00",
            "close_time": "17:00",
            "slot_minutes": 60,
            "exclusive_group": "Uncovered Gym",
        },
    ]

    diagnostics = build_schedule_diagnostics(schedule_input)

    contract = diagnostics["resource_contract"]
    assert contract["status"] == "error"
    codes = {issue["code"] for issue in contract["issues"]}
    assert "exclusive_group_without_gym_modes" in codes
    assert "direct_resource_in_allocator_group" in codes
    assert any(
        action["vector"] == "resource contract"
        and "Allocator-covered gym group contains direct non-GYM resources" in action["message"]
        for action in diagnostics["next_actions"]
    )


def test_build_schedule_diagnostics_downgrades_shortfall_when_solution_is_healthy():
    schedule_input = _diagnostic_schedule_input()
    schedule_input["resources"] = [
        {
            "resource_id": "BAD-Sat-1-A",
            "resource_type": "Badminton Court",
            "label": "Court-1",
            "day": "Sat-2",
            "open_time": "08:00",
            "close_time": "11:00",
            "slot_minutes": 30,
            "exclusive_group": "EHS Main Gym",
        }
    ]
    schedule_output = {
        "status": "FEASIBLE",
        "assignments": [
            {"game_id": "BAD-01", "resource_id": "BAD-Sat-1-A", "slot": "Sat-2-08:00"},
            {"game_id": "BAD-02", "resource_id": "BAD-Sat-1-A", "slot": "Sat-2-08:30"},
            {"game_id": "BAD-03", "resource_id": "BAD-Sat-1-A", "slot": "Sat-2-09:00"},
        ],
        "unscheduled": [],
        "pool_results": [{"resource_type": "Badminton Court", "status": "FEASIBLE"}],
        "conflict_audit_summary": {},
    }

    diagnostics = build_schedule_diagnostics(schedule_input, schedule_output)

    assert any(
        action["severity"] == "info"
        and action["vector"] == "capacity note"
        and "but all games were scheduled" in action["message"]
        for action in diagnostics["next_actions"]
    )
    assert not any(
        action["vector"] == "gym modes" and action["severity"] == "medium"
        for action in diagnostics["next_actions"]
    )


def test_format_schedule_diagnostics_includes_compact_next_action_lines():
    diagnostics = build_schedule_diagnostics(_diagnostic_schedule_input())

    lines = format_schedule_diagnostics(diagnostics)

    assert lines[0].startswith("Schedule diagnostics:")
    assert any(line.startswith("Resource contract:") for line in lines)
    assert any("Next action" in line for line in lines)


def test_run_diagnose_schedule_writes_json_report(tmp_path):
    input_path = tmp_path / "schedule_input.json"
    output_path = tmp_path / "schedule_diagnostics.json"
    input_path.write_text(json.dumps(_diagnostic_schedule_input()), encoding="utf-8")

    exit_code = run_diagnose_schedule(input_path, output_path=output_path)

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["summary"]["game_count"] == 3
    assert report["next_actions"]


# ---------------------------------------------------------------------------
# Quality warnings — #153
# ---------------------------------------------------------------------------

def _quality_schedule_input() -> dict:
    return {
        "games": [
            {
                "game_id": "BBM-Semi-1",
                "event": "Basketball - Men Team",
                "stage": "Semi",
                "pool_id": "",
                "duration_minutes": 60,
                "resource_type": "Gym Court",
                "team_a_id": None,
                "team_b_id": None,
                "earliest_slot": None,
                "latest_slot": None,
            },
            {
                "game_id": "BBM-Final",
                "event": "Basketball - Men Team",
                "stage": "Final",
                "pool_id": "",
                "duration_minutes": 60,
                "resource_type": "Gym Court",
                "team_a_id": None,
                "team_b_id": None,
                "earliest_slot": None,
                "latest_slot": None,
            },
            {
                "game_id": "VBM-01",
                "event": "Volleyball - Men Team",
                "stage": "Pool",
                "pool_id": "P1",
                "duration_minutes": 60,
                "resource_type": "Volleyball Court",
                "team_a_id": None,
                "team_b_id": None,
                "earliest_slot": None,
                "latest_slot": None,
            },
        ],
        "resources": [
            {
                "resource_id": "GYM-1",
                "resource_type": "Gym Court",
                "label": "Court-1",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "22:00",
                "slot_minutes": 60,
            },
            {
                "resource_id": "VB-1",
                "resource_type": "Volleyball Court",
                "label": "VB-Court-1",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "22:00",
                "slot_minutes": 60,
            },
        ],
        "precedence": [
            {
                "before_game_id": "BBM-Semi-1",
                "after_game_id": "BBM-Final",
                "min_gap_slots": 1,
            }
        ],
        "playoff_slots": [],
    }


def _quality_schedule_output(
    semi_slot: str = "Sat-1-19:00",
    final_slot: str = "Sat-1-20:30",
    vb_slot: str = "Sat-1-19:00",
    vb_switches: int = 0,
) -> dict:
    pool_result: dict = {
        "resource_type": "Volleyball Court",
        "status": "OPTIMAL",
    }
    if vb_switches:
        pool_result["volleyball_adjacent_switches"] = vb_switches
    return {
        "status": "OPTIMAL",
        "solver_wall_seconds": 0.1,
        "assignments": [
            {"game_id": "BBM-Semi-1", "resource_id": "GYM-1", "slot": semi_slot},
            {"game_id": "BBM-Final",  "resource_id": "GYM-1", "slot": final_slot},
            {"game_id": "VBM-01",     "resource_id": "VB-1",  "slot": vb_slot},
        ],
        "unscheduled": [],
        "pool_results": [pool_result],
        "conflict_audit_summary": {},
        "conflict_audit": [],
    }


def test_quality_warnings_absent_for_clean_schedule():
    """A schedule finishing before 20:00 with adequate gaps emits no quality warnings."""
    si = _quality_schedule_input()
    # Semi at 14:00, Final at 16:00 → finishes 17:00; gap = 60 min ≥ 30
    so = _quality_schedule_output(semi_slot="Sat-1-14:00", final_slot="Sat-1-16:00")
    diagnostics = build_schedule_diagnostics(si, so)
    assert diagnostics["quality_warnings"] == []


def test_quality_warnings_late_finish_flagged():
    """An event finishing after 20:00 emits a late_finish warning."""
    si = _quality_schedule_input()
    # BBM-Final at 20:30 → finishes 21:30
    so = _quality_schedule_output(semi_slot="Sat-1-18:00", final_slot="Sat-1-20:30")
    diagnostics = build_schedule_diagnostics(si, so)
    late = [w for w in diagnostics["quality_warnings"] if w["check"] == "late_finish"]
    assert len(late) == 1
    assert late[0]["event"] == "Basketball - Men Team"
    assert late[0]["latest_finish"] == "21:30"
    assert late[0]["severity"] == "medium"
    assert late[0]["game_id"] == "BBM-Final"


def test_quality_warnings_tight_turnaround_flagged():
    """Semi ending at 20:00 and Final starting at 20:15 (15 min gap) is flagged."""
    si = _quality_schedule_input()
    # Semi at 19:00 (60 min) ends at 20:00. Final at 20:15 → gap = 15 min < 30
    # But we need 15-min slots for this to work. Use 30-min slots instead.
    si["resources"][0]["slot_minutes"] = 30
    si["games"][0]["duration_minutes"] = 60  # Semi is 60 min (2 slots)
    si["games"][1]["duration_minutes"] = 60
    so = _quality_schedule_output(semi_slot="Sat-1-19:00", final_slot="Sat-1-20:15")
    # Semi ends at 20:00, Final at 20:15 → gap = 15 min
    so["assignments"][1]["slot"] = "Sat-1-20:15"
    diagnostics = build_schedule_diagnostics(si, so)
    tight = [w for w in diagnostics["quality_warnings"] if w["check"] == "tight_turnaround"]
    assert len(tight) == 1
    assert tight[0]["before_game_id"] == "BBM-Semi-1"
    assert tight[0]["after_game_id"] == "BBM-Final"
    assert tight[0]["gap_minutes"] == 15
    assert tight[0]["severity"] == "medium"


def test_quality_warnings_adequate_turnaround_not_flagged():
    """A 45-minute gap between Semi and Final is not flagged."""
    si = _quality_schedule_input()
    # Semi at 14:00 (60 min) ends at 15:00. Final at 15:45 → gap = 45 min
    so = _quality_schedule_output(semi_slot="Sat-1-14:00", final_slot="Sat-1-15:45")
    so["assignments"][1]["slot"] = "Sat-1-15:45"
    diagnostics = build_schedule_diagnostics(si, so)
    tight = [w for w in diagnostics["quality_warnings"] if w["check"] == "tight_turnaround"]
    assert tight == []


def test_quality_warnings_volleyball_switches_medium():
    """Volleyball switches above the threshold emit a medium warning."""
    si = _quality_schedule_input()
    so = _quality_schedule_output(vb_switches=6)
    diagnostics = build_schedule_diagnostics(si, so)
    sw = [w for w in diagnostics["quality_warnings"] if w["check"] == "volleyball_switches"]
    assert len(sw) == 1
    assert sw[0]["severity"] == "medium"
    assert sw[0]["switch_count"] == 6


def test_quality_warnings_volleyball_switches_info():
    """A small number of volleyball switches emits only an info-level warning."""
    si = _quality_schedule_input()
    so = _quality_schedule_output(vb_switches=2)
    diagnostics = build_schedule_diagnostics(si, so)
    sw = [w for w in diagnostics["quality_warnings"] if w["check"] == "volleyball_switches"]
    assert len(sw) == 1
    assert sw[0]["severity"] == "info"


def test_quality_warnings_no_output_returns_empty():
    """build_schedule_diagnostics without schedule_output has no quality_warnings."""
    diagnostics = build_schedule_diagnostics(_quality_schedule_input())
    assert diagnostics["quality_warnings"] == []


def test_quality_warnings_infeasible_output_returns_empty():
    """An INFEASIBLE schedule skips quality checks (nothing to assess)."""
    si = _quality_schedule_input()
    so = {
        "status": "INFEASIBLE",
        "assignments": [],
        "unscheduled": ["BBM-Semi-1", "BBM-Final"],
        "pool_results": [],
        "conflict_audit_summary": {},
        "conflict_audit": [],
    }
    diagnostics = build_schedule_diagnostics(si, so)
    assert diagnostics["quality_warnings"] == []


def test_quality_warnings_surface_in_next_actions():
    """Medium quality warnings propagate into next_actions as quality-vector suggestions."""
    si = _quality_schedule_input()
    # Final at 21:00 → finishes 22:00 (late finish)
    so = _quality_schedule_output(semi_slot="Sat-1-18:00", final_slot="Sat-1-21:00")
    diagnostics = build_schedule_diagnostics(si, so)
    quality_actions = [
        a for a in diagnostics["next_actions"] if a["vector"] == "quality" and a["severity"] == "medium"
    ]
    assert quality_actions, "Expected medium quality actions from late finish"


def test_quality_warnings_appear_in_format_output():
    """format_schedule_diagnostics includes a Quality line for each warning."""
    si = _quality_schedule_input()
    so = _quality_schedule_output(semi_slot="Sat-1-18:00", final_slot="Sat-1-21:00")
    diagnostics = build_schedule_diagnostics(si, so)
    lines = format_schedule_diagnostics(diagnostics)
    quality_lines = [ln for ln in lines if ln.startswith("Quality [")]
    assert quality_lines, "Expected Quality lines in formatted output"
    assert any("late_finish" in ln for ln in quality_lines)
