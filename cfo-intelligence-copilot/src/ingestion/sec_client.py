"""Download public filings listed in the source registry from SEC EDGAR.

Raw documents are stored under data/raw/ (git-ignored) - the repository references public sources rather
than redistributing them. SEC fair-access policy: identify yourself via SEC_USER_AGENT and stay well under
10 requests/second.
"""
from __future__ import annotations

import time
from datetime import date

import requests

from src import settings
from src.ingestion.source_registry import load_registry


def download_sources(force: bool = False, include_optional: bool = False) -> list[str]:
    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetched = []
    reg = load_registry()
    wanted = {"yes", "optional"} if include_optional else {"yes"}
    for _, r in reg[reg["ingest"].isin(wanted)].iterrows():
        target = settings.RAW_DIR / r["local_filename"]
        if target.exists() and not force:
            continue
        resp = requests.get(r["source_url"], headers={"User-Agent": settings.SEC_USER_AGENT}, timeout=60)
        resp.raise_for_status()
        target.write_bytes(resp.content)
        fetched.append(f"{r['source_id']} -> {target.name} ({len(resp.content):,} bytes, retrieved {date.today()})")
        time.sleep(0.5)
    return fetched


if __name__ == "__main__":
    for line in download_sources(include_optional=True):
        print(line)
