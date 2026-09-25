# Finance AI Transformation

Portfolio of independent proof-of-concept projects on applying AI to finance: governed, traceable and built on public
data.

| Project | Summary |
|---|---|
| [**CFO Intelligence Copilot**](cfo-intelligence-copilot/README.md) | Executive financial-intelligence layer over Microsoft's public FY2026 Form 10-K. It combines an iXBRL-extracted financial data model, a deterministic calculation engine (variance, driver trees, scenarios), period-aware RAG over management commentary, and an LLM narrative constrained by a numeric grounding validator, with a full audit trail. Streamlit UI, FastAPI and a consulting-style executive report. |
| [**AI Value Command Centre**](ai-value-command-centre/README.md) | "Are we actually getting value from AI?" A CFO platform for an enterprise AI portfolio built on HPE portfolio categories: investment, cost intelligence, benefit realisation (realised / validated / hypothetical), ROI movement, confidence scoring, scenarios, a multi-agent CFO copilot with a safe natural-language query layer, RAG over cited public HPE filings, and an evidence and audit trail. Includes a [deep-dive analysis](ai-value-command-centre/docs/deep_dive_analysis.md) of HPE's public AI business. Public HPE data plus clearly labelled synthetic enterprise data. |

All projects use only publicly available information, plus clearly labelled synthetic data where a project says so, and
aren't affiliated with any company whose public data they analyse.
