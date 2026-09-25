# Demo script (15–20 minutes)

Audience: CFO, CIO/CTO, Chief Transformation Officer, finance transformation and enterprise AI leaders.
Setup: `make data && make app` (or `streamlit run app/streamlit_app.py`). A full, machine-generated transcript of every
question below is in [`demo_transcript.md`](demo_transcript.md), regenerated with `python -m scripts.run_demo`.

Figures quoted here are from Microsoft's FY2026 Form 10-K as extracted by the system. Regenerate the transcript if the
data is rebuilt.

---

## 0. Framing (1 min)

> "Finance leaders don't lack data - they lack time to find, reconcile and interpret it. This isn't a PDF chatbot. The
> numbers come from the filing's XBRL tags, the maths is Python, and the language model is only allowed to explain
> evidence it's handed. Watch the sidebar: *AI retrieves and explains; deterministic code calculates.*"

Point at the principles panel in the sidebar and the "independent proof-of-concept" disclaimer.

## 1. Executive dashboard (2 min) - *Executive dashboard*

* Twelve KPI cards, each with a trend line and **the filing page it came from** (e.g. revenue $331.8B, +17.8%, p.50).
* Click **📘 CFO Executive Brief** to get the snapshot, trends, segment analysis, management commentary and attention areas.
* Click **Download executive report** to get the consulting-style HTML report (print to PDF).

## 2. Ten executive questions (6 min) - *CFO Copilot*, sidebar "Demo questions"

| # | Question | What to point out |
|---|---|---|
| 1 | What changed in the company's financial performance? | Top-3 moves ranked by a *stated* rule (abs % change): capex +79.6%, OCF +34.4%, EPS +31.6% |
| 2 | Why did operating margin change? | Exact identity: gross margin % −0.9 pp, opex leverage +2.0 pp → OM +1.2 pp to 46.8%. Segment GM view shows Intelligent Cloud −4.2 pp |
| 3 | Which segment drove revenue growth? | Intelligent Cloud: $31.5B = 63% of the $50.1B increase. Drill-down to offerings, with the unreconciled residual shown |
| 4 | How did free cash flow change? | OCF +$46.8B but capex +$51.4B → FCF −$4.6B to $67.0B; 63% of OCF reinvested |
| 5 | What are the biggest expense movements? | Service cost of revenue +$19.9B dominates; opex grew slower than revenue (+7.4% vs +17.8%) |
| 6 | How much is the company investing in R&D? | $35.6B, +9.5%, falling as a share of revenue (11.5% → 10.7%), plus management's stated reason, quoted |
| 7 | How has capex changed? | Capex intensity 22.9% → 34.9% of revenue |
| 8 | What are the main financial risks disclosed by management? | Risk-factor quotes (management commentary) kept **separate** from calculated indicators |
| 9 | Show me the evidence behind this conclusion. | Follow-up uses conversation context: document, section, page, URL for every number |
| 10 | Run a scenario where revenue growth is 5 percentage points lower. | Disclaimer first; illustrative OI −$11.3B (−5.9%) vs base case |

For each answer, show the four evidence types (📄 factual · 🧮 calculated · 💭 interpretation · 🗣️ management), then
**CONFIDENCE** and **BASIS**, then open *Calculations* to see formula, inputs, page and engine version.

## 3. The "killer demo" (5 min) - sidebar "Killer demo (run in order)"

1. *"Revenue increased significantly, but operating margin moved differently. Explain the bridge between revenue growth
   and operating-income growth, identify the major cost drivers, distinguish management's stated explanations from your
   own calculated analysis, and show me the source for every number."*
   → Revenue +17.8%, OI +20.8%, operating leverage 1.17x. The bridge is gross-profit volume +$34.5B, gross-margin rate
   −$2.9B, R&D −$3.1B, S&M −$1.1B, G&A −$0.7B, and it **reconciles to the dollar**. MD&A quotes are listed separately.
2. *"Now assume revenue growth is 5 percentage points lower next year while gross margin remains constant. What is the
   illustrative impact on operating income?"* → parsed as a −5 pp shock with GM held; OI −$11.3B.
3. *"Which assumptions have the greatest sensitivity?"* → gross margin (±1 pp ≈ $3.9B of OI) outranks revenue growth
   (±1 pp ≈ $2.3B). Show the tornado in *Scenario lab*.
4. *"Show me exactly how you calculated that."* → every formula, every input with its page, the method and the
   assumption sources.

## 4. Controls in action (2 min)

* *"What will revenue be next year?"* → refused; offers a scenario instead (no forecasts are ever generated).
* *"What is the airspeed of a swallow?"* → *"I could not find sufficient evidence in the available public filings."*
* *AI governance & audit* view → model card, versioned prompt, and a step-by-step audit record of the last question
  (intent rule → sources → calculations → prompt → response → validation → answer hash).
* *Statements & evidence* → *Data quality*: 84/84 checks pass. The **restatement** the system found (FY2024/FY2025 D&A
  recast between filings) is flagged for review.

## 5. Enterprise extension (1 min) - *Enterprise extension*

> "The same layers - governed data, a deterministic metric layer, retrieval, a constrained LLM and an audit trail - are
> exactly what an internal CFO platform needs. Swap SEC filings for ERP, data warehouse, cloud cost and AI-workload
> telemetry, and the copilot becomes an enterprise CFO intelligence platform."

Close with [`enterprise-roadmap.md`](enterprise-roadmap.md).
