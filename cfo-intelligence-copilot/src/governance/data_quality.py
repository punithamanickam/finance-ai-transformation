"""Automated data-quality controls over the financial model. Used by the test-suite and to write
``docs/data_quality_report.md``."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from src import settings
from src.financial_model.repository import FinancialRepository

TOL = 1.0  # USD millions - reported figures are rounded to the nearest million


@dataclass
class Check:
    category: str
    name: str
    fiscal_year: int | None
    expected: float | None
    actual: float | None
    passed: bool
    detail: str = ""


def _v(repo: FinancialRepository, m: str, fy: int, member: str = "") -> float | None:
    k = f"{m}|FY{fy}|{member}"
    r = repo._index.get(k)
    return None if r is None else float(r["value"])


def _eq(cat, name, fy, expected, actual, detail="", tol=TOL) -> Check | None:
    if expected is None or actual is None:
        return None
    return Check(cat, name, fy, expected, actual, abs(expected - actual) <= tol, detail)


def run_checks(repo: FinancialRepository | None = None) -> list[Check]:
    repo = repo or FinancialRepository()
    df = repo.df
    out: list[Check] = []
    add = lambda c: out.append(c) if c else None  # noqa: E731
    bs_years = repo.years("total_assets")
    is_years = repo.years("revenue")
    cf_years = repo.years("operating_cash_flow")

    for fy in bs_years:
        add(_eq("Balance sheet", "Total assets = Total liabilities and stockholders' equity", fy,
                _v(repo, "total_assets", fy), _v(repo, "total_liabilities_and_equity", fy)))
        tl, eq = _v(repo, "total_liabilities", fy), _v(repo, "shareholders_equity", fy)
        if tl is not None and eq is not None:
            add(_eq("Balance sheet", "Total liabilities + Stockholders' equity = Total assets", fy, _v(repo, "total_assets", fy), tl + eq))
        add(_eq("Balance sheet", "Cash & equivalents + short-term investments = Total cash and short-term investments", fy,
                _v(repo, "cash_and_short_term_investments", fy),
                (_v(repo, "cash_and_equivalents", fy) or 0) + (_v(repo, "short_term_investments", fy) or 0)))
        add(_eq("Cash flow", "Cash flow ending cash = Balance sheet cash and cash equivalents", fy,
                _v(repo, "cash_and_equivalents", fy), _v(repo, "cash_end_of_period", fy)))

    for fy in cf_years:
        parts = [_v(repo, m, fy) for m in ["operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "fx_effect_on_cash"]]
        if None not in parts:
            add(_eq("Cash flow", "Operating + investing + financing + FX = Net change in cash", fy, _v(repo, "net_change_in_cash", fy), sum(parts)))
        c0, c1 = _v(repo, "cash_end_of_period", fy - 1), _v(repo, "cash_end_of_period", fy)
        if c0 is not None and c1 is not None:
            add(_eq("Cash flow", "Opening cash + net change = Closing cash", fy, c1, c0 + (_v(repo, "net_change_in_cash", fy) or 0)))

    for fy in is_years:
        rev = _v(repo, "revenue", fy)
        add(_eq("Revenue", "Product + Service and other revenue = Total revenue", fy, rev,
                (_v(repo, "revenue_product", fy) or 0) + (_v(repo, "revenue_service", fy) or 0)))
        segs = [_v(repo, "segment_revenue", fy, s) for s in ["PBP", "IC", "MPC"]]
        if None not in segs:
            add(_eq("Segments", "Sum of segment revenue = Total revenue", fy, rev, sum(segs)))
        segoi = [_v(repo, "segment_operating_income", fy, s) for s in ["PBP", "IC", "MPC"]]
        if None not in segoi:
            add(_eq("Segments", "Sum of segment operating income = Total operating income", fy, _v(repo, "operating_income", fy), sum(segoi)))
        segcor = [_v(repo, "segment_cost_of_revenue", fy, s) for s in ["PBP", "IC", "MPC"]]
        if None not in segcor:
            add(_eq("Segments", "Sum of segment cost of revenue = Total cost of revenue", fy, _v(repo, "cost_of_revenue", fy), sum(segcor)))
        geo = [_v(repo, "revenue_us", fy), _v(repo, "revenue_other_countries", fy)]
        if None not in geo:
            add(_eq("Revenue", "United States + Other countries revenue = Total revenue", fy, rev, sum(geo)))
        offs = df[(df.metric_id == "revenue_by_offering") & (df.fiscal_year == fy)]
        if len(offs) >= 5:
            add(_eq("Revenue", "Sum of product/service offering revenue = Total revenue", fy, rev, float(offs.value.sum()),
                    f"{len(offs)} offerings", tol=TOL * 3))
        gp = _v(repo, "gross_profit", fy)
        cor = _v(repo, "cost_of_revenue", fy)
        add(_eq("Income statement", "Revenue - Cost of revenue = Gross margin", fy, gp, rev - cor if rev and cor else None))
        opex = [_v(repo, m, fy) for m in ["research_and_development", "sales_and_marketing", "general_and_administrative"]]
        if gp is not None and None not in opex:
            add(_eq("Income statement", "Gross margin - R&D - S&M - G&A = Operating income", fy, _v(repo, "operating_income", fy), gp - sum(opex)))
        oi, oth = _v(repo, "operating_income", fy), _v(repo, "other_income_expense", fy)
        if oi is not None and oth is not None:
            add(_eq("Income statement", "Operating income + Other income (expense) = Income before taxes", fy, _v(repo, "income_before_tax", fy), oi + oth))
        pbt, tax = _v(repo, "income_before_tax", fy), _v(repo, "income_tax", fy)
        if pbt is not None and tax is not None:
            add(_eq("Income statement", "Income before taxes - Provision for taxes = Net income", fy, _v(repo, "net_income", fy), pbt - tax))
        ni, sh = _v(repo, "net_income", fy), _v(repo, "diluted_shares", fy)
        if ni and sh:
            add(_eq("Income statement", "Net income / diluted shares ≈ diluted EPS", fy, _v(repo, "eps_diluted", fy), ni / sh, tol=0.02))

    # independent recomputation of YoY and margins (pandas, not the calculation engine) vs the engine
    from src.calculations.engine import CalculationEngine

    eng = CalculationEngine(repo)
    for fy in is_years[1:]:
        r1, r0 = _v(repo, "revenue", fy), _v(repo, "revenue", fy - 1)
        m = eng.calculate("revenue_growth", fy)
        if m.ok:
            add(_eq("Calculations", "Revenue growth: engine = independent recomputation", fy, (r1 - r0) / r0, m.value, tol=1e-9))
    for fy in is_years:
        for mid, num in [("gross_margin_pct", "gross_profit"), ("operating_margin_pct", "operating_income"), ("net_margin_pct", "net_income")]:
            m = eng.calculate(mid, fy)
            if m.ok:
                add(_eq("Calculations", f"{m.name}: engine = independent recomputation", fy, _v(repo, num, fy) / _v(repo, "revenue", fy), m.value, tol=1e-9))

    # structural checks
    dup = int(df.fact_key.duplicated().sum())
    out.append(Check("Integrity", "No duplicate financial records (unique fact_key)", None, 0, dup, dup == 0))
    money = df[df.currency.fillna("") != ""]
    bad_cur = sorted(set(money.currency) - {"USD"})
    out.append(Check("Integrity", "Currency is consistent (USD only)", None, None, None, not bad_cur, f"non-USD: {bad_cur}" if bad_cur else "all monetary facts USD"))
    unit_per_metric = df.groupby("metric_id").unit.nunique()
    mixed = sorted(unit_per_metric[unit_per_metric > 1].index)
    out.append(Check("Integrity", "Units are consistent within each metric", None, None, None, not mixed, f"mixed units: {mixed}" if mixed else "one unit per metric"))
    usd = df[df.currency == "USD"]
    bad_unit = sorted(set(usd.unit) - {"USD millions", "USD per share"})
    out.append(Check("Integrity", "Monetary units normalised (USD millions / USD per share)", None, None, None, not bad_unit, str(bad_unit) if bad_unit else "ok"))
    conflicts = int((df.consistency == "conflict").sum())
    out.append(Check("Integrity", "No intra-filing value conflicts", None, 0, conflicts, conflicts == 0))
    return out


def coverage(repo: FinancialRepository | None = None) -> pd.DataFrame:
    """Missing-value matrix for the canonical (non-dimensional) metrics."""
    repo = repo or FinancialRepository()
    d = repo.df[repo.df.dimension_member == ""]
    years = sorted(d.fiscal_year.unique())
    piv = d.pivot_table(index=["statement", "metric_id"], columns="fiscal_year", values="value", aggfunc="count").reindex(columns=years)
    return piv.notna()


def write_report(path=None) -> str:
    path = path or (settings.PROJECT_ROOT / "docs" / "data_quality_report.md")
    repo = FinancialRepository()
    checks = run_checks(repo)
    cov = coverage(repo)
    conflicts = pd.read_csv(settings.CONFLICTS_CSV) if settings.CONFLICTS_CSV.exists() and settings.CONFLICTS_CSV.stat().st_size > 1 else pd.DataFrame()
    passed = sum(c.passed for c in checks)
    lines = [
        "# Data Quality Report",
        "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by `src/governance/data_quality.py` (re-run with `python -m scripts.build_financial_model`)._",
        "",
        f"**Result: {passed}/{len(checks)} checks passed.** Financial facts in model: {len(repo.df)} "
        f"(fiscal years {min(repo.df.fiscal_year)}–{max(repo.df.fiscal_year)}).",
        "",
        "Tolerance: ±$1M for reported-figure identities (filings round to the nearest million); 1e-9 for engine-vs-independent recomputation.",
        "",
    ]
    for cat in dict.fromkeys(c.category for c in checks):
        lines += [f"## {cat}", "", "| Check | FY | Expected | Actual | Result | Detail |", "|---|---|---:|---:|:---:|---|"]
        for c in [c for c in checks if c.category == cat]:
            fmt = (lambda x: "" if x is None else (f"{x:,.4f}" if abs(x) < 10 else f"{x:,.0f}"))
            lines.append(f"| {c.name} | {c.fiscal_year or ''} | {fmt(c.expected)} | {fmt(c.actual)} | {'✅' if c.passed else '❌'} | {c.detail} |")
        lines.append("")
    lines += ["## Missing values (coverage of canonical metrics)", "",
              "Cells marked ⚠️ are not available in the loaded filings and are **flagged, not estimated**. "
              "Balance-sheet items exist only for year-ends presented in the filings loaded (FY2024–FY2026).", ""]
    years = list(cov.columns)
    lines.append("| Statement | Metric | " + " | ".join(f"FY{y}" for y in years) + " |")
    lines.append("|---|---|" + "|".join(":-:" for _ in years) + "|")
    for (stmt, mid), row in cov.iterrows():
        lines.append(f"| {stmt} | `{mid}` | " + " | ".join("✅" if row[y] else "⚠️" for y in years) + " |")
    lines += ["", "## Cross-source differences and conflicts", ""]
    if conflicts.empty:
        lines.append("None detected.")
    else:
        lines += ["The same period can be reported in more than one filing. The most recent filing is treated as authoritative "
                  "(prior-year comparatives are sometimes recast); every difference is logged here for human review.", "",
                  "| Type | Fact | Value used (source, page) | Other value (source, page) | Resolution |", "|---|---|---|---|---|"]
        for _, r in conflicts.iterrows():
            lines.append(f"| {r.conflict_type} | `{r.fact_key}` | {r.value_used:,.0f} ({r.value_used_source}, p.{r.value_used_page}) | "
                         f"{r.other_value} ({r.other_source}, p.{r.other_page}) | {r.resolution} |")
    lines.append("")
    path.write_text("\n".join(lines))
    return str(path)
