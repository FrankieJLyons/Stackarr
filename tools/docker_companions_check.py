"""Scoped companion acceptance; source core apps are inspected and queried only."""

import argparse
import asyncio
import hashlib
import json
import shutil
import time
from pathlib import Path

from stackarr.app_backups import AppBackups
from stackarr.companions import APPS, Companions, cleanup_safe
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.kuma import Kuma
from stackarr.onboarding import SaveDraft, SetupDraft, initialize, save
from stackarr.store import Store

MAIN = Path("test-results/docker-plex-bc615eaf1fe6").resolve()
LAB = Path("test-results/docker-companions-20261017").resolve()
PORTS = {"tautulli": 42475, "kuma": 42476, "cleanuparr": 42477}


def media():
    return {str(p.relative_to(MAIN / "media")): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (MAIN / "media").rglob("*") if p.is_file()}


def prepare():
    target = LAB / "controller/state"
    assert not (LAB / "installation.json").exists(), "Lab already installed; use setup."
    target.mkdir(parents=True, exist_ok=True)
    source = Store(MAIN / "controller/state")
    shutil.copyfile(source.root / "secrets.key", target / "secrets.key")
    store = Store(target)
    deployments = Deployments(store, auto_logins=True)
    initialize(store)
    with source.db() as old, store.db() as new:
        for table in ("settings", "secrets", "deployments", "deployment_secrets"):
            rows = old.execute("SELECT * FROM " + table).fetchall()
            if table == "secrets":
                rows = [row for row in rows if row[0] in {"plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr"}]
            new.execute("DELETE FROM " + table)
            for row in rows:
                new.execute("INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in row) + ")", row)
    for row in deployments.rows():
        destination = target / "deployments" / row["id"]
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.root / "deployments" / row["id"] / "compose.json", destination / "compose.json")
    save(store, SaveDraft(revision=1, draft=SetupDraft(apps=list(PORTS), port_mode="custom",
        choices={key: {"port": port} for key, port in PORTS.items()})))
    (LAB / "before.json").write_text(json.dumps({"media": media(), "running": deployments._call(["ps", "-q", "--no-trunc"]).splitlines()}))
    payload = deployments.review()
    identity = deployments.enqueue(payload)
    (LAB / "installation.json").write_text(json.dumps({"id": identity}))
    asyncio.run(deployments.run_one())
    row = next(row for row in deployments.rows() if row["id"] == identity)
    assert row["state"] == "needs-setup", row["message"]
    print("Disposable companion installation running.", flush=True)


def setup():
    deployments = Deployments(Store(LAB / "controller/state"), auto_logins=True)
    identity = json.loads((LAB / "installation.json").read_text())["id"]
    companions = Companions(deployments)
    review = companions.review(identity)
    companions.execute(review)
    print("Reviewed companion setup completed.", flush=True)
    verify(deployments, identity, companions)


def verify(deployments, identity, companions):
    payload = load_receipt(deployments, identity)
    for key in APPS:
        info = inspect_container(deployments, identity, payload, key)
        assert all(mount["Type"] == "volume" for mount in info["Mounts"])
        assert companions.login(identity, key)["login"]["username"] == "stackarr"
    state = companions.state(identity)["apps"]
    with companions.client(PORTS["cleanuparr"]) as client:
        client.headers["X-Api-Key"] = state["cleanuparr"]["api_key"]
        cleanup_safe(client)
        for key in ("sonarr", "radarr"):
            assert len(client.get("/api/configuration/" + key).json()["instances"]) == 1
        assert len(client.get("/api/configuration/download_client").json()["clients"]) == 1
    with Kuma(f"http://127.0.0.1:{PORTS['kuma']}") as socket:
        socket.login(state["kuma"])
        assert len(socket.monitors()) == 9
    companions.execute(companions.review(identity))
    assert media() == json.loads((LAB / "before.json").read_text())["media"]
    before = set(json.loads((LAB / "before.json").read_text())["running"])
    after = set(deployments._call(["ps", "-q", "--no-trunc"]).splitlines())
    core = {row["container"] for key, row in companions.sources().items() if key not in APPS}
    assert core <= before & after
    # The separate packaged-maintenance check replaces only the main dashboard.
    assert len(before - after) <= 1
    (LAB / "report.json").write_text(json.dumps({"passed": True, "generated_logins": 3,
        "kuma_monitors": 9, "cleanup_dry_run": True, "cleanup_jobs_disabled": 5,
        "cleanup_connections": 3, "idempotent_setup": True, "no_media_mounts": True,
        "media_hashes_preserved": len(media()), "existing_core_containers_preserved": True,
        "time": time.time()}, indent=2))
    print("Companion connections, logins, safety and preservation passed.", flush=True)


def restart_backup():
    deployments = Deployments(Store(LAB / "controller/state"), auto_logins=True)
    identity = json.loads((LAB / "installation.json").read_text())["id"]
    backups = AppBackups(deployments)
    saved = backups.execute(backups.review(identity))
    assert saved
    companions = Companions(deployments)
    payload = load_receipt(deployments, identity)
    for key in APPS:
        companions.owned(identity, key, payload)
    # The backup pauses and restarts precisely the three config-only containers.
    time.sleep(25)
    verify(deployments, identity, companions)
    report = json.loads((LAB / "report.json").read_text())
    report.update(companion_backup_verified=True, companion_restart_persistence=True)
    (LAB / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "setup", "restart_backup"))
    globals()[parser.parse_args().action]()
