import httpx
import pytest
from fastapi.testclient import TestClient

from stackarr.server import create_app


@pytest.fixture
def app(tmp_path):
    def deny(request):
        raise AssertionError("Tests must explicitly mock every integration request")

    return create_app(
        tmp_path, origin="http://testserver", transport=httpx.MockTransport(deny), background=False
    )


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth(client, app):
    password = "synthetic test password"
    headers = {"Origin": "http://testserver"}
    response = client.post(
        "/api/setup",
        json={"password": password, "setup_token": (app.state.store.root / "setup-token").read_text()},
        headers=headers,
    )
    assert response.status_code == 200
    response = client.post("/api/login", json={"password": password}, headers=headers)
    assert response.status_code == 200
    return headers | {"X-CSRF-Token": response.json()["csrf"]}
