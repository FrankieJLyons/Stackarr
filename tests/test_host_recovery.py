import copy
import io
import json
import tarfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from stackarr.app_backups import AppBackups, digest
from stackarr.config import Config
from stackarr.deployment import DeploymentError, Deployments, images
from stackarr.host_recovery import HostBackups, Recovery, canonical
from stackarr.installer import compose_plan
from stackarr.store import Store


@pytest.fixture
def recovery_lab(tmp_path, monkeypatch):
    source = Store(tmp_path / "original-controller")
    dashboard = Store(tmp_path / "original-dashboard")
    for store in (source, dashboard):
        with store.db() as db:
            db.execute("INSERT INTO sessions VALUES('obsolete','obsolete',9999999999)")
            db.execute("INSERT INTO account VALUES(1,'original-salt','original-hash')")
    media = tmp_path / "preserved media"
    media.mkdir()
    (media / "keep.txt").write_text("keep original media")
    config = Config()
    config.storage.data_root = str(media)
    for key in ("sonarr", "radarr", "prowlarr", "qbittorrent"):
        config.integrations[key].enabled = True
        config.integrations[key].mode = "install"
    compose = compose_plan(config)["compose"]
    compose["networks"] = {"control": {}}
    for key, service in compose["services"].items():
        service.update(image=images()[key], platform="linux/amd64", logging={"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}})
    payload = {"config": config.model_dump(), "apps": list(compose["services"]), "compose": compose}
    stage = tmp_path / "contents"
    stage.mkdir()
    for store, name in ((source, "controller"), (dashboard, "dashboard")):
        import shutil
        shutil.copyfile(store.path, stage / (name + ".db"))
    (stage / "dashboard.key").write_bytes((dashboard.root / "secrets.key").read_bytes())
    key = (source.root / "secrets.key").read_bytes()
    crypt = SimpleNamespace(store=SimpleNamespace(cipher=Fernet(key)))
    hashes = {}
    for app in payload["apps"]:
        path = tmp_path / (app + ".tar")
        with tarfile.open(path, "w") as tar:
            member = tarfile.TarInfo("settings.json")
            member.size = 4
            tar.addfile(member, io.BytesIO(b"safe"))
        hashes[app] = digest(path)
        AppBackups.crypt(crypt, path, stage / ("b" * 32 + "-" + app + ".enc"))
    metadata = {"format": 1, "namespace": "c" * 32, "id": "d" * 32, "snapshots": [
        {"backup": "b" * 32, "manifest": {"deployment": "a" * 32, "apps": payload["apps"], "installation": payload, "hashes": hashes},
         "running": {k: True for k in payload["apps"]}}],
        "hashes": {p.name: digest(p) for p in stage.iterdir()}}
    package = tmp_path / "package"
    package.mkdir()
    for name in ("StackarrPreview.exe", "stackarr-image.tar", "Start-StackarrPreview.ps1"):
        (package / name).write_bytes(b"synthetic package fixture")
    (package / "manifest.json").write_text(json.dumps({"schema": 1, "image_id": "sha256:" + "e" * 64,
        "files": {p.name: digest(p) for p in package.iterdir()}}))
    keyfile = tmp_path / "recovery-key.json"
    keyfile.write_text(json.dumps({"format": 1, "namespace": metadata["namespace"], "key": key.decode()}))
    bundle = tmp_path / "fixture.stackarr-recovery"

    def repack():
        (stage / "metadata.json").write_text(json.dumps(metadata))
        archive = tmp_path / "host.tar"
        with tarfile.open(archive, "w") as tar:
            for p in stage.iterdir():
                tar.add(p, arcname=p.name)
        bundle.unlink(missing_ok=True)
        AppBackups.crypt(crypt, archive, bundle)
    repack()
    monkeypatch.setattr(Deployments, "context", lambda self: {"name": "fixture", "endpoint": "unix:///fixture"})
    calls = []
    monkeypatch.setattr(Deployments, "_call", lambda self, args, **kw: calls.append(args) or "")
    monkeypatch.setattr("stackarr.ports.available", lambda port: True)
    return Recovery(bundle, keyfile, package), metadata, stage, repack, media, calls


def test_complete_checkpoint_authenticates_app_archives_and_revokes_sessions(recovery_lab):
    recovery, _, _, _, media, calls = recovery_lab
    with recovery.opened() as (stage, metadata):
        import sqlite3
        for name in ("controller", "dashboard"):
            with closing(sqlite3.connect(stage / (name + ".db"))) as db:
                assert not db.execute("SELECT * FROM sessions").fetchall()
                assert db.execute("SELECT hash FROM account").fetchone()[0] == "original-hash"
        assert (stage / ("a" * 32) / "sonarr" / "volume.tar").is_file()
    review = recovery.review(media.parent / "new state", {str(media): str(media)}, 29100, 29010)
    assert review["apps"] == sorted(metadata["snapshots"][0]["manifest"]["apps"])
    assert all(args[2] in {"ps", "volume", "network"} for args in calls)
    assert (media / "keep.txt").read_text() == "keep original media"


@pytest.mark.parametrize("damage", ["wrong-key", "truncated", "changed-app", "missing-file", "extra-service", "privileged", "extra-bind"])
def test_untrusted_or_incomplete_backup_fails_before_any_docker_writes(recovery_lab, damage):
    recovery, metadata, stage, repack, media, calls = recovery_lab
    if damage == "wrong-key":
        recovery.crypt.store.cipher = Fernet(Fernet.generate_key())
    elif damage == "truncated":
        recovery.bundle.write_bytes(recovery.bundle.read_bytes()[:-10])
    elif damage == "changed-app":
        (stage / ("b" * 32 + "-sonarr.enc")).write_bytes(b"changed")
        repack()
    elif damage == "missing-file":
        (stage / "dashboard.key").unlink()
        repack()
    else:
        services = metadata["snapshots"][0]["manifest"]["installation"]["compose"]["services"]
        if damage == "extra-service":
            services["unknown"] = copy.deepcopy(services["sonarr"])
        elif damage == "privileged":
            services["sonarr"]["privileged"] = True
        else:
            services["sonarr"]["volumes"].append({"type": "bind", "source": "/", "target": "/host"})
        repack()
    with pytest.raises(DeploymentError):
        recovery.review(media.parent / "new-state", {str(media): str(media)})
    assert not calls


@pytest.mark.parametrize("existing", ["container", "volume", "network", "unlabelled-volume"])
def test_existing_host_resources_are_never_adopted(recovery_lab, monkeypatch, existing):
    recovery, _, _, _, media, _ = recovery_lab
    def docker(self, args, **kw):
        command = args[2:]
        if command[0] == "ps" and existing == "container":
            return "existing-container"
        if command[0] == "network" and existing == "network":
            return "existing-network"
        if command[:2] == ["volume", "ls"] and existing == "volume":
            return "existing-volume"
        if command == ["volume", "ls", "-q"] and existing == "unlabelled-volume":
            return "stackarr-owned-" + "a" * 32 + "_sonarr-config"
        return ""
    monkeypatch.setattr(Deployments, "_call", docker)
    with pytest.raises(DeploymentError, match="exist"):
        recovery.review(media.parent / "new-state", {str(media): str(media)})


def test_busy_original_app_port_and_nonempty_state_block_recovery(recovery_lab, monkeypatch):
    recovery, _, _, _, media, calls = recovery_lab
    monkeypatch.setattr("stackarr.ports.available", lambda p: p != 8989)
    with pytest.raises(DeploymentError, match="port is busy"):
        recovery.review(media.parent / "new-state", {str(media): str(media)})
    assert not calls
    with pytest.raises(DeploymentError, match="empty"):
        recovery.review(media, {str(media): str(media)})


def test_checkpoint_uses_only_catalog_recipes_for_all_nine_apps():
    config = Config()
    config.storage.data_root = str(Path.cwd())
    for app in config.integrations.values():
        app.enabled, app.mode = True, "install"
    compose = compose_plan(config)["compose"]
    compose["networks"] = {"control": {}}
    for key, service in compose["services"].items():
        service.update(image=images()[key], platform="linux/amd64", logging={"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}})
    assert canonical({"config": config.model_dump(), "apps": list(compose["services"]), "compose": compose}) == compose


def test_dashboard_discovery_accepts_verified_desktop_mount_spelling(tmp_path, monkeypatch):
    import hashlib
    import os

    host = Deployments(Store(tmp_path / "controller/state"))
    shared = tmp_path / "controller/shared"
    shared.mkdir()
    (shared / "rpc.key").write_bytes(b"synthetic enrollment")
    (shared / "controller.crt").write_bytes(b"synthetic certificate")
    source = str(shared)
    if os.name == "nt":
        source = "/run/desktop/mnt/host/" + source[0].lower() + source[2:].replace("\\", "/")
    info = {"Id": "a" * 64, "Config": {"Labels": {"com.docker.compose.service": "stackarr"}},
        "Mounts": [{"Destination": "/run/stackarr-controller", "Source": source, "RW": False},
                   {"Destination": "/var/lib/stackarr", "Type": "volume"}],
        "HostConfig": {"PortBindings": {"8787/tcp": [{"HostIp": "127.0.0.1", "HostPort": "29210"}]}},
        "State": {"Running": True}}
    expected = hashlib.sha256(b"synthetic enrollment" + b"synthetic certificate").hexdigest()
    monkeypatch.setattr(host, "_call", lambda args, **kw: "a" * 64 if args[0] == "ps" else json.dumps([info]) if args[0] == "inspect" else expected)
    assert HostBackups(host, 29210).dashboard() == "a" * 64
    expected = "changed enrollment"
    with pytest.raises(DeploymentError, match="enrollment changed"):
        HostBackups(host, 29210).dashboard()


def test_host_backup_inventory_includes_installations_older_than_recent_list(tmp_path, monkeypatch):
    host = Deployments(Store(tmp_path / "state"))
    with host.store.db() as db:
        db.execute("INSERT INTO deployments VALUES(?,?,?,?,?,?)", ("a" * 32, "needs-setup", "Ready", 0, 0, '{"apps":["kuma"]}'))
        for index in range(25):
            db.execute("INSERT INTO deployments VALUES(?,?,?,?,?,?)", (f"{index:032x}", "superseded", "Replaced", index + 1, 0, '{"apps":["seerr"]}'))
    assert all(r["id"] != "a" * 32 for r in host.rows())
    monkeypatch.setattr(AppBackups, "review", lambda self, identity: {"deployment": identity, "apps": ["kuma"]})
    monkeypatch.setattr("stackarr.host_recovery.load_receipt", lambda *args: {})
    monkeypatch.setattr("stackarr.host_recovery.canonical", lambda *args: {})
    monkeypatch.setattr(HostBackups, "dashboard", lambda self: "b" * 64)
    monkeypatch.setattr(HostBackups, "dashboard_revision", lambda self: 1)
    assert HostBackups(host).review()["reviews"][0]["deployment"] == "a" * 32
