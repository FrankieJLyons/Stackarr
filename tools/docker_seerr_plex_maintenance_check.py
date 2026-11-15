"""Plex-account Seerr acceptance; fixed disposable Docker state and ports only."""

import argparse
import asyncio
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import httpx

from stackarr import seerr_wiring
from stackarr.app_backups import AppBackups
from stackarr.app_maintenance import AppMaintenance
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.onboarding import SaveDraft, SetupDraft, initialize, save
from stackarr.store import Store
from stackarr.updates import Updates, catalog
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import bootstrap, command, hashes

ROOT = Path("test-results/docker-seerr-plex-maintenance-20261018").resolve()
RETAINED = Path("test-results/docker-optional-maintenance-20261018").resolve()
STATE = ROOT / "package-state/controller/state"
PACKAGE = Path("test-results/optional-maintenance-package-extracted-r4/Stackarr-Docker-Optional-Maintenance-Preview-20261018-r4").resolve()
PORT = 43270
ORIGIN = "http://localhost:29240"


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2))


def host():
    with sqlite3.connect(STATE / "stackarr.db") as db:
        assert not db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running')").fetchone()
        assert not db.execute("SELECT 1 FROM app_updates WHERE state='running'").fetchone()
    db.close()
    return Deployments(Store(STATE))


def identity():
    return json.loads((ROOT / "lab.json").read_text())["deployment"]


def query(service, sql, parameters=None):
    payload = load_receipt(service, identity())
    info = inspect_container(service, identity(), payload, "seerr")
    script = "const sqlite=require('sqlite3');const db=new sqlite.Database('/app/config/db/db.sqlite3');db.configure('busyTimeout',10000);db.all(" + json.dumps(sql) + "," + json.dumps(parameters or []) + ",(error,rows)=>{if(error){process.exitCode=1;}else{console.log(JSON.stringify(rows));}db.close();});"
    return json.loads(command(["exec", info["Id"], "node", "-e", script]))


def stop_controller():
    directory = STATE.parent.resolve()
    assert directory.is_relative_to(ROOT) and not directory.is_symlink() and not directory.is_junction()
    env = os.environ | {"STACKARR_SEERR_PLEX_LAB_CONTROLLER": str(directory)}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_SEERR_PLEX_LAB_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0


def preserved():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert hashes(RETAINED / "media") == json.loads((RETAINED / "media-before.json").read_text())
    if (ROOT / "dependencies.json").exists():
        for row in json.loads((ROOT / "dependencies.json").read_text()):
            info = json.loads(command(["inspect", row["container"]]))[0]
            assert info["Id"] == row["container"] and info["State"]["Running"]


def prepare():
    assert (ROOT / "main-before.json").exists()
    installation, origin = bootstrap(PACKAGE, ROOT, 29240, 29091)
    assert origin == ORIGIN and installation["controller_port"] == 29091
    write("packaged-installation.json", installation)
    stop_controller()
    if not (ROOT / "dependencies.json").exists():
        dependencies = []
        for deployment, app in (("45ae8284ba7c49678d3276687c371bfd", "plex"),
                                ("218aec9409444692aae9e928e88f5af3", "sonarr"),
                                ("218aec9409444692aae9e928e88f5af3", "radarr")):
            info = json.loads(command(["inspect", "stackarr-owned-" + deployment + "-" + app + "-1"]))[0]
            assert info["Config"]["Labels"]["com.docker.compose.project"] == "stackarr-owned-" + deployment
            assert not info["State"]["Running"]
            command(["start", info["Id"]])
            dependencies.append({"app": app, "container": info["Id"], "was_running": False})
        write("dependencies.json", dependencies)
    if not (ROOT / "lab.json").exists():
        service = host()
        initialize(service.store)
        save(service.store, SaveDraft(revision=1, draft=SetupDraft(apps=["seerr"], port_mode="custom",
            choices={"seerr": {"port": PORT}})))
        plan = service.review()
        previous = json.loads((RETAINED / "previous-images.json").read_text())["seerr"]["image"]
        plan["compose"]["services"]["seerr"]["image"] = previous
        deployment = service.enqueue(plan)
        write("lab.json", {"deployment": deployment, "port": PORT, "previous_image": previous})
        asyncio.run(service.run_one())
        assert next(row for row in service.rows() if row["id"] == deployment)["state"] == "needs-setup"
        payload = load_receipt(service, deployment)
        info = inspect_container(service, deployment, payload, "seerr")
        command(["exec", info["Id"], "sh", "-c", "printf 'Original Plex-account Seerr configuration' > /app/config/stackarr-sso-sentinel"])
    bootstrap(PACKAGE, ROOT, 29240, 29091)
    preserved()
    print("Fresh Seerr 3.4.1 ready at http://localhost:43270; only separate lab Plex/Arr dependencies started.", flush=True)


def account_setup():
    service = host()
    saved = json.loads((ROOT / "plex-pin-private.json").read_text())
    with httpx.Client(trust_env=False, timeout=30) as client:
        if (ROOT / "plex-login.enc").exists():
            token = json.loads(service.store.cipher.decrypt((ROOT / "plex-login.enc").read_bytes()))["token"]
        else:
            response = client.get("https://plex.tv/api/v2/pins/" + str(saved["pin"]["id"]), headers=saved["headers"])
            token = response.json().get("authToken") if response.status_code == 200 else None
        assert token, "Complete the separate Seerr authorization in Plex first."
        (ROOT / "plex-login.enc").write_bytes(service.store.cipher.encrypt(json.dumps({"token": token}).encode()))
        login = client.post("http://127.0.0.1:43270/api/v1/auth/plex", json={"authToken": token})
        assert login.status_code == 200, "Real Plex login to the isolated Seerr was rejected."
        authenticated = client.get("http://127.0.0.1:43270/api/v1/auth/me")
        authenticated.raise_for_status()
        user = authenticated.json()
        assert user["id"] == 1 and user["userType"] == 1 and user["plexId"] and user["permissions"] == 2
    payload = load_receipt(service, identity())
    info = inspect_container(service, identity(), payload, "seerr")
    settings = json.loads(command(["exec", info["Id"], "head", "-c", "131072", "/app/config/settings.json"]))
    api_key = settings["main"]["apiKey"]
    revision, config = service.store.config()
    secrets = {"seerr": {"api_key": api_key}}
    retained_state = Path(json.loads((RETAINED / "packaged-installation.json").read_text())["state"])
    source = Store(retained_state)
    for key, port in (("sonarr", 43260), ("radarr", 43261)):
        app = config.integrations[key]
        app.enabled, app.mode, app.port = True, "connect", port
        app.url, app.peer_url = "http://127.0.0.1:" + str(port), "http://host.docker.internal:" + str(port)
        secrets[key] = source.secret(key)
    service.store.save(config, revision, secrets)
    private = {"token": token, "owner": {name: user[name] for name in ("id", "userType", "plexId", "permissions")}}
    (ROOT / "plex-login.enc").write_bytes(service.store.cipher.encrypt(json.dumps(private).encode()))
    with httpx.Client(base_url="http://127.0.0.1:43250", trust_env=False, timeout=30,
                      headers={"Accept": "application/json", "X-Plex-Token": token}) as plex:
        assert plex.get("/identity").json()["MediaContainer"]["machineIdentifier"] == "de85e27af353f7aecba4608db2e241ff9dcfc76c"
        sections = plex.get("/library/sections").json()["MediaContainer"].get("Directory", [])
        assert any(row["key"] == "1" for row in sections)
        library = next((row for row in sections if row["title"] == "Stackarr Seerr SSO originals"), None)
        if library is None:
            created = plex.post("/library/sections", params={"name": "Stackarr Seerr SSO originals", "type": "movie",
                "agent": "tv.plex.agents.movie", "scanner": "Plex Movie", "language": "en-GB",
                "location": "/data/movies/Stackarr Maintenance Fixture"})
            created.raise_for_status()
            sections = plex.get("/library/sections").json()["MediaContainer"]["Directory"]
            library = next(row for row in sections if row["title"] == "Stackarr Seerr SSO originals")
        library_id = library["key"]
        write("plex-library.json", {"id": library_id, "original_library_preserved": True})
    with httpx.Client(base_url="http://127.0.0.1:43270", trust_env=False, timeout=45, headers={"X-Api-Key": api_key}) as client:
        plex = client.post("/api/v1/settings/plex", json={"ip": "host.docker.internal", "port": 43250, "useSsl": False})
        plex.raise_for_status()
        assert plex.json()["machineId"] == "de85e27af353f7aecba4608db2e241ff9dcfc76c"
        libraries = client.get("/api/v1/settings/plex/library", params={"sync": "true", "enable": library_id})
        libraries.raise_for_status()
        assert any(row["id"] == library_id and row["enabled"] for row in libraries.json())
        async def wire():
            async with httpx.AsyncClient(trust_env=False, timeout=45) as api:
                changes, _ = await seerr_wiring.build(service.store, api)
                assert len(changes) in {0, 2}
                for change in changes:
                    await seerr_wiring.apply(service.store, api, change)
        asyncio.run(wire())
        client.post("/api/v1/settings/main", json={"localLogin": False, "newPlexLogin": False}).raise_for_status()
        client.post("/api/v1/settings/initialize").raise_for_status()
    preserved()
    write("account-setup.json", {"passed": True, "real_plex_oauth": True, "owner_user_type": 1,
        "only_separate_lab_plex_selected": True, "original_library_enabled": True, "local_login_disabled": True,
        "existing_accounts_and_tokens_not_copied": True})
    print("Real Plex-account Seerr login, separate Plex library and Arr connections verified; local login disabled.", flush=True)


def client(service):
    return httpx.Client(base_url="http://127.0.0.1:43270", trust_env=False, timeout=30,
                        headers={"X-Api-Key": service.store.secret("seerr")["api_key"]})


def plex_login(service):
    private = json.loads(service.store.cipher.decrypt((ROOT / "plex-login.enc").read_bytes()))
    with httpx.Client(base_url="http://127.0.0.1:43270", trust_env=False, timeout=30) as api:
        assert api.get("/api/v1/auth/me").status_code in {401, 403}
        response = api.post("/api/v1/auth/plex", json={"authToken": private["token"]})
        assert response.status_code == 200, "Fresh-session Plex login failed."
        owner = api.get("/api/v1/auth/me")
        owner.raise_for_status()
        assert {name: owner.json()[name] for name in private["owner"]} == private["owner"]
        api.post("/api/v1/auth/logout").raise_for_status()


def checkpoint(service):
    updates = Updates(service)
    payload = load_receipt(service, identity())
    value = updates.protected(payload, "seerr", updates.credentials(identity(), payload, "seerr"))
    assert value["authentication"]["mediaServerLogin"] and not value["authentication"]["localLogin"]
    assert len(value["users"]) == 1 and value["users"][0]["userType"] == 1 and value["users"][0]["plexId"]
    assert any(row["id"] == 9700001 and row["status"] == 1 and row["requestedBy"] == 1 for row in value["requests"])
    return value


def verify(service):
    original = json.loads(service.store.cipher.decrypt((ROOT / "baseline.enc").read_bytes()))
    assert checkpoint(service) == original
    plex_login(service)
    assert checkpoint(service) == original
    payload = load_receipt(service, identity())
    info = inspect_container(service, identity(), payload, "seerr")
    assert command(["exec", info["Id"], "cat", "/app/config/stackarr-sso-sentinel"]) == "Original Plex-account Seerr configuration"
    assert command(["exec", info["Id"], "sh", "-c", "if test -e /app/config/stackarr-sso-fault-marker; then printf present; else printf absent; fi"]) == "absent"
    preserved()


def fixture_setup():
    stop_controller()
    service = host()
    query(service, "INSERT OR IGNORE INTO media (id,mediaType,tmdbId,status) VALUES (9700001,'movie',9700001,1)")
    query(service, "INSERT OR IGNORE INTO media_request (id,status,type,mediaId,requestedById,is4k,isAutoRequest,ignoreQuota) VALUES (9700001,1,'movie',9700001,1,0,0,0)")
    baseline = checkpoint(service)
    (ROOT / "baseline.enc").write_bytes(service.store.cipher.encrypt(json.dumps(baseline).encode()))
    plex_login(service)
    with httpx.Client(base_url="http://127.0.0.1:43270", trust_env=False, timeout=30) as api:
        assert api.post("/api/v1/auth/plex", json={"authToken": "invalid-isolated-test-token"}).status_code >= 400
    with client(service) as api:
        assert len(api.get("/api/v1/user").json()["results"]) == 1
    verify(service)
    write("fixture.json", {"passed": True, "real_plex_owner": True, "fresh_cookie_jar_login": True,
        "invalid_token_rejected_without_creating_user": True, "synthetic_pending_request": 9700001,
        "no_download_or_media_request_submitted": True})
    print("Fresh Plex sessions and invalid-token rejection verified; original pending request fixture saved without triggering downloads.", flush=True)


def mutate(service):
    with client(service) as api:
        api.post("/api/v1/settings/main", json={"mediaServerLogin": False}).raise_for_status()
        assert api.get("/api/v1/settings/main").json()["mediaServerLogin"] is False
    query(service, "UPDATE media_request SET status=3 WHERE id=9700001")
    assert query(service, "SELECT status FROM media_request WHERE id=9700001")[0]["status"] == 3
    info = inspect_container(service, identity(), load_receipt(service, identity()), "seerr")
    command(["exec", info["Id"], "sh", "-c", "printf 'Changed by test candidate' > /app/config/stackarr-sso-sentinel; printf confirmed > /app/config/stackarr-sso-fault-marker"])


def report_case(case, **extra):
    path = ROOT / "native-report.json"
    report = json.loads(path.read_text()) if path.exists() else {"cases": []}
    assert not any(row["case"] == case for row in report["cases"])
    report["cases"].append({"case": case, "passed": True, "fresh_plex_login": True,
        "owner_library_requests_connections_preserved": True, "main_and_media_preserved": True, **extra})
    write(path.name, report)
    print("Plex-account Seerr passed: " + case, flush=True)


def native_tests():
    stop_controller()
    service = host()
    recorded = {row["case"] for row in json.loads((ROOT / "native-report.json").read_text())["cases"]} if (ROOT / "native-report.json").exists() else set()
    for failed in (False, True):
        case = "failed-repair-recovery" if failed else "repair"
        if case in recorded:
            continue
        original_health = AppMaintenance.health
        injected = False
        def health(self, review, payload, **kwargs):
            nonlocal injected
            ready = original_health(self, review, payload, **kwargs)
            if ready and failed and not injected:
                mutate(service)
                injected = True
            return ready
        AppMaintenance.health = health
        try:
            operation = service.actions.enqueue(service.actions.review(identity(), "seerr", "repair"))
            asyncio.run(service.actions.run_one())
            row = next(row for row in service.actions.rows() if row["id"] == operation)
            assert row["state"] == ("failed-recovered" if failed else "succeeded"), row["message"]
            assert not failed or injected
            verify(service)
            report_case(case, actual_authentication_and_request_writes=injected)
        finally:
            AppMaintenance.health = original_health
    updates = Updates(service)
    if "update-and-manual-rollback" not in recorded:
        payload = load_receipt(service, identity())
        if payload["compose"]["services"]["seerr"]["image"] != catalog()["apps"]["seerr"]["image"]:
            assert updates.execute(updates.review(identity(), "seerr"))["state"] == "succeeded"
        verify(service)
        run = next(row["id"] for row in updates.listing()["history"] if row["app"] == "seerr")
        assert updates.execute(updates.review(identity(), "seerr", "rollback", run))["state"] == "succeeded"
        verify(service)
        report_case("update-and-manual-rollback", previous="3.4.1", candidate="3.5.0")
    if "healthy-candidate-authentication-change-recovery" not in recorded:
        normal = updates.health
        injected = False
        def change_after_health(payload, key, secret, version, seconds=180):
            nonlocal injected
            ready = normal(payload, key, secret, version, seconds)
            if ready and payload["compose"]["services"]["seerr"]["image"] == catalog()["apps"]["seerr"]["image"] and not injected:
                mutate(service)
                injected = True
            return ready
        updates.health = change_after_health
        try:
            result = updates.execute(updates.review(identity(), "seerr"))
            assert injected and result["state"] == "rolled-back", result["message"]
            verify(service)
            report_case("healthy-candidate-authentication-change-recovery", healthy_api_before_rejection=True,
                real_login_flag_and_request_writes=True)
        finally:
            updates.health = normal
    if "interrupted-worker-recovery" not in recorded:
        child = subprocess.run([sys.executable, "-m", "tools.docker_seerr_plex_maintenance_check", "crash_update"], timeout=400)
        assert child.returncode == 77
        subprocess.run([sys.executable, "-m", "tools.docker_seerr_plex_maintenance_check", "recover_update"], check=True, timeout=400)
        verify(service)
        report_case("interrupted-worker-recovery", actual_worker_exit=True, actual_authentication_and_request_writes=True,
                    receipt_file_database_gap=True)
    if "encrypted-backup-restore" not in recorded:
        backups = AppBackups(service)
        backups.execute(backups.review(identity(), apps=["seerr"]))
        saved = backups.rows()[0]["id"]
        write("backup-restore-original.json", {"id": saved})
        payload = load_receipt(service, identity())
        assert updates.health(payload | {"identity": identity()}, "seerr", updates.credentials(identity(), payload, "seerr"), "3.4.1")
        mutate(service)
        backups.execute(backups.review(identity(), saved))
        payload = load_receipt(service, identity())
        assert updates.health(payload | {"identity": identity()}, "seerr", updates.credentials(identity(), payload, "seerr"), "3.4.1")
        verify(service)
        report_case("encrypted-backup-restore", actual_authentication_and_request_writes=True)


def crash_update():
    service = host()
    updates = Updates(service)
    normal = updates.health
    def crash(payload, key, secret, version, seconds=180):
        ready = normal(payload, key, secret, version, seconds)
        if ready and payload["compose"]["services"]["seerr"]["image"] == catalog()["apps"]["seerr"]["image"]:
            mutate(service)
            operation = updates.listing()["history"][0]["id"]
            run = updates.read(operation)
            updates.save(run, "running", "committing-receipt")
            updates.files(run).write_text(json.dumps(run["new"]["compose"], sort_keys=True))
            write("interrupted-update.json", {"id": operation})
            print("Exiting only the test worker after real auth/request writes and a receipt commit gap.", flush=True)
            os._exit(77)
        return ready
    updates.health = crash
    updates.execute(updates.review(identity(), "seerr"))
    raise AssertionError("Expected isolated worker exit")


def recover_update():
    operation = json.loads((ROOT / "interrupted-update.json").read_text())["id"]
    with sqlite3.connect(STATE / "stackarr.db") as db:
        row = db.execute("SELECT deployment,app FROM app_updates WHERE id=?", (operation,)).fetchone()
        assert row == (identity(), "seerr")
    db.close()
    service = Deployments(Store(STATE))
    updates = Updates(service)
    assert updates.execute(updates.review(identity(), "seerr", "update-recover", operation))["state"] == "succeeded"


def normalize_baseline():
    service = host()
    path = ROOT / "baseline.enc"
    original = path.read_bytes()
    previous = ROOT / "baseline-with-scan-cursor.enc"
    if not previous.exists():
        previous.write_bytes(original)
    value = json.loads(service.store.cipher.decrypt(original))
    for library in value["plex"].get("libraries", []):
        library.pop("lastScan", None)
    path.write_bytes(service.store.cipher.encrypt(json.dumps(value).encode()))
    verify(service)
    print("Only the volatile library scan cursor was projected from the baseline; original encrypted checkpoint retained.", flush=True)


def cleanup_work():
    root = STATE / "app-backups"
    removed = 0
    for path in root.iterdir():
        if path.is_dir() and path.name.startswith(("work-", "update-", "maintenance-")):
            assert path.resolve().is_relative_to(ROOT) and not path.is_symlink() and not path.is_junction()
            assert all(not child.is_symlink() and not child.is_junction() for child in path.rglob("*"))
            shutil.rmtree(path)
            removed += 1
    return removed


def snapshot_proof(service):
    with service.store.db() as db:
        rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM deployment_actions WHERE state='failed-recovered'")]
    review = next(row for row in rows if row.get("app") == "seerr" and row.get("action") == "repair")
    backups = AppBackups(service)
    with tempfile.TemporaryDirectory(prefix="sso-proof-", dir=ROOT) as folder:
        for kind, snapshot in (("before", review["run"]["backup"]), ("failed", review["run"]["recovery_backup"])):
            stage = Path(folder) / kind
            stage.mkdir()
            backups.materialize(snapshot, stage)
            with tarfile.open(stage / "seerr/volume.tar") as archive:
                members = {row.name.removeprefix("./"): row for row in archive.getmembers()}
                settings = json.loads(archive.extractfile(members["settings.json"]).read())
                assert settings["main"]["mediaServerLogin"] == (kind == "before")
                database = stage / "db"
                database.mkdir()
                for name in ("db.sqlite3", "db.sqlite3-wal", "db.sqlite3-shm"):
                    if "db/" + name in members:
                        (database / name).write_bytes(archive.extractfile(members["db/" + name]).read())
                with sqlite3.connect(database / "db.sqlite3") as db:
                    assert db.execute("SELECT status FROM media_request WHERE id=9700001").fetchone()[0] == (1 if kind == "before" else 3)
                db.close()
    write("snapshot-proof.json", {"passed": True, "encrypted_original_and_failed_candidate_inspected": True,
        "real_plex_signin_setting_changed": True, "real_request_database_write_confirmed": True})


def finalize():
    from stackarr.self_update import SelfUpdates
    from tools.docker_folder_ports_check import stop_lab

    native = json.loads((ROOT / "native-report.json").read_text())
    browser = json.loads((ROOT / "browser-report.json").read_text())
    assert len(native["cases"]) == 6 and all(row["passed"] for row in native["cases"])
    assert browser["passed"] and browser["app_actions"] == 5
    service = host()
    verify(service)
    snapshot_proof(service)
    payload = load_receipt(service, identity())
    assert payload["compose"]["services"]["seerr"]["image"] == json.loads((ROOT / "lab.json").read_text())["previous_image"]
    runtime = SelfUpdates(ROOT / "package-state")
    active = runtime.active()
    _, manifest = runtime.release(active["release"])
    assert manifest["release"] == Path(browser["package"]).name
    assert runtime.controller_probe(active)["executable"] == manifest["files"]["StackarrPreview.exe"]
    protected_runtime = runtime.protected(active)
    promotion = next(row for row in runtime.jobs() if row["phase"] == "succeeded" and row["target"]["release"] == active["release"])
    promotion_file = runtime.home / "jobs" / promotion["id"] / "job.json"
    events = command(["events", "--since", str(int(promotion["created"])), "--until", str(int(promotion_file.stat().st_mtime) + 1),
        "--filter", "type=container", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity(), "--format", "{{json .}}"])
    lifecycle = {"create", "destroy", "start", "stop", "restart", "kill", "die"}
    assert all(json.loads(row).get("Action", json.loads(row).get("status")) not in lifecycle for row in events.splitlines())
    write("package-promotion-preservation.json", {"passed": True, "seerr_lifecycle_events_during_stackarr_promotion": 0})
    monitoring_script = """import asyncio,json
from pathlib import Path
from stackarr.store import Store
from stackarr.integrations import collect
store=Store(Path('/var/lib/stackarr'))
async def main():
 async def one(key,app):
  try:
   await collect(key,app,store.secret(key))
   return {'app':key,'authenticated':True}
  except Exception:
   return {'app':key,'authenticated':False}
 return await asyncio.gather(*(one(key,app) for key,app in store.config()[1].integrations.items() if app.enabled))
print(json.dumps(asyncio.run(main())))
"""
    main_dashboard = command(["ps", "-q", "--no-trunc", "--filter", "name=^/stackarr-plex-lab-bc615eaf1fe6-stackarr-1$"])
    monitoring = json.loads(command(["exec", main_dashboard, "python", "-c", monitoring_script]))
    assert len(monitoring) == 9 and all(row["authenticated"] for row in monitoring)
    write("main-dashboard-monitoring.json", monitoring)
    preserved()
    removed = cleanup_work()
    installation = json.loads((ROOT / "packaged-installation.json").read_text())
    stop_lab(ROOT, installation, [identity()])
    stop_controller()
    expected_dependencies = {"plex": "45ae8284ba7c49678d3276687c371bfd", "sonarr": "218aec9409444692aae9e928e88f5af3", "radarr": "218aec9409444692aae9e928e88f5af3"}
    original_running = set(json.loads((ROOT / "main-before.json").read_text())["running"])
    for row in json.loads((ROOT / "dependencies.json").read_text()):
        info = json.loads(command(["inspect", row["container"]]))[0]
        project = "stackarr-owned-" + expected_dependencies[row["app"]]
        assert info["Config"]["Labels"]["com.docker.compose.project"] == project
        assert info["Name"] == "/" + project + "-" + row["app"] + "-1" and info["Id"] not in original_running
        assert not row["was_running"]
        command(["stop", "--timeout", "30", info["Id"]])
        assert not json.loads(command(["inspect", info["Id"]]))[0]["State"]["Running"]
    assert not inspect_container(service, identity(), payload, "seerr")["State"]["Running"]
    assert not json.loads(command(["inspect", protected_runtime["container"]]))[0]["State"]["Running"]
    for port in (29240, 29091, 43270):
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert hashes(RETAINED / "media") == json.loads((RETAINED / "media-before.json").read_text())
    write("acceptance.json", {"passed": True, "real_plex_owner_sso": True, "fresh_session_login_after_every_case": True,
        "local_login_disabled": True, "native_cases": 6, "packaged_app_actions": 5,
        "older_packaged_update_checkpoint_recovered_in_new_package": True,
        "stackarr_package_promotion_preserved_seerr_container": True,
        "healthy_api_candidate_with_broken_plex_signin_rejected_and_recovered": True,
        "actual_worker_exit_and_request_database_writes": True, "encrypted_snapshot_write_proof": True,
        "plex_owner_permissions_library_and_pending_request_preserved": True,
        "existing_nine_apps_and_dashboard_unchanged": True, "main_fresh_authenticated_integrations": 9,
        "main_media_files_preserved": 16, "lab_media_files_preserved": 3,
        "lab_and_borrowed_dependencies_stopped": True, "settings_volumes_keys_and_encrypted_backups_retained": True,
        "temporary_plaintext_work_directories_removed": removed, "package": manifest["release"]})
    print("Seerr Plex-account acceptance complete; all existing apps/settings/media preserved and isolated lab stopped.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "account_setup", "fixture_setup", "native_tests", "crash_update", "recover_update", "normalize_baseline", "finalize"))
    args = parser.parse_args()
    globals()[args.phase]()


if __name__ == "__main__":
    main()
