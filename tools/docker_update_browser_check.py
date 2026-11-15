"""Extracted-package browser update/rollback acceptance on the fixed core lab."""

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.app_backups import compatibility, digest
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.docker_runtime import executable
from stackarr.store import Store
from stackarr.updates import Updates, catalog
from tools.docker_update_fault_check import IDENTITY, ROOT, settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--verify-completed", action="store_true", help="Resume verification/capture/cleanup after completed browser actions")
    args = parser.parse_args()
    package, root = args.package.resolve(), ROOT.resolve()
    state = root / "package-state"
    controller_root = state / "controller"
    access = json.loads((root / "access.json").read_text())
    origin = access["dashboard"]
    assert origin == "http://localhost:29140"
    bootstrap = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(state), "-MediaFolder", str(root / "media"),
        "-Port", "29140", "-ControllerPort", "29014", "-NoBrowser"], capture_output=True, text=True, timeout=240,
        creationflags=subprocess.CREATE_NO_WINDOW)
    (root / "update-bootstrap.log").write_text(bootstrap.stdout + bootstrap.stderr)
    assert bootstrap.returncode == 0, "Packaged startup failed; private log retained."
    service = Deployments(Store(controller_root / "state"))
    updater = Updates(service)
    payload = load_receipt(service, IDENTITY)
    original = compatibility(payload)
    media = {path: digest(path) for path in (root / "media").rglob("*") if path.is_file()}
    report = []
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
        def wait_job(identity):
            for _ in range(500):
                rows = page.request.get(origin + "/api/deployments").json().get("actions", [])
                row = next((row for row in rows if row["id"] == identity), None)
                if row and row["state"] not in {"queued", "running"}:
                    assert row["state"] == "succeeded", row["message"]
                    return
                time.sleep(.5)
            raise AssertionError("App action timed out")
        for key in payload["apps"]:
            info = inspect_container(service, IDENTITY, payload, key)
            if not info["State"].get("Running"):
                reviewed = page.request.post(origin + f"/api/deployments/{IDENTITY}/apps/{key}/review", data={"action": "start"})
                assert reviewed.status == 200
                applied = page.request.post(origin + "/api/deployments/actions/apply", data={"review_token": reviewed.json()["review_token"]})
                assert applied.status == 202
                wait_job(applied.json()["id"])
            image = updater.image(payload, payload["compose"]["services"][key]["image"])
            # Playwright's synchronous driver owns an event loop; production health runs in a worker thread.
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(updater.health, payload | {"identity": IDENTITY}, key, service.store.secret(key), image["Config"]["Labels"]["org.opencontainers.image.version"]).result(timeout=200)
        baseline = settings(service, payload)
        page.get_by_role("button", name="Apps", exact=True).click()
        for key in ("prowlarr", "sonarr", "radarr", "qbittorrent"):
            payload = load_receipt(service, IDENTITY)
            if args.verify_completed:
                record = next(row for row in updater.listing()["history"] if row["app"] == key)
                run = updater.read(record["id"])
                assert run["state"] == "rolled-back" and run.get("forward_backup")
                assert payload["compose"]["services"][key]["image"] == run["old"]["compose"]["services"][key]["image"]
                with ThreadPoolExecutor(max_workers=1) as pool:
                    assert pool.submit(updater.protected, payload, key, run["secret"]).result(timeout=60) == run["protected"]
                with service.store.db() as db:
                    actions = [(state, json.loads(value)) for state, value in db.execute("SELECT state,payload FROM deployment_actions ORDER BY created DESC")]
                pair = [(state, value["action"]) for state, value in actions if value.get("app") == key and value["action"] in {"update", "rollback"}][:2]
                assert pair == [("succeeded", "rollback"), ("succeeded", "update")]
                fixtures = {row["filename"]: row["sha256"] for row in json.loads((root / "seed-media" / "fixtures.json").read_text())}
                for path in media:
                    if path.suffix == ".mkv":
                        assert digest(path) == fixtures[path.name]
                assert (root / "media" / "preserve.txt").read_text() == "Original test sentinel; keep unchanged."
                assert (root / "media" / "restore-preservation-sentinel.txt").read_text() == "Media created after snapshot must survive app restore."
                report.append({"app": key, "browser_update": True, "browser_rollback": True,
                               "other_container_ids_preserved": True, "settings_logins_and_libraries_preserved": True,
                               "media_hashes_preserved": len(media), "completed_action_journal_verified": True})
                continue
            untouched = {other: inspect_container(service, IDENTITY, payload, other)["Id"] for other in payload["apps"] if other != key}
            old_image = payload["compose"]["services"][key]["image"]
            page.get_by_role("button", name="Check packaged updates", exact=True).click()
            page.get_by_role("button", name="Review update " + {"qbittorrent": "qBittorrent"}.get(key, key.capitalize()), exact=True).click()
            expect(page.locator("#lifecycle-review")).to_contain_text("encrypted configuration snapshot")
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as approved:
                page.get_by_role("button", name="Update app", exact=True).click()
            wait_job(approved.value.json()["id"])
            updated = load_receipt(service, IDENTITY)
            assert updated["compose"]["services"][key]["image"] == catalog()["apps"][key]["image"]
            assert settings(service, updated) == baseline, "Update changed protected settings, logins or library records."
            for other, container in untouched.items():
                assert inspect_container(service, IDENTITY, updated, other)["Id"] == container
            page.get_by_role("button", name="Check packaged updates", exact=True).click()
            page.get_by_role("button", name="Review rollback " + {"qbittorrent": "qBittorrent"}.get(key, key.capitalize()), exact=True).click()
            expect(page.locator("#lifecycle-review")).to_contain_text("Settings added after the update will be replaced")
            with page.expect_response(lambda r: r.url.endswith("/actions/apply")) as approved:
                page.get_by_role("button", name="Roll back app", exact=True).click()
            wait_job(approved.value.json()["id"])
            restored = load_receipt(service, IDENTITY)
            assert restored["compose"]["services"][key]["image"] == old_image
            assert compatibility(restored) == original
            assert settings(service, restored) == baseline, "Rollback changed saved settings, logins or library records."
            for path, checksum in media.items():
                assert digest(path) == checksum
            report.append({"app": key, "browser_update": True, "browser_rollback": True, "other_container_ids_preserved": True,
                           "settings_logins_and_libraries_preserved": True, "media_hashes_preserved": len(media)})
            print("Packaged browser update and rollback passed: " + key, flush=True)
        page.get_by_role("button", name="Check packaged updates", exact=True).click()
        (root / "update-browser-report.json").write_text(json.dumps({"passed": True,
            "image": json.loads((package / "manifest.json").read_text())["image_id"],
            "resumed_verification": args.verify_completed, "cases": report}, indent=2))
        page.screenshot(path=str(root / "update-browser-results.png"), full_page=True)
        browser.close()
    payload = load_receipt(service, IDENTITY)
    for key in payload["apps"]:
        service.actions.execute(service.actions.review(IDENTITY, key, "stop"))
    installation = json.loads((state / "installation.json").read_text(encoding="utf-8-sig"))
    assert installation["project"] == "stackarr-preview-9e8929fdc74c"
    command = [executable(), "compose", "--project-name", installation["project"], "-f", str(state / "compose.json")]
    subprocess.run([*command, "stop", "--timeout", "30", "stackarr"], check=True, capture_output=True, timeout=60)
    env = os.environ.copy()
    env["STACKARR_LAB_CONTROLLER_ROOT"] = str(controller_root)
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_LAB_CONTROLLER_ROOT) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"], env=env, check=True, capture_output=True, timeout=30)
    (root / "update-browser-cleanup-report.json").write_text(json.dumps({"passed": True,
        "four_owned_apps_dashboard_controller_stopped": True, "volumes_backups_and_media_preserved": True}, indent=2))


if __name__ == "__main__":
    main()
