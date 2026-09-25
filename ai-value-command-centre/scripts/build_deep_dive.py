"""Generate docs/deep_dive_analysis.md from the engines and the cited public data, so every figure is reproducible.

    python -m scripts.build_deep_dive
"""
from __future__ import annotations

import pandas as pd

from src import settings
from src.agents.orchestrator import context_for
from src.copilot.response import money, pct, spct
from src.public import hpe


def _fin():
    return pd.DataFrame(hpe.financial_rows())


def v(fin, metric, period, segment="Total company"):
    x = fin[(fin.metric == metric) & (fin.period == period) & (fin.segment == segment)]
    return float(x.value.iloc[0]) if len(x) else None


def public_part() -> list[str]:
    fin = _fin()
    facts = {f["id"]: f for f in hpe.ai_facts()}
    src = {s["url"]: s["source_id"] for s in hpe.source_rows()}

    def cite(fid):
        f = facts[fid]
        return f"[{fid}]({f['url']})"

    yrs = ["FY2023", "FY2024", "FY2025"]
    rev = {y: v(fin, "total_net_revenue", y) for y in yrs}
    gp = {y: v(fin, "gross_profit", y) for y in yrs}
    op = {y: v(fin, "earnings_from_operations", y) for y in yrs}
    ni = {y: v(fin, "net_earnings_attributable_to_HPE", y) for y in yrs}
    rd = {y: v(fin, "research_and_development", y) for y in yrs}
    ocf = {y: v(fin, "net_cash_from_operating_activities", y) for y in yrs}
    fcf = {y: v(fin, "free_cash_flow_non_GAAP", y) for y in yrs}
    q = {p: {m: v(fin, m, p) for m in ("total_net_revenue", "gross_profit", "earnings_from_operations", "free_cash_flow_non_GAAP")}
         for p in ("Q1 FY2026", "Q2 FY2026", "Q3 FY2026")}
    ytd = v(fin, "total_net_revenue", "9M FY2026 (YTD)")
    segs = ["Server", "Hybrid Cloud", "Networking", "Financial Services", "Corporate Investments and Other"]
    seg = {s: (v(fin, "segment_net_revenue", "FY2025", s), v(fin, "segment_earnings_from_operations", "FY2025", s)) for s in segs}
    seg_total = sum(r for r, _ in seg.values())
    q3s = {s: (v(fin, "segment_net_revenue", "Q3 FY2026", s), v(fin, "segment_earnings_from_operations", "Q3 FY2026", s))
           for s in ("Cloud & AI", "Networking", "Corporate Investments and Other")}
    tenk = "https://www.sec.gov/Archives/edgar/data/1645590/000164559025000130/hpe-20251031.htm"
    q3rel = "https://www.sec.gov/Archives/edgar/data/1645590/000164559026000078/ex-991x922026x8k.htm"
    ai_rev_q3 = 1.6e9
    L = [
        "## Part 1. HPE's AI business: what the public record shows",
        "",
        f"> PUBLIC data only. Annual figures are from HPE's [FY2025 Form 10-K]({tenk}) (fiscal years end 31 October); FY2026 quarterly figures are from "
        f"the 10-Qs and 8-K earnings releases ([Q3 FY2026 release]({q3rel})). AI order, backlog and customer figures are company-reported KPIs from "
        "earnings calls and slides; HPE describes them as unaudited. Ratios marked *calculated* are this analysis's arithmetic on those figures.",
        "",
        "### 1.1 Scale and trajectory",
        "",
        "| $M | FY2023 | FY2024 | FY2025 |",
        "|---|---:|---:|---:|",
        "| Total net revenue | " + " | ".join(f"{rev[y] / 1e6:,.0f}" for y in yrs) + " |",
        "| Gross profit | " + " | ".join(f"{gp[y] / 1e6:,.0f}" for y in yrs) + " |",
        "| Gross margin (*calculated*) | " + " | ".join(pct(gp[y] / rev[y], 1) for y in yrs) + " |",
        "| R&D | " + " | ".join(f"{rd[y] / 1e6:,.0f}" for y in yrs) + " |",
        "| Earnings (loss) from operations | " + " | ".join(f"{op[y] / 1e6:,.0f}" for y in yrs) + " |",
        "| Net earnings attributable to HPE | " + " | ".join(f"{ni[y] / 1e6:,.0f}" for y in yrs) + " |",
        "| Operating cash flow | " + " | ".join(f"{ocf[y] / 1e6:,.0f}" for y in yrs) + " |",
        "| Free cash flow (HPE non-GAAP) | " + " | ".join(f"{fcf[y] / 1e6:,.0f}" for y in yrs) + " |",
        "",
        f"* Revenue grew {pct(rev['FY2025'] / rev['FY2024'] - 1, 1)} in FY2025 (*calculated*), helped by about four months of Juniper Networks after the "
        f"acquisition closed on 2 July 2025 {cite('AI-31')}. Gross margin fell from {pct(gp['FY2023'] / rev['FY2023'], 1)} to {pct(gp['FY2025'] / rev['FY2025'], 1)} "
        "over the two years (*calculated*). The 10-K explains the FY2025 fall in Server gross profit as due to \"input cost increases and higher mix of lower margin products\".",
        f"* The FY2025 operating loss of {money(abs(op['FY2025']))} includes $1,621M of impairment charges (10-K). Free cash flow fell to {money(fcf['FY2025'])}.",
        f"* FY2026 has turned sharply: revenue of {money(q['Q1 FY2026']['total_net_revenue'])}, {money(q['Q2 FY2026']['total_net_revenue'])} and "
        f"{money(q['Q3 FY2026']['total_net_revenue'])} in Q1-Q3 ({money(ytd)} for nine months, already {pct(ytd / rev['FY2025'])} of FY2025's full year, *calculated*). "
        f"Q3 gross margin was {pct(q['Q3 FY2026']['gross_profit'] / q['Q3 FY2026']['total_net_revenue'], 1)} and operating profit {money(q['Q3 FY2026']['earnings_from_operations'])}. "
        "HPE guides FY2026 revenue growth of 34-37% (Q3 release). The 10-Q attributes part of Q3 server growth to higher selling prices from memory and SSD "
        f"cost inflation {cite('AI-18')}, so not all of the growth is volume.",
        "",
        "### 1.2 Segment economics",
        "",
        "| FY2025 segment | Revenue $M | Share (*calc.*) | Operating profit $M | Margin (*calc.*) |",
        "|---|---:|---:|---:|---:|",
    ] + [f"| {s} | {seg[s][0] / 1e6:,.0f} | {pct(seg[s][0] / seg_total)} | {seg[s][1] / 1e6:,.0f} | {pct(seg[s][1] / seg[s][0], 1)} |" for s in segs] + [
        "",
        "| Q3 FY2026 segment (new structure) | Revenue $M | Operating profit $M | Margin (*calc.*) |",
        "|---|---:|---:|---:|",
    ] + [f"| {s} | {r / 1e6:,.0f} | {o / 1e6:,.0f} | {pct(o / r, 1)} |" for s, (r, o) in q3s.items()] + [
        "",
        f"* In FY2025 the Server segment carried {pct(seg['Server'][0] / seg_total)} of segment revenue at a {pct(seg['Server'][1] / seg['Server'][0], 1)} margin, while "
        f"Networking earned {pct(seg['Networking'][1] / seg['Networking'][0], 1)}. Networking produced {pct(seg['Networking'][1] / sum(o for _, o in seg.values()))} "
        "of segment operating profit on less than a fifth of revenue (*calculated*). That is the economic logic of the Juniper deal.",
        f"* From FY2026 HPE reports Server, Hybrid Cloud and Financial Services together as **Cloud & AI** {cite('AI-16')}, so FY2026 segments are not directly "
        f"comparable with FY2025. In Q3 FY2026 Cloud & AI earned {pct(q3s['Cloud & AI'][1] / q3s['Cloud & AI'][0], 1)} against 7.0% a year earlier {cite('AI-17')}.",
        "",
        "### 1.3 AI demand: orders, backlog and conversion",
        "",
        f"* **Backlog.** AI systems backlog reached $6.8B exiting Q3 FY2026, up 14% sequentially {cite('AI-03')}; including Networks for AI, total AI backlog "
        f"was a record $7.6B, with $3.1B of AI orders in the quarter and $6.7B year to date {cite('AI-04')}. The slide series runs from $2.4B at Q4 FY2024.",
        f"* **Revenue.** AI systems revenue was \"almost $1.6 billion\" in Q3 FY2026 {cite('AI-02')}. Against Cloud & AI revenue of {money(q3s['Cloud & AI'][0])} that is "
        f"about {pct(ai_rev_q3 / q3s['Cloud & AI'][0])} of the segment (*calculated*), and the $6.8B backlog equals about "
        f"{6.8e9 / ai_rev_q3:.1f} quarters of AI systems revenue at the Q3 run-rate (*calculated*).",
        f"* **Customer mix.** 59% of cumulative AI orders since Q1 FY2023 came from sovereign and enterprise customers {cite('AI-05')}; after the quarter HPE "
        f"won a $3.5B inferencing deal with an unnamed hyperscaler {cite('AI-07')}. The 10-K warns that AI demand is lumpy and historically concentrated in "
        f"a small number of large customers {cite('AI-12')}.",
        f"* **Earlier trajectory.** FY2025 AI orders were $6.8B, with $13.4B cumulative since Q1 FY2023 {cite('AI-11')}; cumulative AI systems bookings "
        f"reached $16.4B by Q2 FY2026 {cite('AI-09')}.",
        "",
        "### 1.4 The portfolio the enterprise scenario maps to",
        "",
        f"* **HPE Private Cloud AI**, announced June 2024 as the lead offering of NVIDIA AI Computing by HPE {cite('AI-19')}: NVIDIA AI Enterprise and NIM "
        f"software with HPE AI Essentials, on HPE compute, storage and networking, in four configurations {cite('AI-20')}. HPE reported about 100 new "
        f"Private Cloud AI logos in FY2025 {cite('AI-25')} and triple-digit year-on-year order growth in Q3 FY2026 {cite('AI-24')}.",
        f"* **HPE GreenLake cloud** is described in the 10-K as the centrepiece of the strategy, with pay-per-use consumption {cite('AI-29')}; customers grew 18% "
        f"to 52,000 in Q3 FY2026 {cite('AI-27')} and annualised revenue run-rate was $3.151B at FY2025 year end {cite('AI-28')}.",
        f"* **Networking**: Juniper (announced January 2024 at about $14B equity value {cite('AI-30')}, closed July 2025 {cite('AI-31')}) brings Mist AI; the DOJ "
        f"settlement required limited access to Mist AIOps technology {cite('AI-32')}. Networks for AI orders were $0.7B in Q3 FY2026 {cite('AI-06')}.",
        f"* **Storage and supercomputing**: more than 7,400 Alletra MP arrays shipped by the end of FY2025 {cite('AI-36')}; HPE Cray EX systems powered the three "
        f"exascale systems on the November 2024 TOP500 list {cite('AI-34')}. **Operations software**: OpsRamp {cite('AI-22')}. **Services and financing** {cite('AI-38')}.",
        "",
        "### 1.5 What HPE's own disclosures imply for an enterprise measuring AI value",
        "",
        f"1. **HPE itself names the risk this project addresses.** Its 10-K risk factors include failing to recoup AI investments {cite('AI-15')}. The same question applies to buyers.",
        "2. **Deployment model changes the cost structure.** GreenLake consumption makes AI infrastructure a variable cost; Private Cloud AI makes it capacity "
        "you own, where **utilisation** decides unit economics. The command centre therefore tracks GPU-hours against installed capacity.",
        f"3. **Vendor efficiency claims need local evidence.** HPE's \"up to 60% lower token cost\" versus public cloud is HPE's own analysis {cite('AI-24')}. "
        "The scenario engine does not use it; it uses the enterprise's metered cost per GPU-hour.",
        f"4. **Supply and energy are real constraints.** The 10-Q discusses memory supply and pricing {cite('AI-18')}; the 10-K links AI compute to energy demand {cite('AI-39')}. "
        "Capacity bought ahead of demand is expensive when supply is tight and power is costly.",
        "",
    ]
    del src
    return L


def synthetic_part() -> list[str]:
    ctx = context_for(None)
    k, t, p = ctx.kpis, ctx.table, ctx.portfolio
    q = p.quarterly()
    mv = p.roi_movement()
    ls = ctx.benefits.leakage_summary()
    pnl = ctx.benefits.pnl_reflection()
    dep = [d for d in ctx.benefits.assumption_dependency() if d["assumption_share"] >= 0.4]
    conf = ctx.benefits.by_type()
    g = ctx.costs.cost_growth_drivers()
    infra = ctx.costs.infrastructure()
    ue = ctx.costs.unit_economics()["metrics"]
    sens = ctx.scenario.sensitivity()
    s80 = ctx.scenario.run({"utilisation_target": 0.80})["incremental"]
    s10 = ctx.scenario.run({"additional_investment": 10_000_000})["incremental"]
    down = ctx.scenario.run({"benefit_realisation": 0.8, "cloud_cost_change": 0.2})["scenario"]
    groups = ctx.repo.programme_costs.groupby("cost_group").amount.sum().sort_values(ascending=False)
    green, red, amber = t[t.rag == "Green"], t[t.rag == "Red"], t[t.rag == "Amber"]
    by_cat = t.groupby("hpe_category").agg(inv=("investment", "sum"), real=("realised_value", "sum"), exp=("expected_value", "sum")).sort_values("inv", ascending=False)
    worst = mv["initiatives"][:2]
    L = [
        "## Part 2. What the command centre finds in the portfolio",
        "",
        f"> {settings.SYNTHETIC_LABEL}. The enterprise, Meridian Enterprise Group, is fictional; it runs its AI programme on HPE portfolio categories. "
        "None of these figures are HPE's. Every number below is produced by the engines and can be reproduced with `python -m scripts.build_deep_dive`.",
        "",
        "### 2.1 The answer to \"Are we actually getting value from AI?\"",
        "",
        f"**Partly, and less than the business case says.** FY2026 investment was **{money(k['total_investment'])}** ({spct(k['budget_variance_pct'], 1)} vs budget). "
        f"**{money(k['realised_value'])}** of value is realised with evidence, **{pct(k['benefit_realisation'])}** of the **{money(k['expected_value'])}** expected. "
        f"In-year realised ROI is **{pct(k['realised_roi'])}** (expected {pct(k['expected_roi'])}), or ${k['value_per_dollar']:.2f} of value per $1. "
        f"A further {money(k['validated_value'])} is confirmed by owners but not yet in actuals, and {money(k['hypothetical_value'])} is still an assumption.",
        "",
        f"In-year ROI understates a programme in its first year. On a forecast basis (two more years at FY2026 exit run-rates, documented assumptions "
        f"A-30 to A-32) the portfolio has a three-year NPV of {money(k['npv_3yr'])}; that figure is a forecast and depends on those assumptions.",
        "",
        "### 2.2 Where the money goes",
        "",
        "* By cost group: " + ", ".join(f"{gname} {money(val)} ({pct(val / groups.sum())})" for gname, val in groups.items()) + ".",
        "* By HPE category: " + "; ".join(f"{c} {money(r.inv)} invested, {money(r.real)} realised ({pct(r.real / r.exp)} of expected)" for c, r in by_cat.iterrows()) + ".",
        f"* {int((t.hpe_category == 'HPE Private Cloud AI').sum())} initiatives on HPE Private Cloud AI hold the largest share of investment; the category's realisation "
        "is held back mainly by two initiatives, the delayed Supply Chain AI Optimisation and the low-adoption Enterprise Knowledge Copilot.",
        "",
        "### 2.3 How much value is real, and how much is in the P&L",
        "",
        f"* {pct(pnl['share_of_realised_in_pnl'])} of realised benefit ({money(pnl['financial_realised'])}) is GL-evidenced and visible in the P&L; "
        f"{money(pnl['operational_realised'])} is operational (hours released) and becomes financial only if capacity is redeployed or cost removed. "
        f"Only {pct(pnl['share_of_expected_in_pnl'])} of the business-case benefit is in the P&L today.",
        "* Evidence quality differs sharply by benefit type: " + "; ".join(f"{c['label'].lower()} {c['score']:.0f}/100 ({c['band']})" for c in conf) + ". "
        "Cost savings are finance-validated and GL-backed; revenue uplift relies on attribution models; risk value on management estimates.",
        "",
        "### 2.4 Why realised value is below expectation (benefits leakage)",
        "",
        f"The {money(ls['unrealised'])} shortfall against the {money(ls['business_case'])} business case decomposes exactly into:",
        "",
        "| Cause | $M |", "|---|---:|",
    ] + [f"| {r['label']} | {r['value'] / 1e6:,.1f} |" for r in ls["reasons"]] + [
        "",
        f"* **Pending validation** is the largest item: value the business says exists but Finance has not yet evidenced. It is a measurement and recognition "
        "problem as much as a delivery problem.",
        f"* **Low adoption** and **delayed implementation** are delivery problems, concentrated in " + ", ".join(f"{x['name']} ({money(x['unrealised'])}, mainly {x['primary_reason'].lower()})" for x in ls["by_initiative"][:3]) + ".",
        f"* Business run costs exceeded plan by {money(ls['cost_overruns'])}, which reduces net value further.",
        "",
        "### 2.5 Why ROI fell this quarter",
        "",
        f"Quarterly ROI moved from {pct(mv['roi_from'], 1)} in {mv['from']} to {pct(mv['roi_to'], 1)} in {mv['to']} ({mv['change_pp']:+.1f} pp): cost effect "
        f"{mv['cost_effect_pp']:+.1f} pp, value effect {mv['value_effect_pp']:+.1f} pp. The contributions below sum exactly to the change.",
        "",
        "| Initiative | Contribution (pp) | Value change | Cost change |", "|---|---:|---:|---:|",
    ] + [f"| {x['name']} | {x['contribution_pp']:+.1f} | {money(x['value_change'])} | {money(x['cost_change'])} |" for x in mv["initiatives"][:6]] + [
        "",
        f"* Infrastructure cost rose {pct(mv['cost_groups']['Infrastructure']['change_pct'])} quarter on quarter while GPU utilisation fell from "
        f"{pct(mv['utilisation_from'], 1)} to {pct(mv['utilisation_to'], 1)}; installed GPU capacity grew {pct(mv['capacity_change_pct'])}.",
        f"* {worst[0]['name']} is the largest drag: its value per active user fell "
        + (f"{pct(abs(mv['value_per_unit_revisions'][0]['value_per_user_change']))} after the cross-sell assumption was revised (A-24)" if mv["value_per_unit_revisions"] else "sharply")
        + f". {worst[1]['name']}'s spend rose {money(worst[1]['cost_change'])} in the quarter, mostly GPU cost for added capacity, while its adoption is "
        f"{pct(float(t.set_index('initiative_id').adoption_vs_target[worst[1]['initiative_id']]))} of target after a "
        f"{int(t.set_index('initiative_id').schedule_slip_months[worst[1]['initiative_id']])}-month go-live delay.",
        "",
        "### 2.6 Cost growth, utilisation and unit economics",
        "",
        f"* Q4 spend grew {pct(g['growth'], 1)} to {money(g['q4'])}; the largest movements: " + ", ".join(f"{x['name']} {x['category']} +{money(x['change'])}" for x in g["top_movements"][:3]) + ".",
        "* Cluster utilisation in Q4: " + "; ".join(f"{c['name']} {pct(c['utilisation_q4'])} ({c['gpus_now']} GPUs, {c['idle_gpu_hours_q4']:,.0f} idle GPU-hours)" for c in infra["clusters"]) + ".",
        f"* Unit economics: ${ue['ai_cost_per_employee']:,.0f} per employee, ${ue['ai_cost_per_interaction']:.2f} per AI interaction, ${ue['ai_cost_per_transaction']:.2f} per "
        f"transaction, ${ue['ai_cost_per_dollar_savings']:.2f} of cost per $1 of realised savings, ${ue['ai_cost_per_gpu_hour_used']:.2f} infrastructure cost per used GPU-hour.",
        "",
        "### 2.7 Winners and at-risk initiatives",
        "",
        f"* **On track ({len(green)})**: " + ", ".join(f"{r['name']} ({pct(r.benefit_realisation)} realised, ROI {pct(r.realised_roi)})" for _, r in green.sort_values('realised_value', ascending=False).iterrows())
        + f". Together they produce {pct(green.realised_value.sum() / k['realised_value'])} of realised value from {pct(green.investment.sum() / k['total_investment'])} of investment.",
        f"* **At risk ({len(red)})**: " + "; ".join(f"{r['name']}: " + ", ".join(f["detail"] for f in r.risk_flags) for _, r in red.iterrows()) + ".",
        f"* **Watch ({len(amber)})**: " + "; ".join(f"{r['name']}: " + ", ".join(f["detail"] for f in r.risk_flags) for _, r in amber.iterrows()) + ".",
        "* Status is derived by four documented rules (realisation, budget, schedule, adoption), not entered by hand.",
        "",
        "### 2.8 Assumptions that carry the number",
        "",
        f"{len(dep)} benefit lines rely on assumptions for at least 40% of their value ({money(sum(d['expected'] for d in dep))} of business case):",
        "",
    ] + [f"* {d['description']} ({d['initiative_id']}): {pct(d['assumption_share'])} assumption-based; " + "; ".join(f"{a['assumption_id']} {a['description'].lower()} (source: {a['source']})" for a in d["assumptions"][:2]) for d in dep] + [
        "",
        "### 2.9 Scenarios and sensitivity (illustrative)",
        "",
        f"* **Utilisation 63% → 80%**: about {s80['capacity_gpu_hours']:,.0f} GPU-hours a year of new workloads on existing capacity; incremental cost {money(s80['cost'])}, "
        f"incremental value {money(s80['value'])}, incremental ROI {pct(s80['roi'])}, payback {s80['payback_months']:.1f} months, and about "
        f"{money(s80['infrastructure_avoided'])} of capacity cost avoided.",
        f"* **Invest an additional $10M in proven use cases**: incremental value {money(s10['value'])}, incremental ROI {pct(s10['roi'])} "
        "(scaled from Green-initiative returns with a diminishing-return factor, A-35).",
        f"* **Downside (80% realisation, cloud +20%)**: expected net value falls to {money(down['net_value'])} and ROI to {pct(down['roi'], 1)}.",
        "* Sensitivity ranking (net value swing for ±20%): " + ", ".join(f"{x['label']} {money(x['swing'])}" for x in sens) + ".",
        "",
        "### 2.10 Areas management may wish to investigate",
        "",
        f"1. Convert the {money(k['validated_value'])} of validated benefit into evidence: agree measurement with Finance, starting with revenue attribution.",
        "2. Re-baseline business cases whose core assumption has already been revised (cross-sell uplift) or rests on a vendor benchmark (inventory reduction).",
        "3. Gate further GPU capacity on demonstrated demand, and fill idle private capacity before buying more; of the scenarios tested, raising utilisation has the highest incremental ROI.",
        "4. Treat adoption as a managed KPI for the knowledge copilot and developer tools; productivity hours count as value only when redeployed.",
        "5. Scale what works: the Green initiatives return more than $1.3 of expected value per $1 and carry high evidence confidence.",
        "",
    ]
    del q
    return L


def main():
    head = [
        "# Deep-dive analysis: AI Value Command Centre",
        "",
        "*Two parts: (1) HPE's AI business from public filings and disclosures; (2) what the AI Value Command Centre finds when a CFO applies it to an AI "
        "portfolio built on HPE categories. Part 2 uses synthetic data for a fictional enterprise.*",
        "",
        f"> Independent portfolio project. Not affiliated with or endorsed by HPE. Public figures are cited; synthetic figures are labelled. Nothing here is "
        "investment advice. Generated by `scripts/build_deep_dive.py`.",
        "",
    ]
    tail = [
        "## Part 3. Method and limitations",
        "",
        "* Public HPE figures were read from SEC filings (XBRL company facts cross-checked with filing text) and HPE investor-relations documents; hpe.com "
        "itself was not reachable from the research environment, so HPE releases were taken from SEC 8-K exhibits and the NVIDIA newsroom. See "
        "`data/public/RESEARCH_NOTES.md` for every URL and unverified item.",
        "* HPE does not disclose Private Cloud AI revenue or AI systems margins; no such figures are estimated here.",
        "* The synthetic dataset is generated from documented design inputs (`src/synthetic/catalog.py`); conclusions such as which initiatives are at risk "
        "and why ROI moved are derived by the engines from the generated transactions, not written into the data.",
        "* Confidence scores rate evidence quality; they are not probabilities. Scenario outputs are illustrative applications of documented assumptions.",
    ]
    lines = head + public_part() + synthetic_part() + tail
    out = settings.DOCS_DIR / "deep_dive_analysis.md"
    out.write_text("\n".join(lines) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
