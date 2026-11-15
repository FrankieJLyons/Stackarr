"""Claimed-account host recovery using fresh Docker volumes and original lab media.

Fixed maintainer scope only. Never targets the main installation for mutation.
Previously claimed lab containers stay stopped while their isolated copies run.
"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.app_backups import AppBackups, digest
from stackarr.companions import Companions
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.host_recovery import Recovery
from stackarr.onboarding import SaveDraft, SetupDraft, initialize, save
from stackarr.store import Store
from stackarr.updates import Updates
from tools import docker_app_maintenance_check as preservation
from tools import docker_optional_maintenance_check as optional
from tools import docker_seerr_plex_maintenance_check as sso
from tools.docker_folder_ports_check import bootstrap, command, hashes
from tools.docker_host_recovery_check import api, frozen, login, wait_job

ROOT = Path("test-results/docker-claimed-host-recovery-20261018").resolve()
PACKAGE = Path("test-results/seerr-plex-maintenance-package-extracted-r2/Stackarr-Docker-Seerr-Plex-Maintenance-Preview-20261018-r2").resolve()
STATE = ROOT / "package-state/controller/state"
PORTS = {"plex": 43250, "seerr": 43270, "tautulli": 43252, "sonarr": 43260, "radarr": 43261}
MACHINE = "de85e27af353f7aecba4608db2e241ff9dcfc76c"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2), encoding="utf-8")


def scoped(path):
    path = Path(path).resolve()
    assert path.is_relative_to(ROOT) and path != ROOT and not path.is_symlink() and not path.is_junction()
    return path


def host(state=STATE):
    state = scoped(state)
    with closing(sqlite3.connect(state / "stackarr.db")) as db:
        assert not db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running')").fetchone()
    return Deployments(Store(state))


def stop_controller(state):
    directory = scoped(Path(state) / "controller")
    env = os.environ | {"STACKARR_CLAIMED_RECOVERY_CONTROLLER": str(directory)}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_CLAIMED_RECOVERY_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0


def originals():
    # These are the earlier disposable account labs, never the main app state.
    old = optional.host()
    prior = sso.host()
    selected = {key: (old, optional.target()) for key in ("plex", "tautulli")}
    auxiliary = read(optional.ROOT / "auxiliary.json")["deployment"]
    selected.update({key: (old, auxiliary) for key in ("sonarr", "radarr")})
    selected["seerr"] = (prior, sso.identity())
    return selected


def preserved():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert hashes(optional.ROOT / "media") == read(ROOT / "original-media.json")
    for row in read(ROOT / "original-containers.json"):
        info = json.loads(command(["inspect", row["id"]]))[0]
        assert info["Id"] == row["id"] and info["Image"] == row["image"] and not info["State"]["Running"]
        assert info["State"]["FinishedAt"] == row["finished"]


def prepare():
    ROOT.mkdir(exist_ok=True)
    assert not (ROOT / "source.json").exists(), "Use the existing lab's next phase."
    assert read(sso.ROOT / "acceptance.json")["passed"]
    assert read(optional.ROOT / "acceptance.json")["passed"]
    write("main-before.json", preservation.main_snapshot())
    write("original-media.json", hashes(optional.ROOT / "media"))
    selected = originals()
    records = []
    for key, (source, identity) in selected.items():
        info = inspect_container(source, identity, load_receipt(source, identity), key)
        assert not info["State"]["Running"]
        records.append({"app": key, "id": info["Id"], "image": info["Image"], "finished": info["State"]["FinishedAt"]})
    write("original-containers.json", records)
    media = scoped(ROOT / "source media – originals")
    shutil.copytree(optional.ROOT / "media", media)
    installation, origin = bootstrap(PACKAGE, ROOT, 29250, 29092, media)
    stop_controller(ROOT / "package-state")
    service = Deployments(Store(STATE))
    initialize(service.store)
    draft = SetupDraft(apps=list(PORTS), port_mode="custom", data_root=str(media),
                       choices={key: {"port": port} for key, port in PORTS.items()})
    save(service.store, SaveDraft(revision=1, draft=draft))
    plan = service.review()
    for key, (source, identity) in selected.items():
        plan["compose"]["services"][key]["image"] = load_receipt(source, identity)["compose"]["services"][key]["image"]
    identity = service.enqueue(plan)
    write("source.json", {"installation": installation, "origin": origin, "deployment": identity, "media": str(media)})
    asyncio.run(service.run_one())
    assert next(row for row in service.rows() if row["id"] == identity)["state"] == "needs-setup"
    payload = load_receipt(service, identity)
    for key in PORTS:
        info = inspect_container(service, identity, payload, key)
        command(["stop", "--timeout", "60", info["Id"]])
    AppBackups(service).review(identity)
    snapshots = []
    for key, (source, old_id) in selected.items():
        backups = AppBackups(source)
        review = backups.review(old_id, apps=[key])
        assert not review["containers"][key]["running"]
        backups.execute(review)
        snapshot = next(row["id"] for row in backups.rows() if row["deployment"] == old_id)
        with tempfile.TemporaryDirectory(prefix="fixture-import-", dir=ROOT) as name:
            stage = Path(name)
            backups.materialize(snapshot, stage)
            # Only a new, exclusive, receipt-verified configuration volume is writable.
            AppBackups(service).review(identity)
            AppBackups(service).helper(payload | {"identity": identity}, key, stage / key, restore=True)
        snapshots.append({"app": key, "original_deployment": old_id, "snapshot": snapshot})
    revision, config = service.store.config()
    credentials = {key: source.store.secret(key) for key, (source, _) in selected.items()}
    assert all(credentials.values())
    service.store.save(config, revision, credentials)
    tautulli = Companions(selected["tautulli"][0]).state(selected["tautulli"][1])["apps"]["tautulli"]
    Companions(service).save(identity, {"apps": {"tautulli": tautulli}})
    # Normally issued Plex authorization from the earlier sign-in test, never a database token query.
    private = json.loads(selected["seerr"][0].store.cipher.decrypt((sso.ROOT / "plex-login.enc").read_bytes()))
    (ROOT / "plex-login.enc").write_bytes(service.store.cipher.encrypt(json.dumps(private).encode()))
    for key in PORTS:
        command(["start", inspect_container(service, identity, payload, key)["Id"]])
    write("fixture-import.json", {"only_stopped_disposable_accounts_copied": True, "fresh_volume_count": 5,
        "original_configuration_volumes_preserved": True, "encrypted_snapshots": snapshots})
    preserved()
    print("Five fresh source volumes prepared from stopped account labs; original containers and main installation unchanged.", flush=True)


def accounts(service, identity, baseline=False):
    payload = load_receipt(service, identity)
    updates = Updates(service)
    private = json.loads(service.store.cipher.decrypt((ROOT / "plex-login.enc").read_bytes()))
    result = {"protected": {}}
    for key in PORTS:
        secret = updates.credentials(identity, payload, key)
        for _ in range(120):
            try:
                result["protected"][key] = updates.protected(payload | {"identity": identity}, key, secret)
                break
            except Exception:
                time.sleep(1)
        else:
            raise AssertionError("Recovered protected settings unavailable: " + key)
    with httpx.Client(base_url="http://127.0.0.1:43250", timeout=30, trust_env=False,
                      headers={"Accept": "application/json", "X-Plex-Token": private["token"]}) as client:
        machine = client.get("/identity").json()["MediaContainer"]
        assert machine["claimed"] and machine["machineIdentifier"] == MACHINE
        sections = client.get("/library/sections").json()["MediaContainer"]["Directory"]
        result["plex_libraries"] = [{name: row.get(name) for name in ("key", "uuid", "title", "agent", "type")} for row in sections]
        result["plex_items"] = {}
        parts = []
        for row in sections:
            items = client.get("/library/sections/" + row["key"] + "/all").json()["MediaContainer"].get("Metadata", [])
            result["plex_items"][row["key"]] = [{name: item.get(name) for name in ("ratingKey", "title", "guid")} for item in items]
            for item in items:
                for media in item.get("Media", []):
                    parts.extend(media.get("Part", []))
        assert parts and any(row["title"] == "Stackarr Seerr SSO originals" for row in sections)
        part = client.get(parts[0]["key"], headers={"Range": "bytes=0-4095"})
        assert part.status_code in {200, 206} and part.content
        result["media_prefix_hash"] = hashlib.sha256(part.content[:4096]).hexdigest()
        rejected = client.get("/library/sections", headers={"X-Plex-Token": "invalid-isolated-authorization"})
        assert rejected.status_code in {401, 403}
    with httpx.Client(trust_env=False, timeout=15) as anonymous:
        assert anonymous.get("http://127.0.0.1:43250/library/sections").status_code in {401, 403}
    with httpx.Client(base_url="http://127.0.0.1:43270", timeout=30, trust_env=False) as client:
        assert client.get("/api/v1/auth/me").status_code in {401, 403}
        assert client.post("/api/v1/auth/plex", json={"authToken": private["token"]}).status_code == 200
        user = client.get("/api/v1/auth/me").json()
        assert {name: user[name] for name in private["owner"]} == private["owner"]
        client.post("/api/v1/auth/logout").raise_for_status()
        assert client.post("/api/v1/auth/plex", json={"authToken": "invalid-isolated-authorization"}).status_code >= 400
    seerr = result["protected"]["seerr"]
    assert len(seerr["users"]) == 1 and seerr["users"][0]["userType"] == 1
    assert seerr["authentication"]["mediaServerLogin"] and not seerr["authentication"]["localLogin"]
    assert len(seerr["requests"]) == 1 and seerr["requests"][0]["id"] == 9700001 and seerr["requests"][0]["status"] == 1
    record = Companions(service).login(identity, "tautulli", payload)
    assert record["login"]["password"]
    with Companions.client(PORTS["tautulli"]) as client:
        client.headers["X-Api-Key"] = service.store.secret("tautulli")["api_key"]
        def get(cmd):
            response = client.get("/api/v2", params={"cmd": cmd})
            response.raise_for_status()
            value = response.json()["response"]
            assert value["result"] == "success", "Tautulli readback failed: " + cmd
            return value["data"]
        assert get("get_server_info")["pms_identifier"] == MACHINE
        assert isinstance(get("get_activity")["sessions"], list)
        if baseline:
            get("refresh_libraries_list")
            get("refresh_users_list")
        libraries = get("get_libraries")
        result["tautulli_libraries"] = sorted([{name: row.get(name) for name in ("section_id", "section_name", "section_type")} for row in libraries], key=lambda row: str(row["section_id"]))
        assert result["tautulli_libraries"]
        users = get("get_users")
        result["tautulli_users"] = sorted([{name: row.get(name) for name in ("row_id", "user_id", "is_admin", "is_active", "shared_libraries")} for row in users], key=lambda row: str(row["user_id"]))
        assert any(str(row["user_id"]) == str(private["owner"]["plexId"]) for row in users)
    if baseline:
        (ROOT / "accounts-baseline.enc").write_bytes(service.store.cipher.encrypt(json.dumps(result).encode()))
    else:
        expected = json.loads(service.store.cipher.decrypt((ROOT / "accounts-baseline.enc").read_bytes()))
        assert result == expected, "Claimed-account settings or original library records changed."
    preserved()
    return result


def configure():
    source = read(ROOT / "source.json")
    service = host()
    accounts(service, source["deployment"], baseline=True)
    installation, origin = bootstrap(PACKAGE, ROOT, 29250, 29092)
    password = secrets.token_urlsafe(32)
    invitation = command(["compose", "--project-name", installation["project"], "-f", str(ROOT / "package-state/compose.json"),
                          "exec", "-T", "stackarr", "stackarr", "setup-link"])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.goto(invitation)
        page.get_by_label("Create a password", exact=True).fill(password)
        page.get_by_role("button", name="Continue to setup", exact=False).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        browser.close()
    write("access.json", {"owner_password": password, "dashboard": origin})
    with login(origin, password) as client:
        saved = api(client, "config")
        config = saved["config"]
        config["storage"]["data_root"] = source["media"]
        for key in PORTS:
            config["integrations"][key].update(enabled=True, mode="connect", url="http://host.docker.internal:" + str(PORTS[key]), port=PORTS[key])
        api(client, "config", {"revision": saved["revision"], "config": config,
                              "credentials": {key: service.store.secret(key) for key in PORTS}}, method="PUT")
        write("source-dashboard-config.json", api(client, "config"))
        old_session = {"cookies": dict(client.cookies), "csrf": client.headers["X-CSRF-Token"]}
        (ROOT / "source-session.enc").write_bytes(service.store.cipher.encrypt(json.dumps(old_session).encode()))
    write("source-account-acceptance.json", {"passed": True, "claimed_plex_identity": MACHINE,
        "real_seerr_plex_owner": True, "synthetic_pending_request": 9700001,
        "tautulli_fresh_web_login_and_authenticated_plex_monitoring": True,
        "original_library_file_read_verified": True, "invalid_authorization_rejected": True})
    print("Source claimed Plex, fresh Seerr Plex-owner login and Tautulli login/monitoring pass with original library and pending request.", flush=True)


def backup():
    source = read(ROOT / "source.json")
    access = read(ROOT / "access.json")
    vault = scoped(ROOT / "independent recovery copies")
    vault.mkdir()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(180000)
        page.goto(source["origin"])
        page.get_by_label("Password", exact=True).fill(access["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Backups", exact=True).click()
        with page.expect_response(lambda r: r.url.endswith("/api/host-backup-review")) as reviewed:
            page.get_by_role("button", name="Prepare whole-host recovery", exact=True).click()
        assert reviewed.value.status == 200 and len(reviewed.value.json()["apps"]) == 5
        expect(page.get_by_role("button", name="Create recovery file", exact=True)).to_be_visible()
        page.screenshot(path=str(ROOT / "claimed-backup-review.png"), full_page=True)
        with page.expect_response(lambda r: r.url.endswith("/api/deployments/actions/apply")) as applied:
            page.get_by_role("button", name="Create recovery file", exact=True).click()
        assert applied.value.status == 202
        with login(source["origin"], access["owner_password"]) as client:
            wait_job(client, applied.value.json()["id"])
            (vault / "recovery-key.json").write_text(json.dumps(api(client, "backup-key", {"password": access["owner_password"]})))
        browser.close()
    service = host()
    accounts(service, source["deployment"])
    bundle = next((STATE / "host-recovery").glob("*.stackarr-recovery"))
    shutil.copyfile(bundle, vault / bundle.name)
    recovery = Recovery(vault / bundle.name, vault / "recovery-key.json", PACKAGE)
    with recovery.opened() as (_, meta):
        assert sum(len(row["manifest"]["apps"]) for row in meta["snapshots"]) == 5
    copied_media = scoped(ROOT / "recovered media – originals")
    shutil.copytree(source["media"], copied_media)
    write("source-media-hashes.json", hashes(Path(source["media"])))
    write("request.json", {"bundle": str(vault / bundle.name), "keyfile": str(vault / "recovery-key.json"),
        "package": str(PACKAGE), "destination": str(ROOT / "recovered-state"),
        "media": {source["media"]: str(copied_media)}, "port": 29251, "controller_port": 29093})
    write("backup-acceptance.json", {"passed": True, "packaged_browser_review_and_apply": True,
        "five_complete_app_archives_verified": True, "independent_file_and_key_retained": True,
        "bundle_sha256": digest(vault / bundle.name)})
    print("Packaged browser created the complete claimed-account recovery file; independent encrypted copy and key verify.", flush=True)


def database_proof(service, identity):
    payload = load_receipt(service, identity)
    containers = {key: inspect_container(service, identity, payload, key)["Id"] for key in ("plex", "seerr", "tautulli")}
    database = "/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db"
    plex = command(["exec", containers["plex"], "/usr/lib/plexmediaserver/Plex SQLite", "-readonly", database,
                    "PRAGMA integrity_check; SELECT COUNT(*) FROM metadata_items;"])
    assert plex.splitlines()[0] == "ok"
    script = "const sqlite=require('sqlite3');const db=new sqlite.Database('/app/config/db/db.sqlite3',sqlite.OPEN_READONLY);db.all('PRAGMA integrity_check',(e,r)=>{if(e||r[0].integrity_check!=='ok'){process.exitCode=1;db.close();return;}db.all('SELECT id,status,requestedById FROM media_request ORDER BY id',(e,r)=>{if(e)process.exitCode=1;else console.log(JSON.stringify(r));db.close();});});"
    seerr = json.loads(command(["exec", containers["seerr"], "node", "-e", script]))
    script = "import sqlite3,json; c=sqlite3.connect('file:/config/tautulli.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; print(json.dumps({t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('users','library_sections','session_history')})); c.close()"
    tautulli = json.loads(command(["exec", containers["tautulli"], "python", "-c", script]))
    return {"plex_metadata_rows": int(plex.splitlines()[1]), "seerr_pending_request_rows": seerr,
            "tautulli_database_rows": tautulli, "three_database_integrity_checks": True}


def loss():
    source = read(ROOT / "source.json")
    assert read(ROOT / "backup-acceptance.json")["passed"]
    assert frozen(ROOT, PACKAGE, "review", ROOT / "request.json", "blocked-existing.json")[0] == 1
    stop_controller(ROOT / "package-state")
    service = host()
    identity = source["deployment"]
    # Only this task's newly generated five-app project and dashboard can be removed.
    assert set(load_receipt(service, identity)["apps"]) == set(PORTS)
    assert identity not in {row[1] for row in originals().values()}
    assert source["installation"]["project"].startswith("stackarr-preview-")
    original_ids = {row["id"] for row in read(ROOT / "original-containers.json")} | set(read(ROOT / "main-before.json")["running"])
    inventory = AppBackups(service).review(identity)["containers"]
    assert set(inventory) == set(PORTS) and not ({row["id"] for row in inventory.values()} & original_ids)
    preserved()
    proof = database_proof(service, identity)
    (ROOT / "database-baseline.enc").write_bytes(service.store.cipher.encrypt(json.dumps(proof).encode()))
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(STATE / "deployments" / identity / "compose.json"), "down", "--volumes", "--timeout", "90"])
    command(["compose", "--project-name", source["installation"]["project"], "-f", str(ROOT / "package-state/compose.json"), "down", "--volumes"])
    assert not command(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity])
    scoped(ROOT / "package-state").rename(scoped(ROOT / "lost-source-state-retained"))
    request = read(ROOT / "request.json")
    from cryptography.fernet import Fernet

    key = read(Path(request["keyfile"]))
    write("wrong-key.json", key | {"key": Fernet.generate_key().decode()})
    write("wrong-key-request.json", request | {"keyfile": str(ROOT / "wrong-key.json")})
    assert frozen(ROOT, PACKAGE, "review", ROOT / "wrong-key-request.json", "blocked-wrong-key.json")[0] == 1
    assert not Path(request["destination"]).exists()
    with socket.socket() as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("0.0.0.0", PORTS["plex"]))
        occupied.listen()
        assert frozen(ROOT, PACKAGE, "review", ROOT / "request.json", "blocked-busy-port.json")[0] == 1
    assert frozen(ROOT, PACKAGE, "review", ROOT / "request.json", "recovery-review.json")[0] == 0
    preserved()
    print("Only five new source volumes and dashboard removed; source state unavailable. Existing-resource/wrong-key/busy-port gates pass.", flush=True)


def recover():
    review = read(ROOT / "recovery-review.json")
    recovery = Recovery(review["bundle"], review["keyfile"], PACKAGE)
    original = AppBackups.helper
    count = 0
    def fail_after_account_write(self, payload, key, directory, restore=False):
        nonlocal count
        if restore:
            count += 1
            if count == 2:
                raise RuntimeError("Isolated failure after real claimed Plex configuration extraction")
        return original(self, payload, key, directory, restore)
    AppBackups.helper = fail_after_account_write
    try:
        try:
            recovery.execute(review)
        except Exception:
            assert count == 2
        else:
            raise AssertionError("Recovery write fault did not execute")
    finally:
        AppBackups.helper = original
    journal = read(Path(review["destination"]) / "recovery.json")
    assert journal["phase"] == "failed" and len(journal["containers"]) == 5
    for identity in journal["containers"].values():
        assert command(["inspect", identity, "--format", "{{.State.Running}}" ]) == "false"
    # Read-only evidence proves the first claimed account volume really received data.
    plex = next(value for key, value in journal["containers"].items() if key.endswith(":plex"))
    copied = ROOT / "partial-plex-proof.xml"
    command(["cp", plex + ":/config/Library/Application Support/Plex Media Server/Preferences.xml", str(copied)])
    import xml.etree.ElementTree as ET

    assert ET.parse(copied).getroot().attrib["ProcessedMachineIdentifier"] == MACHINE
    copied.unlink()
    preserved()
    request = read(ROOT / "request.json")
    collision = scoped(ROOT / "blocked-resource-destination")
    write("resource-collision-request.json", request | {"destination": str(collision)})
    code, blocked = frozen(ROOT, PACKAGE, "review", ROOT / "resource-collision-request.json", "blocked-stopped-resources.json")
    assert code == 1 and "still exist" in blocked.get("message", "")
    assert not collision.exists()
    code, result = frozen(ROOT, PACKAGE, "apply", ROOT / "recovery-review.json", "recovery-result.json")
    assert code == 0 and result["passed"], "Fresh packaged claimed-account recovery failed."
    write("recovery-acceptance.json", {"passed": True, "real_claimed_plex_configuration_written_before_failure": True,
        "all_five_new_containers_stopped_after_failure": True, "fresh_packaged_process_retry": True,
        "existing_stopped_resources_rejected_before_adoption": True, "wrong_key_and_occupied_app_port_rejected": True})
    print("Real partial claimed-account extraction proved; fresh packaged executable recovered all five new volumes.", flush=True)


def verify():
    review = read(ROOT / "recovery-review.json")
    destination = scoped(review["destination"])
    launch = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(PACKAGE / "Start-StackarrPreview.ps1"), "-StateDirectory", str(destination), "-NoBrowser"],
        capture_output=True, text=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT / "recovered-bootstrap.log").write_text(launch.stdout + launch.stderr)
    assert launch.returncode == 0
    service = host(destination / "controller/state")
    identity = read(ROOT / "source.json")["deployment"]
    original = Store(ROOT / "lost-source-state-retained/controller/state")
    assert {key: original.secret(key) for key in original.secret_names()} == {key: service.store.secret(key) for key in original.secret_names()}
    assert (ROOT / "lost-source-state-retained/controller/shared/rpc.key").read_bytes() != (destination / "controller/shared/rpc.key").read_bytes()
    accounts(service, identity)
    expected_database = json.loads(service.store.cipher.decrypt((ROOT / "database-baseline.enc").read_bytes()))
    assert database_proof(service, identity) == expected_database
    origin = "http://localhost:" + str(review["port"])
    prior_session = json.loads(service.store.cipher.decrypt((ROOT / "source-session.enc").read_bytes()))
    with httpx.Client(base_url=origin, trust_env=False, cookies=prior_session["cookies"]) as client:
        assert client.get("/api/config").status_code in {401, 403}
    password = read(ROOT / "access.json")["owner_password"]
    with login(origin, password) as client:
        prior = read(ROOT / "source-dashboard-config.json")["config"]
        prior["storage"]["data_root"] = next(iter(review["media"].values()))
        assert api(client, "config")["config"] == prior
        assert api(client, "backup-policy")["policy"]["enabled"] is False
        api(client, "refresh", {}, status=202)
        for _ in range(120):
            fresh = {row["id"] for row in api(client, "status")["integrations"] if row["state"] == "ready" and not row["stale"]}
            if set(PORTS) <= fresh:
                break
            time.sleep(1)
        assert set(PORTS) <= fresh, "Recovered dashboard integrations did not authenticate."
    expected_media = read(ROOT / "source-media-hashes.json")
    assert hashes(Path(read(ROOT / "source.json")["media"])) == expected_media
    assert hashes(Path(next(iter(review["media"].values())))) == expected_media
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.goto(origin)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=False).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        page.get_by_role("button", name="Backups", exact=True).click()
        expect(page.get_by_text("Recovered host. Review backup storage and enable the schedule again.", exact=False)).to_be_visible()
        page.screenshot(path=str(ROOT / "claimed-recovered-dashboard.png"), full_page=True)
        browser.close()
    preserved()
    write("verification.json", {"passed": True, "apps_reconstructed": 5, "claimed_plex_identity_preserved": True,
        "library_ids_and_original_media_read_preserved": True, "seerr_fresh_plex_owner_login": True,
        "seerr_owner_permissions_pending_request_and_arr_connections_preserved": True,
        "tautulli_fresh_password_login_and_authenticated_same_plex_server": True,
        "three_app_databases_pass_integrity_and_record_preservation_checks": True,
        "controller_credentials_and_dashboard_password_preserved": True, "old_stackarr_sessions_revoked": True,
        "private_controller_enrollment_regenerated": True,
        "five_dashboard_integrations_authenticated": True, "backup_schedule_paused": True,
        "source_state_unavailable_during_restore": True, "new_media_location_used": True,
        "sample_files_preserved_per_copy": len(expected_media), "original_labs_and_main_preserved": True})
    print("Recovered claimed Plex, fresh Seerr Plex login, Tautulli login/monitoring and all five dashboard integrations pass.", flush=True)


def finish():
    assert read(ROOT / "verification.json")["passed"]
    review = read(ROOT / "recovery-review.json")
    destination = scoped(review["destination"])
    service = host(destination / "controller/state")
    assert not (ROOT / "partial-plex-proof.xml").exists() and not (destination / "recovered-dashboard").exists()
    identity = read(ROOT / "source.json")["deployment"]
    payload = load_receipt(service, identity)
    script = """import asyncio,json
from pathlib import Path
from stackarr.store import Store
from stackarr.integrations import collect
async def main():
 store=Store(Path('/var/lib/stackarr')); cfg=store.config()[1]
 async def one(key,app):
  try: await collect(key,app,store.secret(key)); return key,True
  except Exception: return key,False
 print(json.dumps(dict(await asyncio.gather(*(one(k,a) for k,a in cfg.integrations.items() if a.enabled)))))
asyncio.run(main())
"""
    dashboard = command(["ps", "-q", "--no-trunc", "--filter", "name=^/stackarr-plex-lab-bc615eaf1fe6-stackarr-1$"])
    fresh = json.loads(command(["exec", dashboard, "python", "-c", script]))
    assert len(fresh) == 9 and all(fresh.values())
    write("main-authenticated-monitoring.json", fresh)
    stop_controller(destination)
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f",
             str(destination / "controller/state/deployments" / identity / "compose.json"), "stop", "--timeout", "90"])
    installation = read(destination / "installation.json")
    command(["compose", "--project-name", installation["project"], "-f", str(destination / "compose.json"), "stop"])
    for key in PORTS:
        assert not inspect_container(service, identity, payload, key)["State"]["Running"]
    for port in (review["port"], review["controller_port"], *PORTS.values()):
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    preserved()
    report = read(ROOT / "verification.json") | read(ROOT / "recovery-acceptance.json") | {
        "existing_nine_main_integrations_authenticated": True, "main_media_files_preserved": len(read(ROOT / "main-before.json")["media"]),
        "isolated_recovered_apps_dashboard_controller_stopped": True, "original_test_containers_remained_stopped": True,
        "configuration_volumes_keys_encrypted_recovery_files_and_media_retained": True,
        "scope": "Same-computer isolated Docker reconstruction; replacement Windows/native dialogs and revoked/shared cloud-account credentials remain separate gates.",
        "package": PACKAGE.name}
    write("acceptance.json", report)
    print("Claimed-account whole-host recovery acceptance passed. Lab stopped; existing nine apps, settings and media preserved.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "configure", "backup", "loss", "recover", "verify", "finish"))
    args = parser.parse_args()
    globals()[args.phase]()
