"""Benefit realisation and benefits leakage.

Leakage decomposition for each benefit line (exact: the parts sum to business case - realised):

    delayed implementation  = business case - plan shifted by the go-live slip (value pushed beyond the period)
    low adoption            = shifted plan x (1 - actual active users / planned active users at the same stage)
    value per unit          = adoption-adjusted plan - measured benefit   (labelled with the line's residual reason:
                              incorrect assumptions, technical constraints, benefit measurement problem)
    pending validation      = validated benefit (confirmed by the owner, not yet evidenced in actuals)

A negative value-per-unit term means the benefit is delivering more per user than the business case assumed.
Cost overruns are reported alongside: incremental operating cost above plan reduces net value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.finance.confidence import ConfidenceEngine
from src.finance.portfolio import BENEFIT_TYPES, Evidence, _ds, records
from src.synthetic.catalog import FY_MONTHS

REASONS = {"delayed_implementation": "Delayed implementation", "low_adoption": "Low adoption",
           "incorrect_assumptions": "Incorrect assumptions", "technical_constraints": "Technical constraints",
           "benefit_measurement_problem": "Benefit measurement problem", "pending_validation": "Pending validation",
           "cost_overruns": "Cost overruns", "over_delivery": "Over-delivery vs business case"}


class BenefitsEngine:
    def __init__(self, portfolio):
        self.p = portfolio
        self.repo = portfolio.repo

    def _months_between(self, a: str, b: str) -> int:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        return (b.year - a.year) * 12 + b.month - a.month

    def leakage_lines(self) -> pd.DataFrame:
        r = self.repo
        bm, use = r["benefit_monthly"], r["ai_usage"]
        ini = r.initiatives.set_index("initiative_id")
        lines = self.p._benefit_lines()
        rows = []
        for _, b in lines.iterrows():
            i = ini.loc[b.initiative_id]
            delay = self._months_between(i.planned_go_live, i.actual_go_live)
            s = bm[bm.benefit_id == b.benefit_id].set_index("month").reindex(FY_MONTHS).fillna(0.0)
            u = use[use.initiative_id == b.initiative_id].set_index("month").reindex(FY_MONTHS)
            bc = s.business_case_value.values
            planned = u.planned_active_users.fillna(0).values
            active = u.active_users.fillna(0).values
            shifted = np.array([bc[m - delay] if 0 <= m - delay < 12 else 0.0 for m in range(12)])
            planned_shift = np.array([planned[m - delay] if 0 <= m - delay < 12 else 0.0 for m in range(12)])
            ratio = np.divide(active, planned_shift, out=np.zeros(12), where=planned_shift > 0)
            adopted = shifted * ratio
            measured, realised, validated = s.measured_value.sum(), s.realised_value.sum(), s.validated_value.sum()
            d_delay, d_adopt, d_unit = bc.sum() - shifted.sum(), shifted.sum() - adopted.sum(), adopted.sum() - measured
            unit_reason = b.residual_reason if isinstance(b.residual_reason, str) and b.residual_reason else (
                "over_delivery" if d_unit < 0 else "incorrect_assumptions")
            rows.append({"benefit_id": b.benefit_id, "initiative_id": b.initiative_id, "benefit_type": b.benefit_type,
                         "description": b.description, "business_case": bc.sum(), "owner_forecast": b.owner_forecast_value,
                         "validated": validated, "realised": realised, "gap": bc.sum() - realised,
                         "realisation": realised / bc.sum() if bc.sum() else None,
                         "delayed_implementation": d_delay, "low_adoption": d_adopt, "value_per_unit": d_unit,
                         "value_per_unit_reason": unit_reason, "pending_validation": validated,
                         "go_live_slip_months": delay, "primary_evidence": b.evidence_type, "methodology": b.methodology})
        return pd.DataFrame(rows)

    def realisation_table(self) -> list[dict]:
        lk = self.leakage_lines()
        conf = ConfidenceEngine(self.p).score_lines().set_index("benefit_id")
        lk["confidence"] = lk.benefit_id.map(conf.score)
        lk["confidence_band"] = lk.benefit_id.map(conf.band)
        ev = self.repo["benefit_evidence"]
        prim = ev[ev.evidence_kind.isin(["GL journal extract", "System telemetry export"])].set_index("benefit_id").evidence_kind
        lk["primary_evidence"] = lk.benefit_id.map(prim).fillna("Business-owner confirmation only")
        names = self.repo.initiatives.set_index("initiative_id").name
        lk["initiative_name"] = lk.initiative_id.map(names)
        return records(lk)

    def leakage_summary(self) -> dict:
        lk = self.leakage_lines()
        t = self.p.initiative_table()
        reasons = {"delayed_implementation": lk.delayed_implementation.sum(), "low_adoption": lk.low_adoption.sum()}
        for reason, grp in lk.groupby("value_per_unit_reason"):
            reasons[reason] = reasons.get(reason, 0.0) + grp.value_per_unit.sum()
        reasons["pending_validation"] = lk.pending_validation.sum()
        overrun = float((t.incremental_opex_actual - t.incremental_opex_plan).clip(lower=0).sum())
        by_ini = []
        for iid, grp in lk.groupby("initiative_id"):
            parts = {"delayed_implementation": grp.delayed_implementation.sum(), "low_adoption": grp.low_adoption.sum(),
                     "pending_validation": grp.pending_validation.sum()}
            for reason, g2 in grp.groupby("value_per_unit_reason"):
                parts[reason] = parts.get(reason, 0.0) + g2.value_per_unit.sum()
            main = max(parts.items(), key=lambda kv: kv[1])
            by_ini.append({"initiative_id": iid, "name": t.set_index("initiative_id").name[iid],
                           "business_case": grp.business_case.sum(), "realised": grp.realised.sum(), "unrealised": grp.gap.sum(),
                           "components": {k: float(v) for k, v in parts.items()}, "primary_reason": REASONS[main[0]]})
        by_ini.sort(key=lambda x: -x["unrealised"])
        total_bc, total_real = lk.business_case.sum(), lk.realised.sum()
        return {"business_case": total_bc, "realised": total_real, "unrealised": total_bc - total_real,
                "reasons": [{"reason": k, "label": REASONS.get(k, k), "value": float(v)} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])],
                "cost_overruns": overrun, "by_initiative": by_ini,
                "method": "Counterfactual decomposition: plan -> plan shifted by go-live slip -> adjusted for actual adoption -> measured -> realised"}

    def pnl_reflection(self) -> dict:
        """How much realised value is visible in the P&L (GL-backed) versus operational only."""
        lines = self.p._benefit_lines()
        fin = lines[lines.evidence_type == "financial"].realised_value.sum()
        ops = lines[lines.evidence_type == "operational"].realised_value.sum()
        total_measured = lines.measured_value.sum()
        fl = self.repo["financials"]
        pnl_tagged = fl.ai_attributed_benefit.sum()
        return {"financial_realised": fin, "operational_realised": ops, "validated": lines.validated_value.sum(),
                "hypothetical": lines.hypothetical_value.sum(), "business_case": lines.business_case_value.sum(),
                "share_of_realised_in_pnl": fin / (fin + ops) if fin + ops else None,
                "share_of_expected_in_pnl": fin / lines.business_case_value.sum() if len(lines) else None,
                "share_of_measured_in_pnl": fin / total_measured if total_measured else None,
                "pnl_tagged_benefit": pnl_tagged, "reconciles": abs(pnl_tagged - fin) < 50}

    def assumption_dependency(self) -> list[dict]:
        conf = ConfidenceEngine(self.p).score_lines()
        a = self.repo["assumptions"].set_index("assumption_id")
        lines = self.p._benefit_lines().set_index("benefit_id")
        out = []
        for _, c in conf.iterrows():
            ids = [x for x in str(lines.loc[c.benefit_id, "assumption_ids"]).split(",") if x and x != "nan"]
            share = (c.hypothetical + 0.5 * c.validated) / c.expected if c.expected else 0
            out.append({"benefit_id": c.benefit_id, "initiative_id": c.initiative_id, "description": c.description,
                        "expected": c.expected, "hypothetical": c.hypothetical, "validated": c.validated,
                        "assumption_share": share, "methodology": lines.loc[c.benefit_id, "methodology"],
                        "confidence": c.score, "band": c.band,
                        "assumptions": [{"assumption_id": x, "description": a.loc[x, "description"], "source": a.loc[x, "source"],
                                         "last_reviewed": a.loc[x, "last_reviewed"]} for x in ids if x in a.index]})
        return sorted(out, key=lambda x: -x["assumption_share"])

    def by_type(self) -> list[dict]:
        conf = ConfidenceEngine(self.p)
        s = conf.score_lines()
        return [conf.summarise(s[s.benefit_type == t], label) for t, label in BENEFIT_TYPES.items() if (s.benefit_type == t).any()]

    def register_evidence(self) -> None:
        conf = ConfidenceEngine(self.p)
        s = conf.score_lines()
        ev = self.repo["benefit_evidence"]
        for _, c in s.iterrows():
            e = ev[ev.benefit_id == c.benefit_id]
            self.p._reg(Evidence(
                f"benefit.{c.benefit_id}", c.description, float(c.realised), "USD",
                "Realised = measured - validated; Hypothetical = business case - measured",
                [{"label": "Business case", "value": float(c.expected)}, {"label": "Realised", "value": float(c.realised)},
                 {"label": "Validated", "value": float(c.validated)}, {"label": "Hypothetical", "value": float(c.hypothetical)}]
                + [{"label": f"{x.evidence_kind} ({x.period_from} to {x.period_to}), validated by {x.validated_by}", "value": float(x.amount_covered)}
                   for x in e.itertuples()],
                [_ds("benefit_monthly", 12, f"benefit_id = '{c.benefit_id}'"), _ds("benefit_evidence", len(e), f"benefit_id = '{c.benefit_id}'")],
                f"SELECT month, business_case_value, realised_value, validated_value FROM benefit_monthly WHERE benefit_id = '{c.benefit_id}'",
                notes=[f"Confidence {c.score:.0f}/100 ({c.band})"] + c.basis))
            self.p._reg(Evidence(
                f"confidence.{c.benefit_id}", f"Confidence: {c.description}", float(c.score), "score",
                " + ".join(f"{w:.2f} x {k}" for k, w in __import__('src.finance.confidence', fromlist=['WEIGHTS']).WEIGHTS.items()),
                [{"label": k.replace("_", " "), "value": round(v, 3)} for k, v in c.factors.items()],
                notes=c.basis + [__import__('src.finance.confidence', fromlist=['DISCLAIMER']).DISCLAIMER]))
