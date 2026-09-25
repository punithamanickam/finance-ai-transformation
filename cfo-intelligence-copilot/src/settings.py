"""Central configuration. Paths and runtime settings only - no financial numbers live here."""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional .env support
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SOURCES_DIR = DATA_DIR / "sources"
AUDIT_DIR = DATA_DIR / "audit"
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
REPORTS_DIR = PROJECT_ROOT / "reports"

SOURCE_REGISTRY = DATA_DIR / "source_registry.csv"
METRIC_MAP = CONFIG_DIR / "metric_map.json"
XBRL_FACTS_CSV = PROCESSED_DIR / "xbrl_facts.csv"
FINANCIAL_FACTS_CSV = PROCESSED_DIR / "financial_facts.csv"
CONFLICTS_CSV = PROCESSED_DIR / "source_conflicts.csv"
DB_PATH = PROCESSED_DIR / "cfo_copilot.db"
CHUNKS_JSONL = PROCESSED_DIR / "document_chunks.jsonl"  # derived from raw filings; git-ignored
INDEX_PATH = PROCESSED_DIR / "retrieval_index.pkl"  # git-ignored

COMPANY = os.getenv("CFO_COMPANY", "Microsoft Corporation")
CURRENT_FY = int(os.getenv("CFO_CURRENT_FY", "2026"))

# SEC asks automated clients to identify themselves: "Company Name admin@domain"
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "CFO-Intelligence-Copilot research-prototype admin@example.com")

# LLM provider: "anthropic" (requires ANTHROPIC_API_KEY or an `ant auth login` profile) or "offline"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5")

CALC_ENGINE_VERSION = "1.0.0"
