"""CFO Executive Brief - dashboard KPIs, trends and the 'Financial performance at a glance' summary.

Composed entirely from the calculation engine + copilot handlers, so every number carries a source.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.calculations.engine import CalculationEngine
from src.calculations.models import format_value
from src.copilot import handlers as H
from src.copilot.evidence import Evidence
from src.copilot.intent import Intent

KPI_SPEC = [
    ("revenue", "Revenue", True), ("revenue_growth", "Revenue growth", True), ("gross_margin_pct", "Gross margin", True),
    ("operating_income", "Operating income", True), ("operating_margin_pct", "Operating margin", True), ("net_income", "Net income", True),
    ("operating_cash_flow", "Operating cash flow", True), ("free_cash_flow", "Free cash flow", True),
    ("cash_and_short_term_investments", "Cash & short-term investments", True), ("total_debt", "Total debt", False),
    ("research_and_development", "R&D", None), ("capital_expenditure", "Capex", None),
]


@dataclass
class KPI:
    metric_id: str
    label: str
    value: float | None
    display: str
    unit: str
    prior: float | None
    change_display: str
    direction: str
    favourable: bool | None
    series: dict[int, float | None]
    source: str
    formula: str


@dataclass
class ExecutiveBrief:
    fiscal_year: int
    prior_year: int
    kpis: list[KPI]
    trends: dict[str, dict[str, dict[int, float | None]]]
    sections: dict[str, Evidence] = field(default_factory=dict)
    at_a_glance: list[dict] = field(default_factory=list)


def _kpi(eng: CalculationEngine, mid: str, label: str, up_good, fy: int, years: list[int]) -> KPI:
    v = eng.variance(mid, fy, fy - 1)
    m = eng.calculate(mid, fy)
    unit = v.unit or m.unit
    if v.absolute_change is None:
        ch = "n/a"
    elif unit == "%":
        ch = format_value(v.absolute_change, "pp")
    else:
        ch = f"{v.pct_change:+.1%}" if v.pct_change is not None else "n/a"
    src = "; ".join(sorted({f"{i.document} p.{i.page}" for i in m.inputs})) if m.inputs else "n/a"
    fav = None if up_good is None or v.absolute_change is None else ((v.absolute_change > 0) == up_good)
    return KPI(mid, label, m.value, m.display(1), unit, v.prior, ch, v.direction, fav, eng.series(mid, years), src, m.formula)


def build_brief(eng: CalculationEngine | None = None, fy: int | None = None) -> ExecutiveBrief:
    eng = eng or CalculationEngine()
    fy = fy or eng.repo.latest_year
    years = [y for y in eng.repo.years("revenue") if y <= fy]
    kpis = [_kpi(eng, m, l, g, fy, years) for m, l, g in KPI_SPEC]
    trends = {
        "Revenue trend": {"Revenue": eng.series("revenue", years), "Operating income": eng.series("operating_income", years),
                          "Net income": eng.series("net_income", years)},
        "Margin trend": {"Gross margin %": eng.series("gross_margin_pct", years), "Operating margin %": eng.series("operating_margin_pct", years),
                         "Net margin %": eng.series("net_margin_pct", years)},
        "Cash-flow trend": {"Operating cash flow": eng.series("operating_cash_flow", years), "Capex": eng.series("capital_expenditure", years),
                            "Free cash flow": eng.series("free_cash_flow", years)},
        "Investment trend": {"R&D % revenue": eng.series("rd_pct_revenue", years), "Capex % revenue": eng.series("capex_intensity", years)},
    }
    seg_years = [y for y in eng.repo.years("segment_revenue", "IC") if y <= fy]
    trends["Segment revenue"] = {name: eng.series("segment_revenue", seg_years, seg) for seg, name in eng.segments()}
    it = Intent("brief", fiscal_year=fy, prior_year=fy - 1)
    sections = {
        "What changed?": H.biggest_changes(eng, it),
        "Why did it change?": H.profitability_bridge(eng, Intent("profitability_bridge", fiscal_year=fy, prior_year=fy - 1)),
        "Where is management investing?": H.investment(eng, it),
        "Cash flow": H.cash_flow(eng, it),
        "Segment analysis": H.segment(eng, Intent("segment", fiscal_year=fy, prior_year=fy - 1), "which segment contributed"),
        "What financial risks are visible?": H.risks(eng, it),
        "What requires CFO attention?": H.cfo_attention(eng, it),
        "Scenario: revenue growth −5 pp": H.scenario(eng, Intent("scenario", fiscal_year=fy), deltas={"revenue_growth": -0.05}, overrides={}),
    }
    glance = [{"question": q, "answer": sections[q].headline, "confidence": sections[q].confidence, "basis": " / ".join(sections[q].basis)}
              for q in ["What changed?", "Why did it change?", "Where is management investing?", "What financial risks are visible?",
                        "What requires CFO attention?"]]
    return ExecutiveBrief(fy, fy - 1, kpis, trends, sections, glance)
