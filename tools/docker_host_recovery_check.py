"""Whole-host loss and fresh-process recovery, restricted to a newly created lab."""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from playwright.sync_api import expect, sync_playwright

from stackarr.app_backups import AppBackups
from stackarr.arr_logins import read as arr_login
from stackarr.companions import Companions, cleanup_safe
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.host_recovery import Recovery
from stackarr.onboarding import AppChoice, SetupDraft
from stackarr.ports import suggestions
from stackarr.store import Store
from stackarr.updates import Updates
from tools.docker_folder_ports_check import MAIN, bootstrap, command, hashes, main_settings, stop_lab


def api(client, path, value=None, method=None, status=200):
    result = client.request(method or ("GET" if value is None else "POST"), "/api/" + path, json=value)
    assert result.status_code == status, "Scoped API check failed: " + path + "/" + str(result.status_code)
    return result.json()


def wait_job(client, identity, installation=False):
    for _ in range(1800):
        rows = api(client, "deployments")["operations" if installation else "actions"]
        row = next((r for r in rows if r["id"] == identity), None)
        if row and row["state"] not in {"queued", "running"}:
            assert row["state"] == ("needs-setup" if installation else "succeeded"), row["message"]
            return row
        time.sleep(.5)
    raise AssertionError("Scoped recovery lab operation timed out")


@contextmanager
def login(origin, password):
    client = httpx.Client(base_url=origin, trust_env=False, timeout=210, headers={"Origin": origin})
    try:
        response = api(client, "login", {"password": password})
        client.headers["X-CSRF-Token"] = response["csrf"]
        yield client
    finally:
        client.close()


def setup_source(root, package):
    media = root / "source media – samples"
    # Original generated fixtures only, copied read-only from the earlier disposable import lab.
    if not media.exists():
        shutil.copytree(Path("test-results/docker-core-05cebfd84fd1/media").resolve(), media)
    installation, origin = bootstrap(package, root, 29210, 29080, media)
    state = root / "package-state"
    base = ["compose", "--project-name", installation["project"], "-f", str(state / "compose.json")]
    invitation = command([*base, "exec", "-T", "stackarr", "stackarr", "setup-link"])
    password = json.loads((root / "access.json").read_text())["owner_password"] if (root / "access.json").exists() else secrets.token_urlsafe(24)
    (root / "access.json").write_text(json.dumps({"owner_password": password, "dashboard": origin}))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(invitation)
        if page.get_by_label("Create a password", exact=True).count():
            page.get_by_label("Create a password", exact=True).fill(password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            expect(page.get_by_label("Choose available ports for me (recommended)")).to_be_visible()
        browser.close()
    identities = []
    with login(origin, password) as client:
        for apps in (["sonarr", "radarr", "prowlarr", "qbittorrent"], ["kuma"], ["plex", "seerr", "tautulli", "cleanuparr"]):
            existing = next((r for r in api(client, "deployments")["operations"] if set(r["apps"]) == set(apps) and r["state"] == "needs-setup"), None)
            if existing:
                identity = existing["id"]
                identities.append(identity)
                if "plex" not in apps:
                    result = api(client, "deployments/" + identity + "/finish-connecting", {})
                    assert {r["state"] for r in result["apps"]} == {"connected"}
                continue
            draft = api(client, "onboarding")
            ports = suggestions(SetupDraft(apps=apps, choices={k: AppChoice(port=43000 + n) for n, k in enumerate(apps)}))
            choices = {r["app"]: {"mode": "install", "port": r["port"]} for r in ports}
            api(client, "onboarding", {"revision": draft["revision"], "draft": {"step": 2, "apps": apps,
                "port_mode": "custom", "choices": choices, "data_root": str(media), "folder_root": 0}}, method="PUT")
            reviewed = api(client, "deployments/review", {})
            identity = api(client, "deployments/install", {"review_token": reviewed["review_token"]}, status=202)["id"]
            wait_job(client, identity, installation=True)
            identities.append(identity)
            if apps == ["kuma"]:
                review = api(client, "deployments/" + identity + "/companions-review", {})
                job = api(client, "deployments/actions/apply", {"review_token": review["review_token"]}, status=202)
                wait_job(client, job["id"])
            if "plex" not in apps:
                result = api(client, "deployments/" + identity + "/finish-connecting", {})
                assert {r["state"] for r in result["apps"]} == {"connected"}
        config = api(client, "config")
        (root / "source-config.json").write_text(json.dumps(config))
    host = Deployments(Store(state / "controller/state"))
    for identity in identities:
        payload = load_receipt(host, identity)
        for key in payload["apps"]:
            name = host.owned_container(identity, payload, key)
            target = payload["compose"]["services"][key]["volumes"][0]["target"]
            # A non-secret configuration file proves all nine independent volumes are restored byte-for-byte.
            command(["exec", name, "/bin/sh", "-c", "printf 'Original isolated recovery fixture' > " + target + "/stackarr-recovery-fixture.txt"])
    (root / "source.json").write_text(json.dumps({"installation": installation, "origin": origin,
        "identities": identities, "media": str(media)}, indent=2))
    print("Separate nine-app source lab installed; core logins and Kuma monitoring initialized.", flush=True)


def source_backup(root, package):
    source = json.loads((root / "source.json").read_text())
    password = json.loads((root / "access.json").read_text())["owner_password"]
    # Upgrade only this lab's dashboard/controller to the package under acceptance.
    state = root / "package-state"
    env = os.environ | {"STACKARR_RECOVERY_LAB_CONTROLLER": str(state / "controller")}
    stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_RECOVERY_LAB_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert stopped.returncode == 0
    bootstrap(package, root, source["installation"]["port"], source["installation"]["controller_port"])
    host = Deployments(Store(root / "package-state/controller/state"))
    cleanup_id = source["identities"][-1]
    companion = Companions(host)
    saved = companion.state(cleanup_id)
    record = saved["apps"].setdefault("cleanuparr", {"username": "stackarr", "password": secrets.token_urlsafe(32)})
    def save_cleanup():
        companion.save(cleanup_id, saved)
    save_cleanup()
    companion.cleanup(cleanup_id, load_receipt(host, cleanup_id), record, save_cleanup, companion.sources())
    revision, config = host.store.config()
    host.store.save(config, revision, {"cleanuparr": {"api_key": record["api_key"]}})
    updater = Updates(host)
    protected = {}
    for identity in source["identities"]:
        payload = load_receipt(host, identity)
        for key in payload["apps"]:
            if key in {"sonarr", "radarr", "prowlarr", "qbittorrent"}:
                protected[key] = updater.protected(payload, key, host.store.secret(key))
    (root / "protected.json").write_text(json.dumps(protected))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(120000)
        page.goto(source["origin"])
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Backups", exact=True).click()
        expect(page.get_by_role("button", name="Review backup plan", exact=True)).to_be_visible(timeout=120000)
        with page.expect_response(lambda r: r.url.endswith("/api/host-backup-review"), timeout=120000) as result:
            page.get_by_role("button", name="Prepare whole-host recovery", exact=True).click()
        assert result.value.status == 200, "Packaged host review failed: " + str(result.value.status)
        expect(page.get_by_role("button", name="Create recovery file", exact=True)).to_be_visible(timeout=120000)
        page.screenshot(path=str(root / "backup-review.png"), full_page=True)
        with page.expect_response(lambda r: r.url.endswith("/api/deployments/actions/apply")) as response:
            page.get_by_role("button", name="Create recovery file", exact=True).click()
        assert response.value.status == 202
        with login(source["origin"], password) as client:
            result = wait_job(client, response.value.json()["id"])
            vault = root / "independent recovery copies"
            vault.mkdir()
            key = api(client, "backup-key", {"password": password})
            (vault / "recovery-key.json").write_text(json.dumps(key))
        page.reload()
        page.get_by_role("button", name="Backups", exact=True).click()
        expect(page.get_by_text(result["message"], exact=False).first).to_be_visible()
        page.screenshot(path=str(root / "backup-verified.png"), full_page=True)
        browser.close()
    bundle = next((host.store.root / "host-recovery").glob("*.stackarr-recovery"))
    shutil.copyfile(bundle, vault / bundle.name)
    recovery = Recovery(vault / bundle.name, vault / "recovery-key.json", package)
    with recovery.opened() as (_, meta):
        assert sum(len(r["manifest"]["apps"]) for r in meta["snapshots"]) == 9
    copied_media = root / "recovered media – samples"
    shutil.copytree(source["media"], copied_media)
    value = {"bundle": str(vault / bundle.name), "keyfile": str(vault / "recovery-key.json"), "package": str(package),
        "destination": str(root / "recovered-state"), "media": {source["media"]: str(copied_media)}, "port": 29211, "controller_port": 29081}
    (root / "request.json").write_text(json.dumps(value))
    (root / "source-media-hashes.json").write_text(json.dumps(hashes(Path(source["media"]))))
    print("Packaged browser created and authenticated the complete nine-app recovery file; independent copies retained.", flush=True)


def frozen(root, package, mode, input_file, result_name):
    report = root / result_name
    if report.exists():
        report = report.with_stem(report.stem + "-" + uuid.uuid4().hex[:8])
    result = subprocess.run([str(package / "StackarrPreview.exe"), "--host-recovery-" + mode,
        str(input_file), "--recovery-report", str(report)], capture_output=True, timeout=1800,
        creationflags=subprocess.CREATE_NO_WINDOW)
    value = json.loads(report.read_text())
    return result.returncode, value


def lose_source(root, package):
    source = json.loads((root / "source.json").read_text())
    request = json.loads((root / "request.json").read_text())
    request["package"] = str(package)
    (root / "request.json").write_text(json.dumps(request))
    code, _ = frozen(root, package, "review", root / "request.json", "blocked-existing.json")
    assert code == 1
    # Exactly this newly created lab, verified against its enrollment and saved IDs; no main resources are targeted.
    stop_lab(root, source["installation"], source["identities"])
    state = root / "package-state"
    stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_RECOVERY_LAB_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=os.environ | {"STACKARR_RECOVERY_LAB_CONTROLLER": str(state / "controller")}, capture_output=True,
        timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert stopped.returncode == 0
    host = Deployments(Store(state / "controller/state"))
    for identity in source["identities"]:
        payload = load_receipt(host, identity)
        reviewed = AppBackups(host).review(identity)
        assert not any(c["running"] for c in reviewed["containers"].values())
        assert set(payload["apps"]) <= {"plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr", "tautulli", "kuma", "cleanuparr"}
        command(["compose", "--project-name", "stackarr-owned-" + identity, "-f",
            str(state / "controller/state/deployments" / identity / "compose.json"), "down", "--volumes"])
        assert not command(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + identity])
    command(["compose", "--project-name", source["installation"]["project"], "-f", str(state / "compose.json"), "down", "--volumes"])
    state.rename(root / "lost-source-state-retained")  # Original controller/account unavailable to the recovery process.
    review_target(root, package)


def review_target(root, package):
    request = json.loads((root / "request.json").read_text())
    request["package"] = str(package)
    (root / "request.json").write_text(json.dumps(request))
    key = json.loads(Path(request["keyfile"]).read_text())
    wrong = root / "wrong-key.json"
    wrong.write_text(json.dumps(key | {"key": Fernet.generate_key().decode()}))
    (root / "wrong-key-request.json").write_text(json.dumps(request | {"keyfile": str(wrong)}))
    assert frozen(root, package, "review", root / "wrong-key-request.json", "blocked-wrong-key.json")[0] == 1
    assert not Path(request["destination"]).exists()
    recovery = Recovery(request["bundle"], request["keyfile"], package)
    with recovery.opened() as (_, meta):
        saved = next(r for r in meta["snapshots"] if "sonarr" in r["manifest"]["apps"])
        app_port = int(saved["manifest"]["installation"]["compose"]["services"]["sonarr"]["ports"][0]["published"])
    with socket.socket() as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("0.0.0.0", app_port))
        occupied.listen()
        assert frozen(root, package, "review", root / "request.json", "blocked-busy-port.json")[0] == 1
    assert not Path(request["destination"]).exists()
    assert frozen(root, package, "review", root / "request.json", "recovery-review.json")[0] == 0
    print("Simulated loss removed only the nine test volumes and dashboard volume; original host state is unavailable. Existing-resource, wrong-key and occupied-port gates passed.", flush=True)


def recover(root, package):
    review = json.loads((root / "recovery-review.json").read_text())
    recovery = Recovery(review["bundle"], review["keyfile"], package)
    original = AppBackups.helper
    count = 0
    def fail_once(self, payload, key, directory, restore=False):
        nonlocal count
        if restore:
            count += 1
            if count == 2:
                raise RuntimeError("Injected disposable restore failure after one real volume write")
        return original(self, payload, key, directory, restore)
    AppBackups.helper = fail_once
    try:
        try:
            recovery.execute(review)
        except Exception:
            assert count == 2
        else:
            raise AssertionError("Restore failure injection did not execute")
    finally:
        AppBackups.helper = original
    journal = json.loads((Path(review["destination"]) / "recovery.json").read_text())
    assert journal["phase"] == "failed" and len(journal["containers"]) == 9
    for identity in journal["containers"].values():
        assert command(["inspect", identity, "--format", "{{.State.Running}}"]) == "false"
    print("Injected extraction failure left only the nine new recovery containers stopped. Retrying in a fresh packaged process.", flush=True)
    code, result = frozen(root, package, "apply", root / "recovery-review.json", "recovery-result.json")
    assert code == 0 and result["passed"], result.get("message", "Frozen recovery failed")
    print("Fresh packaged process restored all nine configuration volumes and the dashboard account.", flush=True)


def verify(root, package):
    source = json.loads((root / "source.json").read_text())
    password = json.loads((root / "access.json").read_text())["owner_password"]
    review = json.loads((root / "recovery-review.json").read_text())
    state = Path(review["destination"])
    launch = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(state), "-NoBrowser"],
        capture_output=True, text=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    (root / "recovered-bootstrap.log").write_text(launch.stdout + launch.stderr)
    assert launch.returncode == 0
    origin = "http://localhost:" + str(review["port"])
    host = Deployments(Store(state / "controller/state"))
    old = Store(root / "lost-source-state-retained/controller/state")
    assert {k: old.secret(k) for k in old.secret_names()} == {k: host.store.secret(k) for k in old.secret_names()}
    protected = json.loads((root / "protected.json").read_text())
    for identity in source["identities"]:
        payload = load_receipt(host, identity)
        for key in payload["apps"]:
            info = inspect_container(host, identity, payload, key)
            assert info["State"]["Running"]
            name = host.owned_container(identity, payload, key)
            target = payload["compose"]["services"][key]["volumes"][0]["target"]
            assert command(["exec", name, "cat", target + "/stackarr-recovery-fixture.txt"]) == "Original isolated recovery fixture"
            if key in protected:
                for _ in range(60):
                    try:
                        assert Updates(host).protected(payload, key, host.store.secret(key)) == protected[key]
                        break
                    except Exception:
                        time.sleep(1)
                else:
                    raise AssertionError("Recovered app protected settings differ")
            if key in {"sonarr", "radarr", "prowlarr"}:
                assert arr_login(host, identity, payload, key, host.store.secret(key)["api_key"])
            if key == "cleanuparr":
                port = int(payload["compose"]["services"][key]["ports"][0]["published"])
                with Companions.client(port) as client:
                    client.headers["X-Api-Key"] = host.store.secret(key)["api_key"]
                    cleanup_safe(client)
    with login(origin, password) as client:
        config = api(client, "config")
        prior = json.loads((root / "source-config.json").read_text())["config"]
        if prior["storage"]["data_root"] in review["media"]:
            prior["storage"]["data_root"] = review["media"][prior["storage"]["data_root"]]
        assert config["config"] == prior
        assert api(client, "backup-policy")["policy"]["enabled"] is False
        api(client, "refresh", {}, status=202)
        for _ in range(120):
            fresh = {r["id"] for r in api(client, "status")["integrations"] if r["state"] == "ready" and not r["stale"]}
            if {"sonarr", "radarr", "prowlarr", "qbittorrent", "kuma"} <= fresh:
                break
            time.sleep(.5)
        assert {"sonarr", "radarr", "prowlarr", "qbittorrent", "kuma"} <= fresh
    expected_media = json.loads((root / "source-media-hashes.json").read_text())
    assert hashes(Path(source["media"])) == expected_media
    assert hashes(Path(next(iter(review["media"].values())))) == expected_media
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(origin)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=False).click()
        expect(page.get_by_role("button", name="Backups", exact=True)).to_be_visible()
        page.get_by_role("button", name="Backups", exact=True).click()
        expect(page.get_by_text("Recovered host. Review backup storage and enable the schedule again.", exact=False)).to_be_visible()
        page.screenshot(path=str(root / "recovered-dashboard.png"), full_page=True)
        browser.close()
    baseline = json.loads((root / "main-before.json").read_text())
    assert main_settings() == baseline["settings"] and hashes(MAIN / "media") == baseline["media"]
    assert set(baseline["running"]) <= set(command(["ps", "-q", "--no-trunc"]).splitlines())
    report = {"passed": True, "apps_reconstructed": 9, "deployment_groups": 3,
        "fresh_process_after_failed_restore": True, "dashboard_password_preserved": True,
        "controller_credentials_preserved": True, "generated_arr_logins_verified": 3,
        "authenticated_core_and_kuma": sorted(fresh), "nine_config_volume_files_preserved": True,
        "media_files_preserved": len(expected_media), "main_media_files_preserved": len(baseline["media"]),
        "main_apps_settings_and_ids_preserved": True, "original_host_state_unavailable_during_recovery": True,
        "wrong_key_busy_port_existing_resources_rejected": True, "backup_schedule_paused": True,
        "cleanuparr_authenticated_dry_run_and_jobs_disabled": True,
        "limitations": "Same-computer isolated Docker loss/recovery. Plex/Seerr/Tautulli use first-run fixture configurations; claimed-account recovery and a replacement Windows host/native wizard need further acceptance."}
    (root / "report.json").write_text(json.dumps(report, indent=2))
    print("Whole-host recovery passed: nine app volumes, preserved account/core logins/settings, media hashes and all main containers unchanged.", flush=True)


def finish(root, package):
    report = json.loads((root / "report.json").read_text())
    assert report["passed"]
    main_access = json.loads((MAIN / "access.json").read_text())
    origin = main_access["dashboard"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(120000)
        page.goto(origin)
        page.get_by_label("Password", exact=True).fill(main_access["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Backups", exact=True).click()
        expect(page.get_by_role("button", name="Review backup plan", exact=True)).to_be_visible(timeout=120000)
        with page.expect_response(lambda r: r.url.endswith("/api/host-backup-review"), timeout=120000) as response:
            page.get_by_role("button", name="Prepare whole-host recovery", exact=True).click()
        assert response.value.status == 200 and len(response.value.json()["apps"]) == 9
        expect(page.get_by_role("button", name="Create recovery file", exact=True)).to_be_visible(timeout=120000)
        page.screenshot(path=str(root / "main-recovery-controls.png"), full_page=True)
        # Deliberately leave the main operation unapproved: this acceptance never stops/restores its apps.
        browser.close()
    source = json.loads((root / "source.json").read_text())
    review = json.loads((root / "recovery-review.json").read_text())
    state = Path(review["destination"])
    host = Deployments(Store(state / "controller/state"))
    before = set(command(["ps", "-q", "--no-trunc"]).splitlines())
    owned = set()
    for identity in source["identities"]:
        owned.update(c["id"] for c in AppBackups(host).review(identity)["containers"].values())
    installation = json.loads((state / "installation.json").read_text())
    dashboard = command(["compose", "--project-name", installation["project"], "-f", str(state / "compose.json"), "ps", "-q", "stackarr"])
    owned.add(dashboard)
    assert len(owned) == 10 and owned <= before
    stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_RECOVERY_LAB_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=os.environ | {"STACKARR_RECOVERY_LAB_CONTROLLER": str(state / "controller")}, capture_output=True,
        timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert stopped.returncode == 0
    for identity in source["identities"]:
        command(["compose", "--project-name", "stackarr-owned-" + identity, "-f",
            str(state / "controller/state/deployments" / identity / "compose.json"), "down", "--timeout", "90"])
    command(["compose", "--project-name", installation["project"], "-f", str(state / "compose.json"), "down"])
    assert set(command(["ps", "-q", "--no-trunc"]).splitlines()) == before - owned
    expected_media = json.loads((root / "source-media-hashes.json").read_text())
    assert hashes(Path(source["media"])) == expected_media
    assert hashes(Path(next(iter(review["media"].values())))) == expected_media
    baseline = json.loads((root / "main-before.json").read_text())
    assert main_settings() == baseline["settings"] and hashes(MAIN / "media") == baseline["media"]
    report.update(main_recovery_review_available=True, main_apps_fresh=9, final_bundle=package.name + ".zip",
        isolated_test_containers_and_networks_removed=True, recovered_configuration_volumes_retained=10)
    (root / "report.json").write_text(json.dumps(report, indent=2))
    print("Main recovery review verified without approval; only recovered test containers/networks removed, all ten configuration volumes and media retained.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--phase", choices=["source", "backup", "loss", "review", "recover", "verify", "finish"])
    args = parser.parse_args()
    package = args.package.resolve()
    root = args.root.resolve() if args.root else (Path("test-results") / ("docker-host-recovery-" + uuid.uuid4().hex[:12])).resolve()
    assert root.is_relative_to(Path("test-results").resolve()) and root.name.startswith("docker-host-recovery-")
    if not root.exists():
        root.mkdir()
        (root / "main-before.json").write_text(json.dumps({"settings": main_settings(), "media": hashes(MAIN / "media"),
            "running": command(["ps", "-q", "--no-trunc"]).splitlines()}))
    print("Whole-host recovery lab: " + str(root), flush=True)
    for name, fn in [("source", setup_source), ("backup", source_backup), ("loss", lose_source), ("review", review_target), ("recover", recover), ("verify", verify), ("finish", finish)]:
        if (args.phase is None and name != "review") or args.phase == name:
            fn(root, package)


if __name__ == "__main__":
    main()
