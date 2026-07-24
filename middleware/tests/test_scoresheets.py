import json

from PIL import Image

import scoresheets
from score_sheet_verses import VerseSetError, load_bible_verse_set
from scoresheets import (
    BASKETBALL_EVENT,
    BIBLE_CHALLENGE_EVENT,
    LOGO_BOX,
    MAX_ROSTER_ROWS,
    MAX_VOLLEYBALL_ROSTER_ROWS,
    SOCCER_EVENT,
    VOLLEYBALL_MEN_EVENT,
    VOLLEYBALL_WOMEN_EVENT,
    ScoreSheetError,
    _extract_photo_ref,
    _bible_challenge_scripture_summary,
    _filter_games,
    _friendly_location,
    build_bible_challenge_roster_index,
    build_roster_index,
    build_soccer_roster_index,
    build_volleyball_roster_index,
    enrich_roster_photos_from_workbook,
    render_basketball_scoresheet_page,
    render_bible_challenge_scoresheet_page,
    render_soccer_scoresheet_page,
    render_volleyball_scoresheet_page,
    score_entry_url_for_game,
    write_basketball_scoresheets_pdf,
    write_bible_challenge_scoresheets_pdf,
    write_soccer_scoresheets_pdf,
    write_volleyball_scoresheets_pdf,
)

SCORE_ENTRY_URL = "https://sportsfest.example.test/coordinator-score-entry/"


def _schedule_input():
    return {
        "games": [
            {
                "game_id": "BBM-01",
                "event": BASKETBALL_EVENT,
                "stage": "Pool",
                "pool_id": "A",
                "round": 1,
                "team_a_id": "BBM::RPC",
                "team_a_label": "RPC",
                "team_b_id": "BBM::GAC",
                "team_b_label": "GAC",
                "duration_minutes": 60,
                "resource_type": "Basketball Court",
            },
            {
                "game_id": "VBM-01",
                "event": VOLLEYBALL_MEN_EVENT,
                "stage": "Pool",
                "pool_id": "A",
                "round": 1,
                "team_a_id": "VBM::RPC",
                "team_a_label": "RPC",
                "team_b_id": "VBM::GAC",
                "team_b_label": "GAC",
                "duration_minutes": 60,
                "resource_type": "Volleyball Court",
            },
            {
                "game_id": "VBW-01",
                "event": VOLLEYBALL_WOMEN_EVENT,
                "stage": "Pool",
                "pool_id": "A",
                "round": 1,
                "team_a_id": "VBW::SDC",
                "team_a_label": "SDC",
                "team_b_id": "VBW::GLA",
                "team_b_label": "GLA",
                "duration_minutes": 60,
                "resource_type": "Volleyball Court",
            },
            {
                "game_id": "SOC-G1",
                "event": SOCCER_EVENT,
                "stage": "Pool",
                "pool_id": "A",
                "round": 1,
                "team_a_id": "SOC::RPC",
                "team_a_label": "RPC",
                "team_b_id": "SOC::GAC",
                "team_b_label": "GAC",
                "duration_minutes": 60,
                "resource_type": "Soccer Field",
            },
            {
                "game_id": "BC-RR-01",
                "event": BIBLE_CHALLENGE_EVENT,
                "stage": "Pool",
                "pool_id": "A",
                "round": 1,
                "team_a_id": "BC::RPC",
                "team_a_label": "RPC",
                "team_b_id": "BC::GAC",
                "team_b_label": "GAC",
                "team_c_id": "BC::MWC",
                "team_c_label": "MWC",
                "duration_minutes": 60,
                "resource_type": "Bible Challenge Station",
            },
        ],
        "resources": [],
    }


def _schedule_output():
    return {
        "status": "APPROVED",
        "assignments": [
            {"game_id": "BBM-01", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-16:00"},
            {"game_id": "VBM-01", "resource_id": "GYM-Sat-1-2", "slot": "Sat-1-17:00"},
            {"game_id": "VBW-01", "resource_id": "GYM-Sat-1-3", "slot": "Sat-1-18:00"},
            {"game_id": "SOC-G1", "resource_id": "SOC-Sat-1-1", "slot": "Sat-1-19:00"},
            {"game_id": "BC-RR-01", "resource_id": "BC-Sun-1-1", "slot": "Sun-1-18:00"},
        ],
        "unscheduled": [],
    }


def _schedule_input_with_playoffs():
    """Base fixture plus BBM quarterfinal/semifinal rows for --stage/--game-key tests (Issue #348)."""
    data = _schedule_input()
    data["games"].extend([
        {
            "game_id": "BBM-QF-1",
            "event": BASKETBALL_EVENT,
            "stage": "Quarterfinal",
            "team_a_id": "BBM::RPC",
            "team_a_label": "RPC",
            "team_b_id": "BBM::GAC",
            "team_b_label": "GAC",
            "duration_minutes": 60,
            "resource_type": "Basketball Court",
        },
        {
            "game_id": "BBM-Semi-1",
            "event": BASKETBALL_EVENT,
            "stage": "Semifinal",
            "team_a_id": "BBM::RPC",
            "team_a_label": "RPC",
            "team_b_id": "BBM::GAC",
            "team_b_label": "GAC",
            "duration_minutes": 60,
            "resource_type": "Basketball Court",
        },
    ])
    return data


def _schedule_output_with_playoffs():
    data = _schedule_output()
    data["assignments"].extend([
        {"game_id": "BBM-QF-1", "resource_id": "GYM-Sat-2-1", "slot": "Sat-2-08:00"},
        {"game_id": "BBM-Semi-1", "resource_id": "GYM-Sat-2-1", "slot": "Sat-2-11:00"},
    ])
    return data


def _logo(path):
    image = Image.new("RGBA", (80, 80), (220, 20, 30, 255))
    image.save(path)


def _photo(path, color=(30, 120, 220, 255)):
    image = Image.new("RGBA", (40, 40), color)
    image.save(path)


def test_build_roster_index_accepts_exported_basketball_triplet():
    rows = [
        {
            "Church Team": "RPC",
            "First Name": "An",
            "Last Name": "Nguyen",
            "Age (at Event)": 17,
            "sport_type": "Basketball",
            "sport_gender": "Men",
            "sport_format": "Team",
        },
        {
            "Church Team": "RPC",
            "First Name": "Nope",
            "Last Name": "Nguyen",
            "Age (at Event)": 17,
            "sport_type": "Basketball",
            "sport_gender": "Women",
            "sport_format": "Team",
        },
    ]

    indexed = build_roster_index(rows)

    assert [row["First Name"] for row in indexed["RPC"]] == ["An"]


def test_build_volleyball_roster_index_keeps_men_and_women_separate():
    rows = [
        {
            "Church Team": "RPC",
            "First Name": "An",
            "Last Name": "Nguyen",
            "Age (at Event)": 17,
            "sport_type": "Volleyball",
            "sport_gender": "Men",
            "sport_format": "Team",
        },
        {
            "Church Team": "RPC",
            "First Name": "Bao",
            "Last Name": "Tran",
            "Age (at Event)": 18,
            "sport_type": "Volleyball",
            "sport_gender": "Women",
            "sport_format": "Team",
        },
    ]

    indexed = build_volleyball_roster_index(rows)

    assert [row["First Name"] for row in indexed[VOLLEYBALL_MEN_EVENT]["RPC"]] == ["An"]
    assert [row["First Name"] for row in indexed[VOLLEYBALL_WOMEN_EVENT]["RPC"]] == ["Bao"]


def test_build_soccer_roster_index_accepts_exported_coed_exhibition_triplet():
    rows = [
        {
            "Church Team": "RPC",
            "First Name": "An",
            "Last Name": "Nguyen",
            "Age (at Event)": 17,
            "sport_type": "Soccer",
            "sport_gender": "Coed",
            "sport_format": "Exhibition",
        },
        {
            "Church Team": "RPC",
            "First Name": "Nope",
            "Last Name": "Nguyen",
            "Age (at Event)": 17,
            "sport_type": "Soccer",
            "sport_gender": "Men",
            "sport_format": "Team",
        },
    ]

    indexed = build_soccer_roster_index(rows)

    assert [row["First Name"] for row in indexed["RPC"]] == ["An"]


def test_build_bible_challenge_roster_index_accepts_mixed_team_roster():
    rows = [
        {
            "Church Team": "RPC",
            "First Name": "An",
            "Last Name": "Nguyen",
            "Age (at Event)": 17,
            "sport_type": "Bible Challenge",
            "sport_gender": "Mixed",
            "sport_format": "Team",
        },
        {
            "Church Team": "RPC",
            "First Name": "Nope",
            "Last Name": "Nguyen",
            "Age (at Event)": 17,
            "sport_type": "Basketball",
            "sport_gender": "Men",
            "sport_format": "Team",
        },
    ]

    indexed = build_bible_challenge_roster_index(rows)

    assert [row["First Name"] for row in indexed["RPC"]] == ["An"]


def test_render_basketball_scoresheet_places_logo_upper_left(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    photo = tmp_path / "player.png"
    _photo(photo)
    roster_index = build_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "Photo": str(photo),
                "sport_type": "Basketball",
                "sport_gender": "Men",
                "sport_format": "Team",
                "approval_status": "approved",
            }
        ]
    )

    page = render_basketball_scoresheet_page(
        {
            "game_key": "BBM-01",
            "event": BASKETBALL_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "GYM-Sat-1-1",
            "scheduled_slot": "Sat-1-16:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    # The canonical logo is contained in LOGO_BOX at the upper-left of the page.
    sample_x = LOGO_BOX[0] + 20
    sample_y = LOGO_BOX[1] + 20
    assert page.getpixel((sample_x, sample_y)) == (220, 20, 30)
    # First roster photo sits inside the left team table, below the header.
    assert page.getpixel((124, 570)) == (30, 120, 220)


def test_render_basketball_scoresheet_strikes_unapproved_roster_row(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    roster_index = build_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Basketball",
                "sport_gender": "Men",
                "sport_format": "Team",
                "Approval_Status (WP)": "reapproval_required",
            }
        ]
    )

    page = render_basketball_scoresheet_page(
        {
            "game_key": "BBM-01",
            "event": BASKETBALL_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "GYM-Sat-1-1",
            "scheduled_slot": "Sat-1-16:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((250, 586)) == (170, 31, 45)


def test_render_basketball_scoresheet_does_not_strike_wp_approved_roster_row(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    roster_index = build_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Basketball",
                "sport_gender": "Men",
                "sport_format": "Team",
                "Approval_Status (WP)": "approved",
            }
        ]
    )

    page = render_basketball_scoresheet_page(
        {
            "game_key": "BBM-01",
            "event": BASKETBALL_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "GYM-Sat-1-1",
            "scheduled_slot": "Sat-1-16:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((250, 586)) != (170, 31, 45)


def test_render_volleyball_scoresheet_places_logo_and_roster_photo(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    photo = tmp_path / "player.png"
    _photo(photo, color=(40, 200, 90, 255))
    roster_index = build_volleyball_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "Photo": str(photo),
                "sport_type": "Volleyball",
                "sport_gender": "Men",
                "sport_format": "Team",
                "approval_status": "approved",
            }
        ]
    )

    page = render_volleyball_scoresheet_page(
        {
            "game_key": "VBM-01",
            "event": VOLLEYBALL_MEN_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "GYM-Sat-1-2",
            "scheduled_slot": "Sat-1-17:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((LOGO_BOX[0] + 20, LOGO_BOX[1] + 20)) == (220, 20, 30)
    assert page.getpixel((111, 804)) == (40, 200, 90)


def test_render_volleyball_scoresheet_strikes_unapproved_roster_row(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    roster_index = build_volleyball_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Volleyball",
                "sport_gender": "Men",
                "sport_format": "Team",
                "Approval_Status (WP)": "pending",
            }
        ]
    )

    page = render_volleyball_scoresheet_page(
        {
            "game_key": "VBM-01",
            "event": VOLLEYBALL_MEN_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "GYM-Sat-1-2",
            "scheduled_slot": "Sat-1-17:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((180, 816)) == (170, 31, 45)


def test_render_volleyball_scoresheet_does_not_strike_wp_approved_roster_row(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    roster_index = build_volleyball_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Volleyball",
                "sport_gender": "Men",
                "sport_format": "Team",
                "Approval_Status (WP)": "approved",
            }
        ]
    )

    page = render_volleyball_scoresheet_page(
        {
            "game_key": "VBM-01",
            "event": VOLLEYBALL_MEN_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "GYM-Sat-1-2",
            "scheduled_slot": "Sat-1-17:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((180, 816)) != (170, 31, 45)


def test_render_soccer_scoresheet_places_logo_upper_left(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)

    page = render_soccer_scoresheet_page(
        {
            "game_key": "SOC-G1",
            "event": SOCCER_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "SOC-Sat-1-1",
            "scheduled_slot": "Sat-1-19:00",
        },
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((LOGO_BOX[0] + 20, LOGO_BOX[1] + 20)) == (220, 20, 30)


def test_render_soccer_scoresheet_prints_and_strikes_unapproved_roster_row(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    roster_index = build_soccer_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Soccer",
                "sport_gender": "Coed",
                "sport_format": "Exhibition",
                "Approval_Status (WP)": "validated",
            }
        ]
    )

    page = render_soccer_scoresheet_page(
        {
            "game_key": "SOC-G1",
            "event": SOCCER_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "SOC-Sat-1-1",
            "scheduled_slot": "Sat-1-19:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((250, 921)) == (170, 31, 45)


def test_render_soccer_scoresheet_does_not_strike_wp_approved_roster_row(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    roster_index = build_soccer_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Soccer",
                "sport_gender": "Coed",
                "sport_format": "Exhibition",
                "Approval_Status (WP)": "approved",
            }
        ]
    )

    page = render_soccer_scoresheet_page(
        {
            "game_key": "SOC-G1",
            "event": SOCCER_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "resource_id": "SOC-Sat-1-1",
            "scheduled_slot": "Sat-1-19:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((250, 921)) != (170, 31, 45)


def test_render_bible_challenge_scoresheet_places_logo_upper_left(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)

    page = render_bible_challenge_scoresheet_page(
        {
            "game_key": "BC-RR-01",
            "event": BIBLE_CHALLENGE_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "team_c_label": "MWC",
            "resource_id": "BC-Sun-1-1",
            "scheduled_slot": "Sun-1-18:00",
        },
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((LOGO_BOX[0] + 20, LOGO_BOX[1] + 20)) == (220, 20, 30)


def test_render_bible_challenge_scoresheet_prints_roster_photo(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    photo = tmp_path / "player.png"
    _photo(photo, color=(40, 200, 90, 255))
    roster_index = build_bible_challenge_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "Photo": str(photo),
                "sport_type": "Bible Challenge",
                "sport_gender": "Mixed",
                "sport_format": "Team",
                "approval_status": "approved",
            }
        ]
    )

    page = render_bible_challenge_scoresheet_page(
        {
            "game_key": "BC-RR-01",
            "event": BIBLE_CHALLENGE_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "team_c_label": "MWC",
            "resource_id": "BC-Sun-1-1",
            "scheduled_slot": "Sun-1-18:00",
        },
        roster_index=roster_index,
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    # First roster photo sits inside team A's roster column, below the score tracker.
    assert page.getpixel((124, 870)) == (40, 200, 90)


def test_render_bible_challenge_scoresheet_strikes_unapproved_roster_row():
    roster_index = build_bible_challenge_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Bible Challenge",
                "sport_gender": "Mixed",
                "sport_format": "Team",
                "Approval_Status (WP)": "pending",
            }
        ]
    )

    page = render_bible_challenge_scoresheet_page(
        {
            "game_key": "BC-RR-01",
            "event": BIBLE_CHALLENGE_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "team_c_label": "MWC",
            "resource_id": "BC-Sun-1-1",
            "scheduled_slot": "Sun-1-18:00",
        },
        roster_index=roster_index,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((200, 879)) == (170, 31, 45)


def test_render_bible_challenge_scoresheet_does_not_strike_wp_approved_roster_row():
    roster_index = build_bible_challenge_roster_index(
        [
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Bible Challenge",
                "sport_gender": "Mixed",
                "sport_format": "Team",
                "Approval_Status (WP)": "approved",
            }
        ]
    )

    page = render_bible_challenge_scoresheet_page(
        {
            "game_key": "BC-RR-01",
            "event": BIBLE_CHALLENGE_EVENT,
            "team_a_label": "RPC",
            "team_b_label": "GAC",
            "team_c_label": "MWC",
            "resource_id": "BC-Sun-1-1",
            "scheduled_slot": "Sun-1-18:00",
        },
        roster_index=roster_index,
        score_entry_base_url=SCORE_ENTRY_URL,
    )

    assert page.getpixel((200, 879)) != (170, 31, 45)


def test_basketball_roster_table_capacity_is_15():
    assert MAX_ROSTER_ROWS == 15


def test_volleyball_roster_table_capacity_is_18():
    assert MAX_VOLLEYBALL_ROSTER_ROWS == 18


def test_friendly_location_formats_basketball_gym_resource_ids():
    assert _friendly_location({"resource_id": "GYM-Sat-1-4"}) == "EHS Main Gym - Court 4"
    assert _friendly_location({"scheduled_location": "Orange - Table 1", "resource_id": "GYM-Sat-1-4"}) == "Orange - Table 1"


def test_enrich_roster_photos_reads_excel_image_formula(tmp_path):
    from openpyxl import Workbook

    workbook_path = tmp_path / "roster.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Roster"
    ws.append(["Church Team", "Photo", "First Name"])
    ws.append(["RPC", '=IMAGE("https://example.test/player.jpg")', "An"])
    wb.save(workbook_path)

    rows = [{"Church Team": "RPC", "Photo": None, "First Name": "An"}]

    enriched = enrich_roster_photos_from_workbook(rows, workbook_path)

    assert enriched[0]["Photo"] == '=IMAGE("https://example.test/player.jpg")'
    assert rows[0]["Photo"] is None


def test_enrich_roster_photos_replaces_nan_with_xludf_image_formula(tmp_path):
    from openpyxl import Workbook

    workbook_path = tmp_path / "roster.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Roster"
    ws.append(["Church Team", "Photo", "First Name"])
    ws.append(["RPC", '=_xludf.IMAGE("https://example.test/player.jpg")', "An"])
    wb.save(workbook_path)

    rows = [{"Church Team": "RPC", "Photo": float("nan"), "First Name": "An"}]

    enriched = enrich_roster_photos_from_workbook(rows, workbook_path)

    assert enriched[0]["Photo"] == '=_xludf.IMAGE("https://example.test/player.jpg")'
    assert _extract_photo_ref(enriched[0]["Photo"]) == "https://example.test/player.jpg"


def test_score_entry_url_uses_stable_game_key():
    assert score_entry_url_for_game("BBM-01", SCORE_ENTRY_URL) == (
        "https://sportsfest.example.test/coordinator-score-entry/?action=score&game_key=BBM-01"
    )


def test_load_bible_challenge_verse_set_returns_2026_references_in_order():
    verses = load_bible_verse_set("bc_2026", event="bible-challenge")

    assert [verse.reference for verse in verses] == [
        "Matthew 13:23",
        "Colossians 2:6-7",
        "Psalm 1:3",
        "Jeremiah 17:7-8",
        "James 1:2-3",
        "Romans 8:37",
        "1 Corinthians 16:13",
        "2 Corinthians 4:8-9",
        "Matthew 5:14",
        "Galatians 6:9-10",
        "1 Timothy 4:12",
        "Matthew 13:31-32",
        "2 Timothy 4:7",
        "Philippians 3:14",
    ]
    assert all(verse.event_locked for verse in verses)
    assert all(not verse.general_pool for verse in verses)
    assert all(verse.verse_text != verse.reference for verse in verses)
    assert verses[3].verse_text.startswith("Blessed is the man who trusts")


def test_load_bible_challenge_verse_set_accepts_wordpress_event_label():
    verses = load_bible_verse_set("bc_2026", event=BIBLE_CHALLENGE_EVENT)

    assert len(verses) == 14
    assert verses[0].reference == "Matthew 13:23"


def test_bible_challenge_verse_set_is_locked_to_bible_challenge():
    try:
        load_bible_verse_set("bc_2026", event="basketball")
    except VerseSetError as exc:
        assert "bc_2026" in str(exc)
    else:
        raise AssertionError("Expected locked BC verse set to reject basketball.")


def test_bible_challenge_verse_set_rejects_placeholder_text(tmp_path):
    source = tmp_path / "verses.json"
    source.write_text(
        json.dumps(
            {
                "verse_sets": [
                    {
                        "set_key": "bc_test",
                        "event": BIBLE_CHALLENGE_EVENT,
                        "season": 2026,
                        "sort_order": 1,
                        "reference": "John 3:16",
                        "verse_text": "John 3:16",
                        "active": True,
                        "event_locked": True,
                        "general_pool": False,
                        "allowed_events": [BIBLE_CHALLENGE_EVENT],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        load_bible_verse_set("bc_test", event=BIBLE_CHALLENGE_EVENT, source_path=source)
    except VerseSetError as exc:
        assert "placeholder verse_text" in str(exc)
    else:
        raise AssertionError("Expected placeholder verse text to be rejected.")


def test_bible_challenge_scripture_summary_uses_loaded_set():
    summary = _bible_challenge_scripture_summary(load_bible_verse_set("bc_2026", event="bible-challenge"))

    assert summary.startswith("Matthew 13:23; Colossians 2:6-7")
    assert summary.endswith("2 Timothy 4:7; Philippians 3:14")


def test_write_basketball_scoresheets_pdf_filters_to_basketball(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output()), encoding="utf-8")

    pdf_path, page_count = write_basketball_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        roster_rows=[
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": BASKETBALL_EVENT,
                "approval_status": "approved",
            }
        ],
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="basketball.pdf",
    )

    assert page_count == 1
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_write_volleyball_scoresheets_pdf_filters_to_volleyball(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output()), encoding="utf-8")

    pdf_path, page_count = write_volleyball_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        roster_rows=[
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": VOLLEYBALL_MEN_EVENT,
                "approval_status": "approved",
            }
        ],
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="volleyball.pdf",
    )

    assert page_count == 2
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_write_soccer_scoresheets_pdf_filters_to_soccer(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output()), encoding="utf-8")

    pdf_path, page_count = write_soccer_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        roster_rows=[
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": SOCCER_EVENT,
                "approval_status": "approved",
            }
        ],
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="soccer.pdf",
    )

    assert page_count == 1
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_write_bible_challenge_scoresheets_pdf_filters_to_bible_challenge(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output()), encoding="utf-8")

    pdf_path, page_count = write_bible_challenge_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        roster_rows=[
            {
                "Church Team": "RPC",
                "First Name": "An",
                "Last Name": "Nguyen",
                "Age (at Event)": 17,
                "sport_type": "Bible Challenge",
                "sport_gender": "Mixed",
                "sport_format": "Team",
                "approval_status": "approved",
            }
        ],
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="bible-challenge.pdf",
    )

    assert page_count == 1
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_write_bible_challenge_scoresheets_cycles_one_verse_per_game(tmp_path, monkeypatch):
    schedule_input = _schedule_input()
    schedule_output = _schedule_output()
    for idx in range(2, 16):
        game_id = f"BC-RR-{idx:02d}"
        schedule_input["games"].append(
            {
                "game_id": game_id,
                "event": BIBLE_CHALLENGE_EVENT,
                "stage": "Pool",
                "pool_id": "A",
                "round": idx,
                "team_a_id": "BC::WSD",
                "team_a_label": "WSD",
                "team_b_id": "BC::ANH",
                "team_b_label": "ANH",
                "team_c_id": "BC::LBC",
                "team_c_label": "LBC",
                "duration_minutes": 60,
                "resource_type": "Bible Challenge Station",
            }
        )
        schedule_output["assignments"].append(
            {"game_id": game_id, "resource_id": f"BC-Sun-1-{idx}", "slot": f"Sun-1-18:{idx - 1:02d}"}
        )
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(schedule_input), encoding="utf-8")
    output_path.write_text(json.dumps(schedule_output), encoding="utf-8")
    assigned_references = []

    def fake_render_bible_challenge_scoresheet_page(game, **kwargs):
        assigned_references.append(kwargs["bible_verse"].reference)
        return Image.new("RGB", (100, 100), "white")

    monkeypatch.setattr(scoresheets, "render_bible_challenge_scoresheet_page", fake_render_bible_challenge_scoresheet_page)

    _, page_count = write_bible_challenge_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="bible-challenge.pdf",
    )

    assert page_count == 15
    assert assigned_references[:2] == ["Matthew 13:23", "Colossians 2:6-7"]
    assert assigned_references[13] == "Philippians 3:14"
    assert assigned_references[14] == "Matthew 13:23"


# ---------------------------------------------------------------------------
# --stage / --game-key filtering (Issue #348)
# ---------------------------------------------------------------------------

def _games(stage=None):
    return [
        {"game_key": "BBM-01", "event": BASKETBALL_EVENT, "stage": "Pool"},
        {"game_key": "BBM-QF-1", "event": BASKETBALL_EVENT, "stage": "Quarterfinal"},
        {"game_key": "BBM-Semi-1", "event": BASKETBALL_EVENT, "stage": "Semifinal"},
        {"game_key": "BBM-Final", "event": BASKETBALL_EVENT, "stage": "Final"},
        {"game_key": "BBM-3rd-Place", "event": BASKETBALL_EVENT, "stage": "3rd Place"},
    ]


def test_filter_games_no_filters_returns_unchanged():
    games = _games()
    assert _filter_games(games, "basketball") == games


def test_filter_games_stage_playoff_excludes_pool():
    result = _filter_games(_games(), "basketball", stage="playoff")
    assert {g["game_key"] for g in result} == {
        "BBM-QF-1", "BBM-Semi-1", "BBM-Final", "BBM-3rd-Place",
    }


def test_filter_games_stage_quarterfinal_matches_only_qf():
    result = _filter_games(_games(), "basketball", stage="quarterfinal")
    assert [g["game_key"] for g in result] == ["BBM-QF-1"]


def test_filter_games_stage_3rd_place_alias_maps_to_3rd_stage():
    result = _filter_games(_games(), "basketball", stage="3rd-place")
    assert [g["game_key"] for g in result] == ["BBM-3rd-Place"]


def test_filter_games_game_key_selects_one():
    result = _filter_games(_games(), "basketball", game_keys=["BBM-QF-1"])
    assert [g["game_key"] for g in result] == ["BBM-QF-1"]


def test_filter_games_game_key_multiple_selects_batch():
    result = _filter_games(_games(), "basketball", game_keys=["BBM-QF-1", "BBM-Final"])
    assert {g["game_key"] for g in result} == {"BBM-QF-1", "BBM-Final"}


def test_filter_games_stage_and_game_key_use_intersection():
    """Both filters supplied: only games matching both survive."""
    result = _filter_games(
        _games(),
        "basketball",
        stage="playoff",
        game_keys=["BBM-01", "BBM-QF-1"],
    )
    # BBM-01 is Pool (fails --stage playoff); only BBM-QF-1 satisfies both.
    assert [g["game_key"] for g in result] == ["BBM-QF-1"]


def test_filter_games_unknown_stage_raises_clear_error():
    try:
        _filter_games(_games(), "basketball", stage="bogus")
    except ScoreSheetError as exc:
        assert "Unknown --stage value" in str(exc)
    else:
        raise AssertionError("Expected an unknown --stage value to be rejected.")


def test_filter_games_no_match_raises_clear_error():
    try:
        _filter_games(_games(), "basketball", stage="playoff", game_keys=["BBM-01"])
    except ScoreSheetError as exc:
        assert "No basketball games matched" in str(exc)
    else:
        raise AssertionError("Expected the empty stage+game-key intersection to raise.")


def test_filter_games_missing_game_key_warns_but_returns_found_matches():
    messages = []
    from loguru import logger as loguru_logger
    sink_id = loguru_logger.add(lambda msg: messages.append(msg), level="WARNING")
    try:
        result = _filter_games(_games(), "basketball", game_keys=["BBM-QF-1", "BBM-QF-9"])
    finally:
        loguru_logger.remove(sink_id)

    assert [g["game_key"] for g in result] == ["BBM-QF-1"]
    assert any("BBM-QF-9" in m for m in messages), (
        "Expected a WARNING naming the --game-key that was not found"
    )


def test_write_basketball_scoresheets_pdf_stage_playoff_filter(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input_with_playoffs()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output_with_playoffs()), encoding="utf-8")

    pdf_path, page_count = write_basketball_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="basketball-playoff.pdf",
        stage="playoff",
    )

    # BBM-01 (Pool) is excluded; BBM-QF-1 and BBM-Semi-1 remain.
    assert page_count == 2
    assert pdf_path.exists()


def test_write_basketball_scoresheets_pdf_game_key_filter(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input_with_playoffs()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output_with_playoffs()), encoding="utf-8")

    pdf_path, page_count = write_basketball_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="basketball-one-game.pdf",
        game_keys=["BBM-QF-1"],
    )

    assert page_count == 1
    assert pdf_path.exists()


def test_write_basketball_scoresheets_pdf_game_key_multiple_batch(tmp_path):
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input_with_playoffs()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output_with_playoffs()), encoding="utf-8")

    pdf_path, page_count = write_basketball_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="basketball-batch.pdf",
        game_keys=["BBM-QF-1", "BBM-Semi-1"],
    )

    assert page_count == 2
    assert pdf_path.exists()


def test_write_basketball_scoresheets_pdf_stage_and_game_key_no_match_raises(tmp_path):
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input_with_playoffs()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output_with_playoffs()), encoding="utf-8")

    try:
        write_basketball_scoresheets_pdf(
            input_path,
            output_path,
            tmp_path / "scoresheets",
            score_entry_base_url=SCORE_ENTRY_URL,
            stage="playoff",
            game_keys=["BBM-01"],
        )
    except ScoreSheetError as exc:
        assert "No basketball games matched" in str(exc)
    else:
        raise AssertionError("Expected the empty stage+game-key intersection to raise.")


def test_write_basketball_scoresheets_pdf_no_filter_behavior_unchanged(tmp_path):
    """Existing no-filter behavior is unchanged even with playoff rows present."""
    logo = tmp_path / "logo.png"
    _logo(logo)
    input_path = tmp_path / "approved_schedule_input.json"
    output_path = tmp_path / "approved_schedule_output.json"
    input_path.write_text(json.dumps(_schedule_input_with_playoffs()), encoding="utf-8")
    output_path.write_text(json.dumps(_schedule_output_with_playoffs()), encoding="utf-8")

    pdf_path, page_count = write_basketball_scoresheets_pdf(
        input_path,
        output_path,
        tmp_path / "scoresheets",
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="basketball-all.pdf",
    )

    assert page_count == 3
    assert pdf_path.exists()
