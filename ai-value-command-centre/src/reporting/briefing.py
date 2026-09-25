"""CFO / board briefing generator (Executive Reporting Agent output).

Every sentence is assembled from engine outputs. Language is deliberately neutral: the briefing surfaces questions
and areas management may wish to investigate; it does not make decisions.
"""
from __future__ import annotations

import html
from datetime import date

from src import settings
from src.copilot.response import money, pct
from src.finance.portfolio import BENEFIT_TYPES


def build_briefing(ctx) -> dict:
    k, t = ctx.kpis, ctx.table
    q = ctx.portfolio.quarterly()
    mv = ctx.portfolio.roi_movement()
    ls = ctx.benefits.leakage_summary()
    pnl = ctx.benefits.pnl_reflection()
    dep = [d for d in ctx.benefits.assumption_dependency() if d["assumption_share"] >= 0.4]
    growth = ctx.costs.cost_growth_drivers()
    red = t[t.rag == "Red"].sort_values("expected_value", ascending=False)
    over = t[t.budget_variance_pct > 0.05].sort_values("budget_variance_pct", ascending=False)
    green = t[t.rag == "Green"].sort_values("realised_value", ascending=False)
    sens = ctx.scenario.sensitivity()
    util = ctx.scenario.run({"utilisation_target": 0.80})["incremental"]
    names = t.set_index("initiative_id")["name"]
    s = []

    s.append(("AI Portfolio Executive Summary", [
        f"FY2026 AI investment was {money(k['total_investment'])} across {k['initiatives']} initiatives. Realised value is "
        f"{money(k['realised_value'])} ({pct(k['benefit_realisation'])} of the {money(k['expected_value'])} expected), giving an in-year realised ROI of "
        f"{pct(k['realised_roi'])} against an expected {pct(k['expected_roi'])}.",
        f"A further {money(k['validated_value'])} is confirmed by business owners but not yet evidenced in actuals; {money(k['hypothetical_value'])} "
        f"remains dependent on business-case assumptions.",
        f"{k['at_risk']} initiatives are flagged at risk and {k['watch']} are on watch. {len(green)} initiatives are at or above 90% realisation "
        f"and carry {pct(green.realised_value.sum() / k['realised_value'])} of realised value.",
        f"On the forecast outlook (two further years at FY2026 exit run-rates, documented assumptions A-30 to A-32), the portfolio shows a three-year NPV of "
        f"{money(k['npv_3yr'])}. This is a forecast, not an actual.",
    ]))
    s.append(("Investment", [
        f"Spend of {money(k['total_investment'])} was {pct(k['budget_variance_pct'], 1)} above the {money(k['budget'])} budget.",
        "By quarter: " + ", ".join(f"{r.quarter} {money(r.investment)}" for r in q.itertuples()) + ".",
        "Largest investments: " + ", ".join(f"{r['name']} {money(r.investment)}" for _, r in t.sort_values('investment', ascending=False).head(3).iterrows()) + ".",
    ]))
    s.append(("Value Realisation", [
        "Realised value by type: " + ", ".join(f"{BENEFIT_TYPES[b].lower()} {money(float(t[f'realised_{b}'].sum()))}" for b in BENEFIT_TYPES if t[f'realised_{b}'].sum() > 0) + ".",
        f"{pct(pnl['share_of_realised_in_pnl'])} of realised benefit ({money(pnl['financial_realised'])}) is visible in the P&L; "
        f"{money(pnl['operational_realised'])} is operational (released hours) and becomes financial value only if capacity is redeployed or cost removed.",
        "Unrealised benefit of " + money(ls["unrealised"]) + " breaks down as: " + ", ".join(f"{r['label'].lower()} {money(r['value'])}" for r in ls["reasons"] if r["value"] > 0) + ".",
    ]))
    s.append(("ROI", [
        f"Quarterly ROI moved {mv['change_pp']:+.1f} pp from {pct(mv['roi_from'], 1)} ({mv['from']}) to {pct(mv['roi_to'], 1)} ({mv['to']}); "
        f"cost effect {mv['cost_effect_pp']:+.1f} pp, value effect {mv['value_effect_pp']:+.1f} pp.",
        "Largest contributors: " + ", ".join(f"{x['name']} {x['contribution_pp']:+.1f} pp" for x in mv["initiatives"][:3]) + ".",
        f"Value per $1 invested to date: ${k['value_per_dollar']:.2f}.",
    ]))
    s.append(("Cost Trends", [
        f"AI spend grew {pct(growth['growth'], 1)} quarter on quarter to {money(growth['q4'])}. "
        + "Main movements: " + ", ".join(f"{c['label']} {money(c['change'])}" for c in growth["by_category"][:3] if c["change"] > 0) + ".",
        f"GPU utilisation fell from {pct(mv['utilisation_from'], 1)} to {pct(mv['utilisation_to'], 1)} while installed capacity rose {pct(mv['capacity_change_pct'])}.",
    ]))
    s.append(("Key Variances", [f"{r['name']}: {money(r.actual_spend)} spent vs {money(r.budget)} budget ({pct(r.budget_variance_pct)})." for _, r in over.iterrows()]
              or ["No initiative is more than 5% over budget."]))
    s.append(("Benefits at Risk", [f"{r['name']}: {money(r.realised_value)} realised of {money(r.expected_value)} expected ({pct(r.benefit_realisation)}); "
                                   + ", ".join(f["detail"] for f in r.risk_flags) + "." for _, r in red.iterrows()]))
    s.append(("Major Assumptions", [f"{names[d['initiative_id']]}: {d['description']}: {pct(d['assumption_share'])} of {money(d['expected'])} depends on "
                                    + ", ".join(f"{a['assumption_id']} ({a['description'].lower()}, source: {a['source'].lower()})" for a in d["assumptions"][:2]) + "."
                                    for d in dep[:6]]))
    top_red = red.iloc[0] if len(red) else None
    s.append(("Key Questions for Management", [
        f"What evidence would move the {money(k['validated_value'])} of validated benefit into financial actuals, and by when?",
        (f"Is the business case for {top_red['name']} still valid given realisation of {pct(top_red.benefit_realisation)} and a "
         f"{int(top_red.schedule_slip_months)}-month go-live slip?") if top_red is not None else "Are the business cases for at-risk initiatives still valid?",
        "Which released productivity hours have been redeployed, and how will that show up in cost or output?",
        f"Should GPU capacity additions be gated on demonstrated demand, given utilisation of {pct(mv['utilisation_to'], 1)}?",
        "Which revenue-uplift benefits have an attribution method agreed with Finance?",
    ]))
    s.append(("Recommended Areas for Investigation", [
        f"Management may wish to investigate the adoption shortfall in {', '.join(t[t.adoption_vs_target < 0.6]['name'])}, which accounts for "
        f"{money(next((r['value'] for r in ls['reasons'] if r['reason'] == 'low_adoption'), 0))} of unrealised benefit.",
        f"Management may wish to review capacity planning: raising utilisation to 80% would free about {util['capacity_gpu_hours']:,.0f} GPU-hours a year "
        f"(illustrative incremental ROI {pct(util['roi'])} on synthetic assumptions).",
        f"Management may wish to prioritise evidence for benefits that rely mainly on assumptions ({len(dep)} lines, {money(sum(d['expected'] for d in dep))}).",
        f"The value estimate is most sensitive to {sens[0]['label'].lower()} and {sens[1]['label'].lower()}; management may wish to stress-test these first.",
    ]))
    return {"title": "AI Portfolio: CFO Briefing", "subtitle": f"{k['period']} | as of {k['as_of']}", "generated": date.today().isoformat(),
            "scope": ctx.bu_scope or "Whole portfolio", "sections": [{"heading": h, "points": p} for h, p in s],
            "kpis": {x: k[x] for x in ("total_investment", "realised_value", "expected_value", "realised_roi", "expected_roi", "benefit_realisation", "at_risk")},
            "disclaimer": settings.SYNTHETIC_LABEL + ". Generated deterministically from the engines; language is advisory and decisions rest with management."}


def to_markdown(b: dict) -> str:
    out = [f"# {b['title']}", f"*{b['subtitle']} | scope: {b['scope']} | generated {b['generated']}*", "", f"> {b['disclaimer']}", ""]
    for sec in b["sections"]:
        out.append(f"## {sec['heading']}")
        out += [f"- {p}" for p in sec["points"]]
        out.append("")
    return "\n".join(out)


def to_html(b: dict) -> str:
    k = b["kpis"]
    tiles = [("Investment", money(k["total_investment"])), ("Realised value", money(k["realised_value"])), ("Expected value", money(k["expected_value"])),
             ("Realised ROI", pct(k["realised_roi"])), ("Benefit realisation", pct(k["benefit_realisation"])), ("At-risk initiatives", str(k["at_risk"]))]
    secs = "".join(f"<section><h2>{html.escape(s['heading'])}</h2><ul>" + "".join(f"<li>{html.escape(p)}</li>" for p in s["points"]) + "</ul></section>"
                   for s in b["sections"])
    tiles_html = "".join(f"<div class='tile'><div class='l'>{html.escape(a)}</div><div class='v'>{html.escape(v)}</div></div>" for a, v in tiles)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CFO Briefing</title><style>
:root{{--bg:#fbfbfa;--fg:#1d2330;--muted:#5d6675;--line:#e3e5e8;--accent:#01a982;--warn:#b54708}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--fg:#e8eaee;--muted:#9aa3b2;--line:#2a2f39;--accent:#2fd3a8;--warn:#f79009}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.55 Inter,system-ui,sans-serif;margin:0;padding:32px 16px}}
main{{max-width:880px;margin:0 auto}} h1{{font-size:26px;margin:0}} .sub{{color:var(--muted);margin:4px 0 20px}}
.note{{border-left:3px solid var(--warn);padding:8px 12px;color:var(--muted);font-size:13px;margin-bottom:20px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:24px}}
.tile{{border:1px solid var(--line);border-radius:8px;padding:10px 12px}} .l{{color:var(--muted);font-size:12px}} .v{{font-size:20px;font-weight:600}}
h2{{font-size:17px;border-bottom:1px solid var(--line);padding-bottom:6px;margin-top:26px}} li{{margin:6px 0}}
</style></head><body><main><h1>{html.escape(b['title'])}</h1><div class="sub">{html.escape(b['subtitle'])} &middot; scope: {html.escape(b['scope'])} &middot; generated {b['generated']}</div>
<div class="note">{html.escape(b['disclaimer'])}</div><div class="tiles">{tiles_html}</div>{secs}</main></body></html>"""
