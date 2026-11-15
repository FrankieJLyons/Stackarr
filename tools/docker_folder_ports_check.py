"""Packaged Docker setup with occupied ports and approved Unicode media storage."""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
import uuid
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.docker_runtime import executable
from stackarr.store import Store

MAIN = Path("test-results/docker-plex-bc615eaf1fe6").resolve()
APPS = {"sonarr", "radarr", "qbittorrent"}


def command(arguments, timeout=180):
    result = subprocess.run([executable(), *arguments], capture_output=True, text=True, encoding="utf-8",
        timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError("Scoped Docker setup check failed; private output withheld.")
    return result.stdout.strip()


def hashes(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def main_settings():
    store = Store(MAIN / "controller/state")
    config = store.config()[1]
    return {key: {"settings": app.model_dump(), "credential_hash": hashlib.sha256(json.dumps(
        store.secret(key), sort_keys=True).encode()).hexdigest()} for key, app in config.integrations.items()}


def listener(stack, port):
    probe = socket.socket()
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    probe.bind(("127.0.0.1", port))
    probe.listen()
    stack.callback(probe.close)
    return probe


def free_listener(stack, start):
    for port in range(start, start + 100):
        try:
            return listener(stack, port)
        except OSError:
            continue
    raise AssertionError("No free test-listener port")


def bootstrap(package, root, port, controller_port, media=None):
    state = root / "package-state"
    args = ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(state), "-Port", str(port),
        "-ControllerPort", str(controller_port), "-NoBrowser"]
    if media:
        args.extend(["-MediaFolder", str(media)])
    result = subprocess.run(args, capture_output=True, text=True, timeout=240,
        creationflags=subprocess.CREATE_NO_WINDOW)
    (root / ("bootstrap-" + uuid.uuid4().hex[:8] + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, "Packaged startup failed; see the scoped bootstrap log."
    installation = json.loads((state / "installation.json").read_text(encoding="utf-8-sig"))
    return installation, "http://localhost:" + str(installation["port"])


def stop_lab(root, installation, identities):
    state = root / "package-state"
    for identity in identities:
        command(["compose", "--project-name", "stackarr-owned-" + identity, "-f",
            str(state / "controller/state/deployments" / identity / "compose.json"), "stop"])
    command(["compose", "--project-name", installation["project"], "-f", str(state / "compose.json"), "stop"])
    env = os.environ | {"STACKARR_TEST_CONTROLLER_ROOT": str(state / "controller")}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        # A frozen one-file executable has a bootloader and a child process.
        # Stopping only the recorded bootloader PID can leave its server alive.
        "$taskWorkers=@(Get-CimInstance Win32_Process -Filter \"Name = 'StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_TEST_CONTROLLER_ROOT) -and $_.CommandLine.Contains('--controller-serve') }); foreach ($taskWorker in $taskWorkers) { Stop-Process -Id $taskWorker.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0


def run(package):
    root = (Path("test-results") / ("docker-folder-ports-" + uuid.uuid4().hex[:12])).resolve()
    root.mkdir()
    media = root / "Media with spaces – 电影"
    media.mkdir()
    (media / "preserve original.txt").write_text("Original isolated media sentinel; never move or replace.", encoding="utf-8")
    initial_media = hashes(media)
    baseline = {"media": hashes(MAIN / "media"), "settings": main_settings(),
                "running": command(["ps", "-q", "--no-trunc"]).splitlines()}
    (root / "before.json").write_text(json.dumps(baseline, indent=2))
    print("Packaged folder/port test lab: " + str(root), flush=True)
    all_listeners, installed_ids = [], []
    with ExitStack() as stack:
        dashboard_blocker, controller_blocker = free_listener(stack, 29160), free_listener(stack, 29016)
        all_listeners.extend([dashboard_blocker, controller_blocker])
        requested_port, requested_controller = dashboard_blocker.getsockname()[1], controller_blocker.getsockname()[1]
        for port in (8080, 8989, 7878):
            try:
                all_listeners.append(listener(stack, port))
            except OSError:
                pass  # An existing service is already a real conflict; never contact or stop it.
        installation, origin = bootstrap(package, root, requested_port, requested_controller, media)
        assert installation["port"] != requested_port and installation["controller_port"] != requested_controller
        state = root / "package-state"
        base = ["compose", "--project-name", installation["project"], "-f", str(state / "compose.json")]
        invitation = command([*base, "exec", "-T", "stackarr", "stackarr", "setup-link"])
        password = secrets.token_urlsafe(24)
        (root / "access.json").write_text(json.dumps({"dashboard": origin, "owner_password": password}))
        print("Busy dashboard and private ports were avoided; starting the browser journey.", flush=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(120000)
            page.goto(invitation)
            page.get_by_label("Create a password", exact=True).fill(password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            expect(page.get_by_label("Choose available ports for me (recommended)")).to_be_checked()
            assert page.locator("#setup-ports-advanced").get_attribute("open") is None
            for key in APPS:
                page.locator("#setup-" + key).check()
            page.get_by_role("button", name="Save & continue", exact=False).click()
            expect(page.get_by_role("heading", name="Where will your media live?", exact=True)).to_be_visible()
            expect(page.locator("#setup-selected-folder")).to_have_text(media.name)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(root / "media-folder-phone.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1100})
            page.screenshot(path=str(root / "media-folder.png"), full_page=True)
            csrf = page.request.get(origin + "/api/session").json()["csrf"]
            page.context.set_extra_http_headers({"Origin": origin, "X-CSRF-Token": csrf})

            def api(path, value=None, expected=200):
                result = page.request.get(origin + "/api/" + path) if value is None else page.request.post(origin + "/api/" + path, data=value)
                assert result.status == expected, "Scoped API check failed: " + path + "/" + str(result.status)
                return result.json()

            def wait_install(identity):
                for _ in range(360):
                    row = next((row for row in api("deployments")["operations"] if row["id"] == identity), None)
                    if row and row["state"] not in {"queued", "running"}:
                        return row
                    time.sleep(1)
                raise AssertionError("Packaged installation did not complete")

            def review():
                with page.expect_response(lambda response: response.url.endswith("/api/deployments/review")) as result:
                    page.get_by_role("button", name="Review installation", exact=True).click()
                assert result.value.ok
                return {row["id"]: int(row["port"]) for row in result.value.json()["apps"]}

            def approve(expected=202):
                with page.expect_response(lambda response: response.url.endswith("/api/deployments/install")) as result:
                    page.get_by_role("button", name="Download & install these apps", exact=True).click()
                assert result.value.status == expected
                return result.value.json()

            draft = api("onboarding")["draft"]
            assert draft["port_mode"] == "automatic"
            assert all(draft["choices"][key]["port"] != port for key, port in (("sonarr", 8989), ("radarr", 7878), ("qbittorrent", 8080)))
            # Only the UI cancellation response is simulated; root permission/consent is contract-tested separately.
            page.route("**/api/onboarding/choose-folder", lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"cancelled":true}'))
            page.get_by_role("button", name="Choose another folder…", exact=True).click()
            expect(page.locator("#setup-host-result")).to_contain_text("previous folder is unchanged")
            expect(page.locator("#setup-selected-folder")).to_have_text(media.name)
            page.unroute("**/api/onboarding/choose-folder")
            page.get_by_role("button", name="Save & continue", exact=False).click()
            expected_folder = api("onboarding")["draft"]
            assert expected_folder["data_root"] == str(media) and expected_folder["folder_root"] == 0
            selected = review()
            late = listener(stack, selected["sonarr"])
            all_listeners.append(late)
            approve(expected=409)
            expect(page.get_by_role("button", name="Use available ports", exact=True)).to_be_visible()
            assert not api("deployments")["operations"]
            page.screenshot(path=str(root / "conflict-after-review.png"), full_page=True)
            page.get_by_role("button", name="Use available ports", exact=True).click()
            expect(page.get_by_role("heading", name="App addresses ready", exact=True)).to_be_visible()
            repaired = review()
            assert repaired["sonarr"] != selected["sonarr"] and repaired["radarr"] == selected["radarr"]
            assert api("onboarding")["draft"]["data_root"] == str(media)
            queued = approve()["id"]
            during_pull = listener(stack, repaired["radarr"])
            all_listeners.append(during_pull)
            blocked = wait_install(queued)
            assert blocked["state"] == "ports-blocked", blocked["message"]
            assert not command(["ps", "-a", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + queued])
            assert not command(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + queued])
            assert hashes(media) == initial_media
            page.get_by_role("button", name="Check progress", exact=True).click()
            expect(page.get_by_role("button", name="Use available ports", exact=True)).to_be_visible()
            page.screenshot(path=str(root / "conflict-during-download.png"), full_page=True)
            page.get_by_role("button", name="Use available ports", exact=True).click()
            final = review()
            assert final["radarr"] != repaired["radarr"]
            identity = approve()["id"]
            installed_ids.append(identity)
            completed = wait_install(identity)
            assert completed["state"] == "needs-setup", completed["message"]
            assert next(row for row in api("deployments")["operations"] if row["id"] == queued)["state"] == "superseded"
            print("Both late-conflict paths recovered with fresh review; three real Docker apps are running.", flush=True)
            page.get_by_role("button", name="Check progress", exact=True).click()
            with page.expect_response(lambda response: response.url.endswith("/finish-connecting")) as result:
                page.locator('[data-finish-install="' + identity + '"]').click()
            assert result.value.ok and {row["state"] for row in result.value.json()["apps"]} == {"connected"}
            expect(page.get_by_text("Connected to Stackarr. Connection details were saved privately.", exact=False).first).to_be_visible(timeout=120000)
            print("Private handoff completed for the three apps.", flush=True)
            page.get_by_role("button", name="Open connection settings", exact=True).click()
            page.get_by_role("button", name="Preview app connections", exact=True).click()
            expect(page.get_by_role("button", name="Apply reviewed connections", exact=True)).to_be_visible()
            with page.expect_response(lambda response: response.url.endswith("/api/wiring/apply")) as result:
                page.get_by_role("button", name="Apply reviewed connections", exact=True).click()
            assert result.value.ok and len(result.value.json()["results"]) == 2
            api("refresh", {}, expected=202)
            for _ in range(90):
                statuses = api("status")["integrations"]
                if {row["id"] for row in statuses if row["state"] == "ready" and not row["stale"]} == APPS:
                    break
                time.sleep(1)
            assert {row["id"] for row in statuses if row["state"] == "ready" and not row["stale"]} == APPS
            for row in statuses:
                assert row["url"].rstrip("/") == "http://localhost:" + str(final[row["id"]])
            page.get_by_role("button", name="Overview", exact=True).click()
            expect(page.get_by_role("heading", name="Connected. Collected. Ready.", exact=True)).to_be_visible()
            page.screenshot(path=str(root / "three-apps-connected.png"), full_page=True)
            current_ids = command(["ps", "-q", "--no-trunc", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity])
            reopened, reopened_origin = bootstrap(package, root, requested_port + 20, requested_controller + 20)
            assert reopened == installation and reopened_origin == origin
            assert command(["ps", "-q", "--no-trunc", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity]) == current_ids
            assert all(hashes(media)[name] == value for name, value in initial_media.items())
            browser.close()
        stop_lab(root, installation, installed_ids)
        print("Media setup, actual app connections and saved-address reopen passed.", flush=True)
        monitoring = root / "monitoring-only"
        monitoring.mkdir()
        monitor_install, monitor_origin = bootstrap(package, monitoring, 29175, 29025)
        state = monitoring / "package-state"
        base = ["compose", "--project-name", monitor_install["project"], "-f", str(state / "compose.json")]
        invitation = command([*base, "exec", "-T", "stackarr", "stackarr", "setup-link"])
        monitor_password = secrets.token_urlsafe(24)
        (monitoring / "access.json").write_text(json.dumps({"dashboard": monitor_origin, "owner_password": monitor_password}))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(120000)
            page.goto(invitation)
            page.get_by_label("Create a password", exact=True).fill(monitor_password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            page.get_by_role("button", name="Monitoring only", exact=True).click()
            page.get_by_role("button", name="Save & continue", exact=False).click()
            expect(page.get_by_role("heading", name="No media folder needed", exact=True)).to_be_visible()
            assert page.get_by_role("button", name="Choose a folder…", exact=True).count() == 0
            page.get_by_role("button", name="Save & continue", exact=False).click()
            page.get_by_role("button", name="Review installation", exact=True).click()
            with page.expect_response(lambda response: response.url.endswith("/api/deployments/install")) as result:
                page.get_by_role("button", name="Download & install these apps", exact=True).click()
            monitor_id = result.value.json()["id"]
            for _ in range(180):
                rows = page.request.get(monitor_origin + "/api/deployments").json()["operations"]
                if rows and rows[0]["state"] not in {"queued", "running"}:
                    break
                time.sleep(1)
            assert rows[0]["state"] == "needs-setup"
            page.get_by_role("button", name="Check progress", exact=True).click()
            page.get_by_role("button", name="Review companion setup", exact=True).click()
            expect(page.get_by_role("button", name="Set up companions", exact=True)).to_be_visible(timeout=120000)
            page.get_by_role("button", name="Set up companions", exact=True).click()
            for _ in range(180):
                actions = page.request.get(monitor_origin + "/api/deployments").json().get("actions", [])
                if actions and actions[0]["state"] not in {"queued", "running"}:
                    break
                time.sleep(1)
            assert actions[0]["state"] == "succeeded", actions[0]["message"]
            page.get_by_role("button", name="Check progress", exact=True).click()
            page.locator('[data-finish-install="' + monitor_id + '"]').click()
            expect(page.get_by_text("Connected to Stackarr. Connection details were saved privately.", exact=False).first).to_be_visible(timeout=120000)
            page.get_by_role("button", name="Open Home →", exact=True).click()
            expect(page.get_by_role("heading", name="Connected. Collected. Ready.", exact=True)).to_be_visible(timeout=60000)
            page.screenshot(path=str(root / "monitoring-without-media-folder.png"), full_page=True)
            browser.close()
        monitor_store = Store(state / "controller/state")
        with monitor_store.db() as db:
            assert db.execute("SELECT count(*) FROM controller_media_roots").fetchone()[0] == 0
        stop_lab(monitoring, monitor_install, [monitor_id])
        for probe in all_listeners:
            probe.settimeout(.01)
            try:
                unexpected, _ = probe.accept()
            except TimeoutError:
                continue
            unexpected.close()
            raise AssertionError("Port checks contacted an unrelated listener")
    assert hashes(MAIN / "media") == baseline["media"] and main_settings() == baseline["settings"]
    assert set(baseline["running"]) <= set(command(["ps", "-q", "--no-trunc"]).splitlines())
    manifest = json.loads((package / "manifest.json").read_text())
    report = {"passed": True, "image": manifest["image_id"], "packaged_startup_without_python": True,
        "occupied_dashboard_and_controller_ports_avoided": True, "automatic_app_ports": final,
        "duplicate_and_reserved_port_contracts": True, "late_review_conflict_recovered": True,
        "during_pull_conflict_recovered_before_app_or_media_creation": True, "media_folder_reused_without_reselection": True,
        "folder_path_spaces_and_unicode": True, "cancel_keeps_previous_folder": "browser response fixture; host grant contract separately tested",
        "actual_three_app_connections": True, "monitoring_only_needs_no_media_folder": True,
        "saved_addresses_and_app_ids_preserved_on_reopen": True, "unrelated_listeners_contacted": 0,
        "main_apps_settings_and_credentials_preserved": True, "main_media_hashes_preserved": len(baseline["media"]),
        "test_containers_stopped_configuration_retained": True,
        "limitations": "Native Windows folder-dialog interaction and novice-recipient usability still need a human walkthrough."}
    (root / "report.json").write_text(json.dumps(report, indent=2))
    print("Packaged folder/port recovery passed; evidence: " + str(root / "report.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    run(parser.parse_args().package.resolve())
