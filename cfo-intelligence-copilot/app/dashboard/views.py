"""Dashboard, variance/driver-tree, scenario, statements/evidence, governance and enterprise views."""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.common import DOWN, NEUTRAL, SERIES, UP, engine, fmt, md, plotly_layout, render_evidence
from src import settings
from src.calculations.driver_trees import flatten, free_cash_flow_tree, operating_income_tree, revenue_tree
from src.calculations.engine import METRICS
from src.calculations.scenario import DISCLAIMER, Assumptions, ScenarioEngine
from src.calculations.variance import MAJOR_METRICS, explain_variance, variance_table
from src.governance.audit import read_audit_log
from src.governance.prompts import load_prompt
from src.ingestion.source_registry import load_registry
from src.reporting.brief import build_brief
from src.reporting.report import render_report


@st.cache_data(show_spinner=False)
def _brief(fy: int):
    return build_brief(engine(), fy)


@st.cache_data(show_spinner=False)
def _report_html() -> str:
    return render_report()


def _line(series: dict[str, dict], pct=False, height=260, title=None):
    fig = go.Figure()
    for i, (name, s) in enumerate(series.items()):
        ys = sorted(s)
        fig.add_trace(go.Scatter(x=[f"FY{y}" for y in ys], y=[(s[y] if pct else (s[y] or 0) / 1000) if s[y] is not None else None for y in ys],
                                 name=name, mode="lines+markers", line=dict(width=2, color=SERIES[i % 3]), marker=dict(size=8),
                                 hovertemplate="%{y:.1%}" if pct else "$%{y:,.1f}B"))
    return plotly_layout(fig, height, pct, title)


def _bars(series: dict[str, dict], height=260, title=None):
    fig = go.Figure()
    for i, (name, s) in enumerate(series.items()):
        ys = sorted(s)
        fig.add_trace(go.Bar(x=[f"FY{y}" for y in ys], y=[(s[y] or 0) / 1000 for y in ys], name=name, marker_color=SERIES[i % 3],
                             marker_line_width=0, hovertemplate="$%{y:,.1f}B"))
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.06)
    fig.update_traces(marker_cornerradius=4)
    return plotly_layout(fig, height, False, title)


def dashboard():
    eng = engine()
    fy = st.session_state.get("fy", eng.repo.latest_year)
    st.subheader(f"Executive dashboard · FY{fy} (fiscal year ended June 30, {fy})")
    b = _brief(fy)
    cols = st.columns(6)
    for i, k in enumerate(b.kpis):
        arrow = "▲" if k.direction == "up" else "▼" if k.direction == "down" else "•"
        tone = "" if k.favourable is None else ("color:#1a7f4b" if k.favourable else "color:#c0392b")
        label = "" if k.favourable is None else (" favourable" if k.favourable else " unfavourable")
        with cols[i % 6]:
            st.markdown(f"<div class='kpi'><div class='l'>{k.label}</div><div class='v'>{k.display}</div>"
                        f"<div class='c' style='{tone}'>{arrow} {k.change_display} vs FY{b.prior_year}<span style='opacity:.6'>{label}</span></div>"
                        f"<div class='s'>{k.source}</div></div>", unsafe_allow_html=True)
            ys = sorted(k.series)
            vals = [k.series[y] for y in ys]
            if sum(v is not None for v in vals) >= 2:
                fig = go.Figure(go.Scatter(x=[f"FY{y}" for y in ys], y=vals, mode="lines+markers", line=dict(width=2, color=SERIES[0]),
                                           marker=dict(size=6), hovertemplate="%{x}: %{y:,.3~s}<extra></extra>"))
                fig.update_layout(height=70, margin=dict(l=0, r=0, t=4, b=0), xaxis=dict(visible=False), yaxis=dict(visible=False),
                                  plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"spark-{k.metric_id}")
    st.caption("Trend lines use every fiscal year available in the loaded filings. Hover a card's sparkline for values; "
               "each card cites the filing page of its inputs.")

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("📘 CFO Executive Brief", type="primary", width="stretch"):
            st.session_state["show_brief"] = True
    with c2:
        st.download_button("⬇️ Download executive report (HTML, print-to-PDF)", _report_html(), file_name=f"CFO_Executive_Report_FY{fy}.html",
                           mime="text/html", width="stretch")

    st.markdown("#### Financial performance at a glance")
    for g in b.at_a_glance:
        with st.container(border=True):
            st.markdown(f"**{g['question']}**  \n{md(g['answer'])}")
            st.caption(f"Confidence {g['confidence']} · Basis: {g['basis']}")

    t1, t2 = st.columns(2)
    t1.plotly_chart(_bars(b.trends["Revenue trend"], title="Revenue, operating income, net income (USD B)"), width="stretch")
    t2.plotly_chart(_line(b.trends["Margin trend"], pct=True, title="Margin trend"), width="stretch")
    t3, t4 = st.columns(2)
    t3.plotly_chart(_bars(b.trends["Cash-flow trend"], title="Operating cash flow, capex, free cash flow (USD B)"), width="stretch")
    t4.plotly_chart(_line(b.trends["Investment trend"], pct=True, title="Investment intensity (% of revenue)"), width="stretch")

    if st.session_state.get("show_brief"):
        st.divider()
        st.markdown("## 📘 CFO Executive Brief")
        st.caption("Financial snapshot · revenue, margin, cash-flow and investment trends · segment analysis · key management commentary · "
                   "areas requiring CFO attention - all with source references.")
        segs = b.trends["Segment revenue"]
        st.plotly_chart(_bars(segs, title="Segment revenue (USD B)"), width="stretch")
        for title, ev in b.sections.items():
            with st.expander(title, expanded=title in {"What changed?", "What requires CFO attention?"}):
                render_evidence(ev)


def _waterfall(tree, title):
    labels = [f"Prior year {tree.label}"]
    measures = ["absolute"]
    values = [tree.prior / 1000]
    for ch in tree.children:
        if ch.change is None:
            continue
        labels.append(ch.label.split(" (")[0])
        measures.append("relative")
        values.append(ch.change / 1000)
    labels.append(f"Current year {tree.label}")
    measures.append("total")
    values.append(tree.current / 1000)
    fig = go.Figure(go.Waterfall(x=labels, measure=measures, y=values, increasing=dict(marker_color=UP), decreasing=dict(marker_color=DOWN),
                                 totals=dict(marker_color=NEUTRAL), connector=dict(line=dict(width=1, color="rgba(128,128,128,.4)")),
                                 texttemplate="%{delta:+.1f}", hovertemplate="%{x}: $%{y:,.1f}B<extra></extra>"))
    fig.update_layout(showlegend=False)
    return plotly_layout(fig, 360, title=title)


def variance_view():
    eng = engine()
    fy = st.session_state.get("fy", eng.repo.latest_year)
    years = eng.repo.years("revenue")
    prior = st.selectbox("Compare against", [y for y in years if y < fy][::-1], format_func=lambda y: f"FY{y}")
    st.subheader(f"Variance analysis · FY{fy} vs FY{prior}")
    rows = []
    for v in variance_table(eng, fy, prior):
        ratio = v.unit in {"%", "x"}
        rows.append({"Metric": v.label, f"FY{fy}": fmt(v.current, v.unit), f"FY{prior}": fmt(v.prior, v.unit),
                     "Absolute variance": (fmt(v.absolute_change, "pp") if v.unit == "%" else fmt(v.absolute_change, v.unit)) if v.absolute_change is not None else "n/a",
                     "% variance": f"{v.pct_change:+.1%}" if v.pct_change is not None else ("pp" if ratio else "n/a"),
                     "Direction": {"up": "▲", "down": "▼"}.get(v.direction, "•"),
                     "Assessment": {True: "favourable", False: "unfavourable", None: "neutral / context"}[v.favourable], "Status": v.status})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=560)
    st.caption("Favourability convention: revenue, profit and cash increases are favourable; S&M, G&A and cost of revenue increases are "
               "unfavourable; R&D and capex are shown as neutral (investment) - a documented convention, not a judgement.")
    mid = st.selectbox("Explain a variance", MAJOR_METRICS, format_func=lambda m: METRICS[m].name if m in METRICS else m.replace("_", " ").capitalize())
    ex = explain_variance(eng, mid, fy, prior)
    v = ex.variance
    st.markdown(md(f"**{v.label}** FY{fy}: {fmt(v.current, v.unit)} · FY{prior}: {fmt(v.prior, v.unit)} · variance "
                f"{fmt(v.absolute_change, 'pp' if v.unit == '%' else v.unit) if v.absolute_change is not None else 'n/a'}"
                + (f" ({v.pct_change:+.1%})" if v.pct_change is not None else "")))
    if ex.explanation_status == "evidence_found" and prior == fy - 1:
        for e in ex.evidence:
            st.markdown(f"> {md(e['text'][:900])}\n\n<small>🗣️ Management commentary · {e['citation']}</small>", unsafe_allow_html=True)
    else:
        st.info(ex.explanation if prior == fy - 1 else "Management commentary covers current vs immediately prior year only. "
                "Public filing does not provide sufficient evidence to determine the specific cause for this comparison.")

    st.divider()
    st.subheader("Driver trees")
    tab_oi, tab_rev, tab_fcf = st.tabs(["Operating income", "Revenue growth", "Free cash flow"])
    with tab_oi:
        tree = operating_income_tree(eng, fy)
        if tree.change is not None:
            st.plotly_chart(_waterfall(tree, f"Operating income bridge FY{fy - 1} → FY{fy} (USD B)"), width="stretch")
            st.caption(tree.note)
            st.dataframe(_tree_df(tree), hide_index=True, width="stretch")
    with tab_rev:
        tree = revenue_tree(eng, fy)
        if tree.change is not None:
            st.plotly_chart(_waterfall(tree, f"Revenue bridge by segment FY{fy - 1} → FY{fy} (USD B)"), width="stretch")
            seg = st.selectbox("Drill down into segment", [c.label for c in tree.children])
            node = next(c for c in tree.children if c.label == seg)
            st.plotly_chart(_waterfall(node, f"{seg}: revenue change by product / service offering (USD B)"), width="stretch")
            st.dataframe(_tree_df(node), hide_index=True, width="stretch")
            if any(c.node_id.startswith("unreconciled") for c in node.children):
                st.caption(next(c.note for c in node.children if c.node_id.startswith("unreconciled")))
    with tab_fcf:
        tree = free_cash_flow_tree(eng, fy)
        if tree.change is not None:
            st.plotly_chart(_waterfall(tree, f"Free cash flow bridge FY{fy - 1} → FY{fy} (USD B)"), width="stretch")
            st.dataframe(_tree_df(tree), hide_index=True, width="stretch")


def _tree_df(tree) -> pd.DataFrame:
    rows = flatten(tree)
    return pd.DataFrame([{"Driver": "    " * r["depth"] + r["label"], "Prior": fmt(r["prior"]) if r["prior"] is not None else "",
                          "Current": fmt(r["current"]) if r["current"] is not None else "",
                          "Contribution to change": fmt(r["change"]) if r["change"] is not None else "",
                          "Share of parent change": f"{r['share_of_parent_change']:.0%}" if r["share_of_parent_change"] is not None else "",
                          "Formula / note": r["formula"] or r["note"]} for r in rows])


def scenario_view():
    eng = engine()
    se = ScenarioEngine(eng)
    base, src = se.base_assumptions()
    st.subheader(f"Scenario lab · illustrative FY{se.base_year + 1}")
    st.markdown(f"<div class='disclaimer'>⚠️ {DISCLAIMER} The base case mechanically carries forward FY{se.base_year} actual ratios; "
                "it is not a forecast or a prediction.</div>", unsafe_allow_html=True)
    c = st.columns(3)
    a = {}
    specs = [("revenue_growth", "Revenue growth", -0.2, 0.4), ("gross_margin", "Gross margin %", 0.5, 0.8), ("rd_growth", "R&D growth", -0.2, 0.4),
             ("sm_growth", "S&M growth", -0.2, 0.4), ("ga_growth", "G&A growth", -0.2, 0.4), ("tax_rate", "Tax rate", 0.1, 0.3),
             ("capex_intensity", "Capex % of revenue", 0.1, 0.5), ("ocf_to_net_income", "OCF / net income (x)", 0.8, 1.8)]
    for i, (k, label, lo, hi) in enumerate(specs):
        with c[i % 3]:
            b = getattr(base, k)
            a[k] = st.slider(label, float(lo), float(hi), float(b), 0.005 if k != "ocf_to_net_income" else 0.01,
                             format="%.3f", help=f"Base case: {b:.3f} - {src[k]}")
            st.caption(f"base {b:.1%}" if k != "ocf_to_net_income" else f"base {b:.2f}x")
    cmp_ = se.compare(overrides=a)
    lines = ["revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capital_expenditure", "free_cash_flow"]
    df = pd.DataFrame([{"Line": l.replace("_", " ").capitalize(), "Base case": fmt(cmp_.base.lines[l]), "Scenario": fmt(cmp_.scenario.lines[l]),
                        "Δ": fmt(cmp_.delta[l]), "Δ %": f"{cmp_.delta_pct[l]:+.1%}" if cmp_.delta_pct[l] is not None else ""} for l in lines])
    k1, k2, k3 = st.columns(3)
    k1.metric("Illustrative operating income", fmt(cmp_.scenario.lines["operating_income"]), fmt(cmp_.delta["operating_income"]))
    k2.metric("Illustrative operating margin", f"{cmp_.scenario.lines['operating_margin']:.1%}",
              f"{(cmp_.scenario.lines['operating_margin'] - cmp_.base.lines['operating_margin']) * 100:+.1f} pp")
    k3.metric("Illustrative free cash flow", fmt(cmp_.scenario.lines["free_cash_flow"]), fmt(cmp_.delta["free_cash_flow"]))
    st.dataframe(df, hide_index=True, width="stretch")
    st.caption("Method: " + cmp_.method)
    st.markdown("#### Sensitivity - which assumptions matter most?")
    target = st.radio("Target", ["operating_income", "free_cash_flow", "net_income"], horizontal=True)
    rows = se.sensitivity(target)[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=[r["assumption"] + f" ({r['shock']})" for r in rows], x=[r["impact_up"] / 1000 for r in rows], orientation="h",
                         name="Assumption up", marker_color=SERIES[0], hovertemplate="%{x:+.2f}B"))
    fig.add_trace(go.Bar(y=[r["assumption"] + f" ({r['shock']})" for r in rows], x=[r["impact_down"] / 1000 for r in rows], orientation="h",
                         name="Assumption down", marker_color=SERIES[1], hovertemplate="%{x:+.2f}B"))
    fig.update_layout(barmode="overlay", bargap=0.35)
    fig.update_traces(marker_cornerradius=4)
    st.plotly_chart(plotly_layout(fig, 360, title=f"Tornado: Δ illustrative {target.replace('_', ' ')} (USD B) vs base case"), width="stretch")


def statements_view():
    eng = engine()
    repo = eng.repo
    st.subheader("Financial statements & evidence explorer")
    tab1, tab2, tab3, tab4 = st.tabs(["Statements", "Fact provenance", "Sources", "Data quality"])
    with tab1:
        for stmt in ["Income Statement", "Balance Sheet", "Cash Flow Statement"]:
            st.markdown(f"**{stmt}** (USD millions, except per-share)")
            piv = repo.statement(stmt)
            st.dataframe(piv.reset_index().drop(columns=["metric_id"]).rename(columns={"metric_label": "Line item"}), hide_index=True, width="stretch")
        seg = repo.df[repo.df.statement == "Segment"].pivot_table(index=["dimension_label", "metric_label"], columns="fiscal_year", values="value")
        st.markdown("**Segment P&L** (USD millions)")
        st.dataframe(seg.reset_index(), hide_index=True, width="stretch")
    with tab2:
        st.caption("Every number in the model with its provenance: document, page, section, table, row, column, XBRL concept and fact id.")
        q = st.text_input("Filter (metric, concept, row label…)", "")
        d = repo.df
        if q:
            mask = d.apply(lambda r: q.lower() in " ".join(str(x) for x in r.values).lower(), axis=1)
            d = d[mask]
        st.dataframe(d[["fact_key", "reporting_period", "statement", "metric_label", "dimension_label", "value", "unit", "source_document",
                        "source_page", "source_section", "source_table", "row_label", "column_label", "xbrl_concept", "xbrl_fact_id",
                        "extraction_method", "occurrences", "consistency", "restated_vs_prior_filing", "source_url"]],
                     hide_index=True, width="stretch", height=520, column_config={"source_url": st.column_config.LinkColumn("source_url", display_text="SEC ↗")})
    with tab3:
        st.dataframe(load_registry().drop(columns=["short_name"]), hide_index=True, width="stretch",
                     column_config={"source_url": st.column_config.LinkColumn("source_url")})
        st.caption("Raw filings are downloaded from SEC EDGAR at build time and are not redistributed in the repository.")
    with tab4:
        p = settings.PROJECT_ROOT / "docs" / "data_quality_report.md"
        st.markdown(p.read_text() if p.exists() else "Run `python -m scripts.build_financial_model` to generate the report.")


def governance_view(copilot):
    st.subheader("AI governance")
    c1, c2 = st.columns([1, 1])
    prompt = load_prompt("cfo_copilot_system")
    with c1:
        st.markdown("**Model card**")
        st.table(pd.DataFrame([
            ("LLM provider", copilot.provider.name), ("Model", copilot.provider.model),
            ("Prompt version", prompt.ref), ("Calculation engine", f"Python deterministic engine v{settings.CALC_ENGINE_VERSION}"),
            ("Retrieval", "TF-IDF (1-2 gram) cosine similarity over filing chunks; source-filtered by fiscal year"),
            ("Structured data", f"SQLite ({len(engine().repo.df)} facts, iXBRL-extracted)"),
            ("Numeric guardrail", "Every number in LLM text must match the evidence pack, else deterministic narrative"),
            ("Human authority", "Outputs are decision support; no automated actions"),
        ], columns=["Control", "Value"]))
    with c2:
        st.markdown("**System prompt (versioned)**")
        st.code(prompt.text, language="markdown")
    st.markdown("**Audit log** - user question → retrieved sources → metrics selected → calculation → LLM prompt → LLM response → validation → final answer")
    log = read_audit_log(100)
    if not log:
        st.info("No interactions yet - ask the copilot a question.")
    else:
        st.dataframe(pd.DataFrame([{"timestamp": r["timestamp"], "question": r["user_query"], "intent": r.get("intent"), "confidence": r.get("confidence"),
                                    "answer_source": r.get("answer_source"), "model": r.get("model"), "prompt": r.get("prompt_version"),
                                    "interaction_id": r["interaction_id"]} for r in log]), hide_index=True, width="stretch")
        pick = st.selectbox("Inspect interaction", [r["interaction_id"] for r in log],
                            format_func=lambda i: next(f"{r['timestamp']} · {r['user_query'][:70]}" for r in log if r["interaction_id"] == i))
        rec = next(r for r in log if r["interaction_id"] == pick)
        for s in rec["steps"]:
            with st.expander(f"{s['step']} · {s['at']}"):
                st.json({k: v for k, v in s.items() if k not in {"step", "at"}})
        st.caption(f"Final answer SHA-256: {rec.get('final_answer_sha256')}")
    st.markdown("**Source conflicts & restatements (require human review)**")
    if settings.CONFLICTS_CSV.exists() and settings.CONFLICTS_CSV.stat().st_size > 1:
        st.dataframe(pd.read_csv(settings.CONFLICTS_CSV), hide_index=True, width="stretch")


def enterprise_view():
    st.subheader("From Financial Statement Copilot → Enterprise CFO Intelligence Platform")
    st.caption("Conceptual extension. Illustrates how the same architecture could run on enterprise data; it does not describe any specific company's systems.")
    img = settings.PROJECT_ROOT / "architecture" / "enterprise_extension.png"
    if img.exists():
        st.image(str(img), width="stretch")
    st.markdown((settings.PROJECT_ROOT / "docs" / "enterprise-roadmap.md").read_text() if (settings.PROJECT_ROOT / "docs" / "enterprise-roadmap.md").exists() else "")
