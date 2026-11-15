from concurrent.futures import ThreadPoolExecutor

from stackarr import setup_handoff
from stackarr.setup_handoff import authorized, exchange, issue


def ticket(app):
    return issue(app.state.store, "http://testserver").split("#setup=")[1]


def test_invitation_claim_and_password_without_token(client, app):
    value = ticket(app)
    assert value not in client.get("/api/session").text
    assert client.post("/api/setup/handoff", json={"ticket": value}).status_code == 403
    headers = {"Origin": "http://testserver"}
    response = client.post("/api/setup/handoff", json={"ticket": value}, headers=headers)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/session").json()["setup_approved"]
    assert client.post("/api/setup/handoff", json={"ticket": value}, headers=headers).status_code == 403
    assert client.post("/api/setup", json={"password": "synthetic test password"}, headers=headers).status_code == 200
    assert not client.get("/api/session").json()["setup_approved"]
    assert client.get("/api/config").status_code == 401
    assert issue(app.state.store, "http://testserver") == "http://testserver/"


def test_expiry_rotation_and_no_unapproved_claim(client, app):
    old = ticket(app)
    new = ticket(app)
    assert exchange(app.state.store, old) is None
    cookie = exchange(app.state.store, new)
    assert authorized(app.state.store, cookie)
    assert not authorized(app.state.store, new)
    with app.state.store.db() as db:
        db.execute("UPDATE setup_handoffs SET expires=0")
    assert not authorized(app.state.store, cookie)
    value = ticket(app)
    with app.state.store.db() as db:
        db.execute("UPDATE setup_handoffs SET expires=0")
    assert exchange(app.state.store, value) is None
    response = client.post("/api/setup", json={"password": "synthetic test password"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 403


def test_only_one_browser_can_claim_invitation(app):
    value = ticket(app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: exchange(app.state.store, value), range(2)))
    assert sum(cookie is not None for cookie in result) == 1
    assert value.encode() not in app.state.store.path.read_bytes()


def test_password_entry_has_its_own_bounded_approval_window(client, app, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(setup_handoff.time, "time", lambda: clock[0])
    value = ticket(app)
    clock[0] += setup_handoff.INVITATION_SECONDS - 1
    headers = {"Origin": "http://testserver"}
    response = client.post("/api/setup/handoff", json={"ticket": value}, headers=headers)
    assert response.status_code == 200
    assert f"Max-Age={setup_handoff.BROWSER_APPROVAL_SECONDS}" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    clock[0] += 6 * 60
    assert client.get("/api/session").json()["setup_approved"]
    assert client.post("/api/setup", json={"password": "synthetic delayed setup password"}, headers=headers).status_code == 200
    assert client.post("/api/login", json={"password": "synthetic delayed setup password"}, headers=headers).status_code == 200
    assert client.get("/api/session").json()["authenticated"]


def test_session_checks_do_not_extend_setup_approval(client, app, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(setup_handoff.time, "time", lambda: clock[0])
    headers = {"Origin": "http://testserver"}
    assert client.post("/api/setup/handoff", json={"ticket": ticket(app)}, headers=headers).status_code == 200
    with app.state.store.db() as db:
        deadline = db.execute("SELECT expires FROM setup_handoffs WHERE kind='browser'").fetchone()[0]
    clock[0] = deadline - 1
    assert client.get("/api/session").json()["setup_approved"]
    clock[0] = deadline + 1
    assert not client.get("/api/session").json()["setup_approved"]
    response = client.post("/api/setup", json={"password": "synthetic expired setup password"}, headers=headers)
    assert response.status_code == 403
    assert "password has not been saved" in response.json()["detail"]
    with app.state.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0
