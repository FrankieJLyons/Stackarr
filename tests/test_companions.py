import configparser
import json

import httpx
import pytest

from stackarr.companions import CLEANUP_JOBS, Companions, cleanup_safe
from stackarr.config import Integration
from stackarr.deployment import DeploymentError
from stackarr.integrations import IntegrationError, collect
from stackarr.kuma import Kuma
from stackarr.store import Conflict, Store


@pytest.mark.parametrize("unsafe", ["general", *CLEANUP_JOBS])
def test_cleanup_safety_rejects_changed_settings_without_writes(unsafe):
    def respond(request):
        assert request.method == "GET"
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={"dryRun": name != unsafe, "enabled": name == unsafe,
            "searchEnabled": name == unsafe, "proactiveSearchEnabled": False})
    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(DeploymentError):
            cleanup_safe(client)


def test_cleanup_rejects_local_authentication_bypass():
    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={"dryRun": True, "auth": {"disableAuthForLocalAddresses": True}}))) as client:
        with pytest.raises(DeploymentError):
            cleanup_safe(client)


def test_cleanup_missing_job_safety_field_fails_closed():
    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={"dryRun": True}))) as client:
        with pytest.raises(DeploymentError):
            cleanup_safe(client)


def test_changed_review_has_no_secret_or_container_writes(tmp_path, monkeypatch):
    store = Store(tmp_path)
    companions = Companions(type("Deployments", (), {"store": store})())
    monkeypatch.setattr(companions, "review", lambda identity: {"deployment": identity, "revision": 2})
    with pytest.raises(Conflict):
        companions.execute({"deployment": "a" * 32, "revision": 1})
    assert store.secret_names() == []


def test_generated_credentials_are_encrypted_and_resumable(tmp_path):
    store = Store(tmp_path)
    companions = Companions(type("Deployments", (), {"store": store})())
    state = {"apps": {"kuma": {"username": "stackarr", "password": "synthetic-private-companion-password"}}}
    companions.save("a" * 32, state)
    assert companions.state("a" * 32) == state
    assert state["apps"]["kuma"]["password"].encode() not in store.path.read_bytes()


def test_kuma_protocol_handles_ping_ack_and_rejects_arbitrary_events():
    packets = iter(['0' + json.dumps({"sid": "abcdefgh1234"}), '40', '2', '431[{"ok":true}]'])
    posted = []
    def respond(request):
        if request.method == "GET":
            return httpx.Response(200, text=next(packets))
        posted.append(request.content.decode())
        return httpx.Response(200, text="ok")
    with Kuma("http://fixture", httpx.MockTransport(respond)) as socket:
        assert socket.call("getMonitorList") == {"ok": True}
        with pytest.raises(DeploymentError):
            socket.call("deleteMonitor", 1)
    assert "3" in posted and not any("deleteMonitor" in value for value in posted)


def test_kuma_rejected_login_cannot_continue():
    packets = iter(['0' + json.dumps({"sid": "abcdefgh1234"}), '40', '431[{"ok":false,"msg":"private error"}]'])
    def respond(request):
        return httpx.Response(200, text=next(packets) if request.method == "GET" else "ok")
    with Kuma("http://fixture", httpx.MockTransport(respond)) as socket:
        with pytest.raises(DeploymentError, match="Existing accounts"):
            socket.login({"username": "stackarr", "password": "synthetic"})


async def test_tautulli_unreachable_plex_is_unavailable_not_zero_streams():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"response": {"result": "success", "data": {}}}))
    with pytest.raises(IntegrationError, match="Plex activity"):
        await collect("tautulli", Integration(enabled=True, url="http://fixture"), {"api_key": "a" * 32}, transport)


def test_tautulli_first_run_saves_token_before_connection_setup(tmp_path, monkeypatch):
    companions = Companions(type("D", (), {"store": Store(tmp_path)})())
    config = configparser.ConfigParser()
    config.read_dict({"General": {"first_run_complete": "0", "api_key": "a" * 32}, "PMS": {}})
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path == "/identity":
            return httpx.Response(200, text='<MediaContainer machineIdentifier="owned-docker-plex"/>')
        if request.url.path in {"/welcome", "/auth/login", "/settings"}:
            return httpx.Response(200, text='<meta name="csrf-token" content="synthetic-csrf-token-value">')
        if request.url.path == "/save_pms_token":
            config["PMS"]["pms_token"] = "synthetic-plex-token"
        if request.url.path == "/configUpdate":
            assert config["PMS"]["pms_token"] == "synthetic-plex-token"
            config["General"]["first_run_complete"] = "1"
            config["PMS"].update(pms_identifier="owned-docker-plex", pms_url="http://host.docker.internal:42450")
        if request.url.path == "/auth/signin":
            return httpx.Response(200, json={"status": "success"})
        if request.url.path == "/api/v2":
            data = {"pms_identifier": "owned-docker-plex"} if request.url.params["cmd"] == "get_server_info" else {"sessions": []}
            return httpx.Response(200, json={"response": {"result": "success", "data": data}})
        return httpx.Response(200, json={})
    monkeypatch.setattr(companions, "client", lambda port: httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(companions, "tautulli_config", lambda *args: config)
    monkeypatch.setattr(companions, "credential", lambda *args: {"api_key": "synthetic-plex-token"})
    record = {"username": "stackarr", "password": "synthetic-generated-password"}
    payload = {"compose": {"services": {"tautulli": {"ports": [{"published": "42465"}]}}}}
    companions.tautulli("a" * 32, payload, record, lambda: None, {"plex": {"port": 42450}})
    assert record["complete"] and record["plex_identifier"] == "owned-docker-plex"
    assert calls.index("/save_pms_token") < calls.index("/configUpdate")
