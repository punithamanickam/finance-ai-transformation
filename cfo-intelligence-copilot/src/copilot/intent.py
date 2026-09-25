"""Intent detection and financial-metric identification (deterministic, rule-based, auditable).

A rules-first router is a deliberate governance choice: the mapping from a question to the metrics and
calculations used is explainable and testable. An LLM classifier can be added behind the same interface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# phrase -> canonical metric (longest phrases first when matching)
METRIC_SYNONYMS: dict[str, str] = {
    "free cash flow margin": "free_cash_flow_margin", "fcf margin": "free_cash_flow_margin",
    "free cash flow": "free_cash_flow", "fcf": "free_cash_flow",
    "operating cash flow margin": "operating_cash_flow_margin",
    "operating cash flow": "operating_cash_flow", "cash from operations": "operating_cash_flow", "ocf": "operating_cash_flow",
    "gross margin %": "gross_margin_pct", "gross margin percentage": "gross_margin_pct", "gross margin": "gross_margin_pct",
    "gross profit": "gross_profit",
    "operating margin": "operating_margin_pct", "operating income": "operating_income", "operating profit": "operating_income", "ebit ": "operating_income",
    "net margin": "net_margin_pct", "net income": "net_income", "profit": "net_income", "earnings per share": "eps_diluted", "eps": "eps_diluted",
    "ebitda": "ebitda_proxy",
    "total revenue": "revenue", "revenue per employee": "revenue_per_employee", "revenue growth": "revenue_growth", "revenue": "revenue", "sales": "revenue", "top line": "revenue",
    "cost of revenue": "cost_of_revenue", "cogs": "cost_of_revenue",
    "research and development": "research_and_development", "r&d": "research_and_development",
    "sales and marketing": "sales_and_marketing", "s&m": "sales_and_marketing",
    "general and administrative": "general_and_administrative", "g&a": "general_and_administrative",
    "operating expenses": "total_operating_expenses", "opex": "total_operating_expenses",
    "capital expenditure": "capital_expenditure", "capital expenditures": "capital_expenditure", "capex": "capital_expenditure",
    "capex intensity": "capex_intensity",
    "cash conversion": "cash_conversion", "current ratio": "current_ratio", "debt-to-equity": "debt_to_equity", "debt to equity": "debt_to_equity",
    "net debt": "net_debt", "total debt": "total_debt", "debt": "total_debt", "roic": "roic_proxy", "return on invested capital": "roic_proxy",
    "effective tax rate": "effective_tax_rate_calc", "tax rate": "effective_tax_rate_calc", "income tax": "income_tax",
    "employees": "employees", "headcount": "employees",
    "microsoft cloud": "microsoft_cloud_revenue", "cash": "cash_and_short_term_investments",
    "goodwill": "goodwill", "total assets": "total_assets", "equity": "shareholders_equity",
    "other income": "other_income_expense", "dividends": "dividends_paid", "buybacks": "share_repurchases", "share repurchases": "share_repurchases",
}


@dataclass
class Intent:
    name: str
    metrics: list[str] = field(default_factory=list)
    fiscal_year: int | None = None
    prior_year: int | None = None
    scenario: dict = field(default_factory=dict)
    sub: str = ""  # sub-intent detail (e.g. "highest_margin")
    matched_rule: str = ""


def find_metrics(q: str) -> list[str]:
    ql = f" {q.lower()} "
    found: list[str] = []
    for phrase in sorted(METRIC_SYNONYMS, key=len, reverse=True):
        pat = r"(?<![a-z&])" + re.escape(phrase.strip()) + r"(?![a-z&])"
        if re.search(pat, ql):
            mid = METRIC_SYNONYMS[phrase]
            if mid not in found:
                found.append(mid)
            ql = re.sub(pat, " ", ql)
    return found


def find_years(q: str) -> list[int]:
    ys = [int(y) for y in re.findall(r"(?<!\d)(20[12]\d)(?!\d)", q.lower())]
    ys += [2000 + int(y) for y in re.findall(r"\bfy\s?(\d{2})(?!\d)", q.lower())]
    return list(dict.fromkeys(ys))


def parse_scenario(q: str) -> dict:
    """Extract scenario shocks/overrides. Returns {'deltas': {...}, 'overrides': {...}}."""
    ql = q.lower()
    deltas, overrides = {}, {}
    names = {"revenue growth": "revenue_growth", "revenue": "revenue_growth", "gross margin": "gross_margin", "r&d": "rd_growth",
             "research and development": "rd_growth", "sales and marketing": "sm_growth", "s&m": "sm_growth",
             "g&a": "ga_growth", "general and administrative": "ga_growth", "tax rate": "tax_rate", "capex": "capex_intensity",
             "capital expenditure": "capex_intensity", "operating expense": "opex_growth", "opex": "opex_growth"}
    for phrase, key in sorted(names.items(), key=lambda kv: -len(kv[0])):
        if phrase not in ql:
            continue
        seg = ql[ql.find(phrase):ql.find(phrase) + 90]
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:percentage points?|pp|points?|%)\s*(lower|higher|less|more|down|up|lower than|higher than)", seg)
        m2 = re.search(r"(decreas|declin|fall|drop|reduc|lower|increas|rise|higher|grow)\w*\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*(?:percentage points?|pp|points?|%)", seg)
        m3 = re.search(r"(?:is|of|at|to|grows?|growth of|=)\s*(\d+(?:\.\d+)?)\s*%", seg)
        if m:
            sign = -1 if m.group(2).startswith(("lower", "less", "down")) else 1
            deltas[key] = sign * float(m.group(1)) / 100
        elif m2 and key.endswith("_growth") and m2.group(1).startswith(("grow", "rise")) and "p" not in seg[m2.end() - 3:m2.end()]:
            overrides[key] = float(m2.group(2)) / 100  # "R&D grows 20%" sets the growth rate
        elif m2:
            sign = -1 if m2.group(1).startswith(("decreas", "declin", "fall", "drop", "reduc", "lower")) else 1
            deltas[key] = sign * float(m2.group(2)) / 100
        elif m3 and not re.search(r"constant|unchanged|flat|same", seg[:40]):
            overrides[key] = float(m3.group(1)) / 100
        ql = ql.replace(phrase, " " * len(phrase), 1)
    for k in ("opex_growth",):
        for d in (deltas, overrides):
            if k in d:
                v = d.pop(k)
                d.update({"rd_growth": v, "sm_growth": v, "ga_growth": v})
    return {"deltas": deltas, "overrides": overrides}


RULES: list[tuple[str, str, str]] = [
    # (intent, sub, regex) - evaluated in order
    ("profitability_bridge", "", r"bridge|revenue growth and operating[- ]income growth|relationship between revenue growth and operating income"),
    ("show_calculation", "", r"how (did|do) you (calculate|compute|get)|show (me )?(exactly )?how you calculated|show (me )?the (calculation|formula|math)"),
    ("show_source", "", r"^\W*(now,? |and |ok,? )?(show (me )?(the )?(source|evidence)|where (does|did) (this|that))|evidence behind"),
    ("sensitivity", "", r"sensitiv|which assumptions?"),
    ("scenario", "", r"scenario|assume|what if|suppose|simulate|if revenue growth|stress"),
    ("forecast_request", "", r"\b(forecast|predict|guidance for|next year's (revenue|earnings)|will (revenue|earnings|profit|margin)s? (be|grow))\b"),
    ("operating_leverage", "", r"operating leverage"),
    ("brief", "", r"executive brief|cfo brief|at a glance"),
    ("biggest_changes", "", r"(three|3|biggest|largest|major) (biggest |largest )?(financial )?changes|what changed in (the company'?s )?financial performance|what changed\??$|financial performance"),
    ("cfo_attention", "", r"investigate|requires? (cfo )?attention|red flags?|what should the cfo|concern"),
    ("risks", "", r"\brisks?\b"),
    ("opportunities", "", r"opportunit|upside"),
    ("segment", "contribution", r"segment.*(contribut|drove|drive|driving)|(contribut|drove|drive).*segment|growth came from each segment|which segment"),
    ("segment", "", r"segment|intelligent cloud|productivity and business|more personal computing"),
    ("expenses", "", r"expense (movement|categor|line)|largest expense|biggest expense|which (operating )?expense|expenses? (grow|growing|increase)|opex (grow|vs)|expenses growing faster|cost (movement|base|structure|drivers)"),
    ("margin_drivers", "operating", r"(why|what).*(operating margin)|operating margin.*(change|trend|driv)|margin trend"),
    ("margin_drivers", "gross", r"(why|what).*(gross margin)|gross margin.*(driv|chang)"),
    ("oi_drivers", "", r"(why|what).*(operating income)|operating income.*(increase|driv|change)"),
    ("cash_flow", "", r"cash[- ]flow|reinvest|cash conversion|compare with net income|fcf vs|free cash flow compare"),
    ("cash_position", "", r"how much cash|cash position|liquidity|balance sheet strength|cash (balance|on hand)"),
    ("investment", "", r"invest(ing|ment)|where is management|r&d|research and development|capex|capital expenditure|spend"),
    ("comparison", "", r"\bcompare\b|\bversus\b|\bvs\.?\b"),
]


def detect_intent(question: str, default_fy: int) -> Intent:
    q = question.strip()
    ql = q.lower()
    metrics = find_metrics(q)
    years = sorted(find_years(q), reverse=True)
    fy = years[0] if years else default_fy
    prior = years[1] if len(years) > 1 else fy - 1
    for name, sub, pat in RULES:
        if re.search(pat, ql):
            intent = Intent(name, metrics, fy, prior, sub=sub, matched_rule=pat)
            if name == "scenario":
                intent.scenario = parse_scenario(q)
            if name == "comparison" and not metrics:
                intent.metrics = []
            # a metric-specific "how did X change" beats generic investment wording
            if name in {"investment"} and any(k in ql for k in ("grow", "change", "changed", "increase")) and metrics and not re.search(r"where|how much is", ql):
                return Intent("metric_change", metrics, fy, prior, matched_rule="metric+change")
            return intent
    if metrics:
        return Intent("metric_change", metrics, fy, prior, matched_rule="metric mention")
    return Intent("document_qa", [], fy, prior, matched_rule="fallback: retrieval over filing text")
