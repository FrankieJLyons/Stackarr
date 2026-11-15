import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from stackarr.deployment import DeploymentError
from stackarr.self_update import FILES, SelfUpdates, fingerprint, package
from stackarr.store import Store


@pytest.fixture
def release(tmp_path):
    directory = tmp_path / "release"
    directory.mkdir()
    for name in FILES:
        (directory / name).write_bytes(("Synthetic payload " + name).encode())
    manifest = {"schema": 1, "release": "Stackarr-Test-1", "maintenance": {"protocol": 1, "state_schema": 1},
        "image": "stackarr:test-fixture", "image_id": "sha256:" + "a" * 64,
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    archive = tmp_path / "update.zip"
    with zipfile.ZipFile(archive, "x") as bundle:
        for item in directory.iterdir():
            bundle.write(item, "Stackarr-Update/" + item.name)
    return directory, archive


def test_release_staging_verifies_every_payload_without_running_code(tmp_path, release):
    root = tmp_path / "state"
    root.mkdir()
    updater = SelfUpdates(root)
    result = updater.admit(release[1])
    staged, manifest = updater.release(result["id"])
    assert manifest["release"] == result["release"] == "Stackarr-Test-1"
    assert set(p.name for p in staged.iterdir()) == FILES | {"manifest.json"}
    (staged / "StackarrPreview.exe").write_bytes(b"changed")
    with pytest.raises(DeploymentError, match="changed"):
        updater.release(result["id"])


def test_failed_release_copy_can_retry_without_adopting_partial_files(tmp_path, release, monkeypatch):
    import shutil

    root = tmp_path / "state"
    root.mkdir()
    updater = SelfUpdates(root)
    original = shutil.copyfile
    count = 0
    def interrupted(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 3:
            raise PermissionError("Isolated interrupted release copy")
        return original(*args, **kwargs)
    monkeypatch.setattr("stackarr.self_update.shutil.copyfile", interrupted)
    with pytest.raises(PermissionError):
        updater.stage_directory(release[0])
    assert not list((updater.home / "releases").iterdir())
    monkeypatch.setattr("stackarr.self_update.shutil.copyfile", original)
    assert updater.release(updater.stage_directory(release[0])[0])[1]["release"] == "Stackarr-Test-1"


@pytest.mark.parametrize("damage", ["extra", "traversal", "duplicate", "missing", "protocol", "hash", "repository"])
def test_bad_packages_rejected_before_any_docker_access(tmp_path, release, damage):
    directory, archive = release
    if damage in {"protocol", "hash", "repository"}:
        manifest = json.loads((directory / "manifest.json").read_text())
        if damage == "protocol":
            manifest["maintenance"]["state_schema"] = 2
        elif damage == "hash":
            manifest["files"]["StackarrPreview.exe"] = "b" * 64
        else:
            manifest["image"] = "arbitrary:code"
        (directory / "manifest.json").write_text(json.dumps(manifest))
    archive.unlink()
    with zipfile.ZipFile(archive, "x") as bundle:
        for item in directory.iterdir():
            if damage == "missing" and item.name == "StackarrPreview.exe":
                continue
            bundle.write(item, ("../" if damage == "traversal" else "release/") + item.name)
        if damage == "extra":
            bundle.writestr("release/run-this.ps1", "untrusted commands")
        if damage == "duplicate":
            bundle.writestr("release/StackarrPreview.exe", "changed")
    root = tmp_path / "state"
    root.mkdir()
    with pytest.raises(DeploymentError):
        SelfUpdates(root).admit(archive)
    assert not (root / "stackarr-runtime.json").exists()


def test_protected_database_probe_ignores_sessions_but_detects_credentials_and_settings(tmp_path):
    store = Store(tmp_path / "state")
    expected = fingerprint(store.root)
    with store.db() as db:
        db.execute("INSERT INTO sessions VALUES('synthetic','synthetic',99999999)")
        db.execute("INSERT INTO audit VALUES(1,0,'synthetic','stackarr')")
    assert fingerprint(store.root) == expected
    store.save(store.config()[1], 1, {"sonarr": {"api_key": "synthetic secret"}})
    assert fingerprint(store.root) != expected


def test_recipe_rejects_media_mounts_extra_services_and_privileges(tmp_path):
    root = tmp_path / "state"
    plan = {"services": {"stackarr": {"image": "stackarr:fixture", "init": True, "read_only": True,
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"], "ports": ["127.0.0.1:29100:8787"],
        "environment": {"STACKARR_ORIGIN": "http://localhost:29100", "STACKARR_CONTROLLER_SHARED": "/run/stackarr-controller", "STACKARR_CONTROLLER_PORT": "29010"},
        "volumes": ["dashboard-state:/var/lib/stackarr", {"type": "bind", "source": str(root / "controller/shared"), "target": "/run/stackarr-controller", "read_only": True}],
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=32m"]}}, "volumes": {"dashboard-state": {}}}
    SelfUpdates.recipe(plan, root, 29100, 29010)
    for mutation in (lambda p: p["services"]["stackarr"].update(privileged=True),
                     lambda p: p["services"].update(plex={}),
                     lambda p: p["services"]["stackarr"]["volumes"].append("media:/data")):
        value = json.loads(json.dumps(plan))
        mutation(value)
        with pytest.raises(DeploymentError):
            SelfUpdates.recipe(value, root, 29100, 29010)
    plan['services']['stackarr']['environment'].update(
        STACKARR_LAN_ORIGIN='https://stackarr.home.arpa',
        STACKARR_LAN_LINKS=json.dumps({'plex':'https://plex.home.arpa'}))
    SelfUpdates.recipe(plan, root, 29100, 29010)
    plan['services']['stackarr']['environment']['STACKARR_LAN_LINKS'] = json.dumps({'plex':'http://plex.home.arpa'})
    with pytest.raises(DeploymentError, match='LAN configuration'):
        SelfUpdates.recipe(plan, root, 29100, 29010)


def test_update_cannot_drop_lan_support_before_downtime(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from stackarr.self_update import write

    updater = SelfUpdates(tmp_path)
    runtime = {'release':'a'*64, 'context':{'name':'fixture'},
               'plan':{'services':{'stackarr':{'environment':{'STACKARR_LAN_ORIGIN':'https://stackarr.home.arpa'}}}}}
    monkeypatch.setattr(updater, 'active', lambda: runtime)
    updater.docker = SimpleNamespace(context=lambda: runtime['context'])
    monkeypatch.setattr(updater, 'protected', lambda _: {})
    monkeypatch.setattr(updater, 'release', lambda _: (tmp_path, {'lan_access':0}))
    write(updater.home/'candidate.json', {'id':'b'*64})
    with pytest.raises(DeploymentError, match='cannot preserve LAN access'):
        updater.review('update')
    assert list((updater.home/'jobs').iterdir()) == []


def test_encrypted_checkpoint_restore_cannot_overwrite_app_receipts(tmp_path, release):
    root = tmp_path / "state"
    state = root / "controller/state"
    store = Store(state)
    directory = state / "deployments" / ("a" * 32)
    directory.mkdir(parents=True)
    (directory / "compose.json").write_text('{"preserve":"app receipt"}')
    updater = SelfUpdates(root)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "controller.db").write_bytes(store.path.read_bytes())
    (snapshot / "controller.key").write_bytes((state / "secrets.key").read_bytes())
    updater.restore_controller(snapshot)
    assert (directory / "compose.json").read_text() == '{"preserve":"app receipt"}'


def test_incompatible_major_manifest_rejected_without_executing_payload(release):
    directory, _ = release
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["maintenance"]["protocol"] = 2
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(DeploymentError, match="compatible"):
        package(directory)


def test_checking_dashboard_blocks_configuration_writes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from stackarr.server import create_app

    monkeypatch.setenv("STACKARR_UPDATE_CHECKING", "1")
    app = create_app(tmp_path / "dashboard", origin="http://testserver", background=False)
    before = app.state.store.config()
    with TestClient(app) as client:
        response = client.put("/api/config", json={}, headers={"Origin": "http://testserver"})
        assert response.status_code == 503
        assert client.get("/healthz").status_code == 200
    assert app.state.store.config() == before


def test_independent_worker_gets_its_own_frozen_runtime(tmp_path, release, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    updater = SelfUpdates(root)
    staged, _ = updater.stage_directory(release[0])
    identity = "b" * 32
    directory = updater.home / "jobs" / identity
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps({"source": {"release": staged}}))
    calls = []
    monkeypatch.setattr("stackarr.self_update.subprocess.CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr("stackarr.self_update.subprocess.Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    updater.launch(identity)
    assert calls[0][1]['creationflags'] == 0x08000000
    assert calls[0][1]["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert calls[0][0][1] == "--stackarr-maintenance"


def test_corrupt_rollback_checkpoint_rejected_during_review(tmp_path, monkeypatch):
    from stackarr.self_update import write

    root = tmp_path / "state"
    root.mkdir()
    updater = SelfUpdates(root)
    current = {"release": "a" * 64, "context": {"name": "fixture"}}
    previous = {"id": "b" * 32, "created": 0, "phase": "succeeded", "source": {"release": "c" * 64}, "target": current,
        "after": {"inventory": "same"}, "checkpoint_hash": "d" * 64}
    directory = updater.home / "jobs" / previous["id"]
    directory.mkdir()
    write(directory / "job.json", previous)
    (directory / "checkpoint.enc").write_bytes(b"corrupted checkpoint")
    monkeypatch.setattr(updater, "active", lambda: current)
    monkeypatch.setattr(updater, "protected", lambda runtime: {"inventory": "same"})
    monkeypatch.setattr(updater, "release", lambda identity: (Path("unused"), {}))
    monkeypatch.setattr(updater.docker, "context", lambda: current["context"])
    with pytest.raises(DeploymentError, match="Nothing was paused"):
        updater.review("rollback", previous["id"])


def test_rollback_retains_current_owner_and_sessions_but_restores_preferences(tmp_path):
    import sqlite3
    import tarfile
    from contextlib import closing

    root = tmp_path / "state"
    root.mkdir()
    updater = SelfUpdates(root)
    old = Store(tmp_path / "old")
    current = Store(tmp_path / "current")
    for store, label in ((old, "old"), (current, "current")):
        with store.db() as db:
            db.execute("INSERT INTO account VALUES(1,?,?)", (label, label))
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (label, label, 9999999999))
    preferences = current.config()[1].model_copy(deep=True)
    preferences.dashboard.page_size = 42
    current.save(preferences, 1)
    for store in (old, current):
        (store.root / "dashboard.db").write_bytes(store.path.read_bytes())
    with tarfile.open(old.root / "dashboard-volume.tar", "w") as archive:
        archive.add(old.path, arcname="stackarr.db")
    updater.retain_account(old.root, current.root)
    with closing(sqlite3.connect(old.root / "dashboard.db")) as db:
        assert db.execute("SELECT hash FROM account").fetchone()[0] == "current"
        assert db.execute("SELECT token FROM sessions").fetchone()[0] == "current"
        assert json.loads(db.execute("SELECT data FROM settings").fetchone()[0])["dashboard"]["page_size"] != 42


def test_maintenance_probe_waits_for_busy_signed_status_lane(tmp_path, monkeypatch):
    from stackarr.controller_transport import ControllerConnectionError

    root = tmp_path / "state"
    root.mkdir()
    calls = []

    class Remote:
        async def request(self, operation):
            calls.append(operation)
            if len(calls) == 1:
                raise ControllerConnectionError("Controller is busy", 429)
            return {"protocol": 1, "checking": True}

    monkeypatch.setattr("stackarr.controller_enrollment.client", lambda *args, **kwargs: Remote())
    monkeypatch.setattr("stackarr.self_update.time.sleep", lambda seconds: None)
    assert SelfUpdates(root).controller_probe({"controller_port": 29014}) == {"protocol": 1, "checking": True}
    assert calls == ["stackarr-probe", "stackarr-probe"]
