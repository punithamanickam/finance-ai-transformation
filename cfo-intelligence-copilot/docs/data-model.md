# Financial data model

## Entity: `FinancialFact` (`src/financial_model/schema.py`)

One row = one reported number with full provenance. Stored in `data/processed/financial_facts.csv`, which is committed
and reviewable, and loaded into SQLite table `financial_facts`.

| Field | Example | Notes |
|---|---|---|
| `fact_key` | `revenue\|FY2026\|` | `metric_id\|FYyyyy\|dimension_member`, unique |
| `company` | Microsoft Corporation | |
| `reporting_period` / `fiscal_year` | FY2026 / 2026 | fiscal year ends June 30 |
| `period_end`, `period_type` | 2026-06-30, duration | instants for balance-sheet items |
| `statement` | Income Statement | Income Statement · Balance Sheet · Cash Flow Statement · Segment · Notes · Business (Item 1) |
| `section` | Revenue | analytical grouping |
| `metric_id`, `metric_label` | revenue, Total revenue | canonical id (see `config/metric_map.json`) |
| `dimension_type`, `dimension_member`, `dimension_label` | segment, IC, Intelligent Cloud | also `product_offering`, `geography` |
| `value` | 331839 | |
| `currency`, `unit` | USD, USD millions | monetary normalised to USD millions; per-share in USD |
| `source_id`, `source_document` | MSFT-10K-FY2026, Microsoft FY2026 Form 10-K | links to `data/source_registry.csv` |
| `source_page` | 50 | printed page number of the filing |
| `source_section` | Item 8. Financial Statements and Supplementary Data | 10-K Item |
| `source_table`, `table_index` | INCOME STATEMENTS, 0 | table title and position on the page |
| `row_label`, `column_label` | Total revenue, 2026 | as printed |
| `source_url` | https://www.sec.gov/Archives/... | |
| `xbrl_concept`, `xbrl_fact_id` | us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax | the exact tagged element |
| `extraction_method` | ixbrl \| text-pattern | headcount is a deterministic regex over Item 1 text |
| `occurrences` | 4 | how many times the same fact appears in the filing (statement, MD&A, notes) |
| `consistency` | consistent \| conflict | conflicting occurrences block the fact |
| `restated_vs_prior_filing` | true | value differs from the earlier filing for the same period |

Example record (from the committed CSV):

```yaml
company: Microsoft Corporation
period: FY2026
statement: Income Statement
metric: Total revenue
value: 331839
currency: USD
unit: millions
source: Microsoft FY2026 Form 10-K
section: Item 8. Financial Statements and Supplementary Data - INCOME STATEMENTS
page: 50
row / column: Total revenue / 2026
xbrl: us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax
url: https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm
```

## Coverage

| Area | Metrics | Years |
|---|---|---|
| Income statement | revenue (total/product/service), cost of revenue (total/product/service), gross margin, R&D, S&M, G&A, operating income, other income, pre-tax income, tax, net income, EPS basic/diluted, diluted shares, effective tax rate | FY2023–FY2026 |
| Balance sheet | cash, short-term investments, total cash & STI, receivables, inventory, current assets, PP&E, equity investments, goodwill, intangibles, total assets, payables, current debt, short-term unearned revenue, current liabilities, long-term debt, total liabilities, equity | FY2024–FY2026 (partial FY2023) |
| Cash flow | OCF, D&A-and-other, SBC, capex, acquisitions, investing CF, buybacks, dividends, financing CF, FX, net change, closing cash | FY2023–FY2026 |
| Segments | revenue, cost of revenue, operating expenses, operating income × 3 segments | FY2023–FY2026 |
| Revenue by offering | 10 product/service lines (discovered from the filing's dimensions) | FY2023–FY2026 (renamed lines superseded) |
| Geography | United States, other countries | FY2023–FY2026 |
| Other | Microsoft Cloud revenue, full-time employees | FY2023–FY2026 |

Missing cells are **flagged in `docs/data_quality_report.md`, never estimated**.

## Build pipeline (`scripts/build_financial_model.py`)

1. `source_registry.csv` → `data/sources/*.json` cards
2. SEC download (skipped if present, `--offline`)
3. `document_parser.parse_filing` → pages / Items / headings / tables
4. `ixbrl_extractor.extract_facts` → `xbrl_facts.csv` (every tagged number, ~1,500 per 10-K)
5. `builder.build_from_filing` → canonical facts per filing: 12-month durations only, primary statement occurrence
   preferred, intra-filing consistency checked
6. `builder.merge_filings` → latest filing authoritative. Cross-filing differences and superseded (renamed) dimension
   members are logged to `source_conflicts.csv`
7. SQLite build, retrieval chunks + index, data-quality report

## Reconciliation rules

| Situation | Treatment |
|---|---|
| Same fact repeated inside a filing with identical values | `occurrences` > 1, primary statement page cited |
| Same fact repeated inside a filing with different values | `consistency = conflict` → the calculation engine refuses the fact (`DataConflict`) |
| Same period in two filings, values differ | Most recent filing used; `restated_vs_prior_filing = true`; logged; surfaced as a CFO-attention item |
| Category renamed in a later filing (e.g. *Gaming* → *XBOX*) | Older member excluded for periods the newer filing covers (prevents double counting); logged as `superseded_member` |

The FY2026 10-K recasts FY2024 and FY2025 *"Depreciation, amortization, and other"* relative to the FY2025 10-K. The
system detects this automatically. It's the kind of discrepancy a finance team needs flagged before drawing trend
conclusions.
