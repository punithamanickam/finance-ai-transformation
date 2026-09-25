"""Deterministic financial formulas. The language model never calculates: every number the copilot states comes
from these functions (or aggregations of the database), and each function documents its formula.

Conventions
* Amounts in USD. Rates as decimals (0.25 = 25%).
* ROI is reported on a net basis: (value - investment) / investment. A negative ROI means the investment has not yet
  been recovered. "Value per $1 invested" (value / investment) is reported separately.
* Functions return None when a result is undefined (e.g. division by zero, no sign change for IRR) rather than a
  misleading number.
"""
from __future__ import annotations

from collections.abc import Sequence

FORMULAS = {
    "roi": "ROI = (Value - Investment) / Investment",
    "value_per_dollar": "Value per $1 invested = Value / Investment",
    "net_value": "Net value = Value - Investment",
    "benefit_realisation": "Benefit realisation % = Realised benefit / Expected benefit",
    "budget_variance": "Budget variance = Actual - Budget; % = (Actual - Budget) / Budget (positive = overspend)",
    "forecast_variance": "Forecast variance = Actual - Forecast; % = (Actual - Forecast) / Forecast",
    "payback_months": "Payback = first month in which cumulative net cash flow >= 0 (linear interpolation within the month)",
    "npv": "NPV = sum_t CF_t / (1 + r)^t, t in years, CF_0 undiscounted",
    "irr": "IRR = r such that NPV(r) = 0 (bisection on [-99%, 1000%]); undefined without a sign change",
    "cost_per_outcome": "Cost per outcome = Cost / Outcome volume",
    "incremental_roi": "Incremental ROI = (Incremental value - Incremental investment) / Incremental investment",
}


def _div(a: float, b: float) -> float | None:
    return None if b == 0 else a / b


def roi(value: float, investment: float) -> float | None:
    return _div(value - investment, investment)


def value_per_dollar(value: float, investment: float) -> float | None:
    return _div(value, investment)


def net_value(value: float, investment: float) -> float:
    return value - investment


def benefit_realisation(realised: float, expected: float) -> float | None:
    return _div(realised, expected)


def budget_variance(actual: float, budget: float) -> tuple[float, float | None]:
    return actual - budget, _div(actual - budget, budget)


def forecast_variance(actual: float, forecast: float) -> tuple[float, float | None]:
    return actual - forecast, _div(actual - forecast, forecast)


def payback_months(cash_flows: Sequence[float]) -> float | None:
    """Monthly net cash flows (negative = outflow). Returns months to payback, None if not reached in the horizon."""
    cum = 0.0
    for i, cf in enumerate(cash_flows):
        prev = cum
        cum += cf
        if prev < 0 <= cum:
            return round(i + (-prev / cf), 2)  # months elapsed from the start of month 0
    return 0.0 if cash_flows and cash_flows[0] >= 0 else None


def npv(rate: float, cash_flows: Sequence[float]) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))


def irr(cash_flows: Sequence[float], lo: float = -0.99, hi: float = 10.0, tol: float = 1e-7) -> float | None:
    f_lo, f_hi = npv(lo, cash_flows), npv(hi, cash_flows)
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = npv(mid, cash_flows)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def cost_per_outcome(cost: float, outcomes: float) -> float | None:
    return _div(cost, outcomes)


def incremental_roi(incremental_value: float, incremental_investment: float) -> float | None:
    return roi(incremental_value, incremental_investment)
