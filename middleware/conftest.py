import sys
import os
import shutil
import uuid
from pathlib import Path

import pytest

MIDDLEWARE_DIR = Path(__file__).resolve().parent
TEST_TEMP_DIR = MIDDLEWARE_DIR / "temp" / "pytest-run"
TEST_EXPORT_DIR = MIDDLEWARE_DIR / "temp" / "pytest-export"

TEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)
TEST_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("TMP", str(TEST_TEMP_DIR))
os.environ.setdefault("TEMP", str(TEST_TEMP_DIR))
os.environ.setdefault("TMPDIR", str(TEST_TEMP_DIR))
os.environ.setdefault("EXPORT_DIR", str(TEST_EXPORT_DIR))

# Add middleware root to sys.path so tests can import project modules
sys.path.insert(0, str(MIDDLEWARE_DIR))


@pytest.fixture
def tmp_path():
    """Provide a repo-local tmp_path so tests never depend on system temp permissions."""
    path = TEST_TEMP_DIR / f"pytest-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    yield path
    shutil.rmtree(path, ignore_errors=True)
