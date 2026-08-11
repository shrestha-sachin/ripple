from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok_and_solver_is_ready():
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["service"] == "ripple-api"
    # A degraded status here means OR-Tools cannot solve on this host, which
    # is the exact failure mode we deploy Phase 0 early to catch.
    assert body["solver_ready"] is True, f"CP-SAT smoke test failed: {body}"
    assert body["status"] == "ok"
    assert body["dependencies"]["ortools"] != "missing"
    assert body["uptime_seconds"] >= 0


def test_solver_caps_are_enforced_and_bounded():
    body = client.get("/health").json()
    caps = body["solver_caps_seconds"]
    # Every solve path must be time-capped so the UI can never hang.
    assert 0 < caps["scenario"] <= caps["repair"] <= caps["plan"]
    assert caps["plan"] <= 30


def test_root_lists_entrypoints():
    body = client.get("/").json()
    assert body["health"] == "/health"


def test_cors_allows_local_frontend():
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
