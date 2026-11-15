"""Opt-in browser-to-Docker install check using fresh, isolated app deployments."""

import argparse
import json
import re
import socket
import threading
import time
import uuid
from pathlib import Path

import httpx
import uvicorn
from playwright.sync_api import expect, sync_playwright

from stackarr.pairing import PairingGate
from stackarr.server import create_app
from tools.browser_check import capture_browser_failure, open_task_group, resume_setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Also install fresh Arr and qBittorrent apps and verify credential handoff")
    parser.add_argument("--plex", action="store_true", help="Also verify a fresh, unclaimed Plex installation without signing into an account")
    parser.add_argument("--companions", action="store_true", help="Also install isolated Tautulli, Uptime Kuma and Cleanuparr test instances")
    parser.add_argument("--only", choices=("seerr", "tautulli", "kuma", "cleanuparr"), help="Test exactly one app, including its reviewed stop/start actions")
    args = parser.parse_args()
    if args.only and (args.full or args.plex or args.companions):
        parser.error("--only cannot be combined with group installation options")
    root = Path("test-results") / ("wizard-install-" + uuid.uuid4().hex[:12])
    root.mkdir(parents=True)
    ports = {"Seerr": 35055}
    if args.companions:
        ports.update(Tautulli=38181, **{"Uptime Kuma": 33001, "Cleanuparr": 31011})
    if args.full:
        ports.update(Sonarr=38989, Radarr=37878, Prowlarr=39696, qBittorrent=38080)
    if args.plex:
        ports["Plex"] = 42450
    lifecycle_key = args.only or "seerr"
    lifecycle_name, lifecycle_port = {
        "seerr": ("Seerr", 35055), "tautulli": ("Tautulli", 38181),
        "kuma": ("Uptime Kuma", 33001), "cleanuparr": ("Cleanuparr", 31011),
    }[lifecycle_key]
    if args.only:
        ports = {lifecycle_name: lifecycle_port}
    if args.full or args.plex:
        (root / "media").mkdir()
        (root / "media" / "preserve.txt").write_text("Synthetic media sentinel. Keep unchanged.", encoding="utf-8")
    for port in ports.values():
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", port))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    pairing = PairingGate()
    media_roots = [{'path': str((root / 'media').resolve()), 'host_path': str((root / 'media').resolve()), 'label': 'Test media'}] if args.full or args.plex else []
    app = create_app(root / "state", origin=origin, pairing=pairing, host_checks=True, host_install=True, media_roots=media_roots)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as playwright, capture_browser_failure(lambda: page, root):
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(origin)
            page.get_by_role("button", name="Request setup approval").click()
            page.get_by_text("Your code:", exact=False).wait_for()
            assert pairing.approve(pairing.display_code())
            page.get_by_label("Create a password", exact=True).fill("synthetic installation test password")
            page.get_by_role("button", name="Continue to setup").click()
            page.get_by_role("button", name="Review app choices", exact=True).click()
            page.get_by_role('button', name='Choose my own', exact=True).click()
            page.get_by_text('Advanced port settings', exact=True).click()
            page.get_by_label("Port selection", exact=True).select_option("custom")
            for name, port in ports.items():
                page.get_by_label(name, exact=True).check()
                page.get_by_label(name + " port", exact=True).fill(str(port))
            page.get_by_role("button", name="Check for conflicts", exact=True).click()
            expect(page.locator("#setup-port-status")).to_contain_text("Checked on the installation computer")
            page.get_by_role("button", name="Save & continue").click()
            if args.full or args.plex:
                page.get_by_role("button", name=re.compile(r'^Choose (?:another )?folder…$')).click()
                page.get_by_role("button", name="Test media", exact=True).click()
                page.get_by_role("button", name="Use this folder", exact=True).click()
            page.get_by_role("button", name="Save & continue").click()
            with page.expect_response("**/api/deployments/review", timeout=90000) as review:
                page.get_by_role("button", name="Review installation", exact=True).click()
            assert review.value.ok, f"Installation review failed: {review.value.status}: {review.value.json().get('detail')}"
            page.get_by_role("button", name="Download & install these apps", exact=True).click(timeout=90000)
            if args.full:
                page.get_by_role("heading", name=re.compile("^(Waiting to start|Setting up your apps)$")).wait_for(timeout=30000)
                interruption = {"sent": False}
                def drop_one_status_request(route):
                    if route.request.method == "GET" and not interruption["sent"]:
                        interruption["sent"] = True
                        route.abort("connectionreset")
                    else:
                        route.continue_()
                page.route("**/api/deployments", drop_one_status_request)
            page.get_by_role("heading", name="Apps installed — finish setup", exact=True).or_(page.get_by_role("heading", name="Installation needs attention", exact=True)).wait_for(timeout=1100000)
            page.screenshot(path=str(root / "installed.png"), full_page=True)
            assert app.state.deployments.rows()[0]["state"] == "needs-setup", app.state.deployments.rows()
            page.reload()
            resume_setup(page)
            page.get_by_role("button", name="Review app choices", exact=True).click()
            page.get_by_role("heading", name="Apps installed — finish setup", exact=True).wait_for()
            if "Seerr" in ports:
                open_task_group(page, 'accounts')
                page.get_by_role("button", name="Finish connecting", exact=True).click()
                expect(page.locator('section').filter(has=page.get_by_role("heading", name="Finish connecting your apps")).locator('[role="status"]')).to_contain_text("complete its account setup", timeout=30000)
            else:
                expect(page.get_by_role("heading", name="Finish connecting your apps", exact=True)).to_have_count(0)
            assert not app.state.store.secret("plex") and not app.state.store.secret("seerr")
            if args.full:
                assert interruption["sent"]
            assert not errors, errors
            operations = app.state.deployments.rows()
            assert len(operations) == 1 and operations[0]["state"] == "needs-setup"
            config = app.state.store.config()[1]
            expected_apps = set(payload_key for payload_key, entry in config.integrations.items() if entry.enabled)
            assert len(expected_apps) == len(ports), "Unselected integrations must remain disabled"
            assert config.integrations[lifecycle_key].url == f"http://127.0.0.1:{lifecycle_port}"
            assert config.integrations["plex"].enabled == args.plex
            if args.full or args.plex:
                assert (root / "media" / "preserve.txt").read_text(encoding="utf-8") == "Synthetic media sentinel. Keep unchanged."
            if args.plex:
                response = httpx.get(config.integrations["plex"].url + "/status/sessions", headers={"Accept": "application/json"}, trust_env=False, timeout=10)
                response.raise_for_status()
                assert response.json()["MediaContainer"]["size"] == 0
                with app.state.store.db() as db:
                    identity, raw = db.execute("SELECT id,payload FROM deployments").fetchone()
                payload = json.loads(raw)
                name = app.state.deployments.owned_container(identity, payload, "plex")
                info = json.loads(app.state.deployments._call(["--context", payload["context"]["name"], "inspect", name]))[0]
                media_mount = next(m for m in info["Mounts"] if m["Destination"] == "/data")
                assert media_mount["RW"] is False
            if args.full:
                assert config.storage.data_root == str((root / "media").resolve())
                for key, folder in (("sonarr", "tv"), ("radarr", "movies")):
                    assert (root / "media" / "media" / folder).is_dir()
                    response = httpx.get(config.integrations[key].url + "/api/v3/rootfolder", headers={"X-Api-Key": app.state.store.secret(key)["api_key"]}, trust_env=False)
                    response.raise_for_status()
                    assert [row["path"] for row in response.json()] == ["/data/media/" + folder]
                open_task_group(page, 'accounts')
                page.get_by_text("Your installed app logins", exact=True).click()
                page.get_by_label("App login", exact=True).select_option('qbittorrent')
                page.get_by_label("Stackarr owner password", exact=True).fill("synthetic installation test password")
                page.get_by_role("button", name="Show generated login", exact=True).click()
                expect(page.get_by_label("Generated qBittorrent password", exact=True)).to_be_visible()
                assert page.get_by_label("Generated qBittorrent password", exact=True).input_value() == app.state.store.secret("qbittorrent")["password"]
                page.get_by_role("button", name="Hide login", exact=True).click()
                expect(page.locator("#generated-login-output")).to_be_hidden()
                assert not page.locator("#generated-login-output").inner_text()
                assert set(app.state.store.secret_names()) == {"sonarr", "radarr", "prowlarr", "qbittorrent"}
                open_task_group(page, 'connections')
                page.get_by_role("button", name="Preview app connections", exact=True).click()
                expect(page.locator("#wiring-output")).to_contain_text("Stackarr qBittorrent", timeout=60000)
                assert page.locator("#wiring-output li").count() == 4
                page.get_by_role("button", name="Apply reviewed changes", exact=True).click()
                expect(page.locator("#wiring-output")).to_contain_text("created", timeout=60000)
                assert page.locator("#wiring-output li").count() == 4
                assert all("created" in text for text in page.locator("#wiring-output li").all_text_contents())
                open_task_group(page, 'connections')
                page.get_by_role("button", name="Preview app connections", exact=True).click()
                expect(page.locator("#wiring-output")).to_contain_text("No new connection changes are ready. Check any notices below.", timeout=60000)
                page.screenshot(path=str(root / "connections.png"), full_page=True)
            page.locator('button[data-view="settings"]').click()
            page.locator('button[data-settings-section="maintenance"]').click()
            page.get_by_role("button", name="Check installation 1", exact=True).click()
            expect(page.locator('[id^="install-check-"]')).to_contain_text("Read-only check", timeout=60000)
            check_rows = page.locator('[id^="install-check-"] li')
            assert check_rows.count() == len(ports)
            assert all(" · running" in text for text in check_rows.all_text_contents()), "Installed container drift check failed"
            page.screenshot(path=str(root / "installation-check.png"), full_page=True)
            before_config = app.state.store.config()
            with app.state.store.db() as db:
                identity, raw = db.execute("SELECT id,payload FROM deployments").fetchone()
            payload = json.loads(raw)
            from stackarr.deployment_check import inspect_container

            original = {key: inspect_container(app.state.deployments, identity, payload, key)["Id"] for key in payload["apps"]}
            page.get_by_role("button", name=f"Review stop {lifecycle_name}", exact=True).click()
            expect(page.locator('#lifecycle-review')).to_contain_text("may force it to stop")
            page.get_by_role("button", name="Cancel", exact=True).click()
            assert inspect_container(app.state.deployments, identity, payload, lifecycle_key)["State"]["Running"]
            page.get_by_role("button", name=f"Review stop {lifecycle_name}", exact=True).click()
            page.get_by_role("button", name="Stop app", exact=True).click()
            expect(page.locator('#lifecycle-history')).to_contain_text(f"{lifecycle_name} stopped.", timeout=70000)
            for key in payload["apps"]:
                info = inspect_container(app.state.deployments, identity, payload, key)
                assert info["Id"] == original[key]
                assert info["State"]["Running"] == (key != lifecycle_key)
            page.get_by_role("button", name="Check installation 1", exact=True).click()
            page.get_by_role("button", name=f"Review start {lifecycle_name}", exact=True).click()
            page.get_by_role("button", name="Start app", exact=True).click()
            expect(page.locator('#lifecycle-history')).to_contain_text(f"{lifecycle_name} started.", timeout=70000)
            expect(page.locator('[id^="install-check-"]')).to_contain_text("Check this installation again for current status.")
            assert page.get_by_role("button", name=f"Review start {lifecycle_name}", exact=True).count() == 0
            assert app.state.store.config() == before_config
            assert inspect_container(app.state.deployments, identity, payload, lifecycle_key)["Id"] == original[lifecycle_key]
            if args.full or args.plex:
                assert (root / "media" / "preserve.txt").read_text(encoding="utf-8") == "Synthetic media sentinel. Keep unchanged."
            page.screenshot(path=str(root / "lifecycle.png"), full_page=True)
            (root / "report.json").write_text(json.dumps({"passed": True, "apps": list(ports), "credential_handoff_and_wiring": args.full, "unclaimed_plex_checked": args.plex, "owned_stop_start_checked": True, "scope": "Real browser, owner pairing, reviewed install, saved progress and optional-app isolation; Plex claim/playback and Seerr account setup remain separate", "errors": errors}, indent=2))
            print("Browser-to-Docker installation passed; report: " + str(root / "report.json"))
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        # Stop only completed test deployments; preserve their volumes and saved evidence.
        for row in app.state.deployments.rows():
            if row["state"] != "needs-setup":
                continue
            directory = app.state.store.root / "deployments" / row["id"]
            with app.state.store.db() as db:
                payload = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (row["id"],)).fetchone()[0])
            from stackarr.docker_names import app_project

            app.state.deployments._call(["--context", payload["context"]["name"], "compose", "--project-name",
                app_project(row['id'], payload), "-f", str(directory / "compose.json"), "down"], timeout=60)
        listener.close()


if __name__ == "__main__":
    main()
