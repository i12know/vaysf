import json

import pandas as pd
from openpyxl import load_workbook

from church_teams_export import ChurchTeamsExporter
from config import (
    POD_RESOURCE_TYPE_PICKLEBALL,
    COURT_ESTIMATE_POOL_GAMES_PER_TEAM,
    SPORT_TYPE,
    TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
    TEAM_RESOURCE_TYPE_SOCCER,
)
from schedule_workbook import ScheduleWorkbookBuilder


def _find_row_by_first_cell(ws, value: str) -> int:
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == value:
            return row
    raise AssertionError(f"Could not find row starting with {value!r}")


def _sheet_rows(ws) -> list[dict]:
    headers = [ws.cell(row=1, column=col).value for col in range(1, ws.max_column + 1)]
    rows = []
    for row_idx in range(2, ws.max_row + 1):
        row = {
            headers[col_idx - 1]: ws.cell(row=row_idx, column=col_idx).value
            for col_idx in range(1, ws.max_column + 1)
        }
        if any(value not in (None, "") for value in row.values()):
            rows.append(row)
    return rows


def _make_gym_roster(n_churches: int = 8) -> list[dict]:
    """Return minimal Basketball-Men roster rows for n_churches churches."""
    codes = ["RPC", "ANH", "FVC", "GAC", "NSD", "TLC", "GLA", "ORN"][:n_churches]
    return _make_gym_roster_from_codes(codes)


def _make_gym_roster_from_codes(codes: list[str]) -> list[dict]:
    """Return minimal Basketball-Men roster rows for explicit church codes."""
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
                "team_a_label": "OCB",
                "team_b_label": "RPC",
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
        "conflict_audit_summary": {
            "total_edges": 1,
            "separated_edges": 1,
            "overlapping_edges": 0,
            "incomplete_edges": 0,
            "remaining_primary_overlap_penalty": 0,
            "remaining_secondary_overlap_penalty": 0,
        },
        "conflict_audit": [
            {
                "team_a_label": "OCB",
                "event_a": "Basketball - Men Team",
                "team_b_label": "OCB",
                "event_b": "Volleyball - Men Team",
                "shared_count": 2,
                "primary_overlap_count": 2,
                "secondary_only_count": 0,
                "status": "SeparatedInSchedule",
                "overlap_count": 0,
                "scheduled_team_a_games": 1,
                "scheduled_team_b_games": 1,
                "shared_participant_names": "An, Binh",
                "overlap_game_pairs": "",
            }
        ],
    }
    return schedule_output, schedule_input


def test_church_teams_exporter_schedule_methods_delegate_to_builder():
    """ChurchTeamsExporter should reuse the extracted scheduling implementation."""
    method_names = (
        "_build_schedule_input",
        "_write_schedule_input_tab",
        "_build_schedule_output_flat_rows",
        "_write_schedule_output_report",
        "_build_gym_resources_from_allocator",
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
    """The planning workbook entry point should always create the operator + planning tabs."""
    builder = ScheduleWorkbookBuilder()
    roster_rows = _make_gym_roster()
    schedule_input = builder.write_schedule_input_json(
        roster_rows,
        [],
        tmp_path / "missing.xlsx",
        tmp_path / "schedule_input.json",
    )
    schedule_input["gym_modes"] = {
        "Main Gym": {
            "Basketball Court": 2,
            "Volleyball Court": 1,
        }
    }
    schedule_input["gym_allocation"] = {
        "source": "allocator",
        "switch_count": 1,
        "decisions": [
            {
                "gym_name": "Main Gym",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "12:00",
                "mode": "Basketball Court",
                "courts": 2,
                "slot_minutes": 60,
            }
        ],
        "mode_demand": {"Basketball Court": 4},
        "mode_supply": {"Basketball Court": 4},
        "mode_shortfall": {"Basketball Court": 0},
    }
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
        "Summary",
        "Venue-Estimator",
        "Pool-Assignment",
        "Pod-Divisions",
        "Pod-Entries-Review",
        "Court-Schedule-Sketch",
        "Pod-Resource-Estimate",
        "Schedule-Input",
        "Gym-Allocation",
    ]
    summary_ws = wb["Summary"]
    assert summary_ws["A1"].value == "VAY Sports Fest — Schedule Workbook Guide"
    assert "Layer 1 planning aid" in str(summary_ws["B4"].value)
    summary_text = "".join(
        str(summary_ws.cell(row=row, column=2).value or "")
        for row in range(1, summary_ws.max_row + 1)
    )
    assert "Church_Team_Status_ALL" in summary_text
    assert "run-schedule.bat" in summary_text
    assert "assign-pools" in summary_text
    assert "BB/VBM/VBW/BC/SOC" in summary_text
    venue_ws = wb["Venue-Estimator"]
    assert venue_ws["A1"].comment is not None
    assert "Canonical event name" in venue_ws["A1"].comment.text
    pool_ws = wb["Pool-Assignment"]
    assert pool_ws["A1"].comment is not None
    assert "Canonical team-sport event" in pool_ws["A1"].comment.text
    assert "SOC" in pool_ws["A1"].comment.text
    assert pool_ws["I1"].comment is not None
    assert "Leave blank or enter 0" in pool_ws["I1"].comment.text
    pod_ws = wb["Pod-Divisions"]
    assert pod_ws["A1"].comment is not None
    assert "Canonical division label" in pod_ws["A1"].comment.text
    assert pod_ws["K1"].comment is not None
    assert "Ready = clean to plan" in pod_ws["K1"].comment.text
    entry_ws = wb["Pod-Entries-Review"]
    assert entry_ws["A1"].comment is not None
    assert "Unique row ID" in entry_ws["A1"].comment.text
    sketch_ws = wb["Court-Schedule-Sketch"]
    assert sketch_ws["A4"].comment is not None
    assert "Start time for the slot" in sketch_ws["A4"].comment.text
    resource_ws = wb["Pod-Resource-Estimate"]
    assert resource_ws["A1"].comment is not None
    assert "Racquet event" in resource_ws["A1"].comment.text
    schedule_input_ws = wb["Schedule-Input"]
    games_header_row = _find_row_by_first_cell(schedule_input_ws, "GAMES") + 1
    resources_header_row = _find_row_by_first_cell(schedule_input_ws, "RESOURCES") + 1
    playoff_header_row = _find_row_by_first_cell(schedule_input_ws, "PLAYOFF-SLOTS") + 1
    assert schedule_input_ws.cell(row=games_header_row, column=1).comment is not None
    assert (
        "Unique placeholder game ID"
        in schedule_input_ws.cell(row=games_header_row, column=1).comment.text
    )
    assert schedule_input_ws.cell(row=resources_header_row, column=1).comment is not None
    assert (
        "Exact solver resource ID"
        in schedule_input_ws.cell(row=resources_header_row, column=1).comment.text
    )
    assert schedule_input_ws.cell(row=playoff_header_row, column=1).comment is not None
    assert (
        "Exact playoff game ID"
        in schedule_input_ws.cell(row=playoff_header_row, column=1).comment.text
    )
    gym_ws = wb["Gym-Allocation"]
    assert gym_ws["A4"].comment is not None
    assert "Exclusive Venue Group / gym block name" in gym_ws["A4"].comment.text
    assert gym_ws["A8"].comment is not None
    assert "Sport mode or resource mode" in gym_ws["A8"].comment.text


def test_write_schedule_workbook_loads_pool_assignment_sidecar(tmp_path):
    builder = ScheduleWorkbookBuilder()
    roster_rows = _make_gym_roster()
    schedule_input = builder.write_schedule_input_json(
        roster_rows,
        [],
        tmp_path / "missing.xlsx",
        tmp_path / "schedule_input.json",
    )
    sidecar_path = tmp_path / "pool_assignments.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "version": 1,
                "rows": [
                    {
                        "event": SPORT_TYPE["BASKETBALL"],
                        "team_id": "RPC",
                        "seed": 1,
                        "random_draw_order": 4,
                        "notes": "Returning champion",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    workbook_path = tmp_path / "schedule_workbook.xlsx"

    builder.write_schedule_workbook(
        workbook_path,
        roster_rows,
        [],
        schedule_input,
        tmp_path / "missing.xlsx",
        pool_assignment_path=sidecar_path,
    )

    ws = load_workbook(workbook_path)["Pool-Assignment"]
    rpc_row = next(
        row for row in _sheet_rows(ws)
        if row["Event"] == SPORT_TYPE["BASKETBALL"] and row["Team ID"] == "RPC"
    )
    assert rpc_row["Seed"] == 1
    assert rpc_row["Notes"] == "Returning champion"
    assert rpc_row["Pool ID"] is not None
    assert rpc_row["Pool Slot"] is not None


def test_refresh_pool_assignments_persists_seed_edits_and_recomputes_draw(tmp_path):
    builder = ScheduleWorkbookBuilder()
    roster_rows = _make_gym_roster(n_churches=4)
    schedule_input = builder.write_schedule_input_json(
        roster_rows,
        [],
        tmp_path / "missing.xlsx",
        tmp_path / "schedule_input.json",
    )
    workbook_path = tmp_path / "schedule_workbook.xlsx"
    sidecar_path = tmp_path / "pool_assignments.json"

    builder.write_schedule_workbook(
        workbook_path,
        roster_rows,
        [],
        schedule_input,
        tmp_path / "missing.xlsx",
        pool_assignment_path=sidecar_path,
    )

    wb = load_workbook(workbook_path)
    ws = wb["Pool-Assignment"]
    headers = [ws.cell(row=1, column=col).value for col in range(1, ws.max_column + 1)]
    seed_col = headers.index("Seed") + 1
    notes_col = headers.index("Notes") + 1
    team_id_col = headers.index("Team ID") + 1
    for row_idx in range(2, ws.max_row + 1):
        team_id = ws.cell(row=row_idx, column=team_id_col).value
        if team_id == "RPC":
            ws.cell(row=row_idx, column=seed_col, value=1)
            ws.cell(row=row_idx, column=notes_col, value="Top seed")
        elif team_id == "ANH":
            ws.cell(row=row_idx, column=seed_col, value=2)
    wb.save(workbook_path)

    builder.refresh_pool_assignments(
        workbook_path,
        sidecar_path=sidecar_path,
    )

    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    saved_rpc = next(
        row for row in payload["rows"]
        if row["event"] == SPORT_TYPE["BASKETBALL"] and row["team_id"] == "RPC"
    )
    assert saved_rpc["seed"] == 1
    assert saved_rpc["notes"] == "Top seed"

    refreshed_ws = load_workbook(workbook_path)["Pool-Assignment"]
    refreshed_rows = _sheet_rows(refreshed_ws)
    rpc_row = next(
        row for row in refreshed_rows
        if row["Event"] == SPORT_TYPE["BASKETBALL"] and row["Team ID"] == "RPC"
    )
    anh_row = next(
        row for row in refreshed_rows
        if row["Event"] == SPORT_TYPE["BASKETBALL"] and row["Team ID"] == "ANH"
    )
    assert rpc_row["Draw Position"] == 1
    assert anh_row["Draw Position"] == 2


def test_refresh_pool_assignments_flags_duplicate_seeds(tmp_path):
    builder = ScheduleWorkbookBuilder()
    roster_rows = _make_gym_roster(n_churches=4)
    schedule_input = builder.write_schedule_input_json(
        roster_rows,
        [],
        tmp_path / "missing.xlsx",
        tmp_path / "schedule_input.json",
    )
    workbook_path = tmp_path / "schedule_workbook.xlsx"
    sidecar_path = tmp_path / "pool_assignments.json"

    builder.write_schedule_workbook(
        workbook_path,
        roster_rows,
        [],
        schedule_input,
        tmp_path / "missing.xlsx",
        pool_assignment_path=sidecar_path,
    )

    wb = load_workbook(workbook_path)
    ws = wb["Pool-Assignment"]
    headers = [ws.cell(row=1, column=col).value for col in range(1, ws.max_column + 1)]
    seed_col = headers.index("Seed") + 1
    team_id_col = headers.index("Team ID") + 1
    for row_idx in range(2, ws.max_row + 1):
        team_id = ws.cell(row=row_idx, column=team_id_col).value
        if team_id in {"RPC", "ANH"}:
            ws.cell(row=row_idx, column=seed_col, value=1)
    wb.save(workbook_path)

    builder.refresh_pool_assignments(
        workbook_path,
        sidecar_path=sidecar_path,
    )

    refreshed_rows = _sheet_rows(load_workbook(workbook_path)["Pool-Assignment"])
    duplicate_rows = [
        row for row in refreshed_rows
        if row["Event"] == SPORT_TYPE["BASKETBALL"] and row["Team ID"] in {"RPC", "ANH"}
    ]
    assert len(duplicate_rows) == 2
    assert {row["Assignment Basis"] for row in duplicate_rows} == {"SeededDuplicate"}


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
    assert wb.sheetnames == ["Schedule-by-Time", "Schedule-by-Sport", "Conflict-Audit"]


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


# ===========================================================================
# Pure scheduling-method tests migrated from test_church_teams_export.py
# (Issue #98 Step 4 — ScheduleWorkbookBuilder extraction)
# ===========================================================================


def _write_venue_input(path, headers, data_rows, gym_modes_rows=None):
    """Write a venue_input.xlsx with a Venue-Input tab (and optional Gym-Modes)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    for r, data in enumerate(data_rows, start=2):
        for c, val in enumerate(data, start=1):
            ws.cell(row=r, column=c, value=val)
    if gym_modes_rows is not None:
        gm = wb.create_sheet("Gym-Modes")
        for r, data in enumerate(gym_modes_rows, start=1):
            for c, val in enumerate(data, start=1):
                gm.cell(row=r, column=c, value=val)
    wb.save(path)


def _make_render_schedule_pair():
    """Return (schedule_output, schedule_input) test fixtures."""
    schedule_input = {
        "games": [
            {
                "game_id": "BBM-01", "event": "Basketball - Men Team",
                "stage": "Pool", "pool_id": "P1", "round": 1,
                "team_a_id": "BBM-P1-T1", "team_b_id": "BBM-P1-T2",
                "duration_minutes": 60, "resource_type": "Gym Court",
                "earliest_slot": None, "latest_slot": None,
            },
            {
                "game_id": "BBM-Final", "event": "Basketball - Men Team",
                "stage": "Final", "pool_id": "", "round": 1,
                "team_a_id": "WIN-BBM-Semi-1", "team_b_id": "WIN-BBM-Semi-2",
                "duration_minutes": 60, "resource_type": "Gym Court",
                "earliest_slot": None, "latest_slot": None,
            },
        ],
        "resources": [
            {
                "resource_id": "GYM-Sat-1-1", "resource_type": "Gym Court",
                "label": "Court-1", "day": "Sat-1",
                "open_time": "08:00", "close_time": "12:00", "slot_minutes": 60,
            }
        ],
        "precedence": [],
    }
    schedule_output = {
        "solved_at": "2026-05-01T10:00:00",
        "status": "OPTIMAL",
        "solver_wall_seconds": 0.1,
        "assignments": [
            {"game_id": "BBM-01",    "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
            {"game_id": "BBM-Final", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-10:00"},
        ],
        "unscheduled": [],
    }
    return schedule_output, schedule_input


def test_venue_capacity_court_slot_math():
    """Pool/playoff/total slot math (Issue #83)."""
    builder = ScheduleWorkbookBuilder()

    # 0 teams -> all zeros
    s0 = builder._compute_court_slots(0)
    assert s0["pool_slots"] == 0
    assert s0["playoff_teams"] == 0
    assert s0["playoff_slots"] == 0
    assert s0["total_slots"] == 0
    assert s0["court_hours"] == 0.0

    # 6 teams, 2 pool games each -> ceil(6*2/2) = 6 pool, 4-team playoff = 3 playoff games
    s6 = builder._compute_court_slots(6)
    assert s6["pool_slots"] == 6
    assert s6["playoff_teams"] == 4
    assert s6["playoff_slots"] == 3
    assert s6["third_place_slots"] == 1
    assert s6["total_slots"] == 10
    assert s6["court_hours"] == 10.0  # 60 min/game

    # 8 teams -> ceil(8*2/2)=8 pool, 8-team playoff = 7 playoff games
    s8 = builder._compute_court_slots(8)
    assert s8["pool_slots"] == 8
    assert s8["playoff_teams"] == 8
    assert s8["playoff_slots"] == 7
    assert s8["third_place_slots"] == 1
    assert s8["total_slots"] == 16

    # 3 teams -> only pool play, no playoff
    s3 = builder._compute_court_slots(3)
    assert s3["pool_slots"] == 3
    assert s3["playoff_teams"] == 0
    assert s3["playoff_slots"] == 0
    assert s3["total_slots"] == 3


def test_count_estimating_teams_uses_min_team_size():
    """A church only counts when its roster meets the min team size (Issue #83)."""
    builder = ScheduleWorkbookBuilder()

    # RPC has 5 basketball players (meets min=5), TLC has 4 (potential only)
    roster_rows = [
        {"Church Team": "RPC", "sport_type": "Basketball", "sport_gender": "Men"} for _ in range(5)
    ] + [
        {"Church Team": "TLC", "sport_type": "Basketball", "sport_gender": "Men"} for _ in range(4)
    ]

    result = builder._count_estimating_teams(roster_rows, "Basketball - Men Team", min_team_size=5)
    assert result["n_estimating"] == 1       # only RPC qualifies
    assert result["n_potential"] == 2        # RPC (estimating) + TLC (partial) = all with >= 1
    assert result["team_codes"] == "RPC"     # sorted, comma-separated


def test_count_estimating_teams_separates_volleyball_men_and_women():
    """Volleyball Men and Women are distinct events; team_codes is sorted (Issue #83)."""
    builder = ScheduleWorkbookBuilder()

    roster_rows = (
        [{"Church Team": "RPC", "sport_type": "Volleyball", "sport_gender": "Men"} for _ in range(6)]
        + [{"Church Team": "RPC", "sport_type": "Volleyball", "sport_gender": "Women"} for _ in range(6)]
        + [{"Church Team": "TLC", "sport_type": "Volleyball", "sport_gender": "Women"} for _ in range(6)]
    )

    men = builder._count_estimating_teams(roster_rows, "Volleyball - Men Team", 6)
    assert men["n_estimating"] == 1
    assert men["team_codes"] == "RPC"

    women = builder._count_estimating_teams(roster_rows, "Volleyball - Women Team", 6)
    assert women["n_estimating"] == 2
    assert women["team_codes"] == "RPC, TLC"  # alphabetically sorted


def test_count_estimating_teams_soccer_full_label():
    """Soccer sport_type is stored as the full Other-Events label, not just 'Soccer'."""
    builder = ScheduleWorkbookBuilder()

    # Other-events registrations store the full SPORT_TYPE constant value verbatim
    roster_rows = [
        {"Church Team": "RPC", "sport_type": SPORT_TYPE["SOCCER"], "sport_gender": "Mixed"}
        for _ in range(5)
    ] + [
        {"Church Team": "TLC", "sport_type": SPORT_TYPE["SOCCER"], "sport_gender": "Mixed"}
        for _ in range(3)
    ]

    result = builder._count_estimating_teams(
        roster_rows, SPORT_TYPE["SOCCER"], min_team_size=4
    )
    assert result["n_estimating"] == 1      # only RPC has >= 4
    assert result["n_potential"] == 2       # RPC + TLC both have >= 1
    assert result["team_codes"] == "RPC"


def test_count_estimating_teams_respects_explicit_team_order():
    """Explicit A/B team splits should count as separate estimating teams."""
    builder = ScheduleWorkbookBuilder()

    roster_rows = (
        [
            {
                "Church Team": "RPC",
                "team_order": "A",
                "sport_type": "Basketball",
                "sport_gender": "Men",
            }
            for _ in range(5)
        ]
        + [
            {
                "Church Team": "RPC",
                "team_order": "B",
                "sport_type": "Basketball",
                "sport_gender": "Men",
            }
            for _ in range(5)
        ]
        + [
            {
                "Church Team": "OCB",
                "team_order": "A",
                "sport_type": "Basketball",
                "sport_gender": "Men",
            }
            for _ in range(5)
        ]
    )

    result = builder._count_estimating_teams(
        roster_rows, "Basketball - Men Team", min_team_size=5
    )

    assert result["n_estimating"] == 3
    assert result["n_potential"] == 3
    assert result["team_codes"] == "OCB-A, RPC-A, RPC-B"


def test_count_racquet_entries():
    """Racquet entries: complete pairs counted as 1, singles as 1; potential = all regs."""
    builder = ScheduleWorkbookBuilder()

    roster_rows = [
        # 5 Badminton doubles registrations → 2 complete pairs + 1 waiting
        {"sport_type": "Badminton", "sport_format": "Mixed Doubles"} for _ in range(5)
    ] + [
        # 2 Badminton singles
        {"sport_type": "Badminton", "sport_format": "Men Singles"},
        {"sport_type": "Badminton", "sport_format": "Women Singles"},
    ] + [
        # Pickleball should not bleed into Badminton count
        {"sport_type": "Pickleball", "sport_format": "Mixed Doubles"},
    ]

    result = builder._count_racquet_entries(roster_rows, "Badminton")
    assert result["n_estimating"] == 2 + 2   # floor(5/2)=2 pairs + 2 singles
    assert result["n_potential"] == 5 + 2    # 5 doubles + 2 singles = 7 registrations
    assert result["team_codes"] == ""


def test_pod_format_class():
    builder = ScheduleWorkbookBuilder()
    assert builder._pod_format_class("Men Single") == "singles"
    assert builder._pod_format_class("Singles") == "singles"
    assert builder._pod_format_class("Women Singles") == "singles"
    assert builder._pod_format_class("Men Double") == "doubles"
    assert builder._pod_format_class("Doubles") == "doubles"
    assert builder._pod_format_class("Mixed Double") == "doubles"
    assert builder._pod_format_class("Team") == "anomaly"
    assert builder._pod_format_class("") == "anomaly"
    assert builder._pod_format_class(None) == "anomaly"


def test_make_division_id():
    builder = ScheduleWorkbookBuilder()
    assert builder._make_division_id("Badminton", "Men", "singles") == "BAD-Men-Singles"
    assert builder._make_division_id("Table Tennis", "Women", "doubles") == "TT-Women-Doubles"
    assert builder._make_division_id("Pickleball 35+", "Mixed", "doubles") == "PCK35-Mixed-Doubles"
    assert builder._make_division_id("Tennis", "Men", "anomaly") == "TEN-Men-Anomaly"
    assert builder._make_division_id("Table Tennis 35+", "Men", "singles") == "TT35-Men-Singles"


def test_build_pod_error_lookup():
    builder = ScheduleWorkbookBuilder()
    validation_rows = [
        {
            "Participant ID (WP)": "42",
            "sport_type": "Badminton",
            "Severity": "ERROR",
            "Status": "open",
        },
        {
            "Participant ID (WP)": "42",
            "sport_type": "Pickleball",
            "Severity": "WARNING",  # warnings excluded
            "Status": "open",
        },
        {
            "Participant ID (WP)": "99",
            "sport_type": "Table Tennis",
            "Severity": "ERROR",
            "Status": "resolved",  # resolved excluded
        },
        {
            "Participant ID (WP)": "55",
            "sport_type": "Tennis",
            "Severity": "ERROR",
            "Status": "open",
        },
    ]
    lookup = builder._build_pod_error_lookup(validation_rows)
    assert lookup == {"42": {"Badminton"}, "55": {"Tennis"}}


def test_build_pod_divisions_rows_singles():
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Single",
         "Participant ID (WP)": "1", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Single",
         "Participant ID (WP)": "2", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Single",
         "Participant ID (WP)": "3", "Church Team": "TLC"},
    ]
    # Participant 2 has an error
    validation_rows = [
        {"Participant ID (WP)": "2", "sport_type": "Badminton", "Severity": "ERROR", "Status": "open"},
    ]
    rows = builder._build_pod_divisions_rows(roster_rows, validation_rows)

    assert len(rows) == 1
    div = rows[0]
    assert div["division_id"] == "BAD-Men-Singles"
    assert div["sport_type"] == "Badminton"
    assert div["resource_type"] == "Badminton Court"
    assert div["planning_entries"] == 3
    assert div["confirmed_entries"] == 2  # participant 2 has error
    assert div["provisional_entries"] == 1
    assert div["anomaly_count"] == 0
    assert div["division_status"] == "Partial"


def test_build_pod_divisions_rows_doubles():
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "10", "Church Team": "RPC"},
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "11", "Church Team": "RPC"},
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "12", "Church Team": "TLC"},
        {"sport_type": "Table Tennis", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "13", "Church Team": "TLC"},
    ]
    rows = builder._build_pod_divisions_rows(roster_rows, [])

    assert len(rows) == 1
    div = rows[0]
    assert div["division_id"] == "TT-Men-Doubles"
    assert div["resource_type"] == "Table Tennis Table"
    assert div["planning_entries"] == 2   # floor(4/2)
    assert div["confirmed_entries"] == 2  # no errors
    assert div["provisional_entries"] == 0
    assert div["division_status"] == "Ready"


def test_build_pod_divisions_rows_anomaly():
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {"sport_type": "Pickleball", "sport_gender": "Men", "sport_format": "Team",
         "Participant ID (WP)": "20", "Church Team": "RPC"},
    ]
    rows = builder._build_pod_divisions_rows(roster_rows, [])

    assert len(rows) == 1
    div = rows[0]
    assert div["division_id"] == "PCK-Men-Anomaly"
    assert div["planning_entries"] == 0
    assert div["confirmed_entries"] == 0
    assert div["anomaly_count"] == 1
    assert div["division_status"] == "AnomalyOnly"


def test_build_pod_entries_review_singles():
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {"sport_type": "Tennis", "sport_gender": "Women", "sport_format": "Women Single",
         "Participant ID (WP)": "30", "First Name": "Lan", "Last Name": "Tran", "Church Team": "RPC"},
        {"sport_type": "Tennis", "sport_gender": "Women", "sport_format": "Women Single",
         "Participant ID (WP)": "31", "First Name": "Hoa", "Last Name": "Le", "Church Team": "RPC"},
    ]
    validation_rows = [
        {"Participant ID (WP)": "31", "sport_type": "Tennis", "Severity": "ERROR", "Status": "open"},
    ]
    rows = builder._build_pod_entries_review_rows(roster_rows, validation_rows)

    assert len(rows) == 2
    singles = [r for r in rows if r["entry_type"] == "Singles"]
    assert len(singles) == 2

    lan = next(r for r in singles if r["participant_1_name"] == "Lan Tran")
    assert lan["review_status"] == "OK"
    assert lan["partner_status"] == "N/A"
    assert lan["division_id"] == "TEN-Women-Singles"

    hoa = next(r for r in singles if r["participant_1_name"] == "Hoa Le")
    assert hoa["review_status"] == "NeedsReview"


def test_build_pod_entries_review_doubles_reciprocal():
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "40", "First Name": "Anh", "Last Name": "Nguyen",
         "partner_name": "Binh Tran", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Men", "sport_format": "Men Double",
         "Participant ID (WP)": "41", "First Name": "Binh", "Last Name": "Tran",
         "partner_name": "Anh Nguyen", "Church Team": "TLC"},
    ]
    rows = builder._build_pod_entries_review_rows(roster_rows, [])

    assert len(rows) == 1
    pair = rows[0]
    assert pair["entry_type"] == "DoublesPair"
    assert pair["partner_status"] == "Confirmed"
    assert pair["review_status"] == "OK"
    assert "Anh Nguyen" in pair["participant_1_name"] or "Binh Tran" in pair["participant_1_name"]
    assert "Anh Nguyen" in pair["participant_2_name"] or "Binh Tran" in pair["participant_2_name"]
    # cross-church pair shows both church codes
    assert "RPC" in pair["church_team"] and "TLC" in pair["church_team"]


def test_build_pod_entries_review_doubles_missing_partner():
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {"sport_type": "Pickleball", "sport_gender": "Women", "sport_format": "Women Double",
         "Participant ID (WP)": "50", "First Name": "Cam", "Last Name": "Ho",
         "partner_name": "", "Church Team": "RPC"},
    ]
    rows = builder._build_pod_entries_review_rows(roster_rows, [])

    assert len(rows) == 1
    entry = rows[0]
    assert entry["entry_type"] == "UnresolvedDoubles"
    assert entry["partner_status"] == "MissingPartner"
    assert entry["review_status"] == "NeedsReview"


def test_build_pod_entries_review_doubles_non_reciprocal():
    builder = ScheduleWorkbookBuilder()
    # A claims B, B claims someone else (non-reciprocal)
    roster_rows = [
        {"sport_type": "Badminton", "sport_gender": "Mixed", "sport_format": "Mixed Double",
         "Participant ID (WP)": "60", "First Name": "Dan", "Last Name": "Vo",
         "partner_name": "Linh Pham", "Church Team": "RPC"},
        {"sport_type": "Badminton", "sport_gender": "Mixed", "sport_format": "Mixed Double",
         "Participant ID (WP)": "61", "First Name": "Linh", "Last Name": "Pham",
         "partner_name": "Khoa Bui", "Church Team": "RPC"},  # claims Khoa, not Dan
    ]
    rows = builder._build_pod_entries_review_rows(roster_rows, [])

    unresolved = [r for r in rows if r["entry_type"] == "UnresolvedDoubles"]
    assert len(unresolved) >= 1
    reasons = {r["partner_status"] for r in unresolved}
    assert "NonReciprocal" in reasons


def test_build_pod_entries_review_anomaly():
    builder = ScheduleWorkbookBuilder()
    roster_rows = [
        {"sport_type": "Table Tennis 35+", "sport_gender": "Men", "sport_format": "Team",
         "Participant ID (WP)": "70", "First Name": "Tri", "Last Name": "Nguyen",
         "Church Team": "RPC"},
    ]
    rows = builder._build_pod_entries_review_rows(roster_rows, [])

    assert len(rows) == 1
    assert rows[0]["entry_type"] == "Anomaly"
    assert rows[0]["review_status"] == "NeedsReview"
    assert "Team" in rows[0]["notes"]


def test_build_scenario_schedule_pool_before_playoffs():
    """Pool before early playoffs, early playoffs on sat2, finals pinned to sun2."""
    pool_queues = [
        [f"BBM-{i:02d}" for i in range(1, 5)],
        [f"VBM-{i:02d}" for i in range(1, 5)],
        [f"VBW-{i:02d}" for i in range(1, 5)],
    ]
    early_playoff_queues = [
        ["BBM-Semi-1", "BBM-Semi-2"],
        ["VBM-Semi-1", "VBM-Semi-2"],
        ["VBW-Semi-1", "VBW-Semi-2"],
    ]
    final_queues = [
        ["BBM-Final"],
        ["VBM-Final"],
        ["VBW-Final"],
    ]

    n_sat, n_sun = 13, 8

    for n_courts in [3, 4, 5]:
        grids = ScheduleWorkbookBuilder._build_scenario_schedule(
            n_courts, pool_queues, early_playoff_queues, final_queues, n_sat, n_sun
        )
        sat1_cells = [cell for row in grids[0] for cell in row if cell]
        sun1_cells = [cell for row in grids[1] for cell in row if cell]
        sat2_cells = [cell for row in grids[2] for cell in row if cell]
        sun2_cells = [cell for row in grids[3] for cell in row if cell]

        all_pool  = {g for q in pool_queues for g in q}
        all_early = {g for q in early_playoff_queues for g in q}
        all_final = {g for q in final_queues for g in q}

        # All pool games appear in sat1/sun1/sat2
        assert set(sat1_cells + sun1_cells + sat2_cells) & all_pool == all_pool, \
            f"n_courts={n_courts}: missing pool games"

        # No playoff/final games in sat1 or sun1
        assert not (set(sat1_cells) & (all_early | all_final)), \
            f"n_courts={n_courts}: playoff/final in sat1"
        assert not (set(sun1_cells) & (all_early | all_final)), \
            f"n_courts={n_courts}: playoff/final in sun1"

        # Early playoffs land on sat2, not sun2
        assert set(sat2_cells) & all_early == all_early, \
            f"n_courts={n_courts}: early playoffs missing from sat2"
        assert not (set(sun2_cells) & all_early), \
            f"n_courts={n_courts}: early playoffs leaked into sun2"

        # Finals land on sun2, not sat2
        assert set(sun2_cells) & all_final == all_final, \
            f"n_courts={n_courts}: finals missing from sun2"
        assert not (set(sat2_cells) & all_final), \
            f"n_courts={n_courts}: finals leaked into sat2"

        # Pool games never appear in sun2
        assert not (set(sun2_cells) & all_pool), \
            f"n_courts={n_courts}: pool games leaked into sun2"

        # Playoffs/finals stay on their primary court blocks
        n_sports = len(pool_queues)
        base = n_courts // n_sports
        extras = n_courts % n_sports
        cur = 0
        for sport_idx, (early_q, final_q) in enumerate(zip(early_playoff_queues, final_queues)):
            k = base + (1 if sport_idx < extras else 0)
            sport_courts = set(range(cur, cur + k))
            cur += k
            playoff_ids = set(early_q) | set(final_q)
            for sess_idx in [2, 3]:  # sat2, sun2 only
                for t, row in enumerate(grids[sess_idx]):
                    for c_idx, game_id in enumerate(row):
                        if game_id in playoff_ids:
                            assert c_idx in sport_courts, (
                                f"n_courts={n_courts} sport={sport_idx}: "
                                f"{game_id} on court {c_idx}, expected {sport_courts}"
                            )


def test_pod_resource_estimate_no_venue_input(tmp_path):
    """When no venue_input.xlsx exists, tab still renders with notice row."""
    builder = ScheduleWorkbookBuilder()
    # Provide zero registrations — all entries will be 0.
    available = {}  # empty — no venue file
    pod_rows = builder._build_pod_resource_rows([], available)

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    builder._write_pod_resource_estimate(ws, pod_rows, available)

    # All Fit Status cells say "No venue data"
    fit_values = {ws.cell(row=r, column=7).value for r in range(2, 2 + len(pod_rows))}
    assert fit_values == {"No venue data"}, f"Unexpected fit values: {fit_values}"


def test_pod_resource_estimate_fit_status_rules():
    """Green/Yellow/Red thresholds from POD_FIT_YELLOW_MAX (= 3)."""
    builder = ScheduleWorkbookBuilder()
    from config import POD_RESOURCE_TYPE_BADMINTON, POD_FIT_YELLOW_MAX

    # Build roster rows: 10 Badminton singles → Required = 9
    roster_rows = [
        {"sport_type": "Badminton", "sport_format": "Men Singles"} for _ in range(10)
    ]

    # Green: available >= required (9)
    green = builder._build_pod_resource_rows(
        roster_rows, {POD_RESOURCE_TYPE_BADMINTON: 9}
    )
    badminton_green = next(r for r in green if "Badminton" in r["Event"])
    assert badminton_green["Fit Status"] == "Green"
    assert badminton_green["Surplus / Shortage"] == 0

    # Yellow: short by 1 to POD_FIT_YELLOW_MAX (3)
    yellow = builder._build_pod_resource_rows(
        roster_rows, {POD_RESOURCE_TYPE_BADMINTON: 9 - POD_FIT_YELLOW_MAX}
    )
    badminton_yellow = next(r for r in yellow if "Badminton" in r["Event"])
    assert badminton_yellow["Fit Status"] == "Yellow"

    # Red: short by more than POD_FIT_YELLOW_MAX
    red = builder._build_pod_resource_rows(
        roster_rows, {POD_RESOURCE_TYPE_BADMINTON: 9 - POD_FIT_YELLOW_MAX - 1}
    )
    badminton_red = next(r for r in red if "Badminton" in r["Event"])
    assert badminton_red["Fit Status"] == "Red"


def test_load_venue_input_aggregates_by_resource_type(tmp_path):
    """Available Slots are summed across multiple rows of the same resource type."""
    from openpyxl import Workbook
    from config import POD_RESOURCE_TYPE_PICKLEBALL

    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)

    # Two Pickleball Court rows: 24 + 18 = 42 total
    ws.cell(row=2, column=3, value=POD_RESOURCE_TYPE_PICKLEBALL)
    ws.cell(row=2, column=9, value=24)
    ws.cell(row=3, column=3, value=POD_RESOURCE_TYPE_PICKLEBALL)
    ws.cell(row=3, column=9, value=18)

    path = tmp_path / "venue_input.xlsx"
    wb.save(path)

    result = ScheduleWorkbookBuilder._load_venue_input(path)
    assert result[POD_RESOURCE_TYPE_PICKLEBALL] == 42


def test_load_venue_input_fallback_formula(tmp_path):
    """When Available Slots is zero/missing, compute from Quantity/times/Slot Minutes."""
    from openpyxl import Workbook
    from config import POD_RESOURCE_TYPE_TENNIS

    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)

    # 4 courts, 13:00–18:00, 60-min slots → (18-13)*60/60 + 1 = 6 starts → 4*6 = 24
    ws.cell(row=2, column=3, value=POD_RESOURCE_TYPE_TENNIS)
    ws.cell(row=2, column=4, value=4)    # Quantity
    ws.cell(row=2, column=6, value=13)   # Start Time (decimal hour)
    ws.cell(row=2, column=7, value=18)   # Last Start Time
    ws.cell(row=2, column=8, value=60)   # Slot Minutes
    ws.cell(row=2, column=9, value=0)    # Available Slots = 0 → triggers fallback

    path = tmp_path / "venue_input.xlsx"
    wb.save(path)

    result = ScheduleWorkbookBuilder._load_venue_input(path)
    assert result[POD_RESOURCE_TYPE_TENNIS] == 24


def test_load_venue_input_ignores_blank_resource_rows(tmp_path):
    """Blank resource rows should be ignored instead of creating a literal 'nan' bucket."""
    from openpyxl import Workbook
    from config import POD_RESOURCE_TYPE_PICKLEBALL

    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)

    ws.cell(row=2, column=3, value=POD_RESOURCE_TYPE_PICKLEBALL)
    ws.cell(row=2, column=9, value=24)
    ws.cell(row=3, column=3, value=None)
    ws.cell(row=3, column=9, value=None)

    path = tmp_path / "venue_input.xlsx"
    wb.save(path)

    result = ScheduleWorkbookBuilder._load_venue_input(path)
    assert result == {POD_RESOURCE_TYPE_PICKLEBALL: 24}


def test_build_gym_game_objects_structure():
    """Each game object has all required OR-Tools schema fields."""
    builder = ScheduleWorkbookBuilder()
    games = builder._build_gym_game_objects(_make_gym_roster())
    assert games, "Expected at least one game"
    required_fields = {
        "game_id", "event", "stage", "pool_id", "round",
        "team_a_id", "team_b_id", "duration_minutes",
        "resource_type", "earliest_slot", "latest_slot",
    }
    for g in games:
        assert required_fields <= g.keys(), f"Missing fields in {g}"
    from config import GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL
    valid_types = {GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL}
    assert all(g["resource_type"] in valid_types for g in games), \
        f"Unexpected resource_type(s): {[g['resource_type'] for g in games]}"
    # team_a_id and team_b_id must be non-null strings for all games (pool + playoff)
    assert all(
        isinstance(g["team_a_id"], str) and isinstance(g["team_b_id"], str)
        for g in games
    ), "All games must have non-null team_a_id and team_b_id"


def test_build_gym_game_objects_stages():
    """With 8 BBM teams, only Pool stage is present (playoffs go in Playoff-Slots tab)."""
    builder = ScheduleWorkbookBuilder()
    games = builder._build_gym_game_objects(_make_gym_roster(8))
    bbm_stages = {g["stage"] for g in games if g["event"] == SPORT_TYPE["BASKETBALL"]}
    assert bbm_stages == {"Pool"}, f"Expected only Pool stage; got {bbm_stages}"


def test_build_gym_game_objects_prefix_format():
    """Pool game IDs follow the BBM-01 format."""
    builder = ScheduleWorkbookBuilder()
    games = builder._build_gym_game_objects(_make_gym_roster())
    pool_ids = [g["game_id"] for g in games if g["stage"] == "Pool" and g["event"] == SPORT_TYPE["BASKETBALL"]]
    assert pool_ids, "Expected Basketball pool games"
    import re
    assert all(re.match(r"BBM-\d{2}$", gid) for gid in pool_ids)


def test_build_gym_game_objects_stable_team_ids():
    """The same placeholder team ID is reused across multiple pool games for that team."""
    builder = ScheduleWorkbookBuilder()
    games = builder._build_gym_game_objects(_make_gym_roster(8))
    bbm_pool = [g for g in games if g["stage"] == "Pool" and g["event"] == SPORT_TYPE["BASKETBALL"]]
    assert bbm_pool, "Expected Basketball pool games"

    # Collect all team IDs and count appearances
    from collections import Counter
    appearances: Counter = Counter()
    for g in bbm_pool:
        appearances[g["team_a_id"]] += 1
        appearances[g["team_b_id"]] += 1

    # The live Basketball default is now 3 games/team, so 8 teams split into
    # two 4-team round-robin pools and every placeholder appears 3 times.
    assert appearances, "Expected stable placeholder team IDs to be reused"
    assert all(count == 3 for count in appearances.values()), appearances


def test_build_gym_game_objects_pool_id_nonempty():
    """Pool games carry a non-empty pool_id; playoff/final games have empty pool_id."""
    builder = ScheduleWorkbookBuilder()
    games = builder._build_gym_game_objects(_make_gym_roster(8))
    pool_games = [g for g in games if g["stage"] == "Pool"]
    playoff_games = [g for g in games if g["stage"] not in ("Pool",)]

    assert pool_games, "Expected pool games"
    assert all(g["pool_id"] != "" for g in pool_games), "Pool games must have non-empty pool_id"
    assert all(g["pool_id"] == "" for g in playoff_games), "Playoff/final games must have empty pool_id"


def test_build_gym_game_objects_team_id_format():
    """Pool game team IDs follow the stable placeholder format PREFIX-Px-Ty."""
    import re as _re
    builder = ScheduleWorkbookBuilder()
    games = builder._build_gym_game_objects(_make_gym_roster(8))
    bbm_pool = [g for g in games if g["stage"] == "Pool" and g["event"] == SPORT_TYPE["BASKETBALL"]]
    for g in bbm_pool:
        assert _re.match(r"BBM-P\d+-T\d+$", g["team_a_id"]), f"Unexpected team_a_id: {g['team_a_id']}"
        assert _re.match(r"BBM-P\d+-T\d+$", g["team_b_id"]), f"Unexpected team_b_id: {g['team_b_id']}"


def test_build_schedule_input_gym_court_scenario(tmp_path):
    """Fallback path: gym resources cover all four sessions split by basketball/volleyball."""
    from config import SCHEDULE_SOLVER_GYM_COURTS, GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL
    builder = ScheduleWorkbookBuilder()
    si = builder._build_schedule_input(_make_gym_roster(), [], tmp_path / "missing.xlsx")
    assert si["gym_court_scenario"] == SCHEDULE_SOLVER_GYM_COURTS
    gym_resources = [r for r in si["resources"] if r["resource_type"] in (GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL)]
    n_sessions = 4  # Sat-1, Sun-1, Sat-2, Sun-2
    assert len(gym_resources) == SCHEDULE_SOLVER_GYM_COURTS * n_sessions
    # Allocation source should be "fallback" when venue_input.xlsx is absent
    assert si.get("gym_allocation", {}).get("source") == "fallback"


def test_build_schedule_input_legacy_venue_rows_do_not_add_fallback_gyms(tmp_path):
    """Legacy Venue-Input rows should be used directly instead of adding fallback gym courts."""
    from config import GYM_RESOURCE_TYPE_BASKETBALL

    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    rows = [
        ["Main Gym", "Church Main Gym", GYM_RESOURCE_TYPE_BASKETBALL,
         1, "2026-07-18", 8, 10, 60, None, None, None, None],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, rows)

    builder = ScheduleWorkbookBuilder()
    si = builder._build_schedule_input(_make_gym_roster(), [], path)

    assert si["gym_allocation"]["source"] == "direct_venue_input"
    assert si["resource_count"] == 1
    assert {g["resource_type"] for g in si["games"]} == {GYM_RESOURCE_TYPE_BASKETBALL}
    assert [r["resource_type"] for r in si["resources"]] == [GYM_RESOURCE_TYPE_BASKETBALL]
    assert si["resources"][0]["day"] == "Sat-1"
    assert si["resources"][0]["venue_name"] == "Church Main Gym"


def test_build_schedule_input_grouped_rows_without_gym_modes_use_direct_resources(tmp_path):
    """Grouped venue rows should not be dropped when Gym-Modes is missing."""
    from config import GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL

    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity", "Day",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Exclusive Venue Group", "Contact", "Cost", "Notes",
    ]
    rows = [
        ["Main Gym", "Church Main Gym", GYM_RESOURCE_TYPE_BASKETBALL, 1, "Sat-1",
         "2026-07-18", 8, 12, 60, None, "Main Gym", None, None, None],
        ["Main Gym", "Church Main Gym", GYM_RESOURCE_TYPE_VOLLEYBALL, 2, "Sat-1",
         "2026-07-18", 8, 12, 60, None, "Main Gym", None, None, None],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, rows)

    builder = ScheduleWorkbookBuilder()
    si = builder._build_schedule_input(_make_gym_roster(), [], path)

    assert si["gym_allocation"]["source"] == "direct_venue_input"
    assert si["gym_allocation"]["reason"] == "grouped_rows_without_gym_modes"
    assert {r["resource_type"] for r in si["resources"]} == {
        GYM_RESOURCE_TYPE_BASKETBALL,
        GYM_RESOURCE_TYPE_VOLLEYBALL,
    }
    assert {g["resource_type"] for g in si["games"]} == {GYM_RESOURCE_TYPE_BASKETBALL}


def test_build_schedule_input_allocator_omits_zero_team_gym_sports(tmp_path):
    """Allocator-backed schedule input should omit placeholder sports with no estimating teams."""
    from config import GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL

    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity", "Day",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Exclusive Venue Group", "Contact", "Cost", "Notes",
    ]
    rows = [
        ["Main Gym", "Church Main Gym", GYM_RESOURCE_TYPE_BASKETBALL, 1, "Sat-1",
         "2026-07-18", 8, 12, 60, None, "Main Gym", None, None, None],
        ["Main Gym", "Church Main Gym", GYM_RESOURCE_TYPE_VOLLEYBALL, 2, "Sat-1",
         "2026-07-18", 8, 12, 60, None, "Main Gym", None, None, None],
    ]
    gym_modes = [
        ["Gym Name", "Basketball Courts", "Volleyball Courts"],
        ["Main Gym", 1, 2],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, rows, gym_modes_rows=gym_modes)

    builder = ScheduleWorkbookBuilder()
    si = builder._build_schedule_input(_make_gym_roster(), [], path)

    assert si["gym_allocation"]["source"] == "allocator"
    assert {g["resource_type"] for g in si["games"]} == {GYM_RESOURCE_TYPE_BASKETBALL}
    assert {r["resource_type"] for r in si["resources"]} == {GYM_RESOURCE_TYPE_BASKETBALL}


def test_build_pod_game_objects_single_elimination():
    """With 3 entries in a division, 2 game placeholders are generated."""
    from config import POD_RESOURCE_EVENT_TYPE

    roster_rows = [
        {"Church Team": "RPC", "Participant ID (WP)": i,
         "sport_type": SPORT_TYPE["BADMINTON"], "sport_gender": "Women",
         "sport_format": "Women Single"}
        for i in range(1, 4)  # 3 entries
    ]
    builder = ScheduleWorkbookBuilder()
    games = builder._build_pod_game_objects(roster_rows, [])
    assert len(games) == 2, f"Expected 2 games (3-1=2), got {len(games)}"
    assert all(g["game_id"].startswith("BAD-Women-Singles-") for g in games)
    assert all(g["stage"] == "R1" for g in games)
    assert all(g["resource_type"] == POD_RESOURCE_EVENT_TYPE[SPORT_TYPE["BADMINTON"]] for g in games)
    assert games[0]["game_id"] == "BAD-Women-Singles-01"


def test_build_pod_game_objects_skips_empty_divisions():
    """Divisions with fewer than 2 entries produce no game objects."""
    roster_rows = [
        {"Church Team": "RPC", "Participant ID (WP)": 1,
         "sport_type": SPORT_TYPE["BADMINTON"], "sport_gender": "Men",
         "sport_format": "Men Single"},
    ]
    builder = ScheduleWorkbookBuilder()
    games = builder._build_pod_game_objects(roster_rows, [])
    assert games == [], "Single-entry division should produce no games"


def test_build_gym_resource_objects_count():
    """4 sessions × (n_basketball + n_volleyball) resources are returned."""
    resources = ScheduleWorkbookBuilder._build_gym_resource_objects(n_basketball=2, n_volleyball=2)
    assert len(resources) == 16, f"Expected 4 sessions × 4 courts = 16, got {len(resources)}"
    from config import GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL
    valid_types = {GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL}
    assert all(r["resource_type"] in valid_types for r in resources)
    days = {r["day"] for r in resources}
    assert days == {"Sat-1", "Sun-1", "Sat-2", "Sun-2"}
    bb = [r for r in resources if r["resource_type"] == GYM_RESOURCE_TYPE_BASKETBALL]
    vb = [r for r in resources if r["resource_type"] == GYM_RESOURCE_TYPE_VOLLEYBALL]
    assert len(bb) == 8, f"Expected 4 sessions × 2 basketball courts = 8, got {len(bb)}"
    assert len(vb) == 8, f"Expected 4 sessions × 2 volleyball courts = 8, got {len(vb)}"


def test_build_gym_resource_objects_labels():
    """Court labels and resource_ids are formatted correctly."""
    resources = ScheduleWorkbookBuilder._build_gym_resource_objects(n_basketball=2, n_volleyball=1)
    labels = {r["label"] for r in resources}
    assert labels == {"Court-1", "Court-2", "Court-3"}
    ids = {r["resource_id"] for r in resources}
    assert "GYM-Sat-1-1" in ids
    assert "GYM-Sun-2-3" in ids


def test_build_gym_resource_objects_include_blank_exclusive_group():
    """Gym resources carry the same exclusive_group field as venue-loaded resources."""
    resources = ScheduleWorkbookBuilder._build_gym_resource_objects(n_basketball=1, n_volleyball=1)
    assert resources
    assert all("exclusive_group" in r for r in resources)
    assert all(r["exclusive_group"] == "" for r in resources)


def test_load_venue_input_rows_missing_file(tmp_path):
    """Returns empty list when venue_input.xlsx does not exist."""
    result = ScheduleWorkbookBuilder._load_venue_input_rows(tmp_path / "missing.xlsx")
    assert result == []


def test_load_venue_input_rows_expands_quantity(tmp_path):
    """Quantity=2 for a Tennis Court row yields 2 resource objects."""
    from openpyxl import Workbook
    from config import POD_RESOURCE_TYPE_TENNIS

    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    ws.cell(row=2, column=3, value=POD_RESOURCE_TYPE_TENNIS)
    ws.cell(row=2, column=4, value=2)    # Quantity = 2
    ws.cell(row=2, column=6, value=9)    # Start Time
    ws.cell(row=2, column=7, value=17)   # Last Start Time
    ws.cell(row=2, column=8, value=30)   # Slot Minutes

    path = tmp_path / "venue_input.xlsx"
    wb.save(path)

    result = ScheduleWorkbookBuilder._load_venue_input_rows(path)
    assert len(result) == 2
    assert result[0]["resource_type"] == POD_RESOURCE_TYPE_TENNIS
    assert result[0]["label"] == "Court-1"
    assert result[1]["label"] == "Court-2"
    assert result[0]["open_time"] == "09:00"
    assert result[0]["day"] == "Day-1"


def test_load_venue_input_rows_table_label(tmp_path):
    """Table Tennis Table rows get Table-N labels instead of Court-N."""
    from openpyxl import Workbook
    from config import POD_RESOURCE_TYPE_TABLE_TENNIS

    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    ws.cell(row=2, column=3, value=POD_RESOURCE_TYPE_TABLE_TENNIS)
    ws.cell(row=2, column=4, value=3)
    ws.cell(row=2, column=6, value=9)
    ws.cell(row=2, column=7, value=17)
    ws.cell(row=2, column=8, value=20)

    path = tmp_path / "venue_input.xlsx"
    wb.save(path)

    result = ScheduleWorkbookBuilder._load_venue_input_rows(path)
    assert len(result) == 3
    assert all(r["label"].startswith("Table-") for r in result)


def test_load_venue_input_rows_skips_blank_resource_rows(tmp_path):
    """Blank/NaN venue rows should be ignored instead of crashing Schedule-Input generation."""
    from openpyxl import Workbook
    from config import POD_RESOURCE_TYPE_TENNIS

    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    ws.cell(row=2, column=3, value=POD_RESOURCE_TYPE_TENNIS)
    ws.cell(row=2, column=4, value=2)
    ws.cell(row=2, column=6, value=9)
    ws.cell(row=2, column=7, value=17)
    ws.cell(row=2, column=8, value=30)
    ws.cell(row=3, column=3, value=None)
    ws.cell(row=3, column=4, value=None)
    ws.cell(row=3, column=6, value=None)
    ws.cell(row=3, column=7, value=None)
    ws.cell(row=3, column=8, value=None)

    path = tmp_path / "venue_input.xlsx"
    wb.save(path)

    result = ScheduleWorkbookBuilder._load_venue_input_rows(path)
    assert len(result) == 2
    assert all(r["resource_type"] == POD_RESOURCE_TYPE_TENNIS for r in result)


def test_load_venue_input_rows_reads_exclusive_group(tmp_path):
    """Exclusive Venue Group column is attached to each emitted resource object."""
    from config import POD_RESOURCE_TYPE_TENNIS

    headers = [
        "Pod Name", "Venue Name", "Exclusive Venue Group", "Resource Type",
        "Quantity", "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    rows = [
        ["BB Pod", "Midsize Gym", "Midsize Gym", POD_RESOURCE_TYPE_TENNIS,
         2, None, 9, 17, 30, None, None, None, None],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, rows)

    result = ScheduleWorkbookBuilder._load_venue_input_rows(path)
    assert len(result) == 2
    assert all(r["exclusive_group"] == "Midsize Gym" for r in result)
    assert all(r["venue_name"] == "Midsize Gym" for r in result)


def test_load_venue_input_rows_blank_exclusive_group(tmp_path):
    """A row with no Exclusive Venue Group yields an empty-string group."""
    from config import POD_RESOURCE_TYPE_TENNIS

    headers = [
        "Pod Name", "Venue Name", "Exclusive Venue Group", "Resource Type",
        "Quantity", "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    rows = [
        ["Tennis Pod", "Chapman", None, POD_RESOURCE_TYPE_TENNIS,
         1, None, 9, 17, 60, None, None, None, None],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, rows)

    result = ScheduleWorkbookBuilder._load_venue_input_rows(path)
    assert result[0]["exclusive_group"] == ""
    assert result[0]["venue_name"] == "Chapman"


def test_load_venue_input_rows_derives_day_labels_from_date_column(tmp_path):
    """Date-only venue rows should map to logical weekday labels like Fri-*/Sat-*."""
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    rows = [
        ["Basketball Pod", "HS Small Gym", "Basketball Court", 1,
         "2026-07-17", 17, 21, 60, None, None, None, None],
        ["Basketball Pod", "HS Small Gym", "Basketball Court", 1,
         "2026-07-18", 8, 16, 60, None, None, None, None],
        ["Basketball Pod", "HS Small Gym", "Basketball Court", 1,
         "2026-07-19", 12, 20, 60, None, None, None, None],
        ["Basketball Pod", "HS Small Gym", "Basketball Court", 1,
         "2026-07-25", 8, 17, 60, None, None, None, None],
        ["Basketball Pod", "HS Small Gym", "Basketball Court", 1,
         "2026-07-26", 12, 17, 60, None, None, None, None],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, rows)

    result = ScheduleWorkbookBuilder._load_venue_input_rows(path)
    assert [r["day"] for r in result] == ["Fri-1", "Sat-1", "Sun-1", "Sat-2", "Sun-2"]


def test_load_venue_input_rows_normalizes_resource_types_and_prefixes(tmp_path):
    """Human-friendly resource names should normalize to canonical scheduler IDs."""
    headers = [
        "Pod Name", "Venue Name", "Resource Type", "Quantity",
        "Date", "Start Time", "Last Start Time", "Slot Minutes",
        "Available Slots", "Contact", "Cost", "Notes",
    ]
    rows = [
        ["Bible Challenge", "Library", "Jeopardy stage", 1,
         "2026-07-18", 11, 20, 60, None, None, None, None],
        ["Soccer", "Field", "Soccer field", 1,
         "2026-07-18", 11, 17, 60, None, None, None, None],
        ["Table Tennis", "Chapel", "Table Tennis station", 1,
         "2026-07-18", 17, 21, 20, None, None, None, None],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, rows)

    result = ScheduleWorkbookBuilder._load_venue_input_rows(path)
    assert [r["resource_type"] for r in result] == [
        "BC Station",
        "Soccer Field",
        "Table Tennis Table",
    ]
    assert [r["resource_id"] for r in result] == [
        "BC-Sat-1-1",
        "SOC-Sat-1-1",
        "TT-Sat-1-1",
    ]


def test_load_gym_modes_missing_file(tmp_path):
    """Returns empty dict when venue_input.xlsx does not exist."""
    assert ScheduleWorkbookBuilder._load_gym_modes(tmp_path / "missing.xlsx") == {}


def test_load_gym_modes_missing_tab(tmp_path):
    """File present but no Gym-Modes tab → empty dict (warning, no crash)."""
    headers = ["Pod Name", "Resource Type", "Quantity"]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, [["P", "Tennis Court", 1]])
    assert ScheduleWorkbookBuilder._load_gym_modes(path) == {}


def test_load_gym_modes_reads_capacities(tmp_path):
    """Gym-Modes tab is parsed into {gym: {resource_type: courts_per_block}}."""
    headers = ["Pod Name", "Resource Type", "Quantity"]
    gym_modes = [
        ["Gym Name", "Basketball Courts", "Volleyball Courts",
         "Badminton Courts", "Pickleball Courts", "Soccer Fields", "Notes"],
        ["Midsize Gym", 1, 2, 6, 8, 1, "either-or"],
        ["Big Gym", 2, 3, 12, 0, 0, "larger"],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, [["P", "Tennis Court", 1]], gym_modes)

    result = ScheduleWorkbookBuilder._load_gym_modes(path)
    assert result["Midsize Gym"] == {
        "Basketball Court": 1, "Volleyball Court": 2,
        "Badminton Court": 6, "Pickleball Court": 8, "Soccer Field": 1,
    }
    assert result["Big Gym"]["Volleyball Court"] == 3
    assert result["Big Gym"]["Pickleball Court"] == 0


def test_load_gym_modes_trims_header_whitespace(tmp_path):
    """Operator-edited headers with trailing spaces are normalized before row access."""
    headers = ["Pod Name", "Resource Type", "Quantity"]
    gym_modes = [
        ["Gym Name ", "Basketball Courts ", "Volleyball Courts ", "Notes "],
        ["Midsize Gym", 1, 2, "either-or"],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, [["P", "Tennis Court", 1]], gym_modes)

    result = ScheduleWorkbookBuilder._load_gym_modes(path)
    assert result["Midsize Gym"]["Basketball Court"] == 1
    assert result["Midsize Gym"]["Volleyball Court"] == 2


def test_load_gym_modes_skips_note_row(tmp_path):
    """A footer row with text in Gym Name but no capacities is ignored."""
    headers = ["Pod Name", "Resource Type", "Quantity"]
    gym_modes = [
        ["Gym Name", "Basketball Courts", "Volleyball Courts",
         "Badminton Courts", "Pickleball Courts", "Soccer Fields", "Notes"],
        ["Midsize Gym", 1, 2, 6, 8, 1, "either-or"],
        ["Capacity-per-mode coefficients for the LP estimator.",
         None, None, None, None, None, None],
    ]
    path = tmp_path / "venue_input.xlsx"
    _write_venue_input(path, headers, [["P", "Tennis Court", 1]], gym_modes)

    result = ScheduleWorkbookBuilder._load_gym_modes(path)
    assert list(result.keys()) == ["Midsize Gym"]


def test_build_schedule_input_keys(tmp_path):
    """_build_schedule_input returns dict with all required top-level keys."""
    builder = ScheduleWorkbookBuilder()
    si = builder._build_schedule_input(_make_gym_roster(), [], tmp_path / "missing.xlsx")
    assert set(si.keys()) == {
        "generated_at", "gym_court_scenario", "game_count", "resource_count",
        "games", "resources", "playoff_slots", "gym_modes", "gym_allocation",
        "team_conflicts", "precedence",
    }
    assert si["game_count"] == len(si["games"])
    assert si["resource_count"] == len(si["resources"])
    assert si["game_count"] > 0
    assert si["resource_count"] > 0  # at least gym resources


def test_build_schedule_input_uses_pool_assignments_for_core_gym_games(tmp_path):
    """Layer 2 schedule input should replace gym placeholders with assigned real teams."""
    builder = ScheduleWorkbookBuilder()
    roster_rows = []
    for participant_id in range(1, 11):
        roster_rows.append({
            "Church Team": "OCB",
            "sport_type": SPORT_TYPE["BASKETBALL"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": participant_id,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],
        })
        roster_rows.append({
            "Church Team": "RPC",
            "sport_type": SPORT_TYPE["BASKETBALL"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": participant_id + 100,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],
        })
        roster_rows.append({
            "Church Team": "OCB",
            "sport_type": SPORT_TYPE["VOLLEYBALL_MEN"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": participant_id,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],
        })
        roster_rows.append({
            "Church Team": "ANH",
            "sport_type": SPORT_TYPE["VOLLEYBALL_MEN"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": participant_id + 200,
            "participant_primary_sport": SPORT_TYPE["VOLLEYBALL_MEN"],
        })

    si = builder._build_schedule_input(roster_rows, [], tmp_path / "missing.xlsx")

    bb_game = next(game for game in si["games"] if game["event"] == SPORT_TYPE["BASKETBALL"])
    assert bb_game["team_a_id"].startswith("BBM::") or bb_game["team_b_id"].startswith("BBM::")
    assert bb_game["solver_pool"] == "Gym Core"
    assert any(
        {"BBM::", "VBM::"} == {
            edge["team_a_id"].split("::")[0] + "::",
            edge["team_b_id"].split("::")[0] + "::",
        }
        for edge in si["team_conflicts"]
    )


def test_build_assigned_gym_game_objects_fallback_counts_team_order_units():
    roster_rows = []
    for church_code in ("RPC", "OCB"):
        for team_order in ("A", "B"):
            for participant_id in range(5):
                roster_rows.append(
                    {
                        "Church Team": church_code,
                        "team_order": team_order,
                        "sport_type": SPORT_TYPE["BASKETBALL"],
                        "sport_gender": "Men",
                        "sport_format": "Team",
                        "Participant ID (WP)": f"{church_code}-{team_order}-{participant_id}",
                    }
                )

    games = ScheduleWorkbookBuilder._build_assigned_gym_game_objects(
        roster_rows,
        [],
        allow_placeholder_fallback=False,
    )

    basketball_games = [
        game for game in games if game["event"] == SPORT_TYPE["BASKETBALL"]
    ]
    assert len(basketball_games) == 6


def test_classmethod_schedule_helpers_do_not_instantiate_exporter_subclass():
    class CountingBuilder(ScheduleWorkbookBuilder):
        init_calls = 0

        def __init__(self):
            type(self).init_calls += 1
            super().__init__()

    CountingBuilder._build_core_gym_team_lookup([])
    assert CountingBuilder.init_calls == 0


def test_build_schedule_output_flat_rows_count():
    """Returns one row per assignment."""
    so, si = _make_render_schedule_pair()
    rows = ScheduleWorkbookBuilder._build_schedule_output_flat_rows(so, si)
    assert len(rows) == 2


def test_build_schedule_output_flat_rows_fields():
    """Each row contains expected keys with non-empty event."""
    so, si = _make_render_schedule_pair()
    rows = ScheduleWorkbookBuilder._build_schedule_output_flat_rows(so, si)
    required = {"game_id", "event", "stage", "round", "team_a_id", "team_b_id",
                "resource_label", "day", "slot", "duration_minutes"}
    for row in rows:
        assert required.issubset(row.keys())
        assert row["event"] == "Basketball - Men Team"


def test_build_schedule_output_flat_rows_sorted():
    """Rows are sorted Pool before Final (stage order)."""
    so, si = _make_render_schedule_pair()
    rows = ScheduleWorkbookBuilder._build_schedule_output_flat_rows(so, si)
    stages = [r["stage"] for r in rows]
    assert stages == ["Pool", "Final"]


def test_build_schedule_output_flat_rows_time_part():
    """The slot field extracts the HH:MM part from the full slot label."""
    so, si = _make_render_schedule_pair()
    rows = ScheduleWorkbookBuilder._build_schedule_output_flat_rows(so, si)
    pool_row = next(r for r in rows if r["game_id"] == "BBM-01")
    assert pool_row["slot"] == "08:00"


def test_build_schedule_output_flat_rows_day_display():
    """Sat-1 is translated to '1st Sat'."""
    so, si = _make_render_schedule_pair()
    rows = ScheduleWorkbookBuilder._build_schedule_output_flat_rows(so, si)
    assert all(r["day"] == "1st Sat" for r in rows)


def test_build_schedule_output_flat_rows_empty():
    """Empty assignments list returns empty rows."""
    so = {"assignments": [], "unscheduled": []}
    si = {"games": [], "resources": [], "precedence": []}
    rows = ScheduleWorkbookBuilder._build_schedule_output_flat_rows(so, si)
    assert rows == []


def test_compute_court_slots_matches_normalized_policy_8teams_gpg2():
    """8 teams / gpg=2 now stays at 8 pool games under the normalized policy."""

    n_teams, gpg = 8, 2
    actual = len(ScheduleWorkbookBuilder._make_pool_game_pairs("_", n_teams, gpg))
    assert actual == 8  # pools [4,4] with 4-match matrices -> 4 + 4

    builder = ScheduleWorkbookBuilder()
    s_formula = builder._compute_court_slots(n_teams, pool_games_per_team=gpg)
    s_actual  = builder._compute_court_slots(n_teams, pool_games_per_team=gpg,
                                              actual_pool_games=actual)
    assert s_formula["pool_slots"] == 8
    assert s_actual["pool_slots"]  == 8


def test_make_pool_game_pairs_exact_two_games_per_team():
    """Normalized B4 policy keeps every team at the same exact pool-game count."""
    from collections import Counter

    cases = [
        (3, 2, 2, 3),
        (4, 2, 2, 4),
        (5, 2, 2, 5),
        (7, 2, 2, 7),
        (8, 2, 2, 8),
        (12, 2, 2, 12),
        (20, 2, 2, 20),
    ]
    for n_teams, gpg, expected_games_per_team, expected_total_games in cases:
        pairs = ScheduleWorkbookBuilder._make_pool_game_pairs("T", n_teams, gpg)
        games_per_team: Counter = Counter()
        for a, b, _ in pairs:
            games_per_team[a] += 1
            games_per_team[b] += 1
        assert len(pairs) == expected_total_games, (
            f"n_teams={n_teams}: total pool games {len(pairs)} != {expected_total_games}"
        )
        assert games_per_team, f"Expected generated games for n_teams={n_teams}"
        assert all(count == expected_games_per_team for count in games_per_team.values()), (
            f"n_teams={n_teams}, gpg={gpg}: {dict(games_per_team)}"
        )


def test_make_pool_game_pairs_direct_match_for_two_teams():
    """Two teams stay as a single direct match rather than an over-built pool."""

    pairs = ScheduleWorkbookBuilder._make_pool_game_pairs("T", 2, 2)
    assert pairs == [("T-P1-T1", "T-P1-T2", "P1")]


def test_make_pool_game_pairs_exact_three_games_per_team_even_counts():
    """3-game mode keeps even-count pools at exactly 3 games/team."""
    from collections import Counter

    cases = [
        (4, 6),
        (6, 9),
        (8, 12),
        (10, 15),
        (12, 18),
    ]
    for n_teams, expected_total_games in cases:
        pairs = ScheduleWorkbookBuilder._make_pool_game_pairs("T", n_teams, 3)
        games_per_team: Counter = Counter()
        for a, b, _ in pairs:
            games_per_team[a] += 1
            games_per_team[b] += 1
        assert len(pairs) == expected_total_games
        assert games_per_team
        assert all(count == 3 for count in games_per_team.values()), dict(games_per_team)


def test_make_pool_game_pairs_three_game_policy_odd_counts_use_one_extra_slot():
    """Odd-size 3-game pools keep everyone at 3 except the highest odd-pool slot."""
    from collections import Counter

    cases = [
        (5, [3, 3, 3, 3, 4]),
        (7, [3, 3, 3, 3, 3, 3, 4]),
        (9, [3, 3, 3, 3, 3, 3, 3, 3, 4]),
        (13, [3] * 12 + [4]),
    ]
    for n_teams, expected_counts in cases:
        pairs = ScheduleWorkbookBuilder._make_pool_game_pairs("T", n_teams, 3)
        games_per_team: Counter = Counter()
        for a, b, _ in pairs:
            games_per_team[a] += 1
            games_per_team[b] += 1
        assert sorted(games_per_team.values()) == expected_counts, (
            f"n_teams={n_teams}: {dict(games_per_team)}"
        )


def test_make_pool_game_pairs_reject_unsupported_target():
    """Only 2 and 3 games/team are supported for live team-sport planning."""
    import pytest

    with pytest.raises(ValueError, match="Only 2 and 3 games/team are supported"):
        ScheduleWorkbookBuilder._make_pool_game_pairs("T", 8, 4)


def test_summarize_pool_policy_three_game_note_for_odd_pool():
    """3-game mode should explain which odd-pool slot gets the extra game."""
    summary = ScheduleWorkbookBuilder._summarize_pool_policy(13, 3)

    assert summary["target_pool_games_per_team"] == 3
    assert summary["actual_pool_games_per_team"] == 3.08
    assert "5-team pools give T5 the extra 4th game" in summary["pool_composition"]
    assert summary["actual_pool_games"] == 20


def test_pool_sizes_for_assignment_follow_three_game_policy(monkeypatch):
    """Pool-Assignment should switch to 4/4/5 sizing when Basketball uses 3 games/team."""
    builder = ScheduleWorkbookBuilder()
    codes = [
        "RPC", "ANH", "FVC", "GAC", "NSD", "TLC", "GLA",
        "ORN", "WSD", "PCC", "PHX", "WAG", "NHC",
    ]
    monkeypatch.setitem(COURT_ESTIMATE_POOL_GAMES_PER_TEAM, SPORT_TYPE["BASKETBALL"], 3)

    assert builder._pool_sizes_for_assignment(
        SPORT_TYPE["BASKETBALL"],
        len(codes),
    ) == [4, 4, 5]


def test_build_gym_game_objects_follow_three_game_policy(monkeypatch):
    """Layer-2 bridge game generation should honor the explicit 3-game policy."""
    from collections import Counter

    builder = ScheduleWorkbookBuilder()
    codes = [
        "RPC", "ANH", "FVC", "GAC", "NSD", "TLC", "GLA",
        "ORN", "WSD", "PCC", "PHX", "WAG", "NHC",
    ]
    monkeypatch.setitem(COURT_ESTIMATE_POOL_GAMES_PER_TEAM, SPORT_TYPE["BASKETBALL"], 3)
    games = builder._build_gym_game_objects(_make_gym_roster_from_codes(codes))
    bbm_pool = [g for g in games if g["stage"] == "Pool" and g["event"] == SPORT_TYPE["BASKETBALL"]]

    appearances: Counter = Counter()
    for g in bbm_pool:
        appearances[g["team_a_id"]] += 1
        appearances[g["team_b_id"]] += 1

    assert len(bbm_pool) == 20
    assert sorted(appearances.values()) == ([3] * 12) + [4]


def test_compute_court_slots_consistent_with_make_pool_game_pairs():
    """pool_slots from _compute_court_slots equals len(_make_pool_game_pairs) for
    several (n_teams, gpg) combinations."""

    builder = ScheduleWorkbookBuilder()
    cases = [(2, 2), (5, 2), (8, 2), (12, 2), (9, 3), (13, 3)]
    for n_teams, gpg in cases:
        actual = len(ScheduleWorkbookBuilder._make_pool_game_pairs("_", n_teams, gpg))
        s = builder._compute_court_slots(n_teams, pool_games_per_team=gpg,
                                          actual_pool_games=actual)
        assert s["pool_slots"] == actual, (
            f"n_teams={n_teams}, gpg={gpg}: pool_slots={s['pool_slots']} != actual={actual}"
        )


def test_warn_if_schedules_mismatched_clean():
    """Returns True and no warning when all assignment IDs are in schedule_input."""

    so = {"assignments": [{"game_id": "G1", "resource_id": "R1", "slot": "Sat-1-08:00"}]}
    si = {"games": [{"game_id": "G1"}], "playoff_slots": []}
    assert ScheduleWorkbookBuilder._warn_if_schedules_mismatched(so, si) is True


def test_warn_if_schedules_mismatched_playoff_ok():
    """Returns True when assignment ID matches a playoff_slot, not a game."""

    so = {"assignments": [{"game_id": "BBM-Final", "resource_id": "R1", "slot": "Sat-2-14:00"}]}
    si = {"games": [], "playoff_slots": [{"game_id": "BBM-Final"}]}
    assert ScheduleWorkbookBuilder._warn_if_schedules_mismatched(so, si) is True


def test_warn_if_schedules_mismatched_detects_orphan():
    """Returns False and logs a warning when an assignment game_id is unknown."""
    from loguru import logger

    messages = []
    sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
    try:
        so = {"assignments": [{"game_id": "STALE-99", "resource_id": "R1", "slot": "Sat-1-08:00"}]}
        si = {"games": [{"game_id": "G1"}], "playoff_slots": []}
        result = ScheduleWorkbookBuilder._warn_if_schedules_mismatched(so, si)
    finally:
        logger.remove(sink_id)
    assert result is False
    assert any("STALE-99" in m for m in messages)
    assert any("different runs" in m for m in messages)


def test_warn_if_resource_slot_minutes_differ_from_config_is_advisory():
    """Mismatched venue slot sizes should warn without blocking Layer 2 generation."""
    from loguru import logger

    messages = []
    sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
    try:
        ScheduleWorkbookBuilder._warn_if_resource_slot_minutes_differ_from_config(
            all_games=[
                {
                    "game_id": "PCK-01",
                    "event": SPORT_TYPE["PICKLEBALL"],
                    "resource_type": POD_RESOURCE_TYPE_PICKLEBALL,
                    "duration_minutes": 30,
                }
            ],
            all_resources=[
                {
                    "resource_id": "PCK-Sat-1-1",
                    "resource_type": POD_RESOURCE_TYPE_PICKLEBALL,
                    "slot_minutes": 20,
                }
            ],
        )
    finally:
        logger.remove(sink_id)

    assert any("Layer 2 duration mismatch" in m for m in messages)
    assert any("Pickleball Court" in m for m in messages)
    assert any("config.py game duration is 30m" in m for m in messages)
    assert any("ignore this warning" in m for m in messages)


def test_write_schedule_output_report_creates_file(tmp_path):
    """_write_schedule_output_report writes an xlsx with all expected tabs."""
    import openpyxl
    so, si = _make_render_schedule_pair()
    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, so, si)
    assert out.exists()
    wb = openpyxl.load_workbook(out)
    assert "Schedule-by-Time" in wb.sheetnames
    assert "Schedule-by-Sport" in wb.sheetnames
    assert "Conflict-Audit" in wb.sheetnames


def test_write_schedule_output_report_tab1_has_data(tmp_path):
    """Schedule-by-Time tab has a title in row 1 and game text in the grid."""
    import openpyxl
    so, si = _make_render_schedule_pair()
    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, so, si)
    ws = openpyxl.load_workbook(out)["Schedule-by-Time"]
    title = ws.cell(row=1, column=1).value
    assert title and "Sports Fest" in title
    # At least one game should appear somewhere in the grid
    all_values = [ws.cell(row=r, column=c).value
                  for r in range(1, ws.max_row + 1)
                  for c in range(1, ws.max_column + 1)]
    assert any("BBM" in str(v) for v in all_values if v)


def test_write_schedule_output_report_tab2_flat_list(tmp_path):
    """Schedule-by-Sport tab has a header row and one data row per assignment."""
    import openpyxl
    so, si = _make_render_schedule_pair()
    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, so, si)
    ws = openpyxl.load_workbook(out)["Schedule-by-Sport"]
    assert ws.cell(row=1, column=1).value == "game_id"
    assert ws.cell(row=2, column=1).value == "BBM-01"    # Pool comes first
    assert ws.cell(row=3, column=1).value == "BBM-Final"


def test_write_schedule_output_report_renders_three_team_bc_cell(tmp_path):
    """Schedule-by-Time should render BC Jeopardy games with all three team labels."""
    import openpyxl

    schedule_input = {
        "games": [
            {
                "game_id": "BC-P1-RR-1",
                "event": SPORT_TYPE["BIBLE_CHALLENGE"],
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BC::RPC",
                "team_b_id": "BC::ANH",
                "team_c_id": "BC::OCB",
                "team_a_label": "RPC",
                "team_b_label": "ANH",
                "team_c_label": "OCB",
                "duration_minutes": 60,
                "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                "earliest_slot": None,
                "latest_slot": None,
            }
        ],
        "resources": [
            {
                "resource_id": "BC-Sat-1-1",
                "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                "label": "BC-1",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "10:00",
                "slot_minutes": 60,
                "exclusive_group": "",
            }
        ],
        "playoff_slots": [],
        "precedence": [],
    }
    schedule_output = {
        "solved_at": "2026-05-01T10:00:00",
        "status": "OPTIMAL",
        "solver_wall_seconds": 0.1,
        "assignments": [
            {"game_id": "BC-P1-RR-1", "resource_id": "BC-Sat-1-1", "slot": "Sat-1-08:00"}
        ],
        "unscheduled": [],
        "conflict_audit_summary": {},
        "conflict_audit": [],
    }

    out = tmp_path / "bc_sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, schedule_output, schedule_input)
    ws = openpyxl.load_workbook(out)["Schedule-by-Time"]
    all_values = [
        ws.cell(row=r, column=c).value
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
    ]
    assert any("RPC / ANH / OCB" in str(value) for value in all_values if value)


def test_write_schedule_output_report_tab3_conflict_audit(tmp_path):
    """Conflict-Audit tab should render audit rows and summary content."""
    import openpyxl
    so, si = _make_schedule_pair()
    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, so, si)
    ws = openpyxl.load_workbook(out)["Conflict-Audit"]
    assert ws.cell(row=1, column=1).value == "Cross-Sport Conflict Audit"
    assert "Separated" in str(ws.cell(row=3, column=2).value)
    assert ws.cell(row=6, column=1).value == "team_a_label"
    assert ws.cell(row=7, column=1).value == "OCB"
    assert ws.cell(row=7, column=8).value == "SeparatedInSchedule"


def test_write_schedule_output_report_tab3_planning_only_conflict_audit(tmp_path):
    """Conflict-Audit should render planning-only rows distinctly."""
    import openpyxl

    so, si = _make_schedule_pair()
    so["conflict_audit_summary"]["planning_only_edges"] = 1
    so["conflict_audit_summary"]["separated_edges"] = 0
    so["conflict_audit"][0]["event_b"] = SPORT_TYPE["BIBLE_CHALLENGE"]
    so["conflict_audit"][0]["status"] = "PlanningOnly"
    so["conflict_audit"][0]["scheduled_team_b_games"] = 0

    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, so, si)
    ws = openpyxl.load_workbook(out)["Conflict-Audit"]
    assert "Planning-only" in str(ws.cell(row=3, column=2).value)
    assert ws.cell(row=7, column=8).value == "PlanningOnly"


def test_write_schedule_output_report_unscheduled_section(tmp_path):
    """Unscheduled section appears in Schedule-by-Sport when games are unscheduled."""
    import openpyxl
    so, si = _make_render_schedule_pair()
    so["unscheduled"] = ["BBM-QF-1"]
    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, so, si)
    ws = openpyxl.load_workbook(out)["Schedule-by-Sport"]
    all_values = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
    assert any("Unscheduled" in str(v) for v in all_values if v)
    assert any("BBM-QF-1" in str(v) for v in all_values if v)


def test_write_schedule_output_report_groups_mixed_pod_windows(tmp_path):
    """Pod resources with different slot windows render as separate time-grid sections."""
    import openpyxl

    schedule_input = {
        "games": [
            {
                "game_id": "PCK-01", "event": "Pickleball",
                "stage": "R1", "pool_id": "", "round": 1,
                "team_a_id": None, "team_b_id": None,
                "duration_minutes": 20, "resource_type": "Pickleball Court",
                "earliest_slot": None, "latest_slot": None,
            },
            {
                "game_id": "TT-01", "event": "Table Tennis",
                "stage": "R1", "pool_id": "", "round": 1,
                "team_a_id": None, "team_b_id": None,
                "duration_minutes": 30, "resource_type": "Table Tennis Table",
                "earliest_slot": None, "latest_slot": None,
            },
        ],
        "resources": [
            {
                "resource_id": "PCK-1", "resource_type": "Pickleball Court",
                "label": "Court-1", "day": "Day-1",
                "open_time": "13:00", "close_time": "13:40", "slot_minutes": 20,
            },
            {
                "resource_id": "TT-1", "resource_type": "Table Tennis Table",
                "label": "Table-1", "day": "Day-1",
                "open_time": "18:00", "close_time": "19:00", "slot_minutes": 30,
            },
        ],
        "precedence": [],
    }
    schedule_output = {
        "solved_at": "2026-05-15T07:07:48",
        "status": "PARTIAL",
        "solver_wall_seconds": 0.2,
        "assignments": [
            {"game_id": "PCK-01", "resource_id": "PCK-1", "slot": "Day-1-13:00"},
            {"game_id": "TT-01", "resource_id": "TT-1", "slot": "Day-1-18:00"},
        ],
        "unscheduled": [],
        "pool_results": [],
    }
    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, schedule_output, schedule_input)
    ws = openpyxl.load_workbook(out)["Schedule-by-Time"]

    all_values = [
        ws.cell(row=r, column=c).value
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
    ]
    string_values = [str(v) for v in all_values if v is not None]

    assert any("Pickleball Court" in v for v in string_values)
    assert any("Table Tennis Table" in v for v in string_values)
    assert "13:00" in string_values
    assert "18:00" in string_values
    assert any("PCK-01" in v for v in string_values)
    assert any("TT-01" in v for v in string_values)


def test_write_schedule_output_report_merges_gym_core_day_sections(tmp_path):
    """Gym Core resources for one day/resource_type render as one continuous section."""
    import openpyxl

    schedule_input = {
        "games": [
            {
                "game_id": "VBM-01", "event": "Volleyball - Men Team",
                "stage": "Pool", "pool_id": "P1", "round": 1,
                "team_a_id": "VBM::RPC", "team_b_id": "VBM::SDC",
                "duration_minutes": 60, "resource_type": "Volleyball Court",
                "earliest_slot": None, "latest_slot": None,
            },
            {
                "game_id": "VBM-02", "event": "Volleyball - Men Team",
                "stage": "Pool", "pool_id": "P1", "round": 2,
                "team_a_id": "VBM::FVC", "team_b_id": "VBM::ORN",
                "duration_minutes": 60, "resource_type": "Volleyball Court",
                "earliest_slot": None, "latest_slot": None,
            },
            {
                "game_id": "VBW-01", "event": "Volleyball - Women Team",
                "stage": "Pool", "pool_id": "P1", "round": 1,
                "team_a_id": "VBW::RPC", "team_b_id": "VBW::PCC",
                "duration_minutes": 60, "resource_type": "Volleyball Court",
                "earliest_slot": None, "latest_slot": None,
            },
        ],
        "resources": [
            {
                "resource_id": "GYM-Day-1-1", "resource_type": "Volleyball Court",
                "label": "Court-1", "day": "Day-1", "open_time": "08:00",
                "close_time": "18:00", "slot_minutes": 60,
                "solver_pool": ScheduleWorkbookBuilder._GYM_CORE_SOLVER_POOL,
                "exclusive_group": "HS Big Gym",
            },
            {
                "resource_id": "GYM-Day-1-4", "resource_type": "Volleyball Court",
                "label": "Court-1", "day": "Day-1", "open_time": "12:00",
                "close_time": "21:00", "slot_minutes": 60,
                "solver_pool": ScheduleWorkbookBuilder._GYM_CORE_SOLVER_POOL,
                "exclusive_group": "HS Big Gym",
            },
            {
                "resource_id": "GYM-Day-1-6", "resource_type": "Volleyball Court",
                "label": "Court-3", "day": "Day-1", "open_time": "12:00",
                "close_time": "21:00", "slot_minutes": 60,
                "solver_pool": ScheduleWorkbookBuilder._GYM_CORE_SOLVER_POOL,
                "exclusive_group": "HS Big Gym",
            },
            {
                "resource_id": "VB-Day-1-1", "resource_type": "Volleyball Court",
                "label": "Court-2", "day": "Day-1", "open_time": "10:00",
                "close_time": "13:00", "slot_minutes": 60,
                "solver_pool": ScheduleWorkbookBuilder._GYM_CORE_SOLVER_POOL,
                "venue_name": "Orange Gym",
                "exclusive_group": "",
            },
        ],
        "precedence": [],
    }
    schedule_output = {
        "solved_at": "2026-05-20T14:07:19",
        "status": "OPTIMAL",
        "solver_wall_seconds": 0.1,
        "assignments": [
            {"game_id": "VBM-01", "resource_id": "GYM-Day-1-1", "slot": "Day-1-08:00"},
            {"game_id": "VBW-01", "resource_id": "VB-Day-1-1", "slot": "Day-1-10:00"},
            {"game_id": "VBM-02", "resource_id": "GYM-Day-1-4", "slot": "Day-1-14:00"},
        ],
        "unscheduled": [],
        "pool_results": [],
    }
    out = tmp_path / "sched.xlsx"
    ScheduleWorkbookBuilder._write_schedule_output_report(out, schedule_output, schedule_input)
    ws = openpyxl.load_workbook(out)["Schedule-by-Time"]

    all_values = [
        ws.cell(row=r, column=c).value
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
    ]
    string_values = [str(v) for v in all_values if v is not None]

    volleyball_sections = [v for v in string_values if "Volleyball Court" in v]
    assert len(volleyball_sections) == 1
    assert "08:00-21:00" in volleyball_sections[0]
    assert "08:00" in string_values
    assert "20:00" in string_values
    assert any("HS Big Gym Court-1 [08:00-18:00]" in v for v in string_values)
    assert any("HS Big Gym Court-1 [12:00-21:00]" in v for v in string_values)
    assert any("HS Big Gym Court-3" in v for v in string_values)
    assert any("Orange Gym Court-2" in v for v in string_values)
    assert any("VBM-01" in v for v in string_values)
    assert any("VBM-02" in v for v in string_values)
    assert any("VBW-01" in v for v in string_values)


# ---------------------------------------------------------------------------
# Bible Challenge Venue-Estimator tests (Issue #118)
# ---------------------------------------------------------------------------

def _bc_roster(church_codes, n_per_church=3):
    """Build minimal BC roster rows — enough to meet min_team_size=3."""
    rows = []
    for code in church_codes:
        for _ in range(n_per_church):
            rows.append({"Church Team": code, "sport_type": SPORT_TYPE["BIBLE_CHALLENGE"], "sport_gender": "Mixed"})
    return rows


def test_bc_venue_estimator_rr_game_count_12_teams():
    """12 BC teams × 2 games/team ÷ 3 teams/game = 8 RR games."""
    from config import (
        COURT_ESTIMATE_BC_TEAMS_PER_GAME,
        COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM,
        COURT_ESTIMATE_BC_PLAYOFF_GAMES,
        COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF,
        COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
    )
    builder = ScheduleWorkbookBuilder()
    churches = [f"C{i:02d}" for i in range(1, 13)]  # 12 teams
    rows = _bc_roster(churches)
    capacity_rows = builder._build_venue_capacity_rows(rows)
    bc_row = next(r for r in capacity_rows if r["Event"] == SPORT_TYPE["BIBLE_CHALLENGE"])

    assert bc_row["Estimating Teams/Entries"] == 12
    assert bc_row["Pool Slots"] == 8                        # ceil(12*2/3)
    assert bc_row["Actual Pool Games/Team"] == 2
    assert bc_row["Playoff Teams"] == COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF
    assert bc_row["Playoff Slots"] == COURT_ESTIMATE_BC_PLAYOFF_GAMES  # 4
    assert bc_row["Total Court Slots"] == 12                # 8 RR + 4 playoff
    assert bc_row["Minutes Per Game"] == COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE  # 60
    assert bc_row["Estimated Court Hours"] == 12.0          # 12 games × 60 min / 60
    assert bc_row["Third Place?"] == "No"
    assert "Sequential" in bc_row["Pool Composition"]
    assert "1 classroom" in bc_row["Pool Composition"]


def test_bc_venue_estimator_no_playoff_when_fewer_than_9_teams():
    """8 BC teams → no playoff (need ≥ 9). Pool Slots = ceil(8*2/3) = 6."""
    from config import COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF
    builder = ScheduleWorkbookBuilder()
    churches = [f"C{i:02d}" for i in range(1, 9)]  # 8 teams
    rows = _bc_roster(churches)
    capacity_rows = builder._build_venue_capacity_rows(rows)
    bc_row = next(r for r in capacity_rows if r["Event"] == SPORT_TYPE["BIBLE_CHALLENGE"])

    assert bc_row["Estimating Teams/Entries"] == 8
    assert bc_row["Pool Slots"] == 6                        # ceil(8*2/3) = ceil(5.33) = 6
    assert bc_row["Actual Pool Games/Team"] == 2
    assert bc_row["Playoff Teams"] == 0
    assert bc_row["Playoff Slots"] == 0
    assert bc_row["Total Court Slots"] == 6
    assert f"< {COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF}" in bc_row["Pool Composition"]


def test_bc_venue_estimator_zero_teams():
    """0 BC teams → all zeros, no crash."""
    builder = ScheduleWorkbookBuilder()
    capacity_rows = builder._build_venue_capacity_rows([])
    bc_row = next(r for r in capacity_rows if r["Event"] == SPORT_TYPE["BIBLE_CHALLENGE"])

    assert bc_row["Estimating Teams/Entries"] == 0
    assert bc_row["Actual Pool Games/Team"] == 0
    assert bc_row["Pool Slots"] == 0
    assert bc_row["Playoff Slots"] == 0
    assert bc_row["Total Court Slots"] == 0
    assert bc_row["Estimated Court Hours"] == 0.0


def test_bc_venue_estimator_not_in_court_hours_model():
    """BC must NOT appear via the standard concurrent court-hours COURT_ESTIMATE_EVENTS path."""
    from config import COURT_ESTIMATE_EVENTS
    assert SPORT_TYPE["BIBLE_CHALLENGE"] not in COURT_ESTIMATE_EVENTS


def test_bc_venue_estimator_waits_for_first_three_team_game():
    """With only 2 BC teams, the sequential queue should remain in waiting mode."""
    builder = ScheduleWorkbookBuilder()
    rows = _bc_roster(["RPC", "OCB"])
    capacity_rows = builder._build_venue_capacity_rows(rows)
    bc_row = next(r for r in capacity_rows if r["Event"] == SPORT_TYPE["BIBLE_CHALLENGE"])

    assert bc_row["Estimating Teams/Entries"] == 2
    assert bc_row["Actual Pool Games/Team"] == 0
    assert bc_row["Pool Slots"] == 0
    assert bc_row["Total Court Slots"] == 0
    assert "waiting for at least 3 teams" in bc_row["Pool Composition"]


def test_bc_minutes_per_game_is_60():
    """Confirm COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE was updated to 60."""
    from config import COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE
    assert COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE == 60


# ---------------------------------------------------------------------------
# Bible Challenge Pool-Assignment & conflict-edge tests (Issue #118)
# ---------------------------------------------------------------------------

def test_bc_appears_in_pool_assignment_base_rows():
    """BC teams meeting min_team_size=3 should produce Pool-Assignment rows."""
    builder = ScheduleWorkbookBuilder()
    churches = ["RPC", "OCB", "ANH"]
    rows = _bc_roster(churches, n_per_church=3)
    base_rows = builder._build_pool_assignment_base_rows(rows)
    bc_rows = [r for r in base_rows if r["Event"] == SPORT_TYPE["BIBLE_CHALLENGE"]]
    assert {r["Team ID"] for r in bc_rows} == set(churches)
    for r in bc_rows:
        assert r["Min Team Size"] == 3
        assert r["Roster Count"] == 3


def test_bc_pool_assignment_below_min_team_size_excluded():
    """BC team with fewer than 3 roster members is excluded from Pool-Assignment."""
    builder = ScheduleWorkbookBuilder()
    rows = (
        _bc_roster(["RPC"], n_per_church=3)
        + _bc_roster(["OCB"], n_per_church=2)  # below min
    )
    base_rows = builder._build_pool_assignment_base_rows(rows)
    bc_rows = [r for r in base_rows if r["Event"] == SPORT_TYPE["BIBLE_CHALLENGE"]]
    assert {r["Team ID"] for r in bc_rows} == {"RPC"}


def test_bc_cross_sport_conflict_edge_with_basketball(tmp_path):
    """BC and BB teams sharing an athlete must produce a team_conflicts edge."""
    builder = ScheduleWorkbookBuilder()
    shared_id = 42
    # Need ≥ 2 BB teams and ≥ 2 BC teams so the pool-assignment logic
    # doesn't fall into the "WaitingForMoreTeams" branch.
    bb_rpc = [
        {
            "Church Team": "RPC",
            "sport_type": SPORT_TYPE["BASKETBALL"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],
        }
        for pid in range(40, 45)  # includes shared_id=42
    ]
    bb_anh = [
        {
            "Church Team": "ANH",
            "sport_type": SPORT_TYPE["BASKETBALL"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],
        }
        for pid in range(50, 55)
    ]
    bc_ocb = [
        {
            "Church Team": "OCB",
            "sport_type": SPORT_TYPE["BIBLE_CHALLENGE"],
            "sport_gender": "Mixed",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],  # primary is BB
        }
        for pid in (shared_id, 90, 91)  # #42 is shared with RPC's BB team
    ]
    bc_tlc = [
        {
            "Church Team": "TLC",
            "sport_type": SPORT_TYPE["BIBLE_CHALLENGE"],
            "sport_gender": "Mixed",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["BIBLE_CHALLENGE"],
        }
        for pid in (95, 96, 97)
    ]
    roster_rows = bb_rpc + bb_anh + bc_ocb + bc_tlc

    si = builder._build_schedule_input(roster_rows, [], tmp_path / "no_venue.xlsx")

    bc_bb_edges = [
        edge for edge in si["team_conflicts"]
        if {edge.get("event_a"), edge.get("event_b")}
           == {SPORT_TYPE["BASKETBALL"], SPORT_TYPE["BIBLE_CHALLENGE"]}
    ]
    assert len(bc_bb_edges) == 1
    edge = bc_bb_edges[0]
    assert edge["shared_count"] == 1
    assert edge["primary_overlap_count"] == 1  # athlete's primary is BB
    assert edge["secondary_only_count"] == 0


def test_bc_pool_assignment_creates_bc_station_games(tmp_path):
    """BC pool-assignment rows should create sequential BC Station queue games."""
    builder = ScheduleWorkbookBuilder()
    bc_rows = _bc_roster(["RPC", "OCB", "ANH"], n_per_church=3)

    si = builder._build_schedule_input(bc_rows, [], tmp_path / "no_venue.xlsx")
    bc_games = [g for g in si.get("games", []) if g.get("event") == SPORT_TYPE["BIBLE_CHALLENGE"]]
    assert len(bc_games) == 2
    assert all(g["resource_type"] == TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE for g in bc_games)
    assert all(g["team_c_id"] for g in bc_games)


def test_bc_pool_of_four_assigns_extra_round_to_t4():
    """A 4-team BC pool should give the third appearance to T4, not the top slots."""
    pool_rows = [
        {"Pool Slot": "T1", "Team ID": "A"},
        {"Pool Slot": "T2", "Team ID": "B"},
        {"Pool Slot": "T3", "Team ID": "C"},
        {"Pool Slot": "T4", "Team ID": "D"},
    ]
    triplets = ScheduleWorkbookBuilder._bc_pool_triplets(pool_rows)
    appearances = {}
    for trio in triplets:
        for row in trio:
            team_id = row["Team ID"]
            appearances[team_id] = appearances.get(team_id, 0) + 1

    assert len(triplets) == 3
    assert appearances == {"A": 2, "B": 2, "C": 2, "D": 3}


def test_bc_schedule_input_adds_playoff_precedence(tmp_path):
    """Nine BC teams should keep all BC prelims ahead of semis, then semis ahead of the final."""
    builder = ScheduleWorkbookBuilder()
    bc_rows = _bc_roster(
        ["RPC", "OCB", "ANH", "GLA", "TLC", "FVC", "MWC", "NSD", "WCC"],
        n_per_church=3,
    )

    si = builder._build_schedule_input(bc_rows, [], tmp_path / "no_venue.xlsx")
    bc_games = [g for g in si["games"] if g.get("event") == SPORT_TYPE["BIBLE_CHALLENGE"]]
    pool_game_ids = {
        str(g["game_id"])
        for g in bc_games
        if g.get("stage") == "Pool"
    }
    semi_ids = {
        str(g["game_id"])
        for g in bc_games
        if g.get("stage") == "Semi"
    }
    final_ids = {
        str(g["game_id"])
        for g in bc_games
        if g.get("stage") == "Final"
    }
    assert semi_ids == {"BC-Semi-1", "BC-Semi-2", "BC-Semi-3"}
    assert final_ids == {"BC-Final"}

    precedence_pairs = {
        (str(rule["before_game_id"]), str(rule["after_game_id"]))
        for rule in si["precedence"]
    }
    expected_pairs = {
        (pool_game_id, semi_id)
        for pool_game_id in pool_game_ids
        for semi_id in semi_ids
    } | {
        (semi_id, "BC-Final")
        for semi_id in semi_ids
    }
    assert precedence_pairs == expected_pairs
    assert all(int(rule.get("min_gap_slots") or 0) == 1 for rule in si["precedence"])


def test_bc_event_in_pool_assignment_defs():
    """BC must be the 4th entry in _POOL_ASSIGNMENT_EVENT_DEFS with prefix 'BC'."""
    defs = ScheduleWorkbookBuilder._POOL_ASSIGNMENT_EVENT_DEFS
    assert (SPORT_TYPE["BIBLE_CHALLENGE"], "BC") in defs
    # Sort index makes BC the last (4th) event
    idx = ScheduleWorkbookBuilder._event_sort_index(SPORT_TYPE["BIBLE_CHALLENGE"])
    assert idx == 3


# ---------------------------------------------------------------------------
# Soccer (optional / config-driven) tests — Issue #118
# ---------------------------------------------------------------------------

def _soccer_roster(church_codes, n_per_church=4):
    """Build minimal Soccer roster rows — enough to meet min_team_size=4."""
    rows = []
    for code in church_codes:
        for _ in range(n_per_church):
            rows.append({"Church Team": code, "sport_type": SPORT_TYPE["SOCCER"], "sport_gender": "Mixed"})
    return rows


def test_soccer_in_pool_assignment_defs_when_enabled():
    """When SOCCER_ENABLED is True (default), Soccer is included in pool defs as 5th entry."""
    from config import SOCCER_ENABLED
    assert SOCCER_ENABLED is True
    defs = ScheduleWorkbookBuilder._POOL_ASSIGNMENT_EVENT_DEFS
    assert (SPORT_TYPE["SOCCER"], "SOC") in defs
    idx = ScheduleWorkbookBuilder._event_sort_index(SPORT_TYPE["SOCCER"])
    assert idx == 4  # after BB(0), VBM(1), VBW(2), BC(3)


def test_soccer_in_court_estimate_events_when_enabled():
    """Soccer should appear in the standard court-hours estimator when enabled."""
    from config import COURT_ESTIMATE_EVENTS, SOCCER_ENABLED
    assert SOCCER_ENABLED is True
    assert SPORT_TYPE["SOCCER"] in COURT_ESTIMATE_EVENTS


def test_soccer_appears_in_pool_assignment_base_rows():
    """Soccer teams meeting min_team_size=4 should produce Pool-Assignment rows."""
    builder = ScheduleWorkbookBuilder()
    churches = ["RPC", "OCB", "ANH"]
    rows = _soccer_roster(churches, n_per_church=4)
    base_rows = builder._build_pool_assignment_base_rows(rows)
    soccer_rows = [r for r in base_rows if r["Event"] == SPORT_TYPE["SOCCER"]]
    assert {r["Team ID"] for r in soccer_rows} == set(churches)
    for r in soccer_rows:
        assert r["Min Team Size"] == 4


def test_soccer_pool_assignment_below_min_team_size_excluded():
    """Soccer team with fewer than 4 roster members is excluded from Pool-Assignment."""
    builder = ScheduleWorkbookBuilder()
    rows = (
        _soccer_roster(["RPC"], n_per_church=4)
        + _soccer_roster(["OCB"], n_per_church=3)  # below min
    )
    base_rows = builder._build_pool_assignment_base_rows(rows)
    soccer_rows = [r for r in base_rows if r["Event"] == SPORT_TYPE["SOCCER"]]
    assert {r["Team ID"] for r in soccer_rows} == {"RPC"}


def test_soccer_cross_sport_conflict_edge_with_basketball(tmp_path):
    """Soccer and BB teams sharing an athlete must produce a team_conflicts edge."""
    builder = ScheduleWorkbookBuilder()
    shared_id = 42
    bb_rpc = [
        {
            "Church Team": "RPC",
            "sport_type": SPORT_TYPE["BASKETBALL"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],
        }
        for pid in range(40, 45)  # includes shared_id=42
    ]
    bb_anh = [
        {
            "Church Team": "ANH",
            "sport_type": SPORT_TYPE["BASKETBALL"],
            "sport_gender": "Men",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["BASKETBALL"],
        }
        for pid in range(50, 55)
    ]
    soccer_ocb = [
        {
            "Church Team": "OCB",
            "sport_type": SPORT_TYPE["SOCCER"],
            "sport_gender": "Mixed",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["SOCCER"],  # primary is Soccer
        }
        for pid in (shared_id, 90, 91, 92)
    ]
    soccer_tlc = [
        {
            "Church Team": "TLC",
            "sport_type": SPORT_TYPE["SOCCER"],
            "sport_gender": "Mixed",
            "sport_format": "Team",
            "Participant ID (WP)": pid,
            "participant_primary_sport": SPORT_TYPE["SOCCER"],
        }
        for pid in (95, 96, 97, 98)
    ]
    roster_rows = bb_rpc + bb_anh + soccer_ocb + soccer_tlc

    si = builder._build_schedule_input(roster_rows, [], tmp_path / "no_venue.xlsx")

    bb_soccer_edges = [
        edge for edge in si["team_conflicts"]
        if {edge.get("event_a"), edge.get("event_b")}
           == {SPORT_TYPE["BASKETBALL"], SPORT_TYPE["SOCCER"]}
    ]
    assert len(bb_soccer_edges) == 1
    edge = bb_soccer_edges[0]
    assert edge["shared_count"] == 1
    # Athlete's primary is Soccer, which is one of the events on this edge.
    assert edge["primary_overlap_count"] == 1


def test_soccer_schedule_input_creates_soccer_field_games(tmp_path):
    """Soccer pool-assignment rows should create real Soccer Field games, not Gym Core games."""
    builder = ScheduleWorkbookBuilder()
    rows = _soccer_roster(["RPC", "OCB", "ANH"], n_per_church=4)
    si = builder._build_schedule_input(rows, [], tmp_path / "no_venue.xlsx")
    soccer_games = [g for g in si.get("games", []) if g.get("event") == SPORT_TYPE["SOCCER"]]
    assert len(soccer_games) == 3
    assert all(g["resource_type"] == TEAM_RESOURCE_TYPE_SOCCER for g in soccer_games)
    assert all(g["stage"] == "Pool" for g in soccer_games)
    assert all(g.get("team_c_id") in (None, "") for g in soccer_games)


def test_soccer_schedule_input_adds_playoff_precedence(tmp_path):
    """Six Soccer teams should add semis/final/3rd plus pool-before-semi precedence."""
    builder = ScheduleWorkbookBuilder()
    rows = _soccer_roster(["RPC", "OCB", "ANH", "GLA", "TLC", "FVC"], n_per_church=4)

    si = builder._build_schedule_input(rows, [], tmp_path / "no_venue.xlsx")
    soccer_games = [g for g in si["games"] if g.get("event") == SPORT_TYPE["SOCCER"]]
    pool_game_ids = {
        str(g["game_id"])
        for g in soccer_games
        if g.get("stage") == "Pool"
    }
    semi_ids = {
        str(g["game_id"])
        for g in soccer_games
        if g.get("stage") == "Semi"
    }
    final_ids = {
        str(g["game_id"])
        for g in soccer_games
        if g.get("stage") == "Final"
    }
    third_ids = {
        str(g["game_id"])
        for g in soccer_games
        if g.get("stage") == "3rd"
    }

    assert len(pool_game_ids) == 6
    assert semi_ids == {"SOC-Semi-1", "SOC-Semi-2"}
    assert final_ids == {"SOC-Final"}
    assert third_ids == {"SOC-3rd"}

    precedence_pairs = {
        (str(rule["before_game_id"]), str(rule["after_game_id"]))
        for rule in si["precedence"]
        if str(rule.get("before_game_id") or "").startswith("SOC-")
           or str(rule.get("after_game_id") or "").startswith("SOC-")
    }
    expected_pairs = {
        (pool_game_id, semi_id)
        for pool_game_id in pool_game_ids
        for semi_id in semi_ids
    } | {
        (semi_id, "SOC-Final")
        for semi_id in semi_ids
    } | {
        (semi_id, "SOC-3rd")
        for semi_id in semi_ids
    }
    assert precedence_pairs == expected_pairs


def test_soccer_disabled_removes_from_pool_assignment(monkeypatch):
    """When SOCCER_ENABLED=False, Soccer is excluded from Pool-Assignment outputs."""
    # Simulate disabled mode by patching the class attribute to the without-Soccer list.
    defs_without_soccer = [
        (event, prefix)
        for event, prefix in ScheduleWorkbookBuilder._POOL_ASSIGNMENT_EVENT_DEFS
        if event != SPORT_TYPE["SOCCER"]
    ]
    monkeypatch.setattr(
        ScheduleWorkbookBuilder,
        "_POOL_ASSIGNMENT_EVENT_DEFS",
        defs_without_soccer,
    )

    builder = ScheduleWorkbookBuilder()
    rows = _soccer_roster(["RPC", "OCB"], n_per_church=4)
    base_rows = builder._build_pool_assignment_base_rows(rows)
    soccer_rows = [r for r in base_rows if r["Event"] == SPORT_TYPE["SOCCER"]]
    assert soccer_rows == []
