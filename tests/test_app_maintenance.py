import copy
import io
import json
import tarfile

import pytest

from stackarr.app_backups import AppBackups
from stackarr.app_maintenance import AppMaintenance
from stackarr.config import Config
from stackarr.deployment import DeploymentError, Deployments
from stackarr.installer import compose_plan
from stackarr.store import Conflict, Store


@pytest.fixture
def maintenance(tmp_path, monkeypatch):
    config = Config()
    config.storage.data_root = str(tmp_path / "media")
    (tmp_path / "media").mkdir()
    config.integrations["plex"].enabled = True
    config.integrations["plex"].mode = "install"
    config.integrations["plex"].port = 32400
    service = Deployments(Store(tmp_path / "controller/state"))
    identity, project = "a" * 32, "stackarr-owned-" + "a" * 32
    plan = compose_plan(config)["compose"]
    plan["networks"] = {"control": {}}
    recipe = plan["services"]["plex"]
    recipe.update(image="plexinc/pms-docker@sha256:" + "d" * 64, platform="linux/amd64",
                  logging={"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}})
    context = {"name": "fixture", "endpoint": "unix:///fixture"}
    payload = {"config": config.model_dump(), "apps": ["plex"], "compose": plan, "context": context}
    with service.store.db() as db:
        db.execute("INSERT INTO deployments VALUES(?,?,?,?,?,?)", (identity, "needs-setup", "Ready", 0, 0, json.dumps(payload)))
    directory = service.store.root / "deployments" / identity
    directory.mkdir(parents=True)
    (directory / "compose.json").write_text(json.dumps(plan, sort_keys=True))
    image = {"Id": "sha256:" + "e" * 64, "Os": "linux", "Architecture": "amd64", "Config": {"Env": [], "User": "", "Cmd": None, "Entrypoint": None}}
    original = {"Id": "b" * 64, "Image": image["Id"], "Config": {"Image": recipe["image"],
        "Env": [f"{k}={v}" for k, v in recipe["environment"].items()], "User": "", "Cmd": None, "Entrypoint": None,
        "Labels": {"com.docker.compose.project": project, "com.docker.compose.service": "plex"}},
        "HostConfig": {"PortBindings": {"32400/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32400"}]},
            "SecurityOpt": recipe["security_opt"], "RestartPolicy": {"Name": "unless-stopped"}},
        "Mounts": [{"Destination": "/config", "Type": "volume", "Name": project + "_plex-config"},
            {"Destination": "/data", "Type": "bind", "Source": config.storage.data_root, "RW": False}],
        "NetworkSettings": {"Networks": {project + "_control": {}}}, "State": {"Running": True, "ExitCode": 0}}
    flags = {"container": copy.deepcopy(original), "shared": False, "volume": True, "count": 0, "poison": False, "crash": False,
        "files": {"settings": b"original settings and login", "library.db": b"original library records"},
        "image": image, "cache": None, "cache_shared": False, "cache_options": None}
    volume = {"Name": project + "_plex-config", "CreatedAt": "original", "Driver": "local", "Scope": "local", "Options": None,
        "Labels": {"com.docker.compose.project": project, "com.docker.compose.volume": "plex-config"}}
    calls = []

    def docker(args, **kwargs):
        calls.append(args)
        assert args[:2] == ["--context", "fixture"]
        verb = args[2]
        info = flags["container"]
        if verb == "ps":
            ids = [info["Id"]] if info else []
            if flags["shared"] and any("volume=" in arg for arg in args):
                ids.append("c" * 64)
            if flags["cache_shared"] and args[-1] == "volume=" + flags["cache"]:
                ids.append("d" * 64)
            return "\n".join(ids)
        if verb == "inspect":
            if not info:
                raise DeploymentError("Missing container")
            return json.dumps([info])
        if args[2:4] == ["image", "inspect"]:
            return json.dumps([image])
        if args[2:4] == ["volume", "inspect"]:
            if not flags["volume"]:
                raise DeploymentError("Settings volume missing")
            if args[-1] == flags["cache"]:
                return json.dumps([{"Name": flags["cache"], "CreatedAt": "original cache", "Driver": "local", "Scope": "local",
                    "Options": flags["cache_options"], "Labels": {"com.docker.volume.anonymous": ""}}])
            return json.dumps([volume])
        if args[2:4] == ["network", "inspect"]:
            return json.dumps([{"Id": "f" * 64, "Driver": "bridge", "Options": {},
                "Labels": {"com.docker.compose.project": project, "com.docker.compose.network": "control"}}])
        if verb in {"stop", "start"}:
            assert info and args[-1] == info["Id"]
            info["State"]["Running"] = verb == "start"
            return ""
        if verb == "rm":
            assert len(args) == 4 and info and args[-1] == info["Id"] and not info["State"]["Running"]
            flags["container"] = None
            return ""
        if verb == "compose":
            assert ("--no-deps" in args or "create" in args) and "--no-build" in args and args[args.index("--pull") + 1] == "never"
            saved = json.loads(__import__("pathlib").Path(args[args.index("-f") + 1]).read_text())
            assert set(saved["services"]) == {"plex"} and saved["volumes"]["plex-config"]["external"]
            assert not flags["container"]
            flags["count"] += 1
            flags["container"] = copy.deepcopy(original)
            flags["container"]["State"]["Running"] = "create" not in args
            flags["container"]["Id"] = str(flags["count"]) * 64
            flags["container"]["Config"]["Labels"].update(saved["services"]["plex"]["labels"])
            if flags["cache"]:
                assert any(value.get("name") == flags["cache"] and value.get("external") for value in saved["volumes"].values())
                flags["container"]["Mounts"].append({"Destination": "/transcode", "Type": "volume", "Name": flags["cache"], "RW": True})
            if flags["poison"] and flags["count"] == 1:
                flags["files"]["settings"] = b"candidate changed settings"
            if flags["crash"] and flags["count"] == 1:
                raise SystemExit("Simulated process interruption after real candidate creation")
            return ""
        raise AssertionError(args)

    def helper(self, payload, key, directory, restore=False):
        assert key == "plex"
        if restore:
            with tarfile.open(directory / "volume.tar") as archive:
                flags["files"] = {row.name: archive.extractfile(row).read() for row in archive if row.isfile()}
        else:
            with tarfile.open(directory / "volume.tar", "w") as archive:
                for name, data in flags["files"].items():
                    row = tarfile.TarInfo(name)
                    row.size = len(data)
                    archive.addfile(row, io.BytesIO(data))

    monkeypatch.setattr(service, "context", lambda: context)
    monkeypatch.setattr(service, "_call", docker)
    monkeypatch.setattr("stackarr.app_maintenance.available", lambda port: True)
    monkeypatch.setattr(AppBackups, "helper", helper)
    monkeypatch.setattr(AppMaintenance, "health", lambda *args, **kwargs: True)
    monkeypatch.setattr(AppMaintenance, "protected", lambda self, *args: self.deployments.actions.fingerprint({k: v.decode() for k, v in flags["files"].items()}))
    return service, identity, flags, calls


@pytest.mark.asyncio
async def test_reviewed_repair_and_remove_keep_settings_library_and_backup(maintenance):
    service, identity, flags, calls = maintenance
    before = copy.deepcopy(flags["files"])
    original = flags["container"]["Id"]
    for action in ("repair", "remove", "repair"):
        review = service.actions.review(identity, "plex", action)
        public = json.dumps(service.actions.public(review))
        assert "original settings" not in public and "library.db" not in public and original not in public
        service.actions.enqueue(review)
        await service.actions.run_one()
        assert service.actions.rows()[0]["state"] == "succeeded"
        assert flags["files"] == before
        assert bool(flags["container"]) == (action != "remove")
    assert flags["container"]["Id"] != original
    assert len(AppBackups(service).rows()) == 3
    assert all(args[2:4] not in (["volume", "rm"], ["network", "rm"], ["image", "rm"]) for args in calls)


@pytest.mark.parametrize("change", ["shared", "missing-volume", "missing-media", "foreign", "extra-mount", "environment", "port"])
def test_unsafe_or_changed_runtime_rejected_before_writes(maintenance, monkeypatch, change):
    service, identity, flags, calls = maintenance
    if change == "shared":
        flags["shared"] = True
    elif change == "missing-volume":
        flags["volume"] = False
    elif change == "missing-media":
        __import__("pathlib").Path(flags["container"]["Mounts"][1]["Source"]).rmdir()
    elif change == "foreign":
        flags["container"]["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
    elif change == "extra-mount":
        flags["container"]["Mounts"].append({"Destination": "/other", "Type": "volume", "Name": "private"})
    elif change == "environment":
        flags["container"]["Config"]["Env"].append("UNREVIEWED=private")
    else:
        flags["container"] = None
        monkeypatch.setattr("stackarr.app_maintenance.available", lambda port: False)
    with pytest.raises((DeploymentError, Conflict)):
        service.actions.review(identity, "plex", "repair")
    assert all(args[2] in {"ps", "inspect", "image", "volume", "network"} for args in calls)


@pytest.mark.asyncio
async def test_changed_review_is_rejected_before_stop_or_snapshot(maintenance):
    service, identity, flags, calls = maintenance
    review = service.actions.review(identity, "plex", "repair")
    service.actions.enqueue(review)
    flags["container"]["Id"] = "c" * 64
    await service.actions.run_one()
    assert service.actions.rows()[0]["state"] == "failed"
    assert all(args[2] in {"ps", "inspect", "image", "volume", "network"} for args in calls)


@pytest.mark.asyncio
async def test_wrong_candidate_settings_restore_verified_before_repair_snapshot(maintenance):
    service, identity, flags, _ = maintenance
    before = copy.deepcopy(flags["files"])
    flags["poison"] = True
    service.actions.enqueue(service.actions.review(identity, "plex", "repair"))
    await service.actions.run_one()
    assert service.actions.rows()[0]["state"] == "failed-recovered"
    assert flags["files"] == before and flags["container"]["State"]["Running"]
    assert {row["kind"] for row in AppBackups(service).rows()} == {"before-repair", "before-maintenance-recovery"}


def test_process_interruption_blocks_other_actions_and_requires_reviewed_recovery(maintenance):
    service, identity, flags, _ = maintenance
    before = copy.deepcopy(flags["files"])
    review = service.actions.review(identity, "plex", "repair")
    operation = service.actions.enqueue(review)
    with service.store.db() as db:
        db.execute("UPDATE deployment_actions SET state='running' WHERE id=?", (operation,))
    flags["crash"] = True
    with pytest.raises(SystemExit):
        AppMaintenance(service).execute(review, operation)
    # Startup marks the durable existing journal; no Docker operation is replayed.
    from stackarr.lifecycle import Lifecycle

    service.actions = Lifecycle(service)
    assert service.actions.rows()[0]["state"] == "needs-recovery"
    with pytest.raises(Conflict, match="maintenance"):
        service.actions.enqueue(service.actions.review(identity, "plex", "stop"))
    recovery = service.actions.review(identity, "plex", "repair-recover", operation)
    result = AppMaintenance(service).execute(recovery, "9" * 32)
    assert "recovered" in result and flags["files"] == before
    assert service.actions.rows()[0]["state"] == "recovered"


@pytest.mark.parametrize("removed", [False, True])
def test_interrupted_removal_never_replays_deletion_and_keeps_settings(maintenance, monkeypatch, removed):
    service, identity, flags, calls = maintenance
    before, original = copy.deepcopy(flags["files"]), flags["container"]["Id"]
    review = service.actions.review(identity, "plex", "remove")
    operation = service.actions.enqueue(review)
    with service.store.db() as db:
        db.execute("UPDATE deployment_actions SET state='running' WHERE id=?", (operation,))
    save, docker = AppMaintenance.save, service._call

    def interrupt_before(self, operation, review, phase):
        save(self, operation, review, phase)
        if phase == "removing-container" and not removed:
            raise SystemExit("Interrupted before deletion")

    def interrupt_after(args, **kwargs):
        result = docker(args, **kwargs)
        if args[2] == "rm" and removed:
            raise SystemExit("Interrupted after deletion")
        return result

    monkeypatch.setattr(AppMaintenance, "save", interrupt_before)
    monkeypatch.setattr(service, "_call", interrupt_after)
    with pytest.raises(SystemExit):
        AppMaintenance(service).execute(review, operation)
    from stackarr.lifecycle import Lifecycle

    count = len(calls)
    service.actions = Lifecycle(service)
    assert len(calls) == count and service.actions.rows()[0]["state"] == "needs-recovery"
    with pytest.raises(Conflict, match="maintenance"):
        service.actions.enqueue(service.actions.review(identity, "plex", "repair"))
    recovery = service.actions.review(identity, "plex", "repair-recover", operation)
    result = AppMaintenance(service).execute(recovery, "9" * 32)
    assert flags["files"] == before and len(AppBackups(service).rows()) == 1
    assert service.actions.rows()[0]["state"] == "recovered"
    if removed:
        assert flags["container"] is None and "Removal completed" in result
    else:
        assert flags["container"]["Id"] == original and flags["container"]["State"]["Running"]
        assert "original container" in result
    assert sum(args[2] == "rm" for args in calls) == int(removed)
    assert not any(args[2] == "compose" for args in calls)


@pytest.mark.asyncio
async def test_absent_app_keeps_working_configuration_backups(maintenance):
    service, identity, flags, _ = maintenance
    flags["container"] = None
    review = AppBackups(service).review(identity)
    assert review["containers"]["plex"] == {"id": None, "running": False}
    AppBackups(service).execute(review)
    assert flags["container"] is None and AppBackups(service).rows()


@pytest.mark.parametrize("changed", [False, True])
def test_explicit_docker_default_network_options_are_allowed_but_custom_options_block(maintenance, monkeypatch, changed):
    service, identity, _, _ = maintenance
    original = service._call

    def docker(args, **kwargs):
        result = original(args, **kwargs)
        if args[2:4] == ["network", "inspect"]:
            rows = json.loads(result)
            rows[0]["Options"] = {"com.docker.network.enable_ipv4": "true", "com.docker.network.enable_ipv6": "false"}
            if changed:
                rows[0]["Options"]["com.docker.network.bridge.enable_icc"] = "false"
            return json.dumps(rows)
        return result

    monkeypatch.setattr(service, "_call", docker)
    if changed:
        with pytest.raises(DeploymentError, match="network"):
            service.actions.review(identity, "plex", "repair")
    else:
        assert service.actions.review(identity, "plex", "repair")["resources"]["network"]


@pytest.mark.asyncio
async def test_repair_preserves_previously_stopped_state(maintenance):
    service, identity, flags, calls = maintenance
    flags["container"]["State"]["Running"] = False
    service.actions.enqueue(service.actions.review(identity, "plex", "repair"))
    await service.actions.run_one()
    assert service.actions.rows()[0]["state"] == "succeeded"
    assert not flags["container"]["State"]["Running"]
    assert not any(args[2] == "start" or args[2] == "compose" and "up" in args for args in calls)


def plex_cache(flags):
    flags["cache"] = "c" * 64
    flags["image"]["Config"]["Volumes"] = {"/config": {}, "/transcode": {}}
    flags["container"]["Mounts"].append({"Destination": "/transcode", "Type": "volume", "Name": flags["cache"], "RW": True})


@pytest.mark.asyncio
async def test_plex_image_declared_anonymous_cache_is_retained_across_repair_remove_and_bring_back(maintenance):
    service, identity, flags, _ = maintenance
    plex_cache(flags)
    for action in ("repair", "remove", "repair"):
        review = service.actions.review(identity, "plex", action)
        assert review["resources"]["auxiliary"]["/transcode"]["name"] == flags["cache"]
        service.actions.enqueue(review)
        await service.actions.run_one()
        assert service.actions.rows()[0]["state"] == "succeeded"
    assert flags["container"]["Mounts"][-1]["Name"] == flags["cache"]


@pytest.mark.parametrize("unsafe", ["shared", "bind"])
def test_unknown_or_shared_plex_scratch_storage_is_never_adopted(maintenance, unsafe):
    service, identity, flags, calls = maintenance
    plex_cache(flags)
    if unsafe == "shared":
        flags["cache_shared"] = True
    else:
        flags["cache_options"] = {"device": "unreviewed host path"}
    with pytest.raises(DeploymentError, match="scratch"):
        service.actions.review(identity, "plex", "repair")
    assert all(args[2] in {"ps", "inspect", "image", "volume", "network"} for args in calls)
