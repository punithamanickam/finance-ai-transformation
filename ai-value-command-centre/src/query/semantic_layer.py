"""Controlled natural-language-to-data layer.

The user's words never reach the database. The parser extracts a structured `QuerySpec` (entity, filters, sort,
limit) using a whitelist of entities, fields and operators; the renderer turns the spec into a parameterised,
read-only SELECT against a documented semantic view. Anything outside the whitelist is ignored or refused.

Safety controls
1. Identifiers (tables, columns, sort keys) come only from SEMANTIC_MODEL; values are bound parameters.
2. The renderer can only emit SELECT ... FROM <view> [WHERE ...] [ORDER BY ...] LIMIT n (n <= 100).
3. `validate_sql` re-checks the rendered SQL (single statement, SELECT only, no DDL/DML keywords, known view).
4. SQLite connections run with PRAGMA query_only; BU-scoped users always get an extra bu_id filter.
5. Questions that contain SQL or destructive intent are refused before parsing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

SEMANTIC_MODEL = {
    "initiatives": {
        "view": "ai_initiative_metrics",
        "label": "AI initiatives",
        "default_fields": ["initiative_id", "name", "business_unit", "geography", "hpe_category", "status", "investment",
                           "budget", "budget_variance_pct", "expected_value", "realised_value", "benefit_realisation",
                           "realised_roi", "confidence", "rag"],
        "fields": {
            "initiative_id": "text", "name": "text", "business_unit": "text", "bu_id": "text", "geography": "text",
            "hpe_category": "text", "status": "text", "rag": "text", "investment": "money", "budget": "money",
            "budget_variance": "money", "budget_variance_pct": "pct", "forecast_spend": "money",
            "expected_value": "money", "realised_value": "money", "validated_value": "money", "hypothetical_value": "money",
            "benefit_realisation": "pct", "realised_roi": "pct", "expected_roi": "pct", "confidence": "number",
            "adoption_rate": "pct", "active_users": "number", "cloud_consumption": "money", "infrastructure_cost": "money",
            "npv_3yr": "money", "payback_months": "number", "risk_exposure": "money", "open_risks": "number",
        },
        "default_sort": ("investment", "DESC"),
    },
    "benefits": {
        "view": "benefit_line_metrics",
        "label": "benefit lines",
        "default_fields": ["benefit_id", "initiative_id", "initiative_name", "benefit_type", "description", "business_case",
                           "realised", "validated", "gap", "realisation", "confidence", "methodology"],
        "fields": {"benefit_id": "text", "initiative_id": "text", "initiative_name": "text", "bu_id": "text", "benefit_type": "text",
                   "description": "text", "business_case": "money", "owner_forecast": "money", "realised": "money",
                   "validated": "money", "gap": "money", "realisation": "pct", "confidence": "number", "methodology": "text",
                   "primary_evidence": "text", "assumption_share": "pct"},
        "default_sort": ("gap", "DESC"),
    },
    "risks": {
        "view": "risk_register",
        "label": "risks",
        "default_fields": ["risk_id", "initiative_id", "initiative_name", "category", "title", "financial_impact", "probability",
                           "exposure", "owner", "status"],
        "fields": {"risk_id": "text", "initiative_id": "text", "initiative_name": "text", "bu_id": "text", "category": "text",
                   "title": "text", "financial_impact": "money", "probability": "pct", "exposure": "money", "owner": "text",
                   "status": "text", "mitigation": "text"},
        "default_sort": ("exposure", "DESC"),
    },
    "costs": {
        "view": "cost_by_category",
        "label": "cost categories",
        "default_fields": ["initiative_id", "initiative_name", "cost_category", "cost_group", "actual", "budget", "variance"],
        "fields": {"initiative_id": "text", "initiative_name": "text", "bu_id": "text", "cost_category": "text", "cost_group": "text",
                   "actual": "money", "budget": "money", "variance": "money"},
        "default_sort": ("actual", "DESC"),
    },
}

FIELD_SYNONYMS = [
    # (regex, entity -> field) - first match wins; longer phrases first
    (r"budget variance|over ?spend|overrun", {"initiatives": "budget_variance_pct", "costs": "variance"}),
    (r"expected (?:ai )?value|expected benefit|business case", {"initiatives": "expected_value", "benefits": "business_case"}),
    (r"realis(?:ed|ation) rate|benefit realisation|realisation", {"initiatives": "benefit_realisation", "benefits": "realisation"}),
    (r"realised (?:ai )?value|realised benefit|actual benefit", {"initiatives": "realised_value", "benefits": "realised"}),
    (r"validated", {"initiatives": "validated_value", "benefits": "validated"}),
    (r"hypothetical", {"initiatives": "hypothetical_value"}),
    (r"expected roi", {"initiatives": "expected_roi"}),
    (r"\broi\b|return", {"initiatives": "realised_roi"}),
    (r"\bnpv\b", {"initiatives": "npv_3yr"}),
    (r"payback", {"initiatives": "payback_months"}),
    (r"confidence", {"initiatives": "confidence", "benefits": "confidence"}),
    (r"adoption", {"initiatives": "adoption_rate"}),
    (r"cloud (?:cost|consumption|spend)", {"initiatives": "cloud_consumption"}),
    (r"infrastructure cost|infra cost", {"initiatives": "infrastructure_cost"}),
    (r"exposure|risk exposure", {"initiatives": "risk_exposure", "risks": "exposure"}),
    (r"impact", {"risks": "financial_impact"}),
    (r"probability|likelihood", {"risks": "probability"}),
    (r"\bgap\b|shortfall|unrealised", {"benefits": "gap"}),
    (r"forecast", {"initiatives": "forecast_spend", "benefits": "owner_forecast"}),
    (r"\bbudget\b", {"initiatives": "budget", "costs": "budget"}),
    (r"investment|invested|spend|cost", {"initiatives": "investment", "costs": "actual"}),
]

CATEGORICAL = [
    # (regex, field, value) applied when the entity has the field
    (r"\bemea\b|europe", "geography", "EMEA"), (r"\bamericas\b|\bus\b|north america", "geography", "Americas"),
    (r"\bapj\b|asia", "geography", "APJ"), (r"\bglobal\b", "geography", "Global"),
    (r"customer operations|customer ops", "business_unit", "Customer Operations"),
    (r"sales|commercial", "business_unit", "Sales & Commercial"),
    (r"supply chain|manufacturing", "business_unit", "Supply Chain & Manufacturing"),
    (r"\bfinance\b(?! close)", "business_unit", "Finance"),
    (r"technology|security|\bit\b", "business_unit", "Technology & Security"),
    (r"corporate services", "business_unit", "Corporate Services"),
    (r"engineering", "business_unit", "Engineering"),
    (r"private cloud ai|\bpcai\b", "hpe_category", "HPE Private Cloud AI"),
    (r"greenlake", "hpe_category", "HPE GreenLake cloud"),
    (r"networking", "hpe_category", "Networking"),
    (r"ai infrastructure", "hpe_category", "AI Infrastructure"),
    (r"\bdelayed\b|\blate\b", "status", "Delayed"),
    (r"at[- ]risk|\bred\b", "rag", "Red"), (r"\bamber\b|watch ?list", "rag", "Amber"), (r"\bgreen\b|on track", "rag", "Green"),
    (r"productivity", "benefit_type", "productivity"), (r"cost savings?", "benefit_type", "cost_savings"),
    (r"revenue", "benefit_type", "revenue"), (r"risk[- ]related|risk value", "benefit_type", "risk"),
    (r"management estimate", "methodology", "management_estimate"),
    (r"\bopen\b", "status", "Open"), (r"mitigating", "status", "Mitigating"),
    (r"\bgpu\b", "cost_category", "gpu"), (r"\bcloud\b", "cost_category", "cloud"), (r"consulting", "cost_category", "consulting"),
]

OPERATORS = [
    (r"(?:more than|greater than|above|over|exceeding|>=?|at least|higher than)", ">"),
    (r"(?:less than|below|under|<=?|at most|lower than)", "<"),
]
FORBIDDEN = re.compile(
    r"\b(drop|truncate|alter)\s+(table|database|view|index|schema)\b|\bdelete\s+from\b|\binsert\s+into\b"
    r"|\bupdate\s+\w+\s+set\b|\bselect\b[\s\S]*\bfrom\b|;|--|/\*|\bunion\s+(all\s+)?select\b|\battach\b|\bpragma\b"
    r"|\b(delete|remove|wipe|erase|destroy|overwrite|drop)\b[\s\S]*\b(data|records?|rows?|tables?|initiatives?|database|benefits?|risks?)\b",
    re.I)
MAX_LIMIT = 100


class QueryRefused(ValueError):
    pass


@dataclass
class Filter:
    field: str
    op: str  # = > <
    value: float | str

    def to_dict(self):
        return {"field": self.field, "op": self.op, "value": self.value}


@dataclass
class QuerySpec:
    entity: str
    fields: list[str]
    filters: list[Filter] = field(default_factory=list)
    sort: tuple[str, str] | None = None
    limit: int = 50

    def to_dict(self):
        return {"entity": self.entity, "fields": self.fields, "filters": [f.to_dict() for f in self.filters],
                "sort": list(self.sort) if self.sort else None, "limit": self.limit}


def _amount(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    unit = (unit or "").lower()
    if unit in ("m", "mn", "million", "millions"):
        v *= 1e6
    elif unit in ("k", "thousand"):
        v *= 1e3
    elif unit in ("b", "bn", "billion"):
        v *= 1e9
    return v


def parse(question: str) -> QuerySpec:
    q = question.strip()
    if not q or len(q) > 500:
        raise QueryRefused("Questions must be between 1 and 500 characters.")
    if FORBIDDEN.search(q):
        raise QueryRefused("Only read-only analytical questions are supported; SQL and data-changing requests are not accepted.")
    ql = q.lower()
    entity = ("risks" if re.search(r"\brisks?\b", ql) and not re.search(r"at[- ]risk", ql)
              else "benefits" if re.search(r"\bbenefit(s| lines?)\b", ql) and not re.search(r"initiatives?|projects?", ql)
              else "costs" if re.search(r"cost categor|by category|spend by|vendor", ql) else "initiatives")
    model = SEMANTIC_MODEL[entity]
    filters: list[Filter] = []

    # numeric comparisons: "<field words> <op> <number><unit|%>"  or  "<op> <number> <field words>"
    num = r"\$?\s*([\d.,]+)\s*(%|m\b|mn\b|million|k\b|thousand|b\b|bn\b|billion)?"
    for op_re, op in OPERATORS:
        for m in re.finditer(op_re + r"\s+" + num, ql):
            raw, unit = m.group(1), m.group(2)
            value = float(raw.replace(",", "")) / 100 if unit == "%" else _amount(raw, unit)
            window = ql[max(0, m.start() - 40): m.end() + 30]
            fname = _field_in(window, entity) or model["default_sort"][0]
            if model["fields"].get(fname) == "pct" and unit != "%" and value > 1.5:
                value = value / 100
            filters.append(Filter(fname, op, value))
    for pat, fname, val in CATEGORICAL:
        if fname in model["fields"] and re.search(pat, ql) and not any(f.field == fname for f in filters):
            if entity == "benefits" and fname == "benefit_type" and "benefit" not in ql:
                continue
            filters.append(Filter(fname, "=", val))
    m = re.search(r"\b(AI-\d{3})\b", q, re.I)
    if m and "initiative_id" in model["fields"]:
        filters.append(Filter("initiative_id", "=", m.group(1).upper()))

    sort = model["default_sort"]
    m = re.search(r"(top|largest|biggest|highest|most|bottom|lowest|smallest|least|worst|best)\s*(\d+)?", ql)
    limit = 50
    if m:
        word, n = m.group(1), m.group(2)
        direction = "ASC" if word in ("bottom", "lowest", "smallest", "least", "worst") else "DESC"
        after = ql[m.end(): m.end() + 60]
        fname = _field_in(after, entity) or _field_in(ql, entity) or model["default_sort"][0]
        sort = (fname, direction)
        limit = int(n) if n else (5 if word in ("top", "bottom") else 10)
    m2 = re.search(r"(?:sorted|ordered|rank(?:ed)?) by\s+([a-z %$]+)", ql)
    if m2:
        sort = (_field_in(m2.group(1), entity) or sort[0], "DESC")
    fields = list(model["default_fields"])
    for f in filters + ([Filter(sort[0], "=", "")] if sort else []):
        if f.field not in fields:
            fields.append(f.field)
    return QuerySpec(entity, fields, filters, sort, min(limit, MAX_LIMIT))


def _field_in(text_: str, entity: str) -> str | None:
    for pat, mapping in FIELD_SYNONYMS:
        if entity in mapping and re.search(pat, text_):
            return mapping[entity]
    return None


def render(spec: QuerySpec, bu_scope: str | None = None) -> tuple[str, dict]:
    if spec.entity not in SEMANTIC_MODEL:
        raise QueryRefused("Unknown entity")
    model = SEMANTIC_MODEL[spec.entity]
    allowed = model["fields"]
    cols = [c for c in spec.fields if c in allowed]
    if not cols:
        raise QueryRefused("No valid fields requested")
    where, params = [], {}
    for i, f in enumerate(spec.filters):
        if f.field not in allowed or f.op not in ("=", ">", "<"):
            raise QueryRefused(f"Filter on '{f.field}' is not allowed")
        params[f"p{i}"] = f.value
        where.append(f"{f.field} {f.op} :p{i}")
    if bu_scope:
        where.append("bu_id = :scope")
        params["scope"] = bu_scope
    sql = f"SELECT {', '.join(cols)} FROM {model['view']}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if spec.sort and spec.sort[0] in allowed and spec.sort[1] in ("ASC", "DESC"):
        sql += f" ORDER BY {spec.sort[0]} {spec.sort[1]}"
    sql += f" LIMIT {min(int(spec.limit), MAX_LIMIT)}"
    validate_sql(sql)
    return sql, params


_ALLOWED_VIEWS = {m["view"] for m in SEMANTIC_MODEL.values()}


def validate_sql(sql: str) -> None:
    s = sql.strip()
    if ";" in s or "--" in s or "/*" in s:
        raise QueryRefused("Multiple statements and comments are not allowed")
    if not re.match(r"^SELECT\s", s, re.I):
        raise QueryRefused("Only SELECT statements are allowed")
    if re.search(r"\b(drop|delete|insert|update|alter|truncate|create|attach|pragma|grant|revoke|replace|union)\b", s, re.I):
        raise QueryRefused("Statement contains a forbidden keyword")
    views = set(re.findall(r"\bFROM\s+([a-z_]+)", s, re.I))
    if not views or not views <= _ALLOWED_VIEWS:
        raise QueryRefused("Query targets a table outside the semantic layer")


def execute(engine: Engine, sql: str, params: dict) -> list[dict]:
    validate_sql(sql)
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            conn.exec_driver_sql("PRAGMA query_only = ON")
        try:
            rows = conn.execute(text(sql), params).mappings().all()
        finally:
            if engine.dialect.name == "sqlite":
                conn.exec_driver_sql("PRAGMA query_only = OFF")
    return [dict(r) for r in rows]


def describe(spec: QuerySpec) -> str:
    model = SEMANTIC_MODEL[spec.entity]
    parts = [model["label"]]
    for f in spec.filters:
        v = f.value
        if isinstance(v, float) and model["fields"].get(f.field) == "money":
            v = f"${v / 1e6:,.1f}M"
        elif isinstance(v, float) and model["fields"].get(f.field) == "pct":
            v = f"{v:.0%}"
        parts.append(f"{f.field.replace('_', ' ')} {f.op} {v}")
    if spec.sort:
        parts.append(f"sorted by {spec.sort[0].replace('_', ' ')} {'descending' if spec.sort[1] == 'DESC' else 'ascending'}")
    return ", ".join(parts)
