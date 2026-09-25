"""Intent handlers. Each builds an Evidence pack from the calculation engine (numbers) and the retriever
(management commentary). No handler lets an LLM produce a number."""
from __future__ import annotations

from src.calculations.driver_trees import flatten, free_cash_flow_tree, operating_income_tree, revenue_tree
from src.calculations.engine import METRICS, CalculationEngine
from src.calculations.models import format_value
from src.calculations.scenario import DISCLAIMER, ScenarioEngine
from src.calculations.variance import NO_EVIDENCE
from src.copilot.evidence import Evidence, SourceItem
from src.copilot.intent import Intent
from src.ingestion.source_registry import load_registry
from src.retrieval.vector_store import get_store

NOT_FOUND = "I could not find sufficient evidence in the available public filings."
CONFLICT = "The available sources contain differing values. The system requires manual review."


def fmt(v, unit="USD millions", d=1):
    return format_value(v, unit, d)


def _filing_sources(fy: int) -> set[str]:
    reg = load_registry()
    ids = set(reg[(reg.fiscal_year == str(fy)) & (reg.ingest == "yes")].source_id)
    return ids


def commentary(ev: Evidence, query: str, fy: int, k: int = 2, types=("management_commentary",), min_score: float = 0.12,
               record_absence: bool = True) -> int:
    hits = get_store().search(query, k=k, content_types=set(types), min_score=min_score, source_ids=_filing_sources(fy) or None)
    n = ev.add_commentary(hits)
    if n == 0 and record_absence:
        ev.add_statement(f"{NO_EVIDENCE} (searched: '{query}')", "management_commentary")
        ev.lower_confidence("Medium")
    return n


def _change_words(v) -> str:
    if v.absolute_change is None:
        return "was not comparable"
    if v.unit == "%":
        return f"{'rose' if v.absolute_change > 0 else 'fell'} {abs(v.absolute_change) * 100:.1f} pp to {fmt(v.current, '%')}"
    word = "increased" if v.absolute_change > 0 else "decreased"
    pct = f" ({v.pct_change:+.1%})" if v.pct_change is not None else ""
    return f"{word} {fmt(abs(v.absolute_change), v.unit)}{pct} to {fmt(v.current, v.unit)}"


def _label(mid: str) -> str:
    return METRICS[mid].name if mid in METRICS else mid.replace("_", " ").capitalize()


def _unavailable(ev: Evidence, what: str, note: str = "") -> Evidence:
    ev.status = "insufficient_evidence"
    ev.confidence = "Low"
    ev.headline = f"{NOT_FOUND} ({what}{' - ' + note if note else ''})"
    return ev


# ---------------------------------------------------------------------------------------------------------------
def metric_change(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="metric_change", title="Metric change", fiscal_year=fy, prior_year=prior)
    lines = []
    for mid in it.metrics[:3]:
        v = eng.variance(mid, fy, prior)
        if v.status == "blocked":
            ev.status = "conflict"
            ev.headline = CONFLICT
            ev.add_statement(v.note, "factual_observation")
            return ev
        if v.status != "ok":
            ev.add_statement(f"{_label(mid)}: {NOT_FOUND} {v.note}", "factual_observation")
            ev.lower_confidence("Low")
            continue
        ev.add_variance(v)
        basis = "calculated_analysis" if mid in METRICS else "factual_observation"
        ev.add_statement(f"{v.label} {_change_words(v)} in FY{fy} (FY{prior}: {fmt(v.prior, v.unit)}).", basis)
        lines.append(f"{v.label} {_change_words(v)} in FY{fy} versus FY{prior}")
        if mid in METRICS:
            ev.add_calc(eng.calculate(mid, fy))
            ev.add_calc(eng.calculate(mid, prior))
        years = [y for y in eng.repo.years("revenue") if y <= fy]
        if len(years) >= 3 and mid not in METRICS:
            c = eng.cagr(mid, years[0], fy)
            if c.ok:
                ev.add_calc(c)
                ev.add_statement(f"{c.name}: {c.display()} (compound annual growth).", "calculated_analysis")
        if mid in {"research_and_development", "sales_and_marketing", "general_and_administrative", "capital_expenditure"}:
            ratio = {"research_and_development": "rd_pct_revenue", "sales_and_marketing": "sm_pct_revenue",
                     "general_and_administrative": "ga_pct_revenue", "capital_expenditure": "capex_intensity"}[mid]
            rv = eng.variance(ratio, fy, prior)
            if rv.status == "ok":
                ev.add_variance(rv)
                ev.add_statement(f"{rv.label} {_change_words(rv)}.", "calculated_analysis")
                lines.append(f"{rv.label.lower()} {_change_words(rv)}")
        if mid == "revenue_per_employee" or mid == "employees":
            ev.lower_confidence("Medium")
        from src.calculations.variance import EXPLANATION_QUERIES
        commentary(ev, EXPLANATION_QUERIES.get(mid, v.label + " increased decreased driven by"), fy, k=1)
    if not ev.key_numbers:
        return _unavailable(ev, ", ".join(it.metrics) or "requested metric")
    ev.headline = "; ".join(lines) + "."
    ev.title = " / ".join(k.metric for k in ev.key_numbers[:2]) + f" - FY{fy} vs FY{prior}"
    return ev


def biggest_changes(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="biggest_changes", title=f"What changed in FY{fy}", fiscal_year=fy, prior_year=prior)
    core = ["revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "operating_cash_flow", "capital_expenditure",
            "free_cash_flow", "cash_and_short_term_investments"]
    vs = [eng.variance(m, fy, prior) for m in core]
    vs = [v for v in vs if v.status == "ok"]
    if not vs:
        return _unavailable(ev, f"FY{fy} vs FY{prior}")
    for v in vs:
        ev.add_variance(v)
    for m in ["gross_margin_pct", "operating_margin_pct", "net_margin_pct"]:
        v = eng.variance(m, fy, prior)
        if v.status == "ok":
            ev.add_variance(v)
    ranked = sorted([v for v in vs if v.pct_change is not None], key=lambda v: -abs(v.pct_change))[:3]
    ev.tables["ranking_definition"] = [{"definition": "Top 3 = largest absolute % change YoY among: " + ", ".join(v.label for v in vs)}]
    for i, v in enumerate(ranked, 1):
        ev.add_statement(f"#{i} by absolute % change: {v.label} {_change_words(v)}.", "calculated_analysis")
    om = eng.variance("operating_margin_pct", fy, prior)
    gm = eng.variance("gross_margin_pct", fy, prior)
    if om.status == "ok" and gm.status == "ok":
        ev.add_statement(f"Gross margin % {_change_words(gm)}; operating margin % {_change_words(om)}.", "calculated_analysis")
    commentary(ev, f"revenue increased driven by growth fiscal year {fy}", fy, k=1)
    commentary(ev, "net income and diluted EPS were positively impacted", fy, k=1, record_absence=False)
    capex, ocf = eng.variance("capital_expenditure", fy, prior), eng.variance("operating_cash_flow", fy, prior)
    if capex.status == ocf.status == "ok" and capex.pct_change and ocf.pct_change and capex.pct_change > ocf.pct_change:
        ev.add_statement(f"Capital expenditure grew faster ({capex.pct_change:+.1%}) than operating cash flow ({ocf.pct_change:+.1%}); "
                         "this may indicate an investment-heavy phase in which free cash flow lags earnings.", "possible_interpretation")
    ev.headline = "The three largest year-over-year moves (by absolute % change) were " + "; ".join(
        f"{v.label} {_change_words(v)}" for v in ranked) + "."
    return ev


def oi_drivers(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="oi_drivers", title=f"Operating income drivers FY{fy} vs FY{prior}", fiscal_year=fy, prior_year=prior)
    tree = operating_income_tree(eng, fy)
    if tree.change is None:
        return _unavailable(ev, "operating income bridge")
    for m in ["operating_income", "revenue", "gross_profit", "research_and_development", "sales_and_marketing", "general_and_administrative"]:
        ev.add_variance(eng.variance(m, fy, prior))
    ev.trees.append(tree.model_dump())
    ev.tables["operating_income_bridge"] = flatten(tree)
    for ch in tree.children:
        ev.add_inputs(ch.inputs)
        ev.add_statement(f"{ch.label}: {fmt(ch.change)} contribution to the change in operating income"
                         + (f" ({ch.share_of_parent_change:.0%} of the change)" if ch.share_of_parent_change is not None else "") + ".",
                         "calculated_analysis")
        for g in ch.children:
            ev.add_statement(f"  – {g.label}: {fmt(g.change)} ({g.formula}).", "calculated_analysis")
    ev.add_statement(tree.note, "calculated_analysis")
    commentary(ev, f"operating income increased driven by fiscal year {fy}", fy, k=2)
    gp = tree.children[0]
    ev.headline = (f"Operating income moved {fmt(tree.change)} to {fmt(tree.current)}. Gross profit added {fmt(gp.change)} "
                   f"(volume {fmt(gp.children[0].change)}, gross-margin-rate effect {fmt(gp.children[1].change)}), while higher "
                   f"R&D, S&M and G&A absorbed {fmt(-sum(c.change for c in tree.children[1:]))}.")
    return ev


def margin_drivers(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    gross = it.sub == "gross"
    ev = Evidence(intent="margin_drivers", title=f"{'Gross' if gross else 'Operating'} margin drivers FY{fy} vs FY{prior}",
                  fiscal_year=fy, prior_year=prior)
    ratios = ["gross_margin_pct", "rd_pct_revenue", "sm_pct_revenue", "ga_pct_revenue"]
    vs = {m: eng.variance(m, fy, prior) for m in ["operating_margin_pct"] + ratios}
    if any(v.status != "ok" for v in vs.values()):
        return _unavailable(ev, "margin decomposition")
    for m, v in vs.items():
        ev.add_variance(v)
        ev.add_calc(eng.calculate(m, fy))
    om = vs["operating_margin_pct"]
    decomposition = [
        {"driver": "Gross margin %", "impact_pp": vs["gross_margin_pct"].absolute_change},
        {"driver": "R&D % of revenue", "impact_pp": -vs["rd_pct_revenue"].absolute_change},
        {"driver": "S&M % of revenue", "impact_pp": -vs["sm_pct_revenue"].absolute_change},
        {"driver": "G&A % of revenue", "impact_pp": -vs["ga_pct_revenue"].absolute_change},
    ]
    ev.tables["operating_margin_decomposition"] = decomposition + [{"driver": "= Change in operating margin", "impact_pp": om.absolute_change}]
    ev.add_statement("Identity: Δ operating margin = Δ gross margin % − Δ R&D% − Δ S&M% − Δ G&A% (all as % of revenue).", "calculated_analysis")
    for d in decomposition:
        ev.add_statement(f"{d['driver']}: {d['impact_pp'] * 100:+.1f} pp impact on operating margin.", "calculated_analysis")
    # segment gross margin view
    rows = []
    for seg, name in eng.segments():
        r1, r0 = eng.value("segment_revenue", fy, seg), eng.value("segment_revenue", prior, seg)
        c1, c0 = eng.value("segment_cost_of_revenue", fy, seg), eng.value("segment_cost_of_revenue", prior, seg)
        if None in (r1, r0, c1, c0):
            continue
        rows.append({"segment": name, f"gross_margin_FY{fy}": (r1 - c1) / r1, f"gross_margin_FY{prior}": (r0 - c0) / r0,
                     "change_pp": (r1 - c1) / r1 - (r0 - c0) / r0, "revenue_share": r1 / eng.value("revenue", fy)})
        for mid in ("segment_revenue", "segment_cost_of_revenue"):
            ev.add_inputs([eng.fact_input(mid, mid, y, seg) for y in (fy, prior)])
    if rows:
        ev.tables["segment_gross_margin"] = rows
        worst = min(rows, key=lambda r: r["change_pp"])
        ev.add_statement(f"Segment gross margin (segment revenue − segment cost of revenue): {worst['segment']} moved "
                         f"{worst['change_pp'] * 100:+.1f} pp, the largest decline/smallest improvement among segments.", "calculated_analysis")
        best = max(rows, key=lambda r: r["revenue_share"])
        if len(rows) > 1:
            ev.add_statement("A shift in revenue mix toward segments with different gross margins may also contribute to the consolidated "
                             f"change (largest segment by revenue: {best['segment']}, {best['revenue_share']:.0%}).", "possible_interpretation")
    commentary(ev, "gross margin percentage decreased increased driven by", fy, k=2)
    if not gross:
        commentary(ev, f"operating income increased driven by fiscal year {fy}", fy, k=1, record_absence=False)
    gm = vs["gross_margin_pct"]
    if gross:
        ev.headline = f"Gross margin % {_change_words(gm)} in FY{fy}." + (
            f" By segment, {worst['segment']} saw the largest decline ({worst['change_pp'] * 100:+.1f} pp)." if rows else "")
    else:
        opex_pp = -(vs["rd_pct_revenue"].absolute_change + vs["sm_pct_revenue"].absolute_change + vs["ga_pct_revenue"].absolute_change)
        ev.headline = (f"Operating margin {_change_words(om)}: gross margin % contributed {gm.absolute_change * 100:+.1f} pp and "
                       f"lower operating expenses as a share of revenue contributed {opex_pp * 100:+.1f} pp.")
    return ev


def expenses(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="expenses", title=f"Expense movements FY{fy} vs FY{prior}", fiscal_year=fy, prior_year=prior)
    lines = ["cost_of_revenue_service", "cost_of_revenue_product", "research_and_development", "sales_and_marketing",
             "general_and_administrative"]
    vs = [v for v in (eng.variance(m, fy, prior) for m in lines) if v.status == "ok"]
    if not vs:
        return _unavailable(ev, "expense lines")
    by_abs = sorted(vs, key=lambda v: -abs(v.absolute_change))
    by_pct = sorted(vs, key=lambda v: -(v.pct_change or 0))
    for v in by_abs[:5]:
        ev.add_variance(v)
    ev.tables["expense_movements_ranked_by_absolute_change"] = [
        {"expense": v.label, f"FY{fy}": v.current, f"FY{prior}": v.prior, "change": v.absolute_change, "change_pct": v.pct_change} for v in by_abs]
    ev.add_statement(f"Largest absolute increase: {by_abs[0].label} ({fmt(by_abs[0].absolute_change)}, {by_abs[0].pct_change:+.1%}).", "calculated_analysis")
    ev.add_statement(f"Fastest growth rate: {by_pct[0].label} ({by_pct[0].pct_change:+.1%}).", "calculated_analysis")
    opex, rev = eng.variance("total_operating_expenses", fy, prior), eng.variance("revenue", fy, prior)
    if opex.status == rev.status == "ok":
        ev.add_variance(opex)
        ev.add_variance(rev)
        faster = "slower" if opex.pct_change < rev.pct_change else "faster"
        ev.add_statement(f"Operating expenses (R&D + S&M + G&A) grew {opex.pct_change:+.1%} versus revenue {rev.pct_change:+.1%} - "
                         f"i.e. {faster} than revenue.", "calculated_analysis")
        cor = eng.variance("cost_of_revenue", fy, prior)
        if cor.status == "ok":
            ev.add_statement(f"Cost of revenue grew {cor.pct_change:+.1%}, {'faster' if cor.pct_change > rev.pct_change else 'slower'} than revenue.",
                             "calculated_analysis")
    for q in ["cost of revenue increased driven by", "research and development expenses increased driven by"]:
        commentary(ev, q, fy, k=1, record_absence=False)
    ev.headline = (f"The largest expense movement was {by_abs[0].label} ({fmt(by_abs[0].absolute_change)}, {by_abs[0].pct_change:+.1%}); "
                   f"the fastest-growing line was {by_pct[0].label} ({by_pct[0].pct_change:+.1%})."
                   + (f" Operating expenses grew {faster} than revenue ({opex.pct_change:+.1%} vs {rev.pct_change:+.1%})." if opex.status == "ok" else ""))
    return ev


def segment(eng: CalculationEngine, it: Intent, question: str = "") -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ql = question.lower()
    ev = Evidence(intent="segment", title=f"Segment analysis FY{fy} vs FY{prior}", fiscal_year=fy, prior_year=prior)
    rows = eng.segment_table(fy) if prior == fy - 1 else []
    if not rows or any(r["revenue"] is None or r["revenue_prior"] is None for r in rows):
        return _unavailable(ev, "segment data")
    for r in rows:
        ev.add_inputs(r["inputs"])
    ev.tables["segments"] = [{k: v for k, v in r.items() if k != "inputs"} for r in rows]
    for r in rows:
        ev.add_variance(eng.variance("segment_revenue", fy, prior, r["segment_id"]), f"{r['segment']} revenue")
    tot = eng.variance("revenue", fy, prior)
    ev.add_variance(tot, "Total revenue")
    top_c = max(rows, key=lambda r: r["contribution_to_growth"] or -9)
    fastest = max(rows, key=lambda r: r["revenue_growth"])
    slowest = min(rows, key=lambda r: r["revenue_growth"])
    hi_m = max(rows, key=lambda r: r["operating_margin"])
    lo_m = min(rows, key=lambda r: r["operating_margin"])
    for r in rows:
        ev.add_statement(f"{r['segment']}: revenue {fmt(r['revenue'])} ({r['revenue_growth']:+.1%}), contributed "
                         f"{r['contribution_to_growth']:.0%} of total revenue growth ({r['growth_contribution_pp'] * 100:+.1f} pp of the "
                         f"{tot.pct_change:+.1%}); operating margin {r['operating_margin']:.1%} (FY{prior}: {r['operating_margin_prior']:.1%}).",
                         "calculated_analysis")
    ev.add_statement("Rankings use explicit definitions: contribution = segment Δrevenue / total Δrevenue; growth = segment revenue YoY %; "
                     "margin = segment operating income / segment revenue. No subjective 'performance' score is applied.", "calculated_analysis")
    tree = revenue_tree(eng, fy)
    ev.trees.append(tree.model_dump())
    ev.tables["revenue_driver_tree"] = flatten(tree)
    for seg_node in tree.children:
        if seg_node.children:
            top = seg_node.children[0]
            ev.add_statement(f"Within {seg_node.label}, the largest revenue increase came from {top.label} ({fmt(top.change)}).", "calculated_analysis")
        for ch in seg_node.children:
            ev.add_inputs(ch.inputs)
    commentary(ev, f"segment revenue increased driven by Azure Microsoft 365 fiscal year {fy}", fy, k=2)
    if "margin" in ql:
        ev.headline = (f"{hi_m['segment']} has the highest operating margin ({hi_m['operating_margin']:.1%}); {lo_m['segment']} the lowest "
                       f"({lo_m['operating_margin']:.1%}).")
    elif "fastest" in ql or "growing" in ql:
        ev.headline = f"{fastest['segment']} grew fastest ({fastest['revenue_growth']:+.1%}); {slowest['segment']} grew slowest ({slowest['revenue_growth']:+.1%})."
    elif "weak" in ql:
        ev.headline = (f"On the defined measures, {slowest['segment']} had the lowest revenue growth ({slowest['revenue_growth']:+.1%}) and "
                       f"{lo_m['segment']} the lowest operating margin ({lo_m['operating_margin']:.1%}). 'Weakest' is not a reported measure - "
                       "these are the underlying numbers.")
    else:
        ev.headline = (f"{top_c['segment']} contributed most to revenue growth: {fmt(top_c['revenue'] - top_c['revenue_prior'])} or "
                       f"{top_c['contribution_to_growth']:.0%} of the {fmt(tot.absolute_change)} total increase.")
    return ev


def cash_position(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="cash_position", title=f"Cash and liquidity at FY{fy} year end", fiscal_year=fy, prior_year=prior)
    for m in ["cash_and_equivalents", "short_term_investments", "cash_and_short_term_investments", "total_debt", "net_debt", "current_ratio",
              "debt_to_equity"]:
        v = eng.variance(m, fy, prior)
        if v.status == "ok":
            ev.add_variance(v)
            if m in METRICS:
                ev.add_calc(eng.calculate(m, fy))
    if not ev.key_numbers:
        return _unavailable(ev, "balance sheet cash")
    cs, nd = eng.variance("cash_and_short_term_investments", fy, prior), eng.calculate("net_debt", fy)
    ev.add_statement(f"Cash, cash equivalents and short-term investments {_change_words(cs)} at June 30, {fy}.", "factual_observation")
    if nd.ok:
        ev.add_statement(f"Net debt (debt − cash & short-term investments) was {nd.display()}{' (a net cash position)' if nd.value < 0 else ''}; "
                         "excludes lease liabilities.", "calculated_analysis")
    commentary(ev, "cash cash equivalents and short-term investments totaled", fy, k=1)
    ev.headline = (f"At June 30, {fy} the company held {fmt(cs.current)} of cash, cash equivalents and short-term investments "
                   f"({_change_words(cs).split(' to ')[0]} year over year)" + (f"; net debt was {nd.display()}." if nd.ok else "."))
    return ev


def cash_flow(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="cash_flow", title=f"Cash flow FY{fy} vs FY{prior}", fiscal_year=fy, prior_year=prior)
    for m in ["operating_cash_flow", "capital_expenditure", "free_cash_flow", "net_income", "capex_reinvestment_rate", "cash_conversion",
              "free_cash_flow_margin"]:
        v = eng.variance(m, fy, prior)
        if v.status == "ok":
            ev.add_variance(v)
        if m in METRICS:
            ev.add_calc(eng.calculate(m, fy))
    if not ev.key_numbers:
        return _unavailable(ev, "cash flow statement")
    tree = free_cash_flow_tree(eng, fy)
    ev.trees.append(tree.model_dump())
    ev.tables["free_cash_flow_tree"] = flatten(tree)
    for ch in tree.children:
        ev.add_inputs(ch.inputs)
    ocf, capex, fcf = (eng.variance(m, fy, prior) for m in ["operating_cash_flow", "capital_expenditure", "free_cash_flow"])
    rr, conv = eng.calculate("capex_reinvestment_rate", fy), eng.calculate("cash_conversion", fy)
    ev.add_statement(f"Operating cash flow {_change_words(ocf)}; capex {_change_words(capex)}.", "factual_observation")
    ev.add_statement(f"Free cash flow (OCF − capex) {_change_words(fcf)}.", "calculated_analysis")
    if rr.ok:
        ev.add_statement(f"{rr.display()} of operating cash flow was reinvested in property and equipment (capex / OCF).", "calculated_analysis")
    if conv.ok:
        ev.add_statement(f"Free cash flow was {conv.display()} net income (FCF / net income).", "calculated_analysis")
        if conv.value < 1:
            ev.add_statement("FCF below net income can reflect heavy capital investment and non-cash gains in net income; the filing's cash-flow "
                             "commentary should be read for the specific causes.", "possible_interpretation")
    commentary(ev, "cash from operations increased due to cash received from customers", fy, k=1)
    commentary(ev, "cash used in investing increased due to additions to property and equipment", fy, k=1, record_absence=False)
    ev.headline = (f"Operating cash flow {_change_words(ocf)}, but capex {_change_words(capex)}, so free cash flow {_change_words(fcf)}."
                   + (f" Capex absorbed {rr.display()} of operating cash flow." if rr.ok else ""))
    return ev


def investment(eng: CalculationEngine, it: Intent, question: str = "") -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="investment", title=f"Where the company is investing - FY{fy}", fiscal_year=fy, prior_year=prior)
    for m in ["research_and_development", "rd_pct_revenue", "capital_expenditure", "capex_intensity", "property_and_equipment", "acquisitions"]:
        v = eng.variance(m, fy, prior)
        if v.status == "ok":
            ev.add_variance(v)
            if m in METRICS:
                ev.add_calc(eng.calculate(m, fy))
    if not ev.key_numbers:
        return _unavailable(ev, "investment data")
    rd, capex, ppe = (eng.variance(m, fy, prior) for m in ["research_and_development", "capital_expenditure", "property_and_equipment"])
    rdp, ci = eng.variance("rd_pct_revenue", fy, prior), eng.variance("capex_intensity", fy, prior)
    ev.add_statement(f"R&D {_change_words(rd)}; R&D as % of revenue {_change_words(rdp)}.", "calculated_analysis")
    ev.add_statement(f"Capex {_change_words(capex)}; capex intensity {_change_words(ci)}.", "calculated_analysis")
    if ppe.status == "ok":
        ev.add_statement(f"Property and equipment, net {_change_words(ppe)} on the balance sheet.", "factual_observation")
    commentary(ev, "research and development expenses increased driven by investments in compute capacity AI", fy, k=1)
    commentary(ev, "investments in AI infrastructure datacenter capacity", fy, k=1, record_absence=False)
    if any(k in question.lower() for k in ("r&d", "research")):
        ev.headline = (f"R&D {_change_words(rd)} in FY{fy}, {fmt(rdp.current, '%')} of revenue (FY{prior}: {fmt(rdp.prior, '%')}). "
                       f"For context, capex {_change_words(capex)}.")
    else:
        ev.headline = (f"Investment is concentrated in capital expenditure: capex {_change_words(capex)} (capex intensity {fmt(ci.current, '%')}), "
                       f"while R&D {_change_words(rd)} ({fmt(rdp.current, '%')} of revenue).")
    return ev


def comparison(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="comparison", title=f"FY{fy} compared with FY{prior}", fiscal_year=fy, prior_year=prior)
    metrics = it.metrics or ["revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "operating_cash_flow",
                             "capital_expenditure", "free_cash_flow", "gross_margin_pct", "operating_margin_pct"]
    for m in metrics:
        v = eng.variance(m, fy, prior)
        if v.status == "ok":
            ev.add_variance(v)
    if not ev.key_numbers:
        return _unavailable(ev, f"FY{fy} vs FY{prior}")
    n = fy - prior
    for m in ["revenue", "operating_income", "net_income"]:
        c = eng.cagr(m, prior, fy)
        if c.ok:
            ev.add_calc(c)
            ev.add_statement(f"{c.name}: {c.display()} per year over {n} year(s).", "calculated_analysis")
    rev = next((k for k in ev.key_numbers if k.metric == "Total revenue"), ev.key_numbers[0])
    ev.headline = f"Across FY{prior}→FY{fy}, {rev.metric.lower()} moved {rev.change} to {rev.current}."
    return ev


def profitability_bridge(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = oi_drivers(eng, it)
    if ev.status != "ok":
        return ev
    ev.intent, ev.title = "profitability_bridge", f"Revenue growth → operating income growth bridge, FY{fy} vs FY{prior}"
    rg, oig = eng.variance("revenue", fy, prior), eng.variance("operating_income", fy, prior)
    dol = ev.add_calc(eng.calculate("operating_leverage", fy))
    ev.add_variance(eng.variance("operating_margin_pct", fy, prior))
    m = margin_drivers(eng, Intent("margin_drivers", fiscal_year=fy, prior_year=prior))
    ev.tables["operating_margin_decomposition"] = m.tables.get("operating_margin_decomposition", [])
    ev.tables["segment_gross_margin"] = m.tables.get("segment_gross_margin", [])
    ev.add_statement(f"Revenue grew {rg.pct_change:+.1%} and operating income grew {oig.pct_change:+.1%}; degree of operating leverage "
                     f"{dol.display()} ({'operating income grew faster than revenue' if dol.value and dol.value > 1 else 'operating income grew slower than revenue'}).",
                     "calculated_analysis")
    for s in m.statements:
        if s.basis in {"calculated_analysis", "possible_interpretation"} and s.text not in {x.text for x in ev.statements}:
            ev.statements.append(s)
    commentary(ev, "gross margin percentage decreased driven by AI infrastructure scaling", fy, k=1, record_absence=False)
    commentary(ev, "operating expenses increased driven by investments", fy, k=1, record_absence=False)
    ev.headline = (f"Revenue grew {rg.pct_change:+.1%} while operating income grew {oig.pct_change:+.1%} (operating leverage {dol.display()}). "
                   + ev.headline + " " + m.headline)
    return ev


def operating_leverage(eng, it):
    ev = profitability_bridge(eng, it)
    ev.intent = "operating_leverage"
    return ev


def risks(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="risks", title=f"Financial risks visible in the FY{fy} filing", fiscal_year=fy, prior_year=prior)
    ev.lower_confidence("Medium")
    for q in ["AI investments may not realize expected returns cost structure uncertainty", "competition cloud-based AI services",
              "cybersecurity data security breach", "tax liabilities", "regulatory legal proceedings", "datacenter capacity supply"]:
        commentary(ev, q, fy, k=1, types=("risk_factor",), min_score=0.08, record_absence=False)
    # quantitative risk indicators computed from the data (not management statements)
    indicators = []
    for m, rule in [("capex_intensity", "rising capital intensity"), ("gross_margin_pct", "gross margin % trend"),
                    ("free_cash_flow_margin", "free cash flow margin trend"), ("cash_conversion", "FCF / net income")]:
        v = eng.variance(m, fy, prior)
        if v.status == "ok":
            ev.add_variance(v)
            indicators.append((rule, v))
    for rule, v in indicators:
        ev.add_statement(f"Indicator – {rule}: {v.label} {_change_words(v)}.", "calculated_analysis")
    other = eng.value("other_income_expense", fy)
    pbt = eng.value("income_before_tax", fy)
    if other is not None and pbt:
        ev.add_statement(f"Other income (expense), net was {fmt(other)} ({other / pbt:.1%} of pre-tax income); non-operating items can make "
                         "net income more volatile than operating income.", "calculated_analysis")
    ev.add_statement("The quoted risk-factor passages are management's disclosures; the indicators are calculated from reported figures. "
                     "Neither is a prediction.", "possible_interpretation")
    ev.headline = ("Management's risk factors emphasise uncertainty around AI demand and cost structure, competition, security and regulation "
                   "(quoted below). In the numbers, " + "; ".join(f"{v.label.lower()} {_change_words(v)}" for _, v in indicators[:3]) + ".")
    ev.basis = list(dict.fromkeys(ev.basis + ["Management commentary"]))
    return ev


def opportunities(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="opportunities", title=f"Opportunities visible in the FY{fy} financial data", fiscal_year=fy, prior_year=prior)
    ev.lower_confidence("Medium")
    mc = eng.variance("microsoft_cloud_revenue", fy, prior)
    if mc.status == "ok":
        ev.add_variance(mc)
        ev.add_statement(f"Microsoft Cloud revenue {_change_words(mc)}.", "factual_observation")
    offs = eng.repo.members("revenue_by_offering")
    growth = []
    for member, label in zip(offs.dimension_member, offs.dimension_label):
        v = eng.variance("revenue_by_offering", fy, prior, member)
        if v.status == "ok" and v.prior and v.prior > 1000:
            growth.append((label, v))
    growth.sort(key=lambda t: -t[1].pct_change)
    ev.tables["offering_growth"] = [{"offering": l, f"FY{fy}": v.current, f"FY{prior}": v.prior, "growth": v.pct_change} for l, v in growth]
    for l, v in growth[:3]:
        ev.add_inputs(v.inputs)
        ev.add_variance(v, f"{l} revenue")
        ev.add_statement(f"{l} revenue {_change_words(v)}.", "calculated_analysis")
    dol = eng.calculate("operating_leverage", fy)
    if dol.ok:
        ev.add_calc(dol)
        ev.add_statement(f"Degree of operating leverage {dol.display()}.", "calculated_analysis")
    ev.add_statement("Fast-growing offerings combined with positive operating leverage may indicate scope for continued margin support, "
                     "subject to the capital intensity required to serve that growth.", "possible_interpretation")
    commentary(ev, "opportunity AI demand Microsoft Cloud growth remaining performance obligation", fy, k=1, record_absence=False)
    ev.headline = ("The fastest-growing offerings were " + ", ".join(f"{l} ({v.pct_change:+.1%})" for l, v in growth[:3]) + "."
                   + (f" Microsoft Cloud revenue {_change_words(mc)}." if mc.status == "ok" else ""))
    return ev


def cfo_attention(eng: CalculationEngine, it: Intent) -> Evidence:
    fy, prior = it.fiscal_year, it.prior_year
    ev = Evidence(intent="cfo_attention", title=f"Areas for CFO investigation - FY{fy}", fiscal_year=fy, prior_year=prior)
    ev.lower_confidence("Medium")
    flags = []

    def v(m):
        return eng.variance(m, fy, prior)

    capex, ocf, fcf, ni = v("capital_expenditure"), v("operating_cash_flow"), v("free_cash_flow"), v("net_income")
    if capex.status == ocf.status == "ok" and capex.pct_change > ocf.pct_change:
        flags.append(("Capital intensity", f"Capex grew {capex.pct_change:+.1%} vs operating cash flow {ocf.pct_change:+.1%}.",
                      "Return on AI/datacenter capex, asset utilisation, depreciation outlook.", [capex, ocf]))
    if fcf.status == ni.status == "ok" and fcf.pct_change is not None and ni.pct_change is not None and fcf.pct_change < ni.pct_change:
        flags.append(("Earnings-to-cash gap", f"Net income grew {ni.pct_change:+.1%} but free cash flow {_change_words(fcf)}.",
                      "Quality of earnings: non-cash gains, working capital, capex timing.", [fcf, ni]))
    gm = v("gross_margin_pct")
    if gm.status == "ok" and gm.absolute_change < 0:
        flags.append(("Gross margin compression", f"Gross margin % {_change_words(gm)}.", "Unit economics of AI infrastructure, pricing, mix.", [gm]))
    ar, rev = v("accounts_receivable"), v("revenue")
    if ar.status == rev.status == "ok" and ar.pct_change > rev.pct_change:
        flags.append(("Receivables growth", f"Accounts receivable grew {ar.pct_change:+.1%} vs revenue {rev.pct_change:+.1%}.",
                      "Collections, billing timing, customer credit.", [ar, rev]))
    other, pbt = eng.value("other_income_expense", fy), eng.value("income_before_tax", fy)
    if other is not None and pbt and abs(other / pbt) > 0.03:
        oth = v("other_income_expense")
        flags.append(("Non-operating volatility", f"Other income (expense), net {_change_words(oth)} ({other / pbt:.1%} of pre-tax income).",
                      "Sustainability of investment gains; separate operating from non-operating performance.", [oth]))
    etr = v("effective_tax_rate_calc")
    if etr.status == "ok" and abs(etr.absolute_change) > 0.005:
        flags.append(("Tax rate movement", f"Effective tax rate {_change_words(etr)}.", "Drivers of tax rate change; uncertain tax positions.", [etr]))
    restated = eng.repo.df[(eng.repo.df.restated_vs_prior_filing == True)]  # noqa: E712
    if len(restated):
        flags.append(("Data governance – restated comparatives",
                      f"{len(restated)} prior-year figure(s) differ between the FY{fy} and FY{fy - 1} filings "
                      f"({', '.join(sorted(set(restated.metric_label)))}).", "Confirm the basis of recast comparatives before trend analysis.", []))
    ev.tables["attention_flags"] = [{"area": a, "observation": o, "what_to_investigate": q} for a, o, q, _ in flags]
    for a, o, q, vs in flags:
        for x in vs:
            ev.add_variance(x)
        ev.add_statement(f"{a}: {o}", "calculated_analysis")
        ev.add_statement(f"{a} – suggested line of enquiry: {q}", "possible_interpretation")
    ev.add_statement("Flags are generated by explicit, documented rules over reported figures (see docs/financial-calculations.md). "
                     "They are prompts for human review, not conclusions.", "calculated_analysis")
    ev.headline = f"{len(flags)} areas meet the documented review rules: " + "; ".join(a for a, *_ in flags) + "."
    return ev


def scenario(eng: CalculationEngine, it: Intent, deltas: dict | None = None, overrides: dict | None = None) -> Evidence:
    se = ScenarioEngine(eng)
    deltas = deltas if deltas is not None else it.scenario.get("deltas", {})
    overrides = overrides if overrides is not None else it.scenario.get("overrides", {})
    fy = se.base_year
    ev = Evidence(intent="scenario", title=f"Illustrative scenario - FY{fy + 1} vs base case", fiscal_year=fy + 1, prior_year=fy, disclaimer=DISCLAIMER)
    if not deltas and not overrides:
        deltas = {"revenue_growth": -0.05}
        ev.add_statement("No specific shock was parsed from the question; defaulting to revenue growth −5 pp.", "calculated_analysis")
    cmp_ = se.compare(overrides=overrides, deltas=deltas)
    base_a, src = se.base_assumptions()
    ev.tables["assumptions"] = [{"assumption": k, "base_case": getattr(base_a, k), "scenario": getattr(cmp_.scenario.assumptions, k),
                                 "base_case_source": src[k]} for k in base_a.model_dump()]
    rows = []
    for k in ["revenue", "gross_profit", "operating_income", "operating_margin", "net_income", "operating_cash_flow", "capital_expenditure", "free_cash_flow"]:
        unit = "%" if k == "operating_margin" else "USD millions"
        rows.append({"line": k, "base_case": cmp_.base.lines[k], "scenario": cmp_.scenario.lines[k], "delta": cmp_.delta[k], "delta_pct": cmp_.delta_pct[k]})
        ch = (format_value(cmp_.delta[k], "pp") if unit == "%" else
              f"{'+' if cmp_.delta[k] >= 0 else '-'}{fmt(abs(cmp_.delta[k]))}" + (f" ({cmp_.delta_pct[k]:+.1%})" if cmp_.delta_pct[k] is not None else ""))
        from src.copilot.evidence import KeyNumber
        ev.key_numbers.append(KeyNumber(metric=k.replace("_", " ").capitalize(), current=fmt(cmp_.scenario.lines[k], unit), prior=fmt(cmp_.base.lines[k], unit),
                                        change=ch, current_value=cmp_.scenario.lines[k], prior_value=cmp_.base.lines[k], change_value=cmp_.delta[k],
                                        unit=unit, current_label=f"Scenario FY{fy + 1}E", prior_label=f"Base case FY{fy + 1}E"))
    ev.tables["scenario_results"] = rows
    ev.tables["method"] = [{"method": cmp_.method}]
    for k in ["revenue", "research_and_development", "sales_and_marketing", "general_and_administrative"]:
        ev.add_calc(eng.reported(k, fy))
    for k in ["revenue_growth", "gross_margin_pct", "effective_tax_rate_calc", "capex_intensity", "ocf_to_net_income"]:
        ev.add_calc(eng.calculate(k, fy))
    shock_txt = ", ".join([f"{k} {v * 100:+.1f} pp" for k, v in deltas.items()] + [f"{k} set to {v:.1%}" for k, v in overrides.items()])
    oi = cmp_.delta["operating_income"]
    ev.add_statement(f"Shock applied: {shock_txt}. All other assumptions held at FY{fy} actual ratios.", "calculated_analysis")
    ev.add_statement(f"Illustrative impact on FY{fy + 1} operating income: {'+' if oi >= 0 else '-'}{fmt(abs(oi))} "
                     f"({cmp_.delta_pct['operating_income']:+.1%}) versus the base case.", "calculated_analysis")
    ev.add_statement(DISCLAIMER + " The base case mechanically carries forward FY actual ratios; it is not a forecast.", "possible_interpretation")
    ev.basis = ["Calculated metric", "Structured financial data", "Scenario model (illustrative)"]
    ev.lower_confidence("Medium")
    ev.headline = (f"{DISCLAIMER} With {shock_txt} (other assumptions at FY{fy} actual ratios), illustrative FY{fy + 1} operating income would be "
                   f"{fmt(cmp_.scenario.lines['operating_income'])}, {'+' if oi >= 0 else '-'}{fmt(abs(oi))} ({cmp_.delta_pct['operating_income']:+.1%}) "
                   f"versus the base case; free cash flow would change by {'+' if cmp_.delta['free_cash_flow'] >= 0 else '-'}{fmt(abs(cmp_.delta['free_cash_flow']))}.")
    return ev


def sensitivity(eng: CalculationEngine, it: Intent) -> Evidence:
    se = ScenarioEngine(eng)
    fy = se.base_year
    ev = Evidence(intent="sensitivity", title=f"Assumption sensitivity - illustrative FY{fy + 1} operating income", fiscal_year=fy + 1, prior_year=fy,
                  disclaimer=DISCLAIMER)
    rows = se.sensitivity("operating_income")
    rows_fcf = se.sensitivity("free_cash_flow")
    for k in ["revenue_growth", "gross_margin_pct", "effective_tax_rate_calc", "capex_intensity", "ocf_to_net_income"]:
        ev.add_calc(eng.calculate(k, fy))
    ev.tables["method"] = [{"method": "Each assumption is shocked up and down by the stated amount from the base case (FY actual ratios "
                                      "carried forward) with all others held constant; impact = scenario line - base-case line."}]
    ev.tables["sensitivity_operating_income"] = rows
    ev.tables["sensitivity_free_cash_flow"] = rows_fcf
    for r in rows[:4]:
        ev.add_statement(f"{r['assumption']} {r['shock']}: operating income {fmt(r['impact_up'])} / {fmt(r['impact_down'])}.", "calculated_analysis")
    ev.add_statement(f"For free cash flow the most sensitive assumption is {rows_fcf[0]['assumption']} ({rows_fcf[0]['shock']}: "
                     f"{fmt(rows_fcf[0]['abs_impact'])}).", "calculated_analysis")
    ev.add_statement(DISCLAIMER, "possible_interpretation")
    ev.basis = ["Calculated metric", "Scenario model (illustrative)"]
    ev.lower_confidence("Medium")
    top = rows[0]
    ev.headline = (f"{DISCLAIMER} Operating income is most sensitive to {top['assumption']} ({top['shock']} ≈ {fmt(top['abs_impact'])}), followed by "
                   f"{rows[1]['assumption']} ({fmt(rows[1]['abs_impact'])}) and {rows[2]['assumption']} ({fmt(rows[2]['abs_impact'])}).")
    return ev


def forecast_request(eng, it):
    ev = Evidence(intent="forecast_request", title="Forecast request", fiscal_year=it.fiscal_year, status="refused", confidence="High")
    ev.headline = ("The public filings do not contain a forecast I can rely on, and this system does not generate predictions. "
                   "I can run an illustrative scenario instead (e.g. 'Run a scenario where revenue growth is 5 percentage points lower').")
    ev.add_statement("Hallucination control: forecasts and management intentions are never generated.", "calculated_analysis")
    ev.basis = ["Governance control"]
    return ev


def document_qa(eng: CalculationEngine, it: Intent, question: str) -> Evidence:
    fy = it.fiscal_year
    ev = Evidence(intent="document_qa", title="Filing text search", fiscal_year=fy)
    hits = get_store().search(question, k=3, min_score=0.1, source_ids=_filing_sources(fy) or None)
    if not hits:
        return _unavailable(ev, "no structured metric or filing passage matched the question")
    ev.add_commentary(hits)
    ev.lower_confidence("Medium")
    ev.headline = "No structured metric matched this question; the most relevant passages from the filing are quoted below verbatim."
    return ev


def show_evidence(prev: Evidence | None, calculation: bool) -> Evidence:
    if prev is None:
        ev = Evidence(intent="show_calculation" if calculation else "show_source", title="Source registry", fiscal_year=0)
        reg = load_registry()
        for _, r in reg[reg.ingest != "no"].iterrows():
            ev.sources.append(SourceItem(document=r.short_name, section=r.source_type, page="-", url=r.source_url, detail=r.reporting_period))
        ev.headline = "There is no previous answer in this session; these are the public sources loaded into the model."
        ev.basis = ["Source registry"]
        return ev
    ev = prev.model_copy(deep=True)
    ev.intent = "show_calculation" if calculation else "show_source"
    ev.title = ("How it was calculated: " if calculation else "Evidence for: ") + prev.title
    ev.statements = [s for s in prev.statements if s.basis != "possible_interpretation"] if not calculation else []
    if calculation:
        for c in prev.calculations:
            ev.add_statement(f"{c.name} FY{c.fiscal_year} = {c.display(2)} | formula: {c.formula} | inputs: {c.formula_with_values or 'n/a'} | "
                             f"engine v{c.engine_version} at {c.calculated_at}", "calculated_analysis")
        for t, rows in prev.tables.items():
            if t in {"operating_income_bridge", "free_cash_flow_tree", "revenue_driver_tree"}:
                for r in rows:
                    if r.get("formula"):
                        ev.add_statement(f"{'  ' * r['depth']}{r['label']}: {r['formula']}", "calculated_analysis")
        if prev.intent in {"scenario", "sensitivity"}:
            for r in prev.tables.get("method", []):
                ev.add_statement(r["method"], "calculated_analysis")
            for r in prev.tables.get("assumptions", []):
                ev.add_statement(f"Assumption {r['assumption']}: base {r['base_case']:.4f} ({r['base_case_source']}) → scenario {r['scenario']:.4f}",
                                 "calculated_analysis")
            for r in prev.tables.get("sensitivity_operating_income", []):
                ev.add_statement(f"Sensitivity {r['assumption']} {r['shock']}: Δ operating income = run(base with {r['assumption']} shocked) − "
                                 f"run(base) = {fmt(r['impact_up'])} / {fmt(r['impact_down'])}", "calculated_analysis")
    ev.headline = (f"Every number in the previous answer comes from {len(prev.sources)} cited source location(s)"
                   + (f" and {len(prev.calculations)} deterministic calculation(s), listed below with formulas and inputs." if calculation else ", listed below with page references."))
    return ev
