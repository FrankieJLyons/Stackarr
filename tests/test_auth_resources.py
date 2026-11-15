import asyncio
import threading
import time

import httpx
import pytest

from stackarr import server


def test_setup_resource_failure_preserves_setup_and_can_retry(client, app, monkeypatch):
    token = app.state.store.root / "setup-token"
    body = {"password": "synthetic test password", "setup_token": token.read_text()}
    original = server.password_hash

    def fail(*args):
        raise ValueError("private runtime diagnostic")

    monkeypatch.setattr(server, "password_hash", fail)
    response = client.post("/api/setup", json=body, headers={"Origin": "http://testserver"})
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert "private runtime diagnostic" not in response.text
    assert token.exists()
    with app.state.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0
    monkeypatch.setattr(server, "password_hash", original)
    assert client.post("/api/setup", json=body, headers={"Origin": "http://testserver"}).status_code == 200


def test_login_resource_failure_never_creates_session(client, app, auth, monkeypatch):
    client.post("/api/logout", headers=auth)

    def fail(*args):
        raise MemoryError()

    monkeypatch.setattr(server, "password_hash", fail)
    response = client.post("/api/login", json={"password": "synthetic test password"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 503
    assert "set-cookie" not in response.headers
    assert not client.get("/api/session").json()["authenticated"]
    with app.state.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_password_checks_do_not_allocate_concurrently(app, monkeypatch):
    active = maximum = 0
    lock = threading.Lock()

    def hash_once(*args):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(.04)
        with lock:
            active -= 1
        return "synthetic"

    monkeypatch.setattr(server, "password_hash", hash_once)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        results = await asyncio.gather(*(client.post("/api/login", json={"password": "synthetic password"}, headers={"Origin": "http://testserver"}) for _ in range(3)))
    assert all(response.status_code == 401 for response in results)
    assert maximum == 1
