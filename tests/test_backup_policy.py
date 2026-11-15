import asyncio
import json
import shutil
import time
from pathlib import Path

import pytest
from test_app_backups import backup_lab as backup_lab
from test_deployment_check import installed as installed

from stackarr.app_backups import AppBackups
from stackarr.backup_policy import BackupPlans, next_run
from stackarr.deployment import DeploymentError
from stackarr.store import Conflict


@pytest.fixture
def plan_lab(backup_lab, tmp_path, monkeypatch):
    service, identity, info, files, calls = backup_lab
    plans = BackupPlans(service.deployments)
    external = tmp_path / "other-disk"
    external.mkdir()
    monkeypatch.setattr("stackarr.backup_policy.disk", lambda path: "2" if Path(path).is_relative_to(external) else "1")
    destination = plans.admit(external)["id"]
    plans.configure(plans.review({"enabled": True, "time": "03:00", "keep": 2,
                                 "deployments": [identity], "destination": destination}))
    helper = service.helper
    monkeypatch.setattr(AppBackups, "helper", lambda self, payload, key, directory, restore=False: helper(payload, key, directory, restore))
    return plans, service, identity, info, files, calls, external


def test_retention_preserves_manual_and_safety_snapshots_and_external_recovery(plan_lab, tmp_path):
    plans, service, identity, info, files, _, _ = plan_lab
    expected = dict(files)
    service.execute(service.review(identity))
    manual = service.rows()[0]["id"]
    for _ in range(4):
        plans.execute({"revision": plans.read()[0]})
    rows = service.rows()
    scheduled = [row for row in rows if row["kind"] == "scheduled"]
    assert len(scheduled) == 2 and any(row["id"] == manual for row in rows)
    snapshot = scheduled[0]["id"]
    location, envelope = plans.external(snapshot)
    assert b"private fixture" not in (location / "plex.enc").read_bytes()
    assert envelope["manifest"] == service.manifest(snapshot)
    # Simulate losing only the local snapshot; the registered off-disk copy must restore.
    plans.remove_files(service.root / snapshot, ["plex.enc", "controller.enc"])
    files["settings.json"] = b"changed after scheduled snapshot"
    service.execute(service.review(identity, snapshot))
    assert files == expected and info["State"]["Running"]
    safety = next(row for row in service.rows() if row["kind"] == "before-restore")
    plans.external(safety["id"])
    assert plans.listing()["policy"]["last_status"] == "Verified"


def test_corrupt_external_copy_rejected_before_downtime(plan_lab):
    plans, service, identity, info, files, calls, _ = plan_lab
    plans.execute({"revision": plans.read()[0]})
    snapshot = service.rows()[0]["id"]
    location, _ = plans.external(snapshot)
    plans.remove_files(service.root / snapshot, ["plex.enc", "controller.enc"])
    path = location / "plex.enc"
    path.write_bytes(path.read_bytes()[:-10])
    calls.clear()
    before = dict(files)
    with pytest.raises(DeploymentError, match="verification failed"):
        service.execute(service.review(identity, snapshot))
    assert files == before and info["State"]["Running"]
    assert not any(args[2] in {"stop", "start"} for args in calls)


def test_disconnected_disk_does_not_stop_apps_or_prune(plan_lab, monkeypatch):
    plans, service, _, info, _, calls, _ = plan_lab
    plans.execute({"revision": plans.read()[0]})
    before = service.rows()
    calls.clear()
    monkeypatch.setattr("stackarr.backup_policy.disk", lambda path: "changed-disk")
    with pytest.raises(DeploymentError, match="unavailable or changed"):
        plans.execute({"revision": plans.read()[0]})
    assert service.rows() == before and info["State"]["Running"]
    assert not any(args[2] in {"stop", "start"} for args in calls)
    assert "failed" in plans.listing()["policy"]["last_status"]


def test_due_schedule_is_claimed_once_and_survives_new_instance(plan_lab):
    plans, service, _, _, _, _, _ = plan_lab
    revision, policy = plans.read()
    now = time.time()
    policy["next_run"] = now - 86400 * 3
    with plans.store.db() as db:
        plans.write(db, revision, policy)
    assert plans.tick(now)
    assert not BackupPlans(service.deployments).tick(now)
    queued = [row for row in service.deployments.actions.rows() if row["state"] == "queued"]
    assert len(queued) == 1
    asyncio.run(service.deployments.actions.run_one())
    assert service.deployments.actions.rows()[0]["state"] == "succeeded"
    assert plans.read()[1]["next_run"] > now


def test_busy_schedule_waits_without_losing_due_slot(plan_lab):
    plans, _, _, _, _, _, _ = plan_lab
    revision, policy = plans.read()
    now = time.time()
    policy["next_run"] = now - 1
    with plans.store.db() as db:
        plans.write(db, revision, policy)
        db.execute("INSERT INTO deployment_actions VALUES(?,?,?,?,?,?)", ("a" * 32, "running", "busy", now, now, "{}"))
    assert not plans.tick(now)
    assert plans.read()[1]["next_run"] == policy["next_run"]


def test_changed_policy_cancels_queued_backup_before_mutation(plan_lab):
    plans, _, _, _, _, calls, _ = plan_lab
    revision, policy = plans.read()
    plans.configure(plans.review({key: policy[key] for key in ("enabled", "time", "keep", "deployments", "destination")} | {"enabled": False}))
    calls.clear()
    with pytest.raises(Conflict):
        plans.execute({"revision": revision})
    assert not calls


def test_same_disk_and_unexpected_retention_files_are_rejected(plan_lab, tmp_path, monkeypatch):
    plans, service, identity, _, _, _, _ = plan_lab
    monkeypatch.setattr("stackarr.backup_policy.disk", lambda path: "same")
    with pytest.raises(DeploymentError, match="different physical disk"):
        plans.admit(tmp_path)
    directory = tmp_path / "owned"
    directory.mkdir()
    (directory / "personal.txt").write_text("keep")
    with pytest.raises(DeploymentError, match="Unexpected files"):
        plans.remove_files(directory, ["plex.enc"])
    assert (directory / "personal.txt").read_text() == "keep"


def test_next_nightly_time_is_in_future():
    now = time.time()
    assert now < next_run(now, "03:00") <= now + 90000


@pytest.mark.parametrize("state", ["Queued", "Running"])
def test_startup_reconciles_interrupted_schedule_without_replaying_data_writes(plan_lab, state):
    plans, _, _, _, _, calls, _ = plan_lab
    revision, policy = plans.read()
    with plans.store.db() as db:
        plans.write(db, revision, policy | {"last_status": state})
    calls.clear()
    plans.reconcile_startup()
    value = plans.read()[1]
    assert not calls
    if state == "Queued":
        assert value["enabled"] and value["next_run"] <= time.time()
    else:
        assert not value["enabled"] and value["next_run"] is None and "interrupted" in value["last_status"]


def test_copy_failure_keeps_new_local_backup_and_old_copies(plan_lab, monkeypatch):
    plans, service, identity, info, _, _, _ = plan_lab
    service.execute(service.review(identity))
    previous = {row["id"] for row in service.rows()}
    monkeypatch.setattr(shutil, "copyfile", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("test disk full")))
    with pytest.raises(DeploymentError, match="saved locally"):
        plans.execute({"revision": plans.read()[0]})
    assert previous < {row["id"] for row in service.rows()} and info["State"]["Running"]


def test_external_manifest_cannot_redirect_payload_paths(plan_lab):
    plans, service, identity, _, _, _, _ = plan_lab
    service.execute(service.review(identity))
    snapshot = service.rows()[0]["id"]
    location, value = plans.external(snapshot)
    value["files"] = {"../secrets.key": "unused"}
    (location / "snapshot.enc").write_bytes(plans.store.cipher.encrypt(json.dumps(value).encode()))
    with pytest.raises(DeploymentError, match="identity is invalid"):
        plans.external(snapshot)
