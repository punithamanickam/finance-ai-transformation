"""CFO Intelligence Copilot - Streamlit front end.

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="CFO Intelligence Copilot", page_icon="📊", layout="wide")

from app.chat.views import chat_view  # noqa: E402
from app.common import CSS, PRINCIPLES, engine  # noqa: E402
from app.dashboard import views as V  # noqa: E402
from src import settings  # noqa: E402
from src.copilot.copilot import CFOCopilot  # noqa: E402
from src.retrieval.vector_store import retrieval_available  # noqa: E402

st.markdown(CSS, unsafe_allow_html=True)

if "copilot" not in st.session_state:
    st.session_state["copilot"] = CFOCopilot(engine=engine(), session_id="streamlit")
copilot: CFOCopilot = st.session_state["copilot"]

with st.sidebar:
    st.markdown("## 📊 CFO Intelligence Copilot")
    st.caption("Independent portfolio proof-of-concept over public SEC filings. Not affiliated with or representing Microsoft or any other company.")
    page = st.radio("View", ["Executive dashboard", "CFO Copilot", "Variance & driver trees", "Scenario lab", "Statements & evidence",
                             "AI governance & audit", "Enterprise extension"], label_visibility="collapsed")
    years = engine().repo.years("revenue")
    st.session_state["fy"] = st.selectbox("Fiscal year", years[::-1][:3], format_func=lambda y: f"FY{y}")
    st.markdown("**AI does not replace financial controls**")
    for p in PRINCIPLES:
        st.markdown(f"<div class='principle'>{p}</div>", unsafe_allow_html=True)
    st.caption(f"LLM: {copilot.provider.name} · {copilot.provider.model}")
    if not retrieval_available():
        st.warning("Retrieval index not built - management commentary unavailable. Run `python -m scripts.build_financial_model`.")

if page == "Executive dashboard":
    V.dashboard()
elif page == "CFO Copilot":
    chat_view(copilot)
elif page == "Variance & driver trees":
    V.variance_view()
elif page == "Scenario lab":
    V.scenario_view()
elif page == "Statements & evidence":
    V.statements_view()
elif page == "AI governance & audit":
    V.governance_view(copilot)
else:
    V.enterprise_view()

st.caption(f"Data: {settings.COMPANY} public filings via SEC EDGAR · see Source registry. Illustrative scenarios are not management guidance. Not investment advice.")
