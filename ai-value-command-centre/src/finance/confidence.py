"""AI Value Confidence Engine.

A structured, explainable score of how well each benefit is supported by evidence. It is **not** a probability that
the benefit is real; it summarises evidence quality against eight documented factors so a CFO can see *why* a number
is more or less trustworthy.

Factor (weight)                 Scoring basis
source quality (0.15)           evidence behind the realised amount: GL-backed financial 1.0, system telemetry 0.75
actual vs forecast (0.15)       share of expected value already realised (capped at 1)
financial validation (0.15)     1 if a Finance business partner has validated the benefit, else 0
data completeness (0.10)        live months with measured value / live months
owner confirmation (0.05)       1 if the benefit owner has confirmed the benefit, else 0
methodology (0.15)              controlled test 1.0, before/after 0.75, attribution model 0.5, management estimate 0.3
recency (0.10)                  1 if latest evidence <= 45 days before period end, declining linearly to 0 at 365 days
assumption dependency (0.15)    1 - (hypothetical + 0.5 x validated) / expected
"""
from __future__ import annotations

import pandas as pd

from src.finance.repository import AS_OF

WEIGHTS = {"source_quality": 0.15, "actual_vs_forecast": 0.15, "financial_validation": 0.15, "data_completeness": 0.10,
           "owner_confirmation": 0.05, "methodology": 0.15, "recency": 0.10, "assumption_dependency": 0.15}
METHOD_SCORE = {"controlled_test": 1.0, "before_after": 0.75, "attribution_model": 0.5, "management_estimate": 0.3}
METHOD_LABEL = {"controlled_test": "controlled test", "before_after": "before/after comparison",
                "attribution_model": "attribution model", "management_estimate": "management estimate"}
SOURCE_SCORE = {"financial": 1.0, "operational": 0.75}
DISCLAIMER = ("Confidence is an evidence-quality score built from eight documented factors. It is not a statistical "
              "probability that the benefit will be achieved.")


class ConfidenceEngine:
    def __init__(self, portfolio):
        self.p = portfolio
        self.repo = portfolio.repo

    @staticmethod
    def band(score: float | None) -> str:
        if score is None or pd.isna(score):
            return "n/a"
        return "High" if score >= 75 else "Medium" if score >= 50 else "Low"

    def score_lines(self) -> pd.DataFrame:
        lines = self.p._benefit_lines()
        bm = self.repo["benefit_monthly"]
        ev = self.repo["benefit_evidence"]
        ini = self.repo.initiatives.set_index("initiative_id")
        as_of = pd.Timestamp(AS_OF)
        rows = []
        for _, b in lines.iterrows():
            live = bm[(bm.benefit_id == b.benefit_id) & (bm.month >= ini.loc[b.initiative_id, "actual_go_live"][:7])]
            completeness = (live.measured_value > 0).mean() if len(live) else 0.0
            real_ev = ev[(ev.benefit_id == b.benefit_id) & ev.evidence_kind.isin(["GL journal extract", "System telemetry export"])]
            last = pd.to_datetime(real_ev.evidence_date).max() if len(real_ev) else None
            age = (as_of - last).days if last is not None else 999
            recency = 1.0 if age <= 45 else max(0.0, 1 - (age - 45) / 320)
            exp = b.business_case_value or 1.0
            f = {
                "source_quality": SOURCE_SCORE.get(b.evidence_type, 0.4) if b.realised_value > 0 else 0.1,
                "actual_vs_forecast": min(1.0, b.realised_value / exp),
                "financial_validation": 1.0 if b.finance_validated else 0.0,
                "data_completeness": float(completeness),
                "owner_confirmation": 1.0 if b.owner_confirmed else 0.0,
                "methodology": METHOD_SCORE.get(b.methodology, 0.3),
                "recency": recency,
                "assumption_dependency": max(0.0, 1 - (b.hypothetical_value + 0.5 * b.validated_value) / exp),
            }
            score = round(100 * sum(WEIGHTS[k] * v for k, v in f.items()), 1)
            rows.append({"benefit_id": b.benefit_id, "initiative_id": b.initiative_id, "benefit_type": b.benefit_type,
                         "description": b.description, "expected": b.business_case_value, "realised": b.realised_value,
                         "validated": b.validated_value, "hypothetical": b.hypothetical_value, "score": score,
                         "band": self.band(score), "factors": f, "basis": self._basis(b, f, age)})
        return pd.DataFrame(rows)

    @staticmethod
    def _basis(b, f: dict, age: int) -> list[str]:
        out = [f"Realised evidence is {'GL-backed financial data' if b.evidence_type == 'financial' else 'system telemetry'}"
               if b.realised_value > 0 else "No realised evidence yet",
               f"{f['actual_vs_forecast']:.0%} of the business case is realised",
               "Validated by Finance" if b.finance_validated else "Not yet validated by Finance",
               f"Measured with a {METHOD_LABEL.get(b.methodology, b.methodology)}",
               f"Latest actual evidence {age} days before period end" if age < 999 else "No dated actual evidence",
               f"{(b.hypothetical_value / (b.business_case_value or 1)):.0%} of expected value still rests on business-case assumptions"]
        return out

    def by_initiative(self) -> pd.Series:
        s = self.score_lines()
        if s.empty:
            return pd.Series(dtype=float)
        w = s.assign(wx=s.score * s.expected).groupby("initiative_id")
        return (w.wx.sum() / w.expected.sum()).round(1)

    def summarise(self, df: pd.DataFrame, label: str) -> dict:
        """Dollar-weighted confidence for a group of benefit lines, with the evidence counts behind it."""
        if df.empty:
            return {"label": label, "score": None, "band": "n/a"}
        score = float((df.score * df.expected).sum() / df.expected.sum())
        lines = self.p._benefit_lines().set_index("benefit_id").loc[df.benefit_id]
        return {
            "label": label, "expected": float(df.expected.sum()), "realised": float(df.realised.sum()),
            "score": round(score, 1), "band": self.band(round(score, 1)),
            "evidence": {
                "finance_validated_lines": int(lines.finance_validated.sum()),
                "management_estimated_lines": int((lines.methodology == "management_estimate").sum()),
                "controlled_test_lines": int((lines.methodology == "controlled_test").sum()),
                "gl_backed_lines": int((lines.evidence_type == "financial").sum()),
                "telemetry_backed_lines": int((lines.evidence_type == "operational").sum()),
                "initiatives": int(df.initiative_id.nunique()),
            },
            "disclaimer": DISCLAIMER,
        }
