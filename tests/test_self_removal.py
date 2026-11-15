import copy
import json
import shutil
import sqlite3
import tarfile
from contextlib import closing
from types import SimpleNamespace

import pytest

from stackarr.app_backups import digest
from stackarr.deployment import DeploymentError
from stackarr.reinstall_wizard import approve, review
from stackarr.self_removal import SelfRemoval, StackarrRemoved, archive_files
from stackarr.self_update import FILES, SelfUpdates, fingerprint, pending, read, write
from stackarr.store import Conflict, Store


@pytest.fixture
def removal(tmp_path, monkeypatch):
    root = tmp_path / "state"
    store = Store(root / "controller/state")
    shared = root / "controller/shared"
    shared.mkdir()
    for name in ("rpc.key", "controller.crt"):
        (shared / name).write_bytes(b"synthetic enrollment")
    (root / "controller/controller.key").write_bytes(b"synthetic private enrollment")
    directory = tmp_path / "package"
    directory.mkdir()
    for name in FILES:
        (directory / name).write_bytes(("synthetic " + name).encode())
    image_id = "sha256:" + "a" * 64
    write(directory / "manifest.json", {"schema": 1, "release": "Stackarr-Removal-Fixture", "image": "stackarr:fixture", "image_id": image_id,
        "maintenance": {"protocol": 1, "state_schema": 1}, "files": {p.name: digest(p) for p in directory.iterdir()}})
    calls = []
    flags = {"controller": True, "controller_state": store.root, "checking": False, "shared": False, "image": True,
             "volume": True, "poison": False, "poison_files": False, "crash_rm": False, "counter": 0}
    context = {"name": "fixture", "endpoint": "unix:///fixture"}
    docker = SimpleNamespace(context=lambda: context, fixed_context=None)
    updates = SelfUpdates(root, directory, docker)
    release, _ = updates.stage_directory(directory)
    project, volume = "stackarr-preview-" + "a" * 12, "retained-dashboard"
    plan = {"services": {"stackarr": {"image": image_id, "init": True, "read_only": True, "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"], "ports": ["127.0.0.1:29140:8787"],
        "environment": {"STACKARR_ORIGIN": "http://localhost:29140", "STACKARR_CONTROLLER_SHARED": "/run/stackarr-controller", "STACKARR_CONTROLLER_PORT": "29014"},
        "volumes": ["dashboard-state:/var/lib/stackarr", {"type": "bind", "source": str(shared), "target": "/run/stackarr-controller", "read_only": True}],
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=32m"]}}, "volumes": {"dashboard-state": {"external": True, "name": volume}}}
    runtime = {"format": 1, "project": project, "context": context, "port": 29140, "controller_port": 29014,
               "release": release, "volume": volume, "plan": plan}
    write(root / "stackarr-runtime.json", runtime)
    write(root / "compose.json", plan)
    volumes = {volume: tmp_path / "dashboard"}
    dashboard = Store(volumes[volume])
    with dashboard.db() as db:
        db.execute("INSERT INTO account VALUES(1,'synthetic owner','synthetic hash')")
    dashboard.save(dashboard.config()[1], 1, {"sonarr": {"api_key": "synthetic retained credential"}})
    (dashboard.root / "retained-backup.enc").write_bytes(b"original configuration backup bytes")
    image = {"Id": image_id, "Os": "linux", "Architecture": "amd64", "Config": {"Env": [], "User": "10001:10001", "Cmd": None, "Entrypoint": None}}
    original = {"Id": "b" * 64, "Image": image_id, "Config": {"Env": [f"{k}={v}" for k, v in plan["services"]["stackarr"]["environment"].items()],
        "User": "10001:10001", "Cmd": None, "Entrypoint": None,
        "Labels": {"com.docker.compose.project": project, "com.docker.compose.service": "stackarr"}},
        "HostConfig": {"PortBindings": {"8787/tcp": [{"HostIp": "127.0.0.1", "HostPort": "29140"}]}, "ReadonlyRootfs": True,
            "Init": True, "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"], "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=32m"},
            "RestartPolicy": {"Name": "no"}, "NetworkMode": project + "_default", "IpcMode": "private"},
        "Mounts": [{"Destination": "/var/lib/stackarr", "Type": "volume", "Name": volume, "RW": True},
            {"Destination": "/run/stackarr-controller", "Type": "bind", "Source": str(shared), "RW": False}],
        "NetworkSettings": {"Networks": {project + "_default": {}}}, "State": {"Running": True, "ExitCode": 0}}
    flags["container"] = copy.deepcopy(original)

    def call(args, **kwargs):
        calls.append(args)
        if args[:2] == ["--context", "fixture"]:
            args = args[2:]
        info = flags["container"]
        if args[0] == "ps":
            if any("volume=" in arg for arg in args):
                selected = args[-1].split("=", 1)[1]
                rows = [info["Id"]] if info and info["Mounts"][0]["Name"] == selected else []
                return "\n".join(rows + (["c" * 64] if flags["shared"] else []))
            return info["Id"] if info else ""
        if args[0] == "inspect":
            return json.dumps([info])
        if args[:2] == ["image", "inspect"]:
            if not flags["image"]:
                raise DeploymentError("Saved image unavailable")
            return image_id if "--format" in args else json.dumps([image])
        if args[:2] == ["volume", "inspect"]:
            if not flags["volume"]:
                raise DeploymentError("Retained volume unavailable")
            return json.dumps([{"Name": args[-1], "CreatedAt": "original", "Driver": "local", "Scope": "local", "Options": None,
                "Labels": {"com.docker.compose.project": project}}])
        if args[:2] == ["network", "inspect"]:
            return json.dumps([{"Id": "d" * 64, "Driver": "bridge", "Options": {},
                "Labels": {"com.docker.compose.project": project, "com.docker.compose.network": "default"}}])
        if args[:2] == ["volume", "ls"]:
            return "\n".join(volumes)
        if args[:2] == ["volume", "create"]:
            volumes[args[-1]] = tmp_path / args[-1]
            volumes[args[-1]].mkdir()
            return args[-1]
        if args[0] in {"stop", "start"}:
            assert args[-1] == info["Id"]
            info["State"]["Running"] = args[0] == "start"
            return ""
        if args[0] == "rm":
            assert len(args) == 2 and info and args[-1] == info["Id"] and not info["State"]["Running"]
            flags["container"] = None
            if flags["crash_rm"]:
                flags["crash_rm"] = False
                raise SystemExit("Actual test deletion followed by worker interruption")
            return ""
        if args[0] == "load":
            return ""
        raise AssertionError(args)

    def helper(runtime, volume, destination, restore=False):
        target = volumes[volume]
        if restore:
            with tarfile.open(destination / "dashboard-volume.tar") as archive:
                archive.extractall(target, filter="data")
        else:
            with closing(sqlite3.connect(target / "stackarr.db")) as source, closing(sqlite3.connect(destination / "stackarr.db")) as copied:
                source.backup(copied)
            shutil.copyfile(target / "secrets.key", destination / "secrets.key")
            with tarfile.open(destination / "dashboard-volume.tar", "w") as archive:
                archive.add(destination / "stackarr.db", arcname="stackarr.db")
                archive.add(destination / "secrets.key", arcname="secrets.key")
                archive.add(target / "retained-backup.enc", arcname="retained-backup.enc")

    def protected(runtime):
        target = volumes[runtime["volume"]]
        return {"dashboard": fingerprint(target), "dashboard_key": digest(target / "secrets.key"),
                "controller": fingerprint(store.root), "controller_key": digest(store.root / "secrets.key"),
                "inventory": fingerprint(store.root, True), "dashboard_inventory": fingerprint(target, True), "container": flags["container"]["Id"]}

    def up(runtime, checking=False):
        updates.compose(runtime, checking)
        flags["counter"] += 1
        info = copy.deepcopy(original)
        info["Id"] = str(flags["counter"]) * 64
        info["Mounts"][0]["Name"] = runtime["volume"]
        info["Config"]["Env"] += ["STACKARR_RELEASE_ID=" + runtime["release"], "STACKARR_UPDATE_CHECKING=" + ("1" if checking else "0")]
        flags["container"] = info

    def controller_start(runtime, state=None, checking=False):
        flags.update(controller=True, controller_state=state or store.root, checking=checking)

    def health(runtime, expected, checking):
        target = volumes[runtime["volume"]]
        if flags["poison_files"]:
            flags["poison_files"] = False
            (target / "retained-backup.enc").write_bytes(b"candidate damaged backup")
        if flags["poison"]:
            flags["poison"] = False
            changed = Store(target)
            config = changed.config()[1]
            config.dashboard.page_size = 43
            changed.save(config, changed.config()[0])
            raise DeploymentError("Candidate actually changed settings")
        assert fingerprint(target) == expected["dashboard"] and fingerprint(flags["controller_state"]) == expected["controller"]

    docker._call = call
    monkeypatch.setattr(updates, "helper", helper)
    def files(self, runtime):
        import tempfile
        with tempfile.TemporaryDirectory(dir=updates.home) as directory:
            helper(runtime, runtime["volume"], __import__("pathlib").Path(directory))
            return archive_files(__import__("pathlib").Path(directory) / "dashboard-volume.tar")
    monkeypatch.setattr(SelfRemoval, "files", files)
    monkeypatch.setattr(updates, "protected", protected)
    monkeypatch.setattr(updates, "controller_probe", lambda r: {"executable": digest(directory / "StackarrPreview.exe"), "checking": flags["checking"]})
    monkeypatch.setattr(updates, "listening", lambda port: flags["controller"] if port == 29014 else bool(flags["container"] and flags["container"]["State"]["Running"]))
    monkeypatch.setattr(updates, "stop_controller", lambda job: flags.update(controller=False))
    monkeypatch.setattr(updates, "stop_dashboard", lambda runtime: flags["container"]["State"].update(Running=False) if flags["container"] else None)
    monkeypatch.setattr(updates, "controller_start", controller_start)
    monkeypatch.setattr(updates, "up", up)
    monkeypatch.setattr(updates, "health", health)
    monkeypatch.setattr(updates, "launch", lambda *args, **kwargs: None)
    monkeypatch.setattr("stackarr.self_removal.available", lambda port: True)
    return updates, flags, calls, volumes


def remove(updates):
    identity = updates.approve(updates.review("remove"))["id"]
    updates.execute(identity)
    return read(updates.home / "jobs" / identity / "job.json")


def test_removal_keeps_account_credentials_backups_and_requires_reviewed_reinstall(removal):
    updates, flags, calls, volumes = removal
    original = updates.active()
    expected = fingerprint(volumes[original["volume"]])
    job = remove(updates)
    assert job["phase"] == "succeeded" and pending(updates.root) is None
    assert not (updates.home / "active-job.json").exists()
    assert flags["container"] is None and not flags["controller"]
    assert fingerprint(volumes[original["volume"]]) == expected
    assert (volumes[original["volume"]] / "retained-backup.enc").read_bytes() == b"original configuration backup bytes"
    with pytest.raises(StackarrRemoved):
        updates.start()
    with pytest.raises(DeploymentError):
        SelfUpdates.recipe(read(updates.root / "compose.json"), updates.root, 29140, 29014)
    reinstall = updates.approve(updates.review("reinstall"))["id"]
    updates.execute(reinstall)
    assert read(updates.home / "jobs" / reinstall / "job.json")["phase"] == "succeeded"
    assert not (updates.root / "stackarr-removed.json").exists()
    assert fingerprint(volumes[updates.active()["volume"]]) == expected
    assert flags["controller"] and flags["container"]["State"]["Running"]
    assert not any(row[:2] in (["volume", "rm"], ["network", "rm"]) for row in calls)


@pytest.mark.parametrize("change", ["shared", "volume", "image", "environment", "mount", "privileged", "foreign"])
def test_changed_runtime_blocks_removal_before_downtime(removal, change):
    updates, flags, calls, _ = removal
    if change == "shared":
        flags["shared"] = True
    elif change in {"volume", "image"}:
        flags[change] = False
    elif change == "environment":
        flags["container"]["Config"]["Env"].append("UNREVIEWED=1")
    elif change == "mount":
        flags["container"]["Mounts"].append({"Destination": "/media", "Type": "bind"})
    elif change == "privileged":
        flags["container"]["HostConfig"]["Privileged"] = True
    else:
        flags["container"]["Config"]["Labels"]["com.docker.compose.project"] = "unrelated"
    with pytest.raises(DeploymentError):
        updates.review("remove")
    assert flags["controller"] and flags["container"]["State"]["Running"]
    assert not any(row[0] in {"stop", "rm", "start", "load"} for row in calls)


@pytest.mark.parametrize("deleted", [False, True])
def test_interrupted_removal_never_replays_deletion(removal, monkeypatch, deleted):
    updates, flags, calls, _ = removal
    identity = updates.approve(updates.review("remove"))["id"]
    if deleted:
        flags["crash_rm"] = True
    else:
        save = updates.save
        def interrupt(job, phase, message):
            save(job, phase, message)
            if phase == "checkpoint-saved":
                raise SystemExit("Before container deletion")
        monkeypatch.setattr(updates, "save", interrupt)
    with pytest.raises(SystemExit):
        updates.execute(identity)
    count = len([c for c in calls if c[0] == "rm"])
    updates.execute(identity, recover=True)
    assert len([c for c in calls if c[0] == "rm"]) == count
    result = read(updates.home / "jobs" / identity / "job.json")
    assert result["phase"] == ("succeeded" if deleted else "failed-recovered")
    assert bool(flags["container"]) is not deleted


def test_failed_reinstall_candidate_write_keeps_original_removed_state(removal):
    updates, flags, _, volumes = removal
    original = updates.active()
    expected = fingerprint(volumes[original["volume"]])
    remove(updates)
    flags["poison"] = True
    identity = updates.approve(updates.review("reinstall"))["id"]
    updates.execute(identity)
    assert read(updates.home / "jobs" / identity / "job.json")["phase"] == "failed-recovered"
    assert flags["container"] is None and not flags["controller"]
    assert updates.active() == original and fingerprint(volumes[original["volume"]]) == expected
    assert (updates.root / "stackarr-removed.json").exists()
    assert updates.review("reinstall")["source"] == original


def test_reinstall_checks_backup_files_even_when_database_health_passes(removal):
    updates, flags, _, volumes = removal
    original = updates.active()
    remove(updates)
    flags["poison_files"] = True
    identity = updates.approve(updates.review("reinstall"))["id"]
    updates.execute(identity)
    result = read(updates.home / "jobs" / identity / "job.json")
    assert result["phase"] == "failed-recovered" and "configuration files changed" in result["failure"]
    assert flags["container"] is None and not flags["controller"]
    assert (volumes[original["volume"]] / "retained-backup.enc").read_bytes() == b"original configuration backup bytes"


def test_reinstall_commit_interruption_after_marker_clear_recovers_removed_state(removal, monkeypatch):
    updates, flags, _, _ = removal
    remove(updates)
    identity = updates.approve(updates.review("reinstall"))["id"]
    finish = SelfRemoval.finish_reinstall
    def interrupted(self, job):
        finish(self, job)
        raise SystemExit("After marker removal, before terminal journal save")
    monkeypatch.setattr(SelfRemoval, "finish_reinstall", interrupted)
    with pytest.raises(SystemExit):
        updates.execute(identity)
    assert not (updates.root / "stackarr-removed.json").exists()
    updates.execute(identity, recover=True)
    assert read(updates.home / "jobs" / identity / "job.json")["phase"] == "failed-recovered"
    assert (updates.root / "stackarr-removed.json").exists()
    assert flags["container"] is None and not flags["controller"]


@pytest.mark.parametrize("damage", ["port", "checkpoint", "retained-settings"])
def test_unsafe_reinstall_is_rejected_without_overwriting_retained_data(removal, monkeypatch, damage):
    updates, flags, _, volumes = removal
    job = remove(updates)
    if damage == "port":
        monkeypatch.setattr("stackarr.self_removal.available", lambda port: False)
    elif damage == "checkpoint":
        (updates.home / "jobs" / job["id"] / "checkpoint.enc").write_bytes(b"changed")
    else:
        store = Store(volumes[updates.active()["volume"]])
        store.save(store.config()[1], store.config()[0], {"sonarr": {"api_key": "newer retained credential"}})
    expected = fingerprint(volumes[updates.active()["volume"]])
    with pytest.raises((DeploymentError, Conflict)):
        updates.review("reinstall")
    assert not flags["controller"] and flags["container"] is None
    assert fingerprint(volumes[updates.active()["volume"]]) == expected


def test_native_reinstall_review_is_encrypted_expiring_and_single_use(removal, monkeypatch):
    updates, _, _, _ = removal
    remove(updates)
    monkeypatch.setattr("stackarr.reinstall_wizard.SelfUpdates", lambda root: updates)
    value = review(updates.root)
    saved = updates.home / "reinstall-reviews" / (value["id"] + ".enc")
    assert b"synthetic retained credential" not in saved.read_bytes()
    assert approve(value)["id"]
    with pytest.raises(Conflict):
        approve(value)


def test_native_reinstall_review_expiry_cannot_start_a_job(removal, monkeypatch):
    updates, flags, _, _ = removal
    remove(updates)
    monkeypatch.setattr("stackarr.reinstall_wizard.SelfUpdates", lambda root: updates)
    value = review(updates.root)
    monkeypatch.setattr("stackarr.reinstall_wizard.time.time", lambda: 9999999999)
    with pytest.raises(Conflict, match="expired"):
        approve(value)
    assert flags["container"] is None and not flags["controller"] and pending(updates.root) is None


@pytest.mark.parametrize("changed", [False, True])
def test_controller_review_checks_its_local_identity_without_recursive_rpc(removal, monkeypatch, changed):
    updates, _, _, _ = removal
    updates.controller_identity = {"executable": "changed" if changed else digest(updates.package_root / "StackarrPreview.exe"), "checking": False}
    def recursive(*args):
        raise AssertionError("An in-controller review must not recursively acquire its own RPC lane")
    monkeypatch.setattr(updates, "controller_probe", recursive)
    if changed:
        with pytest.raises(DeploymentError, match="controller does not match"):
            updates.review("remove")
    else:
        assert updates.review("remove")["action"] == "remove"


def test_stale_removal_approval_does_not_restart_a_manually_stopped_dashboard(removal):
    updates, flags, calls, _ = removal
    identity = updates.approve(updates.review("remove"))["id"]
    flags["container"]["State"]["Running"] = False
    updates.execute(identity)
    assert read(updates.home / "jobs" / identity / "job.json")["phase"] == "failed-recovered"
    assert not flags["container"]["State"]["Running"]
    assert not any(c[0] in {"start", "rm", "stop"} for c in calls)


def test_reinstall_refuses_a_container_created_after_approval(removal):
    updates, flags, calls, _ = removal
    original = copy.deepcopy(flags["container"])
    remove(updates)
    identity = updates.approve(updates.review("reinstall"))["id"]
    original["Id"] = "f" * 64
    flags["container"] = original
    before = len(calls)
    updates.execute(identity)
    assert read(updates.home / "jobs" / identity / "job.json")["phase"] == "needs-recovery"
    assert flags["container"]["Id"] == "f" * 64 and flags["container"]["State"]["Running"]
    assert not any(c[0] in {"stop", "rm", "load"} for c in calls[before:])
