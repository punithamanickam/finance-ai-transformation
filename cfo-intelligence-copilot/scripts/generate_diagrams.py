"""Render the architecture diagrams in /architecture (PNG) from code, so they stay versioned and reproducible.

    python -m scripts.generate_diagrams
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from src import settings  # noqa: E402
from src.calculations.engine import METRICS  # noqa: E402

INK, MUTED, LINE = "#14213d", "#52514e", "#b8b7b0"
FILL = {"data": "#e8f1fb", "compute": "#e6f6ef", "ai": "#fdeee6", "gov": "#f1eefb", "ui": "#fff6df", "src": "#f2f2f0"}
EDGE = {"data": "#2a78d6", "compute": "#1baf7a", "ai": "#eb6834", "gov": "#4a3aa7", "ui": "#c98500", "src": "#8a8985"}
OUT = settings.PROJECT_ROOT / "architecture"


def box(ax, x, y, w, h, title, sub="", kind="data"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=FILL[kind], ec=EDGE[kind], lw=1.6))
    ax.text(x + w / 2, y + h * (0.62 if sub else 0.5), title, ha="center", va="center", fontsize=10.5, fontweight="bold", color=INK)
    if sub:
        ax.text(x + w / 2, y + h * 0.3, sub, ha="center", va="center", fontsize=7.6, color=MUTED, wrap=True)
    return (x, y, w, h)


def arrow(ax, a, b, label="", side="bottom-top", color=LINE):
    ax_, ay, aw, ah = a
    bx, by, bw, bh = b
    if side == "bottom-top":
        p, q = (ax_ + aw / 2, ay), (bx + bw / 2, by + bh)
    elif side == "right-left":
        p, q = (ax_ + aw, ay + ah / 2), (bx, by + bh / 2)
    else:
        p, q = (ax_ + aw / 2, ay + ah), (bx + bw / 2, by)
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=12, lw=1.4, color=color, shrinkA=2, shrinkB=2))
    if label:
        ax.text((p[0] + q[0]) / 2 + 0.08, (p[1] + q[1]) / 2, label, fontsize=7, color=MUTED, va="center")


def canvas(w, h, title, subtitle):
    fig, ax = plt.subplots(figsize=(w, h), dpi=160)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    ax.text(0.3, h - 0.35, title, fontsize=15, fontweight="bold", color=INK, va="top")
    ax.text(0.3, h - 0.78, subtitle, fontsize=8.5, color=MUTED, va="top")
    return fig, ax


def system_architecture():
    fig, ax = canvas(12, 11, "CFO Intelligence Copilot - system architecture",
                     "Numbers flow through deterministic code; the LLM only explains evidence it is given. Every layer writes to the audit trail.")
    pf = box(ax, 2.75, 9.0, 6.5, 0.9, "PUBLIC FILINGS", "SEC EDGAR: 10-K (iXBRL) FY2026 & FY2025 · 8-K earnings release · source registry", "src")
    ing = box(ax, 3.5, 7.8, 5, 0.8, "DOCUMENT INGESTION", "sec_client · retrieval date & URL recorded · raw files not redistributed", "data")
    par = box(ax, 3.5, 6.6, 5, 0.8, "DOCUMENT PARSING", "pages · 10-K Items · headings · tables · rows · columns", "data")
    st_ = box(ax, 0.6, 5.1, 4.8, 1.0, "STRUCTURED DATA", "iXBRL facts → normalised model (SQLite)\nprovenance: doc/page/table/row/column/concept", "data")
    rag = box(ax, 6.6, 5.1, 4.8, 1.0, "RAG CORPUS", "narrative chunks: MD&A · risk factors · notes\nmanagement commentary tagged by type", "data")
    calc = box(ax, 0.6, 3.7, 4.8, 1.0, "CALCULATION ENGINE", f"{len(METRICS)} metric definitions · variance · CAGR · driver trees\nscenario & sensitivity · data-quality checks", "compute")
    sem = box(ax, 6.6, 3.7, 4.8, 1.0, "SEMANTIC RETRIEVAL", "TF-IDF cosine (pluggable: FAISS / pgvector)\nfiltered by filing period & content type", "compute")
    ai = box(ax, 2.5, 2.3, 7, 0.95, "CFO AI LAYER", "intent → metrics → evidence pack → LLM narrative (swappable model) → numeric grounding validator", "ai")
    d = box(ax, 0.6, 0.95, 3.3, 0.85, "Executive dashboard", "KPIs · trends · CFO brief · report", "ui")
    c = box(ax, 4.35, 0.95, 3.3, 0.85, "CFO Copilot", "ANSWER · KEY NUMBERS · DRIVERS · SOURCE", "ui")
    s = box(ax, 8.1, 0.95, 3.3, 0.85, "Scenario engine", "illustrative - not guidance", "ui")
    audit = box(ax, 0.6, 0.1, 10.8, 0.6, "SOURCE / AUDIT LAYER", "citations · formulas & inputs · prompt version · model · validation result · append-only audit log", "gov")
    arrow(ax, pf, ing); arrow(ax, ing, par)
    arrow(ax, par, st_, "iXBRL tags"); arrow(ax, par, rag, "narrative text")
    arrow(ax, st_, calc); arrow(ax, rag, sem)
    arrow(ax, calc, ai, "calculated metrics"); arrow(ax, sem, ai, "quoted evidence")
    arrow(ax, ai, d); arrow(ax, ai, c); arrow(ax, ai, s)
    fig.savefig(OUT / "system_architecture.png", bbox_inches="tight")
    plt.close(fig)


def data_flow():
    fig, ax = canvas(13, 4.6, "Numerical question data flow", "The LLM never calculates. It receives only validated numbers and may use nothing else.")
    steps = [("User question", "“Why did operating\nmargin change?”", "ui"), ("Intent detection", "rules → margin_drivers", "ai"),
             ("Metric identification", "GM%, R&D%, S&M%,\nG&A%, OM%", "ai"), ("Structured data", "SQLite facts\n+ page refs", "data"),
             ("Python calculation", "Δ OM = ΔGM% − ΔOpex%\n(identity)", "compute"), ("Validation", "reconciles · no conflicts\n· inputs present", "gov"),
             ("LLM explanation", "evidence pack only\nnumeric grounding check", "ai"), ("Source citation", "doc · section · page\n· URL · confidence", "gov")]
    prev = None
    for i, (t, s, k) in enumerate(steps):
        x = 0.3 + (i % 4) * 3.15
        y = 2.3 if i < 4 else 0.4
        b = box(ax, x, y, 2.7, 1.3, t, s, k)
        if prev:
            arrow(ax, prev, b, side="right-left" if i != 4 else "bottom-top")
        prev = b
    fig.savefig(OUT / "data_flow.png", bbox_inches="tight")
    plt.close(fig)


def governance_flow():
    fig, ax = canvas(13, 4.8, "Governance & audit flow", "Each interaction is logged end-to-end with a SHA-256 of the final answer. Humans retain decision authority.")
    steps = [("User question", "timestamp · session", "ui"), ("Retrieved sources", "chunk ids · scores", "data"),
             ("Metrics selected", "intent rule · fiscal years", "ai"), ("Calculation", "formula · inputs · engine v", "compute"),
             ("LLM prompt", "prompt name@version#hash", "ai"), ("LLM response", "model · usage · stop reason", "ai"),
             ("Validation", "unsupported numbers →\ndeterministic fallback", "gov"), ("Final answer", "confidence · basis\n· sha256", "gov")]
    prev = None
    for i, (t, s, k) in enumerate(steps):
        x = 0.3 + (i % 4) * 3.15
        y = 2.4 if i < 4 else 0.4
        b = box(ax, x, y, 2.7, 1.25, t, s, k)
        if prev:
            arrow(ax, prev, b, side="right-left" if i != 4 else "bottom-top")
        prev = b
    fig.savefig(OUT / "governance_flow.png", bbox_inches="tight")
    plt.close(fig)


def enterprise_extension():
    fig, ax = canvas(13, 8.6, "Enterprise extension (conceptual)",
                     "Same layers, enterprise sources. Illustrative target state - not a description of any specific company's systems.")
    srcs = ["ERP / GL", "Data warehouse", "Cloud infrastructure\ncost & usage", "Business applications\n(CRM, billing)", "Operational telemetry",
            "AI workloads\n(GPU hours, tokens)", "Finance systems\n(FP&A, consolidation)"]
    bs = [box(ax, 0.3 + i * 1.8, 6.2, 1.6, 1.0, s, "", "src") for i, s in enumerate(srcs)]
    ed = box(ax, 0.3, 4.9, 12.4, 0.8, "ENTERPRISE DATA", "governed data products · semantic layer · master data (entity, segment, product, cost centre) · lineage", "data")
    fi = box(ax, 0.3, 3.6, 12.4, 0.8, "FINANCE INTELLIGENCE", "metric catalogue · driver trees (unit economics, cost-to-serve, AI ROI) · variance & rolling forecast models · retrieval over policies & commentary", "compute")
    gv = box(ax, 0.3, 2.3, 12.4, 0.8, "AI GOVERNANCE", "model registry · prompt versioning · numeric grounding · access control (RLS) · SOX-aligned audit trail · human sign-off workflow", "gov")
    ex = box(ax, 0.3, 1.0, 12.4, 0.8, "EXECUTIVE DECISION LAYER", "CFO copilot in Teams/Slack · board pack generator · scenario & capital-allocation workspace · alerts on attention rules", "ui")
    for b in bs:
        arrow(ax, b, ed)
    arrow(ax, ed, fi); arrow(ax, fi, gv); arrow(ax, gv, ex)
    ax.text(0.3, 0.45, "Evolution: Financial Statement Copilot (public filings)  →  Enterprise CFO Intelligence Platform (internal, governed, real-time data)",
            fontsize=9, color=INK, fontweight="bold")
    fig.savefig(OUT / "enterprise_extension.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    system_architecture()
    data_flow()
    governance_flow()
    enterprise_extension()
    print("diagrams written to", OUT)
