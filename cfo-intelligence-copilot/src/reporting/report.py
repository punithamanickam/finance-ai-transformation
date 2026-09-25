"""Downloadable executive report (self-contained HTML, print-to-PDF ready)."""
from __future__ import annotations

import base64
import html
import io
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src import settings  # noqa: E402
from src.calculations.models import format_value  # noqa: E402
from src.copilot.evidence import BASIS_LABELS, Evidence  # noqa: E402
from src.reporting.brief import ExecutiveBrief, build_brief  # noqa: E402

PALETTE = ["#1f4e79", "#2e86ab", "#a23b72", "#f18f01", "#6c757d"]

CFO_QUESTIONS = [
    "Is the step-up in capital expenditure earning an adequate return, and over what horizon?",
    "How much of gross-margin compression is structural (AI infrastructure cost) versus mix or timing?",
    "What share of net income growth came from non-operating items, and is it repeatable?",
    "Which segments and offerings are funding growth, and where is operating leverage strongest?",
    "What is the free-cash-flow trajectory if capex intensity stays at the current level?",
    "Are the recast prior-year comparatives in the latest filing understood before trend conclusions are drawn?",
]


def _chart(series: dict[str, dict[int, float | None]], pct: bool = False, kind: str = "line") -> str:
    fig, ax = plt.subplots(figsize=(6.2, 2.8), dpi=150)
    years = sorted({y for s in series.values() for y in s})
    for i, (name, s) in enumerate(series.items()):
        ys = [s.get(y) for y in years]
        vals = [(v * 100 if pct else v / 1000) if v is not None else None for v in ys]
        if kind == "bar":
            w = 0.8 / len(series)
            ax.bar([x + i * w for x in range(len(years))], [v or 0 for v in vals], width=w, label=name, color=PALETTE[i % 5])
        else:
            ax.plot([str(y) for y in years], vals, marker="o", label=name, color=PALETTE[i % 5], linewidth=2)
    if kind == "bar":
        ax.set_xticks([x + 0.4 - 0.4 / len(series) for x in range(len(years))], [f"FY{y}" for y in years])
    ax.set_ylabel("%" if pct else "USD billions", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.18))
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _e(s) -> str:
    return html.escape(str(s))


def _evidence_html(ev: Evidence, include_table: bool = True) -> str:
    out = [f"<p class='answer'>{_e(ev.headline)}</p>"]
    if ev.disclaimer:
        out.append(f"<p class='disclaimer'>⚠ {_e(ev.disclaimer)}</p>")
    if include_table and ev.key_numbers:
        out.append("<table><tr><th>Metric</th><th>Current</th><th>Prior</th><th>Change</th></tr>")
        for k in ev.key_numbers[:10]:
            out.append(f"<tr><td>{_e(k.metric)}</td><td>{_e(k.current)} <span class='muted'>{_e(k.current_label)}</span></td>"
                       f"<td>{_e(k.prior)} <span class='muted'>{_e(k.prior_label)}</span></td><td>{_e(k.change)}</td></tr>")
        out.append("</table>")
    for basis, label in BASIS_LABELS.items():
        items = [s for s in ev.statements if s.basis == basis]
        if not items:
            continue
        out.append(f"<div class='basis basis-{basis}'><h4>{_e(label)}</h4><ul>")
        for s in items[:8]:
            cite = f" <span class='cite'>[{_e('; '.join(s.citations))}]</span>" if s.citations else ""
            out.append(f"<li>{_e(s.text)}{cite}</li>")
        out.append("</ul></div>")
    out.append(f"<p class='meta'>Confidence: <b>{ev.confidence}</b> · Basis: {_e(' / '.join(ev.basis))}</p>")
    return "\n".join(out)


def render_report(brief: ExecutiveBrief | None = None) -> str:
    b = brief or build_brief()
    fy, py = b.fiscal_year, b.prior_year
    kpi_html = "".join(
        f"<div class='kpi'><div class='kl'>{_e(k.label)}</div><div class='kv'>{_e(k.display)}</div>"
        f"<div class='kc {'good' if k.favourable else 'bad' if k.favourable is False else ''}'>"
        f"{'▲' if k.direction == 'up' else '▼' if k.direction == 'down' else '•'} {_e(k.change_display)} vs FY{py}</div>"
        f"<div class='ks'>{_e(k.source)}</div></div>" for k in b.kpis)
    charts = {
        "Revenue trend": _chart(b.trends["Revenue trend"], kind="bar"),
        "Margin trend": _chart(b.trends["Margin trend"], pct=True),
        "Cash-flow trend": _chart(b.trends["Cash-flow trend"], kind="bar"),
        "Investment trend": _chart(b.trends["Investment trend"], pct=True),
        "Segment revenue": _chart(b.trends["Segment revenue"], kind="bar"),
    }
    s = b.sections
    glance = "".join(f"<div class='glance'><h4>{_e(g['question'])}</h4><p>{_e(g['answer'])}</p>"
                     f"<p class='meta'>Confidence {g['confidence']} · {_e(g['basis'])}</p></div>" for g in b.at_a_glance)
    seg_rows = s["Segment analysis"].tables.get("segments", [])
    seg_tbl = "<table><tr><th>Segment</th><th>Revenue</th><th>Growth</th><th>Share of growth</th><th>Op. margin</th><th>Op. margin prior</th></tr>" + "".join(
        f"<tr><td>{_e(r['segment'])}</td><td>{format_value(r['revenue'], 'USD millions')}</td><td>{r['revenue_growth']:+.1%}</td>"
        f"<td>{r['contribution_to_growth']:.0%}</td><td>{r['operating_margin']:.1%}</td><td>{r['operating_margin_prior']:.1%}</td></tr>" for r in seg_rows) + "</table>"
    bs = s["What changed?"]
    from src.copilot.handlers import cash_position
    from src.copilot.intent import Intent
    from src.calculations.engine import CalculationEngine

    bal = cash_position(CalculationEngine(), Intent("cash_position", fiscal_year=fy, prior_year=py))
    # source appendix
    sources = {}
    for ev in list(s.values()) + [bal]:
        for src in ev.sources:
            sources[(src.document, str(src.page), src.detail)] = src
    appendix = "".join(f"<tr><td>{_e(v.document)}</td><td>{_e(v.section)}</td><td>{_e(v.page)}</td><td>{_e(v.detail)}</td>"
                       f"<td><a href='{_e(v.url)}'>SEC</a></td></tr>" for v in sorted(sources.values(), key=lambda x: (x.document, str(x.page))))
    sens = ""
    from src.calculations.scenario import ScenarioEngine

    rows = ScenarioEngine().sensitivity("operating_income")
    sens = "<table><tr><th>Assumption</th><th>Shock</th><th>Δ operating income (up)</th><th>Δ operating income (down)</th></tr>" + "".join(
        f"<tr><td>{_e(r['assumption'])}</td><td>{_e(r['shock'])}</td><td>{format_value(r['impact_up'], 'USD millions')}</td>"
        f"<td>{format_value(r['impact_down'], 'USD millions')}</td></tr>" for r in rows) + "</table>"
    generated = datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CFO Executive Report FY{fy}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{{--ink:#14213d;--muted:#6c757d;--line:#dee2e6;--accent:#1f4e79;--good:#2a9d8f;--bad:#c1121f;--bg:#ffffff;--panel:#f6f8fb}}
body{{font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);max-width:1040px;margin:0 auto;padding:32px 20px;line-height:1.45}}
h1{{font-size:28px;margin:0}} h2{{border-bottom:2px solid var(--accent);padding-bottom:4px;margin-top:40px;font-size:20px;color:var(--accent)}}
h3{{font-size:16px}} h4{{margin:10px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
.cover{{border-left:6px solid var(--accent);padding:8px 18px;margin-bottom:22px}} .muted,.meta{{color:var(--muted);font-size:12px}}
.banner{{background:var(--panel);border:1px solid var(--line);padding:10px 14px;font-size:12.5px;border-radius:6px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin:14px 0}}
.kpi{{border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--panel)}} .kl{{font-size:11px;color:var(--muted);text-transform:uppercase}}
.kv{{font-size:22px;font-weight:700}} .kc{{font-size:12px}} .kc.good{{color:var(--good)}} .kc.bad{{color:var(--bad)}} .ks{{font-size:10px;color:var(--muted);margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0}} th,td{{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left}} th{{background:var(--panel)}}
.answer{{font-size:15px;font-weight:500}} .disclaimer{{color:#9a6700;font-weight:600}} .cite{{color:var(--muted);font-size:11px}}
.basis{{border-left:3px solid var(--line);padding-left:10px;margin:8px 0}} .basis-management_commentary{{border-color:#f18f01}} .basis-possible_interpretation{{border-color:#a23b72}}
.basis-calculated_analysis{{border-color:#2e86ab}} .basis-factual_observation{{border-color:#1f4e79}}
.glance{{border:1px solid var(--line);border-radius:8px;padding:6px 14px;margin:8px 0}} .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
img{{max-width:100%;width:760px;display:block;margin:6px auto}} .principles{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;font-size:12px}} .principles div{{background:var(--panel);padding:8px;border-radius:6px}}
@media (max-width:720px){{.grid2,.principles{{grid-template-columns:1fr}}}}
@media print{{h2{{page-break-before:always}} .cover h2{{page-break-before:avoid}}}}
</style></head><body>
<div class="cover"><div class="muted">CFO Intelligence Copilot · Executive report</div><h1>Microsoft Corporation - FY{fy} Financial Review</h1>
<div class="muted">Fiscal year ended June 30, {fy} vs FY{py} · Generated {generated} · Calculation engine v{settings.CALC_ENGINE_VERSION}</div></div>
<p class="banner"><b>Independent portfolio proof-of-concept.</b> Not affiliated with, endorsed by, or representing Microsoft or any other company. Built only from public SEC filings
(see Source Appendix). Numbers are extracted from filings and calculated by deterministic code; narrative is constrained to that evidence. Interpretations are labelled as such. Not investment advice.</p>
<div class="principles"><div><b>AI retrieves and explains</b></div><div><b>Deterministic code calculates</b></div><div><b>Financial data is the source of truth</b></div><div><b>Humans retain decision authority</b></div><div><b>Every material answer is traceable</b></div></div>

<h2>1. Executive Summary - financial performance at a glance</h2>
<div class="kpis">{kpi_html}</div>
{glance}

<h2>2. Financial Performance</h2>
<img src="{charts['Revenue trend']}" alt="Revenue trend">
{_evidence_html(s['What changed?'])}

<h2>3. Profitability</h2>
<img src="{charts['Margin trend']}" alt="Margin trend">
{_evidence_html(s['Why did it change?'])}

<h2>4. Cash Flow</h2>
<img src="{charts['Cash-flow trend']}" alt="Cash flow trend">
{_evidence_html(s['Cash flow'])}

<h2>5. Balance Sheet</h2>
{_evidence_html(bal)}

<h2>6. Segment Analysis</h2>
<img src="{charts['Segment revenue']}" alt="Segment revenue">
{seg_tbl}
{_evidence_html(s['Segment analysis'], include_table=False)}

<h2>7. Investment</h2>
<img src="{charts['Investment trend']}" alt="Investment trend">
{_evidence_html(s['Where is management investing?'])}

<h2>8. Risks</h2>
{_evidence_html(s['What financial risks are visible?'])}
<h3>Areas requiring CFO attention</h3>
{_evidence_html(s['What requires CFO attention?'], include_table=False)}

<h2>9. Scenario Analysis</h2>
{_evidence_html(s['Scenario: revenue growth −5 pp'])}
<h3>Sensitivity of illustrative operating income</h3>{sens}
<p class="disclaimer">Illustrative scenario — not management guidance. Base case carries forward FY{fy} actual ratios; it is not a forecast.</p>

<h2>10. CFO Questions</h2>
<ol>{''.join(f'<li>{_e(q)}</li>' for q in CFO_QUESTIONS)}</ol>
<p class="meta">Questions are generated from the attention rules and are prompts for management discussion, not conclusions.</p>

<h2>11. Source Appendix</h2>
<table><tr><th>Document</th><th>Section</th><th>Page</th><th>Item</th><th>Link</th></tr>{appendix}</table>
<p class="meta">Full provenance (table, row, column, XBRL concept and fact id) for every figure: data/processed/financial_facts.csv. Data-quality results: docs/data_quality_report.md.</p>
</body></html>"""


def write_report(path=None) -> str:
    path = path or (settings.REPORTS_DIR / "CFO_Executive_Report.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(), encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    print(write_report())
