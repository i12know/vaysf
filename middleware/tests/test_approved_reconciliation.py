"""Tests for reconcile-approved-schedules (Issue #216)."""
from datetime import datetime

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

from config import SPORT_TYPE
from schedule_styles import SPORT_STYLES
from scheduling import approved_reconciliation as rec
from scheduling.venue_loader import _load_venue_input_rows

VENUE_HEADERS = [
    "Pod Name", "Venue Name", "Resource Type", "Quantity", "Day", "Date", "Start Time",
    "Last Start Time", "Slot Minutes", "Available Slots", "Exclusive Venue Group",
    "Contact", "Cost", "Notes",
]


def _solid(color):
    return PatternFill(fill_type="solid", fgColor=color)


def _game(ws, row, col, team_a, team_b, event):
    for offset, value in enumerate((team_a, "v", team_b)):
        cell = ws.cell(row=row, column=col + offset, value=value)
        cell.fill = _solid(SPORT_STYLES[event].fill_color)


def _write_main(path, *, extra=None):
    """Sat 7/18: Main Gym BB1/BB2 + Practice Gym VB1, four hourly rows."""
    wb = Workbook()
    ws = wb.active
    ws.title = "2026_Draft"
    ws["A1"] = "SAT 7/18"
    headers = [("B1:D1", "Main Gym BB1"), ("E1:G1", "Main Gym BB2"), ("H1:J1", "Practice Gym VB1")]
    for rng, name in headers:
        ws.merge_cells(rng)
        ws[rng.split(":")[0]] = name
    for row, label in zip(range(2, 6), ("12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM")):
        ws.cell(row=row, column=1, value=label)
    # 12:00 opening ceremony across every court (one merged range)
    ws.merge_cells("B2:J2")
    ws["B2"] = "OPENING CEREMONY"
    _game(ws, 3, 2, "ANH", "GAC", SPORT_TYPE["BASKETBALL"])
    _game(ws, 3, 8, "RPC", "ORN", SPORT_TYPE["VOLLEYBALL_MEN"])
    ws.merge_cells("E3:G3")
    ws["E3"] = "SET UP - TAPE LINES"
    # 14:00-16:00 BB2 CLOSED, vertically merged over two rows
    ws.merge_cells("E4:G5")
    ws["E4"] = "CLOSED"
    _game(ws, 4, 2, "SBC", "FVC", SPORT_TYPE["BASKETBALL"])
    ws["B5"] = "BB QF"
    ws["H5"] = "DINNER"
    if extra:
        extra(ws)
    wb.save(path)


def _write_badminton(path, lanes=3, matches=39):
    wb = Workbook()
    ws = wb.active
    ws.append(["2026 VAY Badminton Preliminary Schedule"])
    ws.append(["Time", "#", "Court 1"])
    ws.append(["5:00 PM", None, "Opening and Check-Ins"])
    number = 0
    minutes = 17 * 60 + 20
    while number < matches:
        row = [f"{minutes // 60 - 12}:{minutes % 60:02d} PM"]
        for _lane in range(lanes):
            if number >= matches:
                break
            number += 1
            row += [number, f"T{number}A", "v", f"T{number}B"]
        ws.append(row)
        minutes += 20
    wb.save(path)


def _write_soccer(path):
    wb = Workbook()
    ws = wb.active
    for _ in range(10):
        ws.append([])
    ws.append(["SAT 7/18", "1:00 PM", "G1", "ANH", "v", "GAC", "RPC"])
    ws.append(["SAT 7/18", "2:00 PM", "G7", "Group A #2", "v", "G8 Winner", ""])
    wb.save(path)


def _write_table_tennis(path, *, include_sbc=True, scheduled=("FVC", "ORN")):
    wb = Workbook()
    ws = wb.active
    ws.append(["", "VAY SPORTS FEST 2026 - TABLE TENNIS SCHEDULE"])
    ws.append(["Fri 7/24", "Table 1", "Table 2", "Table 3", "Table 4"])
    ws.append(["17:00", "Nhan Micah (ORN) - Phan Dora (WSD)", f"(U35) {scheduled[0]} - (U35) {scheduled[1]}"])
    ws.append(["17:15", "Le An (GAC) - Tran Bo (RPC)"])
    ws.append(["17:30", "SF 1", "FINAL"])
    ws.append([])
    ws.append(["TEAM", "ATHLETES"])
    ws.append(["(U35) FVC", "A & B"])
    ws.append(["(U35) ORN", "C & D"])
    if include_sbc:
        ws.append(["(U35) SBC", "E & F"])
    wb.save(path)


def _write_venue(path, *, badminton_qty=4, extra_rows=(), extra_pins=()):
    wb = Workbook()
    ws = wb.active
    ws.title = "Venue-Input"
    ws.append(VENUE_HEADERS)
    sat = datetime(2026, 7, 18)
    fri = datetime(2026, 7, 24)
    rows = [
        ["Main Gym", "EHS Main Gym", "Basketball Court", 2, "Sat-1", sat, 12, 15, 60, None, "EHS Main Gym", "", "", ""],
        ["Main Gym", "EHS Main Gym", "Volleyball Court", 3, "Sat-1", sat, 12, 15, 60, None, "EHS Main Gym", "", "", ""],
        ["Practice Gym", "EHS Practice Gym", "Volleyball Court", 3, "Sat-1", sat, 12, 15, 60, None, "EHS Practice Gym", "", "", ""],
        ["Soccer", "EHS Field", "Soccer Field", 1, "Sat-1", sat, 13, 17, 60, None, None, "", "", ""],
        ["Orange Badminton", "Orange Church", "Badminton Court", badminton_qty, "Fri-1", fri, 17, 21, 60, None, None, "", "", ""],
        ["Orange Tables", "Orange Church", "Table Tennis Table", 6, "Fri-1", fri, 17, 21, 60, None, None, "", "", ""],
        *extra_rows,
        ["Available Slots formula note", None, None, None, None, None, None, None, None, None, None, None, None, None],
    ]
    for row in rows:
        ws.append(row)
    gm = wb.create_sheet("Gym-Modes")
    gm.append(["Gym Name", "Basketball Courts", "Volleyball Courts"])
    gm.append(["EHS Main Gym", 2, 3])
    gm.append(["EHS Practice Gym", 0, 3])
    ps = wb.create_sheet("Playoff-Slots")
    ps.append(["game_id", "event", "stage", "gym_name", "date", "start_time", "slot_minutes"])
    ps.append(["BBM-Final", SPORT_TYPE["BASKETBALL"], "Final", "EHS Main Gym", sat, "15:00", None])
    for pin in extra_pins:
        ps.append(list(pin))
    wb.save(path)


@pytest.fixture
def sources(tmp_path):
    paths = {
        "main_schedule_path": tmp_path / "main.xlsx",
        "badminton_path": tmp_path / "badminton.xlsx",
        "soccer_path": tmp_path / "soccer.xlsx",
        "table_tennis_path": tmp_path / "tt.xlsx",
        "venue_input_path": tmp_path / "venue_input.xlsx",
    }
    _write_main(paths["main_schedule_path"])
    _write_badminton(paths["badminton_path"])
    _write_soccer(paths["soccer_path"])
    _write_table_tennis(paths["table_tennis_path"], include_sbc=False)
    _write_venue(paths["venue_input_path"])
    return paths


def _rows_for(payload, booked_row_id):
    return [r for r in payload["proposed_venue_rows"] if r[rec.BOOKED_ROW_ID_COLUMN] == booked_row_id]


def _windows(rows):
    return [(r["Start Time"], r["Last Start Time"], r["Quantity"], r["Slot Minutes"]) for r in rows]


# --- classification ---------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("CLOSED", rec.CLOSED),
    ("SET UP - AUDIO / VISUAL", rec.SETUP),
    ("SET UP - TAPE LINES", rec.SETUP),
    ("DINNER", rec.MEAL_OR_BREAK),
    ("LUNCH / COMMUNITY GAMES", rec.MEAL_OR_BREAK),
    ("OPENING CEREMONY", rec.CEREMONY_OR_WORSHIP),
    ("CLOSING CEREMONY", rec.CEREMONY_OR_WORSHIP),
    ("SUNDAY WORSHIP SERVICE", rec.CEREMONY_OR_WORSHIP),
    ("TRACK & FIELD / TUG OF WAR", rec.COMMUNITY_EVENT),
    ("SCRIPTURE MEMORIZATION CONTEST", rec.COMMUNITY_EVENT),
    ("BB QF", rec.SPORT_STAGE_BLOCK),
    ("WVB FINAL", rec.SPORT_STAGE_BLOCK),
    ("BIBLE CHALLENGE FINAL", rec.SPORT_STAGE_BLOCK),
    ("BADMINTON & TABLE TENNIS @ ORANGE CHURCH", rec.REFERENCE),
    ("??", rec.UNRESOLVED),
])
def test_classify_text(text, expected):
    assert rec.classify_text(text)[0] == expected


def test_parse_visual_venue_splits_area_type_and_lane():
    venue = rec.parse_visual_venue("EHS Main Gym BB2")
    assert venue["area"] == "ehs main"  # "gym" is a stop word for matching
    assert venue["resource_type"] == "Basketball Court"
    assert venue["lane"] == 2
    assert rec.parse_visual_venue("BC Library")["resource_type"] == "BC Station"


# --- parsing ----------------------------------------------------------------

def test_main_schedule_parses_games_merged_and_vertical_blocks(sources):
    blocks, _ = rec.parse_main_schedule_blocks(sources["main_schedule_path"])
    by = {(b["venue"], b["start_time"]): b for b in blocks}

    # One merged ceremony range blacks out every venue it covers, with provenance.
    for venue in ("Main Gym BB1", "Main Gym BB2", "Practice Gym VB1"):
        block = by[(venue, "12:00")]
        assert block["classification"] == rec.CEREMONY_OR_WORSHIP
        assert block["source_cell"] == "B2:J2"

    assert by[("Main Gym BB1", "13:00")]["classification"] == rec.SPORT_MATCH
    assert by[("Main Gym BB1", "13:00")]["teams"] == ["ANH", "GAC"]
    assert by[("Practice Gym VB1", "13:00")]["resource_type"] == "Volleyball Court"

    # Vertical CLOSED merge coalesces into one 2-hour block.
    closed = by[("Main Gym BB2", "14:00")]
    assert closed["classification"] == rec.CLOSED
    assert closed["end_time"] == "16:00"

    stage = by[("Main Gym BB1", "15:00")]
    assert stage["classification"] == rec.SPORT_STAGE_BLOCK
    assert stage["resource_type"] == "Basketball Court"


def test_badminton_and_table_tennis_grids(sources):
    _, warnings, grid = rec.parse_badminton_blocks(sources["badminton_path"])
    assert grid["slot_minutes"] == 20
    assert grid["lanes"] == 3
    assert grid["window_start"] == "17:20"
    assert grid["match_count"] == 39
    assert not [w for w in warnings if "expected 39" in w]

    blocks, _, tt_grid, discrepancy = rec.parse_table_tennis_blocks(sources["table_tennis_path"])
    assert tt_grid["slot_minutes"] == 15
    assert tt_grid["lanes"] == 2
    assert {b["classification"] for b in blocks} == {rec.SPORT_MATCH, rec.SPORT_STAGE_BLOCK}
    assert discrepancy["has_discrepancy"] is False


def test_soccer_exact_and_tbd_rows(sources):
    blocks, warnings = rec.parse_soccer_blocks(sources["soccer_path"])
    exact = [b for b in blocks if b["classification"] == rec.SPORT_MATCH]
    tbd = [b for b in blocks if b["classification"] == rec.UNRESOLVED]
    assert [b["game_key"] for b in exact] == ["SOC-G1"]
    assert exact[0]["referee"] == "RPC"
    assert [b["game_key"] for b in tbd] == ["SOC-G7"]
    assert any("expected 6" in w for w in warnings)


# --- reconciliation ---------------------------------------------------------

def test_reconcile_applies_blackouts_mode_locks_and_grids(sources):
    payload = rec.build_reconciliation_payload(**sources)
    assert payload["issues"]["errors"] == []

    # B001 Main Gym BB (2 courts, 12:00-15:00 starts):
    #   12:00 ceremony on both; 13:00 BB2 set-up; 14:00-16:00 BB2 closed.
    assert _windows(_rows_for(payload, "B001")) == [(13, 15, 1, 60)]

    # B002 Main Gym VB mode: BB is in use 13:00-16:00 and 12:00 is ceremony,
    # so the volleyball mode never gets the gym -> row removed entirely.
    assert _rows_for(payload, "B002") == []
    change = next(c for c in payload["row_changes"] if c["booked_row_id"] == "B002")
    assert change["action"] == "removed"

    # B003 Practice Gym VB (3 courts): ceremony 12:00 everywhere, dinner on
    # VB1 at 15:00; the 13:00 MVB game keeps its own mode.
    assert _windows(_rows_for(payload, "B003")) == [(12, 12, 2, 60), (13, 14, 3, 60), (15, 15, 2, 60)]

    # Soccer is validated only, not re-windowed.
    assert _windows(_rows_for(payload, "B004")) == [(13, 17, 1, 60)]

    # Orange racquet rows adopt the approved grids and lane counts.
    badminton = _rows_for(payload, "B005")
    assert _windows(badminton) == [(pytest.approx(17 + 20 / 60), pytest.approx(21 + 20 / 60), 3, 20)]
    assert badminton[0]["Available Slots"] == 3 * 13
    assert _windows(_rows_for(payload, "B006")) == [(17, 17.5, 2, 15)]

    summary = payload["summary"]
    assert summary["by_classification"][rec.SPORT_MATCH] >= 3
    assert summary["booked_rows"] == 6


def test_capacity_overflow_when_grid_needs_more_courts_than_booked(sources):
    _write_venue(sources["venue_input_path"], badminton_qty=2)
    payload = rec.build_reconciliation_payload(**sources)
    kinds = {issue["kind"] for issue in payload["issues"]["errors"]}
    assert "capacity_overflow" in kinds
    # Booked 17:00-22:00 still contains the 17:20-21:40 grid.
    assert "time_outside_booking" not in kinds


def test_lane_beyond_booked_quantity_is_capacity_overflow(sources):
    def extra(ws):
        ws.merge_cells("K1:M1")
        ws["K1"] = "Main Gym BB3"
        _game(ws, 3, 11, "AAA", "BBB", SPORT_TYPE["BASKETBALL"])
    _write_main(sources["main_schedule_path"], extra=extra)
    payload = rec.build_reconciliation_payload(**sources)
    assert any(i["kind"] == "capacity_overflow" and "lane 3" in i["message"]
               for i in payload["issues"]["errors"])


def test_unknown_named_area_is_not_rehomed(sources):
    def extra(ws):
        ws.merge_cells("K1:M1")
        ws["K1"] = "Nowhere Gym BB1"
        _game(ws, 3, 11, "AAA", "BBB", SPORT_TYPE["BASKETBALL"])
    _write_main(sources["main_schedule_path"], extra=extra)
    payload = rec.build_reconciliation_payload(**sources)
    assert any(i["kind"] == "unknown_venue" and "Nowhere Gym BB1" in i["message"]
               for i in payload["issues"]["errors"])


def test_time_outside_booking_is_error(sources):
    def extra(ws):
        ws.cell(row=6, column=1, value="4:00 PM")
        _game(ws, 6, 2, "AAA", "BBB", SPORT_TYPE["BASKETBALL"])
    _write_main(sources["main_schedule_path"], extra=extra)
    payload = rec.build_reconciliation_payload(**sources)
    assert any(i["kind"] == "time_outside_booking" for i in payload["issues"]["errors"])


def test_unbooked_resource_type_is_reported(sources):
    def extra(ws):
        ws.merge_cells("K1:M1")
        ws["K1"] = "BC Library"
        for col, team in zip((11, 12, 13), ("AAA", "BBB", "CCC")):
            cell = ws.cell(row=3, column=col, value=team)
            cell.fill = _solid(SPORT_STYLES[SPORT_TYPE["BIBLE_CHALLENGE"]].fill_color)
    _write_main(sources["main_schedule_path"], extra=extra)
    payload = rec.build_reconciliation_payload(**sources)
    assert any(i["kind"] == "unknown_venue" and "BC Library" in i["message"]
               for i in payload["issues"]["errors"])


def test_overlap_and_gym_mode_conflict_detected(sources):
    def extra(ws):
        # A volleyball game drawn on the Main Gym while BB1 is playing.
        ws.merge_cells("K1:M1")
        ws["K1"] = "Main Gym VB1"
        _game(ws, 3, 11, "AAA", "BBB", SPORT_TYPE["VOLLEYBALL_WOMEN"])
    _write_main(sources["main_schedule_path"], extra=extra)
    payload = rec.build_reconciliation_payload(**sources)
    assert any(i["kind"] == "gym_mode_conflict" for i in payload["issues"]["errors"])


def test_table_tennis_discrepancy_blocks_unless_waived(sources):
    _write_table_tennis(sources["table_tennis_path"], include_sbc=True)
    payload = rec.build_reconciliation_payload(**sources)
    errors = [i for i in payload["issues"]["errors"] if i["kind"] == "source_discrepancy"]
    assert errors and "SBC" in errors[0]["message"]

    waived = rec.build_reconciliation_payload(**sources, waive_table_tennis_discrepancy=True)
    assert not [i for i in waived["issues"]["errors"] if i["kind"] == "source_discrepancy"]
    assert any(i["kind"] == "source_discrepancy" for i in waived["issues"]["warnings"])


def test_missing_source_is_error(sources, tmp_path):
    sources["soccer_path"] = tmp_path / "nope.xlsx"
    payload = rec.build_reconciliation_payload(**sources)
    assert payload["issues"]["errors"][0]["kind"] == "missing_source"


# --- Playoff-Slots pins against the reconciled windows ----------------------

FRIDAY = datetime(2026, 7, 24)


def _table_tennis_pin(start, slot_minutes):
    return ["TT-Final", SPORT_TYPE["TABLE_TENNIS"], "Final", "Orange Church", FRIDAY, start, slot_minutes]


def _pin_errors(payload):
    return [i for i in payload["issues"]["errors"] if i["kind"] == "playoff_slot_conflict"]


def test_pin_on_the_approved_grid_is_accepted(sources):
    _write_venue(sources["venue_input_path"], extra_pins=[_table_tennis_pin("17:15", 15)])
    payload = rec.build_reconciliation_payload(**sources)
    assert _pin_errors(payload) == []
    assert payload["playoff_slots"]["pins_checked"] == 2


def test_pin_keeping_the_old_slot_length_blocks_execute(sources):
    """The real 2026 failure: booked 20-minute pin, approved 15-minute grid."""
    _write_venue(sources["venue_input_path"], extra_pins=[_table_tennis_pin("17:15", 20)])
    errors = _pin_errors(rec.build_reconciliation_payload(**sources))
    assert len(errors) == 1
    assert "TT-Final" in errors[0]["message"]


def test_pin_off_the_new_grid_blocks_execute(sources):
    _write_venue(sources["venue_input_path"], extra_pins=[_table_tennis_pin("17:20", 15)])
    assert "TT-Final" in _pin_errors(rec.build_reconciliation_payload(**sources))[0]["message"]


def test_pin_inside_a_blacked_out_window_blocks_execute(sources):
    sat = datetime(2026, 7, 18)
    pin = ["BBM-Semi", SPORT_TYPE["BASKETBALL"], "Semi", "EHS Main Gym", sat, "12:00", None]
    _write_venue(sources["venue_input_path"], extra_pins=[pin])
    assert "BBM-Semi" in _pin_errors(rec.build_reconciliation_payload(**sources))[0]["message"]


def test_cli_execute_blocked_by_stale_pin_leaves_file_alone(monkeypatch, sources, tmp_path):
    _write_venue(sources["venue_input_path"], extra_pins=[_table_tennis_pin("17:15", 20)])
    before = sources["venue_input_path"].read_bytes()
    assert _cli(monkeypatch, sources, tmp_path, "--execute") == 1
    assert sources["venue_input_path"].read_bytes() == before
    assert not list(tmp_path.glob("venue_input.backup-*.xlsx"))


# --- execute: backup, atomic write, idempotence, loader compatibility -------

def test_apply_writes_backup_tabs_and_is_idempotent(sources):
    venue = sources["venue_input_path"]
    payload = rec.build_reconciliation_payload(**sources)
    result = rec.apply_reconciliation(payload, venue)
    assert result["changed"] is True
    assert result["backup"] and (venue.parent / result["backup"].split("/")[-1]).exists()

    wb = load_workbook(venue)
    assert {"Venue-Input", "Booked-Venue-Input", "Operational-Blocks", "Reconciliation-Sources",
            "Gym-Modes", "Playoff-Slots"} <= set(wb.sheetnames)
    assert wb["Playoff-Slots"]["A2"].value == "BBM-Final"
    booked_types = [r[2] for r in wb["Booked-Venue-Input"].iter_rows(min_row=2, values_only=True) if r[2]]
    assert len(booked_types) == 6

    # The scheduler's own loader reads the reconciled tab.
    resources, _ = _load_venue_input_rows(venue)
    bb = [r for r in resources if r["resource_type"] == "Basketball Court"]
    assert {(r["open_time"], r["close_time"]) for r in bb} == {("13:00", "16:00")}
    assert len(bb) == 1
    bad = [r for r in resources if r["resource_type"] == "Badminton Court"]
    assert len(bad) == 3 and bad[0]["slot_minutes"] == 20
    assert (bad[0]["open_time"], bad[0]["close_time"]) == ("17:20", "21:40")

    before = venue.read_bytes()
    second = rec.build_reconciliation_payload(**sources)
    assert second["booking_source"] == "Booked-Venue-Input"
    assert second["proposed_venue_rows"] == payload["proposed_venue_rows"]
    again = rec.apply_reconciliation(second, venue)
    assert again == {"changed": False, "backup": None}
    assert venue.read_bytes() == before


def test_changed_source_recomputes_from_booking(sources):
    venue = sources["venue_input_path"]
    rec.apply_reconciliation(rec.build_reconciliation_payload(**sources), venue)

    # Re-issue the main schedule without the BB2 CLOSED block: the window
    # must come back because reconciliation runs from the booking tab.
    def reopen(ws):
        ws.unmerge_cells("E4:G5")
        ws["E4"] = None
    _write_main(sources["main_schedule_path"], extra=reopen)
    payload = rec.build_reconciliation_payload(**sources)
    assert _windows(_rows_for(payload, "B001")) == [(13, 13, 1, 60), (14, 15, 2, 60)]


def test_operator_added_row_is_adopted_not_discarded(sources):
    venue = sources["venue_input_path"]
    rec.apply_reconciliation(rec.build_reconciliation_payload(**sources), venue)
    wb = load_workbook(venue)
    ws = wb["Venue-Input"]
    ws.append(["Tennis Pod", "City Park", "Tennis Court", 4, "Sat-1", datetime(2026, 7, 18), 8, 12, 60])
    wb.save(venue)

    payload = rec.build_reconciliation_payload(**sources)
    assert payload["adopted_booked_rows"] == ["B007"]
    assert _windows(_rows_for(payload, "B007")) == [(8, 12, 4, 60)]
    rec.apply_reconciliation(payload, venue)
    booked = load_workbook(venue)["Booked-Venue-Input"]
    assert any(r[2] == "Tennis Court" for r in booked.iter_rows(min_row=2, values_only=True))


# --- CLI ----------------------------------------------------------------------

def _cli(monkeypatch, sources, tmp_path, *flags):
    import main

    argv = [
        "main.py", "reconcile-approved-schedules",
        "--main-schedule", str(sources["main_schedule_path"]),
        "--badminton", str(sources["badminton_path"]),
        "--soccer", str(sources["soccer_path"]),
        "--table-tennis", str(sources["table_tennis_path"]),
        "--venue-input", str(sources["venue_input_path"]),
        "--audit", str(tmp_path / "audit.json"),
        *flags,
    ]
    monkeypatch.setattr(main.sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        main.main()
    return exc.value.code


def test_cli_dry_run_writes_audit_only(monkeypatch, sources, tmp_path):
    before = sources["venue_input_path"].read_bytes()
    assert _cli(monkeypatch, sources, tmp_path, "--dry-run") == 0
    assert sources["venue_input_path"].read_bytes() == before
    import json
    audit = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert audit["summary"]["proposed_rows"] == len(audit["proposed_venue_rows"])
    assert "_venue_model" not in audit
    assert audit["sources"]["main_schedule"]["sha256"]


def test_cli_execute_blocked_by_discrepancy_leaves_file_alone(monkeypatch, sources, tmp_path):
    _write_table_tennis(sources["table_tennis_path"], include_sbc=True)
    before = sources["venue_input_path"].read_bytes()
    assert _cli(monkeypatch, sources, tmp_path, "--execute") == 1
    assert sources["venue_input_path"].read_bytes() == before
    assert not list(tmp_path.glob("venue_input.backup-*.xlsx"))

    assert _cli(monkeypatch, sources, tmp_path, "--execute", "--waive-table-tennis-discrepancy") == 0
    assert list(tmp_path.glob("venue_input.backup-*.xlsx"))
