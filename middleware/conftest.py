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
