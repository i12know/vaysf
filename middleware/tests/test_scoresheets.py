import json

from PIL import Image

from scoresheets import (
    BASKETBALL_EVENT,
    LOGO_BOX,
    MAX_ROSTER_ROWS,
    _extract_photo_ref,
    _friendly_location,
    build_roster_index,
    enrich_roster_photos_from_workbook,
    render_basketball_scoresheet_page,
    score_entry_url_for_game,
    write_basketball_scoresheets_pdf,
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
                "event": "Volleyball - Men Team",
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
        ],
        "resources": [],
    }


def _schedule_output():
    return {
        "status": "APPROVED",
        "assignments": [
            {"game_id": "BBM-01", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-16:00"},
            {"game_id": "VBM-01", "resource_id": "GYM-Sat-1-2", "slot": "Sat-1-17:00"},
        ],
        "unscheduled": [],
    }


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


def test_basketball_roster_table_capacity_is_15():
    assert MAX_ROSTER_ROWS == 15


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
            }
        ],
        logo_path=logo,
        score_entry_base_url=SCORE_ENTRY_URL,
        output_filename="basketball.pdf",
    )

    assert page_count == 1
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
