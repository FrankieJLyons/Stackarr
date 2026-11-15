import copy
import io
import json
import tarfile

import pytest
from test_deployment_check import installed as installed

from stackarr.app_backups import compatibility
from stackarr.deployment import DeploymentError, Deployments
from stackarr.deployment_check import load_receipt
from stackarr.store import Conflict
from stackarr.updates import Updates


@pytest.fixture
def update_lab(installed, monkeypatch):
    service, identity, info, calls = installed
    original = info["Config"]["Image"]
    target = "plexinc/pms-docker@sha256:" + "e" * 64
    info["Id"], info["State"]["ExitCode"] = "b" * 64, 0
    with service.store.db() as db:
        saved = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    info["Config"]["Env"] = [f"{k}={v}" for k, v in saved["compose"]["services"]["plex"]["environment"].items()]
    files = {"settings": b"original settings", "database": b"original schema"}
    flags = {"candidate_fails": False, "old_fails": False, "crash": False, "missing": False, "count": 1}
    monkeypatch.setattr("stackarr.updates.catalog", lambda: {"reviewed_on": "synthetic", "apps": {"plex": {"image": target, "version": "1.0-ls2"}}})
    def docker(args, **kwargs):
        calls.append(args)
        verb = args[2]
        if verb == "inspect":
            if flags["missing"]:
                raise DeploymentError("Missing fixture container")
            return json.dumps([info])
        if args[2:4] == ["volume", "inspect"]:
            return json.dumps([{"Labels": {"com.docker.compose.project": "stackarr-owned-" + identity, "com.docker.compose.volume": "plex-config"}}])
        if verb == "ps":
            return "" if flags["missing"] else info["Id"]
        if verb == "image":
            reference = args[-1]
            return json.dumps([{"Os": "linux", "Architecture": "amd64", "Id": "sha256:" + ("e" if reference == target else "a") * 64,
                                "Config": {"Labels": {"org.opencontainers.image.version": "1.0-ls2" if reference == target else "1.0-ls1"}}}])
        if verb in {"pull", "tag"}:
            return ""
        if verb in {"start", "stop"}:
            assert args[-1] == info["Id"]
            info["State"]["Running"] = verb == "start"
            return info["Id"]
        assert verb == "compose" and args[-1] == "plex"
        assert "--no-deps" in args and "--pull" in args and "never" in args
        from pathlib import Path
        compose = json.loads(Path(args[args.index("-f") + 1]).read_text())
        app = compose["services"]["plex"]
        info["Config"]["Image"] = app["image"]
        info["Config"]["Labels"] = {"com.docker.compose.project": "stackarr-owned-" + identity,
                                     "com.docker.compose.service": "plex", **app.get("labels", {})}
        flags["count"] += 1
        info["Id"] = f'{flags["count"]:064x}'
        info["State"]["Running"], flags["missing"] = True, False
        if app["image"] == target:
            files["database"] = b"migrated by candidate"
            files["candidate-created"] = b"new file"
            if flags.get("changes_settings"):
                files["settings"] = b"unexpected candidate change"
        return ""
    monkeypatch.setattr(service, "_call", docker)
    updates = Updates(service)
    monkeypatch.setattr(updates, "credentials", lambda *args: {"api_key": "fixture"})
    monkeypatch.setattr(updates, "protected", lambda *args: {"setting": files["settings"].decode()})
    def health(payload, *args, **kwargs):
        candidate = payload["compose"]["services"]["plex"]["image"] == target
        if candidate and flags["crash"]:
            raise SimulatedCrash()
        return not (flags["candidate_fails"] if candidate else flags["old_fails"])
    monkeypatch.setattr(updates, "health", health)
    def helper(payload, key, directory, restore=False):
        assert not info["State"]["Running"]
        assert key == "plex"
        if restore:
            with tarfile.open(directory / "volume.tar") as archive:
                files.clear()
                files.update({member.name: archive.extractfile(member).read() for member in archive if member.isfile()})
        else:
            with tarfile.open(directory / "volume.tar", "w") as archive:
                for name, value in files.items():
                    entry = tarfile.TarInfo(name)
                    entry.size = len(value)
                    archive.addfile(entry, io.BytesIO(value))
    monkeypatch.setattr(updates.backups, "helper", helper)
    return updates, identity, info, calls, files, flags, original, target


class SimulatedCrash(BaseException):
    pass


def test_update_and_manual_rollback_restore_image_and_original_database(update_lab):
    updates, identity, info, calls, files, _, original, target = update_lab
    saved = dict(files)
    before = load_receipt(updates.deployments, identity)
    assert updates.execute(updates.review(identity, "plex"))["state"] == "succeeded"
    assert info["Config"]["Image"] == target and files != saved
    assert load_receipt(updates.deployments, identity)["compose"]["services"]["plex"]["image"] == target
    run = updates.listing()["history"][0]["id"]
    files["settings"] = b"owner settings after update"
    assert updates.execute(updates.review(identity, "plex", "rollback", run))["state"] == "succeeded"
    assert files == saved and info["Config"]["Image"] == original
    assert compatibility(load_receipt(updates.deployments, identity)) == compatibility(before)
    assert any(row["kind"] == "before-rollback" for row in updates.backups.rows())
    assert all("prune" not in call and "--volumes" not in call and "down" not in call for call in calls)


def test_failed_health_after_candidate_migration_recovers_old_image_and_data(update_lab):
    updates, identity, info, _, files, flags, original, _ = update_lab
    expected = dict(files)
    flags["candidate_fails"] = True
    result = updates.execute(updates.review(identity, "plex"))
    assert result["state"] == "rolled-back"
    assert files == expected and info["State"]["Running"] and info["Config"]["Image"] == original
    assert updates.listing()["history"][0]["state"] == "rolled-back"


@pytest.mark.parametrize("missing", [False, True])
def test_interrupted_migrated_update_recovers_after_controller_restart(update_lab, missing):
    updates, identity, info, _, files, flags, original, _ = update_lab
    expected = dict(files)
    flags["crash"] = True
    with pytest.raises(SimulatedCrash):
        updates.execute(updates.review(identity, "plex"))
    assert files != expected
    Deployments(updates.store)  # Startup marks unfinished operations; no write is replayed.
    assert updates.deployments.actions.busy()
    with pytest.raises(Conflict, match="Recover"):
        updates.deployments.actions.enqueue({"action": "stop"})
    flags["crash"] = False
    flags["missing"] = missing
    if missing:
        info["State"]["Running"] = False
    run = updates.listing()["history"][0]["id"]
    result = updates.execute(updates.review(identity, "plex", "update-recover", run))
    assert result["state"] == "succeeded" and files == expected
    assert info["Config"]["Image"] == original and info["State"]["Running"]
    assert not updates.deployments.actions.busy()


def test_changed_review_fails_before_pull_or_downtime(update_lab):
    updates, identity, info, calls, _, _, _, _ = update_lab
    review = updates.review(identity, "plex")
    calls.clear()
    info["Id"] = "c" * 64
    with pytest.raises(Conflict):
        updates.execute(review)
    assert all(call[2] in {"inspect", "volume", "ps", "image"} for call in calls)


def test_healthy_candidate_with_lost_settings_is_rolled_back(update_lab):
    updates, identity, info, _, files, flags, original, _ = update_lab
    expected = dict(files)
    flags["changes_settings"] = True
    outcome = updates.execute(updates.review(identity, "plex"))
    assert outcome["state"] == "rolled-back" and files == expected
    assert info["Config"]["Image"] == original


def test_failed_recovery_remains_explicit_and_blocks_other_operations(update_lab):
    updates, identity, _, _, _, flags, _, _ = update_lab
    review = updates.review(identity, "plex")
    flags["candidate_fails"] = flags["old_fails"] = True
    # Preserve the successful baseline check; fail only once candidate starts.
    health = updates.health
    initial = True
    def failing_health(*args, **kwargs):
        nonlocal initial
        if initial:
            initial = False
            return True
        return health(*args, **kwargs)
    updates.health = failing_health
    with pytest.raises(DeploymentError, match="needs attention"):
        updates.execute(review)
    assert updates.listing()["history"][0]["state"] == "needs-recovery"
    assert updates.deployments.actions.busy()


def test_failed_manual_rollback_recovers_newer_settings_from_safety_snapshot(update_lab):
    updates, identity, info, _, files, flags, _, target = update_lab
    updates.execute(updates.review(identity, "plex"))
    run = updates.listing()["history"][0]["id"]
    files["settings"] = b"new owner setting"
    expected = copy.deepcopy(files)
    flags["old_fails"] = True
    result = updates.execute(updates.review(identity, "plex", "rollback", run))
    assert result["state"] == "rolled-back" and files == expected
    assert info["Config"]["Image"] == target and info["State"]["Running"]


def test_update_rejects_extra_unreviewed_volume_before_downtime(update_lab):
    updates, identity, info, calls, *_ = update_lab
    info["Mounts"].append({"Type": "volume", "Destination": "/unreviewed", "Name": "foreign"})
    calls.clear()
    with pytest.raises(DeploymentError, match="extra volume"):
        updates.review(identity, "plex")
    assert not any(call[2] in {"pull", "stop", "compose"} for call in calls)


def test_update_and_rollback_reuse_reviewed_plex_scratch_volume(update_lab, monkeypatch):
    from pathlib import Path

    updates, identity, info, calls, *_ = update_lab
    reference = {"name": "f" * 64, "fingerprint": "reviewed-volume"}
    info["Mounts"].append({"Type": "volume", "Destination": "/transcode", "Name": reference["name"]})
    image = updates.image
    def declared_image(*args):
        result = image(*args)
        result["Config"]["Volumes"] = {"/transcode": {}}
        return result
    monkeypatch.setattr(updates, "image", declared_image)
    def retained(self, payload, name, consumer=None):
        assert name == reference["name"] and consumer == info["Id"]
        return reference
    monkeypatch.setattr("stackarr.app_maintenance.AppMaintenance.auxiliary", retained)
    assert updates.execute(updates.review(identity, "plex"))["state"] == "succeeded"
    run = updates.listing()["history"][0]["id"]
    assert updates.execute(updates.review(identity, "plex", "rollback", run))["state"] == "succeeded"
    plans = [json.loads(Path(call[call.index("-f") + 1]).read_text()) for call in calls if call[2] == "compose"]
    assert len(plans) >= 2
    for plan in plans:
        assert plan["volumes"]["retained-update-cache-0"] == {"external": True, "name": reference["name"]}
        assert {"type": "volume", "source": "retained-update-cache-0", "target": "/transcode"} in plan["services"]["plex"]["volumes"]
