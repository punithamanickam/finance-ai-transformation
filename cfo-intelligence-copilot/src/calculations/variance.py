"""Automatic variance engine: current vs prior, absolute and % variance, and evidence-based explanation.

Explanations come only from retrieved filing text (MD&A / notes / earnings release). If nothing relevant is
retrieved, the engine says so instead of inventing a reason.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.calculations.engine import CalculationEngine
from src.calculations.models import Variance

NO_EVIDENCE = "Public filing does not provide sufficient evidence to determine the specific cause."

MAJOR_METRICS = [
    "revenue", "cost_of_revenue", "gross_profit", "gross_margin_pct", "research_and_development", "sales_and_marketing",
    "general_and_administrative", "total_operating_expenses", "operating_income", "operating_margin_pct",
    "other_income_expense", "income_tax", "net_income", "eps_diluted", "operating_cash_flow", "capital_expenditure",
    "free_cash_flow", "cash_and_short_term_investments", "total_debt",
]

# retrieval query used to look for management's explanation of each variance
EXPLANATION_QUERIES = {
    "revenue": "revenue increased driven by growth",
    "cost_of_revenue": "cost of revenue increased driven by",
    "gross_profit": "gross margin increased driven by gross margin percentage",
    "gross_margin_pct": "gross margin percentage decreased driven by AI infrastructure",
    "research_and_development": "research and development expenses increased driven by",
    "sales_and_marketing": "sales and marketing expenses increased driven by",
    "general_and_administrative": "general and administrative expenses increased driven by",
    "total_operating_expenses": "operating expenses increased driven by",
    "operating_income": "operating income increased driven by",
    "operating_margin_pct": "operating income increased driven by",
    "other_income_expense": "other income expense net recognized gains losses investments",
    "income_tax": "effective tax rate increased decreased",
    "net_income": "net income and diluted EPS were positively impacted",
    "eps_diluted": "diluted EPS increased",
    "operating_cash_flow": "cash from operations increased due to cash received from customers",
    "capital_expenditure": "cash used in investing additions to property and equipment",
    "free_cash_flow": "cash from operations additions to property and equipment",
    "cash_and_short_term_investments": "cash cash equivalents and short-term investments totaled",
    "total_debt": "debt repayments long-term debt",
}


class VarianceExplanation(BaseModel):
    variance: Variance
    evidence: list[dict] = Field(default_factory=list)  # {"text", "citation", "score"}
    explanation_status: str = "no_evidence"  # evidence_found | no_evidence
    explanation: str = NO_EVIDENCE


def variance_table(eng: CalculationEngine, fy: int, prior: int | None = None, metrics: list[str] | None = None) -> list[Variance]:
    return [eng.variance(m, fy, prior) for m in (metrics or MAJOR_METRICS)]


def explain_variance(eng: CalculationEngine, metric_id: str, fy: int, prior: int | None = None, k: int = 2) -> VarianceExplanation:
    from src.ingestion.source_registry import load_registry
    from src.retrieval.vector_store import get_store

    var = eng.variance(metric_id, fy, prior)
    if (prior or fy - 1) != fy - 1:
        return VarianceExplanation(variance=var)  # MD&A explains current vs immediately prior year only
    reg = load_registry()
    sources = set(reg[(reg.fiscal_year == str(fy)) & (reg.ingest == "yes")].source_id) or None
    query = EXPLANATION_QUERIES.get(metric_id, var.label) + f" fiscal year {fy}"
    hits = get_store().search(query, k=k, content_types={"management_commentary"}, min_score=0.12, source_ids=sources)
    if not hits:
        return VarianceExplanation(variance=var)
    ev = [{"text": h.chunk.text, "citation": h.citation(), "score": round(h.score, 3), "page": h.chunk.page,
           "document": h.chunk.document, "url": h.chunk.source_url} for h in hits]
    return VarianceExplanation(variance=var, evidence=ev, explanation_status="evidence_found",
                               explanation="Management commentary retrieved from the filing (quoted verbatim, see evidence).")
