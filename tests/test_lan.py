import json

import httpx
import pytest
from fastapi.testclient import TestClient

from stackarr.lan import LanAccess, browser_routes, browser_url
from stackarr.server import create_app

LOCAL = "http://localhost:29123"
REMOTE = "https://stackarr.home.arpa:29443"


@pytest.fixture
def network(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKARR_LAN_ORIGIN", REMOTE)
    monkeypatch.setenv("STACKARR_LAN_LINKS", json.dumps({"plex": "https://plex.home.arpa:29443"}))
    app = create_app(tmp_path, origin=LOCAL, background=False,
                     transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError("No app access"))))
    with TestClient(app, base_url=LOCAL) as local, TestClient(app, base_url=REMOTE) as remote:
        password = "Synthetic LAN test password"
        body = {"password": password, "setup_token": (tmp_path / "setup-token").read_text()}
        assert remote.post("/api/setup", json=body, headers={"Origin": REMOTE}).status_code == 403
        assert local.post("/api/setup", json=body, headers={"Origin": LOCAL}).status_code == 200
        yield app, local, remote, password


def login(client, origin, password):
    result = client.post("/api/login", json={"password": password}, headers={"Origin": origin})
    assert result.status_code == 200
    return result, {"Origin": origin, "X-CSRF-Token": result.json()["csrf"]}


def test_lan_owner_auth_secure_cookie_and_local_access(network):
    app, local, remote, password = network
    assert remote.get("/api/config").status_code == 401
    response, headers = login(remote, REMOTE, password)
    assert all(flag in response.headers["set-cookie"] for flag in ("Secure", "HttpOnly", "SameSite=strict"))
    assert remote.get("/api/config").json()["network"]["mode"] == "home-network"
    assert remote.post("/api/logout", headers=headers).status_code == 200
    assert remote.get("/api/config").status_code == 401
    response, _ = login(local, LOCAL, password)
    assert "Secure" not in response.headers["set-cookie"]
    assert local.get("/api/config").json()["network"]["mode"] == "this-computer"


def test_host_origin_spoofing_and_cross_origin_requests_rejected(network):
    _, local, remote, password = network
    _, headers = login(remote, REMOTE, password)
    for origin in (LOCAL, "https://attacker.home.arpa", "null"):
        assert remote.post("/api/logout", headers=headers | {"Origin": origin}).status_code == 403
    assert remote.post("/api/logout").status_code == 403
    assert remote.get("/healthz", headers={"Host": "attacker.home.arpa", "X-Forwarded-Host": "stackarr.home.arpa:29443"}).status_code == 400
    assert remote.get("/healthz", headers=[("Host", "stackarr.home.arpa:29443"), ("Host", "localhost:29123")]).status_code == 400
    response, _ = login(local, LOCAL, password)
    assert "Secure" not in response.headers["set-cookie"]


def test_remote_links_do_not_rewrite_saved_configuration(network):
    app, local, remote, password = network
    revision, config = app.state.store.config()
    for key in ("plex", "sonarr"):
        config.integrations[key].enabled = True
        config.integrations[key].url = "http://127.0.0.1:30101"
    app.state.store.save(config, revision)
    login(remote, REMOTE, password)
    login(local, LOCAL, password)
    rows = {r["id"]: r for r in remote.get("/api/status").json()["integrations"]}
    assert rows["plex"]["url"] == "https://plex.home.arpa:29443"
    assert rows["sonarr"]["url"] == ""
    rows = {r["id"]: r for r in local.get("/api/status").json()["integrations"]}
    assert rows["plex"]["url"] == "http://127.0.0.1:30101"
    assert app.state.store.config()[1] == config
    assert browser_routes.get() is None


@pytest.mark.parametrize("origin,links", [
    ("http://server.home.arpa", {}), ("https://user:secret@server.home.arpa", {}),
    ("https://server.home.arpa/path", {}), ("https://server.home.arpa?token=secret", {}),
    ("https://localhost", {}), ("https://server.home.arpa", {"plex": "https://server.home.arpa:32443"}),
    (REMOTE, {"plex": "http://plex.home.arpa"}), ("", {"plex": "https://plex.home.arpa"}),
    (REMOTE, {"plex": "https://apps.home.arpa", "seerr": "https://apps.home.arpa:444"}),
])
def test_invalid_or_cookie_sharing_routes_rejected(origin, links):
    with pytest.raises(ValueError):
        LanAccess(LOCAL, {"STACKARR_LAN_ORIGIN": origin, "STACKARR_LAN_LINKS": json.dumps(links)})


def test_background_routes_are_not_changed_by_request_context():
    assert browser_url("plex", "http://localhost") == "http://localhost"
    token = browser_routes.set({})
    try:
        assert browser_url("plex", "http://localhost") == ""
    finally:
        browser_routes.reset(token)
    assert browser_url("plex", "http://localhost") == "http://localhost"
