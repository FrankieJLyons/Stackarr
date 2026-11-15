"""Exercise the shipped security image with only disposable synthetic lab state."""

import argparse
import copy
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.app_maintenance import AppMaintenance
from stackarr.bundled_images import catalog
from stackarr.deployment import Deployments
from stackarr.deployment_check import load_receipt
from stackarr.self_update import package, read, write
from stackarr.store import Store
from stackarr.updates import Updates
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import bootstrap, command
from tools.docker_seerr_guidance_check import appdata
from tools.docker_seerr_guidance_package_check import cleanup, wait
from tools.docker_seerr_permissions_fix_check import ROOT, exercise, lab
from tools.docker_seerr_permissions_package_check import fingerprint

PACKAGE = Path("test-results/seerr-permissions-package-extracted-r4/Stackarr-Docker-Seerr-Permissions-Preview-20261019-r4").resolve()
ARCHIVE = Path("dist") / (PACKAGE.name + ".zip")
LAB = ROOT / "packaged"
STATE = LAB / "package-state/controller/state"
APP = "http://127.0.0.1:5055"


def preserved():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()


def owned():
    service = Deployments(Store(STATE))
    identity = read(LAB / "operation.json")["id"]
    recipe = load_receipt(service, identity)
    maintenance = AppMaintenance(service)
    info = maintenance.container(identity, recipe, "seerr")
    return service, identity, recipe, maintenance, info


def admin():
    info = owned()[-1]
    settings = json.loads(command(["exec", info["Id"], "head", "-c", "131072", "/app/config/settings.json"]))
    return httpx.Client(base_url=APP, trust_env=False, timeout=30, headers={"X-Api-Key": settings["main"]["apiKey"]})


@contextmanager
def owner():
    origin = "http://localhost:" + str(read(LAB / "installation.json")["port"])
    with httpx.Client(base_url=origin, trust_env=False, timeout=240, headers={"Origin": origin}) as client:
        response = client.post("/api/login", json={"password": read(LAB / "access.json")["owner_password"]})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        yield client


def verify():
    PACKAGE.parent.mkdir(exist_ok=True)
    assert not PACKAGE.exists()
    with zipfile.ZipFile(ARCHIVE) as bundle:
        assert len(bundle.namelist()) == 9
        assert all(len(Path(name).parts) == 2 and Path(name).parts[0] == PACKAGE.name for name in bundle.namelist())
        bundle.extractall(PACKAGE.parent)
    manifest = package(PACKAGE)
    assert manifest["bundled_app_images"][0]["image"] == catalog()["seerr"]["image"]
    report = ROOT / "frozen-smoke.json"
    with tempfile.TemporaryDirectory(prefix="stackarr-security-smoke-") as directory:
        result = subprocess.run([str(PACKAGE / "StackarrPreview.exe"), "--self-test-report", str(report)], cwd=directory,
            timeout=120, creationflags=subprocess.CREATE_NO_WINDOW,
            env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1", "STACKARR_PACKAGE_ROOT": str(PACKAGE)})
    assert result.returncode == 0 and read(report)["passed"] and len(read(report)["checks"]) == 22
    write(ROOT / "package-verification.json", {"package": PACKAGE.name, "zip_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        "payloads": len(manifest["files"]), "frozen_checks": 22, "bundled_security_image": manifest["bundled_app_images"][0]["image"]})
    print("Complete ZIP verified; 22 frozen checks passed outside the checkout.", flush=True)


def install():
    assert read(lab.ROOT / "native-cleaned.json")["containers_network_removed"]
    LAB.mkdir(exist_ok=True)
    # Prove first launch loads the app from the shipped archive, without relying
    # on a developer's cached image or a registry hosting this private build.
    image = catalog()["seerr"]["image"]
    assert not command(["ps", "-a", "-q", "--filter", "ancestor=" + image])
    command(["image", "rm", image])
    installation, origin = bootstrap(PACKAGE, LAB, 29360, 29120)
    write(LAB / "installation.json", installation)
    assert image in json.loads(command(["image", "inspect", image]))[0]["RepoDigests"]
    invite = command(["compose", "--project-name", installation["project"], "-f", str(LAB / "package-state/compose.json"),
        "exec", "-T", "stackarr", "stackarr", "setup-link"])
    password = secrets.token_urlsafe(32)
    write(LAB / "access.json", {"owner_password": password})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(120000)
        page.goto(invite)
        page.get_by_label("Create a password", exact=True).fill(password)
        page.get_by_role("button", name="Continue to setup", exact=False).click()
        page.locator("#setup-seerr").check()
        page.get_by_role("button", name="Save & continue", exact=False).click()
        expect(page.get_by_text("No media folder needed", exact=True)).to_be_visible()
        page.get_by_role("button", name="Save & continue", exact=False).click()
        page.get_by_role("button", name="Review installation", exact=True).click()
        with page.expect_response(lambda r: r.url.endswith("/api/deployments/install")) as installed:
            page.get_by_role("button", name="Download & install these apps", exact=True).click()
        assert installed.value.status == 202
        identity = installed.value.json()["id"]
        write(LAB / "operation.json", {"id": identity})
        wait(page, origin, identity)
        page.screenshot(path=str(LAB / "packaged-install.png"), full_page=True)
        browser.close()
    _, _, recipe, _, info = owned()
    assert recipe["apps"] == ["seerr"] and recipe["compose"]["services"]["seerr"]["image"] == image
    assert appdata(5055)["appData"] is True
    assert len(info["Mounts"]) == 1 and info["Mounts"][0]["Type"] == "volume"
    assert httpx.get(APP + "/api/v1/status", trust_env=False).json()["version"] == "3.5.0-stackarr.1"
    preserved()
    write(LAB / "install-result.json", {"passed": True, "loaded_missing_security_image_from_zip": True, "no_media_mounts": True,
        "fresh_config_volume": info["Mounts"][0]["Name"], "no_storage_warning": True})
    print("Frozen package installed patched Seerr from an absent image cache; no media folder or build needed.", flush=True)


def seed():
    _, identity, recipe, maintenance, info = owned()
    source = lab.PROJECT + "_seerr-config"
    assert json.loads(command(["volume", "inspect", source]))[0]["Labels"]["com.docker.compose.project"] == lab.PROJECT
    maintenance.resources(identity, recipe, "seerr", info)
    # Resource helper shapes differ across old releases; derive the exact saved
    # owned volume from the inspected container after the ownership check.
    target = next(m["Name"] for m in info["Mounts"] if m["Destination"] == "/app/config")
    assert target == "stackarr-owned-" + identity + "_seerr-config"
    assert not command(["ps", "-a", "-q", "--filter", "volume=" + source])
    command(["stop", "--timeout", "60", info["Id"]])
    script = """import json,pathlib,sqlite3,shutil,os
s=pathlib.Path('/source');t=pathlib.Path('/target')
with sqlite3.connect(s/'db/db.sqlite3') as db: assert db.execute('SELECT plexId FROM user WHERE id=1').fetchone()[0]==9700101
if (t/'db/db.sqlite3').exists():
 with sqlite3.connect(t/'db/db.sqlite3') as db: assert db.execute('SELECT COUNT(*) FROM user').fetchone()[0]==0
assert not (s/'settings.json').is_symlink() and not (s/'db/db.sqlite3').is_symlink()
assert not (t/'settings.json').is_symlink() and not (t/'db').is_symlink()
(t/'db').mkdir(exist_ok=True)
shutil.copy2(s/'settings.json',t/'settings.json')
source=sqlite3.connect('file:/source/db/db.sqlite3?mode=ro',uri=True)
with sqlite3.connect(t/'db/db.sqlite3') as destination: source.backup(destination)
source.close()
for p in (t,t/'db',t/'settings.json',t/'db/db.sqlite3'): os.chown(p,1000,1000,follow_symlinks=False)
print('Only synthetic fixture identities seeded into fresh owned lab volume.')
"""
    dashboard = package(PACKAGE)["image_id"]
    command(["run", "--rm", "--network", "none", "--user", "0:0", "--entrypoint", "python",
        "--mount", "type=volume,src=" + source + ",dst=/source,readonly",
        "--mount", "type=volume,src=" + target + ",dst=/target", dashboard, "-c", script])
    command(["start", info["Id"]])
    assert appdata(5055)["appData"] is True
    with owner() as client:
        response = client.post(f"/api/deployments/{identity}/finish-connecting")
        assert response.status_code == 200
    write(LAB / "fixture-seeded.json", {"synthetic_plex_owner_only": True, "no_real_authorization_transferred": True,
        "source_read_only": source, "fresh_destination": target})
    write(LAB / "fingerprint-before.json", fingerprint(info))
    preserved()


def matrix():
    people = read(lab.ROOT / "matrix-private.json")
    with admin() as owner_api:
        results = exercise(lambda: httpx.Client(base_url=APP, trust_env=False, timeout=30), owner_api, people)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(APP + "/login")
        if not page.get_by_placeholder("Email Address", exact=True).is_visible():
            page.get_by_role("button", name="Use your Seerr account", exact=True).click()
        page.get_by_placeholder("Email Address", exact=True).fill("manager-fix@example.invalid")
        page.get_by_placeholder("Password", exact=True).fill(people["manager"]["password"])
        with page.expect_response(lambda r: r.url.endswith("/api/v1/auth/local")) as signed:
            page.get_by_test_id("local-signin-button").click()
        assert signed.value.status == 200
        target = people["admin"]["id"]
        assert page.request.put(APP + f"/api/v1/user/{target}", data={"permissions": 32}).status == 403
        assert page.request.put(APP + "/api/v1/user", data={"ids": [people["guest"]["id"], target], "permissions": 0}).status == 403
        assert page.request.post(APP + f"/api/v1/user/{target}/settings/permissions", data={"permissions": 32}).status == 403
        _, identity, _, _, info = owned()
        command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(STATE / "deployments" / identity / "compose.json"),
            "up", "-d", "--force-recreate", "--no-deps", "--pull", "never", "seerr"])
        assert appdata(5055)["appData"] is True
        assert page.request.get(APP + "/api/v1/auth/me").json()["id"] == people["manager"]["id"]
        assert page.request.put(APP + f"/api/v1/user/{target}", data={"permissions": 32}).status == 403
        assert owned()[-1]["Id"] != info["Id"]
        page.goto(APP + "/users")
        page.screenshot(path=str(LAB / "manager-protected-users.png"), full_page=True)
        browser.close()
    assert fingerprint(owned()[-1]) == read(LAB / "fingerprint-before.json")
    write(LAB / "matrix-result.json", {"passed": True, "checks": results, "browser_login": True,
        "three_alternate_routes_denied_in_real_browser_session": True, "cookie_and_protection_survive_replacement": True,
        "owner_authorization_and_settings_unchanged": True})
    preserved()
    print("Packaged permission matrix and browser login/replacement passed.", flush=True)


def wait_action(identity):
    for _ in range(600):
        with sqlite3.connect(STATE / "stackarr.db") as db:
            row = db.execute("SELECT state,message FROM deployment_actions WHERE id=?", (identity,)).fetchone()
        if row and row[0] not in {"queued", "running"}:
            assert row[0] == "succeeded", "Packaged maintenance failed; private journal retained."
            return
        time.sleep(.5)
    raise AssertionError("Packaged maintenance did not finish")


def update():
    service, identity, recipe, _, info = owned()
    # Construct a disposable previous-release fixture. This is not adoption or a
    # product rollback: no existing user's app/receipt is edited or copied.
    old = copy.deepcopy(recipe)
    old["compose"]["services"]["seerr"]["image"] = read(Path("platform/seerr/upstream.lock.json").resolve())["base"]
    command(["stop", "--timeout", "60", info["Id"]])
    write(STATE / "deployments" / identity / "compose.json", old["compose"])
    with service.store.db() as db:
        db.execute("UPDATE deployments SET payload=? WHERE id=?", (json.dumps(old), identity))
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(STATE / "deployments" / identity / "compose.json"),
        "up", "-d", "--force-recreate", "--no-deps", "--pull", "never", "seerr"])
    assert appdata(5055)["appData"] is True
    assert httpx.get(APP + "/api/v1/status", trust_env=False).json()["version"] == "3.5.0"
    checkpoint = Updates(service).protected(old, "seerr", Updates(service).credentials(identity, old, "seerr"))
    before = fingerprint(owned()[-1])
    with owner() as client:
        review = client.post(f"/api/deployments/{identity}/update-review", json={"app": "seerr", "action": "update"})
        assert review.status_code == 200, "Packaged security update review failed."
        assert review.json()["target_version"] == "3.5.0-stackarr.1"
        approved = client.post("/api/deployments/actions/apply", json={"review_token": review.json()["review_token"]})
        assert approved.status_code == 202
        wait_action(approved.json()["id"])
    service, _, current, _, info = owned()
    assert current["compose"]["services"]["seerr"]["image"] == catalog()["seerr"]["image"]
    assert httpx.get(APP + "/api/v1/status", trust_env=False).json()["version"] == "3.5.0-stackarr.1"
    updates = Updates(service)
    assert updates.protected(current, "seerr", updates.credentials(identity, current, "seerr")) == checkpoint
    assert fingerprint(info) == before
    with admin() as owner_api:
        people = read(lab.ROOT / "matrix-private.json")
        results = exercise(lambda: httpx.Client(base_url=APP, trust_env=False, timeout=30), owner_api, people)
    write(LAB / "update-result.json", {"passed": True, "previous_version": "3.5.0", "candidate": "3.5.0-stackarr.1",
        "normal_packaged_review_approval_and_worker": True, "settings_users_requests_owner_authorization_retained": True,
        "post_update_permission_checks": len(results)})
    preserved()
    print("Packaged 3.5.0 security update passed authenticated checks and retained users, requests and authorization.", flush=True)


def finalize():
    cleanup(LAB, read(LAB / "installation.json"), read(LAB / "operation.json")["id"])
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
    fresh = json.loads(command(["exec", read(ROOT / "main-before.json")["dashboard"], "python", "-c", script]))
    assert len(fresh) == 9 and all(fresh.values())
    write(ROOT / "main-authenticated-monitoring.json", fresh)
    assert set(read(ROOT / "volumes-before.json")) <= set(command(["volume", "ls", "-q"]).split())
    write(ROOT / "acceptance.json", {"passed": True, "delegated_admin_release_gate_passed": True,
        "package": PACKAGE.name, "external_plex_accounts_simulated": True, "no_real_credentials_transferred": True,
        "existing_nine_apps_settings_credentials_backup_policy_and_16_media_files_preserved": True,
        "fresh_nine_app_monitoring": True, "lab_containers_networks_removed_data_retained": True,
        "packaged_install_matrix_browser_replacement_and_security_update_passed": True})
    print("Security fix accepted; existing nine apps/settings/media preserved; all lab containers/networks removed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["verify", "install", "seed", "matrix", "update", "finalize"])
    globals()[parser.parse_args().phase]()
