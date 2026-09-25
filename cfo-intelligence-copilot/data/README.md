# Data

Only **publicly available** documents are used. Primary sources are SEC EDGAR, which is authoritative for filed
financial statements, and Microsoft Investor Relations, for reference. Yahoo Finance, Wikipedia and blogs are not used.

## Source registry

[`source_registry.csv`](source_registry.csv) lists every document the system may use: source URL, document name,
reporting period, filing date, retrieval date, source type, accession number and role. [`sources/`](sources/) holds
one JSON card per source, generated from the registry.

| Source | Role | Ingested |
|---|---|---|
| Microsoft Form 10-K, FY ended June 30 2026 (filed 2026-07-29) | Primary - core source of truth | yes |
| Microsoft Form 10-K, FY ended June 30 2025 (filed 2025-07-30) | Comparatives (FY2023–FY2024) and cross-filing consistency checks | yes |
| Form 8-K Ex. 99.1 - Q4 FY2026 earnings release (2026-07-29) | Management commentary only; quarterly figures not loaded | yes |
| SEC XBRL Company Facts API | Optional independent validation | optional |
| Microsoft Investor Relations website | Reference; blocks automated retrieval, so the SEC copies are used | no |

## Obtaining the documents

The raw filings are **not redistributed** in this repository (`data/raw/` is git-ignored). To download them:

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"   # SEC fair-access policy
python -m scripts.build_financial_model                     # downloads to data/raw/, then builds everything
```

Or download manually from the URLs in `source_registry.csv` and save them under `data/raw/` with the names in the
`local_filename` column, then run `python -m scripts.build_financial_model --offline`.

## Processed data

| File | Committed | Content |
|---|:-:|---|
| `processed/financial_facts.csv` | ✅ | Normalised financial model: one row per reported number, with full provenance (see `docs/data-model.md`). Enables the dashboard, calculations and tests without downloading anything |
| `processed/source_conflicts.csv` | ✅ | Cross-filing restatements, superseded categories, intra-filing conflicts |
| `processed/xbrl_facts.csv` | rebuilt | Every tagged numeric fact extracted from the filings (~3,100 rows) |
| `processed/cfo_copilot.db` | rebuilt | SQLite copy of `financial_facts.csv` (auto-rebuilt on first use) |
| `processed/document_chunks.jsonl`, `retrieval_index.pkl` | rebuilt | Narrative text chunks and retrieval index derived from the raw filings. Management-commentary features need these |

Financial figures are facts reported by the company. Filing text is used only to produce short cited quotations at run
time.
