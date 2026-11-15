"""Packaged schedule/retention/second-disk recovery acceptance in fixed Docker labs."""

import argparse
import json
import os
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.app_backups import AppBackups, digest
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.docker_runtime import executable
from stackarr.store import Store
from stackarr.updates import Updates
from tools.docker_update_fault_check import IDENTITY, ROOT, settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--main-preview", action="store_true", help="Back up all main apps; never restore or prune their media/settings")
    parser.add_argument("--finish-completed", action="store_true", help="Verify a completed lab recovery and finish schedule-disable/capture/cleanup without repeating it")
    args = parser.parse_args()
    assert not args.finish_completed or not args.main_preview
    package = args.package.resolve()
    root = Path("test-results/docker-plex-bc615eaf1fe6").resolve() if args.main_preview else ROOT.resolve()
    state = root if args.main_preview else root / "package-state"
    controller_root = state / "controller"
    controller_port = 29010 if args.main_preview else 29014
    origin = "http://localhost:29100" if args.main_preview else "http://localhost:29140"
    access = json.loads((root / "access.json").read_text())
    media = {path: digest(path) for path in (root / "media").rglob("*") if path.is_file()}
    if not args.main_preview and not args.finish_completed:
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", controller_port)) != 0, "Stop the disposable controller first."
    host = Deployments(Store(controller_root / "state"))
    plans = host.backup_plans
    destination = args.destination.resolve()
    assert str(destination) in {r"D:\Stackarr Backups", r"H:\Stackarr Backups"}, "Use a dedicated designated test destination."
    if not destination.exists():
        destination.mkdir()
    selected = plans.admit(destination)
    if not args.main_preview and not args.finish_completed:
        bootstrap = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
            str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(state), "-MediaFolder", str(root / "media"),
            "-Port", "29140", "-ControllerPort", "29014", "-NoBrowser"], capture_output=True, text=True, timeout=240,
            creationflags=subprocess.CREATE_NO_WINDOW)
        (root / "scheduled-backup-bootstrap.log").write_text(bootstrap.stdout + bootstrap.stderr)
        assert bootstrap.returncode == 0, "Packaged startup failed; private log retained."
    backups = AppBackups(host)
    saved_before = {row["id"] for row in backups.rows() if row["kind"] != "scheduled"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(60000)
        page.goto(origin)
        page.get_by_label("Password", exact=True).fill(access["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        expect(page.get_by_role("button", name="Apps", exact=True)).to_be_visible()
        csrf = page.request.get(origin + "/api/session").json()["csrf"]
        page.context.set_extra_http_headers({"Origin": origin, "X-CSRF-Token": csrf})

        def job(identity):
            for _ in range(1200):
                rows = page.request.get(origin + "/api/deployments").json().get("actions", [])
                row = next((row for row in rows if row["id"] == identity), None)
                if row and row["state"] not in {"queued", "running"}:
                    assert row["state"] == "succeeded", row["message"]
                    return
                time.sleep(.5)
            raise AssertionError("Backup job timed out")

        def health(payload, identity):
            updater = Updates(host)
            for key in payload["apps"]:
                image = updater.image(payload, payload["compose"]["services"][key]["image"])
                with ThreadPoolExecutor(max_workers=1) as pool:
                    assert pool.submit(updater.health, payload | {"identity": identity}, key, host.store.secret(key),
                        image["Config"]["Labels"].get("org.opencontainers.image.version", "")).result(timeout=210)

        def configure(at, enabled=True):
            page.get_by_role("button", name="Backups", exact=True).click()
            expect(page.get_by_role("button", name="Review backup plan", exact=True)).to_be_visible()
            page.get_by_label("Back up nightly", exact=True).set_checked(enabled)
            page.locator("#backup-time").fill(at)
            page.get_by_label("Scheduled copies per installation", exact=True).fill("7" if args.main_preview else "2")
            page.get_by_label("Backup storage", exact=True).select_option(selected["id"])
            page.get_by_role("button", name="Review backup plan", exact=True).click()
            expect(page.locator("#backup-plan-review-output")).to_contain_text("safety" if enabled else "Existing backups are retained", timeout=60000)
            page.get_by_role("button", name="Save backup plan", exact=True).click()
            expect(page.locator("#backup-plan-review-output")).to_be_empty(timeout=60000)

        installs = page.request.get(origin + "/api/deployments").json()["operations"]
        identities = [row["id"] for row in installs if row["state"] == "needs-setup"]
        if not args.main_preview:
            assert identities == [IDENTITY]
            payload = load_receipt(host, IDENTITY)
            for key in payload["apps"]:
                info = inspect_container(host, IDENTITY, payload, key)
                if not info["State"].get("Running"):
                    reviewed = page.request.post(origin + f"/api/deployments/{IDENTITY}/apps/{key}/review", data={"action": "start"})
                    assert reviewed.status == 200
                    queued = page.request.post(origin + "/api/deployments/actions/apply", data={"review_token": reviewed.json()["review_token"]})
                    assert queued.status == 202
                    job(queued.json()["id"])
            health(payload, IDENTITY)
            expected = settings(host, payload)
            container_ids = {key: inspect_container(host, IDENTITY, payload, key)["Id"] for key in payload["apps"]}
        else:
            assert len(identities) == 3
        dashboard_settings = page.request.get(origin + "/api/config").json()
        if args.finish_completed:
            updater = Updates(host)
            for key in payload["apps"]:
                run = updater.read(next(row["id"] for row in updater.listing()["history"] if row["app"] == key))
                with ThreadPoolExecutor(max_workers=1) as pool:
                    assert pool.submit(updater.protected, payload, key, run["secret"]).result(timeout=60) == run["protected"]
            with host.store.db() as db:
                completed = [(state, json.loads(value)["action"]) for state, value in db.execute("SELECT state,payload FROM deployment_actions ORDER BY created DESC")]
            relevant = [row for row in completed if row[1] in {"restore", "scheduled-backup"}][:4]
            assert relevant == [("succeeded", "restore"), *( ("succeeded", "scheduled-backup") for _ in range(3))]
            fixtures = {row["filename"]: row["sha256"] for row in json.loads((root / "seed-media" / "fixtures.json").read_text())}
            for path in media:
                if path.suffix == ".mkv":
                    assert digest(path) == fixtures[path.name]
            assert (root / "media" / "preserve.txt").read_text() == "Original test sentinel; keep unchanged."
            assert (root / "media" / "restore-preservation-sentinel.txt").read_text() == "Media created after snapshot must survive app restore."
        elif args.main_preview:
            configure("03:00")
        else:
            # Exercise the actual packaged wall-clock scheduler, not a test-only clock.
            now = datetime.now()
            target = now.replace(second=0, microsecond=0) + timedelta(minutes=2 if now.second > 45 else 1)
            configure(target.strftime("%H:%M"))
            due = page.request.get(origin + "/api/backup-policy").json()["policy"]["next_run"]
            print("Packaged nightly schedule saved; waiting for the real due minute.", flush=True)
            before_actions = {row["id"] for row in page.request.get(origin + "/api/deployments").json()["actions"]}
            for _ in range(180):
                rows = page.request.get(origin + "/api/deployments").json()["actions"]
                new = [row for row in rows if row["id"] not in before_actions and "backup" in row["message"].lower()]
                if new:
                    job(new[0]["id"])
                    break
                time.sleep(1)
            else:
                raise AssertionError("Real scheduled backup did not run at its due minute")
            assert time.time() >= due
            print("Real packaged scheduled backup completed.", flush=True)

        for _ in range(0 if args.finish_completed else 1 if args.main_preview else 2):
            with page.expect_response(lambda r: r.url.endswith("/backup-plan-run")) as response:
                page.get_by_role("button", name="Run backup plan now", exact=True).click()
            assert response.value.status == 200
            job(response.value.json()["id"])
            print("Packaged run-now backup completed.", flush=True)
        rows = backups.rows()
        scheduled = [row for row in rows if row["kind"] == "scheduled"]
        if not args.main_preview:
            assert len(scheduled) == 2
        else:
            assert {row["deployment"] for row in scheduled} == set(identities)
        assert saved_before <= {row["id"] for row in rows}
        for row in scheduled:
            plans.external(row["id"])
        print("Separate-disk copies verified; retained manual/safety snapshots confirmed.", flush=True)
        corruption_rejected = args.finish_completed
        if not args.main_preview and not args.finish_completed:
            snapshot = scheduled[0]["id"]
            location, manifest = plans.external(snapshot)
            backups_root = backups.root / snapshot
            plans.remove_files(backups_root, [*(key + ".enc" for key in manifest["manifest"]["apps"]), "controller.enc"])
            # Mutate one real database setting in every app after the scheduled snapshot.
            for key in payload["apps"]:
                secret = host.store.secret(key)
                port = payload["compose"]["services"][key]["ports"][0]["published"]
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=20) as client:
                    if key == "qbittorrent":
                        client.post("/api/v2/auth/login", data={"username": secret["username"], "password": secret["password"]}).raise_for_status()
                        client.post("/api/v2/app/setPreferences", data={"json": json.dumps({"max_connec": expected[key]["max_connec"] + 3})}).raise_for_status()
                    else:
                        client.headers["X-Api-Key"] = secret["api_key"]
                        api = "/api/v1" if key == "prowlarr" else "/api/v3"
                        value = expected[key]["ui"] | {"showRelativeDates": not expected[key]["ui"]["showRelativeDates"]}
                        client.put(api + "/config/ui", json=value).raise_for_status()
            assert settings(host, payload) != expected
            test_file = location / "prowlarr.enc"
            original = test_file.read_bytes()
            test_file.write_bytes(original[:-10])
            before_corrupt = settings(host, payload)
            try:
                backups.execute(backups.review(IDENTITY, snapshot))
                raise AssertionError("A corrupt second-disk copy was accepted")
            except ValueError:
                assert settings(host, payload) == before_corrupt
                assert all(inspect_container(host, IDENTITY, payload, key)["State"]["Running"] for key in payload["apps"])
                corruption_rejected = True
            finally:
                test_file.write_bytes(original)
            plans.external(snapshot)
            page.get_by_role("button", name="Refresh Docker backups", exact=True).click()
            page.locator('[data-docker-restore="' + snapshot + '"]').click()
            expect(page.locator("#lifecycle-review")).to_contain_text("safety backup")
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as response:
                page.get_by_role("button", name="Restore snapshot", exact=True).click()
            job(response.value.json()["id"])
            health(payload, IDENTITY)
            assert settings(host, payload) == expected
            assert {key: inspect_container(host, IDENTITY, payload, key)["Id"] for key in payload["apps"]} == container_ids
            assert any(row["kind"] == "before-restore" and row["off_disk"] for row in backups.rows())
            print("Browser restore recovered all four changed settings and logins using only the second-disk snapshot.", flush=True)
        if not args.main_preview:
            configure("03:00", enabled=False)
        stamp = time.time()
        page.request.post(origin + "/api/refresh")
        expected_apps = {"plex", "seerr", "sonarr", "radarr", "prowlarr", "qbittorrent"} if args.main_preview else set(payload["apps"])
        for _ in range(150):
            rows = page.request.get(origin + "/api/status").json()["integrations"]
            ready = {row["id"] for row in rows if row["state"] == "ready" and not row["stale"] and (row["collected_at"] or 0) > stamp}
            if ready == expected_apps:
                break
            time.sleep(.5)
        assert ready == expected_apps
        assert page.request.get(origin + "/api/config").json() == dashboard_settings
        for path, checksum in media.items():
            assert digest(path) == checksum
        page.get_by_role("button", name="Refresh backup plan", exact=True).click()
        page.screenshot(path=str(root / "scheduled-backup-results.png"), full_page=True)
        report = {"passed": True, "packaged_wall_clock_schedule": not args.main_preview, "browser_run_now": True,
                  "resumed_verification": args.finish_completed,
                  "separate_physical_disk": True, "destination": str(destination), "scheduled_retention": 7 if args.main_preview else 2,
                  "manual_safety_update_snapshots_preserved": True, "local_snapshot_missing_during_restore": not args.main_preview,
                  "corrupt_external_copy_rejected_before_downtime": corruption_rejected,
                  "settings_logins_libraries_recovered": not args.main_preview, "media_hashes_preserved": len(media),
                  "fresh_monitoring": sorted(ready), "main_data_never_restored": args.main_preview}
        (root / "scheduled-backup-report.json").write_text(json.dumps(report, indent=2))
        browser.close()
    if not args.main_preview:
        for key in payload["apps"]:
            host.actions.execute(host.actions.review(IDENTITY, key, "stop"))
        command = [executable(), "compose", "--project-name", "stackarr-preview-9e8929fdc74c", "-f", str(state / "compose.json")]
        subprocess.run([*command, "stop", "--timeout", "30", "stackarr"], check=True, capture_output=True, timeout=60)
        env = os.environ.copy()
        env["STACKARR_LAB_CONTROLLER_ROOT"] = str(controller_root)
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_LAB_CONTROLLER_ROOT) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"], env=env, check=True, capture_output=True, timeout=30)
        (root / "scheduled-backup-cleanup-report.json").write_text(json.dumps({"passed": True, "test_apps_dashboard_controller_stopped": True,
            "schedule_disabled": True, "volumes_media_backups_and_external_copies_retained": True}, indent=2))
    print("Packaged scheduled backup acceptance passed.", flush=True)


if __name__ == "__main__":
    main()
