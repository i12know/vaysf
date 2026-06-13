"""
Unit tests for the athlete badge generator (Issue #77).

All tests run in mock mode (no real API calls, no network). Photos are
synthesised in-memory; connectors are MagicMocks.
"""
import io

import pytest
from unittest.mock import MagicMock

from PIL import Image, ImageFont

from badges.generator import (
    QR_CAPTION,
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


def test_event_rows_hide_empty(generator):
    # Only primary present -> exactly one event row.
    p = _participant(primary_sport="Tennis", secondary_sport="", other_events="")
    assert generator._event_rows(p) == ["Primary: Tennis"]
    # Unselected/NA sentinel values are treated as empty.
    p2 = _participant(primary_sport="Unselected/NA", secondary_sport="Badminton", other_events="")
    assert generator._event_rows(p2) == ["Secondary: Badminton"]


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
