import json
from urllib.parse import parse_qs

import httpx
import pytest
from test_deployment_check import installed as installed

from stackarr.arr_logins import prepare, read
from stackarr.bootstrap import BootstrapError
from stackarr.config import Config
from stackarr.web_logins import apply, initialize, public, reveal, review

KEY = "a" * 32


def fixture(installed):
    deployment, identity, info, _ = installed
    service = dict(json.loads((deployment.store.root / "deployments" / identity / "compose.json").read_text())["services"]["plex"])
    service["image"] = "synthetic-sonarr-image"
    service["ports"] = [{"target": 8989, "published": "38989", "host_ip": "127.0.0.1", "protocol": "tcp"}]
    service["volumes"][1]["read_only"] = False
    info["Config"]["Image"] = service["image"]
    info["Config"]["Labels"]["com.docker.compose.service"] = "sonarr"
    info["Mounts"][0]["Name"] = "stackarr-owned-" + identity + "_sonarr-config"
    info["Mounts"][1]["RW"] = True
    info["HostConfig"]["PortBindings"] = {"8989/tcp": [{"HostIp": "127.0.0.1", "HostPort": "38989"}]}
    payload = {"apps": ["sonarr"], "compose": {"services": {"sonarr": service}}, "context": deployment.context()}
    return deployment, identity, payload, info


def test_lost_response_recovers_generated_login_without_resetting_it(installed):
    deployment, identity, payload, _ = fixture(installed)
    state = {"id": 1, "apiKey": KEY, "authenticationMethod": "none", "authenticationRequired": "enabled", "username": "", "password": ""}
    writes = []

    def response(request):
        if request.url.path == "/login":
            assert "X-Api-Key" not in request.headers
            values = parse_qs(request.content.decode())
            valid = values["password"][0] == state["password"]
            return httpx.Response(302, headers={"location": "/" if valid else "/login?loginFailed=true",
                                               "set-cookie": "fixture_auth=accepted; Path=/"})
        if request.url.path == "/":
            assert request.headers.get("cookie") == "fixture_auth=accepted"
            return httpx.Response(200, text="fixture app")
        assert request.headers["X-Api-Key"] == KEY
        if request.method == "GET":
            return httpx.Response(200, json=state.copy())
        assert request.method == "PUT" and request.url.path.endswith("/config/host/1")
        state.update(json.loads(request.content))
        writes.append(state["password"])
        raise httpx.ReadError("synthetic lost response after applying")

    transport = httpx.MockTransport(response)
    with pytest.raises(BootstrapError):
        prepare(deployment, identity, payload, {"sonarr": {"api_key": KEY}}, transport)
    result = prepare(deployment, identity, payload, {"sonarr": {"api_key": KEY}}, transport)
    assert result["apps"]["sonarr"]["state"] == "ready" and len(writes) == 1
    assert writes[0].encode() not in deployment.store.path.read_bytes()
    assert read(deployment, identity, payload, "sonarr", KEY, transport)["password"] == writes[0]
    state["password"] = "later-owner-password"
    result = prepare(deployment, identity, payload, {"sonarr": {"api_key": KEY}}, transport)
    assert result["apps"]["sonarr"]["state"] == "existing" and result["apps"]["sonarr"]["login"] is None
    assert read(deployment, identity, payload, "sonarr", KEY, transport) is None and len(writes) == 1


def test_foreign_container_stops_before_reading_or_writing_credentials(installed):
    deployment, identity, payload, info = fixture(installed)
    info["Mounts"][0]["Name"] = "foreign-config"
    calls = []
    with pytest.raises(BootstrapError):
        prepare(deployment, identity, payload, {"sonarr": {"api_key": KEY}}, httpx.MockTransport(lambda request: calls.append(request)))
    assert not calls


@pytest.fixture
def dashboard_login(tmp_path):
    from stackarr.store import Store

    store, identity = Store(tmp_path), "b" * 32
    config = Config()
    config.integrations["sonarr"].enabled = True
    config.integrations["sonarr"].url = "http://host.docker.internal:38989"
    store.save(config, 1, {"sonarr": {"api_key": KEY}})
    with store.db() as db:
        db.execute("CREATE TABLE controller_connections(id TEXT PRIMARY KEY,revision INTEGER,ports TEXT,activated INTEGER)")
        db.execute("INSERT INTO controller_connections VALUES(?,?,?,1)", (identity, store.config()[0], json.dumps({"sonarr": 38989})))
    initialize(store)
    return store, identity


async def test_dashboard_login_handoff_is_encrypted_and_reveal_checks_live_ownership(dashboard_login):
    store, identity = dashboard_login
    login = {"username": "stackarr", "password": "synthetic-generated-password-value-12345"}
    calls = []

    class Remote:
        async def request(self, operation, payload):
            calls.append(operation)
            if operation == "arr-logins":
                return {"id": identity, "apps": {"sonarr": {"port": 38989, "api_key": KEY, "state": "ready", "login": login}}}
            return {"id": identity, "app": "sonarr", "port": 38989, "api_key": KEY, "login": login}

    remote, plan = Remote(), review(store, identity)
    assert KEY not in json.dumps(public(plan))
    result = await apply(store, remote, plan)
    assert login["password"] not in json.dumps(result) and login["password"].encode() not in store.path.read_bytes()
    assert await reveal(store, remote, "sonarr") == login
    assert calls == ["arr-logins", "arr-login"]
    revision, config = store.config()
    store.save(config, revision, {"sonarr": {"api_key": "owner-changed-key"}})
    with pytest.raises(ValueError):
        await reveal(store, remote, "sonarr")
    assert calls == ["arr-logins", "arr-login"]
