import asyncio
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from stackarr import onboarding
from stackarr.deployment import DeploymentError, Deployments
from stackarr.server import create_app
from stackarr.store import Conflict, Store


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    store = Store(tmp_path / "state")
    onboarding.initialize(store)
    onboarding.save(store, onboarding.SaveDraft(revision=1, draft=onboarding.SetupDraft(apps=["seerr"])))
    service = Deployments(store)
    monkeypatch.setattr(service, "context", lambda: {"name": "fixture", "endpoint": "unix:///fixture"})
    monkeypatch.setattr("stackarr.deployment.preflight", lambda config: [{"check": "fixture", "ok": True}])
    calls = []
    monkeypatch.setattr(service, "network_capacity", lambda *args: {"state": "available"})
    monkeypatch.setattr(service, "_call", lambda args, **kwargs: calls.append(args) or image_answer(args))
    monkeypatch.setattr("stackarr.seerr_storage.prepare", lambda *args: None)
    monkeypatch.setattr("stackarr.ports.ensure", lambda *args: None)
    return service, calls


def image_answer(args):
    if "image" in args and "inspect" in args:
        if "--format" not in args:
            return json.dumps([{"Id": "sha256:" + "a" * 64, "RepoDigests": [args[-1]], "Os": "linux", "Architecture": "amd64", "Config": {"Labels": {
                "org.opencontainers.image.version": "3.5.0-stackarr.2", "io.stackarr.seerr.security-patch": "manage-users-1",
                "io.stackarr.seerr.setup-patch": "plex-setup-1"}}}])
        return json.dumps({"id": "sha256:" + "a" * 64, "digests": [args[-1]], "os": "linux", "arch": "amd64"})
    return ""


def test_review_is_read_only_and_scoped(deployment):
    service, calls = deployment
    before = service.store.config()
    payload = service.review()
    assert service.store.config() == before
    assert not calls
    assert payload["compose"]["networks"] == {"control": {}}
    assert "@sha256:" in payload["compose"]["services"]["seerr"]["image"]
    assert payload["compose"]["services"]["seerr"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert "docker.sock" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_install_activates_only_selected_app_and_saves_completion(deployment):
    service, calls = deployment
    identity = service.enqueue(service.review())
    assert service.rows()[0]["id"] == identity
    with pytest.raises(Conflict):
        service.enqueue(service.review())
    await service.run_one()
    assert service.rows()[0]["state"] == "needs-setup"
    assert service.store.config()[1].integrations["seerr"].url == "http://127.0.0.1:5055"
    assert not service.store.config()[1].integrations["plex"].enabled
    assert not any("pull" in args for args in calls), "Verified bundled-only installs must work without a registry"
    assert all("--project-name" in args and "stackarr-apps" in args for args in calls if "compose" in args)
    assert all("--volumes" not in args and "down" not in args and "prune" not in args for args in calls)
    assert not await service.run_one()


def test_changed_choices_invalidate_approval(deployment):
    service, _ = deployment
    payload = service.review()
    onboarding.save(service.store, onboarding.SaveDraft(revision=2, draft=onboarding.SetupDraft(apps=["plex"])))
    with pytest.raises(Conflict, match="changed"):
        service.enqueue(payload)


@pytest.mark.asyncio
async def test_failure_is_redacted_and_explicitly_resumable(deployment, monkeypatch):
    service, _ = deployment
    identity = service.enqueue(service.review())
    def fail(*args, **kwargs):
        raise RuntimeError("private-secret-upstream-output")
    monkeypatch.setattr(service, "execute", fail)
    await service.run_one()
    assert service.rows()[0]["state"] == "failed"
    assert "private-secret" not in json.dumps(service.rows())
    assert not await service.run_one()
    service.resume(identity)
    assert service.rows()[0]["state"] == "queued"


def test_restart_never_replays_external_writes(deployment):
    service, _ = deployment
    identity = service.enqueue(service.review())
    with service.store.db() as db:
        db.execute("UPDATE deployments SET state='running' WHERE id=?", (identity,))
    restarted = Deployments(service.store)
    assert restarted.rows()[0]["state"] == "interrupted"


@pytest.mark.asyncio
async def test_interrupted_install_resumes_same_owned_project_after_restart(deployment, monkeypatch):
    service, _ = deployment
    reviewed = service.review()
    identity = service.enqueue(reviewed)
    with service.store.db() as db:
        db.execute("UPDATE deployments SET state='running' WHERE id=?", (identity,))
    restarted = Deployments(service.store)
    assert restarted.rows()[0]["state"] == "interrupted"
    monkeypatch.setattr(restarted, "context", lambda: reviewed["context"])
    calls = []
    monkeypatch.setattr(restarted, "network_capacity", lambda *args: {"state": "available"})
    monkeypatch.setattr(restarted, "_call", lambda args, **kwargs: calls.append(args) or image_answer(args))
    restarted.resume(identity)
    assert await restarted.run_one()
    assert restarted.rows()[0]["state"] == "needs-setup"
    assert all("stackarr-apps" in call for call in calls if "compose" in call)
    with service.store.db() as db:
        saved = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    assert saved["compose"] == reviewed["compose"]
    assert not any("down" in call or "--volumes" in call for call in calls)


@pytest.mark.asyncio
async def test_context_change_blocks_before_any_docker_mutation(deployment, monkeypatch):
    service, calls = deployment
    service.enqueue(service.review())
    calls.clear()
    monkeypatch.setattr(service, "context", lambda: {"name": "other", "endpoint": "unix:///other"})
    await service.run_one()
    assert not calls
    assert service.rows()[0]["state"] == "failed"


@pytest.mark.asyncio
async def test_modified_compose_is_never_executed(deployment):
    service, calls = deployment
    identity = service.enqueue(service.review())
    calls.clear()
    directory = service.store.root / "deployments" / identity
    directory.mkdir(parents=True)
    (directory / "compose.json").write_text('{"services":{"foreign":{}}}')
    await service.run_one()
    assert not calls
    assert service.rows()[0]["state"] == "failed"


def test_existing_apps_are_not_adopted(deployment):
    service, _ = deployment
    revision, config = service.store.config()
    config.integrations["seerr"].url = "http://existing.example"
    config.integrations["seerr"].enabled = True
    service.store.save(config, revision)
    with pytest.raises(DeploymentError, match="already configured"):
        service.review()


def test_web_cannot_enable_host_control_on_nonlocal_origin(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        create_app(tmp_path, origin="https://example.com", host_install=True, host_checks=True)


def test_deployment_endpoints_require_session_and_csrf(client, auth):
    result = client.get("/api/deployments").json()
    assert result["available"] is False and result["operations"] == []
    assert result["journey"]["next_action"]["id"] == "choose-apps"
    assert client.post("/api/deployments/review").status_code == 403
    assert client.post("/api/deployments/review", headers=auth).status_code == 409
    client.post("/api/logout", headers=auth)
    assert client.get("/api/deployments").status_code == 401


def test_review_is_bound_to_session_and_consumed(tmp_path):
    async def idle(self):
        await asyncio.sleep(3600)
    with patch.object(Deployments, "work", idle):
        app = create_app(tmp_path, origin="http://localhost:8787", host_checks=True, host_install=True, background=False)
        with TestClient(app, base_url="http://localhost:8787") as client:
            headers = {"Origin": "http://localhost:8787"}
            password = "synthetic test password"
            client.post("/api/setup", json={"password": password, "setup_token": (tmp_path / "setup-token").read_text()}, headers=headers)
            login = client.post("/api/login", json={"password": password}, headers=headers)
            headers["X-CSRF-Token"] = login.json()["csrf"]
            payload = {"draft_revision": 1, "config_revision": 1, "context": {"name": "fixture"}, "apps": [], "compose": {"services": {}}, "config": {"storage": {"data_root": ""}}}
            app.state.deployments._call = lambda *args, **kwargs: ""
            with patch.object(app.state.deployments, "review", return_value=payload):
                review = client.post("/api/deployments/review", headers=headers).json()
            assert client.post("/api/deployments/install", json={"review_token": review["review_token"]}, headers=headers).status_code == 202
            assert client.post("/api/deployments/install", json={"review_token": review["review_token"]}, headers=headers).status_code == 409
            current = client.get("/api/config").json()
            response = client.put("/api/config", json={"revision": current["revision"], "config": current["config"]}, headers=headers)
            assert response.status_code == 409 and "Installation is in progress" in response.text
            assert app.state.store.config()[0] == current["revision"]


def test_generated_login_requires_reauthentication_and_is_not_cached(tmp_path):
    app = create_app(tmp_path, origin="http://localhost:8787", host_checks=True, host_install=True, background=False)
    with TestClient(app, base_url="http://localhost:8787") as client:
        headers = {"Origin": "http://localhost:8787"}
        password = "synthetic owner password"
        client.post("/api/setup", json={"password": password, "setup_token": (tmp_path / "setup-token").read_text()}, headers=headers)
        login = client.post("/api/login", json={"password": password}, headers=headers)
        headers["X-CSRF-Token"] = login.json()["csrf"]
        with patch.object(app.state.deployments, "generated_login", return_value={"username": "admin", "password": "synthetic-generated"}) as reveal:
            assert client.post("/api/deployments/qbittorrent/login", json={"password": password}).status_code == 403
            assert client.post("/api/deployments/qbittorrent/login", json={"password": "incorrect password"}, headers=headers).status_code == 403
            reveal.assert_not_called()
            response = client.post("/api/deployments/qbittorrent/login", json={"password": password}, headers=headers)
            assert response.json()["password"] == "synthetic-generated"
            assert response.headers["Cache-Control"] == "no-store"
            assert "synthetic-generated" not in client.get("/api/audit").text
            assert "synthetic-generated" not in client.get("/api/config").text
        client.post("/api/logout", headers=headers)
        assert client.post("/api/deployments/qbittorrent/login", json={"password": password}, headers=headers).status_code == 401


def test_generated_login_never_reveals_replaced_or_connected_credentials(deployment):
    service, _ = deployment
    with pytest.raises(DeploymentError, match="No unchanged"):
        service.generated_login()
    revision, config = service.store.config()
    config.integrations["qbittorrent"].enabled = True
    config.integrations["qbittorrent"].url = "http://127.0.0.1:8080"
    service.store.save(config, revision, {"qbittorrent": {"username": "admin", "password": "user supplied"}})
    with pytest.raises(DeploymentError, match="No unchanged"):
        service.generated_login()


@pytest.mark.asyncio
async def test_resume_preserves_unrelated_settings_changes(deployment):
    service, _ = deployment
    reviewed = service.review()
    identity = service.enqueue(reviewed)
    with service.store.db() as db:
        db.execute("UPDATE deployments SET state='failed' WHERE id=?", (identity,))
    revision, config = service.store.config()
    config.dashboard.appearance = "light"
    service.store.save(config, revision)
    service.resume(identity)
    with service.store.db() as db:
        resumed = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    assert resumed["compose"] == reviewed["compose"]
    await service.run_one()
    assert service.rows()[0]["state"] == "needs-setup"
    assert service.store.config()[1].dashboard.appearance == "light"


def test_resume_refuses_to_replace_newly_configured_app(deployment):
    service, _ = deployment
    identity = service.enqueue(service.review())
    with service.store.db() as db:
        db.execute("UPDATE deployments SET state='failed' WHERE id=?", (identity,))
    revision, config = service.store.config()
    config.integrations["seerr"].url = "http://existing.example"
    service.store.save(config, revision)
    with pytest.raises(Conflict, match="preserved"):
        service.resume(identity)


def test_registry_retry_never_replays_application_writes(deployment, monkeypatch):
    service, _ = deployment
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if len(calls) < 3:
            raise DeploymentError("synthetic registry limit", retryable=True)
        return ""
    monkeypatch.setattr(service, "_call", command)
    monkeypatch.setattr("stackarr.deployment.time.sleep", lambda seconds: None)
    service._pull("fixture", ["compose"], ["sonarr"])
    assert calls == [["compose", "pull", "--policy", "missing", "sonarr"]] * 3


def test_nontransient_download_error_is_not_retried(deployment, monkeypatch):
    service, _ = deployment
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        raise DeploymentError("invalid image reference")
    monkeypatch.setattr(service, "_call", command)
    with pytest.raises(DeploymentError, match="download failed"):
        service._pull("fixture", ["compose"], ["sonarr"])
    assert len(calls) == 1
