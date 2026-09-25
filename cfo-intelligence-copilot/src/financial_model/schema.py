"""Normalised financial data model (Pydantic). One row = one reported number with full provenance."""
from __future__ import annotations

from pydantic import BaseModel, Field


class FinancialFact(BaseModel):
    fact_key: str = Field(description="metric_id|FYyyyy|dimension_member - unique per fact")
    company: str
    reporting_period: str  # e.g. "FY2026"
    fiscal_year: int
    period_end: str
    period_type: str  # duration | instant
    statement: str  # Income Statement | Balance Sheet | Cash Flow Statement | Segment | Notes | ...
    section: str
    metric_id: str
    metric_label: str
    dimension_type: str = ""  # segment | product_offering | geography | ""
    dimension_member: str = ""
    dimension_label: str = ""
    value: float
    currency: str
    unit: str
    source_id: str
    source_document: str
    source_page: int
    source_section: str
    source_table: str
    table_index: int | None = None
    row_label: str
    column_label: str
    source_url: str
    xbrl_concept: str = ""
    xbrl_fact_id: str = ""
    extraction_method: str = "ixbrl"  # ixbrl | text-pattern
    occurrences: int = 1  # how many times the same fact appears in the filing
    consistency: str = "consistent"  # consistent | conflict
    restated_vs_prior_filing: bool = False

    @property
    def citation(self) -> str:
        return f"{self.source_document}, {self.source_section}, {self.source_table or self.statement}, page {self.source_page}"


class SourceRef(BaseModel):
    fact_key: str
    metric: str
    fiscal_year: int
    value: float
    unit: str
    document: str
    section: str
    table: str
    page: int
    row_label: str
    column_label: str
    url: str

    @classmethod
    def from_fact(cls, f: FinancialFact) -> "SourceRef":
        return cls(
            fact_key=f.fact_key,
            metric=f.metric_label + (f" - {f.dimension_label}" if f.dimension_label else ""),
            fiscal_year=f.fiscal_year,
            value=f.value,
            unit=f.unit,
            document=f.source_document,
            section=f.source_section,
            table=f.source_table,
            page=f.source_page,
            row_label=f.row_label,
            column_label=f.column_label,
            url=f.source_url,
        )
