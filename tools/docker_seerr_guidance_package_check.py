"""Packaged first-run account guidance without touching existing installations."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from stackarr.deployment import Deployments
from stackarr.self_update import package, read, write
from stackarr.store import Store
from tools.docker_folder_ports_check import bootstrap, command, hashes, stop_lab
from tools.docker_seerr_guidance_check import ROOT, appdata, payload, preserved, record

PACKAGE = Path("test-results/seerr-setup-package-extracted-r3/Stackarr-Docker-Seerr-Setup-Preview-20261018-r3").resolve()
ARCHIVE = Path("dist") / (PACKAGE.name + ".zip")


def verify_package():
    PACKAGE.parent.mkdir(exist_ok=True)
    assert not PACKAGE.exists()
    with zipfile.ZipFile(ARCHIVE) as bundle:
        names = bundle.namelist()
        assert len(names) == 9 and all(Path(name).parts[0] == PACKAGE.name and len(Path(name).parts) == 2 for name in names)
        bundle.extractall(PACKAGE.parent)
    manifest = package(PACKAGE)
    report = ROOT / "frozen-smoke.json"
    with tempfile.TemporaryDirectory(prefix="stackarr-seerr-setup-smoke-") as temporary:
        result = subprocess.run([str(PACKAGE / "StackarrPreview.exe"), "--self-test-report", str(report)],
            cwd=temporary, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW,
            env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1", "STACKARR_PACKAGE_ROOT": str(PACKAGE)})
    assert result.returncode == 0 and read(report)["passed"] and len(read(report)["checks"]) == 21
    write(ROOT / "package-verification.json", {"package": manifest["release"], "image": manifest["image_id"],
        "zip_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(), "entries": 9,
        "payload_hashes_verified": len(manifest["files"]), "frozen_smoke_checks": 21})
    print("Final Seerr setup ZIP verified, including 21 frozen checks.", flush=True)


def wait(page, origin, identity):
    for _ in range(600):
        response = page.request.get(origin + "/api/deployments")
        assert response.status == 200
        row = next(row for row in response.json()["operations"] if row["id"] == identity)
        if row["state"] not in {"queued", "running"}:
            assert row["state"] == "needs-setup", row["message"]
            return row
        time.sleep(.5)
    raise AssertionError("The isolated setup did not finish")


def cleanup(root, installation, identity):
    volumes = set(command(["volume", "ls", "-q"]).split())
    stop_lab(root, installation, [identity])
    state = root / "package-state"
    for project, filename in (("stackarr-owned-" + identity, state / "controller/state/deployments" / identity / "compose.json"),
                              (installation["project"], state / "compose.json")):
        command(["compose", "--project-name", project, "-f", str(filename), "down"])
    assert volumes == set(command(["volume", "ls", "-q"]).split())
    write(root / "cleaned.json", {"containers_networks_removed": True, "volumes_state_keys_media_retained": True})


def run(combined=False, resume=False):
    root = ROOT / ("packaged-plex-seerr-r3" if combined else "packaged-seerr-r3")
    if not resume:
        assert not root.exists()
        root.mkdir()
    media = root / "media"
    if not resume:
        shutil.copytree(ROOT / "media", media)
    before = hashes(media)
    if resume:
        installation = read(root / "installation.json")
        origin = "http://localhost:" + str(installation["port"])
    else:
        installation, origin = bootstrap(PACKAGE, root, 29350, 29108, media if combined else None)
    write(root / "installation.json", installation)
    state = root / "package-state"
    invite = command(["compose", "--project-name", installation["project"], "-f", str(state / "compose.json"), "exec", "-T", "stackarr", "stackarr", "setup-link"])
    password = read(root / "access.json")["owner_password"] if resume else secrets.token_urlsafe(32)
    write(root / "access.json", {"owner_password": password})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(120000)
        page.goto(invite)
        if not resume:
            page.get_by_label("Create a password", exact=True).fill(password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            selected = ["seerr", "plex"] if combined else ["seerr"]
            for key in selected:
                page.locator("#setup-" + key).check()
            page.get_by_role("button", name="Save & continue", exact=False).click()
            if combined:
                expect(page.locator("#setup-selected-folder")).to_have_text(media.name)
            else:
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
            write(root / "operation.json", {"id": identity, "ports": ports})
        else:
            page.get_by_label("Password", exact=True).fill(password)
            page.get_by_role("button", name="Sign in", exact=False).click()
            operation = read(root / "operation.json")
            identity, ports = operation["id"], operation["ports"]
            entry = page.get_by_role("button", name="Resume setup", exact=True)
            progress = page.get_by_role("button", name="Check progress", exact=True)
            expect(entry.or_(progress).first).to_be_visible(timeout=120000)
            if entry.is_visible():
                entry.click()
        wait(page, origin, identity)
        page.get_by_role("button", name="Check progress", exact=True).click()
        # The previous guide stays visible while progress refreshes. Wait for
        # that action to finish before opening details in the replacement DOM.
        expect(page.get_by_role("button", name="Check progress", exact=True)).to_be_enabled()
        expect(page.get_by_role("heading", name="Sign in to Seerr with Plex", exact=True)).to_be_visible(timeout=120000)
        assert page.evaluate("!document.querySelector('#main').textContent.includes('\u00e2\u2020')&&!document.querySelector('#main').textContent.includes('\u00c2\u00b7')")
        expect(page.get_by_role("heading", name="Finish setting up your apps", exact=True)).to_have_count(0)
        if combined:
            expect(page.get_by_role("heading", name="Set up your Plex server", exact=True)).to_be_visible()
            page.get_by_text("Movie and TV folder locations", exact=True).click()
            expect(page.get_by_text("/data/media/movies", exact=True)).to_be_visible()
        else:
            expect(page.get_by_role("heading", name="Set up your Plex server", exact=True)).to_have_count(0)
        page.get_by_text("Sign-in could not finish?", exact=True).click()
        address = "http://localhost:" + str(ports["seerr"])
        expect(page.get_by_label("Seerr address", exact=True)).to_have_value(address)
        # Browser-only clipboard fixtures keep the person's actual clipboard intact.
        page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.copiedSetupAddress=value}}})")
        page.get_by_role("button", name="Copy Seerr address", exact=True).click()
        expect(page.get_by_text("Seerr address copied.", exact=False)).to_be_visible()
        assert page.evaluate("window.copiedSetupAddress") == address
        page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('Denied fixture')}}})")
        page.get_by_role("button", name="Copy Seerr address", exact=True).click()
        expect(page.get_by_text("Select and copy the address above", exact=False)).to_be_visible()
        assert page.get_by_label("Seerr address", exact=True).evaluate("e=>e.selectionStart===0&&e.selectionEnd===e.value.length")
        name = "plex-and-seerr" if combined else "seerr-only"
        page.screenshot(path=str(ROOT / (name + "-guidance.png")), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        page.screenshot(path=str(ROOT / (name + "-guidance-phone.png")), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1050})
        assert appdata(ports["seerr"])["appData"] is True
        with page.expect_popup() as opened:
            page.get_by_role("link", name="Open Seerr setup", exact=False).click()
        seerr = opened.value
        expect(seerr.get_by_role("button", name="Configure Plex", exact=True)).to_be_visible(timeout=120000)
        expect(seerr.get_by_text("volume mount was not configured properly", exact=False)).to_have_count(0)
        seerr.screenshot(path=str(ROOT / (name + "-upstream-no-warning.png")), full_page=True)
        if not combined:
            popup_checks(seerr, root, ports["seerr"])
        with page.expect_response(lambda response: response.url.endswith("/finish-connecting")) as finished:
            page.locator('[data-finish-install="' + identity + '"]').click()
        assert finished.value.status == 200
        assert any(row["state"] == "needs-setup" for row in finished.value.json()["apps"])
        service = Deployments(Store(state / "controller/state"))
        recipe = payload(service, identity)
        assert recipe["compose"]["services"]["seerr"]["volumes"] == [{"type": "volume", "source": "seerr-config", "target": "/app/config"}]
        if combined:
            plex = json.loads(command(["inspect", "stackarr-owned-" + identity + "-plex-1"]))[0]
            assert next(mount for mount in plex["Mounts"] if mount["Destination"] == "/data")["RW"] is False
            response = page.request.get("http://localhost:" + str(ports["plex"]) + "/identity", headers={"Accept": "application/json"})
            machine = response.json()["MediaContainer"]
            assert machine["machineIdentifier"] not in {"2a53c6f38fe655b611fbd80c5cf6409bb526300e", "2492001cd73a50a072d280b215f0e7da8e788956"}
            assert not machine.get("claimed")
        assert hashes(media) == before
        record("packaged-" + name + "-account-guidance-and-verified-warning-fix-r3", frozen_controller=True,
               scoped_instructions=True, desktop_phone=True, clipboard_fixture_only=True,
               incomplete_accounts_preserved=True, unchanged_media=True, readable_setup_text=True)
        browser.close()
    cleanup(root, installation, identity)


def popup_checks(seerr, root, port):
    seerr.get_by_role("button", name="Configure Plex", exact=True).click()
    if "real-seerr-button-opens-official-plex-authorization-window" not in {row["case"] for row in read(ROOT / "cases.json")["cases"]}:
        with seerr.expect_popup() as window:
            seerr.get_by_role("button", name=re.compile("Login with")).click()
        auth = window.value
        auth.wait_for_url("https://app.plex.tv/auth/**", timeout=120000)
        assert urlsplit(auth.url).hostname == "app.plex.tv" and urlsplit(auth.url).scheme == "https"
        write(root / "fresh-plex-authorize-private.json", {"url": auth.url, "seerr_port": port})
        auth.screenshot(path=str(ROOT / "real-plex-signin-window.png"), full_page=True)
        record("real-seerr-button-opens-official-plex-authorization-window", actual_upstream_popup=True,
               authentication_completion="separate account step", no_reused_authorization=True)
        auth.close()
    # Install the browser fixture before Seerr initializes its popup helper.
    seerr.add_init_script("window.open=()=>{window.blockedSetupWindows=(window.blockedSetupWindows||0)+1;return null}")
    seerr.reload()
    configure = seerr.get_by_role("button", name="Configure Plex", exact=True)
    login = seerr.get_by_role("button", name=re.compile("Login with"))
    expect(configure.or_(login).first).to_be_visible(timeout=120000)
    if configure.is_visible():
        configure.click()
    windows = len(seerr.context.pages)
    seerr.get_by_role("button", name=re.compile("Login with")).click()
    seerr.wait_for_function("window.blockedSetupWindows===1")
    assert len(seerr.context.pages) == windows
    assert seerr.request.get("http://localhost:" + str(port) + "/api/v1/auth/me").status in {401, 403}
    seerr.screenshot(path=str(ROOT / "blocked-plex-popup.png"), full_page=True)
    if "blocked-upstream-popup-guidance" not in {row["case"] for row in read(ROOT / "cases.json")["cases"]}:
        record("blocked-upstream-popup-guidance", popup_block_is_browser_fixture=True, no_authentication_bypass=True,
               no_window_created=True, upstream_inline_error_not_required=True)


def finalize():
    preserved()
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
    dashboard = read(ROOT / "main-before.json")["dashboard"]
    fresh = json.loads(command(["exec", dashboard, "python", "-c", script]))
    assert len(fresh) == 9 and all(fresh.values())
    write(ROOT / "main-authenticated-monitoring.json", fresh)
    assert set(read(ROOT / "volumes-before.json")) <= set(command(["volume", "ls", "-q"]).split())
    for name in ("packaged-seerr-r2", "packaged-plex-seerr-r2", "packaged-seerr-r3", "packaged-plex-seerr-r3"):
        assert read(ROOT / name / "cleaned.json")["volumes_state_keys_media_retained"]
    cases = read(ROOT / "cases.json")["cases"]
    assert len(cases) >= 12 and all(row["passed"] for row in cases)
    preserved()
    write(ROOT / "acceptance.json", {"passed": True, "cases": len(cases), "package": PACKAGE.name,
        "main_apps_settings_credentials_media_and_backup_policy_preserved": True,
        "nine_main_integrations_freshly_authenticated": True, "main_media_files": len(read(ROOT / "main-before.json")["media"]),
        "lab_state_keys_volumes_and_media_retained": True, "main_not_upgraded": True,
        "official_popup_handoff_verified": True, "fresh_account_completion_separate": True})
    print("Seerr storage/guidance acceptance complete; existing installation preserved.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["verify_package", "seerr", "resume_seerr", "combined", "finalize"])
    phase = parser.parse_args().phase
    if phase in {"seerr", "resume_seerr", "combined"}:
        run(phase == "combined", phase == "resume_seerr")
    else:
        globals()[phase]()
