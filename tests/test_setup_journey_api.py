import json

import httpx
import pytest

from stackarr import onboarding
from stackarr.server import create_app

APPS = ["plex", "seerr", "sonarr", "radarr", "prowlarr", "qbittorrent"]


def save_requests(client, auth):
    saved = client.get("/api/onboarding").json()
    response = client.put("/api/onboarding", headers=auth, json={"revision": saved["revision"], "draft": {
        "apps": APPS, "step": 1, "data_root": "/media/samples"}})
    assert response.status_code == 200
    return response.json()


def checkpoint(journey, identity):
    return next(row for row in journey["checkpoints"] if row["id"] == identity)


def test_journey_requires_authentication_and_get_does_not_change_state(client, app, auth):
    before = app.state.store.audit_rows()
    journey = client.get("/api/onboarding/journey").json()
    assert journey["next_action"]["id"] == "choose-apps"
    assert app.state.store.audit_rows() == before
    assert client.get("/api/deployments").json()["journey"]["selected_apps"] == []
    assert app.state.store.audit_rows() == before
    client.post("/api/logout", headers=auth)
    assert client.get("/api/onboarding/journey").status_code == 401


def test_saved_checklist_reconstructs_after_reopening_without_connecting_apps(client, app, auth):
    before = app.state.store.config()
    saved = save_requests(client, auth)
    result = client.get("/api/deployments").json()["journey"]
    assert result["draft_revision"] == saved["revision"]
    assert result["next_action"]["id"] == "reconnect-installation"
    assert result["ready_to_watch"] is False
    reopened = create_app(app.state.store.root, origin="http://testserver", background=False,
                          transport=httpx.MockTransport(lambda request: pytest.fail("Unexpected upstream call")))
    assert onboarding.read(reopened.state.store) == saved
    assert app.state.store.config() == before


def test_explicit_runtime_check_advances_saved_checklist_across_navigation(client, app, auth, monkeypatch):
    save_requests(client, auth)
    monkeypatch.setattr("stackarr.docker_runtime.inspect", lambda **kwargs: {
        "state": "ready", "checks": [{"detail": "private host path"}], "notice": "synthetic"})
    assert client.post("/api/onboarding/runtime-check").status_code == 403
    assert client.post("/api/onboarding/runtime-check", headers=auth).status_code == 200
    saved = client.get("/api/onboarding").json()
    saved["draft"]["step"] = 2
    assert client.put("/api/onboarding", json=saved, headers=auth).status_code == 200
    journey = client.get("/api/deployments").json()["journey"]
    assert checkpoint(journey, "computer")["state"] == "done"
    assert journey["next_action"]["id"] == "reconnect-installation"
    with app.state.store.db() as db:
        evidence = " ".join(row[0] for row in db.execute("SELECT data FROM setup_observations"))
    assert "private host path" not in evidence
    assert not any(app.enabled for app in app.state.store.config()[1].integrations.values())


def test_source_observation_is_saved_redacted_and_failed_recheck_replaces_success(client, app, auth, monkeypatch):
    save_requests(client, auth)

    async def sources(*args):
        return {"sources": [{"name": "private provider", "enabled": True, "api_key": "secret"}],
                "apps": [{"app": "sonarr", "shared_sources": 1}, {"app": "radarr", "shared_sources": 1}]}

    monkeypatch.setattr("stackarr.indexers.status", sources)
    assert client.get("/api/indexers/status").status_code == 200
    assert checkpoint(client.get("/api/onboarding/journey").json(), "sources")["state"] == "done"
    with app.state.store.db() as db:
        evidence = " ".join(row[0] for row in db.execute("SELECT data FROM setup_observations"))
    assert "private provider" not in evidence and "secret" not in evidence

    async def unavailable(*args):
        raise ValueError("private error")

    monkeypatch.setattr("stackarr.indexers.status", unavailable)
    assert client.get("/api/indexers/status").status_code == 409
    journey = client.get("/api/onboarding/journey").json()
    assert checkpoint(journey, "sources")["state"] == "needs-action"
    assert "private error" not in json.dumps(journey)


def test_settings_change_during_source_probe_cannot_verify_new_settings(client, app, auth, monkeypatch):
    save_requests(client, auth)

    async def changed(*args):
        revision, config = app.state.store.config()
        app.state.store.save(config, revision)
        return {"sources": [{"enabled": True}], "apps": [
            {"app": "sonarr", "shared_sources": 1}, {"app": "radarr", "shared_sources": 1}]}

    monkeypatch.setattr("stackarr.indexers.status", changed)
    assert client.get("/api/indexers/status").status_code == 200
    assert checkpoint(client.get("/api/onboarding/journey").json(), "sources")["state"] == "unknown"
