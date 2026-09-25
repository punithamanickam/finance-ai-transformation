"""Run the executive demo questions end-to-end and write docs/demo_transcript.md.

    python -m scripts.run_demo            # uses LLM_PROVIDER (offline if no credentials)
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.chat.views import DEMO_QUESTIONS, KILLER_DEMO
from src import settings
from src.copilot.copilot import CFOCopilot

EXTRA = ["Which segment has the highest operating margin?", "What should the CFO investigate further?",
         "How does free cash flow compare with net income?", "What will revenue be next year?"]


def main() -> str:
    cp = CFOCopilot(session_id="demo-script")
    out = ["# Demo transcript", "",
           f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by `python -m scripts.run_demo` · provider: "
           f"{cp.provider.name} ({cp.provider.model}) · prompt {cp.prompt.ref}_", "",
           "Every answer below was produced by the running system: numbers come from the calculation engine, quotes from retrieval. "
           "With no LLM credentials the ANSWER paragraph is the deterministic narrative; with an LLM it is model prose that passed the "
           "numeric grounding check.", ""]
    sections = [("Part A - executive demo questions", DEMO_QUESTIONS), ("Part B - the 'killer demo' sequence", KILLER_DEMO),
                ("Part C - controls in action", EXTRA)]
    for title, qs in sections:
        out += [f"## {title}", ""]
        for i, q in enumerate(qs, 1):
            r = cp.ask(q)
            out += [f"### {i}. “{q}”", "", r.to_markdown().split("\n", 2)[2], f"_intent `{r.intent}` · audit id `{r.audit_id}`_", "", "---", ""]
    path = settings.PROJECT_ROOT / "docs" / "demo_transcript.md"
    path.write_text("\n".join(out))
    return str(path)


if __name__ == "__main__":
    print(main())
