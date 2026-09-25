# Trust layer, governance and security

## Principles

1. **Deterministic code calculates.** Every number comes from `src/finance/formulas.py` or an aggregation of the database.
2. **AI retrieves and explains.** Retrieval supplies cited public text; an optional LLM only rewrites narrative.
3. **Actuals and assumptions stay apart.** Every number in a copilot answer carries a basis: actual, validated, calculated,
   assumption, forecast or public. Assumptions are listed separately with source and review date.
4. **Every important answer is traceable.** Headline figures have evidence records; copilot answers are audit-logged.
5. **People decide.** Reports use advisory language ("Management may wish to investigate…").

## Evidence records

`GET /evidence/{id}` (and the **Explain** button) returns, for ids such as `kpi.expected_value`, `initiative.AI-003`,
`benefit.AI-010-B1`, `confidence.AI-001-B1`, `cost.gpu`, `unit.ai_cost_per_employee`, `analysis.roi_movement`:

* label, value, unit, formula;
* components (each linking to its own evidence record);
* data sources: table, row count and filter;
* a reproducible SQL query;
* assumption ids expanded to description, value, source and review date;
* notes and the confidence basis; engine version and as-of date.

## Data lineage

Public sources and synthetic transactions → relational tables → deterministic engines → evidence record → copilot answer →
audit log. Public rows keep `source_id → url, date`; synthetic rows keep `data_label = 'SYNTHETIC'`.

## LLM controls (`src/copilot/llm.py`)

* Optional. Without a key the copilot runs offline with deterministic narrative.
* The LLM sees only the numbers pack (labels, displayed values, key drivers), with a versioned system prompt.
* **Numeric grounding validator:** every number in the LLM's text must appear in the pack. Any unsupported number and the
  rewrite is discarded; the audit record stores the provider, prompt version and the rejected numbers.
* Research answers about HPE are never rewritten and are never answered from model memory: with no retrieved evidence the
  agent says so.

## Audit log

Table `audit_log`: timestamp, user, role, action (`auth.login`, `auth.failed`, `copilot.query`, `query.run`,
`query.refused`, `scenario.run`, `report.cfo`), JSON detail (question, intent, agent, scope, evidence ids, SQL, LLM use)
and the SHA-256 of the response. The same question on the same data produces the same hash (tested).

## Security controls

| Control | Implementation |
|---|---|
| Authentication | PBKDF2-HMAC-SHA256 password hashes (200,000 iterations, per-user salt); HMAC-SHA256 signed bearer tokens with expiry |
| Role-based access | CFO: all data + audit log; FINANCE: whole portfolio; BU: own business unit only, applied in the data repository and as a mandatory `bu_id` filter in SQL |
| Protected endpoints | Every data endpoint requires a valid token; permissions checked per route |
| No arbitrary SQL | The semantic layer maps words to a whitelist of entities, fields and operators; values are bound parameters; rendered SQL is re-validated (single SELECT, allowed views only, no DDL/DML/UNION/comments); SQLite runs with `PRAGMA query_only` |
| Input validation | Pydantic models with length limits; scenario levers bounded; id formats checked by regex; questions over 500 characters rejected |
| Secrets | `AVCC_SECRET_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL` from environment / `.env` (git-ignored); `.env.example` has no values; the dev signing key is random per process |
| Refusals | SQL fragments and destructive requests are refused before routing and logged |

Tests: `tests/test_query_safety.py`, `tests/test_api.py`, `tests/test_copilot.py`.

## Known limitations

* Local demo passwords are for a prototype; production should use the corporate identity provider (OIDC/SAML).
* No rate limiting or CSRF protection (the API uses bearer tokens, not cookies).
* Intent routing is rule-based: robust for the question library, less flexible than an LLM router for novel phrasing.
