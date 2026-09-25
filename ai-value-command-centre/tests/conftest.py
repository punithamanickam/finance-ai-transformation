"""Tests run against a throw-away SQLite database built from the committed synthetic CSVs and public sources."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="avcc-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/avcc_test.db"
os.environ["LLM_PROVIDER"] = "offline"
os.environ["AVCC_SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402

from src.db.database import build_database  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    return build_database()


@pytest.fixture(scope="session")
def ctx(database):
    from src.agents.orchestrator import context_for

    return context_for(None)
