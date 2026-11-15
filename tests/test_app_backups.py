import io
import json
import tarfile

import pytest
from test_deployment_check import installed as installed

from stackarr.app_backups import AppBackups, validate_tar
from stackarr.deployment import DeploymentError


@pytest.fixture
def backup_lab(installed, monkeypatch):
    deployments, identity, info, calls = installed
    info["Id"] = "b" * 64
    files = {"settings.json": b'{"password":"private fixture","setting":7}', "library.db": b"original database fixture"}
    def docker(args, **kwargs):
        calls.append(args)
        if args[2] == "inspect":
            return json.dumps([info])
        if args[2:4] == ["volume", "inspect"]:
            return json.dumps([{"Labels": {"com.docker.compose.project": "stackarr-owned-" + identity, "com.docker.compose.volume": "plex-config"}}])
        if args[2] == "ps":
            return info["Id"]
        assert args[2] in {"start", "stop"}
        info["State"]["Running"] = args[2] == "start"
        return info["Id"]
    monkeypatch.setattr(deployments, "_call", docker)
    service = AppBackups(deployments)
    def helper(payload, key, directory, restore=False):
        assert not info["State"]["Running"]
        assert key == "plex"
        if restore:
            with tarfile.open(directory / "volume.tar") as archive:
                files.clear()
                files.update({member.name: archive.extractfile(member).read() for member in archive if member.isfile()})
        else:
            with tarfile.open(directory / "volume.tar", "w") as archive:
                for name, content in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
    monkeypatch.setattr(service, "helper", helper)
    return service, identity, info, files, calls


@pytest.mark.parametrize("running", [True, False])
def test_real_encrypted_snapshot_restores_settings_and_preserves_runtime_state(backup_lab, running):
    service, identity, info, files, calls = backup_lab
    info["State"]["Running"] = running
    expected = dict(files)
    service.execute(service.review(identity))
    backup = service.rows()[0]
    encrypted = service.root / backup["id"] / "plex.enc"
    assert b"private fixture" not in encrypted.read_bytes()
    files["settings.json"] = b"newer settings"
    files["newer-file"] = b"created after backup"
    service.execute(service.review(identity, backup["id"]))
    assert files == expected
    assert info["State"]["Running"] == running
    assert any(row["kind"] == "before-restore" for row in service.rows())
    assert all(args[2] in {"start", "stop", "inspect", "volume", "ps"} for args in calls)
    assert not list(service.root.glob("work-*"))


def test_corrupt_backup_rejected_before_downtime_or_writes(backup_lab):
    service, identity, _, files, calls = backup_lab
    service.execute(service.review(identity))
    backup = service.rows()[0]["id"]
    encrypted = service.root / backup / "plex.enc"
    encrypted.write_bytes(encrypted.read_bytes()[:-100])
    calls.clear()
    expected = dict(files)
    with pytest.raises(Exception):
        service.execute(service.review(identity, backup))
    assert files == expected
    assert not any(args[2] in {"stop", "start"} for args in calls)


def test_failed_restore_rolls_back_to_latest_settings(backup_lab, monkeypatch):
    service, identity, info, files, _ = backup_lab
    service.execute(service.review(identity))
    backup = service.rows()[0]["id"]
    files["settings.json"] = b"latest owner settings"
    expected = dict(files)
    helper = service.helper
    failed = False
    def fail_once(payload, key, directory, restore=False):
        nonlocal failed
        if restore and not failed:
            failed = True
            files.clear()
            raise RuntimeError("private extraction output")
        helper(payload, key, directory, restore)
    monkeypatch.setattr(service, "helper", fail_once)
    with pytest.raises(DeploymentError, match="before-restore configuration was recovered"):
        service.execute(service.review(identity, backup))
    assert files == expected and info["State"]["Running"]


def test_shared_volume_is_blocked_before_downtime(backup_lab, monkeypatch):
    service, identity, _, _, calls = backup_lab
    original = service.deployments._call
    monkeypatch.setattr(service.deployments, "_call", lambda args, **kw: "c" * 64 if args[2] == "ps" else original(args, **kw))
    with pytest.raises(DeploymentError, match="shared"):
        service.review(identity)
    assert not any(args[2] == "stop" for args in calls)


def test_failed_rollback_keeps_apps_stopped_and_safety_snapshot_available(backup_lab, monkeypatch):
    service, identity, info, _, _ = backup_lab
    service.execute(service.review(identity))
    backup = service.rows()[0]["id"]
    original = service.helper
    def fail_restore(payload, key, directory, restore=False):
        if restore:
            raise RuntimeError("private Docker failure")
        original(payload, key, directory, restore)
    monkeypatch.setattr(service, "helper", fail_restore)
    with pytest.raises(DeploymentError, match="Apps remain stopped"):
        service.execute(service.review(identity, backup))
    assert not info["State"]["Running"]
    assert any(row["kind"] == "before-restore" for row in service.rows())


@pytest.mark.parametrize("name,kind", [("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE), ("link", tarfile.SYMTYPE), ("device", tarfile.CHRTYPE)])
def test_unsafe_tar_entries_rejected(tmp_path, name, kind):
    path = tmp_path / "bad.tar"
    with tarfile.open(path, "w") as archive:
        member = tarfile.TarInfo(name)
        member.type = kind
        archive.addfile(member)
    with pytest.raises(DeploymentError):
        validate_tar(path)


def test_internal_leaf_log_symlink_is_supported(tmp_path):
    path = tmp_path / "logs.tar"
    with tarfile.open(path, "w") as archive:
        archive.addfile(tarfile.TarInfo("./logs/current.log"), io.BytesIO())
        link = tarfile.TarInfo("./logs/app.log")
        link.type, link.linkname = tarfile.SYMTYPE, "current.log"
        archive.addfile(link)
    validate_tar(path)


@pytest.mark.parametrize("target,child", [("../../escape", False), ("inside", True), ("link", False)])
def test_escaping_symlinks_link_chains_and_writes_through_links_rejected(tmp_path, target, child):
    path = tmp_path / "links.tar"
    with tarfile.open(path, "w") as archive:
        link = tarfile.TarInfo("link")
        link.type, link.linkname = tarfile.SYMTYPE, target
        archive.addfile(link)
        if child:
            archive.addfile(tarfile.TarInfo("link/file"), io.BytesIO())
    with pytest.raises(DeploymentError):
        validate_tar(path)
