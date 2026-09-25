# Financial methodology

All calculations are deterministic Python (`src/finance/`, `src/scenario/`). The language model never calculates.
Period: FY2026 of the fictional enterprise (September 2025 to August 2026), closed through 31 August 2026.

## Value definitions

| Term | Definition |
|---|---|
| Investment | Programme spend: `cost_transactions` where `cost_type = 'programme'` |
| Incremental operating cost | Run costs borne by the business once live (`cost_type = 'incremental_opex'`); deducted from value |
| Expected value | Business-case benefit − planned incremental operating cost |
| Measured benefit | Realised + validated benefit |
| **Realised** | Benefit supported by financial (GL) or operational (telemetry) evidence, net of actual incremental operating cost |
| **Validated** | Benefit confirmed by the business owner but not yet evidenced in actuals |
| **Hypothetical** | Expected − realised − validated: business-case assumptions with no evidence yet |
| In the P&L | The GL-evidenced part of realised benefit (reconciles to `financials.ai_attributed_benefit`) |

## Formulas (`src/finance/formulas.py`)

| Metric | Formula |
|---|---|
| ROI | (Value − Investment) ÷ Investment |
| Value per $1 invested | Value ÷ Investment |
| Net value | Value − Investment |
| Benefit realisation % | Realised ÷ Expected |
| Budget variance | Actual − Budget; % = (Actual − Budget) ÷ Budget (positive = overspend) |
| Forecast variance | Actual − Forecast; % of forecast |
| Payback | First month in which cumulative net cash flow ≥ 0, interpolated within the month |
| NPV | Σ CFₜ ÷ (1 + r)ᵗ, t in years, r = A-30 (9%) |
| IRR | r where NPV = 0, by bisection; undefined without a sign change |
| Cost per outcome | Cost ÷ outcome volume |
| Incremental ROI | (ΔValue − ΔCost) ÷ ΔCost |

**Note on ROI basis.** The brief's example figures ("realised ROI 75%" on $31.7M value / $42.3M investment) are a
value-to-investment ratio. This project reports ROI on the standard net basis, so a figure below zero means the investment
has not yet been recovered, and reports the ratio separately as *value per $1 invested* ($0.72 here). In-year ROI
understates a first-year programme, so a three-year lifecycle view (NPV, IRR, payback) sits alongside it.

## Lifecycle outlook (forecast)

FY2026 monthly actuals, then 24 outlook months at the FY26-Q4 measured run-rate × A-31 (persistence 0.9), less run cost of
A-32 (45%) × FY2026 spend and the Q4 incremental-opex run-rate. Discounted at A-30. Labelled as a forecast wherever shown.

## Quarterly ROI movement

ROI = V/C − 1, so ΔROI = (V₂ − V₁)/C₂ (value effect) + V₁(1/C₂ − 1/C₁) (cost effect). Per initiative *i*:
contributionᵢ = ΔVᵢ/C₂ − V₁·ΔCᵢ/(C₁C₂). Contributions sum exactly to ΔROI. Drivers are then read from the data: cost
group changes, GPU utilisation and capacity, go-live slips (milestones) and value-per-user revisions greater than 20%.

## Benefits leakage (exact decomposition per line)

```
delayed implementation = business case − plan shifted by the go-live slip
low adoption           = shifted plan × (1 − actual active users ÷ planned active users at the same stage)
value per unit         = adoption-adjusted plan − measured       (labelled with the owner's reason code)
pending validation     = validated benefit
business case − realised = sum of the four
```

## At-risk rules (derived)

Red if any: realisation < 50%, spend > 10% over budget, go-live ≥ 3 months late, adoption < 60% of target.
Amber if any: realisation < 70%, spend > 5% over, go-live ≥ 1 month late, adoption < 85% of target.

## AI Value Confidence Engine

Score (0–100) = 100 × Σ weight × factor:

| Factor | Weight | Basis |
|---|---:|---|
| Source quality | 15% | GL-backed 1.0, telemetry 0.75 |
| Actual vs forecast | 15% | realised ÷ business case, capped at 1 |
| Financial validation | 15% | Finance business partner sign-off |
| Data completeness | 10% | live months with measured value ÷ live months |
| Owner confirmation | 5% | benefit owner has confirmed |
| Methodology | 15% | controlled test 1.0, before/after 0.75, attribution 0.5, management estimate 0.3 |
| Recency | 10% | full within 45 days of period end, falling to 0 at 365 days |
| Assumption dependency | 15% | 1 − (hypothetical + ½ validated) ÷ business case |

Bands: High ≥ 75, Medium 50–75, Low < 50. The score rates evidence quality; it is **not** a probability that the benefit
will be achieved, and every score is shown with the basis sentences that produced it.

## Scenario engine (`src/scenario/engine.py`, mirrored in `web/scenario.js`)

| Lever | ΔValue | ΔCost |
|---|---|---|
| Additional investment | ΔI × Green-initiative expected value per $ × A-35 | ΔI |
| Utilisation target | ΔGPU-h × value per used GPU-hour × A-33 | ΔGPU-h × (non-infrastructure investment per used GPU-hour × A-36 + A-34) |
| Cloud cost change | – | cloud spend × change |
| Productivity change | productivity business case × change | – |
| Revenue uplift change | revenue business case × change | – |
| Adoption change | productivity business case × change | – |
| Implementation cost change | – | investment × change |
| Project delay | − in-flight expected value × months × A-37 | – |
| Benefit realisation rate | (benefit + deltas above) × (rate − 1) | – |

ΔGPU-h = annualised Q4 capacity × (target − current utilisation). Utilisation-driven value and cost use the Q4 run-rate
basis, and avoided infrastructure (ΔGPU-h × infrastructure cost per capacity GPU-hour) is reported but not netted.
Sensitivity moves each driver ±20% (utilisation ±10 pp) one at a time. The browser engine is checked against the Python
engine in `tests/test_scenario.py`.
