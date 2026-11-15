"""Extracted-package repair/update/rollback on the fixed optional-app lab only."""

import argparse
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.config import CATALOG
from stackarr.self_update import SelfUpdates
from tools.docker_folder_ports_check import bootstrap, command
from tools.docker_optional_maintenance_check import (
    APPS,
    ROOT,
    STATE,
    checkpoint,
    host,
    peers,
    preserved,
    target,
    verify,
    write,
)


def run(package):
    active = ROOT / "packaged-installation.json"
    current_state = Path(json.loads(active.read_text())["state"]).resolve() if active.exists() else STATE
    assert current_state.is_relative_to(ROOT)
    with sqlite3.connect(current_state / "stackarr.db") as db:
        assert not db.execute("SELECT 1 FROM app_updates WHERE state IN ('running','needs-recovery')").fetchone()
        assert not db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running','needs-recovery')").fetchone()
    packaged_root = ROOT / "packaged-preview"
    packaged_root.mkdir(exist_ok=True)
    state_directory = packaged_root / "package-state"
    destination = state_directory / "controller/state"
    if not (state_directory / "installation.json").exists():
        # The launcher correctly refuses an unrecognized nonempty folder. Keep
        # the native test fixture, create a normal empty packaged installation,
        # then import only its controller data with that new controller stopped.
        assert state_directory.resolve().is_relative_to(ROOT) and destination.resolve().is_relative_to(ROOT)
        installation, origin = bootstrap(package, packaged_root, 29230, 29090, ROOT / "media")
        env = os.environ | {"STACKARR_OPTIONAL_CONTROLLER": str(state_directory / "controller")}
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_OPTIONAL_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", installation["controller_port"])) != 0
        empty = packaged_root / "initial-empty-controller-state"
        assert STATE.resolve().is_relative_to(ROOT) and empty.resolve().is_relative_to(ROOT) and not empty.exists()
        with sqlite3.connect(destination / "stackarr.db") as db:
            assert not db.execute("SELECT 1 FROM deployments").fetchone()
        shutil.copytree(destination, empty)
        shutil.copytree(STATE, destination, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("stackarr.db", "stackarr.db-*"))
        # SQLite backup handles any journals from stopping the new empty
        # controller; never overlay one database with another's sidecars.
        with sqlite3.connect(STATE / "stackarr.db") as source_db, sqlite3.connect(destination / "stackarr.db") as target_db:
            source_db.backup(target_db)
        source_db.close()
        target_db.close()
        installation, origin = bootstrap(package, packaged_root, 29230, 29090, ROOT / "media")
        preserved()
        write("packaged-fixture-import.json", {"empty_directory_protection_verified": True,
            "native_fixture_preserved": True, "same_owned_apps_reused": True, "controller_stopped_before_import": True})
    else:
        installation, origin = bootstrap(package, packaged_root, 29230, 29090, ROOT / "media")
    write("packaged-installation.json", {"installation": installation, "origin": origin, "root": str(packaged_root), "state": str(destination)})
    runtime = SelfUpdates(state_directory)
    new_release = json.loads((package / "manifest.json").read_text())["release"]
    runtime.admit((Path("dist") / (new_release + ".zip")).resolve())
    # Never construct Deployments while the controller is executing an action.
    with ThreadPoolExecutor(max_workers=1) as worker, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(180000)
        access_file = ROOT / "access.json"
        if not access_file.exists():
            invitation = command(["compose", "--project-name", installation["project"], "-f", str(state_directory / "compose.json"),
                "exec", "-T", "stackarr", "stackarr", "setup-link"])
            password = secrets.token_urlsafe(32)
            page.goto(invitation)
            page.get_by_label("Create a password", exact=True).fill(password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            expect(page.get_by_role("button", name="Apps", exact=True)).to_be_visible(timeout=180000)
            write("access.json", {"owner_password": password, "dashboard": origin})
        else:
            page.goto(origin)
            page.get_by_label("Password", exact=True).fill(json.loads(access_file.read_text())["owner_password"])
            page.get_by_role("button", name="Sign in", exact=False).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        # Let the running frozen controller adopt its own initial package;
        # a source Python process must never infer the executable's identity.
        for _ in range(60):
            current = page.request.get(origin + "/api/stackarr-updates")
            if current.status == 200:
                break
            assert current.status in {429, 503}, current.json().get("detail")
            time.sleep(.5)
        assert current.status == 200
        if current.json()["current"] != new_release:
            page.get_by_role("button", name="Settings", exact=True).click()
            page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
            page.get_by_role("button", name="Review Stackarr update", exact=True).click()
            with page.expect_response(lambda r: r.url.endswith("/api/stackarr-update-apply")) as approval:
                page.get_by_role("button", name="Update Stackarr", exact=True).click()
            assert approval.value.status == 202
            job_file = runtime.home / "jobs" / approval.value.json()["id"] / "job.json"
            for _ in range(1200):
                job = json.loads(job_file.read_text())
                if job["phase"] in {"succeeded", "rolled-back", "failed-recovered", "needs-recovery"}:
                    assert job["phase"] == "succeeded", job.get("failure", job["message"])
                    break
                time.sleep(.5)
            else:
                raise AssertionError("Isolated package replacement timed out")
            expect(page.get_by_role("button", name="Apps", exact=True)).to_be_enabled()
            page.goto(origin)
            assert runtime.release(runtime.active()["release"])[1]["release"] == new_release
            preserved()
            print("Isolated packaged dashboard/controller updated; media apps preserved.", flush=True)
        service = host()
        page.get_by_role("button", name="Apps", exact=True).click()
        csrf = page.request.get(origin + "/api/session").json()["csrf"]
        page.context.set_extra_http_headers({"Origin": origin, "X-CSRF-Token": csrf})
        def wait_job(identity):
            for _ in range(1200):
                response = page.request.get(origin + "/api/deployments")
                assert response.status == 200
                row = next((row for row in response.json()["actions"] if row["id"] == identity), None)
                if row and row["state"] not in {"queued", "running"}:
                    assert row["state"] == "succeeded", row["message"]
                    return
                time.sleep(.5)
            raise AssertionError("Packaged app action timed out")
        report_file = ROOT / "packaged-browser-report.json"
        report = json.loads(report_file.read_text()) if report_file.exists() else {"cases": []}
        if report.get("package") != str(package):
            if report_file.exists():
                write("packaged-browser-superseded-" + str(time.time_ns()) + ".json", report)
            report = {"cases": [], "package": str(package)}
            write(report_file.name, report)
        for key in APPS:
            if any(row["app"] == key for row in report["cases"]):
                continue
            baseline = worker.submit(checkpoint, service, key).result(timeout=120)
            other = peers(service, key)
            page.locator('[data-check-install="' + target() + '"]').click()
            page.get_by_role("button", name="Review repair " + CATALOG[key]["name"], exact=True).click()
            expect(page.get_by_role("button", name="Repair app", exact=True)).to_be_visible(timeout=180000)
            page.screenshot(path=str(ROOT / (key + "-packaged-repair-review.png")), full_page=True)
            with page.expect_response(lambda r: r.url.endswith("/api/deployments/actions/apply"), timeout=180000) as approval:
                page.get_by_role("button", name="Repair app", exact=True).click()
            assert approval.value.status == 202
            wait_job(approval.value.json()["id"])
            worker.submit(verify, service, key, baseline, other).result(timeout=180)
            print("Packaged repair preserved settings and media: " + key, flush=True)
            for action, button in (("update", "Update app"), ("rollback", "Roll back app")):
                page.get_by_role("button", name="Check packaged updates", exact=True).click()
                review_button = page.get_by_role("button", name="Review " + action + " " + CATALOG[key]["name"], exact=True)
                expect(review_button).to_be_visible(timeout=180000)
                # The old native history contains no succeeded updates after rollback.
                with page.expect_response(lambda r: r.url.endswith("/update-review")) as reviewed:
                    review_button.click()
                assert reviewed.value.status == 200, reviewed.value.json().get("detail")
                expect(page.get_by_role("button", name=button, exact=True)).to_be_visible(timeout=180000)
                with page.expect_response(lambda r: r.url.endswith("/api/deployments/actions/apply"), timeout=180000) as approved:
                    page.get_by_role("button", name=button, exact=True).click()
                assert approved.value.status == 202
                wait_job(approved.value.json()["id"])
                worker.submit(verify, service, key, baseline, other).result(timeout=180)
                print("Packaged " + action + " preserved settings and media: " + key, flush=True)
            report["cases"].append({"app": key, "repair": True, "distinct_image_update": True, "rollback": True,
                "settings_logins_connections_preserved": True, "peer_container_ids_preserved": True, "media_preserved": True})
            write(report_file.name, report)
            print("Packaged browser repair, real update and rollback passed: " + key, flush=True)
        page.get_by_role("button", name="Check packaged updates", exact=True).click()
        page.screenshot(path=str(ROOT / "packaged-browser-results.png"), full_page=True)
        report.update(passed=True, package=str(package), frozen_private_controller=True)
        write(report_file.name, report)
        browser.close()
    preserved()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    run(parser.parse_args().package.resolve())
