"""Export a self-contained static snapshot of the web app (CFO view).

    python -m scripts.export_static            # -> web/dist/ai-value-command-centre.html

The snapshot embeds the same API payloads the live app uses, the evidence records, pre-computed copilot answers to
the demo questions, and the browser port of the scenario engine, so the page works with no server.
"""
from __future__ import annotations

import json
import re
from datetime import date

from src import settings
from src.agents.orchestrator import ask, context_for
from src.api import payloads
from src.api.serialize import jsonable
from src.reporting.briefing import build_briefing
from src.security.auth import Principal

QUESTIONS = [
    "How much have we invested in AI?", "Where is the AI money going?", "How much value has actually been realised?",
    "Why is realised value below expected value?", "Why did AI ROI decline this quarter?", "Explain the biggest ROI movement.",
    "Which initiatives have the largest budget variance?", "Show initiatives with significant budget variance.",
    "Which projects have benefits below plan?", "What is driving AI cost growth?",
    "Show me all AI initiatives with more than $5M investment.", "Which benefits rely heavily on assumptions?",
    "Which benefits are based mainly on assumptions?", "What percentage of AI value is actually reflected in the P&L?",
    "Explain the $49.5M expected benefit.", "What happens if infrastructure utilisation increases from 63% to 80%?",
    "What happens if utilisation increases to 80%?", "What if we invest an additional $10M?",
    "Which variables have the greatest impact on AI value?", "Prepare a CFO briefing for the board.",
    "Prepare a board-level AI investment briefing.", "Which business units have the highest AI spend?",
    "Are we actually getting value from AI?", "Which initiatives are at risk?", "How confident are we in the cost savings?",
    "What is our AI cost per employee?", "Tell me about Supply Chain AI Optimisation", "Tell me about AI Revenue Intelligence",
    "Tell me about Enterprise Knowledge Copilot", "What is HPE Private Cloud AI?", "What is HPE's AI backlog?",
    "What was HPE revenue in FY2025?", "How many GreenLake customers does HPE have?", "When did HPE close the Juniper acquisition?",
    "How are our initiatives mapped to HPE categories?",
]


def build_snapshot() -> dict:
    ctx = context_for(None)
    p = ctx.portfolio
    principal = Principal("snapshot@meridian.example", "CFO")
    snap = {
        "generated": date.today().isoformat(), "user": {"user_id": principal.user_id, "display_name": "Group CFO (static snapshot)", "role": "CFO"},
        "dashboard": payloads.dashboard(ctx), "portfolio": payloads.portfolio(ctx), "investment": payloads.investment(ctx),
        "costs": payloads.costs(ctx), "benefits": payloads.benefits(ctx), "roi": payloads.roi(ctx), "risks": payloads.risks(ctx),
        "sources": payloads.sources(ctx), "scenario": payloads.scenario_meta(ctx), "assumptions": payloads.assumptions(ctx),
        "initiatives": {i: payloads.initiative(ctx, i) for i in ctx.table.initiative_id},
        "report": jsonable(build_briefing(ctx)),
    }
    snap["copilot"] = [{"question": q, "response": jsonable(ask(q, principal, use_llm=False))} for q in QUESTIONS]
    # register every evidence record the pages can link to
    ctx.benefits.register_evidence()
    ctx.costs.register_evidence()
    p.get_evidence("kpi.total_investment")
    snap["evidence"] = {k: payloads.evidence(ctx, k) for k in list(p.evidence)}
    from src.governance import audit

    snap["audit"] = jsonable(audit.read(40))
    return snap


def render(snapshot: dict, full_document: bool = True) -> str:
    web = settings.WEB_DIR
    css = (web / "styles.css").read_text()
    js = (web / "scenario.js").read_text() + "\n" + (web / "app.js").read_text()
    data = json.dumps(snapshot, separators=(",", ":")).replace("</", "<\\/")
    fonts = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
             '&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">')
    plotly = '<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.0/plotly.min.js"></script>'
    body = (f"<title>AI Value Command Centre</title>\n{fonts}\n<style>\n{css}\n</style>\n{plotly}\n"
            f"<div id=\"app\"></div>\n<script>window.AVCC_SNAPSHOT={data};</script>\n<script>\n{js}\n</script>\n")
    if not full_document:
        return body
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + re.sub(r"<div id=\"app\"></div>[\s\S]*$", "", body) + "</head>\n<body>\n"
            + body[body.index('<div id="app">'):] + "</body>\n</html>\n")


def main() -> None:
    snap = build_snapshot()
    out = settings.WEB_DIR / "dist"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ai-value-command-centre.html").write_text(render(snap))
    print(f"wrote {out / 'ai-value-command-centre.html'} ({(out / 'ai-value-command-centre.html').stat().st_size / 1e6:.1f} MB),"
          f" {len(snap['evidence'])} evidence records, {len(snap['copilot'])} copilot answers")


if __name__ == "__main__":
    main()
