# Data Quality Report

_Generated 2026-09-25 06:59 UTC by `src/governance/data_quality.py` (re-run with `python -m scripts.build_financial_model`)._

**Result: 84/84 checks passed.** Financial facts in model: 286 (fiscal years 2022–2026).

Tolerance: ±$1M for reported-figure identities (filings round to the nearest million); 1e-9 for engine-vs-independent recomputation.

## Balance sheet

| Check | FY | Expected | Actual | Result | Detail |
|---|---|---:|---:|:---:|---|
| Total assets = Total liabilities and stockholders' equity | 2024 | 512,163 | 512,163 | ✅ |  |
| Total liabilities + Stockholders' equity = Total assets | 2024 | 512,163 | 512,163 | ✅ |  |
| Cash & equivalents + short-term investments = Total cash and short-term investments | 2024 | 75,543 | 75,543 | ✅ |  |
| Total assets = Total liabilities and stockholders' equity | 2025 | 619,003 | 619,003 | ✅ |  |
| Total liabilities + Stockholders' equity = Total assets | 2025 | 619,003 | 619,003 | ✅ |  |
| Cash & equivalents + short-term investments = Total cash and short-term investments | 2025 | 94,565 | 94,565 | ✅ |  |
| Total assets = Total liabilities and stockholders' equity | 2026 | 758,376 | 758,376 | ✅ |  |
| Total liabilities + Stockholders' equity = Total assets | 2026 | 758,376 | 758,376 | ✅ |  |
| Cash & equivalents + short-term investments = Total cash and short-term investments | 2026 | 76,843 | 76,843 | ✅ |  |

## Cash flow

| Check | FY | Expected | Actual | Result | Detail |
|---|---|---:|---:|:---:|---|
| Cash flow ending cash = Balance sheet cash and cash equivalents | 2024 | 18,315 | 18,315 | ✅ |  |
| Cash flow ending cash = Balance sheet cash and cash equivalents | 2025 | 30,242 | 30,242 | ✅ |  |
| Cash flow ending cash = Balance sheet cash and cash equivalents | 2026 | 20,935 | 20,935 | ✅ |  |
| Operating + investing + financing + FX = Net change in cash | 2023 | 20,773 | 20,773 | ✅ |  |
| Opening cash + net change = Closing cash | 2023 | 34,704 | 34,704 | ✅ |  |
| Operating + investing + financing + FX = Net change in cash | 2024 | -16,389 | -16,389 | ✅ |  |
| Opening cash + net change = Closing cash | 2024 | 18,315 | 18,315 | ✅ |  |
| Operating + investing + financing + FX = Net change in cash | 2025 | 11,927 | 11,927 | ✅ |  |
| Opening cash + net change = Closing cash | 2025 | 30,242 | 30,242 | ✅ |  |
| Operating + investing + financing + FX = Net change in cash | 2026 | -9,307 | -9,307 | ✅ |  |
| Opening cash + net change = Closing cash | 2026 | 20,935 | 20,935 | ✅ |  |

## Revenue

| Check | FY | Expected | Actual | Result | Detail |
|---|---|---:|---:|:---:|---|
| Product + Service and other revenue = Total revenue | 2023 | 211,915 | 211,915 | ✅ |  |
| United States + Other countries revenue = Total revenue | 2023 | 211,915 | 211,915 | ✅ |  |
| Sum of product/service offering revenue = Total revenue | 2023 | 211,915 | 211,915 | ✅ | 10 offerings |
| Product + Service and other revenue = Total revenue | 2024 | 245,122 | 245,122 | ✅ |  |
| United States + Other countries revenue = Total revenue | 2024 | 245,122 | 245,122 | ✅ |  |
| Sum of product/service offering revenue = Total revenue | 2024 | 245,122 | 245,122 | ✅ | 10 offerings |
| Product + Service and other revenue = Total revenue | 2025 | 281,724 | 281,724 | ✅ |  |
| United States + Other countries revenue = Total revenue | 2025 | 281,724 | 281,724 | ✅ |  |
| Sum of product/service offering revenue = Total revenue | 2025 | 281,724 | 281,724 | ✅ | 10 offerings |
| Product + Service and other revenue = Total revenue | 2026 | 331,839 | 331,839 | ✅ |  |
| United States + Other countries revenue = Total revenue | 2026 | 331,839 | 331,839 | ✅ |  |
| Sum of product/service offering revenue = Total revenue | 2026 | 331,839 | 331,839 | ✅ | 10 offerings |

## Segments

| Check | FY | Expected | Actual | Result | Detail |
|---|---|---:|---:|:---:|---|
| Sum of segment revenue = Total revenue | 2023 | 211,915 | 211,915 | ✅ |  |
| Sum of segment operating income = Total operating income | 2023 | 88,523 | 88,523 | ✅ |  |
| Sum of segment cost of revenue = Total cost of revenue | 2023 | 65,863 | 65,863 | ✅ |  |
| Sum of segment revenue = Total revenue | 2024 | 245,122 | 245,122 | ✅ |  |
| Sum of segment operating income = Total operating income | 2024 | 109,433 | 109,433 | ✅ |  |
| Sum of segment cost of revenue = Total cost of revenue | 2024 | 74,114 | 74,114 | ✅ |  |
| Sum of segment revenue = Total revenue | 2025 | 281,724 | 281,724 | ✅ |  |
| Sum of segment operating income = Total operating income | 2025 | 128,528 | 128,528 | ✅ |  |
| Sum of segment cost of revenue = Total cost of revenue | 2025 | 87,831 | 87,831 | ✅ |  |
| Sum of segment revenue = Total revenue | 2026 | 331,839 | 331,839 | ✅ |  |
| Sum of segment operating income = Total operating income | 2026 | 155,237 | 155,237 | ✅ |  |
| Sum of segment cost of revenue = Total cost of revenue | 2026 | 106,374 | 106,374 | ✅ |  |

## Income statement

| Check | FY | Expected | Actual | Result | Detail |
|---|---|---:|---:|:---:|---|
| Revenue - Cost of revenue = Gross margin | 2023 | 146,052 | 146,052 | ✅ |  |
| Gross margin - R&D - S&M - G&A = Operating income | 2023 | 88,523 | 88,523 | ✅ |  |
| Operating income + Other income (expense) = Income before taxes | 2023 | 89,311 | 89,311 | ✅ |  |
| Income before taxes - Provision for taxes = Net income | 2023 | 72,361 | 72,361 | ✅ |  |
| Net income / diluted shares ≈ diluted EPS | 2023 | 9.6800 | 9.6843 | ✅ |  |
| Revenue - Cost of revenue = Gross margin | 2024 | 171,008 | 171,008 | ✅ |  |
| Gross margin - R&D - S&M - G&A = Operating income | 2024 | 109,433 | 109,433 | ✅ |  |
| Operating income + Other income (expense) = Income before taxes | 2024 | 107,787 | 107,787 | ✅ |  |
| Income before taxes - Provision for taxes = Net income | 2024 | 88,136 | 88,136 | ✅ |  |
| Net income / diluted shares ≈ diluted EPS | 2024 | 12 | 12 | ✅ |  |
| Revenue - Cost of revenue = Gross margin | 2025 | 193,893 | 193,893 | ✅ |  |
| Gross margin - R&D - S&M - G&A = Operating income | 2025 | 128,528 | 128,528 | ✅ |  |
| Operating income + Other income (expense) = Income before taxes | 2025 | 123,627 | 123,627 | ✅ |  |
| Income before taxes - Provision for taxes = Net income | 2025 | 101,832 | 101,832 | ✅ |  |
| Net income / diluted shares ≈ diluted EPS | 2025 | 14 | 14 | ✅ |  |
| Revenue - Cost of revenue = Gross margin | 2026 | 225,465 | 225,465 | ✅ |  |
| Gross margin - R&D - S&M - G&A = Operating income | 2026 | 155,237 | 155,237 | ✅ |  |
| Operating income + Other income (expense) = Income before taxes | 2026 | 165,934 | 165,934 | ✅ |  |
| Income before taxes - Provision for taxes = Net income | 2026 | 133,749 | 133,749 | ✅ |  |
| Net income / diluted shares ≈ diluted EPS | 2026 | 18 | 18 | ✅ |  |

## Calculations

| Check | FY | Expected | Actual | Result | Detail |
|---|---|---:|---:|:---:|---|
| Revenue growth: engine = independent recomputation | 2024 | 0.1567 | 0.1567 | ✅ |  |
| Revenue growth: engine = independent recomputation | 2025 | 0.1493 | 0.1493 | ✅ |  |
| Revenue growth: engine = independent recomputation | 2026 | 0.1779 | 0.1779 | ✅ |  |
| Gross margin %: engine = independent recomputation | 2023 | 0.6892 | 0.6892 | ✅ |  |
| Operating margin %: engine = independent recomputation | 2023 | 0.4177 | 0.4177 | ✅ |  |
| Net margin %: engine = independent recomputation | 2023 | 0.3415 | 0.3415 | ✅ |  |
| Gross margin %: engine = independent recomputation | 2024 | 0.6976 | 0.6976 | ✅ |  |
| Operating margin %: engine = independent recomputation | 2024 | 0.4464 | 0.4464 | ✅ |  |
| Net margin %: engine = independent recomputation | 2024 | 0.3596 | 0.3596 | ✅ |  |
| Gross margin %: engine = independent recomputation | 2025 | 0.6882 | 0.6882 | ✅ |  |
| Operating margin %: engine = independent recomputation | 2025 | 0.4562 | 0.4562 | ✅ |  |
| Net margin %: engine = independent recomputation | 2025 | 0.3615 | 0.3615 | ✅ |  |
| Gross margin %: engine = independent recomputation | 2026 | 0.6794 | 0.6794 | ✅ |  |
| Operating margin %: engine = independent recomputation | 2026 | 0.4678 | 0.4678 | ✅ |  |
| Net margin %: engine = independent recomputation | 2026 | 0.4031 | 0.4031 | ✅ |  |

## Integrity

| Check | FY | Expected | Actual | Result | Detail |
|---|---|---:|---:|:---:|---|
| No duplicate financial records (unique fact_key) |  | 0.0000 | 0.0000 | ✅ |  |
| Currency is consistent (USD only) |  |  |  | ✅ | all monetary facts USD |
| Units are consistent within each metric |  |  |  | ✅ | one unit per metric |
| Monetary units normalised (USD millions / USD per share) |  |  |  | ✅ | ok |
| No intra-filing value conflicts |  | 0.0000 | 0.0000 | ✅ |  |

## Missing values (coverage of canonical metrics)

Cells marked ⚠️ are not available in the loaded filings and are **flagged, not estimated**. Balance-sheet items exist only for year-ends presented in the filings loaded (FY2024–FY2026).

| Statement | Metric | FY2022 | FY2023 | FY2024 | FY2025 | FY2026 |
|---|---|:-:|:-:|:-:|:-:|:-:|
| Balance Sheet | `accounts_payable` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `accounts_receivable` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `cash_and_equivalents` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `cash_and_short_term_investments` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `current_assets` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `current_liabilities` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `equity_investments` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `goodwill` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Balance Sheet | `intangible_assets` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `inventory` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `long_term_debt` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `property_and_equipment` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `shareholders_equity` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Balance Sheet | `short_term_debt` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `short_term_investments` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `short_term_unearned_revenue` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `total_assets` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `total_liabilities` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Balance Sheet | `total_liabilities_and_equity` | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| Business (Item 1) | `employees` | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ |
| Cash Flow Statement | `acquisitions` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `capital_expenditure` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `cash_end_of_period` | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `depreciation_amortization_other` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `dividends_paid` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `financing_cash_flow` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `fx_effect_on_cash` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `investing_cash_flow` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `net_change_in_cash` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `operating_cash_flow` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `share_repurchases` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Cash Flow Statement | `stock_based_compensation` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `cost_of_revenue` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `cost_of_revenue_product` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `cost_of_revenue_service` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `diluted_shares` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `eps_basic` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `eps_diluted` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `general_and_administrative` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `gross_profit` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `income_before_tax` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `income_tax` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `net_income` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `operating_income` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `other_income_expense` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `research_and_development` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `revenue` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `revenue_product` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `revenue_service` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Income Statement | `sales_and_marketing` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Notes | `effective_tax_rate` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Notes | `microsoft_cloud_revenue` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Notes | `revenue_other_countries` | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Notes | `revenue_us` | ⚠️ | ✅ | ✅ | ✅ | ✅ |

## Cross-source differences and conflicts

The same period can be reported in more than one filing. The most recent filing is treated as authoritative (prior-year comparatives are sometimes recast); every difference is logged here for human review.

| Type | Fact | Value used (source, page) | Other value (source, page) | Resolution |
|---|---|---|---|---|
| cross_filing_difference | `depreciation_amortization_other|FY2024|` | 20,958 (MSFT-10K-FY2026, p.53.0) | 22287.0 (MSFT-10K-FY2025, p.53) | Most recent filing is authoritative (comparative restated / recast). Flagged for review. |
| cross_filing_difference | `depreciation_amortization_other|FY2025|` | 29,433 (MSFT-10K-FY2026, p.53.0) | 34153.0 (MSFT-10K-FY2025, p.53) | Most recent filing is authoritative (comparative restated / recast). Flagged for review. |
| superseded_member | `revenue_by_offering|FY2024|GamingMember` | nan (MSFT-10K-FY2026, p.nan) | 21503.0 (MSFT-10K-FY2025, p.85) | Category renamed/recast in the most recent filing; older member excluded for this period. |
| superseded_member | `revenue_by_offering|FY2025|GamingMember` | nan (MSFT-10K-FY2026, p.nan) | 23455.0 (MSFT-10K-FY2025, p.85) | Category renamed/recast in the most recent filing; older member excluded for this period. |
| superseded_member | `revenue_by_offering|FY2024|SearchAndNewsAdvertisingMember` | nan (MSFT-10K-FY2026, p.nan) | 12306.0 (MSFT-10K-FY2025, p.85) | Category renamed/recast in the most recent filing; older member excluded for this period. |
| superseded_member | `revenue_by_offering|FY2025|SearchAndNewsAdvertisingMember` | nan (MSFT-10K-FY2026, p.nan) | 13878.0 (MSFT-10K-FY2025, p.85) | Category renamed/recast in the most recent filing; older member excluded for this period. |
