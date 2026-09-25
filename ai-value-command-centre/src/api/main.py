"""AI Value Command Centre REST API.

    uvicorn src.api.main:app --reload     # then open http://127.0.0.1:8000

Every data endpoint requires a bearer token (POST /auth/login). Business-unit users only see their own BU's
initiatives and aggregates. Every copilot query, scenario run and report is written to the audit log.
"""
from __future__ import annotations

import re

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src import settings
from src.agents.orchestrator import ask, context_for
from src.api import payloads
from src.api.serialize import jsonable
from src.db.database import ensure_database, get_engine
from src.governance import audit
from src.query import semantic_layer as Q
from src.reporting.briefing import build_briefing, to_html, to_markdown
from src.scenario.engine import LEVERS
from src.security.auth import Principal, issue_token, verify_password, verify_token

@asynccontextmanager
async def lifespan(_app):
    ensure_database()
    yield


app = FastAPI(lifespan=lifespan, title="AI Value Command Centre API", version=settings.ENGINE_VERSION,
              description="Portfolio prototype: public HPE information + clearly labelled SYNTHETIC enterprise data. "
                          "Deterministic finance engines; the LLM never calculates.")


# ------------------------------------------------------------------ auth
class LoginRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=200)


def principal(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    p = verify_token(authorization.split(" ", 1)[1].strip())
    if p is None:
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return p


def require(permission: str):
    def dep(p: Principal = Depends(principal)) -> Principal:
        if not p.can(permission):
            raise HTTPException(403, f"Role {p.role} lacks permission {permission}")
        return p
    return dep


@app.post("/auth/login")
def login(req: LoginRequest):
    from sqlalchemy import select

    from src.db import schema

    with get_engine().connect() as conn:
        row = conn.execute(select(schema.users).where(schema.users.c.user_id == req.user_id)).mappings().first()
    if not row or not verify_password(req.password, row["password_hash"]):
        audit.record(req.user_id, "-", "auth.failed", {})
        raise HTTPException(401, "Invalid credentials")
    p = Principal(row["user_id"], row["role"], row["bu_id"])
    audit.record(p.user_id, p.role, "auth.login", {"scope": p.scope})
    return {"token": issue_token(p), "user": {"user_id": p.user_id, "display_name": row["display_name"], "role": p.role, "bu_id": p.bu_id}}


@app.get("/auth/me")
def me(p: Principal = Depends(principal)):
    return {"user_id": p.user_id, "role": p.role, "bu_id": p.bu_id, "scope": p.scope}


@app.get("/auth/demo-users")
def demo_users():
    from src.db.database import DEMO_USERS

    return [{"user_id": u, "display_name": n, "role": r, "bu_id": b} for u, n, r, b in DEMO_USERS]


@app.get("/health")
def health():
    k = context_for(None).kpis
    return {"status": "ok", "engine_version": settings.ENGINE_VERSION, "initiatives": k["initiatives"], "as_of": k["as_of"]}


# ------------------------------------------------------------------ data
READ = require("read:portfolio")


@app.get("/dashboard")
def dashboard(p: Principal = Depends(READ)):
    return payloads.dashboard(context_for(p.scope))


@app.get("/portfolio")
def portfolio(p: Principal = Depends(READ)):
    return payloads.portfolio(context_for(p.scope))


@app.get("/initiatives")
def initiatives(p: Principal = Depends(READ)):
    return payloads.portfolio(context_for(p.scope))["initiatives"]


@app.get("/initiatives/{initiative_id}")
def initiative(initiative_id: str, p: Principal = Depends(READ)):
    if not re.fullmatch(r"AI-\d{3}", initiative_id):
        raise HTTPException(422, "initiative_id must look like AI-001")
    d = payloads.initiative(context_for(p.scope), initiative_id)
    if d is None:
        raise HTTPException(404, "Initiative not found in your scope")
    return d


@app.get("/investment")
def investment(p: Principal = Depends(READ)):
    return payloads.investment(context_for(p.scope))


@app.get("/costs")
def costs(p: Principal = Depends(READ)):
    return payloads.costs(context_for(p.scope))


@app.get("/benefits")
def benefits(p: Principal = Depends(READ)):
    return payloads.benefits(context_for(p.scope))


@app.get("/roi")
def roi(p: Principal = Depends(READ)):
    return payloads.roi(context_for(p.scope))


@app.get("/risks")
def risks(p: Principal = Depends(READ)):
    return payloads.risks(context_for(p.scope))


@app.get("/assumptions")
def assumptions(p: Principal = Depends(READ)):
    return payloads.assumptions(context_for(p.scope))


@app.get("/evidence/{evidence_id}")
def evidence(evidence_id: str, p: Principal = Depends(READ)):
    if not re.fullmatch(r"[a-z_]+\.[A-Za-z0-9_.\-]{1,60}", evidence_id):
        raise HTTPException(422, "Malformed evidence id")
    e = payloads.evidence(context_for(p.scope), evidence_id)
    if e is None:
        raise HTTPException(404, "Evidence not found in your scope")
    return e


@app.get("/sources")
def sources(p: Principal = Depends(READ)):
    return payloads.sources(context_for(p.scope))


# ------------------------------------------------------------------ copilot, query, scenario, reports
class CopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    use_llm: bool = True


@app.post("/copilot/query")
def copilot(req: CopilotRequest, p: Principal = Depends(require("run:copilot"))):
    return jsonable(ask(req.question, p, use_llm=req.use_llm))


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.post("/query")
def nl_query(req: QueryRequest, p: Principal = Depends(require("run:copilot"))):
    try:
        spec = Q.parse(req.question)
        sql, params = Q.render(spec, p.scope)
        rows = Q.execute(ensure_database(), sql, params)
    except Q.QueryRefused as e:
        audit.record(p.user_id, p.role, "query.refused", {"question": req.question, "reason": str(e)})
        raise HTTPException(400, str(e))
    audit.record(p.user_id, p.role, "query.run", {"question": req.question, "sql": sql, "params": params}, rows)
    return jsonable({"spec": spec.to_dict(), "sql": sql, "params": params, "rows": rows, "description": Q.describe(spec)})


class ScenarioRequest(BaseModel):
    levers: dict[str, float] = Field(default_factory=dict)

    @field_validator("levers")
    @classmethod
    def _bounded(cls, v: dict[str, float]):
        for k, x in v.items():
            if k not in LEVERS:
                raise ValueError(f"unknown lever {k}")
            lo, hi = LEVERS[k][2], LEVERS[k][3]
            if not lo <= x <= hi:
                raise ValueError(f"{k} must be between {lo} and {hi}")
        return v


@app.post("/scenario/run")
def scenario_run(req: ScenarioRequest, p: Principal = Depends(require("run:scenario"))):
    res = context_for(p.scope).scenario.run(req.levers)
    audit.record(p.user_id, p.role, "scenario.run", {"levers": req.levers}, jsonable(res["incremental"]))
    return jsonable(res)


@app.get("/scenario/meta")
def scenario_meta(p: Principal = Depends(require("run:scenario"))):
    return payloads.scenario_meta(context_for(p.scope))


@app.get("/scenario/sensitivity")
def scenario_sensitivity(p: Principal = Depends(require("run:scenario"))):
    return jsonable(context_for(p.scope).scenario.sensitivity())


class ReportRequest(BaseModel):
    format: str = Field(default="json", pattern="^(json|markdown|html)$")


@app.post("/reports/cfo")
def report(req: ReportRequest, p: Principal = Depends(require("run:report"))):
    b = build_briefing(context_for(p.scope))
    audit.record(p.user_id, p.role, "report.cfo", {"format": req.format}, jsonable(b))
    if req.format == "html":
        return HTMLResponse(to_html(jsonable(b)))
    if req.format == "markdown":
        return {"markdown": to_markdown(jsonable(b))}
    return jsonable(b)


@app.get("/audit")
def audit_log(limit: int = 100, p: Principal = Depends(require("read:audit"))):
    return audit.read(min(max(limit, 1), 500))


# ------------------------------------------------------------------ web app
if settings.WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=settings.WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(settings.WEB_DIR / "index.html")
