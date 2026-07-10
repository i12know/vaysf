"""
Unit tests for the athlete badge generator (Issue #77).

All tests run in mock mode (no real API calls, no network). Photos are
synthesised in-memory; connectors are MagicMocks.
"""
import io

import pytest
import requests
from unittest.mock import MagicMock

from PIL import Image, ImageDraw, ImageFont

from badges.generator import (
    CARD_H,
    CARD_FIRST_Y,
    CARD_OTHER_H,
    CARD_X0,
    CARD_X1,
    CHURCH_CODE_CX,
    PHOTO_LEFT,
    PHOTO_TOP,
    QR_CAPTION,
    QR_CARD,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
    SAFE_TOP,
    TAGLINE_BOX,
    THEME_BOX,
    BadgeGenerator,
    _ascii_initials,
    _resolve_font_path,
)
from badges.runner import BadgeRunner


# ── Fixtures / helpers ─────────────────────────────────────────────────────────

def _png_bytes(color=(80, 160, 200), size=(400, 500)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def generator(tmp_path):
    return BadgeGenerator(
        output_dir=tmp_path / "badges",
        filename_salt="test-only-badge-salt",
    )


def _participant(**overrides):
    base = {
        "chmeetings_id": "3139537",
        "church_code": "RPC",
        "church_name": "Redemption Point",
        "first_name": "An",
        "last_name": "Le",
        "approval_status": "approved",
        "primary_sport": "Tennis",
    }
    base.update(overrides)
    return base


# ── BadgeGenerator: rendering ───────────────────────────────────────────────────

def test_render_produces_portrait_png(generator):
    img = generator.render(_participant(), photo_bytes=_png_bytes())
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


def test_render_to_file_writes_png(generator):
    out = generator.render_to_file(_participant(), photo_bytes=_png_bytes(), force=True)
    assert out.exists()
    assert Image.open(out).size == (1080, 1920)


def test_render_to_file_can_use_church_subfolders(tmp_path):
    generator = BadgeGenerator(
        output_dir=tmp_path / "exports",
        filename_salt="test-only-badge-salt",
        church_subdirs=True,
    )

    out = generator.render_to_file(_participant(), photo_bytes=_png_bytes(), force=True)

    assert out.parent == tmp_path / "exports" / "RPC" / "badges"
    assert out.name.startswith("RPC_3139537_")
    assert out.with_suffix(".png.sha256").exists()


def test_template_artwork_area_is_not_overpainted(tmp_path):
    sentinel = (9, 24, 64, 255)
    template_path = tmp_path / "dark-template.png"
    Image.new("RGBA", (1080, 1920), sentinel).save(template_path)
    generator = BadgeGenerator(
        template_path=template_path,
        output_dir=tmp_path / "badges",
        filename_salt="test-only-badge-salt",
    )

    img = generator.render(_participant(), photo_bytes=None)

    tagline_center = (
        (TAGLINE_BOX[0] + TAGLINE_BOX[2]) // 2,
        (TAGLINE_BOX[1] + TAGLINE_BOX[3]) // 2,
    )
    theme_center = (
        (THEME_BOX[0] + THEME_BOX[2]) // 2,
        (THEME_BOX[1] + THEME_BOX[3]) // 2,
    )
    assert img.getpixel(tagline_center) == sentinel
    assert img.getpixel(theme_center) == sentinel


def test_event_cards_render_as_dark_mode_surfaces(generator):
    img = generator.render(_participant(), photo_bytes=None)
    card_pixel = img.getpixel((CARD_X0 + 430, CARD_FIRST_Y + CARD_H // 2))

    assert card_pixel[0] < 40
    assert card_pixel[1] < 60
    assert card_pixel[2] < 100


def test_event_card_content_uses_bold_font(generator, monkeypatch):
    roles = []

    def capture_text(*args, **kwargs):
        roles.append(kwargs["role"])

    monkeypatch.setattr(generator, "_draw_text_autoshrink", capture_text)
    draw = ImageDraw.Draw(Image.new("RGBA", (1080, 1920)))

    generator._draw_card(draw, "An Le", "#3139537", CARD_FIRST_Y, CARD_H, False)

    assert "bold" in roles


def test_long_vietnamese_name_autoshrinks_and_renders(generator):
    # A long name with diacritics must still produce a valid 1080x1920 image
    # (auto-shrink keeps it inside the safe zone rather than overflowing).
    p = _participant(first_name="Nguyễn", last_name="Hoàng Phương Anh Quốc Việt")
    img = generator.render(p, photo_bytes=None)
    assert img.size == (1080, 1920)


def test_missing_photo_uses_initials_fallback(generator):
    # No photo bytes -> the badge still renders (initials placeholder path).
    img = generator.render(_participant(first_name="An", last_name="Le"), photo_bytes=None)
    assert img.size == (1080, 1920)


def test_corrupt_photo_falls_back_without_raising(generator):
    img = generator.render(_participant(), photo_bytes=b"not-a-real-image")
    assert img.size == (1080, 1920)


def test_deterministic_filename(generator):
    p = _participant()
    assert generator.filename_for(p) == generator.filename_for(dict(p))
    name = generator.filename_for(p)
    assert name.startswith("RPC_3139537_")
    assert name.endswith(".png")


def test_filename_requires_chmeetings_id(generator):
    with pytest.raises(ValueError, match="chmeetings_id"):
        generator.filename_for(_participant(chmeetings_id=None, participant_id=42))


def test_filename_salt_must_be_explicit_and_private(tmp_path, monkeypatch):
    monkeypatch.delenv("BADGE_FILENAME_SALT", raising=False)
    with pytest.raises(ValueError, match="BADGE_FILENAME_SALT"):
        BadgeGenerator(output_dir=tmp_path / "badges")


def test_render_to_file_skips_existing_without_force(generator):
    p = _participant()
    first = generator.render_to_file(p, photo_bytes=_png_bytes(), force=True)
    mtime = first.stat().st_mtime_ns
    # Without force, an existing current file is not rewritten.
    again = generator.render_to_file(p, photo_bytes=_png_bytes())
    assert again == first
    assert again.stat().st_mtime_ns == mtime


def test_render_to_file_refreshes_when_badge_data_changes(generator):
    p = _participant()
    out = generator.render_to_file(p, photo_bytes=_png_bytes(), force=True)
    original = out.read_bytes()

    p["first_name"] = "Updated"
    p["primary_sport"] = "Basketball"
    refreshed = generator.render_to_file(p, photo_bytes=_png_bytes())

    assert refreshed == out
    assert refreshed.read_bytes() != original
    assert generator.last_write_skipped is False


def test_render_to_file_refreshes_when_photo_changes(generator):
    p = _participant()
    out = generator.render_to_file(
        p,
        photo_bytes=_png_bytes(color=(80, 160, 200)),
        force=True,
    )
    original = out.read_bytes()

    generator.render_to_file(
        p,
        photo_bytes=_png_bytes(color=(200, 80, 120)),
    )

    assert out.read_bytes() != original
    assert generator.last_write_skipped is False


def test_resolved_fonts_render_vietnamese_glyphs():
    for role in ("bold", "regular", "mono"):
        path = _resolve_font_path(role)
        assert path is not None
        font = ImageFont.truetype(str(path), 48)
        assert bytes(font.getmask("Nguyễn Hồ Phạm Trần Lê Đinh")) != bytes(
            font.getmask("\ufffd" * 20)
        )


def test_qr_caption_marks_placeholder_as_not_for_check_in():
    assert QR_CAPTION == "ID QR - not for check-in"


def test_wireframe_geometry_stays_inside_safe_area():
    assert TAGLINE_BOX[1] >= SAFE_TOP
    assert TAGLINE_BOX[0] >= SAFE_LEFT
    assert TAGLINE_BOX[2] <= SAFE_RIGHT
    assert THEME_BOX[0] >= SAFE_LEFT
    assert THEME_BOX[2] <= SAFE_RIGHT
    assert PHOTO_LEFT >= SAFE_LEFT
    assert PHOTO_TOP > THEME_BOX[3]
    assert QR_CARD[0] >= SAFE_LEFT
    assert QR_CARD[2] <= SAFE_RIGHT
    assert CARD_X0 >= SAFE_LEFT
    assert CARD_X1 <= SAFE_RIGHT
    assert CARD_FIRST_Y + (3 * 105) + (3 * 12) + CARD_OTHER_H <= SAFE_BOTTOM


def test_church_code_is_centered_under_photo():
    from badges.generator import PHOTO_DIAM

    assert CHURCH_CODE_CX == PHOTO_LEFT + PHOTO_DIAM // 2


def test_event_rows_hide_empty(generator):
    # Only primary present -> name row + primary row (no secondary/others).
    p = _participant(primary_sport="Tennis", secondary_sport="", other_events="")
    rows = generator._card_rows(p)
    texts = [r[0] for r in rows]
    tags  = [r[1] for r in rows]
    assert "Tennis" in texts
    assert "Primary" in tags
    assert "2ndary" not in tags
    assert "Others" not in tags

    # Unselected/NA sentinel values are treated as empty.
    p2 = _participant(primary_sport="Unselected/NA", secondary_sport="Badminton", other_events="")
    rows2 = generator._card_rows(p2)
    texts2 = [r[0] for r in rows2]
    tags2  = [r[1] for r in rows2]
    assert "Badminton" in texts2
    assert "2ndary" in tags2
    assert "Primary" not in tags2


def test_team_sport_does_not_show_stale_racquet_partner(generator):
    p = _participant(
        primary_sport="Volleyball - Men Team",
        primary_format="",
        primary_partner="Timothy Dao",
        secondary_sport="Pickleball",
        secondary_format="Men Double",
        secondary_partner="Timothy Dao",
    )

    rows = generator._card_rows(p)
    assert ("Volleyball - Men Team", "Primary", False) in rows
    assert ("Pickleball (Men Double) w/ Timothy Dao", "2ndary", False) in rows


def test_ascii_initials_strips_accents():
    assert _ascii_initials("Nguyễn", "Hoàng") == "NH"
    assert _ascii_initials("", "") == "?"


# ── BadgeRunner: orchestration ──────────────────────────────────────────────────

def _make_runner(participants, generator, person_photo=None):
    chm = MagicMock()
    wp = MagicMock()
    wp.get_participants.return_value = participants
    wp.get_churches.return_value = [{"church_code": "RPC", "church_name": "Redemption Point"}]
    chm.get_person.return_value = {"id": "3139537", "photo": person_photo,
                                   "first_name": "An", "last_name": "Le"}
    return BadgeRunner(chm, wp, generator), chm, wp


def test_runner_renders_approved(generator):
    runner, chm, wp = _make_runner([_participant()], generator)
    ok = runner.run(force=True)
    assert ok is True
    # One PNG written for the one approved athlete.
    assert len(list(generator.output_dir.glob("*.png"))) == 1


def test_runner_filters_out_non_approved(generator):
    parts = [_participant(), _participant(chmeetings_id="999", approval_status="pending")]
    runner, chm, wp = _make_runner(parts, generator)
    runner.run(force=True)
    pngs = list(generator.output_dir.glob("*.png"))
    assert len(pngs) == 1
    assert any("3139537" in p.name for p in pngs)


def test_runner_uses_approval_only_when_payment_status_is_unreliable(generator):
    participant = _participant(payment_status="pending")
    runner, chm, wp = _make_runner([participant], generator)

    assert runner.run(force=True) is True
    assert len(list(generator.output_dir.glob("*.png"))) == 1


def test_runner_skips_approved_participant_without_chmeetings_id(generator):
    participant = _participant(
        participant_id=42,
        chmeetings_id=None,
    )
    runner, chm, wp = _make_runner([participant], generator)

    assert runner.run(force=True) is True
    assert not list(generator.output_dir.glob("*.png"))
    chm.get_person.assert_not_called()


def test_runner_dry_run_writes_nothing(generator):
    runner, chm, wp = _make_runner([_participant()], generator)
    ok = runner.run(dry_run=True)
    assert ok is True
    assert not generator.output_dir.exists() or not list(generator.output_dir.glob("*.png"))
    # Dry run must not download photos.
    chm.get_person.assert_not_called()


def test_runner_church_filter(generator):
    parts = [
        _participant(chmeetings_id="1", church_code="RPC"),
        _participant(chmeetings_id="2", church_code="ORN"),
    ]
    runner, chm, wp = _make_runner(parts, generator)
    runner.run(church_code="orn", force=True)
    pngs = list(generator.output_dir.glob("*.png"))
    assert len(pngs) == 1
    assert pngs[0].name.startswith("ORN_2_")


def test_runner_chm_id_scope_queries_single(generator):
    runner, chm, wp = _make_runner([_participant()], generator)
    runner.run(chm_id="3139537", force=True)
    wp.get_participants.assert_called_with({"chmeetings_id": "3139537"})


def test_photo_download_uses_chmeetings_first(generator, mocker):
    runner, chm, wp = _make_runner(
        [_participant(photo_url="https://wp.example/photo.jpg")],
        generator,
        person_photo="https://chm.example/photo.jpg",
    )
    response = MagicMock()
    response.content = _png_bytes()
    response.raise_for_status.return_value = None
    get = mocker.patch("badges.runner.requests.get", return_value=response)

    result = runner._fetch_photo_bytes(
        _participant(photo_url="https://wp.example/photo.jpg")
    )

    assert result == response.content
    get.assert_called_once_with(
        "https://chm.example/photo.jpg",
        timeout=(5, 20),
    )


def test_photo_download_falls_back_to_wordpress_after_chm_failure(
    generator, mocker
):
    runner, chm, wp = _make_runner(
        [_participant(photo_url="https://wp.example/photo.jpg")],
        generator,
        person_photo="https://chm.example/broken.jpg",
    )
    wp_response = MagicMock()
    wp_response.content = _png_bytes(color=(10, 20, 30))
    wp_response.raise_for_status.return_value = None

    def get_photo(url, **kwargs):
        if "chm.example" in url:
            raise requests.ConnectionError("broken")
        return wp_response

    get = mocker.patch("badges.runner.requests.get", side_effect=get_photo)
    result = runner._fetch_photo_bytes(
        _participant(photo_url="https://wp.example/photo.jpg")
    )

    assert result == wp_response.content
    assert [call.args[0] for call in get.call_args_list] == [
        "https://chm.example/broken.jpg",
        "https://wp.example/photo.jpg",
    ]


def test_photo_download_falls_back_when_chm_bytes_are_not_an_image(
    generator, mocker
):
    runner, chm, wp = _make_runner(
        [_participant(photo_url="https://wp.example/photo.jpg")],
        generator,
        person_photo="https://chm.example/not-image.jpg",
    )
    bad_response = MagicMock()
    bad_response.content = b"<html>not an image</html>"
    bad_response.raise_for_status.return_value = None
    good_response = MagicMock()
    good_response.content = _png_bytes()
    good_response.raise_for_status.return_value = None
    get = mocker.patch(
        "badges.runner.requests.get",
        side_effect=[bad_response, good_response],
    )

    result = runner._fetch_photo_bytes(
        _participant(photo_url="https://wp.example/photo.jpg")
    )

    assert result == good_response.content
    assert get.call_count == 2


def test_photo_logging_does_not_include_profile_urls(generator, mocker):
    runner, chm, wp = _make_runner(
        [_participant(photo_url="https://wp.example/private-token")],
        generator,
        person_photo="https://chm.example/private-token",
    )
    response = MagicMock()
    response.content = _png_bytes()
    response.raise_for_status.return_value = None
    mocker.patch("badges.runner.requests.get", return_value=response)
    log = mocker.patch("badges.runner.logger")

    runner._fetch_photo_bytes(
        _participant(photo_url="https://wp.example/private-token")
    )

    messages = " ".join(
        str(call.args[0])
        for call in log.info.call_args_list + log.warning.call_args_list
    )
    assert "https://" not in messages
