import os
import sys
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config
from time_utils import current_business_date, parse_wordpress_created_at_to_business_date


def test_parse_wordpress_created_at_converts_utc_to_business_date(mocker):
    mocker.patch.object(Config, "WORDPRESS_CREATED_AT_TIMEZONE", "UTC")
    mocker.patch.object(Config, "BUSINESS_TIMEZONE", "America/Los_Angeles")

    parsed = parse_wordpress_created_at_to_business_date("2026-05-17 01:30:00")

    assert parsed == datetime.date(2026, 5, 16)


def test_parse_wordpress_created_at_preserves_date_only_string(mocker):
    mocker.patch.object(Config, "WORDPRESS_CREATED_AT_TIMEZONE", "UTC")
    mocker.patch.object(Config, "BUSINESS_TIMEZONE", "America/Los_Angeles")

    parsed = parse_wordpress_created_at_to_business_date("2026-05-16")

    assert parsed == datetime.date(2026, 5, 16)


def test_current_business_date_uses_configured_timezone(mocker):
    fake_now = datetime.datetime(2026, 5, 17, 0, 30, tzinfo=datetime.timezone.utc)

    class FakeDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now.replace(tzinfo=None)
            return fake_now.astimezone(tz)

    mocker.patch.object(Config, "BUSINESS_TIMEZONE", "America/Los_Angeles")
    mocker.patch("time_utils.datetime", FakeDateTime)

    assert current_business_date() == datetime.date(2026, 5, 16)
