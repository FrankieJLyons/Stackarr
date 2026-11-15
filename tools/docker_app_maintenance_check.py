"""Acceptance restricted to the retained disposable original-sample Docker lab."""

import argparse
import asyncio
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.app_maintenance import AppMaintenance
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.self_update import FINGERPRINT, SelfUpdates, fingerprint
from stackarr.store import Store
from stackarr.updates import Updates
from tools.docker_folder_ports_check import MAIN, command, hashes, main_settings

LAB = Path("test-results/docker-core-05cebfd84fd1").resolve()
STATE = LAB / "package-state"
CORE = "c6903afb2218471aa2a45be825f625e5"
PROJECT = "stackarr-preview-9e8929fdc74c"
ORIGIN = "http://localhost:29140"
OUTPUT = Path("test-results/docker-app-maintenance-20261018").resolve()
TARGET = "qbittorrent"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(name, value):
    (OUTPUT / name).write_text(json.dumps(value, indent=2))


def host():
    return Deployments(Store(STATE / "controller/state"))


@contextmanager
def owner(origin=ORIGIN, root=LAB):
    client = httpx.Client(base_url=origin, trust_env=False, timeout=180, headers={"Origin": origin})
    response = client.post("/api/login", json={"password": read(root / "access.json")["owner_password"]})
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    try:
        yield client
    finally:
        client.close()


def main_snapshot():
    dashboard = command(["ps", "-q", "--no-trunc", "--filter", "name=^/stackarr-plex-lab-bc615eaf1fe6-stackarr-1$"])
    digest = command(["exec", dashboard, "python", "-c", FINGERPRINT + "\nprint(fingerprint('/var/lib/stackarr'))"])
    return {"dashboard": dashboard, "dashboard_settings": digest, "controller_settings": fingerprint(MAIN / "controller/state"),
        "apps": main_settings(), "media": hashes(MAIN / "media"), "running": command(["ps", "-q", "--no-trunc"]).splitlines()}


def main_preserved(allow_dashboard=False):
    before = read(OUTPUT / "main-before.json")
    after = main_snapshot()
    assert before["dashboard_settings"] == after["dashboard_settings"] and before["controller_settings"] == after["controller_settings"]
    assert before["apps"] == after["apps"] and before["media"] == after["media"]
    expected = set(before["running"]) - ({before["dashboard"]} if allow_dashboard else set())
    assert expected <= set(after["running"])


def login_hash(store):
    with store.db() as db:
        rows = db.execute("SELECT * FROM deployment_logins ORDER BY id").fetchall()
    return hashlib.sha256(json.dumps([[v.hex() if isinstance(v, bytes) else v for v in row] for row in rows]).encode()).hexdigest()


def settings(service, payload):
    return {key: Updates(service).protected(payload, key, service.store.secret(key)) for key in payload["apps"]}


def preserved(absent=False):
    main_preserved()
    before = read(OUTPUT / "lab-before.json")
    service = host()
    payload = load_receipt(service, CORE)
    assert hashes(LAB / "media") == before["media"]
    assert service.store.config()[1].model_dump() == before["config"] and login_hash(service.store) == before["logins"]
    for key in payload["apps"]:
        assert hashlib.sha256(json.dumps(service.store.secret(key), sort_keys=True).encode()).hexdigest() == before["credentials"][key]
        if key == TARGET and absent:
            assert AppMaintenance(service).container(CORE, payload, key) is None
            AppMaintenance(service).resources(CORE, payload, key)
            continue
        info = inspect_container(service, CORE, payload, key)
        assert info["State"]["Running"]
        if key == TARGET:
            marker = command(["exec", info["Id"], "/bin/sh", "-c", "if test -e /config/stackarr-repair-fault-marker.txt; then printf present; else printf absent; fi"])
            assert marker == "absent"
        if key != TARGET:
            assert info["Id"] == before["ids"][key]
        for _ in range(60):
            try:
                assert Updates(service).protected(payload, key, service.store.secret(key)) == before["protected"][key]
                break
            except Exception:
                time.sleep(1)
        else:
            raise AssertionError("Lab settings or credentials changed")


def wait_action(identity, expected="succeeded"):
    previous = None
    for _ in range(480):
        with sqlite3.connect(STATE / "controller/state/stackarr.db") as db:
            row = db.execute("SELECT state,message FROM deployment_actions WHERE id=?", (identity,)).fetchone()
        if row and row[0] != previous:
            print("App maintenance: " + row[0], flush=True)
            previous = row[0]
        if row and row[0] not in {"queued", "running"}:
            assert row[0] == expected, row[1]
            write(identity + "-result.json", {"id": identity, "state": row[0], "message": row[1]})
            return
        time.sleep(.5)
    raise AssertionError("Maintenance worker did not finish")


def prepare(package):
    OUTPUT.mkdir(exist_ok=True)
    if not (OUTPUT / "main-before.json").exists():
        write("main-before.json", main_snapshot())
    main_preserved()
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(STATE), "-NoBrowser"], capture_output=True, timeout=240)
    assert result.returncode == 0
    command(["compose", "--project-name", "stackarr-owned-" + CORE, "-f",
        str(STATE / "controller/state/deployments" / CORE / "compose.json"), "up", "-d", "--wait", "--wait-timeout", "180"])
    service = host()
    payload = load_receipt(service, CORE)
    for _ in range(90):
        try:
            protected = settings(service, payload)
            break
        except Exception:
            time.sleep(1)
    else:
        raise AssertionError("Retained core settings were unavailable")
    for key in payload["apps"]:
        AppMaintenance(service).review(CORE, key, "repair")
    write("lab-before.json", {"ids": {key: inspect_container(service, CORE, payload, key)["Id"] for key in payload["apps"]},
        "protected": protected, "config": service.store.config()[1].model_dump(), "logins": login_hash(service.store),
        "credentials": {key: hashlib.sha256(json.dumps(service.store.secret(key), sort_keys=True).encode()).hexdigest() for key in payload["apps"]},
        "media": hashes(LAB / "media")})
    print("Retained four-app lab ready; strict read-only repair reviews pass, main apps preserved.", flush=True)


def upgrade(archive, root=STATE, origin=ORIGIN, access_root=LAB):
    SelfUpdates(root).admit(archive)
    with owner(origin, access_root) as client:
        response = client.post("/api/stackarr-update-review", json={"action": "update"})
        response.raise_for_status()
        applied = client.post("/api/stackarr-update-apply", json={"review_token": response.json()["review_token"]})
        applied.raise_for_status()
        identity = applied.json()["id"]
    previous = None
    for _ in range(600):
        job = read(root / "stackarr-maintenance/jobs" / identity / "job.json")
        if job["phase"] != previous:
            print("Packaged dashboard update: " + job["phase"], flush=True)
            previous = job["phase"]
        if job["phase"] in {"succeeded", "failed-recovered", "needs-recovery"}:
            assert job["phase"] == "succeeded", job.get("failure", job["message"])
            write(("main-" if root == MAIN else "lab-") + "package-update.json", {"id": identity, "phase": job["phase"]})
            return
        time.sleep(.5)
    raise AssertionError("Packaged dashboard upgrade did not finish")


def signin(page):
    page.goto(ORIGIN)
    page.get_by_label("Password", exact=True).fill(read(LAB / "access.json")["owner_password"])
    page.get_by_role("button", name="Sign in", exact=False).click()
    page.get_by_role("button", name="Apps", exact=True).click()


def browser_action(page, action):
    page.locator('[data-check-install="' + CORE + '"]').click()
    label = "maintenance recovery" if action == "repair-recover" else action
    page.get_by_role("button", name="Review " + label + " qBittorrent", exact=True).click()
    apply = page.get_by_role("button", name={"repair": "Repair app", "remove": "Remove app, keep settings", "repair-recover": "Recover maintenance", "start": "Start app", "stop": "Stop app"}[action], exact=True)
    expect(apply).to_be_visible()
    page.screenshot(path=str(OUTPUT / (action + "-review.png")), full_page=True)
    with page.expect_response(lambda r: r.url.endswith("/api/deployments/actions/apply")) as response:
        apply.click()
    assert response.value.status == 202
    identity = response.value.json()["id"]
    wait_action(identity)
    page.get_by_role("button", name="Refresh app actions", exact=True).click()
    expect(page.locator("#lifecycle-history")).to_contain_text("succeeded")
    page.screenshot(path=str(OUTPUT / (action + "-succeeded.png")), full_page=True)
    return identity


def browser_flow():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(180000)
        signin(page)
        browser_action(page, "repair")
        # API checks use a separate process because Playwright owns an asyncio loop.
        subprocess.run([os.fspath(Path(".venv/Scripts/python.exe")), "-m", "tools.docker_app_maintenance_check", "--phase", "verify"], check=True)
        browser_action(page, "remove")
        subprocess.run([os.fspath(Path(".venv/Scripts/python.exe")), "-m", "tools.docker_app_maintenance_check", "--phase", "verify-absent"], check=True)
        with socket.socket() as listener:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", 42470))
            listener.listen(1)
            with owner() as client:
                rejected = client.post(f"/api/deployments/{CORE}/apps/{TARGET}/review", json={"action": "repair"})
                assert rejected.status_code == 409 and "port" in rejected.json()["detail"]
        page.get_by_role("button", name="Backups", exact=True).click()
        page.locator('[data-docker-backup="' + CORE + '"]').click()
        apply = page.get_by_role("button", name="Create backup", exact=True)
        expect(apply).to_be_visible()
        with page.expect_response(lambda r: r.url.endswith("/api/deployments/actions/apply")) as response:
            apply.click()
        wait_action(response.value.json()["id"])
        subprocess.run([os.fspath(Path(".venv/Scripts/python.exe")), "-m", "tools.docker_app_maintenance_check", "--phase", "verify-absent"], check=True)
        page.get_by_role("button", name="Apps", exact=True).click()
        browser_action(page, "repair")
        browser_action(page, "stop")
        browser_action(page, "repair")
        service = host()
        payload = load_receipt(service, CORE)
        stopped = inspect_container(service, CORE, payload, TARGET)["State"]
        assert not stopped["Running"] and stopped["Status"] == "created"
        assert stopped["StartedAt"].startswith("0001-")
        browser_action(page, "start")
        subprocess.run([os.fspath(Path(".venv/Scripts/python.exe")), "-m", "tools.docker_app_maintenance_check", "--phase", "verify"], check=True)
        browser.close()
    write("browser-report.json", {"passed": True, "repair": True, "remove_keeps_settings": True, "repair_removed_app": True,
        "occupied_saved_port_rejected": True, "backup_absent_app_without_starting": True, "stopped_state_preserved": True,
        "stopped_repair_never_started": True, "peer_app_ids_preserved": 3,
        "lab_media_hashes_preserved": 6, "main_media_hashes_preserved": 16})


def stop_lab_controller():
    env = os.environ | {"STACKARR_APP_MAINTENANCE_LAB_CONTROLLER": str(STATE / "controller")}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_APP_MAINTENANCE_LAB_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30)
    assert result.returncode == 0


def fault(crash=False):
    # Maintainer-only fault injection in this process, never a production environment flag.
    stop_lab_controller()
    service = host()
    review = service.actions.review(CORE, TARGET, "repair")
    operation = service.actions.enqueue(review)
    write("interrupted-operation.json" if crash else "failed-operation.json", {"id": operation})
    original_health, injected = AppMaintenance.health, False

    def fail_once(self, review, payload, **kwargs):
        nonlocal injected
        if not injected:
            injected = True
            info = self.recovery_container(review, payload)
            assert info["Config"]["Labels"].get("io.stackarr.maintenance") == operation
            self.call(payload, "exec", "--user", "0:0", info["Id"], "/bin/sh", "-c",
                "printf 'Stackarr isolated repair interruption fixture' > /config/stackarr-repair-fault-marker.txt")
            assert self.call(payload, "exec", info["Id"], "cat", "/config/stackarr-repair-fault-marker.txt").strip() == "Stackarr isolated repair interruption fixture"
            write("candidate-write-" + operation + ".json", {"observed": True, "only_disposable_config_volume_changed": True})
            if crash:
                print("Exiting only this disposable test worker after confirmed candidate settings writes.", flush=True)
                os._exit(77)
            return False
        return original_health(self, review, payload, **kwargs)

    AppMaintenance.health = fail_once
    asyncio.run(service.actions.run_one())
    wait_action(operation, "failed-recovered")
    preserved()


def recover(package):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(STATE), "-NoBrowser"], capture_output=True, timeout=240)
    assert result.returncode == 0
    operation = read(OUTPUT / "interrupted-operation.json")["id"]
    assert read(OUTPUT / ("candidate-write-" + operation + ".json"))["observed"]
    with sqlite3.connect(STATE / "controller/state/stackarr.db") as db:
        assert db.execute("SELECT state FROM deployment_actions WHERE id=?", (operation,)).fetchone()[0] == "needs-recovery"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(180000)
        signin(page)
        browser_action(page, "repair-recover")
        browser.close()
    preserved()
    write("recovery-report.json", {"passed": True, "fresh_packaged_controller": True, "explicit_browser_recovery": True,
        "candidate_configuration_write_observed": True, "settings_login_and_media_recovered": True,
        "active_release": SelfUpdates(STATE).listing()["current"]})


def finalize():
    preserved()
    assert read(OUTPUT / "browser-report.json")["passed"] and read(OUTPUT / "recovery-report.json")["passed"]
    command(["compose", "--project-name", "stackarr-owned-" + CORE, "-f",
        str(STATE / "controller/state/deployments" / CORE / "compose.json"), "down"])
    command(["compose", "--project-name", PROJECT, "-f", str(STATE / "compose.json"), "down"])
    stop_lab_controller()
    main_preserved()
    assert hashes(LAB / "media") == read(OUTPUT / "lab-before.json")["media"]
    assert len(command(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + CORE]).splitlines()) >= 4
    write("report.json", {"passed": True, "browser": read(OUTPUT / "browser-report.json"), "interruption": read(OUTPUT / "recovery-report.json"),
        "failed_repair_recovered": True, "only_isolated_containers_and_networks_removed": True,
        "configuration_volumes_media_and_snapshots_retained": True, "main_apps_settings_credentials_media_preserved": True})


def main_controls(archive):
    assert read(OUTPUT / "report.json")["passed"]
    upgrade(archive, MAIN, "http://localhost:29100", MAIN)
    main_preserved(allow_dashboard=True)
    origin, checked = "http://localhost:29100", []
    with owner(origin, MAIN) as client:
        groups = client.get("/api/deployments").json()["operations"]
        for group in groups:
            if group["state"] != "needs-setup":
                continue
            response = client.post("/api/deployments/" + group["id"] + "/check", json={})
            response.raise_for_status()
            for app in response.json()["apps"]:
                assert {"repair", "remove"} <= set(app["actions"])
                reviewed = client.post(f"/api/deployments/{group['id']}/apps/{app['app']}/review", json={"action": "repair"})
                reviewed.raise_for_status()  # Review only. Never approve a main app action.
                checked.append(app["app"])
        assert len(checked) == 9
        stamp = time.time()
        client.post("/api/refresh", json={}).raise_for_status()
        for _ in range(120):
            fresh = client.get("/api/status").json()["integrations"]
            ready = {row["id"] for row in fresh if row["state"] == "ready" and not row["stale"] and (row["collected_at"] or 0) > stamp}
            if ready == set(checked):
                break
            time.sleep(.5)
        assert ready == set(checked)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(120000)
        page.goto(origin)
        page.get_by_label("Password", exact=True).fill(read(MAIN / "access.json")["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Apps", exact=True).click()
        for button in page.locator("[data-check-install]").all():
            button.click()
        expect(page.get_by_role("button", name="Review repair qBittorrent", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Review remove Plex", exact=True)).to_be_visible()
        page.screenshot(path=str(OUTPUT / "main-controls.png"), full_page=True)
        browser.close()
    main_preserved(allow_dashboard=True)
    write("main-verification.json", {"passed": True, "fresh_apps": sorted(checked), "all_nine_original_app_ids_preserved": True,
        "controller_and_dashboard_settings_credentials_preserved": True, "main_media_hashes_preserved": 16,
        "no_main_app_repair_removal_or_restore_approved": True, "only_stackarr_updated": True})


def accept(package):
    base = [sys.executable, "-m", "tools.docker_app_maintenance_check"]
    for phase in ("browser", "fault"):
        print("Final packaged acceptance: " + phase, flush=True)
        subprocess.run([*base, "--phase", phase], check=True)
    print("Final packaged acceptance: confirmed-write interruption", flush=True)
    stopped = subprocess.run([*base, "--phase", "crash"])
    assert stopped.returncode != 0
    identity = read(OUTPUT / "interrupted-operation.json")["id"]
    assert read(OUTPUT / ("candidate-write-" + identity + ".json"))["observed"]
    with sqlite3.connect(STATE / "controller/state/stackarr.db") as db:
        assert db.execute("SELECT state FROM deployment_actions WHERE id=?", (identity,)).fetchone()[0] == "running"
    subprocess.run([*base, "--phase", "recover", "--package", str(package)], check=True)
    subprocess.run([*base, "--phase", "finalize"], check=True)
    write("final-acceptance.json", {"passed": True, "release": read(package / "manifest.json")["release"],
        "frozen_browser_workflow": True, "actual_candidate_configuration_writes": True,
        "automatic_failed_repair_recovery": True, "fresh_packaged_interrupted_recovery": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=["prepare", "upgrade", "browser", "verify", "verify-absent", "fault", "crash", "recover", "finalize", "main", "accept"])
    parser.add_argument("--package", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.package.resolve())
    elif args.phase == "upgrade":
        upgrade(args.archive.resolve())
    elif args.phase == "browser":
        browser_flow()
    elif args.phase in {"verify", "verify-absent"}:
        preserved(args.phase == "verify-absent")
    elif args.phase in {"fault", "crash"}:
        fault(args.phase == "crash")
    elif args.phase == "recover":
        recover(args.package.resolve())
    elif args.phase == "finalize":
        finalize()
    elif args.phase == "main":
        main_controls(args.archive.resolve())
    elif args.phase == "accept":
        accept(args.package.resolve())


if __name__ == "__main__":
    main()
