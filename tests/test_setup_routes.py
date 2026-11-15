import json

from fastapi.testclient import TestClient
from test_controller_dashboard import authorize, dashboard


def test_arr_login_review_replay_revision_and_owner_password(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    store, identity = app.state.store, "b" * 32
    revision, config = store.config()
    config.integrations["sonarr"].enabled = True
    config.integrations["sonarr"].url = "http://host.docker.internal:38989"
    store.save(config, revision, {"sonarr": {"api_key": "a" * 32}})
    with store.db() as db:
        db.execute("INSERT INTO controller_connections VALUES(?,?,?,1)",
                   (identity, store.config()[0], json.dumps({"sonarr": 38989})))
    login = {"username": "stackarr", "password": "synthetic-generated-password-value-12345"}
    calls = []
    original = remote.request

    async def request(operation, payload=None):
        if operation not in {"arr-logins", "arr-login"}:
            return await original(operation, payload)
        calls.append(operation)
        if operation == "arr-logins":
            return {"id": identity, "apps": {"sonarr": {"port": 38989, "api_key": "a" * 32,
                                                        "state": "ready", "login": login}}}
        return {"id": identity, "app": "sonarr", "port": 38989, "api_key": "a" * 32, "login": login}

    monkeypatch.setattr(remote, "request", request)
    with TestClient(app) as browser:
        endpoint = "/api/deployments/" + identity + "/logins/review"
        assert browser.post(endpoint, headers={"Origin": "http://testserver"}).status_code == 401
        headers = authorize(browser, app)
        assert browser.post(endpoint).status_code == 403
        reviewed = browser.post(endpoint, headers=headers)
        assert reviewed.status_code == 200 and login["password"] not in reviewed.text
        token = {"review_token": reviewed.json()["review_token"]}
        store.save(store.config()[1], store.config()[0])
        assert browser.post("/api/app-logins/apply", json=token, headers=headers).status_code == 409
        assert not calls
        token = {"review_token": browser.post(endpoint, headers=headers).json()["review_token"]}
        saved = browser.post("/api/app-logins/apply", json=token, headers=headers)
        assert saved.status_code == 200 and login["password"] not in saved.text and "a" * 32 not in saved.text
        assert browser.post("/api/app-logins/apply", json=token, headers=headers).status_code == 409
        reveal = "/api/apps/sonarr/login"
        assert browser.post(reveal, json={"password": "wrong password"}, headers=headers).status_code == 403
        assert calls == ["arr-logins"]
        assert browser.post(reveal, json={"password": "synthetic test password"}, headers=headers).json() == login
        assert calls == ["arr-logins", "arr-login"]
        assert login["password"] not in browser.get("/api/deployments").text


def test_source_review_requires_session_csrf_and_single_use_token(tmp_path, monkeypatch):
    app, _ = dashboard(tmp_path, monkeypatch)
    calls = []

    async def review(store, source, transport=None):
        assert source.api_key == "synthetic-provider-key"
        return {"name": source.name, "feed_url": source.feed_url, "exists": False,
                "private": source.api_key}

    async def apply(store, plan, transport=None):
        calls.append(plan["private"])
        return {"state": "connected"}

    monkeypatch.setattr("stackarr.indexers.review", review)
    monkeypatch.setattr("stackarr.indexers.apply", apply)
    body = {"name": "Chosen provider", "feed_url": "http://fixture.example/api", "api_key": "synthetic-provider-key"}
    with TestClient(app) as browser:
        assert browser.post("/api/indexers/review", json=body, headers={"Origin": "http://testserver"}).status_code == 401
        headers = authorize(browser, app)
        assert browser.post("/api/indexers/review", json=body).status_code == 403
        reviewed = browser.post("/api/indexers/review", json=body, headers=headers)
        assert reviewed.status_code == 200 and body["api_key"] not in reviewed.text
        token = {"review_token": reviewed.json()["review_token"]}
        assert browser.post("/api/indexers/apply", json=token, headers=headers).status_code == 200
        assert browser.post("/api/indexers/apply", json=token, headers=headers).status_code == 409
        assert calls == ["synthetic-provider-key"]


def test_companion_review_requires_csrf_strict_body_and_single_use(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    identity = "a" * 32
    with TestClient(app) as browser:
        endpoint = "/api/deployments/" + identity + "/companions-review"
        assert browser.post(endpoint, json={}, headers={"Origin": "http://testserver"}).status_code == 401
        headers = authorize(browser, app)
        assert browser.post(endpoint, json={}).status_code == 403
        assert browser.post(endpoint, json={"dryRun": False}, headers=headers).status_code == 422
        reviewed = browser.post(endpoint, json={}, headers=headers)
        assert reviewed.status_code == 200
        assert remote.calls[-1] == ("managed-review", {"id": identity, "action": "companions"})
        token = {"review_token": reviewed.json()["review_token"]}
        assert browser.post("/api/deployments/actions/apply", json=token, headers=headers).status_code == 202
        assert browser.post("/api/deployments/actions/apply", json=token, headers=headers).status_code == 409
