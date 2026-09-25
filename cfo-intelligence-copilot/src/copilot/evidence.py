"""Evidence pack: everything the narrative layer is allowed to use, and everything the UI renders."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.calculations.models import CalculatedMetric, InputRef, Variance, format_value

Basis = Literal["factual_observation", "calculated_analysis", "possible_interpretation", "management_commentary"]

BASIS_LABELS = {
    "factual_observation": "Factual observation (reported figure)",
    "calculated_analysis": "Calculated analysis (deterministic engine)",
    "possible_interpretation": "Possible interpretation (inference - not fact)",
    "management_commentary": "Management commentary (quoted from filing)",
}


class KeyNumber(BaseModel):
    metric: str
    current: str
    prior: str
    change: str
    current_value: float | None = None
    prior_value: float | None = None
    change_value: float | None = None
    change_pct: float | None = None
    unit: str = ""
    current_label: str = ""
    prior_label: str = ""


class Statement(BaseModel):
    text: str
    basis: Basis
    citations: list[str] = Field(default_factory=list)


class SourceItem(BaseModel):
    document: str
    section: str
    page: int | str
    url: str
    detail: str = ""

    def key(self):
        return (self.document, self.page, self.detail)


class Evidence(BaseModel):
    intent: str
    title: str
    fiscal_year: int
    prior_year: int | None = None
    status: str = "ok"  # ok | insufficient_evidence | conflict | refused
    headline: str = ""  # deterministic narrative - used verbatim if the LLM is unavailable or fails validation
    key_numbers: list[KeyNumber] = Field(default_factory=list)
    statements: list[Statement] = Field(default_factory=list)
    calculations: list[CalculatedMetric] = Field(default_factory=list)
    variances: list[Variance] = Field(default_factory=list)
    sources: list[SourceItem] = Field(default_factory=list)
    tables: dict[str, list[dict]] = Field(default_factory=dict)  # extra tabular payloads for the UI (segments, scenario ...)
    trees: list[dict] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"] = "High"
    basis: list[str] = Field(default_factory=list)
    disclaimer: str = ""
    retrieved_chunks: list[dict] = Field(default_factory=list)

    # ---- builders ----------------------------------------------------------------------------------------------
    def add_inputs(self, inputs: list[InputRef]) -> None:
        seen = {s.key() for s in self.sources}
        for r in inputs:
            s = SourceItem(document=r.document, section=r.section, page=r.page, url=r.url,
                           detail=f"{r.table or 'statement'} - {r.label} FY{r.fiscal_year}")
            if s.key() not in seen:
                self.sources.append(s)
                seen.add(s.key())
        if inputs and "Structured financial data" not in self.basis:
            self.basis.append("Structured financial data")

    def add_calc(self, m: CalculatedMetric) -> CalculatedMetric:
        self.calculations.append(m)
        self.add_inputs(m.inputs)
        if m.ok and m.formula != "Reported value" and "Calculated metric" not in self.basis:
            self.basis.append("Calculated metric")
        if m.is_proxy and m.ok:
            self.lower_confidence("Medium")
        return m

    def add_variance(self, v: Variance, label: str | None = None) -> Variance:
        self.variances.append(v)
        self.add_inputs(v.inputs)
        self.key_numbers.append(key_number(v, label))
        return v

    def add_statement(self, text: str, basis: Basis, citations: list[str] | None = None) -> None:
        self.statements.append(Statement(text=text, basis=basis, citations=citations or []))
        if basis == "possible_interpretation" and "Inference" not in self.basis:
            self.basis.append("Inference")
        if basis == "management_commentary" and "Management commentary" not in self.basis:
            self.basis.append("Management commentary")

    def add_commentary(self, hits, max_chars: int = 900) -> int:
        n = 0
        seen = {s.key() for s in self.sources}
        used = {r["chunk_id"] for r in self.retrieved_chunks}
        for h in hits:
            c = h.chunk
            if c.chunk_id in used:
                continue
            used.add(c.chunk_id)
            text = c.text if len(c.text) <= max_chars else c.text[:max_chars].rsplit(" ", 1)[0] + " …"
            cite = f"{c.document}, {c.section}{' – ' + c.heading if c.heading else ''}, p.{c.page}"
            self.add_statement(f"“{text}”", "management_commentary", [cite])
            self.retrieved_chunks.append({"chunk_id": c.chunk_id, "score": round(h.score, 3), "citation": cite})
            s = SourceItem(document=c.document, section=c.section, page=c.page, url=c.source_url, detail=c.heading or "narrative")
            if s.key() not in seen:
                self.sources.append(s)
                seen.add(s.key())
            n += 1
        return n

    def lower_confidence(self, level: str) -> None:
        order = {"High": 3, "Medium": 2, "Low": 1}
        if order[level] < order[self.confidence]:
            self.confidence = level

    def pack(self) -> dict:
        """Compact JSON given to the LLM (no URLs / ids - only what it may talk about)."""
        return {
            "title": self.title, "status": self.status, "fiscal_year": self.fiscal_year, "prior_year": self.prior_year,
            "deterministic_summary": self.headline,
            "key_numbers": [k.model_dump(include={"metric", "current", "prior", "change", "current_label", "prior_label"}) for k in self.key_numbers],
            "statements": [{"basis": s.basis, "text": s.text} for s in self.statements],
            "calculations": [{"name": c.name, "fy": c.fiscal_year, "value": c.display(1), "formula": c.formula, "proxy": c.is_proxy, "status": c.status, "note": c.note}
                             for c in self.calculations],
            "tables": self.tables,
            "disclaimer": self.disclaimer,
        }


def key_number(v: Variance, label: str | None = None) -> KeyNumber:
    unit = v.unit
    if v.absolute_change is None:
        change = "n/a"
    elif unit == "%":
        change = format_value(v.absolute_change, "pp")
    elif unit == "x":
        change = f"{v.absolute_change:+.2f}x"
    else:
        sign = "+" if v.absolute_change >= 0 else "-"
        change = f"{sign}{format_value(abs(v.absolute_change), unit)}" + (f" ({v.pct_change:+.1%})" if v.pct_change is not None else "")
    return KeyNumber(metric=label or v.label, current=format_value(v.current, unit), prior=format_value(v.prior, unit), change=change,
                     current_value=v.current, prior_value=v.prior, change_value=v.absolute_change, change_pct=v.pct_change, unit=unit,
                     current_label=f"FY{v.current_year}", prior_label=f"FY{v.prior_year}")
