"""Fresh four-app browser acceptance from an extracted Docker preview ZIP."""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.docker_runtime import executable
from tools.docker_core_check import VERIFY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--keep-running", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    root = (Path("test-results") / ("docker-core-" + uuid.uuid4().hex[:12])).resolve()
    root.mkdir()
    print("Fresh test lab: " + str(root), flush=True)
    media = root / "media"
    media.mkdir()
    sentinel = media / "preserve.txt"
    sentinel.write_text("Original test sentinel; keep unchanged.")
    sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    ports = {"qbittorrent": 42470, "sonarr": 42471, "radarr": 42472, "prowlarr": 42473}
    for port in (29140, 29014, *ports.values()):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    docker = executable()

    def command(arguments, timeout=120):
        result = subprocess.run([docker, *arguments], capture_output=True, text=True, encoding="utf-8",
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Scoped Docker acceptance step failed; private output withheld.")
        return result.stdout.strip()

    before = set(command(["ps", "-q"]).splitlines())
    state = root / "package-state"
    bootstrap = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(state), "-MediaFolder", str(media),
        "-Port", "29140", "-ControllerPort", "29014", "-NoBrowser"], capture_output=True, text=True,
        timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    (root / "bootstrap.log").write_text(bootstrap.stdout + bootstrap.stderr)
    assert bootstrap.returncode == 0
    project = json.loads((state / "installation.json").read_text(encoding="utf-8-sig"))["project"]
    base = ["compose", "--project-name", project, "-f", str(state / "compose.json")]
    origin, password = "http://localhost:29140", secrets.token_urlsafe(24)
    (root / "access.json").write_text(json.dumps({"dashboard": origin, "owner_password": password,
        "notice": "Private disposable lab access; never upload."}))
    invitation = command([*base, "exec", "-T", "stackarr", "stackarr", "setup-link"])
    print("Fresh packaged startup passed; starting the four-app browser journey.", flush=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(120000)
        page.goto(invitation)
        page.get_by_label("Create a password", exact=True).fill(password)
        page.get_by_role("button", name="Continue to setup", exact=False).click()
        page.get_by_role("button", name="Check Docker", exact=True).click()
        expect(page.locator("#setup-runtime-result")).to_contain_text("Docker is ready")
        for key in ports:
            page.locator("#setup-" + key).check()
        page.get_by_label("Port selection", exact=True).select_option("custom")
        for key, port in ports.items():
            page.locator("#setup-port-" + key).fill(str(port))
        page.get_by_role("button", name="Save & continue", exact=False).click()
        page.get_by_role("button", name="Choose a folder…", exact=True).click()
        page.get_by_role("button", name="My media folder", exact=True).click()
        page.get_by_role("button", name="Use this folder", exact=True).click()
        page.get_by_role("button", name="Save & continue", exact=False).click()
        page.get_by_role("button", name="Review installation", exact=True).click()
        page.get_by_role("button", name="Download & install these apps", exact=True).click()
        for _ in range(360):
            rows = page.request.get(origin + "/api/deployments").json()["operations"]
            if rows and rows[0]["state"] in {"needs-setup", "failed", "interrupted"}:
                break
            page.wait_for_timeout(2000)
        assert len(rows) == 1 and rows[0]["state"] == "needs-setup" and set(rows[0]["apps"]) == set(ports)
        identity = rows[0]["id"]
        print("Fresh four-app installation passed; testing the private handoff and all connections.", flush=True)
        page.get_by_role("button", name="Check progress", exact=True).click()
        page.get_by_role("button", name="Finish connecting", exact=True).click()
        expect(page.locator("#wiring-preview")).to_be_visible()
        page.get_by_role("button", name="Review app login setup", exact=True).click()
        page.get_by_role("button", name="Prepare and save app logins", exact=True).click()
        expect(page.get_by_text("Generated login saved privately.", exact=False).first).to_be_visible()
        page.get_by_text("Your installed app logins", exact=True).click()
        page.get_by_label("App login", exact=True).select_option("sonarr")
        page.get_by_label("Stackarr owner password", exact=True).fill(password)
        page.get_by_role("button", name="Show generated login", exact=True).click()
        expect(page.locator("#generated-login-password")).to_be_visible()
        assert len(page.locator("#generated-login-password").input_value()) >= 32
        page.get_by_role("button", name="Hide login", exact=True).click()
        assert page.locator("#generated-login-password").count() == 0
        page.locator("#wiring-preview").click()
        expect(page.locator("#wiring-apply")).to_be_visible()
        with page.expect_response(lambda response: response.url.endswith("/api/wiring/apply"), timeout=120000) as response:
            page.locator("#wiring-apply").click()
        applied = response.value.json()
        assert len(applied["results"]) == 4 and {row["state"] for row in applied["results"]} == {"created"}
        expect(page.locator("#wiring-output")).to_contain_text("Connection results", timeout=120000)
        page.locator("#wiring-preview").click()
        expect(page.locator("#wiring-output")).to_contain_text("No new connections are ready to add", timeout=120000)
        page.screenshot(path=str(root / "connections.png"), full_page=True)
        stamp = time.time()
        page.request.post(origin + "/api/refresh")
        for _ in range(80):
            states = page.request.get(origin + "/api/status").json()["integrations"]
            ready = {app["id"] for app in states if app["state"] == "ready" and not app["stale"] and (app["collected_at"] or 0) > stamp}
            if ready == set(ports):
                break
            page.wait_for_timeout(500)
        assert ready == set(ports)
        browser.close()
    verified = json.loads(command([*base, "exec", "-T", "stackarr", "python", "-c", VERIFY.replace("42460", "42470")]))
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
    assert before <= set(command(["ps", "-q"]).splitlines())
    manifest = json.loads((package / "manifest.json").read_text())
    report = {"passed": True, "packaged_startup_without_python": True, "browser_install_and_wiring": True,
              "deployment": identity, "image": manifest["image_id"], "connections_created": 4,
              "repeat_proposes_changes": 0, "fresh_monitoring": sorted(ready), "readback": verified,
              "sentinel_and_unrelated_containers_preserved": True, "kept_running": args.keep_running,
              "scope": "Fresh four-app package on the existing Docker host; no Windows reboot, indexers, downloads or imports"}
    (root / "report.json").write_text(json.dumps(report, indent=2))
    if args.keep_running:
        print("Fresh packaged four-app acceptance passed; retained lab: " + str(root))
        return
    app_compose = state / "controller/state/deployments" / identity / "compose.json"
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(app_compose), "stop"])
    command([*base, "stop"])
    environment = os.environ.copy()
    environment["STACKARR_LAB_CONTROLLER_ROOT"] = str(state / "controller")
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_LAB_CONTROLLER_ROOT) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                   env=environment, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    print("Fresh packaged four-app browser acceptance passed; evidence: " + str(root / "report.json"))


if __name__ == "__main__":
    main()
