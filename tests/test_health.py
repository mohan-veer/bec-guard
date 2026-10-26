from fastapi.testclient import TestClient

from app.main import app


def test_healthz_starts_without_keys(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with TestClient(app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "mock"
    assert body["tavily_mode"] == "mock"
