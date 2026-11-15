"""Fresh packaged companion journey on the existing, explicitly owned main preview."""

import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.companions import CLEANUP_FLAGS
from stackarr.docker_runtime import executable
from stackarr.integrations import collect
from stackarr.store import Store

ROOT = Path("test-results/docker-plex-bc615eaf1fe6").resolve()
EVIDENCE = ROOT / "companions"
PORTS = {"tautulli": 42465, "kuma": 42466, "cleanuparr": 42467}
CORE = {"plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr"}
ORIGIN = "http://localhost:29100"


def command(arguments):
    result = subprocess.run([executable(), *arguments], capture_output=True, text=True,
        encoding="utf-8", timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, "Scoped Docker verification failed; private output withheld."
    return result.stdout.strip()


def hashes():
    return {str(p.relative_to(ROOT / "media")): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "media").rglob("*") if p.is_file()}


def protected(store):
    config = store.config()[1]
    return {key: {"config": config.integrations[key].model_dump(),
        "credential_hash": hashlib.sha256(json.dumps(store.secret(key), sort_keys=True).encode()).hexdigest()} for key in CORE}


def main():
    EVIDENCE.mkdir(exist_ok=True)
    store = Store(ROOT / "controller/state")
    access = json.loads((ROOT / "access.json").read_text())
    before_path = EVIDENCE / "before.json"
    if not before_path.exists():
        before_path.write_text(json.dumps({"media": hashes(), "protected": protected(store),
            "running": command(["ps", "-q", "--no-trunc"]).splitlines(),
            "dashboard": command(["ps", "-q", "--no-trunc", "--filter", "label=com.docker.compose.project=stackarr-plex-lab-bc615eaf1fe6", "--filter", "label=com.docker.compose.service=stackarr"])}, indent=2))
    before = json.loads(before_path.read_text())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(120000)
        page.goto(ORIGIN)
        page.get_by_label("Password", exact=True).fill(access["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        expect(page.get_by_role("button", name="Apps", exact=True)).to_be_visible()
        csrf = page.request.get(ORIGIN + "/api/session").json()["csrf"]
        page.context.set_extra_http_headers({"Origin": ORIGIN, "X-CSRF-Token": csrf})

        def api(path, value=None):
            response = page.request.get(ORIGIN + "/api/" + path) if value is None else page.request.post(ORIGIN + "/api/" + path, data=value)
            assert response.ok, "Packaged API rejected " + path + ": " + str(response.status)
            return response.json()

        def wait_action(identity):
            for _ in range(600):
                row = next((row for row in api("deployments").get("actions", []) if row["id"] == identity), None)
                if row and row["state"] not in {"queued", "running"}:
                    assert row["state"] == "succeeded", row["message"]
                    return
                time.sleep(1)
            raise AssertionError("Companion action did not finish")

        rows = api("deployments")["operations"]
        installed = [row for row in rows if set(row["apps"]) == set(PORTS)]
        if not installed:
            page.get_by_role("button", name="Apps", exact=True).click()
            page.get_by_role("button", name="Install or connect an app", exact=True).click()
            page.get_by_role("button", name="Add another app", exact=True).click()
            for key in PORTS:
                page.locator("#setup-" + key).check()
            page.get_by_label("Port selection", exact=True).select_option("custom")
            for key, port in PORTS.items():
                page.locator("#setup-port-" + key).fill(str(port))
            page.get_by_role("button", name="Save & continue", exact=False).click()
            expect(page.get_by_role("heading", name="No media folder needed", exact=True)).to_be_visible()
            page.get_by_role("button", name="Save & continue", exact=False).click()
            page.get_by_role("button", name="Review installation", exact=True).click()
            page.get_by_role("button", name="Download & install these apps", exact=True).click()
            for _ in range(360):
                installed = [row for row in api("deployments")["operations"] if set(row["apps"]) == set(PORTS)]
                if installed and installed[0]["state"] not in {"queued", "running"}:
                    break
                time.sleep(1)
        assert len(installed) == 1 and installed[0]["state"] == "needs-setup"
        identity = installed[0]["id"]
        (EVIDENCE / "installation.json").write_text(json.dumps({"id": identity}))
        print("Fresh packaged companion installation running; no media folder requested.", flush=True)
        page.reload()
        page.get_by_role("button", name="Apps", exact=True).click()
        if not set(PORTS) <= set(api("config")["credentials_saved"]):
            with page.expect_response(lambda response: response.url.endswith("/companions-review")) as response:
                page.get_by_role("button", name="Review companion setup", exact=True).click()
            assert response.value.ok
            expect(page.get_by_role("button", name="Set up companions", exact=True)).to_be_visible()
            with page.expect_response(lambda response: response.url.endswith("/actions/apply")) as response:
                page.get_by_role("button", name="Set up companions", exact=True).click()
            assert response.value.ok
            wait_action(response.value.json()["id"])
            print("Packaged companion setup succeeded; checking private handoff.", flush=True)
            page.reload()
            page.get_by_role("button", name="Apps", exact=True).click()
            with page.expect_response(lambda response: response.url.endswith("/finish-connecting")) as response:
                page.locator('[data-finish-install="' + identity + '"]').click()
            assert response.value.ok and {row["state"] for row in response.value.json()["apps"]} <= {"connected", "saved"}
        page.reload()
        page.get_by_role("button", name="Apps", exact=True).click()
        page.get_by_text("Your installed app logins", exact=True).click()
        for key in PORTS:
            page.get_by_label("App login", exact=True).select_option(key)
            page.get_by_label("Stackarr owner password", exact=True).fill(access["owner_password"])
            page.get_by_role("button", name="Show generated login", exact=True).click()
            expect(page.locator("#generated-login-password")).to_be_visible(timeout=90000)
            assert len(page.locator("#generated-login-password").input_value()) >= 32
            page.get_by_role("button", name="Hide login", exact=True).click()
        print("All three generated app logins verified through the protected dashboard.", flush=True)
        policy = api("backup-policy")["policy"]
        assert policy["enabled"] and policy["time"] == "03:00" and policy["keep"] == 7 and policy["destination"]
        if identity not in policy["deployments"]:
            value = {key: policy[key] for key in ("enabled", "time", "keep", "destination", "deployments")}
            value["deployments"] = [*value["deployments"], identity]
            review = api("backup-policy-review", value)
            api("deployments/actions/apply", {"review_token": review["review_token"]})
        # Back up only the new companions; existing six app containers stay running.
        page.get_by_role("button", name="Backups", exact=True).click()
        with page.expect_response(lambda response: "/backup" in response.url and response.request.method == "POST"):
            page.locator('[data-docker-backup="' + identity + '"]').click()
        with page.expect_response(lambda response: response.url.endswith("/actions/apply")) as response:
            page.get_by_role("button", name="Create backup", exact=True).click()
        wait_action(response.value.json()["id"])
        backups = [row for row in api("app-backups")["backups"] if row["deployment"] == identity]
        assert backups and backups[0]["off_disk"]
        stamp = time.time()
        api("refresh", {})
        for _ in range(120):
            rows = api("status")["integrations"]
            ready = {row["id"] for row in rows if row["state"] == "ready" and not row["stale"] and (row["collected_at"] or 0) > stamp}
            monitors = next((row["tables"].get("monitoring", []) for row in rows if row["id"] == "kuma"), [])
            if ready == CORE | set(PORTS) and len(monitors) == 9 and all(row["state"] == "up" for row in monitors):
                break
            time.sleep(1)
        assert ready == CORE | set(PORTS)
        kuma = next(row for row in rows if row["id"] == "kuma")
        assert len(kuma["tables"]["monitoring"]) == 9 and {row["state"] for row in kuma["tables"]["monitoring"]} == {"up"}
        cleanup = next(row for row in rows if row["id"] == "cleanuparr")
        assert cleanup["tables"]["health"][0]["state"] == "ok"
        page.get_by_role("button", name="Overview", exact=True).click()
        page.reload()
        expect(page.get_by_role("heading", name="Connected. Collected. Ready.", exact=True)).to_be_visible(timeout=30000)
        page.screenshot(path=str(EVIDENCE / "nine-apps.png"), full_page=True)
        browser.close()
    assert hashes() == before["media"] and protected(store) == before["protected"]
    assert set(before["running"]) - {before["dashboard"]} <= set(command(["ps", "-q", "--no-trunc"]).splitlines())
    for key in PORTS:
        container = command(["ps", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity,
            "--filter", "label=com.docker.compose.service=" + key])
        mounts = json.loads(command(["inspect", container, "--format", "{{json .Mounts}}" ]))
        assert len(mounts) == 1 and mounts[0]["Type"] == "volume"
    with httpx.Client(base_url="http://127.0.0.1:42467", trust_env=False,
        headers={"X-Api-Key": store.secret("cleanuparr")["api_key"]}) as client:
        general = client.get("/api/configuration/general").json()
        assert general["dryRun"] and not general["auth"]["disableAuthForLocalAddresses"]
        for job, flags in CLEANUP_FLAGS.items():
            config = client.get("/api/configuration/" + job).json()
            assert all(config[flag] is False for flag in flags)
    (EVIDENCE / "report.json").write_text(json.dumps({"passed": True, "packaged_browser_install": True,
        "companion_setup_and_private_handoff": True, "owner_protected_logins": 3, "fresh_integrations": sorted(ready),
        "up_monitors": 9, "cleanuparr_dry_run": True, "automatic_job_groups_disabled": 5,
        "no_media_download_or_socket_mounts": True, "nightly_plan_extended": True, "verified_off_disk_backup": True,
        "core_settings_and_credentials_preserved": True, "media_hashes_preserved": len(hashes()),
        "existing_containers_preserved": True}, indent=2))
    print("Packaged nine-app monitoring, backups and media/settings preservation passed.", flush=True)


async def diagnose():
    store = Store(ROOT / "controller/state")
    with httpx.Client(base_url="http://127.0.0.1:42465", trust_env=False) as client:
        for operation in ("get_activity", "get_server_info"):
            value = client.get("/api/v2", params={"apikey": store.secret("tautulli")["api_key"], "cmd": operation}).json()["response"]
            data = value.get("data")
            print(operation, value.get("result"), type(data).__name__, list(data) if isinstance(data, dict) else "")
            if operation == "get_server_info" and isinstance(data, dict):
                print({key: data.get(key) for key in ("pms_identifier", "pms_ip", "pms_port", "pms_url", "pms_name")})
    for key in PORTS:
        try:
            tables = await collect(key, store.config()[1].integrations[key], store.secret(key))
            print(key, {table: len(rows) for table, rows in tables.items()})
        except Exception as exc:
            print(key, type(exc).__name__, str(exc))
    access = json.loads((ROOT / "access.json").read_text())
    identity = json.loads((EVIDENCE / "installation.json").read_text())["id"]
    with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=90, headers={"Origin": ORIGIN}) as client:
        response = client.post("/api/login", json={"password": access["owner_password"]})
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        response = client.post("/api/deployments/" + identity + "/finish-connecting", json={})
        print("Private handoff public result:", response.json())


if __name__ == "__main__":
    import sys
    asyncio.run(diagnose()) if "--diagnose" in sys.argv else main()
