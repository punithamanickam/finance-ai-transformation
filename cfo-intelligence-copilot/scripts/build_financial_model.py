"""End-to-end data build.

    python -m scripts.build_financial_model            # download (if missing) + extract + model + index + DQ report
    python -m scripts.build_financial_model --offline  # skip downloads, use whatever is in data/raw/

Steps: source registry -> SEC download -> document parsing -> iXBRL fact extraction -> normalised model ->
cross-filing reconciliation -> SQLite -> retrieval index -> data-quality report.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from src import settings
from src.extraction.ixbrl_extractor import extract_to_frame
from src.financial_model.builder import build_from_filing, merge_filings
from src.financial_model.repository import build_database
from src.ingestion.document_parser import parse_filing
from src.ingestion.sec_client import download_sources
from src.ingestion.source_registry import load_registry, write_source_cards

FILINGS = ["MSFT-10K-FY2026", "MSFT-10K-FY2025"]  # most recent first = authoritative order


def main(offline: bool = False) -> None:
    settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    write_source_cards()
    if not offline:
        for line in download_sources():
            print("downloaded", line)
    reg = load_registry().set_index("source_id")

    all_xbrl, model_frames, parsed = [], [], {}
    for sid in FILINGS:
        path = settings.RAW_DIR / reg.loc[sid, "local_filename"]
        if not path.exists():
            sys.exit(f"Missing {path}. Run without --offline to download from SEC EDGAR.")
        print(f"[{sid}] parsing document ...")
        pages = parse_filing(path)
        parsed[sid] = pages
        print(f"[{sid}] extracting inline XBRL facts ...")
        facts = extract_to_frame(path, sid)
        all_xbrl.append(facts)
        model_frames.append(build_from_filing(facts, sid, pages))
        print(f"[{sid}] {len(pages)} pages, {len(facts)} tagged facts, {len(model_frames[-1])} model facts")

    pd.concat(all_xbrl).to_csv(settings.XBRL_FACTS_CSV, index=False)
    model, conflicts = merge_filings(model_frames)
    model.to_csv(settings.FINANCIAL_FACTS_CSV, index=False)
    conflicts.to_csv(settings.CONFLICTS_CSV, index=False)
    build_database()
    print(f"financial model: {len(model)} facts; {len(conflicts)} conflicts/restatements logged")

    # retrieval corpus (text chunks) - derived from raw documents, git-ignored
    from src.retrieval.chunker import build_chunks, write_chunks
    from src.retrieval.vector_store import build_index

    commentary_path = settings.RAW_DIR / reg.loc["MSFT-8K-FY26Q4-EX99", "local_filename"]
    if commentary_path.exists():
        parsed["MSFT-8K-FY26Q4-EX99"] = parse_filing(commentary_path)
    chunks = [c for sid, pages in parsed.items() for c in build_chunks(pages, sid)]
    write_chunks(chunks)
    build_index(chunks)
    print(f"retrieval index: {len(chunks)} chunks")

    from src.governance.data_quality import write_report

    report = write_report()
    print(f"data-quality report: {report}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    main(ap.parse_args().offline)
