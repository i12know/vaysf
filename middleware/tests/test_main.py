import argparse
import datetime as dt
import json

import pytest
from openpyxl import Workbook, load_workbook

import main
from schedule_workbook import ScheduleWorkbookBuilder


def _run_main_expect_exit(expected_code: int) -> None:
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == expected_code


def _minimal_schedule_input() -> dict:
    return {
        "generated_at": "2026-05-15T00:00:00",
        "gym_court_scenario": 4,
        "game_count": 2,
        "resource_count": 1,
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
            },
            {
                "game_id": "BBM-02",
                "event": "Basketball - Men Team",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 2,
                "team_a_id": "BBM-P1-T3",
                "team_b_id": "BBM-P1-T4",
                "duration_minutes": 60,
                "resource_type": "Gym Court",
                "earliest_slot": None,
                "latest_slot": None,
            },
        ],
        "resources": [
            {
                "resource_id": "GYM-Sat-1-1",
                "resource_type": "Gym Court",
                "label": "Court-1",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "10:00",
                "slot_minutes": 60,
                "exclusive_group": "",
            }
        ],
        "playoff_slots": [],
        "gym_modes": {},
    }


def test_parse_args_solve_schedule_defaults(monkeypatch):
    monkeypatch.setattr(main.sys, "argv", ["main.py", "solve-schedule"])
    args = main.parse_args()
    assert args.command == "solve-schedule"
    assert args.input is None
    assert args.output is None


def test_parse_args_produce_schedule_aliases(monkeypatch):
    monkeypatch.setattr(
        main.sys,
        "argv",
        [
            "main.py",
            "produce-schedule",
            "--input",
            "out.json",
            "--constraint",
            "in.json",
            "--output",
            "schedule.xlsx",
        ],
    )
    args = main.parse_args()
    assert args.command == "produce-schedule"
    assert args.schedule_output == "out.json"
    assert args.schedule_input == "in.json"
    assert args.output == "schedule.xlsx"


def test_parse_args_build_schedule_workbook_defaults(monkeypatch):
    monkeypatch.setattr(main.sys, "argv", ["main.py", "build-schedule-workbook"])
    args = main.parse_args()
    assert args.command == "build-schedule-workbook"
    assert args.input_json is None
    assert args.input_xlsx is None
    assert args.output is None


def test_main_build_schedule_workbook_writes_xlsx(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "EXPORT_DIR", tmp_path)

    schedule_input_path = tmp_path / "schedule_input.json"
    schedule_input_path.write_text(
        json.dumps(_minimal_schedule_input()), encoding="utf-8"
    )

    class FakeDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 15)

    monkeypatch.setattr(main.datetime, "date", FakeDate)
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            command="build-schedule-workbook",
            input_json=None,
            input_xlsx=None,
            output=None,
        ),
    )

    _run_main_expect_exit(0)

    out_path = tmp_path / "Schedule_Workbook_2026-05-15.xlsx"
    assert out_path.exists()
    wb = load_workbook(out_path)
    assert "Schedule-Input" in wb.sheetnames


def test_main_build_schedule_workbook_missing_input_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "EXPORT_DIR", tmp_path)
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            command="build-schedule-workbook",
            input_json=str(tmp_path / "does_not_exist.json"),
            input_xlsx=None,
            output=None,
        ),
    )

    _run_main_expect_exit(1)


def test_main_solve_schedule_uses_default_paths(mocker, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    mock_run = mocker.patch("scheduler.run_solve_schedule", return_value=7)
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(command="solve-schedule", input=None, output=None),
    )

    _run_main_expect_exit(7)

    mock_run.assert_called_once_with(
        tmp_path / "schedule_input.json",
        tmp_path / "schedule_output.json",
    )


def test_main_produce_schedule_uses_default_paths(mocker, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "EXPORT_DIR", tmp_path)

    schedule_output_path = tmp_path / "schedule_output.json"
    schedule_input_path = tmp_path / "schedule_input.json"
    schedule_output_path.write_text(
        json.dumps(
            {
                "solved_at": "2026-05-15T12:00:00",
                "status": "OPTIMAL",
                "solver_wall_seconds": 0.1,
                "assignments": [],
                "unscheduled": [],
            }
        ),
        encoding="utf-8",
    )
    schedule_input_path.write_text(
        json.dumps({"games": [], "resources": [], "playoff_slots": []}),
        encoding="utf-8",
    )

    class FakeDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 15)

    monkeypatch.setattr(main.datetime, "date", FakeDate)
    mock_write = mocker.patch.object(
        ScheduleWorkbookBuilder,
        "write_schedule_output_workbook",
    )
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            command="produce-schedule",
            schedule_output=None,
            schedule_input=None,
            output=None,
        ),
    )

    _run_main_expect_exit(0)

    mock_write.assert_called_once()
    out_path, so_data, si_data = mock_write.call_args.args
    assert out_path == tmp_path / "VAYSF_Schedule_2026-05-15.xlsx"
    assert so_data["status"] == "OPTIMAL"
    assert si_data["games"] == []


def test_schedule_pipeline_export_solve_produce_local(mocker, monkeypatch, tmp_path):
    pytest.importorskip("ortools")

    export_dir = tmp_path / "export"
    schedule_input_path = export_dir / "schedule_input.json"
    schedule_output_path = export_dir / "schedule_output.json"
    workbook_path = export_dir / "VAYSF_Schedule_test.xlsx"
    real_exporter_cls = main.ChurchTeamsExporter

    class FakeExporter:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def generate_reports(
            self,
            target_church_code,
            output_dir,
            force_resend_pending,
            force_resend_validated1,
            force_resend_validated2,
            dry_run,
            target_resend_chm_id,
        ):
            output_dir.mkdir(parents=True, exist_ok=True)
            wb = Workbook()
            ws = wb.active
            ws.title = "Summary"
            ws["A1"] = "Fake export for CLI pipeline test"
            wb.save(output_dir / "Church_Team_Status_ALL_2026-05-15.xlsx")
            data = _minimal_schedule_input()
            schedule_input = output_dir / "schedule_input.json"
            schedule_input.write_text(json.dumps(data), encoding="utf-8")
            return True

    monkeypatch.setattr(main, "ChurchTeamsExporter", FakeExporter)

    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            command="export-church-teams",
            church_code=None,
            output=str(export_dir),
            force_resend_pending=False,
            force_resend_validated1=False,
            force_resend_validated2=False,
            dry_run=False,
            chm_id=None,
        ),
    )
    _run_main_expect_exit(0)
    assert schedule_input_path.exists()
    monkeypatch.setattr(main, "ChurchTeamsExporter", real_exporter_cls)

    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            command="solve-schedule",
            input=str(schedule_input_path),
            output=str(schedule_output_path),
        ),
    )
    _run_main_expect_exit(0)
    assert schedule_output_path.exists()

    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            command="produce-schedule",
            schedule_output=str(schedule_output_path),
            schedule_input=str(schedule_input_path),
            output=str(workbook_path),
        ),
    )
    _run_main_expect_exit(0)

    wb = load_workbook(workbook_path)
    assert "Schedule-by-Time" in wb.sheetnames
    assert "Schedule-by-Sport" in wb.sheetnames

    schedule_output = json.loads(schedule_output_path.read_text(encoding="utf-8"))
    assert schedule_output["status"] == "OPTIMAL"
    assert len(schedule_output["assignments"]) == 2
