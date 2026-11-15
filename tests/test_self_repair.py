import errno
import json
from types import SimpleNamespace

import pytest

from stackarr.deployment import DeploymentError
from stackarr.reinstall_wizard import approve, review
from stackarr.runtime_storage import check
from stackarr.self_update import fingerprint, pending, read, write
from stackarr.store import Conflict
from tests.test_self_removal import removal  # noqa: F401


@pytest.fixture
def repair(removal, monkeypatch):  # noqa: F811
    updates, flags, calls, volumes = removal
    manifest = read(updates.package_root / "manifest.json")
    write(updates.package_root / "manifest.json", manifest | {"runtime_repair": 1})
    monkeypatch.setattr("stackarr.self_repair.available", lambda port: True)
    return updates, flags, calls, volumes


@pytest.mark.parametrize("missing,controller", [(False, True), (False, False), (True, False)])
def test_repair_healthy_stopped_or_missing_runtime_keeps_release_and_all_data(repair, missing, controller):
    updates, flags, _, volumes = repair
    source = updates.active()
    before = fingerprint(volumes[source["volume"]])
    if missing:
        flags["container"] = None
    elif not controller:
        flags["container"]["State"]["Running"] = False
    flags["controller"] = controller
    operation = updates.approve(updates.review("repair"))["id"]
    updates.execute(operation)
    result = read(updates.home / "jobs" / operation / "job.json")
    assert result["phase"] == "succeeded" and pending(updates.root) is None
    assert updates.active()["release"] == source["release"] and updates.active()["volume"] != source["volume"]
    assert fingerprint(volumes[updates.active()["volume"]]) == before
    assert (volumes[updates.active()["volume"]] / "retained-backup.enc").read_bytes() == b"original configuration backup bytes"
    assert flags["controller"] and flags["container"]["State"]["Running"]


@pytest.mark.parametrize("fault", ["poison", "poison_files"])
def test_failed_repair_recovers_original_account_and_backup_files(repair, fault):
    updates, flags, _, volumes = repair
    source = updates.active()
    before = fingerprint(volumes[source["volume"]])
    operation = updates.approve(updates.review("repair"))["id"]
    flags[fault] = True
    updates.execute(operation)
    assert read(updates.home / "jobs" / operation / "job.json")["phase"] == "failed-recovered"
    assert updates.active() == source and fingerprint(volumes[source["volume"]]) == before


@pytest.mark.parametrize("damage", ["shared", "volume", "foreign-port", "removed", "edited-container", "missing-key"])
def test_repair_refuses_unverified_data_and_occupied_ports_without_stopping(repair, monkeypatch, damage):
    updates, flags, calls, _ = repair
    if damage in {"shared", "volume"}:
        flags[damage] = damage == "shared"
    elif damage == "foreign-port":
        flags["container"] = None
        monkeypatch.setattr("stackarr.self_repair.available", lambda port: False)
    elif damage == "removed":
        write(updates.root / "stackarr-removed.json", {"format": 1, "job": "f" * 32})
    elif damage == "missing-key":
        (updates.root / "controller/state/secrets.key").unlink()
    else:
        flags["container"]["HostConfig"]["Privileged"] = True
    with pytest.raises((DeploymentError, Conflict)):
        updates.review("repair")
    assert not any(row[0] in {"stop", "rm", "start"} for row in calls)


def test_storage_failure_after_approval_cancels_before_downtime(repair, monkeypatch):
    updates, flags, calls, _ = repair
    operation = updates.approve(updates.review("repair"))["id"]
    identity = flags["container"]["Id"]
    monkeypatch.setattr("stackarr.self_repair.check", lambda *args: (_ for _ in ()).throw(DeploymentError("Storage denied")))
    updates.execute(operation)
    assert read(updates.home / "jobs" / operation / "job.json")["phase"] == "failed-recovered"
    assert flags["container"]["Id"] == identity and flags["controller"]
    assert not any(row[0] in {"stop", "rm", "start"} for row in calls)


def test_local_repair_review_is_one_use_action_bound_and_not_reinstall(repair, monkeypatch):
    updates, _, _, _ = repair
    monkeypatch.setattr("stackarr.reinstall_wizard.SelfUpdates", lambda path: updates)
    value = review(updates.root, "repair")
    with pytest.raises(DeploymentError):
        approve(value)
    assert approve(value, "repair")["id"]
    with pytest.raises(Conflict):
        approve(value, "repair")


@pytest.mark.parametrize("failure", ["full", "denied"])
def test_storage_preflight_reports_actionable_failure_and_keeps_existing_files(tmp_path, monkeypatch, failure):
    original = tmp_path / "keep.txt"
    original.write_text("keep")
    if failure == "full":
        monkeypatch.setattr("stackarr.runtime_storage.shutil.disk_usage", lambda path: SimpleNamespace(free=0))
    else:
        monkeypatch.setattr("stackarr.runtime_storage.os.replace", lambda *args: (_ for _ in ()).throw(PermissionError(errno.EACCES, "private path")))
    with pytest.raises(DeploymentError) as error:
        check(tmp_path)
    assert "private path" not in str(error.value) and "storage" in str(error.value)
    assert original.read_text() == "keep" and list(tmp_path.iterdir()) == [original]


def test_failed_atomic_journal_write_preserves_previous_record(tmp_path, monkeypatch):
    target = tmp_path / "job.json"
    write(target, {"phase": "checkpoint-saved"})
    monkeypatch.setattr("stackarr.self_update.os.replace", lambda *args: (_ for _ in ()).throw(OSError(errno.ENOSPC, "full")))
    with pytest.raises(OSError):
        write(target, {"phase": "committing"})
    assert json.loads(target.read_text()) == {"phase": "checkpoint-saved"}
    assert not target.with_suffix(".tmp").exists()


@pytest.mark.parametrize("verified_controller", [False, True])
def test_first_browser_repair_prepares_verified_runtime_without_an_extra_status_step(repair, monkeypatch, verified_controller):
    updates, _, _, _ = repair
    runtime = updates.active()
    (updates.root / "stackarr-runtime.json").unlink()
    adopted = []
    def adopt():
        adopted.append(True)
        write(updates.root / "stackarr-runtime.json", runtime)
        return runtime
    monkeypatch.setattr(updates, "adopt", adopt)
    if verified_controller:
        updates.controller_identity = {"executable": updates.release(runtime["release"])[1]["files"]["StackarrPreview.exe"], "checking": False}
        assert updates.review("repair")["source"] == runtime
        assert adopted == [True]
    else:
        with pytest.raises(DeploymentError, match="no verified saved"):
            updates.review("repair")
        assert not adopted and not (updates.root / "stackarr-runtime.json").exists()
