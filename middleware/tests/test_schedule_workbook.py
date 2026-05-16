import json

import pandas as pd
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


def test_read_roster_validation_rows_missing_path_degrades():
    """A missing ALL workbook should yield empty lists, not raise."""
    roster_rows, validation_rows = ScheduleWorkbookBuilder.read_roster_validation_rows(None)
    assert roster_rows == []
    assert validation_rows == []


def test_read_roster_validation_rows_parses_tabs(tmp_path):
    """Roster and Validation-Issues tabs round-trip into builder-shaped dicts."""
    xlsx_path = tmp_path / "Church_Team_Status_ALL.xlsx"
    roster_df = pd.DataFrame(
        [
            {
                "Church Team": "RPC",
                "sport_type": SPORT_TYPE["BASKETBALL"],
                "sport_gender": "Men",
                "sport_format": "Team",
                "Participant ID (WP)": 1,
                "First Name": "An",
                "Last Name": "Nguyen",
                "partner_name": None,
            }
        ]
    )
    validation_df = pd.DataFrame(
        [
            {
                "Church Team": "RPC",
                "Severity": "ERROR",
                "Status": "open",
                "Participant ID (WP)": 1,
                "sport_type": SPORT_TYPE["BASKETBALL"],
            }
        ]
    )
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        roster_df.to_excel(writer, sheet_name="Roster", index=False)
        validation_df.to_excel(writer, sheet_name="Validation-Issues", index=False)

    roster_rows, validation_rows = ScheduleWorkbookBuilder.read_roster_validation_rows(
        xlsx_path
    )

    assert len(roster_rows) == 1
    assert roster_rows[0]["Church Team"] == "RPC"
    # NaN cells normalize to None so `str(v or "")` collapses blanks cleanly.
    assert roster_rows[0]["partner_name"] is None
    assert len(validation_rows) == 1
    assert validation_rows[0]["Severity"] == "ERROR"


def test_read_roster_validation_rows_missing_tab_degrades(tmp_path):
    """A workbook without the expected tabs degrades to empty lists."""
    xlsx_path = tmp_path / "no_tabs.xlsx"
    pd.DataFrame([{"x": 1}]).to_excel(xlsx_path, sheet_name="Summary", index=False)

    roster_rows, validation_rows = ScheduleWorkbookBuilder.read_roster_validation_rows(
        xlsx_path
    )
    assert roster_rows == []
    assert validation_rows == []


def test_load_available_slots_from_schedule_input_counts_slots():
    schedule_input = {
        "resources": [
            {
                "resource_id": "PCK-1",
                "resource_type": "Pickleball Court",
                "label": "Court-1",
                "day": "Day-1",
                "open_time": "09:00",
                "close_time": "10:00",
                "slot_minutes": 30,
            },
            {
                "resource_id": "PCK-2",
                "resource_type": "Pickleball Court",
                "label": "Court-2",
                "day": "Day-1",
                "open_time": "09:00",
                "close_time": "09:30",
                "slot_minutes": 30,
            },
        ]
    }

    totals = ScheduleWorkbookBuilder._load_available_slots_from_schedule_input(
        schedule_input
    )

    assert totals["Pickleball Court"] == 3


def test_write_schedule_workbook_uses_schedule_input_resources_offline(tmp_path):
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {
            "Church Team": "RPC",
            "sport_type": SPORT_TYPE["PICKLEBALL"],
            "sport_gender": "Mixed",
            "sport_format": "Singles",
            "Participant ID (WP)": 1,
            "First Name": "Alex",
            "Last Name": "Tran",
        }
    ]
    schedule_input = {
        "generated_at": "2026-05-16T00:00:00",
        "gym_court_scenario": 4,
        "game_count": 0,
        "resource_count": 1,
        "games": [],
        "resources": [
            {
                "resource_id": "PCK-1",
                "resource_type": "Pickleball Court",
                "label": "Court-1",
                "day": "Day-1",
                "open_time": "09:00",
                "close_time": "10:00",
                "slot_minutes": 30,
                "exclusive_group": "",
            }
        ],
        "playoff_slots": [],
        "gym_modes": {},
    }
    workbook_path = tmp_path / "offline_schedule_workbook.xlsx"

    builder.write_schedule_workbook(
        workbook_path,
        roster_rows,
        [],
        schedule_input,
        venue_input_path=None,
    )

    wb = load_workbook(workbook_path)
    ws = wb["Pod-Resource-Estimate"]

    found_row = None
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == SPORT_TYPE["PICKLEBALL"]:
            found_row = row
            break

    assert found_row is not None
    assert ws.cell(row=found_row, column=5).value == 2
    all_values = [
        ws.cell(row=r, column=1).value
        for r in range(1, ws.max_row + 1)
        if ws.cell(row=r, column=1).value is not None
    ]
    assert any(
        "schedule_input.json resources" in str(value) for value in all_values
    )
