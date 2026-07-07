"""Operator-gated ChMeetings profile photo repair helpers."""

from pathlib import Path
import hashlib
import mimetypes
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from loguru import logger
import requests

from chmeetings.backend_connector import ChMeetingsConnector


ALLOWED_PROFILE_PHOTO_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_REPAIR_DOWNLOAD_DIR = Path(__file__).resolve().parent / "temp" / "photo-repair"
ALLOWED_PROFILE_PHOTO_URL_HOSTS = {
    "cdne-chmeetings-content.azureedge.net",
    "chmeetings.blob.core.windows.net",
}


def _sniff_image_content_type(path: Path) -> Optional[str]:
    """Return a conservative image MIME type from file signature bytes."""
    with path.open("rb") as fh:
        header = fh.read(16)

    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_profile_photo_file(
    photo_file: str,
    *,
    max_bytes: int = MAX_PROFILE_PHOTO_BYTES,
) -> Dict[str, Any]:
    """Validate a local profile photo before sending it to ChMeetings."""
    path = Path(photo_file)
    result: Dict[str, Any] = {
        "ok": False,
        "path": path,
        "content_type": None,
        "size_bytes": 0,
        "error": "",
    }

    if not path.exists():
        result["error"] = f"photo file not found: {path}"
        return result
    if not path.is_file():
        result["error"] = f"photo path is not a file: {path}"
        return result

    size_bytes = path.stat().st_size
    result["size_bytes"] = size_bytes
    if size_bytes <= 0:
        result["error"] = "photo file is empty"
        return result
    if size_bytes > max_bytes:
        result["error"] = (
            f"photo file is {size_bytes} bytes; max allowed by this tool is {max_bytes}"
        )
        return result

    guessed_type = mimetypes.guess_type(str(path))[0]
    sniffed_type = _sniff_image_content_type(path)
    if guessed_type not in ALLOWED_PROFILE_PHOTO_TYPES:
        result["error"] = f"unsupported profile photo extension/content type: {guessed_type or 'unknown'}"
        return result
    if sniffed_type is None:
        result["error"] = "photo file signature is not a supported image"
        return result
    if sniffed_type != guessed_type:
        result["error"] = (
            f"photo extension suggests {guessed_type}, but file signature is {sniffed_type}"
        )
        return result

    result["ok"] = True
    result["content_type"] = sniffed_type
    return result


def download_profile_photo_url(
    photo_url: str,
    *,
    download_dir: Path = PHOTO_REPAIR_DOWNLOAD_DIR,
    max_bytes: int = MAX_PROFILE_PHOTO_BYTES,
) -> Dict[str, Any]:
    """Download a ChMeetings-hosted profile photo URL to a local temp file."""
    result: Dict[str, Any] = {
        "ok": False,
        "path": None,
        "content_type": None,
        "size_bytes": 0,
        "error": "",
    }
    parsed = urlparse(photo_url)
    if parsed.scheme != "https":
        result["error"] = "photo URL must use https"
        return result
    if parsed.netloc.lower() not in ALLOWED_PROFILE_PHOTO_URL_HOSTS:
        result["error"] = "photo URL host is not an allowed ChMeetings image host"
        return result

    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    download_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(photo_url.encode("utf-8")).hexdigest()[:16]
    path = download_dir / f"profile-photo-{digest}{suffix}"

    try:
        response = requests.get(photo_url, stream=True, timeout=(5, 30))
        response.raise_for_status()
        total = 0
        with path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    result["error"] = (
                        f"downloaded photo exceeds max allowed size of {max_bytes} bytes"
                    )
                    return result
                fh.write(chunk)
        result["path"] = path
        validation = validate_profile_photo_file(str(path), max_bytes=max_bytes)
        if not validation["ok"]:
            result["error"] = str(validation["error"])
            return result
        result["ok"] = True
        result["content_type"] = validation["content_type"]
        result["size_bytes"] = validation["size_bytes"]
        return result
    except requests.RequestException as exc:
        result["error"] = f"photo URL download failed: {exc}"
        return result


def upload_person_photo(
    person_id: str,
    *,
    photo_file: Optional[str] = None,
    photo_url: Optional[str] = None,
    dry_run: bool = True,
    execute: bool = False,
    connector: Optional[ChMeetingsConnector] = None,
) -> Dict[str, Any]:
    """Validate and optionally upload one local photo to one ChMeetings person.

    This uses the VAY SM church-level ChMeetings API key configured for this
    project. It intentionally does not run inside daily repair flows; operators
    must target a specific person and pass ``execute=True`` for a live upload.
    """
    summary: Dict[str, Any] = {
        "person_id": str(person_id),
        "validated": False,
        "dry_run": dry_run,
        "uploaded": False,
        "confirmed_photo": False,
        "already_had_photo": False,
        "source": "file" if photo_file else "url" if photo_url else "",
        "error": "",
    }

    if bool(photo_file) == bool(photo_url):
        summary["error"] = "provide exactly one of photo_file or photo_url"
        logger.error(f"upload-person-photo: {summary['error']}")
        return summary

    if photo_url:
        download = download_profile_photo_url(photo_url)
        if not download["ok"]:
            summary["error"] = str(download["error"])
            logger.error(f"upload-person-photo: {summary['error']}")
            return summary
        photo_path = Path(download["path"])
        validation = {
            "ok": True,
            "path": photo_path,
            "content_type": download["content_type"],
            "size_bytes": download["size_bytes"],
        }
    else:
        validation = validate_profile_photo_file(str(photo_file))

    if not validation["ok"]:
        summary["error"] = str(validation["error"])
        logger.error(f"upload-person-photo: {summary['error']}")
        return summary

    summary["validated"] = True
    logger.info(
        "upload-person-photo: validated local image "
        f"({validation['content_type']}, {validation['size_bytes']} bytes)"
    )

    if dry_run:
        logger.info(
            f"upload-person-photo dry-run: would upload image to ChMeetings person {person_id}"
        )
        return summary
    if not execute:
        summary["error"] = "execute=True is required for a live upload"
        logger.error("upload-person-photo requires --dry-run or --execute.")
        return summary

    owns_connector = connector is None
    chm_connector = connector or ChMeetingsConnector()

    try:
        if owns_connector:
            chm_connector.__enter__()
        if not chm_connector.authenticate():
            summary["error"] = "Authentication with ChMeetings failed"
            logger.error(summary["error"])
            return summary

        before = chm_connector.get_person(str(person_id))
        if not before:
            summary["error"] = f"ChMeetings person {person_id} was not found"
            logger.error(summary["error"])
            return summary
        summary["already_had_photo"] = bool(before.get("photo"))

        uploaded = chm_connector.upload_person_photo(
            str(person_id),
            validation["path"],
            content_type=str(validation["content_type"]),
        )
        if not uploaded:
            summary["error"] = "ChMeetings photo upload returned no payload"
            logger.error(summary["error"])
            return summary

        summary["uploaded"] = True
        after = chm_connector.get_person(str(person_id))
        summary["confirmed_photo"] = bool(after and after.get("photo"))
        if summary["confirmed_photo"]:
            logger.info(
                f"upload-person-photo: uploaded and confirmed profile photo for person {person_id}"
            )
        else:
            logger.warning(
                f"upload-person-photo: upload returned success, but person {person_id} "
                "does not show a photo on immediate re-read"
            )
        return summary
    finally:
        if owns_connector:
            chm_connector.__exit__(None, None, None)
