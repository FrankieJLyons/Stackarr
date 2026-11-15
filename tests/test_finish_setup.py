import asyncio
import json

import httpx
import pytest
from test_deployment_check import installed as installed

from stackarr.finish_setup import FILES, LIMIT, finish, read_candidate
from stackarr.server import create_app


def prepare(installed, monkeypatch, raw='<Preferences PlexOnlineToken="test-plex-key"/>'):
    service, identity, info, calls = installed
    info["Id"] = "b" * 64
    revision, config = service.store.config()
    config.integrations["plex"].enabled = True
    config.integrations["plex"].url = "http://127.0.0.1:32400"
    service.store.save(config, revision)

    def command(args, **kwargs):
        calls.append(args)
        return raw if "exec" in args else json.dumps([info])

    monkeypatch.setattr(service, "_call", command)
    return service, identity, calls


def plex_api(request):
    assert request.headers["X-Plex-Token"] == "test-plex-key"
    return httpx.Response(200, json={"MediaContainer": {"size": 0, "Metadata": []}})


async def test_finish_encrypts_verified_key_and_never_returns_it(installed, monkeypatch):
    service, identity, calls = prepare(installed, monkeypatch)
    result = await finish(service, identity, httpx.MockTransport(plex_api))
    assert result["apps"][0]["state"] == "connected"
    assert service.store.secret("plex") == {"api_key": "test-plex-key"}
    assert "test-plex-key" not in json.dumps(result)
    assert b"test-plex-key" not in service.store.path.read_bytes()
    assert calls[-1] == ["--context", "fixture", "exec", "b" * 64, "head", "-c", str(LIMIT + 1), FILES["plex"]]
    calls.clear()
    assert (await finish(service, identity))["apps"][0]["state"] == "saved"
    assert not calls


@pytest.mark.parametrize("raw,expected", [
    ('<Preferences/>', "needs-setup"),
    ('not xml private information', "check-needed"),
    ('x' * (LIMIT + 1), "check-needed"),
    ('<!DOCTYPE x><Preferences/>', "check-needed"),
], ids=["unclaimed", "malformed", "oversized", "doctype"])
async def test_incomplete_or_invalid_settings_are_safe(installed, monkeypatch, raw, expected):
    service, identity, _ = prepare(installed, monkeypatch, raw)
    result = await finish(service, identity)
    assert result["apps"][0]["state"] == expected
    assert not service.store.secret("plex")
    assert "private information" not in json.dumps(result)


async def test_changed_connection_never_reads_credentials(installed, monkeypatch):
    service, identity, calls = prepare(installed, monkeypatch)
    revision, config = service.store.config()
    config.integrations["plex"].url = "http://other-server:32400"
    service.store.save(config, revision)
    assert (await finish(service, identity))["apps"][0]["state"] == "check-needed"
    assert not calls


async def test_disabled_optional_app_is_skipped_without_failure(installed, monkeypatch):
    service, identity, calls = prepare(installed, monkeypatch)
    revision, config = service.store.config()
    config.integrations["plex"].enabled = False
    service.store.save(config, revision)
    assert (await finish(service, identity))["apps"] == []
    assert not calls


async def test_changed_container_never_reads_credentials(installed, monkeypatch):
    service, identity, calls = prepare(installed, monkeypatch)
    installed[2]["Config"]["Image"] = "foreign"
    assert (await finish(service, identity))["apps"][0]["state"] == "check-needed"
    assert not any("exec" in call for call in calls)


async def test_settings_race_keeps_newer_credentials(installed, monkeypatch):
    service, identity, _ = prepare(installed, monkeypatch)

    def response(request):
        revision, config = service.store.config()
        service.store.save(config, revision, {"plex": {"api_key": "user-saved-secret"}})
        return plex_api(request)

    result = await finish(service, identity, httpx.MockTransport(response))
    assert result["apps"][0]["state"] == "changed"
    assert service.store.secret("plex")["api_key"] == "user-saved-secret"


async def test_rejected_key_is_not_saved(installed, monkeypatch):
    service, identity, _ = prepare(installed, monkeypatch)
    result = await finish(service, identity, httpx.MockTransport(lambda request: httpx.Response(401)))
    assert result["apps"][0]["state"] == "waiting"
    assert not service.store.secret("plex")


@pytest.mark.parametrize("initialized,expected", [(False, None), (True, {"api_key": "synthetic-seerr-secret"})])
def test_seerr_requires_completed_account_setup(installed, monkeypatch, initialized, expected):
    from stackarr import finish_setup

    service, identity, info, calls = installed
    info["Id"] = "b" * 64
    monkeypatch.setattr(finish_setup, "differences", lambda *args: [])
    monkeypatch.setattr(finish_setup, "inspect_container", lambda *args: info)
    monkeypatch.setattr(service, "_call", lambda *args, **kwargs: json.dumps({"public": {"initialized": initialized}, "main": {"apiKey": "synthetic-seerr-secret"}}))
    config = service.store.config()[1]
    app = config.integrations["seerr"]
    app.enabled, app.url = True, "http://127.0.0.1:5055"
    payload = {"context": {"name": "fixture"}, "compose": {"services": {"seerr": {"ports": [{"published": "5055"}]}}}}
    assert read_candidate(service, identity, payload, "seerr", app) == expected


def test_container_dashboard_cannot_read_host_credentials(client, auth):
    endpoint = "/api/deployments/" + "a" * 32 + "/finish-connecting"
    assert client.post(endpoint).status_code == 403
    assert client.post(endpoint, headers=auth).status_code == 409


async def test_authenticated_finish_blocks_competing_changes(installed, monkeypatch):
    from stackarr import finish_setup

    service, identity, _ = prepare(installed, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def verify(*args):
        entered.set()
        await release.wait()

    monkeypatch.setattr(finish_setup, "collect", verify)
    origin = "http://localhost:8787"
    app = create_app(service.store.root, origin=origin, host_checks=True, host_install=True, background=False)
    monkeypatch.setattr(app.state.deployments, "context", service.context)
    monkeypatch.setattr(app.state.deployments, "_call", service._call)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin, headers={"Origin": origin}) as client:
        password = "synthetic test password"
        result = await client.post("/api/setup", json={"password": password, "setup_token": (service.store.root / "setup-token").read_text()})
        assert result.status_code == 200
        login = await client.post("/api/login", json={"password": password})
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        endpoint = "/api/deployments/" + identity + "/finish-connecting"
        pending = asyncio.create_task(client.post(endpoint))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            assert (await client.post(endpoint)).status_code == 409
            assert (await client.post("/api/deployments/install", json={"review_token": "a" * 43})).status_code == 409
            assert (await client.post("/api/deployments/" + identity + "/resume")).status_code == 409
            assert (await client.post("/api/deployments/actions/apply", json={"review_token": "a" * 43})).status_code == 409
        finally:
            release.set()
            result = await pending
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["apps"][0]["state"] == "connected"
        assert "test-plex-key" not in result.text
