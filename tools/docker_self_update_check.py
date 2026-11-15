"""Packaged Stackarr swaps and failures, restricted to the disposable core lab."""

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.self_update import SelfUpdates, fingerprint, read
from stackarr.store import Store
from stackarr.updates import Updates
from tools.docker_folder_ports_check import MAIN, command, hashes, main_settings

LAB = Path("test-results/docker-core-05cebfd84fd1").resolve()
STATE = LAB / "package-state"
CORE = "c6903afb2218471aa2a45be825f625e5"
ORIGIN = "http://localhost:29140"
PROJECT = "stackarr-preview-9e8929fdc74c"


def host():
    return Deployments(Store(STATE / "controller/state"))


def prepare(output, package):
    current_dashboard = command(["ps", "-aq", "--no-trunc", "--filter", "name=^/" + PROJECT + "-stackarr-1$"])
    baseline = {"main_settings": main_settings(), "main_media": hashes(MAIN / "media"),
                "running": [c for c in command(["ps", "-q", "--no-trunc"]).splitlines() if c != current_dashboard], "lab_media": hashes(LAB / "media")}
    (output / "before.json").write_text(json.dumps(baseline))
    command(["load", "--input", str(package / "stackarr-image.tar")])
    env = os.environ | {"STACKARR_SELF_TEST_CONTROLLER": str(STATE / "controller")}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_SELF_TEST_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0
    manifest = read(package / "manifest.json")
    plan = read(STATE / "compose.json")
    plan["services"]["stackarr"]["image"] = manifest["image"]
    (STATE / "compose.json").write_text(json.dumps(plan))
    env.update(STACKARR_PORT="29140", STACKARR_CONTROLLER_PORT="29014", STACKARR_PACKAGE_ROOT=str(package),
        STACKARR_CONTROLLER_ROOTS=json.dumps([{"path": str(LAB / "media"), "host_path": str(LAB / "media"), "label": "Original sample media"}]))
    process = subprocess.Popen([str(package / "StackarrPreview.exe"), "--controller-serve", str(STATE / "controller"), "--controller-port", "29014"],
        env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    (STATE / "controller.pid").write_text(str(process.pid))
    command(["compose", "--project-name", PROJECT, "-f", str(STATE / "compose.json"), "up", "-d", "--wait", "--wait-timeout", "120"])
    command(["compose", "--project-name", PROJECT, "-f", str(STATE / "compose.json"), "exec", "-T", "stackarr", "python", "-c",
        "from pathlib import Path; Path('/var/lib/stackarr/self-update-preserve.txt').write_text('Original Stackarr configuration file; preserve across updates.')"])
    command(["compose", "--project-name", "stackarr-owned-" + CORE, "-f", str(STATE / "controller/state/deployments" / CORE / "compose.json"), "up", "-d", "--wait", "--wait-timeout", "180"])
    service = host()
    payload = load_receipt(service, CORE)
    updater = Updates(service)
    settings = {}
    for key in payload["apps"]:
        for _ in range(90):
            try:
                settings[key] = updater.protected(payload, key, service.store.secret(key))
                break
            except Exception:
                time.sleep(1)
        assert key in settings
    (output / "lab-before.json").write_text(json.dumps({"apps": {key: inspect_container(service, CORE, payload, key)["Id"] for key in payload["apps"]},
        "settings": settings, "controller": fingerprint(service.store.root)}))
    print("Self-update-capable packaged baseline and original four-app test lab ready; main apps excluded.", flush=True)


def wait_job(output, identity, expected=None, timeout=480):
    path = STATE / "stackarr-maintenance/jobs" / identity / "job.json"
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        job = read(path)
        if job["phase"] != previous:
            print("Stackarr " + job["action"] + ": " + job["phase"], flush=True)
            previous = job["phase"]
        if job["phase"] in {"succeeded", "rolled-back", "failed-recovered", "needs-recovery"}:
            if expected:
                assert job["phase"] == expected, job.get("failure", job["message"])
            (output / (identity + "-result.json")).write_text(json.dumps({k: job.get(k) for k in ("id", "action", "phase", "message", "failure_phase", "failure")}, indent=2))
            return job
        time.sleep(.5)
    raise AssertionError("Independent Stackarr worker timed out")


def check_preserved(output, page=None):
    before = read(output / "before.json")
    original = read(output / "lab-before.json")
    service = host()
    payload = load_receipt(service, CORE)
    for key in payload["apps"]:
        info = inspect_container(service, CORE, payload, key)
        assert info["Id"] == original["apps"][key] and info["State"]["Running"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(Updates(service).protected, payload, key, service.store.secret(key)).result(timeout=30) == original["settings"][key]
    assert hashes(LAB / "media") == before["lab_media"]
    assert main_settings() == before["main_settings"] and hashes(MAIN / "media") == before["main_media"]
    assert set(before["running"]) <= set(command(["ps", "-q", "--no-trunc"]).splitlines())
    if page:
        assert page.request.get(ORIGIN + "/api/session").status == 200
    assert command(["compose", "--project-name", PROJECT, "-f", str(STATE / "compose.json"), "exec", "-T", "stackarr", "cat", "/var/lib/stackarr/self-update-preserve.txt"]) == "Original Stackarr configuration file; preserve across updates."


def journey(output, archive, action="update", identity=None, expected="succeeded"):
    if archive:
        SelfUpdates(STATE).admit(archive)
    password = read(LAB / "access.json")["owner_password"]
    prior_page_size = None
    if action == "rollback":
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=45, headers={"Origin": ORIGIN}) as client:
            authenticated = client.post("/api/login", json={"password": password})
            authenticated.raise_for_status()
            client.headers["X-CSRF-Token"] = authenticated.json()["csrf"]
            saved = client.get("/api/config").json()
            prior_page_size = saved["config"]["dashboard"]["page_size"]
            saved["config"]["dashboard"]["page_size"] = 25 if prior_page_size != 25 else 26
            client.put("/api/config", json={"revision": saved["revision"], "config": saved["config"], "credentials": {}}).raise_for_status()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(120000)
        page.goto(ORIGIN)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
        if action == "rollback":
            button = page.locator('[data-stackarr-review="rollback"][data-stackarr-id="' + identity + '"]')
        else:
            button = page.get_by_role("button", name="Review Stackarr update", exact=True)
        expect(button).to_be_visible(timeout=120000)
        button.click()
        apply = page.get_by_role("button", name="Roll back Stackarr" if action == "rollback" else "Update Stackarr", exact=True)
        expect(apply).to_be_visible(timeout=120000)
        page.screenshot(path=str(output / (action + "-review-" + expected + ".png")), full_page=True)
        with page.expect_response(lambda r: r.url.endswith("/api/stackarr-update-apply")) as response:
            apply.click()
        assert response.value.status == 202
        queued = response.value.json()["id"]
        if action == "rollback":
            expect(page.get_by_label("Rows per page", exact=True)).to_be_disabled()
        job = wait_job(output, queued, expected)
        page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
        page.wait_for_function("identity => state.stackarrUpdates?.history.some(row => row.id === identity.id && row.phase === identity.phase) && !state.stackarrUpdates.recover && !state.stackarrUpdatePending", arg={"id": queued, "phase": expected})
        expect(page.get_by_text(job["message"], exact=False).first).to_be_visible(timeout=120000)
        page.screenshot(path=str(output / (action + "-" + expected + ".png")), full_page=True)
        check_preserved(output, page)
        if prior_page_size is not None:
            assert page.request.get(ORIGIN + "/api/config").json()["config"]["dashboard"]["page_size"] == prior_page_size
            expect(page.get_by_label("Rows per page", exact=True)).to_have_value(str(prior_page_size))
            expect(page.get_by_label("Rows per page", exact=True)).to_be_enabled()
            assert page.get_by_text("Status refresh failed.", exact=False).count() == 0
        (output / (queued + "-preservation.json")).write_text(json.dumps({"passed": True,
            "action": action, "phase": expected, "current_session_valid": True,
            "four_lab_app_ids_and_protected_settings_preserved": True,
            "main_settings_credentials_and_containers_preserved": True,
            "lab_media_hashes_preserved": 6, "main_media_hashes_preserved": 16,
            "restored_settings_visible_and_editable": prior_page_size is not None}, indent=2))
        browser.close()
    return job


def interrupted(output, archive, baseline_package):
    updater = SelfUpdates(STATE)
    updater.admit(archive)
    # Ask the active controller to review its own release. A development module
    # may have newer fingerprint rules than the older release under test.
    with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=120, headers={"Origin": ORIGIN}) as client:
        authenticated = client.post("/api/login", json={"password": read(LAB / "access.json")["owner_password"]})
        authenticated.raise_for_status()
        client.headers["X-CSRF-Token"] = authenticated.json()["csrf"]
        reviewed = client.post("/api/stackarr-update-review", json={"action": "update"})
        reviewed.raise_for_status()
        approved = client.post("/api/stackarr-update-apply", json={"review_token": reviewed.json()["review_token"]})
        approved.raise_for_status()
        job_id = approved.json()["id"]
    path = STATE / "stackarr-maintenance/jobs" / job_id / "job.json"
    for _ in range(240):
        job = read(path)
        if job["phase"] in {"succeeded", "failed-recovered", "needs-recovery"}:
            raise AssertionError("Candidate ended before the intended interruption: " + str(job.get("failure", job["phase"])))
        if job["phase"] == "checking-candidate":
            ids = command(["ps", "-q", "--no-trunc", "--filter", "name=^/" + PROJECT + "-stackarr-1$"]).split()
            if ids:
                info = json.loads(command(["inspect", ids[0]]))[0]
                if info["Config"].get("Labels", {}).get("io.stackarr.release") == job["target"]["release"]:
                    marker = command(["exec", ids[0], "python", "-c", "import sqlite3; print(sqlite3.connect('/var/lib/stackarr/stackarr.db').execute(\"SELECT count(*) FROM sqlite_master WHERE name='self_update_failure_fixture'\").fetchone()[0])"])
                    if marker == "1":
                        command(["pause", ids[0]])
                        break
        time.sleep(.25)
    else:
        raise AssertionError("Disposable candidate did not reach its write-before-health interruption point")
    env = os.environ | {"STACKARR_SELF_TEST_PID": str(job["worker_pid"]), "STACKARR_SELF_TEST_ROOT": str(STATE), "STACKARR_SELF_TEST_JOB": job_id}
    stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "$taskWorker=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $env:STACKARR_SELF_TEST_PID); if (-not $taskWorker -or $taskWorker.Name -ne 'StackarrPreview.exe' -or -not $taskWorker.CommandLine.Contains('--stackarr-maintenance') -or -not $taskWorker.CommandLine.Contains($env:STACKARR_SELF_TEST_ROOT) -or -not $taskWorker.CommandLine.Contains($env:STACKARR_SELF_TEST_JOB)) { exit 9 }; Stop-Process -Id $taskWorker.ProcessId -Force"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert stopped.returncode == 0
    (output / "interruption.json").write_text(json.dumps({"job": job_id, "candidate_database_write_observed": True,
        "only_candidate_paused": True, "only_recorded_worker_killed": True, "older_packaged_launcher": baseline_package.name}, indent=2))
    print("Killed only the independent test worker after candidate database writes; reopening the older packaged launcher.", flush=True)
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", str(baseline_package / "Start-StackarrPreview.ps1"),
        "-StateDirectory", str(STATE), "-NoBrowser"], capture_output=True, text=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    (output / "interrupted-reopen.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0
    recovered = wait_job(output, job_id, "failed-recovered")
    check_preserved(output)
    return recovered


def bootstrap(output, archive):
    """Upgrade an older preview without its background browser polling race."""
    SelfUpdates(STATE).admit(archive)
    with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=120, headers={"Origin": ORIGIN}) as client:
        authenticated = client.post("/api/login", json={"password": read(LAB / "access.json")["owner_password"]})
        authenticated.raise_for_status()
        client.headers["X-CSRF-Token"] = authenticated.json()["csrf"]
        reviewed = client.post("/api/stackarr-update-review", json={"action": "update"})
        reviewed.raise_for_status()
        approved = client.post("/api/stackarr-update-apply", json={"review_token": reviewed.json()["review_token"]})
        approved.raise_for_status()
        identity = approved.json()["id"]
    job = wait_job(output, identity, "succeeded")
    check_preserved(output)
    (output / "successful-job.json").write_text(json.dumps({"id": job["id"]}))


def finalize(output):
    check_preserved(output)
    successful = read(output / "successful-job.json")["id"]
    interruption = read(output / "interruption.json")
    results = [read(path) for path in output.glob("*-result.json")]
    assert next(row for row in results if row["id"] == successful)["phase"] == "succeeded"
    assert any(row["phase"] == "rolled-back" for row in results)
    assert any(row["phase"] == "failed-recovered" and row["failure_phase"] == "checking-candidate"
        and "settings changed" in row["failure"] for row in results)
    assert next(row for row in results if row["id"] == interruption["job"])["phase"] == "failed-recovered"
    before = read(output / "before.json")
    report = {"passed": True, "successful_update": successful, "active_release": SelfUpdates(STATE).listing()["current"], "manual_rollback": True,
        "rollback_restored_preference_and_kept_session": True, "failed_candidate_data_detected": True,
        "fresh_process_interrupted_recovery": interruption, "lab_app_ids_and_protected_settings_preserved": 4,
        "lab_media_hashes_preserved": len(before["lab_media"]), "main_media_hashes_preserved": len(before["main_media"]),
        "main_settings_credentials_and_running_containers_preserved": True,
        "arbitrary_stackarr_config_file_preserved": True, "operations": results}
    (output / "report.json").write_text(json.dumps(report, indent=2))
    service = host()
    payload = load_receipt(service, CORE)
    # The assertions above checked each exact app identity and settings. Compose
    # down removes only these owned containers/networks, never configuration volumes.
    for key in payload["apps"]:
        assert inspect_container(service, CORE, payload, key)["Id"] == read(output / "lab-before.json")["apps"][key]
    command(["compose", "--project-name", "stackarr-owned-" + CORE, "-f",
        str(STATE / "controller/state/deployments" / CORE / "compose.json"), "down"])
    runtime = read(STATE / "stackarr-runtime.json")
    dashboard = json.loads(command(["inspect", PROJECT + "-stackarr-1"]))[0]
    assert dashboard["Config"]["Labels"]["com.docker.compose.project"] == PROJECT
    assert next(m["Name"] for m in dashboard["Mounts"] if m["Destination"] == "/var/lib/stackarr") == runtime["volume"]
    command(["compose", "--project-name", PROJECT, "-f", str(STATE / "compose.json"), "down"])
    env = os.environ | {"STACKARR_SELF_TEST_CONTROLLER": str(STATE / "controller")}
    stopped = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_SELF_TEST_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert stopped.returncode == 0
    assert hashes(LAB / "media") == before["lab_media"] and main_settings() == before["main_settings"]
    assert hashes(MAIN / "media") == before["main_media"]
    expected_running = set(before["running"]) - set(read(output / "lab-before.json")["apps"].values())
    assert expected_running <= set(command(["ps", "-q", "--no-trunc"]).splitlines())
    (output / "cleanup.json").write_text(json.dumps({"passed": True, "only_owned_lab_containers_and_networks_removed": True,
        "volumes_media_staged_packages_and_checkpoints_retained": True, "main_preserved": True}, indent=2))
    print("All packaged self-update/recovery checks passed; isolated containers stopped and data retained.", flush=True)


def resume(output, package):
    """Reopen a retained managed lab; retain earlier identity evidence separately."""
    from stackarr.self_update import pending

    assert not pending(STATE)
    before = read(output / "before.json")
    previous = read(output / "lab-before.json")
    assert main_settings() == before["main_settings"] and hashes(MAIN / "media") == before["main_media"]
    assert hashes(LAB / "media") == before["lab_media"]
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
        str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", str(STATE), "-NoBrowser"], capture_output=True, timeout=240)
    assert result.returncode == 0
    service = host()
    payload = load_receipt(service, CORE)
    command(["compose", "--project-name", "stackarr-owned-" + CORE, "-f",
        str(STATE / "controller/state/deployments" / CORE / "compose.json"), "up", "-d", "--wait", "--wait-timeout", "180"])
    for key in payload["apps"]:
        for _ in range(90):
            try:
                assert Updates(service).protected(payload, key, service.store.secret(key)) == previous["settings"][key]
                break
            except Exception:
                time.sleep(1)
        else:
            raise AssertionError("Retained lab settings changed while reopening")
    (output / "lab-before-first-generation.json").write_text(json.dumps(previous))
    (output / "before-first-generation.json").write_text(json.dumps(before))
    current = {key: inspect_container(service, CORE, payload, key)["Id"] for key in payload["apps"]}
    (output / "lab-before.json").write_text(json.dumps(previous | {"apps": current}))
    before["running"] = sorted(set(before["running"]) - set(previous["apps"].values()) | set(current.values()))
    (output / "before.json").write_text(json.dumps(before))
    check_preserved(output)
    print("Retained managed lab reopened; existing settings/media verified and new container generation recorded.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--failed-candidate", type=Path)
    parser.add_argument("--output", type=Path, default=Path("test-results/docker-self-update-20261018"))
    parser.add_argument("--phase", choices=["prepare", "update", "rollback", "failed", "interrupted", "finalize", "resume", "bootstrap"])
    args = parser.parse_args()
    output, package = args.output.resolve(), args.package.resolve()
    assert output.is_relative_to(Path("test-results").resolve()) and output.name.startswith("docker-self-update-")
    output.mkdir(exist_ok=True)
    if args.phase in {None, "prepare"}:
        prepare(output, package)
    if args.phase in {None, "update"}:
        job = journey(output, args.candidate.resolve())
        (output / "successful-job.json").write_text(json.dumps({"id": job["id"]}))
    if args.phase in {None, "rollback"}:
        identity = read(output / "successful-job.json")["id"]
        journey(output, None, "rollback", identity, "rolled-back")
    if args.phase in {None, "failed"}:
        journey(output, args.failed_candidate.resolve(), expected="failed-recovered")
    if args.phase in {None, "interrupted"}:
        interrupted(output, args.failed_candidate.resolve(), package)
    if args.phase == "finalize":
        finalize(output)
    if args.phase == "resume":
        resume(output, package)
    if args.phase == "bootstrap":
        bootstrap(output, args.candidate.resolve())


if __name__ == "__main__":
    main()
