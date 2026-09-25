# Financial calculations

All financial metrics are computed by deterministic Python in `src/calculations/`. The LLM is never asked to compute,
round or estimate a number. This page is the calculation catalogue; the table is generated from `METRICS` in
`src/calculations/engine.py`, so documentation and code cannot drift.

## Principles

1. **One definition per metric** - formula text, input list and a pure function live together in a `MetricDef`.
2. **Inputs are reported facts** from the normalised model (`financial_facts.csv` / SQLite), each carrying document, page,
   table, row, column and XBRL concept.
3. **No invented numbers.** If any input is missing the result is `status = unavailable` with the message
   *"I could not find sufficient evidence in the available public filings."* If sources conflict inside a filing the fact
   is blocked: *"The available sources contain differing values. The system requires manual review."*
4. **Every result retains** formula, input values, source references, `engine_version` and `calculated_at` (UTC).
5. **Proxies are labelled.** EBITDA and ROIC are not reported measures. They're flagged `is_proxy` with an explanatory
   note, and they lower answer confidence to *Medium*.
6. **Ratios change in percentage points.** Variance on a % metric is reported in pp, not as a % of a %.

## Metric catalogue

| id | Metric | Formula | Unit | Proxy | Note |
|---|---|---|---|:-:|---|
| `revenue_growth` | Revenue growth (YoY) | `(Revenue[t] - Revenue[t-1]) / Revenue[t-1]` | % |  |  |
| `gross_margin_pct` | Gross margin % | `Gross margin / Revenue` | % |  |  |
| `operating_margin_pct` | Operating margin % | `Operating income / Revenue` | % |  |  |
| `net_margin_pct` | Net margin % | `Net income / Revenue` | % |  |  |
| `total_operating_expenses` | Total operating expenses | `Research and development + Sales and marketing + General and administrative` | USD millions |  |  |
| `opex_pct_revenue` | Operating expenses as % of revenue | `(R&D + S&M + G&A) / Revenue` | % |  |  |
| `rd_pct_revenue` | R&D as % of revenue | `Research and development / Revenue` | % |  |  |
| `sm_pct_revenue` | Sales & marketing as % of revenue | `Sales and marketing / Revenue` | % |  |  |
| `ga_pct_revenue` | G&A as % of revenue | `General and administrative / Revenue` | % |  |  |
| `ebitda_proxy` | EBITDA proxy | `Operating income + Depreciation, amortization, and other (cash flow statement)` | USD millions | yes | Not a reported GAAP measure. The cash flow line 'Depreciation, amortization, and other' may include items other than D&A, so this is an approximation. |
| `ebitda_proxy_margin` | EBITDA proxy margin | `(Operating income + Depreciation, amortization, and other) / Revenue` | % | yes | Proxy - see EBITDA proxy. |
| `operating_cash_flow_margin` | Operating cash flow margin | `Net cash from operations / Revenue` | % |  |  |
| `free_cash_flow` | Free cash flow | `Net cash from operations - Additions to property and equipment` | USD millions |  | Analyst definition (OCF - capex). Excludes finance-lease principal payments; may differ from company-defined measures. |
| `free_cash_flow_margin` | Free cash flow margin | `(Net cash from operations - Capex) / Revenue` | % |  |  |
| `cash_conversion` | Cash conversion (FCF / net income) | `(Net cash from operations - Capex) / Net income` | x |  |  |
| `ocf_to_net_income` | Operating cash flow / net income | `Net cash from operations / Net income` | x |  |  |
| `capex_intensity` | Capex intensity | `Additions to property and equipment / Revenue` | % |  |  |
| `capex_reinvestment_rate` | Capex as % of operating cash flow | `Additions to property and equipment / Net cash from operations` | % |  |  |
| `current_ratio` | Current ratio | `Total current assets / Total current liabilities` | x |  |  |
| `total_debt` | Total debt | `Current portion of long-term debt + Long-term debt` | USD millions |  | Excludes operating and finance lease liabilities. |
| `debt_to_equity` | Debt-to-equity | `(Current portion of long-term debt + Long-term debt) / Total stockholders' equity` | x |  | Excludes lease liabilities. |
| `net_debt` | Net debt (negative = net cash) | `(Current portion of long-term debt + Long-term debt) - Total cash, cash equivalents, and short-term investments` | USD millions |  | Excludes lease liabilities and equity investments. |
| `effective_tax_rate_calc` | Effective tax rate (calculated) | `Provision for income taxes / Income before income taxes` | % |  |  |
| `roic_proxy` | ROIC proxy | `NOPAT / average invested capital; NOPAT = Operating income x (1 - tax provision / pre-tax income); invested capital = equity + total debt - cash & short-term investments` | % | yes | Simplified proxy: excludes lease liabilities, equity investments and goodwill adjustments; uses the effective tax rate. |
| `revenue_per_employee` | Revenue per employee | `Revenue / Full-time employees (year end)` | USD thousands |  | Headcount is extracted from Item 1 narrative text (not XBRL-tagged) and is a year-end figure. |
| `operating_leverage` | Degree of operating leverage | `Operating income growth / Revenue growth` | x |  | >1.0x means operating income grew faster than revenue (positive operating leverage). |

Also provided by the engine:

| Function | Formula |
|---|---|
| `variance(metric, t, prior)` | absolute = current − prior; % = (current − prior) / abs(prior); ratio metrics in pp |
| `cagr(metric, start, end)` | (end / start)^(1 / years) − 1 |
| `segment_table(t)` | segment growth, operating margin (segment OI / segment revenue), share of revenue, **contribution to growth** = segment Δrevenue / total Δrevenue, growth contribution in pp = segment Δrevenue / prior total revenue |

## Variance engine (`variance.py`)

For each major metric: current year, prior year, absolute variance, % variance, direction and a documented favourability
convention (revenue/profit/cash up = favourable; cost of revenue, S&M and G&A up = unfavourable; R&D and capex = neutral
investment). The explanation step only quotes MD&A / earnings-release passages retrieved from **the filing for that fiscal
year**. When nothing relevant is retrieved, or the comparison isn't current vs immediately prior year (the MD&A doesn't
cover it), the engine returns *"Public filing does not provide sufficient evidence to determine the specific cause."*

## Driver trees (`driver_trees.py`)

| Tree | Decomposition | Reconciliation |
|---|---|---|
| Revenue growth | Δ total revenue = Σ Δ segment revenue → drill-down to product/service offerings | Offerings aren't reported by segment; the mapping follows the Note 18 description (`config/metric_map.json`), and any residual is shown as an explicit "unreconciled" node |
| Operating income | ΔOI = volume effect (ΔRevenue × prior GM%) + rate effect (ΔGM% × current revenue) − ΔR&D − ΔS&M − ΔG&A | Exact (tested) |
| Operating margin | ΔOM = ΔGM% − ΔR&D% − ΔS&M% − ΔG&A% (all % of revenue) | Exact identity (tested) |
| Free cash flow | ΔFCF = ΔOCF − Δcapex; OCF split into net income, D&A-and-other, SBC and a residual (working capital / other non-cash) | Exact (residual shown) |

## Scenario engine (`scenario.py`)

*Illustrative scenario — not management guidance.* The base case carries forward the latest fiscal year's **actual**
ratios (revenue growth, gross margin %, growth of each opex line, effective tax rate, capex/revenue, OCF/net income).
Other income is set to 0, because investment gains and losses aren't extrapolated. The CFO overrides or shocks any
assumption, and the engine recomputes:

```
revenue      = revenue[t] × (1 + g)            gross profit = revenue × GM%
opex_i       = opex_i[t] × (1 + g_i)           operating income = gross profit − Σ opex_i
pre-tax      = operating income + other income net income = pre-tax × (1 − tax rate)
OCF          = net income × (OCF / NI)         capex = revenue × capex intensity
FCF          = OCF − capex
```

Sensitivity shocks each assumption by ±1 pp (±0.05x for OCF/NI) with everything else held constant, then ranks the
assumptions by the absolute impact on the target line (tornado chart).

## CFO attention rules (`handlers.cfo_attention`)

A flag is raised only when a documented rule fires on reported figures:

| Rule | Fires when |
|---|---|
| Capital intensity | capex growth > operating cash flow growth |
| Earnings-to-cash gap | free cash flow growth < net income growth |
| Gross margin compression | gross margin % fell year over year |
| Receivables growth | accounts receivable growth > revenue growth |
| Non-operating volatility | abs(other income (expense)) > 3% of pre-tax income |
| Tax rate movement | abs(Δ effective tax rate) > 0.5 pp |
| Restated comparatives | any prior-year fact differs between the latest and prior filings |

Flags are prompts for human review. Each carries a "possible interpretation" line that states a line of enquiry, not a
conclusion.
