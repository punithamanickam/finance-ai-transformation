import pandas as pd

from src.finance.confidence import WEIGHTS, ConfidenceEngine


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1) < 1e-9


def test_scores_bounded_and_banded(ctx):
    s = ConfidenceEngine(ctx.portfolio).score_lines()
    assert s.score.between(0, 100).all()
    for _, r in s.iterrows():
        assert r.band == ConfidenceEngine.band(r.score)
        assert r.basis  # every score carries an explanation


def test_better_evidence_scores_higher(ctx):
    s = ConfidenceEngine(ctx.portfolio).score_lines().set_index("benefit_id")
    # finance-validated controlled test (support copilot savings) vs management-estimated risk value
    assert s.loc["AI-001-B1", "score"] > s.loc["AI-007-B1", "score"]
    assert ConfidenceEngine.band(80) == "High" and ConfidenceEngine.band(60) == "Medium" and ConfidenceEngine.band(20) == "Low"
    assert ConfidenceEngine.band(float("nan")) == "n/a" and ConfidenceEngine.band(None) == "n/a"
    assert isinstance(s, pd.DataFrame)
