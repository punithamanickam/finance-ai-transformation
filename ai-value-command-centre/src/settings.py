"""Central configuration: paths and runtime settings only. No financial numbers live here."""
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
SYNTHETIC_DIR = DATA_DIR / "synthetic"
PUBLIC_DIR = DATA_DIR / "public"
HPE_DOCS_DIR = PUBLIC_DIR / "hpe_documents"
HPE_SOURCES_CSV = PUBLIC_DIR / "hpe_sources.csv"
HPE_PRODUCTS_CSV = PUBLIC_DIR / "hpe_products.csv"
HPE_FINANCIALS_JSON = PUBLIC_DIR / "hpe_financials.json"
HPE_AI_FACTS_JSON = PUBLIC_DIR / "hpe_ai_facts.json"
RUNTIME_DIR = DATA_DIR / "runtime"  # git-ignored: SQLite DB, audit log
WEB_DIR = PROJECT_ROOT / "web"
REPORTS_DIR = PROJECT_ROOT / "reports"
DOCS_DIR = PROJECT_ROOT / "docs"

# SQLite by default so the project runs with no services; set DATABASE_URL for PostgreSQL, e.g.
# postgresql+psycopg://avcc:avcc@localhost:5432/avcc
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{RUNTIME_DIR / 'avcc.db'}")

# Signing key for API session tokens. Always set it in production; the dev default is per-process and random.
SECRET_KEY = os.getenv("AVCC_SECRET_KEY", "")
TOKEN_TTL_SECONDS = int(os.getenv("AVCC_TOKEN_TTL_SECONDS", "28800"))
# Demo accounts share one password so the prototype runs locally; override it outside a demo.
DEMO_PASSWORD = os.getenv("AVCC_DEMO_PASSWORD", "demo")

# LLM provider: "auto" (Anthropic if credentials exist, else offline) | "anthropic" | "offline"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")

SYNTHETIC_SEED = int(os.getenv("AVCC_SEED", "20260925"))
ENGINE_VERSION = "1.0.0"

SYNTHETIC_LABEL = "SYNTHETIC: demonstration data for a fictional enterprise, not HPE or any company's actual data"
PUBLIC_LABEL = "PUBLIC: publicly available HPE information, cited to source"
