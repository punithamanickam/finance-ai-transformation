import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import settings  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    from src.calculations.engine import CalculationEngine

    return CalculationEngine()


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    import src.governance.audit as audit

    monkeypatch.setattr(audit, "AUDIT_LOG", tmp_path / "audit_log.jsonl")
    monkeypatch.setattr(settings, "AUDIT_DIR", tmp_path)
    yield tmp_path / "audit_log.jsonl"


requires_index = pytest.mark.skipif(not settings.CHUNKS_JSONL.exists(),
                                    reason="retrieval corpus not built - run python -m scripts.build_financial_model")
