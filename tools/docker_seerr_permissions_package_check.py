"""Invited-user browser checks on the retained isolated Seerr r3 package."""

import argparse
import hashlib
import json
import secrets

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.app_maintenance import AppMaintenance
from stackarr.deployment import Deployments
from stackarr.self_update import read, write
from stackarr.store import Store
from tools.docker_folder_ports_check import bootstrap, command
from tools.docker_seerr_guidance_check import appdata, payload
from tools.docker_seerr_guidance_package_check import PACKAGE, cleanup
from tools.docker_seerr_guidance_package_check import ROOT as SETUP_ROOT
from tools.docker_seerr_permissions_check import ROOT, api, preserved

LAB = SETUP_ROOT / "packaged-seerr-r3"
PROOF = ROOT / "packaged"
STATE = LAB / "package-state/controller/state"
ORIGIN = "http://127.0.0.1:5055"


def owned():
    service = Deployments(Store(STATE))
    identity = read(LAB / "operation.json")["id"]
    recipe = payload(service, identity)
    maintenance = AppMaintenance(service)
    info = maintenance.container(identity, recipe, "seerr")
    return service, identity, recipe, maintenance, info


def settings(info):
    return json.loads(command(["exec", info["Id"], "head", "-c", "131072", "/app/config/settings.json"]))


def fingerprint(info):
    script = """const c=require('crypto'),s=require('sqlite3'),f=require('fs');
const db=new s.Database('/app/config/db/db.sqlite3',s.OPEN_READONLY);
db.get('SELECT id,userType,permissions,plexId,plexToken FROM user WHERE id=1',(e,r)=>{
if(e||!r){process.exitCode=1;}else{console.log(JSON.stringify({owner:c.createHash('sha256').update(JSON.stringify(r)).digest('hex'),settings:c.createHash('sha256').update(f.readFileSync('/app/config/settings.json')).digest('hex')}));}db.close();});"""
    return json.loads(command(["exec", info["Id"], "node", "-e", script]))


def admin():
    _, _, _, _, info = owned()
    return httpx.Client(base_url=ORIGIN, trust_env=False, timeout=30, headers={"X-Api-Key": settings(info)["main"]["apiKey"]})


def prepare():
    assert read(ROOT / "native-cleaned.json")["containers_network_removed"]
    assert not PROOF.exists()
    PROOF.mkdir()
    before = read(LAB / "installation.json")
    installation, _ = bootstrap(PACKAGE, LAB, before["port"], before["controller_port"])
    assert installation == before
    identity = read(LAB / "operation.json")["id"]
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f",
             str(STATE / "deployments" / identity / "compose.json"), "up", "-d", "--pull", "never"])
    assert appdata(5055)["appData"] is True
    _, _, recipe, maintenance, info = owned()
    saved = settings(info)
    assert saved["main"]["localLogin"] and saved["public"]["initialized"]
    assert recipe["compose"]["services"]["seerr"]["image"].startswith("ghcr.io/seerr-team/seerr@sha256:")
    write(PROOF / "before.json", {"fingerprint": fingerprint(info), "resources": maintenance.resources(identity, recipe, "seerr", info)})
    renew_invited()
    preserved()
    print("Packaged Seerr lab reopened; only a disposable invited account was added.", flush=True)


def renew_invited():
    password = secrets.token_urlsafe(32)
    with admin() as owner:
        created = api(owner, "POST", "/user", {"email": "packaged-invited@example.invalid", "username": "Packaged invited test", "password": password}, expected=201)
        api(owner, "PUT", "/user/" + str(created["id"]), {"username": "Packaged invited test", "permissions": 32})
    write(PROOF / "access-private.json", {"id": created["id"], "password": password})


def browser():
    access = read(PROOF / "access-private.json")
    with admin() as owner, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(60000)
        page.goto(ORIGIN + "/login")
        if not page.get_by_placeholder("Email Address", exact=True).is_visible():
            page.get_by_role("button", name="Use your Seerr account", exact=True).click()
        page.get_by_placeholder("Email Address", exact=True).fill("packaged-invited@example.invalid")
        page.get_by_placeholder("Password", exact=True).fill(access["password"])
        with page.expect_response(lambda response: response.url.endswith("/api/v1/auth/local")) as signed:
            page.get_by_test_id("local-signin-button").click()
        assert signed.value.status == 200
        assert page.request.get(ORIGIN + "/api/v1/auth/me").json()["id"] == access["id"]
        assert page.request.get(ORIGIN + "/api/v1/settings/main").status == 403
        assert page.request.post(ORIGIN + "/api/v1/user", data={"email": "forbidden@example.invalid", "password": secrets.token_urlsafe(32)}).status == 403
        api(owner, "PUT", "/user/" + str(access["id"]), {"username": "Packaged invited test", "permissions": 8})
        assert page.request.get(ORIGIN + "/api/v1/user/1/settings/permissions").status == 200
        api(owner, "PUT", "/user/" + str(access["id"]), {"username": "Packaged invited test", "permissions": 32})
        assert page.request.get(ORIGIN + "/api/v1/user/1/settings/permissions").status == 403
        _, identity, recipe, maintenance, info = owned()
        command(["compose", "--project-name", "stackarr-owned-" + identity, "-f",
                 str(STATE / "deployments" / identity / "compose.json"), "up", "-d", "--force-recreate", "--no-deps", "--pull", "never", "seerr"])
        assert appdata(5055)["appData"] is True
        current = maintenance.container(identity, recipe, "seerr")
        assert current["Id"] != info["Id"]
        before = read(PROOF / "before.json")
        assert maintenance.resources(identity, recipe, "seerr", current) == before["resources"]
        assert fingerprint(current) == before["fingerprint"]
        page.reload()
        assert page.request.get(ORIGIN + "/api/v1/auth/me").json()["id"] == access["id"]
        assert page.request.get(ORIGIN + "/api/v1/auth/me").json()["permissions"] == 32
        api(owner, "DELETE", "/user/" + str(access["id"]))
        assert page.request.get(ORIGIN + "/api/v1/auth/me").status == 403
        page.reload()
        page.wait_for_url("**/login**")
        expect(page.get_by_role("heading", name="Login with Seerr", exact=True)).to_be_visible()
        page.screenshot(path=str(PROOF / "invited-access-revoked.png"), full_page=True)
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=20) as retry:
            api(retry, "POST", "/auth/local", {"email": "packaged-invited@example.invalid", "password": access["password"]}, expected=403)
        assert fingerprint(current) == before["fingerprint"]
        assert api(owner, "GET", "/user/1")["permissions"] == 2
        browser.close()
    preserved()
    write(PROOF / "browser-report.json", {"passed": True, "real_seerr_browser_login": True, "no_admin_access": True,
        "live_permission_downgrade": True, "cookie_survives_container_replacement": True,
        "deleted_test_user_cookie_and_password_denied": True, "browser_returns_to_signin": True,
        "owner_fresh_plex_authorization_settings_and_volume_preserved": True, "upstream_image_unmodified": True})
    print("Packaged invited-user browser permissions, persistence and revocation passed.", flush=True)


def finalize():
    assert read(PROOF / "browser-report.json")["passed"]
    _, identity, _, _, info = owned()
    assert fingerprint(info) == read(PROOF / "before.json")["fingerprint"]
    installation = read(LAB / "installation.json")
    cleanup(LAB, installation, identity)
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
    findings = read(ROOT / "findings.json")["findings"]
    preserved()
    write(ROOT / "acceptance.json", {"execution_complete": True, "native_cases": len(read(ROOT / "native-report.json")["cases"]),
        "packaged_browser_passed": True, "external_plex_accounts_simulated_by_owner_choice": True,
        "existing_apps_settings_credentials_backup_policy_and_16_files_preserved": True, "fresh_nine_app_monitoring": True,
        "all_lab_containers_networks_removed_data_retained": True, "real_second_account_cloud_check_separate": True,
        "delegated_admin_findings": len(findings), "delegated_admin_release_gate_passed": not findings,
        "package": PACKAGE.name, "package_zip_sha256": hashlib.sha256((PACKAGE.parent.parent.parent / "dist" / (PACKAGE.name + ".zip")).read_bytes()).hexdigest()})
    print("Permission/revocation matrix complete; existing nine apps and media preserved; lab data retained.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "renew_invited", "browser", "finalize"])
    globals()[parser.parse_args().phase]()
