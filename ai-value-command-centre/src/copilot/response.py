"""Structured copilot response. A response is never just a paragraph: every answer carries key drivers, the numbers
behind it (with formula and evidence id), evidence sources, assumptions kept separate from actuals, a confidence
level with its basis, and drill-down references into the data."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from src import settings


def money(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "n/a"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        return f"{sign}${x / 1e9:,.{digits}f}B"
    if x >= 1e6:
        return f"{sign}${x / 1e6:,.{digits}f}M"
    if x >= 1e3:
        return f"{sign}${x / 1e3:,.0f}K"
    return f"{sign}${x:,.0f}"


def spct(x: float | None, digits: int = 0) -> str:
    """Signed percentage, for variances."""
    return "n/a" if x is None else f"{x * 100:+.{digits}f}%"


def pct(x: float | None, digits: int = 0) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def pp(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:+.{digits}f} pp"


@dataclass
class Number:
    label: str
    value: float | None
    unit: str = "USD"  # USD | ratio | pp | count | score | GPU-hours | months
    display: str = ""
    formula: str | None = None
    evidence_id: str | None = None
    basis: str = "actual"  # actual | validated | calculated | assumption | forecast | public

    def __post_init__(self):
        if not self.display:
            self.display = (money(self.value) if self.unit == "USD" else pct(self.value) if self.unit == "ratio"
                            else pp(self.value) if self.unit == "pp" else f"{self.value:,.0f}" if self.value is not None else "n/a")


@dataclass
class EvidenceRef:
    kind: str  # dataset | calculation | document | public_financials
    label: str
    ref: str  # table name, evidence id or document id
    detail: str = ""
    url: str | None = None
    date: str | None = None
    quote: str | None = None


@dataclass
class Drilldown:
    label: str
    kind: str  # initiative | benefit | evidence | cost | scenario | risk
    ref: str


@dataclass
class CopilotResponse:
    question: str
    intent: str
    agent: str
    answer: str
    key_drivers: list[str] = field(default_factory=list)
    numbers: list[Number] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    assumptions: list[dict] = field(default_factory=list)
    confidence: dict = field(default_factory=lambda: {"level": "Medium", "basis": ""})
    drilldown: list[Drilldown] = field(default_factory=list)
    query: dict | None = None
    table: dict | None = None  # optional tabular payload {columns, rows}
    follow_ups: list[str] = field(default_factory=list)
    narrative_source: str = "deterministic"
    data_label: str = settings.SYNTHETIC_LABEL
    audit_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)
