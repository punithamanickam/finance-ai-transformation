"""CFO Copilot conversational interface."""
from __future__ import annotations

import streamlit as st

from app.common import md, render_evidence

DEMO_QUESTIONS = [
    "What changed in the company's financial performance?",
    "Why did operating margin change?",
    "Which segment drove revenue growth?",
    "How did free cash flow change?",
    "What are the biggest expense movements?",
    "How much is the company investing in R&D?",
    "How has capex changed?",
    "What are the main financial risks disclosed by management?",
    "Show me the evidence behind this conclusion.",
    "Run a scenario where revenue growth is 5 percentage points lower.",
]

KILLER_DEMO = [
    "Revenue increased significantly, but operating margin moved differently. Explain the bridge between revenue growth and operating-income "
    "growth, identify the major cost drivers, distinguish management's stated explanations from your own calculated analysis, and show me "
    "the source for every number.",
    "Now assume revenue growth is 5 percentage points lower next year while gross margin remains constant. What is the illustrative impact on operating income?",
    "Which assumptions have the greatest sensitivity?",
    "Show me exactly how you calculated that.",
]

MORE = ["Which segment has the highest operating margin?", "Compare FY2026 with FY2024.", "What should the CFO investigate further?",
        "How much cash does the company have?", "How does free cash flow compare with net income?", "Is operating leverage improving?",
        "What are the major opportunities visible from the financial data?", "What will revenue be next year?"]


def chat_view(copilot):
    st.subheader("CFO Copilot")
    st.caption("Ask in plain English. Numbers are calculated by the deterministic engine from the filings; the narrative can only use those numbers.")
    with st.sidebar:
        st.markdown("**Demo questions**")
        for q in DEMO_QUESTIONS:
            if st.button(q, key=f"dq-{q}", width="stretch"):
                st.session_state["pending_q"] = q
        st.markdown("**Killer demo (run in order)**")
        for i, q in enumerate(KILLER_DEMO, 1):
            if st.button(f"{i}. {q[:70]}…" if len(q) > 70 else f"{i}. {q}", key=f"kd-{i}", width="stretch"):
                st.session_state["pending_q"] = q
        with st.expander("More questions"):
            for q in MORE:
                if st.button(q, key=f"mq-{q}", width="stretch"):
                    st.session_state["pending_q"] = q
        if st.button("Clear conversation", width="stretch"):
            copilot.history.clear()
            st.session_state["messages"] = []

    msgs = st.session_state.setdefault("messages", [])
    for m in msgs:
        with st.chat_message(m["role"], avatar="🧑‍💼" if m["role"] == "user" else "📊"):
            if m["role"] == "user":
                st.markdown(md(m["content"]))
            else:
                r = m["response"]
                st.markdown(f"**{r.title}**")
                render_evidence(r.evidence, r.answer, r.answer_source)
                st.caption(f"Audit id {r.audit_id} · intent `{r.intent}` · {r.provider}/{r.model} · prompt {r.prompt_ref} · "
                           f"validation: {r.validation.get('notes')}")

    q = st.chat_input("Ask the CFO Copilot…") or st.session_state.pop("pending_q", None)
    if q:
        msgs.append({"role": "user", "content": q})
        with st.spinner("Detecting intent → calculating → retrieving evidence → validating…"):
            r = copilot.ask(q)
        msgs.append({"role": "assistant", "response": r})
        st.rerun()
