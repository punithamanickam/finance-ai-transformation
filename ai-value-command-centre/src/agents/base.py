"""Shared context for the agents: one set of deterministic engines per data scope (whole portfolio or one BU)."""
from __future__ import annotations

from functools import cached_property

from src.copilot.response import CopilotResponse, Drilldown, EvidenceRef, Number
from src.finance.benefits import BenefitsEngine
from src.finance.costs import CostEngine
from src.finance.portfolio import PortfolioEngine
from src.finance.repository import Repository
from src.scenario.engine import ScenarioEngine


class Context:
    def __init__(self, bu_scope: str | None = None):
        self.bu_scope = bu_scope
        self.repo = Repository(bu_scope)
        self.portfolio = PortfolioEngine(self.repo)

    @cached_property
    def kpis(self) -> dict:
        return self.portfolio.kpis()

    @cached_property
    def table(self):
        return self.portfolio.initiative_table()

    @cached_property
    def benefits(self) -> BenefitsEngine:
        return BenefitsEngine(self.portfolio)

    @cached_property
    def costs(self) -> CostEngine:
        return CostEngine(self.portfolio)

    @cached_property
    def scenario(self) -> ScenarioEngine:
        return ScenarioEngine(self.portfolio)

    def assumptions(self, ids) -> list[dict]:
        a = self.repo["assumptions"].set_index("assumption_id")
        out = []
        for i in ids:
            if i in a.index:
                r = a.loc[i]
                out.append({"assumption_id": i, "description": r.description, "value": float(r.value), "unit": r.unit,
                            "source": r.source, "owner": r.owner, "last_reviewed": r.last_reviewed})
        return out

    def ini_drill(self, ids, limit: int = 5) -> list[Drilldown]:
        names = self.table.set_index("initiative_id")["name"]
        return [Drilldown(f"{i} {names.get(i, '')}", "initiative", i) for i in list(ids)[:limit]]


class Agent:
    name = "agent"

    def __init__(self, ctx: Context):
        self.ctx = ctx

    def respond(self, question: str, intent: str, answer: str, **kw) -> CopilotResponse:
        return CopilotResponse(question=question, intent=intent, agent=self.name, answer=answer, **kw)


def ds(table: str, detail: str = "") -> EvidenceRef:
    return EvidenceRef("dataset", table.replace("_", " "), table, detail)


def calc(evidence_id: str, label: str, detail: str = "") -> EvidenceRef:
    return EvidenceRef("calculation", label, evidence_id, detail)


__all__ = ["Agent", "Context", "Number", "EvidenceRef", "Drilldown", "ds", "calc"]
