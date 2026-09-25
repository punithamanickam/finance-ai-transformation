import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def token(client, user="cfo@meridian.example"):
    r = client.post("/auth/login", json={"user_id": user, "password": "demo"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.parametrize("path", ["/dashboard", "/portfolio", "/initiatives", "/costs", "/benefits", "/roi", "/risks", "/sources", "/audit"])
def test_endpoints_require_auth(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer forged"}).status_code == 401


def test_login_rejects_bad_password(client):
    assert client.post("/auth/login", json={"user_id": "cfo@meridian.example", "password": "nope"}).status_code == 401


@pytest.mark.parametrize("path", ["/dashboard", "/portfolio", "/initiatives", "/initiatives/AI-003", "/investment", "/costs", "/benefits",
                                  "/roi", "/risks", "/assumptions", "/sources", "/evidence/kpi.expected_value", "/scenario/meta", "/audit"])
def test_cfo_can_read_everything(client, path):
    assert client.get(path, headers=token(client)).status_code == 200


def test_bu_user_is_scoped_and_cannot_read_audit(client):
    h = token(client, "bu.supplychain@meridian.example")
    ids = {i["initiative_id"] for i in client.get("/initiatives", headers=h).json()}
    assert ids == {"AI-003", "AI-009"}
    assert client.get("/initiatives/AI-001", headers=h).status_code == 404
    assert client.get("/audit", headers=h).status_code == 403
    assert client.post("/reports/cfo", headers=h, json={}).status_code == 403


def test_input_validation(client):
    h = token(client)
    assert client.get("/initiatives/../../etc", headers=h).status_code in (404, 422)
    assert client.get("/initiatives/XYZ", headers=h).status_code == 422
    assert client.post("/copilot/query", headers=h, json={"question": ""}).status_code == 422
    assert client.post("/scenario/run", headers=h, json={"levers": {"utilisation_target": 5}}).status_code == 422
    assert client.post("/scenario/run", headers=h, json={"levers": {"rm_rf": 1}}).status_code == 422
    assert client.post("/query", headers=h, json={"question": "DROP TABLE users"}).status_code == 400


def test_copilot_scenario_report_flow(client):
    h = token(client)
    r = client.post("/copilot/query", headers=h, json={"question": "How much value has actually been realised?", "use_llm": False}).json()
    assert r["audit_id"] and r["numbers"]
    s = client.post("/scenario/run", headers=h, json={"levers": {"utilisation_target": 0.8}}).json()
    assert s["incremental"]["capacity_gpu_hours"] > 0
    rep = client.post("/reports/cfo", headers=h, json={"format": "json"}).json()
    assert [x["heading"] for x in rep["sections"]][:2] == ["AI Portfolio Executive Summary", "Investment"]
    assert "Management may wish to" in " ".join(rep["sections"][-1]["points"])
    assert client.get("/evidence/kpi.nope", headers=h).status_code == 404
