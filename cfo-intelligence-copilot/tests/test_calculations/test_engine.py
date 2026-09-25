"""Deterministic calculation engine: formulas, provenance, missing-data behaviour, driver trees, scenarios."""
import pytest

from src.calculations.driver_trees import free_cash_flow_tree, operating_income_tree, revenue_tree
from src.calculations.engine import METRICS
from src.calculations.scenario import ScenarioEngine

FY = 2026


def v(engine, m, fy=FY, member=""):
    return engine.repo.get(m, fy, member).value


def test_revenue_growth_matches_independent_formula(engine):
    r = engine.calculate("revenue_growth", FY)
    assert r.ok
    assert r.value == pytest.approx((v(engine, "revenue") - v(engine, "revenue", FY - 1)) / v(engine, "revenue", FY - 1), abs=1e-12)


@pytest.mark.parametrize("metric,num", [("gross_margin_pct", "gross_profit"), ("operating_margin_pct", "operating_income"),
                                        ("net_margin_pct", "net_income"), ("rd_pct_revenue", "research_and_development"),
                                        ("sm_pct_revenue", "sales_and_marketing"), ("capex_intensity", "capital_expenditure")])
def test_ratio_metrics(engine, metric, num):
    assert engine.calculate(metric, FY).value == pytest.approx(v(engine, num) / v(engine, "revenue"), abs=1e-12)


def test_free_cash_flow_and_conversion(engine):
    fcf = engine.calculate("free_cash_flow", FY)
    assert fcf.value == pytest.approx(v(engine, "operating_cash_flow") - v(engine, "capital_expenditure"))
    conv = engine.calculate("cash_conversion", FY)
    assert conv.value == pytest.approx(fcf.value / v(engine, "net_income"))


def test_balance_sheet_ratios(engine):
    debt = v(engine, "short_term_debt") + v(engine, "long_term_debt")
    assert engine.calculate("total_debt", FY).value == pytest.approx(debt)
    assert engine.calculate("net_debt", FY).value == pytest.approx(debt - v(engine, "cash_and_short_term_investments"))
    assert engine.calculate("debt_to_equity", FY).value == pytest.approx(debt / v(engine, "shareholders_equity"))
    assert engine.calculate("current_ratio", FY).value == pytest.approx(v(engine, "current_assets") / v(engine, "current_liabilities"))


def test_every_calculated_metric_retains_formula_inputs_sources_version(engine):
    for mid in METRICS:
        r = engine.calculate(mid, FY)
        assert r.formula and r.engine_version and r.calculated_at
        if r.ok:
            assert r.inputs, mid
            for i in r.inputs:
                assert i.page > 0 and i.document and i.url.startswith("https://www.sec.gov/")


def test_missing_inputs_are_not_invented(engine):
    # FY2023 debt is not presented in the loaded balance sheets, so ROIC for FY2024 (needs opening balances) is unavailable
    r = engine.calculate("roic_proxy", 2024)
    assert r.status == "unavailable" and r.value is None
    assert engine.calculate("revenue_growth", 2010).status == "unavailable"


def test_proxies_are_labelled(engine):
    assert engine.calculate("ebitda_proxy", FY).is_proxy
    assert "Not a reported GAAP measure" in engine.calculate("ebitda_proxy", FY).note


def test_variance_and_cagr(engine):
    var = engine.variance("revenue", FY)
    assert var.absolute_change == pytest.approx(v(engine, "revenue") - v(engine, "revenue", FY - 1))
    assert var.favourable is True
    gm = engine.variance("gross_margin_pct", FY)
    assert gm.pct_change is None  # ratio metrics change in percentage points
    years = engine.repo.years("revenue")
    c = engine.cagr("revenue", years[0], FY)
    n = FY - years[0]
    assert c.value == pytest.approx((v(engine, "revenue") / v(engine, "revenue", years[0])) ** (1 / n) - 1)


def test_operating_income_bridge_reconciles(engine):
    t = operating_income_tree(engine, FY)
    assert sum(c.change for c in t.children) == pytest.approx(t.change, abs=1e-6)
    gp = t.children[0]
    assert sum(c.change for c in gp.children) == pytest.approx(gp.change, abs=1e-6)


def test_revenue_tree_segments_sum_to_total(engine):
    t = revenue_tree(engine, FY)
    assert sum(c.change for c in t.children) == pytest.approx(t.change, abs=1.0)
    for seg in t.children:  # offering drill-down + explicit residual reconciles to the segment
        if seg.children:
            assert sum(c.change for c in seg.children) == pytest.approx(seg.change, abs=1.0)


def test_fcf_tree(engine):
    t = free_cash_flow_tree(engine, FY)
    assert t.change == pytest.approx(sum(c.change for c in t.children if c.change is not None))


def test_segment_contributions_sum_to_one(engine):
    rows = engine.segment_table(FY)
    assert sum(r["contribution_to_growth"] for r in rows) == pytest.approx(1.0, abs=1e-3)


def test_scenario_zero_shock_equals_base_and_revenue_shock(engine):
    se = ScenarioEngine(engine)
    same = se.compare()
    assert all(abs(d) < 1e-6 for d in same.delta.values())
    shocked = se.compare(deltas={"revenue_growth": -0.05})
    assert shocked.delta["revenue"] == pytest.approx(-0.05 * v(engine, "revenue"))
    # gross margin held constant -> gross profit falls by the same % as revenue
    assert shocked.delta["gross_profit"] == pytest.approx(shocked.delta["revenue"] * shocked.base.assumptions.gross_margin)
    assert "not management guidance" in shocked.disclaimer


def test_sensitivity_is_ranked(engine):
    rows = ScenarioEngine(engine).sensitivity("operating_income")
    impacts = [r["abs_impact"] for r in rows]
    assert impacts == sorted(impacts, reverse=True)
    assert {r["assumption"] for r in rows if r["abs_impact"] == 0} >= {"tax_rate", "capex_intensity"}
