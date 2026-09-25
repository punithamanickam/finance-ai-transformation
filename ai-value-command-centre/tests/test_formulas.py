import pytest

from src.finance import formulas as F


def test_roi_net_basis():
    assert F.roi(150, 100) == pytest.approx(0.5)
    assert F.roi(75, 100) == pytest.approx(-0.25)
    assert F.roi(10, 0) is None


def test_value_per_dollar_and_net_value():
    assert F.value_per_dollar(31.7, 42.3) == pytest.approx(0.7494, abs=1e-4)
    assert F.net_value(31.7, 42.3) == pytest.approx(-10.6)


def test_benefit_realisation():
    assert F.benefit_realisation(4, 10) == pytest.approx(0.4)
    assert F.benefit_realisation(4, 0) is None


def test_budget_and_forecast_variance_sign_convention():
    var, pct = F.budget_variance(8.4, 7.25)
    assert var == pytest.approx(1.15) and pct == pytest.approx(0.1586, abs=1e-4)  # positive = overspend
    var, pct = F.forecast_variance(9, 10)
    assert var == -1 and pct == pytest.approx(-0.1)


def test_payback_interpolates_within_month():
    assert F.payback_months([-100, 50, 50]) == pytest.approx(3.0)
    assert F.payback_months([-100, 40, 40, 40]) == pytest.approx(3.5)
    assert F.payback_months([-100, 10, 10]) is None
    assert F.payback_months([5, 5]) == 0.0


def test_npv_and_irr_are_consistent():
    cfs = [-1000, 400, 400, 400]
    assert F.npv(0.0, cfs) == pytest.approx(200)
    r = F.irr(cfs)
    assert r == pytest.approx(0.0970, abs=1e-3)
    assert F.npv(r, cfs) == pytest.approx(0, abs=1e-4)
    assert F.irr([100, 100]) is None  # no sign change


def test_incremental_roi_matches_brief_example():
    # brief: +$10M investment, +$16.8M value -> 68%
    assert F.incremental_roi(16.8, 10) == pytest.approx(0.68)
