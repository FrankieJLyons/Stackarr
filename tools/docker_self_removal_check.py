"""Stackarr removal/reinstall acceptance, restricted to the original-sample lab."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.self_removal import SelfRemoval
from stackarr.self_update import TERMINAL, SelfUpdates, pending, read
from tools import docker_app_maintenance_check as lab

OUTPUT = Path("test-results/docker-self-removal-20261018").resolve()
OUTPUT.mkdir(exist_ok=True)
lab.OUTPUT = OUTPUT


def write(name, value):
    lab.write(name, value)


def updater():
    return SelfUpdates(lab.STATE)


def wait(identity, expected):
    previous = None
    for _ in range(960):
        job = read(updater().home / "jobs" / identity / "job.json")
        if job["phase"] != previous:
            print("Stackarr " + job["action"] + ": " + job["phase"], flush=True)
            previous = job["phase"]
        if job["phase"] in TERMINAL | {"needs-recovery"}:
            write(identity + "-result.json", {k: job.get(k) for k in ("id", "action", "phase", "message", "failure", "failure_phase")})
            assert job["phase"] == expected, job.get("failure", job["message"])
            return job
        time.sleep(.5)
    raise AssertionError("Scoped Stackarr worker did not finish")


def running():
    lab.preserved()
    u = updater()
    runtime = u.active()
    u.docker.fixed_context = runtime["context"]["name"]
    actual = u.protected(runtime)
    before = read(OUTPUT / "stackarr-before.json")
    assert {k: v for k, v in actual.items() if k != "container"} == before["protected"]
    assert SelfRemoval(u).files(runtime) == before["configuration_files"]
    assert not (lab.STATE / "stackarr-removed.json").exists()


def removed():
    lab.preserved()
    u = updater()
    removal = SelfRemoval(u)
    saved = removal.saved()
    removal.context(saved["source"])
    removal.retained(saved)
    assert not u.listening(saved["source"]["port"]) and not u.listening(saved["source"]["controller_port"])
    assert read(lab.STATE / "compose.json") == removal.guard(saved["id"])


def browser_remove():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(180000)
        lab.signin(page)
        page.get_by_role("button", name="Settings", exact=True).click()
        with page.expect_response(lambda r: r.url.endswith("/api/stackarr-update-review")) as reviewed:
            page.get_by_role("button", name="Review Stackarr removal", exact=True).click()
        assert reviewed.value.status == 200, "The packaged removal review was rejected before approval"
        apply = page.get_by_role("button", name="Remove Stackarr, keep settings", exact=True)
        expect(apply).to_be_visible(timeout=180000)
        expect(page.locator("#stackarr-update-review")).to_contain_text("Scheduled backups pause", timeout=180000)
        page.screenshot(path=str(OUTPUT / "remove-review.png"), full_page=True)
        with page.expect_response(lambda r: r.url.endswith("/api/stackarr-update-apply")) as response:
            apply.click()
        assert response.value.status == 202
        identity = response.value.json()["id"]
        expect(page.locator("#stackarr-update-review")).to_contain_text("removal requested")
        page.screenshot(path=str(OUTPUT / "remove-requested.png"), full_page=True)
        browser.close()
    wait(identity, "succeeded")
    removed()
    write("browser-removal.json", {"passed": True, "id": identity, "owner_review_approval": True, "apps_media_settings_preserved": True})


def native(package, mode, request, success=True):
    identity = uuid.uuid4().hex
    source, report = OUTPUT / (identity + "-request.json"), OUTPUT / (identity + "-report.json")
    source.write_text(json.dumps(request))
    result = subprocess.run([str(package / "StackarrPreview.exe"), "--stackarr-reinstall-" + mode, str(source),
                             "--maintenance-report", str(report)], capture_output=True, timeout=240,
                            env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1"})
    assert (result.returncode == 0) == success
    return read(report)


def reinstall(package):
    reviewed = native(package, "review", {"state": str(lab.STATE)})
    job = native(package, "apply", reviewed)
    # No duplicate job may start from a reused native approval.
    rejected = native(package, "apply", reviewed, success=False)
    assert rejected["passed"] is False
    wait(job["id"], "succeeded")
    running()
    with lab.owner() as client:
        assert client.get("/api/session").json()["authenticated"]
    write("native-reinstall.json", {"passed": True, "id": job["id"], "frozen_two_step_approval": True,
        "reused_review_rejected": True, "existing_owner_password_valid": True, "account_settings_backups_and_app_logins_preserved": True})


def fresh_start(package, expect_removed=True):
    report = OUTPUT / ("fresh-start-" + uuid.uuid4().hex + ".json")
    result = subprocess.run([str(package / "StackarrPreview.exe"), "--stackarr-start", str(lab.STATE),
                             "--maintenance-report", str(report)], capture_output=True, timeout=300,
                            env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1"})
    assert result.returncode == 0 and read(report)["removed"] == expect_removed
    removed() if expect_removed else running()
    return report


def conflicts(package, baseline):
    for port in (29140, 29014):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", port))
            listener.listen(1)
            result = native(package, "review", {"state": str(lab.STATE)}, success=False)
            assert result["passed"] is False and "port" in result["message"]
        removed()
    # An older launcher must not bypass a completed removal.
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(baseline / "Start-StackarrPreview.ps1"), "-StateDirectory", str(lab.STATE), "-NoBrowser"], capture_output=True, timeout=240)
    assert result.returncode != 0
    removed()
    fresh_start(package)
    write("reinstall-guards.json", {"passed": True, "dashboard_port_conflict_rejected": True,
        "controller_port_conflict_rejected": True, "older_launcher_did_not_reinstall": True, "new_start_requires_review": True})


def older_start_refused(baseline, identity, stage):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(baseline / "Start-StackarrPreview.ps1"), "-StateDirectory", str(lab.STATE), "-NoBrowser"], capture_output=True, timeout=240)
    assert result.returncode != 0 and pending(lab.STATE)["id"] == identity
    lab.preserved()
    write("legacy-refused-" + stage + ".json", {"passed": True, "older_launcher_left_interrupted_operation_untouched": True})


def fault(crash=False):
    u = updater()
    if not crash:
        assert pending(lab.STATE) is None
        staged = u.release(u.active()["release"])[0]
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
            str(staged / "Start-StackarrPreview.ps1"), "-StateDirectory", str(lab.STATE), "-NoBrowser"], capture_output=True, timeout=240)
        assert result.returncode == 0
        removed()
        write("packaged-start-removed.json", {"passed": True, "powershell_launcher_did_not_silently_reinstall": True,
            "no_browser_mode_keeps_removed_state": True})
    u.launch = lambda *args, **kwargs: None
    identity = u.approve(u.review("reinstall"))["id"]
    write("interrupted-reinstall.json" if crash else "failed-reinstall.json", {"id": identity})
    original, injected = u.health, False

    def poisoned(runtime, expected, checking):
        nonlocal injected
        if not injected:
            injected = True
            assert checking and runtime["volume"] == "stackarr-self-update-" + identity
            container, info = u.dashboard(runtime["port"])
            assert next(m["Name"] for m in info["Mounts"] if m["Destination"] == "/var/lib/stackarr") == runtime["volume"]
            code = "import json,sqlite3; d=sqlite3.connect('/var/lib/stackarr/stackarr.db'); r=d.execute('SELECT data FROM settings WHERE id=1').fetchone()[0]; v=json.loads(r); old=v['dashboard']['page_size']; v['dashboard']['page_size']=61 if old!=61 else 62; d.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(v),)); d.commit(); print(json.loads(d.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])['dashboard']['page_size']!=old); d.close()"
            assert u.docker._call(["exec", container, "python", "-c", code]).strip() == "True"
            write("candidate-write-" + identity + ".json", {"observed": True, "only_isolated_candidate_database_changed": True})
            if crash:
                print("Exiting only the test supervisor after confirmed candidate database writes.", flush=True)
                os._exit(77)
        original(runtime, expected, checking)

    u.health = poisoned
    u.execute(identity)
    wait(identity, "failed-recovered")
    removed()


def interrupted_remove():
    u = updater()
    u.launch = lambda *args, **kwargs: None
    identity = u.approve(u.review("remove"))["id"]
    target = read(u.home / "jobs" / identity / "job.json")["before"]["container"]
    write("interrupted-removal.json", {"id": identity})
    original = u.docker._call

    def remove_then_exit(args, **kwargs):
        value = original(args, **kwargs)
        if args == ["rm", target]:
            write("removed-before-exit-" + identity + ".json", {"observed": True, "only_exact_lab_dashboard_removed": True})
            print("Exiting only the test supervisor after confirmed Stackarr container removal.", flush=True)
            os._exit(77)
        return value

    u.docker._call = remove_then_exit
    u.execute(identity)
    raise AssertionError("The guarded interruption did not occur")


def cleanup():
    running()
    lab.command(["compose", "--project-name", "stackarr-owned-" + lab.CORE, "-f",
        str(lab.STATE / "controller/state/deployments" / lab.CORE / "compose.json"), "down"])
    lab.command(["compose", "--project-name", lab.PROJECT, "-f", str(lab.STATE / "compose.json"), "down"])
    lab.stop_lab_controller()
    lab.main_preserved()
    assert lab.hashes(lab.LAB / "media") == read(OUTPUT / "lab-before.json")["media"]
    assert len(lab.command(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=stackarr-owned-" + lab.CORE]).splitlines()) == 4
    write("report.json", {"passed": True, "packaged_browser_removal": True, "packaged_reviewed_reinstall": True,
        "occupied_ports_and_older_launcher_rejected": True, "failed_candidate_database_write_recovered": True,
        "fresh_process_interrupted_removal_and_reinstall_recovery": True, "four_original_app_ids_settings_logins_and_six_media_files_preserved": True,
        "main_nine_apps_settings_credentials_and_sixteen_media_files_preserved": True,
        "only_isolated_containers_networks_removed": True, "settings_volumes_samples_packages_and_checkpoints_retained": True})


def main_controls(archive):
    assert read(OUTPUT / "report.json")["passed"]
    lab.upgrade(archive, lab.MAIN, "http://localhost:29100", lab.MAIN)
    lab.main_preserved(allow_dashboard=True)
    with lab.owner("http://localhost:29100", lab.MAIN) as client:
        response = client.post("/api/stackarr-update-review", json={"action": "remove"})
        response.raise_for_status()  # Review only. Never approve main Stackarr removal.
        assert "media apps keep running" in response.json()["notice"]
        stamp = time.time()
        client.post("/api/refresh", json={}).raise_for_status()
        for _ in range(120):
            rows = client.get("/api/status").json()["integrations"]
            ready = [r["id"] for r in rows if r["state"] == "ready" and not r["stale"] and (r["collected_at"] or 0) > stamp]
            if len(ready) == 9:
                break
            time.sleep(.5)
        assert len(ready) == 9
        plan = client.get("/api/backup-policy").json()["policy"]
        assert plan["enabled"] and plan["time"] == "03:00" and plan["keep"] == 7 and len(plan["deployments"]) == 4
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(120000)
        page.goto("http://localhost:29100")
        page.get_by_label("Password", exact=True).fill(read(lab.MAIN / "access.json")["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Settings", exact=True).click()
        expect(page.get_by_role("button", name="Review Stackarr removal", exact=True)).to_be_visible()
        page.screenshot(path=str(OUTPUT / "main-controls.png"), full_page=True)
        browser.close()
    lab.main_preserved(allow_dashboard=True)
    write("main-verification.json", {"passed": True, "only_stackarr_updated": True, "removal_review_only_never_approved": True,
        "nine_original_app_ids_and_fresh_monitoring": sorted(ready), "all_settings_credentials_and_sixteen_media_files_preserved": True,
        "nightly_backup_plan_unchanged": True})


def run(package, baseline, archive):
    lab.prepare(baseline)
    lab.upgrade(archive)
    u = updater()
    runtime = u.active()
    u.docker.fixed_context = runtime["context"]["name"]
    write("stackarr-before.json", {"protected": {k: v for k, v in u.protected(runtime).items() if k != "container"},
        "configuration_files": SelfRemoval(u).files(runtime)})
    accept(package, baseline)


def accept(package, baseline):
    browser_remove()
    conflicts(package, baseline)
    reinstall(package)
    base = [sys.executable, "-m", "tools.docker_self_removal_check"]
    stopped = subprocess.run([*base, "--phase", "interrupt-remove"])
    assert stopped.returncode != 0
    operation = read(OUTPUT / "interrupted-removal.json")["id"]
    assert read(OUTPUT / ("removed-before-exit-" + operation + ".json"))["observed"]
    assert pending(lab.STATE)["id"] == operation
    older_start_refused(baseline, operation, "removal")
    fresh_start(package)
    assert read(updater().home / "jobs" / operation / "job.json")["phase"] == "succeeded"
    subprocess.run([*base, "--phase", "failed"], check=True)
    stopped = subprocess.run([*base, "--phase", "interrupt-reinstall"])
    assert stopped.returncode != 0
    operation = read(OUTPUT / "interrupted-reinstall.json")["id"]
    assert read(OUTPUT / ("candidate-write-" + operation + ".json"))["observed"] and pending(lab.STATE)["id"] == operation
    older_start_refused(baseline, operation, "reinstall")
    fresh_start(package)
    assert read(updater().home / "jobs" / operation / "job.json")["phase"] == "failed-recovered"
    reinstall(package)
    cleanup()
    write("final-acceptance.json", {"passed": True, "release": read(package / "manifest.json")["release"],
        "actual_candidate_database_writes_observed": True, "fresh_packaged_recovery": True, "media_and_settings_preserved": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["run", "upgrade", "accept", "failed", "interrupt-remove", "interrupt-reinstall", "main", "reinstall", "recover", "cleanup"], required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.phase == "run":
        run(args.package.resolve(), args.baseline.resolve(), args.archive.resolve())
    elif args.phase == "accept":
        accept(args.package.resolve(), args.baseline.resolve())
    elif args.phase == "upgrade":
        lab.upgrade(args.archive.resolve())
    elif args.phase == "main":
        main_controls(args.archive.resolve())
    elif args.phase == "failed":
        fault()
    elif args.phase == "interrupt-remove":
        interrupted_remove()
    elif args.phase == "interrupt-reinstall":
        fault(True)
    elif args.phase == "reinstall":
        reinstall(args.package.resolve())
    elif args.phase == "recover":
        fresh_start(args.package.resolve())
    elif args.phase == "cleanup":
        cleanup()


if __name__ == "__main__":
    main()
