"""FastAPI surface smoke tests."""
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health_and_metric():
    assert client.get("/health").json()["latest_fiscal_year"] == 2026
    r = client.get("/metrics/operating_margin_pct/2026").json()
    assert r["status"] == "ok" and r["inputs"]


def test_ask_and_scenario():
    r = client.post("/ask", json={"question": "Which segment drove revenue growth?"}).json()
    assert r["intent"] == "segment" and r["sources"] and r["audit_id"]
    s = client.post("/scenario", json={"deltas": {"revenue_growth": -0.05}}).json()
    assert s["delta"]["revenue"] < 0 and "not management guidance" in s["disclaimer"]


def test_driver_tree_and_unknown_metric():
    assert client.get("/driver-tree/operating-income/2026").json()["children"]
    assert client.get("/metrics/not_a_metric/2026").status_code == 404
