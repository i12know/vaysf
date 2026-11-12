import sys
import os
import shutil
import uuid
from pathlib import Path

import pytest

MIDDLEWARE_DIR = Path(__file__).resolve().parent
TEST_TEMP_DIR = MIDDLEWARE_DIR / "temp" / "pytest-run"
TEST_EXPORT_DIR = MIDDLEWARE_DIR / "temp" / "pytest-export"
LIVE_TEST_ENV = "LIVE_TEST"
LIVE_MUTATION_TESTS_ENV = "LIVE_MUTATION_TESTS"

TEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)
TEST_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("TMP", str(TEST_TEMP_DIR))
os.environ.setdefault("TEMP", str(TEST_TEMP_DIR))
os.environ.setdefault("TMPDIR", str(TEST_TEMP_DIR))
os.environ.setdefault("EXPORT_DIR", str(TEST_EXPORT_DIR))

# Add middleware root to sys.path so tests can import project modules
sys.path.insert(0, str(MIDDLEWARE_DIR))


def _env_flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() == "true"


def require_live_mutation_test(reason: str) -> None:
    """Skip real write tests unless the caller opts in explicitly."""
    if _env_flag(LIVE_TEST_ENV) and not _env_flag(LIVE_MUTATION_TESTS_ENV):
        pytest.skip(
            "LIVE TEST SAFEGUARD: this test writes to real ChMeetings/WordPress data. "
            f"Set {LIVE_MUTATION_TESTS_ENV}=true to run it intentionally. "
            f"Blocked mutation: {reason}"
        )


def pytest_sessionstart(session):
    """Print a loud warning banner whenever pytest points at live systems."""
    if not _env_flag(LIVE_TEST_ENV):
        return

    border = "=" * 100
    if _env_flag(LIVE_MUTATION_TESTS_ENV):
        print(
            f"\n{border}\n"
            f"DANGER: REAL WRITE TESTS ENABLED ({LIVE_TEST_ENV}=true, {LIVE_MUTATION_TESTS_ENV}=true).\n"
            "Pytest may CREATE, UPDATE, DELETE, or EMAIL against real ChMeetings and WordPress data.\n"
            "Proceed only with disposable test data and a cleanup plan you are ready to execute.\n"
            f"{border}\n"
        )
        return

    print(
        f"\n{border}\n"
        f"STOP: {LIVE_TEST_ENV}=true points pytest at REAL ChMeetings + REAL WordPress systems.\n"
        f"{LIVE_MUTATION_TESTS_ENV} is not enabled, so tests that WRITE to ChMeetings or WordPress will be skipped.\n"
        f"Set {LIVE_MUTATION_TESTS_ENV}=true only when you intentionally want real writes.\n"
        f"{border}\n"
    )


@pytest.fixture
def tmp_path():
    """Provide a repo-local tmp_path so tests never depend on system temp permissions."""
    path = TEST_TEMP_DIR / f"pytest-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_person_alias_map(tmp_path, monkeypatch):
    """Mock mode never reads the operator's real person alias map.

    The real map (``data/person_aliases.local.json``) is private, git-ignored
    and present on the operator's machine. Tests that need aliases build their
    own; every other mock-mode test must see "no alias file" whatever ``.env``
    says. Live runs keep the configured map, since they act on real data.
    """
    if _env_flag(LIVE_TEST_ENV):
        return
    from config import Config

    monkeypatch.setattr(
        Config,
        "PERSON_ALIASES_FILE",
        tmp_path / "person_aliases.absent.json",
    )


class _StubPhotoResponse:
    def __init__(self, status_code: int, content_type: str):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


@pytest.fixture(autouse=True)
def _stub_live_photo_head(monkeypatch):
    """LIVE_TEST photo checks never reach a real image host.

    In live mode the individual validator sends ``requests.head`` to each
    participant's photo URL. The tests feed it fixture URLs, and the real image
    server is private (it answers 403), so the result would depend on network
    access rather than on the code. A URL naming a missing or broken photo
    raises a connection error; any other URL is a reachable JPEG. The real
    ChMeetings and WordPress connectors use ``requests.Session`` and are not
    affected.
    """
    if not _env_flag(LIVE_TEST_ENV):
        return
    import requests

    def fake_head(url, *args, **kwargs):
        lowered = str(url).lower()
        if any(marker in lowered for marker in ("not-exist", "nonexistent", "broken")):
            raise requests.ConnectionError(f"stubbed unreachable photo host: {url}")
        return _StubPhotoResponse(200, "image/jpeg")

    monkeypatch.setattr(requests, "head", fake_head)
