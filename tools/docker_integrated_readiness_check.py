"""Test the extracted integrated Windows package using new, isolated Docker state."""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from stackarr.self_update import FINGERPRINT, fingerprint, package, read, write
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import command, hashes, stop_lab
from tools.docker_seerr_guidance_check import appdata
from tools.docker_seerr_guidance_package_check import wait

ROOT = Path("test-results/docker-integrated-readiness-20261019-r1").resolve()
RELEASE = "Stackarr-Docker-First-Run-Preview-20261019-r1"
PACKAGE = Path("test-results/integrated-readiness-package-extracted-r1", RELEASE).resolve()
ARCHIVE = Path("dist", RELEASE + ".zip").resolve()
LAB = ROOT / "packaged-r2"
STATE = LAB / "package-state"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify():
    assert (ROOT / "main-before.json").is_file() and not PACKAGE.exists()
    PACKAGE.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as bundle:
        assert len(bundle.namelist()) == 9
        assert all(Path(name).parts[0] == RELEASE and len(Path(name).parts) == 2 for name in bundle.namelist())
        bundle.extractall(PACKAGE.parent)
    manifest = package(PACKAGE)
    assert "--package-first-run" in (PACKAGE / "Start Stackarr.cmd").read_text()
    assert not (PACKAGE / "StackarrReadiness.exe").exists()
    report = ROOT / "frozen-smoke.json"
    with tempfile.TemporaryDirectory(prefix="stackarr-integrated-smoke-") as temporary:
        result = subprocess.run([str(PACKAGE / "StackarrPreview.exe"), "--self-test-report", str(report)],
            cwd=temporary, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW,
            env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1", "STACKARR_PACKAGE_ROOT": str(PACKAGE)})
    value = read(report)
    assert result.returncode == 0 and value["passed"] and len(value["checks"]) == 23
    write(ROOT / "package-verification.json", {"release": RELEASE, "zip_sha256": digest(ARCHIVE),
        "image_id": manifest["image_id"], "entries": 9, "payload_hashes_verified": len(manifest["files"]),
        "frozen_checks": 23, "same_main_executable": True})
    print("ZIP hashes and 23 frozen checks passed outside the checkout.", flush=True)


def launch(number):
    report = LAB / ("readiness-private-" + str(number) + ".json")
    log = LAB / ("launcher-" + str(number) + ".log")
    assert not report.exists()
    with log.open("wb") as output:
        child = subprocess.Popen([str(PACKAGE / "StackarrPreview.exe"), "--package-first-run",
            "--data-directory", str(STATE), "--connect-directory", str(LAB / "local-state"),
            "--prerequisite-directory", str(LAB / "prerequisites"), "--first-run-report", str(report),
            "--dashboard-port", "29370", "--controller-port", "29130", "--no-browser"],
            cwd=LAB, stdout=output, stderr=output, stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1"})
    for _ in range(300):
        if report.is_file():
            return child, read(report)["url"]
        assert child.poll() is None, "Frozen readiness stopped; see the private lab log."
        time.sleep(.1)
    raise AssertionError("Frozen readiness did not open")


def snapshot(installation, identity):
    dashboard = command(["compose", "--project-name", installation["project"], "-f", str(STATE / "compose.json"), "ps", "-q", "stackarr"])
    app = json.loads(command(["inspect", "stackarr-owned-" + identity + "-seerr-1"]))[0]
    config = command(["exec", app["Id"], "node", "-e",
        "process.stdout.write(require('crypto').createHash('sha256').update(require('fs').readFileSync('/app/config/settings.json')).digest('hex'))"])
    return {"dashboard": dashboard, "app": app["Id"], "app_settings": config,
        "app_mounts": app["Mounts"], "installation": installation,
        "dashboard_settings": command(["exec", dashboard, "python", "-c", FINGERPRINT + "\nprint(fingerprint('/var/lib/stackarr'))"]),
        "controller_settings": fingerprint(STATE / "controller/state")}


def run():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert not LAB.exists()
    LAB.mkdir()
    media = LAB / "media-sentinel"
    media.mkdir()
    (media / "retain-original.txt").write_text("Isolated original media; never modify during package setup.", encoding="utf-8")
    before_media = hashes(media)
    write(LAB / "media-before.json", before_media)
    process, address = launch(1)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(180000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(address)
        expect(page.locator("#continue-stackarr")).to_be_visible()
        expect(page.locator("#install-docker")).to_be_hidden()
        assert not STATE.exists() and not (LAB / "local-state").exists()
        page.screenshot(path=str(ROOT / "packaged-readiness.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.screenshot(path=str(ROOT / "packaged-readiness-phone.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1100})
        with page.expect_response(lambda response: response.url.endswith("/api/stackarr/start")) as continued:
            page.locator("#continue-stackarr").click()
        assert continued.value.status == 200
        page.get_by_label("Create a password", exact=True).wait_for(state="visible", timeout=300000)
        process.wait(timeout=30)
        assert process.returncode == 0
        installation = read(STATE / "installation.json")
        write(LAB / "installation.json", installation)
        origin = "http://localhost:" + str(installation["port"])
        assert urlsplit(page.url).netloc == urlsplit(origin).netloc
        password = secrets.token_urlsafe(32)
        write(LAB / "access.json", {"owner_password": password})
        page.get_by_label("Create a password", exact=True).fill(password)
        page.get_by_role("button", name="Continue to setup", exact=False).click()
        page.locator("#setup-seerr").check()
        page.get_by_role("button", name="Save & continue", exact=False).click()
        expect(page.get_by_text("No media folder needed", exact=True)).to_be_visible()
        page.get_by_role("button", name="Save & continue", exact=False).click()
        with page.expect_response(lambda response: response.url.endswith("/api/deployments/review")) as reviewed:
            page.get_by_role("button", name="Review installation", exact=True).click()
        assert reviewed.value.status == 200
        ports = {row["id"]: int(row["port"]) for row in reviewed.value.json()["apps"]}
        with page.expect_response(lambda response: response.url.endswith("/api/deployments/install")) as approved:
            page.get_by_role("button", name="Download & install these apps", exact=True).click()
        assert approved.value.status == 202
        identity = approved.value.json()["id"]
        write(LAB / "operation.json", {"id": identity, "ports": ports})
        wait(page, origin, identity)
        page.get_by_role("button", name="Check progress", exact=True).click()
        expect(page.get_by_role("button", name="Check progress", exact=True)).to_be_enabled()
        expect(page.get_by_role("heading", name="Sign in to Seerr with Plex", exact=True)).to_be_visible()
        assert appdata(ports["seerr"])["appData"] is True
        with page.expect_popup() as opened:
            page.get_by_role("link", name="Open Seerr setup", exact=False).click()
        seerr = opened.value
        expect(seerr.get_by_role("button", name="Configure Plex", exact=True)).to_be_visible()
        expect(seerr.get_by_text("volume mount was not configured properly", exact=False)).to_have_count(0)
        seerr.close()
        page.screenshot(path=str(ROOT / "packaged-seerr-guidance.png"), full_page=True)
        before = snapshot(installation, identity)
        write(LAB / "before-reopen.json", before)
        print("Integrated readiness reached the same-tab dashboard and installed separate Seerr with verified storage.", flush=True)
        process, address = launch(2)
        page.goto(address)
        expect(page.locator("#continue-stackarr")).to_be_visible()
        page.locator("#continue-stackarr").click()
        page.wait_for_url(lambda value: urlsplit(value).netloc == urlsplit(origin).netloc, timeout=300000)
        process.wait(timeout=30)
        assert process.returncode == 0
        assert page.request.get(origin + "/api/session").json()["authenticated"] is True
        assert snapshot(read(STATE / "installation.json"), identity) == before
        assert hashes(media) == before_media and not errors
        assert not (LAB / "local-state").exists() and not (LAB / "prerequisites").exists()
        write(ROOT / "packaged-browser.json", {"passed": True,
            "fresh_actual_windows_docker_checks": True, "no_app_state_before_continue": True,
            "same_browser_tab_handoff": True, "separate_reviewed_seerr_install": True,
            "patched_seerr_storage_verified": True, "reopen_saved_installation": True,
            "existing_browser_session_retained": True, "same_lab_container_ids_settings_credentials": True,
            "desktop_phone": True, "media_sentinel_unchanged": True, "no_prerequisite_installer_run": True})
        browser.close()
    preservation.main_preserved()
    print("Reopening retained the same lab containers, account, session, app settings and media.", flush=True)


def cleanup():
    installation, identity = read(LAB / "installation.json"), read(LAB / "operation.json")["id"]
    volumes = set(command(["volume", "ls", "-q"]).split())
    stop_lab(LAB, installation, [identity])
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f",
        str(STATE / "controller/state/deployments" / identity / "compose.json"), "down"])
    command(["compose", "--project-name", installation["project"], "-f", str(STATE / "compose.json"), "down"])
    assert volumes == set(command(["volume", "ls", "-q"]).split())
    assert hashes(LAB / "media-sentinel") == read(LAB / "media-before.json")
    return volumes


def finalize():
    volumes = cleanup()
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    script = """import asyncio,json
from pathlib import Path
from stackarr.store import Store
from stackarr.integrations import collect
async def main():
 store=Store(Path('/var/lib/stackarr'))
 async def one(key,app):
  try: await collect(key,app,store.secret(key)); return key,True
  except Exception: return key,False
 print(json.dumps(dict(await asyncio.gather(*(one(k,a) for k,a in store.config()[1].integrations.items() if a.enabled)))))
asyncio.run(main())
"""
    fresh = json.loads(command(["exec", read(ROOT / "main-before.json")["dashboard"], "python", "-c", script]))
    assert len(fresh) == 9 and all(fresh.values())
    write(ROOT / "main-authenticated-monitoring.json", fresh)
    assert set(read(ROOT / "volumes-before.json")) <= volumes
    write(ROOT / "acceptance.json", {"passed": True, "main_apps_authenticated": 9,
        "main_container_ids_settings_credentials_media_unchanged": True,
        "lab_containers_networks_removed": True, "all_volumes_state_keys_media_retained": True,
        "package": read(ROOT / "package-verification.json"), "browser": read(ROOT / "packaged-browser.json")})
    print("Acceptance passed: all nine original apps authenticate; original IDs, settings, credentials and media unchanged. Lab containers/networks removed; all volumes and data retained.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "run", "finalize"])
    {"verify": verify, "run": run, "finalize": finalize}[parser.parse_args().action]()
