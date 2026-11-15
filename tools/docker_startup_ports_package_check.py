"""Frozen controller and browser acceptance of a real final-start port conflict."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.bootstrap import accepted
from stackarr.deployment import Deployments
from stackarr.docker_runtime import executable
from stackarr.install_ports import InstallPorts
from stackarr.self_update import package, read, write
from stackarr.store import Store
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import bootstrap, command, hashes, stop_lab
from tools.docker_host_recovery_check import api
from tools.docker_startup_ports_check import LABEL, ROOT, info, marker, receipt, record, remove_owner

PACKAGE = Path("test-results/startup-ports-package-extracted-r4/Stackarr-Docker-Startup-Ports-Preview-20261018-r4").resolve()
ARCHIVE = Path("dist") / (PACKAGE.name + ".zip")
LAB = ROOT / "package-lab-r4"
STATE = LAB / "package-state"
ORIGIN = "http://localhost:29330"


def packaged():
    PACKAGE.parent.mkdir(exist_ok=True)
    assert not PACKAGE.exists()
    with zipfile.ZipFile(ARCHIVE) as bundle:
        names = bundle.namelist()
        assert len(names) == 9 and all(Path(name).parts[0] == PACKAGE.name and len(Path(name).parts) == 2 for name in names)
        bundle.extractall(PACKAGE.parent)
    manifest = package(PACKAGE)
    report = ROOT / "frozen-smoke.json"
    with tempfile.TemporaryDirectory(prefix="stackarr-startup-ports-smoke-") as temporary:
        result = subprocess.run([str(PACKAGE / "StackarrPreview.exe"), "--self-test-report", str(report)],
            cwd=temporary, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW,
            env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1", "STACKARR_PACKAGE_ROOT": str(PACKAGE)})
    assert result.returncode == 0 and read(report)["passed"] and len(read(report)["checks"]) == 20
    write(ROOT / "package-verification.json", {"package": manifest["release"], "image": manifest["image_id"],
        "zip_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(), "entries": 9,
        "payload_hashes_verified": len(manifest["files"]), "frozen_smoke_checks": 20})
    LAB.mkdir()
    media = LAB / "media"
    shutil.copytree(ROOT / "media", media)
    write(ROOT / "packaged-media-before.json", hashes(media))
    control = ROOT / "proxy-control.json"
    write(control, {"root": str(ROOT), "deployment_root": str(STATE / "controller/state/deployments"), "docker": executable(), "helper": manifest["image_id"], "label": LABEL,
                    "owner_name": "stackarr-startup-packaged-original", "mode": "normal"})
    proxy = ROOT / "proxy-dist-r3/docker"
    assert (proxy / "docker.exe").is_file()
    with patch.dict(os.environ, {"PATH": str(proxy) + os.pathsep + os.environ["PATH"], "STACKARR_LAB_PROXY_CONFIG": str(control)}):
        installation, origin = bootstrap(PACKAGE, LAB, 29330, 29106, media)
    assert origin == ORIGIN
    write(ROOT / "packaged-installation.json", installation)
    invite = command(["compose", "--project-name", installation["project"], "-f", str(STATE / "compose.json"),
                      "exec", "-T", "stackarr", "stackarr", "setup-link"])
    password = secrets.token_urlsafe(32)
    write(LAB / "access.json", {"owner_password": password})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(120000)
        page.goto(invite)
        page.get_by_label("Create a password", exact=True).fill(password)
        page.get_by_role("button", name="Continue to setup", exact=False).click()
        for key in ("prowlarr", "qbittorrent"):
            page.locator("#setup-" + key).check()
        page.get_by_role("button", name="Save & continue", exact=False).click()
        expect(page.locator("#setup-selected-folder")).to_have_text(media.name)
        page.get_by_role("button", name="Save & continue", exact=False).click()
        page.get_by_role("button", name="Review installation", exact=True).click()
        expect(page.get_by_role("button", name="Download & install these apps", exact=True)).to_be_visible()
        write(control, read(control) | {"mode": "armed"})
        with page.expect_response(lambda response: response.url.endswith("/api/deployments/install")) as response:
            page.get_by_role("button", name="Download & install these apps", exact=True).click()
        assert response.value.status == 202
        identity = response.value.json()["id"]
        write(ROOT / "packaged-operation.json", {"id": identity})
        print("Frozen controller is starting the isolated app batch; real port fault armed.", flush=True)
        with browser_client(page) as client:
            row = wait(client, identity)
            assert row["state"] == "failed" and row["diagnostic"] == "startup-port-conflict", row["message"]
        browser.close()
    recover()


def wait(client, identity):
    for _ in range(600):
        row = next(row for row in api(client, "deployments")["operations"] if row["id"] == identity)
        if row["state"] not in {"queued", "running"}:
            return row
        time.sleep(.5)
    raise AssertionError("The isolated packaged installation did not finish")


def open_setup(page):
    entry = page.get_by_role("button", name="Resume setup", exact=True)
    progress = page.locator("[data-finish-install], [data-install-port-review]")
    expect(entry.or_(progress).first).to_be_visible(timeout=120000)
    if entry.is_visible():
        entry.click()


@contextmanager
def browser_client(page):
    csrf = page.request.get(ORIGIN + "/api/session").json()["csrf"]
    cookies = {item["name"]: item["value"] for item in page.context.cookies(ORIGIN)}
    with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=210, cookies=cookies,
                      headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}) as client:
        yield client


def recover():
    identity = read(ROOT / "packaged-operation.json")["id"]
    fault = read(ROOT / "packaged-fault.json")
    assert fault["id"] == identity and info(identity, "prowlarr")["Id"] == fault["prowlarr"]
    host = Deployments(Store(STATE / "controller/state"), auto_logins=True)
    source = receipt(host, identity)
    already_recovered = host.rows()[0]["state"] == "needs-setup"
    if already_recovered:
        resources = {key: row["resources"] for key, row in source["install_ports"]["before"].items()}
    else:
        assert not info(identity, "qbittorrent")["State"]["Running"]
        resources = {key: row["resources"] for key, row in InstallPorts(host).inspect(identity, source).items()}
    marker(identity)
    password = read(LAB / "access.json")["owner_password"]
    control = ROOT / "proxy-control.json"
    write(control, read(control) | {"mode": "normal"})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(120000)
        page.goto(ORIGIN)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=False).click()
        open_setup(page)
        if not already_recovered:
            expect(page.get_by_role("button", name="Review available ports", exact=True)).to_be_visible()
            page.screenshot(path=str(ROOT / "packaged-final-start-failure.png"), full_page=True)
            with page.expect_response(lambda response: response.url.endswith("/ports/review")) as response:
                page.get_by_role("button", name="Review available ports", exact=True).click()
            assert response.value.status == 200
            reviewed = response.value.json()
            assert [row["app"] for row in reviewed["changes"]] == ["qbittorrent"]
            assert reviewed["changes"][0]["previous"] == fault["port"]
            new_port = reviewed["changes"][0]["port"]
            assert new_port != fault["port"]
            expect(page.get_by_role("heading", name="Review new app addresses", exact=True)).to_be_visible()
            page.screenshot(path=str(ROOT / "packaged-reviewed-ports.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(ROOT / "packaged-reviewed-ports-phone.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1050})
            with page.expect_response(lambda response: response.url.endswith("/api/deployments/actions/apply")) as response:
                page.get_by_role("button", name="Apply new ports & resume", exact=True).click()
            assert response.value.status == 202 and response.value.json()["id"] == identity
            with browser_client(page) as client:
                row = wait(client, identity)
                assert row["state"] == "needs-setup" and row["phase"] == "complete", row["message"]
        else:
            new_port = int(source["compose"]["services"]["qbittorrent"]["ports"][0]["published"])
        target = receipt(host, identity)
        assert target["compose"]["volumes"] == source["compose"]["volumes"]
        assert info(identity, "prowlarr")["Id"] == fault["prowlarr"]
        assert {key: row["resources"] for key, row in InstallPorts(host).inspect(identity, target).items()} == resources
        marker(identity)
        # Deliberately stale only this lab's unactivated binding, as if its
        # approval response was lost. Trusted host status must repair it.
        dashboard = command(["compose", "--project-name", read(ROOT / "packaged-installation.json")["project"],
                             "-f", str(STATE / "compose.json"), "ps", "-q", "stackarr"])
        script = "import json;from pathlib import Path;from stackarr.store import Store;s=Store(Path('/var/lib/stackarr'));\nwith s.db() as d:\n r=d.execute('SELECT ports FROM controller_connections WHERE id=?',(" + repr(identity) + ",)).fetchone();p=json.loads(r[0]);p['qbittorrent']=" + str(fault["port"]) + ";d.execute('UPDATE controller_connections SET ports=? WHERE id=? AND activated=0',(json.dumps(p)," + repr(identity) + "))"
        command(["exec", dashboard, "python", "-c", script])
        with browser_client(page) as client:
            api(client, "deployments")
        script = "from pathlib import Path;from stackarr.store import Store;from stackarr.controller_connections import binding;print(binding(Store(Path('/var/lib/stackarr'))," + repr(identity) + ")[1]['qbittorrent'])"
        assert int(command(["exec", dashboard, "python", "-c", script])) == new_port
        page.reload()
        open_setup(page)
        expect(page.locator('[data-finish-install="' + identity + '"]')).to_be_visible()
        with page.expect_response(lambda response: response.url.endswith("/finish-connecting")) as response:
            page.locator('[data-finish-install="' + identity + '"]').click()
        assert response.value.status == 200 and all(row["state"] in {"connected", "saved"} for row in response.value.json()["apps"])
        expect(page.get_by_text("Connected to Stackarr. Connection details were saved privately.", exact=False).first).to_be_visible(timeout=120000)
        page.screenshot(path=str(ROOT / "packaged-recovered-connected.png"), full_page=True)
        with browser_client(page) as client:
            config = api(client, "config")["config"]["integrations"]
            assert config["qbittorrent"]["port"] == new_port and str(new_port) in config["qbittorrent"]["url"]
        address = host.store.config()[1].integrations["qbittorrent"].url
        with httpx.Client(base_url=address, trust_env=False, headers={"Referer": address}, timeout=15) as client:
            assert accepted(client.post("/api/v2/auth/login", data=host.store.secret("qbittorrent")))
            assert client.get("/api/v2/torrents/info").json() == []
        token = host.store.secret("prowlarr")["api_key"]
        with httpx.Client(base_url=host.store.config()[1].integrations["prowlarr"].url, trust_env=False, headers={"X-Api-Key": token}, timeout=15) as client:
            assert client.get("/api/v1/config/ui").json()["enableColorImpairedMode"] is True
        assert json.loads(command(["inspect", fault["owner"]]))[0]["State"]["Running"]
        assert hashes(LAB / "media") == read(ROOT / "packaged-media-before.json")
        preservation.OUTPUT = ROOT
        preservation.main_preserved()
        record("packaged-frozen-browser-final-start-recovery-r4", same_installation=identity,
               healthy_app_id_and_setting_retained=True, settings_volumes_and_media_retained=True,
               old_port_owner_kept_running=True, stale_handoff_repaired=True, finish_connecting_passed=True)
        browser.close()


def finalize():
    report = read(ROOT / "cases.json")
    assert len(report["cases"]) == 9 and all(row["passed"] for row in report["cases"])
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
    dashboard = command(["ps", "-q", "--no-trunc", "--filter", "name=^/stackarr-plex-lab-bc615eaf1fe6-stackarr-1$"])
    fresh = json.loads(command(["exec", dashboard, "python", "-c", script]))
    assert len(fresh) == 9 and all(fresh.values())
    write(ROOT / "main-authenticated-monitoring.json", fresh)
    volumes = set(command(["volume", "ls", "-q"]).split())
    assert set(read(ROOT / "volumes-before.json")) <= volumes
    cleanup()
    assert not command(["ps", "-aq", "--filter", "label=io.stackarr.lab=" + LABEL])
    assert volumes == set(command(["volume", "ls", "-q"]).split())
    preservation.main_preserved()
    assert hashes(LAB / "media") == read(ROOT / "packaged-media-before.json")
    assert hashes(ROOT / "media") == read(ROOT / "media-before.json")
    write(ROOT / "acceptance.json", {"passed": True, "cases": 9, "package": PACKAGE.name,
        "six_native_real_docker_cases": True, "three_packaged_frozen_controller_browser_cases": True,
        "nine_main_integrations_freshly_authenticated": True, "main_media_files": len(read(ROOT / "main-before.json")["media"]),
        "main_apps_settings_credentials_media_and_schedule_preserved": True, "main_package_not_upgraded": True,
        "lab_containers_and_networks_removed": True, "all_volumes_state_keys_and_media_retained": True})
    print("Final-start recovery acceptance passed; existing apps untouched and all lab data retained.", flush=True)


def cleanup():
    identity = read(ROOT / "packaged-operation.json")["id"]
    installation = read(ROOT / "packaged-installation.json")
    if not (ROOT / "package-cleaned-r4.json").exists():
        stop_lab(LAB, installation, [identity])
        for project, filename in (("stackarr-owned-" + identity, STATE / "controller/state/deployments" / identity / "compose.json"),
                                  (installation["project"], STATE / "compose.json")):
            command(["compose", "--project-name", project, "-f", str(filename), "down"])
        remove_owner(read(ROOT / "packaged-fault.json")["owner"])
        write(ROOT / "package-cleaned-r4.json", {"containers_networks_removed": True, "volumes_state_keys_media_retained": True})
    for project in ("stackarr-owned-" + identity, installation["project"]):
        assert not command(["ps", "-aq", "--filter", "label=com.docker.compose.project=" + project])
        assert not command(["network", "ls", "-q", "--filter", "label=com.docker.compose.project=" + project])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("packaged", "recover", "cleanup", "finalize"))
    globals()[parser.parse_args().phase]()
