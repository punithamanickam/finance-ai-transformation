"""Illustrative one-year scenario simulator.

Base case = the latest reported fiscal year's actual ratios carried forward (NOT a forecast and NOT management
guidance). The CFO overrides assumptions; the engine recomputes a simple P&L and cash view deterministically and
compares it with the base case.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.calculations.engine import CalculationEngine

DISCLAIMER = "Illustrative scenario — not management guidance."


class Assumptions(BaseModel):
    revenue_growth: float = Field(description="YoY revenue growth, decimal")
    gross_margin: float
    rd_growth: float
    sm_growth: float
    ga_growth: float
    other_income: float = Field(0.0, description="Other income (expense), USD millions")
    tax_rate: float
    capex_intensity: float = Field(description="Capex as % of revenue")
    ocf_to_net_income: float = Field(description="Operating cash flow / net income")


class ScenarioResult(BaseModel):
    label: str
    base_year: int
    scenario_year: int
    assumptions: Assumptions
    lines: dict[str, float]
    disclaimer: str = DISCLAIMER


class ScenarioComparison(BaseModel):
    base: ScenarioResult
    scenario: ScenarioResult
    delta: dict[str, float]
    delta_pct: dict[str, float | None]
    assumption_sources: dict[str, str]
    disclaimer: str = DISCLAIMER
    method: str = (
        "Revenue = prior revenue x (1 + growth); gross profit = revenue x gross margin; each opex line grows at its "
        "assumed rate; operating income = gross profit - opex; pre-tax = operating income + other income; "
        "net income = pre-tax x (1 - tax rate); operating cash flow = net income x OCF/NI ratio; "
        "capex = revenue x capex intensity; free cash flow = OCF - capex."
    )


class ScenarioEngine:
    def __init__(self, eng: CalculationEngine | None = None):
        self.eng = eng or CalculationEngine()
        self.base_year = self.eng.repo.latest_year

    def _v(self, m, y=None):
        return self.eng.value(m, y or self.base_year)

    def base_assumptions(self) -> tuple[Assumptions, dict[str, str]]:
        y = self.base_year
        a = Assumptions(
            revenue_growth=self._v("revenue_growth"),
            gross_margin=self._v("gross_margin_pct"),
            rd_growth=(self._v("research_and_development") / self._v("research_and_development", y - 1)) - 1,
            sm_growth=(self._v("sales_and_marketing") / self._v("sales_and_marketing", y - 1)) - 1,
            ga_growth=(self._v("general_and_administrative") / self._v("general_and_administrative", y - 1)) - 1,
            other_income=0.0,
            tax_rate=self._v("effective_tax_rate_calc"),
            capex_intensity=self._v("capex_intensity"),
            ocf_to_net_income=self._v("ocf_to_net_income"),
        )
        src = {
            "revenue_growth": f"FY{y} actual revenue growth (calculated)",
            "gross_margin": f"FY{y} actual gross margin % (calculated)",
            "rd_growth": f"FY{y} actual R&D growth", "sm_growth": f"FY{y} actual S&M growth",
            "ga_growth": f"FY{y} actual G&A growth",
            "other_income": "Set to 0 - non-operating items (e.g. investment gains/losses) are volatile and not extrapolated",
            "tax_rate": f"FY{y} effective tax rate (provision / pre-tax income)",
            "capex_intensity": f"FY{y} capex / revenue", "ocf_to_net_income": f"FY{y} OCF / net income",
        }
        return a, src

    def run(self, a: Assumptions, label: str = "Scenario") -> ScenarioResult:
        y = self.base_year
        rev = self._v("revenue") * (1 + a.revenue_growth)
        gp = rev * a.gross_margin
        rd = self._v("research_and_development") * (1 + a.rd_growth)
        sm = self._v("sales_and_marketing") * (1 + a.sm_growth)
        ga = self._v("general_and_administrative") * (1 + a.ga_growth)
        oi = gp - rd - sm - ga
        pbt = oi + a.other_income
        ni = pbt * (1 - a.tax_rate)
        ocf = ni * a.ocf_to_net_income
        capex = rev * a.capex_intensity
        lines = {"revenue": rev, "cost_of_revenue": rev - gp, "gross_profit": gp, "research_and_development": rd,
                 "sales_and_marketing": sm, "general_and_administrative": ga, "operating_income": oi,
                 "operating_margin": oi / rev, "income_before_tax": pbt, "net_income": ni, "operating_cash_flow": ocf,
                 "capital_expenditure": capex, "free_cash_flow": ocf - capex}
        return ScenarioResult(label=label, base_year=y, scenario_year=y + 1, assumptions=a, lines=lines)

    def compare(self, overrides: dict[str, float] | None = None, deltas: dict[str, float] | None = None) -> ScenarioComparison:
        """overrides: absolute assumption values; deltas: additive shocks (e.g. {'revenue_growth': -0.05})."""
        base_a, src = self.base_assumptions()
        s = base_a.model_dump()
        s.update(overrides or {})
        for k, d in (deltas or {}).items():
            s[k] = s[k] + d
        base = self.run(base_a, "Base case (FY actual ratios carried forward)")
        scen = self.run(Assumptions(**s), "Scenario")
        delta = {k: scen.lines[k] - base.lines[k] for k in base.lines}
        pct = {k: (delta[k] / abs(base.lines[k]) if base.lines[k] and k != "operating_margin" else None) for k in base.lines}
        return ScenarioComparison(base=base, scenario=scen, delta=delta, delta_pct=pct, assumption_sources=src)

    def sensitivity(self, target: str = "operating_income") -> list[dict]:
        """Impact on `target` of a standardised shock to each assumption, ranked by absolute impact."""
        shocks = {"revenue_growth": 0.01, "gross_margin": 0.01, "rd_growth": 0.01, "sm_growth": 0.01, "ga_growth": 0.01,
                  "tax_rate": 0.01, "capex_intensity": 0.01, "ocf_to_net_income": 0.05}
        base_a, _ = self.base_assumptions()
        base_val = self.run(base_a).lines[target]
        rows = []
        for k, shock in shocks.items():
            up = base_a.model_dump(); up[k] += shock
            dn = base_a.model_dump(); dn[k] -= shock
            vu = self.run(Assumptions(**up)).lines[target] - base_val
            vd = self.run(Assumptions(**dn)).lines[target] - base_val
            rows.append({"assumption": k, "shock": f"±{shock * 100:.0f} pp" if k != "ocf_to_net_income" else "±0.05x",
                         "impact_up": vu, "impact_down": vd, "abs_impact": max(abs(vu), abs(vd)), "target": target})
        return sorted(rows, key=lambda r: -r["abs_impact"])
