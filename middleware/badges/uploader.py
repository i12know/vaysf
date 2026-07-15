"""Upload generated athlete badge PNGs to the WordPress plugin."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests
from loguru import logger
from PIL import Image

from config import Config

BADGE_WIDTH = 1080
BADGE_HEIGHT = 1920
MAX_BADGE_BYTES = 5 * 1024 * 1024
_SAFE_BADGE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.png$")


@dataclass(frozen=True)
class BadgeUploadResult:
    """WordPress badge upload response."""

    filename: str
    url: str
    byte_size: int
    sha256_hash: str


class WordPressBadgeUploader:
    """Small client for the ``/wp-json/vaysf/v1/badges`` upload endpoint."""

    def __init__(self, wp_connector: Optional[Any] = None, session: Optional[requests.Session] = None) -> None:
        self.base_url = (
            getattr(wp_connector, "custom_api_url", None)
            or f"{str(Config.WP_URL).rstrip('/')}/wp-json/vaysf/v1"
        ).rstrip("/")
        self.session = session or requests.Session()

        if wp_connector is not None and getattr(wp_connector, "session", None) is not None:
            self.session.cookies.update(wp_connector.session.cookies)

        self.session.headers.update({
            "X-VAYSF-API-Key": Config.WP_API_KEY or "",
            "Accept": "application/json",
            "User-Agent": "VAYSF-middleware badge-uploader",
        })
        # WordPressConnector sets application/json globally, but multipart uploads
        # need requests to compute their own Content-Type boundary.
        self.session.headers.pop("Content-Type", None)

    def upload_badge(self, badge_path: Path, *, filename: Optional[str] = None) -> BadgeUploadResult:
        """Upload one generated 1080x1920 PNG badge and return its hosted URL."""
        badge_path = Path(badge_path)
        upload_name = filename or badge_path.name
        self._validate_local_badge(badge_path, upload_name)

        with badge_path.open("rb") as handle:
            response = self.session.post(
                f"{self.base_url}/badges",
                data={"filename": upload_name},
                files={"badge": (upload_name, handle, "image/png")},
                timeout=(10, 60),
            )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error(
                f"Badge upload failed filename={upload_name} "
                f"status={getattr(response, 'status_code', 'unknown')}"
            )
            raise exc

        payload = response.json()
        result = BadgeUploadResult(
            filename=str(payload.get("filename") or upload_name),
            url=str(payload.get("url") or ""),
            byte_size=int(payload.get("size") or badge_path.stat().st_size),
            sha256_hash=str(payload.get("sha256") or ""),
        )
        logger.debug(f"Badge uploaded filename={result.filename} bytes={result.byte_size}")
        return result

    @staticmethod
    def _validate_local_badge(badge_path: Path, filename: str) -> None:
        if not badge_path.is_file():
            raise FileNotFoundError(f"Badge PNG not found: {badge_path}")
        if not _SAFE_BADGE_FILENAME_RE.match(filename):
            raise ValueError("Badge filename must be a safe .png filename.")
        size = badge_path.stat().st_size
        if size <= 0:
            raise ValueError("Badge PNG is empty.")
        if size > MAX_BADGE_BYTES:
            raise ValueError(
                f"Badge PNG is too large ({size} bytes; max {MAX_BADGE_BYTES})."
            )

        with Image.open(badge_path) as image:
            if image.format != "PNG":
                raise ValueError("Badge file must be a PNG image.")
            if image.size != (BADGE_WIDTH, BADGE_HEIGHT):
                raise ValueError(
                    f"Badge PNG must be {BADGE_WIDTH}x{BADGE_HEIGHT}; got {image.size[0]}x{image.size[1]}."
                )
