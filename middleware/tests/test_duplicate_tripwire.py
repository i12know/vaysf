"""Warning-only duplicate tripwires in scoresheets, badges and the export (#312).

Two things are proven for each output: the WARNING fires for a same-name,
same-birthdate pair under two ChMeetings IDs, and the output is exactly what
it would have been without the check ("paper must match data"). "Without the
check" is a second run with the tripwire patched out.

Every person here is synthetic.
"""

import copy
import io
import json
import zipfile
from unittest.mock import MagicMock

import pytest
from loguru import logger
from openpyxl import Workbook, load_workbook
from PIL import Image

import scoresheets
from badges.generator import BadgeGenerator
from badges.runner import BadgeRunner
from church_teams_export import ChurchTeamsExporter
from scoresheets import (
    BASKETBALL_EVENT,
    VOLLEYBALL_MEN_EVENT,
    VOLLEYBALL_WOMEN_EVENT,
    build_roster_index,
    load_roster_birthdates_from_workbook,
    write_basketball_scoresheets_pdf,
    write_volleyball_scoresheets_pdf,
)
from sync import duplicate_tripwire
from sync.duplicate_finder import DuplicateFinder
from sync.duplicate_tripwire import find_likely_duplicates, tripwire_person, warn_on_likely_duplicates
from wordpress.frontend_connector import WordPressConnector

from test_scoresheets import SCORE_ENTRY_URL, _logo, _schedule_input, _schedule_output


@pytest.fixture
def warnings_logged():
    """WARNING-level log lines written while the test runs."""
    lines = []
    sink = logger.add(lambda message: lines.append(str(message).rstrip("\n")),
                      format="{message}", level="WARNING")
    yield lines
    logger.remove(sink)


@pytest.fixture
def no_aliases(mocker):
    return mocker.patch.object(duplicate_tripwire, "load_person_aliases_for_reader", return_value={})


def _alias(canonical):
    return {"canonical_chm_id": canonical, "reason": "", "confirmed_by": "", "confirmed_on": "", "note": ""}


def _tripwire_lines(lines):
    return [line for line in lines if "Possible duplicate person" in line]


# ── The shared helper ────────────────────────────────────────────────────────


def _person(chm_id, first="Ngoc", last="Le", birthdate="2008-04-15", group="team RPC"):
    return tripwire_person(chm_id, first, last, birthdate, group)


def test_same_name_and_birthdate_under_two_ids_warns_once(warnings_logged, no_aliases):
    people = [_person("3633885"), _person("3634002"), _person("3700000", first="Khoa")]

    warned = warn_on_likely_duplicates(people, context="Basketball score sheets")

    assert warned == [("team RPC", "3633885", "3634002")]
    [line] = _tripwire_lines(warnings_logged)
    assert line == (
        "[VAY SM] Possible duplicate person in Basketball score sheets, team RPC: "
        "ChMeetings IDs 3633885 and 3634002 have the same name and birthdate. Both rows "
        "were kept; the output was not changed. Run 'python main.py find-duplicates' to "
        "review the pair."
    )
    assert "Ngoc" not in line and "2008" not in line  # IDs only: no name or birthdate in the log


def test_helper_never_touches_the_rows_it_is_given(no_aliases):
    people = [_person("3633885"), _person("3634002")]
    before = copy.deepcopy(people)

    warn_on_likely_duplicates(people, context="test")

    assert people == before


@pytest.mark.parametrize(
    "first, second",
    [
        (("Ngọc", "Lê"), ("Ngoc", "Le")),
        (("Đức", "Đinh"), ("duc", "DINH")),
        (("Thảo", "Nguyễn"), (" Thao ", "Nguyen")),
    ],
)
def test_name_comparison_matches_find_duplicates(first, second):
    people = [
        _person("1", first=first[0], last=first[1]),
        _person("2", first=second[0], last=second[1]),
    ]

    assert find_likely_duplicates(people) == [("team RPC", "1", "2")]


@pytest.mark.parametrize(
    "second",
    [
        {"first": "Khoa"},  # twins: same birthdate, different names
        {"birthdate": "2010-09-01"},  # two people who share a name
        {"birthdate": ""},  # nothing to compare
        {"birthdate": None},
        {"group": "team ORN"},  # same person on two teams is not a team duplicate
        {"first": "", "last": ""},
    ],
    ids=["twins", "same_name_other_birthdate", "blank_birthdate", "no_birthdate",
         "other_team", "no_name"],
)
def test_pairs_that_must_not_warn(warnings_logged, no_aliases, second):
    people = [_person("1"), _person("2", **second)]

    assert warn_on_likely_duplicates(people, context="test") == []
    assert _tripwire_lines(warnings_logged) == []
    no_aliases.assert_not_called()  # the alias file is read only when there is a pair


def test_blank_birthdates_never_match_each_other():
    people = [_person("1", birthdate=""), _person("2", birthdate="")]

    assert find_likely_duplicates(people) == []


def test_same_id_listed_twice_and_rows_without_an_id_are_ignored():
    people = [_person("1"), _person("1"), _person(""), _person(None)]

    assert find_likely_duplicates(people) == []


def test_ids_read_back_from_a_workbook_as_numbers():
    people = [_person(3633885.0), _person(3634002)]

    assert find_likely_duplicates(people) == [("team RPC", "3633885", "3634002")]


def test_three_rows_for_one_person_warn_for_each_pair(warnings_logged, no_aliases):
    people = [_person("12"), _person("5"), _person("101")]

    warned = warn_on_likely_duplicates(people, context="test")

    assert warned == [("team RPC", "5", "12"), ("team RPC", "5", "101"), ("team RPC", "12", "101")]
    assert len(_tripwire_lines(warnings_logged)) == 3


def test_pair_already_resolved_by_the_alias_map_is_skipped(warnings_logged):
    people = [_person("100"), _person("200"), _person("300")]

    warned = warn_on_likely_duplicates(
        people, context="test", aliases={"100": _alias("150"), "150": _alias("200")}
    )

    # 100 -> 150 -> 200 is decided; 300 is a new duplicate of that person.
    assert warned == [("team RPC", "100", "300"), ("team RPC", "200", "300")]
    assert all("100 and 200" not in line for line in _tripwire_lines(warnings_logged))


def test_alias_map_is_loaded_through_the_read_side_loader(warnings_logged, mocker):
    loader = mocker.patch.object(
        duplicate_tripwire, "load_person_aliases_for_reader", return_value={"1": _alias("2")}
    )

    assert warn_on_likely_duplicates([_person("1"), _person("2")], context="badge generation") == []
    loader.assert_called_once()
    assert _tripwire_lines(warnings_logged) == []


def test_no_birthdates_at_all_is_reported_not_silent(mocker):
    info = []
    sink = logger.add(lambda message: info.append(str(message)), format="{message}", level="INFO")
    try:
        warn_on_likely_duplicates(
            [_person("1", birthdate=None), _person("2", birthdate=None)],
            context="Basketball score sheets",
        )
    finally:
        logger.remove(sink)

    assert any("Duplicate check skipped for Basketball score sheets" in line for line in info)


def test_a_failure_inside_the_check_never_reaches_the_caller(warnings_logged, mocker):
    mocker.patch.object(duplicate_tripwire, "find_likely_duplicates", side_effect=RuntimeError("boom"))

    assert warn_on_likely_duplicates([_person("1"), _person("2")], context="badge generation") == []
    [line] = [text for text in warnings_logged if "could not run" in text]
    assert "badge generation" in line and "the output was not affected" in line


def test_every_tripwire_pair_is_a_strong_find_duplicates_proposal(mocker, tmp_path):
    """One definition of "same person": the tripwire never warns about a pair
    that `find-duplicates` would not offer."""
    participants = [
        {"participant_id": 1, "chmeetings_id": "501", "first_name": "Ngọc", "last_name": "Lê",
         "birthdate": "2008-04-15", "email": "a@example.com", "phone": "1", "gender": "Female",
         "church_code": "RPC", "approval_status": "approved"},
        {"participant_id": 2, "chmeetings_id": "502", "first_name": "Ngoc", "last_name": "Le",
         "birthdate": "2008-04-15", "email": "b@example.com", "phone": "2", "gender": "Male",
         "church_code": "RPC", "approval_status": "approved"},
        {"participant_id": 3, "chmeetings_id": "503", "first_name": "Khoa", "last_name": "Le",
         "birthdate": "2008-04-15", "email": "a@example.com", "phone": "1", "gender": "Male",
         "church_code": "RPC", "approval_status": "approved"},
    ]
    mocker.patch("sync.duplicate_finder.load_person_aliases", return_value={})
    wp = MagicMock(spec=WordPressConnector)
    wp.get_participants.side_effect = lambda params=None: participants if params["page"] == 1 else []
    wp.get_rosters.return_value = []
    summary = DuplicateFinder(wp, output_dir=tmp_path).run()
    import pandas as pd

    proposals = pd.read_excel(summary["output_file"], sheet_name="Proposals", dtype=str)
    strong = {
        frozenset((row["Canonical ChM ID"], row["Stale ChM ID"]))
        for _, row in proposals.iterrows()
        if row["Strength"] == "strong"
    }

    tripwire = find_likely_duplicates(
        tripwire_person(p["chmeetings_id"], p["first_name"], p["last_name"], p["birthdate"], "church RPC")
        for p in participants
    )

    assert [frozenset(pair[1:]) for pair in tripwire] == [frozenset(("501", "502"))]
    assert {frozenset(pair[1:]) for pair in tripwire} <= strong


# ── Scoresheets ──────────────────────────────────────────────────────────────


def _roster_row(chm_id, first="An", last="Nguyen", team="RPC", event=BASKETBALL_EVENT, **extra):
    row = {
        "Church Team": team,
        "ChMeetings ID": chm_id,
        "First Name": first,
        "Last Name": last,
        "Age (at Event)": 17,
        "sport_type": event,
        "approval_status": "approved",
    }
    row.update(extra)
    return row


def _write_basketball(tmp_path, name, roster_rows, roster_birthdates):
    out = tmp_path / name
    out.mkdir()
    logo = out / "logo.png"
    _logo(logo)
    input_path = out / "approved_schedule_input.json"
    output_path = out / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output()), encoding="utf-8")
    pdf_path, pages = write_basketball_scoresheets_pdf(
        input_path,
        output_path,
        out / "scoresheets",
        roster_rows=roster_rows,
        roster_birthdates=roster_birthdates,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="basketball.pdf",
    )
    return pdf_path.read_bytes(), pages


def _freeze_pdf_clock(mocker):
    # Pillow stamps CreationDate/ModDate; hold the clock so two runs can be compared.
    import time as time_module

    mocker.patch("PIL.PdfImagePlugin.time.gmtime", return_value=time_module.gmtime(0))
    mocker.patch("PIL.PdfParser.time.gmtime", return_value=time_module.gmtime(0), create=True)


def test_scoresheet_duplicate_on_one_team_warns_and_pdf_is_byte_identical(
    tmp_path, mocker, warnings_logged, no_aliases
):
    _freeze_pdf_clock(mocker)
    roster_rows = [
        _roster_row("3633885"),
        _roster_row("3634002"),  # the same athlete, registered again
        _roster_row("3700000", first="Binh"),
    ]
    birthdates = {"3633885": "2008-04-15", "3634002": "2008-04-15", "3700000": "2008-04-15"}
    rows_before = copy.deepcopy(roster_rows)

    with_check, pages = _write_basketball(tmp_path, "with", roster_rows, birthdates)

    [line] = _tripwire_lines(warnings_logged)
    assert "Basketball score sheets, team RPC" in line
    assert "ChMeetings IDs 3633885 and 3634002" in line
    assert "find-duplicates" in line
    assert roster_rows == rows_before  # same rows, same order, no added keys

    mocker.patch.object(scoresheets, "_warn_on_duplicate_roster_rows", return_value=None)
    without_check, pages_without = _write_basketball(tmp_path, "without", roster_rows, birthdates)

    assert pages == pages_without
    assert with_check == without_check


def test_scoresheet_roster_index_still_lists_both_rows(warnings_logged, no_aliases):
    roster_rows = [_roster_row("3633885"), _roster_row("3634002")]
    index = build_roster_index(roster_rows)
    before = copy.deepcopy(index)

    scoresheets._warn_on_duplicate_roster_rows(
        index, "Basketball", {"3633885": "2008-04-15", "3634002": "2008-04-15"}
    )

    assert len(_tripwire_lines(warnings_logged)) == 1
    assert index == before
    assert [row["ChMeetings ID"] for row in index["RPC"]] == ["3633885", "3634002"]
    assert all("Birthdate" not in row for row in index["RPC"])  # nothing was added to print


def test_scoresheet_twins_on_one_team_do_not_warn(tmp_path, warnings_logged, no_aliases):
    roster_rows = [_roster_row("1", first="Minh"), _roster_row("2", first="Manh")]

    _write_basketball(tmp_path, "twins", roster_rows, {"1": "2008-04-15", "2": "2008-04-15"})

    assert _tripwire_lines(warnings_logged) == []


def test_scoresheet_same_name_on_two_teams_does_not_warn(tmp_path, warnings_logged, no_aliases):
    roster_rows = [_roster_row("1", team="RPC"), _roster_row("2", team="ORN")]

    _write_basketball(tmp_path, "teams", roster_rows, {"1": "2008-04-15", "2": "2008-04-15"})

    assert _tripwire_lines(warnings_logged) == []


def test_scoresheet_birthdate_on_the_row_is_used_when_present(warnings_logged, no_aliases):
    index = build_roster_index(
        [_roster_row("1", Birthdate="2008-04-15"), _roster_row("2", Birthdate="2008-04-15")]
    )

    scoresheets._warn_on_duplicate_roster_rows(index, "Basketball")

    assert len(_tripwire_lines(warnings_logged)) == 1


def test_scoresheet_alias_resolved_pair_does_not_warn(warnings_logged, mocker):
    mocker.patch.object(
        duplicate_tripwire, "load_person_aliases_for_reader", return_value={"1": _alias("2")}
    )
    index = build_roster_index([_roster_row("1"), _roster_row("2")])

    scoresheets._warn_on_duplicate_roster_rows(
        index, "Basketball", {"1": "2008-04-15", "2": "2008-04-15"}
    )

    assert _tripwire_lines(warnings_logged) == []


def test_volleyball_checks_men_and_women_separately(tmp_path, warnings_logged, no_aliases):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output()), encoding="utf-8")
    roster_rows = [
        _roster_row("1", event=VOLLEYBALL_MEN_EVENT),
        _roster_row("2", event=VOLLEYBALL_MEN_EVENT),
        # Same name and birthdate on the women's team of the same church: another team.
        _roster_row("3", event=VOLLEYBALL_WOMEN_EVENT),
    ]

    write_volleyball_scoresheets_pdf(
        input_path, output_path, tmp_path / "scoresheets", roster_rows=roster_rows,
        roster_birthdates={"1": "2008-04-15", "2": "2008-04-15", "3": "2008-04-15"},
        logo_path=logo, score_entry_base_url=SCORE_ENTRY_URL, output_filename="volleyball.pdf",
    )

    [line] = _tripwire_lines(warnings_logged)
    assert f"{VOLLEYBALL_MEN_EVENT} score sheets, team RPC" in line
    assert "ChMeetings IDs 1 and 2" in line


def test_roster_birthdates_come_from_the_contacts_status_tab(tmp_path):
    workbook_path = tmp_path / "Church_Team_Status_ALL.xlsx"
    wb = Workbook()
    roster = wb.active
    roster.title = "Roster"
    roster.append(["Church Team", "ChMeetings ID", "First Name"])
    roster.append(["RPC", 3633885, "An"])
    contacts = wb.create_sheet("Contacts-Status")
    contacts.append(["Church Team", "ChMeetings ID", "First Name", "Birthdate"])
    contacts.append(["RPC", 3633885, "An", "2008-04-15"])
    contacts.append(["RPC", "3634002", "An", "2008-04-15T00:00:00"])
    contacts.append(["RPC", 3700000, "Binh", None])
    wb.save(workbook_path)

    assert load_roster_birthdates_from_workbook(workbook_path) == {
        "3633885": "2008-04-15",
        "3634002": "2008-04-15T00:00:00",
    }


@pytest.mark.parametrize("sheets", [["Roster"], ["Roster", "Contacts-Status"]])
def test_roster_birthdates_degrade_to_empty(tmp_path, sheets):
    workbook_path = tmp_path / "partial.xlsx"
    wb = Workbook()
    wb.active.title = sheets[0]
    for name in sheets[1:]:
        wb.create_sheet(name).append(["Church Team", "First Name"])  # no ID/Birthdate columns
    wb.save(workbook_path)

    assert load_roster_birthdates_from_workbook(workbook_path) == {}
    assert load_roster_birthdates_from_workbook(tmp_path / "missing.xlsx") == {}


def test_generate_scoresheets_command_warns_from_a_real_context_workbook(
    tmp_path, monkeypatch, warnings_logged, no_aliases
):
    """End to end through main.py: the Roster tab has no birthdate, so the
    command reads it from the same workbook's Contacts-Status tab."""
    import main

    workbook_path = tmp_path / "Church_Team_Status_ALL.xlsx"
    wb = Workbook()
    roster = wb.active
    roster.title = "Roster"
    roster.append(["Church Team", "ChMeetings ID", "Approval_Status (WP)", "Photo",
                   "First Name", "Last Name", "Age (at Event)", "sport_type",
                   "sport_gender", "sport_format"])
    for chm_id, first in ((3633885, "An"), (3634002, "An"), (3700000, "Binh")):
        roster.append(["RPC", chm_id, "approved", None, first, "Nguyen", 17,
                       "Basketball", "Men", "Team"])
    contacts = wb.create_sheet("Contacts-Status")
    contacts.append(["Church Team", "ChMeetings ID", "First Name", "Last Name", "Birthdate"])
    for chm_id, first in ((3633885, "An"), (3634002, "An"), (3700000, "Binh")):
        contacts.append(["RPC", chm_id, first, "Nguyen", "2008-04-15"])
    wb.save(workbook_path)
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output()), encoding="utf-8")
    monkeypatch.setattr(main.sys, "argv", [
        "main.py", "generate-scoresheets", "--sport", "basketball",
        "--input", str(input_path), "--schedule-output", str(output_path),
        "--input-xlsx", str(workbook_path), "--logo", str(logo),
        "--score-entry-url", SCORE_ENTRY_URL, "--output", str(tmp_path / "out"),
    ])

    with pytest.raises(SystemExit) as exc:
        main.main()

    assert exc.value.code == 0
    assert list((tmp_path / "out").glob("*.pdf"))  # the sheets are still produced
    [line] = _tripwire_lines(warnings_logged)
    assert "Basketball score sheets, team RPC" in line
    assert "ChMeetings IDs 3633885 and 3634002" in line


# ── Badges ───────────────────────────────────────────────────────────────────


def _athlete(chm_id, **overrides):
    athlete = {
        "chmeetings_id": chm_id,
        "church_code": "RPC",
        "church_name": "Redemption Point",
        "first_name": "Ngọc",
        "last_name": "Lê",
        "birthdate": "2008-04-15",
        "approval_status": "approved",
        "primary_sport": "Tennis",
        "consent_status": True,
    }
    athlete.update(overrides)
    return athlete


def _run_badges(tmp_path, name, participants, monkeypatch):
    monkeypatch.setattr("badges.runner.time.sleep", lambda *a, **k: None)
    generator = BadgeGenerator(output_dir=tmp_path / name, filename_salt="test-only-badge-salt")
    chm, wp = MagicMock(), MagicMock()
    wp.get_participants.return_value = participants
    wp.get_churches.return_value = [{"church_code": "RPC", "church_name": "Redemption Point"}]
    chm.get_person.return_value = {"id": "1", "photo": None, "first_name": "Ngọc", "last_name": "Lê"}
    assert BadgeRunner(chm, wp, generator).run(force=True) is True
    return {path.name: path.read_bytes() for path in sorted(generator.output_dir.glob("*.png"))}


def test_badge_duplicate_in_one_church_warns_and_every_badge_is_byte_identical(
    tmp_path, mocker, monkeypatch, warnings_logged, no_aliases
):
    participants = [
        _athlete("3633885"),
        _athlete("3634002", first_name="Ngoc", last_name="Le"),  # same athlete, no diacritics
        _athlete("3700000", first_name="Khoa"),
    ]
    before = copy.deepcopy(participants)

    with_check = _run_badges(tmp_path, "with", copy.deepcopy(participants), monkeypatch)

    [line] = _tripwire_lines(warnings_logged)
    assert "badge generation, church RPC" in line
    assert "ChMeetings IDs 3633885 and 3634002" in line
    assert "find-duplicates" in line
    assert len(with_check) == 3  # a badge for each row, the duplicate included
    assert participants == before

    mocker.patch.object(BadgeRunner, "_warn_on_duplicate_athletes", return_value=None)
    without_check = _run_badges(tmp_path, "without", copy.deepcopy(participants), monkeypatch)

    assert with_check == without_check


def test_badge_name_keeps_its_diacritics(tmp_path, monkeypatch, no_aliases):
    """The name key is for matching only; what is rendered is the registered name."""
    rendered = []
    original = BadgeGenerator.render_to_file

    def spy(self, participant, *args, **kwargs):
        rendered.append((participant["first_name"], participant["last_name"]))
        return original(self, participant, *args, **kwargs)

    monkeypatch.setattr(BadgeGenerator, "render_to_file", spy)

    _run_badges(tmp_path, "names", [_athlete("1"), _athlete("2")], monkeypatch)

    assert rendered == [("Ngọc", "Lê"), ("Ngọc", "Lê")]


@pytest.mark.parametrize(
    "second",
    [
        {"first_name": "Khoa"},  # twins
        {"church_code": "ORN"},  # keyed on church as well as name and birthdate
        {"birthdate": "2010-09-01"},
    ],
    ids=["twins", "other_church", "other_birthdate"],
)
def test_badge_pairs_that_must_not_warn(tmp_path, monkeypatch, warnings_logged, no_aliases, second):
    badges = _run_badges(tmp_path, "quiet", [_athlete("1"), _athlete("2", **second)], monkeypatch)

    assert len(badges) == 2
    assert _tripwire_lines(warnings_logged) == []


def test_badge_alias_resolved_pair_does_not_warn(tmp_path, mocker, monkeypatch, warnings_logged):
    mocker.patch.object(
        duplicate_tripwire, "load_person_aliases_for_reader", return_value={"1": _alias("2")}
    )

    _run_badges(tmp_path, "aliased", [_athlete("1"), _athlete("2")], monkeypatch)

    assert _tripwire_lines(warnings_logged) == []


# ── export-church-teams (issue #40) ──────────────────────────────────────────


def _chm_member(chm_id, first="Daniel", last="Cao", birthdate="2001-03-04", **overrides):
    member = {
        "Church Team": "RPC",
        "ChMeetings ID": chm_id,
        "First Name": first,
        "Last Name": last,
        "Gender": "Male",
        "Birthdate": birthdate,
        "Mobile Phone": "555-0101",
        "Email": f"member{chm_id}@example.com",
        "Is_Member_ChM": True,
        "ChM_Roles": "Athlete/Participant",
        "ChM_Completion_Checklist": "",
        "Update_on_ChM": "2026-05-08 10:00:00",
    }
    member.update(overrides)
    return member


@pytest.fixture
def exporter(mocker):
    chm_connector, wp_connector = MagicMock(), MagicMock()
    chm_connector.authenticate.return_value = True
    mocker.patch("church_teams_export.ChMeetingsConnector", return_value=chm_connector)
    mocker.patch("church_teams_export.WordPressConnector", return_value=wp_connector)
    wp_connector.get_church_by_code.return_value = {"church_id": 1, "church_code": "RPC"}
    wp_connector.get_validation_issues.return_value = []
    wp_connector.get_rosters.return_value = []
    instance = ChurchTeamsExporter()
    instance.latest_chm_update_by_church = {"RPC": "2026-05-08 10:00:00"}
    return instance, wp_connector


def _export(exporter_and_wp, mocker, members, output_dir):
    instance, wp_connector = exporter_and_wp
    mocker.patch.object(instance, "_fetch_chm_church_team_data", return_value={"RPC": members})
    wp_connector.get_participants.return_value = [
        {
            "participant_id": 100 + index,
            "chmeetings_id": member["ChMeetings ID"],
            "approval_status": "approved",
            "created_at": "2026-05-01 10:00:00",
        }
        for index, member in enumerate(members)
    ]
    output_dir.mkdir()
    assert instance.generate_reports("RPC", output_dir) is True
    return output_dir / "Church_Team_Status_RPC.xlsx"


def _workbook_parts(path):
    """Every part of the xlsx except the one that records when it was written."""
    with zipfile.ZipFile(path) as archive:
        return {
            name: archive.read(name) for name in archive.namelist() if name != "docProps/core.xml"
        }


def test_issue_40_duplicate_name_in_the_export_warns_and_the_workbook_is_unchanged(
    exporter, mocker, tmp_path, warnings_logged, no_aliases
):
    """#40: two profiles for one athlete both sit in the church's Team group, so
    the export lists the name twice. The row stays; the log now says so."""
    members = [
        _chm_member("4100001"),
        _chm_member("4100002"),  # the second application of the same athlete
        _chm_member("4100003", first="Minh"),
    ]

    with_check = _export(exporter, mocker, members, tmp_path / "with")

    [line] = _tripwire_lines(warnings_logged)
    assert "export-church-teams, church RPC" in line
    assert "ChMeetings IDs 4100001 and 4100002" in line
    assert "find-duplicates" in line
    contacts = load_workbook(with_check)["Contacts-Status"]
    exported_ids = [str(row[1]) for row in contacts.iter_rows(min_row=2, values_only=True)]
    assert sorted(exported_ids) == ["4100001", "4100002", "4100003"]  # the duplicate is still listed

    mocker.patch("church_teams_export.warn_on_likely_duplicates", return_value=[])
    without_check = _export(exporter, mocker, members, tmp_path / "without")

    assert _workbook_parts(with_check) == _workbook_parts(without_check)


def test_export_rows_handed_to_the_writer_are_identical(exporter, mocker, tmp_path, no_aliases):
    instance, _ = exporter
    members = [_chm_member("4100001"), _chm_member("4100002")]
    write_report = mocker.patch.object(instance, "_write_excel_report")

    _export(exporter, mocker, members, tmp_path / "with")
    with_check = copy.deepcopy(write_report.call_args.args[1:])

    mocker.patch("church_teams_export.warn_on_likely_duplicates", return_value=[])
    _export(exporter, mocker, members, tmp_path / "without")

    assert write_report.call_args.args[1:] == with_check
    assert [row["ChMeetings ID"] for row in with_check[1]] == ["4100001", "4100002"]


@pytest.mark.parametrize(
    "second",
    [
        {"first": "Dustin"},  # twins in one church
        {"birthdate": "2003-07-08"},  # two members who share a name
    ],
    ids=["twins", "same_name_other_birthdate"],
)
def test_export_pairs_that_must_not_warn(
    exporter, mocker, tmp_path, warnings_logged, no_aliases, second
):
    mocker.patch.object(exporter[0], "_write_excel_report")

    _export(exporter, mocker, [_chm_member("1"), _chm_member("2", **second)], tmp_path / "out")

    assert _tripwire_lines(warnings_logged) == []


def test_export_alias_resolved_pair_does_not_warn(exporter, mocker, tmp_path, warnings_logged):
    mocker.patch.object(
        duplicate_tripwire, "load_person_aliases_for_reader", return_value={"1": _alias("2")}
    )
    mocker.patch.object(exporter[0], "_write_excel_report")

    _export(exporter, mocker, [_chm_member("1"), _chm_member("2")], tmp_path / "out")

    assert _tripwire_lines(warnings_logged) == []


# ── The tripwire module cannot write anywhere ────────────────────────────────


def test_tripwire_module_imports_no_connector():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(duplicate_tripwire.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    assert not any(name.startswith(("chmeetings", "wordpress", "requests")) for name in imported)


def test_png_fixture_is_stable():
    """Guards the byte comparisons above: Pillow PNG output is deterministic."""
    first, second = io.BytesIO(), io.BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(first, "PNG")
    Image.new("RGB", (4, 4), (1, 2, 3)).save(second, "PNG")
    assert first.getvalue() == second.getvalue()
