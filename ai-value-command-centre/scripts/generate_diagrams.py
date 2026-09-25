"""Render the architecture and data-model diagrams to architecture/*.png.

    python -m scripts.generate_diagrams
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from src import settings  # noqa: E402

INK, MUTED, LINE = "#111a19", "#5b6664", "#c5ccca"
FILL = {"user": "#e4edf9", "app": "#ffffff", "ai": "#efeafb", "engine": "#e6f5e6", "data": "#fdf3dc", "public": "#e3f3f0", "trust": "#fbe9e9"}
EDGE = {"user": "#1c5cab", "app": "#677371", "ai": "#6a4bc4", "engine": "#067a06", "data": "#8a5a00", "public": "#0f7a6b", "trust": "#b02a2a"}


def box(ax, x, y, w, h, title, sub="", kind="app"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=FILL[kind], ec=EDGE[kind], lw=1.4))
    ax.text(x + w / 2, y + h / 2 + (0.12 if sub else 0), title, ha="center", va="center", fontsize=10.5, color=INK, fontweight="bold")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.2, sub, ha="center", va="center", fontsize=7.8, color=MUTED, wrap=True)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.2))


def architecture(path):
    fig, ax = plt.subplots(figsize=(13, 11))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 11.4)
    ax.axis("off")
    ax.text(0.2, 11.05, "AI Value Command Centre: system architecture", fontsize=15, fontweight="bold", color=INK)
    ax.text(0.2, 10.7, "AI retrieves and explains; deterministic engines calculate; every answer is traceable to source data", fontsize=9.5, color=MUTED)
    box(ax, 5, 9.7, 3, 0.7, "CFO", "CEO · CIO · FP&A · BU leaders", "user")
    box(ax, 3.2, 8.5, 6.6, 0.8, "Web application", "Command Center · Portfolio · Value & ROI · Costs · Benefits · Risk · Scenarios · Evidence · Report", "app")
    box(ax, 3.2, 7.4, 6.6, 0.8, "FastAPI + security", "bearer tokens · RBAC (CFO / Finance / BU) · input validation · audit logging", "app")
    box(ax, 4.2, 6.3, 4.6, 0.8, "AI CFO Copilot", "intent routing · structured answers · optional LLM narrative", "ai")
    box(ax, 1.2, 5.1, 10.6, 0.85, "Agent / orchestration layer", "Finance Analyst · Portfolio Analyst · Benefits · Scenario · Research/RAG · Executive Reporting agents", "ai")
    for i, (t, s) in enumerate([("Finance engine", "ROI · NPV · IRR · payback · variance"),
                                ("Portfolio engine", "KPIs · value bridge · risk rules"),
                                ("Scenario engine", "levers · sensitivity · JS parity"),
                                ("RAG engine", "TF-IDF + metadata filters · citations")]):
        box(ax, 0.4 + i * 3.1, 3.75, 2.9, 0.95, t, s, "engine")
    box(ax, 0.4, 2.35, 2.9, 0.95, "Semantic query layer", "NL → whitelisted spec → read-only SQL", "engine")
    for i, (t, s) in enumerate([("Financial data", "costs · budgets · P&L"), ("AI portfolio data", "initiatives · risks"),
                                ("Usage data", "AI usage · GPU hours"), ("Benefits data", "benefits · evidence")]):
        box(ax, 3.5 + i * 2.35, 2.35, 2.2, 0.95, t, s + "\nSYNTHETIC", "data")
    box(ax, 3.5, 1.15, 9.25, 0.8, "Public HPE documents & filings", "10-K / 10-Q / 8-K releases · earnings calls · product announcements · cited source registry · PUBLIC", "public")
    box(ax, 0.4, 0.1, 12.35, 0.75, "Evidence / audit layer", "evidence records (formula, components, datasets, SQL, assumptions) · confidence basis · append-only audit log with response SHA-256", "trust")
    for x1, y1, x2, y2 in [(6.5, 9.7, 6.5, 9.3), (6.5, 8.5, 6.5, 8.2), (6.5, 7.4, 6.5, 7.1), (6.5, 6.3, 6.5, 5.95)]:
        arrow(ax, x1, y1, x2, y2)
    for i in range(4):
        arrow(ax, 1.85 + i * 3.1, 5.1, 1.85 + i * 3.1, 4.7)
    arrow(ax, 1.85, 3.75, 1.85, 3.3)
    for i in range(4):
        arrow(ax, 4.6 + i * 2.35, 3.75, 4.6 + i * 2.35, 3.3)
    arrow(ax, 10.15, 3.75, 10.15, 1.95)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def data_model(path):
    groups = [
        ("Organisation", "data", ["companies", "business_units", "cost_centres", "users"]),
        ("Portfolio", "data", ["ai_initiatives", "milestones", "investment_transactions", "risks", "assumptions"]),
        ("Financial", "data", ["cost_transactions", "budgets", "forecasts", "financials", "vendors"]),
        ("Usage", "data", ["ai_usage", "infrastructure_usage"]),
        ("Benefits", "data", ["benefits", "benefit_monthly", "benefit_evidence"]),
        ("Public HPE", "public", ["hpe_sources", "hpe_products", "hpe_financials", "documents"]),
        ("Semantic views", "engine", ["ai_initiative_metrics", "benefit_line_metrics", "risk_register", "cost_by_category"]),
        ("Governance", "trust", ["audit_log"]),
    ]
    fig, ax = plt.subplots(figsize=(13, 6.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6.4)
    ax.axis("off")
    ax.text(0.2, 6.1, "Data model: 24 tables + 4 materialised semantic views", fontsize=14, fontweight="bold", color=INK)
    ax.text(0.2, 5.78, "Key: initiative_id links portfolio, financial, usage and benefit tables; bu_id drives role-based scope; source_id cites public data",
            fontsize=9, color=MUTED)
    for i, (g, kind, tables) in enumerate(groups):
        x, y = 0.2 + (i % 4) * 3.2, 3.0 if i < 4 else 0.2
        h = 0.45 + 0.42 * len(tables)
        ax.add_patch(FancyBboxPatch((x, y + 2.5 - h), 3.0, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=FILL[kind], ec=EDGE[kind], lw=1.3))
        ax.text(x + 0.15, y + 2.5 - 0.28, g, fontsize=10.5, fontweight="bold", color=INK, va="center")
        for j, tname in enumerate(tables):
            ax.text(x + 0.25, y + 2.5 - 0.7 - j * 0.42, tname, fontsize=9, family="monospace", color=INK, va="center")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    out = settings.PROJECT_ROOT / "architecture"
    out.mkdir(exist_ok=True)
    architecture(out / "system_architecture.png")
    data_model(out / "data_model.png")
    print("wrote", out)
