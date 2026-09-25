"""Portfolio analytics reconcile and derive conclusions from data."""
import pytest

from src.finance.benefits import BenefitsEngine


def test_value_classification_reconciles(ctx):
    k = ctx.kpis
    assert k["realised_value"] + k["validated_value"] + k["hypothetical_value"] == pytest.approx(k["expected_value"], abs=1)
    assert k["realised_roi"] == pytest.approx((k["realised_value"] - k["total_investment"]) / k["total_investment"])
    assert k["benefit_realisation"] == pytest.approx(k["realised_value"] / k["expected_value"])


def test_headline_numbers_are_in_the_demo_range(ctx):
    k = ctx.kpis
    assert k["total_investment"] == pytest.approx(42.3e6, rel=0.001)
    assert 28e6 < k["realised_value"] < 34e6 and 47e6 < k["expected_value"] < 52e6
    assert k["initiatives"] == 12


def test_waterfall_sums_to_net_value(ctx):
    w = ctx.portfolio.waterfall()
    steps = [s for s in w["steps"] if s["kind"] != "total"]
    assert sum(s["value"] for s in steps) == pytest.approx(w["net_value"])
    assert w["net_value"] == pytest.approx(ctx.kpis["net_value"], abs=1)
    for s in steps:
        if s.get("drilldown"):
            assert sum(d["value"] for d in s["drilldown"]) == pytest.approx(abs(s["value"]), abs=1)


def test_roi_movement_decomposition_is_exact(ctx):
    m = ctx.portfolio.roi_movement()
    assert m["value_effect_pp"] + m["cost_effect_pp"] == pytest.approx(m["change_pp"])
    assert sum(x["contribution_pp"] for x in m["initiatives"]) == pytest.approx(m["change_pp"])
    assert m["change_pp"] < 0  # the synthetic scenario contains a Q4 ROI decline; derived, not written in
    assert m["utilisation_to"] < m["utilisation_from"]


def test_leakage_components_sum_to_gap(ctx):
    for r in BenefitsEngine(ctx.portfolio).leakage_lines().itertuples():
        parts = r.delayed_implementation + r.low_adoption + r.value_per_unit + r.pending_validation
        assert parts == pytest.approx(r.gap, abs=1)


def test_at_risk_is_derived_from_rules(ctx):
    t = ctx.table
    for _, r in t.iterrows():
        assert r.at_risk == any(f["level"] == "Red" for f in r.risk_flags)
    delayed = t[t.initiative_id == "AI-003"].iloc[0]
    assert delayed.at_risk and delayed.schedule_slip_months >= 2


def test_bu_scope_restricts_data():
    from src.agents.orchestrator import context_for

    scm = context_for("BU-SCM")
    assert set(scm.table.bu_id) == {"BU-SCM"}
    assert scm.kpis["total_investment"] < context_for(None).kpis["total_investment"]
