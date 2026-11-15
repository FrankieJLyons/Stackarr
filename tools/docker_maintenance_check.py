"""Packaged recovery acceptance on two explicitly owned, local Docker preview labs."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.app_backups import AppBackups
from stackarr.arr_logins import read as read_arr_login
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.docker_runtime import executable
from stackarr.store import Store

CORE = "c6903afb2218471aa2a45be825f625e5"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--main-preview", action="store_true", help="Upgrade main preview and back up all six apps; never restore its data")
    parser.add_argument("--upgrade-only", action="store_true", help="Upgrade the main dashboard/controller, verify update controls and preserve app containers")
    args = parser.parse_args()
    assert not args.upgrade_only or args.main_preview
    package = args.package.resolve()
    lab = Path("test-results/docker-plex-bc615eaf1fe6" if args.main_preview else "test-results/docker-core-05cebfd84fd1").resolve()
    state = lab if args.main_preview else lab / "package-state"
    if args.upgrade_only:
        assert not (state / "stackarr-runtime.json").exists(), "Use reviewed self-update for an already managed Stackarr release"
    controller_root = state / "controller"
    origin = "http://localhost:29100" if args.main_preview else "http://localhost:29140"
    port = 29010 if args.main_preview else 29014
    project = "stackarr-plex-lab-bc615eaf1fe6" if args.main_preview else "stackarr-preview-9e8929fdc74c"
    access = json.loads((lab / "access.json").read_text())
    assert access["dashboard"] == origin
    manifest = json.loads((package / "manifest.json").read_text())
    exe = package / "StackarrPreview.exe"
    assert digest(exe) == manifest["files"][exe.name]
    media_before = {str(path.relative_to(lab / "media")): digest(path) for path in (lab / "media").rglob("*") if path.is_file()}
    docker = executable()

    def command(arguments, timeout=180):
        result = subprocess.run([docker, *arguments], capture_output=True, text=True, encoding="utf-8",
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Scoped Docker maintenance check failed; private output withheld.")
        return result.stdout.strip()

    before = set(command(["ps", "-q", "--no-trunc"]).splitlines())
    old_dashboard = command(["compose", "--project-name", project, "-f", str(state / "compose.json"), "ps", "-q", "stackarr"])
    command(["load", "--input", str(package / "stackarr-image.tar")])
    assert command(["image", "inspect", manifest["image"], "--format", "{{.Id}}"] ) == manifest["image_id"]
    env = os.environ.copy()
    env["STACKARR_LAB_CONTROLLER_ROOT"] = str(controller_root)
    stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_LAB_CONTROLLER_ROOT) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                             env=env, capture_output=True, timeout=30)
    assert stopped.returncode == 0
    env.update(STACKARR_PORT=origin.rsplit(":", 1)[1], STACKARR_CONTROLLER_PORT=str(port),
        STACKARR_PACKAGE_ROOT=str(package), PYINSTALLER_RESET_ENVIRONMENT="1", STACKARR_CONTROLLER_ROOTS=json.dumps([
        {"path": str(lab / "media"), "host_path": str(lab / "media"), "label": "Test media"}]))
    with (lab / "maintenance-controller.log").open("w") as log:
        process = subprocess.Popen([str(exe), "--controller-serve", str(controller_root), "--controller-port", str(port)],
                                   env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    access["controller_pid"] = process.pid
    (lab / "access.json").write_text(json.dumps(access))
    compose_path = state / "compose.json"
    compose = json.loads(compose_path.read_text(encoding="utf-8-sig"))
    assert set(compose["services"]) == {"stackarr"}
    compose["services"]["stackarr"]["image"] = manifest["image"]
    compose_path.write_text(json.dumps(compose, indent=2))
    base = ["compose", "--project-name", project, "-f", str(compose_path)]
    command([*base, "up", "-d", "--wait", "--wait-timeout", "120"])
    print("Packaged maintenance dashboard and controller running.", flush=True)

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
        for _ in range(60):
            status = page.request.get(origin + "/api/deployments").json()
            if status.get("controller") == "connected":
                break
            time.sleep(.5)
        assert status["controller"] == "connected"
        # Refresh the UI's initial snapshot if it overlapped controller startup.
        page.reload()
        expect(page.get_by_role("button", name="Apps", exact=True)).to_be_visible()
        identities = [row["id"] for row in status["operations"] if row["state"] == "needs-setup"]
        dashboard_settings = page.request.get(origin + "/api/config").json()
        if args.upgrade_only:
            expected_apps = {key for key, value in dashboard_settings["config"]["integrations"].items() if value["enabled"]}
            page.get_by_role("button", name="Apps", exact=True).click()
            page.get_by_role("button", name="Check packaged updates", exact=True).click()
            rows = page.request.get(origin + "/api/updates").json()
            assert {row["app"] for row in rows["apps"] if row["available"]} == {"sonarr", "radarr", "prowlarr", "qbittorrent"}
            stamp = time.time()
            page.request.post(origin + "/api/refresh")
            for _ in range(120):
                fresh = page.request.get(origin + "/api/status").json()["integrations"]
                ready = {row["id"] for row in fresh if row["state"] == "ready" and not row["stale"] and (row["collected_at"] or 0) > stamp}
                if ready == expected_apps:
                    break
                time.sleep(.5)
            assert ready == expected_apps
            assert page.request.get(origin + "/api/config").json() == dashboard_settings
            page.get_by_role("button", name="Settings", exact=True).click()
            page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
            expect(page.get_by_text("Current release: " + manifest["release"], exact=True)).to_be_visible()
            self_updates = page.request.get(origin + "/api/stackarr-updates").json()
            assert self_updates["current"] == manifest["release"] and not self_updates["history"]
            assert not self_updates["candidate"] and not self_updates["recover"]
            for name, checksum in media_before.items():
                assert digest(lab / "media" / name) == checksum
            after = set(command(["ps", "-q", "--no-trunc"]).splitlines())
            assert before - {old_dashboard} <= after
            page.screenshot(path=str(lab / "update-controls.png"), full_page=True)
            (lab / "update-main-preview-report.json").write_text(json.dumps({"passed": True, "image": manifest["image_id"],
                "update_controls_available": True, "stackarr_self_update_controls_available": True,
                "main_app_images_unchanged": True, "fresh_monitoring": sorted(ready),
                "settings_preserved": True, "media_hashes_preserved": len(media_before), "unrelated_containers_preserved": True}, indent=2))
            browser.close()
            print(f"Final packaged update controls available; all {len(ready)} main apps remain fresh and unchanged.")
            return
        assert len(identities) == (3 if args.main_preview else 1)
        if not args.main_preview:
            assert identities == [CORE]

        def wait_action(identity):
            for _ in range(300):
                rows = page.request.get(origin + "/api/deployments").json().get("actions", [])
                row = next((row for row in rows if row["id"] == identity), None)
                if row and row["state"] not in {"queued", "running"}:
                    assert row["state"] == "succeeded", row["message"]
                    return
                time.sleep(.5)
            raise AssertionError("Maintenance action timed out")

        def backup_rows():
            for _ in range(20):
                response = page.request.get(origin + "/api/app-backups")
                if response.status == 200:
                    return response.json()["backups"]
                assert response.status in {429, 503}
                time.sleep(.5)
            raise AssertionError("Read-only backup list was unavailable")

        def action(key, verb):
            reviewed = page.request.post(origin + f"/api/deployments/{CORE}/apps/{key}/review", data={"action": verb})
            assert reviewed.status == 200
            response = page.request.post(origin + "/api/deployments/actions/apply", data={"review_token": reviewed.json()["review_token"]})
            assert response.status == 202
            wait_action(response.json()["id"])

        if not args.main_preview:
            response = page.request.post(origin + f"/api/deployments/{CORE}/check")
            assert response.status == 200, response.json()
            checked = response.json()
            for app in checked["apps"]:
                if app["state"] == "stopped":
                    action(app["app"], "start")
            page.get_by_role("button", name="Apps", exact=True).click()
            page.locator("[data-check-install]").click()
            page.get_by_role("button", name="Review stop Prowlarr", exact=True).click()
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as applied:
                page.get_by_role("button", name="Stop app", exact=True).click()
            wait_action(applied.value.json()["id"])

            page.locator("[data-check-install]").click()
            page.get_by_role("button", name="Review start Prowlarr", exact=True).click()
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as applied:
                page.get_by_role("button", name="Start app", exact=True).click()
            wait_action(applied.value.json()["id"])
            page.locator("[data-check-install]").click()
            page.get_by_role("button", name="Review restart Prowlarr", exact=True).click()
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as applied:
                page.get_by_role("button", name="Restart app", exact=True).click()
            wait_action(applied.value.json()["id"])

            print("Browser start/stop/restart controls passed.", flush=True)

        # Verify app API credentials/settings before mutation and compare after restore.
        host = Deployments(Store(controller_root / "state"))
        private = {}
        clients = {}
        libraries = {}
        if not args.main_preview:
            payload = load_receipt(host, CORE)
            container_ids = {key: inspect_container(host, CORE, payload, key)["Id"] for key in payload["apps"]}
            for key in payload["apps"]:
                port_value = payload["compose"]["services"][key]["ports"][0]["published"]
                clients[key] = httpx.Client(base_url=f"http://localhost:{port_value}", trust_env=False, timeout=20)
                credential = host.store.secret(key)
                if key == "qbittorrent":
                    for _ in range(60):
                        try:
                            result = clients[key].post("/api/v2/auth/login", data={"username": credential["username"], "password": credential["password"]})
                            if result.status_code in {200, 204} and (result.text == "Ok." or result.status_code == 204):
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.5)
                    assert result.status_code in {200, 204} and clients[key].cookies
                    private[key] = clients[key].get("/api/v2/app/preferences").json()
                else:
                    clients[key].headers["X-Api-Key"] = credential["api_key"]
                    for _ in range(120):
                        try:
                            result = clients[key].get("/api/v3/config/ui" if key != "prowlarr" else "/api/v1/config/ui")
                            if result.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.5)
                    assert result.status_code == 200
                    private[key] = result.json()
                    assert read_arr_login(host, CORE, payload, key, credential["api_key"])
                    if key in {"sonarr", "radarr"}:
                        path = "/api/v3/series" if key == "sonarr" else "/api/v3/movie"
                        libraries[key] = [(item["id"], item.get("tvdbId"), item.get("tmdbId"), item["path"])
                                          for item in clients[key].get(path).json()]

        print("Authenticated app settings captured; reviewing encrypted backup.", flush=True)
        page.get_by_role("button", name="Backups", exact=True).click()
        for identity in identities:
            page.locator(f'[data-docker-backup="{identity}"]').click()
            expect(page.locator("#lifecycle-review")).to_contain_text("encrypted")
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as applied:
                page.get_by_role("button", name="Create backup", exact=True).click()
            wait_action(applied.value.json()["id"])
            print("Encrypted app configuration snapshot passed.", flush=True)
        page.get_by_role("button", name="Refresh Docker backups", exact=True).click()
        backups = backup_rows()
        assert set(identities) <= {row["deployment"] for row in backups}
        if args.main_preview:
            backup_service = AppBackups(host)
            with tempfile.TemporaryDirectory(prefix="verify-", dir=backup_service.root) as temporary:
                for identity in identities:
                    stage = Path(temporary) / identity
                    stage.mkdir()
                    backup_service.materialize(next(row["id"] for row in backups if row["deployment"] == identity), stage)
            print("All six encrypted archives decrypted and validated without restoring main data.", flush=True)
        if not args.main_preview:
            snapshot = next(row["id"] for row in backups if row["deployment"] == CORE and row["kind"] == "manual")
            new_media = lab / "media" / "restore-preservation-sentinel.txt"
            new_media.write_text("Media created after snapshot must survive app restore.")
            for key, client in clients.items():
                # Backup restarted the app; qBittorrent's previous session is intentionally invalid.
                for _ in range(120):
                    try:
                        if key == "qbittorrent":
                            credential = host.store.secret(key)
                            client.post("/api/v2/auth/login", data={"username": credential["username"], "password": credential["password"]})
                            ready = client.get("/api/v2/app/preferences")
                        else:
                            ready = client.get("/api/v1/config/ui" if key == "prowlarr" else "/api/v3/config/ui")
                        if ready.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.5)
                assert ready.status_code == 200
                if key == "qbittorrent":
                    response = client.post("/api/v2/app/setPreferences", data={"json": json.dumps({"max_connec": private[key]["max_connec"] + 1})})
                    response.raise_for_status()
                    assert client.get("/api/v2/app/preferences").json()["max_connec"] != private[key]["max_connec"]
                else:
                    path = "/api/v1/config/ui" if key == "prowlarr" else "/api/v3/config/ui"
                    changed = private[key] | {"showRelativeDates": not private[key]["showRelativeDates"]}
                    response = client.put(path, json=changed)
                    response.raise_for_status()
                    assert client.get(path).json()["showRelativeDates"] != private[key]["showRelativeDates"]
            page.locator(f'[data-docker-restore="{snapshot}"]').click()
            expect(page.locator("#lifecycle-review")).to_contain_text("safety backup")
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as applied:
                page.get_by_role("button", name="Restore snapshot", exact=True).click()
            wait_action(applied.value.json()["id"])
            for key, client in clients.items():
                for _ in range(120):
                    try:
                        if key == "qbittorrent":
                            credential = host.store.secret(key)
                            client.post("/api/v2/auth/login", data={"username": credential["username"], "password": credential["password"]})
                            current = client.get("/api/v2/app/preferences").json()
                            assert current["max_connec"] == private[key]["max_connec"]
                        else:
                            current = client.get("/api/v1/config/ui" if key == "prowlarr" else "/api/v3/config/ui").json()
                            assert current == private[key]
                        break
                    except (httpx.HTTPError, ValueError, AssertionError):
                        time.sleep(.5)
                else:
                    raise AssertionError("Restored app settings or credentials did not match")
                assert inspect_container(host, CORE, payload, key)["Id"] == container_ids[key]
                if key != "qbittorrent":
                    assert read_arr_login(host, CORE, payload, key, host.store.secret(key)["api_key"])
                if key in libraries:
                    path = "/api/v3/series" if key == "sonarr" else "/api/v3/movie"
                    assert [(item["id"], item.get("tvdbId"), item.get("tmdbId"), item["path"])
                            for item in client.get(path).json()] == libraries[key]
            assert new_media.read_text() == "Media created after snapshot must survive app restore."
            assert any(row["kind"] == "before-restore" for row in backup_rows())
            print("Browser restore recovered all four app settings and logins; container identities and media preserved.", flush=True)

        stamp = time.time()
        page.request.post(origin + "/api/refresh")
        expected = {"plex", "seerr", "sonarr", "radarr", "prowlarr", "qbittorrent"} if args.main_preview else {"sonarr", "radarr", "prowlarr", "qbittorrent"}
        for _ in range(120):
            rows = page.request.get(origin + "/api/status").json()["integrations"]
            ready = {row["id"] for row in rows if row["state"] == "ready" and not row["stale"] and (row["collected_at"] or 0) > stamp}
            if ready == expected:
                break
            time.sleep(.5)
        assert ready == expected
        assert page.request.get(origin + "/api/config").json() == dashboard_settings
        page.get_by_role("button", name="Refresh Docker backups", exact=True).click()
        page.screenshot(path=str(lab / "maintenance-backups.png"), full_page=True)
        page.get_by_role("button", name="Apps", exact=True).click()
        for button in page.locator("[data-check-install]").all():
            button.click()
        page.locator("#lifecycle-history").screenshot(path=str(lab / "maintenance-results.png"))
        for name, expected_hash in media_before.items():
            assert digest(lab / "media" / name) == expected_hash
        after = set(command(["ps", "-q", "--no-trunc"]).splitlines())
        assert before - {old_dashboard} <= after
        report = {"passed": True, "image": manifest["image_id"], "browser_backup": True,
                  "app_backups": sorted(expected), "browser_restore": not args.main_preview,
                  "media_hashes_preserved": len(media_before), "fresh_monitoring": sorted(ready),
                  "unrelated_containers_preserved": True,
                  "app_settings_and_credentials_restored": not args.main_preview}
        (lab / "maintenance-report.json").write_text(json.dumps(report, indent=2))
        browser.close()
    if not args.main_preview:
        # Return this disposable lab to its original stopped state, retaining all volumes/media.
        for key in payload["apps"]:
            host.actions.execute(host.actions.review(CORE, key, "stop"))
        dashboard = command([*base, "ps", "-q", "stackarr"])
        record = json.loads(command(["inspect", dashboard]))[0]
        assert record["Config"]["Labels"]["com.docker.compose.project"] == project
        command(["stop", "--timeout", "30", dashboard])
        stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_LAB_CONTROLLER_ROOT) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                                 env=env, capture_output=True, timeout=30)
        assert stopped.returncode == 0
        (lab / "maintenance-cleanup-report.json").write_text(json.dumps({"passed": True,
            "owned_test_apps_stopped": 4, "dashboard_stopped": True, "controller_stopped": True,
            "volumes_and_media_preserved": True}, indent=2))
    print("Packaged Docker maintenance acceptance passed.")


if __name__ == "__main__":
    main()
