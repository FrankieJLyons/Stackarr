import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from stackarr import native_import, onboarding
from stackarr.home import Home, HomeError
from stackarr.native_import import NativeImporter, NativeImportError, connect
from stackarr.server import create_app
from stackarr.store import Conflict, Store
from tests.test_controller_dashboard import authorize


@pytest.fixture
def native(tmp_path):
    program_data = tmp_path / "ProgramData"
    for name in ("Sonarr", "Radarr", "Prowlarr"):
        directory = program_data / name
        directory.mkdir(parents=True)
        (directory / "config.xml").write_text('<Config><ApiKey>' + 'a'*32 + '</ApiKey><Port>8989</Port><UrlBase>/arr</UrlBase></Config>')
    calls = []
    data = {
        "rootfolder": [{"id": 1, "path": "D:\\TV", "freeSpace": 123}],
        "qualityprofile": [{"id": 7, "name": "My custom profile", "upgradeAllowed": True,
                            "items": [{"quality": {"id": 1, "name": "SDTV"}, "allowed": True}]}],
        "downloadclient": [{"id": 2, "name": "Existing downloads", "implementation": "QBittorrent", "enable": True,
                            "fields": [{"name": "password", "value": "never-expose-password"}]}],
        "indexer": [{"id": 5, "name": "Existing source", "implementation": "Torznab", "enable": True,
                     "fields": [{"name": "apiKey", "value": "never-expose-provider-key"}]}],
        "applications": [{"id": 1, "name": "Sonarr", "implementation": "Sonarr", "syncLevel": "addOnly"}],
    }
    identity = {"app": "sonarr", "wrong_folder": False, "redirect": False}

    def reply(request):
        calls.append(request)
        assert request.method == "GET", "Native import may only read from the existing app"
        assert request.headers["X-Api-Key"] == 'a'*32
        if request.url.host == "host.docker.internal":
            assert request.headers["Host"] == "127.0.0.1:8989"
        if identity["redirect"]:
            return httpx.Response(302, headers={"Location": "http://elsewhere.invalid/"})
        if request.url.path.endswith("system/status"):
            name = identity["app"].capitalize()
            return httpx.Response(200, json={"appName": name, "version": "4.0.0", "appData":
                str(program_data / name) if not identity["wrong_folder"] else "/config"})
        return httpx.Response(200, json=data[request.url.path.rsplit("/", 1)[1]])

    transport = httpx.MockTransport(reply)
    importer = NativeImporter(enabled=True, program_data=program_data, transport=transport)
    return importer, transport, calls, data, identity


def run(awaitable):
    return asyncio.run(awaitable)


def test_review_is_redacted_and_import_is_atomic_encrypted_read_only(tmp_path, native):
    importer, transport, calls, _, _ = native
    review = run(importer.review("sonarr"))
    assert 'a'*32 not in json.dumps(review)
    assert "never-expose" not in json.dumps(review)
    assert review["snapshot"]["quality_profiles"][0]["name"] == "My custom profile"
    store = Store(tmp_path / "stackarr")
    onboarding.initialize(store)
    bundle = run(importer.redeem(review["review_reference"]))
    result = run(connect(store, bundle, 1, review["snapshot"], transport=transport))
    assert result["read_only"] and result["state"] == "connected"
    assert store.secret("sonarr") == {"api_key": 'a'*32}
    assert b'never-expose' not in store.path.read_bytes()
    assert ('a'*32).encode() not in store.path.read_bytes()
    app = store.config()[1].integrations["sonarr"]
    assert (app.mode, app.read_only, app.url, app.quality_profile) == ("connect", True, "http://127.0.0.1:8989/arr", "")
    draft = onboarding.read(store)["draft"]
    assert draft["choices"]["sonarr"]["mode"] == "connect"
    assert native_import.imported(store) == [review["snapshot"]]
    assert all(request.method == "GET" for request in calls)
    with pytest.raises(Conflict):
        run(importer.redeem(review["review_reference"]))


@pytest.mark.parametrize("change", ["config", "settings", "expired", "identity"])
def test_review_rejects_changes(native, change):
    importer, _, _, data, identity = native
    review = run(importer.review("sonarr"))
    if change == "config":
        path = importer.root / "Sonarr" / "config.xml"
        path.write_text(path.read_text().replace("8989", "8990"))
    elif change == "settings":
        data["downloadclient"][0]["fields"][0]["value"] = "rotated-private-password"
    elif change == "expired":
        importer.clock = lambda: float('inf')
    else:
        identity["wrong_folder"] = True
    with pytest.raises((Conflict, NativeImportError)):
        run(importer.redeem(review["review_reference"]))


def test_free_space_changes_do_not_invalidate_review(native):
    importer, _, _, data, _ = native
    review = run(importer.review("sonarr"))
    data["rootfolder"][0]["freeSpace"] += 100
    assert run(importer.redeem(review["review_reference"]))["credential"]


@pytest.mark.parametrize("xml", [
    '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///private">]><Config/>',
    '<Config><ApiKey>' + 'a'*32 + '</ApiKey><Port>8989</Port><UrlBase>//other-host</UrlBase></Config>',
    '<Config><ApiKey>' + 'a'*32 + '</ApiKey><Port>8989</Port><UrlBase>/%2e%2e</UrlBase></Config>',
    'x'*65537,
], ids=["entity", "authority", "encoded-path", "size"])
def test_unsafe_config_never_sends_credentials(native, xml):
    importer, _, calls, _, _ = native
    (importer.root / "Sonarr" / "config.xml").write_text(xml)
    with pytest.raises(NativeImportError):
        run(importer.inspect("sonarr"))
    assert not calls


def test_docker_identity_and_redirect_not_accepted(native):
    importer, _, calls, _, identity = native
    identity["wrong_folder"] = True
    with pytest.raises(NativeImportError, match="folder"):
        run(importer.inspect("sonarr"))
    assert len(calls) == 1
    identity["redirect"] = True
    with pytest.raises(NativeImportError):
        run(importer.inspect("sonarr"))
    assert len(calls) == 2


def test_existing_connections_and_concurrent_settings_are_preserved(tmp_path, native):
    importer, transport, _, _, _ = native
    bundle = run(importer.inspect("sonarr"))
    store = Store(tmp_path / "stackarr")
    onboarding.initialize(store)
    revision, config = store.config()
    config.integrations["sonarr"].url = "http://other-existing-app:8989"
    store.save(config, revision, {"sonarr": {"api_key": "previous-secret"}})
    with pytest.raises(Conflict, match="different"):
        run(connect(store, bundle, 2, bundle["snapshot"], transport=transport))
    assert store.secret("sonarr") == {"api_key": "previous-secret"}
    assert native_import.imported(store) == []
    config.integrations["sonarr"].url = ""
    store.save(config, 2, {"sonarr": None})
    with pytest.raises(Conflict, match="settings changed"):
        run(connect(store, bundle, 2, bundle["snapshot"], transport=transport))
    assert not store.secret("sonarr")


def test_remote_route_and_repeat_import(tmp_path, native):
    importer, transport, calls, _, _ = native
    store = Store(tmp_path / "stackarr")
    onboarding.initialize(store)
    bundle = run(importer.inspect("sonarr"))
    run(connect(store, bundle, 1, bundle["snapshot"], remote=True, transport=transport))
    assert calls[-1].url.host == "host.docker.internal"
    assert calls[-1].headers["Host"] == "127.0.0.1:8989"
    assert store.config()[1].integrations["sonarr"].request_host == "127.0.0.1:8989"
    assert store.config()[1].integrations["sonarr"].browser_url == "http://127.0.0.1:8989/arr"
    assert run(connect(store, bundle, 2, bundle["snapshot"], remote=True, transport=transport))["revision"] == 3


def test_prowlarr_fields_are_never_disclosed(native):
    importer, _, _, _, identity = native
    identity["app"] = "prowlarr"
    review = run(importer.review("prowlarr"))
    assert len(review["snapshot"]["sources"]) == 1
    assert len(review["snapshot"]["linked_apps"]) == 1
    assert "never-expose" not in json.dumps(review)


def test_browser_review_session_csrf_and_redaction(tmp_path, monkeypatch, native):
    importer, transport, _, _, _ = native
    monkeypatch.setattr(native_import, "NativeImporter", lambda **kwargs: importer)
    app = create_app(tmp_path / "dashboard", origin="http://testserver", background=False, host_checks=True, transport=transport)
    with TestClient(app) as browser:
        assert browser.post("/api/native-imports/scan").status_code in {401, 403}
        headers = authorize(browser, app)
        assert browser.post("/api/native-imports/scan", headers={"Origin": "http://testserver"}).status_code == 403
        review = browser.post("/api/native-imports/review", headers=headers, json={"app": "sonarr"})
        assert review.status_code == 200
        assert "review_reference" not in review.json()
        assert 'a'*32 not in review.text and "never-expose" not in review.text
        payload = {"review_token": review.json()["review_token"]}
        with TestClient(app) as other:
            login = other.post("/api/login", headers={"Origin": "http://testserver"}, json={"password": "synthetic test password"})
            response = other.post("/api/native-imports/apply", json=payload, headers={"Origin": "http://testserver", "X-CSRF-Token": login.json()["csrf"]})
            assert response.status_code == 409
        result = browser.post("/api/native-imports/apply", headers=headers, json=payload)
        assert result.status_code == 200, result.text
        assert 'a'*32 not in result.text and "never-expose" not in result.text
        assert browser.post("/api/native-imports/apply", headers=headers, json=payload).status_code == 409
        assert len(browser.get("/api/native-imports").json()["apps"]) == 1


def test_read_only_enforced_at_write_boundaries(tmp_path):
    from stackarr.indexers import apply, validate
    from stackarr.wiring import WiringError, apply_plan

    store = Store(tmp_path / "stackarr")
    revision, config = store.config()
    for key in ("sonarr", "prowlarr"):
        config.integrations[key].enabled = True
        config.integrations[key].url = "http://127.0.0.1:8989"
        config.integrations[key].read_only = True
    store.save(config, revision)
    with pytest.raises(ValueError, match="read-only"):
        run(apply(store, {}))
    with pytest.raises(ValueError, match="read-only"):
        run(validate(store, {}))
    with pytest.raises(WiringError, match="read-only"):
        run(apply_plan(store, {"revision": 2, "changes": [{"source": "qbittorrent", "target": "sonarr"}]}))
    with pytest.raises(HomeError, match="read-only"):
        run(Home(store).call("/api/v1/request", method="POST"))
    config.integrations["sonarr"].read_only = False
    with pytest.raises(ValueError, match="read-only"):
        store.save(config, 2)


def test_private_controller_handoff_and_path_rejection(tmp_path, native):
    from stackarr.controller import InstallationController
    from stackarr.controller_transport import (
        ControllerClient,
        ControllerConnectionError,
        create_controller_app,
    )

    importer, _, _, _, _ = native
    controller = InstallationController(Store(tmp_path / "controller"), [], 28000)
    controller.native_importer = importer
    key = bytes(range(32))
    app = create_controller_app(controller, key, "127.0.0.1:28010", run_worker=False)

    async def check():
        transport = httpx.ASGITransport(app)
        client = ControllerClient("http://127.0.0.1:28010", key, transport=transport)
        with pytest.raises(ControllerConnectionError):
            await client.request("native-review", {"app": "sonarr", "path": "C:/private"})
        with pytest.raises(ControllerConnectionError):
            await client.request("native-review", {"app": "../private"})
        review = await client.request("native-review", {"app": "sonarr"})
        assert "credential" not in review
        bundle = await client.request("native-redeem", {"review_reference": review["review_reference"]})
        assert bundle["credential"] == {"api_key": 'a'*32}
        with pytest.raises(ControllerConnectionError):
            await client.request("native-redeem", {"review_reference": review["review_reference"]})
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:28010") as browser:
            response = await browser.post("/v1/native-redeem", json={"review_reference": review["review_reference"]})
            assert response.status_code == 401 and 'a'*32 not in response.text
    run(check())


def test_native_host_routing_is_limited_and_used_by_status(tmp_path):
    from stackarr.config import Integration
    from stackarr.integrations import collect

    with pytest.raises(ValueError):
        Integration(read_only=True, url="http://host.docker.internal:8989", request_host="other-host:8989")
    with pytest.raises(ValueError):
        Integration(read_only=True, url="http://remote.example:8989", request_host="127.0.0.1:8989")
    with pytest.raises(ValueError):
        Integration(read_only=True, url="http://host.docker.internal:8990", request_host="127.0.0.1:8989")
    app = Integration(enabled=True, read_only=True, url="http://host.docker.internal:8989", request_host="127.0.0.1:8989")

    def reply(request):
        assert request.method == "GET"
        assert request.headers['Host'] == '127.0.0.1:8989'
        if request.url.path.endswith('/system/status'):
            return httpx.Response(200, json={'version': '4.0'})
        return httpx.Response(200, json=[] if request.url.path.endswith('/health') else {'records': []})
    assert run(collect('sonarr', app, {'api_key': 'a'*32}, httpx.MockTransport(reply)))


def test_existing_native_source_links_use_windows_addresses(tmp_path):
    from stackarr.config import Integration
    from stackarr.indexers import status

    store = Store(tmp_path / 'dashboard')
    revision, config = store.config()
    for app, port in [('sonarr', 8989), ('prowlarr', 9696)]:
        config.integrations[app] = Integration(enabled=True, read_only=True, url=f'http://host.docker.internal:{port}',
                                               browser_url=f'http://127.0.0.1:{port}', request_host=f'127.0.0.1:{port}')
    store.save(config, revision, {app: {'api_key': 'a'*32} for app in ('sonarr', 'prowlarr')})

    def reply(request):
        assert request.method == 'GET'
        assert request.headers['Host'] == f'127.0.0.1:{request.url.port}'
        if request.url.port == 9696:
            return httpx.Response(200, json=[{'name': 'Source', 'enable': True}])
        return httpx.Response(200, json=[{'implementation': 'Torznab', 'fields': [{'name': 'baseUrl', 'value': url}]}
            for url in ('http://localhost:9696', 'http://127.0.0.1:9696', 'http://other-host:9696', 'http://localhost:19696')])
    result = run(status(store, httpx.MockTransport(reply)))
    assert result['apps'][0]['shared_sources'] == 2
