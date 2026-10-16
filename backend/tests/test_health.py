from importlib.metadata import version

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "My Pal",
        "version": version("mypal"),
        "environment": "test",
    }


def test_health_response_carries_request_id(client: TestClient) -> None:
    response = client.get("/api/health")

    assert len(response.headers["X-Request-ID"]) == 32
