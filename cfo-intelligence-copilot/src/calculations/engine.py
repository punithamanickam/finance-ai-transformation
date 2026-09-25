"""Deterministic financial calculation engine.

The LLM never computes a financial metric. Every metric below is defined once - formula text, inputs and a
pure Python function - and evaluated against the financial repository. Missing inputs produce
``status = unavailable`` (never an invented number); conflicting inputs produce ``status = blocked``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.calculations.models import CalculatedMetric, InputRef, Variance, format_value
from src.financial_model.repository import DataConflict, DataUnavailable, FinancialRepository, get_repository


@dataclass
class In:
    alias: str
    metric_id: str
    year_offset: int = 0  # 0 = current year, -1 = prior year
    member: str = ""
    optional: bool = False


@dataclass
class MetricDef:
    metric_id: str
    name: str
    unit: str
    formula: str
    inputs: list[In]
    fn: Callable[[dict], float]
    note: str = ""
    is_proxy: bool = False
    derived_inputs: list[tuple[str, str, int]] = field(default_factory=list)  # (alias, calc metric_id, offset)


def _debt(v):
    return v["short_term_debt"] + v["long_term_debt"]


def _nopat(v, suffix=""):
    etr = v["income_tax" + suffix] / v["income_before_tax" + suffix]
    return v["operating_income" + suffix] * (1 - etr)


def _ic(v, suffix=""):
    return (v["shareholders_equity" + suffix] + v["short_term_debt" + suffix] + v["long_term_debt" + suffix]
            - v["cash_and_short_term_investments" + suffix])


METRICS: dict[str, MetricDef] = {m.metric_id: m for m in [
    MetricDef("revenue_growth", "Revenue growth (YoY)", "%", "(Revenue[t] - Revenue[t-1]) / Revenue[t-1]",
              [In("revenue", "revenue"), In("revenue_prior", "revenue", -1)],
              lambda v: (v["revenue"] - v["revenue_prior"]) / v["revenue_prior"]),
    MetricDef("gross_margin_pct", "Gross margin %", "%", "Gross margin / Revenue",
              [In("gross_profit", "gross_profit"), In("revenue", "revenue")], lambda v: v["gross_profit"] / v["revenue"]),
    MetricDef("operating_margin_pct", "Operating margin %", "%", "Operating income / Revenue",
              [In("operating_income", "operating_income"), In("revenue", "revenue")],
              lambda v: v["operating_income"] / v["revenue"]),
    MetricDef("net_margin_pct", "Net margin %", "%", "Net income / Revenue",
              [In("net_income", "net_income"), In("revenue", "revenue")], lambda v: v["net_income"] / v["revenue"]),
    MetricDef("total_operating_expenses", "Total operating expenses", "USD millions",
              "Research and development + Sales and marketing + General and administrative",
              [In("research_and_development", "research_and_development"), In("sales_and_marketing", "sales_and_marketing"),
               In("general_and_administrative", "general_and_administrative")],
              lambda v: v["research_and_development"] + v["sales_and_marketing"] + v["general_and_administrative"]),
    MetricDef("opex_pct_revenue", "Operating expenses as % of revenue", "%", "(R&D + S&M + G&A) / Revenue",
              [In("research_and_development", "research_and_development"), In("sales_and_marketing", "sales_and_marketing"),
               In("general_and_administrative", "general_and_administrative"), In("revenue", "revenue")],
              lambda v: (v["research_and_development"] + v["sales_and_marketing"] + v["general_and_administrative"]) / v["revenue"]),
    MetricDef("rd_pct_revenue", "R&D as % of revenue", "%", "Research and development / Revenue",
              [In("research_and_development", "research_and_development"), In("revenue", "revenue")],
              lambda v: v["research_and_development"] / v["revenue"]),
    MetricDef("sm_pct_revenue", "Sales & marketing as % of revenue", "%", "Sales and marketing / Revenue",
              [In("sales_and_marketing", "sales_and_marketing"), In("revenue", "revenue")],
              lambda v: v["sales_and_marketing"] / v["revenue"]),
    MetricDef("ga_pct_revenue", "G&A as % of revenue", "%", "General and administrative / Revenue",
              [In("general_and_administrative", "general_and_administrative"), In("revenue", "revenue")],
              lambda v: v["general_and_administrative"] / v["revenue"]),
    MetricDef("ebitda_proxy", "EBITDA proxy", "USD millions",
              "Operating income + Depreciation, amortization, and other (cash flow statement)",
              [In("operating_income", "operating_income"), In("depreciation_amortization_other", "depreciation_amortization_other")],
              lambda v: v["operating_income"] + v["depreciation_amortization_other"], is_proxy=True,
              note="Not a reported GAAP measure. The cash flow line 'Depreciation, amortization, and other' may include items other than D&A, so this is an approximation."),
    MetricDef("ebitda_proxy_margin", "EBITDA proxy margin", "%",
              "(Operating income + Depreciation, amortization, and other) / Revenue",
              [In("operating_income", "operating_income"), In("depreciation_amortization_other", "depreciation_amortization_other"), In("revenue", "revenue")],
              lambda v: (v["operating_income"] + v["depreciation_amortization_other"]) / v["revenue"], is_proxy=True,
              note="Proxy - see EBITDA proxy."),
    MetricDef("operating_cash_flow_margin", "Operating cash flow margin", "%", "Net cash from operations / Revenue",
              [In("operating_cash_flow", "operating_cash_flow"), In("revenue", "revenue")],
              lambda v: v["operating_cash_flow"] / v["revenue"]),
    MetricDef("free_cash_flow", "Free cash flow", "USD millions", "Net cash from operations - Additions to property and equipment",
              [In("operating_cash_flow", "operating_cash_flow"), In("capital_expenditure", "capital_expenditure")],
              lambda v: v["operating_cash_flow"] - v["capital_expenditure"],
              note="Analyst definition (OCF - capex). Excludes finance-lease principal payments; may differ from company-defined measures."),
    MetricDef("free_cash_flow_margin", "Free cash flow margin", "%", "(Net cash from operations - Capex) / Revenue",
              [In("operating_cash_flow", "operating_cash_flow"), In("capital_expenditure", "capital_expenditure"), In("revenue", "revenue")],
              lambda v: (v["operating_cash_flow"] - v["capital_expenditure"]) / v["revenue"]),
    MetricDef("cash_conversion", "Cash conversion (FCF / net income)", "x", "(Net cash from operations - Capex) / Net income",
              [In("operating_cash_flow", "operating_cash_flow"), In("capital_expenditure", "capital_expenditure"), In("net_income", "net_income")],
              lambda v: (v["operating_cash_flow"] - v["capital_expenditure"]) / v["net_income"]),
    MetricDef("ocf_to_net_income", "Operating cash flow / net income", "x", "Net cash from operations / Net income",
              [In("operating_cash_flow", "operating_cash_flow"), In("net_income", "net_income")],
              lambda v: v["operating_cash_flow"] / v["net_income"]),
    MetricDef("capex_intensity", "Capex intensity", "%", "Additions to property and equipment / Revenue",
              [In("capital_expenditure", "capital_expenditure"), In("revenue", "revenue")],
              lambda v: v["capital_expenditure"] / v["revenue"]),
    MetricDef("capex_reinvestment_rate", "Capex as % of operating cash flow", "%", "Additions to property and equipment / Net cash from operations",
              [In("capital_expenditure", "capital_expenditure"), In("operating_cash_flow", "operating_cash_flow")],
              lambda v: v["capital_expenditure"] / v["operating_cash_flow"]),
    MetricDef("current_ratio", "Current ratio", "x", "Total current assets / Total current liabilities",
              [In("current_assets", "current_assets"), In("current_liabilities", "current_liabilities")],
              lambda v: v["current_assets"] / v["current_liabilities"]),
    MetricDef("total_debt", "Total debt", "USD millions", "Current portion of long-term debt + Long-term debt",
              [In("short_term_debt", "short_term_debt"), In("long_term_debt", "long_term_debt")], _debt,
              note="Excludes operating and finance lease liabilities."),
    MetricDef("debt_to_equity", "Debt-to-equity", "x", "(Current portion of long-term debt + Long-term debt) / Total stockholders' equity",
              [In("short_term_debt", "short_term_debt"), In("long_term_debt", "long_term_debt"), In("shareholders_equity", "shareholders_equity")],
              lambda v: _debt(v) / v["shareholders_equity"], note="Excludes lease liabilities."),
    MetricDef("net_debt", "Net debt (negative = net cash)", "USD millions",
              "(Current portion of long-term debt + Long-term debt) - Total cash, cash equivalents, and short-term investments",
              [In("short_term_debt", "short_term_debt"), In("long_term_debt", "long_term_debt"),
               In("cash_and_short_term_investments", "cash_and_short_term_investments")],
              lambda v: _debt(v) - v["cash_and_short_term_investments"], note="Excludes lease liabilities and equity investments."),
    MetricDef("effective_tax_rate_calc", "Effective tax rate (calculated)", "%", "Provision for income taxes / Income before income taxes",
              [In("income_tax", "income_tax"), In("income_before_tax", "income_before_tax")],
              lambda v: v["income_tax"] / v["income_before_tax"]),
    MetricDef("roic_proxy", "ROIC proxy", "%",
              "NOPAT / average invested capital; NOPAT = Operating income x (1 - tax provision / pre-tax income); "
              "invested capital = equity + total debt - cash & short-term investments",
              [In("operating_income", "operating_income"), In("income_tax", "income_tax"), In("income_before_tax", "income_before_tax"),
               In("shareholders_equity", "shareholders_equity"), In("short_term_debt", "short_term_debt"), In("long_term_debt", "long_term_debt"),
               In("cash_and_short_term_investments", "cash_and_short_term_investments"),
               In("shareholders_equity_prior", "shareholders_equity", -1), In("short_term_debt_prior", "short_term_debt", -1),
               In("long_term_debt_prior", "long_term_debt", -1), In("cash_and_short_term_investments_prior", "cash_and_short_term_investments", -1)],
              lambda v: _nopat(v) / ((_ic(v) + _ic(v, "_prior")) / 2), is_proxy=True,
              note="Simplified proxy: excludes lease liabilities, equity investments and goodwill adjustments; uses the effective tax rate."),
    MetricDef("revenue_per_employee", "Revenue per employee", "USD thousands", "Revenue / Full-time employees (year end)",
              [In("revenue", "revenue"), In("employees", "employees")], lambda v: v["revenue"] * 1000 / v["employees"],
              note="Headcount is extracted from Item 1 narrative text (not XBRL-tagged) and is a year-end figure."),
    MetricDef("operating_leverage", "Degree of operating leverage", "x", "Operating income growth / Revenue growth",
              [In("operating_income", "operating_income"), In("operating_income_prior", "operating_income", -1),
               In("revenue", "revenue"), In("revenue_prior", "revenue", -1)],
              lambda v: ((v["operating_income"] - v["operating_income_prior"]) / v["operating_income_prior"])
              / ((v["revenue"] - v["revenue_prior"]) / v["revenue_prior"]),
              note=">1.0x means operating income grew faster than revenue (positive operating leverage)."),
]}

# metrics treated as ratios in variance analysis (change expressed in percentage points)
RATIO_UNITS = {"%"}

# variance direction: +1 = an increase is favourable, -1 = unfavourable, 0 = neutral
FAVOURABILITY = {
    "revenue": 1, "gross_profit": 1, "operating_income": 1, "net_income": 1, "operating_cash_flow": 1, "free_cash_flow": 1,
    "cost_of_revenue": -1, "research_and_development": 0, "sales_and_marketing": -1, "general_and_administrative": -1,
    "capital_expenditure": 0, "total_operating_expenses": -1, "gross_margin_pct": 1, "operating_margin_pct": 1,
    "net_margin_pct": 1, "eps_diluted": 1, "cash_and_short_term_investments": 1, "total_debt": -1,
    "free_cash_flow_margin": 1, "income_tax": -1,
}


class CalculationEngine:
    def __init__(self, repo: FinancialRepository | None = None):
        self.repo = repo or get_repository()

    # ---- raw facts -------------------------------------------------------------------------------------------
    def fact_input(self, alias: str, metric_id: str, fy: int, member: str = "") -> InputRef:
        f = self.repo.get(metric_id, fy, member)
        return InputRef(alias=alias, label=f.metric_label + (f" - {f.dimension_label}" if f.dimension_label else ""),
                        fiscal_year=fy, value=f.value, unit=f.unit, fact_key=f.fact_key, document=f.source_document,
                        section=f.source_section, table=f.source_table, page=f.source_page, url=f.source_url)

    def value(self, metric_id: str, fy: int, member: str = "") -> float | None:
        """Reported fact value, or a calculated metric value, or None."""
        if metric_id in METRICS:
            r = self.calculate(metric_id, fy)
            return r.value if r.ok else None
        try:
            return self.repo.get(metric_id, fy, member).value
        except (DataUnavailable, DataConflict):
            return None

    def reported(self, metric_id: str, fy: int, member: str = "") -> CalculatedMetric:
        """Wrap a reported fact as a CalculatedMetric (identity formula) so callers handle one type."""
        try:
            ref = self.fact_input(metric_id, metric_id, fy, member)
        except DataUnavailable:
            return CalculatedMetric(metric_id=metric_id, name=metric_id, fiscal_year=fy, value=None, unit="",
                                    formula="reported value", status="unavailable",
                                    note="I could not find sufficient evidence in the available public filings.")
        except DataConflict as e:
            return CalculatedMetric(metric_id=metric_id, name=metric_id, fiscal_year=fy, value=None, unit="",
                                    formula="reported value", status="blocked", note=str(e))
        return CalculatedMetric(metric_id=metric_id, name=ref.label, fiscal_year=fy, value=ref.value, unit=ref.unit,
                                formula="Reported value", formula_with_values=format_value(ref.value, ref.unit), inputs=[ref])

    # ---- calculated metrics ----------------------------------------------------------------------------------
    def calculate(self, metric_id: str, fy: int) -> CalculatedMetric:
        if metric_id not in METRICS:
            return self.reported(metric_id, fy)
        d = METRICS[metric_id]
        refs, vals = [], {}
        for spec in d.inputs:
            year = fy + spec.year_offset
            try:
                ref = self.fact_input(spec.alias, spec.metric_id, year, spec.member)
            except DataUnavailable:
                return CalculatedMetric(metric_id=metric_id, name=d.name, fiscal_year=fy, value=None, unit=d.unit, formula=d.formula,
                                        inputs=refs, status="unavailable", is_proxy=d.is_proxy,
                                        note=f"Required input '{spec.metric_id}' for FY{year} is not in the loaded public filings - metric not calculated.")
            except DataConflict as e:
                return CalculatedMetric(metric_id=metric_id, name=d.name, fiscal_year=fy, value=None, unit=d.unit, formula=d.formula,
                                        inputs=refs, status="blocked", note=str(e), is_proxy=d.is_proxy)
            refs.append(ref)
            vals[spec.alias] = ref.value
        result = d.fn(vals)
        expanded = "; ".join(f"{r.label} FY{r.fiscal_year} = {r.value:,.2f} ({r.unit}, p.{r.page})" for r in refs)
        return CalculatedMetric(metric_id=metric_id, name=d.name, fiscal_year=fy, value=result, unit=d.unit, formula=d.formula,
                                formula_with_values=expanded, inputs=refs, note=d.note, is_proxy=d.is_proxy)

    # ---- time series helpers ------------------------------------------------------------------------------------
    def variance(self, metric_id: str, fy: int, prior: int | None = None, member: str = "") -> Variance:
        prior = prior or fy - 1
        if metric_id in METRICS:
            cur_m, pri_m = self.calculate(metric_id, fy), self.calculate(metric_id, prior)
        elif member:
            cur_m, pri_m = self.reported(metric_id, fy, member), self.reported(metric_id, prior, member)
        else:
            cur_m, pri_m = self.reported(metric_id, fy), self.reported(metric_id, prior)
        unit = cur_m.unit or pri_m.unit
        label = cur_m.name if cur_m.ok else pri_m.name
        if not (cur_m.ok and pri_m.ok):
            bad = cur_m if not cur_m.ok else pri_m
            return Variance(metric_id=metric_id, label=label, unit=unit, current_year=fy, prior_year=prior, current=cur_m.value,
                            prior=pri_m.value, absolute_change=None, pct_change=None, direction="n/a", favourable=None,
                            status=bad.status, note=bad.note, inputs=cur_m.inputs + pri_m.inputs)
        c, p = cur_m.value, pri_m.value
        absolute = c - p
        is_ratio = unit in RATIO_UNITS or unit == "x"
        pct = None if is_ratio or p == 0 else absolute / abs(p)
        direction = "flat" if abs(absolute) < 1e-9 else ("up" if absolute > 0 else "down")
        fav_sign = FAVOURABILITY.get(metric_id, 0)
        favourable = None if fav_sign == 0 or direction == "flat" else (absolute > 0) == (fav_sign > 0)
        formula = ("Current - Prior (percentage points)" if unit in RATIO_UNITS else
                   "Absolute = Current - Prior; % = (Current - Prior) / |Prior|")
        return Variance(metric_id=metric_id, label=label, unit=unit, current_year=fy, prior_year=prior, current=c, prior=p,
                        absolute_change=absolute, pct_change=pct, direction=direction, favourable=favourable,
                        inputs=cur_m.inputs + pri_m.inputs, formula=formula)

    def cagr(self, metric_id: str, start: int, end: int, member: str = "") -> CalculatedMetric:
        a = self.reported(metric_id, start, member) if metric_id not in METRICS else self.calculate(metric_id, start)
        b = self.reported(metric_id, end, member) if metric_id not in METRICS else self.calculate(metric_id, end)
        name = f"{a.name if a.ok else metric_id} CAGR FY{start}-FY{end}"
        if not (a.ok and b.ok) or end <= start or a.value <= 0:
            return CalculatedMetric(metric_id=f"{metric_id}_cagr", name=name, fiscal_year=end, value=None, unit="%",
                                    formula="(End / Start)^(1 / years) - 1", status="unavailable",
                                    note="Insufficient data in the loaded filings for this period.")
        n = end - start
        val = (b.value / a.value) ** (1 / n) - 1
        return CalculatedMetric(metric_id=f"{metric_id}_cagr", name=name, fiscal_year=end, value=val, unit="%",
                                formula=f"(Value FY{end} / Value FY{start})^(1/{n}) - 1",
                                formula_with_values=f"({b.value:,.0f} / {a.value:,.0f})^(1/{n}) - 1",
                                inputs=a.inputs + b.inputs)

    def series(self, metric_id: str, years: list[int], member: str = "") -> dict[int, float | None]:
        return {y: self.value(metric_id, y, member) for y in years}

    # ---- segments ---------------------------------------------------------------------------------------------
    def segments(self) -> list[tuple[str, str]]:
        m = self.repo.members("segment_revenue")
        return list(zip(m.dimension_member, m.dimension_label))

    def segment_table(self, fy: int) -> list[dict]:
        rows = []
        total_c = self.value("revenue", fy)
        total_p = self.value("revenue", fy - 1)
        for seg, name in self.segments():
            rc, rp = self.value("segment_revenue", fy, seg), self.value("segment_revenue", fy - 1, seg)
            oc, op = self.value("segment_operating_income", fy, seg), self.value("segment_operating_income", fy - 1, seg)
            refs = []
            for mid in ["segment_revenue", "segment_operating_income"]:
                for y in [fy, fy - 1]:
                    try:
                        refs.append(self.fact_input(mid, mid, y, seg))
                    except (DataUnavailable, DataConflict):
                        pass
            row = {"segment_id": seg, "segment": name, "revenue": rc, "revenue_prior": rp, "operating_income": oc,
                   "operating_income_prior": op, "inputs": refs}
            row["revenue_growth"] = (rc - rp) / rp if rc is not None and rp else None
            row["operating_margin"] = oc / rc if oc is not None and rc else None
            row["operating_margin_prior"] = op / rp if op is not None and rp else None
            row["share_of_revenue"] = rc / total_c if rc is not None and total_c else None
            d_total = (total_c - total_p) if total_c is not None and total_p is not None else None
            row["contribution_to_growth"] = (rc - rp) / d_total if rc is not None and rp is not None and d_total else None
            row["growth_contribution_pp"] = (rc - rp) / total_p if rc is not None and rp is not None and total_p else None
            row["operating_income_growth"] = (oc - op) / op if oc is not None and op else None
            rows.append(row)
        return rows
