"""Result objects for the deterministic calculation engine. Every number carries its formula and inputs."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InputRef(BaseModel):
    alias: str
    label: str
    fiscal_year: int
    value: float
    unit: str
    fact_key: str
    document: str
    section: str
    table: str
    page: int
    url: str
    derived: bool = False  # True when the input is itself a calculated metric


class CalculatedMetric(BaseModel):
    metric_id: str
    name: str
    fiscal_year: int
    value: float | None
    unit: str  # "%" | "USD millions" | "x" | "USD thousands" | "pp"
    formula: str
    formula_with_values: str = ""
    inputs: list[InputRef] = Field(default_factory=list)
    status: str = "ok"  # ok | unavailable | blocked
    note: str = ""
    is_proxy: bool = False
    engine_version: str = settings.CALC_ENGINE_VERSION
    calculated_at: str = Field(default_factory=_now)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.value is not None

    def display(self, decimals: int = 1) -> str:
        return format_value(self.value, self.unit, decimals) if self.ok else "n/a"


class Variance(BaseModel):
    metric_id: str
    label: str
    unit: str
    current_year: int
    prior_year: int
    current: float | None
    prior: float | None
    absolute_change: float | None
    pct_change: float | None  # for ratio metrics this is None and absolute_change is in pp
    direction: str  # up | down | flat | n/a
    favourable: bool | None
    inputs: list[InputRef] = Field(default_factory=list)
    formula: str = ""
    status: str = "ok"
    note: str = ""


def format_value(v: float | None, unit: str, decimals: int = 1) -> str:
    if v is None:
        return "n/a"
    if unit == "%":
        return f"{v * 100:.{decimals}f}%"
    if unit == "pp":
        return f"{v * 100:+.{decimals}f} pp"
    if unit == "x":
        return f"{v:.2f}x"
    if unit == "USD millions":
        sign = "-" if v < 0 else ""
        if abs(v) >= 1000:
            return f"{sign}${abs(v) / 1000:,.{decimals}f}B"
        return f"{sign}${abs(v):,.0f}M"
    if unit == "USD thousands":
        return f"${v:,.0f}K"
    if unit == "USD per share":
        return f"${v:,.2f}"
    if unit == "people":
        return f"{v:,.0f}"
    return f"{v:,.{decimals}f} {unit}"
