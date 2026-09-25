"""Deterministic SYNTHETIC data generator.

Turns the design inputs in `catalog.py` into transaction-level tables: monthly cost transactions, budgets,
forecasts, usage, infrastructure utilisation, benefits and evidence, 24 months of P&L, risks and assumptions.

Internal consistency rules (tested in tests/test_data_consistency.py):
* An initiative's actual spend is the sum of its cost transactions; infrastructure cost is part of that sum.
* A cluster's cost is the sum of the infrastructure cost of the initiatives it hosts.
* Business-case benefit follows planned go-live and planned adoption; measured benefit follows actual go-live and
  actual active users, so a delay or low adoption shows up in benefits without being written in.
* Measured = realised + validated for every benefit line and month.
* Financially evidenced benefits appear in the P&L (`financials.ai_attributed_benefit`) in the same months.

Same seed, same data: the generator is reproducible.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src import settings
from src.synthetic import catalog as C

RAMP_MONTHS = 4  # linear adoption ramp after go-live (documented synthetic convention)
HOURS_PER_MONTH = 730
# Design input: utilisation each cluster runs at in FY26-Q3 before later capacity decisions (synthetic).
CLUSTER_Q3_UTILISATION = {"PCAI-EMEA-01": 0.60, "PCAI-US-01": 0.76, "GL-US-01": 0.74, "GL-APJ-01": 0.71, "PUB-GPU-01": 0.88}
BUILD_GPU_HOURS = 250  # model build / fine-tune GPU-hours per month before go-live (synthetic)


def _ramp(k: int) -> float:
    return 0.0 if k < 0 else min(1.0, (k + 1) / RAMP_MONTHS)


def _spend_weights(ini: C.Initiative, go_live: int) -> np.ndarray:
    w = np.zeros(12)
    for m in range(ini.start, 12):
        w[m] = 1.25 if m < go_live else 0.85
    return w


def generate(seed: int = settings.SYNTHETIC_SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    months = C.FY_MONTHS
    t: dict[str, list[dict]] = {k: [] for k in (
        "cost_transactions", "budgets", "ai_usage", "benefit_monthly", "benefits", "benefit_evidence",
        "milestones", "investment_transactions", "forecasts")}
    infra_cost = {cid: np.zeros(12) for cid in C.CLUSTERS}
    gpu_demand = {cid: np.zeros(12) for cid in C.CLUSTERS}  # inference GPU-hours (relative, calibrated below)
    build_demand = {cid: np.zeros(12) for cid in C.CLUSTERS}  # build / fine-tune GPU-hours
    fin_benefit = {}  # (month, bu) -> financially evidenced benefit
    tx_id = 0

    for ini in C.INITIATIVES:
        delay = ini.actual_go_live - ini.planned_go_live
        # ---------- spend: budget vs actual by category ----------
        wp, wa = _spend_weights(ini, ini.planned_go_live), _spend_weights(ini, ini.actual_go_live)
        mix = C.COST_MIX[ini.cost_mix]
        budget = {c: ini.budget * s * wp / wp.sum() for c, s in mix.items()}
        raw = {}
        for c, s in mix.items():
            shock = np.ones(12)
            for cat, frm, mult in ini.cost_shocks:
                if cat == c:
                    shock[frm:] *= mult
            raw[c] = s * wa * shock * (1 + rng.normal(0, 0.04, 12)).clip(0.85, 1.15)
        scale = ini.actual_spend / sum(v.sum() for v in raw.values())
        actual = {c: v * scale for c, v in raw.items()}
        for c in mix:
            for m in range(12):
                if budget[c][m] > 0:
                    t["budgets"].append({"initiative_id": ini.initiative_id, "month": months[m], "cost_category": c,
                                         "cost_group": C.COST_CATEGORIES[c], "budget_amount": round(budget[c][m], 2)})
                amt = actual[c][m]
                if amt <= 0:
                    continue
                parts = [amt] if amt < 60_000 else [amt * 0.6, amt * 0.4]
                for i, part in enumerate(parts):
                    vendor = C.VENDORS[c]
                    if c == "cloud" and i == len(parts) - 1 and ini.public_cloud_share > 0:
                        vendor = C.PUBLIC_CLOUD_VENDOR
                    tx_id += 1
                    t["cost_transactions"].append({
                        "transaction_id": f"CT-{tx_id:05d}", "initiative_id": ini.initiative_id, "month": months[m],
                        "cost_category": c, "cost_group": C.COST_CATEGORIES[c], "cost_type": "programme",
                        "vendor_id": vendor[0], "cost_centre_id": f"CC-{ini.bu_id[3:]}-AI", "amount": round(part, 2),
                        "description": f"{ini.name}: {c}"})
                if c in C.INFRA_CATEGORIES:
                    infra_cost[ini.cluster_id][m] += amt
                if c == "cloud" and ini.public_cloud_share > 0:
                    infra_cost["PUB-GPU-01"][m] += amt * ini.public_cloud_share
        # incremental operating cost borne by the business once live (outside the programme budget)
        live_months = [m for m in range(12) if m >= ini.actual_go_live]
        for m in live_months:
            tx_id += 1
            t["cost_transactions"].append({
                "transaction_id": f"CT-{tx_id:05d}", "initiative_id": ini.initiative_id, "month": months[m],
                "cost_category": "employees", "cost_group": "Incremental operating cost", "cost_type": "incremental_opex",
                "vendor_id": None, "cost_centre_id": f"CC-{ini.bu_id[3:]}-OPS",
                "amount": round(ini.incremental_opex_actual / len(live_months), 2),
                "description": f"{ini.name}: business run cost (review, change management, support)"})

        # ---------- usage ----------
        planned_active = np.array([ini.users_target * ini.adoption_plan * _ramp(m - ini.planned_go_live) for m in range(12)])
        active = np.array([ini.users_target * ini.adoption_actual * _ramp(m - ini.actual_go_live) for m in range(12)])
        active = active * (1 + rng.normal(0, 0.03, 12)).clip(0.93, 1.07)
        for m in range(ini.start, 12):
            licensed = ini.users_target if m >= ini.actual_go_live else round(ini.users_target * 0.05)
            interactions = active[m] * ini.interactions_per_user * float(rng.uniform(0.96, 1.04))
            if m < ini.actual_go_live:  # pilot usage
                interactions = licensed * 0.3 * ini.interactions_per_user
            build_h = BUILD_GPU_HOURS if m < ini.actual_go_live else 60.0
            infer_h = interactions / 1000 * ini.gpu_hours_per_1k_interactions
            gpu_h = infer_h + build_h
            t["ai_usage"].append({
                "initiative_id": ini.initiative_id, "month": months[m], "licensed_users": int(licensed),
                "planned_active_users": int(round(planned_active[m])), "active_users": int(round(active[m])),
                "adoption_rate": round(active[m] / ini.users_target, 4), "interactions": int(round(interactions)),
                "transactions": int(round(interactions * ini.transactions_per_interaction)),
                "transaction_type": ini.transaction_label, "gpu_hours": round(gpu_h, 1)})
            share_pub = ini.public_cloud_share * 0.5
            gpu_demand[ini.cluster_id][m] += infer_h * (1 - share_pub)
            gpu_demand["PUB-GPU-01"][m] += infer_h * share_pub
            build_demand[ini.cluster_id][m] += build_h

        # ---------- benefits ----------
        for li, b in enumerate(ini.benefits, start=1):
            line_id = f"{ini.initiative_id}-B{li}"
            bc_shape = planned_active / planned_active.sum()
            bc = b.business_case * bc_shape
            # value had it gone live late but at planned adoption: plan shifted by the delay
            shifted = np.array([bc[m - delay] if m - delay >= 0 else 0.0 for m in range(12)])
            planned_shift_users = np.array([planned_active[m - delay] if m - delay >= 0 else 0.0 for m in range(12)])
            adopt_ratio = np.divide(active, planned_shift_users, out=np.zeros(12), where=planned_shift_users > 0)
            adopted = shifted * adopt_ratio
            revision = np.ones(12)
            if b.revision:
                revision[b.revision[0]:] = b.revision[1]
            value_factor = b.measured / (adopted * revision).sum()
            measured = adopted * revision * value_factor
            # owner-confirmed but not yet evidenced: spread over live months, weighted towards recent months
            w = measured * (0.5 + 0.6 * (np.arange(12) / 11) ** 2)
            validated = np.minimum(b.validated * w / w.sum(), measured * 0.9) if w.sum() else np.zeros(12)
            validated *= b.validated / validated.sum() if validated.sum() else 0.0
            realised = measured - validated
            unit_value = b.unit_value
            for m in range(12):
                if bc[m] == 0 and measured[m] == 0:
                    continue
                t["benefit_monthly"].append({
                    "benefit_id": line_id, "initiative_id": ini.initiative_id, "month": months[m], "benefit_type": b.type,
                    "business_case_value": round(bc[m], 2), "measured_value": round(measured[m], 2),
                    "realised_value": round(realised[m], 2), "validated_value": round(validated[m], 2),
                    "driver_volume": round(measured[m] / unit_value, 1)})
                if b.evidence_type == "financial":
                    key = (months[m], ini.bu_id)
                    fin_benefit[key] = fin_benefit.get(key, 0.0) + realised[m]
            hypothetical = max(b.business_case - b.measured, 0.0)
            t["benefits"].append({
                "benefit_id": line_id, "initiative_id": ini.initiative_id, "benefit_type": b.type,
                "description": b.description, "driver": b.driver, "driver_unit": b.unit, "unit_value": unit_value,
                "business_case_value": round(b.business_case, 2),
                "owner_forecast_value": round(b.measured + b.owner_forecast_share * hypothetical, 2),
                "evidence_type": b.evidence_type, "methodology": b.methodology, "residual_reason": b.residual_reason or None,
                "finance_validated": b.finance_validated, "owner_confirmed": b.owner_confirmed,
                "assumption_ids": ",".join(b.assumption_ids), "benefit_owner": ini.owner})
            # evidence records
            live = [m for m in range(12) if realised[m] > 0]
            ev_kind = {"financial": ("GL journal extract", "financials"), "operational": ("System telemetry export", "ai_usage")}[b.evidence_type]
            if live:
                t["benefit_evidence"].append({
                    "evidence_id": f"EV-{line_id}-1", "benefit_id": line_id, "evidence_kind": ev_kind[0], "dataset": ev_kind[1],
                    "period_from": months[live[0]], "period_to": months[live[-1]], "amount_covered": round(realised.sum(), 2),
                    "validated_by": "Finance business partner" if b.finance_validated else "Benefit owner",
                    "quality": "high" if b.methodology == "controlled_test" else "medium",
                    "evidence_date": _month_end(months[live[-1]])})
            if b.validated > 0:
                val_months = [m for m in range(12) if validated[m] > 0]
                t["benefit_evidence"].append({
                    "evidence_id": f"EV-{line_id}-2", "benefit_id": line_id, "evidence_kind": "Business-owner confirmation",
                    "dataset": "benefits", "period_from": months[val_months[0]], "period_to": months[val_months[-1]],
                    "amount_covered": round(b.validated, 2), "validated_by": "Benefit owner", "quality": "low",
                    "evidence_date": "2026-09-10"})
            t["benefit_evidence"].append({
                "evidence_id": f"EV-{line_id}-0", "benefit_id": line_id, "evidence_kind": "Approved business case",
                "dataset": "assumptions", "period_from": months[0], "period_to": months[-1],
                "amount_covered": round(b.business_case, 2), "validated_by": "Investment committee", "quality": "low",
                "evidence_date": "2025-08-28"})

        # ---------- milestones, funding, forecasts ----------
        pg, ag = ini.planned_go_live, ini.actual_go_live
        for name, p, a in [("Business case approved", ini.start - 1, ini.start - 1), ("Build start", ini.start, ini.start),
                           ("Pilot", pg - 1, ag - 1), ("Go-live", pg, ag), ("Scale-out complete", pg + 3, ag + 3)]:
            done = a <= 11
            t["milestones"].append({
                "initiative_id": ini.initiative_id, "milestone": name, "planned_date": _month_end(_month(p)),
                "actual_date": _month_end(_month(a)) if done else None,
                "forecast_date": _month_end(_month(a)),
                "status": ("Complete late" if a > p else "Complete") if done else ("Late" if a > p else "Planned")})
        tranches = [0.45, 0.35, 0.20]
        for i, share in enumerate(tranches):
            t["investment_transactions"].append({
                "funding_id": f"FUND-{ini.initiative_id}-{i + 1}", "initiative_id": ini.initiative_id,
                "approval_date": _month_end(_month(max(ini.start - 1, 0) + i * 3)), "gate": ["Gate 1: build", "Gate 2: pilot", "Gate 3: scale"][i],
                "approved_amount": round(ini.budget * share, 2), "approver": "AI Investment Committee"})
        month_actual = sum(actual.values())
        month_budget = sum(budget.values())
        for q, idx in [(1, 2), (2, 5), (3, 8)]:
            to_date, bud_to_date = month_actual[: idx + 1].sum(), month_budget[: idx + 1].sum()
            run_rate = to_date / bud_to_date if bud_to_date else 1.0
            fcst = to_date + month_budget[idx + 1:].sum() * (0.5 + 0.5 * run_rate)
            t["forecasts"].append({"initiative_id": ini.initiative_id, "forecast_version": f"FY26 Q{q} re-forecast",
                                   "horizon": "FY2026", "measure": "programme_spend", "amount": round(fcst, 2)})
        run_cost = month_actual.sum() * dict(_assumption_values())["A-32"]
        for fy in ("FY2027", "FY2028"):
            t["forecasts"].append({"initiative_id": ini.initiative_id, "forecast_version": "FY26 Q4 outlook",
                                   "horizon": fy, "measure": "programme_spend", "amount": round(run_cost, 2)})

    tables = {k: pd.DataFrame(v) for k, v in t.items()}

    # ---------- infrastructure ----------
    rows = []
    for cid, (name, platform, region, product, gpus) in C.CLUSTERS.items():
        cap = np.array(gpus) * HOURS_PER_MONTH
        demand, build = gpu_demand[cid], build_demand[cid]
        q3 = [6, 7, 8]
        # inference intensity is calibrated once, so the cluster runs at its design utilisation in FY26-Q3;
        # every other month follows from usage and capacity decisions
        scale = (CLUSTER_Q3_UTILISATION[cid] * cap[q3].sum() - build[q3].sum()) / demand[q3].sum()
        used = np.minimum(demand * scale + build, cap * 0.97)
        for m in range(12):
            if cap[m] == 0:
                continue
            rows.append({"cluster_id": cid, "month": months[m], "cluster_name": name, "platform": platform, "region": region,
                         "hpe_product_id": product, "gpus": gpus[m], "gpu_hours_capacity": float(cap[m]),
                         "gpu_hours_used": round(float(used[m]), 1), "utilisation": round(float(used[m] / cap[m]), 4),
                         "infrastructure_cost": round(float(infra_cost[cid][m]), 2),
                         "energy_kwh": round(float(used[m] * 1.1 + cap[m] * 0.25), 0)})
    tables["infrastructure_usage"] = pd.DataFrame(rows)

    tables.update(_reference_tables())
    tables["financials"] = _financials(rng, fin_benefit, tables["cost_transactions"])
    return tables


def _assumption_values():
    return [(a[0], a[2]) for a in C.ASSUMPTIONS]


def _month(idx: int) -> str:
    y, m = 2025, 9 + idx
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def _month_end(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    nxt = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
    return nxt.strftime("%Y-%m-%d")


def _reference_tables() -> dict[str, pd.DataFrame]:
    ini_rows = []
    for i in C.INITIATIVES:
        ini_rows.append({
            "initiative_id": i.initiative_id, "name": i.name, "bu_id": i.bu_id, "geography": i.geography,
            "hpe_category": i.hpe_category, "hpe_product_ids": ",".join(i.hpe_products), "use_case": i.use_case,
            "cluster_id": i.cluster_id, "start_date": _month_end(_month(i.start))[:8] + "01",
            "planned_go_live": _month_end(_month(i.planned_go_live)), "actual_go_live": _month_end(_month(i.actual_go_live)),
            "target_completion": i.target_completion, "status": i.status, "budget": i.budget,
            "users_target": i.users_target, "adoption_target": i.adoption_plan,
            "incremental_opex_plan": i.incremental_opex_plan, "owner": i.owner})
    company = pd.DataFrame([C.COMPANY])
    bus = pd.DataFrame([{"bu_id": b, "company_id": "MEG", "name": n, "leader_role": lr, "headcount": h}
                        for b, n, lr, h in C.BUSINESS_UNITS])
    cost_centres = pd.DataFrame([{"cost_centre_id": f"CC-{b[3:]}-{s}", "bu_id": b, "name": f"{n} {label}"}
                                 for b, n, _, _ in C.BUSINESS_UNITS for s, label in (("AI", "AI programme"), ("OPS", "operations"))])
    vendors = {v[0]: v for v in list(C.VENDORS.values()) + [C.PUBLIC_CLOUD_VENDOR] if v[0]}
    vendors_df = pd.DataFrame([{"vendor_id": v[0], "name": v[1], "vendor_type": v[2]} for v in vendors.values()])
    assumptions = pd.DataFrame([{"assumption_id": a[0], "description": a[1], "value": a[2], "unit": a[3], "category": a[4],
                                 "source": a[5], "owner": a[6], "last_reviewed": a[7], "initiative_id": a[8]} for a in C.ASSUMPTIONS])
    risks = pd.DataFrame([{"risk_id": r[0], "initiative_id": r[1], "category": r[2], "title": r[3], "financial_impact": r[4],
                           "probability": r[5], "probability_basis": "Owner assessment at FY26 Q4 risk review (not a model prediction)",
                           "mitigation": r[6], "owner": r[7], "status": r[8]} for r in C.RISKS])
    return {"companies": company, "business_units": bus, "cost_centres": cost_centres, "ai_initiatives": pd.DataFrame(ini_rows),
            "vendors": vendors_df, "assumptions": assumptions, "risks": risks}


def _financials(rng, fin_benefit: dict, costs: pd.DataFrame) -> pd.DataFrame:
    """24 months of BU-level P&L. AI programme spend sits in Technology; evidenced AI benefits lower costs / add margin."""
    rows = []
    prog = costs[costs.cost_type == "programme"].merge(
        pd.DataFrame([{"initiative_id": i.initiative_id, "bu_id": i.bu_id} for i in C.INITIATIVES]), on="initiative_id")
    prog_by = prog.groupby(["month", "bu_id"]).amount.sum().to_dict()
    base_opex = {"BU-CUS": 31e6, "BU-SAL": 24e6, "BU-SCM": 44e6, "BU-FIN": 7.5e6, "BU-TEC": 21e6, "BU-COR": 11e6, "BU-ENG": 26e6}
    for k, ym in enumerate(C.FIN_MONTHS):
        season = 1 + 0.06 * math.sin((k % 12) / 12 * 2 * math.pi)
        growth = 1.04 ** (k / 12)
        revenue = C.COMPANY["annual_revenue_fy2025"] / 12 * season * growth * float(rng.uniform(0.985, 1.015))
        rows.append({"month": ym, "bu_id": "BU-SAL", "account": "Revenue", "amount": round(revenue, 2),
                     "ai_programme_spend": 0.0, "ai_attributed_benefit": round(fin_benefit.get((ym, "BU-SAL"), 0.0), 2)})
        rows.append({"month": ym, "bu_id": "BU-SCM", "account": "Cost of sales", "amount": round(revenue * 0.63, 2),
                     "ai_programme_spend": 0.0, "ai_attributed_benefit": round(fin_benefit.get((ym, "BU-SCM"), 0.0), 2)})
        for bu, base in base_opex.items():
            ai_spend = prog_by.get((ym, bu), 0.0)
            benefit = fin_benefit.get((ym, bu), 0.0) if bu not in ("BU-SAL", "BU-SCM") else 0.0
            opex = base * growth * float(rng.uniform(0.98, 1.02)) + ai_spend - benefit
            rows.append({"month": ym, "bu_id": bu, "account": "Operating expenses", "amount": round(opex, 2),
                         "ai_programme_spend": round(ai_spend, 2), "ai_attributed_benefit": round(benefit, 2)})
    return pd.DataFrame(rows)


def write_csvs(tables: dict[str, pd.DataFrame]) -> None:
    settings.SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(settings.SYNTHETIC_DIR / f"{name}.csv", index=False)


if __name__ == "__main__":
    tabs = generate()
    write_csvs(tabs)
    for n, d in tabs.items():
        print(f"{n:24s} {len(d):6d} rows")
