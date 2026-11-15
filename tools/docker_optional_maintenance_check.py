"""Five-app maintenance acceptance, restricted to a fresh original-sample lab.

Never copies an existing Plex identity or account token. Account fixtures and
fault injection belong only to this maintainer process, never the product API.
"""

import argparse
import asyncio
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from stackarr.app_backups import AppBackups, compatibility
from stackarr.app_maintenance import AppMaintenance
from stackarr.companions import Companions
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.onboarding import SaveDraft, SetupDraft, initialize, save
from stackarr.store import Store
from stackarr.updates import Updates, catalog
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import command, hashes
from tools.plex_fixture import write_sample

ROOT = Path("test-results/docker-optional-maintenance-20261018").resolve()
STATE = ROOT / "package-state/controller/state"
APPS = ("plex", "seerr", "tautulli", "kuma", "cleanuparr")
PORTS = {key: 43250 + n for n, key in enumerate(APPS)}


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2))


def host():
    location = STATE
    active = ROOT / "packaged-installation.json"
    if active.exists():
        location = Path(json.loads(active.read_text())["state"]).resolve()
        assert location.is_relative_to(ROOT) and not location.is_symlink() and not location.is_junction()
    return Deployments(Store(location), auto_logins=True)


def preserved():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert hashes(ROOT / "media") == json.loads((ROOT / "media-before.json").read_text())


def prepare():
    assert (ROOT / "main-before.json").exists() and not (ROOT / "lab.json").exists()
    media = ROOT / "media"
    media.mkdir()
    write_sample(media / "movies/Stackarr Maintenance Fixture/Stackarr Maintenance Fixture.avi")
    (media / "tv").mkdir()
    (media / "preserve.txt").write_text("Original isolated sample media; preserve unchanged.")
    write("media-before.json", hashes(media))
    service = host()
    initialize(service.store)
    save(service.store, SaveDraft(revision=1, draft=SetupDraft(apps=list(APPS), port_mode="custom",
        data_root=str(media), choices={key: {"port": port} for key, port in PORTS.items()})))
    previous = json.loads((ROOT / "previous-images.json").read_text())
    assert set(previous) == set(APPS)
    payload = service.review()
    # Only this fresh lab starts on earlier official releases. Production's
    # immutable installation/update catalogs remain the authority for users.
    for key in APPS:
        payload["compose"]["services"][key]["image"] = previous[key]["image"]
    identity = service.enqueue(payload)
    write("lab.json", {"deployment": identity, "ports": PORTS})
    asyncio.run(service.run_one())
    row = next(row for row in service.rows() if row["id"] == identity)
    assert row["state"] == "needs-setup", row["message"]
    payload = load_receipt(service, identity)
    for key in APPS:
        info = inspect_container(service, identity, payload, key)
        assert info["State"]["Running"]
        command(["exec", info["Id"], "/bin/sh", "-c", "printf 'Original isolated app settings' > "
            + payload["compose"]["services"][key]["volumes"][0]["target"] + "/stackarr-maintenance-sentinel.txt"])
    preserved()
    print("Fresh five-app lab installed on distinct official baseline images; existing apps preserved.", flush=True)


def fixture_setup():
    """Fresh unclaimed Plex and local Seerr account; no personal cloud token."""
    import httpx

    service = host()
    identity = json.loads((ROOT / "lab.json").read_text())["deployment"]
    payload = load_receipt(service, identity)
    with httpx.Client(base_url="http://127.0.0.1:43250", trust_env=False, timeout=30, headers={"Accept": "application/json"}) as client:
        machine = client.get("/identity").json()["MediaContainer"]
        assert not machine["claimed"]
        write("plex-origin.json", {"identity": machine["machineIdentifier"]})
        if not client.get("/library/sections").json()["MediaContainer"].get("Directory"):
            result = client.post("/library/sections", params={"name": "Original maintenance samples", "type": "movie",
                "agent": "com.plexapp.agents.none", "scanner": "Plex Movie Scanner", "language": "xn", "location": "/data/movies"})
            result.raise_for_status()
        for row in client.get("/library/sections").json()["MediaContainer"]["Directory"]:
            client.get("/library/sections/" + row["key"] + "/refresh").raise_for_status()
    info = inspect_container(service, identity, payload, "seerr")
    if not info["State"]["Running"]:
        command(["start", info["Id"]])
        time.sleep(15)
    password = secrets.token_urlsafe(32)
    script = ROOT / "seerr-password-fixture.cjs"
    script.write_text("require('fs').writeFileSync('/app/config/fixture-password-hash',require('bcrypt').hashSync(" + json.dumps(password) + ",12))")
    command(["cp", str(script), info["Id"] + ":/app/stackarr-fixture.cjs"])
    command(["exec", info["Id"], "node", "/app/stackarr-fixture.cjs"])
    password_hash = command(["exec", info["Id"], "cat", "/app/config/fixture-password-hash"])
    command(["stop", "--timeout", "60", info["Id"]])
    database_dir = ROOT / "seerr-fixture-db"
    assert not database_dir.exists()
    command(["cp", info["Id"] + ":/app/config/db", str(database_dir)])
    database = database_dir / "db.sqlite3"
    with sqlite3.connect(database) as db:
        columns = db.execute('PRAGMA table_info("user")').fetchall()
        write("seerr-user-schema.json", columns)
        db.execute('INSERT INTO user (id,email,username,password,userType,permissions,avatar) VALUES (1,?,?,?,?,?,?)',
                   ("fixture@stackarr.invalid", "Stackarr isolated fixture", password_hash, 2, 2, ""))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()
    settings = json.loads(command(["cp", info["Id"] + ":/app/config/settings.json", str(ROOT / "seerr-settings-private.json")]) or (ROOT / "seerr-settings-private.json").read_text())
    settings["public"]["initialized"] = True
    settings["main"].update(localLogin=True, mediaServerLogin=False, newPlexLogin=False, versionCheck=False)
    settings["plex"].update(name="Isolated unclaimed fixture", ip="host.docker.internal", port=43250, useSsl=False, machineId=machine["machineIdentifier"])
    settings_file = ROOT / "seerr-settings-private.json"
    settings_file.write_text(json.dumps(settings))
    command(["cp", str(database), info["Id"] + ":/app/config/db/db.sqlite3"])
    empty = ROOT / "empty-sqlite-sidecar"
    empty.write_bytes(b"")
    for suffix in ("-wal", "-shm"):
        command(["cp", str(empty), info["Id"] + ":/app/config/db/db.sqlite3" + suffix])
    command(["cp", str(settings_file), info["Id"] + ":/app/config/settings.json"])
    command(["run", "--rm", "--network", "none", "--user", "0", "--entrypoint", "chown", "-v",
        "stackarr-owned-" + identity + "_seerr-config:/app/config", payload["compose"]["services"]["seerr"]["image"],
        "-R", "1000:1000", "/app/config"])
    command(["start", info["Id"]])
    revision, config = service.store.config()
    service.store.save(config, revision, {"seerr": {"api_key": settings["main"]["apiKey"]}})
    write("seerr-login-private.json", {"email": "fixture@stackarr.invalid", "password": password})
    companions = Companions(service)
    state = companions.state(identity)
    for key in ("kuma", "cleanuparr"):
        state["apps"][key] = {"username": "stackarr", "password": secrets.token_urlsafe(32)}
        companions.save(identity, state)
        def callback():
            companions.save(identity, state)
        getattr(companions, {"cleanuparr": "cleanup"}.get(key, key))(identity, payload, state["apps"][key], callback, companions.sources())
    revision, config = service.store.config()
    service.store.save(config, revision, {key: {"api_key": state["apps"][key]["api_key"]} for key in ("kuma", "cleanuparr")})
    time.sleep(25)
    preserved()
    print("Isolated local accounts configured. Plex/Tautulli account acceptance requires a separately claimed test server.", flush=True)


def auxiliary_setup():
    """New Arr/download services provide real saved connections for the five apps."""
    import httpx

    from stackarr import seerr_wiring
    from stackarr.onboarding import read

    service = host()
    draft = read(service.store)
    apps = ("sonarr", "radarr", "qbittorrent")
    save(service.store, SaveDraft(revision=draft["revision"], draft=SetupDraft(apps=list(apps), port_mode="custom",
        data_root=str(ROOT / "media"), choices={key: {"port": 43260 + n} for n, key in enumerate(apps)})))
    operation = service.enqueue(service.review())
    asyncio.run(service.run_one())
    assert next(row for row in service.rows() if row["id"] == operation)["state"] == "needs-setup"
    write("auxiliary.json", {"deployment": operation})
    revision, config = service.store.config()
    for key in apps:
        config.integrations[key].peer_url = "http://host.docker.internal:" + str(config.integrations[key].port)
    service.store.save(config, revision, {})
    for folder in ("tv", "movies"):
        (ROOT / "media/media" / folder).mkdir(parents=True, exist_ok=True)
    async def wire():
        async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
            for key in ("sonarr", "radarr"):
                app = service.store.config()[1].integrations[key]
                result = await client.post(app.url + "/api/v3/rootfolder", headers={"X-Api-Key": service.store.secret(key)["api_key"]},
                    json={"path": "/data/media/" + ("tv" if key == "sonarr" else "movies")})
                result.raise_for_status()
            changes, notices = await seerr_wiring.build(service.store, client)
            assert len(changes) == 2, notices
            for change in changes:
                await seerr_wiring.apply(service.store, client, change)
    asyncio.run(wire())
    identity = json.loads((ROOT / "lab.json").read_text())["deployment"]
    companions = Companions(service)
    state = companions.state(identity)
    payload = load_receipt(service, identity)
    for key in ("kuma", "cleanuparr"):
        getattr(companions, {"cleanuparr": "cleanup"}.get(key, key))(identity, payload, state["apps"][key],
            lambda: companions.save(identity, state), companions.sources())
    preserved()
    print("Fresh auxiliary Sonarr, Radarr and qBittorrent connected to isolated Seerr, Kuma and disabled Cleanuparr.", flush=True)


def finish_plex():
    """Run only after the user claims this new server; no copied cloud identity."""
    import xml.etree.ElementTree as ET

    import httpx

    from stackarr.companions import reply
    from stackarr.finish_setup import read_candidate
    from stackarr.integrations import collect

    # The independent account handoff must not reconcile another test worker's
    # in-flight maintenance journal. No Lifecycle/Deployments constructor here.
    service = object.__new__(Deployments)
    service.store, service.runner = Store(STATE), subprocess.run
    payload = load_receipt(service, target())
    app = service.store.config()[1].integrations["plex"]
    credential = read_candidate(service, target(), payload, "plex", app)
    assert credential and credential["api_key"] != "isolated-unclaimed-server-fixture", "Finish claiming only the new test Plex server first."
    with httpx.Client(base_url=app.url, timeout=15, trust_env=False,
                      headers={"Accept": "application/json", "X-Plex-Token": credential["api_key"]}) as client:
        identity = client.get("/identity").json()["MediaContainer"]
        assert identity["claimed"]
        original = (json.loads((ROOT / "plex-origin.json").read_text())["identity"] if (ROOT / "plex-origin.json").exists()
                    else ET.parse(ROOT / "plex-fixture-private.xml").getroot().attrib["ProcessedMachineIdentifier"])
        assert identity["machineIdentifier"] == original
        info = inspect_container(service, target(), payload, "plex")
        assert info["Id"] not in json.loads((ROOT / "main-before.json").read_text())["running"]
    asyncio.run(collect("plex", app, credential))
    revision, config = service.store.config()
    service.store.save(config, revision, {"plex": credential})
    companions = Companions(service)
    state = companions.state(target())
    if "tautulli" not in state["apps"]:
        state["apps"]["tautulli"] = {"username": "stackarr", "password": secrets.token_urlsafe(32)}
        companions.save(target(), state)
        companions.tautulli(target(), payload, state["apps"]["tautulli"],
            lambda: companions.save(target(), state), companions.sources())
    record = state["apps"]["tautulli"]
    with companions.client(PORTS["tautulli"]) as client:
        companions.tautulli_session(client, "/auth/login")
        result = reply(client, "POST", "/auth/signin", data={"username": record["username"], "password": record["password"], "admin_login": "1"})
        assert result["status"] == "success"
        config = companions.tautulli_config(target(), payload)
        assert config.get("PMS", "pms_identifier").strip('"') == original
        companions.tautulli_session(client, "/settings")
        reply(client, "POST", "/save_pms_token", data={"token": credential["api_key"]})
    record.update(complete=True, plex_identifier=original)
    companions.save(target(), state)
    revision, config = service.store.config()
    service.store.save(config, revision, {"tautulli": {"api_key": record["api_key"]}})
    asyncio.run(collect("tautulli", config.integrations["tautulli"], {"api_key": record["api_key"]}))
    preserved()
    write("plex-account-acceptance.json", {"fresh_claimed_identity_verified": True, "tautulli_authenticated_monitoring": True,
        "existing_plex_identities_not_adopted": True, "existing_server_tokens_not_copied": True})
    print("New user-claimed Plex lab and Tautulli authenticated monitoring verified privately.", flush=True)


def scan_fixture():
    """Retain the initial fixture; Plex intentionally ignores filenames with 'sample'."""
    import httpx

    service = host()
    credential = Updates(service).credentials(target(), load_receipt(service, target()), "plex")
    before = json.loads((ROOT / "media-before.json").read_text())
    original = ROOT / "media/movies/Original Stackarr Sample/Original Stackarr Sample.avi"
    destination = ROOT / "media/movies/Stackarr Maintenance Fixture/Stackarr Maintenance Fixture.avi"
    destination.parent.mkdir(exist_ok=True)
    if not destination.exists():
        shutil.copyfile(original, destination)
    after = hashes(ROOT / "media")
    assert all(after[name] == value for name, value in before.items())
    write("media-before.json", after)
    with httpx.Client(base_url="http://127.0.0.1:43250", timeout=15, trust_env=False,
                      headers={"Accept": "application/json", "X-Plex-Token": credential["api_key"]}) as client:
        client.get("/library/sections/1/refresh").raise_for_status()
        for _ in range(90):
            rows = client.get("/library/sections/1/all").json()["MediaContainer"].get("Metadata", [])
            if rows:
                assert len(rows) == 1 and rows[0]["title"] == "Stackarr Maintenance Fixture"
                write("plex-library-before.json", {"items": [{name: row.get(name) for name in ("ratingKey", "title", "guid")} for row in rows]})
                preserved()
                print("Original generated AVI indexed in the claimed lab Plex; all earlier media files retained.", flush=True)
                return
            time.sleep(2)
    raise AssertionError("The original generated Plex fixture did not finish indexing")


def target():
    return json.loads((ROOT / "lab.json").read_text())["deployment"]


def checkpoint(service, key):
    payload = load_receipt(service, target())
    updates = Updates(service)
    credential = updates.credentials(target(), payload, key)
    value = updates.protected(payload | {"identity": target()}, key, credential)
    if key == "seerr":
        import httpx

        with httpx.Client(base_url="http://127.0.0.1:43251", trust_env=False, timeout=15) as client:
            login = client.post("/api/v1/auth/local", json=json.loads((ROOT / "seerr-login-private.json").read_text()))
            assert login.status_code == 200 and login.json()["id"] == 1
    if key == "plex":
        import xml.etree.ElementTree as ET

        import httpx

        with httpx.Client(base_url="http://127.0.0.1:43250", trust_env=False, timeout=15,
                          headers={"Accept": "application/json", "X-Plex-Token": credential["api_key"]}) as client:
            identity = client.get("/identity").json()["MediaContainer"]
            assert identity["claimed"] and identity["machineIdentifier"] == value["identity"]
            assert identity["machineIdentifier"] == ET.parse(ROOT / "plex-fixture-private.xml").getroot().attrib["ProcessedMachineIdentifier"]
            rows = client.get("/library/sections/1/all").json()["MediaContainer"].get("Metadata", [])
            value["fixture_items"] = [{name: row.get(name) for name in ("ratingKey", "title", "guid")} for row in rows]
            assert value["fixture_items"] == json.loads((ROOT / "plex-library-before.json").read_text())["items"]
    return value


def peers(service, key):
    return {app: inspect_container(service, row["id"], load_receipt(service, row["id"]), app)["Id"]
            for row in service.rows() if row["state"] == "needs-setup" for app in row["apps"] if app != key}


def verify(service, key, baseline, other):
    assert checkpoint(service, key) == baseline
    assert peers(service, key) == other
    payload = load_receipt(service, target())
    info = inspect_container(service, target(), payload, key)
    if key == "plex":
        with service.store.db() as db:
            reviews = [json.loads(row[0]) for row in db.execute("SELECT payload FROM deployment_actions ORDER BY created")]
        reviewed = next(row["resources"]["auxiliary"] for row in reviews
                        if row.get("app") == "plex" and row.get("resources", {}).get("auxiliary"))
        assert Updates(service).auxiliary(payload, key, info) == reviewed
    folder = payload["compose"]["services"][key]["volumes"][0]["target"]
    assert command(["exec", info["Id"], "cat", folder + "/stackarr-maintenance-sentinel.txt"]) == "Original isolated app settings"
    assert command(["exec", info["Id"], "/bin/sh", "-c", "if test -e " + folder + "/stackarr-fault-marker; then printf present; else printf absent; fi"]) == "absent"
    preserved()


def mutation(service, payload, key):
    info = inspect_container(service, target(), payload, key)
    folder = payload["compose"]["services"][key]["volumes"][0]["target"]
    command(["exec", info["Id"], "/bin/sh", "-c",
        "printf 'Candidate changed configuration' > " + folder + "/stackarr-maintenance-sentinel.txt; printf 'Confirmed candidate write' > " + folder + "/stackarr-fault-marker"])
    assert command(["exec", info["Id"], "cat", folder + "/stackarr-fault-marker"]) == "Confirmed candidate write"


def report_case(key, case, **extra):
    filename = ROOT / "native-report.json"
    record = json.loads(filename.read_text()) if filename.exists() else {"cases": []}
    record["cases"].append({"app": key, "case": case, "passed": True, **extra})
    write(filename.name, record)
    print(key + ": " + case + " passed; settings, logins, media and peer container IDs preserved.", flush=True)


def maintenance(key):
    assert key in APPS
    service = host()
    baseline, other = checkpoint(service, key), peers(service, key)
    original = compatibility(load_receipt(service, target()))
    recorded = {row["case"] for row in json.loads((ROOT / "native-report.json").read_text())["cases"] if row["app"] == key} if (ROOT / "native-report.json").exists() else set()
    # Authenticated same-image repair and failure after confirmed config writes.
    original_health = AppMaintenance.health
    for fail in (False, True):
        if ("failed-repair-recovery" if fail else "repair") in recorded:
            continue
        injected = False
        def health(self, review, payload, **kwargs):
            nonlocal injected
            ready = original_health(self, review, payload, **kwargs)
            if ready and fail and not injected:
                mutation(service, payload, key)
                injected = True
                return False
            return ready
        AppMaintenance.health = health
        try:
            operation = service.actions.enqueue(service.actions.review(target(), key, "repair"))
            asyncio.run(service.actions.run_one())
            row = next(row for row in service.actions.rows() if row["id"] == operation)
            assert row["state"] == ("failed-recovered" if fail else "succeeded"), row["message"]
            if fail:
                assert injected
            verify(service, key, baseline, other)
            report_case(key, "failed-repair-recovery" if fail else "repair", candidate_config_writes_confirmed=injected)
        finally:
            AppMaintenance.health = original_health
    updates = Updates(service)
    if "distinct-image-update-and-rollback" not in recorded:
        result = updates.execute(updates.review(target(), key))
        assert result["state"] == "succeeded", result["message"]
        verify(service, key, baseline, other)
        run = next(row for row in updates.listing()["history"] if row["app"] == key)["id"]
        assert updates.execute(updates.review(target(), key, "rollback", run))["state"] == "succeeded"
        assert compatibility(load_receipt(service, target())) == original
        verify(service, key, baseline, other)
        report_case(key, "distinct-image-update-and-rollback", previous=updates.read(run)["old_version"], candidate=catalog()["apps"][key]["version"])
    normal = updates.health
    written = False
    def fail_candidate(payload, app, secret, version, seconds=180):
        nonlocal written
        if payload["compose"]["services"][key]["image"] == catalog()["apps"][key]["image"]:
            mutation(service, payload, key)
            written = True
            return False
        return normal(payload, app, secret, version, seconds)
    updates.health = fail_candidate
    outcome = updates.execute(updates.review(target(), key))
    assert written and outcome["state"] == "rolled-back", outcome["message"]
    verify(service, key, baseline, other)
    report_case(key, "failed-update-recovery", candidate_config_writes_confirmed=True)
    worker = subprocess.run([sys.executable, "-m", "tools.docker_optional_maintenance_check", "crash-update", "--app", key], timeout=400)
    assert worker.returncode == 77
    operation = json.loads((ROOT / (key + "-interrupted-update.json")).read_text())["id"]
    subprocess.run([sys.executable, "-m", "tools.docker_optional_maintenance_check", "recover-update", "--app", key, "--operation", operation], check=True, timeout=400)
    verify(service, key, baseline, other)
    report_case(key, "fresh-process-interrupted-update-recovery", receipt_file_database_gap=True, candidate_config_writes_confirmed=True)


def crash_update(key):
    service = host()
    updates = Updates(service)
    normal = updates.health
    def crash(payload, app, secret, version, seconds=180):
        if payload["compose"]["services"][key]["image"] == catalog()["apps"][key]["image"]:
            mutation(service, payload, key)
            record = next(row for row in updates.listing()["history"] if row["app"] == key)
            run = updates.read(record["id"])
            updates.save(run, "running", "committing-receipt")
            updates.files(run).write_text(json.dumps(run["new"]["compose"], sort_keys=True))
            write(key + "-interrupted-update.json", {"id": run["id"]})
            print("Exiting only isolated maintenance worker after confirmed configuration writes and receipt gap.", flush=True)
            os._exit(77)
        return normal(payload, app, secret, version, seconds)
    updates.health = crash
    updates.execute(updates.review(target(), key))
    raise AssertionError("Expected isolated worker exit")


def recover_update(key, operation):
    updates = Updates(host())
    assert updates.read(operation)["deployment"] == target() and updates.read(operation)["app"] == key
    assert updates.execute(updates.review(target(), key, "update-recover", operation))["state"] == "succeeded"


def backup_restore(key):
    service = host()
    baseline, other = checkpoint(service, key), peers(service, key)
    from stackarr.updates import response_version

    updates = Updates(service)
    payload = load_receipt(service, target())
    credential = updates.credentials(target(), payload, key)
    version = asyncio.run(response_version(key, "http://127.0.0.1:" + str(PORTS[key]), credential))
    backups = AppBackups(service)
    backups.execute(backups.review(target(), apps=[key]))
    saved = backups.rows()[0]["id"]
    payload = load_receipt(service, target())
    mutation(service, payload, key)
    backups.execute(backups.review(target(), saved))
    assert updates.health(payload | {"identity": target()}, key, credential, version)
    verify(service, key, baseline, other)
    report_case(key, "encrypted-backup-restore", media_hashes_preserved=len(hashes(ROOT / "media")))


def verify_native_evidence():
    expected = {"repair", "failed-repair-recovery", "distinct-image-update-and-rollback", "failed-update-recovery",
                "fresh-process-interrupted-update-recovery", "encrypted-backup-restore"}
    record = json.loads((ROOT / "native-report.json").read_text())
    assert len(record["cases"]) == 30
    for key in APPS:
        assert {row["case"] for row in record["cases"] if row["app"] == key} == expected
    # Inspect immutable native snapshots without reconciling the separately
    # running packaged controller's journal or calling any app container.
    service = object.__new__(Deployments)
    service.store, service.runner = Store(STATE), subprocess.run
    backups = AppBackups(service)
    with service.store.db() as db:
        rows = [json.loads(raw) for (raw,) in db.execute("SELECT payload FROM deployment_actions WHERE state='failed-recovered' ORDER BY created DESC")]
    proofs = []
    for key in APPS:
        review = next(row for row in rows if row.get("app") == key and row.get("action") == "repair")
        with tempfile.TemporaryDirectory(prefix="repair-write-proof-", dir=ROOT) as folder:
            stage = Path(folder)
            for kind, identity in (("before", review["run"]["backup"]), ("candidate", review["run"]["recovery_backup"])):
                work = stage / kind
                work.mkdir()
                backups.materialize(identity, work)
                with tarfile.open(work / key / "volume.tar") as archive:
                    members = {member.name.removeprefix("./"): member for member in archive.getmembers()}
                    sentinel = archive.extractfile(members["stackarr-maintenance-sentinel.txt"]).read()
                    assert sentinel == (b"Original isolated app settings" if kind == "before" else b"Candidate changed configuration")
                    if kind == "candidate":
                        assert archive.extractfile(members["stackarr-fault-marker"]).read() == b"Confirmed candidate write"
                    else:
                        assert "stackarr-fault-marker" not in members
        proofs.append({"app": key, "verified_before_snapshot": True, "verified_failed_candidate_write_snapshot": True})
    write("native-evidence.json", {"passed": True, "cases": 30, "apps": 5, "repair_write_proofs": proofs})
    print("All 30 native cases verified; five encrypted safety snapshots prove actual failed-candidate configuration writes.", flush=True)


def finalize():
    from stackarr.self_update import SelfUpdates
    from stackarr.updates import app_version, response_version
    from tools.docker_folder_ports_check import stop_lab

    packaged = json.loads((ROOT / "packaged-installation.json").read_text())
    active_state = Path(packaged["state"]).resolve()
    assert active_state.is_relative_to(ROOT)
    with sqlite3.connect(active_state / "stackarr.db") as db:
        assert not db.execute("SELECT 1 FROM app_updates WHERE state IN ('running','needs-recovery')").fetchone()
        assert not db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running','needs-recovery')").fetchone()
    browser = json.loads((ROOT / "packaged-browser-report.json").read_text())
    native = json.loads((ROOT / "native-evidence.json").read_text())
    assert browser["passed"] and len(browser["cases"]) == len(APPS) and native["passed"]
    assert {row["app"] for row in browser["cases"]} == set(APPS)
    assert all(row["repair"] and row["distinct_image_update"] and row["rollback"] for row in browser["cases"])
    service = host()
    updates = Updates(service)
    payload = load_receipt(service, target())
    previous = json.loads((ROOT / "previous-images.json").read_text())
    versions = {row["app"]: row["previous"] for row in json.loads((ROOT / "native-report.json").read_text())["cases"]
                if row["case"] == "distinct-image-update-and-rollback"}
    for key in APPS:
        assert payload["compose"]["services"][key]["image"] == previous[key]["image"]
        credential = updates.credentials(target(), payload, key)
        actual = asyncio.run(response_version(key, "http://127.0.0.1:" + str(PORTS[key]), credential))
        assert app_version(actual) == app_version(versions[key])
        last_update = next(row for row in updates.listing()["history"] if row["app"] == key)
        assert last_update["state"] == "rolled-back"
        assert updates.protected(payload, key, credential) == updates.read(last_update["id"])["protected"]
        verify(service, key, checkpoint(service, key), peers(service, key))
        print("Final image, saved settings, login and media verified: " + key, flush=True)
    runtime = SelfUpdates(Path(packaged["root"]) / "package-state")
    active = runtime.active()
    _, manifest = runtime.release(active["release"])
    assert runtime.controller_probe(active)["executable"] == manifest["files"]["StackarrPreview.exe"]
    assert manifest == json.loads((Path(browser["package"]) / "manifest.json").read_text())
    protected_runtime = runtime.protected(active)  # verifies dashboard image/recipe
    # Connection completion delivers current credentials to the dashboard's
    # encrypted store. Check from its actual network and store, rather than
    # the controller's older installation-time credential cache.
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
  except Exception as exc:
   return {'app':key,'authenticated':False,'error':getattr(exc,'code',type(exc).__name__)}
 return await asyncio.gather(*(one(key,app) for key,app in store.config()[1].integrations.items() if app.enabled))
print(json.dumps(asyncio.run(main())))
"""
    main_dashboard = command(["ps", "-q", "--no-trunc", "--filter", "name=^/stackarr-plex-lab-bc615eaf1fe6-stackarr-1$"])
    monitoring = json.loads(command(["exec", main_dashboard, "python", "-c", monitoring_script]))
    assert len(monitoring) == 9 and all(row["authenticated"] for row in monitoring)
    write("main-dashboard-monitoring.json", {"source": "actual dashboard network and encrypted credentials", "apps": monitoring})
    preserved()
    summary = {"passed": True, "apps": list(APPS), "native_cases": 30, "packaged_browser_actions": 15,
        "five_confirmed_repair_write_snapshots": True, "fresh_claimed_plex_identity_and_video_preserved": True,
        "plex_original_transcode_volume_preserved": True, "seerr_local_password_login_verified": True,
        "tautulli_plex_connection_verified": True, "kuma_monitors_and_metrics_key_preserved": True,
        "cleanup_dry_run_and_disabled_jobs_preserved": True, "main_fresh_authenticated_integrations": 9,
        "main_dashboard_and_app_container_ids_preserved": True, "main_settings_credentials_media_preserved": True,
        "main_tracked_media_files": 16, "lab_tracked_media_files": len(hashes(ROOT / "media")),
        "frozen_private_controller_verified": True, "package": manifest["release"]}
    write("acceptance.json", summary)
    identities = [target(), json.loads((ROOT / "auxiliary.json").read_text())["deployment"]]
    stop_lab(Path(packaged["root"]), packaged["installation"], identities)
    # Frozen one-file executables can have a parent/child pair. End only the
    # exact isolated controller command line, then prove its listener is gone.
    controller_root = active_state.parent.resolve()
    assert controller_root.is_relative_to(ROOT)
    env = os.environ | {"STACKARR_OPTIONAL_STOP_ROOT": str(controller_root)}
    stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_OPTIONAL_STOP_ROOT) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert stopped.returncode == 0
    for port in (packaged["installation"]["port"], packaged["installation"]["controller_port"]):
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    for identity in identities:
        saved = load_receipt(service, identity)
        assert all(not inspect_container(service, identity, saved, key)["State"]["Running"] for key in saved["apps"])
    assert not json.loads(command(["inspect", protected_runtime["container"]]))[0]["State"]["Running"]
    # Abrupt test-worker exits can leave plaintext work archives. Remove only
    # generated temporary directories, retaining every encrypted snapshot/key.
    removed = 0
    for backups in (STATE / "app-backups", active_state / "app-backups"):
        for path in backups.iterdir():
            if path.is_dir() and path.name.startswith(("work-", "update-", "maintenance-")):
                assert path.resolve().is_relative_to(ROOT) and not path.is_symlink() and not path.is_junction()
                assert all(not child.is_symlink() and not child.is_junction() for child in path.rglob("*"))
                shutil.rmtree(path)
                removed += 1
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    summary.update(isolated_lab_stopped=True, volumes_media_keys_and_encrypted_snapshots_retained=True,
                   temporary_plaintext_work_directories_removed=removed)
    write("acceptance.json", summary)
    print("Five-app acceptance complete: 30 native cases, 15 packaged browser actions; existing nine apps preserved and lab stopped with data retained.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "fixture_setup", "auxiliary_setup", "finish_plex", "scan_fixture", "maintenance", "crash-update", "recover-update", "backup_restore", "verify_native_evidence", "finalize"))
    parser.add_argument("--app", choices=APPS)
    parser.add_argument("--operation")
    args = parser.parse_args()
    if args.action == "recover-update":
        recover_update(args.app, args.operation)
    elif args.action in {"maintenance", "crash-update", "backup_restore"}:
        globals()[args.action.replace("-", "_")](args.app)
    else:
        globals()[args.action]()


if __name__ == "__main__":
    main()
