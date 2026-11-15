"""Authenticated source setup routes keep reviews private and evidence bounded."""

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

from stackarr import indexers

PRIVATE = "synthetic-private-source-secret"
PROVIDER_BODY = {"provider_id": "a" * 24, "name": "Fixture provider", "fields": {"apiKey": PRIVATE}}


def configure_source(app):
    revision, config = app.state.store.config()
    config.integrations["prowlarr"].enabled = True
    config.integrations["prowlarr"].url = "http://prowlarr.example"
    return app.state.store.save(config, revision, {"prowlarr": {"api_key": "synthetic-controller-key"}})


def plan(app):
    revision, base, key = indexers.connection(app.state.store)
    return {"revision": revision, "base": base, "key": key, "name": "Fixture provider",
            "provider": "Fixture", "exists": False,
            "payload": {"implementation": "Cardigann", "definitionName": "fixture", "name": "Fixture provider",
                        "fields": [{"name": "apiKey", "value": PRIVATE}]}}


def evidence(app, kind):
    with app.state.store.db() as db:
        row = db.execute("SELECT data FROM setup_observations WHERE kind=?", (kind,)).fetchone()
    return json.loads(row[0]) if row else None


def source_result(**changes):
    result = {"state": "results", "media_type": "movie", "query": "private media query", "sources": [
        {"id": 5, "name": "private source name", "apiKey": PRIVATE, "url": "http://private.example",
         "authentication": "passed", "categories": "supported", "search": "results", "state": "results", "result_count": 2}],
        "checked_sources": 1, "total_enabled": 1, "limited": False,
        "sharing": {"sources": [{"id": 5, "name": "private source name", "enabled": True, "apiKey": PRIVATE}],
                    "apps": [{"app": "radarr", "shared_sources": 1}, {"app": "sonarr", "shared_sources": 1}]}}
    result.update(changes)
    return result


def test_source_catalog_requires_session_and_redacts_upstream_errors(client, app, auth, monkeypatch):
    calls = []

    async def catalog(*args):
        calls.append(True)
        raise ValueError(PRIVATE + " http://private.example")

    monkeypatch.setattr(indexers, "catalog", catalog)
    response = client.get("/api/indexers/catalog")
    assert response.status_code == 409 and PRIVATE not in response.text and "private.example" not in response.text
    client.post("/api/logout", headers=auth)
    assert client.get("/api/indexers/catalog").status_code == 401 and len(calls) == 1


def test_source_catalog_success_is_read_only(client, app, auth, monkeypatch):
    async def catalog(*args):
        return {"providers": [{"id": "a" * 24, "name": "Fixture", "supported": True, "fields": []}], "notice": "Fixture"}

    monkeypatch.setattr(indexers, "catalog", catalog)
    before = app.state.store.audit_rows()
    response = client.get("/api/indexers/catalog")
    assert response.status_code == 200 and response.json()["providers"][0]["name"] == "Fixture"
    assert app.state.store.audit_rows() == before


def test_provider_review_requires_csrf_and_only_returns_public_plan(client, app, auth, monkeypatch):
    configure_source(app)
    calls = []

    async def review(*args):
        calls.append(True)
        return plan(app)

    monkeypatch.setattr(indexers, "review_provider", review)
    assert client.post("/api/indexers/providers/review", json=PROVIDER_BODY).status_code == 403
    response = client.post("/api/indexers/providers/review", json=PROVIDER_BODY, headers=auth)
    assert response.status_code == 200 and len(calls) == 1
    assert PRIVATE not in response.text and "controller-key" not in response.text and "prowlarr.example" not in response.text
    assert response.json()["provider"] == "Fixture" and response.json()["review_token"]


def test_provider_review_is_owned_by_its_session_and_token_is_consumed(client, app, auth, monkeypatch):
    configure_source(app)
    calls = []

    async def review(*args):
        return plan(app)

    async def apply(*args):
        calls.append(True)
        return {"state": "connected", "detail": "Fixture"}

    monkeypatch.setattr(indexers, "review_provider", review)
    monkeypatch.setattr(indexers, "apply", apply)
    token = client.post("/api/indexers/providers/review", json=PROVIDER_BODY, headers=auth).json()["review_token"]
    first_cookie = dict(client.cookies)
    second = client.post("/api/login", json={"password": "synthetic test password"}, headers={"Origin": "http://testserver"})
    second_auth = {"Origin": "http://testserver", "X-CSRF-Token": second.json()["csrf"]}
    assert client.post("/api/indexers/apply", json={"review_token": token}, headers=second_auth).status_code == 409
    assert calls == []
    client.cookies.clear()
    client.cookies.update(first_cookie)
    assert client.post("/api/indexers/apply", json={"review_token": token}, headers=auth).status_code == 200
    assert client.post("/api/indexers/apply", json={"review_token": token}, headers=auth).status_code == 409
    assert len(calls) == 1


def test_provider_review_expires_before_any_apply(client, app, auth, monkeypatch):
    configure_source(app)
    clock = [time.monotonic()]
    monkeypatch.setattr("stackarr.server.time", SimpleNamespace(time=time.time, monotonic=lambda: clock[0]))

    async def review(*args):
        return plan(app)

    async def apply(*args):
        pytest.fail("Expired source review must not reach Prowlarr")

    monkeypatch.setattr(indexers, "review_provider", review)
    monkeypatch.setattr(indexers, "apply", apply)
    token = client.post("/api/indexers/providers/review", json=PROVIDER_BODY, headers=auth).json()["review_token"]
    clock[0] += 301
    response = client.post("/api/indexers/apply", json={"review_token": token}, headers=auth)
    assert response.status_code == 409


def test_stale_provider_review_is_rejected_and_existing_source_is_preserved(client, app, auth, monkeypatch):
    configure_source(app)
    writes = []
    actual_apply = indexers.apply

    async def review(*args):
        return plan(app)

    def upstream(request):
        if request.method != "GET":
            writes.append(request.method)
        return httpx.Response(200, json=[plan(app)["payload"]])

    async def apply(store, proposal, transport=None):
        return await actual_apply(store, proposal, httpx.MockTransport(upstream))

    monkeypatch.setattr(indexers, "review_provider", review)
    monkeypatch.setattr(indexers, "apply", apply)
    token = client.post("/api/indexers/providers/review", json=PROVIDER_BODY, headers=auth).json()["review_token"]
    revision, config = app.state.store.config()
    app.state.store.save(config, revision)
    assert client.post("/api/indexers/apply", json={"review_token": token}, headers=auth).status_code == 409
    token = client.post("/api/indexers/providers/review", json=PROVIDER_BODY, headers=auth).json()["review_token"]
    response = client.post("/api/indexers/apply", json={"review_token": token}, headers=auth)
    assert response.status_code == 200 and response.json()["state"] == "existing" and writes == []


@pytest.mark.parametrize("body", [{"query": "x", "media_type": "movie"},
                                  {"query": "Fixture", "media_type": PRIVATE},
                                  {"query": "Fixture\n" + PRIVATE, "media_type": "tv"},
                                  {"query": "Fixture", "media_type": "movie", "command": "private"}])
def test_source_check_rejects_invalid_body_without_running_probe(client, auth, monkeypatch, body):
    async def validate(*args):
        pytest.fail("Invalid diagnostic input must not contact a provider")

    monkeypatch.setattr(indexers, "validate", validate)
    response = client.post("/api/indexers/validate", json=body, headers=auth)
    assert response.status_code == 422 and PRIVATE not in response.text


def test_source_check_requires_csrf_and_persists_only_sanitized_evidence(client, app, auth, monkeypatch):
    async def validate(*args):
        return source_result()

    monkeypatch.setattr(indexers, "validate", validate)
    assert client.post("/api/indexers/validate", json={"query": "Fixture", "media_type": "movie"}).status_code == 403
    revision = app.state.store.config()[0]
    response = client.post("/api/indexers/validate", json={"query": "Fixture", "media_type": "movie"}, headers=auth)
    assert response.status_code == 200
    saved = evidence(app, "source-validation-movie")
    assert saved["config_revision"] == revision and saved["successful"] == 1 and saved["matching"] == 1
    assert saved["source_snapshot"]["source_ids"] == [5]
    with app.state.store.db() as db:
        encoded = " ".join(row[0] for row in db.execute("SELECT data FROM setup_observations"))
    assert all(value not in encoded for value in (PRIVATE, "private source", "private media", "private.example", "result_count"))


def test_source_check_binds_evidence_to_revision_before_probe(client, app, auth, monkeypatch):
    revision = app.state.store.config()[0]

    async def validate(*args):
        changed_revision, config = app.state.store.config()
        app.state.store.save(config, changed_revision)
        return source_result()

    monkeypatch.setattr(indexers, "validate", validate)
    response = client.post("/api/indexers/validate", json={"query": "Fixture", "media_type": "tv"}, headers=auth)
    assert response.status_code == 200
    assert evidence(app, "source-validation-tv")["config_revision"] == revision
    assert evidence(app, "sources")["config_revision"] == revision
    assert app.state.store.config()[0] == revision + 1


@pytest.mark.parametrize("error,status", [(TimeoutError(PRIVATE), 504), (ValueError(PRIVATE), 409)])
def test_failed_source_check_replaces_success_with_unverified_evidence(client, app, auth, monkeypatch, error, status):
    async def success(*args):
        return source_result()

    monkeypatch.setattr(indexers, "validate", success)
    body = {"query": "Fixture", "media_type": "movie"}
    assert client.post("/api/indexers/validate", json=body, headers=auth).status_code == 200

    async def failure(*args):
        raise error

    monkeypatch.setattr(indexers, "validate", failure)
    response = client.post("/api/indexers/validate", json=body, headers=auth)
    assert response.status_code == status and PRIVATE not in response.text
    saved = evidence(app, "source-validation-movie")
    assert saved["available"] is False and saved["successful"] == 0 and saved["matching"] == 0


def test_source_check_lock_prevents_parallel_provider_queries(client, app, auth, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    async def validate(*args):
        calls.append(True)
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return source_result()

    monkeypatch.setattr(indexers, "validate", validate)
    body = {"query": "Fixture", "media_type": "movie"}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/indexers/validate", json=body, headers=auth)
        try:
            assert entered.wait(3)
            response = client.post("/api/indexers/validate", json=body, headers=auth)
            assert response.status_code == 409 and "already running" in response.text
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200
    assert len(calls) == 1


def test_source_check_deadline_cancels_probe_and_releases_lock(client, app, auth, monkeypatch):
    original_timeout = asyncio.timeout
    cancelled = []

    def timeout(duration):
        return original_timeout(0.01 if duration == 50 else duration)

    async def slow(*args):
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.append(True)

    monkeypatch.setattr("stackarr.server.asyncio.timeout", timeout)
    monkeypatch.setattr(indexers, "validate", slow)
    body = {"query": "Fixture", "media_type": "movie"}
    assert client.post("/api/indexers/validate", json=body, headers=auth).status_code == 504
    assert cancelled == [True]

    async def success(*args):
        return source_result()

    monkeypatch.setattr(indexers, "validate", success)
    assert client.post("/api/indexers/validate", json=body, headers=auth).status_code == 200
