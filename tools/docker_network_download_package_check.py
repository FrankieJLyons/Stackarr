"""Frozen-controller/browser download retry, compatible promotion and lab cleanup."""

import argparse
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

from stackarr import onboarding
from stackarr.deployment import Deployments
from stackarr.self_update import SelfUpdates, fingerprint, package, read, write
from stackarr.store import Store
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import bootstrap, command, hashes, stop_lab
from tools.docker_host_recovery_check import api, login
from tools.docker_network_download_check import ENGINE, LABEL, REGISTRY, ROOT, outer, preserved, record
from tools.download_registry_fixture import build

PACKAGE = Path("test-results/network-download-package-extracted-r2/Stackarr-Docker-Network-Download-Preview-20261018-r2").resolve()
OLD = Path("test-results/runtime-repair-package-extracted-r2/Stackarr-Docker-Runtime-Repair-Preview-20261018-r2").resolve()
ARCHIVE = Path("dist") / (PACKAGE.name + ".zip")
LAB = ROOT / "package-lab"
STATE = LAB / "package-state"
ORIGIN = "http://localhost:29310"
PACKAGE_REGISTRY = "stackarr-network-download-package-registry-20261018-r2"


def packaged():
    if not PACKAGE.exists():
        PACKAGE.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(ARCHIVE) as bundle:
            names = bundle.namelist()
            assert len(names) == 9 and all(Path(name).parts[0] == PACKAGE.name and len(Path(name).parts) == 2 for name in names)
            bundle.extractall(PACKAGE.parent)
    manifest = package(PACKAGE)
    report = ROOT / "frozen-smoke.json"
    with tempfile.TemporaryDirectory(prefix="stackarr-network-download-smoke-") as temporary:
        result = subprocess.run([str(PACKAGE / "StackarrPreview.exe"), "--self-test-report", str(report)],
            cwd=temporary, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW,
            env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1", "STACKARR_PACKAGE_ROOT": str(PACKAGE)})
    assert result.returncode == 0 and read(report)["passed"] and len(read(report)["checks"]) == 19
    write(ROOT / "package-verification.json", {"package": manifest["release"], "image": manifest["image_id"],
        "zip_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(), "entries": 9,
        "payload_hashes_verified": len(manifest["files"]), "frozen_smoke_checks": 19})
    LAB.mkdir(exist_ok=True)
    media = LAB / "media"
    shutil.copytree(Path("test-results/docker-optional-maintenance-20261018/media"), media)
    write(ROOT / "packaged-media-before.json", hashes(media))
    installation, origin = bootstrap(OLD, LAB, 29310, 29104)
    assert origin == ORIGIN
    password = secrets.token_urlsafe(32)
    write(LAB / "access.json", {"owner_password": password})
    invite = command(["compose", "--project-name", installation["project"], "-f", str(STATE / "compose.json"), "exec", "-T", "stackarr", "stackarr", "setup-link"])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(180000)
        page.goto(invite)
        page.get_by_label("Create a password", exact=True).fill(password)
        page.get_by_role("button", name="Continue to setup", exact=False).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        with login(ORIGIN, password) as client:
            current = api(client, "config")
            current["config"]["dashboard"]["appearance"] = "light"
            api(client, "config", {"revision": current["revision"], "config": current["config"]}, method="PUT")
        before = fingerprint(STATE / "controller/state")
        SelfUpdates(STATE, OLD).admit(ARCHIVE.resolve())
        page.reload()
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
        page.get_by_role("button", name="Review Stackarr update", exact=True).click()
        with page.expect_response(lambda response: response.url.endswith("/api/stackarr-update-apply")) as approval:
            page.get_by_role("button", name="Update Stackarr", exact=True).click()
        assert approval.value.status == 202
        operation = approval.value.json()["id"]
        for _ in range(600):
            job = read(STATE / "stackarr-maintenance/jobs" / operation / "job.json")
            if job["phase"] in {"succeeded", "failed-recovered", "needs-recovery"}:
                break
            time.sleep(.5)
        assert job["phase"] == "succeeded", job["message"]
        page.goto(ORIGIN)
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        assert fingerprint(STATE / "controller/state") == before
        with Store(STATE / "controller/state").db() as db:
            assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='deployment_steps'").fetchone()
        with login(ORIGIN, password) as client:
            assert api(client, "config")["config"]["dashboard"]["appearance"] == "light"
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
        expect(page.get_by_text(PACKAGE.name, exact=False).first).to_be_visible()
        page.screenshot(path=str(ROOT / "packaged-compatible-update.png"), full_page=True)
        record("packaged-older-release-promotion-with-account-session-and-settings-retained", old_idle_database_preserved=True)

        directory = ROOT / "package-registry"
        directory.mkdir()
        fixture = build(directory, ROOT / "binaries", "packaged")
        image = fixture["image"].replace("localhost:5000/", "localhost:44551/")
        shutil.copyfile(Path(__file__).with_name("download_registry_fixture.py"), directory / "registry.py")
        write(directory / "control.json", {"mode": "unauthorized"})
        outer(["run", "-d", "--name", PACKAGE_REGISTRY, "--label", "io.stackarr.lab=" + LABEL,
            "--network", "bridge", "--publish", "127.0.0.1:44551:5000", "--memory", "256m", "--pids-limit", "128",
            "--mount", "type=bind,source=" + str(directory) + ",target=/fixture", "--entrypoint", "python", manifest["image_id"], "/fixture/registry.py"])
        for _ in range(60):
            if (directory / "observations.json").exists():
                break
            time.sleep(.5)
        assert (directory / "observations.json").exists()
        host = Deployments(Store(STATE / "controller/state"), auto_logins=True)
        draft = onboarding.read(host.store)
        onboarding.save(host.store, onboarding.SaveDraft(revision=draft["revision"], draft=onboarding.SetupDraft(
            step=2, apps=["seerr"], choices={"seerr": {"mode": "install", "port": 43450}})))
        with patch("stackarr.deployment.images", return_value={"seerr": image}):
            reviewed = host.review()
        # Only this original-image fixture receives an explicit test subnet, so
        # the host's remaining default address range stays available to others.
        existing = outer(["network", "ls", "-q"]).stdout.split()
        subnets = outer(["network", "inspect", "--format", "{{json .IPAM.Config}}", *existing]).stdout
        occupied = [ipaddress.ip_network(row["Subnet"]) for line in subnets.splitlines()
                    for row in json.loads(line) or [] if row.get("Subnet")]
        subnet = ipaddress.ip_network("198.18.66.0/28")
        assert not any(value.version == 4 and value.overlaps(subnet) for value in occupied)
        reviewed["compose"]["networks"]["control"] = {"ipam": {"config": [{"subnet": str(subnet)}]}}
        identity = host.enqueue(reviewed)
        write(ROOT / "packaged-operation.json", {"id": identity, "image": image, "installation": installation})
        with login(ORIGIN, password) as client:
            for _ in range(600):
                row = next(row for row in api(client, "deployments")["operations"] if row["id"] == identity)
                if row["state"] == "failed":
                    break
                time.sleep(.5)
            assert row["state"] == "failed" and row["phase"] == "downloading" and row["diagnostic"] == "download-unavailable", row["message"]
            assert not outer(["ps", "-aq", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity]).stdout.strip()
            assert not outer(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity]).stdout.strip()
            saved = api(client, "onboarding")
            api(client, "onboarding", {"revision": saved["revision"], "draft": {"step": 2, "apps": ["seerr"], "port_mode": "custom", "choices": {"seerr": {"mode": "install", "port": 43450}}}}, method="PUT")
        browser.close()
    retry_browser()


def retry_browser():
    identity = read(ROOT / "packaged-operation.json")["id"]
    password = read(LAB / "access.json")["owner_password"]
    directory = ROOT / "package-registry"
    manifest = package(PACKAGE)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(180000)
        page.goto(ORIGIN)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=False).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        if page.get_by_role("button", name="Resume setup", exact=True).is_visible():
            page.get_by_role("button", name="Resume setup", exact=True).click()
        expect(page.get_by_role("button", name="Retry download", exact=True)).to_be_visible()
        before_networks = outer(["network", "ls", "-q", "--no-trunc"]).stdout
        page.get_by_role("button", name="Check Docker again", exact=True).click()
        expect(page.get_by_text("unallocated IPv4 network ranges", exact=False).first).to_be_visible()
        assert before_networks == outer(["network", "ls", "-q", "--no-trunc"]).stdout
        page.screenshot(path=str(ROOT / "packaged-download-failure.png"), full_page=True)
        write(directory / "control.json", {"mode": "healthy"})
        with page.expect_response(lambda response: response.url.endswith("/api/deployments/" + identity + "/resume")) as resumed:
            page.get_by_role("button", name="Retry download", exact=True).click()
        assert resumed.value.status == 202
        with login(ORIGIN, password) as client:
            for _ in range(600):
                row = next(row for row in api(client, "deployments")["operations"] if row["id"] == identity)
                if row["state"] not in {"queued", "running"}:
                    break
                time.sleep(.5)
            assert row["state"] == "needs-setup" and row["phase"] == "complete", row["message"]
            assert api(client, "config")["config"]["dashboard"]["appearance"] == "light"
        page.reload()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        if page.get_by_role("button", name="Resume setup", exact=True).is_visible():
            page.get_by_role("button", name="Resume setup", exact=True).click()
        expect(page.get_by_role("heading", name="Apps installed — finish setup", exact=True)).to_be_visible()
        page.screenshot(path=str(ROOT / "packaged-download-retry.png"), full_page=True)
        browser.close()
    controller = Deployments(Store(STATE / "controller/state"))
    with controller.store.db() as db:
        assert db.execute("SELECT count(*) FROM deployments").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit WHERE event='deployment.started'").fetchone()[0] == 1
    runtime = SelfUpdates(STATE, PACKAGE).active()
    assert SelfUpdates(STATE, PACKAGE).controller_probe(runtime)["executable"] == manifest["files"]["StackarrPreview.exe"]
    container = "stackarr-owned-" + identity + "-seerr-1"
    assert outer(["exec", container, "/bin/busybox", "cat", "/app/config/preserve.txt"]).stdout.strip() == "original-settings"
    assert hashes(LAB / "media") == read(ROOT / "packaged-media-before.json")
    record("packaged-real-registry-failure-browser-check-and-frozen-download-retry", actual_frozen_controller=True,
           same_deployment_single_activation=True, no_app_resources_before_download=True, original_fixture_not_upstream_seerr=True)


def finalize():
    report = read(ROOT / "cases.json")
    assert len(report["cases"]) == 8 and all(row["passed"] for row in report["cases"])
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
    dashboard = command(["ps", "-q", "--no-trunc", "--filter", "name=^/stackarr-plex-lab-bc615eaf1fe6-stackarr-1$"])
    fresh = json.loads(command(["exec", dashboard, "python", "-c", script]))
    assert len(fresh) == 9 and all(fresh.values())
    write(ROOT / "main-authenticated-monitoring.json", fresh)
    state = read(ROOT / "packaged-operation.json")
    volumes = set(command(["volume", "ls", "-q"]).splitlines())
    stop_lab(LAB, state["installation"], [state["id"]])
    command(["compose", "--project-name", "stackarr-owned-" + state["id"], "-f", str(STATE / "controller/state/deployments" / state["id"] / "compose.json"), "down"])
    command(["compose", "--project-name", state["installation"]["project"], "-f", str(STATE / "compose.json"), "down"])
    for name in (PACKAGE_REGISTRY, REGISTRY, ENGINE, "stackarr-network-download-registry-20261018", "stackarr-network-download-engine-20261018"):
        info = json.loads(outer(["inspect", name]).stdout)[0]
        assert info["Config"]["Labels"].get("io.stackarr.lab") in {LABEL, "network-download-20261018"}
        outer(["stop", "--timeout", "30", info["Id"]])
        outer(["rm", info["Id"]])
    assert volumes == set(command(["volume", "ls", "-q"]).splitlines())
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert hashes(LAB / "media") == read(ROOT / "packaged-media-before.json")
    write(ROOT / "acceptance.json", {"passed": True, "cases": 8, "package": PACKAGE.name,
        "six_real_nested_engine_cases": True, "two_packaged_browser_cases": True,
        "nine_main_integrations_freshly_authenticated": True, "main_media_files": len(read(ROOT / "main-before.json")["media"]),
        "existing_main_apps_media_settings_and_schedule_preserved": True,
        "lab_containers_and_networks_removed": True, "all_volumes_state_keys_and_media_retained": True,
        "main_package_not_upgraded": True})
    print("Final network/download acceptance passed; only lab containers/networks removed, all settings/media retained.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("packaged", "retry-browser", "finalize"))
    globals()[parser.parse_args().phase.replace("-", "_")]()
