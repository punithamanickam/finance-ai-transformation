"""Shared UI helpers: palette, styling, cached engines, evidence rendering."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.calculations.engine import CalculationEngine
from src.calculations.models import format_value
from src.copilot.evidence import BASIS_LABELS, Evidence

# validated categorical order (dataviz reference palette, slots 1-3) + neutral
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
NEUTRAL = "#8a8985"
UP, DOWN = "#2a78d6", "#eb6834"  # waterfall polarity (not status colours)

BASIS_STYLE = {
    "factual_observation": ("📄", "#2a78d6"),
    "calculated_analysis": ("🧮", "#1baf7a"),
    "possible_interpretation": ("💭", "#9a6700"),
    "management_commentary": ("🗣️", "#eb6834"),
}

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1280px;}
.kpi {border:1px solid rgba(128,128,128,.25); border-radius:10px; padding:10px 12px; height:100%;}
.kpi .l {font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; opacity:.7}
.kpi .v {font-size:1.45rem; font-weight:700; line-height:1.2}
.kpi .c {font-size:.8rem} .kpi .s {font-size:.66rem; opacity:.6; margin-top:2px}
.pill {display:inline-block; padding:1px 8px; border-radius:10px; font-size:.72rem; font-weight:600; border:1px solid currentColor; margin-right:4px}
.principle {border-left:3px solid #2a78d6; padding:2px 8px; margin:3px 0; font-size:.8rem}
.disclaimer {border:1px solid #eda100; background:rgba(237,161,0,.08); padding:6px 10px; border-radius:6px; font-weight:600}
</style>
"""

PRINCIPLES = ["AI retrieves and explains.", "Deterministic code calculates.", "Financial data remains the source of truth.",
              "Humans retain decision authority.", "Every material answer is traceable."]


@st.cache_resource
def engine() -> CalculationEngine:
    return CalculationEngine()


def plotly_layout(fig, height=320, pct=False, title=None):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=44 if title else 10, b=10), title=dict(text=title, font=dict(size=14)) if title else None,
                      legend=dict(orientation="h", yanchor="top", y=-0.12, x=0), hovermode="x unified",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=12))
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)", zeroline=False, tickformat=".0%" if pct else None)
    fig.update_xaxes(showgrid=False)
    return fig


def md(text: str) -> str:
    """Escape characters Streamlit markdown would otherwise treat as LaTeX / formatting."""
    return str(text).replace("$", "\\$")


def fmt(v, unit="USD millions", d=1):
    return format_value(v, unit, d)


def render_evidence(ev: Evidence, answer: str | None = None, answer_source: str = "deterministic", show_tables: bool = True):
    st.markdown("##### ANSWER")
    st.markdown(md(answer or ev.headline))
    if ev.disclaimer:
        st.markdown(f"<div class='disclaimer'>⚠️ {ev.disclaimer}</div>", unsafe_allow_html=True)
    if ev.status != "ok":
        st.warning(f"Status: {ev.status.replace('_', ' ')}")
    if ev.key_numbers:
        st.markdown("##### KEY NUMBERS")
        st.dataframe(pd.DataFrame([{"Metric": k.metric, "Current": f"{k.current} ({k.current_label})", "Prior": f"{k.prior} ({k.prior_label})",
                                    "Change": k.change} for k in ev.key_numbers]), hide_index=True, width="stretch")
    st.markdown("##### DRIVERS")
    for basis, label in BASIS_LABELS.items():
        items = [s for s in ev.statements if s.basis == basis]
        if not items:
            continue
        icon, color = BASIS_STYLE[basis]
        st.markdown(f"<span class='pill' style='color:{color}'>{icon} {label}</span>", unsafe_allow_html=True)
        for s in items:
            cite = f"  \n<small style='opacity:.65'>{'; '.join(s.citations)}</small>" if s.citations else ""
            st.markdown(f"- {md(s.text)}{md(cite)}", unsafe_allow_html=True)
    if show_tables and ev.tables:
        with st.expander("Supporting tables", expanded=False):
            for name, rows in ev.tables.items():
                if rows:
                    st.caption(name.replace("_", " "))
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.markdown("##### SOURCE")
    if ev.sources:
        st.dataframe(pd.DataFrame([{"Document": s.document, "Section": s.section, "Page": str(s.page), "Item": s.detail, "Source URL": s.url}
                                   for s in ev.sources]), hide_index=True, width="stretch",
                     column_config={"Source URL": st.column_config.LinkColumn("Source URL", display_text="SEC ↗")})
    else:
        st.caption("No source - see status.")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**CONFIDENCE**  \n{ {'High': '🟢', 'Medium': '🟡', 'Low': '🔴'}[ev.confidence]} {ev.confidence}")
    c2.markdown(f"**BASIS**  \n{' / '.join(ev.basis) or 'n/a'}")
    c3.markdown(f"**NARRATIVE**  \n{'LLM (validated against evidence)' if answer_source == 'llm' else 'Deterministic template'}")
    if ev.calculations:
        with st.expander(f"Calculations ({len(ev.calculations)}) - formula, inputs, engine version"):
            st.dataframe(pd.DataFrame([{"Metric": c.name, "FY": c.fiscal_year, "Result": c.display(2), "Formula": c.formula,
                                        "Inputs (value, unit, page)": c.formula_with_values, "Status": c.status, "Proxy": c.is_proxy,
                                        "Engine": c.engine_version, "Calculated at": c.calculated_at} for c in ev.calculations]),
                         hide_index=True, width="stretch")
