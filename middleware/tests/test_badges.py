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
    QR_CARD,
    QR_TAG_TOP,
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
from badges.uploader import BadgeUploadResult, WordPressBadgeUploader


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
        "consent_status": True,
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


def test_missing_consent_turns_name_card_red(generator):
    img = generator.render(_participant(consent_status=False), photo_bytes=None)
    name_card_pixel = img.getpixel((CARD_X0 + 40, CARD_FIRST_Y + 35))
    sport_card_pixel = img.getpixel((CARD_X0 + 40, CARD_FIRST_Y + CARD_H + 40))

    assert name_card_pixel[0] > 130
    assert name_card_pixel[1] < 70
    assert name_card_pixel[2] < 80
    assert sport_card_pixel[2] > sport_card_pixel[0]


def test_missing_consent_name_text_stays_white(generator, monkeypatch):
    fills = []

    def capture_text(*args, **kwargs):
        fills.append(kwargs["fill"])

    monkeypatch.setattr(generator, "_draw_text_autoshrink", capture_text)
    draw = ImageDraw.Draw(Image.new("RGBA", (1080, 1920)))
    generator._draw_cards(draw, _participant(consent_status=False))

    assert fills[0] == (246, 249, 255, 255)


def test_qr_tags_show_minor_and_missing_consent(generator, monkeypatch):
    drawn = []

    def capture_text(draw, text, **kwargs):
        drawn.append((text, kwargs["box"], kwargs["fill"]))

    monkeypatch.setattr(generator, "_draw_text_autoshrink", capture_text)
    draw = ImageDraw.Draw(Image.new("RGBA", (1080, 1920)))
    generator._draw_qr_tags(
        draw,
        _participant(consent_status=False, minor_status=True, age_at_event=17),
    )

    assert [item[0] for item in drawn] == ["Minor", "Consent Form Needed"]
    assert all(item[2] == (0, 0, 0, 255) for item in drawn)
    assert drawn[0][1][1] == QR_TAG_TOP


def test_qr_tags_omit_adult_consent_complete(generator, monkeypatch):
    drawn = []
    monkeypatch.setattr(
        generator,
        "_draw_text_autoshrink",
        lambda draw, text, **kwargs: drawn.append(text),
    )
    draw = ImageDraw.Draw(Image.new("RGBA", (1080, 1920)))

    generator._draw_qr_tags(
        draw,
        _participant(consent_status=True, minor_status=False, age_at_event=18),
    )

    assert drawn == []


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


def test_qr_card_does_not_draw_caption_text(generator, monkeypatch):
    def fail_if_caption_is_drawn(*args, **kwargs):
        raise AssertionError("QR card should not draw caption text")

    monkeypatch.setattr(generator, "_draw_text_autoshrink", fail_if_caption_is_drawn)
    canvas = Image.new("RGBA", (1080, 1920))
    draw = ImageDraw.Draw(canvas)

    generator._draw_qr_block(
        canvas,
        draw,
        "3615924",
        _participant(consent_status=True, minor_status=False),
    )


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


def test_badge_name_uses_display_first_name_when_present(generator):
    rows = generator._card_rows(
        _participant(
            first_name="Ngoc",
            display_first_name="Khoa",
            full_name="Ngoc Le",
            last_name="Le",
        )
    )

    assert rows[0][0] == "Khoa Le"


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

def _make_runner(participants, generator, person_photo=None, badge_uploader=None):
    chm = MagicMock()
    wp = MagicMock()
    wp.get_participants.return_value = participants
    wp.get_churches.return_value = [{"church_code": "RPC", "church_name": "Redemption Point"}]
    chm.get_person.return_value = {"id": "3139537", "photo": person_photo,
                                   "first_name": "An", "last_name": "Le"}
    return BadgeRunner(chm, wp, generator, badge_uploader=badge_uploader), chm, wp


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


def test_runner_uploads_rendered_badge(generator):
    uploader = MagicMock()
    runner, chm, wp = _make_runner([_participant()], generator, badge_uploader=uploader)

    assert runner.run(force=True, upload=True) is True

    pngs = list(generator.output_dir.glob("*.png"))
    assert len(pngs) == 1
    uploader.upload_badge.assert_called_once_with(pngs[0])


def test_runner_requires_upload_for_chmeetings_badge_url(generator):
    runner, chm, wp = _make_runner([_participant()], generator)

    assert runner.run(write_chmeetings_badge_url=True) is False

    chm.get_member_fields.assert_not_called()
    chm.update_person.assert_not_called()


def test_runner_writes_uploaded_badge_url_to_chmeetings(generator):
    uploader = MagicMock()
    uploader.upload_badge.return_value = BadgeUploadResult(
        filename="RPC_3139537_abcd1234.png",
        url="https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png",
        byte_size=12345,
        sha256_hash="abc123",
    )
    runner, chm, wp = _make_runner([_participant()], generator, badge_uploader=uploader)
    chm.get_member_fields.return_value = [
        {"field_name": "Sports Fest Badge URL", "field_id": 98765, "field_type": "text"}
    ]
    chm.get_person.return_value = {
        "id": "3139537",
        "photo": None,
        "first_name": "An",
        "last_name": "Le",
        "additional_fields": [
            {"field_id": 1281851, "field_type": "dropdown", "selected_option_id": 199354},
        ],
    }
    chm.update_person.return_value = True

    assert runner.run(force=True, upload=True, write_chmeetings_badge_url=True) is True

    chm.update_person.assert_called_once()
    args, kwargs = chm.update_person.call_args
    assert args[:3] == ("3139537", "An", "Le")
    additional_fields = args[3]
    assert {field["field_id"] for field in additional_fields} == {1281851, 98765}
    badge_field = next(field for field in additional_fields if field["field_id"] == 98765)
    assert badge_field["field_type"] == "text"
    assert badge_field["value"] == (
        "https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png"
        "<IMG SRC=https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png>"
    )
    assert kwargs["extra_person_data"] == chm.get_person.return_value


def test_badge_url_profile_value_appends_chmeetings_img_tag():
    url = "https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png"

    assert BadgeRunner._badge_url_profile_value(url) == (
        "https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png"
        "<IMG SRC=https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png>"
    )


def test_runner_dry_run_upload_writes_and_uploads_nothing(generator):
    uploader = MagicMock()
    runner, chm, wp = _make_runner([_participant()], generator, badge_uploader=uploader)

    assert runner.run(dry_run=True, upload=True) is True

    assert not generator.output_dir.exists() or not list(generator.output_dir.glob("*.png"))
    uploader.upload_badge.assert_not_called()
    chm.get_person.assert_not_called()


def test_badge_uploader_posts_png_without_json_content_type(tmp_path, monkeypatch):
    png_path = tmp_path / "RPC_3139537_abcd1234.png"
    png_path.write_bytes(_png_bytes(size=(1080, 1920)))
    monkeypatch.setattr("badges.uploader.Config.WP_URL", "https://sportsfest.example")
    monkeypatch.setattr("badges.uploader.Config.WP_API_KEY", "secret")

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "filename": png_path.name,
        "url": "https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png",
        "size": png_path.stat().st_size,
        "sha256": "abc123",
    }
    session = MagicMock()
    session.headers = {}
    session.cookies = {}
    session.post.return_value = response

    result = WordPressBadgeUploader(session=session).upload_badge(png_path)

    assert result.filename == png_path.name
    assert result.sha256_hash == "abc123"
    assert "Content-Type" not in session.headers
    assert session.headers["X-VAYSF-API-Key"] == "secret"
    kwargs = session.post.call_args.kwargs
    assert kwargs["data"] == {"filename": png_path.name}
    assert kwargs["files"]["badge"][0] == png_path.name
    assert kwargs["files"]["badge"][2] == "image/png"


def test_badge_uploader_retries_403_with_reencoded_png(tmp_path, monkeypatch):
    png_path = tmp_path / "RPC_3139537_abcd1234.png"
    png_path.write_bytes(_png_bytes(size=(1080, 1920)))
    retry_path = tmp_path / "retry.png"
    retry_path.write_bytes(_png_bytes(color=(90, 40, 180), size=(1080, 1920)))
    monkeypatch.setattr("badges.uploader.Config.WP_URL", "https://sportsfest.example")
    monkeypatch.setattr("badges.uploader.Config.WP_API_KEY", "secret")
    monkeypatch.setattr(
        WordPressBadgeUploader,
        "_reencode_for_firewall_retry",
        staticmethod(lambda badge_path: retry_path),
    )

    forbidden_response = MagicMock()
    forbidden_response.status_code = 403
    forbidden_response.text = "Forbidden"

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {
        "filename": png_path.name,
        "url": "https://sportsfest.example/wp-content/uploads/vaysf/badges/RPC_3139537_abcd1234.png",
        "size": png_path.stat().st_size,
        "sha256": "abc123",
    }

    session = MagicMock()
    session.headers = {}
    session.cookies = {}
    session.post.side_effect = [forbidden_response, ok_response]

    result = WordPressBadgeUploader(session=session).upload_badge(png_path)

    assert result.url.endswith("/RPC_3139537_abcd1234.png")
    assert session.post.call_count == 2
    assert not retry_path.exists()


def test_badge_uploader_rejects_non_png_filename(tmp_path):
    png_path = tmp_path / "RPC_3139537_abcd1234.jpg"
    png_path.write_bytes(_png_bytes(size=(1080, 1920)))

    with pytest.raises(ValueError, match="safe .png"):
        WordPressBadgeUploader._validate_local_badge(png_path, png_path.name)


def test_badge_uploader_rejects_wrong_dimensions(tmp_path):
    png_path = tmp_path / "RPC_3139537_abcd1234.png"
    png_path.write_bytes(_png_bytes(size=(400, 500)))

    with pytest.raises(ValueError, match="1080x1920"):
        WordPressBadgeUploader._validate_local_badge(png_path, png_path.name)


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


def test_runner_backfills_consent_status_from_chmeetings_value(generator):
    participant = _participant()
    participant.pop("consent_status")
    runner, chm, wp = _make_runner(
        [participant],
        generator,
        person_photo=None,
    )
    chm.get_person.return_value = {
        "id": "3139537",
        "photo": None,
        "birth_date": "2008-07-18",
        "additional_fields": [
            {
                "field_name": "Completion Check List",
                "value": "2. Consent Form Signed by Self or Parents",
            }
        ],
    }

    runner._fetch_photo_bytes(participant)

    assert participant["consent_status"] is True
    assert participant["age_at_event"] == 18
    assert participant["minor_status"] is False


def test_runner_uses_chmeetings_nickname_for_badge_display_name(generator):
    participant = _participant(first_name="Ngoc", last_name="Le")
    runner, chm, wp = _make_runner([participant], generator, person_photo=None)
    chm.get_person.return_value = {
        "id": "3139537",
        "nick_name": "Khoa",
        "photo": None,
        "birth_date": "2000-01-01",
        "additional_fields": [],
    }

    runner._fetch_photo_bytes(participant)

    assert participant["first_name"] == "Ngoc"
    assert participant["display_first_name"] == "Khoa"


def test_runner_backfills_missing_consent_from_chmeetings_options(generator):
    participant = _participant(consent_status=True)
    runner, chm, wp = _make_runner(
        [participant],
        generator,
        person_photo=None,
    )
    chm.get_person.return_value = {
        "id": "3139537",
        "photo": None,
        "birth_date": "2008-12-31",
        "additional_fields": [
            {
                "field_name": "Completion Check List",
                "value": "",
                "selected_option_ids": [199608],
            }
        ],
    }

    runner._fetch_photo_bytes(participant)

    assert participant["consent_status"] is False
    assert participant["age_at_event"] == 17
    assert participant["minor_status"] is True


def test_runner_age_at_event_matches_church_export_boundary(mocker):
    mocker.patch("badges.runner.Config.SPORTS_FEST_DATE", "2026-07-18")

    assert BadgeRunner._age_at_event("2008-07-18") == 18
    assert BadgeRunner._age_at_event("2008-12-31") == 17
    assert BadgeRunner._age_at_event("") is None
