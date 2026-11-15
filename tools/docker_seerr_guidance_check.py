"""Seerr warning/persistence checks confined to new owned Docker volumes."""

import argparse
import asyncio
import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet
from playwright.sync_api import expect, sync_playwright

from stackarr import onboarding
from stackarr.app_maintenance import AppMaintenance
from stackarr.deployment import DeploymentError, Deployments
from stackarr.seerr_storage import prepare
from stackarr.self_update import read, write
from stackarr.store import Store
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import command, hashes

ROOT = Path("test-results/docker-seerr-guidance-20261018-r1").resolve()
LABEL = "seerr-guidance-20261018-r1"
PORT = 43750
HELPER = "sha256:fdb0437ffd70db2e453abd45a53c25528f5daf50397180ff3ad36d1d4f2f86f3"


def payload(service, identity):
    with service.store.db() as db:
        return json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])


def node(info, code):
    return command(["exec", info["Id"], "node", "-e", code])


def appdata(port):
    with httpx.Client(trust_env=False, timeout=10) as client:
        for _ in range(120):
            try:
                result = client.get("http://127.0.0.1:" + str(port) + "/api/v1/status/appdata")
                result.raise_for_status()
                return result.json()
            except httpx.HTTPError:
                time.sleep(.5)
    raise AssertionError("The isolated Seerr did not become ready")


def preserved():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    if (ROOT / "media-before.json").exists():
        assert hashes(ROOT / "media") == read(ROOT / "media-before.json")


def record(case, **proof):
    preserved()
    report = read(ROOT / "cases.json") if (ROOT / "cases.json").exists() else {"cases": []}
    assert case not in {row["case"] for row in report["cases"]}
    report["cases"].append({"case": case, "passed": True, "main_preserved": True, **proof})
    write(ROOT / "cases.json", report)
    print("Isolated Seerr setup check passed: " + case, flush=True)


def native():
    assert (ROOT / "main-before.json").exists()
    shutil.copytree(Path("test-results/docker-optional-maintenance-20261018/media"), ROOT / "media")
    write(ROOT / "media-before.json", hashes(ROOT / "media"))
    service = Deployments(Store(ROOT / "native/state"))
    onboarding.initialize(service.store)
    draft = onboarding.read(service.store)
    onboarding.save(service.store, onboarding.SaveDraft(revision=draft["revision"], draft=onboarding.SetupDraft(
        apps=["seerr"], choices={"seerr": {"mode": "install", "port": PORT}}, port_mode="custom")))
    identity = service.enqueue(service.review())
    write(ROOT / "native-operation.json", {"id": identity})
    # Reproduce the unmodified upstream first-run warning before the product's
    # verified fix. No production package has a disable-check/test switch.
    with patch("stackarr.seerr_storage.prepare", lambda *args: None):
        asyncio.run(service.run_one())
    assert service.rows()[0]["state"] == "needs-setup", service.rows()[0]["message"]
    recipe = payload(service, identity)
    maintenance = AppMaintenance(service)
    info = maintenance.container(identity, recipe, "seerr")
    before = maintenance.resources(identity, recipe, "seerr", info)
    status = appdata(PORT)
    assert status["appData"] is False and status["appDataPermissions"] is True
    assert node(info, "const fs=require('fs');const x=fs.lstatSync('/app/config/DOCKER');console.log(x.isFile()&&x.size===0)") == "true"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1365, "height": 950})
        page.goto("http://localhost:" + str(PORT) + "/setup")
        expect(page.get_by_text("volume mount was not configured properly", exact=False)).to_be_visible(timeout=120000)
        page.screenshot(path=str(ROOT / "upstream-warning-before.png"), full_page=True)
        prepare(service, identity, recipe)
        assert appdata(PORT)["appData"] is True
        page.reload()
        expect(page.get_by_text("volume mount was not configured properly", exact=False)).to_have_count(0)
        page.screenshot(path=str(ROOT / "verified-storage-after.png"), full_page=True)
        browser.close()
    assert maintenance.resources(identity, recipe, "seerr", maintenance.container(identity, recipe, "seerr")) == before
    record("real-upstream-warning-cleared-after-owned-storage-and-durable-write-check", settings_volume_retained=True)

    # Guard unexpected files and links: none may be hidden/deleted as a warning.
    for name, code, verify in (
        ("nonempty-marker", "fs.writeFileSync('/app/config/DOCKER','preserve this file')", "fs.readFileSync('/app/config/DOCKER','utf8')==='preserve this file'"),
        ("symlink-marker", "fs.symlinkSync('settings.json','/app/config/DOCKER')", "fs.lstatSync('/app/config/DOCKER').isSymbolicLink()"),
    ):
        node(info, "const fs=require('fs');" + code)
        try:
            prepare(service, identity, recipe)
        except DeploymentError as error:
            assert error.kind == "seerr-storage"
        else:
            raise AssertionError("An unexpected marker must be retained")
        assert node(info, "const fs=require('fs');console.log(" + verify + ")") == "true"
        node(info, "require('fs').unlinkSync('/app/config/DOCKER')")
        record("retain-" + name)

    node(info, "const fs=require('fs');fs.writeFileSync('/app/config/DOCKER','');fs.chmodSync('/app/config',0o500)")
    try:
        try:
            prepare(service, identity, recipe)
        except DeploymentError as error:
            assert error.kind == "seerr-storage"
        else:
            raise AssertionError("Denied writes must keep the warning")
        assert appdata(PORT)["appData"] is False
    finally:
        node(info, "require('fs').chmodSync('/app/config',0o755)")
    record("real-write-denial-keeps-warning-and-settings")
    volume = "stackarr-owned-" + identity + "_seerr-config"
    shared = command(["run", "-d", "--label", "io.stackarr.lab=" + LABEL, "--network", "none", "--entrypoint", "python",
                      "--mount", "type=volume,source=" + volume + ",target=/fixture,readonly", HELPER, "-c", "import time;time.sleep(600)"])
    try:
        try:
            prepare(service, identity, recipe)
        except DeploymentError as error:
            assert error.kind == "seerr-storage"
        else:
            raise AssertionError("Shared storage must retain the marker")
        assert appdata(PORT)["appData"] is False
    finally:
        owned = json.loads(command(["inspect", shared]))[0]
        assert owned["Config"]["Labels"]["io.stackarr.lab"] == LABEL
        command(["rm", "--force", shared])
    prepare(service, identity, recipe)
    record("shared-volume-refused-before-warning-clear")

    storage_persistence()


def storage_persistence():
    """Unauthenticated fresh-volume persistence; no account credential access."""
    identity = read(ROOT / "native-operation.json")["id"]
    service = Deployments(Store(ROOT / "native/state"))
    recipe = payload(service, identity)
    maintenance = AppMaintenance(service)
    info = maintenance.container(identity, recipe, "seerr")
    before = maintenance.resources(identity, recipe, "seerr", info)
    node(info, "require('fs').writeFileSync('/app/config/stackarr-persistence-sentinel','Original isolated Seerr settings')")
    digest = "const fs=require('fs'),c=require('crypto');console.log(c.createHash('sha256').update(fs.readFileSync('/app/config/settings.json')).digest('hex'))"
    settings_hash = node(info, digest)
    base = ["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(service.store.root / "deployments" / identity / "compose.json")]
    command([*base, "up", "-d", "--force-recreate", "--no-deps", "--pull", "never", "seerr"])
    assert appdata(PORT)["appData"] is True
    current = maintenance.container(identity, recipe, "seerr")
    assert current["Id"] != info["Id"] and maintenance.resources(identity, recipe, "seerr", current) == before
    assert node(current, digest) == settings_hash
    assert node(current, "console.log(require('fs').readFileSync('/app/config/stackarr-persistence-sentinel','utf8'))") == "Original isolated Seerr settings"
    assert node(current, "console.log(require('fs').statSync('/app/config/db/db.sqlite3').isFile())") == "true"
    prepare(service, identity, recipe)
    record("recreated-container-retains-settings-database-and-warning-fix", same_volume=True,
           same_settings_hash=True, database_present=True, no_account_credential_access=True)
    command([*base, "down"])


def lab_token():
    # This purpose-created authorization checkpoint belongs to the earlier
    # disposable SSO lab. Never read an existing application's account database.
    source = Path("test-results/docker-seerr-plex-maintenance-20261018").resolve()
    key = source / "package-state/controller/state/secrets.key"
    sealed = source / "plex-login.enc"
    assert key.is_file() and sealed.is_file()
    return json.loads(Fernet(key.read_bytes()).decrypt(sealed.read_bytes()))["token"]


def persistence():
    # Save a real Plex owner and setting through Seerr's normal API, then
    # replace only its lab container and verify a fresh login and unchanged data.
    identity = read(ROOT / "native-operation.json")["id"]
    service = Deployments(Store(ROOT / "native/state"))
    recipe = payload(service, identity)
    maintenance = AppMaintenance(service)
    info = maintenance.container(identity, recipe, "seerr")
    before = maintenance.resources(identity, recipe, "seerr", info)
    token = lab_token()
    with httpx.Client(base_url="http://127.0.0.1:" + str(PORT), trust_env=False, timeout=30) as client:
        response = client.post("/api/v1/auth/plex", json={"authToken": token})
        assert response.status_code == 200
        user = response.json()
        settings = client.get("/api/v1/settings/main").json()
        settings["applicationTitle"] = "Stackarr storage preservation lab"
        assert client.post("/api/v1/settings/main", json=settings).status_code == 200
    settings_hash = node(info, "const c=require('crypto'),fs=require('fs');console.log(c.createHash('sha256').update(fs.readFileSync('/app/config/settings.json')).digest('hex'))")
    base = ["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(service.store.root / "deployments" / identity / "compose.json")]
    command([*base, "up", "-d", "--force-recreate", "--no-deps", "--pull", "never", "seerr"])
    assert appdata(PORT)["appData"] is True
    current = maintenance.container(identity, recipe, "seerr")
    assert current["Id"] != info["Id"] and maintenance.resources(identity, recipe, "seerr", current) == before
    with httpx.Client(base_url="http://127.0.0.1:" + str(PORT), trust_env=False, timeout=30) as client:
        assert client.post("/api/v1/auth/plex", json={"authToken": token}).json()["id"] == user["id"]
        assert client.get("/api/v1/settings/main").json()["applicationTitle"] == "Stackarr storage preservation lab"
    assert node(current, "const c=require('crypto'),fs=require('fs');console.log(c.createHash('sha256').update(fs.readFileSync('/app/config/settings.json')).digest('hex'))") == settings_hash
    prepare(service, identity, recipe)
    write(ROOT / "native-private.json", {"owner": user["id"], "settings_hash": settings_hash})
    record("recreated-container-retains-owner-settings-and-warning-fix", settings_volume_retained=True, media_files=len(read(ROOT / "media-before.json")))
    command([*base, "down"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["native", "storage_persistence", "persistence"])
    parser.add_argument("--allow-test-authorization-reuse", action="store_true", help="Requires explicit human approval for this credential transfer")
    args = parser.parse_args()
    if args.phase == "persistence" and not args.allow_test_authorization_reuse:
        parser.error("Ask the owner before reusing the earlier disposable lab's authorization. Use storage_persistence for a credential-free check.")
    globals()[args.phase]()
