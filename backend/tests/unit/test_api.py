import httpx
import pytest

from app.main import app


@pytest.fixture
def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def test_liveness_and_version(client):
    async with client:
        response = await client.get("/health/live", headers={"X-Request-ID": "test-correlation"})
        assert response.status_code == 200
        assert response.json() == {"status": "live"}
        assert response.headers["x-request-id"] == "test-correlation"
        assert response.headers["x-content-type-options"] == "nosniff"
        response = await client.get("/api/v1/system/version")
        assert response.json()["version"] == "0.1.0"


async def test_payload_limit(client):
    async with client:
        response = await client.post("/api/v1/clients", content=b"x" * 65537)
        assert response.status_code == 413
        assert set(response.json()["error"]) == {"code", "message", "request_id"}


async def test_invalid_host(client):
    async with client:
        assert (
            await client.get("/health/live", headers={"host": "attacker.invalid"})
        ).status_code == 400


async def test_request_id_sanitization(client):
    async with client:
        response = await client.get("/health/live", headers={"x-request-id": "bad id!"})
        assert response.headers["x-request-id"] != "bad id!"


def test_openapi_routes_and_auth():
    schema = app.openapi()
    for path in [
        "/api/v1/auth/bootstrap",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/clients",
        "/api/v1/entities",
        "/api/v1/engagements",
        "/api/v1/ai/execute",
        "/api/v1/jobs/diagnostic",
    ]:
        assert path in schema["paths"]
    assert schema["paths"]["/api/v1/clients"]["get"]["security"]
