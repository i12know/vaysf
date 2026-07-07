from pathlib import Path
from unittest.mock import MagicMock

from photo_repair import (
    download_profile_photo_url,
    upload_person_photo,
    validate_profile_photo_file,
)


def _write_png(path: Path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"profile-photo")


def test_validate_profile_photo_file_accepts_supported_png(tmp_path):
    photo = tmp_path / "athlete.png"
    _write_png(photo)

    result = validate_profile_photo_file(str(photo))

    assert result["ok"] is True
    assert result["content_type"] == "image/png"
    assert result["size_bytes"] == photo.stat().st_size


def test_validate_profile_photo_file_rejects_non_image(tmp_path):
    photo = tmp_path / "athlete.png"
    photo.write_text("not really an image", encoding="utf-8")

    result = validate_profile_photo_file(str(photo))

    assert result["ok"] is False
    assert "signature" in result["error"]


def test_upload_person_photo_dry_run_validates_without_api_calls(tmp_path):
    photo = tmp_path / "athlete.png"
    _write_png(photo)
    connector = MagicMock()

    summary = upload_person_photo(
        "999001",
        photo_file=str(photo),
        dry_run=True,
        connector=connector,
    )

    assert summary["validated"] is True
    assert summary["uploaded"] is False
    connector.authenticate.assert_not_called()
    connector.upload_person_photo.assert_not_called()


def test_upload_person_photo_execute_uploads_and_confirms(tmp_path):
    photo = tmp_path / "athlete.png"
    _write_png(photo)
    connector = MagicMock()
    connector.authenticate.return_value = True
    connector.get_person.side_effect = [
        {"id": "999001", "photo": ""},
        {"id": "999001", "photo": "https://chm.example/photo.jpg"},
    ]
    connector.upload_person_photo.return_value = {
        "id": "999001",
        "photo": "https://chm.example/photo.jpg",
    }

    summary = upload_person_photo(
        "999001",
        photo_file=str(photo),
        dry_run=False,
        execute=True,
        connector=connector,
    )

    assert summary["uploaded"] is True
    assert summary["confirmed_photo"] is True
    assert summary["already_had_photo"] is False
    connector.authenticate.assert_called_once()
    connector.get_person.assert_any_call("999001")
    connector.upload_person_photo.assert_called_once_with(
        "999001",
        photo,
        content_type="image/png",
    )


def test_upload_person_photo_execute_reports_missing_person(tmp_path):
    photo = tmp_path / "athlete.png"
    _write_png(photo)
    connector = MagicMock()
    connector.authenticate.return_value = True
    connector.get_person.return_value = None

    summary = upload_person_photo(
        "999001",
        photo_file=str(photo),
        dry_run=False,
        execute=True,
        connector=connector,
    )

    assert summary["uploaded"] is False
    assert "not found" in summary["error"]
    connector.upload_person_photo.assert_not_called()


def test_download_profile_photo_url_accepts_chmeetings_cdn(mocker, tmp_path):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"\x89PNG\r\n\x1a\n"
            yield b"profile-photo"

    get = mocker.patch("photo_repair.requests.get", return_value=FakeResponse())

    result = download_profile_photo_url(
        "https://cdne-chmeetings-content.azureedge.net/images/846969/attachments/a/photo.png",
        download_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["content_type"] == "image/png"
    assert Path(result["path"]).exists()
    get.assert_called_once()


def test_download_profile_photo_url_rejects_non_chmeetings_host(tmp_path):
    result = download_profile_photo_url(
        "https://example.com/photo.png",
        download_dir=tmp_path,
    )

    assert result["ok"] is False
    assert "allowed ChMeetings image host" in result["error"]


def test_upload_person_photo_dry_run_accepts_photo_url(mocker, tmp_path):
    photo = tmp_path / "downloaded.png"
    _write_png(photo)
    mocker.patch(
        "photo_repair.download_profile_photo_url",
        return_value={
            "ok": True,
            "path": photo,
            "content_type": "image/png",
            "size_bytes": photo.stat().st_size,
        },
    )
    connector = MagicMock()

    summary = upload_person_photo(
        "999001",
        photo_url="https://cdne-chmeetings-content.azureedge.net/images/846969/attachments/a/photo.png",
        dry_run=True,
        connector=connector,
    )

    assert summary["validated"] is True
    assert summary["source"] == "url"
    assert summary["uploaded"] is False
    connector.authenticate.assert_not_called()
