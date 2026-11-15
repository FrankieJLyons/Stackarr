import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from test_controller_dashboard import authorize, dashboard
from test_deployment_check import installed as installed

from stackarr.config import Config
from stackarr.controller import InstallationController
from stackarr.controller_connections import finish_owned, generated_login
from stackarr.controller_transport import ControllerClient, ControllerConnectionError, create_controller_app
from stackarr.installer import compose_plan
from stackarr.store import Conflict, Store

PORTS = {"sonarr": 38989, "radarr": 37878, "prowlarr": 39696, "qbittorrent": 38080}
SECRETS = {key: {"api_key": str(index) * 32} for index, key in enumerate(PORTS, 1) if key != "qbittorrent"}
SECRETS["qbittorrent"] = {"username": "admin", "password": "synthetic-qbit-password"}


class CoreConnection:
    def __init__(self, identity):
        self.calls = []
        self.reply = {"id": identity, "apps": {key: {"port": port, "credential": SECRETS[key]} for key, port in PORTS.items()}}

    async def request(self, operation, payload):
        assert operation == "app-connections" and payload == {"id": self.reply["id"]}
        self.calls.append(operation)
        return copy.deepcopy(self.reply)


@pytest.fixture
def core_handoff(tmp_path):
    store, identity = Store(tmp_path / "dashboard"), "b" * 32
    revision, config = store.config()
    config.integrations["plex"].enabled = True
    config.integrations["plex"].url = "http://host.docker.internal:42450"
    store.save(config, revision, {"plex": {"api_key": "existing-plex-fixture"}})
    with store.db() as db:
        db.execute("CREATE TABLE controller_connections (id TEXT PRIMARY KEY, revision INTEGER, ports TEXT, activated INTEGER DEFAULT 0)")
        db.execute("INSERT INTO controller_connections(id,revision,ports) VALUES(?,?,?)", (identity, store.config()[0], json.dumps(PORTS)))
    return store, identity, CoreConnection(identity)


def core_api(request):
    assert request.url.host == "host.docker.internal" and request.url.port in PORTS.values()
    if request.url.path.endswith("/auth/login"):
        return httpx.Response(200, text="Ok.")
    if request.url.path.endswith("/system/status"):
        return httpx.Response(200, json={"version": "fixture"})
    if request.url.path.endswith(("/queue", "/blocklist")):
        return httpx.Response(200, json={"records": [], "totalRecords": 0})
    return httpx.Response(200, json=[])


async def test_atomic_encrypted_core_handoff_preserves_plex_and_repeats_safely(core_handoff):
    store, identity, remote = core_handoff
    plex = store.config()[1].integrations["plex"].model_dump()
    result = await finish_owned(store, remote, identity, httpx.MockTransport(core_api))
    assert len(result["apps"]) == 4 and {row["state"] for row in result["apps"]} == {"connected"}
    for key, port in PORTS.items():
        app = store.config()[1].integrations[key]
        assert app.enabled and app.url == app.peer_url == f"http://host.docker.internal:{port}"
        assert app.browser_url == f"http://localhost:{port}" and store.secret(key) == SECRETS[key]
        secret = SECRETS[key].get("api_key", SECRETS[key].get("password"))
        assert secret not in json.dumps(result) and secret.encode() not in store.path.read_bytes()
    assert store.config()[1].integrations["plex"].model_dump() == plex
    assert store.secret("plex") == {"api_key": "existing-plex-fixture"}
    assert {row["state"] for row in (await finish_owned(store, remote, identity))["apps"]} == {"saved"}


async def test_handoff_uses_approved_quality_after_the_setup_draft_changes(core_handoff):
    store, identity, remote = core_handoff
    with store.db() as db:
        db.execute("CREATE TABLE controller_quality_profiles (id TEXT PRIMARY KEY, profiles TEXT NOT NULL)")
        db.execute("INSERT INTO controller_quality_profiles VALUES(?,?)",
                   (identity, json.dumps({"sonarr": "HD-1080p", "radarr": "Ultra-HD"})))
    from stackarr import onboarding

    onboarding.initialize(store)
    onboarding.save(store, onboarding.SaveDraft(revision=1, draft=onboarding.SetupDraft(
        apps=["sonarr"], choices={"sonarr": onboarding.AppChoice(quality_profile="SD")})))
    result = await finish_owned(store, remote, identity, httpx.MockTransport(core_api))
    assert {row["state"] for row in result["apps"]} == {"connected"}
    config = store.config()[1]
    assert config.integrations["sonarr"].quality_profile == "HD-1080p"
    assert config.integrations["radarr"].quality_profile == "Ultra-HD"
    assert len(remote.calls) == 1
    assert await generated_login(store, remote) == SECRETS["qbittorrent"]


@pytest.mark.parametrize("change", [
    lambda reply: reply.update(id="c" * 32),
    lambda reply: reply["apps"].pop("sonarr"),
    lambda reply: reply["apps"]["radarr"].update(port=True),
    lambda reply: reply["apps"]["sonarr"].update(port=38990),
    lambda reply: reply["apps"]["prowlarr"].update(credential={"api_key": "invalid"}),
    lambda reply: reply["apps"]["qbittorrent"].update(credential={"username": "admin", "password": "bad\nvalue"}),
    lambda reply: reply["apps"]["qbittorrent"].update(url="http://foreign.example"),
])
async def test_malformed_handoff_never_saves_partial_credentials(core_handoff, change):
    store, identity, remote = core_handoff
    before = store.config()
    change(remote.reply)
    # The fake transport checks the request identity independently of its reply.
    async def malformed(*args):
        return remote.reply
    remote.request = malformed
    with pytest.raises(ValueError):
        await finish_owned(store, remote, identity, httpx.MockTransport(core_api))
    assert store.config() == before and store.secret_names() == ["plex"]


async def test_failed_app_does_not_block_ready_apps_and_retry(core_handoff):
    store, identity, remote = core_handoff
    result = await finish_owned(store, remote, identity, httpx.MockTransport(
        lambda request: httpx.Response(401) if request.url.port == PORTS["radarr"] else core_api(request)))
    assert {row['app']: row['state'] for row in result['apps']} == {
        'sonarr': 'connected', 'radarr': 'waiting', 'prowlarr': 'connected', 'qbittorrent': 'connected'}
    assert not store.secret('radarr') and store.secret('qbittorrent')
    # Progress and ownership survive a dashboard restart and unrelated settings edits.
    store = Store(store.root)
    revision, config = store.config()
    config.dashboard.page_size = 25
    store.save(config, revision)
    result = await finish_owned(store, remote, identity, httpx.MockTransport(core_api))
    assert [row['state'] for row in result['apps']] == ['saved','connected','saved','saved']
    assert await generated_login(store, remote) == SECRETS['qbittorrent']


async def test_concurrent_edit_preserves_all_settings(core_handoff):
    store, identity, remote = core_handoff

    def race(request):
        revision, config = store.config()
        store.save(config, revision, {"sonarr": {"api_key": "later-user-setting"}})
        return core_api(request)

    result = await finish_owned(store, remote, identity, httpx.MockTransport(race))
    assert {row["state"] for row in result["apps"]} == {"changed"}
    assert store.secret("sonarr") == {"api_key": "later-user-setting"}
    assert not store.secret("radarr") and not store.secret("qbittorrent")


async def test_unfinished_accounts_and_native_import_do_not_block_core_apps(core_handoff):
    from stackarr.controller_connections import progress, refresh_ports
    from stackarr.web_logins import review

    store, identity, remote = core_handoff
    with store.db() as db:
        db.execute('UPDATE controller_connections SET ports=?', (json.dumps({**PORTS, 'seerr': 35055}),))
    original = remote.request
    async def accounts(operation, payload):
        if operation == 'seerr-connection':
            return {'id': identity, 'port': 35055, 'credential': None}
        return await original(operation, payload)
    remote.request = accounts
    result = await finish_owned(store, remote, identity, httpx.MockTransport(core_api))
    assert [row['state'] for row in result['apps']] == ['connected'] * 4 + ['needs-setup']
    assert set(review(store, identity)['ports']) == {'sonarr','radarr','prowlarr'}
    assert await generated_login(store, remote) == SECRETS['qbittorrent']
    # A partial completion locks the recorded ports just like a completed group.
    refresh_ports(store, [{'id': identity, 'port_recovery': True, 'apps': list(PORTS) + ['seerr'],
                         'ports': {**PORTS, 'sonarr': 50000, 'seerr': 35055}}])
    from stackarr.controller_connections import binding
    assert binding(store, identity)[1]['sonarr'] == PORTS['sonarr']
    # A subsequent native import replaces the dashboard connection, not the owned app.
    revision, config = store.config()
    config.integrations['sonarr'].url = 'http://native.test'
    config.integrations['sonarr'].read_only = True
    store.save(config, revision, {'sonarr': {'api_key': 'native-key'}})
    assert next(row for row in progress(Store(store.root), identity) if row['app'] == 'sonarr')['state'] == 'changed'
    with pytest.raises(ValueError):
        review(store, identity)
    result = await finish_owned(store, remote, identity, httpx.MockTransport(core_api))
    assert next(row for row in result['apps'] if row['app'] == 'sonarr')['state'] == 'changed'
    assert store.secret('sonarr') == {'api_key': 'native-key'}


def test_activation_failure_rolls_back_config_and_secrets(core_handoff):
    store, _, _ = core_handoff
    revision, config = store.config()
    config.integrations["sonarr"].enabled = True
    config.integrations["sonarr"].url = "http://host.docker.internal:38989"
    with pytest.raises(Conflict):
        store.save(config, revision, {"sonarr": SECRETS["sonarr"]}, complete_controller="c" * 32)
    assert store.config()[0] == revision and not store.secret("sonarr")
    assert not store.config()[1].integrations["sonarr"].enabled


def test_dashboard_handoff_and_password_protected_reveal(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    identity = "b" * 32
    with app.state.store.db() as db:
        db.execute("INSERT INTO controller_connections(id,revision,ports) VALUES(?,?,?)", (identity, app.state.store.config()[0], json.dumps(PORTS)))
    core, original = CoreConnection(identity), remote.request

    async def request(operation, payload=None):
        return await core.request(operation, payload) if operation == "app-connections" else await original(operation, payload)

    async def verified(*args):
        return {}

    monkeypatch.setattr(remote, "request", request)
    monkeypatch.setattr("stackarr.controller_connections.collect", verified)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        assert identity in browser.get("/api/deployments").json()["finish_connecting"]
        endpoint = "/api/deployments/" + identity + "/finish-connecting"
        assert browser.post(endpoint).status_code == 403
        response = browser.post(endpoint, headers=headers)
        assert response.status_code == 200 and len(response.json()["apps"]) == 4
        assert "synthetic-qbit-password" not in response.text
        assert identity not in browser.get("/api/deployments").json()["finish_connecting"]
        reveal = "/api/deployments/qbittorrent/login"
        assert browser.post(reveal, headers=headers, json={"password": "incorrect owner password"}).status_code == 403
        assert browser.post(reveal, headers=headers, json={"password": "synthetic test password"}).json() == SECRETS["qbittorrent"]


async def test_private_rpc_delivers_only_unchanged_owned_checkpoint(installed, monkeypatch):
    deployment, identity, info, calls = installed
    config = Config()
    config.storage.data_root = info["Mounts"][1]["Source"]
    app = config.integrations["qbittorrent"]
    app.enabled, app.mode, app.port = True, "install", 38080
    compose = compose_plan(config)["compose"]
    project = "stackarr-owned-" + identity
    payload = {"apps": ["qbittorrent"], "compose": compose, "context": deployment.context()}
    (deployment.store.root / "deployments" / identity / "compose.json").write_text(json.dumps(compose, sort_keys=True))
    info["Config"].update(Image=compose["services"]["qbittorrent"]["image"])
    info["Config"]["Labels"]["com.docker.compose.service"] = "qbittorrent"
    info["Mounts"][0]["Name"] = project + "_qbittorrent-config"
    info["Mounts"][1]["RW"] = True
    info["HostConfig"]["PortBindings"] = {"38080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "38080"}]}
    app.mode, app.url = "connect", "http://127.0.0.1:38080"
    deployment.store.save(config, 1, {"qbittorrent": SECRETS["qbittorrent"]})
    with deployment.store.db() as db:
        db.execute("UPDATE deployments SET payload=? WHERE id=?", (json.dumps(payload), identity))
        db.execute("INSERT INTO deployment_secrets VALUES(?,?)", (identity, deployment.store.cipher.encrypt(json.dumps({"qbittorrent": SECRETS["qbittorrent"]}).encode())))
    controller = InstallationController(deployment.store, [], 29100, deployments=deployment)
    key = b"c" * 32
    rpc = create_controller_app(controller, key, "127.0.0.1:29010", run_worker=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=rpc), base_url="http://127.0.0.1:29010") as browser:
        assert (await browser.post("/v1/app-connections", json={"id": identity})).status_code == 401
    client = ControllerClient("http://127.0.0.1:29010", key, httpx.ASGITransport(app=rpc))
    reply = await client.request("app-connections", {"id": identity})
    assert reply == {"id": identity, "apps": {"qbittorrent": {"port": 38080, "credential": SECRETS["qbittorrent"]}}}
    assert "synthetic-qbit-password" not in json.dumps(controller.status())
    info["Mounts"][0]["Name"] = "foreign-volume"
    with pytest.raises(ControllerConnectionError):
        await client.request("app-connections", {"id": identity})
    info["Mounts"][0]["Name"] = project + "_qbittorrent-config"
    revision, config = deployment.store.config()
    deployment.store.save(config, revision, {"qbittorrent": {"username": "admin", "password": "later-user-password"}})
    with pytest.raises(ControllerConnectionError):
        await client.request("app-connections", {"id": identity})
