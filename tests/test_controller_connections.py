import json

import httpx
import pytest
from fastapi.testclient import TestClient
from test_controller_dashboard import authorize, dashboard
from test_deployment_check import installed as installed
from test_finish_setup import prepare

from stackarr.controller import InstallationController
from stackarr.controller_connections import finish_plex
from stackarr.controller_transport import ControllerClient, ControllerConnectionError, create_controller_app
from stackarr.store import Store


class Connection:
    def __init__(self, identity):
        self.calls = []
        self.reply = {"id": identity, "port": 32400, "credential": {"api_key": "synthetic-plex-key"}}

    async def request(self, operation, payload):
        self.calls.append((operation, payload))
        return self.reply


def register(store, identity):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS controller_connections (id TEXT PRIMARY KEY, revision INTEGER, ports TEXT, activated INTEGER DEFAULT 0)")
        db.execute("INSERT INTO controller_connections(id,revision,ports) VALUES(?,?,?)",
                   (identity, store.config()[0], json.dumps({"plex": 32400})))


@pytest.fixture
def handoff(tmp_path):
    store, identity = Store(tmp_path / "dashboard"), "a" * 32
    register(store, identity)
    return store, identity, Connection(identity)


def plex_api(request):
    assert request.url.host == "host.docker.internal" and request.url.port == 32400
    assert request.headers["X-Plex-Token"] == "synthetic-plex-key"
    return httpx.Response(200, json={"MediaContainer": {"size": 0, "Metadata": []}})


async def test_private_handoff_verifies_encrypts_and_is_idempotent(handoff):
    store, identity, controller = handoff
    result = await finish_plex(store, controller, identity, httpx.MockTransport(plex_api))
    assert result["apps"][0]["state"] == "connected"
    assert "synthetic-plex-key" not in json.dumps(result)
    assert b"synthetic-plex-key" not in store.path.read_bytes()
    assert store.secret("plex") == {"api_key": "synthetic-plex-key"}
    assert store.config()[1].integrations["plex"].browser_url == "http://localhost:32400/web"
    assert (await finish_plex(store, controller, identity))["apps"][0]["state"] == "saved"
    assert len(controller.calls) == 1
    revision, config = store.config()
    config.integrations["plex"].enabled = False
    store.save(config, revision)
    assert (await finish_plex(store, controller, identity))["apps"] == []
    assert len(controller.calls) == 1


async def test_unclaimed_plex_remains_unconfigured(handoff):
    store, identity, controller = handoff
    controller.reply["credential"] = None
    before = store.config()
    assert (await finish_plex(store, controller, identity))["apps"][0]["state"] == "needs-setup"
    assert store.config() == before and not store.secret("plex")


@pytest.mark.parametrize("changes", [
    {"port": 32401}, {"port": True}, {"id": "b" * 32}, {"url": "http://other.example"},
    {"credential": {"api_key": "short"}}, {"credential": {"api_key": "private\nvalue"}},
    {"credential": {"api_key": "synthetic-plex-key", "password": "unexpected"}},
])
async def test_identity_and_credential_changes_never_save(handoff, changes):
    store, identity, controller = handoff
    controller.reply.update(changes)
    with pytest.raises(ValueError):
        await finish_plex(store, controller, identity)
    assert not store.secret("plex") and not store.config()[1].integrations["plex"].enabled


async def test_existing_settings_and_inflight_edits_are_preserved(handoff):
    store, identity, controller = handoff

    def race(request):
        revision, config = store.config()
        store.save(config, revision, {"plex": {"api_key": "user-saved-secret"}})
        return plex_api(request)

    result = await finish_plex(store, controller, identity, httpx.MockTransport(race))
    assert result["apps"][0]["state"] == "changed"
    assert store.secret("plex") == {"api_key": "user-saved-secret"}
    controller.calls.clear()
    assert (await finish_plex(store, controller, identity))["apps"][0]["state"] == "changed"
    assert not controller.calls


async def test_rejected_credentials_and_unknown_installation_are_not_saved(handoff):
    store, identity, controller = handoff
    result = await finish_plex(store, controller, identity, httpx.MockTransport(lambda request: httpx.Response(401)))
    assert result["apps"][0]["state"] == "waiting" and not store.secret("plex")
    controller.calls.clear()
    with pytest.raises(ValueError):
        await finish_plex(store, controller, "b" * 32)
    assert not controller.calls


async def test_controller_handoff_uses_private_transport_and_owned_container(installed, monkeypatch):
    deployments, identity, calls = prepare(installed, monkeypatch)
    service = InstallationController(deployments.store, [], 28000, deployments=deployments)
    key = bytes(range(32))
    rpc = create_controller_app(service, key, "127.0.0.1:29010", run_worker=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=rpc), base_url="http://127.0.0.1:29010") as browser:
        assert (await browser.post("/v1/plex-connection", json={"id": identity})).status_code == 401
    client = ControllerClient("http://127.0.0.1:29010", key, httpx.ASGITransport(app=rpc))
    reply = await client.request("plex-connection", {"id": identity})
    assert reply["credential"] == {"api_key": "test-plex-key"}
    assert "test-plex-key" not in json.dumps(service.status())
    assert service.status()["operations"][0]["links"][0]["url"].endswith("/web")
    calls.clear()
    installed[2]["Config"]["Image"] = "foreign"
    with pytest.raises(ControllerConnectionError, match="Controller checks failed"):
        await client.request("plex-connection", {"id": identity})
    assert not any("exec" in call for call in calls)


def test_dashboard_endpoint_never_returns_credential(tmp_path, monkeypatch):
    app, controller = dashboard(tmp_path, monkeypatch)
    identity = "a" * 32
    register(app.state.store, identity)
    private = Connection(identity)
    original = controller.request

    async def request(operation, payload=None):
        return await private.request(operation, payload) if operation == "plex-connection" else await original(operation, payload)

    monkeypatch.setattr(controller, "request", request)
    monkeypatch.setattr("stackarr.controller_connections.collect", lambda *args: async_verified())

    async def async_verified():
        return {}

    with TestClient(app) as browser:
        headers = authorize(browser, app)
        endpoint = "/api/deployments/" + identity + "/finish-connecting"
        assert browser.post(endpoint).status_code == 403
        response = browser.post(endpoint, headers=headers)
        assert response.status_code == 200 and response.json()["apps"][0]["state"] == "connected"
        assert "synthetic-plex-key" not in response.text
        assert response.headers["cache-control"] == "no-store"
