import json

from openpyxl import load_workbook

from church_teams_export import ChurchTeamsExporter
from config import SPORT_TYPE
from schedule_workbook import ScheduleWorkbookBuilder


def _make_gym_roster(n_churches: int = 8) -> list[dict]:
    """Return minimal Basketball-Men roster rows for n_churches churches."""
    codes = ["RPC", "ANH", "FVC", "GAC", "NSD", "TLC", "GLA", "ORN"][:n_churches]
    rows = []
    for code in codes:
        for _ in range(5):  # 5 members per church -> meets min team size
            rows.append(
                {
                    "Church Team": code,
                    "sport_type": SPORT_TYPE["BASKETBALL"],
                    "sport_gender": "Men",
                    "sport_format": "Team",
                    "Participant ID (WP)": 1,
                }
            )
    return rows


def _make_schedule_pair() -> tuple[dict, dict]:
    schedule_input = {
        "games": [
            {
                "game_id": "BBM-01",
                "event": "Basketball - Men Team",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BBM-P1-T1",
                "team_b_id": "BBM-P1-T2",
                "duration_minutes": 60,
                "resource_type": "Gym Court",
                "earliest_slot": None,
                "latest_slot": None,
            }
        ],
        "resources": [
            {
                "resource_id": "GYM-Sat-1-1",
                "resource_type": "Gym Court",
                "label": "Court-1",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "09:00",
                "slot_minutes": 60,
                "exclusive_group": "",
            }
        ],
        "playoff_slots": [],
    }
    schedule_output = {
        "solved_at": "2026-05-01T10:00:00",
        "status": "OPTIMAL",
        "solver_wall_seconds": 0.1,
        "assignments": [
            {"game_id": "BBM-01", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"}
        ],
        "unscheduled": [],
    }
    return schedule_output, schedule_input


def test_church_teams_exporter_schedule_methods_delegate_to_builder():
    """ChurchTeamsExporter should reuse the extracted scheduling implementation."""
    method_names = (
        "_build_schedule_input",
        "_write_schedule_input_tab",
        "_build_schedule_output_flat_rows",
        "_write_schedule_output_report",
        "write_schedule_input_json",
        "write_schedule_workbook",
        "write_schedule_output_workbook",
    )
    for method_name in method_names:
        assert ChurchTeamsExporter.__dict__[method_name] is ScheduleWorkbookBuilder.__dict__[method_name]


def test_write_schedule_input_json_writes_file(tmp_path):
    """The extracted builder should own the schedule_input.json write path."""
    builder = ScheduleWorkbookBuilder()
    json_path = tmp_path / "schedule_input.json"

    schedule_input = builder.write_schedule_input_json(
        _make_gym_roster(),
        [],
        tmp_path / "missing.xlsx",
        json_path,
    )

    assert json_path.exists()
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["game_count"] == schedule_input["game_count"]
    assert written["resource_count"] == schedule_input["resource_count"]
    assert written["games"]
    assert written["resources"]


def test_write_schedule_workbook_creates_planning_tabs(tmp_path):
    """The planning workbook entry point should always create the six schedule tabs."""
    builder = ScheduleWorkbookBuilder()
    roster_rows = _make_gym_roster()
    schedule_input = builder.write_schedule_input_json(
        roster_rows,
        [],
        tmp_path / "missing.xlsx",
        tmp_path / "schedule_input.json",
    )
    workbook_path = tmp_path / "schedule_workbook.xlsx"

    builder.write_schedule_workbook(
        workbook_path,
        roster_rows,
        [],
        schedule_input,
        tmp_path / "missing.xlsx",
    )

    wb = load_workbook(workbook_path)
    assert wb.sheetnames == [
        "Venue-Estimator",
        "Pod-Divisions",
        "Pod-Entries-Review",
        "Court-Schedule-Sketch",
        "Pod-Resource-Estimate",
        "Schedule-Input",
    ]


def test_write_schedule_output_workbook_creates_schedule_tabs(tmp_path):
    """The output-workbook entry point should produce the two renderer tabs."""
    schedule_output, schedule_input = _make_schedule_pair()
    workbook_path = tmp_path / "schedule_output.xlsx"

    ScheduleWorkbookBuilder.write_schedule_output_workbook(
        workbook_path,
        schedule_output,
        schedule_input,
    )

    wb = load_workbook(workbook_path)
    assert wb.sheetnames == ["Schedule-by-Time", "Schedule-by-Sport"]
