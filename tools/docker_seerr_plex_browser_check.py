"""Packaged Seerr/Plex update controls on the fixed isolated SSO lab only."""

import json
import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.self_update import SelfUpdates
from stackarr.updates import Updates
from tools.docker_folder_ports_check import bootstrap, command
from tools.docker_seerr_plex_maintenance_check import (
    ORIGIN,
    PACKAGE,
    ROOT,
    STATE,
    cleanup_work,
    host,
    identity,
    preserved,
    verify,
    write,
)


def main():
    native = json.loads((ROOT / "native-report.json").read_text())
    assert len(native["cases"]) == 6 and all(row["passed"] for row in native["cases"])
    with sqlite3.connect(STATE / "stackarr.db") as db:
        assert not db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running','needs-recovery')").fetchone()
        assert not db.execute("SELECT 1 FROM app_updates WHERE state IN ('running','needs-recovery')").fetchone()
    db.close()
    cleanup_work()
    installation, origin = bootstrap(PACKAGE, ROOT, 29240, 29091)
    assert origin == ORIGIN
    service = host()
    runtime = SelfUpdates(ROOT / "package-state")
    new_package = Path(json.loads((ROOT / "package-verification-r2.json").read_text())["package"])
    new_release = new_package.name
    report_file = ROOT / "browser-report.json"
    report = json.loads(report_file.read_text()) if report_file.exists() else {"steps": []}
    def recorded(name, **extra):
        report["steps"].append({"step": name, "passed": True, **extra})
        write(report_file.name, report)
        print("Packaged Plex-account Seerr passed: " + name, flush=True)
    def done(name):
        return any(row["step"] == name for row in report["steps"])
    with ThreadPoolExecutor(max_workers=1) as worker, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(180000)
        access = ROOT / "access.json"
        if not access.exists():
            invite = command(["compose", "--project-name", installation["project"], "-f", str(ROOT / "package-state/compose.json"),
                "exec", "-T", "stackarr", "stackarr", "setup-link"])
            password = secrets.token_urlsafe(32)
            page.goto(invite)
            page.get_by_label("Create a password", exact=True).fill(password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
            write(access.name, {"owner_password": password, "dashboard": origin})
        else:
            page.goto(origin)
            page.get_by_label("Password", exact=True).fill(json.loads(access.read_text())["owner_password"])
            page.get_by_role("button", name="Sign in", exact=False).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        csrf = page.request.get(origin + "/api/session").json()["csrf"]
        page.context.set_extra_http_headers({"Origin": origin, "X-CSRF-Token": csrf})
        # The older-version fixture was installed by the native maintainer
        # harness. It has no dashboard installation-review binding. Use the
        # normal owner-authorized connect-only API for this test's generated
        # credential; never insert a binding or bypass the handoff guard.
        if not done("fixture-monitoring-connection"):
            saved = page.request.get(origin + "/api/config").json()
            app = saved["config"]["integrations"]["seerr"]
            app.update(enabled=True, mode="connect", url="http://host.docker.internal:43270", port=43270)
            result = page.request.put(origin + "/api/config", data={"revision": saved["revision"], "config": saved["config"],
                "credentials": {"seerr": {"api_key": service.store.secret("seerr")["api_key"]}}})
            assert result.status == 200
            recorded("fixture-monitoring-connection", native_fixture=True, normal_existing_connection_api=True)
        for _ in range(60):
            result = page.request.get(origin + "/api/stackarr-updates")
            if result.status == 200:
                break
            assert result.status in {429, 503}
            time.sleep(.5)
        assert result.status == 200
        def wait_job(operation):
            for _ in range(1200):
                response = page.request.get(origin + "/api/deployments")
                if response.status in {429, 503}:
                    time.sleep(.5)
                    continue
                assert response.status == 200
                row = next((row for row in response.json()["actions"] if row["id"] == operation), None)
                if row and row["state"] not in {"running", "queued"}:
                    assert row["state"] == "succeeded", row["message"]
                    return
                time.sleep(.5)
            raise AssertionError("Isolated packaged Seerr action timed out")
        def app_action(action, name):
            if done(name):
                return
            page.get_by_role("button", name="Apps", exact=True).click()
            if action == "repair":
                page.locator('[data-check-install="' + identity() + '"]').click()
                page.get_by_role("button", name="Review repair Seerr", exact=True).click()
                apply_name = "Repair app"
            else:
                page.get_by_role("button", name="Check packaged updates", exact=True).click()
                with page.expect_response(lambda r: r.url.endswith("/update-review")) as reviewed:
                    page.get_by_role("button", name="Review " + action + " Seerr", exact=True).click()
                assert reviewed.value.status == 200, reviewed.value.json().get("detail")
                apply_name = "Update app" if action == "update" else "Roll back app"
            expect(page.get_by_role("button", name=apply_name, exact=True)).to_be_visible()
            page.screenshot(path=str(ROOT / (name + "-review.png")), full_page=True)
            with page.expect_response(lambda r: r.url.endswith("/api/deployments/actions/apply")) as approved:
                page.get_by_role("button", name=apply_name, exact=True).click()
            assert approved.value.status == 202
            wait_job(approved.value.json()["id"])
            worker.submit(verify, service).result(timeout=180)
            recorded(name, fresh_plex_session=True, request_and_settings_preserved=True)
        app_action("update", "legacy-package-update")
        if not done("new-package-promotion"):
            legacy = next(row for row in Updates(service).listing()["history"] if row["state"] == "succeeded")
            saved = Updates(service).read(legacy["id"])
            assert "authentication" not in saved["protected"] and "_protected_version" not in saved["secret"]
            write("legacy-update.json", {"id": legacy["id"], "actual_previous_package_checkpoint": True})
            runtime.admit((Path("dist") / (new_release + ".zip")).resolve())
            page.get_by_role("button", name="Settings", exact=True).click()
            page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
            page.get_by_role("button", name="Review Stackarr update", exact=True).click()
            with page.expect_response(lambda r: r.url.endswith("/api/stackarr-update-apply")) as approved:
                page.get_by_role("button", name="Update Stackarr", exact=True).click()
            assert approved.value.status == 202
            job = runtime.home / "jobs" / approved.value.json()["id"] / "job.json"
            for _ in range(1200):
                value = json.loads(job.read_text())
                if value["phase"] in {"succeeded", "rolled-back", "failed-recovered", "needs-recovery"}:
                    assert value["phase"] == "succeeded", value.get("failure", value["message"])
                    break
                time.sleep(.5)
            else:
                raise AssertionError("Isolated Stackarr package update timed out")
            page.goto(origin)
            expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
            assert runtime.release(runtime.active()["release"])[1]["release"] == new_release
            worker.submit(verify, service).result(timeout=180)
            recorded("new-package-promotion", media_app_unchanged=True)
        app_action("rollback", "legacy-checkpoint-rollback-in-new-package")
        app_action("repair", "new-package-repair")
        app_action("update", "new-package-update")
        app_action("rollback", "new-package-rollback")
        page.get_by_role("button", name="Apps", exact=True).click()
        page.get_by_role("button", name="Check packaged updates", exact=True).click()
        page.screenshot(path=str(ROOT / "packaged-browser-results.png"), full_page=True)
        report.update(passed=True, package=str(new_package), app_actions=5, frozen_controller=True)
        write(report_file.name, report)
        browser.close()
    preserved()


if __name__ == "__main__":
    main()
