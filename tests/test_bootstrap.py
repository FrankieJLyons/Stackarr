import json
from urllib.parse import parse_qs

import httpx
import pytest

from stackarr.bootstrap import credentials
from stackarr.deployment import DeploymentError, Deployments
from stackarr.store import Store


def test_qbit_password_checkpoint_recovers_lost_response_without_rewriting(tmp_path, monkeypatch):
    deployment = Deployments(Store(tmp_path))
    monkeypatch.setattr(deployment, "owned_container", lambda *args: "owned-fixture")
    monkeypatch.setattr(deployment, "_call", lambda *args, **kwargs: "temporary password is provided for this session: temporary-fixture")
    state = {"password": "temporary-fixture", "writes": 0}

    def respond(request):
        fields = parse_qs(request.content.decode())
        if request.url.path == "/":
            return httpx.Response(200)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(204 if fields["password"][0] == state["password"] else 401)
        if request.url.path.endswith("/setPreferences"):
            state["password"] = json.loads(fields["json"][0])["web_ui_password"]
            state["writes"] += 1
            raise httpx.ReadError("synthetic lost response")
        assert request.url.path.endswith("/torrents/info")
        return httpx.Response(200, json=[])

    client = httpx.Client
    monkeypatch.setattr("stackarr.bootstrap.httpx.Client", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    payload = {"context": {"name": "fixture"}, "apps": ["qbittorrent"], "compose": {
        "services": {"qbittorrent": {"ports": [{"published": "38080"}]}}}}
    with pytest.raises(httpx.ReadError):
        credentials(deployment, "fixture", payload)
    with deployment.store.db() as db:
        encrypted = db.execute("SELECT value FROM deployment_secrets WHERE id='fixture'").fetchone()[0]
    assert state["password"].encode() not in encrypted
    recovered = credentials(deployment, "fixture", payload)
    assert recovered["qbittorrent"]["password"] == state["password"]
    assert state["writes"] == 1


def test_credential_read_requires_owned_config_volume(tmp_path, monkeypatch):
    deployment = Deployments(Store(tmp_path))
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        return json.dumps([{"Config": {"Labels": {"com.docker.compose.project": "foreign", "com.docker.compose.service": "sonarr"}}}])
    monkeypatch.setattr(deployment, "_call", command)
    payload = {"context": {"name": "fixture"}, "apps": ["sonarr"]}
    with pytest.raises(DeploymentError, match="ownership"):
        credentials(deployment, "a" * 32, payload)
    assert len(calls) == 1 and "inspect" in calls[0]


@pytest.mark.asyncio
async def test_wiring_separates_host_api_from_app_peer_address(tmp_path):
    from stackarr.config import Config
    from stackarr.wiring import build_plan

    store = Store(tmp_path)
    config = Config().model_dump()
    for key, port in (("sonarr", 38989), ("qbittorrent", 38080)):
        config["integrations"][key].update(enabled=True, url=f"http://127.0.0.1:{port}", peer_url=f"http://{key}:{port}")
    store.save(Config.model_validate(config), 1, {"sonarr": {"api_key": "synthetic"}, "qbittorrent": {"username": "admin", "password": "synthetic"}})

    def respond(request):
        assert request.url.host == "127.0.0.1"  # Stackarr can reach the published host API.
        if request.url.path.endswith("/schema"):
            return httpx.Response(200, json=[{"implementation": "QBittorrent", "fields": [
                {"name": name} for name in ("host", "port", "username", "password", "tvCategory")]}])
        return httpx.Response(200, json=[])

    result = await build_plan(store, httpx.MockTransport(respond))
    fields = {f["name"]: f["value"] for f in result["changes"][0]["payload"]["fields"]}
    assert fields["host"] == "qbittorrent"  # Sonarr reaches its peer through the private network.
    assert fields["port"] == 38080
