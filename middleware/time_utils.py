from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger

from config import Config, DEFAULT_BUSINESS_TIMEZONE, DEFAULT_WORDPRESS_CREATED_AT_TIMEZONE


def _resolve_zoneinfo(configured_name: str, fallback_name: str, label: str) -> ZoneInfo:
    try:
        return ZoneInfo(configured_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            f"Invalid {label} timezone '{configured_name}'. Falling back to '{fallback_name}'."
        )
        return ZoneInfo(fallback_name)


def get_business_zoneinfo() -> ZoneInfo:
    return _resolve_zoneinfo(
        getattr(Config, "BUSINESS_TIMEZONE", DEFAULT_BUSINESS_TIMEZONE),
        DEFAULT_BUSINESS_TIMEZONE,
        "BUSINESS_TIMEZONE",
    )


def get_wordpress_created_at_zoneinfo() -> ZoneInfo:
    return _resolve_zoneinfo(
        getattr(
            Config,
            "WORDPRESS_CREATED_AT_TIMEZONE",
            DEFAULT_WORDPRESS_CREATED_AT_TIMEZONE,
        ),
        DEFAULT_WORDPRESS_CREATED_AT_TIMEZONE,
        "WORDPRESS_CREATED_AT_TIMEZONE",
    )


def current_business_date() -> date:
    return datetime.now(get_business_zoneinfo()).date()


def parse_wordpress_created_at_to_business_date(value: Any) -> Optional[date]:
    """Convert a WordPress created_at value into the Sports Fest business date.

    WordPress REST responses currently expose ``created_at`` as a naive MySQL
    timestamp string. This helper interprets that timestamp in the configured
    WordPress timezone, then converts it into the Sports Fest business timezone
    before taking the date. If an explicit timezone offset is already present in
    the string, that offset wins.
    """
    text = str(value or "").strip()
    if not text:
        return None

    # A date-only string is already the intended calendar date; do not shift it.
    if len(text) == 10:
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    normalized = text.replace("Z", "+00:00")
    parsed_dt: Optional[datetime] = None

    try:
        parsed_dt = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed_dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed_dt is None:
        return None

    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=get_wordpress_created_at_zoneinfo())

    return parsed_dt.astimezone(get_business_zoneinfo()).date()
