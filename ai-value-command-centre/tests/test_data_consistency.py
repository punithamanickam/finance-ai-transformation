"""The synthetic dataset must be internally consistent and reproducible."""
import pandas as pd
import pytest

from src import settings
from src.synthetic import catalog as C
from src.synthetic.generator import generate


@pytest.fixture(scope="module")
def t():
    return {n: pd.read_csv(settings.SYNTHETIC_DIR / f"{n}.csv") for n in
            ("cost_transactions", "budgets", "benefit_monthly", "infrastructure_usage", "financials", "ai_usage", "benefits")}


def test_generator_is_deterministic_and_matches_committed_csvs(t):
    a, b = generate(), generate()
    for name in ("cost_transactions", "benefit_monthly", "infrastructure_usage"):
        pd.testing.assert_frame_equal(a[name], b[name])
    assert a["cost_transactions"].amount.sum() == pytest.approx(t["cost_transactions"].amount.sum(), rel=1e-9)


def test_initiative_spend_equals_sum_of_transactions(t):
    prog = t["cost_transactions"][t["cost_transactions"].cost_type == "programme"].groupby("initiative_id").amount.sum()
    for ini in C.INITIATIVES:
        assert prog[ini.initiative_id] == pytest.approx(ini.actual_spend, abs=5)


def test_budget_table_equals_approved_budget(t):
    b = t["budgets"].groupby("initiative_id").budget_amount.sum()
    for ini in C.INITIATIVES:
        assert b[ini.initiative_id] == pytest.approx(ini.budget, abs=5)


def test_cluster_cost_is_the_sum_of_hosted_infrastructure_cost(t):
    ct = t["cost_transactions"]
    infra = ct[ct.cost_category.isin(C.INFRA_CATEGORIES)]
    cluster_of = {i.initiative_id: i.cluster_id for i in C.INITIATIVES}
    exp = infra.assign(c=infra.initiative_id.map(cluster_of)).groupby("c").amount.sum()
    got = t["infrastructure_usage"].groupby("cluster_id").infrastructure_cost.sum()
    for cid in ("PCAI-EMEA-01", "PCAI-US-01", "GL-US-01", "GL-APJ-01"):
        assert got[cid] == pytest.approx(exp[cid], rel=1e-6)


def test_measured_equals_realised_plus_validated(t):
    bm = t["benefit_monthly"]
    assert (bm.measured_value - bm.realised_value - bm.validated_value).abs().max() < 0.05
    assert (bm.realised_value >= -0.01).all() and (bm.validated_value >= -0.01).all()


def test_no_benefit_before_actual_go_live(t):
    bm = t["benefit_monthly"]
    for ini in C.INITIATIVES:
        pre = bm[(bm.initiative_id == ini.initiative_id) & (bm.month < C.FY_MONTHS[ini.actual_go_live])]
        assert pre.measured_value.sum() == 0


def test_productivity_moves_with_active_users(t):
    """Productivity benefit per active user is constant within a line, so more adoption means more benefit."""
    bm, use = t["benefit_monthly"], t["ai_usage"]
    prod = bm[bm.benefit_type == "productivity"].merge(use, on=["initiative_id", "month"])
    prod = prod[prod.active_users > 0]
    for bid, g in prod.groupby("benefit_id"):
        if len(g) >= 3:
            ratio = g.measured_value / g.active_users
            assert ratio.std() / ratio.mean() < 0.2, bid


def test_evidenced_benefits_reconcile_to_the_pnl(t):
    lines = t["benefits"].set_index("benefit_id")
    bm = t["benefit_monthly"]
    fin = bm[bm.benefit_id.map(lines.evidence_type) == "financial"].realised_value.sum()
    assert t["financials"].ai_attributed_benefit.sum() == pytest.approx(fin, abs=50)


def test_financials_cover_24_months_and_usage_12(t):
    assert t["financials"].month.nunique() == 24
    assert t["ai_usage"].month.nunique() == 12
    assert len(C.INITIATIVES) >= 12
